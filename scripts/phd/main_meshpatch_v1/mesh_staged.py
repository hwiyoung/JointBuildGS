"""Run unchanged mesh operations in separate processes under the frozen RAM cap.

The GeoGS function and Open3D connected-component implementation are unchanged.
A Python return-profile hook observes its component arrays, avoiding a second
whole-source connectivity calculation solely for removal accounting.
"""
import argparse
import ctypes
import gc
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

from mesh_common import C, D, O, LT, dump, mesh_config, now, sha, status

VERSION = 'separate_processes_v1'
STAGES = ('cleanup', 'before', 'account', 'after')
GUARD_BYTES = 38 * 1024**3


def policy():
    path=C/'memory_execution_v1.json'
    assert sha(path)==json.loads(path.with_suffix('.lock.json').read_text())['sha256']
    data=json.loads(path.read_text())
    assert (data['container_limit_gib'],data['host_admission_available_gib'],data['admission_stable_seconds'])==(40,56,60)
    assert data['proactive_stop_gib']*1024**3==GUARD_BYTES and data['host_reserve_stop_gib']==16
    assert data['version']==VERSION and data['original_function_unmodified'] and data['original_open3d_clustering']
    return data


def trim():
    gc.collect()
    ctypes.CDLL(None).malloc_trim(0)


def memory():
    root = Path('/sys/fs/cgroup')
    return dict(current_bytes=int((root/'memory.current').read_text()),
                peak_bytes=int((root/'memory.peak').read_text()),
                events={k:int(v) for k,v in (s.split() for s in (root/'memory.events').read_text().splitlines())})


def host_available():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):return int(line.split()[1])*1024
    raise RuntimeError('MemAvailable missing')


def supervise(command, guard_bytes=GUARD_BYTES):
    events=memory()['events'];peak=0;guard=False;reason=None
    process=subprocess.Popen(command,start_new_session=True)
    while process.poll() is None:
        m=memory();peak=max(peak,m['current_bytes'])
        if m['current_bytes']>=guard_bytes or host_available()<16*1024**3:
            guard=True;reason='container_memory_margin' if m['current_bytes']>=guard_bytes else 'host_reserve_below_16GiB'
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        time.sleep(.25)
    last=memory();oom=last['events'].get('oom_kill',0)>events.get('oom_kill',0)
    return dict(exit_code=process.returncode,peak_observed_bytes=peak,proactive_stop=guard,
                stop_reason=reason,oom_kill=oom,guard_bytes=guard_bytes,finished_at=now(),scientific_verdict=None)


def workspace(key):
    return O/'mesh_stages_v1'/key


def binding(row, cfg):
    return dict(version=VERSION, source_sha256=row['sha256'],
                evaluation_sha256=row['evaluation_sha256'], values_sha256=row['values_sha256'],
                original_function_sha256=cfg['source_function']['sha256'],
                metric_inputs_sha256=sha(C/'mesh_metric_inputs_v1.json'),
                execution_policy_sha256=sha(C/'memory_execution_v1.json'))


def load(key):
    policy()
    cfg=mesh_config();row=next(r for r in cfg['targets'] if r['key']==key)
    return cfg,row,workspace(key)


def captured_cleanup(mesh, cfg):
    from mesh_worker import original_cleanup
    func=original_cleanup(cfg);capture={};old=sys.getprofile()
    def observe(frame,event,arg):
        if frame.f_code is not func.__code__:return
        if event=='c_return' and getattr(arg,'__name__','')=='cluster_connected_triangles':
            # Return freed native adjacency allocations to the OS before filtering.
            ctypes.CDLL(None).malloc_trim(0)
        if event=='return' and arg is not None:
            for name in ['triangle_clusters','cluster_n_triangles','cluster_area']:
                capture[name]=frame.f_locals[name]
    trim();sys.setprofile(observe)
    try:clean=func(mesh,cluster_to_keep=50)
    finally:sys.setprofile(old)
    assert set(capture)=={'triangle_clusters','cluster_n_triangles','cluster_area'}
    return clean,capture


def child(key, stage):
    import numpy as np
    import open3d as o3d
    from mesh_worker import first_hit, summarize, case_crops, stage1_metrics, removed_areas
    cfg,row,folder=load(key);folder.mkdir(parents=True,exist_ok=True)
    source=Path(row['mesh']);b=binding(row,cfg);started=time.monotonic()
    assert sha(source)==row['sha256']
    status(key,stage,execution=VERSION)
    result={}
    if stage=='cleanup':
        mesh=o3d.io.read_triangle_mesh(str(source));assert len(mesh.triangles)
        source_n=len(mesh.triangles)
        clean,arrays=captured_cleanup(mesh,cfg)
        assert len(arrays['triangle_clusters'])==source_n
        assert int(np.asarray(arrays['cluster_n_triangles']).sum())==source_n
        for name,a in arrays.items():np.save(folder/(name+'.npy'),a)
        post=folder/'fuse_post.ply';temp=folder/'fuse_post.writing.ply'
        assert o3d.io.write_triangle_mesh(str(temp),clean,write_ascii=False)
        temp.replace(post)
        result=dict(before_triangles=source_n,after_triangles=len(clean.triangles),
                    output_sha256=sha(post),output=str(post),
                    arrays={name:sha(folder/(name+'.npy')) for name in arrays})
    elif stage=='before':
        mcfg=C/'mesh_metric_inputs_v1.json'
        assert sha(mcfg)==json.loads((C/'mesh_metric_inputs_v1.lock.json').read_text())['sha256']
        for item in json.loads(mcfg.read_text())['inputs']:
            if item['site'] in [None,row['site']]:assert sha(item['path'])==item['sha256']
        assert sha(row['evaluation'])==row['evaluation_sha256']
        assert sha(row['values'])==row['values_sha256']
        e=dict(np.load(row['evaluation']));v=dict(np.load(row['values']))
        mesh=o3d.io.read_triangle_mesh(str(source));z=first_hit(mesh,e,v);result['before']=summarize(e,z)
        rec=LT/'patch_z'/f'{key}.npz'
        if rec.exists():
            errors=[]
            for aa,bb in zip(result['before'],summarize(e,dict(np.load(rec)))):
                for field in ['within_tau_pct','floating_pct','no_surface_pct']:
                    if aa[field] is not None:errors.append(abs(aa[field]-bb[field]))
            result['before_reference_check']=dict(reference=str(rec),max_area_difference_pp=max(errors,default=0),
                                                 status='PASS' if max(errors,default=0)<=.5 else 'STOP')
            assert result['before_reference_check']['status']=='PASS','STOP_BEFORE_BASELINE_MISMATCH'
        out=O/'patch_z'/f'{key}__before.npz';out.parent.mkdir(exist_ok=True)
        if out.exists():
            saved=dict(np.load(out));assert saved.keys()==z.keys()
            assert all(np.array_equal(saved[k],z[k],equal_nan=True) for k in z),'previous before array changed'
        else:np.savez_compressed(out,**z)
        result['case_crops']=case_crops(mesh,row,'before');trim()
        if 'stage1' in row['groups']:
            status(key,'stage1_before_metrics',execution=VERSION)
            result['stage1_before']=stage1_metrics(mesh,row['site'],row['prior'])
    elif stage=='account':
        source_info=json.loads((folder/'cleanup.json').read_text())['result']
        for name,value in source_info['arrays'].items():assert sha(folder/(name+'.npy'))==value
        mesh=o3d.io.read_triangle_mesh(str(source))
        e=dict(np.load(row['evaluation']));z=dict(np.load(O/'patch_z'/f'{key}__before.npz'))
        labels=np.load(folder/'triangle_clusters.npy',mmap_mode='r')
        counts=np.load(folder/'cluster_n_triangles.npy',mmap_mode='r')
        threshold=max(int(np.sort(counts)[-50]),50)
        f=np.asarray(mesh.triangles);deg=(f[:,0]==f[:,1])|(f[:,0]==f[:,2])|(f[:,1]==f[:,2])
        removed=(counts[labels]<threshold)|deg
        assert int((~removed).sum())==source_info['after_triangles']
        result['removed']=removed_areas(mesh,removed,e,z)
        result['case_crops']=case_crops(mesh,row,'removed',removed)
        postdir=O/'mesh_post'/key;postdir.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(postdir/'removed_source_triangles.npz',removed=np.flatnonzero(removed),source_triangle_count=len(f))
        surviving_degenerate=int((deg&(counts[labels]>=threshold)).sum())
        kept=counts[counts>=threshold]
        result['cleanup']=dict(before_triangles=len(f),after_triangles=source_info['after_triangles'],
            before_components=len(counts),after_components=len(kept) if not surviving_degenerate else None,
            min_remaining_component_triangles=int(kept.min()) if len(kept) and not surviving_degenerate else None,
            count_threshold=threshold,cluster_to_keep=50,ties_retained=True,
            removed_degenerate_triangles=surviving_degenerate,output=str(postdir/'fuse_post.ply'),
            output_sha256=source_info['output_sha256'],source_sha256=row['sha256'],
            original_function_sha256=cfg['source_function']['sha256'],
            component_accounting='Original function captured components; whole components retained. If surviving degenerates exist, recount after cleanup.')
    elif stage=='after':
        account=json.loads((folder/'account.json').read_text())['result']
        mesh=o3d.io.read_triangle_mesh(str(folder/'fuse_post.ply'))
        if account['cleanup']['removed_degenerate_triangles']:
            _,counts,_=mesh.cluster_connected_triangles();counts=np.asarray(counts)
            result['component_recount']=dict(after_components=len(counts),min_remaining_component_triangles=int(counts.min()) if len(counts) else None)
            trim()
        result['case_crops']=case_crops(mesh,row,'after')
        e=dict(np.load(row['evaluation']));v=dict(np.load(row['values']));z=first_hit(mesh,e,v)
        out=O/'patch_z'/f'{key}__after.npz'
        if out.exists():
            saved=dict(np.load(out));assert all(np.array_equal(saved[k],z[k],equal_nan=True) for k in z)
        else:np.savez_compressed(out,**z)
        result['after']=summarize(e,z);trim()
        if 'stage1' in row['groups']:
            status(key,'stage1_after_metrics',execution=VERSION)
            result['stage1_after']=stage1_metrics(mesh,row['site'],row['prior'])
    else:raise ValueError(stage)
    dump(folder/(stage+'.json'),dict(binding=b,result=result,seconds=time.monotonic()-started,
        process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        cgroup=memory(),finished_at=now(),scientific_verdict=None))


def run_stage(key, stage):
    cfg,row,folder=load(key);folder.mkdir(parents=True,exist_ok=True)
    record=folder/(stage+'.json')
    if record.exists():
        assert json.loads(record.read_text())['binding']==binding(row,cfg)
        return
    previous=folder/(stage+'_execution.json')
    if previous.exists() and json.loads(previous.read_text())['exit_code']:
        raise RuntimeError(f'{key} {stage}: prior failed attempt preserved; no automatic identical retry')
    receipt=dict(key=key,stage=stage,**supervise([sys.executable,__file__,key,'--stage',stage]))
    dump(folder/(stage+'_execution.json'),receipt)
    if receipt['exit_code']:
        status(key,'RESOURCE_BUDGET_EXCEEDED' if receipt['proactive_stop'] else 'FAILED',execution=VERSION,**{k:v for k,v in receipt.items() if k not in ['key','stage','scientific_verdict']})
        with (D/'issues.md').open('a') as f:
            f.write(f"\n- {now()}: {key} {stage} 종료 {receipt['exit_code']}. 선제 메모리 중지={receipt['proactive_stop']}, OOM 확인={receipt['oom_kill']}, 관측 최대 {receipt['peak_observed_bytes']/1024**3:.2f} GiB. 단계 기록은 {folder}. 같은 조건의 자동 반복 없음.\n")
        raise RuntimeError(f'{key} {stage}: {receipt}')
    assert record.exists()


def process(key, probe=False):
    cfg,row,folder=load(key);dest=D/'tables/meshes'/f'{key}.json'
    if dest.exists() and not probe:return
    if row['status']!='READY':
        dump(dest,dict(target=row,status=row['status'],scientific_verdict=None));return
    for stage in (('cleanup',) if probe else STAGES):run_stage(key,stage)
    if probe:return
    records={stage:json.loads((folder/(stage+'.json')).read_text()) for stage in STAGES}
    result=dict(target=row,status='PASS',scientific_verdict=None,provenance='[이 발주에서 냄]',execution=VERSION,case_crops=[])
    for stage in STAGES:
        data=dict(records[stage]['result'])
        if stage=='cleanup':continue
        result['case_crops']+=data.pop('case_crops',[])
        recount=data.pop('component_recount',None);result.update(data)
        if recount:result['cleanup'].update(recount)
    result.update(seconds=sum(r['seconds'] for r in records.values()),finished_at=now(),
                  memory_stage_receipts={stage:str(folder/(stage+'_execution.json')) for stage in STAGES})
    final=Path(result['cleanup']['output']);final.parent.mkdir(parents=True,exist_ok=True)
    if final.exists():assert sha(final)==result['cleanup']['output_sha256']
    else:os.link(folder/'fuse_post.ply',final)
    dump(dest,result);status(key,'complete',seconds=result['seconds'],after_triangles=result['cleanup']['after_triangles'],execution=VERSION)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('key');parser.add_argument('--stage',choices=STAGES)
    parser.add_argument('--probe-cleanup',action='store_true');args=parser.parse_args()
    if args.stage:child(args.key,args.stage)
    else:process(args.key,args.probe_cleanup)

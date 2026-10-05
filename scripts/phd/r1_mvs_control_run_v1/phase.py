"""Execute the sealed R1 plan in Docker and verify realized checkpoint controls."""
import argparse, hashlib, json, math, os, subprocess, sys, time
from pathlib import Path
from types import SimpleNamespace

def read(p): return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''): h.update(b)
    return h.hexdigest()
def write(p,v):
    with Path(p).open('x') as f: json.dump(v,f,indent=2,allow_nan=False)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['verify','anchor','preflight','refinement','extract']);ap.add_argument('--iteration',type=int);a=ap.parse_args()
    out=Path('/output');plan=read('/runtime/execution_plan.json');phase=a.phase
    assert Path('/.dockerenv').exists() and not Path('/artifacts/JointBuildGS').exists()
    assert sha('/input/input_manifest.json')=='26cba2200d6a49589270f8f6c66f4f1670705f05fa1447056e31371d6531223a'
    if phase=='verify':
        manifest=read('/input/input_manifest.json')
        for row in manifest['files']:
            p=Path('/input')/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],row['path']
        provenance=read('/runtime/refinement_source/mvs_pgsr_source_provenance.json')
        for name,key in [('anchor','parent_implementation_hashes'),('refinement','prepared_implementation_hashes')]:
            for path,digest in provenance[key].items():assert sha(Path('/runtime')/(name+'_source')/path)==digest,(name,path)
        previous=read('/runtime/receipt.json')
        for name,digest in previous['runtime_files'].items():assert sha(Path('/runtime')/name)==digest,name
        write(out/'receipt.json',dict(status='PASS',input_files=len(manifest['files']),scientific_verdict=None))
        return
    env=dict(os.environ);env.update(plan['anchor' if phase in ('anchor','extract') else 'refinement']['environment'])
    env['PYTHONUNBUFFERED']='1';env['JBGS_RUN_PHASE']=phase
    if phase=='extract':
        import shutil
        it=a.iteration;model=out/'model';target=model/'point_cloud'/f'iteration_{it}';target.mkdir(parents=True)
        complete=Path('/trained/model/jbgs_complete')/f'iteration_{it}';r=read(complete/'receipt.json')
        assert sha(complete/'point_cloud.ply')==r['ply_sha256']
        shutil.copy2(complete/'point_cloud.ply',target/'point_cloud.ply');shutil.copy2('/trained/model/cfg_args',model/'cfg_args')
        command=['python','render.py','-s','/input/scene','-m',str(model),'--iteration',str(it),'--mesh_res','512','--num_cluster','50','--data_device','cpu']
    else:
        spec=plan['anchor' if phase=='anchor' else 'refinement'];command=list(spec['argv'])
        if phase=='preflight':command+=plan['refinement']['preflight_override']
        command[1]='/driver/train_observed.py'
        if phase!='anchor':
            anchor=read('/anchor/receipt.json');assert anchor['iteration']==8000
            assert sha('/anchor/checkpoint.pth')==anchor['checkpoint_sha256']
            if phase=='refinement':
                gate=read('/gate/receipt.json');assert gate['status']=='PASS' and gate['anchor_sha256']==anchor['checkpoint_sha256']
    invocation=dict(phase=phase,command=command,started_unix=time.time(),runtime_image_id=plan['runtime_image_id'],driver_sha256=sha(__file__),scientific_verdict=None)
    write(out/'invocation.json',invocation)
    result={**invocation,'status':'FAIL'}
    with (out/'process.log').open('x') as log,(out/'gpu.csv').open('x') as gpu:
        child=subprocess.Popen(command,cwd='/source',env=env,stdout=log,stderr=subprocess.STDOUT)
        while child.poll() is None:
            subprocess.run(['nvidia-smi','--query-gpu=timestamp,uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits'],stdout=gpu,stderr=subprocess.DEVNULL);gpu.flush();time.sleep(5)
    result.update(exit_code=child.returncode,wall_seconds=time.time()-invocation['started_unix'])
    try:
        assert child.returncode==0, 'process exit '+str(child.returncode)
        if phase=='extract':
            import numpy as np,open3d as o3d
            surfaces={}
            for name in ('fuse.ply','fuse_post.ply'):
                p=out/'model/train'/f'ours_{a.iteration}'/name;m=o3d.io.read_triangle_mesh(str(p))
                assert len(m.vertices)>0 and len(m.triangles)>0 and np.isfinite(np.asarray(m.vertices)).all()
                surfaces[name]=dict(path=str(p.relative_to(out)),sha256=sha(p),vertices=len(m.vertices),triangles=len(m.triangles))
            split=read('/input/scene/split_manifest.json');renders=[]
            from PIL import Image
            for index,v in enumerate(sorted(split['evaluation'],key=lambda v:v['name'])):
                folder=out/'model/test'/f'ours_{a.iteration}'
                gt=folder/'gt'/f'{index:05d}.png';rgb=folder/'renders'/f'{index:05d}.png'
                with Image.open(gt) as x,Image.open(Path('/input/scene/images')/v['name']) as y:assert np.array_equal(np.asarray(x.convert('RGB')),np.asarray(y.convert('RGB'))),v['name']
                renders.append(dict(name=v['name'],path=str(rgb.relative_to(out)),sha256=sha(rgb)))
            result.update(surfaces=surfaces,renders=renders,iteration=a.iteration)
        else:
            stop=8000 if phase=='anchor' else 8100 if phase=='preflight' else 30000
            complete=out/'model/jbgs_complete'/f'iteration_{stop}';receipt=read(complete/'receipt.json')
            for name,key in [('checkpoint.pth','checkpoint_sha256'),('point_cloud.ply','ply_sha256')]:assert sha(complete/name)==receipt[key]
            assert receipt['iteration']==stop and receipt['after_protection_registration'] is True
            result.update(iteration=stop,checkpoint=receipt)
            progress=read(out/'progress.json');assert progress['iteration']==stop and progress['finite']
            if phase!='anchor':
                sys.path.insert(0,'/driver');from legacy_validation import validate_completion
                cfg=dict(anchors={'R1':{'sha256':anchor['checkpoint_sha256']}},anchor_iteration=8000,final_iteration=30000,preflight={'stop_after':8100})
                detail=validate_completion(out,cfg,SimpleNamespace(region='R1',phase='preflight' if phase=='preflight' else 'train',mode='mvs',prior=.005))
                grads=[json.loads(line) for line in (out/'model/mvs_pgsr_gradient_trace.jsonl').read_text().splitlines()]
                assert grads and all(g.get('finite',True) for row in grads for g in row['total_loss_gradients'].values())
                result.update(anchor_sha256=anchor['checkpoint_sha256'],validation=detail,gradient_rows=len(grads))
        result['status']='PASS'
    except Exception as exc:result['error']=repr(exc)
    result['log_sha256']=sha(out/'process.log');write(out/'receipt.json',result)
    print(json.dumps({k:result.get(k) for k in ('phase','status','iteration','wall_seconds','error')}),flush=True)
    if result['status']!='PASS':raise SystemExit(1)

if __name__=='__main__':main()

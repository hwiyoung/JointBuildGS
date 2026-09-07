"""Fresh official auxiliary extractions governed by the frozen resource amendment."""
import argparse
import gc
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).parent/'evaluation'))
from runtime_layout import RuntimeLayout
from supplemental_repeat import SupplementalRepeat
from resource_contract import ResourceContract, sha, require
from resource_schedule import acquire_extraction_lock, HELPER_SOURCE as SCHEDULER_SOURCE
from parse_extraction import PARSER_SOURCE, PARSER_SHA256, parse_extraction_log
from repeat_contract import REPEAT_HELPER_SOURCE, load_repeat_binding

IMAGE = 'sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'


def dump(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def snapshot(path, content):
    with Path(path).open('xb') as stream:
        stream.write(content)


def memory():
    base = Path('/sys/fs/cgroup')
    return dict(unix=time.time(), memory_current_bytes=int((base/'memory.current').read_text()),
                memory_peak_bytes=int((base/'memory.peak').read_text()), memory_max=(base/'memory.max').read_text().strip(),
                host_mem_available_bytes=next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()
                                             if line.startswith('MemAvailable:')),
                memory_events={key:int(value) for key,value in (line.split() for line in (base/'memory.events').read_text().splitlines())})


def file_record(root, path):
    return dict(path=str(path.relative_to(root)), sha256=sha(path), bytes=path.stat().st_size)


def native_variant(output, planned, source_ply, cfg_args, common, resource, cfg, repeat_binding):
    directory = output/'auxiliary'/planned['name']
    directory.mkdir(parents=True, exist_ok=False)
    point = directory/f'model/point_cloud/iteration_{planned["iteration"]}/point_cloud.ply'
    point.parent.mkdir(parents=True)
    shutil.copyfile(source_ply, point)
    shutil.copyfile(cfg_args, directory/'model/cfg_args')
    snapshot(directory/'parse_extraction_snapshot.py', PARSER_SOURCE)
    if repeat_binding:
        snapshot(directory/'repeat_contract_snapshot.json', resource.repeat.path.read_bytes())
        snapshot(directory/'repeat_helper_snapshot.py', REPEAT_HELPER_SOURCE)
    source_sha = sha(source_ply)
    require(sha(point) == source_sha, 'Exact source PLY copy differs')
    host_wait_start = time.monotonic()
    minimum = resource.data['resource_policy']['memory_limit_bytes']+resource.data['resource_policy']['minimum_host_headroom_bytes']
    with (directory/'host_memory_wait.jsonl').open('x') as log:
        while True:
            sample = memory()
            log.write(json.dumps(sample)+'\n')
            log.flush()
            if sample['host_mem_available_bytes'] >= minimum:
                break
            time.sleep(5)
    host_wait = time.monotonic()-host_wait_start
    before = memory()
    require(before['memory_max'] == str(resource.data['resource_policy']['memory_limit_bytes']), 'Actual memory cap differs')
    model = directory/'model'
    command = ['python','render.py','-s','/input/scene','-m',str(model), '--iteration',str(planned['iteration']),
               '--mesh_res',str(planned['mesh_res'])]
    if not planned['export_images']:
        command += ['--skip_train','--skip_test']
    invocation = dict(common, phase='auxiliary_variant', variant=planned['name'],
                      **{key:planned[key] for key in ('iteration','mesh_res','required','export_images','source_kind')},
                      command=command, source_complete_ply_sha256=source_sha, copied_ply_sha256=sha(point),
                      render_cfg_args_sha256=sha(model/'cfg_args'), memory_before=before,
                      cgroup_memory_limit_bytes=resource.data['resource_policy']['memory_limit_bytes'],
                      host_headroom_wait_seconds=host_wait,
                      extraction_helper_snapshot=dict(path='parse_extraction_snapshot.py',sha256=PARSER_SHA256),
                      started_unix=time.time())
    dump(directory/'invocation.json', invocation)
    samples = [before]
    start = time.monotonic()
    with (directory/'render.log').open('x') as log, (directory/'memory.jsonl').open('x') as memlog, (directory/'gpu.csv').open('x') as gpulog:
        memlog.write(json.dumps(before)+'\n')
        memlog.flush()
        child = subprocess.Popen(command, cwd='/source', stdout=log, stderr=subprocess.STDOUT)
        while True:
            pid, wait_status, usage = os.wait4(child.pid, os.WNOHANG)
            if pid:
                native_code = os.waitstatus_to_exitcode(wait_status)
                child.returncode = native_code
                child_rss = usage.ru_maxrss*1024
                break
            sampled = memory()
            samples.append(sampled)
            memlog.write(json.dumps(sampled)+'\n')
            memlog.flush()
            subprocess.run(['nvidia-smi','--query-gpu=timestamp,uuid,memory.used,utilization.gpu',
                            '--format=csv,noheader,nounits'], stdout=gpulog, stderr=subprocess.DEVNULL, check=False)
            gpulog.flush()
            time.sleep(2)
        native_wall = time.monotonic()-start
        after = memory()
        samples.append(after)
        memlog.write(json.dumps(after)+'\n')
    oom_delta = after['memory_events'].get('oom_kill',0)-before['memory_events'].get('oom_kill',0)
    confirmed_optional_oom = not planned['required'] and native_code == -9 and oom_delta >= 1
    status = 'TECHNICAL_RESOURCE_UNAVAILABLE' if confirmed_optional_oom else ('PASS' if native_code == 0 else 'FAIL')
    validation, files, realized, counts = [], [], None, None
    if native_code == 0:
        try:
            realized = parse_extraction_log(directory/'render.log', planned['mesh_res'], cfg['extraction']['num_cluster'])
            import numpy as np
            import open3d as o3d
            for name in ('fuse.ply','fuse_post.ply'):
                path = model/f'train/ours_{planned["iteration"]}'/name
                mesh = o3d.io.read_triangle_mesh(str(path))
                area = float(mesh.get_surface_area())
                valid = bool(len(mesh.vertices) and len(mesh.triangles) and np.isfinite(np.asarray(mesh.vertices)).all() and area > 0)
                validation.append(dict(path=str(path.relative_to(directory)), vertices=len(mesh.vertices), triangles=len(mesh.triangles),
                                       finite_vertices=bool(np.isfinite(np.asarray(mesh.vertices)).all()),
                                       surface_area_m2=area, valid_triangle_surface=valid))
                if not valid:
                    status = 'FAIL'
                del mesh
                gc.collect()
            if planned['export_images']:
                counts = {role:len(list((model/role/f'ours_{planned["iteration"]}/renders').glob('*.png'))) for role in ('train','test')}
                if counts != dict(train=cfg['regions'][common['region']]['expected_train'],test=cfg['regions'][common['region']]['expected_test']):
                    status = 'FAIL'
        except Exception as error:
            status = 'FAIL'
            validation.append(dict(validation_error=repr(error)))
    for name in ('fuse.ply','fuse_post.ply'):
        path = model/f'train/ours_{planned["iteration"]}'/name
        exists = path.is_file() and path.stat().st_size > 0
        files.append(dict(path=str(path.relative_to(directory)), exists=exists, bytes=path.stat().st_size if exists else None,
                          sha256=sha(path) if exists else None, atomic_variant_available=status == 'PASS'))
    receipt = dict(invocation, status=status, native_exit_code=native_code,
                   validated_exit_code=0 if status=='PASS' else (native_code or 95), exit_code=0 if status=='PASS' else (native_code or 95),
                   wall_seconds=native_wall, child_peak_rss_bytes=child_rss, memory_after=after,
                   native_pid=child.pid, cgroup_oom_kill_delta=oom_delta,
                   memory_trace=dict(path='memory.jsonl',sha256=sha(directory/'memory.jsonl')),
                   source_log=dict(path='render.log',sha256=sha(directory/'render.log')),
                   sampled_peak_memory_current_bytes=max(s['memory_current_bytes'] for s in samples),
                   sampled_min_host_mem_available_bytes=min(s['host_mem_available_bytes'] for s in samples),
                   files=files, validation=validation, realized_extraction=realized, exported_images=counts,
                   technical_unavailability_is_geometry_failure=False, technical_unavailability_is_reference_absence=False,
                   finished_unix=time.time())
    dump(directory/'receipt.json', receipt)
    resource.validate_variant(receipt, planned, directory)
    print(json.dumps(dict(variant=planned['name'],status=status,wall_seconds=native_wall,oom_kill_delta=oom_delta)),flush=True)
    return dict(name=planned['name'], status=status, receipt_path=str((directory/'receipt.json').relative_to(output)),
                receipt_sha256=sha(directory/'receipt.json'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', type=Path, default=Path('/task'))
    parser.add_argument('--region', choices=('P1','P2','P3'), required=True)
    parser.add_argument('--condition', required=True)
    parser.add_argument('--run-family', choices=('primary','native_repeat_1'), default='primary')
    args = parser.parse_args()
    require(Path('/.dockerenv').exists() and not Path('/reference').exists() and not Path('/artifacts/JointBuildGS').exists(),
            'Use the isolated Docker resource runtime')
    task, output = args.task, Path('/output')
    cfg_path = task/'contracts/execution_v1.json'
    cfg = json.loads(cfg_path.read_text())
    layout = RuntimeLayout(task, task/'contracts/runtime_layout_allocator_v2.json', cfg['regions'])
    repeat = SupplementalRepeat(task, task/'contracts/supplemental_repeat_v1.json', layout)
    resource = ResourceContract(task, task/'contracts/extraction_resource_v3.json', layout, repeat)
    repeat_id = None if args.run_family == 'primary' else args.run_family
    expected_output = resource.aux_run(args.region,args.condition,repeat_id)
    require(os.path.samefile(expected_output, output), 'Resource output mount differs from resolver')
    require(not (output/'auxiliary_invocation.json').exists(), 'Resource auxiliary output must be fresh')
    run = repeat.run(args.region) if repeat_id else layout.run(args.region,args.condition)
    train = json.loads((run/'train_receipt.json').read_text())
    render = json.loads((run/'render_receipt.json').read_text())
    metrics = json.loads((run/'metrics_receipt.json').read_text())
    for phase,value in (('train',train),('render',render),('metrics',metrics)):
        require(value.get('status') == 'PASS' and value.get('phase') == phase and value.get('condition') == args.condition
                and value.get('region') == args.region and value.get('config_sha256') == sha(cfg_path), 'Completed native phases required')
        layout.require_receipt(value)
        if repeat_id:
            repeat.require_run_receipt(value,args.region)
    input_root = Path('/input')
    manifest_path = input_root/'input_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    require(sha(manifest_path) == train['input_manifest_sha256'], 'Frozen input identity differs')
    for row in manifest['files']:
        require(sha(input_root/row['path']) == row['sha256'], 'Frozen input changed: '+row['path'])
    source = Path('/source')
    source_hashes = {str(p.relative_to(source)):sha(p) for p in sorted(source.rglob('*.py')) if 'submodules' not in p.parts}
    require(source_hashes == train['implementation_hashes'] and os.environ['JBGS_RUNTIME_IMAGE_ID'] == IMAGE, 'Scientific source/runtime differs')
    effective = json.loads(subprocess.check_output(['python','-c',
        'import json,torch;torch.cuda.init();print(json.dumps([torch.cuda.get_allocator_backend(),torch.cuda.memory_stats()["max_split_size"]]))'],text=True))
    require(effective == ['native',134217728], 'Allocator differs')
    anchor = layout.anchor_checkpoint(args.region)
    repeat_binding = load_repeat_binding(cfg_path, layout.path, args.region,args.condition,'auxiliary',
        contract_path=repeat.path if repeat_id else '/no_repeat_contract', anchor_root=anchor,
        gate_path=task/layout.data['parity_directory']/args.region/'anchor_gate.json')
    common = dict(task_id=cfg['task_id'],region=args.region,condition=args.condition,phase='auxiliary',
                  run_family=args.run_family,config_sha256=sha(cfg_path),input_manifest_sha256=sha(manifest_path),
                  runtime_layout_sha256=layout.digest,runtime_revision='allocator_v2',runtime_image_id=IMAGE,
                  implementation_hashes=source_hashes,scientific_verdict=None,**resource.binding(),**(repeat_binding or {}),
                  driver_sha256=sha(__file__), container_id=(output/'container_id.txt').read_text().strip(),
                  environment={key:os.environ.get(key) for key in ('LD_PRELOAD','LD_LIBRARY_PATH','TORCH_HOME','OMP_NUM_THREADS','PYTORCH_CUDA_ALLOC_CONF','JBGS_RUNTIME_REVISION')})
    for name, content in [('auxiliary_driver_snapshot.py',Path(__file__).read_bytes()),
                          ('resource_contract_snapshot.py',Path(__file__).with_name('resource_contract.py').read_bytes()),
                          ('resource_schedule_snapshot.py',SCHEDULER_SOURCE),('parse_extraction_snapshot.py',PARSER_SOURCE),
                          ('auxiliary_config_snapshot.json',cfg_path.read_bytes()),
                          ('auxiliary_runtime_layout_snapshot.json',layout.path.read_bytes()),
                          ('auxiliary_resource_contract_snapshot.json',resource.path.read_bytes())]:
        snapshot(output/name, content)
    if repeat_binding:
        snapshot(output/'auxiliary_repeat_contract_snapshot.json',repeat.path.read_bytes())
        snapshot(output/'auxiliary_repeat_helper_snapshot.py',REPEAT_HELPER_SOURCE)
    lock, scheduling = acquire_extraction_lock('auxiliary')
    start = time.monotonic()
    common['resource_scheduling'] = dict(scheduling, helper_snapshot_path='resource_schedule_snapshot.py')
    common['started_unix'] = time.time()
    common['command'] = ['python','/audit/run_auxiliary_resource_v3.py','--region',args.region,'--condition',args.condition,'--run-family',args.run_family]
    dump(output/'auxiliary_invocation.json',common)
    variants, error = [], None
    try:
        for planned in resource.variant_inventory(args.region,args.condition,repeat_id):
            complete = anchor if planned['source_kind'] == 'common_anchor' else run/'model/jbgs_complete/iteration_30000'
            state = json.loads((complete/'receipt.json').read_text())
            ply = complete/'point_cloud.ply'
            require(state['iteration'] == planned['iteration'] and sha(ply) == state['ply_sha256'], 'Complete-state source PLY differs')
            variants.append(native_variant(output,planned,ply,run/'model/cfg_args',common,resource,cfg,repeat_binding))
    except Exception as exception:
        error = repr(exception)
    status = 'PASS' if error is None else 'FAIL'
    manifest_path = output/'auxiliary_manifest.json'
    dump(manifest_path,dict(common,status=status,variants=variants,error=error,
         phase_pass_meaning='Required variants passed and every optional variant is successful or has confirmed cgroup OOM evidence'))
    producers = [file_record(output,path) for path in sorted(output.rglob('*')) if path.is_file() and
                 ('model' not in path.relative_to(output).parts) and path.name not in ('auxiliary_receipt.json',)]
    rss = []
    for row in variants:
        value = json.loads((output/row['receipt_path']).read_text())
        rss.append(value['child_peak_rss_bytes'])
    receipt = dict(common,status=status,native_exit_code=0 if status=='PASS' else 1,validated_exit_code=0 if status=='PASS' else 1,
                   phase_pass_meaning='RESOURCE_CONTRACT_REQUIREMENTS_MET_WITH_OPTIONAL_FAILURES_EXPLICIT',
                   wall_seconds=time.monotonic()-start,child_peak_rss_bytes=max(rss,default=0),variants=variants,error=error,
                   validation=[dict(path='auxiliary_manifest.json',exists_nonempty=True,bytes=manifest_path.stat().st_size,sha256=sha(manifest_path))],
                   producer_files=producers,finished_unix=time.time())
    if status == 'PASS':
        resource.validate_receipt(receipt,args.region,args.condition,repeat_id)
    dump(output/'auxiliary_receipt.json',receipt)
    print(json.dumps(dict(region=args.region,condition=args.condition,phase='auxiliary',status=status,error=error)),flush=True)
    raise SystemExit(0 if status=='PASS' else 1)


if __name__ == '__main__':
    main()

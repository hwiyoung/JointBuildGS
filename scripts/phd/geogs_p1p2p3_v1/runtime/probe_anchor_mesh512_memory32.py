"""One nonprimary P1 anchor-512 resource probe under a 32GiB memory cap."""
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import time


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def dump(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def require(value, message):
    if not value:
        raise ValueError(message)


def helper(name):
    path = Path('/probe')/(name+'_snapshot.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def memory():
    root = Path('/sys/fs/cgroup')
    available = next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()
                     if line.startswith('MemAvailable:'))
    events = dict(line.split() for line in (root/'memory.events').read_text().splitlines())
    return dict(unix=time.time(), memory_current_bytes=int((root/'memory.current').read_text()),
                memory_peak_bytes=int((root/'memory.peak').read_text()),
                memory_max=(root/'memory.max').read_text().strip(), host_mem_available_bytes=available,
                memory_events={key:int(value) for key,value in events.items()})


def main():
    require(Path('/.dockerenv').exists() and not Path('/reference').exists()
            and not Path('/artifacts/JointBuildGS').exists(), 'Isolated Docker without reference is required')
    output = Path('/probe')
    require(not (output/'invocation.json').exists() and not (output/'model').exists(), 'Probe must be fresh')
    schedule = helper('resource_schedule')
    extraction_lock, scheduling = schedule.acquire_extraction_lock('auxiliary')
    config_sha = sha('/config.json')
    config = json.loads(Path('/config.json').read_text())
    require(512 in config['extraction']['sensitivity_mesh_res'], '512 must be a preregistered sensitivity')
    input_sha = sha('/input/input_manifest.json')
    require(config_sha == 'b08bbcc808da060322fc1ed05902edbb08db2a0784dd146f4644adc12228eab4', 'Config changed')
    require(input_sha == '3257b3604f630a64948606605c3ae46f2e22d4d5829b5ad49a7d46b342a42112', 'P1 input manifest changed')
    require(sha('/runtime_layout.json') == '28b83d4a462d764cbe0d59b32f7a816db92236141879806a5a1bc8ce4e450cd5', 'Layout changed')
    manifest = json.loads(Path('/input/input_manifest.json').read_text())
    for row in manifest['files']:
        require(sha(Path('/input')/row['path']) == row['sha256'], 'Frozen input changed: '+row['path'])
    anchor = json.loads(Path('/anchor/receipt.json').read_text())
    anchor_sha = sha('/anchor/checkpoint.pth')
    ply_sha = sha('/anchor/point_cloud.ply')
    require(anchor_sha == anchor['checkpoint_sha256'] == 'c08a39aa2deb81b26dd4dd75d0be9e6bb5e150db503f9d422a05423388679274'
            and ply_sha == anchor['ply_sha256'] and anchor['iteration'] == 8000
            and anchor['after_protection_registration'] is True, 'Exact protected anchor differs')
    source = Path('/source')
    hashes = {str(path.relative_to(source)):sha(path) for path in sorted(source.rglob('*.py')) if 'submodules' not in path.parts}
    train = json.loads(Path('/final_train_receipt.json').read_text())
    require(train['status'] == 'PASS' and train['region'] == 'P1' and train['condition'] == 'D005_Pnative'
            and train['implementation_hashes'] == hashes and train['config_sha256'] == config_sha
            and train['input_manifest_sha256'] == input_sha, 'Source/input differs from completed native training')
    require(os.environ.get('PYTORCH_CUDA_ALLOC_CONF') == 'backend:native,max_split_size_mb:128', 'Allocator differs')
    effective = json.loads(subprocess.check_output(['python', '-c',
        'import json,torch;torch.cuda.init();print(json.dumps([torch.cuda.get_allocator_backend(),torch.cuda.memory_stats()["max_split_size"]]))'], text=True))
    require(effective == ['native', 134217728], 'Actual allocator differs')
    model = output/'model'
    copied = model/'point_cloud/iteration_8000/point_cloud.ply'
    copied.parent.mkdir(parents=True)
    shutil.copyfile('/anchor/point_cloud.ply', copied)
    shutil.copyfile('/final_cfg_args', model/'cfg_args')
    require(sha(copied) == ply_sha and sha(model/'cfg_args') == sha('/final_cfg_args'), 'Copied renderer inputs differ')
    before = memory()
    require(before['memory_max'] == str(32*1024**3), 'Actual cgroup memory cap must be32GiB')
    require(before['host_mem_available_bytes'] >= 40*1024**3, 'Host availability below32GiB+8GiB headroom')
    command = ['python', 'render.py', '-s', '/input/scene', '-m', '/probe/model', '--iteration', '8000', '--mesh_res', '512']
    started = time.time()
    invocation = dict(task_id='PHD-GEOGS-P1P2P3-v1', diagnostic='NONPRIMARY_OFFICIAL_ANCHOR512_MEMORY32_PROBE',
        region='P1', condition='D005_Pnative', iteration=8000, mesh_res=512, command=command,
        started_unix=started, scientific_verdict=None, reference_accessed=False, output_promoted=False,
        runtime_image_id=os.environ['JBGS_RUNTIME_IMAGE_ID'], config_sha256=config_sha,
        runtime_layout_sha256=sha('/runtime_layout.json'), input_manifest_sha256=input_sha,
        anchor_checkpoint_sha256=anchor_sha, source_complete_ply_sha256=ply_sha, copied_ply_sha256=sha(copied),
        render_cfg_args_sha256=sha(model/'cfg_args'), final_train_receipt_sha256=sha('/final_train_receipt.json'),
        source_hashes=hashes, driver_sha256=sha(__file__), resource_scheduling=scheduling,
        memory_before=before, configured_memory_limit_bytes=32*1024**3, minimum_host_headroom_bytes=8*1024**3,
        scientific_training_controls_changed=False, image_export_skipped=False,
        primary_result=False, extraction_mesh_resolution_changed_from_primary=True,
        sensitivity_resolution_pre_registered=True, concurrent_gpu0_training_allowed=True,
        environment={key:os.environ.get(key) for key in ('PYTORCH_CUDA_ALLOC_CONF','LD_PRELOAD','LD_LIBRARY_PATH','OMP_NUM_THREADS')})
    dump(output/'invocation.json', invocation)
    samples = []
    with (output/'render.log').open('x') as log, (output/'memory.jsonl').open('x') as memlog, (output/'gpu.csv').open('x') as gpu:
        child = subprocess.Popen(command, cwd='/source', stdout=log, stderr=subprocess.STDOUT)
        while True:
            sampled = memory()
            samples.append(sampled)
            memlog.write(json.dumps(sampled)+'\n')
            memlog.flush()
            subprocess.run(['nvidia-smi', '--query-gpu=timestamp,uuid,memory.used,utilization.gpu',
                            '--format=csv,noheader,nounits'], stdout=gpu, stderr=subprocess.DEVNULL, check=False)
            gpu.flush()
            if child.poll() is not None:
                break
            time.sleep(2)
        native_code = child.wait()
    wall_seconds = time.time()-started
    child_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024
    valid, outputs, realized, error = native_code == 0, [], None, None
    try:
        if valid:
            parser = helper('parse_extraction')
            realized = parser.parse_extraction_log(output/'render.log', 512, 50)
            import numpy as np
            import open3d as o3d
            for name in ('fuse.ply', 'fuse_post.ply'):
                path = model/'train/ours_8000'/name
                mesh = o3d.io.read_triangle_mesh(str(path))
                area = float(mesh.get_surface_area())
                valid_surface = bool(len(mesh.vertices) and len(mesh.triangles) and np.isfinite(np.asarray(mesh.vertices)).all() and area > 0)
                outputs.append(dict(path=str(path.relative_to(output)), bytes=path.stat().st_size, sha256=sha(path),
                                    vertices=len(mesh.vertices), triangles=len(mesh.triangles), surface_area_m2=area, valid_triangle_surface=valid_surface))
                valid = valid and valid_surface
                del mesh
            counts = {role:len(list((model/role/'ours_8000/renders').glob('*.png'))) for role in ('train','test')}
            valid = valid and counts == {'train':98,'test':15}
        else:
            counts = None
    except Exception as exception:
        error, valid = repr(exception), False
        counts = None
    after = memory()
    receipt = dict(invocation, status='PASS' if valid else 'FAIL', native_exit_code=native_code,
        validated_exit_code=0 if valid else (native_code or 95), wall_seconds=wall_seconds,
        child_peak_rss_bytes=child_rss, memory_after=after,
        sampled_min_host_mem_available_bytes=min(row['host_mem_available_bytes'] for row in samples),
        sampled_max_memory_current_bytes=max(row['memory_current_bytes'] for row in samples),
        cgroup_oom_kill_delta=after['memory_events'].get('oom_kill',0)-before['memory_events'].get('oom_kill',0),
        files=outputs, exported_images=counts, realized_extraction=realized, validation_error=error,
        finished_unix=time.time(), validation_wall_seconds=time.time()-started-wall_seconds)
    dump(output/'receipt.json', receipt)
    print(json.dumps({key:receipt[key] for key in ('status','native_exit_code','wall_seconds','child_peak_rss_bytes','cgroup_oom_kill_delta')}), flush=True)
    raise SystemExit(0 if valid else 1)


if __name__ == '__main__':
    main()

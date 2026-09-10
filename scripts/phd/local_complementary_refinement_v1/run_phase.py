"""Docker worker for the additive, same-Anchor local refinement experiment."""
import argparse
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import time

from common import read, record, require_docker, sha, write_new


def main():
    require_docker()
    parser = argparse.ArgumentParser()
    parser.add_argument('--region', choices=['P1', 'P2', 'P3'], required=True)
    parser.add_argument('--condition', required=True)
    parser.add_argument('--phase', choices=['probe', 'train', 'render', 'metrics'], required=True)
    args = parser.parse_args()
    cfg, binding = read('/config.json'), read('/binding.json')
    condition = next(c for c in cfg['conditions'] if c['id'] == args.condition)
    output, source, model = Path('/output'), Path('/source'), Path('/output/model')
    receipt_path = output/f'{args.phase}_receipt.json'
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    started = time.time()
    invocation = dict(task_id=cfg['task_id'], scientific_verdict=None, region=args.region,
                      condition=args.condition, phase=args.phase, started_unix=started,
                      config=record('/config.json'), input_binding=record('/binding.json'),
                      config_sha256=sha('/config.json'), iteration=30000,
                      driver=record(__file__), runtime_image_id=os.environ.get('JBGS_RUNTIME_IMAGE_ID'))
    code, native_code, validation = 1, None, []
    try:
        if binding['config']['sha256'] != sha('/config.json'):
            raise ValueError('Input binding and configuration differ')
        if invocation['runtime_image_id'] != cfg['runtime']['image_id']:
            raise ValueError('Runtime image differs')
        if os.environ.get('PYTORCH_CUDA_ALLOC_CONF') != cfg['runtime']['allocator']:
            raise ValueError('Allocator policy differs')
        if any(p.exists() for p in [Path('/reference'), Path('/references'), Path('/parent'), Path('/artifacts/JointBuildGS')]):
            raise ValueError('Broad parent/reference mounts are prohibited in model containers')
        sealed = read('/input/input_manifest.json')
        if sha('/input/input_manifest.json') != binding['regions'][args.region]['manifest']['sha256']:
            raise ValueError('Region input seal differs')
        for item in sealed['files']:
            if sha(Path('/input')/item['path']) != item['sha256']:
                raise ValueError('Sealed input changed: '+item['path'])
        provenance = read(source/'local_source_provenance.json')
        actual_hashes = {str(p.relative_to(source)):sha(p) for p in sorted(source.rglob('*.py'))
                         if 'submodules' not in p.parts and '__pycache__' not in p.parts}
        if actual_hashes != provenance['prepared_implementation_hashes']:
            raise ValueError('Prepared source changed')
        invocation.update(source_provenance=record(source/'local_source_provenance.json'),
                          implementation_hashes=actual_hashes,
                          input_manifest_sha256=sha('/input/input_manifest.json'),
                          expected_test_count=sum(i['role']=='evaluation' for i in sealed['images']),
                          parent_condition=condition['parent_condition'],
                          local_mode='complementary', tau0_m=binding['tau0_m'], tau1_m=binding['tau1_m'])
        os.environ.update(JBGS_LOCAL_DEPTH_MODE='complementary', JBGS_LOCAL_TAU0=str(binding['tau0_m']),
                          JBGS_LOCAL_TAU1=str(binding['tau1_m']))
        if args.phase in ['probe','train']:
            if model.exists():
                raise FileExistsError(model)
            anchor = record('/anchor/checkpoint.pth')
            if anchor['sha256'] != binding['regions'][args.region]['checkpoint']['sha256']:
                raise ValueError('Complete Anchor8k changed')
            parent_invocation = read('/parent_invocation.json')
            if parent_invocation['region'] != args.region or parent_invocation['condition'] != condition['parent_condition']:
                raise ValueError('Parent command belongs to a different condition')
            # Same native flags; all changed controls are explicit in the new contract.
            paths = sealed['training_paths']
            command = ['python','train.py','-s','/input/scene','-m',str(model),
                       '--lod_depth_path','/input/'+paths['prior_depth'],
                       '--da_depth_path','/input/'+paths['da3_depth'],
                       '--lod2_pcd_path','/input/'+paths['protection_pcd'],
                       '--eval','--lod_init','--freeze_onlybldg','--protect_bldg','--dynamic_depth_weight',
                       '-r','1','--port','0','--iterations','30000','--stage_switch_iter','8000',
                       '--lambda_lod_init','0.08','--lambda_lod_anchor',str(condition['lambda_p']),
                       '--jbgs_capture_iterations','8001','30000',
                       '--jbgs_input_manifest','/input/input_manifest.json',
                       '--jbgs_resume_full','/anchor/checkpoint.pth']
            if condition['protection'] == 'release':
                command += ['--jbgs_release_protection','--lod2_building_xyz_lr_scale','1','--protect_bldg_lr_scale','1']
            if args.phase == 'probe':
                command += ['--jbgs_stop_after','8001']
            invocation.update(anchor=anchor, parent_invocation=record('/parent_invocation.json'),
                              training_start_iteration=8000, training_end_iteration=8001 if args.phase=='probe' else 30000,
                              prior_initialization_and_anchor_retained=True, image_only=False)
        elif args.phase == 'render':
            if read(output/'train_receipt.json')['status'] != 'PASS':
                raise ValueError('Completed training is required')
            command = ['python','render.py','-s','/input/scene','-m',str(model),'--iteration','30000','--mesh_res','512']
            invocation.update(mesh_res=512, render_source_ply=record(model/'point_cloud/iteration_30000/point_cloud.ply'))
        else:
            if read(output/'render_receipt.json')['status'] != 'PASS':
                raise ValueError('Completed rendering is required')
            command = ['python','metrics.py','-m',str(model)]
        invocation['command'] = command
        invocation['environment'] = {k:os.environ.get(k) for k in ['JBGS_LOCAL_DEPTH_MODE','JBGS_LOCAL_TAU0','JBGS_LOCAL_TAU1','PYTORCH_CUDA_ALLOC_CONF','OMP_NUM_THREADS','TORCH_HOME','LD_PRELOAD']}
        write_new(output/f'{args.phase}_invocation.json', invocation)
        (output/f'{args.phase}_driver_snapshot.py').write_bytes(Path(__file__).read_bytes())
        with (output/f'{args.phase}.log').open('x') as log, (output/f'{args.phase}_gpu.csv').open('x') as gpu:
            child = subprocess.Popen(command, cwd=source, stdout=log, stderr=subprocess.STDOUT)
            while child.poll() is None:
                subprocess.run(['nvidia-smi','--query-gpu=timestamp,uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits'],
                               stdout=gpu, stderr=subprocess.DEVNULL)
                gpu.flush()
                time.sleep(5)
            native_code = child.wait()
        if native_code:
            raise RuntimeError('Native process failed with code '+str(native_code))
        required = []
        if args.phase in ['train','probe']:
            end = invocation['training_end_iteration']
            restore = read(model/'jbgs_restore.json')
            if restore['iteration'] != 8000 or restore['checkpoint_sha256'] != invocation['anchor']['sha256'] or restore['release'] != (condition['protection']=='release'):
                raise ValueError('Restored state identity or protection differs')
            trace = [json.loads(line) for line in (model/'local_trace.jsonl').read_text().splitlines()]
            if trace[0]['iteration'] != 8001 or trace[-1]['iteration'] != end:
                raise ValueError('Local objective trace does not span expected steps')
            for row in trace:
                if row['tau0'] != binding['tau0_m'] or row['tau1'] != binding['tau1_m'] or row['lambda_prior'] != condition['lambda_p']:
                    raise ValueError('Realized local weights differ')
                for kind in ['prior','visual']:
                    raw, weighted = row['raw_'+kind+'_loss'], row['weighted_'+kind+'_loss']
                    if not math.isfinite(weighted) or weighted < -1e-7 or weighted > raw+max(1e-5,abs(raw)*1e-5):
                        raise ValueError('Local attenuation is not finite/bounded')
            required = [model/f'jbgs_complete/iteration_{end}/checkpoint.pth', model/f'jbgs_complete/iteration_{end}/point_cloud.ply']
            if args.phase == 'train':
                required.append(model/'point_cloud/iteration_30000/point_cloud.ply')
            validation += [{'restore':restore, 'local_trace_rows':len(trace), 'first_local_trace':trace[0], 'last_local_trace':trace[-1]}]
        elif args.phase == 'render':
            import numpy as np
            import open3d as o3d
            required = [model/'train/ours_30000/fuse.ply', model/'train/ours_30000/fuse_post.ply']
            for path in required:
                mesh = o3d.io.read_triangle_mesh(str(path))
                if not len(mesh.triangles) or not np.isfinite(np.asarray(mesh.vertices)).all() or mesh.get_surface_area()<=0:
                    raise ValueError('Invalid extracted surface')
                validation.append(dict(path=str(path.relative_to(output)), vertices=len(mesh.vertices),triangles=len(mesh.triangles),surface_area_m2=mesh.get_surface_area()))
            count = len(list((model/'test/ours_30000/renders').glob('*.png')))
            if count != invocation['expected_test_count']:
                raise ValueError('Evaluation image count differs')
        else:
            required = [model/'results.json', model/'per_view.json']
            values, per = read(required[0])['ours_30000'], read(required[1])['ours_30000']
            if not all(math.isfinite(values[k]) and len(per[k])==invocation['expected_test_count'] for k in ['PSNR','SSIM','LPIPS']):
                raise ValueError('Incomplete or invalid appearance metrics')
            validation.append(dict(metrics=values, native_lpips_backbone='vgg',native_lpips_range='[0,1]'))
        for path in required:
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError('Required output missing: '+str(path))
            validation.append(record(path))
        invocation['outputs'] = [dict(record(path), path=str(path.relative_to(output))) for path in required]
        code = 0
    except Exception as error:
        validation.append({'exception_type':type(error).__name__, 'exception':str(error)})
    result = dict(invocation, status='PASS' if code==0 else 'FAIL', native_exit_code=native_code,
                  validated_exit_code=code, finished_unix=time.time(), wall_seconds=time.time()-started,
                  child_peak_rss_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024, validation=validation)
    write_new(receipt_path,result)
    print(json.dumps({k:result[k] for k in ['region','condition','phase','status','wall_seconds','validation']},allow_nan=False),flush=True)
    raise SystemExit(code)


if __name__=='__main__':
    main()

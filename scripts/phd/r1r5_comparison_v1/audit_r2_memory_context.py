"""Read existing R2 failure traces; infer next camera without rerunning training."""
import hashlib
import json
from pathlib import Path

import numpy as np


cfg = json.loads(Path('/config.json').read_text())
root = Path(cfg['root'])
inputs = {}


def read_text(path):
    data = path.read_bytes()
    inputs[str(path.relative_to(root))] = hashlib.sha256(data).hexdigest()
    return data.decode()


def read_json(path):
    return json.loads(read_text(path))


def sampling(folder):
    rows = [json.loads(line) for line in read_text(folder / 'camera_sampling.jsonl').splitlines()]
    assert [r['iteration'] for r in rows] == list(range(8001, rows[-1]['iteration'] + 1))
    return rows


baseline = sampling(root / 'R2/mvs')
by_iteration = {r['iteration']: r for r in baseline}
failures = []
for name in cfg['failed_outputs']:
    folder = root / 'R2' / name
    rows = sampling(folder)
    assert all(r['camera'] == by_iteration[r['iteration']]['camera'] for r in rows)
    progress = read_json(folder / 'progress.json')
    assert read_json(folder / 'receipt.json')['status'] == 'FAIL'
    log = read_text(folder / 'process.log')
    assert 'torch.cuda.OutOfMemoryError' in log
    following = by_iteration[rows[-1]['iteration'] + 1]
    model_checkpoints = sorted(str(p.relative_to(folder)) for p in (folder / 'model').rglob('*')
                               if p.suffix in ('.ply', '.pth') and p.name != 'input.ply')
    failures.append(dict(output=name, successful_logged_iterations=len(rows),
                         last_logged_iteration=rows[-1]['iteration'],
                         inferred_next_iteration=following['iteration'],
                         inferred_next_camera=following['camera'],
                         direct_failed_camera_log=False,
                         all_logged_cameras_match_control=True,
                         last_progress=progress, failed_refinement_checkpoints=model_checkpoints,
                         oom_excerpt=log[log.rfind('torch.cuda.OutOfMemoryError'):].split('Training progress:')[0].strip()))

candidate_cameras = {r['inferred_next_camera'] for r in failures}
assert len(candidate_cameras) == 1
candidate_camera = next(iter(candidate_cameras))
regions = []
for region in ['R2', 'R3', 'R4', 'R5']:
    folder = root / region / 'preparation'
    metadata = read_json(folder / 'region.json')
    config = read_json(folder / 'preparation_config.json')
    split = read_json(folder / 'input/scene/split_manifest.json')
    train = split['train']
    centers = np.array([-np.array(v['R']).T @ np.array(v['t']) for v in train])
    extent = float(1.1 * np.linalg.norm(centers - centers.mean(0), axis=1).max())
    assert np.isclose(extent, metadata['camera_radius_m'])
    region_box = metadata['region']
    regions.append(dict(region=region, train_views=len(train),
                        uv_size_m=[region_box['u_m'][1] - region_box['u_m'][0],
                                   region_box['v_m'][1] - region_box['v_m'][0]],
                        context_buffer_uv_m=metadata['context_buffer_uv_m'],
                        image_dimensions=sorted(set((v['width'], v['height']) for v in train)),
                        regional_loss_mask=config['baseline']['regional_loss_mask'],
                        rgb_loss_domain=config['baseline']['rgb_loss_domain'],
                        camera_radius_m=extent, clone_split_boundary_m=extent * metadata['percent_dense']))
    if region == 'R2':
        suspect = next(v for v in train if Path(v['name']).stem == candidate_camera)
        image = folder / 'input/scene/images' / suspect['name']
        image_hash = hashlib.sha256(image.read_bytes()).hexdigest()
        assert image_hash == suspect['sha256']

binding = read_json(root / 'R2' / cfg['failed_outputs'][-1] / 'local_mask_binding.json')
result = dict(status='PASS_READONLY_MEMORY_CONTEXT_AUDIT', scientific_verdict=None,
              failures=failures, regions=regions, common_inferred_camera=candidate_camera,
              common_camera_local_prior_zero_pixels=binding['counts'][candidate_camera],
              common_camera=suspect, image_sha256=image_hash,
              mvs_control_peak_allocated_gib=read_json(root / 'R2/mvs/progress.json')['peak_cuda_allocated_bytes'] / 1024**3,
              input_sha256=inputs, script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              config_sha256=hashlib.sha256(Path('/config.json').read_bytes()).hexdigest(),
              new_training_steps=0,
              limitation='Failed camera inferred from identical contiguous completed camera prefixes and control next draw; not directly instrumented at failed render. Failed Gaussian states and per-view tile counts were not saved; exact primitive cause remains unmeasured.')
Path('/out/receipt.json').write_text(json.dumps(result, indent=2))
print(json.dumps({k:result[k] for k in ['status', 'common_inferred_camera', 'common_camera_local_prior_zero_pixels', 'regions', 'mvs_control_peak_allocated_gib']}))

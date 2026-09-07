"""Complete-state instrumentation for the pinned GeoGS diagnostic.

The upstream model, optimizer, renderer and losses are unchanged. Only explicit
resume state and the declared refinement protection release are added.
"""
import hashlib
import json
import random
import resource
import time
from pathlib import Path

import numpy as np
import torch

SCHEMA = 'JBGS_GEOGS_COMPLETE_STATE_v1'
STARTED = time.monotonic()
RUNTIME_KEYS = (
    'ema_loss_for_log', 'ema_dist_for_log', 'ema_normal_for_log', 'ema_lod_loss', 'ema_da_loss',
    'freeze_done', 'dynamic_switch_triggered', 'dynamic_switch_iter', 'dynamic_switch_forced',
    'lod_loss_history', 'last_dynamic_check', 'da_phase', 'da_weight', 'da_depth_history',
    'da_monitor_depth', 'da_monitor_rgb', 'da_last_check', 'da_consecutive', 'da_locked_weight',
)
NON_METHOD_ARGS = {'model_path', 'quiet', 'ip', 'port', 'checkpoint_iterations', 'start_checkpoint',
                   'save_iterations'}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def register_args(parser):
    parser.add_argument('--jbgs_resume_full')
    parser.add_argument('--jbgs_capture_iterations', type=int, nargs='+', default=[8000, 30000])
    parser.add_argument('--jbgs_stop_after', type=int, default=0)
    parser.add_argument('--jbgs_release_protection', action='store_true')
    parser.add_argument('--jbgs_input_manifest')


def validate_args(args):
    if args.start_checkpoint:
        raise ValueError('Use a complete state; upstream checkpoint omits required state')
    if args.jbgs_release_protection and not args.jbgs_resume_full:
        raise ValueError('Protection release is restricted to a saved refinement anchor')
    if args.dynamic_stage_switch or args.enable_gaussian_completion:
        raise ValueError('This frozen diagnostic supports fixed stages and completion disabled')


def cpu_clone(value):
    return None if value is None else value.detach().cpu().clone()


def camera_names(cameras):
    names = [c.image_name for c in cameras]
    if len(names) != len(set(names)):
        raise ValueError('Duplicate image stem in camera identity')
    return names


def implementation_hashes():
    root = Path(__file__).parent
    return {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob('*.py'))
            if 'submodules' not in p.parts and '__pycache__' not in p.parts}


def capture_state(env):
    g, scene, args = env['gaussians'], env['scene'], env['args']
    torch.cuda.synchronize()
    return {
        'schema': SCHEMA, 'iteration': env['iteration'], 'scientific_verdict': None,
        'model': g.capture(), 'frozen_mask': cpu_clone(g.frozen_mask),
        'completed_mask': cpu_clone(g.completed_mask),
        'building_freeze_mask': cpu_clone(env['building_freeze_mask']),
        'runtime': {k: env[k] for k in RUNTIME_KEYS},
        'train_order': camera_names(scene.getTrainCameras()),
        'test_order': camera_names(scene.getTestCameras()),
        'viewpoint_stack': None if env['viewpoint_stack'] is None else camera_names(env['viewpoint_stack']),
        'rng': {'python': random.getstate(), 'numpy': np.random.get_state(),
                'torch_cpu': torch.get_rng_state(), 'torch_cuda': torch.cuda.get_rng_state_all()},
        'args': vars(args).copy(), 'optimization': vars(env['opt']).copy(),
        'input_manifest_sha256': digest(args.jbgs_input_manifest) if args.jbgs_input_manifest else None,
        'hook_state': {'xyz': args.lod2_building_xyz_lr_scale,
                       'rotation_scale': args.protect_bldg_lr_scale,
                       'protect_bldg': args.protect_bldg,
                       'release': args.jbgs_release_protection},
        'source_sha256': digest(Path(__file__).with_name('train.py')),
        'implementation_hashes': implementation_hashes(),
    }


def restore_state(path, env, functions):
    state = torch.load(path)
    if state.get('schema') != SCHEMA:
        raise ValueError('Unrecognized or incomplete checkpoint')
    args, g, scene = env['args'], env['gaussians'], env['scene']
    if state['source_sha256'] != digest(Path(__file__).with_name('train.py')):
        raise ValueError('Instrumented training source changed')
    if state['implementation_hashes'] != implementation_hashes():
        raise ValueError('An instrumented implementation file changed')
    if state['optimization'] != vars(env['opt']):
        raise ValueError('Optimization settings differ from the complete state')
    if state['iteration'] != args.stage_switch_iter:
        raise ValueError('Experimental branching is restricted to the frozen anchor boundary')
    if state['hook_state']['release']:
        raise ValueError('Branch input must be the native protected anchor')
    allowed = NON_METHOD_ARGS | {'lambda_lod_anchor', 'lod2_building_xyz_lr_scale', 'protect_bldg_lr_scale'}
    differences = {}
    for key, old in state['args'].items():
        if key.startswith('jbgs_') or key in allowed:
            continue
        if getattr(args, key) != old:
            differences[key] = [old, getattr(args, key)]
    if differences:
        raise ValueError(f'Unplanned settings changed: {differences}')
    current_input = digest(args.jbgs_input_manifest) if args.jbgs_input_manifest else None
    if current_input != state['input_manifest_sha256']:
        raise ValueError('Scene input manifest changed')
    g.restore(state['model'], env['opt'])
    g.frozen_mask = None if state['frozen_mask'] is None else state['frozen_mask'].to(g._xyz.device)
    g.completed_mask = None if state['completed_mask'] is None else state['completed_mask'].to(g._xyz.device)
    building = state['building_freeze_mask']
    building = None if building is None else building.to(g._xyz.device)
    if building is None or g.frozen_mask is None:
        raise ValueError('Anchor must contain actual protection state')
    if g.completed_mask is not None and g.completed_mask.any():
        raise ValueError('Completion was disabled in the frozen experiment')
    out = dict(state['runtime'], first_iter=state['iteration'], building_freeze_mask=building)
    for role, cameras in [('train', scene.getTrainCameras()), ('test', scene.getTestCameras())]:
        by_name = {c.image_name: c for c in cameras}
        if set(by_name) != set(state[role + '_order']):
            raise ValueError(f'{role} camera membership changed')
        cameras[:] = [by_name[n] for n in state[role + '_order']]
    by_name = {c.image_name: c for c in scene.getTrainCameras()}
    stack = state['viewpoint_stack']
    out['viewpoint_stack'] = None if stack is None else [by_name[n] for n in stack]
    if args.jbgs_release_protection:
        if args.lod2_building_xyz_lr_scale != 1.0 or args.protect_bldg_lr_scale != 1.0:
            raise ValueError('Released condition requires all gradient factors equal to one')
        # Keep global densification active. Setting freeze_onlybldg=False would
        # instead stop all densification in upstream and is intentionally avoided.
        g.set_frozen_mask(None)
        out['building_freeze_mask'] = None
        out['freeze_done'] = False
    else:
        if args.lod2_building_xyz_lr_scale != state['hook_state']['xyz'] or args.protect_bldg_lr_scale != state['hook_state']['rotation_scale']:
            raise ValueError('Native protection condition changed its gradient factors')
        functions['attenuate_building_xyz_lr'](g, g.frozen_mask, args.lod2_building_xyz_lr_scale)
        if args.protect_bldg:
            functions['attenuate_building_other_lr'](g, g.frozen_mask, args.protect_bldg_lr_scale)
    # Restore only after all initialization and hook registration. No random draw
    # may intervene before upstream resumes its camera and densification schedule.
    random.setstate(state['rng']['python'])
    np.random.set_state(state['rng']['numpy'])
    torch.set_rng_state(state['rng']['torch_cpu'].cpu())
    torch.cuda.set_rng_state_all([x.cpu() for x in state['rng']['torch_cuda']])
    receipt = {'schema': SCHEMA, 'checkpoint': str(path), 'checkpoint_sha256': digest(path),
               'iteration': state['iteration'], 'release': args.jbgs_release_protection,
               'lambda_lod_anchor': args.lambda_lod_anchor, 'scientific_verdict': None}
    with (Path(args.model_path) / 'jbgs_restore.json').open('x') as f:
        json.dump(receipt, f, indent=2)
    return out


def after_step(env):
    iteration, args, g = env['iteration'], env['args'], env['gaussians']
    if iteration % 100 == 0 or iteration in args.jbgs_capture_iterations:
        row = {'iteration': iteration, 'camera': env['cam_name'], 'rgb_loss': env['rgb_loss'].item(),
               'lod_loss': env['lod_depth_loss'].item(), 'da_loss': env['da_depth_loss'].item(),
               'lod_weight': env['current_lod_weight'], 'da_weight': env['current_da_weight'],
               'gaussians': len(g.get_xyz),
               'protected': int(g.frozen_mask.sum()) if g.frozen_mask is not None else 0,
               'elapsed_seconds': time.monotonic() - STARTED,
               'peak_cuda_allocated_bytes': torch.cuda.max_memory_allocated(),
               'peak_cuda_reserved_bytes': torch.cuda.max_memory_reserved(),
               'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}
        with (Path(args.model_path) / 'jbgs_trace.jsonl').open('a') as f:
            f.write(json.dumps(row, allow_nan=False) + '\n')
    if iteration in args.jbgs_capture_iterations:
        root = Path(args.model_path) / 'jbgs_complete' / f'iteration_{iteration}'
        root.mkdir(parents=True, exist_ok=False)
        state = capture_state(env)
        torch.save(state, root / 'checkpoint.pth')
        g.save_ply(str(root / 'point_cloud.ply'))
        receipt = {'schema': SCHEMA, 'iteration': iteration, 'after_protection_registration': True,
                   'gaussians': len(g.get_xyz), 'scientific_verdict': None,
                   'checkpoint_sha256': digest(root / 'checkpoint.pth'),
                   'ply_sha256': digest(root / 'point_cloud.ply')}
        with (root / 'receipt.json').open('x') as f:
            json.dump(receipt, f, indent=2)
        print(f'[JBGS] Complete state captured after iteration {iteration}')
    return bool(args.jbgs_stop_after and iteration >= args.jbgs_stop_after)

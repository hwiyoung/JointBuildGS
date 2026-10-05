"""Read-only final-state objective gradients; called before the SH color probe.

This compares full-frame raw objective derivatives on a PLY-loaded model. It
does not reconstruct protection hooks, Adam moments, or historical updates.
"""
import ast
import json
from pathlib import Path

import cv2
import numpy as np
import torch

import rgb_radius_probe as p
from jbgs_mvs_pgsr_depth import read_colmap_depth, resample_depth_to_camera


def _native_function(source, name):
    tree = ast.parse(source.read_text())
    selected = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(selected) != 1:
        raise ValueError('Missing unique native function: ' + name)
    namespace = {'torch': torch}
    code = ast.Module(body=selected, type_ignores=[])
    exec(compile(code, str(source), 'exec'), namespace)
    return namespace[name]


def _default(source, name):
    values = []
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (isinstance(target, ast.Attribute) and target.attr == name
                        and isinstance(target.value, ast.Name)
                        and target.value.id == 'self'):
                    values.append(ast.literal_eval(node.value))
    if len(values) != 1:
        raise ValueError('Missing unique native default: ' + name)
    return values[0]


def _last_trace(model):
    path = model / 'jbgs_trace.jsonl'
    row = None
    with path.open() as stream:
        for line in stream:
            if line.strip():
                row = json.loads(line)
    if row is None or row['iteration'] != 30000:
        raise ValueError('Expected actual final 30000-step trace: ' + str(path))
    return path, row


def _training_model(staged, mode, region):
    if (staged / 'jbgs_trace.jsonl').exists():
        return staged, {'staged_model': str(staged), 'training_model': str(staged),
                        'resolution': 'already_original_training_model'}
    if mode != 'mvs':
        raise ValueError('Missing original training trace: ' + str(staged))
    receipt_path = staged.parent / 'receipt.json'
    receipt = p.read(receipt_path)
    job = receipt['job']
    if receipt['status'] != 'PASS' or (job['mode'], job['region']) != (mode, region):
        raise ValueError('Unexpected extraction lineage: ' + str(receipt_path))
    relative = Path(job['training_relative'])
    if relative.is_absolute() or '..' in relative.parts or relative.parts[0] != 'train':
        raise ValueError('Unexpected training-relative path')
    original = p.TASK / relative / 'model'
    checked = {}
    for suffix in ('cfg_args', 'point_cloud/iteration_30000/point_cloud.ply'):
        relpath = str(relative / 'model' / suffix)
        expected = next(row['sha256'] for row in job['files'] if row['path'] == relpath)
        if p.sha(original / suffix) != expected or p.sha(staged / suffix) != expected:
            raise ValueError('Staged/original model hash mismatch: ' + suffix)
        checked[suffix] = expected
    return original, {'staged_model': str(staged), 'training_model': str(original),
                      'resolution': 'extraction_receipt_job_training_relative',
                      'extraction_receipt': str(receipt_path),
                      'extraction_receipt_sha256': p.sha(receipt_path),
                      'identical_staged_original_sha256': checked}


def _stored_target(root, manifest, relative, width, height, device):
    path = root / relative
    expected = next(row['sha256'] for row in manifest['files'] if row['path'] == relative)
    if p.sha(path) != expected:
        raise ValueError('Depth target hash mismatch: ' + str(path))
    # The train-time load_depth_set uses LINEAR; any earlier DA3 preprocessing
    # interpolation is already represented by these immutable stored arrays.
    native = np.load(path)
    depth = cv2.resize(native, (width, height), interpolation=cv2.INTER_LINEAR)
    return torch.tensor(depth, dtype=torch.float32, device=device), {
        'path': str(path), 'sha256': expected,
        'loader_interpolation': 'cv2.INTER_LINEAR',
    }


def _pair(a, b):
    if a is None or b is None:
        return {'present': False}
    if not torch.isfinite(a).all() or not torch.isfinite(b).all():
        raise FloatingPointError('Nonfinite objective gradient')
    dot = float((a * b).sum(dtype=torch.float64))
    na = float(torch.linalg.vector_norm(a))
    nb = float(torch.linalg.vector_norm(b))
    return {'present': True, 'rgb_l2_norm': na, 'component_l2_norm': nb,
            'dot': dot, 'cosine': dot / (na * nb) if na and nb else None,
            'component_to_rgb_norm_ratio': nb / na if na else None}


@torch.enable_grad()
def analyze(pc, camera, pipe, bg, case, condition, model=None):
    """Return JSON-serializable full-frame derivatives without changing values.

    ``model`` is the staged or original directory containing cfg_args. By
    default it is recovered from condition['cfg_args']['path']; extraction
    receipts resolve the original training trace after exact model checks.
    """
    model = Path(model) if model is not None else Path(condition['cfg_args']['path']).parent
    mode = condition.get('mode', condition['id'].rsplit('_', 1)[0])
    if mode not in ('mvs', 'da3'):
        raise ValueError('This bounded gradient probe supports MVS-only and DA3 only')
    region = case.get('region', case['id'].split('_')[0])
    model, model_resolution = _training_model(model, mode, region)
    root = p.BASE / 'inputs' / region
    manifest_path = root / 'input_manifest.json'
    manifest = p.read(manifest_path)
    source = p.SOURCE if mode == 'mvs' else p.BASE / 'sources/GeoGS-state-camera-v1'
    train_source = source / 'train.py'
    args_source = source / 'arguments/__init__.py'
    depth_loss = _native_function(train_source, 'compute_depth_loss')
    normal_weight = float(_default(args_source, 'lambda_normal'))
    dssim_weight = float(_default(args_source, 'lambda_dssim'))
    trace_path, trace = _last_trace(model)
    weights = {'prior': float(trace['lod_weight']),
               'visual': float(trace['da_weight']), 'normal': normal_weight}
    values = p.cfg_args(model / 'cfg_args')
    if values.get('da_conf_path'):
        raise ValueError('Confidence-weighted runs are outside the bounded probe')
    h, w = camera.image_height, camera.image_width
    name = camera.image_name
    device = pc._xyz.device
    targets, target_meta = {}, {}
    targets['prior'], target_meta['prior'] = _stored_target(
        root, manifest, f"{manifest['training_paths']['prior_depth']}/raw_depth/{name}.npy", w, h, device)
    if mode == 'da3':
        targets['visual'], target_meta['visual'] = _stored_target(
            root, manifest, f"{manifest['training_paths']['da3_depth']}/raw_depth/{name}.npy", w, h, device)
    else:
        binding_path = p.TASK / 'inputs_v2' / region / 'bindings.json'
        binding = p.read(binding_path)
        if p.sha(manifest_path) != binding['parent_input_manifest_sha256']:
            raise ValueError('MVS parent manifest mismatch')
        view = next(row for row in binding['train'] if Path(row['name']).stem == name)
        for key in ('K', 'R', 't'):
            np.testing.assert_allclose(view[key], case[key], rtol=0, atol=1e-9)
        if (view['width'], view['height']) != (w, h):
            raise ValueError('MVS target dimensions mismatch')
        metadata = view['maps']['depth']
        native_path = binding_path.parent / view['local_depth']
        native = read_colmap_depth(native_path, metadata)
        depth, _ = resample_depth_to_camera(native, metadata['K'], view['K'], w, h)
        targets['visual'] = torch.tensor(depth, dtype=torch.float32, device=device)
        target_meta['visual'] = {'path': str(native_path), 'sha256': metadata['sha256'],
                                 'binding_path': str(binding_path), 'binding_sha256': p.sha(binding_path),
                                 'loader': 'native read_colmap_depth + resample_depth_to_camera'}

    names = ('xyz', 'scaling', 'rotation', 'opacity')
    params = tuple(getattr(pc, '_' + name) for name in names)
    flags = tuple(param.requires_grad for param in params)
    for param in params:
        if getattr(param, '_backward_hooks', None):
            raise ValueError('Raw derivative probe requires no parameter protection hooks')
        param.requires_grad_(True)
    try:
        pkg = p.render(camera, pc, pipe, bg)
        gt = camera.original_image.to(device)
        rgb = ((1 - dssim_weight) * (pkg['render'] - gt).abs().mean()
               + dssim_weight * (1 - p.ssim(pkg['render'], gt)))
        components = {key: depth_loss(pkg['surf_depth'], target,
                                     conf_map=None, mask=None, use_scale_invariant=False)
                      for key, target in targets.items()}
        components['normal'] = (1 - (pkg['rend_normal'] * pkg['surf_normal']).sum(dim=0)).mean()
        rgb_grads = torch.autograd.grad(rgb, params, retain_graph=True, allow_unused=True)
        rows = {}
        for key, loss in components.items():
            grads = torch.autograd.grad(loss, params, retain_graph=True, allow_unused=True)
            raw = {name: _pair(a, b) for name, a, b in zip(names, rgb_grads, grads)}
            weighted = {name: _pair(a, None if b is None else weights[key] * b)
                        for name, a, b in zip(names, rgb_grads, grads)}
            rows[key] = {'loss_unweighted': float(loss.detach()), 'weight': weights[key],
                         'loss_weighted': float(loss.detach()) * weights[key],
                         'raw_component_vs_rgb': raw, 'weighted_component_vs_rgb': weighted}
            del grads
        result = {'status': 'PASS_RAW_FINAL_OBJECTIVE_GRADIENTS', 'scientific_verdict': None,
                  'case_id': case['id'], 'condition_id': condition['id'], 'camera': name,
                  'frame_scope': 'full frame, matching native training loss support',
                  'rgb_loss': float(rgb.detach()), 'rgb_dssim_weight': dssim_weight,
                  'components': rows, 'target_provenance': target_meta,
                  'model_resolution': model_resolution,
                  'final_trace': {'path': str(trace_path), 'sha256': p.sha(trace_path), 'row': trace},
                  'source_sha256': {str(path): p.sha(path) for path in (train_source, args_source)},
                  'parameterization': 'raw xyz, log scaling, unnormalized quaternion rotation, logit opacity',
                  'interpretation': 'Negative dot means component-only infinitesimal Euclidean descent would increase full-frame RGB loss at this final state. This is not the actual protected Adam update, not a training-history cause, and not evidence specific to the ROI. Norms across different parameter groups are not comparable. Last recorded dynamic weights are used; no controller update is simulated.',
                  'optimizer_steps': 0, 'parameter_values_changed': False,
                  'protection_hooks_applied': False, 'adam_preconditioning_applied': False}
        return result
    finally:
        for param, flag in zip(params, flags):
            param.requires_grad_(flag)

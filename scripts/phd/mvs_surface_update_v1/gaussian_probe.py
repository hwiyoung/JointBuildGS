"""Bounded checkpoint-derived GeoGS intervention and paired observation audit.

This is an inference intervention, not training or an optimizer resume. The native
renderer/camera adapter is imported from an exact checkpoint-bound source. A sparse
XYZ patch is sufficient to reproduce the derived state from the immutable anchor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import sys
import time
import traceback
from types import SimpleNamespace

import numpy as np
from PIL import Image


FIELDS = ('_xyz', '_features_dc', '_features_rest', '_scaling', '_rotation', '_opacity')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def clean(x):
    if isinstance(x, dict): return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [clean(v) for v in x]
    if isinstance(x, np.ndarray): return clean(x.tolist())
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (np.bool_,)): return bool(x)
    if isinstance(x, (np.floating, float)): return float(x) if np.isfinite(x) else None
    return x


def write(path, obj):
    with Path(path).open('x') as stream:
        json.dump(clean(obj), stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def ray_world(camera, uv, depth):
    ray = np.linalg.inv(np.asarray(camera['K'])) @ np.r_[uv, 1.]
    return np.asarray(camera['R']).T @ (ray * depth - np.asarray(camera['t']))


def project(camera, xyz):
    points = np.asarray(xyz) @ np.asarray(camera['R']).T + np.asarray(camera['t'])
    ph = points @ np.asarray(camera['K']).T
    with np.errstate(divide='ignore', invalid='ignore'):
        return ph[..., :2] / ph[..., 2:3], points[..., 2]


def bounded_plane_displacement(xyz, point, normal, maximum):
    xyz, point, normal = np.asarray(xyz), np.asarray(point), np.asarray(normal)
    if (xyz.ndim != 2 or xyz.shape[1] != 3 or point.shape != (3,) or normal.shape != (3,)
            or not all(np.isfinite(a).all() for a in (xyz, point, normal))
            or not np.isfinite(maximum) or maximum <= 0 or np.linalg.norm(normal) < 1e-8):
        raise ValueError('Finite XYZ, plane point/normal and positive bound required')
    normal = normal / np.linalg.norm(normal)
    distance = (point - xyz) @ normal
    return np.clip(distance, -maximum, maximum)[:, None] * normal, distance


def frozen_masks(camera, case, reference=False, ring_radius=31):
    """Fixed image masks; other-view support unions both source hypotheses.

    A projected quadrilateral is only a measurement window, not known visibility.
    It is frozen before the intervention and independent of after residual/alpha.
    """
    from PIL import ImageDraw
    width, height = int(camera['width']), int(camera['height'])
    target = np.zeros((height, width), bool)
    if reference:
        x0, y0, x1, y1 = case['bbox']
        target[max(0, y0):min(height, y1), max(0, x0):min(width, x1)] = True
        center = np.asarray(case['uv'], float)
    else:
        ref = case['reference_camera']; x0, y0, x1, y1 = case['bbox']
        # Corners follow pixel-center footprint edges. Both source depths are
        # used for both arms, so moving geometry cannot choose its scoring window.
        corners = [[x0-.5, y0-.5], [x1-.5, y0-.5], [x1-.5, y1-.5], [x0-.5, y1-.5]]
        for source in ('prior', 'mvs'):
            raw = case.get(source+'_patch_world')
            xyz = (np.asarray(raw, dtype=float).reshape(-1, 3) if raw is not None
                   else np.stack([ray_world(ref, uv, case[source+'_depth']) for uv in corners]))
            uv, z = project(camera, xyz)
            good = np.isfinite(uv).all(1) & np.isfinite(z) & (z > .01)
            uv = uv[good]
            if len(uv):
                mask = Image.new('1', (width, height), 0)
                draw = ImageDraw.Draw(mask)
                if len(uv) >= 3:
                    from scipy.spatial import ConvexHull, QhullError
                    try:
                        polygon = uv[ConvexHull(uv).vertices]
                        draw.polygon([tuple(p) for p in polygon], fill=1)
                    except QhullError:
                        for point in uv: draw.point(tuple(point), fill=1)
                else:
                    for point in uv: draw.point(tuple(point), fill=1)
                support = np.asarray(mask, bool)
                if raw is not None:
                    from scipy.ndimage import binary_dilation
                    support = binary_dilation(support, structure=np.ones((3, 3), bool), iterations=1)
                target |= support
    from scipy.ndimage import distance_transform_edt
    ring = (distance_transform_edt(~target) <= ring_radius) & ~target if target.any() else np.zeros_like(target)
    return {'target': target, 'surrounding': ring, 'outside': ~(target | ring)}


def paired_metrics(photo, before, after, mask):
    n = int(mask.sum())
    if not n: return {'pixels': 0, 'status': 'NO_FIXED_WINDOW_SUPPORT'}
    err0 = np.mean(np.abs(before['rgb']-photo), axis=2)
    err1 = np.mean(np.abs(after['rgb']-photo), axis=2)
    delta = err1 - err0
    d0, d1 = before['depth'], after['depth']
    a0, a1 = before['alpha'], after['alpha']
    valid = mask & np.isfinite(d0) & np.isfinite(d1) & (d0 > 0) & (d1 > 0) & (a0 >= .5) & (a1 >= .5)
    angle_valid = valid & (np.linalg.norm(before['normal'], axis=2) > .1) & (np.linalg.norm(after['normal'], axis=2) > .1)
    dot = np.sum(before['normal']*after['normal'], axis=2)
    lengths = np.linalg.norm(before['normal'], axis=2)*np.linalg.norm(after['normal'], axis=2)
    angle = np.rad2deg(np.arccos(np.clip(dot / np.maximum(lengths, 1e-12), -1, 1)))
    mse0 = float(np.mean((before['rgb'][mask]-photo[mask])**2))
    mse1 = float(np.mean((after['rgb'][mask]-photo[mask])**2))
    return dict(pixels=n, status='PAIRED_FIXED_WINDOW',
        photo_mae_before=float(err0[mask].mean()), photo_mae_after=float(err1[mask].mean()),
        photo_mae_delta=float(delta[mask].mean()),
        photo_rmse_before=float(np.sqrt(mse0)), photo_rmse_after=float(np.sqrt(mse1)),
        photo_psnr_before_db=-10*math.log10(mse0) if mse0 > 0 else None,
        photo_psnr_after_db=-10*math.log10(mse1) if mse1 > 0 else None,
        photo_improved_pixels_gt_1_255=int((mask & (delta < -1/255)).sum()),
        photo_worsened_pixels_gt_1_255=int((mask & (delta > 1/255)).sum()),
        rgb_abs_change_mean=float(np.mean(np.abs(after['rgb'][mask]-before['rgb'][mask]))),
        rgb_abs_change_max=float(np.max(np.abs(after['rgb'][mask]-before['rgb'][mask]))),
        depth_paired_alpha05_pixels=int(valid.sum()),
        depth_abs_change_mean_m=float(np.abs(d1[valid]-d0[valid]).mean()) if valid.any() else None,
        depth_abs_change_max_m=float(np.abs(d1[valid]-d0[valid]).max()) if valid.any() else None,
        depth_changed_gt_1cm_pixels=int((valid & (np.abs(d1-d0) > .01)).sum()),
        alpha_coverage_lost_pixels=int((mask & (a0 >= .5) & (a1 < .5)).sum()),
        alpha_coverage_gained_pixels=int((mask & (a0 < .5) & (a1 >= .5)).sum()),
        normal_paired_pixels=int(angle_valid.sum()),
        normal_angle_change_mean_deg=float(angle[angle_valid].mean()) if angle_valid.any() else None,
        geometry_change_is_accuracy=False, image_fit_is_independent_validation=False)


def native_camera(definition, Camera, apply_projection, torch):
    width, height = int(definition['width']), int(definition['height'])
    k = np.asarray(definition['K'])
    camera = Camera(0, np.asarray(definition['R']).T, np.asarray(definition['t']),
        2*np.arctan(width/(2*k[0, 0])), 2*np.arctan(height/(2*k[1, 1])),
        torch.zeros((3, height, width)), None, Path(definition['image_name']).stem, 0, data_device='cpu')
    return apply_projection(camera, definition)


def cpu_render(camera, gaussian, pipe, background, render, torch):
    with torch.no_grad():
        package = render(camera, gaussian, pipe, background)
        result = dict(rgb=package['render'].detach().permute(1, 2, 0).cpu().numpy().copy(),
            depth=package['surf_depth'][0].detach().cpu().numpy().copy(),
            alpha=package['rend_alpha'][0].detach().cpu().numpy().copy(),
            normal=package['rend_normal'].detach().permute(1, 2, 0).cpu().numpy().copy(),
            radii=package['radii'].detach().cpu().numpy().copy())
    if not all(np.isfinite(a).all() for a in result.values()):
        raise ValueError('Native renderer returned nonfinite values')
    return result


def contribution(camera, gaussian, pipe, target_mask, render, torch):
    """Exact integrated native T*alpha weights through color derivatives.

    Zero color changes neither geometry nor opacity/depth sorting. All Gaussians
    remain in the pass, so weights include competing occluders. Screen-space
    radii are not interpreted as contribution.
    """
    color = torch.zeros_like(gaussian._xyz, requires_grad=True)
    pkg = render(camera, gaussian, pipe, torch.zeros(3, device='cuda'), override_color=color)
    mask = torch.from_numpy(target_mask).to('cuda')
    target = torch.autograd.grad(pkg['render'][0][mask].sum(), color, retain_graph=True)[0][:, 0]
    total = torch.autograd.grad(pkg['render'][0].sum(), color)[0][:, 0]
    return target.detach().cpu().numpy(), total.detach().cpu().numpy()


def save_render(folder, prefix, value):
    Image.fromarray(np.round(np.clip(value['rgb'], 0, 1)*255).astype(np.uint8)).save(folder/(prefix+'_rgb.png'))
    Image.fromarray(np.round(np.clip(value['alpha'], 0, 1)*255).astype(np.uint8)).save(folder/(prefix+'_alpha.png'))
    Image.fromarray(np.round(np.clip(value['normal']*.5+.5, 0, 1)*255).astype(np.uint8)).save(folder/(prefix+'_normal.png'))


def difference_images(folder, before, after, photo, masks):
    def signed(array, maximum, name, valid=None):
        scaled = np.clip(array/maximum, -1, 1)
        rgb = np.ones(array.shape+(3,), np.float32)
        rgb[..., 0] -= np.maximum(-scaled, 0)
        rgb[..., 2] -= np.maximum(scaled, 0)
        rgb[..., 1] -= np.abs(scaled)
        if valid is not None: rgb[~valid] = .3
        Image.fromarray(np.round(rgb*255).astype(np.uint8)).save(folder/(name+'.png'))
        return dict(range=[-maximum, maximum], clipped_pixels=int((np.abs(array)>maximum).sum()))
    photo_delta = np.mean(np.abs(after['rgb']-photo), 2)-np.mean(np.abs(before['rgb']-photo), 2)
    depth_valid = (before['depth'] > 0) & (after['depth'] > 0) & (before['alpha'] >= .5) & (after['alpha'] >= .5)
    metadata = dict(photo_error_delta=signed(photo_delta, .02, 'photo_error_delta'),
        depth_delta=signed(after['depth']-before['depth'], .1, 'depth_delta', depth_valid),
        alpha_delta=signed(after['alpha']-before['alpha'], .1, 'alpha_delta'))
    mask = np.zeros(masks['target'].shape+(3,), np.uint8)
    mask[masks['surrounding']] = [255, 192, 0]; mask[masks['target']] = [0, 210, 200]
    Image.fromarray(mask).save(folder/'fixed_masks.png')
    valid = (before['depth']>0)&(before['alpha']>=.5)
    depth_max = float(np.percentile(before['depth'][valid], 99)) if valid.any() else 1.
    for prefix, value in (('before', before), ('after', after)):
        d = np.clip(value['depth']/depth_max, 0, 1)
        d[(value['depth'] <= 0)|(value['alpha'] < .5)] = 0
        Image.fromarray(np.round(d*255).astype(np.uint8)).save(folder/(prefix+'_depth.png'))
    metadata['depth_display_range_m'] = [0, depth_max]
    metadata['signed_legend'] = 'blue negative; white zero; red positive; gray invalid depth'
    write(folder/'display_scales.json', metadata)


def run(args):
    if not Path('/.dockerenv').exists(): raise RuntimeError('Docker required')
    if args.output.exists(): raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    started = time.time()
    cases_doc = json.loads(args.cases.read_text())
    if cases_doc.get('scientific_verdict') is not None: raise ValueError('Null scientific verdict required')
    region = next(r for r in cases_doc['regions'] if r['id'] == args.region)
    anchor_receipt = json.loads((args.anchor/'receipt.json').read_text())
    checkpoint = args.anchor/'checkpoint.pth'
    checkpoint_sha = sha(checkpoint)
    if (checkpoint_sha != anchor_receipt['checkpoint_sha256'] or anchor_receipt['iteration'] != 8000
            or anchor_receipt.get('scientific_verdict') is not None
            or sha(args.anchor/'receipt.json') != region['anchor_receipt_sha256']):
        raise ValueError('Exact regional anchor differs')
    import torch
    if not torch.cuda.is_available(): raise RuntimeError('Coordinated GPU required')
    torch.set_num_threads(4)
    state = torch.load(checkpoint, map_location='cpu')
    if (state['schema'] != 'JBGS_GEOGS_COMPLETE_STATE_v1' or state['iteration'] != 8000
            or state.get('scientific_verdict') is not None): raise ValueError('Checkpoint identity differs')
    source_hashes = {str(p.relative_to(args.source)): sha(p) for p in sorted(args.source.rglob('*.py'))
                     if 'submodules' not in p.parts and '__pycache__' not in p.parts}
    if source_hashes != state['implementation_hashes']: raise ValueError('Checkpoint renderer source differs')
    sys.path.insert(0, str(args.source))
    from gaussian_renderer import render
    from scene.gaussian_model import GaussianModel
    from scene.cameras import Camera
    from jbgs_camera_adapter import apply_projection
    gaussian = GaussianModel(state['args']['sh_degree'])
    gaussian.active_sh_degree = state['model'][0]
    model_cpu = {field: state['model'][i+1].detach() for i, field in enumerate(FIELDS)}
    for field in FIELDS:
        setattr(gaussian, field, torch.nn.Parameter(model_cpu[field].to('cuda'), requires_grad=False))
    gaussian.spatial_lr_scale = state['model'][11]
    original_xyz = gaussian._xyz.detach().clone()
    native_args = state['args']; protected = state['frozen_mask']
    pipe = SimpleNamespace(compute_cov3D_python=native_args.get('compute_cov3D_python', False),
                           depth_ratio=native_args.get('depth_ratio', 0.), convert_SHs_python=False, debug=False)
    background = torch.tensor([1., 1., 1.] if native_args['white_background'] else [0., 0., 0.], device='cuda')
    before_exact = {field: bool(torch.equal(getattr(gaussian, field).cpu(), model_cpu[field])) for field in FIELDS}
    if not all(before_exact.values()): raise ValueError('Inference parameter copy differs')
    photo_manifest = json.loads((args.inputs/args.region/'input_manifest.json').read_text())
    seals = {r['path']: r['sha256'] for r in photo_manifest['files']}
    if sha(args.inputs/args.region/'input_manifest.json') != state['input_manifest_sha256']:
        raise ValueError('Checkpoint input manifest differs')
    copied_state_summary = dict(schema=state['schema'], iteration=state['iteration'], gaussians=len(original_xyz),
        protected=int(protected.sum()) if protected is not None else 0, native_args=native_args)
    del state
    cache = {}; photos = {}; camera_defs = {}
    for case in region['cases']:
        for definition in [case['reference_camera'], *case['neighbors']]:
            name = definition['image_name']
            if name in camera_defs and camera_defs[name] != definition:
                raise ValueError('Inconsistent camera definition')
            camera_defs[name] = definition
    for name, definition in camera_defs.items():
        relative = 'scene/images/'+name
        path = args.inputs/args.region/relative
        if sha(path) != seals[relative]: raise ValueError('Photo input differs: '+name)
        photos[name] = np.asarray(Image.open(path).convert('RGB'), dtype=np.float32)/255
        if photos[name].shape[:2] != (definition['height'], definition['width']): raise ValueError('RGB dimensions differ')
        camera = native_camera(definition, Camera, apply_projection, torch)
        before = cpu_render(camera, gaussian, pipe, background, render, torch)
        cache[name] = (camera, before)
    first_name = next(iter(cache)); first_camera, first_before = cache[first_name]
    repeated = cpu_render(first_camera, gaussian, pipe, background, render, torch)
    noop = {key: float(np.max(np.abs(first_before[key]-repeated[key]))) for key in ('rgb', 'depth', 'alpha', 'normal')}
    if any(value > 1e-6 for value in noop.values()): raise ValueError('No-op repeated render exceeds 1e-6')
    write(args.output/'invocation.json', dict(task_id=cases_doc['task_id'], region=args.region,
        scientific_verdict=None, checkpoint_sha256=checkpoint_sha, anchor_receipt_sha256=sha(args.anchor/'receipt.json'),
        cases_sha256=sha(args.cases), driver_sha256=sha(__file__), source_hashes=source_hashes,
        state=copied_state_summary, initial_parameters_exact=before_exact, no_op_render_max_abs=noop,
        operation='bounded XYZ-only inference intervention; no training/optimizer continuation',
        source_representation='existing native GeoGS 2D surfels; native diff_surfel_rasterization',
        runtime_image_id=os.environ.get('JBGS_RUNTIME_IMAGE_ID'), torch_version=torch.__version__,
        cuda_version=torch.version.cuda, gpu=torch.cuda.get_device_name(0), started_unix=started,
        max_displacement_m=args.max_displacement, maximum_ids=args.maximum_ids,
        minimum_target_locality=args.minimum_locality, geometric_depth_tolerance_m=args.depth_tolerance))
    results = []
    xyz_cpu = original_xyz.cpu().numpy()
    for case in region['cases']:
        case_started = time.time(); folder = args.output/case['case_id']; folder.mkdir()
        print(json.dumps(dict(event='case_started', region=args.region, case=case['case_id'])), flush=True)
        ref = case['reference_camera']; refname = ref['image_name']; camera, baseline = cache[refname]
        masks = frozen_masks(ref, case, True, args.ring_radius)
        target_weight, total_weight = contribution(camera, gaussian, pipe, masks['target'], render, torch)
        uv, z = project(ref, xyz_cpu)
        safe_uv = np.clip(np.nan_to_num(uv, nan=-1e9, posinf=1e9, neginf=-1e9), -1e9, 1e9)
        u = np.clip(np.floor(safe_uv[:, 0]+.5).astype(np.int64), 0, ref['width']-1)
        v = np.clip(np.floor(safe_uv[:, 1]+.5).astype(np.int64), 0, ref['height']-1)
        x0, y0, x1, y1 = case['bbox']
        inside = np.isfinite(uv).all(1) & (z > 0) & (uv[:, 0] >= x0-.5) & (uv[:, 0] < x1-.5) & (uv[:, 1] >= y0-.5) & (uv[:, 1] < y1-.5)
        depth_distance = np.abs(z-baseline['depth'][v, u])
        geometric = inside & (baseline['alpha'][v, u] >= .5) & (depth_distance <= args.depth_tolerance)
        locality = target_weight / np.maximum(total_weight, 1e-12)
        meaningful = target_weight >= .001
        candidates = geometric & meaningful
        selected_mask = candidates & (locality >= args.minimum_locality)
        ids = np.flatnonzero(selected_mask)
        reasons = []
        if case['decision'] != 'IMAGE_SUPPORTED_LOCAL_PROBE': reasons.append('SOURCE_EVIDENCE_NOT_APPROVED_FOR_PROBE')
        if len(ids) == 0: reasons.append('NO_LOCAL_GEOMETRY_AND_CONTRIBUTION_ASSOCIATION')
        if len(ids) > args.maximum_ids: reasons.append('ASSOCIATION_EXCEEDS_ID_CAP')
        alpha_sum = float(baseline['alpha'][masks['target']].sum())
        selected_fraction = float(target_weight[ids].sum()/max(alpha_sum, 1e-12))
        if selected_fraction < .05: reasons.append('SELECTED_IDS_EXPLAIN_LT_5_PERCENT_TARGET_ALPHA')
        applied_ids = ids if not reasons else np.array([], dtype=np.int64)
        before_xyz = xyz_cpu[applied_ids].copy()
        if len(applied_ids):
            delta, signed_distance = bounded_plane_displacement(before_xyz, case['target_xyz_world'], case['target_normal_world'], args.max_displacement)
            after_xyz = (before_xyz+delta).astype(np.float32)
            with torch.no_grad(): gaussian._xyz[torch.from_numpy(applied_ids).cuda()] = torch.from_numpy(after_xyz).cuda()
        else:
            after_xyz = before_xyz.copy(); delta = np.empty((0, 3)); signed_distance = np.empty(0)
        all_candidates = np.flatnonzero(candidates)
        np.savez_compressed(folder/'association_and_intervention.npz', candidate_ids=all_candidates,
            candidate_xyz_before=xyz_cpu[all_candidates], candidate_target_contribution=target_weight[all_candidates],
            candidate_total_contribution=total_weight[all_candidates], candidate_target_locality=locality[all_candidates],
            candidate_before_depth_distance_m=depth_distance[all_candidates], selected_ids=ids,
            applied_ids=applied_ids, xyz_before=before_xyz, xyz_after=after_xyz,
            displacement=after_xyz-before_xyz, plane_distance_before=signed_distance,
            target_total_alpha=np.array(alpha_sum), selected_target_fraction=np.array(selected_fraction))
        # A diagnostic color pass displays total selected T*alpha contribution.
        # Geometry is reset temporarily so this support image precedes intervention.
        with torch.no_grad():
            gaussian._xyz.copy_(original_xyz)
            color = torch.zeros_like(gaussian._xyz)
            color[torch.from_numpy(ids).cuda()] = 1.
            contribution_pkg = render(camera, gaussian, pipe, torch.zeros(3, device='cuda'), override_color=color)
            selected_support = contribution_pkg['render'][0].cpu().numpy().copy()
            if len(applied_ids): gaussian._xyz[torch.from_numpy(applied_ids).cuda()] = torch.from_numpy(after_xyz).cuda()
        Image.fromarray(np.round(np.clip(selected_support, 0, 1)*255).astype(np.uint8)).save(folder/'selected_contribution.png')
        np.save(folder/'selected_contribution.npy', selected_support)
        view_results = []
        for index, definition in enumerate([ref, *case['neighbors']]):
            name = definition['image_name']; c, before = cache[name]
            after = cpu_render(c, gaussian, pipe, background, render, torch) if len(applied_ids) else before
            vmasks = frozen_masks(definition, case, index == 0, args.ring_radius)
            photo = photos[name]
            vf = folder/f'view_{index:02d}'; vf.mkdir()
            save_render(vf, 'before', before); save_render(vf, 'after', after)
            difference_images(vf, before, after, photo, vmasks)
            Image.fromarray(np.round(photo*255).astype(np.uint8)).save(vf/'photo.png')
            metrics = {key: paired_metrics(photo, before, after, mask) for key, mask in vmasks.items()}
            np.savez_compressed(vf/'raw.npz', rgb_before=before['rgb'], rgb_after=after['rgb'], photo=photo,
                depth_before=before['depth'], depth_after=after['depth'], alpha_before=before['alpha'], alpha_after=after['alpha'],
                normal_before=before['normal'], normal_after=after['normal'], **{key+'_mask': value for key, value in vmasks.items()})
            write(vf/'metrics.json', dict(image_name=name, camera=definition,
                masks='reference exact7x7; neighbors union of both raw49-point projected hulls +1px support; surrounding31px dilation; no visibility or ground-truth claim', metrics=metrics))
            view_results.append(dict(image_name=name, path=vf.name, metrics=metrics))
        current_xyz = gaussian._xyz.detach().cpu().numpy()
        observed_ids = np.flatnonzero(np.any(current_xyz != xyz_cpu, axis=1))
        if not set(observed_ids).issubset(set(applied_ids)): raise ValueError('Unselected XYZ changed')
        unchanged = {field: bool(torch.equal(getattr(gaussian, field).cpu(), model_cpu[field])) for field in FIELDS[1:]}
        if not all(unchanged.values()): raise ValueError('Non-XYZ parameter changed')
        max_shift = float(np.linalg.norm(current_xyz[applied_ids]-xyz_cpu[applied_ids], axis=1).max()) if len(applied_ids) else 0.
        if max_shift > args.max_displacement+2e-5: raise ValueError('Actual float32 movement exceeds bound')
        result = dict(case_id=case['case_id'], status='BOUNDED_PROBE_APPLIED' if len(applied_ids) else 'NO_UPDATE_ABSTAIN',
            scientific_verdict=None, source_decision=case['decision'], source_reasons=case['reason_codes'], association_reasons=reasons,
            geometric_and_contribution_candidates=len(all_candidates), selected_ids=len(ids), changed_ids=len(observed_ids),
            selected_target_alpha_fraction=selected_fraction, target_alpha_sum=alpha_sum,
            applied_protected_ids=int(protected[applied_ids].sum()) if protected is not None else None,
            protected_intervention='explicit isolated counterfactual; original native training protection untouched',
            actual_max_displacement_m=max_shift, nonselected_xyz_exact=True, non_xyz_parameters_exact=unchanged,
            proposal=case, views=view_results, wall_seconds=time.time()-case_started)
        write(folder/'result.json', result); results.append(result)
        with torch.no_grad(): gaussian._xyz.copy_(original_xyz)
        if not torch.equal(gaussian._xyz, original_xyz): raise ValueError('Case reset differs')
        print(json.dumps(dict(event='case_complete', case=case['case_id'], status=result['status'], changed_ids=len(observed_ids))), flush=True)
    if sha(checkpoint) != checkpoint_sha: raise ValueError('Read-only input checkpoint changed')
    outputs = {str(p.relative_to(args.output)): sha(p) for p in sorted(args.output.rglob('*')) if p.is_file()}
    receipt = dict(task_id=cases_doc['task_id'], region=args.region, status='PASS_BOUNDED_INFERENCE_DIAGNOSTIC', scientific_verdict=None,
        cases_sha256=sha(args.cases), checkpoint_sha256=checkpoint_sha, no_op_render_max_abs=noop,
        original_checkpoint_unchanged=True, cases=results, output_sha256=outputs,
        inference_not_training=True, independent_accuracy=False, wall_seconds=time.time()-started,
        peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(), peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
    write(args.output/'receipt.json', receipt)
    print(json.dumps(dict(region=args.region, status=receipt['status'], cases=len(results), wall_seconds=receipt['wall_seconds'])), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--region', choices=('P1', 'P2', 'P3'), required=True)
    parser.add_argument('--source', type=Path, default=Path('/source'))
    parser.add_argument('--anchor', type=Path, default=Path('/anchor'))
    parser.add_argument('--inputs', type=Path, default=Path('/inputs'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-displacement', type=float, default=.1)
    parser.add_argument('--maximum-ids', type=int, default=256)
    parser.add_argument('--minimum-locality', type=float, default=.5)
    parser.add_argument('--depth-tolerance', type=float, default=.25)
    parser.add_argument('--ring-radius', type=int, default=31)
    args = parser.parse_args()
    if not (0 < args.max_displacement <= .1 and 0 < args.maximum_ids <= 256 and .5 <= args.minimum_locality <= 1 and 0 < args.depth_tolerance <= .5):
        raise ValueError('Probe limits exceeded')
    existed = args.output.exists()
    try:
        run(args)
    except Exception as error:
        if not existed and args.output.is_dir():
            write(args.output/'failure.json', dict(status='FAIL', scientific_verdict=None,
                region=args.region, error=repr(error), traceback=traceback.format_exc(),
                partial_outputs_preserved=True, driver_sha256=sha(__file__)))
        raise


if __name__ == '__main__': main()

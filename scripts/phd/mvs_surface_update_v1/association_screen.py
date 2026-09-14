"""Nonmutating screen of already-admitted observations against a frozen GS anchor.

The original seven-pixel evidence window and every frozen association threshold
are retained. This screen does not render any modified state or rank after-fit.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import os
import resource
import sys
import time
import traceback
from types import SimpleNamespace

import numpy as np


POLICY = dict(minimum_target_contribution=.001, minimum_locality=.5,
              depth_tolerance_m=.25, maximum_ids=256, minimum_target_alpha_fraction=.05,
              maximum_displacement_m=.1, patch_side_pixels=7)


def select_ids(camera, bbox, xyz, baseline, target_weight, total_weight, project):
    """Exactly the frozen gaussian_probe association predicates, without edits."""
    uv, z = project(camera, xyz)
    safe_uv = np.clip(np.nan_to_num(uv, nan=-1e9, posinf=1e9, neginf=-1e9), -1e9, 1e9)
    u = np.clip(np.floor(safe_uv[:, 0]+.5).astype(np.int64), 0, camera['width']-1)
    v = np.clip(np.floor(safe_uv[:, 1]+.5).astype(np.int64), 0, camera['height']-1)
    x0, y0, x1, y1 = bbox
    inside = np.isfinite(uv).all(1) & (z > 0) & (uv[:, 0] >= x0-.5) & (uv[:, 0] < x1-.5) & (uv[:, 1] >= y0-.5) & (uv[:, 1] < y1-.5)
    depth_distance = np.abs(z-baseline['depth'][v, u])
    alpha_ok = baseline['alpha'][v, u] >= .5
    geometric = inside & alpha_ok & (depth_distance <= POLICY['depth_tolerance_m'])
    locality = target_weight/np.maximum(total_weight, 1e-12)
    meaningful = target_weight >= POLICY['minimum_target_contribution']
    candidates = geometric & meaningful
    selected = candidates & (locality >= POLICY['minimum_locality'])
    return dict(ids=np.flatnonzero(selected), candidates=np.flatnonzero(candidates),
                locality=locality, depth_distance=depth_distance,
                funnel=dict(positive_target_contribution_ids=int(meaningful.sum()),
                    projected_center_inside_ids=int(inside.sum()),
                    center_inside_alpha05_ids=int((inside & alpha_ok).sum()),
                    geometry_compatible_ids=int(geometric.sum()),
                    geometry_and_contribution_ids=int(candidates.sum()),
                    localized_ids=int(selected.sum())))


def admission_reasons(ids, selected_fraction, decision):
    reasons = []
    if decision != 'IMAGE_SUPPORTED_LOCAL_PROBE': reasons.append('SOURCE_EVIDENCE_NOT_APPROVED_FOR_PROBE')
    if len(ids) == 0: reasons.append('NO_LOCAL_GEOMETRY_AND_CONTRIBUTION_ASSOCIATION')
    if len(ids) > POLICY['maximum_ids']: reasons.append('ASSOCIATION_EXCEEDS_ID_CAP')
    if selected_fraction < POLICY['minimum_target_alpha_fraction']: reasons.append('SELECTED_IDS_EXPLAIN_LT_5_PERCENT_TARGET_ALPHA')
    return reasons


def run(args, h):
    import torch
    if not Path('/.dockerenv').exists() or not torch.cuda.is_available(): raise RuntimeError('Coordinated GPU Docker required')
    if args.output.exists(): raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    started = time.time(); torch.set_num_threads(4)
    doc = json.loads(args.cases.read_text())
    if doc.get('scientific_verdict') is not None: raise ValueError('Null scientific verdict required')
    region = next(r for r in doc['regions'] if r['id'] == args.region)
    checkpoint = args.anchor/'checkpoint.pth'; checksum = h.sha(checkpoint)
    anchor_receipt = json.loads((args.anchor/'receipt.json').read_text())
    if (anchor_receipt['checkpoint_sha256'] != checksum or anchor_receipt['iteration'] != 8000
            or anchor_receipt.get('scientific_verdict') is not None
            or h.sha(args.anchor/'receipt.json') != region['anchor_receipt_sha256']): raise ValueError('Anchor identity differs')
    state = torch.load(checkpoint, map_location='cpu')
    if state['schema'] != 'JBGS_GEOGS_COMPLETE_STATE_v1' or state['iteration'] != 8000: raise ValueError('Complete anchor format required')
    source_hashes = {str(p.relative_to(args.source)): h.sha(p) for p in sorted(args.source.rglob('*.py'))
                     if 'submodules' not in p.parts and '__pycache__' not in p.parts}
    if source_hashes != state['implementation_hashes']: raise ValueError('Checkpoint renderer source differs')
    manifest_path = args.inputs/args.region/'input_manifest.json'
    if h.sha(manifest_path) != state['input_manifest_sha256']: raise ValueError('Original input identity differs')
    manifest = json.loads(manifest_path.read_text()); seals = {r['path']: r['sha256'] for r in manifest['files']}
    sys.path.insert(0, str(args.source))
    from gaussian_renderer import render
    from scene.gaussian_model import GaussianModel
    from scene.cameras import Camera
    from jbgs_camera_adapter import apply_projection
    gaussian = GaussianModel(state['args']['sh_degree']); gaussian.active_sh_degree = state['model'][0]
    model_cpu = {field: state['model'][i+1].detach() for i, field in enumerate(h.FIELDS)}
    for field in h.FIELDS: setattr(gaussian, field, torch.nn.Parameter(model_cpu[field].to('cuda'), requires_grad=False))
    gaussian.spatial_lr_scale = state['model'][11]
    native_args = state['args']; protected = state['frozen_mask']; xyz = model_cpu['_xyz'].numpy()
    pipe = SimpleNamespace(compute_cov3D_python=native_args.get('compute_cov3D_python', False),
        depth_ratio=native_args.get('depth_ratio', 0.), convert_SHs_python=False, debug=False)
    bg = torch.tensor([1.,1.,1.] if native_args['white_background'] else [0.,0.,0.], device='cuda')
    del state
    initial = {field: bool(torch.equal(getattr(gaussian, field).cpu(), model_cpu[field])) for field in h.FIELDS}
    if not all(initial.values()): raise ValueError('Initial parameters differ')
    invocation = dict(task_id=doc['task_id'], region=args.region, scientific_verdict=None,
        operation='association-only nonmutating screen; no after-state rendering or performance selection',
        policy=POLICY, cases_sha256=h.sha(args.cases), checkpoint_sha256=checksum,
        original_probe_helper_sha256=h.sha(args.probe_helper), driver_sha256=h.sha(__file__),
        source_hashes=source_hashes, initial_parameters_exact=initial,
        runtime_image_id=os.environ.get('JBGS_RUNTIME_IMAGE_ID'), torch_version=torch.__version__,
        gpu=torch.cuda.get_device_name(0), started_unix=started)
    h.write(args.output/'invocation.json', invocation)
    cache = {}; results=[]; noop=None
    for case in region['cases']:
        if case['decision'] != 'IMAGE_SUPPORTED_LOCAL_PROBE': raise ValueError('Screen scope restricted to already-admitted observations')
        if [case['bbox'][2]-case['bbox'][0],case['bbox'][3]-case['bbox'][1]] != [7,7]: raise ValueError('Frozen seven-pixel support changed')
        ref = case['reference_camera']; name=ref['image_name']
        if name not in cache:
            photo = args.inputs/args.region/'scene/images'/name
            if h.sha(photo) != seals['scene/images/'+name]: raise ValueError('Photo identity differs')
            camera = h.native_camera(ref, Camera, apply_projection, torch)
            before = h.cpu_render(camera, gaussian, pipe, bg, render, torch)
            cache[name] = (camera, before, ref)
            if noop is None:
                repeated = h.cpu_render(camera, gaussian, pipe, bg, render, torch)
                noop = {key: float(np.max(np.abs(before[key]-repeated[key]))) for key in ('rgb','depth','alpha','normal')}
                if any(v > 1e-6 for v in noop.values()): raise ValueError('No-op numerical repeat exceeds frozen bound')
        camera,before,cached_ref=cache[name]
        if ref != cached_ref: raise ValueError('Camera identity conflicts')
        mask = h.frozen_masks(ref, case, True)['target']
        tw,total = h.contribution(camera, gaussian, pipe, mask, render, torch)
        selected = select_ids(ref, case['bbox'], xyz, before, tw, total, h.project)
        ids, candidates = selected['ids'], selected['candidates']
        alpha_sum = float(before['alpha'][mask].sum())
        fraction = float(tw[ids].sum()/max(alpha_sum,1e-12))
        reasons = admission_reasons(ids, fraction, case['decision'])
        folder=args.output/case['case_id'];folder.mkdir()
        np.savez_compressed(folder/'association.npz',candidate_ids=candidates,candidate_xyz=xyz[candidates],
            candidate_target_contribution=tw[candidates],candidate_total_contribution=total[candidates],
            candidate_locality=selected['locality'][candidates],candidate_depth_distance_m=selected['depth_distance'][candidates],
            selected_ids=ids,selected_xyz=xyz[ids],target_alpha_sum=np.array(alpha_sum),selected_target_fraction=np.array(fraction))
        row=dict(case_id=case['case_id'], selection=case.get('selection'), reference_image=name,
            uv=case['uv'], status='ELIGIBLE_FOR_BOUNDED_PROBE' if not reasons else 'ASSOCIATION_ABSTAIN',
            scientific_verdict=None, association_reasons=reasons, funnel=selected['funnel'], selected_ids=len(ids),
            selected_target_alpha_fraction=fraction, target_alpha_sum=alpha_sum,
            all_target_derivative_sum=float(tw.astype(np.float64).sum()),
            candidate_locality_max=float(selected['locality'][candidates].max()) if len(candidates) else None,
            selected_protected_ids=int(protected[ids].sum()) if protected is not None else None,
            selected_xyz_payload='association.npz', modified_gaussians=0, after_state_rendered=False)
        h.write(folder/'result.json',row);results.append(row)
        print(json.dumps(h.clean(row)),flush=True)
    final = {field: bool(torch.equal(getattr(gaussian,field).cpu(),model_cpu[field])) for field in h.FIELDS}
    if not all(final.values()) or h.sha(checkpoint) != checksum: raise ValueError('Nonmutating screen modified input')
    outputs={str(p.relative_to(args.output)):h.sha(p) for p in sorted(args.output.rglob('*')) if p.is_file()}
    result=dict(status='PASS_ASSOCIATION_ONLY_SCREEN',task_id=doc['task_id'],region=args.region,scientific_verdict=None,
        policy=POLICY,cases=results,eligible_count=sum(r['status']=='ELIGIBLE_FOR_BOUNDED_PROBE' for r in results),
        no_op_render_max_abs=noop,final_parameters_exact=final,original_checkpoint_unchanged=True,
        checkpoint_sha256=checksum,cases_sha256=h.sha(args.cases),output_sha256=outputs,
        original_probe_helper_sha256=h.sha(args.probe_helper),modified_gaussians=0,after_state_rendered=False,
        wall_seconds=time.time()-started,peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(),
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
    h.write(args.output/'receipt.json',result)
    print(json.dumps({k:result[k] for k in ('status','region','eligible_count','wall_seconds')}),flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('cases','source','anchor','inputs','output','probe-helper'):ap.add_argument('--'+key,type=Path,required=True)
    ap.add_argument('--probe-helper-sha256',required=True);ap.add_argument('--region',choices=('P2','P3'),required=True)
    args=ap.parse_args()
    import hashlib
    if hashlib.sha256(args.probe_helper.read_bytes()).hexdigest()!=args.probe_helper_sha256:raise ValueError('Exact frozen probe helper changed')
    spec=importlib.util.spec_from_file_location('frozen_gaussian_probe',args.probe_helper)
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    existed=args.output.exists()
    try:run(args,h)
    except Exception as e:
        if not existed and args.output.is_dir():h.write(args.output/'failure.json',dict(status='FAIL',scientific_verdict=None,error=repr(e),traceback=traceback.format_exc(),partial_outputs_preserved=True))
        raise


if __name__=='__main__':main()

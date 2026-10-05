"""Paired expected-depth diagnostics against evaluation-only current UAS returns.

Run after a regional probe receipt is sealed. Neither return selection nor the
target/annulus window depends on before/after model depth, opacity, or error.
This scores visible-return point samples, not a watertight reference surface.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.spatial import cKDTree


REFERENCE_SHAS = {
    'P1': '3d111cf0cd8ab39fccb85ce0075486ec40f4f60584b5c68b2ab122918b321543',
    'P2': '9dc75111e8a5e83808d566c0b6621092423898a1f6badb9438f1a0d75e16e7ba',
    'P3': 'a72041a28c8242d3901f5696d88e607473814299baab43103fda89fc179b1f81',
}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def clean(value):
    if isinstance(value, dict): return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [clean(v) for v in value]
    if isinstance(value, np.ndarray): return clean(value.tolist())
    if isinstance(value, np.integer): return int(value)
    if isinstance(value, np.bool_): return bool(value)
    if isinstance(value, (float, np.floating)): return float(value) if np.isfinite(value) else None
    return value


def write(path, data):
    with Path(path).open('x') as stream:
        json.dump(clean(data), stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def reference_masks(camera, bbox, ring_radius):
    """Original reference-camera patch and fixed pixel annulus, no model input."""
    h, w = int(camera['height']), int(camera['width'])
    x0, y0, x1, y1 = map(int, bbox)
    target = np.zeros((h, w), bool)
    target[max(y0, 0):min(y1, h), max(x0, 0):min(x1, w)] = True
    ring = ((distance_transform_edt(~target) <= ring_radius) & ~target
            if target.any() else np.zeros_like(target))
    return target, ring


def front_return_cohort(points, camera, target, surrounding):
    """Nearest RGB pixel, frontmost measured UAS return, deterministic raw ID.

    This rejects rear returns observed by the same image pixel. Missing UAS
    foreground samples may still leave actually occluded returns, so it is a
    UAS-conditioned visibility diagnostic rather than proven camera visibility.
    """
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3: raise ValueError('Expected Nx3 UAS points')
    h, w = target.shape
    if surrounding.shape != target.shape or (target & surrounding).any():
        raise ValueError('Fixed target and annulus must be disjoint')
    union = target | surrounding
    if union.sum() > 100000: raise ValueError('Local reference window exceeds 100,000 pixels')
    kept_ids, kept_uv, kept_z, kept_pixel = [], [], [], []
    r, t, k = (np.asarray(camera[key], dtype=np.float64) for key in ('R', 't', 'K'))
    for start in range(0, len(points), 250000):
        source = points[start:start+250000]
        cam = source @ r.T + t
        valid = np.isfinite(cam).all(1) & (cam[:, 2] > 0)
        local = np.flatnonzero(valid)
        cam = cam[local]
        projected = cam @ k.T
        uv = projected[:, :2] / projected[:, 2:3]
        in_frame = ((uv[:, 0] >= -.5) & (uv[:, 0] < w-.5)
                    & (uv[:, 1] >= -.5) & (uv[:, 1] < h-.5))
        local, cam, uv = local[in_frame], cam[in_frame], uv[in_frame]
        ij = np.floor(uv+.5).astype(np.int64)
        selected = union[ij[:, 1], ij[:, 0]]
        kept_ids.append(start+local[selected]); kept_uv.append(uv[selected])
        kept_z.append(cam[selected, 2]); kept_pixel.append(ij[selected, 1]*w+ij[selected, 0])
    ids = np.concatenate(kept_ids) if kept_ids else np.empty(0, np.int64)
    uv = np.concatenate(kept_uv) if kept_uv else np.empty((0, 2))
    z = np.concatenate(kept_z) if kept_z else np.empty(0)
    pixel = np.concatenate(kept_pixel) if kept_pixel else np.empty(0, np.int64)
    order = np.lexsort((ids, z, pixel))
    sorted_pixel = pixel[order]
    first = np.r_[True, sorted_pixel[1:] != sorted_pixel[:-1]] if len(order) else np.empty(0, bool)
    winners = order[first]
    chosen, locations, depths = ids[winners], uv[winners], z[winners]
    pixels = np.column_stack((pixel[winners] % w, pixel[winners] // w)).astype(np.int64)
    code = np.where(target[pixels[:, 1], pixels[:, 0]], 1, 2).astype(np.int8)
    # Excluded values are retained as counts, not silently treated as misses.
    unique, counts = np.unique(sorted_pixel, return_counts=True)
    return dict(reference_original_indices=chosen, reference_points=points[chosen],
                reference_projected_uv=locations, reference_camera_z=depths,
                reference_pixel_xy=pixels, domain_code=code,
                projected_returns_in_window=np.array(len(ids), np.int64),
                excluded_rear_or_duplicate_returns=np.array(len(ids)-len(chosen), np.int64),
                returns_per_selected_pixel=counts.astype(np.int64),
                projection_rounding_error_px=np.linalg.norm(locations-pixels, axis=1))


def stats(values):
    x = np.asarray(values)
    x = x[np.isfinite(x)]
    if not len(x): return dict(count=0, mean=None, median=None, p95=None, rmse=None, maximum=None)
    return dict(count=len(x), mean=x.mean(), median=np.median(x), p95=np.quantile(x, .95),
                rmse=np.sqrt(np.mean(x*x)), maximum=x.max())


def score_cohort(cohort, camera, arrays, alpha_min=.5):
    """Keep all frozen IDs; conditional paired metrics accompany coverage losses."""
    ij = cohort['reference_pixel_xy']; x, y = ij[:, 0], ij[:, 1]
    zref = cohort['reference_camera_z']; refs = cohort['reference_points']
    n = len(ij); ray = np.column_stack((ij, np.ones(n))) @ np.linalg.inv(camera['K']).T
    r, t = np.asarray(camera['R']), np.asarray(camera['t'])
    raw = dict(cohort)
    tree = cKDTree(refs) if len(refs) else None
    for arm in ('before', 'after'):
        depth = np.asarray(arrays['depth_'+arm])[y, x].astype(np.float64)
        alpha = np.asarray(arrays['alpha_'+arm])[y, x].astype(np.float64)
        valid = np.isfinite(depth) & (depth > 0) & np.isfinite(alpha) & (alpha >= alpha_min)
        xyz = (ray*depth[:, None]-t) @ r
        signed = np.where(valid, depth-zref, np.nan)
        paired_dist = np.where(valid, np.linalg.norm(xyz-refs, axis=1), np.nan)
        nearest = np.full(n, np.nan)
        if tree is not None and valid.any(): nearest[valid] = tree.query(xyz[valid], workers=1)[0]
        raw.update({arm+'_valid': valid, arm+'_depth': depth, arm+'_alpha': alpha,
                    arm+'_rendered_xyz': np.where(valid[:, None], xyz, np.nan),
                    arm+'_signed_camera_z_error_m': signed, arm+'_absolute_camera_z_error_m': np.abs(signed),
                    arm+'_distance_to_same_return_m': paired_dist,
                    arm+'_nearest_local_front_return_distance_m': nearest})
    both = raw['before_valid'] & raw['after_valid']
    raw['paired_valid'] = both
    raw['paired_absolute_error_delta_m'] = raw['after_absolute_camera_z_error_m']-raw['before_absolute_camera_z_error_m']
    summary = {}
    for code, domain in ((1, 'target'), (2, 'surrounding')):
        members = cohort['domain_code'] == code
        pair = members & both; b = members & raw['before_valid']; a = members & raw['after_valid']
        denominator = int(members.sum())
        row = dict(status='REFERENCE_RETURN_DIAGNOSTIC' if denominator else 'NOT_ASSESSED_REFERENCE_ABSENT',
                   frozen_reference_count=denominator, before_valid=int(b.sum()), after_valid=int(a.sum()),
                   paired_valid=int(pair.sum()), missing_before=int((members & ~raw['before_valid']).sum()),
                   missing_after=int((members & ~raw['after_valid']).sum()),
                   lost_after=int((b & ~raw['after_valid']).sum()), gained_after=int((a & ~raw['before_valid']).sum()),
                   missing_both=int((members & ~raw['before_valid'] & ~raw['after_valid']).sum()),
                   before_coverage=float(b.sum()/denominator) if denominator else None,
                   after_coverage=float(a.sum()/denominator) if denominator else None,
                   projection_rounding_error_px=stats(cohort['projection_rounding_error_px'][members]),
                   condition_on_paired_valid=True, thresholds_are_diagnostic=True)
        for arm in ('before', 'after'):
            for metric in ('absolute_camera_z_error_m', 'signed_camera_z_error_m', 'distance_to_same_return_m',
                           'nearest_local_front_return_distance_m'):
                row['paired_'+arm+'_'+metric] = stats(raw[arm+'_'+metric][pair])
        differences = raw['paired_absolute_error_delta_m'][pair]
        row['paired_absolute_error_delta_m'] = stats(differences)
        row['transitions'] = [dict(threshold_m=tau, improved=int((differences < -tau).sum()),
                                  damaged=int((differences > tau).sum()), within_threshold=int((np.abs(differences) <= tau).sum()))
                              for tau in (.01, .05)]
        summary[domain] = row
    return raw, summary


def run(args):
    started = time.time()
    probe = json.loads((args.probe/'receipt.json').read_text())
    if probe['status'] != 'PASS_BOUNDED_INFERENCE_DIAGNOSTIC' or probe['scientific_verdict'] is not None:
        raise ValueError('A sealed completed null-verdict probe is required')
    if sha(args.cases) != probe['cases_sha256']: raise ValueError('Case proposal changed after probe')
    cases_doc = json.loads(args.cases.read_text()); region = probe['region']
    cases = next(r['cases'] for r in cases_doc['regions'] if r['id'] == region)
    if sha(args.reference) != REFERENCE_SHAS[region]: raise ValueError('Exact current UAS identity mismatch')
    args.output.mkdir(parents=True, exist_ok=False)
    with np.load(args.reference, allow_pickle=False) as reference_file:
        reference = reference_file['uas_xyz'].astype(np.float64)
    frozen = []
    for case in cases:
        identifier = case['case_id']; camera = case['reference_camera']
        folder = args.output/identifier; folder.mkdir()
        target, surrounding = reference_masks(camera, case['bbox'], args.ring_radius)
        cohort = front_return_cohort(reference, camera, target, surrounding)
        # Every case cohort is fixed before opening ANY model output array.
        np.savez_compressed(folder/'reference_cohort.npz', **cohort)
        frozen.append((case, target, surrounding, cohort))
    write(args.output/'cohorts_frozen.json', dict(region=region, scientific_verdict=None,
        reference_sha256=REFERENCE_SHAS[region], cases_sha256=sha(args.cases),
        selection_sees_model_depth_or_alpha=False,
        cohorts={case['case_id']: sha(args.output/case['case_id']/'reference_cohort.npz')
                 for case, _, _, _ in frozen}))
    results = []; bound = []
    for case, target, surrounding, cohort in frozen:
        identifier = case['case_id']; camera = case['reference_camera']; folder = args.output/identifier
        raw_path = args.probe/identifier/'view_00/raw.npz'
        relative = str(raw_path.relative_to(args.probe))
        if sha(raw_path) != probe['output_sha256'][relative]: raise ValueError('Probe raw arrays changed')
        with np.load(raw_path, allow_pickle=False) as archive:
            arrays = {key: archive[key] for key in ('depth_before', 'depth_after', 'alpha_before', 'alpha_after', 'target_mask', 'surrounding_mask')}
        if any(arrays[key].shape != target.shape for key in arrays): raise ValueError('Probe dimensions differ from camera')
        if not (np.array_equal(target, arrays['target_mask']) and np.array_equal(surrounding, arrays['surrounding_mask'])):
            raise ValueError('Frozen source masks differ from probe masks')
        paired, summary = score_cohort(cohort, camera, arrays, args.alpha_min)
        np.savez_compressed(folder/'paired_reference_arrays.npz', **paired)
        result = dict(case_id=identifier, image_name=camera['image_name'], scientific_verdict=None,
                      original_reference_sha256=REFERENCE_SHAS[region], cohort_sha256=sha(folder/'reference_cohort.npz'),
                      frozen_ids=len(cohort['reference_original_indices']),
                      projected_returns_in_window=int(cohort['projected_returns_in_window']),
                      excluded_rear_or_duplicate_returns=int(cohort['excluded_rear_or_duplicate_returns']),
                      reference_cohort='frontmost original UAS return per nearest native RGB pixel; fixed source-only window',
                      domains=summary)
        write(folder/'summary.json', result); results.append(result)
        bound.append(dict(path=relative, sha256=probe['output_sha256'][relative]))
    write(args.output/'summary.json', dict(region=region, cases=results, scientific_verdict=None,
        representation='alpha-normalized rendered expected camera-Z vs original front UAS point returns',
        limitations=['UAS point sampling is not a watertight reference surface or guaranteed camera visibility',
                     'Point-to-point distance contains reference density and nearest-pixel quantization effects',
                     'Coverage loss is reported separately; paired error summaries condition on both valid arms',
                     'Inherited working EPSG:25832/UAS-header EPSG:32632 absolute datum calibration is unverified',
                     'Current images and current UAS are development evidence; no confirmatory scientific verdict']))
    write(args.output/'receipt.json', dict(task_id=cases_doc['task_id'], region=region,
        status='PASS_REFERENCE_DIAGNOSTIC', scientific_verdict=None, references_used_in_intervention=False,
        scope='fixed reference-camera patch and annulus only; no reference alignment or parameter selection',
        probe_receipt_sha256=sha(args.probe/'receipt.json'), cases_sha256=sha(args.cases),
        reference_sha256=REFERENCE_SHAS[region], source_sha256=sha(__file__), raw_probe_inputs=bound,
        alpha_min=args.alpha_min, annulus_radius_px=args.ring_radius,
        runtime=dict(python=platform.python_version(), numpy=np.__version__), elapsed_seconds=time.time()-started,
        output_sha256={str(p.relative_to(args.output)): sha(p) for p in sorted(args.output.rglob('*')) if p.is_file()}))
    print(json.dumps(dict(region=region, status='PASS_REFERENCE_DIAGNOSTIC', cases=len(results))), flush=True)


def main():
    if not Path('/.dockerenv').exists(): raise RuntimeError('CPU Docker execution required')
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('probe', 'cases', 'reference', 'output'): parser.add_argument('--'+key, type=Path, required=True)
    parser.add_argument('--ring-radius', type=int, default=31)
    parser.add_argument('--alpha-min', type=float, default=.5)
    args = parser.parse_args()
    if args.ring_radius != 31 or args.alpha_min != .5: raise ValueError('Frozen ring=31px and alpha=0.5 required')
    try: run(args)
    except Exception as exc:
        if args.output.is_dir() and not (args.output/'failure.json').exists():
            write(args.output/'failure.json', dict(error=repr(exc), scientific_verdict=None))
        raise


if __name__ == '__main__': main()

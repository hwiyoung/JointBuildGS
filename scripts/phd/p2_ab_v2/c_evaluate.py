"""Evaluate B outputs only after training, using the preserved P2 UAS reference."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import numpy as np

from src.phd.p2_ab_v2.geometry_evaluation import GeometryEvaluator
from src.phd.p2_ab_v2.evaluation import paired_detail_metrics, rasterize_median, detail_residual, common_detail_fields

REPO = Path(__file__).resolve().parents[3]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def write(path, payload):
    with Path(path).open('x') as f:
        json.dump(payload, f, ensure_ascii=False, allow_nan=False, indent=2)
        f.write('\n')


def load_xyz(path):
    with np.load(path, allow_pickle=False) as data:
        xyz = data['xyz'].astype(np.float64)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or not np.isfinite(xyz).all():
        raise ValueError(f'invalid surface XYZ: {path}')
    return xyz


def main(args):
    start = time.monotonic()
    args.output.mkdir(parents=True, exist_ok=False)
    write(args.output/'STARTED.json', dict(task_id='PHD-P2-AB-V2-C-EVALUATION', scientific_verdict=None))
    manifest_path = args.common/'sample_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    reference_path = args.reference/'evaluation_reference.npz'
    reference_manifest_path = args.reference/'reference_manifest.json'
    reference_meta = json.loads(reference_manifest_path.read_text())
    with np.load(reference_path, allow_pickle=False) as data:
        reference = data['uas_xyz'].astype(np.float64)
    domain = manifest['domain']
    bounds = np.array([[domain['x'][0], domain['y'][0]], [domain['x'][1], domain['y'][1]]])
    inside = lambda p: ((p[:, :2] >= bounds[0]) & (p[:, :2] < bounds[1])).all(1)
    reference = reference[inside(reference)]
    inputs = {str(p): sha(p) for p in [manifest_path, reference_path, reference_manifest_path]}
    rows = []
    evaluator = GeometryEvaluator(reference, workers=4)
    metric_cache, cache_hits = {}, 0
    spacings = (.25, .5, 1.)
    reference_fields = {s: detail_residual(rasterize_median(reference, bounds, s)[0]) for s in spacings}
    arm_fields = {s: {} for s in spacings}
    for root in args.b_root:
        run_receipt = root/'result.json'
        if not run_receipt.is_file():
            raise ValueError(f'B completed result.json required before reference evaluation: {root}')
        inputs[str(run_receipt)] = sha(run_receipt)
        for final_path in sorted(root.glob('*/extracted_surface.npz')):
            folder = final_path.parent
            if f'{root.name}/{folder.name}' in args.exclude_arm:
                continue
            initial_path = folder/'initial_extracted_surface.npz'
            stages = [initial_path, final_path]
            points, metrics = [], {}
            for stage, path in zip(['initial', 'final'], stages):
                xyz = load_xyz(path)
                mask = inside(xyz)
                p = xyz[mask]
                # XY domain is fixed; wrong Z is retained and penalized.
                point_hash = hashlib.sha256(p.tobytes()).hexdigest()
                if point_hash not in metric_cache:
                    metric_cache[point_hash] = evaluator.measure(p, (.25, .5, 1.), .5)
                else:
                    cache_hits += 1
                metric = copy.deepcopy(metric_cache[point_hash])
                metric['all_output_point_count'] = len(xyz)
                metric['outside_fixed_xy_domain_count'] = int((~mask).sum())
                metric['outside_xy_reference_status'] = 'OUTSIDE_FIXED_EVALUATION_DOMAIN'
                metrics[stage] = metric
                points.append(p)
                inputs[str(path)] = sha(path)
            detail = paired_detail_metrics(*points, reference, bounds, (.25, .5, 1.))
            key = f'{root.name}/{folder.name}'
            for s in spacings:
                arm_fields[s][key] = {phase: detail_residual(rasterize_median(p, bounds, s)[0])
                                     for phase, p in zip(['initial', 'final'], points)}
            row = dict(run=root.name, arm=folder.name, geometry=metrics, detail=detail)
            rows.append(row)
            write(args.output/f'{root.name}__{folder.name}.json', row)
            print(json.dumps({'run': root.name, 'arm': folder.name,
                'initial_p90_m': metrics['initial']['prediction_to_reference']['p90_m'],
                'final_p90_m': metrics['final']['prediction_to_reference']['p90_m']}), flush=True)
    if not rows:
        raise ValueError('No complete B surfaces found')
    write(args.output/'evaluation.json', dict(
        scientific_verdict=None, arms=rows, reference_points=len(reference),
        cross_arm_detail=[dict(spacing_m=s, **common_detail_fields(arm_fields[s], reference_fields[s])) for s in spacings],
        comparison='prior-start arms share G0; image-only input differs; v1 image resolution and support differ',
        detail_scope='2.5D fixed XY median-height residual diagnostic; not semantic detail certification',
        reference_frame='preserved legacy numeric frame; datum/epoch and native reference precision uncalibrated',
    ))
    sources = [Path(__file__), REPO/'src/phd/p2_ab_v1/evaluation.py',
               REPO/'src/phd/p2_ab_v2/geometry_evaluation.py',
               REPO/'src/phd/p2_ab_v2/evaluation.py',
               REPO/'docs/experiments/phd/p2_ab_v2/C_EVALUATION_PROTOCOL_ko_v2.md']
    for source in sources:
        target = args.output/'source_snapshot'/source.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    if any(sha(p) != h for p, h in inputs.items()):
        raise RuntimeError('Inputs changed during evaluation')
    write(args.output/'technical_receipt.json', dict(
        task_id='PHD-P2-AB-V2-C-EVALUATION', status='REFERENCE_ONLY_DIAGNOSTIC_COMPLETE',
        scientific_verdict=None, arms=len(rows), reference_points=len(reference),
        exact_query_workers=4, identical_xyz_metric_cache_hits=cache_hits,
        excluded_arms=args.exclude_arm,
        input_sha256=inputs, source_sha256={str(p.relative_to(REPO)): sha(p) for p in sources},
        reference_manifest=reference_meta,
        git_head=os.environ.get('JBGS_SOURCE_GIT_HEAD'), container_image=os.environ.get('JBGS_CONTAINER_IMAGE_ID'),
        elapsed_seconds=time.monotonic()-start,
    ))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--common', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--b-root', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--exclude-arm', action='append', default=[])
    main(parser.parse_args())

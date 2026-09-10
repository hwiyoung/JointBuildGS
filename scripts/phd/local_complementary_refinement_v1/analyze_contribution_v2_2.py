"""Additive, frozen-snapshot LC contribution diagnosis; never writes runtime inputs."""
import argparse
import csv
import hashlib
import json
import platform
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import scipy
from scipy.spatial import cKDTree


def read(path):
    return json.loads(path.read_text())


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def stats(values):
    values = np.asarray(values, dtype=float)
    require(values.ndim == 1 and np.isfinite(values).all(), 'Invalid distances; do not silently drop missingness')
    if not len(values):
        return dict(count=0, mean_m=None, median_m=None, p90_m=None, rmse_m=None)
    return dict(count=len(values), mean_m=float(values.mean()), median_m=float(np.median(values)),
                p90_m=float(np.quantile(values, .9)), rmse_m=float(np.sqrt(np.mean(values ** 2))))


def paired(before, after, epsilon):
    require(before.shape == after.shape and before.size > 0, 'Paired populations differ or are empty')
    delta = after - before
    require(np.isfinite(delta).all(), 'Nonfinite paired change')
    fractions = [float(np.mean(delta < -epsilon)), float(np.mean(np.abs(delta) <= epsilon)), float(np.mean(delta > epsilon))]
    require(abs(sum(fractions) - 1) < 1e-12, 'Paired partition failed')
    return dict(count=len(delta), mean_delta_m=float(delta.mean()), median_delta_m=float(np.median(delta)),
                median_absolute_delta_m=float(np.median(np.abs(delta))), improved_gt_01m=fractions[0],
                within_01m=fractions[1], worsened_gt_01m=fractions[2])


def write_csv(path, rows):
    with path.open('x') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    for key in ['task', 'parent', 'config', 'output']:
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    require(Path('/.dockerenv').exists(), 'Docker required')
    start = time.time()
    config = read(args.config)
    require(config['scientific_verdict'] is None, 'Scientific verdict must remain null')
    out = args.output / ('attempt_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    inputs = {}
    checks = []

    def bind(path, expected=None):
        digest = sha(path)
        require(expected is None or digest == expected, 'Hash mismatch: ' + str(path))
        inputs[str(path)] = dict(path=str(path), sha256=digest)
        return digest

    bind(args.config)
    bind(Path(__file__))
    packet = args.task / 'review_site' / config['review_packet']
    bind(packet / 'receipt.json', config['review_receipt_sha256'])
    receipt = read(packet / 'receipt.json')
    require(receipt['status'] == 'PASS_REVIEW_PACKET', 'Verified packet required')
    for name in ['data.json', 'sources.json']:
        bind(packet / name, next(x['sha256'] for x in receipt['outputs'] if x['path'] == name))
    data = read(packet / 'data.json')
    require(data['evaluated_conditions'] == config['expected_local_conditions'], 'Unexpected condition population')
    policy = read(packet / 'sources.json')
    evals = {sha(path): path.parent for path in (args.task / 'evaluation').glob('attempt_*/receipt.json')}
    metrics, changes, geometry, figure_records, profiles = [], [], [], [], []
    for bundle in policy['bundles']:
        summary = args.task / bundle['summary']
        sr = read(summary / 'receipt.json')
        expected_sr = next(x['sha256'] for x in receipt['inputs'] if x['path'].endswith(bundle['summary'] + '/receipt.json'))
        bind(summary / 'receipt.json', expected_sr)
        ep = evals[next(x['sha256'] for x in sr['inputs'] if x['path'] == '/evaluation/receipt.json')]
        bind(ep / 'receipt.json')
        er = read(ep / 'receipt.json')
        sealed = {x['path']: x['sha256'] for x in er['outputs']}
        gp = summary / 'geometry_all_thresholds_raw_post.csv'
        bind(gp, next(x['sha256'] for x in sr['outputs'] if x['path'] == gp.name))
        with gp.open() as stream:
            old_geometry = list(csv.DictReader(stream))
        for region in bundle['regions']:
            selected = [x for x in data['rows'] if x['region'] == region]
            mp = ep / region / selected[0]['condition'] / 'raw_metrics.json'
            bind(mp, sealed[str(mp.relative_to(ep))])
            bounds = np.asarray(read(mp)['bounds_half_open'])
            candidates = ['ANCHOR'] + [f'D{d}_P{mode}' for d in ['005', '0005', '0'] for mode in ['native', 'release']] + [x['condition'] for x in selected]
            for kind in ['raw', 'post']:
                arrays = {}
                reference = ref_ids = None
                for candidate in candidates:
                    if candidate.startswith('LC_'):
                        path = ep / region / candidate / (kind + '_distances.npz')
                        expected = sealed[str(path.relative_to(ep))]
                    else:
                        parent_id = ('D005_Pnative.anchor_512.' if candidate == 'ANCHOR' else candidate + '.mesh_512.') + kind
                        path = args.parent / 'evaluation/geometry' / region / parent_id / 'sample0.1_reference0.1.npz'
                        hashes = {x['sha256'] for x in er['inputs'] if x['path'].endswith('/' + str(path.relative_to(args.parent)))}
                        require(len(hashes) == 1, 'Unsealed parent cache')
                        expected = hashes.pop()
                    bind(path, expected)
                    with np.load(path, allow_pickle=False) as z:
                        ref = z['reference_points']
                        ids = z['reference_original_indices']
                        rd = z['reference_to_triangle_distance']
                        pd = z['prediction_to_reference_distance']
                        pred = z['prediction_surface_samples']
                    if reference is None:
                        reference, ref_ids = ref, ids
                    require(np.array_equal(ref, reference) and np.array_equal(ids, ref_ids), 'Reference XYZ/ID/order mismatch')
                    require(len(rd) == len(ref) and len(pd) == len(pred), 'Distance membership mismatch')
                    require(np.isfinite(pred).all() and np.isfinite(ref).all() and (rd >= 0).all() and (pd >= 0).all(), 'Invalid geometry')
                    checks.append('identity-and-distance-shapes:' + region + '/' + kind + '/' + candidate)
                    arrays[candidate] = dict(rd=rd, pd=pd, pred=pred)
                    for threshold in [.1, .2, .25, .5, 1., 2.]:
                        p, r = float(np.mean(pd < threshold)), float(np.mean(rd < threshold))
                        f = 2*p*r/(p+r) if p+r else 0.
                        old = next(x for x in old_geometry if x['region'] == region and x['candidate'] == candidate and x['mesh_kind'] == kind and float(x['threshold_m']) == threshold)
                        require(all(abs(value - float(old[key])) < 1e-12 for key, value in [('precision', p), ('recall', r), ('f1', f)]), 'Sealed metric reproduction failed')
                        geometry.append(dict(region=region, candidate=candidate, mesh_kind=kind, threshold_m=threshold, precision=p, recall=r, f1=f))
                    domains = [('whole', np.ones(len(ref), bool), np.ones(len(pred), bool))]
                    if kind == 'raw':
                        for axis in [0, 1]:
                            center = bounds[axis].mean()
                            domains.append(('band_' + 'XY'[axis], np.abs(ref[:, axis]-center) < config['section_width_m']/2,
                                            np.abs(pred[:, axis]-center) < config['section_width_m']/2))
                    for domain, rs, ps in domains:
                        for direction, values in [('ref_to_full_mesh_3d', rd[rs]), ('sample_to_full_ref_3d', pd[ps])]:
                            metrics.append(dict(region=region, candidate=candidate, mesh_kind=kind, domain=domain, direction=direction, **stats(values)))
                        if domain != 'whole':
                            axis = 'XY'.index(domain[-1]); horizontal = 1-axis
                            require(rs.any() and ps.any(), 'Missing projected support must be explicit')
                            r2 = ref[rs][:, [horizontal, 2]]; p2 = pred[ps][:, [horizontal, 2]]
                            # Both directions retained. These are projection diagnostics, not semantic or signed-height errors.
                            for direction, values in [('ref_to_band_samples_2d', cKDTree(p2).query(r2, workers=2)[0]),
                                                      ('band_samples_to_ref_2d', cKDTree(r2).query(p2, workers=2)[0])]:
                                metrics.append(dict(region=region, candidate=candidate, mesh_kind=kind, domain=domain, direction=direction, **stats(values)))
                pairs = [('matched_LC', row['parent_condition'], row['condition']) for row in selected]
                pairs += [('global_prior_reduction', f'D005_P{mode}', f'D{d}_P{mode}') for mode in ['native', 'release'] for d in ['0005', '0']]
                pairs += [('LC_vs_weak_global', f'D{d}_P{row["protection"]}', row['condition']) for row in selected for d in ['0005', '0'] if row['parent_condition'] != f'D{d}_P{row["protection"]}']
                domains = [('whole', np.ones(len(reference), bool))]
                if kind == 'raw':
                    domains += [('band_' + 'XY'[axis], np.abs(reference[:, axis]-bounds[axis].mean()) < config['section_width_m']/2) for axis in [0, 1]]
                for contrast, before, after in pairs:
                    for domain, rs in domains:
                        changes.append(dict(region=region, mesh_kind=kind, contrast=contrast, before=before, after=after, domain=domain,
                                            **paired(arrays[before]['rd'][rs], arrays[after]['rd'][rs], config['paired_change_description_m'])))
                if kind == 'raw':
                    for mode in ['native', 'release']:
                        names = ['ANCHOR'] + [f'D{d}_P{mode}' for d in ['005', '0005', '0']] + [f'LC_D{d}_P{mode}' for d in ['005', '0005', '0']]
                        fig, axes = plt.subplots(2, 7, figsize=(30, 10), sharex='row', sharey=True, layout='constrained')
                        for axis in [0, 1]:
                            horizontal = 1-axis; center = bounds[axis].mean()
                            rs = np.abs(reference[:, axis]-center) < config['section_width_m']/2
                            for col, name in enumerate(names):
                                ax = axes[axis, col]
                                ax.scatter(reference[rs, horizontal], reference[rs, 2], s=2, c='#555555', marker='.', rasterized=True)
                                n = None
                                if name in arrays:
                                    pred = arrays[name]['pred']; ps = np.abs(pred[:, axis]-center) < config['section_width_m']/2; n = int(ps.sum())
                                    ax.scatter(pred[ps, horizontal], pred[ps, 2], s=3, c='#2E6FBB', marker='x', linewidths=.3, rasterized=True)
                                    for point in pred[ps]:
                                        profiles.append(dict(region=region, protection=mode, candidate=name, fixed_axis='XY'[axis], x_m=float(point[0]), y_m=float(point[1]), z_m=float(point[2])))
                                else:
                                    ax.text(.05, .5, 'NOT EVALUATED\nin this snapshot', transform=ax.transAxes)
                                label = name.replace('_P' + mode, '').replace('ANCHOR', 'Anchor8k')
                                ax.set_title(f'{label}\n{"XY"[axis]}={center:.2f}; ref={rs.sum():,}; surface={n}', fontsize=10)
                                ax.set(xlim=bounds[horizontal], ylim=bounds[2], xlabel='XY'[horizontal] + ' (m)', ylabel='Z (m)')
                                ax.set_aspect('equal', adjustable='box'); ax.grid(color='#DDDDDD', linewidth=.5)
                                figure_records.append(dict(region=region, protection=mode, candidate=name, axis='XY'[axis], reference_count=int(rs.sum()), prediction_count=n, center_m=float(center)))
                        fig.suptitle(f'{region} / {mode} / same raw TSDF512 bounds, axes and 0.5 m sample bands\nGray: observed UAS; blue: all predicted band samples. Not mesh-plane intersections; reference gaps unassessed.', fontsize=14)
                        fig.savefig(out / f'{region}_{mode}_sections.png', dpi=150); plt.close(fig)
                del arrays
        print('ANALYZED ' + ','.join(bundle['regions']), flush=True)
    for name, rows in [('continuous_metrics.csv', metrics), ('paired_continuous_changes.csv', changes), ('all_geometry.csv', geometry), ('section_samples.csv', profiles)]:
        write_csv(out / name, rows)
    (out / 'figure_records.json').write_text(json.dumps(figure_records, indent=2) + '\n')
    shutil.copyfile(args.config, out / args.config.name)
    shutil.copyfile(Path(__file__), out / Path(__file__).name)
    result = dict(status='PASS_SEALED_CONTINUOUS_CONTRIBUTION_DIAGNOSTIC', scientific_verdict=None,
                  evaluated_local_conditions=data['evaluated_conditions'], config=config, checks=checks,
                  geometry_reproduction_checks=len(geometry), metric_rows=len(metrics), paired_rows=len(changes),
                  figure_count=6, reference_correspondence='exact original IDs, XYZ and order; no semantic surface identity claim',
                  versions=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__, matplotlib=matplotlib.__version__),
                  wall_seconds=time.time()-start, inputs=list(inputs.values()),
                  outputs=[dict(path=str(p.relative_to(out)), sha256=sha(p)) for p in sorted(out.rglob('*')) if p.is_file()])
    (out / 'receipt.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(output=str(out), status=result['status'], local_count=data['evaluated_conditions'], metric_rows=len(metrics))))


if __name__ == '__main__':
    main()

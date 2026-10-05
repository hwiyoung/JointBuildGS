"""Find input conflicts with residual output discrepancy. CPU Docker only.

Uses frozen point identities and both directions of the prior/current relation.
All search bands are posthoc development diagnostics, never training masks.
"""
import argparse
import csv
import json
import platform
import sys
import time
import traceback
import warnings
from pathlib import Path

import numpy as np
import scipy
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

sys.path.append(str(Path(__file__).resolve().parents[1] / 'r1r5_comparison_v1'))
from analyze_final_surfaces import read, write, sha, distances
import matplotlib.pyplot as plt


def groups(xyz, radius):
    pairs = cKDTree(xyz).query_pairs(radius, output_type='ndarray')
    graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])),
                       shape=(len(xyz), len(xyz)))
    _, labels = connected_components(graph, directed=False)
    return labels


def number_stats(values):
    values = np.asarray(values)
    values = values[np.isfinite(values)]
    if not len(values):
        return dict(n=0, median=None, p90=None)
    return dict(n=len(values), median=float(np.median(values)),
                p90=float(np.quantile(values, .9)))


def self_check():
    assert groups(np.array([[0., 0, 0], [1, 0, 0], [8, 0, 0]]), 2).tolist() == [0, 0, 1]
    xyz = np.array([[-10, -10, 0], [10, -10, 0], [10, 10, 0], [-10, 10, 0]], np.float32)
    tri = np.array([[0, 1, 2], [0, 2, 3]], np.uint32)
    d, _ = distances(xyz, tri, np.array([[0, 0, 2], [1, 1, -.3]]), 10)
    assert np.allclose(d, [2., .3], atol=1e-6)
    print('PASS analytic surface distances and disconnected component grouping', flush=True)


def main(cfg, out):
    started = time.time()
    art = Path(cfg['artifact_root']); root = art / cfg['comparison_relative']
    ana = root / cfg['analysis']; frozen_receipt = read(ana / 'receipt.json')
    assert frozen_receipt['status'] == 'PASS_PAIRED_INPUT_DISTANCE_DIAGNOSTIC'
    angle = np.deg2rad(cfg['object_axis_angle_deg'])
    basis = np.array([[np.cos(angle), np.sin(angle)], [np.sin(angle), -np.cos(angle)]])
    all_components = []; counts = []; sensitivity = []; bindings = {}
    helper = Path(sys.modules['analyze_final_surfaces'].__file__)
    bindings[str(helper)] = sha(helper)
    for region in cfg['regions']:
        evdir = art / cfg['r1_audit_relative'] if region == 'R1' else root / region / 'audit/result'
        evpath = evdir / 'surface_evidence.npz'; raypath = evdir / 'per_view_relations.npz'
        er = read(evdir / 'receipt.json')
        for p in [evpath, raypath]:
            digest = sha(p); assert digest == er['files'][p.name], str(p)
            bindings[str(p)] = digest
        e = np.load(evpath); rays = np.load(raypath)
        path = ana / (region + '_paired_samples.npz'); bindings[str(path)] = sha(path)
        summary = read(ana / (region + '_summary.json'))['metadata']
        # Bind the saved metric inputs to their original receipt and immutable meshes.
        assert summary == next(x for x in frozen_receipt['regions'] if x['region'] == region)
        for name, digest in summary['input_bindings'].items():
            assert sha(name) == digest, name
            bindings[name] = digest
        for model in summary['models'].values():
            assert sha(model['path']) == model['sha256'], model['path']
        a = np.load(path); source = a['source'] == 0; xyz = e['mvs_xyz']
        assert np.array_equal(a['xyz'][source], xyz)
        assert np.array_equal(e['names'], rays['names'])
        assert np.array_equal((rays['mvs'] > 0).sum(0), e['mvs_view_count'])
        zp = art / cfg['r1_review_relative'] / 'config.json' if region == 'R1' else root / region / 'review_zones.json'
        zones = {int(z['id'][1:]): z for z in read(zp)['zones']}
        bindings[str(zp)] = sha(zp)
        zone = a['zone'][source]; rel = e['mvs_relation']
        uvz = np.column_stack([xyz[:, :2] @ basis.T, xyz[:, 2]])
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            gap = np.nanmedian(rays['mvs_depth_gap'], axis=0)
        consistent = np.isin(rel, cfg['inherited_relation_labels'])
        assert np.all(e['mvs_view_count'][consistent] >= cfg['minimum_support_views'])
        assert np.all(e['mvs_camera_span_m'][consistent] >= cfg['minimum_camera_span_m'])
        assert np.all(e['mvs_dominant_fraction'][consistent] >= cfg['minimum_dominant_fraction'])
        assert np.all(np.abs(gap[consistent]) > cfg['source_gap_camera_z_m'])
        prior_meta = read(root / cfg['uas_analysis'] / (region + '_prior_reference.json'))
        pp = Path(prior_meta['source']); assert sha(pp) == prior_meta['sha256']
        bindings[str(pp)] = prior_meta['sha256']
        p = np.load(pp)
        # Same MVS query to prior and output surfaces; no mixed camera-Z/3D ratios.
        dp, _ = distances(p['xyz'].astype(np.float32), p['faces'].astype(np.uint32), xyz, np.inf)
        ds = {b: a['distance_' + b][source] for b in [*cfg['branches'], 'local_prior0']}
        for branch, d in ds.items():
            replay = np.minimum(np.linalg.norm(xyz.astype(float) - a['closest_' + branch][source], axis=1), cfg['distance_cap_m'])
            assert np.allclose(replay, d, atol=1e-7), (region, branch)
        masks = {}
        for branch in cfg['branches']:
            residual = consistent & (ds[branch] > cfg['residual_surface_m'])
            ratio = ds[branch] / np.maximum(dp, 1e-9)
            ratio_valid = (dp >= cfg['prior_surface_distance_min_m']) & (ds[branch] < cfg['distance_cap_m'])
            little = residual & ratio_valid & (ratio >= cfg['little_gain_remaining_fraction'])
            masks[branch + '_residual'] = residual
            masks[branch + '_little_gain'] = little
            counts.append(dict(region=region, branch=branch, input_samples=len(xyz),
                conflict_samples=int(consistent.sum()), residual_samples=int(residual.sum()),
                little_gain_samples=int(little.sum()), censored_residual=int((residual & (ds[branch] >= cfg['distance_cap_m'])).sum()),
                near_mvs_after_conflict=int((consistent & (ds[branch] <= cfg['residual_surface_m'])).sum())))
            for threshold in cfg['residual_sensitivity_m']:
                for fraction in cfg['remaining_fraction_sensitivity']:
                    sensitivity.append(dict(region=region, branch=branch, residual_m=threshold,
                        remaining_fraction=fraction, n=int((consistent & (ds[branch] > threshold) & ratio_valid & (ratio >= fraction)).sum())))
            for category, chosen in [('residual', residual), ('little_gain', little)]:
                for zi in np.unique(zone):
                    for direction in cfg['inherited_relation_labels']:
                        indices = np.flatnonzero(chosen & (zone == zi) & (rel == direction))
                        if not len(indices): continue
                        labels = groups(xyz[indices], cfg['component_link_radius_m'])
                        for label in np.unique(labels):
                            ids = indices[labels == label]
                            if len(ids) < cfg['minimum_component_points']: continue
                            q = uvz[ids]; centroid = xyz[ids].mean(0)
                            values = np.linalg.eigvalsh(np.cov(xyz[ids].T, bias=True))
                            row = dict(id='', region=region, branch=branch, category=category,
                                zone=f'Z{zi:02}', zone_name=zones[int(zi)]['name'], context=zones[int(zi)]['kind'],
                                direction='PRIOR_IN_FRONT' if direction == 2 else 'PRIOR_BEHIND', n=len(ids),
                                sample_indices=ids.tolist(), source_rows=e['mvs_source_rows'][ids].tolist(),
                                center_uvz=np.median(q, axis=0).tolist(), bounds_uvz=[q.min(0).tolist(), q.max(0).tolist()],
                                centroid_epsg25832=(centroid + cfg['world_shift']).tolist(),
                                gap_camera_z=number_stats(gap[ids]), prior_surface=number_stats(dp[ids]),
                                output_surface={b: number_stats(d[ids]) for b, d in ds.items()},
                                remaining_fraction=number_stats(ratio[ids]), views=number_stats(e['mvs_view_count'][ids]),
                                camera_span_m=number_stats(e['mvs_camera_span_m'][ids]),
                                plane_rms_m=float(np.sqrt(max(0., values[0]))),
                                scientific_verdict=None)
                            all_components.append(row)
        np.savez_compressed(out / (region + '_sample_diagnostic.npz'), xyz=xyz, uvz=uvz,
            source_rows=e['mvs_source_rows'], zone=zone, relation=rel, gap_camera_z=gap,
            prior_surface_distance=dp, views=e['mvs_view_count'], camera_span=e['mvs_camera_span_m'],
            **{'distance_' + k: v for k, v in ds.items()}, **masks)
        fig, axs = plt.subplots(1, 2, figsize=(16, 7), sharex=True, sharey=True)
        for ax, branch in zip(axs, cfg['branches']):
            ax.scatter(uvz[:, 0], uvz[:, 1], c=e['mvs_rgb'] / 255., s=1, alpha=.5)
            for mask, color, title in [(consistent, '#338fcc', 'prior/MVS conflict'),
                    (masks[branch + '_residual'], '#ec8c22', 'output residual >0.5m'),
                    (masks[branch + '_little_gain'], '#d41448', 'remaining >=80%')]:
                ax.scatter(uvz[mask, 0], uvz[mask, 1], c=color, s=5, label=title)
            for zid, z in zones.items():
                if zid == 0: continue
                xy = np.array(z['polygon']); ax.plot(*np.vstack([xy, xy[0]]).T, lw=.5, color='.3')
                ax.text(*xy.mean(0), z['id'], fontsize=7)
            ax.set_aspect('equal'); ax.set_title(region + ' / ' + branch.upper() + '-GeoGS')
            ax.set_xlabel('object u [m]'); ax.set_ylabel('object v [m]'); ax.legend(fontsize=8)
        axs[0].invert_yaxis()
        fig.suptitle('Input-based development search. Red is a review candidate, not weight causality or ground truth.')
        fig.tight_layout(); fig.savefig(out / (region + '_map.png'), dpi=145); plt.close(fig)
        print(region, json.dumps(counts[-2:]), flush=True)
    all_components.sort(key=lambda x: (x['category'], x['branch'], x['region'], -x['n'], x['zone'], x['center_uvz']))
    for i, row in enumerate(all_components, 1): row['id'] = f'W{i:03}'
    write(out / 'components.json', dict(scientific_verdict=None, components=all_components))
    for filename, rows in [('counts.csv', counts), ('sensitivity.csv', sensitivity)]:
        with (out / filename).open('w') as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    write(out / 'receipt.json', dict(status='PASS_INPUT_CONFLICT_RESIDUAL_SEARCH', scientific_verdict=None,
        config=cfg, counts=counts, component_count=len(all_components), input_sha256=bindings,
        script_sha256=sha(__file__), elapsed_seconds=time.time()-started,
        versions=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__),
        selection_reference_used=False, source_accuracy_certified=False, weights_changed=False,
        global_weight_sweep_performed=False, output_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != 'receipt.json'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--config', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args(); output = Path(args.output); output.mkdir(parents=True, exist_ok=False)
    try:
        self_check(); main(read(args.config), output)
    except Exception:
        write(output / 'failure.json', dict(status='FAIL', scientific_verdict=None, traceback=traceback.format_exc()))
        raise

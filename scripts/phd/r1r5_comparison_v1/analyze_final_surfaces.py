"""Matched input-sample distances to final native TSDF meshes; not GT accuracy."""
import argparse
import csv
import gc
import hashlib
import json
import platform
import time
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d


def read(p):
    return json.loads(Path(p).read_text())


def write(p, obj):
    p = Path(p)
    q = p.with_suffix('.tmp')
    q.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False))
    q.replace(p)


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def mesh_arrays(path):
    """Read the exact Open3D binary triangle schema without object-list allocation."""
    types = {'double': '<f8', 'float': '<f4', 'uchar': 'u1', 'uint': '<u4', 'int': '<i4'}
    fields = []; section = None; face_type = None
    with path.open('rb') as f:
        while True:
            line = f.readline().decode('ascii').strip(); words = line.split()
            if line == 'end_header':
                break
            if words[:1] == ['format']:
                assert words[1] == 'binary_little_endian'
            if words[:1] == ['element']:
                section = words[1]
                if section == 'vertex': nv = int(words[2])
                elif section == 'face': nf = int(words[2])
                else: raise ValueError('Unsupported PLY element ' + section)
            if words[:1] == ['property']:
                if section == 'vertex': fields.append((words[2], types[words[1]]))
                else:
                    assert words[1:3] == ['list', 'uchar'] and words[4] == 'vertex_indices'
                    assert face_type is None
                    face_type = np.dtype([('count', 'u1'), ('indices', types[words[3]], (3,))])
        offset = f.tell()
    vd = np.dtype(fields)
    v = np.memmap(path, mode='r', dtype=vd, offset=offset, shape=(nv,))
    faces = np.memmap(path, mode='r', dtype=face_type, offset=offset + nv * vd.itemsize, shape=(nf,))
    assert path.stat().st_size == offset + nv * vd.itemsize + nf * face_type.itemsize
    assert np.all(faces['count'] == 3)
    return v, faces


def cropped_mesh(path, query, margin):
    v, faces = mesh_arrays(path)
    lo = query[:, :2].min(0) - margin; hi = query[:, :2].max(0) + margin
    selected = []
    for start in range(0, len(faces), 250000):
        tri = faces['indices'][start:start + 250000]
        x = v['x'][tri]; y = v['y'][tri]
        mask = (x.max(1) >= lo[0]) & (x.min(1) <= hi[0]) & (y.max(1) >= lo[1]) & (y.min(1) <= hi[1])
        if mask.any(): selected.append(np.asarray(tri[mask], dtype=np.int64))
    tri = np.concatenate(selected)
    ids, inverse = np.unique(tri, return_inverse=True)
    xyz = np.column_stack([v[k][ids] for k in 'xyz']).astype(np.float32)
    triangles = inverse.reshape(-1, 3).astype(np.uint32)
    return xyz, triangles, dict(original_vertices=len(v), original_triangles=len(faces),
                                queried_vertices=len(ids), queried_triangles=len(tri))


def distances(xyz, triangles, points, cap):
    scene = o3d.t.geometry.RaycastingScene(nthreads=4)
    scene.add_triangles(o3d.core.Tensor(xyz), o3d.core.Tensor(triangles))
    ds = []; closest = []
    for start in range(0, len(points), 20000):
        p = points[start:start + 20000].astype(np.float32)
        out = scene.compute_closest_points(o3d.core.Tensor(p), nthreads=4)
        q = out['points'].numpy()
        d = np.linalg.norm(p.astype(float) - q.astype(float), axis=1)
        assert np.isfinite(d).all()
        ds.append(np.minimum(d, cap)); closest.append(q)
    del scene
    return np.concatenate(ds), np.concatenate(closest)


def stats(x):
    if not len(x): return dict(n=0)
    return dict(n=len(x), median_m=float(np.median(x)), p90_m=float(np.quantile(x, .9)),
                mean_capped_m=float(x.mean()), within_05m_percent=float(100 * (x <= .5).mean()),
                within_1m_percent=float(100 * (x <= 1).mean()), within_2m_percent=float(100 * (x <= 2).mean()))


def comparison(base, other):
    d = other - base
    if not len(d): return dict(paired_n=0)
    return dict(paired_n=len(d), median_distance_change_m=float(np.median(d)),
                mean_distance_change_m=float(d.mean()),
                closer_over_01m_percent=float(100 * (d < -.1).mean()),
                farther_over_01m_percent=float(100 * (d > .1).mean()),
                within_1m_change_pp=float(100 * ((other <= 1).mean() - (base <= 1).mean())))


def load_queries(art, root, region, cfg):
    if region == 'R1':
        folder = art / cfg['r1_review_relative']; path = folder / 'surface_judgments.npz'; a = np.load(path)
        points = a['xyz']; source = a['source']; judgment = a['judgment']; zone = a['zone']
        # R1 stores the numeric Z suffix, while its polygon application order differs.
        zones = sorted(read(folder / 'config.json')['zones'], key=lambda z: int(z['id'][1:]))
        counts_path = folder / 'zone_judgments.json'
        for z in read(counts_path)['zones']:
            zid = int(z['id'][1:])
            assert int(((zone == zid) & (source == 0)).sum()) == z['mvs_samples']
            assert int(((zone == zid) & (source == 1)).sum()) == z['prior_samples']
        bindings = {str(p): sha(p) for p in [path, folder / 'config.json', counts_path]}
    else:
        path = root / region / 'audit/result/surface_evidence.npz'; jp = root / region / 'review/judgments.npz'
        a = np.load(path); j = np.load(jp)
        points = np.concatenate([a['mvs_xyz'], a['prior_xyz']])
        source = np.concatenate([np.zeros(len(a['mvs_xyz']), np.uint8), np.ones(len(a['prior_xyz']), np.uint8)])
        judgment = np.concatenate([j['mvs_judgment'], j['prior_judgment']])
        zone = np.concatenate([j['mvs_zone'], j['prior_zone']])
        zp = root / region / 'review_zones.json'; zones = read(zp)['zones']
        bindings = {str(p): sha(p) for p in [path, jp, zp]}
    assert len(points) == len(source) == len(judgment) == len(zone)
    assert [z['id'] for z in zones] == ['Z%02d' % i for i in range(len(zones))]
    assert np.isfinite(points).all()
    return points, source, judgment, zone, zones, bindings


def plot_region(out, region, points, source, zones, branch_distance):
    theta = np.deg2rad(70); basis = np.array([[np.cos(theta), np.sin(theta)], [np.sin(theta), -np.cos(theta)]])
    uv = points[:, :2] @ basis.T
    fig, axs = plt.subplots(2, 3, figsize=(16, 10), sharex=True, sharey=True)
    for row in range(2):
        sel = source == row; xy = uv[sel]
        for col, branch in enumerate(['mvs', 'da3', 'local_prior0']):
            ax = axs[row, col]
            val = branch_distance[branch][sel]
            if col:
                val = val - branch_distance['mvs'][sel]; cmap = 'coolwarm'; vmin = -1; vmax = 1
            else: cmap = 'viridis'; vmin = 0; vmax = 2
            sc = ax.scatter(xy[:, 0], xy[:, 1], c=val, cmap=cmap, vmin=vmin, vmax=vmax, s=2, linewidths=0, rasterized=True)
            for z in zones:
                poly = np.array(z['polygon']); ax.plot(*np.vstack([poly, poly[0]]).T, color='0.35', lw=.5)
                if z['id'] != 'Z00': ax.text(*poly.mean(0), z['id'], fontsize=7, ha='center', bbox=dict(facecolor='white', alpha=.65, edgecolor='none', pad=1))
            ax.set_aspect('equal'); ax.set_title(('MVS samples' if row == 0 else 'Prior samples') + ' / ' + branch)
            ax.set_xlabel('object u [m]'); ax.set_ylabel('object v [m]'); fig.colorbar(sc, ax=ax, shrink=.7, label='distance [m]' if col == 0 else 'distance change vs MVS control [m]')
    for ax in axs[1]: ax.invert_yaxis()
    fig.suptitle(region + ': identical input samples to native TSDF surface; not independent accuracy\nDelta: blue = closer to this input; red = farther. Query distances capped at 10 m.')
    fig.tight_layout(); fig.savefig(out / (region + '_input_distance.png'), dpi=140); plt.close(fig)


def self_test():
    xyz = np.array([[-20, -20, 0], [20, -20, 0], [20, 20, 0], [-20, 20, 0]], np.float32)
    tri = np.array([[0, 1, 2], [0, 2, 3]], np.uint32)
    q = np.array([[0, 0, 2], [1, 2, -.25]], np.float32)
    d, _ = distances(xyz, tri, q, 10)
    assert np.allclose(d, [2, .25], atol=1e-6)
    c = comparison(np.array([2., .2]), np.array([1., .4]))
    assert c['closer_over_01m_percent'] == 50 and c['farther_over_01m_percent'] == 50
    row = dict(region='test', **stats(d), **c)
    assert row['n'] == row['paired_n'] == 2
    print('PASS analytic plane distances and paired improvement/degradation accounting')


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--config', type=Path); ap.add_argument('--output', type=Path); ap.add_argument('--self-test', action='store_true'); args = ap.parse_args()
    if args.self_test: self_test(); return
    cfg = read(args.config); art = Path(cfg['artifact_root']); root = art / cfg['attempt_relative']; out = args.output
    config = read(root / 'config.json'); legacy = art / config['r1_run_relative']; overrides = read(root / 'execution/artifact_overrides.json')
    all_rows = []; region_info = []; started = time.time()
    write(out / 'bound_overrides.json', overrides)
    try:
        for region in cfg['regions']:
            points, source, judgment, zone, zones, bindings = load_queries(art, root, region, cfg)
            ds = {}; nearest = {}; models = {}
            for branch in cfg['branches']:
                write(out / 'status.json', dict(state='RUNNING', region=region, branch=branch, elapsed_seconds=time.time()-started, scientific_verdict=None))
                if region == 'R1' and branch == 'mvs':
                    folder = legacy / read(legacy / 'mesh_recovery.json')['relative'] / 'extract_final'
                else: folder = root / overrides.get(region, {}).get('extract_' + branch, region + '/extract_' + branch)
                recpath = folder / 'receipt.json'; rec = read(recpath); assert rec['status'] == 'PASS'
                surface = rec['surfaces']['fuse.ply']; path = folder / surface['path']; digest = sha(path)
                assert digest == surface['sha256'], str(path)
                xyz, tris, sizes = cropped_mesh(path, points, cfg['distance_cap_m'])
                ds[branch], nearest[branch] = distances(xyz, tris, points, cfg['distance_cap_m'])
                models[branch] = dict(path=str(path), sha256=digest, receipt_sha256=sha(recpath), **sizes)
                print(region, branch, sizes, 'seconds', round(time.time()-started, 1), flush=True)
                del xyz, tris; gc.collect()
            np.savez_compressed(out / (region + '_paired_samples.npz'), xyz=points, source=source, judgment=judgment, zone=zone,
                                **{'distance_' + k: v for k, v in ds.items()}, **{'closest_' + k: v for k, v in nearest.items()})
            rows = []
            for zid in [-1] + list(range(len(zones))):
                for src in [0, 1]:
                    for kind in [-1, 0, 1, 2, 3, 4]:
                        sel = (source == src) & ((zone == zid) if zid >= 0 else True) & ((judgment == kind) if kind >= 0 else True)
                        if not sel.any(): continue
                        for branch in cfg['branches']:
                            rows.append(dict(region=region, zone='ALL' if zid < 0 else zones[zid]['id'], zone_name='ALL' if zid < 0 else zones[zid]['name'],
                                             source='mvs' if src == 0 else 'prior', judgment=kind, branch=branch,
                                             **stats(ds[branch][sel]), **comparison(ds['mvs'][sel], ds[branch][sel])))
            all_rows.extend(rows)
            masks = read(root / region / 'masks/receipt.json')
            info = dict(region=region, input_bindings=bindings, models=models, zones=zones,
                        masked_pixels=masks['total_pixels'], masked_views=masks['contributing_views'],
                        query_count=len(points), input_sample_file=region + '_paired_samples.npz')
            region_info.append(info)
            write(out / (region + '_summary.json'), dict(status='PASS_PAIRED_INPUT_DISTANCE_DIAGNOSTIC', scientific_verdict=None, metadata=info, rows=rows))
            plot_region(out, region, points, source, zones, ds)
            del points, source, judgment, zone, ds, nearest; gc.collect()
        with (out / 'zone_metrics.csv').open('w') as f:
            w = csv.DictWriter(f, fieldnames=list(all_rows[0])); w.writeheader(); w.writerows(all_rows)
        write(out / 'receipt.json', dict(status='PASS_PAIRED_INPUT_DISTANCE_DIAGNOSTIC', scientific_verdict=None, regions=region_info,
              rows=len(all_rows), elapsed_seconds=time.time()-started, config=cfg, script_sha256=sha(__file__),
              versions=dict(python=platform.python_version(), numpy=np.__version__, open3d=o3d.__version__),
              reference_used=False, interpretation='Input agreement only; fixed input-reviewed groups, same samples for every branch. One-way distance can miss extra surfaces. No GT accuracy or source authority claim. Distances >=10m censored; no use for training or mask revision.'))
        write(out / 'status.json', dict(state='COMPLETE', scientific_verdict=None, elapsed_seconds=time.time()-started))
    except Exception:
        import traceback
        write(out / 'failure.json', dict(status='FAIL', scientific_verdict=None, error=traceback.format_exc()))
        write(out / 'status.json', dict(state='FAILED', scientific_verdict=None, elapsed_seconds=time.time()-started))
        raise


if __name__ == '__main__': main()

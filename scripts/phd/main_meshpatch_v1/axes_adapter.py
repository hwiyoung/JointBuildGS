"""Reuse AXES71-v2 functions unchanged, with its original input mounts."""
import sys
from pathlib import Path
sys.path.insert(0, '/repo/scripts/phd/main_axes71_v2')
import ax_common as ax
import ax_arrays as aa
import a2x_sample as axs
import a3_metrics as a3
import a4_axes as a4
import dm_common as dm
from src.phd.metrics_v3.surface import MeshScene
import numpy as np
from scipy.spatial import cKDTree
MP = Path('/mp')


def inputs(site, prior):
    gt = dm.SiteGT(site)
    u = dm.Unit(site, prior, gt)
    normals = axs.normals_full(site, gt)
    ref = axs.Ref(gt.Gb, normals[0][gt.bs_idx])
    ref_b = None
    if site == 'B0_b10':
        mask = gt.G['use_gt_primary'].astype(bool)
        points, nn = gt.X[1][mask], normals[1][mask]
        keep = gt.in_cells(points)
        ref_b = axs.Ref(np.vstack([gt.Gb, points[keep]]), np.vstack([normals[0][gt.bs_idx], nn[keep]]))
    cells = aa.cells(site, prior)
    ev = dict(np.load(ax.PH / 'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2' / f'{site}__{prior}/evaluation.npz'))
    assert np.array_equal(u.centre, ev['centre']), 'LOSSTRAIN and region-v3 patch centres differ'
    return dict(gt=gt, u=u, normals=normals, ref=ref, ref_b=ref_b, cells=cells, ev=ev)


def distances(site, prior, result, mesh, folder, context):
    """Original full_dist and Ref.query; outputs are new per-point files under /mp."""
    import gc
    folder.mkdir(parents=True, exist_ok=True)
    gt, u, normals = (context[k] for k in ('gt', 'u', 'normals'))
    v, f = dm.read_mesh(mesh)
    scene = MeshScene(v, f)
    sample = dm.result_sample(v, f, gt)
    del v, f
    gc.collect()
    own = {prior: dm.owner_of_scene_points(site, prior, gt)}
    tree = cKDTree(u.centre)
    near = {prior: tree.query(gt.Gb, workers=-1)[1].astype(np.int64)}
    axs.DIST = folder
    z = axs.full_dist(site, prior, result, 'meshpatch', u, gt, scene, sample,
                      normals[0][gt.bs_idx], normals, own, near, context['ref'].tree,
                      mesh, 'GeoGS cleanup before/after; original AXES71-v2 functions', None)
    del scene
    gc.collect()
    _, nd, lat, _ = context['ref'].query(sample, z['q_d'])
    pd = tree.query(sample, workers=-1)[0]
    extra = dict(ndist=nd.astype(np.float32), lat=lat.astype(np.float32), pd=pd.astype(np.float32))
    prefix = folder / f'{site}_{prior}__{result}'
    b0 = None
    if context['ref_b'] is not None:
        dr_b, nd_b, lat_b, _ = context['ref_b'].query(sample)
        extra.update(ndist_b=nd_b.astype(np.float32), lat_b=lat_b.astype(np.float32))
        b0 = prefix.with_name(prefix.name + '__b0gt.npz')
        np.savez_compressed(b0, q_d_b0gt=dr_b.astype(np.float32))
    xp = prefix.with_name(prefix.name + '__x.npz')
    np.savez_compressed(xp, **extra)
    return (prefix.with_suffix('.npz'), xp, b0)


def values(site, prior, result, context, paths):
    arrays = aa.arrays(site, prior, result, context['cells'], paths=paths)
    blocks = {key: a3.blocks_of([arrays], key) for key in ['all'] + ax.KEYS}
    ev = context['ev']
    eligible = ev['in_eval'] & ev['scoring_allowed']
    cell_blocks = {}
    for cell in range(6):
        mask = eligible & (ev['cell'] == cell)
        g = aa.sel(arrays['rows'], mask[arrays['rows']['patch']])
        s = aa.sel(arrays['smp'], mask[arrays['smp']['patch']])
        cell_blocks[str(cell)] = dict(status='있음', gt=aa.gt_block(g), res=aa.res_block(s, place=True))
    bins = a4.bins_of(site, prior, context['cells'])
    axes = {}
    for line, axis in a4.LINES:
        axes[line] = {}
        for i in list(range(len(a4.labels(axis)))) + ([99] if line == 'axis2_mask' else []):
            row = a4.value([arrays], line, i, [bins])
            g = aa.sel(arrays['rows'], bins[line][arrays['rows']['patch']] == i)
            gb = aa.gt_block(g)
            n_all=int((bins[line][arrays['smp']['patch']] == i).sum())
            row.update(out4=gb.get('out4'), far1=gb.get('far1'), n_res_all=n_all, excluded_res=n_all-row['n_res'], label=a4.labels(axis)[i] if i != 99 else '한 점')
            axes[line][str(i)] = row
    return dict(losstrain_cells_0_to_5=cell_blocks, axes71_cells=blocks, axes=axes,
                axes_info={k: v for k, v in bins.items() if not isinstance(v, np.ndarray)})

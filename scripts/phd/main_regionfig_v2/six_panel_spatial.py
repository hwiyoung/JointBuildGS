"""Actual-XY profiles of supplied layers; no new loss or photo-check calculation."""
from rfcore import *

LAYER_KEYS = ['prior', 'mvs_p', 'gt_p', 'z_category', 'z_check']


def spatial_section(ex, d, step=.25):
    start, end = np.asarray(ex['start_xy']), np.asarray(ex['end_xy'])
    length = float(np.linalg.norm(end - start))
    direction = (end - start) / length
    perpendicular = np.array([-direction[1], direction[0]])
    edges = np.minimum(np.arange(int(np.ceil(length / step)) + 1) * step, length)
    centres = (edges[1:] + edges[:-1]) / 2
    h = np.full((len(centres), len(LAYER_KEYS)), np.nan)
    counts = np.zeros_like(h, dtype=int)
    layers = []
    for k, key in enumerate(LAYER_KEYS):
        displacement = np.zeros(len(d['centre'])) if key == 'prior' else d[key].astype(float)
        xyz = d['centre'] + displacement[:, None] * d['normal']
        along = (xyz[:, :2] - start) @ direction
        across = (xyz[:, :2] - start) @ perpendicular
        keep = (d['matched'] & d['roof_like'] & np.isfinite(xyz).all(axis=1)
                & (along >= 0) & (along <= length) & (abs(across) <= ex['half_width_m']))
        ids = np.flatnonzero(keep)
        bins = np.minimum(np.searchsorted(edges, along[ids], side='right') - 1, len(centres) - 1)
        for b in range(len(centres)):
            selected = ids[bins == b]
            counts[b, k] = len(selected)
            if len(selected):
                h[b, k] = np.median(xyz[selected, 2])
        layers.append(dict(key=key, patch_ids=d['patch_id'][ids], xyz=xyz[ids],
                           along_m=along[ids], across_m=across[ids], bin_index=bins))
    assert np.isfinite(h[:, 2]).any(), 'No supplied reference support for the photo guide'
    zero = float(np.nanmin(h[:, 2]))
    indices = np.flatnonzero(np.isfinite(h[:, 2]))
    runs = np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)
    guide = [np.column_stack((start + centres[run, None] * direction, h[run, 2]))
             for run in runs if len(run)]
    return dict(start_xy=start, end_xy=end, length_m=length, half_width_m=ex['half_width_m'],
                bin_edges_m=edges, bin_centres_m=centres, bin_counts=counts,
                heights_model_m=h, heights_relative_m=h-zero, reference_zero_model_m=zero,
                layers=layers, photo_guide_xyz=guide,
                interpretation='Independent layer medians within the same actual-XY band; not a watertight reconstructed mesh section.',
                occlusion_revalidated=False, scientific_verdict=None)


def projected_guides(sec, ex, g):
    out = []
    for xyz in sec['photo_guide_xyz']:
        uv, depth = project(np.asarray(xyz), g['pose'], g['cam'])
        assert (depth > 0).all(), 'Photo guide lies behind camera'
        out.append(g['transform'].transform(uv-np.array(ex['photo']['crop_box_px'][:2])))
    return out

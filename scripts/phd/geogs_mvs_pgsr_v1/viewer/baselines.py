"""Display-only baseline RGB from native attributes or explicit photo projection.

These readers never write inputs, train, choose source authority, or calculate
quality scores. All index lists describe display sampling only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


RAW_UAS_SHA256 = '50783bfb205ea5532ac2a300d7e41b6b6426e45009d6c961d603e079cc5ae7b4'
RAW_UAS_BYTES = 1277996022
WORLD_SHIFT = [690953., 5336071., 604.]


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def _json(path):
    return json.loads(Path(path).read_text())


def _indices(count, cap):
    if cap < 1:
        raise ValueError('Positive display point cap required')
    return np.arange(count, dtype=np.int64) if count <= cap else np.linspace(0, count-1, cap, dtype=np.int64)


def recover_uas_rgb(reference_npz: Path, raw_laz: Path, world_shift: list,
                    point_cap=200000):
    """Recover native LAS RGB using exact frozen reference row identities.

    The 1.28 GB raw source is not repeatedly hashed. Its known production SHA is
    declared separately from current header/size and sampled-coordinate checks.
    Raw row IDs and reference-array IDs are retained for every displayed point.
    """
    import laspy
    reference_npz, raw_laz = Path(reference_npz), Path(raw_laz)
    with np.load(reference_npz, allow_pickle=False) as payload:
        points = payload['uas_xyz']
        raw_rows = payload['uas_raw_rows']
        selected = _indices(len(points), point_cap)
        xyz = np.asarray(points[selected], dtype=np.float64)
        rows = np.asarray(raw_rows[selected], dtype=np.int64)
    if len(xyz) != len(rows) or len(np.unique(rows)) != len(rows) or not np.isfinite(xyz).all():
        raise ValueError('Invalid paired UAS reference identities')
    shift = np.asarray(world_shift, dtype=np.float64)
    if shift.shape != (3,) or not np.isfinite(shift).all():
        raise ValueError('Finite inherited world shift required')
    rgb16 = np.empty((len(rows), 3), dtype=np.uint16)
    block_points = 50000
    order = np.argsort(rows, kind='stable')
    ordered_rows = rows[order]
    maximum_coordinate_error = 0.
    blocks_read = 0
    with laspy.open(raw_laz) as stream:
        header = stream.header
        dimensions = list(header.point_format.dimension_names)
        if not all(name in dimensions for name in ('red', 'green', 'blue')):
            raise ValueError('Raw UAS has no native RGB attributes')
        if rows.size and (rows.min() < 0 or rows.max() >= header.point_count):
            raise ValueError('UAS raw row outside original file')
        for block in np.unique(ordered_rows // block_points):
            start = int(block) * block_points
            left = np.searchsorted(ordered_rows, start)
            right = np.searchsorted(ordered_rows, start + block_points)
            positions = order[left:right]
            local_rows = rows[positions] - start
            stream.seek(start)
            chunk = stream.read_points(min(block_points, header.point_count-start))
            selected_raw = chunk[local_rows]
            actual = np.column_stack((selected_raw.x, selected_raw.y, selected_raw.z)) - shift
            delta = float(np.max(np.abs(actual - xyz[positions]))) if len(positions) else 0.
            maximum_coordinate_error = max(maximum_coordinate_error, delta)
            if delta > 2e-7:
                raise ValueError('Native UAS row coordinates differ from frozen reference')
            rgb16[positions] = np.column_stack((selected_raw.red, selected_raw.green, selected_raw.blue))
            blocks_read += 1
        header_record = dict(point_count=int(header.point_count), point_format=int(header.point_format.id),
                             scales=header.scales.tolist(), offsets=header.offsets.tolist())
    # This producer stores 8-bit RGB in the high byte (255 << 8 == 65280).
    # Keep standard high-byte conversion if some low-byte residues are nonzero,
    # but record that observation rather than inventing a per-scene normalization.
    residues = rgb16.astype(np.uint32) % 256
    rgb = (rgb16.astype(np.uint32) // 256).astype(np.uint8)
    provenance = dict(display_only=True, scientific_verdict=None,
        color=dict(kind='NATIVE_UAS_LAZ_RGB_ATTRIBUTE', label='원 UAS LAZ RGB', coverage=1. if len(rows) else 0.),
        geometry_source=str(reference_npz), geometry_sha256=_sha(reference_npz),
        rgb_source=str(raw_laz), raw_bytes=raw_laz.stat().st_size, raw_header=header_record,
        expected_producer_sha256=RAW_UAS_SHA256, expected_producer_bytes=RAW_UAS_BYTES,
        full_raw_sha256_recomputed=False, native_coordinate_identity_checked=True,
        coordinate_max_abs_error_m=maximum_coordinate_error, coordinate_tolerance_m=2e-7,
        world_shift=list(world_shift), selected_reference_indices=selected.tolist(),
        selected_uas_raw_rows=rows.tolist(), source_point_count=len(points), display_point_count=len(rows),
        sampling='deterministic ordered subset of frozen reference rows; no averaging or geometry movement',
        las_seek_block_points=block_points, las_blocks_read=blocks_read,
        rgb_conversion='uint16 // 256; no data-dependent normalization',
        rgb16_min=rgb16.min(axis=0).tolist() if len(rows) else None,
        rgb16_max=rgb16.max(axis=0).tolist() if len(rows) else None,
        rgb16_low_byte_nonzero_channels=int(np.count_nonzero(residues)),
        original_rgb_production_method='not re-estimated; native LAZ attributes, not claimed to be LiDAR spectral measurements')
    return xyz.astype(np.float32), rgb, provenance


def _project(points, view):
    R, t, K = (np.asarray(view[key], dtype=np.float64) for key in ('R', 't', 'K'))
    local = points @ R.T + t
    projected = local @ K.T
    uv = np.full((len(points), 2), np.nan)
    front = local[:, 2] > 0
    uv[front] = projected[front, :2] / projected[front, 2:3]
    inside = front & (uv[:, 0] >= 0) & (uv[:, 0] < view['width']-1) & (uv[:, 1] >= 0) & (uv[:, 1] < view['height']-1)
    return uv, local[:, 2], inside


def colorize_photos(points, base_region: Path, maximum_views=8):
    """Color prior geometry from actual train RGB with same-prior occlusion.

    Saved prior raycast camera-Z is the CPU visibility buffer. Its native rays
    lie at u+0.5/v+0.5, so nearest lookup for projected (u,v) uses floor(u,v).
    This is display color only and says nothing about prior temporal validity.
    """
    from PIL import Image
    base_region = Path(base_region)
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError('Finite Nx3 display points required')
    if maximum_views < 1:
        raise ValueError('Positive maximum view count required')
    split_path = base_region/'scene/split_manifest_da3_v2.json'
    split = _json(split_path)
    bound_files = {r['path']: r for r in _json(base_region/'input_manifest.json')['files']}
    if _sha(split_path) != bound_files['scene/split_manifest_da3_v2.json']['sha256']:
        raise ValueError('Frozen split changed')
    probe = points[_indices(len(points), 4096)]
    ranked = []
    for view in split['train']:
        if view['camera_model'] != 'PINHOLE':
            raise ValueError('Expected inherited undistorted PINHOLE camera')
        uv, depth, inside = _project(probe, view)
        centered = ((uv[:, 0]-view['K'][0][2])/view['K'][0][0])**2 + ((uv[:, 1]-view['K'][1][2])/view['K'][1][1])**2
        ranked.append((-int(inside.sum()), float(np.median(centered[inside])) if inside.any() else float('inf'), view['name'], view))
    ranked.sort(key=lambda r: r[:3])
    rgb = np.full((len(points), 3), 160, dtype=np.uint8)
    best = np.full(len(points), np.inf)
    assigned = np.full(len(points), -1, dtype=np.int16)
    records = []
    tolerance = .5
    for view_index, (_, _, _, view) in enumerate(ranked[:maximum_views]):
        name = view['name']; stem = Path(name).stem
        image_path = base_region/'scene/images'/name
        depth_relative = 'prior/raw_depth/' + stem + '.npy'
        prior_path = base_region/depth_relative
        if _sha(image_path) != view['sha256'] or _sha(prior_path) != bound_files[depth_relative]['sha256']:
            raise ValueError('Photo or same-prior visibility source changed')
        with Image.open(image_path) as image:
            image_rgb = np.asarray(image.convert('RGB'))
        prior = np.load(prior_path, allow_pickle=False)
        if image_rgb.shape != (view['height'], view['width'], 3) or prior.shape != image_rgb.shape[:2]:
            raise ValueError('Photo/visibility raster dimensions differ from calibration')
        uv, depth, inside = _project(points, view)
        candidates = np.flatnonzero(inside)
        x0 = np.floor(uv[candidates, 0]).astype(np.int64)
        y0 = np.floor(uv[candidates, 1]).astype(np.int64)
        source_depth = prior[y0, x0]
        visible = np.isfinite(source_depth) & (source_depth > 0) & (np.abs(source_depth-depth[candidates]) <= tolerance)
        eligible = candidates[visible]; x0, y0 = x0[visible], y0[visible]
        score = ((uv[eligible, 0]-view['K'][0][2])/view['K'][0][0])**2 + ((uv[eligible, 1]-view['K'][1][2])/view['K'][1][1])**2
        improve = score < best[eligible]
        picked = eligible[improve]; x0, y0 = x0[improve], y0[improve]
        fx = uv[picked, 0] - x0; fy = uv[picked, 1] - y0
        colors = (image_rgb[y0, x0]*(1-fx)[:, None]*(1-fy)[:, None]
                  + image_rgb[y0, x0+1]*fx[:, None]*(1-fy)[:, None]
                  + image_rgb[y0+1, x0]*(1-fx)[:, None]*fy[:, None]
                  + image_rgb[y0+1, x0+1]*fx[:, None]*fy[:, None])
        rgb[picked] = np.clip(np.rint(colors), 0, 255).astype(np.uint8)
        assigned[picked] = view_index; best[picked] = score[improve]
        records.append(dict(name=name, image_sha256=view['sha256'], prior_depth_sha256=bound_files[depth_relative]['sha256'],
                            projected_points=len(candidates), same_prior_visible_points=len(eligible), updated_color_points=len(picked)))
    colored = assigned >= 0
    coverage = float(colored.mean()) if len(points) else 0.
    return rgb, dict(display_only=True, scientific_verdict=None,
        color=dict(kind='CURRENT_PHOTO_PROJECTED_ON_PRIOR', label='현재 사진 투영색 · prior 기하는 그대로', coverage=coverage),
        colored_points=int(colored.sum()), uncolored_points=int((~colored).sum()), fallback_rgb=[160,160,160],
        split_sha256=_sha(split_path), camera_membership='train only', maximum_views=maximum_views,
        view_selection='projected coarse-support count descending, median off-axis distance ascending, filename tie-break',
        per_point_selection='minimum optical-axis ray distance among same-prior visible selected views',
        visibility='saved same-prior raycast camera-Z; nearest half-pixel source lookup',
        visibility_tolerance_camera_z_m=tolerance, rgb_sampling='bilinear original RGB at projected integer-center coordinates',
        selected_views=records, assignment_view_indices=assigned.tolist(),
        limitations=['display-only photo projection is not native ALS RGB or a historical texture',
                     'same-prior visibility does not validate currentness or account for new occluders absent from prior',
                     'uncolored points remain gray; no MVS/GT source selection or geometry movement'])


def photo_colorize_prior(points, base_region: Path, maximum_views=8):
    return colorize_photos(points, base_region, maximum_views)


def load_baseline(region, kind, base: Path, reference_root: Path,
                  raw_uas_path=Path('/raw/TUM_Downtown_ULS_20241217_nadir.laz'), max_points=200000):
    """Read a display baseline; native OpenMVS and COLMAP supervision stay distinct."""
    base, reference_root = Path(base), Path(reference_root)
    if kind == 'reference':
        return recover_uas_rgb(reference_root/region/'reference.npz', raw_uas_path, WORLD_SHIFT, max_points)
    if kind == 'mvs':
        path = base/'evaluation_inputs'/region/'native.npz'
        source = next(r for r in _json(base/'contracts/evaluation_sources_v1.json')['baselines'] if r['region'] == region)
        if _sha(path) != source['sha256']:
            raise ValueError('Frozen OpenMVS baseline changed')
        with np.load(path, allow_pickle=False) as payload:
            selected = _indices(len(payload['mvs_xyz']), max_points)
            xyz = payload['mvs_xyz'][selected].astype(np.float32)
            rgb = payload['mvs_rgb'][selected].astype(np.uint8)
            rows = payload['mvs_original_row'][selected]
            files = payload['mvs_original_file_index'][selected]
        return xyz, rgb, dict(display_only=True, scientific_verdict=None,
            color=dict(kind='NATIVE_OPENMVS_RGB', label='기존 OpenMVS 점 RGB', coverage=1. if len(xyz) else 0.),
            source=str(path), source_sha256=source['sha256'], source_lineage=source['image_geometry_lineage'],
            selected_source_indices=selected.tolist(), original_source_rows=rows.tolist(), original_source_file_indices=files.tolist(),
            supervision_equivalence='historical fused OpenMVS baseline; not the COLMAP per-camera depth used as new supervision')
    if kind == 'prior':
        path = base/'evaluation/viewer'/region/'prior_mesh.json'
        payload = _json(path)
        points = np.asarray(payload['xyz'], dtype=np.float32).reshape(-1,3)
        selected = _indices(len(points), max_points); xyz = points[selected]
        rgb, provenance = colorize_photos(xyz, base/'inputs'/region)
        provenance.update(geometry_source=str(path), geometry_sha256=_sha(path), selected_existing_display_indices=selected.tolist())
        return xyz, rgb, provenance
    raise ValueError('Unknown baseline kind: ' + kind)


def colmap_depth_points(bindings_path: Path, mvs_root: Path, base_region: Path, point_cap=200000):
    """Display the actual COLMAP supervision as colored camera-depth points."""
    from PIL import Image
    try:
        from mvs_depth import read_colmap_depth
    except ModuleNotFoundError as exc:
        if exc.name != 'mvs_depth':
            raise
        from src.phd.geogs_mvs_pgsr_v1.mvs_depth import read_colmap_depth
    bindings_path, mvs_root, base_region = Path(bindings_path), Path(mvs_root), Path(base_region)
    binding = _json(bindings_path)
    region = binding['region']
    domain = _json(base_region.parents[1]/'contracts/execution_v1.json')['regions'][region]['domain']
    lo = np.array([domain[k][0] for k in 'xyz']); hi = np.array([domain[k][1] for k in 'xyz'])
    views = binding['train']; per_view = max(1, int(np.ceil(point_cap*2/max(1,len(views)))))
    points, colors, identities, used = [], [], [], []
    for view_index, view in enumerate(views):
        depth = read_colmap_depth(mvs_root/view['local_depth'], view['maps']['depth'])
        valid = np.flatnonzero(np.isfinite(depth) & (depth > 0))
        # Bound computation before backprojection. Sampling is fixed, not quality selected.
        candidate = valid[_indices(len(valid), min(len(valid), per_view*16))] if len(valid) else valid
        v, u = np.divmod(candidate, depth.shape[1])
        rays = np.column_stack((u,v,np.ones(len(u)))) @ np.linalg.inv(np.asarray(view['maps']['depth']['K'])).T
        local = rays * depth[v,u,None]
        xyz = (local - np.asarray(view['t'])) @ np.asarray(view['R'])
        inside = np.all((xyz >= lo) & (xyz < hi), axis=1)
        picked = np.flatnonzero(inside); picked = picked[_indices(len(picked), per_view)]
        xyz, local, u, v = xyz[picked], local[picked], u[picked], v[picked]
        image_path = base_region/'scene/images'/view['name']
        if _sha(image_path) != view['sha256']:
            raise ValueError('Frozen COLMAP RGB source changed')
        with Image.open(image_path) as image:
            image_rgb = np.asarray(image.convert('RGB'))
        uv = local @ np.asarray(view['K']).T
        uv = uv[:,:2] / uv[:,2:3]
        x = np.floor(uv[:,0]+.5).astype(int); y = np.floor(uv[:,1]+.5).astype(int)
        okay = (x >= 0) & (x < image_rgb.shape[1]) & (y >= 0) & (y < image_rgb.shape[0])
        points.append(xyz[okay]); colors.append(image_rgb[y[okay],x[okay]])
        identities.append(np.column_stack((np.full(int(okay.sum()),view_index),u[okay],v[okay])).astype(np.int32))
        used.append(dict(name=view['name'], depth_sha256=view['maps']['depth']['sha256'], image_sha256=view['sha256'], display_candidates=int(okay.sum())))
    xyz = np.concatenate(points) if points else np.empty((0,3)); rgb = np.concatenate(colors) if colors else np.empty((0,3),np.uint8)
    ids = np.concatenate(identities) if identities else np.empty((0,3),np.int32)
    selected = _indices(len(xyz), point_cap)
    return xyz[selected].astype(np.float32), rgb[selected].astype(np.uint8), dict(display_only=True, scientific_verdict=None,
        color=dict(kind='ORIGINAL_RGB_AT_NATIVE_COLMAP_DEPTH_RAY', label='COLMAP depth + 원사진 RGB', coverage=1. if len(selected) else 0.),
        binding_path=str(bindings_path), binding_sha256=_sha(bindings_path), region=region,
        bounds_half_open=dict(min=lo.tolist(),max=hi.tolist()), coordinate_frame='inherited local camera/world metric coordinates',
        geometry='backproject existing finite-positive native camera-Z; no fusion, registration, hole filling or surface inference',
        sampling='deterministic per-view raster subsets, fixed prism crop, final ordered cap',
        selected_view_u_v=ids[selected].tolist(), views=used,
        limitations=['multiple cameras may show repeated samples of the same surface', 'display sampling does not replace the full training depth raster'])

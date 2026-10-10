"""Hash-bound native COLMAP camera-Z depth and train-only neighbor candidates.

Depth is in the frozen scene's metric units. Invalid samples remain invalid;
there is no filling, scale fitting, confidence inference, or reference access.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


def checked_bytes(path, expected_sha256):
    """Read an exact source; a missing or incorrect SHA is a hard failure."""
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ValueError("A bound SHA256 is required")
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError(f"Source SHA256 mismatch: {path}")
    return data


def resolve_artifact_path(path, artifact_root):
    """Resolve the canonical container namespace without permitting root escape."""
    prefix = Path('/artifacts/JointBuildGS')
    source = Path(path)
    try:
        relative = source.relative_to(prefix)
    except ValueError as exc:
        raise ValueError(f"Expected canonical artifact path: {path}") from exc
    root = Path(artifact_root).resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Artifact path escapes its root")
    return resolved


def load_split_manifest(path, expected_sha256):
    split = json.loads(checked_bytes(path, expected_sha256))
    names = {}
    for role in ('all', 'train', 'evaluation'):
        rows = split[role]
        names[role] = [row['name'] for row in rows]
        if len(names[role]) != len(set(names[role])):
            raise ValueError(f"Duplicate camera in {role}")
    if set(names['train']) & set(names['evaluation']):
        raise ValueError("Training and evaluation cameras overlap")
    if set(names['train']) | set(names['evaluation']) != set(names['all']):
        raise ValueError("Split does not partition camera membership")
    by_name = {view['name']: view for view in split['all']}
    for role in ('train', 'evaluation'):
        if any(view != by_name[view['name']] for view in split[role]):
            raise ValueError("Split camera metadata differs from all-camera binding")
    return split


def read_colmap_depth(path, metadata):
    """Read native COLMAP float32 layout, verifying header, size and source SHA."""
    if metadata.get('frame') not in ('CAMERA_Z', 'CAMERA_Z_METERS'):
        raise ValueError("Only frozen camera-Z depth is supported")
    data = checked_bytes(path, metadata['sha256'])
    end = 0
    for _ in range(3):
        end = data.find(b'&', end, 100) + 1
        if end == 0:
            raise ValueError("Malformed COLMAP depth header")
    try:
        width, height, channels = map(int, data[:end].decode('ascii').split('&')[:3])
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Malformed COLMAP depth dimensions") from exc
    if width <= 0 or height <= 0 or channels != 1:
        raise ValueError("Expected one-channel positive COLMAP depth dimensions")
    if (width, height, channels, end) != (
        metadata['width'], metadata['height'], metadata['channels'], metadata['header_bytes']
    ):
        raise ValueError("COLMAP depth header differs from binding")
    if len(data) != end + width * height * 4:
        raise ValueError("COLMAP depth payload length differs")
    # COLMAP stores W x H x C in Fortran order; expose the H x W image.
    return np.frombuffer(data, dtype='<f4', offset=end).reshape(
        (width, height), order='F'
    ).T.copy()


def _intrinsics(matrix):
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise ValueError("Finite 3x3 camera intrinsics required")
    if not np.array_equal(matrix[2], [0., 0., 1.]) or np.linalg.det(matrix) <= 0:
        raise ValueError("Invalid pinhole camera intrinsics")
    return matrix


def resample_depth_to_camera(depth, native_K, rgb_K, width, height):
    """Map integer RGB rays to nearest native samples; return depth and validity.

    Nearest means floor(native coordinate + 0.5), including odd image sizes.
    Invalid raw values and out-of-bounds rays yield zero and False. Valid values
    retain the native camera-Z value exactly; zeros never enter interpolation.
    """
    depth = np.asarray(depth)
    if depth.ndim != 2 or depth.size == 0 or width <= 0 or height <= 0:
        raise ValueError("Positive source and destination raster dimensions required")
    native_K, rgb_K = _intrinsics(native_K), _intrinsics(rgb_K)
    yy, xx = np.indices((height, width), dtype=np.float64)
    pixels = np.stack((xx, yy, np.ones_like(xx)), axis=-1)
    native = pixels @ (native_K @ np.linalg.inv(rgb_K)).T
    native = native[..., :2] / native[..., 2:3]
    ix, iy = np.floor(native[..., 0] + .5).astype(np.int64), np.floor(native[..., 1] + .5).astype(np.int64)
    inside = (ix >= 0) & (ix < depth.shape[1]) & (iy >= 0) & (iy < depth.shape[0])
    sampled = depth[np.clip(iy, 0, depth.shape[0] - 1), np.clip(ix, 0, depth.shape[1] - 1)]
    valid = inside & np.isfinite(sampled) & (sampled > 0)
    return np.where(valid, sampled, 0).astype(np.float32), valid


def load_view_depth(view, artifact_root=None, verify_rgb=True, *, depth_path=None, rgb_path=None):
    """Load one bound view; explicit mounted paths avoid a broad artifact mount.

    Intended for preparation/preloading, never reparsing every optimization step.
    Explicit paths still require the manifest's original source SHA256 values.
    """
    if view['camera_model'] != 'PINHOLE':
        raise ValueError("Expected frozen undistorted PINHOLE camera")
    if verify_rgb:
        if rgb_path is None and artifact_root is None:
            raise ValueError("Explicit RGB mount or artifact root required")
        checked_bytes(rgb_path if rgb_path is not None else resolve_artifact_path(view['path'], artifact_root), view['sha256'])
    meta = view['maps']['depth']
    if depth_path is None and artifact_root is None:
        raise ValueError("Explicit depth mount or artifact root required")
    source = depth_path if depth_path is not None else resolve_artifact_path(meta['path'], artifact_root)
    raw = read_colmap_depth(source, meta)
    depth, valid = resample_depth_to_camera(raw, meta['K'], view['K'], view['width'], view['height'])
    receipt = dict(name=view['name'], source_path=meta['path'], source_sha256=meta['sha256'],
                   rgb_sha256=view['sha256'], rgb_verified=verify_rgb,
                   native_shape=list(raw.shape), output_shape=list(depth.shape),
                   frame='CAMERA_Z_METERS', native_valid_pixels=int((np.isfinite(raw) & (raw > 0)).sum()),
                   output_valid_pixels=int(valid.sum()), output_pixels=int(valid.size),
                   sampler='K_native @ inverse(K_rgb); floor(uv+0.5); invalid_to_zero',
                   hole_fill=False, scale_fit=False, inferred_confidence=False)
    return depth, valid, receipt


def _camera(view):
    K = _intrinsics(view['K'])
    R, t = np.asarray(view['R'], dtype=np.float64), np.asarray(view['t'], dtype=np.float64)
    if R.shape != (3, 3) or t.shape != (3,) or not np.isfinite(R).all() or not np.isfinite(t).all():
        raise ValueError("Invalid camera pose")
    if not np.allclose(R @ R.T, np.eye(3), atol=1e-8, rtol=0):
        raise ValueError("Camera rotation is not orthonormal")
    return K, R, t, -R.T @ t


def build_neighbor_graph(train_views, native_depths, maximum_neighbors=8,
                         grid_side=17, minimum_overlap_fraction=.1,
                         maximum_axis_angle_degrees=30., maximum_baseline_depth_ratio=1.):
    """Select deterministic train-only candidates from current MVS/image support.

    The caller supplies only train rows and their native depth arrays. Candidate
    overlap means positive-Z projection inside the neighbor image, not visibility
    or consistency. Runtime geometry losses must apply their own occlusion masks.
    Metric baseline is normalized by the reference's sampled median MVS depth;
    no scene-independent distance such as 1.5 m is imposed.
    """
    if maximum_neighbors < 1 or grid_side < 2 or not 0 <= minimum_overlap_fraction <= 1:
        raise ValueError("Invalid neighbor graph controls")
    if not 0 <= maximum_axis_angle_degrees <= 180 or maximum_baseline_depth_ratio <= 0:
        raise ValueError("Invalid neighbor geometry limits")
    views = sorted(train_views, key=lambda v: v['name'])
    names = [v['name'] for v in views]
    if len(set(names)) != len(names) or set(native_depths) != set(names):
        raise ValueError("Native depths must match unique train camera membership")
    cameras = {v['name']: _camera(v) for v in views}
    graph = {}
    for view in views:
        name = view['name']; raw = np.asarray(native_depths[name])
        meta = view['maps']['depth']
        if raw.shape != (meta['height'], meta['width']):
            raise ValueError("Native depth raster differs from camera metadata")
        ys = np.unique(np.linspace(0, raw.shape[0]-1, grid_side).astype(int))
        xs = np.unique(np.linspace(0, raw.shape[1]-1, grid_side).astype(int))
        yy, xx = np.meshgrid(ys, xs, indexing='ij'); depths = raw[yy, xx]
        good = np.isfinite(depths) & (depths > 0)
        pixels = np.stack((xx[good], yy[good], np.ones(int(good.sum()))), axis=-1)
        _, R, t, center = cameras[name]
        points = ((pixels @ np.linalg.inv(_intrinsics(meta['K'])).T) * depths[good, None] - t) @ R
        median_depth = float(np.median(depths[good])) if good.any() else None
        candidates = []
        for neighbor in views:
            if neighbor['name'] == name:
                continue
            K2, R2, t2, c2 = cameras[neighbor['name']]
            baseline = float(np.linalg.norm(c2-center))
            angle = float(np.degrees(np.arccos(np.clip(R[2] @ R2[2], -1, 1))))
            local = points @ R2.T + t2
            projection = local @ K2.T
            positive = local[:, 2] > 0
            uv = np.full((len(points), 2), np.nan)
            uv[positive] = projection[positive, :2] / projection[positive, 2:3]
            inside = positive & (uv[:, 0] >= 0) & (uv[:, 0] <= neighbor['width']-1) & (uv[:, 1] >= 0) & (uv[:, 1] <= neighbor['height']-1)
            overlap = float(inside.mean()) if len(points) else 0.
            ratio = baseline/median_depth if median_depth else None
            reasons = []
            if baseline <= 1e-8: reasons.append('duplicate_center')
            if angle > maximum_axis_angle_degrees: reasons.append('axis_angle')
            if ratio is None: reasons.append('no_reference_depth_support')
            elif ratio > maximum_baseline_depth_ratio: reasons.append('baseline_depth_ratio')
            if overlap < minimum_overlap_fraction: reasons.append('projected_overlap')
            candidates.append(dict(name=neighbor['name'], baseline_m=baseline,
                                   baseline_depth_ratio=ratio, axis_angle_degrees=angle,
                                   projected_overlap_fraction=overlap, in_frame_points=int(inside.sum()),
                                   exclusion_reasons=reasons))
        eligible = sorted((c for c in candidates if not c['exclusion_reasons']),
                          key=lambda c: (-c['projected_overlap_fraction'], c['baseline_depth_ratio'], c['name']))
        graph[name] = dict(selected=[c['name'] for c in eligible[:maximum_neighbors]],
                           sampled_valid_points=len(points), sampled_median_depth_m=median_depth,
                           candidates=candidates)
    return dict(schema='jbgs.mvs_train_neighbor_candidates.v1', train_names=names,
                scope='TRAIN_ONLY_GEOMETRIC_CANDIDATES_NOT_VISIBILITY_CONFIDENCE',
                selection='projected_overlap_desc_then_baseline_depth_ratio_asc_then_name',
                controls=dict(maximum_neighbors=maximum_neighbors, grid_side=grid_side,
                              minimum_overlap_fraction=minimum_overlap_fraction,
                              maximum_axis_angle_degrees=maximum_axis_angle_degrees,
                              maximum_baseline_depth_ratio=maximum_baseline_depth_ratio),
                scientific_verdict=None, graph=graph)

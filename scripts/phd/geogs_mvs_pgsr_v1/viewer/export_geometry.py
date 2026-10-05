"""CPU-only display exports with explicit geometry and color provenance.

Source coordinates are retained without a new origin or registration. Binary XYZ
is float32 for WebGL display only; these files must never replace scoring inputs.
"""
from pathlib import Path
import hashlib

import numpy as np
from plyfile import PlyData


SH_C0 = 0.28209479177387814


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def _source(path, expected_sha):
    path = Path(path).resolve(strict=True)
    result = dict(path=str(path), bytes=path.stat().st_size, sha256=_sha(path))
    if expected_sha is not None and result['sha256'] != expected_sha:
        raise ValueError('Source SHA256 differs from the frozen record: ' + str(path))
    return result


def _bounds(bounds):
    if bounds is None:
        return None
    value = np.asarray([bounds['min'], bounds['max']], dtype=np.float64)
    if value.shape != (2, 3) or not np.isfinite(value).all() or np.any(value[0] >= value[1]):
        raise ValueError('Expected finite, increasing bounds min/max XYZ')
    return value


def _cap(value):
    if isinstance(value, bool) or int(value) != value or value <= 0:
        raise ValueError('point_cap must be a positive integer')
    return int(value)


def _rgb(value, count):
    value = np.asarray(value)
    if value.shape != (count, 3) or not np.issubdtype(value.dtype, np.number):
        raise ValueError('Expected one RGB triplet per point, in explicit 0..255 units')
    if not np.isfinite(value).all() or np.any(value < 0) or np.any(value > 255):
        raise ValueError('RGB values must be finite and in 0..255; no automatic color scaling')
    return value


def _color_stats(rgb):
    if not len(rgb):
        return dict(meaningful_variance=False, range_u8=None, channel_std_u8=None)
    value = np.asarray(rgb, dtype=np.float64)
    low, high = value.min(axis=0), value.max(axis=0)
    return dict(meaningful_variance=bool(np.any(high > low)),
                range_u8=[low.tolist(), high.tolist()], channel_std_u8=value.std(axis=0).tolist())


def _binary(directory, name, values, dtype):
    array = np.ascontiguousarray(values, dtype=dtype)
    path = directory / (name + '.bin')
    with path.open('xb') as stream:
        array.tofile(stream)
    return dict(url=path.name, bytes=path.stat().st_size, sha256=_sha(path),
                dtype=array.dtype.str, shape=list(array.shape))


def _point_buffers(destination, xyz, rgb, source_indices=None):
    record = dict(xyz=_binary(destination, 'points.xyz', xyz, '<f4'),
                  rgb=_binary(destination, 'points.rgb', np.rint(rgb), 'u1'), count=len(xyz))
    if source_indices is not None:
        record['source_indices'] = _binary(destination, 'points.source_indices', source_indices, '<u8')
    return record


def _envelope(geometry_kind, source, color, sampling):
    return dict(geometry_kind=geometry_kind, source=source, color=color, sampling=sampling,
                coordinate_frame='Unchanged source XYZ; no added origin, registration, or coordinate transform',
                source_coordinate_precision='Source numeric precision retained during CPU crop/interpolation',
                display_coordinate_precision='IEEE754 float32 little-endian; display only, never scoring input',
                evaluation_reinput=False, scientific_verdict=None)


def _select_indices(xyz, bounds, point_cap):
    mask = np.ones(len(xyz), dtype=bool) if bounds is None else np.all(
        (xyz >= bounds[0]) & (xyz < bounds[1]), axis=1)
    selected = np.flatnonzero(mask)
    cropped_count = len(selected)
    if cropped_count > point_cap:
        selected = selected[np.linspace(0, cropped_count - 1, point_cap, dtype=np.int64)]
    return selected, cropped_count


def export_points(xyz, rgb, destination, *, bounds=None, point_cap=200000,
                  source=None, color=None, geometry_kind='point_cloud', source_indices=None):
    """Export paired real points/colors; an optional row map preserves raw IDs.

    ``rgb`` has explicit 0..255 units. Point cropping is min-inclusive,
    max-exclusive. Capping keeps deterministic ordered source indices.
    """
    xyz = np.asarray(xyz)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or not np.isfinite(xyz).all():
        raise ValueError('Expected finite Nx3 source coordinates')
    rgb = _rgb(rgb, len(xyz))
    cap, box = _cap(point_cap), _bounds(bounds)
    selected, cropped_count = _select_indices(xyz, box, cap)
    if source_indices is None:
        ids = selected
    else:
        source_indices = np.asarray(source_indices)
        if (source_indices.shape != (len(xyz),) or not np.issubdtype(source_indices.dtype, np.integer)
                or np.any(source_indices < 0)):
            raise ValueError('source_indices must contain one nonnegative integer per source row')
        ids = source_indices[selected]
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    result = _envelope(geometry_kind, source, color or dict(kind='SOURCE_RGB', label='Provided source RGB'),
        dict(method='ORDERED_DETERMINISTIC_INDEX_CAP', source_count=len(xyz), cropped_count=cropped_count,
             displayed_count=len(selected), point_cap=cap, crop='min inclusive, max exclusive',
             selected_indices_preserved=True))
    result['points'] = _point_buffers(destination, xyz[selected], rgb[selected], ids)
    result['mesh'] = None
    result['color'] = dict(result['color'], validation=_color_stats(rgb[selected]))
    return result


def export_gaussians(path, destination, bounds, expected_sha=None, point_cap=200000):
    """Display actual Gaussian centers and SH-DC color, without opacity filtering."""
    source = _source(path, expected_sha)
    box, cap = _bounds(bounds), _cap(point_cap)
    vertices = PlyData.read(path, mmap='r')['vertex'].data
    required = ('x', 'y', 'z', 'f_dc_0', 'f_dc_1', 'f_dc_2')
    if any(name not in vertices.dtype.names for name in required):
        raise ValueError('Gaussian PLY requires XYZ and three SH-DC coefficients')
    selected = []
    # Do not materialize the full multi-million-row SH payload.
    for start in range(0, len(vertices), 65536):
        block = vertices[start:start + 65536]
        xyz = np.column_stack([block[key] for key in required[:3]])
        dc = np.column_stack([block[key] for key in required[3:]])
        if not np.isfinite(xyz).all() or not np.isfinite(dc).all():
            raise ValueError('Nonfinite Gaussian position or SH-DC coefficient')
        indices, _ = _select_indices(xyz, box, len(block))
        selected.append(indices + start)
    selected = np.concatenate(selected) if selected else np.empty(0, dtype=np.int64)
    cropped_count = len(selected)
    if cropped_count > cap:
        selected = selected[np.linspace(0, cropped_count - 1, cap, dtype=np.int64)]
    xyz = np.column_stack([vertices[key][selected] for key in required[:3]])
    dc = np.column_stack([vertices[key][selected] for key in required[3:]])
    rgb = np.clip(.5 + SH_C0 * dc.astype(np.float64), 0, 1) * 255
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    result = _envelope('GAUSSIAN_CENTERS', source,
        dict(kind='SH_DC_COLOR', label='Gaussian centers colored by SH-DC; not a rendered image or extracted surface',
             formula='uint8(round(255 * clip(0.5 + 0.28209479177387814 * f_dc, 0, 1)))',
             validation=_color_stats(rgb)),
        dict(method='ORDERED_DETERMINISTIC_INDEX_CAP', source_count=len(vertices), cropped_count=cropped_count,
             displayed_count=len(selected), point_cap=cap, crop='min inclusive, max exclusive',
             selected_indices_preserved=True, opacity_filter=False, invented_surface=False))
    result['points'] = _point_buffers(destination, xyz, rgb, selected)
    result['mesh'] = None
    return result


def _clip_polygon(polygon, axis, boundary, keep_above):
    """Sutherland-Hodgman clipping; last three channels carry linear RGB."""
    if not len(polygon):
        return polygon
    clipped = []
    previous = polygon[-1]
    previous_inside = previous[axis] >= boundary if keep_above else previous[axis] <= boundary
    for current in polygon:
        current_inside = current[axis] >= boundary if keep_above else current[axis] <= boundary
        if current_inside != previous_inside:
            fraction = (boundary - previous[axis]) / (current[axis] - previous[axis])
            intersection = previous + fraction * (current - previous)
            intersection[axis] = boundary
            clipped.append(intersection)
        if current_inside:
            clipped.append(current)
        previous, previous_inside = current, current_inside
    return np.asarray(clipped, dtype=np.float64).reshape(-1, 6)


def _clip_mesh(xyz, rgb, triangles, box):
    """Keep interior native faces and clip crossing faces without closing caps."""
    interior, boundary_polygons = [], []
    for start in range(0, len(triangles), 65536):
        faces = triangles[start:start + 65536]
        points = xyz[faces]
        if box is None:
            interior.append(faces)
            continue
        inside = np.all((points >= box[0]) & (points <= box[1]), axis=(1, 2))
        outside = np.any(np.all(points < box[0], axis=1) | np.all(points > box[1], axis=1), axis=1)
        interior.append(faces[inside])
        for face in faces[~inside & ~outside]:
            polygon = np.column_stack((xyz[face], rgb[face])).astype(np.float64)
            for axis in range(3):
                polygon = _clip_polygon(polygon, axis, box[0, axis], True)
                polygon = _clip_polygon(polygon, axis, box[1, axis], False)
            if len(polygon) >= 3:
                boundary_polygons.append(polygon)
    retained = np.concatenate(interior) if interior else np.empty((0, 3), dtype=np.int64)
    original_ids, compact = np.unique(retained.reshape(-1), return_inverse=True)
    result_xyz, result_rgb = [xyz[original_ids]], [rgb[original_ids].astype(np.float64)]
    result_faces = [compact.reshape(-1, 3)]
    offset = len(original_ids)
    for polygon in boundary_polygons:
        result_xyz.append(polygon[:, :3])
        result_rgb.append(polygon[:, 3:])
        result_faces.append(np.asarray([[offset, offset + i, offset + i + 1]
                                        for i in range(1, len(polygon) - 1)], dtype=np.int64))
        offset += len(polygon)
    points, colors, faces = np.concatenate(result_xyz), np.concatenate(result_rgb), np.concatenate(result_faces)
    # Remove only exact zero-area degeneracies created by plane intersections.
    nondegenerate = []
    for start in range(0, len(faces), 65536):
        chunk = faces[start:start + 65536]
        p = points[chunk]
        keep = np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1) > 0
        nondegenerate.append(chunk[keep])
    faces = np.concatenate(nondegenerate) if nondegenerate else np.empty((0, 3), dtype=np.int64)
    # Compact orphaned boundary vertices without changing any retained triangle.
    ids, inverse = np.unique(faces.reshape(-1), return_inverse=True)
    return points[ids], colors[ids], inverse.reshape(-1, 3), len(boundary_polygons)


def _sample_mesh(xyz, rgb, triangles, count):
    if not len(triangles):
        return np.empty((0, 3)), np.empty((0, 3)), 0.0
    areas = np.empty(len(triangles), dtype=np.float64)
    for start in range(0, len(triangles), 65536):
        points = xyz[triangles[start:start + 65536]]
        areas[start:start + len(points)] = .5 * np.linalg.norm(
            np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]), axis=1)
    area = float(areas.sum())
    if not np.isfinite(area) or area <= 0:
        raise ValueError('Cropped mesh has invalid surface area')
    rng = np.random.default_rng(0)
    selected = np.searchsorted(np.cumsum(areas), rng.random(count) * area, side='right')
    selected = np.minimum(selected, len(triangles) - 1)
    uv = rng.random((count, 2))
    root = np.sqrt(uv[:, 0])
    bary = np.column_stack((1 - root, root * (1 - uv[:, 1]), root * uv[:, 1]))
    faces = triangles[selected]
    return (np.einsum('ni,nij->nj', bary, xyz[faces]),
            np.einsum('ni,nij->nj', bary, rgb[faces]), area)


def export_native_mesh(path, destination, bounds, expected_sha=None, point_cap=200000, *, colorizer=None):
    """Export full colored clipped mesh plus seeded area-uniform display points."""
    source = _source(path, expected_sha)
    box, cap = _bounds(bounds), _cap(point_cap)
    ply = PlyData.read(path, mmap='r', known_list_len={'face': {'vertex_indices': 3}})
    if 'vertex' not in ply or 'face' not in ply:
        raise ValueError('Expected a native triangle mesh PLY')
    vertices = ply['vertex'].data
    if any(key not in vertices.dtype.names for key in ('x', 'y', 'z')):
        raise ValueError('Native mesh has no explicit XYZ')
    native_rgb = all(key in vertices.dtype.names for key in ('red', 'green', 'blue'))
    if not native_rgb and colorizer is None:
        raise ValueError('Native mesh has no explicit vertex RGB; a declared colorizer is required')
    xyz = np.column_stack([vertices[key] for key in ('x', 'y', 'z')]).astype(np.float64)
    rgb = (_rgb(np.column_stack([vertices[key] for key in ('red', 'green', 'blue')]), len(xyz))
           if native_rgb else np.zeros((len(xyz), 3), dtype=np.uint8))
    if not np.isfinite(xyz).all():
        raise ValueError('Native mesh has nonfinite vertices')
    source_color = _color_stats(rgb)
    if native_rgb and not source_color['meaningful_variance']:
        raise ValueError('Native mesh RGB is constant; cannot claim meaningful measured color support')
    faces = np.asarray(ply['face']['vertex_indices'])
    if faces.dtype == object:
        if any(len(face) != 3 for face in faces):
            raise ValueError('Only native triangle faces are supported')
        faces = np.asarray(list(faces), dtype=np.int64)
    if (faces.ndim != 2 or faces.shape[1] != 3 or not np.issubdtype(faces.dtype, np.integer)
            or np.any(faces < 0) or np.any(faces >= len(xyz))):
        raise ValueError('Invalid native triangle indices')
    source_vertex_count, source_triangle_count = len(xyz), len(faces)
    xyz, rgb, faces, boundary_count = _clip_mesh(xyz, rgb, faces, box)
    color = dict(kind='NATIVE_VERTEX_RGB',
        label='Native mesh vertex RGB; interpolated on clipped edges and sample points',
        encoding='uint8 RGB; interpolation in the stored RGB encoding, nearest integer on export',
        validation=source_color)
    if not native_rgb:
        rgb, declared_color = colorizer(xyz)
        rgb = _rgb(rgb, len(xyz))
        if not isinstance(declared_color, dict) or not declared_color.get('kind') or not declared_color.get('label'):
            raise ValueError('Colorizer must declare a provenance color kind and label')
        color = dict(declared_color, validation=_color_stats(rgb), native_vertex_rgb=False)
    if len(xyz) > np.iinfo(np.uint32).max:
        raise ValueError('Display mesh exceeds uint32 index capacity')
    sampled_xyz, sampled_rgb, area = _sample_mesh(xyz, rgb, faces, cap)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    result = _envelope('NATIVE_RGB_TRIANGLE_MESH' if native_rgb else 'COLORIZED_NATIVE_TRIANGLE_MESH', source,
        color,
        dict(method='SURFACE_AREA_UNIFORM_SEED_0', seed=0, point_cap=cap, displayed_count=len(sampled_xyz),
             source_vertex_count=source_vertex_count, source_triangle_count=source_triangle_count,
             cropped_surface_area_m2=area, clipped_boundary_polygons=boundary_count,
             full_cropped_mesh_exported=True, mesh_simplification=False, added_clip_cap_faces=False,
             crop='Closed-box triangle clipping; boundary planes retained, no closing caps'))
    result['points'] = _point_buffers(destination, sampled_xyz, sampled_rgb)
    result['mesh'] = dict(xyz=_binary(destination, 'mesh.xyz', xyz, '<f4'),
        rgb=_binary(destination, 'mesh.rgb', np.rint(rgb), 'u1'),
        indices=_binary(destination, 'mesh.indices', faces, '<u4'),
        vertex_count=len(xyz), triangle_count=len(faces))
    return result

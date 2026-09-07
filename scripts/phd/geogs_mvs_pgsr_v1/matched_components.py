"""CPU-only raw-mesh connectivity inside the exact frozen matched-comparison ROI.

Components share a native mesh edge with positive length remaining inside the ROI.
Clipping does not weld separate vertices, add caps, or connect intersections of
unrelated faces. Component area is the exact box-clipped triangle area, not a
sampled point count. This is a descriptive diagnostic, not a scientific verdict.
"""
import argparse
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time

import numpy as np
from plyfile import PlyData
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


CHUNK = 65536
DEFINITION = {
    'connectivity': 'Native shared edge with strictly positive clipped length inside the closed ROI box',
    'area': 'Float64 Sutherland-Hodgman box clipping; sum of triangle fan areas',
    'point_only_contact_connects': False,
    'coordinate_welding': False,
    'closing_caps': False,
    'smoothing': False,
    'small_component_filter': False,
    'reference_access': False,
    'limitation': 'Fixed ROI can split components connected only outside it; unrelated intersecting faces remain disconnected',
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def checked(root, record):
    root = Path(root).resolve(strict=True)
    path = (root / record['path']).resolve(strict=True)
    path.relative_to(root)
    if path.stat().st_size != record['bytes'] or sha(path) != record['sha256']:
        raise ValueError('Frozen mesh identity differs: ' + str(path))
    return path


def clip_polygon(points, box):
    polygon = np.asarray(points, dtype=np.float64)
    for axis in range(3):
        for side in range(2):
            boundary = box[side, axis]
            if not len(polygon):
                return np.empty((0, 3), dtype=np.float64)
            output = []
            previous = polygon[-1]
            prev_inside = previous[axis] >= boundary if side == 0 else previous[axis] <= boundary
            for current in polygon:
                inside = current[axis] >= boundary if side == 0 else current[axis] <= boundary
                if inside != prev_inside:
                    ratio = (boundary - previous[axis]) / (current[axis] - previous[axis])
                    point = previous + ratio * (current - previous)
                    point[axis] = boundary
                    output.append(point)
                if inside:
                    output.append(current)
                previous, prev_inside = current, inside
            polygon = np.asarray(output, dtype=np.float64).reshape(-1, 3)
    return polygon


def polygon_area(polygon):
    if len(polygon) < 3:
        return 0.0
    cross = np.cross(polygon[1:-1] - polygon[0], polygon[2:] - polygon[0])
    return float(np.linalg.norm(cross, axis=1).sum() * .5)


def positive_clipped_edges(start, end, box):
    """Closed-box slab intersection; a point contact does not join components."""
    delta = end - start
    low, high = np.zeros(len(start)), np.ones(len(start))
    valid = np.any(delta != 0, axis=1)
    for axis in range(3):
        moving = delta[:, axis] != 0
        valid &= moving | ((start[:, axis] >= box[0, axis]) & (start[:, axis] <= box[1, axis]))
        axis_low, axis_high = np.full(len(start), -np.inf), np.full(len(start), np.inf)
        first = (box[0, axis] - start[moving, axis]) / delta[moving, axis]
        second = (box[1, axis] - start[moving, axis]) / delta[moving, axis]
        axis_low[moving], axis_high[moving] = np.minimum(first, second), np.maximum(first, second)
        low, high = np.maximum(low, axis_low), np.minimum(high, axis_high)
    return valid & (high > low)


def measure(vertices, faces, bounds):
    vertices, faces = np.asarray(vertices), np.asarray(faces)
    if set(bounds) == {'x', 'y', 'z'}:
        box = np.asarray([bounds[axis] for axis in ('x', 'y', 'z')], dtype=np.float64).T
    elif set(bounds) == {'min', 'max'}:
        box = np.asarray([bounds['min'], bounds['max']], dtype=np.float64)
    else:
        raise ValueError('Expected exact frozen x/y/z intervals or explicit min/max XYZ bounds')
    if box.shape != (2, 3) or not np.isfinite(box).all() or np.any(box[0] >= box[1]):
        raise ValueError('Invalid finite XYZ ROI bounds')
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
        raise ValueError('Invalid mesh vertices')
    if faces.ndim != 2 or faces.shape[1] != 3 or not np.issubdtype(faces.dtype, np.integer):
        raise ValueError('Native triangular integer faces required')
    ids, areas = [], []
    crossing_count = 0
    for start in range(0, len(faces), CHUNK):
        batch = faces[start:start + CHUNK]
        if np.any(batch < 0) or np.any(batch >= len(vertices)):
            raise ValueError('Face vertex index out of range')
        xyz = vertices[batch].astype(np.float64)
        outside = np.any((xyz.max(axis=1) < box[0]) | (xyz.min(axis=1) > box[1]), axis=1)
        inside = np.all((xyz >= box[0]) & (xyz <= box[1]), axis=(1, 2))
        area = np.zeros(len(batch), dtype=np.float64)
        area[inside] = .5 * np.linalg.norm(np.cross(xyz[inside, 1]-xyz[inside, 0],
                                                   xyz[inside, 2]-xyz[inside, 0]), axis=1)
        for index in np.flatnonzero(~outside & ~inside):
            area[index] = polygon_area(clip_polygon(xyz[index], box))
            crossing_count += int(area[index] > 0)
        keep = area > 0
        ids.append(np.flatnonzero(keep) + start)
        areas.append(area[keep])
    ids = np.concatenate(ids) if ids else np.empty(0, dtype=np.int64)
    areas = np.concatenate(areas) if areas else np.empty(0, dtype=np.float64)
    result = {'source_vertex_count': len(vertices), 'source_triangle_count': len(faces),
              'positive_area_native_faces_in_roi': len(ids), 'clipped_boundary_face_count': crossing_count,
              'component_count': 0, 'surface_area_m2': 0., 'largest_area_component_share': None,
              'largest_component_area_m2': 0., 'top10_area_share': None, 'top10_components': []}
    if not len(ids):
        return result
    # Keep native IDs: the display exporter deliberately duplicates clipped boundary vertices.
    selected = faces[ids].astype(np.int64)
    edges = np.concatenate((selected[:, [0, 1]], selected[:, [1, 2]], selected[:, [2, 0]]))
    owners = np.tile(np.arange(len(ids), dtype=np.int64), 3)
    edges.sort(axis=1)
    edge_keep = np.zeros(len(edges), dtype=bool)
    for start in range(0, len(edges), CHUNK):
        batch = edges[start:start + CHUNK]
        edge_keep[start:start + CHUNK] = positive_clipped_edges(vertices[batch[:, 0]], vertices[batch[:, 1]], box)
    edges, owners = edges[edge_keep], owners[edge_keep]
    order = np.lexsort((edges[:, 1], edges[:, 0]))
    edges, owners = edges[order], owners[order]
    same = np.all(edges[1:] == edges[:-1], axis=1)
    # Chains also correctly connect non-manifold edges having more than two incident faces.
    left, right = owners[:-1][same], owners[1:][same]
    graph = coo_matrix((np.ones(len(left), dtype=np.uint8), (left, right)), shape=(len(ids), len(ids))).tocsr()
    count, labels = connected_components(graph, directed=False)
    component_areas = np.bincount(labels, weights=areas, minlength=count)
    component_faces = np.bincount(labels, minlength=count)
    rank = np.argsort(-component_areas, kind='stable')[:10]
    total = float(component_areas.sum())
    result.update(component_count=int(count), surface_area_m2=total,
                  largest_area_component_share=float(component_areas[rank[0]] / total),
                  largest_component_area_m2=float(component_areas[rank[0]]),
                  top10_area_share=float(component_areas[rank].sum() / total),
                  top10_components=[{'rank': i+1, 'area_m2': float(component_areas[c]),
                                     'area_share': float(component_areas[c]/total),
                                     'native_face_count': int(component_faces[c])} for i, c in enumerate(rank)])
    return result


def inputs(operation, base, doc):
    config = doc['config']
    for key, expected in {'regions': ['P1', 'P2'], 'modes': ['da3', 'mvs', 'mvs_pgsr'],
                          'prior': .005, 'mesh_resolution': 512, 'surface': 'raw',
                          'protection': 'native', 'iteration': 30000, 'scientific_verdict': None}.items():
        if config.get(key) != expected:
            raise ValueError('Unsupported matched comparison: ' + key)
    if len(doc['controls']) != 2 or len(doc['runs']) != 4:
        raise ValueError('Exactly two controls and four new extraction receipts are required')
    result = []
    for region in config['regions']:
        controls = [row for row in doc['controls'] if row['region'] == region and row['mode'] == 'da3']
        if len(controls) != 1:
            raise ValueError('Control membership mismatch')
        control = controls[0]
        result.append((region, 'da3', checked(base, control['surface']), control['surface']))
        for mode in ('mvs', 'mvs_pgsr'):
            jobs = [row for row in doc['runs'] if row['region'] == region and row['mode'] == mode]
            if len(jobs) != 1:
                raise ValueError('New-run membership mismatch')
            job = jobs[0]
            folder = operation / 'extractions' / job['id']
            receipt = read(folder / 'receipt.json')
            if receipt.get('status') != 'PASS' or receipt.get('scientific_verdict') is not None or receipt['job'] != job:
                raise ValueError('Extraction receipt did not pass or job changed')
            for key in ('mesh_res', 'num_cluster', 'voxel_size_m', 'sdf_trunc_m', 'depth_trunc_m'):
                if receipt['realized_extraction'][key] != control['realized_extraction'][key]:
                    raise ValueError('Matched extraction differs: ' + key)
            record = receipt['surfaces']['raw']
            result.append((region, mode, checked(folder, record), record))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation', type=Path, required=True)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if Path('/reference').exists():
        raise RuntimeError('This diagnostic must run without a reference mount')
    doc = read(args.operation / 'plan.json')
    rows = inputs(args.operation, args.base, doc)  # all four PASS receipts before any mesh measurement
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    common = {'scientific_verdict': None, 'plan_sha256': sha(args.operation / 'plan.json'),
              'script_sha256': sha(__file__), 'definition': DEFINITION, 'crs': doc['crs']}
    results = []
    for region, mode, path, source in rows:
        ply = PlyData.read(path, mmap='r', known_list_len={'face': {'vertex_indices': 3}})
        vertices = np.column_stack([ply['vertex'][axis] for axis in ('x', 'y', 'z')])
        faces = np.asarray(ply['face']['vertex_indices'])
        measured = measure(vertices, faces, doc['regions'][region]['domain'])
        measured.update(**common, region=region, mode=mode, source=source,
                        bounds=doc['regions'][region]['domain'])
        write(args.output / (region + '_' + mode + '.json'), measured)
        results.append(measured)
        print(region, mode, measured['component_count'], measured['largest_area_component_share'], flush=True)
        del ply, vertices, faces
    fields = ['region', 'mode', 'component_count', 'positive_area_native_faces_in_roi', 'surface_area_m2',
              'largest_component_area_m2', 'largest_area_component_share', 'top10_area_share']
    with (args.output / 'summary.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(results)
    write(args.output / 'receipt.json', {**common, 'status': 'PASS', 'raw_meshes_measured': len(results),
          'wall_seconds': time.monotonic()-started, 'versions': {
              name: importlib.metadata.version(name) for name in ('numpy', 'scipy', 'plyfile')},
          'results': [{'region': r['region'], 'mode': r['mode'], 'file': r['region']+'_'+r['mode']+'.json',
                       'sha256': sha(args.output / (r['region']+'_'+r['mode']+'.json'))} for r in results]})


if __name__ == '__main__':
    main()

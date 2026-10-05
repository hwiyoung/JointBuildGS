"""Freeze native P2 units and disjoint development view roles; separate references.

Docker-only. Every output folder is created exactly once. No source is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path

import laspy
import numpy as np
from shapely.geometry import box, shape

from src.stage2.colmap_io import read_cameras_bin, read_images_bin
from scripts.phd.mvs_als_source_relation_v1.run import parse_binary_ply_vertices, in_domain, tile_indices

REPO = Path(__file__).resolve().parents[3]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def record(path, expected=None):
    value = sha(path)
    if expected and value != expected:
        raise RuntimeError(f'Input hash mismatch: {path}')
    return {'path': str(path), 'sha256': value, 'bytes': Path(path).stat().st_size}


def config_bundle(path):
    cfg = read(path)
    return cfg, {key: read(REPO / cfg[key]) for key in ['patch_config', 'camera_config', 'source_config', 'reference_config']}


def recover_original_rows(root, cfg, source, tile, selected_rows):
    """Replay only source-to-tile membership, verifying every recovered tile XYZ."""
    shift = np.array(cfg['frame']['world_shift_xyz_m'])
    output_rows, output_files, file_names, records = [], [], [], []
    offset = 0

    def accept(xyz, original_offset, file_index):
        nonlocal offset
        world_xy = xyz[:, :2].astype(np.float64) + shift[:2]
        tx, ty = tile_indices(cfg, world_xy)
        mask = in_domain(cfg, world_xy) & (tx == 4) & (ty == 4)
        native = np.flatnonzero(mask)
        local = xyz[mask].astype('<f4')
        if not np.array_equal(local, tile[offset:offset + len(local)]):
            raise RuntimeError(f'Raw-to-tile XYZ mismatch: {source} offset {offset}')
        wanted = selected_rows[(selected_rows >= offset) & (selected_rows < offset + len(local))] - offset
        output_rows.extend((native[wanted] + original_offset).tolist())
        output_files.extend([file_index] * len(wanted))
        offset += len(local)

    if source == 'mvs':
        spec = cfg['inputs']['mvs']
        path = root / spec['relative_path']
        records.append(record(path, spec['sha256']))
        file_names.append(str(path))
        vertices, _, _ = parse_binary_ply_vertices(path)
        for start in range(0, len(vertices), 2_000_000):
            a = vertices[start:start + 2_000_000]
            accept(np.column_stack([a[k] for k in ['x', 'y', 'z']]), start, 0)
    else:
        spec = cfg['inputs']['existing_als']
        for fi, name in enumerate(sorted(spec['files'])):
            path = root / spec['relative_root'] / name
            records.append(record(path, spec['files'][name]))
            file_names.append(str(path))
            start = 0
            with laspy.open(path) as reader:
                for chunk in reader.chunk_iterator(2_000_000):
                    xyz = np.column_stack([np.asarray(chunk.x), np.asarray(chunk.y), np.asarray(chunk.z) + spec['z_shift_m']]) - shift
                    accept(xyz, start, fi)
                    start += len(chunk)
    assert offset == len(tile) and len(output_rows) == len(selected_rows)
    return np.array(output_rows, dtype=np.int64), np.array(output_files, dtype=np.int16), file_names, records


def build_common(config_path):
    started = time.time()
    cfg, bundle = config_bundle(config_path)
    root = Path(cfg['artifact_root'])
    out = root / cfg['output_relative_root'] / 'common'
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'STARTED.json', {'task_id': cfg['task_id'], 'scientific_verdict': None})
    patch_cfg = bundle['patch_config']
    source_cfg = bundle['source_config']
    camera_cfg = bundle['camera_config']['inputs']
    patch_root = root / patch_cfg['output_relative_root']
    relation_root = root / patch_cfg['inputs']['source_relation_relative_root']
    input_records = [record(config_path)] + [record(REPO / cfg[k]) for k in bundle]
    frame, domain = patch_cfg['frame'], patch_cfg['domain']
    cell = cfg['cell_size_m']
    keys = [(ix, iy) for ix in range(int(domain['x'][0] / cell), int(domain['x'][1] / cell))
            for iy in range(int(domain['y'][0] / cell), int(domain['y'][1] / cell))]
    indices = {key: i for i, key in enumerate(keys)}
    units = [{'unit_index': i, 'unit_id': f'P2_X{ix:03d}_Y{iy:03d}', 'grid_ix': ix, 'grid_iy': iy,
              'bbox_xy': [ix * cell, iy * cell, (ix + 1) * cell, (iy + 1) * cell], 'sources': {}}
             for i, (ix, iy) in enumerate(keys)]
    arrays, lineage, denominators = {}, {}, {}
    for source in ['mvs', 'als']:
        spec = patch_cfg['inputs']['partitions'][source]
        tile_path = relation_root / spec['relative_path']
        input_records.append(record(tile_path, spec['sha256']))
        tile = np.memmap(tile_path, mode='r', dtype='<f4').reshape(-1, 3)
        native_rows = np.load(patch_root / f'point_rows_{source}.npy', allow_pickle=False)
        points = np.load(patch_root / f'points_{source}.npy', allow_pickle=False)
        patches = np.load(patch_root / f'patches_{source}.npy', allow_pickle=False)
        for name in [f'point_rows_{source}.npy', f'points_{source}.npy', f'patches_{source}.npy']:
            input_records.append(record(patch_root / name))
        selected = np.ones(len(tile), dtype=bool)
        for axis, key in enumerate(['x', 'y', 'z']):
            selected &= (tile[:, axis] >= domain[key][0]) & (tile[:, axis] < domain[key][1])
        assert np.array_equal(native_rows, np.flatnonzero(selected)), f'Incomplete prism membership: {source}'
        xyz = np.asarray(tile[native_rows])
        unit_index = np.array([indices[tuple(v)] for v in np.floor(xyz[:, :2] / cell).astype(int)], dtype=np.int32)
        patch_by_id = {int(p['patch_id']): p for p in patches}
        patch_type = np.array([int(patch_by_id[int(pid)]['type']) if int(pid) in patch_by_id else 0 for pid in points['patch_id']], dtype=np.uint8)
        originals, file_index, names, records = recover_original_rows(root, source_cfg, source, tile, native_rows)
        input_records += records
        lineage[source] = {'raw_files': names, 'membership_status': 'ALL_TILE_XYZ_EXACTLY_REPLAYED_FROM_RAW_BYTES',
                           'point_order': 'ascending immutable tile rows', 'tile_point_count': len(tile)}
        arrays.update({f'{source}_xyz': xyz, f'{source}_tile_rows': native_rows, f'{source}_patch_id': points['patch_id'],
                       f'{source}_unit_index': unit_index, f'{source}_normals': np.column_stack([points[k] for k in ['nx', 'ny', 'nz']]),
                       f'{source}_patch_type': patch_type, f'{source}_original_row': originals, f'{source}_original_file_index': file_index})
        for unit in units:
            rows = np.flatnonzero(unit_index == unit['unit_index'])
            layers = []
            for pid in np.unique(points['patch_id'][rows]):
                group = rows[points['patch_id'][rows] == pid]
                p = patch_by_id.get(int(pid))
                layers.append({'patch_id': int(pid), 'count': len(group), 'type': int(p['type']) if p is not None else 0,
                               'normal': [float(p[k]) for k in ['nx', 'ny', 'nz']] if p is not None else None,
                               'centroid': xyz[group].mean(0).astype(float).tolist(),
                               'plane_rmse_m': float(p['plane_rmse_m']) if p is not None else None,
                               'z_min_m': float(xyz[group, 2].min()), 'z_max_m': float(xyz[group, 2].max())})
            unit[f'{source}_count'] = len(rows)
            unit['sources'][source] = {'patches': layers, 'availability': 'ABSENT' if not len(rows) else 'PRESENT_USABILITY_UNASSESSED'}
        denominators[source] = {'prism_native_points': len(xyz), 'nonempty_xy_units': len(np.unique(unit_index)),
                                 'planar_points': int((patch_type == 1).sum()), 'empty_xy_units': len(units) - len(np.unique(unit_index))}
    eligible = [u['unit_index'] for u in units if max(u['mvs_count'], u['als_count']) >= cfg['pilot']['minimum_points_in_either_source']]
    pilot = np.array(eligible)[np.linspace(0, len(eligible)-1, min(len(eligible), cfg['pilot']['maximum_units']), dtype=int)].tolist()
    for unit in units:
        unit['pilot_selected'] = unit['unit_index'] in pilot
    np.savez_compressed(out / 'units.npz', **arrays)
    write(out / 'units.json', {'units': units, 'pilot_unit_indices': pilot, 'pilot_unit_ids': [units[i]['unit_id'] for i in pilot],
                               'eligible_pilot_unit_count': len(eligible), 'cell_area_is_nominal_xy_not_verified_surface': True})
    cam_root = root / camera_cfg['camera_root']
    input_records += [record(cam_root / 'sparse/cameras.bin', camera_cfg['cameras_sha256']),
                      record(cam_root / 'sparse/images.bin', camera_cfg['images_sha256']),
                      record(root / camera_cfg['views'], camera_cfg['views_sha256']),
                      record(REPO / camera_cfg['crosswalk'], camera_cfg['crosswalk_sha256'])]
    cameras, images = read_cameras_bin(cam_root / 'sparse/cameras.bin'), read_images_bin(cam_root / 'sparse/images.bin')
    frozen = read(root / camera_cfg['views'])['views']
    exact = {int(r['colmap_image_id']): r for r in read(REPO / camera_cfg['crosswalk'])['rows']}
    assert len(exact) == 937 and len(frozen) == 66
    split = cfg['view_split']
    ordered = sorted(frozen, key=lambda r: hashlib.sha256((split['seed'] + str(r['colmap_image_id'])).encode()).hexdigest())
    views = []
    for rank, row in enumerate(ordered):
        iid = int(row['colmap_image_id']); im = images[iid]; cam = cameras[im.camera_id]
        assert iid in exact and im.name == row['name'] and cam.model in ['PINHOLE', 'SIMPLE_PINHOLE']
        path = cam_root / 'images' / im.name
        rec = record(path, row['image_sha256']); input_records.append(rec)
        role = 'decision' if rank < split['decision_count'] else ('train' if rank < split['decision_count'] + split['train_count'] else 'appearance_eval')
        views.append({'image_id': iid, 'camera_id': im.camera_id, 'role': role, 'hash_rank': rank, 'name': im.name,
                      'path': str(path), 'sha256': rec['sha256'], 'K': cam.K().tolist(), 'R': im.R().tolist(), 't': im.tvec.tolist(),
                      'width': cam.width, 'height': cam.height, 'camera_model': cam.model, 'historically_used_for_development': True})
    write(out / 'views.json', {'views': views, 'split': split, 'coordinate_frame': 'SCENE_LOCAL_XYZ',
                               'independence_caveat': 'Disjoint new roles only. All 66 historically reused, camera solution and MVS share exact937.'})
    manifest = {'schema': cfg['schema'], 'task_id': cfg['task_id'], 'scientific_verdict': None, 'status': 'COMMON_INPUTS_FROZEN_DEVELOPMENT_ONLY',
                'frame': frame, 'domain': domain, 'source_lineage': lineage, 'denominators': denominators, 'unit_count': len(units),
                'pilot_unit_indices': pilot, 'view_split': split, 'inputs': input_records, 'git_commit': subprocess.check_output(['git','-c',f'safe.directory={REPO}','rev-parse','HEAD'], cwd=REPO, text=True).strip(),
                'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'laspy': laspy.__version__},
                'source_transform': {'mvs': 'Native scene-local; no added correction.', 'als': 'Partition already applies raw Z +45.7 then subtracts [690953,5336071,604]; additional correction=0.'},
                'unresolved': ['Camera/registration metric uncertainty not calibrated', 'No measured terrain gravity supplied by this sample; scene Z is a coordinate axis', 'Prior current usability not determined by this manifest'],
                'evaluation_reference_accessed': False, 'elapsed_seconds': time.time() - started,
                'outputs': {n: record(out/n) for n in ['units.npz','units.json','views.json']}}
    write(out / 'sample_manifest.json', manifest)
    print(json.dumps({'common': str(out), 'unit_count': len(units), 'pilot_units': len(pilot), 'denominators': denominators}, indent=2), flush=True)


def build_evaluation(config_path):
    started = time.time(); cfg, bundle = config_bundle(config_path); root = Path(cfg['artifact_root'])
    common = root / cfg['output_relative_root'] / 'common'
    manifest, unit_json = read(common / 'sample_manifest.json'), read(common / 'units.json')
    out = root / cfg['output_relative_root'] / cfg.get('evaluation_directory', 'evaluation')
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'STARTED.json', {'task_id': cfg['task_id'], 'role': cfg['reference_role'], 'scientific_verdict': None})
    spec = bundle['reference_config']['inputs']['c1_current_uas_lidar']
    path = root / spec['relative_path']; ref_record = record(path, spec['sha256'])
    shift = np.array(manifest['frame']['world_shift_xyz_m']); domain = manifest['domain']; kept, raw_rows, classes = [], [], []
    xy_count, offset = 0, 0
    with laspy.open(path) as reader:
        projection_vlrs = [v for v in reader.header.vlrs if v.user_id in ['LASF_Projection', 'liblas']]
        geokeys = [{'key_id': int(k.id), 'tiff_tag_location': int(k.tiff_tag_location), 'count': int(k.count), 'value_offset': int(k.value_offset)}
                   for v in projection_vlrs if hasattr(v, 'geo_keys') for k in v.geo_keys]
        source_epsg = next((k['value_offset'] for k in geokeys if k['key_id'] == 3072), None)
        header = {'count': reader.header.point_count, 'mins': reader.header.mins.tolist(), 'maxs': reader.header.maxs.tolist(),
                  'scales': reader.header.scales.tolist(), 'offsets': reader.header.offsets.tolist(), 'source_projected_epsg_from_vlr': source_epsg,
                  'geokeys': geokeys, 'projection_text': [v.record_data.decode('utf8', errors='replace').rstrip('\x00') for v in projection_vlrs if hasattr(v, 'record_data')]}
        for chunk in reader.chunk_iterator(2_000_000):
            xyz = np.column_stack([np.asarray(chunk.x),np.asarray(chunk.y),np.asarray(chunk.z)]) - shift
            mask = np.ones(len(xyz), dtype=bool)
            for axis, key in enumerate(['x','y']):
                mask &= (xyz[:,axis] >= domain[key][0]) & (xyz[:,axis] < domain[key][1])
            xy_count += int(mask.sum())
            mask &= (xyz[:,2] >= domain['z'][0]) & (xyz[:,2] < domain['z'][1])
            kept.append(xyz[mask]); raw_rows.append(np.flatnonzero(mask) + offset); classes.append(np.asarray(chunk.classification)[mask]); offset += len(chunk)
    xyz = np.concatenate(kept); rows = np.concatenate(raw_rows); classification = np.concatenate(classes)
    assert offset == spec['point_count'] and len(xyz) > 0
    cell=cfg['cell_size_m']; keys={(u['grid_ix'],u['grid_iy']):u['unit_index'] for u in unit_json['units']}
    unit_index = np.array([keys[tuple(v)] for v in np.floor(xyz[:,:2] / cell).astype(int)], dtype=np.int32)
    np.savez_compressed(out / 'evaluation_reference.npz', uas_xyz=xyz.astype(np.float64), uas_original_rows=rows,
                        uas_classification=classification, uas_unit_index=unit_index)
    world_box=box(domain['x'][0]+shift[0],domain['y'][0]+shift[1],domain['x'][1]+shift[0],domain['y'][1]+shift[1])
    footprint_root=root / bundle['reference_config']['output_relative_root']
    footprints, footprint_records = [], []
    for p in sorted(footprint_root.glob('operations/C2_MVS/*/work/shared_footprint.geojson')):
        data=read(p)
        for feature in data['features']:
            geom=shape(feature['geometry'])
            if not geom.intersects(world_box): continue
            footprint_records.append(record(p)); footprints.append(feature)
    write(out / 'shared_groundsurface_xy.geojson', {'type':'FeatureCollection', 'features':footprints, 'crs': {'type':'name','properties':{'name':'EPSG:25832'}}})
    ids=[f['properties'].get('stable_id') for f in footprints]
    coverage=[]
    counts=np.bincount(unit_index,minlength=len(unit_json['units']))
    for u,count in zip(unit_json['units'], counts):
        coverage.append({'unit_index':u['unit_index'],'unit_id':u['unit_id'],'uas_point_count':int(count),
                         'evaluation_support': 'PRESENT_POINT_SUPPORT_ACCURACY_UNCALIBRATED' if count else 'NO_REFERENCE',
                         'stable_ids': [f['properties'].get('stable_id') for f in footprints if shape(f['geometry']).intersects(box(u['bbox_xy'][0]+shift[0],u['bbox_xy'][1]+shift[1],u['bbox_xy'][2]+shift[0],u['bbox_xy'][3]+shift[1]))]})
    write(out/'reference_manifest.json',{'schema':'jointbuildgs.phd.p2_ab.evaluation_reference.v1','role':cfg['reference_role'],'scientific_verdict':None,
          'input':ref_record,'header':header,'transform':'raw ellipsoidal XYZ minus world shift only; additional vertical correction=0',
          'horizontal_frame_caveat': {'source_epsg': source_epsg, 'project_working_epsg': 25832, 'transform_applied': 'IDENTITY_NUMERIC_LEGACY_COMPARISON_FRAME',
                                      'datum_epoch_bridge_accuracy_m': None, 'metric_claim': 'Numeric common-frame diagnostic only; absolute current accuracy requires verified datum/epoch bridge'},
          'uas_prism_count':len(xyz),'uas_xy_count':xy_count,'uas_excluded_z_count':xy_count-len(xyz),'covered_units':int((counts>0).sum()),
          'stable_ids':ids,'footprint_input_records':footprint_records,'footprint_rule':'Existing exact GroundSurface XY + stable ID only; no Z/roof semantics read',
          'units':coverage,'uncertainty':{'empirical_accuracy_m':None,'claim':'Independent current observation; shared acquisition/frame may correlate georeferencing errors. Metric uncertainty not calibrated.'},
          'elapsed_seconds':time.time()-started,'outputs':{n:record(out/n) for n in ['evaluation_reference.npz','shared_groundsurface_xy.geojson']}})
    print(json.dumps({'evaluation':str(out),'uas_prism_points':len(xyz),'covered_units':int((counts>0).sum()),'stable_ids':ids},indent=2),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('mode',choices=['common','evaluation']); parser.add_argument('--config',type=Path,default=REPO/'configs/phd/p2_ab_v1/sample_v1.json')
    args=parser.parse_args()
    (build_common if args.mode=='common' else build_evaluation)(args.config)

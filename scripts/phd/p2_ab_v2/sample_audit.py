"""Read-only verification of new common inputs; writes only a fresh audit root."""
from __future__ import annotations
import argparse
import json
import platform
import shutil
import time
from pathlib import Path

import cv2
import numpy as np

from scripts.phd.p2_ab_v2.sample_build import read, write, record, quantiles


def run(config_path):
    started = time.time()
    cfg = read(config_path)
    root = Path(cfg['artifact_root'])
    common, out = root / cfg['common_relative_root'], root / cfg['output_relative_root']
    out.mkdir(parents=True, exist_ok=False)
    manifest = read(common/'sample_manifest.json')
    views = read(common/'views.json')['views']
    builder_audit = read(common/'projection_audit.json')
    # All frozen inputs are checked again, including all 66 extracted original JPGs.
    for entry in manifest['inputs']:
        record(entry['path'], entry['sha256'])
    for entry in manifest['outputs'].values():
        record(entry['path'], entry['sha256'])
    roles = {r:{v['image_id'] for v in views if v['role']==r}
             for r in ['decision','train','appearance_eval']}
    assert [len(roles[r]) for r in roles] == [22,33,11]
    assert len(set.union(*roles.values())) == 66
    old_b = read(root / cfg['old_b_relative_root'] / 'views.json')['views']
    old_b = {r['image_id']:r for r in old_b if 'K' in r}
    checked, ratios, crop_factors = [], [], []
    for view in views:
        record(view['path'], view['sha256'])
        record(view['valid_mask_path'], view['valid_mask_sha256'])
        img = cv2.imread(view['path'])
        mask = cv2.imread(view['valid_mask_path'], cv2.IMREAD_GRAYSCALE)
        assert img.shape[:2] == mask.shape == (view['height'],view['width'])
        assert set(np.unique(mask)).issubset({0,255})
        assert view['resize_scale'] == 1 and view['original_focal_preserved']
        assert view['K'][0][0] == view['original_camera_params'][0]
        assert view['K'][1][1] == view['original_camera_params'][1]
        assert view['original_width'] == 5280 and view['original_height'] == 3956
        entry = {'image_id':view['image_id'], 'role':view['role'], 'valid_fraction':float((mask>0).mean()),
                 'depth_dimensions':view['geometric_depth']['dimensions'],
                 'normal_dimensions':view['geometric_normal']['dimensions']}
        if view['image_id'] in old_b:
            b = old_b[view['image_id']]
            x0,y0,x1,y1 = b['crop_xyxy']
            factors = [b['width']/(x1-x0), b['height']/(y1-y0)]
            focal_gain = [view['K'][0][0]/b['K'][0][0], view['K'][1][1]/b['K'][1][1]]
            entry.update(old_b_crop_resize_xy=factors, actual_new_to_old_b_focal_ratio_xy=focal_gain)
            if view['role']=='train':
                ratios.append(focal_gain)
                crop_factors.append(factors)
        checked.append(entry)
    native = np.load(common/'native_geometry.npz',allow_pickle=False)
    geometry = {}
    for source in ['mvs','als']:
        xyz = native[f'{source}_xyz']
        assert np.isfinite(xyz).all()
        assert len(np.unique(native[f'{source}_tile_rows'])) == len(xyz)
        geometry[source] = {'point_count':len(xyz), 'xyz_min':xyz.min(0).tolist(), 'xyz_max':xyz.max(0).tolist(),
                            'unique_raw_file_row_pairs':len(np.unique(np.column_stack([native[f'{source}_original_file_index'],native[f'{source}_original_row']]),axis=0)),
                            'finite_normal_count':int(np.isfinite(native[f'{source}_normals']).all(1).sum()),
                            'native_patch_count':int(len(np.unique(native[f'{source}_patch_id'])))}
        assert geometry[source]['unique_raw_file_row_pairs'] == len(xyz)
    aggregate = {'native_geometry':geometry, 'views':checked,
                 'train_new_to_stored_v1_b_focal_ratio_xy':quantiles(ratios),
                 'train_v1_b_crop_resize_xy':quantiles(crop_factors),
                 'valid_pixel_fraction':quantiles([v['valid_fraction'] for v in checked]),
                 'remap_projection_error_px_max':max(v['remap_projection_max_abs_error_px'] for v in builder_audit['views']),
                 'geometric_depth_dimensions_unique':sorted({tuple(v['depth_dimensions']) for v in checked}),
                 'geometric_normal_dimensions_unique':sorted({tuple(v['normal_dimensions']) for v in checked})}
    receipt = {'task_id':cfg['task_id'],'scientific_verdict':None,'status':'PASS_TECHNICAL_INPUT_INTEGRITY_ONLY',
               'all_common_inputs_and_outputs_sha256_rechecked':True,
               'all_native_raw_row_identities_unique':True,'all_image_dimensions_and_binary_valid_masks_checked':True,
               'reference_accessed':False,'views_disjoint_roles':{r:sorted(ids) for r,ids in roles.items()},
               'metrics':aggregate,'config':record(config_path),'source':record(__file__),
               'common_manifest':record(common/'sample_manifest.json'),
               'git_commit':manifest['git_commit'],'docker_image_id':cfg['docker_image_id'],
               'versions':{'python':platform.python_version(),'numpy':np.__version__,'opencv':cv2.__version__},
               'elapsed_seconds':time.time()-started,
               'limits':['No actual occlusion or currentness certificate.',
                         'Projection pixels do not establish resolvable texture or surface detail.',
                         'Original-focal undistortion resamples original JPG; it does not restore absent sensor observations.',
                         'Same historically reused 66 development views and exact937 MVS dependence.',
                         'No reference fit, datum correction, camera adjustment or extra vertical correction.']}
    write(out/'audit_receipt.json',receipt)
    shutil.copyfile(config_path,out/'config.json')
    shutil.copyfile(__file__,out/'sample_audit.py')
    print(json.dumps({k:v for k,v in aggregate.items() if k!='views'},indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    run(Path(parser.parse_args().config))

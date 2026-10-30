"""Freeze the order and outcome-blind scope before any sample calculation."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re

import numpy as np
from shapely.geometry import Polygon, shape, mapping
from shapely.ops import unary_union

W = Path('/art/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2')
C = Path('/cfg'); O = Path('/out'); R = Path('/repo')

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()

def stamp():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()

def dump(p, value):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')

def ground_records(path):
    """Read only building IDs and GroundSurface metadata from the frozen JSON.

    Roof/wall numeric tokens are skipped as text, never parsed into geometry.
    GroundSurface is necessary solely for exclusion and outline/hatch display.
    """
    bid = None
    with Path(path).open() as f:
        for line in f:
            if line.startswith('    "id":'):
                bid = json.loads(line.split(':', 1)[1].strip().rstrip(','))
            elif line.startswith('      "ground":'):
                block = line.split(':', 1)[1].strip()
                depth = block.count('[')-block.count(']')
                while depth:
                    line = next(f); block += '\n'+line
                    depth += line.count('[')-line.count(']')
                ground = json.loads(block.rstrip().rstrip(','))
                assert bid and ground
                polys = [Polygon(np.asarray(q['ext'])[:, :2],
                         [np.asarray(h)[:, :2] for h in q['holes'] if len(h)>=4]).buffer(0)
                         for q in ground]
                yield bid, unary_union(polys)

def main():
    assert not (C/'judgenum_v1.json').exists(), 'Never overwrite a frozen config'
    wc = json.loads((R/'configs/phd/main_widen0_v2/widen0_v2.json').read_text())
    pc = json.loads((R/'configs/phd/main_photocheck_v1/photocheck_v1.json').read_text())
    split = json.loads((W/'building_split.json').read_text())
    scope = json.loads((W/'scope_split.json').read_text())
    names = wc['scope']['evaluation_regions']
    regions = {n: shape(scope['regions'][n]) for n in names}
    exclusion = []; outlines = []
    dev = set(split['development']); held = set(split['holdout'])
    for bid, fp in ground_records(W/'inputs/lod2_buildings.json'):
        hits = [n for n, p in regions.items() if fp.intersects(p)]
        if hits: exclusion.append({'building': bid, 'regions': hits})
        state = 'evaluation' if hits else ('holdout' if bid in held else 'development')
        outlines.append({'type': 'Feature', 'properties': {'building': bid, 'split': state},
                         'geometry': mapping(fp)})
    excluded = {q['building'] for q in exclusion}
    assert not excluded & held, 'Frozen holdout must remain outside evaluation ranges'
    assert excluded <= dev
    dump(C/'scope_geometry.json', {'type': 'FeatureCollection', 'features': outlines,
         'purpose': 'GroundSurface XY only; exclusions and outline/hatch display',
         'crs': 'EPSG:25832', 'scientific_verdict': None})
    order = (C/'order_v1.txt').read_text()
    cfg = {
      'task_id': 'PHD-MAIN-JUDGENUM-v1', 'scientific_verdict': None,
      'created_at': stamp(), 'source_tag': '[이 발주에서 냄]',
      'authoritative_order_sha256': sha(C/'order_v1.txt'),
      'ordered_methods_2_to_6': order.split('## 2. 단계 가:', 1)[1].split('## 7.', 1)[0],
      'figure_rules_8': order.split('## 8. 그림', 1)[1].split('## 9.', 1)[0],
      'frame': pc['frame'],
      'sources': {'widen': str(W),
        'roof_photo': '/art/phase-payloads/phd/main_photocheck_v1/PHD-MAIN-PHOTOCHECK-v1',
        'wall_photo': '/art/phase-payloads/phd/main_wallphoto_v1/PHD-MAIN-WALLPHOTO-v1',
        'mvs_points': str(W/'holdout/internal/points/<tile>/mvs_a.npy'),
        'mvs_points_status': 'path to be verified before cylinder work; no new MVS',
        'patch_members': ['building', 'patch_id', 'kind', 'area', 'centre', 'normal', 'roof_type', 'cell', 'mvs_a_a', 'u_prior'],
        'source_roles': 'Widen cells only for sample/calibration/diagnostics; not geometric decisions'},
      'scope': {'rule': 'Exact frozen GroundSurface XY intersects any of the four evaluation polygons; exclude whole building',
        'evaluation_regions': names, 'excluded': exclusion,
        'development': sorted(dev-excluded), 'holdout': sorted(held),
        'exploration': wc['scope']['exploration_regions'],
        'geometry_sha256': sha(C/'scope_geometry.json'),
        'source_development_expected': {'LoD2': 135, 'ALS': 132},
        'evaluation_read_boundary': 'Only IDs and GroundSurface XY for exclusion/display; never decode measurement rows of excluded buildings. Compressed ZIP seek may decompress skipped bytes, which are not interpreted as measurements.'},
      'sample_gate': {'cell_numbers': [1,2], 'kind': 1,
        'building_area_strictly_gt_m2': 1., 'min_buildings_each_prior_cell': 5,
        'top3_denominator': 'all eligible area in that prior/kind/cell; no threshold on contributing building',
        'stop_before_cylinders_if_fail': True},
      'cores': {'spacing_m': .25, 'use_inherited_centres_and_normals': True,
        'als_normal_scale_min_ratio_to_roughness': 25, 'normal_refit': False},
      'cylinder': {'radii_m': [.05,.075,.10,.125,.15,.20,.25,.30,.40,.50],
        'half_length_m': 5., 'outer_face': {k: wc['definitions'][k] for k in ['layer_thickness_m','layer_step_m','layer_share','slab_half_m']},
        'face_implementation': 'scripts/phd/main_widen0_v2/u_core.py:find_face; exact source hash recorded',
        'selection': 'first candidate with median count >=20, among cores with count>0 at r=0.50; otherwise 0.50 and flag',
        'selection_groups': ['prior','kind'], 'min_points': 4,
        'standard_deviation_ddof': 1, 'nmad_k': 1.4826,
        'missing_face': 'n=0; retain raw column count separately'},
      'detection': {'z': 1.96, 'floor_m': .0275, 'mvs_offset_key': 'mvs_a_a',
        'missing_mvs_offset': 'zero only for DL; retain missing flag',
        'prior_sigma': pc['uncertainty'],
        'formula_m': 'z * sqrt(s**2/n + a**2 + 0.0275**2 + sigma_p**2)',
        'judgment_codes': {'same': 0,'different': 1,'inherit': 2},
        'inherit_only': 'n<4', 'same': 'n>=4 and abs(d)<=DL',
        'missing_prior_sigma': 'unavailable; never substitute a numerical sigma',
        'old_comparison_tau_m': wc['tau_m']},
      'components': {'radius_m': .36, 'groups': ['building','prior','judgment'],
        'inherited_spacing_fallback': wc['components']['radius_fallback'],
        'null_eligible_cell': 0, 'null_min_building_area_m2': 10.,
        'minimum_area_quantile': .95, 'quantile_method': 'higher',
        'quantile_reason': 'Observed fraction strictly above A must not exceed 5 percent',
        'minimum_area_groups': ['prior','kind'], 'building_size_bins_m2': [10.,100.,500.],
        'small_if': 'area<A', 'neighbor_distance_m': .36,
        'small_replacement': 'largest area of non-different boundary judgments; none leaves unchanged',
        'replacement_tie': 'same before inherit; synchronous from original judgments',
        'minimum_object_area_m2': 1., 'same_islands': 'report only'},
      'initial_choice': {'photo_candidates': pc['judgments']['candidates'],
        'threshold2_m': [.3,.5,.75,1.,1.5,2.,3.,5.,None],
        'none_means': 'unknown always preserves',
        'rules': {'support': 0, 'contradict': 1, 'unknown': '0 if abs(d)<=threshold2 else 1'},
        'not_applicable_code': 9, 'unknown_photo_codes': [2,3,4],
        'missing_photo': 'unknown with missing flag', 'als_wall': 'unknown',
        'wrong': '(cell==1 and choice==0) or (cell==2 and choice==1)',
        'excluded_error_cells': [3,4,5,6],
        'error_ratio_denominator': 'postprocessed different area in cells 0,1,2',
        'selection': 'minimum wrong area; tie largest threshold2, None largest, then earliest photo index',
        'groups': ['LoD2_roof','LoD2_wall','ALS_roof'], 'als_wall_values': 'ALS_roof',
        'additional_groups': ['LoD2_combined','ALS_combined'],
        'building_equal': 'mean per-building wrong fraction over eligible different cells 0,1,2; zero denominator unavailable',
        'leave_one_out': 'buildings with cell1>1m2 or cell2>1m2 in selection group',
        'baselines': ['no photos; reselect threshold2','delta=0.10,s_min=0.3,threshold2=None']},
      'diagnostics': {'standardized_abs_distance_quantiles': [.683,.95,.99],
        'count_bins': [[4,9],[10,19],[20,49],[50,None]],
        'out_of_cylinder_m': [3.,5.,10.], 'bias_correct_decisions': False},
      'sensitivity': [{'name':'confidence90','z':1.645}, {'name':'confidence99','z':2.576},
        {'name':'spacing050','spacing_m':.5}, {'name':'length3','half_length_m':3.},
        {'name':'length10','half_length_m':10.}],
      'sensitivity_spacing': 'inherit photo tangent-grid grouping; keep lexicographically first patch_id and sum member area; do not average coordinates',
      'figures': {'dpi':300,'north_up':True,
        'judgment_colors':['#0072b2','#d55e00','#999999'],
        'photo_colors':['#238b45','#d73027','#999999'],
        'choice_colors':['#8c564b','#238b45'],
        'cell12_colors':['#0072b2','#d55e00'],
        'section_rule':'largest cell1 component per prior; largest cell2 component per prior; largest cell0 LoD2 flat-roof building',
        'section_ties':'area descending then building ID then smallest patch_id',
        'section_length_m':10.,'section_half_width_m':.3,
        'section_coordinates':None,
        'section_coordinate_status':'derive and append lock after sample gate, before any cylinders',
        'montage_n_per_prior':20,'montage_max_per_building':3,'photo_margin_m':3.,
        'photo_projection':pc['photos']['projection'], 'no_cause_labels':True},
      'execution': {'training':False,'gpu':False,'nice':19,'max_memory_gib':32,
        'tile_m':100.,'tile_overlap_m':10.,'cpu_estimate_stop_hours':72,
        'allowed':['configs/phd/main_judgenum_v1/','scripts/phd/main_judgenum_v1/',
                   'docs/experiments/phd/main_judgenum_v1/','PH/main_judgenum_v1/PHD-MAIN-JUDGENUM-v1/'],
        'holdout_public_fields':['building_count','core_point_count','area_m2','sha256'],
        'archive_max_bytes':399000000}, 'amendments': []}
    dump(C/'judgenum_v1.json', cfg)
    sources = [W/'building_split.json', W/'scope_split.json',
      R/'configs/phd/main_widen0_v2/widen0_v2.json',
      R/'configs/phd/main_photocheck_v1/photocheck_v1.json',
      R/'configs/phd/main_wallphoto_v1/wallphoto_v1.json',
      R/'scripts/phd/main_widen0_v2/u_core.py', R/'scripts/phd/main_widen0_v2/scope_split.py']
    dump(C/'judgenum_v1.lock.json', {'locked_at':stamp(), 'before_first_calculation':True,
      'config_sha256':sha(C/'judgenum_v1.json'), 'sources':{str(p):sha(p) for p in sources},
      'commit':os.environ['JUDGENUM_COMMIT'],'image_id':os.environ['JUDGENUM_IMAGE'],
      'scientific_verdict':None})
    print('LOCKED', sha(C/'judgenum_v1.json'), 'excluded buildings', len(excluded),
          'remaining membership', len(dev-excluded), 'holdout membership', len(held))

if __name__=='__main__': main()

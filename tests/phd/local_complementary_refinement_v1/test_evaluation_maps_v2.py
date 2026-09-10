"""Synthetic cell-state, membership, provenance and exported-PNG checks."""
import contextlib
import copy
import csv
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'scripts/phd/local_complementary_refinement_v1'))
import evaluation_maps_v2 as maps


def fixture():
    condition = dict(id='LC_D005_Pnative', parent_condition='D005_Pnative')
    bounds = np.array([[10.2, 12.2], [20.3, 21.8], [0., 3.]])
    # Two distinct original reference points per occupied cell; cells8..11 absent.
    centers = np.array([[10.2+(i%4+.5)*.5, 20.3+(i//4+.5)*.5] for i in range(8)])
    points = np.repeat(np.c_[centers, np.ones(8)], 2, axis=0)
    points[1::2, 2] = 1.1
    ids = np.arange(1000, 1016, dtype=np.int64)
    anchor = np.array([[.1,.1],[1,1],[.1,.1],[.1,1],[.1,1],[.1,.1],[1,1],[np.inf,1]]).ravel()
    global_result = np.array([[.1,.1],[.1,.1],[1,1],[1,.1],[.1,1],[.1,.1],[1,1],[1,np.inf]]).ravel()
    local = np.array([[.1,.1],[.1,.1],[1,1],[.1,1],[1,.1],[1,1],[.1,.1],[.1,1]]).ravel()
    rows = []
    for before_name, after_name, before, after in [('ANCHOR','D005_Pnative',anchor,global_result),
            ('ANCHOR','LC_D005_Pnative',anchor,local), ('D005_Pnative','LC_D005_Pnative',global_result,local)]:
        for i, (x, y) in enumerate(centers):
            b, a = before[2*i:2*i+2], after[2*i:2*i+2]
            c = int(((b>=.5)&(a<.5)).sum()); d = int(((b<.5)&(a>=.5)).sum())
            rows.append(dict(region='P2', candidate=after_name, comparator=before_name, mesh_kind='raw',
                             cell_id=i, x_m=x, y_m=y, reference_count=2, strict_reference_count=1,
                             threshold_m=.5, corrected_count=c, damaged_count=d,
                             both_correction_and_damage=c>0 and d>0,
                             finite_pair_count=int((np.isfinite(a)&np.isfinite(b)).sum())))
    metrics = dict(region='P2', candidate=condition['id'], mesh_kind='raw', mesh_res=512,
                   scientific_verdict=None, bounds_half_open=bounds.tolist(),
                   reference_points_after_voxel=len(ids), crs={'working': 'EPSG:25832', 'world_shift': [690953,5336071,604]})
    return rows, condition, metrics, points, ids, local


class MapsV2Tests(unittest.TestCase):
    def case(self):
        rows, condition, metrics, points, ids, local = fixture()
        return maps.build_case(rows, 'P2', condition, metrics, points, ids, local, .5, .5)

    def test_opposing_point_changes_are_both_never_netted(self):
        result = maps.category([0,2,2,2,2], [0,0,1,0,1], [0,0,0,1,1])
        np.testing.assert_array_equal(result, [0,1,2,3,4])
        with self.assertRaises(ValueError): maps.category([1], [1], [1])
        with self.assertRaises(ValueError): maps.category([2], [-1], [1])

    def test_fixed_roi_origin_and_original_membership_match_all_panels(self):
        case = self.case()
        self.assertEqual(case['dims'], (4,3))
        np.testing.assert_array_equal(case['counts'], [2]*8+[0]*4)
        self.assertEqual(case['reference_count'], 16)
        self.assertEqual(case['panels'][0]['category'][3], 4)
        self.assertEqual(case['panels'][1]['category'][3], 1)
        self.assertEqual(case['panels'][2]['category'][3], 4)
        for p in case['panels']:
            np.testing.assert_array_equal(p['category'][8:], [0]*4)
        # A world-origin grid would assign these coordinates differently.
        np.testing.assert_allclose(case['centers'][0], [10.45,20.55])

    def test_csv_tampering_cannot_change_grid_support_or_hide_both(self):
        rows, c, m, points, ids, local = fixture()
        for field, value in [('cell_id',99), ('x_m',10.0), ('reference_count',3),
                             ('threshold_m',2.), ('strict_reference_count',3), ('finite_pair_count',3),
                             ('corrected_count',3), ('both_correction_and_damage',True)]:
            changed = copy.deepcopy(rows); changed[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                maps.build_case(changed,'P2',c,m,points,ids,local,.5,.5)
        for changed in [rows[1:], rows+[rows[0]]]:
            with self.assertRaises(ValueError): maps.build_case(changed,'P2',c,m,points,ids,local,.5,.5)

    def test_original_reference_ids_and_half_open_roi_are_not_remapped(self):
        rows,c,m,points,ids,local = fixture()
        bad_ids=ids.copy();bad_ids[1]=bad_ids[0]
        with self.assertRaises(ValueError): maps.build_case(rows,'P2',c,m,points,bad_ids,local,.5,.5)
        outside=points.copy();outside[0,0]=m['bounds_half_open'][0][1]
        with self.assertRaises(ValueError): maps.build_case(rows,'P2',c,m,outside,ids,local,.5,.5)
        bad=local.copy();bad[0]=np.nan
        with self.assertRaises(ValueError): maps.build_case(rows,'P2',c,m,points,ids,bad,.5,.5)

    def test_empty_reference_is_unassessed_in_every_roi_cell(self):
        _,c,m,_,_,_=fixture();m['reference_points_after_voxel']=0
        case=maps.build_case([],'P2',c,m,np.empty((0,3)),np.empty(0,dtype=np.int64),np.empty(0),.5,.5)
        self.assertEqual(case['reference_count'],0)
        for panel in case['panels']: np.testing.assert_array_equal(panel['category'],np.zeros(12))

    def test_export_has_all_cells_and_nonempty_readable_png(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)
            synthetic=self.case();synthetic['region']='SYNTHETIC P2'
            result=maps.export_case(output,synthetic)
            self.assertEqual(result['cells_without_observed_reference'],4)
            png=next(output.glob('*.png')); csv_path=next(output.glob('*.csv'))
            with Image.open(png) as image:
                self.assertEqual(image.size,(2720,1190))
                rgb=np.asarray(image.convert('RGB'))
                self.assertGreater(float(rgb.std()),10)
                # Explicit palette must survive the exported pixels.
                for color in maps.COLORS[2:]:
                    expected=np.array([int(color[i:i+2],16) for i in (1,3,5)])
                    self.assertTrue(np.any(np.all(rgb==expected,axis=2)))
            with csv_path.open() as stream: rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),12)
            self.assertEqual(rows[3]['global_to_local_state'],'BOTH_CORRECTION_AND_DAMAGE')
            self.assertEqual(rows[11]['anchor_to_global_state'],'NO_REFERENCE')
            with self.assertRaises(FileExistsError): maps.export_case(output,synthetic)
            preview=os.environ.get('JBGS_MAP_TEST_PREVIEW')
            if preview:
                destination=Path(preview)
                if destination.exists(): raise FileExistsError(destination)
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(png,destination)
                shutil.copyfile(csv_path,destination.with_suffix('.csv'))

    def test_producer_output_hash_and_path_are_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'source.csv').write_text('source\n')
            receipt={'outputs':[dict(maps.record(root/'source.csv'),path='source.csv')]}
            self.assertEqual(maps.verify_output(root,receipt,'source.csv'),root/'source.csv')
            (root/'source.csv').write_text('tampered\n')
            with self.assertRaises(ValueError): maps.verify_output(root,receipt,'source.csv')
            with self.assertRaises(ValueError): maps.safe_child(root,'../elsewhere')

    def test_finalized_attempt_cli_exports_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); evaluation=root/'attempt_SYNTHETIC';evaluation.mkdir()
            rows,c,m,points,ids,local=fixture()
            config={'schema':'jbgs.local_complementary_refinement.v2','task_id':'SYNTHETIC',
                    'scientific_verdict':None,'regions':['P2'],'conditions':[c],
                    'evaluation':{'xy_cell_m':.5,'paired_primary_threshold_m':.5,'mesh_resolutions':[512]}}
            config_path=root/'experiment_v2.json';maps.write_new(config_path,config)
            maps.write_new(evaluation/'config_snapshot.json',config)
            with (evaluation/'same_cell_changes.csv').open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
            case=evaluation/'P2'/c['id'];case.mkdir(parents=True)
            maps.write_new(case/'raw_metrics.json',m)
            np.savez(case/'raw_distances.npz',reference_points=points,reference_original_indices=ids,
                     reference_to_triangle_distance=local)
            receipt={'schema':'jbgs.local_complementary_evaluation.v2','status':'PARTIAL_DEVELOPMENT_EVALUATION',
                     'scientific_verdict':None,'task_id':'SYNTHETIC','run_count':1,
                     'reference_used_for_training_or_parameter_selection':False,
                     'inputs':[maps.record(config_path)],
                     'outputs':[dict(maps.record(p),path=str(p.relative_to(evaluation))) for p in sorted(evaluation.rglob('*')) if p.is_file()]}
            maps.write_new(evaluation/'receipt.json',receipt)
            argv=['evaluation_maps_v2.py','--evaluation',str(evaluation),'--config',str(config_path),'--output',str(root/'maps')]
            with patch.object(sys,'argv',argv),contextlib.redirect_stdout(io.StringIO()): maps.main()
            output=root/'maps'/evaluation.name; result=maps.read(output/'receipt.json')
            self.assertEqual(result['case_count'],1)
            self.assertEqual(result['status'],'PASS_STATIC_MAPS')
            self.assertIsNone(result['scientific_verdict'])
            for r in result['outputs']: self.assertEqual(maps.sha(output/r['path']),r['sha256'])
            with patch.object(sys,'argv',argv),self.assertRaises(FileExistsError): maps.main()


if __name__=='__main__': unittest.main()

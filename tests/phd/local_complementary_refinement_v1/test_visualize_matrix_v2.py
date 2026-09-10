"""Sealed matrix boundary, units, missingness and export tests without GT/models."""
import copy
import csv
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts/phd/local_complementary_refinement_v1'))
import visualize_matrix_v2 as chart


def fixture(full=False):
    conditions=[]
    for coefficient,tag in [(.005,'D005'),(.0005,'D0005'),(0.,'D0')]:
        for protection in ('native','release'):
            parent=tag+'_P'+protection
            conditions.append(dict(id='LC_'+parent,parent_condition=parent,lambda_p=coefficient,protection=protection))
    cfg=dict(schema='jbgs.local_complementary_refinement.v2',task_id='SYNTHETIC_MATRIX_QA',scientific_verdict=None,
        regions=['P1','P2','P3'],conditions=conditions,training={'repetitions':1},
        evaluation={'paired_primary_threshold_m':.5,'mesh_resolutions':[512],
                    'reference_for_training_or_parameter_selection':False})
    rows=[]
    for region in cfg['regions'] if full else ['P2']:
        for index,c in enumerate(conditions if full else conditions[:2]):
            oldp,oldr,newp,newr,g,d=[(.8,.5,.4,.75,3,1),(.5,.5,.7,.5,1,1),
                (.6,.75,.6,.5,0,2),(.5,.5,.5,.5,1,1),(.5,.5,.5,.625,1,0),(.6,.5,.55,.375,0,1)][index]
            oldf=2*oldp*oldr/(oldp+oldr);newf=2*newp*newr/(newp+newr)
            rows.append(dict(region=region,condition=c['id'],parent_condition=c['parent_condition'],lambda_prior=c['lambda_p'],
                protection=c['protection'],mesh_kind='raw',mesh_res=512,threshold_m=.5,reference_count=8,
                local_corrected_vs_global=g,local_damaged_vs_global=d,scientific_verdict=None,
                global_precision=oldp,local_precision=newp,delta_precision=newp-oldp,
                global_recall=oldr,local_recall=newr,delta_recall=newr-oldr,
                global_f1=oldf,local_f1=newf,delta_f1=newf-oldf))
    receipt=dict(schema='jbgs.local_complementary_summary.v2',scientific_verdict=None,task_id=cfg['task_id'],
        status='COMPLETE_18_DEVELOPMENT_SUMMARY' if full else 'PARTIAL_INTERMEDIATE_NO_OUTCOME_CONCLUSION',
        expected_condition_count=18,observed_condition_count=len(rows),raw_gt_or_model_loaded=False,
        parameter_selection_or_temporal_truth_inferred=False)
    return cfg,rows,receipt


def write_csv(path,rows):
    with path.open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def seal(root,full=False):
    cfg,rows,receipt=fixture(full);config=root/'experiment_v2.json';chart.write_json(config,cfg)
    summary=root/'summary';summary.mkdir();csv_path=summary/'paired_summary.csv';write_csv(csv_path,rows)
    receipt.update(inputs=[chart.record(config)],outputs=[dict(chart.record(csv_path),path=csv_path.name)])
    chart.write_json(summary/'receipt.json',receipt)
    return summary,config


class MatrixAccountingTests(unittest.TestCase):
    def test_small_nonzero_changes_do_not_acquire_exact_zero_labels(self):
        self.assertEqual(chart.signed_label(1e-7,4),'+1.00e-07')
        self.assertEqual(chart.signed_label(-1e-5,2),'-1.00e-05')
        self.assertEqual(chart.signed_label(-0.,4),'+0.0000')
        self.assertEqual(chart.signed_label(-.12345,4),'-.1235'.replace('-.','-0.'))

    def test_percentage_points_f1_units_and_same_denominator(self):
        cfg,source,receipt=fixture();rows,missing,complete=chart.validate_rows(source,cfg,receipt)
        self.assertEqual(len(rows),2);self.assertEqual(len(missing),16);self.assertFalse(complete)
        self.assertAlmostEqual(rows[0]['delta_precision_percentage_points'],-40.)
        self.assertAlmostEqual(rows[0]['delta_recall_percentage_points'],25.)
        self.assertAlmostEqual(rows[0]['delta_f1'],source[0]['delta_f1'])
        self.assertEqual(rows[0]['correction_percent'],37.5)
        self.assertEqual(rows[0]['damage_percent'],12.5)
        self.assertIn('16 remaining conditions not plotted (not zero)',chart.status_line(2,False))

    def test_complete_requires_exact_all18_and_frozen_order(self):
        cfg,rows,receipt=fixture(True)
        actual,missing,complete=chart.validate_rows(rows[::-1],cfg,receipt)
        self.assertTrue(complete);self.assertEqual(missing,[])
        self.assertEqual([(r['region'],r['condition']) for r in actual],[(r['region'],r['condition']) for r in rows])
        receipt['observed_condition_count']=17
        with self.assertRaisesRegex(ValueError,'exact all18'):chart.validate_rows(rows[:-1],cfg,receipt)

    def test_duplicate_unexpected_and_unmatched_condition_rejected(self):
        for field,value in [('region','P4'),('parent_condition','D0_Pnative'),('lambda_prior',0),('protection','release')]:
            cfg,rows,receipt=fixture();rows[0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):chart.validate_rows(rows,cfg,receipt)
        cfg,rows,receipt=fixture();rows[1]=dict(rows[0])
        with self.assertRaisesRegex(ValueError,'duplicate'):chart.validate_rows(rows,cfg,receipt)

    def test_metric_count_and_delta_mismatches_fail_closed(self):
        for field,value in [('delta_precision',-.2),('global_precision',1.1),('local_damaged_vs_global',8),
                            ('reference_count',9),('local_corrected_vs_global',2),('delta_f1',.1),('mesh_res',1024)]:
            cfg,rows,receipt=fixture();rows[0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):chart.validate_rows(rows,cfg,receipt)

    def test_no_reference_is_na_and_never_imputed_as_zero(self):
        cfg,rows,receipt=fixture()
        for row in rows:
            row.update(reference_count=0,local_corrected_vs_global=0,local_damaged_vs_global=0)
            for metric in ('precision','recall','f1'):
                for side in ('global','local','delta'):row[side+'_'+metric]=None
        actual,_,_=chart.validate_rows(rows,cfg,receipt)
        self.assertIsNone(actual[0]['delta_f1']);self.assertIsNone(actual[0]['correction_percent'])
        rows[0]['delta_recall']=0
        with self.assertRaisesRegex(ValueError,'unassessed'):chart.validate_rows(rows,cfg,receipt)

    def test_explicit_null_and_evaluation_only_receipt_required(self):
        for field,value in [('scientific_verdict','PASS'),('raw_gt_or_model_loaded',True),
                            ('parameter_selection_or_temporal_truth_inferred',True),('status','RUNNING')]:
            cfg,rows,receipt=fixture();receipt[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):chart.validate_rows(rows,cfg,receipt)
        cfg,rows,receipt=fixture();receipt.pop('scientific_verdict')
        with self.assertRaises(ValueError):chart.validate_rows(rows,cfg,receipt)


class SealedMatrixTests(unittest.TestCase):
    def test_tampered_csv_and_wrong_config_are_rejected_before_writing(self):
        for target in ('csv','config'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);summary,config=seal(root)
                path=summary/'paired_summary.csv' if target=='csv' else config
                with path.open('a') as stream:stream.write('\n')
                with self.assertRaisesRegex(ValueError,'digest|changed'):
                    chart.produce(summary,config,root/'figures')
                self.assertFalse((root/'figures').exists())

    def test_partial_export_has_only_two_rows_and_exact_input_output_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);summary,config=seal(root)
            output,receipt=chart.produce(summary,config,root/'figures')
            self.assertEqual(receipt['status'],'PASS_PARTIAL_MATRIX_FIGURES_NO_OUTCOME_CONCLUSION')
            self.assertFalse(receipt['reference_or_model_loaded']);self.assertFalse(receipt['uncertainty_intervals_present'])
            self.assertFalse(receipt['missing_conditions_are_zero_rows'])
            self.assertEqual(len(chart.read_json(output/'not_plotted_conditions.json')),16)
            with (output/'chart_data.csv').open() as stream:rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),2)
            for r in receipt['outputs']:self.assertEqual(chart.sha(output/r['path']),r['sha256'])
            self.assertEqual(chart.sha(output/'config_snapshot.json'),chart.sha(config))
            self.assertEqual(chart.sha(output/'source_paired_summary.csv'),chart.sha(summary/'paired_summary.csv'))
            for name in ('delta_metrics.png','correction_damage.png'):
                with Image.open(output/name) as im:
                    self.assertEqual(im.width,2560);self.assertGreater(im.height,700)
                    array=np.asarray(im.convert('RGB'));self.assertGreater(float(array.std()),10)

    def test_full18_export_and_optional_synthetic_visual_qa(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);summary,config=seal(root,True)
            output,receipt=chart.produce(summary,config,root/'figures')
            self.assertEqual(receipt['observed_condition_count'],18)
            self.assertEqual(receipt['not_plotted_condition_count'],0)
            self.assertEqual(receipt['status'],'PASS_COMPLETE_18_MATRIX_FIGURES')
            with (output/'chart_data.csv').open() as stream:self.assertEqual(len(list(csv.DictReader(stream))),18)
            preview=os.environ.get('JBGS_MATRIX_TEST_PREVIEW')
            if preview:shutil.copytree(output,preview)

    def test_cannot_write_under_immutable_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);summary,config=seal(root)
            with self.assertRaisesRegex(ValueError,'separate'):chart.produce(summary,config,summary/'new')


if __name__=='__main__':unittest.main()

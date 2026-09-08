"""Analytic discrepancy, denominator, missing-output, and seal-gate checks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from scripts.phd.source_candidate_v1.common import sha
from scripts.phd.source_candidate_v1.evaluate import (
    assess_selection, evaluate_region, geometric_discrepancy, load_reference_npz, summarize_cells, verify_method_seal,
)


def fixture():
    native={'mvs_xyz':np.array([[.25,.25,1.],[.75,.25,1.],[.25,.75,1.]]),
            'als_xyz':np.array([[.25,.25,3.],[.75,.25,3.],[.25,.75,3.]])}
    membership={s+'_cell':np.zeros(3,np.int64) for s in ('mvs','als')}
    membership.update({s+'_inlier':np.ones(3,bool) for s in ('mvs','als')})
    candidate=[dict(cell_id=0,both_valid=True,area_m2=1.,candidates={s:dict(valid=True) for s in ('mvs','als')})]
    decision=[dict(cell_id=0,action='IMAGE')]
    domain={'x':[0,1],'y':[0,1],'z':[0,5]}
    return native,membership,native['mvs_xyz'].copy(),candidate,decision,domain


def summary_row(cell_id,mvs,als,action,valid=True,refs=10):
    row=dict(cell_id=cell_id,region='P1',both_valid=valid,reference_count=refs,action=action,
             mvs_error_m=mvs,als_error_m=als,mvs_native_count=100,als_native_count=20,
             mvs_candidate_count=80,als_candidate_count=15)
    row.update(assess_selection(mvs,als,action,.1))
    return row


class SourceCandidateEvaluationTests(unittest.TestCase):
    def test_parallel_planes_have_exact_two_meter_discrepancy_and_source_symmetry(self):
        args=fixture()
        rows,summary=evaluate_region('P1',*args,cell_m=1.)
        row=rows[0]
        self.assertAlmostEqual(row['mvs_error_m'],0.)
        self.assertAlmostEqual(row['als_error_m'],2.)
        self.assertTrue(row['selection_correct'])
        self.assertEqual(row['regret_m'],0.)
        self.assertEqual(summary['common_accepted_cells'],1)
        native,membership,ref,candidates,decisions,domain=copy.deepcopy(args)
        native['mvs_xyz'],native['als_xyz']=native['als_xyz'],native['mvs_xyz']
        decisions[0]['action']='PRIOR'
        swapped,_=evaluate_region('P1',native,membership,ref,candidates,decisions,domain,1.)
        self.assertEqual(swapped[0]['selected_error_m'],row['selected_error_m'])
        self.assertEqual(swapped[0]['selection_correct'],row['selection_correct'])

    def test_prediction_absence_with_reference_is_zero_completeness(self):
        metric=geometric_discrepancy(np.empty((0,3)),np.array([[0,0,0.]]),[.1,1])
        self.assertEqual(metric['status'],'PREDICTION_ABSENT_WITH_REFERENCE')
        self.assertIsNone(metric['symmetric_mean_m'])
        self.assertEqual([r['recall'] for r in metric['thresholds']],[0.,0.])
        self.assertEqual([r['reference_missing_count'] for r in metric['thresholds']],[1,1])

    def test_reference_absence_is_unassessed_not_zero_error(self):
        metric=geometric_discrepancy(np.array([[0,0,0.]]),np.empty((0,3)))
        self.assertEqual(metric['status'],'NOT_ASSESSED_REFERENCE_ABSENT')
        self.assertIsNone(metric['symmetric_mean_m'])
        self.assertEqual(metric['thresholds'],[])

    def test_exact_reference_schema_preserves_xyz_and_requires_raw_row_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'reference.npz'
            xyz=np.array([[.1,.2,3.],[.4,.5,6.]],dtype=np.float64)
            np.savez(path,uas_xyz=xyz,uas_raw_rows=np.array([45,72],dtype=np.int64))
            np.testing.assert_array_equal(load_reference_npz(path),xyz)
            np.savez(path,xyz=xyz)
            with self.assertRaisesRegex(ValueError,'exact uas_xyz and uas_raw_rows'):
                load_reference_npz(path)
            np.savez(path,uas_xyz=xyz,uas_raw_rows=np.array([45],dtype=np.int64))
            with self.assertRaisesRegex(ValueError,'raw-row lineage schema mismatch'):
                load_reference_npz(path)

    def test_abstention_is_missing_full_target_geometry(self):
        native,membership,ref,candidates,decisions,domain=fixture()
        decisions[0]['action']='ABSTAIN'
        rows,summary=evaluate_region('P1',native,membership,ref,candidates,decisions,domain,1.)
        self.assertIsNone(rows[0]['selected_error_m'])
        whole=summary['whole_native_point_weighted_diagnostics']
        self.assertEqual(whole['selected_inlier_union']['status'],'PREDICTION_ABSENT_WITH_REFERENCE')
        for row in whole['selected_full_target_cell_constrained_completeness']['thresholds']:
            self.assertEqual(row['recall'],0.)
            self.assertEqual(row['reference_missing_count'],3)

    def test_selected_and_baselines_use_exact_same_accepted_cells(self):
        rows=[summary_row(0,0.,2.,'IMAGE'),summary_row(1,100.,1.,'ABSTAIN'),
              summary_row(2,None,None,'ABSTAIN',refs=0)]
        result=summarize_cells(rows)
        self.assertEqual(result['total_cells'],3)
        self.assertEqual(result['paired_cells'],2)
        self.assertEqual(result['common_accepted_cells'],1)
        errors=result['equal_cell_discrepancy']
        self.assertEqual(errors['all_paired_same_cells']['mvs_error_m']['mean'],50.)
        self.assertNotIn('selected_error_m',errors['all_paired_same_cells'])
        for source in ('mvs','als','selected','oracle'):
            self.assertEqual(errors['accepted_same_cells'][source+'_error_m']['n'],1)
        self.assertEqual(errors['accepted_same_cells']['mvs_error_m']['mean'],0.)
        self.assertEqual(result['accepted_fraction_paired_cells'],.5)

    def test_deadband_ties_do_not_artificially_count_as_correct(self):
        tie=assess_selection(.5,.55,'IMAGE',.1)
        self.assertIsNone(tie['selection_correct'])
        self.assertEqual(tie['selection_evaluation_status'],'WITHIN_EVALUATION_DEADBAND')
        wrong=assess_selection(.5,2.,'PRIOR',.1)
        self.assertFalse(wrong['selection_correct'])
        self.assertEqual(wrong['regret_m'],1.5)

    def test_candidate_filtering_diagnostic_preserves_raw_native_error(self):
        native,membership,ref,candidates,decisions,domain=fixture()
        native['mvs_xyz']=np.vstack((native['mvs_xyz'],[.5,.5,4.]))
        membership['mvs_cell']=np.zeros(4,np.int64)
        membership['mvs_inlier']=np.array([True,True,True,False])
        _,summary=evaluate_region('P1',native,membership,ref,candidates,decisions,domain,1.)
        whole=summary['whole_native_point_weighted_diagnostics']
        self.assertGreater(whole['mvs_whole_native']['symmetric_mean_m'],0.)
        self.assertEqual(whole['mvs_all_inliers']['symmetric_mean_m'],0.)
        self.assertEqual(whole['mvs_whole_native']['prediction_count'],4)
        self.assertEqual(whole['mvs_all_inliers']['prediction_count'],3)

    def test_unsealed_and_tampered_method_fails_before_reference_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('numpy.load',side_effect=AssertionError('Reference arrays must not open')):
                with self.assertRaises(FileNotFoundError):
                    verify_method_seal(root)
                config={'regions':{r:{} for r in ('P1','P2','P3')}}
                (root/'config.json').write_text(json.dumps(config))
                files={}
                for region in config['regions']:
                    (root/region).mkdir()
                    for name in ('candidates.json','membership.npz','observations.json','decisions.json',
                                 'input_summary.json','observation_summary.json','decision_summary.json','rgb_ledger.json'):
                        p=root/region/name;p.write_text('[]');files[f'{region}/{name}']=sha(p)
                (root/'sensitivity.json').write_text('[]');files['sensitivity.json']=sha(root/'sensitivity.json')
                seal=dict(status='METHOD_FROZEN_BEFORE_REFERENCE_ACCESS',scientific_verdict=None,
                          reference_accessed=False,config_sha256=sha(root/'config.json'),files=files)
                (root/'method_seal.json').write_text(json.dumps(seal))
                verify_method_seal(root)
                (root/'P2/decisions.json').write_text('["changed"]')
                with self.assertRaisesRegex(ValueError,'Sealed method bytes changed'):
                    verify_method_seal(root)


if __name__=='__main__':
    unittest.main()

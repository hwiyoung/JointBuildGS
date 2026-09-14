"""Fixed association thresholds and nonmutating input screening controls."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np


ROOT=Path(__file__).resolve().parents[2]
def module(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts/phd/mvs_surface_update_v1'/filename)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
s=module('screen','association_screen.py');p=module('probe','gaussian_probe.py')


class FrozenAssociationTests(unittest.TestCase):
    def test_locality_and_geometry_are_joint_and_boundaries_preserved(self):
        camera=dict(width=100,height=100,K=[[100,0,50],[0,100,50],[0,0,1]],R=np.eye(3),t=np.zeros(3))
        xyz=np.array([[0,0,1],[0,0,1],[0,0,1],[0,0,1],[0,0,1.251],[0,0,1.25]],float)
        before=dict(depth=np.ones((100,100)),alpha=np.ones((100,100)))
        target=np.array([4.,.1,3.,3.,3.,.001]);total=np.array([5.,2.,6.,7.,5.,.001])
        xyz_copy=xyz.copy();target_copy=target.copy()
        result=s.select_ids(camera,[47,47,54,54],xyz,before,target,total,p.project)
        np.testing.assert_array_equal(result['ids'],[0,2,5])
        np.testing.assert_array_equal(result['candidates'],[0,1,2,3,5])
        np.testing.assert_array_equal(xyz,xyz_copy);np.testing.assert_array_equal(target,target_copy)

    def test_target_coverage_is_separate_from_per_id_locality(self):
        reasons=s.admission_reasons(np.array([10,20]),.01148927052952115,'IMAGE_SUPPORTED_LOCAL_PROBE')
        self.assertEqual(reasons,['SELECTED_IDS_EXPLAIN_LT_5_PERCENT_TARGET_ALPHA'])
        self.assertEqual(s.admission_reasons(np.array([10]),.05,'IMAGE_SUPPORTED_LOCAL_PROBE'),[])

    def test_source_abstain_and_cap_never_override_to_obtain_modification(self):
        self.assertIn('SOURCE_EVIDENCE_NOT_APPROVED_FOR_PROBE',s.admission_reasons(np.arange(6),.2582,'ABSTAIN'))
        self.assertIn('ASSOCIATION_EXCEEDS_ID_CAP',s.admission_reasons(np.arange(257),.8,'IMAGE_SUPPORTED_LOCAL_PROBE'))
        self.assertEqual(s.POLICY['minimum_locality'],.5)
        self.assertEqual(s.POLICY['depth_tolerance_m'],.25)
        self.assertEqual(s.POLICY['maximum_displacement_m'],.1)


if __name__=='__main__':unittest.main()

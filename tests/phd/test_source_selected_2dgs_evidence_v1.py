import unittest
import numpy as np
from src.phd.source_selected_2dgs_v1 import evidence as ev
from scripts.phd.source_selected_2dgs_v1.prepare import unique_cases


def camera():
    return dict(K=np.array([[10.,0,5],[0,10,5],[0,0,1]]), R=np.eye(3), t=np.zeros(3), width=11, height=11)


class SourceEvidenceTests(unittest.TestCase):
    def test_integer_ray_roundtrip_and_world_normal(self):
        c = camera(); angle=.4; c['R']=np.array([[np.cos(angle),0,np.sin(angle)],[0,1,0],[-np.sin(angle),0,np.cos(angle)]]); c['t']=np.array([2.,-1.,3.])
        uv=np.array([[2,3],[8,6]]); depth=np.array([10.,12.]); xyz=ev.world_points(c,uv,depth)
        projected,z=ev.project_points(c,xyz)
        np.testing.assert_allclose(projected,uv,atol=1e-12); np.testing.assert_allclose(z,depth)
        normal,valid=ev.normals_from_depth(c,np.full((11,11),10.))
        self.assertEqual(valid.sum(),81); np.testing.assert_allclose(normal[5,5],np.array([0,0,-1.])@c['R'],atol=1e-6)

    def test_normals_do_not_fill_holes_or_use_one_sided_stencils(self):
        d=np.full((11,11),10.); d[5,5]=np.nan
        n,v=ev.normals_from_depth(camera(),d)
        for y,x in [(5,5),(5,4),(5,6),(4,5),(6,5),(0,5)]: self.assertFalse(v[y,x]); self.assertTrue(np.isnan(n[y,x]).all())
        self.assertTrue(v[4,4])

    def test_replacement_requires_exact_footprint_and_own_prior_depth(self):
        c=camera(); uv=np.array([[3,3],[6.49,6.49],[6.51,6],[4,4],[4,4]])
        xyz=ev.world_points(c,uv,np.array([10,10,10,10.24,10.26]))
        hit=ev.prior_replacement_membership(xyz,c,[3,3,7,7],np.full((11,11),10.),.25)
        np.testing.assert_array_equal(hit,[True,True,False,True,False])

    def test_projection_is_sparse_and_never_creates_authority(self):
        c=camera(); xyz=ev.world_points(c,np.array([[5,5],[6,5],[5,5]]),np.array([10,12,10]))
        result=ev.point_projection_support(c,xyz,np.full((11,11),10.),.5)
        self.assertEqual(result['mask'].sum(),2); self.assertEqual(result['compatible_mask'].sum(),1)
        np.testing.assert_array_equal(result['point_indices'],[0,1,2]); np.testing.assert_array_equal(result['compatible'],[True,False,True])
        a=self.targets(projection=result['compatible_mask'])
        self.assertEqual(a['authority_mask'].sum(),0); self.assertFalse(a['depth_valid'][5,5]); self.assertFalse(a['normal_valid'][5,5]); self.assertTrue(a['photo_mask'][5,5])

    def targets(self,authority=None,projection=None,md=None,pdomain=None,mdomain=None):
        shape=(11,11); zero=np.zeros(shape,bool); normal=np.broadcast_to([0.,0.,-1.],shape+(3,)).copy()
        return ev.view_targets(np.full(shape,10.),np.full(shape,12.) if md is None else md,normal,normal,np.ones(shape,bool),zero if authority is None else authority,zero if projection is None else projection,zero,zero,ring_radius=1,prior_domain_mask=pdomain,mvs_domain_mask=mdomain)

    def test_authority_requires_paired_source_availability_without_fallback(self):
        auth=np.zeros((11,11),bool); auth[5,5]=True; md=np.full((11,11),12.); md[5,5]=np.nan
        a=self.targets(authority=auth,md=md)
        self.assertTrue(a['authority_mask'][5,5]); self.assertFalse(a['depth_valid'][5,5]); self.assertFalse(a['prior_depth_valid'][5,5]); self.assertTrue(a['target_mask'][5,5])
        self.assertEqual(a['decision_mask'][5,5],2)
        self.assertTrue(a['depth_valid'][2,2]); self.assertEqual(a['selected_depth'][2,2],10.)

    def test_own_xy_domain_prevents_other_surface_prior_fallback(self):
        pdomain=np.ones((11,11),bool); pdomain[5,5]=False
        a=self.targets(pdomain=pdomain,mdomain=np.ones((11,11),bool))
        self.assertTrue(a['photo_mask'][5,5]); self.assertFalse(a['prior_input_valid'][5,5]); self.assertFalse(a['depth_valid'][5,5])

    def test_source_target_and_comparison_domains_are_common_and_disjoint(self):
        auth=np.zeros((11,11),bool); auth[5,5]=True; projection=auth.copy(); projection[3,3]=True
        a=self.targets(authority=auth,projection=projection)
        self.assertEqual(a['selected_depth'][5,5],12.); self.assertEqual(a['prior_depth'][5,5],10.)
        np.testing.assert_array_equal(a['depth_valid'],a['prior_depth_valid']); np.testing.assert_array_equal(a['normal_valid'],a['prior_normal_valid'])
        self.assertFalse(a['projection_abstain_mask'][5,5]); self.assertTrue(a['normal_valid'][5,5])
        count=a['target_mask'].astype(int)+a['surrounding_mask']+a['outside_mask']; self.assertTrue((count==1).all())
        np.testing.assert_array_equal(a['source_normal'],a['selected_normal'])

    def test_seed_sampling_exact_controls_and_stable_identity(self):
        sample,exact=ev.seed_pixel_mask((11,11),8,[[3,3,6,6]])
        self.assertEqual(exact.sum(),9); self.assertEqual(sample.sum(),13)
        uv=np.array([[3,3],[4,3]]); ids=ev.stable_ids(2,12,11,uv,0)
        self.assertEqual(ids[1]-ids[0],1); self.assertTrue((ev.stable_ids(2,12,11,uv,1)-ids==10**11).all()); self.assertTrue((ids<2**53).all())

    def test_assembly_preserves_outside_rows_and_negative_control(self):
        def cloud(n,kind,offset):
            return dict(xyz=np.arange(n*3,dtype=np.float32).reshape(n,3),rgb=np.ones((n,3),np.float32),normal=np.tile([0.,0.,-1.],(n,1)).astype(np.float32),scale=np.ones(n,np.float32),source_kind=np.full(n,kind,np.uint8),stable_source_id=np.arange(n,dtype=np.int64)+offset)
        p=cloud(4,0,10); m=cloud(2,1,20); mask=np.array([False,True,False,True]); baseline,selected=ev.assemble_source_arms(p,mask,m)
        for key in p: np.testing.assert_array_equal(selected[key][:2],baseline[key][~mask])
        np.testing.assert_array_equal(selected['trainable_geometry'],[False,False,True,True])
        b,s=ev.assemble_source_arms(p,np.zeros(4,bool),cloud(0,1,20))
        for key in b: np.testing.assert_array_equal(b[key],s[key])

    def test_parent_cases_dedupe_by_observation_not_case_display_id(self):
        c=dict(selection=dict(camera='P2_1',point=10),case_id='P2_01',decision='ABSTAIN',bbox=[1,1,8,8])
        d=dict(c,case_id='P2_99')
        result=unique_cases([('a',dict(regions=[dict(id='P2',cases=[c])])),('b',dict(regions=[dict(id='P2',cases=[d])]))],'P2')
        self.assertEqual(len(result),1); self.assertEqual(len(result[0]['parents']),2)
        d=dict(d,decision='IMAGE_SUPPORTED_LOCAL_PROBE')
        with self.assertRaises(ValueError): unique_cases([('a',dict(regions=[dict(id='P2',cases=[c,d])]))],'P2')


if __name__=='__main__': unittest.main()

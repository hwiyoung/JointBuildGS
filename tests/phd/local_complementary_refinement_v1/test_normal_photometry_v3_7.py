import unittest
import numpy as np
from src.phd.local_normal_photometry_v3_7 import estimate_normal, plane_depth, rays
from scripts.phd.local_complementary_refinement_v1.photometric_walkthrough_v3_2 import uv_grid, project, score


class NormalGeometryTests(unittest.TestCase):
    def setUp(self):
        self.uv = uv_grid([20,20], 9)
        self.K = np.array([[120.,0,20],[0,100.,20],[0,0,1]])
        self.mask = np.ones((9,9), bool)
        self.n = np.array([.2,-.3,1.]); self.n /= np.linalg.norm(self.n)
        self.d = 20/(rays(self.uv,self.K) @ self.n)

    def test_slanted_plane_normal_and_depth(self):
        normal = estimate_normal(self.uv,self.d,self.mask,self.K)
        self.assertGreater(abs(np.dot(normal['normal_camera'],self.n)),1-1e-12)
        d,m = plane_depth(self.uv,self.d,self.mask,self.K,normal)
        np.testing.assert_allclose(d,self.d,atol=1e-11)
        self.assertTrue(m.all())

    def test_center_is_not_refitted_and_sign_invariant(self):
        d = self.d.copy(); d[4,4] += 1.
        normal = estimate_normal(self.uv,d,self.mask,self.K)
        plane,m = plane_depth(self.uv,d,self.mask,self.K,normal)
        self.assertAlmostEqual(plane[4,4],d[4,4],12)
        opposite = dict(normal, normal_camera=(-np.array(normal['normal_camera'])).tolist())
        reverse,_ = plane_depth(self.uv,d,self.mask,self.K,opposite)
        np.testing.assert_allclose(plane,reverse,atol=1e-12)

    def test_holes_stay_holes_and_missing_center_unavailable(self):
        mask = self.mask.copy(); mask[0,0]=False
        n = estimate_normal(self.uv,self.d,mask,self.K)
        d,m = plane_depth(self.uv,self.d,mask,self.K,n)
        self.assertFalse(m[0,0]); self.assertTrue(np.isnan(d[0,0]))
        mask[4,4]=False
        n = estimate_normal(self.uv,self.d,mask,self.K)
        self.assertEqual(n['status'],'MISSING_CENTER_DEPTH')
        self.assertFalse(plane_depth(self.uv,self.d,mask,self.K,n)[1].any())

    def test_explicit_homography_independent_projection(self):
        ref = dict(K=self.K,R=np.eye(3),t=np.array([.2,-.1,.5]))
        angle=.15
        R=np.array([[np.cos(angle),0,np.sin(angle)],[0,1,0],[-np.sin(angle),0,np.cos(angle)]])
        other = dict(K=self.K,R=R,t=np.array([-1.,.4,.1]))
        q,_,_=project(self.uv,self.d,ref,other)
        A=R@np.asarray(ref['R']).T
        b=other['t']-A@ref['t']
        H=self.K@(A+np.outer(b,self.n)/20)@np.linalg.inv(self.K)
        h=np.concatenate([self.uv,np.ones((9,9,1))],-1)@H.T
        np.testing.assert_allclose(q,h[...,:2]/h[...,2:],atol=1e-11)

    def test_frontoparallel_equivalence(self):
        d=np.full((9,9),20.)
        n=estimate_normal(self.uv,d,self.mask,self.K)
        np.testing.assert_allclose(plane_depth(self.uv,d,self.mask,self.K,n)[0],d,atol=1e-12)

    def test_affine_brightness_and_undefined(self):
        rng=np.random.default_rng(47); rgb=rng.uniform(.1,.4,(9,9,3))
        self.assertAlmostEqual(score(rgb,2*rgb+.1,self.mask,1e-12)[0]['cost'],0.,12)
        self.assertIsNone(score(rgb,rgb,np.zeros_like(self.mask),1e-12)[0]['cost'])
        self.assertIsNone(score(rgb,np.ones_like(rgb),self.mask,1e-12)[0]['cost'])


if __name__ == '__main__':
    unittest.main()

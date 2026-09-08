"""Scientific mechanism checks; run in Docker, with scratch outside the repo."""
import tempfile
import unittest

import numpy as np

from src.phd.srdm_p1p2p3_v1.core import (
    SRDMConfig, aggregate_cost_volume, descriptors, left_right_valid,
    prior_unary, project_sparse_to_right, quadratic_weight, run_srdm, search_ranges,
)


class SRDMCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(prefix="srdm_unit_")

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_quadratic_kernel_continuity_and_tail(self):
        got = quadratic_weight(np.array([0., 10., 20., 30.]), 10.)
        self.assertEqual(got[0], 1.)
        self.assertAlmostEqual(got[2], np.exp(-2))
        self.assertAlmostEqual(got[3], np.exp(-3))
        self.assertGreater(got[1], np.exp(-1))

    def test_prior_replaces_photo_only_in_strong_stage(self):
        photo = np.array([[[.7,.8,.9], [.1,.2,.3]]], np.float32)
        sparse = np.array([[1.,np.nan]], np.float32)
        labels = np.arange(3, dtype=np.float32)
        weak = prior_unary(photo, sparse, labels, "weak", SRDMConfig(weak_sigma=2))
        np.testing.assert_allclose(weak[0,0], photo[0,0]-.4*np.exp(-np.array([1,0,1])/2), atol=1e-7)
        strong = prior_unary(photo, sparse, labels, "strong", SRDMConfig(gamma=.5))
        np.testing.assert_allclose(strong[0,0], [.5,0,.5])
        np.testing.assert_array_equal(strong[0,1], photo[0,1])
        np.testing.assert_array_equal(photo[0,0], np.array([.7,.8,.9],np.float32))

    def test_orthogonal_path_reaches_off_scanline_and_subtracts_redundancy(self):
        cost = np.array([[1.,2.],[4.,8.]],np.float32)[...,None]
        gray = np.ones((2,2),np.float32)
        # First horizontal, then vertical: every pixel gets all four unary costs.
        got = aggregate_cost_volume(cost,gray,SRDMConfig(directions=(0,),threads=1),
                                    self.scratch.name,normalize=False)
        np.testing.assert_allclose(got[...,0],15.)
        # Four orientations include two diagonal chains; diagonals preserve parity.
        got = aggregate_cost_volume(cost,gray,SRDMConfig(threads=1),
                                    self.scratch.name,normalize=False)
        np.testing.assert_allclose(got[...,0],[[48.,42.],[42.,48.]])

    def test_numerical_normalization_preserves_cost_differences(self):
        rng=np.random.default_rng(81)
        cost=rng.uniform(-.4,1,(4,5,7)).astype(np.float32)
        gray=rng.uniform(0,255,(4,5)).astype(np.float32)
        cfg=SRDMConfig(threads=1)
        raw=aggregate_cost_volume(cost,gray,cfg,self.scratch.name,normalize=False)
        normalized=aggregate_cost_volume(cost,gray,cfg,self.scratch.name,normalize=True)
        np.testing.assert_allclose(raw-raw.min(axis=2,keepdims=True),
                                   normalized-normalized.min(axis=2,keepdims=True),atol=3e-5)

    def test_invalid_image_support_interrupts_propagation(self):
        gray=np.ones((3,5),np.float32)
        gray[:,2]=np.nan
        cost=np.ones((3,5,2),np.float32)
        altered=cost.copy()
        altered[:,:2,0]=100
        cfg=SRDMConfig(directions=(0,),threads=1)
        a=aggregate_cost_volume(cost,gray,cfg,self.scratch.name,normalize=False)
        b=aggregate_cost_volume(altered,gray,cfg,self.scratch.name,normalize=False)
        np.testing.assert_array_equal(a[:,3:],b[:,3:])

    def test_hog_unit_votes_and_linear_intensity_invariance(self):
        yy,xx=np.indices((15,17))
        im=(20+xx+2*yy).astype(np.uint8)
        rgb=np.repeat(im[...,None],3,axis=2)
        a=descriptors(rgb)
        b=descriptors((rgb*2+5).astype(np.uint8))
        np.testing.assert_array_equal(a["hog"].sum(axis=2),25.)
        np.testing.assert_array_equal(a["hog"][3:-3,3:-3],b["hog"][3:-3,3:-3])
        np.testing.assert_array_equal(a["census"][3:-3,3:-3],b["census"][3:-3,3:-3])
        self.assertFalse(a["valid"][0].any())

    def test_range_uses_only_similar_intensity_neighbors_and_empty_fallback(self):
        gray=np.array([[20.,20.,100.,100.,200.]],np.float32)
        sparse=np.array([[5.,np.nan,20.,np.nan,np.nan]],np.float32)
        cfg=SRDMConfig(search_radius=1,intensity_tolerance=10,gamma=2,threads=1)
        low,high=search_ranges(gray,sparse,0,30,cfg,self.scratch.name)
        np.testing.assert_array_equal(low,[[3,3,18,18,0]])
        np.testing.assert_array_equal(high,[[7,7,22,22,30]])

    def test_lr_sign_and_occluded_pixels(self):
        left=np.full((1,8),2.,np.float32)
        right=np.full((1,8),-2.,np.float32)
        expected=np.array([[False,False,True,True,True,True,True,True]])
        np.testing.assert_array_equal(left_right_valid(left,right),expected)
        right[0,3]=np.nan
        self.assertFalse(left_right_valid(left,right)[0,5])

    def test_sparse_right_projection_keeps_nearest_collision(self):
        sparse=np.full((1,10),np.nan,np.float32)
        sparse[0,5]=2
        sparse[0,7]=4
        projected=project_sparse_to_right(sparse)
        self.assertEqual(projected[0,3],-4)
        self.assertEqual(np.isfinite(projected).sum(),1)

    def test_complete_pipeline_constant_shift_and_wrong_prior(self):
        rng=np.random.default_rng(34)
        left=rng.integers(0,256,(30,48,3),dtype=np.uint8)
        right=rng.integers(0,256,left.shape,dtype=np.uint8)
        right[:,:-4]=left[:,4:]
        sparse=np.full(left.shape[:2],np.nan,np.float32)
        sparse[10,20]=4
        sparse[18,30]=8
        original=sparse.copy()
        result=run_srdm(left,right,sparse,0,10,
                        SRDMConfig(threads=1,search_radius=5),work_dir=self.scratch.name)
        self.assertTrue(result["prior_keep"][10,20])
        self.assertTrue(result["prior_reject"][18,30])
        central=np.zeros(sparse.shape,bool)
        central[5:-5,12:-7]=True
        base=result["arms"]["image_only"]
        sample=central & base["valid"]
        self.assertGreater(sample.sum(),.85*central.sum())
        self.assertLess(np.median(np.abs(base["disparity"][sample]-4)),.15)
        self.assertFalse(base["interpolated_mask"].any())
        np.testing.assert_array_equal(sparse,original)
        self.assertIsNone(result["receipt"]["scientific_verdict"])

    def test_empty_prior_and_remap_holes_do_not_invent_decisions(self):
        rng=np.random.default_rng(99)
        left=rng.integers(0,256,(20,28,3),dtype=np.uint8)
        right=left.copy()
        mask=np.ones(left.shape[:2],bool)
        mask[8:12,12:16]=False
        sparse=np.full(left.shape[:2],np.nan,np.float32)
        result=run_srdm(left,right,sparse,-2,2,SRDMConfig(threads=1),
                        work_dir=self.scratch.name,left_valid_mask=mask,right_valid_mask=mask)
        self.assertFalse(result["prior_keep"].any())
        self.assertFalse(result["prior_reject"].any())
        self.assertFalse(result["prior_untestable"].any())
        expected=result["arms"]["image_only"]
        self.assertFalse(expected["valid"][~mask].any())
        for name in ("all_prior","srdm"):
            np.testing.assert_array_equal(result["arms"][name]["disparity"],expected["disparity"])

    def test_storage_modes_produce_bit_exact_results(self):
        rng=np.random.default_rng(551)
        left=rng.integers(0,256,(18,28,3),dtype=np.uint8)
        right=rng.integers(0,256,left.shape,dtype=np.uint8)
        right[:,:-3]=left[:,3:]
        sparse=np.full(left.shape[:2],np.nan,np.float32)
        sparse[8,12]=3
        sparse[11,20]=6
        results={}
        for storage in ("memmap","ram","hybrid"):
            results[storage]=run_srdm(left,right,sparse,0,7,
                                      SRDMConfig(threads=1,search_radius=4,storage=storage),
                                      work_dir=self.scratch.name)
        reference=results["memmap"]
        for storage in ("ram","hybrid"):
            other=results[storage]
            for key,value in reference.items():
                if isinstance(value,np.ndarray):
                    np.testing.assert_array_equal(other[key],value)
                    self.assertEqual(other[key].dtype,value.dtype)
                    self.assertEqual(other[key].tobytes(),value.tobytes())
            for arm in reference["arms"]:
                for key,value in reference["arms"][arm].items():
                    np.testing.assert_array_equal(other["arms"][arm][key],value)
                    self.assertEqual(other["arms"][arm][key].tobytes(),value.tobytes())
            self.assertEqual(other["receipt"]["config"]["storage"],storage)

    def test_total_storage_budget_fails_before_allocating(self):
        image=np.zeros((8,8,3),np.uint8)
        sparse=np.full((8,8),np.nan,np.float32)
        with self.assertRaises(MemoryError):
            run_srdm(image,image,sparse,0,10,
                     SRDMConfig(storage="ram",max_total_volume_gib=1e-8),
                     work_dir=self.scratch.name)


if __name__ == "__main__":
    unittest.main()

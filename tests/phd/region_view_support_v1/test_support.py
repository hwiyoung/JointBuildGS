import tempfile
import unittest
from pathlib import Path
import numpy as np
from src.phd.region_view_support_v1 import (
    object_basis, region_mask, corners_xy, read_depth, rgb_native_indices,
    backproject, ray_grid, query_points, concentration,
)


class SupportTests(unittest.TestCase):
    def test_rotated_region_and_world_roundtrip(self):
        basis = object_basis(70)
        region = {'u_m': [100, 240], 'v_m': [-90, -10]}
        xy = np.array([[110, -80], [250, -80], [110, 0]]) @ basis
        xyz = np.column_stack((xy, [-30, -30, -30]))
        np.testing.assert_array_equal(region_mask(xyz, region, basis, [-90, 80]), [True, False, False])
        uv = corners_xy(region, basis) @ basis.T
        np.testing.assert_allclose(uv, [[100,-90], [240,-90], [240,-10], [100,-10], [100,-90]], atol=1e-10)

    def test_depth_layout_and_native_nearest_without_filling(self):
        depth = np.array([[1, 0, 3], [4, 5, 6]], dtype='<f4')
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'depth.bin'
            p.write_bytes(b'3&2&1&' + depth.T.tobytes(order='F'))
            got, meta = read_depth(p)
        np.testing.assert_array_equal(got, depth)
        self.assertEqual((meta['width'], meta['height']), (3, 2))
        _, ids, inside = rgb_native_indices(np.diag([2.,2.,1.]), np.eye(3), 6, 4, 3, 2)
        mapped = got.ravel()[ids].reshape(4,6)
        np.testing.assert_array_equal(mapped[0,:5], [1,0,0,3,3])
        self.assertFalse(inside.reshape(4,6)[0,-1])
        self.assertFalse(inside.reshape(4,6)[-1].any())

    def test_world_projection_and_occlusion_are_distinct(self):
        K = np.array([[10.,0,2], [0,10,2], [0,0,1]])
        R = np.array([[0.,-1,0], [1,0,0], [0,0,1]])
        t = np.array([1.,2.,3.])
        depth = np.full((5,5), 10., dtype=np.float32)
        xyz = backproject(depth.ravel(), ray_grid(K,5,5), R,t)
        frame, has, residual, support = query_points(xyz,R,t,K,depth,[.25,.5,1.])
        self.assertTrue(frame.all() and has.all() and support.all())
        self.assertLess(np.abs(residual).max(), 1e-5)
        occluded = xyz.copy(); occluded[:,2] += 4
        _,has,_,support = query_points(occluded,R,t,K,depth,[.5])
        self.assertTrue(has.all())
        self.assertFalse(support.any())

    def test_equal_roi_pixels_do_not_imply_equal_mean_loss_mass(self):
        result = concentration([100/1000, 100/100])
        self.assertAlmostEqual(result['top1_fraction'], 10/11)
        self.assertEqual(result['n_cumulative']['0.9'], 1)
        self.assertEqual(result['ranking'], [1,0])
        self.assertIsNone(concentration([0,0])['top1_fraction'])


if __name__ == '__main__':
    unittest.main()

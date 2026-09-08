import unittest
import numpy as np
from scripts.phd.srdm_p1p2p3_v1.run_regions import world_cloud, geometric_right_prior


class ReconstructionFrameTest(unittest.TestCase):
    def test_nonidentity_camera_and_rectification(self):
        angle = np.deg2rad(20)
        rect = np.array([[np.cos(angle), 0, np.sin(angle)], [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]])
        rotation = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
        translation = np.array([1., 2., 3.])
        pair = {"Q": np.array([[1., 0, 0, 0], [0, 1., 0, 0], [0, 0, 0, 100.], [0, 0, 5., 0]]),
                "R1": rect, "world_to_left_R": rotation, "world_to_left_t": translation}
        disparity = np.full((3, 4), 2, np.float32)
        selected = np.zeros((3, 4), bool)
        selected[1, 2] = True
        xyz, uv = world_cloud(disparity, selected, pair)
        expected = rotation.T @ (rect.T @ np.array([.2, .1, 10.]) - translation)
        np.testing.assert_allclose(xyz[0], expected, atol=1e-7)
        np.testing.assert_array_equal(uv, [[2, 1]])

    def test_no_selected_points(self):
        pair = {"Q": np.eye(4), "R1": np.eye(3), "world_to_left_R": np.eye(3), "world_to_left_t": np.zeros(3)}
        xyz, uv = world_cloud(np.ones((2, 2), np.float32), np.zeros((2, 2), bool), pair)
        self.assertEqual(xyz.shape, (0, 3))
        self.assertEqual(uv.shape, (0, 2))

    def test_right_prior_uses_original_subpixel_projection(self):
        sparse = np.full((3, 4), np.nan, np.float32)
        indices = np.full((3, 4), -1, np.int64)
        sparse[1, 1], indices[1, 1] = .98, 0
        pair = {"sparse_disparity": sparse, "sparse_source_index": indices,
                "als_right_pixel_xy": np.array([[.51, 1.]])}
        right = geometric_right_prior(pair)
        self.assertAlmostEqual(float(right[1, 1]), -.98, places=6)
        self.assertTrue(np.isnan(right[1, 0]))


if __name__ == "__main__":
    unittest.main()

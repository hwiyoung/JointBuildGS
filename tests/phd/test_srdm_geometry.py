"""Geometric invariants for the preserved-source stereo adapter."""
import unittest

import numpy as np

from src.phd.srdm_p1p2p3_v1.geometry import (
    disparity_bounds, inside_box, rectification, rectified_projection,
    reproject_disparity, select_pair, sparse_als_projection,
)


def view(image_id, center):
    return dict(image_id=image_id, width=80, height=60,
                K=[[100., 0, 40.], [0, 100., 30.], [0, 0, 1]],
                R=np.eye(3).tolist(), t=(-np.asarray(center, float)).tolist())


class StereoGeometryTests(unittest.TestCase):
    def setUp(self):
        self.left, self.right = view(1, [0, 0, 0]), view(2, [1, 0, 0])
        self.rect = rectification(self.left, self.right)

    def test_calibrated_projection_and_Q_roundtrip_with_world_translation(self):
        left, right = view(1, [2, 3, 4]), view(2, [3, 3, 4])
        rect = rectification(left, right)
        xyz = np.array([[2., 3., 14.], [3., 3.5, 14.], [2.4, 3.2, 24.]])
        uv1, _ = rectified_projection(xyz, left, rect["R1"], rect["P1"])
        uv2, _ = rectified_projection(xyz, right, rect["R2"], rect["P2"])
        np.testing.assert_allclose(uv1[:, 1], uv2[:, 1], atol=1e-10)
        disparity = uv1[:, 0] - uv2[:, 0]
        homogeneous = np.column_stack([uv1, disparity, np.ones(len(xyz))]) @ rect["Q"].T
        reconstructed = homogeneous[:, :3] / homogeneous[:, 3:4]
        reconstructed = reconstructed @ (np.asarray(left["R"]).T @ rect["R1"].T).T + np.array([2, 3, 4])
        np.testing.assert_allclose(reconstructed, xyz, atol=1e-9)
        dense = np.full((60, 80), np.nan, np.float32)
        # alpha=0 may adjust focal length even for parallel input cameras.
        dense[30, 40] = rect["P1"][0, 0] / 10
        dense_xyz = reproject_disparity(dense, rect["Q"], np.eye(3), [2, 3, 4])
        np.testing.assert_allclose(dense_xyz[30, 40], xyz[0], atol=1e-6)
        self.assertTrue(np.isnan(dense_xyz[0, 0]).all())

    def test_sparse_collision_depth_and_original_source_identity(self):
        # First two points hit same left pixel; nearest one must retain row 9.
        xyz = np.array([[0., 0., 10.], [0., 0., 20.], [0., 0., -5.], [1., 1., 10.]])
        rows, files = np.array([9, 11, 12, 13]), np.array([2, 1, 0, 1])
        masks = np.ones((60, 80), bool)
        result = sparse_als_projection(xyz, rows, files, self.left, self.right, self.rect,
                                       masks, masks, 1, 30)
        self.assertEqual(result["sparse_source_row"][30, 40], 9)
        self.assertEqual(result["sparse_source_file_index"][30, 40], 2)
        self.assertEqual(result["sparse_source_index"][30, 40], 0)
        self.assertAlmostEqual(float(result["sparse_disparity"][30, 40]), self.rect["P1"][0, 0] / 10, places=5)
        self.assertEqual(result["als_projection_state"].tolist(), [3, 2, 0, 3])

    def test_far_context_is_retained_but_not_seeded_outside_roi_search(self):
        masks = np.ones((60, 80), bool)
        result = sparse_als_projection(np.array([[0., 0., 40.]]), [7], [0],
                                       self.left, self.right, self.rect, masks, masks, 5, 15)
        self.assertEqual(result["als_projection_state"].tolist(), [4])
        self.assertTrue(np.isnan(result["sparse_disparity"]).all())

    def test_occlusion_in_right_image_alone_excludes_seed(self):
        # Distinct left pixels, same right pixel: the farther point is invisible
        # in the ALS right-view point raster and must not seed stereo matching.
        masks = np.ones((60, 80), bool)
        result = sparse_als_projection(np.array([[0., 0., 10.], [-1., 0., 20.]]), [7, 8], [0, 0],
                                       self.left, self.right, self.rect, masks, masks, 1, 30)
        self.assertEqual(result["als_projection_state"].tolist(), [3, 2])

    def test_rotated_camera_frame_roundtrip(self):
        angle = np.deg2rad(25.)
        R = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1.]])
        center = np.array([8., -4., 13.])
        left, right = view(1, [0, 0, 0]), view(2, [1, 0, 0])
        left.update(R=R.tolist(), t=(-R @ center).tolist())
        right.update(R=R.tolist(), t=(-R @ (center + R.T @ [1., 0., 0.])).tolist())
        rect = rectification(left, right)
        xyz = np.array([[0, 0, 10.], [1, .3, 12.]]) @ R + center
        uv1, _ = rectified_projection(xyz, left, rect["R1"], rect["P1"])
        uv2, _ = rectified_projection(xyz, right, rect["R2"], rect["P2"])
        q = np.column_stack([uv1, uv1[:, 0] - uv2[:, 0], np.ones(len(xyz))]) @ rect["Q"].T
        reconstructed = (q[:, :3] / q[:, 3:4]) @ rect["R1"] @ R + center
        np.testing.assert_allclose(reconstructed, xyz, atol=1e-9)

    def test_geometry_only_pair_selection_positive_disparity_and_bounds(self):
        settings = dict(grid_axis_count=5, min_angle_deg=3, max_angle_deg=20, rectification_alpha=0)
        left, right, rect, chosen, ledger = select_pair([self.right, self.left], [-1, -1, 9], [1, 1, 11], settings)
        self.assertEqual((left["image_id"], right["image_id"]), (1, 2))
        self.assertEqual(chosen["status"], "ELIGIBLE")
        self.assertEqual(len(ledger), 1)
        low, high = disparity_bounds([-1, -1, 9], [1, 1, 11], left, right, rect, 2)
        self.assertLessEqual(low, 100 / 11)
        self.assertGreaterEqual(high, 100 / 9)

    def test_zero_baseline_and_half_open_roi(self):
        with self.assertRaises(ValueError):
            rectification(self.left, self.left)
        mask = inside_box(np.array([[0, 0, 0], [1, 0, 0], [-.1, 0, 0]]), [0, 0, 0], [1, 1, 1])
        self.assertEqual(mask.tolist(), [True, False, False])


if __name__ == "__main__":
    unittest.main()

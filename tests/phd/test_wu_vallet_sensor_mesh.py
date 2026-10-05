from __future__ import annotations

import unittest

import numpy as np

from src.phd.wu_vallet_p3_v1.sensor_mesh import (
    ALSMeshConfig, ImageMeshConfig, als_acquisition_to_sensor_mesh, image_depth_to_sensor_mesh,
)


class WuValletImageSensorMeshTest(unittest.TestCase):
    def setUp(self):
        self.K = np.array([[2., 0., 1.], [0., 2., 1.], [0., 0., 1.]])
        self.config = ImageMeshConfig(max_edge_length_m=4.0, max_depth_jump_m=0.5)

    def test_plane_reconstructs_camera_z_grid_and_native_pixel_ids(self):
        result = image_depth_to_sensor_mesh(np.full((3, 3), 2.0), self.K, np.eye(3), np.zeros(3), self.config)
        mesh = result["mesh"]
        self.assertEqual(len(mesh.vertices), 9)
        self.assertEqual(len(mesh.triangles), 8)
        np.testing.assert_array_equal(mesh.native_rows, np.arange(9))
        np.testing.assert_allclose(mesh.vertices[4], [0, 0, 2])
        np.testing.assert_allclose(mesh.vertices[0], [-1, -1, 2])
        np.testing.assert_array_equal(result["pixel_uv"][4], [1, 1])
        self.assertTrue(result["meshed_pixel_mask"].all())

    def test_world_camera_pose_and_optical_origin_roundtrip(self):
        R = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
        t = np.array([1., 2., 3.])
        result = image_depth_to_sensor_mesh(np.full((3, 3), 2.0), self.K, R, t, self.config)
        mesh = result["mesh"]
        camera = mesh.vertices @ R.T + t
        projected = camera @ self.K.T
        np.testing.assert_allclose(projected[:, :2] / projected[:, 2:], result["pixel_uv"], atol=1e-12)
        np.testing.assert_allclose(camera[:, 2], 2.0)
        np.testing.assert_allclose(mesh.optical_origins, np.broadcast_to(-R.T @ t, mesh.vertices.shape))

    def test_missing_depth_creates_holes_without_delaunay_bridge(self):
        depth = np.full((3, 3), 2.0)
        depth[1, 1] = np.nan
        result = image_depth_to_sensor_mesh(depth, self.K, np.eye(3), np.zeros(3), self.config)
        self.assertEqual(result["diagnostics"]["valid_positive_depth_pixels"], 8)
        self.assertEqual(len(result["mesh"].triangles), 2)
        self.assertNotIn(4, result["pixel_ids"].tolist())
        self.assertFalse(result["meshed_pixel_mask"][1, 1])

    def test_depth_discontinuity_is_excluded_with_explicit_config(self):
        result = image_depth_to_sensor_mesh(np.array([[2., 2.], [2., 5.]]), self.K,
                                            np.eye(3), np.zeros(3), self.config)
        self.assertEqual(result["diagnostics"]["faces_with_depth_jump"], 2)
        self.assertEqual(len(result["mesh"].triangles), 0)
        self.assertEqual(len(result["mesh"].vertices), 0)
        self.assertEqual(result["diagnostics"]["valid_but_unmeshed_pixels"], 4)

    def test_zero_negative_infinite_depths_do_not_enter_mesh(self):
        depth = np.array([[0., -1.], [np.inf, 2.]])
        result = image_depth_to_sensor_mesh(depth, self.K, np.eye(3), np.zeros(3), self.config)
        self.assertEqual(result["diagnostics"]["invalid_or_nonpositive_depth_pixels"], 3)
        self.assertEqual(len(result["mesh"].vertices), 0)

    def test_nonrotation_and_missing_thresholds_fail(self):
        with self.assertRaises(ValueError):
            image_depth_to_sensor_mesh(np.ones((3, 3)), self.K, 2 * np.eye(3), np.zeros(3), self.config)
        with self.assertRaises(TypeError):
            ImageMeshConfig()


class WuValletALSSensorMeshTest(unittest.TestCase):
    def setUp(self):
        self.points = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [1., 1., 0.]])
        self.scan = np.array([0, 0, 1, 1])
        self.beam = np.array([0, 1, 0, 1])
        self.gps = np.array([0., 1., 2., 3.])
        self.times = np.array([0., 3.])
        self.trajectory = np.array([[0., 0., 10.], [3., 0., 10.]])
        self.config = ALSMeshConfig(max_edge_length_m=2., max_scan_gap=1, max_beam_gap=1,
                                    max_time_gap_s=3., trajectory_coordinate_role="sensor_optical_center")

    def build(self, **changes):
        args = dict(points=self.points, scan_ids=self.scan, beam_orders=self.beam, gps_times=self.gps,
                    trajectory_times=self.times, trajectory_positions=self.trajectory, config=self.config)
        args.update(changes)
        return als_acquisition_to_sensor_mesh(**args)

    def test_scan_order_mesh_interpolates_actual_origins_and_preserves_native_rows(self):
        rows = np.array([105, 200, 111, 9])
        result = self.build(native_rows=rows)
        mesh = result["mesh"]
        self.assertEqual(len(mesh.triangles), 2)
        np.testing.assert_array_equal(mesh.vertices, self.points)
        np.testing.assert_array_equal(mesh.native_rows, rows)
        np.testing.assert_allclose(mesh.optical_origins[:, 0], self.gps)
        np.testing.assert_allclose(mesh.optical_origins[:, 2], 10.0)

    def test_out_of_support_times_fail_instead_of_clamping(self):
        with self.assertRaisesRegex(ValueError, "outside trajectory support"):
            self.build(gps_times=np.array([0., 1., 2., 4.]))
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            self.build(trajectory_times=np.array([0., 0.]))

    def test_duplicate_returns_are_not_selected_implicitly(self):
        with self.assertRaisesRegex(ValueError, "select returns explicitly"):
            self.build(scan_ids=np.array([0, 0, 0, 1]), beam_orders=np.array([0, 1, 0, 1]))

    def test_scan_gap_filter_does_not_invent_missing_scanlines(self):
        result = self.build(scan_ids=np.array([0, 0, 2, 2]))
        self.assertEqual(result["diagnostics"]["faces_with_scan_gap"], 2)
        self.assertEqual(len(result["mesh"].vertices), 0)
        self.assertEqual(len(result["mesh"].triangles), 0)

    def test_one_scanline_or_unresolved_sensor_center_fails(self):
        with self.assertRaisesRegex(ValueError, "collinear"):
            self.build(scan_ids=np.zeros(4, dtype=int), beam_orders=np.arange(4))
        with self.assertRaisesRegex(ValueError, "sensor_optical_center"):
            ALSMeshConfig(max_edge_length_m=2., max_scan_gap=1, max_beam_gap=1,
                          max_time_gap_s=3., trajectory_coordinate_role="GPS_antenna_unresolved")


if __name__ == "__main__":
    unittest.main()

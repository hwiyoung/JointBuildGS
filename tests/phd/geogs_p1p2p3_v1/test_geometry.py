import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np

MODULE = Path(__file__).resolve().parents[3] / "scripts/phd/geogs_p1p2p3_v1/evaluation/geometry.py"
spec = importlib.util.spec_from_file_location("geogs_geometry", MODULE)
geometry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geometry)


class GeometryEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.vertices = np.array([[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0]], dtype=float)
        self.faces = np.array([[0, 1, 2], [0, 2, 3]])
        self.bounds = [[0, 2], [0, 2], [-1, 1]]

    def test_triangle_interior_distance_is_not_nearest_vertex(self):
        query = np.array([[1, 1, 0.25]])
        actual = geometry.points_to_triangle_surface(query, self.vertices, self.faces)
        nearest_vertex = np.linalg.norm(self.vertices - query, axis=1).min()
        self.assertAlmostEqual(float(actual[0]), 0.25, places=6)
        self.assertGreater(nearest_vertex, 1.4)

    def test_crossing_triangle_clips_and_halfopen_face_is_excluded(self):
        vertices, faces = geometry.clip_mesh_to_box(self.vertices, self.faces, [[0.5, 1.5], [0.5, 1.5], [-1, 1]])
        self.assertAlmostEqual(float(geometry.triangle_areas(vertices, faces).sum()), 1.0)
        self.assertTrue(np.all((vertices[:, :2] >= 0.5) & (vertices[:, :2] <= 1.5)))
        outside_face = np.array([[2, 0, -0.5], [2, 1, -0.5], [2, 0, 0.5]])
        _, upper_faces = geometry.clip_mesh_to_box(outside_face, [[0, 1, 2]], self.bounds)
        self.assertEqual(len(upper_faces), 0)
        self.assertFalse(geometry.inside_half_open([[2, 1, 0]], self.bounds)[0])

    def test_sampling_density_does_not_change_perfect_plane_scores(self):
        coordinates = np.arange(0.025, 2, 0.05)
        xx, yy = np.meshgrid(coordinates, coordinates)
        reference = np.column_stack((xx.ravel(), yy.ravel(), np.zeros(xx.size)))
        samples = []
        for spacing in (0.05, 0.1, 0.2):
            metrics, arrays = geometry.evaluate_geometry(self.vertices, self.faces, reference, self.bounds,
                                                        spacing=spacing, reference_voxel_size=0.05)
            self.assertEqual(metrics["status"], "ASSESSED_DEVELOPMENT_ONLY")
            self.assertEqual(metrics["thresholds"][0]["f1"], 1.0)
            self.assertLess(metrics["reference_to_prediction_triangle"]["p95"], 1e-6)
            samples.append(len(arrays["prediction_surface_samples"]))
        self.assertEqual(samples, [1600, 400, 100])
        first, _ = geometry.sample_surface(self.vertices, self.faces, 0.1, 0)
        repeat, _ = geometry.sample_surface(self.vertices, self.faces, 0.1, 0)
        np.testing.assert_array_equal(first, repeat)

    def test_reference_absence_and_reconstruction_failure_are_distinct(self):
        absent, _ = geometry.evaluate_geometry(self.vertices, self.faces, [], self.bounds)
        failed, arrays = geometry.evaluate_geometry([], [], [[1, 1, 0]], self.bounds)
        self.assertEqual(absent["status"], "NOT_ASSESSED_REFERENCE_ABSENT")
        self.assertIsNone(absent["thresholds"][0]["f1"])
        self.assertEqual(failed["status"], "RECONSTRUCTION_FAILURE")
        self.assertEqual(failed["thresholds"][0]["f1"], 0.0)
        self.assertTrue(np.isinf(arrays["reference_to_triangle_distance"]).all())

    def test_reference_voxel_uses_fixed_origin_original_points_and_stable_order(self):
        points = np.array([[-0.01, 0.01, 0.01], [-0.04, 0.04, 0.04], [0.09, 0.09, 0.09], [0.05, 0.05, 0.05]])
        selected, indices = geometry.voxel_reference(points, 0.1)
        reordered, _ = geometry.voxel_reference(points[::-1], 0.1)
        np.testing.assert_array_equal(selected, points[indices])
        np.testing.assert_array_equal(selected, reordered)
        self.assertEqual(len(selected), 2)

    def test_distance_archive_is_readable_and_cannot_overwrite(self):
        _, arrays = geometry.evaluate_geometry(self.vertices, self.faces, [[1, 1, 0]], self.bounds)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "distances.npz"
            geometry.save_distance_arrays(path, arrays)
            with np.load(path, allow_pickle=False) as restored:
                np.testing.assert_array_equal(restored["clipped_triangles"], arrays["clipped_triangles"])
            with self.assertRaises(FileExistsError):
                geometry.save_distance_arrays(path, arrays)


if __name__ == "__main__":
    unittest.main()

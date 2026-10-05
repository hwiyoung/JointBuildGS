from __future__ import annotations

import unittest

import numpy as np

from src.phd.wu_vallet_p3_v1.ray_update import (
    CHANGED, CONSISTENT, SINGLE, RayUpdateConfig, SensorMesh, classify_and_update,
)


def square(z: float, x: float = 0.0, native_start: int = 0) -> SensorMesh:
    vertices = np.array([[x, 0, z], [x + 1, 0, z], [x + 1, 1, z], [x, 1, z]], dtype=float)
    origins = vertices.copy()
    origins[:, 2] = 10.0
    return SensorMesh(vertices, np.array([[0, 1, 2], [0, 2, 3]]), origins,
                      np.arange(native_start, native_start + 4))


def joined(*meshes: SensorMesh) -> SensorMesh:
    offsets = np.cumsum([0] + [len(mesh.vertices) for mesh in meshes[:-1]])
    return SensorMesh(np.concatenate([mesh.vertices for mesh in meshes]),
                      np.concatenate([mesh.triangles + offset for mesh, offset in zip(meshes, offsets)]),
                      np.concatenate([mesh.optical_origins for mesh in meshes]))


class WuValletRayUpdateTest(unittest.TestCase):
    def setUp(self):
        self.config = RayUpdateConfig(distance_tolerance_m=0.1)

    def test_close_surface_retains_original_old_points_and_native_rows(self):
        old, new = square(1.0, native_start=100), square(1.05, native_start=900)
        result = classify_and_update(old, new, self.config)
        self.assertTrue(np.all(result["old_face_labels"] == CONSISTENT))
        self.assertTrue(np.all(result["new_face_labels"] == CONSISTENT))
        np.testing.assert_array_equal(result["updated_points"], old.vertices)
        np.testing.assert_array_equal(result["updated_native_rows"], np.arange(100, 104))
        self.assertEqual(result["diagnostics"]["admitted_new_vertices"], 0)

    def test_demolished_roof_is_replaced_by_current_lower_surface(self):
        old, new = square(2), square(0)
        result = classify_and_update(old, new, self.config)
        self.assertTrue(np.all(result["old_face_labels"] == CHANGED))
        self.assertTrue(np.all(result["new_face_labels"] == CHANGED))
        np.testing.assert_array_equal(result["updated_points"], new.vertices)
        self.assertGreater(result["diagnostics"]["directions"]["new_to_old"]["target_hits"], 0)

    def test_fig6_construction_removes_old_background_but_is_not_general_currentness_proof(self):
        old, new = square(0), square(2)
        result = classify_and_update(old, new, self.config)
        np.testing.assert_array_equal(result["updated_points"], new.vertices)
        self.assertTrue(np.all(result["old_face_labels"] == CHANGED))
        self.assertGreater(result["diagnostics"]["directions"]["old_to_new"]["target_hits"], 0)
        self.assertIn("old_background_removed", result["reproduction_scope"]["construction_policy"])
        self.assertFalse(result["reproduction_scope"]["native_2026_reproduction"])

    def test_disjoint_coverage_preserves_both_sources_without_inventing_currentness(self):
        old, new = square(0, x=0), square(1, x=3)
        result = classify_and_update(old, new, self.config)
        self.assertTrue(np.all(result["old_face_labels"] == SINGLE))
        self.assertTrue(np.all(result["new_face_labels"] == SINGLE))
        self.assertEqual(len(result["updated_points"]), 8)
        self.assertIsNone(result["reproduction_scope"]["scientific_verdict"])

    def test_ray_stops_at_endpoint_does_not_hit_surface_behind_observation(self):
        # The current upper square is internally consistent; the old plane lies
        # beyond its endpoint, so current-to-old must not record an intersection.
        result = classify_and_update(square(0), square(2), self.config)
        self.assertEqual(result["diagnostics"]["directions"]["new_to_old"]["target_hits"], 0)

    def test_self_occluded_source_samples_do_not_assert_empty_space(self):
        old = square(1)
        new = joined(square(2), square(0))
        result = classify_and_update(old, new, self.config)
        stats = result["diagnostics"]["directions"]["new_to_old"]
        self.assertGreater(stats["source_self_occluded_rays"], 0)
        self.assertEqual(stats["target_hits"], 0)
        self.assertTrue(np.all(result["new_face_labels"][2:] == SINGLE))

    def test_large_triangle_surface_distance_is_not_nearest_vertex_distance(self):
        old = SensorMesh(np.array([[-5, -5, 0], [10, -5, 0], [-5, 10, 0.0]]),
                         np.array([[0, 1, 2]]),
                         np.array([[-5, -5, 10], [10, -5, 10], [-5, 10, 10.0]]))
        new = square(0.02)
        result = classify_and_update(old, new, self.config)
        self.assertTrue(np.all(result["new_face_labels"] == CONSISTENT))
        self.assertEqual(result["diagnostics"]["admitted_new_vertices"], 0)

    def test_missing_sensor_origins_and_invalid_topology_fail_explicitly(self):
        mesh = square(0)
        with self.assertRaises(TypeError):
            SensorMesh(mesh.vertices, mesh.triangles)
        with self.assertRaises(ValueError):
            SensorMesh(mesh.vertices, np.array([[0, 1, 99]]), mesh.optical_origins)
        with self.assertRaises(ValueError):
            SensorMesh(mesh.vertices, np.array([[0, 0, 1]]), mesh.optical_origins)
        with self.assertRaises(ValueError):
            SensorMesh(mesh.vertices, mesh.triangles, np.zeros((1, 3)))
        with self.assertRaises(TypeError):
            RayUpdateConfig()

    def test_inputs_remain_unchanged(self):
        old, new = square(0), square(2)
        before = old.vertices.copy()
        classify_and_update(old, new, self.config)
        np.testing.assert_array_equal(old.vertices, before)
        self.assertFalse(old.vertices.flags.writeable)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

import numpy as np

from src.phd.wu_vallet_p3_v1.ray_update import (
    CHANGED, CONSISTENT, SINGLE, RayUpdateConfig,
    classify_and_update as reference_update,
)
from src.phd.wu_vallet_p3_v2.ray_runtime import (
    RuntimeConfig, SensorMesh, TriangleScene, classify_and_update, region_diagnostics,
)
from tests.phd.test_wu_vallet_ray_update import joined, square


class AcceleratedRayRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.config = RuntimeConfig(0.1, nthreads=2, query_chunk_size=5)

    def test_five_controlled_scenes_match_v1_face_vertex_and_update_results(self):
        scenes = [
            (square(1, native_start=100), square(1.05, native_start=900)),
            (square(2), square(0)),
            (square(0), square(2)),
            (square(0), square(1, x=3)),
            (square(1), joined(square(2), square(0))),
        ]
        for old, new in scenes:
            with self.subTest(old_z=old.vertices[0, 2], new_z=new.vertices[0, 2], n=len(new.vertices)):
                expected = reference_update(old, new, RayUpdateConfig(0.1))
                actual = classify_and_update(old, new, self.config)
                for key in ("old_face_labels", "new_face_labels", "old_vertex_labels", "new_vertex_labels",
                            "old_keep_mask", "new_keep_mask", "updated_points", "updated_source", "updated_native_rows"):
                    np.testing.assert_array_equal(actual[key], expected[key], err_msg=key)
                for side in ("old", "new"):
                    np.testing.assert_array_equal(actual[f"raw_{side}_face_labels"], actual[f"{side}_face_labels"])

    def test_only_current_rays_can_remove_obstructing_old_roof_without_old_origins(self):
        old0 = square(2, native_start=10)
        old = SensorMesh(old0.vertices, old0.triangles, None, old0.native_rows)
        result = classify_and_update(old, square(0), RuntimeConfig(0.1, direction_mode="ONLY_CURRENT_IMAGE_RAYS", nthreads=2))
        self.assertTrue(np.all(result["old_face_labels"] == CHANGED))
        self.assertEqual(result["reproduction_scope"]["executed_directions"], ["new_to_old"])
        self.assertEqual(result["reproduction_scope"]["optical_origins"]["old"], "missing_not_invented")
        self.assertNotIn("old_to_new", result["diagnostics"]["directions"])

    def test_only_current_rays_preserve_old_background_behind_new_construction(self):
        old0 = square(0)
        old = SensorMesh(old0.vertices, old0.triangles, None)
        result = classify_and_update(old, square(2), RuntimeConfig(0.1, direction_mode="ONLY_CURRENT_IMAGE_RAYS", nthreads=2))
        self.assertTrue(np.all(result["old_face_labels"] == SINGLE))
        self.assertEqual(len(result["updated_points"]), 8)
        self.assertIsNone(result["reproduction_scope"]["scientific_verdict"])
        self.assertFalse(result["reproduction_scope"]["native_2026_reproduction"])

    def test_missing_origins_never_silently_enable_bidirectional(self):
        base = square(0)
        missing = SensorMesh(base.vertices, base.triangles, None)
        with self.assertRaisesRegex(ValueError, "BIDIRECTIONAL"):
            classify_and_update(missing, square(2), self.config)
        with self.assertRaisesRegex(ValueError, "current image"):
            classify_and_update(square(2), missing, RuntimeConfig(0.1, direction_mode="ONLY_CURRENT_IMAGE_RAYS"))
        with self.assertRaises(ValueError):
            RuntimeConfig(0.1, direction_mode="automatic")

    def test_exact_triangle_distance_interior_edge_vertex_and_tolerance_boundary(self):
        large = SensorMesh(np.array([[-5, -5, 0], [10, -5, 0], [-5, 10, 0.0]]),
                           np.array([[0, 1, 2]]), None)
        scene = TriangleScene(large, self.config)
        distances = scene.distances(np.array([[0, 0, .1], [-5, -5, .1], [-6, -5, 0], [0, 0, .100001]]))
        np.testing.assert_allclose(distances, [.1, .1, 1., .100001], rtol=0, atol=1e-12)
        updated = classify_and_update(square(1), square(1.1), self.config)
        self.assertTrue(np.all(updated["new_face_labels"] == CONSISTENT))

    def test_finite_endpoint_margin_and_front_of_origin_exclusion(self):
        scene = TriangleScene(square(1), self.config)
        starts = np.array([[.25, .25, 10.]] * 5)
        endpoints = np.array([[.25, .25, 1.], [.25, .25, 1.1], [.25, .25, .9],
                              [.25, .25, .89999], [.25, .25, 11.]])
        ids, distance = scene.first_hits(starts, endpoints, .1)
        np.testing.assert_array_equal(ids >= 0, [False, False, False, True, False])
        self.assertAlmostEqual(distance[3], 9.)

    def test_origin_on_triangle_does_not_hide_farther_hit(self):
        scene = TriangleScene(joined(square(2), square(1)), self.config)
        ids, distance = scene.first_hits(np.array([[.25, .25, 2.]]), np.array([[.25, .25, 0.]]), .1)
        self.assertGreaterEqual(ids[0], 2)
        self.assertAlmostEqual(distance[0], 1.)

    def test_source_occlusion_blocks_free_space_claim(self):
        result = classify_and_update(square(1), joined(square(2), square(0)), self.config)
        stats = result["diagnostics"]["directions"]["new_to_old"]
        self.assertEqual(stats["target_hits"], 0)
        self.assertGreater(stats["source_self_occluded_rays"], 0)
        self.assertTrue(np.all(result["new_face_labels"][2:] == SINGLE))

    def test_edge_connected_area_filter_preserves_raw_results(self):
        old, new = joined(square(2), square(2, x=3)), joined(square(0), square(0, x=3))
        result = classify_and_update(old, new, RuntimeConfig(.1, small_region_area_m2=1.1, nthreads=2))
        self.assertTrue(np.all(result["raw_old_face_labels"] == CHANGED))
        self.assertTrue(np.all(result["old_face_labels"] == SINGLE))
        self.assertEqual(result["region_diagnostics"]["old"]["component_count"], 2)
        np.testing.assert_array_equal(result["region_diagnostics"]["old"]["component_face_counts"], [2, 2])
        np.testing.assert_allclose(result["region_diagnostics"]["old"]["component_areas_m2"], [1., 1.])
        self.assertEqual(len(result["raw_updated_points"]), 8)
        self.assertEqual(len(result["updated_points"]), 16)

    def test_area_filter_uses_shared_edges_not_merely_shared_vertices(self):
        vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0]], dtype=float)
        mesh = SensorMesh(vertices, np.array([[0, 1, 2], [0, 3, 4]]), None)
        refined, diag = region_diagnostics(mesh, np.array([CHANGED, CHANGED]), .6)
        self.assertEqual(diag["component_count"], 2)
        self.assertTrue(np.all(refined == SINGLE))

    def test_empty_surface_and_isolated_vertices_are_explicit(self):
        old = SensorMesh(np.array([[0., 0, 0]]), np.empty((0, 3), dtype=int), None, np.array([13]))
        result = classify_and_update(old, square(2), RuntimeConfig(.1, direction_mode="ONLY_CURRENT_IMAGE_RAYS", nthreads=2))
        self.assertEqual(result["diagnostics"]["isolated_vertices"]["old"], 1)
        self.assertTrue(result["old_keep_mask"][0])
        self.assertEqual(result["updated_native_rows"][0], 13)

    def test_native_rows_and_input_geometry_are_immutable(self):
        base = square(0)
        with self.assertRaises(ValueError):
            SensorMesh(base.vertices, base.triangles, None, np.array([1, 1, 2, 3]))
        old = SensorMesh(base.vertices, base.triangles, None)
        original = old.vertices.copy()
        classify_and_update(old, square(2), RuntimeConfig(.1, direction_mode="ONLY_CURRENT_IMAGE_RAYS", nthreads=2))
        np.testing.assert_array_equal(original, old.vertices)
        self.assertFalse(old.vertices.flags.writeable)

    def test_partial_old_origins_skip_rays_but_preserve_target_geometry(self):
        base = joined(square(0), square(0, x=3))
        origins = base.optical_origins.copy(); origins[:4] = np.nan
        old = SensorMesh(base.vertices, base.triangles, origins)
        new = joined(square(2), square(2, x=3))
        result = classify_and_update(old, new, self.config)
        self.assertTrue(result["old_keep_mask"][:4].all())
        self.assertFalse(result["old_keep_mask"][4:].any())
        self.assertEqual(result["reproduction_scope"]["unavailable_origin_vertices"]["old"], 4)
        stats = result["diagnostics"]["directions"]["old_to_new"]
        self.assertEqual(stats["unavailable_origin_sample_rays"], 8)
        self.assertEqual(stats["degenerate_sample_rays"], 0)

    def test_missing_current_or_invalid_partial_origin_is_rejected(self):
        base = square(0)
        origins = base.optical_origins.copy(); origins[0, 0] = np.nan
        with self.assertRaises(ValueError):
            SensorMesh(base.vertices, base.triangles, origins)
        origins[0] = np.nan
        missing = SensorMesh(base.vertices, base.triangles, origins)
        with self.assertRaises(ValueError):
            classify_and_update(square(2), missing, self.config)


if __name__ == "__main__":
    unittest.main()

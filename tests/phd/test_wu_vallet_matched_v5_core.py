"""Analytic scene expectations, independent of any UAS or native region result."""
from __future__ import annotations

import unittest
import numpy as np

from src.phd.wu_vallet_matched_v5.core import (
    SensorMesh, RuntimeConfig, classify_relations, components, assemble_status,
)


def plane(z, x=0., size=2.):
    vertices = np.array([[x, 0, z], [x + size, 0, z], [x + size, size, z], [x, size, z]], float)
    triangles = np.array([[0, 1, 2], [0, 2, 3]])
    origins = vertices.copy(); origins[:, 2] = 10
    return SensorMesh(vertices, triangles, origins)


def join(*meshes):
    offsets = np.cumsum([0] + [len(m.vertices) for m in meshes[:-1]])
    return SensorMesh(np.concatenate([m.vertices for m in meshes]),
                      np.concatenate([m.triangles + k for m, k in zip(meshes, offsets)]),
                      np.concatenate([m.optical_origins for m in meshes]))


def execute(old, new, area=1., sampling="vertices_and_centroid"):
    raw = classify_relations(old, new, RuntimeConfig(.1, ray_sampling=sampling, nthreads=2))
    selected = {side: assemble_status(len(mesh.vertices), mesh.triangles, raw[f"raw_{side}_face_labels"],
                components(mesh.vertices, mesh.triangles, raw[f"raw_{side}_face_labels"]), area)
                for side, mesh in (("old", old), ("new", new))}
    return raw, selected


class MatchedCorrectnessTests(unittest.TestCase):
    def test_unchanged_plane_keeps_exact_old_geometry_only(self):
        old, new = plane(1), plane(1.05)
        raw, selected = execute(old, new)
        self.assertTrue((raw["raw_old_face_labels"] == "consistent").all())
        self.assertTrue((raw["raw_new_face_labels"] == "consistent").all())
        self.assertTrue(selected["old"]["old_keep"].all())
        self.assertFalse(selected["new"]["new_keep"].any())

    def test_demolition_removes_old_roof_adds_current_ground(self):
        raw, selected = execute(plane(4), plane(0))
        self.assertTrue((raw["raw_old_face_labels"] == "changed").all())
        self.assertFalse(selected["old"]["old_keep"].any())
        self.assertTrue(selected["new"]["new_keep"].all())
        self.assertEqual(raw["diagnostics"]["directions"]["old_to_new"]["target_hits"], 0)
        self.assertGreater(raw["diagnostics"]["directions"]["new_to_old"]["target_hits"], 0)

    def test_construction_removes_old_ground_adds_current_roof(self):
        raw, selected = execute(plane(0), plane(4))
        self.assertFalse(selected["old"]["old_keep"].any())
        self.assertTrue(selected["new"]["new_keep"].all())
        self.assertGreater(raw["diagnostics"]["directions"]["old_to_new"]["target_hits"], 0)
        self.assertEqual(raw["diagnostics"]["directions"]["new_to_old"]["target_hits"], 0)

    def test_large_erroneous_surface_has_same_observable_evidence_as_demolition(self):
        # The true current scene remains z=4, but a wrong image depth reports z=0.
        # Truth is known to this test alone, not supplied to the update function.
        raw, selected = execute(plane(4), plane(0), area=1.)
        self.assertTrue(selected["new"]["new_keep"].all())
        self.assertFalse(selected["old"]["old_keep"].any())
        self.assertEqual(raw["diagnostics"]["directions"]["new_to_old"]["target_hits"], 8)

    def test_small_erroneous_surface_is_filtered_and_never_readmitted(self):
        raw, selected = execute(plane(4, size=.5), plane(0, size=.5), area=1.)
        self.assertTrue((raw["raw_new_face_labels"] == "changed").all())
        self.assertTrue((selected["new"]["status"] == "filtered").all())
        self.assertFalse(selected["new"]["new_keep"].any())
        self.assertTrue(selected["old"]["old_keep"].all())

    def test_raw_ray_api_cannot_leak_v2_assembled_point_masks(self):
        result = classify_relations(plane(4), plane(0), RuntimeConfig(.1, nthreads=2))
        self.assertNotIn("new_keep_mask", result)
        self.assertNotIn("updated_points", result)
        with self.assertRaisesRegex(ValueError, "area zero"):
            classify_relations(plane(4), plane(0), RuntimeConfig(.1, small_region_area_m2=1., nthreads=2))

    def test_own_foreground_blocks_background_free_space_claim(self):
        raw, selected = execute(plane(2), join(plane(4), plane(0)))
        self.assertEqual(raw["diagnostics"]["directions"]["new_to_old"]["target_hits"], 0)
        self.assertGreater(raw["diagnostics"]["directions"]["new_to_old"]["source_self_occluded_rays"], 0)
        self.assertTrue((raw["raw_new_face_labels"][2:] == "single").all())
        # This unknown/occluded raw SINGLE is explicitly retained by this declared
        # baseline policy, so SINGLE must not be called certified current geometry.
        self.assertTrue(selected["new"]["new_keep"][4:].all())

    def test_consistent_surface_is_not_deleted_by_conflicting_ray(self):
        # Equal foreground exists in both meshes; a lower new surface is hidden.
        raw, selected = execute(plane(4), join(plane(4), plane(0)))
        self.assertTrue((raw["raw_old_face_labels"] == "consistent").all())
        self.assertTrue(selected["old"]["old_keep"].all())
        self.assertFalse(selected["new"]["new_keep"][:4].any())

    def test_unrelated_source_regions_remain_raw_single(self):
        raw, selected = execute(plane(0), plane(4, x=5.))
        for side in ("old", "new"):
            self.assertTrue((raw[f"raw_{side}_face_labels"] == "single").all())
        self.assertTrue(selected["old"]["old_keep"].all())
        self.assertTrue(selected["new"]["new_keep"].all())

    def test_unsupported_origin_triangle_fails_in_every_region_policy(self):
        base = plane(0); origins = base.optical_origins.copy(); origins[0] = np.nan
        old = SensorMesh(base.vertices, base.triangles, origins)
        with self.assertRaisesRegex(ValueError, "Unsupported old"):
            classify_relations(old, plane(4), RuntimeConfig(.1, nthreads=2))

    def test_unused_missing_origin_vertex_does_not_make_up_acquisition_ray(self):
        base = plane(0)
        old = SensorMesh(np.vstack((base.vertices, [20, 20, 0.])), base.triangles,
                         np.vstack((base.optical_origins, [np.nan] * 3)))
        raw, selected = execute(old, plane(4))
        self.assertTrue(selected["old"]["old_keep"][-1])
        self.assertEqual(selected["old"]["status"][-1], "unassessed")

    def test_mixed_consistent_changed_retains_shared_old_boundary(self):
        mesh = plane(0)
        labels = np.array(["consistent", "changed"])
        selected = assemble_status(4, mesh.triangles, labels, components(mesh.vertices, mesh.triangles, labels), 0.)
        np.testing.assert_array_equal(selected["old_keep"], [True, True, True, False])
        np.testing.assert_array_equal(selected["new_keep"], [False, False, False, True])
        self.assertTrue(selected["incident"]["accepted_changed"][0])
        self.assertTrue(selected["incident"]["consistent"][0])

    def test_filtered_shared_raw_single_point_has_independent_admission_evidence(self):
        mesh = plane(0)
        labels = np.array(["single", "changed"])
        selected = assemble_status(4, mesh.triangles, labels, components(mesh.vertices, mesh.triangles, labels), 3.)
        np.testing.assert_array_equal(selected["new_keep"], [True, True, True, False])
        self.assertEqual(selected["status"][0], "raw_single")
        self.assertTrue(selected["incident"]["filtered"][0])
        self.assertFalse(selected["new_keep"][3])

    def test_face_filter_uses_full_context_before_final_region_crop(self):
        mesh = plane(0)
        labels = np.array(["changed", "changed"])
        regions = components(mesh.vertices, mesh.triangles, labels)
        self.assertEqual(regions["area_m2"].tolist(), [4.])
        selected = assemble_status(4, mesh.triangles, labels, regions, 3.)
        # Cropping to the first triangle before measuring area would give 2 m2
        # and wrongly filter. The pipeline's final point crop follows this step.
        self.assertTrue(selected["new_keep"][[0, 1, 2]].all())

    def test_component_identity_corruption_is_rejected(self):
        mesh = plane(0); labels = np.array(["changed", "changed"])
        regions = components(mesh.vertices, mesh.triangles, labels)
        regions["face_component_id"][0] = -1
        with self.assertRaisesRegex(ValueError, "valid component"):
            assemble_status(4, mesh.triangles, labels, regions, 1.)


if __name__ == "__main__":
    unittest.main()

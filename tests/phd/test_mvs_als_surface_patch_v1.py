from __future__ import annotations

import unittest

import numpy as np

from scripts.phd.mvs_als_source_relation_v1 import run as relation
from scripts.phd.mvs_als_surface_patch_v1 import run as patches


PROFILE = {
    "neighbor_radius_m": 2.1,
    "maximum_normal_angle_deg": 20.0,
    "maximum_symmetric_point_to_plane_m": 0.25,
    "maximum_bridge_surface_variation": 0.15,
    "maximum_patch_radius_m": 4.0,
    "maximum_patch_cores": 32,
    "minimum_plane_fit_cores": 4,
    "patch_plane_rmse_m": 0.2,
    "patch_max_abs_residual_m": 0.4,
    "patch_max_local_normal_deg": 20.0,
    "minimum_patch_cores": 2,
    "minimum_dominant_relation_fraction": 0.6,
}


def rows_for(xyz: np.ndarray, labels: list[int], sources: list[int] | None = None) -> np.ndarray:
    rows = np.zeros(len(xyz), dtype=relation.OUTPUT_DTYPE)
    rows["x"], rows["y"], rows["z"] = xyz.T
    rows["nx"] = 0.0
    rows["ny"] = 0.0
    rows["nz"] = 1.0
    rows["relation_class"] = labels
    rows["core_source"] = sources or [0] * len(xyz)
    rows["surface_variation"] = 0.01
    return rows


class SurfacePatchV1Test(unittest.TestCase):
    def test_normal_break_and_source_boundary_block_edges(self):
        xyz = np.asarray([[0, 0, 0], [2, 0, 0], [4, 0, 0], [6, 0, 0]], dtype=np.float64)
        rows = rows_for(xyz, [2, 2, 2, 2], [0, 0, 1, 1])
        normals, valid = patches.normalized_normals(rows)
        normals[1] = [1, 0, 0]
        eligible, _reason = patches.bridge_eligibility(rows, valid, PROFILE)
        edges = patches.accepted_surface_edges(xyz, normals, eligible, rows["core_source"], PROFILE)
        self.assertEqual(edges.tolist(), [[2, 3]])

    def test_bounded_patches_are_deterministic_and_connected(self):
        xyz = np.asarray([[float(x), 0, 0] for x in range(0, 14, 2)], dtype=np.float64)
        rows = rows_for(xyz, [2] * len(xyz))
        normals, valid = patches.normalized_normals(rows)
        eligible, _reason = patches.bridge_eligibility(rows, valid, PROFILE)
        edges = patches.accepted_surface_edges(xyz, normals, eligible, rows["core_source"], PROFILE)
        first, _ = patches.guarded_kruskal_patches(xyz, rows["core_source"], eligible, edges, normals, PROFILE)
        second, _ = patches.guarded_kruskal_patches(xyz, rows["core_source"], eligible, edges, normals, PROFILE)
        np.testing.assert_array_equal(first, second)
        self.assertGreater(len(np.unique(first)), 1)
        for patch_id in np.unique(first):
            ids = np.flatnonzero(first == patch_id)
            self.assertLessEqual(np.max(xyz[ids, 0]) - np.min(xyz[ids, 0]), 8.0)

    def test_small_and_mixed_patches_fail_closed(self):
        xyz = np.asarray([[0, 0, 0], [2, 0, 0], [0, 4, 0]], dtype=np.float64)
        rows = rows_for(xyz, [2, 3, 4])
        normals, valid = patches.normalized_normals(rows)
        eligible, reason = patches.bridge_eligibility(rows, valid, PROFILE)
        edges = patches.accepted_surface_edges(xyz, normals, eligible, rows["core_source"], PROFILE)
        assignment, _ = patches.guarded_kruskal_patches(xyz, rows["core_source"], eligible, edges, normals, PROFILE)
        membership, summaries = patches.summarize_patches(rows, xyz, normals, assignment, PROFILE, 2.0)
        self.assertEqual(int(membership["patch_relation_class"][2]), 5)
        self.assertEqual(int(membership["patch_status"][2]), 2)
        pair = np.flatnonzero(assignment == assignment[0])
        self.assertEqual(len(pair), 2)
        self.assertTrue(np.all(membership["patch_relation_class"][pair] == 5))
        self.assertTrue(np.all(membership["patch_status"][pair] == 3))
        self.assertEqual(len(summaries), 2)

    def test_invalid_normal_stays_unassigned(self):
        xyz = np.asarray([[0, 0, 0], [2, 0, 0]], dtype=np.float64)
        rows = rows_for(xyz, [5, 5])
        rows["nz"][1] = np.nan
        normals, valid = patches.normalized_normals(rows)
        eligible, reason = patches.bridge_eligibility(rows, valid, PROFILE)
        edges = patches.accepted_surface_edges(xyz, normals, eligible, rows["core_source"], PROFILE)
        assignment, _ = patches.guarded_kruskal_patches(xyz, rows["core_source"], eligible, edges, normals, PROFILE)
        membership, _ = patches.summarize_patches(rows, xyz, normals, assignment, PROFILE, 2.0, reason)
        self.assertEqual(int(membership["patch_id"][1]), 0)
        self.assertEqual(int(membership["patch_relation_class"][1]), 5)
        self.assertEqual(int(membership["patch_status"][1]), 0)
        self.assertEqual(int(membership["unassigned_reason"][1]), 1)

    def test_class_5_and_high_variation_are_preserved_without_bridging(self):
        xyz = np.asarray([[0, 0, 0], [2, 0, 0], [4, 0, 0]], dtype=np.float64)
        rows = rows_for(xyz, [2, 5, 2])
        rows["surface_variation"][2] = 0.9
        normals, valid = patches.normalized_normals(rows)
        eligible, reason = patches.bridge_eligibility(rows, valid, PROFILE)
        self.assertEqual(eligible.tolist(), [True, False, False])
        self.assertEqual(reason.tolist(), [0, 2, 3])
        edges = patches.accepted_surface_edges(xyz, normals, eligible, rows["core_source"], PROFILE)
        assignment, _ = patches.guarded_kruskal_patches(
            xyz, rows["core_source"], eligible, edges, normals, PROFILE,
        )
        membership, _ = patches.summarize_patches(
            rows, xyz, normals, assignment, PROFILE, 2.0, reason,
        )
        self.assertEqual(membership["patch_id"].tolist(), [1, 0, 0])
        self.assertEqual(membership["unassigned_reason"].tolist(), [0, 2, 3])

    def test_candidate_evidence_is_never_smoothed_to_compatible(self):
        xyz = np.asarray([[0, 0, 0], [2, 0, 0], [0, 2, 0], [2, 2, 0]], dtype=np.float64)
        rows = rows_for(xyz, [1, 1, 1, 2])
        normals, valid = patches.normalized_normals(rows)
        eligible, reason = patches.bridge_eligibility(rows, valid, PROFILE)
        edges = patches.accepted_surface_edges(xyz, normals, eligible, rows["core_source"], PROFILE)
        assignment, _ = patches.guarded_kruskal_patches(
            xyz, rows["core_source"], eligible, edges, normals, PROFILE,
        )
        membership, _ = patches.summarize_patches(
            rows, xyz, normals, assignment, PROFILE, 2.0, reason,
        )
        self.assertTrue(np.all(membership["patch_relation_class"] == 5))
        self.assertTrue(np.all(membership["patch_status"] == 3))


if __name__ == "__main__":
    unittest.main()

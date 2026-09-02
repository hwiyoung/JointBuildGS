from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from scripts.phd.mvs_als_current_view_render_v1 import render


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/phd/mvs_als_current_view_render_v1/pilot_v1.json"


class CurrentViewRenderV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = render.load_config(CONFIG)

    def test_contract_freezes_three_exact_views_and_no_prohibited_input_path(self) -> None:
        views = self.cfg["inputs"]["selected_views"]
        self.assertEqual([row["role"] for row in views], ["TOP", "OBLIQUE_A", "OBLIQUE_B"])
        self.assertEqual([row["colmap_image_id"] for row in views], [90, 840, 659])
        self.assertEqual(len({row["image_sha256"] for row in views}), 3)
        self.assertTrue(all(len(row["image_sha256"]) == 64 for row in views))
        input_text = json.dumps(self.cfg["inputs"], sort_keys=True).lower()
        for token in ("uas", "lod2", "roofsurface", "groundsurface", "stable_id", "journal1"):
            self.assertNotIn(token, input_text)
        self.assertIsNone(self.cfg["scientific_verdict"])

    def test_prism_selection_is_exactly_half_open(self) -> None:
        minimum = np.array([-1.0, -2.0, -3.0], np.float32)
        maximum = np.array([1.0, 2.0, 3.0], np.float32)
        points = np.array(
            [
                [-1.0, -2.0, -3.0],
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 2.0, 0.0],
                [0.0, 0.0, 3.0],
            ],
            np.float32,
        )
        selected = render.select_half_open_prism(points, minimum, maximum)
        self.assertEqual(selected.shape, (2, 3))
        np.testing.assert_array_equal(selected[0], points[0])
        np.testing.assert_array_equal(selected[1], points[1])

    def test_projection_and_zbuffer_keep_nearest_camera_z(self) -> None:
        points = np.array(
            [
                [0.0, 0.0, 2.0],
                [0.0, 0.0, 5.0],
                [1.0, 0.0, 2.0],
                [0.0, 0.0, -1.0],
            ],
            np.float32,
        )
        intrinsic = np.array([[10.0, 0.0, 5.0], [0.0, 10.0, 5.0], [0.0, 0.0, 1.0]])
        x, y, z = render.project_points(
            points, np.eye(3), np.zeros(3), intrinsic, width=12, height=12
        )
        depth = render.nearest_zbuffer(x, y, z, width=12, height=12)
        self.assertEqual(len(z), 3)
        self.assertAlmostEqual(float(depth[5, 5]), 2.0)
        self.assertAlmostEqual(float(depth[5, 10]), 2.0)
        self.assertEqual(int(np.isfinite(depth).sum()), 2)

    def test_connected_proxy_is_separate_min_depth_disk_expansion(self) -> None:
        raw = np.full((7, 7), np.inf, np.float32)
        raw[3, 2] = 4.0
        raw[3, 4] = 2.0
        proxy = render.connected_display_proxy(raw, radius=2)
        self.assertEqual(int(np.isfinite(raw).sum()), 2)
        self.assertGreater(int(np.isfinite(proxy).sum()), 2)
        self.assertAlmostEqual(float(proxy[3, 3]), 2.0)
        self.assertAlmostEqual(float(raw[3, 2]), 4.0)
        self.assertTrue(np.isinf(raw[3, 3]))

    def test_connectivity_reports_proxy_improvement_without_source_judgment(self) -> None:
        raw = np.zeros((9, 9), dtype=bool)
        raw[4, 2] = True
        raw[4, 6] = True
        raw_depth = np.where(raw, 3.0, np.inf).astype(np.float32)
        proxy = np.isfinite(render.connected_display_proxy(raw_depth, radius=2))
        raw_metrics = render.mask_connectivity(raw)
        proxy_metrics = render.mask_connectivity(proxy)
        self.assertEqual(raw_metrics["component_count"], 2)
        self.assertEqual(proxy_metrics["component_count"], 1)
        self.assertTrue(self.cfg["interpretation_boundary"]["no_source_decision"])
        self.assertTrue(self.cfg["interpretation_boundary"]["no_fusion"])
        self.assertEqual(self.cfg["relation_patch_overlay"]["use"], "DISPLAY_ONLY")
        self.assertEqual(
            self.cfg["interpretation_boundary"]["relation_and_patch_classes_used"],
            "DISPLAY_ONLY",
        )

    def test_residual_definition_is_mvs_minus_existing_als(self) -> None:
        mvs = np.array([[2.0, np.inf], [5.0, 7.0]], np.float32)
        als = np.array([[1.5, 1.0], [6.0, np.inf]], np.float32)
        signed, metrics = render.residual_stats(mvs, als)
        self.assertAlmostEqual(float(signed[0, 0]), 0.5)
        self.assertAlmostEqual(float(signed[1, 0]), -1.0)
        self.assertEqual(metrics["common_pixels"], 2)
        self.assertEqual(metrics["signed_definition"], "MVS_CAMERA_Z_MINUS_EXISTING_ALS_CAMERA_Z")

    def test_visibility_gate_uses_each_cores_own_raw_source_only(self) -> None:
        mvs = np.full((4, 4), np.inf, np.float32)
        als = np.full((4, 4), np.inf, np.float32)
        mvs[1, 1] = 5.0
        als[1, 1] = 9.0
        als[2, 2] = 3.0
        x = np.array([1, 1, 2, 2], np.int32)
        y = np.array([1, 1, 2, 2], np.int32)
        z = np.array([5.2, 5.2, 3.6, 3.1], np.float32)
        source = np.array([0, 1, 1, 1], np.uint8)
        visible = render.raw_source_visibility_mask(
            x, y, z, source, {"mvs": mvs, "existing_als": als}, tolerance_m=0.5
        )
        np.testing.assert_array_equal(visible, [True, False, False, True])

    def test_patch_uid_color_is_deterministic_and_unassigned_is_neutral(self) -> None:
        first = render.patch_uid_color(b"abc123", 7)
        second = render.patch_uid_color(b"abc123", 7)
        other = render.patch_uid_color(b"def456", 8)
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertEqual(render.patch_uid_color(b"", 0), (0.39, 0.46, 0.55))

    def test_patch_binding_requires_exact_relation_lineage(self) -> None:
        relation = np.zeros(
            2,
            dtype=[
                ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                ("relation_class", "u1"), ("core_source", "u1"),
            ],
        )
        relation["relation_class"] = [2, 4]
        relation["core_source"] = [0, 1]
        membership = np.zeros(
            2,
            dtype=[
                ("core_index", "<u4"), ("patch_id", "<u4"),
                ("raw_relation_class", "u1"), ("patch_relation_class", "u1"),
                ("core_source", "u1"), ("patch_status", "u1"),
            ],
        )
        membership["core_index"] = [0, 1]
        membership["patch_id"] = [1, 1]
        membership["raw_relation_class"] = [2, 4]
        membership["patch_relation_class"] = [2, 5]
        membership["core_source"] = [0, 1]
        membership["patch_status"] = [1, 3]
        summary = np.zeros(
            1,
            dtype=[
                ("patch_id", "<u4"), ("patch_uid", "S20"),
                ("core_source", "u1"), ("patch_status", "u1"),
            ],
        )
        summary["patch_id"] = 1
        summary["patch_uid"] = b"stable"
        render.validate_patch_bindings(relation, membership, summary, 2, 1)
        membership["raw_relation_class"][1] = 3
        with self.assertRaisesRegex(RuntimeError, "raw relation provenance"):
            render.validate_patch_bindings(relation, membership, summary, 2, 1)


if __name__ == "__main__":
    unittest.main()

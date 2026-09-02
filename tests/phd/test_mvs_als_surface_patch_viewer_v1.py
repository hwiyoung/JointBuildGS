from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from scripts.phd.mvs_als_surface_patch_viewer_v1 import build as viewer


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/phd/mvs_als_surface_patch_viewer_v1/viewer_v1.json"
APP = REPO / "src/apps/mvs_als_surface_patch_viewer_v1"


class SurfacePatchViewerV1Tests(unittest.TestCase):
    def test_config_separates_viewer_and_preserves_null_verdict(self):
        cfg = viewer.load_config(CONFIG)
        self.assertIsNone(cfg["scientific_verdict"])
        self.assertEqual(cfg["default_port"], 8892)
        self.assertEqual(set(cfg["classes"]), {"1", "2", "3", "4", "5"})
        self.assertNotEqual(cfg["source_relation_viewer_relative_root"], cfg["viewer_output_relative_root"])
        self.assertEqual(cfg["display_sampling"]["role"], "DISPLAY_ONLY_NO_METHOD_FEEDBACK")
        self.assertEqual(len(cfg["surface_patch_artifact_manifest_sha256"]), 64)
        self.assertEqual(len(cfg["surface_patch_validation_receipt_sha256"]), 64)

    def test_input_paths_exclude_evaluation_sources(self):
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        serialized = json.dumps({
            "relation": cfg["source_relation_viewer_relative_root"],
            "patch": cfg["surface_patch_relative_root"],
            "viewer": cfg["viewer_output_relative_root"],
        }).lower()
        for token in ("uas", "lod2", "footprint", "stable_id", "journal1"):
            self.assertNotIn(token, serialized)

    def test_app_exposes_before_after_uid_family_status_and_highlight(self):
        html = (APP / "index.html").read_text(encoding="utf-8")
        app = (APP / "app.js").read_text(encoding="utf-8")
        for mode in ("raw", "patch", "uid", "source", "status"):
            self.assertIn(f'value="{mode}"', html)
        self.assertIn('id="show-mvs"', html)
        self.assertIn('id="show-als"', html)
        self.assertIn('id="show-centroids"', html)
        self.assertIn("function selectCore", app)
        self.assertIn("patchHighlight", app)
        self.assertIn("uidColorByPatch", app)

    def test_app_has_no_remote_browser_dependency(self):
        for name in ("index.html", "app.js", "styles.css"):
            text = (APP / name).read_text(encoding="utf-8")
            self.assertNotIn("https://", text)
            self.assertNotIn("http://", text)

    def test_patch_array_contract_accepts_stable_uid_and_rejects_raw_drift(self):
        membership_dtype = np.dtype([
            ("core_index", "<u4"), ("patch_id", "<u4"),
            ("raw_relation_class", "u1"), ("patch_relation_class", "u1"),
            ("core_source", "u1"), ("patch_status", "u1"),
            ("unassigned_reason", "u1"), ("patch_core_count", "<u4"),
            ("patch_purity", "<f4"), ("patch_radius_m", "<f4"),
        ])
        summary_dtype = np.dtype([
            ("patch_id", "<u4"), ("patch_uid", "S20"),
            ("core_source", "u1"), ("patch_relation_class", "u1"),
            ("patch_status", "u1"), ("dominant_raw_class", "u1"),
            ("core_count", "<u4"),
            ("cx", "<f4"), ("cy", "<f4"), ("cz", "<f4"),
            ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"),
            ("radius_m", "<f4"), ("bbox_diagonal_m", "<f4"),
            ("plane_rmse_m", "<f4"), ("plane_p95_abs_residual_m", "<f4"),
            ("plane_max_abs_residual_m", "<f4"), ("normal_p95_deg", "<f4"),
            ("normal_max_deg", "<f4"),
            ("support_area_proxy_m2", "<f4"), ("relation_purity", "<f4"),
            ("robust_fraction", "<f4"), ("median_surface_variation", "<f4"),
            ("count_class_1", "<u4"), ("count_class_2", "<u4"),
            ("count_class_3", "<u4"), ("count_class_4", "<u4"),
            ("count_class_5", "<u4"),
        ])
        membership = np.zeros(2, dtype=membership_dtype)
        membership["core_index"] = [0, 1]
        membership["patch_id"] = [1, 1]
        membership["raw_relation_class"] = [2, 2]
        membership["patch_relation_class"] = [2, 2]
        membership["patch_status"] = [1, 1]
        membership["patch_core_count"] = [2, 2]
        membership["patch_purity"] = [1, 1]
        summary = np.zeros(1, dtype=summary_dtype)
        summary["patch_id"] = 1
        summary["patch_uid"] = b"0123456789abcdef0123"
        summary["patch_relation_class"] = 2
        summary["patch_status"] = 1
        summary["dominant_raw_class"] = 2
        summary["core_count"] = 2
        summary["count_class_2"] = 2
        relation = np.zeros((2, 4), dtype=np.uint8)
        relation[:, 0] = 2
        viewer.validate_patch_arrays(membership, summary, relation)
        relation[1, 0] = 3
        with self.assertRaisesRegex(RuntimeError, "raw five-class provenance drift"):
            viewer.validate_patch_arrays(membership, summary, relation)


if __name__ == "__main__":
    unittest.main()

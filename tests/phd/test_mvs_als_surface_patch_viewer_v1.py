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
        self.assertEqual(len(cfg["region_unit_artifact_manifest_sha256"]), 64)
        self.assertEqual(len(cfg["region_unit_validation_receipt_sha256"]), 64)
        self.assertEqual(cfg["region_unit_task_id"], "PHD-REGION-UNIT-v1")
        self.assertNotEqual(cfg["region_unit_relative_root"], cfg["viewer_output_relative_root"])

    def test_input_paths_exclude_evaluation_sources(self):
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        serialized = json.dumps({
            "relation": cfg["source_relation_viewer_relative_root"],
            "patch": cfg["surface_patch_relative_root"],
            "unit": cfg["region_unit_relative_root"],
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

    def test_app_exposes_t0_region_unit_layer(self):
        html = (APP / "index.html").read_text(encoding="utf-8")
        app = (APP / "app.js").read_text(encoding="utf-8")
        for control in ("show-t0", "t0-show-mvs", "t0-show-als", "t0-mode", "t0-dim", "view-prism", "t0-accounting"):
            self.assertIn(f'id="{control}"', html)
        for mode in ("uid", "kind", "primary", "pairing", "support", "pairdist", "tilt", "role", "pairrule", "layer", "cores"):
            self.assertIn(f'value="{mode}"', html)
        for symbol in ("function selectUnit", "manifest.region_units", "createT0Layer", "Box3Helper", "t0Neighbors"):
            self.assertIn(symbol, app)

    def test_region_unit_array_contract_rejects_coverage_drift(self):
        cells = np.zeros(3, dtype=[
            ("cell_index", "<u4"), ("source", "u1"), ("kx", "<i4"), ("ky", "<i4"), ("kz", "<i4"),
            ("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("point_count", "<u4"),
            ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"), ("surface_variation", "<f4"), ("normal_valid", "u1"),
            ("segment_id", "<u4"), ("unit_id", "<u4"), ("role", "u1"), ("pair_distance_m", "<f4"), ("pair_rule", "u1"),
        ])
        cells["unit_id"] = [1, 2, 2]
        cells["source"] = [0, 0, 1]
        units = np.zeros(2, dtype=[
            ("unit_id", "<u4"), ("unit_uid", "S16"), ("primary_source", "u1"), ("kind", "u1"),
            ("small", "u1"), ("split_child", "u1"), ("split_reason", "u1"), ("mixed_prior", "u1"),
            ("absorbed_cell_count", "<u4"), ("prior_segment_count", "<u4"), ("prior_offset_median_m", "<f4"),
            ("prior_offset_spread_m", "<f4"), ("prior_plane_rmse_m", "<f4"), ("core_count_total", "<u4"),
            ("core_count_class_1", "<u4"), ("core_count_class_2", "<u4"), ("core_count_class_3", "<u4"),
            ("core_count_class_4", "<u4"), ("core_count_class_5", "<u4"),
            ("mvs_cell_count", "<u4"), ("mvs_point_count", "<u4"), ("als_cell_count", "<u4"), ("als_point_count", "<u4"),
            ("area_m2", "<f4"), ("cx", "<f4"), ("cy", "<f4"), ("cz", "<f4"), ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"),
            ("plane_d", "<f4"), ("plane_rmse_m", "<f4"), ("plane_p95_abs_residual_m", "<f4"),
            ("extent_e1_m", "<f4"), ("extent_e2_m", "<f4"), ("tilt_from_up_deg", "<f4"), ("prior_support_fraction", "<f4"),
            ("paired_als_segment_count", "<u4"), ("component_count", "<u4"),
            ("bbox_min_x", "<f4"), ("bbox_min_y", "<f4"), ("bbox_min_z", "<f4"),
            ("bbox_max_x", "<f4"), ("bbox_max_y", "<f4"), ("bbox_max_z", "<f4"),
        ])
        units["unit_id"] = [1, 2]
        units["unit_uid"] = [b"aaaaaaaaaaaaaaaa", b"bbbbbbbbbbbbbbbb"]
        adjacency = np.zeros(1, dtype=[("unit_a", "<u4"), ("unit_b", "<u4"), ("contact_pairs", "<u4"), ("same_primary", "u1"),
                                       ("contact_mvs_mvs", "<u4"), ("contact_als_als", "<u4"), ("contact_cross", "<u4")])
        adjacency["unit_a"], adjacency["unit_b"], adjacency["contact_pairs"], adjacency["contact_mvs_mvs"] = 1, 2, 3, 3
        viewer.validate_region_unit_arrays(cells, units, adjacency)
        cells["unit_id"][1] = 0
        with self.assertRaisesRegex(RuntimeError, "coverage drift"):
            viewer.validate_region_unit_arrays(cells, units, adjacency)

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

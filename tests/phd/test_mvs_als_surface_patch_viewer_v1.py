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
        self.assertGreaterEqual(len(cfg["prisms"]), 1)
        for item in cfg["prisms"]:
            for key in ("evidence_bank_artifact_manifest_sha256", "evidence_bank_validation_receipt_sha256",
                        "warp_ncc_artifact_manifest_sha256", "warp_ncc_validation_receipt_sha256"):
                self.assertEqual(len(item[key]), 64)
            self.assertNotEqual(item["evidence_bank_relative_root"], cfg["viewer_output_relative_root"])
        self.assertEqual(cfg["prisms"][0]["name"], "pilot")
        self.assertGreater(cfg["hm_zone_rule"]["min_height_above_ground_m"], 0)
        self.assertEqual(set(cfg["evidence_cell_colors"]["state"]), {"1", "2", "3", "4", "5"})

    def test_input_paths_exclude_evaluation_sources(self):
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        serialized = json.dumps({
            "relation": cfg["source_relation_viewer_relative_root"],
            "patch": cfg["surface_patch_relative_root"],
            "prisms": [[p["evidence_bank_relative_root"], p["warp_ncc_relative_root"]] for p in cfg["prisms"]],
            "viewer": cfg["viewer_output_relative_root"],
        }).lower()
        for token in ("uas", "lod2", "footprint", "stable_id", "journal1"):
            self.assertNotIn(token, serialized)

    def test_app_exposes_stage_tabs_prisms_and_evidence_modes(self):
        html = (APP / "index.html").read_text(encoding="utf-8")
        app = (APP / "app.js").read_text(encoding="utf-8")
        for control in ("stage-tabs", "prism-select", "view-prism", "view-scene", "clear-selection", "scene-mode", "hm-list", "hm-boundary",
                        "s1-mode", "t1-mode", "t2-mode", "t2-case", "t2-case-note", "show-cells-m", "show-cells-p", "show-raw-m", "show-raw-p", "state-filter", "only-selected-pair", "image-top", "image-panel", "image-close",
                        "chip-panel", "chip-img", "t1-accounting", "t2-accounting", "selection-details"):
            self.assertIn(f'id="{control}"', html)
        for stage in ("scene", "s1", "t1", "t2"):
            self.assertIn(f'data-stage="{stage}"', html)
            self.assertIn(f'id="stage-{stage}"', html)
        for mode in ("hm", "class", "state", "dz", "rough", "fpen", "fagree", "fblock", "d3a", "texture", "r1",
                     "delta", "fmp", "fpm", "sm", "sp", "power", "npm", "npp", "nvdiff", "ctrl", "edge", "r2"):
            self.assertIn(f'value="{mode}"', html)
        for symbol in ("manifest.prisms", "manifest.hm_zones", "function selectCell", "function selectCore", "function evCases", "function setStage",
                       "function setActivePrism", "renderHmList", "delta_sign", "chips.files"):
            self.assertIn(symbol, app)
        # the rejected T0 region-unit layer is gone from the viewer
        self.assertNotIn("region_units", app)
        self.assertNotIn('id="show-t0"', html)

    def test_hm_zone_rule_finds_elevated_prior_only_cluster(self):
        rng = np.random.default_rng(1)
        # flat ground of class-1 cores on a 2 m grid, plus a 12 x 12 m block of class-4 cores 8 m above ground
        gx, gy = np.meshgrid(np.arange(0, 60, 2.0), np.arange(0, 60, 2.0))
        ground = np.column_stack((gx.ravel(), gy.ravel(), rng.normal(0, 0.05, gx.size)))
        bx, by = np.meshgrid(np.arange(20, 32, 1.0), np.arange(20, 32, 1.0))
        roof = np.column_stack((bx.ravel(), by.ravel(), np.full(bx.size, 8.0)))
        low = np.column_stack((np.arange(40, 50, 1.0), np.full(10, 45.0), np.full(10, 0.5)))  # class-4 at ground height → not elevated
        xyz = np.vstack((ground, roof, low)); cls = np.concatenate((np.ones(len(ground)), np.full(len(roof), 4), np.full(len(low), 4))).astype(np.uint8)
        rule = {"min_height_above_ground_m": 3.0, "ground_cell_m": 24.0, "cluster_cell_m": 2.0, "min_cores_per_cell": 2, "min_area_m2": 80.0, "boundary_margin_m": 6.0}
        mvs = np.column_stack((np.arange(20, 26, 1.0), np.full(6, 25.0), np.full(6, 1.0)))  # MVS present under a third of the roof columns
        flag, cluster, table = viewer.hm_zones(xyz, cls, rule, np.array([0.0, 0.0, -1.0]), np.array([60.0, 60.0, 10.0]), mvs)
        self.assertEqual(int(flag.sum()), len(roof))
        self.assertGreater(table[0]["mvs_column_fraction"], 0.05); self.assertLess(table[0]["mvs_column_fraction"], 0.4)
        _, _, table_none = viewer.hm_zones(xyz, cls, rule, np.array([0.0, 0.0, -1.0]), np.array([60.0, 60.0, 10.0]))
        self.assertIsNone(table_none[0]["mvs_column_fraction"])
        # prior-quality zones: same roof, both supports, noisy MVS → one cluster; quiet MVS → none
        cls_both = np.where(cls == 4, 1, cls)
        metrics = np.zeros((len(xyz), 6), dtype=np.float32); metrics[:, 4] = 0.5; metrics[:, 5] = 0.05
        qrule = dict(rule, min_sigma_ratio=3.0, min_sigma_mvs_m=0.15)
        qflag, qcluster, qtable = viewer.quality_zones(xyz, cls_both, metrics, qrule, np.array([0.0, 0.0, -1.0]), np.array([60.0, 60.0, 10.0]))
        self.assertEqual(int(qflag.sum()), len(roof)); self.assertEqual(len(qtable), 1); self.assertAlmostEqual(qtable[0]["sigma_mvs_median_m"], 0.5, places=5)
        metrics[:, 4] = 0.06
        qflag2, _, qtable2 = viewer.quality_zones(xyz, cls_both, metrics, qrule, np.array([0.0, 0.0, -1.0]), np.array([60.0, 60.0, 10.0]))
        self.assertEqual(int(qflag2.sum()), 0); self.assertEqual(qtable2, [])
        self.assertEqual(len(table), 1)
        self.assertAlmostEqual(table[0]["height_median_m"], 8.0, delta=0.2)
        self.assertFalse(table[0]["touches_scene_boundary"])
        self.assertEqual(int((cluster == 1).sum()), len(roof))
        self.assertTrue(np.all(cluster[len(ground) + len(roof):] == 0))

    def test_evidence_array_contract_binds_t1_t2_and_pairing(self):
        from scripts.phd.evidence_bank_v1 import run as eb
        from scripts.phd.warp_ncc_v1 import run as wn
        t1 = np.zeros(3, dtype=eb.CELL_DTYPE); t2 = np.zeros(3, dtype=wn.CELL_DTYPE)
        top = np.zeros(3, dtype=[("ix", "<i4"), ("iy", "<i4"), ("layer", "u1"), ("mvs_z", "<f4"), ("als_z", "<f4")])
        for arr in (t1, t2, top):
            arr["ix"] = [0, 1, 2]; arr["iy"] = [5, 5, 6]
        t1["state"] = t2["state"] = [1, 2, 3]
        t1["r"] = [1, 2, 3]; t2["r_t1"] = [1, 2, 3]
        viewer.validate_evidence_arrays(t1, t2, top)
        t2["r_t1"][0] = 0
        with self.assertRaisesRegex(RuntimeError, "r_t1"):
            viewer.validate_evidence_arrays(t1, t2, top)
        t2["r_t1"][0] = 1; top["ix"][2] = 9
        with self.assertRaisesRegex(RuntimeError, "pairing top-layer"):
            viewer.validate_evidence_arrays(t1, t2, top)

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
        membership["core_source"] = [0, 0]
        membership["patch_core_count"] = [2, 2]
        summaries = np.zeros(1, dtype=summary_dtype)
        summaries["patch_id"] = [1]
        summaries["patch_uid"] = [b"p_00000001"]
        summaries["patch_relation_class"] = [2]
        summaries["dominant_raw_class"] = [2]
        summaries["core_count"] = [2]
        attributes = np.zeros((2, 4), dtype=np.uint8)
        attributes[:, 0] = [2, 2]
        viewer.validate_patch_arrays(membership, summaries, attributes)
        attributes[0, 0] = 1
        with self.assertRaisesRegex(RuntimeError, "raw five-class provenance drift"):
            viewer.validate_patch_arrays(membership, summaries, attributes)


if __name__ == "__main__":
    unittest.main()

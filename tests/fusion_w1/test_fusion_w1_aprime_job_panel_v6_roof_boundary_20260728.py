#!/usr/bin/env python3
"""Contract tests for the 4907182 panel-v6 actual roof-boundary backfill."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v6_roof_boundary_20260728.py"
)
SPEC = importlib.util.spec_from_file_location(
    "fusion_w1_aprime_job_panel_v6_roof_boundary", MODULE_PATH
)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot import {MODULE_PATH}")
panel = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = panel
SPEC.loader.exec_module(panel)


IDENTITY = ("DEBY_LOD2_4907182", "Aprime", "r1")


class JobPanelV6RoofBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config, cls.base_config = panel.load_config()
        cls.report = panel.base.load_report_module(cls.base_config)
        evidence = panel.base.resolve_evidence(cls.base_config, cls.report, *IDENTITY)
        cls.evidence = panel.augment_evidence(evidence, cls.config)
        cls.view = cls.evidence["image_mask"]

    def test_scope_and_new_namespace_are_locked(self) -> None:
        self.assertEqual(panel.allowed_identity(self.config), IDENTITY)
        self.assertEqual(
            self.config["outputs"]["root"],
            "phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/review_v6_roof_boundary",
        )
        self.assertEqual(set(self.config["outputs"]), {"root", "panel", "complete"})
        with self.assertRaisesRegex(panel.PanelError, "outside the locked"):
            panel.validate_identity(
                self.config, self.base_config, "DEBY_LOD2_42364609", "Aprime", "r1"
            )

    def test_v4_v5_are_preserved_and_v5_is_retracted(self) -> None:
        snapshot = panel.historical_bundle_snapshot(self.config)
        self.assertEqual(snapshot["v4"]["status"], "historical")
        self.assertEqual(
            snapshot["v5"]["status"],
            "historical_retracted_flat_median_height_locator",
        )
        self.assertEqual(set(snapshot["v5"]["records"]), {"complete.json", "panel.png"})

    def test_boundary_is_actual_z_tin_support_not_flat_footprint(self) -> None:
        boundary = self.view["roof_boundary"]
        segments = np.asarray(self.view["boundary_segments_base"])
        self.assertEqual(segments.shape, (boundary["segments_n"], 2, 3))
        self.assertGreater(boundary["segments_n"], 0)
        self.assertGreater(boundary["components_n"], 0)
        self.assertGreater(boundary["z_max_m"] - boundary["z_min_m"], 0.01)
        self.assertEqual(
            boundary["tin_stats"]["source_points_n"],
            self.view["seed_contract"]["unfiltered_points_n"],
        )
        nan_polyline = np.asarray(self.view["footprint_uv"])
        self.assertTrue(np.isnan(nan_polyline[2::3]).all())
        self.assertEqual(len(nan_polyline), boundary["segments_n"] * 3)

    def test_common_projection_datum_geoid_and_adopted_pose_are_explicit(self) -> None:
        coordinate = self.view["coordinate_contract"]
        self.assertEqual(coordinate["input_vertical_datum"], "orthometric")
        self.assertEqual(coordinate["orthometric_to_ellipsoidal_geoid_m"], 45.7)
        self.assertEqual(
            coordinate["projection_engine"],
            "src.stage2.image_projection.project_base_points",
        )
        self.assertEqual(coordinate["additional_transform_application_count"], 0)
        self.assertEqual(
            coordinate["observed_corrected_images_sha256"],
            coordinate["adopted_corrected_images_sha256"],
        )
        self.assertLessEqual(
            self.view["seed_contract"]["maximum_canonical_roundtrip_delta_m"],
            1.0e-9,
        )

    def test_view_selection_is_geometry_only_and_fails_closed(self) -> None:
        selection = self.view["selection"]
        self.assertTrue(selection["boundary_all_valid_and_in_frame"])
        self.assertTrue(selection["seed_all_valid_and_in_frame"])
        self.assertEqual(
            selection["boundary_endpoints_in_frame_n"],
            selection["boundary_endpoints_n"],
        )
        self.assertEqual(selection["seed_in_frame_n"], selection["seed_points_n"])
        for key in (
            "image_pixels_used_for_ranking",
            "M_j_used_for_ranking_or_eligibility",
            "reference_GML_used_for_ranking_or_eligibility",
            "output_CityJSON_used_for_ranking_or_eligibility",
        ):
            self.assertFalse(selection[key])
        eligible = [
            candidate
            for candidate in selection["candidates"]
            if candidate["boundary_all_valid_and_in_frame"]
            and candidate["seed_all_valid_and_in_frame"]
        ]
        expected = min(
            eligible,
            key=lambda candidate: (
                -candidate["boundary_bbox_area_px2"],
                -candidate["boundary_length_px"],
                candidate["nadir_deg"],
                candidate["frame_radius"],
                candidate["selection_order"],
                candidate["image_name"],
            ),
        )
        self.assertEqual(self.view["row"]["image_name"], expected["image_name"])

    def test_crop_and_first_row_adapter_use_only_boundary_and_seed(self) -> None:
        x0, y0, x1, y1 = self.view["crop_box"]
        self.assertTrue(all(type(value) is int for value in self.view["crop_box"]))
        boundary_uv = np.asarray(self.view["boundary_segments_uv"]).reshape(-1, 2)
        seed_uv = np.asarray(self.view["seed_uv"])
        points = np.vstack((boundary_uv, seed_uv))
        self.assertTrue(np.all(points[:, 0] >= x0))
        self.assertTrue(np.all(points[:, 0] < x1))
        self.assertTrue(np.all(points[:, 1] >= y0))
        self.assertTrue(np.all(points[:, 1] < y1))
        self.assertFalse(np.asarray(self.view["mask"]).any())
        self.assertNotIn("selected_M_j", self.view["records"])
        self.assertTrue(all(value is False for value in self.view["alignment_independence"].values()))

    def test_stale_projection_helpers_are_not_called(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("image_projection.project_base_points(", source)
        self.assertNotIn("v4.projected_input_view(", source)
        self.assertNotIn("base_xy_to_canonical_at_z(", source)
        self.assertNotIn("mask_containment(", source)
        self.assertNotIn("panel_v5_backfill", source)

    def test_inherited_resolver_reads_are_disclosed_but_not_used_for_alignment(self) -> None:
        disclosure = self.config["resolver_disclosure"]
        self.assertTrue(
            disclosure["inherited_base_resolver_reads_M_j_before_v6_geometry_selection"]
        )
        self.assertTrue(
            disclosure[
                "inherited_base_resolver_reads_reference_GML_before_v6_geometry_selection"
            ]
        )
        self.assertFalse(
            disclosure["inherited_values_used_for_v6_view_ranking_eligibility_or_crop"]
        )

    def test_unrelated_queue_is_allowed_but_gpu_and_source_drift_are_not(self) -> None:
        execution = self.config["execution"]
        self.assertTrue(execution["unrelated_queue_allowed"])
        self.assertFalse(execution["gpus_required"])
        self.assertEqual(execution["gpu_devices_used"], [])
        self.assertTrue(execution["target_source_hashes_verified_before_and_after_render"])
        self.assertTrue(execution["output_namespace_isolated_from_training"])
        wrapper = (
            REPO
            / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_aprime_job_panel_v6_roof_boundary_20260728.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn("systemctl", wrapper)
        self.assertNotIn("ACTIVE_QUEUE_UNIT", wrapper)
        self.assertNotIn("--gpus", wrapper)

    def test_check_payload_has_no_verdict(self) -> None:
        payload = panel.check_job(
            self.config, self.base_config, self.report, *IDENTITY
        )
        self.assertEqual(payload["selected_image"], self.view["row"]["image_name"])
        self.assertFalse(payload["training_readout_assembly_score_changed"])
        self.assertIsNone(payload["scientific_verdict"])
        self.assertIsNone(payload["interpretation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

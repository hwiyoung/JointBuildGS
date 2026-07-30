#!/usr/bin/env python3
"""Contract and integration tests for A-prime panel-v7 reference roof locator."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from unittest import mock
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v7_reference_roof_boundary_20260728.py"
)
SPEC = importlib.util.spec_from_file_location(
    "fusion_w1_aprime_job_panel_v7_reference_roof_boundary", MODULE_PATH
)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot import {MODULE_PATH}")
panel = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = panel
SPEC.loader.exec_module(panel)


IDENTITY = ("DEBY_LOD2_4907182", "Aprime", "r1")


class JobPanelV7ReferenceRoofBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config, cls.base_config = panel.load_config()
        cls.report = panel.base.load_report_module(cls.base_config)
        evidence = panel.base.resolve_evidence(cls.base_config, cls.report, *IDENTITY)
        cls.evidence = panel.augment_evidence(evidence, cls.config)
        cls.view = cls.evidence["image_mask"]

    def test_scope_and_isolated_namespace_are_locked(self) -> None:
        self.assertEqual(len(panel.allowed_identities(self.config)), 9)
        self.assertIn(IDENTITY, panel.allowed_identities(self.config))
        self.assertEqual(
            self.config["outputs"]["root"],
            "phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/review_v7_reference_roof_boundary",
        )
        with self.assertRaisesRegex(panel.PanelError, "locked"):
            panel.validate_identity(
                self.config, self.base_config, "DEBY_LOD2_4907184", "Aprime", "r1"
            )

    def test_reference_parser_returns_only_roofsurface_exterior_rings(self) -> None:
        roof = self.view["reference_roof"]
        rings = self.view["reference_roof_rings_base"]
        self.assertEqual(roof["included_semantics"], ["RoofSurface"])
        self.assertEqual(roof["ring_role"], "Polygon exterior only")
        self.assertFalse(roof["interior_rings_used"])
        self.assertEqual(roof["exterior_rings_n"], 2)
        self.assertEqual(len(rings), roof["exterior_rings_n"])
        self.assertTrue(all(np.allclose(ring[0], ring[-1]) for ring in rings))
        self.assertGreater(roof["z_max_m"] - roof["z_min_m"], 0.01)

    def test_full_scene_first_hit_visibility_selects_only_0182(self) -> None:
        selection = self.view["selection"]
        self.assertEqual(selection["primary_image"], "DJI_20241217084837_0182_D.JPG")
        self.assertEqual(selection["selected_tier"], "B_fallback_full_in_frame_and_target_roof_visible")
        self.assertEqual(selection["usable_visible_views_n"], 1)
        self.assertEqual(selection["margin_visible_views_n"], 0)
        self.assertGreater(selection["primary_rank_metrics"]["visible_target_roof_pixels_n"], 18000)
        by_name = {item["image_name"]: item for item in selection["candidates"]}
        self.assertEqual(by_name["DJI_20241217084837_0182_D.JPG"]["visible_target_roof_pixels_n"], 18695)
        self.assertTrue(by_name["DJI_20241217084837_0182_D.JPG"]["boundary_full_in_frame"])
        self.assertFalse(by_name["DJI_20241217084837_0182_D.JPG"]["all_valid_and_inside_margin"])
        self.assertEqual(by_name["DJI_20241217102937_0014_D.JPG"]["visible_target_roof_pixels_n"], 0)
        self.assertEqual(by_name["DJI_20241217102925_0008_D.JPG"]["visible_target_roof_pixels_n"], 0)

    def test_rank_is_area_first_inside_first_nonempty_visibility_tier(self) -> None:
        selection = self.view["selection"]
        candidates = selection["candidates"]
        if selection["selected_tier"].startswith("A_"):
            eligible = [
                item
                for item in candidates
                if item["all_valid_and_inside_margin"]
                and item["visible_target_roof_pixels_n"] > 0
                and item["bbox_area_px2"] >= 2500.0
            ]
        else:
            eligible = [
                item
                for item in candidates
                if item["boundary_full_in_frame"]
                and item["visible_target_roof_pixels_n"] > 0
                and item["bbox_area_px2"] >= 2500.0
            ]
        expected = min(
            eligible,
            key=lambda item: (
                -item["bbox_area_px2"],
                item["centrality_normalized"],
                item["nadir_deg"],
                item["frame_radius"],
                item["selection_order"],
                item["image_name"],
            ),
        )
        self.assertEqual(selection["primary_image"], expected["image_name"])

    def test_photo_row_is_visible_reference_boundary_lines_only(self) -> None:
        primary = self.view["primary"]
        self.assertGreater(primary["visible_boundary_polylines_n"], 0)
        self.assertGreater(primary["visible_boundary_samples_n"], 0)
        self.assertEqual(np.asarray(self.view["seed_uv"]).shape, (0, 2))
        self.assertFalse(np.asarray(self.view["mask"]).any())
        exclusions = set(self.view["first_row_exclusions"])
        self.assertTrue(
            {"ALS seed points", "class6 TIN points", "class6 TIN boundary", "M_j mask", "Roofer output"}.issubset(exclusions)
        )

    def test_medium_and_tight_crops_contain_reference_boundary(self) -> None:
        primary = self.view["primary"]
        values = panel._boundary_values(primary["rings_uv"])
        for key in ("medium_crop_box", "tight_crop_box"):
            x0, y0, x1, y1 = primary[key]
            self.assertTrue(np.all(values[:, 0] >= x0))
            self.assertTrue(np.all(values[:, 0] < x1))
            self.assertTrue(np.all(values[:, 1] >= y0))
            self.assertTrue(np.all(values[:, 1] < y1))

    def test_coordinate_datum_pose_and_raycast_scene_are_explicit(self) -> None:
        coordinate = self.view["coordinate_contract"]
        self.assertEqual(coordinate["input_vertical_datum"], "orthometric")
        self.assertEqual(coordinate["orthometric_to_ellipsoidal_geoid_m"], 45.7)
        self.assertEqual(coordinate["additional_transform_application_count"], 0)
        self.assertEqual(
            coordinate["observed_corrected_images_sha256"],
            coordinate["adopted_corrected_images_sha256"],
        )
        scene = self.view["selection"]["visibility_scene"]
        self.assertTrue(scene["all_scene_surfaces_are_occluders"])
        self.assertEqual(scene["positive_hit"], "selected-building RoofSurface only")
        self.assertGreater(scene["triangles_n"], scene["selected_building_roof_triangles_n"])

    def test_reference_use_is_post_hoc_and_not_experimental_input(self) -> None:
        disclosure = self.config["resolver_disclosure"]
        self.assertTrue(
            disclosure[
                "reference_RoofSurface_used_for_post_hoc_visual_selection_crop_and_overlay"
            ]
        )
        self.assertFalse(
            disclosure[
                "reference_used_for_training_supervision_readout_assembly_or_scoring"
            ]
        )
        for key in (
            "M_j_used_for_v7_view_selection_crop_or_overlay",
            "ALS_seed_used_for_v7_view_selection_crop_or_overlay",
            "class6_TIN_used_for_v7_view_selection_crop_or_overlay",
            "output_CityJSON_used_for_v7_view_selection_crop_or_overlay",
        ):
            self.assertFalse(disclosure[key])

    def test_stale_locator_paths_are_not_called_and_wrapper_is_cpu_only(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("_raycast_cached_lod2_roof_bool_mask(", source)
        self.assertIn("pilot_plane_mask_producer._camera_ray_chunk(", source)
        self.assertIn("image_projection.project_base_points(", source)
        self.assertNotIn("v4.projected_input_view(", source)
        self.assertNotIn("base_xy_to_canonical_at_z(", source)
        self.assertNotIn("load_approved_footprint_xy(", source)
        self.assertNotIn("roof_boundary_overlay", source)
        wrapper = (
            REPO
            / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_aprime_job_panel_v7_reference_roof_boundary_20260728.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn("systemctl", wrapper)
        self.assertNotIn("--gpus", wrapper)

    def test_check_payload_has_no_verdict(self) -> None:
        with mock.patch.object(panel.base, "resolve_evidence", return_value={}), mock.patch.object(
            panel, "augment_evidence", return_value=self.evidence
        ):
            payload = panel.check_job(self.config, self.base_config, self.report, *IDENTITY)
        self.assertEqual(payload["primary_image"], "DJI_20241217084837_0182_D.JPG")
        self.assertEqual(
            payload["first_row_overlay_layers"],
            ["evaluation_only_reference_LoD2_RoofSurface_exterior_boundary_lines"],
        )
        self.assertEqual(payload["first_row_points"], 0)
        self.assertEqual(payload["first_row_filled_regions"], 0)
        self.assertFalse(payload["training_readout_assembly_score_changed"])
        self.assertIsNone(payload["scientific_verdict"])
        self.assertIsNone(payload["interpretation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

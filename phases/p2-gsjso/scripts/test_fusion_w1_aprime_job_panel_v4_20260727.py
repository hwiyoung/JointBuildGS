#!/usr/bin/env python3
"""Contract and end-to-end tests for the one-file A-prime panel v4."""
from __future__ import annotations

import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO / "phases/p2-gsjso/scripts/fusion_w1_aprime_job_panel_v4_20260727.py"
SPEC = importlib.util.spec_from_file_location("fusion_w1_aprime_job_panel_v4", MODULE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot import {MODULE_PATH}")
panel = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = panel
SPEC.loader.exec_module(panel)


SMOKE_IDENTITY = ("DEBY_LOD2_42364609", "Aprime", "r1")
COMPLEX_IDENTITY = ("DEBY_LOD2_42364659", "Aprime", "r1")


class JobPanelV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config, cls.base_config = panel.load_panel_config()
        cls.report = panel.base.load_report_module(cls.base_config)
        evidence = panel.base.resolve_evidence(
            cls.base_config, cls.report, *SMOKE_IDENTITY
        )
        cls.evidence = panel.augment_evidence(evidence, cls.config)
        cls.evidence["base_config"] = cls.base_config
        complex_evidence = panel.base.resolve_evidence(
            cls.base_config, cls.report, *COMPLEX_IDENTITY
        )
        cls.complex_evidence = panel.augment_evidence(complex_evidence, cls.config)
        cls.complex_evidence["base_config"] = cls.base_config

    def test_single_file_grid_and_camera_contract(self) -> None:
        visual = self.config["visual_contract"]
        self.assertEqual((visual["rows"], visual["columns"]), (5, 5))
        self.assertTrue(visual["single_visual_file"])
        self.assertFalse(visual["placeholders_allowed_for_measured"])
        camera = visual["camera_contract"]
        self.assertEqual(camera["projection"], "orthographic")
        self.assertEqual(camera["z_exaggeration"], 1.0)
        self.assertTrue(camera["shared_scene_bounds_across_geometry_rows"])
        self.assertEqual(
            [item["key"] for item in camera["views"]],
            ["top", "oblique_a", "oblique_b", "principal_side"],
        )
        implementation_paths = [item["path"] for item in panel.implementation_records(self.config)]
        self.assertIn(self.config["base_contract"]["config"], implementation_paths)
        self.assertIn(self.config["base_contract"]["renderer"], implementation_paths)
        self.assertIn("src/stage2/colmap_io.py", implementation_paths)

    def test_input_locator_separates_footprint_seed_and_Mj(self) -> None:
        view = self.evidence["image_mask"]
        self.assertEqual(view["selection"]["M_j_or_image_pixels_used_for_ranking"], False)
        self.assertEqual(view["seed_contract"]["source"], "ALS classification 6 only")
        self.assertEqual(view["seed_contract"]["class2_rows_n"], 0)
        self.assertEqual(view["seed_contract"]["sfm_rows_n"], 0)
        self.assertEqual(view["footprint_uv"].shape[1], 2)
        self.assertEqual(view["seed_uv"].shape[1], 2)
        self.assertEqual(view["mask"].shape, (view["image"].height, view["image"].width))
        self.assertGreater(view["selection"]["seed_inframe_fraction"], 0.94)
        self.assertGreaterEqual(view["mask_alignment"]["all_views_max"], view["mask_alignment"]["all_views_min"])

    def test_output_and_reference_are_distinct_sources_and_geometry(self) -> None:
        comparison = panel.output_reference_comparison(self.evidence)
        self.assertNotEqual(
            comparison["output_cityjson_sha256"],
            comparison["reference_gml_sha256"][0],
        )
        self.assertFalse(comparison["exact_XYZ_coordinate_set_equal"])
        self.assertEqual(
            comparison["roofer_footprint_source_role"],
            "approved_LoD2_GroundSurface_XY_only",
        )

    def test_cityjson_parser_selects_lod2_solid_and_semantics(self) -> None:
        stats = self.evidence["cityjson_surface_stats"]
        self.assertGreaterEqual(stats["lod"], 2.0)
        self.assertGreater(stats["surfaces_n"], 3)
        self.assertGreater(stats["semantic_counts"].get("RoofSurface", 0), 0)
        self.assertGreater(stats["semantic_counts"].get("WallSurface", 0), 0)
        self.assertGreater(stats["semantic_counts"].get("GroundSurface", 0), 0)

    def test_cityjson_interior_ring_is_not_filled(self) -> None:
        payload = {
            "type": "CityJSON",
            "version": "2.0",
            "CityObjects": {
                "synthetic": {
                    "type": "BuildingPart",
                    "geometry": [
                        {
                            "type": "Solid",
                            "lod": "2.2",
                            "boundaries": [
                                [
                                    [
                                        [0, 1, 2, 3],
                                        [4, 5, 6, 7],
                                    ]
                                ]
                            ],
                            "semantics": {
                                "surfaces": [{"type": "RoofSurface"}],
                                "values": [[0]],
                            },
                        }
                    ],
                }
            },
            "vertices": [
                [0, 0, 10],
                [10, 0, 10],
                [10, 10, 10],
                [0, 10, 10],
                [3, 3, 10],
                [7, 3, 10],
                [7, 7, 10],
                [3, 7, 10],
            ],
        }
        with tempfile.TemporaryDirectory(prefix="aprime-panel-v4-hole-") as temporary:
            path = Path(temporary) / "hole.city.json"
            panel.base.write_json_exclusive(path, payload)
            surfaces, stats = panel.load_cityjson_surfaces(path)
        self.assertEqual(stats["interior_rings_n"], 1)
        self.assertEqual(stats["surfaces_with_interior_rings_n"], 1)
        parts = panel.cityjson_render_parts(
            surfaces,
            {"local_origin_epsg25832_xyz": [0.0, 0.0, 0.0]},
        )
        self.assertEqual(parts["stats"]["filled_surfaces_n"], 0)
        self.assertEqual(parts["stats"]["wireframe_only_surfaces_n"], 1)
        self.assertEqual(len(parts["wireframe_rings"]), 2)
        self.assertEqual(sum(item["interior"] for item in parts["wireframe_rings"]), 1)

    def test_scene_frame_is_output_selected_and_shared(self) -> None:
        frame = panel.scene_frame(self.evidence, self.config)
        self.assertEqual(frame["crs"], "EPSG:25832")
        self.assertEqual(frame["z_exaggeration"], 1.0)
        self.assertNotIn("reference", frame["axis"]["source"])
        self.assertFalse(frame["reference_view_orientation_influence"])
        self.assertTrue(frame["reference_shared_bounds_influence"])
        self.assertEqual(
            [item["key"] for item in frame["cameras"]],
            ["top", "oblique_a", "oblique_b", "principal_side"],
        )
        self.assertTrue(all(item["projection"] == "orthographic" for item in frame["cameras"]))
        bounds = frame["local_bounds_xyz"]
        self.assertEqual(len(bounds), 3)
        self.assertTrue(all(pair[1] > pair[0] for pair in bounds))

    def test_primary_score_and_mesh_are_measured(self) -> None:
        self.assertEqual(self.evidence["primary_score"]["state"], "MEASURED")
        measurements = self.evidence["readout"]["primary"]["measurements"]
        self.assertIn("roof_rms_m", measurements)
        topology = panel.mesh_topology_stats(self.evidence["mesh_faces"])
        self.assertGreater(topology["faces_n"], 0)
        self.assertGreater(topology["edges_n"], 0)

    def test_primary_score_rejects_cross_building_binding(self) -> None:
        tampered = copy.deepcopy(self.evidence)
        original_record = tampered["readout"]["primary"]["receipt"]
        payload = panel.base.load_json(panel.base.repo_path(original_record["path"]))
        payload["identity"]["building_id"] = COMPLEX_IDENTITY[0]
        with tempfile.TemporaryDirectory(prefix="aprime-panel-v4-score-") as temporary:
            path = Path(temporary) / "score.json"
            panel.base.write_json_exclusive(path, payload)
            replacement = panel.base.file_record(path)
            tampered["readout"]["primary"]["receipt"] = replacement
            tampered["readout"]["artifact_ledger"] = [
                replacement if item == original_record else item
                for item in tampered["readout"]["artifact_ledger"]
            ]
            with self.assertRaisesRegex(panel.PanelError, "building_id identity drift"):
                panel.primary_score(tampered)

    def test_complex_measured_job_full_render_regression(self) -> None:
        faces_n = len(self.complex_evidence["mesh_faces"])
        self.assertGreater(faces_n, 100000)
        self.assertEqual(
            self.complex_evidence["cityjson_surface_stats"]["surfaces_n"], 19
        )
        with tempfile.TemporaryDirectory(prefix="aprime-panel-v4-complex-") as temporary:
            output_root = Path(temporary) / "review-v4"
            receipt = panel.publish_job(
                self.config,
                self.base_config,
                self.report,
                *COMPLEX_IDENTITY,
                output_root=output_root,
            )
            render = receipt["panel_contract"]["render"]
            self.assertEqual(render["mesh_topology"]["faces_n"], faces_n)
            self.assertEqual(render["mesh_faces_displayed_per_view"], faces_n)
            self.assertEqual(render["cityjson"]["surfaces_n"], 19)
            verified = panel.verify_bundle(
                self.config,
                self.base_config,
                *COMPLEX_IDENTITY,
                output_root=output_root,
            )
            self.assertEqual(verified["outputs"], receipt["outputs"])

    def test_temp_publication_is_one_visual_file_atomic_and_verdict_free(self) -> None:
        sources_before = panel.source_snapshot(self.evidence)
        with tempfile.TemporaryDirectory(prefix="aprime-panel-v4-test-") as temporary:
            output_root = Path(temporary) / "review-v4"
            receipt = panel.publish_job(
                self.config,
                self.base_config,
                self.report,
                *SMOKE_IDENTITY,
                output_root=output_root,
            )
            self.assertEqual(receipt["schema"], panel.RECEIPT_SCHEMA)
            self.assertEqual(receipt["state"], "COMPLETE")
            self.assertEqual(receipt["measurement_state"], "MEASURED")
            self.assertIsNone(receipt["scientific_verdict"])
            self.assertIsNone(receipt["interpretation"])
            self.assertTrue(receipt["panel_contract"]["single_visual_file"])
            self.assertEqual(receipt["panel_contract"]["placeholders"], 0)
            self.assertEqual(
                receipt["panel_contract"]["render"]["layout"],
                "5_rows_x_5_columns_single_png",
            )
            self.assertEqual(
                receipt["panel_contract"]["render"]["mesh_faces_displayed_per_view"],
                receipt["panel_contract"]["render"]["mesh_topology"]["faces_n"],
            )
            self.assertFalse(receipt["reference_gml"]["view_orientation_influence"])
            self.assertTrue(receipt["reference_gml"]["shared_bounds_influence"])
            job = panel.output_job_dir(
                self.config, *SMOKE_IDENTITY, output_root=output_root
            )
            self.assertEqual(
                {path.name for path in job.iterdir()},
                {"panel.png", "opacity.csv", "roofer.city.json", "complete.json"},
            )
            self.assertGreaterEqual(
                receipt["render_quality"]["width"],
                self.config["visual_contract"]["minimum_panel_pixels"][0],
            )
            self.assertGreaterEqual(
                receipt["render_quality"]["height"],
                self.config["visual_contract"]["minimum_panel_pixels"][1],
            )
            verified = panel.verify_bundle(
                self.config,
                self.base_config,
                *SMOKE_IDENTITY,
                output_root=output_root,
            )
            self.assertEqual(verified["outputs"], receipt["outputs"])
        self.assertEqual(panel.source_snapshot(self.evidence), sources_before)


if __name__ == "__main__":
    unittest.main()

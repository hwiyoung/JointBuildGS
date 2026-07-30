#!/usr/bin/env python3
"""Contract tests for dense qualitative v4."""
from __future__ import annotations

import importlib.util
import inspect
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v4_20260728.py"
SPEC = importlib.util.spec_from_file_location("fusion_w1_dense_baseline_qualitative_v4", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import {MODULE_PATH}")
qual = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = qual
SPEC.loader.exec_module(qual)


class DenseBaselineQualitativeV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = qual.load_config()

    def test_frozen_sample_and_precise_population_wording(self) -> None:
        self.assertEqual(tuple(self.config["sample_freeze"]["selected_building_ids"]), qual.EXPECTED_SELECTED)
        self.assertEqual(
            self.config["population_contract"]["display_name"],
            "dense LoD2 output exists (has_lod22); quality not implied",
        )

    def test_row_one_has_both_classes_and_reference_but_no_tin_or_footprint(self) -> None:
        contract = self.config["photo_projection_contract"]
        self.assertEqual(contract["allowed_photo_overlays"], qual.ROW1_PRIMITIVES)
        self.assertIn("class6", qual.ROW1_PRIMITIVES[1])
        self.assertIn("class2", qual.ROW1_PRIMITIVES[2])
        self.assertTrue(contract["dense_tin_boundary_overlay_forbidden"])
        self.assertTrue(contract["footprint_overlay_forbidden"])

    def test_single_view_slot_policy_is_full_context_tight(self) -> None:
        slots = qual.V3.photo_slot_plan([{"name": "one.jpg"}])
        self.assertEqual([item["crop_profile"] for item in slots], ["full", "medium", "tight"])
        self.assertEqual({item["view"]["name"] for item in slots}, {"one.jpg"})

    def test_view_selector_uses_nadir_as_primary_rank_and_returns_one(self) -> None:
        config = json.loads(json.dumps(self.config))
        config["photo_projection_contract"]["minimum_projected_boundary_bbox_area_px2"] = 1.0
        config["photo_projection_contract"]["minimum_projected_boundary_bbox_fraction"] = 0.0
        ring = np.asarray([[0, 0, 10], [1, 0, 10], [1, 1, 10], [0, 1, 10]], dtype=float)
        camera = SimpleNamespace(width=100, height=100)
        views = {
            "oblique.jpg": SimpleNamespace(camera=camera, center_canonical=np.asarray([100.0, 0.0, 100.0])),
            "nadir.jpg": SimpleNamespace(camera=camera, center_canonical=np.asarray([5.0, 0.0, 100.0])),
        }
        receipt = {
            "all_vertices_valid": True, "all_vertices_inside_full_frame": True,
            "all_vertices_inside_margin": True, "bbox_area_px2": 500.0,
            "bbox_area_fraction": 0.05, "projected_polygon_area_px2": 400.0,
            "frame_center_radius": 0.1, "rings_n": 1, "vertices_n": 5,
        }
        visibility = {"passes_target_roof_visibility_gate": True, "visible_target_fraction": 0.8}
        with tempfile.TemporaryDirectory(prefix="dense-v4-view-") as temporary:
            directory = Path(temporary)
            for name in views:
                Image.new("RGB", (100, 100)).save(directory / name)
            with (
                mock.patch.object(qual, "_target_center_canonical", return_value=np.zeros(3)),
                mock.patch.object(qual.V3, "project_reference_roof_boundaries", return_value=([ring[:, :2]], receipt)),
                mock.patch.object(qual.V3, "raycast_target_roof_visibility", return_value=visibility),
            ):
                selected = qual.select_reference_photo_views(
                    "DEBY_LOD2_test", [ring], views, {}, directory,
                    SimpleNamespace(), config,
                )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["name"], "nadir.jpg")
        self.assertLess(selected[0]["nadir_deg"], 30.0)

    def test_target_reference_triangles_are_excluded_from_dense_occluders(self) -> None:
        ring = np.asarray([[0, 0, 10], [1, 0, 10], [1, 1, 10], [0, 1, 10]], dtype=float)
        target = np.asarray([[[-1, -1, 10], [2, -1, 10], [0, 2, 10]]], dtype=float)
        other = np.asarray([[[5, 5, 10], [6, 5, 10], [5, 6, 10]]], dtype=float)
        scene = qual.V3.LoD2RaycastScene(
            triangles_xyz=np.concatenate((target, other), axis=0),
            building_ids=np.asarray(["DEBY_LOD2_target", "DEBY_LOD2_other"], dtype=object),
            semantic_types=np.asarray(["RoofSurface", "RoofSurface"], dtype=object),
            source_records=(), stats={},
        )
        config = json.loads(json.dumps(self.config))
        config["photo_projection_contract"]["visibility_gate"]["surrounding_scene_aoi_margin_m"] = 20.0
        observed, excluded = qual._local_scene_triangles("DEBY_LOD2_target", [ring], scene, config)
        self.assertEqual(excluded, 1)
        self.assertEqual(len(observed), 1)
        np.testing.assert_allclose(observed[0], other[0])

    def test_dense_projection_receipts_are_class_specific(self) -> None:
        source = inspect.getsource(qual.project_visible_dense_points)
        self.assertIn("classification", inspect.signature(qual.project_visible_dense_points).parameters)
        self.assertIn("class-{int(classification)}", source)
        self.assertIn('"classification": int(classification)', source)

    def test_raw_reference_extractor_preserves_original_xyz(self) -> None:
        xml = """<?xml version='1.0'?>
        <CityModel xmlns:gml='http://www.opengis.net/gml' xmlns:bldg='http://www.opengis.net/citygml/building/1.0'>
          <bldg:Building gml:id='DEBY_LOD2_test'><bldg:boundedBy><bldg:RoofSurface>
            <gml:Polygon><gml:exterior><gml:LinearRing><gml:posList srsDimension='3'>
              0 0 10  2 0 11  2 2 12  0 2 10
            </gml:posList></gml:LinearRing></gml:exterior></gml:Polygon>
          </bldg:RoofSurface></bldg:boundedBy></bldg:Building>
        </CityModel>"""
        with tempfile.TemporaryDirectory(prefix="dense-v4-gml-") as temporary:
            path = Path(temporary) / "test.gml"
            path.write_text(xml, encoding="utf-8")
            observed = qual.load_raw_reference_roof_exterior_rings([path], {"DEBY_LOD2_test"})
        ring = observed["DEBY_LOD2_test"][0]
        np.testing.assert_allclose(ring[:4, 2], [10.0, 11.0, 12.0, 10.0])
        self.assertTrue(np.array_equal(ring[0], ring[-1]))

    def test_reference_only_plot_function_cannot_receive_roofer_surfaces(self) -> None:
        signature = inspect.signature(qual.plot_reference_only)
        self.assertIn("reference_rings", signature.parameters)
        self.assertNotIn("surfaces", signature.parameters)
        source = inspect.getsource(qual.render_building)
        row4_block = source[source.index("reference_faces = 0"):source.index("comparison_lines =")]
        self.assertIn("plot_reference_only", row4_block)
        self.assertNotIn("plot_cityjson", row4_block)
        self.assertIn("reference_only_frame", row4_block)

    def test_roofer_footprint_and_quality_caveats_are_source_locked(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("approved/reference-derived LoD2 GroundSurface XY footprint", source)
        self.assertIn("assembled/valid shell != geometric quality", source)
        self.assertIn("nodata_fraction", source)
        self.assertNotIn("LoD2 shell/shape-output success", source)

    def test_wrapper_is_cpu_only_and_refuses_overwrite(self) -> None:
        wrapper = (REPO / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_dense_baseline_qualitative_v4_20260728.sh").read_text(encoding="utf-8")
        self.assertIn("--network=none", wrapper)
        self.assertIn("--read-only", wrapper)
        self.assertNotIn("--gpus", wrapper)
        self.assertIn("output exists; overwrite refused", wrapper)

    def test_config_is_verdict_free_and_new_namespace(self) -> None:
        self.assertEqual(self.config["publication"]["learning_runs_started"], 0)
        self.assertIsNone(self.config["publication"]["scientific_verdict"])
        self.assertTrue(self.config["outputs"]["root"].endswith("_v4"))


if __name__ == "__main__":
    unittest.main()

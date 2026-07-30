#!/usr/bin/env python3
"""Contract tests for dense qualitative v5."""
from __future__ import annotations

import importlib.util
import inspect
import sqlite3
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
from shapely import wkb


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v5_20260728.py"
SPEC = importlib.util.spec_from_file_location("fusion_w1_dense_baseline_qualitative_v5", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import {MODULE_PATH}")
qual = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = qual
SPEC.loader.exec_module(qual)


class DenseBaselineQualitativeV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = qual.load_config()

    def test_frozen_sample_and_new_namespace(self) -> None:
        self.assertEqual(tuple(self.config["sample_freeze"]["selected_building_ids"]), qual.EXPECTED_SELECTED)
        self.assertTrue(self.config["outputs"]["root"].endswith("_v5"))
        self.assertEqual(self.config["publication"]["learning_runs_started"], 0)
        self.assertIsNone(self.config["publication"]["scientific_verdict"])

    def test_one_input_has_two_class_roles(self) -> None:
        contract = self.config["canonical_roofer_crop_contract"]
        self.assertEqual(contract["source_laz_classifications_present"], [1, 2, 6])
        self.assertEqual(contract["roofer_classifications_consumed"], [2, 6])
        self.assertEqual(contract["defaults_verified_from_roofer_help_all"]["bld_class"], 6)
        self.assertEqual(contract["defaults_verified_from_roofer_help_all"]["grnd_class"], 2)
        self.assertIn("same crop LAS", contract["row_2_meaning"])

    def test_full_context_unfiltered_crop_contract(self) -> None:
        contract = self.config["canonical_roofer_crop_contract"]
        self.assertEqual(contract["canonical_source_footprints_n"], 199)
        self.assertEqual(contract["expected_crop_objects_n"], 179)
        self.assertEqual(contract["diagnostic_additions"], ["--crop-only", "--crop-output"])
        self.assertTrue(contract["filtered_crop_forbidden"])
        self.assertTrue(contract["crop_only_equivalence_validated"])
        self.assertEqual(contract["crop_only_vs_full_reconstruction_selected_las"], "9 of 9 byte-identical")

    def test_expected_counts_include_zero_ground_case(self) -> None:
        counts = self.config["canonical_roofer_crop_contract"]["expected_frozen_nine_crop_counts"]
        self.assertEqual(counts["DEBY_LOD2_4908178"], {"total": 3089, "class_2": 2866, "class_6": 223})
        self.assertEqual(counts["DEBY_LOD2_104583447"], {"total": 64, "class_2": 0, "class_6": 64})
        self.assertEqual(len(counts), 9)

    def test_crop_export_3d_polygon_is_stripped_to_xy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dense-v5-gpkg-") as temporary:
            path = Path(temporary) / "crop.gpkg"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE gpkg_contents (table_name TEXT, data_type TEXT)")
            connection.execute("CREATE TABLE gpkg_geometry_columns (table_name TEXT, column_name TEXT, srs_id INTEGER)")
            connection.execute("CREATE TABLE geom (building_id TEXT, geom BLOB)")
            connection.execute("INSERT INTO gpkg_contents VALUES ('geom','features')")
            connection.execute("INSERT INTO gpkg_geometry_columns VALUES ('geom','geom',25832)")
            polygon = Polygon([(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0), (0, 0, 0)])
            blob = b"GP" + bytes((0, 1)) + struct.pack("<i", 25832) + wkb.dumps(polygon, output_dimension=3)
            connection.execute("INSERT INTO geom VALUES (?,?)", ("DEBY_LOD2_test", blob))
            connection.commit(); connection.close()
            ring, source_has_z = qual._load_crop_footprint(path, "DEBY_LOD2_test")
        self.assertTrue(source_has_z)
        self.assertEqual(ring.shape[1], 2)
        np.testing.assert_allclose(ring[0], ring[-1])

    def test_empty_class2_is_explicitly_supported(self) -> None:
        source = inspect.getsource(qual.projected_photo_panel)
        self.assertIn("if len(class2_points)", source)
        self.assertIn("contains zero class-2 points", source)
        render = inspect.getsource(qual.render_building)
        self.assertNotIn("len(class2_points) and", render)
        self.assertIn("if len(class2_points) else", render)

    def test_row_contract_is_input_output_reference(self) -> None:
        source = inspect.getsource(qual.render_building)
        self.assertIn("One canonical-equivalent Roofer input, colored by role", source)
        self.assertIn("Canonical CityJSON output", source)
        self.assertIn("Reference LoD2 ONLY", source)
        self.assertEqual(qual.ROW2_PRIMITIVES[0], "one_roofer_crop_stage_LAS_colored_by_class_role")

    def test_receipt_columns_mask_neighboring_3d_artists(self) -> None:
        helper = inspect.getsource(qual._opaque_text_panel)
        self.assertIn('ax.set_zorder(20)', helper)
        self.assertIn('ax.patch.set_facecolor("white")', helper)
        self.assertIn('facecolor="white"', helper)
        source = inspect.getsource(qual.render_building)
        self.assertEqual(source.count("_opaque_text_panel("), 3)

    def test_wrapper_replays_full_aoi_without_filter(self) -> None:
        wrapper = (REPO / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_dense_baseline_qualitative_v5_20260728.sh").read_text(encoding="utf-8")
        self.assertIn("--box 690791.740 5335864.050 691154.650 5336353.850", wrapper)
        self.assertIn("--crop-only --crop-output", wrapper)
        self.assertNotIn("--filter", wrapper)
        self.assertIn("output exists; overwrite refused", wrapper)
        self.assertIn("--network=none", wrapper)

    def test_only_selected_crop_objects_are_bundled(self) -> None:
        source = inspect.getsource(qual.publish)
        self.assertIn("copy_selected_crop_bundle", source)
        self.assertNotIn("shutil.copytree(crop_root", source)
        helper = inspect.getsource(qual.copy_selected_crop_bundle)
        self.assertIn("for building_id in building_ids", helper)
        self.assertIn("Number of source footprints: 199", helper)


if __name__ == "__main__":
    unittest.main()

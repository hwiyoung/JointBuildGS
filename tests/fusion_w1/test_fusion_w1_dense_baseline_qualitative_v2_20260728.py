#!/usr/bin/env python3
"""Unit and contract tests for the corrected P0 dense-baseline publisher."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v2_20260728.py"
)
SPEC = importlib.util.spec_from_file_location(
    "fusion_w1_dense_baseline_qualitative_v2", MODULE_PATH
)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot import {MODULE_PATH}")
qual = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = qual
SPEC.loader.exec_module(qual)


EXPECTED_SELECTED = [
    "DEBY_LOD2_4908178",
    "DEBY_LOD2_104583447",
    "DEBY_LOD2_4959753",
    "DEBY_LOD2_60097",
    "DEBY_LOD2_4907023",
    "DEBY_LOD2_4908353",
    "DEBY_LOD2_4907207",
    "DEBY_LOD2_4959461",
    "DEBY_LOD2_60042",
]


class DenseBaselineQualitativeV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = qual.load_config()
        cls.result = qual.select_sample(cls.config)

    def test_population_is_dual_verified_canonical_114(self) -> None:
        self.assertEqual(len(self.result.population_ids), 114)
        self.assertEqual(len(set(self.result.population_ids)), 114)
        self.assertEqual(tuple(sorted(self.result.population_ids)), self.result.population_ids)
        self.assertEqual(
            self.result.population_set_sha256,
            "5481f13b5741909ea1fd2cb3fd014459410adea60e3febc72ae8ebb149a2814f",
        )
        self.assertNotIn("DEBY_LOD2_108247714", self.result.population_ids)
        source_paths = {record["path"] for record in self.result.source_records}
        self.assertIn(
            "phases/p2-gsjso/runs/boundary_and_robustness/20260719_boundary_map_v3/label_inventory.json",
            source_paths,
        )
        self.assertIn("docs/experiments/evaluation/attr_outcome_regression/tables/regression_input_snapshot.csv", source_paths)

    def test_deterministic_nine_cell_selection_matches_independent_result(self) -> None:
        selected = [row["building_id"] for row in self.result.selected]
        self.assertEqual(selected, EXPECTED_SELECTED)
        self.assertEqual(len(set(selected)), 9)
        expected_cells = [
            (size, observation)
            for size in ("low", "mid", "high")
            for observation in ("low", "mid", "high")
        ]
        observed_cells = [
            (row["stratum_size_area"], row["stratum_observation_recon_score"])
            for row in self.result.selected
        ]
        self.assertEqual(observed_cells, expected_cells)

    def test_selection_audit_covers_each_population_member_once(self) -> None:
        self.assertEqual(len(self.result.audit_rows), 114)
        self.assertEqual(
            {row["building_id"] for row in self.result.audit_rows},
            set(self.result.population_ids),
        )
        self.assertEqual(sum(bool(row["selected"]) for row in self.result.audit_rows), 9)
        candidate_counts = {}
        for row in self.result.audit_rows:
            cell = (row["stratum_size_area"], row["stratum_observation_recon_score"])
            candidate_counts.setdefault(cell, row["cell_candidate_count"])
            self.assertEqual(candidate_counts[cell], row["cell_candidate_count"])
            self.assertGreaterEqual(row["distance_to_cell_median_l2"], 0.0)
        self.assertEqual(sum(candidate_counts.values()), 114)

    def test_selector_whitelist_has_no_outcome_or_reference_fields(self) -> None:
        selection = self.config["selection_contract"]
        allowed = set(selection["allowed_selector_fields"])
        prohibited = set(selection["prohibited_selector_fields"])
        self.assertFalse(allowed & prohibited)
        self.assertNotIn("assembled", allowed)
        self.assertNotIn("val3dity_valid", allowed)
        self.assertNotIn("rf_rmse_lod22", allowed)
        self.assertNotIn("rf_roof_planes", allowed)
        self.assertNotIn("ref_roof_planes", allowed)
        for row in self.result.audit_rows:
            self.assertFalse(set(row) & prohibited)

    def test_global_midrank_is_tie_robust_and_scaled(self) -> None:
        observed = qual.midrank_01({"b": 1.0, "a": 1.0, "d": 4.0, "c": 2.0})
        self.assertEqual(observed["a"], observed["b"])
        self.assertAlmostEqual(observed["a"], (1.5 - 1.0) / 3.0)
        self.assertAlmostEqual(observed["c"], (3.0 - 1.0) / 3.0)
        self.assertEqual(observed["d"], 1.0)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in observed.values()))

    def test_cell_distance_tie_breaks_by_building_id(self) -> None:
        ranks = {
            "x": {"DEBY_LOD2_2": 0.25, "DEBY_LOD2_1": 0.75},
            "y": {"DEBY_LOD2_2": 0.75, "DEBY_LOD2_1": 0.25},
        }
        medians, scored = qual.cell_median_scores(
            ["DEBY_LOD2_2", "DEBY_LOD2_1"], ranks, ["x", "y"]
        )
        self.assertEqual(medians, {"x": 0.5, "y": 0.5})
        self.assertAlmostEqual(scored[0][0], scored[1][0])
        self.assertEqual([item[1] for item in scored], ["DEBY_LOD2_1", "DEBY_LOD2_2"])

    def test_photo_addresses_are_deferred_until_postselection_geometry_binding(self) -> None:
        source_paths = {record["path"] for record in self.result.source_records}
        self.assertIn("docs/experiments/input-and-alignment/boundary_map/tables/boundary_map_v2_ladder.csv", source_paths)
        self.assertNotIn("docs/boundary_map_v2_metrics.csv", source_paths)
        for row in self.result.selected:
            self.assertNotIn("representative_views", row)
        binding = self.config["selection_contract"]["representative_photo_binding"]
        self.assertIn("after sample selection and class-6 clipping", binding)
        self.assertIn("actual DIM class-6 TIN support boundary", binding)
        self.assertIn("reference geometry never affects ranking", binding)

    def test_circular_camera_separation_handles_wraparound(self) -> None:
        self.assertAlmostEqual(qual.circular_separation_deg(350.0, 10.0), 20.0)
        self.assertAlmostEqual(qual.circular_separation_deg(10.0, 350.0), 20.0)
        self.assertAlmostEqual(qual.circular_separation_deg(45.0, 225.0), 180.0)

    def test_config_is_4x5_verdict_free_and_cpu_only(self) -> None:
        visual = self.config["visual_contract"]
        self.assertEqual((visual["rows"], visual["columns"]), (4, 5))
        self.assertEqual(tuple(visual["mandatory_labels"]), qual.MANDATORY_LABELS)
        self.assertEqual(visual["camera_contract"]["projection"], "orthographic")
        self.assertEqual(visual["camera_contract"]["z_exaggeration"], 1.0)
        publication = self.config["publication"]
        self.assertFalse(publication["overwrite_allowed"])
        self.assertTrue(publication["output_directory_atomic_publish"])
        self.assertEqual(publication["learning_runs_started"], 0)
        self.assertIsNone(publication["scientific_verdict"])
        self.assertIsNone(publication["interpretation"])
        execution = self.config["execution"]
        self.assertEqual(execution["network"], "none")
        self.assertFalse(execution["gpus_required"])
        self.assertTrue(execution["nonroot"])

    def test_wrapper_locks_network_cpu_dependencies_and_output_policy(self) -> None:
        wrapper = (
            REPO
            / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_dense_baseline_qualitative_v2_20260728.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("--network=none", wrapper)
        self.assertIn("--read-only", wrapper)
        self.assertIn("--cpus=6", wrapper)
        self.assertNotIn("--gpus", wrapper)
        self.assertIn(
            "import laspy, lxml, matplotlib, numpy, PIL, shapely",
            wrapper,
        )
        self.assertIn("output exists; overwrite refused", wrapper)
        self.assertIn("$OUTPUT_PARENT_REL:rw", wrapper)

    def test_projection_contract_is_explicit_and_legacy_p0_helper_is_absent(self) -> None:
        contract = self.config["photo_projection_contract"]
        self.assertEqual(contract["input_vertical_datum"], "orthometric")
        self.assertTrue(contract["flat_single_Z_footprint_projection_forbidden"])
        self.assertTrue(contract["reference_roof_boundary_forbidden"])
        self.assertEqual(contract["additional_pose_transform_application_count"], 0)
        implementation = set(self.config["implementation_files"])
        self.assertIn("src/stage2/image_projection.py", implementation)
        self.assertIn("phases/p2-gsjso/scripts/fusion_w1/roof_boundary_overlay.py", implementation)
        self.assertNotIn("phases/p0-audit/scripts/07_failure_diagnosis.py", implementation)
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("T7.project_points", source)
        self.assertNotIn("07_failure_diagnosis.py", source)
        image_source = self.config["sources"]["image_directory"]
        self.assertEqual(
            image_source["path"],
            "phases/p0-audit/data/work/mvs/colmap_dense/images",
        )
        self.assertIn("matching corrected cameras.bin", image_source["role"])

    def test_actual_xyz_boundary_is_not_flattened(self) -> None:
        points = np.asarray(
            [
                [0.0, 0.0, 10.0],
                [1.0, 0.0, 10.5],
                [1.0, 1.0, 11.0],
                [0.0, 1.0, 10.5],
            ],
            dtype=np.float64,
        )
        boundary = qual.build_input_roof_boundary(self.config, points)
        self.assertGreater(float(np.ptp(boundary.boundary_segments_xyz[..., 2])), 0.9)

    def test_target_cityjson_parser_does_not_mix_buildings(self) -> None:
        payload = {
            "type": "CityJSON",
            "version": "2.0",
            "transform": {"scale": [1, 1, 1], "translate": [0, 0, 0]},
            "vertices": [
                [0, 0, 10],
                [1, 0, 10],
                [1, 1, 10],
                [0, 1, 10],
                [100, 100, 20],
                [101, 100, 20],
                [101, 101, 20],
                [100, 101, 20],
            ],
            "CityObjects": {
                "DEBY_LOD2_1": {"type": "Building", "children": ["part_1"]},
                "part_1": {
                    "type": "BuildingPart",
                    "parents": ["DEBY_LOD2_1"],
                    "geometry": [
                        {
                            "type": "Solid",
                            "lod": "2.2",
                            "boundaries": [[[[0, 1, 2, 3]]]],
                            "semantics": {
                                "surfaces": [{"type": "RoofSurface"}],
                                "values": [[0]],
                            },
                        }
                    ],
                },
                "DEBY_LOD2_2": {"type": "Building", "children": ["part_2"]},
                "part_2": {
                    "type": "BuildingPart",
                    "parents": ["DEBY_LOD2_2"],
                    "geometry": [
                        {
                            "type": "Solid",
                            "lod": "2.2",
                            "boundaries": [[[[4, 5, 6, 7]]]],
                            "semantics": {
                                "surfaces": [{"type": "RoofSurface"}],
                                "values": [[0]],
                            },
                        }
                    ],
                },
            },
        }
        surfaces, stats = qual.load_cityjson_surfaces_for_building(payload, "DEBY_LOD2_1")
        self.assertEqual(len(surfaces), 1)
        self.assertEqual(stats["vertices_n"], 4)
        self.assertEqual(stats["semantic_counts"], {"RoofSurface": 1})
        self.assertLess(float(np.max(surfaces[0]["xyz"][:, 0])), 2.0)

    def test_locked_footprint_reader_uses_configured_geopackage(self) -> None:
        footprints, record = qual.load_locked_footprints(
            self.config, [EXPECTED_SELECTED[0]]
        )
        self.assertEqual(set(footprints), {EXPECTED_SELECTED[0]})
        self.assertGreater(footprints[EXPECTED_SELECTED[0]].area, 0.0)
        self.assertEqual(
            record["sha256"],
            self.config["sources"]["approved_footprint_xy"]["sha256"],
        )
        self.assertTrue(record["path"].endswith("lod2_ground_plan.gpkg"))

    def test_selection_audit_payload_has_no_interpretation(self) -> None:
        payload = qual.selection_audit_payload(self.config, self.result)
        self.assertEqual(payload["schema"], qual.AUDIT_SCHEMA)
        self.assertEqual(payload["population"]["count"], 114)
        self.assertTrue(payload["population"]["dual_source_exact_match"])
        self.assertEqual(payload["candidate_audit_row_count"], 114)
        self.assertEqual(payload["outcome_or_reference_fields_used_after_population_lock"], [])
        self.assertIsNone(payload["scientific_verdict"])
        self.assertIsNone(payload["interpretation"])

    def test_exclusive_json_writer_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dense-baseline-qual-test-") as temporary:
            path = Path(temporary) / "record.json"
            qual.write_json_new(path, {"state": "first"})
            with self.assertRaisesRegex(qual.DenseBaselineError, "overwrite refused"):
                qual.write_json_new(path, {"state": "second"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"state": "first"})

    def test_source_ledger_rehashes_and_rejects_drift(self) -> None:
        source = REPO / "configs/input_and_alignment/projection_datum.json"
        record = qual.file_record(source)
        self.assertEqual(qual.verify_source_records([record]), 1)
        tampered = dict(record)
        tampered["sha256"] = "0" * 64
        with self.assertRaisesRegex(qual.DenseBaselineError, "source hash drift"):
            qual.verify_source_records([tampered])

    def test_config_rejects_outcome_leakage(self) -> None:
        tampered = copy.deepcopy(self.config)
        tampered["selection_contract"]["allowed_selector_fields"].append("rf_rmse_lod22")
        with tempfile.TemporaryDirectory(prefix="dense-baseline-config-test-") as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(qual.DenseBaselineError, "overlap|outcome leaked"):
                qual.load_config(path, verify_sources=False)


if __name__ == "__main__":
    unittest.main()

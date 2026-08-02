from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import src.evaluation.c1_c2_dev_gate_closure_v1.evaluator as evaluator

from src.evaluation.c1_c2_dev_gate_closure_v1.evaluator import (
    evaluate_g3,
    evaluate_g4,
    evaluate_row,
    load_config,
    parse_cityjsonseq_roof_surfaces,
    parse_val3dity_cjseq_stdout,
)
from src.evaluation.c1_c2_dev_gate_closure_v1.g2_runner import _c2_cityjson_records


def _candidate_config() -> dict:
    config = copy.deepcopy(load_config())
    config["gates"]["G3"]["grid_origin_xy"] = [0.0, 0.0]
    return config


def _flat_square_surfaces():
    header = {
        "type": "CityJSON",
        "version": "2.0",
        "transform": {"scale": [1, 1, 1], "translate": [0, 0, 0]},
        "vertices": [],
        "CityObjects": {},
    }
    record = {
        "type": "CityJSONFeature",
        "id": "feature-1",
        "vertices": [[0, 0, 10], [2, 0, 10], [2, 2, 10], [0, 2, 10]],
        "CityObjects": {
            "building": {
                "type": "Building",
                "geometry": [
                    {
                        "type": "MultiSurface",
                        "lod": "2.2",
                        "boundaries": [[[0, 1, 2, 3]]],
                        "semantics": {
                            "surfaces": [{"type": "RoofSurface"}],
                            "values": [0],
                        },
                    }
                ],
            }
        },
    }
    return parse_cityjsonseq_roof_surfaces(
        (json.dumps(header) + "\n" + json.dumps(record) + "\n").encode("utf-8")
    )


def _reference_rows(normal=(0.0, 0.0, 1.0)):
    return [
        {
            "stable_id": "B001",
            "patch_id": "P1",
            "cell_ix": ix,
            "cell_iy": iy,
            "normal_x": normal[0],
            "normal_y": normal[1],
            "normal_z": normal[2],
        }
        for iy in range(2)
        for ix in range(2)
    ]


def _metric_row(method="C2_MVS", **overrides):
    row = {
        "building_id": "B001",
        "group_id": "G01",
        "split": "development",
        "method_id": method,
        "run_id": "sealed-r4",
        "operation_id": "op-1",
        "operation_unit_id": "C2_MVS|component-1",
        "G0_generated": "true",
        "G1_schema_semantic": "true",
        "reference_vertical_coverage": "0.9",
        "height_error_mae_m": "0.5",
        "RMSZ_m": "0.5",
        "RMSXY_m": "0.5",
        "surface_distance_rmse_m": "0.5",
        "surface_distance_p95_m": "1.0",
    }
    row.update(overrides)
    return row


def _g2_unit(valid=True):
    errors = [] if valid else [302]
    return {
        "operation_unit_id": "C2_MVS|component-1",
        "source": {"path": "sealed.jsonl", "bytes": 1, "sha256": "0" * 64},
        "result": {
            "features": [{"feature_id": "feature-1", "error_codes": errors, "valid": valid}],
            "unit_valid": valid,
        },
    }


class GateClosureCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = _candidate_config()
        cls.surfaces = _flat_square_surfaces()

    def test_contract_pins_g2_but_keeps_g3_g4_diagnostic(self):
        self.assertEqual(self.config["status"], "USER_DIRECTED_PROVISIONAL_DEVELOPMENT_DIAGNOSTIC_CLOSURE")
        self.assertIsNone(self.config["scientific_verdict"])
        self.assertEqual(
            self.config["gates"]["G2"]["status"],
            "READY_PINNED_IMAGE_AND_STDIN_CONTRACT",
        )
        self.assertEqual(
            self.config["gates"]["G2"]["command"],
            [
                "val3dity",
                "--overlap_tol",
                "-1.0",
                "--planarity_d2p_tol",
                "0.01",
                "--planarity_n_tol",
                "20.0",
                "--snap_tol",
                "0.001",
                "stdin",
            ],
        )
        self.assertEqual(
            self.config["provisional_threshold_calibration"]["status"],
            "DRAFT_NOT_EXECUTED_DEVELOPMENT_ONLY",
        )

    def test_bound_text_specs_equal_committed_lf_git_blobs(self):
        repo = Path(evaluator.REPO).resolve()
        for spec in self.config["inputs"].values():
            process = subprocess.run(
                [
                    "git",
                    "-c",
                    "safe.directory=",
                    "-c",
                    f"safe.directory={repo}",
                    "-C",
                    str(repo),
                    "cat-file",
                    "blob",
                    f"HEAD:{spec['path']}",
                ],
                check=True,
                capture_output=True,
            )
            blob = process.stdout
            self.assertNotIn(b"\r", blob)
            self.assertEqual(len(blob), spec["bytes"])
            self.assertEqual(hashlib.sha256(blob).hexdigest(), spec["sha256"])

    def test_bound_text_accepts_only_crlf_portability_not_lone_cr_or_drift(self):
        lf = b"alpha\nbeta\n"
        spec = {
            "path": "synthetic.txt",
            "bytes": len(lf),
            "sha256": hashlib.sha256(lf).hexdigest(),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.txt"
            with patch.object(evaluator, "repo_path", return_value=path):
                path.write_bytes(lf.replace(b"\n", b"\r\n"))
                self.assertEqual(evaluator._read_bound_file(spec), lf)
                path.write_bytes(b"alpha\rbeta\n")
                with self.assertRaisesRegex(evaluator.ClosureError, "line endings"):
                    evaluator._read_bound_file(spec)
                path.write_bytes(b"alpha\nBETa\n")
                with self.assertRaisesRegex(evaluator.ClosureError, "identity"):
                    evaluator._read_bound_file(spec)

    def test_val3dity_stdin_output_parser(self):
        result = parse_val3dity_cjseq_stdout(
            b'"1st-line" []\n"feature-1" []\n"feature-2" [302]\n',
            ["feature-1", "feature-2"],
        )
        self.assertFalse(result["unit_valid"])
        self.assertEqual(result["features"][1]["error_codes"], [302])

    def test_g2_runner_selects_exact_six_c2_units(self):
        manifest = {
            "records": [
                {"path": f"operations/C2_MVS/COMP_{index}/work/out/tile.jsonl"}
                for index in range(6)
            ]
        }
        self.assertEqual(len(_c2_cityjson_records(manifest)), 6)

    def test_cityjson_roof_surface_and_g3_exact_match(self):
        self.assertEqual(len(self.surfaces), 1)
        score = evaluate_g3(_reference_rows(), self.surfaces, [0, 0, 2, 2], self.config)
        self.assertEqual(score["roof_plane_completeness"], 1.0)
        self.assertEqual(score["roof_plane_correctness"], 1.0)
        self.assertEqual(score["roof_plane_quality"], 1.0)
        self.assertTrue(score["G3_roof_structure_acceptable"])
        self.assertTrue(score["candidate_only"])

    def test_cityjsonseq_header_transform_is_inherited_and_not_parsed_as_feature(self):
        header = {
            "type": "CityJSON",
            "version": "2.0",
            "transform": {"scale": [2, 3, 1], "translate": [10, 20, 0]},
            "vertices": [],
            "CityObjects": {},
        }
        feature = {
            "type": "CityJSONFeature",
            "id": "feature-1",
            "vertices": [[0, 0, 10], [1, 0, 10], [1, 1, 10]],
            "CityObjects": {
                "building": {
                    "type": "Building",
                    "geometry": [{
                        "type": "MultiSurface",
                        "lod": "2.2",
                        "boundaries": [[[0, 1, 2]]],
                        "semantics": {
                            "surfaces": [{"type": "RoofSurface"}],
                            "values": [0],
                        },
                    }],
                }
            },
        }
        data = (json.dumps(header) + "\n" + json.dumps(feature) + "\n").encode("utf-8")
        surfaces = parse_cityjsonseq_roof_surfaces(data)
        self.assertEqual(len(surfaces), 1)
        np.testing.assert_allclose(surfaces[0].triangles[0][0], [10, 20, 10])

    def test_cityjsonseq_rejects_missing_duplicate_or_malformed_header_and_feature(self):
        valid_header = {
            "type": "CityJSON",
            "transform": {"scale": [1, 1, 1], "translate": [0, 0, 0]},
            "vertices": [],
            "CityObjects": {},
        }
        valid_feature = {
            "type": "CityJSONFeature",
            "id": "feature-1",
            "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            "CityObjects": {"building": {"type": "Building", "geometry": []}},
        }
        cases = {
            "feature_before_header": [valid_feature],
            "duplicate_header": [valid_header, valid_header, valid_feature],
            "nonempty_header": [{**valid_header, "vertices": [[0, 0, 0]]}, valid_feature],
            "bad_transform": [{**valid_header, "transform": {"scale": [1, 1], "translate": [0, 0, 0]}}, valid_feature],
            "feature_transform": [valid_header, {**valid_feature, "transform": valid_header["transform"]}],
            "empty_feature_vertices": [valid_header, {**valid_feature, "vertices": []}],
        }
        for name, records in cases.items():
            with self.subTest(name=name), self.assertRaises(evaluator.ClosureError):
                parse_cityjsonseq_roof_surfaces(
                    ("\n".join(json.dumps(record) for record in records) + "\n").encode("utf-8")
                )

    def test_g3_rejects_normal_mismatch(self):
        score = evaluate_g3(
            _reference_rows(normal=(1.0, 0.0, 0.0)),
            self.surfaces,
            [0, 0, 2, 2],
            self.config,
        )
        self.assertEqual(score["roof_plane_completeness"], 0.0)
        self.assertFalse(score["G3_roof_structure_acceptable"])

    def test_g4_uses_min_and_max_threshold_directions(self):
        passed, _, reason = evaluate_g4(_metric_row(), self.config)
        self.assertTrue(passed)
        self.assertIsNone(reason)
        failed_coverage, _, _ = evaluate_g4(
            _metric_row(reference_vertical_coverage="0.7"), self.config
        )
        failed_p95, _, _ = evaluate_g4(
            _metric_row(surface_distance_p95_m="2.1"), self.config
        )
        self.assertFalse(failed_coverage)
        self.assertFalse(failed_p95)

    def test_g4_missing_metric_is_null(self):
        value, _, reason = evaluate_g4(_metric_row(RMSXY_m=""), self.config)
        self.assertIsNone(value)
        self.assertEqual(reason, "MISSING_SEALED_CONTINUOUS_METRICS:RMSXY_m")

    def test_c1_self_reference_isolated_and_pass_remains_null(self):
        row = evaluate_row(
            _metric_row(method="C1_L_upper"),
            _reference_rows(),
            self.surfaces,
            [0, 0, 2, 2],
            self.config,
        )
        self.assertIsNone(row["G3_roof_structure_acceptable"])
        self.assertIsNone(row["G4_geometric_accuracy_acceptable"])
        self.assertIsNone(row["PASS_usable"])
        self.assertIn("SELF_REFERENCE", row["gate_null_reasons"]["G3"])

    def test_c2_candidates_compute_but_g2_and_pass_remain_null(self):
        row = evaluate_row(
            _metric_row(),
            _reference_rows(),
            self.surfaces,
            [0, 0, 2, 2],
            self.config,
            _g2_unit(),
        )
        self.assertIsNone(row["G3_roof_structure_acceptable"])
        self.assertIsNone(row["G4_geometric_accuracy_acceptable"])
        self.assertTrue(row["G2_geometry_topology_valid"])
        self.assertIsNone(row["PASS_usable"])
        self.assertEqual(row["reconstruction_invocation_count"], 0)
        self.assertEqual(row["roofer_invocation_count"], 0)
        self.assertEqual(row["validator_invocation_count"], 0)

    def test_invalid_g2_is_known_failure_but_pass_still_null(self):
        row = evaluate_row(
            _metric_row(),
            _reference_rows(),
            self.surfaces,
            [0, 0, 2, 2],
            self.config,
            _g2_unit(valid=False),
        )
        self.assertFalse(row["G2_geometry_topology_valid"])
        self.assertEqual(row["first_known_failure_gate"], "G2")
        self.assertIsNone(row["PASS_usable"])


if __name__ == "__main__":
    unittest.main()

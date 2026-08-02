from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.visualization.fixed_view_qualitative import (
    BBox,
    SUPPLEMENT_STATUS,
    _write_stage_and_correction_funnel,
    load_cityjsonseq,
    render_from_config,
    stream_eligibility_cells,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path.read_bytes()


def write_las(path: Path, offset: float) -> bytes:
    import laspy

    path.parent.mkdir(parents=True, exist_ok=True)
    header = laspy.LasHeader(point_format=3, version="1.2")
    header.scales = np.asarray([0.001, 0.001, 0.001])
    header.offsets = np.asarray([0.0, 0.0, 0.0])
    las = laspy.LasData(header)
    las.x = np.asarray([0.0, 4.0, 8.0, 1.0, 5.0]) + offset
    las.y = np.asarray([0.0, 4.0, 8.0, 5.0, 1.0])
    las.z = np.asarray([0.0, 7.0, 10.0, 8.0, 9.0])
    las.classification = np.asarray([2, 6, 6, 6, 6], dtype=np.uint8)
    las.write(path)
    return path.read_bytes()


def cityjson_rows(offset: float) -> list[dict[str, object]]:
    return [
        {
            "type": "CityJSON",
            "version": "2.0",
            "transform": {"scale": [0.001, 0.001, 0.001], "translate": [offset, 0.0, 0.0]},
            "CityObjects": {},
            "vertices": [],
        },
        {
            "type": "CityJSONFeature",
            "id": "feature",
            "CityObjects": {
                "part": {
                    "type": "BuildingPart",
                    "geometry": [
                        {
                            "type": "Solid",
                            "lod": "2.2",
                            "boundaries": [[[[0, 1, 2, 3]]]],
                            "semantics": {"surfaces": [{"type": "RoofSurface"}], "values": [[0]]},
                        }
                    ],
                }
            },
            "vertices": [[0, 0, 10000], [8000, 0, 10000], [8000, 8000, 10000], [0, 8000, 10000]],
        },
    ]


class CityJsonTest(unittest.TestCase):
    def test_header_transform_is_inherited_and_semantics_retained(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "result.city.jsonl"
            write_jsonl(path, cityjson_rows(100.0))
            surfaces = load_cityjsonseq(path)
            self.assertEqual(len(surfaces), 1)
            self.assertEqual(surfaces[0].semantic, "RoofSurface")
            np.testing.assert_allclose(surfaces[0].xyz[2], [108.0, 8.0, 10.0])


class CompactStreamTest(unittest.TestCase):
    def test_empty_excluded_example_is_not_fabricated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cells.csv"
            data = write_csv(
                path,
                ["patch_id", "cell_x", "cell_y", "top_z"],
                [{"patch_id": "P", "cell_x": 1, "cell_y": 1, "top_z": 5}],
            )
            points, record = stream_eligibility_cells(
                path,
                {
                    "PASS": (BBox(0, 0, 2, 2), {"P"}),
                    "FAIL": (BBox(0, 0, 2, 2), {"F"}),
                },
                expected_bytes=len(data),
                expected_sha256=hashlib.sha256(data).hexdigest(),
                expected_rows=1,
            )
            self.assertEqual(len(points["PASS"].xyz), 1)
            self.assertEqual(len(points["FAIL"].xyz), 0)
            self.assertEqual(record["full_read_and_digest_passes"], 1)


class PromotedR4FunnelTest(unittest.TestCase):
    def test_exact_promoted_r4_values_prove_51_50_and_46_4_1_correction(self) -> None:
        repository = Path(__file__).resolve().parents[3]
        metrics_path = repository / "docs/experiments/p2/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/building_method_metrics_v1.csv"
        config_path = repository / "configs/p2_baselines/c1_c2_qualitative_evaluator_backfill_v1/render_v1.json"
        with metrics_path.open("r", encoding="utf-8", newline="") as stream:
            metric_rows = list(csv.DictReader(stream))
        correction = json.loads(config_path.read_text(encoding="utf-8"))["coverage_correction"]
        with tempfile.TemporaryDirectory() as temp:
            record = _write_stage_and_correction_funnel(Path(temp) / "funnel.csv", metric_rows, correction)
            self.assertEqual(record["g0"]["C1_L_upper"], {"numerator": 51, "denominator": 51})
            self.assertEqual(record["g0"]["C2_MVS"], {"numerator": 50, "denominator": 51})
            self.assertEqual(record["g1"]["C2_MVS"], {"numerator": 50, "denominator": 51})
            self.assertEqual(record["coverage_correction"]["full"], {"numerator": 46, "denominator": 50})
            self.assertEqual(record["coverage_correction"]["partial"], {"numerator": 4, "denominator": 50})
            self.assertEqual(record["coverage_correction"]["absent"], {"numerator": 1, "denominator": 51})
            self.assertEqual(record["coverage_correction"]["supersedes_return_arithmetic"], "47/50")


class EndToEndTest(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        repository = root / "repo"
        artifact = root / "artifact"
        r3 = root / "r3"
        output = root / "output"

        bbox_fields = ["stable_id", "bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y", "reference_candidate_patch_ids"]
        bbox_rows = [
            {"stable_id": "DEBY_LOD2_1", "bbox_min_x": 0, "bbox_min_y": 0, "bbox_max_x": 8, "bbox_max_y": 8, "reference_candidate_patch_ids": "P1"},
            {"stable_id": "DEBY_LOD2_4907183", "bbox_min_x": 0, "bbox_min_y": 0, "bbox_max_x": 8, "bbox_max_y": 8, "reference_candidate_patch_ids": "P1"},
            {"stable_id": "PASS", "bbox_min_x": 0, "bbox_min_y": 0, "bbox_max_x": 2, "bbox_max_y": 2, "reference_candidate_patch_ids": "P1"},
            {"stable_id": "FAIL", "bbox_min_x": 10, "bbox_min_y": 10, "bbox_max_x": 12, "bbox_max_y": 12, "reference_candidate_patch_ids": "PF"},
        ]
        write_csv(repository / "bbox.csv", bbox_fields, bbox_rows)
        metric_fields = ["building_id", "method_id", "G0_generated", "G1_schema_semantic", "RMSZ_m", "reference_vertical_coverage", "vertically_scored_cell_count", "failure_reasons"]
        partial_ids = ["DEBY_LOD2_4907177", "DEBY_LOD2_4907180", "DEBY_LOD2_4907176", "DEBY_LOD2_4906965"]
        roster = ["DEBY_LOD2_1", "DEBY_LOD2_4907183", *partial_ids, *[f"DEBY_LOD2_{1000 + index}" for index in range(45)]]
        self.assertEqual(len(roster), 51)
        metric_rows = []
        for building in roster:
            for method in ("C1_L_upper", "C2_MVS"):
                generated = not (building == "DEBY_LOD2_4907183" and method == "C2_MVS")
                coverage = ""
                scored = 0
                if generated:
                    coverage = "0.5" if method == "C2_MVS" and building in partial_ids else "1.0"
                    scored = 5 if coverage == "0.5" else 10
                metric_rows.append({
                    "building_id": building,
                    "method_id": method,
                    "G0_generated": str(generated),
                    "G1_schema_semantic": str(generated),
                    "RMSZ_m": "1.25" if generated else "",
                    "reference_vertical_coverage": coverage,
                    "vertically_scored_cell_count": scored,
                    "failure_reasons": "" if generated else "UNASSOCIATED_CONDITION_COMPONENT",
                })
        write_csv(repository / "metrics.csv", metric_fields, metric_rows)
        example_fields = ["label", "stable_id", "candidate", "reference_cells", "image_views", "mvs_cells", "c4_cells", "exclusion_reason"]
        write_csv(
            repository / "examples.csv",
            example_fields,
            [
                {"label": "P1", "stable_id": "PASS", "candidate": "True", "reference_cells": 1, "image_views": 2, "mvs_cells": 3, "c4_cells": 4, "exclusion_reason": "PASS_ALL_INPUT_SUPPORT_RULES"},
                {"label": "F1", "stable_id": "FAIL", "candidate": "False", "reference_cells": 3, "image_views": 2, "mvs_cells": 3, "c4_cells": 4, "exclusion_reason": "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT"},
            ],
        )

        compact = write_csv(
            artifact / "compact.csv",
            ["patch_id", "cell_x", "cell_y", "top_z"],
            [
                {"patch_id": "P1", "cell_x": 1, "cell_y": 1, "top_z": 7},
                {"patch_id": "PF", "cell_x": 10.2, "cell_y": 10.2, "top_z": 7},
                {"patch_id": "PF", "cell_x": 10.8, "cell_y": 10.8, "top_z": 8},
                {"patch_id": "PF", "cell_x": 11.5, "cell_y": 11.5, "top_z": 9},
            ],
        )
        associations = [
            {"building_id": "DEBY_LOD2_1", "method_id": "C1_L_upper", "component_id": "C1", "operation_unit_id": "C1_L_upper|C1", "pre_roofer_failure": None},
            {"building_id": "DEBY_LOD2_1", "method_id": "C2_MVS", "component_id": "C2", "operation_unit_id": "C2_MVS|C2", "pre_roofer_failure": None},
            {"building_id": "DEBY_LOD2_4907183", "method_id": "C1_L_upper", "component_id": "C1", "operation_unit_id": "C1_L_upper|C1", "pre_roofer_failure": None},
            {"building_id": "DEBY_LOD2_4907183", "method_id": "C2_MVS", "component_id": None, "operation_unit_id": None, "pre_roofer_failure": None},
        ]
        write_jsonl(r3 / "freeze/associations.jsonl", associations)
        units = []
        city_records = []
        for unit_id, work in (("C1_L_upper|C1", "operations/c1/work"), ("C2_MVS|C2", "operations/c2/work")):
            las_data = write_las(r3 / work / "input.las", 0.0)
            write_json(
                r3 / work / "r_derived.geojson",
                {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [8, 0], [8, 8], [0, 8], [0, 0]]]}, "properties": {}}]},
            )
            roofprint_data = (r3 / work / "r_derived.geojson").read_bytes()
            city_path = r3 / work / "out/result.city.jsonl"
            write_jsonl(city_path, cityjson_rows(0.0))
            city_data = city_path.read_bytes()
            units.append({
                "operation_unit_id": unit_id,
                "work_directory": work,
                "input": {"path": f"{work}/input.las", "bytes": len(las_data), "sha256": hashlib.sha256(las_data).hexdigest()},
                "r_derived": {"path": f"{work}/r_derived.geojson", "bytes": len(roofprint_data), "sha256": hashlib.sha256(roofprint_data).hexdigest()},
            })
            city_records.append({"path": f"{work}/out/result.city.jsonl", "bytes": len(city_data), "sha256": hashlib.sha256(city_data).hexdigest()})
        write_jsonl(r3 / "freeze/units.jsonl", units)
        write_json(repository / "accepted.json", {"schema": "jointbuildgs.p2_c1_c2_r3_finalize_source_manifest.v1", "records": city_records})
        score_rows = [
            {"stable_id": building, "cell_x": str(x), "cell_y": str(y), "top_z": str(z)}
            for building in ("DEBY_LOD2_1", "DEBY_LOD2_4907183")
            for x, y, z in ((1, 1, 7), (5, 5, 9))
        ]
        write_jsonl(r3 / "freeze/scores.jsonl", score_rows)

        allow_records = []
        for path, role in (
            ("freeze/associations.jsonl", "SEALED_ASSOCIATION_CONTROL"),
            ("freeze/units.jsonl", "SEALED_EXECUTION_UNIT_CONTROL"),
            ("freeze/scores.jsonl", "SEALED_DEVELOPMENT_REFERENCE_CONTROL"),
        ):
            data = (r3 / path).read_bytes()
            allow_records.append({"source": "R3", "path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "role": role})
        for unit in units:
            allow_records.append({"source": "R3", **unit["input"], "role": "DERIVED_OPERATION_LAS"})
            allow_records.append({"source": "R3", **unit["r_derived"], "role": "DERIVED_R_DERIVED"})
        allow_records.extend({"source": "R3", **row, "role": "DERIVED_CITYJSONSEQ"} for row in city_records)
        allow_records.append({"source": "COMPACT_REFERENCE", "path": "compact.csv", "bytes": len(compact), "sha256": hashlib.sha256(compact).hexdigest(), "role": "BOUND_COMPACT_REFERENCE_CELLS"})
        allow_identity = hashlib.sha256(json.dumps(allow_records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        write_json(repository / "allowlist.json", {
            "schema": "jointbuildgs.c1_c2_qualitative_evaluator_backfill_artifact_allowlist.v1",
            "task_id": "TEST", "record_count": len(allow_records),
            "total_bytes": sum(int(row["bytes"]) for row in allow_records), "record_identity_sha256": allow_identity,
            "records": allow_records, "scientific_verdict": None,
        })

        config = {
            "schema": "jointbuildgs.c1_c2_qualitative_evaluator_backfill_config.v1",
            "task_id": "TEST",
            "inputs": {
                "artifact_allowlist_git_path": "allowlist.json",
                "r3_associations_path": "freeze/associations.jsonl",
                "r3_execution_units_path": "freeze/units.jsonl",
                "r3_score_cells_path": "freeze/scores.jsonl",
                "development_bboxes_git_path": "bbox.csv",
                "r4_metrics_git_path": "metrics.csv",
                "r4_accepted_r3_source_manifest_git_path": "accepted.json",
            },
            "expected_association_rows": 4,
            "expected_execution_units": 2,
            "expected_unique_execution_units": 2,
            "cases": [
                {"building_id": "DEBY_LOD2_1", "selection_role": "OUTCOME_FREE_PRESELECTED_REPRESENTATIVE"},
                {"building_id": "DEBY_LOD2_4907183", "selection_role": "POST_HOC_DIAGNOSTIC_UNASSOCIATED_C2_EMPTY"},
            ],
            "eligibility": {
                "examples_git_path": "examples.csv",
                "bbox_ledger_git_path": "bbox.csv",
                "example_labels": ["P1", "F1"],
                "compact_reference_cells": {
                    "artifact_relative_path": "compact.csv",
                    "bytes": len(compact),
                    "sha256": hashlib.sha256(compact).hexdigest(),
                    "expected_rows": 4,
                },
            },
            "coverage_correction": {
                "partial_building_ids": partial_ids,
                "absent_building_id": "DEBY_LOD2_4907183",
            },
            "style": {
                "dpi": 45,
                "case_figure_inches": [6, 5],
                "eligibility_figure_inches": [6, 4],
                "viewport_margin_ratio": 0.08,
                "viewport_minimum_margin_m": 0.5,
                "z_pad_ratio": 0.05,
                "z_minimum_pad_m": 0.5,
                "point_size": 2.0,
                "eligibility_point_size": 3.0,
                "line_width": 0.5,
                "colormap": "viridis",
                "oblique_elevation_deg": 32.0,
                "oblique_azimuth_deg": -58.0,
                "section_band_ratio": 0.1,
                "section_minimum_half_band_m": 1.0,
            },
        }
        config_path = repository / "config.json"
        write_json(config_path, config)
        return config_path, artifact, r3, output

    def test_real_entry_function_preserves_fair_camera_and_empty_c2(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config, artifact, r3, output = self._fixture(root)
            manifest = render_from_config(config_path=config, repository_root=root / "repo", artifact_root=artifact, r3_root=r3, output_dir=output)
            self.assertEqual(manifest["status"], SUPPLEMENT_STATUS)
            self.assertIsNone(manifest["scientific_verdict"])
            self.assertEqual(manifest["scope"]["metric_recomputation_count"], 0)
            self.assertEqual(manifest["scope"]["roofer_invocation_count"], 0)
            self.assertEqual(len(manifest["case_sheets"]), 2)
            empty_sheet = next(value for value in manifest["case_sheets"] if value["building_id"] == "DEBY_LOD2_4907183")
            self.assertEqual(empty_sheet["methods"]["C2_MVS"]["empty_reason"], "UNASSOCIATED_CONDITION_COMPONENT")
            self.assertEqual(empty_sheet["methods"]["C2_MVS"]["displayed_points"], 0)
            eligibility = {value["stable_id"]: value for value in manifest["eligibility"]["examples"]}
            self.assertEqual(eligibility["PASS"]["actual_compact_rows"], 1)
            self.assertEqual(eligibility["FAIL"]["actual_compact_rows"], 3)
            self.assertEqual(eligibility["FAIL"]["recorded_reference_cells"], 3)
            self.assertEqual(manifest["input_reads"]["unique_execution_units"], 2)
            self.assertEqual(manifest["input_reads"]["duplicate_payload_reads_prevented"], 1)
            self.assertEqual(manifest["stage_and_coverage_correction"]["g0"]["C1_L_upper"], {"numerator": 51, "denominator": 51})
            self.assertEqual(manifest["stage_and_coverage_correction"]["g1"]["C2_MVS"], {"numerator": 50, "denominator": 51})
            self.assertEqual(manifest["stage_and_coverage_correction"]["coverage_correction"]["partial"], {"numerator": 4, "denominator": 50})
            self.assertTrue((output / "fixed_view_manifest_v1.json").is_file())
            self.assertTrue((output / "stage_and_coverage_correction_v1.csv").is_file())
            self.assertEqual(len(list(output.glob("*.png"))), 3)

    def test_existing_nonempty_output_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config, artifact, r3, output = self._fixture(root)
            output.mkdir(parents=True)
            (output / "existing.txt").write_text("do not overwrite", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "absent or empty"):
                render_from_config(config_path=config, repository_root=root / "repo", artifact_root=artifact, r3_root=r3, output_dir=output)

    def test_repeated_render_has_identical_png_and_stage_csv_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config, artifact, r3, first_output = self._fixture(root)
            second_output = root / "output-repeat"
            render_from_config(config_path=config, repository_root=root / "repo", artifact_root=artifact, r3_root=r3, output_dir=first_output)
            render_from_config(config_path=config, repository_root=root / "repo", artifact_root=artifact, r3_root=r3, output_dir=second_output)

            def output_digests(directory: Path) -> dict[str, str]:
                selected = sorted([*directory.glob("*.png"), directory / "stage_and_coverage_correction_v1.csv"])
                self.assertTrue(all(path.is_file() for path in selected))
                return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in selected}

            first = output_digests(first_output)
            second = output_digests(second_output)
            self.assertEqual(set(first), set(second))
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

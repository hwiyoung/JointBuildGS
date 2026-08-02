from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import laspy

from scripts.p2_baselines.c1_c2_feasibility_pilot_v1 import contract


class ContractTests(unittest.TestCase):
    def test_exact_development_scope_and_representatives(self) -> None:
        result = contract.validate_contract()
        self.assertEqual(51, result["building_count"])
        self.assertEqual("712cf0e7e635f049857302f4e5ffea825165d9fb38dd3091d0ab192d5974a68b", result["development_id_set_sha256"])
        self.assertEqual([1, 1, 1, 1, 47], sorted(result["group_sizes"].values()))
        self.assertEqual(5, len(result["representatives"]))
        self.assertEqual(0, result["scientific_payload_bytes_read_or_hashed"])
        config = contract.load_config()["scope"]
        self.assertEqual(2731, config["roster_bytes"])
        self.assertEqual("c9f6412c4878a2cec3be09e465bb7a2be60f4f8329a473bf4acd44679c6afecc", config["roster_sha256"])
        self.assertEqual(8241, config["reference_association_bytes"])
        self.assertEqual("3a3c80b510cbba5f9a714cf8bb55c5e0ad2a80fe8250a313ce5a9a6f4a823628", config["reference_association_sha256"])

    def test_config_prohibits_old_or_raw_inputs_and_all_outcome_splits(self) -> None:
        config = contract.load_config()
        tokens = set(config["inputs"]["prohibited_mount_tokens"])
        self.assertIn("dim_dense.ply", tokens)
        self.assertIn("reference/c1_class26_v1.ply", tokens)
        self.assertIn("validation", tokens)
        self.assertIn("held_out", tokens)
        self.assertFalse(config["scope"]["validation_payload_mount_allowed"])
        self.assertFalse(config["scope"]["held_out_payload_mount_allowed"])
        self.assertFalse(config["c1_materialization"]["r1_reference_cells_used"])
        self.assertFalse(config["association"]["crop_allowed"])
        self.assertFalse(config["association"]["registration_allowed"])
        c2 = config["inputs"]["c2_mvs_class26"]
        self.assertEqual(2951, c2["attestation_checkpoint_bytes"])
        self.assertEqual("b301d3dc7dec2423ff5760c47db4dfef4f62e919b5aac5808a30c82a9330a8f8", c2["attestation_checkpoint_sha256"])

    def test_c2_attestation_checkpoint_is_exactly_bound(self) -> None:
        body = {
            "payload": {
                "derivative": {
                    "path": "/artifacts/JointBuildGS/task/common/mvs_class26_v1.ply",
                    "bytes": 7,
                    "sha256": "a" * 64,
                }
            }
        }
        data = contract.canonical_json_bytes(body)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "checkpoint.json"
            path.write_bytes(data)
            record, observed = contract.resolve_checkpoint_record(
                path,
                "payload.derivative",
                "task/common/mvs_class26_v1.ply",
                expected_checkpoint_bytes=len(data),
                expected_checkpoint_sha256=contract.sha256_bytes(data),
            )
            self.assertEqual(7, record["bytes"])
            self.assertEqual(1, observed["full_read_and_digest_passes"])
            with self.assertRaisesRegex(RuntimeError, "input digest mismatch"):
                contract.resolve_checkpoint_record(
                    path,
                    "payload.derivative",
                    "task/common/mvs_class26_v1.ply",
                    expected_checkpoint_bytes=len(data),
                    expected_checkpoint_sha256="b" * 64,
                )

    def test_c1_materialization_uses_exact_grid_fields_and_thresholds(self) -> None:
        config = copy.deepcopy(contract.load_config())
        config["frame"]["aoi_bbox"] = [0.0, 0.0, 5.0, 5.0]
        config["c1_materialization"]["terrain_filter_windows_cells"] = [3]
        size = 25
        arrays = {
            "min_z": np.zeros(size, dtype=np.float64),
            "max_z": np.zeros(size, dtype=np.float64),
            "count": np.ones(size, dtype=np.uint64),
            "sum_z": np.zeros(size, dtype=np.float64),
            "sum_z2": np.zeros(size, dtype=np.float64),
            "class2_min_z": np.zeros(size, dtype=np.float64),
            "class2_count": np.ones(size, dtype=np.uint64),
            "class6_max_z": np.full(size, -np.inf, dtype=np.float64),
            "class6_count": np.zeros(size, dtype=np.uint64),
        }
        arrays["class6_max_z"][[6, 7, 8]] = [3.0, 4.0, 2.0]
        arrays["class6_count"][[6, 7, 8]] = [3, 2, 3]
        arrays["class2_min_z"][0] = 0.75
        buffer = io.BytesIO()
        np.savez_compressed(buffer, **arrays)
        points, stats = contract.load_c1_grid(buffer.getvalue(), config)
        self.assertEqual(25, stats["ground_points"])
        self.assertEqual(1, stats["building_points"])
        self.assertEqual([(1, 1, 3.0)], [(p.ix, p.iy, p.z) for p in points if p.classification == 6])
        self.assertEqual(0.75, next(p.z for p in points if p.classification == 2 and p.ix == 0 and p.iy == 0))
        self.assertFalse(stats["r1_reference_cells_used"])

    def test_condition_components_and_r_derived_are_id_and_bbox_blind(self) -> None:
        config = copy.deepcopy(contract.load_config())
        config["frame"]["aoi_bbox"] = [0.0, 0.0, 100.0, 100.0]
        config["condition_geometry"]["fixed_tile_anchor"] = [0.0, 0.0]
        points = [
            contract.Point(0.5, 0.5, 0.0, 2, 0, 0),
            contract.Point(1.5, 1.5, 5.0, 6, 1, 1),
            contract.Point(2.5, 1.5, 5.0, 6, 2, 1),
            contract.Point(2.5, 2.5, 5.0, 6, 2, 2),
            contract.Point(1.5, 2.5, 5.0, 6, 1, 2),
        ]
        components, mapping = contract.derive_components("C2_MVS", points, config)
        self.assertEqual(1, len(components))
        self.assertEqual(4, components[0]["point_count"])
        self.assertNotIn("stable_id", components[0])
        self.assertNotIn("bbox", components[0])
        self.assertEqual(4, len(mapping))
        input_bytes, geojson_bytes = contract.component_job("C2_MVS", components[0], points, config)
        self.assertIn(b"condition_class6_component_only", geojson_bytes)
        self.assertNotIn(b"DEBY", geojson_bytes)
        with laspy.open(io.BytesIO(input_bytes), closefd=False) as reader:
            cloud = reader.read()
        self.assertEqual(5, len(cloud.points))
        self.assertEqual({2, 6}, set(int(value) for value in cloud.classification))
        self.assertEqual("1.2", str(cloud.header.version))

    def test_score_association_makes_102_rows_and_can_share_unique_operation(self) -> None:
        config = contract.load_config()
        roster = contract.read_csv(contract.REPO / config["scope"]["roster_path"])
        associations = contract.read_csv(contract.REPO / config["scope"]["reference_association_path"])
        patches = sorted({patch for row in associations for patch in row["reference_patch_ids"].split(";")})
        reference = [
            {"patch_id": patch, "cell_ix": "1", "cell_iy": "1", "top_z": "5", "normal_x": "0", "normal_y": "0", "normal_z": "1"}
            for patch in patches
        ]
        component_maps = {
            "C1_L_upper": {(1, 1): "C1_L_upper_COMP_aaaaaaaaaaaaaaaaaaaa"},
            "C2_MVS": {(1, 1): "C2_MVS_COMP_bbbbbbbbbbbbbbbbbbbb"},
        }
        rows, score_cells = contract.associate_development(roster, associations, reference, component_maps)
        self.assertEqual(102, len(rows))
        self.assertEqual(2, len({row["operation_unit_id"] for row in rows}))
        self.assertGreater(len(score_cells), 51)
        self.assertTrue(all(row["association_role"].startswith("SCORE_IDENTITY_ONLY") for row in rows))

    def test_add_once_and_completed_synthetic_fast_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = contract.AddOnceStore(Path(temporary))
            first = contract.prepare_synthetic(store)
            second = contract.prepare_synthetic(store)
            self.assertEqual(first, second)
            with self.assertRaisesRegex(RuntimeError, "add-once"):
                store.add("smoke/work/input.las", b"replacement")

    def test_strict_lod22_and_provisional_g2_separation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            cityjson = {
                "type": "CityJSON",
                "version": "2.0",
                "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "CityObjects": {
                    "x": {
                        "type": "Building",
                        "geometry": [{
                            "type": "MultiSurface", "lod": "2.2", "boundaries": [[[0, 1, 2]], [[0, 1, 2]], [[0, 1, 2]]],
                            "semantics": {"surfaces": [{"type": "RoofSurface"}, {"type": "WallSurface"}, {"type": "GroundSurface"}], "values": [0, 1, 2]},
                        }],
                    }
                },
            }
            (output / "out.json").write_text(json.dumps(cityjson), encoding="utf-8")
            check = contract.provisional_output_check(output)
            self.assertTrue(check["G0_generated"])
            self.assertIsNone(check["G2_geometry_topology_valid"])
            self.assertEqual("CANONICAL_VALIDATOR_UNAVAILABLE", check["G2_null_reason"])
            cityjson["CityObjects"]["x"]["geometry"][0]["lod"] = "1.1"
            (output / "out.json").write_text(json.dumps(cityjson), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "LoD1.1"):
                contract.provisional_output_check(output)

    def test_schema_keeps_canonical_g2_g3_g4_and_pass_null(self) -> None:
        schema = json.loads((contract.REPO / "configs/p2_baselines/c1_c2_feasibility_pilot_v1/result_schema_v1.json").read_text(encoding="utf-8"))
        props = schema["properties"]
        self.assertEqual("null", props["G2_geometry_topology_valid"]["type"])
        self.assertEqual("CANONICAL_VALIDATOR_UNAVAILABLE", props["G2_null_reason"]["const"])
        for field in ("G3_roof_structure_acceptable", "G4_geometric_accuracy_acceptable", "PASS_usable"):
            self.assertEqual("null", props[field]["type"])

    def test_group_balanced_summary_is_descriptive_only(self) -> None:
        rows = [
            {"group_id": "g_big", "metrics": {"RMSZ_m": 1.0}},
            {"group_id": "g_big", "metrics": {"RMSZ_m": 3.0}},
            {"group_id": "g_small", "metrics": {"RMSZ_m": 10.0}},
        ]
        summary = contract.group_balanced_summary(rows, "RMSZ_m")
        self.assertEqual(6.0, summary["unweighted_group_mean"])
        self.assertIsNone(summary["inferential_statistics"])

    def test_continuous_metric_formulas_and_roof_triangle_extraction(self) -> None:
        triangle = np.asarray([[0.0, 0.0, 5.0], [2.0, 0.0, 5.0], [0.0, 2.0, 5.0]])
        reference = [{"cell_x": "0.5", "cell_y": "0.5", "top_z": "4.0", "normal_x": "0", "normal_y": "0", "normal_z": "1"}]
        metrics = contract.score_continuous(reference, [triangle])
        self.assertEqual(1.0, metrics["reference_vertical_coverage"])
        self.assertEqual(1.0, metrics["RMSZ_m"])
        self.assertEqual(0.0, metrics["RMSXY_m"])
        self.assertEqual(1.0, metrics["surface_distance_rmse_m"])
        self.assertEqual(0.0, metrics["normal_angular_error_median_deg"])
        self.assertIsNone(metrics["roof_plane_completeness"])

    def test_host_wrapper_is_serial_cpu_only_and_has_narrow_mounts(self) -> None:
        script = (contract.REPO / "scripts/p2_baselines/c1_c2_feasibility_pilot_v1/run_pilot_host.sh").read_text(encoding="utf-8")
        self.assertIn("--network none --cpus 2 --memory 8g", script)
        self.assertIn("--jobs 1", script)
        self.assertIn("timeout 600", script)
        self.assertIn('merge-base --is-ancestor "${SOURCE_COMMIT}" "${HEAD_SHA}"', script)
        self.assertIn('"${PACKET_SOURCE_COMMIT}" != "${SOURCE_COMMIT}"', script)
        self.assertNotIn('"${HEAD_SHA}" != "${SOURCE_COMMIT}"', script)
        self.assertEqual(1, script.count("${ARTIFACT_ROOT}:/artifacts/JointBuildGS:ro"))
        self.assertNotIn("validation:", script)
        self.assertNotIn("held_out:", script)
        receipt = script.index("validate_two_host_handoff.py")
        first_scientific_stat = script.index('for exact_input in "${C1_GRID}"')
        task_mkdir = script.index('mkdir -p "${TASK_ROOT}"')
        self.assertLess(receipt, first_scientific_stat)
        self.assertLess(receipt, task_mkdir)

    def test_promote_writes_exact_review_surface_and_is_add_once(self) -> None:
        config = contract.load_config()
        roster = contract.read_csv(contract.REPO / config["scope"]["roster_path"])
        representatives = contract.representative_cases(roster)
        metrics = contract.score_continuous([], [])
        rows = []
        for item in roster:
            for method in contract.CONDITIONS:
                rows.append({
                    "building_id": item["stable_id"], "group_id": item["group_id"], "split": "development",
                    "method_id": method, "reference_provenance": "SELF_REFERENCE_UPPER_BASELINE" if method == "C1_L_upper" else "INDEPENDENT_UAS_SCORE_ONLY",
                    "component_id": None, "operation_unit_id": None, "G0_generated": False, "G1_schema_semantic": None,
                    "G2_internal_screen": None, "G2_geometry_topology_valid": None, "G2_null_reason": "CANONICAL_VALIDATOR_UNAVAILABLE",
                    "G3_roof_structure_acceptable": None, "G4_geometric_accuracy_acceptable": None, "PASS_usable": None,
                    "threshold_null_reason": "THRESHOLD_NOT_FROZEN", "attempt_count": 0, "retry_count": 0,
                    "runtime_seconds": None, "peak_memory_bytes": None, "input_point_count": None, "roofer_input_point_count": None,
                    "output_bytes": 0, "failure_reasons": ["UNASSOCIATED"], "metrics": metrics,
                })
        summaries = [{"method_id": method, **contract.group_balanced_summary(rows, "RMSZ_m")} for method in contract.CONDITIONS]
        cases = [row for row in rows if representatives[row["group_id"]] == row["building_id"]]
        with tempfile.TemporaryDirectory() as external, tempfile.TemporaryDirectory() as repository:
            store = contract.AddOnceStore(Path(external))
            metric_record = store.add("results/building_method_metrics_v1.jsonl", contract.jsonl_bytes(rows))
            summary_record = store.add("results/group_balanced_descriptive_v1.jsonl", contract.jsonl_bytes(summaries))
            case_record = store.add("results/preselected_case_index_v1.jsonl", contract.jsonl_bytes(cases))
            report_record = store.add("results/C1_C2_DEVELOPMENT_REPORT_v1.md", b"compact\n")
            store.add_json("control/finalized_v1.json", {
                "status": "TECHNICAL_RESULTS_COMPLETE_FOR_WORK_HOST_REVIEW", "scientific_verdict": None,
                "run_id": "run", "operation_id": "b" * 64, "metrics": metric_record,
                "group_balanced_descriptive": summary_record, "preselected_cases": case_record, "report": report_record,
                "unique_execution_units": 0, "duplicate_roofer_calculations_prevented": 0,
                "method_summary": {method: {"G0_generated": 0, "G1_provisional_true": 0} for method in contract.CONDITIONS},
            })
            first = contract.promote(store, Path(repository), "a" * 40)
            second = contract.promote(store, Path(repository), "a" * 40)
            self.assertEqual(102, first["result_rows"])
            self.assertTrue(second["fast_path"])
            csv_path = Path(repository) / "docs/experiments/p2/c1_c2_feasibility_pilot_v1/building_method_metrics_v1.csv"
            self.assertEqual(103, len(csv_path.read_text(encoding="utf-8").splitlines()))
            report = (Path(repository) / "docs/experiments/p2/c1_c2_feasibility_pilot_v1/C1_C2_DEVELOPMENT_REPORT_v1.md").read_text(encoding="utf-8")
            self.assertIn("canonical G2", report)
            self.assertIn("scientific_verdict", report)

    def test_retry_quarantines_attempt_one_output_and_records_logs(self) -> None:
        unit_id = "C1_L_upper|C1_L_upper_COMP_aaaaaaaaaaaaaaaaaaaa"
        unit = {
            "operation_unit_id": unit_id, "condition_id": "C1_L_upper",
            "component_id": "C1_L_upper_COMP_aaaaaaaaaaaaaaaaaaaa",
            "work_directory": "operations/C1_L_upper/C1_L_upper_COMP_aaaaaaaaaaaaaaaaaaaa/work",
            "output_directory": "operations/C1_L_upper/C1_L_upper_COMP_aaaaaaaaaaaaaaaaaaaa/work/out",
        }
        with tempfile.TemporaryDirectory() as temporary:
            store = contract.AddOnceStore(Path(temporary))
            units_record = store.add("freeze/execution_units_v1.jsonl", contract.jsonl_bytes([unit]))
            store.add_json("control/scientific_prepared_v1.json", {"status": "PREPARED", "execution_units": units_record})
            first = contract.next_attempt(store, unit_id)
            self.assertEqual(1, first["attempt_number"])
            output = store.path(unit["output_directory"])
            output.mkdir(parents=True)
            (output / "partial.tmp").write_bytes(b"partial")
            work = store.path(unit["work_directory"])
            (work / "roofer.log.json").write_text("{}", encoding="utf-8")
            (work / "runtime.attempt_1.log").write_text("infra fail", encoding="utf-8")
            retry = contract.record_attempt(store, unit_id, 1, 125, 1.0, None)
            self.assertEqual("RETRY_AUTHORIZED_INFRASTRUCTURE_ONLY", retry["status"])
            second = contract.next_attempt(store, unit_id)
            self.assertEqual(2, second["attempt_number"])
            self.assertTrue((work / "out.attempt_01.quarantine/partial.tmp").is_file())
            self.assertTrue((work / "roofer.log.attempt_01.quarantine.json").is_file())
            self.assertTrue(output.is_dir())
            cityjson = {
                "type": "CityJSON", "version": "2.0", "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "CityObjects": {"x": {"type": "Building", "geometry": [{
                    "type": "MultiSurface", "lod": "2.2",
                    "boundaries": [[[0, 1, 2]], [[0, 1, 2]], [[0, 1, 2]]],
                    "semantics": {"surfaces": [{"type": "RoofSurface"}, {"type": "WallSurface"}, {"type": "GroundSurface"}], "values": [0, 1, 2]},
                }]}}
            }
            (output / "result.json").write_text(json.dumps(cityjson), encoding="utf-8")
            (work / "runtime.attempt_2.log").write_text("ok", encoding="utf-8")
            final = contract.record_attempt(store, unit_id, 2, 0, 2.0, 123)
            self.assertEqual("COMPLETE", final["status"])
            self.assertEqual(2, len(final["runtime_logs"]))
            self.assertEqual(1, final["quarantine_state"]["files"])
            self.assertTrue(final["quarantine_state"]["roofer_internal_log_moved"])
            with self.assertRaisesRegex(RuntimeError, "already has final"):
                contract.record_attempt(store, unit_id, 2, 0, 2.0, 123)

    def test_toy_prepare_freezes_geometry_before_score_and_reuses_shared_units(self) -> None:
        config = copy.deepcopy(contract.load_config())
        config["frame"]["aoi_bbox"] = [0.0, 0.0, 10.0, 10.0]
        config["condition_geometry"]["fixed_tile_anchor"] = [0.0, 0.0]
        config["c1_materialization"]["terrain_filter_windows_cells"] = [3]
        size = 100
        arrays = {
            "min_z": np.zeros(size, dtype=np.float64), "max_z": np.zeros(size, dtype=np.float64),
            "count": np.ones(size, dtype=np.uint64), "sum_z": np.zeros(size, dtype=np.float64),
            "sum_z2": np.zeros(size, dtype=np.float64), "class2_min_z": np.zeros(size, dtype=np.float64),
            "class2_count": np.ones(size, dtype=np.uint64), "class6_max_z": np.full(size, -np.inf, dtype=np.float64),
            "class6_count": np.zeros(size, dtype=np.uint64),
        }
        for iy, ix in ((1, 1), (1, 2), (2, 1), (2, 2)):
            flat = iy * 10 + ix
            arrays["class6_max_z"][flat] = 5.0
            arrays["class6_count"][flat] = 3
        grid_buffer = io.BytesIO()
        np.savez_compressed(grid_buffer, **arrays)
        c1_bytes = grid_buffer.getvalue()
        c2_points = [contract.Point(ix + 0.5, iy + 0.5, 5.0, 6, ix, iy) for iy, ix in ((1, 1), (1, 2), (2, 1), (2, 2))]
        c2_points += [contract.Point(ix + 0.5, iy + 0.5, 0.0, 2, ix, iy) for iy, ix in ((0, 0), (0, 3), (3, 0), (3, 3))]
        c2_bytes = contract.ply_bytes(c2_points)
        associations = contract.read_csv(contract.REPO / config["scope"]["reference_association_path"])
        patches = sorted({patch for row in associations for patch in row["reference_patch_ids"].split(";")})
        reference_buffer = io.StringIO(newline="")
        reference_writer = __import__("csv").DictWriter(reference_buffer, fieldnames=["patch_id", "cell_ix", "cell_iy", "cell_x", "cell_y", "top_z", "normal_x", "normal_y", "normal_z"], lineterminator="\n")
        reference_writer.writeheader()
        cells = ((1, 1), (1, 2), (2, 1), (2, 2))
        for index, patch in enumerate(patches):
            ix, iy = cells[index % 4]
            reference_writer.writerow({"patch_id": patch, "cell_ix": ix, "cell_iy": iy, "cell_x": ix + 0.5, "cell_y": iy + 0.5, "top_z": 5, "normal_x": 0, "normal_y": 0, "normal_z": 1})
        reference_bytes = reference_buffer.getvalue().encode()
        patch_bytes = ("patch_id\n" + "".join(f"{patch}\n" for patch in patches)).encode()
        config["inputs"]["c1_grid"].update(bytes=len(c1_bytes), sha256=contract.sha256_bytes(c1_bytes))
        config["inputs"]["c1_reference_cells"].update(bytes=len(reference_bytes), sha256=contract.sha256_bytes(reference_bytes), expected_rows=len(patches))
        config["inputs"]["c1_patch_summary"].update(bytes=len(patch_bytes), sha256=contract.sha256_bytes(patch_bytes), expected_rows=len(patches))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            inputs.mkdir()
            c1_path, c2_path = inputs / "c1.npz", inputs / "c2.ply"
            ref_path, patch_path, checkpoint_path = inputs / "reference.csv", inputs / "patch.csv", inputs / "checkpoint.json"
            c1_path.write_bytes(c1_bytes); c2_path.write_bytes(c2_bytes)
            ref_path.write_bytes(reference_bytes); patch_path.write_bytes(patch_bytes)
            checkpoint_bytes = json.dumps({"payload": {"derivative": {
                "path": "/artifacts/JointBuildGS/" + config["inputs"]["c2_mvs_class26"]["artifact_relative_path"],
                "bytes": len(c2_bytes), "sha256": contract.sha256_bytes(c2_bytes),
            }}}).encode("utf-8")
            checkpoint_path.write_bytes(checkpoint_bytes)
            config["inputs"]["c2_mvs_class26"].update(
                attestation_checkpoint_bytes=len(checkpoint_bytes),
                attestation_checkpoint_sha256=contract.sha256_bytes(checkpoint_bytes),
            )
            store = contract.AddOnceStore(root / "output")
            store.add_json("control/synthetic_smoke_pass_v1.json", {"status": "PASS"})
            with mock.patch.object(contract, "load_config", return_value=config):
                prepared = contract.prepare_scientific(
                    store, c1_grid_path=c1_path, c2_ply_path=c2_path, c2_checkpoint_path=checkpoint_path,
                    reference_cells_path=ref_path, patch_summary_path=patch_path,
                    source_commit="a" * 40, run_id="toy-run",
                )
                reused = contract.prepare_scientific(
                    store, c1_grid_path=Path("missing"), c2_ply_path=Path("missing"), c2_checkpoint_path=Path("missing"),
                    reference_cells_path=Path("missing"), patch_summary_path=Path("missing"),
                    source_commit="a" * 40, run_id="toy-run",
                )
            self.assertEqual(102, prepared["result_rows"])
            self.assertEqual(2, prepared["unique_execution_units"])
            self.assertEqual(100, prepared["duplicate_roofer_calculations_prevented"])
            self.assertTrue(reused["fast_path"])
            checkpoint = json.loads(store.path("checkpoints/120-condition_components_and_r_derived_frozen.json").read_bytes())
            self.assertFalse(checkpoint["reference_score_cells_opened_before_checkpoint"])

    def test_shared_operation_las_is_verified_once_then_count_is_reused(self) -> None:
        config = copy.deepcopy(contract.load_config())
        points = [
            contract.Point(0.5, 0.5, 0.0, 2, 0, 0),
            contract.Point(1.5, 1.5, 5.0, 6, 1, 1),
            contract.Point(2.5, 1.5, 5.0, 6, 2, 1),
            contract.Point(1.5, 2.5, 5.0, 6, 1, 2),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            class CountingStore(contract.AddOnceStore):
                reads = 0
                def read_verified(self, record):  # type: ignore[no-untyped-def]
                    self.reads += 1
                    return super().read_verified(record)
            store = CountingStore(Path(temporary))
            record = store.add("operations/shared/work/input.las", contract.las_bytes(points, config))
            units = {"shared": {"input": record}}
            counts = contract.roofer_point_counts(store, units)
            simulated_102_rows = [counts["shared"] for _ in range(102)]
            self.assertEqual([4] * 102, simulated_102_rows)
            self.assertEqual(1, store.reads)


if __name__ == "__main__":
    unittest.main()

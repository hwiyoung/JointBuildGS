from __future__ import annotations

import copy
import hashlib
import io
import json
import subprocess
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
        self.assertEqual(
            {
                "GROUP_32a743e7f900e7ae": "DEBY_LOD2_4959327",
                "GROUP_37b5107f054e56e8": "DEBY_LOD2_4906981",
                "GROUP_660281d563f14018": "DEBY_LOD2_4959461",
                "GROUP_6e1c6ddc7a70ba88": "DEBY_LOD2_4906982",
                "GROUP_a47a79580ecbedd1": "DEBY_LOD2_4959314",
            },
            result["representatives"],
        )
        self.assertEqual(21714, result["development_score_cell_rows"])
        self.assertEqual("1dca79dcc411c4904eb491a5b8aaa03890984e52", result["frozen_eligibility_blob"])
        self.assertEqual("f6db7b8accdbd7b57b4a221c441acfc5589fb592", result["frozen_split_blob"])
        self.assertEqual(0, result["scientific_payload_bytes_read_or_hashed"])
        config = contract.load_config()["scope"]
        self.assertEqual(2731, config["roster_bytes"])
        self.assertEqual("c9f6412c4878a2cec3be09e465bb7a2be60f4f8329a473bf4acd44679c6afecc", config["roster_sha256"])
        self.assertEqual(21714, config["development_score_cell_rows"])
        self.assertEqual(12014, config["development_score_scope_canonical_lf_bytes"])
        self.assertEqual(
            "MIN_SHA256(representative_selection_task_id|group_id|stable_id)_BEFORE_OUTCOME_ACCESS",
            contract.load_config()["representative_case_rule"],
        )

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
        self.assertFalse(config["c1_materialization"]["source_classification_fields_usable"])
        self.assertFalse(config["association"]["crop_allowed"])
        self.assertFalse(config["association"]["registration_allowed"])
        c2 = config["inputs"]["c2_mvs_class26"]
        self.assertEqual(2951, c2["attestation_checkpoint_bytes"])
        self.assertEqual("b301d3dc7dec2423ff5760c47db4dfef4f62e919b5aac5808a30c82a9330a8f8", c2["attestation_checkpoint_sha256"])
        c1 = config["inputs"]["c1_grid"]
        self.assertEqual(3140, c1["attestation_checkpoint_bytes"])
        self.assertEqual({"0": 177981904}, c1["raw_class_counts"])

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

    def test_c1_checkpoint_binds_generic_grid_and_raw_zero_classes(self) -> None:
        spec = copy.deepcopy(contract.load_config()["inputs"]["c1_grid"])
        body = {
            "stage": "c1_reference_frozen_pre_c5", "status": "COMPLETED_FSYNC",
            "payload": {
                "grid": {"path": "/artifacts/JointBuildGS/" + spec["artifact_relative_path"], "bytes": spec["bytes"], "sha256": spec["sha256"]},
                "input": {"point_count": 177981904, "raw_class_counts": {"0": 177981904}},
            },
        }
        data = contract.canonical_json_bytes(body)
        spec.update(attestation_checkpoint_bytes=len(data), attestation_checkpoint_sha256=contract.sha256_bytes(data))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "050.json"
            path.write_bytes(data)
            record, observed = contract.resolve_c1_grid_checkpoint(path, spec)
            self.assertEqual(spec["sha256"], record["sha256"])
            self.assertEqual(1, observed["full_read_and_digest_passes"])
            body["payload"]["input"]["raw_class_counts"] = {"2": 1}
            bad = contract.canonical_json_bytes(body)
            path.write_bytes(bad)
            spec.update(attestation_checkpoint_bytes=len(bad), attestation_checkpoint_sha256=contract.sha256_bytes(bad))
            with self.assertRaisesRegex(RuntimeError, "class-count"):
                contract.resolve_c1_grid_checkpoint(path, spec)

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
        arrays["max_z"][[6, 7, 8]] = [3.0, 4.0, 2.0]
        arrays["count"][[6, 7, 8]] = [3, 2, 3]
        arrays["min_z"][0] = 0.75
        arrays["class6_max_z"][10] = 99.0
        arrays["class6_count"][10] = 99
        buffer = io.BytesIO()
        np.savez_compressed(buffer, **arrays)
        points, stats = contract.load_c1_grid(buffer.getvalue(), config)
        self.assertEqual(25, stats["ground_points"])
        self.assertEqual(1, stats["building_points"])
        self.assertEqual([(1, 1, 3.0)], [(p.ix, p.iy, p.z) for p in points if p.classification == 6])
        self.assertEqual(0.75, next(p.z for p in points if p.classification == 2 and p.ix == 0 and p.iy == 0))
        self.assertFalse(stats["class_specific_fields_used"])
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
        score_scope = contract.read_csv(contract.REPO / config["scope"]["development_score_scope_path"])
        patch_by_id = {row["stable_id"]: row["reference_patch_ids"].split(";")[0] for row in score_scope}
        reference = [{
            "stable_id": row["stable_id"], "group_id": row["group_id"], "patch_id": patch_by_id[row["stable_id"]],
            "flat_index": str(index), "cell_ix": "1", "cell_iy": "1", "top_z": "5",
            "normal_x": "0", "normal_y": "0", "normal_z": "1",
        } for index, row in enumerate(roster)]
        component_maps = {
            "C1_L_upper": {(1, 1): "C1_L_upper_COMP_aaaaaaaaaaaaaaaaaaaa"},
            "C2_MVS": {(1, 1): "C2_MVS_COMP_bbbbbbbbbbbbbbbbbbbb"},
        }
        rows, score_cells = contract.associate_development(roster, reference, component_maps)
        self.assertEqual(102, len(rows))
        self.assertEqual(2, len({row["operation_unit_id"] for row in rows}))
        self.assertEqual(51, len(score_cells))
        self.assertTrue(all(row["association_role"].startswith("SCORE_IDENTITY_ONLY") for row in rows))

    def test_score_projection_is_one_pass_exact_and_inclusive(self) -> None:
        content = (
            "patch_id,flat_index,cell_ix,cell_iy,cell_x,cell_y,top_z,normal_x,normal_y,normal_z\n"
            "UASPATCH_00000000000000000001,10,1,2,5.0,6.0,7.0,0,0,1\n"
            "UASPATCH_ffffffffffffffffffff,11,9,9,99.0,99.0,7.0,0,0,1\n"
        ).encode()
        scope = [{
            "stable_id": "DEBY_LOD2_1", "group_id": "GROUP_0000000000000001",
            "bbox_min_x": "5.0", "bbox_min_y": "6.0", "bbox_max_x": "5.0", "bbox_max_y": "6.0",
            "reference_patch_ids": "UASPATCH_00000000000000000001", "expected_score_cells": "1",
        }]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "reference.csv"
            path.write_bytes(content)
            rows, record = contract.project_development_score_cells(path, {
                "bytes": len(content), "sha256": contract.sha256_bytes(content), "expected_rows": 2,
            }, scope)
        self.assertEqual(1, len(rows))
        self.assertEqual("10", rows[0]["flat_index"])
        self.assertEqual(1, record["full_read_and_digest_passes"])
        self.assertEqual(0, record["non_development_rows_retained_scored_or_promoted"])

    def test_add_once_and_completed_synthetic_fast_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = contract.AddOnceStore(Path(temporary))
            first = contract.prepare_synthetic(store)
            second = contract.prepare_synthetic(store)
            self.assertEqual(first, second)
            action = contract.next_synthetic_action(store)
            self.assertEqual("RUN", action["action"])
            output = store.path("smoke/work/out")
            output.mkdir()
            geometry = {
                "type": "MultiSurface", "lod": "2.2",
                "boundaries": [[[0, 1, 2]], [[0, 1, 2]], [[0, 1, 2]]],
                "semantics": {
                    "surfaces": [{"type": "RoofSurface"}, {"type": "WallSurface"}, {"type": "GroundSurface"}],
                    "values": [0, 1, 2],
                },
            }
            cityjson = {
                "type": "CityJSON", "version": "2.0",
                "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "CityObjects": {
                    f"synthetic-{index}": {"type": "Building", "geometry": [copy.deepcopy(geometry)]}
                    for index in range(5)
                },
            }
            (output / "result.json").write_text(json.dumps(cityjson), encoding="utf-8")
            store.path("smoke/work/runtime.log").write_text("ok", encoding="utf-8")
            passed = contract.verify_synthetic(store, output, 0)
            self.assertEqual("PASS", passed["status"])
            before = sorted(path.relative_to(store.root).as_posix() for path in store.root.rglob("*") if path.is_file())
            skipped = contract.next_synthetic_action(store)
            after = sorted(path.relative_to(store.root).as_posix() for path in store.root.rglob("*") if path.is_file())
            self.assertEqual("SKIP_COMPLETED", skipped["action"])
            self.assertEqual(before, after)
            with self.assertRaisesRegex(RuntimeError, "add-once"):
                store.add("smoke/work/input.las", b"replacement")

        with tempfile.TemporaryDirectory() as temporary:
            partial = contract.AddOnceStore(Path(temporary))
            contract.prepare_synthetic(partial)
            contract.next_synthetic_action(partial)
            partial.path("smoke/work/out").mkdir()
            partial.path("smoke/work/runtime.log").write_text("infra failure", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "exited 125"):
                contract.verify_synthetic(partial, partial.path("smoke/work/out"), 125)
            failed = json.loads(partial.path("smoke/attempt_01.result.json").read_bytes())
            self.assertEqual("FAILED", failed["status"])
            self.assertIsNotNone(failed["runtime_log"])
            with self.assertRaisesRegex(RuntimeError, "partial or failed"):
                contract.next_synthetic_action(partial)

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
            self.assertTrue(check["G1_schema_semantic"])
            self.assertTrue(check["geometry_ring_diagnostic"])
            self.assertIsNone(check["G2_geometry_topology_valid"])
            self.assertEqual("CANONICAL_VALIDATOR_UNAVAILABLE", check["G2_null_reason"])
            cityjson["CityObjects"]["x"]["geometry"][0]["boundaries"][0][0][0] = 99
            (output / "out.json").write_text(json.dumps(cityjson), encoding="utf-8")
            invalid = contract.provisional_output_check(output)
            self.assertFalse(invalid["G1_schema_semantic"])
            self.assertFalse(invalid["geometry_ring_diagnostic"])
            self.assertIn("BOUNDARY_INDEX_OR_SHAPE_INVALID", invalid["G1_failure_reasons"])
            cityjson["CityObjects"]["x"]["geometry"][0]["boundaries"][0][0][0] = 0
            cityjson["CityObjects"]["x"]["geometry"][0]["lod"] = "1.1"
            (output / "out.json").write_text(json.dumps(cityjson), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "LoD1.1"):
                contract.provisional_output_check(output)

    def test_schema_keeps_canonical_g2_g3_g4_and_pass_null(self) -> None:
        config = contract.load_config()
        schema = json.loads((contract.REPO / "configs/p2_baselines/c1_c2_feasibility_pilot_v1/result_schema_v1.json").read_text(encoding="utf-8"))
        props = schema["properties"]
        self.assertNotIn("G2_internal_screen", props)
        self.assertIn("geometry_ring_diagnostic", props)
        self.assertEqual("null", props["G2_geometry_topology_valid"]["type"])
        self.assertEqual("CANONICAL_VALIDATOR_UNAVAILABLE", props["G2_null_reason"]["const"])
        for field in ("G3_roof_structure_acceptable", "G4_geometric_accuracy_acceptable", "PASS_usable"):
            self.assertEqual("null", props[field]["type"])
        row = {
            "building_id": "DEBY_LOD2_1", "group_id": "GROUP_0000000000000001", "split": "development",
            "method_id": "C2_MVS", "run_id": "run", "operation_id": "a" * 64,
            "criterion_version": config["result"]["criterion_version"], "reference_provenance": "INDEPENDENT_UAS_SCORE_ONLY",
            "component_id": None, "operation_unit_id": None, "G0_generated": False,
            "G1_schema_semantic": None, "G1_check_class": "INTERNAL_CITYJSON_BOUNDARY_SEMANTICS_PARENT_CHILD_VALIDATION",
            "G1_failure_reasons": ["NO_EXECUTED_CITYJSON_OUTPUT"], "geometry_ring_diagnostic": None,
            "geometry_ring_diagnostic_class": "DIAGNOSTIC_RING_INDEX_SANITY_NOT_G2_NOT_VAL3DITY",
            "G2_geometry_topology_valid": None, "G2_null_reason": "CANONICAL_VALIDATOR_UNAVAILABLE",
            "G3_roof_structure_acceptable": None, "G4_geometric_accuracy_acceptable": None, "PASS_usable": None,
            "threshold_null_reason": "THRESHOLD_NOT_FROZEN", "attempt_count": 0, "retry_count": 0,
            "runtime_seconds": None, "peak_memory_bytes": None, "peak_memory_unavailable_reason": "NO_ROOFER_EXECUTION",
            "input_point_count": None, "roofer_input_point_count": None, "output_bytes": 0,
            "failure_reasons": ["UNASSOCIATED_CONDITION_COMPONENT"], "metrics": contract.score_continuous([], []),
            "scientific_verdict": None,
        }
        result = contract.validate_result_rows([row], config)
        self.assertEqual(1, result["validated_rows"])

    def test_group_balanced_summary_is_descriptive_only(self) -> None:
        rows = [
            {"group_id": "g_big", "metrics": {"RMSZ_m": 1.0}},
            {"group_id": "g_big", "metrics": {"RMSZ_m": 3.0}},
            {"group_id": "g2", "metrics": {"RMSZ_m": 4.0}},
            {"group_id": "g3", "metrics": {"RMSZ_m": 6.0}},
            {"group_id": "g4", "metrics": {"RMSZ_m": 8.0}},
            {"group_id": "g5", "metrics": {"RMSZ_m": 10.0}},
        ]
        sizes = {"g_big": 2, "g2": 1, "g3": 1, "g4": 1, "g5": 1}
        summary = contract.group_balanced_summary(rows, "RMSZ_m", sizes)
        self.assertEqual(6.0, summary["unweighted_group_mean"])
        self.assertEqual(5, len(summary["groups"]))
        self.assertTrue(summary["all_five_groups_have_value"])
        self.assertIsNone(summary["inferential_statistics"])
        rows[-1]["metrics"]["RMSZ_m"] = None
        missing = contract.group_balanced_summary(rows, "RMSZ_m", sizes)
        self.assertIsNone(missing["unweighted_group_mean"])
        self.assertEqual(4, missing["groups_with_value"])

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
        self.assertIn("next-synthetic", script)
        self.assertIn("remaining_cap_seconds", script)
        self.assertIn('timeout "${attempt_timeout}" docker run', script)
        self.assertIn("HARD_CAP_SECONDS=43200", script)
        self.assertIn('merge-base --is-ancestor "${SOURCE_COMMIT}" "${HEAD_SHA}"', script)
        self.assertIn('"${PACKET_SOURCE_COMMIT}" != "${SOURCE_COMMIT}"', script)
        self.assertNotIn('"${HEAD_SHA}" != "${SOURCE_COMMIT}"', script)
        self.assertEqual(0, script.count("${ARTIFACT_ROOT}:/artifacts/JointBuildGS:ro"))
        self.assertNotIn("--artifact-root /artifacts/JointBuildGS", script)
        self.assertNotIn("sha256sum", script)
        self.assertIn("--entrypoint /opt/conda/bin/python", script)
        self.assertIn("parse_machine_decision.awk", script)
        self.assertIn('p["artifacts"]["attestation_reuse"]==c["accepted_attestation_reuse"]', script)
        self.assertIn("ambiguous synthetic machine decision channel", script)
        self.assertIn("ambiguous scientific machine decision channel", script)
        self.assertIn("c1_c2_feasibility_pilot_recovery_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-v1", script)
        self.assertNotIn('TASK_REL="phase-payloads/p2-baselines/c1_c2_feasibility_pilot_v1/P2-C1-C2-FEASIBILITY-PILOT-v1"', script)
        self.assertIn("050-c1_reference_frozen_pre_c5.json", script)
        self.assertNotIn("PATCH_SUMMARY", script)
        self.assertIn("ROOFER_IMAGE_GNU_TIME_UNAVAILABLE_VERIFIED_IMMUTABLE_IMAGE", script)
        self.assertIn("--accepted-commit \"${HEAD_SHA}\"", script)
        self.assertNotIn("validation:", script)
        self.assertNotIn("held_out:", script)
        receipt = script.index("validate_two_host_handoff.py")
        first_scientific_stat = script.index('for exact_input in "${C1_GRID}"')
        task_mkdir = script.index('mkdir -p "${TASK_ROOT}"')
        self.assertLess(receipt, first_scientific_stat)
        self.assertLess(receipt, task_mkdir)

    def test_machine_channel_ignores_container_banner_and_is_exact(self) -> None:
        parser = contract.REPO / "scripts/p2_baselines/c1_c2_feasibility_pilot_v1/parse_machine_decision.awk"

        def parse(observed: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["awk", "-f", str(parser)], input=observed,
                capture_output=True, text=True, check=False,
            )

        banner = "==========\n== CUDA ==\nimmutable startup text\n"
        passed = parse(banner + "JBGS_MACHINE_DECISION_V1\tRUN\t1\n")
        self.assertEqual(0, passed.returncode)
        self.assertEqual("RUN\n1\n", passed.stdout)
        for invalid in (
            banner,
            banner + "JBGS_MACHINE_DECISION_V1\tRUN\t1\nJBGS_MACHINE_DECISION_V1\tRUN\t1\n",
            banner + "JBGS_MACHINE_DECISION_V1\tRUN\n",
            banner + "JBGS_MACHINE_DECISION_V1\tTUNE\t1\n",
            banner + "JBGS_MACHINE_DECISION_V1\tRUN\t3\n",
            banner + "JBGS_MACHINE_DECISION_V1\tSKIP_COMPLETED\t1\n",
        ):
            self.assertNotEqual(0, parse(invalid).returncode)
        self.assertEqual("P2-C1-C2-FEASIBILITY-PILOT-v1", contract.REPRESENTATIVE_SELECTION_TASK_ID)
        self.assertEqual(
            "P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-v1",
            contract.load_config()["task_id"],
        )

    def test_recovery_packet_binds_immutable_git_receipt_blob_not_checkout_eol(self) -> None:
        source_commit = "896fe284bc4d496e6e9c79720f4e75396a41d0b2"
        source_path = (
            "artifacts/manifests/handoffs/"
            "P2-W2C-C1-C2-FEASIBILITY-PILOT-v1/300-closed.json"
        )
        source = subprocess.check_output(
            [
                "git", "-c", f"safe.directory={contract.REPO}",
                "-C", str(contract.REPO), "show", f"{source_commit}:{source_path}",
            ]
        )
        expected = "705348ecde9d139254bdd24e59ed02312d5321c20f802649f1ce4ca19f5b9bda"
        self.assertEqual(expected, hashlib.sha256(source).hexdigest())
        source_payload = json.loads(source)
        identities = sorted(
            (
                {key: record[key] for key in ("uri", "bytes", "sha256")}
                for record in source_payload["artifacts"]["records"]
            ),
            key=lambda item: item["uri"],
        )
        identity_sha = hashlib.sha256(
            (json.dumps(identities, sort_keys=True, separators=(",", ":")) + "\n").encode()
        ).hexdigest()
        expected_identity = "f63d5d4405157615d807d6babd4a9bf74a16ab13818193945ed9bbfc02532db3"
        self.assertEqual(expected_identity, identity_sha)
        self.assertEqual(
            {
                "source_handoff_id": "P2-W2C-C1-C2-FEASIBILITY-PILOT-v1",
                "source_task_id": "P2-C1-C2-FEASIBILITY-PILOT-v1",
                "source_receipt_path": source_path,
                "source_receipt_commit": source_commit,
                "source_receipt_sha256": expected,
                "record_identity_sha256": expected_identity,
            },
            contract.load_config()["accepted_attestation_reuse"],
        )
        packet = (
            contract.REPO / "docs/handoffs/P2_W2C_C1_C2_FEASIBILITY_PILOT_RECOVERY_v1.md"
        ).read_text(encoding="utf-8")
        self.assertIn(expected, packet)
        self.assertIn(expected_identity, packet)

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
                    "G1_failure_reasons": ["NO_EXECUTED_CITYJSON_OUTPUT"], "geometry_ring_diagnostic": None,
                    "G2_geometry_topology_valid": None, "G2_null_reason": "CANONICAL_VALIDATOR_UNAVAILABLE",
                    "G3_roof_structure_acceptable": None, "G4_geometric_accuracy_acceptable": None, "PASS_usable": None,
                    "threshold_null_reason": "THRESHOLD_NOT_FROZEN", "attempt_count": 0, "retry_count": 0,
                    "runtime_seconds": None, "peak_memory_bytes": None, "peak_memory_unavailable_reason": "NO_ROOFER_EXECUTION",
                    "input_point_count": None, "roofer_input_point_count": None,
                    "output_bytes": 0, "failure_reasons": ["UNASSOCIATED"], "metrics": metrics,
                })
        summaries = [{"method_id": method, **contract.group_balanced_summary(rows, "RMSZ_m")} for method in contract.CONDITIONS]
        technical = contract.condition_group_technical_summary(rows, config["scope"]["group_sizes"])
        cases = [row for row in rows if representatives[row["group_id"]] == row["building_id"]]
        with tempfile.TemporaryDirectory() as external, tempfile.TemporaryDirectory() as repository:
            subprocess.run(["git", "init"], cwd=repository, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "JointBuildGS Test"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "--allow-empty", "-m", "accepted"], cwd=repository, check=True, capture_output=True)
            promotion_parent = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True,
            ).stdout.strip()
            store = contract.AddOnceStore(Path(external))
            metric_record = store.add("results/building_method_metrics_v1.jsonl", contract.jsonl_bytes(rows))
            summary_record = store.add("results/group_balanced_descriptive_v1.jsonl", contract.jsonl_bytes(summaries))
            technical_record = store.add("results/condition_group_technical_summary_v1.jsonl", contract.jsonl_bytes(technical))
            input_definition_record = store.add(
                "results/development_input_definition_v1.csv",
                contract.canonical_lf_bytes(contract.REPO / config["scope"]["development_score_scope_path"]),
            )
            case_record = store.add("results/preselected_case_index_v1.jsonl", contract.jsonl_bytes(cases))
            report_record = store.add("results/C1_C2_DEVELOPMENT_REPORT_v1.md", b"canonical G2\nscientific_verdict\n")
            store.add_json("control/finalized_v1.json", {
                "status": "TECHNICAL_RESULTS_COMPLETE_FOR_WORK_HOST_REVIEW", "scientific_verdict": None,
                "run_id": "run", "operation_id": "b" * 64, "metrics": metric_record,
                "group_balanced_descriptive": summary_record, "condition_group_technical_summary": technical_record,
                "development_input_definition": input_definition_record,
                "preselected_cases": case_record, "report": report_record,
                "unique_execution_units": 0, "duplicate_roofer_calculations_prevented": 0,
                "method_summary": {method: {"G0_generated": 0, "G1_provisional_true": 0} for method in contract.CONDITIONS},
                "execution_authority": {"handoff_id": "test", "accepted_commit": promotion_parent}, "tool_records": {}, "input_records": {}, "output_records": {},
                "result_schema_validation": {"validated_rows": 102},
                "qualitative_fixed_view": {"status": "NOT_RENDERED", "reason": "TEST"},
            })
            with self.assertRaisesRegex(RuntimeError, "exact clean accepted"):
                contract.promote(store, Path(repository), "a" * 40)
            first = contract.promote(store, Path(repository), promotion_parent)
            second = contract.promote(store, Path(repository), promotion_parent)
            self.assertEqual(102, first["result_rows"])
            self.assertTrue(second["fast_path"])
            csv_path = Path(repository) / "docs/experiments/p2/c1_c2_feasibility_pilot_recovery_v1/building_method_metrics_v1.csv"
            self.assertEqual(103, len(csv_path.read_text(encoding="utf-8").splitlines()))
            input_definition_path = Path(repository) / "docs/experiments/p2/c1_c2_feasibility_pilot_recovery_v1/development_input_definition_v1.csv"
            self.assertEqual(52, len(input_definition_path.read_text(encoding="utf-8").splitlines()))
            report = (Path(repository) / "docs/experiments/p2/c1_c2_feasibility_pilot_recovery_v1/C1_C2_DEVELOPMENT_REPORT_v1.md").read_text(encoding="utf-8")
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
            retry = contract.record_attempt(store, unit_id, 1, 125, 1.0, None, "ROOFER_IMAGE_GNU_TIME_UNAVAILABLE")
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
            final = contract.record_attempt(store, unit_id, 2, 0, 2.0, 123, None)
            self.assertEqual("COMPLETE", final["status"])
            self.assertEqual(2, len(final["runtime_logs"]))
            self.assertEqual([1.0, 2.0], final["attempt_runtime_seconds"])
            self.assertEqual(3.0, final["runtime_seconds"])
            self.assertEqual(1, final["quarantine_state"]["files"])
            self.assertTrue(final["quarantine_state"]["roofer_internal_log_moved"])
            with self.assertRaisesRegex(RuntimeError, "already has final"):
                contract.record_attempt(store, unit_id, 2, 0, 2.0, 123, None)

    def test_attempt_two_blocks_before_quarantine_without_retry_authorization(self) -> None:
        unit_id = "C1_L_upper|C1_L_upper_COMP_aaaaaaaaaaaaaaaaaaaa"
        unit = {
            "operation_unit_id": unit_id, "condition_id": "C1_L_upper",
            "component_id": "C1_L_upper_COMP_aaaaaaaaaaaaaaaaaaaa",
            "work_directory": "operations/C1/work", "output_directory": "operations/C1/work/out",
        }
        with tempfile.TemporaryDirectory() as temporary:
            store = contract.AddOnceStore(Path(temporary))
            units_record = store.add("freeze/execution_units_v1.jsonl", contract.jsonl_bytes([unit]))
            store.add_json("control/scientific_prepared_v1.json", {"status": "PREPARED", "execution_units": units_record})
            contract.next_attempt(store, unit_id)
            output = store.path(unit["output_directory"])
            output.mkdir(parents=True)
            (output / "must-remain.txt").write_text("preserve", encoding="utf-8")
            store.add_json(f"operation_records/{contract._unit_slug(unit_id)}/attempt_01.result.json", {
                "status": "TERMINAL_ATTEMPT_RESULT", "attempt_number": 1, "exit_code": 125,
            })
            with self.assertRaisesRegex(RuntimeError, "not explicitly retry-authorized"):
                contract.next_attempt(store, unit_id)
            self.assertTrue((output / "must-remain.txt").is_file())

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
            arrays["max_z"][flat] = 5.0
            arrays["count"][flat] = 3
        grid_buffer = io.BytesIO()
        np.savez_compressed(grid_buffer, **arrays)
        c1_bytes = grid_buffer.getvalue()
        c2_points = [contract.Point(ix + 0.5, iy + 0.5, 5.0, 6, ix, iy) for iy, ix in ((1, 1), (1, 2), (2, 1), (2, 2))]
        c2_points += [contract.Point(ix + 0.5, iy + 0.5, 0.0, 2, ix, iy) for iy, ix in ((0, 0), (0, 3), (3, 0), (3, 3))]
        c2_bytes = contract.ply_bytes(c2_points)
        roster = contract.read_csv(contract.REPO / config["scope"]["roster_path"])
        score_scope = [{
            "stable_id": row["stable_id"], "group_id": row["group_id"],
            "bbox_min_x": "0.0", "bbox_min_y": "0.0", "bbox_max_x": "10.0", "bbox_max_y": "10.0",
            "reference_patch_ids": f"UASPATCH_{index:020x}", "expected_score_cells": "1",
        } for index, row in enumerate(roster, start=1)]
        reference_buffer = io.StringIO(newline="")
        reference_writer = __import__("csv").DictWriter(reference_buffer, fieldnames=["patch_id", "flat_index", "cell_ix", "cell_iy", "cell_x", "cell_y", "top_z", "normal_x", "normal_y", "normal_z"], lineterminator="\n")
        reference_writer.writeheader()
        cells = ((1, 1), (1, 2), (2, 1), (2, 2))
        for index, scope in enumerate(score_scope):
            ix, iy = cells[index % 4]
            reference_writer.writerow({"patch_id": scope["reference_patch_ids"], "flat_index": index, "cell_ix": ix, "cell_iy": iy, "cell_x": ix + 0.5, "cell_y": iy + 0.5, "top_z": 5, "normal_x": 0, "normal_y": 0, "normal_z": 1})
        reference_bytes = reference_buffer.getvalue().encode()
        config["inputs"]["c1_grid"].update(bytes=len(c1_bytes), sha256=contract.sha256_bytes(c1_bytes), raw_point_count=100, raw_class_counts={"0": 100})
        config["inputs"]["reference_candidate_cells"].update(bytes=len(reference_bytes), sha256=contract.sha256_bytes(reference_bytes), expected_rows=51)
        config["scope"]["development_score_cell_rows"] = 51
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            inputs.mkdir()
            c1_path, c2_path = inputs / "c1.npz", inputs / "c2.ply"
            ref_path, c1_checkpoint_path, c2_checkpoint_path = inputs / "reference.csv", inputs / "c1-checkpoint.json", inputs / "c2-checkpoint.json"
            c1_path.write_bytes(c1_bytes); c2_path.write_bytes(c2_bytes)
            ref_path.write_bytes(reference_bytes)
            c1_checkpoint_bytes = contract.canonical_json_bytes({
                "stage": "c1_reference_frozen_pre_c5", "status": "COMPLETED_FSYNC",
                "payload": {
                    "grid": {"path": "/artifacts/JointBuildGS/" + config["inputs"]["c1_grid"]["artifact_relative_path"], "bytes": len(c1_bytes), "sha256": contract.sha256_bytes(c1_bytes)},
                    "input": {"point_count": 100, "raw_class_counts": {"0": 100}},
                },
            })
            c1_checkpoint_path.write_bytes(c1_checkpoint_bytes)
            config["inputs"]["c1_grid"].update(attestation_checkpoint_bytes=len(c1_checkpoint_bytes), attestation_checkpoint_sha256=contract.sha256_bytes(c1_checkpoint_bytes))
            c2_checkpoint_bytes = json.dumps({"payload": {"derivative": {
                "path": "/artifacts/JointBuildGS/" + config["inputs"]["c2_mvs_class26"]["artifact_relative_path"],
                "bytes": len(c2_bytes), "sha256": contract.sha256_bytes(c2_bytes),
            }}}).encode("utf-8")
            c2_checkpoint_path.write_bytes(c2_checkpoint_bytes)
            config["inputs"]["c2_mvs_class26"].update(
                bytes=len(c2_bytes), sha256=contract.sha256_bytes(c2_bytes),
                attestation_checkpoint_bytes=len(c2_checkpoint_bytes),
                attestation_checkpoint_sha256=contract.sha256_bytes(c2_checkpoint_bytes),
            )
            receipt_path = inputs / "100-accepted.json"
            image_id = "sha256:" + "c" * 64
            receipt_path.write_text(json.dumps({
                "handoff_id": config["handoff_id"], "state": "accepted", "direction": "work_to_experiment",
                "verification": {"docker_image_digest": image_id},
            }), encoding="utf-8")
            store = contract.AddOnceStore(root / "output")
            store.add_json("control/synthetic_smoke_pass_v1.json", {"status": "PASS"})
            validation = {
                "development_id_set_sha256": config["scope"]["development_id_set_sha256"],
                "representatives": contract.representative_cases(roster),
            }
            with mock.patch.object(contract, "load_config", return_value=config), \
                 mock.patch.object(contract, "validate_contract", return_value=validation), \
                 mock.patch.object(contract, "read_csv", side_effect=[roster, score_scope]):
                prepared = contract.prepare_scientific(
                    store, c1_grid_path=c1_path, c1_checkpoint_path=c1_checkpoint_path,
                    c2_ply_path=c2_path, c2_checkpoint_path=c2_checkpoint_path, reference_cells_path=ref_path,
                    source_commit="a" * 40, run_id="toy-run", handoff_id=config["handoff_id"],
                    accepted_receipt_path=receipt_path, accepted_commit="b" * 40,
                    project_image_id=image_id, artifact_root_token="artifact://JointBuildGS",
                )
                reused = contract.prepare_scientific(
                    store, c1_grid_path=Path("missing"), c1_checkpoint_path=Path("missing"),
                    c2_ply_path=Path("missing"), c2_checkpoint_path=Path("missing"), reference_cells_path=Path("missing"),
                    source_commit="a" * 40, run_id="toy-run", handoff_id=config["handoff_id"],
                    accepted_receipt_path=receipt_path, accepted_commit="b" * 40,
                    project_image_id=image_id, artifact_root_token="artifact://JointBuildGS",
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

    def test_finalize_emits_unassociated_rows_as_g0_instead_of_aborting(self) -> None:
        config = contract.load_config()
        roster = contract.read_csv(contract.REPO / config["scope"]["roster_path"])
        mappings = []
        cells = []
        for index, item in enumerate(roster):
            cells.append({
                "stable_id": item["stable_id"], "group_id": item["group_id"], "patch_id": f"UASPATCH_{index:020x}",
                "flat_index": str(index), "cell_ix": "1", "cell_iy": "1", "cell_x": "1.5", "cell_y": "1.5",
                "top_z": "5", "normal_x": "0", "normal_y": "0", "normal_z": "1",
            })
            for method in contract.CONDITIONS:
                mappings.append({
                    "building_id": item["stable_id"], "group_id": item["group_id"], "split": "development",
                    "method_id": method, "component_id": None, "operation_unit_id": None,
                    "reference_cell_count": 1, "component_overlap_reference_cells": 0,
                    "association_role": "SCORE_IDENTITY_ONLY_AFTER_FROZEN_CONDITION_GEOMETRY",
                    "pre_roofer_failure": None,
                })
        with tempfile.TemporaryDirectory() as temporary:
            store = contract.AddOnceStore(Path(temporary))
            mapping_record = store.add("freeze/development_score_association_v1.jsonl", contract.jsonl_bytes(mappings))
            cells_record = store.add("freeze/development_score_cells_v1.jsonl", contract.jsonl_bytes(cells))
            components_record = store.add("freeze/condition_components_v1.jsonl", b"")
            units_record = store.add("freeze/execution_units_v1.jsonl", b"")
            store.add_json("control/synthetic_smoke_pass_v1.json", {"status": "PASS"})
            store.add_json("control/preselected_cases_v1.json", {"cases": contract.representative_cases(roster)})
            store.add_json("control/scientific_prepared_v1.json", {
                "status": "PREPARED", "run_id": "run", "operation_id": "a" * 64,
                "condition_components": components_record, "development_score_association": mapping_record,
                "development_score_cells": cells_record, "execution_units": units_record,
                "unique_execution_units": 0, "duplicate_roofer_calculations_prevented": 0,
                "execution_authority": {"handoff_id": config["handoff_id"]}, "tool_records": {}, "input_records": {}, "output_records": {},
            })
            finalized = contract.finalize(store)
            rows = contract.parse_jsonl(store.read_verified(finalized["metrics"]))
            technical = contract.parse_jsonl(store.read_verified(finalized["condition_group_technical_summary"]))
        self.assertEqual(102, len(rows))
        self.assertTrue(all(row["G0_generated"] is False for row in rows))
        self.assertTrue(all(row["failure_reasons"] == ["UNASSOCIATED_CONDITION_COMPONENT"] for row in rows))
        self.assertEqual(10, len(technical))


if __name__ == "__main__":
    unittest.main()

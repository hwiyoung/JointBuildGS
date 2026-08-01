from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np


SCRIPT = Path("scripts/input_and_alignment/gate_s0/freeze_recovery_v1/run_freeze_recovery.py")
SPEC = importlib.util.spec_from_file_location("freeze_recovery", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def small_config() -> dict:
    return {
        "grid": {
            "terrain_filter_windows_cells": [3, 5],
            "local_window_cells": 3,
            "minimum_points_per_cell": 3,
            "minimum_height_above_terrain_m": 2.5,
            "minimum_valid_neighbors": 3,
            "local_plane_rmse_limit_m": 10.0,
            "minimum_up_dot": 0.1,
            "vegetation_roughness_limit_m": 20.0,
            "within_cell_z_std_limit_m": 10.0,
            "vegetation_z_std_trigger_m": 20.0,
            "minimum_component_cells": 2,
            "minimum_planar_fraction": 0.5,
        },
        "association": {
            "minimum_intersection_area_m2": 1.0,
            "minimum_reference_overlap_fraction": 0.5,
        },
        "aoi": {"bbox": [0.0, 0.0, 6.0, 6.0]},
    }


def roof_grid(z_shift: float = 0.0):
    grid = MODULE.RecoveryGrid((0.0, 0.0, 6.0, 6.0), 1.0)
    for iy in range(6):
        for ix in range(6):
            x = np.array([ix + 0.2, ix + 0.4, ix + 0.6])
            y = np.array([iy + 0.2, iy + 0.4, iy + 0.6])
            if 1 <= ix <= 4 and 1 <= iy <= 4:
                z = np.array([z_shift, z_shift + 5.0, z_shift + 5.0])
            else:
                z = np.array([z_shift, z_shift, z_shift])
            grid.update(x, y, z)
    return grid


class FreezeRecoveryTests(unittest.TestCase):
    def test_frozen_common_source_and_minimal_consumer_graph(self) -> None:
        config = json.loads(MODULE.CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual((962, 937, 25), (
            config["common_source"]["image_members"],
            config["common_source"]["included_pairs"],
            config["common_source"]["excluded_no_pose"],
        ))
        consumed = config["consumed_common_base"]
        self.assertEqual(807_030_928, consumed["camera_model"]["expected_bytes"] + consumed["image_poses"]["expected_bytes"] + consumed["sparse_points"]["expected_bytes"] + consumed["dense_ply"]["expected_bytes"])
        not_consumed = {Path(item["path"]).name for item in consumed["not_consumed"]}
        self.assertTrue({"rigs.bin", "frames.bin", "scene.mvs", "dim_v1.laz"}.issubset(not_consumed))
        self.assertNotIn("points3D.bin", not_consumed)

    def test_reference_ids_ignore_vertical_shift(self) -> None:
        first = MODULE.extract_reference(roof_grid(0.0), small_config(), "config-blob")
        second = MODULE.extract_reference(roof_grid(100.0), small_config(), "config-blob")
        self.assertEqual(sorted(first.component_ids.values()), sorted(second.component_ids.values()))
        self.assertGreater(len(first.component_ids), 0)

    def test_reference_rule_uses_no_prior_or_semantic_input(self) -> None:
        reference = MODULE.extract_reference(roof_grid(), small_config(), "config-blob")
        rows = MODULE.reference_rows(roof_grid(), reference)
        self.assertGreater(len(rows), 0)
        self.assertNotIn("roof_type", rows[0])
        self.assertNotIn("source_lod2", rows[0])
        self.assertNotIn("absolute_z", rows[0])

    def test_reference_component_planar_fraction_includes_nonplanar_candidates(self) -> None:
        permissive = small_config()
        permissive["grid"]["local_plane_rmse_limit_m"] = 0.1
        permissive["grid"]["minimum_planar_fraction"] = 0.1
        accepted = MODULE.extract_reference(roof_grid(), permissive, "rules")
        self.assertEqual([0.25], list(accepted.planar_fraction.values()))
        strict = small_config()
        strict["grid"]["local_plane_rmse_limit_m"] = 0.1
        strict["grid"]["minimum_planar_fraction"] = 0.7
        rejected = MODULE.extract_reference(roof_grid(), strict, "rules")
        self.assertEqual({}, rejected.component_ids)

    def test_reference_crosswalk_scores_only_independent_cells_inside_target_bbox(self) -> None:
        grid = roof_grid()
        reference = MODULE.extract_reference(grid, small_config(), "rules")
        associations, score_cells, rows = MODULE.crosswalk_reference_to_buildings(
            grid,
            reference,
            [{"stable_id": "B", "bbox": (1.0, 1.0, 3.0, 3.0)}],
            3.0,
        )
        self.assertTrue(associations["B"])
        self.assertGreater(score_cells["B"], 0)
        self.assertTrue(any(row["score_support_is_independent_uas_cells_clipped_to_target_bbox"] == "true" for row in rows))
        self.assertTrue(all(row["lod2_geometry_used_as_score_geometry"] == "false" for row in rows))

    def test_c5_candidate_load_checks_attestation_and_keeps_independent_reference(self) -> None:
        grid = roof_grid()
        terrain = MODULE.terrain_envelope(grid, [3, 5])
        record = {
            "stable_building_id": "DEBY_LOD2_TEST",
            "footprint": [{"exterior": [[0.5, 0.5], [5.5, 0.5], [5.5, 5.5], [0.5, 5.5], [0.5, 0.5]], "interiors": []}],
            "ground_height_m": 0.0,
            "top_height_m": 5.0,
            "prior_role": "LOD2_DERIVED_COARSE_LOD1",
            "evaluation_class": "REFERENCE_DERIVED_DIAGNOSTIC_ONLY",
            "primary_c5_eligible": False,
        }
        data = (json.dumps(record, sort_keys=True) + "\n").encode()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "prior.jsonl"
            path.write_bytes(data)
            spec = {"bytes": len(data), "attested_sha256": MODULE.sha256_bytes(data)}
            selected, input_record, deltas = MODULE.load_c5_file_once(
                path,
                spec,
                {"DEBY_LOD2_TEST"},
                grid,
                terrain,
                {"DEBY_LOD2_TEST": (1.0, 1.0, 5.0, 5.0)},
                10.0,
            )
        self.assertEqual(["DEBY_LOD2_TEST"], list(selected))
        self.assertTrue(selected["DEBY_LOD2_TEST"]["independent_primary_reference_required"])
        self.assertTrue(selected["DEBY_LOD2_TEST"]["input_available_within_fixed_buffer"])
        self.assertEqual(10.0, selected["DEBY_LOD2_TEST"]["input_availability_buffer_m"])
        self.assertEqual(1, input_record["full_passes"])
        self.assertTrue(deltas)

    def test_c5_provenance_guard_rejects_primary_eligible_record(self) -> None:
        grid = roof_grid()
        terrain = MODULE.terrain_envelope(grid, [3, 5])
        record = {
            "stable_building_id": "bad",
            "footprint": [{"exterior": [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]], "interiors": []}],
            "primary_c5_eligible": True,
        }
        data = (json.dumps(record) + "\n").encode()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.jsonl"
            path.write_bytes(data)
            spec = {"bytes": len(data), "attested_sha256": MODULE.sha256_bytes(data)}
            with self.assertRaisesRegex(RuntimeError, "provenance guard"):
                MODULE.load_c5_file_once(path, spec, {"bad"}, grid, terrain)

    def test_split_group_connects_same_tile_and_shared_prior(self) -> None:
        units = [
            {"stable_id": "a", "execution_tile_id": "t1", "e_paired": "true"},
            {"stable_id": "b", "execution_tile_id": "t1", "e_paired": "true"},
            {"stable_id": "c", "execution_tile_id": "t2", "e_paired": "true"},
        ]
        groups, splits = MODULE.split_groups(units, {"a": ["p1"], "c": ["p1"]}, "20260731")
        self.assertEqual(groups["a"], groups["b"])
        self.assertEqual(groups["a"], groups["c"])
        self.assertEqual(1, len(set(splits.values())))

    def test_checkpoint_survives_later_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = MODULE.Checkpoints(Path(temporary), "op")
            store.write(10, "upstream", {"digest": "abc"})
            try:
                raise RuntimeError("injected later failure")
            except RuntimeError:
                pass
            path = Path(temporary) / "checkpoints/010-upstream.json"
            self.assertTrue(path.is_file())
            self.assertEqual("op", json.loads(path.read_text())["operation_id"])
            resumed = MODULE.Checkpoints(Path(temporary), "op")
            self.assertTrue(resumed.completed(10, "upstream"))
            self.assertEqual("abc", resumed.payload(10, "upstream")["digest"])

    def test_add_once_reuses_identical_orphan_and_refuses_different_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "one.json"
            MODULE.add_once_json(path, {"a": 1})
            reused = MODULE.add_once_json(path, {"a": 1})
            self.assertTrue(reused["reused_orphan_exact"])
            with self.assertRaisesRegex(RuntimeError, "differs from deterministic retry"):
                MODULE.add_once_json(path, {"a": 2})

    def test_synthetic_las_exercises_missing_pyproj_fallback_path(self) -> None:
        result = MODULE.synthetic_laz_fallback_check()
        self.assertEqual(3, result["points"])
        self.assertEqual(1, result["chunks"])

    def test_epsg_transform_residual(self) -> None:
        x, y = MODULE.base.epsg32632_to_25832(np.array([690791.74]), np.array([5335864.05]))
        self.assertLess(abs(float(x[0]) - 690791.740001741), 0.0003)
        self.assertLess(abs(float(y[0]) - 5335864.049877891), 0.0003)

    def test_stage3_smoke_has_five_conditions_and_no_external_roofprint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = MODULE.write_stage3_smoke_inputs(root)
            geojson = json.loads((root / "stage3/synthetic_r_derived.geojson").read_text())
        self.assertEqual(5, len(result["condition_labels"]))
        self.assertFalse(result["external_roofprint_used"])
        self.assertFalse(result["quality_or_performance"])
        self.assertEqual("condition_class6_points_only", result["roofprint_source"])
        self.assertEqual("Polygon", geojson["features"][0]["geometry"]["type"])

    def test_roofer_runtime_receipt_hashes_only_task_outputs(self) -> None:
        config = json.loads(MODULE.CONFIG_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = Path(temporary)
            output_root = artifact_root / config["output_namespace"]
            (output_root / "control").mkdir(parents=True)
            stage3 = MODULE.write_stage3_smoke_inputs(output_root)
            checkpoints = MODULE.Checkpoints(output_root, "op")
            checkpoints.write(90, "stage3_interface_smoke_inputs", {**stage3, "roofer_image": config["stage3"]["roofer_image"], "runtime_smoke_status": "PENDING_HOST_ORCHESTRATOR"})
            (output_root / "control/execution_ledger_v1.json").write_text(json.dumps({"operation_identity": {"operation_id": "op", "source_commit": "abc"}, "checkpoints": checkpoints.records}))
            (output_root / "stage3/roofer_smoke_sealed/output").mkdir(parents=True)
            (output_root / "stage3/roofer_smoke_sealed/output/smoke.city.jsonl").write_text(json.dumps({"type": "CityJSONFeature", "id": "SYNTHETIC_1", "CityObjects": {"SYNTHETIC_1": {"type": "Building", "geometry": [{"type": "MultiSurface", "lod": "2.2", "boundaries": [[[0, 1, 2, 3]]]}]}}, "vertices": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]}) + "\n")
            (output_root / "stage3/roofer_smoke_sealed/runtime.log").write_text("Roofer 1.0.0\n")
            runtime_control = {"status": "TEST_PASS", "acceptance": {"project_docker_image_id": "sha256:" + "1" * 64}}
            with mock.patch.object(MODULE, "enforce_runtime_control", return_value=runtime_control), mock.patch.object(MODULE, "validate_reusable_ledger", return_value={}):
                receipt = MODULE.record_roofer_smoke(
                    artifact_root,
                    0,
                    config["stage3"]["roofer_image"],
                    config["stage3"]["roofer_image_id"],
                    "sha256:" + "1" * 64,
                )
        self.assertEqual("PASS", receipt["status"])
        self.assertEqual("op", receipt["operation_id"])
        self.assertEqual("sha256:" + "1" * 64, receipt["observed_project_image_id"])
        self.assertEqual(0, receipt["scientific_source_bytes_read_or_hashed"])
        self.assertFalse(receipt["quality_or_performance"])

    def test_roofer_rejects_empty_json_and_wrong_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "empty.jsonl"
            path.write_text("{}\n")
            with self.assertRaisesRegex(RuntimeError, "no CityJSON geometry"):
                MODULE.validate_roofer_json(path)
        config = json.loads(MODULE.CONFIG_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RuntimeError, "pinned image"):
                MODULE.record_roofer_smoke(
                    Path(temporary),
                    0,
                    config["stage3"]["roofer_image"] + "-wrong",
                    config["stage3"]["roofer_image_id"],
                    "sha256:" + "1" * 64,
                )

    def test_c4_provider_classes_are_isolated(self) -> None:
        grid = MODULE.RecoveryGrid((0.0, 0.0, 2.0, 2.0), 1.0)
        grid.update(np.array([0.2, 0.3, 0.4]), np.array([0.2, 0.3, 0.4]), np.array([0.0, 5.0, 100.0]), np.array([2, 6, 20], dtype=np.uint8))
        self.assertEqual(5.0, grid.class6_max_z[0])
        self.assertEqual(0.0, grid.class2_min_z[0])

    def test_processing_buffer_does_not_collapse_spatial_split_groups(self) -> None:
        units = [
            {"stable_id": "left", "execution_tile_id": "t1", "e_paired": "true", "bbox_min_x": "0", "bbox_min_y": "0", "bbox_max_x": "1", "bbox_max_y": "1"},
            {"stable_id": "right", "execution_tile_id": "t2", "e_paired": "true", "bbox_min_x": "15", "bbox_min_y": "0", "bbox_max_x": "16", "bbox_max_y": "1"},
        ]
        groups, _ = MODULE.split_groups(units, {}, "seed")
        self.assertNotEqual(groups["left"], groups["right"])

    def test_canonical_scene_population_is_exact_199(self) -> None:
        config = json.loads(MODULE.CONFIG_PATH.read_text(encoding="utf-8"))
        buildings, record = MODULE.load_candidate_buildings(config)
        self.assertEqual(199, len(buildings))
        self.assertEqual(config["eligibility"]["stable_id_set_sha256"], record["stable_id_set_sha256"])
        self.assertEqual("CLASSIFIED_CURRENT_MVS_CLASS_2_6_POINT_XY_PERCENTILE_1_TO_99_PLUS_FIXED_25M_MARGIN", config["aoi"]["selection_rule"])
        self.assertTrue(config["aoi"]["lod2_groundsurface_overlay_used_before_aoi_selection"])
        self.assertFalse(config["aoi"]["lod2_roofsurface_roof_type_or_performance_used"])
        self.assertFalse(config["aoi"]["outcome_or_roof_label_used"])

    def test_all_199_targets_are_assigned_to_an_existing_aoi_tile(self) -> None:
        config = json.loads(MODULE.CONFIG_PATH.read_text(encoding="utf-8"))
        buildings, _ = MODULE.load_candidate_buildings(config)
        tile_ids = {feature["properties"]["tile_id"] for feature in MODULE.execution_tiles_geojson(config)["features"]}
        assigned = {MODULE.execution_tile_id(config, building["bbox"]) for building in buildings}
        self.assertEqual(199, len(buildings))
        self.assertTrue(assigned)
        self.assertTrue(assigned <= tile_ids)
        self.assertFalse(any("-" in tile_id.removeprefix("TILE_") for tile_id in assigned))

    def test_roofer_host_contract_preflights_and_scopes_mounts(self) -> None:
        path = MODULE.REPO / "scripts/input_and_alignment/gate_s0/freeze_recovery_v1/run_roofer_smoke_host.sh"
        script = path.read_text(encoding="utf-8")
        self.assertLess(script.index("--mode runtime-control"), script.index("synthetic_class26.laz:/work/stage3/synthetic_class26.laz:ro"))
        self.assertIn('"${OBSERVED_PROJECT_IMAGE_ID}"', script)
        self.assertIn('synthetic_class26.laz:/work/stage3/synthetic_class26.laz:ro', script)
        self.assertIn('synthetic_r_derived.geojson:/work/stage3/synthetic_r_derived.geojson:ro', script)
        self.assertNotIn('-v "${ARTIFACT_ROOT_HOST}:/artifacts/JointBuildGS" \\\n  -w "/artifacts/JointBuildGS/${TASK_REL}"', script)
        self.assertEqual(2, script.count('-v "${ARTIFACT_ROOT_HOST}:/artifacts/JointBuildGS:ro"'))
        self.assertIn('-v "${TASK_HOST}:/artifacts/JointBuildGS/${TASK_REL}:rw"', script)
        self.assertLess(script.index('find "${PENDING_ATTEMPT}/output" -type f -exec sync -f'), script.index('mv "${PENDING_ATTEMPT}/.exit_code.pending" "${PENDING_ATTEMPT}/exit_code"'))
        self.assertLess(script.index('mv "${PENDING_ATTEMPT}/.exit_code.pending" "${PENDING_ATTEMPT}/exit_code"'), script.index('mv "${PENDING_ATTEMPT}" "${SEALED_ATTEMPT}"', script.index('if [[ ! -d "${SEALED_ATTEMPT}" ]]')))
        self.assertIn("roofer_smoke_sealed", script)

    def test_completed_c5_checkpoint_reconstructs_without_source(self) -> None:
        row = {
            "stable_id": "A",
            "footprint_polygon_count": 1,
            "input_prior_role": "LOD1",
            "source_evaluation_class": "REFERENCE_DERIVED_DIAGNOSTIC_ONLY",
            "primary_c5_eligible_in_source_same_lineage": False,
            "independent_primary_reference_required": True,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoints = MODULE.Checkpoints(root, "operation")
            checkpoints.write(71, "c5_input_1", {"input": {"path": "/source/removed.jsonl", "full_passes": 1}, "selected_rows": [row], "ground_to_mvs_deltas_m": [1.25]})
            resumed = MODULE.Checkpoints(root, "operation")
            payload = resumed.payload(71, "c5_input_1")
        self.assertEqual("A", payload["selected_rows"][0]["stable_id"])
        self.assertEqual([1.25], payload["ground_to_mvs_deltas_m"])

    def test_source_attempts_are_durable_and_retry_cap_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            attempts = MODULE.SourceAttempts(Path(temporary), "operation", retry_max=1)
            attempts.start("dense_mvs", [{"path": "/source/dense.ply", "accepted_bytes": 10}])
            attempts.start("dense_mvs", [{"path": "/source/dense.ply", "accepted_bytes": 10}])
            with self.assertRaisesRegex(RuntimeError, "retry cap exhausted"):
                attempts.start("dense_mvs", [{"path": "/source/dense.ply", "accepted_bytes": 10}])
            audit = attempts.audit()
        self.assertEqual(2, audit["attempt_counts"]["dense_mvs"])
        self.assertEqual(2, audit["maximum_attempts_per_stage"])

    def test_hard_exit_pending_write_is_quarantined_without_publication(self) -> None:
        code = (
            "import os,sys; from pathlib import Path; "
            "from scripts.input_and_alignment.gate_s0.freeze_recovery_v1 import run_freeze_recovery as m; "
            "w=m.AddOnceWriter(Path(sys.argv[1])); w.write(b'partial'); "
            "w.handle.flush(); os.fsync(w.handle.fileno()); os._exit(17)"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            final = root / "common/value.bin"
            completed = subprocess.run([sys.executable, "-c", code, str(final)], check=False)
            self.assertEqual(17, completed.returncode)
            self.assertFalse(final.exists())
            self.assertTrue(final.with_name(".value.bin.pending").exists())
            recovered = MODULE.recover_pending_files(root)
            self.assertEqual("QUARANTINED_INCOMPLETE_STAGE_OUTPUT", recovered[0]["action"])
            self.assertFalse(final.exists())

    def test_unknown_resume_namespace_file_is_rejected(self) -> None:
        self.assertTrue(MODULE.allowed_namespace_file("checkpoints/071-c5_input_1.json"))
        self.assertTrue(MODULE.allowed_namespace_file("inputs/c4_690_5335_grid_v1.npz"))
        self.assertFalse(MODULE.allowed_namespace_file("unexpected/source-copy.bin"))

    def test_reusable_ledger_rejects_summary_tamper(self) -> None:
        config = json.loads(MODULE.CONFIG_PATH.read_text(encoding="utf-8"))
        operation_contract = {"source_commit": "abc", "contract": "test"}
        operation_id = MODULE.sha256_bytes(MODULE.canonical_json_bytes(operation_contract))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoints = MODULE.Checkpoints(root, operation_id)
            summary_record = None
            for ordinal, stage in sorted(MODULE.expected_checkpoint_stages(config, False).items()):
                payload = {}
                if ordinal == 100:
                    summary_record = MODULE.add_once_json(root / "freeze/technical_summary_v1.json", {"operation_id": operation_id, "source_commit": "abc"})
                    payload = {"summary": summary_record}
                checkpoints.write(ordinal, stage, payload)
            ledger_path = root / "control/execution_ledger_v1.json"
            MODULE.add_once_json(
                ledger_path,
                {
                    "schema": "jointbuildgs.gate_s0_freeze_recovery_no_repeat_ledger.v1",
                    "status": "EXECUTION_COMPLETE_PENDING_ROOFER_SMOKE",
                    "operation_identity": {**operation_contract, "operation_id": operation_id},
                    "checkpoints": checkpoints.records,
                    "source_attempts": MODULE.SourceAttempts(root, operation_id, config["cost_caps"]["retry_max"]).audit(),
                },
            )
            MODULE.validate_reusable_ledger(root, ledger_path, operation_contract, config)
            assert summary_record is not None
            Path(summary_record["path"]).write_text("{}\n")
            with self.assertRaisesRegex(RuntimeError, "compact output digest mismatch"):
                MODULE.validate_reusable_ledger(root, ledger_path, operation_contract, config)

    def test_protected_work_guards_are_false(self) -> None:
        config = json.loads(MODULE.CONFIG_PATH.read_text(encoding="utf-8"))
        for key in ("performance", "quality_scoring", "held_out_access", "fusion_w1_access", "r_ext_access", "source_lod2_geometry_access"):
            self.assertFalse(config["guards"][key])
        self.assertIsNone(config["scientific_verdict"])


if __name__ == "__main__":
    unittest.main()

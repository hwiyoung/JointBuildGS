from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import torch

from scripts.p2.c3_development_stage3_v1 import contract
from scripts.p2_baselines.c1_c2_feasibility_pilot_v1.contract import (
    AddOnceStore,
    canonical_json_bytes,
    read_csv,
    sha256_bytes,
)
from src.stage3.c3_checkpoint_roofer_adapter_v1 import LOCAL_SHIFT_XYZ


def _logits(label: int) -> list[float]:
    value = [-4.0] * 4
    value[label] = 4.0
    return value


def _checkpoint() -> dict:
    sx, sy, sz = LOCAL_SHIFT_XYZ
    world = [
        [690792.2, 5335864.2, 615.0],
        [690793.2, 5335864.2, 615.1],
        [690792.2, 5335865.2, 615.2],
        [690793.2, 5335865.2, 615.3],
        [690792.2, 5335864.2, 604.0],
        [690793.2, 5335864.2, 604.0],
        [690792.2, 5335865.2, 604.0],
        [690793.2, 5335865.2, 604.0],
    ]
    local = [[x - sx, y - sy, z - sz] for x, y, z in world]
    return {
        "it": 30000,
        "n_prim": 8,
        "state_dict": {
            "means": torch.tensor(local, dtype=torch.float32),
            "sem_logits": torch.tensor([_logits(1)] * 4 + [_logits(3)] * 4),
            "opacities_raw": torch.zeros(8),
        },
        "stage2_group_ids": torch.tensor([0] * 4 + [1] * 4),
        "stage2_rep_normals": torch.tensor([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]]),
        "stage2_rep_d": torch.tensor([615.0, 604.0]),
    }


class C3DevelopmentStage3ContractTests(unittest.TestCase):
    def test_preflight_reuses_exact_roofer_contract_and_keeps_final_gates_null(self) -> None:
        result = contract.validate_contract()
        self.assertEqual("PASS", result["status"])
        self.assertIn("--lod22", result["roofer_command_args"])
        self.assertIsNone(result["G3"])
        self.assertIsNone(result["G4"])
        self.assertIsNone(result["PASS_usable"])
        self.assertIsNone(result["scientific_verdict"])

    def test_score_input_is_rejected_before_geometry_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "must be frozen before association"):
                contract.associate_development(
                    AddOnceStore(root / "out"),
                    score_cells_path=root / "not-opened.jsonl",
                    source_commit="a" * 40,
                    run_id="test-run",
                )

    def test_prepare_then_associate_emits_one_shared_job_and_multiplicity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint_path = root / "final.pt"
            torch.save(_checkpoint(), checkpoint_path)
            config = deepcopy(contract.load_config())
            expected = config["inputs"]["r4_final_checkpoint"]
            expected["bytes"] = checkpoint_path.stat().st_size
            expected["expected_primitives"] = 8
            expected["expected_stage2_groups"] = 2
            expected["expected_grouped_primitives"] = 8

            roster = read_csv(
                contract.REPO / "configs/p2_baselines/c1_c2_feasibility_pilot_v1/development_roster_v1.csv"
            )
            score_rows = []
            for row in roster:
                score_rows.append({
                    "stable_id": row["stable_id"], "group_id": row["group_id"],
                    "cell_ix": 0, "cell_iy": 0,
                })
            while len(score_rows) < 21714:
                score_rows.append(dict(score_rows[0]))
            score_data = b"".join(canonical_json_bytes(row) for row in score_rows)
            score_path = root / "development_score_cells_v1.jsonl"
            score_path.write_bytes(score_data)
            score_spec = config["inputs"]["r3_development_score_cells"]
            score_spec["bytes"] = len(score_data)
            score_spec["sha256"] = sha256_bytes(score_data)

            store = AddOnceStore(root / "out")
            with (
                patch.object(contract, "load_config", return_value=config),
                patch.object(contract, "_validate_r4_attestation", return_value={"record": {"sha256": expected["sha256"]}}),
            ):
                frozen = contract.prepare_geometry(
                    store,
                    checkpoint_path=checkpoint_path,
                    source_commit="a" * 40,
                    run_id="test-run",
                )
                associated = contract.associate_development(
                    store,
                    score_cells_path=score_path,
                    source_commit="a" * 40,
                    run_id="test-run",
                )
                execution_unit = json.loads(
                    (store.root / "freeze/c3_execution_units_v1.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()[0]
                )
                work = store.root / execution_unit["work_directory"]
                (work / "out").mkdir()
                (work / "runtime.log").write_text("synthetic failure\n", encoding="utf-8")
                sealed_output = work / "out" / "sealed.bin"
                sealed_output.write_bytes(b"sealed")
                contract.record_roofer_terminal(
                    store,
                    unit_id=execution_unit["operation_unit_id"],
                    exit_code=1,
                    runtime_seconds=2,
                )
                contract.verify_roofer_terminal(
                    store, unit_id=execution_unit["operation_unit_id"]
                )
                sealed_output.write_bytes(b"tampered")
                with self.assertRaisesRegex(RuntimeError, "record output digest mismatch"):
                    contract.verify_roofer_terminal(
                        store, unit_id=execution_unit["operation_unit_id"]
                    )
                sealed_output.write_bytes(b"sealed")
                extra_output = work / "out" / "extra.bin"
                extra_output.write_bytes(b"extra")
                with self.assertRaisesRegex(RuntimeError, "output tree differs"):
                    contract.verify_roofer_terminal(
                        store, unit_id=execution_unit["operation_unit_id"]
                    )
                extra_output.unlink()
                symlink_output = work / "out" / "link.bin"
                os.symlink(sealed_output, symlink_output)
                with self.assertRaisesRegex(RuntimeError, "symlink/non-regular"):
                    contract.verify_roofer_terminal(
                        store, unit_id=execution_unit["operation_unit_id"]
                    )
                symlink_output.unlink()
                finalized = contract.finalize_technical(
                    store,
                    source_commit="a" * 40,
                    run_id="test-run",
                )

            self.assertEqual("FROZEN", frozen["status"])
            self.assertEqual(0, frozen["reference_score_inputs_opened_before_freeze"])
            self.assertEqual(0, frozen["checkpoint_input"]["full_hash_passes"])
            self.assertEqual("ASSOCIATED", associated["status"])
            self.assertTrue(associated["geometry_frozen_before_score_open"])
            self.assertEqual(1, associated["unique_roofer_operations"])
            self.assertEqual(50, associated["duplicate_roofer_calculations_prevented"])
            multiplicity = json.loads(
                (store.root / "diagnostics/c3_component_multiplicity_v1.json").read_bytes()
            )
            self.assertEqual(1, multiplicity["unique_associated_component_count"])
            self.assertEqual(51, multiplicity["max_buildings_sharing_one_component"])
            self.assertEqual({"SHARED_COMPONENT": 51}, multiplicity["association_class_counts"])
            self.assertEqual(
                "TECHNICAL_ASSOCIATION_MULTIPLICITY_NOT_INDEPENDENT_BUILDING_SUCCESS",
                multiplicity["interpretation"],
            )
            job = json.loads(
                (store.root / "freeze/c3_all_jobs_v1.jsonl").read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertFalse(job["stable_id_used_to_derive_input"])
            self.assertFalse(job["reference_or_bbox_used_to_derive_input"])
            self.assertEqual(contract.load_reused_config()["stage3"]["command_args"], job["roofer_command_args"])
            self.assertIsNone(associated["G3"])
            self.assertIsNone(associated["G4"])
            self.assertIsNone(associated["PASS_usable"])
            self.assertEqual(51, finalized["result_rows"])
            self.assertEqual(0, finalized["building_level_gate_evaluable_count"])
            self.assertEqual(0, finalized["building_G0_true_count"])
            self.assertEqual(0, finalized["building_G1_true_count"])
            result_rows = [
                json.loads(line)
                for line in (store.root / "results/development_technical_results_v1.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertTrue(all(row["G0_generated"] is None for row in result_rows))
            self.assertTrue(all(row["G1_schema_semantic"] is None for row in result_rows))
            self.assertTrue(all(row["result_class"] == "DEVELOPMENT_TECHNICAL_DIAGNOSTIC_ONLY" for row in result_rows))
            self.assertIsNone(finalized["G2"])
            stage_text = (store.root / "results/stage_counts_v1.csv").read_text(encoding="utf-8")
            self.assertIn("ONE_TO_ONE_BUILDING_COMPONENT,COMPLETE,0,51", stage_text)
            self.assertIn("COMPONENT_G0_GENERATED,COMPLETE,0,1", stage_text)
            self.assertIn("G2_GEOMETRY_TOPOLOGY_VALID,PENDING", stage_text)
            self.assertIn("PASS_USABLE,PENDING", stage_text)
            result_path = store.root / "results/development_technical_results_v1.jsonl"
            original_result = result_path.read_bytes()
            result_path.write_bytes(original_result + b"{}\n")
            with self.assertRaisesRegex(RuntimeError, "record output digest mismatch"):
                contract.finalize_technical(
                    store,
                    source_commit="a" * 40,
                    run_id="test-run",
                )


if __name__ == "__main__":
    unittest.main()

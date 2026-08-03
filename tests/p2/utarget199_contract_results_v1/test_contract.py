from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.p2_baselines.c1_c2_feasibility_pilot_v1.contract import AddOnceStore, canonical_json_bytes
from scripts.p2.utarget199_contract_results_v1.contract import (
    _g4_candidate,
    _reference_rows_for_finalize,
    associate_components,
    load_config,
    validate_config,
)


class ContractTest(unittest.TestCase):
    def test_host_wrapper_validates_recovery_receipt_with_artifact_root(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        wrapper = (repo_root / "scripts/p2/utarget199_contract_results_v1/run_contract_host.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("P2-W2C-UTARGET199-CONTRACT-RESULTS-RECOVERY-R3-v1/100-accepted.json", wrapper)
        self.assertIn("--artifact-root /artifacts/JointBuildGS", wrapper)
        self.assertIn("PREPARED_SOURCE_COMMIT", wrapper)
        self.assertIn("PREPARED_RUN_ID", wrapper)

    def test_existing_reference_ledger_is_verified_and_reused_without_source_read(self) -> None:
        config = load_config()
        rows = [{"stable_id": "A", "patch_id": "P", "x": 1.0, "y": 2.0, "z": 3.0}]
        data = canonical_json_bytes(rows[0]) + b"\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = AddOnceStore(root)
            restart = config["inputs"]["reference_candidate_cells"]["derived_restart"]
            restart["bytes"] = len(data)
            restart["sha256"] = hashlib.sha256(data).hexdigest()
            target = root / restart["path"]
            target.parent.mkdir(parents=True)
            target.write_bytes(data)
            reused, source_record, output_record = _reference_rows_for_finalize(
                store, [], root / "must_not_be_opened.csv", config
            )
            self.assertEqual(rows, reused)
            self.assertEqual(0, source_record["full_read_and_digest_passes"])
            self.assertEqual(restart["sha256"], output_record["sha256"])

    def test_canonical_config_is_exact_199x3(self) -> None:
        result = validate_config()
        self.assertEqual(result["buildings"], 199)
        self.assertEqual(result["expected_rows"], 597)
        self.assertIsNone(result["scientific_verdict"])

    def test_bbox_association_retains_unassociated_and_flags_shared(self) -> None:
        roster = [
            {"stable_id": "A", "bbox": [0.0, 0.0, 1.0, 1.0], "reference_patch_ids": (), "candidate_split": "development"},
            {"stable_id": "B", "bbox": [0.0, 0.0, 1.0, 1.0], "reference_patch_ids": (), "candidate_split": "held_out"},
        ]
        components = []
        for method in ("C1_L_upper", "C2_MVS", "C3_GS_image"):
            components.append({"condition_id": method, "component_id": f"{method}_X", "cells": [[0, 0]]})
        result = associate_components(roster, components, [0.0, 0.0], 1.0)
        self.assertEqual(len(result), 6)
        self.assertTrue(all(row["association_status"] == "SHARED_COMPONENT" for row in result))
        self.assertTrue(all(row["one_to_one_building_component"] is False for row in result))

    def test_candidate_g4_requires_every_metric(self) -> None:
        thresholds = {
            "reference_vertical_coverage_min": 0.8,
            "height_error_mae_m_max": 1.0,
            "RMSZ_m_max": 1.0,
            "RMSXY_m_max": 1.0,
            "surface_distance_rmse_m_max": 1.0,
            "surface_distance_p95_m_max": 2.0,
        }
        passing = {
            "reference_vertical_coverage": 0.9,
            "height_error_mae_m": 0.5,
            "RMSZ_m": 0.7,
            "RMSXY_m": 0.4,
            "surface_distance_rmse_m": 0.8,
            "surface_distance_p95_m": 1.5,
        }
        self.assertTrue(_g4_candidate(passing, thresholds))
        self.assertIsNone(_g4_candidate({**passing, "RMSZ_m": None}, thresholds))


if __name__ == "__main__":
    unittest.main()

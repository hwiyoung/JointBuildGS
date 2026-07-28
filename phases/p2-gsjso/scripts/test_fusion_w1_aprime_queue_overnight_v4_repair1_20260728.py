#!/usr/bin/env python3
"""Focused audit for the append-only overnight-v4 repair1 controller."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "phases/p2-gsjso/configs/fusion_w1_aprime_queue_overnight_v4_repair1_20260728.json"
LOCK_ROOT = REPO / "phases/p2-gsjso/runs/20260726_fusion_w1_aprime/unattended_queue_overnight_v4_repair1"
RECOVERY_LOCK = LOCK_ROOT / "RECOVERY_LOCK.json"
READOUT_LOCK = LOCK_ROOT / "READOUT_CONTINUATION_LOCK.json"
HISTORICAL_READOUT_LOCK = LOCK_ROOT / "HISTORICAL_READOUT_RECOVERY_LOCK.json"
WRAPPER = REPO / "phases/p2-gsjso/scripts/run_fusion_w1_aprime_queue_overnight_v4_repair1_20260728.sh"
V4_ROOT = REPO / "phases/p2-gsjso/runs/20260726_fusion_w1_aprime/unattended_queue_overnight_v4"
PLACEHOLDER_PREFIX = "__PLACEHOLDER_"
EXPECTED_HISTORICAL = [
    "DEBY_LOD2_42364663",
    "DEBY_LOD2_4907182",
    "DEBY_LOD2_4907510",
    "DEBY_LOD2_4908050",
]
EXPECTED_FAILED = EXPECTED_HISTORICAL[:3]


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"JSON root is not an object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_record(test: unittest.TestCase, record: dict) -> None:
    path = REPO / record["path"]
    test.assertTrue(path.is_file(), record["path"])
    test.assertFalse(path.is_symlink(), record["path"])
    test.assertEqual(path.stat().st_size, record["bytes"], record["path"])
    test.assertEqual(sha256(path), record["sha256"], record["path"])


def placeholders(value: object, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            found.extend(placeholders(nested, f"{prefix}.{key}" if prefix else key))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found.extend(placeholders(nested, f"{prefix}[{index}]"))
    elif isinstance(value, str) and value.startswith(PLACEHOLDER_PREFIX):
        found.append(prefix)
    return found


class OvernightV4Repair1Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_json(CONFIG)
        cls.overrides = cls.config["overrides"]
        cls.lock = load_json(RECOVERY_LOCK)
        cls.readout_lock = load_json(READOUT_LOCK)
        cls.historical_readout_lock = load_json(HISTORICAL_READOUT_LOCK)

    def test_single_level_extends_supported_schema(self) -> None:
        self.assertEqual(
            self.config["schema"],
            "jointbuildgs.fusion_w1_aprime.unattended_queue_overnight_v4.config.v1",
        )
        extends = self.config["extends"]
        self.assertEqual(
            extends,
            {
                "path": "phases/p2-gsjso/configs/fusion_w1_aprime_queue_continuation_v3_20260727.json",
                "sha256": "cea887ee9fc98ee34f807884d7a0163d3fbb949eeedfc21c87eada7e0959573e",
                "bytes": 11834,
            },
        )
        verify_record(self, extends)
        base = load_json(REPO / extends["path"])
        self.assertEqual(
            base["schema"],
            "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.config.v1",
        )
        self.assertNotIn("extends", base)

    def test_new_namespace_only(self) -> None:
        repair_root = self.overrides["outputs"]["root"]
        self.assertEqual(
            repair_root,
            "phases/p2-gsjso/runs/20260726_fusion_w1_aprime/unattended_queue_overnight_v4_repair1",
        )
        self.assertNotEqual(repair_root, self.overrides["readout_head_repair_contract"]["source_namespace"])
        self.assertTrue(self.overrides["publication"]["source_overnight_v4_never_rewritten"])
        for lane in ("gpu0", "gpu1"):
            values = self.overrides["resources"]["lanes"][lane]
            self.assertIn("unattended_queue_overnight_v4_repair1", values["lock"])
            self.assertIn("unattended_queue_overnight_v4_repair1", values["runtime_environment"])
            self.assertIn("repair1", values["container_namespace"])
        self.assertIn("unattended_queue_overnight_v4_repair1", self.overrides["resources"]["readout_lock"])

    def test_v4_terminal_evidence_and_identical_failures(self) -> None:
        evidence = self.lock["v4_readout_head_failure"]
        self.assertEqual(evidence["source_namespace"], V4_ROOT.relative_to(REPO).as_posix())
        self.assertFalse(evidence["source_namespace_mutation_allowed"])
        self.assertEqual(evidence["terminal_state"], "STOPPED_THREE_CONSECUTIVE_BUILDING_SKIPS")
        self.assertEqual(evidence["failure"]["error_type"], "RUN_READOUTExternalError")
        self.assertEqual(evidence["failure"]["consecutive_buildings_in_queue_order"], EXPECTED_FAILED)
        for record in evidence["records"].values():
            verify_record(self, record)
        stop = load_json(REPO / evidence["records"]["stage_stop"]["path"])
        self.assertEqual(stop["cause"]["consecutive_buildings"], EXPECTED_FAILED)
        self.assertEqual(stop["cause"]["error_type"], "RUN_READOUTExternalError")
        signatures = []
        for key in (
            "failure_42364663_attempt_003",
            "failure_4907182_attempt_003",
            "failure_4907510_attempt_003",
        ):
            failure = load_json(REPO / evidence["records"][key]["path"])
            self.assertEqual(failure["error_type"], "RUN_READOUTExternalError")
            self.assertIn("launch HEAD vs materialization HEAD", failure["message"])
            signatures.append(failure["error_signature"])
        self.assertEqual(signatures, [evidence["failure"]["error_signature"]] * 3)

    def test_four_canonical_readouts_were_absent_at_lock(self) -> None:
        absent = self.lock["v4_readout_head_failure"]["canonical_readout_complete_absent"]
        self.assertEqual(
            [Path(path).parts[-4] for path in absent],
            EXPECTED_HISTORICAL,
        )
        self.assertEqual(len(absent), 4)

    def test_historical_training_order_and_hashes(self) -> None:
        reuse = self.lock["historical_training_reuse"]
        self.assertEqual(reuse["producer_head"], "191b5652be6d38a81a3cba7ab05cd3db4ffbe796")
        self.assertEqual([row["building_id"] for row in reuse["allowed_jobs"]], EXPECTED_HISTORICAL)
        self.assertEqual([row["identity"]["building_id"] for row in reuse["records"]], EXPECTED_HISTORICAL)
        self.assertEqual(
            self.overrides["historical_training_reuse_contract"]["allowed_jobs"],
            reuse["allowed_jobs"],
        )
        for row in reuse["records"]:
            for key in ("materialization", "started", "completed", "final_checkpoint"):
                verify_record(self, row[key])

    def test_sequence_and_readout_lock(self) -> None:
        sequence = self.overrides["sequence_contract"]
        self.assertEqual(sequence["source_entries"], 20)
        self.assertEqual(sequence["historical_training_reuse_jobs"], 4)
        self.assertEqual(sequence["new_training_jobs"], 15)
        self.assertEqual(sequence["terminal_jobs"], 20)
        self.assertEqual(sequence["pair_count"], 11)
        self.assertEqual(self.readout_lock["state"], "LOCKED_BEFORE_REMAINING_JOB_START")
        self.assertEqual(self.readout_lock["scope"], {"remaining_jobs": 20, "physical_gpu": 1})
        self.assertEqual(self.readout_lock["binding"]["historical_training_jobs_allowed"], 4)
        self.assertEqual(self.readout_lock["binding"]["new_queue_training_jobs_after_historical_postprocess"], 15)
        self.assertFalse(self.readout_lock["binding"]["existing_v4_namespace_mutated"])

    def test_all_repair_inputs_are_frozen_without_placeholders(self) -> None:
        self.assertEqual(placeholders(self.config), [])
        self.assertEqual(placeholders(self.lock), [])
        for record in self.overrides["locked_inputs"].values():
            verify_record(self, record)
        verify_record(self, self.lock["recovery_scope"]["source_fixed_readout_config"])
        verify_record(self, self.lock["recovery_scope"]["readout_continuation_lock"])
        historical_record = self.overrides["locked_inputs"]["readout_head_repair_contract"]
        self.assertEqual(historical_record["path"], HISTORICAL_READOUT_LOCK.relative_to(REPO).as_posix())
        self.assertEqual(
            self.historical_readout_lock["schema"],
            "jointbuildgs.fusion_w1_aprime.readout_historical_training_recovery_lock.v1",
        )
        self.assertEqual(
            self.historical_readout_lock["state"],
            "LOCKED_FOR_HISTORICAL_READOUT_RECOVERY",
        )
        self.assertEqual(
            self.historical_readout_lock["historical_training_reuse"]["allowed_jobs"],
            self.lock["historical_training_reuse"]["allowed_jobs"],
        )

    def test_wrapper_is_thin_and_selects_repair1(self) -> None:
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn(CONFIG.relative_to(REPO).as_posix(), text)
        self.assertIn(Path(__file__).relative_to(REPO).as_posix(), text)
        self.assertIn("fusion_w1_aprime_queue_continuation_v3_20260727.py", text)
        self.assertIn("run_fusion_w1_aprime_queue_continuation_v3_20260727.sh", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

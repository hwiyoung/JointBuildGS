#!/usr/bin/env python3
"""Focused tests for the separate S3-A human-admission ledger."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("e5_c001_s3_human_admission.py")
SPEC = importlib.util.spec_from_file_location("e5_c001_s3_human_admission", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
ADMISSION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADMISSION)


class HumanAdmissionContractTest(unittest.TestCase):
    @staticmethod
    def valid_half() -> dict[str, str]:
        return {
            "run_name": ADMISSION.HALF_RUN,
            "record_type": "gate_summary",
            "gate_attempt": "2",
            "total_loss_finite_status": "pass",
            "train_return_code": "0",
            "semdepth_status": "pass",
            "boundary_normal_status": "pass",
            "semdepth_grad_share_max": "0.30117899587852465",
            "boundary_normal_grad_share_max": "0.0032805631872199433",
            "gate_status": "fail",
            "gate_reasons": ADMISSION.EXPECTED_MECHANICAL_REASON,
            "pi_all_targets_status": "fail",
            "effective_semdepth_scale": "0.5",
            "effective_nb_scale": "1.0",
            "effective_w_semdepth_smooth": "0.125",
            "effective_w_semdepth_plane": "0.125",
            "effective_w_boundary_normal": "0.01",
            "judgment_scope": "mechanical preregistered gate fields only; human verdict excluded",
        }

    def test_apply_appends_only_human_fields_and_preserves_mechanical_cells(self) -> None:
        half = self.valid_half()
        other = {"run_name": "other", "record_type": "loss_component", "gate_status": ""}
        fields = list(dict.fromkeys([*other, *half]))
        rows = [copy.deepcopy(other), copy.deepcopy(half)]
        before = copy.deepcopy(rows)
        output_fields, output = ADMISSION.apply_human_fields(fields, rows)
        self.assertEqual(output_fields[-2:], ADMISSION.HUMAN_FIELDS)
        for old, new in zip(before, output):
            self.assertEqual({key: new.get(key) for key in old}, old)
        self.assertEqual(output[0]["human_verdict"], "")
        self.assertEqual(output[1]["human_verdict"], ADMISSION.HUMAN_VERDICT)
        self.assertEqual(output[1]["human_verdict_reason"], ADMISSION.HUMAN_VERDICT_REASON)

    def test_wrong_reason_fails_closed(self) -> None:
        row = self.valid_half()
        row["human_verdict"] = ADMISSION.HUMAN_VERDICT
        row["human_verdict_reason"] = "different"
        with self.assertRaisesRegex(RuntimeError, "human_verdict_reason"):
            ADMISSION.validate_human_fields([row])

    def test_wrong_attempt_fails_closed(self) -> None:
        row = self.valid_half()
        row["gate_attempt"] = "1"
        row["human_verdict"] = ADMISSION.HUMAN_VERDICT
        row["human_verdict_reason"] = ADMISSION.HUMAN_VERDICT_REASON
        with self.assertRaisesRegex(RuntimeError, "outside the exact human ruling"):
            ADMISSION.validate_human_fields([row])

    def test_numeric_gate_criterion_still_fails_closed(self) -> None:
        row = self.valid_half()
        row["semdepth_grad_share_max"] = "0.400001"
        with self.assertRaisesRegex(RuntimeError, "locked <=0.40"):
            ADMISSION.validate_mechanical_half_summary(row)


if __name__ == "__main__":
    unittest.main()

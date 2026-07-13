#!/usr/bin/env python3
"""Focused contract tests for the S3-A gate orchestrator."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("e5_c001_s3_semantic_guided.py")
SPEC = importlib.util.spec_from_file_location("e5_c001_s3_semantic_guided", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
S3 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S3)


class S3OrchestratorContractTest(unittest.TestCase):
    _DIGEST_A = "sha256:" + "a" * 64
    _DIGEST_B = "sha256:" + "b" * 64

    def test_docker_image_id_accepts_host_digest_only_when_cli_unavailable(self) -> None:
        with (
            mock.patch.dict(os.environ, {"S3_DOCKER_IMAGE_ID": self._DIGEST_A}),
            mock.patch.object(S3, "capture", return_value="not_available:docker"),
        ):
            self.assertEqual(S3.docker_image_id(), self._DIGEST_A)

    def test_docker_image_id_rejects_real_inspect_mismatch(self) -> None:
        with (
            mock.patch.dict(os.environ, {"S3_DOCKER_IMAGE_ID": self._DIGEST_A}),
            mock.patch.object(S3, "capture", return_value=self._DIGEST_B),
        ):
            with self.assertRaisesRegex(RuntimeError, "does not match docker inspect"):
                S3.docker_image_id()

    def test_docker_image_id_rejects_fallback_when_inspect_executes_but_fails(self) -> None:
        with (
            mock.patch.dict(os.environ, {"S3_DOCKER_IMAGE_ID": self._DIGEST_A}),
            mock.patch.object(
                S3,
                "capture",
                return_value="Error response from daemon: No such image: jointbuildgs:dev",
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "inspect was executable"):
                S3.docker_image_id()

    def test_docker_image_id_requires_valid_digest_when_cli_unavailable(self) -> None:
        with (
            mock.patch.dict(os.environ, {"S3_DOCKER_IMAGE_ID": "not-a-digest"}),
            mock.patch.object(S3, "capture", return_value="not_available:docker"),
        ):
            with self.assertRaisesRegex(RuntimeError, "not a valid host-inspected sha256"):
                S3.docker_image_id()

    def test_exact_base_rejects_unknown_derived_key(self) -> None:
        base = S3.locked_base()
        derived = dict(base)
        derived.update(S3.SEMANTIC_DELTA)
        derived.update(
            {
                "semantic_geometry_audit_every": 10,
                "semantic_region_cache": S3.ws(S3.SEMANTIC_REGION_CACHE),
                "densify_audit_buildings": S3.DENSIFY_AUDIT_BUILDINGS,
                "s3_gate_attempt": 1,
                "s3_semdepth_scale": 1.0,
                "s3_nb_scale": 1.0,
                "s3_claim_scope": (
                    "oracle class+instance-address mechanism upper bound; not a battlefield "
                    "win; S3-B forbids the oracle ID map and owns the FM/paper claim"
                ),
                "s3_no_monocular_depth": True,
            }
        )
        S3.verify_exact_base(derived, base)
        derived["w_mvc_typo_or_injection"] = 123
        with self.assertRaisesRegex(RuntimeError, "unexpected"):
            S3.verify_exact_base(derived, base)

    def test_full_cell_may_inherit_one_half_scale_only_via_locked_shape(self) -> None:
        base = S3.locked_base()
        original_dir = S3.CONFIG_DIR
        with tempfile.TemporaryDirectory() as tmp:
            S3.CONFIG_DIR = Path(tmp)
            try:
                _path, config, _metadata = S3.make_config(
                    base=base,
                    run_name=S3.FULL_RUNS[0],
                    max_iter=S3.FULL_MAX_ITER,
                    generic_audit_every=S3.FULL_GENERIC_AUDIT_EVERY,
                    semantic_audit_every=S3.FULL_SEMANTIC_AUDIT_EVERY,
                    semdepth_scale=0.5,
                    nb_scale=1.0,
                    gate_attempt=0,
                )
            finally:
                S3.CONFIG_DIR = original_dir
        self.assertEqual(config["w_semdepth_smooth"], 0.125)
        self.assertEqual(config["w_semdepth_plane"], 0.125)
        self.assertEqual(config["w_boundary_normal"], 0.01)

    @staticmethod
    def _audit_rows() -> list[dict[str, str]]:
        primary = sorted(S3.PRIMARY_AUDIT_COMPONENTS)
        denominator = float(len(primary))
        rows = [
            {
                "step": "1500",
                "component": component,
                "grad_norm": "1",
                "grad_norm_share": str(1.0 / denominator),
                "denominator_role": "primary",
            }
            for component in primary
        ]
        rows.extend(
            {
                "step": "1500",
                "component": component,
                "grad_norm": str(2.0 * denominator),
                "grad_norm_share": "2.0",
                "denominator_role": "audit_only",
            }
            for component in sorted(S3.DETAIL_AUDIT_COMPONENTS)
        )
        return rows

    def test_gradient_shares_are_recomputed_and_detail_may_exceed_one(self) -> None:
        rows = self._audit_rows()
        self.assertEqual(S3.validate_denominator_contract(rows, {1500}), [])
        bad = [dict(row) for row in rows]
        bad[0]["grad_norm_share"] = "0.9"
        reasons = S3.validate_denominator_contract(bad, {1500})
        self.assertTrue(any("does not match primary norms" in reason for reason in reasons))
        detail = {
            "raw_loss": "1",
            "weighted_loss": "1",
            "weight": "0.25",
            "grad_norm": "2",
            "grad_norm_share": "2",
            "grad_status": "",
        }
        self.assertTrue(
            S3.component_audit_complete(
                [detail], 1, 0.25, require_unit_share=False
            )
        )

    def test_normalized_source_cannot_override_provenance(self) -> None:
        source = {
            "step": "1500",
            "run_name": "forged",
            "record_type": "forged",
            "source_csv": "forged",
            "source_row": "999",
            "active": "0",
        }
        rows = S3.normalize_source_rows(
            "locked_run",
            Path("loss.csv"),
            Path("semantic.csv"),
            [source],
            [],
            1500,
            2499,
        )
        self.assertEqual(rows[0]["run_name"], "locked_run")
        self.assertEqual(rows[0]["record_type"], "loss_component")
        self.assertEqual(rows[0]["source_csv"], "loss.csv")
        self.assertEqual(rows[0]["source_row"], 2)
        self.assertEqual(rows[0]["active"], 1)

    def test_seed_inventory_requires_exact_unique_six(self) -> None:
        rows = S3.read_csv(S3.CSV_SEED_INVENTORY)
        self.assertEqual(S3.validate_seed_inventory(rows), [])
        forged = [dict(rows[0]) for _ in range(6)]
        self.assertTrue(S3.validate_seed_inventory(forged))


if __name__ == "__main__":
    unittest.main()

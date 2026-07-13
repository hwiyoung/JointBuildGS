#!/usr/bin/env python3
"""Focused contract tests for the S3-A gate orchestrator."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("e5_c001_s3_semantic_guided.py")
SPEC = importlib.util.spec_from_file_location("e5_c001_s3_semantic_guided", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
S3 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S3)


class S3OrchestratorContractTest(unittest.TestCase):
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
                "s3_claim_scope": "oracle-label mechanism upper bound; not the FM/paper claim",
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

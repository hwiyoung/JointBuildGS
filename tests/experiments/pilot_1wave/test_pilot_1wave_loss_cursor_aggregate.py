#!/usr/bin/env python3
"""Synthetic CPU-only tests for P1W checkpoint-cursor loss aggregation."""
from __future__ import annotations

import ast
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = REPO / "scripts/pilot_1wave"
SCRIPT = SCRIPT_DIR / "pilot_1wave_loss_cursor_aggregate.py"
SPEC = importlib.util.spec_from_file_location(
    "pilot_1wave_loss_cursor_aggregate", SCRIPT
)
aggregate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = aggregate
SPEC.loader.exec_module(aggregate)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class PilotOneWaveLossCursorAggregateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix=".p1w_loss_cursor_", dir=TEST_DIR
        )
        self.root = Path(self.temporary.name)
        self.training_root = self.root / "training/runs"
        self.output = self.root / "outputs/pilot_1wave_loss_shares.csv"
        self.receipt = self.root / "outputs/pilot_1wave_loss_shares.receipt.json"
        self.run_receipts = self.root / "outputs/run_receipts"
        self.loaded_by_path: dict[Path, SimpleNamespace] = {}
        self.loader_calls: list[tuple[Path, dict[str, object]]] = []
        self._build_fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _loss_bytes(self, condition: str) -> bytes:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(
            buffer,
            fieldnames=aggregate.SOURCE_FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        for iteration in range(
            aggregate.AUDIT_EVERY,
            aggregate.CHECKPOINT_STEP + 1,
            aggregate.AUDIT_EVERY,
        ):
            for term in aggregate.LOSS_TERMS:
                if term == "pho":
                    raw = weighted = 0.25
                    share = roof_share = 0.4
                elif term == "plane" and condition in {"04a", "04b"}:
                    raw = weighted = 0.25
                    share = roof_share = 0.4
                elif term == "nc":
                    raw = weighted = 0.05
                    share = roof_share = 0.2
                else:
                    raw = weighted = share = roof_share = 0.0
                writer.writerow(
                    {
                        "iter": iteration,
                        "term": term,
                        "raw": raw,
                        "weighted": weighted,
                        "share": share,
                        "roof_share": roof_share,
                    }
                )
        return buffer.getvalue().encode("utf-8")

    def _build_fixture(self) -> None:
        for condition, seed in aggregate.EXPECTED_RUN_KEYS:
            run_dir = self.training_root / condition / f"seed_{seed}"
            audit_dir = run_dir / "audit"
            checkpoint_dir = run_dir / "ckpt"
            audit_dir.mkdir(parents=True)
            checkpoint_dir.mkdir(parents=True)

            config = run_dir / "resolved_config.json"
            config.write_text(
                json.dumps(
                    {
                        "condition": condition,
                        "seed": seed,
                        "max_iter": aggregate.CHECKPOINT_STEP,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            source_bytes = self._loss_bytes(condition)
            source = audit_dir / "pilot_loss_shares.csv"
            source.write_bytes(source_bytes)

            checkpoint = checkpoint_dir / "step_020000.pt"
            checkpoint_bytes = f"synthetic-{condition}-{seed}".encode("ascii")
            checkpoint.write_bytes(checkpoint_bytes)
            checkpoint_sha = digest(checkpoint_bytes)
            Path(f"{checkpoint}.sha256").write_text(
                f"{checkpoint_sha}  {checkpoint.name}\n", encoding="ascii"
            )

            output_path_text = str(run_dir.resolve())
            binding = {
                "training_config": digest(
                    f"training-{condition}-{seed}".encode("ascii")
                ),
                "effective_training_config": digest(
                    f"effective-{condition}-{seed}".encode("ascii")
                ),
                "output_path": digest(output_path_text.encode("utf-8")),
            }
            cursor_files = {
                path: {
                    "exists": False,
                    "size_bytes": 0,
                    "prefix_sha256": None,
                }
                for path in aggregate.EXPECTED_LOSS_PATHS
            }
            cursor_files[aggregate.LOSS_SHARE_RELATIVE_PATH] = {
                "exists": True,
                "size_bytes": len(source_bytes),
                "prefix_sha256": digest(source_bytes),
            }
            cursor = {
                "schema": aggregate.LOSS_CURSOR_SCHEMA,
                "completed_steps": aggregate.CHECKPOINT_STEP,
                "files": cursor_files,
            }
            payload = {
                "step_semantics": aggregate.STEP_SEMANTICS,
                "binding_sha256": binding,
                "learning_runs_started": 1,
                "loss_log_cursor": cursor,
            }
            self.loaded_by_path[checkpoint.resolve()] = SimpleNamespace(
                sha256=checkpoint_sha,
                completed_steps=aggregate.CHECKPOINT_STEP,
                payload=payload,
            )

            manifest = {
                "schema": aggregate.FULL_STATE_SCHEMA,
                "output_path": output_path_text,
                "config_path": str(config.resolve()),
                "config_file_sha256": aggregate.sha256_file(config),
                "binding_sha256": binding,
                "max_iter": aggregate.CHECKPOINT_STEP,
                "checkpoint_steps": list(aggregate.CHECKPOINT_STEPS),
                "step_semantics": aggregate.STEP_SEMANTICS,
                "loss_csv_paths": list(aggregate.EXPECTED_LOSS_PATHS),
                "last_completed_steps": aggregate.CHECKPOINT_STEP,
                "learning_runs_started": 1,
                "latest_full_checkpoint": {
                    "path": str(checkpoint.resolve()),
                    "sha256": checkpoint_sha,
                    "completed_steps": aggregate.CHECKPOINT_STEP,
                },
                "process_completed": True,
                "process_completed_steps": aggregate.CHECKPOINT_STEP,
            }
            (run_dir / "full_state_manifest.json").write_text(
                json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
            )

    def loader(self, path: Path, **kwargs):
        resolved = path.resolve()
        self.loader_calls.append((resolved, dict(kwargs)))
        loaded = self.loaded_by_path[resolved]
        self.assertEqual(kwargs.get("map_location"), "cpu")
        self.assertEqual(
            kwargs.get("expected_binding_sha256"),
            loaded.payload["binding_sha256"],
        )
        return loaded

    def run_aggregate(self):
        return aggregate.aggregate_loss_cursors(
            training_root=self.training_root,
            output_path=self.output,
            receipt_path=self.receipt,
            run_receipt_dir=self.run_receipts,
            loader=self.loader,
        )

    def _source(self, condition: str = "01", seed: int = 1001) -> Path:
        return (
            self.training_root
            / condition
            / f"seed_{seed}"
            / aggregate.LOSS_SHARE_RELATIVE_PATH
        )

    def _manifest(self, condition: str = "01", seed: int = 1001) -> Path:
        return (
            self.training_root
            / condition
            / f"seed_{seed}"
            / "full_state_manifest.json"
        )

    def test_output_fields_match_scoring_contract_without_importing_scorer(self) -> None:
        scoring_path = SCRIPT_DIR / "pilot_1wave_scoring.py"
        scoring_tree = ast.parse(scoring_path.read_text(encoding="utf-8"))
        scoring_fields = None
        for node in scoring_tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if any(
                isinstance(target, ast.Name) and target.id == "LOSS_SHARE_FIELDS"
                for target in node.targets
            ):
                scoring_fields = ast.literal_eval(node.value)
                break
        self.assertEqual(scoring_fields, aggregate.OUTPUT_FIELDS)

    def test_exact_ten_run_aggregate_receipts_ratio_and_idempotence(self) -> None:
        first = self.run_aggregate()
        self.assertEqual(first["state"], "published")
        self.assertEqual(first["aggregate_row_count"], 14_000)
        self.assertEqual(len(self.loader_calls), 10)

        with self.output.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        self.assertEqual(tuple(reader.fieldnames or ()), aggregate.OUTPUT_FIELDS)
        self.assertEqual(len(rows), 14_000)
        self.assertEqual(
            {(row["condition_id"], int(row["seed"])) for row in rows},
            set(aggregate.EXPECTED_RUN_KEYS),
        )
        self.assertTrue(all(int(row["checkpoint_step"]) == 20_000 for row in rows))

        aggregate_receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(aggregate_receipt["aggregate_row_count"], 14_000)
        self.assertEqual(len(aggregate_receipt["run_receipts"]), 10)
        receipt_paths = sorted(self.run_receipts.glob("*.json"))
        self.assertEqual(len(receipt_paths), 10)
        for path in receipt_paths:
            receipt = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["loss_share_source"]["row_count"], 1_400)
            self.assertEqual(receipt["loss_share_source"]["tail_bytes"], 0)
            if receipt["condition_id"] in {"04a", "04b"}:
                ratio = receipt["plane_photo_ratio_evidence"]
                self.assertTrue(ratio["applicable"])
                self.assertEqual(ratio["defined_iter_count"], 200)
                self.assertEqual(ratio["within_required_count"], 200)
                self.assertEqual(ratio["first_defined"]["plane_photo_ratio"], 1.0)

        mtimes = {
            path: path.stat().st_mtime_ns
            for path in [self.output, self.receipt, *receipt_paths]
        }
        self.loader_calls.clear()
        second = self.run_aggregate()
        self.assertEqual(second["state"], "already_present_identical")
        self.assertEqual(len(self.loader_calls), 10)
        self.assertEqual(
            mtimes,
            {path: path.stat().st_mtime_ns for path in mtimes},
        )

    def test_tail_prefix_and_truncation_fail_closed(self) -> None:
        source = self._source()
        original = source.read_bytes()

        source.write_bytes(original + b"20100,pho,1,1,1,1\n")
        with self.assertRaisesRegex(aggregate.AggregateError, "uncheckpointed tail"):
            self.run_aggregate()

        source.write_bytes(original)
        mutated = bytearray(original)
        index = mutated.index(b"0.25")
        mutated[index : index + 4] = b"0.35"
        source.write_bytes(mutated)
        with self.assertRaisesRegex(aggregate.AggregateError, "prefix SHA256"):
            self.run_aggregate()

        source.write_bytes(original[:-1])
        with self.assertRaisesRegex(aggregate.AggregateError, "shorter"):
            self.run_aggregate()

    def test_cursor_boundary_and_path_set_fail_closed(self) -> None:
        checkpoint = (
            self.training_root / "01/seed_1001/ckpt/step_020000.pt"
        ).resolve()
        loaded = self.loaded_by_path[checkpoint]
        record = loaded.payload["loss_log_cursor"]["files"][
            aggregate.LOSS_SHARE_RELATIVE_PATH
        ]
        source_bytes = self._source().read_bytes()
        record["size_bytes"] = len(source_bytes) - 1
        record["prefix_sha256"] = digest(source_bytes[:-1])
        self._source().write_bytes(source_bytes[:-1])
        with self.assertRaisesRegex(aggregate.AggregateError, "cuts through"):
            self.run_aggregate()

        self._source().write_bytes(source_bytes)
        record["size_bytes"] = len(source_bytes)
        record["prefix_sha256"] = digest(source_bytes)
        loaded.payload["loss_log_cursor"]["files"]["audit/injected.csv"] = {
            "exists": False,
            "size_bytes": 0,
            "prefix_sha256": None,
        }
        with self.assertRaisesRegex(aggregate.AggregateError, "loss path set"):
            self.run_aggregate()

    def test_sidecar_schedule_and_discovery_fail_closed(self) -> None:
        sidecar = self.training_root / "01/seed_1001/ckpt/step_020000.pt.sha256"
        sidecar.write_text("0" * 64 + "  step_020000.pt\n", encoding="ascii")
        with self.assertRaisesRegex(aggregate.AggregateError, "sidecar"):
            self.run_aggregate()

        checkpoint = self.training_root / "01/seed_1001/ckpt/step_020000.pt"
        checkpoint_sha = digest(checkpoint.read_bytes())
        sidecar.write_text(
            f"{checkpoint_sha}  step_020000.pt\n", encoding="ascii"
        )
        manifest_path = self._manifest()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["checkpoint_steps"] = [5000, 10000, 20000, 15000]
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(aggregate.AggregateError, "checkpoint schedule"):
            self.run_aggregate()

        manifest["checkpoint_steps"] = list(aggregate.CHECKPOINT_STEPS)
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        missing = self.training_root / "04b/seed_1002/full_state_manifest.json"
        missing.unlink()
        with self.assertRaisesRegex(aggregate.AggregateError, "discovery mismatch"):
            self.run_aggregate()

    def test_extra_run_and_nonidentical_output_fail_closed(self) -> None:
        extra = self.training_root / "05/seed_1001"
        extra.mkdir(parents=True)
        (extra / "full_state_manifest.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(aggregate.AggregateError, "discovery mismatch"):
            self.run_aggregate()

        (extra / "full_state_manifest.json").unlink()
        self.run_aggregate()
        self.output.write_bytes(b"changed\n")
        with self.assertRaisesRegex(aggregate.AggregateError, "non-identical"):
            self.run_aggregate()


if __name__ == "__main__":
    unittest.main()

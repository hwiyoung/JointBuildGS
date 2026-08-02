from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import src.evaluation.c1_c2_dev_gate_closure_v1.g2_runner as g2_runner
from src.evaluation.c1_c2_dev_gate_closure_v1.evaluator import (
    ClosureError,
    canonical_json_bytes,
    load_g2_receipts,
    sha256_bytes,
)


IMAGE_ID = "sha256:pinned-image"
VALID_STDOUT = b'"1st-line" []\n"feature-1" []\n'
INVALID_STDOUT = b'"1st-line" []\n"feature-1" [302]\n'
CITYJSONSEQ = b'{"type":"CityJSON"}\n{"type":"CityJSONFeature","id":"feature-1"}\n'


def _config() -> dict:
    return {
        "task_id": "G2-R2-TEST",
        "inputs": {"source_manifest": {"path": "manifest.json"}},
        "gates": {
            "G2": {
                "validator": "val3dity",
                "version": "2.6.0",
                "container_image_ref": "val3dity:test",
                "container_image_id": IMAGE_ID,
                "input_mode": "CITYJSONSEQ_STDIN_PIPE",
                "command": ["val3dity", "stdin"],
                "expected_unique_c2_units": 6,
            }
        },
    }


def _records() -> list[dict]:
    return [
        {
            "path": f"operations/C2_MVS/COMP_{index}/work/out/tile.jsonl",
            "bytes": len(CITYJSONSEQ),
            "sha256": sha256_bytes(CITYJSONSEQ),
        }
        for index in range(6)
    ]


class _ProcessRunner:
    def __init__(self, outcomes: list[tuple[int, bytes, bytes]]):
        self.outcomes = list(outcomes)
        self.validator_calls = 0

    def __call__(self, command, **kwargs):
        if command[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, (IMAGE_ID + "\n").encode(), b"")
        self.validator_calls += 1
        if not self.outcomes:
            raise AssertionError("unexpected validator invocation")
        exit_code, stdout, stderr = self.outcomes.pop(0)
        return subprocess.CompletedProcess(command, exit_code, stdout, stderr)


class G2RunnerR2Tests(unittest.TestCase):
    def _run(
        self,
        directory: str,
        outcomes: list[tuple[int, bytes, bytes]],
        *,
        source_reader=None,
    ):
        config = _config()
        records = _records()
        manifest = canonical_json_bytes({"records": records})
        runner = _ProcessRunner(outcomes)
        output = Path(directory) / "g2.json"
        progress = Path(directory) / "progress"
        reader = source_reader or Mock(return_value=CITYJSONSEQ)
        with (
            patch.object(g2_runner, "load_config", return_value=config),
            patch.object(g2_runner, "_read_bound_file", return_value=manifest),
            patch.object(g2_runner, "_read_source_record", reader),
        ):
            result = g2_runner.run_g2(
                Path("sealed"),
                output,
                process_runner=runner,
                progress_dir=progress,
            )
        return result, runner, reader, output, progress, config, records

    def test_exit_zero_accepts_valid_and_invalid_geometry(self):
        for stdout, expected_class, expected_valid in (
            (VALID_STDOUT, "VALIDATION_COMPLETED_EXIT_0_VALID", True),
            (INVALID_STDOUT, "VALIDATION_COMPLETED_EXIT_0_INVALID_GEOMETRY", False),
        ):
            with self.subTest(expected_class=expected_class), tempfile.TemporaryDirectory() as directory:
                result, runner, reader, _, _, _, _ = self._run(
                    directory,
                    [(0, stdout, b"")] * 6,
                )
                self.assertEqual(runner.validator_calls, 6)
                self.assertEqual(reader.call_count, 6)
                self.assertEqual(result["unit_count"], 6)
                self.assertTrue(all(unit["result"]["unit_valid"] is expected_valid for unit in result["units"]))
                self.assertTrue(all(unit["runtime_exit_anomaly"] is False for unit in result["units"]))
                self.assertTrue(all(unit["completion_class"] == expected_class for unit in result["units"]))

    def test_exit_one_is_accepted_only_for_complete_invalid_result_and_consumer_revalidates_it(self):
        with tempfile.TemporaryDirectory() as directory:
            result, _, _, output, _, config, records = self._run(
                directory,
                [(1, INVALID_STDOUT, b"geometry invalid\n")] * 6,
            )
            self.assertTrue(all(unit["runtime_exit_anomaly"] is True for unit in result["units"]))
            self.assertTrue(
                all(
                    unit["completion_class"] == "VALIDATION_COMPLETED_EXIT_1_INVALID_GEOMETRY"
                    for unit in result["units"]
                )
            )
            loaded = load_g2_receipts(
                output,
                config,
                {record["path"]: record for record in records},
            )
            self.assertEqual(len(loaded), 6)

    def test_unexplained_or_process_failure_exit_is_rejected(self):
        for exit_code, stdout, message in (
            (1, VALID_STDOUT, "unexplained"),
            (2, VALID_STDOUT, "not an accepted"),
            (-9, VALID_STDOUT, "not an accepted"),
        ):
            with self.subTest(exit_code=exit_code), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ClosureError, message):
                    self._run(directory, [(exit_code, stdout, b"")])
                self.assertFalse((Path(directory) / "g2.json").exists())

    def test_stdout_contract_is_parsed_before_exit_handling(self):
        cases = (
            (b'"1st-line" []\n"wrong-id" [302]\n', "feature order or syntax"),
            (b'"1st-line" [101]\n"feature-1" [302]\n', "metadata record"),
            (b"not-json\n", "line count differs"),
        )
        for stdout, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ClosureError, message):
                    self._run(directory, [(2, stdout, b"")])

    def test_failure_preserves_completed_units_and_retry_reuses_them_without_source_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            first_reader = Mock(return_value=CITYJSONSEQ)
            with self.assertRaisesRegex(ClosureError, "not an accepted"):
                self._run(
                    directory,
                    [
                        (0, VALID_STDOUT, b""),
                        (1, INVALID_STDOUT, b"invalid\n"),
                        (2, VALID_STDOUT, b"crash\n"),
                    ],
                    source_reader=first_reader,
                )
            progress = Path(directory) / "progress"
            self.assertEqual(len(list(progress.glob("*.json"))), 2)
            self.assertEqual(first_reader.call_count, 3)
            second_reader = Mock(return_value=CITYJSONSEQ)
            result, runner, _, output, _, _, _ = self._run(
                directory,
                [(0, VALID_STDOUT, b"")] * 4,
                source_reader=second_reader,
            )
            self.assertTrue(output.is_file())
            self.assertEqual(second_reader.call_count, 4)
            self.assertEqual(runner.validator_calls, 4)
            self.assertEqual(
                result["resumption"],
                {
                    "reused_exact_unit_receipts": 2,
                    "new_source_reads_and_hashes": 4,
                    "new_validator_invocations": 4,
                },
            )
            self.assertTrue(result["units"][1]["runtime_exit_anomaly"])

    def test_tampered_progress_receipt_fails_before_source_read_or_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ClosureError):
                self._run(directory, [(0, VALID_STDOUT, b""), (2, VALID_STDOUT, b"")])
            receipt_path = sorted((Path(directory) / "progress").glob("*.json"))[0]
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["unit"]["stdout"]["text"] = receipt["unit"]["stdout"]["text"].replace("[]", "[302]", 1)
            receipt_path.write_bytes(canonical_json_bytes(receipt))
            reader = Mock(return_value=CITYJSONSEQ)
            with self.assertRaisesRegex(ClosureError, "byte identity differs"):
                self._run(directory, [], source_reader=reader)
            reader.assert_not_called()

    def test_all_existing_progress_is_verified_before_any_missing_unit_work(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ClosureError):
                self._run(directory, [(0, VALID_STDOUT, b""), (0, VALID_STDOUT, b""), (2, VALID_STDOUT, b"")])
            receipt_paths = sorted((Path(directory) / "progress").glob("*.json"))
            self.assertEqual(len(receipt_paths), 2)
            receipt_paths[0].unlink()
            later_receipt = json.loads(receipt_paths[1].read_text(encoding="utf-8"))
            later_receipt["unit"]["stdout"]["sha256"] = "0" * 64
            receipt_paths[1].write_bytes(canonical_json_bytes(later_receipt))
            reader = Mock(return_value=CITYJSONSEQ)
            with self.assertRaisesRegex(ClosureError, "byte identity differs"):
                self._run(directory, [], source_reader=reader)
            reader.assert_not_called()

    def test_unexpected_or_nonregular_progress_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            progress = Path(directory) / "progress"
            progress.mkdir()
            (progress / "unexpected.json").write_text("{}\n", encoding="utf-8")
            reader = Mock(return_value=CITYJSONSEQ)
            with self.assertRaisesRegex(ClosureError, "unexpected G2 progress entry"):
                self._run(directory, [], source_reader=reader)
            reader.assert_not_called()

    def test_add_once_publication_does_not_replace_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "receipt.json"
            target.write_bytes(b"original")
            with self.assertRaisesRegex(ClosureError, "already exists"):
                g2_runner._publish_add_once(target, b"replacement")
            self.assertEqual(target.read_bytes(), b"original")

    def test_cli_accepts_explicit_progress_directory(self):
        args = g2_runner.parse_args(
            [
                "--source-root", "sealed",
                "--output", "g2.json",
                "--progress-dir", "progress",
            ]
        )
        self.assertEqual(args.progress_dir, Path("progress"))

    def test_consumer_rejects_wrong_task_prohibited_counters_and_boolean_exit(self):
        mutations = (
            ("task_id", lambda receipt: receipt.__setitem__("task_id", "OTHER-TASK"), "authority differs"),
            (
                "reconstruction_invocation_count",
                lambda receipt: receipt.__setitem__("reconstruction_invocation_count", 1),
                "authority differs",
            ),
            (
                "roofer_invocation_count",
                lambda receipt: receipt.__setitem__("roofer_invocation_count", 1),
                "authority differs",
            ),
            (
                "validation_access_count",
                lambda receipt: receipt.__setitem__("validation_access_count", 1),
                "authority differs",
            ),
            (
                "held_out_access_count",
                lambda receipt: receipt.__setitem__("held_out_access_count", 1),
                "authority differs",
            ),
            (
                "boolean_exit",
                lambda receipt: receipt["units"][0].__setitem__("process_exit_code", False),
                "exit code is malformed",
            ),
        )
        for label, mutate, message in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                _, _, _, output, _, config, records = self._run(
                    directory,
                    [(0, VALID_STDOUT, b"")] * 6,
                )
                receipt = json.loads(output.read_text(encoding="utf-8"))
                mutate(receipt)
                output.write_bytes(canonical_json_bytes(receipt))
                with self.assertRaisesRegex(ClosureError, message):
                    load_g2_receipts(
                        output,
                        config,
                        {record["path"]: record for record in records},
                    )


if __name__ == "__main__":
    unittest.main()

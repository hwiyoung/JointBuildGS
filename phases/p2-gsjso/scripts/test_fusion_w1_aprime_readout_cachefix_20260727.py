#!/usr/bin/env python3
"""Regression tests for the generic A-prime readout cachefix adapter."""
from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1_aprime_readout_cachefix_20260727.json"
)
BASE_CONFIG_PATH = (
    REPO / "phases/p2-gsjso/configs/fusion_w1_aprime_readout_20260726.json"
)
HELPER_PATH = (
    REPO / "phases/p2-gsjso/scripts/fusion_w1_aprime_readout_cachefix_20260727.py"
)
WRAPPER_PATH = (
    REPO / "phases/p2-gsjso/scripts/run_fusion_w1_aprime_readout_cachefix_20260727.sh"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("aprime_readout_cachefix_tested", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import cachefix helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cachefix = load_module()


class ConfigAndWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cls.base = json.loads(BASE_CONFIG_PATH.read_text(encoding="utf-8"))
        cls.wrapper = WRAPPER_PATH.read_text(encoding="utf-8")

    def test_locked_base_hashes_and_continuation_lock(self) -> None:
        contract = self.config["cachefix_contract"]
        for key in ("base_readout_config", "base_readout_driver", "continuation_lock"):
            record = contract[key]
            path = REPO / record["path"]
            self.assertEqual(sha256(path), record["sha256"])
            self.assertEqual(path.stat().st_size, record["bytes"])
        lock = json.loads(
            (REPO / contract["continuation_lock"]["path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(lock["state"], "LOCKED_BEFORE_REMAINING_JOB_START")
        self.assertEqual(lock["scope"]["remaining_jobs"], 20)
        self.assertEqual(lock["scope"]["physical_gpu"], 1)

    def test_scientific_readout_contract_is_unchanged(self) -> None:
        for key in (
            "schema",
            "run_id",
            "branch",
            "locked_inputs",
            "identity_contract",
            "primary",
            "legacy_alpha_comparison",
            "roofer",
            "containers",
            "retry_contract",
            "publication",
        ):
            self.assertEqual(self.config[key], self.base[key], key)
        expected_outputs = dict(self.base["outputs"])
        expected_outputs["runtime_environment"] = (
            "phases/p2-gsjso/runs/20260726_fusion_w1_aprime/runtime_env"
        )
        self.assertEqual(self.config["outputs"], expected_outputs)
        self.assertEqual(self.config["outputs"]["root"], self.base["outputs"]["root"])

    def test_config_validates_without_git_runtime_gate(self) -> None:
        loaded = cachefix.load_config(CONFIG_PATH)
        self.assertEqual(loaded["task_id"], "FUS-W1-APRIME-READOUT-CACHEFIX-001")
        self.assertTrue(loaded["cachefix_contract"]["reuse_only"])
        self.assertFalse(loaded["cachefix_contract"]["compilation_allowed"])

    def test_historical_readout_contract_is_closed_and_awaits_recovery_lock(self) -> None:
        contract = self.config["historical_training_readout_reuse_contract"]
        self.assertTrue(contract["enabled"])
        self.assertTrue(contract["strict_current_head_default"])
        self.assertEqual(
            contract["producer_head"],
            "191b5652be6d38a81a3cba7ab05cd3db4ffbe796",
        )
        self.assertEqual(
            contract["allowed_jobs"],
            [
                {"building_id": "DEBY_LOD2_42364663", "arm": "Aprime", "replicate": "r1", "profile": "full"},
                {"building_id": "DEBY_LOD2_4907182", "arm": "Aprime", "replicate": "r1", "profile": "full"},
                {"building_id": "DEBY_LOD2_4907510", "arm": "Aprime", "replicate": "r1", "profile": "full"},
                {"building_id": "DEBY_LOD2_4908050", "arm": "Aprime", "replicate": "r1", "profile": "full"},
            ],
        )
        self.assertEqual(contract["completed_optimizer_updates"], 30000)
        self.assertTrue(contract["producer_head_must_be_ancestor"])
        self.assertTrue(contract["method_files_must_be_current_identical"])
        recovery = contract["recovery_lock"]
        path = REPO / recovery["path"]
        self.assertEqual(recovery["sha256"], sha256(path))
        self.assertEqual(recovery["bytes"], path.stat().st_size)

    def test_cachefix_outputs_are_under_locked_continuation(self) -> None:
        contract = self.config["cachefix_contract"]
        root = Path(contract["continuation_root"])
        self.assertEqual(Path(contract["continuation_lock"]["path"]).parent, root)
        for key in ("cache_probe_receipt", "ephemeral_lock_quarantine"):
            Path(contract[key]).relative_to(root)
        self.assertNotEqual(root, Path(self.config["outputs"]["root"]))

    def test_wrapper_sets_exact_nonroot_cache_environment_on_gpu1(self) -> None:
        self.assertIn('GPU_INDEX="${APRIME_READOUT_CACHEFIX_GPU_INDEX:-1}"', self.wrapper)
        self.assertIn('[[ "$GPU_INDEX" == "1" ]]', self.wrapper)
        self.assertIn('--user "$HOST_UID:$HOST_GID"', self.wrapper)
        self.assertIn(
            '--env "HOME=/workspace/JointBuildGS/$RUNTIME_REL/home"', self.wrapper
        )
        self.assertIn(
            '--env "XDG_CACHE_HOME=/workspace/JointBuildGS/$RUNTIME_REL/xdg_cache"',
            self.wrapper,
        )
        self.assertIn(
            '--env "TORCH_EXTENSIONS_DIR=/workspace/JointBuildGS/$RUNTIME_REL/torch_extensions"',
            self.wrapper,
        )
        self.assertIn("--env MAX_JOBS=2", self.wrapper)

    def test_wrapper_rejects_non_gpu1_override_before_docker(self) -> None:
        environment = os.environ.copy()
        environment["APRIME_READOUT_CACHEFIX_GPU_INDEX"] = "0"
        process = subprocess.run(
            ["bash", str(WRAPPER_PATH), "cache-check"],
            cwd=REPO,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(process.returncode, 64)
        self.assertIn("locked to physical GPU 1", process.stderr)
        self.assertIn("APRIME_READOUT_CACHEFIX_GPU_INDEX=0", process.stderr)
        self.assertNotIn("docker:", process.stderr.lower())

    def test_wrapper_uses_base_driver_and_orders_hygiene_before_finalize(self) -> None:
        self.assertIn(
            'BASE_DRIVER="phases/p2-gsjso/scripts/fusion_w1_aprime_readout_20260726.py"',
            self.wrapper,
        )
        run_one = self.wrapper[self.wrapper.index("run_one() {") : self.wrapper.index("verify_images\n")]
        self.assertLess(run_one.index('CURRENT_STAGE="cache_probe"'), run_one.index('CURRENT_STAGE="begin_attempt"'))
        self.assertLess(run_one.index('CURRENT_STAGE="finalize_hygiene"'), run_one.index('CURRENT_STAGE="finalize"'))
        self.assertIn('run_tools "${argv[@]}" >"$attempt_rel/legacy_alpha/classification.stdout.log"', run_one)
        self.assertNotIn("TRAINING_WRAPPER", self.wrapper)
        self.assertNotIn(" materialize ", self.wrapper)

    def signal_harness(
        self, signal_name: str, status: int, *, preexisting: str | None = None
    ) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        definitions = self.wrapper[: self.wrapper.index("\nverify_images\n")]
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            attempt = (
                root
                / "by_building/DEBY_LOD2_42364659/arm_Aprime/r1/attempts/attempt_001"
            )
            attempt.mkdir(parents=True)
            if preexisting == "failure":
                (attempt / "failure.json").write_text('{"state":"FAILED"}\n', encoding="utf-8")
            elif preexisting == "complete":
                complete = root / "by_building/DEBY_LOD2_42364659/arm_Aprime/r1/complete.json"
                complete.write_text('{"state":"COMPLETE"}\n', encoding="utf-8")
            calls = root / "calls.txt"
            harness = f"""
READOUT_ROOT={str(root)!r}
BUILDING_ID=DEBY_LOD2_42364659
ARM=Aprime
REPLICATE=r1
ACTIVE_ATTEMPT=1
ACTIVE_FAILURE_CLOSED=false
CURRENT_STAGE=primary_tsdf
base_tools() {{
  printf '%s\\n' "$*" >> {str(calls)!r}
  printf '%s\\n' '{{"state":"FAILED"}}' > {str(attempt / 'failure.json')!r}
}}
handle_wrapper_signal {signal_name} {status}
"""
            process = subprocess.run(
                ["bash"],
                cwd=REPO,
                input=definitions + harness,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            rows = calls.read_text(encoding="utf-8").splitlines() if calls.is_file() else []
        return process, rows

    def test_term_and_int_close_active_attempt_once_with_stable_signal_failure(self) -> None:
        for signal_name, status in (("TERM", 143), ("INT", 130)):
            with self.subTest(signal_name=signal_name):
                process, calls = self.signal_harness(signal_name, status)
                self.assertEqual(process.returncode, status)
                self.assertEqual(len(calls), 1)
                self.assertIn("record-failure", calls[0])
                self.assertIn("--attempt 1", calls[0])
                self.assertIn("--stage primary_tsdf", calls[0])
                self.assertIn("--error-type ExternalSignal", calls[0])
                self.assertIn(f"--message cache-fixed wrapper interrupted by {signal_name}", calls[0])

    def test_signal_handler_does_not_duplicate_existing_failure(self) -> None:
        process, calls = self.signal_harness("TERM", 143, preexisting="failure")
        self.assertEqual(process.returncode, 143)
        self.assertEqual(calls, [])
        self.assertIn("already has a failure receipt", process.stderr)

    def test_signal_handler_does_not_contradict_authoritative_complete(self) -> None:
        process, calls = self.signal_harness("TERM", 143, preexisting="complete")
        self.assertEqual(process.returncode, 143)
        self.assertEqual(calls, [])
        self.assertIn("authoritative readout complete already exists", process.stderr)

    def test_production_one_command_installs_err_term_and_int_handlers(self) -> None:
        one_case = self.wrapper[self.wrapper.index("  one)\n") :]
        self.assertIn("trap 'handle_wrapper_error \"$?\"' ERR", one_case)
        self.assertIn("trap 'handle_wrapper_signal TERM 143' TERM", one_case)
        self.assertIn("trap 'handle_wrapper_signal INT 130' INT", one_case)
        self.assertIn("trap - ERR TERM INT", one_case)


class CacheTreeTests(unittest.TestCase):
    def test_tree_ledger_detects_file_and_directory_changes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "gsplat_cuda.so").write_bytes(b"binary")
            before = cachefix.tree_ledger(root)
            (root / "nested").mkdir()
            after_directory = cachefix.tree_ledger(root)
            self.assertNotEqual(before, after_directory)
            (root / "nested/new.o").write_bytes(b"object")
            after_file = cachefix.tree_ledger(root)
            self.assertNotEqual(after_directory, after_file)

    def test_tree_ledger_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "target").write_bytes(b"data")
            (root / "link").symlink_to(root / "target")
            with self.assertRaises(cachefix.ReadoutCachefixError):
                cachefix.tree_ledger(root)


class QuarantineTests(unittest.TestCase):
    def make_attempt(
        self,
        root: Path,
        *,
        legacy_state: str = "NOT_ASSEMBLED",
        extra_zero: bool = False,
    ) -> tuple[Path, dict[str, object], object]:
        attempt = root / "canonical/readout/attempts/attempt_001"
        (attempt / "primary/engine").mkdir(parents=True)
        (attempt / "legacy_alpha/engine").mkdir(parents=True)
        (attempt / "attempt.json").write_text('{"state":"STARTED"}\n', encoding="utf-8")
        (attempt / "primary/score.json").write_text(
            '{"state":"MEASURED"}\n', encoding="utf-8"
        )
        (attempt / "legacy_alpha/score.json").write_text(
            json.dumps({"state": legacy_state}) + "\n", encoding="utf-8"
        )
        (attempt / "primary/engine/model.city.json").write_text(
            '{"type":"CityJSON"}\n', encoding="utf-8"
        )
        (attempt / "primary/engine/scores.csv.lock").touch()
        if legacy_state == "MEASURED":
            (attempt / "legacy_alpha/engine/model.city.json").write_text(
                '{"type":"CityJSON"}\n', encoding="utf-8"
            )
            (attempt / "legacy_alpha/engine/scores.csv.lock").touch()
        if extra_zero:
            (attempt / "unrelated.empty").touch()

        config: dict[str, object] = {
            "run_id": "20260726_fusion_w1_aprime",
            "task_id": "FUS-W1-APRIME-READOUT-CACHEFIX-001",
            "cachefix_contract": {
                "base_readout_driver": {
                    "path": "unused.py",
                    "sha256": "unused",
                    "bytes": 1,
                },
                "allowed_lock_relative_paths": [
                    "primary/engine/scores.csv.lock",
                    "legacy_alpha/engine/scores.csv.lock",
                ],
                "ephemeral_lock_quarantine": "continuation/readout_cachefix/quarantine",
            },
        }

        class FakeBase:
            @staticmethod
            def load_config(_path: Path) -> dict[str, object]:
                return {}

            @staticmethod
            def load_attempt(
                _config: dict[str, object],
                _building_id: str,
                _arm: str,
                _run: str,
                _attempt: int,
            ) -> tuple[Path, dict[str, object]]:
                return attempt, {}

            @staticmethod
            def job_dir(
                _config: dict[str, object], _building_id: str, _arm: str, _run: str
            ) -> Path:
                return root / "canonical/readout/job"

        return attempt, config, FakeBase()

    def run_quarantine(
        self, root: Path, config: dict[str, object], fake_base: object
    ) -> dict[str, object]:
        with (
            mock.patch.object(cachefix, "REPO", root),
            mock.patch.object(cachefix, "DEFAULT_CONFIG", root / "derived.json"),
            mock.patch.object(cachefix, "load_base_driver", return_value=fake_base),
            mock.patch.object(cachefix, "git", return_value="a" * 40),
        ):
            return cachefix.quarantine_ephemeral_locks(
                config, "DEBY_LOD2_42364659", "Aprime", "r1", 1
            )

    def test_moves_only_primary_lock_for_not_assembled_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            attempt, config, fake_base = self.make_attempt(root)
            payload = self.run_quarantine(root, config, fake_base)
            self.assertFalse((attempt / "primary/engine/scores.csv.lock").exists())
            destination = (
                root
                / "continuation/readout_cachefix/quarantine/by_building"
                / "DEBY_LOD2_42364659/arm_Aprime/r1/attempt_001"
                / "primary/engine/scores.csv.lock"
            )
            self.assertTrue(destination.is_file())
            self.assertEqual(destination.stat().st_size, 0)
            self.assertEqual(payload["moved_ephemeral_lock_count"], 1)
            self.assertFalse(payload["scientific_artifacts_moved"])
            self.assertEqual(payload["scientific_artifact_move_count"], 0)
            self.assertEqual(payload["new_training_runs_started"], 0)
            self.assertGreater((attempt / "finalize_hygiene.json").stat().st_size, 0)

    def test_measured_legacy_requires_and_moves_two_locks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            attempt, config, fake_base = self.make_attempt(root, legacy_state="MEASURED")
            payload = self.run_quarantine(root, config, fake_base)
            self.assertEqual(payload["moved_ephemeral_lock_count"], 2)
            self.assertEqual(list(attempt.rglob("scores.csv.lock")), [])
            self.assertEqual(
                {row["source_relative_to_attempt"] for row in payload["moved_ephemeral_locks"]},
                {
                    "primary/engine/scores.csv.lock",
                    "legacy_alpha/engine/scores.csv.lock",
                },
            )

    def test_rejects_unrelated_zero_byte_file_without_moving_lock(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            attempt, config, fake_base = self.make_attempt(root, extra_zero=True)
            with self.assertRaises(cachefix.ReadoutCachefixError):
                self.run_quarantine(root, config, fake_base)
            self.assertTrue((attempt / "primary/engine/scores.csv.lock").exists())
            self.assertFalse((attempt / "finalize_hygiene.json").exists())

    def test_rejects_lock_still_held_by_scorer(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            attempt, config, fake_base = self.make_attempt(root)
            lock_path = attempt / "primary/engine/scores.csv.lock"
            with lock_path.open("r+b") as stream:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(cachefix.ReadoutCachefixError):
                    self.run_quarantine(root, config, fake_base)
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            self.assertTrue(lock_path.exists())


if __name__ == "__main__":
    unittest.main()

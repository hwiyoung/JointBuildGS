#!/usr/bin/env python3
"""Unit/contract tests for the FUS-W1 Gate A lock1 runtime guard."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_alignment_runtime_guard_lock1.py"
)
SPEC = importlib.util.spec_from_file_location(
    "fusion_w1_alignment_runtime_guard", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)

CONFIG_PATH = (
    REPO / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_alignment_gate_lock1.json"
)
WRAPPER_PATH = (
    REPO / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_alignment_gate_lock1.sh"
)


def completed(
    stdout: str = "",
    returncode: int = 0,
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["fixture"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class FusionW1AlignmentRuntimeGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        baseline_path = REPO / cls.config["execution_guard"][
            "immutable_baseline_receipt"
        ]
        status_path = REPO / cls.config["execution_guard"][
            "immutable_baseline_status"
        ]
        cls.baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        cls.status = json.loads(status_path.read_text(encoding="utf-8"))

    def test_wrapper_locks_exact_cpu_tools_runtime(self) -> None:
        text = WRAPPER_PATH.read_text(encoding="utf-8")
        required = (
            'TOOLS_IMAGE_ID="sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"',
            "--pid=host",
            "--network=none",
            "--read-only",
            "--memory=24g",
            "--memory-swap=24g",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--env MPLCONFIGDIR=/tmp/matplotlib",
            "--env CUDA_VISIBLE_DEVICES=",
            "--env NVIDIA_VISIBLE_DEVICES=void",
            "/var/run/docker.sock:/var/run/docker.sock:ro",
            "/usr/bin/docker:/usr/local/bin/docker:ro",
            "${HOST_REPO}:/workspace/JointBuildGS:rw",
            "${HOST_REPO}:/host-control/JointBuildGS:ro",
        )
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, text)
        self.assertNotIn("--gpus", text)
        self.assertIn(
            "fusion_w1_alignment_runtime_guard_lock1.py", text
        )

    def test_locked_immutable_receipts_are_5_of_5_and_gate_required(self) -> None:
        evidence = guard.validate_immutable_preflight(self.config)
        self.assertEqual(evidence["receipt"]["five_pin_passed_or_caveated_count"], 5)
        self.assertEqual(evidence["status_receipt"]["five_pin"], "5/5")
        self.assertTrue(
            evidence["status_receipt"]["learning_still_gated_by_gate_a"]
        )
        self.assertFalse(
            evidence["receipt"]["learning_entry_authorized"]
        )

    def test_immutable_receipt_hash_drift_fails_closed(self) -> None:
        drift = copy.deepcopy(self.config)
        drift["execution_guard"][
            "immutable_baseline_receipt_sha256"
        ] = "0" * 64
        with self.assertRaisesRegex(
            guard.RuntimeGuardError, "receipt SHA-256 mismatch"
        ):
            guard.validate_immutable_preflight(drift)

    def test_status_must_keep_continuation_and_gate_a(self) -> None:
        drift = copy.deepcopy(self.status)
        drift["learning_still_gated_by_gate_a"] = False
        config = copy.deepcopy(self.config)
        with mock.patch.object(
            guard,
            "load_json",
            side_effect=[self.baseline, drift],
        ):
            with self.assertRaisesRegex(
                guard.RuntimeGuardError,
                "learning_still_gated_by_gate_a",
            ):
                guard.validate_immutable_preflight(config)

    def test_git_provenance_requires_clean_tracked_and_committed_files(
        self,
    ) -> None:
        config = copy.deepcopy(self.config)
        paths = guard._implementation_paths(config)
        fake_head = "a" * 40
        blobs = {path: f"blob:{path}\n".encode() for path in paths}
        with tempfile.TemporaryDirectory(
            prefix="fusion_w1_guard_git."
        ) as temporary:
            fixture = Path(temporary)
            for relative, payload in blobs.items():
                path = fixture / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)

            status_output = [""]

            def fake_git(*args: str, check: bool = True):
                if args == ("branch", "--show-current"):
                    return completed("exp/fusion-w1\n")
                if args == ("rev-parse", "HEAD"):
                    return completed(fake_head + "\n")
                if args[:2] == ("cat-file", "-t"):
                    return completed("commit\n")
                if args[:2] == ("merge-base", "--is-ancestor"):
                    return completed()
                if args[:2] == ("status", "--porcelain=v1"):
                    return completed(status_output[0])
                raise AssertionError(f"unexpected git call: {args}")

            def fake_git_bytes(*args: str, check: bool = True):
                self.assertEqual(args[0], "show")
                relative = args[1].split(":", 1)[1]
                return subprocess.CompletedProcess(
                    args=["fixture"],
                    returncode=0,
                    stdout=blobs[relative],
                    stderr=b"",
                )

            with (
                mock.patch.object(guard, "REPO_ROOT", fixture),
                mock.patch.object(guard, "git", side_effect=fake_git),
                mock.patch.object(
                    guard, "git_bytes", side_effect=fake_git_bytes
                ),
            ):
                evidence = guard.validate_git_provenance(
                    config,
                    dispatch_commit="b" * 40,
                    amendment_commit="c" * 40,
                )
                self.assertTrue(
                    evidence[
                        "implementation_all_committed_and_head_match"
                    ]
                )
                status_output[0] = " M src/stage2/train.py\n"
                with self.assertRaisesRegex(
                    guard.RuntimeGuardError,
                    "tracked worktree/index is not clean",
                ):
                    guard.validate_git_provenance(
                        config,
                        dispatch_commit="b" * 40,
                        amendment_commit="c" * 40,
                    )

    def test_training_image_aggregate_matches_preflight_algorithm(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="fusion_w1_guard_images."
        ) as temporary:
            root = Path(temporary)
            logical = root / "images"
            logical.mkdir()
            (logical / "b.JPG").write_bytes(b"B")
            (logical / "a.JPG").write_bytes(b"A")
            with mock.patch.object(guard, "REPO_ROOT", root):
                observed, count, total = (
                    guard.sha256sum_stream_aggregate(logical)
                )
            expected_stream = b""
            for name, value in (("a.JPG", b"A"), ("b.JPG", b"B")):
                digest = hashlib.sha256(value).hexdigest()
                expected_stream += (
                    f"{digest}  images/{name}\n".encode("utf-8")
                )
            self.assertEqual(
                observed, hashlib.sha256(expected_stream).hexdigest()
            )
            self.assertEqual(count, 2)
            self.assertEqual(total, 2)

    def test_training_image_aggregate_preserves_locked_symlink_path(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="fusion_w1_guard_symlink_images."
        ) as temporary:
            root = Path(temporary)
            physical = root / "physical" / "images"
            physical.mkdir(parents=True)
            (physical / "a.JPG").write_bytes(b"A")
            logical_parent = root / "logical"
            logical_parent.mkdir()
            (logical_parent / "images").symlink_to(physical)
            with mock.patch.object(guard, "REPO_ROOT", root):
                resolved = guard.repo_path("logical/images")
                observed, count, total = guard.sha256sum_stream_aggregate(
                    resolved,
                    logical_prefix="logical/images",
                )
            digest = hashlib.sha256(b"A").hexdigest()
            expected = hashlib.sha256(
                f"{digest}  logical/images/a.JPG\n".encode("utf-8")
            ).hexdigest()
            self.assertEqual(observed, expected)
            self.assertEqual(count, 1)
            self.assertEqual(total, 1)

    def test_process_scan_finds_training_and_ignores_guard(self) -> None:
        patterns = self.config["execution_guard"][
            "local_namespace_forbidden_command_regexes"
        ]
        commands = {
            91001: "python src/stage2/train.py --config locked.yaml",
            91002: (
                "python phases/p2-gsjso/scripts/"
                "fusion_w1_alignment_runtime_guard_lock1.py launch"
            ),
        }
        with (
            mock.patch.object(guard.os, "getpid", return_value=99991),
            mock.patch.object(guard.os, "getppid", return_value=99992),
            mock.patch.object(
                guard,
                "process_command",
                side_effect=lambda pid: commands[pid],
            ),
        ):
            rows = guard.scan_processes(patterns, pids=commands)
        self.assertEqual([row["pid"] for row in rows], [91001])

    def test_unknown_gpu_is_downstream_block_but_cpu_gate_can_continue(
        self,
    ) -> None:
        docker_ps = json.dumps(
            {
                "ID": "abc",
                "Names": "jointbuildgs-dev",
                "Image": "jointbuildgs:dev",
                "Command": "sleep infinity",
                "Labels": "com.docker.compose.project=jointbuildgs",
                "State": "running",
                "Status": "Up",
            }
        )

        def fake_run(command, **kwargs):
            if command[:2] == ["docker", "ps"]:
                return completed(docker_ps + "\n")
            raise AssertionError(f"unexpected command: {command}")

        gpu = {
            "source": "fixture",
            "argv": ["nvidia-smi"],
            "returncode": 0,
            "stdout": "424242, python, 330\n",
            "stderr": "",
            "probe_container_used_gpu_visibility": False,
        }
        with (
            mock.patch.object(guard, "scan_processes", return_value=[]),
            mock.patch.object(guard, "run", side_effect=fake_run),
            mock.patch.object(
                guard, "_gpu_compute_probe", return_value=gpu
            ),
            mock.patch.object(
                guard, "process_command", return_value="unknown.py"
            ),
            mock.patch.object(
                Path,
                "read_text",
                return_value="Name:\tpython\nNSpid:\t101\n",
            ),
        ):
            result = guard.fresh_execution_probe(
                self.config, self.baseline
            )
        self.assertEqual(result["status"], "passed_with_caveat")
        evidence = result["evidence"]
        self.assertTrue(evidence["cpu_gate_authorized"])
        self.assertTrue(evidence["downstream_gpu_stage_launch_blocked"])
        self.assertEqual(
            evidence["unknown_gpu_compute_processes"][0]["pid"], 424242
        )

    def test_known_training_process_blocks_gate(self) -> None:
        with (
            mock.patch.object(
                guard,
                "scan_processes",
                return_value=[
                    {
                        "pid": 42,
                        "command": "python src/stage2/train.py",
                        "matched_regexes": ["train"],
                    }
                ],
            ),
            mock.patch.object(
                guard,
                "run",
                return_value=completed(""),
            ),
            mock.patch.object(
                guard,
                "_gpu_compute_probe",
                return_value={
                    "source": "fixture",
                    "argv": ["nvidia-smi"],
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "no device",
                    "probe_container_used_gpu_visibility": False,
                },
            ),
            mock.patch.object(
                Path,
                "read_text",
                return_value="NSpid:\t101\n",
            ),
        ):
            with self.assertRaisesRegex(
                guard.RuntimeGuardError, "found active training"
            ):
                guard.fresh_execution_probe(
                    self.config, self.baseline
                )

    def test_child_argv_rejects_guard_or_config_override(self) -> None:
        receipt = (
            REPO
            / "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1"
            / "w1_align_execution_guard.json"
        )
        valid = [
            "python",
            guard.LOCKED_GATE_SCRIPT,
            "--config",
            str(CONFIG_PATH),
            "--execution-guard",
            str(receipt),
            "--cohort",
            "core",
        ]
        self.assertEqual(
            guard.validate_child_argv(valid, CONFIG_PATH, receipt), valid
        )
        with self.assertRaisesRegex(
            guard.RuntimeGuardError, "exactly one locked --config"
        ):
            guard.validate_child_argv(
                [
                    *valid,
                    "--config",
                    "alternate.json",
                ],
                CONFIG_PATH,
                receipt,
            )

    def test_child_argv_accepts_only_locked_coreg_gate_mode(self) -> None:
        receipt = (
            REPO
            / "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1"
            / "w1_align2_execution_guard.json"
        )
        valid = [
            "python",
            guard.LOCKED_GATE_SCRIPT,
            "--config",
            str(CONFIG_PATH),
            "--execution-guard",
            str(receipt),
            "--coreg-lock2",
        ]
        self.assertEqual(
            guard.validate_child_argv(valid, CONFIG_PATH, receipt), valid
        )
        config = copy.deepcopy(self.config)
        config["coreg_gate_lock2"]["enabled"] = False
        with self.assertRaisesRegex(
            guard.RuntimeGuardError, "mode is not locked"
        ):
            guard.validate_child_argv(
                valid, CONFIG_PATH, receipt, config=config
            )

    def test_views_override_is_disabled_without_path_and_sha_lock(self) -> None:
        receipt = (
            REPO
            / "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1"
            / "w1_align_execution_guard.json"
        )
        argv = [
            "python",
            guard.LOCKED_GATE_SCRIPT,
            "--config",
            str(CONFIG_PATH),
            "--execution-guard",
            str(receipt),
            "--views",
            "unlocked_views.csv",
        ]
        with self.assertRaisesRegex(
            guard.RuntimeGuardError,
            "--views is disabled",
        ):
            guard.validate_child_argv(argv, CONFIG_PATH, receipt)

    def test_views_override_requires_exact_locked_path_and_rehash(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="fusion_w1_guard_views."
        ) as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            receipt = root / "receipt.json"
            views_path = root / "locked_views.csv"
            views_path.write_text(
                "building_id,view_name\n1,image.JPG\n",
                encoding="utf-8",
            )
            views_sha = hashlib.sha256(views_path.read_bytes()).hexdigest()
            config = copy.deepcopy(self.config)
            config["view_selection"]["provided_views_csv_path"] = (
                "locked_views.csv"
            )
            config["view_selection"]["provided_views_csv_sha256"] = views_sha
            config_path.write_text("{}", encoding="utf-8")
            valid = [
                "python",
                guard.LOCKED_GATE_SCRIPT,
                "--config",
                "config.json",
                "--execution-guard",
                "receipt.json",
                "--views",
                "locked_views.csv",
            ]
            with mock.patch.object(guard, "REPO_ROOT", root):
                self.assertEqual(
                    guard.validate_child_argv(
                        valid,
                        config_path,
                        receipt,
                        config=config,
                    ),
                    valid,
                )
                self.assertEqual(
                    guard.provided_views_lock(config),
                    ("locked_views.csv", views_sha),
                )
                wrong = [*valid[:-1], "other_views.csv"]
                with self.assertRaisesRegex(
                    guard.RuntimeGuardError,
                    "--views differs",
                ):
                    guard.validate_child_argv(
                        wrong,
                        config_path,
                        receipt,
                        config=config,
                    )
                views_path.write_text(
                    "building_id,view_name\n1,changed.JPG\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(
                    guard.RuntimeGuardError,
                    "SHA-256 mismatch",
                ):
                    guard.provided_views_lock(config)

    def test_other_path_overrides_must_equal_locked_config_paths(self) -> None:
        receipt = (
            REPO
            / "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1"
            / "w1_align_execution_guard.json"
        )
        base = [
            "python",
            guard.LOCKED_GATE_SCRIPT,
            "--config",
            str(CONFIG_PATH),
            "--execution-guard",
            str(receipt),
        ]
        for option, value in (
            ("--targets", "alternate_targets.csv"),
            ("--datum-config", "alternate_datum.json"),
            ("--output-dir", "alternate_output"),
        ):
            with self.subTest(option=option):
                with self.assertRaisesRegex(
                    guard.RuntimeGuardError,
                    "differs from the locked config path",
                ):
                    guard.validate_child_argv(
                        [*base, option, value],
                        CONFIG_PATH,
                        receipt,
                    )

    def test_single_writer_lock_is_nonblocking(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="fusion_w1_guard_lock."
        ) as temporary:
            path = Path(temporary) / "gate.lock"
            with guard.single_writer_lock(path):
                with self.assertRaisesRegex(
                    guard.RuntimeGuardError,
                    "another Gate A writer",
                ):
                    with guard.single_writer_lock(path):
                        pass


if __name__ == "__main__":
    unittest.main()

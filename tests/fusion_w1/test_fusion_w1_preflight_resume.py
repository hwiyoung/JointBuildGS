#!/usr/bin/env python3
"""Unit/contract tests for the FUS-W1 resume preflight."""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[2] / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_preflight_resume.py"
SPEC = importlib.util.spec_from_file_location(
    "fusion_w1_preflight_resume", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)

REPO = Path(__file__).resolve().parents[2]
CONFIG_PATH = (
    REPO / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_preflight_resume_v1.json"
)
WRAPPER_PATH = (
    REPO / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_preflight_resume.sh"
)


def completed(
    stdout: str = "", returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["fixture"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class FusionW1PreflightResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    def test_locked_config_is_valid_and_snapshot_is_not_a_stop(self) -> None:
        preflight.validate_config(self.config)
        policy = self.config["time_policy"]
        amendment = self.config["git_lock"]["protocol_amendment"]
        self.assertEqual(policy["amendment_id"], amendment["amendment_id"])
        self.assertEqual(policy["amendment_commit"], amendment["commit"])
        self.assertEqual(policy["snapshot_mode"], "status_snapshot_only")
        self.assertFalse(policy["hard_stop_at_snapshot"])
        self.assertTrue(policy["continue_after_snapshot"])
        self.assertEqual(
            {
                item["role"]: item["path"]
                for item in self.config["git_lock"]["implementation_files"]
            },
            {
                "config": (
                    "phases/p2-gsjso/configs/fusion_w1/"
                    "fusion_w1_preflight_resume_v1.json"
                ),
                "script": (
                    "phases/p2-gsjso/scripts/fusion_w1/"
                    "fusion_w1_preflight_resume.py"
                ),
                "wrapper": (
                    "phases/p2-gsjso/scripts/fusion_w1/"
                    "run_fusion_w1_preflight_resume.sh"
                ),
                "test": (
                    "tests/fusion_w1/"
                    "test_fusion_w1_preflight_resume.py"
                ),
            },
        )

    def test_output_contract_cannot_overwrite_prior_blocked_manifest(self) -> None:
        drift = copy.deepcopy(self.config)
        drift["outputs"]["preflight_resume"] = drift["outputs"][
            "prior_blocked_manifest"
        ]
        with self.assertRaisesRegex(
            preflight.PreflightError, "may not overwrite blocked manifest"
        ):
            preflight.validate_config(drift)

    def test_runtime_rejects_an_alternate_uncommitted_config_path(self) -> None:
        preflight.require_locked_config_path(self.config, CONFIG_PATH)
        with tempfile.TemporaryDirectory(
            prefix="fusion_w1_alternate_config."
        ) as temporary:
            alternate = Path(temporary) / "alternate.json"
            alternate.write_text(
                json.dumps(self.config, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                preflight.PreflightError,
                "committed implementation-contract config",
            ):
                preflight.require_locked_config_path(self.config, alternate)

    def test_override_requires_explicit_mode_and_caveat(self) -> None:
        for mutation in ("mode", "caveat"):
            with self.subTest(mutation=mutation):
                drift = copy.deepcopy(self.config)
                override = drift["mount_freshness"][
                    "missing_background_document"
                ]
                if mutation == "mode":
                    override["override_mode"] = "implicit"
                else:
                    override["provenance_caveat"] = ""
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_config(drift)

    def test_sha256sum_stream_aggregate_matches_sha256sum_format(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="fusion_w1_preflight_test."
        ) as temporary:
            root = Path(temporary)
            (root / "b.bin").write_bytes(b"B")
            (root / "a.bin").write_bytes(b"A")
            with mock.patch.object(preflight, "REPO", root):
                observed, count, total_bytes, inventory = (
                    preflight.sha256sum_stream_aggregate(root)
                )
            expected_stream = b""
            for name, value in (("a.bin", b"A"), ("b.bin", b"B")):
                digest = hashlib.sha256(value).hexdigest()
                logical = name
                expected_stream += f"{digest}  {logical}\n".encode("utf-8")
            self.assertEqual(
                observed, hashlib.sha256(expected_stream).hexdigest()
            )
            self.assertEqual(count, 2)
            self.assertEqual(total_bytes, 2)
            self.assertEqual(
                [Path(row["path"]).name for row in inventory],
                ["a.bin", "b.bin"],
            )

    def test_process_guard_finds_training_but_not_preflight(self) -> None:
        patterns = self.config["training_process_guard"][
            "forbidden_command_regexes"
        ]
        commands = {
            91001: "python src/stage2/train.py --config locked.yaml",
            91002: (
                "python phases/p2-gsjso/scripts/fusion_w1/"
                "fusion_w1_preflight_resume.py"
            ),
        }
        with mock.patch.object(
            preflight,
            "process_command",
            side_effect=lambda pid: commands[pid],
        ):
            matches = preflight.scan_processes(
                patterns, pids=commands.keys()
            )
        self.assertEqual([row["pid"] for row in matches], [91001])

    def test_unknown_gpu_compute_is_caveated_and_blocks_future_launch(
        self,
    ) -> None:
        def fake_run(command, **kwargs):
            if command[:2] == ["docker", "ps"]:
                return completed("")
            if command and command[0] == "nvidia-smi":
                return completed("424242, python, 330\n")
            raise AssertionError(f"unexpected command: {command}")

        with (
            mock.patch.object(preflight, "scan_processes", return_value=[]),
            mock.patch.object(preflight, "process_command", return_value=""),
            mock.patch.object(preflight, "run", side_effect=fake_run),
        ):
            result = preflight.check_no_active_training(self.config)
        self.assertEqual(result["status"], "passed_with_caveat")
        self.assertTrue(
            result["evidence"]["future_gpu_stage_launch_blocked"]
        )
        self.assertEqual(
            [row["pid"] for row in result["evidence"][
                "unknown_gpu_compute_processes"
            ]],
            [424242],
        )

    def test_failed_gpu_compute_probe_fails_closed(self) -> None:
        def fake_run(command, **kwargs):
            if command[:2] == ["docker", "ps"]:
                return completed("")
            if command and command[0] == "nvidia-smi":
                return completed(returncode=1, stderr="query failed")
            raise AssertionError(f"unexpected command: {command}")

        with (
            mock.patch.object(preflight, "scan_processes", return_value=[]),
            mock.patch.object(preflight, "run", side_effect=fake_run),
        ):
            result = preflight.check_no_active_training(self.config)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            result["evidence"]["future_gpu_stage_launch_blocked"]
        )

    def test_git_lock_requires_committed_implementation_and_clean_tracked_tree(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="fusion_w1_git_fixture."
        ) as temporary:
            fixture_repo = Path(temporary)
            lock = self.config["git_lock"]
            paths = [
                lock["dispatch"]["path"],
                *(item["path"] for item in lock["protocol_amendment"]["files"]),
                *(item["path"] for item in lock["implementation_files"]),
            ]
            head_content: dict[str, str] = {}
            for path in paths:
                source = REPO / path
                destination = fixture_repo / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                content = source.read_text(encoding="utf-8")
                destination.write_text(content, encoding="utf-8")
                head_content[path] = content

            status_output = [""]
            fake_head = "a" * 40

            def fake_git(*args: str, check: bool = True):
                if args == ("branch", "--show-current"):
                    return completed(lock["expected_branch"] + "\n")
                if args == ("rev-parse", "HEAD"):
                    return completed(fake_head + "\n")
                if args[:2] == ("cat-file", "-t"):
                    return completed("commit\n")
                if args[:2] == ("merge-base", "--is-ancestor"):
                    return completed()
                if args and args[0] == "show":
                    path = args[1].split(":", 1)[1]
                    content = head_content.get(path)
                    if content is None:
                        return completed(returncode=128)
                    return completed(content)
                if args[:2] == ("status", "--porcelain=v1"):
                    return completed(status_output[0])
                raise AssertionError(f"unexpected git fixture call: {args}")

            with (
                mock.patch.object(preflight, "REPO", fixture_repo),
                mock.patch.object(preflight, "git", side_effect=fake_git),
            ):
                result = preflight.check_git_lock(self.config)
                self.assertEqual(result["status"], "passed")
                evidence = result["evidence"]
                self.assertEqual(evidence["implementation_head"], fake_head)
                self.assertTrue(
                    evidence["implementation_all_working_and_head_match"]
                )
                self.assertEqual(len(evidence["implementation_files"]), 4)
                self.assertTrue(
                    evidence["dispatch"]["working_and_committed_match"]
                )
                self.assertTrue(
                    evidence["protocol_amendment"][
                        "working_and_committed_match"
                    ]
                )

                status_output[0] = " M src/stage2/train.py\n"
                dirty = preflight.check_git_lock(self.config)
                self.assertEqual(dirty["status"], "failed")
                self.assertEqual(
                    dirty["evidence"]["tracked_worktree_changes"],
                    [" M src/stage2/train.py"],
                )

                script_path = lock["implementation_files"][1]["path"]
                (fixture_repo / script_path).write_text(
                    head_content[script_path] + "\n# uncommitted drift\n",
                    encoding="utf-8",
                )
                status_output[0] = ""
                drift = preflight.check_git_lock(self.config)
                self.assertEqual(drift["status"], "failed")
                self.assertFalse(
                    drift["evidence"][
                        "implementation_all_working_and_head_match"
                    ]
                )

    def test_missing_background_document_passes_only_with_caveat(self) -> None:
        with (
            tempfile.TemporaryDirectory(
                prefix="fusion_w1_missing_container."
            ) as container_temporary,
            tempfile.TemporaryDirectory(
                prefix="fusion_w1_missing_host."
            ) as host_temporary,
        ):
            container_root = Path(container_temporary)
            host_root = Path(host_temporary)
            drift = copy.deepcopy(self.config)
            drift["mount_freshness"]["control_files"] = []
            drift["mount_freshness"]["missing_background_document"][
                "path"
            ] = "docs/missing.md"
            git_check = {
                "evidence": {
                    "dispatch": {"working_and_committed_match": True}
                }
            }
            with mock.patch.object(preflight, "REPO", container_root):
                result = preflight.check_mount_freshness(
                    drift, git_check, host_root
                )
            self.assertEqual(result["status"], "passed_with_caveat")
            self.assertIn("does not reconstruct", result["caveat"])
            missing = result["evidence"]["missing_background_document"]
            self.assertTrue(missing["override_valid"])
            self.assertTrue(missing["not_reconstructed_or_substituted"])

    def test_unexpected_present_background_document_fails_closed(self) -> None:
        with (
            tempfile.TemporaryDirectory(
                prefix="fusion_w1_present_container."
            ) as container_temporary,
            tempfile.TemporaryDirectory(
                prefix="fusion_w1_present_host."
            ) as host_temporary,
        ):
            container_root = Path(container_temporary)
            host_root = Path(host_temporary)
            relative = Path("docs/unlocked.md")
            for root in (container_root, host_root):
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / relative).write_text("same but unlocked\n")
            drift = copy.deepcopy(self.config)
            drift["mount_freshness"]["control_files"] = []
            drift["mount_freshness"]["missing_background_document"][
                "path"
            ] = relative.as_posix()
            git_check = {
                "evidence": {
                    "dispatch": {"working_and_committed_match": True}
                }
            }
            with mock.patch.object(preflight, "REPO", container_root):
                result = preflight.check_mount_freshness(
                    drift, git_check, host_root
                )
            self.assertEqual(result["status"], "failed")
            self.assertEqual(
                result["evidence"]["missing_background_document"]["status"],
                "unexpected_present_unlocked",
            )
            self.assertIn("without an expected SHA-256", result["caveat"])

    def test_script_has_no_stage2_training_import(self) -> None:
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertNotIn("src.stage2.train", imported)

    def test_wrapper_is_docker_gpu_pid_namespace_only_preflight(self) -> None:
        wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
        self.assertIn("docker run --rm", wrapper)
        self.assertIn("--gpus", wrapper)
        self.assertIn("--pid=host", wrapper)
        self.assertIn("fusion_w1_preflight_resume.py", wrapper)
        self.assertNotIn("src/stage2/train.py", wrapper)
        self.assertNotRegex(wrapper, r"--env[ =]+HOME(?:=|\\b)")
        self.assertNotIn("CODEX_HOME", wrapper)

    def test_readout_plan_is_plan_only_serial_24g(self) -> None:
        plan = self.config["readout_resource_plan"]
        self.assertEqual(plan["max_parallel_readout_jobs"], 1)
        self.assertFalse(plan["concurrent_with_training"])
        self.assertEqual(
            plan["required_docker_flags"],
            ["--memory=24g", "--memory-swap=24g"],
        )
        self.assertEqual(plan["memory_bytes"], 24 * 1024**3)
        self.assertEqual(plan["memory_swap_bytes"], 24 * 1024**3)


if __name__ == "__main__":
    unittest.main(verbosity=2)

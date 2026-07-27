#!/usr/bin/env python3
"""Dry-run contract tests for the continuation-v3 user service control plane."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
DRIVER = REPO / "phases/p2-gsjso/scripts/fusion_w1_aprime_continuation_v3_service_20260727.py"
CONFIG = REPO / "phases/p2-gsjso/configs/fusion_w1_aprime_continuation_v3_service_20260727.json"
WRAPPER = REPO / "phases/p2-gsjso/scripts/run_fusion_w1_aprime_continuation_v3_service_20260727.sh"
EXPECTED_HEAD = "1" * 40


def load_driver():
    spec = importlib.util.spec_from_file_location("continuation_v3_service_under_test", DRIVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controller = load_driver()
config = controller.load_config(CONFIG)


def completed(arguments=(), returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(arguments, returncode, stdout, stderr)


class ConfigAndUnitTests(unittest.TestCase):
    def test_config_targets_queue_v3_and_review_v3_only(self):
        self.assertEqual(
            config["queue"]["wrapper"],
            "phases/p2-gsjso/scripts/run_fusion_w1_aprime_queue_continuation_v3_20260727.sh",
        )
        self.assertTrue(config["queue"]["root"].endswith("unattended_queue_continuation_v3_repair1"))
        self.assertIn("/review_v3/", config["review_index"]["publication_root"])
        self.assertNotIn("continuation_v2", config["queue"]["root"])

    def test_source_v2_is_read_only_boundary_input(self):
        source = config["source_v2"]
        self.assertTrue(source["reused_stage_record"].endswith("arm_Aprime_r1.json"))
        self.assertEqual(source["required_status"], "MEASURED")
        self.assertEqual(
            source["referenced_receipt_hash_verification_owner"],
            "queue_v3_verify_initialize",
        )
        self.assertFalse(config["boundary_gate"]["service_sends_signals_to_v2"])

    def test_rendered_unit_has_fixed_head_v3_exec_and_explicit_log(self):
        unit = controller.render_unit(config, EXPECTED_HEAD).decode("utf-8")
        self.assertIn(f'"--expected-head" "{EXPECTED_HEAD}"', unit)
        self.assertIn("run_fusion_w1_aprime_queue_continuation_v3_20260727.sh", unit)
        self.assertNotIn("run_fusion_w1_aprime_queue_continuation_20260727.sh", unit)
        self.assertIn(f"WorkingDirectory={config['service']['working_directory']}", unit)
        self.assertIn(
            "StandardOutput=append:"
            + config["service"]["working_directory"]
            + "/"
            + config["service"]["log"],
            unit,
        )
        self.assertIn("StandardError=append:", unit)

    def test_rendered_unit_pins_kill_and_restart_policy(self):
        unit = controller.render_unit(config, EXPECTED_HEAD).decode("utf-8")
        required = (
            "Type=exec",
            "StartLimitIntervalSec=0",
            "RefuseManualStop=no",
            "Restart=on-failure",
            "RestartSec=30s",
            "RestartPreventExitStatus=2 78",
            "KillMode=control-group",
            "KillSignal=SIGTERM",
            "SendSIGKILL=yes",
            "TimeoutStopSec=300s",
            "FinalKillSignal=SIGKILL",
            "TimeoutStopFailureMode=terminate",
            "StandardInput=null",
        )
        for line in required:
            self.assertIn(line, unit)
        self.assertIn('"record-stop-audit"', unit)
        self.assertIn('"record-stop-post-audit"', unit)
        self.assertIn('"${SERVICE_RESULT}"', unit)
        self.assertIn('"${EXIT_CODE}"', unit)
        self.assertIn('"${EXIT_STATUS}"', unit)
        self.assertTrue(config["stop_control"]["partial_artifacts_preserved"])
        self.assertFalse(config["stop_control"]["partial_artifacts_deleted"])

    def test_rendered_unit_declares_capability_but_does_not_enable_linger(self):
        unit = controller.render_unit(config, EXPECTED_HEAD).decode("utf-8")
        self.assertNotIn("loginctl", unit)
        self.assertNotIn("enable-linger", unit)
        self.assertTrue(config["service"]["terminal_close_capability_declared"])
        self.assertTrue(config["service"]["terminal_close_safe_now_requires_runtime_evidence"])
        self.assertTrue(config["service"]["logout_persistence_requires_linger"])
        self.assertFalse(config["service"]["auto_enable_linger"])

    def test_render_unit_rejects_non_commit_head(self):
        with self.assertRaises(controller.ServiceContractError):
            controller.render_unit(config, "HEAD")

    def test_host_wrapper_is_thin_and_has_no_service_mutation_at_import(self):
        source = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("set -Eeuo pipefail", source)
        self.assertIn('exec /usr/bin/python3 "$CONTROLLER" --config "$CONFIG" "$@"', source)
        self.assertNotIn("systemctl", source)
        self.assertNotIn("kill ", source)

    def test_install_dry_run_does_not_write_or_call_systemctl(self):
        with (
            mock.patch.object(controller, "verify_fixed_head", return_value={"head": EXPECTED_HEAD}),
            mock.patch.object(
                controller,
                "exclusive_or_identical",
                side_effect=AssertionError("dry run attempted a write"),
            ),
            mock.patch.object(
                controller,
                "run_command",
                side_effect=AssertionError("dry run called systemctl"),
            ),
        ):
            result = controller.install_service(config, EXPECTED_HEAD, dry_run=True)
        self.assertEqual(result["state"], "DRY_RUN")
        self.assertTrue(result["dry_run"])
        self.assertIn("[Service]", result["unit"])

    def test_fixed_head_scope_expands_service_queue_qualitative_and_locked_dependencies(self):
        scope = controller.fixed_head_scope(config)
        groups = scope["groups"]
        self.assertEqual(len(groups["service_implementation"]), 4)
        self.assertEqual(len(groups["queue_v3_implementation"]), 4)
        self.assertEqual(len(groups["qualitative_v3_implementation"]), 4)
        self.assertEqual(len(groups["queue_v3_locked_dependencies"]), 17)
        self.assertEqual(len(scope["paths"]), 25)
        self.assertEqual(len(set(scope["paths"])), 25)
        self.assertEqual(
            set(scope["queue_locked_inputs"]),
            set(config["fixed_head_contract"]["required_queue_locked_input_names"]),
        )
        self.assertEqual(
            set(scope["cross_group_overlaps_verified_once"]),
            set(groups["qualitative_v3_implementation"]),
        )

    def test_stop_audit_is_append_only_and_declares_partial_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audit_root = root / "audits"
            source = root / "status.json"
            source.write_bytes(b'{"state":"ACTIVE"}\n')
            local = copy.deepcopy(config)
            local["stop_control"]["audit_root"] = "AUDIT"
            local["review_index"]["control_files"] = ["SOURCE"]

            def mapped(value):
                if value == "AUDIT":
                    return audit_root
                if value == "SOURCE":
                    return source
                raise AssertionError(value)

            with (
                mock.patch.object(controller, "repo_path", side_effect=mapped),
                mock.patch.object(
                    controller,
                    "repo_relative",
                    side_effect=lambda path: path.relative_to(root).as_posix(),
                ),
                mock.patch.object(
                    controller,
                    "verify_fixed_head",
                    return_value={"head": EXPECTED_HEAD},
                ),
                mock.patch.object(
                    controller,
                    "service_status",
                    return_value={"terminal_close_safe_now": True},
                ),
            ):
                result = controller.record_stop_audit(local, EXPECTED_HEAD)
            publications = list(audit_root.glob("*.json"))
            self.assertEqual(len(publications), 1)
            payload = json.loads(publications[0].read_text(encoding="utf-8"))
        self.assertEqual(result["state"], "RECORDED")
        self.assertEqual(payload["state"], "STOP_REQUEST_RECORDED_BEFORE_SIGNAL")
        self.assertTrue(payload["stop_contract"]["partial_artifacts_preserved"])
        self.assertFalse(payload["stop_contract"]["partial_artifacts_deleted"])
        self.assertEqual(payload["stop_contract"]["graceful_timeout_seconds"], 300)
        self.assertEqual(payload["stop_contract"]["emergency_signal_after_timeout"], "SIGKILL")

    def test_stop_post_audit_records_timeout_and_emergency_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audit_root = root / "audits"
            local = copy.deepcopy(config)
            local["stop_control"]["audit_root"] = "AUDIT"
            with (
                mock.patch.object(
                    controller,
                    "repo_path",
                    side_effect=lambda value: audit_root
                    if value == "AUDIT"
                    else (_ for _ in ()).throw(AssertionError(value)),
                ),
                mock.patch.object(
                    controller,
                    "repo_relative",
                    side_effect=lambda path: path.relative_to(root).as_posix(),
                ),
                mock.patch.object(
                    controller,
                    "verify_fixed_head",
                    return_value={"head": EXPECTED_HEAD},
                ),
                mock.patch.object(
                    controller,
                    "service_status",
                    return_value={"terminal_close_safe_now": False},
                ),
            ):
                result = controller.record_stop_post_audit(
                    local,
                    EXPECTED_HEAD,
                    "timeout",
                    "killed",
                    "9",
                )
            publications = list(audit_root.glob("*_post.json"))
            self.assertEqual(len(publications), 1)
            payload = json.loads(publications[0].read_text(encoding="utf-8"))
        self.assertTrue(result["timeout_observed"])
        self.assertTrue(result["emergency_sigkill_observed"])
        self.assertTrue(payload["partial_artifacts_preserved"])
        self.assertFalse(payload["partial_artifacts_deleted"])

    def test_stop_dry_run_does_not_call_systemctl_and_exposes_audit_policy(self):
        with mock.patch.object(
            controller,
            "run_command",
            side_effect=AssertionError("dry run called systemctl"),
        ):
            result = controller.stop_service(config, dry_run=True)
        self.assertEqual(result["state"], "DRY_RUN")
        self.assertTrue(result["dry_run"])
        self.assertTrue(result["exec_stop_pre_signal_audit_required"])
        self.assertTrue(result["exec_stop_post_outcome_audit_required"])
        self.assertEqual(result["graceful_signal"], "SIGTERM")
        self.assertEqual(result["graceful_timeout_seconds"], 300)
        self.assertEqual(result["emergency_signal_after_timeout"], "SIGKILL")
        self.assertTrue(result["partial_artifacts_preserved"])
        self.assertEqual(
            result["command"],
            [
                "systemctl",
                "--user",
                "stop",
                "--no-block",
                config["service"]["unit_name"],
            ],
        )


class BoundaryGateTests(unittest.TestCase):
    def make_stage(self, directory: str, *, status_value: str = "MEASURED"):
        path = Path(directory) / "stage.json"
        path.write_text(
            json.dumps(
                {
                    "status": status_value,
                    "entry": dict(config["source_v2"]["required_identity"]),
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_reused_stage_gate_accepts_only_measured_exact_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_stage(directory)
            with mock.patch.object(controller, "repo_path", return_value=path):
                result = controller.verify_reused_stage_record(config)
            self.assertEqual(result["status"], "MEASURED")
            self.assertEqual(result["identity"]["building_id"], "DEBY_LOD2_42364659")

    def test_reused_stage_gate_rejects_non_measured(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_stage(directory, status_value="SKIPPED")
            with (
                mock.patch.object(controller, "repo_path", return_value=path),
                self.assertRaises(controller.ServiceContractError),
            ):
                controller.verify_reused_stage_record(config)

    def test_boundary_gate_delegates_hash_validation_to_v3_verify(self):
        fake_paths = {
            config["source_v2"]["driver_lock"]: Path("/tmp/v2.lock"),
            config["queue"]["driver_lock"]: Path("/tmp/v3.lock"),
            config["queue"]["wrapper"]: Path("/tmp/v3-wrapper.sh"),
        }

        def mapped(value):
            return fake_paths.get(value, Path("/tmp/unused"))

        with (
            mock.patch.object(
                controller,
                "verify_reused_stage_record",
                return_value={"status": "MEASURED"},
            ),
            mock.patch.object(controller, "active_source_v2_wrapper_processes", return_value=[]),
            mock.patch.object(controller, "active_blocking_aprime_containers", return_value=[]),
            mock.patch.object(controller, "lock_path_is_free", return_value=True),
            mock.patch.object(controller, "repo_path", side_effect=mapped),
            mock.patch.object(
                controller,
                "run_command",
                return_value=completed(stdout='{"state":"PASSED"}\n'),
            ) as runner,
        ):
            result = controller.verify_source_boundary(config, run_v3_verify=True)
        self.assertEqual(result["state"], "PASSED")
        self.assertTrue(result["v3_verify"]["delegated_receipt_hash_verification"])
        self.assertIn("verify", runner.call_args.args[0])
        self.assertFalse(result["service_sent_signals_to_v2"])

    def test_boundary_gate_rejects_active_old_wrapper_before_start(self):
        with (
            mock.patch.object(
                controller,
                "verify_reused_stage_record",
                return_value={"status": "MEASURED"},
            ),
            mock.patch.object(
                controller,
                "active_source_v2_wrapper_processes",
                return_value=[{"pid": 123}],
            ),
            self.assertRaisesRegex(controller.ServiceContractError, "still active"),
        ):
            controller.verify_source_boundary(config, run_v3_verify=False)

    def test_boundary_gate_rejects_held_v2_lock(self):
        with (
            mock.patch.object(
                controller,
                "verify_reused_stage_record",
                return_value={"status": "MEASURED"},
            ),
            mock.patch.object(controller, "active_source_v2_wrapper_processes", return_value=[]),
            mock.patch.object(controller, "repo_path", return_value=Path("/tmp/lock")),
            mock.patch.object(controller, "lock_path_is_free", return_value=False),
            self.assertRaisesRegex(controller.ServiceContractError, "still held"),
        ):
            controller.verify_source_boundary(config, run_v3_verify=False)

    def test_boundary_gate_rejects_source_v2_or_orphaned_v3_container(self):
        with (
            mock.patch.object(
                controller,
                "verify_reused_stage_record",
                return_value={"status": "MEASURED"},
            ),
            mock.patch.object(controller, "active_source_v2_wrapper_processes", return_value=[]),
            mock.patch.object(controller, "repo_path", return_value=Path("/tmp/lock")),
            mock.patch.object(controller, "lock_path_is_free", return_value=True),
            mock.patch.object(
                controller,
                "active_blocking_aprime_containers",
                return_value=["jointbuildgs-aprime-deadbeef"],
            ),
            self.assertRaisesRegex(controller.ServiceContractError, "containers are still active"),
        ):
            controller.verify_source_boundary(config, run_v3_verify=False)

    def test_container_inspect_detects_renamed_training_container_by_mount_and_command(self):
        identifier = "a" * 64
        inspection = [
            {
                "Id": identifier,
                "Name": "/renamed-unrelated-looking",
                "Mounts": [
                    {
                        "Type": "bind",
                        "Source": config["repository"],
                        "Destination": "/workspace/JointBuildGS",
                    }
                ],
                "Config": {
                    "Cmd": ["python", "-m", "src.stage2.train"],
                    "Env": ["CUDA_VISIBLE_DEVICES=0"],
                },
                "Args": ["--config", "/workspace/JointBuildGS/run/resolved_config.yaml"],
            }
        ]
        with mock.patch.object(
            controller,
            "run_command",
            side_effect=[
                completed(stdout=identifier + "\n"),
                completed(stdout=json.dumps(inspection)),
            ],
        ):
            result = controller.active_blocking_aprime_containers(config)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["primary_repo_and_command_match"])
        self.assertFalse(result[0]["auxiliary_name_regex_match"])
        self.assertIn("src.stage2.train", result[0]["matched_scientific_markers"])

    def test_container_name_regex_is_only_auxiliary_but_still_fail_closed(self):
        identifier = "b" * 64
        inspection = [
            {
                "Id": identifier,
                "Name": "/jointbuildgs-aprime-orphan",
                "Mounts": [],
                "Config": {"Cmd": ["sleep", "60"], "Env": []},
                "Args": [],
            }
        ]
        with mock.patch.object(
            controller,
            "run_command",
            side_effect=[
                completed(stdout=identifier + "\n"),
                completed(stdout=json.dumps(inspection)),
            ],
        ):
            result = controller.active_blocking_aprime_containers(config)
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]["primary_repo_and_command_match"])
        self.assertTrue(result[0]["auxiliary_name_regex_match"])
        self.assertTrue(result[0]["name_regex_is_auxiliary_only"])

    def test_container_inspect_detects_run_config_even_without_original_name(self):
        identifier = "e" * 64
        inspection = [
            {
                "Id": identifier,
                "Name": "/renamed-config-runner",
                "Mounts": [
                    {
                        "Type": "bind",
                        "Source": config["repository"],
                        "Destination": "/workspace/JointBuildGS",
                    }
                ],
                "Config": {"Cmd": ["python", "worker.py"], "Env": []},
                "Args": ["--config", "/workspace/job/resolved_config.yaml"],
            }
        ]
        with mock.patch.object(
            controller,
            "run_command",
            side_effect=[
                completed(stdout=identifier + "\n"),
                completed(stdout=json.dumps(inspection)),
            ],
        ):
            result = controller.active_blocking_aprime_containers(config)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["primary_repo_and_command_match"])
        self.assertEqual(result[0]["matched_scientific_markers"], ["resolved_config.yaml"])

    def test_container_inspect_ignores_unrelated_active_container(self):
        identifier = "c" * 64
        inspection = [
            {
                "Id": identifier,
                "Name": "/postgres",
                "Mounts": [{"Type": "volume", "Source": "db", "Destination": "/data"}],
                "Config": {"Cmd": ["postgres"], "Env": []},
                "Args": [],
            }
        ]
        with mock.patch.object(
            controller,
            "run_command",
            side_effect=[
                completed(stdout=identifier + "\n"),
                completed(stdout=json.dumps(inspection)),
            ],
        ):
            self.assertEqual(controller.active_blocking_aprime_containers(config), [])

    def test_container_inspect_failure_blocks_boundary_claim(self):
        identifier = "d" * 64
        with (
            mock.patch.object(
                controller,
                "run_command",
                side_effect=[
                    completed(stdout=identifier + "\n"),
                    completed(returncode=1, stderr="inspect failed"),
                ],
            ),
            self.assertRaisesRegex(controller.ServiceContractError, "docker inspect failed"),
        ):
            controller.active_blocking_aprime_containers(config)

    def test_start_dry_run_does_not_call_systemctl(self):
        with (
            mock.patch.object(controller, "installed_expected_head", return_value=EXPECTED_HEAD),
            mock.patch.object(
                controller,
                "exec_preflight",
                return_value={"state": "PASSED", "source_boundary": {"state": "PASSED"}},
            ),
            mock.patch.object(
                controller,
                "run_command",
                side_effect=AssertionError("dry-run start called systemctl"),
            ),
        ):
            result = controller.start_service(config, dry_run=True)
        self.assertEqual(result["state"], "DRY_RUN")
        self.assertEqual(result["preflight"]["source_boundary"]["state"], "PASSED")

    def test_controller_source_contains_no_process_signalling(self):
        source = DRIVER.read_text(encoding="utf-8")
        self.assertNotIn("os.kill", source)
        self.assertNotIn("SIGSTOP", source)
        self.assertNotIn("import signal", source)
        self.assertNotIn("signal_sender", source)


class ServiceStatusTests(unittest.TestCase):
    def make_proc(self, root: Path, pid: int, *, stdin_target: str, cgroup: str):
        proc = root / str(pid)
        (proc / "fd").mkdir(parents=True)
        (proc / "fd/0").symlink_to(stdin_target)
        (proc / "cgroup").write_text(f"0::{cgroup}\n", encoding="utf-8")

    def test_terminal_close_safe_now_requires_all_live_runtime_evidence(self):
        pid = 4242
        cgroup = (
            "/user.slice/user-1000.slice/user@1000.service/app.slice/"
            + config["service"]["unit_name"]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_proc(root, pid, stdin_target="/dev/null", cgroup=cgroup)
            evidence = controller.terminal_close_runtime_evidence(
                config,
                {
                    "LoadState": "loaded",
                    "ActiveState": "active",
                    "SubState": "running",
                    "MainPID": str(pid),
                    "ControlGroup": cgroup,
                    "StandardInput": "null",
                    "StandardOutput": "append:"
                    + os.fspath(controller.repo_path(config["service"]["log"])),
                    "StandardError": "append:"
                    + os.fspath(controller.repo_path(config["service"]["log"])),
                },
                proc_root=root,
            )
        self.assertTrue(evidence["terminal_close_safe_now"])
        self.assertTrue(all(evidence["checks"].values()))

    def test_terminal_close_safe_now_is_false_when_stdin_is_not_dev_null(self):
        pid = 4343
        cgroup = "/app.slice/" + config["service"]["unit_name"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_file = root / "terminal"
            input_file.write_bytes(b"tty")
            self.make_proc(root, pid, stdin_target=os.fspath(input_file), cgroup=cgroup)
            evidence = controller.terminal_close_runtime_evidence(
                config,
                {
                    "LoadState": "loaded",
                    "ActiveState": "active",
                    "SubState": "running",
                    "MainPID": str(pid),
                    "ControlGroup": cgroup,
                    "StandardInput": "null",
                    "StandardOutput": "append:"
                    + os.fspath(controller.repo_path(config["service"]["log"])),
                    "StandardError": "append:"
                    + os.fspath(controller.repo_path(config["service"]["log"])),
                },
                proc_root=root,
            )
        self.assertFalse(evidence["terminal_close_safe_now"])
        self.assertFalse(evidence["checks"]["main_pid_stdin_is_dev_null"])

    def test_terminal_close_safe_now_is_false_when_loaded_unit_log_is_not_append(self):
        pid = 4444
        cgroup = "/app.slice/" + config["service"]["unit_name"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_proc(root, pid, stdin_target="/dev/null", cgroup=cgroup)
            evidence = controller.terminal_close_runtime_evidence(
                config,
                {
                    "LoadState": "loaded",
                    "ActiveState": "active",
                    "SubState": "running",
                    "MainPID": str(pid),
                    "ControlGroup": cgroup,
                    "StandardInput": "null",
                    "StandardOutput": "journal",
                    "StandardError": "journal",
                },
                proc_root=root,
            )
        self.assertFalse(evidence["terminal_close_safe_now"])
        self.assertFalse(evidence["checks"]["unit_stdout_is_append_log"])
        self.assertFalse(evidence["checks"]["unit_stderr_is_append_log"])

    def test_terminal_close_accepts_systemd_normalized_append_with_exact_fragment(self):
        pid = 4545
        cgroup = "/app.slice/" + config["service"]["unit_name"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_proc(root, pid, stdin_target="/dev/null", cgroup=cgroup)
            unit_path = root / config["service"]["unit_name"]
            expected_log = os.fspath(controller.repo_path(config["service"]["log"]))
            unit_path.write_text(
                "\n".join(
                    (
                        "[Service]",
                        "StandardInput=null",
                        f"StandardOutput=append:{expected_log}",
                        f"StandardError=append:{expected_log}",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            evidence = controller.terminal_close_runtime_evidence(
                config,
                {
                    "LoadState": "loaded",
                    "ActiveState": "active",
                    "SubState": "running",
                    "MainPID": str(pid),
                    "ControlGroup": cgroup,
                    "StandardInput": "null",
                    "StandardOutput": "append",
                    "StandardError": "append",
                    "FragmentPath": os.fspath(unit_path),
                    "DropInPaths": "",
                },
                proc_root=root,
                unit_path=unit_path,
            )
        self.assertTrue(evidence["terminal_close_safe_now"])
        self.assertTrue(evidence["checks"]["unit_stdout_is_append_log"])
        self.assertTrue(evidence["checks"]["unit_stderr_is_append_log"])

    def test_status_separates_capability_from_safe_now_measurement(self):
        systemctl_output = "\n".join(
            (
                "LoadState=not-found",
                "ActiveState=inactive",
                "SubState=dead",
                "MainPID=0",
                "ControlGroup=",
            )
        )
        with mock.patch.object(
            controller,
            "run_command",
            side_effect=[
                completed(stdout=systemctl_output),
                completed(stdout="no\n"),
            ],
        ):
            result = controller.service_status(config)
        self.assertTrue(result["terminal_close_capability"]["declared"])
        self.assertFalse(result["terminal_close_safe_now"])
        self.assertNotIn("terminal_close_persistence", result)
        self.assertEqual(result["user_linger"], "DISABLED")


class ReviewIndexTests(unittest.TestCase):
    def test_regular_source_index_is_content_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.bin"
            path.write_bytes(b"source-evidence")
            before = (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns)
            record = controller.stable_source_record(path, "source.bin")
            after = (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns)
        self.assertEqual(record["state"], "REGULAR_FILE")
        self.assertEqual(before, after)

    def test_review_index_rejects_symlink_and_special_file_without_following(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.write_bytes(b"target")
            link = root / "link"
            link.symlink_to(target)
            self.assertEqual(
                controller.stable_source_record(link, "link")["state"],
                "REJECTED_SYMLINK",
            )
            if hasattr(os, "mkfifo"):
                fifo = root / "fifo"
                os.mkfifo(fifo)
                self.assertTrue(stat.S_ISFIFO(fifo.lstat().st_mode))
                self.assertEqual(
                    controller.stable_source_record(fifo, "fifo")["state"],
                    "REJECTED_SPECIAL",
                )

    def test_review_index_is_observational_and_non_recursive(self):
        fake_git = mock.Mock()
        fake_git.side_effect = [
            completed(stdout=EXPECTED_HEAD + "\n"),
            completed(stdout="exp/fusion-w1\n"),
        ]
        with (
            mock.patch.object(controller, "git", fake_git),
            mock.patch.object(
                controller,
                "stable_source_record",
                side_effect=lambda _path, logical: {"path": logical, "state": "MISSING"},
            ),
        ):
            result = controller.build_review_index(config, EXPECTED_HEAD)
        self.assertTrue(result["source_read_only"])
        self.assertFalse(result["source_mutation_performed"])
        self.assertFalse(result["recursive_scientific_payload_hashing"])
        self.assertIsNone(result["interpretation_or_verdict"])
        self.assertTrue(all("continuation_v3" in row["path"] for row in result["control_files"]))

    def test_review_publication_is_exclusive_and_outside_queue_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue_root = root / "queue_v3"
            review_root = root / "review_v3"
            queue_root.mkdir()
            local = copy.deepcopy(config)
            local["queue"]["root"] = "QUEUE"
            local["review_index"]["publication_root"] = "REVIEW"

            def mapped(value):
                if value == "QUEUE":
                    return queue_root
                if value == "REVIEW":
                    return review_root
                raise AssertionError(value)

            with (
                mock.patch.object(controller, "repo_path", side_effect=mapped),
                mock.patch.object(
                    controller,
                    "repo_relative",
                    side_effect=lambda path: path.relative_to(root).as_posix(),
                ),
            ):
                first = controller.publish_review_index(local, {"state": "INDEX"}, "snapshot-001")
                with self.assertRaises(controller.ServiceContractError):
                    controller.publish_review_index(local, {"state": "INDEX"}, "snapshot-001")
            self.assertEqual(first["state"], "PUBLISHED")
            self.assertTrue((review_root / "snapshot-001.json").is_file())
            self.assertEqual(list(queue_root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()

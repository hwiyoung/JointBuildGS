#!/usr/bin/env python3
"""Mocked contract/state-machine tests for the P1W postprocess driver."""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts/experiments/pilot_1wave/pilot_1wave_postprocess_driver.py"
SPEC = importlib.util.spec_from_file_location("pilot_1wave_postprocess_driver", SCRIPT)
driver = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = driver
SPEC.loader.exec_module(driver)


def write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_loss_bundle(root: Path) -> tuple[Path, Path]:
    loss_dir = root / "loss"
    output = loss_dir / driver.LOSS_OUTPUT_NAME
    rows = []
    for index in range(14_000):
        row = {field: "" for field in driver.LOSS_OUTPUT_FIELDS}
        row.update({
            "schema_version": "test",
            "condition_id": "01",
            "seed": 1001,
            "checkpoint_step": 20_000,
            "checkpoint_sha256": "a" * 64,
            "iter": index,
            "term": "pho",
            "raw": 1.0,
            "weighted": 1.0,
            "share": 1.0,
            "roof_share": 1.0,
        })
        rows.append(row)
    write_csv(output, rows)
    run_records = []
    for condition, seed in driver._job_order():
        path = loss_dir / "run_receipts" / f"{condition}_seed{seed}.json"
        write_json(path, {
            "schema": "jointbuildgs.pilot_1wave.loss_cursor_run_receipt.v1",
            "condition_id": condition,
            "seed": seed,
        })
        run_records.append({
            "condition_id": condition,
            "seed": seed,
            "path": str(path.resolve()),
            "sha256": driver.sha256_file(path),
        })
    write_json(loss_dir / driver.LOSS_RECEIPT_NAME, {
        "schema": "jointbuildgs.pilot_1wave.loss_cursor_aggregate_receipt.v1",
        "state": "complete",
        "run_count": 10,
        "aggregate_row_count": 14_000,
        "aggregate_output": {
            "path": str(output.resolve()),
            "sha256": driver.sha256_file(output),
            "fields": list(driver.LOSS_OUTPUT_FIELDS),
        },
        "run_receipts": run_records,
    })
    aggregate = root / "aggregate"
    aggregate.mkdir(parents=True)
    shutil.copyfile(output, aggregate / driver.LOSS_OUTPUT_NAME)
    write_json(aggregate / "pilot_1wave_manifest.json", {
        "outputs": {
            driver.LOSS_OUTPUT_NAME: {
                "sha256": driver.sha256_file(output),
                "row_count": 14_000,
            }
        }
    })
    return loss_dir, aggregate


def fake_job(condition: str = "01", seed: int = 1001, sequence: int = 1) -> driver.Job:
    base = driver.REPO / "test-fixture" / condition / str(seed)
    return driver.Job(
        sequence=sequence,
        condition=condition,
        seed=seed,
        job_id=f"{condition}_seed{seed}",
        run_dir=base,
        config_path=base / "config.yaml",
        config_sha256="a" * 64,
        full_state_manifest=base / "full_state_manifest.json",
        checkpoint=base / "ckpt/step_020000.pt",
        checkpoint_sha256="b" * 64,
    )


def fake_extract_policy() -> dict[str, object]:
    return {
        "mode": "serial",
        "max_parallel": 1,
        "sha256": driver.EXTRACT_POLICY_LOCK_SHA256,
        "job_order": [
            f"{condition}_seed{seed}" for condition, seed in driver._job_order()
        ],
    }


def docker_record(*, name: str, job_id: str, contract_sha: str,
                  status: str, exit_code: int = 0,
                  image_id: str = driver.ROOFER_IMAGE_ID) -> dict:
    return {
        "Id": "c" * 64,
        "Name": f"/{name}",
        "Image": image_id,
        "RestartCount": 0,
        "Config": {
            "Image": driver.ROOFER_IMAGE,
            "Entrypoint": ["/roofer"],
            "Cmd": ["--lod22"],
            "Labels": {
                "jointbuildgs.p1w.job": job_id,
                "jointbuildgs.p1w.contract": contract_sha,
            },
        },
        "HostConfig": {
            "Binds": [f"{driver.REPO}:{driver.CONTAINER_REPO}"],
            "NetworkMode": "none",
        },
        "State": {
            "Status": status,
            "ExitCode": exit_code,
            "StartedAt": "2026-07-22T00:00:01Z",
            "FinishedAt": "2026-07-22T00:00:02Z",
        },
    }


class CommandContractTest(unittest.TestCase):
    def test_container_absolute_declared_paths_resolve_to_host_repo(self) -> None:
        host = driver.REPO / "test-fixture/artifact.bin"
        declared = str(driver.CONTAINER_REPO / "test-fixture/artifact.bin")
        self.assertEqual(
            driver._resolve_declared_path(
                declared, declaring_file=driver.REPO / "test-fixture/receipt.json"
            ),
            host.resolve(),
        )

    def test_job_order_and_gpu_assignment_are_exact(self) -> None:
        self.assertEqual(len(driver._job_order()), 10)
        self.assertEqual(driver._job_order()[0], ("01", 1001))
        self.assertEqual(driver._job_order()[-1], ("04b", 1002))
        jobs = [fake_job(condition, seed, index)
                for index, (condition, seed) in enumerate(driver._job_order(), 1)]
        self.assertEqual([job.gpu for job in jobs], [0, 1] * 5)

    def test_resume_gpu_waves_are_singleton_and_canonical(self) -> None:
        # Models an asymmetric resume where several seed1002 outputs already
        # completed and the pending list is no longer pair-aligned.
        pending = [
            fake_job("01", 1001, 1),
            fake_job("02", 1001, 3),
            fake_job("03", 1002, 6),
            fake_job("04a", 1001, 7),
        ]
        waves = driver.gpu_waves(pending)
        self.assertEqual([[job.gpu for job in wave] for wave in waves],
                         [[0], [0], [1], [0]])
        self.assertEqual(
            [job.job_id for wave in waves for job in wave],
            [job.job_id for job in pending],
        )

    def test_resume_gpu_waves_reject_noncanonical_input_order(self) -> None:
        pending = [fake_job("01", 1002, 2), fake_job("01", 1001, 1)]
        with self.assertRaisesRegex(driver.DriverError, "not in canonical order"):
            driver.gpu_waves(pending)

    def test_extract_serial_waits_validates_and_marks_before_next_start(self) -> None:
        temporary = Path(tempfile.mkdtemp(prefix="p1w-wave-reap-"))
        self.addCleanup(shutil.rmtree, temporary)
        jobs = [fake_job("01", 1001, 1), fake_job("01", 1002, 2)]
        attempts = []
        for index in range(2):
            path = temporary / f"attempt_{index + 1:03d}"
            path.mkdir()
            attempts.append(path)
        events: list[str] = []

        class Process:
            def __init__(self, label: str) -> None:
                self.label = label

            def wait(self) -> int:
                events.append(f"wait:{self.label}")
                return 0

        def start(command: list[str], *_args: object, **_kwargs: object) -> Process:
            label = command[-1]
            events.append(f"start:{label}")
            return Process(label)

        def validate(job: driver.Job, _attempt: Path) -> None:
            events.append(f"validate:{job.job_id}")

        def marker(_attempt: Path, _stage: str, job_id: str,
                   _outputs: object, _extra: object) -> None:
            events.append(f"marker:{job_id}")

        with mock.patch.object(
            driver, "completed_attempt",
            side_effect=[None, None, attempts[0], attempts[1]],
        ), \
             mock.patch.object(driver, "next_attempt", side_effect=attempts), \
             mock.patch.object(
                 driver, "dev_extract_command",
                 side_effect=lambda job, _attempt: ["mock-extract", job.job_id],
             ), \
             mock.patch.object(driver.subprocess, "Popen", side_effect=start), \
             mock.patch.object(driver, "validate_extract", side_effect=validate), \
             mock.patch.object(driver, "write_stage_marker", side_effect=marker):
            driver.run_extract_barrier(jobs, fake_extract_policy())
        self.assertEqual(events, [
            "start:01_seed1001", "wait:01_seed1001",
            "validate:01_seed1001", "marker:01_seed1001",
            "start:01_seed1002", "wait:01_seed1002",
            "validate:01_seed1002", "marker:01_seed1002",
        ])

    def test_extract_recipe_is_fixed_and_has_no_legacy_crop_args(self) -> None:
        job = fake_job()
        attempt = driver.REPO / "test-fixture/attempt_001"
        command = driver.dev_extract_command(job, attempt)
        self.assertIn(driver.DEV_IMAGE_ID, command)
        self.assertEqual(command[command.index("--gpus") + 1], "device=0")
        self.assertEqual(command[command.index("--memory") + 1], "24g")
        self.assertEqual(command[command.index("--memory-swap") + 1], "24g")
        self.assertNotIn("all", command)
        self.assertFalse(any(
            argument.startswith("NVIDIA_VISIBLE_DEVICES=") for argument in command
        ))
        self.assertEqual(command.count("CUDA_VISIBLE_DEVICES=0"), 1)
        self.assertEqual(
            command.count(
                "PYTHONPATH=/workspace/JointBuildGS/scripts/experiments/"
                "pilot_1wave:/workspace/JointBuildGS"
            ),
            1,
        )
        self.assertEqual(command.count("--sor"), 1)
        self.assertEqual(command[command.index("--sor") + 1], "on")
        self.assertIn("--no-sem", command)
        self.assertEqual(command[command.index("--checkpoint-step") + 1], "20000")
        for forbidden in ("--targets", "--buffer", "--geojson", "--data-root", "--max-views"):
            self.assertNotIn(forbidden, command)

    def test_p0_command_is_cpu_only_pinned_and_attested(self) -> None:
        command = driver.p0_command(["python3", "tool.py"])
        self.assertIn(driver.P0_IMAGE_ID, command)
        self.assertIn("NVIDIA_VISIBLE_DEVICES=none", command)
        self.assertIn("CUDA_VISIBLE_DEVICES=-1", command)
        self.assertIn(f"P1W_P0_TOOLS_IMAGE_ID={driver.P0_IMAGE_ID}", command)
        self.assertIn("P1W_INSIDE_P0_TOOLS=1", command)

    def test_finalize_command_requires_execution_receipt(self) -> None:
        job = fake_job()
        runtime = driver.REPO / "test-fixture/roofer/runtime"
        receipt = runtime / "roofer_execution_receipt.json"
        command = driver.finalize_command(job, runtime, receipt)
        self.assertIn("--execution-receipt", command)
        self.assertEqual(command[command.index("--execution-receipt") + 1],
                         driver.container_path(receipt))

    def test_dry_run_has_ten_extracts_and_starts_nothing(self) -> None:
        jobs = [fake_job(condition, seed, index)
                for index, (condition, seed) in enumerate(driver._job_order(), 1)]
        payload = driver.dry_run_plan(jobs, {
            "state": "preflight_passed",
            "extract_policy_lock": fake_extract_policy(),
        })
        extracts = [row for row in payload["commands"] if row["stage"] == "extract"]
        self.assertEqual(len(extracts), 10)
        self.assertEqual(
            [
                (row["job_id"], row["gpu"],
                 row["command"][row["command"].index("--gpus") + 1])
                for row in extracts
            ],
            [
                (job.job_id, job.gpu, f"device={job.gpu}")
                for job in jobs
            ],
        )
        for row in extracts:
            command = row["command"]
            self.assertEqual(command.count("--gpus"), 1)
            self.assertEqual(command[command.index("--memory") + 1], "24g")
            self.assertEqual(command[command.index("--memory-swap") + 1], "24g")
            self.assertNotIn("all", command)
            self.assertFalse(any(
                argument.startswith("NVIDIA_VISIBLE_DEVICES=")
                for argument in command
            ))
            self.assertEqual(command.count("CUDA_VISIBLE_DEVICES=0"), 1)
        self.assertEqual(payload["gpu_work_started"], 0)
        self.assertEqual(payload["roofer_invocations_started"], 0)
        self.assertEqual(payload["score_invocations_started"], 0)
        self.assertEqual(payload["extract_schedule"]["mode"], "serial")
        self.assertEqual(payload["extract_schedule"]["max_parallel"], 1)
        self.assertEqual(
            [row["serial_ordinal"] for row in extracts], list(range(1, 11))
        )

    def test_gpu_device_request_rejects_every_noncanonical_device(self) -> None:
        self.assertEqual(driver.docker_gpu_device_request(0),
                         ["--gpus", "device=0"])
        self.assertEqual(driver.docker_gpu_device_request(1),
                         ["--gpus", "device=1"])
        for invalid in (-1, 2, True, "0", None):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(driver.DriverError,
                                            "must be exactly 0 or 1"):
                    driver.docker_gpu_device_request(invalid)  # type: ignore[arg-type]

    def test_gpu_probe_binds_each_device_to_one_distinct_uuid(self) -> None:
        uuids = (
            "GPU-4bdfb675-5d06-8d93-b07e-cbee885cf52c",
            "GPU-fab8c2ab-d02e-92a2-a873-9f096c67c32c",
        )
        responses = [
            subprocess.CompletedProcess(["docker"], 0, f"{uuid}\n", "")
            for uuid in uuids
        ]
        commands: list[list[str]] = []

        def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(list(command))
            return responses[len(commands) - 1]

        with mock.patch.object(driver, "run_host", side_effect=run):
            result = driver.probe_gpu_device_bindings()

        self.assertEqual(result["state"], "pass")
        self.assertEqual(result["unique_visible_uuid_count"], 2)
        self.assertEqual(result["learning_runs_started"], 0)
        self.assertEqual(result["gpu_work_started"], 0)
        self.assertEqual(
            [record["visible_gpu_uuid"] for record in result["devices"]],
            list(uuids),
        )
        for physical_gpu, command in enumerate(commands):
            self.assertEqual(command[command.index("--gpus") + 1],
                             f"device={physical_gpu}")
            self.assertNotIn("all", command)
            self.assertFalse(any(
                argument.startswith("NVIDIA_VISIBLE_DEVICES=")
                for argument in command
            ))
            self.assertEqual(command.count("CUDA_VISIBLE_DEVICES=0"), 1)
            self.assertIn(driver.DEV_IMAGE_ID, command)
            self.assertIn("nvidia-smi", command)

    def test_gpu_probe_rejects_duplicate_visible_uuid(self) -> None:
        uuid = "GPU-4bdfb675-5d06-8d93-b07e-cbee885cf52c"
        response = subprocess.CompletedProcess(["docker"], 0, f"{uuid}\n", "")
        with mock.patch.object(driver, "run_host", return_value=response):
            with self.assertRaisesRegex(driver.DriverError, "two distinct UUIDs"):
                driver.probe_gpu_device_bindings()

    def test_extract_memory_probe_requires_24g_and_zero_swap(self) -> None:
        response = subprocess.CompletedProcess(
            ["docker"], 0, f"{driver.EXTRACT_CONTAINER_MEMORY_BYTES}\n0\n", ""
        )
        with mock.patch.object(driver, "run_host", return_value=response) as run:
            result = driver.probe_extract_memory_limit()
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--memory") + 1], "24g")
        self.assertEqual(command[command.index("--memory-swap") + 1], "24g")
        self.assertEqual(result["memory_max_bytes"], 24 * 1024**3)
        self.assertEqual(result["swap_max_bytes"], 0)
        self.assertEqual(result["gpu_work_started"], 0)

        bad = subprocess.CompletedProcess(["docker"], 0, "max\nmax\n", "")
        with mock.patch.object(driver, "run_host", return_value=bad):
            with self.assertRaisesRegex(driver.DriverError, "cgroup memory probe"):
                driver.probe_extract_memory_limit()

    def test_failed_postprocess_archive_is_recorded_but_not_resumed(self) -> None:
        temporary = Path(tempfile.mkdtemp(
            prefix=".p1w-failed-postprocess-", dir=SCRIPT.parent
        ))
        self.addCleanup(shutil.rmtree, temporary)
        archive = temporary / "attempt1_ce2fdab_gpu_device_overlap"
        state = write_json(archive / "driver_state.json", {
            "schema": driver.DRIVER_SCHEMA,
            "state": "aborted",
            "correction_head": "ce2fdab53d072adbb63dc05be6cda8da52ebd68d",
            "abort_events": [{"type": "DriverError", "message": "exit=137"}],
        })
        records = driver.historical_postprocess_attempt_records(temporary)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["name"], archive.name)
        self.assertEqual(records[0]["correction_head"],
                         "ce2fdab53d072adbb63dc05be6cda8da52ebd68d")
        self.assertEqual(records[0]["abort_event_count"], 1)
        self.assertEqual(records[0]["driver_state_sha256"],
                         driver.sha256_file(state))

    def test_extract_policy_lock_verifies_archived_oom_evidence(self) -> None:
        temporary = Path(tempfile.mkdtemp(
            prefix=".p1w-extract-policy-", dir=SCRIPT.parent
        ))
        self.addCleanup(shutil.rmtree, temporary)
        archive_root = temporary / "archives"
        archive = archive_root / "attempt2_160f1af_extract_oom"
        state = write_json(archive / "driver_state.json", {
            "schema": driver.DRIVER_SCHEMA,
            "state": "aborted",
            "correction_head": "160f1af6e1f56c487c6eb54a9621de52cf77aeb7",
            "abort_events": [{"type": "DriverError", "message": "exit=137"}],
        })
        evidence = archive / "attempts/03_seed1001/extract/attempt_001"
        started = write_json(evidence / "started.json", {"state": "started"})
        stdout = evidence / "stdout.log"
        stdout.write_text("Killed\n", encoding="utf-8")
        failure = write_json(evidence / "failure.json", {
            "schema": driver.STAGE_MARKER_SCHEMA,
            "state": "error",
            "stage": "extract",
            "job_id": "03_seed1001",
            "return_code": 137,
        })
        policy = json.loads(driver.EXTRACT_POLICY_LOCK.read_text(encoding="utf-8"))
        policy["superseded_attempt"].update({
            "driver_state_sha256": driver.sha256_file(state),
            "started_json_sha256": driver.sha256_file(started),
            "stdout_log_sha256": driver.sha256_file(stdout),
            "failure_json_sha256": driver.sha256_file(failure),
        })
        policy_path = write_json(temporary / "policy.json", policy)
        with mock.patch.object(driver, "EXTRACT_POLICY_LOCK", policy_path), \
             mock.patch.object(
                 driver, "EXTRACT_POLICY_LOCK_SHA256", driver.sha256_file(policy_path)
             ), \
             mock.patch.object(
                 driver, "POSTPROCESS_FAILED_ATTEMPTS_ROOT", archive_root
             ):
            result = driver.validate_extract_policy_lock()
        self.assertTrue(result["superseded_evidence_checked"])
        self.assertEqual(result["max_parallel"], 1)

        policy["max_parallel"] = 2
        write_json(policy_path, policy)
        with mock.patch.object(driver, "EXTRACT_POLICY_LOCK", policy_path), \
             mock.patch.object(
                 driver, "EXTRACT_POLICY_LOCK_SHA256", driver.sha256_file(policy_path)
             ), \
             mock.patch.object(
                 driver, "POSTPROCESS_FAILED_ATTEMPTS_ROOT", archive_root
             ):
            with self.assertRaisesRegex(driver.DriverError, "max parallel"):
                driver.validate_extract_policy_lock()

    def test_loss_aggregate_discovers_condition_seed_under_runs(self) -> None:
        captured: list[str] = []
        attempt = driver.REPO / "test-fixture/loss-attempt"
        with mock.patch.object(driver, "completed_attempt", return_value=None), \
             mock.patch.object(driver, "next_attempt", return_value=attempt), \
             mock.patch.object(driver, "stage_command", side_effect=lambda command, *_args: captured.extend(command)), \
             mock.patch.object(driver, "load_json", side_effect=driver.DriverError("stop after command")):
            with self.assertRaisesRegex(driver.DriverError, "stop after command"):
                driver.run_loss_aggregate()
        root_index = captured.index("--training-root") + 1
        self.assertEqual(
            captured[root_index], driver.container_path(driver.TRAINING_ROOT / "runs")
        )

    def test_numeric_manifest_binds_exact_real_loss_bundle(self) -> None:
        temporary = Path(tempfile.mkdtemp(prefix=".p1w-loss-binding-", dir=SCRIPT.parent))
        self.addCleanup(shutil.rmtree, temporary)
        loss_dir, aggregate = write_loss_bundle(temporary)
        result = driver.validate_numeric_loss_binding(aggregate, loss_dir)
        self.assertEqual(result["output_sha256"], driver.sha256_file(
            aggregate / driver.LOSS_OUTPUT_NAME
        ))
        self.assertEqual(len(result["run_receipts"]), 10)
        write_csv(aggregate / driver.LOSS_OUTPUT_NAME, [{"placeholder": "empty"}])
        with self.assertRaisesRegex(driver.DriverError, "numeric/loss cursor SHA"):
            driver.validate_numeric_loss_binding(aggregate, loss_dir)

    def test_loss_receipt_allowlist_is_complete_and_ordered(self) -> None:
        self.assertEqual(len(driver.LOSS_RUN_RECEIPT_OUTPUTS), 10)
        self.assertEqual(
            driver.LOSS_RUN_RECEIPT_OUTPUTS[0],
            "loss_share_receipts/01_seed1001.json",
        )
        self.assertEqual(
            driver.LOSS_RUN_RECEIPT_OUTPUTS[-1],
            "loss_share_receipts/04b_seed1002.json",
        )
        self.assertTrue(set(driver.LOSS_RUN_RECEIPT_OUTPUTS).issubset(
            driver.PUBLISH_ALLOWLIST
        ))


class RetainedContainerStateMachineTest(unittest.TestCase):
    def test_pure_resume_transitions_fail_closed(self) -> None:
        self.assertEqual(driver.retained_action(None, launch_record_exists=False,
                                                finalized=False), "create")
        self.assertEqual(driver.retained_action("created", launch_record_exists=True,
                                                finalized=False), "start")
        self.assertEqual(driver.retained_action("running", launch_record_exists=True,
                                                finalized=False), "wait")
        self.assertEqual(driver.retained_action("exited", launch_record_exists=True,
                                                finalized=False, exit_code=0),
                         "finalize_process")
        self.assertEqual(driver.retained_action("exited", launch_record_exists=True,
                                                finalized=False, exit_code=7),
                         "fail_nonzero")
        self.assertEqual(driver.retained_action(None, launch_record_exists=True,
                                                finalized=False),
                         "fail_missing_after_launch")
        self.assertEqual(driver.retained_action(None, launch_record_exists=True,
                                                finalized=True), "skip")

    def test_create_start_wait_records_exactly_one_launch(self) -> None:
        temporary = Path(tempfile.mkdtemp(prefix="p1w-retained-"))
        self.addCleanup(shutil.rmtree, temporary)
        job = fake_job()
        name = "jointbuildgs-p1w-test-roofer"
        contract = {"job_id": job.job_id, "argv": ["--lod22"]}
        contract_sha = driver.sha256_bytes(driver.canonical_json(contract))
        created = docker_record(name=name, job_id=job.job_id,
                                contract_sha=contract_sha, status="created")
        calls: list[list[str]] = []
        inspections = iter((None, created))

        def inspect(_name: str) -> dict | None:
            try:
                return next(inspections)
            except StopIteration:
                return created

        def run(command: list[str] | tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            command = list(command)
            calls.append(command)
            if command[:2] == ["docker", "wait"]:
                return subprocess.CompletedProcess(command, 0, "0\n", "")
            if command[:2] == ["docker", "logs"]:
                return subprocess.CompletedProcess(command, 0, "roofer log\n", "")
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch.object(driver, "inspect_container", side_effect=inspect), \
             mock.patch.object(driver, "run_host", side_effect=run):
            driver.run_retained_container(
                name=name, job_id=job.job_id, contract=contract,
                create_command=["docker", "create", "--name", name],
                state_dir=temporary, expected_image_id=driver.ROOFER_IMAGE_ID,
            )
        self.assertEqual(sum(command[:2] == ["docker", "create"] for command in calls), 1)
        self.assertEqual(sum(command[:2] == ["docker", "start"] for command in calls), 1)
        self.assertEqual(sum(command[:2] == ["docker", "wait"] for command in calls), 1)
        launch = json.loads((temporary / "container_launch.json").read_text())
        self.assertEqual(launch["container_id"], "c" * 64)
        self.assertEqual(launch["contract_sha256"], contract_sha)
        self.assertEqual(json.loads((temporary / "process_complete.json").read_text())["exit_code"], 0)

    def test_missing_container_after_launch_never_recreates(self) -> None:
        temporary = Path(tempfile.mkdtemp(prefix="p1w-missing-"))
        self.addCleanup(shutil.rmtree, temporary)
        write_json(temporary / "container_launch.json", {"state": "container_created"})
        with mock.patch.object(driver, "inspect_container", return_value=None), \
             mock.patch.object(driver, "run_host") as run:
            with self.assertRaisesRegex(driver.DriverError, "fail_missing_after_launch"):
                driver.run_retained_container(
                    name="missing", job_id="01_seed1001", contract={"x": 1},
                    create_command=["docker", "create"], state_dir=temporary,
                    expected_image_id=driver.ROOFER_IMAGE_ID,
                )
        run.assert_not_called()

    def test_execution_receipt_binds_inspect_logs_and_prepare(self) -> None:
        # This fixture lives below the repo because the receipt intentionally
        # refuses evidence paths outside the mounted repository.
        temporary = Path(tempfile.mkdtemp(prefix=".p1w-receipt-", dir=SCRIPT.parent))
        self.addCleanup(shutil.rmtree, temporary)
        job = fake_job()
        name = driver.roofer_container_name(job)
        contract_sha = "d" * 64
        write_json(temporary / "roofer_prepare.json", {"schema": "prepare"})
        write_json(temporary / "roofer_argv.json", {"schema": "argv"})
        write_json(temporary / "container_launch.json", {
            "container_id": "c" * 64, "contract_sha256": contract_sha,
            "start_attempts": [{"ordinal": 1, "requested_utc": "2026-07-22T00:00:00Z"}],
        })
        write_json(temporary / "process_complete.json", {"exit_code": 0})
        (temporary / "container.log").write_text("immutable log\n", encoding="utf-8")
        record = docker_record(name=name, job_id=job.job_id,
                               contract_sha=contract_sha, status="exited")
        with mock.patch.object(driver, "inspect_container", return_value=record):
            receipt_path = driver.write_roofer_execution_receipt(job, temporary)
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["schema"], "jointbuildgs.pilot_1wave.roofer_execution.v1")
        self.assertEqual(receipt["roofer_invocation_count"], 1)
        self.assertEqual(receipt["container"]["image_id"], driver.ROOFER_IMAGE_ID)
        self.assertEqual(receipt["container"]["binds"], [
            f"{driver.REPO}:{driver.CONTAINER_REPO}"
        ])
        self.assertEqual(receipt["execution"]["start_attempt_count"], 1)
        self.assertEqual(receipt["execution"]["wait_exit_code"], 0)
        self.assertEqual(receipt["logs"]["sha256"], driver.sha256_file(temporary / "container.log"))

    def test_receipt_present_marker_missing_reuses_immutable_execution(self) -> None:
        temporary = Path(tempfile.mkdtemp(prefix=".p1w-receipt-resume-", dir=SCRIPT.parent))
        self.addCleanup(shutil.rmtree, temporary)
        job = fake_job()
        name = driver.roofer_container_name(job)
        contract_sha = "d" * 64
        write_json(temporary / "roofer_prepare.json", {"schema": "prepare"})
        write_json(temporary / "roofer_argv.json", {"schema": "argv"})
        write_json(temporary / "container_launch.json", {
            "container_id": "c" * 64,
            "contract_sha256": contract_sha,
            "start_attempts": [
                {"ordinal": 1, "requested_utc": "2026-07-22T00:00:00Z"}
            ],
        })
        write_json(temporary / "process_complete.json", {"exit_code": 0})
        (temporary / "container.log").write_text("immutable log\n", encoding="utf-8")
        record = docker_record(
            name=name,
            job_id=job.job_id,
            contract_sha=contract_sha,
            status="exited",
        )
        with mock.patch.object(driver, "inspect_container", return_value=record):
            receipt_path = driver.write_roofer_execution_receipt(job, temporary)
        sealed = {
            path.name: path.read_bytes()
            for path in (
                temporary / "process_complete.json",
                temporary / "container.log",
                receipt_path,
            )
        }

        with mock.patch.object(driver, "inspect_container", return_value=record), \
             mock.patch.object(driver, "run_retained_container") as retained:
            driver.run_roofer_barrier([job], {job.job_id: temporary})

        retained.assert_not_called()
        for name, expected in sealed.items():
            self.assertEqual((temporary / name).read_bytes(), expected)


class MachineGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="p1w-gates-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp)

    def _binding_fixture(self, *, one_offdiag: bool = False) -> Path:
        output = self.temp / "binding"
        buildings: list[dict[str, object]] = []
        matrix: list[dict[str, object]] = []
        for condition, seed in driver._job_order():
            for building_id in driver.EXPECTED_IDS:
                buildings.append({
                    "condition_id": condition, "seed": seed,
                    "crop_contract_sha_match": "True",
                    "classification_receipt_sha_match": "True",
                    "spatial_owner_matches_parent": "True",
                    "cityjson_owner_match": "True",
                    "owner_contained": "True",
                })
            for row_index, locked in enumerate(driver.EXPECTED_IDS):
                for col_index, parent in enumerate(driver.EXPECTED_IDS):
                    assigned = row_index == col_index
                    if one_offdiag and condition == "01" and seed == 1001:
                        if row_index == 0 and col_index == 0:
                            assigned = False
                        elif row_index == 0 and col_index == 1:
                            assigned = True
                    matrix.append({
                        "condition_id": condition, "seed": seed,
                        "locked_building_id": locked, "output_parent_id": parent,
                        "owner_assignment": str(assigned),
                        "is_diagonal": str(row_index == col_index),
                    })
        write_csv(output / "binding_audit.csv", buildings)
        write_csv(output / "binding_audit_spatial_matrix.csv", matrix)
        return output

    def test_g1_requires_all_ten_identity_matrices(self) -> None:
        result = driver.evaluate_g1(self._binding_fixture())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["binding_rows"], 300)
        self.assertEqual(result["spatial_rows"], 9000)
        self.assertTrue(all(run["diagonal_assignments"] == 30 for run in result["runs"]))
        self.assertTrue(all(run["offdiagonal_assignments"] == 0 for run in result["runs"]))

    def test_g1_fails_one_swapped_assignment(self) -> None:
        result = driver.evaluate_g1(self._binding_fixture(one_offdiag=True))
        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["runs"][0]["pass"])

    def test_complete_binding_batch_with_failed_g1_remains_reportable(self) -> None:
        output = self._binding_fixture(one_offdiag=True)
        write_json(output / "binding_audit_receipt.json", {
            "schema": "jointbuildgs.pilot_1wave.binding_batch_receipt.v1",
            "state": "complete",
            "hard_gate_passed": False,
            "global_g1": {"pass": False},
        })
        receipt = driver.validate_binding_batch_outputs(output)
        self.assertFalse(receipt["hard_gate_passed"])
        self.assertEqual(driver.evaluate_g1(output)["status"], "fail")

    def _winner_fixture(self, *, co_minimum: bool = False) -> Path:
        rows = []
        for index, condition in enumerate(driver.HONEST_CONDITIONS):
            is_minimum = index == 0 or (co_minimum and index == 1)
            rows.append({
                "condition_id": condition,
                "eligible_two_seed_rule": "True",
                "is_minimum_worst_rms": str(is_minimum),
                "co_minimum_count": "2" if co_minimum else "1",
                "seed_1001_rule_abcd": "True",
                "seed_1002_rule_abcd": "True",
                "rule_abcd_seed_count": "2",
                "worst_seed_roof_rms_median_m": "1.25" if is_minimum else str(1.5 + index),
            })
        return write_csv(self.temp / "winner.csv", rows)

    def test_g2_unique_honest_winner_and_g3_strict_2m(self) -> None:
        g2, g3 = driver.evaluate_g2_g3(self._winner_fixture())
        self.assertEqual(g2["status"], "pass")
        self.assertEqual(g2["winner_condition_id"], "01")
        self.assertEqual(g3["status"], "pass")
        self.assertEqual(g3["best_honest_worst_seed_rms_median_m"], 1.25)

    def test_g2_rejects_co_minimum(self) -> None:
        g2, _g3 = driver.evaluate_g2_g3(self._winner_fixture(co_minimum=True))
        self.assertEqual(g2["status"], "fail")
        self.assertEqual(g2["unique_minimum_count"], 2)

    def test_g4_separates_canonical_runs_from_retry_history(self) -> None:
        preflight = {
            "training": {
                "jobs": [{"job_id": str(index)} for index in range(10)],
                "guard": {"triggered": False, "partial": False, "completion": True},
                "canonical_completed_20k_count": 10,
                "canonical_collapse_count": 0,
                "canonical_divergence_count": 0,
                "canonical_guard_abort_count": 0,
                "historical_learning_runs_started": 16,
                "historical_failed_attempt_archive_count": 4,
                "historical_failed_attempt_archives": ["a", "b", "c", "d"],
                "historical_failed_postprocess_attempt_archive_count": 1,
                "historical_failed_postprocess_attempt_archives": [{
                    "name": "attempt1_ce2fdab_gpu_device_overlap",
                    "correction_head": "ce2fdab53d072adbb63dc05be6cda8da52ebd68d",
                }],
            }
        }
        result = driver.evaluate_g4(preflight, [])
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["canonical_training_completed_20k_count"], 10)
        self.assertEqual(result["historical_learning_runs_started"], 16)
        self.assertEqual(result["historical_failed_attempt_archive_count"], 4)
        self.assertEqual(
            result["historical_failed_postprocess_attempt_archive_count"], 1
        )
        self.assertTrue(result["history_excluded_from_canonical_gate_counts"])
        self.assertEqual(driver.evaluate_g4(preflight, [{"type": "error"}])["status"], "fail")


class Wave2AndPublicationTest(unittest.TestCase):
    def test_final_manifest_preflight_provenance_is_complete_copy(self) -> None:
        preflight = {
            "correction_head": "a" * 40,
            "tracked_tree_clean": True,
            "committed_runtime_sources": {"driver.py": "b" * 64},
            "crop_lock": {
                "inventory_sha256": driver.INVENTORY_SHA256,
                "inventory_records_sha256": driver.INVENTORY_RECORDS_SHA256,
                "checked_file_count": 1_927,
                "checked_total_bytes": 12_335_728_234,
                "crop_area_m2": driver.CROP_AREA_M2,
            },
            "gsplat_extension": {
                "path": "runtime/gsplat_cuda.so",
                "sha256": driver.GSPLAT_EXTENSION_SHA256,
            },
            "gpu_device_probe": {
                "schema": "jointbuildgs.pilot_1wave.gpu_device_probe.v1",
                "state": "pass",
            },
            "extract_policy_lock": fake_extract_policy(),
        }
        result = driver.final_preflight_provenance(preflight)
        self.assertEqual(set(result), {
            "correction_head", "committed_runtime_sources", "crop_lock",
            "gsplat_extension", "gpu_device_probe", "extract_policy_lock",
        })
        self.assertEqual(result["crop_lock"]["inventory_sha256"],
                         driver.INVENTORY_SHA256)
        preflight["crop_lock"]["inventory_sha256"] = "mutated"
        self.assertEqual(result["crop_lock"]["inventory_sha256"],
                         driver.INVENTORY_SHA256)

    def test_resume_never_mixes_correction_heads_or_source_maps(self) -> None:
        state = {
            "correction_head": "a" * 40,
            "preflight": {"committed_runtime_sources": {"x.py": "1" * 64}},
        }
        same = {
            "correction_head": "a" * 40,
            "committed_runtime_sources": {"x.py": "1" * 64},
            "extract_policy_lock": fake_extract_policy(),
        }
        driver.require_resume_contract(state, same, has_stage_outputs=True)
        changed_head = dict(same, correction_head="b" * 40)
        with self.assertRaisesRegex(driver.DriverError, "correction HEAD changed"):
            driver.require_resume_contract(state, changed_head, has_stage_outputs=True)
        changed_source = dict(same, committed_runtime_sources={"x.py": "2" * 64})
        with self.assertRaisesRegex(driver.DriverError, "source SHA map changed"):
            driver.require_resume_contract(state, changed_source, has_stage_outputs=True)
        state["preflight"]["extract_policy_lock"] = fake_extract_policy()
        changed_policy = dict(
            same,
            extract_policy_lock={**fake_extract_policy(), "max_parallel": 2},
        )
        with self.assertRaisesRegex(driver.DriverError, "extract policy changed"):
            driver.require_resume_contract(
                state, changed_policy, has_stage_outputs=True
            )

    def test_missing_wave2_lock_is_explicitly_blocked(self) -> None:
        self.assertEqual(driver.validate_wave2_lock(None, None), {
            "status": "blocked_missing_wave2_lock", "launch_performed": False,
        })

    def test_wave2_sha_without_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(driver.DriverError, "requires --wave2-lock"):
            driver.validate_wave2_lock(None, "a" * 64)

    def test_publish_immutable_never_replaces_different_bytes(self) -> None:
        temporary = Path(tempfile.mkdtemp(prefix="p1w-publish-"))
        self.addCleanup(shutil.rmtree, temporary)
        source = temporary / "source"
        target = temporary / "target"
        source.write_bytes(b"source")
        target.write_bytes(b"different")
        with self.assertRaisesRegex(driver.DriverError, "refusing to replace"):
            driver.publish_immutable(source, target)
        self.assertEqual(target.read_bytes(), b"different")

    def test_partial_allowlist_publish_resumes_with_identical_ledger(self) -> None:
        temporary = Path(tempfile.mkdtemp(prefix=".p1w-publish-resume-", dir=SCRIPT.parent))
        self.addCleanup(shutil.rmtree, temporary)
        source_root = temporary / "sources"
        partial_root = temporary / "partial"
        clean_root = temporary / "clean"
        sources = {}
        for index, name in enumerate(driver.PUBLISH_ALLOWLIST):
            path = source_root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"stable-{index}\n".encode())
            sources[name] = path
        calls = 0

        def crash_after_three(source: Path, target: Path) -> str:
            nonlocal calls
            calls += 1
            if calls == 4:
                raise RuntimeError("simulated host loss")
            return driver.publish_immutable(source, target)

        with self.assertRaisesRegex(RuntimeError, "simulated host loss"):
            driver.publish_allowlisted_files(
                sources, partial_root, publisher=crash_after_three
            )
        resumed = driver.publish_allowlisted_files(sources, partial_root)
        clean = driver.publish_allowlisted_files(sources, clean_root)
        self.assertEqual(resumed, clean)
        for name in driver.PUBLISH_ALLOWLIST:
            self.assertEqual((partial_root / name).read_bytes(),
                             (clean_root / name).read_bytes())

    def test_publication_snapshot_freezes_gates_receipt_and_preboundary_aborts(self) -> None:
        temporary = Path(tempfile.mkdtemp(prefix="p1w-publication-snapshot-"))
        self.addCleanup(shutil.rmtree, temporary)
        binding = temporary / "binding"
        aggregate = temporary / "aggregate"
        buildings: list[dict[str, object]] = []
        matrix: list[dict[str, object]] = []
        for condition, seed in driver._job_order():
            for building_id in driver.EXPECTED_IDS:
                buildings.append({
                    "condition_id": condition,
                    "seed": seed,
                    "crop_contract_sha_match": "True",
                    "classification_receipt_sha_match": "True",
                    "spatial_owner_matches_parent": "True",
                    "cityjson_owner_match": "True",
                    "owner_contained": "True",
                })
            for row_index, locked in enumerate(driver.EXPECTED_IDS):
                for col_index, parent in enumerate(driver.EXPECTED_IDS):
                    matrix.append({
                        "condition_id": condition,
                        "seed": seed,
                        "locked_building_id": locked,
                        "output_parent_id": parent,
                        "owner_assignment": str(row_index == col_index),
                        "is_diagonal": str(row_index == col_index),
                    })
        write_csv(binding / "binding_audit.csv", buildings)
        write_csv(binding / "binding_audit_spatial_matrix.csv", matrix)
        winner_rows = []
        for index, condition in enumerate(driver.HONEST_CONDITIONS):
            winner_rows.append({
                "condition_id": condition,
                "eligible_two_seed_rule": "True",
                "is_minimum_worst_rms": str(index == 0),
                "co_minimum_count": "1",
                "seed_1001_rule_abcd": "True",
                "seed_1002_rule_abcd": "True",
                "rule_abcd_seed_count": "2",
                "worst_seed_roof_rms_median_m": str(1.25 + index),
            })
        write_csv(aggregate / "pilot_1wave_winner.csv", winner_rows)
        preflight = {
            "correction_head": "a" * 40,
            "wave2_launch": {
                "status": "blocked_missing_wave2_lock",
                "launch_performed": False,
            },
            "training": {
                "jobs": [{"job_id": str(index)} for index in range(10)],
                "guard": {"triggered": False, "partial": False, "completion": True},
                "canonical_completed_20k_count": 10,
                "canonical_collapse_count": 0,
                "canonical_divergence_count": 0,
                "canonical_guard_abort_count": 0,
                "historical_learning_runs_started": 16,
                "historical_failed_attempt_archive_count": 4,
                "historical_failed_attempt_archives": ["a", "b", "c", "d"],
            },
        }
        before = {"at": "before", "type": "BeforeSnapshot", "message": "included"}
        after = {"at": "after", "type": "AfterSnapshot", "message": "live only"}
        state = {"abort_events": [before]}
        jobs = [
            fake_job(condition, seed, index)
            for index, (condition, seed) in enumerate(driver._job_order(), 1)
        ]
        executions = {
            job.job_id: {"path": f"runtime/{job.job_id}.json", "sha256": "f" * 64}
            for job in jobs
        }
        with mock.patch.object(
            driver, "repo_relative", side_effect=lambda path: str(Path(path).resolve())
        ), mock.patch.object(
            driver, "now", side_effect=("gate-time", "complete-time", "publish-time")
        ):
            frozen = driver.freeze_publication_snapshot(
                state,
                binding_dir=binding,
                aggregate_dir=aggregate,
                preflight_payload=preflight,
            )
        receipt_before = driver.postprocess_receipt_payload(
            jobs=jobs,
            preflight_payload=preflight,
            publication_snapshot=frozen,
            roofer_execution_receipts=executions,
        )
        self.assertEqual(frozen["machine_gates"]["G4"]["postprocess_abort_count"], 1)
        self.assertEqual(frozen["machine_gates"]["G4"]["status"], "fail")
        state["abort_events"].append(after)
        with mock.patch.object(
            driver, "repo_relative", side_effect=lambda path: str(Path(path).resolve())
        ):
            reopened = driver.freeze_publication_snapshot(
                state,
                binding_dir=binding,
                aggregate_dir=aggregate,
                preflight_payload=preflight,
            )
        receipt_after = driver.postprocess_receipt_payload(
            jobs=jobs,
            preflight_payload=preflight,
            publication_snapshot=reopened,
            roofer_execution_receipts=executions,
        )
        self.assertEqual(frozen, reopened)
        self.assertEqual(driver.canonical_json(receipt_before),
                         driver.canonical_json(receipt_after))
        self.assertEqual(receipt_after["abort_events"], [before])


if __name__ == "__main__":
    unittest.main()

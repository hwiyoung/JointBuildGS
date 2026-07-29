#!/usr/bin/env python3
"""Contract and dry-run tests for the P1W two-GPU guard driver."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import yaml


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts/experiments/pilot_1wave/pilot_1wave_driver.py"
SPEC = importlib.util.spec_from_file_location("pilot_1wave_driver", SCRIPT)
driver = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = driver
SPEC.loader.exec_module(driver)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


class DriverContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.mkdtemp(prefix="p1w-driver-")
        self.repo = Path(self.temp) / "repo"
        self.repo.mkdir()
        self.verifier_source = (
            self.repo / driver.CHECKPOINT_VERIFIER_RELATIVE_PATH
        )
        self.verifier_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            SCRIPT.with_name("pilot_1wave_checkpoint_verify.py"),
            self.verifier_source,
        )
        self.verifier_sha = digest(self.verifier_source)
        self.image_id = "sha256:" + "a" * 64
        self.bundle = self.repo / "run/training/resolved_configs"
        self.bundle.mkdir(parents=True)
        self.runs = self.repo / "run/training/runs"
        self.manifest = self._resolved_manifest()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp)

    def _resolved_manifest(self) -> Path:
        inventory_binding = self._materialized_inventory()
        records = []
        sequence = 0
        arms = {
            "01": "01_surface",
            "02": "02_photo_control",
            "03": "03_plane_soft",
            "04a": "04a_plane_medium_vision",
            "04b": "04b_plane_medium_gt_upperbound",
        }
        for condition, arm in arms.items():
            for seed in (1001, 1002):
                sequence += 1
                job_id = f"{condition}_seed{seed}"
                config_path = self.bundle / f"{job_id}.yaml"
                out_container = f"/workspace/JointBuildGS/run/training/runs/{condition}/seed_{seed}"
                config = {
                    "pilot_resolved_config_schema": (
                        "jointbuildgs.pilot_1wave.resolved_configs.v1"
                    ),
                    "pilot_run_id": "20260721_pilot_1wave",
                    "pilot_job_id": job_id,
                    "pilot_arm": arm,
                    "pilot_condition": condition,
                    "pilot_materialized_input_inventory_path": (
                        "/workspace/JointBuildGS/"
                        + inventory_binding["path"]
                    ),
                    "pilot_materialized_input_inventory_sha256": (
                        inventory_binding["sha256"]
                    ),
                    "seed": seed,
                    "max_iter": 20000,
                    "full_state_checkpoint": True,
                    "full_state_checkpoint_steps": [5000, 10000, 15000, 20000],
                    "full_state_resume": "auto",
                    "full_state_loss_csv_paths": [
                        "audit/pilot_loss_shares.csv",
                        "audit/pilot_loss_details.csv",
                        "audit/pilot_plane_photo_ratio.csv",
                    ],
                    "out_dir": out_container,
                    "w_sem": 0.0,
                    "w_mutual": 0.0,
                    "w_mvc": 0.0,
                    "w_distort": 0.0,
                    "w_mono_depth": 0.0,
                    "w_semdepth_smooth": 0.0,
                    "w_semdepth_plane": 0.0,
                    "w_boundary_normal": 0.0,
                }
                config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
                records.append(
                    {
                        "sequence": sequence,
                        "job_id": job_id,
                        "condition": condition,
                        "pilot_arm": arm,
                        "seed": seed,
                        "config_path": str(config_path.relative_to(self.repo)),
                        "config_sha256": digest(config_path),
                        "out_dir": out_container,
                    }
                )
        return write_json(
            self.bundle / "resolved_configs_manifest.json",
            {
                "schema": "jointbuildgs.pilot_1wave.resolved_configs.v1",
                "run_id": "20260721_pilot_1wave",
                "state": "resolved",
                "learning_runs_started": 0,
                "inputs": {
                    "materialized_input_inventory": inventory_binding,
                },
                "budget": {
                    "seeds": [1001, 1002],
                    "max_optimizer_updates": 20000,
                    "full_state_checkpoint_updates": [5000, 10000, 15000, 20000],
                    "gpu_count": 2,
                    "wall_guard_hours": 9.0,
                    "stop_starting_new_runs_hours": 8.5,
                    "partial_is_winner_eligible": False,
                },
                "training_output_root": {
                    "path": str(self.runs.relative_to(self.repo)),
                    "container_path": "/workspace/JointBuildGS/run/training/runs",
                    "writable_and_separate_from_config_bundle": True,
                },
                "config_count": 10,
                "jobs": records,
            },
        )

    def _materialized_inventory(self) -> dict:
        view_id = "view0001.png"
        root = self.repo / "run/prep"
        specs = [
            ("sfm_cameras", root / "data/sparse/0/cameras.bin", None),
            ("sfm_images", root / "data/sparse/0/images.bin", None),
            ("sfm_points3d", root / "data/sparse/0/points3D.bin", None),
            ("rgb", root / f"data/images/{view_id}", view_id),
            (
                "mvs_depth_geometric",
                root / f"data/stereo/depth_maps/{view_id}.geometric.bin",
                view_id,
            ),
            (
                "mvs_normal_geometric",
                root / f"data/stereo/normal_maps/{view_id}.geometric.bin",
                view_id,
            ),
            ("mono_normal_omnidata", root / "mono/view0001.npy", view_id),
        ]
        records = []
        role_counts = {}
        for index, (role, path, record_view) in enumerate(specs, start=1):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"{role}-{index}".encode("ascii"))
            record = {
                "role": role,
                "path": str(path.relative_to(self.repo)),
                "size_bytes": path.stat().st_size,
                "sha256": digest(path),
            }
            if record_view is not None:
                record["view_id"] = record_view
            records.append(record)
            role_counts[role] = role_counts.get(role, 0) + 1
        inventory = {
            "schema": "jointbuildgs.pilot_1wave.materialized_input_inventory.v1",
            "run_id": "20260721_pilot_1wave",
            "mode": "result_blind_materialized_stage2_inputs",
            "data_root": str((root / "data").relative_to(self.repo)),
            "mono_normal_dir": str((root / "mono").relative_to(self.repo)),
            "view_ids": [view_id],
            "view_count": 1,
            "role_counts": role_counts,
            "file_count": len(records),
            "total_bytes": sum(item["size_bytes"] for item in records),
            "records": records,
            "records_sha256": driver._json_sha256(records),
            "learning_runs_started": 0,
            "optimizer_updates": 0,
        }
        inventory_path = root / "materialized_input_inventory.json"
        write_json(inventory_path, inventory)
        return {
            "path": str(inventory_path.relative_to(self.repo)),
            "sha256": digest(inventory_path),
            "records_sha256": inventory["records_sha256"],
            "view_count": 1,
            "file_count": len(records),
            "total_bytes": inventory["total_bytes"],
        }

    def _checkpoint(self, out: Path, step: int, payload: bytes = b"checkpoint") -> str:
        path = out / "ckpt" / f"step_{step:06d}.pt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        sha = digest(path)
        Path(f"{path}.sha256").write_text(f"{sha}  {path.name}\n", encoding="ascii")
        return sha

    def _full_manifest(
        self,
        job,
        sha: str,
        *,
        step: int = 20000,
        process_completed: bool = False,
    ) -> dict:
        return {
            "schema": "jointbuildgs.stage2.resume_manifest.v1",
            "output_path": job.out_container,
            "config_path": job.config_container,
            "config_file_sha256": job.config_sha256,
            "binding_sha256": {
                "training_config": job.training_config_binding_sha256,
                "effective_training_config": "2" * 64,
                "output_path": hashlib.sha256(
                    job.out_container.encode("utf-8")
                ).hexdigest(),
            },
            "max_iter": 20000,
            "checkpoint_steps": [5000, 10000, 15000, 20000],
            "step_semantics": "completed_optimizer_updates",
            "loss_csv_paths": list(job.loss_csv_paths),
            "last_completed_steps": step,
            "learning_runs_started": 1,
            "latest_full_checkpoint": {
                "path": f"{job.out_container}/ckpt/step_{step:06d}.pt",
                "sha256": sha,
                "completed_steps": step,
            },
            "process_completed": process_completed,
            "process_completed_steps": 20000 if process_completed else 0,
        }

    def _inspect(self, job):
        return driver.inspect_run_state(
            self.repo,
            job,
            expected_image_id=self.image_id,
            verifier_source_sha256=self.verifier_sha,
        )

    @staticmethod
    def _expected_identity() -> dict:
        return {
            "real_uid": driver.REQUIRED_HOST_UID,
            "real_gid": driver.REQUIRED_HOST_GID,
            "effective_uid": driver.REQUIRED_HOST_UID,
            "effective_gid": driver.REQUIRED_HOST_GID,
            "required_uid": driver.REQUIRED_HOST_UID,
            "required_gid": driver.REQUIRED_HOST_GID,
            "training_container_user": driver.TRAINING_CONTAINER_USER,
        }

    def test_dry_run_has_ten_docker_only_commands_and_two_gpu_preview(self) -> None:
        _payload, jobs = driver.load_resolved_jobs(self.repo, self.manifest)
        with mock.patch.object(
            driver,
            "require_host_driver_identity",
            return_value=self._expected_identity(),
        ):
            preview = driver._dry_run_payload(
                self.repo,
                self.manifest,
                jobs,
                "sha256:" + "a" * 64,
                "b" * 40,
            )
        self.assertEqual(preview["state"], "dry_run_validated")
        self.assertEqual(preview["learning_runs_started"], 0)
        self.assertEqual(
            preview["runtime"]["training_container_user"], "0:0"
        )
        self.assertEqual(
            preview["runtime"]["host_driver_identity"],
            self._expected_identity(),
        )
        self.assertEqual(
            preview["runtime"]["training_artifact_publication"],
            {
                "runtime_json": "0644",
                "full_state_checkpoint": "0644",
                "checkpoint_sha256_sidecar": "0644",
            },
        )
        self.assertFalse(
            any(key.startswith("torch_extensions") for key in preview["runtime"])
        )
        self.assertEqual(len(preview["jobs"]), 10)
        self.assertEqual({row["queue_gpu_preview"] for row in preview["jobs"]}, {0, 1})
        for row in preview["jobs"]:
            self.assertTrue(driver.command_is_docker_only(row["command"]))
            self.assertEqual(row["command"][:3], ["docker", "compose", "run"])
            self.assertIn("NVIDIA_VISIBLE_DEVICES=", row["command_string"])
            self.assertIn("--name", row["command"])
            self.assertIn(row["container_name"], row["command"])
            self.assertEqual(row["container_user"], "0:0")
            user_index = row["command"].index("--user")
            self.assertEqual(row["command"][user_index + 1], "0:0")
            self.assertNotIn("torch_extensions_dir", row)
            self.assertFalse(
                any(token.startswith("TORCH_EXTENSIONS_DIR=") for token in row["command"])
            )
            self.assertFalse(
                any(
                    token == "HOME" or token.startswith("HOME=")
                    for token in row["command"]
                )
            )
            self.assertRegex(
                row["container_name"],
                r"^jointbuildgs-p1w-20260721-(?:01|02|03|04a|04b)-seed(?:1001|1002)$",
            )

    def test_host_identity_is_exact_and_fails_closed(self) -> None:
        with (
            mock.patch.object(driver.os, "getuid", return_value=1000),
            mock.patch.object(driver.os, "getgid", return_value=1000),
            mock.patch.object(driver.os, "geteuid", return_value=1000),
            mock.patch.object(driver.os, "getegid", return_value=1000),
        ):
            self.assertEqual(
                driver.require_host_driver_identity(), self._expected_identity()
            )
        with (
            mock.patch.object(driver.os, "getuid", return_value=1000),
            mock.patch.object(driver.os, "getgid", return_value=1000),
            mock.patch.object(driver.os, "geteuid", return_value=0),
            mock.patch.object(driver.os, "getegid", return_value=0),
        ):
            with self.assertRaisesRegex(
                driver.DriverError, "exact host UID:GID 1000:1000"
            ):
                driver.require_host_driver_identity()

    def test_training_command_contract_rejects_user_or_environment_drift(self) -> None:
        name = driver.container_name_for("01_seed1001")
        command = driver.command_for("/workspace/config.yaml", 0, container_name=name)
        self.assertTrue(driver.command_is_docker_only(command))
        self.assertEqual(
            command,
            [
                "docker",
                "compose",
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "--user",
                "0:0",
                "--name",
                name,
                "-e",
                "NVIDIA_VISIBLE_DEVICES=0",
                "-e",
                "CUDA_VISIBLE_DEVICES=0",
                "dev",
                "python",
                "-m",
                "src.stage2.train",
                "--config",
                "/workspace/config.yaml",
            ],
        )
        with self.assertRaisesRegex(driver.DriverError, "unsafe Docker container name"):
            driver.command_for(
                "/workspace/config.yaml",
                0,
                container_name="unsafe name",
            )

        wrong_user = list(command)
        wrong_user[wrong_user.index("--user") + 1] = "1000:1000"
        self.assertFalse(driver.command_is_docker_only(wrong_user))

        with_extensions = list(command)
        service_index = with_extensions.index("dev")
        with_extensions[service_index:service_index] = [
            "-e",
            "TORCH_EXTENSIONS_DIR=/tmp/legacy-jit-cache",
        ]
        self.assertFalse(driver.command_is_docker_only(with_extensions))

        with_home = list(command)
        service_index = with_home.index("dev")
        with_home[service_index:service_index] = ["-e", "HOME=/tmp/injected"]
        self.assertFalse(driver.command_is_docker_only(with_home))

    def test_start_and_9h_guard_boundaries(self) -> None:
        self.assertTrue(driver.may_start_new_run(driver.STOP_START_SECONDS - 1e-6))
        self.assertFalse(driver.may_start_new_run(driver.STOP_START_SECONDS))
        self.assertIsNone(driver.guard_target(driver.WALL_GUARD_SECONDS - 1e-6, 5000))
        self.assertEqual(driver.guard_target(driver.WALL_GUARD_SECONDS, 0), 5000)
        self.assertEqual(driver.guard_target(driver.WALL_GUARD_SECONDS, 5000), 10000)
        self.assertEqual(driver.guard_target(driver.WALL_GUARD_SECONDS, 15000), 20000)
        self.assertIsNone(driver.guard_target(driver.WALL_GUARD_SECONDS, 20000))

    def test_checkpoint_requires_actual_sha_and_caches_unchanged_file(self) -> None:
        out = self.runs / "01/seed_1001"
        self._checkpoint(out, 5000, b"real durable state")
        cache: dict = {}
        self.assertTrue(driver.checkpoint_is_durable(out, 5000, sha_cache=cache))
        self.assertEqual(len(cache), 1)
        self.assertTrue(driver.checkpoint_is_durable(out, 5000, sha_cache=cache))
        self.assertEqual(len(cache), 1)
        checkpoint = out / "ckpt/step_005000.pt"
        Path(f"{checkpoint}.sha256").write_text(
            f"{'0' * 64}  {checkpoint.name}\n", encoding="ascii"
        )
        self.assertFalse(driver.checkpoint_is_durable(out, 5000, sha_cache=cache))

    def test_checkpoint_cache_rehashes_same_size_same_mtime_replacement(self) -> None:
        out = self.runs / "01/seed_1001"
        self._checkpoint(out, 5000, b"first-state")
        cache: dict = {}
        self.assertTrue(driver.checkpoint_is_durable(out, 5000, sha_cache=cache))
        checkpoint = out / "ckpt/step_005000.pt"
        original_stat = checkpoint.stat()
        replacement = checkpoint.with_name("replacement.pt")
        replacement.write_bytes(b"other-state")
        os.replace(replacement, checkpoint)
        os.utime(
            checkpoint,
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )
        # The old sidecar remains. A cache omitting inode/ctime would accept it.
        self.assertFalse(driver.checkpoint_is_durable(out, 5000, sha_cache=cache))

    def test_durable_20k_crash_is_partial_until_completion_manifest(self) -> None:
        _payload, jobs = driver.load_resolved_jobs(self.repo, self.manifest)
        job = next(item for item in jobs if item.job_id == "04a_seed1001")
        out = job.out_host
        sha = self._checkpoint(out, 20000, b"final state")
        state = self._inspect(job)
        self.assertFalse(state["completed"])
        self.assertFalse(state["winner_eligible"])
        self.assertTrue(state["partial"])
        full_manifest = self._full_manifest(job, sha)
        write_json(out / "full_state_manifest.json", full_manifest)
        with mock.patch.object(
            driver, "validate_checkpoint_payload", return_value=(True, None)
        ):
            state = self._inspect(job)
        self.assertFalse(state["completed"])
        self.assertTrue(state["partial"])

        full_manifest["process_completed"] = True
        full_manifest["process_completed_steps"] = 20000
        write_json(out / "full_state_manifest.json", full_manifest)
        with mock.patch.object(
            driver, "validate_checkpoint_payload", return_value=(True, None)
        ):
            state = self._inspect(job)
        self.assertTrue(state["completed"])
        self.assertTrue(state["winner_eligible"])
        self.assertFalse(state["partial"])

    def test_completion_rejects_extra_binding_key_and_nonexact_latest(self) -> None:
        _payload, jobs = driver.load_resolved_jobs(self.repo, self.manifest)
        job = next(item for item in jobs if item.job_id == "04b_seed1002")
        sha20 = self._checkpoint(job.out_host, 20000, b"state-20k")
        manifest = self._full_manifest(job, sha20, process_completed=True)
        manifest["binding_sha256"]["injected"] = "f" * 64
        write_json(job.out_host / "full_state_manifest.json", manifest)
        with mock.patch.object(
            driver, "validate_checkpoint_payload", return_value=(True, None)
        ):
            state = self._inspect(job)
        self.assertFalse(state["completed"])
        self.assertFalse(state["binding_valid"])

        sha15 = self._checkpoint(job.out_host, 15000, b"state-15k")
        manifest = self._full_manifest(
            job, sha15, step=15000, process_completed=True
        )
        write_json(job.out_host / "full_state_manifest.json", manifest)
        state = self._inspect(job)
        self.assertFalse(state["completed"])
        self.assertEqual(state["durable_checkpoint_steps"], [15000, 20000])
        self.assertTrue(state["latest_manifest_checkpoint_valid"])

    def test_completion_rejects_payload_validation_failure(self) -> None:
        _payload, jobs = driver.load_resolved_jobs(self.repo, self.manifest)
        job = jobs[0]
        sha = self._checkpoint(job.out_host, 20000, b"not-a-torch-checkpoint")
        write_json(
            job.out_host / "full_state_manifest.json",
            self._full_manifest(job, sha, process_completed=True),
        )
        with mock.patch.object(
            driver,
            "validate_checkpoint_payload",
            return_value=(False, "synthetic malformed payload"),
        ):
            state = self._inspect(job)
        self.assertFalse(state["completed"])
        self.assertFalse(state["checkpoint_payload_valid"])
        self.assertIn("synthetic malformed", state["checkpoint_payload_error"])

    def test_payload_verifier_runs_pinned_named_gpu_disabled_container(self) -> None:
        _payload, jobs = driver.load_resolved_jobs(self.repo, self.manifest)
        job = jobs[0]
        sha = self._checkpoint(job.out_host, 20000, b"payload-container-check")
        binding = {
            "training_config": job.training_config_binding_sha256,
            "effective_training_config": "2" * 64,
            "output_path": hashlib.sha256(
                job.out_container.encode("utf-8")
            ).hexdigest(),
        }
        checkpoint_container = f"{job.out_container}/ckpt/step_020000.pt"
        result = {
            "schema": "jointbuildgs.pilot_1wave.checkpoint_verification.v1",
            "state": "verified",
            "checkpoint_path": checkpoint_container,
            "checkpoint_sha256": sha,
            "completed_steps": 20000,
            "step_semantics": "completed_optimizer_updates",
            "binding_sha256": binding,
            "loss_csv_paths": list(job.loss_csv_paths),
            "learning_runs_started": 1,
            "verifier_source_path": str(
                driver.CONTAINER_REPO / driver.CHECKPOINT_VERIFIER_RELATIVE_PATH
            ),
            "verifier_source_sha256": self.verifier_sha,
            "read_only": True,
            "gpu_required": False,
        }
        completed = SimpleNamespace(
            returncode=0,
            stdout=(
                "container banner\n"
                + driver.CHECKPOINT_VERIFIER_RESULT_PREFIX
                + json.dumps(result, separators=(",", ":"))
                + "\n"
            ),
            stderr="",
        )
        verifier_name = f"{job.container_name}-checkpoint-verify"
        with (
            mock.patch.object(
                driver, "query_image_id", return_value=self.image_id
            ),
            mock.patch.object(driver, "_assert_container_absent"),
            mock.patch.object(driver, "_stop_container") as stop,
            mock.patch.object(driver, "_cleanup_container") as cleanup,
            mock.patch.object(driver.subprocess, "run", return_value=completed) as run,
        ):
            valid, error = driver.validate_checkpoint_payload(
                self.repo,
                job.out_host / "ckpt/step_020000.pt",
                checkpoint_container=checkpoint_container,
                verifier_container_name=verifier_name,
                expected_image_id=self.image_id,
                expected_verifier_source_sha256=self.verifier_sha,
                expected_sha256=sha,
                expected_binding_sha256=binding,
                expected_loss_csv_paths=job.loss_csv_paths,
            )
        self.assertTrue(valid, error)
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["docker", "compose", "run"])
        self.assertIn(verifier_name, command)
        self.assertIn("NVIDIA_VISIBLE_DEVICES=none", command)
        self.assertIn("CUDA_VISIBLE_DEVICES=-1", command)
        self.assertIn(checkpoint_container, command)
        stop.assert_called_once_with(
            self.repo, verifier_name, timeout_seconds=10
        )
        cleanup.assert_called_once_with(self.repo, verifier_name)

    def test_launch_rechecks_manifest_and_config_bytes(self) -> None:
        _payload, jobs = driver.load_resolved_jobs(self.repo, self.manifest)
        manifest_sha = digest(self.manifest)
        driver._verify_launch_bindings(
            resolved_manifest_path=self.manifest,
            resolved_manifest_sha256=manifest_sha,
            job=jobs[0],
        )
        self.manifest.chmod(0o644)
        self.manifest.write_text(self.manifest.read_text() + " ", encoding="utf-8")
        with self.assertRaisesRegex(driver.DriverError, "resolved manifest changed"):
            driver._verify_launch_bindings(
                resolved_manifest_path=self.manifest,
                resolved_manifest_sha256=manifest_sha,
                job=jobs[0],
            )

    def test_materialized_inventory_is_bound_and_full_byte_validation_fails_closed(self) -> None:
        payload, jobs = driver.load_resolved_jobs(self.repo, self.manifest)
        binding = driver._load_materialized_inventory_binding(self.repo, payload)
        attestation = driver.validate_materialized_input_files(self.repo, binding)
        self.assertTrue(attestation["validated"])
        self.assertEqual(attestation["file_count"], 7)
        first_record = binding.payload["records"][0]
        first_path = self.repo / first_record["path"]
        first_path.write_bytes(b"mutated-materialized-input")
        with self.assertRaisesRegex(driver.DriverError, "do not match inventory"):
            driver.validate_materialized_input_files(self.repo, binding)
        with self.assertRaisesRegex(driver.DriverError, "materialized input inventory changed"):
            # The lightweight per-launch check rejects inventory-manifest drift.
            job = jobs[0]
            job.materialized_inventory_host.write_text("{}\n", encoding="utf-8")
            driver._verify_launch_bindings(
                resolved_manifest_path=self.manifest,
                resolved_manifest_sha256=digest(self.manifest),
                job=job,
            )

    def test_execution_tree_gate_is_scoped_and_fails_closed(self) -> None:
        clean_sha = hashlib.sha256(b"").hexdigest()
        with mock.patch.object(
            driver,
            "query_execution_tree_state",
            return_value=(False, clean_sha, ()),
        ):
            self.assertEqual(
                driver.require_clean_execution_tree(
                    self.repo, expected_status_sha256=clean_sha
                ),
                clean_sha,
            )
        with mock.patch.object(
            driver,
            "query_execution_tree_state",
            return_value=(
                True,
                "f" * 64,
                ("?? phases/p2-gsjso/scripts/injected.py",),
            ),
        ):
            with self.assertRaisesRegex(driver.DriverError, "execution tree is dirty"):
                driver.require_clean_execution_tree(self.repo)
        self.assertNotIn("docs", driver.EXECUTION_TREE_PATHS)
        self.assertNotIn("phases/p2-gsjso/runs", driver.EXECUTION_TREE_PATHS)
        self.assertIn(
            "scripts/experiments/pilot_1wave", driver.EXECUTION_TREE_PATHS
        )

    def test_config_cannot_rebind_materialized_inventory(self) -> None:
        payload = json.loads(self.manifest.read_text())
        record = payload["jobs"][0]
        config_path = self.repo / record["config_path"]
        config = yaml.safe_load(config_path.read_text())
        config["pilot_materialized_input_inventory_sha256"] = "0" * 64
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        record["config_sha256"] = digest(config_path)
        write_json(self.manifest, payload)
        with self.assertRaisesRegex(driver.DriverError, "inventory binding mismatch"):
            driver.load_resolved_jobs(self.repo, self.manifest)

    def test_driver_lock_is_exclusive_and_mode_0644(self) -> None:
        path = self.repo / "run/training/driver_manifest.json"
        with driver.exclusive_driver_lock(path) as lock_path:
            self.assertEqual(lock_path.stat().st_mode & 0o777, 0o644)
            with self.assertRaisesRegex(driver.DriverError, "another P1W driver"):
                with driver.exclusive_driver_lock(path):
                    pass

    def test_finalization_grace_default_is_one_hour(self) -> None:
        args = driver.parser().parse_args([])
        self.assertEqual(args.finalization_grace_seconds, 3600.0)

    def test_popen_failure_still_cleans_owned_deterministic_container(self) -> None:
        _payload, jobs = driver.load_resolved_jobs(self.repo, self.manifest)
        cleanup = mock.Mock()
        stop = mock.Mock()
        with (
            mock.patch.object(driver, "query_git_dirty", return_value=(False, "d" * 64)),
            mock.patch.object(
                driver,
                "query_execution_tree_state",
                return_value=(False, "e" * 64, ()),
            ),
            mock.patch.object(
                driver, "query_compose_config_sha256", return_value="c" * 64
            ),
            mock.patch.object(driver, "query_git_head", return_value="b" * 40),
            mock.patch.object(
                driver, "query_image_id", return_value="sha256:" + "a" * 64
            ),
            mock.patch.object(
                driver,
                "require_host_driver_identity",
                return_value=self._expected_identity(),
            ),
            mock.patch.object(driver, "_assert_container_absent"),
            mock.patch.object(driver, "_stop_container", stop),
            mock.patch.object(driver, "_cleanup_container", cleanup),
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic Popen failure"):
                driver.execute_queue(
                    repo=self.repo,
                    resolved_manifest_path=self.manifest,
                    driver_manifest_path=self.repo / "run/training/driver_manifest.json",
                    jobs=jobs,
                    image_id="sha256:" + "a" * 64,
                    git_head="b" * 40,
                    poll_seconds=1.0,
                    checkpoint_grace_seconds=60.0,
                    signal_grace_seconds=1.0,
                    popen_factory=mock.Mock(
                        side_effect=RuntimeError("synthetic Popen failure")
                    ),
                )
        stop.assert_called_once_with(
            self.repo, jobs[0].container_name, timeout_seconds=10
        )
        cleanup.assert_called_once_with(self.repo, jobs[0].container_name)
        mode = (
            self.repo / "run/training/driver_manifest.json"
        ).stat().st_mode & 0o777
        self.assertEqual(mode, 0o644)

    def test_compose_digest_drift_blocks_launch_before_popen(self) -> None:
        _payload, jobs = driver.load_resolved_jobs(self.repo, self.manifest)
        popen = mock.Mock()
        with (
            mock.patch.object(driver, "query_git_dirty", return_value=(False, "d" * 64)),
            mock.patch.object(
                driver,
                "query_execution_tree_state",
                return_value=(False, "e" * 64, ()),
            ),
            mock.patch.object(
                driver,
                "query_compose_config_sha256",
                side_effect=("c" * 64, "f" * 64),
            ),
            mock.patch.object(driver, "query_git_head", return_value="b" * 40),
            mock.patch.object(
                driver, "query_image_id", return_value="sha256:" + "a" * 64
            ),
            mock.patch.object(
                driver,
                "require_host_driver_identity",
                return_value=self._expected_identity(),
            ),
        ):
            with self.assertRaisesRegex(driver.DriverError, "Compose config changed"):
                driver.execute_queue(
                    repo=self.repo,
                    resolved_manifest_path=self.manifest,
                    driver_manifest_path=self.repo / "run/training/driver_manifest.json",
                    jobs=jobs,
                    image_id="sha256:" + "a" * 64,
                    git_head="b" * 40,
                    poll_seconds=1.0,
                    checkpoint_grace_seconds=60.0,
                    signal_grace_seconds=1.0,
                    popen_factory=popen,
                )
        popen.assert_not_called()

    def test_driver_rejects_output_inside_config_bundle(self) -> None:
        payload = json.loads(self.manifest.read_text())
        payload["training_output_root"]["path"] = str(
            (self.bundle / "runs").relative_to(self.repo)
        )
        write_json(self.manifest, payload)
        with self.assertRaisesRegex(driver.DriverError, "overlaps immutable"):
            driver.load_resolved_jobs(self.repo, self.manifest)

    def test_driver_rejects_noncanonical_job_and_output_schema(self) -> None:
        payload = json.loads(self.manifest.read_text())
        record = payload["jobs"][0]
        config_path = self.repo / record["config_path"]
        config = yaml.safe_load(config_path.read_text())
        config["pilot_condition"] = "02"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        record["config_sha256"] = digest(config_path)
        write_json(self.manifest, payload)
        with self.assertRaisesRegex(driver.DriverError, "condition mismatch"):
            driver.load_resolved_jobs(self.repo, self.manifest)

        # Rebuild, then bind the first output to a noncanonical nested directory.
        shutil.rmtree(self.bundle)
        self.bundle.mkdir(parents=True)
        self.manifest = self._resolved_manifest()
        payload = json.loads(self.manifest.read_text())
        record = payload["jobs"][0]
        config_path = self.repo / record["config_path"]
        config = yaml.safe_load(config_path.read_text())
        config["out_dir"] += "/nested"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        record["out_dir"] = config["out_dir"]
        record["config_sha256"] = digest(config_path)
        write_json(self.manifest, payload)
        with self.assertRaisesRegex(driver.DriverError, "not the canonical"):
            driver.load_resolved_jobs(self.repo, self.manifest)

    def test_simulated_queue_starts_two_gpus_then_guards_at_next_5k(self) -> None:
        _payload, jobs = driver.load_resolved_jobs(self.repo, self.manifest)

        class FakeClock:
            value = 0.0

            def __call__(self) -> float:
                return self.value

            def sleep(self, seconds: float) -> None:
                self.value += seconds

        clock = FakeClock()
        processes = []

        class FakeProcess:
            def __init__(self, job, pid: int) -> None:
                self.job = job
                self.pid = pid
                self.return_code = None
                self.checkpoint_written = False

            def poll(self):
                if clock.value >= 36000.0 and not self.checkpoint_written:
                    sha = self_test._checkpoint(
                        self.job.out_host, 5000, f"state-{self.pid}".encode()
                    )
                    write_json(
                        self.job.out_host / "full_state_manifest.json",
                        {
                            "schema": "jointbuildgs.stage2.resume_manifest.v1",
                            "binding_sha256": {"training_config": "5" * 64},
                            "last_completed_steps": 5000,
                            "learning_runs_started": 1,
                            "latest_full_checkpoint": {
                                "path": str(
                                    (
                                        self.job.out_host
                                        / "ckpt/step_005000.pt"
                                    ).resolve()
                                ),
                                "sha256": sha,
                                "completed_steps": 5000,
                            },
                            "process_completed": False,
                        },
                    )
                    self.checkpoint_written = True
                return self.return_code

        self_test = self

        def fake_popen(command, **_kwargs):
            process = FakeProcess(jobs[len(processes)], 2000 + len(processes))
            processes.append(process)
            return process

        def fake_signal(_repo, running, sig):
            if sig in (driver.signal.SIGINT, driver.signal.SIGTERM, driver.signal.SIGKILL):
                running.process.return_code = 130

        driver._CHECKPOINT_SHA_CACHE.clear()
        with (
            mock.patch.object(driver, "query_git_dirty", return_value=(False, "d" * 64)),
            mock.patch.object(
                driver,
                "query_execution_tree_state",
                return_value=(False, "e" * 64, ()),
            ),
            mock.patch.object(
                driver, "query_compose_config_sha256", return_value="c" * 64
            ),
            mock.patch.object(driver, "query_git_head", return_value="b" * 40),
            mock.patch.object(driver, "query_image_id", return_value="sha256:" + "a" * 64),
            mock.patch.object(
                driver,
                "require_host_driver_identity",
                return_value=self._expected_identity(),
            ),
            mock.patch.object(driver, "_signal_running", side_effect=fake_signal),
            mock.patch.object(driver, "_assert_container_absent"),
            mock.patch.object(driver, "_cleanup_container"),
            mock.patch.object(driver, "_stop_container"),
        ):
            result = driver.execute_queue(
                repo=self.repo,
                resolved_manifest_path=self.manifest,
                driver_manifest_path=self.repo / "run/training/driver_manifest.json",
                jobs=jobs,
                image_id="sha256:" + "a" * 64,
                git_head="b" * 40,
                poll_seconds=3600.0,
                checkpoint_grace_seconds=7200.0,
                signal_grace_seconds=60.0,
                clock=clock,
                sleeper=clock.sleep,
                popen_factory=fake_popen,
            )

        self.assertEqual(len(processes), 2)
        self.assertEqual(result["state"], "guarded_partial")
        self.assertTrue(result["guard"]["triggered"])
        self.assertEqual(result["runtime"]["compose_config_sha256"], "c" * 64)
        self.assertEqual(result["runtime"]["training_container_user"], "0:0")
        self.assertEqual(
            result["runtime"]["host_driver_identity"], self._expected_identity()
        )
        self.assertEqual(
            result["runtime"]["training_artifact_publication"],
            {
                "runtime_json": "0644",
                "full_state_checkpoint": "0644",
                "checkpoint_sha256_sidecar": "0644",
            },
        )
        self.assertFalse(
            any(key.startswith("torch_extensions") for key in result["runtime"])
        )
        self.assertTrue(result["runtime"]["execution_tree"]["clean"])
        self.assertTrue(
            result["runtime"]["materialized_input_validation"]["validated"]
        )
        self.assertEqual(result["learning_runs_started"], 2)
        states = [row["state"] for row in result["jobs"]]
        self.assertEqual(states[:2], ["partial_guarded", "partial_guarded"])
        self.assertEqual(states[2:], ["deferred_8p5h_gate"] * 8)
        commands = [row["command"] for row in result["jobs"][:2]]
        self.assertEqual(
            [row["container_user"] for row in result["jobs"][:2]],
            ["0:0", "0:0"],
        )
        self.assertTrue(
            all("torch_extensions_dir" not in row for row in result["jobs"][:2])
        )
        self.assertEqual(
            [command[command.index("--user") + 1] for command in commands],
            ["0:0", "0:0"],
        )
        self.assertTrue(
            all(
                not any(token.startswith("TORCH_EXTENSIONS_DIR=") for token in command)
                for command in commands
            )
        )
        self.assertIn("NVIDIA_VISIBLE_DEVICES=0", commands[0])
        self.assertIn("NVIDIA_VISIBLE_DEVICES=1", commands[1])
        self.assertEqual(
            [row["guard_target_step"] for row in result["jobs"][:2]],
            [5000, 5000],
        )


if __name__ == "__main__":
    unittest.main()

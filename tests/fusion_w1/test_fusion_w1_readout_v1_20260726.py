#!/usr/bin/env python3
"""Synthetic and contract tests for the Fusion W1 §5 readout driver.

No training, GPU readout, Roofer, val3dity, or reference scoring is executed.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[2] / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_readout_v1_20260726.py"
SPEC = importlib.util.spec_from_file_location("fusion_w1_readout_tested", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

REPO = Path(__file__).resolve().parents[2]
CONFIG_PATH = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_v1_20260726.json"
)
RECOVERY2_POLICY_PATH = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_infra_retry2_20260726.json"
)
WRAPPER = SCRIPT.parent / "run_fusion_w1_readout_v1_20260726.sh"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def config_copy() -> dict:
    return copy.deepcopy(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))


def minimal_repo_config(root: Path) -> dict:
    config = config_copy()
    config["training"]["root"] = "training"
    config["outputs"]["root"] = "readout"
    config["outputs"]["job_template"] = (
        "readout/by_building/{building_id}/arm_{arm}/{run}"
    )
    config["outputs"]["runtime_counters"] = "readout/runtime_counters.json"
    config["outputs"]["runtime_counters_lock"] = (
        "readout/runtime_counters.json.lock"
    )
    config["outputs"]["scores_csv"] = "readout/w1_scores_building.csv"
    config["outputs"]["summary_csv"] = "readout/w1_summary.csv"
    config["outputs"]["panels_dir"] = "readout/w1_panels"
    config["outputs"]["failures_jsonl"] = "readout/failures.jsonl"
    config["p0prime"]["scores_csv"] = "p0prime/scores.csv"
    config["p0prime"]["job_template"] = "p0prime/by_building/{building_id}"
    config["pointcloudification"]["writable_environment"] = {
        "HOME": "runtime_env/home",
        "XDG_CACHE_HOME": "runtime_env/xdg_cache",
        "TORCH_EXTENSIONS_DIR": "runtime_env/torch_extensions_seeded_v2",
    }
    return config


def make_training_job(
    root: Path,
    config: dict,
    *,
    building_id: str = "DEBY_LOD2_42364609",
    arm: str = "A",
    run: str = "r1",
) -> dict[str, Path]:
    job = (
        root
        / "training"
        / "by_building"
        / building_id
        / f"arm_{arm}"
        / run
    )
    checkpoint = job / "ckpt/step_030000.pt"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_bytes(b"synthetic-full-state-checkpoint")
    final_checkpoint = job / "ckpt/final.pt"
    final_checkpoint.write_bytes(b"synthetic-legacy-export-checkpoint")
    full_state = job / "full_state_manifest.json"
    write_json(
        full_state,
        {
            "schema": "jointbuildgs.stage2.resume_manifest.v1",
            "process_completed": True,
            "process_completed_steps": 30000,
        },
    )
    data_root = root / "data"
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        path = data_root / "sparse/0" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"synthetic-{name}".encode())
    image = data_root / "images/a.jpg"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"synthetic-image")
    supervision = data_root / "supervision.csv"
    write_csv(supervision, ["image_name"], [{"image_name": "a.jpg"}])
    materialization = job / "materialization_manifest.json"
    write_json(
        materialization,
        {
            "schema": "jointbuildgs.fusion_w1.training_materialization.v1",
            "status": "PASSED",
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
            "preprocess": {
                "data_root": "data",
                "supervision_index": "data/supervision.csv",
            },
            "view_roles": {"train_views": ["a.jpg"]},
        },
    )
    completed = job / "completed.json"
    write_json(
        completed,
        {
            "schema": "jointbuildgs.fusion_w1.training_completed.v1",
            "job_key": f"{building_id}/arm_{arm}/{run}",
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
            "return_code": 0,
            "materialization": {
                "path": str(materialization.relative_to(root)),
                "sha256": sha(materialization),
            },
            "training_completion": {
                "status": "PASSED",
                "completed_optimizer_updates": 30000,
                "checkpoint": str(checkpoint.relative_to(root)),
                "checkpoint_sha256": sha(checkpoint),
                "final_checkpoint": str(final_checkpoint.relative_to(root)),
                "final_checkpoint_sha256": sha(final_checkpoint),
                "full_state_manifest": str(full_state.relative_to(root)),
                "full_state_manifest_sha256": sha(full_state),
            },
        },
    )
    return {
        "job": job,
        "checkpoint": checkpoint,
        "final_checkpoint": final_checkpoint,
        "full_state": full_state,
        "materialization": materialization,
        "completed": completed,
    }


def make_infrastructure_retry_success(
    root: Path,
    paths: dict[str, Path],
) -> dict[str, Path]:
    job = paths["job"]
    attempt = job / "infra_retry_01"
    moved: dict[str, Path] = {}
    for key, relative in (
        ("checkpoint", Path("ckpt/step_030000.pt")),
        ("final_checkpoint", Path("ckpt/final.pt")),
        ("full_state", Path("full_state_manifest.json")),
    ):
        destination = attempt / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        paths[key].replace(destination)
        moved[key] = destination

    expected_job_key = "DEBY_LOD2_42364609/arm_A/r1"
    original_log = job / "training.log"
    original_log.write_text(
        "gsplat/cuda/_backend.py\n"
        "PermissionError: [Errno 13] Permission denied: '/.cache'\n",
        encoding="utf-8",
    )
    original_started = job / "started.json"
    write_json(
        original_started,
        {
            "schema": "jointbuildgs.fusion_w1.training_started.v1",
            "job_key": expected_job_key,
            "materialization_manifest_sha256": sha(paths["materialization"]),
        },
    )
    original_failed = job / "failed.json"
    write_json(
        original_failed,
        {
            "schema": "jointbuildgs.fusion_w1.training_failed.v1",
            "job_key": expected_job_key,
            "return_code": 1,
            "log_sha256": sha(original_log),
        },
    )
    original_full_state = job / "full_state_manifest.json"
    write_json(
        original_full_state,
        {
            "schema": "jointbuildgs.stage2.resume_manifest.v1",
            "learning_runs_started": 0,
            "learning_runs_incremented_this_process": False,
            "start_completed_steps": 0,
            "last_completed_steps": 0,
            "latest_full_checkpoint": None,
        },
    )
    raw_policy = {
        "schema": "jointbuildgs.fusion_w1.training_infra_retry_policy.v1",
        "status": "APPROVED",
        "attempt_directory": "infra_retry_01",
        "required_failure": {
            "artifact_sha256": {
                "started": sha(original_started),
                "failed": sha(original_failed),
                "log": sha(original_log),
                "full_state": sha(original_full_state),
            }
        },
    }
    policy_path = root / "retry_policy.json"
    write_json(policy_path, raw_policy)
    policy = {
        "path": str(policy_path.relative_to(root)),
        "sha256": sha(policy_path),
        **raw_policy,
    }

    retry_key = f"{expected_job_key}/infra_retry_01"
    snapshot_sha = "a" * 64
    retry_started = attempt / "retry_started.json"
    write_json(
        retry_started,
        {
            "schema": "jointbuildgs.fusion_w1.training_infra_retry_started.v1",
            "job_key": expected_job_key,
            "retry_key": retry_key,
            "policy": policy,
            "materialization": {
                "path": str(paths["materialization"].relative_to(root)),
                "sha256": sha(paths["materialization"]),
            },
        },
    )

    completed = json.loads(paths["completed"].read_text(encoding="utf-8"))
    training_completion = completed["training_completion"]
    training_completion.update(
        {
            "checkpoint": str(moved["checkpoint"].relative_to(root)),
            "checkpoint_sha256": sha(moved["checkpoint"]),
            "final_checkpoint": str(moved["final_checkpoint"].relative_to(root)),
            "final_checkpoint_sha256": sha(moved["final_checkpoint"]),
            "full_state_manifest": str(moved["full_state"].relative_to(root)),
            "full_state_manifest_sha256": sha(moved["full_state"]),
        }
    )
    retry_completed = attempt / "retry_completed.json"
    write_json(
        retry_completed,
        {
            "schema": "jointbuildgs.fusion_w1.training_infra_retry_completed.v1",
            "job_key": expected_job_key,
            "retry_key": retry_key,
            "return_code": 0,
            "retry_started_receipt": {
                "path": str(retry_started.relative_to(root)),
                "sha256": sha(retry_started),
            },
            "original_failure_snapshot_sha256": snapshot_sha,
            "training_completion": training_completion,
        },
    )
    completed["infrastructure_retry"] = {
        "policy": policy,
        "original_started_receipt": {
            "path": str(original_started.relative_to(root)),
            "sha256": sha(original_started),
        },
        "original_failed_receipt": {
            "path": str(original_failed.relative_to(root)),
            "sha256": sha(original_failed),
        },
        "retry_started_receipt": {
            "path": str(retry_started.relative_to(root)),
            "sha256": sha(retry_started),
        },
        "retry_completed_receipt": {
            "path": str(retry_completed.relative_to(root)),
            "sha256": sha(retry_completed),
        },
        "original_file_snapshot_sha256": snapshot_sha,
        "resolved_config_difference_keys": ["out_dir"],
        "optimizer_restart_completed_steps": 0,
    }
    write_json(paths["completed"], completed)
    return {
        **paths,
        **moved,
        "attempt": attempt,
        "original_started": original_started,
        "original_failed": original_failed,
        "original_full_state": original_full_state,
        "original_log": original_log,
        "retry_started": retry_started,
        "retry_completed": retry_completed,
        "policy": policy_path,
    }


def make_readout_preoutput_cache_failure(
    root: Path,
    config: dict,
    *,
    building_id: str = "DEBY_LOD2_42364609",
    arm: str = "A",
    run: str = "r1",
) -> dict[str, Path]:
    """Build the exact immutable pre-output failure needed by the retry gate."""

    job = MODULE.job_dir(config, building_id, arm, run, repo=root)
    job.mkdir(parents=True)
    key = MODULE.job_key(building_id, arm, run)
    checkpoint = root / "training/checkpoint.pt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"synthetic-readout-checkpoint")
    materialization = job / "materialization.json"
    write_json(
        materialization,
        {
            "schema": MODULE.MATERIALIZATION_SCHEMA,
            "state": "PASSED",
            "job_key": key,
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
        },
    )
    output = job / "pointcloud/readout.npz"
    output_rel = str(output.relative_to(root))
    invocation = job / "extract_invocation.json"
    write_json(
        invocation,
        {
            "schema": "jointbuildgs.fusion_w1.extract_invocation.v1",
            "state": "AUTHORIZED",
            "created_at": "2026-07-26T00:00:00+09:00",
            "run_id": config["run_id"],
            "job_key": key,
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
            "training_checkpoint": {
                "path": str(checkpoint.relative_to(root)),
                "sha256": sha(checkpoint),
            },
            "output": output_rel,
            "argv": [
                "phases/p2-gsjso/scripts/tum_mob_tsdf_extract.py",
                "--checkpoint",
                str(checkpoint.relative_to(root)),
                "--out",
                output_rel,
                "--no-sem",
            ],
            "retry_allowed": False,
        },
    )
    started = job / "readout_started.json"
    write_json(
        started,
        {
            "schema": MODULE.JOB_SCHEMA,
            "state": "STARTED",
            "created_at": "2026-07-26T00:00:01+09:00",
            "run_id": config["run_id"],
            "job_key": key,
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
            "stage": "readout",
            "invocation": {
                "path": str(invocation.relative_to(root)),
                "sha256": sha(invocation),
            },
            "retry_allowed": False,
        },
    )
    log = job / "extract.stdout.log"
    log.write_text(
        "gsplat/cuda/_backend.py\n"
        "PermissionError: [Errno 13] Permission denied: '/.cache'\n",
        encoding="utf-8",
    )
    failed = job / "failed.json"
    write_json(
        failed,
        {
            "schema": "jointbuildgs.fusion_w1.readout_failure.v1",
            "state": "FAILED",
            "created_at": "2026-07-26T00:00:02+09:00",
            "run_id": config["run_id"],
            "job_key": key,
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
            "stage": "readout",
            "message": "point-cloud readout failed",
            "retry_allowed": False,
        },
    )
    artifact_paths = {
        "materialization": materialization,
        "invocation": invocation,
        "started": started,
        "log": log,
        "failed": failed,
    }
    policy = root / "configs/readout_retry.json"
    write_json(
        policy,
        {
            "schema": MODULE.READOUT_RETRY_POLICY_SCHEMA,
            "status": "APPROVED",
            "run_id": config["run_id"],
            "approved_by": "김휘영",
            "retry_kind": "GSPLAT_JIT_CACHE_PERMISSION_PREOUTPUT",
            "job_key": key,
            "stage": "readout",
            "required_pre_retry_head": "a" * 40,
            "required_retry_commit_distance": 1,
            "allowed_retry_commit_paths": ["synthetic-retry-change"],
            "maximum_retries_per_job": 1,
            "attempt_directory": MODULE.READOUT_RETRY_ATTEMPT_DIRECTORY,
            "writable_environment": {
                "HOME": "runtime_env/home",
                "XDG_CACHE_HOME": "runtime_env/xdg_cache",
                "TORCH_EXTENSIONS_DIR": "runtime_env/torch_extensions",
            },
            "allowed_invocation_differences": [
                "output",
                "argv_value_after_--out",
            ],
            "required_failure": {
                "artifact_sha256": {
                    label: sha(path) for label, path in artifact_paths.items()
                },
                "log_markers": [
                    "gsplat/cuda/_backend.py",
                    "PermissionError: [Errno 13] Permission denied: '/.cache'",
                ],
                "required_absent_outputs": [
                    "pointcloud/readout.npz",
                    "extract_receipt.json",
                    "classification_invocation.json",
                    "classification_receipt.json",
                    "roofer_invocation.json",
                    "roofer_receipt.json",
                    "score_receipt.json",
                    "complete.json",
                ],
                "required_counter_values": {
                    "readout_runs_started": 1,
                    "roofer_runs_started": 0,
                    "scoring_runs_started": 0,
                },
            },
            "preservation_contract": {
                "original_materialization_immutable": True,
                "original_invocation_immutable": True,
                "original_started_receipt_immutable": True,
                "original_failed_receipt_immutable": True,
                "original_log_immutable": True,
                "retry_receipts_exclusive": True,
                "retry_output_namespace_separate": True,
            },
            "counter_contract": {
                "retry_is_same_authorized_readout": True,
                "second_readout_started_receipt_forbidden": True,
                "readout_runs_started_increment": 0,
            },
        },
    )
    return {
        "job": job,
        "checkpoint": checkpoint,
        "materialization": materialization,
        "invocation": invocation,
        "started": started,
        "log": log,
        "failed": failed,
        "output": output,
        "policy": policy,
    }


def make_readout_recovery2_fixture(
    root: Path,
    config: dict,
) -> dict[str, Path]:
    paths = make_readout_preoutput_cache_failure(root, config)
    building_id = "DEBY_LOD2_42364609"
    key = f"{building_id}/arm_A/r1"
    MODULE.prepare_extract_infra_retry(
        config,
        paths["policy"],
        building_id,
        "A",
        "r1",
        repo=root,
        validate_git=False,
    )
    prior_attempt = paths["job"] / MODULE.READOUT_RETRY_ATTEMPT_DIRECTORY
    prior_log = prior_attempt / "extract.stdout.log"
    prior_log.write_text(
        "Error building extension 'gsplat_cuda'\n"
        "returned non-zero exit status 137\n"
        "Killed\n"
        "ninja: build stopped: subcommand failed\n",
        encoding="utf-8",
    )
    MODULE.record_extract_infra_retry_failure(
        config,
        building_id,
        "A",
        "r1",
        message="synthetic cache-build OOM",
        repo=root,
    )

    common_cache = root / "runtime_env/torch_extensions/gsplat_cuda"
    common_cache.mkdir(parents=True)
    (common_cache / "build.ninja").write_text("partial-build\n", encoding="utf-8")
    (common_cache / "partial.cuda.o").write_bytes(b"partial-object")

    training_attempt = root / "training-success/infra_retry_01"
    source_cache = training_attempt / "runtime_env/torch_extensions/gsplat_cuda"
    source_cache.mkdir(parents=True)
    (source_cache / "build.ninja").write_text("complete-build\n", encoding="utf-8")
    (source_cache / "gsplat_cuda.so").write_bytes(b"synthetic-complete-extension")
    (source_cache / "kernel.cuda.o").write_bytes(b"synthetic-kernel-object")
    training_log = training_attempt / "training.log"
    training_log.write_text("training completed 30000\n", encoding="utf-8")
    training_started = training_attempt / "retry_started.json"
    write_json(
        training_started,
        {
            "schema": MODULE.RETRY_STARTED_SCHEMA,
            "job_key": key,
            "retry_key": f"{key}/{MODULE.RETRY_ATTEMPT_DIRECTORY}",
            "docker_image": {
                "image": config["pointcloudification"]["image"],
                "image_id": config["pointcloudification"]["image_id"],
            },
            "environment": {
                "TORCH_EXTENSIONS_DIR": (
                    "/workspace/JointBuildGS/"
                    + str(source_cache.parent.relative_to(root))
                )
            },
        },
    )
    training_completed = training_attempt / "retry_completed.json"
    write_json(
        training_completed,
        {
            "schema": MODULE.RETRY_COMPLETED_SCHEMA,
            "job_key": key,
            "return_code": 0,
            "training_completion": {
                "status": "PASSED",
                "completed_optimizer_updates": 30000,
            },
        },
    )
    completed = root / "training-success/completed.json"
    write_json(
        completed,
        {
            "schema": "jointbuildgs.fusion_w1.training_completed.v1",
            "job_key": key,
            "return_code": 0,
            "log_sha256": sha(training_log),
            "infrastructure_retry": {
                "retry_completed_receipt": {
                    "path": str(training_completed.relative_to(root)),
                    "sha256": sha(training_completed),
                }
            },
        },
    )

    original = {
        "materialization": paths["materialization"],
        "invocation": paths["invocation"],
        "started": paths["started"],
        "log": paths["log"],
        "failed": paths["failed"],
    }
    prior = {
        "retry_started": prior_attempt / "retry_started.json",
        "invocation": prior_attempt / "extract_invocation.json",
        "log": prior_log,
        "retry_failed": prior_attempt / "retry_failed.json",
    }
    source_inventory = MODULE._cache_inventory(source_cache, repo=root)
    common_inventory = MODULE._cache_inventory(common_cache, repo=root)
    policy_payload = copy.deepcopy(
        json.loads(RECOVERY2_POLICY_PATH.read_text(encoding="utf-8"))
    )
    policy_payload["required_pre_recovery_head"] = "a" * 40
    policy_payload["allowed_recovery_commit_paths"] = ["synthetic-recovery2-change"]
    policy_payload["allowed_recovery_commit_paths"].append(
        MODULE.READOUT_RECOVERY2_POLICY_RELATIVE.as_posix()
    )
    policy_payload["required_original_failure"]["artifact_sha256"] = {
        label: sha(path) for label, path in original.items()
    }
    policy_payload["required_prior_retry_failure"]["artifact_sha256"] = {
        label: sha(path) for label, path in prior.items()
    }
    policy_payload["writable_environment"] = config["pointcloudification"][
        "writable_environment"
    ]
    policy_payload["successful_training_cache_source"].update(
        {
            key_name: source_inventory[key_name]
            for key_name in (
                "root",
                "inventory_format",
                "inventory_sha256",
                "files_n",
                "bytes_n",
            )
        }
    )
    policy_payload["successful_training_cache_source"]["required_key_files"] = {
        "gsplat_cuda.so": sha(source_cache / "gsplat_cuda.so"),
        "build.ninja": sha(source_cache / "build.ninja"),
    }
    policy_payload["successful_training_cache_source"][
        "successful_training_artifacts"
    ] = {
        "completed": {
            "path": str(completed.relative_to(root)),
            "sha256": sha(completed),
        },
        "retry_started": {
            "path": str(training_started.relative_to(root)),
            "sha256": sha(training_started),
        },
        "retry_completed": {
            "path": str(training_completed.relative_to(root)),
            "sha256": sha(training_completed),
        },
        "log": {
            "path": str(training_log.relative_to(root)),
            "sha256": sha(training_log),
        },
    }
    policy_payload["successful_training_cache_source"]["docker_image_id"] = (
        config["pointcloudification"]["image_id"]
    )
    policy_payload["required_common_cache_before_seed"].update(
        {
            key_name: common_inventory[key_name]
            for key_name in (
                "root",
                "inventory_format",
                "inventory_sha256",
                "files_n",
                "bytes_n",
            )
        }
    )
    seed_destination = (
        root / "runtime_env/torch_extensions_seeded_v2/gsplat_cuda"
    )
    policy_payload["required_seed_destination_absent"] = {
        "root": str(seed_destination.relative_to(root)),
        "must_be_absent_before_publish": True,
    }
    policy = root / MODULE.READOUT_RECOVERY2_POLICY_RELATIVE
    write_json(policy, policy_payload)
    return {
        **paths,
        "prior_attempt": prior_attempt,
        "prior_log": prior_log,
        "source_cache": source_cache,
        "common_cache": common_cache,
        "seed_destination": seed_destination,
        "training_started": training_started,
        "training_completed": training_completed,
        "training_log": training_log,
        "training_root_completed": completed,
        "recovery2_policy": policy,
    }


class ConfigContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = MODULE.load_config(CONFIG_PATH)

    def test_fixed_smoke_job_is_failure_42364609_arm_a_r1(self) -> None:
        self.assertEqual(
            self.config["smoke_job"]["job_key"],
            "DEBY_LOD2_42364609/arm_A/r1",
        )

    def test_resource_and_roofer_contracts_are_exact(self) -> None:
        self.assertEqual(self.config["resource_lock"]["memory"], "24g")
        self.assertEqual(self.config["resource_lock"]["memory_swap"], "24g")
        self.assertFalse(
            self.config["resource_lock"]["concurrent_with_training"]
        )
        self.assertEqual(
            self.config["resource_lock"]["failed_job_retry"], "forbidden"
        )
        self.assertEqual(
            self.config["roofer"]["parameters"],
            [
                "--id-attribute",
                "building_id",
                "--jobs",
                "3",
                "--srs",
                "EPSG:25832",
                "--bld-class",
                "6",
                "--grnd-class",
                "2",
                "--lod22",
            ],
        )
        self.assertIn("@sha256:", self.config["roofer"]["image"])
        self.assertEqual(
            self.config["queue_contract"][
                "same_error_type_consecutive_building_stop_n"
            ],
            3,
        )

    def test_readout_reuses_locked_extractor_and_disables_semantics(self) -> None:
        pointcloud = self.config["pointcloudification"]
        self.assertEqual(
            pointcloud["script"],
            "phases/p2-gsjso/scripts/tum_mob_tsdf_extract.py",
        )
        self.assertFalse(pointcloud["semantic_pass"])
        self.assertEqual(pointcloud["footprint_buffer_m"], 15.0)
        self.assertEqual(pointcloud["voxel_m"], 0.05)
        self.assertEqual(pointcloud["minimum_observations"], 3)
        self.assertEqual(
            self.config["training"]["extract_checkpoint_relpath"],
            "ckpt/final.pt",
        )
        extractor = (
            REPO / pointcloud["script"]
        ).read_text(encoding="utf-8")
        trainer = (
            REPO / self.config["training"]["trainer_source"]
        ).read_text(encoding="utf-8")
        self.assertIn('sd = ck["state_dict"]', extractor)
        self.assertIn(
            'torch.save(final_ckpt, out_dir / "ckpt" / "final.pt")',
            trainer,
        )

    def test_readout_and_training_share_the_locked_run_level_cache(self) -> None:
        expected = {
            "HOME": "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/runtime_env/home",
            "XDG_CACHE_HOME": "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/runtime_env/xdg_cache",
            "TORCH_EXTENSIONS_DIR": "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/runtime_env/torch_extensions_seeded_v2",
        }
        self.assertEqual(
            self.config["pointcloudification"]["writable_environment"], expected
        )
        training = json.loads(
            (
                REPO
                / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_training_v1_20260725.json"
            ).read_text(encoding="utf-8")
        )
        training_environment = training["launch_contract"][
            "writable_environment"
        ]
        self.assertEqual(
            {
                key: str(
                    Path(training_environment["root"])
                    / training_environment["variables"][key]
                )
                for key in training_environment["variables"]
            },
            expected,
        )
        self.assertEqual(
            self.config["pointcloudification"]["jit_build_environment"],
            {"MAX_JOBS": "1"},
        )
        self.assertEqual(
            training["launch_contract"]["jit_build_environment"],
            {"MAX_JOBS": "1"},
        )

    def test_classification_reuses_p0_smrf_without_downsampling(self) -> None:
        classification = self.config["classification"]
        self.assertEqual(classification["target_density"], 0.0)
        self.assertEqual(
            classification["script"],
            "scripts/input_and_alignment/p2_gsjso/_mob_prep_las.py",
        )
        self.assertEqual(classification["smrf"]["ground_class"], 2)
        self.assertEqual(classification["overlay"]["building_class"], 6)

    def test_all_locked_static_inputs_match_repository(self) -> None:
        observed = MODULE.verify_static_inputs(self.config, repo=REPO)
        self.assertGreaterEqual(len(observed), 8)

    def test_fixed_score_header_covers_requested_metrics(self) -> None:
        required = {
            "assembly_lod2_success",
            "lod1_fallback",
            "val3dity_valid",
            "plane_f1",
            "roof_rms_m",
            "roof_completeness",
            "face_count_ratio",
            "rms_pair_laser_denominator_contribution",
            "rms_pair_image_denominator_contribution",
            "delta_roof_rms_vs_p0prime_m",
            "texture_stratum",
            "panel_png",
            "panel_materials",
        }
        self.assertTrue(required.issubset(MODULE.SCORE_FIELDS))

    def test_wrapper_enforces_serial_24g_offline_docker_and_process_guard(self) -> None:
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn('MEMORY_LIMIT="24g"', text)
        self.assertGreaterEqual(text.count('--network=none'), 3)
        self.assertGreaterEqual(text.count('--memory="$MEMORY_LIMIT"'), 3)
        self.assertIn("acquire_serial_lock", text)
        self.assertIn("training/runtime_counters.json.lock", text)
        self.assertIn("assert_no_training_or_other_readout", text)
        self.assertIn("src[.]stage2[.]train", text)
        self.assertIn('--pull=never', text)
        self.assertIn("roofer-argv", text)
        self.assertIn('"${argv[@]}"', text)
        self.assertNotIn("ROOFER_PARAMETERS", text)
        self.assertIn("CATASTROPHE_STOP_N=3", text)
        self.assertIn("recorded and skipped failed job without retry", text)
        self.assertIn("finalize-partial", text)
        self.assertIn("extract-environment", text)
        self.assertIn("retry-extract-infra", text)
        self.assertIn("record-extract-infra-retry-failure", text)
        self.assertGreaterEqual(text.count('"${environment_args[@]}"'), 2)
        self.assertIn("output validation or adoption failed", text)
        self.assertIn("recover-extract-infra2", text)
        self.assertIn("MAX_JOBS=1", text)

    def test_score_frame_subtracts_locked_geoid_once(self) -> None:
        reference = self.config["scoring"]["reference"]
        self.assertEqual(reference["score_time_z_shift_m"], -45.7)
        self.assertIn("ellipsoidal", reference["prediction_vertical_frame"])
        self.assertIn("orthometric", reference["reference_vertical_frame"])


class TargetAndCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = MODULE.load_config(CONFIG_PATH)

    def test_population_and_smoke_texture_join_use_locked_t9_t11_rule(self) -> None:
        self.assertEqual(len(MODULE.target_rows(self.config, repo=REPO)), 178)
        metadata = MODULE.target_metadata(
            self.config, "DEBY_LOD2_42364609", repo=REPO
        )
        self.assertEqual(metadata["tier"], "height")
        self.assertEqual(metadata["source_cell_label"], "cell_2_anchored")
        self.assertEqual(metadata["texture_threshold"], 0.804)
        self.assertEqual(metadata["texture_stratum"], "textured")

    def test_extractor_argv_has_one_target_and_no_reference(self) -> None:
        materialization = {
            "building_id": "DEBY_LOD2_42364609",
            "training": {
                "checkpoint": "training/checkpoint.pt",
                "data_root": "data",
            },
            "footprint": {"path": "footprint.geojson"},
        }
        argv = MODULE.extract_argv(
            self.config, materialization, "readout.npz"
        )
        self.assertIn("--no-sem", argv)
        self.assertEqual(argv[argv.index("--targets") + 1], "42364609")
        self.assertEqual(argv[argv.index("--buffer") + 1], "15.0")
        self.assertFalse(any("lod2" in value.lower() for value in argv))
        self.assertFalse(any("reference" in value.lower() for value in argv))

    def test_classification_argv_locks_no_density_match(self) -> None:
        materialization = {
            "building_id": "DEBY_LOD2_42364609",
            "footprint": {"path": "footprint.geojson"},
        }
        extract = {"pointcloud": {"path": "readout.npz"}}
        argv = MODULE.classification_argv(
            self.config, materialization, extract, "classification"
        )
        self.assertEqual(argv[argv.index("--target-density") + 1], "0.0")
        self.assertEqual(argv[argv.index("--buffer") + 1], "15.0")

    def test_roofer_argv_keeps_only_plumbing_after_locked_defaults(self) -> None:
        argv = MODULE.roofer_argv(
            self.config, "classified.las", "footprint.geojson", "roofer"
        )
        self.assertEqual(
            argv[: len(self.config["roofer"]["parameters"])],
            self.config["roofer"]["parameters"],
        )
        self.assertEqual(argv[-3:], ["classified.las", "footprint.geojson", "roofer"])

    def test_p0prime_helpers_are_loaded_and_reused(self) -> None:
        p0 = MODULE.p0prime_module(self.config, repo=REPO)
        self.assertAlmostEqual(p0.plane_f1(0.5, 1.0), 2.0 / 3.0)
        flags = p0.assembly_flags(
            {
                "attributes": {
                    "rf_success": True,
                    "rf_pointcloud_unusable": False,
                    "rf_extrusion_mode": "standard",
                },
                "has_lod22": True,
            },
            val3dity_feature={"validity": False},
        )
        self.assertTrue(flags["assembly_lod2_success"])
        self.assertFalse(flags["val3dity_valid"])


class TrainingLineageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = minimal_repo_config(self.root)
        self.paths = make_training_job(self.root, self.config)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def resolve(self) -> dict:
        return MODULE.resolve_training_artifacts(
            self.config,
            "DEBY_LOD2_42364609",
            "A",
            "r1",
            repo=self.root,
        )

    def test_completed_30k_full_state_job_is_consumable(self) -> None:
        result = self.resolve()
        self.assertEqual(
            result["full_state_checkpoint_sha256"],
            sha(self.paths["checkpoint"]),
        )
        self.assertEqual(
            result["checkpoint_sha256"], sha(self.paths["final_checkpoint"])
        )
        self.assertEqual(result["checkpoint"].name, "final.pt")
        self.assertEqual(result["train_views"], ["a.jpg"])

    def test_training_failed_receipt_blocks_readout(self) -> None:
        write_json(self.paths["job"] / "failed.json", {"schema": "failed"})
        with self.assertRaisesRegex(MODULE.ReadoutError, "failed receipt"):
            self.resolve()

    def test_verified_infrastructure_retry_with_preserved_failure_is_consumable(self) -> None:
        self.paths = make_infrastructure_retry_success(self.root, self.paths)
        self.assertTrue(
            MODULE.shallow_training_complete(
                self.config,
                "DEBY_LOD2_42364609",
                "A",
                "r1",
                repo=self.root,
            )
        )
        result = self.resolve()
        self.assertTrue(self.paths["original_failed"].is_file())
        self.assertEqual(result["checkpoint"], self.paths["final_checkpoint"])
        self.assertEqual(result["checkpoint"].parents[1], self.paths["attempt"])

    def test_infrastructure_retry_receipt_hash_drift_is_rejected(self) -> None:
        self.paths = make_infrastructure_retry_success(self.root, self.paths)
        retry_started = json.loads(
            self.paths["retry_started"].read_text(encoding="utf-8")
        )
        retry_started["unapproved_drift"] = True
        write_json(self.paths["retry_started"], retry_started)
        with self.assertRaisesRegex(MODULE.ReadoutError, "SHA256 mismatch"):
            self.resolve()

    def test_infrastructure_retry_checkpoint_outside_attempt_is_rejected(self) -> None:
        self.paths = make_infrastructure_retry_success(self.root, self.paths)
        arbitrary = self.root / "arbitrary/final.pt"
        arbitrary.parent.mkdir(parents=True)
        arbitrary.write_bytes(self.paths["final_checkpoint"].read_bytes())
        completed = json.loads(self.paths["completed"].read_text(encoding="utf-8"))
        completed["training_completion"]["final_checkpoint"] = str(
            arbitrary.relative_to(self.root)
        )
        completed["training_completion"]["final_checkpoint_sha256"] = sha(arbitrary)
        retry_completed = json.loads(
            self.paths["retry_completed"].read_text(encoding="utf-8")
        )
        retry_completed["training_completion"] = completed["training_completion"]
        write_json(self.paths["retry_completed"], retry_completed)
        completed["infrastructure_retry"]["retry_completed_receipt"]["sha256"] = sha(
            self.paths["retry_completed"]
        )
        write_json(self.paths["completed"], completed)
        self.assertFalse(
            MODULE.shallow_training_complete(
                self.config,
                "DEBY_LOD2_42364609",
                "A",
                "r1",
                repo=self.root,
            )
        )
        with self.assertRaisesRegex(MODULE.ReadoutError, "extract checkpoint path"):
            self.resolve()

    def test_checkpoint_hash_drift_fails_closed(self) -> None:
        self.paths["final_checkpoint"].write_bytes(b"changed")
        with self.assertRaisesRegex(MODULE.ReadoutError, "SHA256 mismatch"):
            self.resolve()

    def test_incomplete_full_state_fails_closed(self) -> None:
        payload = json.loads(
            self.paths["full_state"].read_text(encoding="utf-8")
        )
        payload["process_completed_steps"] = 29999
        write_json(self.paths["full_state"], payload)
        completion = json.loads(
            self.paths["completed"].read_text(encoding="utf-8")
        )
        completion["training_completion"]["full_state_manifest_sha256"] = sha(
            self.paths["full_state"]
        )
        write_json(self.paths["completed"], completion)
        with self.assertRaisesRegex(MODULE.ReadoutError, "optimizer updates"):
            self.resolve()

    def test_wrong_completion_schema_fails_closed(self) -> None:
        payload = json.loads(
            self.paths["completed"].read_text(encoding="utf-8")
        )
        payload["schema"] = "wrong"
        write_json(self.paths["completed"], payload)
        with self.assertRaisesRegex(MODULE.ReadoutError, "completion schema"):
            self.resolve()

    def test_absolute_checkpoint_path_is_rejected(self) -> None:
        payload = json.loads(
            self.paths["completed"].read_text(encoding="utf-8")
        )
        payload["training_completion"]["final_checkpoint"] = str(
            self.paths["final_checkpoint"].resolve()
        )
        write_json(self.paths["completed"], payload)
        with self.assertRaisesRegex(MODULE.ReadoutError, "absolute"):
            self.resolve()


class StateCounterAndPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = minimal_repo_config(self.root)
        self.bid = "DEBY_LOD2_42364609"
        self.job = MODULE.job_dir(
            self.config, self.bid, "A", "r1", repo=self.root
        )
        self.job.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_each_stage_counter_increments_once_and_duplicate_refuses(self) -> None:
        for stage in ("readout", "roofer", "scoring"):
            invocation = self.job / f"{stage}_invocation.json"
            write_json(invocation, {"schema": "synthetic"})
            MODULE.begin_stage(
                self.config,
                self.bid,
                "A",
                "r1",
                stage=stage,
                invocation_path=invocation,
                repo=self.root,
            )
            with self.assertRaisesRegex(MODULE.ReadoutError, "already started"):
                MODULE.begin_stage(
                    self.config,
                    self.bid,
                    "A",
                    "r1",
                    stage=stage,
                    invocation_path=invocation,
                    repo=self.root,
                )
        counters = json.loads(
            (self.root / "readout/runtime_counters.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(counters["readout_runs_started"], 1)
        self.assertEqual(counters["roofer_runs_started"], 1)
        self.assertEqual(counters["scoring_runs_started"], 1)
        self.assertEqual(counters["source_receipts_n"], 3)
        self.assertEqual(
            counters["counter_truth"],
            "immutable_stage_STARTED_receipts",
        )

    def test_counter_view_reconciles_after_interrupted_publication(self) -> None:
        invocation = self.job / "readout_invocation.json"
        write_json(invocation, {"schema": "synthetic"})
        MODULE.begin_stage(
            self.config,
            self.bid,
            "A",
            "r1",
            stage="readout",
            invocation_path=invocation,
            repo=self.root,
        )
        counter_path = self.root / "readout/runtime_counters.json"
        write_json(counter_path, {"schema": "stale-interrupted-view"})
        counters = MODULE.reconcile_runtime_counters(
            self.config, repo=self.root
        )
        self.assertEqual(counters["readout_runs_started"], 1)
        self.assertEqual(counters["roofer_runs_started"], 0)
        self.assertEqual(counters["source_receipts_n"], 1)
        with self.assertRaisesRegex(MODULE.ReadoutError, "already started"):
            MODULE.begin_stage(
                self.config,
                self.bid,
                "A",
                "r1",
                stage="readout",
                invocation_path=invocation,
                repo=self.root,
            )
        repaired = json.loads(counter_path.read_text(encoding="utf-8"))
        self.assertEqual(repaired["readout_runs_started"], 1)

    def test_started_receipt_sha_binds_the_executed_argv(self) -> None:
        invocation = self.job / "extract_invocation.json"
        write_json(
            invocation,
            {
                "schema": "jointbuildgs.fusion_w1.extract_invocation.v1",
                "state": "AUTHORIZED",
                "job_key": f"{self.bid}/arm_A/r1",
                "argv": ["locked.py", "--value", "one"],
            },
        )
        MODULE.begin_stage(
            self.config,
            self.bid,
            "A",
            "r1",
            stage="readout",
            invocation_path=invocation,
            repo=self.root,
        )
        payload = json.loads(invocation.read_text(encoding="utf-8"))
        payload["argv"][-1] = "tampered"
        write_json(invocation, payload)
        with self.assertRaisesRegex(MODULE.ReadoutError, "SHA256 mismatch"):
            MODULE.invocation_argv(
                self.config,
                self.bid,
                "A",
                "r1",
                "extract_invocation.json",
                "jointbuildgs.fusion_w1.extract_invocation.v1",
                repo=self.root,
            )

    def test_failed_receipt_is_idempotent_and_blocks_stage_retry(self) -> None:
        first = MODULE.record_failure(
            self.config,
            self.bid,
            "A",
            "r1",
            stage="synthetic",
            message="boom",
            repo=self.root,
        )
        second = MODULE.record_failure(
            self.config,
            self.bid,
            "A",
            "r1",
            stage="synthetic-again",
            message="different",
            repo=self.root,
        )
        self.assertEqual(first, second)
        invocation = self.job / "readout_invocation.json"
        write_json(invocation, {"schema": "synthetic"})
        with self.assertRaisesRegex(MODULE.ReadoutError, "retries are forbidden"):
            MODULE.begin_stage(
                self.config,
                self.bid,
                "A",
                "r1",
                stage="readout",
                invocation_path=invocation,
                repo=self.root,
            )

    def test_incremental_score_is_identity_unique_and_sorted(self) -> None:
        later = {
            "building_id": "DEBY_LOD2_2",
            "arm": "B",
            "run": "r2",
            "processing_order": 2,
        }
        earlier = {
            "building_id": "DEBY_LOD2_1",
            "arm": "A",
            "run": "r1",
            "processing_order": 1,
        }
        MODULE.upsert_score_row(self.config, later, repo=self.root)
        MODULE.upsert_score_row(self.config, earlier, repo=self.root)
        rows = MODULE.read_csv(self.root / "readout/w1_scores_building.csv")
        self.assertEqual(
            [(row["building_id"], row["arm"], row["run"]) for row in rows],
            [
                ("DEBY_LOD2_1", "A", "r1"),
                ("DEBY_LOD2_2", "B", "r2"),
            ],
        )
        with self.assertRaisesRegex(MODULE.ReadoutError, "already exists"):
            MODULE.upsert_score_row(self.config, earlier, repo=self.root)

    def test_paired_rms_denominator_is_explicit_and_finite_only(self) -> None:
        finite = MODULE.paired_rms_fields(
            0.7, {"roof_rms_m": "0.5"}, "rms_pair_laser"
        )
        self.assertTrue(finite["rms_pair_laser_eligible"])
        self.assertEqual(finite["rms_pair_laser_denominator_contribution"], 1)
        self.assertAlmostEqual(finite["rms_pair_laser_delta_m"], 0.2)
        missing = MODULE.paired_rms_fields(
            None, {"roof_rms_m": "0.5"}, "rms_pair_laser"
        )
        self.assertFalse(missing["rms_pair_laser_eligible"])
        self.assertEqual(missing["rms_pair_laser_denominator_contribution"], 0)

    def test_scoring_claim_precedes_reference_open_in_source(self) -> None:
        source = inspect.getsource(MODULE.score_one)
        self.assertLess(source.index("begin_stage("), source.index("parse_lod2_roofs("))

    def test_partial_finalize_publishes_zero_measurement_contract_without_counter(self) -> None:
        counter = self.root / "readout/runtime_counters.json"
        self.assertFalse(counter.exists())
        result = MODULE.finalize_partial(self.config, repo=self.root)
        scores = self.root / "readout/w1_scores_building.csv"
        summary = self.root / "readout/w1_summary.csv"
        self.assertEqual(MODULE.csv_header(scores), MODULE.SCORE_FIELDS)
        self.assertEqual(MODULE.read_csv(scores), [])
        rows = MODULE.read_csv(summary)
        self.assertEqual(MODULE.csv_header(summary), MODULE.SUMMARY_FIELDS)
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(row["status"] == "NOT_MEASURED" for row in rows))
        self.assertTrue(all(row["score_rows_n"] == "0" for row in rows))
        self.assertEqual(result["not_measured_rows_n"], 12)
        self.assertFalse(result["stage_counters_touched"])
        self.assertFalse(counter.exists())

    def test_partial_finalize_aggregates_existing_score_rows_observationally(self) -> None:
        MODULE.upsert_score_row(
            self.config,
            {
                "building_id": self.bid,
                "arm": "A",
                "run": "r1",
                "processing_order": 1,
                "tier": "height",
                "cohort": "core",
                "texture_stratum": "textured",
                "assembly_lod2_success": True,
                "lod1_fallback": False,
                "val3dity_valid": True,
                "plane_f1": 0.75,
                "roof_rms_m": 0.20,
                "roof_completeness": 0.90,
                "face_count_ratio": 1.10,
                "rms_pair_laser_denominator_contribution": 1,
                "rms_pair_laser_delta_m": -0.03,
                "rms_pair_image_denominator_contribution": 1,
                "rms_pair_image_delta_m": -0.10,
            },
            repo=self.root,
        )
        result = MODULE.finalize_partial(self.config, repo=self.root)
        rows = MODULE.read_csv(self.root / "readout/w1_summary.csv")
        measured = [
            row
            for row in rows
            if row["tier"] == "height"
            and row["arm"] == "A"
            and row["run"] == "r1"
        ]
        self.assertEqual(len(measured), 1)
        self.assertEqual(measured[0]["status"], "MEASURED")
        self.assertEqual(measured[0]["score_rows_n"], "1")
        self.assertEqual(measured[0]["assembly_lod2_success_n"], "1")
        self.assertEqual(measured[0]["roof_rms_m_median"], "0.200000000")
        self.assertEqual(result["score_rows_n"], 1)
        self.assertEqual(result["not_measured_rows_n"], 11)
        self.assertFalse(
            (self.root / "readout/runtime_counters.json").exists()
        )

    def test_partial_finalize_preserves_existing_counter_byte_for_byte(self) -> None:
        counter = self.root / "readout/runtime_counters.json"
        write_json(
            counter,
            {
                "schema": MODULE.COUNTER_SCHEMA,
                "readout_runs_started": 2,
                "roofer_runs_started": 1,
                "scoring_runs_started": 1,
            },
        )
        before = counter.read_bytes()
        result = MODULE.finalize_partial(self.config, repo=self.root)
        self.assertEqual(counter.read_bytes(), before)
        self.assertTrue(result["counter_existed_before"])
        self.assertTrue(result["counter_existed_after"])
        self.assertFalse(result["stage_counters_touched"])
        source = inspect.getsource(MODULE.finalize_partial)
        self.assertNotIn("begin_stage(", source)
        self.assertNotIn("reconcile_runtime_counters(", source)


class ReadoutInfrastructureRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = minimal_repo_config(self.root)
        self.paths = make_readout_preoutput_cache_failure(
            self.root, self.config
        )
        self.bid = "DEBY_LOD2_42364609"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def prepare(self) -> dict:
        return MODULE.prepare_extract_infra_retry(
            self.config,
            self.paths["policy"],
            self.bid,
            "A",
            "r1",
            repo=self.root,
            validate_git=False,
        )

    def write_retry_npz(self) -> Path:
        import numpy as np

        invocation = json.loads(
            (
                self.paths["job"]
                / MODULE.READOUT_RETRY_ATTEMPT_DIRECTORY
                / "extract_invocation.json"
            ).read_text(encoding="utf-8")
        )
        output = self.root / invocation["output"]
        output.parent.mkdir(parents=True, exist_ok=True)
        points = np.asarray(
            [[690000.0, 5330000.0, 530.0], [690001.0, 5330001.0, 531.0]],
            dtype=np.float64,
        )
        np.savez(
            output,
            P_utm=points,
            P_utm_clean=points,
            voxel=0.05,
            downscale=1.0,
        )
        return output

    def test_writable_environment_is_exact_shared_and_symlink_safe(self) -> None:
        with self.assertRaisesRegex(MODULE.ReadoutError, "not ready"):
            MODULE.writable_readout_environment(
                self.config, repo=self.root, require_ready=True
            )
        environment = MODULE.writable_readout_environment(
            self.config, repo=self.root, create=True
        )
        self.assertEqual(
            set(environment["host_paths"]), MODULE.WRITABLE_ENVIRONMENT_KEYS
        )
        self.assertEqual(environment["runtime_root"], "runtime_env")
        for key, relative in environment["host_paths"].items():
            self.assertTrue((self.root / relative).is_dir(), key)
            self.assertEqual(
                environment["container_values"][key],
                f"/workspace/JointBuildGS/{relative}",
            )

        escaping = copy.deepcopy(self.config)
        escaping["pointcloudification"]["writable_environment"]["HOME"] = (
            "../escape"
        )
        with self.assertRaisesRegex(MODULE.ReadoutError, "unsafe"):
            MODULE.writable_readout_environment(escaping, repo=self.root)

        linked = copy.deepcopy(self.config)
        actual = self.root / "runtime_env/actual"
        actual.mkdir(parents=True)
        link = self.root / "runtime_env/link"
        link.symlink_to(actual, target_is_directory=True)
        linked["pointcloudification"]["writable_environment"]["HOME"] = (
            "runtime_env/link/cache"
        )
        with self.assertRaisesRegex(MODULE.ReadoutError, "symlink"):
            MODULE.writable_readout_environment(linked, repo=self.root)

    def test_symlinked_retry_output_namespace_is_rejected_before_receipts(self) -> None:
        import numpy as np

        self.prepare()
        attempt = (
            self.paths["job"] / MODULE.READOUT_RETRY_ATTEMPT_DIRECTORY
        )
        diverted = self.root / "diverted-pointcloud"
        diverted.mkdir()
        (attempt / "pointcloud").symlink_to(diverted, target_is_directory=True)
        points = np.asarray([[1.0, 2.0, 3.0]], dtype=np.float64)
        np.savez(
            diverted / "readout.npz",
            P_utm=points,
            P_utm_clean=points,
            voxel=0.05,
            downscale=1.0,
        )
        with self.assertRaisesRegex(MODULE.ReadoutError, "contains a symlink"):
            MODULE.accept_extract_infra_retry(
                self.config,
                self.bid,
                "A",
                "r1",
                wall_seconds=1.0,
                repo=self.root,
            )
        self.assertFalse((attempt / "extract_receipt.json").exists())
        self.assertFalse((attempt / "retry_completed.json").exists())
        self.assertFalse((self.paths["job"] / "extract_receipt.json").exists())

    def test_one_retry_adopts_output_without_increment_or_original_drift(self) -> None:
        original_hashes = {
            name: sha(path)
            for name, path in self.paths.items()
            if name
            in {"materialization", "invocation", "started", "log", "failed"}
        }
        prepared = self.prepare()
        self.assertEqual(prepared["status"], "AUTHORIZED")
        self.assertIn("infra_retry_01/pointcloud/readout.npz", prepared["retry_output"])
        retry_argv = MODULE.retry_extract_argv(
            self.config, self.bid, "A", "r1", repo=self.root
        )
        self.assertEqual(retry_argv.count("--out"), 1)
        self.assertEqual(
            retry_argv[retry_argv.index("--out") + 1],
            prepared["retry_output"],
        )
        retry_environment = MODULE.retry_extract_environment(
            self.config, self.bid, "A", "r1", repo=self.root
        )
        self.assertEqual(len(retry_environment), 3)
        with self.assertRaisesRegex(MODULE.ReadoutError, "already claimed"):
            self.prepare()

        output = self.write_retry_npz()
        receipt = MODULE.accept_extract_infra_retry(
            self.config,
            self.bid,
            "A",
            "r1",
            wall_seconds=3.0,
            repo=self.root,
        )
        self.assertEqual(receipt["pointcloud"]["path"], str(output.relative_to(self.root)))
        self.assertEqual(receipt["infrastructure_retry"]["counter_increment"], 0)
        self.assertTrue(MODULE._validate_adopted_extract_retry(self.paths["job"], repo=self.root))
        MODULE.ensure_not_failed(self.paths["job"], repo=self.root)
        counters = MODULE.reconcile_runtime_counters(self.config, repo=self.root)
        self.assertEqual(counters["readout_runs_started"], 1)
        self.assertEqual(counters["roofer_runs_started"], 0)
        self.assertEqual(counters["scoring_runs_started"], 0)
        for name, digest in original_hashes.items():
            self.assertEqual(sha(self.paths[name]), digest, name)

        # Downstream receipts are permitted after adoption and do not weaken
        # the immutable original-file checks.
        write_json(
            self.paths["job"] / "classification_invocation.json",
            {"schema": "synthetic-downstream"},
        )
        MODULE.ensure_not_failed(self.paths["job"], repo=self.root)

    def test_original_drift_or_preexisting_output_blocks_before_claim(self) -> None:
        self.paths["log"].write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ReadoutError, "SHA256 mismatch"):
            self.prepare()
        self.assertFalse(
            (self.paths["job"] / MODULE.READOUT_RETRY_ATTEMPT_DIRECTORY).exists()
        )

    def test_acceptance_rejects_unexpected_root_file_and_records_retry_failure(self) -> None:
        self.prepare()
        self.write_retry_npz()
        write_json(
            self.paths["job"] / "classification_invocation.json",
            {"schema": "unexpected-before-adoption"},
        )
        with self.assertRaisesRegex(
            MODULE.ReadoutError, "pre-adoption original readout file inventory"
        ):
            MODULE.accept_extract_infra_retry(
                self.config,
                self.bid,
                "A",
                "r1",
                wall_seconds=1.0,
                repo=self.root,
            )
        failed = MODULE.record_extract_infra_retry_failure(
            self.config,
            self.bid,
            "A",
            "r1",
            message="acceptance validation failed",
            repo=self.root,
        )
        self.assertFalse(failed["another_retry_allowed"])
        self.assertTrue(
            (
                self.paths["job"]
                / MODULE.READOUT_RETRY_ATTEMPT_DIRECTORY
                / "retry_failed.json"
            ).is_file()
        )
        with self.assertRaisesRegex(MODULE.ReadoutError, "already failed"):
            MODULE.retry_extract_argv(
                self.config, self.bid, "A", "r1", repo=self.root
            )

    def test_downstream_failure_after_adoption_has_distinct_terminal_receipt(self) -> None:
        self.prepare()
        self.write_retry_npz()
        MODULE.accept_extract_infra_retry(
            self.config,
            self.bid,
            "A",
            "r1",
            wall_seconds=1.0,
            repo=self.root,
        )
        original_failure_sha = sha(self.paths["failed"])
        failure = MODULE.record_failure(
            self.config,
            self.bid,
            "A",
            "r1",
            stage="classification",
            message="synthetic downstream failure",
            repo=self.root,
        )
        self.assertEqual(
            failure["schema"],
            "jointbuildgs.fusion_w1.readout_failure_after_infrastructure_retry.v1",
        )
        self.assertEqual(sha(self.paths["failed"]), original_failure_sha)
        with self.assertRaisesRegex(MODULE.ReadoutError, "failed after"):
            MODULE.ensure_not_failed(self.paths["job"], repo=self.root)

    def test_adopted_validator_rejects_rehashed_completed_chain_drift(self) -> None:
        self.prepare()
        self.write_retry_npz()
        MODULE.accept_extract_infra_retry(
            self.config,
            self.bid,
            "A",
            "r1",
            wall_seconds=1.0,
            repo=self.root,
        )
        attempt = self.paths["job"] / MODULE.READOUT_RETRY_ATTEMPT_DIRECTORY
        completed_path = attempt / "retry_completed.json"
        completed = json.loads(completed_path.read_text(encoding="utf-8"))
        completed["retry_key"] = "DEBY_LOD2_42364609/arm_A/r1/unauthorized"
        write_json(completed_path, completed)
        root_receipt = self.paths["job"] / "extract_receipt.json"
        root = json.loads(root_receipt.read_text(encoding="utf-8"))
        root["infrastructure_retry"]["retry_completed"]["sha256"] = sha(
            completed_path
        )
        write_json(root_receipt, root)
        with self.assertRaisesRegex(MODULE.ReadoutError, "completed readout retry key"):
            MODULE._validate_adopted_extract_retry(
                self.paths["job"], repo=self.root
            )

    def test_successful_adoption_cannot_be_poisoned_by_retry_failure_command(self) -> None:
        self.prepare()
        self.write_retry_npz()
        MODULE.accept_extract_infra_retry(
            self.config,
            self.bid,
            "A",
            "r1",
            wall_seconds=1.0,
            repo=self.root,
        )
        with self.assertRaisesRegex(MODULE.ReadoutError, "successfully adopted"):
            MODULE.record_extract_infra_retry_failure(
                self.config,
                self.bid,
                "A",
                "r1",
                message="must not poison success",
                repo=self.root,
            )
        self.assertFalse(
            (
                self.paths["job"]
                / MODULE.READOUT_RETRY_ATTEMPT_DIRECTORY
                / "retry_failed.json"
            ).exists()
        )

    def test_retry_invocation_rejects_non_output_scientific_drift(self) -> None:
        self.prepare()
        original = json.loads(self.paths["invocation"].read_text(encoding="utf-8"))
        retry_path = (
            self.paths["job"]
            / MODULE.READOUT_RETRY_ATTEMPT_DIRECTORY
            / "extract_invocation.json"
        )
        retry = json.loads(retry_path.read_text(encoding="utf-8"))
        retry["training_checkpoint"] = {
            **retry["training_checkpoint"],
            "sha256": "f" * 64,
        }
        with self.assertRaisesRegex(MODULE.ReadoutError, "training_checkpoint"):
            MODULE._validate_retry_invocation_difference(
                original, retry, retry_output=retry["output"]
            )

    def test_git_gate_checks_ancestor_before_exact_one_commit_diff(self) -> None:
        base = "a" * 40
        head = "b" * 40
        policy = {
            "required_pre_retry_head": base,
            "allowed_retry_commit_paths": ["allowed.py"],
        }
        seen: list[tuple[str, ...]] = []

        def fake_git(_repo: Path, *args: str) -> str:
            seen.append(args)
            responses = {
                ("branch", "--show-current"): "exp/fusion-w1",
                ("rev-parse", "HEAD"): head,
                ("merge-base", "--is-ancestor", base, head): "",
                ("rev-list", "--count", f"{base}..{head}"): "1",
                ("diff", "--name-only", base, head): "allowed.py",
                ("status", "--porcelain=v1", "--untracked-files=all"): "",
            }
            return responses[args]

        with mock.patch.object(MODULE, "_run_git", side_effect=fake_git):
            state = MODULE._validate_readout_retry_git_state(self.root, policy)
        self.assertTrue(state["pre_retry_head_is_ancestor"])
        self.assertIn(("merge-base", "--is-ancestor", base, head), seen)


class ReadoutInfrastructureRecovery2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = minimal_repo_config(self.root)
        self.paths = make_readout_recovery2_fixture(self.root, self.config)
        self.bid = "DEBY_LOD2_42364609"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def prepare(self) -> dict:
        return MODULE.prepare_extract_infra_recovery2(
            self.config,
            self.paths["recovery2_policy"],
            self.bid,
            "A",
            "r1",
            repo=self.root,
            validate_git=False,
        )

    def write_output(self) -> Path:
        import numpy as np

        invocation_path = (
            self.paths["job"]
            / MODULE.READOUT_RECOVERY2_ATTEMPT_DIRECTORY
            / "extract_invocation.json"
        )
        invocation = json.loads(invocation_path.read_text(encoding="utf-8"))
        output = self.root / invocation["output"]
        output.parent.mkdir(parents=True, exist_ok=True)
        points = np.asarray(
            [[690000.0, 5330000.0, 530.0], [690001.0, 5330001.0, 531.0]],
            dtype=np.float64,
        )
        np.savez(
            output,
            P_utm=points,
            P_utm_clean=points,
            voxel=0.05,
            downscale=1.0,
        )
        return output

    def test_cache_seeded_exact_one_recovery_adopts_without_counter_increment(self) -> None:
        immutable = {
            path: sha(path)
            for path in (
                self.paths["materialization"],
                self.paths["invocation"],
                self.paths["started"],
                self.paths["log"],
                self.paths["failed"],
                self.paths["prior_attempt"] / "retry_started.json",
                self.paths["prior_attempt"] / "extract_invocation.json",
                self.paths["prior_log"],
                self.paths["prior_attempt"] / "retry_failed.json",
            )
        }
        source_before = MODULE._cache_inventory(
            self.paths["source_cache"], repo=self.root
        )
        common_before = MODULE._cache_inventory(
            self.paths["common_cache"], repo=self.root
        )
        prepared = self.prepare()
        self.assertEqual(prepared["counter_increment"], 0)
        self.assertEqual(prepared["jit_build_environment"], {"MAX_JOBS": "1"})
        self.assertEqual(
            MODULE._cache_inventory(self.paths["common_cache"], repo=self.root)[
                "inventory_sha256"
            ],
            common_before["inventory_sha256"],
        )
        self.assertEqual(
            MODULE._cache_inventory(
                self.paths["seed_destination"], repo=self.root
            )["inventory_sha256"],
            source_before["inventory_sha256"],
        )
        seed_manifest_path = (
            self.paths["job"]
            / MODULE.READOUT_RECOVERY2_ATTEMPT_DIRECTORY
            / "cache_seed_manifest.json"
        )
        seed_manifest = json.loads(seed_manifest_path.read_text(encoding="utf-8"))
        self.assertTrue(seed_manifest["prior_common_cache_unchanged_after_publish"])
        self.assertTrue(seed_manifest["single_atomic_directory_rename_publish"])
        self.assertEqual(
            seed_manifest["prior_common_cache_preserved_in_place_at"],
            str(self.paths["common_cache"].relative_to(self.root)),
        )
        self.assertEqual(
            MODULE._cache_inventory(self.paths["source_cache"], repo=self.root),
            source_before,
        )
        environment = MODULE.recovery2_extract_environment(
            self.config, self.bid, "A", "r1", repo=self.root
        )
        self.assertIn("MAX_JOBS=1", environment)
        self.assertEqual(len(environment), 4)
        argv = MODULE.recovery2_extract_argv(
            self.config, self.bid, "A", "r1", repo=self.root
        )
        original = json.loads(self.paths["invocation"].read_text(encoding="utf-8"))
        self.assertEqual(
            argv,
            MODULE._replace_only_output(
                original["argv"], original["output"], prepared["recovery_output"]
            ),
        )
        with self.assertRaisesRegex(MODULE.ReadoutError, "already claimed"):
            self.prepare()

        output = self.write_output()
        receipt = MODULE.accept_extract_infra_recovery2(
            self.config,
            self.bid,
            "A",
            "r1",
            wall_seconds=2.0,
            repo=self.root,
        )
        self.assertEqual(receipt["pointcloud"]["path"], str(output.relative_to(self.root)))
        self.assertEqual(receipt["infrastructure_recovery2"]["counter_increment"], 0)
        MODULE.ensure_not_failed(self.paths["job"], repo=self.root)
        counters = MODULE.reconcile_runtime_counters(self.config, repo=self.root)
        self.assertEqual(counters["readout_runs_started"], 1)
        self.assertEqual(counters["roofer_runs_started"], 0)
        self.assertEqual(counters["scoring_runs_started"], 0)
        for path, digest in immutable.items():
            self.assertEqual(sha(path), digest, str(path))

    def test_nonzero_prior_output_blocks_before_recovery2_claim(self) -> None:
        prior_output = self.paths["prior_attempt"] / "pointcloud/readout.npz"
        prior_output.parent.mkdir(parents=True)
        prior_output.write_bytes(b"forbidden-partial-output")
        with self.assertRaisesRegex(MODULE.ReadoutError, "forbidden output"):
            self.prepare()
        self.assertFalse(
            (
                self.paths["job"]
                / MODULE.READOUT_RECOVERY2_ATTEMPT_DIRECTORY
            ).exists()
        )

    def test_training_cache_drift_blocks_before_seed(self) -> None:
        (self.paths["source_cache"] / "gsplat_cuda.so").write_bytes(b"drift")
        with self.assertRaisesRegex(MODULE.ReadoutError, "SHA256 mismatch|inventory_sha256"):
            self.prepare()
        self.assertFalse(
            (
                self.paths["job"]
                / MODULE.READOUT_RECOVERY2_ATTEMPT_DIRECTORY
            ).exists()
        )

    def test_symlink_in_training_cache_blocks_before_seed(self) -> None:
        (self.paths["source_cache"] / "forbidden-link").symlink_to(
            self.paths["source_cache"] / "build.ninja"
        )
        with self.assertRaisesRegex(MODULE.ReadoutError, "symlink"):
            self.prepare()

    def test_recovery2_failure_is_terminal_and_cannot_be_reclaimed(self) -> None:
        self.prepare()
        failed = MODULE.record_extract_infra_recovery2_failure(
            self.config,
            self.bid,
            "A",
            "r1",
            message="synthetic recovery2 failure",
            repo=self.root,
        )
        self.assertFalse(failed["another_recovery_allowed"])
        self.assertEqual(failed["counter_increment"], 0)
        with self.assertRaisesRegex(MODULE.ReadoutError, "already failed"):
            MODULE.recovery2_extract_argv(
                self.config, self.bid, "A", "r1", repo=self.root
            )
        with self.assertRaisesRegex(MODULE.ReadoutError, "already claimed"):
            self.prepare()

    def test_noncanonical_absolute_policy_path_is_rejected(self) -> None:
        outside = self.root.parent / f"{self.root.name}_outside_recovery2.json"
        write_json(outside, {"schema": MODULE.READOUT_RECOVERY2_POLICY_SCHEMA})
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        with self.assertRaisesRegex(MODULE.ReadoutError, "canonical recovery2 policy"):
            MODULE.validate_readout_recovery2_policy(
                self.config, outside, repo=self.root
            )

    def test_symlinked_job_parent_is_rejected_before_atomic_claim(self) -> None:
        job = self.paths["job"]
        real_job = job.with_name("r1-real")
        job.rename(real_job)
        job.symlink_to(real_job.name, target_is_directory=True)
        with self.assertRaisesRegex(MODULE.ReadoutError, "contains a symlink"):
            self.prepare()
        self.assertFalse(
            (real_job / MODULE.READOUT_RECOVERY2_ATTEMPT_DIRECTORY).exists()
        )

    def test_versioned_destination_must_be_absent_before_claim(self) -> None:
        self.paths["seed_destination"].mkdir(parents=True)
        (self.paths["seed_destination"] / "unexpected").write_bytes(b"occupied")
        with self.assertRaisesRegex(MODULE.ReadoutError, "is not absent"):
            self.prepare()
        self.assertFalse(
            (
                self.paths["job"]
                / MODULE.READOUT_RECOVERY2_ATTEMPT_DIRECTORY
            ).exists()
        )

    def test_single_rename_failure_preserves_old_cache_and_never_hides_path(self) -> None:
        common_before = MODULE._cache_inventory(
            self.paths["common_cache"], repo=self.root
        )
        with mock.patch.object(
            MODULE.os, "rename", side_effect=OSError("synthetic publish interruption")
        ) as rename:
            with self.assertRaisesRegex(OSError, "synthetic publish interruption"):
                self.prepare()
        self.assertEqual(rename.call_count, 1)
        self.assertEqual(
            MODULE._cache_inventory(self.paths["common_cache"], repo=self.root),
            common_before,
        )
        self.assertFalse(self.paths["seed_destination"].exists())
        self.assertTrue(
            (
                self.paths["job"]
                / MODULE.READOUT_RECOVERY2_ATTEMPT_DIRECTORY
                / "retry_failed.json"
            ).is_file()
        )


class PointCloudAndQueueTests(unittest.TestCase):
    def test_npz_contract_accepts_xyz_and_rejects_semantic_arrays(self) -> None:
        import numpy as np

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = minimal_repo_config(root)
            path = root / "readout.npz"
            points = np.asarray(
                [[690000.0, 5330000.0, 530.0], [690001.0, 5330001.0, 531.0]]
            )
            np.savez(
                path,
                P_utm=points,
                P_utm_clean=points,
                voxel=0.05,
                downscale=1.0,
            )
            stats = MODULE.inspect_npz(path, config, repo=root)
            self.assertEqual(stats["clean_points_n"], 2)
            np.savez(
                path,
                P_utm=points,
                P_utm_clean=points,
                P_class=np.asarray([1, 2]),
                voxel=0.05,
                downscale=1.0,
            )
            with self.assertRaisesRegex(MODULE.ReadoutError, "semantic output"):
                MODULE.inspect_npz(path, config, repo=root)

    def test_nonfinite_npz_fails_closed(self) -> None:
        import numpy as np

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = minimal_repo_config(root)
            path = root / "readout.npz"
            points = np.asarray([[0.0, 0.0, float("nan")]])
            np.savez(
                path,
                P_utm=points,
                P_utm_clean=points,
                voxel=0.05,
                downscale=1.0,
            )
            with self.assertRaisesRegex(MODULE.ReadoutError, "non-finite"):
                MODULE.inspect_npz(path, config, repo=root)

    def test_queue_emits_only_smoke_until_smoke_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = minimal_repo_config(root)
            target = root / "targets.csv"
            fields = ["building_id", "processing_order"]
            write_csv(
                target,
                [*fields, "cohort"],
                [
                    {
                        "building_id": "DEBY_LOD2_42364609",
                        "processing_order": 1,
                        "cohort": "core",
                    }
                ],
            )
            config["targets"]["path"] = "targets.csv"
            config["targets"]["sha256"] = sha(target)
            config["targets"]["expected_population"] = 1
            make_training_job(root, config)
            self.assertEqual(
                MODULE.list_pending(config, repo=root),
                ["DEBY_LOD2_42364609/arm_A/r1"],
            )
            smoke_job = MODULE.job_dir(
                config,
                "DEBY_LOD2_42364609",
                "A",
                "r1",
                repo=root,
            )
            smoke_job.mkdir(parents=True)
            write_json(smoke_job / "complete.json", {"state": "COMPLETE"})
            self.assertEqual(MODULE.list_pending(config, repo=root), [])

    def test_partial_smoke_state_is_not_silently_retried(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = minimal_repo_config(root)
            target = root / "targets.csv"
            write_csv(
                target,
                ["building_id", "processing_order", "cohort"],
                [
                    {
                        "building_id": "DEBY_LOD2_42364609",
                        "processing_order": 1,
                        "cohort": "core",
                    }
                ],
            )
            config["targets"]["path"] = "targets.csv"
            config["targets"]["sha256"] = sha(target)
            config["targets"]["expected_population"] = 1
            make_training_job(root, config)
            smoke_job = MODULE.job_dir(
                config,
                "DEBY_LOD2_42364609",
                "A",
                "r1",
                repo=root,
            )
            smoke_job.mkdir(parents=True)
            write_json(smoke_job / "readout_started.json", {"state": "STARTED"})
            with self.assertRaisesRegex(MODULE.ReadoutError, "partial state"):
                MODULE.list_pending(config, repo=root)

    def test_queue_preserves_global_phase_order_before_target_nesting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = minimal_repo_config(root)
            targets = root / "targets.csv"
            smoke = "DEBY_LOD2_42364609"
            core_2 = "DEBY_LOD2_42364659"
            extension = "DEBY_LOD2_4907182"
            write_csv(
                targets,
                ["building_id", "processing_order", "cohort"],
                [
                    {
                        "building_id": smoke,
                        "processing_order": 1,
                        "cohort": "core",
                    },
                    {
                        "building_id": core_2,
                        "processing_order": 2,
                        "cohort": "core",
                    },
                    {
                        "building_id": extension,
                        "processing_order": 3,
                        "cohort": "extension",
                    },
                ],
            )
            config["targets"]["path"] = "targets.csv"
            config["targets"]["sha256"] = sha(targets)
            config["targets"]["expected_population"] = 3
            make_training_job(root, config, building_id=smoke, arm="A", run="r1")
            for building_id, arm, run in (
                (core_2, "A", "r1"),
                (smoke, "A", "r2"),
                (core_2, "A", "r2"),
                (core_2, "B", "r1"),
                (extension, "A", "r1"),
            ):
                make_training_job(
                    root,
                    config,
                    building_id=building_id,
                    arm=arm,
                    run=run,
                )
            smoke_job = MODULE.job_dir(
                config, smoke, "A", "r1", repo=root
            )
            smoke_job.mkdir(parents=True)
            write_json(smoke_job / "complete.json", {"state": "COMPLETE"})
            self.assertEqual(
                MODULE.list_pending(config, repo=root),
                [
                    f"{core_2}/arm_A/r1",
                    f"{smoke}/arm_A/r2",
                    f"{core_2}/arm_A/r2",
                    f"{core_2}/arm_B/r1",
                    f"{extension}/arm_A/r1",
                ],
            )

    def test_missing_mandatory_core_phase_blocks_extension_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = minimal_repo_config(root)
            targets = root / "targets.csv"
            smoke = "DEBY_LOD2_42364609"
            core_2 = "DEBY_LOD2_42364659"
            extension = "DEBY_LOD2_4907182"
            write_csv(
                targets,
                ["building_id", "processing_order", "cohort"],
                [
                    {
                        "building_id": smoke,
                        "processing_order": 1,
                        "cohort": "core",
                    },
                    {
                        "building_id": core_2,
                        "processing_order": 2,
                        "cohort": "core",
                    },
                    {
                        "building_id": extension,
                        "processing_order": 3,
                        "cohort": "extension",
                    },
                ],
            )
            config["targets"]["path"] = "targets.csv"
            config["targets"]["sha256"] = sha(targets)
            config["targets"]["expected_population"] = 3
            make_training_job(root, config, building_id=smoke)
            make_training_job(root, config, building_id=core_2)
            make_training_job(root, config, building_id=extension)
            smoke_job = MODULE.job_dir(
                config, smoke, "A", "r1", repo=root
            )
            smoke_job.mkdir(parents=True)
            write_json(smoke_job / "complete.json", {"state": "COMPLETE"})
            self.assertEqual(
                MODULE.list_pending(config, repo=root),
                [f"{core_2}/arm_A/r1"],
            )


class PanelMaterialTests(unittest.TestCase):
    def test_panel_contains_all_six_required_materials(self) -> None:
        import laspy
        import numpy as np
        from PIL import Image
        from shapely.geometry import Polygon

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = minimal_repo_config(root)
            data = root / "data"
            image_path = data / "images/view.png"
            image_path.parent.mkdir(parents=True)
            image = np.zeros((80, 100, 3), dtype=np.uint8)
            image[20:60, 25:75] = [80, 140, 200]
            Image.fromarray(image).save(image_path)
            mask_path = data / "photo_support_masks/view.npy"
            mask_path.parent.mkdir(parents=True)
            mask = np.zeros((80, 100), dtype=bool)
            mask[25:55, 30:70] = True
            np.save(mask_path, mask)
            supervision = data / "supervision.csv"
            write_csv(
                supervision,
                ["image_name", "photo_support_mask_path"],
                [
                    {
                        "image_name": "view.png",
                        "photo_support_mask_path": "data/photo_support_masks/view.npy",
                    }
                ],
            )
            seed = root / "seed.las"
            header = laspy.LasHeader(point_format=3, version="1.4")
            las = laspy.LasData(header)
            las.x = np.asarray([0.0, 1.0, 1.0, 0.0])
            las.y = np.asarray([0.0, 0.0, 1.0, 1.0])
            las.z = np.asarray([5.0, 5.0, 5.0, 5.0])
            las.classification = np.asarray([6, 6, 6, 6], dtype=np.uint8)
            las.write(seed)
            learned_path = root / "learned.npz"
            learned = np.asarray(
                [[0.0, 0.0, 5.0], [1.0, 0.0, 5.1], [1.0, 1.0, 5.2]]
            )
            np.savez(learned_path, P_utm_clean=learned)
            cityjson = root / "fusion.city.json"
            write_json(cityjson, {"type": "CityJSON", "version": "2.0"})
            surface = SimpleNamespace(
                polygon=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
            )
            materialization = {
                "job_key": "DEBY_LOD2_42364609/arm_A/r1",
                "building_id": "DEBY_LOD2_42364609",
                "arm": "A",
                "replicate": "r1",
                "training": {
                    "data_root": "data",
                    "supervision_index": "data/supervision.csv",
                    "train_views": ["view.png"],
                },
            }
            p0prime = {"row": {"seed_las": "seed.las"}}
            extract = {"pointcloud": {"path": "learned.npz"}}
            panel, materials = MODULE.render_panel(
                config,
                materialization,
                p0prime,
                extract,
                cityjson,
                [surface],
                [surface],
                repo=root,
            )
            self.assertTrue(panel.is_file())
            payload = json.loads(materials.read_text(encoding="utf-8"))
            self.assertEqual(payload["state"], "COMPLETE")
            self.assertIn("input_image_crop", payload)
            self.assertIn("seed_topview", payload)
            self.assertIn("learned_topview_and_section", payload)
            self.assertIn("assembled_model", payload)
            self.assertIn("reference", payload)
            self.assertIn("panel", payload)


if __name__ == "__main__":
    unittest.main()

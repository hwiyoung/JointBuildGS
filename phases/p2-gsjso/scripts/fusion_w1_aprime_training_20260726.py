#!/usr/bin/env python3
"""Materialize, audit, and launch the locked Fusion-W1 A-prime training jobs.

The numerical trainer always runs in the pinned Docker image.  Materialization
is also required to run in that image because it reopens every selected view
through ``ColmapDataset`` and proves that depth, normal, and photo supervision
resolve to the exact saved roof-TIN mask M_j.  The host-side ``launch`` command
only performs orchestration and receipt publication around one foreground job.

No readout, Roofer, scoring, or scientific verdict is implemented here.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import yaml


REPO = Path(__file__).resolve().parents[3]
CONTAINER_REPO = Path("/workspace/JointBuildGS")
DEFAULT_CONFIG = (
    REPO / "phases/p2-gsjso/configs/fusion_w1_aprime_training_20260726.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.training_driver.config.v1"
PREPROCESS_SCHEMA = "jointbuildgs.fusion_w1_aprime.preprocess_building.v1"
MATERIALIZATION_SCHEMA = "jointbuildgs.fusion_w1_aprime.training_materialization.v1"
STARTED_SCHEMA = "jointbuildgs.fusion_w1_aprime.training_started.v1"
COMPLETED_SCHEMA = "jointbuildgs.fusion_w1_aprime.training_completed.v1"
FAILED_SCHEMA = "jointbuildgs.fusion_w1_aprime.training_failed.v1"
COUNTER_SCHEMA = "jointbuildgs.fusion_w1_aprime.training_runtime_counter.v1"
QUEUE_SCHEMA = "jointbuildgs.fusion_w1_aprime.training_queue.v1"
T1_SCHEMA = "jointbuildgs.fusion_w1_aprime.t1_mini_smoke.receipt.v1"
ARMS = ("Aprime", "B")
RUNS = ("r1", "r2")
PROFILES = ("full", "mini_smoke")
ARM_DIFFERENCE_KEYS = frozenset(
    {"w_depth", "depth_final_weight", "w_normal", "normal_final_weight"}
)


class ContractError(RuntimeError):
    """A locked method, input, profile, or runtime condition drifted."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256_bytes(encoded)


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"JSON root must be an object: {path}")
    return payload


def require_equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise ContractError(f"{label}: observed={observed!r}, expected={expected!r}")


def resolve_path(repo: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        try:
            return repo / path.relative_to(CONTAINER_REPO)
        except ValueError:
            return path
    return repo / path


def relative(repo: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo.resolve()))
    except ValueError as exc:
        raise ContractError(f"path escapes repository: {path}") from exc


def container_path(repo: Path, path: Path) -> str:
    return str(CONTAINER_REPO / Path(relative(repo, path)))


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
        os.fchmod(stream.fileno(), 0o644)
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_text(
        path,
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
    )


def atomic_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(fields), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_text(path, buffer.getvalue())


def exclusive_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as exc:
        raise ContractError(f"exclusive receipt already exists: {path}") from exc
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={repo}", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode:
        raise ContractError(
            f"git {' '.join(args)} failed: {completed.stderr.strip()}"
        )
    return completed


def load_config(path: Path) -> dict[str, Any]:
    config = load_json(path)
    require_equal(config.get("schema"), CONFIG_SCHEMA, "driver config schema")
    require_equal(config.get("run_id"), "20260726_fusion_w1_aprime", "run namespace")
    require_equal(config.get("branch"), "exp/fusion-w1", "branch contract")
    recipe = config["recipe"]
    expected = {
        "max_iter": 30000,
        "run_seeds": {"r1": 1001, "r2": 1002},
        "init_pointcloud_mode": "replace",
        "mvs_seed_init_opacity": 0.1,
        "seed_protect": False,
        "surface_seed_protect": False,
        "seed_lineage_audit": True,
        "seed_lineage_audit_every": 500,
        "downscale": 1.0,
        "sh_degree": 3,
        "sh_up_every": 1000,
        "w_photo": 1.0,
        "photo_lam": 0.2,
        "load_depth": True,
        "load_normal": True,
        "depth_scale": 1.0,
        "depth_prior_alignment": "alpha_lsq",
        "depth_alignment_detach_scale": True,
        "depth_schedule": "constant_then_exp_decay",
        "depth_warmup": 15000,
        "depth_ramp_steps": 15000,
        "arm_Aprime_depth_weight": 0.5,
        "arm_Aprime_depth_final_weight": 0.05,
        "arm_B_depth_weight": 0.0,
        "arm_B_depth_final_weight": 0.0,
        "normal_prior_orientation": "signed",
        "normal_schedule": "constant_then_exp_decay",
        "normal_warmup": 15000,
        "normal_ramp_steps": 15000,
        "arm_Aprime_normal_weight": 0.05,
        "arm_Aprime_normal_final_weight": 0.005,
        "arm_B_normal_weight": 0.0,
        "arm_B_normal_final_weight": 0.0,
        "w_nc": 0.05,
        "nc_schedule": "ramp",
        "nc_warmup": 15000,
        "nc_ramp_steps": 5000,
        "w_distort": 100.0,
        "distort_normalization": "scene_scale_sq",
        "distort_schedule": "ramp",
        "distort_warmup": 15000,
        "distort_ramp_steps": 5000,
        "load_semantic": False,
        "seed_semantic": False,
        "lr_means": 0.00016,
        "lr_scales": 0.005,
        "lr_quats": 0.001,
        "lr_opacities": 0.05,
        "lr_sh0": 0.0025,
        "lr_shN": 0.000125,
        "prune_opa": 0.005,
        "grow_grad2d": 0.0002,
        "grow_scale3d": 0.01,
        "prune_scale3d": 0.1,
        "refine_start_iter": 500,
        "refine_stop_iter": 15000,
        "refine_every": 100,
        "reset_every": 3000,
        "eval_every": 2000,
        "ckpt_every": 5000,
        "full_state_checkpoint": True,
        "full_state_checkpoint_steps": [5000, 10000, 15000, 20000, 25000, 30000],
        "full_state_loss_csv_paths": ["audit/loss_grad_norms.csv", "audit/seed_lineage.csv"],
        "full_state_resume": "off",
        "loss_grad_audit_every": 500,
        "final_prune_opa": 0.0,
        "elongation_filter": False,
    }
    for key, value in expected.items():
        require_equal(recipe.get(key), value, f"full recipe {key}")
    for key in (
        "w_sem",
        "w_mutual",
        "w_structure",
        "w_mvc",
        "w_plane",
        "w_mono_depth",
        "w_mono_normal_aux",
        "w_semdepth_smooth",
        "w_semdepth_plane",
        "w_boundary_normal",
    ):
        require_equal(float(recipe.get(key, math.nan)), 0.0, f"forbidden term {key}")
    require_equal(
        config["inputs"].get("preprocess_cache_namespace"),
        "aprime_pose_28b38383a0b6d826_class6_e005_k3_rooftin_v2",
        "final preprocess v2 namespace",
    )
    require_equal(config["queue_contract"].get("expected_jobs"), 21, "queue size")
    require_equal(config["launch_contract"].get("time_cutoff"), None, "time cutoff")
    smoke = config["mini_smoke_profile"]
    prereg_smoke = {
        "max_iter": 600,
        "depth_warmup": 300,
        "depth_ramp_steps": 300,
        "normal_warmup": 300,
        "normal_ramp_steps": 300,
        "nc_warmup": 300,
        "nc_ramp_steps": 100,
        "distort_warmup": 300,
        "distort_ramp_steps": 100,
        "refine_start_iter": 50,
        "refine_stop_iter": 500,
        "refine_every": 25,
        "reset_every": 300,
    }
    for key, value in prereg_smoke.items():
        require_equal(smoke["overrides"].get(key), value, f"mini smoke {key}")
    require_equal(
        smoke.get("required_post_transition_components"),
        ["depth", "normal", "nc", "distort"],
        "mini smoke observed components",
    )
    require_equal(smoke.get("required_cumulative_pruned_min"), 1, "mini smoke prune floor")
    require_equal(smoke.get("seed_protection_must_remain_off"), True, "mini smoke protection")
    require_equal(smoke.get("full_recipe_is_unchanged"), True, "mini smoke recipe role")
    return config


def validate_locked_inputs(repo: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    records: dict[str, dict[str, str]] = {}
    inputs = config["inputs"]
    for name in ("prereg_lock", "pose_manifest", "gate_manifest", "targets_csv", "targets_manifest"):
        path = resolve_path(repo, inputs[name])
        if not path.is_file():
            raise ContractError(f"locked input missing: {inputs[name]}")
        observed = sha256_file(path)
        require_equal(observed, inputs[f"{name}_sha256"], f"{name} SHA-256")
        records[name] = {"path": relative(repo, path), "sha256": observed}
    prereg = load_json(resolve_path(repo, inputs["prereg_lock"]))
    require_equal(prereg.get("schema"), "jointbuildgs.fusion_w1_aprime.prereg_lock.v1", "prereg schema")
    require_equal(prereg["p7_targets"]["run_seeds"], {"r1": 1001, "r2": 1002}, "prereg seeds")
    require_equal(prereg["p4_dynamics"]["seed_protect"], False, "prereg seed protection")
    require_equal(prereg["p4_dynamics"]["surface_seed_protect"], False, "prereg surface protection")
    pose = load_json(resolve_path(repo, inputs["pose_manifest"]))
    require_equal(pose.get("status"), "PASSED", "pose manifest status")
    require_equal(
        pose.get("derived_sha256", {}).get("images.bin"),
        inputs["corrected_images_sha256"],
        "corrected pose images hash",
    )
    require_equal(
        int(pose.get("transform_application_count", -1)),
        int(inputs["transform_application_count"]),
        "pose transform application count",
    )
    gate_payload = load_json(resolve_path(repo, inputs["gate_manifest"]))
    gate_status = gate_payload.get("gate_slots", {}).get("status", gate_payload.get("status"))
    require_equal(gate_status, inputs["gate_required_status"], "Gate-A-v2 status")
    return records


def committed_method_gate(
    repo: Path,
    config: Mapping[str, Any],
    *,
    expected_head: str | None = None,
) -> dict[str, Any]:
    branch = git(repo, "branch", "--show-current").stdout.strip()
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    require_equal(branch, config["branch"], "git branch")
    if expected_head is not None:
        require_equal(head, expected_head, "launch HEAD vs materialization HEAD")
    records: list[dict[str, str]] = []
    for value in config["method_files"]:
        path = resolve_path(repo, value)
        if not path.is_file():
            raise ContractError(f"method file missing: {value}")
        if git(repo, "ls-files", "--error-unmatch", value, check=False).returncode:
            raise ContractError(f"method file is not committed: {value}")
        if git(repo, "diff", "--quiet", "HEAD", "--", value, check=False).returncode:
            raise ContractError(f"method file differs from committed HEAD: {value}")
        records.append({"path": value, "sha256": sha256_file(path)})
    return {"branch": branch, "head": head, "files": records}


def read_targets(repo: Path, config: Mapping[str, Any]) -> list[dict[str, str]]:
    path = resolve_path(repo, config["inputs"]["targets_csv"])
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = [dict(row) for row in csv.DictReader(stream)]
    if len(rows) != 9:
        raise ContractError(f"A-prime target population must be 9, got {len(rows)}")
    orders = [int(row["aprime_order"]) for row in rows]
    require_equal(orders, list(range(1, 10)), "A-prime target order")
    if len({row["building_id"] for row in rows}) != 9:
        raise ContractError("A-prime targets contain duplicate building IDs")
    if any(re.fullmatch(r"DEBY_LOD2_[0-9]+", row["building_id"]) is None for row in rows):
        raise ContractError("A-prime target has a noncanonical building ID")
    return rows


def _profile_recipe(config: Mapping[str, Any], profile: str) -> dict[str, Any]:
    if profile not in PROFILES:
        raise ContractError(f"unknown training profile: {profile}")
    recipe = dict(config["recipe"])
    if profile == "mini_smoke":
        recipe.update(config["mini_smoke_profile"]["overrides"])
    return recipe


def job_dir(
    repo: Path,
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    profile: str,
) -> Path:
    if re.fullmatch(r"DEBY_LOD2_[0-9]+", building_id) is None:
        raise ContractError(f"unsafe building ID: {building_id!r}")
    if arm not in ARMS or run not in RUNS or profile not in PROFILES:
        raise ContractError(f"invalid arm/run/profile: {arm}/{run}/{profile}")
    if profile == "mini_smoke":
        allowed = config["mini_smoke_profile"]["allowed_job"]
        require_equal(
            {"building_id": building_id, "arm": arm, "run": run},
            allowed,
            "mini-smoke job identity",
        )
    root_key = "mini_smoke_root" if profile == "mini_smoke" else "training_root"
    root = resolve_path(repo, config["outputs"][root_key])
    return root / "by_building" / building_id / f"arm_{arm}" / run


def build_training_config(
    *,
    repo: Path,
    config: Mapping[str, Any],
    preprocess: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    profile: str,
    out_dir: Path,
) -> dict[str, Any]:
    if arm not in ARMS or run not in RUNS:
        raise ContractError(f"invalid arm/run: {arm}/{run}")
    recipe = _profile_recipe(config, profile)
    views = preprocess["selected_names"]
    if arm == "Aprime":
        w_depth = float(recipe["arm_Aprime_depth_weight"])
        depth_final = float(recipe["arm_Aprime_depth_final_weight"])
        w_normal = float(recipe["arm_Aprime_normal_weight"])
        normal_final = float(recipe["arm_Aprime_normal_final_weight"])
    else:
        w_depth = float(recipe["arm_B_depth_weight"])
        depth_final = float(recipe["arm_B_depth_final_weight"])
        w_normal = float(recipe["arm_B_normal_weight"])
        normal_final = float(recipe["arm_B_normal_final_weight"])

    def value(key: str) -> Any:
        return recipe[key]

    data_root = resolve_path(repo, preprocess["data_root"])
    seed_path = resolve_path(repo, preprocess["seed_canonical_npz"])
    return {
        "seed": int(recipe["run_seeds"][run]),
        "device": "cuda",
        "data_root": container_path(repo, data_root),
        "out_dir": container_path(repo, out_dir),
        "init_pointcloud": container_path(repo, seed_path),
        "init_pointcloud_mode": "replace",
        "mvs_seed_init_opacity": float(value("mvs_seed_init_opacity")),
        "seed_protect": False,
        "surface_seed_protect": False,
        "seed_lineage_audit": True,
        "seed_lineage_audit_every": int(value("seed_lineage_audit_every")),
        "visible_views": list(views),
        "train_views": list(views),
        "eval_views": [],
        "photo_mask_dir": container_path(repo, data_root / "photo_support_masks"),
        "downscale": 1.0,
        "sh_degree": int(value("sh_degree")),
        "sh_up_every": int(value("sh_up_every")),
        "w_photo": float(value("w_photo")),
        "photo_lam": float(value("photo_lam")),
        "load_depth": True,
        "load_normal": True,
        "depth_scale": float(value("depth_scale")),
        "w_depth": w_depth,
        "depth_prior_alignment": "alpha_lsq",
        "depth_alignment_detach_scale": True,
        "depth_schedule": value("depth_schedule"),
        "depth_warmup": int(value("depth_warmup")),
        "depth_ramp_steps": int(value("depth_ramp_steps")),
        "depth_final_weight": depth_final,
        "w_normal": w_normal,
        "normal_prior_orientation": "signed",
        "normal_schedule": value("normal_schedule"),
        "normal_warmup": int(value("normal_warmup")),
        "normal_ramp_steps": int(value("normal_ramp_steps")),
        "normal_final_weight": normal_final,
        "w_nc": float(value("w_nc")),
        "nc_schedule": value("nc_schedule"),
        "nc_warmup": int(value("nc_warmup")),
        "nc_ramp_steps": int(value("nc_ramp_steps")),
        "w_distort": float(value("w_distort")),
        "distort_normalization": value("distort_normalization"),
        "distort_schedule": value("distort_schedule"),
        "distort_warmup": int(value("distort_warmup")),
        "distort_ramp_steps": int(value("distort_ramp_steps")),
        "load_semantic": False,
        "seed_semantic": False,
        "w_sem": 0.0,
        "w_mutual": 0.0,
        "w_structure": 0.0,
        "w_mvc": 0.0,
        "w_plane": 0.0,
        "w_mono_depth": 0.0,
        "w_mono_normal_aux": 0.0,
        "w_semdepth_smooth": 0.0,
        "w_semdepth_plane": 0.0,
        "w_boundary_normal": 0.0,
        "lr_means": float(value("lr_means")),
        "lr_scales": float(value("lr_scales")),
        "lr_quats": float(value("lr_quats")),
        "lr_opacities": float(value("lr_opacities")),
        "lr_sh0": float(value("lr_sh0")),
        "lr_shN": float(value("lr_shN")),
        "prune_opa": float(value("prune_opa")),
        "grow_grad2d": float(value("grow_grad2d")),
        "grow_scale3d": float(value("grow_scale3d")),
        "prune_scale3d": float(value("prune_scale3d")),
        "refine_start_iter": int(value("refine_start_iter")),
        "refine_stop_iter": int(value("refine_stop_iter")),
        "refine_every": int(value("refine_every")),
        "reset_every": int(value("reset_every")),
        "max_iter": int(value("max_iter")),
        "eval_every": int(value("eval_every")),
        "ckpt_every": int(value("ckpt_every")),
        "full_state_checkpoint": True,
        "full_state_checkpoint_steps": list(value("full_state_checkpoint_steps")),
        "full_state_loss_csv_paths": list(value("full_state_loss_csv_paths")),
        "full_state_resume": "off",
        "loss_grad_audit_every": int(value("loss_grad_audit_every")),
        "final_prune_opa": 0.0,
        "elongation_filter": False,
    }


def validate_ablation_pair(
    config_a: Mapping[str, Any], config_b: Mapping[str, Any]
) -> dict[str, Any]:
    differences = {
        key
        for key in set(config_a) | set(config_b)
        if config_a.get(key) != config_b.get(key)
    }
    require_equal(differences, ARM_DIFFERENCE_KEYS, "A-prime/B difference keys")
    require_equal(config_a["w_depth"], 0.5, "A-prime depth weight")
    require_equal(config_a["depth_final_weight"], 0.05, "A-prime depth endpoint")
    require_equal(config_a["w_normal"], 0.05, "A-prime normal weight")
    require_equal(config_a["normal_final_weight"], 0.005, "A-prime normal endpoint")
    require_equal(config_b["w_depth"], 0.0, "arm B depth weight")
    require_equal(config_b["w_normal"], 0.0, "arm B normal weight")
    for key in ("load_depth", "load_normal", "photo_mask_dir", "train_views", "eval_views"):
        require_equal(config_a[key], config_b[key], f"A-prime/B shared {key}")
    return {
        "status": "PASSED",
        "difference_keys": sorted(differences),
        "all_other_keys_identical": True,
        "maps_and_exact_M_j_loaded_in_both_arms": True,
    }


def schedule_weight_reference(
    *, base: float, final: float, iteration: int, transition: int, steps: int
) -> float:
    """Pure reference for the trainer's constant-then-exponential schedule."""
    if float(base) == 0.0 and float(final) == 0.0:
        return 0.0
    if iteration < transition:
        return float(base)
    if steps <= 1:
        return float(final)
    t = min(1.0, (iteration - transition) / (steps - 1))
    return math.exp(math.log(base) * (1.0 - t) + math.log(final) * t)


def require_docker_materializer() -> None:
    if not Path("/.dockerenv").is_file():
        raise ContractError(
            "materialization and exact-M_j roundtrip must run in the pinned Docker image"
        )


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _preprocess_manifest_path(
    repo: Path, config: Mapping[str, Any], building_id: str
) -> Path:
    stable = resolve_path(repo, config["inputs"]["preprocess_stable_root"])
    namespace = str(config["inputs"]["preprocess_cache_namespace"])
    return stable / namespace / "by_building" / building_id / "preprocess_manifest.json"


def _artifact_record(
    *,
    repo: Path,
    manifest: Mapping[str, Any],
    raw_path: str,
    label: str,
    verify_hash: bool = True,
) -> dict[str, Any]:
    inventory = manifest.get("artifact_sha256")
    if not isinstance(inventory, Mapping):
        raise ContractError("preprocess artifact_sha256 inventory is missing")
    expected = inventory.get(raw_path)
    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise ContractError(f"preprocess artifact is not hash-bound ({label}): {raw_path}")
    path = resolve_path(repo, raw_path)
    if not path.is_file():
        raise ContractError(f"preprocess artifact missing ({label}): {raw_path}")
    observed = sha256_file(path) if verify_hash else expected
    require_equal(observed, expected, f"preprocess artifact SHA-256 ({label})")
    return {"path": relative(repo, path), "sha256": expected}


def _read_supervision_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = [dict(row) for row in csv.DictReader(stream)]
    required = {
        "selection_order",
        "building_id",
        "image_name",
        "class6_npz_path",
        "depth_path",
        "normal_path",
        "valid_M_j_path",
        "photo_support_mask_path",
        "mask_pixels_n",
        "pose_sha256",
        "photo_equals_M_j",
        "supervision_class",
    }
    if not rows or not required.issubset(rows[0]):
        raise ContractError(
            f"supervision index fields drifted: missing={sorted(required - set(rows[0] if rows else []))}"
        )
    return rows


def validate_mask_triplet(
    *,
    image_name: str,
    expected: np.ndarray,
    depth_mask: np.ndarray,
    normal_mask: np.ndarray,
    photo_mask: np.ndarray,
) -> dict[str, Any]:
    """Validate that the three trainer masks are exactly the saved M_j array."""
    arrays = {
        "expected_M_j": np.asarray(expected),
        "depth_mask": np.asarray(depth_mask),
        "normal_mask": np.asarray(normal_mask),
        "photo_mask": np.asarray(photo_mask),
    }
    shapes = {name: value.shape for name, value in arrays.items()}
    if len(set(shapes.values())) != 1:
        raise ContractError(f"M_j shape mismatch for {image_name}: {shapes}")
    expected_bool = arrays["expected_M_j"].astype(np.bool_, copy=False)
    for name in ("depth_mask", "normal_mask", "photo_mask"):
        observed = arrays[name].astype(np.bool_, copy=False)
        if not np.array_equal(observed, expected_bool):
            differing = int(np.count_nonzero(observed != expected_bool))
            raise ContractError(
                f"trainer {name} differs from exact M_j for {image_name}: pixels={differing}"
            )
    pixels = int(expected_bool.sum())
    if pixels <= 0:
        raise ContractError(f"saved M_j is empty for {image_name}")
    return {
        "image_name": image_name,
        "shape": list(expected_bool.shape),
        "mask_pixels_n": pixels,
        "depth_equals_M_j": True,
        "normal_equals_M_j": True,
        "photo_equals_M_j": True,
    }


def _validate_dataloader_roundtrip(
    *,
    repo: Path,
    data_root: Path,
    selected_names: Sequence[str],
    rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    try:
        from src.stage2.dataloader import ColmapDataset
    except Exception as exc:  # pragma: no cover - environment failure
        raise ContractError(f"cannot import ColmapDataset in materializer: {exc}") from exc

    row_by_name = {str(row["image_name"]): row for row in rows}
    dataset = ColmapDataset(
        data_root,
        downscale=1.0,
        load_depth=True,
        load_normal=True,
        load_semantic=False,
        visible_views=list(selected_names),
        photo_mask_dir=data_root / "photo_support_masks",
    )
    require_equal(len(dataset), len(selected_names), "dataloader selected view count")
    per_view: list[dict[str, Any]] = []
    for index, expected_name in enumerate(selected_names):
        batch = dataset[index]
        require_equal(batch.get("name"), expected_name, "dataloader image identity/order")
        for key in ("depth", "depth_mask", "normal", "normal_mask", "photo_mask"):
            if key not in batch:
                raise ContractError(f"dataloader omitted {key} for {expected_name}")
        row = row_by_name[expected_name]
        valid_path = resolve_path(repo, row["valid_M_j_path"])
        class6_path = resolve_path(repo, row["class6_npz_path"])
        expected = np.load(valid_path, allow_pickle=False)
        if expected.ndim != 2:
            raise ContractError(f"saved valid_M_j must be HxW: {valid_path}")
        with np.load(class6_path, allow_pickle=False) as archive:
            if set(archive.files) != {"depth_camera_z_m", "normal_world", "valid_M_j"}:
                raise ContractError(
                    f"class6 supervision archive fields drifted: {class6_path}"
                )
            archive_mask = archive["valid_M_j"].astype(np.bool_)
            if not np.array_equal(archive_mask, expected.astype(np.bool_)):
                raise ContractError(f"class6 NPZ valid_M_j differs from saved mask: {expected_name}")
            depth_target = archive["depth_camera_z_m"]
            normal_target = archive["normal_world"]
            if bool(np.any(depth_target[~archive_mask] != 0.0)):
                raise ContractError(f"depth target is nonzero outside M_j: {expected_name}")
            if bool(np.any(normal_target[~archive_mask] != 0.0)):
                raise ContractError(f"normal target is nonzero outside M_j: {expected_name}")
        evidence = validate_mask_triplet(
            image_name=expected_name,
            expected=expected,
            depth_mask=batch["depth_mask"].cpu().numpy(),
            normal_mask=batch["normal_mask"].cpu().numpy(),
            photo_mask=batch["photo_mask"].cpu().numpy(),
        )
        require_equal(
            evidence["mask_pixels_n"], int(row["mask_pixels_n"]), "M_j pixel count"
        )
        per_view.append(evidence)
    return {
        "status": "PASSED",
        "implementation": "src.stage2.dataloader.ColmapDataset",
        "downscale": 1.0,
        "views_n": len(per_view),
        "mask_pixels_total": sum(item["mask_pixels_n"] for item in per_view),
        "all_depth_normal_photo_masks_exactly_equal_saved_M_j": True,
        "per_view": per_view,
    }


def validate_preprocess(
    repo: Path,
    config: Mapping[str, Any],
    building_id: str,
    *,
    roundtrip: bool,
    hash_artifacts: bool = True,
) -> dict[str, Any]:
    path = _preprocess_manifest_path(repo, config, building_id)
    manifest = load_json(path)
    inputs = config["inputs"]
    require_equal(manifest.get("schema"), PREPROCESS_SCHEMA, "preprocess building schema")
    require_equal(manifest.get("status"), inputs["preprocess_required_status"], "preprocess status")
    require_equal(manifest.get("run_id"), config["run_id"], "preprocess run")
    require_equal(
        manifest.get("building", {}).get("building_id"), building_id, "preprocess building"
    )
    data_root = resolve_path(repo, manifest["data_root"])
    required_root = resolve_path(repo, inputs["preprocess_stable_root"])
    required_namespace_root = required_root / inputs["preprocess_cache_namespace"]
    if not _path_is_within(data_root, required_namespace_root / "by_building"):
        raise ContractError(f"preprocess data root escapes new A-prime cache: {data_root}")
    forbidden = resolve_path(repo, inputs["old_preprocess_root_forbidden"])
    if _path_is_within(data_root, forbidden):
        raise ContractError("old arm-A preprocess cache was selected")

    cache = manifest.get("cache_policy", {})
    require_equal(cache.get("namespace"), inputs["preprocess_cache_namespace"], "cache namespace")
    require_equal(cache.get("old_arm_A_cache_read_count"), 0, "old cache read count")
    require_equal(cache.get("old_arm_A_cache_reused"), False, "old cache reuse")
    require_equal(cache.get("supervision_and_seed_regenerated"), True, "cache regeneration")

    pose = manifest.get("pose_binding", {})
    require_equal(
        pose.get("corrected_images_sha256"),
        inputs["corrected_images_sha256"],
        "preprocess corrected pose hash",
    )
    require_equal(
        int(pose.get("transform_application_count", -1)),
        int(inputs["transform_application_count"]),
        "preprocess transform count",
    )
    require_equal(
        int(pose.get("additional_transform_application_count", -1)),
        0,
        "preprocess additional transform count",
    )

    method = manifest.get("method_binding")
    if not isinstance(method, Mapping) or not isinstance(method.get("required_files"), list):
        raise ContractError("preprocess method binding is missing")
    require_equal(method.get("branch"), config["branch"], "preprocess generation branch")
    generation_head = str(method.get("head", ""))
    if re.fullmatch(r"[0-9a-f]{40}", generation_head) is None:
        raise ContractError("preprocess generation HEAD is invalid")
    ancestry = git(repo, "merge-base", "--is-ancestor", generation_head, "HEAD", check=False)
    if ancestry.returncode:
        raise ContractError("preprocess generation HEAD is not an ancestor of current HEAD")
    method_files: list[dict[str, str]] = []
    for record in method["required_files"]:
        raw = str(record.get("path", ""))
        expected = str(record.get("sha256", ""))
        file_path = resolve_path(repo, raw)
        if not file_path.is_file():
            raise ContractError(f"preprocess method-bound file missing: {raw}")
        require_equal(sha256_file(file_path), expected, f"preprocess method hash {raw}")
        if git(repo, "ls-files", "--error-unmatch", raw, check=False).returncode:
            raise ContractError(f"preprocess method-bound file is not committed: {raw}")
        if git(repo, "diff", "--quiet", "HEAD", "--", raw, check=False).returncode:
            raise ContractError(f"preprocess method-bound file differs from HEAD: {raw}")
        method_files.append({"path": raw, "sha256": expected})

    views = manifest.get("views", {})
    selected = list(views.get("selected_names") or [])
    training = list(views.get("training_names") or [])
    evaluation = list(views.get("evaluation_names") or [])
    if not selected or len(selected) != len(set(selected)):
        raise ContractError("preprocess selected view inventory is empty or duplicated")
    require_equal(training, selected, "all selected views are training views")
    require_equal(evaluation, [], "A-prime evaluation view inventory")
    require_equal(views.get("visibility_vote_views_equal_training_views"), True, "visibility/train equality")
    require_equal(views.get("inventory_equality_verified"), True, "view inventory equality")
    require_equal(int(views.get("count", -1)), len(selected), "view count")
    colmap = manifest.get("colmap_data_root", {})
    require_equal(colmap.get("directly_consumable"), True, "COLMAP root consumability")
    require_equal(colmap.get("sparse_points_source"), "filtered_ALS_class6_only", "COLMAP point source")
    require_equal(int(colmap.get("class2_points_n", -1)), 0, "trainer class2 rows")
    require_equal(int(colmap.get("sfm_points_n", -1)), 0, "trainer SfM rows")
    require_equal(float(colmap.get("training_downscale_required", math.nan)), 1.0, "training downscale")

    seed = manifest.get("seed", {})
    require_equal(int(seed.get("class2_rows_n", -1)), 0, "seed class2 rows")
    require_equal(int(seed.get("sfm_rows_n", -1)), 0, "seed SfM rows")
    require_equal(float(seed.get("init_opacity", math.nan)), 0.1, "seed init opacity")
    require_equal(seed.get("classification_counts"), {"6": int(seed["filtered_points_n"])}, "seed classes")
    seed_record = seed.get("canonical_npz", {})
    seed_path = resolve_path(repo, seed_record["path"])
    require_equal(sha256_file(seed_path), seed_record.get("sha256"), "seed NPZ SHA-256")
    with np.load(seed_path, allow_pickle=False) as archive:
        for field in ("classification", "init_opacity", "visibility_votes", "xyz", "rgb"):
            if field not in archive.files:
                raise ContractError(f"A-prime seed NPZ omits {field}")
        classes = archive["classification"]
        opacities = archive["init_opacity"]
        votes = archive["visibility_votes"]
        count = int(archive["xyz"].shape[0])
        if classes.shape != (count,) or not bool(np.all(classes == 6)):
            raise ContractError("training seed is not class6-only")
        if opacities.shape != (count,) or not bool(np.allclose(opacities, 0.1, rtol=0, atol=1e-7)):
            raise ContractError("training seed opacity is not exactly the locked 0.1")
        if votes.shape != (count,) or not bool(np.all(votes >= 3)):
            raise ContractError("training seed contains a point below the k=3 visibility gate")
    require_equal(count, int(seed["filtered_points_n"]), "seed NPZ point count")

    ground = manifest.get("ground_readout_only", {})
    require_equal(ground.get("role"), "P0prime_and_readout_join_only_never_trainer", "ground role")
    require_equal(ground.get("trainer_path_reference"), False, "ground trainer reference")
    require_equal(ground.get("classification_counts"), {"2": int(ground["points_n"])}, "ground classes")

    supervision = manifest.get("supervision", {})
    require_equal(supervision.get("classes"), [6], "supervision classes")
    require_equal(supervision.get("ground_supervision"), False, "ground supervision")
    require_equal(supervision.get("wall_supervision"), False, "wall supervision")
    require_equal(supervision.get("photo_mask"), "exact_M_j", "photo mask role")
    require_equal(
        supervision.get("mask_normalization_denominator"),
        "cardinality_M_j",
        "mask normalization denominator",
    )
    require_equal(int(supervision.get("views_n", -1)), len(selected), "supervision view count")
    index_record = supervision.get("index", {})
    index_path = resolve_path(repo, index_record["path"])
    require_equal(sha256_file(index_path), index_record.get("sha256"), "supervision index SHA-256")
    rows = _read_supervision_rows(index_path)
    require_equal(len(rows), len(selected), "supervision row count")
    require_equal({row["image_name"] for row in rows}, set(selected), "supervision view set")
    if any(row["building_id"] != building_id for row in rows):
        raise ContractError("supervision index contains a different building")
    if any(row["pose_sha256"] != inputs["corrected_images_sha256"] for row in rows):
        raise ContractError("supervision index pose hash drifted")
    if any(row["supervision_class"] != "6" for row in rows):
        raise ContractError("supervision index contains a non-class6 row")
    if any(row["photo_equals_M_j"].lower() != "true" for row in rows):
        raise ContractError("supervision index reports photo mask != M_j")

    artifacts: list[dict[str, Any]] = []
    key_paths = [
        seed_record["path"],
        views["csv"]["path"],
        index_record["path"],
        relative(repo, data_root / "sparse/0/cameras.bin"),
        relative(repo, data_root / "sparse/0/images.bin"),
        relative(repo, data_root / "sparse/0/points3D.bin"),
    ]
    for row in rows:
        key_paths.extend(
            row[key]
            for key in (
                "class6_npz_path",
                "depth_path",
                "normal_path",
                "valid_M_j_path",
                "photo_support_mask_path",
            )
        )
    for raw in sorted(set(key_paths)):
        artifacts.append(
            _artifact_record(
                repo=repo,
                manifest=manifest,
                raw_path=raw,
                label="training_input",
                verify_hash=hash_artifacts,
            )
        )
    artifact_snapshot_sha = canonical_json_sha256(artifacts)
    dataloader = (
        _validate_dataloader_roundtrip(
            repo=repo, data_root=data_root, selected_names=selected, rows=rows
        )
        if roundtrip
        else {
            "status": "BOUND_FROM_MATERIALIZATION",
            "views_n": len(selected),
            "all_depth_normal_photo_masks_exactly_equal_saved_M_j": None,
        }
    )
    return {
        "status": "PASSED",
        "building_id": building_id,
        "manifest": relative(repo, path),
        "manifest_sha256": sha256_file(path),
        "data_root": relative(repo, data_root),
        "seed_canonical_npz": relative(repo, seed_path),
        "seed_canonical_npz_sha256": sha256_file(seed_path),
        "seed_points_n": count,
        "seed_too_small": bool(seed.get("seed_too_small")),
        "selected_names": selected,
        "training_names": training,
        "evaluation_names": evaluation,
        "view_count": len(selected),
        "supervision_index": relative(repo, index_path),
        "supervision_index_sha256": sha256_file(index_path),
        "training_artifacts": artifacts,
        "training_artifact_snapshot_sha256": artifact_snapshot_sha,
        "method_binding": {
            "generation_head": generation_head,
            "required_files": method_files,
        },
        "pose_binding": dict(pose),
        "cache_policy": dict(cache),
        "dataloader_roundtrip": dataloader,
        "full_snapshot_sha256": canonical_json_sha256(
            {
                "manifest_sha256": sha256_file(path),
                "artifact_snapshot_sha256": artifact_snapshot_sha,
            }
        ),
    }


def _method_hash_lookup(method: Mapping[str, Any]) -> dict[str, str]:
    return {str(record["path"]): str(record["sha256"]) for record in method["files"]}


def _write_compose_override(path: Path, service: str) -> None:
    payload = {"services": {service: {"network_mode": "none"}}}
    atomic_text(
        path,
        yaml.safe_dump(payload, sort_keys=True, allow_unicode=True, default_flow_style=False),
    )


def materialize(
    *,
    repo: Path,
    config_path: Path,
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    profile: str,
    require_docker: bool = True,
) -> dict[str, Any]:
    if require_docker:
        require_docker_materializer()
    method = committed_method_gate(repo, config)
    locked_inputs = validate_locked_inputs(repo, config)
    targets = read_targets(repo, config)
    if building_id not in {row["building_id"] for row in targets}:
        raise ContractError(f"building is outside locked A-prime targets: {building_id}")
    preprocess = validate_preprocess(
        repo, config, building_id, roundtrip=True, hash_artifacts=True
    )
    target = job_dir(repo, config, building_id, arm, run, profile)
    outputs = config["outputs"]
    if target.exists():
        raise ContractError(f"job directory already exists; immutable materialization: {target}")
    comparison_out = resolve_path(repo, config["outputs"]["training_root"]) / "_ablation_compare"
    a_config = build_training_config(
        repo=repo,
        config=config,
        preprocess=preprocess,
        building_id=building_id,
        arm="Aprime",
        run=run,
        profile=profile,
        out_dir=comparison_out,
    )
    b_config = build_training_config(
        repo=repo,
        config=config,
        preprocess=preprocess,
        building_id=building_id,
        arm="B",
        run=run,
        profile=profile,
        out_dir=comparison_out,
    )
    ablation = validate_ablation_pair(a_config, b_config)
    selected = build_training_config(
        repo=repo,
        config=config,
        preprocess=preprocess,
        building_id=building_id,
        arm=arm,
        run=run,
        profile=profile,
        out_dir=target,
    )
    target.mkdir(parents=True, exist_ok=False)
    resolved_path = target / outputs["resolved_config"]
    override_path = target / outputs["compose_override"]
    manifest_path = target / outputs["materialization_manifest"]
    atomic_text(
        resolved_path,
        yaml.safe_dump(
            selected, sort_keys=False, allow_unicode=True, default_flow_style=False
        ),
    )
    _write_compose_override(override_path, config["launch_contract"]["docker_service"])
    receipt_names = (
        outputs["started_receipt"],
        outputs["completed_receipt"],
        outputs["failed_receipt"],
    )
    payload = {
        "schema": MATERIALIZATION_SCHEMA,
        "status": "PASSED",
        "created_at": utc_now(),
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "profile": profile,
        "seed": selected["seed"],
        "git": method,
        "driver_config": relative(repo, config_path),
        "driver_config_sha256": sha256_file(config_path),
        "locked_inputs": locked_inputs,
        "preprocess": preprocess,
        "recipe": {
            "full_recipe_sha256": canonical_json_sha256(config["recipe"]),
            "profile_overrides": (
                dict(config["mini_smoke_profile"]["overrides"])
                if profile == "mini_smoke"
                else {}
            ),
            "resolved_scientific_config_sha256": canonical_json_sha256(selected),
        },
        "view_roles": {
            "visible_views": preprocess["selected_names"],
            "training_views": preprocess["training_names"],
            "evaluation_views": [],
            "all_selected_views_are_training_views": True,
        },
        "ablation_validation": ablation,
        "resolved_config": relative(repo, resolved_path),
        "resolved_config_sha256": sha256_file(resolved_path),
        "compose_override": relative(repo, override_path),
        "compose_override_sha256": sha256_file(override_path),
        "network_mode": "none",
        "output_dir": relative(repo, target),
        "runtime_receipts_present_at_publication": {name: False for name in receipt_names},
        "learning_runs_started": 0,
        "publication": {
            "resolved_config_written_first": True,
            "compose_override_written_before_manifest": True,
            "manifest_written_last": True,
            "actual_training_started": False,
        },
    }
    atomic_json(manifest_path, payload)
    return payload


def _load_materialization(
    repo: Path,
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    profile: str,
) -> tuple[Path, dict[str, Any], str]:
    target = job_dir(repo, config, building_id, arm, run, profile)
    path = target / config["outputs"]["materialization_manifest"]
    payload = load_json(path)
    require_equal(payload.get("schema"), MATERIALIZATION_SCHEMA, "materialization schema")
    require_equal(payload.get("status"), "PASSED", "materialization status")
    require_equal(payload.get("building_id"), building_id, "materialization building")
    require_equal(payload.get("arm"), arm, "materialization arm")
    require_equal(payload.get("replicate"), run, "materialization replicate")
    require_equal(payload.get("profile"), profile, "materialization profile")
    return path, payload, sha256_file(path)


def check_materialization(
    *,
    repo: Path,
    config_path: Path,
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    profile: str,
    roundtrip: bool,
) -> dict[str, Any]:
    path, materialization, digest = _load_materialization(
        repo, config, building_id, arm, run, profile
    )
    method = committed_method_gate(
        repo, config, expected_head=materialization["git"]["head"]
    )
    require_equal(method, materialization["git"], "materialized method snapshot")
    require_equal(
        sha256_file(config_path),
        materialization["driver_config_sha256"],
        "driver config since materialization",
    )
    require_equal(
        validate_locked_inputs(repo, config),
        materialization["locked_inputs"],
        "locked input snapshot",
    )
    preprocess = validate_preprocess(
        repo, config, building_id, roundtrip=roundtrip, hash_artifacts=True
    )
    for key in (
        "manifest_sha256",
        "full_snapshot_sha256",
        "training_artifact_snapshot_sha256",
        "seed_canonical_npz_sha256",
        "supervision_index_sha256",
    ):
        require_equal(preprocess[key], materialization["preprocess"][key], f"preprocess {key}")
    target = job_dir(repo, config, building_id, arm, run, profile)
    resolved_path = target / config["outputs"]["resolved_config"]
    override_path = target / config["outputs"]["compose_override"]
    require_equal(
        sha256_file(resolved_path), materialization["resolved_config_sha256"], "resolved config hash"
    )
    require_equal(
        sha256_file(override_path), materialization["compose_override_sha256"], "compose override hash"
    )
    with resolved_path.open("r", encoding="utf-8") as stream:
        resolved = yaml.safe_load(stream)
    expected = build_training_config(
        repo=repo,
        config=config,
        preprocess=preprocess,
        building_id=building_id,
        arm=arm,
        run=run,
        profile=profile,
        out_dir=target,
    )
    require_equal(resolved, expected, "resolved training config reconstruction")
    comparison_out = resolve_path(repo, config["outputs"]["training_root"]) / "_ablation_compare"
    a_config = build_training_config(
        repo=repo, config=config, preprocess=preprocess, building_id=building_id,
        arm="Aprime", run=run, profile=profile, out_dir=comparison_out,
    )
    b_config = build_training_config(
        repo=repo, config=config, preprocess=preprocess, building_id=building_id,
        arm="B", run=run, profile=profile, out_dir=comparison_out,
    )
    ablation = validate_ablation_pair(a_config, b_config)
    require_equal(ablation, materialization["ablation_validation"], "ablation snapshot")
    return {
        "status": "PASSED",
        "materialization_manifest": relative(repo, path),
        "materialization_manifest_sha256": digest,
        "method_head": method["head"],
        "resolved_config": relative(repo, resolved_path),
        "resolved_config_sha256": sha256_file(resolved_path),
        "preprocess_full_snapshot_sha256": preprocess["full_snapshot_sha256"],
        "dataloader_roundtrip_reexecuted": roundtrip,
        "runtime_receipts": {
            name: (target / name).is_file()
            for name in (
                config["outputs"]["started_receipt"],
                config["outputs"]["completed_receipt"],
                config["outputs"]["failed_receipt"],
            )
        },
    }


def _profile_root(repo: Path, config: Mapping[str, Any], profile: str) -> Path:
    key = "mini_smoke_root" if profile == "mini_smoke" else "training_root"
    return resolve_path(repo, config["outputs"][key])


def _validate_preflight_gate(
    repo: Path, name: str, contract: Mapping[str, Any]
) -> dict[str, Any]:
    if name == "T2":
        return _validate_t2_gate(repo, contract)
    path = resolve_path(repo, contract["path"])
    payload = load_json(path)
    require_equal(payload.get("schema"), contract["schema"], f"{name} gate schema")
    field = str(contract.get("status_field", "status"))
    require_equal(payload.get(field), contract["accepted_status"], f"{name} gate {field}")
    return {
        "path": relative(repo, path),
        "sha256": sha256_file(path),
        "schema": str(payload["schema"]),
        "status_field": field,
        "accepted_status": str(payload[field]),
    }


def _current_file_record(
    repo: Path, record: Mapping[str, Any], label: str, *, require_bytes: bool
) -> dict[str, Any]:
    raw = record.get("path")
    expected = record.get("sha256")
    if not isinstance(raw, str) or not raw:
        raise ContractError(f"{label} path is missing")
    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise ContractError(f"{label} SHA-256 is invalid")
    path = resolve_path(repo, raw)
    if not path.is_file():
        raise ContractError(f"{label} file is missing: {raw}")
    require_equal(sha256_file(path), expected, f"{label} current SHA-256")
    observed_bytes = int(path.stat().st_size)
    if require_bytes:
        require_equal(int(record.get("bytes", -1)), observed_bytes, f"{label} byte count")
    return {"path": relative(repo, path), "sha256": expected, "bytes": observed_bytes}


def _validate_t2_gate(
    repo: Path, contract: Mapping[str, Any]
) -> dict[str, Any]:
    """Reject the obsolete uncommitted T2 receipt and bind the rerun in full."""
    path = resolve_path(repo, contract["path"])
    payload = load_json(path)
    require_equal(payload.get("schema"), contract["schema"], "T2 gate schema")
    field = str(contract["status_field"])
    require_equal(payload.get(field), contract["accepted_status"], "T2 gate status")
    require_equal(payload.get("identity"), contract["identity"], "T2 rehearsal identity")
    require_equal(payload.get("verdict"), None, "T2 verdict field")

    git_lock = payload.get("git_lock")
    if not isinstance(git_lock, Mapping):
        raise ContractError("T2 receipt lacks the committed git_lock")
    require_equal(git_lock.get("branch"), "exp/fusion-w1", "T2 git branch")
    t2_head = str(git_lock.get("head", ""))
    if re.fullmatch(r"[0-9a-f]{40}", t2_head) is None:
        raise ContractError("T2 receipt git HEAD is null or invalid")
    current_head = git(repo, "rev-parse", "HEAD").stdout.strip()
    require_equal(t2_head, current_head, "T2 receipt HEAD vs launch HEAD")
    implementation = git_lock.get("implementation_files")
    if not isinstance(implementation, list):
        raise ContractError("T2 git_lock implementation inventory is missing")
    require_equal(len(implementation), 4, "T2 committed implementation count")
    expected_paths = list(contract["implementation_files"])
    require_equal(
        [record.get("path") for record in implementation],
        expected_paths,
        "T2 implementation path inventory",
    )
    implementation_records: list[dict[str, Any]] = []
    for record in implementation:
        raw = str(record.get("path", ""))
        require_equal(record.get("tracked_at_head"), True, f"T2 tracked method {raw}")
        require_equal(record.get("worktree_matches_head"), True, f"T2 clean method {raw}")
        file_record = _current_file_record(
            repo, record, f"T2 implementation {raw}", require_bytes=False
        )
        blob = git(repo, "rev-parse", f"{t2_head}:{raw}", check=False)
        if blob.returncode:
            raise ContractError(f"T2 method did not exist at receipt HEAD: {raw}")
        require_equal(blob.stdout.strip(), record.get("git_blob"), f"T2 method git blob {raw}")
        if git(repo, "ls-files", "--error-unmatch", raw, check=False).returncode:
            raise ContractError(f"T2 implementation is no longer committed: {raw}")
        if git(repo, "diff", "--quiet", "HEAD", "--", raw, check=False).returncode:
            raise ContractError(f"T2 implementation differs from current HEAD: {raw}")
        implementation_records.append({**file_record, "git_blob": record["git_blob"]})

    checks = payload.get("checks")
    if not isinstance(checks, Mapping):
        raise ContractError("T2 receipt checks are missing")
    missing = set(contract["required_true_checks"]) - set(checks)
    if missing:
        raise ContractError(f"T2 receipt omits required checks: {sorted(missing)}")
    false_checks = sorted(key for key, value in checks.items() if value is not True)
    if false_checks:
        raise ContractError(f"T2 receipt has non-true checks: {false_checks}")

    method = payload.get("method", {})
    require_equal(method.get("integration_mask"), "exact_class6_roof_TIN_M_j", "T2 mask")
    require_equal(method.get("alpha_threshold"), None, "T2 alpha threshold")
    require_equal(method.get("alpha_read_for_masking"), False, "T2 alpha read")
    require_equal(
        method.get("tsdf_implementation"),
        "Open3D_ScalableTSDFVolume",
        "T2 real TSDF implementation",
    )
    require_equal(
        method.get("marching_cubes"), "Open3D_extract_triangle_mesh", "T2 MC implementation"
    )
    require_equal(
        method.get("mask_application"),
        "outside_exact_M_j_set_to_zero_before_RGBD_integration",
        "T2 mask application",
    )
    integration = payload.get("integration", {})
    require_equal(
        int(integration.get("alpha_threshold_exclusions_total_n", -1)), 0, "T2 alpha exclusions"
    )
    require_equal(
        int(integration.get("outside_M_j_nonzero_after_mask_total_n", -1)),
        0,
        "T2 outside-M_j support",
    )
    exact_inventory = str(integration.get("exact_M_j_inventory_sha256", ""))
    if re.fullmatch(r"[0-9a-f]{64}", exact_inventory) is None:
        raise ContractError("T2 exact-M_j inventory hash is invalid")
    if int(integration.get("nonempty_M_j_views_n", 0)) <= 0:
        raise ContractError("T2 integrated no nonempty M_j views")
    if int(integration.get("integrated_pixels_total_n", 0)) <= 0:
        raise ContractError("T2 integrated no surface pixels")

    inputs = payload.get("inputs")
    if not isinstance(inputs, Mapping):
        raise ContractError("T2 input bindings are missing")
    named_roles = set(contract["required_current_inputs"])
    missing_roles = named_roles - set(inputs)
    if missing_roles:
        raise ContractError(f"T2 current input roles are missing: {sorted(missing_roles)}")
    unexpected_roles = set(inputs) - named_roles - {"consumed_preprocess_artifacts"}
    if unexpected_roles:
        raise ContractError(f"T2 current input roles are unexpected: {sorted(unexpected_roles)}")
    input_records = {
        role: _current_file_record(
            repo, inputs[role], f"T2 input {role}", require_bytes=False
        )
        for role in contract["required_current_inputs"]
    }
    require_equal(input_records["config"]["path"], expected_paths[0], "T2 config identity")
    require_equal(input_records["script"]["path"], expected_paths[1], "T2 script identity")

    t2_config = load_json(resolve_path(repo, input_records["config"]["path"]))
    require_equal(
        t2_config.get("schema"), "jointbuildgs.fusion_w1_aprime.tsdf.config.v1", "T2 config schema"
    )
    require_equal(t2_config.get("implementation_files"), expected_paths, "T2 config implementation list")
    rehearsal = t2_config.get("rehearsal", {})
    for key in ("building_id", "condition", "replicate"):
        require_equal(rehearsal.get(key), contract["identity"][key], f"T2 config rehearsal {key}")
    require_equal(
        rehearsal.get("checkpoint_sha256"),
        input_records["checkpoint"]["sha256"],
        "T2 config checkpoint hash",
    )
    require_equal(
        rehearsal.get("preprocess_manifest_sha256"),
        input_records["preprocess_manifest"]["sha256"],
        "T2 config preprocess hash",
    )

    training_path = resolve_path(repo, input_records["training_config"]["path"])
    with training_path.open("r", encoding="utf-8") as stream:
        training = yaml.safe_load(stream)
    if not isinstance(training, Mapping):
        raise ContractError("T2 bound training config is not a mapping")
    preprocess = load_json(resolve_path(repo, input_records["preprocess_manifest"]["path"]))
    require_equal(
        preprocess.get("building", {}).get("building_id"),
        contract["identity"]["building_id"],
        "T2 preprocess building binding",
    )
    training_data_root = resolve_path(repo, str(training.get("data_root", ""))).resolve()
    preprocess_data_root = resolve_path(repo, str(preprocess.get("data_root", ""))).resolve()
    require_equal(training_data_root, preprocess_data_root, "T2 training/preprocess data root")
    training_out = resolve_path(repo, str(training.get("out_dir", ""))).resolve()
    checkpoint_path = resolve_path(repo, input_records["checkpoint"]["path"]).resolve()
    if checkpoint_path.name != "final.pt" or not _path_is_within(checkpoint_path, training_out / "ckpt"):
        raise ContractError("T2 checkpoint is not the bound training final.pt")
    require_equal(
        int(inputs["checkpoint"].get("completed_steps", -1)),
        int(training.get("max_iter", -2)),
        "T2 checkpoint/training final step",
    )
    train_views = list(training.get("train_views") or [])
    require_equal(
        int(integration.get("training_views_n", -1)), len(train_views), "T2 training view count"
    )
    consumed = inputs.get("consumed_preprocess_artifacts")
    if not isinstance(consumed, list) or not consumed:
        raise ContractError("T2 receipt has no consumed preprocess artifact inventory")
    consumed_records = [
        _current_file_record(
            repo, record, "T2 consumed preprocess artifact", require_bytes=True
        )
        for record in consumed
    ]
    consumed_paths = [record["path"] for record in consumed_records]
    if len(consumed_paths) != len(set(consumed_paths)):
        raise ContractError("T2 consumed preprocess inventory has duplicate paths")
    expected_consumed = {
        relative(repo, preprocess_data_root / "sparse/0/cameras.bin"),
        relative(repo, preprocess_data_root / "sparse/0/images.bin"),
        relative(repo, resolve_path(repo, str(training.get("init_pointcloud", "")))),
        *{
            relative(
                repo,
                preprocess_data_root / "supervision/class6" / f"{image_name}.npz",
            )
            for image_name in train_views
        },
    }
    require_equal(set(consumed_paths), expected_consumed, "T2 consumed preprocess coverage")
    artifact_inventory = preprocess.get("artifact_sha256")
    if not isinstance(artifact_inventory, Mapping):
        raise ContractError("T2 preprocess manifest lacks artifact hashes")
    for record in consumed_records:
        require_equal(
            artifact_inventory.get(record["path"]),
            record["sha256"],
            f"T2 consumed artifact/preprocess manifest binding {record['path']}",
        )

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ContractError("T2 receipt artifact inventory is empty")
    if len({record.get("path") for record in artifacts}) != len(artifacts):
        raise ContractError("T2 artifact inventory has duplicate paths")
    artifact_records = [
        _current_file_record(repo, record, "T2 output artifact", require_bytes=True)
        for record in artifacts
    ]
    software = payload.get("software", {})
    require_equal(
        software.get("container_image_id"),
        "sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396",
        "T2 Docker image",
    )
    return {
        "path": relative(repo, path),
        "sha256": sha256_file(path),
        "schema": str(payload["schema"]),
        "status_field": field,
        "accepted_status": str(payload[field]),
        "identity": dict(payload["identity"]),
        "git_lock": {
            "branch": git_lock["branch"],
            "head": t2_head,
            "implementation_files": implementation_records,
        },
        "checks": dict(checks),
        "input_records": input_records,
        "consumed_preprocess_artifacts": consumed_records,
        "artifact_records": artifact_records,
        "exact_M_j_inventory_sha256": exact_inventory,
        "consumer_validation": "full_current_hash_bytes_and_cross_binding",
    }


def validate_preflight_gates(
    repo: Path, config: Mapping[str, Any], profile: str
) -> dict[str, Any]:
    names = ("five_pin",) if profile == "mini_smoke" else ("five_pin", "T1", "T2", "T3")
    records = {
        name: _validate_preflight_gate(repo, name, config["preflight_gates"][name])
        for name in names
    }
    return {
        "status": "PASSED",
        "profile": profile,
        "required_gates": list(names),
        "records": records,
    }


def verify_docker_image(config: Mapping[str, Any]) -> dict[str, str]:
    launch = config["launch_contract"]
    completed = subprocess.run(
        ["docker", "image", "inspect", launch["docker_image"], "--format", "{{.Id}}"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise ContractError(f"cannot inspect Docker image: {completed.stderr.strip()}")
    observed = completed.stdout.strip()
    require_equal(observed, launch["docker_image_id"], "training Docker image ID")
    return {"image": str(launch["docker_image"]), "image_id": observed}


def prepare_writable_environment(
    repo: Path, config: Mapping[str, Any]
) -> dict[str, Any]:
    root = resolve_path(repo, config["launch_contract"]["writable_environment_root"])
    run_root = resolve_path(repo, config["outputs"]["run_root"])
    if not _path_is_within(root, run_root) or root == run_root:
        raise ContractError("writable environment root must be a strict child of A-prime run")
    if root.is_symlink():
        raise ContractError("writable environment root cannot be a symlink")
    directories = {
        "HOME": root / "home",
        "XDG_CACHE_HOME": root / "xdg_cache",
        "TORCH_EXTENSIONS_DIR": root / "torch_extensions",
    }
    root.mkdir(parents=True, exist_ok=True)
    records: dict[str, dict[str, Any]] = {}
    environment: dict[str, str] = {}
    for name, path in directories.items():
        if path.is_symlink():
            raise ContractError(f"writable environment directory is a symlink: {path}")
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir() or not os.access(path, os.W_OK | os.X_OK):
            raise ContractError(f"writable environment is not usable: {path}")
        environment[name] = container_path(repo, path)
        records[name] = {
            "host_path": relative(repo, path),
            "container_path": environment[name],
            "is_symlink": False,
            "writable": True,
        }
    environment["MAX_JOBS"] = str(config["launch_contract"]["jit_max_jobs"])
    return {
        "root": relative(repo, root),
        "variables": environment,
        "directories": records,
    }


def docker_command(
    *,
    repo: Path,
    config: Mapping[str, Any],
    resolved_config: Path,
    compose_override: Path,
    building_id: str,
    arm: str,
    run: str,
    profile: str,
    gpu: int,
    environment: Mapping[str, str],
) -> list[str]:
    choices = tuple(int(value) for value in config["launch_contract"]["physical_gpu_choices"])
    if gpu not in choices:
        raise ContractError(f"physical GPU must be one of {choices}, got {gpu}")
    job_key = f"{profile}/{building_id}/arm_{arm}/{run}"
    suffix = sha256_bytes(job_key.encode("utf-8"))[:12]
    command = [
        "docker",
        "compose",
        "-f",
        str(repo / "docker-compose.yml"),
        "-f",
        str(compose_override),
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--name",
        f"jointbuildgs-aprime-{suffix}",
        "-e",
        f"NVIDIA_VISIBLE_DEVICES={gpu}",
        "-e",
        f"CUDA_VISIBLE_DEVICES={config['launch_contract']['container_visible_gpu']}",
    ]
    for name, value in sorted(environment.items()):
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", name) is None:
            raise ContractError(f"unsafe container environment name: {name!r}")
        command.extend(("-e", f"{name}={value}"))
    command.extend(
        (
            config["launch_contract"]["docker_service"],
            "python",
            "-m",
            "src.stage2.train",
            "--config",
            container_path(repo, resolved_config),
        )
    )
    return command


def _counter_paths(
    repo: Path, config: Mapping[str, Any], profile: str
) -> tuple[Path, Path]:
    root = _profile_root(repo, config, profile)
    return (
        root / config["outputs"]["runtime_counter"],
        root / config["outputs"]["runtime_counter_lock"],
    )


def _counter_update(
    *,
    repo: Path,
    config: Mapping[str, Any],
    profile: str,
    job_key: str,
    state: str,
    detail: Mapping[str, Any],
) -> dict[str, Any]:
    path, lock_path = _counter_paths(repo, config, profile)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if path.is_file():
            payload = load_json(path)
            require_equal(payload.get("schema"), COUNTER_SCHEMA, "runtime counter schema")
        else:
            payload = {
                "schema": COUNTER_SCHEMA,
                "run_id": config["run_id"],
                "profile": profile,
                "event_sequence": 0,
                "jobs": {},
                "events": [],
            }
        sequence = int(payload.get("event_sequence", 0)) + 1
        event = {
            "sequence": sequence,
            "at": utc_now(),
            "job_key": job_key,
            "state": state,
            "detail": dict(detail),
        }
        payload["event_sequence"] = sequence
        payload["updated_at"] = event["at"]
        payload.setdefault("jobs", {})[job_key] = {
            "state": state,
            "updated_at": event["at"],
            "last_sequence": sequence,
            **dict(detail),
        }
        payload.setdefault("events", []).append(event)
        atomic_json(path, payload)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return {"path": relative(repo, path), "sha256": sha256_file(path), "sequence": sequence}


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def _positive_float(row: Mapping[str, str], key: str) -> bool:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError):
        return False
    return math.isfinite(value) and value > 0.0


def _verify_effective_config(
    effective: Mapping[str, Any], resolved: Mapping[str, Any]
) -> dict[str, Any]:
    exact = {
        "depth_schedule": resolved["depth_schedule"],
        "depth_warmup": resolved["depth_warmup"],
        "depth_ramp_steps": resolved["depth_ramp_steps"],
        "depth_base_weight": resolved["w_depth"],
        "depth_final_weight": resolved["depth_final_weight"],
        "depth_prior_alignment": "alpha_lsq",
        "depth_alignment_detach_scale": True,
        "normal_prior_orientation": "signed",
        "normal_schedule": resolved["normal_schedule"],
        "normal_warmup": resolved["normal_warmup"],
        "normal_ramp_steps": resolved["normal_ramp_steps"],
        "normal_final_weight": resolved["normal_final_weight"],
        "w_nc": resolved["w_nc"],
        "nc_schedule": "ramp",
        "nc_warmup": resolved["nc_warmup"],
        "nc_ramp_steps": resolved["nc_ramp_steps"],
        "w_distort": resolved["w_distort"],
        "distort_normalization": "scene_scale_sq",
        "distort_schedule": "ramp",
        "distort_warmup": resolved["distort_warmup"],
        "distort_ramp_steps": resolved["distort_ramp_steps"],
        "surface_seed_protect": False,
        "legacy_mvs_seed_protect": False,
        "seed_protect": False,
        "seed_lineage_audit": True,
        "mvs_seed_init_opacity": 0.1,
        "seed_protected_lineage": "none",
        "prune_opa": resolved["prune_opa"],
        "grow_grad2d": resolved["grow_grad2d"],
        "refine_start_iter": resolved["refine_start_iter"],
        "refine_stop_iter": resolved["refine_stop_iter"],
        "refine_every": resolved["refine_every"],
        "reset_every": resolved["reset_every"],
        "final_prune_opa": 0.0,
        "elongation_filter": False,
    }
    for key, expected in exact.items():
        require_equal(effective.get(key), expected, f"effective trainer config {key}")
    if float(effective.get("distort_norm_denominator", 0.0)) <= 0.0:
        raise ContractError("effective distortion scene-scale denominator is not positive")
    return {"status": "PASSED", "checked": exact}


def _verify_seed_trajectory(
    path: Path, initialization_path: Path, *, expected_initial_opacity: float
) -> dict[str, Any]:
    initialization = load_json(initialization_path)
    require_equal(
        initialization.get("schema"),
        "jointbuildgs.stage2.seed_initialization_audit.v1",
        "seed initialization schema",
    )
    require_equal(initialization.get("status"), "OBSERVED", "seed initialization status")
    require_equal(initialization.get("iteration"), 0, "seed initialization iteration")
    require_equal(
        initialization.get("observation_phase"),
        "initialization_pre_dynamics",
        "seed initialization phase",
    )
    require_equal(
        initialization.get("strategy_step_post_backward_calls"),
        0,
        "seed initialization strategy calls",
    )
    require_equal(
        initialization.get("optimizer_updates_completed"),
        0,
        "seed initialization optimizer updates",
    )
    require_equal(initialization.get("intervention"), False, "seed initialization intervention")
    require_equal(initialization.get("scientific_verdict"), None, "seed initialization verdict")
    if int(initialization.get("seed_lineage_count", 0)) <= 0:
        raise ContractError("seed initialization audit has no lineage roots")
    if not math.isclose(
        float(initialization.get("requested_opacity", float("nan"))),
        expected_initial_opacity,
        rel_tol=0.0,
        abs_tol=1e-6,
    ) or not math.isclose(
        float(initialization.get("opacity_median", float("nan"))),
        expected_initial_opacity,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise ContractError("observed pre-dynamics seed opacity is not 0.1")

    rows = [row for row in _read_csv_rows(path) if row.get("scope") == "all_seed_lineage"]
    if not rows:
        raise ContractError("seed lineage audit has no all_seed_lineage rows")
    rows.sort(key=lambda row: int(row["iteration"]))
    first = rows[0]
    if int(first["iteration"]) != 0:
        raise ContractError("seed lineage audit omits iteration zero")
    if int(first["seed_lineage_count"]) <= 0:
        raise ContractError("seed lineage audit begins with no seed roots")
    if any(str(row["seed_protect_active"]).lower() not in {"false", "0"} for row in rows):
        raise ContractError("seed protection became active during A-prime observation")
    if any(int(row["cum_prune_seed_protected"]) != 0 for row in rows):
        raise ContractError("a seed lineage was protected from pruning")
    cumulative_pruned = max(int(row["cum_pruned"]) for row in rows)
    return {
        "status": "PASSED",
        "path": str(path),
        "rows_n": len(rows),
        "initial": {
            "iteration": int(initialization["iteration"]),
            "observation_phase": str(initialization["observation_phase"]),
            "seed_lineage_count": int(initialization["seed_lineage_count"]),
            "opacity_median": float(initialization["opacity_median"]),
            "requested_opacity": float(initialization["requested_opacity"]),
        },
        "first_post_dynamics_observation": {
            "iteration": int(first["iteration"]),
            "seed_lineage_count": int(first["seed_lineage_count"]),
            "opacity_median": float(first["opacity_median"]),
        },
        "final_observation": {
            "iteration": int(rows[-1]["iteration"]),
            "seed_lineage_count": int(rows[-1]["seed_lineage_count"]),
            "opacity_median": float(rows[-1]["opacity_median"]),
        },
        "minimum_seed_lineage_count": min(int(row["seed_lineage_count"]) for row in rows),
        "maximum_cumulative_pruned": cumulative_pruned,
        "maximum_cumulative_prune_candidates": max(
            int(row["cum_prune_candidates"]) for row in rows
        ),
        "cumulative_seed_protected": 0,
        "protection_active": False,
    }


def _verify_mini_smoke_terms(
    path: Path, config: Mapping[str, Any]
) -> dict[str, Any]:
    smoke = config["mini_smoke_profile"]
    transition = int(smoke["overrides"]["depth_warmup"])
    rows = _read_csv_rows(path)
    evidence: dict[str, dict[str, Any]] = {}
    for component in smoke["required_post_transition_components"]:
        candidates = [
            row
            for row in rows
            if row.get("component") == component
            and int(row.get("step", -1)) >= transition
            and all(_positive_float(row, field) for field in smoke["required_positive_fields"])
        ]
        if not candidates:
            raise ContractError(
                f"T1 mini smoke has no post-transition positive evidence for {component}"
            )
        row = candidates[-1]
        evidence[component] = {
            "step": int(row["step"]),
            **{field: float(row[field]) for field in smoke["required_positive_fields"]},
        }
    return {
        "status": "PASSED",
        "transition_iteration": transition,
        "required_fields_strictly_positive": list(smoke["required_positive_fields"]),
        "component_evidence": evidence,
    }


def verify_training_completion(
    *,
    repo: Path,
    config: Mapping[str, Any],
    target: Path,
    resolved_path: Path,
    profile: str,
) -> dict[str, Any]:
    maximum = int(_profile_recipe(config, profile)["max_iter"])
    manifest_path = target / "full_state_manifest.json"
    effective_path = target / "effective_config.json"
    final_path = target / "ckpt/final.pt"
    checkpoint = target / "ckpt" / f"step_{maximum:06d}.pt"
    sidecar = Path(f"{checkpoint}.sha256")
    loss_path = target / "audit/loss_grad_norms.csv"
    seed_path = target / "audit/seed_lineage.csv"
    seed_initialization_path = target / "audit/seed_initialization.json"
    for path in (
        manifest_path,
        effective_path,
        final_path,
        checkpoint,
        sidecar,
        loss_path,
        seed_path,
        seed_initialization_path,
    ):
        if not path.is_file() or path.stat().st_size <= 0:
            raise ContractError(f"completed trainer output missing or empty: {path}")
    manifest = load_json(manifest_path)
    require_equal(manifest.get("schema"), "jointbuildgs.stage2.resume_manifest.v1", "full-state schema")
    require_equal(manifest.get("process_completed"), True, "trainer process completion")
    require_equal(int(manifest.get("process_completed_steps", -1)), maximum, "trainer completed steps")
    require_equal(int(manifest.get("last_completed_steps", -1)), maximum, "trainer last step")
    latest = manifest.get("latest_full_checkpoint", {})
    require_equal(int(latest.get("completed_steps", -1)), maximum, "latest checkpoint step")
    require_equal(sha256_file(checkpoint), latest.get("sha256"), "latest checkpoint hash")
    sidecar_match = re.fullmatch(
        rf"([0-9a-f]{{64}})  ({re.escape(checkpoint.name)})\n?",
        sidecar.read_text(encoding="utf-8"),
    )
    if sidecar_match is None:
        raise ContractError(f"invalid checkpoint sidecar: {sidecar}")
    require_equal(sidecar_match.group(1), sha256_file(checkpoint), "checkpoint sidecar hash")
    effective = load_json(effective_path)
    with resolved_path.open("r", encoding="utf-8") as stream:
        resolved = yaml.safe_load(stream)
    effective_evidence = _verify_effective_config(effective, resolved)
    seed_evidence = _verify_seed_trajectory(
        seed_path,
        seed_initialization_path,
        expected_initial_opacity=float(
            config["mini_smoke_profile"]["required_seed_init_opacity"]
        ),
    )
    mini_evidence = None
    if profile == "mini_smoke":
        mini_evidence = _verify_mini_smoke_terms(loss_path, config)
        if seed_evidence["maximum_cumulative_pruned"] < int(
            config["mini_smoke_profile"]["required_cumulative_pruned_min"]
        ):
            raise ContractError("T1 mini smoke did not execute an actual prune")
    return {
        "status": "PASSED",
        "profile": profile,
        "completed_optimizer_updates": maximum,
        "full_state_manifest": {
            "path": relative(repo, manifest_path),
            "sha256": sha256_file(manifest_path),
        },
        "checkpoint": {"path": relative(repo, checkpoint), "sha256": sha256_file(checkpoint)},
        "final_checkpoint": {"path": relative(repo, final_path), "sha256": sha256_file(final_path)},
        "effective_config": {
            "path": relative(repo, effective_path),
            "sha256": sha256_file(effective_path),
            "validation": effective_evidence,
        },
        "loss_grad_audit": {"path": relative(repo, loss_path), "sha256": sha256_file(loss_path)},
        "seed_lineage_audit": {
            **seed_evidence,
            "path": relative(repo, seed_path),
            "sha256": sha256_file(seed_path),
            "initialization_receipt": {
                "path": relative(repo, seed_initialization_path),
                "sha256": sha256_file(seed_initialization_path),
            },
        },
        "mini_smoke_term_evidence": mini_evidence,
    }


def _publish_t1_gate(
    *,
    repo: Path,
    config: Mapping[str, Any],
    completion: Mapping[str, Any],
    completed_receipt_path: Path,
) -> dict[str, Any]:
    contract = config["preflight_gates"]["T1"]
    path = resolve_path(repo, contract["path"])
    if completion.get("profile") != "mini_smoke":
        raise ContractError("T1 gate can only be published from the mini-smoke profile")
    seed = completion["seed_lineage_audit"]
    payload = {
        "schema": T1_SCHEMA,
        "status": "PASSED",
        "created_at": utc_now(),
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "role": "T1_surface_regularization_actual_activation_and_unprotected_prune_evidence",
        "mini_smoke_completed_receipt": {
            "path": relative(repo, completed_receipt_path),
            "sha256": sha256_file(completed_receipt_path),
        },
        "term_evidence": completion["mini_smoke_term_evidence"],
        "seed_lineage_evidence": seed,
        "requirements": {
            "post_transition_term_fields_strictly_positive": True,
            "seed_init_opacity_0_1_observed": True,
            "protection_off_for_all_observations": True,
            "cumulative_seed_protected_zero": True,
            "actual_prune_count_positive": seed["maximum_cumulative_pruned"] > 0,
            "scientific_verdict": None,
        },
    }
    exclusive_json(path, payload)
    return {"path": relative(repo, path), "sha256": sha256_file(path)}


def launch(
    *,
    repo: Path,
    config_path: Path,
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    profile: str,
    gpu: int,
    popen_factory: Callable[..., Any] = subprocess.Popen,
) -> dict[str, Any]:
    if Path("/.dockerenv").is_file():
        raise ContractError("launch is a host-side Docker orchestration command")
    target = job_dir(repo, config, building_id, arm, run, profile)
    outputs = config["outputs"]
    materialization_path, materialization, materialization_sha = _load_materialization(
        repo, config, building_id, arm, run, profile
    )
    check = check_materialization(
        repo=repo,
        config_path=config_path,
        config=config,
        building_id=building_id,
        arm=arm,
        run=run,
        profile=profile,
        roundtrip=False,
    )
    if any(check["runtime_receipts"].values()):
        raise ContractError("job has a prior runtime receipt; refuse duplicate launch")
    preflight = validate_preflight_gates(repo, config, profile)
    if profile == "mini_smoke":
        t1_gate_path = resolve_path(repo, config["preflight_gates"]["T1"]["path"])
        if t1_gate_path.exists():
            raise ContractError("T1 gate receipt already exists; refuse duplicate mini smoke")
    image = verify_docker_image(config)
    writable = prepare_writable_environment(repo, config)
    resolved_path = target / outputs["resolved_config"]
    override_path = target / outputs["compose_override"]
    job_key = f"{profile}/{building_id}/arm_{arm}/{run}"
    command = docker_command(
        repo=repo,
        config=config,
        resolved_config=resolved_path,
        compose_override=override_path,
        building_id=building_id,
        arm=arm,
        run=run,
        profile=profile,
        gpu=gpu,
        environment=writable["variables"],
    )
    lock_path = resolve_path(repo, outputs["run_root"]) / outputs["foreground_lock"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as foreground_lock:
        try:
            fcntl.flock(foreground_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ContractError("another A-prime foreground training job holds the lock") from exc
        started_path = target / outputs["started_receipt"]
        completed_path = target / outputs["completed_receipt"]
        failed_path = target / outputs["failed_receipt"]
        log_path = target / outputs["job_log"]
        started_payload = {
            "schema": STARTED_SCHEMA,
            "status": "STARTED",
            "created_at": utc_now(),
            "run_id": config["run_id"],
            "task_id": config["task_id"],
            "job_key": job_key,
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
            "profile": profile,
            "seed": materialization["seed"],
            "physical_gpu": gpu,
            "container_visible_gpu": config["launch_contract"]["container_visible_gpu"],
            "command": command,
            "foreground_single_job_lock": relative(repo, lock_path),
            "method": materialization["git"],
            "materialization": {
                "path": relative(repo, materialization_path),
                "sha256": materialization_sha,
            },
            "preflight": preflight,
            "docker_image": image,
            "network_mode": "none",
            "writable_environment": writable,
            "claim_mode": "atomic_O_EXCL",
        }
        exclusive_json(started_path, started_payload)
        _counter_update(
            repo=repo,
            config=config,
            profile=profile,
            job_key=job_key,
            state="claimed",
            detail={"physical_gpu": gpu, "started_receipt": relative(repo, started_path)},
        )
        started_monotonic = time.monotonic()
        return_code: int | None = None
        process_id: int | None = None
        terminal_completed = False
        try:
            with log_path.open("x", encoding="utf-8", buffering=1) as log:
                process = popen_factory(
                    command,
                    cwd=repo,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                process_id = int(process.pid)
                _counter_update(
                    repo=repo,
                    config=config,
                    profile=profile,
                    job_key=job_key,
                    state="docker_started",
                    detail={"docker_compose_pid": process_id},
                )
                return_code = int(process.wait())
            if return_code != 0:
                raise ContractError(f"Docker training exited with code {return_code}")
            completion = verify_training_completion(
                repo=repo,
                config=config,
                target=target,
                resolved_path=resolved_path,
                profile=profile,
            )
            elapsed = time.monotonic() - started_monotonic
            completed_payload = {
                "schema": COMPLETED_SCHEMA,
                "status": "COMPLETED",
                "created_at": utc_now(),
                "run_id": config["run_id"],
                "task_id": config["task_id"],
                "job_key": job_key,
                "building_id": building_id,
                "arm": arm,
                "replicate": run,
                "profile": profile,
                "seed": materialization["seed"],
                "return_code": return_code,
                "elapsed_seconds": elapsed,
                "docker_compose_pid": process_id,
                "started_receipt": {
                    "path": relative(repo, started_path),
                    "sha256": sha256_file(started_path),
                },
                "materialization": {
                    "path": relative(repo, materialization_path),
                    "sha256": materialization_sha,
                },
                "training_completion": completion,
                "log": {"path": relative(repo, log_path), "sha256": sha256_file(log_path)},
                "scientific_verdict": None,
            }
            exclusive_json(completed_path, completed_payload)
            terminal_completed = True
            t1_gate = None
            if profile == "mini_smoke":
                t1_gate = _publish_t1_gate(
                    repo=repo,
                    config=config,
                    completion=completion,
                    completed_receipt_path=completed_path,
                )
                completed_payload["T1_gate"] = t1_gate
            _counter_update(
                repo=repo,
                config=config,
                profile=profile,
                job_key=job_key,
                state="completed",
                detail={
                    "elapsed_seconds": elapsed,
                    "completed_receipt": relative(repo, completed_path),
                    "T1_gate": t1_gate,
                },
            )
            return completed_payload
        except BaseException as exc:
            elapsed = time.monotonic() - started_monotonic
            if terminal_completed:
                _counter_update(
                    repo=repo,
                    config=config,
                    profile=profile,
                    job_key=job_key,
                    state="completed_with_postpublication_error",
                    detail={"elapsed_seconds": elapsed, "reason": str(exc)},
                )
                raise
            failed_payload = {
                "schema": FAILED_SCHEMA,
                "status": "FAILED",
                "created_at": utc_now(),
                "run_id": config["run_id"],
                "task_id": config["task_id"],
                "job_key": job_key,
                "building_id": building_id,
                "arm": arm,
                "replicate": run,
                "profile": profile,
                "return_code": return_code,
                "elapsed_seconds": elapsed,
                "docker_compose_pid": process_id,
                "error_type": type(exc).__name__,
                "reason": str(exc),
                "started_receipt": {
                    "path": relative(repo, started_path),
                    "sha256": sha256_file(started_path),
                },
                "log": (
                    {"path": relative(repo, log_path), "sha256": sha256_file(log_path)}
                    if log_path.is_file()
                    else None
                ),
                "partial_outputs_preserved": True,
            }
            if not failed_path.exists():
                exclusive_json(failed_path, failed_payload)
            _counter_update(
                repo=repo,
                config=config,
                profile=profile,
                job_key=job_key,
                state="failed",
                detail={"elapsed_seconds": elapsed, "reason": str(exc)},
            )
            raise
        finally:
            fcntl.flock(foreground_lock.fileno(), fcntl.LOCK_UN)


def build_queue_rows(
    targets: Sequence[Mapping[str, str]], config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    ordered = sorted(targets, key=lambda row: int(row["aprime_order"]))
    rows: list[dict[str, Any]] = []

    def append(building: Mapping[str, str], arm: str, run: str) -> None:
        rows.append(
            {
                "queue_order": len(rows) + 1,
                "building_id": building["building_id"],
                "aprime_order": int(building["aprime_order"]),
                "target_role": building["target_role"],
                "arm": arm,
                "replicate": run,
                "seed": int(config["recipe"]["run_seeds"][run]),
                "profile": "full",
            }
        )

    for building in ordered:
        append(building, "Aprime", "r1")
    for building in ordered:
        append(building, "Aprime", "r2")
    dim_failures = [row for row in ordered if row["target_role"] == "dim_failure"]
    textured = [row for row in ordered if row["target_role"] == "textured_control"]
    if len(dim_failures) != 8 or len(textured) != 1:
        raise ContractError("locked B subset requires eight dim failures and one textured control")
    for building in (*dim_failures[:2], textured[0]):
        append(building, "B", "r1")
    require_equal(len(rows), int(config["queue_contract"]["expected_jobs"]), "queue length")
    require_equal([row["queue_order"] for row in rows], list(range(1, 22)), "queue order")
    return rows


def publish_queue_plan(
    *, repo: Path, config_path: Path, config: Mapping[str, Any]
) -> dict[str, Any]:
    method = committed_method_gate(repo, config)
    locked = validate_locked_inputs(repo, config)
    targets = read_targets(repo, config)
    rows = build_queue_rows(targets, config)
    csv_path = resolve_path(repo, config["outputs"]["queue_plan_csv"])
    json_path = resolve_path(repo, config["outputs"]["queue_plan_json"])
    csv_fields = (
        "queue_order",
        "building_id",
        "aprime_order",
        "target_role",
        "arm",
        "replicate",
        "seed",
        "profile",
    )
    if csv_path.exists() or json_path.exists():
        if not (csv_path.is_file() and json_path.is_file()):
            raise ContractError("queue publication is partial")
        existing = load_json(json_path)
        require_equal(existing.get("schema"), QUEUE_SCHEMA, "queue schema")
        require_equal(existing.get("rows"), rows, "immutable queue rows")
        require_equal(existing.get("queue_csv_sha256"), sha256_file(csv_path), "queue CSV hash")
        require_equal(existing.get("method"), method, "immutable queue method snapshot")
        return {**existing, "publication_reused": True}
    atomic_csv(csv_path, rows, csv_fields)
    payload = {
        "schema": QUEUE_SCHEMA,
        "status": "PLANNED",
        "created_at": utc_now(),
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "driver_config": relative(repo, config_path),
        "driver_config_sha256": sha256_file(config_path),
        "method": method,
        "locked_inputs": locked,
        "queue_contract": dict(config["queue_contract"]),
        "rows": rows,
        "jobs_n": len(rows),
        "queue_csv": relative(repo, csv_path),
        "queue_csv_sha256": sha256_file(csv_path),
        "actual_training_started": False,
    }
    atomic_json(json_path, payload)
    return payload


def queue_next(
    *, repo: Path, config: Mapping[str, Any]
) -> dict[str, Any]:
    path = resolve_path(repo, config["outputs"]["queue_plan_json"])
    plan = load_json(path)
    require_equal(plan.get("schema"), QUEUE_SCHEMA, "queue plan schema")
    method = committed_method_gate(repo, config, expected_head=plan["method"]["head"])
    require_equal(method, plan["method"], "queue method snapshot")
    expected = build_queue_rows(read_targets(repo, config), config)
    require_equal(plan.get("rows"), expected, "queue rows since publication")
    states: list[dict[str, Any]] = []
    next_row = None
    for row in expected:
        target = job_dir(
            repo,
            config,
            row["building_id"],
            row["arm"],
            row["replicate"],
            "full",
        )
        completed = target / config["outputs"]["completed_receipt"]
        failed = target / config["outputs"]["failed_receipt"]
        started = target / config["outputs"]["started_receipt"]
        materialized = target / config["outputs"]["materialization_manifest"]
        if completed.is_file():
            state = "COMPLETED"
        elif failed.is_file():
            state = "FAILED_REVIEW_REQUIRED"
        elif started.is_file():
            state = "STARTED_WITHOUT_TERMINAL_RECEIPT"
        elif materialized.is_file():
            state = "READY_TO_LAUNCH"
        else:
            state = "NEEDS_MATERIALIZATION"
        record = {**row, "state": state, "job_dir": relative(repo, target)}
        states.append(record)
        if next_row is None and state != "COMPLETED":
            next_row = record
    command = None
    if next_row is not None and next_row["state"] in {"NEEDS_MATERIALIZATION", "READY_TO_LAUNCH"}:
        action = "materialize" if next_row["state"] == "NEEDS_MATERIALIZATION" else "launch"
        command = [
            "phases/p2-gsjso/scripts/run_fusion_w1_aprime_training_20260726.sh",
            action,
            "--building-id",
            next_row["building_id"],
            "--arm",
            next_row["arm"],
            "--run",
            next_row["replicate"],
            "--profile",
            "full",
        ]
        if action == "launch":
            command.extend(("--gpu", "<0-or-1>"))
    return {
        "status": "QUEUE_COMPLETE" if next_row is None else "PENDING",
        "completed_n": sum(record["state"] == "COMPLETED" for record in states),
        "jobs_n": len(states),
        "next": next_row,
        "next_command": command,
        "states": states,
        "automatic_training_started": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("materialize", "check"):
        sub = commands.add_parser(name)
        sub.add_argument("--building-id", required=True)
        sub.add_argument("--arm", choices=ARMS, required=True)
        sub.add_argument("--run", choices=RUNS, required=True)
        sub.add_argument("--profile", choices=PROFILES, default="full")
    launch_parser = commands.add_parser("launch")
    launch_parser.add_argument("--building-id", required=True)
    launch_parser.add_argument("--arm", choices=ARMS, required=True)
    launch_parser.add_argument("--run", choices=RUNS, required=True)
    launch_parser.add_argument("--profile", choices=PROFILES, default="full")
    launch_parser.add_argument("--gpu", type=int, choices=(0, 1), required=True)
    commands.add_parser("queue-plan")
    commands.add_parser("queue-next")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = resolve_path(REPO, args.config)
    config = load_config(config_path)
    if args.command == "materialize":
        result = materialize(
            repo=REPO,
            config_path=config_path,
            config=config,
            building_id=args.building_id,
            arm=args.arm,
            run=args.run,
            profile=args.profile,
        )
    elif args.command == "check":
        result = check_materialization(
            repo=REPO,
            config_path=config_path,
            config=config,
            building_id=args.building_id,
            arm=args.arm,
            run=args.run,
            profile=args.profile,
            roundtrip=True,
        )
    elif args.command == "launch":
        result = launch(
            repo=REPO,
            config_path=config_path,
            config=config,
            building_id=args.building_id,
            arm=args.arm,
            run=args.run,
            profile=args.profile,
            gpu=args.gpu,
        )
    elif args.command == "queue-plan":
        result = publish_queue_plan(repo=REPO, config_path=config_path, config=config)
    elif args.command == "queue-next":
        result = queue_next(repo=REPO, config=config)
    else:  # pragma: no cover
        raise AssertionError(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        print(f"FUS-W1 A-prime training contract error: {exc}", file=sys.stderr)
        raise SystemExit(2)

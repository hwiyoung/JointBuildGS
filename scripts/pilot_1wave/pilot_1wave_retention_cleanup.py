#!/usr/bin/env python3
"""Compact the completed P1W run while preserving the no-retrain recovery path.

The script is intentionally run-specific and fail-closed.  It keeps the ten
20k full-state checkpoints and ten successful geometry NPZ files, publishes a
small prediction/receipt pack, and removes only the enumerated regenerable
payloads.  Dry-run is the default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[2]
SOURCE_RUN = REPO / "phases/p2-gsjso/runs/pilot_1wave/20260721_pilot_1wave"
READOUT = REPO / "phases/p2-gsjso/runs/pilot_1wave/20260722_pilot_1wave_readout"
PACK = READOUT / "prediction_pack"
RETENTION_DIR = READOUT / "retention"
PLAN_PATH = RETENTION_DIR / "retention_plan.json"
RECEIPT_PATH = RETENTION_DIR / "retention_receipt.json"
RUNS = tuple(
    (condition, seed)
    for condition in ("01", "02", "03", "04a", "04b")
    for seed in (1001, 1002)
)
INTERMEDIATE_STEPS = ("005000", "010000", "015000")
ROOT_ONLY_DELETIONS = (
    REPO / "phases/p2-gsjso/scripts/.p1w_score_n8l4rqx4",
    SOURCE_RUN
    / "prep_artifacts/plane_masks_04a_vs_04b_qa_attempt1_root700",
)
UPSTREAM_INPUTS = (
    REPO / "results/tum_transfer/mob_analysis/seed/seed_dense.ply",
    REPO / "results/tum_transfer/data_geoidfix/images",
    REPO / "results/tum_transfer/data_geoidfix/stereo/depth_maps",
    REPO / "results/tum_transfer/data_geoidfix/stereo/normal_maps",
    REPO / "results/tum_transfer/data_geoidfix/sparse/0/cameras.bin",
    REPO / "results/tum_transfer/data_geoidfix/sparse/0/images.bin",
    REPO / "results/tum_transfer/data_geoidfix/sparse/0/points3D.bin",
    REPO
    / (
        "results/tum_transfer/e5_s1_full_factor/C001/torch_hub/hub/"
        "checkpoints/omnidata_normal_dpt_hybrid.pth"
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--prepare",
        action="store_true",
        help="publish the compact pack and immutable deletion plan without deleting",
    )
    modes.add_argument(
        "--delete",
        action="store_true",
        help="apply an existing plan; intended for the pinned container as root",
    )
    modes.add_argument(
        "--finalize",
        action="store_true",
        help="verify all planned deletions, including root-only paths, and seal receipt",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    resolved = path.resolve(strict=False)
    try:
        return str(resolved.relative_to(REPO.resolve()))
    except ValueError as exc:
        raise RuntimeError(f"path escapes repository: {path}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def git(*args: str) -> str:
    return subprocess.check_output(
        ("git", *args), cwd=REPO, text=True, stderr=subprocess.STDOUT
    ).strip()


def ensure_clean_tracked_tree() -> None:
    changed = [
        line
        for line in git("status", "--short", "--untracked-files=no").splitlines()
        if line and not line.endswith(" .gitignore")
    ]
    if changed:
        raise RuntimeError(
            "unexpected tracked changes before cleanup:\n" + "\n".join(changed)
        )


def ensure_untracked_target(path: Path) -> None:
    output = git("ls-files", "--", rel(path))
    if output:
        raise RuntimeError(
            f"refusing to remove tracked content under {rel(path)}:\n{output}"
        )


def tree_stats(path: Path) -> dict[str, int]:
    if not path.exists() and not path.is_symlink():
        return {"bytes": 0, "files": 0, "dirs": 0}
    if path.is_symlink():
        return {"bytes": int(path.lstat().st_size), "files": 1, "dirs": 0}
    if path.is_file():
        return {"bytes": int(path.stat().st_size), "files": 1, "dirs": 0}
    total_bytes = 0
    files = 0
    dirs = 1
    for root, dirnames, filenames in os.walk(path):
        dirs += len(dirnames)
        for filename in filenames:
            item = Path(root) / filename
            if item.is_symlink():
                total_bytes += item.lstat().st_size
            else:
                total_bytes += item.stat().st_size
            files += 1
    return {"bytes": int(total_bytes), "files": files, "dirs": dirs}


def source_run_stats() -> dict[str, int]:
    return tree_stats(SOURCE_RUN)


def file_record(path: Path, *, include_sha: bool = True) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    record: dict[str, Any] = {
        "path": rel(path),
        "bytes": int(path.stat().st_size),
    }
    if include_sha:
        record["sha256"] = sha256_file(path)
    return record


def copy_immutable(source: Path, destination: Path) -> dict[str, Any]:
    source_record = file_record(source)
    if destination.exists():
        if not destination.is_file():
            raise RuntimeError(f"pack destination is not a file: {destination}")
        if sha256_file(destination) != source_record["sha256"]:
            raise RuntimeError(f"refusing to overwrite differing pack file: {destination}")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    packed_record = file_record(destination)
    if packed_record["sha256"] != source_record["sha256"]:
        raise RuntimeError(f"copy SHA mismatch: {source} -> {destination}")
    return {"source": source_record, "packed": packed_record}


def copy_failure_jsons(
    source_root: Path, destination_root: Path
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not source_root.is_dir():
        return records
    for source in sorted(source_root.rglob("*.json")):
        if source.stat().st_size > 256 * 1024:
            continue
        destination = destination_root / source.relative_to(source_root)
        records.append(copy_immutable(source, destination))
    return records


def verify_upstreams() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in UPSTREAM_INPUTS:
        if not path.exists():
            raise FileNotFoundError(f"upstream rematerialization input missing: {path}")
        stats = tree_stats(path)
        records.append({"path": rel(path), **stats})
    return records


def verify_checkpoint(condition: str, seed: int) -> dict[str, Any]:
    run_root = SOURCE_RUN / f"training/runs/{condition}/seed_{seed}"
    manifest_path = run_root / "full_state_manifest.json"
    checkpoint_path = run_root / "ckpt/step_020000.pt"
    sidecar_path = checkpoint_path.with_suffix(".pt.sha256")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    latest = payload.get("latest_full_checkpoint") or {}
    if payload.get("process_completed") is not True:
        raise RuntimeError(f"incomplete run manifest: {manifest_path}")
    if int(latest.get("completed_steps", -1)) != 20000:
        raise RuntimeError(f"non-20k latest checkpoint: {manifest_path}")
    expected_sha = str(latest.get("sha256", ""))
    actual_sha = sha256_file(checkpoint_path)
    if actual_sha != expected_sha:
        raise RuntimeError(f"checkpoint SHA mismatch: {checkpoint_path}")
    sidecar_sha = sidecar_path.read_text(encoding="utf-8").strip().split()[0]
    if sidecar_sha != actual_sha:
        raise RuntimeError(f"checkpoint sidecar mismatch: {sidecar_path}")
    return {
        "condition_id": condition,
        "seed": seed,
        "checkpoint": file_record(checkpoint_path, include_sha=False)
        | {"sha256": actual_sha},
        "checkpoint_sidecar": file_record(sidecar_path),
        "full_state_manifest": file_record(manifest_path),
    }


def verify_geometry_npz(condition: str, seed: int) -> dict[str, Any]:
    root = SOURCE_RUN / (
        f"training/postprocess/attempts/{condition}_seed{seed}/extract/attempt_001"
    )
    npz_path = root / "scene_geometry.npz"
    provenance_path = root / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    expected_sha = str((provenance.get("output_npz") or {}).get("sha256", ""))
    actual_sha = sha256_file(npz_path)
    if actual_sha != expected_sha:
        raise RuntimeError(f"geometry NPZ SHA mismatch: {npz_path}")
    return {
        "condition_id": condition,
        "seed": seed,
        "geometry_npz": file_record(npz_path, include_sha=False)
        | {"sha256": actual_sha},
        "provenance": file_record(provenance_path),
    }


def build_pack() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    records.append(
        copy_immutable(
            SOURCE_RUN / "training/pilot_1wave_driver_manifest.json",
            PACK / "training_driver_manifest.json",
        )
    )
    records.append(
        copy_immutable(
            SOURCE_RUN / "training/postprocess/roofprint_binding_receipt.json",
            PACK / "roofprint_binding_receipt.json",
        )
    )
    for condition, seed in RUNS:
        label = f"{condition}_seed{seed}"
        training_root = SOURCE_RUN / f"training/runs/{condition}/seed_{seed}"
        post_root = SOURCE_RUN / f"training/postprocess/attempts/{label}"
        pairs = (
            (
                training_root / "full_state_manifest.json",
                PACK / label / "full_state_manifest.json",
            ),
            (
                training_root / "renders/it020000_v2_rgb.png",
                PACK / label / "final_preview_v2.png",
            ),
            (
                post_root / "extract/attempt_001/provenance.json",
                PACK / label / "extract_provenance.json",
            ),
            (
                post_root / "extract/attempt_001/metrics.json",
                PACK / label / "extract_metrics.json",
            ),
            (
                post_root / "extract/attempt_001/coverage.csv",
                PACK / label / "extract_coverage.csv",
            ),
            (
                post_root / "classify/attempt_001/classification_receipt.json",
                PACK / label / "classification_receipt.json",
            ),
            (
                post_root
                / "prepare/attempt_001/runtime/roofer_execution_receipt.json",
                PACK / label / "roofer_execution_receipt.json",
            ),
            (
                post_root / "prepare/attempt_001/runtime/roofer_invocation.json",
                PACK / label / "roofer_invocation.json",
            ),
            (
                post_root / "prepare/attempt_001/runtime/assembled.city.json",
                PACK / label / "assembled.city.json",
            ),
        )
        for source, destination in pairs:
            records.append(copy_immutable(source, destination))
    records.extend(
        copy_failure_jsons(
            SOURCE_RUN / "training/failed_attempts",
            PACK / "failure_receipts/training",
        )
    )
    for attempt in (
        "attempt1_ce2fdab_gpu_device_overlap",
        "attempt2_160f1af_extract_oom",
        "attempt3_1dfdcb5_classify_validator_schema",
    ):
        records.extend(
            copy_failure_jsons(
                SOURCE_RUN / f"training/postprocess_failed_attempts/{attempt}",
                PACK / f"failure_receipts/postprocess/{attempt}",
            )
        )
    return records


def deletion_targets() -> list[tuple[Path, str, str]]:
    targets: list[tuple[Path, str, str]] = []

    def add(path: Path, category: str, recovery: str) -> None:
        targets.append((path, category, recovery))

    for path in (
        SOURCE_RUN / "prep_artifacts/data/images",
        SOURCE_RUN / "prep_artifacts/data/stereo",
        SOURCE_RUN / "prep_artifacts/mono_normal_omnidata_world_npy",
        SOURCE_RUN / "prep_artifacts/seeds",
    ):
        add(
            path,
            "materialized_training_input",
            "rerun pinned pilot_1wave_prepare/omnidata preparation from verified upstreams",
        )
    for name in (
        "plane_masks_04a_vs_04b_qa_attempt2_pre_code_commit",
        "plane_masks_04b_attempt1_pre_small_core",
    ):
        add(
            SOURCE_RUN / f"prep_artifacts/{name}",
            "superseded_mask_attempt",
            "canonical tracked plane mask and QA outputs are retained",
        )
    add(
        SOURCE_RUN / "training/failed_attempts",
        "failed_training_runtime",
        "compact JSON failure receipts are copied into the prediction pack",
    )
    for name in (
        "attempt1_ce2fdab_gpu_device_overlap",
        "attempt2_160f1af_extract_oom",
        "attempt3_1dfdcb5_classify_validator_schema",
    ):
        add(
            SOURCE_RUN / f"training/postprocess_failed_attempts/{name}",
            "failed_postprocess_runtime",
            "compact JSON failure receipts are copied into the prediction pack",
        )
    for condition, seed in RUNS:
        run_root = SOURCE_RUN / f"training/runs/{condition}/seed_{seed}"
        for step in INTERMEDIATE_STEPS:
            checkpoint = run_root / f"ckpt/step_{step}.pt"
            add(
                checkpoint,
                "intermediate_checkpoint",
                "final 20k full-state checkpoint and SHA sidecar are retained",
            )
            add(
                checkpoint.with_suffix(".pt.sha256"),
                "intermediate_checkpoint_sidecar",
                "corresponding intermediate checkpoint is intentionally removed",
            )
        add(
            run_root / "ckpt/final.pt",
            "unreferenced_model_only_checkpoint",
            "canonical lineage uses retained step_020000.pt full-state checkpoint",
        )
        add(
            run_root / "renders",
            "training_renders",
            "one final v2 preview per run is copied into the prediction pack",
        )
        add(
            run_root / "tb",
            "tensorboard_runtime",
            "published loss CSV and compact receipts are retained",
        )
        classify = SOURCE_RUN / (
            f"training/postprocess/attempts/{condition}_seed{seed}/"
            "classify/attempt_001"
        )
        add(
            classify / "scene_raw.las",
            "regenerable_raw_las",
            "regenerate from retained scene_geometry.npz with classifier",
        )
        add(
            classify / "scene_classified.las",
            "regenerable_classified_las",
            "regenerate from retained scene_geometry.npz with classifier",
        )
    return targets


def build_plan() -> dict[str, Any]:
    ensure_clean_tracked_tree()
    upstreams = verify_upstreams()
    checkpoints = [verify_checkpoint(*run) for run in RUNS]
    geometry = [verify_geometry_npz(*run) for run in RUNS]
    deletions: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for path, category, recovery in deletion_targets():
        resolved = path.resolve(strict=False)
        if resolved in seen:
            raise RuntimeError(f"duplicate deletion target: {path}")
        seen.add(resolved)
        ensure_untracked_target(path)
        deletions.append(
            {
                "path": rel(path),
                "category": category,
                "recovery": recovery,
                **tree_stats(path),
            }
        )
    root_only = [
        {
            "path": rel(path),
            "category": "root_owned_stale_runtime",
            "recovery": "none; superseded or empty scratch directory",
        }
        for path in ROOT_ONLY_DELETIONS
    ]
    return {
        "schema": "jointbuildgs.pilot_1wave.retention_plan.v1",
        "created_utc": utc_now(),
        "git_head": git("rev-parse", "HEAD"),
        "source_run": rel(SOURCE_RUN),
        "source_run_pre": source_run_stats(),
        "policy": {
            "tier": "postprocess_recovery_without_retraining",
            "keep_20k_full_state_checkpoints": 10,
            "keep_geometry_npz_cache": 10,
            "keep_final_readout_and_report": True,
            "keep_materialized_training_inputs": False,
            "training_resume_after_compaction": (
                "requires rematerializing locked inputs; 20k checkpoint migration "
                "is a separate task"
            ),
            "strict_existing_path_validators": (
                "may fail for intentionally removed LAS/materialized paths; use this "
                "receipt and regenerate from retained NPZ/upstreams first"
            ),
        },
        "verified_upstream_rematerialization_inputs": upstreams,
        "retained_checkpoints": checkpoints,
        "retained_geometry_npz": geometry,
        "deletions": deletions,
        "root_only_deletions": root_only,
    }


def remove_path(path: Path) -> None:
    rel(path)
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def prepare_cleanup() -> None:
    if PLAN_PATH.exists() or RECEIPT_PATH.exists():
        raise RuntimeError(
            "retention plan/receipt already exists; refuse a second destructive apply"
        )
    plan = build_plan()
    pack_records = build_pack()
    pack_manifest = {
        "schema": "jointbuildgs.pilot_1wave.prediction_pack.v1",
        "created_utc": utc_now(),
        "source_run": rel(SOURCE_RUN),
        "purpose": (
            "compact immutable evidence for independent re-score, qualitative review, "
            "lineage review, and failure audit"
        ),
        "files": pack_records,
    }
    canonical_write(PACK / "prediction_pack_manifest.json", pack_manifest)
    plan["prediction_pack_manifest"] = file_record(
        PACK / "prediction_pack_manifest.json"
    )
    canonical_write(PLAN_PATH, plan)
    print(
        json.dumps(
            {
                "state": "prepared",
                "plan": rel(PLAN_PATH),
                "delete_next": [rel(path) for path, _, _ in deletion_targets()]
                + [rel(path) for path in ROOT_ONLY_DELETIONS],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def apply_prepared_plan() -> None:
    if not PLAN_PATH.is_file():
        raise FileNotFoundError(PLAN_PATH)
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    planned = {str(record["path"]) for record in plan["deletions"]}
    expected = {rel(path) for path, _, _ in deletion_targets()}
    if planned != expected:
        raise RuntimeError("retention plan deletion set differs from script allowlist")
    planned_root = {str(record["path"]) for record in plan["root_only_deletions"]}
    expected_root = {rel(path) for path in ROOT_ONLY_DELETIONS}
    if planned_root != expected_root:
        raise RuntimeError("retention plan root-only set differs from script allowlist")
    for path, _, _ in deletion_targets():
        remove_path(path)
    for path in ROOT_ONLY_DELETIONS:
        remove_path(path)
    print(
        json.dumps(
            {
                "state": "deletion_complete",
                "deleted_allowlist_count": len(expected) + len(expected_root),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def verify_retained(plan: dict[str, Any]) -> dict[str, Any]:
    checkpoint_records = [verify_checkpoint(*run) for run in RUNS]
    geometry_records = [verify_geometry_npz(*run) for run in RUNS]
    sparse = SOURCE_RUN / "prep_artifacts/data/sparse/0"
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        if not (sparse / name).is_file():
            raise FileNotFoundError(f"retained readout sparse input missing: {sparse/name}")
    for record in plan["deletions"]:
        path = REPO / record["path"]
        if path.exists() or path.is_symlink():
            raise RuntimeError(f"planned deletion still exists: {record['path']}")
    for record in plan["root_only_deletions"]:
        path = REPO / record["path"]
        if path.exists() or path.is_symlink():
            raise RuntimeError(f"root-only deletion still exists: {record['path']}")
    pack_manifest = PACK / "prediction_pack_manifest.json"
    payload = json.loads(pack_manifest.read_text(encoding="utf-8"))
    for pair in payload["files"]:
        packed = REPO / pair["packed"]["path"]
        if sha256_file(packed) != pair["packed"]["sha256"]:
            raise RuntimeError(f"prediction pack SHA mismatch: {packed}")
    return {
        "checkpoints": checkpoint_records,
        "geometry_npz": geometry_records,
        "readout_sparse": [
            file_record(sparse / name) for name in ("cameras.bin", "images.bin", "points3D.bin")
        ],
        "prediction_pack_manifest": file_record(pack_manifest),
    }


def finalize_cleanup() -> None:
    if not PLAN_PATH.is_file():
        raise FileNotFoundError(PLAN_PATH)
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    retained = verify_retained(plan)
    pre = plan["source_run_pre"]
    post = source_run_stats()
    removed_bytes = int(pre["bytes"]) - int(post["bytes"])
    if removed_bytes <= 0:
        raise RuntimeError("cleanup did not reduce the source run")
    receipt = {
        "schema": "jointbuildgs.pilot_1wave.retention_receipt.v1",
        "sealed_utc": utc_now(),
        "git_head_before_cleanup_commit": git("rev-parse", "HEAD"),
        "state": "complete",
        "source_run_pre": pre,
        "source_run_post": post,
        "removed_bytes": removed_bytes,
        "removed_gib": removed_bytes / (1024**3),
        "retained_bytes": int(post["bytes"]),
        "retained_gib": int(post["bytes"]) / (1024**3),
        "plan": file_record(PLAN_PATH),
        "retained_verification": retained,
        "root_only_deletions_complete": True,
        "unrelated_untracked_files_touched": False,
    }
    canonical_write(RECEIPT_PATH, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


def main() -> None:
    args = parse_args()
    if args.prepare:
        prepare_cleanup()
        return
    if args.delete:
        apply_prepared_plan()
        return
    if args.finalize:
        finalize_cleanup()
        return
    plan = build_plan()
    print(
        json.dumps(
            {
                "state": "dry_run",
                "source_run_pre": plan["source_run_pre"],
                "planned_deletions": len(plan["deletions"]),
                "planned_delete_bytes": sum(
                    int(record["bytes"]) for record in plan["deletions"]
                ),
                "planned_delete_gib": sum(
                    int(record["bytes"]) for record in plan["deletions"]
                )
                / (1024**3),
                "root_only_deletions": plan["root_only_deletions"],
                "retained_checkpoint_bytes": sum(
                    int(record["checkpoint"]["bytes"])
                    for record in plan["retained_checkpoints"]
                ),
                "retained_geometry_npz_bytes": sum(
                    int(record["geometry_npz"]["bytes"])
                    for record in plan["retained_geometry_npz"]
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

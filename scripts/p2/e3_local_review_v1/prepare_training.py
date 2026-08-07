#!/usr/bin/env python3
"""Materialize the reviewed 4906982 crop for a sparse-seeded E3 run.

This is a thin connector around the existing ``materialize_scene_crop`` and
E1-E6 common gsplat config. It does not implement another cropper or trainer.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

import yaml

from src.stage2.colmap_io import read_images_bin, read_points3d_bin
from src.stage2.pilot_scene_prep import (
    WORLD_SHIFT,
    ViewCrop,
    materialize_scene_crop,
    preflight_view_sources,
    write_points3d_bin,
)


SCHEMA = "jointbuildgs.p2.e3_local_4906982.training_prep.v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--max-iter", type=int, required=True)
    parser.add_argument("--w-distort", type=float, required=True)
    parser.add_argument("--reset-every", type=int, required=True)
    args = parser.parse_args()
    if not Path("/.dockerenv").exists():
        raise RuntimeError("training prep must run in the pinned Docker image")

    repo = args.repo_root.resolve()
    artifacts = args.artifact_root.resolve()
    source_root = artifacts / "phase-payloads/p0-audit/data/work/mvs/colmap_dense"
    review_root = artifacts / (
        "phase-payloads/p2/e3_local_review_v1/"
        "P2-E3-LOCAL-4906982-INPUT-REVIEW-v3"
    )
    task_root = artifacts / "phase-payloads/p2/e3_local_4906982_v1" / args.task_name
    receipt_path = task_root / "control/prep_receipt.json"
    source_csv = review_root / "view_candidates.csv"
    common_config_path = repo / "configs/p2/e1_e6_techdev_v1/common_gs.yaml"
    source_identity = {
        "view_candidates_csv": sha256(source_csv),
        "common_gs_config": sha256(common_config_path),
        "source_cameras": sha256(source_root / "sparse/cameras.bin"),
        "source_images": sha256(source_root / "sparse/images.bin"),
        "source_points3D": sha256(source_root / "sparse/points3D.bin"),
        "source_commit": args.source_commit,
    }
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("schema") == SCHEMA and receipt.get("source_identity") == source_identity:
            print(json.dumps({"status": "reused", **receipt["summary"]}, ensure_ascii=False))
            return 0
    if task_root.exists():
        raise RuntimeError(f"nonmatching training-prep output already exists: {task_root}")

    rows = list(csv.DictReader(source_csv.open(encoding="utf-8")))
    source_images = read_images_bin(source_root / "sparse/images.bin")
    images_by_name = {image.name: image for image in source_images.values()}
    plans = []
    train_views, eval_views = [], []
    for row in rows:
        name = row["view_name"]
        image = images_by_name[name]
        plans.append(
            ViewCrop(
                image_id=int(image.id),
                name=name,
                source_camera_id=int(image.camera_id),
                crop=tuple(map(int, ast.literal_eval(row["crop_xyxy"]))),
                visible_building_count=1,
            )
        )
        (train_views if row["local_role"] == "LOCAL_TRAIN" else eval_views).append(name)
    if len(plans) != 55 or len(train_views) != 47 or len(eval_views) != 8:
        raise RuntimeError("reviewed v3 55/47/8 membership drifted")

    preflight = preflight_view_sources(source_root, plans)
    staging = task_root.with_name(task_root.name + f".staging.{os.getpid()}")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    building_row = next(
        json.loads(line)
        for line in (
            artifacts
            / "phase-payloads/p2/qualitative_199_common_manifest_v1/"
            "P2-QUALITATIVE-199-COMMON-MANIFEST-v1/manifest/"
            "building_camera_view_crop_manifest_v1.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("building_id") == "DEBY_LOD2_4906982"
    )
    data_stats = materialize_scene_crop(
        source_root,
        source_root / "sparse",
        staging / "data/colmap_crop",
        plans,
        building_row["viewport_bbox_xy"],
    )
    points_path = staging / "data/colmap_crop/sparse/0/points3D.bin"
    points = read_points3d_bin(points_path)
    z_low, z_high = (
        float(value) - float(WORLD_SHIFT[2])
        for value in building_row["z_range_ellipsoidal_m"]
    )
    points = points[(points[:, 2] >= z_low) & (points[:, 2] <= z_high)]
    write_points3d_bin(points_path, points)
    data_stats["sfm_points_clipped"] = int(len(points))
    data_stats["sfm_crop_rule"] = "reviewed viewport XYZ prism"

    exact_manifest = {
        "schema": "jointbuildgs.exact_local_view_manifest.v1",
        "member_count": len(rows),
        "rows": [{"basename": row["view_name"]} for row in rows],
    }
    exact_path = staging / "control/exact_views.json"
    roles_path = staging / "control/view_roles.json"
    write_json(exact_path, exact_manifest)
    write_json(
        roles_path,
        {
            "schema": "jointbuildgs.p2.e3_local_4906982.view_roles.v1",
            "rule": "PROTECT_GLOBAL_HELDOUT_PLUS_AZIMUTH_NADIR_STRATIFIED_FILL",
            "train_count": len(train_views),
            "eval_count": len(eval_views),
            "train_views": train_views,
            "eval_views": eval_views,
        },
    )

    final_data = task_root / "data/colmap_crop"
    final_exact = task_root / "control/exact_views.json"
    final_roles = task_root / "control/view_roles.json"
    run_root = artifacts / (
        "phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1/"
        f"runs/{args.run_name}/seed0"
    )
    config = yaml.safe_load(common_config_path.read_text(encoding="utf-8"))
    config.update(
        {
            "data_root": str(final_data).replace(str(artifacts), "/artifacts/JointBuildGS"),
            "exact_view_manifest": str(final_exact).replace(str(artifacts), "/artifacts/JointBuildGS"),
            "exact_view_manifest_sha256": sha256(exact_path),
            "exact_view_count": len(rows),
            "view_roles_manifest": str(final_roles).replace(str(artifacts), "/artifacts/JointBuildGS"),
            "view_roles_manifest_sha256": sha256(roles_path),
            "out_dir": str(run_root).replace(str(artifacts), "/artifacts/JointBuildGS"),
            "load_depth": False,
            "w_depth": 0.0,
            "load_normal": False,
            "w_normal": 0.0,
            "load_semantic": False,
            "w_sem": 0.0,
            "w_distort": args.w_distort,
            "reset_every": args.reset_every,
            "eval_every": 1000,
            "ckpt_every": 1000,
            "max_iter": args.max_iter,
            "scientific_verdict": None,
        }
    )
    config.pop("init_pointcloud", None)
    config_path = staging / "config/effective.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    summary = {
        "building_id": "DEBY_LOD2_4906982",
        "view_count": len(rows),
        "train_count": len(train_views),
        "eval_count": len(eval_views),
        "sparse_seed_count": int(data_stats["sfm_points_clipped"]),
        "max_iter": int(config["max_iter"]),
        "run_root": str(run_root),
        "training_started": False,
    }
    write_json(
        staging / "control/prep_receipt.json",
        {
            "schema": SCHEMA,
            "source_identity": source_identity,
            "source_preflight": preflight,
            "data_stats": data_stats,
            "effective_config_sha256": sha256(config_path),
            "summary": summary,
            "scientific_verdict": None,
        },
    )
    (staging / "NOTES.md").write_text(
        "# E3 local 4906982 training prep\n\n"
        "- Reuses the reviewed v3 55-view crop and existing materialize_scene_crop.\n"
        "- Train/eval = 47/8; six original held-out views remain evaluation-only.\n"
        "- Eight near-nadir views selected by actual roof-footprint visibility repair the v2 context-prism blind spot.\n"
        f"- Iteration budget: {args.max_iter}; w_distort: {args.w_distort}; reset_every: {args.reset_every}.\n"
        "- The task/run identifiers and diagnostic controls are explicit CLI inputs so the same connector is reused.\n"
        "- Initialization is the cropped real SfM sparse cloud; MVS seed is not used.\n"
        "- Loss is the existing E1-E6 common gsplat 2DGS body with MVS depth/normal and all external priors disabled.\n"
        "- Training outputs are technical-development observations; scientific_verdict remains null.\n",
        encoding="utf-8",
    )
    os.replace(staging, task_root)
    print(json.dumps({"status": "built", **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

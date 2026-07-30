#!/usr/bin/env python3
"""S3-B step-0a alpha sweep over the 42 existing checkpoints; learning zero."""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import platform
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np
import torch
from shapely import contains_xy
from shapely.geometry import Point, box

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator  # noqa: E402

import e5_c001_s3b0_common as common


SUMMARY_FIELDS = [
    "row_type", "run_id", "building_id", "arm", "replicate", "job_class",
    "height_delta_m", "alpha", "canonical_depth", "fused_all_count",
    "minobs_count", "sor_count", "sor_status", "inside_footprint_count",
    "height_window_count", "roof_candidate_count", "anchor_band_count",
    "anchor_band_coverage_eligible_cells", "anchor_band_coverage_occupied_cells",
    "anchor_band_coverage_ratio", "anchor_band_density_pt_m2",
    "inside_density_pt_m2", "above_anchor_count", "below_anchor_count",
    "reference_band_199_count", "reference_band_199_present",
    "seed_anchor_source", "seed_anchor_half_band_m", "ground_z_local_m",
    "roof_candidate_min_above_ground_m", "histogram_top_above_ground_m",
    "survival_class", "upper_xy_pattern", "upper_edge_fraction",
    "upper_neighbor_direction_fraction", "upper_cell_count_cv",
    "nearest_neighbor_building_id", "alpha0p5_existing_fused_all_match",
    "alpha0p5_existing_minobs_match", "alpha0p5_existing_sor_match",
    "alpha0p5_existing_all_payload_match", "alpha0p5_existing_clean_payload_match",
    "checkpoint", "checkpoint_sha256", "extraction_npz", "extraction_npz_sha256",
    "gt_role", "learning_runs_started", "status",
    "hist_bin_low_above_ground_m", "hist_bin_high_above_ground_m", "hist_count",
    "classification_name", "classification_count", "classification_fraction",
]

TIMELINE_FIELDS = [
    "run_id", "building_id", "arm", "replicate", "step",
    "n_primitives", "seed_surviving_lineage_count", "seed_fp_count",
    "seed_fp_median_opacity", "prune_candidates", "prune_seed_protected",
    "pruned", "cum_prune_candidates", "cum_prune_seed_protected", "cum_pruned",
    "seed_protect_active", "seed_protected_count", "effective_prune_opa",
    "effective_reset_opa", "event_files", "event_files_sha256",
    "runner_log", "runner_log_sha256", "lineage_count_note",
    "seed_log_count", "seed_opacity_source", "opacity_checkpoint",
    "opacity_checkpoint_sha256",
    "learning_runs_started", "status",
]

CLASS_LABELS = {
    "밀림": "shifted",
    "소멸": "vanished",
    "판독_미달": "readout_below_threshold",
    "잔존": "retained",
    "상하_분산": "split_above_below",
}


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def alpha_tag(value: float) -> str:
    return str(value).replace(".", "p")


def sorted_points(points: np.ndarray) -> np.ndarray:
    value = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    if not len(value):
        return value
    order = np.lexsort((value[:, 2], value[:, 1], value[:, 0]))
    return value[order]


def payload_match(left: np.ndarray, right: np.ndarray, atol: float = 1e-12) -> bool:
    a = sorted_points(left)
    b = sorted_points(right)
    return bool(a.shape == b.shape and np.allclose(a, b, rtol=0.0, atol=atol))


def fit_plane(points_local: np.ndarray) -> np.ndarray:
    design = np.column_stack([points_local[:, 0], points_local[:, 1], np.ones(len(points_local))])
    return np.linalg.lstsq(design, points_local[:, 2], rcond=None)[0].astype(np.float64)


def point_inside_world(points_world: np.ndarray, footprint: Any) -> np.ndarray:
    if not len(points_world):
        return np.zeros(0, dtype=bool)
    minx, miny, maxx, maxy = footprint.bounds
    x, y = points_world[:, 0], points_world[:, 1]
    box_mask = (x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy)
    index = np.flatnonzero(box_mask)
    output = np.zeros(len(points_world), dtype=bool)
    if len(index):
        output[index] = contains_xy(footprint, x[index], y[index])
    return output


def occupied_coverage(points_xy: np.ndarray, footprint: Any, grid: float) -> tuple[int, int, float]:
    minx, miny, maxx, maxy = footprint.bounds
    eligible: set[tuple[int, int]] = set()
    for ix in range(math.floor(minx / grid), math.ceil(maxx / grid)):
        for iy in range(math.floor(miny / grid), math.ceil(maxy / grid)):
            if footprint.intersects(box(ix * grid, iy * grid, (ix + 1) * grid, (iy + 1) * grid)):
                eligible.add((ix, iy))
    occupied = {
        (math.floor(float(x) / grid), math.floor(float(y) / grid))
        for x, y in np.asarray(points_xy, dtype=np.float64).reshape(-1, 2)
    } & eligible
    return len(eligible), len(occupied), len(occupied) / len(eligible) if eligible else 0.0


def validate_sources(
    jobs: list[dict[str, str]],
    status_by_id: dict[str, dict[str, str]],
    phase3_lock: dict[str, Any],
    lock: dict[str, Any],
) -> None:
    if len(jobs) != 42 or len(status_by_id) != 42:
        raise RuntimeError(f"base42 inventory drift: jobs={len(jobs)}, status={len(status_by_id)}")
    if phase3_lock["extraction"]["alpha_min_inclusive"] != 0.5:
        raise RuntimeError("existing Phase-3 alpha lock drift")
    for key in ("voxel_m", "min_observations", "sor_neighbors", "sor_std_ratio"):
        if key not in phase3_lock["extraction"]:
            raise RuntimeError(f"Phase-3 extraction field missing: {key}")
    for row in jobs:
        status = status_by_id.get(row["job_id"])
        if status is None or status["status"] != "complete" or status["returncode"] != "0":
            raise RuntimeError(f"checkpoint status is not complete: {row['job_id']}")
        if row["gt_used"] != "False" or row["lod2_used"] != "False" or row["als_used"] != "False":
            raise RuntimeError(f"training input truth flag drift: {row['job_id']}")
        if status["final_checkpoint"] != row["final_checkpoint"]:
            raise RuntimeError(f"checkpoint path drift: {row['job_id']}")
    if lock["alpha_0a"]["canonical_depth"] != phase3_lock["extraction"]["canonical_depth"]:
        raise RuntimeError("canonical depth drift between S3-B0 and Phase 3")
    if not math.isclose(
        float(lock["alpha_0a"]["roof_candidate_min_above_ground_m"]),
        float(phase3_lock["roof_evidence"]["minimum_height_above_observed_ground_m"]),
    ):
        raise RuntimeError("roof-candidate minimum drift between S3-B0 and Phase 3")


def worker(args: argparse.Namespace) -> None:
    lock = common.load_lock(args.lock.resolve())
    sources = {key: common.resolve(value) for key, value in lock["sources"].items()}
    outputs = {key: common.resolve(value) for key, value in lock["outputs"].items()}
    phase3_lock = json.loads(sources["phase3_lock"].read_text(encoding="utf-8"))
    jobs = read_csv(sources["phase2_jobs_csv"])
    status_rows = read_csv(sources["phase2_status_csv"])
    status_by_id = {row["job_id"]: row for row in status_rows}
    validate_sources(jobs, status_by_id, phase3_lock, lock)
    phase3 = load_module(
        "s3b0_phase3_reuse",
        common.REPO / "phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase3.py",
    )
    sys.path.insert(0, str(common.REPO))
    from gsplat import rasterization_2dgs
    from src.stage2.colmap_io import read_cameras_bin, read_images_bin

    shard_jobs = [
        row for index, row in enumerate(jobs)
        if index % int(args.shard_count) == int(args.shard_index)
    ]
    runtime_root = outputs["alpha_runtime_root"]
    result_root = runtime_root / "jobs"
    run_jobs = outputs["alpha_run"] / "jobs"
    result_root.mkdir(parents=True, exist_ok=True)
    run_jobs.mkdir(parents=True, exist_ok=True)
    log_path = outputs["alpha_run"] / f"worker_{args.shard_index}.log"
    common.atomic_text(log_path, "")

    def log(message: str) -> None:
        line = f"{common.now()} {message}"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        print(line, flush=True)

    ext = phase3_lock["extraction"]
    alpha_values = [float(value) for value in lock["alpha_0a"]["alpha_values"]]
    offset = common.load_world_offset(sources["train_manifest"])
    device = torch.device("cuda")
    for ordinal, row in enumerate(shard_jobs, start=1):
        run_id = row["job_id"]
        checkpoint = common.resolve(row["final_checkpoint"])
        prepared = common.resolve(row["data_root"])
        status = status_by_id[run_id]
        checkpoint_hash = common.sha256_file(checkpoint)
        if checkpoint_hash != status["final_checkpoint_sha256"]:
            raise RuntimeError(f"checkpoint hash drift: {run_id}")
        sparse = prepared / "sparse"
        if (sparse / "0/cameras.bin").exists():
            sparse = sparse / "0"
        cameras = read_cameras_bin(sparse / "cameras.bin")
        images = sorted(read_images_bin(sparse / "images.bin").values(), key=lambda item: item.name)
        payload = torch.load(checkpoint, map_location=device, weights_only=False)
        state = payload["state_dict"]
        means = state["means"].to(device)
        quats = state["quats"].to(device)
        scales = torch.exp(state["log_scales"]).to(device)
        opacities = torch.sigmoid(state["opacities_raw"]).to(device).reshape(-1)
        colors = torch.cat([state["sh0"], state["shN"]], dim=1).to(device)
        voxel_m = float(ext["voxel_m"])
        depth_min = float(ext["depth_min_m_exclusive"])
        depth_max = float(ext["depth_max_m_exclusive"])
        off, mul = 1 << 20, 1 << 21
        chunks: dict[float, list[Any]] = {alpha: [] for alpha in alpha_values}
        view_rows: list[dict[str, Any]] = []

        def add_keys(points: torch.Tensor, alpha: float) -> None:
            quantized = torch.floor(points / voxel_m).to(torch.int64) + off
            if torch.any(quantized < 0) or torch.any(quantized >= mul):
                raise RuntimeError(f"voxel key range exceeded: {run_id} alpha={alpha}")
            packed = (quantized[:, 0] * mul + quantized[:, 1]) * mul + quantized[:, 2]
            chunks[alpha].append(torch.unique(packed).cpu())

        for view_index, image in enumerate(images):
            camera = cameras[image.camera_id]
            width, height = int(camera.width), int(camera.height)
            intrinsic = torch.tensor(camera.K(), dtype=torch.float32, device=device)
            rotation = torch.tensor(image.R(), dtype=torch.float32, device=device)
            translation = torch.tensor(image.tvec, dtype=torch.float32, device=device)
            viewmat = torch.eye(4, dtype=torch.float32, device=device)
            viewmat[:3, :3] = rotation
            viewmat[:3, 3] = translation
            with torch.no_grad():
                rendered = rasterization_2dgs(
                    means=means,
                    quats=quats,
                    scales=scales,
                    opacities=opacities,
                    colors=colors,
                    viewmats=viewmat.unsqueeze(0),
                    Ks=intrinsic.unsqueeze(0),
                    width=width,
                    height=height,
                    near_plane=0.01,
                    far_plane=1e10,
                    render_mode="RGB+ED",
                    depth_mode="expected",
                    sh_degree=int(ext["sh_degree"]),
                )
            alpha_image = rendered[1][0, ..., 0]
            median_depth = rendered[5][0, ..., 0]
            pixel_v, pixel_u = torch.meshgrid(
                torch.arange(height, dtype=torch.float32, device=device),
                torch.arange(width, dtype=torch.float32, device=device),
                indexing="ij",
            )
            audit = {"view_index": view_index, "view_name": image.name}
            finite_base = (
                torch.isfinite(alpha_image)
                & torch.isfinite(median_depth)
                & (median_depth > depth_min)
                & (median_depth < depth_max)
            )
            for alpha_value in alpha_values:
                valid = finite_base & (alpha_image >= alpha_value)
                audit[f"alpha_{alpha_tag(alpha_value)}_valid_pixels"] = int(valid.sum().item())
                if not torch.any(valid):
                    continue
                z = median_depth[valid]
                x = (pixel_u[valid] - intrinsic[0, 2]) / intrinsic[0, 0] * z
                y = (pixel_v[valid] - intrinsic[1, 2]) / intrinsic[1, 1] * z
                camera_xyz = torch.stack([x, y, z], dim=1)
                world_local = (camera_xyz - translation) @ rotation
                world_local = world_local[torch.isfinite(world_local).all(dim=1)]
                if len(world_local):
                    add_keys(world_local, alpha_value)
            view_rows.append(audit)

        save: dict[str, Any] = {
            "world_offset": offset,
            "view_names": np.asarray([image.name for image in images]),
            "voxel_m": np.asarray(voxel_m),
            "min_observations": np.asarray(int(ext["min_observations"])),
        }
        fusion_manifest: dict[str, Any] = {}
        for alpha_value in alpha_values:
            result = phase3._fuse_key_chunks(
                chunks[alpha_value],
                voxel_m=voxel_m,
                min_observations=int(ext["min_observations"]),
                world_offset=offset,
                sor_neighbors=int(ext["sor_neighbors"]),
                sor_std_ratio=float(ext["sor_std_ratio"]),
            )
            tag = alpha_tag(alpha_value)
            for stage in ("all", "minobs", "clean"):
                save[f"P_utm_alpha_{tag}_{stage}"] = result[stage]
                save[f"observation_count_alpha_{tag}_{stage}"] = result[f"{stage}_counts"]
            fusion_manifest[tag] = {
                "alpha": alpha_value,
                "fused_all": int(len(result["all"])),
                "minobs_kept": int(len(result["minobs"])),
                "sor_kept": int(len(result["clean"])),
                "sor_status": result["sor_status"],
            }
        output_npz = result_root / f"{run_id}.npz"
        tmp = output_npz.with_name(output_npz.name + ".tmp.npz")
        np.savez_compressed(tmp, **save)
        os.replace(tmp, output_npz)
        existing_path = sources["phase3_root"] / "jobs" / run_id / "fused_depth.npz"
        existing_checks: dict[str, Any] = {"available": existing_path.exists()}
        if existing_path.exists():
            existing = np.load(existing_path, allow_pickle=False)
            tag = alpha_tag(0.5)
            existing_checks.update(
                {
                    "fused_all_count_match": int(len(save[f"P_utm_alpha_{tag}_all"]))
                    == int(len(existing["P_utm_median_all"])),
                    "minobs_count_match": int(len(save[f"P_utm_alpha_{tag}_minobs"]))
                    == int(len(existing["P_utm_median_minobs"])),
                    "sor_count_match": int(len(save[f"P_utm_alpha_{tag}_clean"]))
                    == int(len(existing["P_utm_median_clean"])),
                    "all_payload_match": payload_match(
                        save[f"P_utm_alpha_{tag}_all"], existing["P_utm_median_all"]
                    ),
                    "clean_payload_match": payload_match(
                        save[f"P_utm_alpha_{tag}_clean"], existing["P_utm_median_clean"]
                    ),
                    "existing_path": common.rel(existing_path),
                    "existing_sha256": common.sha256_file(existing_path),
                }
            )
            required = [
                "fused_all_count_match", "minobs_count_match", "sor_count_match",
                "all_payload_match", "clean_payload_match",
            ]
            if not all(existing_checks[key] for key in required):
                raise RuntimeError(f"alpha=0.5 Phase-3 cross-check drift: {run_id} {existing_checks}")
        manifest = {
            "schema": "jointbuildgs.s3b0.alpha_extraction.v1",
            "created_utc": common.now(),
            "run_id": run_id,
            "building_id": common.full_id(row["building_id"]),
            "arm": row["arm"],
            "replicate": row["replicate"],
            "job_class": row["job_class"],
            "height_delta_m": float(row["height_delta_m"]),
            "checkpoint": common.rel(checkpoint),
            "checkpoint_sha256": checkpoint_hash,
            "checkpoint_it": int(status["final_checkpoint_it"]),
            "checkpoint_n_prim": int(status["final_checkpoint_n_prim"]),
            "prepared_root": common.rel(prepared),
            "fixed_view_count": len(images),
            "fixed_views": [image.name for image in images],
            "render_pass_count": 1,
            "equivalent_alpha_readout_count": len(alpha_values),
            "fusion": fusion_manifest,
            "phase3_alpha0p5_crosscheck": existing_checks,
            "view_rows": view_rows,
            "output_npz": common.rel(output_npz),
            "output_npz_sha256": common.sha256_file(output_npz),
            "gt_used": False,
            "lod2_used": False,
            "als_used": False,
            "learning_runs_started": 0,
            "status": "measured",
        }
        manifest_path = run_jobs / f"{run_id}.json"
        common.atomic_json(manifest_path, manifest)
        log(
            f"job={ordinal}/{len(shard_jobs)} run={run_id} views={len(images)} "
            f"a0p1={fusion_manifest['0p1']['sor_kept']} "
            f"a0p5={fusion_manifest['0p5']['sor_kept']} learning=0"
        )
        del payload, state, means, quats, scales, opacities, colors
        torch.cuda.empty_cache()


def nearest_neighbors(footprints: dict[str, Any], targets: Iterable[str]) -> dict[str, str]:
    output: dict[str, str] = {}
    for target in targets:
        centre = footprints[target].centroid
        candidates = [
            (centre.distance(geom.centroid), bid)
            for bid, geom in footprints.items() if bid != target
        ]
        output[target] = min(candidates)[1]
    return output


def upper_pattern(
    points_world: np.ndarray,
    footprint: Any,
    neighbor_footprint: Any,
    grid: float,
    edge_band_m: float,
    edge_threshold: float,
    neighbor_threshold: float,
) -> dict[str, Any]:
    if not len(points_world):
        return {
            "pattern": "none",
            "edge_fraction": None,
            "neighbor_direction_fraction": None,
            "cell_count_cv": None,
            "cells": np.empty((0, 3), dtype=np.float64),
        }
    distances = np.asarray(
        [footprint.boundary.distance(Point(float(x), float(y))) for x, y in points_world[:, :2]],
        dtype=np.float64,
    )
    edge_fraction = float(np.mean(distances <= edge_band_m))
    centre = np.asarray(footprint.centroid.coords[0], dtype=np.float64)
    neighbor = np.asarray(neighbor_footprint.centroid.coords[0], dtype=np.float64)
    direction = neighbor - centre
    norm = float(np.linalg.norm(direction))
    if norm > 1e-12:
        direction /= norm
        relative = points_world[:, :2] - centre[None, :]
        neighbor_fraction = float(np.mean(relative @ direction > 0.0))
    else:
        neighbor_fraction = 0.5
    keys = np.floor(points_world[:, :2] / grid).astype(np.int64)
    unique, counts = np.unique(keys, axis=0, return_counts=True)
    cell_cv = float(np.std(counts) / np.mean(counts)) if len(counts) and np.mean(counts) > 0 else 0.0
    cells = np.column_stack(
        [
            (unique[:, 0].astype(np.float64) + 0.5) * grid,
            (unique[:, 1].astype(np.float64) + 0.5) * grid,
            counts.astype(np.float64),
        ]
    )
    if edge_fraction >= edge_threshold:
        pattern = "edge_band_concentrated"
    elif neighbor_fraction >= neighbor_threshold:
        pattern = "neighbor_direction_concentrated"
    else:
        pattern = "interior_distributed"
    return {
        "pattern": pattern,
        "edge_fraction": edge_fraction,
        "neighbor_direction_fraction": neighbor_fraction,
        "cell_count_cv": cell_cv,
        "cells": cells,
    }


def classify(low: dict[str, Any], high: dict[str, Any]) -> str:
    if int(low["anchor_band_count"]) == 0:
        if int(low["above_anchor_count"]) > 0 and int(low["below_anchor_count"]) == 0:
            return "밀림"
        if int(low["above_anchor_count"]) == 0:
            return "소멸"
        return "상하_분산"
    if int(high["anchor_band_count"]) == 0:
        return "판독_미달"
    return "잔존"


def parse_timeline(
    jobs: list[dict[str, str]],
    status_by_id: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    tags = {
        "stats/n_primitives": "n_primitives",
        "seed/surviving": "seed_surviving_lineage_count",
        "stats/prune_candidates": "prune_candidates",
        "stats/prune_seed_protected": "prune_seed_protected",
        "stats/pruned": "pruned",
        "stats/cum_prune_candidates": "cum_prune_candidates",
        "stats/cum_prune_seed_protected": "cum_prune_seed_protected",
        "stats/cum_pruned": "cum_pruned",
        "stats/seed_protect_active": "seed_protect_active",
        "stats/seed_protected_count": "seed_protected_count",
        "stats/effective_prune_opa": "effective_prune_opa",
        "stats/effective_reset_opa": "effective_reset_opa",
    }
    for job in jobs:
        if job["job_class"] != "base" or job["arm"] != "a2":
            continue
        run_id = job["job_id"]
        short = job["building_id"]
        run_dir = common.resolve(job["out_dir"])
        event_files = sorted((run_dir / "tb").glob("events.out.tfevents*"))
        if not event_files:
            raise RuntimeError(f"A2 TensorBoard events absent: {run_id}")
        accumulator = EventAccumulator(str(run_dir / "tb"), size_guidance={"scalars": 0})
        accumulator.Reload()
        available = set(accumulator.Tags().get("scalars", []))
        series: dict[str, dict[int, float]] = {}
        for tag, field in tags.items():
            if tag in available:
                series[field] = {
                    int(event.step): float(event.value)
                    for event in accumulator.Scalars(tag)
                }
        runner_log = common.resolve(status_by_id[run_id]["log_path"])
        text = runner_log.read_text(encoding="utf-8", errors="ignore")
        pattern = re.compile(
            r"\[seed-survival\]\s+it=(\d+)\s+N=(\d+)\s+seeds=(\d+)"
        )
        logged_seed_count: dict[int, int] = {}
        for match in pattern.finditer(text):
            logged_seed_count[int(match.group(1))] = int(match.group(3))

        checkpoint_opacity: dict[int, dict[str, Any]] = {}
        checkpoint_paths = sorted((run_dir / "ckpt").glob("step_*.pt"))
        checkpoint_paths.extend(sorted((run_dir / "ckpt").glob("final.pt")))
        for checkpoint in checkpoint_paths:
            payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
            step = int(payload["it"])
            lineage = payload.get("surface_seed_lineage_mask")
            state = payload.get("state_dict", {})
            if lineage is None or "opacities_raw" not in state:
                raise RuntimeError(f"A2 checkpoint lacks seed opacity state: {checkpoint}")
            lineage = lineage.detach().cpu().bool().reshape(-1)
            opacities = torch.sigmoid(state["opacities_raw"].detach().cpu()).reshape(-1)
            if len(lineage) != len(opacities):
                raise RuntimeError(f"A2 seed-lineage/opacity length drift: {checkpoint}")
            selected = opacities[lineage]
            checkpoint_opacity[step] = {
                "count": int(lineage.sum().item()),
                "median_opacity": float(selected.median().item()) if len(selected) else 0.0,
                "path": common.rel(checkpoint),
                "sha256": common.sha256_file(checkpoint),
            }

        steps = sorted(
            set().union(
                *(values.keys() for values in series.values()),
                logged_seed_count.keys(),
                checkpoint_opacity.keys(),
            )
        )
        event_paths = [common.rel(path) for path in event_files]
        event_hashes = {common.rel(path): common.sha256_file(path) for path in event_files}
        for step in steps:
            opacity_row = checkpoint_opacity.get(step)
            source_header = step == steps[0]
            row: dict[str, Any] = {
                "run_id": run_id,
                "building_id": common.full_id(short),
                "arm": job["arm"],
                "replicate": job["replicate"],
                "step": step,
                "seed_fp_count": opacity_row["count"] if opacity_row else None,
                "seed_fp_median_opacity": opacity_row["median_opacity"] if opacity_row else None,
                "event_files": ";".join(event_paths) if source_header else None,
                "event_files_sha256": (
                    json.dumps(event_hashes, sort_keys=True) if source_header else None
                ),
                "runner_log": common.rel(runner_log) if source_header else None,
                "runner_log_sha256": common.sha256_file(runner_log) if source_header else None,
                "lineage_count_note": (
                    "seed/surviving and checkpoint surface_seed_lineage_mask include "
                    "seed-lineage children created by densification; prepared crop carries "
                    "the named target building surface seed"
                    if source_header
                    else None
                ),
                "seed_log_count": logged_seed_count.get(step),
                "seed_opacity_source": (
                    "read-only checkpoint surface_seed_lineage_mask median sigmoid(opacities_raw)"
                    if opacity_row else "not sampled; no checkpoint at this step"
                ),
                "opacity_checkpoint": opacity_row["path"] if opacity_row else None,
                "opacity_checkpoint_sha256": opacity_row["sha256"] if opacity_row else None,
                "learning_runs_started": 0,
                "status": "measured",
            }
            for field, values in series.items():
                row[field] = values.get(step)
            rows.append(row)
    return rows


def make_heightmap(
    path: Path,
    points_world: np.ndarray,
    footprint: Any,
    offset: np.ndarray,
    plane: np.ndarray,
    row: dict[str, Any],
) -> None:
    centre = np.asarray(footprint.centroid.coords[0], dtype=np.float64)
    local_xy = points_world[:, :2] - offset[None, :2] if len(points_world) else np.empty((0, 2))
    residual = (
        points_world[:, 2] - offset[2]
        - (plane[0] * local_xy[:, 0] + plane[1] * local_xy[:, 1] + plane[2])
        if len(points_world) else np.empty(0)
    )
    fig, axis = plt.subplots(figsize=(6.2, 5.4), dpi=170)
    for polygon in common.flatten_polygons(footprint):
        xy = np.asarray(polygon.exterior.coords, dtype=np.float64)
        axis.plot(xy[:, 0] - centre[0], xy[:, 1] - centre[1], color="#222222", linewidth=1.2)
    if len(points_world):
        scatter = axis.scatter(
            points_world[:, 0] - centre[0],
            points_world[:, 1] - centre[1],
            c=residual,
            s=5,
            cmap="coolwarm",
            vmin=-4.0,
            vmax=4.0,
            linewidths=0,
        )
        colorbar = fig.colorbar(scatter, ax=axis)
        colorbar.set_label("z - seed anchor plane [m]")
    axis.set_aspect("equal")
    axis.set_xlabel("E - footprint centre [m]")
    axis.set_ylabel("N - footprint centre [m]")
    axis.set_title(
        f"{row['building_id']} | A1 r1 | alpha={row['alpha']}\n"
        f"anchor band N={row['anchor_band_count']}, coverage={float(row['anchor_band_coverage_ratio']):.3f}, "
        f"class={CLASS_LABELS.get(row['survival_class'], row['survival_class'])}"
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    fig.savefig(tmp)
    plt.close(fig)
    os.replace(tmp, path)


def make_upper_cell_figure(
    path: Path,
    classified: list[tuple[dict[str, Any], np.ndarray, Any]],
    building_id: str,
) -> None:
    selected = [
        item
        for item in classified
        if item[0]["survival_class"] == "밀림" and item[0]["building_id"] == building_id
    ]
    count = max(1, len(selected))
    columns = min(4, count)
    rows = math.ceil(count / columns)
    fig, axes = plt.subplots(rows, columns, figsize=(3.8 * columns, 3.5 * rows), dpi=160)
    axes_array = np.atleast_1d(axes).reshape(-1)
    vmax = max(
        (float(np.max(cells[:, 2])) for _row, cells, _footprint in selected if len(cells)),
        default=1.0,
    )
    scalar = plt.cm.ScalarMappable(
        norm=Normalize(vmin=1.0, vmax=max(1.0, vmax)),
        cmap="viridis",
    )
    if not selected:
        axes_array[0].text(0.5, 0.5, "shifted runs: 0", ha="center", va="center")
        axes_array[0].axis("off")
    for axis, (row, cells, footprint) in zip(axes_array, selected):
        centre = np.asarray(footprint.centroid.coords[0], dtype=np.float64)
        for polygon in common.flatten_polygons(footprint):
            xy = np.asarray(polygon.exterior.coords, dtype=np.float64)
            axis.plot(xy[:, 0] - centre[0], xy[:, 1] - centre[1], color="#222222", linewidth=1.0)
        if len(cells):
            axis.scatter(
                cells[:, 0] - centre[0], cells[:, 1] - centre[1],
                c=cells[:, 2], s=22, cmap="viridis", vmin=1.0, vmax=vmax, linewidths=0,
            )
        axis.set_aspect("equal")
        delta = float(row["height_delta_m"])
        axis.set_title(
            f"{str(row['arm']).upper()} {row['replicate']} {row['job_class']} dz={delta:+g}m\n"
            f"edge={float(row['upper_edge_fraction']):.3f}, "
            f"neighbor={float(row['upper_neighbor_direction_fraction']):.3f}",
            fontsize=8,
        )
        axis.tick_params(labelsize=7)
    for axis in axes_array[len(selected):]:
        axis.axis("off")
    if selected:
        color_axis = fig.add_axes([0.925, 0.15, 0.015, 0.70])
        fig.colorbar(scalar, cax=color_axis, label="upper mass count / 0.5m cell")
    fig.suptitle(
        f"{building_id} | alpha=0.1 upper-anchor mass XY cells | shifted runs",
        fontsize=11,
    )
    fig.subplots_adjust(left=0.05, right=0.89, bottom=0.04, top=0.92, wspace=0.28, hspace=0.36)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    fig.savefig(tmp)
    plt.close(fig)
    os.replace(tmp, path)


def make_timeline_figure(path: Path, timeline: list[dict[str, Any]]) -> None:
    run_ids = sorted({row["run_id"] for row in timeline})
    fig, axes = plt.subplots(3, 2, figsize=(13, 10), dpi=155, sharex=False)
    for axis, run_id in zip(axes.reshape(-1), run_ids):
        values = [row for row in timeline if row["run_id"] == run_id]
        step = np.asarray([int(row["step"]) for row in values])
        seed = np.asarray(
            [float(row["seed_surviving_lineage_count"]) if row.get("seed_surviving_lineage_count") is not None else np.nan for row in values]
        )
        protected = np.asarray(
            [float(row["seed_protected_count"]) if row.get("seed_protected_count") is not None else np.nan for row in values]
        )
        opacity = np.asarray(
            [float(row["seed_fp_median_opacity"]) if row.get("seed_fp_median_opacity") is not None else np.nan for row in values]
        )
        cumulative_candidates = np.asarray(
            [float(row["cum_prune_candidates"]) if row.get("cum_prune_candidates") is not None else np.nan for row in values]
        )
        cumulative_protected = np.asarray(
            [float(row["cum_prune_seed_protected"]) if row.get("cum_prune_seed_protected") is not None else np.nan for row in values]
        )
        cumulative_pruned = np.asarray(
            [float(row["cum_pruned"]) if row.get("cum_pruned") is not None else np.nan for row in values]
        )
        active = np.asarray(
            [float(row["seed_protect_active"]) if row.get("seed_protect_active") is not None else np.nan for row in values]
        )
        denominator = np.where(cumulative_candidates > 0, cumulative_candidates, np.nan)
        protected_fraction = cumulative_protected / denominator
        pruned_fraction = cumulative_pruned / denominator
        active_indices = np.flatnonzero(active > 0.5)
        if len(active_indices):
            start = step[active_indices[0]]
            previous = active_indices[0]
            for current in active_indices[1:]:
                if current != previous + 1:
                    axis.axvspan(start, step[previous], color="#c9e4c5", alpha=0.28)
                    start = step[current]
                previous = current
            axis.axvspan(start, step[previous], color="#c9e4c5", alpha=0.28, label="protect active")
        axis.plot(step, seed, color="#355c7d", label="seed lineage count")
        axis.plot(step, protected, color="#6c9a8b", linestyle="--", label="protected count")
        twin = axis.twinx()
        twin.plot(step, opacity, color="#c49a46", marker="o", markersize=2.5, label="target seed median opacity")
        twin.plot(step, protected_fraction, color="#5a8f69", label="cum protected / candidates")
        twin.plot(step, pruned_fraction, color="#c06c84", label="cum pruned / candidates")
        twin.set_ylim(0, 1)
        axis.set_title(run_id)
        axis.set_xlabel("step")
        axis.grid(alpha=0.2)
        lines, labels = axis.get_legend_handles_labels()
        lines2, labels2 = twin.get_legend_handles_labels()
        axis.legend(lines + lines2, labels + labels2, fontsize=6, loc="best")
    fig.suptitle("A2 protect/prune/opacity timeline | existing logs only | learning 0", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    fig.savefig(tmp)
    plt.close(fig)
    os.replace(tmp, path)


def aggregate(args: argparse.Namespace) -> None:
    lock = common.load_lock(args.lock.resolve())
    sources = {key: common.resolve(value) for key, value in lock["sources"].items()}
    outputs = {key: common.resolve(value) for key, value in lock["outputs"].items()}
    alpha_cfg = lock["alpha_0a"]
    jobs = read_csv(sources["phase2_jobs_csv"])
    status_rows = read_csv(sources["phase2_status_csv"])
    status_by_id = {row["job_id"]: row for row in status_rows}
    phase3_lock = json.loads(sources["phase3_lock"].read_text(encoding="utf-8"))
    validate_sources(jobs, status_by_id, phase3_lock, lock)
    job_manifest_root = outputs["alpha_run"] / "jobs"
    manifests = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(job_manifest_root.glob("*.json"))
    }
    if set(manifests) != {row["job_id"] for row in jobs}:
        raise RuntimeError("0-a worker manifest set does not match base42")

    targets = list(lock["targets"])
    target_full = [common.full_id(short) for short in targets]
    footprints_target = common.load_footprints(sources["footprints"], target_full)
    footprints_all = common.load_footprints(sources["footprints"])
    nearest = nearest_neighbors(footprints_all, target_full)
    offset = common.load_world_offset(sources["train_manifest"])
    fm = common.load_fm_summaries(sources["fm_rescore_csv"])
    p0 = np.load(sources["p0_fill_npz"], allow_pickle=False)
    roofs = common.load_lod2_roofs(sources["lod2_dir"], targets)
    geoid = float(json.loads(sources["projection_datum"].read_text(encoding="utf-8"))["orthometric_geoid_m"])
    p0_plane: dict[str, np.ndarray] = {}
    for short in targets:
        points = np.asarray(p0[f"{common.full_id(short)}_local_xyz"], dtype=np.float64)
        p0_plane[short] = fit_plane(points)

    summary_rows: list[dict[str, Any]] = []
    histogram_rows: list[dict[str, Any]] = []
    points_for_figure: dict[tuple[str, float], np.ndarray] = {}
    row_for_figure: dict[tuple[str, float], dict[str, Any]] = {}
    upper_audit: dict[str, dict[str, Any]] = {}
    by_run_alpha: dict[tuple[str, float], dict[str, Any]] = {}
    extraction_paths: list[Path] = []
    for job in jobs:
        run_id = job["job_id"]
        short = job["building_id"]
        building_id = common.full_id(short)
        footprint = footprints_target[building_id]
        manifest = manifests[run_id]
        extraction_path = common.resolve(manifest["output_npz"])
        extraction_paths.append(extraction_path)
        if common.sha256_file(extraction_path) != manifest["output_npz_sha256"]:
            raise RuntimeError(f"0-a extraction hash drift: {run_id}")
        payload = np.load(extraction_path, allow_pickle=False)
        anchor_plane = p0_plane[short].copy()
        anchor_plane[2] += float(job["height_delta_m"])
        ground = float(fm[short]["ground_z_local_m"])
        classification_window_top = ground + float(alpha_cfg["histogram_top_above_ground_m"])
        roof_min = ground + float(alpha_cfg["roof_candidate_min_above_ground_m"])
        footprint_area = float(footprint.area)
        for alpha_value in [float(value) for value in alpha_cfg["alpha_values"]]:
            tag = alpha_tag(alpha_value)
            points_world = np.asarray(payload[f"P_utm_alpha_{tag}_clean"], dtype=np.float64)
            inside = point_inside_world(points_world, footprint)
            inside_points = points_world[inside]
            local_z = inside_points[:, 2] - offset[2] if len(inside_points) else np.empty(0)
            in_window = (local_z >= ground) & (local_z <= classification_window_top)
            roof_mask = (local_z >= roof_min) & (local_z <= classification_window_top)
            roof_points = inside_points[roof_mask]
            roof_local_xy = roof_points[:, :2] - offset[None, :2] if len(roof_points) else np.empty((0, 2))
            anchor_z = (
                anchor_plane[0] * roof_local_xy[:, 0]
                + anchor_plane[1] * roof_local_xy[:, 1]
                + anchor_plane[2]
                if len(roof_points) else np.empty(0)
            )
            residual = roof_points[:, 2] - offset[2] - anchor_z if len(roof_points) else np.empty(0)
            band_mask = np.abs(residual) <= float(alpha_cfg["anchor_half_band_m"])
            above = residual > float(alpha_cfg["anchor_half_band_m"])
            below = residual < -float(alpha_cfg["anchor_half_band_m"])
            band_points = roof_points[band_mask]
            eligible, occupied, coverage = occupied_coverage(
                band_points[:, :2], footprint, float(alpha_cfg["coverage_grid_m"])
            )
            reference_count: int | None = None
            reference_present: bool | None = None
            if short == "4907199":
                reference = (
                    common.reference_roof_z(roof_points[:, :2], roofs[short], geoid)
                    if len(roof_points)
                    else np.empty(0)
                )
                reference_count = int(
                    np.sum(np.abs(roof_points[:, 2] - reference) <= float(alpha_cfg["reference_half_band_199_m"]))
                )
                reference_present = reference_count > 0
            checks = manifest["phase3_alpha0p5_crosscheck"] if math.isclose(alpha_value, 0.5) else {}
            row = {
                "row_type": "summary",
                "run_id": run_id,
                "building_id": building_id,
                "arm": job["arm"],
                "replicate": job["replicate"],
                "job_class": job["job_class"],
                "height_delta_m": float(job["height_delta_m"]),
                "alpha": alpha_value,
                "canonical_depth": alpha_cfg["canonical_depth"],
                "fused_all_count": int(len(payload[f"P_utm_alpha_{tag}_all"])),
                "minobs_count": int(len(payload[f"P_utm_alpha_{tag}_minobs"])),
                "sor_count": int(len(points_world)),
                "sor_status": manifest["fusion"][tag]["sor_status"],
                "inside_footprint_count": int(len(inside_points)),
                "height_window_count": int(in_window.sum()),
                "roof_candidate_count": int(len(roof_points)),
                "anchor_band_count": int(band_mask.sum()),
                "anchor_band_coverage_eligible_cells": eligible,
                "anchor_band_coverage_occupied_cells": occupied,
                "anchor_band_coverage_ratio": coverage,
                "anchor_band_density_pt_m2": int(band_mask.sum()) / footprint_area if footprint_area else None,
                "inside_density_pt_m2": len(inside_points) / footprint_area if footprint_area else None,
                "above_anchor_count": int(above.sum()),
                "below_anchor_count": int(below.sum()),
                "reference_band_199_count": reference_count,
                "reference_band_199_present": reference_present,
                "seed_anchor_source": "Phase-0 P0 fitted plane plus locked job height_delta_m",
                "seed_anchor_half_band_m": float(alpha_cfg["anchor_half_band_m"]),
                "ground_z_local_m": ground,
                "roof_candidate_min_above_ground_m": float(alpha_cfg["roof_candidate_min_above_ground_m"]),
                "histogram_top_above_ground_m": float(alpha_cfg["histogram_top_above_ground_m"]),
                "nearest_neighbor_building_id": nearest[building_id],
                "alpha0p5_existing_fused_all_match": checks.get("fused_all_count_match"),
                "alpha0p5_existing_minobs_match": checks.get("minobs_count_match"),
                "alpha0p5_existing_sor_match": checks.get("sor_count_match"),
                "alpha0p5_existing_all_payload_match": checks.get("all_payload_match"),
                "alpha0p5_existing_clean_payload_match": checks.get("clean_payload_match"),
                "checkpoint": manifest["checkpoint"],
                "checkpoint_sha256": manifest["checkpoint_sha256"],
                "extraction_npz": common.rel(extraction_path),
                "extraction_npz_sha256": manifest["output_npz_sha256"],
                "gt_role": "LoD2 opened after fusion only for 4907199 reference-band score",
                "learning_runs_started": 0,
                "status": "measured",
            }
            summary_rows.append(row)
            by_run_alpha[(run_id, alpha_value)] = row
            if job["job_class"] == "base" and job["arm"] == "a1" and job["replicate"] == "r1":
                points_for_figure[(short, alpha_value)] = roof_points
                row_for_figure[(short, alpha_value)] = row
            bins = np.arange(
                0.0,
                float(alpha_cfg["histogram_top_above_ground_m"]) + float(alpha_cfg["histogram_bin_m"]) * 0.5,
                float(alpha_cfg["histogram_bin_m"]),
            )
            counts, edges = np.histogram(local_z[in_window] - ground, bins=bins)
            for index, count in enumerate(counts):
                histogram_rows.append(
                    {
                        **{key: row.get(key) for key in (
                            "run_id", "building_id", "arm", "replicate", "job_class",
                            "height_delta_m", "alpha", "canonical_depth", "checkpoint",
                            "checkpoint_sha256", "extraction_npz", "extraction_npz_sha256",
                            "gt_role", "learning_runs_started", "status",
                        )},
                        "row_type": "hist_bin",
                        "hist_bin_low_above_ground_m": float(edges[index]),
                        "hist_bin_high_above_ground_m": float(edges[index + 1]),
                        "hist_count": int(count),
                    }
                )
            if math.isclose(alpha_value, 0.1):
                pattern = upper_pattern(
                    roof_points[above],
                    footprint,
                    footprints_all[nearest[building_id]],
                    float(alpha_cfg["xy_map_grid_m"]),
                    float(alpha_cfg["upper_edge_band_m"]),
                    float(alpha_cfg["upper_edge_concentration_fraction"]),
                    float(alpha_cfg["upper_neighbor_direction_fraction"]),
                )
                upper_audit[run_id] = pattern

    classification_rows: list[dict[str, Any]] = []
    classified_for_figure: list[tuple[dict[str, Any], np.ndarray, Any]] = []
    for job in jobs:
        run_id = job["job_id"]
        low = by_run_alpha[(run_id, 0.1)]
        high = by_run_alpha[(run_id, 0.5)]
        survival = classify(low, high)
        pattern = upper_audit[run_id]
        for alpha_value in [0.1, 0.3, 0.5]:
            row = by_run_alpha[(run_id, alpha_value)]
            row["survival_class"] = survival
            row["upper_xy_pattern"] = pattern["pattern"]
            row["upper_edge_fraction"] = pattern["edge_fraction"]
            row["upper_neighbor_direction_fraction"] = pattern["neighbor_direction_fraction"]
            row["upper_cell_count_cv"] = pattern["cell_count_cv"]
        classified_for_figure.append(
            (low, pattern["cells"], footprints_target[common.full_id(job["building_id"])])
        )
    group_keys = sorted({(row["building_id"], row["arm"]) for row in summary_rows})
    for building_id, arm in group_keys:
        run_classes = [
            by_run_alpha[(job["job_id"], 0.1)]["survival_class"]
            for job in jobs
            if common.full_id(job["building_id"]) == building_id and job["arm"] == arm
        ]
        counts = Counter(run_classes)
        for name in sorted(counts):
            classification_rows.append(
                {
                    "row_type": "arm_classification",
                    "building_id": building_id,
                    "arm": arm,
                    "classification_name": name,
                    "classification_count": counts[name],
                    "classification_fraction": counts[name] / len(run_classes),
                    "learning_runs_started": 0,
                    "status": "measured",
                }
            )
    common.atomic_csv(outputs["alpha_csv"], [*summary_rows, *histogram_rows, *classification_rows], SUMMARY_FIELDS)

    timeline = parse_timeline(jobs, status_by_id)
    common.atomic_csv(outputs["timeline_csv"], timeline, TIMELINE_FIELDS)
    figure_dir = outputs["alpha_figure_dir"]
    generated_figures: list[Path] = []
    for short in targets:
        plane = p0_plane[short]
        for alpha_value in [0.1, 0.3, 0.5]:
            row = row_for_figure[(short, alpha_value)]
            path = figure_dir / f"{common.full_id(short)}_a1_r1_alpha_{alpha_tag(alpha_value)}.png"
            make_heightmap(
                path,
                points_for_figure[(short, alpha_value)],
                footprints_target[common.full_id(short)],
                offset,
                plane,
                row,
            )
            generated_figures.append(path)
    stale_upper = figure_dir / "shifted_upper_xy_cells.png"
    if stale_upper.exists():
        stale_upper.unlink()
    for short in targets:
        upper_path = figure_dir / f"{common.full_id(short)}_shifted_upper_xy_cells.png"
        make_upper_cell_figure(upper_path, classified_for_figure, common.full_id(short))
        generated_figures.append(upper_path)
    timeline_path = figure_dir / "a2_seed_survival_timeline.png"
    make_timeline_figure(timeline_path, timeline)
    generated_figures.append(timeline_path)

    cell_arrays: dict[str, np.ndarray] = {}
    for run_id, detail in upper_audit.items():
        cell_arrays[f"{run_id}_alpha0p1_upper_cells"] = np.asarray(detail["cells"], dtype=np.float64)
    cell_npz = outputs["alpha_run"] / "upper_xy_cells.npz"
    common.atomic_deterministic_npz(cell_npz, cell_arrays)

    output_paths = [
        outputs["alpha_csv"], outputs["timeline_csv"], cell_npz,
        *generated_figures, *sorted(job_manifest_root.glob("*.json")),
        outputs["alpha_run"] / "worker_0.log", outputs["alpha_run"] / "worker_1.log",
        outputs["alpha_run"] / "launcher_0.log", outputs["alpha_run"] / "launcher_1.log",
    ]
    code_sources = [
        Path(__file__).resolve(),
        common.REPO / "scripts/e5_c001/s3b0/e5_c001_s3b0_common.py",
        common.REPO / "phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase3.py",
        common.REPO / "scripts/e5_c001/s3b0/run_e5_c001_s3b0_alpha.sh",
        common.REPO / "tests/experiments/e5_c001_s3b0/test_e5_c001_s3b0_alpha.py",
    ]
    lod2_sources = sorted(
        {
            Path(roof["source"])
            for building_roofs in roofs.values()
            for roof in building_roofs
        }
    )
    timeline_sources = {
        common.resolve(row[key])
        for row in timeline
        for key in ("runner_log", "opacity_checkpoint")
        if row.get(key)
    }
    timeline_sources.update(
        common.resolve(path)
        for row in timeline
        for path in str(row.get("event_files", "")).split(";")
        if path
    )
    manifest = {
        "schema": "jointbuildgs.s3b0.alpha_measurement.v1",
        "created_utc": common.now(),
        "task": "0-a existing-checkpoint alpha sweep and A2 log timeline",
        "crs": lock["crs"],
        "git": {
            "head": common.git_value("rev-parse", "HEAD"),
            "branch": common.git_value("branch", "--show-current"),
            "dirty": bool(common.git_value("status", "--porcelain")),
        },
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "docker_image": lock["containers"]["main_image"],
            "docker_image_id": lock["containers"]["main_image_id"],
        },
        "render_contract": {
            "checkpoint_count": 42,
            "render_pass_count": 42,
            "equivalent_alpha_readout_count": 126,
            "alpha_values": alpha_cfg["alpha_values"],
            "canonical_depth": alpha_cfg["canonical_depth"],
            "voxel_m": phase3_lock["extraction"]["voxel_m"],
            "min_observations": phase3_lock["extraction"]["min_observations"],
            "sor_neighbors": phase3_lock["extraction"]["sor_neighbors"],
            "sor_std_ratio": phase3_lock["extraction"]["sor_std_ratio"],
        },
        "counts": {
            "summary_rows": len(summary_rows),
            "histogram_rows": len(histogram_rows),
            "arm_classification_rows": len(classification_rows),
            "timeline_rows": len(timeline),
            "heightmap_figures": 9,
            "auxiliary_figures": 4,
            "worker_manifests": len(manifests),
        },
        "classification_counts": dict(Counter(row["survival_class"] for row in summary_rows if row["alpha"] == 0.1)),
        "alpha0p5_crosscheck": {
            "jobs_checked": 42,
            "all_count_match": all(manifest["phase3_alpha0p5_crosscheck"]["fused_all_count_match"] for manifest in manifests.values()),
            "minobs_count_match": all(manifest["phase3_alpha0p5_crosscheck"]["minobs_count_match"] for manifest in manifests.values()),
            "sor_count_match": all(manifest["phase3_alpha0p5_crosscheck"]["sor_count_match"] for manifest in manifests.values()),
            "all_payload_match": all(manifest["phase3_alpha0p5_crosscheck"]["all_payload_match"] for manifest in manifests.values()),
            "clean_payload_match": all(manifest["phase3_alpha0p5_crosscheck"]["clean_payload_match"] for manifest in manifests.values()),
        },
        "source_sha256": common.source_hashes(
            [
                *code_sources, *lod2_sources, *timeline_sources,
                args.lock.resolve(), sources["phase2_jobs_csv"], sources["phase2_status_csv"],
                sources["phase3_lock"], sources["p0_fill_npz"], sources["fm_rescore_csv"],
                sources["footprints"], sources["train_manifest"], sources["projection_datum"],
            ]
        ),
        "checkpoint_sha256": {
            run_id: manifest["checkpoint_sha256"] for run_id, manifest in sorted(manifests.items())
        },
        "runtime_extraction_sha256": {
            common.rel(path): common.sha256_file(path) for path in sorted(extraction_paths)
        },
        "output_sha256": common.source_hashes(output_paths),
        "gt_boundary": {
            "render_and_fusion": "GT closed",
            "footprint": "opened after fusion for spatial measurement",
            "lod2": "opened after fusion only for 4907199 reference-band score",
            "als": "not opened",
        },
        "learning_runs_started": 0,
        "status": "measured",
    }
    common.atomic_json(outputs["alpha_run"] / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "status": "measured",
                "summary_rows": len(summary_rows),
                "timeline_rows": len(timeline),
                "classification_counts": manifest["classification_counts"],
                "learning_runs_started": 0,
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=common.DEFAULT_LOCK)
    sub = parser.add_subparsers(dest="command", required=True)
    worker_parser = sub.add_parser("worker")
    worker_parser.add_argument("--shard-index", type=int, required=True)
    worker_parser.add_argument("--shard-count", type=int, default=2)
    sub.add_parser("aggregate")
    args = parser.parse_args()
    if args.command == "worker":
        worker(args)
    else:
        aggregate(args)


if __name__ == "__main__":
    main()

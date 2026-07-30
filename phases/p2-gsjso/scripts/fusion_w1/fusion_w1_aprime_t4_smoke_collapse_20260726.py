#!/usr/bin/env python3
"""Reconstruct the preregistered arm-A roof-opacity trajectory for T4."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch


STEPS = (5000, 10000, 15000, 20000, 25000, 30000)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--initial-opacity", type=float, default=0.25)
    return parser.parse_args()


def checkpoint_row(
    path: Path,
    step: int,
    xy_min: np.ndarray,
    xy_max: np.ndarray,
    roof_z_floor: float,
) -> dict[str, object]:
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    state = checkpoint["model"]["state_dict"]
    means = state["means"].detach().cpu().numpy()
    opacity = torch.sigmoid(state["opacities_raw"].detach()).cpu().numpy()
    proxy = (
        (means[:, 0] >= xy_min[0])
        & (means[:, 0] <= xy_max[0])
        & (means[:, 1] >= xy_min[1])
        & (means[:, 1] <= xy_max[1])
        & (means[:, 2] > roof_z_floor)
    )
    values = opacity[proxy]
    if not len(values):
        raise RuntimeError(f"empty fixed roof geometry proxy at step {step}")
    strategy_state = checkpoint.get("strategy", {}).get("state", {})
    return {
        "iteration": step,
        "source": "full_state_fixed_geometry_proxy",
        "model_gaussians_n": len(means),
        "roof_proxy_n": len(values),
        "opacity_q25": float(np.quantile(values, 0.25)),
        "opacity_median": float(np.median(values)),
        "opacity_q75": float(np.quantile(values, 0.75)),
        "opacity_gt_0p5_n": int((values > 0.5).sum()),
        "cum_prune_candidates": int(strategy_state.get("cum_prune_candidates", 0)),
        "cum_prune_seed_protected": int(
            strategy_state.get("cum_prune_seed_protected", 0)
        ),
        "cum_pruned": int(strategy_state.get("cum_pruned", 0)),
        "checkpoint_path": str(path),
        "checkpoint_sha256": sha256(path),
    }


def main() -> int:
    started = time.monotonic()
    args = parse_args()
    seed = np.load(args.seed)
    xyz = np.asarray(seed["xyz"], dtype=np.float64)
    classification = np.asarray(seed["classification"], dtype=np.uint8)
    class6 = xyz[classification == 6]
    class2 = xyz[classification == 2]
    if not len(class6) or not len(class2):
        raise RuntimeError("T4 requires both class 6 and class 2 in the old arm-A seed")
    xy_min = class6[:, :2].min(axis=0)
    xy_max = class6[:, :2].max(axis=0)
    roof_z_floor = float(class2[:, 2].max())
    init_proxy = (
        (class6[:, 0] >= xy_min[0])
        & (class6[:, 0] <= xy_max[0])
        & (class6[:, 1] >= xy_min[1])
        & (class6[:, 1] <= xy_max[1])
        & (class6[:, 2] > roof_z_floor)
    )
    init_n = int(init_proxy.sum())
    rows: list[dict[str, object]] = [
        {
            "iteration": 0,
            "source": "seed_class6_fixed_geometry_proxy",
            "model_gaussians_n": len(xyz),
            "roof_proxy_n": init_n,
            "opacity_q25": args.initial_opacity,
            "opacity_median": args.initial_opacity,
            "opacity_q75": args.initial_opacity,
            "opacity_gt_0p5_n": int(init_n if args.initial_opacity > 0.5 else 0),
            "cum_prune_candidates": 0,
            "cum_prune_seed_protected": 0,
            "cum_pruned": 0,
            "checkpoint_path": "initial_seed_config",
            "checkpoint_sha256": "",
        }
    ]
    for step in STEPS:
        path = args.checkpoint_dir / f"step_{step:06d}.pt"
        if not path.is_file():
            raise FileNotFoundError(path)
        rows.append(checkpoint_row(path, step, xy_min, xy_max, roof_z_floor))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "arm_A_roof_opacity_trajectory.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)

    x = np.array([int(row["iteration"]) for row in rows])
    median = np.array([float(row["opacity_median"]) for row in rows])
    q25 = np.array([float(row["opacity_q25"]) for row in rows])
    q75 = np.array([float(row["opacity_q75"]) for row in rows])
    fig, ax = plt.subplots(figsize=(8.4, 4.8), constrained_layout=True)
    ax.fill_between(x, q25, q75, color="#4c78a8", alpha=0.18, label="roof proxy Q25–Q75")
    ax.plot(x, median, marker="o", linewidth=2, color="#1f4e79", label="roof proxy median")
    ax.axvline(15000, color="#d62728", linestyle="--", linewidth=1.6, label="phase switch 15k")
    ax.axvspan(15000, 30000, color="#d62728", alpha=0.045, label="prior decay + surface regularization")
    ax.axhline(0.5, color="#555555", linestyle=":", linewidth=1.2, label="opacity 0.5")
    ax.set_yscale("log")
    ax.set_xlim(0, 30000)
    ax.set_xlabel("optimizer iteration")
    ax.set_ylabel("opacity (log scale)")
    ax.set_title("DEBY_LOD2_42364609 — prior arm A roof-opacity trajectory")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(fontsize=8, ncol=2)
    fig_path = args.output_dir / "arm_A_roof_opacity_trajectory.png"
    fig.savefig(fig_path, dpi=180)
    plt.close(fig)

    elapsed = time.monotonic() - started
    receipt = {
        "schema": "jointbuildgs.fusion_w1_aprime.t4_smoke_collapse.v1",
        "task_id": "FUS-W1-APRIME-T4-001",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETED",
        "role": "record_only_not_verdict",
        "building_id": "DEBY_LOD2_42364609",
        "arm": "prior_arm_A",
        "proxy": {
            "xy": "inclusive initial class6 XY bounding box",
            "z": "strictly greater than initial class2 maximum canonical z",
            "xy_min": xy_min.tolist(),
            "xy_max": xy_max.tolist(),
            "roof_z_floor": roof_z_floor,
            "initial_exact_class6_n": len(class6),
            "initial_proxy_n": init_n,
            "limitation": "geometry proxy; checkpoint does not preserve class2/class6 lineage labels",
        },
        "time_limit_minutes": 30,
        "execution_wall_seconds": elapsed,
        "within_time_limit": elapsed <= 1800,
        "inputs": {
            "seed": {"path": str(args.seed), "sha256": sha256(args.seed)},
            "checkpoint_dir": str(args.checkpoint_dir),
        },
        "observations": rows,
        "outputs": {
            "csv": {"path": str(csv_path), "sha256": sha256(csv_path)},
            "figure": {"path": str(fig_path), "sha256": sha256(fig_path)},
        },
        "verdict": None,
    }
    receipt_path = args.output_dir / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

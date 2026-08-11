#!/usr/bin/env python3
"""S0-c: audit the local 4906982 three-arm anomaly (ALS depth-only < control).

Reads the sealed TensorBoard scalars and effective configs of the three arms
(FUSED_VIS_CONF control, ALS_DEPTH_ONLY, E4_ALS_PRIOR_ONLY) and summarizes the
loss/statistics trajectories after the 7000-update branch point, together with
the existing three-arm roofer metrics. Read-only; no training.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

REPO = Path(__file__).resolve().parents[3]
COMMON = REPO / "configs/p2/e4_e6_redesign_s0_v1/s0_v1.yaml"
ARTIFACTS = Path("/artifacts/JointBuildGS")

TAG_PREFIXES = ("loss/", "loss_weight/", "stats/external_als", "seed/surviving", "eval")


def scalar_series(tb_dir: Path) -> dict[str, list[tuple[int, float]]]:
    accumulator = EventAccumulator(str(tb_dir), size_guidance={"scalars": 0})
    accumulator.Reload()
    series: dict[str, list[tuple[int, float]]] = {}
    for tag in accumulator.Tags().get("scalars", []):
        if not any(tag.startswith(prefix) for prefix in TAG_PREFIXES):
            continue
        series[tag] = [(int(event.step), float(event.value)) for event in accumulator.Scalars(tag)]
    return series


def summarize(series: dict[str, list[tuple[int, float]]], branch_step: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for tag, points in sorted(series.items()):
        if not points:
            continue
        post = [value for step, value in points if step > branch_step]
        out[tag] = {
            "first_step": points[0][0],
            "last_step": points[-1][0],
            "value_at_branch": next((value for step, value in points if step >= branch_step), None),
            "final_value": points[-1][1],
            "post_branch_mean": sum(post) / len(post) if post else None,
            "post_branch_max": max(post) if post else None,
        }
    return out


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    common = yaml.safe_load(COMMON.read_text(encoding="utf-8"))
    out_root = Path(common["output_root"]) / "s0c"
    out_root.mkdir(parents=True, exist_ok=True)

    arms = {}
    for arm, relative in common["arms"].items():
        root = ARTIFACTS / relative
        config = json.loads((root / "effective_config.json").read_text(encoding="utf-8"))
        arms[arm] = {
            "relative_root": relative,
            "weights": {
                key: config.get(key)
                for key in (
                    "w_depth", "w_normal", "w_mvc", "w_nc", "w_distort",
                    "w_external_als_depth", "w_external_als_normal",
                    "external_als_huber_delta_m", "max_iter", "seed",
                )
            },
            "scalars": summarize(scalar_series(root / "tb"), branch_step=7000),
        }

    metrics_path = ARTIFACTS / common["three_arm_metrics"]
    three_arm = list(csv.DictReader(metrics_path.open(encoding="utf-8")))

    receipt = {
        "schema": "jointbuildgs.p2.e4_e6_redesign_s0_v1.s0c.v1",
        "task_id": common["task_id"],
        "started_utc": started,
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "branch_step": 7000,
        "arms": arms,
        "three_arm_metrics_rows": three_arm,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    (out_root / "ablation_audit_v1.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    brief = {
        arm: {
            "final_loss_total": data["scalars"].get("loss/total", {}).get("final_value"),
            "final_loss_depth": data["scalars"].get("loss/depth", {}).get("final_value"),
            "final_loss_nc": data["scalars"].get("loss/nc", {}).get("final_value"),
            "final_als_depth": data["scalars"].get("loss/external_als_depth_huber", {}).get("final_value"),
            "final_als_normal": data["scalars"].get("loss/external_als_normal_sign_invariant", {}).get("final_value"),
            "als_valid_px_final": data["scalars"].get("stats/external_als_depth_valid_pixel_count", {}).get("final_value"),
        }
        for arm, data in arms.items()
    }
    print(json.dumps(brief, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

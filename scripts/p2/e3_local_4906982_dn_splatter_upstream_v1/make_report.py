#!/usr/bin/env python3
"""Create the compact, idempotent report for the pinned upstream DN-Splatter run."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    args = parser.parse_args()

    root = args.task_root
    metrics_path = root / "evaluation/metrics.json"
    rows_path = root / "evaluation/checkpoint_metrics.csv"
    metrics = json.loads(metrics_path.read_text())
    aggregates = {int(row["checkpoint_step"]): row for row in metrics["fixed_heldout_aggregates"]}
    geometry = {int(row["checkpoint_step"]): row for row in metrics["gaussian_metrics"]}
    with rows_path.open(newline="") as handle:
        view_rows = list(csv.DictReader(handle))

    def fmt(step: int, key: str, digits: int = 3) -> str:
        return f"{float(aggregates[step][key]):.{digits}f}"

    table = []
    for step in (7000, 12000, 15000, 19999):
        table.append(
            "| {step} | {count:,} | {psnr} | {rmse} | {alpha} | {coverage} | {p99} | {zmax} | {high_z:,} |".format(
                step="20k" if step == 19999 else f"{step // 1000}k",
                count=int(geometry[step]["gaussian_count"]),
                psnr=fmt(step, "rgb_psnr_mean_of_views"),
                rmse=fmt(step, "depth_rmse_valid_m_mean_of_views"),
                alpha=fmt(step, "alpha_mean_mean_of_views"),
                coverage=fmt(step, "alpha_ge_0p1_fraction_mean_of_views"),
                p99=f"{float(geometry[step]['world_z_p99']):.3f}",
                zmax=f"{float(geometry[step]['world_z_max']):.3f}",
                high_z=int(geometry[step]["world_z_gt_650"]),
            )
        )

    step12 = [row for row in view_rows if int(row["checkpoint_step"]) == 12000]
    worst = sorted(step12, key=lambda row: float(row["depth_l1_mean_m"]), reverse=True)[:2]
    worst_lines = [
        f"- `{row['view']}`: depth L1 {float(row['depth_l1_mean_m']):.2f} m, "
        f"absolute residual p50/p95 {float(row['depth_abs_p50_m']):.2f}/{float(row['depth_abs_p95_m']):.2f} m, "
        f"PSNR {float(row['rgb_psnr']):.2f} dB."
        for row in worst
    ]

    report = f"""# Pinned upstream DN-Splatter on DEBY_LOD2_4906982

`scientific_verdict: null`

## Execution

- One upstream DN-Splatter training run (`R1`) completed all 20,000 iterations.
- Upstream commit: `97588b4290128ce7ba6fdbfaac3020b42b17de4c` with no source edits.
- Fixed data: 55 views (47 train / 8 held-out), exact sparse SfM initialization, raw positive-finite COLMAP geometric camera-Z depth.
- DN method controls include EdgeAwareLogL1 depth, depth-derived normal supervision/TV, DN minimum-scale regularization, 2D Gaussians, upstream densification and culling.
- No ALS, LoD2 Z/roof/semantic prior, MVC, confidence mask, or fusion-support mask entered training.

## Fixed held-out measurements

All rows use the same eight held-out views. DN expected depth is compared to raw COLMAP camera-Z depth.

| checkpoint | Gaussians | RGB PSNR dB | depth RMSE m | mean alpha | alpha >=0.1 coverage | world Z p99 m | world Z max m | Z>650 m |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(table)}

The best measured checkpoint is 12k. The two largest 12k depth failures are both oblique held-out views:

{chr(10).join(worst_lines)}

## Qualitative observations

- At 12k, several near-nadir views reconstruct recognizable roofs, but coverage remains patchy and the two oblique views contain large dark/incorrect-depth regions.
- From 15k to 20k, Gaussian count falls from 1,415,032 to 712,233 and alpha>=0.1 coverage falls from 0.566 to 0.281. The effective standard-method config has `continue_cull_post_densification: true` and `cull_alpha_thresh: 0.1`; the training log records repeated culling through 20k. The 20k panels visibly lose large near-nadir regions.
- The 20k reduction in `Z>650 m` (669 at 15k to 226) occurs together with this coverage collapse, so it is not evidence of a cleaner usable surface by itself.
- A high-Z tail remains at every checkpoint; 12k has 576 Gaussians above 650 m and world-Z max 664.837 m.

## What this run does and does not establish

- It establishes that the complete, pinned DN-Splatter pipeline can train to completion on this dataset; earlier setup failures were Docker/dependency/runtime-cache failures.
- It establishes two observed failure modes: large oblique raw-depth disagreement already at the best 12k checkpoint, and strong post-15k coverage loss while upstream culling continues.
- It does **not** establish that depth supervision alone caused the poor result. Full DN changes depth loss, depth-derived normal losses, scale regularization, densification, and culling together, and this task has no same-method no-depth control.
- It is not comparable to the earlier `DN_DEPTH` transplant as a single loss ablation: that run kept the JointBuildGS trainer and inserted only an EdgeAwareLogL1 expected-depth term; this run uses the complete upstream DN model and refinement policy.
- Fusion and Roofer were not executed in this upstream adapter pass. No downstream Roofer claim is made from render/alpha/high-Z measurements.

## Next controlled measurement

Stay within DN-Splatter. The directly observed endpoint confound should be isolated first with one rerun that changes only `continue_cull_post_densification: True -> False` (or equivalently freezes culling at the pre-registered 15k boundary). This is not a move away from the reference family: upstream's separate `dn-splatter-big` preset also disables post-densification culling, although it additionally changes the alpha threshold and therefore must not be adopted wholesale for a single-variable test. If the question is specifically whether depth itself is harmful, that is a separate single-variable experiment: the same pinned DN pipeline with depth and depth-derived normal supervision disabled, while refinement/culling remain identical. Neither follow-up is executed here.

## Representative images

- `evaluation/representative_images/step_012000_heldout_contact.png` — best measured checkpoint.
- `evaluation/representative_images/step_019999_heldout_contact.png` — final checkpoint after coverage collapse.

Large logs: `logs/R1.log`, `logs/evaluate.log`.
"""
    (root / "comparison.md").write_text(report)

    # Required task-root aliases retain the detailed evaluation namespace as source.
    shutil.copy2(metrics_path, root / "metrics.json")
    shutil.copy2(rows_path, root / "checkpoint_metrics.csv")

    summary = {
        "schema": "jointbuildgs.p2.e3_local_4906982_dn_splatter_upstream_v1.run_summary.v1",
        "training_runs_started": 1,
        "training_runs_completed": 1,
        "completed_iterations": 20000,
        "best_measured_checkpoint": 12000,
        "downstream_fusion_executed": False,
        "roofer_executed": False,
        "scientific_verdict": None,
    }
    (root / "run_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    issue = """
## 2026-08-09 formal R1 and fixed-view evaluation

- Status: complete. One formal upstream DN-Splatter run completed 20,000
  iterations; 7k, 12k, 15k, and final checkpoints were evaluated on the same
  eight held-out views.
- The best measured checkpoint was 12k. Continued upstream culling after 15k
  coincided with Gaussian count and alpha-coverage collapse by 20k.
- Two oblique held-out views retained very large raw-depth residuals at 12k.
- These observations do not isolate depth as the cause because no same-method
  no-depth control was run.
- One accidental host `python3` invocation intentionally exited immediately and
  performed no project computation or artifact mutation. All dataset, training,
  evaluation, and report computation used Docker.
- scientific_verdict: null
"""
    issues_path = root / "issues.md"
    existing = issues_path.read_text()
    if "## 2026-08-09 formal R1 and fixed-view evaluation" not in existing:
        issues_path.write_text(existing.rstrip() + "\n" + issue)

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""FC-3 diagnosis: read TB of smoke run, report eval PSNR trajectory + decision.

Usage (after FC-3 finishes):
    python scripts/phase2_synthesis/fc3_diagnose.py

Prints:
  - train PSNR trajectory
  - eval PSNR trajectory
  - loss components over time
  - train/eval gap
  - decision (GO / marginal / STOP) based on the scenarios in prior message.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from tensorboard.backend.event_processing import event_accumulator

ROOT = Path(__file__).resolve().parents[2]
TB = ROOT / "results/phase2_synthesis/smoke/tb"


def main():
    if not TB.exists():
        print(f"[fc3] {TB} not found — smoke not started or crashed"); return
    ea = event_accumulator.EventAccumulator(str(TB))
    ea.Reload()

    def get(tag):
        try:
            return [(e.step, e.value) for e in ea.Scalars(tag)]
        except KeyError:
            return []

    train_psnr = get("metric/psnr_train")
    eval_psnr = get("eval/psnr")
    eval_depth = get("eval/depth_mae")
    eval_normal = get("eval/normal_cos")
    loss_photo = get("loss/photo")
    loss_depth = get("loss/depth")
    loss_normal = get("loss/normal")
    loss_sem = get("loss/sem")
    n_prim = get("stats/n_primitives")

    def last(s, k=5):
        return [(s[i][0], round(s[i][1], 3)) for i in range(max(0, len(s) - k), len(s))]

    print("=" * 70)
    print("FC-3 Smoke Diagnosis")
    print("=" * 70)
    print(f"Train PSNR (last 5): {last(train_psnr)}")
    print(f"Eval  PSNR (all)   : {[(s, round(v, 3)) for s, v in eval_psnr]}")
    print(f"Eval  Depth MAE    : {[(s, round(v, 3)) for s, v in eval_depth]}")
    print(f"Eval  Normal cos   : {[(s, round(v, 3)) for s, v in eval_normal]}")
    print(f"N primitives (last): {last(n_prim, 3)}")
    print()
    print(f"Loss/photo  last 3: {last(loss_photo, 3)}")
    print(f"Loss/depth  last 3: {last(loss_depth, 3)}")
    print(f"Loss/normal last 3: {last(loss_normal, 3)}")
    print(f"Loss/sem    last 3: {last(loss_sem, 3)}")
    print()

    # Decision logic
    final_eval = eval_psnr[-1][1] if eval_psnr else None
    final_train = train_psnr[-1][1] if train_psnr else None
    gap = (final_train - final_eval) if (final_train and final_eval) else None

    # Multi-metric decision (PSNR alone is insufficient)
    print("DECISION (multi-metric)")
    print("-" * 70)
    if final_eval is None:
        print("  NO-GO: no eval data recorded (crashed?)"); return

    final_depth_mae = eval_depth[-1][1] if eval_depth else None
    final_normal_cos = eval_normal[-1][1] if eval_normal else None
    final_n = n_prim[-1][1] if n_prim else None
    last_photo = loss_photo[-1][1] if loss_photo else None
    last_depth_l = loss_depth[-1][1] if loss_depth else None

    # Check each health criterion
    checks = []
    checks.append(("eval PSNR ≥ 20",           final_eval >= 20,                  f"{final_eval:.2f}"))
    checks.append(("eval depth MAE < 2 m",     (final_depth_mae is None) or (final_depth_mae < 2.0),
                   f"{final_depth_mae:.3f} m" if final_depth_mae is not None else "—"))
    checks.append(("eval normal cos > 0.7",    (final_normal_cos is None) or (final_normal_cos > 0.7),
                   f"{final_normal_cos:.3f}" if final_normal_cos is not None else "—"))
    checks.append(("train-eval gap < 10 dB",   (gap is None) or (gap < 10),
                   f"{gap:.2f} dB" if gap is not None else "—"))
    checks.append(("N primitives 200k-2M",     (final_n is None) or (200_000 <= final_n <= 2_000_000),
                   f"{int(final_n):,}" if final_n is not None else "—"))
    checks.append(("loss/photo finite",        (last_photo is None) or (last_photo == last_photo and last_photo < 10),
                   f"{last_photo:.4f}" if last_photo is not None else "—"))
    checks.append(("loss/depth finite",        (last_depth_l is None) or (last_depth_l == last_depth_l and last_depth_l < 100),
                   f"{last_depth_l:.4f}" if last_depth_l is not None else "—"))

    for name, ok, val in checks:
        mark = "✓" if ok else "✗"
        print(f"  [{mark}] {name:32s} = {val}")
    passes = sum(1 for _, ok, _ in checks if ok)
    print()
    print(f"  {passes}/{len(checks)} checks pass")

    if passes == len(checks):
        print("  -> GO: all health criteria met. Launch 4-condition full training.")
    elif passes >= len(checks) - 2:
        print("  -> CONDITIONAL GO: minor concerns. Review failed checks, proceed with caveat.")
    elif passes >= 3:
        print("  -> MARGINAL: multiple issues. Recommend param adjustment before full training.")
        print("     Common fixes:")
        print("       - eval PSNR low with healthy train: SH degree 3 → 1, refine_stop 10k → 7k")
        print("       - depth MAE high: w_depth 0.5 → 0.1 (scale mismatch)")
        print("       - normal cos random: check normal_mask, verify normal GT frame")
        print("       - N primitives exploding: grow_grad2d 5e-4 → 2e-4")
    else:
        print("  -> STOP: fundamental issue. Diagnose before re-running.")
        print("     Inspect: train render vs eval render, per-loss trajectories, bbox of primitives.")


if __name__ == "__main__":
    main()

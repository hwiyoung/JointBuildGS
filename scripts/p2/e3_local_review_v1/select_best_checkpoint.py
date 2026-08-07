#!/usr/bin/env python3
"""Select one checkpoint using only the locked local validation mean PSNR."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from tensorboard.backend.event_processing.event_accumulator import EventAccumulator


SCHEMA = "jointbuildgs.p2.e3_local_4906982.checkpoint_selection.v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--view-roles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_root.resolve()
    roles = json.loads(args.view_roles.read_text(encoding="utf-8"))
    if len(roles["eval_views"]) != 8 or len(roles["train_views"]) != 47:
        raise RuntimeError("locked 47/8 train/validation membership drifted")
    scalar_events = sorted(
        path for path in (run / "tb").glob("events.out.tfevents.*")
        if ".qualitative" not in path.name
    )
    if len(scalar_events) != 1:
        raise RuntimeError(f"expected one scalar event file, found {len(scalar_events)}")
    events = EventAccumulator(str(scalar_events[0]), size_guidance={"scalars": 0})
    events.Reload()
    scores = events.Scalars("eval/psnr")
    if not scores:
        raise RuntimeError("eval/psnr is absent")
    rows = []
    final_step = max(int(event.step) for event in scores)
    for event in scores:
        step = int(event.step)
        checkpoint = run / "ckpt" / f"step_{step:06d}.pt"
        if not checkpoint.is_file():
            if step == final_step and (run / "ckpt/final.pt").is_file():
                checkpoint = run / "ckpt/final.pt"
            else:
                raise FileNotFoundError(checkpoint)
        rows.append({
            "step": step,
            "validation_mean_psnr_db": float(event.value),
            "checkpoint": str(checkpoint),
            "checkpoint_sha256": sha256(checkpoint),
        })
    selected = max(rows, key=lambda row: (row["validation_mean_psnr_db"], -row["step"]))
    payload = {
        "schema": SCHEMA,
        "selection_rule": "MAX_LOCKED_VALIDATION_8_VIEW_MEAN_PSNR_TIE_EARLIEST_STEP",
        "metric": "eval/psnr",
        "optimization": "maximize",
        "validation_view_count": 8,
        "validation_membership": roles["eval_views"],
        "candidate_count": len(rows),
        "candidates": rows,
        "selected": selected,
        "downstream_metrics_used_for_selection": False,
        "scientific_verdict": None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps(selected, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

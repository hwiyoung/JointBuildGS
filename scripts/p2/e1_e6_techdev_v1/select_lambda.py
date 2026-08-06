from __future__ import annotations

import argparse
import json
from pathlib import Path

from tensorboard.backend.event_processing.event_accumulator import EventAccumulator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid-root", type=Path, required=True)
    parser.add_argument("--prep-root", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for value in (0.2, 0.5, 1.0):
        run = args.grid_root / str(value).replace(".", "p")
        events = sorted((run / "tb").glob("events.out.tfevents.*"))
        if not events:
            raise FileNotFoundError(f"missing TensorBoard events: {run}")
        accumulator = EventAccumulator(str(events[-1])).Reload()
        scalars = accumulator.Scalars("eval/depth_mae")
        if not scalars:
            raise RuntimeError(f"missing eval/depth_mae: {run}")
        final = max(scalars, key=lambda item: item.step)
        rows.append({"lambda_L": value, "held_out_depth_mae_m": float(final.value), "iteration": int(final.step)})
    selected = min(rows, key=lambda row: (row["held_out_depth_mae_m"], row["lambda_L"]))
    payload = {
        "schema": "jointbuildgs.p2.e1_e6.lambda_grid.v1",
        "iterations": 7000,
        "criterion": "MIN_HELD_OUT_MVS_DEPTH_MAE",
        "rows": rows,
        "selected_lambda_L": selected["lambda_L"],
        "scientific_verdict": None,
    }
    args.prep_root.mkdir(parents=True, exist_ok=True)
    (args.prep_root / "lambda_selection.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    table = [
        "# E5 lambda grid",
        "",
        "| lambda_L | held-out depth MAE (m) | iteration |",
        "|---:|---:|---:|",
        *(f"| {row['lambda_L']} | {row['held_out_depth_mae_m']:.6f} | {row['iteration']} |" for row in rows),
        "",
        f"Selected: **{selected['lambda_L']}** by minimum held-out MVS depth MAE.",
        "",
        "This is a non-confirmatory technical selection; `scientific_verdict` remains null.",
    ]
    (args.prep_root / "lambda_grid.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Measure checkpoint geometry/opacity without rendering or retraining."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import torch


SCHEMA = "jointbuildgs.p2.e3_local_4906982.checkpoint_geometry_audit.v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def quantiles(values: np.ndarray) -> dict[str, float]:
    names = ("minimum", "p01", "p10", "median", "p90", "p99", "maximum")
    points = (0.0, 0.01, 0.10, 0.50, 0.90, 0.99, 1.0)
    return {name: float(value) for name, value in zip(names, np.quantile(values, points))}


def audit(path: Path, world_shift_z: float, high_z: float, alpha: float) -> dict[str, Any]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    state = payload["state_dict"]
    z = state["means"][:, 2].detach().numpy().astype(np.float64) + world_shift_z
    opacity = torch.sigmoid(state["opacities_raw"]).reshape(-1).detach().numpy().astype(np.float64)
    opaque = opacity >= alpha
    high = z > high_z
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "step": int(payload.get("step", payload.get("iteration", payload.get("it", -1)))),
        "gaussian_count": int(len(z)),
        "world_z_m": quantiles(z),
        "opacity": quantiles(opacity),
        "alpha_threshold": alpha,
        "opaque_count": int(np.count_nonzero(opaque)),
        "high_z_threshold_m": high_z,
        "high_z_count": int(np.count_nonzero(high)),
        "high_z_opaque_count": int(np.count_nonzero(high & opaque)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--world-shift-z", type=float, default=604.0)
    parser.add_argument("--high-z", type=float, default=650.0)
    parser.add_argument("--alpha", type=float, default=0.5)
    args = parser.parse_args()
    rows = [audit(path.resolve(), args.world_shift_z, args.high_z, args.alpha) for path in args.checkpoint]
    result = {
        "schema": SCHEMA,
        "checkpoints": rows,
        "scientific_verdict": None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps(rows, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

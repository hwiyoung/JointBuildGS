#!/usr/bin/env python3
"""Compare point-cloud geometry from controlled depth-fusion arms."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import open3d as o3d


def summarize(run: Path, high_z: float) -> dict:
    receipt = json.loads((run / "pointcloud/extraction_receipt.json").read_text(encoding="utf-8"))
    cloud = o3d.io.read_point_cloud(str(run / "pointcloud/depth_fusion.ply"))
    xyz = np.asarray(cloud.points, dtype=np.float64)
    return {
        "run": run.name,
        "receipt_schema": receipt["schema"],
        "checkpoint_sha256": receipt["checkpoint"]["sha256"],
        "point_count": int(len(xyz)),
        "world_z_m": {
            name: float(value)
            for name, value in zip(
                ("minimum", "p01", "p10", "median", "p90", "p99", "maximum"),
                np.quantile(xyz[:, 2], (0, 0.01, 0.10, 0.50, 0.90, 0.99, 1)),
            )
        },
        "high_z_threshold_m": high_z,
        "high_z_point_count": int(np.count_nonzero(xyz[:, 2] > high_z)),
        "integrated_pixel_count": int(receipt["integrated_pixel_count"]),
        "mesh_polygon_count": int(receipt["mesh_polygon_count"]),
        "mesh_surface_area_m2": float(receipt["mesh_surface_area_m2"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--high-z", type=float, default=650.0)
    args = parser.parse_args()
    rows = [summarize(run.resolve(), args.high_z) for run in args.run]
    if len({row["checkpoint_sha256"] for row in rows}) != 1:
        raise RuntimeError("fusion arms do not share one exact checkpoint")
    payload = {
        "schema": "jointbuildgs.p2.e3_local_4906982.fusion_comparison.v1",
        "same_checkpoint": True,
        "arms": rows,
        "scientific_verdict": None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

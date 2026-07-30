#!/usr/bin/env python3
"""Prepare the sparse COLMAP seed as a GS-local PLY for E5.

The native COLMAP points3D.txt is already in the GS-local frame. This helper
applies the same AOI crop and local z band used by dense/acmp seed prep, then
writes a simple ASCII PLY consumed by src/stage2/pointcloud_io.py.
"""
from __future__ import annotations

import argparse
from pathlib import Path


REPO = Path("/workspace/JointBuildGS")
DEFAULT_IN = REPO / "phases/p0-audit/data/work/mvs/openmvs/colmap_txt/sparse/points3D.txt"
DEFAULT_OUT = REPO / "results/tum_transfer/mob_analysis/seed/seed_sparse.ply"
WORLD_SHIFT = (690953.0, 5336071.0, 604.0)
AOI_UTM = (690766.0, 691180.0, 5335839.0, 5336379.0)
Z_BAND = (-65.0, 30.0)


def write_ply(path: Path, points: list[tuple[float, float, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {len(points)}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("end_header\n")
        for x, y, z in points:
            f.write(f"{x:.6f} {y:.6f} {z:.6f}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--points3d", default=str(DEFAULT_IN))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    x0 = AOI_UTM[0] - WORLD_SHIFT[0]
    x1 = AOI_UTM[1] - WORLD_SHIFT[0]
    y0 = AOI_UTM[2] - WORLD_SHIFT[1]
    y1 = AOI_UTM[3] - WORLD_SHIFT[1]
    z0, z1 = Z_BAND

    total = 0
    kept: list[tuple[float, float, float]] = []
    with Path(args.points3d).open() as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            total += 1
            parts = line.split()
            if len(parts) < 4:
                continue
            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            if x0 <= x <= x1 and y0 <= y <= y1 and z0 <= z <= z1:
                kept.append((x, y, z))

    write_ply(Path(args.out), kept)
    print(f"[seed-prep:sparse] input={args.points3d}")
    print(f"[seed-prep:sparse] total={total} kept={len(kept)} z_band=[{z0},{z1}] -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

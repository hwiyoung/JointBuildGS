#!/usr/bin/env python3
"""Sample the ARRGS S5 B-rep into geometry_eval-compatible crops.

For each finished real run: sample roof/wall faces at ~25 pts/m² (class 6) and
ground faces at ~8 pts/m² (class 2) → viewer-local binary PLY named
B{idx}_{sid}.points.ply in an ARRGS arm dir, so the sealed journal1 evaluator
scores it byte-comparable to E1/E2/E7/E8/GS rows.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import numpy as np

BASE = Path("/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1")
if not BASE.exists():
    BASE = Path("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/"
                "phase-payloads/p2/arrgs_v1")


def write_ply(path, xyz, cls):
    n = len(xyz)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {n}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar classification\nend_header\n")
    with open(path, "wb") as f:
        f.write(header.encode())
        rec = np.zeros(n, dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("c", "u1")])
        rec["x"], rec["y"], rec["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
        rec["c"] = cls
        f.write(rec.tobytes())


def sample_obj(obj_path, density_roofwall=25.0, density_ground=8.0, seed=0,
               density_wall=8.0):
    verts, tris = [], []
    cls = "roof"
    for ln in open(obj_path):
        t = ln.split()
        if not t:
            continue
        if t[0] == "v":
            verts.append([float(t[1]), float(t[2]), float(t[3])])
        elif t[0] == "g":
            cls = t[1]
        elif t[0] == "f":
            tris.append((cls, [int(x) - 1 for x in t[1:4]]))
    verts = np.asarray(verts)
    rng = np.random.default_rng(seed)
    pts, cs = [], []
    for cls, tri in tris:
        a, b, c = verts[tri[0]], verts[tri[1]], verts[tri[2]]
        area = 0.5 * np.linalg.norm(np.cross(b - a, c - a))
        dens = (density_ground if cls == "ground"
                else density_wall if cls == "wall" else density_roofwall)
        k = max(1, int(area * dens))
        r1 = np.sqrt(rng.random(k))
        r2 = rng.random(k)
        p = (1 - r1)[:, None] * a + (r1 * (1 - r2))[:, None] * b + (r1 * r2)[:, None] * c
        pts.append(p)
        cs.append(np.full(k, 2 if cls == "ground" else 6, dtype=np.uint8))
    return np.concatenate(pts), np.concatenate(cs)


def main():
    arm_dir = BASE / "eval_arm_ARRGS"
    arm_dir.mkdir(exist_ok=True)
    rows = []
    for exp in ("X1", "X2", "X3"):
        root = BASE / f"P2-ARRGS-{exp}-v1/runs"
        if not root.is_dir():
            continue
        for run in sorted(root.iterdir()):
            obj = run / "s5_brep.obj"
            rj = run / "run.json"
            if not obj.is_file() or not rj.is_file():
                continue
            cfg = json.load(open(rj))["config"]
            bkey = cfg["scene"]["bkey"]
            dx = cfg["scene"].get("inject_delta_east_m", 0)
            dz = cfg["scene"].get("inject_delta_z_m", 0)
            xyz, cls = sample_obj(obj)
            if dx == 0 and dz == 0:
                out = arm_dir / f"{bkey}.points.ply"  # clean runs -> main arm
            else:
                d = BASE / f"eval_arm_ARRGS_dx{int(dx*100):03d}_dz{int(dz*100):03d}"
                d.mkdir(exist_ok=True)
                out = d / f"{bkey}.points.ply"
            write_ply(out, xyz, cls)
            rows.append({"run": f"{exp}/{run.name}", "bkey": bkey,
                         "points": int(len(xyz)), "out": str(out)})
            print(f"[export] {exp}/{run.name} -> {out.name} ({len(xyz)} pts)")
    json.dump(rows, open(BASE / "eval_export_index.json", "w"), indent=1)


if __name__ == "__main__":
    main()

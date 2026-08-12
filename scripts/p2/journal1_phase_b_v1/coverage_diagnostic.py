#!/usr/bin/env python3
"""Per-building E1/E2 coverage diagnostic over the existing LoD2 roof polygon.

For every Phase-B candidate building (viewer review_manifest.json) and each arm
crop (E1 current UAS LiDAR, E2 current-image MVS), rasterize the LoD2 roof
polygon XY into cells and measure how much of that area the arm's points cover.
This separates "no current data here" (acquisition gap) from "current data
disagrees here" (change / abstraction signal), so low Phase-A completeness is
not mistaken for change by itself.

Per building x arm:
  n_pts            total crop points
  any_xy           share of roof cells with any-class points
  cls6_xy          share of roof cells with building-class (6) points
  groundonly_xy    share of roof cells with ground-class (2) but no class-6
  dz_med_m         median (cell median class-6 z) - (LoD2 ring plane z)
  above_ridge_share share of class-6 points higher than ring zmax + above_ridge_m
                   (vegetation-misclassification signal)
  veg_cell_share   share of class-6 roof cells whose intra-cell z IQR exceeds
                   veg_ziqr_m (canopy is thick, roofs are thin surfaces)

Building-level gates (advisory only, thresholds from config):
  gate_any_070 / gate_cls6_070 — True when max(E1,E2) coverage >= gate_min_cover.

Diagnostic output is evaluation-support metadata; it makes no scientific
verdict and never feeds training or parameter selection.

Run inside the project container (same mounts as build_label_review_viewer.py).
"""

import argparse
import hashlib
import json
import math
import platform
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from shapely.prepared import prep

PLY_DT = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                   ("r", "u1"), ("g", "u1"), ("b", "u1"), ("c", "u1")])
EXPECTED_PROPS = ["float x", "float y", "float z", "uchar red", "uchar green",
                  "uchar blue", "uchar classification"]


def read_crop(path):
    """Structured array of the sealed crop PLY (fixed 16-byte layout)."""
    raw = Path(path).read_bytes()
    hdr_end = raw.index(b"end_header\n") + len(b"end_header\n")
    header = raw[:hdr_end].decode("ascii", "replace").split("\n")
    props = [l.split(" ", 1)[1] for l in header if l.startswith("property ")]
    if props != EXPECTED_PROPS:
        raise ValueError(f"{path}: unexpected PLY layout {props}")
    n = int(next(l for l in header if l.startswith("element vertex")).split()[2])
    return np.frombuffer(raw, dtype=PLY_DT, count=n, offset=hdr_end)


def ring_planes(rings):
    """[(xy Polygon, unit normal, point-on-plane, tilt_deg)] per exterior ring."""
    out = []
    for r in rings:
        v = np.asarray(r, dtype=np.float64)
        if len(v) < 4:
            continue
        n = np.zeros(3)
        for i in range(len(v) - 1):
            n += np.cross(v[i], v[i + 1])
        ln = np.linalg.norm(n)
        if ln < 1e-9:
            continue
        n /= ln
        if n[2] < 0:
            n = -n
        try:
            poly = Polygon(v[:, :2]).buffer(0)
        except Exception:
            continue
        if poly.is_empty:
            continue
        out.append((poly, n, v[0], math.degrees(math.acos(min(1.0, abs(n[2]))))))
    return out


def roof_cells(planes, cell):
    """Cell-center list covering the union of ring polygons."""
    if not planes:
        return None, []
    roof = unary_union([p for p, *_ in planes])
    pre = prep(roof)
    minx, miny, maxx, maxy = roof.bounds
    xs = np.arange(math.floor(minx / cell) * cell + cell / 2, maxx, cell)
    ys = np.arange(math.floor(miny / cell) * cell + cell / 2, maxy, cell)
    return roof, [(x, y) for x in xs for y in ys if pre.contains(Point(x, y))]


def plane_z_at(planes, x, y):
    for poly, n, p0, _tilt in planes:
        if abs(n[2]) > 0.1 and poly.contains(Point(x, y)):
            return p0[2] - (n[0] * (x - p0[0]) + n[1] * (y - p0[1])) / n[2]
    return None


def cell_keys(xy, cell):
    return set(zip(np.floor(xy[:, 0] / cell).astype(np.int64),
                   np.floor(xy[:, 1] / cell).astype(np.int64)))


def arm_stats(pts, planes, centers, cell, cfg):
    keys = [(int(math.floor(x / cell)), int(math.floor(y / cell))) for x, y in centers]
    n_cells = len(keys)
    xy = np.stack([pts["x"], pts["y"]], axis=1) if len(pts) else np.zeros((0, 2))
    m6 = pts["c"] == 6
    m2 = pts["c"] == 2
    k_any = cell_keys(xy, cell) if len(pts) else set()
    k6 = cell_keys(xy[m6], cell) if m6.any() else set()
    k2 = cell_keys(xy[m2], cell) if m2.any() else set()
    stats = {
        "n_pts": int(len(pts)),
        "any_xy": round(sum(1 for k in keys if k in k_any) / n_cells, 3),
        "cls6_xy": round(sum(1 for k in keys if k in k6) / n_cells, 3),
        "groundonly_xy": round(sum(1 for k in keys if k in k2 and k not in k6) / n_cells, 3),
    }
    # class-6 z behaviour over the roof polygon
    dzs, veg_cells, n6_cells = [], 0, 0
    if m6.any():
        p6 = pts[m6]
        by_cell = defaultdict(list)
        for (i, j), z in zip(map(tuple, np.stack(
                [np.floor(p6["x"] / cell), np.floor(p6["y"] / cell)], 1).astype(np.int64)),
                p6["z"]):
            by_cell[(i, j)].append(z)
        for k, (cx, cy) in zip(keys, centers):
            zs = by_cell.get(k)
            if not zs:
                continue
            n6_cells += 1
            zs = np.asarray(zs)
            if len(zs) >= 4 and np.percentile(zs, 75) - np.percentile(zs, 25) > cfg["veg_ziqr_m"]:
                veg_cells += 1
            pz = plane_z_at(planes, cx, cy)
            if pz is not None:
                dzs.append(float(np.median(zs)) - pz)
    stats["dz_med_m"] = round(float(np.median(dzs)), 2) if dzs else None
    stats["veg_cell_share"] = round(veg_cells / n6_cells, 3) if n6_cells else None
    return stats


def above_ridge_share(pts, rings, above_m):
    m6 = pts["c"] == 6
    if not m6.any():
        return None
    zmax = max(p[2] for r in rings for p in r)
    return round(float((pts["z"][m6] > zmax + above_m).mean()), 3)


def git_commit(repo_dir):
    try:
        return subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="configs/p2/journal1_phase_b_v1/run_v1.json")
    args = ap.parse_args()
    cfg_all = json.load(open(args.config))
    cfg = cfg_all["coverage_diagnostic"]
    viewer = Path(cfg_all["out_dir"])
    manifest = json.load(open(viewer / "review_manifest.json"))

    rows = []
    for b in manifest["buildings"]:
        planes = ring_planes(b["lod2_rings"])
        _roof, centers = roof_cells(planes, cfg["cell_m"])
        if not centers:
            rows.append({"stable_id": b["stable_id"], "bkey": b["bkey"],
                         "tier": b["tier"], "error": "NO_ROOF_POLYGON"})
            continue
        row = {"stable_id": b["stable_id"], "bkey": b["bkey"], "tier": b["tier"],
               "n_roof_cells": len(centers),
               "phase_a": {"completeness_0p5": b["metrics"]["e1_lod2_completeness_0p5"],
                            "acc_median_m": b["metrics"]["e1_lod2_acc_median_m"],
                            "n_e1_roof_pts": b["metrics"]["n_e1_roof_pts"]}}
        for arm in ("E1", "E2"):
            rel = b["assets"].get(arm)
            if not rel:
                row[arm] = None
                continue
            pts = read_crop(viewer / rel)
            st = arm_stats(pts, planes, centers, cfg["cell_m"], cfg)
            st["above_ridge_share"] = above_ridge_share(pts, b["lod2_rings"],
                                                        cfg["above_ridge_m"])
            row[arm] = st
        cov_any = [row[a]["any_xy"] for a in ("E1", "E2") if row.get(a)]
        cov_c6 = [row[a]["cls6_xy"] for a in ("E1", "E2") if row.get(a)]
        row["gate_any_070"] = bool(cov_any and max(cov_any) >= cfg["gate_min_cover"])
        row["gate_cls6_070"] = bool(cov_c6 and max(cov_c6) >= cfg["gate_min_cover"])
        rows.append(row)

    out_path = Path(cfg["out"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    generated_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "schema": "journal1_phase_b_coverage_diag_v1",
        "task_id": cfg_all["task_id"],
        "status": cfg_all["status"],
        "scientific_verdict": None,
        "generated_utc": generated_utc,
        "params": {k: cfg[k] for k in ("cell_m", "gate_min_cover", "veg_ziqr_m",
                                        "above_ridge_m")},
        "definition": {
            "any_xy": "share of LoD2 roof-polygon 0.5m cells containing any-class arm points",
            "cls6_xy": "same with building-class (6) points only",
            "groundonly_xy": "cells with ground-class (2) but no class-6 (demolition signal)",
            "dz_med_m": "median class-6 cell z minus LoD2 ring plane z (float/abstraction signal)",
            "above_ridge_share": "class-6 points above ring zmax + above_ridge_m (vegetation misclassification signal)",
            "veg_cell_share": "class-6 cells with z IQR > veg_ziqr_m (canopy thickness signal)",
            "gate_*_070": "advisory evaluability gate: max(E1,E2) coverage >= gate_min_cover",
        },
        "source_manifest_sha256": hashlib.sha256(
            (viewer / "review_manifest.json").read_bytes()).hexdigest(),
        "git_commit": git_commit(Path(__file__).resolve().parents[3]),
        "python": platform.python_version(),
        "buildings": rows,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))

    ok = [r for r in rows if "error" not in r]
    fail_any = [r for r in ok if not r["gate_any_070"]]
    fail_c6 = [r for r in ok if not r["gate_cls6_070"]]
    print(json.dumps({
        "buildings": len(rows),
        "gate_any_070_fail": len(fail_any),
        "gate_cls6_070_fail": len(fail_c6),
        "gate_any_fail_bkeys": sorted(r["bkey"] for r in fail_any),
        "out": str(out_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Rasterize the sealed full-scene E1 (current UAS LiDAR) and E2 (current-image
MVS) classified scenes into 0.5 m XY occupancy overlays for the Phase-B map.

The overview map's per-building coverage numbers say how much of each LoD2 roof
polygon a sensor covers; these overlays show the sensors' actual acquisition
extent, so an empty building can be read directly as "outside the data" versus
"inside the data but mismatching". All classes are kept — the overlays encode
acquisition extent, not classification.

Outputs (into the viewer payload, same 8881 server):
  overlay_E1.png / overlay_E2.png  per-sensor occupancy (density-scaled alpha)
  overlay_BOTH.png                 composite: E1-only / E2-only / both colors
  overlay_bounds.json              viewer-local bounds + cell size for the map

Run inside the project container (same mounts as build_label_review_viewer.py).
"""

import argparse
import json
import platform
import struct
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_label_review_viewer import git_commit  # noqa: E402


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def bin_counts(xs, ys, bounds, cell):
    """uint32 count grid (rows = north to south) for viewer-local points."""
    minx, miny, maxx, maxy = bounds
    w = int(np.ceil((maxx - minx) / cell))
    h = int(np.ceil((maxy - miny) / cell))
    ix = np.floor((xs - minx) / cell).astype(np.int64)
    iy = np.floor((maxy - ys) / cell).astype(np.int64)  # row 0 = max Y (north up)
    m = (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h)
    grid = np.zeros((h, w), dtype=np.uint32)
    np.add.at(grid, (iy[m], ix[m]), 1)
    return grid


def density_alpha(counts, knee):
    """0..255 alpha from point counts: visible when sparse, saturating at knee."""
    a = np.zeros(counts.shape, dtype=np.float32)
    nz = counts > 0
    a[nz] = 0.25 + 0.65 * np.minimum(1.0, np.log1p(counts[nz]) / np.log1p(knee))
    return (a * 255).astype(np.uint8)


def rgba_single(counts, color, knee):
    h, w = counts.shape
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., 0], out[..., 1], out[..., 2] = color
    out[..., 3] = density_alpha(counts, knee)
    return out


def rgba_both(c1, c2, col1, col2, col_both, knee):
    h, w = c1.shape
    out = np.zeros((h, w, 4), dtype=np.uint8)
    only1 = (c1 > 0) & (c2 == 0)
    only2 = (c2 > 0) & (c1 == 0)
    both = (c1 > 0) & (c2 > 0)
    for m, col in ((only1, col1), (only2, col2), (both, col_both)):
        out[m, 0], out[m, 1], out[m, 2] = col
    out[..., 3] = density_alpha(np.maximum(c1, c2), knee)
    return out


def write_png_rgba(path, rgba):
    """Minimal 8-bit RGBA PNG writer (stdlib only)."""
    h, w = rgba.shape[:2]
    raw = b"".join(b"\x00" + rgba[i].tobytes() for i in range(h))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    Path(path).write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b""))


def scene_counts(laz_path, origin, bounds, cell, chunk_pts):
    import laspy
    total = 0
    grid = None
    with laspy.open(laz_path) as f:
        for pts in f.chunk_iterator(chunk_pts):
            xs = np.asarray(pts.x, dtype=np.float64) - origin[0]
            ys = np.asarray(pts.y, dtype=np.float64) - origin[1]
            g = bin_counts(xs, ys, bounds, cell)
            grid = g if grid is None else grid + g
            total += len(xs)
    return grid, total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="configs/p2/journal1_phase_b_v1/run_v1.json")
    args = ap.parse_args()
    cfg_all = json.load(open(args.config))
    cfg = cfg_all["sensor_overlay"]
    origin = cfg_all["origin"]
    out_dir = Path(cfg_all["out_dir"])
    cell = cfg["cell_m"]

    fps = json.load(open(cfg_all["overview_map"]["footprints_geojson"]))["features"]
    xs, ys = [], []
    for f in fps:
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            for x, y, *_ in poly[0]:
                xs.append(x - origin[0])
                ys.append(y - origin[1])
    m = cfg["margin_m"]
    bounds = (min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m)

    counts, totals = {}, {}
    for arm in ("E1", "E2"):
        counts[arm], totals[arm] = scene_counts(
            cfg[f"{arm.lower()}_scene_laz"], origin, bounds, cell, cfg["chunk_pts"])
        write_png_rgba(out_dir / f"overlay_{arm}.png",
                       rgba_single(counts[arm], hex_rgb(cfg["colors"][arm]),
                                   cfg["alpha_knee_pts"]))
    write_png_rgba(out_dir / "overlay_BOTH.png",
                   rgba_both(counts["E1"], counts["E2"],
                             hex_rgb(cfg["colors"]["E1"]), hex_rgb(cfg["colors"]["E2"]),
                             hex_rgb(cfg["colors"]["BOTH"]), cfg["alpha_knee_pts"]))

    occ1 = int((counts["E1"] > 0).sum())
    occ2 = int((counts["E2"] > 0).sum())
    occ_both = int(((counts["E1"] > 0) & (counts["E2"] > 0)).sum())
    generated_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    bounds_doc = {
        "schema": "journal1_phase_b_sensor_overlay_v1",
        "generated_utc": generated_utc,
        "bounds_viewer_local": {"minx": round(bounds[0], 2), "miny": round(bounds[1], 2),
                                 "maxx": round(bounds[2], 2), "maxy": round(bounds[3], 2)},
        "cell_m": cell,
        "colors": cfg["colors"],
        "note": "occupancy of the sealed full-scene classified clouds, all classes; alpha scales with point density",
    }
    (out_dir / "overlay_bounds.json").write_text(json.dumps(bounds_doc, indent=1))

    receipt = {
        "task_id": cfg_all["task_id"], "status": cfg_all["status"],
        "scientific_verdict": None, "generated_utc": generated_utc,
        "tool": "scripts/p2/journal1_phase_b_v1/build_sensor_extent_rasters.py",
        "config": str(args.config),
        "git_commit": git_commit(Path(__file__).resolve().parents[3]),
        "python": platform.python_version(),
        "inputs": {"e1_scene_laz": cfg["e1_scene_laz"], "e2_scene_laz": cfg["e2_scene_laz"],
                    "points_read": totals},
        "grid": {"cell_m": cell, "shape_hw": list(counts["E1"].shape),
                  "occupied_cells": {"E1": occ1, "E2": occ2, "both": occ_both}},
        "outputs": ["overlay_E1.png", "overlay_E2.png", "overlay_BOTH.png",
                     "overlay_bounds.json"],
    }
    (Path(cfg_all["overview_map"]["coverage_all_out"]).parent
     / "sensor_overlay_receipt_v1.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps({"points_read": totals, "grid_hw": list(counts["E1"].shape),
                      "occupied_cells": receipt["grid"]["occupied_cells"]}))


if __name__ == "__main__":
    main()

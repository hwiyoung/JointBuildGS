"""Visualize rendered image samples from the Pix4D-standard UAV mission.

Shows a representative waypoint's 5 captures (1 nadir + 4 oblique N/E/S/W) × 4
passes (RGB / depth / normal / semantic color). That's a 5 × 4 = 20 subplot grid
per waypoint.

Also shows a compressed overview grid of RGB-only samples for multiple waypoints
spread across the scene.

Output: results/phase2_synthesis/figures/render_samples.png
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image as PILImage
import cv2

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "results/phase2_synthesis/dataset"
OUT_DIR = ROOT / "results/phase2_synthesis/figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Focus waypoint (center of scene)
FOCUS = "waypt_06_03"  # middle row, middle col for 14×8 grid

VIEWS = [
    (f"{FOCUS}_nadir",         "Nadir (down)"),
    (f"{FOCUS}_oblique_az000", "Oblique N (az 0°)"),
    (f"{FOCUS}_oblique_az090", "Oblique E (az 90°)"),
    (f"{FOCUS}_oblique_az180", "Oblique S (az 180°)"),
    (f"{FOCUS}_oblique_az270", "Oblique W (az 270°)"),
]

# Waypoints distributed across 14×8 grid (for overview panel)
OVERVIEW_WAYPTS = [
    "waypt_00_00_nadir", "waypt_00_07_nadir",
    "waypt_03_00_nadir", "waypt_03_07_nadir",
    "waypt_06_00_nadir", "waypt_06_07_nadir",
    "waypt_09_00_nadir", "waypt_09_07_nadir",
    "waypt_13_00_nadir", "waypt_13_07_nadir",
    "waypt_06_03_oblique_az000", "waypt_06_03_oblique_az090",
]


def load_rgb(name):
    p = DS / "images" / f"{name}.png"
    return np.array(PILImage.open(p)) if p.exists() else None


def load_depth(name):
    p = DS / "depth" / f"{name}.exr"
    if not p.exists(): return None
    d = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
    if d is None: return None
    if d.ndim == 3: d = d[..., 0]
    # mask out sky sentinel
    mask = d < 25000
    d = np.where(mask, d, np.nan)
    return d


def load_normal(name):
    p = DS / "normal" / f"{name}.exr"
    if not p.exists(): return None
    n = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
    if n is None: return None
    # stored as BGRA (n+1)/2 in COLMAP world; visualize as RGB directly
    n_rgb = n[..., :3][..., ::-1]  # BGR -> RGB
    return np.clip(n_rgb, 0, 1)


def load_semantic(name):
    p = DS / "semantic_color" / f"{name}.png"
    if not p.exists(): return None
    return np.array(PILImage.open(p))


def main():
    fig = plt.figure(figsize=(22, 14))
    gs = fig.add_gridspec(4, 5, height_ratios=[1, 1, 1, 1])

    # -------- Top 4 rows: 5 waypoint views × 4 passes --------
    pass_loaders = [
        ("RGB", load_rgb, None),
        ("Depth", load_depth, "magma_r"),
        ("Normal", load_normal, None),
        ("Semantic", load_semantic, None),
    ]
    for r, (pname, loader, cmap) in enumerate(pass_loaders):
        for c, (name, title) in enumerate(VIEWS):
            ax = fig.add_subplot(gs[r, c])
            img = loader(name)
            if img is None:
                ax.text(0.5, 0.5, "missing", ha="center", va="center")
            else:
                if pname == "Depth":
                    vmin = np.nanpercentile(img, 5)
                    vmax = np.nanpercentile(img, 95)
                    ax.imshow(img, cmap=cmap, vmin=vmin, vmax=vmax)
                else:
                    ax.imshow(img)
            if r == 0:
                ax.set_title(title, fontsize=10)
            if c == 0:
                ax.set_ylabel(pname, fontsize=11, rotation=90, labelpad=10)
            ax.set_xticks([]); ax.set_yticks([])

    plt.suptitle(f"Pix4D-standard UAV render samples — waypoint {FOCUS} (5 views × 4 passes)",
                 fontsize=13)
    plt.tight_layout()
    out = OUT_DIR / "render_samples.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    plt.close()
    print(f"[viz] saved: {out}")

    # -------- Separate figure: spatial coverage map (nadir thumbnails as a map) --------
    # Scene waypoint grid is 14 rows × 8 cols (row 0..13, col 0..7).
    # Show a subsample arranged to their SPATIAL position (like a top-down map).
    sample_rows = [0, 2, 4, 6, 9, 11, 13]   # 7 rows, evenly spread
    sample_cols = [0, 2, 4, 6]              # 4 cols
    fig2, axes = plt.subplots(len(sample_rows), len(sample_cols),
                               figsize=(len(sample_cols) * 3, len(sample_rows) * 2.25))
    # Each thumbnail shows the nadir image from that waypoint; row/col order
    # matches the waypoint grid in EPSG:7415 (top row = north, bottom = south,
    # left col = west, right col = east).
    for ri, r in enumerate(sample_rows):
        for ci, c in enumerate(sample_cols):
            name = f"waypt_{r:02d}_{c:02d}_nadir"
            ax = axes[ri, ci]
            img = load_rgb(name)
            if img is not None:
                ax.imshow(img)
            else:
                ax.text(0.5, 0.5, "missing", ha="center", va="center")
            ax.set_xticks([]); ax.set_yticks([])
            if ri == 0:
                ax.set_title(f"col {c}", fontsize=9)
            if ci == 0:
                ax.set_ylabel(f"row {r}", fontsize=9, rotation=0, labelpad=25, ha="right")
    plt.suptitle(f"Nadir coverage map — {len(sample_rows)}×{len(sample_cols)} subsample\n"
                 f"of the full 14×8 waypoint grid (top=north, left=west; "
                 f"total 112 nadir waypoints, each 120×90m footprint).",
                 fontsize=11, y=1.00)
    plt.tight_layout()
    out2 = OUT_DIR / "coverage_map.png"
    plt.savefig(out2, dpi=130, bbox_inches="tight")
    plt.close()
    print(f"[viz] saved: {out2}")


if __name__ == "__main__":
    main()

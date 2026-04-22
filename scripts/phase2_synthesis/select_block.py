"""Select a natural 200x200m block from 3D BAG Amsterdam Jordaan.

Strategy:
  1. Scan all 2888 buildings across 4 tiles, read world XY centroid
     (note: 3D BAG uses EPSG:7415 Dutch national grid, meters)
  2. Slide a 200x200m window in 10m steps
  3. For each window, count buildings and measure roof-type diversity
  4. Pick the window with (a) 80–150 buildings and (b) max roof-type entropy
  5. Save metadata + visualization to results/phase2_synthesis/

Output:
  results/phase2_synthesis/selected_block.json   (window bbox, selected building IDs)
  results/phase2_synthesis/block_selection.png   (map of all buildings + chosen window)
"""
from __future__ import annotations

import glob
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "synthetic_a"))


WINDOW_SIZE = 200.0   # meters (Pix4D mission scope)
WINDOW_STRIDE = 10.0  # meters
MIN_BUILDINGS = 80
MAX_BUILDINGS = 150
MIN_TYPES = 4         # require at least 4 distinct roof types in the window

ROOF_TYPES = ["flat", "shed", "gable", "hip", "tri-slope", "complex"]
TYPE_COLOR = {
    "flat":      "#4C9AFF",
    "shed":      "#9B59B6",
    "gable":     "#20A050",
    "hip":       "#FFB040",
    "tri-slope": "#FF6B6B",
    "complex":   "#888888",
}


def load_buildings_world():
    """Load all Jordaan buildings with their WORLD positions.

    `parse_tile` centers each building at origin; we re-read raw CityJSON to
    preserve world (EPSG:7415) positions.
    """
    from buildings_3dbag import parse_tile, classify_roof_type_from_faces  # noqa: F401
    tiles = sorted(glob.glob(str(ROOT / "results/synthetic_a/3dbag_raw/amsterdam_jordaan/*.city.json")))
    assert tiles, "no Jordaan tiles found"

    out = []
    for tile_path in tiles:
        cj = json.load(open(tile_path))
        transform = cj.get("transform", {})
        scale = np.array(transform.get("scale", [1, 1, 1]))
        translate = np.array(transform.get("translate", [0, 0, 0]))
        raw_verts = np.array(cj.get("vertices", []), dtype=np.float64)
        if len(raw_verts) == 0:
            continue
        world_verts = raw_verts * scale + translate  # meters in EPSG:7415

        parsed = parse_tile(tile_path)
        # parse_tile centers each building; we need world positions.
        # Re-extract world centroid per building by name from raw CityObjects.
        name_to_world_centroid = {}
        name_to_world_bbox = {}
        for obj_name, obj in cj.get("CityObjects", {}).items():
            if obj.get("type") not in ("Building", "BuildingPart"):
                continue
            geom = obj.get("geometry", [])
            if not geom:
                continue
            # Collect all vertex indices referenced by this object
            idxs = set()
            for g in geom:
                def walk(b):
                    if isinstance(b, list):
                        if b and isinstance(b[0], int):
                            idxs.update(b)
                        else:
                            for x in b:
                                walk(x)
                walk(g.get("boundaries", []))
            if not idxs:
                continue
            pts = world_verts[list(idxs)]
            name_to_world_centroid[obj_name] = pts.mean(axis=0)
            name_to_world_bbox[obj_name] = (pts.min(axis=0), pts.max(axis=0))

        # Merge: for each parsed building, attach its world centroid
        for b in parsed:
            wc = name_to_world_centroid.get(b["name"])
            if wc is None:
                continue
            wb = name_to_world_bbox[b["name"]]
            out.append({
                "name": b["name"],
                "type": b["type"],
                "ground_area": float(b["ground_area"]),
                "world_x": float(wc[0]),
                "world_y": float(wc[1]),
                "world_z": float(wc[2]),
                "world_bbox_min": wb[0].tolist(),
                "world_bbox_max": wb[1].tolist(),
                "source_tile": Path(tile_path).name,
            })
    return out


def roof_type_entropy(counts: dict) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    probs = [c / total for c in counts.values() if c > 0]
    return -sum(p * math.log(p) for p in probs)


def find_best_window(buildings):
    xs = np.array([b["world_x"] for b in buildings])
    ys = np.array([b["world_y"] for b in buildings])
    x_min, x_max = xs.min(), xs.max()
    y_min, y_max = ys.min(), ys.max()

    best = None
    candidates = []
    for cx in np.arange(x_min + WINDOW_SIZE/2, x_max - WINDOW_SIZE/2, WINDOW_STRIDE):
        for cy in np.arange(y_min + WINDOW_SIZE/2, y_max - WINDOW_SIZE/2, WINDOW_STRIDE):
            mask = ((xs >= cx - WINDOW_SIZE/2) & (xs <= cx + WINDOW_SIZE/2) &
                    (ys >= cy - WINDOW_SIZE/2) & (ys <= cy + WINDOW_SIZE/2))
            n = int(mask.sum())
            if not (MIN_BUILDINGS <= n <= MAX_BUILDINGS):
                continue
            types = [buildings[i]["type"] for i in np.where(mask)[0]]
            type_counts = {t: types.count(t) for t in ROOF_TYPES}
            if sum(1 for c in type_counts.values() if c > 0) < MIN_TYPES:
                continue
            entropy = roof_type_entropy(type_counts)
            candidates.append({
                "cx": float(cx), "cy": float(cy), "n": n,
                "type_counts": type_counts, "entropy": entropy,
            })
            if best is None or entropy > best["entropy"]:
                best = candidates[-1]
    return best, candidates


def plot_selection(buildings, best, out_path: Path):
    xs = np.array([b["world_x"] for b in buildings])
    ys = np.array([b["world_y"] for b in buildings])
    types = [b["type"] for b in buildings]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))

    # (1) All Jordaan: color by roof type + highlighted window
    for rt in ROOF_TYPES:
        mask = np.array([t == rt for t in types])
        if mask.any():
            ax1.scatter(xs[mask], ys[mask], s=8, c=TYPE_COLOR[rt],
                        label=f"{rt} ({mask.sum()})", alpha=0.6)
    if best is not None:
        rect = mpatches.Rectangle(
            (best["cx"] - WINDOW_SIZE/2, best["cy"] - WINDOW_SIZE/2),
            WINDOW_SIZE, WINDOW_SIZE, linewidth=2.5, edgecolor="red",
            facecolor="none", label=f"Selected window ({best['n']} bldgs)")
        ax1.add_patch(rect)
    ax1.set_title(f"All Jordaan buildings (n={len(buildings)}) + selected 200×200m window",
                  fontsize=12)
    ax1.set_xlabel("EPSG:7415 X (m)")
    ax1.set_ylabel("EPSG:7415 Y (m)")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.set_aspect("equal")

    # (2) Zoom into selected window: per-building footprint bbox
    if best is not None:
        cx, cy = best["cx"], best["cy"]
        half = WINDOW_SIZE / 2
        ax2.set_xlim(cx - half - 10, cx + half + 10)
        ax2.set_ylim(cy - half - 10, cy + half + 10)
        # Mark window
        rect = mpatches.Rectangle(
            (cx - half, cy - half), WINDOW_SIZE, WINDOW_SIZE,
            linewidth=2, edgecolor="red", facecolor="none", alpha=0.5)
        ax2.add_patch(rect)
        # Draw each building's footprint bbox
        n_shown = 0
        for b in buildings:
            x, y = b["world_x"], b["world_y"]
            if not (cx - half <= x <= cx + half and cy - half <= y <= cy + half):
                continue
            bmin, bmax = b["world_bbox_min"], b["world_bbox_max"]
            w = bmax[0] - bmin[0]
            h = bmax[1] - bmin[1]
            color = TYPE_COLOR.get(b["type"], "#aaa")
            patch = mpatches.Rectangle(
                (bmin[0], bmin[1]), w, h,
                linewidth=0.5, edgecolor="black", facecolor=color, alpha=0.7)
            ax2.add_patch(patch)
            n_shown += 1
        type_summary = ", ".join(f"{rt}:{best['type_counts'][rt]}"
                                  for rt in ROOF_TYPES
                                  if best['type_counts'][rt] > 0)
        ax2.set_title(f"Selected window zoom: {n_shown} bldgs  [{type_summary}]",
                      fontsize=11)
        ax2.set_xlabel("EPSG:7415 X (m)")
        ax2.set_ylabel("EPSG:7415 Y (m)")
        ax2.set_aspect("equal")

    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"  -> {out_path}")


def main():
    out_dir = ROOT / "results/phase2_synthesis"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[select] loading all Jordaan buildings with world coords …")
    buildings = load_buildings_world()
    print(f"[select] loaded {len(buildings)} buildings")
    type_hist = {}
    for b in buildings:
        type_hist[b["type"]] = type_hist.get(b["type"], 0) + 1
    print(f"[select] Jordaan type distribution: {type_hist}")

    print(f"[select] sliding 200×200m window with {WINDOW_STRIDE}m stride …")
    best, candidates = find_best_window(buildings)
    print(f"[select] {len(candidates)} candidate windows found in range "
          f"[{MIN_BUILDINGS}, {MAX_BUILDINGS}] buildings × ≥{MIN_TYPES} roof types")
    if best is None:
        raise SystemExit("[select] no window matches criteria. Adjust MIN/MAX.")

    cx, cy = best["cx"], best["cy"]
    print(f"[select] best window: center=({cx:.1f}, {cy:.1f}) EPSG:7415")
    print(f"         n_buildings={best['n']}, entropy={best['entropy']:.3f}")
    print(f"         type_counts={best['type_counts']}")

    # Save selection
    half = WINDOW_SIZE / 2
    inside = [b for b in buildings
              if cx - half <= b["world_x"] <= cx + half
              and cy - half <= b["world_y"] <= cy + half]
    sel = {
        "window": {
            "center": [cx, cy],
            "size": WINDOW_SIZE,
            "bbox_min": [cx - half, cy - half],
            "bbox_max": [cx + half, cy + half],
            "crs": "EPSG:7415",
        },
        "n_buildings": len(inside),
        "type_counts": best["type_counts"],
        "roof_type_entropy": best["entropy"],
        "buildings": inside,
    }
    (out_dir / "selected_block.json").write_text(
        json.dumps(sel, indent=2, default=float))
    print(f"[select] saved: {out_dir/'selected_block.json'}")

    # NOTE: block_selection.png is redundant with viz_block_3d.py output (which
    # draws the same 2D context + zoom with real ground polygons + a 3D view).
    # Kept as optional diagnostic; comment out to skip.
    # plot_selection(buildings, best, out_dir / "block_selection.png")


if __name__ == "__main__":
    main()

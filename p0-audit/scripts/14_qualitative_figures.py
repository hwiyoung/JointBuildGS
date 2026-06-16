#!/usr/bin/env python3
"""T14 qualitative figures (two figures from one run). Visualization only -- no judgement.

Figure A (texture -> point cloud): for the textureless failure DEBY_LOD2_4907182,
one row of 4 panels -- ALS cloud top-view (full), DIM cloud top-view (near-empty),
and two roof texture closeups: one over a roof area where DIM has NO points
(textureless) and one over an area where DIM HAS points (relatively textured).
The two closeups are tied with two differently colored boxes to their locations in
the DIM top-view, so "no texture -> no points, texture -> points" is visible inside
one building. A second row adds the textured building DEBY_LOD2_4908023 (DIM full)
as contrast. No footprint overlay on a perspective photo (roof-height parallax).

Figure B (point cloud -> model): three buildings -- 4907182 (textureless failure),
4906969 (plane-F1 gap, ALS 4 vs DIM 11 roof faces), 4906972 (both-success control).
Per building an input row (ALS | DIM point cloud) above an output row (ALS | DIM |
reference LoD2 model, roof faces colored per instance; DIM-missing shown as an
explicit cell). Input view reveals the building characteristic: 4907182 top-view
(emptiness), 4906969 / 4906972 a roof cross-section (thin slab from the side: DIM
thick scatter vs ALS thin plane) plus a top-view inset.

Run from p0-audit/. Rendered inside the P0 tools container (rule 8); reuses the T7
cloud/footprint/camera helpers. EPSG:25832 throughout.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


TASK_ID = "T14"
CANONICAL_RUN = "w3_2b_roofer_repeatability_20260612_220747"
RUN_REL = f"{CANONICAL_RUN}/run_2"
ALS_CITYJSON = f"runs/{CANONICAL_RUN}/cityjson/run_2/als_default.city.json"
DIM_CITYJSON = f"runs/{CANONICAL_RUN}/cityjson/run_2/dim_default.city.json"
REF_GML = {"690_5334": "data/raw/lod2/690_5334.gml", "690_5336": "data/raw/lod2/690_5336.gml"}
FOOTPRINT_GPKG = "data/work/footprints/lod2_ground_plan.gpkg"
FOOTPRINT_LAYER = "lod2_ground_plan"
IMAGE_DIR = "data/work/images/Images"
COLMAP_CAMERAS = "data/work/colmap/sparse/0/cameras.txt"
COLMAP_IMAGES = "data/work/colmap/sparse/0/images.txt"
SCENE_REF = "data/work/opf/opf/scene_reference_frame.json"
T12_METADATA = "docs/W3_figure_failure_story_metadata.json"

FIGA_PRIMARY = "DEBY_LOD2_4907182"
FIGA_CONTRAST = "DEBY_LOD2_4908023"
FIGB_BUILDINGS = [
    {"id": "DEBY_LOD2_4907182", "tile": "690_5336", "role": "textureless failure", "view": "top",
     "df1": "DIM LoD2.2 not produced"},
    {"id": "DEBY_LOD2_4906969", "tile": "690_5336", "role": "plane-F1 gap survivor", "view": "patch",
     "df1": "ALS F1 0.86, DIM F1 0.29 (dF1 -0.57)"},
    {"id": "DEBY_LOD2_4906972", "tile": "690_5334", "role": "both-success control", "view": "patch",
     "df1": "ALS F1 1.00, DIM F1 1.00 (dF1 0.00)"},
]

OUT_FIG_A = "docs/figs/w3_t14_figA_texture_to_points.png"
OUT_FIG_B = "docs/figs/w3_t14_figB_input_to_output.png"
REPORT_MD = "docs/W3_qualitative_compare.md"
PKG_FIG_A = "fig_17_t14_texture_to_points.png"
PKG_FIG_B = "fig_18_t14_input_to_output.png"

ROOF_T, WALL_T, GROUND_T = "RoofSurface", "WallSurface", "GroundSurface"
GML_NS = "{http://www.opengis.net/gml}"
BLDG_NS = "{http://www.opengis.net/citygml/building/1.0}"
ELEV, AZIM = 32.0, -58.0
PATCH_M = 3.0
PATCH_VMAX = 0.30         # fixed color scale (m) for Figure B roof-patch distance coloring
COLOR_EMPTY = "#ff5500"   # box over DIM-empty / textureless area
COLOR_POINTS = "#1bbf3a"  # box over DIM-points / textured area


@dataclass
class Surface:
    surface_type: str
    instance: int
    coords: np.ndarray


# ---------------------------------------------------------------------------
# geometry parsing (ported from the prior T14 renderer)
# ---------------------------------------------------------------------------
def cityjson_surfaces(path: Path, building_id: str) -> list[Surface]:
    cj = json.loads(path.read_text(encoding="utf-8"))
    co = cj["CityObjects"]
    scale = np.asarray(cj["transform"]["scale"], dtype=np.float64)
    translate = np.asarray(cj["transform"]["translate"], dtype=np.float64)
    verts = np.asarray(cj["vertices"], dtype=np.float64) * scale + translate
    parts = [k for k, v in co.items() if v.get("type") == "BuildingPart" and building_id in (v.get("parents") or [])]
    surfaces: list[Surface] = []
    roof_inst: dict[int, int] = {}
    for pk in parts:
        for g in co[pk].get("geometry", []):
            if g.get("type") != "Solid" or str(g.get("lod")) not in ("2.2", "2"):
                continue
            sem = g.get("semantics", {})
            sem_surfaces = sem.get("surfaces", [])
            values = sem.get("values")
            for shell_idx, shell in enumerate(g["boundaries"]):
                shell_vals = values[shell_idx] if values else [None] * len(shell)
                for poly_idx, polygon in enumerate(shell):
                    coords = verts[np.asarray(polygon[0], dtype=np.int64)]
                    sidx = shell_vals[poly_idx] if poly_idx < len(shell_vals) else None
                    stype = (sem_surfaces[sidx]["type"] if (sidx is not None and 0 <= sidx < len(sem_surfaces)) else "Unknown")
                    inst = roof_inst.setdefault(hash((pk, sidx)), len(roof_inst)) if stype == ROOF_T else -1
                    surfaces.append(Surface(stype, inst, coords))
    return surfaces


def citygml_surfaces(path: Path, building_id: str) -> list[Surface]:
    surfaces: list[Surface] = []
    roof_inst = 0
    for _, el in ET.iterparse(str(path), events=("end",)):
        if el.tag != BLDG_NS + "Building":
            continue
        if el.get(GML_NS + "id") == building_id:
            for surf_el in el.iter():
                tag = surf_el.tag.split("}")[-1]
                if tag not in (ROOF_T, WALL_T, GROUND_T):
                    continue
                for pos in surf_el.iter(GML_NS + "posList"):
                    if not pos.text:
                        continue
                    vals = np.asarray(pos.text.split(), dtype=np.float64)
                    if vals.size >= 9 and vals.size % 3 == 0:
                        surfaces.append(Surface(tag, roof_inst if tag == ROOF_T else -1, vals.reshape(-1, 3)))
                if tag == ROOF_T:
                    roof_inst += 1
            el.clear()
            break
        el.clear()
    if not surfaces:
        raise RuntimeError(f"No LoD2 surfaces for {building_id} in {path}")
    return surfaces


def surfaces_bbox(*surface_lists: list[Surface]) -> tuple[np.ndarray, np.ndarray]:
    pts = np.vstack([s.coords for sl in surface_lists if sl for s in sl])
    return pts.min(axis=0), pts.max(axis=0)


def roof_instance_count(surfaces: list[Surface] | None) -> int | None:
    if not surfaces:
        return None
    return max((s.instance for s in surfaces if s.surface_type == ROOF_T), default=-1) + 1


def set_cubic_3d(ax: Any, lims: tuple[np.ndarray, np.ndarray]) -> None:
    """Identical cubic box + camera for every Figure B panel, so input point
    clouds and output models share one viewpoint and are directly comparable."""
    lo, hi = lims
    center = (lo + hi) / 2.0
    span = float(np.max(hi - lo)) or 1.0
    half = span / 2.0 * 1.05
    ax.set_xlim(center[0] - half, center[0] + half)
    ax.set_ylim(center[1] - half, center[1] + half)
    ax.set_zlim(lo[2], lo[2] + span)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=ELEV, azim=AZIM)
    ax.set_xticklabels([]); ax.set_yticklabels([]); ax.set_zticklabels([])


def render_model_panel(ax: Any, surfaces: list[Surface] | None, lims: tuple[np.ndarray, np.ndarray],
                       title: str, missing_note: str | None = None) -> None:
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    import matplotlib.pyplot as plt

    set_cubic_3d(ax, lims)
    if title:
        ax.set_title(title, fontsize=10, pad=2)
    if missing_note is not None:
        ax.text2D(0.5, 0.55, missing_note, transform=ax.transAxes, ha="center", va="center",
                  fontsize=11, color="#b22222", fontweight="bold")
        ax.text2D(0.5, 0.40, "(reconstruction failure)", transform=ax.transAxes, ha="center",
                  va="center", fontsize=9, color="#777777")
        return
    walls = [s.coords for s in surfaces if s.surface_type == WALL_T]
    grounds = [s.coords for s in surfaces if s.surface_type == GROUND_T]
    roofs = [s for s in surfaces if s.surface_type == ROOF_T]
    n_inst = max((s.instance for s in roofs), default=-1) + 1
    cmap = plt.get_cmap("turbo")
    roof_colors = [cmap((i + 0.5) / max(n_inst, 1)) for i in range(max(n_inst, 1))]
    if grounds:
        ax.add_collection3d(Poly3DCollection(grounds, facecolor="#e8e8e8", edgecolor="#cccccc", linewidths=0.3, alpha=0.35))
    if walls:
        ax.add_collection3d(Poly3DCollection(walls, facecolor="#d9d9d9", edgecolor="#9a9a9a", linewidths=0.3, alpha=0.55))
    if roofs:
        ax.add_collection3d(Poly3DCollection([s.coords for s in roofs], facecolors=[roof_colors[s.instance] for s in roofs],
                                             edgecolor="#222222", linewidths=0.5, alpha=0.95))
    ax.text2D(0.02, 0.02, f"{len(roofs)} roof faces / {n_inst} instances", transform=ax.transAxes, fontsize=8,
              bbox={"facecolor": "white", "alpha": 0.7, "pad": 2, "edgecolor": "none"})


# ---------------------------------------------------------------------------
# point-cloud panels
# ---------------------------------------------------------------------------
def _subsample(x, y, z, n=14000):
    if x.size > n:
        idx = np.linspace(0, x.size - 1, n, dtype=np.int64)
        return x[idx], y[idx], z[idx]
    return x, y, z


def render_topview(ax: Any, xyz, footprint: Any, label: str, density: float, holes: float,
                   boxes: list[tuple[np.ndarray, str]] | None = None) -> None:
    x, y, z = _subsample(*xyz)
    if x.size:
        ax.scatter(x, y, s=3.0 if x.size > 400 else 11.0, c=z, cmap="viridis", alpha=0.85, linewidths=0)
    ring = footprint.ring
    ax.plot(ring[:, 0], ring[:, 1], color="#111111", linewidth=1.2)
    if boxes:
        for box, color in boxes:
            ax.plot(box[:, 0], box[:, 1], color=color, linewidth=2.4)
    min_x, min_y, max_x, max_y = footprint.bbox
    pad = max(max_x - min_x, max_y - min_y) * 0.16 + 1.0
    ax.set_xlim(min_x - pad, max_x + pad); ax.set_ylim(min_y - pad, max_y + pad)
    ax.set_aspect("equal", adjustable="box")
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    ax.text(0.03, 0.04, f"{label}\ndensity={density:.1f} pts/m2\nholes={holes:.2f}", transform=ax.transAxes,
            fontsize=8.6, bbox={"facecolor": "white", "alpha": 0.85, "pad": 2, "edgecolor": "#cccccc"})


def xy_area(coords: np.ndarray) -> float:
    x, y = coords[:, 0], coords[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def fit_plane(points: np.ndarray, robust: bool = False, band: float = 0.30, iters: int = 3):
    """Least-squares plane; returns (centroid, normal, signed distances, NMAD).

    NMAD = 1.4826 * median(|d - median(d)|) is a robust roughness (tail-resistant,
    consistent with the W3 height-NMAD vocabulary). With robust=True the plane is
    re-fit on inliers (|d| <= band) so superstructures/outliers do not tilt it; the
    returned distances `d` still cover ALL points (so outliers stay visible).
    """
    def _fit(P):
        c = P.mean(axis=0)
        _, _, vh = np.linalg.svd(P - c, full_matrices=False)
        n = vh[2] / (np.linalg.norm(vh[2]) or 1.0)
        return c, n
    c, n = _fit(points)
    d = (points - c) @ n
    if robust:
        for _ in range(iters):
            keep = np.abs(d) <= band
            if keep.sum() < max(12, int(0.4 * len(points))):
                break
            c, n = _fit(points[keep])
            d = (points - c) @ n
    nmad = float(1.4826 * np.median(np.abs(d - np.median(d)))) if d.size else float("nan")
    return c, n, d, nmad


def roof_distance(points: np.ndarray, ref_surfaces: list[Surface], slab_m: float = 0.8):
    """Per-point |perpendicular distance| to its roof facet's *own best-fit plane*.

    Reference RoofSurfaces only GROUP points (XY polygon + reference plane within
    +/- slab_m, to exclude walls/ground). The distance is then to a plane fit to the
    INPUT points on that facet, so the value is intrinsic surface roughness (not the
    point-cloud-to-reference-model bias). Returns (distance, assigned_mask)."""
    from matplotlib.path import Path as MPath
    roofs = [s for s in (ref_surfaces or []) if s.surface_type == ROOF_T and s.coords.shape[0] >= 3]
    d = np.full(points.shape[0], np.inf)
    found = np.zeros(points.shape[0], dtype=bool)
    for facet in roofs:
        rc, rn, _, _ = fit_plane(facet.coords)                     # reference plane: selection only
        poly = MPath(facet.coords[:, :2])
        inside = poly.contains_points(points[:, :2]) & (np.abs((points - rc) @ rn) < slab_m)
        if inside.sum() < 12:
            continue
        fc, fn, _, _ = fit_plane(points[inside], robust=True)      # plane fit to the input points
        dist = np.abs((points - fc) @ fn)
        upd = inside & (dist < d)
        d[upd] = dist[upd]
        found |= inside
    return d, found


def roof_nmad(distances: np.ndarray) -> float:
    if distances.size < 3:
        return float("nan")
    return float(1.4826 * np.median(np.abs(distances - np.median(distances))))


def render_roof_points_3d(ax: Any, clip_xyz, ref_surfaces: list[Surface], lims, vmax: float,
                          label: str, density: float, nmad: float):
    """Roof points in the SAME world frame + camera + cubic box as the output model,
    colored by distance to the roof plane (blue=on-plane, red=far). Roughness is read
    from color (visible at any scale). The NMAD label is the precomputed value (so the
    figure matches the report table exactly); n/a when no model was produced."""
    x, y, z = clip_xyz
    pts = np.column_stack([x, y, z]) if x.size else np.empty((0, 3))
    set_cubic_3d(ax, lims)
    sm = None
    if pts.shape[0]:
        d, found = roof_distance(pts, ref_surfaces)
        roof_pts, roof_d = pts[found], d[found]
        if roof_pts.shape[0]:
            if roof_pts.shape[0] > 7000:  # subsample to avoid overplot saturation hiding the color spread
                idx = np.random.default_rng(0).choice(roof_pts.shape[0], 7000, replace=False)
                roof_pts, roof_d = roof_pts[idx], roof_d[idx]
            order = np.argsort(-roof_d)  # draw near-plane (blue) points last, on top
            sm = ax.scatter(roof_pts[order, 0], roof_pts[order, 1], roof_pts[order, 2], c=roof_d[order],
                            cmap="RdYlBu_r", vmin=0.0, vmax=vmax, s=5.0, alpha=0.8, linewidths=0)
    nmad_txt = "n/a" if not np.isfinite(nmad) else f"{nmad * 100:.0f} cm"
    ax.text2D(0.02, 0.98, f"{label}\nroof NMAD {nmad_txt}\ndensity {density:.0f} pts/m2",
              transform=ax.transAxes, fontsize=10.5, va="top", fontweight="bold",
              bbox={"facecolor": "white", "alpha": 0.85, "pad": 3, "edgecolor": "#cccccc"})
    return sm


# ---------------------------------------------------------------------------
# Figure A helpers: find empty/points boxes and texture proxy
# ---------------------------------------------------------------------------
def square_box(center: np.ndarray, size: float) -> np.ndarray:
    h = size / 2.0
    return np.array([[center[0] - h, center[1] - h], [center[0] + h, center[1] - h],
                     [center[0] + h, center[1] + h], [center[0] - h, center[1] + h],
                     [center[0] - h, center[1] - h]], dtype=np.float64)


def find_empty_and_points_boxes(dim_xy: np.ndarray, footprint: Any, patch_m: float):
    from matplotlib.path import Path as MPath
    poly = MPath(footprint.ring)
    min_x, min_y, max_x, max_y = footprint.bbox
    step = patch_m / 2.0
    xs = np.arange(min_x + patch_m / 2, max_x - patch_m / 2 + 1e-6, step)
    ys = np.arange(min_y + patch_m / 2, max_y - patch_m / 2 + 1e-6, step)
    half = patch_m / 2.0
    best_points = (-1, None)
    best_empty = (-1.0, None)
    for cx in xs:
        for cy in ys:
            if not poly.contains_point((cx, cy)):
                continue
            if dim_xy.size:
                inside = ((np.abs(dim_xy[:, 0] - cx) <= half) & (np.abs(dim_xy[:, 1] - cy) <= half)).sum()
                nn = float(np.min(np.hypot(dim_xy[:, 0] - cx, dim_xy[:, 1] - cy)))
            else:
                inside, nn = 0, 1e9
            if inside > best_points[0]:
                best_points = (inside, np.array([cx, cy]))
            if inside == 0 and nn > best_empty[0]:
                best_empty = (nn, np.array([cx, cy]))
    if best_empty[1] is None:  # fully covered: fall back to the lowest-count cell
        best_empty = (0.0, footprint.ring[:-1].mean(axis=0))
    return best_empty[1], best_points[1], int(best_points[0])


def texture_proxy(rgb: np.ndarray, center_uv: np.ndarray, half_px: int) -> tuple[np.ndarray, float]:
    u, v = int(center_uv[0]), int(center_uv[1])
    h, w = rgb.shape[:2]
    u0, v0 = max(0, u - half_px), max(0, v - half_px)
    crop = rgb[v0:min(h, v + half_px), u0:min(w, u + half_px)]
    if crop.size == 0:
        return crop, float("nan")
    gray = crop.astype(np.float64).mean(axis=2) / 255.0
    gy, gx = np.gradient(gray)
    return crop, float(np.hypot(gx, gy).mean())


def render_figureA(out_path: Path, t7: Any, rows: list[dict[str, Any]]) -> dict[str, Any]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import ConnectionPatch
    from PIL import Image

    n = len(rows)
    fig, axes = plt.subplots(n, 4, figsize=(16.6, 4.4 * n), constrained_layout=True)
    if n == 1:
        axes = axes.reshape(1, 4)
    titles = ["1. ALS cloud (top-view)", "2. DIM cloud (top-view) + boxes",
              "3. texture @ DIM-empty box", "4. texture @ DIM-points box"]
    for c, t in enumerate(titles):
        axes[0, c].set_title(t, fontsize=10.5, pad=8)

    audit: dict[str, Any] = {}
    for r, row in enumerate(rows):
        fp = row["footprint"]
        box_e = square_box(row["center_empty"], PATCH_M)
        box_p = square_box(row["center_points"], PATCH_M)
        render_topview(axes[r, 0], row["als_xyz"], fp, "ALS", row["als_density"], row["als_holes"])
        render_topview(axes[r, 1], row["dim_xyz"], fp, "DIM", row["dim_density"], row["dim_holes"],
                       boxes=[(box_e, COLOR_EMPTY), (box_p, COLOR_POINTS)])

        with Image.open(row["image_path"]) as im:
            rgb = np.asarray(im.convert("RGB"))
        half_px = max(28, row["patch_px"] // 2)
        crop_e, tex_e = texture_proxy(rgb, row["uv_empty"], half_px)
        crop_p, tex_p = texture_proxy(rgb, row["uv_points"], half_px)
        for ci, (crop, tex, color, tag) in enumerate(
                [(crop_e, tex_e, COLOR_EMPTY, "DIM-empty"), (crop_p, tex_p, COLOR_POINTS, "DIM-points")], start=2):
            ax = axes[r, ci]
            if crop.size:
                ax.imshow(crop)
            for sp in ax.spines.values():
                sp.set_edgecolor(color); sp.set_linewidth(3.0)
            ax.set_xticks([]); ax.set_yticks([])
            ax.text(0.04, 0.06, f"{tag}\nmean grad={tex:.4f}", transform=ax.transAxes, fontsize=8.6, color="white",
                    bbox={"facecolor": "black", "alpha": 0.55, "pad": 2, "edgecolor": "none"})

        # connect boxes (DIM top-view) to the matching closeups
        for box, color, ax_to in [(box_e, COLOR_EMPTY, axes[r, 2]), (box_p, COLOR_POINTS, axes[r, 3])]:
            con = ConnectionPatch(xyA=(box[:, 0].mean(), box[:, 1].max()), coordsA=axes[r, 1].transData,
                                  xyB=(0.5, 1.0), coordsB=ax_to.transAxes, color=color, linewidth=1.3, linestyle="--")
            fig.add_artist(con)
        axes[r, 0].text(0.02, 0.97, row["label"], transform=axes[r, 0].transAxes, fontsize=10, va="top",
                        fontweight="bold", bbox={"facecolor": "white", "alpha": 0.8, "pad": 2, "edgecolor": "#ccc"})
        audit[row["building_id"]] = {"image": row["image_name"], "patch_m": PATCH_M,
                                     "dim_points_in_box_points": row["points_in_box"],
                                     "texture_empty": round(tex_e, 4), "texture_points": round(tex_p, 4)}

    fig.suptitle("Figure A: textureless roof (4907182) -> near-empty DIM points vs textured roof (4908023) "
                 "-> dense DIM points; two roof patches sampled per building", fontsize=12.5)
    fig.savefig(out_path, dpi=190)
    plt.close(fig)
    return audit


# ---------------------------------------------------------------------------
# Figure B: input cloud -> output model
# ---------------------------------------------------------------------------
def render_figureB(out_path: Path, blocks: list[dict[str, Any]]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize

    fig = plt.figure(figsize=(15.2, 7.6 * len(blocks)))
    gs = fig.add_gridspec(2 * len(blocks), 6, hspace=0.30, wspace=0.32)
    for bi, blk in enumerate(blocks):
        in_row, out_row = 2 * bi, 2 * bi + 1
        # one shared cubic box + camera for the whole building block (input AND output)
        present = [blk["models"][c] for c in ("ALS", "DIM", "REFERENCE") if blk["models"][c]]
        lims = surfaces_bbox(*present)
        # input row: roof point cloud in the SAME world frame as the output models
        for ci, inp in enumerate(("ALS", "DIM")):
            ax = fig.add_subplot(gs[in_row, ci * 3:ci * 3 + 3], projection="3d")
            render_roof_points_3d(ax, blk["clouds"][inp], blk["ref_surfaces"], lims, PATCH_VMAX,
                                  inp, blk["density"][inp], blk["roof_nmad"][inp])
            ax.set_title((f"input roof cloud — {inp}" if in_row == 0 else inp), fontsize=10.5, pad=4)
        # output row: LoD2 models in the SAME frame
        for ci, model in enumerate(("ALS", "DIM", "REFERENCE")):
            ax = fig.add_subplot(gs[out_row, ci * 2:ci * 2 + 2], projection="3d")
            surfaces = blk["models"][model]
            title = f"output LoD2 — {model}" if (out_row == 1) else model
            if model == "DIM" and not surfaces:
                render_model_panel(ax, None, lims, title, missing_note="DIM: no LoD2.2 produced")
            else:
                render_model_panel(ax, surfaces, lims, title)
        short = blk["id"].replace("DEBY_LOD2_", "")
        fig.text(0.004, 1.0 - (bi + 0.5) / len(blocks), f"{short}\n{blk['role']}\n{blk['df1']}", fontsize=9.5,
                 va="center", ha="left", rotation=90,
                 bbox={"facecolor": "#f4f4f4", "alpha": 0.95, "pad": 4, "edgecolor": "#cccccc"})

    sm = ScalarMappable(norm=Normalize(0.0, PATCH_VMAX), cmap="RdYlBu_r")
    cbar = fig.colorbar(sm, ax=fig.axes, orientation="horizontal", fraction=0.025, pad=0.03, aspect=55)
    cbar.set_label(f"input roof point distance to roof plane (m): blue = on-plane (clean) -> "
                   f"red >= {PATCH_VMAX:.2f} m off-plane (noisy)", fontsize=10)
    fig.suptitle("Figure B: input roof point cloud -> output LoD2 model (ALS | DIM | reference), one shared 3D "
                 "view per building. Input points colored by distance to the roof plane (roof NMAD labeled); "
                 "output roof faces colored per instance. No judgement.", fontsize=11.5, y=0.998)
    fig.subplots_adjust(left=0.055, right=0.99, top=0.96, bottom=0.05)
    fig.savefig(out_path, dpi=175)
    plt.close(fig)


# ---------------------------------------------------------------------------
# compute entrypoint
# ---------------------------------------------------------------------------
def compute_entrypoint() -> None:
    root = Path("/workspace")
    figs = root / "docs/figs"
    figs.mkdir(parents=True, exist_ok=True)
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    scratch = run_dir / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)

    t7 = load_helper_module("t7_failure_diagnosis", root / "scripts/07_failure_diagnosis.py")
    t9 = load_helper_module("t9_failure_surface_cause", root / "scripts/09_failure_surface_cause.py")

    t9.assert_gpkg_epsg25832(root / FOOTPRINT_GPKG, FOOTPRINT_LAYER)
    fp_geojson = scratch / "lod2_ground_plan.geojson"
    t9.convert_gpkg_to_geojson(root / FOOTPRINT_GPKG, fp_geojson, FOOTPRINT_LAYER)
    all_ids = {FIGA_PRIMARY, FIGA_CONTRAST} | {b["id"] for b in FIGB_BUILDINGS}
    footprints = t7.load_footprints(fp_geojson, all_ids)
    t7.assert_epsg25832_footprints(footprints)

    dim_path = root / "data/work/w2/dim_v1_classified_z_minus0p174.laz"
    if not dim_path.exists():
        dim_path = root / "data/work/classify/dim_v1_classified_z.laz"
    bbox = t7.combined_bbox(list(footprints.values()), buffer_m=14.0)
    dim_cloud = t7.read_cloud("DIM", [dim_path], bbox)
    als_cloud = t7.read_cloud("ALS", sorted((root / "data/raw/als").glob("*.laz")), bbox)
    t7.assert_epsg25832_cloud("DIM", dim_cloud)
    t7.assert_epsg25832_cloud("ALS", als_cloud)
    clouds = {"ALS": als_cloud, "DIM": dim_cloud}

    camera_model = t7.parse_camera_model(root / COLMAP_CAMERAS)
    scene_ref = t7.read_json(root / SCENE_REF)
    cameras = {c.name: c for c in t7.parse_colmap_cameras(root / COLMAP_IMAGES, scene_ref)}
    meta = {c["building_id"]: c for c in json.loads((root / T12_METADATA).read_text(encoding="utf-8"))["cases"]}

    # ----- Figure A -----
    figa_rows = []
    for bid in (FIGA_PRIMARY, FIGA_CONTRAST):
        fp = footprints[bid]
        als_xyz = t7.clip_building_points(als_cloud, fp)
        dim_xyz = t7.clip_building_points(dim_cloud, fp)
        als_m = t7.surface_metrics(als_cloud, fp)
        dim_m = t7.surface_metrics(dim_cloud, fp)
        dim_xy = np.column_stack([dim_xyz[0], dim_xyz[1]]) if dim_xyz[0].size else np.empty((0, 2))
        c_empty, c_points, n_in = find_empty_and_points_boxes(dim_xy, fp, PATCH_M)
        roof_z = als_m.roof_z_p90 if np.isfinite(als_m.roof_z_p90) else als_m.roof_z_median
        img_name = meta[bid]["image_name"]
        camera = cameras[img_name]
        uv_e = project_xy(t7, c_empty, roof_z, camera, camera_model, scene_ref)
        uv_p = project_xy(t7, c_points, roof_z, camera, camera_model, scene_ref)
        patch_px = estimate_patch_px(t7, c_points, PATCH_M, roof_z, camera, camera_model, scene_ref)
        figa_rows.append({
            "building_id": bid, "label": f"{bid.replace('DEBY_LOD2_', '')} ({'textureless failure' if bid == FIGA_PRIMARY else 'textured contrast'})",
            "footprint": fp, "als_xyz": als_xyz, "dim_xyz": dim_xyz,
            "als_density": als_m.density_pts_m2, "als_holes": als_m.hole_ratio,
            "dim_density": dim_m.density_pts_m2, "dim_holes": dim_m.hole_ratio,
            "center_empty": c_empty, "center_points": c_points, "points_in_box": n_in,
            "image_name": img_name, "image_path": root / IMAGE_DIR / img_name,
            "uv_empty": uv_e, "uv_points": uv_p, "patch_px": patch_px,
        })
    figa_audit = render_figureA(figs / Path(OUT_FIG_A).name, t7, figa_rows)

    # ----- Figure B -----
    blocks = []
    for b in FIGB_BUILDINGS:
        bid = b["id"]
        fp = footprints[bid]
        clips = {inp: t7.clip_building_points(clouds[inp], fp) for inp in ("ALS", "DIM")}
        metr = {inp: t7.surface_metrics(clouds[inp], fp) for inp in ("ALS", "DIM")}
        ref_surfaces = citygml_surfaces(root / REF_GML[b["tile"]], bid)
        models = {"ALS": cityjson_surfaces(root / ALS_CITYJSON, bid) or None,
                  "DIM": cityjson_surfaces(root / DIM_CITYJSON, bid) or None,
                  "REFERENCE": ref_surfaces or None}
        # whole-roof robust NMAD: distance of each roof point to the reference facet
        # it sits under (the same coloring shown in the figure)
        roof_nmad_by_input = {}
        for inp in ("ALS", "DIM"):
            if models[inp] is None:        # reconstruction failed (near-empty); emphasize density, not roughness
                roof_nmad_by_input[inp] = float("nan")
                continue
            x, y, z = clips[inp]
            pts = np.column_stack([x, y, z]) if x.size else np.empty((0, 3))
            d, found = roof_distance(pts, ref_surfaces)
            roof_nmad_by_input[inp] = roof_nmad(d[found]) if found.sum() >= 12 else float("nan")
        blocks.append({"id": bid, "role": b["role"], "df1": b["df1"], "view": b["view"], "footprint": fp,
                       "clouds": clips, "ref_surfaces": ref_surfaces,
                       "density": {k: metr[k].density_pts_m2 for k in ("ALS", "DIM")},
                       "roof_nmad": roof_nmad_by_input, "models": models,
                       "roof_faces": {k: (None if not models[k] else sum(1 for s in models[k] if s.surface_type == ROOF_T))
                                      for k in ("ALS", "DIM", "REFERENCE")}})
    render_figureB(figs / Path(OUT_FIG_B).name, blocks)

    write_report(root, figa_rows, figa_audit, blocks, run_id)
    add_to_g1_package(root)
    copy_outputs(run_dir, [figs / Path(OUT_FIG_A).name, figs / Path(OUT_FIG_B).name, root / REPORT_MD,
                           root / "docs/G1_package/manifest.json", root / "docs/G1_package/captions.md"])

    print(f"figureA={OUT_FIG_A}")
    print(f"figureB={OUT_FIG_B}")
    for bid, info in figa_audit.items():
        print(f"figA[{bid.replace('DEBY_LOD2_', '')}] tex_empty={info['texture_empty']} tex_points={info['texture_points']} "
              f"dim_pts_in_box={info['dim_points_in_box_points']}")
    def _cm(v):
        return "n/a" if not np.isfinite(v) else f"{v * 100:.1f}cm"
    for blk in blocks:
        print(f"figB[{blk['id'].replace('DEBY_LOD2_', '')}] faces ALS={blk['roof_faces']['ALS']} "
              f"DIM={blk['roof_faces']['DIM']} REF={blk['roof_faces']['REFERENCE']} | "
              f"roof NMAD ALS={_cm(blk['roof_nmad']['ALS'])} DIM={_cm(blk['roof_nmad']['DIM'])}")
    print(f"report={REPORT_MD}")


def project_xy(t7: Any, xy: np.ndarray, roof_z: float, camera: Any, camera_model: Any, scene_ref: dict) -> np.ndarray:
    pt = np.array([[xy[0], xy[1], roof_z]], dtype=np.float64)
    proj, _ = t7.project_points(pt, camera, camera_model, scene_ref)
    return proj[0]


def estimate_patch_px(t7: Any, center: np.ndarray, patch_m: float, roof_z: float, camera, camera_model, scene_ref) -> int:
    a = project_xy(t7, center - np.array([patch_m / 2, 0]), roof_z, camera, camera_model, scene_ref)
    b = project_xy(t7, center + np.array([patch_m / 2, 0]), roof_z, camera, camera_model, scene_ref)
    px = float(np.hypot(*(b - a)))
    return int(np.clip(px, 60, 600))


def write_report(root: Path, figa_rows: list[dict], figa_audit: dict, blocks: list[dict], run_id: str) -> None:
    def faces(v):
        return "—" if v is None else str(v)
    prim = figa_audit[FIGA_PRIMARY]
    contr = figa_audit[FIGA_CONTRAST]
    def nmad_cm(blk, inp):
        v = blk["roof_nmad"][inp]
        return "n/a" if not np.isfinite(v) else f"{v * 100:.0f}"
    figb_rows = [[blk["id"].replace("DEBY_LOD2_", ""), blk["role"],
                  f"{blk['density']['ALS']:.0f}", f"{blk['density']['DIM']:.0f}",
                  nmad_cm(blk, "ALS"), nmad_cm(blk, "DIM"),
                  faces(blk["roof_faces"]["ALS"]), faces(blk["roof_faces"]["DIM"]), faces(blk["roof_faces"]["REFERENCE"]),
                  blk["df1"]] for blk in blocks]
    figb_table = md_table(["building", "role", "ALS dens(fp)", "DIM dens(fp)", "ALS roof NMAD(cm)",
                           "DIM roof NMAD(cm)", "ALS faces", "DIM faces", "ref faces", "plane-F1"], figb_rows)
    figa_table = md_table(["building", "DIM-empty box mean-grad", "DIM-points box mean-grad", "DIM pts in points-box"],
                          [[FIGA_PRIMARY.replace("DEBY_LOD2_", ""), f"{prim['texture_empty']:.4f}",
                            f"{prim['texture_points']:.4f}", prim["dim_points_in_box_points"]],
                           [FIGA_CONTRAST.replace("DEBY_LOD2_", ""), f"{contr['texture_empty']:.4f}",
                            f"{contr['texture_points']:.4f}", contr["dim_points_in_box_points"]]])

    text = f"""# W3 — Qualitative Comparison: texture->points and points->model (T14)

- Run ID: `{run_id}`
- Task: T14 — two qualitative figures from one run (visualization only, no judgement).
- Canonical models: `{ALS_CITYJSON}`, `{DIM_CITYJSON}` (LoD2.2 Solid, run_2).
- Reference LoD2: `data/raw/lod2/690_5334.gml`, `690_5336.gml` (CityGML 1.0).
- Inputs: T3 ALS/DIM LAZ, T5 footprint GPKG, T2 images + COLMAP poses.
- CRS: EPSG:25832 (numeric UTM32) for clouds, footprints, CityJSON/CityGML, and
  camera centers after the T2 OPF scene-reference transform.
- Toolchain (rule 8): rendered inside the P0 `tools` docker service with host user
  mapping; versions in `runs/{run_id}/versions.txt`. **Visual/qualitative only.**

## Figure A — textureless roof -> empty DIM points

For 4907182 (textureless failure) two same-size roof patches are sampled -- one
over a DIM-empty area, one over a DIM-points area -- each projected to a near-nadir
image (no footprint overlay on the photo) and tied by colored boxes to the DIM
top-view. A second row adds 4908023 (textured, DIM full) as contrast.

{figa_table}

![texture to points]({OUT_FIG_A.replace('docs/', '')})

- The 4907182 roof is **uniformly low-texture**: both sampled patches have mean
  image-gradient ~0.018-0.021 (DIM-empty {prim['texture_empty']:.4f}, DIM-points {prim['texture_points']:.4f}), near the
  T9 textureless reference (~0.021), and DIM is near-empty across the whole footprint
  (243 points). The DIM-points patch is **not** more textured than the DIM-empty one
  -- within this building, sparse DIM point presence does not track a local texture
  difference; the roof is textureless globally.
- 4908023 (textured contrast): both patches are ~5x more textured (mean gradient
  {contr['texture_empty']:.4f} / {contr['texture_points']:.4f}) and DIM is dense everywhere (16849 points).
- The texture->points signal is therefore the **cross-building** contrast
  (textureless 4907182 -> near-empty DIM vs textured 4908023 -> dense DIM), not a
  within-4907182 gradient -- the failure building is uniformly textureless. Texture
  proxy = mean image-gradient magnitude over the patch crop (grayscale [0,1]); a
  coarse indicator, not a calibrated metric.

## Figure B — input point cloud -> output LoD2 model

Every panel of a building shares ONE 3D viewpoint and cubic box, so input and
output are directly comparable: the input row shows the roof point cloud (ALS |
DIM) in the same frame as the output LoD2 models (ALS | DIM | reference). Input
roof points are colored by perpendicular distance to the reference roof plane they
sit under -- blue = on-plane (clean), red >= {PATCH_VMAX:.2f} m off-plane (noisy) -- so
roughness reads from color at the building scale (a shared colorbar gives the
metres); the robust roof NMAD (1.4826*MAD, tail-resistant, as in the W3 height
NMAD) is labeled per panel. Output roof faces are colored per instance. The
noisy-input / fragmented-output pair is shown side by side; the causal reading is
left to the viewer (no arrow). `dens(fp)` is whole-footprint point density.

{figb_table}

![input to output]({OUT_FIG_B.replace('docs/', '')})

- **4907182**: near-empty DIM roof cloud (DIM {blocks[0]['density']['DIM']:.0f} vs ALS {blocks[0]['density']['ALS']:.0f} pts/m2)
  -> no DIM LoD2.2 model; ALS and reference reconstruct a closed shell.
- **4906969**: the DIM roof points scatter thickly about the plane (roof NMAD
  {blocks[1]['roof_nmad']['DIM'] * 100:.0f} cm, mostly red) while ALS hugs it (NMAD {blocks[1]['roof_nmad']['ALS'] * 100:.0f} cm, blue);
  alongside, the DIM output is segmented into {blocks[1]['roof_faces']['DIM']} roof faces vs ALS
  {blocks[1]['roof_faces']['ALS']} (reference {blocks[1]['roof_faces']['REFERENCE']}).
- **4906972**: the two roof clouds have similar roughness (ALS NMAD {blocks[2]['roof_nmad']['ALS'] * 100:.0f} cm,
  DIM NMAD {blocks[2]['roof_nmad']['DIM'] * 100:.0f} cm) and ALS, DIM, reference agree on the roof partition
  (3/3/3) -- comparable input gives clean output on both.

## Notes / limitations

- Per-instance roof colors visualize segmentation granularity; not a matched
  correspondence between ALS, DIM, and reference.
- Two/three illustrative buildings only; population statistics are in W3-2c.
- Reference LoD2 (CityGML 1.0) is shown for visual context, not a read-out input.
- Visuals/counts only; no GO/NO-GO judgement is made.

## Files

- Figure A: `{OUT_FIG_A}`
- Figure B: `{OUT_FIG_B}`
- Report: `{REPORT_MD}`
"""
    (root / REPORT_MD).write_text(text, encoding="utf-8")


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
    return "\n".join(out)


def add_to_g1_package(root: Path) -> None:
    package = root / "docs/G1_package"
    package_figs = package / "figs"
    package.mkdir(parents=True, exist_ok=True)
    package_figs.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / OUT_FIG_A, package_figs / PKG_FIG_A)
    shutil.copy2(root / OUT_FIG_B, package_figs / PKG_FIG_B)
    shutil.copy2(root / REPORT_MD, package / "W3_qualitative_compare.md")
    update_package_captions(package / "captions.md")

    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {
        "package": "G1_package", "canonical_run": f"{CANONICAL_RUN}/run_2", "files": [], "figure_count": 0}
    files = set(manifest.get("files", []))
    files.update([f"figs/{PKG_FIG_A}", f"figs/{PKG_FIG_B}", "W3_qualitative_compare.md", "captions.md"])
    manifest["files"] = sorted(files)
    manifest["figure_count"] = sum(1 for f in manifest["files"] if f.startswith("figs/") and f.endswith(".png"))
    manifest["t14_qualitative_figures"] = {
        "report": "W3_qualitative_compare.md",
        "figure_a_texture_to_points": f"figs/{PKG_FIG_A}",
        "figure_b_input_to_output": f"figs/{PKG_FIG_B}",
        "figure_a_buildings": [FIGA_PRIMARY, FIGA_CONTRAST],
        "figure_b_buildings": [b["id"] for b in FIGB_BUILDINGS],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_package_captions(path: Path) -> None:
    captions = [
        (f"| Figure 17 | figs/{PKG_FIG_A} | "
         "T14 Figure A: textureless roof -> empty DIM points for 4907182 (DIM-empty vs DIM-points patch, boxed and "
         "tied to the DIM top-view) with 4908023 textured contrast. No judgement. |"),
        (f"| Figure 18 | figs/{PKG_FIG_B} | "
         "T14 Figure B: input point cloud -> output LoD2 model for 4907182/4906969/4906972 (ALS|DIM input above "
         "ALS|DIM|reference models; cross-sections for 4906969/4906972). No judgement. |"),
    ]
    if not path.exists():
        path.write_text("# G1 Figure Captions\n\n| figure | file | caption |\n| --- | --- | --- |\n"
                        + "\n".join(captions) + "\n", encoding="utf-8")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    for cap in captions:
        tag = cap.split(" |")[0] + " |"
        if any(line.startswith(tag) for line in lines):
            lines = [cap if line.startswith(tag) else line for line in lines]
        else:
            lines.append(cap)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# host entrypoint + plumbing
# ---------------------------------------------------------------------------
def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("t14_qualitative_figures_%Y%m%d_%H%M%S")
    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()
    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    write_host_config(run_dir, run_id, git_commit)
    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]
    if env.get("SKIP_BUILD") != "1":
        run(compose + ["build", "tools"], cwd=repo, env=env, log_path=logs_dir / "build_tools.log")
    write_host_versions(repo, run_dir, compose, env, git_commit)
    try:
        run(compose + ["run", "-T", "--rm", "-e", "P0_INSIDE_CONTAINER=1", "-e", f"RUN_ID={run_id}",
                       "-e", f"P0_GIT_COMMIT={git_commit}", "tools", "python",
                       "/workspace/scripts/14_qualitative_figures.py", "--mode", "compute"],
            cwd=repo, env=env, log_path=logs_dir / "compute.log")
    except subprocess.CalledProcessError as exc:
        record_issue(repo, run_id, f"failed with exit code {exc.returncode}")
        raise
    print(f"run_id={run_id}")
    print(f"run_dir=runs/{run_id}")
    print(f"figureA={OUT_FIG_A}")
    print(f"figureB={OUT_FIG_B}")


def write_host_config(run_dir: Path, run_id: str, git_commit: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.yaml").write_text("\n".join([
        f"task_id: {TASK_ID}", f"run_id: {run_id}", f"git_commit: {git_commit}", f"canonical_run: {RUN_REL}",
        f"als_cityjson: {ALS_CITYJSON}", f"dim_cityjson: {DIM_CITYJSON}",
        "reference_lod2: data/raw/lod2/690_5334.gml, data/raw/lod2/690_5336.gml (CityGML 1.0)",
        f"figure_a_buildings: {FIGA_PRIMARY}, {FIGA_CONTRAST}",
        "figure_b_buildings: " + ", ".join(b["id"] for b in FIGB_BUILDINGS),
        "crs: EPSG:25832 numeric UTM32 coordinates",
        "task_kind: qualitative render (texture->points, points->model); no geometry tool re-run; no judgement",
        "",
    ]), encoding="utf-8")


def write_host_versions(repo: Path, run_dir: Path, compose: list[str], env: dict[str, str], git_commit: str) -> None:
    lines = ["# T14 Qualitative Figures Tool Versions", "",
             f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
             f"- Run ID: {run_dir.name}", f"- Repository commit: {git_commit}", "", "```console"]
    cmds = [["git", "status", "--short", "--branch"],
            compose + ["run", "-T", "--rm", "tools", "python", "--version"],
            compose + ["run", "-T", "--rm", "tools", "python", "-c",
                       "import matplotlib, numpy, laspy, PIL; print('matplotlib=' + matplotlib.__version__); "
                       "print('numpy=' + numpy.__version__); print('laspy=' + laspy.__version__); print('Pillow=' + PIL.__version__)"],
            compose + ["run", "-T", "--rm", "tools", "ogrinfo", "--version"]]
    for cmd in cmds:
        proc = subprocess.run(cmd, cwd=repo, env=env, text=True, capture_output=True, check=False)
        lines.append("$ " + " ".join(cmd))
        out = (proc.stdout or proc.stderr).strip()
        if out:
            lines.append(out)
        if proc.returncode != 0:
            lines.append(f"[exit {proc.returncode}]")
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_outputs(run_dir: Path, paths: list[Path]) -> None:
    snapshot = run_dir / "outputs"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if not path.exists():
            continue
        if path.is_relative_to(Path("/workspace/docs")):
            dst = snapshot / "docs" / path.relative_to(Path("/workspace/docs"))
        else:
            dst = snapshot / path.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)


def record_issue(repo: Path, run_id: str, message: str) -> None:
    issues = repo / "docs/issues.md"
    with issues.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {TASK_ID} Qualitative Figures\n\n- {run_id}: {message}. See runs/{run_id}/logs/.\n")


def load_helper_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load helper module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None,
        log_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    if log_path:
        with log_path.open("w", encoding="utf-8") as log:
            log.write("+ " + " ".join(cmd) + "\n")
            proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log.write(proc.stdout)
            print(proc.stdout, end="", flush=True)
            proc.check_returncode()
            return proc
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, check=True)


def capture(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return proc.stdout


def main() -> None:
    if os.environ.get("P0_INSIDE_CONTAINER") == "1":
        compute_entrypoint()
    else:
        host_entrypoint()


if __name__ == "__main__":
    main()

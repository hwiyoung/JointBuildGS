#!/usr/bin/env python3
"""cards-v4-kit: manual-review judgment cards.

Read/render only. No reconstruction or retraining. Geo outputs are EPSG:25832;
OPF/COLMAP uses EPSG:32632-local camera coordinates with image-projection
vertical datum controlled by configs/projection_datum.json.
"""
from __future__ import annotations

import csv
import json
import math
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import laspy
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from evidence_cards_v2 import (  # noqa: E402
    ALS_TILES,
    DATA,
    DIM_CLOUD,
    GMLDIR,
    GEOJSON,
    IMAGE_DIR,
    REPO,
    clip_poly_rect,
    distort,
    parse_cam_model,
    parse_cameras,
    proj_ring,
    to_cam,
)
from projection_datum import describe_projection_config, projection_geoid_m  # noqa: E402


RUN_ID = "20260703_cards_v4_kit"
RUN_DIR = REPO / "phases" / "p2-gsjso" / "runs" / RUN_ID
DOCS = REPO / "docs"
OUT_DIR = DOCS / "evidence" / "judgment_kit_v4"
POP = DOCS / "population_aux_v4.csv"
LOWTEX = DOCS / "lowtex_v5.csv"
CROSS = DOCS / "bucket_crosswalk_v2.csv"
MANUAL = DOCS / "manual_review_judgments.csv"
SHAPE_FLAGS = DOCS / "footprint_shape_flags.csv"
REPORT = DOCS / "judgment_kit_v4_report.md"
EVCARD_V3 = SCRIPT_DIR / "aux_v4b.py"
EVCARD_V2 = SCRIPT_DIR / "evidence_cards_v2.py"
EVAL = REPO / "phases/p0-audit/runs/mob_eval"
IMAGERY_DATE = "2024-12-17"
TIME_DIFF_LOCATORS = ["42364663", "4959320"]
TINY_EXAMPLES = ["104583794", "108247350", "4908160", "4908169", "8568392"]


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception as exc:  # pragma: no cover
        return f"unavailable: {exc}"


def read_rows(path: Path) -> list[dict[str, str]]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in cols})


def fnum(v, default: float | None = None) -> float | None:
    try:
        if v in ("", None):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def short_bid(bid: str) -> str:
    return bid.replace("DEBY_LOD2_", "")


def full_bid(bid: str) -> str:
    return bid if bid.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{bid}"


def close_ring(ring: np.ndarray) -> np.ndarray:
    r = np.asarray(ring, float)
    if len(r) and not np.allclose(r[0, :2], r[-1, :2]):
        r = np.vstack([r, r[0]])
    return r


def polygon_area(ring: np.ndarray) -> float:
    r = close_ring(np.asarray(ring, float))
    if len(r) < 4:
        return 0.0
    x, y = r[:, 0], r[:, 1]
    return float(abs(0.5 * np.sum(x[:-1] * y[1:] - x[1:] * y[:-1])))


def polygon_perimeter(ring: np.ndarray) -> float:
    r = close_ring(np.asarray(ring, float))
    if len(r) < 2:
        return 0.0
    d = np.diff(r[:, :2], axis=0)
    return float(np.sqrt((d * d).sum(axis=1)).sum())


def shape_metrics(ring: np.ndarray) -> dict[str, object]:
    r = close_ring(ring)
    area = polygon_area(r)
    perim = polygon_perimeter(r)
    width = float(r[:, 0].max() - r[:, 0].min())
    height = float(r[:, 1].max() - r[:, 1].min())
    if min(width, height) <= 1e-9:
        aspect = float("inf")
    else:
        aspect = float(max(width / height, height / width))
    iso = float(perim * perim / (4.0 * math.pi * area)) if area > 0 else float("inf")
    return {
        "area_m2": round(area, 3),
        "bbox_width_m": round(width, 3),
        "bbox_height_m": round(height, 3),
        "bbox_aspect_ratio": round(aspect, 3) if np.isfinite(aspect) else "inf",
        "perimeter_m": round(perim, 3),
        "isoperimetric": round(iso, 3) if np.isfinite(iso) else "inf",
        "small_flag": int(area < 50.0),
        "elong_flag": int((aspect >= 3.0) or (iso >= 3.0)),
    }


def load_footprints() -> dict[str, np.ndarray]:
    feats = json.load(open(GEOJSON))["features"]
    out: dict[str, np.ndarray] = {}
    for feat in feats:
        bid = short_bid(feat["properties"]["building_id"])
        geom = feat["geometry"]
        if geom["type"] == "Polygon":
            candidates = [np.asarray(geom["coordinates"][0], float)]
        else:
            candidates = [np.asarray(poly[0], float) for poly in geom["coordinates"]]
        ring = max(candidates, key=polygon_area)
        if bid not in out or polygon_area(ring) > polygon_area(out[bid]):
            out[bid] = close_ring(ring)
    return out


@lru_cache(maxsize=None)
def gml_building_cached(bid: str) -> dict[str, object] | None:
    full = full_bid(bid)
    for gml in sorted(GMLDIR.glob("*.gml")):
        for _, el in ET.iterparse(gml, events=("end",)):
            if el.tag.rsplit("}", 1)[-1] != "Building":
                continue
            got = next((v for k, v in el.attrib.items() if k.rsplit("}", 1)[-1] == "id"), None)
            if got != full:
                el.clear()
                continue

            def rings(kind: str) -> list[np.ndarray]:
                rr: list[np.ndarray] = []
                for surf in el.iter():
                    if surf.tag.rsplit("}", 1)[-1] != kind:
                        continue
                    for pl in surf.iter():
                        if pl.tag.rsplit("}", 1)[-1] == "posList" and pl.text:
                            rr.append(np.asarray([float(x) for x in pl.text.split()], float).reshape(-1, 3))
                return rr

            roof_type = next((e.text.strip() for e in el.iter() if e.tag.rsplit("}", 1)[-1] == "roofType" and e.text), "NONE")
            creation = next((e.text for e in el.iter() if e.tag.rsplit("}", 1)[-1] == "creationDate"), "")
            grundriss = ""
            for e in el.iter():
                nm = e.attrib.get("name") or next((v for k, v in e.attrib.items() if k.rsplit("}", 1)[-1] == "name"), None)
                if nm == "Grundrissaktualitaet":
                    grundriss = next((c.text for c in e if c.tag.rsplit("}", 1)[-1] == "value"), "") or ""
            rec = {"roof": rings("RoofSurface"), "wall": rings("WallSurface"), "roofType": roof_type, "creationDate": creation, "grundriss": grundriss}
            el.clear()
            return rec
    return None


@lru_cache(maxsize=1)
def roof_height_index() -> dict[str, float]:
    out: dict[str, float] = {}
    for gml in sorted(GMLDIR.glob("*.gml")):
        for _, el in ET.iterparse(gml, events=("end",)):
            if el.tag.rsplit("}", 1)[-1] != "Building":
                continue
            got = next((v for k, v in el.attrib.items() if k.rsplit("}", 1)[-1] == "id"), None)
            if not got:
                el.clear()
                continue
            roof_pts = []
            for surf in el.iter():
                if surf.tag.rsplit("}", 1)[-1] != "RoofSurface":
                    continue
                for pl in surf.iter():
                    if pl.tag.rsplit("}", 1)[-1] == "posList" and pl.text:
                        roof_pts.append(np.asarray([float(x) for x in pl.text.split()], float).reshape(-1, 3))
            if roof_pts:
                out[short_bid(got)] = float(np.median(np.vstack(roof_pts)[:, 2]))
            el.clear()
    return out


def roof_height_for_bid(bid: str, fallback: float = 0.0) -> float:
    return roof_height_index().get(short_bid(bid), fallback)


def roof_height(gb: dict[str, object] | None, fallback: float = 0.0) -> float:
    if not gb or not gb.get("roof"):
        return fallback
    return float(np.median(np.vstack(gb["roof"])[:, 2]))


def ground_height(gb: dict[str, object] | None, fallback: float = 0.0) -> float:
    if not gb:
        return fallback
    rings = list(gb.get("roof") or []) + list(gb.get("wall") or [])
    if not rings:
        return fallback
    return float(np.vstack(rings)[:, 2].min())


def centroid_xy(ring: np.ndarray) -> np.ndarray:
    r = close_ring(ring)
    return np.asarray([float(r[:-1, 0].mean()), float(r[:-1, 1].mean())])


def point_uv(point3: np.ndarray, cam, params: np.ndarray, sr: dict) -> tuple[np.ndarray | None, bool]:
    cc = to_cam(np.asarray(point3, float)[None], cam, sr)
    if cc[0, 2] <= 1.0:
        return None, False
    uv = distort(cc, params)[0]
    return uv, True


def in_frame(uv: np.ndarray | None, width: int, height: int, margin: float = 0.0) -> bool:
    if uv is None or not np.isfinite(uv).all():
        return False
    return margin <= uv[0] < width - margin and margin <= uv[1] < height - margin


def zenith_deg(cam, target3: np.ndarray) -> float:
    v = cam.center - np.asarray(target3, float)
    n = float(np.linalg.norm(v))
    if n <= 1e-9:
        return float("nan")
    return math.degrees(math.acos(min(1.0, max(-1.0, abs(v[2]) / n))))


def nearest_neighbors(bid: str, footprints: dict[str, np.ndarray], n: int = 3) -> list[str]:
    c0 = centroid_xy(footprints[bid])
    rows = []
    for other, ring in footprints.items():
        if other == bid:
            continue
        rows.append((float(np.linalg.norm(centroid_xy(ring) - c0)), other))
    rows.sort()
    return [b for _, b in rows[:n]]


def footprint_at_roof(bid: str, ring: np.ndarray) -> np.ndarray:
    z = roof_height_for_bid(bid, 0.0)
    return np.column_stack([ring[:, 0], ring[:, 1], np.full(len(ring), z, dtype=float)])


def projected_ring_at_roof(bid: str, ring: np.ndarray, cam, params: np.ndarray, sr: dict) -> np.ndarray | None:
    return proj_ring(footprint_at_roof(bid, ring), cam, params, sr)


def clipped_uv_for_bbox(uv: np.ndarray | None, width: int, height: int) -> np.ndarray | None:
    if uv is None or len(uv) < 3:
        return None
    cp = clip_poly_rect(uv, 0, 0, width - 1, height - 1)
    if len(cp) < 2:
        return None
    return np.asarray(cp, float)


def ring_visible_in_frame(uv: np.ndarray | None, width: int, height: int) -> bool:
    cp = clipped_uv_for_bbox(uv, width, height)
    if cp is None or len(cp) < 2:
        return False
    return bool(np.ptp(cp[:, 0]) >= 3.0 or np.ptp(cp[:, 1]) >= 3.0)


def projected_neighbor_rings(
    bid: str,
    footprints: dict[str, np.ndarray],
    cam,
    params: np.ndarray,
    sr: dict,
    width: int,
    height: int,
    n: int = 3,
    search_n: int = 120,
) -> list[tuple[str, np.ndarray | None]]:
    selected: list[tuple[str, np.ndarray | None]] = []
    for nb in nearest_neighbors(bid, footprints, n=search_n):
        uv = projected_ring_at_roof(nb, footprints[nb], cam, params, sr)
        if ring_visible_in_frame(uv, width, height):
            selected.append((nb, uv))
        if len(selected) >= n:
            break
    return selected


def neighbor_center_ids_for_view(
    bid: str,
    footprints: dict[str, np.ndarray],
    cam,
    params: np.ndarray,
    sr: dict,
    width: int,
    height: int,
    z_ref: float,
    n: int = 3,
    search_n: int = 120,
    candidate_ids: list[str] | None = None,
) -> list[str]:
    selected: list[str] = []
    source_ids = candidate_ids if candidate_ids is not None else nearest_neighbors(bid, footprints, n=search_n)
    for nb in source_ids[:search_n]:
        ctr = np.array([*centroid_xy(footprints[nb]), z_ref])
        uv, front = point_uv(ctr, cam, params, sr)
        if front and in_frame(uv, width, height, margin=15.0):
            selected.append(nb)
        if len(selected) >= n:
            break
    return selected


def select_locator_view(
    bid: str,
    ring: np.ndarray,
    footprints: dict[str, np.ndarray],
    cams,
    params: np.ndarray,
    sr: dict,
    width: int,
    height: int,
):
    z_ref = roof_height_for_bid(bid)
    ctr = np.array([*centroid_xy(ring), z_ref])
    near_ids = nearest_neighbors(bid, footprints, n=120)
    candidates = []
    fallback = []
    for cam in cams:
        ctr_uv, front = point_uv(ctr, cam, params, sr)
        if not front:
            continue
        target_uv = projected_ring_at_roof(bid, ring, cam, params, sr)
        if not ring_visible_in_frame(target_uv, width, height):
            continue
        z = zenith_deg(cam, ctr)
        neighbors = neighbor_center_ids_for_view(bid, footprints, cam, params, sr, width, height, z_ref, n=3, candidate_ids=near_ids)
        row = (z, cam, ctr_uv, neighbors)
        if in_frame(ctr_uv, width, height, margin=5.0):
            candidates.append(row)
        else:
            fallback.append((0 if in_frame(ctr_uv, width, height) else 1, -len(neighbors), z, cam, ctr_uv, neighbors))
    if candidates:
        candidates.sort(key=lambda t: t[0])
        z, cam, ctr_uv, neighbors = candidates[0]
        return cam, ctr_uv, float(z), f"center_inframe_min_zenith_neighbor_centers_{len(neighbors)}", neighbors
    if fallback:
        fallback.sort(key=lambda t: (t[0], t[1], t[2]))
        _, _, z, cam, ctr_uv, neighbors = fallback[0]
        return cam, ctr_uv, float(z), f"fallback_front_or_edge_visible_neighbors_{len(neighbors)}", neighbors
    return None, None, float("nan"), "no_view", []


def bbox_from_uv(arrays: Iterable[np.ndarray | None], width: int, height: int, pad: int, min_size: int) -> tuple[int, int, int, int] | None:
    pts = []
    for a in arrays:
        if a is None or len(a) == 0:
            continue
        aa = np.asarray(a, float)
        m = np.isfinite(aa[:, 0]) & np.isfinite(aa[:, 1])
        if m.any():
            pts.append(aa[m])
    if not pts:
        return None
    p = np.vstack(pts)
    x0 = float(np.clip(np.nanmin(p[:, 0]) - pad, 0, width - 1))
    y0 = float(np.clip(np.nanmin(p[:, 1]) - pad, 0, height - 1))
    x1 = float(np.clip(np.nanmax(p[:, 0]) + pad, 1, width))
    y1 = float(np.clip(np.nanmax(p[:, 1]) + pad, 1, height))
    cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    half = max(0.5 * (x1 - x0), 0.5 * (y1 - y0), 0.5 * min_size)
    x0 = max(0, int(round(cx - half)))
    y0 = max(0, int(round(cy - half)))
    x1 = min(width, int(round(cx + half)))
    y1 = min(height, int(round(cy + half)))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    return x0, y0, x1, y1


def draw_clipped_ring(ax, uv: np.ndarray | None, bbox, color: str, lw: float, label_text: str | None = None, alpha: float = 1.0, linestyle: str = "-") -> bool:
    if uv is None or len(uv) < 3:
        return False
    x0, y0, x1, y1 = bbox
    cp = clip_poly_rect(uv, x0, y0, x1, y1)
    if len(cp) < 2:
        return False
    q = np.asarray(cp + [cp[0]], float)
    ax.plot(q[:, 0] - x0, q[:, 1] - y0, linestyle, color=color, lw=lw, alpha=alpha)
    if label_text:
        c = np.mean(q[:-1], axis=0)
        ax.text(c[0] - x0, c[1] - y0, label_text, color=color, fontsize=6.4, ha="center", va="center", weight="bold")
    return True


def crop_image(image: np.ndarray, bbox):
    x0, y0, x1, y1 = bbox
    return image[y0:y1, x0:x1]


def load_las_points(path: Path, class6_only: bool = True) -> tuple[np.ndarray, np.ndarray, int]:
    if not path.exists():
        return np.zeros((0, 2), dtype=float), np.zeros(0, dtype=float), 0
    las = laspy.read(path)
    x = np.asarray(las.x, dtype=float)
    y = np.asarray(las.y, dtype=float)
    z = np.asarray(las.z, dtype=float)
    cls = np.asarray(getattr(las, "classification", np.zeros_like(z, dtype=np.uint8)))
    m = cls == 6 if class6_only and len(cls) else np.ones_like(z, dtype=bool)
    if not m.any() and class6_only:
        m = np.ones_like(z, dtype=bool)
    return np.column_stack([x[m], y[m]]), z[m], int(m.sum())


def fallback_dim_points(ring: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    las = laspy.read(str(DIM_CLOUD))
    xy = np.column_stack([np.asarray(las.x), np.asarray(las.y)]).astype(float)
    z = np.asarray(las.z, dtype=float)
    cls = np.asarray(getattr(las, "classification", np.zeros_like(z, dtype=np.uint8)))
    bb = [ring[:, 0].min() - 2, ring[:, 1].min() - 2, ring[:, 0].max() + 2, ring[:, 1].max() + 2]
    m = (xy[:, 0] >= bb[0]) & (xy[:, 0] <= bb[2]) & (xy[:, 1] >= bb[1]) & (xy[:, 1] <= bb[3])
    if len(cls):
        m &= cls == 6
    return xy[m], z[m], int(m.sum())


def fallback_als_points(ring: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    bb = [ring[:, 0].min() - 2, ring[:, 1].min() - 2, ring[:, 0].max() + 2, ring[:, 1].max() + 2]
    chunks_xy, chunks_z = [], []
    for tile in ALS_TILES:
        with laspy.open(tile) as fh:
            h = fh.header
            if h.x_max < bb[0] or h.x_min > bb[2] or h.y_max < bb[1] or h.y_min > bb[3]:
                continue
        las = laspy.read(tile)
        xy = np.column_stack([np.asarray(las.x), np.asarray(las.y)]).astype(float)
        z = np.asarray(las.z, dtype=float)
        cls = np.asarray(getattr(las, "classification", np.zeros_like(z, dtype=np.uint8)))
        m = (xy[:, 0] >= bb[0]) & (xy[:, 0] <= bb[2]) & (xy[:, 1] >= bb[1]) & (xy[:, 1] <= bb[3])
        if len(cls):
            m &= cls == 6
        if m.any():
            chunks_xy.append(xy[m])
            chunks_z.append(z[m])
    if not chunks_xy:
        return np.zeros((0, 2), dtype=float), np.zeros(0, dtype=float), 0
    xy = np.vstack(chunks_xy)
    z = np.concatenate(chunks_z)
    return xy, z, int(len(z))


def cloud_for(bid: str, ring: np.ndarray, arm: str) -> tuple[np.ndarray, np.ndarray, int, str]:
    path = EVAL / arm / f"{full_bid(bid)}_orig_classified.las"
    xy, z, n = load_las_points(path, class6_only=True)
    source = str(path.relative_to(REPO)) if path.exists() else "fallback_global"
    if n == 0 and arm == "raw_dense":
        xy, z, n = fallback_dim_points(ring)
    if n == 0 and arm == "raw_lidar":
        xy, z, n = fallback_als_points(ring)
    return xy, z, n, source


def inside_clip(xy: np.ndarray, z: np.ndarray, ring: np.ndarray, margin: float = 2.0):
    if len(xy) == 0:
        return xy, z, np.zeros(0, dtype=bool)
    bb = [ring[:, 0].min() - margin, ring[:, 1].min() - margin, ring[:, 0].max() + margin, ring[:, 1].max() + margin]
    m = (xy[:, 0] >= bb[0]) & (xy[:, 0] <= bb[2]) & (xy[:, 1] >= bb[1]) & (xy[:, 1] <= bb[3])
    xy2 = xy[m]
    z2 = z[m]
    inside = MplPath(ring[:, :2]).contains_points(xy2) if len(xy2) else np.zeros(0, dtype=bool)
    return xy2, z2, inside


def draw_topview(ax, xy: np.ndarray, z: np.ndarray, ring: np.ndarray, title: str, point_size: float, cmap: str = "viridis"):
    xy2, z2, inside = inside_clip(xy, z, ring)
    ring2 = close_ring(ring)
    if len(xy2):
        sc = ax.scatter(xy2[:, 0], xy2[:, 1], c=z2, s=point_size, cmap=cmap, alpha=0.9, linewidths=0)
        plt.colorbar(sc, ax=ax, fraction=0.045, pad=0.01, label="Z m")
    else:
        ax.text(0.5, 0.5, "no class-6 points", transform=ax.transAxes, ha="center", va="center", fontsize=8)
    ax.plot(ring2[:, 0], ring2[:, 1], color="red", lw=1.4)
    ax.set_xlim(ring2[:, 0].min() - 2, ring2[:, 0].max() + 2)
    ax.set_ylim(ring2[:, 1].min() - 2, ring2[:, 1].max() + 2)
    ax.set_aspect("equal")
    ax.set_title(f"{title} | in footprint n={int(inside.sum())}", fontsize=8.0)
    ax.tick_params(labelsize=6)
    ax.set_xlabel("E", fontsize=7)
    ax.set_ylabel("N", fontsize=7)
    return int(inside.sum()), len(xy2)


def render_locator_panel(ax, image: np.ndarray, bbox, target_uv, neighbor_uvs: list[tuple[str, np.ndarray | None]], bid: str, view_name: str, zenith: float):
    ax.imshow(crop_image(image, bbox))
    ax.axis("off")
    drawn_neighbors = 0
    for nb, uv in neighbor_uvs:
        if draw_clipped_ring(ax, uv, bbox, color="#c9c9c9", lw=0.9, label_text=nb, alpha=0.9):
            drawn_neighbors += 1
    draw_clipped_ring(ax, target_uv, bbox, color="red", lw=2.2, label_text=bid, alpha=0.98)
    ax.set_title(f"locator | {view_name} | zenith={zenith:.1f} deg", fontsize=8.0)
    return drawn_neighbors


def render_closeup_panel(ax, image: np.ndarray, bbox, target_uv, view_name: str, zenith: float):
    ax.imshow(crop_image(image, bbox))
    ax.axis("off")
    draw_clipped_ring(ax, target_uv, bbox, color="red", lw=1.7, label_text=None, alpha=0.92)
    ax.set_title(f"roof close-up | same view | zenith={zenith:.1f} deg", fontsize=8.0)


def header_line(row: dict[str, str], cross: dict[str, str], low: dict[str, str], shape: dict[str, object]) -> str:
    return (
        f"area={shape['area_m2']}m2 small={shape['small_flag']} elong={shape['elong_flag']} | "
        f"DIMdens={cross.get('dim_rf_pt_density','')} n_nadir={cross.get('n_views_nadir','')} "
        f"inc60={cross.get('frac_views_incidence_le60','')} recon={cross.get('recon_score_median','')} "
        f"occl={row.get('occlusion_frac_approx','')} | "
        f"lowtex-v5={low.get('roof_lowtex_v5','')}@{low.get('lowtex_v5_zenith_deg','')}deg "
        f"veto={cross.get('veto_recovered','') or 'none'}"
    )


def source_batch(manual_rows: dict[str, dict[str, str]], bid: str) -> tuple[str, str]:
    if not manual_rows:
        return "", "docs/research/methodology/tables/manual_review_judgments.csv missing"
    row = manual_rows.get(full_bid(bid)) or manual_rows.get(bid) or {}
    return row.get("batch", row.get("batch_id", row.get("배치", ""))), "docs/research/methodology/tables/manual_review_judgments.csv"


def render_manual_card(
    bid: str,
    ring: np.ndarray,
    shape: dict[str, object],
    pop_by: dict[str, dict[str, str]],
    cross_by: dict[str, dict[str, str]],
    low_by: dict[str, dict[str, str]],
    manual_by: dict[str, dict[str, str]],
    footprints: dict[str, np.ndarray],
    cams,
    params,
    sr,
    width: int,
    height: int,
) -> dict[str, object]:
    gb = gml_building_cached(bid)
    cam, ctr_uv, zenith, view_reason, neighbor_ids = select_locator_view(bid, ring, footprints, cams, params, sr, width, height)
    if cam is None:
        raise RuntimeError(f"no locator view for {bid}")
    image = np.asarray(Image.open(IMAGE_DIR / cam.name).convert("RGB"))
    target_uv = projected_ring_at_roof(bid, ring, cam, params, sr)
    neighbor_uvs = [(nb, projected_ring_at_roof(nb, footprints[nb], cam, params, sr)) for nb in neighbor_ids]
    if sum(1 for _, uv in neighbor_uvs if ring_visible_in_frame(uv, width, height)) < 2:
        neighbor_uvs = projected_neighbor_rings(bid, footprints, cam, params, sr, width, height, n=3, search_n=120)
    loc_bbox = bbox_from_uv(
        [
            clipped_uv_for_bbox(target_uv, width, height),
            *[clipped_uv_for_bbox(uv, width, height) for _, uv in neighbor_uvs],
            ctr_uv[None] if ctr_uv is not None else None,
        ],
        width,
        height,
        pad=230,
        min_size=980,
    )
    close_bbox = bbox_from_uv([clipped_uv_for_bbox(target_uv, width, height)], width, height, pad=80, min_size=360)
    if loc_bbox is None:
        loc_bbox = close_bbox
    if close_bbox is None:
        close_bbox = loc_bbox
    dim_xy, dim_z, dim_n, dim_source = cloud_for(bid, ring, "raw_dense")
    als_xy, als_z, als_n, als_source = cloud_for(bid, ring, "raw_lidar")
    als_marker_scale = 3 if als_n < 500 else 1
    als_point_size = 9.0 if als_n < 500 else 3.0
    dim_point_size = 3.0
    fig, axes = plt.subplots(2, 2, figsize=(13.6, 10.2))
    drawn_neighbors = render_locator_panel(axes[0, 0], image, loc_bbox, target_uv, neighbor_uvs, bid, cam.name, zenith)
    render_closeup_panel(axes[0, 1], image, close_bbox, target_uv, cam.name, zenith)
    dim_inside, dim_clip = draw_topview(axes[1, 0], dim_xy, dim_z, ring, "DIM(classified) top-view", dim_point_size)
    als_inside, als_clip = draw_topview(axes[1, 1], als_xy, als_z, ring, f"ALS top-view height-colored (marker x{als_marker_scale})", als_point_size)
    pop = pop_by.get(full_bid(bid), {})
    cross = cross_by.get(full_bid(bid), {})
    low = low_by.get(full_bid(bid), {})
    batch, batch_source = source_batch(manual_by, bid)
    fig.suptitle(f"DEBY_LOD2_{bid} | {header_line(pop, cross, low, shape)}", fontsize=8.5)
    fig.text(
        0.5,
        0.016,
        "Color rules: locator red=target roof-height footprint, gray=neighbor roof-height footprints+ID; close-up red=target footprint; top-view red=EPSG:25832 footprint, viridis=height.",
        ha="center",
        fontsize=7.0,
    )
    fig.tight_layout(rect=[0, 0.035, 1, 0.955])
    out = OUT_DIR / f"{bid}.png"
    fig.savefig(out, dpi=125)
    plt.close(fig)
    return {
        "building_id": full_bid(bid),
        "card_type": "manual_review",
        "figure": str(out.relative_to(REPO)),
        "locator_view": cam.name,
        "locator_zenith_deg": round(float(zenith), 3),
        "view_reason": view_reason,
        "neighbor_ids": ";".join(full_bid(n) for n, _ in neighbor_uvs),
        "neighbor_rings_drawn": drawn_neighbors,
        "manual_batch": batch,
        "manual_source": batch_source,
        "area_m2": shape["area_m2"],
        "small_flag": shape["small_flag"],
        "elong_flag": shape["elong_flag"],
        "bbox_aspect_ratio": shape["bbox_aspect_ratio"],
        "isoperimetric": shape["isoperimetric"],
        "dim_density": cross.get("dim_rf_pt_density", ""),
        "n_views_nadir": cross.get("n_views_nadir", ""),
        "inc60": cross.get("frac_views_incidence_le60", ""),
        "recon_score": cross.get("recon_score_median", ""),
        "occlusion": pop.get("occlusion_frac_approx", ""),
        "lowtex_v5": low.get("roof_lowtex_v5", ""),
        "lowtex_v5_zenith_deg": low.get("lowtex_v5_zenith_deg", ""),
        "veto_recovered": cross.get("veto_recovered", ""),
        "dim_points_in_footprint": dim_inside,
        "dim_points_plotted": dim_clip,
        "dim_source": dim_source,
        "als_points_in_footprint": als_inside,
        "als_points_plotted": als_clip,
        "als_source": als_source,
        "als_marker_scale": als_marker_scale,
        "observation": "4-panel kit: locator, roof close-up, DIM top-view, ALS top-view; render only.",
    }


def render_time_locator(
    bid: str,
    ring: np.ndarray,
    footprints: dict[str, np.ndarray],
    cams,
    params,
    sr,
    width: int,
    height: int,
    pop_by: dict[str, dict[str, str]],
) -> dict[str, object]:
    cam, ctr_uv, zenith, view_reason, neighbor_ids = select_locator_view(bid, ring, footprints, cams, params, sr, width, height)
    if cam is None:
        raise RuntimeError(f"no time locator view for {bid}")
    image = np.asarray(Image.open(IMAGE_DIR / cam.name).convert("RGB"))
    target_uv = projected_ring_at_roof(bid, ring, cam, params, sr)
    neighbor_uvs = [(nb, projected_ring_at_roof(nb, footprints[nb], cam, params, sr)) for nb in neighbor_ids]
    if sum(1 for _, uv in neighbor_uvs if ring_visible_in_frame(uv, width, height)) < 2:
        neighbor_uvs = projected_neighbor_rings(bid, footprints, cam, params, sr, width, height, n=3, search_n=120)
    bbox = bbox_from_uv(
        [
            clipped_uv_for_bbox(target_uv, width, height),
            *[clipped_uv_for_bbox(uv, width, height) for _, uv in neighbor_uvs],
            ctr_uv[None] if ctr_uv is not None else None,
        ],
        width,
        height,
        pad=260,
        min_size=1100,
    )
    if bbox is None:
        raise RuntimeError(f"no bbox for {bid}")
    fig, ax = plt.subplots(1, 1, figsize=(8.8, 7.1))
    drawn_neighbors = render_locator_panel(ax, image, bbox, target_uv, neighbor_uvs, bid, cam.name, zenith)
    row = pop_by.get(full_bid(bid), {})
    title = f"DEBY_LOD2_{bid} time/check locator | recon={row.get('recon_score_median','')} n_nadir={row.get('n_views_nadir','')} ALS note source=v3 manifest"
    fig.suptitle(title, fontsize=8.6)
    fig.text(0.5, 0.02, "Color rules: red=target roof-height footprint; gray=neighbor roof-height footprints+ID. Render only.", ha="center", fontsize=7.4)
    fig.tight_layout(rect=[0, 0.04, 1, 0.95])
    out = OUT_DIR / f"timediff_{bid}_locator.png"
    fig.savefig(out, dpi=125)
    plt.close(fig)
    return {
        "building_id": full_bid(bid),
        "card_type": "time_diff_locator",
        "figure": str(out.relative_to(REPO)),
        "locator_view": cam.name,
        "locator_zenith_deg": round(float(zenith), 3),
        "view_reason": view_reason,
        "neighbor_ids": ";".join(full_bid(n) for n, _ in neighbor_uvs),
        "neighbor_rings_drawn": drawn_neighbors,
        "manual_batch": "",
        "manual_source": "nonblocking time-diff locator",
        "area_m2": row.get("footprint_area_m2", ""),
        "small_flag": "",
        "elong_flag": "",
        "bbox_aspect_ratio": "",
        "isoperimetric": "",
        "dim_density": "",
        "n_views_nadir": row.get("n_views_nadir", ""),
        "inc60": row.get("frac_views_incidence_le60", ""),
        "recon_score": row.get("recon_score_median", ""),
        "occlusion": row.get("occlusion_frac_approx", ""),
        "lowtex_v5": row.get("roof_lowtex_v5", ""),
        "lowtex_v5_zenith_deg": row.get("lowtex_v5_zenith_deg", ""),
        "veto_recovered": "",
        "dim_points_in_footprint": "",
        "dim_points_plotted": "",
        "dim_source": "",
        "als_points_in_footprint": "",
        "als_points_plotted": "",
        "als_source": "docs/evidence/evidence_cards_v3/manifest.csv for old ALS count",
        "als_marker_scale": "",
        "observation": "nonblocking locator cut; render only.",
    }


def red_channel_note() -> str:
    text = EVCARD_V3.read_text()
    uses = []
    for token in ['c="red"', 'color="red"', '"red"', "'red'"]:
        if token in text:
            uses.append(token)
    if uses:
        return f"evidence_cards_v3 렌더 코드에 빨간색 토큰 {uses}가 있다. 재사용 전 별도 확인이 필요하다."
    return (
        "evidence_cards_v3 렌더 코드에는 빨간 오버레이 채널이 없다. draw_card_panel은 초록 LoD2 링, 청록 LiDAR 점, 흰색 에지 화살표만 쓴다. "
        "이전 패널의 빨강은 v2 ID/footprint 화살표 또는 진단 스크립트 산출로 보이며, v3에서 정의된 채널은 아니다."
    )


def write_shape_flags(manual_bids: list[str], footprints: dict[str, np.ndarray]) -> list[dict[str, object]]:
    rows = []
    for bid in manual_bids:
        ring = footprints[bid]
        m = shape_metrics(ring)
        m.update({"building_id": full_bid(bid), "manual_review_key": bid, "join_key": full_bid(bid)})
        rows.append(m)
    cols = [
        "building_id",
        "manual_review_key",
        "join_key",
        "area_m2",
        "bbox_width_m",
        "bbox_height_m",
        "bbox_aspect_ratio",
        "perimeter_m",
        "isoperimetric",
        "small_flag",
        "elong_flag",
    ]
    write_csv(SHAPE_FLAGS, rows, cols)
    return rows


def write_report(
    manual_bids: list[str],
    manifest: list[dict[str, object]],
    shape_rows: list[dict[str, object]],
    manual_missing: bool,
    red_note: str,
    failures: list[str],
) -> None:
    manual_cards = [m for m in manifest if m["card_type"] == "manual_review"]
    time_cards = [m for m in manifest if m["card_type"] == "time_diff_locator"]
    small = sum(int(r["small_flag"]) for r in shape_rows)
    elong = sum(int(r["elong_flag"]) for r in shape_rows)
    als_lt500 = [m["building_id"] for m in manual_cards if fnum(m.get("als_points_in_footprint"), 0) < 500]
    neighbor_counts = [int(fnum(m.get("neighbor_rings_drawn"), 0) or 0) for m in manual_cards]
    neighbor_min = min(neighbor_counts) if neighbor_counts else 0
    neighbor_lt2 = sum(1 for n in neighbor_counts if n < 2)
    td495 = next((m for m in time_cards if m["building_id"] == "DEBY_LOD2_4959320"), None)
    td495_obs = (
        "4959320 locator는 v4 수치 `recon_score_median=1.461`, 기존 v3 manifest ALS=85,951점 조건과 함께 기록했다. "
        "큰 footprint와 조밀한 ALS 상한이 같은 위치확인 crop에 대응한다는 관찰만 남겼다."
    )
    if td495 is None:
        td495_obs = "4959320 locator는 생성되지 않았다."
    lines = [
        "# judgment_kit_v4_report",
        "",
        "> 재구성/재학습 없음. 판정 금지. 수치·관찰과 산출만 기록한다.",
        "",
        "## 0. 입력과 규약",
        "",
        f"- image-projection zeta: `{describe_projection_config()}`.",
        "- 3D/씨드 경로 `-556`은 건드리지 않았다.",
        "- 지오 산출물 CRS: EPSG:25832. OPF/COLMAP frame: EPSG:32632.",
        f"- 수동판정 대상: `docs/experiments/input-and-alignment/bucket_crosswalk/tables/bucket_crosswalk_v2.csv`의 `new_class=수동판정` {len(manual_bids)}동.",
        f"- `docs/research/methodology/tables/manual_review_judgments.csv`: {'없음 - 배치 열은 비움' if manual_missing else '읽음'}.",
        "",
        "## 1. 산출",
        "",
        f"- `docs/evidence/judgment_kit_v4/*.png`: 수동판정 4칸 카드 {len(manual_cards)}장.",
        f"- 비차단 시간차 locator: {len(time_cards)}장.",
        f"- manifest: `docs/evidence/judgment_kit_v4/manifest.csv`.",
        f"- locator neighbor rings: min={neighbor_min}, lt2={neighbor_lt2}.",
        f"- footprint shape flags: `docs/evidence/judgment_kit_v4/support/footprint_shape_flags.csv` ({len(shape_rows)}동, small={small}, elong={elong}).",
        f"- run versions: `phases/p2-gsjso/runs/{RUN_ID}/versions.txt`.",
        "",
        "## 2. 결함별 조치",
        "",
        "| 결함 | 조치 | 관찰 |",
        "|---|---|---|",
        "| ① 47장 중 30장 footprint 링 부재 | locator 패널을 새로 만들고 target=굵은 빨강 roof-height footprint, neighbor=가는 회색 roof-height footprint+ID로 고정했다. | manifest에 `neighbor_rings_drawn`을 기록했다. |",
        "| ② 초소형 동 crop이 너무 넓음 | locator와 별개로 같은 view의 roof close-up 패널을 두고, target footprint bbox 기준 tight crop을 사용했다. | `small_flag(<50m2)` 동은 shape flags에서 추적 가능하다. |",
        "| ③ 정의 없는 빨간 채널 | v4 footer에 모든 색 규약을 명시했다. | " + red_note + " |",
        "| ④ 구 점군 패널의 오염 투영 혼란 | `docs/evidence/evidence_cards_v1/`과 v2 사진 링을 재사용하지 않고, `configs/projection_datum.json` 기본 45.700 경로로 재투영했다. | top-view는 사진 투영 링 없이 EPSG:25832 footprint만 사용했다. |",
        "| ⑤ ALS 34~287점 동에서 점이 작음 | ALS class-6 in-footprint <500이면 top-view 마커를 3배 키웠다. | 대상: " + ", ".join(als_lt500[:20]) + (" ..." if len(als_lt500) > 20 else "") + f" ({len(als_lt500)}동). |",
        "| ⑥ 4906999 시간차 강기울기 산개 | v3 코드는 class-6 footprint 내부 ALS를 image에 투영하되 사진 occlusion/depth 선별은 하지 않았다. | v4 수동판정 카드에서는 사진 위 ALS 점을 제거하고, 점 증거는 DIM/ALS top-view로 분리했다. |",
        "",
        "## 3. 빨간 채널 정체",
        "",
        f"- {red_note}",
        "- v4 카드 색: locator target red, neighbor gray, close-up target red, top-view footprint red, point color viridis height. 그 외 overlay 색은 쓰지 않았다.",
        "",
        "## 4. 시간차 locator",
        "",
        "- 42364663, 4959320 locator 컷을 같은 roof-height footprint 규약으로 생성했다.",
        f"- {td495_obs}",
        "",
        "## 5. 실패·주의",
        "",
    ]
    if failures:
        lines.extend(f"- {x}" for x in failures)
    else:
        lines.append("- 없음.")
    lines.extend(
        [
            "",
            "## 6. 판정 필요 지점",
            "",
            "1. `docs/research/methodology/tables/manual_review_judgments.csv` 부재 상태에서 `bucket_crosswalk_v2.csv`의 44동 목록을 수동판정 kit 기준으로 사용할지 여부.",
            "2. `small_flag`와 `elong_flag`를 manual_review_judgments.csv에 병합할지 여부.",
            "3. ALS<500점 마커 3배 확대 카드들을 동일 판독 우선순위로 둘지 여부.",
            "4. 4959320의 낮은 관측점수와 조밀 ALS 상한 관찰을 시간차/대조군 논의에 포함할지 여부.",
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n")


def write_versions(manifest: list[dict[str, object]], manual_missing: bool) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id: {RUN_ID}",
        f"git_head: {git_head()}",
        "command: docker run --rm --user $(id -u):$(id -g) -v $PWD:/workspace/JointBuildGS -w /workspace/JointBuildGS jointbuildgs-p0-tools:t0 python3 phases/p2-gsjso/scripts/judgment_kit_v4.py",
        f"projection_config: {describe_projection_config()}",
        f"orthometric_geoid_m: {projection_geoid_m():.6f}",
        "crs: geo EPSG:25832; OPF EPSG:32632",
        "container: jointbuildgs-p0-tools:t0; Docker --user",
        f"python: {platform.python_version()}",
        f"numpy: {np.__version__}",
        "reconstruction_or_retraining: none",
        f"manual_review_judgments_csv_missing: {int(manual_missing)}",
        f"manual_cards: {sum(1 for m in manifest if m['card_type'] == 'manual_review')}",
        f"time_diff_locators: {sum(1 for m in manifest if m['card_type'] == 'time_diff_locator')}",
        "",
    ]
    (RUN_DIR / "versions.txt").write_text("\n".join(lines))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sr = json.load(open(DATA / "work/opf/opf/scene_reference_frame.json"))["base_to_canonical"]
    width, height, params = parse_cam_model(DATA / "work/colmap/sparse/0/cameras.txt")
    cams = parse_cameras(DATA / "work/colmap/sparse/0/images.txt", sr)
    footprints = load_footprints()
    pop_by = {r["building_id"]: r for r in read_rows(POP)}
    low_by = {r["building_id"]: r for r in read_rows(LOWTEX)}
    cross_rows = read_rows(CROSS)
    cross_by = {r["building_id"]: r for r in cross_rows}
    manual_bids = [short_bid(r["building_id"]) for r in cross_rows if r.get("new_class") == "수동판정"]
    manual_missing = not MANUAL.exists()
    manual_by = {r.get("building_id", ""): r for r in read_rows(MANUAL)} if not manual_missing else {}
    shape_rows = write_shape_flags(manual_bids, footprints)
    shape_by = {short_bid(r["building_id"]): r for r in shape_rows}
    failures: list[str] = []
    manifest: list[dict[str, object]] = []
    for i, bid in enumerate(manual_bids, 1):
        try:
            rec = render_manual_card(
                bid,
                footprints[bid],
                shape_by[bid],
                pop_by,
                cross_by,
                low_by,
                manual_by,
                footprints,
                cams,
                params,
                sr,
                width,
                height,
            )
            manifest.append(rec)
            print(f"[cards-v4] manual {i:02d}/{len(manual_bids)} {bid} view={rec['locator_view']} zen={rec['locator_zenith_deg']}", flush=True)
        except Exception as exc:
            failures.append(f"{full_bid(bid)}: {exc}")
            print(f"[cards-v4] FAIL {bid}: {exc}", flush=True)
    for bid in TIME_DIFF_LOCATORS:
        try:
            rec = render_time_locator(bid, footprints[bid], footprints, cams, params, sr, width, height, pop_by)
            manifest.append(rec)
            print(f"[cards-v4] timediff {bid} view={rec['locator_view']} zen={rec['locator_zenith_deg']}", flush=True)
        except Exception as exc:
            failures.append(f"time_diff {full_bid(bid)}: {exc}")
            print(f"[cards-v4] FAIL timediff {bid}: {exc}", flush=True)
    mcols = [
        "building_id",
        "card_type",
        "figure",
        "locator_view",
        "locator_zenith_deg",
        "view_reason",
        "neighbor_ids",
        "neighbor_rings_drawn",
        "manual_batch",
        "manual_source",
        "area_m2",
        "small_flag",
        "elong_flag",
        "bbox_aspect_ratio",
        "isoperimetric",
        "dim_density",
        "n_views_nadir",
        "inc60",
        "recon_score",
        "occlusion",
        "lowtex_v5",
        "lowtex_v5_zenith_deg",
        "veto_recovered",
        "dim_points_in_footprint",
        "dim_points_plotted",
        "dim_source",
        "als_points_in_footprint",
        "als_points_plotted",
        "als_source",
        "als_marker_scale",
        "observation",
    ]
    write_csv(OUT_DIR / "manifest.csv", manifest, mcols)
    write_report(manual_bids, manifest, shape_rows, manual_missing, red_channel_note(), failures)
    write_versions(manifest, manual_missing)
    print(f"[done] {OUT_DIR}")
    print(f"[done] {SHAPE_FLAGS}")
    print(f"[done] {REPORT}")
    print(f"[done] {RUN_DIR / 'versions.txt'}")


if __name__ == "__main__":
    main()

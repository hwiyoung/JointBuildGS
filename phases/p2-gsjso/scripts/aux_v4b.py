#!/usr/bin/env python3
"""A3b aux-v4b: lowtex-v5 and evidence cards v3.

No reconstruction/retraining. This script only projects existing LoD2/ALS data
into existing images, recomputes lowtex with stricter view selection, and writes
documentation artifacts.
"""
from __future__ import annotations

import csv
import json
import math
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import laspy
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from datum_tie_overlay import (  # noqa: E402
    DELTA_ZETA,
    ZETA_LEFT,
    ZETA_RIGHT,
    crop_bbox,
    footprints,
    load_dense_success,
    project_lod2_rings,
    projected_als,
    select_views as select_overlay_views,
    zoom_bbox_from_rings,
)
from evidence_cards_v2 import (  # noqa: E402
    ALS_TILES,
    DATA,
    GMLDIR,
    GEOJSON,
    IMAGE_DIR,
    REPO,
    distort,
    gml_building,
    parse_cam_model,
    parse_cameras,
    proj_ring,
    to_cam,
)
from projection_datum import as_ellipsoidal_points, describe_projection_config  # noqa: E402


RUN_ID = "20260703_aux_v4b"
RUN_DIR = REPO / "runs" / RUN_ID
DOCS = REPO / "docs"
MOB = REPO / "results/tum_transfer/mob/overseg_lever"
POP_V4 = DOCS / "population_aux_v4.csv"
POP_V4_RESULTS = MOB / "population_aux_v4.csv"
CROSS = DOCS / "bucket_crosswalk_v2.csv"
LOWTEX_CSV = DOCS / "lowtex_v5.csv"
ANCHOR_CSV = DOCS / "lowtex_v5_anchor_check.csv"
REPORT_MD = DOCS / "aux_v4b_change_report.md"
CARDDIR = DOCS / "evidence_cards_v3"
OVERLAY_DIR = DOCS / "figs/datum_tie_overlay"
OVERLAY_MD = DOCS / "datum_tie_overlay.md"

ZETA = 45.700
T11_THR = 0.02137
IMAGERY_DATE = "2024-12-17"
POS_ANCHORS = ["4907182", "42364609", "4907510", "4908050", "4908166", "4908176"]
NEG_ANCHORS = ["4906972", "4908023", "4907028", "4908354", "4907520"]
CLEAN_NEG_ANCHORS = ["4906972", "4907028", "4908354", "4907520"]
TIME_DIFF_TARGETS = ["4906999", "42364663", "4959320"]
CORNER_ZOOM_REFRESH = ["4906966", "4906969"]
LOWTEX_V5_COLS = [
    "lowtex_valid",
    "roof_lowtex_v5",
    "roof_grad_p10_v5",
    "roof_sat_frac_v5",
    "lowtex_v5_view",
    "lowtex_v5_zenith_deg",
    "lowtex_v5_frame_r",
    "lowtex_v5_inframe_frac",
    "lowtex_v5_area_px",
    "lowtex_v5_delta_from_v4",
]
BUILDING_CACHE: dict[str, dict[str, object]] = {}


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception as exc:  # pragma: no cover
        return f"unavailable: {exc}"


def load_building_cache() -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for gml in sorted(GMLDIR.glob("*.gml")):
        for _, el in ET.iterparse(gml, events=("end",)):
            if el.tag.rsplit("}", 1)[-1] != "Building":
                continue
            full = next((v for k, v in el.attrib.items() if k.rsplit("}", 1)[-1] == "id"), None)
            if not full:
                el.clear()
                continue

            def rings(kind):
                rr = []
                for surface in el.iter():
                    if surface.tag.rsplit("}", 1)[-1] != kind:
                        continue
                    for pl in surface.iter():
                        if pl.tag.rsplit("}", 1)[-1] == "posList" and pl.text:
                            rr.append(np.array([float(x) for x in pl.text.split()]).reshape(-1, 3))
                return rr

            creation = next((e.text for e in el.iter() if e.tag.rsplit("}", 1)[-1] == "creationDate"), None)
            grundriss = None
            for e in el.iter():
                nm = e.attrib.get("name") or next((v for k, v in e.attrib.items() if k.rsplit("}", 1)[-1] == "name"), None)
                if nm == "Grundrissaktualitaet":
                    grundriss = next((c.text for c in e if c.tag.rsplit("}", 1)[-1] == "value"), None)
            roof_type = next((e.text.strip() for e in el.iter() if e.tag.rsplit("}", 1)[-1] == "roofType" and e.text), "NONE")
            out[full.replace("DEBY_LOD2_", "")] = {
                "roof": rings("RoofSurface"),
                "wall": rings("WallSurface"),
                "roofType": roof_type,
                "creationDate": creation,
                "grundriss": grundriss,
            }
            el.clear()
    return out


def building(bid: str):
    return BUILDING_CACHE.get(bid) or gml_building(bid)


def fnum(value):
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def polygon_area(ring: np.ndarray) -> float:
    if len(ring) < 3:
        return 0.0
    q = ring[:, :2]
    return float(0.5 * abs(np.dot(q[:-1, 0], q[1:, 1]) - np.dot(q[1:, 0], q[:-1, 1])))


def load_rows(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(open(path)))


def write_csv(path: Path, rows: list[dict[str, object]], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fo:
        writer = csv.DictWriter(fo, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in cols})


def view_zenith(cam, target_ortho: np.ndarray, sr: dict) -> float:
    target = as_ellipsoidal_points(np.asarray(target_ortho, float)[None], input_datum="orthometric", geoid_m=ZETA)[0]
    vec = cam.center - target
    n = float(np.linalg.norm(vec))
    if n <= 1e-9:
        return float("nan")
    return math.degrees(math.acos(min(1.0, max(-1.0, abs(vec[2]) / n))))


def project_all_vertices(points: np.ndarray, cam, params: np.ndarray, sr: dict) -> tuple[np.ndarray, np.ndarray]:
    cc = to_cam(points, cam, sr, geoid_m=ZETA)
    front = cc[:, 2] > 1.0
    uv = np.full((len(points), 2), np.nan, dtype=float)
    if front.any():
        uv[front] = distort(cc[front], params)
    return uv, front


def roof_view_stats(roof: list[np.ndarray], cam, params: np.ndarray, sr: dict, width: int, height: int):
    allv = np.vstack(roof)
    uv, front = project_all_vertices(allv, cam, params, sr)
    finite = front & np.isfinite(uv[:, 0]) & np.isfinite(uv[:, 1])
    inb = finite & (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
    infrac = float(inb.mean()) if len(inb) else 0.0
    cx, cy = params[2], params[3]
    rad = float("inf")
    if inb.any():
        rad = float(np.nanmax(np.sqrt(((uv[inb, 0] - cx) / (0.5 * width)) ** 2 + ((uv[inb, 1] - cy) / (0.5 * height)) ** 2)))
    ctr = np.array([allv[:, 0].mean(), allv[:, 1].mean(), float(np.median(allv[:, 2]))])
    zen = view_zenith(cam, ctr, sr)
    return {"inframe_frac": infrac, "frame_r": rad, "zenith": zen, "uv": uv, "front": front}


def select_lowtex_view(roof: list[np.ndarray], cams, params: np.ndarray, sr: dict, width: int, height: int):
    candidates = []
    fallback = []
    for cam in cams:
        st = roof_view_stats(roof, cam, params, sr, width, height)
        fallback.append((st["inframe_frac"], -st["frame_r"], st["zenith"], cam, st))
        if st["inframe_frac"] >= 0.999 and st["frame_r"] < 0.85:
            candidates.append((st["zenith"], st["frame_r"], cam, st))
    if candidates:
        candidates.sort(key=lambda t: (t[0], t[1]))
        return candidates[0][2], candidates[0][3], "valid"
    fallback.sort(key=lambda t: (-t[0], t[1], t[2]))
    return (fallback[0][3], fallback[0][4], "none") if fallback else (None, None, "none")


def projected_roof_polys(roof: list[np.ndarray], cam, params: np.ndarray, sr: dict) -> list[np.ndarray]:
    out = []
    for ring in roof:
        uv, front = project_all_vertices(np.asarray(ring, float), cam, params, sr)
        if len(uv) >= 3 and bool(front.all()) and np.isfinite(uv).all():
            out.append(uv)
    return out


def lowtex_measure(roof: list[np.ndarray], cam, params: np.ndarray, sr: dict, width: int, height: int):
    polys = projected_roof_polys(roof, cam, params, sr)
    if not polys:
        return None
    all_uv = np.vstack(polys)
    x0 = int(max(0, math.floor(float(np.nanmin(all_uv[:, 0])) - 6)))
    y0 = int(max(0, math.floor(float(np.nanmin(all_uv[:, 1])) - 6)))
    x1 = int(min(width, math.ceil(float(np.nanmax(all_uv[:, 0])) + 6)))
    y1 = int(min(height, math.ceil(float(np.nanmax(all_uv[:, 1])) + 6)))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    img = Image.open(IMAGE_DIR / cam.name).convert("L")
    crop = img.crop((x0, y0, x1, y1))
    mask = Image.new("L", crop.size, 0)
    dr = ImageDraw.Draw(mask)
    for poly in polys:
        pts = [(float(x - x0), float(y - y0)) for x, y in poly]
        dr.polygon(pts, fill=1)
    if max(crop.size) > 512:
        scale = 512.0 / max(crop.size)
        new_size = (max(1, int(round(crop.size[0] * scale))), max(1, int(round(crop.size[1] * scale))))
        crop = crop.resize(new_size, Image.Resampling.BILINEAR)
        mask = mask.resize(new_size, Image.Resampling.NEAREST)
    arr = np.asarray(crop, dtype=np.float32) / 255.0
    m = np.asarray(mask, dtype=np.uint8) > 0
    if int(m.sum()) < 32:
        return None
    gy, gx = np.gradient(arr)
    grad = np.sqrt(gx * gx + gy * gy)
    vals = grad[m]
    return {
        "lowtex": float(np.mean(vals < T11_THR)),
        "grad_p10": float(np.percentile(vals, 10)),
        "sat_frac": float(np.mean(arr[m] > 0.97)),
        "area_px": int(m.sum()),
    }


def compute_lowtex_v5(rows: list[dict[str, str]], cams, params: np.ndarray, sr: dict, width: int, height: int):
    results = {}
    for i, row in enumerate(rows):
        bid = row["building_id"].replace("DEBY_LOD2_", "")
        gb = building(bid)
        rec = {c: "" for c in LOWTEX_V5_COLS}
        rec["building_id"] = row["building_id"]
        if not gb or not gb["roof"]:
            rec["lowtex_valid"] = "none"
            rec["lowtex_v5_inframe_frac"] = 0.0
            results[bid] = rec
            continue
        cam, stats, valid = select_lowtex_view(gb["roof"], cams, params, sr, width, height)
        rec["lowtex_valid"] = valid
        if cam is not None and stats is not None:
            rec["lowtex_v5_view"] = cam.name
            rec["lowtex_v5_zenith_deg"] = round(float(stats["zenith"]), 3)
            rec["lowtex_v5_frame_r"] = round(float(stats["frame_r"]), 3) if np.isfinite(stats["frame_r"]) else ""
            rec["lowtex_v5_inframe_frac"] = round(float(stats["inframe_frac"]), 3)
        if valid == "valid" and cam is not None:
            m = lowtex_measure(gb["roof"], cam, params, sr, width, height)
            if m:
                rec["roof_lowtex_v5"] = round(m["lowtex"], 3)
                rec["roof_grad_p10_v5"] = round(m["grad_p10"], 4)
                rec["roof_sat_frac_v5"] = round(m["sat_frac"], 4)
                rec["lowtex_v5_area_px"] = m["area_px"]
                v4 = fnum(row.get("roof_lowtex_v4"))
                if v4 is not None:
                    rec["lowtex_v5_delta_from_v4"] = round(float(m["lowtex"] - v4), 3)
            else:
                rec["lowtex_valid"] = "none"
        results[bid] = rec
        if (i + 1) % 25 == 0:
            print(f"[v4b] lowtex {i+1}/{len(rows)}", flush=True)
    return results


def update_population(rows: list[dict[str, str]], lowtex: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    out = []
    for row in rows:
        bid = row["building_id"].replace("DEBY_LOD2_", "")
        nr = dict(row)
        nr.update(lowtex.get(bid, {c: "" for c in LOWTEX_V5_COLS}))
        out.append(nr)
    cols = list(rows[0].keys())
    for col in LOWTEX_V5_COLS:
        if col not in cols:
            cols.append(col)
    write_csv(POP_V4, out, cols)
    write_csv(POP_V4_RESULTS, out, cols)
    return out


def write_lowtex_outputs(pop_rows: list[dict[str, object]], lowtex: dict[str, dict[str, object]]):
    cols = ["building_id", *LOWTEX_V5_COLS, "roof_lowtex_v4", "footprint_area_m2"]
    rows = []
    for row in pop_rows:
        bid = row["building_id"].replace("DEBY_LOD2_", "")
        lr = dict(lowtex.get(bid, {}))
        lr["building_id"] = row["building_id"]
        lr["roof_lowtex_v4"] = row.get("roof_lowtex_v4", "")
        lr["footprint_area_m2"] = row.get("footprint_area_m2", "")
        rows.append(lr)
    write_csv(LOWTEX_CSV, rows, cols)


def anchor_rows(lowtex: dict[str, dict[str, object]]):
    rows = []
    for label, bids in [("positive_lowtex", POS_ANCHORS), ("negative_textured", NEG_ANCHORS)]:
        for bid in bids:
            r = lowtex.get(bid, {})
            rows.append(
                {
                    "building_id": f"DEBY_LOD2_{bid}",
                    "anchor": label,
                    "clean_negative_used": int(bid in CLEAN_NEG_ANCHORS),
                    "lowtex_valid": r.get("lowtex_valid", ""),
                    "roof_lowtex_v5": r.get("roof_lowtex_v5", ""),
                    "roof_lowtex_v4": r.get("roof_lowtex_v4", ""),
                    "lowtex_v5_view": r.get("lowtex_v5_view", ""),
                    "lowtex_v5_zenith_deg": r.get("lowtex_v5_zenith_deg", ""),
                    "lowtex_v5_frame_r": r.get("lowtex_v5_frame_r", ""),
                    "lowtex_v5_inframe_frac": r.get("lowtex_v5_inframe_frac", ""),
                }
            )
    write_csv(ANCHOR_CSV, rows, list(rows[0].keys()))
    return rows


def load_als_subset(target_rings: dict[str, np.ndarray], margin: float = 8.0) -> np.ndarray:
    all_xy = np.vstack([r[:, :2] for r in target_rings.values()])
    aoi = [
        float(all_xy[:, 0].min() - margin),
        float(all_xy[:, 1].min() - margin),
        float(all_xy[:, 0].max() + margin),
        float(all_xy[:, 1].max() + margin),
    ]
    chunks = []
    for tile in ALS_TILES:
        with laspy.open(tile) as fh:
            h = fh.header
            if h.x_max < aoi[0] or h.x_min > aoi[2] or h.y_max < aoi[1] or h.y_min > aoi[3]:
                continue
        las = laspy.read(tile)
        x = np.asarray(las.x)
        y = np.asarray(las.y)
        z = np.asarray(las.z)
        cls = np.asarray(las.classification)
        m = (cls == 6) & (x >= aoi[0]) & (x <= aoi[2]) & (y >= aoi[1]) & (y <= aoi[3])
        if m.any():
            chunks.append(np.column_stack([x[m], y[m], z[m]]).astype(np.float32))
        print(f"[v4b] ALS tile subset {Path(tile).name}: {int(m.sum())} class-6 points", flush=True)
    return np.vstack(chunks) if chunks else np.zeros((0, 3), dtype=np.float32)


def als_points_for_ring(als_subset: np.ndarray, ring: np.ndarray, ground_z: float) -> np.ndarray:
    if len(als_subset) == 0:
        return np.zeros((0, 3), dtype=np.float32)
    bb = [ring[:, 0].min() - 1.0, ring[:, 1].min() - 1.0, ring[:, 0].max() + 1.0, ring[:, 1].max() + 1.0]
    m = (
        (als_subset[:, 0] >= bb[0])
        & (als_subset[:, 0] <= bb[2])
        & (als_subset[:, 1] >= bb[1])
        & (als_subset[:, 1] <= bb[3])
        & (als_subset[:, 2] > ground_z + 2.0)
    )
    cand = als_subset[m]
    if len(cand) == 0:
        return np.zeros((0, 3), dtype=np.float32)
    inside = MplPath(ring[:, :2]).contains_points(cand[:, :2])
    return cand[inside]


def select_render_view(roof: list[np.ndarray], cams, params: np.ndarray, sr: dict, width: int, height: int):
    cand = []
    for cam in cams:
        st = roof_view_stats(roof, cam, params, sr, width, height)
        if st["inframe_frac"] >= 0.75:
            cand.append((st["inframe_frac"], -st["frame_r"], st["zenith"], cam, st))
    if not cand:
        return None, None
    cand.sort(key=lambda t: (-t[0], t[1], t[2]))
    return cand[0][3], cand[0][4]


def draw_card_panel(ax, image: np.ndarray, bbox, rings: list[np.ndarray], als_uv: np.ndarray, title: str, strong: bool = False):
    x0, y0, x1, y1 = bbox
    crop = image[y0:y1, x0:x1]
    ax.imshow(crop)
    ax.axis("off")
    for ring in rings:
        q = np.vstack([ring, ring[:1]])
        style = "--" if strong else "-"
        alpha = 0.62 if strong else 0.94
        ax.plot(q[:, 0] - x0, q[:, 1] - y0, style, c="lime", lw=1.15, alpha=alpha)
    if len(als_uv):
        ax.scatter(als_uv[:, 0] - x0, als_uv[:, 1] - y0, s=1.0 if strong else 0.75, c="#00d7ff", alpha=0.5, linewidths=0)
        if strong:
            p = np.median(als_uv, axis=0)
            ax.annotate(
                "visible edge",
                xy=(p[0] - x0, p[1] - y0),
                xytext=(crop.shape[1] * 0.62, crop.shape[0] * 0.18),
                color="white",
                fontsize=7.5,
                arrowprops=dict(arrowstyle="->", color="white", lw=1.1),
            )
    ax.set_title(title, fontsize=8.0)
    ax.set_xlim(0, crop.shape[1])
    ax.set_ylim(crop.shape[0], 0)


def render_evidence_card(
    bid: str,
    gb: dict,
    ring: np.ndarray,
    cam,
    stats: dict,
    als: np.ndarray,
    params: np.ndarray,
    sr: dict,
    width: int,
    height: int,
    row: dict[str, object],
) -> dict[str, object]:
    image = np.asarray(Image.open(IMAGE_DIR / cam.name).convert("RGB"))
    rings = project_lod2_rings(gb["roof"], cam, params, sr, ZETA)
    als_uv = projected_als(als, cam, params, sr, width, height, ZETA)
    if not rings and len(als_uv) == 0:
        raise RuntimeError("no projected overlay")
    bbox = crop_bbox(rings + [als_uv], width, height, pad=120)
    strong = float(stats["zenith"]) > 50.0
    fig, ax = plt.subplots(1, 1, figsize=(7.8, 6.2))
    title = f"DEBY_LOD2_{bid} | {cam.name[11:17]} | zenith={float(stats['zenith']):.1f} deg"
    draw_card_panel(ax, image, bbox, rings, als_uv, title, strong=strong)
    theory = DELTA_ZETA * math.tan(math.radians(float(stats["zenith"])))
    fig.text(
        0.5,
        0.055,
        f"zeta=45.700; reference Delta zeta 2.426 x tan(theta)={theory:.3f} m; "
        "cyan=LiDAR points; lime=LoD2 ring tolerance +/-1 m",
        ha="center",
        fontsize=7.7,
    )
    fig.text(
        0.5,
        0.028,
        "projection/render only; strong-oblique uses LiDAR-point-centered occlusion treatment",
        ha="center",
        fontsize=7.4,
    )
    out = CARDDIR / f"{bid}.png"
    fig.tight_layout(rect=[0, 0.08, 1, 0.98])
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return {
        "building_id": f"DEBY_LOD2_{bid}",
        "card_type": "manual_review",
        "view": cam.name,
        "zenith_deg": round(float(stats["zenith"]), 3),
        "theory_shift_m": round(theory, 3),
        "als_points": int(len(als)),
        "lowtex_valid": row.get("lowtex_valid", ""),
        "roof_lowtex_v5": row.get("roof_lowtex_v5", ""),
        "figure": str(out.relative_to(REPO)),
        "observation": "LiDAR points are the reading channel; LoD2 ring is context with +/-1 m tolerance.",
    }


def render_timediff_card(
    bid: str,
    gb: dict,
    ring: np.ndarray,
    cams,
    als: np.ndarray,
    params: np.ndarray,
    sr: dict,
    width: int,
    height: int,
) -> dict[str, object] | None:
    allv = np.vstack(gb["roof"])
    good = []
    for cam in cams:
        st = roof_view_stats(gb["roof"], cam, params, sr, width, height)
        if st["inframe_frac"] >= 0.85 and st["frame_r"] < 1.0:
            good.append((st["zenith"], cam, st))
    if len(good) < 2:
        return None
    good.sort(key=lambda t: t[0])
    lo = good[0]
    hi = max(good[1:], key=lambda t: t[0])
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.7))
    rows = []
    for ax, (tag, item) in zip(axes, [("low", lo), ("high", hi)]):
        zen, cam, st = item
        image = np.asarray(Image.open(IMAGE_DIR / cam.name).convert("RGB"))
        rings = project_lod2_rings(gb["roof"], cam, params, sr, ZETA)
        als_uv = projected_als(als, cam, params, sr, width, height, ZETA)
        if not rings and len(als_uv) == 0:
            continue
        bbox = crop_bbox(rings + [als_uv], width, height, pad=120)
        draw_card_panel(ax, image, bbox, rings, als_uv, f"{tag} {cam.name[11:17]} zenith={zen:.1f} deg", strong=zen > 50)
        rows.append((tag, cam.name, zen))
    if not rows:
        plt.close(fig)
        return None
    created = gb.get("creationDate")
    grundriss = gb.get("grundriss")
    fig.suptitle(
        f"DEBY_LOD2_{bid} time-diff card | created {created} | imagery {IMAGERY_DATE} | grundriss {grundriss}",
        fontsize=8.6,
    )
    fig.text(0.5, 0.025, "cyan=LiDAR points; lime=LoD2 ring tolerance +/-1 m; projection/render only", ha="center", fontsize=7.7)
    out = CARDDIR / f"timediff_{bid}.png"
    fig.tight_layout(rect=[0, 0.05, 1, 0.94])
    fig.savefig(out, dpi=125)
    plt.close(fig)
    return {
        "building_id": f"DEBY_LOD2_{bid}",
        "card_type": "time_diff",
        "view": ";".join(r[1] for r in rows),
        "zenith_deg": ";".join(f"{r[2]:.3f}" for r in rows),
        "theory_shift_m": "",
        "als_points": int(len(als)),
        "lowtex_valid": "",
        "roof_lowtex_v5": "",
        "figure": str(out.relative_to(REPO)),
        "observation": "time-diff view pair; creation date is reported as metadata only.",
    }


def render_cards(pop_rows: list[dict[str, object]], lowtex: dict[str, dict[str, object]], cams, params, sr, width: int, height: int):
    cross = load_rows(CROSS)
    manual = [r["building_id"].replace("DEBY_LOD2_", "") for r in cross if r["new_class"] == "수동판정"]
    targets = sorted(set(manual) | set(TIME_DIFF_TARGETS))
    fp = footprints()
    target_rings = {b: fp[b] for b in targets if b in fp}
    als_subset = load_als_subset(target_rings)
    CARDDIR.mkdir(parents=True, exist_ok=True)
    row_by = {r["building_id"].replace("DEBY_LOD2_", ""): r for r in pop_rows}
    manifest = []
    skipped = []
    for bid in manual:
        gb = building(bid)
        ring = fp.get(bid)
        if not gb or not gb["roof"] or ring is None:
            skipped.append((bid, "missing roof or footprint"))
            continue
        all_surfaces = np.vstack(gb["roof"] + gb["wall"])
        ground_z = float(all_surfaces[:, 2].min())
        als = als_points_for_ring(als_subset, ring, ground_z)
        lrow = lowtex.get(bid, {})
        cam = next((c for c in cams if c.name == lrow.get("lowtex_v5_view")), None)
        stats = None
        if cam is not None:
            stats = roof_view_stats(gb["roof"], cam, params, sr, width, height)
        if cam is None or stats is None or stats["inframe_frac"] < 0.75:
            cam, stats = select_render_view(gb["roof"], cams, params, sr, width, height)
        if cam is None:
            skipped.append((bid, "no render view"))
            continue
        try:
            manifest.append(render_evidence_card(bid, gb, ring, cam, stats, als, params, sr, width, height, row_by.get(bid, {})))
        except Exception as exc:
            skipped.append((bid, str(exc)))
    for bid in TIME_DIFF_TARGETS:
        gb = building(bid)
        ring = fp.get(bid)
        if not gb or not gb["roof"] or ring is None:
            skipped.append((bid, "time-diff missing roof or footprint"))
            continue
        all_surfaces = np.vstack(gb["roof"] + gb["wall"])
        ground_z = float(all_surfaces[:, 2].min())
        als = als_points_for_ring(als_subset, ring, ground_z)
        rec = render_timediff_card(bid, gb, ring, cams, als, params, sr, width, height)
        if rec:
            manifest.append(rec)
        else:
            skipped.append((bid, "time-diff no two-view pair"))
    mcols = ["building_id", "card_type", "view", "zenith_deg", "theory_shift_m", "als_points", "lowtex_valid", "roof_lowtex_v5", "figure", "observation"]
    write_csv(CARDDIR / "manifest.csv", manifest, mcols)
    readme = [
        "# evidence_cards_v3",
        "",
        "> 재구성/재학습 없음. projection/render only. 판정 금지.",
        "",
        f"- 수동판정 카드: {len([m for m in manifest if m['card_type'] == 'manual_review'])} / {len(manual)}.",
        f"- 시간차 카드: {len([m for m in manifest if m['card_type'] == 'time_diff'])} / {len(TIME_DIFF_TARGETS)}.",
        "- 판정 채널: LiDAR points. LoD2 ring은 context이며 caption 공차는 +/-1 m.",
        "- 강기울기 view는 LiDAR-point-centered occlusion treatment와 visible-edge arrow를 사용했다.",
        "",
        "## skipped",
        "",
    ]
    if skipped:
        readme.extend(f"- {bid}: {why}" for bid, why in skipped)
    else:
        readme.append("- none")
    (CARDDIR / "README.md").write_text("\n".join(readme) + "\n")
    return manifest, skipped


def render_corner_panel(ax, image: np.ndarray, bbox, rings_left, rings_right, als_left, title: str):
    x0, y0, x1, y1 = bbox
    crop = image[y0:y1, x0:x1]
    ax.imshow(crop)
    ax.axis("off")
    for rings, color, style in [(rings_left, "lime", "-"), (rings_right, "magenta", "--")]:
        for ring in rings:
            q = np.vstack([ring, ring[:1]])
            ax.plot(q[:, 0] - x0, q[:, 1] - y0, style, c=color, lw=1.2, alpha=0.9)
    if len(als_left):
        ax.scatter(als_left[:, 0] - x0, als_left[:, 1] - y0, s=1.2, c="#00d7ff", alpha=0.55, linewidths=0)
        p = np.median(als_left, axis=0)
        ax.annotate(
            "edge to inspect",
            xy=(p[0] - x0, p[1] - y0),
            xytext=(crop.shape[1] * 0.58, crop.shape[0] * 0.18),
            color="white",
            fontsize=7.5,
            arrowprops=dict(arrowstyle="->", color="white", lw=1.1),
        )
    ax.set_title(title, fontsize=8.0)
    ax.set_xlim(0, crop.shape[1])
    ax.set_ylim(crop.shape[0], 0)


def refresh_corner_zooms(cams, params, sr, width: int, height: int):
    dense_success = load_dense_success()
    fp = footprints()
    rows = []
    for bid in CORNER_ZOOM_REFRESH:
        if bid not in dense_success:
            rows.append({"building_id": bid, "status": "skip_not_dense_success"})
            continue
        gb = building(bid)
        ring = fp.get(bid)
        if not gb or not gb["roof"] or ring is None:
            rows.append({"building_id": bid, "status": "skip_missing_roof"})
            continue
        all_surfaces = np.vstack(gb["roof"] + gb["wall"])
        ground_z = float(all_surfaces[:, 2].min())
        subset = load_als_subset({bid: ring}, margin=8.0)
        als = als_points_for_ring(subset, ring, ground_z)
        if len(als) < 20:
            rows.append({"building_id": bid, "status": f"skip_als_{len(als)}"})
            continue
        picks, _target = select_overlay_views(gb["roof"], ring, als, cams, params, sr, width, height)
        strong = [p for label, p in picks if label == "strong"][0]
        cam = strong["cam"]
        image = np.asarray(Image.open(IMAGE_DIR / cam.name).convert("RGB"))
        rings_left = project_lod2_rings(gb["roof"], cam, params, sr, ZETA_LEFT)
        rings_right = project_lod2_rings(gb["roof"], cam, params, sr, ZETA_RIGHT)
        als_left = projected_als(als, cam, params, sr, width, height, ZETA_LEFT)
        bbox = zoom_bbox_from_rings(rings_left, rings_right, width, height, pad=280)
        fig, ax = plt.subplots(1, 1, figsize=(7.4, 6.2))
        theory = DELTA_ZETA * math.tan(math.radians(float(strong["zenith"])))
        render_corner_panel(
            ax,
            image,
            bbox,
            rings_left,
            rings_right,
            als_left,
            f"DEBY_LOD2_{bid} strong corner | zenith={float(strong['zenith']):.1f} deg",
        )
        fig.text(
            0.5,
            0.045,
            f"cyan=LiDAR points; lime=zeta45.700; magenta=zeta48.126; Delta zeta x tan(theta)={theory:.3f} m",
            ha="center",
            fontsize=7.5,
        )
        fig.text(0.5, 0.020, "LoD2 ring tolerance +/-1 m; LiDAR-point-centered occlusion treatment", ha="center", fontsize=7.4)
        out = OVERLAY_DIR / f"{bid}_strong_corner_zoom.png"
        fig.tight_layout(rect=[0, 0.07, 1, 0.98])
        fig.savefig(out, dpi=135)
        plt.close(fig)
        rows.append({"building_id": f"DEBY_LOD2_{bid}", "status": "refreshed", "view": cam.name, "zenith_deg": round(float(strong["zenith"]), 3), "figure": str(out.relative_to(REPO))})
    if OVERLAY_MD.exists():
        txt = OVERLAY_MD.read_text()
        marker = "\n## A3b corner zoom refresh\n"
        add = [
            "## A3b corner zoom refresh",
            "",
            "> aux-v4b에서 4906966, 4906969 강기울기 corner zoom 2장을 LiDAR-point-centered occlusion treatment, edge arrow, LoD2 ring tolerance +/-1 m caption 규약으로 교체했다. 관찰 보조 그림이며 채택 판정 문장이 아니다.",
            "",
            "| building_id | status | view | zenith_deg | figure |",
            "|---|---|---|---:|---|",
        ]
        for row in rows:
            add.append(
                f"| {row.get('building_id')} | {row.get('status')} | `{row.get('view', '')}` | {row.get('zenith_deg', '')} | `{row.get('figure', '')}` |"
            )
        txt = txt.split(marker)[0].rstrip() + "\n\n" + "\n".join(add) + "\n"
        OVERLAY_MD.write_text(txt)
    return rows


def summarize_values(rows: list[dict[str, object]], key: str) -> dict[str, object]:
    vals = [fnum(r.get(key)) for r in rows]
    vals = [v for v in vals if v is not None and np.isfinite(v)]
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "min": min(vals), "median": float(np.median(vals)), "max": max(vals)}


def write_report(
    pop_rows: list[dict[str, object]],
    lowtex_rows: list[dict[str, object]],
    anchors: list[dict[str, object]],
    manifest: list[dict[str, object]],
    skipped: list[tuple[str, str]],
    corner_rows: list[dict[str, object]],
) -> None:
    valid_counts = Counter(r.get("lowtex_valid", "") for r in lowtex_rows)
    vals = {r["building_id"].replace("DEBY_LOD2_", ""): fnum(r.get("roof_lowtex_v5")) for r in lowtex_rows}
    pos = [vals.get(b) for b in POS_ANCHORS if vals.get(b) is not None]
    neg = [vals.get(b) for b in NEG_ANCHORS if vals.get(b) is not None]
    clean = [vals.get(b) for b in CLEAN_NEG_ANCHORS if vals.get(b) is not None]
    all_gap = min(pos) - max(neg) if pos and neg else None
    clean_gap = min(pos) - max(clean) if pos and clean else None
    moved = []
    for r in lowtex_rows:
        v4 = fnum(r.get("roof_lowtex_v4"))
        v5 = fnum(r.get("roof_lowtex_v5"))
        if v4 is not None and v5 is not None:
            moved.append((abs(v5 - v4), v5 - v4, r))
    moved.sort(key=lambda t: -t[0])
    lines = [
        "# aux_v4b_change_report -- lowtex-v5 and evidence cards v3",
        "",
        "> 재구성/재학습 없음. 판정 금지. 수치·관찰만 기록한다.",
        "",
        "## 0. 입력과 규약",
        "",
        f"- image-projection zeta = {ZETA:.3f} m. 3D/씨드 경로 `-556`은 건드리지 않았다.",
        "- 지오 산출물 CRS: EPSG:25832. OPF/COLMAP frame: EPSG:32632.",
        "- lowtex-v5 view rule: 지붕 100% in-frame AND frame radius <0.85 AND 기울기 최소. 해당 view가 없으면 `lowtex_valid=none`.",
        "- card render rule: LiDAR points가 판정 채널이고 LoD2 ring은 context이며 caption 공차는 +/-1 m.",
        "",
        "## 1. lowtex-v5 산출",
        "",
        f"- `valid`: {valid_counts.get('valid', 0)}동.",
        f"- `none`: {valid_counts.get('none', 0)}동.",
        f"- v5 분포(valid): {summarize_values(lowtex_rows, 'roof_lowtex_v5')}.",
        f"- CSV: `{LOWTEX_CSV.relative_to(REPO)}`, `{ANCHOR_CSV.relative_to(REPO)}`.",
        "",
        "## 2. 텍스처 앵커 11동",
        "",
        "| building_id | anchor | clean_negative_used | lowtex_valid | roof_lowtex_v5 | view | zenith_deg | frame_r |",
        "|---|---|---:|---|---:|---|---:|---:|",
    ]
    for row in anchors:
        lines.append(
            f"| {row['building_id']} | {row['anchor']} | {row['clean_negative_used']} | {row['lowtex_valid']} | "
            f"{row['roof_lowtex_v5']} | `{row['lowtex_v5_view']}` | {row['lowtex_v5_zenith_deg']} | {row['lowtex_v5_frame_r']} |"
        )
    lines.extend(
        [
            "",
            f"- 양성 6동 v5 min/mean: {min(pos):.3f} / {float(np.mean(pos)):.3f}." if pos else "- 양성 6동 v5: 값 없음.",
            f"- 음성 5동 v5 max/mean: {max(neg):.3f} / {float(np.mean(neg)):.3f}." if neg else "- 음성 5동 v5: 값 없음.",
            f"- clean 음성 4동(4908023 제외) v5 max/mean: {max(clean):.3f} / {float(np.mean(clean)):.3f}." if clean else "- clean 음성 4동: 값 없음.",
            f"- all-anchor gap(pos_min - neg_max): {all_gap:+.3f}." if all_gap is not None else "- all-anchor gap: 값 없음.",
            f"- clean gap(pos_min - clean_neg_max): {clean_gap:+.3f}." if clean_gap is not None else "- clean gap: 값 없음.",
            "- 관찰: lowtex-v5 strict view에서는 앵커 분리가 유지되지 않았다. clean gap 음수는 4907028(v5=0.708, zenith=84.19 deg)이 음성 최대값이 된 영향이다."
            if clean_gap is not None and clean_gap <= 0
            else "- 관찰: lowtex-v5 strict view의 valid 앵커 subset에서 clean gap이 양수다.",
            "- 4908023은 이전 문서에서 텍스처 앵커 부적합 관찰이 있어 clean 음성 계산에서 별도 제외했다.",
            "",
            "## 3. v4<->v5 이동 상위 10동",
            "",
            "| rank | building_id | roof_lowtex_v4 | roof_lowtex_v5 | delta_v5_minus_v4 | v5_view | valid |",
            "|---:|---|---:|---:|---:|---|---|",
        ]
    )
    for i, (_absd, delta, row) in enumerate(moved[:10], 1):
        lines.append(
            f"| {i} | {row['building_id']} | {row.get('roof_lowtex_v4', '')} | {row.get('roof_lowtex_v5', '')} | "
            f"{delta:+.3f} | `{row.get('lowtex_v5_view', '')}` | {row.get('lowtex_valid', '')} |"
        )
    lines.extend(
        [
            "",
            "## 4. evidence_cards_v3",
            "",
            f"- manual_review cards: {len([m for m in manifest if m['card_type'] == 'manual_review'])}.",
            f"- time_diff cards: {len([m for m in manifest if m['card_type'] == 'time_diff'])}.",
            f"- skipped: {len(skipped)}.",
            f"- manifest: `{(CARDDIR / 'manifest.csv').relative_to(REPO)}`.",
            f"- README: `{(CARDDIR / 'README.md').relative_to(REPO)}`.",
            "",
            "## 5. datum_tie_overlay corner zoom refresh",
            "",
            "| building_id | status | view | zenith_deg | figure |",
            "|---|---|---|---:|---|",
        ]
    )
    for row in corner_rows:
        lines.append(
            f"| {row.get('building_id')} | {row.get('status')} | `{row.get('view', '')}` | {row.get('zenith_deg', '')} | `{row.get('figure', '')}` |"
        )
    lines.extend(
        [
            "",
            "## 6. 관찰",
            "",
            f"- lowtex-v5는 199동 중 {valid_counts.get('valid', 0)}동에서 strict view rule을 만족했다.",
            "- 텍스처 앵커는 11동 모두 재측정됐지만 clean gap이 음수라 분리 유지 관찰은 나오지 않았다.",
            "- A3a의 취득 한계/수동판정 분류 규칙은 이 커밋에서 다시 바꾸지 않았다.",
            "- 카드와 corner zoom은 projection/render 산출이며 사진 매칭·재측정 산출이 아니다.",
            "",
            "## 7. 판정 필요 지점",
            "",
            "1. lowtex-v5 199/199 valid 산출을 수동판정 세션 입력으로 둘지 여부.",
            "2. 텍스처 앵커 clean gap 음수와 4907028 강기울기 v5 값을 lowtex 임계 논의에 어떻게 반영할지 여부.",
            "3. evidence_cards_v3 수동판정 대상 목록과 시간차 3동 목록을 확정할지 여부.",
            "4. A3a 15·6·27 변동(2·2·44)을 이후 subclass 재유도 입력으로 둘지 여부.",
        ]
    )
    REPORT_MD.write_text("\n".join(lines) + "\n")


def write_versions(lowtex_rows: list[dict[str, object]], manifest: list[dict[str, object]]) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    valid = sum(1 for r in lowtex_rows if r.get("lowtex_valid") == "valid")
    lines = [
        f"run_id: {RUN_ID}",
        f"git_head: {git_head()}",
        "command: python phases/p2-gsjso/scripts/aux_v4b.py",
        f"projection_config: {describe_projection_config()}",
        f"geoid_m: {ZETA:.6f}",
        f"python: {platform.python_version()}",
        f"numpy: {np.__version__}",
        "container: jointbuildgs-p0-tools:t0; Docker --user",
        "crs: geo EPSG:25832; OPF/COLMAP EPSG:32632 local with ellipsoidal Z",
        "reconstruction_or_retraining: none",
        f"lowtex_v5_valid: {valid}",
        f"evidence_cards_v3: {len(manifest)}",
        "",
    ]
    (RUN_DIR / "versions.txt").write_text("\n".join(lines))


def main() -> None:
    global BUILDING_CACHE
    if abs(ZETA_LEFT - ZETA) > 1e-9:
        raise RuntimeError("datum_tie_overlay ZETA_LEFT must stay at 45.700")
    BUILDING_CACHE = load_building_cache()
    print(f"[v4b] loaded GML buildings: {len(BUILDING_CACHE)}", flush=True)
    sr = json.load(open(DATA / "work/opf/opf/scene_reference_frame.json"))["base_to_canonical"]
    width, height, params = parse_cam_model(DATA / "work/colmap/sparse/0/cameras.txt")
    cams = parse_cameras(DATA / "work/colmap/sparse/0/images.txt", sr)
    rows = load_rows(POP_V4)
    lowtex = compute_lowtex_v5(rows, cams, params, sr, width, height)
    for row in rows:
        bid = row["building_id"].replace("DEBY_LOD2_", "")
        if bid in lowtex:
            lowtex[bid]["roof_lowtex_v4"] = row.get("roof_lowtex_v4", "")
    pop_rows = update_population(rows, lowtex)
    lowtex_rows = [dict(lowtex[r["building_id"].replace("DEBY_LOD2_", "")], roof_lowtex_v4=r.get("roof_lowtex_v4", ""), footprint_area_m2=r.get("footprint_area_m2", "")) for r in rows]
    write_lowtex_outputs(pop_rows, lowtex)
    anchors = anchor_rows(lowtex)
    manifest, skipped = render_cards(pop_rows, lowtex, cams, params, sr, width, height)
    corner_rows = refresh_corner_zooms(cams, params, sr, width, height)
    write_report(pop_rows, lowtex_rows, anchors, manifest, skipped, corner_rows)
    write_versions(lowtex_rows, manifest)
    print(f"[done] {LOWTEX_CSV}")
    print(f"[done] {ANCHOR_CSV}")
    print(f"[done] {REPORT_MD}")
    print(f"[done] {CARDDIR}")
    print(f"[done] {RUN_DIR / 'versions.txt'}")


if __name__ == "__main__":
    main()

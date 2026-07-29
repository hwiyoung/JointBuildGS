#!/usr/bin/env python3
"""Classify E5 pilot apparent successes by roof-structure substance.

Read-only over existing E5 pilot outputs.  No training, recipe, or Roofer
parameter changes are made here.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import laspy
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

import pointcloud_attributes_v1 as base
from e5_pilot_gate_tools import C001_IDS, READOUT_STRING, run_names


GATE_RUN_DIR = Path("phases/p0-audit/runs/e5p_gate_20260707_C001")
TRAIN_RUN_DIR = Path("phases/p2-gsjso/runs/e5p_train_20260707_C001")
LOD2_DIR = Path("phases/p0-audit/data/raw/lod2")
FOOTPRINTS_GPKG = Path("phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg")
REPORT_PATH = Path("docs/experiments/e5_pilot_substantiveness/reports/W_E5_pilot_substantiveness.md")
DETAIL_CSV = Path("docs/experiments/e5_pilot_substantiveness/tables/e5_pilot_substantiveness_detail.csv")
SUMMARY_CSV = Path("docs/experiments/e5_pilot_substantiveness/tables/e5_pilot_substantiveness_summary.csv")
PAIR_CSV = Path("docs/experiments/e5_pilot_substantiveness/tables/e5_pilot_substantiveness_pair_clean.csv")
SELECTION_CSV = Path("docs/experiments/e5_pilot_substantiveness/tables/e5_pilot_substantiveness_panel_selection.csv")
FIG_DIR = Path("docs/figs/e5_pilot/subst")
RUN_DIR = Path("phases/p2-gsjso/runs/20260707_e5_pilot_subst")

RAW_POINTCLOUDS = {
    "sparse": Path("phases/p0-audit/runs/e5p_baseline_sparse_20260706_002300/classified/raw_sparse_classified.laz"),
    "dense": Path("phases/p0-audit/data/work/w2/dim_v1_classified_z_minus0p174.laz"),
    "acmp": Path("phases/p0-audit/runs/e5p_baseline_acmp_20260706_001813/classified/raw_acmp_classified.laz"),
}
PAIR_BASELINE_HAS_LOD22 = {"sparse": 2, "dense": 10, "acmp": 12}
PAIR_BASELINE_LABEL = {"sparse": "raw-sparse", "dense": "raw-dense(w2_1 DIM)", "acmp": "raw-ACMP"}
TEXTURELESS_IDS = ("DEBY_LOD2_8568391", "DEBY_LOD2_8568392")
ACMP_REGRESSION_IDS = ("DEBY_LOD2_108247350", "DEBY_LOD2_108247351")

PRIMARY_LABELS = {
    "shell": "결손",
    "under_seg": "과병합",
    "clean_struct": "구조 일치",
    "over_seg": "과분할",
}


def configure_korean_font() -> None:
    candidates = [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    ]
    for path in candidates:
        if path.exists():
            font_manager.fontManager.addfont(str(path))
            plt.rcParams["font.family"] = "Noto Sans CJK JP"
            plt.rcParams["axes.unicode_minus"] = False
            return


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def tf(value: Any) -> bool:
    return str(value).lower() in {"true", "1", "yes", "y"}


def num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        v = float(value)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)):
            return ""
        return f"{float(value):.{digits}f}"
    return str(value)


def run_meta(run_name: str) -> tuple[str, str]:
    parts = run_name.split("_")
    return parts[-2], parts[-1]


def primary_class(pred_roof_planes: int, ref_roof_planes: int) -> str:
    if pred_roof_planes == 0:
        return "shell"
    if pred_roof_planes < ref_roof_planes:
        return "under_seg"
    if pred_roof_planes == ref_roof_planes:
        return "clean_struct"
    return "over_seg"


def rmse_tail_fence(values: list[float]) -> dict[str, float]:
    q1, median, q3 = np.percentile(values, [25, 50, 75])
    iqr = q3 - q1
    return {
        "q1": float(q1),
        "median": float(median),
        "q3": float(q3),
        "iqr": float(iqr),
        "upper_fence": float(q3 + 1.5 * iqr),
    }


def load_reference_counts() -> dict[str, int]:
    roofs = base.load_roof_surfaces(LOD2_DIR, set(C001_IDS))
    missing = [bid for bid in C001_IDS if not roofs.get(bid)]
    if missing:
        raise RuntimeError(f"missing reference RoofSurface for {missing[:5]}")
    return {bid: len(roofs[bid]) for bid in C001_IDS}


def build_detail_rows() -> tuple[list[dict[str, Any]], dict[str, float]]:
    status_rows = read_csv(GATE_RUN_DIR / "building_reconstruction_status.csv")
    prep_rows = read_csv(GATE_RUN_DIR / "prep_metrics.csv")
    prep_by = {(r["run_name"], r["roofer_repeat"], r["building_id"]): r for r in prep_rows}
    ref_counts = load_reference_counts()
    finite_rmse = [
        float(r["rf_rmse_lod22"])
        for r in status_rows
        if r["roofer_repeat"] == "run_1" and tf(r["has_lod22"]) and num(r.get("rf_rmse_lod22")) is not None
    ]
    fence = rmse_tail_fence(finite_rmse)

    rows: list[dict[str, Any]] = []
    for run_name in run_names():
        arm, replicate = run_meta(run_name)
        for r in status_rows:
            if r["run_name"] != run_name or r["roofer_repeat"] != "run_1":
                continue
            bid = r["building_id"]
            pred = int(float(r["rf_roof_planes"] or 0))
            ref = ref_counts[bid]
            klass = primary_class(pred, ref)
            rmse = num(r.get("rf_rmse_lod22"))
            success = tf(r["has_lod22"])
            rmse_tail = bool(success and rmse is not None and rmse > fence["upper_fence"])
            clean = bool(success and klass == "clean_struct" and not rmse_tail)
            prep = prep_by.get((run_name, "run_1", bid), {})
            clip_points = int(float(prep.get("n_building_in_fp") or 0)) if prep else 0
            rows.append(
                {
                    "arm": arm,
                    "replicate": replicate,
                    "run_name": run_name,
                    "building_id": bid,
                    "has_lod22": str(success),
                    "ref_roof_planes": ref,
                    "gs_roof_planes": pred,
                    "primary_class": klass,
                    "primary_label": PRIMARY_LABELS[klass],
                    "rf_rmse_lod22": fmt(rmse, 6),
                    "rmse_tail": str(rmse_tail),
                    "clean": str(clean),
                    "val3dity_valid": str(tf(r.get("val3dity_valid"))),
                    "status_reason": r.get("reason", ""),
                    "roofer_no_points": str(r.get("reason", "") == "pointcloud_unusable_no_points"),
                    "clip_building_points": clip_points,
                    "clip_zero_points": str(clip_points == 0),
                }
            )
    return rows, fence


def build_summary(detail_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    by_run: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in detail_rows:
        by_run[(row["arm"], row["replicate"])].append(row)
    for arm in ("sparse", "dense", "acmp"):
        for replicate in ("r1", "r2"):
            rows = by_run[(arm, replicate)]
            counts = Counter(r["primary_class"] for r in rows)
            out.append(
                {
                    "씨앗": arm,
                    "씨드": replicate,
                    "성공 수": sum(tf(r["has_lod22"]) for r in rows),
                    "결손": counts["shell"],
                    "과병합": counts["under_seg"],
                    "구조 일치": counts["clean_struct"],
                    "과분할": counts["over_seg"],
                    "적합 붕괴(rmse 꼬리)": sum(tf(r["rmse_tail"]) for r in rows),
                    "클린": sum(tf(r["clean"]) for r in rows),
                    "val3dity 유효": sum(tf(r["val3dity_valid"]) for r in rows),
                }
            )
    return out


def build_pair_clean(summary_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by = {(r["씨앗"], r["씨드"]): r for r in summary_rows}
    out = []
    for arm in ("sparse", "dense", "acmp"):
        out.append(
            {
                "씨앗": arm,
                "짝 기준": PAIR_BASELINE_LABEL[arm],
                "기준 has_lod22": f"{PAIR_BASELINE_HAS_LOD22[arm]}/18",
                "GS r1 has_lod22": f"{by[(arm, 'r1')]['성공 수']}/18",
                "GS r1 클린": f"{by[(arm, 'r1')]['클린']}/18",
                "GS r2 has_lod22": f"{by[(arm, 'r2')]['성공 수']}/18",
                "GS r2 클린": f"{by[(arm, 'r2')]['클린']}/18",
            }
        )
    return out


def md_table(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    if not rows:
        return ["_none_"]
    out = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(row.get(c, "")) for c in columns) + " |")
    return out


def absolute_vertices(payload: dict[str, Any]) -> np.ndarray:
    arr = np.asarray(payload.get("vertices", []), dtype=float)
    if arr.size == 0:
        return arr.reshape((0, 3))
    tr = payload.get("transform", {})
    scale = np.asarray(tr.get("scale", [1, 1, 1]), dtype=float)
    translate = np.asarray(tr.get("translate", [0, 0, 0]), dtype=float)
    return arr * scale + translate


def iter_cityjson_faces(geom_type: str | None, boundaries: Any, values: Any) -> list[tuple[list[list[int]], int | None]]:
    faces: list[tuple[list[list[int]], int | None]] = []
    if boundaries is None:
        return faces
    if geom_type == "Solid":
        for shell_idx, shell in enumerate(boundaries):
            shell_values = values[shell_idx] if isinstance(values, list) and shell_idx < len(values) else []
            for face_idx, rings in enumerate(shell):
                sem_idx = shell_values[face_idx] if isinstance(shell_values, list) and face_idx < len(shell_values) else None
                faces.append((rings, sem_idx))
    elif geom_type in {"MultiSurface", "CompositeSurface"}:
        for face_idx, rings in enumerate(boundaries):
            sem_idx = values[face_idx] if isinstance(values, list) and face_idx < len(values) else None
            faces.append((rings, sem_idx))
    elif geom_type == "MultiSolid":
        for solid_idx, solid in enumerate(boundaries):
            solid_values = values[solid_idx] if isinstance(values, list) and solid_idx < len(values) else []
            for shell_idx, shell in enumerate(solid):
                shell_values = solid_values[shell_idx] if isinstance(solid_values, list) and shell_idx < len(solid_values) else []
                for face_idx, rings in enumerate(shell):
                    sem_idx = shell_values[face_idx] if isinstance(shell_values, list) and face_idx < len(shell_values) else None
                    faces.append((rings, sem_idx))
    return faces


def cityjson_polys(path: Path, bid: str) -> tuple[list[np.ndarray], list[np.ndarray]]:
    if not path.exists():
        return [], []
    payload = json.loads(path.read_text(encoding="utf-8"))
    vertices = absolute_vertices(payload)
    cityobjects = payload.get("CityObjects", {})
    object_ids = [bid, *cityobjects.get(bid, {}).get("children", [])]
    roofs: list[np.ndarray] = []
    others: list[np.ndarray] = []
    for object_id in object_ids:
        obj = cityobjects.get(object_id)
        if not obj:
            continue
        for geom in obj.get("geometry", []):
            semantics = geom.get("semantics") or {}
            surfaces = semantics.get("surfaces") or []
            values = semantics.get("values")
            for rings, sem_idx in iter_cityjson_faces(geom.get("type"), geom.get("boundaries"), values):
                if not rings:
                    continue
                ring = rings[0]
                if not ring:
                    continue
                poly = vertices[np.asarray(ring, dtype=int)]
                typ = ""
                if sem_idx is not None and 0 <= int(sem_idx) < len(surfaces):
                    typ = surfaces[int(sem_idx)].get("type", "")
                (roofs if typ == "RoofSurface" else others).append(poly)
    return roofs, others


def draw_cloud(ax: Any, points: np.ndarray, title: str, color: np.ndarray | None = None, cmap: str = "viridis") -> None:
    ax.set_title(title, fontsize=8)
    if len(points) == 0:
        ax.text(0.5, 0.5, "점 없음", ha="center", va="center", transform=ax.transAxes, fontsize=8)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_box_aspect(1)
        ax.set_xticks([])
        ax.set_yticks([])
        return
    if len(points) > 60000:
        idx = np.random.default_rng(0).choice(len(points), 60000, replace=False)
        points = points[idx]
        if color is not None:
            color = color[idx]
    if color is None:
        color = points[:, 2] - np.nanmin(points[:, 2])
    ax.scatter(points[:, 0], points[:, 1], c=color, cmap=cmap, s=0.8, linewidths=0)
    mn = points[:, :2].min(axis=0)
    mx = points[:, :2].max(axis=0)
    ctr = (mn + mx) / 2
    radius = max(float((mx - mn).max()) / 2, 1.0)
    ax.set_xlim(ctr[0] - radius, ctr[0] + radius)
    ax.set_ylim(ctr[1] - radius, ctr[1] + radius)
    ax.set_aspect("equal", adjustable="box")
    ax.set_box_aspect(1)
    ax.set_xticks([])
    ax.set_yticks([])


def draw_model(ax: Any, roofs: list[np.ndarray], others: list[np.ndarray], title: str) -> None:
    ax.set_title(title, fontsize=8)
    if not roofs and not others:
        ax.text2D(0.5, 0.5, "조립 없음", ha="center", va="center", transform=ax.transAxes, fontsize=8)
        ax.set_axis_off()
        return
    allpts = np.vstack(roofs + others)
    zmin = allpts[:, 2].min()

    def shifted(poly: np.ndarray) -> np.ndarray:
        q = poly.copy()
        q[:, 2] -= zmin
        return q

    if others:
        ax.add_collection3d(
            Poly3DCollection([shifted(p) for p in others], facecolor="0.82", edgecolor="0.55", linewidths=0.15, alpha=0.30)
        )
    if roofs:
        colors = [plt.cm.tab20(i % 20) for i in range(len(roofs))]
        ax.add_collection3d(
            Poly3DCollection([shifted(p) for p in roofs], facecolor=colors, edgecolor="k", linewidths=0.25, alpha=0.92)
        )
    mn = allpts.min(axis=0)
    mx = allpts.max(axis=0)
    ctr = (mn + mx) / 2
    radius = max(float((mx - mn)[:2].max()) / 2, 1.0)
    ax.set_xlim(ctr[0] - radius, ctr[0] + radius)
    ax.set_ylim(ctr[1] - radius, ctr[1] + radius)
    ax.set_zlim(0, max(float(mx[2] - mn[2]) * 1.1, 1.0))
    ax.view_init(elev=28, azim=-58)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_zticks([])
    ax.set_box_aspect((1, 1, 0.5))
    ax.text2D(0.02, 0.93, f"roof {len(roofs)}", transform=ax.transAxes, fontsize=7)


def read_roof_points(path: Path, bid: str, footprints: dict[str, Any]) -> np.ndarray:
    if not path.exists():
        return np.empty((0, 3), dtype=np.float64)
    xyz, cls = base.read_las_footprint(path, footprints[bid])
    if len(xyz) == 0:
        return np.empty((0, 3), dtype=np.float64)
    return xyz[np.asarray(cls) == 6]


def gs_las_path(run_name: str, bid: str) -> Path:
    return GATE_RUN_DIR / "roofer" / run_name / "run_1" / f"{bid}_run_1_classified.las"


def cityjson_path(run_name: str) -> Path:
    return GATE_RUN_DIR / "cityjson" / f"{run_name}_run_1.city.json"


def draw_distance_cloud(ax: Any, points: np.ndarray, roofs_ref: list[Any], title: str) -> None:
    ax.set_title(title, fontsize=8)
    if len(points) == 0:
        ax.text(0.5, 0.5, "점 없음", ha="center", va="center", transform=ax.transAxes, fontsize=8)
        ax.set_xticks([])
        ax.set_yticks([])
        return
    zref, _miss = base.local_ref_z(points[:, 0], points[:, 1], roofs_ref, None)
    if zref is None:
        draw_cloud(ax, points, title)
        return
    delta = points[:, 2] - zref
    draw_cloud(ax, points, title, color=np.clip(delta, -3, 3), cmap="coolwarm")


def make_case_panel(case_rows: list[dict[str, Any]], out: Path, title: str, footprints: dict[str, Any], ref_roofs: dict[str, list[Any]]) -> None:
    nrows = len(case_rows)
    fig = plt.figure(figsize=(15, 3.3 * nrows))
    for ridx, row in enumerate(case_rows):
        bid = row["building_id"]
        arm = row["arm"]
        run_name = row["run_name"]
        raw_pts = read_roof_points(RAW_POINTCLOUDS[arm], bid, footprints)
        gs_pts = read_roof_points(gs_las_path(run_name, bid), bid, footprints)
        roofs, others = cityjson_polys(cityjson_path(run_name), bid)
        base_idx = ridx * 5
        row_title = (
            f"{arm}-{row['replicate']} {bid.replace('DEBY_LOD2_', '')}: "
            f"ref {row['ref_roof_planes']} / GS {row['gs_roof_planes']}, "
            f"RMSE {row['rf_rmse_lod22'] or 'NA'}"
        )
        draw_cloud(fig.add_subplot(nrows, 5, base_idx + 1), raw_pts, f"{row_title}\nraw 점군")
        draw_cloud(fig.add_subplot(nrows, 5, base_idx + 2), gs_pts, "GS 점군")
        draw_model(fig.add_subplot(nrows, 5, base_idx + 3, projection="3d"), roofs, others, "조립 결과")
        draw_distance_cloud(fig.add_subplot(nrows, 5, base_idx + 4), gs_pts, ref_roofs[bid], "면-거리 색칠")
        draw_model(fig.add_subplot(nrows, 5, base_idx + 5, projection="3d"), roofs, others, "면별 모델")
    fig.suptitle(title, fontsize=12)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170)
    plt.close(fig)


def plot_scatter(detail_rows: list[dict[str, Any]], out: Path) -> None:
    colors = {"shell": "#666666", "under_seg": "#2b6cb0", "clean_struct": "#2f855a", "over_seg": "#c53030"}
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True)
    for ax, arm in zip(axes, ("sparse", "dense", "acmp")):
        sub = [r for r in detail_rows if r["arm"] == arm]
        for replicate, marker in (("r1", "o"), ("r2", "^")):
            rep_rows = [r for r in sub if r["replicate"] == replicate]
            ax.scatter(
                [int(r["ref_roof_planes"]) for r in rep_rows],
                [int(r["gs_roof_planes"]) for r in rep_rows],
                c=[colors[r["primary_class"]] for r in rep_rows],
                marker=marker,
                s=44,
                edgecolor="white",
                linewidth=0.5,
                label=replicate,
                alpha=0.9,
            )
        max_v = max([int(r["gs_roof_planes"]) for r in sub] + [int(r["ref_roof_planes"]) for r in sub] + [5])
        ax.plot([0, max_v], [0, max_v], "--", color="0.4", linewidth=0.8)
        ax.set_title(arm)
        ax.set_xlabel("참조 지붕면 수")
        ax.set_xlim(-0.5, max(5, max(int(r["ref_roof_planes"]) for r in sub) + 1))
        ax.set_ylim(-1, max_v + 5)
        ax.grid(True, alpha=0.25)
        for r in sub:
            if int(r["gs_roof_planes"]) >= 10:
                ax.annotate(r["building_id"].replace("DEBY_LOD2_", ""), (int(r["ref_roof_planes"]), int(r["gs_roof_planes"])), fontsize=6)
    axes[0].set_ylabel("GS 지붕면 수")
    handles = [
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=colors[k], label=v, markersize=7)
        for k, v in PRIMARY_LABELS.items()
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=8)
    fig.suptitle("GS 지붕면 수 vs 참조 지붕면 수")
    fig.tight_layout(rect=(0, 0.12, 1, 0.94))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)


def plot_rmse_hist(detail_rows: list[dict[str, Any]], fence: dict[str, float], out: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharey=True)
    bins = np.linspace(0, 45, 16)
    for ax, arm in zip(axes, ("sparse", "dense", "acmp")):
        vals = [float(r["rf_rmse_lod22"]) for r in detail_rows if r["arm"] == arm and r["rf_rmse_lod22"]]
        ax.hist(vals, bins=bins, color="#4a6fa5", edgecolor="white", alpha=0.85)
        ax.axvline(1.0, color="#2f855a", linestyle="--", linewidth=1.2, label="1 m")
        ax.axvline(31.0, color="#c53030", linestyle=":", linewidth=1.2, label="31 m")
        ax.axvline(fence["upper_fence"], color="black", linestyle="-.", linewidth=1.0, label="Tukey")
        ax.set_title(arm)
        ax.set_xlabel("rf_rmse_lod22 (m)")
        ax.grid(True, axis="y", alpha=0.25)
    axes[0].set_ylabel("동 수")
    axes[-1].legend(fontsize=7)
    fig.suptitle("RMSE 분포: 1 m·31 m 앵커선과 데이터 꼬리선")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)


def make_contact_sheet(rows: list[dict[str, Any]], out: Path, title: str) -> None:
    cols = 4
    rows_n = max(1, math.ceil(len(rows) / cols))
    fig, axes = plt.subplots(rows_n, cols, figsize=(13, 2.2 * rows_n))
    axes_arr = np.asarray(axes).reshape(-1)
    for ax in axes_arr:
        ax.set_axis_off()
    for ax, row in zip(axes_arr, rows):
        ax.set_axis_on()
        ax.set_xticks([])
        ax.set_yticks([])
        ref = int(row["ref_roof_planes"])
        pred = int(row["gs_roof_planes"])
        ax.barh([0], [max(ref, 0.01)], color="#d9e2ec", height=0.28, label="ref")
        ax.barh([0.35], [max(pred, 0.01)], color="#c53030" if pred > ref else "#666666", height=0.28, label="GS")
        ax.set_xlim(0, max(ref, pred, 1) * 1.2)
        ax.set_ylim(-0.3, 0.8)
        ax.text(
            0.02,
            0.95,
            f"{row['arm']}-{row['replicate']} {row['building_id'].replace('DEBY_LOD2_', '')}\n"
            f"ref {ref} / GS {pred}, RMSE {row['rf_rmse_lod22'] or 'NA'}\n"
            f"{row['primary_label']} · valid {row['val3dity_valid']}",
            transform=ax.transAxes,
            va="top",
            fontsize=7,
        )
    fig.suptitle(title, fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170)
    plt.close(fig)


def status_lookup(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(r["run_name"], r["building_id"]): r for r in rows}


def select_panels(detail_rows: list[dict[str, Any]], footprints: dict[str, Any], ref_roofs: dict[str, list[Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    by = status_lookup(detail_rows)

    for arm in ("sparse", "dense", "acmp"):
        clean_rows = [r for r in detail_rows if r["arm"] == arm and tf(r["clean"]) and r["rf_rmse_lod22"]]
        if clean_rows:
            med = float(np.median([float(r["rf_rmse_lod22"]) for r in clean_rows]))
            row = min(clean_rows, key=lambda r: (abs(float(r["rf_rmse_lod22"]) - med), r["replicate"], r["building_id"]))
            fig = FIG_DIR / f"panel_typical_clean_{arm}_{row['replicate']}_{row['building_id']}.png"
            make_case_panel([row], fig, f"구조 일치 대표: {arm}", footprints, ref_roofs)
            selected.append({**selection_row("구조 일치 대표", row, "클린 중 RMSE 중앙값에 가장 가까움"), "figure": str(fig)})

        tex_rows = [r for r in detail_rows if r["arm"] == arm and r["building_id"] in TEXTURELESS_IDS and tf(r["has_lod22"])]
        if tex_rows:
            row = min(tex_rows, key=lambda r: (not tf(r["clean"]), num(r["rf_rmse_lod22"]) if num(r["rf_rmse_lod22"]) is not None else math.inf, r["replicate"], r["building_id"]))
            fig = FIG_DIR / f"panel_textureless_{arm}_{row['replicate']}_{row['building_id']}.png"
            make_case_panel([row], fig, f"무텍스처 복구 대표: {arm}", footprints, ref_roofs)
            selected.append({**selection_row("무텍스처 복구", row, "8568391·8568392 중 has_lod22 후 RMSE 낮은 행"), "figure": str(fig)})

        flip_bids = []
        for bid in C001_IDS:
            r1 = by.get((f"gs_e5_C001_{arm}_r1", bid))
            r2 = by.get((f"gs_e5_C001_{arm}_r2", bid))
            if r1 and r2 and tf(r1["has_lod22"]) != tf(r2["has_lod22"]):
                flip_bids.append(bid)
        if flip_bids:
            bid = sorted(flip_bids)[0]
            rows = [by[(f"gs_e5_C001_{arm}_r1", bid)], by[(f"gs_e5_C001_{arm}_r2", bid)]]
            fig = FIG_DIR / f"panel_seed_flip_{arm}_{bid}.png"
            make_case_panel(rows, fig, f"씨드 변동 대표: {arm}", footprints, ref_roofs)
            selected.append({**selection_row("씨드 변동", rows[0], "r1/r2 has_lod22 flip 중 building_id 사전순 첫 행"), "figure": str(fig), "paired_run": rows[1]["run_name"]})

    for bid in ACMP_REGRESSION_IDS:
        candidates = [r for r in detail_rows if r["arm"] == "acmp" and r["building_id"] == bid and not tf(r["has_lod22"])]
        if candidates:
            row = sorted(candidates, key=lambda r: r["replicate"])[0]
            fig = FIG_DIR / f"panel_acmp_regression_{row['replicate']}_{bid}.png"
            make_case_panel([row], fig, "ACMP 짝 기준 회귀 사례", footprints, ref_roofs)
            selected.append({**selection_row("ACMP 회귀", row, "지정 ID 108247350·108247351 중 GS 미조립 행"), "figure": str(fig)})

    shell_rows = [r for r in detail_rows if r["primary_class"] == "shell"]
    over_rows = [r for r in detail_rows if r["primary_class"] == "over_seg"]
    make_contact_sheet(shell_rows, FIG_DIR / "pathology_all_shell.png", "결손 전수: GS 지붕면 0")
    make_contact_sheet(over_rows, FIG_DIR / "pathology_all_overseg.png", "과분할 전수: GS 지붕면 > 참조")
    return selected


def selection_row(kind: str, row: dict[str, Any], rule: str) -> dict[str, Any]:
    return {
        "유형": kind,
        "선정 규칙": rule,
        "씨앗": row["arm"],
        "씨드": row["replicate"],
        "run_name": row["run_name"],
        "building_id": row["building_id"],
        "ref_roof_planes": row["ref_roof_planes"],
        "gs_roof_planes": row["gs_roof_planes"],
        "rf_rmse_lod22": row["rf_rmse_lod22"],
        "primary_label": row["primary_label"],
        "clean": row["clean"],
    }


def write_versions(fence: dict[str, float]) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    head = capture(["git", "rev-parse", "HEAD"])
    branch = capture(["git", "branch", "--show-current"])
    lines = [
        "run_id: 20260707_e5_pilot_subst",
        f"created_utc: {datetime.now(timezone.utc).isoformat()}",
        "task: E5 pilot substantiveness classification and qualitative panels",
        "mode: read-only over existing six GS pilot runs; no retraining; no recipe change; no Roofer change; no gate verdict",
        "crs: EPSG:25832",
        f"git_head: {head}",
        f"git_branch: {branch}",
        "docker_image: jointbuildgs-p0-tools:t0",
        f"readout: {READOUT_STRING}",
        f"input_gate_run: {GATE_RUN_DIR}",
        f"input_train_run: {TRAIN_RUN_DIR}",
        "reference_lod2: phases/p0-audit/data/raw/lod2/*.gml",
        "w_d6_shape_correction: docs/W_D6_shape_audit.md; 4906969=stepped flat roof; curved roofs=0 in D6 set",
        f"rmse_tail_upper_fence_m: {fence['upper_fence']:.6f}",
        f"script: phases/p2-gsjso/scripts/{Path(__file__).name}",
    ]
    (RUN_DIR / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def capture(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True).strip()


def write_report(
    summary_rows: list[dict[str, Any]],
    pair_rows: list[dict[str, Any]],
    selected_rows: list[dict[str, Any]],
    fence: dict[str, float],
) -> None:
    obs_bits = []
    for arm in ("sparse", "dense", "acmp"):
        sub = [r for r in summary_rows if r["씨앗"] == arm]
        success = sum(int(r["성공 수"]) for r in sub)
        shell = sum(int(r["결손"]) for r in sub)
        over = sum(int(r["과분할"]) for r in sub)
        clean = sum(int(r["클린"]) for r in sub)
        obs_bits.append(f"{arm}: 성공 {success}/36 · 결손 {shell}/36 · 과분할 {over}/36 · 클린 {clean}/36")
    branch = capture(["git", "branch", "--show-current"])
    head = capture(["git", "rev-parse", "HEAD"])
    lines = [
        "# E5 파일럿 실질성 분류",
        "",
        "> 판정 금지. 재학습 0 · 레시피 변경 0 · Roofer 변경 0. 기존 6런 `gs_e5_C001_{sparse,dense,acmp}_{r1,r2}` 산출만 읽었다. CRS는 EPSG:25832.",
        "",
        "## 시작 전 확인",
        "",
        f"- 브랜치·HEAD: `{branch}` · `{head}`.",
        f"- 입력 보고서·표: `{REPORT_PATH.with_name('W_E5_pilot_gate.md')}`, `docs/e5_pilot_seed_pair_status.csv`.",
        f"- 조립 출력: `{GATE_RUN_DIR}/`.",
        f"- 점군화·지문: `{TRAIN_RUN_DIR}/`.",
        "- 참조 지붕 구조: LoD2 참조 CityGML의 RoofSurface 수·형상. W_D6 형상 교정본을 준용했고, 4906969는 단차 평지붕이며 D6 작업동의 곡면 지붕은 0동으로 기록한다.",
        "",
        "## 잣대",
        "",
        "- 1차 축: GS 지붕면 수와 참조 RoofSurface 수를 비교했다. 0이면 결손, 참조보다 작으면 과병합, 같으면 구조 일치, 크면 과분할로 적었다.",
        "- 분류표는 C001 18동 전수 회계다. 성공 수는 `has_lod22`이고, 결손은 지붕면 0인 미조립 행까지 포함한다.",
        "- 2차 축: `rf_rmse_lod22` 분포를 봤다. 적합 붕괴는 전체 GS run_1 성공 61건의 Tukey 상단 울타리로 표시했다.",
        f"- RMSE 분포값: Q1 {fence['q1']:.3f} m · 중앙값 {fence['median']:.3f} m · Q3 {fence['q3']:.3f} m · 꼬리선 {fence['upper_fence']:.3f} m.",
        "- 그림에는 LDBV LoD2 1 m와 P0 4907019 껍데기 31 m를 앵커선으로 함께 표시했다.",
        "- 유효성(val3dity)은 실질성 기준이 아니므로 별도 열로만 병기했다.",
        "- 정밀 completeness/correctness 매칭은 전수 실험으로 이월한다. 파일럿은 지붕면 수 대 참조와 RMSE 분포로 근사했다.",
        "",
        "## 분류표",
        "",
        *md_table(summary_rows, ["씨앗", "씨드", "성공 수", "결손", "과병합", "구조 일치", "과분할", "적합 붕괴(rmse 꼬리)", "클린", "val3dity 유효"]),
        "",
        "## 씨앗별 짝 대비",
        "",
        *md_table(pair_rows, ["씨앗", "짝 기준", "기준 has_lod22", "GS r1 has_lod22", "GS r1 클린", "GS r2 has_lod22", "GS r2 클린"]),
        "",
        "## 그림",
        "",
        f"- 지붕면 수 산점도: `{FIG_DIR / 'scatter_roofplanes_by_seed.png'}`.",
        f"- RMSE 분포: `{FIG_DIR / 'rmse_hist_by_seed.png'}`.",
        f"- 결손 전수 그림: `{FIG_DIR / 'pathology_all_shell.png'}`.",
        f"- 과분할 전수 그림: `{FIG_DIR / 'pathology_all_overseg.png'}`.",
        "",
        "## 정성 패널 선정",
        "",
        *md_table(selected_rows, ["유형", "선정 규칙", "씨앗", "씨드", "building_id", "ref_roof_planes", "gs_roof_planes", "rf_rmse_lod22", "primary_label", "clean", "figure"]),
        "",
        "## 산출 표",
        "",
        f"- 전수 세부표: `{DETAIL_CSV}`.",
        f"- 요약표: `{SUMMARY_CSV}`.",
        f"- 클린 재집계: `{PAIR_CSV}`.",
        f"- 패널 선정표: `{SELECTION_CSV}`.",
        f"- 실행 지문: `{RUN_DIR / 'versions.txt'}`.",
        "",
        "## 관찰",
        "",
        "- " + " / ".join(obs_bits) + ". 각 수치는 씨앗별 36행 기준이다.",
        "- 위 수치와 그림은 판정 재료이며, 게이트 판단 문구는 쓰지 않는다.",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-panels", action="store_true", help="only write tables/report")
    return parser


def main() -> None:
    args = build_argparser().parse_args()
    configure_korean_font()
    detail_rows, fence = build_detail_rows()
    summary_rows = build_summary(detail_rows)
    pair_rows = build_pair_clean(summary_rows)
    write_csv(DETAIL_CSV, detail_rows)
    write_csv(SUMMARY_CSV, summary_rows)
    write_csv(PAIR_CSV, pair_rows)
    plot_scatter(detail_rows, FIG_DIR / "scatter_roofplanes_by_seed.png")
    plot_rmse_hist(detail_rows, fence, FIG_DIR / "rmse_hist_by_seed.png")
    ref_roofs = base.load_roof_surfaces(LOD2_DIR, set(C001_IDS))
    footprints = base.load_footprints(FOOTPRINTS_GPKG, set(C001_IDS))
    selected_rows = select_panels(detail_rows, footprints, ref_roofs) if not args.skip_panels else []
    write_csv(SELECTION_CSV, selected_rows)
    write_versions(fence)
    write_report(summary_rows, pair_rows, selected_rows, fence)
    print(json.dumps({"report": str(REPORT_PATH), "fig_dir": str(FIG_DIR), "detail_rows": len(detail_rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

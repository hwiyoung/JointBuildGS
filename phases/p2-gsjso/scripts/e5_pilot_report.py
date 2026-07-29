#!/usr/bin/env python3
"""Build E5 pilot gate report tables and figures.

The report is gate material only.  It names counts, flips, failures, and figure
paths, but does not declare pass/fail.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import laspy
import matplotlib
import numpy as np
from shapely.geometry import Polygon

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

import pointcloud_attributes_v1 as base
from e5_pilot_gate_tools import C001_IDS, READOUT_STRING, run_names


RAW_ACMP_STATUS = Path("phases/p0-audit/runs/e5p_baseline_acmp_20260706_001813/building_reconstruction_status.csv")
RAW_SPARSE_STATUS = Path("phases/p0-audit/runs/e5p_baseline_sparse_20260706_002300/building_reconstruction_status.csv")
W2_STATUS = Path("phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv")
RAW_SPARSE_LAS = Path("phases/p0-audit/runs/e5p_baseline_sparse_20260706_002300/classified/raw_sparse_classified.laz")
FOOTPRINTS_GEOJSON = Path("results/tum_transfer/analysis/footprints_aoi.geojson")
FOOTPRINTS_GPKG = Path("phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg")
LOD2_DIR = Path("phases/p0-audit/data/raw/lod2")


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
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def tf(value: str | None) -> bool:
    return str(value).lower() == "true"


def num(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        v = float(value)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def status_lookup(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    return {(r["input"], r["building_id"]): r for r in rows}


def md_table(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    if not rows:
        return ["_none_"]
    out = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(row.get(c, "")) for c in columns) + " |")
    return out


def load_footprint_rings() -> dict[str, np.ndarray]:
    payload = json.loads(FOOTPRINTS_GEOJSON.read_text(encoding="utf-8"))
    out = {}
    for feat in payload["features"]:
        bid = feat.get("properties", {}).get("building_id")
        if bid not in C001_IDS:
            continue
        geom = feat["geometry"]
        ring = geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"][0][0]
        out[bid] = np.asarray(ring, dtype=np.float64)
    return out


def in_ring(points: np.ndarray, ring: np.ndarray, buffer_m: float = 0.0) -> np.ndarray:
    if len(points) == 0:
        return np.zeros((0,), dtype=bool)
    poly = Polygon(ring)
    if buffer_m:
        poly = poly.buffer(buffer_m)
    from shapely import contains_xy

    return contains_xy(poly, points[:, 0], points[:, 1])


def las_points(path: Path, bid: str, rings: dict[str, np.ndarray], class_filter: int | None = None) -> np.ndarray:
    if not path.exists():
        return np.empty((0, 3), dtype=np.float64)
    las = laspy.read(str(path))
    xyz = np.column_stack([np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)])
    cls = np.asarray(las.classification, dtype=np.uint8)
    mask = in_ring(xyz, rings[bid], buffer_m=2.0)
    if class_filter is not None:
        mask &= cls == class_filter
    return xyz[mask]


def cityjson_object_polys(path: Path, bid: str) -> tuple[list[np.ndarray], list[np.ndarray]]:
    if not path.exists():
        return [], []
    cj = json.loads(path.read_text(encoding="utf-8"))
    tr = cj.get("transform", {})
    scale = np.asarray(tr.get("scale", [1, 1, 1]), dtype=float)
    trans = np.asarray(tr.get("translate", [0, 0, 0]), dtype=float)
    verts = np.asarray(cj.get("vertices", []), dtype=float) * scale + trans
    roofs, others = [], []
    obj = cj.get("CityObjects", {}).get(bid)
    if obj is None:
        return [], []
    for geom in obj.get("geometry", []):
        sem = geom.get("semantics", {})
        surfaces = sem.get("surfaces", [])
        values = sem.get("values")
        if geom.get("type") == "Solid":
            shells = geom.get("boundaries", [])
            val_shells = values or []
        elif geom.get("type") == "MultiSurface":
            shells = [geom.get("boundaries", [])]
            val_shells = [values] if values is not None else []
        else:
            continue
        for si, shell in enumerate(shells):
            val_faces = val_shells[si] if si < len(val_shells) else None
            for fi, surf in enumerate(shell):
                ring = surf[0] if surf and isinstance(surf[0], list) else surf
                if not ring:
                    continue
                poly = verts[np.asarray(ring, dtype=int)]
                typ = ""
                if val_faces is not None and fi < len(val_faces) and val_faces[fi] is not None:
                    idx = int(val_faces[fi])
                    if 0 <= idx < len(surfaces):
                        typ = surfaces[idx].get("type", "")
                (roofs if typ == "RoofSurface" else others).append(poly)
    return roofs, others


def draw_cloud(ax, points: np.ndarray, title: str, color_by_z: bool = True) -> None:
    ax.set_title(title, fontsize=9)
    if len(points) == 0:
        ax.text(0.5, 0.5, "점 없음", ha="center", va="center", transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
        return
    if len(points) > 60000:
        points = points[np.random.default_rng(0).choice(len(points), 60000, replace=False)]
    color = points[:, 2] - np.nanmin(points[:, 2]) if color_by_z else "#2f6f8f"
    ax.scatter(points[:, 0], points[:, 1], c=color, cmap="viridis", s=0.8, linewidths=0)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


def draw_model(ax, roofs: list[np.ndarray], others: list[np.ndarray], title: str) -> None:
    ax.set_title(title, fontsize=9)
    if not roofs and not others:
        ax.text2D(0.5, 0.5, "조립 없음", ha="center", va="center", transform=ax.transAxes)
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
            Poly3DCollection([shifted(p) for p in others], facecolor="0.82", edgecolor="0.55", linewidths=0.2, alpha=0.35)
        )
    if roofs:
        colors = [plt.cm.tab20(i % 20) for i in range(len(roofs))]
        ax.add_collection3d(
            Poly3DCollection([shifted(p) for p in roofs], facecolor=colors, edgecolor="k", linewidths=0.35, alpha=0.95)
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
    ax.text2D(0.02, 0.93, f"roof {len(roofs)}", transform=ax.transAxes, fontsize=8)


def generation_figure(args: argparse.Namespace, bid: str, out: Path) -> None:
    rings = load_footprint_rings()
    base_pts = las_points(RAW_SPARSE_LAS, bid, rings, class_filter=6)
    gs_las = Path(args.gate_run_dir) / "roofer/gs_e5_C001_sparse_r1/run_1" / f"{bid}_run_1_classified.las"
    gs_pts = las_points(gs_las, bid, rings, class_filter=6)
    cityjson = Path(args.gate_run_dir) / "cityjson/gs_e5_C001_sparse_r1_run_1.city.json"
    roofs, others = cityjson_object_polys(cityjson, bid)
    fig = plt.figure(figsize=(12, 4.2))
    draw_cloud(fig.add_subplot(1, 3, 1), base_pts, f"{bid}\nraw-sparse 기준 점군")
    draw_cloud(fig.add_subplot(1, 3, 2), gs_pts, "GS-sparse-r1 점군")
    draw_model(fig.add_subplot(1, 3, 3, projection="3d"), roofs, others, "GS-sparse-r1 조립")
    fig.suptitle("생성 축 3연 대비: 기준선 점군 vs GS 점군 vs 조립 결과", fontsize=11)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)


def pick_quality_case(seed_rows: list[dict[str, Any]], repeat_rows: list[dict[str, str]]) -> tuple[str, str]:
    flips = [r for r in repeat_rows if r.get("repeat_flip") == "True"]
    if flips:
        return flips[0]["run_name"], flips[0]["building_id"]
    candidates = []
    for row in seed_rows:
        d = num(row.get("gs_r1_rmse_delta_vs_pair"))
        if d is not None:
            candidates.append((abs(d), row["gs_r1_run"], row["building_id"]))
    if candidates:
        _, run_name, bid = max(candidates)
        return run_name, bid
    return "gs_e5_C001_sparse_r1", "DEBY_LOD2_8568391"


def quality_figure(args: argparse.Namespace, run_name: str, bid: str, out: Path) -> None:
    repo = Path.cwd()
    footprints = base.load_footprints(FOOTPRINTS_GPKG, {bid})
    roofs_ref = base.load_roof_surfaces(LOD2_DIR, {bid}).get(bid, [])
    las_path = Path(args.gate_run_dir) / "roofer" / run_name / "run_1" / f"{bid}_run_1_classified.las"
    xyz, cls = base.read_las_footprint(las_path, footprints[bid]) if las_path.exists() else (np.empty((0, 3)), np.empty((0,)))
    roof_pts = xyz[cls == 6] if len(xyz) else np.empty((0, 3))
    zref, _miss = base.local_ref_z(roof_pts[:, 0], roof_pts[:, 1], roofs_ref, None) if len(roof_pts) else (None, 1.0)
    fig = plt.figure(figsize=(10, 4.5))
    ax0 = fig.add_subplot(1, 2, 1)
    ax0.set_title(f"{bid}\n거리-색칠 점군", fontsize=9)
    if len(roof_pts) and zref is not None:
        delta = roof_pts[:, 2] - zref
        sc = ax0.scatter(roof_pts[:, 0], roof_pts[:, 1], c=delta, cmap="coolwarm", vmin=-3, vmax=3, s=1.2, linewidths=0)
        fig.colorbar(sc, ax=ax0, shrink=0.8, label="z-GML roof m")
    else:
        ax0.text(0.5, 0.5, "점/참조 없음", ha="center", va="center", transform=ax0.transAxes)
    ax0.set_aspect("equal")
    ax0.set_xticks([])
    ax0.set_yticks([])
    cityjson = Path(args.gate_run_dir) / "cityjson" / f"{run_name}_run_1.city.json"
    roofs, others = cityjson_object_polys(cityjson, bid)
    draw_model(fig.add_subplot(1, 2, 2, projection="3d"), roofs, others, f"{run_name} per-facet 모델")
    fig.suptitle("품질 축 대비: 거리-색칠 점군 + 면 단위 모델", fontsize=11)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)
    _ = repo


def build_seed_pair_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    gate_rows = read_csv(Path(args.gate_run_dir) / "building_reconstruction_status.csv")
    gs = {(r["run_name"], r["roofer_repeat"], r["building_id"]): r for r in gate_rows}
    base_rows = read_csv(RAW_ACMP_STATUS) + read_csv(RAW_SPARSE_STATUS) + read_csv(W2_STATUS)
    base_by = status_lookup(base_rows)
    pair_lookup = {"sparse": "raw-sparse", "dense": "DIM", "acmp": "raw-ACMP"}
    pair_display = {"sparse": "raw-sparse", "dense": "raw-dense(w2_1 DIM)", "acmp": "raw-ACMP"}
    out = []
    for arm in ("sparse", "dense", "acmp"):
        base_label = pair_lookup[arm]
        for bid in C001_IDS:
            r1 = gs.get((f"gs_e5_C001_{arm}_r1", "run_1", bid), {})
            r2 = gs.get((f"gs_e5_C001_{arm}_r2", "run_1", bid), {})
            br = base_by.get((base_label, bid), {})
            b_rmse = num(br.get("rf_rmse_lod22"))
            g_rmse = num(r1.get("rf_rmse_lod22"))
            out.append(
                {
                    "arm": arm,
                    "building_id": bid,
                    "pair_baseline": pair_display[arm],
                    "pair_baseline_source_input": base_label,
                    "baseline_has_lod22": br.get("has_lod22", ""),
                    "baseline_reason": br.get("reason", ""),
                    "gs_r1_run": f"gs_e5_C001_{arm}_r1",
                    "gs_r1_has_lod22": r1.get("has_lod22", ""),
                    "gs_r1_valid": r1.get("val3dity_valid", ""),
                    "gs_r1_reason": r1.get("reason", ""),
                    "gs_r1_rmse_delta_vs_pair": "" if b_rmse is None or g_rmse is None else f"{g_rmse - b_rmse:.6f}",
                    "gs_r2_run": f"gs_e5_C001_{arm}_r2",
                    "gs_r2_has_lod22": r2.get("has_lod22", ""),
                    "gs_r2_valid": r2.get("val3dity_valid", ""),
                    "gs_r2_reason": r2.get("reason", ""),
                    "r1_r2_flip": str(r1.get("has_lod22", "") != r2.get("has_lod22", "")),
                }
            )
    return out


def build_summary_rows(seed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for arm in ("sparse", "dense", "acmp"):
        sub = [r for r in seed_rows if r["arm"] == arm]
        out.append(
            {
                "씨앗": arm,
                "짝 기준": sub[0]["pair_baseline"],
                "기준 has_lod22": f"{sum(tf(r['baseline_has_lod22']) for r in sub)}/18",
                "GS r1 has_lod22": f"{sum(tf(r['gs_r1_has_lod22']) for r in sub)}/18",
                "GS r2 has_lod22": f"{sum(tf(r['gs_r2_has_lod22']) for r in sub)}/18",
                "r1-r2 flip": sum(r["r1_r2_flip"] == "True" for r in sub),
                "r1 유효성 통과": f"{sum(tf(r['gs_r1_valid']) for r in sub)}/18",
                "r2 유효성 통과": f"{sum(tf(r['gs_r2_valid']) for r in sub)}/18",
            }
        )
    return out


def write_report(args: argparse.Namespace) -> None:
    train_fp = read_csv(Path(args.train_run_dir) / "train_fingerprints.csv")
    readout_fp = read_csv(Path(args.train_run_dir) / "readout_fingerprints.csv")
    repeat_rows = read_csv(Path(args.train_run_dir) / "repeat_flip_table.csv")
    seed_rows = build_seed_pair_rows(args)
    summary_rows = build_summary_rows(seed_rows)
    write_csv(Path("docs/experiments/e5_pilot/tables/e5_pilot_seed_pair_status.csv"), seed_rows)
    write_csv(Path("docs/experiments/e5_pilot/tables/e5_pilot_seed_pair_summary.csv"), summary_rows)

    q_run, q_bid = pick_quality_case(seed_rows, repeat_rows)
    gen_fig = Path(args.fig_dir) / "e5_generation_DEBY_LOD2_8568391.png"
    generation_figure(args, "DEBY_LOD2_8568391", gen_fig)
    qual_fig = Path(args.fig_dir) / f"e5_quality_{q_run}_{q_bid}.png"
    quality_figure(args, q_run, q_bid, qual_fig)

    checklist = []
    readout_by = {r["run_name"]: r for r in readout_fp}
    status_rows = read_csv(Path(args.gate_run_dir) / "building_reconstruction_status.csv")
    for fp in train_fp:
        name = fp["run_name"]
        sub = [r for r in status_rows if r["run_name"] == name and r["roofer_repeat"] == "run_1"]
        checklist.append(
            {
                "run": name,
                "학습": "완료" if fp.get("ckpt_sha256") and fp["ckpt_sha256"] != "missing" else "미완료",
                "점군화": "완료" if readout_by.get(name, {}).get("tsdf_sha256") not in {None, "", "missing"} else "미완료",
                "조립 run_1": "완료" if len(sub) == 18 else "미완료",
                "has_lod22 run_1": f"{sum(tf(r['has_lod22']) for r in sub)}/18" if sub else "",
            }
        )
    write_csv(Path("docs/experiments/e5_pilot/tables/e5_pilot_completion_checklist.csv"), checklist)

    flip_rows = [r for r in seed_rows if r["r1_r2_flip"] == "True"]
    repeat_flip_rows = [r for r in repeat_rows if r["repeat_flip"] == "True"]
    lines = [
        "# E5 파일럿 게이트 재료",
        "",
        "> 판정 금지. 이 문서는 표·그림·관찰만 기록한다. CRS는 EPSG:25832.",
        "",
        "## 고정 조건",
        "",
        "- 파일럿 블록: C001, 18동.",
        "- 학습 범위: C001 AOI + 20 m 버퍼로 자른 씨앗 점군·영상. 전체 장면 학습 없음.",
        "- 관측기하 기록: 선정 규칙에는 관측기하 조건이 없었고, 미학습 지역 전체가 관측 열세(최고 0.7)라는 판정 부속 사실을 기록한다.",
        f"- 점군화·라벨 방식(read-out): `{READOUT_STRING}`.",
        "- 생성 채점 범위: 씨앗별 짝 채점. GS-sparse vs raw-sparse, GS-dense vs raw-dense(w2_1 DIM), GS-acmp vs raw-ACMP. LiDAR는 완전측량 기준선 참고.",
        "- C001 기준선 성적(has_lod22): LiDAR 15/18, raw-ACMP 12/18, raw-dense(w2_1 DIM) 10/18, raw-sparse 2/18.",
        "- 성공 회계: `has_lod22`가 주, 유효성 통과는 참고. `no_points`는 조립기 문턱 기준과 클립 내 점 0 기준을 구분한다.",
        "",
        "## 완주 체크리스트",
        "",
        *md_table(checklist, ["run", "학습", "점군화", "조립 run_1", "has_lod22 run_1"]),
        "",
        "## 씨앗별 짝 채점 요약",
        "",
        *md_table(summary_rows, ["씨앗", "짝 기준", "기준 has_lod22", "GS r1 has_lod22", "GS r2 has_lod22", "r1-r2 flip", "r1 유효성 통과", "r2 유효성 통과"]),
        "",
        "## 재현 재료",
        "",
        f"- r1 vs r2 조립 성공 동 집합 flip: {len(flip_rows)}건.",
        f"- 조립 3회 내부 flip: {len(repeat_flip_rows)}건.",
        "- 전체 flip 목록: `docs/experiments/e5_pilot/tables/e5_pilot_seed_pair_status.csv`, `phases/p2-gsjso/runs/e5p_train_20260707_C001/repeat_flip_table.csv`.",
        "",
        "## 그림 쌍",
        "",
        f"- 생성 축: `{gen_fig}`.",
        f"- 품질 축: `{qual_fig}`. 대표 선정: 조립 3회 flip 우선, 없으면 `rf_rmse_lod22` 짝 델타 최대.",
        "",
        "## 런 지문",
        "",
        "- 학습 지문: `phases/p2-gsjso/runs/e5p_train_20260707_C001/train_fingerprints.csv`.",
        "- 점군화 지문: `phases/p2-gsjso/runs/e5p_train_20260707_C001/readout_fingerprints.csv`.",
        "- 조립 지문: `phases/p0-audit/runs/e5p_gate_20260707_C001/versions.txt`.",
        "- 속성 검산: `docs/experiments/pointcloud_attributes/tables/e5_pilot_pointcloud_attributes_v1_3_check.json`.",
        "",
        "## 관찰",
        "",
        "- C001은 미학습 지역이며 관측 열세(최고 0.7)가 함께 기록된 블록이다.",
        "- sparse 씨앗의 일부 동은 초기 씨앗점이 0개로 기록됐다. 이 항목은 생성 축 그림과 실패 목록에서 따로 확인한다.",
        "- 위 표와 그림은 게이트 판정 재료이며, 판정 문구는 쓰지 않는다.",
    ]
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"report": args.report, "figures": [str(gen_fig), str(qual_fig)]}, ensure_ascii=False))


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-run-dir", default="phases/p2-gsjso/runs/e5p_train_20260707_C001")
    parser.add_argument("--gate-run-dir", default="phases/p0-audit/runs/e5p_gate_20260707_C001")
    parser.add_argument("--fig-dir", default="docs/figs/e5_pilot")
    parser.add_argument("--report", default="docs/experiments/e5_pilot/reports/W_E5_pilot_gate.md")
    return parser


def main() -> None:
    configure_korean_font()
    write_report(build_argparser().parse_args())


if __name__ == "__main__":
    main()

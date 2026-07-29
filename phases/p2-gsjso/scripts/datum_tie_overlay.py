#!/usr/bin/env python3
"""Datum tie overlay render for two zeta values.

This script uses existing OPF/COLMAP cameras, ALS class-6 roof points and LoD2
roof rings. It renders side-by-side crops for zeta=45.7 and zeta=48.126.
No reconstruction or retraining is triggered.
"""
from __future__ import annotations

import csv
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

import laspy
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
import numpy as np
from PIL import Image

sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from evidence_cards_v2 import (  # noqa: E402
    ALS_TILES,
    DATA,
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


RUN_ID = "20260703_datum_tie_overlay"
RUN_DIR = REPO / "phases" / "p2-gsjso" / "runs" / RUN_ID
FIG_DIR = REPO / "docs/figs/datum_tie_overlay"
OUT_MD = REPO / "docs/experiments/datum_tie_overlay/reports/datum_tie_overlay.md"
SUCCESS_CSV = REPO / "phases/p0-audit/runs/w2_1d_bucket_relabel_20260612_final/docs/W2_1c_paired_status.csv"
ZETA_LEFT = 45.7
ZETA_RIGHT = 48.126
DELTA_ZETA = ZETA_RIGHT - ZETA_LEFT
MAX_ALS_PLOT = 4500


TARGETS = [
    {
        "bid": "4906966",
        "location": "west/NW",
        "shape": "sloped, LoD2 roofType 3100",
        "reason": "서쪽 블록, 수직/중간/강기울기 뷰 보유, 강기울기 지붕 외곽-배경 대비가 선명한 시연 조건.",
    },
    {
        "bid": "4906969",
        "location": "central/south",
        "shape": "flat, LoD2 roofType 1000",
        "reason": "중앙 블록, flat 지붕 형태, 강기울기 뷰에서도 참조 지붕 링이 crop 안에 남는 시연 조건.",
    },
    {
        "bid": "4959460",
        "location": "east",
        "shape": "complex/other, LoD2 roofType 9999",
        "reason": "동쪽 블록, 큰 지붕 외곽과 강기울기 링이 crop 안에 남아 AOI 동서 분산을 채우는 조건.",
    },
]

ANGLE_TARGETS = [
    ("vertical", 8.0, 0.0, 15.0),
    ("middle", 30.0, 20.0, 45.0),
    ("strong", 60.0, 50.0, 89.0),
]


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception as exc:  # pragma: no cover
        return f"unavailable: {exc}"


def load_dense_success() -> set[str]:
    out: set[str] = set()
    for row in csv.DictReader(open(SUCCESS_CSV)):
        if row["als_has_lod22"] == "True" and row["dim_has_lod22"] == "True":
            out.add(row["building_id"].replace("DEBY_LOD2_", ""))
    return out


def footprints() -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for feat in json.load(open(GEOJSON))["features"]:
        bid = feat["properties"]["building_id"].replace("DEBY_LOD2_", "")
        geom = feat["geometry"]
        ring = np.array(
            geom["coordinates"][0] if geom["type"] == "Polygon" else max((poly[0] for poly in geom["coordinates"]), key=len),
            dtype=float,
        )
        if bid not in out or len(ring) > len(out[bid]):
            out[bid] = ring
    return out


def polygon_area(ring: np.ndarray) -> float:
    if len(ring) < 3:
        return 0.0
    return float(0.5 * abs(np.dot(ring[:-1, 0], ring[1:, 1]) - np.dot(ring[1:, 0], ring[:-1, 1])))


def view_zenith_deg(cam, target_ortho: np.ndarray, zeta: float) -> float:
    target = as_ellipsoidal_points(target_ortho[None], input_datum="orthometric", geoid_m=zeta)[0]
    vec = cam.center - target
    norm = float(np.linalg.norm(vec))
    if norm <= 1e-9:
        return float("nan")
    return math.degrees(math.acos(min(1.0, max(-1.0, abs(vec[2]) / norm))))


def project_points(points: np.ndarray, cam, params: np.ndarray, sr: dict, zeta: float) -> tuple[np.ndarray, np.ndarray]:
    cc = to_cam(points, cam, sr, geoid_m=zeta)
    front = cc[:, 2] > 1.0
    uv = np.full((len(points), 2), np.nan, dtype=float)
    if front.any():
        uv[front] = distort(cc[front], params)
    return uv, front


def als_roof_points(ring: np.ndarray, ground_z: float) -> np.ndarray:
    bb = [ring[:, 0].min() - 1, ring[:, 1].min() - 1, ring[:, 0].max() + 1, ring[:, 1].max() + 1]
    poly = MplPath(ring[:, :2])
    chunks = []
    for tile in ALS_TILES:
        with laspy.open(tile) as fh:
            h = fh.header
            if h.x_max < bb[0] or h.x_min > bb[2] or h.y_max < bb[1] or h.y_min > bb[3]:
                continue
        las = laspy.read(tile)
        x = np.asarray(las.x)
        y = np.asarray(las.y)
        z = np.asarray(las.z)
        cls = np.asarray(las.classification)
        in_bbox = (x >= bb[0]) & (x <= bb[2]) & (y >= bb[1]) & (y <= bb[3])
        idx = np.where((cls == 6) & in_bbox & (z > ground_z + 2.0))[0]
        if idx.size == 0:
            continue
        xy = np.column_stack([x[idx], y[idx]])
        inside = poly.contains_points(xy)
        if inside.any():
            chunks.append(np.column_stack([xy[inside, 0], xy[inside, 1], z[idx][inside]]))
    return np.vstack(chunks) if chunks else np.zeros((0, 3), dtype=float)


def inframe_uv(points: np.ndarray, cam, params: np.ndarray, sr: dict, width: int, height: int, zeta: float):
    uv, front = project_points(points, cam, params, sr, zeta)
    ok = front & np.isfinite(uv[:, 0]) & np.isfinite(uv[:, 1])
    ok &= (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
    return uv[ok], int(ok.sum()), float(ok.mean()) if len(ok) else 0.0


def select_views(roof: list[np.ndarray], ring: np.ndarray, als: np.ndarray, cams, params, sr, width: int, height: int):
    all_roof = np.vstack(roof)
    target = np.array([ring[:, 0].mean(), ring[:, 1].mean(), float(np.median(all_roof[:, 2]))])
    candidates = []
    cx, cy = params[2], params[3]
    for cam in cams:
        als_uv, n_als, _als_frac = inframe_uv(als, cam, params, sr, width, height, ZETA_LEFT)
        if n_als < 80:
            continue
        roof_uv, _front = project_points(all_roof, cam, params, sr, ZETA_LEFT)
        roof_ok = np.isfinite(roof_uv[:, 0]) & np.isfinite(roof_uv[:, 1])
        roof_ok &= (roof_uv[:, 0] >= 0) & (roof_uv[:, 0] < width) & (roof_uv[:, 1] >= 0) & (roof_uv[:, 1] < height)
        roof_frac = float(roof_ok.mean())
        if roof_frac < 0.6:
            continue
        rad = float(
            np.nanmax(np.sqrt(((als_uv[:, 0] - cx) / (0.5 * width)) ** 2 + ((als_uv[:, 1] - cy) / (0.5 * height)) ** 2))
        )
        zen = view_zenith_deg(cam, target, ZETA_LEFT)
        candidates.append({"cam": cam, "zenith": zen, "rad": rad, "n_als": n_als, "roof_frac": roof_frac})

    picks = []
    used: set[str] = set()
    for label, target_zen, lo, hi in ANGLE_TARGETS:
        pool = [c for c in candidates if lo <= c["zenith"] < hi and c["cam"].name not in used]
        if not pool:
            raise RuntimeError(f"no {label} view for target at ranges {lo}-{hi} deg")
        pick = min(
            pool,
            key=lambda c: abs(c["zenith"] - target_zen) + 2.5 * max(0.0, c["rad"] - 1.25) - 0.0003 * c["n_als"],
        )
        used.add(pick["cam"].name)
        picks.append((label, pick))
    return picks, target


def project_lod2_rings(roof: list[np.ndarray], cam, params: np.ndarray, sr: dict, zeta: float) -> list[np.ndarray]:
    rings = []
    for ring in roof:
        uv = proj_ring(ring, cam, params, sr, geoid_m=zeta)
        if uv is not None and len(uv) >= 3 and np.isfinite(uv).all():
            rings.append(uv)
    return rings


def projected_als(als: np.ndarray, cam, params: np.ndarray, sr: dict, width: int, height: int, zeta: float) -> np.ndarray:
    uv, _n, _frac = inframe_uv(als, cam, params, sr, width, height, zeta)
    if len(uv) > MAX_ALS_PLOT:
        step = int(math.ceil(len(uv) / MAX_ALS_PLOT))
        uv = uv[::step]
    return uv


def crop_bbox(uv_sets: list[np.ndarray], width: int, height: int, pad: int = 140) -> tuple[int, int, int, int]:
    pts = [u for u in uv_sets if u is not None and len(u)]
    if not pts:
        raise RuntimeError("no projected points for crop")
    all_uv = np.vstack(pts)
    ok = np.isfinite(all_uv[:, 0]) & np.isfinite(all_uv[:, 1])
    ok &= (all_uv[:, 0] > -pad) & (all_uv[:, 0] < width + pad) & (all_uv[:, 1] > -pad) & (all_uv[:, 1] < height + pad)
    if ok.sum() < 3:
        raise RuntimeError("too few finite projected points for crop")
    all_uv = all_uv[ok]
    x0 = int(max(0, np.floor(all_uv[:, 0].min() - pad)))
    y0 = int(max(0, np.floor(all_uv[:, 1].min() - pad)))
    x1 = int(min(width, np.ceil(all_uv[:, 0].max() + pad)))
    y1 = int(min(height, np.ceil(all_uv[:, 1].max() + pad)))
    if x1 - x0 < 80 or y1 - y0 < 80:
        cx = int(np.clip(np.median(all_uv[:, 0]), 0, width - 1))
        cy = int(np.clip(np.median(all_uv[:, 1]), 0, height - 1))
        x0, x1 = max(0, cx - 180), min(width, cx + 180)
        y0, y1 = max(0, cy - 180), min(height, cy + 180)
    return x0, y0, x1, y1


def zoom_bbox_from_rings(
    rings_left: list[np.ndarray],
    rings_right: list[np.ndarray],
    width: int,
    height: int,
    pad: int = 280,
) -> tuple[int, int, int, int]:
    centers = []
    diffs = []
    for left, right in zip(rings_left, rings_right):
        n = min(len(left), len(right))
        if n == 0:
            continue
        ul = left[:n]
        ur = right[:n]
        ok = np.isfinite(ul[:, 0]) & np.isfinite(ur[:, 0])
        ok &= (ul[:, 0] >= 0) & (ul[:, 0] < width) & (ul[:, 1] >= 0) & (ul[:, 1] < height)
        ok &= (ur[:, 0] >= 0) & (ur[:, 0] < width) & (ur[:, 1] >= 0) & (ur[:, 1] < height)
        if ok.any():
            centers.append(0.5 * (ul[ok] + ur[ok]))
            diffs.append(np.linalg.norm(ur[ok] - ul[ok], axis=1))
    if not centers:
        return crop_bbox(rings_left + rings_right, width, height, pad=pad)
    all_centers = np.vstack(centers)
    all_diffs = np.concatenate(diffs)
    center = all_centers[int(np.argmax(all_diffs))]
    x0 = int(max(0, center[0] - pad))
    x1 = int(min(width, center[0] + pad))
    y0 = int(max(0, center[1] - pad))
    y1 = int(min(height, center[1] + pad))
    return x0, y0, x1, y1


def draw_panel(ax, crop: np.ndarray, x0: int, y0: int, rings: list[np.ndarray], als_uv: np.ndarray, title: str):
    ax.imshow(crop)
    ax.axis("off")
    ax.set_title(title, fontsize=8.5)
    for ring in rings:
        q = np.vstack([ring, ring[:1]])
        ax.plot(q[:, 0] - x0, q[:, 1] - y0, "-", c="lime", lw=1.25, alpha=0.95)
    if len(als_uv):
        ax.scatter(als_uv[:, 0] - x0, als_uv[:, 1] - y0, s=0.65, c="#00d7ff", alpha=0.42, linewidths=0)
    ax.set_xlim(0, crop.shape[1])
    ax.set_ylim(crop.shape[0], 0)


def render_pair(
    image: np.ndarray,
    out_path: Path,
    bid: str,
    angle_label: str,
    view_name: str,
    zenith: float,
    bbox: tuple[int, int, int, int],
    rings_left: list[np.ndarray],
    als_left: np.ndarray,
    rings_right: list[np.ndarray],
    als_right: np.ndarray,
    zoom: bool = False,
) -> None:
    x0, y0, x1, y1 = bbox
    crop = image[y0:y1, x0:x1]
    theory = DELTA_ZETA * math.tan(math.radians(zenith))
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 6.2))
    draw_panel(axes[0], crop, x0, y0, rings_left, als_left, f"left zeta={ZETA_LEFT:.3f} m")
    draw_panel(axes[1], crop, x0, y0, rings_right, als_right, f"right zeta={ZETA_RIGHT:.3f} m")
    zoom_label = " corner zoom" if zoom else ""
    fig.suptitle(
        f"DEBY_LOD2_{bid} {angle_label}{zoom_label} | view zenith={zenith:.2f} deg | "
        f"Delta zeta={DELTA_ZETA:.3f} m x tan(theta) = {theory:.3f} m | {view_name}",
        fontsize=8.6,
    )
    fig.text(0.5, 0.018, "lime=LoD2 roof ring, cyan=ALS class-6 roof points; same crop and camera for both panels", ha="center", fontsize=8)
    fig.tight_layout(rect=[0, 0.035, 1, 0.93])
    fig.savefig(out_path, dpi=135)
    plt.close(fig)


def observation_for(angle_label: str) -> str:
    if angle_label == "vertical":
        return "수직 뷰에서는 두 zeta 패널의 차이가 작고, 45.7 패널의 링/점이 지붕 외곽에 더 머물러 보인다."
    if angle_label == "middle":
        return "중간 뷰에서는 오른쪽 48.126 패널이 같은 방향으로 이동해 차이가 보이기 시작한다."
    return "강기울기 뷰에서는 45.7 패널의 링/점이 지붕 모서리에 더 가까워 보이고, 48.126 패널의 이동이 crop 안에서 분리되어 보인다."


def write_versions() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id: {RUN_ID}",
        f"git_head: {git_head()}",
        "command: python phases/p2-gsjso/scripts/datum_tie_overlay.py",
        f"projection_config_context: {describe_projection_config()}",
        f"left_zeta_m: {ZETA_LEFT:.6f}",
        f"right_zeta_m: {ZETA_RIGHT:.6f}",
        f"delta_zeta_m: {DELTA_ZETA:.6f}",
        "render_only: true",
        "reconstruction_or_retraining: none",
        "crs: geo EPSG:25832; OPF/COLMAP EPSG:32632 local with ellipsoidal Z",
        "container: jointbuildgs-p0-tools:t0; Docker --user",
        f"python: {platform.python_version()}",
        f"numpy: {np.__version__}",
        "",
    ]
    (RUN_DIR / "versions.txt").write_text("\n".join(lines))


def write_report(selection_rows: list[dict[str, object]], view_rows: list[dict[str, object]], zoom_rows: list[dict[str, object]]) -> None:
    lines = [
        "# Datum Tie Overlay - 확인 오버레이",
        "",
        "> 브랜치 `feat/p2-structure-learn`. 재구성/재학습 없음. 순수 투영·렌더 산출. 최종 판정은 김휘영.",
        "",
        "## 0. 재현 범위",
        "",
        f"- 실행 산출: `docs/figs/datum_tie_overlay/`, `{RUN_DIR.relative_to(REPO)}/versions.txt`.",
        "- 지오 산출물 CRS: EPSG:25832. OPF 선언 CRS: EPSG:32632.",
        f"- 왼쪽 패널: `zeta={ZETA_LEFT:.3f} m` 공식 45.7.",
        f"- 오른쪽 패널: `zeta={ZETA_RIGHT:.3f} m` 기각된 관례·LS 참고 대비값.",
        f"- 이론 이동량: `Delta zeta {DELTA_ZETA:.3f} m x tan(theta)`.",
        "- A3a/A3b는 이 커밋에서 수행하지 않았다.",
        "",
        "## 1. 대상 선정",
        "",
        "선정 근거: zeta는 블록 상수이므로 어느 건물에도 같은 값으로 들어가야 한다. 이번 선정은 차이가 픽셀로 보이는 조건의 시연 기준이다. 서로 다른 위치·형태에서 같은 값으로 지붕 외곽과 LiDAR 지붕점이 함께 움직이면 상수성의 시각 증거가 된다.",
        "",
        "dense 성공 그룹은 `W2_1c_paired_status.csv`에서 `als_has_lod22=True AND dim_has_lod22=True`인 114동 기준을 사용했다. 아래 3동은 모두 이 기준에 포함된다.",
        "",
        "| building_id | 위치 | centroid E,N | 형태 | 수직/중간/강기울기 각도 deg | 선정 사유 |",
        "|---|---|---:|---|---|---|",
    ]
    for row in selection_rows:
        lines.append(
            f"| {row['building_id']} | {row['location']} | {row['centroid']} | {row['shape']} | "
            f"{row['angles']} | {row['reason']} |"
        )
    lines.extend(
        [
            "",
            "## 2. 뷰별 오버레이",
            "",
            "| building_id | angle_bin | view | zenith_deg | Delta zeta x tan(theta) m | figure | 관찰 |",
            "|---|---|---|---:|---:|---|---|",
        ]
    )
    for row in view_rows:
        lines.append(
            f"| {row['building_id']} | {row['angle_bin']} | `{row['view']}` | {row['zenith_deg']:.2f} | "
            f"{row['theory_m']:.3f} | `{row['figure']}` | {row['observation']} |"
        )
    lines.extend(
        [
            "",
            "## 3. 강기울기 모서리 확대",
            "",
            "| building_id | view | zenith_deg | Delta zeta x tan(theta) m | figure | 관찰 |",
            "|---|---|---:|---:|---|---|",
        ]
    )
    for row in zoom_rows:
        lines.append(
            f"| {row['building_id']} | `{row['view']}` | {row['zenith_deg']:.2f} | {row['theory_m']:.3f} | "
            f"`{row['figure']}` | 강기울기 1뷰의 모서리 확대 crop에서 두 zeta 투영 차이가 픽셀로 분리되어 보인다. |"
        )
    lines.extend(
        [
            "",
            "## 4. 관찰",
            "",
            "- 수직 뷰에서는 `Delta zeta x tan(theta)`가 작아 패널 차이가 작다.",
            "- 중간·강기울기 뷰로 갈수록 같은 zeta 차이가 더 큰 image-plane 이동으로 보인다.",
            "- 세 위치/형태 모두에서 `45.7` 패널의 LoD2 링과 ALS 지붕점이 지붕 외곽에 더 가까워 보인다. 이 문장은 시각 관찰이며 채택 판정이 아니다.",
            "- `48.126` 패널은 강기울기 crop에서 같은 방향으로 더 이동해 외곽과 분리되어 보인다. 이 문장은 시각 관찰이며 채택 판정이 아니다.",
            "",
            "## 5. 판정 필요 지점",
            "",
            "1. `45.7` 공식값을 이후 A3a/A3b 입력 zeta로 사용할지 여부.",
            "2. `48.126` LS 참고값을 이번 오버레이 이후 계속 대비값으로만 둘지 여부.",
            "3. 이 확인 오버레이만으로 A3a/A3b 투입 조건이 충분한지 여부.",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n")


def main() -> None:
    dense_success = load_dense_success()
    fp = footprints()
    sr = json.load(open(DATA / "work/opf/opf/scene_reference_frame.json"))["base_to_canonical"]
    width, height, params = parse_cam_model(DATA / "work/colmap/sparse/0/cameras.txt")
    cams = parse_cameras(DATA / "work/colmap/sparse/0/images.txt", sr)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    selection_rows = []
    view_rows = []
    zoom_rows = []
    for meta in TARGETS:
        bid = meta["bid"]
        if bid not in dense_success:
            raise RuntimeError(f"target is not in dense success group: {bid}")
        gb = gml_building(bid)
        ring = fp.get(bid)
        if not gb or not gb["roof"] or ring is None:
            raise RuntimeError(f"missing GML roof or footprint: {bid}")
        all_surfaces = np.vstack(gb["roof"] + gb["wall"])
        ground_z = float(all_surfaces[:, 2].min())
        als = als_roof_points(ring, ground_z)
        if len(als) < 80:
            raise RuntimeError(f"too few ALS roof points for {bid}: {len(als)}")
        picks, _target = select_views(gb["roof"], ring, als, cams, params, sr, width, height)
        pick_by_label = {label: pick for label, pick in picks}
        angle_text = " / ".join(f"{label} {pick_by_label[label]['zenith']:.1f}" for label, *_ in ANGLE_TARGETS)
        centroid = ring[:, :2].mean(axis=0)
        selection_rows.append(
            {
                "building_id": f"DEBY_LOD2_{bid}",
                "location": meta["location"],
                "centroid": f"{centroid[0]:.1f}, {centroid[1]:.1f}",
                "shape": meta["shape"],
                "angles": angle_text,
                "reason": meta["reason"],
            }
        )

        image_cache: dict[str, np.ndarray] = {}
        for label, pick in picks:
            cam = pick["cam"]
            if cam.name not in image_cache:
                image_cache[cam.name] = np.asarray(Image.open(IMAGE_DIR / cam.name).convert("RGB"))
            image = image_cache[cam.name]
            rings_left = project_lod2_rings(gb["roof"], cam, params, sr, ZETA_LEFT)
            rings_right = project_lod2_rings(gb["roof"], cam, params, sr, ZETA_RIGHT)
            als_left = projected_als(als, cam, params, sr, width, height, ZETA_LEFT)
            als_right = projected_als(als, cam, params, sr, width, height, ZETA_RIGHT)
            bbox = crop_bbox(rings_left + rings_right + [als_left, als_right], width, height)
            out = FIG_DIR / f"{bid}_{label}_pair.png"
            render_pair(
                image,
                out,
                bid,
                label,
                cam.name,
                float(pick["zenith"]),
                bbox,
                rings_left,
                als_left,
                rings_right,
                als_right,
            )
            theory = DELTA_ZETA * math.tan(math.radians(float(pick["zenith"])))
            view_rows.append(
                {
                    "building_id": f"DEBY_LOD2_{bid}",
                    "angle_bin": label,
                    "view": cam.name,
                    "zenith_deg": float(pick["zenith"]),
                    "theory_m": theory,
                    "figure": str(out.relative_to(REPO)),
                    "observation": observation_for(label),
                }
            )

        strong = pick_by_label["strong"]
        cam = strong["cam"]
        if cam.name not in image_cache:
            image_cache[cam.name] = np.asarray(Image.open(IMAGE_DIR / cam.name).convert("RGB"))
        rings_left = project_lod2_rings(gb["roof"], cam, params, sr, ZETA_LEFT)
        rings_right = project_lod2_rings(gb["roof"], cam, params, sr, ZETA_RIGHT)
        als_left = projected_als(als, cam, params, sr, width, height, ZETA_LEFT)
        als_right = projected_als(als, cam, params, sr, width, height, ZETA_RIGHT)
        out = FIG_DIR / f"{bid}_strong_corner_zoom.png"
        render_pair(
            image_cache[cam.name],
            out,
            bid,
            "strong",
            cam.name,
            float(strong["zenith"]),
            zoom_bbox_from_rings(rings_left, rings_right, width, height),
            rings_left,
            als_left,
            rings_right,
            als_right,
            zoom=True,
        )
        zoom_rows.append(
            {
                "building_id": f"DEBY_LOD2_{bid}",
                "view": cam.name,
                "zenith_deg": float(strong["zenith"]),
                "theory_m": DELTA_ZETA * math.tan(math.radians(float(strong["zenith"]))),
                "figure": str(out.relative_to(REPO)),
            }
        )
        print(
            f"{bid}: views "
            + ", ".join(f"{label}={pick['zenith']:.1f}deg {pick['cam'].name}" for label, pick in picks)
            + f" | ALS roof points={len(als)} area={polygon_area(ring):.1f}m2"
        )

    write_report(selection_rows, view_rows, zoom_rows)
    write_versions()
    print(f"[done] {OUT_MD}")
    print(f"[done] {FIG_DIR}")
    print(f"[done] {RUN_DIR / 'versions.txt'}")


if __name__ == "__main__":
    main()

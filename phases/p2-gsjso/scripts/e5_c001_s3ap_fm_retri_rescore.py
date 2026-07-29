#!/usr/bin/env python3
"""Learning-zero cached-DLT recognition QA and roof-plane rescore.

Wave 1 projects the actual LoD2 RoofSurface geometry and GroundSurface
footprint with the fixed COLMAP cameras.  Wave 2 (implemented below the Wave 1
entrypoint) only reads the cached post-cheirality/post-2px DLT survivors; it
never imports MASt3R and never starts inference or training.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np
from lxml import etree
from PIL import Image
from shapely import make_valid
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon, box, shape
from shapely.ops import unary_union

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402
from shapely import contains_xy
from shapely.geometry import MultiPoint
from sklearn.linear_model import LinearRegression, RANSACRegressor

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in os.sys.path:
    os.sys.path.insert(0, str(REPO))
from src.stage2.colmap_io import read_cameras_bin, read_images_bin, read_points3d_bin  # noqa: E402

RUN_ID = "20260715_e5_c001_s3ap_fm_retri_rescore"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
CONFIG = REPO / "phases/p2-gsjso/configs/e5_c001_s3ap_fm_retri_rescore.json"
OLD_RUN = REPO / "phases/p2-gsjso/runs/20260714_e5_c001_s3ap_fm_retriangulation"
OLD_MANIFEST = OLD_RUN / "manifest.json"
PAIR_DIR = OLD_RUN / "pairs"
TRAIN_MANIFEST = REPO / "results/tum_transfer/e5_pilot/C001/C001_train_prep_manifest.json"
DATA_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"
SPARSE_DIR = DATA_ROOT / "sparse/0"
IMAGE_DIR = DATA_ROOT / "images"
FOOTPRINTS = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
LOD2_DIR = REPO / "phases/p0-audit/data/raw/lod2"
PROJECTION_DATUM = REPO / "configs/projection_datum.json"
REG_CSV = REPO / "docs/experiments/e5_c001_s3ap/tables/e5_c001_s3ap_fm_retri_registration.csv"
OUT_CSV = REPO / "docs/experiments/e5_c001_s3ap/tables/e5_c001_s3ap_fm_retri_rescore.csv"
REPORT = REPO / "docs/experiments/e5_c001_s3ap/reports/W_E5_C001_S3Ap_FM재채점_20260715.md"
FIG_DIR = REPO / "docs/figs/e5_c001_s3ap_fm_retri_rescore"
REG_MANIFEST = RUN_DIR / "registration_manifest.json"
MANIFEST = RUN_DIR / "manifest.json"
PROGRESS = RUN_DIR / "progress.json"
RUN_LOG = RUN_DIR / "run.log"
DENSE_POINTS = REPO / "results/tum_transfer/e5_pilot/C001/seeds/seed_dense_C001_buf20.ply"
SPARSE_POINTS = SPARSE_DIR / "points3D.bin"

TARGETS = ["4907199", "8568391", "8568392"]
CLASS_LABEL = {
    "seated": "앉음",
    "ambiguous": "애매",
    "misregistered": "어긋남",
    "pending": "미검토",
}


@dataclass
class Surface:
    surface_id: str
    kind: str
    rings: list[np.ndarray]
    polygon: Polygon | MultiPolygon
    x0: float
    y0: float
    z0: float
    ax: float
    by: float

    def z_at(self, x: np.ndarray | float, y: np.ndarray | float) -> np.ndarray:
        return self.z0 + self.ax * (np.asarray(x) - self.x0) + self.by * (np.asarray(y) - self.y0)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_font() -> None:
    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["axes.unicode_minus"] = False


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block_data in iter(lambda: handle.read(block_size), b""):
            digest.update(block_data)
    return digest.hexdigest()


def git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def log(message: str) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{now()} {message}"
    with RUN_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(line, flush=True)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(value, encoding="utf-8")
    os.replace(tmp, path)


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (float, np.floating)):
        return "" if not math.isfinite(float(value)) else f"{float(value):.6f}"
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    return str(value)


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: fmt(row.get(key)) for key in fields} for row in rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def gml_id(elem: etree._Element) -> str:
    for key, value in elem.attrib.items():
        if local_name(key) == "id":
            return str(value)
    return ""


def parse_poslist(text: str) -> np.ndarray:
    values = np.asarray([float(value) for value in text.split()], dtype=np.float64)
    if values.size % 3:
        raise RuntimeError("GML posList is not XYZ")
    return values.reshape(-1, 3)


def first_ring(elem: etree._Element) -> np.ndarray | None:
    for child in elem.iter():
        if local_name(child.tag) == "posList" and child.text:
            return parse_poslist(child.text)
    return None


def polygon_rings(elem: etree._Element) -> list[np.ndarray]:
    exterior: np.ndarray | None = None
    holes: list[np.ndarray] = []
    for child in elem:
        if local_name(child.tag) == "exterior":
            exterior = first_ring(child)
        elif local_name(child.tag) == "interior":
            ring = first_ring(child)
            if ring is not None:
                holes.append(ring)
    if exterior is None:
        rings = [parse_poslist(child.text) for child in elem.iter() if local_name(child.tag) == "posList" and child.text]
        return rings[:1]
    return [exterior, *holes]


def flatten_polygons(geom: Any) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        out: list[Polygon] = []
        for part in geom.geoms:
            out.extend(flatten_polygons(part))
        return out
    return []


def make_surface(surface_id: str, kind: str, rings: list[np.ndarray]) -> Surface | None:
    if not rings or len(rings[0]) < 3:
        return None
    normalized: list[np.ndarray] = []
    for ring in rings:
        arr = np.asarray(ring, dtype=np.float64)
        if not np.allclose(arr[0], arr[-1]):
            arr = np.vstack([arr, arr[0]])
        normalized.append(arr)
    polygon = make_valid(Polygon(normalized[0][:, :2], [ring[:, :2] for ring in normalized[1:]]))
    parts = [part for part in flatten_polygons(polygon) if part.area > 0.01]
    if not parts:
        return None
    polygon = parts[0] if len(parts) == 1 else MultiPolygon(parts)
    points = normalized[0][:-1]
    x0, y0, z0 = np.mean(points, axis=0)
    design = np.column_stack([points[:, 0] - x0, points[:, 1] - y0, np.ones(len(points))])
    ax, by, centre = np.linalg.lstsq(design, points[:, 2], rcond=None)[0]
    return Surface(surface_id, kind, normalized, polygon, float(x0), float(y0), float(centre), float(ax), float(by))


def load_lod2() -> dict[str, dict[str, list[Surface]]]:
    wanted = {f"DEBY_LOD2_{short}" for short in TARGETS}
    out = {short: {"RoofSurface": [], "GroundSurface": []} for short in TARGETS}
    for path in sorted(LOD2_DIR.glob("*.gml")):
        for _event, elem in etree.iterparse(str(path), events=("end",), recover=True):
            if local_name(elem.tag) != "Building":
                continue
            bid = gml_id(elem)
            if bid in wanted:
                short = bid.removeprefix("DEBY_LOD2_")
                for kind in ["RoofSurface", "GroundSurface"]:
                    index = 0
                    for surface_elem in elem.iter():
                        if local_name(surface_elem.tag) != kind:
                            continue
                        for polygon_elem in surface_elem.iter():
                            if local_name(polygon_elem.tag) != "Polygon":
                                continue
                            index += 1
                            surface = make_surface(f"{bid}_{kind}_{index}", kind, polygon_rings(polygon_elem))
                            if surface is not None:
                                out[short][kind].append(surface)
            elem.clear()
            parent = elem.getparent()
            if parent is not None:
                while elem.getprevious() is not None:
                    del parent[0]
    for short in TARGETS:
        if not out[short]["RoofSurface"]:
            raise RuntimeError(f"missing LoD2 RoofSurface: {short}")
    return out


def load_all_footprints() -> dict[str, Polygon | MultiPolygon]:
    payload = json.loads(FOOTPRINTS.read_text(encoding="utf-8"))
    crs = str(payload.get("crs", {}).get("properties", {}).get("name", ""))
    if "25832" not in crs:
        raise RuntimeError(f"footprint CRS mismatch: {crs}")
    pieces: dict[str, list[Any]] = {}
    for feature in payload["features"]:
        bid = str((feature.get("properties") or {}).get("building_id", ""))
        geom = make_valid(shape(feature["geometry"]))
        if bid and not geom.is_empty:
            pieces.setdefault(bid, []).append(geom)
    return {bid: make_valid(unary_union(geoms)) for bid, geoms in pieces.items()}


def load_frames() -> dict[str, dict[str, Any]]:
    cameras = read_cameras_bin(SPARSE_DIR / "cameras.bin")
    images = read_images_bin(SPARSE_DIR / "images.bin")
    out: dict[str, dict[str, Any]] = {}
    for item in images.values():
        path = IMAGE_DIR / item.name
        if not path.exists():
            continue
        camera = cameras[item.camera_id]
        out[Path(item.name).stem] = {
            "path": path,
            "name": item.name,
            "K": camera.K(),
            "R": item.R(),
            "t": np.asarray(item.tvec, dtype=np.float64),
            "width": int(camera.width),
            "height": int(camera.height),
        }
    return out


def project(local_xyz: np.ndarray, frame: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    camera = (frame["R"] @ np.asarray(local_xyz, dtype=np.float64).T).T + frame["t"]
    homogeneous = (frame["K"] @ camera.T).T
    pixels = np.full((len(camera), 2), np.nan, dtype=np.float64)
    positive = camera[:, 2] > 1e-9
    pixels[positive] = homogeneous[positive, :2] / homogeneous[positive, 2:3]
    return pixels, camera[:, 2]


def local_ring(surface: Surface, ring: np.ndarray, offset: np.ndarray, geoid: float) -> np.ndarray:
    ring = np.asarray(ring, dtype=np.float64)
    return np.column_stack([
        ring[:, 0] - offset[0],
        ring[:, 1] - offset[1],
        ring[:, 2] + geoid - offset[2],
    ])


def projected_rings(surface: Surface, frame: dict[str, Any], offset: np.ndarray, geoid: float) -> list[np.ndarray]:
    out: list[np.ndarray] = []
    for ring in surface.rings:
        pixels, depth = project(local_ring(surface, ring, offset, geoid), frame)
        if np.all(depth > 0) and np.isfinite(pixels).all():
            out.append(pixels)
    return out


def union_projected_roofs(surfaces: Sequence[Surface], frame: dict[str, Any], offset: np.ndarray, geoid: float) -> Any:
    polygons: list[Polygon] = []
    for surface in surfaces:
        rings = projected_rings(surface, frame, offset, geoid)
        if not rings:
            continue
        poly = make_valid(Polygon(rings[0], rings[1:]))
        polygons.extend(flatten_polygons(poly))
    return make_valid(unary_union(polygons)) if polygons else Polygon()


def boundary_fraction(geom: Any, frame_rect: Polygon) -> float:
    boundary = geom.boundary
    total = float(boundary.length)
    return float(boundary.intersection(frame_rect).length / total) if total > 0 else 0.0


def figure_crop(geom: Any, width: int, height: int) -> tuple[float, float, float, float]:
    if geom.is_empty:
        return 0.0, float(width), float(height), 0.0
    minx, miny, maxx, maxy = geom.bounds
    visible_x = min(max((minx + maxx) / 2, 0), width)
    visible_y = min(max((miny + maxy) / 2, 0), height)
    extent = max(maxx - minx, maxy - miny, 220.0)
    half = min(max(extent * 1.45, 260.0), max(width, height) * 0.55) / 2
    x0, x1 = max(0.0, visible_x - half), min(float(width), visible_x + half)
    y0, y1 = max(0.0, visible_y - half), min(float(height), visible_y + half)
    if x1 - x0 < 200:
        x0, x1 = max(0.0, x1 - 200), min(float(width), x0 + 200)
    if y1 - y0 < 200:
        y0, y1 = max(0.0, y1 - 200), min(float(height), y0 + 200)
    return x0, x1, y1, y0


def draw_reference(ax: Any, roof_surfaces: Sequence[Surface], ground_surfaces: Sequence[Surface], frame: dict[str, Any], offset: np.ndarray, geoid: float) -> None:
    first_roof = True
    first_ground = True
    for surface in roof_surfaces:
        rings = projected_rings(surface, frame, offset, geoid)
        if not rings:
            continue
        outer = rings[0]
        ax.add_patch(MplPolygon(outer, closed=True, facecolor="#00bcd4", edgecolor="#002b36", alpha=0.24, linewidth=1.0))
        for ring in rings:
            ax.plot(ring[:, 0], ring[:, 1], color="#00ffff", linewidth=2.0, label="actual LoD2 RoofSurface" if first_roof else None)
            first_roof = False
    for surface in ground_surfaces:
        for ring in projected_rings(surface, frame, offset, geoid):
            ax.plot(ring[:, 0], ring[:, 1], color="#ffd166", linestyle="--", linewidth=1.5, label="LoD2 footprint @ GroundSurface" if first_ground else None)
            first_ground = False


def make_registration_figure(short: str, stem: str, frame: dict[str, Any], roof: Sequence[Surface], ground: Sequence[Surface], offset: np.ndarray, geoid: float, row: dict[str, Any]) -> Path:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    rgb = np.asarray(Image.open(frame["path"]).convert("RGB"))
    roof_geom = union_projected_roofs(roof, frame, offset, geoid)
    crop = figure_crop(roof_geom, frame["width"], frame["height"])
    fig, axes = plt.subplots(1, 3, figsize=(20, 6.2), dpi=140)
    for ax in axes:
        ax.imshow(rgb)
        ax.set_aspect("equal")
        ax.set_xlabel("source x [px]")
        ax.set_ylabel("source y [px]")
    draw_reference(axes[0], roof, ground, frame, offset, geoid)
    axes[0].set_xlim(0, frame["width"])
    axes[0].set_ylim(frame["height"], 0)
    axes[0].set_title("Full source frame: fixed-pose reference projection")
    axes[0].legend(loc="lower left", fontsize=7)
    axes[1].set_xlim(crop[0], crop[1])
    axes[1].set_ylim(crop[2], crop[3])
    axes[1].set_title("Building-centred crop: source RGB only")
    draw_reference(axes[2], roof, ground, frame, offset, geoid)
    axes[2].set_xlim(crop[0], crop[1])
    axes[2].set_ylim(crop[2], crop[3])
    axes[2].set_title("Building-centred crop: RoofSurface + footprint")
    fig.suptitle(
        f"DEBY_LOD2_{short} | {stem} | clipped area={float(row['roof_clipped_area_px']):.1f}px | "
        f"safe perimeter={float(row['safe_perimeter_fraction']):.3f} | {row['view_quality_class']}",
        fontsize=10,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    path = FIG_DIR / f"recog_{short}_{stem}.png"
    fig.savefig(path)
    plt.close(fig)
    return path


REG_FIELDS = [
    "row_type", "building_id", "view_stem", "view", "address_support", "oracle_visible_support",
    "roof_surface_count", "roof_area_m2", "footprint_roof_xy_symmetric_difference_m2",
    "roof_full_projected_area_px", "roof_clipped_area_px", "safe_perimeter_fraction",
    "projected_bbox_xyxy", "view_quality_class", "view_votes_for_building", "configured_anchor_view",
    "registration_class", "registration_class_ko", "registration_observation", "status",
    "projection_rule", "gt_role", "learning_runs_started", "new_mast3r_inference_runs",
]


def registration_report(rows: Sequence[dict[str, Any]], figures: Sequence[Path]) -> str:
    summaries = [row for row in rows if row["row_type"] == "building_summary"]
    views = [row for row in rows if row["row_type"] == "view"]
    lines = [
        "# W — E5 C001 S3-A′ FM 재삼각측량 재채점 (2026-07-15)", "",
        "> 학습 0회·신규 MASt3R 추론 0회. 기존 고정-COLMAP DLT 캐시만 재사용한다.",
        "> LoD2 지붕·발자국은 등록 QA와 채점·오버레이에만 사용한다.", "",
        "## 1파 — 인식 QA·등록 확인", "",
        "- 실제 CityGML `RoofSurface` 평면과 `GroundSurface` footprint를 `z_local=z_DHHN2016+45.7-world_offset_z`로 변환하고 고정 `K[R|t]`로 투영했다.",
        "- 판독 가능: 화면 안 지붕 면적 ≥256 px 및 8 px 안전 프레임 내 외곽 ≥0.70. 앵커: ≥1024 px 및 ≥0.90. 프레임 절단 뷰는 건물 투표에서 제외했다.",
        "- 기존 semantic mask/IoU는 LoD2 계보 자기일치라 등록 판정값으로 재사용하지 않았다.", "",
        "| 건물 | 앵커 | 등록 분류 | 판독 가능/전체 뷰 | 등록 확인 1줄 |",
        "|---|---|---|---:|---|",
    ]
    for row in summaries:
        lines.append(
            f"| {row['building_id']} | `{row['configured_anchor_view']}` | **{row['registration_class_ko']}** "
            f"| {row['reviewable_view_count']}/{row['visible_view_count']} | {row['registration_observation']} |"
        )
    lines.extend(["", "### 뷰별 관측 품질", "", "| 건물 | 뷰 | 면적(px) | 안전 외곽 | 품질 | 투표 |", "|---|---|---:|---:|---|---|"])
    for row in views:
        lines.append(
            f"| {row['building_id']} | `{row['view_stem']}` | {float(row['roof_clipped_area_px']):.1f} "
            f"| {float(row['safe_perimeter_fraction']):.3f} | `{row['view_quality_class']}` | {row['view_votes_for_building']} |"
        )
    lines.extend(["", "### 원 프레임 + 중심 크롭", ""])
    for path in figures:
        lines.append(f"![{path.stem}](figs/e5_c001_s3ap_fm_retri_rescore/{path.name})")
    lines.extend(["", "## 2파 — 높이·평면·경계표", "", "1파 등록 정지점 이후 실행 전.", ""])
    return "\n".join(lines)


def write_progress(phase: str, completed: Sequence[str], status: str) -> None:
    atomic_text(PROGRESS, json.dumps({
        "schema": "jointbuildgs.s3ap.fm_retri_rescore.progress.v1",
        "updated_utc": now(), "phase": phase, "completed": list(completed), "status": status,
        "learning_runs_started": 0, "new_mast3r_inference_runs": 0,
    }, ensure_ascii=False, indent=2) + "\n")


def wave1(allow_pending: bool) -> None:
    configure_font()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if config["learning_runs_allowed"] != 0 or config["new_mast3r_inference_allowed"] is not False:
        raise RuntimeError("learning/inference lock mismatch")
    old_manifest = json.loads(OLD_MANIFEST.read_text(encoding="utf-8"))
    offset = np.asarray(json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))["world_offset"], dtype=np.float64)
    datum = json.loads(PROJECTION_DATUM.read_text(encoding="utf-8"))
    geoid = float(datum["orthometric_geoid_m"])
    lod2 = load_lod2()
    footprints = load_all_footprints()
    frames = load_frames()
    gate = config["registration_gate"]
    frame_margin = float(gate["safe_frame_margin_px"])
    rows: list[dict[str, Any]] = []
    figures: list[Path] = []
    completed: list[str] = []
    log("wave1_start cached-only registration QA")
    for short in TARGETS:
        roof = lod2[short]["RoofSurface"]
        ground = lod2[short]["GroundSurface"]
        roof_union = make_valid(unary_union([surface.polygon for surface in roof]))
        target_fp = footprints[f"DEBY_LOD2_{short}"]
        symdiff = float(roof_union.symmetric_difference(target_fp).area)
        review = config["registration_reviews"][short]
        view_rows: list[dict[str, Any]] = []
        for view in old_manifest["locked_visible_views"][short]:
            stem = view["stem"]
            frame = frames[stem]
            geom = union_projected_roofs(roof, frame, offset, geoid)
            frame_rect = box(0, 0, frame["width"], frame["height"])
            safe_rect = box(frame_margin, frame_margin, frame["width"] - frame_margin, frame["height"] - frame_margin)
            clipped_area = float(geom.intersection(frame_rect).area) if not geom.is_empty else 0.0
            safe_fraction = boundary_fraction(geom, safe_rect)
            reviewable = clipped_area >= float(gate["reviewable_min_clipped_area_px"]) and safe_fraction >= float(gate["reviewable_min_safe_perimeter_fraction"])
            anchor = clipped_area >= float(gate["anchor_min_clipped_area_px"]) and safe_fraction >= float(gate["anchor_min_safe_perimeter_fraction"])
            quality = "anchor" if anchor else ("reviewable_nonanchor" if reviewable else "frame_clipped_or_too_small")
            bounds = geom.bounds if not geom.is_empty else (math.nan,) * 4
            row = {
                "row_type": "view", "building_id": f"DEBY_LOD2_{short}", "view_stem": stem, "view": view["view"],
                "address_support": view["support"], "oracle_visible_support": view["oracle_visible_support"],
                "roof_surface_count": len(roof), "roof_area_m2": float(roof_union.area),
                "footprint_roof_xy_symmetric_difference_m2": symdiff,
                "roof_full_projected_area_px": float(geom.area) if not geom.is_empty else 0.0,
                "roof_clipped_area_px": clipped_area, "safe_perimeter_fraction": safe_fraction,
                "projected_bbox_xyxy": ";".join(fmt(value) for value in bounds), "view_quality_class": quality,
                "view_votes_for_building": "yes" if anchor else "no", "configured_anchor_view": review["anchor_view"],
                "registration_class": review["registration_class"],
                "registration_class_ko": CLASS_LABEL.get(review["registration_class"], review["registration_class"]),
                "registration_observation": review["observation"], "status": "measured",
                "projection_rule": "actual LoD2 roof/ground XYZ -> local with geoid 45.7 -> fixed COLMAP K[R|t]",
                "gt_role": "registration QA/overlay only", "learning_runs_started": 0, "new_mast3r_inference_runs": 0,
            }
            path = make_registration_figure(short, stem, frame, roof, ground, offset, geoid, row)
            figures.append(path)
            view_rows.append(row)
            rows.append(row)
            atomic_csv(REG_CSV, rows, REG_FIELDS)
            write_progress("wave1_registration", completed, f"measured:{short}:{stem}")
            log(f"wave1_view {short} {stem} quality={quality} area={clipped_area:.3f} safe_perim={safe_fraction:.6f}")
        anchors = [row for row in view_rows if row["view_quality_class"] == "anchor"]
        reviewable = [row for row in view_rows if row["view_quality_class"] != "frame_clipped_or_too_small"]
        acquisition_blocks = {row["view_stem"].split("_")[1][:12] for row in reviewable}
        configured_anchor = review["anchor_view"]
        if configured_anchor == "auto" and anchors:
            configured_anchor = max(anchors, key=lambda row: (float(row["safe_perimeter_fraction"]), float(row["roof_clipped_area_px"])))["view_stem"]
        if review["registration_class"] == "pending" and not allow_pending:
            raise RuntimeError(f"pending registration review: {short}")
        if review["registration_class"] != "pending":
            anchor_ok = configured_anchor in {row["view_stem"] for row in anchors}
            consensus_ok = (
                configured_anchor == "MULTIVIEW_CONSENSUS"
                and len(reviewable) >= int(gate["consensus_min_reviewable_views"])
                and len(acquisition_blocks) >= int(gate["consensus_min_acquisition_blocks"])
            )
            if not (anchor_ok or consensus_ok):
                raise RuntimeError(f"configured anchor/consensus is not eligible for {short}: {configured_anchor}")
        summary = {
            "row_type": "building_summary", "building_id": f"DEBY_LOD2_{short}", "view_stem": "BUILDING",
            "roof_surface_count": len(roof), "roof_area_m2": float(roof_union.area),
            "footprint_roof_xy_symmetric_difference_m2": symdiff,
            "view_quality_class": "anchor_review_summary", "configured_anchor_view": configured_anchor,
            "registration_class": review["registration_class"],
            "registration_class_ko": CLASS_LABEL.get(review["registration_class"], review["registration_class"]),
            "registration_observation": review["observation"], "visible_view_count": len(view_rows),
            "reviewable_view_count": sum(row["view_quality_class"] != "frame_clipped_or_too_small" for row in view_rows),
            "anchor_view_count": len(anchors), "status": "pending_visual_review" if review["registration_class"] == "pending" else "registration_reviewed",
            "projection_rule": "actual LoD2 roof/ground XYZ -> local with geoid 45.7 -> fixed COLMAP K[R|t]",
            "gt_role": "registration QA/overlay only", "learning_runs_started": 0, "new_mast3r_inference_runs": 0,
        }
        rows.append(summary)
        atomic_csv(REG_CSV, rows, REG_FIELDS + ["visible_view_count", "reviewable_view_count", "anchor_view_count"])
        completed.append(short)
        write_progress("wave1_registration", completed, f"building_complete:{short}")
    atomic_text(REPORT, registration_report(rows, figures))
    write_progress("wave1_registration", completed, "complete")
    log("wave1_complete")
    source_paths = [
        Path(__file__), CONFIG, OLD_MANIFEST, TRAIN_MANIFEST, PROJECTION_DATUM, FOOTPRINTS,
        SPARSE_DIR / "cameras.bin", SPARSE_DIR / "images.bin", *sorted(PAIR_DIR.glob("*.npz")),
    ]
    source_paths.extend(sorted(LOD2_DIR.glob("*.gml")))
    source_paths.extend(frames[view["stem"]]["path"] for views in old_manifest["locked_visible_views"].values() for view in views)
    output_paths = [REG_CSV, REPORT, PROGRESS, RUN_LOG, *figures]
    payload = {
        "schema": "jointbuildgs.s3ap.fm_retri_rescore.registration.v1", "created_utc": now(),
        "git_head_at_measurement": git_value("rev-parse", "HEAD"), "branch": git_value("branch", "--show-current"),
        "learning_runs_started": 0, "new_mast3r_inference_runs": 0,
        "cache_source_run": rel(OLD_RUN), "registration_gate": gate,
        "source_sha256": {rel(path): sha256_file(path) for path in source_paths},
        "output_sha256": {rel(path): sha256_file(path) for path in output_paths},
        "row_count": len(rows), "view_row_count": sum(row["row_type"] == "view" for row in rows),
        "summary_row_count": sum(row["row_type"] == "building_summary" for row in rows),
        "registration_classes": {row["building_id"]: row["registration_class"] for row in rows if row["row_type"] == "building_summary"},
        "interpretation_or_verdict": None,
    }
    atomic_text(REG_MANIFEST, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def finite_stats(values: np.ndarray) -> dict[str, float | None]:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if not len(values):
        return {key: None for key in ["q05", "q25", "median", "q75", "q95", "mad", "rms"]}
    median = float(np.median(values))
    return {
        "q05": float(np.quantile(values, 0.05)),
        "q25": float(np.quantile(values, 0.25)),
        "median": median,
        "q75": float(np.quantile(values, 0.75)),
        "q95": float(np.quantile(values, 0.95)),
        "mad": float(np.median(np.abs(values - median))),
        "rms": float(np.sqrt(np.mean(values * values))),
    }


def read_ply_xyz_ascii(path: Path) -> np.ndarray:
    vertex_count: int | None = None
    header_lines = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            header_lines += 1
            if line.startswith("element vertex "):
                vertex_count = int(line.split()[-1])
            if line.strip() == "end_header":
                break
    if vertex_count is None:
        raise RuntimeError(f"missing ASCII PLY vertex count: {rel(path)}")
    points = np.loadtxt(path, skiprows=header_lines, max_rows=vertex_count, usecols=(0, 1, 2), dtype=np.float32)
    points = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    if len(points) != vertex_count:
        raise RuntimeError(f"PLY count mismatch: {len(points)} != {vertex_count}")
    return points


def points_in_geometry(points_local: np.ndarray, geometry: Any, offset: np.ndarray) -> np.ndarray:
    minx, miny, maxx, maxy = geometry.bounds
    x = points_local[:, 0].astype(np.float64) + float(offset[0])
    y = points_local[:, 1].astype(np.float64) + float(offset[1])
    candidate = (x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy)
    out = np.zeros(len(points_local), dtype=bool)
    indices = np.flatnonzero(candidate)
    if len(indices):
        out[indices] = contains_xy(geometry, x[indices], y[indices])
    return out


def estimate_ground(
    short: str,
    target: Any,
    all_footprints: Any,
    points_local: np.ndarray,
    offset: np.ndarray,
    config: dict[str, Any],
) -> dict[str, Any]:
    minimum = float(config["target_outer_distance_min_m"])
    maximum = float(config["target_outer_distance_max_m"])
    exclusion = float(config["all_footprint_exclusion_buffer_m"])
    region = make_valid(target.buffer(maximum).difference(target.buffer(minimum)))
    region = make_valid(region.difference(all_footprints.buffer(exclusion)))
    selected = points_local[points_in_geometry(points_local, region, offset)]
    grid = float(config["grid_m"])
    minimum_per_cell = int(config["min_points_per_cell"])
    if not len(selected):
        raise RuntimeError(f"no clean exterior observed points for {short}")
    world_xy = selected[:, :2].astype(np.float64) + offset[:2]
    cell_xy = np.floor(world_xy / grid).astype(np.int64)
    unique, inverse = np.unique(cell_xy, axis=0, return_inverse=True)
    cell_q10: list[float] = []
    for index in range(len(unique)):
        values = selected[inverse == index, 2].astype(np.float64)
        if len(values) >= minimum_per_cell:
            cell_q10.append(float(np.quantile(values, float(config["cell_z_quantile"]))))
    values = np.asarray(cell_q10, dtype=np.float64)
    if not len(values):
        raise RuntimeError(f"no clean exterior ground cells for {short}")
    if len(values) >= 4:
        q1, q3 = np.quantile(values, [0.25, 0.75])
        iqr = float(q3 - q1)
        clipped = values[(values >= q1 - 1.5 * iqr) & (values <= q3 + 1.5 * iqr)]
    else:
        clipped = values
    bin_width = float(config["mode_bin_m"])
    bin_ids = np.floor(clipped / bin_width).astype(np.int64)
    bins, counts = np.unique(bin_ids, return_counts=True)
    max_count = int(np.max(counts))
    mode_bin = int(np.min(bins[counts == max_count]))
    mode_centre = (mode_bin + 0.5) * bin_width
    selected_cells = clipped[np.abs(clipped - mode_centre) <= float(config["mode_half_window_m"])]
    method = "clean exterior 1m-cell q10 lower-mode median"
    if len(selected_cells) < 3:
        selected_cells = clipped
        method = "clean exterior 1m-cell q10 Tukey-clipped median fallback"
    ground = float(np.median(selected_cells))
    return {
        "ground_z_local_m": ground,
        "ground_z_mad_m": float(np.median(np.abs(selected_cells - ground))),
        "ground_method": method,
        "ground_region_rule": (
            f"target {minimum:.1f}-{maximum:.1f}m exterior; all footprint buffers {exclusion:.1f}m excluded"
        ),
        "ground_observed_point_count": int(len(selected)),
        "ground_cell_count": int(len(values)),
        "ground_mode_cell_count": int(len(selected_cells)),
        "ground_mode_centre_local_m": mode_centre,
        "ground_source": (
            "elevation: SfM points3D.bin + dense-init PLY; supplied footprints_aoi geometry used "
            "for target exterior/exclusion masks; no LoD2 roof height/plane or ALS elevation"
        ),
    }


def acquisition_block(stem: str) -> str:
    return stem.split("_")[1][:12]


def load_cached_pairs(old_manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    expected_hashes = old_manifest["output_sha256"]
    out: dict[str, list[dict[str, Any]]] = {short: [] for short in TARGETS}
    for path in sorted(PAIR_DIR.glob("*.npz")):
        relative = rel(path)
        if expected_hashes.get(relative) != sha256_file(path):
            raise RuntimeError(f"cached DLT hash mismatch: {relative}")
        with np.load(path, allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata_json"]))
            detail = {
                "path": path,
                "short": str(metadata["short"]),
                "rank": int(metadata["rank"]),
                "view_a": str(metadata["view_a"]),
                "view_b": str(metadata["view_b"]),
                "old_row": metadata["row"],
                "pixels_a": np.asarray(archive["pixels_a"], dtype=np.float64),
                "pixels_b": np.asarray(archive["pixels_b"], dtype=np.float64),
                "world": np.asarray(archive["world_local_xyz"], dtype=np.float64),
                "cached_inside": np.asarray(archive["inside_footprint_score_mask"], dtype=bool),
                "max_reprojection_error_px": np.asarray(archive["max_reprojection_error_px"], dtype=np.float64),
            }
        if detail["short"] not in out:
            continue
        out[detail["short"]].append(detail)
    expected_counts = {"4907199": 10, "8568391": 3, "8568392": 3}
    for short, count in expected_counts.items():
        if len(out[short]) != count:
            raise RuntimeError(f"cached pair count mismatch for {short}: {len(out[short])} != {count}")
        out[short].sort(key=lambda detail: detail["rank"])
    return out


def reference_z_for_points(points_local: np.ndarray, roof: Sequence[Surface], offset: np.ndarray, geoid: float) -> np.ndarray:
    if not len(points_local):
        return np.zeros(0, dtype=np.float64)
    world_x = points_local[:, 0] + offset[0]
    world_y = points_local[:, 1] + offset[1]
    reference = np.full(len(points_local), np.nan, dtype=np.float64)
    for surface in roof:
        covered = contains_xy(surface.polygon, world_x, world_y)
        reference[covered] = surface.z_at(world_x[covered], world_y[covered]) + geoid - offset[2]
    return reference


def fit_plane(points: np.ndarray, references: np.ndarray, config: dict[str, Any]) -> dict[str, Any]:
    points = np.asarray(points, dtype=np.float64)
    references = np.asarray(references, dtype=np.float64)
    finite = np.isfinite(points).all(axis=1) & np.isfinite(references)
    points, references = points[finite], references[finite]
    if len(points) < 3 or len(np.unique(np.round(points[:, :2], 6), axis=0)) < 3:
        return {
            "plane_status": "insufficient_xy_support", "ransac_inlier_count": 0,
            "ransac_inlier_ratio": None, "plane_ax": None, "plane_by": None, "plane_c": None,
            "plane_internal_rms_m": None, "fitted_plane_to_lod2_rms_m": None,
            "ransac_inlier_mask": np.zeros(len(points), dtype=bool),
        }
    centre = np.mean(points[:, :2], axis=0)
    x = points[:, :2] - centre
    minimum = max(int(config["ransac_min_samples_floor"]), int(math.ceil(float(config["ransac_min_samples_fraction"]) * len(points))))
    minimum = min(minimum, len(points))
    try:
        model = RANSACRegressor(
            estimator=LinearRegression(), min_samples=minimum,
            residual_threshold=float(config["ransac_residual_threshold_m"]),
            max_trials=int(config["ransac_max_trials"]), random_state=int(config["random_seed"]),
        )
        model.fit(x, points[:, 2])
        predicted = np.asarray(model.predict(x), dtype=np.float64)
        # Re-evaluate the final refitted estimator against the locked residual
        # threshold. sklearn's stored consensus mask precedes the final refit
        # and can otherwise under-report the support of that reported plane.
        inlier = np.abs(points[:, 2] - predicted) <= float(config["ransac_residual_threshold_m"])
        estimator = model.estimator_
        ax, by = [float(value) for value in estimator.coef_]
        intercept = float(estimator.intercept_ - ax * centre[0] - by * centre[1])
        return {
            "plane_status": "fit", "ransac_inlier_count": int(np.count_nonzero(inlier)),
            "ransac_inlier_ratio": float(np.mean(inlier)), "plane_ax": ax, "plane_by": by,
            "plane_c": intercept,
            "plane_internal_rms_m": float(np.sqrt(np.mean((points[inlier, 2] - predicted[inlier]) ** 2))) if np.any(inlier) else None,
            "fitted_plane_to_lod2_rms_m": float(np.sqrt(np.mean((predicted - references) ** 2))),
            "ransac_inlier_mask": inlier,
        }
    except (ValueError, RuntimeError) as exc:
        return {
            "plane_status": f"fit_failed:{type(exc).__name__}", "ransac_inlier_count": 0,
            "ransac_inlier_ratio": None, "plane_ax": None, "plane_by": None, "plane_c": None,
            "plane_internal_rms_m": None, "fitted_plane_to_lod2_rms_m": None,
            "ransac_inlier_mask": np.zeros(len(points), dtype=bool),
        }


def grid_coverage(points_local: np.ndarray, footprint: Any, offset: np.ndarray, grid: float) -> dict[str, Any]:
    minx, miny, maxx, maxy = footprint.bounds
    ix = np.arange(math.floor(minx / grid), math.floor(maxx / grid) + 1, dtype=np.int64)
    iy = np.arange(math.floor(miny / grid), math.floor(maxy / grid) + 1, dtype=np.int64)
    mesh_x, mesh_y = np.meshgrid(ix, iy, indexing="xy")
    candidate_cells = zip(mesh_x.ravel().tolist(), mesh_y.ravel().tolist())
    eligible_cells = {
        (cell_x, cell_y)
        for cell_x, cell_y in candidate_cells
        if footprint.intersects(
            box(cell_x * grid, cell_y * grid, (cell_x + 1) * grid, (cell_y + 1) * grid)
        )
    }
    if len(points_local):
        world_xy = points_local[:, :2] + offset[:2]
        point_cells = np.floor(world_xy / grid).astype(np.int64)
        occupied = set(zip(point_cells[:, 0].tolist(), point_cells[:, 1].tolist())) & eligible_cells
    else:
        occupied = set()
    return {
        "coverage_grid_m": grid,
        "coverage_eligible_cell_count": len(eligible_cells),
        "coverage_occupied_cell_count": len(occupied),
        "coverage_ratio": float(len(occupied) / len(eligible_cells)) if eligible_cells else None,
        "eligible_cells": eligible_cells,
        "occupied_cells": occupied,
    }


def convex_hull_coverage(points_local: np.ndarray, footprint: Any, offset: np.ndarray) -> float | None:
    if len(points_local) < 3:
        return 0.0 if len(points_local) else None
    xy = points_local[:, :2] + offset[:2]
    hull = MultiPoint(xy).convex_hull
    return float(hull.intersection(footprint).area / footprint.area) if footprint.area > 0 else None


RESCORE_FIELDS = [
    "row_type", "building_id", "pair_rank", "view_a", "view_b", "acquisition_block_a", "acquisition_block_b",
    "pair_relation", "known_colmap_baseline_m", "baseline_class", "eligible_summary_pair",
    "cached_dlt_survivor_count", "cached_max_reprojection_error_px", "inside_point_count",
    "inside_z_q05_local_m", "inside_z_q25_local_m", "inside_z_median_local_m", "inside_z_q75_local_m",
    "inside_z_q95_local_m", "inside_z_mad_m", "reference_roof_z_median_local_m", "abs_delta_z_median_m",
    "abs_delta_z_mad_m", "point_to_lod2_rms_m", "upper_roof_candidate_count", "upper_height_threshold_local_m",
    "plane_status", "ransac_inlier_count", "ransac_inlier_ratio", "plane_ax", "plane_by", "plane_c",
    "plane_internal_rms_m", "fitted_plane_to_lod2_rms_m", "coverage_grid_m", "coverage_eligible_cell_count",
    "coverage_occupied_cell_count", "coverage_ratio", "convex_hull_coverage_ratio", "ground_z_local_m",
    "ground_z_mad_m", "ground_method", "ground_region_rule", "ground_observed_point_count", "ground_cell_count",
    "ground_mode_cell_count", "ground_mode_centre_local_m", "ground_source", "registration_class",
    "selected_pair_count", "eligible_pair_count", "nonzero_inside_pair_count", "inside_point_count_pair_median",
    "inside_point_count_max_pair", "inside_point_count_max_pair_rank", "abs_delta_z_across_pair_mad_m",
    "numeric_boundary_class", "numeric_boundary_class_ko", "numeric_boundary_reason", "summary_aggregation",
    "status", "cache_path", "cache_sha256", "gt_role", "learning_runs_started", "new_mast3r_inference_runs",
]


def pair_score_row(
    detail: dict[str, Any], short: str, footprint: Any, roof: Sequence[Surface], offset: np.ndarray, geoid: float,
    ground: dict[str, Any], config: dict[str, Any], registration_class: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    world = detail["world"]
    if len(world):
        x = world[:, 0] + offset[0]
        y = world[:, 1] + offset[1]
        inside = contains_xy(footprint, x, y)
    else:
        inside = np.zeros(0, dtype=bool)
    if not np.array_equal(inside, detail["cached_inside"]):
        raise RuntimeError(f"cached footprint mask drift: {short} rank {detail['rank']}")
    inside_points = world[inside]
    reference = reference_z_for_points(inside_points, roof, offset, geoid)
    z_stats = finite_stats(inside_points[:, 2] if len(inside_points) else np.zeros(0))
    errors = np.abs(inside_points[:, 2] - reference) if len(inside_points) else np.zeros(0)
    error_stats = finite_stats(errors)
    plane = fit_plane(inside_points, reference, config["plane"])
    coverage = grid_coverage(inside_points, footprint, offset, float(config["coverage"]["grid_m"]))
    baseline = float(detail["old_row"]["known_colmap_baseline_m"])
    block_a, block_b = acquisition_block(detail["view_a"]), acquisition_block(detail["view_b"])
    relation = "cross_acquisition_block" if block_a != block_b else "same_acquisition_block"
    eligible = relation == "cross_acquisition_block" and baseline > 0.06
    threshold = float(ground["ground_z_local_m"]) + 1.5
    upper = int(np.count_nonzero(inside_points[:, 2] >= threshold)) if len(inside_points) else 0
    row: dict[str, Any] = {
        "row_type": "view_pair", "building_id": f"DEBY_LOD2_{short}", "pair_rank": detail["rank"],
        "view_a": detail["view_a"], "view_b": detail["view_b"], "acquisition_block_a": block_a,
        "acquisition_block_b": block_b, "pair_relation": relation, "known_colmap_baseline_m": baseline,
        "baseline_class": detail["old_row"]["baseline_class"], "eligible_summary_pair": eligible,
        "cached_dlt_survivor_count": len(world),
        "cached_max_reprojection_error_px": float(np.max(detail["max_reprojection_error_px"])) if len(world) else None,
        "inside_point_count": len(inside_points), "inside_z_q05_local_m": z_stats["q05"],
        "inside_z_q25_local_m": z_stats["q25"], "inside_z_median_local_m": z_stats["median"],
        "inside_z_q75_local_m": z_stats["q75"], "inside_z_q95_local_m": z_stats["q95"],
        "inside_z_mad_m": z_stats["mad"],
        "reference_roof_z_median_local_m": float(np.median(reference)) if len(reference) else None,
        "abs_delta_z_median_m": error_stats["median"], "abs_delta_z_mad_m": error_stats["mad"],
        "point_to_lod2_rms_m": error_stats["rms"], "upper_roof_candidate_count": upper,
        "upper_height_threshold_local_m": threshold, "plane_status": plane["plane_status"],
        "ransac_inlier_count": plane["ransac_inlier_count"], "ransac_inlier_ratio": plane["ransac_inlier_ratio"],
        "plane_ax": plane["plane_ax"], "plane_by": plane["plane_by"], "plane_c": plane["plane_c"],
        "plane_internal_rms_m": plane["plane_internal_rms_m"],
        "fitted_plane_to_lod2_rms_m": plane["fitted_plane_to_lod2_rms_m"],
        "coverage_grid_m": coverage["coverage_grid_m"],
        "coverage_eligible_cell_count": coverage["coverage_eligible_cell_count"],
        "coverage_occupied_cell_count": coverage["coverage_occupied_cell_count"],
        "coverage_ratio": coverage["coverage_ratio"],
        "convex_hull_coverage_ratio": convex_hull_coverage(inside_points, footprint, offset),
        **ground, "registration_class": registration_class, "status": "scored_cached_dlt",
        "cache_path": rel(detail["path"]), "cache_sha256": sha256_file(detail["path"]),
        "gt_role": (
            "cached DLT inherits source-run frozen T0-1 oracle-address crop; this wave applies LoD2 roof "
            "after cache for score/overlay and supplied footprint geometry for inside/exterior/coverage masks"
        ),
        "learning_runs_started": 0, "new_mast3r_inference_runs": 0,
    }
    scored = {
        **detail, "inside": inside, "inside_points": inside_points, "reference": reference,
        "errors": errors, "plane": plane, "coverage": coverage, "row": row,
    }
    return row, scored


def numeric_boundary(summary: dict[str, Any], registration_class: str) -> tuple[str, str, str]:
    if registration_class == "misregistered":
        return "iv_bad_registration", "(iv) 등록 불량", "registration_class=misregistered; score withheld"
    if registration_class == "ambiguous":
        return "ambiguous_registration", "등록 애매·분류 보류", "registration_class=ambiguous"
    n = int(summary["inside_point_count"])
    dz = summary["abs_delta_z_median_m"]
    plane_rms = summary["fitted_plane_to_lod2_rms_m"]
    inlier = summary["ransac_inlier_ratio"]
    coverage = summary["coverage_ratio"]
    good = (
        n >= 20 and dz is not None and float(dz) <= 1.0 and plane_rms is not None and float(plane_rms) <= 1.0
        and inlier is not None and float(inlier) >= 0.50 and coverage is not None and float(coverage) >= 0.25
    )
    if good:
        return (
            "i_seed_usable", "(i) 지붕 평면 적합 양호+발자국 덮음",
            "n>=20; median_abs_dz<=1.0m; plane RMS<=1.0m; inlier>=0.50; coverage>=0.25",
        )
    if dz is not None and float(dz) <= 1.5:
        failed = []
        if n < 20:
            failed.append("n<20")
        if plane_rms is None or float(plane_rms) > 1.0:
            failed.append("plane_RMS>1.0_or_NA")
        if inlier is None or float(inlier) < 0.50:
            failed.append("inlier<0.50_or_NA")
        if coverage is None or float(coverage) < 0.25:
            failed.append("coverage<0.25_or_NA")
        return "ii_near_height_scattered_or_low_coverage", "(ii) 높이 근처·흩어짐/저커버", ";".join(failed)
    return "iii_wrong_height_neighbor_or_wall", "(iii) 엉뚱한 높이·이웃/벽", "no inside points or median|dz|>1.5m"


def summary_score_row(
    short: str, pair_rows: Sequence[dict[str, Any]], details: Sequence[dict[str, Any]], footprint: Any,
    roof: Sequence[Surface], offset: np.ndarray, geoid: float, ground: dict[str, Any], config: dict[str, Any],
    registration_class: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    eligible_details = [detail for detail in details if bool(detail["row"]["eligible_summary_pair"])]
    pooled = np.concatenate([detail["inside_points"] for detail in eligible_details], axis=0) if eligible_details else np.zeros((0, 3))
    references = np.concatenate([detail["reference"] for detail in eligible_details]) if eligible_details else np.zeros(0)
    errors = np.abs(pooled[:, 2] - references) if len(pooled) else np.zeros(0)
    z_stats, error_stats = finite_stats(pooled[:, 2] if len(pooled) else np.zeros(0)), finite_stats(errors)
    plane = fit_plane(pooled, references, config["plane"])
    coverage = grid_coverage(pooled, footprint, offset, float(config["coverage"]["grid_m"]))
    eligible_rows = [row for row in pair_rows if bool(row["eligible_summary_pair"])]
    inside_counts = [int(row["inside_point_count"]) for row in eligible_rows]
    nonzero = [row for row in eligible_rows if int(row["inside_point_count"]) > 0]
    pair_error_medians = np.asarray([float(row["abs_delta_z_median_m"]) for row in nonzero if row["abs_delta_z_median_m"] is not None])
    pair_error_centre = float(np.median(pair_error_medians)) if len(pair_error_medians) else None
    pair_error_mad = float(np.median(np.abs(pair_error_medians - pair_error_centre))) if len(pair_error_medians) else None
    max_row = max(eligible_rows, key=lambda row: int(row["inside_point_count"])) if eligible_rows else None
    threshold = float(ground["ground_z_local_m"]) + 1.5
    row: dict[str, Any] = {
        "row_type": "building_summary", "building_id": f"DEBY_LOD2_{short}", "pair_rank": "POOLED_CROSS_BLOCK",
        "pair_relation": "cross_acquisition_block_only", "baseline_class": "baseline>0.06m only",
        "eligible_summary_pair": True, "cached_dlt_survivor_count": sum(len(detail["world"]) for detail in eligible_details),
        "inside_point_count": len(pooled), "inside_z_q05_local_m": z_stats["q05"],
        "inside_z_q25_local_m": z_stats["q25"], "inside_z_median_local_m": z_stats["median"],
        "inside_z_q75_local_m": z_stats["q75"], "inside_z_q95_local_m": z_stats["q95"],
        "inside_z_mad_m": z_stats["mad"],
        "reference_roof_z_median_local_m": float(np.median(references)) if len(references) else None,
        "abs_delta_z_median_m": error_stats["median"], "abs_delta_z_mad_m": error_stats["mad"],
        "point_to_lod2_rms_m": error_stats["rms"],
        "upper_roof_candidate_count": int(np.count_nonzero(pooled[:, 2] >= threshold)) if len(pooled) else 0,
        "upper_height_threshold_local_m": threshold, "plane_status": plane["plane_status"],
        "ransac_inlier_count": plane["ransac_inlier_count"], "ransac_inlier_ratio": plane["ransac_inlier_ratio"],
        "plane_ax": plane["plane_ax"], "plane_by": plane["plane_by"], "plane_c": plane["plane_c"],
        "plane_internal_rms_m": plane["plane_internal_rms_m"],
        "fitted_plane_to_lod2_rms_m": plane["fitted_plane_to_lod2_rms_m"],
        "coverage_grid_m": coverage["coverage_grid_m"],
        "coverage_eligible_cell_count": coverage["coverage_eligible_cell_count"],
        "coverage_occupied_cell_count": coverage["coverage_occupied_cell_count"], "coverage_ratio": coverage["coverage_ratio"],
        "convex_hull_coverage_ratio": convex_hull_coverage(pooled, footprint, offset), **ground,
        "registration_class": registration_class, "selected_pair_count": len(pair_rows),
        "eligible_pair_count": len(eligible_rows), "nonzero_inside_pair_count": len(nonzero),
        "inside_point_count_pair_median": float(np.median(inside_counts)) if inside_counts else None,
        "inside_point_count_max_pair": int(max_row["inside_point_count"]) if max_row else None,
        "inside_point_count_max_pair_rank": int(max_row["pair_rank"]) if max_row else None,
        "abs_delta_z_across_pair_mad_m": pair_error_mad,
        "summary_aggregation": "pooled all footprint-XY-inside cached DLT survivors from cross-block baseline>0.06m pairs",
        "status": "summary", "gt_role": (
            "cached DLT inherits source-run frozen T0-1 oracle-address crop; this wave applies LoD2 roof "
            "after cache for score/overlay and supplied footprint geometry for inside/exterior/coverage masks"
        ),
        "learning_runs_started": 0, "new_mast3r_inference_runs": 0,
    }
    code, label, reason = numeric_boundary(row, registration_class)
    row.update({"numeric_boundary_class": code, "numeric_boundary_class_ko": label, "numeric_boundary_reason": reason})
    return row, {"pooled": pooled, "references": references, "errors": errors, "plane": plane, "coverage": coverage}


def plot_polygon_world(ax: Any, geometry: Any, centre: np.ndarray, color: str, linestyle: str, label: str, linewidth: float = 1.8) -> None:
    first = True
    for polygon in flatten_polygons(geometry):
        rings = [polygon.exterior, *polygon.interiors]
        for ring in rings:
            xy = np.asarray(ring.coords, dtype=np.float64) - centre[None, :]
            ax.plot(xy[:, 0], xy[:, 1], color=color, linestyle=linestyle, linewidth=linewidth, label=label if first else None)
            first = False


def score_figure(
    short: str, representative: str, frame: dict[str, Any], details: Sequence[dict[str, Any]], summary: dict[str, Any],
    footprint: Any, roof: Sequence[Surface], ground_surfaces: Sequence[Surface], offset: np.ndarray, geoid: float,
) -> Path:
    rgb = np.asarray(Image.open(frame["path"]).convert("RGB"))
    pixels: list[np.ndarray] = []
    errors: list[np.ndarray] = []
    for detail in details:
        if not bool(detail["row"]["eligible_summary_pair"]):
            continue
        source_pixels = detail["pixels_a"] if detail["view_a"] == representative else (detail["pixels_b"] if detail["view_b"] == representative else None)
        if source_pixels is not None and len(source_pixels):
            pixels.append(source_pixels[detail["inside"]])
            errors.append(detail["errors"])
    shown_pixels = np.concatenate(pixels, axis=0) if pixels else np.zeros((0, 2))
    shown_errors = np.concatenate(errors) if errors else np.zeros(0)
    roof_geom = union_projected_roofs(roof, frame, offset, geoid)
    crop = figure_crop(roof_geom, frame["width"], frame["height"])
    fig, axes = plt.subplots(1, 3, figsize=(20, 6.5), dpi=150)
    norm = Normalize(vmin=0.0, vmax=2.0, clip=True)
    cmap = plt.get_cmap("viridis")
    for ax in axes[:2]:
        ax.imshow(rgb)
        draw_reference(ax, roof, ground_surfaces, frame, offset, geoid)
        ax.set_xlabel("source x [px]")
        ax.set_ylabel("source y [px]")
    for ax in axes[:2]:
        if len(shown_pixels):
            near = shown_errors <= 1.0
            middle = (shown_errors > 1.0) & (shown_errors <= 1.5)
            far = shown_errors > 1.5
            ax.scatter(shown_pixels[near, 0], shown_pixels[near, 1], c=shown_errors[near], cmap=cmap, norm=norm, s=12, marker="o", edgecolors="black", linewidths=0.15, alpha=0.85)
            ax.scatter(shown_pixels[middle, 0], shown_pixels[middle, 1], c=shown_errors[middle], cmap=cmap, norm=norm, s=22, marker="^", edgecolors="black", linewidths=0.25, alpha=0.9)
            ax.scatter(shown_pixels[far, 0], shown_pixels[far, 1], c=shown_errors[far], cmap=cmap, norm=norm, s=22, marker="x", linewidths=0.7, alpha=0.9)
    axes[0].set_xlim(0, frame["width"])
    axes[0].set_ylim(frame["height"], 0)
    axes[0].set_title("Full frame: all inside cached DLT points")
    axes[1].set_xlim(crop[0], crop[1])
    axes[1].set_ylim(crop[2], crop[3])
    axes[1].set_title("Building crop: point colour = |delta z| [m]")
    axes[0].legend(loc="lower left", fontsize=6)
    axes[1].legend(loc="lower left", fontsize=6)
    centre = np.asarray(footprint.centroid.coords[0], dtype=np.float64)
    plot_polygon_world(axes[2], footprint, centre, "#00bcd4", "-", "footprint", 2.0)
    roof_union = make_valid(unary_union([surface.polygon for surface in roof]))
    plot_polygon_world(axes[2], roof_union, centre, "#d81b60", "--", "LoD2 roof outline", 1.4)
    pooled = summary["pooled"]
    pooled_errors = summary["errors"]
    if len(pooled):
        xy = pooled[:, :2] + offset[:2] - centre[None, :]
        near = pooled_errors <= 1.0
        middle = (pooled_errors > 1.0) & (pooled_errors <= 1.5)
        far = pooled_errors > 1.5
        axes[2].scatter(xy[near, 0], xy[near, 1], c=pooled_errors[near], cmap=cmap, norm=norm, s=15, marker="o", edgecolors="black", linewidths=0.15, alpha=0.85)
        axes[2].scatter(xy[middle, 0], xy[middle, 1], c=pooled_errors[middle], cmap=cmap, norm=norm, s=28, marker="^", edgecolors="black", linewidths=0.25, alpha=0.9)
        axes[2].scatter(xy[far, 0], xy[far, 1], c=pooled_errors[far], cmap=cmap, norm=norm, s=28, marker="x", linewidths=0.8, alpha=0.9)
    axes[2].set_aspect("equal")
    axes[2].set_xlabel(f"E - {centre[0]:.3f} [m], EPSG:25832")
    axes[2].set_ylabel(f"N - {centre[1]:.3f} [m], EPSG:25832")
    axes[2].set_title("Top view: footprint, LoD2 outline, inside points")
    axes[2].legend(loc="best", fontsize=8)
    scalar = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    scalar.set_array([])
    cax = fig.add_axes([0.925, 0.20, 0.012, 0.58])
    colorbar = fig.colorbar(scalar, cax=cax)
    colorbar.set_label("vertical |delta z| to LoD2 [m], clipped at 2 m")
    fig.suptitle(
        f"DEBY_LOD2_{short} | {representative} | pooled inside n={len(pooled)} | "
        f"coverage={fmt(summary['coverage']['coverage_ratio'])}", fontsize=10,
    )
    fig.subplots_adjust(left=0.045, right=0.90, bottom=0.10, top=0.90, wspace=0.22)
    path = FIG_DIR / f"score_{short}.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def rescore_report(pair_rows: Sequence[dict[str, Any]], summaries: Sequence[dict[str, Any]], figures: Sequence[Path]) -> str:
    wave1_text = REPORT.read_text(encoding="utf-8").split("## 2파 —", 1)[0].rstrip()
    lines = [wave1_text, "", "## 2파 — 높이·평면·경계표", "",
        "- 이번 파도 후보 생성·추론 없음. 기존 NPZ의 cheirality·재투영 ≤2 px DLT 생존점 중 발자국 XY 안의 **모든 점**을 높이 필터 전에 재채점했다. 캐시는 원 실행의 frozen T0-1 oracle-address 크롭 계보를 그대로 상속한다.",
        "- 건물 요약은 acquisition-minute block이 다른 쌍이면서 기선 >0.06 m인 쌍의 안 점을 풀링한다. 쌍별 행은 제외 쌍과 0점 쌍도 보존한다.",
        "- 지면 **높이 표본**은 관측 SfM+밀집 초기점만 썼다. 발주 입력 `footprints_aoi` 형상으로 표적 2–15 m 바깥과 모든 발자국 1 m buffer를 공간 마스킹하고, 1 m 셀 q10의 0.5 m 하부 모드 중앙값을 냈다. LoD2 지붕 높이·평면과 ALS 높이는 쓰지 않았다.",
        "- 평면은 안 점 전체에 결정적 RANSAC(잔차 0.30 m, seed 20260715); 커버리지는 발자국과 교차하는 0.5 m 셀 중 점이 있는 셀의 비율이다.", "",
        "### 건물 요약·수치 경계", "",
        "| 건물 | 교차쌍 안 점(쌍 중앙/최대·rank) | z 중앙±MAD | 중앙 abs(Δz) | 점→LoD2 RMS | 적합면→LoD2 RMS | inlier | 커버리지 | 수치 분류 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in summaries:
        lines.append(
            f"| {row['building_id']} | {row['inside_point_count']} ({fmt(row['inside_point_count_pair_median'])}/{row['inside_point_count_max_pair']}·r{row['inside_point_count_max_pair_rank']}) "
            f"| {fmt(row['inside_z_median_local_m'])}±{fmt(row['inside_z_mad_m'])} "
            f"| {fmt(row['abs_delta_z_median_m'])} | {fmt(row['point_to_lod2_rms_m'])} "
            f"| {fmt(row['fitted_plane_to_lod2_rms_m'])} | {fmt(row['ransac_inlier_ratio'])} "
            f"| {fmt(row['coverage_ratio'])} | **{row['numeric_boundary_class_ko']}** |"
        )
    single_pair_rows = [row for row in summaries if int(row["nonzero_inside_pair_count"]) == 1]
    if single_pair_rows:
        lines.extend(["", "### 단일 비영점 쌍 보존", ""])
        for row in single_pair_rows:
            source = next(
                pair for pair in pair_rows
                if pair["building_id"] == row["building_id"]
                and bool(pair["eligible_summary_pair"])
                and int(pair["inside_point_count"]) > 0
            )
            clipped_note = ""
            if source["view_a"].endswith("0048_D") or source["view_b"].endswith("0048_D"):
                clipped_note = "; 0048은 1파 frame-clipped·비투표 뷰"
            lines.append(
                f"- {row['building_id']}: 요약 대상 {row['eligible_pair_count']}쌍 중 비영점 1쌍; "
                f"r{source['pair_rank']} `{source['view_a']} × {source['view_b']}` = "
                f"{source['inside_point_count']}점{clipped_note}."
            )
    lines.extend(["", "### 지면 재추정", "", "| 건물 | 지면 z(local m) | MAD | 관측점 | 셀/모드 셀 | 방식 |", "|---|---:|---:|---:|---:|---|"])
    for row in summaries:
        lines.append(
            f"| {row['building_id']} | {fmt(row['ground_z_local_m'])} | {fmt(row['ground_z_mad_m'])} "
            f"| {row['ground_observed_point_count']} | {row['ground_cell_count']}/{row['ground_mode_cell_count']} | {row['ground_method']} |"
        )
    lines.extend(["", "### 뷰쌍별 모든 안 점", "",
        "| 건물·rank | 관계/기선(m) | 요약 포함 | 안 점 | z 중앙±MAD | 중앙 abs(Δz) | 평면 RMS | inlier | 커버리지 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ])
    for row in pair_rows:
        z_text = "—" if row["inside_z_median_local_m"] is None else f"{fmt(row['inside_z_median_local_m'])}±{fmt(row['inside_z_mad_m'])}"
        lines.append(
            f"| {row['building_id']}·r{row['pair_rank']} | {row['pair_relation']}/{fmt(row['known_colmap_baseline_m'])} "
            f"| {fmt(row['eligible_summary_pair'])} | {row['inside_point_count']} "
            f"| {z_text} "
            f"| {fmt(row['abs_delta_z_median_m'])} | {fmt(row['fitted_plane_to_lod2_rms_m'])} "
            f"| {fmt(row['ransac_inlier_ratio'])} | {fmt(row['coverage_ratio'])} |"
        )
    lines.extend(["", "### 높이 색·평면도", ""])
    for path in figures:
        lines.append(f"![{path.stem}](figs/e5_c001_s3ap_fm_retri_rescore/{path.name})")
    lines.extend(["", "### 경계 판독표", "",
        "| 건물 | 등록 | 기계 분류 코드 | 수치 사유 |",
        "|---|---|---|---|",
    ])
    for row in summaries:
        lines.append(
            f"| {row['building_id']} | `{row['registration_class']}` | `{row['numeric_boundary_class']}` | {row['numeric_boundary_reason']} |"
        )
    lines.extend(["", "## 한 줄 관찰", ""])
    lines.append(" · ".join(
        f"{row['building_id'].removeprefix('DEBY_LOD2_')}={row['numeric_boundary_class']}"
        for row in summaries
    ))
    lines.append("")
    return "\n".join(lines)


def wave2() -> None:
    configure_font()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if config["learning_runs_allowed"] != 0 or config["new_mast3r_inference_allowed"] is not False:
        raise RuntimeError("learning/inference lock mismatch")
    registration_rows = read_csv_rows(REG_CSV)
    registration = {row["building_id"].removeprefix("DEBY_LOD2_"): row["registration_class"] for row in registration_rows if row["row_type"] == "building_summary"}
    if set(registration) != set(TARGETS) or any(value == "pending" for value in registration.values()):
        raise RuntimeError(f"registration stop gate incomplete: {registration}")
    old_manifest = json.loads(OLD_MANIFEST.read_text(encoding="utf-8"))
    offset = np.asarray(json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))["world_offset"], dtype=np.float64)
    geoid = float(json.loads(PROJECTION_DATUM.read_text(encoding="utf-8"))["orthometric_geoid_m"])
    lod2, footprints, frames = load_lod2(), load_all_footprints(), load_frames()
    all_footprint_union = make_valid(unary_union(list(footprints.values())))
    sparse = read_points3d_bin(SPARSE_POINTS)[:, :3].astype(np.float64)
    dense = read_ply_xyz_ascii(DENSE_POINTS).astype(np.float64)
    observed = np.concatenate([sparse, dense], axis=0)
    pair_cache = load_cached_pairs(old_manifest)
    pair_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    score_details_by_short: dict[str, list[dict[str, Any]]] = {}
    summary_details: dict[str, dict[str, Any]] = {}
    completed: list[str] = []
    log("wave2_start cached-only all-inside rescore")
    for short in TARGETS:
        footprint = footprints[f"DEBY_LOD2_{short}"]
        ground = estimate_ground(short, footprint, all_footprint_union, observed, offset, config["rescore_lock"]["ground"])
        building_pairs: list[dict[str, Any]] = []
        building_details: list[dict[str, Any]] = []
        for detail in pair_cache[short]:
            row, scored = pair_score_row(
                detail, short, footprint, lod2[short]["RoofSurface"], offset, geoid, ground,
                config["rescore_lock"], registration[short],
            )
            pair_rows.append(row)
            building_pairs.append(row)
            building_details.append(scored)
            atomic_csv(OUT_CSV, [*pair_rows, *summary_rows], RESCORE_FIELDS)
            write_progress("wave2_rescore", completed, f"scored:{short}:rank{detail['rank']}")
            log(
                f"wave2_pair {short} rank={detail['rank']} eligible={row['eligible_summary_pair']} "
                f"inside={row['inside_point_count']} dz={fmt(row['abs_delta_z_median_m'])}"
            )
        summary_row, summary_detail = summary_score_row(
            short, building_pairs, building_details, footprint, lod2[short]["RoofSurface"], offset, geoid,
            ground, config["rescore_lock"], registration[short],
        )
        summary_rows.append(summary_row)
        score_details_by_short[short] = building_details
        summary_details[short] = summary_detail
        atomic_csv(OUT_CSV, [*pair_rows, *summary_rows], RESCORE_FIELDS)
        completed.append(short)
        write_progress("wave2_rescore", completed, f"building_complete:{short}")
        log(
            f"wave2_summary {short} inside={summary_row['inside_point_count']} "
            f"dz={fmt(summary_row['abs_delta_z_median_m'])} coverage={fmt(summary_row['coverage_ratio'])} "
            f"class={summary_row['numeric_boundary_class']}"
        )
    figures: list[Path] = []
    reviews = config["registration_reviews"]
    for short in TARGETS:
        representative = reviews[short]["anchor_view"]
        if representative == "MULTIVIEW_CONSENSUS":
            candidates = [row for row in registration_rows if row["row_type"] == "view" and row["building_id"] == f"DEBY_LOD2_{short}" and row["view_quality_class"] != "frame_clipped_or_too_small"]
            representative = max(candidates, key=lambda row: float(row["roof_clipped_area_px"]))["view_stem"]
        figures.append(score_figure(
            short, representative, frames[representative], score_details_by_short[short], summary_details[short],
            footprints[f"DEBY_LOD2_{short}"], lod2[short]["RoofSurface"], lod2[short]["GroundSurface"], offset, geoid,
        ))
    atomic_text(REPORT, rescore_report(pair_rows, summary_rows, figures))
    write_progress("wave2_rescore", completed, "complete")
    log("wave2_complete")
    source_paths = [
        Path(__file__), CONFIG, REG_CSV, REG_MANIFEST, OLD_MANIFEST, TRAIN_MANIFEST, PROJECTION_DATUM,
        FOOTPRINTS, SPARSE_POINTS, DENSE_POINTS, SPARSE_DIR / "cameras.bin", SPARSE_DIR / "images.bin",
        *sorted(PAIR_DIR.glob("*.npz")), *sorted(LOD2_DIR.glob("*.gml")),
    ]
    output_paths = [OUT_CSV, REPORT, PROGRESS, RUN_LOG, *sorted(FIG_DIR.glob("recog_*.png")), *figures]
    payload = {
        "schema": "jointbuildgs.s3ap.fm_retri_rescore.v1", "created_utc": now(),
        "git_head_at_measurement": git_value("rev-parse", "HEAD"), "branch": git_value("branch", "--show-current"),
        "docker": {"tag": "jointbuildgs-s3ap-mast3r:20260714-f5209af", "image_id": "sha256:89d64b4c7112cc55db0d42d562e2a0208858658c0c67ab1bd48424175c50f501"},
        "learning_runs_started": 0, "new_mast3r_inference_runs": 0,
        "cache_source_run": rel(OLD_RUN), "cached_pair_count": sum(len(value) for value in pair_cache.values()),
        "cached_dlt_survivor_count": sum(len(detail["world"]) for values in pair_cache.values() for detail in values),
        "cache_input_lineage": (
            "cached DLT NPZ inherits the source run's frozen T0-1 oracle-address input crops; "
            "this wave performs no crop selection, matching, inference, or triangulation"
        ),
        "registration_classes": registration, "rescore_lock": config["rescore_lock"],
        "ground_source_quality": {
            "sparse_point_count": len(sparse), "dense_point_count": len(dense),
            "sparse_track_metadata_available": False,
            "note": (
                "ground elevations use observed SfM+dense-init geometry; supplied footprints_aoi geometry "
                "defines target exterior and building exclusions; no LoD2 roof height/plane or ALS elevation; "
                "sparse track lengths and dense native visibility are not claimed"
            ),
        },
        "source_sha256": {rel(path): sha256_file(path) for path in source_paths},
        "output_sha256": {rel(path): sha256_file(path) for path in output_paths},
        "row_count": len(pair_rows) + len(summary_rows), "pair_row_count": len(pair_rows),
        "summary_row_count": len(summary_rows),
        "numeric_boundary_classes": {row["building_id"]: row["numeric_boundary_class"] for row in summary_rows},
        "interpretation_or_verdict": None, "no_seed_or_training_use": True,
    }
    atomic_text(MANIFEST, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["registration", "rescore"], required=True)
    parser.add_argument("--allow-pending", action="store_true")
    args = parser.parse_args()
    if args.phase == "registration":
        wave1(args.allow_pending)
    elif args.phase == "rescore":
        wave2()


if __name__ == "__main__":
    main()

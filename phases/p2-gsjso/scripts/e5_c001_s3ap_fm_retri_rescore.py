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

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in os.sys.path:
    os.sys.path.insert(0, str(REPO))
from src.stage2.colmap_io import read_cameras_bin, read_images_bin  # noqa: E402

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
REG_CSV = REPO / "docs/e5_c001_s3ap_fm_retri_registration.csv"
OUT_CSV = REPO / "docs/e5_c001_s3ap_fm_retri_rescore.csv"
REPORT = REPO / "docs/W_E5_C001_S3Ap_FM재채점_20260715.md"
FIG_DIR = REPO / "docs/figs/e5_c001_s3ap_fm_retri_rescore"
REG_MANIFEST = RUN_DIR / "registration_manifest.json"
MANIFEST = RUN_DIR / "manifest.json"
PROGRESS = RUN_DIR / "progress.json"
RUN_LOG = RUN_DIR / "run.log"

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["registration"], required=True)
    parser.add_argument("--allow-pending", action="store_true")
    args = parser.parse_args()
    if args.phase == "registration":
        wave1(args.allow_pending)


if __name__ == "__main__":
    main()

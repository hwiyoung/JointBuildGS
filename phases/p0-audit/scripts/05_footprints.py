#!/usr/bin/env python3
"""Extract LoD2 ground plans and intersect them with the target scene AOI.

Run from phases/p0-audit/. The host entrypoint re-runs this script inside the P0 tools
container so GDAL/laspy execution stays in the audit toolchain.
"""

from __future__ import annotations

import csv
import json
import math
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np


TASK_ID = "T5"
GROUND = 2
BUILDING = 6


@dataclass
class GroundPlanPart:
    building_id: str
    source_file: str
    part_id: int
    ring: np.ndarray
    area_m2: float
    bbox: tuple[float, float, float, float]


@dataclass
class BuildingStats:
    source_files: set[str] = field(default_factory=set)
    part_count: int = 0
    intersecting_part_count: int = 0
    area_m2: float = 0.0
    min_x: float = math.inf
    min_y: float = math.inf
    max_x: float = -math.inf
    max_y: float = -math.inf

    def add_part(self, part: GroundPlanPart, intersects_aoi: bool) -> None:
        self.source_files.add(part.source_file)
        self.part_count += 1
        self.area_m2 += part.area_m2
        self.min_x = min(self.min_x, part.bbox[0])
        self.min_y = min(self.min_y, part.bbox[1])
        self.max_x = max(self.max_x, part.bbox[2])
        self.max_y = max(self.max_y, part.bbox[3])
        if intersects_aoi:
            self.intersecting_part_count += 1


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))

    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]
    if env.get("SKIP_BUILD") != "1":
        run(compose + ["build", "tools"], cwd=repo, env=env)

    git_commit = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo.parent,
        text=True,
    ).strip()
    run_id = env.get("RUN_ID") or datetime.now().strftime("t5_footprints_%Y%m%d_%H%M%S")

    try:
        run(
            compose
            + [
                "run",
                "-T",
                "--rm",
                "-e",
                "P0_INSIDE_CONTAINER=1",
                "-e",
                f"P0_GIT_COMMIT={git_commit}",
                "-e",
                f"RUN_ID={run_id}",
                "tools",
                "python",
                "/workspace/scripts/05_footprints.py",
                *sys.argv[1:],
            ],
            cwd=repo,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        record_issue(repo, run_id, f"failed with exit code {exc.returncode}")
        raise


def run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    log_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    if log_path:
        with log_path.open("w", encoding="utf-8") as log:
            log.write("+ " + " ".join(cmd) + "\n")
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            log.write(proc.stdout)
            print(proc.stdout, end="", flush=True)
            proc.check_returncode()
            return proc
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, check=True)


def capture(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    return (proc.stdout or proc.stderr).strip()


def record_issue(repo: Path, run_id: str, message: str) -> None:
    issues = repo / "phases/p0-audit/docs/issues.md"
    with issues.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {TASK_ID} LoD2 Footprint Extraction\n\n")
        fh.write(f"- {run_id}: {message}. See runs/{run_id}/logs/.\n")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def gml_id(elem: ET.Element, fallback: str) -> str:
    for key, value in elem.attrib.items():
        if local_name(key) == "id" and value:
            return value
    return fallback


def parse_poslist(text: str) -> np.ndarray:
    values = [float(v) for v in text.split()]
    if len(values) % 3 == 0:
        return np.array(values, dtype=float).reshape((-1, 3))[:, :2]
    if len(values) % 2 == 0:
        return np.array(values, dtype=float).reshape((-1, 2))
    raise ValueError("gml:posList has neither 2D nor 3D coordinate stride")


def ring_area(xy: np.ndarray) -> float:
    x = xy[:, 0]
    y = xy[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def normalize_ring(xy: np.ndarray) -> np.ndarray | None:
    if xy.shape[0] < 4:
        return None
    if not np.all(np.isfinite(xy)):
        return None
    if not np.allclose(xy[0], xy[-1]):
        xy = np.vstack([xy, xy[0]])
    if ring_area(xy) < 0.25:
        return None
    return xy


def epsg25832_numeric_bounds(parts: list[GroundPlanPart]) -> None:
    if not parts:
        raise RuntimeError("No LoD2 GroundSurface ground plans were extracted")
    min_x = min(part.bbox[0] for part in parts)
    min_y = min(part.bbox[1] for part in parts)
    max_x = max(part.bbox[2] for part in parts)
    max_y = max(part.bbox[3] for part in parts)
    if not (100000.0 <= min_x <= max_x <= 900000.0):
        raise AssertionError(f"LoD2 easting bounds are outside EPSG:25832 numeric range: {min_x}, {max_x}")
    if not (5_000_000.0 <= min_y <= max_y <= 6_200_000.0):
        raise AssertionError(
            f"LoD2 northing bounds are outside EPSG:25832 numeric range: {min_y}, {max_y}"
        )


def parse_lod2_ground_plans(lod2_paths: list[Path]) -> list[GroundPlanPart]:
    parts: list[GroundPlanPart] = []
    skipped_no_ground = 0

    for path in lod2_paths:
        fallback_idx = 0
        for _, elem in ET.iterparse(path, events=("end",)):
            if local_name(elem.tag) != "Building":
                continue

            fallback_idx += 1
            building_id = gml_id(elem, f"{path.stem}_{fallback_idx}")
            part_id = 0

            for surface in elem.iter():
                if local_name(surface.tag) != "GroundSurface":
                    continue

                poslist = None
                for child in surface.iter():
                    if local_name(child.tag) == "posList" and child.text:
                        poslist = child.text
                        break
                if not poslist:
                    continue

                xy = normalize_ring(parse_poslist(poslist))
                if xy is None:
                    continue

                part_id += 1
                bbox = (
                    float(np.min(xy[:, 0])),
                    float(np.min(xy[:, 1])),
                    float(np.max(xy[:, 0])),
                    float(np.max(xy[:, 1])),
                )
                parts.append(
                    GroundPlanPart(
                        building_id=building_id,
                        source_file=path.name,
                        part_id=part_id,
                        ring=xy,
                        area_m2=ring_area(xy),
                        bbox=bbox,
                    )
                )

            if part_id == 0:
                skipped_no_ground += 1
            elem.clear()

    if skipped_no_ground:
        print(f"warning: buildings without usable GroundSurface rings: {skipped_no_ground}")
    epsg25832_numeric_bounds(parts)
    return parts


def sample_scene_points(laz_path: Path, max_points: int = 500_000) -> np.ndarray:
    import laspy

    chunks: list[np.ndarray] = []
    with laspy.open(laz_path) as fh:
        for points in fh.chunk_iterator(1_000_000):
            x = np.asarray(points.x)
            y = np.asarray(points.y)
            if hasattr(points, "classification"):
                cls = np.asarray(points.classification, dtype=np.uint8)
                mask = (cls == GROUND) | (cls == BUILDING)
                if np.count_nonzero(mask) >= 100:
                    x = x[mask]
                    y = y[mask]
            if x.size == 0:
                continue
            keep = min(x.size, 15_000)
            if x.size > keep:
                idx = np.linspace(0, x.size - 1, keep, dtype=np.int64)
                x = x[idx]
                y = y[idx]
            chunks.append(np.column_stack([x, y]))

    if not chunks:
        raise RuntimeError(f"No sampleable points found in {laz_path}")

    samples = np.vstack(chunks)
    if samples.shape[0] > max_points:
        idx = np.linspace(0, samples.shape[0] - 1, max_points, dtype=np.int64)
        samples = samples[idx]
    return samples


def scene_aoi_from_laz(laz_path: Path, margin_m: float = 25.0) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    samples = sample_scene_points(laz_path)
    min_x, max_x = np.percentile(samples[:, 0], [1.0, 99.0])
    min_y, max_y = np.percentile(samples[:, 1], [1.0, 99.0])
    min_x = float(min_x - margin_m)
    max_x = float(max_x + margin_m)
    min_y = float(min_y - margin_m)
    max_y = float(max_y + margin_m)
    ring = np.array(
        [
            [min_x, min_y],
            [max_x, min_y],
            [max_x, max_y],
            [min_x, max_y],
            [min_x, min_y],
        ],
        dtype=float,
    )
    return ring, (min_x, min_y, max_x, max_y)


def bbox_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def point_in_rect(point: np.ndarray, rect: tuple[float, float, float, float]) -> bool:
    return rect[0] <= point[0] <= rect[2] and rect[1] <= point[1] <= rect[3]


def point_in_polygon(point: tuple[float, float], ring: np.ndarray) -> bool:
    x, y = point
    inside = False
    n = ring.shape[0]
    for idx in range(n - 1):
        x1, y1 = ring[idx]
        x2, y2 = ring[idx + 1]
        if ((y1 > y) != (y2 > y)) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def orientation(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def on_segment(a: np.ndarray, b: np.ndarray, c: np.ndarray, eps: float = 1e-9) -> bool:
    return (
        min(a[0], c[0]) - eps <= b[0] <= max(a[0], c[0]) + eps
        and min(a[1], c[1]) - eps <= b[1] <= max(a[1], c[1]) + eps
        and abs(orientation(a, b, c)) <= eps
    )


def segments_intersect(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> bool:
    o1 = orientation(a, b, c)
    o2 = orientation(a, b, d)
    o3 = orientation(c, d, a)
    o4 = orientation(c, d, b)
    if o1 * o2 < 0.0 and o3 * o4 < 0.0:
        return True
    return on_segment(a, c, b) or on_segment(a, d, b) or on_segment(c, a, d) or on_segment(c, b, d)


def polygon_intersects_rect(ring: np.ndarray, bbox: tuple[float, float, float, float]) -> bool:
    poly_bbox = (
        float(np.min(ring[:, 0])),
        float(np.min(ring[:, 1])),
        float(np.max(ring[:, 0])),
        float(np.max(ring[:, 1])),
    )
    if not bbox_overlap(poly_bbox, bbox):
        return False
    if any(point_in_rect(point, bbox) for point in ring[:-1]):
        return True

    min_x, min_y, max_x, max_y = bbox
    corners = [
        np.array([min_x, min_y], dtype=float),
        np.array([max_x, min_y], dtype=float),
        np.array([max_x, max_y], dtype=float),
        np.array([min_x, max_y], dtype=float),
    ]
    if any(point_in_polygon((float(corner[0]), float(corner[1])), ring) for corner in corners):
        return True

    rect_edges = list(zip(corners, corners[1:] + corners[:1]))
    for idx in range(ring.shape[0] - 1):
        a = ring[idx]
        b = ring[idx + 1]
        if any(segments_intersect(a, b, c, d) for c, d in rect_edges):
            return True
    return False


def write_geojson(parts: list[GroundPlanPart], out_path: Path) -> None:
    features = []
    for part in parts:
        coords = [[round(float(x), 3), round(float(y), 3)] for x, y in part.ring]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "building_id": part.building_id,
                    "source_file": part.source_file,
                    "part_id": part.part_id,
                    "area_m2": round(part.area_m2, 3),
                    "min_x": round(part.bbox[0], 3),
                    "min_y": round(part.bbox[1], 3),
                    "max_x": round(part.bbox[2], 3),
                    "max_y": round(part.bbox[3], 3),
                },
                "geometry": {"type": "Polygon", "coordinates": [coords]},
            }
        )
    out_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")),
        encoding="utf-8",
    )


def write_scene_aoi_geojson(ring: np.ndarray, bbox: tuple[float, float, float, float], out_path: Path) -> None:
    coords = [[round(float(x), 3), round(float(y), 3)] for x, y in ring]
    feature = {
        "type": "Feature",
        "properties": {
            "name": "scene_aoi",
            "crs": "EPSG:25832",
            "min_x": round(bbox[0], 3),
            "min_y": round(bbox[1], 3),
            "max_x": round(bbox[2], 3),
            "max_y": round(bbox[3], 3),
        },
        "geometry": {"type": "Polygon", "coordinates": [coords]},
    }
    out_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": [feature]}, separators=(",", ":")),
        encoding="utf-8",
    )


def convert_geojson_to_gpkg(src: Path, dst: Path, layer: str, log_path: Path) -> None:
    if dst.exists():
        dst.unlink()
    run(
        [
            "ogr2ogr",
            "-f",
            "GPKG",
            "-a_srs",
            "EPSG:25832",
            str(dst),
            str(src),
            "-nln",
            layer,
            "-lco",
            "GEOMETRY_NAME=geom",
        ],
        log_path=log_path,
    )


def write_intersection_csv(
    parts: list[GroundPlanPart],
    aoi_bbox: tuple[float, float, float, float],
    out_csv: Path,
) -> tuple[dict[str, BuildingStats], list[tuple[str, BuildingStats]]]:
    stats: dict[str, BuildingStats] = defaultdict(BuildingStats)
    for part in parts:
        intersects = polygon_intersects_rect(part.ring, aoi_bbox)
        stats[part.building_id].add_part(part, intersects)

    rows = sorted(
        [(building_id, item) for building_id, item in stats.items() if item.intersecting_part_count],
        key=lambda item: item[0],
    )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "building_id",
                "source_files",
                "part_count",
                "intersecting_part_count",
                "area_m2",
                "min_x",
                "min_y",
                "max_x",
                "max_y",
            ]
        )
        for building_id, item in rows:
            writer.writerow(
                [
                    building_id,
                    ";".join(sorted(item.source_files)),
                    item.part_count,
                    item.intersecting_part_count,
                    f"{item.area_m2:.3f}",
                    f"{item.min_x:.3f}",
                    f"{item.min_y:.3f}",
                    f"{item.max_x:.3f}",
                    f"{item.max_y:.3f}",
                ]
            )
    return stats, rows


def write_versions(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# T5 Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {os.environ['RUN_ID']}",
        f"- Repository commit: {os.environ.get('P0_GIT_COMMIT', 'unknown')}",
        "",
        "```console",
    ]
    for cmd in (
        ["python", "--version"],
        ["ogr2ogr", "--version"],
        ["ogrinfo", "--version"],
        [
            "python",
            "-c",
            "import laspy, numpy; print('laspy ' + laspy.__version__); print('numpy ' + numpy.__version__)",
        ],
    ):
        lines.append("$ " + " ".join(cmd))
        lines.append(capture(cmd))
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_config(run_dir: Path, values: dict[str, str | int | float]) -> None:
    lines = ["task: T5_lod2_footprints"]
    for key, value in values.items():
        lines.append(f"{key}: {value}")
    (run_dir / "config.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(
    summary_path: Path,
    run_id: str,
    run_dir: Path,
    lod2_paths: list[Path],
    ground_plan_gpkg: Path,
    scene_aoi_gpkg: Path,
    csv_path: Path,
    building_count: int,
    part_count: int,
    intersecting_count: int,
    aoi_bbox: tuple[float, float, float, float],
    footprint_bounds: tuple[float, float, float, float],
    ground_info: str,
    aoi_info: str,
) -> None:
    rel = lambda path: path.as_posix().replace("/workspace/", "")
    summary_path.write_text(
        "\n".join(
            [
                "# T5 LoD2 Footprint Extraction",
                "",
                f"- Run ID: {run_id}",
                f"- Run directory: {rel(run_dir)}",
                f"- LoD2 source files: {', '.join(path.name for path in lod2_paths)}",
                "- CRS assertion: EPSG:25832 numeric bounds PASS",
                f"- Ground plan GPKG: {rel(ground_plan_gpkg)}",
                f"- Scene AOI GPKG: {rel(scene_aoi_gpkg)}",
                f"- Scene AOI intersecting buildings CSV: {rel(csv_path)}",
                f"- Buildings with usable LoD2 GroundSurface: {building_count:,}",
                f"- Ground plan polygon parts: {part_count:,}",
                f"- Buildings intersecting scene AOI: {intersecting_count:,}",
                (
                    "- Ground plan bounds: "
                    f"x=[{footprint_bounds[0]:.3f}, {footprint_bounds[2]:.3f}], "
                    f"y=[{footprint_bounds[1]:.3f}, {footprint_bounds[3]:.3f}]"
                ),
                (
                    "- Scene AOI bounds: "
                    f"x=[{aoi_bbox[0]:.3f}, {aoi_bbox[2]:.3f}], "
                    f"y=[{aoi_bbox[1]:.3f}, {aoi_bbox[3]:.3f}]"
                ),
                f"- Run config: {rel(run_dir / 'config.yaml')}",
                f"- Run versions: {rel(run_dir / 'versions.txt')}",
                "",
                "## ogrinfo ground plan",
                "",
                "```console",
                ground_info,
                "```",
                "",
                "## ogrinfo scene AOI",
                "",
                "```console",
                aoi_info,
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    root = Path("/workspace")
    data = root / "data"
    docs = root / "docs"
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    log_dir = run_dir / "logs"
    work_dir = data / "work/footprints"

    lod2_paths = sorted((data / "raw/lod2").glob("*.gml"))
    classified_laz = data / "work/classify/dim_v1_classified.laz"
    dim_laz = data / "work/mvs/dim/dim_v1.laz"
    scene_laz = classified_laz if classified_laz.exists() else dim_laz

    ground_plan_geojson = work_dir / "lod2_ground_plan.geojson"
    ground_plan_gpkg = work_dir / "lod2_ground_plan.gpkg"
    scene_aoi_geojson = work_dir / "scene_aoi.geojson"
    scene_aoi_gpkg = work_dir / "scene_aoi.gpkg"
    csv_path = docs / "scene_aoi_buildings.csv"
    summary_path = docs / "footprints_summary.md"

    if not lod2_paths:
        raise FileNotFoundError(data / "raw/lod2")
    if not scene_laz.exists():
        raise FileNotFoundError("Expected data/work/classify/dim_v1_classified.laz or data/work/mvs/dim/dim_v1.laz")

    log_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    write_versions(run_dir)

    aoi_ring, aoi_bbox = scene_aoi_from_laz(scene_laz)
    parts = parse_lod2_ground_plans(lod2_paths)
    footprint_bounds = (
        min(part.bbox[0] for part in parts),
        min(part.bbox[1] for part in parts),
        max(part.bbox[2] for part in parts),
        max(part.bbox[3] for part in parts),
    )

    write_geojson(parts, ground_plan_geojson)
    write_scene_aoi_geojson(aoi_ring, aoi_bbox, scene_aoi_geojson)
    convert_geojson_to_gpkg(
        ground_plan_geojson,
        ground_plan_gpkg,
        "lod2_ground_plan",
        log_dir / "ogr2ogr_lod2_ground_plan.log",
    )
    convert_geojson_to_gpkg(
        scene_aoi_geojson,
        scene_aoi_gpkg,
        "scene_aoi",
        log_dir / "ogr2ogr_scene_aoi.log",
    )

    stats, intersecting_rows = write_intersection_csv(parts, aoi_bbox, csv_path)
    ground_info = capture(["ogrinfo", "-so", str(ground_plan_gpkg), "lod2_ground_plan"])
    aoi_info = capture(["ogrinfo", "-so", str(scene_aoi_gpkg), "scene_aoi"])

    write_config(
        run_dir,
        {
            "run_id": run_id,
            "input_lod2_dir": "data/raw/lod2",
            "scene_laz": scene_laz.as_posix().replace("/workspace/", ""),
            "ground_plan_gpkg": "data/work/footprints/lod2_ground_plan.gpkg",
            "scene_aoi_gpkg": "data/work/footprints/scene_aoi.gpkg",
            "intersecting_buildings_csv": "docs/scene_aoi_buildings.csv",
            "building_count": len(stats),
            "ground_plan_part_count": len(parts),
            "intersecting_building_count": len(intersecting_rows),
            "scene_aoi_min_x": f"{aoi_bbox[0]:.3f}",
            "scene_aoi_min_y": f"{aoi_bbox[1]:.3f}",
            "scene_aoi_max_x": f"{aoi_bbox[2]:.3f}",
            "scene_aoi_max_y": f"{aoi_bbox[3]:.3f}",
        },
    )
    write_summary(
        summary_path=summary_path,
        run_id=run_id,
        run_dir=run_dir,
        lod2_paths=lod2_paths,
        ground_plan_gpkg=ground_plan_gpkg,
        scene_aoi_gpkg=scene_aoi_gpkg,
        csv_path=csv_path,
        building_count=len(stats),
        part_count=len(parts),
        intersecting_count=len(intersecting_rows),
        aoi_bbox=aoi_bbox,
        footprint_bounds=footprint_bounds,
        ground_info=ground_info,
        aoi_info=aoi_info,
    )

    print(f"building_count={len(stats)}")
    print(f"ground_plan_part_count={len(parts)}")
    print(f"scene_aoi_intersecting_buildings={len(intersecting_rows)}")
    print(f"ground_plan_gpkg={ground_plan_gpkg}")
    print(f"scene_aoi_gpkg={scene_aoi_gpkg}")
    print(f"intersecting_csv={csv_path}")
    print(f"summary={summary_path}")


if __name__ == "__main__":
    if os.environ.get("P0_INSIDE_CONTAINER") != "1":
        host_entrypoint()
    else:
        main()

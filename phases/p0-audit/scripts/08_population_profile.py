#!/usr/bin/env python3
"""T8 evaluation-population profile for P0 audit buildings.

Run from phases/p0-audit/. Host mode re-runs this script inside the P0 tools
container so GDAL/XML/numeric processing stays in the recorded audit toolchain.
"""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import numpy as np


TASK_ID = "T8"
CANONICAL_RUN = "w3_2b_roofer_repeatability_20260612_220747/run_2"
STATUS_CSV = "docs/W3_2c_canonical_paired_status.csv"
FOOTPRINT_GPKG = "data/work/footprints/lod2_ground_plan.gpkg"
FOOTPRINT_LAYER = "lod2_ground_plan"
FAILURE_BUCKET = "roof_matching_assembly_failure"


@dataclass
class BuildingGeometry:
    building_id: str
    area_m2: float = 0.0
    perimeter_m: float = 0.0
    exterior_vertex_count: int = 0
    part_count: int = 0
    min_x: float = math.inf
    min_y: float = math.inf
    max_x: float = -math.inf
    max_y: float = -math.inf

    def add_part(self, ring: np.ndarray, area_m2: float | None = None) -> None:
        if ring.shape[0] < 4:
            return
        if not np.allclose(ring[0], ring[-1]):
            ring = np.vstack([ring, ring[0]])
        part_area = ring_area(ring) if area_m2 is None else float(area_m2)
        self.area_m2 += part_area
        self.perimeter_m += ring_perimeter(ring)
        self.exterior_vertex_count += int(max(ring.shape[0] - 1, 0))
        self.part_count += 1
        self.min_x = min(self.min_x, float(np.min(ring[:, 0])))
        self.min_y = min(self.min_y, float(np.min(ring[:, 1])))
        self.max_x = max(self.max_x, float(np.max(ring[:, 0])))
        self.max_y = max(self.max_y, float(np.max(ring[:, 1])))


@dataclass
class HeightStats:
    source_files: set[str] = field(default_factory=set)
    z_min: float = math.inf
    z_max: float = -math.inf
    coordinate_count: int = 0

    def add(self, z_values: np.ndarray, source_file: str) -> None:
        if z_values.size == 0:
            return
        self.source_files.add(source_file)
        self.z_min = min(self.z_min, float(np.min(z_values)))
        self.z_max = max(self.z_max, float(np.max(z_values)))
        self.coordinate_count += int(z_values.size)

    @property
    def height_m(self) -> float:
        if not np.isfinite(self.z_min) or not np.isfinite(self.z_max):
            return math.nan
        return self.z_max - self.z_min


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("t8_population_profile_%Y%m%d_%H%M%S")
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
        run(
            compose
            + [
                "run",
                "-T",
                "--rm",
                "-e",
                "P0_INSIDE_CONTAINER=1",
                "-e",
                f"RUN_ID={run_id}",
                "-e",
                f"P0_GIT_COMMIT={git_commit}",
                "tools",
                "python",
                "/workspace/scripts/08_population_profile.py",
                "--mode",
                "compute",
            ],
            cwd=repo,
            env=env,
            log_path=logs_dir / "compute.log",
        )
    except subprocess.CalledProcessError as exc:
        record_issue(repo, run_id, f"failed with exit code {exc.returncode}")
        raise

    print(f"run_id={run_id}")
    print(f"run_dir=runs/{run_id}")
    print("report=docs/W4b_population_profile.md")


def compute_entrypoint() -> None:
    root = Path("/workspace")
    docs = root / "docs"
    data = root / "data"
    figs = docs / "figs"
    package = docs / "G1_package"
    package_figs = package / "figs"
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    scratch_dir = run_dir / "scratch"
    run_dir.mkdir(parents=True, exist_ok=True)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)

    status_rows = read_csv(root / STATUS_CSV)
    populations = derive_populations(status_rows)
    target_ids = set(populations["full_199"])

    footprint_gpkg = root / FOOTPRINT_GPKG
    assert_gpkg_epsg25832(footprint_gpkg, FOOTPRINT_LAYER)
    footprint_geojson = scratch_dir / "lod2_ground_plan.geojson"
    convert_gpkg_to_geojson(footprint_gpkg, footprint_geojson, FOOTPRINT_LAYER)
    geometries = load_footprint_metrics(footprint_geojson, target_ids)
    assert_epsg25832_geometries(geometries)

    lod2_paths = sorted((data / "raw/lod2").glob("*.gml"))
    if not lod2_paths:
        raise FileNotFoundError("No LoD2 CityGML files found under data/raw/lod2")
    heights = parse_lod2_heights(lod2_paths, target_ids)

    paired_by_id = {row["building_id"]: row for row in status_rows}
    metric_rows = build_metric_rows(populations, paired_by_id, geometries, heights)
    summary_rows = build_summary_rows(metric_rows, populations)
    summary_display_rows = build_summary_display_rows(summary_rows)
    observation_rows = build_observation_rows(metric_rows, populations)
    cluster_observation = describe_failure_cluster(metric_rows, populations)
    control_observation = describe_control_representativeness(metric_rows, populations)

    metrics_csv = docs / "W4b_population_profile_building_metrics.csv"
    summary_csv = docs / "W4b_population_profile_summary.csv"
    metrics_json = data / "work/diagnose/t8_population_profile_metrics.json"
    scatter_fig = figs / "w4b_population_size_complexity.png"
    report_md = docs / "W4b_population_profile.md"

    write_csv(metrics_csv, [format_metric_row(row) for row in metric_rows])
    write_csv(summary_csv, summary_rows)
    write_metrics_json(metrics_json, run_id, populations, metric_rows, summary_rows, cluster_observation)
    render_size_complexity_scatter(scatter_fig, metric_rows, populations)
    write_report(
        report_md,
        run_id,
        run_dir,
        metrics_csv,
        summary_csv,
        metrics_json,
        scatter_fig,
        summary_display_rows,
        observation_rows,
        cluster_observation,
        control_observation,
    )
    add_to_g1_package(package, package_figs, report_md, metrics_csv, summary_csv, scatter_fig)
    copy_outputs(
        run_dir,
        [
            report_md,
            metrics_csv,
            summary_csv,
            metrics_json,
            scatter_fig,
            package / "W4b_population_profile.md",
            package / "w4b_population_profile_building_metrics.csv",
            package / "w4b_population_profile_summary.csv",
            package_figs / "fig_12_w4b_population_size_complexity.png",
            package / "manifest.json",
        ],
    )

    print(f"full_199_n={len(populations['full_199'])}")
    print(f"control_93_n={len(populations['control_93'])}")
    print(f"failure_8_n={len(populations['failure_8'])}")
    print(cluster_observation)
    print(f"report={rel(report_md)}")
    print(f"scatter={rel(scatter_fig)}")


def derive_populations(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    full_ids = [row["building_id"] for row in rows]
    control_ids = [row["building_id"] for row in rows if row["coverage_control_population"] == "yes"]
    failure_ids = [
        row["building_id"]
        for row in rows
        if row["coverage_control_population"] == "yes" and row["dim_failure_bucket_v1"] == FAILURE_BUCKET
    ]
    if len(full_ids) != 199:
        raise RuntimeError(f"Expected 199 canonical buildings, got {len(full_ids)}")
    if len(control_ids) != 93:
        raise RuntimeError(f"Expected 93 coverage-control buildings, got {len(control_ids)}")
    if len(failure_ids) != 8:
        raise RuntimeError(f"Expected 8 DIM reconstruction failures, got {len(failure_ids)}")
    return {
        "full_199": full_ids,
        "control_93": control_ids,
        "failure_8": failure_ids,
    }


def convert_gpkg_to_geojson(gpkg_path: Path, geojson_path: Path, layer: str) -> None:
    if geojson_path.exists():
        geojson_path.unlink()
    run(
        [
            "ogr2ogr",
            "-f",
            "GeoJSON",
            str(geojson_path),
            str(gpkg_path),
            layer,
        ],
        cwd=Path("/workspace"),
    )


def assert_gpkg_epsg25832(gpkg_path: Path, layer: str) -> None:
    if not gpkg_path.exists():
        raise FileNotFoundError(gpkg_path)
    text = capture(["ogrinfo", "-al", "-so", str(gpkg_path), layer], cwd=Path("/workspace"))
    accepted = "25832" in text or "ETRS89" in text.upper() or "UTM ZONE 32" in text.upper()
    if not accepted:
        raise AssertionError(f"Footprint GPKG CRS is not tagged as EPSG:25832/ETRS89 UTM32: {gpkg_path}")


def load_footprint_metrics(path: Path, target_ids: set[str]) -> dict[str, BuildingGeometry]:
    data = read_json(path)
    output = {bid: BuildingGeometry(building_id=bid) for bid in target_ids}
    for feature in data["features"]:
        props = feature.get("properties", {})
        bid = props.get("building_id")
        if bid not in target_ids:
            continue
        area_m2 = float(props["area_m2"]) if props.get("area_m2") not in (None, "") else None
        for ring in exterior_rings(feature.get("geometry", {})):
            output[bid].add_part(ring, area_m2)
            area_m2 = None
    missing = sorted(bid for bid, geom in output.items() if geom.part_count == 0)
    if missing:
        raise RuntimeError(f"Missing footprint geometry for {len(missing)} buildings: {', '.join(missing[:10])}")
    return output


def exterior_rings(geometry: dict[str, Any]) -> list[np.ndarray]:
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")
    rings: list[np.ndarray] = []
    if geom_type == "Polygon":
        if coords:
            rings.append(np.array([[float(pt[0]), float(pt[1])] for pt in coords[0]], dtype=np.float64))
    elif geom_type == "MultiPolygon":
        for poly in coords or []:
            if poly:
                rings.append(np.array([[float(pt[0]), float(pt[1])] for pt in poly[0]], dtype=np.float64))
    else:
        raise RuntimeError(f"Unsupported footprint geometry type: {geom_type}")
    return rings


def assert_epsg25832_geometries(geometries: dict[str, BuildingGeometry]) -> None:
    xs = np.array([value for geom in geometries.values() for value in (geom.min_x, geom.max_x)], dtype=np.float64)
    ys = np.array([value for geom in geometries.values() for value in (geom.min_y, geom.max_y)], dtype=np.float64)
    if not np.all((100000.0 <= xs) & (xs <= 900000.0)):
        raise AssertionError("Footprint easting values are outside UTM zone 32 numeric range")
    if not np.all((5_000_000.0 <= ys) & (ys <= 6_200_000.0)):
        raise AssertionError("Footprint northing values are outside Germany UTM northing range")


def parse_lod2_heights(paths: list[Path], target_ids: set[str]) -> dict[str, HeightStats]:
    heights = {bid: HeightStats() for bid in target_ids}
    for path in paths:
        fallback_idx = 0
        for _, elem in ET.iterparse(path, events=("end",)):
            if local_name(elem.tag) != "Building":
                continue
            fallback_idx += 1
            bid = gml_id(elem, f"{path.stem}_{fallback_idx}")
            if bid in target_ids:
                z_values: list[np.ndarray] = []
                for child in elem.iter():
                    if local_name(child.tag) == "posList" and child.text:
                        coords = parse_poslist_3d(child.text)
                        if coords is not None:
                            z_values.append(coords[:, 2])
                if z_values:
                    heights[bid].add(np.concatenate(z_values), path.name)
            elem.clear()
    missing = sorted(bid for bid, stats in heights.items() if not np.isfinite(stats.height_m))
    if missing:
        raise RuntimeError(f"Missing LoD2 height for {len(missing)} buildings: {', '.join(missing[:10])}")
    return heights


def build_metric_rows(
    populations: dict[str, list[str]],
    paired_by_id: dict[str, dict[str, str]],
    geometries: dict[str, BuildingGeometry],
    heights: dict[str, HeightStats],
) -> list[dict[str, Any]]:
    control_ids = set(populations["control_93"])
    failure_ids = set(populations["failure_8"])
    rows: list[dict[str, Any]] = []
    for bid in populations["full_199"]:
        geom = geometries[bid]
        height = heights[bid]
        status = paired_by_id[bid]
        rows.append(
            {
                "building_id": bid,
                "in_full_199": True,
                "in_control_93": bid in control_ids,
                "in_failure_8": bid in failure_ids,
                "paired_category": status.get("paired_category", ""),
                "coverage_control_population": status.get("coverage_control_population", ""),
                "dim_failure_bucket_v1": status.get("dim_failure_bucket_v1", ""),
                "floor_area_m2": geom.area_m2,
                "perimeter_m": geom.perimeter_m,
                "exterior_vertex_count": float(geom.exterior_vertex_count),
                "part_count": geom.part_count,
                "height_m": height.height_m,
                "height_source_files": ",".join(sorted(height.source_files)),
                "height_coordinate_count": height.coordinate_count,
            }
        )
    return rows


def build_summary_rows(metric_rows: list[dict[str, Any]], populations: dict[str, list[str]]) -> list[dict[str, str]]:
    by_id = {row["building_id"]: row for row in metric_rows}
    output: list[dict[str, str]] = []
    metric_specs = [
        ("floor_area_m2", "area_m2"),
        ("perimeter_m", "perimeter_m"),
        ("exterior_vertex_count", "exterior_vertex_count"),
        ("height_m", "height_m"),
    ]
    for population, ids in populations.items():
        row: dict[str, str] = {"population": population, "n_buildings": str(len(ids))}
        pop_rows = [by_id[bid] for bid in ids]
        for key, prefix in metric_specs:
            values = np.array([item[key] for item in pop_rows if np.isfinite(float(item[key]))], dtype=np.float64)
            if values.size:
                p25 = float(np.percentile(values, 25.0))
                p75 = float(np.percentile(values, 75.0))
                row[f"{prefix}_n"] = str(values.size)
                row[f"{prefix}_median"] = fmt(float(np.median(values)), 3)
                row[f"{prefix}_p25"] = fmt(p25, 3)
                row[f"{prefix}_p75"] = fmt(p75, 3)
                row[f"{prefix}_iqr"] = fmt(p75 - p25, 3)
            else:
                row[f"{prefix}_n"] = "0"
                row[f"{prefix}_median"] = "n/a"
                row[f"{prefix}_p25"] = "n/a"
                row[f"{prefix}_p75"] = "n/a"
                row[f"{prefix}_iqr"] = "n/a"
        output.append(row)
    return output


def build_summary_display_rows(summary_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in summary_rows:
        output.append(
            {
                "population": row["population"],
                "n": row["n_buildings"],
                "area_m2_median_iqr": format_median_iqr(row, "area_m2"),
                "perimeter_m_median_iqr": format_median_iqr(row, "perimeter_m"),
                "complexity_vertices_median_iqr": format_median_iqr(row, "exterior_vertex_count"),
                "height_m_median_iqr": format_median_iqr(row, "height_m"),
            }
        )
    return output


def build_observation_rows(metric_rows: list[dict[str, Any]], populations: dict[str, list[str]]) -> list[dict[str, str]]:
    by_id = {row["building_id"]: row for row in metric_rows}
    output = []
    for bid in populations["failure_8"]:
        row = by_id[bid]
        output.append(
            {
                "building_id": bid,
                "area_m2": fmt(row["floor_area_m2"], 2),
                "perimeter_m": fmt(row["perimeter_m"], 2),
                "exterior_vertices": str(int(row["exterior_vertex_count"])),
                "height_m": fmt(row["height_m"], 2),
                "dim_failure_bucket_v1": row["dim_failure_bucket_v1"],
            }
        )
    return output


def describe_failure_cluster(metric_rows: list[dict[str, Any]], populations: dict[str, list[str]]) -> str:
    by_id = {row["building_id"]: row for row in metric_rows}
    control = [by_id[bid] for bid in populations["control_93"]]
    failure = [by_id[bid] for bid in populations["failure_8"]]
    control_area_p25, control_area_p75 = percentile_pair(control, "floor_area_m2")
    control_vertices_p25, control_vertices_p75 = percentile_pair(control, "exterior_vertex_count")
    failure_area_median = median(failure, "floor_area_m2")
    failure_vertices_median = median(failure, "exterior_vertex_count")
    control_area_median = median(control, "floor_area_m2")
    control_vertices_median = median(control, "exterior_vertex_count")
    inside_iqr = sum(
        control_area_p25 <= row["floor_area_m2"] <= control_area_p75
        and control_vertices_p25 <= row["exterior_vertex_count"] <= control_vertices_p75
        for row in failure
    )
    area_ratio = safe_ratio(failure_area_median, control_area_median)
    vertex_ratio = safe_ratio(failure_vertices_median, control_vertices_median)
    if inside_iqr >= 6:
        pattern = "통제 93의 중심 분포와 겹쳐 뚜렷한 별도 군집은 약하다"
    elif failure_area_median < control_area_p25 and failure_vertices_median < control_vertices_p25:
        pattern = "통제 93보다 작은 면적·단순 형상 쪽에 치우친 군집이 관찰된다"
    elif failure_area_median < control_area_p25 and control_vertices_p25 <= failure_vertices_median <= control_vertices_p75:
        pattern = "면적은 통제 IQR보다 작고 복잡도는 통제 IQR 내부라 소형 건물 쪽 치우침은 있으나 크기-복잡도 동시 군집은 제한적이다"
    elif failure_area_median > control_area_p75 and failure_vertices_median > control_vertices_p75:
        pattern = "통제 93보다 큰 면적·복잡 형상 쪽에 치우친 군집이 관찰된다"
    else:
        pattern = "일부는 통제 IQR을 벗어나지만 단일 크기-복잡도 군집은 약하다"
    return (
        f"실패 8동은 면적-복잡도 기준 통제 93 IQR 내부가 {inside_iqr}/8이고, "
        f"중앙값 비율은 면적 {area_ratio:.2f}배·꼭짓점 {vertex_ratio:.2f}배로 {pattern}."
    )


def describe_control_representativeness(metric_rows: list[dict[str, Any]], populations: dict[str, list[str]]) -> str:
    by_id = {row["building_id"]: row for row in metric_rows}
    full = [by_id[bid] for bid in populations["full_199"]]
    control = [by_id[bid] for bid in populations["control_93"]]
    ratios = {
        "면적": safe_ratio(median(control, "floor_area_m2"), median(full, "floor_area_m2")),
        "꼭짓점": safe_ratio(median(control, "exterior_vertex_count"), median(full, "exterior_vertex_count")),
        "높이": safe_ratio(median(control, "height_m"), median(full, "height_m")),
    }
    return (
        "통제 93/전체 199 중앙값 비율은 "
        + ", ".join(f"{name} {value:.2f}배" for name, value in ratios.items())
        + "로 기록된다."
    )


def percentile_pair(rows: list[dict[str, Any]], key: str) -> tuple[float, float]:
    values = np.array([row[key] for row in rows if np.isfinite(float(row[key]))], dtype=np.float64)
    if values.size == 0:
        return math.nan, math.nan
    return float(np.percentile(values, 25.0)), float(np.percentile(values, 75.0))


def median(rows: list[dict[str, Any]], key: str) -> float:
    values = np.array([row[key] for row in rows if np.isfinite(float(row[key]))], dtype=np.float64)
    return float(np.median(values)) if values.size else math.nan


def safe_ratio(numerator: float, denominator: float) -> float:
    if not np.isfinite(numerator) or not np.isfinite(denominator) or abs(denominator) < 1e-12:
        return math.nan
    return numerator / denominator


def write_metrics_json(
    path: Path,
    run_id: str,
    populations: dict[str, list[str]],
    metric_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, str]],
    cluster_observation: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "task_id": TASK_ID,
        "canonical_run": CANONICAL_RUN,
        "crs": "EPSG:25832 numeric UTM32 for T5 footprint GPKG and LoD2 CityGML coordinates",
        "population_counts": {key: len(value) for key, value in populations.items()},
        "failure_bucket": FAILURE_BUCKET,
        "cluster_observation": cluster_observation,
        "summary": summary_rows,
        "rows": sanitize_json(metric_rows),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_size_complexity_scatter(
    out_path: Path,
    metric_rows: list[dict[str, Any]],
    populations: dict[str, list[str]],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    by_id = {row["building_id"]: row for row in metric_rows}
    full = [by_id[bid] for bid in populations["full_199"]]
    control = [by_id[bid] for bid in populations["control_93"]]
    failure = [by_id[bid] for bid in populations["failure_8"]]

    fig, ax = plt.subplots(figsize=(8.0, 5.6), constrained_layout=True)
    ax.scatter(
        [row["floor_area_m2"] for row in full],
        [row["exterior_vertex_count"] for row in full],
        s=18,
        color="#c7c7c7",
        alpha=0.55,
        linewidths=0,
        label="Full 199",
    )
    ax.scatter(
        [row["floor_area_m2"] for row in control],
        [row["exterior_vertex_count"] for row in control],
        s=38,
        facecolors="none",
        edgecolors="#2f6fbb",
        linewidths=1.0,
        alpha=0.9,
        label="Control 93",
    )
    ax.scatter(
        [row["floor_area_m2"] for row in failure],
        [row["exterior_vertex_count"] for row in failure],
        s=82,
        marker="*",
        color="#d62728",
        edgecolors="#7f1d1d",
        linewidths=0.6,
        label="Failure 8",
        zorder=5,
    )
    for row in failure:
        ax.annotate(
            row["building_id"].replace("DEBY_LOD2_", ""),
            (row["floor_area_m2"], row["exterior_vertex_count"]),
            textcoords="offset points",
            xytext=(4, 4),
            fontsize=7,
            color="#7f1d1d",
        )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Footprint area (m2, log scale)")
    ax.set_ylabel("Exterior vertex count (log scale)")
    ax.set_title("T8 evaluation population: size vs shape complexity")
    ax.grid(True, linewidth=0.3, alpha=0.35)
    ax.legend(loc="best", frameon=True)
    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def write_report(
    out_path: Path,
    run_id: str,
    run_dir: Path,
    metrics_csv: Path,
    summary_csv: Path,
    metrics_json: Path,
    scatter_fig: Path,
    summary_display_rows: list[dict[str, str]],
    observation_rows: list[dict[str, str]],
    cluster_observation: str,
    control_observation: str,
) -> None:
    out_path.write_text(
        "\n".join(
            [
                "# W4b Population Profile (T8)",
                "",
                f"- Run ID: {run_id}",
                f"- Run directory: {rel(run_dir)}",
                f"- Canonical input: `{CANONICAL_RUN}`",
                f"- Building metrics CSV: `{rel(metrics_csv)}`",
                f"- Population summary CSV: `{rel(summary_csv)}`",
                f"- Metrics JSON: `{rel(metrics_json)}`",
                "- Inputs: T5 footprint GPKG, LoD2 reference CityGML, canonical paired-status CSV.",
                "- CRS: EPSG:25832 was checked from the T5 GPKG CRS tag and numeric UTM32 coordinate bounds.",
                "- Scope: distribution/profile observation only. P0 acceptance/rejection remains outside this T8 output.",
                "",
                "## Population Summary",
                "",
                markdown_table(
                    summary_display_rows,
                    [
                        "population",
                        "n",
                        "area_m2_median_iqr",
                        "perimeter_m_median_iqr",
                        "complexity_vertices_median_iqr",
                        "height_m_median_iqr",
                    ],
                ),
                "",
                "Median/IQR cells are formatted as `median [p25-p75]`.",
                "",
                "## Failure 8 Building Metrics",
                "",
                markdown_table(
                    observation_rows,
                    [
                        "building_id",
                        "area_m2",
                        "perimeter_m",
                        "exterior_vertices",
                        "height_m",
                        "dim_failure_bucket_v1",
                    ],
                ),
                "",
                "## Figure",
                "",
                f"![size-complexity scatter]({rel(scatter_fig).replace('docs/', '')})",
                "",
                "## Observations",
                "",
                f"- {control_observation}",
                f"- {cluster_observation}",
                "- Height is measured as LoD2 CityGML per-building z-range; shape complexity is the exterior footprint vertex count.",
                "- These are profile observations only; representativeness or P0 recovery decisions require human G1/E5 interpretation.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def add_to_g1_package(
    package: Path,
    package_figs: Path,
    report_md: Path,
    metrics_csv: Path,
    summary_csv: Path,
    scatter_fig: Path,
) -> None:
    package.mkdir(parents=True, exist_ok=True)
    package_figs.mkdir(parents=True, exist_ok=True)
    targets = [
        (report_md, package / "W4b_population_profile.md"),
        (metrics_csv, package / "w4b_population_profile_building_metrics.csv"),
        (summary_csv, package / "w4b_population_profile_summary.csv"),
        (scatter_fig, package_figs / "fig_12_w4b_population_size_complexity.png"),
    ]
    for src, dst in targets:
        shutil.copy2(src, dst)
    manifest_path = package / "manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
    else:
        manifest = {"package": "G1_package", "canonical_run": CANONICAL_RUN, "files": [], "figure_count": 0}
    files = set(manifest.get("files", []))
    for _, dst in targets:
        files.add(dst.relative_to(package).as_posix())
    manifest["files"] = sorted(files)
    manifest["figure_count"] = sum(1 for item in manifest["files"] if item.startswith("figs/") and item.endswith(".png"))
    manifest["w4b_population_profile"] = {
        "report": "W4b_population_profile.md",
        "figure": "figs/fig_12_w4b_population_size_complexity.png",
        "tables": [
            "w4b_population_profile_building_metrics.csv",
            "w4b_population_profile_summary.csv",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_outputs(run_dir: Path, paths: list[Path]) -> None:
    snapshot = run_dir / "outputs"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if not path.exists():
            continue
        if path.is_relative_to(Path("/workspace/docs")):
            dst = snapshot / "docs" / path.relative_to(Path("/workspace/docs"))
        elif path.is_relative_to(Path("/workspace/data")):
            dst = snapshot / "data" / path.relative_to(Path("/workspace/data"))
        else:
            dst = snapshot / path.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


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


def capture(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return proc.stdout


def record_issue(repo: Path, run_id: str, message: str) -> None:
    issues = repo / "phases/p0-audit/docs/issues.md"
    with issues.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {TASK_ID} Population Profile\n\n")
        fh.write(f"- {run_id}: {message}. See runs/{run_id}/logs/.\n")


def write_host_config(run_dir: Path, run_id: str, git_commit: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.yaml").write_text(
        "\n".join(
            [
                f"task_id: {TASK_ID}",
                f"run_id: {run_id}",
                f"git_commit: {git_commit}",
                "canonical_run: " + CANONICAL_RUN,
                "status_csv: " + STATUS_CSV,
                "footprints: " + FOOTPRINT_GPKG,
                "footprint_layer: " + FOOTPRINT_LAYER,
                "lod2_citygml: data/raw/lod2/*.gml",
                "crs: EPSG:25832 numeric UTM32 coordinates",
                "population_rule: full_199 all canonical rows; control_93 coverage_control_population=yes; failure_8 dim_failure_bucket_v1=roof_matching_assembly_failure",
                "scope: distribution/profile observation only; no P0 judgement",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_host_versions(
    repo: Path,
    run_dir: Path,
    compose: list[str],
    env: dict[str, str],
    git_commit: str,
) -> None:
    lines = [
        "# T8 Population Profile Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {run_dir.name}",
        f"- Repository commit: {git_commit}",
        "",
        "```console",
    ]
    version_cmds = [
        ["git", "status", "--short", "--branch"],
        compose + ["run", "-T", "--rm", "tools", "python", "--version"],
        compose
        + [
            "run",
            "-T",
            "--rm",
            "tools",
            "python",
            "-c",
            "import matplotlib, numpy; print('matplotlib=' + matplotlib.__version__); print('numpy=' + numpy.__version__)",
        ],
        compose + ["run", "-T", "--rm", "tools", "ogrinfo", "--version"],
    ]
    for cmd in version_cmds:
        proc = subprocess.run(cmd, cwd=repo, env=env, text=True, capture_output=True, check=False)
        lines.append("$ " + " ".join(cmd))
        out = (proc.stdout or proc.stderr).strip()
        if out:
            lines.append(out)
        if proc.returncode != 0:
            lines.append(f"[exit {proc.returncode}]")
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def gml_id(elem: ET.Element, fallback: str) -> str:
    for key, value in elem.attrib.items():
        if local_name(key) == "id" and value:
            return value
    return fallback


def parse_poslist_3d(text: str) -> np.ndarray | None:
    values = [float(value) for value in text.split()]
    if len(values) % 3 == 0:
        return np.array(values, dtype=np.float64).reshape((-1, 3))
    if len(values) % 2 == 0:
        return None
    raise ValueError("gml:posList has neither 2D nor 3D coordinate stride")


def ring_area(xy: np.ndarray) -> float:
    x = xy[:, 0]
    y = xy[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def ring_perimeter(xy: np.ndarray) -> float:
    deltas = np.diff(xy, axis=0)
    return float(np.sum(np.sqrt(np.sum(deltas * deltas, axis=1))))


def format_metric_row(row: dict[str, Any]) -> dict[str, str]:
    return {
        "building_id": row["building_id"],
        "in_full_199": "yes" if row["in_full_199"] else "no",
        "in_control_93": "yes" if row["in_control_93"] else "no",
        "in_failure_8": "yes" if row["in_failure_8"] else "no",
        "paired_category": row["paired_category"],
        "coverage_control_population": row["coverage_control_population"],
        "dim_failure_bucket_v1": row["dim_failure_bucket_v1"],
        "floor_area_m2": fmt(row["floor_area_m2"], 3),
        "perimeter_m": fmt(row["perimeter_m"], 3),
        "exterior_vertex_count": str(int(row["exterior_vertex_count"])),
        "part_count": str(int(row["part_count"])),
        "height_m": fmt(row["height_m"], 3),
        "height_source_files": row["height_source_files"],
        "height_coordinate_count": str(int(row["height_coordinate_count"])),
    }


def format_median_iqr(row: dict[str, str], prefix: str) -> str:
    return f"{row[prefix + '_median']} [{row[prefix + '_p25']}-{row[prefix + '_p75']}]"


def markdown_table(rows: list[dict[str, str]], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join(lines)


def sanitize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_json(val) for key, val in value.items()}
    if isinstance(value, list):
        return [sanitize_json(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def fmt(value: float, decimals: int) -> str:
    if value is None or not np.isfinite(float(value)):
        return "n/a"
    return f"{float(value):.{decimals}f}"


def rel(path: Path) -> str:
    text = path.as_posix()
    return text.replace("/workspace/", "")


def main() -> None:
    if os.environ.get("P0_INSIDE_CONTAINER") == "1":
        compute_entrypoint()
    else:
        host_entrypoint()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Finalize W2-1c quality-controlled paired population and failure buckets.

Run from p0-audit/. The host entrypoint re-runs this script inside the P0 tools
container so laspy/matplotlib execution stays in the audit toolchain.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


TASK_ID = "W2-1c"
BASE_NODATA_MAX = 0.30
BASE_DENSITY_MIN = 20.0
SENSITIVITY = [
    ("strict", 0.20, 30.0),
    ("base", BASE_NODATA_MAX, BASE_DENSITY_MIN),
    ("loose", 0.40, 10.0),
]
AOI_BBOX = (690791.740, 5335864.050, 691154.650, 5336353.850)
REFERENCE_CASE_ID = "DEBY_LOD2_104586480"


@dataclass
class Footprint:
    building_id: str
    area_m2: float
    bbox: tuple[float, float, float, float]
    ring: np.ndarray


def host_entrypoint(args: argparse.Namespace) -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]
    if env.get("SKIP_BUILD") != "1":
        run(compose + ["build", "tools"], cwd=repo, env=env)

    run_id = env.get("RUN_ID") or datetime.now().strftime("w2_1c_quality_paired_%Y%m%d_%H%M%S")
    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()
    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    write_config(run_dir, run_id, args.w2_run_id, git_commit)

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
            f"W2_RUN_ID={args.w2_run_id}",
            "-e",
            f"P0_GIT_COMMIT={git_commit}",
            "tools",
            "python",
            "/workspace/scripts/10_w2_quality_paired.py",
            "--inside",
            "--w2-run-id",
            args.w2_run_id,
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "quality_paired.log",
    )


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
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def write_config(run_dir: Path, run_id: str, w2_run_id: str, git_commit: str) -> None:
    lines = [
        "task: W2-1c_quality_paired_population",
        f"run_id: {run_id}",
        f"w2_run_id: {w2_run_id}",
        f"git_commit: {git_commit}",
        f"coverage_nodata_max: {BASE_NODATA_MAX}",
        f"coverage_density_min_pts_m2: {BASE_DENSITY_MIN}",
        f"reference_case_id: {REFERENCE_CASE_ID}",
    ]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_versions(run_dir: Path, w2_run_id: str) -> None:
    lines = [
        "# W2-1c Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {os.environ['RUN_ID']}",
        f"- W2 source run: {w2_run_id}",
        f"- Repository commit: {os.environ.get('P0_GIT_COMMIT', 'unknown')}",
        "",
        "```console",
    ]
    for cmd in (
        ["python", "--version"],
        [
            "python",
            "-c",
            "import laspy, matplotlib, numpy; print('laspy ' + laspy.__version__); print('matplotlib ' + matplotlib.__version__); print('numpy ' + numpy.__version__)",
        ],
    ):
        lines.append("$ " + " ".join(cmd))
        lines.append(capture(cmd))
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def inside_entrypoint(args: argparse.Namespace) -> None:
    root = Path("/workspace")
    docs = root / "docs"
    figs = docs / "figs"
    data = root / "data"
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)
    write_versions(run_dir, args.w2_run_id)

    paired_b = read_csv(docs / "W2_1b_paired_status.csv")
    footprints = load_footprints(data / "work/footprints/lod2_ground_plan.geojson")
    ref_metrics, ref_fig = analyze_reference_case(
        data,
        root / "runs" / args.w2_run_id,
        footprints[REFERENCE_CASE_ID],
        figs,
    )
    paired_c = build_quality_rows(paired_b, ref_metrics)
    summary_rows = build_bucket_summary(paired_c)
    success_rows = build_success_rates(paired_c)
    sensitivity_rows = build_sensitivity(paired_c)
    reference_rows = build_reference_exclusions(ref_metrics)

    outputs = [
        (docs / "W2_1c_paired_status.csv", paired_c),
        (docs / "W2_1c_failure_bucket_summary.csv", summary_rows),
        (docs / "W2_1c_success_rates.csv", success_rows),
        (docs / "W2_1c_coverage_sensitivity.csv", sensitivity_rows),
        (docs / "W2_1c_reference_mismatch_exclusions.csv", reference_rows),
    ]
    for path, rows in outputs:
        write_csv(path, rows)

    report = docs / "W2_1c_quality_paired.md"
    write_report(report, paired_c, summary_rows, success_rows, sensitivity_rows, reference_rows, ref_fig)
    copy_outputs(run_dir, [path for path, _ in outputs] + [report], [ref_fig])

    for path, _ in outputs:
        print(f"output={rel(path)}")
    print(f"reference_figure={rel(ref_fig)}")
    print(f"report={rel(report)}")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError(f"No rows for {path}")
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def load_footprints(path: Path) -> dict[str, Footprint]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    footprints: dict[str, Footprint] = {}
    for feature in payload["features"]:
        props = feature["properties"]
        ring = np.array(feature["geometry"]["coordinates"][0], dtype=np.float64)
        if not np.allclose(ring[0], ring[-1]):
            ring = np.vstack([ring, ring[0]])
        footprints[props["building_id"]] = Footprint(
            building_id=props["building_id"],
            area_m2=float(props["area_m2"]),
            bbox=(float(props["min_x"]), float(props["min_y"]), float(props["max_x"]), float(props["max_y"])),
            ring=ring,
        )
    return footprints


def build_quality_rows(rows: list[dict[str, str]], ref_metrics: dict[str, str]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in rows:
        out = dict(row)
        dim_density = parse_float(row["dim_rf_pt_density"])
        dim_nodata = parse_float(row["dim_rf_nodata_frac"])
        coverage_base = coverage_pass(dim_nodata, dim_density, BASE_NODATA_MAX, BASE_DENSITY_MIN)
        coverage_strict = coverage_pass(dim_nodata, dim_density, 0.20, 30.0)
        coverage_loose = coverage_pass(dim_nodata, dim_density, 0.40, 10.0)
        reference_exclude = row["building_id"] == REFERENCE_CASE_ID and ref_metrics["reference_mismatch_suspected"] == "yes"
        both_attempted = row["both_attempted"] == "yes"
        coverage_control = both_attempted and coverage_base and not reference_exclude

        out["dim_coverage_nodata_max"] = f"{BASE_NODATA_MAX:.2f}"
        out["dim_coverage_density_min_pts_m2"] = f"{BASE_DENSITY_MIN:.1f}"
        out["dim_coverage_pass"] = yesno(coverage_base)
        out["dim_coverage_pass_strict"] = yesno(coverage_strict)
        out["dim_coverage_pass_loose"] = yesno(coverage_loose)
        out["reference_mismatch_exclude"] = yesno(reference_exclude)
        out["reference_mismatch_reason"] = ref_metrics["reason"] if reference_exclude else ""
        out["coverage_control_population"] = yesno(coverage_control)
        out["als_failure_bucket_v1"] = failure_bucket("ALS", row, coverage_base, reference_exclude)
        out["dim_failure_bucket_v1"] = failure_bucket("DIM", row, coverage_base, reference_exclude)
        output.append(out)
    return output


def coverage_pass(nodata: float | None, density: float | None, nodata_max: float, density_min: float) -> bool:
    if nodata is None or density is None:
        return False
    return nodata <= nodata_max and density >= density_min


def failure_bucket(label: str, row: dict[str, str], dim_coverage_pass: bool, reference_exclude: bool) -> str:
    prefix = label.lower()
    reason = row[f"{prefix}_reason"]
    status = row[f"{prefix}_status"]
    if status == "success":
        return "success"
    if label == "DIM" and reference_exclude:
        return "reference_mismatch"
    if reason == "missing_roofer_output":
        return "reference_mismatch"
    if reason in {"pointcloud_unusable_no_points", "pointcloud_unusable_no_planes", "pointcloud_unusable"}:
        return "coverage"
    if label == "DIM" and reason == "missing_lod22_geometry":
        return "roof_matching_assembly_failure" if dim_coverage_pass else "coverage"
    if reason == "val3dity_invalid":
        return "validity"
    return "roof_matching_assembly_failure"


def build_bucket_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    buckets = ["success", "coverage", "roof_matching_assembly_failure", "validity", "reference_mismatch"]
    output: list[dict[str, str]] = []
    for label in ("als", "dim"):
        for bucket in buckets:
            output.append(
                {
                    "input": label.upper(),
                    "bucket_v1": bucket,
                    "full_199_count": str(sum(row[f"{label}_failure_bucket_v1"] == bucket for row in rows)),
                    "both_attempted_179_count": str(
                        sum(row["both_attempted"] == "yes" and row[f"{label}_failure_bucket_v1"] == bucket for row in rows)
                    ),
                    "coverage_control_count": str(
                        sum(row["coverage_control_population"] == "yes" and row[f"{label}_failure_bucket_v1"] == bucket for row in rows)
                    ),
                }
            )
    return output


def build_success_rates(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    populations = [
        ("full_199", rows),
        ("both_attempted_179", [row for row in rows if row["both_attempted"] == "yes"]),
        ("coverage_controlled", [row for row in rows if row["coverage_control_population"] == "yes"]),
    ]
    output: list[dict[str, str]] = []
    for name, pop in populations:
        total = len(pop)
        output.append(
            {
                "population": name,
                "n": str(total),
                "als_success": count_rate(sum(row["als_status"] == "success" for row in pop), total),
                "dim_success": count_rate(sum(row["dim_status"] == "success" for row in pop), total),
                "both_success": count_rate(sum(row["paired_category"] == "both_success" for row in pop), total),
                "als_only": count_rate(sum(row["paired_category"] == "ALS_only" for row in pop), total),
                "dim_only": count_rate(sum(row["paired_category"] == "DIM_only" for row in pop), total),
                "both_fail": count_rate(sum(row["paired_category"] == "both_fail" for row in pop), total),
            }
        )
    return output


def build_sensitivity(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for name, nodata_max, density_min in SENSITIVITY:
        pop = [
            row
            for row in rows
            if row["both_attempted"] == "yes"
            and row["reference_mismatch_exclude"] != "yes"
            and coverage_pass(parse_float(row["dim_rf_nodata_frac"]), parse_float(row["dim_rf_pt_density"]), nodata_max, density_min)
        ]
        total = len(pop)
        output.append(
            {
                "sensitivity": name,
                "nodata_max": f"{nodata_max:.2f}",
                "density_min_pts_m2": f"{density_min:.1f}",
                "coverage_controlled_n": str(total),
                "als_success": count_rate(sum(row["als_status"] == "success" for row in pop), total),
                "dim_success": count_rate(sum(row["dim_status"] == "success" for row in pop), total),
                "dim_failure_coverage": str(sum(row["dim_failure_bucket_v1"] == "coverage" for row in pop)),
                "dim_failure_roof_matching_assembly": str(
                    sum(row["dim_failure_bucket_v1"] == "roof_matching_assembly_failure" for row in pop)
                ),
                "dim_failure_validity": str(sum(row["dim_failure_bucket_v1"] == "validity" for row in pop)),
            }
        )
    return output


def build_reference_exclusions(ref_metrics: dict[str, str]) -> list[dict[str, str]]:
    return [ref_metrics] if ref_metrics["reference_mismatch_suspected"] == "yes" else [
        {
            "building_id": REFERENCE_CASE_ID,
            "reference_mismatch_suspected": "no",
            "reason": ref_metrics["reason"],
            "action": "keep",
        }
    ]


def analyze_reference_case(
    data: Path,
    source_run: Path,
    footprint: Footprint,
    figs: Path,
) -> tuple[dict[str, str], Path]:
    als = read_points(sorted((data / "raw/als").glob("*.laz")), footprint, buffer_m=6.0)
    dim = read_points([data / "work/w2/dim_v1_classified_z_minus0p174.laz"], footprint, buffer_m=6.0)
    als_metrics = point_metrics(als)
    dim_metrics = point_metrics(dim)
    suspected = (
        dim_metrics["inside_ground_ratio"] >= 0.50
        and als_metrics["inside_ground_ratio"] <= 0.05
        and dim_metrics["inside_count"] > 0
    )
    reason = (
        "DIM footprint interior is dominated by ground-class points while ALS has almost no ground-class interior; "
        "coverage is high, so the failure is treated as reference or temporal mismatch candidate."
        if suspected
        else "No strong ALS/DIM interior ground-ratio discrepancy under the current heuristic."
    )
    city_als = load_cityjson(source_run / "cityjson/als_roofer.city.json")
    city_dim = load_cityjson(source_run / "cityjson/dim_roofer.city.json")
    fig_path = figs / f"w2_1c_{REFERENCE_CASE_ID}_als_dim_section.png"
    write_reference_figure(fig_path, footprint, als, dim, city_als, city_dim)
    metrics = {
        "building_id": REFERENCE_CASE_ID,
        "reference_mismatch_suspected": yesno(suspected),
        "reason": reason,
        "action": "exclude_from_coverage_control_population" if suspected else "keep",
        "figure": rel(fig_path),
        "als_inside_count": str(als_metrics["inside_count"]),
        "als_inside_ground_ratio": f"{als_metrics['inside_ground_ratio']:.3f}",
        "als_inside_non_ground_z_p50": f"{als_metrics['inside_non_ground_z_p50']:.3f}",
        "dim_inside_count": str(dim_metrics["inside_count"]),
        "dim_inside_ground_ratio": f"{dim_metrics['inside_ground_ratio']:.3f}",
        "dim_inside_non_ground_z_p50": f"{dim_metrics['inside_non_ground_z_p50']:.3f}",
    }
    return metrics, fig_path


def read_points(paths: list[Path], footprint: Footprint, buffer_m: float) -> dict[str, np.ndarray]:
    import laspy

    min_x, min_y, max_x, max_y = footprint.bbox
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    zs: list[np.ndarray] = []
    cls: list[np.ndarray] = []
    for path in paths:
        with laspy.open(path) as fh:
            for points in fh.chunk_iterator(1_000_000):
                x = np.asarray(points.x)
                y = np.asarray(points.y)
                mask = (
                    (x >= min_x - buffer_m)
                    & (x <= max_x + buffer_m)
                    & (y >= min_y - buffer_m)
                    & (y <= max_y + buffer_m)
                )
                if not np.any(mask):
                    continue
                xs.append(x[mask].astype(np.float64, copy=False))
                ys.append(y[mask].astype(np.float64, copy=False))
                zs.append(np.asarray(points.z)[mask].astype(np.float64, copy=False))
                cls.append(np.asarray(points.classification, dtype=np.uint8)[mask])
    if not xs:
        return empty_points()
    x = np.concatenate(xs)
    y = np.concatenate(ys)
    return {
        "x": x,
        "y": y,
        "z": np.concatenate(zs),
        "classification": np.concatenate(cls),
        "inside": points_in_polygon(x, y, footprint.ring),
    }


def empty_points() -> dict[str, np.ndarray]:
    return {
        "x": np.array([], dtype=np.float64),
        "y": np.array([], dtype=np.float64),
        "z": np.array([], dtype=np.float64),
        "classification": np.array([], dtype=np.uint8),
        "inside": np.array([], dtype=bool),
    }


def point_metrics(points: dict[str, np.ndarray]) -> dict[str, float | int]:
    inside = points["inside"]
    count = int(np.count_nonzero(inside))
    if count == 0:
        return {"inside_count": 0, "inside_ground_ratio": 0.0, "inside_non_ground_z_p50": float("nan")}
    cls = points["classification"]
    z = points["z"]
    ground = inside & (cls == 2)
    non_ground = inside & (cls != 2)
    if np.any(non_ground):
        non_ground_p50 = float(np.median(z[non_ground]))
    else:
        non_ground_p50 = float("nan")
    return {
        "inside_count": count,
        "inside_ground_ratio": float(np.count_nonzero(ground) / count),
        "inside_non_ground_z_p50": non_ground_p50,
    }


def write_reference_figure(
    path: Path,
    footprint: Footprint,
    als: dict[str, np.ndarray],
    dim: dict[str, np.ndarray],
    city_als: dict[str, Any],
    city_dim: dict[str, Any],
) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(16, 12), constrained_layout=True)
    plot_topdown(axes[0, 0], "ALS top-down", footprint, als, city_als)
    plot_topdown(axes[0, 1], "DIM top-down", footprint, dim, city_dim)
    plot_profile(axes[1, 0], "ALS profile", footprint, als, city_als)
    plot_profile(axes[1, 1], "DIM profile", footprint, dim, city_dim)
    fig.suptitle(f"{REFERENCE_CASE_ID} ALS vs DIM section/reference check", fontsize=14)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_topdown(ax: Any, title: str, footprint: Footprint, points: dict[str, np.ndarray], city: dict[str, Any]) -> None:
    x = points["x"]
    y = points["y"]
    z = points["z"]
    cls = points["classification"]
    if x.size:
        idx = sample_indices(x.size, 100_000)
        ground = cls[idx] == 2
        ax.scatter(x[idx][ground], y[idx][ground], s=1, c="#9a9a9a", alpha=0.25, linewidths=0, label="ground")
        sc = ax.scatter(x[idx][~ground], y[idx][~ground], s=1, c=z[idx][~ground], cmap="viridis", alpha=0.65, linewidths=0, label="non-ground")
        colorbar(sc, ax, "Z")
    ax.plot(footprint.ring[:, 0], footprint.ring[:, 1], color="#d62728", linewidth=2.0, label="footprint")
    plot_cityjson_xy(ax, city, color="#1f77b4")
    ax.set_title(title)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    ax.legend(loc="best", fontsize=8)


def plot_profile(ax: Any, title: str, footprint: Footprint, points: dict[str, np.ndarray], city: dict[str, Any]) -> None:
    axis = footprint_axis(footprint.ring)
    origin = footprint.ring[:-1].mean(axis=0)
    x = points["x"]
    y = points["y"]
    z = points["z"]
    cls = points["classification"]
    if x.size:
        s = (np.column_stack([x, y]) - origin) @ axis
        idx = sample_indices(x.size, 100_000)
        ground = cls[idx] == 2
        ax.scatter(s[idx][ground], z[idx][ground], s=1, c="#9a9a9a", alpha=0.25, linewidths=0, label="ground")
        ax.scatter(s[idx][~ground], z[idx][~ground], s=1, c="#2ca02c", alpha=0.45, linewidths=0, label="non-ground")
    city_vertices = vertices_for_cityjson(city)
    if city_vertices.size:
        city_s = (city_vertices[:, :2] - origin) @ axis
        ax.scatter(city_s, city_vertices[:, 2], s=14, c="#1f77b4", alpha=0.9, label="Roofer vertices")
    fp_s = (footprint.ring[:, :2] - origin) @ axis
    ax.axvspan(float(np.min(fp_s)), float(np.max(fp_s)), color="#d62728", alpha=0.12, label="footprint span")
    ax.set_title(title)
    ax.set_xlabel("Along-axis distance (m)")
    ax.set_ylabel("Z (m)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=8)


def load_cityjson(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    transform = payload.get("transform", {"scale": [1, 1, 1], "translate": [0, 0, 0]})
    vertices = np.array(payload.get("vertices", []), dtype=np.float64)
    if vertices.size:
        vertices = vertices * np.array(transform["scale"], dtype=np.float64) + np.array(transform["translate"], dtype=np.float64)
    payload["_absolute_vertices"] = vertices
    return payload


def vertices_for_cityjson(city: dict[str, Any]) -> np.ndarray:
    vertices = city.get("_absolute_vertices", np.empty((0, 3)))
    objects = city.get("CityObjects", {})
    indices: set[int] = set()
    for obj_id in [REFERENCE_CASE_ID, *objects.get(REFERENCE_CASE_ID, {}).get("children", [])]:
        obj = objects.get(obj_id)
        if not obj:
            continue
        for geom in obj.get("geometry", []):
            collect_indices(geom.get("boundaries", []), indices)
    if not indices:
        return np.empty((0, 3), dtype=np.float64)
    return vertices[np.array(sorted(indices), dtype=np.int64)]


def plot_cityjson_xy(ax: Any, city: dict[str, Any], color: str) -> None:
    vertices = city.get("_absolute_vertices", np.empty((0, 3)))
    objects = city.get("CityObjects", {})
    for obj_id in [REFERENCE_CASE_ID, *objects.get(REFERENCE_CASE_ID, {}).get("children", [])]:
        obj = objects.get(obj_id)
        if not obj:
            continue
        for geom in obj.get("geometry", []):
            for ring in iter_rings(geom.get("boundaries", [])):
                coords = vertices[np.array(ring, dtype=np.int64)]
                ax.plot(coords[:, 0], coords[:, 1], color=color, linewidth=1.1, alpha=0.8, label="Roofer geometry")


def collect_indices(value: Any, output: set[int]) -> None:
    if isinstance(value, int):
        output.add(value)
    elif isinstance(value, list):
        for item in value:
            collect_indices(item, output)


def iter_rings(value: Any) -> list[list[int]]:
    rings: list[list[int]] = []
    if isinstance(value, list):
        if value and all(isinstance(item, int) for item in value):
            rings.append(value)
        else:
            for item in value:
                rings.extend(iter_rings(item))
    return rings


def colorbar(scatter: Any, ax: Any, label: str) -> None:
    import matplotlib.pyplot as plt

    cbar = plt.colorbar(scatter, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(label)


def sample_indices(size: int, max_count: int) -> np.ndarray:
    if size <= max_count:
        return np.arange(size)
    rng = np.random.default_rng(20260612)
    return np.sort(rng.choice(size, size=max_count, replace=False))


def footprint_axis(ring: np.ndarray) -> np.ndarray:
    coords = ring[:-1]
    centered = coords - coords.mean(axis=0)
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    return vh[0]


def points_in_polygon(xs: np.ndarray, ys: np.ndarray, ring: np.ndarray) -> np.ndarray:
    inside = np.zeros(xs.shape, dtype=bool)
    for idx in range(ring.shape[0] - 1):
        x1, y1 = ring[idx]
        x2, y2 = ring[idx + 1]
        crossing = (y1 > ys) != (y2 > ys)
        if not np.any(crossing):
            continue
        x_at_y = (x2 - x1) * (ys[crossing] - y1) / (y2 - y1) + x1
        inside[crossing] ^= xs[crossing] < x_at_y
    return inside


def write_report(
    path: Path,
    paired: list[dict[str, str]],
    bucket_rows: list[dict[str, str]],
    success_rows: list[dict[str, str]],
    sensitivity_rows: list[dict[str, str]],
    reference_rows: list[dict[str, str]],
    ref_fig: Path,
) -> None:
    dim_coverage_counts = Counter(row["dim_failure_bucket_v1"] for row in paired)
    no_points_total = sum(row["dim_reason"] == "pointcloud_unusable_no_points" for row in paired)
    no_points_als_success = sum(
        row["dim_reason"] == "pointcloud_unusable_no_points" and row["als_status"] == "success" for row in paired
    )
    missing_lod22_coverage = sum(
        row["dim_reason"] == "missing_lod22_geometry" and row["dim_failure_bucket_v1"] == "coverage" for row in paired
    )
    lines = [
        "# W2-1c Quality-Paired Population",
        "",
        f"- Coverage rule: DIM `nodata_frac <= {BASE_NODATA_MAX}` and `pt_density >= {BASE_DENSITY_MIN} pts/m2`.",
        "- Sensitivity: strict `0.20/30 pts/m2`, loose `0.40/10 pts/m2`.",
        "- Failure bucket v1: `coverage`, `roof_matching_assembly_failure`, `validity`, `reference_mismatch`.",
        "- Coverage-controlled population: both attempted, DIM coverage pass, and no reference-mismatch exclusion.",
        "",
        "## Success Rates",
        "",
    ]
    lines.extend(markdown_table(success_rows))
    lines.extend(
        [
            "",
            "## DIM Failure Bucket Summary",
            "",
            f"- DIM `no_points` classified as coverage: {no_points_total} total; {no_points_als_success} are paired with ALS success.",
            f"- DIM `missing_lod22_geometry` classified as coverage due to coverage miss: {missing_lod22_coverage}.",
            f"- DIM bucket counts, full 199: {dict(dim_coverage_counts)}",
            "",
            "## Bucket Counts",
            "",
        ]
    )
    lines.extend(markdown_table(bucket_rows))
    lines.extend(["", "## Coverage Sensitivity", ""])
    lines.extend(markdown_table(sensitivity_rows))
    lines.extend(["", "## Reference Mismatch Check", ""])
    lines.extend(markdown_table(reference_rows))
    lines.extend(
        [
            "",
            f"- ALS/DIM section figure: `{rel(ref_fig)}`",
            "",
            "## Files",
            "",
            "- Updated paired CSV: `docs/W2_1c_paired_status.csv`",
            "- Classification summary: `docs/W2_1c_failure_bucket_summary.csv`",
            "- Success-rate table: `docs/W2_1c_success_rates.csv`",
            "- Coverage sensitivity: `docs/W2_1c_coverage_sensitivity.csv`",
            "- Reference mismatch exclusions: `docs/W2_1c_reference_mismatch_exclusions.csv`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def markdown_table(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return []
    headers = list(rows[0].keys())
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" if idx == 0 else "---:" for idx, _ in enumerate(headers)) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(row[h] for h in headers) + " |")
    return out


def copy_outputs(run_dir: Path, docs: list[Path], figs: list[Path]) -> None:
    import shutil

    doc_dir = run_dir / "docs"
    fig_dir = run_dir / "figs"
    doc_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)
    for path in docs:
        shutil.copy2(path, doc_dir / path.name)
    for path in figs:
        shutil.copy2(path, fig_dir / path.name)


def count_rate(count: int, total: int) -> str:
    return f"{count}/{total} ({count / total * 100.0:.1f}%)" if total else "0/0 (nan)"


def parse_float(value: str) -> float | None:
    if value == "":
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def yesno(value: bool) -> str:
    return "yes" if value else "no"


def rel(path: Path) -> str:
    return path.as_posix().replace("/workspace/", "").replace("p0-audit/", "")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--w2-run-id", default="w2_1_roofer_default_20260612_152729")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.inside or os.environ.get("P0_INSIDE_CONTAINER") == "1":
        inside_entrypoint(args)
    else:
        host_entrypoint(args)


if __name__ == "__main__":
    main()

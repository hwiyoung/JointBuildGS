#!/usr/bin/env python3
"""Run W2-1 Roofer default reconstructions for ALS and DIM inputs.

Run from phases/p0-audit/. The host entrypoint orchestrates Docker Compose services.
Container modes perform data preparation and post-processing inside the P0
toolchain.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_ID = "W2-1"
DIM_MEDIAN_RESIDUAL_M = 0.174
DIM_Z_OFFSET_M = -DIM_MEDIAN_RESIDUAL_M
AOI_BBOX = (690791.740, 5335864.050, 691154.650, 5336353.850)


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("w2_1_roofer_default_%Y%m%d_%H%M%S")
    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()

    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]
    if env.get("SKIP_BUILD") != "1":
        run(compose + ["build", "tools"], cwd=repo, env=env, log_path=logs_dir / "build_tools.log")

    write_host_config(repo, run_dir, run_id, git_commit)
    write_host_versions(repo, run_dir, compose, env, git_commit)

    common_env = [
        "-e",
        "P0_INSIDE_TOOLS=1",
        "-e",
        f"RUN_ID={run_id}",
        "-e",
        f"P0_GIT_COMMIT={git_commit}",
    ]
    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            *common_env,
            "tools",
            "python",
            "/workspace/scripts/08_roofer_w2.py",
            "--mode",
            "prepare",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "prepare.log",
    )

    roofer_runs = {
        "als": {
            "input": "/workspace/data/raw/als",
            "output": f"/workspace/runs/{run_id}/roofer_als",
        },
        "dim": {
            "input": "/workspace/data/work/w2/dim_v1_classified_z_minus0p174.laz",
            "output": f"/workspace/runs/{run_id}/roofer_dim",
        },
    }
    for label, spec in roofer_runs.items():
        run(
            compose
            + [
                "run",
                "-T",
                "--rm",
                "roofer",
                "--id-attribute",
                "building_id",
                "--box",
                *(f"{v:.3f}" for v in AOI_BBOX),
                spec["input"],
                "/workspace/data/work/w2/footprints_scene_aoi.gpkg",
                spec["output"],
            ],
            cwd=repo,
            env=env,
            log_path=logs_dir / f"roofer_{label}.log",
        )

    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            *common_env,
            "tools",
            "python",
            "/workspace/scripts/08_roofer_w2.py",
            "--mode",
            "postprocess",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "postprocess.log",
    )

    print(f"run_id={run_id}")
    print(f"run_dir=runs/{run_id}")
    print("report=docs/W2_1_roofer_default.md")


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


def capture(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def write_host_config(repo: Path, run_dir: Path, run_id: str, git_commit: str) -> None:
    config = {
        "task": "W2-1_roofer_default",
        "run_id": run_id,
        "git_commit": git_commit,
        "crs": "EPSG:25832",
        "aoi_bbox": list(AOI_BBOX),
        "footprints": "data/work/w2/footprints_scene_aoi.gpkg",
        "footprint_source": "data/work/footprints/lod2_ground_plan.gpkg",
        "building_list": "docs/scene_aoi_buildings.csv",
        "input_a": "data/raw/als/*.laz",
        "input_b_source": "data/work/classify/dim_v1_classified_z.laz",
        "input_b_used": "data/work/w2/dim_v1_classified_z_minus0p174.laz",
        "dim_median_residual_removed_m": DIM_MEDIAN_RESIDUAL_M,
        "dim_z_offset_applied_m": DIM_Z_OFFSET_M,
        "roofer": {
            "mode": "default reconstruction parameters",
            "plumbing_options": [
                "--id-attribute building_id",
                "--box AOI_BBOX",
            ],
        },
        "outputs": {
            "als_cityjson": f"runs/{run_id}/cityjson/als_roofer.city.json",
            "dim_cityjson": f"runs/{run_id}/cityjson/dim_roofer.city.json",
            "building_status": f"runs/{run_id}/building_reconstruction_status.csv",
        },
    }
    (run_dir / "config.yaml").write_text(to_yaml(config), encoding="utf-8")


def to_yaml(value: Any, indent: int = 0) -> str:
    space = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{space}{key}:")
                lines.append(to_yaml(item, indent + 2))
            else:
                lines.append(f"{space}{key}: {yaml_scalar(item)}")
        return "\n".join(lines) + ("\n" if indent == 0 else "")
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{space}-")
                lines.append(to_yaml(item, indent + 2))
            else:
                lines.append(f"{space}- {yaml_scalar(item)}")
        return "\n".join(lines)
    return f"{space}{yaml_scalar(value)}"


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text or any(ch in text for ch in ":#[]{}*,&!|>'\"%@`"):
        return json.dumps(text, ensure_ascii=False)
    return text


def write_host_versions(
    repo: Path,
    run_dir: Path,
    compose: list[str],
    env: dict[str, str],
    git_commit: str,
) -> None:
    lines = [
        "# W2-1 Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {run_dir.name}",
        f"- Repository commit: {git_commit}",
        "",
        "```console",
    ]
    commands = [
        ["git", "status", "--short", "--branch"],
        [*compose, "images"],
        [*compose, "run", "-T", "--rm", "roofer", "-v"],
        [*compose, "run", "-T", "--rm", "tools", "val3dity", "--version"],
        [*compose, "run", "-T", "--rm", "tools", "pdal", "--version"],
        [*compose, "run", "-T", "--rm", "tools", "ogr2ogr", "--version"],
        [
            *compose,
            "run",
            "-T",
            "--rm",
            "tools",
            "python",
            "-c",
            "import laspy, numpy; print('laspy ' + laspy.__version__); print('numpy ' + numpy.__version__)",
        ],
    ]
    for cmd in commands:
        lines.append("$ " + " ".join(cmd))
        lines.append(capture(cmd, cwd=repo, env=env))
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def tools_prepare() -> None:
    root = Path("/workspace")
    data = root / "data"
    docs = root / "docs"
    work_dir = data / "work/w2"
    work_dir.mkdir(parents=True, exist_ok=True)

    building_ids = read_building_ids(docs / "scene_aoi_buildings.csv")
    write_footprint_subset(
        data / "work/footprints/lod2_ground_plan.gpkg",
        work_dir / "footprints_scene_aoi.gpkg",
        building_ids,
    )
    write_dim_offset_laz(
        data / "work/classify/dim_v1_classified_z.laz",
        work_dir / "dim_v1_classified_z_minus0p174.laz",
        DIM_Z_OFFSET_M,
    )
    print(f"prepared_buildings={len(building_ids)}")
    print("prepared_footprints=data/work/w2/footprints_scene_aoi.gpkg")
    print("prepared_dim=data/work/w2/dim_v1_classified_z_minus0p174.laz")


def read_building_ids(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        ids = [row["building_id"] for row in csv.DictReader(fh)]
    if len(ids) != len(set(ids)):
        duplicates = [bid for bid, count in Counter(ids).items() if count > 1]
        raise RuntimeError(f"Duplicate building_id values in {path}: {duplicates[:5]}")
    return ids


def write_footprint_subset(source: Path, target: Path, building_ids: list[str]) -> None:
    if target.exists():
        target.unlink()
    quoted = ", ".join("'" + bid.replace("'", "''") + "'" for bid in building_ids)
    sql = f"SELECT * FROM lod2_ground_plan WHERE building_id IN ({quoted})"
    run(
        [
            "ogr2ogr",
            "-f",
            "GPKG",
            target.as_posix(),
            source.as_posix(),
            "-dialect",
            "SQLITE",
            "-sql",
            sql,
            "-nln",
            "footprints_scene_aoi",
            "-a_srs",
            "EPSG:25832",
        ]
    )


def write_dim_offset_laz(source: Path, target: Path, z_offset_m: float) -> None:
    import laspy

    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
        print(f"reusing_existing_dim_offset={target}")
        return

    tmp = target.with_suffix(".tmp.laz")
    if tmp.exists():
        tmp.unlink()
    with laspy.open(source) as reader:
        with laspy.open(tmp, mode="w", header=reader.header) as writer:
            for points in reader.chunk_iterator(1_000_000):
                points.z = points.z + z_offset_m
                writer.write_points(points)
    tmp.replace(target)


def tools_postprocess() -> None:
    root = Path("/workspace")
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    docs = root / "docs"
    cityjson_dir = run_dir / "cityjson"
    val_dir = run_dir / "val3dity"
    cityjson_dir.mkdir(parents=True, exist_ok=True)
    val_dir.mkdir(parents=True, exist_ok=True)

    expected_ids = read_building_ids(docs / "scene_aoi_buildings.csv")
    outputs = {
        "ALS": {
            "jsonl_dir": run_dir / "roofer_als",
            "cityjson": cityjson_dir / "als_roofer.city.json",
            "val_report": val_dir / "als_val3dity_report.json",
            "val_log": val_dir / "als_val3dity.log",
        },
        "DIM": {
            "jsonl_dir": run_dir / "roofer_dim",
            "cityjson": cityjson_dir / "dim_roofer.city.json",
            "val_report": val_dir / "dim_val3dity_report.json",
            "val_log": val_dir / "dim_val3dity.log",
        },
    }

    all_rows: list[dict[str, str]] = []
    summaries: dict[str, Counter[str]] = {}
    val_summaries: dict[str, dict[str, int | bool]] = {}

    for label, spec in outputs.items():
        jsonl_files = sorted(spec["jsonl_dir"].glob("*.city.jsonl"))
        if not jsonl_files:
            raise RuntimeError(f"No Roofer CityJSONSeq files found in {spec['jsonl_dir']}")
        combine_cityjsonseq(jsonl_files, spec["cityjson"])
        run(
            [
                "val3dity",
                spec["cityjson"].as_posix(),
                "--report",
                spec["val_report"].as_posix(),
            ],
            log_path=spec["val_log"],
        )
        val_report = json.loads(spec["val_report"].read_text(encoding="utf-8"))
        val_by_id = {
            str(feature.get("id")): feature
            for feature in val_report.get("features", [])
            if feature.get("id") is not None
        }
        roofer_by_id = parse_roofer_features(jsonl_files)
        rows = classify_buildings(label, expected_ids, roofer_by_id, val_by_id)
        all_rows.extend(rows)
        summaries[label] = Counter(row["reason"] for row in rows)
        val_summaries[label] = {
            "validity": bool(val_report.get("validity", False)),
            "feature_total": int(sum(item.get("total", 0) for item in val_report.get("features_overview", []))),
            "feature_valid": int(sum(item.get("valid", 0) for item in val_report.get("features_overview", []))),
        }

    status_csv = run_dir / "building_reconstruction_status.csv"
    write_status_csv(status_csv, all_rows)
    summary_json = run_dir / "w2_1_summary.json"
    write_summary_json(summary_json, summaries, val_summaries, outputs, status_csv)
    write_report(docs / "W2_1_roofer_default.md", run_id, summaries, val_summaries, outputs, status_csv)

    print(f"status_csv={rel(status_csv)}")
    print(f"summary_json={rel(summary_json)}")
    print(f"als_cityjson={rel(outputs['ALS']['cityjson'])}")
    print(f"dim_cityjson={rel(outputs['DIM']['cityjson'])}")


def combine_cityjsonseq(jsonl_files: list[Path], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    top: dict[str, Any] | None = None
    cityobjects: dict[str, Any] = {}
    vertices: list[list[int]] = []
    extent = [math.inf, math.inf, math.inf, -math.inf, -math.inf, -math.inf]

    for path in jsonl_files:
        with path.open("r", encoding="utf-8") as fh:
            header = json.loads(fh.readline())
            if top is None:
                top = header
                top["CityObjects"] = {}
                top["vertices"] = []
            source_transform = header.get("transform")
            target_transform = top.get("transform")
            for line in fh:
                if not line.strip():
                    continue
                feature = json.loads(line)
                feature_vertices = feature.get("vertices", [])
                converted_vertices = convert_vertices(feature_vertices, source_transform, target_transform)
                offset = len(vertices)
                vertices.extend(converted_vertices)
                for obj_id, obj in feature.get("CityObjects", {}).items():
                    if obj_id in cityobjects:
                        raise RuntimeError(f"Duplicate CityObject id while merging Roofer output: {obj_id}")
                    shift_cityobject_boundaries(obj, offset)
                    cityobjects[obj_id] = obj
                    obj_extent = obj.get("geographicalExtent")
                    if obj_extent and len(obj_extent) == 6:
                        extent = [
                            min(extent[0], float(obj_extent[0])),
                            min(extent[1], float(obj_extent[1])),
                            min(extent[2], float(obj_extent[2])),
                            max(extent[3], float(obj_extent[3])),
                            max(extent[4], float(obj_extent[4])),
                            max(extent[5], float(obj_extent[5])),
                        ]

    if top is None:
        raise RuntimeError("No CityJSONSeq input files were provided")
    top["CityObjects"] = cityobjects
    top["vertices"] = vertices
    if all(math.isfinite(v) for v in extent):
        top.setdefault("metadata", {})["geographicalExtent"] = extent
    output.write_text(json.dumps(top, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def convert_vertices(
    vertices: list[list[int | float]],
    source_transform: dict[str, list[float]] | None,
    target_transform: dict[str, list[float]] | None,
) -> list[list[int]]:
    if source_transform == target_transform:
        return [[int(round(coord)) for coord in vertex] for vertex in vertices]
    if not source_transform or not target_transform:
        raise RuntimeError("Cannot merge CityJSONSeq tiles with missing transform metadata")
    src_scale = source_transform["scale"]
    src_translate = source_transform["translate"]
    dst_scale = target_transform["scale"]
    dst_translate = target_transform["translate"]
    converted = []
    for vertex in vertices:
        absolute = [float(vertex[i]) * src_scale[i] + src_translate[i] for i in range(3)]
        converted.append([int(round((absolute[i] - dst_translate[i]) / dst_scale[i])) for i in range(3)])
    return converted


def shift_cityobject_boundaries(obj: dict[str, Any], offset: int) -> None:
    for geom in obj.get("geometry", []):
        if "boundaries" in geom:
            geom["boundaries"] = shift_boundary_indices(geom["boundaries"], offset)


def shift_boundary_indices(value: Any, offset: int) -> Any:
    if isinstance(value, int):
        return value + offset
    if isinstance(value, list):
        return [shift_boundary_indices(item, offset) for item in value]
    return value


def parse_roofer_features(jsonl_files: list[Path]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for path in jsonl_files:
        with path.open("r", encoding="utf-8") as fh:
            next(fh)
            for line in fh:
                if not line.strip():
                    continue
                feature = json.loads(line)
                feature_id = str(feature.get("id", ""))
                objects = feature.get("CityObjects", {})
                building = objects.get(feature_id)
                if not building:
                    building = next((obj for obj in objects.values() if obj.get("type") == "Building"), None)
                if not building:
                    continue
                attrs = building.get("attributes", {})
                by_id[feature_id] = {
                    "attributes": attrs,
                    "has_lod22": has_lod22_geometry(objects),
                    "jsonl_file": path.name,
                }
    return by_id


def has_lod22_geometry(objects: dict[str, Any]) -> bool:
    for obj in objects.values():
        for geom in obj.get("geometry", []):
            if str(geom.get("lod")) == "2.2":
                return True
    return False


def classify_buildings(
    label: str,
    expected_ids: list[str],
    roofer_by_id: dict[str, dict[str, Any]],
    val_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for building_id in expected_ids:
        roofer = roofer_by_id.get(building_id)
        val = val_by_id.get(building_id)
        attrs = roofer["attributes"] if roofer else {}
        val_valid = bool(val.get("validity")) if val else False
        val_errors = json.dumps(val.get("errors", []), ensure_ascii=False, separators=(",", ":")) if val else ""
        has_lod22 = bool(roofer.get("has_lod22")) if roofer else False
        status, reason = classify_reason(attrs, bool(roofer), val_valid, bool(val), has_lod22)
        rows.append(
            {
                "input": label,
                "building_id": building_id,
                "status": status,
                "reason": reason,
                "rf_success": str(attrs.get("rf_success", "")),
                "rf_extrusion_mode": str(attrs.get("rf_extrusion_mode", "")),
                "rf_pointcloud_unusable": str(attrs.get("rf_pointcloud_unusable", "")),
                "rf_roof_type": str(attrs.get("rf_roof_type", "")),
                "rf_pt_density": format_float(attrs.get("rf_pt_density")),
                "rf_nodata_frac": format_float(attrs.get("rf_nodata_frac")),
                "rf_rmse_lod22": format_float(attrs.get("rf_rmse_lod22")),
                "rf_roof_planes": str(attrs.get("rf_roof_planes", "")),
                "has_lod22": str(has_lod22),
                "val3dity_valid": str(val_valid) if val else "",
                "val3dity_errors": val_errors,
            }
        )
    return rows


def classify_reason(
    attrs: dict[str, Any],
    has_roofer: bool,
    val_valid: bool,
    has_val_report: bool,
    has_lod22: bool,
) -> tuple[str, str]:
    if not has_roofer:
        return "failure", "missing_roofer_output"
    if attrs.get("rf_success") is False:
        return "failure", "roofer_unsuccessful"
    if attrs.get("rf_pointcloud_unusable") is True:
        roof_type = str(attrs.get("rf_roof_type", ""))
        if roof_type == "no points":
            return "failure", "pointcloud_unusable_no_points"
        if roof_type == "no planes":
            return "failure", "pointcloud_unusable_no_planes"
        return "failure", "pointcloud_unusable"
    extrusion = str(attrs.get("rf_extrusion_mode", ""))
    if extrusion == "skip":
        return "failure", "roofer_skip_no_3d_geometry"
    if extrusion == "lod11_fallback":
        return "failure", "lod11_fallback"
    if not has_lod22:
        return "failure", "missing_lod22_geometry"
    if not has_val_report:
        return "failure", "missing_val3dity_report"
    if not val_valid:
        return "failure", "val3dity_invalid"
    return "success", "success"


def format_float(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return str(value)


def write_status_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError("No building status rows to write")
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_summary_json(
    path: Path,
    summaries: dict[str, Counter[str]],
    val_summaries: dict[str, dict[str, int | bool]],
    outputs: dict[str, dict[str, Path]],
    status_csv: Path,
) -> None:
    payload = {
        "run_id": os.environ["RUN_ID"],
        "task": "W2-1_roofer_default",
        "dim_z_offset_applied_m": DIM_Z_OFFSET_M,
        "dim_median_residual_removed_m": DIM_MEDIAN_RESIDUAL_M,
        "status_csv": rel(status_csv),
        "summaries": {label: dict(counter) for label, counter in summaries.items()},
        "val3dity": val_summaries,
        "outputs": {
            label: {name: rel(path) for name, path in spec.items() if isinstance(path, Path)}
            for label, spec in outputs.items()
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_report(
    path: Path,
    run_id: str,
    summaries: dict[str, Counter[str]],
    val_summaries: dict[str, dict[str, int | bool]],
    outputs: dict[str, dict[str, Path]],
    status_csv: Path,
) -> None:
    labels = ["ALS", "DIM"]
    all_reasons = sorted({reason for counter in summaries.values() for reason in counter})
    lines = [
        "# W2-1 Roofer Default Reconstruction",
        "",
        f"- Run ID: `{run_id}`",
        f"- Run directory: `runs/{run_id}`",
        "- AOI: `scene_aoi.gpkg` bounding box, EPSG:25832.",
        "- Footprints: `data/work/w2/footprints_scene_aoi.gpkg` from `docs/scene_aoi_buildings.csv` (199 buildings).",
        "- Input A: ALS validation LAZ tiles from `data/raw/als/`.",
        (
            "- Input B: `data/work/classify/dim_v1_classified_z.laz` with the +0.174 m "
            "median DIM-ALS residual removed (`Z := Z - 0.174 m`) as "
            "`data/work/w2/dim_v1_classified_z_minus0p174.laz`."
        ),
        "- Roofer parameters: defaults, with only `--id-attribute building_id` and `--box` for AOI plumbing.",
        "",
        "## Outputs",
        "",
    ]
    for label in labels:
        lines.extend(
            [
                f"- {label} CityJSON: `{rel(outputs[label]['cityjson'])}`",
                f"- {label} val3dity report: `{rel(outputs[label]['val_report'])}`",
            ]
        )
    lines.extend(
        [
            f"- Building success/failure CSV: `{rel(status_csv)}`",
            "",
            "## Summary",
            "",
            "| Input | Success | Failure | val3dity valid features | val3dity validity |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for label in labels:
        success = summaries[label].get("success", 0)
        total = sum(summaries[label].values())
        valid_features = val_summaries[label]["feature_valid"]
        feature_total = val_summaries[label]["feature_total"]
        validity = "valid" if val_summaries[label]["validity"] else "invalid"
        lines.append(
            f"| {label} | {success} | {total - success} | {valid_features}/{feature_total} | {validity} |"
        )
    lines.extend(["", "## Failure Reason Counts", "", "| Reason | ALS | DIM |", "|---|---:|---:|"])
    for reason in all_reasons:
        lines.append(f"| `{reason}` | {summaries['ALS'].get(reason, 0)} | {summaries['DIM'].get(reason, 0)} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def rel(path: Path) -> str:
    return path.as_posix().replace("/workspace/", "").replace("phases/p0-audit/", "")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("host", "prepare", "postprocess"), default="host")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "host":
        host_entrypoint()
    elif args.mode == "prepare":
        tools_prepare()
    elif args.mode == "postprocess":
        tools_postprocess()
    else:
        raise AssertionError(args.mode)


if __name__ == "__main__":
    main()

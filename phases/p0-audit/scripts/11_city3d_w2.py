#!/usr/bin/env python3
"""Run W2-2 City3D default paired comparison.

Run from phases/p0-audit/. The host entrypoint orchestrates Docker Compose services.
Container modes prepare per-building City3D inputs, execute City3D, and
post-process OBJ validation/status outputs.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from p0_paths import P0_EVIDENCE


TASK_ID = "W2-2"
W2_1_RUN_ID = "w2_1_roofer_default_20260612_152729"
CITY3D_SOURCE_COMMIT = "c9299efe61625f03a78245683eaa155a9670df0e"
CITY3D_MIN_POINTS = 40
CITY3D_PIXEL_SIZE_M = 0.15
POINT_CLASS_FILTER = 6
DIM_Z_OFFSET_M = -0.174


STATUS_FIELDS = [
    "input",
    "building_id",
    "status",
    "reason",
    "rf_success",
    "rf_extrusion_mode",
    "rf_pointcloud_unusable",
    "rf_roof_type",
    "rf_pt_density",
    "rf_nodata_frac",
    "rf_rmse_lod22",
    "rf_roof_planes",
    "has_lod22",
    "val3dity_valid",
    "val3dity_errors",
]


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("w2_2_city3d_default_%Y%m%d_%H%M%S")
    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()
    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]
    write_host_config(run_dir, run_id, git_commit)

    try:
        if env.get("SKIP_BUILD") != "1":
            run(compose + ["build", "tools"], cwd=repo, env=env, log_path=logs_dir / "build_tools.log")
            run(compose + ["build", "city3d"], cwd=repo, env=env, log_path=logs_dir / "build_city3d.log")
        write_host_versions(repo, run_dir, compose, env, git_commit)
    except subprocess.CalledProcessError as exc:
        record_issue(
            repo,
            run_id,
            f"City3D build/version step failed with exit code {exc.returncode}; see runs/{run_id}/logs/.",
        )
        raise

    city3d_workers = env.get("CITY3D_WORKERS", "2")
    city3d_timeout_sec = env.get("CITY3D_TIMEOUT_SEC", "240")
    common_env = [
        "-e",
        f"RUN_ID={run_id}",
        "-e",
        f"P0_GIT_COMMIT={git_commit}",
    ]
    city3d_env = common_env + [
        "-e",
        f"CITY3D_WORKERS={city3d_workers}",
        "-e",
        f"CITY3D_TIMEOUT_SEC={city3d_timeout_sec}",
    ]
    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            *city3d_env,
            "tools",
            "python",
            "/workspace/scripts/11_city3d_w2.py",
            "--mode",
            "prepare",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "prepare.log",
    )
    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            *city3d_env,
            "city3d",
            "python",
            "/workspace/scripts/11_city3d_w2.py",
            "--mode",
            "run-city3d",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "city3d.log",
    )
    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            *city3d_env,
            "tools",
            "python",
            "/workspace/scripts/11_city3d_w2.py",
            "--mode",
            "postprocess",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "postprocess.log",
    )

    print(f"run_id={run_id}")
    print(f"run_dir=runs/{run_id}")
    print("report=docs/W2_2_city3d_default.md")


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


def record_issue(repo: Path, run_id: str, message: str) -> None:
    path = repo / "phases/p0-audit/issues.md"
    text = path.read_text(encoding="utf-8") if path.exists() else "# P0 Issues\n"
    section = "\n## W2-2 City3D Default\n\n"
    if "## W2-2 City3D Default" not in text:
        text = text.rstrip() + section
    text = text.rstrip() + f"\n- {run_id}: {message}\n"
    path.write_text(text, encoding="utf-8")


def write_host_config(run_dir: Path, run_id: str, git_commit: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "task": "W2-2_city3d_default",
        "run_id": run_id,
        "git_commit": git_commit,
        "crs": "EPSG:25832",
        "city3d_source": "https://github.com/tudelft3d/City3D",
        "city3d_commit": CITY3D_SOURCE_COMMIT,
        "city3d_parameters": {
            "min_points": CITY3D_MIN_POINTS,
            "pixel_size_m": CITY3D_PIXEL_SIZE_M,
            "solver": "SCIP",
        },
        "city3d_execution": {
            "workers": int(os.environ.get("CITY3D_WORKERS", "2")),
            "timeout_sec": int(os.environ.get("CITY3D_TIMEOUT_SEC", "240")),
            "resume_reuses_existing_outputs": True,
        },
        "point_cloud_filter": {
            "classification": POINT_CLASS_FILTER,
            "classification_name": "building",
            "reason": "City3D does not consume ASPRS classes directly; roof/building points are clipped per footprint.",
        },
        "inputs": {
            "A_ALS": "data/raw/als/*.laz",
            "B_DIM": "data/work/w2/dim_v1_classified_z_minus0p174.laz",
            "DIM_z_offset_m": DIM_Z_OFFSET_M,
            "footprints_gpkg": "data/work/w2/footprints_scene_aoi.gpkg",
            "footprints_city3d_geojson": "data/work/w2_city3d/footprints_scene_aoi.geojson",
        },
        "outputs": {
            "models": f"runs/{run_id}/models/",
            "val3dity": f"runs/{run_id}/val3dity/",
            "status_csv": f"runs/{run_id}/building_reconstruction_status.csv",
            "paired_csv": "docs/W2_2_city3d_paired_status.csv",
            "success_rates": "docs/W2_2_city3d_success_rates.csv",
            "two_by_two": "docs/W2_2_roofer_city3d_2x2.csv",
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
        "# W2-2 Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {run_dir.name}",
        f"- Repository commit: {git_commit}",
        f"- City3D source commit: {CITY3D_SOURCE_COMMIT}",
        "",
        "```console",
    ]
    commands = [
        ["git", "status", "--short", "--branch"],
        [*compose, "images"],
        [*compose, "run", "-T", "--rm", "city3d", "city3d_cli", "--version"],
        [*compose, "run", "-T", "--rm", "tools", "val3dity", "--version"],
        [*compose, "run", "-T", "--rm", "tools", "pdal", "--version"],
        [
            *compose,
            "run",
            "-T",
            "--rm",
            "tools",
            "python",
            "-c",
            "import laspy, matplotlib, numpy; print('laspy ' + laspy.__version__); print('matplotlib ' + matplotlib.__version__); print('numpy ' + numpy.__version__)",
        ],
    ]
    for cmd in commands:
        lines.append("$ " + " ".join(cmd))
        lines.append(capture(cmd, cwd=repo, env=env))
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare_entrypoint() -> None:
    import laspy
    import numpy as np
    from matplotlib.path import Path as MplPath

    root = Path("/workspace")
    data = root / "data"
    docs = P0_EVIDENCE
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    inputs_dir = run_dir / "city3d_inputs"
    footprints_dir = inputs_dir / "footprints"
    work_city3d = data / "work/w2_city3d"
    for path in (inputs_dir, footprints_dir, work_city3d):
        path.mkdir(parents=True, exist_ok=True)

    building_ids = read_building_ids(docs / "scene_aoi_buildings.csv")
    footprints = load_footprints(data / "work/footprints/lod2_ground_plan.geojson", building_ids)
    if len(footprints) != 199:
        raise RuntimeError(f"Expected 199 footprints, found {len(footprints)}")

    subset_geojson = work_city3d / "footprints_scene_aoi.geojson"
    write_feature_collection(subset_geojson, [footprints[bid]["feature"] for bid in building_ids])
    for bid in building_ids:
        write_feature_collection(footprints_dir / f"{bid}.geojson", [footprints[bid]["feature"]])

    source_specs = {
        "ALS": sorted((data / "raw/als").glob("*.laz")),
        "DIM": [data / "work/w2/dim_v1_classified_z_minus0p174.laz"],
    }
    manifest_rows: list[dict[str, str]] = []
    for label, paths in source_specs.items():
        if not paths or any(not path.exists() for path in paths):
            raise RuntimeError(f"Missing source paths for {label}: {[str(path) for path in paths]}")
        output_dir = inputs_dir / label.lower()
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"preparing_city3d_ply input={label} sources={len(paths)} buildings={len(building_ids)}", flush=True)
        point_counts = write_city3d_plys(
            laspy=laspy,
            np=np,
            MplPath=MplPath,
            source_paths=paths,
            footprints=[footprints[bid] for bid in building_ids],
            output_dir=output_dir,
        )
        for bid in building_ids:
            footprint = footprints[bid]
            count = point_counts[bid]
            area = float(footprint["properties"]["area_m2"])
            manifest_rows.append(
                {
                    "input": label,
                    "building_id": bid,
                    "point_count": str(count),
                    "footprint_area_m2": f"{area:.3f}",
                    "point_density_pts_m2": f"{(count / area if area > 0 else 0.0):.6f}",
                    "point_cloud": rel(output_dir / f"{bid}.ply"),
                    "footprint_geojson": rel(footprints_dir / f"{bid}.geojson"),
                    "output_obj": rel(run_dir / "models" / label.lower() / f"{bid}.obj"),
                }
            )
    manifest_path = run_dir / "city3d_input_manifest.csv"
    write_csv(manifest_path, manifest_rows)
    print(f"footprints_geojson={rel(subset_geojson)}")
    print(f"manifest={rel(manifest_path)}")


def read_building_ids(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        ids = [row["building_id"] for row in csv.DictReader(fh)]
    if len(ids) != len(set(ids)):
        duplicates = [bid for bid, count in Counter(ids).items() if count > 1]
        raise RuntimeError(f"Duplicate building_id values in {path}: {duplicates[:5]}")
    return ids


def load_footprints(path: Path, building_ids: list[str]) -> dict[str, dict[str, Any]]:
    wanted = set(building_ids)
    payload = json.loads(path.read_text(encoding="utf-8"))
    footprints: dict[str, dict[str, Any]] = {}
    for feature in payload["features"]:
        props = dict(feature["properties"])
        bid = props.get("building_id")
        if bid not in wanted:
            continue
        coords = feature["geometry"]["coordinates"]
        if feature["geometry"]["type"] == "Polygon":
            ring = coords[0]
        elif feature["geometry"]["type"] == "MultiPolygon":
            ring = coords[0][0]
        else:
            continue
        if ring[0] != ring[-1]:
            ring = [*ring, ring[0]]
        props["area_m2"] = float(props["area_m2"])
        props["min_x"] = float(props["min_x"])
        props["min_y"] = float(props["min_y"])
        props["max_x"] = float(props["max_x"])
        props["max_y"] = float(props["max_y"])
        clean_feature = {
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        }
        footprints[bid] = {"feature": clean_feature, "properties": props, "ring": ring}
    missing = [bid for bid in building_ids if bid not in footprints]
    if missing:
        raise RuntimeError(f"Missing footprints for {len(missing)} building ids; first={missing[:5]}")
    return footprints


def write_feature_collection(path: Path, features: list[dict[str, Any]]) -> None:
    payload = {
        "type": "FeatureCollection",
        "name": path.stem,
        "crs": {"type": "name", "properties": {"name": "EPSG:25832"}},
        "features": features,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def write_city3d_plys(
    laspy: Any,
    np: Any,
    MplPath: Any,
    source_paths: list[Path],
    footprints: list[dict[str, Any]],
    output_dir: Path,
) -> dict[str, int]:
    counts = {fp["properties"]["building_id"]: 0 for fp in footprints}
    paths = {
        fp["properties"]["building_id"]: MplPath(np.asarray(fp["ring"], dtype=np.float64))
        for fp in footprints
    }
    bbox_index = [
        (
            fp["properties"]["building_id"],
            fp["properties"]["min_x"],
            fp["properties"]["min_y"],
            fp["properties"]["max_x"],
            fp["properties"]["max_y"],
        )
        for fp in footprints
    ]

    for source in source_paths:
        print(f"counting_points source={source}", flush=True)
        with laspy.open(source) as reader:
            for points in reader.chunk_iterator(750_000):
                x, y, z = filtered_xyz(np, points)
                if x.size == 0:
                    continue
                accumulate_counts(np, paths, bbox_index, x, y, counts)

    handles: dict[str, Any] = {}
    try:
        for bid, count in counts.items():
            path = output_dir / f"{bid}.ply"
            fh = path.open("wb")
            handles[bid] = fh
            header = (
                "ply\n"
                "format binary_little_endian 1.0\n"
                f"element vertex {count}\n"
                "property double x\n"
                "property double y\n"
                "property double z\n"
                "end_header\n"
            )
            fh.write(header.encode("ascii"))

        for source in source_paths:
            print(f"writing_points source={source}", flush=True)
            with laspy.open(source) as reader:
                for points in reader.chunk_iterator(750_000):
                    x, y, z = filtered_xyz(np, points)
                    if x.size == 0:
                        continue
                    write_points(np, paths, bbox_index, x, y, z, handles)
    finally:
        for fh in handles.values():
            fh.close()

    total_points = sum(counts.values())
    print(f"prepared_ply_dir={output_dir} total_class6_points={total_points}", flush=True)
    return counts


def filtered_xyz(np: Any, points: Any) -> tuple[Any, Any, Any]:
    classes = np.asarray(points.classification)
    mask = classes == POINT_CLASS_FILTER
    if not np.any(mask):
        return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64)
    return (
        np.asarray(points.x)[mask],
        np.asarray(points.y)[mask],
        np.asarray(points.z)[mask],
    )


def accumulate_counts(
    np: Any,
    paths: dict[str, Any],
    bbox_index: list[tuple[str, float, float, float, float]],
    x: Any,
    y: Any,
    counts: dict[str, int],
) -> None:
    xy = None
    for bid, min_x, min_y, max_x, max_y in bbox_index:
        mask = (x >= min_x) & (x <= max_x) & (y >= min_y) & (y <= max_y)
        if not np.any(mask):
            continue
        if xy is None:
            xy = np.column_stack((x, y))
        inside = paths[bid].contains_points(xy[mask], radius=1e-9)
        counts[bid] += int(np.count_nonzero(inside))


def write_points(
    np: Any,
    paths: dict[str, Any],
    bbox_index: list[tuple[str, float, float, float, float]],
    x: Any,
    y: Any,
    z: Any,
    handles: dict[str, Any],
) -> None:
    xy = None
    for bid, min_x, min_y, max_x, max_y in bbox_index:
        bbox_mask = (x >= min_x) & (x <= max_x) & (y >= min_y) & (y <= max_y)
        if not np.any(bbox_mask):
            continue
        if xy is None:
            xy = np.column_stack((x, y))
        candidate_idx = np.flatnonzero(bbox_mask)
        inside = paths[bid].contains_points(xy[candidate_idx], radius=1e-9)
        if not np.any(inside):
            continue
        idx = candidate_idx[inside]
        xyz = np.column_stack((x[idx], y[idx], z[idx])).astype("<f8", copy=False)
        xyz.tofile(handles[bid])


def city3d_entrypoint() -> None:
    root = Path("/workspace")
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    manifest = read_csv(run_dir / "city3d_input_manifest.csv")
    manifest.sort(key=lambda row: (int(row["point_count"]), row["input"], row["building_id"]))
    logs_dir = run_dir / "logs/city3d_buildings"
    logs_dir.mkdir(parents=True, exist_ok=True)
    for label in ("als", "dim"):
        (run_dir / "models" / label).mkdir(parents=True, exist_ok=True)

    timeout_sec = int(os.environ.get("CITY3D_TIMEOUT_SEC", "240"))
    workers = max(1, int(os.environ.get("CITY3D_WORKERS", "2")))
    print(f"city3d_jobs={len(manifest)} workers={workers} timeout_sec={timeout_sec}", flush=True)

    started = time.monotonic()
    rows: list[dict[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_city3d_one, row, logs_dir, timeout_sec) for row in manifest]
        for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            result = future.result()
            rows.append(result)
            if index % 25 == 0 or index == len(futures):
                elapsed = time.monotonic() - started
                print(f"city3d_progress={index}/{len(futures)} elapsed_sec={elapsed:.1f}", flush=True)

    rows.sort(key=lambda row: (row["input"], row["building_id"]))
    results_csv = run_dir / "city3d_run_results.csv"
    write_csv(results_csv, rows)
    print(f"city3d_results={rel(results_csv)}")


def run_city3d_one(row: dict[str, str], logs_dir: Path, timeout_sec: int) -> dict[str, str]:
    label = row["input"].lower()
    bid = row["building_id"]
    point_count = int(row["point_count"])
    point_cloud = Path("/workspace") / row["point_cloud"]
    footprint = Path("/workspace") / row["footprint_geojson"]
    output_obj = Path("/workspace") / row["output_obj"]
    output_obj.parent.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / label / f"{bid}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    if point_count < CITY3D_MIN_POINTS:
        log_file.write_text(
            f"skipped: point_count {point_count} < City3D min_points {CITY3D_MIN_POINTS}\n",
            encoding="utf-8",
        )
        return city3d_result_row(row, 0, 0.0, log_file, "low_points")
    reused = reuse_existing_city3d_result(row, log_file, output_obj)
    if reused is not None:
        return reused

    cmd = ["city3d_cli", point_cloud.as_posix(), footprint.as_posix(), output_obj.as_posix()]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_sec,
            check=False,
        )
        elapsed = time.monotonic() - started
        log_file.write_text("+ " + " ".join(cmd) + "\n" + proc.stdout, encoding="utf-8")
        return city3d_result_row(row, proc.returncode, elapsed, log_file, "")
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        log_file.write_text(
            "+ " + " ".join(cmd) + "\n" + output + f"\nTIMEOUT after {timeout_sec} sec\n",
            encoding="utf-8",
        )
        return city3d_result_row(row, 124, elapsed, log_file, "timeout")


def reuse_existing_city3d_result(row: dict[str, str], log_file: Path, output_obj: Path) -> dict[str, str] | None:
    if output_obj.exists() and output_obj.stat().st_size > 0 and count_obj_faces(output_obj) > 0:
        return city3d_result_row(row, 0, 0.0, log_file, "reused_existing_output")
    if not log_file.exists():
        return None
    text = read_short_log(log_file)
    if "TIMEOUT after" in text:
        return city3d_result_row(row, 124, 0.0, log_file, "timeout")
    if "no roofs could be extracted" in text or "reconstruction failed" in text:
        return city3d_result_row(row, 1, 0.0, log_file, "reused_existing_failure")
    return None


def city3d_result_row(
    manifest_row: dict[str, str],
    returncode: int,
    elapsed_sec: float,
    log_file: Path,
    skipped_reason: str,
) -> dict[str, str]:
    output_obj = Path("/workspace") / manifest_row["output_obj"]
    return {
        "input": manifest_row["input"],
        "building_id": manifest_row["building_id"],
        "point_count": manifest_row["point_count"],
        "footprint_area_m2": manifest_row["footprint_area_m2"],
        "point_density_pts_m2": manifest_row["point_density_pts_m2"],
        "returncode": str(returncode),
        "elapsed_sec": f"{elapsed_sec:.3f}",
        "skipped_reason": skipped_reason,
        "output_obj": manifest_row["output_obj"],
        "output_exists": yesno(output_obj.exists() and output_obj.stat().st_size > 0),
        "output_size_bytes": str(output_obj.stat().st_size if output_obj.exists() else 0),
        "log_file": rel(log_file),
    }


def postprocess_entrypoint() -> None:
    root = Path("/workspace")
    docs = P0_EVIDENCE
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    val_dir = run_dir / "val3dity"
    val_dir.mkdir(parents=True, exist_ok=True)

    manifest = read_csv(run_dir / "city3d_input_manifest.csv")
    run_results = {(row["input"], row["building_id"]): row for row in read_csv(run_dir / "city3d_run_results.csv")}
    val_rows = validate_city3d_objs(run_dir, val_dir, manifest, run_results)
    val_by_key = {(row["input"], row["building_id"]): row for row in val_rows}
    write_csv(run_dir / "val3dity_summary.csv", val_rows)

    status_rows = build_city3d_status(manifest, run_results, val_by_key)
    write_csv(run_dir / "building_reconstruction_status.csv", status_rows, fieldnames=STATUS_FIELDS)

    paired_rows = build_paired_rows(docs / "W2_1c_paired_status.csv", status_rows)
    success_rows = build_success_rates(paired_rows)
    two_by_two_rows = build_two_by_two(paired_rows)
    failure_rows = build_failure_reason_counts(status_rows)

    outputs = [
        (docs / "W2_2_city3d_paired_status.csv", paired_rows),
        (docs / "W2_2_city3d_success_rates.csv", success_rows),
        (docs / "W2_2_roofer_city3d_2x2.csv", two_by_two_rows),
        (docs / "W2_2_city3d_failure_reasons.csv", failure_rows),
    ]
    for path, rows in outputs:
        write_csv(path, rows)
    report = docs / "W2_2_city3d_default.md"
    write_report(report, run_id, success_rows, two_by_two_rows, failure_rows)
    copy_outputs(run_dir, [path for path, _ in outputs] + [report])

    print(f"status_csv={rel(run_dir / 'building_reconstruction_status.csv')}")
    print(f"paired_csv={rel(docs / 'W2_2_city3d_paired_status.csv')}")
    print(f"success_rates={rel(docs / 'W2_2_city3d_success_rates.csv')}")
    print(f"two_by_two={rel(docs / 'W2_2_roofer_city3d_2x2.csv')}")
    print(f"report={rel(report)}")


def validate_city3d_objs(
    run_dir: Path,
    val_dir: Path,
    manifest: list[dict[str, str]],
    run_results: dict[tuple[str, str], dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    total = len(manifest)
    for index, item in enumerate(manifest, start=1):
        label = item["input"]
        bid = item["building_id"]
        result = run_results[(label, bid)]
        obj = Path("/workspace") / item["output_obj"]
        report = val_dir / label.lower() / f"{bid}.json"
        log = val_dir / label.lower() / f"{bid}.log"
        report.parent.mkdir(parents=True, exist_ok=True)
        log.parent.mkdir(parents=True, exist_ok=True)
        valid = ""
        errors = ""
        returncode = ""
        if obj.exists() and obj.stat().st_size > 0 and count_obj_faces(obj) > 0:
            proc = subprocess.run(
                ["val3dity", obj.as_posix(), "--report", report.as_posix()],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            log.write_text(proc.stdout, encoding="utf-8")
            returncode = str(proc.returncode)
            if report.exists():
                payload = json.loads(report.read_text(encoding="utf-8"))
                valid = str(report_validity(payload))
                errors = json.dumps(extract_val_errors(payload), ensure_ascii=False, separators=(",", ":"))
        rows.append(
            {
                "input": label,
                "building_id": bid,
                "val3dity_returncode": returncode,
                "val3dity_valid": valid,
                "val3dity_errors": errors,
                "val3dity_report": rel(report) if report.exists() else "",
                "val3dity_log": rel(log) if log.exists() else "",
                "obj_faces": str(count_obj_faces(obj) if obj.exists() else 0),
                "city3d_returncode": result["returncode"],
                "city3d_log": result["log_file"],
            }
        )
        if index % 50 == 0 or index == total:
            print(f"val3dity_progress={index}/{total}", flush=True)
    return rows


def count_obj_faces(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if line.startswith("f "):
                count += 1
    return count


def report_validity(payload: dict[str, Any]) -> bool:
    if "validity" in payload:
        return bool(payload["validity"])
    if "features" in payload:
        features = payload.get("features") or []
        if features:
            return all(bool(item.get("validity", False)) for item in features)
    primitives = payload.get("primitives") or []
    if primitives:
        return all(bool(item.get("validity", False)) for item in primitives)
    return False


def extract_val_errors(payload: Any) -> list[Any]:
    found: list[Any] = []

    def visit(value: Any) -> None:
        if len(found) >= 20:
            return
        if isinstance(value, dict):
            if "errors" in value and value["errors"]:
                found.append(value["errors"])
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return found


def build_city3d_status(
    manifest: list[dict[str, str]],
    run_results: dict[tuple[str, str], dict[str, str]],
    val_by_key: dict[tuple[str, str], dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in manifest:
        label = item["input"]
        bid = item["building_id"]
        result = run_results[(label, bid)]
        val = val_by_key.get((label, bid), {})
        point_count = int(item["point_count"])
        density = float(item["point_density_pts_m2"])
        obj = Path("/workspace") / item["output_obj"]
        obj_faces = int(val.get("obj_faces", "0") or 0)
        val_valid = parse_bool(val.get("val3dity_valid", ""))
        log_text = read_short_log(Path("/workspace") / result["log_file"])
        status, reason = classify_city3d_reason(point_count, result, obj, obj_faces, val_valid, bool(val), log_text)
        pointcloud_unusable = reason in {"pointcloud_unusable_no_points", "pointcloud_unusable_low_points"}
        rows.append(
            {
                "input": label,
                "building_id": bid,
                "status": status,
                "reason": reason,
                "rf_success": str(status == "success"),
                "rf_extrusion_mode": "city3d_obj" if obj_faces > 0 else "",
                "rf_pointcloud_unusable": str(pointcloud_unusable),
                "rf_roof_type": "city3d",
                "rf_pt_density": f"{density:.6f}",
                "rf_nodata_frac": "",
                "rf_rmse_lod22": "",
                "rf_roof_planes": "",
                "has_lod22": str(obj_faces > 0),
                "val3dity_valid": str(val_valid) if val.get("val3dity_valid", "") else "",
                "val3dity_errors": val.get("val3dity_errors", ""),
            }
        )
    return rows


def classify_city3d_reason(
    point_count: int,
    result: dict[str, str],
    obj: Path,
    obj_faces: int,
    val_valid: bool,
    has_val_row: bool,
    log_text: str,
) -> tuple[str, str]:
    if point_count == 0:
        return "failure", "pointcloud_unusable_no_points"
    if result["skipped_reason"] == "low_points":
        return "failure", "pointcloud_unusable_low_points"
    if result["skipped_reason"] == "timeout":
        return "failure", "city3d_timeout"
    if result["returncode"] != "0":
        if "no roofs could be extracted" in log_text:
            return "failure", "city3d_no_roofs_extracted"
        if "reconstruction failed" in log_text:
            return "failure", "city3d_reconstruction_failed"
        return "failure", "city3d_execution_failed"
    if not obj.exists() or obj.stat().st_size == 0:
        return "failure", "missing_city3d_output"
    if obj_faces == 0:
        return "failure", "missing_lod22_geometry"
    if not has_val_row:
        return "failure", "missing_val3dity_report"
    if not val_valid:
        return "failure", "val3dity_invalid"
    return "success", "success"


def read_short_log(path: Path, limit: int = 12000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text[-limit:]


def build_paired_rows(w2_1c_csv: Path, status_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    w2_rows = read_csv(w2_1c_csv)
    status_by_key = {(row["input"], row["building_id"]): row for row in status_rows}
    paired: list[dict[str, str]] = []
    for base in w2_rows:
        bid = base["building_id"]
        als = status_by_key[("ALS", bid)]
        dim = status_by_key[("DIM", bid)]
        als_success = als["status"] == "success"
        dim_success = dim["status"] == "success"
        if als_success and dim_success:
            category = "both_success"
        elif als_success:
            category = "ALS_only"
        elif dim_success:
            category = "DIM_only"
        else:
            category = "both_fail"
        paired.append(
            {
                "building_id": bid,
                "paired_category": category,
                "w2_1c_both_attempted": base["both_attempted"],
                "w2_1c_coverage_control_population": base["coverage_control_population"],
                "w2_1c_als_bucket": base["als_failure_bucket_v1"],
                "w2_1c_dim_bucket": base["dim_failure_bucket_v1"],
                "reference_mismatch_exclude": base["reference_mismatch_exclude"],
                "exclude_reason": base.get("exclude_reason", ""),
                "city3d_als_status": als["status"],
                "city3d_als_reason": als["reason"],
                "city3d_als_density": als["rf_pt_density"],
                "city3d_als_val3dity_valid": als["val3dity_valid"],
                "city3d_dim_status": dim["status"],
                "city3d_dim_reason": dim["reason"],
                "city3d_dim_density": dim["rf_pt_density"],
                "city3d_dim_val3dity_valid": dim["val3dity_valid"],
                "roofer_als_status": base["als_status"],
                "roofer_dim_status": base["dim_status"],
            }
        )
    return paired


def build_success_rates(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    populations = [
        ("full_199", lambda row: True),
        ("both_attempted_179", lambda row: row["w2_1c_both_attempted"] == "yes"),
        ("coverage_controlled", lambda row: row["w2_1c_coverage_control_population"] == "yes"),
    ]
    output: list[dict[str, str]] = []
    for name, predicate in populations:
        selected = [row for row in rows if predicate(row)]
        n = len(selected)
        als_success = sum(row["city3d_als_status"] == "success" for row in selected)
        dim_success = sum(row["city3d_dim_status"] == "success" for row in selected)
        both_success = sum(row["paired_category"] == "both_success" for row in selected)
        als_only = sum(row["paired_category"] == "ALS_only" for row in selected)
        dim_only = sum(row["paired_category"] == "DIM_only" for row in selected)
        both_fail = sum(row["paired_category"] == "both_fail" for row in selected)
        output.append(
            {
                "population": name,
                "n": str(n),
                "als_success": fmt_count_rate(als_success, n),
                "dim_success": fmt_count_rate(dim_success, n),
                "both_success": fmt_count_rate(both_success, n),
                "als_only": fmt_count_rate(als_only, n),
                "dim_only": fmt_count_rate(dim_only, n),
                "both_fail": fmt_count_rate(both_fail, n),
            }
        )
    return output


def build_two_by_two(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected = [row for row in rows if row["w2_1c_coverage_control_population"] == "yes"]
    n = len(selected)
    return [
        {
            "input": "ALS",
            "population": "coverage_controlled",
            "n": str(n),
            "roofer_success": fmt_count_rate(sum(row["roofer_als_status"] == "success" for row in selected), n),
            "city3d_success": fmt_count_rate(sum(row["city3d_als_status"] == "success" for row in selected), n),
        },
        {
            "input": "DIM",
            "population": "coverage_controlled",
            "n": str(n),
            "roofer_success": fmt_count_rate(sum(row["roofer_dim_status"] == "success" for row in selected), n),
            "city3d_success": fmt_count_rate(sum(row["city3d_dim_status"] == "success" for row in selected), n),
        },
    ]


def build_failure_reason_counts(status_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    counters: dict[str, Counter[str]] = {"ALS": Counter(), "DIM": Counter()}
    for row in status_rows:
        counters[row["input"]][row["reason"]] += 1
    reasons = sorted(set(counters["ALS"]) | set(counters["DIM"]))
    return [{"reason": reason, "ALS": str(counters["ALS"][reason]), "DIM": str(counters["DIM"][reason])} for reason in reasons]


def write_report(
    path: Path,
    run_id: str,
    success_rows: list[dict[str, str]],
    two_by_two_rows: list[dict[str, str]],
    failure_rows: list[dict[str, str]],
) -> None:
    workers = os.environ.get("CITY3D_WORKERS", "2")
    timeout_sec = os.environ.get("CITY3D_TIMEOUT_SEC", "240")
    lines = [
        "# W2-2 City3D Default Reconstruction",
        "",
        f"- Run ID: `{run_id}`",
        f"- Run directory: `runs/{run_id}`",
        "- Input A: ALS LAZ tiles from `data/raw/als/`.",
        "- Input B: `data/work/w2/dim_v1_classified_z_minus0p174.laz`.",
        "- Footprints: `data/work/w2_city3d/footprints_scene_aoi.geojson` converted from the same W2 GPKG subset.",
        (
            f"- City3D defaults: `Method::min_points={CITY3D_MIN_POINTS}`, "
            f"`Method::pixel_size={CITY3D_PIXEL_SIZE_M}`; source commit `{CITY3D_SOURCE_COMMIT}`."
        ),
        f"- City3D input point filter: ASPRS class `{POINT_CLASS_FILTER}` per footprint.",
        f"- City3D execution: `CITY3D_WORKERS={workers}`, `CITY3D_TIMEOUT_SEC={timeout_sec}`.",
        "",
        "## Outputs",
        "",
        f"- Model set: `runs/{run_id}/models/`",
        f"- val3dity reports: `runs/{run_id}/val3dity/`",
        f"- Building status CSV: `runs/{run_id}/building_reconstruction_status.csv`",
        "- Paired CSV: `docs/W2_2_city3d_paired_status.csv`",
        "- Success rates: `docs/W2_2_city3d_success_rates.csv`",
        "- Roofer/City3D 2x2: `docs/W2_2_roofer_city3d_2x2.csv`",
        "",
        "## Execution Notes",
        "",
        "- The City3D container builds the upstream command-line example only; GUI/Qt targets are excluded.",
        "- Each building uses one footprint GeoJSON and one clipped PLY containing class 6 points.",
        "- Resume mode reuses existing non-empty OBJ outputs and existing timeout/failure logs.",
        "- Per-building timeouts and reconstruction failures are kept in `building_reconstruction_status.csv` as failure reasons.",
        "",
        "## Success Rates",
        "",
        "| population | n | ALS success | DIM success | both success | ALS only | DIM only | both fail |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in success_rows:
        lines.append(
            "| {population} | {n} | {als_success} | {dim_success} | {both_success} | {als_only} | {dim_only} | {both_fail} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            "## Coverage-Controlled 2x2",
            "",
            "| input | n | Roofer success | City3D success |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for row in two_by_two_rows:
        lines.append(f"| {row['input']} | {row['n']} | {row['roofer_success']} | {row['city3d_success']} |")
    lines.extend(["", "## City3D Failure Reasons", "", "| reason | ALS | DIM |", "| --- | ---: | ---: |"])
    for row in failure_rows:
        lines.append(f"| `{row['reason']}` | {row['ALS']} | {row['DIM']} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def copy_outputs(run_dir: Path, docs: list[Path]) -> None:
    snapshot = run_dir / "docs_snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in docs:
        shutil.copy2(path, snapshot / path.name)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str] | None = None) -> None:
    if not rows:
        raise RuntimeError(f"No rows for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    names = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def fmt_count_rate(count: int, total: int) -> str:
    if total <= 0:
        return "0/0 (nan)"
    return f"{count}/{total} ({count / total * 100:.1f}%)"


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "valid"}


def yesno(value: bool) -> str:
    return "yes" if value else "no"


def rel(path: Path) -> str:
    return path.as_posix().replace("/workspace/", "").replace("phases/p0-audit/", "")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("host", "prepare", "run-city3d", "postprocess"), default="host")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "host":
        host_entrypoint()
    elif args.mode == "prepare":
        prepare_entrypoint()
    elif args.mode == "run-city3d":
        city3d_entrypoint()
    elif args.mode == "postprocess":
        postprocess_entrypoint()
    else:
        raise AssertionError(args.mode)


if __name__ == "__main__":
    main()

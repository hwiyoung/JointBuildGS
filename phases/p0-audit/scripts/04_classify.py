#!/usr/bin/env python3
"""Classify DIM LAZ for Roofer input.

Run from phases/p0-audit/. The host entrypoint re-runs this script inside the P0 tools
container so PDAL/laspy work stays Docker-based.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np


TASK_ID = "T4"
GROUND = 2
BUILDING = 6
UNCLASSIFIED = 1


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
    run_id = env.get("RUN_ID") or datetime.now().strftime("t4_classify_%Y%m%d_%H%M%S")

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
                "/workspace/scripts/04_classify.py",
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
) -> None:
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
    else:
        subprocess.run(cmd, cwd=cwd, env=env, check=True)


def record_issue(repo: Path, run_id: str, message: str) -> None:
    issues = repo / "phases/p0-audit/docs/issues.md"
    with issues.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {TASK_ID} Point Classification\n\n")
        fh.write(f"- {run_id}: {message}. See runs/{run_id}/logs/.\n")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


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
    if not np.allclose(xy[0], xy[-1]):
        xy = np.vstack([xy, xy[0]])
    if ring_area(xy) < 0.25:
        return None
    return xy


def parse_lod2_ground_footprints(
    lod2_paths: list[Path],
    dim_bounds: tuple[float, float, float, float],
) -> tuple[list[np.ndarray], int]:
    min_x, min_y, max_x, max_y = dim_bounds
    selected: list[np.ndarray] = []
    total = 0

    for path in lod2_paths:
        for _, elem in ET.iterparse(path, events=("end",)):
            if local_name(elem.tag) != "GroundSurface":
                continue

            total += 1
            poslist = None
            for child in elem.iter():
                if local_name(child.tag) == "posList" and child.text:
                    poslist = child.text
                    break
            if poslist:
                xy = normalize_ring(parse_poslist(poslist))
                if xy is not None and (
                    float(np.max(xy[:, 0])) >= min_x
                    and float(np.min(xy[:, 0])) <= max_x
                    and float(np.max(xy[:, 1])) >= min_y
                    and float(np.min(xy[:, 1])) <= max_y
                ):
                    selected.append(xy)
            elem.clear()

    if not selected:
        raise RuntimeError("No LoD2 GroundSurface footprints overlap DIM bounds")
    return selected, total


def write_footprint_geojson(footprints: list[np.ndarray], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    features = []
    for idx, xy in enumerate(footprints, start=1):
        coords = [[round(float(x), 3), round(float(y), 3)] for x, y in xy]
        features.append(
            {
                "type": "Feature",
                "properties": {"id": idx, "class": BUILDING},
                "geometry": {"type": "Polygon", "coordinates": [coords]},
            }
        )
    out_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )


def write_pdal_pipeline(
    in_laz: Path,
    footprint_geojson: Path,
    out_laz: Path,
    pipeline_path: Path,
) -> None:
    out_laz.parent.mkdir(parents=True, exist_ok=True)
    smrf = {
        "type": "filters.smrf",
        "cell": float(os.environ.get("SMRF_CELL", "1.0")),
        "slope": float(os.environ.get("SMRF_SLOPE", "0.15")),
        "scalar": float(os.environ.get("SMRF_SCALAR", "1.25")),
        "threshold": float(os.environ.get("SMRF_THRESHOLD", "0.5")),
        "window": float(os.environ.get("SMRF_WINDOW", "18.0")),
        "ground_class": GROUND,
        "other_class": UNCLASSIFIED,
    }
    pipeline = {
        "pipeline": [
            {"type": "readers.las", "filename": str(in_laz)},
            smrf,
            {
                "type": "filters.overlay",
                "dimension": "Classification",
                "datasource": str(footprint_geojson),
                "column": "class",
                "where": f"Classification != {GROUND}",
                "threads": int(os.environ.get("OVERLAY_THREADS", "8")),
            },
            {
                "type": "writers.las",
                "filename": str(out_laz),
                "a_srs": "EPSG:25832",
                "minor_version": 4,
                "dataformat_id": 3,
                "compression": "lazperf",
            },
        ]
    }
    pipeline_path.write_text(json.dumps(pipeline, indent=2), encoding="utf-8")


def class_name(class_id: int) -> str:
    return {GROUND: "ground", BUILDING: "building", UNCLASSIFIED: "unclassified"}.get(
        class_id,
        "other",
    )


def histogram_laz(path: Path, sample_limit_per_class: int = 90_000) -> tuple[Counter, dict[int, np.ndarray]]:
    import laspy

    counts: Counter = Counter()
    samples: dict[int, list[np.ndarray]] = defaultdict(list)

    with laspy.open(path) as fh:
        for points in fh.chunk_iterator(1_000_000):
            cls = np.asarray(points.classification, dtype=np.uint8)
            bincount = np.bincount(cls, minlength=256)
            counts.update({idx: int(val) for idx, val in enumerate(bincount) if val})

            for class_id in (GROUND, BUILDING, UNCLASSIFIED):
                idx = np.flatnonzero(cls == class_id)
                if idx.size == 0:
                    continue
                keep = min(idx.size, 3_000)
                if idx.size > keep:
                    stride_idx = np.linspace(0, idx.size - 1, keep, dtype=np.int64)
                    idx = idx[stride_idx]
                samples[class_id].append(
                    np.column_stack(
                        [
                            np.asarray(points.x)[idx],
                            np.asarray(points.y)[idx],
                        ]
                    )
                )

    sampled: dict[int, np.ndarray] = {}
    rng = np.random.default_rng(42)
    for class_id, parts in samples.items():
        arr = np.vstack(parts) if parts else np.empty((0, 2), dtype=float)
        if arr.shape[0] > sample_limit_per_class:
            idx = rng.choice(arr.shape[0], size=sample_limit_per_class, replace=False)
            arr = arr[idx]
        sampled[class_id] = arr
    return counts, sampled


def histogram_als(paths: list[Path]) -> dict[str, Counter]:
    import laspy

    out: dict[str, Counter] = {}
    for path in paths:
        counts: Counter = Counter()
        with laspy.open(path) as fh:
            for points in fh.chunk_iterator(1_000_000):
                cls = np.asarray(points.classification, dtype=np.uint8)
                bincount = np.bincount(cls, minlength=256)
                counts.update({idx: int(val) for idx, val in enumerate(bincount) if val})
        out[path.name] = counts
    return out


def counts_table(counts: Counter) -> str:
    total = sum(counts.values())
    lines = ["| Class | Label | Points | Share |", "|---:|---|---:|---:|"]
    for class_id in sorted(k for k, v in counts.items() if v):
        count = counts[class_id]
        share = count / total * 100.0 if total else 0.0
        lines.append(f"| {class_id} | {class_name(class_id)} | {count:,} | {share:.3f}% |")
    return "\n".join(lines)


def als_table(als_counts: dict[str, Counter]) -> str:
    lines = [
        "| File | Total points | Ground(2) | Building(6) | Other classified |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, counts in sorted(als_counts.items()):
        total = sum(counts.values())
        ground = counts.get(GROUND, 0)
        building = counts.get(BUILDING, 0)
        other = total - ground - building
        lines.append(f"| {name} | {total:,} | {ground:,} | {building:,} | {other:,} |")
    return "\n".join(lines)


def write_plan_png(
    samples: dict[int, np.ndarray],
    footprints: list[np.ndarray],
    out_png: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_png.parent.mkdir(parents=True, exist_ok=True)

    focus_parts = [samples[class_id] for class_id in (GROUND, BUILDING) if class_id in samples]
    if not focus_parts:
        focus_parts = [arr for arr in samples.values() if arr.size]
    focus = np.vstack(focus_parts)
    min_x, max_x = np.percentile(focus[:, 0], [1.0, 99.0])
    min_y, max_y = np.percentile(focus[:, 1], [1.0, 99.0])
    margin = 35.0
    min_x -= margin
    max_x += margin
    min_y -= margin
    max_y += margin

    width = max_x - min_x
    height = max_y - min_y
    if width > height:
        pad = (width - height) / 2.0
        min_y -= pad
        max_y += pad
    else:
        pad = (height - width) / 2.0
        min_x -= pad
        max_x += pad

    fig, ax = plt.subplots(figsize=(14, 14))

    draw_order = [
        (UNCLASSIFIED, "#8a8a8a", 0.16, "unclassified(1)"),
        (GROUND, "#2ca02c", 0.24, "ground(2)"),
        (BUILDING, "#d62728", 0.60, "building(6)"),
    ]
    for class_id, color, alpha, label in draw_order:
        arr = samples.get(class_id)
        if arr is None or arr.size == 0:
            continue
        in_view = (
            (arr[:, 0] >= min_x)
            & (arr[:, 0] <= max_x)
            & (arr[:, 1] >= min_y)
            & (arr[:, 1] <= max_y)
        )
        arr = arr[in_view]
        if arr.size == 0:
            continue
        ax.scatter(arr[:, 0], arr[:, 1], s=0.7, c=color, alpha=alpha, linewidths=0, label=label)

    for xy in footprints:
        if (
            float(np.max(xy[:, 0])) < min_x
            or float(np.min(xy[:, 0])) > max_x
            or float(np.max(xy[:, 1])) < min_y
            or float(np.min(xy[:, 1])) > max_y
        ):
            continue
        ax.plot(xy[:, 0], xy[:, 1], color="#111111", linewidth=0.25, alpha=0.2)

    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(min_x, max_x)
    ax.set_ylim(min_y, max_y)
    ax.set_xlabel("Easting (EPSG:25832 m)")
    ax.set_ylabel("Northing (EPSG:25832 m)")
    ax.set_title("T4 DIM classification plan view (zoomed to classified core)")
    ax.legend(markerscale=8, loc="upper right")
    ax.grid(True, linewidth=0.25, alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_png, dpi=240)
    plt.close(fig)


def write_versions(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# T4 Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {os.environ['RUN_ID']}",
        f"- Repository commit: {os.environ.get('P0_GIT_COMMIT', 'unknown')}",
        "",
        "```console",
    ]
    for cmd in (
        ["pdal", "--version"],
        ["lasinfo", "--version"],
        [
            "python",
            "-c",
            "import laspy, matplotlib, numpy; print('laspy ' + laspy.__version__); print('matplotlib ' + matplotlib.__version__); print('numpy ' + numpy.__version__)",
        ],
    ):
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
        lines.append("$ " + " ".join(cmd))
        lines.append((proc.stdout or proc.stderr).strip())
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_config(run_dir: Path, values: dict[str, str | int | float]) -> None:
    lines = ["task: T4_point_classification"]
    for key, value in values.items():
        lines.append(f"{key}: {value}")
    (run_dir / "config.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    root = Path("/workspace")
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    log_dir = run_dir / "logs"
    work_dir = root / "data/work/classify"
    docs_dir = root / "docs"
    figs_dir = docs_dir / "figs"

    dim_laz = root / "data/work/mvs/dim/dim_v1.laz"
    classified_laz = work_dir / "dim_v1_classified.laz"
    footprints_geojson = work_dir / "lod2_ground_footprints.geojson"
    pipeline_json = work_dir / "dim_classify_pipeline.json"
    stats_md = docs_dir / "dim_v1_classification_stats.md"
    plan_png = figs_dir / "dim_v1_classification_plan.png"
    lod2_paths = sorted((root / "data/raw/lod2").glob("*.gml"))
    als_paths = sorted((root / "data/raw/als").glob("*.laz"))

    if not dim_laz.exists():
        raise FileNotFoundError(dim_laz)
    if not lod2_paths:
        raise FileNotFoundError(root / "data/raw/lod2")
    if not als_paths:
        raise FileNotFoundError(root / "data/raw/als")

    log_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    write_versions(run_dir)

    import laspy

    with laspy.open(dim_laz) as fh:
        h = fh.header
        dim_bounds = (float(h.mins[0]), float(h.mins[1]), float(h.maxs[0]), float(h.maxs[1]))
        dim_point_count = int(h.point_count)

    footprints, total_footprints = parse_lod2_ground_footprints(lod2_paths, dim_bounds)
    write_footprint_geojson(footprints, footprints_geojson)
    write_pdal_pipeline(dim_laz, footprints_geojson, classified_laz, pipeline_json)

    write_config(
        run_dir,
        {
            "run_id": run_id,
            "input_dim_laz": "data/work/mvs/dim/dim_v1.laz",
            "output_classified_laz": "data/work/classify/dim_v1_classified.laz",
            "footprints_geojson": "data/work/classify/lod2_ground_footprints.geojson",
            "stats": "docs/dim_v1_classification_stats.md",
            "plan_png": "docs/figs/dim_v1_classification_plan.png",
            "smrf_cell": float(os.environ.get("SMRF_CELL", "1.0")),
            "smrf_slope": float(os.environ.get("SMRF_SLOPE", "0.15")),
            "smrf_scalar": float(os.environ.get("SMRF_SCALAR", "1.25")),
            "smrf_threshold": float(os.environ.get("SMRF_THRESHOLD", "0.5")),
            "smrf_window": float(os.environ.get("SMRF_WINDOW", "18.0")),
            "dim_point_count": dim_point_count,
            "lod2_ground_footprints_total": total_footprints,
            "lod2_ground_footprints_overlapping_dim": len(footprints),
        },
    )

    if os.environ.get("FORCE") == "1" or not classified_laz.exists():
        run(["pdal", "pipeline", str(pipeline_json)], log_path=log_dir / "pdal_classify.log")

    dim_counts, samples = histogram_laz(classified_laz)
    als_counts = histogram_als(als_paths)
    write_plan_png(samples, footprints, plan_png)

    if dim_counts.get(GROUND, 0) == 0:
        raise RuntimeError("SMRF produced zero ground(2) points")
    if dim_counts.get(BUILDING, 0) == 0:
        raise RuntimeError("Footprint overlay produced zero building(6) points")

    with os.popen(f"lasinfo {classified_laz}") as pipe:
        lasinfo_text = pipe.read().strip()
    lasinfo_block = "\n".join(f"    {line}" for line in lasinfo_text.splitlines())

    stats_md.write_text(
        "\n".join(
            [
                "# DIM v1 Classification Stats",
                "",
                f"- Run ID: {run_id}",
                "- Input DIM LAZ: data/work/mvs/dim/dim_v1.laz",
                "- Output classified LAZ: data/work/classify/dim_v1_classified.laz",
                "- CRS assertion: EPSG:25832",
                f"- DIM point count before classification: {dim_point_count:,}",
                f"- LoD2 GroundSurface footprints parsed: {total_footprints:,}",
                f"- LoD2 GroundSurface footprints overlapping DIM bounds: {len(footprints):,}",
                "- Classification method: PDAL filters.smrf ground=2 other=1, then filters.overlay sets non-ground points inside LoD2 footprints to building=6.",
                "- ALS handling: source ALS files were not modified; existing classifications were counted for verification only.",
                f"- Plan view PNG: docs/figs/{plan_png.name}",
                f"- Run config: runs/{run_id}/config.yaml",
                f"- Run versions: runs/{run_id}/versions.txt",
                "",
                "## DIM Classified Counts",
                "",
                counts_table(dim_counts),
                "",
                "## ALS Existing Classification Verification",
                "",
                als_table(als_counts),
                "",
                "## lasinfo output",
                "",
                lasinfo_block,
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"dim_classified_laz={classified_laz}")
    print(f"dim_ground_points={dim_counts.get(GROUND, 0)}")
    print(f"dim_building_points={dim_counts.get(BUILDING, 0)}")
    print(f"stats={stats_md}")
    print(f"plan_png={plan_png}")


if __name__ == "__main__":
    if os.environ.get("P0_INSIDE_CONTAINER") != "1":
        host_entrypoint()
    else:
        main()

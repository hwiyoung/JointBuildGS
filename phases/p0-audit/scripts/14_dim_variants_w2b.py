#!/usr/bin/env python3
"""Run W2-3b DIM point-cloud variants through Roofer defaults.

Run from phases/p0-audit/. Host mode creates two DIM variants from the corrected DIM
cloud, runs Roofer defaults on the W2 coverage-control population, validates the
CityJSON outputs, and writes paired comparison tables against the W2-1c default
DIM baseline.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import shutil
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from p0_paths import P0_EVIDENCE


TASK_ID = "W2-3b"
BASELINE_SOURCE = str(P0_EVIDENCE / "W2_1c_paired_status.csv")
BASE_W2_RUN_ID = "w2_1_roofer_default_20260612_152729"
BASE_DIM = "/workspace/data/work/w2/dim_v1_classified_z_minus0p174.laz"
FOOTPRINTS = "/workspace/data/work/w2/footprints_scene_aoi.gpkg"
VARIANT_DIR = "/workspace/data/work/w2_3b"
AOI_BBOX = (690791.740, 5335864.050, 691154.650, 5336353.850)
ROOFER_JOBS = 32
WALL_NZ_THRESHOLD = 0.3
NORMAL_KNN = 16
THIN_RADIUS_M = 0.30
VARIANTS = [
    {
        "variant": "wall_removed",
        "hypothesis": "H-wall",
        "pointcloud_path": f"{VARIANT_DIR}/dim_wall_removed_nzge0p3.laz",
        "method": f"PDAL crop -> filters.normal(knn={NORMAL_KNN}, always_up=true) -> filters.expression(abs(NormalZ) >= {WALL_NZ_THRESHOLD})",
    },
    {
        "variant": "thinned",
        "hypothesis": "H-density",
        "pointcloud_path": f"{VARIANT_DIR}/dim_thinned_sample_r0p30.laz",
        "method": f"PDAL crop -> filters.sample(radius={THIN_RADIUS_M})",
    },
]


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("w2_3b_dim_variants_%Y%m%d_%H%M%S")
    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()
    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]

    write_host_config(run_dir, run_id, git_commit)
    write_host_versions(repo, run_dir, compose, env, git_commit)
    common_env = ["-e", f"RUN_ID={run_id}", "-e", f"P0_GIT_COMMIT={git_commit}"]

    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            *common_env,
            "tools",
            "python",
            "/workspace/scripts/14_dim_variants_w2b.py",
            "--mode",
            "prepare",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "prepare.log",
    )

    for row in read_csv(run_dir / "execution_plan.csv"):
        run_roofer_plan_row(repo, compose, env, logs_dir, row)

    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            *common_env,
            "tools",
            "python",
            "/workspace/scripts/14_dim_variants_w2b.py",
            "--mode",
            "postprocess",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "postprocess.log",
    )

    print(f"run_id={run_id}")
    print(f"run_dir=runs/{run_id}")
    print("report=docs/W2_3b_dim_variants.md")


def run_roofer_plan_row(
    repo: Path,
    compose: list[str],
    env: dict[str, str],
    logs_dir: Path,
    row: dict[str, str],
) -> None:
    cmd = [
        *compose,
        "run",
        "-T",
        "--rm",
        "roofer",
        "--id-attribute",
        "building_id",
        "--jobs",
        str(ROOFER_JOBS),
        "--box",
        *(f"{value:.3f}" for value in AOI_BBOX),
        "--filter",
        row["ogr_filter"],
        row["pointcloud_path"],
        row["footprint_path"],
        row["output_dir"],
    ]
    run(cmd, cwd=repo, env=env, log_path=logs_dir / f"roofer_{row['variant']}.log")


def prepare_entrypoint() -> None:
    root = Path("/workspace")
    docs = P0_EVIDENCE
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    baseline_rows = coverage_rows(docs / "W2_1c_paired_status.csv")
    coverage_ids = [row["building_id"] for row in baseline_rows]
    write_csv(run_dir / "coverage_control_ids.csv", [{"building_id": bid} for bid in coverage_ids])

    variant_stats = create_variants(root)
    write_csv(run_dir / "variant_pointcloud_stats.csv", variant_stats)

    plan_rows = [plan_row(run_id, variant, coverage_ids) for variant in VARIANTS]
    write_csv(run_dir / "execution_plan.csv", plan_rows)
    print(f"coverage_control_n={len(coverage_ids)}")
    print(f"variant_count={len(plan_rows)}")
    print(f"execution_plan={rel(run_dir / 'execution_plan.csv')}")


def create_variants(root: Path) -> list[dict[str, str]]:
    work = root / "data/work/w2_3b"
    work.mkdir(parents=True, exist_ok=True)
    base_crop = work / "dim_aoi_crop.laz"
    wall = work / "dim_wall_removed_nzge0p3.laz"
    thin = work / "dim_thinned_sample_r0p30.laz"
    source = root / BASE_DIM.removeprefix("/workspace/")
    force = os.environ.get("FORCE_VARIANTS") == "1"

    if force or not base_crop.exists():
        run_pdal_pipeline(
            [
                source.as_posix(),
                {"type": "filters.crop", "bounds": pdal_bounds(AOI_BBOX)},
                {
                    "type": "writers.las",
                    "filename": base_crop.as_posix(),
                    "compression": True,
                    "a_srs": "EPSG:25832",
                    "forward": "all",
                },
            ]
        )
    if force or not wall.exists():
        run_pdal_pipeline(
            [
                base_crop.as_posix(),
                {"type": "filters.normal", "knn": NORMAL_KNN, "always_up": True},
                {"type": "filters.expression", "expression": f"abs(NormalZ) >= {WALL_NZ_THRESHOLD}"},
                {
                    "type": "writers.las",
                    "filename": wall.as_posix(),
                    "compression": True,
                    "a_srs": "EPSG:25832",
                    "forward": "all",
                },
            ]
        )
    if force or not thin.exists():
        run_pdal_pipeline(
            [
                base_crop.as_posix(),
                {"type": "filters.sample", "radius": THIN_RADIUS_M},
                {
                    "type": "writers.las",
                    "filename": thin.as_posix(),
                    "compression": True,
                    "a_srs": "EPSG:25832",
                    "forward": "all",
                },
            ]
        )

    base_count = las_point_count(base_crop)
    stats = [
        variant_stat_row("base_aoi_crop", "AOI crop before variant filtering", base_crop, base_count),
        variant_stat_row("wall_removed", VARIANTS[0]["method"], wall, base_count),
        variant_stat_row("thinned", VARIANTS[1]["method"], thin, base_count),
    ]
    return stats


def variant_stat_row(variant: str, method: str, path: Path, base_count: int) -> dict[str, str]:
    count = las_point_count(path)
    area = (AOI_BBOX[2] - AOI_BBOX[0]) * (AOI_BBOX[3] - AOI_BBOX[1])
    removed = base_count - count
    return {
        "variant": variant,
        "path": rel(path),
        "method": method,
        "point_count": str(count),
        "base_aoi_point_count": str(base_count),
        "kept_fraction": f"{count / base_count:.6f}" if base_count else "",
        "removed_fraction": f"{removed / base_count:.6f}" if base_count else "",
        "aoi_planimetric_density_pts_m2": f"{count / area:.3f}" if area else "",
    }


def run_pdal_pipeline(stages: list[Any]) -> None:
    proc = subprocess.run(
        ["pdal", "pipeline", "--stdin"],
        input=json.dumps(stages),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(proc.stdout, end="")
    proc.check_returncode()


def las_point_count(path: Path) -> int:
    import laspy

    with laspy.open(path) as reader:
        return int(reader.header.point_count)


def pdal_bounds(bbox: tuple[float, float, float, float]) -> str:
    min_x, min_y, max_x, max_y = bbox
    return f"([{min_x:.3f},{max_x:.3f}],[{min_y:.3f},{max_y:.3f}])"


def plan_row(run_id: str, variant: dict[str, str], building_ids: list[str]) -> dict[str, str]:
    return {
        "variant": variant["variant"],
        "hypothesis": variant["hypothesis"],
        "building_count": str(len(building_ids)),
        "building_ids": ";".join(building_ids),
        "ogr_filter": ogr_filter(building_ids),
        "pointcloud_path": variant["pointcloud_path"],
        "footprint_path": FOOTPRINTS,
        "output_dir": f"/workspace/runs/{run_id}/roofer/{variant['variant']}",
        "method": variant["method"],
    }


def postprocess_entrypoint() -> None:
    root = Path("/workspace")
    docs = P0_EVIDENCE
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    baseline_rows = coverage_rows(docs / "W2_1c_paired_status.csv")
    baseline_by_id = {row["building_id"]: row for row in baseline_rows}
    coverage_ids = [row["building_id"] for row in baseline_rows]
    subset_by_id = read_subset_map(docs / "W2_3a_dev_subset.csv")

    status_by_variant: dict[str, list[dict[str, str]]] = {}
    status_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for variant in VARIANTS:
        variant_id = variant["variant"]
        rows, _metrics = postprocess_roofer_output(root, run_dir, variant_id, coverage_ids)
        status_by_variant[variant_id] = rows
        for row in rows:
            status_by_key[(variant_id, row["building_id"])] = row

    paired_rows = build_variant_paired_rows(baseline_rows, status_by_key, subset_by_id)
    success_rows = build_success_summary(paired_rows)
    bucket_rows = build_bucket_summary(paired_rows)
    recovery_rows = build_roof_matching_recovery_rows(baseline_rows, status_by_key, subset_by_id)
    variant_stats = read_csv(run_dir / "variant_pointcloud_stats.csv")
    density_rows = build_density_rows(paired_rows)

    outputs = [
        (docs / "W2_3b_variant_status.csv", paired_rows),
        (docs / "W2_3b_variant_success.csv", success_rows),
        (docs / "W2_3b_bucket_summary.csv", bucket_rows),
        (docs / "W2_3b_roof_matching_recovery.csv", recovery_rows),
        (docs / "W2_3b_variant_pointcloud_stats.csv", variant_stats),
        (docs / "W2_3b_variant_density_summary.csv", density_rows),
    ]
    for path, rows in outputs:
        write_csv(path, rows)
    report = docs / "W2_3b_dim_variants.md"
    write_report(report, run_id, variant_stats, success_rows, bucket_rows, recovery_rows, density_rows)
    copy_outputs(run_dir, [path for path, _rows in outputs] + [report])
    print(f"report={rel(report)}")
    print(f"variant_success={rel(docs / 'W2_3b_variant_success.csv')}")
    print(f"roof_matching_recovery={rel(docs / 'W2_3b_roof_matching_recovery.csv')}")


def postprocess_roofer_output(
    root: Path,
    run_dir: Path,
    variant_id: str,
    expected_ids: list[str],
) -> tuple[list[dict[str, str]], dict[str, str]]:
    w2 = load_w2_module(root)
    output_dir = run_dir / "roofer" / variant_id
    jsonl_files = sorted(output_dir.glob("*.city.jsonl"))
    if not jsonl_files:
        raise RuntimeError(f"No Roofer output found: {output_dir}")
    cityjson = run_dir / "cityjson" / f"dim_{variant_id}.city.json"
    val_report = run_dir / "val3dity" / f"dim_{variant_id}.json"
    val_log = val_report.with_suffix(".log")
    cityjson.parent.mkdir(parents=True, exist_ok=True)
    val_report.parent.mkdir(parents=True, exist_ok=True)
    w2.combine_cityjsonseq(jsonl_files, cityjson)
    run(["val3dity", cityjson.as_posix(), "--report", val_report.as_posix()], log_path=val_log)
    payload = json.loads(val_report.read_text(encoding="utf-8"))
    val_by_id = {
        str(feature.get("id")): feature
        for feature in payload.get("features", [])
        if feature.get("id") is not None
    }
    roofer_by_id = w2.parse_roofer_features(jsonl_files)
    rows = w2.classify_buildings("DIM", expected_ids, roofer_by_id, val_by_id)
    status_csv = run_dir / "status" / f"dim_{variant_id}.csv"
    status_csv.parent.mkdir(parents=True, exist_ok=True)
    w2.write_status_csv(status_csv, rows)
    metrics = {
        "cityjson": rel(cityjson),
        "val_report": rel(val_report),
        "status_csv": rel(status_csv),
        "feature_total": str(sum(item.get("total", 0) for item in payload.get("features_overview", []))),
        "feature_valid": str(sum(item.get("valid", 0) for item in payload.get("features_overview", []))),
        "dataset_validity": str(bool(payload.get("validity", False))),
    }
    return rows, metrics


def build_variant_paired_rows(
    baseline_rows: list[dict[str, str]],
    status_by_key: dict[tuple[str, str], dict[str, str]],
    subset_by_id: dict[str, str],
) -> list[dict[str, str]]:
    rows = []
    for base in baseline_rows:
        bid = base["building_id"]
        for variant in VARIANTS:
            variant_id = variant["variant"]
            status = status_by_key[(variant_id, bid)]
            variant_bucket = failure_bucket("DIM", status["status"], status["reason"])
            base_dim_bucket = failure_bucket("DIM", base["dim_status"], base["dim_reason"])
            rows.append(
                {
                    "building_id": bid,
                    "subset": subset_by_id.get(bid, ""),
                    "variant": variant_id,
                    "hypothesis": variant["hypothesis"],
                    "als_baseline_status": base["als_status"],
                    "als_baseline_reason": base["als_reason"],
                    "dim_baseline_status": base["dim_status"],
                    "dim_baseline_reason": base["dim_reason"],
                    "dim_baseline_bucket_v1": base_dim_bucket,
                    "variant_status": status["status"],
                    "variant_reason": status["reason"],
                    "variant_bucket_v1": variant_bucket,
                    "variant_rf_pt_density": status["rf_pt_density"],
                    "variant_rf_nodata_frac": status["rf_nodata_frac"],
                    "variant_rf_rmse_lod22": status["rf_rmse_lod22"],
                    "variant_has_lod22": status["has_lod22"],
                    "variant_val3dity_valid": status["val3dity_valid"],
                    "baseline_pair_category": pair_category(base["als_status"], base["dim_status"]),
                    "variant_pair_category": pair_category(base["als_status"], status["status"]),
                }
            )
    return rows


def build_success_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    populations = [
        ("coverage_control_93_all", rows),
        ("dev15_w2_3a_subset", [row for row in rows if row["subset"] == "dev"]),
        ("eval78_non_dev", [row for row in rows if row["subset"] == "eval"]),
    ]
    output = []
    for pop_name, pop_all_variants in populations:
        for variant in [item["variant"] for item in VARIANTS]:
            pop = [row for row in pop_all_variants if row["variant"] == variant]
            total = len(pop)
            base_dim_success = sum(row["dim_baseline_status"] == "success" for row in pop)
            variant_dim_success = sum(row["variant_status"] == "success" for row in pop)
            base_both = sum(row["baseline_pair_category"] == "both_success" for row in pop)
            variant_both = sum(row["variant_pair_category"] == "both_success" for row in pop)
            base_roof = sum(row["dim_baseline_bucket_v1"] == "roof_matching_assembly_failure" for row in pop)
            variant_roof = sum(row["variant_bucket_v1"] == "roof_matching_assembly_failure" for row in pop)
            recovered_roof = sum(
                row["dim_baseline_bucket_v1"] == "roof_matching_assembly_failure"
                and row["variant_status"] == "success"
                for row in pop
            )
            output.append(
                {
                    "population": pop_name,
                    "variant": variant,
                    "n": str(total),
                    "baseline_dim_success": count_rate(base_dim_success, total),
                    "variant_dim_success": count_rate(variant_dim_success, total),
                    "delta_dim_success_count": str(variant_dim_success - base_dim_success),
                    "delta_dim_success_pp": delta_pp(variant_dim_success, base_dim_success, total),
                    "baseline_both_success": count_rate(base_both, total),
                    "variant_both_success": count_rate(variant_both, total),
                    "delta_both_success_count": str(variant_both - base_both),
                    "delta_both_success_pp": delta_pp(variant_both, base_both, total),
                    "baseline_roof_matching_failures": str(base_roof),
                    "variant_roof_matching_failures": str(variant_roof),
                    "roof_matching_recovered_to_success": str(recovered_roof),
                }
            )
    return output


def build_bucket_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    buckets = ["success", "coverage", "roof_matching_assembly_failure", "validity", "reference_mismatch", "aoi_edge_excluded"]
    output = []
    for variant in [item["variant"] for item in VARIANTS]:
        pop = [row for row in rows if row["variant"] == variant]
        for bucket in buckets:
            output.append(
                {
                    "population": "coverage_control_93_all",
                    "variant": variant,
                    "bucket_v1": bucket,
                    "baseline_count": str(sum(row["dim_baseline_bucket_v1"] == bucket for row in pop)),
                    "variant_count": str(sum(row["variant_bucket_v1"] == bucket for row in pop)),
                }
            )
    return output


def build_roof_matching_recovery_rows(
    baseline_rows: list[dict[str, str]],
    status_by_key: dict[tuple[str, str], dict[str, str]],
    subset_by_id: dict[str, str],
) -> list[dict[str, str]]:
    target_rows = [
        row
        for row in baseline_rows
        if failure_bucket("DIM", row["dim_status"], row["dim_reason"]) == "roof_matching_assembly_failure"
    ]
    output = []
    for base in target_rows:
        bid = base["building_id"]
        for variant in VARIANTS:
            variant_id = variant["variant"]
            status = status_by_key[(variant_id, bid)]
            variant_bucket = failure_bucket("DIM", status["status"], status["reason"])
            output.append(
                {
                    "building_id": bid,
                    "subset": subset_by_id.get(bid, ""),
                    "variant": variant_id,
                    "baseline_dim_status": base["dim_status"],
                    "baseline_dim_reason": base["dim_reason"],
                    "variant_status": status["status"],
                    "variant_reason": status["reason"],
                    "variant_bucket_v1": variant_bucket,
                    "recovered_to_success": "yes" if status["status"] == "success" else "no",
                    "variant_has_lod22": status["has_lod22"],
                    "variant_val3dity_valid": status["val3dity_valid"],
                    "variant_rf_pt_density": status["rf_pt_density"],
                    "variant_rf_nodata_frac": status["rf_nodata_frac"],
                    "variant_rf_rmse_lod22": status["rf_rmse_lod22"],
                }
            )
    return output


def build_density_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    output = []
    for variant in [item["variant"] for item in VARIANTS]:
        pop = [row for row in rows if row["variant"] == variant]
        densities = [parse_float(row["variant_rf_pt_density"]) for row in pop if parse_float(row["variant_rf_pt_density"]) is not None]
        output.append(
            {
                "variant": variant,
                "n_with_density": str(len(densities)),
                "mean_rf_pt_density": f"{sum(densities) / len(densities):.3f}" if densities else "",
                "median_rf_pt_density": f"{median(densities):.3f}" if densities else "",
                "min_rf_pt_density": f"{min(densities):.3f}" if densities else "",
                "max_rf_pt_density": f"{max(densities):.3f}" if densities else "",
                "target_density_note": "~21 pts/m2 for thinned; wall_removed has no density target",
            }
        )
    return output


def write_report(
    path: Path,
    run_id: str,
    variant_stats: list[dict[str, str]],
    success_rows: list[dict[str, str]],
    bucket_rows: list[dict[str, str]],
    recovery_rows: list[dict[str, str]],
    density_rows: list[dict[str, str]],
) -> None:
    compact_success = [row for row in success_rows if row["population"] == "coverage_control_93_all"]
    compact_buckets = [
        row for row in bucket_rows if row["baseline_count"] != "0" or row["variant_count"] != "0"
    ]
    recovered_count = Counter(
        row["variant"] for row in recovery_rows if row["recovered_to_success"] == "yes"
    )
    lines = [
        "# W2-3b DIM Variant Tests",
        "",
        f"- Run ID: `{run_id}`",
        f"- Baseline: W2-1c coverage-control 93 buildings from `{BASELINE_SOURCE}`.",
        f"- Roofer parameters: defaults; plumbing kept fixed (`--id-attribute`, AOI `--box`, `--filter`, `--jobs {ROOFER_JOBS}`).",
        f"- H-wall variant: remove points with estimated vertical-plane normals (`abs(NormalZ) < {WALL_NZ_THRESHOLD}`).",
        f"- H-density variant: PDAL `filters.sample(radius={THIN_RADIUS_M})` to reduce DIM density toward ALS-scale sampling.",
        "- Baseline roof-matching/assembly failures tracked below are the 7 W2-1c DIM `roof_matching_assembly_failure` buildings.",
        "",
        "## Variant Point Clouds",
        "",
    ]
    lines.extend(markdown_table(variant_stats))
    lines.extend(["", "## Roofer Success vs Baseline DIM", ""])
    lines.extend(markdown_table(compact_success))
    lines.extend(["", "## Roofer Density Summary", ""])
    lines.extend(markdown_table(density_rows))
    success_by_variant = {row["variant"]: row for row in compact_success}
    density_by_variant = {row["variant"]: row for row in density_rows}
    lines.extend(
        [
            "",
            "## Observations",
            "",
            (
                "- H-wall: wall_removed changed DIM success "
                f"{success_by_variant['wall_removed']['baseline_dim_success']} -> "
                f"{success_by_variant['wall_removed']['variant_dim_success']} "
                f"(delta {success_by_variant['wall_removed']['delta_dim_success_count']}, "
                f"{success_by_variant['wall_removed']['delta_dim_success_pp']} pp) and recovered "
                f"{recovered_count.get('wall_removed', 0)} of 7 baseline roof-matching failures."
            ),
            (
                "- H-density: thinned reached mean Roofer footprint density "
                f"{density_by_variant['thinned']['mean_rf_pt_density']} pts/m2 "
                f"(target about 21 pts/m2), changed DIM success "
                f"{success_by_variant['thinned']['baseline_dim_success']} -> "
                f"{success_by_variant['thinned']['variant_dim_success']} "
                f"(delta {success_by_variant['thinned']['delta_dim_success_count']}, "
                f"{success_by_variant['thinned']['delta_dim_success_pp']} pp), and recovered "
                f"{recovered_count.get('thinned', 0)} of 7 baseline roof-matching failures."
            ),
        ]
    )
    lines.extend(["", "## Failure Buckets", ""])
    lines.extend(markdown_table(compact_buckets))
    lines.extend(["", "## Roof-Matching Failure Recovery", ""])
    lines.append(f"- wall_removed recovered {recovered_count.get('wall_removed', 0)} of 7 baseline roof-matching failures.")
    lines.append(f"- thinned recovered {recovered_count.get('thinned', 0)} of 7 baseline roof-matching failures.")
    lines.extend(["", *markdown_table(recovery_rows)])
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- Per-building variant status: `docs/W2_3b_variant_status.csv`",
            "- Success summary: `docs/W2_3b_variant_success.csv`",
            "- Bucket summary: `docs/W2_3b_bucket_summary.csv`",
            "- 7-building recovery table: `docs/W2_3b_roof_matching_recovery.csv`",
            "- Point-cloud variant stats: `docs/W2_3b_variant_pointcloud_stats.csv`",
            "- Density summary: `docs/W2_3b_variant_density_summary.csv`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def coverage_rows(path: Path) -> list[dict[str, str]]:
    rows = [row for row in read_csv(path) if row["coverage_control_population"] == "yes"]
    if len(rows) != 93:
        raise RuntimeError(f"Expected 93 coverage-control rows in {path}, got {len(rows)}")
    return rows


def read_subset_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {row["building_id"]: row["subset"] for row in read_csv(path)}


def failure_bucket(input_label: str, status: str, reason: str) -> str:
    if status == "success":
        return "success"
    if reason in {"pointcloud_unusable_no_points", "pointcloud_unusable_no_planes", "pointcloud_unusable"}:
        return "coverage"
    if reason == "missing_roofer_output":
        return "aoi_edge_excluded"
    if reason == "val3dity_invalid":
        return "validity"
    if input_label == "DIM" and reason == "missing_lod22_geometry":
        return "roof_matching_assembly_failure"
    return "roof_matching_assembly_failure"


def pair_category(als_status: str, dim_status: str) -> str:
    if als_status == "success" and dim_status == "success":
        return "both_success"
    if als_status == "success":
        return "ALS_only"
    if dim_status == "success":
        return "DIM_only"
    return "both_fail"


def load_w2_module(root: Path) -> Any:
    path = root / "scripts/08_roofer_w2.py"
    spec = importlib.util.spec_from_file_location("roofer_w2", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ogr_filter(building_ids: list[str]) -> str:
    quoted = ",".join("'" + bid.replace("'", "''") + "'" for bid in building_ids)
    return f"building_id IN ({quoted})"


def write_host_config(run_dir: Path, run_id: str, git_commit: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "task": "W2-3b_dim_variant_tests",
        "run_id": run_id,
        "git_commit": git_commit,
        "base_w2_run_id": BASE_W2_RUN_ID,
        "baseline_source": BASELINE_SOURCE,
        "coverage_population_n": 93,
        "aoi_bbox": list(AOI_BBOX),
        "base_dim": BASE_DIM,
        "footprints": FOOTPRINTS,
        "roofer_jobs": ROOFER_JOBS,
        "variants": VARIANTS,
    }
    (run_dir / "config.yaml").write_text(to_yaml(config), encoding="utf-8")


def write_host_versions(
    repo: Path,
    run_dir: Path,
    compose: list[str],
    env: dict[str, str],
    git_commit: str,
) -> None:
    lines = [
        "# W2-3b Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {run_dir.name}",
        f"- Repository commit: {git_commit}",
        "",
        "```console",
    ]
    commands = [
        ["git", "status", "--short", "--branch"],
        [*compose, "run", "-T", "--rm", "roofer", "-v"],
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
            "import laspy, numpy; print('laspy ' + laspy.__version__); print('numpy ' + numpy.__version__)",
        ],
    ]
    for cmd in commands:
        lines.append("$ " + " ".join(cmd))
        lines.append(capture(cmd, cwd=repo if cmd[0] != "git" else repo.parent, env=env))
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    log_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError(f"No rows for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def copy_outputs(run_dir: Path, paths: list[Path]) -> None:
    snapshot = run_dir / "docs_snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in paths:
        shutil.copy2(path, snapshot / path.name)


def markdown_table(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return ["_No rows._"]
    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
    return lines


def parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def pct(count: int, total: int) -> str:
    if total <= 0:
        return "nan"
    return f"{count / total * 100:.1f}%"


def count_rate(count: int, total: int) -> str:
    return f"{count}/{total} ({pct(count, total)})"


def delta_pp(new_count: int, old_count: int, total: int) -> str:
    if total <= 0:
        return "nan"
    return f"{((new_count - old_count) / total * 100):+.1f}"


def rel(path: Path) -> str:
    return path.as_posix().replace("/workspace/", "").replace("phases/p0-audit/", "")


def to_yaml(value: Any, indent: int = 0) -> str:
    space = " " * indent
    if isinstance(value, dict):
        lines = []
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
    if not text or any(ch in text for ch in [":", "#", "{", "}", "[", "]", ",", "\n"]):
        return json.dumps(text, ensure_ascii=False)
    return text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("host", "prepare", "postprocess"), default="host")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "host":
        host_entrypoint()
    elif args.mode == "prepare":
        prepare_entrypoint()
    elif args.mode == "postprocess":
        postprocess_entrypoint()
    else:
        raise AssertionError(args.mode)


if __name__ == "__main__":
    main()

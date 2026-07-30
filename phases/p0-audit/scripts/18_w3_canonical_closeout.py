#!/usr/bin/env python3
"""W3-2c P0 closeout with canonical explicit-default Roofer harness.

Run from phases/p0-audit/. Host mode executes compute mode inside the tools container.
Canonical Roofer output is W3-2b run_2, which uses explicit default parameters
and the W2-1c 93-building coverage-control filter.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
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

from p0_paths import P0_EVIDENCE


TASK_ID = "W3-2c"
CANONICAL_RUN_ID = "w3_2b_roofer_repeatability_20260612_220747"
CANONICAL_STAGE = "run_2"
CANONICAL_SEED_NOTE = "Roofer exposes no random seed in the CLI; W2-3a dev subset seed is 20260612."
OLD_W3_RUN_ID = "w3_1_roofer_quality_20260612_210850"
REFERENCE_MISMATCH_IDS = {"DEBY_LOD2_104586480", "DEBY_LOD2_4906973"}
GALLERY_CASE_ID = "DEBY_LOD2_4907182"
RECOVERED_CASE_ID = "DEBY_LOD2_4907510"
QUALITY_TOLERANCE = 0.02
PLANE_F1_DROP_THRESHOLD = 0.10
BOUNDARY_RATIO_THRESHOLD = 1.50
VALIDITY_DROP_THRESHOLD_PP = 10.0


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("w3_2c_canonical_closeout_%Y%m%d_%H%M%S")
    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()
    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]

    write_host_config(run_dir, run_id, git_commit)
    if env.get("SKIP_BUILD") != "1":
        run(compose + ["build", "tools"], cwd=repo, env=env, log_path=logs_dir / "build_tools.log")
    write_host_versions(repo, run_dir, compose, env, git_commit)
    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            "-e",
            f"RUN_ID={run_id}",
            "-e",
            f"P0_GIT_COMMIT={git_commit}",
            "tools",
            "python",
            "/workspace/scripts/18_w3_canonical_closeout.py",
            "--mode",
            "compute",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "compute.log",
    )
    print(f"run_id={run_id}")
    print(f"run_dir=runs/{run_id}")
    print("report=docs/W3_2c_canonical_closeout.md")


def compute_entrypoint() -> None:
    root = Path("/workspace")
    docs = P0_EVIDENCE
    figs = docs.figs("W3")
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    figs.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)

    w3 = load_module("w3_roofer_quality", root / "scripts/15_roofer_quality_w3.py")
    w3b = load_module("w3_roofer_quality_b", root / "scripts/16_roofer_quality_w3b.py")
    w2pair = load_module("w2_pair_analysis", root / "scripts/09_w2_pair_analysis.py")

    canonical_rows = build_canonical_paired_rows(root)
    canonical_both_success_ids = [
        row["building_id"]
        for row in canonical_rows
        if row["coverage_control_population"] == "yes" and row["paired_category"] == "both_success"
    ]
    if len(canonical_both_success_ids) != 71:
        raise RuntimeError(f"Expected 71 canonical both_success buildings, got {len(canonical_both_success_ids)}")

    success_rows = build_success_rows(canonical_rows)
    input_bucket_rows = build_input_bucket_rows(canonical_rows)
    priority_bucket_rows = build_priority_bucket_rows(canonical_rows)
    quality_rows, quality_summary, internal_rows, internal_summary = compute_canonical_quality(
        w3,
        w3b,
        canonical_both_success_ids,
    )
    threshold_rows = build_threshold_rows(quality_summary, success_rows)
    quality_compare_rows, quality_stability_note = build_quality_comparison(quality_summary, internal_summary)
    gallery_path = render_gallery_png(w2pair, root, figs)

    outputs = {
        "paired": docs / "W3_2c_canonical_paired_status.csv",
        "success": docs / "W3_2c_canonical_success_rates.csv",
        "input_buckets": docs / "W3_2c_canonical_input_bucket_summary.csv",
        "priority_buckets": docs / "W3_2c_canonical_priority_buckets.csv",
        "quality_metrics": docs / "W3_2c_canonical_roofer_quality_metrics.csv",
        "quality_summary": docs / "W3_2c_canonical_roofer_quality_summary.csv",
        "internal_metrics": docs / "W3_2c_canonical_internal_boundary_metrics.csv",
        "internal_summary": docs / "W3_2c_canonical_internal_boundary_summary.csv",
        "thresholds": docs / "W3_2c_canonical_threshold_position.csv",
        "quality_compare": docs / "W3_2c_quality_median_change.csv",
    }
    write_csv(outputs["paired"], canonical_rows)
    write_csv(outputs["success"], success_rows)
    write_csv(outputs["input_buckets"], input_bucket_rows)
    write_csv(outputs["priority_buckets"], priority_bucket_rows)
    write_csv(outputs["quality_metrics"], quality_rows)
    write_csv(outputs["quality_summary"], quality_summary)
    write_csv(outputs["internal_metrics"], internal_rows)
    write_csv(outputs["internal_summary"], internal_summary)
    write_csv(outputs["thresholds"], threshold_rows)
    write_csv(outputs["quality_compare"], quality_compare_rows)

    closeout = docs / "W3_2c_canonical_closeout.md"
    write_closeout_report(
        closeout,
        run_id,
        success_rows,
        priority_bucket_rows,
        quality_summary,
        internal_summary,
        threshold_rows,
        quality_compare_rows,
        quality_stability_note,
        gallery_path,
    )
    write_w3_summary(
        docs / "W3_summary.md",
        success_rows,
        priority_bucket_rows,
        quality_summary,
        internal_summary,
        threshold_rows,
        quality_stability_note,
        gallery_path,
    )
    snapshot_paths = list(outputs.values()) + [closeout, docs / "W3_summary.md", gallery_path]
    copy_outputs(run_dir, snapshot_paths)
    write_run_summary(
        run_dir / "w3_2c_summary.json",
        success_rows,
        priority_bucket_rows,
        quality_summary,
        internal_summary,
        threshold_rows,
        quality_stability_note,
        gallery_path,
    )

    print(f"canonical_both_success={len(canonical_both_success_ids)}")
    print(f"success_table={rel(outputs['success'])}")
    print(f"quality_summary={rel(outputs['quality_summary'])}")
    print(f"quality_compare={rel(outputs['quality_compare'])}")
    print(f"gallery_png={rel(gallery_path)}")
    print(f"report={rel(closeout)}")


def build_canonical_paired_rows(root: Path) -> list[dict[str, str]]:
    docs = P0_EVIDENCE
    base_rows = read_csv(docs / "W2_1c_paired_status.csv")
    als_run2 = read_status(root / "runs" / CANONICAL_RUN_ID / "status" / CANONICAL_STAGE / "als_default.csv")
    dim_run2 = read_status(root / "runs" / CANONICAL_RUN_ID / "status" / CANONICAL_STAGE / "dim_default.csv")
    rows = []
    for row in base_rows:
        out = dict(row)
        coverage_control = out["coverage_control_population"] == "yes"
        if coverage_control:
            replace_status(out, "als", als_run2[out["building_id"]])
            replace_status(out, "dim", dim_run2[out["building_id"]])
            out["paired_category"] = pair_category(out["als_status"], out["dim_status"])
            out["als_failure_bucket_v1"] = failure_bucket("ALS", out["als_status"], out["als_reason"], coverage_control)
            out["dim_failure_bucket_v1"] = failure_bucket("DIM", out["dim_status"], out["dim_reason"], coverage_control)
        rows.append(out)
    return rows


def read_status(path: Path) -> dict[str, dict[str, str]]:
    return {row["building_id"]: row for row in read_csv(path)}


def replace_status(out: dict[str, str], prefix: str, status: dict[str, str]) -> None:
    for key in [
        "status",
        "reason",
        "rf_pt_density",
        "rf_nodata_frac",
        "has_lod22",
        "val3dity_valid",
    ]:
        out[f"{prefix}_{key}"] = status[key]


def build_success_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    scopes = [
        ("full_199", rows),
        ("both_attempted_179", [row for row in rows if row["both_attempted"] == "yes"]),
        ("coverage_controlled_93", [row for row in rows if row["coverage_control_population"] == "yes"]),
    ]
    output = []
    for name, subset in scopes:
        total = len(subset)
        als_success = sum(row["als_status"] == "success" for row in subset)
        dim_success = sum(row["dim_status"] == "success" for row in subset)
        both_success = sum(row["paired_category"] == "both_success" for row in subset)
        als_only = sum(row["paired_category"] == "ALS_only" for row in subset)
        dim_only = sum(row["paired_category"] == "DIM_only" for row in subset)
        both_fail = sum(row["paired_category"] == "both_fail" for row in subset)
        output.append(
            {
                "population": name,
                "n": str(total),
                "als_success": count_rate(als_success, total),
                "dim_success": count_rate(dim_success, total),
                "both_success": count_rate(both_success, total),
                "als_only": count_rate(als_only, total),
                "dim_only": count_rate(dim_only, total),
                "both_fail": count_rate(both_fail, total),
                "als_val3dity_valid": count_rate(sum(row["als_val3dity_valid"] == "True" for row in subset), total),
                "dim_val3dity_valid": count_rate(sum(row["dim_val3dity_valid"] == "True" for row in subset), total),
            }
        )
    return output


def build_input_bucket_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    scopes = [
        ("full_199", lambda row: True),
        ("both_attempted_179", lambda row: row["both_attempted"] == "yes"),
        ("coverage_controlled_93", lambda row: row["coverage_control_population"] == "yes"),
    ]
    buckets = ["success", "coverage", "roof_matching_assembly_failure", "validity", "reference_mismatch", "aoi_edge_excluded"]
    output = []
    for input_label, prefix in (("ALS", "als"), ("DIM", "dim")):
        for bucket in buckets:
            out = {"input": input_label, "bucket_v1": bucket}
            for scope_name, pred in scopes:
                out[f"{scope_name}_count"] = str(
                    sum(pred(row) and row[f"{prefix}_failure_bucket_v1"] == bucket for row in rows)
                )
            output.append(out)
    return output


def build_priority_bucket_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    counts = Counter(priority_bucket(row) for row in rows)
    notes = {
        "coverage": "both attempted, outside W2-1c DIM coverage rule after reference-mismatch exclusions",
        "aoi_edge": "footprint centroid outside Roofer AOI box",
        "reference_mismatch": "104586480 from W2-1c and 4906973 from W3-1b height-bias review",
        "roof_matching": "canonical DIM missing_lod22_geometry with coverage present",
        "validity": "coverage-control buildings with ALS or DIM validity bucket after roof-matching priority",
        "remainder_after_priority": "not assigned to non-success/exclusion buckets above; canonical quality table uses 71 paired both_success buildings",
    }
    order = ["coverage", "aoi_edge", "reference_mismatch", "roof_matching", "validity", "remainder_after_priority"]
    return [{"bucket": bucket, "count": str(counts[bucket]), "scope_note": notes[bucket]} for bucket in order]


def priority_bucket(row: dict[str, str]) -> str:
    if row["both_attempted"] != "yes":
        return "aoi_edge"
    if row["reference_mismatch_exclude"] == "yes" or row["building_id"] in REFERENCE_MISMATCH_IDS:
        return "reference_mismatch"
    if row["coverage_control_population"] != "yes":
        return "coverage"
    if "roof_matching_assembly_failure" in (row["als_failure_bucket_v1"], row["dim_failure_bucket_v1"]):
        return "roof_matching"
    if "validity" in (row["als_failure_bucket_v1"], row["dim_failure_bucket_v1"]):
        return "validity"
    return "remainder_after_priority"


def compute_canonical_quality(
    w3: Any,
    w3b: Any,
    building_ids: list[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    reference = w3.parse_lod2_roofs(Path(w3.LOD2_DIR), set(building_ids))
    als_cityjson = Path(f"/workspace/runs/{CANONICAL_RUN_ID}/cityjson/{CANONICAL_STAGE}/als_default.city.json")
    dim_cityjson = Path(f"/workspace/runs/{CANONICAL_RUN_ID}/cityjson/{CANONICAL_STAGE}/dim_default.city.json")
    als_pred = w3.parse_cityjson_roofs(als_cityjson, set(building_ids))
    dim_pred = w3.parse_cityjson_roofs(dim_cityjson, set(building_ids))

    rows = []
    for building_id in building_ids:
        ref_surfaces = reference[building_id]
        als_metrics = w3.compare_building(ref_surfaces, als_pred[building_id])
        dim_metrics = w3.compare_building(ref_surfaces, dim_pred[building_id])
        rows.append(w3.building_metric_row(building_id, ref_surfaces, als_metrics, dim_metrics))
    summary = w3.build_summary(rows)
    internal_rows = w3b.build_internal_boundary_rows(w3, building_ids, reference, als_pred, dim_pred)
    internal_summary = w3b.build_internal_summary(internal_rows)
    return rows, summary, internal_rows, internal_summary


def build_threshold_rows(quality_summary: list[dict[str, str]], success_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_metric = {row["metric"]: row for row in quality_summary}
    cc = next(row for row in success_rows if row["population"] == "coverage_controlled_93")
    plane_drop = fnum(by_metric["plane_f1"]["als_median"]) - fnum(by_metric["plane_f1"]["dim_median"])
    chamfer_ratio = fnum(by_metric["boundary_chamfer_m"]["dim_over_als"])
    hausdorff_ratio = fnum(by_metric["boundary_hausdorff_m"]["dim_over_als"])
    als_valid = count_value(cc["als_val3dity_valid"])
    dim_valid = count_value(cc["dim_val3dity_valid"])
    total = int(cc["n"])
    validity_drop = (als_valid - dim_valid) / total * 100.0
    return [
        threshold_row("plane_f1_drop", plane_drop, PLANE_F1_DROP_THRESHOLD, "ALS median plane F1 minus DIM median plane F1"),
        threshold_row(
            "exterior_boundary_chamfer_ratio",
            chamfer_ratio,
            BOUNDARY_RATIO_THRESHOLD,
            "DIM median exterior Chamfer divided by ALS median exterior Chamfer",
        ),
        threshold_row(
            "exterior_boundary_hausdorff_ratio",
            hausdorff_ratio,
            BOUNDARY_RATIO_THRESHOLD,
            "DIM median exterior Hausdorff divided by ALS median exterior Hausdorff",
        ),
        threshold_row(
            "validity_rate_drop_pp",
            validity_drop,
            VALIDITY_DROP_THRESHOLD_PP,
            "coverage-control val3dity-valid rate: ALS 88/93 (94.6%) minus DIM 83/93 (89.2%)",
        ),
    ]


def threshold_row(item: str, observed: float, threshold: float, definition: str) -> dict[str, str]:
    return {
        "item": item,
        "observed_value": fmt(observed),
        "threshold_value": fmt(threshold),
        "observed_minus_threshold": fmt(observed - threshold),
        "definition": definition,
    }


def build_quality_comparison(
    canonical_summary: list[dict[str, str]],
    canonical_internal_summary: list[dict[str, str]],
) -> tuple[list[dict[str, str]], str]:
    old_external = {row["metric"]: row for row in read_csv(P0_EVIDENCE / "W3_1_roofer_quality_summary.csv")}
    old_internal = {row["metric"]: row for row in read_csv(P0_EVIDENCE / "W3_1b_internal_boundary_summary.csv")}
    canonical = {row["metric"]: row for row in canonical_summary}
    canonical.update({row["metric"]: row for row in canonical_internal_summary})
    rows = []
    max_abs_delta = 0.0
    outside = []
    for metric, old_row in {**old_external, **old_internal}.items():
        can_row = canonical[metric]
        old_n = old_row.get("n", old_row.get("n_paired_finite", ""))
        can_n = can_row.get("n", can_row.get("n_paired_finite", ""))
        for input_label, key in (("ALS", "als_median"), ("DIM", "dim_median")):
            old_value = fnum(old_row[key])
            can_value = fnum(can_row[key])
            delta = can_value - old_value
            max_abs_delta = max(max_abs_delta, abs(delta))
            within = abs(delta) <= QUALITY_TOLERANCE
            if not within:
                outside.append(f"{metric}:{input_label}")
            rows.append(
                {
                    "metric": metric,
                    "input": input_label,
                    "old_n": old_n,
                    "canonical_n": can_n,
                    "old_median": fmt(old_value),
                    "canonical_median": fmt(can_value),
                    "canonical_minus_old": fmt(delta),
                    "within_pm_0p02": "yes" if within else "no",
                }
            )
    if outside:
        note = (
            f"Canonical 71-building medians are not uniformly within +/-0.02 of W3-1/W3-1b; "
            f"max abs change is {max_abs_delta:.3f}, outside entries: {', '.join(outside)}. "
            "Exterior-boundary and height medians retain the previous numeric interpretation, while plane-F1/internal-boundary numeric text is replaced by canonical values."
        )
    else:
        note = (
            f"Canonical 71-building medians are within +/-0.02 of W3-1/W3-1b; "
            f"max abs change is {max_abs_delta:.3f}. Existing numeric interpretation is retained."
        )
    return rows, note


def render_gallery_png(w2pair: Any, root: Path, figs: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    footprints = w2pair.load_footprints(root / "data/work/footprints/lod2_ground_plan.geojson")
    status = read_status(root / "runs" / CANONICAL_RUN_ID / "status" / CANONICAL_STAGE / "dim_default.csv")
    row = status[GALLERY_CASE_ID]
    point_sets = w2pair.read_dim_points_for_cases(
        root / "data/work/w2/dim_v1_classified_z_minus0p174.laz",
        {GALLERY_CASE_ID: footprints[GALLERY_CASE_ID]},
        buffer_m=5.0,
    )
    city = w2pair.load_cityjson(root / "runs" / CANONICAL_RUN_ID / "cityjson" / CANONICAL_STAGE / "dim_default.city.json")
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    w2pair.plot_topdown(axes[0], GALLERY_CASE_ID, footprints[GALLERY_CASE_ID], point_sets[GALLERY_CASE_ID], city)
    w2pair.plot_profile(axes[1], footprints[GALLERY_CASE_ID], point_sets[GALLERY_CASE_ID], city, GALLERY_CASE_ID)
    fig.suptitle(
        (
            f"{GALLERY_CASE_ID} | canonical DIM unrecovered missing_lod22_geometry | "
            f"density={row['rf_pt_density']} pts/m2 | nodata={row['rf_nodata_frac']} | roof_planes={row['rf_roof_planes']}"
        ),
        fontsize=11,
    )
    out = figs / f"w3_2c_dim_unrecovered_missing_lod22_{GALLERY_CASE_ID}.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def write_closeout_report(
    path: Path,
    run_id: str,
    success_rows: list[dict[str, str]],
    priority_bucket_rows: list[dict[str, str]],
    quality_summary: list[dict[str, str]],
    internal_summary: list[dict[str, str]],
    threshold_rows: list[dict[str, str]],
    quality_compare_rows: list[dict[str, str]],
    quality_stability_note: str,
    gallery_path: Path,
) -> None:
    lines = [
        "# W3-2c Canonical P0 Closeout",
        "",
        f"- Run ID: `{run_id}`",
        f"- Canonical Roofer run: `{CANONICAL_RUN_ID}` `{CANONICAL_STAGE}`.",
        "- Canonical harness: explicit Roofer defaults (`plane-detect-epsilon=0.30`, `plane-detect-min-points=15`, `complexity-factor=0.888`), `--jobs 32`, fixed AOI `--box`, and fixed 93-building `--filter`.",
        f"- Seed/log note: {CANONICAL_SEED_NOTE} Canonical logs: `runs/{CANONICAL_RUN_ID}/logs/roofer_run_2_als_default.log` and `runs/{CANONICAL_RUN_ID}/logs/roofer_run_2_dim_default.log`.",
        "",
        "## Canonical Success Rates",
        "",
    ]
    lines.extend(markdown_table(success_rows))
    lines.extend(["", "## Canonical Priority Buckets", ""])
    lines.extend(markdown_table(priority_bucket_rows))
    lines.extend(["", "## Canonical Quality Summary", ""])
    lines.extend(markdown_table(quality_summary + normalize_internal_for_table(internal_summary)))
    lines.extend(["", "## Quality Median Change", "", f"- {quality_stability_note}", ""])
    lines.extend(markdown_table(quality_compare_rows))
    lines.extend(["", "## Section 6 Threshold Position", ""])
    lines.extend(markdown_table(threshold_rows))
    lines.extend(
        [
            "",
            "## Figure Update",
            "",
            f"- Figure 1.1a replacement: `{rel(gallery_path)}`.",
            f"- `{RECOVERED_CASE_ID}` remains documented as a preprocessing-recovered case via `docs/W2_3b_roof_matching_recovery.csv`.",
            "",
            "## Files",
            "",
            "- Canonical paired status: `docs/W3_2c_canonical_paired_status.csv`",
            "- Canonical success rates: `docs/W3_2c_canonical_success_rates.csv`",
            "- Canonical threshold table: `docs/W3_2c_canonical_threshold_position.csv`",
            "- Canonical quality metrics: `docs/W3_2c_canonical_roofer_quality_metrics.csv`",
            "- Quality median change: `docs/W3_2c_quality_median_change.csv`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_w3_summary(
    path: Path,
    success_rows: list[dict[str, str]],
    priority_bucket_rows: list[dict[str, str]],
    quality_summary: list[dict[str, str]],
    internal_summary: list[dict[str, str]],
    threshold_rows: list[dict[str, str]],
    quality_stability_note: str,
    gallery_path: Path,
) -> None:
    lines = [
        "# W3 P0 Integrated Summary",
        "",
        "## Scope",
        "",
        "- Canonical P0 closeout harness: W3-2b `run_2` with explicit Roofer defaults, fixed 93-building coverage-control filter, `--jobs 32`, and fixed AOI `--box`.",
        f"- Canonical logs: `runs/{CANONICAL_RUN_ID}/logs/roofer_run_2_als_default.log`, `runs/{CANONICAL_RUN_ID}/logs/roofer_run_2_dim_default.log`, and `runs/{CANONICAL_RUN_ID}/versions.txt`.",
        f"- Seed note: {CANONICAL_SEED_NOTE}",
        "- Main quality population: canonical coverage-control Roofer default paired `both_success` set, 71 buildings.",
        "",
        "## Population Completeness",
        "",
    ]
    lines.extend(markdown_table(success_rows))
    lines.extend(["", "## Final Building-Level Buckets", ""])
    lines.append(
        "One priority bucket is assigned per building for the 199-building accounting: AOI edge first, then reference mismatch, then coverage-control miss, then roof matching/assembly, then validity."
    )
    lines.extend([""])
    lines.extend(markdown_table(priority_bucket_rows))
    lines.extend(["", "Input-level bucket counts are recorded in `docs/W3_2c_canonical_input_bucket_summary.csv`.", ""])
    lines.extend(["## Quality Metrics", "", "Medians are paired by building where the metric is finite.", ""])
    lines.extend(markdown_table(quality_table_rows(quality_summary, internal_summary)))
    lines.extend(["", "## Robustness Checks", ""])
    lines.extend(
        markdown_table(
            [
                {
                    "check": "W2-3a Roofer grid, ALS",
                    "population": "dev15; applied to 93",
                    "result summary": "selected `default` (`epsilon=0.3`, `min_points=15`, `complexity=0.888`)",
                    "delta note": "canonical run_2 ALS success is 87/93 (93.5%); the pre-canonical W2-3a selected-default rerun also recorded 87/93",
                },
                {
                    "check": "W2-3a Roofer grid, DIM",
                    "population": "dev15; applied to 93",
                    "result summary": "selected `default` (`epsilon=0.3`, `min_points=15`, `complexity=0.888`)",
                    "delta note": "canonical run_2 DIM success is 75/93 (80.6%) and paired both success is 71/93 (76.3%); pre-canonical selected-default rows were 76/93 and 72/93",
                },
                {
                    "check": "W2-3b wall_removed",
                    "population": "coverage-control 93",
                    "result summary": "remove points with `abs(NormalZ) < 0.3`",
                    "delta note": "vs canonical run_2: DIM success 75/93 -> 73/93 (-2.2 pp); paired both success 71/93 -> 66/93 (-5.4 pp); original 7-case roof-matching trace recovered 1/7",
                },
                {
                    "check": "W2-3b thinned",
                    "population": "coverage-control 93",
                    "result summary": "PDAL sample radius 0.3; mean Roofer footprint density 19.147 pts/m2",
                    "delta note": "vs canonical run_2: DIM success 75/93 -> 72/93 (-3.2 pp); paired both success 71/93 -> 67/93 (-4.3 pp); original 7-case roof-matching trace recovered 1/7",
                },
                {
                    "check": "W3-2b repeatability",
                    "population": "canonical 93",
                    "result summary": "three same-settings explicit-default runs",
                    "delta note": "run noise +/-0.5 pp by half-range; unstable building `DEBY_LOD2_60042`",
                },
                {
                    "check": "City3D scope note",
                    "population": "coverage-control 93",
                    "result summary": "W2-2 default comparison recorded City3D success 1/93 for ALS and 1/93 for DIM",
                    "delta note": "W2-2b retained City3D as a scoped comparison artifact rather than extending the P0 Roofer quality analysis",
                },
            ]
        )
    )
    lines.extend(["", f"Quality stability note: {quality_stability_note}", ""])
    lines.extend(["### Roof-Matching Recovery Trace", ""])
    lines.extend(
        markdown_table(
            [
                {"building_id": "DEBY_LOD2_42364609", "subset": "dev", "wall_removed": "no recovery", "thinned": "no recovery"},
                {"building_id": "DEBY_LOD2_42364659", "subset": "eval", "wall_removed": "no recovery", "thinned": "no recovery"},
                {"building_id": "DEBY_LOD2_4907182", "subset": "dev", "wall_removed": "no recovery", "thinned": "no recovery"},
                {"building_id": RECOVERED_CASE_ID, "subset": "eval", "wall_removed": "recovered", "thinned": "recovered"},
                {"building_id": "DEBY_LOD2_4908050", "subset": "eval", "wall_removed": "no recovery", "thinned": "no recovery"},
                {"building_id": "DEBY_LOD2_4908166", "subset": "eval", "wall_removed": "no recovery", "thinned": "no recovery"},
                {"building_id": "DEBY_LOD2_4908176", "subset": "eval", "wall_removed": "no recovery", "thinned": "no recovery"},
            ]
        )
    )
    lines.extend(
        [
            "",
            f"Body case note: `{RECOVERED_CASE_ID}` is now used as the preprocessing-recovered type, not Figure 1.1a.",
            "",
            "## Section 6 Threshold Position",
            "",
        ]
    )
    lines.extend(markdown_table(threshold_rows))
    lines.extend(
        [
            "",
            "## Interpretation Notes",
            "",
            "- Plane F1 reflects reference granularity as well as reconstruction behavior: LoD2 reference roof surfaces can split one visually continuous roof into more instances than Roofer predicts, so F1 is sensitive to plane-instance granularity.",
            "- Exterior boundary error is damped by the footprint prior: Roofer preserves the planimetric building outline closely, so exterior Chamfer/Hausdorff are less input-sensitive than roof-plane F1 or internal shared boundaries.",
            "- `validity != correctness`: `DEBY_LOD2_104586480` shows a ghost-slab case where ALS produced a flat geometry over an effectively empty footprint interior while the model was still val3dity-valid.",
            "",
            "## Limitations",
            "",
            "- Single-scene evidence: all numbers come from the same AOI and footprint set.",
            "- City3D scope: City3D results are retained as W2 comparison context, while W3 quality tables focus on Roofer.",
            "- Roofer grid size: W2-3a used a small, predeclared grid over three parameters.",
            "- Input date gap: ALS is 2022-era data, while UAV image filenames indicate 2024-12-17; the modality timestamp gap is about 2.8 years.",
            "- Dev15 split: the W2-3a dev subset is reported separately and remains marked in downstream robustness tables.",
            "- Harness alignment: W3-2c canonicalizes the explicit-default 93-building harness at W3-2b `run_2`; earlier W2-1c/W3-1 tables remain provenance records for the pre-canonical baseline.",
            "",
            "## Figure List",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            [
                {
                    "figure": "Figure 1.1a",
                    "content": f"`{GALLERY_CASE_ID}` canonical DIM roof-matching/assembly case that did not recover under wall removal or thinning",
                    "file": rel(gallery_path),
                },
                {
                    "figure": "Figure 1.1b",
                    "content": "`DEBY_LOD2_4907518` matched roof planes and ridge/shared-boundary comparison spot check",
                    "file": "docs/figs/w3_1b_matching_overlay_mid_DEBY_LOD2_4907518.png",
                },
                {"figure": "Figure 1.2", "content": "canonical W3-2c plane F1 table source", "file": "docs/W3_2c_canonical_roofer_quality_summary.csv"},
                {"figure": "Figure 1.3", "content": "canonical W3-2c exterior/internal boundary table source", "file": "docs/W3_2c_canonical_internal_boundary_summary.csv"},
                {"figure": "Figure 1.4", "content": "canonical W3-2c height-error table source", "file": "docs/W3_2c_canonical_roofer_quality_summary.csv"},
            ]
        )
    )
    lines.extend(
        [
            "",
            "## Source Tables",
            "",
            "- `docs/W3_2c_canonical_success_rates.csv`",
            "- `docs/W3_2c_canonical_priority_buckets.csv`",
            "- `docs/W3_2c_canonical_input_bucket_summary.csv`",
            "- `docs/W3_2c_canonical_roofer_quality_summary.csv`",
            "- `docs/W3_2c_canonical_internal_boundary_summary.csv`",
            "- `docs/W3_2c_canonical_threshold_position.csv`",
            "- `docs/W3_2c_quality_median_change.csv`",
            "- `docs/W3_2b_roofer_repeatability_success.csv`",
            "- `docs/W2_3b_roof_matching_recovery.csv`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def quality_table_rows(external: list[dict[str, str]], internal: list[dict[str, str]]) -> list[dict[str, str]]:
    by_metric = {row["metric"]: row for row in external}
    by_internal = {row["metric"]: row for row in internal}
    rows = []
    specs = [
        ("plane F1", by_metric["plane_f1"], "n", "projected roof-surface IoU >= 0.50 matching"),
        ("exterior boundary Chamfer (m)", by_metric["boundary_chamfer_m"], "n", "roof-union outline, footprint-sensitive"),
        ("exterior boundary Hausdorff (m)", by_metric["boundary_hausdorff_m"], "n", "roof-union outline, footprint-sensitive"),
        ("internal boundary Chamfer (m)", by_internal["internal_boundary_chamfer_m"], "n_paired_finite", "matched roof-surface shared boundaries"),
        ("internal boundary Hausdorff (m)", by_internal["internal_boundary_hausdorff_m"], "n_paired_finite", "matched roof-surface shared boundaries"),
        ("height bias (m)", by_metric["height_bias_m"], "n", "signed median `pred_z - ref_z`"),
        ("height NMAD (m)", by_metric["height_nmad_m"], "n", "matched roof-intersection samples"),
    ]
    for metric, row, n_key, note in specs:
        rows.append(
            {
                "metric": metric,
                "n": row[n_key],
                "ALS median": row["als_median"],
                "DIM median": row["dim_median"],
                "DIM minus ALS": row["dim_minus_als"],
                "DIM over ALS": row.get("dim_over_als", ""),
                "note": note,
            }
        )
    return rows


def normalize_internal_for_table(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "metric": row["metric"],
            "n": row["n_paired_finite"],
            "als_median": row["als_median"],
            "dim_median": row["dim_median"],
            "dim_minus_als": row["dim_minus_als"],
            "dim_over_als": row["dim_over_als"],
            "interpretation": row["definition"],
        }
        for row in rows
    ]


def write_run_summary(
    path: Path,
    success_rows: list[dict[str, str]],
    priority_bucket_rows: list[dict[str, str]],
    quality_summary: list[dict[str, str]],
    internal_summary: list[dict[str, str]],
    threshold_rows: list[dict[str, str]],
    quality_stability_note: str,
    gallery_path: Path,
) -> None:
    payload = {
        "task": TASK_ID,
        "run_id": os.environ["RUN_ID"],
        "canonical_run_id": CANONICAL_RUN_ID,
        "canonical_stage": CANONICAL_STAGE,
        "canonical_seed_note": CANONICAL_SEED_NOTE,
        "success": success_rows,
        "priority_buckets": priority_bucket_rows,
        "quality_summary": quality_summary,
        "internal_boundary_summary": internal_summary,
        "threshold_position": threshold_rows,
        "quality_stability_note": quality_stability_note,
        "gallery_png": rel(gallery_path),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_host_config(run_dir: Path, run_id: str, git_commit: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "task": "W3-2c_canonical_p0_closeout",
        "run_id": run_id,
        "git_commit": git_commit,
        "canonical_run_id": CANONICAL_RUN_ID,
        "canonical_stage": CANONICAL_STAGE,
        "canonical_seed_note": CANONICAL_SEED_NOTE,
        "old_w3_run_id": OLD_W3_RUN_ID,
        "quality_population": "canonical coverage_control_population=yes and paired_category=both_success",
        "expected_quality_population_n": 71,
        "gallery_case_id": GALLERY_CASE_ID,
        "recovered_case_id": RECOVERED_CASE_ID,
    }
    (run_dir / "config.yaml").write_text(to_yaml(config), encoding="utf-8")


def write_host_versions(repo: Path, run_dir: Path, compose: list[str], env: dict[str, str], git_commit: str) -> None:
    lines = [
        "# W3-2c Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {run_dir.name}",
        f"- Repository commit: {git_commit}",
        "",
        "```console",
    ]
    commands = [
        ["git", "status", "--short", "--branch"],
        [
            *compose,
            "run",
            "-T",
            "--rm",
            "tools",
            "python",
            "-c",
            "import laspy,numpy,matplotlib,shapely,lxml; print('laspy ' + laspy.__version__); print('numpy ' + numpy.__version__); print('matplotlib ' + matplotlib.__version__); print('shapely ' + shapely.__version__); print('lxml ' + lxml.__version__)",
        ],
    ]
    for cmd in commands:
        lines.append("$ " + " ".join(cmd))
        lines.append(capture(cmd, cwd=repo if cmd[0] != "git" else repo.parent, env=env))
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def failure_bucket(input_label: str, status: str, reason: str, coverage_control: bool) -> str:
    if status == "success":
        return "success"
    if reason in {"pointcloud_unusable_no_points", "pointcloud_unusable_no_planes", "pointcloud_unusable"}:
        return "coverage"
    if reason == "missing_roofer_output":
        return "aoi_edge_excluded"
    if reason == "val3dity_invalid":
        return "validity"
    if input_label == "DIM" and reason == "missing_lod22_geometry":
        return "roof_matching_assembly_failure" if coverage_control else "coverage"
    return "roof_matching_assembly_failure"


def pair_category(als_status: str, dim_status: str) -> str:
    if als_status == "success" and dim_status == "success":
        return "both_success"
    if als_status == "success":
        return "ALS_only"
    if dim_status == "success":
        return "DIM_only"
    return "both_fail"


def pct_value(count_rate_value: str) -> float:
    # Input format: "88/93 (94.6%)".
    pct = count_rate_value.split("(")[1].split("%")[0]
    return float(pct)


def count_value(count_rate_value: str) -> int:
    return int(count_rate_value.split("/")[0])


def count_rate(count: int, total: int) -> str:
    return f"{count}/{total} ({count / total * 100:.1f}%)" if total else "0/0 (nan%)"


def fnum(value: str) -> float:
    return float(value) if value != "" else math.nan


def fmt(value: float) -> str:
    if not math.isfinite(value):
        return ""
    return f"{value:.6f}"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError(f"No rows for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return ["_No rows._"]
    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
    return lines


def copy_outputs(run_dir: Path, paths: list[Path]) -> None:
    snapshot = run_dir / "docs_snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in paths:
        shutil.copy2(path, snapshot / path.name)


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, log_path: Path | None = None) -> None:
    print("+ " + " ".join(cmd), flush=True)
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as log:
            log.write("+ " + " ".join(cmd) + "\n")
            proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log.write(proc.stdout)
            print(proc.stdout, end="", flush=True)
            proc.check_returncode()
            return
    subprocess.run(cmd, cwd=cwd, env=env, text=True, check=True)


def capture(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


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
    parser.add_argument("--mode", choices=("host", "compute"), default="host")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "host":
        host_entrypoint()
    elif args.mode == "compute":
        compute_entrypoint()
    else:
        raise AssertionError(args.mode)


if __name__ == "__main__":
    main()

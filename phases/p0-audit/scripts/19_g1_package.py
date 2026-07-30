#!/usr/bin/env python3
"""Build G1 report-material package from canonical P0 W3-2c outputs."""

from __future__ import annotations

import csv
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from shapely.geometry import shape

from p0_paths import P0_EVIDENCE, P0_G1_PACKAGE


ROOT = Path(__file__).resolve().parents[1]
DOCS = P0_EVIDENCE
FIGS_W1 = DOCS.figs("W1")
FIGS_W3 = DOCS.figs("W3")
PACKAGE = P0_G1_PACKAGE
PACKAGE_FIGS = PACKAGE / "figs"
CANONICAL_RUN = "w3_2b_roofer_repeatability_20260612_220747/run_2"


FIGURE_SPECS = [
    (
        "fig_01_t2_camera_lod2_overlay.png",
        FIGS_W1 / "t2_opf_pose_overlay.png",
        "T2 OPF camera positions over the LoD2 footprint context; coordinates are EPSG:25832.",
    ),
    (
        "fig_02_figure_1_1a_dim_unrecovered_4907182.png",
        FIGS_W3 / "w3_2c_dim_unrecovered_missing_lod22_DEBY_LOD2_4907182.png",
        "Figure 1.1a replacement: canonical DIM case DEBY_LOD2_4907182 with missing LoD2.2 geometry after wall removal and thinning variants.",
    ),
    (
        "fig_03_figure_1_1b_ridge_4907518.png",
        FIGS_W3 / "w3_1b_matching_overlay_mid_DEBY_LOD2_4907518.png",
        "Figure 1.1b: DEBY_LOD2_4907518 roof-plane matching overlay and ridge/shared-boundary comparison.",
    ),
    (
        "fig_04_plane_f1_boxplot.png",
        FIGS_W3 / "w3_1_plane_f1_boxplot.png",
        "Plane-instance F1 boxplot from the W3 quality run; canonical medians are tabulated in this package.",
    ),
    (
        "fig_05_boundary_error_boxplots.png",
        FIGS_W3 / "w3_1_boundary_error_boxplots.png",
        "Exterior boundary Chamfer and Hausdorff boxplots from the W3 quality run; canonical medians are tabulated in this package.",
    ),
    (
        "fig_06_height_error_boxplots.png",
        FIGS_W3 / "w3_1_height_error_boxplots.png",
        "Height bias and NMAD boxplots from the W3 quality run; canonical medians are tabulated in this package.",
    ),
    (
        "fig_07_matching_overlay_high_4959793.png",
        FIGS_W3 / "w3_1b_matching_overlay_high_DEBY_LOD2_4959793.png",
        "High-F1 spot-check overlay for DEBY_LOD2_4959793.",
    ),
    (
        "fig_08_matching_overlay_low_4906987.png",
        FIGS_W3 / "w3_1b_matching_overlay_low_DEBY_LOD2_4906987.png",
        "Low-F1 spot-check overlay for DEBY_LOD2_4906987.",
    ),
]


def main() -> None:
    if PACKAGE.exists():
        shutil.rmtree(PACKAGE)
    PACKAGE.mkdir(parents=True, exist_ok=True)
    PACKAGE_FIGS.mkdir(parents=True, exist_ok=True)

    paired = read_csv(DOCS / "W3_2c_canonical_paired_status.csv")
    success = by_key(read_csv(DOCS / "W3_2c_canonical_success_rates.csv"), "population")
    quality = by_key(read_csv(DOCS / "W3_2c_canonical_roofer_quality_summary.csv"), "metric")
    internal = by_key(read_csv(DOCS / "W3_2c_canonical_internal_boundary_summary.csv"), "metric")
    thresholds = by_key(read_csv(DOCS / "W3_2c_canonical_threshold_position.csv"), "item")

    copy_existing_figures()
    aoi_caption = render_aoi_map(paired)
    captions = build_captions(aoi_caption)

    core_rows = build_core_rows(paired, success, quality, internal, thresholds)
    write_md(PACKAGE / "core_table.md", render_core_table(core_rows))

    mcnemar_payload = build_mcnemar(paired)
    write_md(PACKAGE / "mcnemar_assembly.md", render_mcnemar(mcnemar_payload))

    write_md(PACKAGE / "appendix_tables.md", render_appendix(paired, success, quality, internal, thresholds))
    write_md(PACKAGE / "captions.md", render_captions(captions))
    write_md(PACKAGE / "source_mapping.md", render_source_mapping(core_rows))
    write_csv(PACKAGE / "g1_core_table.csv", core_rows)
    write_csv(PACKAGE / "mcnemar_assembly.csv", [mcnemar_payload["control_93"], mcnemar_payload["priority_199"]])
    write_manifest(captions)

    print(f"package={rel(PACKAGE)}")
    print(f"figures={len(captions)}")
    print(f"core_rows={len(core_rows)}")
    print(f"mcnemar_p={mcnemar_payload['control_93']['exact_mcnemar_p']}")


def build_core_rows(
    paired: list[dict[str, str]],
    success: dict[str, dict[str, str]],
    quality: dict[str, dict[str, str]],
    internal: dict[str, dict[str, str]],
    thresholds: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    control = [row for row in paired if row["coverage_control_population"] == "yes"]
    n = len(control)
    als_lod22 = sum(row["als_has_lod22"] == "True" for row in control)
    dim_lod22 = sum(row["dim_has_lod22"] == "True" for row in control)
    cc = success["coverage_controlled_93"]

    rows = [
        {
            "metric": "LoD2.2 generation rate (assembly)",
            "ALS": count_rate(als_lod22, n),
            "DIM": count_rate(dim_lod22, n),
            "gap": pp_gap(dim_lod22, als_lod22, n),
            "section6_threshold_position": "no direct Section 6 threshold; paired assembly table reports exact McNemar p",
            "source": "docs/W3_2c_canonical_paired_status.csv; coverage_control_population=yes; *_has_lod22",
        },
        {
            "metric": "Final success rate",
            "ALS": cc["als_success"],
            "DIM": cc["dim_success"],
            "gap": gap_from_rates(cc["dim_success"], cc["als_success"]),
            "section6_threshold_position": "no direct Section 6 threshold",
            "source": "docs/W3_2c_canonical_success_rates.csv; population=coverage_controlled_93",
        },
        {
            "metric": "Plane F1 median",
            "ALS": quality["plane_f1"]["als_median"],
            "DIM": quality["plane_f1"]["dim_median"],
            "gap": quality["plane_f1"]["dim_minus_als"] + " (old harness gap: -0.128571)",
            "section6_threshold_position": threshold_text(thresholds["plane_f1_drop"]),
            "source": "docs/W3_2c_canonical_roofer_quality_summary.csv; metric=plane_f1; old harness from docs/W3_1_threshold_position.csv",
        },
        {
            "metric": "Exterior boundary Chamfer (m)",
            "ALS": quality["boundary_chamfer_m"]["als_median"],
            "DIM": quality["boundary_chamfer_m"]["dim_median"],
            "gap": quality["boundary_chamfer_m"]["dim_minus_als"],
            "section6_threshold_position": threshold_text(thresholds["exterior_boundary_chamfer_ratio"]),
            "source": "docs/W3_2c_canonical_roofer_quality_summary.csv; metric=boundary_chamfer_m",
        },
        {
            "metric": "Internal boundary Hausdorff (m)",
            "ALS": internal["internal_boundary_hausdorff_m"]["als_median"],
            "DIM": internal["internal_boundary_hausdorff_m"]["dim_median"],
            "gap": internal["internal_boundary_hausdorff_m"]["dim_minus_als"],
            "section6_threshold_position": "auxiliary metric; no direct Section 6 threshold",
            "source": "docs/W3_2c_canonical_internal_boundary_summary.csv; metric=internal_boundary_hausdorff_m",
        },
        {
            "metric": "Height NMAD (m)",
            "ALS": quality["height_nmad_m"]["als_median"],
            "DIM": quality["height_nmad_m"]["dim_median"],
            "gap": quality["height_nmad_m"]["dim_minus_als"],
            "section6_threshold_position": "no direct Section 6 threshold",
            "source": "docs/W3_2c_canonical_roofer_quality_summary.csv; metric=height_nmad_m",
        },
        {
            "metric": "val3dity valid rate",
            "ALS": cc["als_val3dity_valid"],
            "DIM": cc["dim_val3dity_valid"],
            "gap": gap_from_rates(cc["dim_val3dity_valid"], cc["als_val3dity_valid"]),
            "section6_threshold_position": threshold_text(thresholds["validity_rate_drop_pp"]),
            "source": "docs/W3_2c_canonical_success_rates.csv; population=coverage_controlled_93",
        },
    ]
    return rows


def build_mcnemar(paired: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    control = [row for row in paired if row["coverage_control_population"] == "yes"]
    dim_only = sum(row["dim_reason"] == "missing_lod22_geometry" and row["als_reason"] != "missing_lod22_geometry" for row in control)
    als_only = sum(row["als_reason"] == "missing_lod22_geometry" and row["dim_reason"] != "missing_lod22_geometry" for row in control)
    both = sum(row["als_reason"] == "missing_lod22_geometry" and row["dim_reason"] == "missing_lod22_geometry" for row in control)
    neither = len(control) - dim_only - als_only - both
    priority_dim = sum(row["dim_failure_bucket_v1"] == "roof_matching_assembly_failure" for row in paired)
    priority_als = sum(row["als_failure_bucket_v1"] == "roof_matching_assembly_failure" for row in paired)
    return {
        "control_93": {
            "population": "coverage_controlled_93",
            "n": str(len(control)),
            "DIM_only_missing_lod22": str(dim_only),
            "ALS_only_missing_lod22": str(als_only),
            "both_missing_lod22": str(both),
            "neither_missing_lod22": str(neither),
            "discordant_pairs": str(dim_only + als_only),
            "exact_mcnemar_p": f"{exact_mcnemar_p(dim_only, als_only):.7f}",
            "source": "docs/W3_2c_canonical_paired_status.csv; coverage_control_population=yes; *_reason=missing_lod22_geometry",
        },
        "priority_199": {
            "population": "priority_accounting_199",
            "n": "199",
            "DIM_only_missing_lod22": str(priority_dim),
            "ALS_only_missing_lod22": str(priority_als),
            "both_missing_lod22": "",
            "neither_missing_lod22": "",
            "discordant_pairs": "",
            "exact_mcnemar_p": "",
            "source": "docs/W3_2c_canonical_input_bucket_summary.csv; bucket_v1=roof_matching_assembly_failure; full_199_count",
        },
    }


def render_core_table(rows: list[dict[str, str]]) -> str:
    visible = [
        {
            "metric": row["metric"],
            "ALS": row["ALS"],
            "DIM": row["DIM"],
            "gap": row["gap"],
            "Section 6 threshold position": row["section6_threshold_position"],
        }
        for row in rows
    ]
    lines = [
        "# G1 Core Table",
        "",
        f"- Canonical Roofer output: `{CANONICAL_RUN}`.",
        "- Denominator for the main comparison rows is the W2-1c coverage-control population, 93 buildings, unless the row notes otherwise.",
        "",
    ]
    lines.extend(markdown_table(visible))
    lines.extend(
        [
            "",
            "Footnote: Plane F1 canonical gap is DIM minus ALS = -0.095238; the pre-canonical W3-1 harness gap was -0.128571.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_mcnemar(payload: dict[str, dict[str, str]]) -> str:
    rows = [payload["control_93"], payload["priority_199"]]
    visible = [
        {
            "population": row["population"],
            "n": row["n"],
            "DIM only missing_lod22": row["DIM_only_missing_lod22"],
            "ALS only missing_lod22": row["ALS_only_missing_lod22"],
            "both missing_lod22": row["both_missing_lod22"],
            "neither missing_lod22": row["neither_missing_lod22"],
            "discordant pairs": row["discordant_pairs"],
            "exact McNemar p": row["exact_mcnemar_p"],
        }
        for row in rows
    ]
    lines = [
        "# McNemar Missing-LoD2.2 Table",
        "",
        "Binary event: `missing_lod22_geometry` for the paired ALS/DIM Roofer output.",
        "",
    ]
    lines.extend(markdown_table(visible))
    lines.extend(
        [
            "",
            "The 199-building row uses the final priority accounting bucket, where roof-matching/assembly is counted after AOI edge, reference mismatch, and coverage separation.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_appendix(
    paired: list[dict[str, str]],
    success: dict[str, dict[str, str]],
    quality: dict[str, dict[str, str]],
    internal: dict[str, dict[str, str]],
    thresholds: dict[str, dict[str, str]],
) -> str:
    lines = ["# G1 Appendix Tables", ""]
    lines.extend(section("Canonical Three-Level Completeness", renamed_success_rows()))
    lines.extend(section("Priority Buckets", read_csv(DOCS / "W3_2c_canonical_priority_buckets.csv")))
    lines.extend(section("Quality Metrics With n", quality_rows_for_appendix(quality, internal)))
    lines.extend(section("Robustness Summary", robustness_rows()))
    lines.extend(section("Canonical Missing-LoD2.2 Variant Trace", recovery_rows(paired)))
    lines.extend(section("Section 6 Threshold Position", list(thresholds.values())))
    lines.extend(section("Old Harness To Canonical Harness Comparison", old_canonical_rows()))
    return "\n".join(lines).rstrip() + "\n"


def quality_rows_for_appendix(
    quality: dict[str, dict[str, str]], internal: dict[str, dict[str, str]]
) -> list[dict[str, str]]:
    rows = []
    for metric in ["plane_f1", "boundary_chamfer_m", "boundary_hausdorff_m", "height_bias_m", "height_nmad_m"]:
        row = quality[metric]
        rows.append(
            {
                "metric": metric,
                "n": row["n"],
                "ALS_median": row["als_median"],
                "DIM_median": row["dim_median"],
                "DIM_minus_ALS": row["dim_minus_als"],
                "DIM_over_ALS": row["dim_over_als"],
                "source": "docs/W3_2c_canonical_roofer_quality_summary.csv",
            }
        )
    for metric in ["internal_boundary_chamfer_m", "internal_boundary_hausdorff_m"]:
        row = internal[metric]
        rows.append(
            {
                "metric": metric,
                "n": row["n_paired_finite"],
                "ALS_median": row["als_median"],
                "DIM_median": row["dim_median"],
                "DIM_minus_ALS": row["dim_minus_als"],
                "DIM_over_ALS": row["dim_over_als"],
                "source": "docs/W3_2c_canonical_internal_boundary_summary.csv",
            }
        )
    return rows


def robustness_rows() -> list[dict[str, str]]:
    tuning = read_csv(DOCS / "W2_3a_paired_success.csv")
    variants = read_csv(DOCS / "W2_3b_variant_success.csv")
    noise = read_csv(DOCS / "W3_2b_roofer_repeatability_noise.csv")
    rows = []
    for row in tuning:
        if row["population"] == "coverage_control_93_all":
            rows.append(
                {
                    "check": f"W2-3a tuning {row['input']}",
                    "population": row["population"],
                    "baseline_or_anchor": row["default_success"],
                    "variant_or_repeat": row["tuned_success"],
                    "delta": f"{row['delta_count']} ({row['delta_percentage_points']} pp)",
                    "source": "docs/W2_3a_paired_success.csv",
                }
            )
    for row in variants:
        if row["population"] == "coverage_control_93_all":
            rows.append(
                {
                    "check": f"W2-3b {row['variant']} DIM",
                    "population": row["population"],
                    "baseline_or_anchor": row["baseline_dim_success"],
                    "variant_or_repeat": row["variant_dim_success"],
                    "delta": f"{row['delta_dim_success_count']} ({row['delta_dim_success_pp']} pp); missing_lod22 to success count {row['roof_matching_recovered_to_success']}",
                    "source": "docs/W2_3b_variant_success.csv",
                }
            )
    for row in noise:
        rows.append(
            {
                "check": f"W3-2b repeatability {row['metric']}",
                "population": "coverage_control_93",
                "baseline_or_anchor": row["success_count_values"],
                "variant_or_repeat": f"{row['n_runs']} runs",
                "delta": f"half-range {row['half_range_pp']} pp",
                "source": "docs/W3_2b_roofer_repeatability_noise.csv",
            }
        )
    return rows


def recovery_rows(paired: list[dict[str, str]]) -> list[dict[str, str]]:
    canonical_ids = [
        row["building_id"]
        for row in paired
        if row["coverage_control_population"] == "yes" and row["dim_reason"] == "missing_lod22_geometry"
    ]
    recovery_by_id: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in read_csv(DOCS / "W2_3b_roof_matching_recovery.csv"):
        recovery_by_id[row["building_id"]][row["variant"]] = row
    rows = []
    for building_id in canonical_ids:
        wall = recovery_by_id.get(building_id, {}).get("wall_removed")
        thin = recovery_by_id.get(building_id, {}).get("thinned")
        rows.append(
            {
                "building_id": building_id,
                "wall_removed": recovery_label(wall),
                "thinned": recovery_label(thin),
                "trace_note": "present in W2-3b trace" if wall or thin else "not in W2-3b 7-case trace; added by canonical run_2",
            }
        )
    return rows


def renamed_success_rows() -> list[dict[str, str]]:
    rows = []
    for row in read_csv(DOCS / "W3_2c_canonical_success_rates.csv"):
        rows.append(
            {
                "population": row["population"],
                "n": row["n"],
                "als_success": row["als_success"],
                "dim_success": row["dim_success"],
                "both_success": row["both_success"],
                "als_only": row["als_only"],
                "dim_only": row["dim_only"],
                "both_non_success": row["both_fail"],
                "als_val3dity_valid": row["als_val3dity_valid"],
                "dim_val3dity_valid": row["dim_val3dity_valid"],
            }
        )
    return rows


def old_canonical_rows() -> list[dict[str, str]]:
    old_success = by_key(read_csv(DOCS / "W2_1c_success_rates.csv"), "population")["coverage_controlled"]
    canonical_success = by_key(read_csv(DOCS / "W3_2c_canonical_success_rates.csv"), "population")["coverage_controlled_93"]
    old_threshold = by_key(read_csv(DOCS / "W3_1_threshold_position.csv"), "p0_section6_item")
    canonical_threshold = by_key(read_csv(DOCS / "W3_2c_canonical_threshold_position.csv"), "item")
    old_buckets = {row["bucket_v1"]: row for row in read_csv(DOCS / "W2_1c_failure_bucket_summary.csv") if row["input"] == "DIM"}
    canonical_buckets = {row["bucket_v1"]: row for row in read_csv(DOCS / "W3_2c_canonical_input_bucket_summary.csv") if row["input"] == "DIM"}
    return [
        {
            "item": "coverage-control paired both success",
            "old_harness": old_success["both_success"],
            "canonical": canonical_success["both_success"],
            "source": "docs/W2_1c_success_rates.csv; docs/W3_2c_canonical_success_rates.csv",
        },
        {
            "item": "ALS final success",
            "old_harness": old_success["als_success"],
            "canonical": canonical_success["als_success"],
            "source": "docs/W2_1c_success_rates.csv; docs/W3_2c_canonical_success_rates.csv",
        },
        {
            "item": "DIM final success",
            "old_harness": old_success["dim_success"],
            "canonical": canonical_success["dim_success"],
            "source": "docs/W2_1c_success_rates.csv; docs/W3_2c_canonical_success_rates.csv",
        },
        {
            "item": "Plane F1 drop",
            "old_harness": old_threshold["plane_f1_drop"]["observed_value"],
            "canonical": canonical_threshold["plane_f1_drop"]["observed_value"],
            "source": "docs/W3_1_threshold_position.csv; docs/W3_2c_canonical_threshold_position.csv",
        },
        {
            "item": "DIM roof-matching bucket",
            "old_harness": old_buckets["roof_matching_assembly_failure"]["coverage_control_count"],
            "canonical": canonical_buckets["roof_matching_assembly_failure"]["coverage_controlled_93_count"],
            "source": "docs/W2_1c_failure_bucket_summary.csv; docs/W3_2c_canonical_input_bucket_summary.csv",
        },
    ]


def copy_existing_figures() -> None:
    for out_name, src, _caption in FIGURE_SPECS:
        if not src.exists():
            raise FileNotFoundError(src)
        shutil.copy2(src, PACKAGE_FIGS / out_name)


def render_aoi_map(paired: list[dict[str, str]]) -> str:
    all_ids = {row["building_id"] for row in paired}
    control_ids = {row["building_id"] for row in paired if row["coverage_control_population"] == "yes"}
    features = json.loads((ROOT / "data/work/footprints/lod2_ground_plan.geojson").read_text(encoding="utf-8"))["features"]
    aoi = json.loads((ROOT / "data/work/footprints/scene_aoi.geojson").read_text(encoding="utf-8"))["features"]

    grouped: dict[str, list] = defaultdict(list)
    for feature in features:
        building_id = feature["properties"]["building_id"]
        if building_id in all_ids:
            grouped[building_id].append(shape(feature["geometry"]))

    fig, ax = plt.subplots(figsize=(10, 9), constrained_layout=True)
    for feature in aoi:
        geom = shape(feature["geometry"])
        plot_geom(ax, geom, facecolor="none", edgecolor="#111111", linewidth=1.6, alpha=1.0)
    for building_id, geometries in grouped.items():
        if building_id in control_ids:
            face, edge, lw, alpha, zorder = "#f59e0b", "#7c2d12", 0.6, 0.78, 3
        else:
            face, edge, lw, alpha, zorder = "#9ca3af", "#374151", 0.35, 0.45, 2
        for geom in geometries:
            plot_geom(ax, geom, facecolor=face, edgecolor=edge, linewidth=lw, alpha=alpha, zorder=zorder)

    ax.set_aspect("equal", adjustable="box")
    ax.set_title("LoD2 footprint population in AOI (199 buildings; 93 coverage-control)")
    ax.set_xlabel("Easting EPSG:25832 (m)")
    ax.set_ylabel("Northing EPSG:25832 (m)")
    ax.grid(color="#d1d5db", linewidth=0.4, alpha=0.8)
    ax.legend(
        handles=[
            Patch(facecolor="#9ca3af", edgecolor="#374151", label="199-building population"),
            Patch(facecolor="#f59e0b", edgecolor="#7c2d12", label="coverage-control 93"),
            Patch(facecolor="none", edgecolor="#111111", label="scene AOI"),
        ],
        loc="best",
        frameon=True,
    )
    out = PACKAGE_FIGS / "fig_09_lod2_aoi_population_map.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return "LoD2 footprint AOI map with the 199-building population and the 93-building coverage-control subset distinguished by fill color."


def plot_geom(ax, geom, **kwargs) -> None:
    if geom.geom_type == "Polygon":
        xs, ys = geom.exterior.xy
        ax.fill(xs, ys, **kwargs)
        for interior in geom.interiors:
            ix, iy = interior.xy
            ax.fill(ix, iy, facecolor="white", edgecolor=kwargs.get("edgecolor", "white"), linewidth=0.2)
    elif geom.geom_type == "MultiPolygon":
        for part in geom.geoms:
            plot_geom(ax, part, **kwargs)


def build_captions(aoi_caption: str) -> list[dict[str, str]]:
    rows = [
        {"figure": f"Figure {idx}", "file": f"figs/{out_name}", "caption": caption}
        for idx, (out_name, _src, caption) in enumerate(FIGURE_SPECS, start=1)
    ]
    rows.append({"figure": "Figure 9", "file": "figs/fig_09_lod2_aoi_population_map.png", "caption": aoi_caption})
    return rows


def render_captions(rows: list[dict[str, str]]) -> str:
    lines = ["# G1 Figure Captions", ""]
    lines.extend(markdown_table(rows))
    return "\n".join(lines) + "\n"


def render_source_mapping(core_rows: list[dict[str, str]]) -> str:
    core_cell_mapping = []
    for row in core_rows:
        for column in ["ALS", "DIM", "gap", "section6_threshold_position"]:
            core_cell_mapping.append(
                {
                    "table": "core_table.md",
                    "row": row["metric"],
                    "cell": column,
                    "source path / row-filter": row["source"],
                }
            )
    appendix_sources = [
        {
            "package item": "appendix completeness table",
            "source path": "docs/W3_2c_canonical_success_rates.csv",
            "row/filter": "all rows",
        },
        {
            "package item": "appendix priority bucket table",
            "source path": "docs/W3_2c_canonical_priority_buckets.csv",
            "row/filter": "all rows",
        },
        {
            "package item": "appendix quality metrics",
            "source path": "docs/W3_2c_canonical_roofer_quality_summary.csv; docs/W3_2c_canonical_internal_boundary_summary.csv",
            "row/filter": "all metric rows",
        },
        {
            "package item": "appendix robustness tuning",
            "source path": "docs/W2_3a_paired_success.csv",
            "row/filter": "population=coverage_control_93_all",
        },
        {
            "package item": "appendix robustness variants",
            "source path": "docs/W2_3b_variant_success.csv; docs/W2_3b_roof_matching_recovery.csv",
            "row/filter": "population=coverage_control_93_all; canonical missing_lod22 IDs",
        },
        {
            "package item": "appendix run noise",
            "source path": "docs/W3_2b_roofer_repeatability_noise.csv",
            "row/filter": "all rows",
        },
        {
            "package item": "appendix old-canonical harness comparison",
            "source path": "docs/W2_1c_success_rates.csv; docs/W3_1_threshold_position.csv; docs/W3_2c_*",
            "row/filter": "coverage_controlled_93 and Section 6 rows",
        },
        {
            "package item": "McNemar assembly table",
            "source path": "docs/W3_2c_canonical_paired_status.csv",
            "row/filter": "coverage_control_population=yes; *_reason=missing_lod22_geometry",
        },
    ]
    lines = [
        "# G1 Numeric Source Mapping",
        "",
        "## Core Table Cell Mapping",
        "",
    ]
    lines.extend(markdown_table(core_cell_mapping))
    lines.extend(["", "## Appendix And Test Tables", ""])
    lines.extend(markdown_table(appendix_sources))
    lines.extend(
        [
            "",
            "Figure source mapping is listed in `captions.md`; copied figures keep their original filenames in the caption text or source path.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_manifest(captions: list[dict[str, str]]) -> None:
    files = sorted(str(path.relative_to(PACKAGE)) for path in PACKAGE.rglob("*") if path.is_file())
    if "manifest.json" not in files:
        files.append("manifest.json")
        files.sort()
    payload = {
        "package": "G1_package",
        "canonical_run": CANONICAL_RUN,
        "files": files,
        "figure_count": len(captions),
    }
    (PACKAGE / "manifest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def section(title: str, rows: list[dict[str, str]]) -> list[str]:
    lines = [f"## {title}", ""]
    lines.extend(markdown_table(rows))
    lines.append("")
    return lines


def recovery_label(row: dict[str, str] | None) -> str:
    if row is None:
        return "not traced"
    if row["recovered_to_success"] == "yes":
        return f"recovered ({row['variant_status']})"
    return f"not recovered ({row['variant_reason']})"


def exact_mcnemar_p(dim_only: int, als_only: int) -> float:
    n = dim_only + als_only
    if n == 0:
        return 1.0
    k = min(dim_only, als_only)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2.0 * tail)


def threshold_text(row: dict[str, str]) -> str:
    return (
        f"observed={row['observed_value']}; threshold={row['threshold_value']}; "
        f"observed-threshold={row['observed_minus_threshold']}"
    )


def gap_from_rates(dim_rate: str, als_rate: str) -> str:
    dim_num, dim_den = parse_count_rate(dim_rate)
    als_num, als_den = parse_count_rate(als_rate)
    if dim_den != als_den:
        return ""
    return pp_gap(dim_num, als_num, dim_den)


def pp_gap(dim_count: int, als_count: int, total: int) -> str:
    return f"{(dim_count - als_count) / total * 100:+.1f} pp"


def parse_count_rate(text: str) -> tuple[int, int]:
    first = text.split()[0]
    num, den = first.split("/")
    return int(num), int(den)


def count_rate(count: int, total: int) -> str:
    return f"{count}/{total} ({count / total * 100:.1f}%)"


def by_key(rows: list[dict[str, str]], key: str) -> dict[str, dict[str, str]]:
    return {row[key]: row for row in rows}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
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


def write_md(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


if __name__ == "__main__":
    main()

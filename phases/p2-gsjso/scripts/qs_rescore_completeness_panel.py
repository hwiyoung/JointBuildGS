#!/usr/bin/env python3
"""R2 learning-zero roof-completeness backfill and qualitative panel.

This script reads existing C001 score and CityJSON artifacts only.  It:

1. appends ``roof_completeness`` to all existing score rows without changing
   any pre-existing field value;
2. pins the existing RMS-minimum, val3dity-valid oracle audit;
3. writes the dense-success 10-building x 4-model panel inventory and figure;
4. recomputes the existing three panel buildings through the same Hausdorff
   code path; and
5. records source/output SHA-256 values.

No learning, reconstruction, Roofer assembly, or new inference is started.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np
from shapely.ops import unary_union

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import e5_c001_8way as metric  # noqa: E402


RUN_ID = "20260718_qs_rescore_completeness_panel"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
DOCS = REPO / "docs"
FIG_DIR = DOCS / "figs/qs_rescore"

SCORES_CSV = DOCS / "qs_rescore_scores.csv"
PAIRS_CSV = DOCS / "qs_rescore_pairs.csv"
FIXED_CSV = DOCS / "qs_rescore_fixed_conditions.csv"
ORACLE_CSV = DOCS / "qs_rescore_oracle_audit.csv"
SOURCE_A_MANIFEST = REPO / "phases/p2-gsjso/runs/20260716_qs_rescore/manifest.json"
SOURCE_FIXED_MANIFEST = (
    REPO / "phases/p2-gsjso/runs/20260717_qs_rescore_fixed_conditions/manifest.json"
)
LOD2_DIR = REPO / "phases/p0-audit/data/raw/lod2"

PANEL_CSV = DOCS / "qs_rescore_topview_panel.csv"
SPOT_CSV = DOCS / "qs_rescore_hausdorff_spotcheck.csv"
FIGURE = FIG_DIR / "qs_rescore_topview_10x4.png"
REPORT = DOCS / "W_qs_rescore_completeness_panel_20260718.md"
RUN_LOG = RUN_DIR / "run.log"
MANIFEST = RUN_DIR / "manifest.json"

REFERENCE_MODEL_ID = "reference_lod2"
DENSE_MODEL_ID = "canonical_dense_w2_1"
FIXED_MODEL_ID = (
    "e5p_405_repair_20260709_C001:"
    "e5p_3b_s1_20260708_C001:"
    "base:"
    "gs_e5_C001_s1_acmp_r1:"
    "run_1"
)
PANEL_COLUMNS = ("reference", "dense_w2_1", "gs_fixed", "gs_oracle")
SPOT_BUILDINGS = (
    "DEBY_LOD2_4907184",
    "DEBY_LOD2_4908168",
    "DEBY_LOD2_4907188",
)
EXPECTED_SCORE_ROWS = 2813
EXPECTED_ALL_BUILDINGS = 18
EXPECTED_DENSE_SUCCESS = 10
EXPECTED_DENSE_SUCCESS_GS_ROWS = 1500
HAUSDORFF_TOLERANCE_M = 5e-9
ISPRS_COMPLETENESS_URL = (
    "https://www.isprs.org/resources/datasets/benchmarks/"
    "IndoorModeling/results.aspx"
)
ISPRS_ACCESSED = "2026-07-18"

PANEL_FIELDS = [
    "building_id",
    "panel_column",
    "panel_order",
    "model_id",
    "selection_scope",
    "role",
    "wave",
    "setting",
    "arm",
    "run",
    "lineage",
    "cityjson_path",
    "cityjson_sha256",
    "z_shift_to_reference_m",
    "has_lod22",
    "val3dity_valid",
    "roof_face_count",
    "roof_rms_m",
    "roof_hausdorff_m",
    "roof_distance_samples",
    "roof_completeness",
    "gt_role",
    "learning_runs_started",
    "new_inference_runs",
]

SPOT_FIELDS = [
    "building_id",
    "panel_column",
    "model_id",
    "z_shift_to_reference_m",
    "stored_roof_rms_m",
    "recomputed_roof_rms_m",
    "delta_roof_rms_m",
    "stored_roof_hausdorff_m",
    "recomputed_roof_hausdorff_m",
    "delta_roof_hausdorff_m",
    "stored_roof_distance_samples",
    "recomputed_roof_distance_samples",
    "max_unlimited_grid_samples_per_model_surface",
    "sample_spacing_m",
    "sample_limit_per_model_surface",
    "direction",
    "distance_component",
    "reference_selection",
    "learning_runs_started",
    "new_inference_runs",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(REPO.resolve()))


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv_with_fields(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        return fields, list(reader)


def read_csv(path: Path) -> list[dict[str, str]]:
    return read_csv_with_fields(path)[1]


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_csv(
    path: Path,
    rows: Sequence[dict[str, Any]],
    fields: Sequence[str],
    *,
    preserve_strings: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            if preserve_strings:
                values = {field: row.get(field, "") for field in fields}
            else:
                values = {field: format_value(row.get(field)) for field in fields}
            writer.writerow(values)
    os.replace(temporary, path)


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (float, np.floating)):
        parsed = float(value)
        return "" if not math.isfinite(parsed) else f"{parsed:.9f}"
    return str(value)


def number(value: Any) -> float | None:
    try:
        if value in (None, "", "None", "none", "nan"):
            return None
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def truth(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def polygon_union(surfaces: Sequence[Any]) -> Any:
    polygons = [
        polygon
        for surface in surfaces
        for polygon in metric.flatten_polygons(surface.polygon)
        if not polygon.is_empty and polygon.area > 0
    ]
    return unary_union(polygons) if polygons else None


def roof_completeness_xy(refs: Sequence[Any], preds: Sequence[Any]) -> float:
    """Area(model-roof XY union intersect reference-roof XY union) / ref area."""
    reference = polygon_union(refs)
    require(
        reference is not None and not reference.is_empty and float(reference.area) > 0,
        "reference roof XY union is empty",
    )
    predicted = polygon_union(preds)
    if predicted is None or predicted.is_empty:
        return 0.0
    value = float(predicted.intersection(reference).area) / float(reference.area)
    require(math.isfinite(value), "non-finite roof_completeness")
    return min(1.0, max(0.0, value))


def validate_score_source(
    fields: Sequence[str],
    rows: Sequence[dict[str, str]],
) -> tuple[list[str], Counter[str]]:
    required = {
        "model_id",
        "role",
        "building_id",
        "cityjson_path",
        "cityjson_sha256",
        "roof_distance_samples",
        "learning_runs_started",
    }
    require(required.issubset(fields), f"score fields missing: {sorted(required - set(fields))}")
    require(len(rows) == EXPECTED_SCORE_ROWS, f"score rows={len(rows)}")
    require(
        all(row.get("learning_runs_started") == "0" for row in rows),
        "score learning_runs_started drift",
    )
    buildings = {row["building_id"] for row in rows}
    require(len(buildings) == EXPECTED_ALL_BUILDINGS, f"score buildings={len(buildings)}")
    require(buildings == set(metric.C001_IDS), "score building population differs from C001_IDS")
    roles = Counter(row["role"] for row in rows)
    require(
        roles
        == Counter(
            {
                "gs": 2741,
                "canonical_dense": 18,
                "dense_sensitivity": 18,
                "als_upper": 18,
                "reference": 18,
            }
        ),
        f"score role cardinality drift: {dict(roles)}",
    )
    output_fields = list(fields)
    if "roof_completeness" not in output_fields:
        insert_at = output_fields.index("roof_distance_samples") + 1
        output_fields.insert(insert_at, "roof_completeness")
    return output_fields, roles


def load_surfaces(
    score_rows: Sequence[dict[str, str]],
    references: dict[str, list[Any]],
) -> tuple[dict[tuple[str, str], list[Any]], dict[str, Path]]:
    targets_by_path: dict[str, set[str]] = defaultdict(set)
    paths: dict[str, Path] = {}
    declared_sha: dict[str, set[str]] = defaultdict(set)
    for row in score_rows:
        if row["role"] == "reference":
            continue
        relative = row["cityjson_path"]
        require(relative not in {"", "phases/p0-audit/data/raw/lod2/*.gml"}, f"missing model path: {row}")
        path = REPO / relative
        require(path.is_file(), f"missing CityJSON: {relative}")
        targets_by_path[relative].add(row["building_id"])
        paths[relative] = path
        if row.get("cityjson_sha256"):
            declared_sha[relative].add(row["cityjson_sha256"])

    for relative, digests in declared_sha.items():
        require(len(digests) == 1, f"multiple declared SHA256 values for {relative}: {digests}")
        measured = sha256_file(paths[relative])
        require(measured in digests, f"CityJSON SHA256 mismatch: {relative}")

    surfaces: dict[tuple[str, str], list[Any]] = {}
    for relative in sorted(targets_by_path):
        parsed = metric.parse_cityjson_roofs(paths[relative], targets_by_path[relative])
        for bid in targets_by_path[relative]:
            surfaces[(relative, bid)] = parsed.get(bid, [])
    for bid, values in references.items():
        surfaces[("reference_lod2", bid)] = values
    return surfaces, paths


def backfill_scores(
    score_fields: Sequence[str],
    score_rows: list[dict[str, str]],
    references: dict[str, list[Any]],
    surfaces: dict[tuple[str, str], list[Any]],
) -> None:
    for row in score_rows:
        bid = row["building_id"]
        predicted = (
            references[bid]
            if row["role"] == "reference"
            else surfaces[(row["cityjson_path"], bid)]
        )
        row["roof_completeness"] = f"{roof_completeness_xy(references[bid], predicted):.9f}"

    values = [number(row["roof_completeness"]) for row in score_rows]
    require(all(value is not None for value in values), "roof_completeness contains blanks")
    require(
        all(0.0 <= float(value) <= 1.0 for value in values if value is not None),
        "roof_completeness outside [0,1]",
    )
    reference_values = [
        row["roof_completeness"] for row in score_rows if row["role"] == "reference"
    ]
    require(
        reference_values == ["1.000000000"] * EXPECTED_ALL_BUILDINGS,
        f"reference self completeness drift: {reference_values}",
    )
    atomic_csv(SCORES_CSV, score_rows, score_fields, preserve_strings=True)


def dense_success_population(
    pair_rows: Sequence[dict[str, str]],
    score_rows: Sequence[dict[str, str]],
) -> list[str]:
    require(len(pair_rows) == EXPECTED_ALL_BUILDINGS, f"pair rows={len(pair_rows)}")
    require(
        all(row.get("learning_runs_started") == "0" for row in pair_rows),
        "pair learning_runs_started drift",
    )
    buildings = [
        row["building_id"] for row in pair_rows if row["population_role"] == "dense_success"
    ]
    require(len(buildings) == EXPECTED_DENSE_SUCCESS, f"dense-success buildings={len(buildings)}")
    gs_rows = sum(
        row["role"] == "gs" and row["building_id"] in set(buildings)
        for row in score_rows
    )
    require(gs_rows == EXPECTED_DENSE_SUCCESS_GS_ROWS, f"dense-success GS rows={gs_rows}")
    return buildings


def unique_score_lookup(
    score_rows: Sequence[dict[str, str]],
) -> dict[tuple[str, str], dict[str, str]]:
    output: dict[tuple[str, str], dict[str, str]] = {}
    for row in score_rows:
        key = (row["model_id"], row["building_id"])
        require(key not in output, f"duplicate score row: {key}")
        output[key] = row
    return output


def build_panel_rows(
    buildings: Sequence[str],
    score_rows: Sequence[dict[str, str]],
    pair_rows: Sequence[dict[str, str]],
    oracle_rows: Sequence[dict[str, str]],
    fixed_rows: Sequence[dict[str, str]],
) -> list[dict[str, Any]]:
    lookup = unique_score_lookup(score_rows)
    pair_by_bid = {row["building_id"]: row for row in pair_rows}
    oracle_by_bid = {row["building_id"]: row for row in oracle_rows}
    require(len(oracle_by_bid) == EXPECTED_ALL_BUILDINGS, f"oracle rows={len(oracle_by_bid)}")
    require(
        all(row.get("learning_runs_started") == "0" for row in oracle_rows),
        "oracle learning_runs_started drift",
    )

    fixed_dense_rows = [
        row
        for row in fixed_rows
        if row.get("condition_id") == FIXED_MODEL_ID and row.get("scope") == "dense_success"
    ]
    require(len(fixed_dense_rows) == 1, "fixed dense-success condition row not unique")
    fixed_summary = fixed_dense_rows[0]
    require(fixed_summary.get("n_rows") == "10", f"fixed n_rows={fixed_summary.get('n_rows')}")
    require(
        fixed_summary.get("condition_selection_scope")
        == "one_fixed_model_condition_no_per_building_switching",
        "fixed-condition scope drift",
    )

    output: list[dict[str, Any]] = []
    for bid in buildings:
        oracle = oracle_by_bid[bid]
        pair = pair_by_bid[bid]
        require(
            oracle["oracle_model_id"] == pair["gs_best_model_id"],
            f"oracle audit differs from pairs for {bid}",
        )
        require(
            oracle.get("oracle_selection_scope")
            == "per_building_oracle_upper_bound_not_fixed_condition",
            f"oracle scope drift for {bid}",
        )
        selections = (
            (
                "reference",
                REFERENCE_MODEL_ID,
                "reference_self_check",
            ),
            (
                "dense_w2_1",
                DENSE_MODEL_ID,
                "canonical_dense_w2_1",
            ),
            (
                "gs_fixed",
                FIXED_MODEL_ID,
                "one_fixed_model_condition_no_per_building_switching",
            ),
            (
                "gs_oracle",
                oracle["oracle_model_id"],
                oracle["oracle_selection_scope"],
            ),
        )
        for panel_order, (panel_column, model_id, selection_scope) in enumerate(
            selections, start=1
        ):
            source = lookup.get((model_id, bid))
            require(source is not None, f"panel score row missing: {(model_id, bid)}")
            require(number(source.get("roof_rms_m")) is not None, f"panel RMS missing: {(model_id, bid)}")
            require(
                number(source.get("roof_hausdorff_m")) is not None,
                f"panel Hausdorff missing: {(model_id, bid)}",
            )
            require(
                number(source.get("roof_completeness")) is not None,
                f"panel completeness missing: {(model_id, bid)}",
            )
            output.append(
                {
                    "building_id": bid,
                    "panel_column": panel_column,
                    "panel_order": panel_order,
                    "model_id": model_id,
                    "selection_scope": selection_scope,
                    "role": source["role"],
                    "wave": source["wave"],
                    "setting": source["setting"],
                    "arm": source["arm"],
                    "run": source["run"],
                    "lineage": source["lineage"],
                    "cityjson_path": source["cityjson_path"],
                    "cityjson_sha256": source["cityjson_sha256"],
                    "z_shift_to_reference_m": source["z_shift_to_reference_m"],
                    "has_lod22": source["has_lod22"],
                    "val3dity_valid": source["val3dity_valid"],
                    "roof_face_count": source["roof_face_count_model"],
                    "roof_rms_m": source["roof_rms_m"],
                    "roof_hausdorff_m": source["roof_hausdorff_m"],
                    "roof_distance_samples": source["roof_distance_samples"],
                    "roof_completeness": source["roof_completeness"],
                    "gt_role": source["gt_role"],
                    "learning_runs_started": 0,
                    "new_inference_runs": 0,
                }
            )
    require(len(output) == EXPECTED_DENSE_SUCCESS * len(PANEL_COLUMNS), f"panel rows={len(output)}")
    return output


def panel_surfaces(
    row: dict[str, Any],
    references: dict[str, list[Any]],
    surfaces: dict[tuple[str, str], list[Any]],
) -> list[Any]:
    bid = str(row["building_id"])
    if row["panel_column"] == "reference":
        return references[bid]
    return surfaces[(str(row["cityjson_path"]), bid)]


def common_bounds(surface_groups: Sequence[Sequence[Any]]) -> tuple[float, float, float, float]:
    polygons = [
        polygon
        for group in surface_groups
        for surface in group
        for polygon in metric.flatten_polygons(surface.polygon)
    ]
    require(bool(polygons), "panel row contains no roof polygons")
    min_x = min(polygon.bounds[0] for polygon in polygons)
    min_y = min(polygon.bounds[1] for polygon in polygons)
    max_x = max(polygon.bounds[2] for polygon in polygons)
    max_y = max(polygon.bounds[3] for polygon in polygons)
    span = max(max_x - min_x, max_y - min_y, 1.0)
    pad = max(0.5, span * 0.04)
    return min_x - pad, min_y - pad, max_x + pad, max_y + pad


def draw_panel_cell(
    axis: Any,
    surfaces: Sequence[Any],
    row: dict[str, Any],
    bounds: tuple[float, float, float, float],
) -> None:
    palette = plt.cm.tab20(np.linspace(0, 1, max(len(surfaces), 1)))
    for surface_index, surface in enumerate(surfaces):
        for polygon in metric.flatten_polygons(surface.polygon):
            exterior = np.asarray(polygon.exterior.coords)
            axis.fill(
                exterior[:, 0],
                exterior[:, 1],
                color=palette[surface_index % len(palette)],
                alpha=0.76,
                edgecolor="black",
                linewidth=0.45,
            )
            for interior in polygon.interiors:
                hole = np.asarray(interior.coords)
                axis.fill(hole[:, 0], hole[:, 1], color="white", edgecolor="black", linewidth=0.3)
    if not surfaces:
        axis.text(0.5, 0.5, "no roof geometry", transform=axis.transAxes, ha="center", va="center")
    min_x, min_y, max_x, max_y = bounds
    axis.set_xlim(min_x, max_x)
    axis.set_ylim(min_y, max_y)
    axis.set_aspect("equal", adjustable="box")
    axis.tick_params(labelsize=4)
    axis.set_title(
        f"{row['panel_column']}\n"
        f"faces={row['roof_face_count']} | RMS={float(row['roof_rms_m']):.3f} m\n"
        f"roof_completeness={float(row['roof_completeness']):.3f}",
        fontsize=7,
    )


def make_panel_figure(
    buildings: Sequence[str],
    panel_rows: Sequence[dict[str, Any]],
    references: dict[str, list[Any]],
    surfaces: dict[tuple[str, str], list[Any]],
) -> None:
    by_building: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in panel_rows:
        by_building[str(row["building_id"])].append(row)
    figure, axes = plt.subplots(
        len(buildings),
        len(PANEL_COLUMNS),
        figsize=(16, 31),
        dpi=180,
        squeeze=False,
    )
    for row_index, bid in enumerate(buildings):
        rows = sorted(by_building[bid], key=lambda row: int(row["panel_order"]))
        require(
            [row["panel_column"] for row in rows] == list(PANEL_COLUMNS),
            f"panel column order drift for {bid}",
        )
        groups = [panel_surfaces(row, references, surfaces) for row in rows]
        bounds = common_bounds(groups)
        for column_index, (row, group) in enumerate(zip(rows, groups)):
            draw_panel_cell(axes[row_index, column_index], group, row, bounds)
            if column_index == 0:
                axes[row_index, column_index].set_ylabel(
                    bid.removeprefix("DEBY_LOD2_"),
                    fontsize=8,
                )
    figure.suptitle(
        "C001 dense-success roof-surface instances: "
        "reference | dense w2_1 | GS fixed | GS per-building oracle",
        fontsize=13,
        y=0.998,
    )
    figure.tight_layout(rect=[0, 0, 1, 0.995], h_pad=1.4, w_pad=0.8)
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE)
    plt.close(figure)


def unlimited_grid_sample_count(surfaces: Sequence[Any]) -> int:
    if not surfaces:
        return 0
    return max(
        len(metric.sample_polygon_points(surface.polygon, metric.SAMPLE_SPACING_M, limit=None))
        for surface in surfaces
    )


def build_spot_rows(
    panel_rows: Sequence[dict[str, Any]],
    references: dict[str, list[Any]],
    surfaces: dict[tuple[str, str], list[Any]],
) -> list[dict[str, Any]]:
    selected = [
        row for row in panel_rows if str(row["building_id"]) in set(SPOT_BUILDINGS)
    ]
    require(len(selected) == len(SPOT_BUILDINGS) * len(PANEL_COLUMNS), f"spot panel rows={len(selected)}")
    order = {bid: index for index, bid in enumerate(SPOT_BUILDINGS)}
    selected.sort(key=lambda row: (order[str(row["building_id"])], int(row["panel_order"])))

    output: list[dict[str, Any]] = []
    for row in selected:
        bid = str(row["building_id"])
        raw = panel_surfaces(row, references, surfaces)
        max_grid = unlimited_grid_sample_count(raw)
        require(
            max_grid <= 1200,
            f"spot surface would use RNG-limited samples: {bid} {row['panel_column']} {max_grid}",
        )
        shift = number(row.get("z_shift_to_reference_m")) or 0.0
        predicted = (
            references[bid]
            if row["panel_column"] == "reference"
            else metric.shift_surface_z(raw, shift)
        )
        comparison = metric.compare_building(references[bid], predicted)
        stored_rms = number(row["roof_rms_m"])
        stored_hausdorff = number(row["roof_hausdorff_m"])
        stored_samples = int(float(row["roof_distance_samples"]))
        recomputed_rms = number(comparison["ref_rms_m"])
        recomputed_hausdorff = number(comparison["ref_hausdorff_m"])
        recomputed_samples = int(comparison["ref_distance_samples"])
        require(stored_rms is not None and recomputed_rms is not None, f"spot RMS missing: {bid}")
        require(
            stored_hausdorff is not None and recomputed_hausdorff is not None,
            f"spot Hausdorff missing: {bid}",
        )
        delta_rms = recomputed_rms - stored_rms
        delta_hausdorff = recomputed_hausdorff - stored_hausdorff
        require(
            abs(delta_rms) <= HAUSDORFF_TOLERANCE_M,
            f"spot RMS drift: {bid} {row['panel_column']} delta={delta_rms}",
        )
        require(
            abs(delta_hausdorff) <= HAUSDORFF_TOLERANCE_M,
            f"spot Hausdorff drift: {bid} {row['panel_column']} delta={delta_hausdorff}",
        )
        require(
            stored_samples == recomputed_samples,
            f"spot sample-count drift: {bid} {row['panel_column']} "
            f"{stored_samples}!={recomputed_samples}",
        )
        output.append(
            {
                "building_id": bid,
                "panel_column": row["panel_column"],
                "model_id": row["model_id"],
                "z_shift_to_reference_m": shift,
                "stored_roof_rms_m": stored_rms,
                "recomputed_roof_rms_m": recomputed_rms,
                "delta_roof_rms_m": delta_rms,
                "stored_roof_hausdorff_m": stored_hausdorff,
                "recomputed_roof_hausdorff_m": recomputed_hausdorff,
                "delta_roof_hausdorff_m": delta_hausdorff,
                "stored_roof_distance_samples": stored_samples,
                "recomputed_roof_distance_samples": recomputed_samples,
                "max_unlimited_grid_samples_per_model_surface": max_grid,
                "sample_spacing_m": metric.SAMPLE_SPACING_M,
                "sample_limit_per_model_surface": 1200,
                "direction": "model_to_reference_one_way",
                "distance_component": "absolute_vertical_z_difference",
                "reference_selection": (
                    "covering reference roof with closest z; "
                    "nearest XY reference roof when none covers"
                ),
                "learning_runs_started": 0,
                "new_inference_runs": 0,
            }
        )
    return output


def markdown_table(
    rows: Sequence[dict[str, Any]],
    fields: Sequence[str],
) -> list[str]:
    output = [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    for row in rows:
        output.append(
            "| "
            + " | ".join(str(format_value(row.get(field))).replace("|", "\\|") for field in fields)
            + " |"
        )
    return output


def write_report(
    buildings: Sequence[str],
    score_rows: Sequence[dict[str, str]],
    panel_rows: Sequence[dict[str, Any]],
    spot_rows: Sequence[dict[str, Any]],
) -> None:
    panel_counts = Counter(row["panel_column"] for row in panel_rows)
    lines = [
        "# R2 C001 정성 패널·roof completeness·Hausdorff 정의",
        "",
        "- 측정일: 2026-07-18",
        "- `learning_runs_started=0`",
        "- `new_inference_runs=0`",
        "- 기존 CityJSON·LoD2 채점 산출물 읽기 전용; 학습·재구성·Roofer 조립 없음.",
        "",
        "## 산출 행 수",
        "",
        f"- `qs_rescore_scores.csv`: {len(score_rows)}행, `roof_completeness` 전 행 기재.",
        f"- dense-success 모집단: {len(buildings)}동.",
        f"- top-view panel: {len(panel_rows)}행; 열별 {dict(panel_counts)}.",
        f"- Hausdorff spot 재계산: {len(spot_rows)}행.",
        "",
        "## roof_completeness 정의",
        "",
        "`roof_completeness = area(union(model roof XY) ∩ union(reference roof XY)) "
        "/ area(union(reference roof XY))`",
        "",
        "- 계산 코드 경로: `phases/p2-gsjso/scripts/"
        "qs_rescore_completeness_panel.py`의 `roof_completeness_xy()`.",
        "- 지붕면은 `phases/p2-gsjso/scripts/e5_c001_8way.py`의 "
        "`parse_lod2_roofs()`·`parse_cityjson_roofs()`가 생성한 XY polygon을 사용.",
        "- 모델 지붕면이 없으면 0.0, 참조 자기 대조는 1.0.",
        "- 기존 면 개수 기반 `completeness` 필드는 변경하지 않음.",
        f"- ISPRS completeness 계열 출처: {ISPRS_COMPLETENESS_URL}",
        f"- 접속일: {ISPRS_ACCESSED}. 이번 구현은 roof XY projection, buffer b=0 특수화.",
        "",
        "## roof_hausdorff_m 코드 정의",
        "",
        "- 코드 경로: `phases/p2-gsjso/scripts/e5_c001_8way.py`의 "
        "`reference_distance()`·`sample_polygon_points()`.",
        f"- 모델 지붕면 XY 내부를 {metric.SAMPLE_SPACING_M:.2f} m 격자로 표본화; "
        "면당 최대 1,200표본.",
        "- 각 모델 표본에서 참조 지붕면까지의 수직 z 차이를 계산.",
        "- 같은 XY를 덮는 참조면이 여러 개면 모델 z와 절대차가 가장 작은 참조 z를 사용.",
        "- 덮는 참조면이 없으면 XY 최단거리 참조면을 사용.",
        "- `roof_hausdorff_m = max(abs(z_model - z_reference))`.",
        "- 방향은 모델→참조 단방향이며 참조→모델 표본화와 XY 거리 성분은 없음.",
        "",
        "## 3동 동일 코드 경로 재계산",
        "",
        *markdown_table(
            spot_rows,
            [
                "building_id",
                "panel_column",
                "stored_roof_hausdorff_m",
                "recomputed_roof_hausdorff_m",
                "delta_roof_hausdorff_m",
                "recomputed_roof_distance_samples",
            ],
        ),
        "",
        "## top-view 패널",
        "",
        f"- `{rel(FIGURE)}`",
        "- 열: reference | dense_w2_1 | gs_fixed | gs_oracle.",
        "- 각 건물 행의 네 셀은 동일 XY bounds를 사용.",
        "- 각 셀 주석: 지붕면 수, roof RMS, roof_completeness.",
        "",
        "## 고정 선택 주소",
        "",
        f"- dense: `{DENSE_MODEL_ID}`",
        f"- GS fixed: `{FIXED_MODEL_ID}`",
        "- GS oracle: `docs/experiments/evaluation/qs_rescore/tables/qs_rescore_oracle_audit.csv`의 기존 "
        "`per_building_oracle_upper_bound_not_fixed_condition` 주소.",
        "",
        "판정·게이트 해석 없음.",
        "",
    ]
    atomic_text(REPORT, "\n".join(lines))


def write_manifest(
    score_before_sha256: str,
    score_fields_before: Sequence[str],
    score_fields_after: Sequence[str],
    score_rows: Sequence[dict[str, str]],
    buildings: Sequence[str],
    panel_rows: Sequence[dict[str, Any]],
    spot_rows: Sequence[dict[str, Any]],
    cityjson_paths: Iterable[Path],
) -> None:
    source_files = {
        Path(__file__),
        SCRIPT_DIR / "e5_c001_8way.py",
        PAIRS_CSV,
        FIXED_CSV,
        ORACLE_CSV,
        SOURCE_A_MANIFEST,
        SOURCE_FIXED_MANIFEST,
        *LOD2_DIR.glob("*.gml"),
        *cityjson_paths,
    }
    missing_sources = [rel(path) for path in source_files if not path.is_file()]
    require(not missing_sources, f"manifest sources missing: {missing_sources}")
    outputs = [SCORES_CSV, PANEL_CSV, SPOT_CSV, FIGURE, REPORT, RUN_LOG]
    payload = {
        "schema": "jointbuildgs.qs_rescore_completeness_panel.v1",
        "created_utc": now(),
        "git_head_at_measurement": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=REPO, text=True
        ).strip(),
        "crs": "EPSG:25832",
        "score_rows": len(score_rows),
        "score_fields_before": list(score_fields_before),
        "score_fields_after": list(score_fields_after),
        "score_sha256_before_backfill": score_before_sha256,
        "score_sha256_after_backfill": sha256_file(SCORES_CSV),
        "roof_completeness_definition": (
            "area(union(model roof XY) intersect union(reference roof XY)) "
            "/ area(union(reference roof XY))"
        ),
        "roof_completeness_isprs_lineage": {
            "source": ISPRS_COMPLETENESS_URL,
            "accessed": ISPRS_ACCESSED,
            "specialization": "roof XY projection; buffer b=0",
        },
        "existing_count_based_completeness_preserved": True,
        "dense_success_building_count": len(buildings),
        "dense_success_buildings": list(buildings),
        "dense_success_gs_score_rows": sum(
            row["role"] == "gs" and row["building_id"] in set(buildings)
            for row in score_rows
        ),
        "panel_rows": len(panel_rows),
        "panel_columns": list(PANEL_COLUMNS),
        "panel_bounds": "common XY bounds across four cells within each building row",
        "dense_model_id": DENSE_MODEL_ID,
        "fixed_model_id": FIXED_MODEL_ID,
        "oracle_source": rel(ORACLE_CSV),
        "oracle_selection_scope": "per_building_oracle_upper_bound_not_fixed_condition",
        "spot_buildings": list(SPOT_BUILDINGS),
        "spot_rows": len(spot_rows),
        "roof_hausdorff_definition": {
            "direction": "model_to_reference_one_way",
            "component": "absolute vertical z difference",
            "aggregation": "maximum",
            "sample_spacing_m": metric.SAMPLE_SPACING_M,
            "sample_limit_per_model_surface": 1200,
            "reference_selection": (
                "covering reference roof with closest z; nearest XY reference roof otherwise"
            ),
            "symmetric": False,
            "includes_xy_distance": False,
        },
        "spot_tolerance_m": HAUSDORFF_TOLERANCE_M,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "gt_role": "LoD2 reference used for scoring, XY completeness, figures, and self-check only",
        "interpretation_or_verdict": None,
        "source_sha256": {
            **{"docs/experiments/evaluation/qs_rescore/tables/qs_rescore_scores.csv@before_backfill": score_before_sha256},
            **{
                rel(path): sha256_file(path)
                for path in sorted(source_files, key=lambda value: rel(value))
            },
        },
        "output_sha256": {
            rel(path): sha256_file(path) for path in outputs if path.is_file()
        },
    }
    atomic_text(MANIFEST, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    score_before_sha256 = sha256_file(SCORES_CSV)
    score_fields_before, score_rows = read_csv_with_fields(SCORES_CSV)
    score_fields_after, role_counts = validate_score_source(score_fields_before, score_rows)
    pair_rows = read_csv(PAIRS_CSV)
    fixed_rows = read_csv(FIXED_CSV)
    oracle_rows = read_csv(ORACLE_CSV)
    buildings = dense_success_population(pair_rows, score_rows)

    references = metric.parse_lod2_roofs(LOD2_DIR, set(metric.C001_IDS))
    surfaces, cityjson_paths = load_surfaces(score_rows, references)
    backfill_scores(score_fields_after, score_rows, references, surfaces)

    panel_rows = build_panel_rows(
        buildings,
        score_rows,
        pair_rows,
        oracle_rows,
        fixed_rows,
    )
    atomic_csv(PANEL_CSV, panel_rows, PANEL_FIELDS)
    make_panel_figure(buildings, panel_rows, references, surfaces)

    spot_rows = build_spot_rows(panel_rows, references, surfaces)
    atomic_csv(SPOT_CSV, spot_rows, SPOT_FIELDS)
    write_report(buildings, score_rows, panel_rows, spot_rows)

    atomic_text(
        RUN_LOG,
        "\n".join(
            [
                f"{now()} start learning_runs_started=0 new_inference_runs=0",
                f"{now()} score_rows={len(score_rows)} roles={json.dumps(dict(role_counts), sort_keys=True)}",
                f"{now()} roof_completeness_backfilled={len(score_rows)}",
                f"{now()} panel_rows={len(panel_rows)} spot_rows={len(spot_rows)}",
                f"{now()} complete learning_runs_started=0 new_inference_runs=0",
                "",
            ]
        ),
    )
    write_manifest(
        score_before_sha256,
        score_fields_before,
        score_fields_after,
        score_rows,
        buildings,
        panel_rows,
        spot_rows,
        cityjson_paths.values(),
    )
    print(
        json.dumps(
            {
                "score_rows": len(score_rows),
                "panel_rows": len(panel_rows),
                "spot_rows": len(spot_rows),
                "learning_runs_started": 0,
                "new_inference_runs": 0,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

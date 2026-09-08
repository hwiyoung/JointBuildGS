"""Evaluation-only comparison on common original matching pixels in the left image.

Reads sealed candidates and existing evaluation artifacts. No reference payload is
opened, and neither matching nor candidate geometry is changed.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate as ev

THRESHOLDS_M = (.1, .25, .5)
COLOR_LIMIT_M = 2.
COMPARISONS = (("SRDM_FILTER_OFF", "SRDM_NATIVE"),
               ("SRDM_IMAGE_ONLY", "SRDM_FILTER_OFF"),
               ("SRDM_IMAGE_ONLY", "SRDM_NATIVE"))
LIMITATIONS = (
    "Paired samples use the same left-image pixel, not proven same physical surface. "
    "Only non-interpolated, valid points inside the fixed 3D ROI are paired. "
    "Delta is after minus before nearest-UAS-point distance; negative means distance "
    "reduction, not a correctness or temporal-change label. UAS XY-cell occupancy is "
    "a support proxy, not visibility, and absent support remains unknown. Native point "
    "density and reference coverage still affect distances. Common-pixel summaries "
    "exclude gained/lost pixels; their counts and distances are preserved separately. "
    "No parameter selection, source selection, rematching, or candidate update occurs."
)


def reference_cells(path):
    """Recover full evaluated UAS XY occupancy, without reading the UAS payload."""
    with gzip.open(path, "rt", newline="") as handle:
        return np.array([int(row["cell_id"]) for row in csv.DictReader(handle)
                         if row["UAS_median_z"] != ""], dtype=np.int64)


def measured_rays(payload, distances, domain, cell, ref_cells, shape):
    points = ev.xyz(payload["xyz"], "paired candidate")
    uv = np.asarray(payload["pixel_uv"])
    if uv.shape != (len(points), 2) or not np.isfinite(uv).all() or not np.equal(uv, np.rint(uv)).all():
        raise ValueError("Paired pixel_uv must be integer Nx2 in u,v order")
    uv = uv.astype(np.int64)
    if np.any(uv < 0) or np.any(uv[:, 0] >= shape[1]) or np.any(uv[:, 1] >= shape[0]):
        raise ValueError("Paired pixel_uv exceeds the shared left image")
    if np.asarray(payload["valid"]).shape != shape or np.asarray(payload["disparity"]).shape != shape:
        raise ValueError("Candidate raster shape differs from the shared left image")
    flags = ev.interpolation_flags(payload, len(points))
    if not np.asarray(payload["valid"], bool)[uv[:, 1], uv[:, 0]].all():
        raise ValueError("Paired point addresses an invalid pixel")
    source = np.asarray(distances["candidate_source_index"])
    if source.ndim != 1 or not np.issubdtype(source.dtype, np.integer):
        raise ValueError("Evaluation candidate_source_index must be integer and one-dimensional")
    if np.any(source < 0) or np.any(source >= len(points)) or len(np.unique(source)) != len(source):
        raise ValueError("Evaluation candidate indices are duplicated or out of range")
    if not np.array_equal(np.sort(source), np.flatnonzero(ev.roi_mask(points, domain))):
        raise ValueError("Evaluation candidate membership differs from the fixed ROI")
    distance = np.asarray(distances["candidate_to_reference"], dtype=np.float64)
    if distance.shape != source.shape or np.isnan(distance).any() or np.any(distance < 0):
        raise ValueError("Evaluation distance array is not aligned nonnegative data")
    if not np.array_equal(distances["interpolated"], flags[source]):
        raise ValueError("Evaluation interpolation flags differ from candidate membership")
    raster_ids = uv[source, 1] * shape[1] + uv[source, 0]
    if len(np.unique(raster_ids)) != len(raster_ids):
        raise ValueError("Multiple candidate points occupy the same left pixel")
    original = ~flags[source]
    source, distance, raster_ids = source[original], distance[original], raster_ids[original]
    supported = np.isin(ev.cell_ids(points[source], domain, cell), ref_cells)
    order = np.argsort(raster_ids)
    return {"pixel_id": raster_ids[order], "source_row": source[order],
            "distance": distance[order], "reference_xy_support": supported[order],
            "native_points_in_roi": len(original), "interpolated_points_in_roi": int((~original).sum())}


def align_rays(rays):
    """Join by integer pixel ID; point-array order and nearest matches cannot select pairs."""
    ids = np.unique(np.concatenate([rays[arm]["pixel_id"] for arm in ev.ARMS]))
    source = np.full((len(ids), len(ev.ARMS)), -1, dtype=np.int64)
    distance = np.full(source.shape, np.nan)
    support = np.zeros(source.shape, dtype=bool)
    for index, arm in enumerate(ev.ARMS):
        rows = np.searchsorted(ids, rays[arm]["pixel_id"])
        source[rows, index] = rays[arm]["source_row"]
        distance[rows, index] = rays[arm]["distance"]
        support[rows, index] = rays[arm]["reference_xy_support"]
    return {"pixel_id": ids, "source_row": source, "distance": distance,
            "reference_xy_support": support, "measured": source >= 0}


def delta_statistics(values):
    values = np.asarray(values, dtype=np.float64)
    finite = values[np.isfinite(values)]
    summary = {"n_pixels": len(values), "n_finite_delta": len(finite),
               "n_without_finite_reference_distance": int((~np.isfinite(values)).sum()),
               "mean_delta_m": None, "median_delta_m": None,
               "p05_delta_m": None, "p95_delta_m": None,
               "mean_distance_reduction_m": None, "mean_distance_increase_m": None}
    if len(finite):
        summary.update(mean_delta_m=float(finite.mean()), median_delta_m=float(np.median(finite)),
                       p05_delta_m=float(np.quantile(finite, .05)), p95_delta_m=float(np.quantile(finite, .95)))
        reductions, increases = -finite[finite < 0], finite[finite > 0]
        summary.update(mean_distance_reduction_m=float(reductions.mean()) if len(reductions) else None,
                       mean_distance_increase_m=float(increases.mean()) if len(increases) else None)
    summary["threshold_counts_m"] = {
        str(threshold): {"distance_reduction_ge": int((finite <= -threshold).sum()),
                         "distance_increase_ge": int((finite >= threshold).sum()),
                         "absolute_change_lt": int((np.abs(finite) < threshold).sum())}
        for threshold in THRESHOLDS_M}
    edges = [-np.inf, -2., -1., -.5, -.25, -.1, 0., .1, .25, .5, 1., 2., np.inf]
    counts, _ = np.histogram(finite, bins=edges)
    summary["delta_histogram"] = [{"interval_m": f"[{lo}, {hi})", "count": int(count)}
                                  for lo, hi, count in zip(edges[:-1], edges[1:], counts)]
    summary["display_overrange"] = {"below_minus_2m": int((finite < -COLOR_LIMIT_M).sum()),
                                     "above_plus_2m": int((finite > COLOR_LIMIT_M).sum())}
    return summary


def finite_delta(table, before, after):
    values = np.full(len(table["pixel_id"]), np.nan)
    usable = np.isfinite(table["distance"][:, before]) & np.isfinite(table["distance"][:, after])
    values[usable] = table["distance"][usable, after] - table["distance"][usable, before]
    return values


def comparison_summary(table, before, after, reference_available):
    measured, supported = table["measured"], table["reference_xy_support"]
    common = measured[:, before] & measured[:, after]
    all_three = measured.all(axis=1)
    gained = ~measured[:, before] & measured[:, after]
    lost = measured[:, before] & ~measured[:, after]
    delta = finite_delta(table, before, after)
    output = {"before": ev.ARMS[before], "after": ev.ARMS[after],
              "delta_definition": "after minus before candidate-to-UAS distance; negative is distance reduction",
              "both_measured_pixels": int(common.sum()), "gained_measured_pixels": int(gained.sum()),
              "lost_measured_pixels": int(lost.sum()),
              "neither_measured_pixels_in_three_arm_union": int((~(common | gained | lost)).sum()),
              "net_measured_pixels": int(gained.sum() - lost.sum()),
              "common_all_three_primary": delta_statistics(delta[all_three]),
              "common_pair_auxiliary": delta_statistics(delta[common])}
    for label, selected in (("common_all_three", all_three), ("common_pair", common)):
        categories = {"both_supported": supported[:, before] & supported[:, after],
                      "only_before_supported": supported[:, before] & ~supported[:, after],
                      "only_after_supported": ~supported[:, before] & supported[:, after],
                      "neither_supported_unknown": ~supported[:, before] & ~supported[:, after]}
        output[label + "_reference_xy_support"] = {
            name: {"count": int((selected & category).sum()), "delta": delta_statistics(delta[selected & category])}
            for name, category in categories.items()}
    for label, selected, index in (("gained", gained, after), ("lost", lost, before)):
        output[label] = {"count": int(selected.sum()),
                         "reference_xy_supported": int((selected & supported[:, index]).sum()),
                         "reference_xy_absent_unknown": int((selected & ~supported[:, index]).sum()),
                         "available_arm_distance": ev.distribution(table["distance"][selected, index], THRESHOLDS_M, reference_available)}
    return output


def draw_delta(path, left, table, region_id):
    before, after = 1, 2
    delta = finite_delta(table, before, after)
    common = table["measured"].all(axis=1)
    shown = common & np.isfinite(delta)
    raster = np.full(left.shape[:2], np.nan)
    raster.flat[table["pixel_id"][shown]] = delta[shown]
    fig, axis = plt.subplots(figsize=(11, 8))
    axis.imshow(np.mean(left, axis=2), cmap="gray", vmin=0, vmax=255)
    image = axis.imshow(np.ma.masked_invalid(raster), cmap="coolwarm", vmin=-COLOR_LIMIT_M, vmax=COLOR_LIMIT_M)
    axis.set_title(f"{region_id}: SRDM two-stage reimplementation minus filtering off\n"
                   f"Common original pixels in all 3 arms: {common.sum():,}; finite delta: {shown.sum():,}\n"
                   f"Beyond fixed color range: below -2 m {(delta[shown] < -2).sum():,}; above +2 m {(delta[shown] > 2).sum():,}", fontsize=10)
    axis.set(xlabel="left pixel u", ylabel="left pixel v")
    fig.colorbar(image, ax=axis, extend="both", label="Nearest-UAS distance change (m); negative = reduction")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def analyze_region(run_root, eval_root, output, region, config):
    rid = region["id"]
    directory = output / rid
    directory.mkdir()
    pair = ev.load_npz(run_root / rid / "pair.npz")
    shape = pair["left_rgb"].shape[:2]
    cells = reference_cells(eval_root / rid / "height_grid_auxiliary.csv.gz")
    rays = {}
    for arm in ev.ARMS:
        payload = ev.load_npz(run_root / rid / arm / "result.npz")
        raw = ev.load_npz(eval_root / rid / arm / "native_distances.npz")
        rays[arm] = measured_rays(payload, raw, region["domain"], config["xy_cell_m"], cells, shape)
    table = align_rays(rays)
    common = table["measured"].all(axis=1)
    comparisons = {}
    for before, after in COMPARISONS:
        comparisons[before + "_to_" + after] = comparison_summary(
            table, ev.ARMS.index(before), ev.ARMS.index(after), bool(region["reference_points"]))
    summary = {"id": rid, "scientific_verdict": None, "reference_status": region["status"],
               "fixed_domain": region["domain"], "left_image_shape_hw": list(shape),
               "union_measured_pixels": len(table["pixel_id"]), "common_all_three_measured_pixels": int(common.sum()),
               "arms": {}, "comparisons": comparisons}
    for index, arm in enumerate(ev.ARMS):
        measured = table["measured"][:, index]
        summary["arms"][arm] = {"native_points_in_roi": rays[arm]["native_points_in_roi"],
                                "interpolated_points_in_roi_excluded_from_pairs": rays[arm]["interpolated_points_in_roi"],
                                "original_measured_pixels_in_roi": int(measured.sum()),
                                "common_all_three_fraction_of_measured": float(common.sum() / measured.sum()) if measured.any() else None,
                                "reference_xy_supported": int((measured & table["reference_xy_support"][:, index]).sum()),
                                "reference_xy_absent_unknown": int((measured & ~table["reference_xy_support"][:, index]).sum())}
    header = ["u", "v", "common_all_three"]
    for arm in ev.ARMS:
        header.extend([arm + "_result_row", arm + "_measured", arm + "_distance_to_UAS_m", arm + "_reference_xy_support"])
    header.extend([before + "_to_" + after + "_delta_m" for before, after in COMPARISONS])
    deltas = [finite_delta(table, ev.ARMS.index(before), ev.ARMS.index(after)) for before, after in COMPARISONS]
    def rows(indices):
        for index in indices:
            row = [int(table["pixel_id"][index] % shape[1]), int(table["pixel_id"][index] // shape[1]), int(common[index])]
            for arm_index in range(len(ev.ARMS)):
                measured = table["measured"][index, arm_index]
                row.extend([int(table["source_row"][index, arm_index]) if measured else "",
                            int(measured), float(table["distance"][index, arm_index]) if measured else "",
                            int(table["reference_xy_support"][index, arm_index]) if measured else ""])
            row.extend(float(delta[index]) if np.isfinite(delta[index]) else "" for delta in deltas)
            yield row
    ev.gz_csv(directory / "measured_pixel_union.csv.gz", header, rows(range(len(common))))
    ev.gz_csv(directory / "common_pixel_deltas.csv.gz", header, rows(np.flatnonzero(common)))
    np.savez_compressed(directory / "aligned_rays.npz", arms=np.array(ev.ARMS), **table,
                        common_all_three=common, native_minus_filter_off_delta_m=deltas[0])
    draw_delta(directory / "common_pixel_delta.png", pair["left_rgb"], table, rid)
    ev.write_json(directory / "paired_analysis.json", summary)
    return summary


def run(run_root, eval_root, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Run project analysis in Docker")
    document = ev.read_json(eval_root / "evaluation.json")
    if document.get("scientific_verdict", "missing") is not None or document.get("reference_accessed") is not True:
        raise ValueError("Completed null-verdict evaluation required")
    if [region["id"] for region in document["regions"]] != list(ev.REGIONS):
        raise ValueError("All three regions in fixed order required")
    if not set(THRESHOLDS_M).issubset(set(document["config"]["distance_thresholds_m"])):
        raise ValueError("Paired thresholds must be among the existing fixed evaluation thresholds")
    hashes = {"evaluation.json": ev.sha(eval_root / "evaluation.json")}
    candidate_hashes = document["gate"]["outputs"]
    required = {f"{rid}/{name}" for rid in ev.REGIONS for name in
                ("pair.npz", "decision.npz", *[f"{arm}/result.npz" for arm in ev.ARMS])}
    if not required.issubset(candidate_hashes):
        raise ValueError("Completed evaluation has an incomplete candidate gate")
    for name, expected in candidate_hashes.items():
        path = (run_root / name).resolve()
        if not path.is_relative_to(run_root.resolve()) or ev.sha(path) != expected:
            raise ValueError(f"Sealed candidate changed before paired analysis: {name}")
    for rid in ev.REGIONS:
        for name in ("height_grid_auxiliary.csv.gz", *[f"{arm}/native_distances.npz" for arm in ev.ARMS]):
            hashes[f"{rid}/{name}"] = ev.sha(eval_root / rid / name)
    output.mkdir(parents=True, exist_ok=False)
    regions = [analyze_region(run_root, eval_root, output, region, document["config"])
               for region in document["regions"]]
    ev.write_json(output / "paired_analysis.json", {
        "task_id": "PHD-SRDM-P1P2P3-PAIRED-EVALUATION-v1", "scientific_verdict": None,
        "created_utc": datetime.now(timezone.utc).isoformat(), "reference_payload_opened": False,
        "reads_reference_derived_evaluation_only": True, "candidate_update_performed": False,
        "frame": document["frame"], "thresholds_m": THRESHOLDS_M,
        "fixed_delta_color_range_m": [-COLOR_LIMIT_M, COLOR_LIMIT_M],
        "primary_comparison": "SRDM_FILTER_OFF_to_SRDM_NATIVE on common original pixels in all three arms",
        "limitations": LIMITATIONS, "inherited_evaluation_limitations": document["limitations"],
        "evaluation_input_sha256": hashes, "candidate_sha256": candidate_hashes,
        "analyzer_sha256": ev.sha(__file__), "regions": regions})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--evaluation-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.run_root, args.evaluation_root, args.output)

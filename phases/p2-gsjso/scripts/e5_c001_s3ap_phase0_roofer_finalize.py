#!/usr/bin/env python3
"""Finalize the S3-A-prime P0 Roofer read-out and baseline figures.

This script runs inside the pinned P0 tools container after Roofer.  It merges
CityJSONSeq, executes val3dity, scores roof surfaces against LoD2, and updates
the incremental CSV/manifest.  LoD2 enters only in this post-read-out scoring
and overlay stage.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np
from shapely import make_valid
from shapely.geometry import shape
from shapely.ops import unary_union

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

import e5_c001_8way as metrics
import e5_c001_s3ap_phase0_baselines as base


W2_PATH = base.REPO / "phases/p0-audit/scripts/08_roofer_w2.py"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def positive_count(value: Any) -> bool:
    try:
        return int(float(str(value))) > 0
    except (TypeError, ValueError):
        return False


def normalize_manifest_readout(manifest: dict[str, Any], status: str) -> None:
    readout = manifest.setdefault("roofer_readout", {})
    readout.setdefault("locked_pre_execution_status", readout.get("status"))
    readout["status"] = status
    source_hashes = manifest.setdefault("source_sha256", {})
    for path in [
        Path(__file__),
        base.CONFIG,
        base.REPO / "phases/p2-gsjso/scripts/e5_c001_s3ap_phase0_baselines.py",
        base.REPO / "phases/p2-gsjso/scripts/run_e5_c001_s3ap_phase0_baselines.sh",
    ]:
        source_hashes[base.rel(path)] = base.sha256_file(path)


def val3dity(cityjson: Path, report: Path, log_path: Path) -> int:
    report.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["val3dity", cityjson.as_posix(), "--report", report.as_posix()],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    base.atomic_text(log_path, "+ val3dity " + cityjson.as_posix() + " --report " + report.as_posix() + "\n" + (proc.stdout or ""))
    return int(proc.returncode)


def update_failure(reason: str, roofer_exit_code: int, jsonl_count: int) -> None:
    rows = read_csv(base.OUT_P0)
    for row in rows:
        row.update({
            "roofer_readout_status": "adapter_failed",
            "roofer_block_reason": reason,
            "supplied_footprint_passed_to_roofer": False,
            "point_evidence_derived_roofprint_passed_to_roofer": roofer_exit_code == 0 or jsonl_count > 0,
            "geometry_has_lod22": False,
            "has_lod22": False,
            "val3dity_valid": False,
            "substantive_filter": False,
            "status": "measured_surface_readout_adapter_failed",
        })
    base.atomic_csv(base.OUT_P0, rows, base.P0_FIELDS)
    mvs_rows = read_csv(base.OUT_MVS)
    base.atomic_text(
        base.REPORT,
        base.report_fragment(rows, mvs_rows)
        + "\n### Roofer read-out adapter\n\n"
        + f"- status: `adapter_failed`\n- reason: `{reason}`\n"
        + "- supplied footprint passed to Roofer: `false`\n"
        + "- point-evidence-derived roofprint passed to Roofer: "
        + f"`{str(roofer_exit_code == 0 or jsonl_count > 0).lower()}`\n",
    )
    manifest = json.loads(base.MANIFEST.read_text(encoding="utf-8"))
    manifest.update({
        "finalized_utc": base.now(),
        "roofer_adapter_executed": True,
        "roofer_exit_code": roofer_exit_code,
        "roofer_jsonl_count": jsonl_count,
        "val3dity_executed": False,
        "roofer_adapter_status": "adapter_failed",
        "roofer_adapter_reason": reason,
    })
    normalize_manifest_readout(manifest, "adapter_failed")
    manifest["roofer_input_contract"]["point_evidence_derived_roofprint_passed_to_roofer"] = roofer_exit_code == 0 or jsonl_count > 0
    base.write_progress("complete", [], "complete_with_roofer_adapter_failed")
    base.log(f"roofer finalize adapter_failed reason={reason}")
    output_paths = [
        base.OUT_P0, base.OUT_MVS, base.P0_FIG, base.MVS_FIG, base.P0_POINTS,
        base.P0_ROOFER_LAS, base.DERIVED_ROOFPRINTS, base.REPORT, base.PROGRESS,
        base.RUN_LOG, base.RUN_DIR / "roofer.log", base.RUN_DIR / "roofer.log.json",
    ]
    manifest["output_sha256"] = {
        base.rel(path): base.sha256_file(path)
        for path in output_paths if path.exists() and path != base.MANIFEST
    }
    base.atomic_text(base.MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


def surface_ring(surface: Any) -> np.ndarray:
    polygon = max(base.flatten_polygons(surface.polygon), key=lambda item: item.area)
    xy = np.asarray(polygon.exterior.coords, dtype=np.float64)
    z = surface.z_at(xy[:, 0], xy[:, 1])
    return np.column_stack([xy, z])


def set_xy_equal_3d(ax: Any, bounds: tuple[float, float, float, float]) -> None:
    minx, miny, maxx, maxy = bounds
    dx = max(maxx - minx, 1.0)
    dy = max(maxy - miny, 1.0)
    ax.set_box_aspect((dx, dy, max(0.35 * max(dx, dy), 1.0)))


def make_roofer_figure(
    targets: Sequence[str],
    predicted: dict[str, list[Any]],
    status_by_id: dict[str, dict[str, str]],
    accepted_has_lod22: dict[str, bool],
    offset: np.ndarray,
    geoid: float,
) -> None:
    footprints = base.load_footprints(targets)
    references = metrics.parse_lod2_roofs(base.LOD2_DIR, {f"DEBY_LOD2_{short}" for short in targets})
    archive = np.load(base.P0_POINTS, allow_pickle=False)
    derived_payload = json.loads(base.DERIVED_ROOFPRINTS.read_text(encoding="utf-8"))
    derived = {
        str(feature["properties"]["building_id"]).removeprefix("DEBY_LOD2_"): make_valid(shape(feature["geometry"]))
        for feature in derived_payload["features"]
    }
    fig = plt.figure(figsize=(13, 12), dpi=170)
    for row_index, short in enumerate(targets):
        bid = f"DEBY_LOD2_{short}"
        footprint = footprints[short]
        centre = np.asarray(footprint.centroid.coords[0], dtype=np.float64)
        fill = np.asarray(archive[f"{bid}_local_xyz"], dtype=np.float64)
        fill_world_xy = fill[:, :2] + offset[:2]
        refs = references[bid]
        preds = predicted[bid]
        status = status_by_id[bid]

        ax0 = fig.add_subplot(len(targets), 2, row_index * 2 + 1)
        base.plot_outline(ax0, derived[short], centre, "#00a6c8", "-", "derived roofprint")
        roof_union = make_valid(unary_union([surface.polygon for surface in refs]))
        base.plot_outline(ax0, roof_union, centre, "#e67e22", "--", "LoD2 roof outline")
        ax0.scatter(
            fill_world_xy[:, 0] - centre[0], fill_world_xy[:, 1] - centre[1],
            s=7, facecolors="none", edgecolors="#00a6c8", linewidths=0.45, label="P0 fill points",
        )
        ax0.set_aspect("equal")
        ax0.set_title(f"{short} point-evidence roofprint | N={len(fill)}")
        ax0.set_xlabel("E-centre [m]")
        ax0.set_ylabel("N-centre [m]")
        ax0.legend(fontsize=6, loc="best")

        ax1 = fig.add_subplot(len(targets), 2, row_index * 2 + 2, projection="3d")
        for index, ref in enumerate(refs):
            ring = surface_ring(ref)
            vertices = np.column_stack([
                ring[:, 0] - centre[0], ring[:, 1] - centre[1], ring[:, 2],
            ])
            ax1.plot(
                vertices[:, 0], vertices[:, 1], vertices[:, 2],
                color="#e67e22", linestyle="--", linewidth=1.2,
            )
        for index, pred in enumerate(preds):
            ring = surface_ring(pred)
            vertices = np.column_stack([
                ring[:, 0] - centre[0], ring[:, 1] - centre[1], ring[:, 2],
            ])
            ax1.add_collection3d(Poly3DCollection(
                [vertices], facecolor="#00a6c8", edgecolor="#007c91", alpha=0.28,
                linewidth=0.9,
            ))
        if not preds:
            ax1.text2D(0.5, 0.5, "0 Roofer roof surfaces", transform=ax1.transAxes, ha="center", va="center")
        ax1.set_title(
            f"Roofer read-out | roofs={len(preds)}, geometry_lod22="
            f"{str(parse_bool(status.get('has_lod22'))).lower()}, accepted="
            f"{str(accepted_has_lod22[bid]).lower()}"
        )
        ax1.set_xlabel("E-centre [m]")
        ax1.set_ylabel("N-centre [m]")
        ax1.set_zlabel("orthometric z [m]")
        set_xy_equal_3d(ax1, tuple(footprint.bounds))
        ax1.view_init(24, -58)
        handles = [Line2D([0], [0], color="#e67e22", linestyle="--", label="LoD2 score outline")]
        if preds:
            handles.insert(0, Line2D([0], [0], color="#00a6c8", linestyle="-", label="Roofer LoD2.2 roof"))
        ax1.legend(handles=handles, fontsize=6, loc="best")
    fig.suptitle(
        "S3-A-prime Phase 0 P0 point-evidence roofprint and Roofer LoD2.2 read-out | EPSG:25832 | LoD2 score/overlay only",
        fontsize=10,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(base.ROOFER_FIG)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roofer-exit-code", type=int, required=True)
    args = parser.parse_args()
    config = json.loads(base.CONFIG.read_text(encoding="utf-8"))
    targets = list(config["targets"])
    ids = [f"DEBY_LOD2_{short}" for short in targets]
    jsonl_files = sorted(base.ROOFER_DIR.glob("*.city.jsonl"))
    if args.roofer_exit_code != 0 or not jsonl_files:
        reason = (
            f"roofer_exit_{args.roofer_exit_code}" if args.roofer_exit_code != 0
            else "missing_roofer_output"
        )
        update_failure(reason, args.roofer_exit_code, len(jsonl_files))
        return

    w2 = load_module("phase0_w2_roofer", W2_PATH)
    w2.combine_cityjsonseq(jsonl_files, base.CITYJSON)
    val_exit = val3dity(base.CITYJSON, base.VAL_REPORT, base.VAL_LOG)
    if not base.VAL_REPORT.exists():
        update_failure(f"val3dity_report_missing_exit_{val_exit}", args.roofer_exit_code, len(jsonl_files))
        return
    val_report = json.loads(base.VAL_REPORT.read_text(encoding="utf-8"))
    val_by_id = {
        str(feature.get("id")): feature
        for feature in val_report.get("features", [])
        if feature.get("id") is not None
    }
    roofer_by_id = w2.parse_roofer_features(jsonl_files)
    status_rows = w2.classify_buildings("P0", ids, roofer_by_id, val_by_id)
    base.atomic_csv(base.ROOFER_STATUS, status_rows, list(status_rows[0].keys()))
    status_by_id = {row["building_id"]: row for row in status_rows}
    cityjson_payload = json.loads(base.CITYJSON.read_text(encoding="utf-8"))
    cityobjects = cityjson_payload.get("CityObjects", {})
    object_mapping = {
        bid: {
            "cityjson_path": base.rel(base.CITYJSON),
            "building_object_id": bid if bid in cityobjects else None,
            "child_object_ids": list((cityobjects.get(bid) or {}).get("children", [])),
            "jsonl_file": str((roofer_by_id.get(bid) or {}).get("jsonl_file", "")),
        }
        for bid in ids
    }

    references = metrics.parse_lod2_roofs(base.LOD2_DIR, set(ids))
    predicted_ellip = metrics.parse_cityjson_roofs(base.CITYJSON, set(ids))
    geoid = float(json.loads(base.PROJECTION_DATUM.read_text(encoding="utf-8"))["orthometric_geoid_m"])
    predicted = {
        bid: metrics.shift_surface_z(predicted_ellip[bid], -geoid)
        for bid in ids
    }
    rows = read_csv(base.OUT_P0)
    thresholds = config["roofer_readout"]["substantive_filter"]
    forbidden_modes = set(thresholds["forbid_extrusion_modes"])
    comparisons: dict[str, dict[str, Any]] = {}
    accepted_has_lod22: dict[str, bool] = {}
    for row in rows:
        bid = row["building_id"]
        status = status_by_id[bid]
        comparison = metrics.compare_building(references[bid], predicted[bid])
        comparisons[bid] = comparison
        geometry_has_lod22 = parse_bool(status.get("has_lod22"))
        valid = parse_bool(status.get("val3dity_valid"))
        canonical_readout = bool(
            status.get("status") == "success"
            and status.get("rf_extrusion_mode", "") not in forbidden_modes
            and (positive_count(status.get("rf_roof_planes")) if thresholds["require_roof_planes"] else True)
        )
        has_lod22 = bool(geometry_has_lod22 and canonical_readout)
        accepted_has_lod22[bid] = has_lod22
        completeness = comparison["completeness"]
        rms = comparison["ref_rms_m"]
        substantive = bool(
            has_lod22
            and valid
            and rms is not None
            and float(rms) <= float(thresholds["citygml_roof_rms_max_m"])
            and completeness is not None
            and float(completeness) >= float(thresholds["citygml_completeness_min"])
        )
        row.update({
            "roofer_readout_status": "measured_point_evidence_derived_roofprint",
            "roofer_block_reason": "" if status["reason"] == "success" else status["reason"],
            "supplied_footprint_passed_to_roofer": False,
            "point_evidence_derived_roofprint_passed_to_roofer": True,
            "roofer_status": status["status"],
            "roofer_reason": status["reason"],
            "rf_extrusion_mode": status.get("rf_extrusion_mode", ""),
            "rf_roof_planes": status.get("rf_roof_planes", ""),
            "cityjson_path": object_mapping[bid]["cityjson_path"],
            "cityjson_building_object_id": object_mapping[bid]["building_object_id"],
            "cityjson_child_object_ids": ";".join(object_mapping[bid]["child_object_ids"]),
            "geometry_has_lod22": geometry_has_lod22,
            "has_lod22": has_lod22,
            "val3dity_valid": valid,
            "substantive_filter": substantive,
            "citygml_completeness": completeness,
            "citygml_roof_rms_m": rms,
            "status": (
                "measured_surface_readout_complete"
                if canonical_readout else "measured_surface_readout_filtered_fake_success"
            ),
        })
    base.atomic_csv(base.OUT_P0, rows, base.P0_FIELDS)
    offset = np.asarray(json.loads(base.TRAIN_MANIFEST.read_text(encoding="utf-8"))["world_offset"], dtype=np.float64)
    make_roofer_figure(targets, predicted, status_by_id, accepted_has_lod22, offset, geoid)

    mvs_rows = read_csv(base.OUT_MVS)
    lines = [base.report_fragment(rows, mvs_rows), "### Roofer read-out adapter", ""]
    lines.extend([
        "- supplied footprint passed to Roofer: `false`",
        "- point-evidence-derived roofprint passed to Roofer: `true`",
        "- derived roofprint rule: union of P0 fill-point 0.5 m occupied cells",
        "- indirect dependency: the P0 fill points use the supplied footprint as the permitted fill mask",
        "- substantive filter: requires canonical Roofer success, non-fallback extrusion, roof planes, raw LoD2.2 geometry, val3dity, completeness and roof RMS",
        "",
        "| building | Roofer reason | raw geometry LoD2.2 | accepted has_lod22 | val3dity | completeness | roof RMS (m) | substantive filter |",
        "|---|---|---|---|---|---:|---:|---|",
    ])
    for row in rows:
        lines.append(
            f"| {row['building_id']} | `{row['roofer_reason'] or 'success'}` "
            f"| {row['geometry_has_lod22']} | {row['has_lod22']} | {row['val3dity_valid']} "
            f"| {base.fmt(row['citygml_completeness'])} "
            f"| {base.fmt(row['citygml_roof_rms_m'])} | {row['substantive_filter']} |"
        )
    lines.extend(["", f"![P0 Roofer read-out]({base.rel(base.ROOFER_FIG)})", ""])
    base.atomic_text(base.REPORT, "\n".join(lines))

    manifest = json.loads(base.MANIFEST.read_text(encoding="utf-8"))
    manifest.update({
        "finalized_utc": base.now(),
        "roofer_adapter_executed": True,
        "roofer_exit_code": args.roofer_exit_code,
        "roofer_jsonl_count": len(jsonl_files),
        "val3dity_executed": True,
        "val3dity_exit_code": val_exit,
        "roofer_adapter_status": "measured_point_evidence_derived_roofprint",
        "roofer_status_rows": len(status_rows),
        "cityjson": base.rel(base.CITYJSON),
        "val3dity_report": base.rel(base.VAL_REPORT),
        "substantive_filter": thresholds,
        "cityjson_object_mapping": object_mapping,
    })
    normalize_manifest_readout(manifest, "measured_point_evidence_derived_roofprint")
    manifest["roofer_input_contract"]["point_evidence_derived_roofprint_passed_to_roofer"] = True
    manifest["roofer_input_contract"]["supplied_footprint_passed_to_roofer"] = False
    base.write_progress("complete", targets, "complete")
    base.log(
        f"roofer finalize complete jsonl={len(jsonl_files)} val3dity_exit={val_exit} "
        f"has_lod22={sum(parse_bool(row['has_lod22']) for row in rows)}/{len(rows)}"
    )
    output_paths = [
        base.OUT_P0, base.OUT_MVS, base.P0_FIG, base.MVS_FIG, base.ROOFER_FIG,
        base.P0_POINTS, base.P0_ROOFER_LAS, base.DERIVED_ROOFPRINTS, base.CITYJSON,
        base.VAL_REPORT, base.VAL_LOG, base.ROOFER_STATUS, base.REPORT, base.PROGRESS,
        base.RUN_LOG, base.RUN_DIR / "roofer.log", base.RUN_DIR / "roofer.log.json",
        *jsonl_files,
    ]
    manifest["output_sha256"] = {
        base.rel(path): base.sha256_file(path)
        for path in output_paths if path.exists()
    }
    manifest["readout_rows"] = [
        {
            "building_id": row["building_id"],
            "roofer_status": row["roofer_status"],
            "roofer_reason": row["roofer_reason"],
            "rf_extrusion_mode": row["rf_extrusion_mode"],
            "rf_roof_planes": row["rf_roof_planes"],
            "geometry_has_lod22": parse_bool(row["geometry_has_lod22"]),
            "has_lod22": parse_bool(row["has_lod22"]),
            "val3dity_valid": parse_bool(row["val3dity_valid"]),
            "citygml_completeness": float(row["citygml_completeness"]) if row["citygml_completeness"] else None,
            "citygml_roof_rms_m": float(row["citygml_roof_rms_m"]) if row["citygml_roof_rms_m"] else None,
            "substantive_filter": parse_bool(row["substantive_filter"]),
        }
        for row in rows
    ]
    base.atomic_text(base.MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

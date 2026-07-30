#!/usr/bin/env python3
"""Append E5 pilot GS read-out attributes to pointcloud_attributes v1.3.

Input rows are copied unchanged, then 6 C001 GS runs x 18 buildings are
measured from the run_1 GS-semantic classified LAS files actually fed to
Roofer.  The measurement function and parameters are the same as v1.3.
Observation only; no gate verdict.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import pointcloud_attributes_v1 as base
import e5_pointcloud_attributes_v1_3 as e5a
from e5_pilot_gate_tools import C001_IDS, READOUT_STRING, Z_DATUM_HISTORY, run_names, sha256_file


RUN_ID = "20260707_e5_pilot_attr_v1_3_append"


def cmd_out(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    except FileNotFoundError as exc:
        return f"not_available:{exc.filename}"
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def write_rows(path: Path, fieldnames: list[str], old_rows: list[dict[str, str]], new_rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in old_rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
        for row in new_rows:
            writer.writerow({key: base.fmt(row.get(key)) for key in fieldnames})


def verify_existing_rows(
    original_fields: list[str],
    before_rows: list[dict[str, str]],
    out_csv: Path,
) -> dict[str, object]:
    _, after_rows = read_rows(out_csv)
    diffs = []
    for i, old in enumerate(before_rows):
        new = after_rows[i]
        for field in original_fields:
            if old.get(field, "") != new.get(field, ""):
                diffs.append({"row_index": i, "field": field, "before": old.get(field, ""), "after": new.get(field, "")})
                if len(diffs) >= 10:
                    break
        if len(diffs) >= 10:
            break
    return {
        "existing_rows_checked": len(before_rows),
        "original_columns_checked": len(original_fields),
        "diff_count_first_10": len(diffs),
        "diff_examples": diffs,
    }


def load_status(paths: dict[str, tuple[str, Path]]) -> dict[tuple[str, str], dict[str, str]]:
    out: dict[tuple[str, str], dict[str, str]] = {}
    for label, path in paths.values():
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                out[(row["building_id"], label)] = row
    return out


def arm_name(run_name: str) -> str:
    _, _, _, arm, rep = run_name.split("_")
    return f"gs_{arm}_{rep}"


def status_label(run_name: str) -> str:
    _, _, _, arm, rep = run_name.split("_")
    return f"GS-{arm}-{rep}"


def classified_las(repo: Path, gate_run_id: str, run_name: str, bid: str) -> Path:
    return repo / "phases/p0-audit/runs" / gate_run_id / "roofer" / run_name / "run_1" / f"{bid}_run_1_classified.las"


def recode_no_points(row: dict[str, object]) -> None:
    n = int(float(row.get("n_points_footprint") or 0))
    if n != 0:
        return
    row["pt_density_m2"] = 0.0
    row["density_valid"] = False
    row["density_reason"] = "no_points"
    row["coverage_frac"] = 0.0
    row["hole_frac"] = 1.0
    row["coverage_valid"] = False
    row["coverage_reason"] = "no_points"


def build_rows(args: argparse.Namespace) -> list[dict[str, object]]:
    repo = Path.cwd()
    base.GEOID_MED_M = e5a.E5_GEOID_M
    status_paths = {}
    for name in run_names():
        arm = arm_name(name)
        label = status_label(name)
        base.STATUS_ARM[arm] = label
        status_paths[arm] = (label, repo / "phases/p0-audit/runs" / args.gate_run_id / "status" / f"{name}_run_1.csv")
    status = load_status(status_paths)
    footprints = base.load_footprints(repo / args.footprints, set(C001_IDS))
    roofs = base.load_roof_surfaces(repo / args.lod2_gml_dir, set(C001_IDS))
    ref_invalid = base.load_ref_invalid(repo)
    lidar_fallback = e5a.FullLasSource(
        repo / e5a.v11.SOURCE_ALS,
        "fallback_als_footprint_clip",
        f"ALS classified LAZ orthometric +{e5a.E5_GEOID_M:.1f} m for E5 pilot attribute reference",
    )
    lidar_fallback.z = lidar_fallback.z + e5a.E5_GEOID_M

    rows: list[dict[str, object]] = []
    for name in run_names():
        arm = arm_name(name)
        for bid in C001_IDS:
            poly = footprints[bid]
            las_path = classified_las(repo, args.gate_run_id, name, bid)
            if las_path.exists():
                xyz, cls = base.read_las_footprint(las_path, poly)
                ap = base.ArmPoints(
                    xyz=xyz,
                    cls=cls,
                    source="e5_pilot_gssem_classified_las_run_1",
                    path=str(las_path.relative_to(repo)),
                    z_history=Z_DATUM_HISTORY,
                )
            else:
                ap = base.ArmPoints(
                    xyz=np.empty((0, 3), dtype=np.float64),
                    cls=np.empty((0,), dtype=np.uint8),
                    source="missing_clip",
                    path=str(las_path.relative_to(repo)),
                    z_history=Z_DATUM_HISTORY,
                    note="GS-semantic prep produced no classified LAS for run_1",
                )
            lidar_points = e5a.load_lidar_e5(repo, bid, poly, lidar_fallback)
            lidar_roof = lidar_points.xyz[lidar_points.cls == 6]
            row = base.metric_row(
                repo,
                bid,
                arm,
                poly,
                ap,
                lidar_roof if len(lidar_roof) else None,
                roofs.get(bid, []),
                ref_invalid,
                status,
                args,
            )
            recode_no_points(row)
            row["readout"] = READOUT_STRING
            row["v1_3_run_id"] = args.gate_run_id
            row["v1_3_source_status_csv"] = str(status_paths[arm][1].relative_to(repo))
            rows.append(row)
        print(f"[e5-pilot-attr] {name} processed {len(C001_IDS)}", flush=True)
    return rows


def write_versions(path: Path, args: argparse.Namespace, check: dict[str, object], new_rows: list[dict[str, object]]) -> None:
    repo = Path.cwd()
    inputs = {
        "input_csv": repo / args.input_csv,
        "output_csv": repo / args.out_csv,
        "script": Path(__file__),
        "gate_status": repo / "phases/p0-audit/runs" / args.gate_run_id / "building_reconstruction_status.csv",
    }
    lines = [
        f"run_id: {RUN_ID}",
        f"created_utc: {datetime.now(timezone.utc).isoformat()}",
        "task: E5-B2 pilot GS pointcloud attributes append",
        "mode: observation only; no reconstruction; no retraining",
        "crs_xy: EPSG:25832",
        f"git_head: {cmd_out(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch: {cmd_out(['git', 'branch', '--show-current'])}",
        "docker_image: jointbuildgs-p0-tools:t0",
        f"readout: {READOUT_STRING}",
        f"z_datum_history: {Z_DATUM_HISTORY}",
        "",
        "inputs_with_sha256:",
    ]
    for label, path_obj in inputs.items():
        sha = sha256_file(path_obj) if path_obj.exists() and path_obj.stat().st_size < 200 * 1024 * 1024 else "missing_or_large"
        lines.append(f"  {label}: {path_obj} sha256={sha}")
    lines += [
        "",
        "parameters:",
        f"  grid_cell_m: {args.grid_cell_m}",
        f"  local_plane_radius_m: {args.local_plane_radius_m}",
        f"  m3c2_normal_radius_m: {args.m3c2_normal_radius_m}",
        f"  m3c2_proj_radius_m: {args.m3c2_proj_radius_m}",
        f"  floater_margin_m: {args.floater_margin_m}",
        "",
        "checks:",
        f"  existing_rows_checked: {check['existing_rows_checked']}",
        f"  original_columns_checked: {check['original_columns_checked']}",
        f"  existing_row_diffs: {check['diff_count_first_10']}",
        "",
        "new_row_summary:",
        f"  rows: {len(new_rows)}",
        f"  arm_counts: {dict(Counter(str(r['arm']) for r in new_rows))}",
        "",
        "outputs:",
        f"  {args.out_csv}",
        f"  {args.check_json}",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", default="docs/experiments/input-and-alignment/pointcloud_attributes/tables/pointcloud_attributes_v1_3.csv")
    parser.add_argument("--out-csv", default="docs/experiments/input-and-alignment/pointcloud_attributes/tables/pointcloud_attributes_v1_3.csv")
    parser.add_argument("--check-json", default="docs/experiments/input-and-alignment/pointcloud_attributes/tables/e5_pilot_pointcloud_attributes_v1_3_check.json")
    parser.add_argument("--gate-run-id", default="e5p_gate_20260707_C001")
    parser.add_argument("--footprints", default="phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg")
    parser.add_argument("--lod2-gml-dir", default="phases/p0-audit/data/raw/lod2")
    parser.add_argument("--versions", default=f"phases/p2-gsjso/runs/{RUN_ID}/versions.txt")
    parser.add_argument("--grid-cell-m", type=float, default=0.5)
    parser.add_argument("--local-plane-radius-m", type=float, default=0.75)
    parser.add_argument("--local-plane-min-neighbors", type=int, default=10)
    parser.add_argument("--local-plane-max-cores", type=int, default=3000)
    parser.add_argument("--local-plane-max-neighbors", type=int, default=256)
    parser.add_argument("--m3c2-normal-radius-m", type=float, default=1.0)
    parser.add_argument("--m3c2-proj-radius-m", type=float, default=0.75)
    parser.add_argument("--m3c2-min-neighbors", type=int, default=8)
    parser.add_argument("--m3c2-max-cores", type=int, default=2500)
    parser.add_argument("--floater-margin-m", type=float, default=3.0)
    parser.add_argument("--label-proxy-roof-minus-m", type=float, default=1.0)
    return parser


def main() -> None:
    args = build_argparser().parse_args()
    original_fields, old_rows = read_rows(Path(args.input_csv))
    fieldnames = list(original_fields)
    for extra in ("readout", "v1_3_run_id", "v1_3_source_status_csv"):
        if extra not in fieldnames:
            fieldnames.append(extra)
    new_rows = build_rows(args)
    out_csv = Path(args.out_csv)
    write_rows(out_csv, fieldnames, old_rows, new_rows)
    check = verify_existing_rows(original_fields, old_rows, out_csv)
    check.update({"new_rows": len(new_rows), "arm_counts": dict(Counter(str(r["arm"]) for r in new_rows))})
    if check["diff_count_first_10"] != 0:
        raise RuntimeError(f"existing row invariant failed: {check['diff_examples']}")
    Path(args.check_json).write_text(json.dumps(check, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_versions(Path(args.versions), args, check, new_rows)
    print(json.dumps(check, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

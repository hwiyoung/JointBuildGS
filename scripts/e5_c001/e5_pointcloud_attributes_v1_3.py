#!/usr/bin/env python3
"""Append E5 A4 raw baseline attributes to pointcloud_attributes v1.2.

The existing v1.2 rows are copied byte-for-byte at the CSV field level.  New
rows are measured from the classified point clouds that Roofer actually used
for raw-ACMP and raw-sparse.  Observation only; no reconstruction and no
verdict wording.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import laspy
import numpy as np
from shapely import contains_xy
from shapely.geometry import Polygon

import pointcloud_attributes_v1 as base
import pointcloud_attributes_v1_1 as v11


RUN_ID = "20260706_attr_v1_3"
E5_GEOID_M = 45.7
NEW_ARMS = ("raw_acmp_e5p", "raw_sparse_e5p")
ARM_STATUS = {
    "raw_acmp_e5p": "raw-ACMP",
    "raw_sparse_e5p": "raw-sparse",
}
ARM_READOUT = {
    "raw_acmp_e5p": "original point cloud + SMRF/boundary; Roofer default family",
    "raw_sparse_e5p": "original point cloud + SMRF/boundary; Roofer default family",
}


class FullLasSource:
    def __init__(self, path: Path, source: str, z_history: str):
        self.path = path
        self.source = source
        self.z_history = z_history
        las = laspy.read(str(path))
        self.x = np.asarray(las.x, dtype=np.float64)
        self.y = np.asarray(las.y, dtype=np.float64)
        self.z = np.asarray(las.z, dtype=np.float64)
        self.cls = np.asarray(las.classification, dtype=np.uint8)
        self.grid = base.SortedGrid(np.column_stack([self.x, self.y]), 10.0)

    def clip(self, poly: Polygon) -> tuple[np.ndarray, np.ndarray]:
        minx, miny, maxx, maxy = poly.bounds
        idx = self.grid.query_bbox(minx, miny, maxx, maxy)
        if len(idx) == 0:
            return np.empty((0, 3), dtype=np.float64), np.empty((0,), dtype=np.uint8)
        mask = contains_xy(poly, self.x[idx], self.y[idx])
        idx = idx[mask]
        if len(idx) == 0:
            return np.empty((0, 3), dtype=np.float64), np.empty((0,), dtype=np.uint8)
        return np.column_stack([self.x[idx], self.y[idx], self.z[idx]]), self.cls[idx]


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


def load_status(paths: dict[str, Path]) -> dict[tuple[str, str], dict[str, str]]:
    out: dict[tuple[str, str], dict[str, str]] = {}
    for label, path in paths.items():
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                out[(row["building_id"], label)] = row
    return out


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


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(block_size), b""):
            h.update(block)
    return h.hexdigest()


def cmd_out(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    except FileNotFoundError as exc:
        return f"not_available:{exc.filename}"
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


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


def metric_rows_for_arm(
    repo: Path,
    arm: str,
    source: FullLasSource,
    pop: list[str],
    footprints: dict[str, Polygon],
    roofs: dict[str, list[base.RoofSurface]],
    ref_invalid: dict[str, str],
    status: dict[tuple[str, str], dict[str, str]],
    args: argparse.Namespace,
    run_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    lidar_fallback = FullLasSource(
        repo / v11.SOURCE_ALS,
        "fallback_als_footprint_clip",
        f"ALS classified LAZ orthometric +{E5_GEOID_M:.1f} m for E5 attribute reference",
    )
    lidar_fallback.z = lidar_fallback.z + E5_GEOID_M
    for i, bid in enumerate(pop, 1):
        poly = footprints[bid]
        xyz, cls = source.clip(poly)
        lidar_points = load_lidar_e5(repo, bid, poly, lidar_fallback)
        lidar_roof = lidar_points.xyz[lidar_points.cls == 6]
        ap = base.ArmPoints(
            xyz=xyz,
            cls=cls,
            source=source.source,
            path=str(source.path.relative_to(repo)),
            z_history=source.z_history,
        )
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
        row["readout"] = ARM_READOUT[arm]
        row["v1_3_run_id"] = run_id
        row["v1_3_source_status_csv"] = str(status_path_for_arm(repo, arm, args).relative_to(repo))
        rows.append(row)
        if i % 25 == 0 or i == len(pop):
            print(f"[attr-v1.3] {arm} processed {i}/{len(pop)}", flush=True)
    return rows


def load_lidar_e5(repo: Path, bid: str, poly: Polygon, fallback: FullLasSource) -> base.ArmPoints:
    existing = repo / f"phases/p0-audit/runs/mob_eval/raw_lidar/{bid}_orig_classified.las"
    if existing.exists():
        xyz, cls = base.read_las_footprint(existing, poly)
        if len(xyz):
            xyz[:, 2] += E5_GEOID_M - 48.0
        return base.ArmPoints(
            xyz=xyz,
            cls=cls,
            source="existing_mob_eval_clip_e5_shifted",
            path=str(existing.relative_to(repo)),
            z_history=f"existing raw_lidar clip source history orthometric +48.0 m, adjusted {E5_GEOID_M - 48.0:+.1f} m to E5 +45.7",
        )
    xyz, cls = fallback.clip(poly)
    return base.ArmPoints(
        xyz=xyz,
        cls=cls,
        source=fallback.source,
        path=str(fallback.path.relative_to(repo)),
        z_history=fallback.z_history,
        note="non-persistent fallback footprint clip for E5 attributes",
    )


def status_path_for_arm(repo: Path, arm: str, args: argparse.Namespace) -> Path:
    if arm == "raw_acmp_e5p":
        return repo / "phases/p0-audit/runs" / args.acmp_run_id / "building_reconstruction_status.csv"
    if arm == "raw_sparse_e5p":
        return repo / "phases/p0-audit/runs" / args.sparse_run_id / "building_reconstruction_status.csv"
    raise AssertionError(arm)


def classified_path_for_arm(repo: Path, arm: str, args: argparse.Namespace) -> Path:
    if arm == "raw_acmp_e5p":
        return repo / "phases/p0-audit/runs" / args.acmp_run_id / "classified/raw_acmp_classified.laz"
    if arm == "raw_sparse_e5p":
        return repo / "phases/p0-audit/runs" / args.sparse_run_id / "classified/raw_sparse_classified.laz"
    raise AssertionError(arm)


def z_history_for_arm(arm: str) -> str:
    if arm == "raw_acmp_e5p":
        return "E5 raw-ACMP: acmp_aoi_utm.laz orthometric +45.7 m in tum_mob_raw_to_npz.py; SMRF/boundary classified LAS fed to Roofer"
    if arm == "raw_sparse_e5p":
        return "E5 raw-sparse: COLMAP sparse local points + [690953,5336071,604], no geoid term; SMRF/boundary classified LAS fed to Roofer"
    raise AssertionError(arm)


def summarize_new_rows(rows: list[dict[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {"rows": len(rows), "arm_counts": dict(Counter(str(r["arm"]) for r in rows))}
    for arm in NEW_ARMS:
        sub = [r for r in rows if r["arm"] == arm]
        out[f"{arm}_no_points_rows"] = sum(int(float(r.get("n_points_footprint") or 0)) == 0 for r in sub)
        out[f"{arm}_density_nonzero_rows"] = sum(float(r.get("pt_density_m2") or 0.0) > 0.0 for r in sub)
    return out


def write_versions(path: Path, args: argparse.Namespace, check: dict[str, object], new_rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    inputs = {
        "v1_2_csv": Path(args.v1_2_csv),
        "script": Path(__file__),
        "acmp_status": status_path_for_arm(Path.cwd(), "raw_acmp_e5p", args),
        "sparse_status": status_path_for_arm(Path.cwd(), "raw_sparse_e5p", args),
        "acmp_classified": classified_path_for_arm(Path.cwd(), "raw_acmp_e5p", args),
        "sparse_classified": classified_path_for_arm(Path.cwd(), "raw_sparse_e5p", args),
    }
    lines = [
        f"run_id: {RUN_ID}",
        f"created_utc: {datetime.now(timezone.utc).isoformat()}",
        "task: E5-A4 pointcloud attributes v1.3",
        "mode: observation only; no reconstruction; no retraining; no image projection",
        "crs_xy: EPSG:25832",
        f"git_head: {cmd_out(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch: {cmd_out(['git', 'branch', '--show-current'])}",
        "docker_image: jointbuildgs-p0-tools:t0",
        'run_command: docker run --rm --user "$(id -u):$(id -g)" -v "$PWD":/workspace/JointBuildGS -w /workspace/JointBuildGS jointbuildgs-p0-tools:t0 python3 scripts/e5_c001/e5_pointcloud_attributes_v1_3.py',
        f"python: {cmd_out(['python3', '--version'])}",
        "",
        "height_datum:",
        f"  e5_geoid_m: {E5_GEOID_M}",
        "  no_points_recode: density=0, coverage=0, hole=1 for new rows only",
        "",
        "inputs_with_sha256:",
    ]
    for label, path_obj in inputs.items():
        if path_obj.exists() and path_obj.stat().st_size < 200 * 1024 * 1024:
            sha = sha256_file(path_obj)
        elif path_obj.exists():
            sha = "skipped_large_file"
        else:
            sha = "missing"
        lines.append(f"  {label}: {path_obj} sha256={sha}")
    lines += [
        "",
        "parameters:",
        f"  grid_cell_m: {args.grid_cell_m}",
        f"  local_plane_radius_m: {args.local_plane_radius_m}",
        f"  m3c2_normal_radius_m: {args.m3c2_normal_radius_m}",
        f"  m3c2_proj_radius_m: {args.m3c2_proj_radius_m}",
        f"  floater_margin_m: {args.floater_margin_m}",
        f"  label_proxy_roof_minus_m: {args.label_proxy_roof_minus_m}",
        "",
        "checks:",
        f"  existing_rows_checked: {check['existing_rows_checked']}",
        f"  original_columns_checked: {check['original_columns_checked']}",
        f"  existing_row_diffs: {check['diff_count_first_10']}",
        "",
        "new_row_summary:",
    ]
    summary = summarize_new_rows(new_rows)
    for key, value in summary.items():
        lines.append(f"  {key}: {value}")
    lines += [
        "",
        "outputs:",
        f"  {args.out_csv}",
        f"  {args.check_json}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-2-csv", default="docs/evidence/archive/pointcloud_attributes/v1_2/tables/pointcloud_attributes_v1_2.csv")
    parser.add_argument("--out-csv", default="docs/experiments/input-and-alignment/pointcloud_attributes/tables/pointcloud_attributes_v1_3.csv")
    parser.add_argument("--check-json", default="docs/experiments/input-and-alignment/pointcloud_attributes/tables/e5_pointcloud_attributes_v1_3_check.json")
    parser.add_argument("--population", default="docs/experiments/input-and-alignment/population_aux/tables/population_aux_v4.csv")
    parser.add_argument("--footprints", default="phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg")
    parser.add_argument("--lod2-gml-dir", default="phases/p0-audit/data/raw/lod2")
    parser.add_argument("--acmp-run-id", required=True)
    parser.add_argument("--sparse-run-id", required=True)
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
    repo = Path.cwd()
    base.GEOID_MED_M = E5_GEOID_M
    for arm, status_label in ARM_STATUS.items():
        base.STATUS_ARM[arm] = status_label

    original_fields, old_rows = read_rows(repo / args.v1_2_csv)
    fieldnames = list(original_fields)
    for extra in ("readout", "v1_3_run_id", "v1_3_source_status_csv"):
        if extra not in fieldnames:
            fieldnames.append(extra)

    pop = base.read_population(repo / args.population)
    footprints = base.load_footprints(repo / args.footprints, set(pop))
    roofs = base.load_roof_surfaces(repo / args.lod2_gml_dir, set(pop))
    ref_invalid = base.load_ref_invalid(repo)
    status = load_status(
        {
            "raw-ACMP": status_path_for_arm(repo, "raw_acmp_e5p", args),
            "raw-sparse": status_path_for_arm(repo, "raw_sparse_e5p", args),
        }
    )

    new_rows: list[dict[str, object]] = []
    for arm in NEW_ARMS:
        source = FullLasSource(
            classified_path_for_arm(repo, arm, args),
            "e5_baseline_full_classified_las",
            z_history_for_arm(arm),
        )
        source_run = args.acmp_run_id if arm == "raw_acmp_e5p" else args.sparse_run_id
        new_rows.extend(metric_rows_for_arm(repo, arm, source, pop, footprints, roofs, ref_invalid, status, args, source_run))

    out_csv = repo / args.out_csv
    write_rows(out_csv, fieldnames, old_rows, new_rows)
    check = verify_existing_rows(original_fields, old_rows, out_csv)
    check.update(summarize_new_rows(new_rows))
    if check["diff_count_first_10"] != 0:
        raise RuntimeError(f"v1.2 existing row invariant failed: {check['diff_examples']}")
    Path(args.check_json).write_text(json.dumps(check, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_versions(repo / args.versions, args, check, new_rows)
    print(json.dumps(check, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

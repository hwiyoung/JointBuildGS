#!/usr/bin/env python3
"""Repair and rescore CityJSON shell winding for E5 C001 material.

This writes repaired overlay files only. Original CityJSON, status CSV, and
val3dity reports are left untouched.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from e5_baseline_tools import write_status_csv  # noqa: E402
from e5_pilot_gate_tools import P0_RUNS  # noqa: E402


RUN_ID = "e5p_405_repair_20260709_C001"
REPAIR_ROOT = P0_RUNS / RUN_ID
DEFAULT_SOURCE_RUNS = [
    "e5p_3b_s1_20260708_C001",
    "e5p_corrected_s1_20260709_C001",
    "e5p_corrected_s1_recheck_20260709_C001",
]
FACTOR_SOURCE_RUN = "e5p_s1_full_factor_20260709_C001"

CSV_SUMMARY = REPO / "docs/experiments/joint-optimization/e5_c001_s1_full/tables/e5_c001_s1_full_405_rescore.csv"
CSV_BUILDING = REPO / "docs/experiments/joint-optimization/e5_c001_s1_full/tables/e5_c001_s1_full_405_rescore_building.csv"
CSV_ISSUES = REPO / "docs/experiments/joint-optimization/e5_c001_s1_full/tables/e5_c001_s1_full_405_rescore_issues.csv"


def rel(path: Path | str | None) -> str:
    if path is None:
        return ""
    p = Path(path)
    for root in (REPO, Path("/workspace/JointBuildGS")):
        try:
            return str(p.relative_to(root))
        except ValueError:
            pass
    text = str(p)
    prefix = "/workspace/JointBuildGS/"
    return text[len(prefix) :] if text.startswith(prefix) else text


def capture(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, check=False)
    except FileNotFoundError as exc:
        return f"not_available:{exc.filename}"
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        if not fields:
            fh.write("")
            return
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def tf(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def ring_reverse(value: Any) -> Any:
    if isinstance(value, list) and value and all(isinstance(item, int) for item in value):
        return list(reversed(value))
    if isinstance(value, list):
        return [ring_reverse(item) for item in value]
    return value


def repair_cityjson(source: Path, target: Path, flip_object_ids: set[str]) -> tuple[str, str, bool, int]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    before_vertices = sha_json(payload.get("vertices", []))
    changed = 0
    for obj_id, obj in payload.get("CityObjects", {}).items():
        if obj_id not in flip_object_ids:
            continue
        for geom in obj.get("geometry", []):
            if "boundaries" not in geom:
                continue
            geom_type = str(geom.get("type", ""))
            if geom_type not in {"Solid", "MultiSurface", "CompositeSurface", "MultiSolid", "CompositeSolid"}:
                continue
            geom["boundaries"] = ring_reverse(geom["boundaries"])
            changed += 1
    after_vertices = sha_json(payload.get("vertices", []))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return before_vertices, after_vertices, before_vertices == after_vertices, changed


def flip_ids_from_405(report: dict[str, Any], cityjson: Path) -> set[str]:
    payload = json.loads(cityjson.read_text(encoding="utf-8"))
    objects = payload.get("CityObjects", {})
    out: set[str] = set()
    for feature in report.get("features", []) or []:
        has_405 = False
        for err in feature.get("errors", []) or []:
            try:
                code = int(err.get("code"))
            except (TypeError, ValueError):
                continue
            if code != 405:
                continue
            has_405 = True
            err_id = str(err.get("id", ""))
            match = re.search(r"coid=([^|#]+)", err_id)
            if match:
                out.add(match.group(1))
        if has_405:
            fid = str(feature.get("id", ""))
            obj = objects.get(fid)
            if obj:
                out.update(str(child) for child in obj.get("children", []) or [])
                for parent in obj.get("parents", []) or []:
                    out.add(str(parent))
    return {obj_id for obj_id in out if obj_id in objects}


def run_val3dity(cityjson: Path, report: Path, log: Path, force: bool) -> int:
    if report.exists() and not force:
        return 0
    report.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["val3dity", rel(cityjson), "--report", rel(report)]
    proc = subprocess.run(cmd, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.write_text("+ " + " ".join(cmd) + "\n" + (proc.stdout or ""), encoding="utf-8")
    return int(proc.returncode)


def load_val_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def feature_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(f.get("id")): f for f in report.get("features", []) if f.get("id") is not None}


def error_codes(feature: dict[str, Any] | None) -> list[int]:
    if not feature:
        return []
    out: list[int] = []
    for err in feature.get("errors", []) or []:
        try:
            out.append(int(err.get("code")))
        except (TypeError, ValueError):
            pass
    return out


def all_codes(report: dict[str, Any]) -> Counter[int]:
    c: Counter[int] = Counter()
    for feat in report.get("features", []) or []:
        c.update(error_codes(feat))
    return c


def feature_valid(feature: dict[str, Any] | None) -> bool:
    return bool(feature and feature.get("validity") is True)


def update_status(status_src: Path, status_dst: Path, repaired_features: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    rows = read_csv(status_src)
    out: list[dict[str, str]] = []
    for row in rows:
        item = dict(row)
        bid = item.get("building_id", "")
        val = repaired_features.get(bid)
        if val is not None:
            item["val3dity_valid"] = str(feature_valid(val))
            item["val3dity_errors"] = json.dumps(val.get("errors", []), ensure_ascii=False, separators=(",", ":"))
        has_lod22 = tf(item.get("has_lod22"))
        if has_lod22:
            if val is None:
                item["status"] = "failure"
                item["reason"] = "missing_val3dity_report"
            elif not feature_valid(val):
                item["status"] = "failure"
                item["reason"] = "val3dity_invalid"
            elif item.get("reason") in {"val3dity_invalid", "success"}:
                item["status"] = "success"
                item["reason"] = "success"
        out.append(item)
    if out:
        write_status_csv(status_dst, out)
    return out


def status_path_for(cityjson: Path) -> Path:
    return cityjson.parents[1] / "status" / cityjson.name.replace(".city.json", ".csv")


def val_report_for(cityjson: Path) -> Path:
    return cityjson.parents[1] / "val3dity" / cityjson.name.replace(".city.json", "_val3dity.json")


def repair_paths(source_run: str, cityjson: Path) -> dict[str, Path | str]:
    setting = cityjson.parents[1].name
    name = cityjson.name
    root = REPAIR_ROOT / source_run / setting
    return {
        "setting": setting,
        "cityjson": root / "cityjson" / name,
        "val3dity": root / "val3dity" / name.replace(".city.json", "_val3dity.json"),
        "status": root / "status" / name.replace(".city.json", ".csv"),
        "log": root / "logs" / name.replace(".city.json", "_val3dity.log"),
    }


def summarize_file(
    source_run: str,
    setting: str,
    cityjson: Path,
    repaired_cityjson: Path,
    original_report: dict[str, Any],
    repaired_report: dict[str, Any],
    vertices_same: bool,
    changed_geom_count: int,
    val_returncode: int,
) -> dict[str, Any]:
    orig_features = feature_map(original_report)
    rep_features = feature_map(repaired_report)
    ids = sorted(set(orig_features) | set(rep_features))
    orig_codes = all_codes(original_report)
    rep_codes = all_codes(repaired_report)
    return {
        "source_run_id": source_run,
        "setting": setting,
        "run_name": cityjson.name.replace("_run_1.city.json", ""),
        "cityjson": rel(cityjson),
        "repaired_cityjson": rel(repaired_cityjson),
        "val3dity_returncode": val_returncode,
        "n_features_original": len(orig_features),
        "n_features_repaired": len(rep_features),
        "valid_features_original": sum(feature_valid(orig_features.get(fid)) for fid in ids),
        "valid_features_repaired": sum(feature_valid(rep_features.get(fid)) for fid in ids),
        "invalid_features_original": sum(not feature_valid(orig_features.get(fid)) for fid in ids),
        "invalid_features_repaired": sum(not feature_valid(rep_features.get(fid)) for fid in ids),
        "error_405_original": orig_codes.get(405, 0),
        "error_405_repaired": rep_codes.get(405, 0),
        "error_302_original": orig_codes.get(302, 0),
        "error_302_repaired": rep_codes.get(302, 0),
        "error_306_original": orig_codes.get(306, 0),
        "error_306_repaired": rep_codes.get(306, 0),
        "all_errors_original": ";".join(str(k) for k in sorted(orig_codes)),
        "all_errors_repaired": ";".join(str(k) for k in sorted(rep_codes)),
        "vertices_same": str(vertices_same).lower(),
        "coordinate_rms_delta_m": "0.000000" if vertices_same else "",
        "changed_geometry_count": changed_geom_count,
        "repair_rule": "reverse boundary rings only for CityObjects referenced by original val3dity 405 coid/children",
    }


def building_rows(
    source_run: str,
    setting: str,
    cityjson: Path,
    repaired_cityjson: Path,
    original_report: dict[str, Any],
    repaired_report: dict[str, Any],
    status_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    orig_features = feature_map(original_report)
    rep_features = feature_map(repaired_report)
    status_by_id = {row.get("building_id", ""): row for row in status_rows}
    ids = sorted(set(orig_features) | set(rep_features) | set(status_by_id))
    rows: list[dict[str, Any]] = []
    for fid in ids:
        orig = orig_features.get(fid)
        rep = rep_features.get(fid)
        oc = error_codes(orig)
        rc = error_codes(rep)
        status = status_by_id.get(fid, {})
        rows.append(
            {
                "source_run_id": source_run,
                "setting": setting,
                "run_name": cityjson.name.replace("_run_1.city.json", ""),
                "building_id": fid,
                "has_lod22": status.get("has_lod22", ""),
                "status_after": status.get("status", ""),
                "reason_after": status.get("reason", ""),
                "original_valid": str(feature_valid(orig)).lower() if orig is not None else "",
                "repaired_valid": str(feature_valid(rep)).lower() if rep is not None else "",
                "original_error_codes": ";".join(str(c) for c in oc),
                "repaired_error_codes": ";".join(str(c) for c in rc),
                "removed_405": str(405 in oc and 405 not in rc).lower(),
                "introduced_error_codes": ";".join(str(c) for c in sorted(set(rc) - set(oc))),
                "cityjson": rel(cityjson),
                "repaired_cityjson": rel(repaired_cityjson),
            }
        )
    return rows


def source_cityjson_files(source_run: str, settings: set[str] | None) -> list[Path]:
    root = P0_RUNS / source_run
    if not root.exists():
        return []
    files = sorted(root.glob("*/cityjson/*.city.json"))
    if settings:
        files = [p for p in files if p.parents[1].name in settings]
    return files


def append_issue(rows: list[dict[str, Any]], source_run: str, cityjson: Path, message: str) -> None:
    rows.append(
        {
            "source_run_id": source_run,
            "cityjson": rel(cityjson),
            "message": message,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    issues_md = REPO / "phases/p2-gsjso/docs/issues.md"
    if issues_md.exists():
        line = f"- 2026-07-09 A-4 405 repair: {message} ({rel(cityjson)})"
        text = issues_md.read_text(encoding="utf-8")
        if line not in text:
            with issues_md.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")


def process(args: argparse.Namespace) -> None:
    source_runs = list(args.source_run_id or DEFAULT_SOURCE_RUNS)
    if args.include_factor and FACTOR_SOURCE_RUN not in source_runs:
        source_runs.append(FACTOR_SOURCE_RUN)
    settings = set(args.settings) if args.settings else None
    summary_rows = read_csv(CSV_SUMMARY) if args.append else []
    building_out = read_csv(CSV_BUILDING) if args.append else []
    issues: list[dict[str, Any]] = read_csv(CSV_ISSUES) if args.append else []

    if args.append:
        remove_sources = set(source_runs)
        summary_rows = [r for r in summary_rows if r.get("source_run_id") not in remove_sources]
        building_out = [r for r in building_out if r.get("source_run_id") not in remove_sources]
        issues = [r for r in issues if r.get("source_run_id") not in remove_sources]

    for source_run in source_runs:
        files = source_cityjson_files(source_run, settings)
        if not files:
            append_issue(issues, source_run, P0_RUNS / source_run, "no CityJSON files found")
            continue
        for cityjson in files:
            paths = repair_paths(source_run, cityjson)
            repaired_cityjson = paths["cityjson"]
            repaired_report = paths["val3dity"]
            repaired_status = paths["status"]
            log_path = paths["log"]
            status_src = status_path_for(cityjson)
            original_report_path = val_report_for(cityjson)
            original_report = load_val_report(original_report_path)
            flip_object_ids = flip_ids_from_405(original_report, cityjson)
            before_sha, after_sha, vertices_same, changed_geom_count = repair_cityjson(cityjson, repaired_cityjson, flip_object_ids)
            if before_sha != after_sha or not vertices_same:
                append_issue(issues, source_run, cityjson, "vertex hash changed during winding repair")
            val_rc = run_val3dity(repaired_cityjson, repaired_report, log_path, args.force)
            repaired_payload = load_val_report(repaired_report)
            repaired_features = feature_map(repaired_payload)
            status_rows: list[dict[str, str]] = []
            if status_src.exists():
                status_rows = update_status(status_src, repaired_status, repaired_features)
            else:
                append_issue(issues, source_run, cityjson, "status CSV missing for repaired CityJSON")
            summary_rows.append(
                summarize_file(
                    source_run,
                    str(paths["setting"]),
                    cityjson,
                    repaired_cityjson,
                    original_report,
                    repaired_payload,
                    vertices_same,
                    changed_geom_count,
                    val_rc,
                )
            )
            building_out.extend(
                building_rows(
                    source_run,
                    str(paths["setting"]),
                    cityjson,
                    repaired_cityjson,
                    original_report,
                    repaired_payload,
                    status_rows,
                )
            )
            print(
                json.dumps(
                    {
                        "source_run_id": source_run,
                        "setting": paths["setting"],
                        "cityjson": cityjson.name,
                        "405_before": all_codes(original_report).get(405, 0),
                        "405_after": all_codes(repaired_payload).get(405, 0),
                        "valid_before": summary_rows[-1]["valid_features_original"],
                        "valid_after": summary_rows[-1]["valid_features_repaired"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    write_csv(CSV_SUMMARY, summary_rows)
    write_csv(CSV_BUILDING, building_out)
    write_csv(CSV_ISSUES, issues, ["source_run_id", "cityjson", "message", "timestamp_utc"])
    write_versions(source_runs)
    print(json.dumps({"summary": rel(CSV_SUMMARY), "building": rel(CSV_BUILDING), "issues": rel(CSV_ISSUES)}, ensure_ascii=False))


def write_versions(source_runs: list[str]) -> None:
    REPAIR_ROOT.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id: {RUN_ID}",
        f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}",
        f"git_head: {capture(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch: {capture(['git', 'branch', '--show-current'])}",
        "canonical_changed: no",
        "task: A-4 405 WRONG_ORIENTATION_SHELL repair overlay and rescore",
        "repair_rule: reverse boundary rings only for CityObjects referenced by original val3dity 405 coid/children",
        "coordinate_change: vertices array hash must remain identical; coordinate_rms_delta_m=0 when true",
        f"source_run_ids: {','.join(source_runs)}",
        f"val3dity: {capture(['val3dity', '--version']).replace(chr(10), ' ')}",
        f"python: {capture(['python3', '--version'])}",
        f"summary_csv: {rel(CSV_SUMMARY)}",
        f"building_csv: {rel(CSV_BUILDING)}",
    ]
    (REPAIR_ROOT / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run-id", action="append", default=None)
    parser.add_argument("--settings", nargs="*", default=None)
    parser.add_argument("--include-factor", action="store_true")
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    process(args)


if __name__ == "__main__":
    main()

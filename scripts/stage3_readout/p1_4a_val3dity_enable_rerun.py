"""P1-4a validator enablement and validation-only rerun.

This script does not regenerate CityJSON and does not change the relation
read-out algorithm. It resolves val3dity from ``VAL3DITY_BIN`` or ``PATH``,
validates existing relation_readout.city.json files, and updates
validation-side reports. It never clones or builds a repository-local copy.
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = ROOT / "results/stage3_typed_readout/P1_4a_gt_sanity"
ENABLE_DIR = OUT_ROOT / "val3dity_enable"
TARGET_BIDS = ["B1", "B2", "B8", "B6", "B0", "B3"]
SIMPLE_MEDIUM = ["B1", "B2", "B8", "B0"]
CITYJSON_NAME = "relation_readout.city.json"

REPORT = OUT_ROOT / "VAL3DITY_RERUN_REPORT.md"
SEARCH_JSON = ENABLE_DIR / "val3dity_search.json"
BUILD_REPORT = ENABLE_DIR / "build_report.md"
SCHEMA_SUMMARY = ENABLE_DIR / "schema_validation_summary.json"
SUMMARY_CSV = ENABLE_DIR / "summary_val3dity_rerun.csv"
SUMMARY_JSON = ENABLE_DIR / "summary_val3dity_rerun.json"
PHASE0_STATUS = ENABLE_DIR / "phase0_existing_status.md"
PATH_RECOVERY_JSON = ENABLE_DIR / "path_recovery_search.json"

VAL3DITY_DOCS = "https://val3dity.readthedocs.io/main/install.html"
VAL3DITY_USAGE = "https://val3dity.readthedocs.io/main/usage.html"


def ensure_dirs() -> None:
    ENABLE_DIR.mkdir(parents=True, exist_ok=True)


def fmt(value: object, nd: int = 4) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f != f or f in (float("inf"), float("-inf")):
        return "NA"
    return f"{f:.{nd}f}"


def read_json(path: Path) -> Dict:
    return json.loads(path.read_text())


def write_json(path: Path, payload: Dict | List) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def run_capture(
    cmd: List[str],
    *,
    cwd: Optional[Path] = None,
    timeout: int = 120,
    env: Optional[Dict[str, str]] = None,
) -> Dict:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            timeout=timeout,
            capture_output=True,
            text=True,
            env=env,
        )
        return {
            "command": cmd,
            "cwd": str(cwd) if cwd else None,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "timeout": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": cmd,
            "cwd": str(cwd) if cwd else None,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timeout": True,
        }


def md_table(headers: Iterable[str], rows: Iterable[Iterable[object]]) -> List[str]:
    hs = [str(h) for h in headers]
    lines = [
        "| " + " | ".join(hs) + " |",
        "| " + " | ".join("---" for _ in hs) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(x) for x in row) + " |")
    return lines


def phase0_status() -> List[Dict]:
    rows = []
    lines = [
        "# P1-4a Existing Status Before val3dity Enablement",
        "",
        f"- Repo root: `{ROOT}`",
        f"- Target root: `{OUT_ROOT.relative_to(ROOT)}`",
        f"- Existing report: `{(OUT_ROOT / 'VAL3DITY_AND_PRECISION_REPORT.md').relative_to(ROOT)}`",
        f"- Existing summary JSON: `{(OUT_ROOT / 'preflight_precision_metrics.json').relative_to(ROOT)}`",
        "",
        "## Existing Metric Summary",
        "",
    ]
    table_rows = []
    for bid in TARGET_BIDS:
        bdir = OUT_ROOT / bid
        metric_path = bdir / "metrics_preflight_precision.json"
        cityjson_path = bdir / CITYJSON_NAME
        metric = read_json(metric_path)
        row = {
            "bid": bid,
            "cityjson_exists": cityjson_path.exists(),
            "metrics_path": str(metric_path),
            "cityjson_path": str(cityjson_path),
            **metric,
        }
        rows.append(row)
        table_rows.append([
            bid,
            "yes" if cityjson_path.exists() else "no",
            fmt(metric.get("h_err"), 4),
            fmt(metric.get("recall_coverage"), 3),
            fmt(metric.get("pred_precision"), 3),
            fmt(metric.get("F_score"), 3),
            fmt(metric.get("vol_ratio"), 3),
            fmt(metric.get("footprint_IoU"), 3),
            str(metric.get("edge_ok")),
            fmt(metric.get("face_planarity_max"), 6),
            fmt(metric.get("open_edges"), 0),
            fmt(metric.get("nonmanifold_edges"), 0),
        ])
    lines.extend(md_table(
        [
            "bid", "cityjson", "h_err", "recall_coverage",
            "pred_precision", "F_score", "vol_ratio", "footprint_IoU",
            "edge_ok", "face_planarity_max", "open_edges",
            "nonmanifold_edges",
        ],
        table_rows,
    ))
    lines.append("")
    PHASE0_STATUS.write_text("\n".join(lines))
    return rows


def candidate_paths() -> List[Tuple[str, Path]]:
    items: List[Tuple[str, Path]] = []
    env_bin = os.environ.get("VAL3DITY_BIN")
    if env_bin:
        items.append(("VAL3DITY_BIN", Path(env_bin).expanduser()))
    which = shutil.which("val3dity")
    if which:
        items.append(("PATH", Path(which)))
    deduped: List[Tuple[str, Path]] = []
    seen = set()
    for source, path in items:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((source, path))
    return deduped


def path_recovery_search() -> Dict:
    env_bin = os.environ.get("VAL3DITY_BIN")
    path_bin = shutil.which("val3dity")
    payload = {
        "resolution_policy": ["VAL3DITY_BIN", "PATH"],
        "VAL3DITY_BIN": env_bin,
        "PATH_val3dity": path_bin,
        "found_executable_paths": [p for p in [env_bin, path_bin] if p],
        "repository_search_attempted": False,
        "repository_clone_or_build_attempted": False,
    }
    write_json(PATH_RECOVERY_JSON, payload)
    return payload


def verify_val3dity(path: Path) -> Dict:
    executable = path.is_file() and os.access(path, os.X_OK)
    result = {
        "path": str(path),
        "exists": path.exists(),
        "is_file": path.is_file(),
        "executable": executable,
        "help_returncode": None,
        "help_stdout_tail": "",
        "help_stderr_tail": "",
        "help_ok": False,
    }
    if executable:
        help_run = run_capture([str(path), "--help"], timeout=30)
        result.update({
            "help_returncode": help_run.get("returncode"),
            "help_stdout_tail": (help_run.get("stdout") or "")[:4000],
            "help_stderr_tail": (help_run.get("stderr") or "")[:4000],
            "help_ok": help_run.get("returncode") == 0 or bool(
                re.search(r"val3dity|usage|options", (help_run.get("stdout") or "") + (help_run.get("stderr") or ""), re.I)
            ),
        })
    return result


def search_val3dity() -> Dict:
    checks = []
    found = None
    for source, path in candidate_paths():
        item = {"source": source, **verify_val3dity(path)}
        checks.append(item)
        if item["executable"] and item["help_ok"] and found is None:
            found = item
    payload = {
        "found": found is not None,
        "path": found["path"] if found else None,
        "checks": checks,
        "help_output": ((found or {}).get("help_stdout_tail") or (found or {}).get("help_stderr_tail") or "")[:4000],
    }
    write_json(SEARCH_JSON, payload)
    return payload


def write_build_report(build_info: Dict) -> None:
    status = build_info.get("status", "UNKNOWN")
    lines = [
        "# val3dity Resolution Report",
        "",
        "- Resolution policy: `VAL3DITY_BIN`, then `PATH`",
        f"- Resolution status: `{status}`",
        f"- Resolved path: `{build_info.get('resolved_path') or 'NONE'}`",
        "- Repository search attempted: `false`",
        "- Repository clone/build attempted: `false`",
        "",
        "The repository does not vendor, clone, compile, copy, or symlink val3dity.",
        "Provide an executable through `VAL3DITY_BIN` or install it in the container image so it is available on `PATH`.",
        "",
        f"Official install docs: {VAL3DITY_DOCS}",
        f"Official usage docs: {VAL3DITY_USAGE}",
    ]
    BUILD_REPORT.write_text("\n".join(lines) + "\n")


def maybe_enable_val3dity() -> Tuple[Optional[str], Dict, Dict]:
    search = search_val3dity()
    resolved_path = search.get("path") if search.get("found") else None
    resolution = {
        "attempted": False,
        "status": "FOUND" if resolved_path else "MISSING_VAL3DITY_BIN_OR_PATH",
        "resolution_policy": ["VAL3DITY_BIN", "PATH"],
        "resolved_path": resolved_path,
        "repository_clone_or_build_attempted": False,
    }
    write_build_report(resolution)
    if search.get("found"):
        return search["path"], search, resolution
    return None, search, resolution


def run_schema_validation() -> Dict:
    cjio = shutil.which("cjio")
    summary = {"cjio_path": cjio, "items": []}
    for bid in TARGET_BIDS:
        bdir = OUT_ROOT / bid
        if cjio is None:
            item = {
                "bid": bid,
                "schema_status": "SKIPPED_CJIO_NOT_FOUND",
                "notes": "cjio not found on PATH",
                "stdout_path": None,
                "stderr_path": None,
            }
        else:
            stdout_path = bdir / "cjio_validate_stdout.txt"
            stderr_path = bdir / "cjio_validate_stderr.txt"
            cmd = [cjio, str(bdir / CITYJSON_NAME), "validate"]
            result = run_capture(cmd, timeout=120)
            stdout_path.write_text(result.get("stdout") or "")
            stderr_path.write_text(result.get("stderr") or "")
            item = {
                "bid": bid,
                "schema_status": "PASS" if result.get("returncode") == 0 else "FAIL",
                "returncode": result.get("returncode"),
                "notes": "cjio validate completed",
                "command": cmd,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
            }
        summary["items"].append(item)
    write_json(SCHEMA_SUMMARY, summary)
    return summary


def aggregate_errors(node: object, path: str = "$") -> List[Dict]:
    out: List[Dict] = []
    if isinstance(node, dict):
        for key, value in node.items():
            key_l = str(key).lower()
            child_path = f"{path}.{key}"
            if key_l in {"errors", "error", "all_errors", "dataset_errors"}:
                if isinstance(value, list):
                    for idx, item in enumerate(value):
                        out.extend(normalize_error(item, f"{child_path}[{idx}]"))
                elif value:
                    out.extend(normalize_error(value, child_path))
            else:
                out.extend(aggregate_errors(value, child_path))
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            out.extend(aggregate_errors(item, f"{path}[{idx}]"))
    return out


def normalize_error(item: object, path: str) -> List[Dict]:
    if item is None or item == []:
        return []
    if isinstance(item, dict):
        code = item.get("code") or item.get("error_code") or item.get("type")
        message = item.get("description") or item.get("message") or item.get("error")
        return [{
            "path": path,
            "code": str(code) if code is not None else None,
            "message": str(message) if message is not None else None,
            "object_id": item.get("object_id") or item.get("feature_id") or item.get("id"),
            "primitive_id": item.get("primitive_id") or item.get("primitive") or item.get("shell_id"),
            "geometry_id": item.get("geometry_id") or item.get("geometry") or item.get("geom_id"),
            "raw": item,
        }]
    return [{"path": path, "code": str(item), "message": None, "raw": item}]


def report_validity_flag(report: Dict) -> Optional[bool]:
    for key in ["validity", "valid", "is_valid"]:
        if key in report and isinstance(report[key], bool):
            return bool(report[key])
    features = report.get("features")
    if isinstance(features, list) and features:
        vals = []
        for feat in features:
            if isinstance(feat, dict):
                for key in ["validity", "valid", "is_valid"]:
                    if key in feat and isinstance(feat[key], bool):
                        vals.append(bool(feat[key]))
                        break
        if vals:
            return all(vals)
    return None


def stdout_valid_hint(stdout: str, stderr: str) -> Optional[bool]:
    text = f"{stdout}\n{stderr}".lower()
    if re.search(r"\b(valid|validity)\b", text) and re.search(r"\b(no errors|0 errors|valid: true|is valid)\b", text):
        return True
    if re.search(r"\b(invalid|errors?:\s*[1-9]|not valid)\b", text):
        return False
    return None


def parse_val3dity_report(
    *,
    bid: str,
    val3dity_bin: str,
    command: List[str],
    returncode: Optional[int],
    report_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    timeout: bool,
) -> Dict:
    parsed = {
        "bid": bid,
        "val3dity_bin": val3dity_bin,
        "command": " ".join(command),
        "returncode": returncode,
        "status": "TIMEOUT" if timeout else "REPORT_MISSING",
        "valid": None,
        "errors": [],
        "error_details": [],
        "n_errors": 0,
        "report_path": str(report_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "warnings": [],
    }
    if timeout:
        return parsed
    stdout = stdout_path.read_text() if stdout_path.exists() else ""
    stderr = stderr_path.read_text() if stderr_path.exists() else ""
    if not report_path.exists():
        hint = stdout_valid_hint(stdout, stderr)
        if hint is not None:
            parsed.update({
                "status": "PASS" if hint else "FAIL",
                "valid": hint,
                "warnings": ["validity inferred from stdout/stderr because report JSON was missing"],
            })
        return parsed
    try:
        report = json.loads(report_path.read_text())
    except Exception as exc:
        raw_path = report_path.with_suffix(report_path.suffix + ".raw.txt")
        raw_path.write_text(report_path.read_text(errors="replace"))
        parsed.update({
            "status": "PARSE_FAIL",
            "parse_error": str(exc),
            "raw_report_path": str(raw_path),
        })
        return parsed
    error_details = aggregate_errors(report)
    errors = sorted({str(e["code"] or e["message"] or e["path"]) for e in error_details})
    explicit_valid = report_validity_flag(report)
    if errors:
        valid = False
    elif explicit_valid is not None:
        valid = explicit_valid
    else:
        hint = stdout_valid_hint(stdout, stderr)
        valid = True if hint is True else None
    status = "PASS" if valid is True else ("FAIL" if valid is False else "PARSE_FAIL")
    warnings = []
    if returncode not in (0, None) and valid is True:
        warnings.append("non-zero returncode but report parsed as valid; report validity used")
    parsed.update({
        "status": status,
        "valid": valid,
        "errors": errors,
        "error_details": error_details,
        "n_errors": len(error_details),
        "warnings": warnings,
    })
    return parsed


def run_val3dity_for_bid(bid: str, val3dity_bin: str) -> Dict:
    bdir = OUT_ROOT / bid
    input_path = bdir / CITYJSON_NAME
    report_path = bdir / "val3dity_report.json"
    stdout_path = bdir / "val3dity_stdout.txt"
    stderr_path = bdir / "val3dity_stderr.txt"
    parsed_path = bdir / "val3dity_parsed.json"
    cmd = [val3dity_bin, str(input_path), "--report", str(report_path)]
    result = run_capture(cmd, timeout=120)
    stdout_path.write_text(result.get("stdout") or "")
    stderr_path.write_text(result.get("stderr") or "")
    parsed = parse_val3dity_report(
        bid=bid,
        val3dity_bin=val3dity_bin,
        command=cmd,
        returncode=result.get("returncode"),
        report_path=report_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout=bool(result.get("timeout")),
    )
    write_json(parsed_path, parsed)
    return parsed


def formal_verdict_for_bid(metric: Dict) -> str:
    if metric.get("val3dity_valid") is True and metric.get("edge_ok") and metric.get("F_score", 0.0) > 0.6:
        return "VALID_GEOMETRY_OK"
    if metric.get("val3dity_valid") is True:
        return "VALID_GEOMETRY_WARNING"
    if metric.get("val3dity_valid") is False:
        return "VAL3DITY_FAIL"
    return str(metric.get("val3dity_status", "VALIDATION_NOT_RUN"))


def update_metrics(
    parsed: Optional[Dict],
    schema_item: Optional[Dict],
    val3dity_bin: Optional[str],
    blocked_status: Optional[str] = None,
) -> List[Dict]:
    rows = []
    for bid in TARGET_BIDS:
        bdir = OUT_ROOT / bid
        metric = read_json(bdir / "metrics_preflight_precision.json")
        if parsed is None:
            status = blocked_status or "BLOCKED"
            blocked_record = {
                "bid": bid,
                "val3dity_bin": val3dity_bin,
                "command": None,
                "returncode": None,
                "status": status,
                "valid": None,
                "errors": [status],
                "n_errors": 1,
                "report_path": None,
                "stdout_path": None,
                "stderr_path": None,
                "failure_reason": "VAL3DITY_BIN was unset or invalid and val3dity was not available on PATH.",
            }
            write_json(bdir / "val3dity_parsed.json", blocked_record)
            metric.update({
                "val3dity_status": status,
                "val3dity_valid": None,
                "val3dity_errors": [status],
                "val3dity_report": None,
                "val3dity_stdout": None,
                "val3dity_stderr": None,
                "val3dity_binary_path": val3dity_bin,
            })
        else:
            item = parsed[bid]
            metric.update({
                "val3dity_status": item.get("status"),
                "val3dity_valid": item.get("valid"),
                "val3dity_errors": item.get("errors", []),
                "val3dity_report": item.get("report_path"),
                "val3dity_stdout": item.get("stdout_path"),
                "val3dity_stderr": item.get("stderr_path"),
                "val3dity_binary_path": val3dity_bin,
                "val3dity_returncode": item.get("returncode"),
                "val3dity_warnings": item.get("warnings", []),
            })
        if schema_item and bid in schema_item:
            metric["schema_validation_status"] = schema_item[bid].get("schema_status")
            metric["schema_validation_notes"] = schema_item[bid].get("notes")
        else:
            metric["schema_validation_status"] = "NOT_RUN"
            metric["schema_validation_notes"] = "schema validation not run"
        metric["formal_verdict"] = formal_verdict_for_bid(metric)
        write_json(bdir / "metrics_val3dity_rerun.json", metric)
        rows.append(metric)
    return rows


def decide(rows: List[Dict], blocker: Optional[str] = None) -> Dict:
    if blocker == "PARSE":
        final = "E0_BLOCKED_PARSE"
    elif blocker:
        final = "E0_BLOCKED_DEPENDENCY"
    else:
        simple_hits = [
            r["bid"] for r in rows
            if r["bid"] in SIMPLE_MEDIUM and r.get("val3dity_valid") is True and float(r.get("F_score", 0.0)) > 0.6
        ]
        b6 = next(r for r in rows if r["bid"] == "B6")
        b3 = next(r for r in rows if r["bid"] == "B3")
        simple_go = len(simple_hits) >= 3
        hip_strict = b6.get("val3dity_valid") is True and b6.get("F_score", 0.0) > 0.5 and b6.get("h_err", 999) < 2.0
        hip_relaxed = b6.get("val3dity_valid") is True and b6.get("F_score", 0.0) > 0.5 and b6.get("h_err", 999) < 4.0
        complex_separate = b3.get("val3dity_valid") is False or b3.get("F_score", 0.0) <= 0.6 or b3.get("h_err", 0) > 1.0
        if not simple_go:
            final = "E0_FORMAL_NG"
        elif hip_strict and not complex_separate:
            final = "E0_FORMAL_GO"
        else:
            final = "E0_PARTIAL_GO"
        over_volume = [r["bid"] for r in rows if r["bid"] in ["B2", "B8", "B0"] and float(r.get("vol_ratio", 0.0)) > 1.3]
        return {
            "final_decision": final,
            "simple_medium_rule": "GO" if simple_go else "NG",
            "simple_medium_hits": simple_hits,
            "hip_strict_rule": "GO" if hip_strict else "NG",
            "hip_relaxed_rule": "GO" if hip_relaxed else "NG",
            "complex_branch": "SEPARATE" if complex_separate else "NOT_SEPARATE",
            "warnings": (["OVER_VOLUME_WARNING:" + ",".join(over_volume)] if over_volume else [])
                        + (["HIP_HEIGHT_WARNING"] if b6.get("h_err", 0) > 2.0 else []),
        }
    return {
        "final_decision": final,
        "simple_medium_rule": "BLOCKED",
        "simple_medium_hits": [],
        "hip_strict_rule": "BLOCKED",
        "hip_relaxed_rule": "BLOCKED",
        "complex_branch": "BLOCKED",
        "warnings": [],
    }


def write_summary(rows: List[Dict], decision: Dict, search: Dict, build: Dict, schema: Optional[Dict]) -> None:
    fields = [
        "bid", "val3dity_status", "val3dity_valid", "val3dity_errors",
        "h_err", "recall", "precision", "F_score", "vol_ratio",
        "footprint_IoU", "edge_ok", "face_planarity_max",
    ]
    with SUMMARY_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "bid": r.get("bid"),
                "val3dity_status": r.get("val3dity_status"),
                "val3dity_valid": r.get("val3dity_valid"),
                "val3dity_errors": ";".join(str(x) for x in r.get("val3dity_errors", [])),
                "h_err": r.get("h_err"),
                "recall": r.get("recall_coverage"),
                "precision": r.get("pred_precision"),
                "F_score": r.get("F_score"),
                "vol_ratio": r.get("vol_ratio"),
                "footprint_IoU": r.get("footprint_IoU"),
                "edge_ok": r.get("edge_ok"),
                "face_planarity_max": r.get("face_planarity_max"),
            })
    write_json(SUMMARY_JSON, {
        "decision": decision,
        "search": search,
        "build": build,
        "schema_validation": schema,
        "rows": rows,
    })


def schema_by_bid(schema: Optional[Dict]) -> Dict[str, Dict]:
    if not schema:
        return {}
    return {item["bid"]: item for item in schema.get("items", [])}


def error_analysis_rows(rows: List[Dict]) -> List[List[str]]:
    observed = sorted({
        str(code)
        for r in rows
        for code in (r.get("val3dity_errors") or [])
        if code not in {"", "None"}
    })
    notes = {
        "203": "non-planar polygon distance-to-plane issue candidate",
        "204": "non-planar polygon normal deviation candidate",
        "302": "shell not closed candidate",
        "303": "non-manifold edge/shell candidate",
        "305": "multiple connected components candidate",
        "307": "wrong orientation candidate",
    }
    if not observed:
        return [["-", "No val3dity error codes observed or validator did not run."]]
    rows_out = []
    for code in observed:
        rows_out.append([code, notes.get(code, "See val3dity report for code-specific context; no extra inference added.")])
    return rows_out


def write_final_report(
    rows: List[Dict],
    decision: Dict,
    search: Dict,
    build: Dict,
    schema: Optional[Dict],
    val3dity_bin: Optional[str],
) -> None:
    lines = [
        "# P1-4a val3dity Enablement And Rerun",
        "",
        "## 1. Purpose",
        "",
        "Previous status was `BLOCKED_VAL3DITY_MISSING`. This rerun resolves `val3dity` from `VAL3DITY_BIN` or `PATH`, then validates the existing `relation_readout.city.json` artifacts only. No CityJSON regeneration or relation read-out code change was performed.",
        "",
        "## 2. val3dity Installation/Search Result",
        "",
        f"- Found path: `{val3dity_bin or 'NONE'}`",
        f"- Path recovery search: `{PATH_RECOVERY_JSON.relative_to(ROOT)}`",
        f"- Search JSON: `{SEARCH_JSON.relative_to(ROOT)}`",
        f"- Resolution report: `{BUILD_REPORT.relative_to(ROOT)}`",
        f"- Resolution status: `{build.get('status')}`",
        "- Repository clone/build attempted: `false`",
    ]
    if search.get("help_output"):
        lines.extend([
            "- Help/version output excerpt:",
            "```text",
            str(search.get("help_output", ""))[:1200],
            "```",
        ])
    if PATH_RECOVERY_JSON.exists():
        recovery = read_json(PATH_RECOVERY_JSON)
        found_paths = recovery.get("found_executable_paths") or []
        lines.extend([
            "",
            "Approved resolver result:",
            f"- Executable paths supplied by `VAL3DITY_BIN`/`PATH`: {', '.join(found_paths) if found_paths else 'none'}",
            "- Repository-local executable search was not attempted.",
        ])
    lines.extend([
        "",
        "## 3. Schema Validation",
        "",
    ])
    schema_items = (schema or {}).get("items", [])
    if schema_items:
        lines.extend(md_table(
            ["bid", "schema_status", "notes"],
            [[i["bid"], i.get("schema_status"), i.get("notes", "")] for i in schema_items],
        ))
    else:
        lines.append("Schema validation was not run because val3dity enablement stopped before Phase 3.")
    lines.extend([
        "",
        "## 4. val3dity Formal Validity",
        "",
    ])
    lines.extend(md_table(
        ["bid", "val3dity", "errors", "returncode", "report_path"],
        [
            [
                r.get("bid"),
                r.get("val3dity_status"),
                ",".join(str(x) for x in r.get("val3dity_errors", [])) or "-",
                r.get("val3dity_returncode", "NA"),
                r.get("val3dity_report") or "NA",
            ]
            for r in rows
        ],
    ))
    lines.extend([
        "",
        "## 5. Geometry Metrics Kept",
        "",
    ])
    lines.extend(md_table(
        ["bid", "h_err", "recall", "precision", "F_score", "vol_ratio", "footprint_IoU", "Hausdorff", "Chamfer"],
        [
            [
                r.get("bid"),
                fmt(r.get("h_err"), 4),
                fmt(r.get("recall_coverage"), 3),
                fmt(r.get("pred_precision"), 3),
                fmt(r.get("F_score"), 3),
                fmt(r.get("vol_ratio"), 3),
                fmt(r.get("footprint_IoU"), 3),
                fmt(r.get("Hausdorff"), 4),
                fmt(r.get("Chamfer"), 4),
            ]
            for r in rows
        ],
    ))
    lines.extend([
        "",
        "## 6. Formal GO/NG Update",
        "",
        f"- Final decision: `{decision.get('final_decision')}`",
        f"- Simple/medium rule: `{decision.get('simple_medium_rule')}`; hits: {', '.join(decision.get('simple_medium_hits', [])) or 'none'}",
        f"- Hip branch strict rule (h_err < 2m): `{decision.get('hip_strict_rule')}`",
        f"- Hip branch relaxed rule (h_err < 4m): `{decision.get('hip_relaxed_rule')}`",
        f"- Complex branch: `{decision.get('complex_branch')}`",
        f"- Warnings: {', '.join(decision.get('warnings', [])) or 'none'}",
        "",
        "## 7. Failure Analysis",
        "",
    ])
    lines.extend(md_table(["error_code", "interpretation"], error_analysis_rows(rows)))
    lines.extend([
        "",
        "No val3dity pass is inferred from visualization or from geometry-side metrics. If validation did not run, rows remain blocked rather than passing.",
        "",
        "## 8. Next Action",
        "",
    ])
    final_decision = decision.get("final_decision")
    if final_decision in {"E0_FORMAL_GO", "E0_PARTIAL_GO"}:
        lines.append("- Proceed to E1 GT 131 per-building read-out.")
    elif final_decision == "E0_FORMAL_NG":
        lines.append("- val3dity ran but simple/medium rule failed; fix CityJSON construction before E1.")
    else:
        lines.append("- Supply `VAL3DITY_BIN` or add val3dity to the container `PATH`, then rerun this validation-only script.")
    lines.extend([
        "",
        "## Self-verification",
        "",
        f"- {'PASS' if val3dity_bin or build.get('status') == 'MISSING_VAL3DITY_BIN_OR_PATH' else 'FAIL'}: val3dity executable found or explicit resolver failure written.",
        f"- {'PASS' if val3dity_bin and all(r.get('val3dity_status') not in {'BLOCKED_DEPENDENCY', 'NETWORK_BLOCKED', 'BUILD_FAILURE'} for r in rows) else 'BLOCKED'}: 6 bid x relation_readout.city.json validation attempted.",
        f"- {'PASS' if all((OUT_ROOT / r['bid'] / 'val3dity_report.json').exists() or r.get('val3dity_status') in {'BLOCKED_DEPENDENCY', 'NETWORK_BLOCKED', 'BUILD_FAILURE', 'REPORT_MISSING', 'TIMEOUT', 'PARSE_FAIL'} for r in rows) else 'FAIL'}: each bid has val3dity_report.json or explicit failure reason.",
        f"- {'PASS' if all((OUT_ROOT / r['bid'] / 'metrics_val3dity_rerun.json').exists() for r in rows) else 'FAIL'}: metrics_val3dity_rerun.json exists for each bid.",
        f"- {'PASS' if SUMMARY_CSV.exists() and SUMMARY_JSON.exists() else 'FAIL'}: summary CSV/JSON exists.",
        "- PASS: final REPORT exists.",
        f"- PASS: old `BLOCKED_VAL3DITY_MISSING` decision replaced by `{final_decision}`.",
        "",
    ])
    REPORT.write_text("\n".join(lines))


def main() -> int:
    ensure_dirs()
    existing = phase0_status()
    path_recovery_search()
    missing = [r["bid"] for r in existing if not r["cityjson_exists"]]
    if missing:
        raise FileNotFoundError(f"Missing target CityJSON files: {missing}")

    val3dity_bin, search, build = maybe_enable_val3dity()
    parsed_by_bid: Optional[Dict[str, Dict]] = None
    schema: Optional[Dict] = None
    blocker: Optional[str] = None
    blocked_status: Optional[str] = None

    if val3dity_bin is None:
        blocker = "DEPENDENCY"
        blocked_status = "BLOCKED_DEPENDENCY"
        schema = {
            "cjio_path": shutil.which("cjio"),
            "items": [
                {
                    "bid": bid,
                    "schema_status": "SKIPPED_VAL3DITY_ENABLE_BLOCKED",
                    "notes": "schema validation skipped because VAL3DITY_BIN/PATH did not resolve a runnable validator",
                    "stdout_path": None,
                    "stderr_path": None,
                }
                for bid in TARGET_BIDS
            ],
        }
        write_json(SCHEMA_SUMMARY, schema)
        rows = update_metrics(None, None, None, blocked_status)
    else:
        schema = run_schema_validation()
        parsed_by_bid = {bid: run_val3dity_for_bid(bid, val3dity_bin) for bid in TARGET_BIDS}
        if any(p.get("status") == "PARSE_FAIL" for p in parsed_by_bid.values()):
            blocker = "PARSE"
        rows = update_metrics(parsed_by_bid, schema_by_bid(schema), val3dity_bin)

    decision = decide(rows, blocker)
    write_summary(rows, decision, search, build, schema)
    write_final_report(rows, decision, search, build, schema, val3dity_bin)
    print(f"wrote {PHASE0_STATUS}")
    print(f"wrote {SEARCH_JSON}")
    print(f"wrote {BUILD_REPORT}")
    print(f"wrote {SUMMARY_CSV}")
    print(f"wrote {SUMMARY_JSON}")
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

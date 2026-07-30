"""P1-4a validator enablement and validation-only rerun.

This script does not regenerate CityJSON and does not change the relation
read-out algorithm. It only searches/builds val3dity, validates existing
relation_readout.city.json files, and updates validation-side reports.
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
CONFIGURE_LOG = ENABLE_DIR / "build_configure.log"
COMPILE_LOG = ENABLE_DIR / "build_compile.log"
SCHEMA_SUMMARY = ENABLE_DIR / "schema_validation_summary.json"
SUMMARY_CSV = ENABLE_DIR / "summary_val3dity_rerun.csv"
SUMMARY_JSON = ENABLE_DIR / "summary_val3dity_rerun.json"
PHASE0_STATUS = ENABLE_DIR / "phase0_existing_status.md"
PATH_RECOVERY_JSON = ENABLE_DIR / "path_recovery_search.json"

VAL3DITY_REPO = "https://github.com/tudelft3d/val3dity.git"
VAL3DITY_DOCS = "https://val3dity.readthedocs.io/main/install.html"
VAL3DITY_USAGE = "https://val3dity.readthedocs.io/main/usage.html"
APT_INSTALL_NOTE = (
    "sudo apt-get update\n"
    "sudo apt-get install -y cmake g++ git libcgal-dev libeigen3-dev "
    "libgeos++-dev libboost-filesystem-dev libboost-system-dev"
)


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


def run_text(cmd: List[str], timeout: int = 30) -> str:
    out = run_capture(cmd, timeout=timeout)
    text = (out.get("stdout") or "") + (out.get("stderr") or "")
    return text.strip()


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


def previous_checked_paths() -> List[Path]:
    out: List[Path] = []
    p = OUT_ROOT / "preflight_precision_metrics.json"
    if not p.exists():
        return out
    try:
        data = read_json(p)
    except Exception:
        return out
    for value in (data.get("val3dity_search") or {}).get("checked_paths", []) or []:
        out.append(Path(value))
    return out


def candidate_paths() -> List[Tuple[str, Path]]:
    items: List[Tuple[str, Path]] = []
    env_bin = os.environ.get("VAL3DITY_BIN")
    if env_bin:
        items.append(("VAL3DITY_BIN", Path(env_bin)))
    which = shutil.which("val3dity")
    if which:
        items.append(("PATH", Path(which)))
    for rel in [
        "bin/val3dity",
        "tools/val3dity",
        "external/val3dity/build/val3dity",
        "external/val3dity/build/app/val3dity",
        "external/val3dity/build/src/val3dity",
        "external/val3dity/val3dity",
    ]:
        items.append(("repo-local", ROOT / rel))
    for p in previous_checked_paths():
        items.append(("previous-preflight", p))
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
    commands = {
        "which_val3dity": ["bash", "-lc", "which val3dity || true"],
        "command_v_val3dity": ["bash", "-lc", "command -v val3dity || true"],
        "find_media_code_executable": [
            "bash", "-lc",
            "find /media/innopam/InnoPAM-8TB/hwiyoung/code -type f -name val3dity -perm -111 2>/dev/null | sed -n '1,200p'",
        ],
        "find_home_executable": [
            "bash", "-lc",
            "find /home/innopam -type f -name val3dity -perm -111 2>/dev/null | sed -n '1,200p'",
        ],
        "grep_val3dity_commands": [
            "bash", "-lc",
            "grep -R \"val3dity\" -n scripts src results 2>/dev/null | head -200",
        ],
    }
    results = {name: run_capture(cmd, timeout=300) for name, cmd in commands.items()}
    found = []
    for name in ["which_val3dity", "command_v_val3dity", "find_media_code_executable", "find_home_executable"]:
        for line in (results[name].get("stdout") or "").splitlines():
            path = line.strip()
            if path:
                found.append(path)
    payload = {
        "commands": results,
        "found_executable_paths": sorted(set(found)),
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


def dependency_check() -> Dict:
    commands = {
        "cmake": ["cmake", "--version"],
        "g++": ["g++", "--version"],
        "clang++": ["clang++", "--version"],
        "git": ["git", "--version"],
        "pkg-config": ["pkg-config", "--version"],
        "python3": ["python3", "--version"],
    }
    basic = {name: run_capture(cmd, timeout=30) for name, cmd in commands.items()}
    pkg_config = {}
    for pkg in ["geos", "geos++", "eigen3", "cgal"]:
        pkg_config[pkg] = run_capture(["pkg-config", "--modversion", pkg], timeout=30)
    system = {
        "ldconfig": run_capture(["bash", "-lc", "ldconfig -p 2>/dev/null | grep -Ei 'geos|cgal|boost_filesystem|boost_system' | sed -n '1,120p'"], timeout=30),
        "dpkg": run_capture(["bash", "-lc", "if command -v dpkg >/dev/null 2>&1; then dpkg -l | grep -Ei 'cgal|eigen3|geos|boost-filesystem|boost-system' | sed -n '1,160p'; fi"], timeout=30),
        "conda": run_capture(["bash", "-lc", "if command -v conda >/dev/null 2>&1; then conda list | grep -Ei 'cgal|eigen|geos|boost' | sed -n '1,160p'; fi"], timeout=60),
    }
    return {"basic": basic, "pkg_config": pkg_config, "system": system}


def source_state() -> Dict:
    src = ROOT / "external/val3dity"
    if not src.exists():
        return {"exists": False, "path": str(src)}
    return {
        "exists": True,
        "path": str(src),
        "git_status_short": run_text(["git", "-C", str(src), "status", "--short"], timeout=30),
        "git_rev_parse_HEAD": run_text(["git", "-C", str(src), "rev-parse", "HEAD"], timeout=30),
        "git_describe": run_text(["git", "-C", str(src), "describe", "--tags", "--always"], timeout=30),
    }


def clone_source_if_needed(build_info: Dict) -> Tuple[bool, str]:
    src = ROOT / "external/val3dity"
    if src.exists():
        build_info["source_state"] = source_state()
        return True, "source_exists"
    src.parent.mkdir(parents=True, exist_ok=True)
    clone = run_capture(["git", "clone", VAL3DITY_REPO, str(src)], timeout=300)
    build_info["git_clone"] = clone
    if clone.get("returncode") != 0:
        return False, "NETWORK_BLOCKED"
    build_info["source_state"] = source_state()
    return True, "cloned"


def find_built_val3dity(build_dir: Path) -> Optional[Path]:
    candidates = [
        build_dir / "val3dity",
        build_dir / "app/val3dity",
        build_dir / "src/val3dity",
    ]
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    found = []
    for path in build_dir.rglob("val3dity"):
        if path.is_file() and os.access(path, os.X_OK):
            found.append(path)
    return found[0] if found else None


def classify_build_failure(configure_text: str, compile_text: str, clone_status: str) -> str:
    text = f"{configure_text}\n{compile_text}".lower()
    if clone_status == "NETWORK_BLOCKED":
        return "NETWORK_BLOCKED"
    deps = ["cgal", "eigen", "geos", "boost", "could not find", "not found", "missing"]
    if any(token in text for token in deps):
        return "BLOCKED_DEPENDENCY"
    return "BUILD_FAILURE"


def build_val3dity() -> Dict:
    build_info: Dict = {
        "attempted": True,
        "dependency_check": dependency_check(),
        "network_check": run_capture(["git", "ls-remote", VAL3DITY_REPO, "HEAD"], timeout=60),
        "source_state_before": source_state(),
    }
    source_ok, clone_status = clone_source_if_needed(build_info)
    build_info["source_prepare_status"] = clone_status
    if not source_ok:
        build_info["status"] = clone_status
        write_build_report(build_info)
        return build_info

    src = ROOT / "external/val3dity"
    build_dir = src / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    COMPILE_LOG.write_text("")
    configure = run_capture(["cmake", "..", "-DCMAKE_BUILD_TYPE=Release"], cwd=build_dir, timeout=300)
    CONFIGURE_LOG.write_text((configure.get("stdout") or "") + (configure.get("stderr") or ""))
    build_info["configure"] = {
        "command": configure["command"],
        "cwd": configure["cwd"],
        "returncode": configure["returncode"],
        "timeout": configure["timeout"],
    }
    if configure.get("returncode") != 0:
        build_info["status"] = classify_build_failure(CONFIGURE_LOG.read_text(), "", clone_status)
        write_build_report(build_info)
        return build_info

    jobs = str(max(1, os.cpu_count() or 1))
    compile_run = run_capture(["cmake", "--build", ".", f"-j{jobs}"], cwd=build_dir, timeout=1200)
    COMPILE_LOG.write_text((compile_run.get("stdout") or "") + (compile_run.get("stderr") or ""))
    build_info["compile"] = {
        "command": compile_run["command"],
        "cwd": compile_run["cwd"],
        "returncode": compile_run["returncode"],
        "timeout": compile_run["timeout"],
    }
    if compile_run.get("returncode") != 0:
        build_info["status"] = classify_build_failure(CONFIGURE_LOG.read_text(), COMPILE_LOG.read_text(), clone_status)
        write_build_report(build_info)
        return build_info

    built = find_built_val3dity(build_dir)
    if built is None:
        build_info["status"] = "BUILD_FAILURE"
        build_info["error"] = "build finished but no executable named val3dity was found"
        write_build_report(build_info)
        return build_info

    bin_dir = ROOT / "bin"
    bin_dir.mkdir(exist_ok=True)
    link_path = bin_dir / "val3dity"
    try:
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()
        link_path.symlink_to(built.resolve())
        link_mode = "symlink"
    except OSError:
        shutil.copy2(built, link_path)
        link_mode = "copy"
    verify = verify_val3dity(link_path)
    build_info.update({
        "status": "BUILT",
        "built_val3dity_path": str(built),
        "repo_bin_path": str(link_path),
        "link_mode": link_mode,
        "build_verification": verify,
    })
    write_build_report(build_info)
    return build_info


def build_dependency_notes(dep: Dict) -> List[str]:
    lines = []
    for name, result in dep.get("basic", {}).items():
        status = "OK" if result.get("returncode") == 0 else "MISSING"
        first = ((result.get("stdout") or "") + (result.get("stderr") or "")).splitlines()
        lines.append(f"- `{name}`: {status}" + (f" - `{first[0]}`" if first else ""))
    lines.append("")
    lines.append("Library probes:")
    for name, result in dep.get("pkg_config", {}).items():
        status = "OK" if result.get("returncode") == 0 else "NOT_FOUND_BY_PKG_CONFIG"
        text = ((result.get("stdout") or "") + (result.get("stderr") or "")).splitlines()
        lines.append(f"- `{name}`: {status}" + (f" - `{text[0]}`" if text else ""))
    return lines


def write_build_report(build_info: Dict) -> None:
    status = build_info.get("status", "UNKNOWN")
    lines = [
        "# val3dity Build Report",
        "",
        f"- Source repo: `{VAL3DITY_REPO}`",
        f"- Source path: `{ROOT / 'external/val3dity'}`",
        f"- Build status: `{status}`",
        "",
        "## Dependency Check",
        "",
    ]
    lines.extend(build_dependency_notes(build_info.get("dependency_check", {})))
    lines.extend([
        "",
        "## Network Check",
        "",
        f"- `git ls-remote` returncode: `{(build_info.get('network_check') or {}).get('returncode')}`",
        "",
        "## Source State",
        "",
        "Before:",
        "```json",
        json.dumps(build_info.get("source_state_before", {}), indent=2),
        "```",
        "",
        "After/source prepare:",
        "```json",
        json.dumps(build_info.get("source_state", build_info.get("git_clone", {})), indent=2),
        "```",
        "",
        "## Configure And Build",
        "",
        f"- Configure log: `{CONFIGURE_LOG.relative_to(ROOT)}`",
        f"- Compile log: `{COMPILE_LOG.relative_to(ROOT)}`",
    ])
    if status != "BUILT":
        configure_excerpt = CONFIGURE_LOG.read_text(errors="replace")[-2000:] if CONFIGURE_LOG.exists() else ""
        compile_excerpt = COMPILE_LOG.read_text(errors="replace")[-2000:] if COMPILE_LOG.exists() else ""
        lines.extend([
            "",
            "## Failure Excerpt",
            "",
            "```text",
            (configure_excerpt or compile_excerpt or "No configure/build log content was captured.").strip(),
            "```",
            "",
            "## Recommended Install Commands",
            "",
            "Do not run these automatically here; they require user/admin approval if system packages are needed.",
            "",
            "```bash",
            APT_INSTALL_NOTE,
            "```",
            "",
            f"Official install docs: {VAL3DITY_DOCS}",
        ])
    else:
        lines.extend([
            "",
            "## Binary",
            "",
            f"- Built path: `{build_info.get('built_val3dity_path')}`",
            f"- Repo-local path: `{build_info.get('repo_bin_path')}`",
            f"- Link mode: `{build_info.get('link_mode')}`",
        ])
    BUILD_REPORT.write_text("\n".join(lines) + "\n")


def maybe_enable_val3dity() -> Tuple[Optional[str], Dict, Dict]:
    search = search_val3dity()
    if search.get("found"):
        return search["path"], search, {"attempted": False, "status": "NOT_NEEDED"}
    build_info = build_val3dity()
    search_after = search_val3dity()
    if search_after.get("found"):
        return search_after["path"], search_after, build_info
    return None, search_after, build_info


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
                "failure_reason": "val3dity executable was not available; source build did not complete.",
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
        "Previous status was `BLOCKED_VAL3DITY_MISSING`. This rerun searches for or builds `val3dity`, then validates the existing `relation_readout.city.json` artifacts only. No CityJSON regeneration or relation read-out code change was performed.",
        "",
        "## 2. val3dity Installation/Search Result",
        "",
        f"- Found path: `{val3dity_bin or 'NONE'}`",
        f"- Path recovery search: `{PATH_RECOVERY_JSON.relative_to(ROOT)}`",
        f"- Search JSON: `{SEARCH_JSON.relative_to(ROOT)}`",
        f"- Build report: `{BUILD_REPORT.relative_to(ROOT)}`",
        f"- Build status: `{build.get('status')}`",
    ]
    if search.get("help_output"):
        lines.extend([
            "- Help/version output excerpt:",
            "```text",
            str(search.get("help_output", ""))[:1200],
            "```",
        ])
    if build.get("status") not in {"BUILT", "NOT_NEEDED"}:
        lines.extend([
            "",
            "Build did not produce a runnable validator. Configure/build logs are preserved:",
            f"- `{CONFIGURE_LOG.relative_to(ROOT)}`",
            f"- `{COMPILE_LOG.relative_to(ROOT)}`",
            "",
            "Recommended dependency install note, not executed automatically:",
            "```bash",
            APT_INSTALL_NOTE,
            "```",
        ])
    if PATH_RECOVERY_JSON.exists():
        recovery = read_json(PATH_RECOVERY_JSON)
        found_paths = recovery.get("found_executable_paths") or []
        grep_lines = ((recovery.get("commands", {}).get("grep_val3dity_commands", {}) or {}).get("stdout") or "").splitlines()
        lines.extend([
            "",
            "Path recovery result:",
            f"- Executable paths found by requested broad search: {', '.join(found_paths) if found_paths else 'none'}",
            f"- `grep -R \"val3dity\" -n scripts src results | head -200` matched {len(grep_lines)} lines; scripts call `val3dity` by command name, but no local executable path was recovered.",
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
        lines.append("- Resolve validator build/install blocker first, then rerun this validation-only script.")
    lines.extend([
        "",
        "## Self-verification",
        "",
        f"- {'PASS' if val3dity_bin or build.get('status') not in {'BUILT', 'NOT_NEEDED'} else 'FAIL'}: val3dity executable found or build failure reason written.",
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
        status = build.get("status") or "BLOCKED_DEPENDENCY"
        blocker = "DEPENDENCY"
        blocked_status = status if status in {"NETWORK_BLOCKED", "BUILD_FAILURE"} else "BLOCKED_DEPENDENCY"
        schema = {
            "cjio_path": shutil.which("cjio"),
            "items": [
                {
                    "bid": bid,
                    "schema_status": "SKIPPED_VAL3DITY_ENABLE_BLOCKED",
                    "notes": "schema validation skipped because val3dity enablement stopped at source build/dependency phase",
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

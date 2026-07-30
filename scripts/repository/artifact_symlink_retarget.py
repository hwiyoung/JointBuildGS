#!/usr/bin/env python3
"""Plan, apply, and verify fail-closed artifact symlink retargeting.

Only symlink inodes are replaced. Regular files and directories are never
created, removed, moved, or modified by this command. Targets that cannot be
proven to exist under ``JBGS_ARTIFACT_ROOT`` remain unresolved and unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
DEFAULT_PLAN = REPO / "artifacts/manifests/artifact_symlink_retarget_plan_20260730.json"
DEFAULT_RECEIPT = REPO / "artifacts/manifests/artifact_symlink_retarget_receipt_20260730.json"
P0_ROOT = Path("phase-payloads/p0-audit/data")
P0_RETENTION_EVIDENCE = "artifacts/manifests/local_artifact_retention_pass2_plan_20260730.json"
PLAN_SCHEMA = "jointbuildgs.artifact-symlink-retarget-plan.v1"
RECEIPT_SCHEMA = "jointbuildgs.artifact-symlink-retarget-receipt.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true", help="write an immutable retarget plan")
    mode.add_argument("--apply", action="store_true", help="apply exactly the recorded plan")
    mode.add_argument("--verify", action="store_true", help="verify the plan and receipt")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(os.environ["JBGS_ARTIFACT_ROOT"]) if "JBGS_ARTIFACT_ROOT" in os.environ else None,
    )
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest_payload(value: dict[str, Any], field: str) -> str:
    payload = {key: item for key, item in value.items() if key != field}
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def write_new(path: Path, value: dict[str, Any]) -> None:
    if not path.parent.is_dir():
        raise RuntimeError(f"output directory does not exist: {path.parent}")
    try:
        with path.open("xb") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode())
            stream.write(b"\n")
    except FileExistsError as error:
        raise RuntimeError(f"refusing to overwrite immutable file: {path}") from error


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def checked_root(value: Path | None) -> Path:
    if value is None:
        raise RuntimeError("set JBGS_ARTIFACT_ROOT or pass --artifact-root")
    root = value.resolve(strict=True)
    if not root.is_dir():
        raise RuntimeError(f"artifact root is not a directory: {root}")
    return root


def artifact_rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def target_proof(root: Path, target: Path) -> dict[str, Any]:
    info = target.stat()
    if target.is_dir():
        kind = "directory"
    elif target.is_file():
        kind = "regular_file"
    else:
        raise RuntimeError(f"unsupported retained target type: {target}")
    return {
        "artifact_relative_path": artifact_rel(root, target),
        "kind": kind,
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
        "device": info.st_dev,
        "inode": info.st_ino,
    }


def regular_file_snapshot(root: Path) -> dict[str, Any]:
    """Fingerprint regular-file metadata without following any symlink."""
    logical_files = 0
    logical_bytes = 0
    unique: dict[tuple[int, int], int] = {}
    digest = hashlib.sha256()
    stack = [root]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                mode = info.st_mode
                path = Path(entry.path)
                if stat.S_ISDIR(mode):
                    stack.append(path)
                elif stat.S_ISREG(mode):
                    relative = artifact_rel(root, path)
                    logical_files += 1
                    logical_bytes += info.st_size
                    unique.setdefault((info.st_dev, info.st_ino), info.st_size)
                    record = (
                        f"{relative}\0{mode}\0{info.st_size}\0{info.st_mtime_ns}"
                        f"\0{info.st_dev}\0{info.st_ino}\n"
                    )
                    digest.update(record.encode("utf-8", errors="surrogateescape"))
    return {
        "logical_regular_files": logical_files,
        "logical_regular_file_bytes": logical_bytes,
        "unique_regular_files": len(unique),
        "unique_regular_file_bytes": sum(unique.values()),
        "metadata_sha256": digest.hexdigest(),
    }


def broken_symlinks(root: Path) -> list[Path]:
    result: list[Path] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    stack.append(path)
                elif stat.S_ISLNK(info.st_mode) and not path.exists():
                    result.append(path)
    return sorted(result, key=lambda path: artifact_rel(root, path))


def classify(root: Path, link: Path) -> dict[str, Any]:
    relative = artifact_rel(root, link)
    old_target = os.readlink(link)
    candidate: Path | None = None
    rule: str
    evidence: str

    marker = "p0-audit/data/"
    if marker in old_target:
        suffix = old_target.split(marker, 1)[1]
        candidate = root / P0_ROOT / suffix
        rule = "phase_payload_p0_data_relocation"
        evidence = P0_RETENTION_EVIDENCE
    elif relative == "results/tum_transfer/data_geoidfix/images" and old_target == "../data/images":
        candidate = root / P0_ROOT / "work/mvs/colmap_dense/images"
        rule = "replace_broken_chain_with_retained_p0_images"
        evidence = P0_RETENTION_EVIDENCE
    elif old_target.startswith(
        "/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS/results/"
    ):
        suffix = old_target.split("/JointBuildGS/results/", 1)[1]
        candidate = root / "results" / suffix
        rule = "repo_results_to_sibling_artifact_results"
        evidence = "sibling artifact root contract and retained target stat"
    elif "/PlanarSplatting/" in old_target:
        rule = "unresolved_external_planarsplatting_target"
        evidence = "no same-name retained target found under sibling artifact root"
    else:
        rule = "unclassified_broken_symlink"
        evidence = "no safe mapping rule"

    entry: dict[str, Any] = {
        "link_path": relative,
        "old_target": old_target,
        "old_target_is_absolute": os.path.isabs(old_target),
        "old_lexical_resolution": os.path.normpath(str(link.parent / old_target)),
        "mapping_rule": rule,
        "evidence": evidence,
    }
    if candidate is None or not candidate.exists():
        entry.update({"action": "leave_unresolved", "unresolved_reason": evidence})
        if candidate is not None:
            entry["missing_candidate"] = artifact_rel(root, candidate)
        return entry

    candidate = candidate.resolve(strict=True)
    candidate.relative_to(root)
    entry.update(
        {
            "action": "retarget_symlink",
            "new_target": os.path.relpath(candidate, start=link.parent),
            "retained_target": target_proof(root, candidate),
        }
    )
    return entry


def prepare(root: Path, plan_path: Path) -> None:
    links = broken_symlinks(root)
    entries = [classify(root, link) for link in links]
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["action"]] = counts.get(entry["action"], 0) + 1
    plan: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "created_at_utc": utc_now(),
        "artifact_root": str(root),
        "contract": {
            "mutation_scope": "symlink inode replacement only",
            "regular_files_directories_and_payload_bytes": "must remain unchanged",
            "unproven_targets": "must remain unresolved and unchanged",
        },
        "before_broken_symlink_count": len(links),
        "action_counts": counts,
        "before_regular_file_snapshot": regular_file_snapshot(root),
        "entries": entries,
    }
    plan["plan_sha256"] = digest_payload(plan, "plan_sha256")
    write_new(plan_path, plan)
    print(json.dumps({"plan": str(plan_path), "plan_sha256": plan["plan_sha256"], **counts}, indent=2))


def validate_plan(root: Path, plan: dict[str, Any]) -> None:
    if plan.get("schema") != PLAN_SCHEMA:
        raise RuntimeError("unsupported plan schema")
    if plan.get("plan_sha256") != digest_payload(plan, "plan_sha256"):
        raise RuntimeError("plan digest mismatch")
    if Path(plan.get("artifact_root", "")).resolve(strict=True) != root:
        raise RuntimeError("artifact root differs from immutable plan")
    if not isinstance(plan.get("entries"), list):
        raise RuntimeError("plan entries are missing")


def validate_preconditions(root: Path, plan: dict[str, Any]) -> None:
    current_broken = broken_symlinks(root)
    if len(current_broken) != plan["before_broken_symlink_count"]:
        raise RuntimeError("broken symlink inventory changed after planning")
    if regular_file_snapshot(root) != plan["before_regular_file_snapshot"]:
        raise RuntimeError("regular-file inventory changed after planning")
    expected_links = {entry["link_path"] for entry in plan["entries"]}
    if expected_links != {artifact_rel(root, path) for path in current_broken}:
        raise RuntimeError("broken symlink path set changed after planning")

    for entry in plan["entries"]:
        link = root / entry["link_path"]
        if not link.is_symlink() or os.readlink(link) != entry["old_target"]:
            raise RuntimeError(f"symlink changed after planning: {link}")
        if entry["action"] == "retarget_symlink":
            target = root / entry["retained_target"]["artifact_relative_path"]
            if not target.exists() or target_proof(root, target.resolve(strict=True)) != entry["retained_target"]:
                raise RuntimeError(f"retained target changed after planning: {target}")
            computed = os.path.relpath(target.resolve(strict=True), start=link.parent)
            if computed != entry["new_target"]:
                raise RuntimeError(f"recorded relative target is inconsistent: {link}")
        elif entry["action"] != "leave_unresolved":
            raise RuntimeError(f"unsupported plan action: {entry['action']}")


def replace_symlink(link: Path, new_target: str) -> None:
    temporary = link.with_name(f".{link.name}.jbgs-retarget-{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeError(f"temporary path already exists: {temporary}")
    os.symlink(new_target, temporary)
    try:
        os.replace(temporary, link)
    finally:
        if temporary.is_symlink():
            temporary.unlink()


def apply(root: Path, plan_path: Path, receipt_path: Path) -> None:
    plan = read_json(plan_path)
    validate_plan(root, plan)
    validate_preconditions(root, plan)
    before = regular_file_snapshot(root)
    applied: list[dict[str, Any]] = []
    rollback: list[tuple[Path, str]] = []
    try:
        for entry in plan["entries"]:
            if entry["action"] != "retarget_symlink":
                continue
            link = root / entry["link_path"]
            replace_symlink(link, entry["new_target"])
            rollback.append((link, entry["old_target"]))
            applied.append(
                {
                    "link_path": entry["link_path"],
                    "old_target": entry["old_target"],
                    "new_target": entry["new_target"],
                    "retained_target": entry["retained_target"]["artifact_relative_path"],
                }
            )
    except Exception:
        for link, old_target in reversed(rollback):
            replace_symlink(link, old_target)
        raise

    after = regular_file_snapshot(root)
    if after != before:
        for link, old_target in reversed(rollback):
            replace_symlink(link, old_target)
        raise RuntimeError("regular-file inventory changed; symlink retargeting rolled back")

    unresolved = [entry for entry in plan["entries"] if entry["action"] == "leave_unresolved"]
    after_broken = broken_symlinks(root)
    if {artifact_rel(root, path) for path in after_broken} != {entry["link_path"] for entry in unresolved}:
        for link, old_target in reversed(rollback):
            replace_symlink(link, old_target)
        raise RuntimeError("post-apply broken symlink set differs from planned unresolved set")

    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "created_at_utc": utc_now(),
        "artifact_root": str(root),
        "plan_path": str(plan_path.relative_to(REPO)) if plan_path.is_relative_to(REPO) else str(plan_path),
        "plan_sha256": plan["plan_sha256"],
        "applied_count": len(applied),
        "unresolved_count": len(unresolved),
        "after_broken_symlink_count": len(after_broken),
        "regular_file_snapshot_before": before,
        "regular_file_snapshot_after": after,
        "regular_file_snapshot_unchanged": after == before,
        "applied": applied,
        "unresolved": [
            {
                "link_path": entry["link_path"],
                "unchanged_target": entry["old_target"],
                "reason": entry["unresolved_reason"],
            }
            for entry in unresolved
        ],
    }
    receipt["receipt_sha256"] = digest_payload(receipt, "receipt_sha256")
    write_new(receipt_path, receipt)
    print(
        json.dumps(
            {
                "receipt": str(receipt_path),
                "receipt_sha256": receipt["receipt_sha256"],
                "applied": len(applied),
                "unresolved": len(unresolved),
                "regular_file_snapshot_unchanged": True,
            },
            indent=2,
        )
    )


def verify(root: Path, plan_path: Path, receipt_path: Path) -> None:
    plan = read_json(plan_path)
    receipt = read_json(receipt_path)
    validate_plan(root, plan)
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise RuntimeError("unsupported receipt schema")
    if receipt.get("receipt_sha256") != digest_payload(receipt, "receipt_sha256"):
        raise RuntimeError("receipt digest mismatch")
    if receipt.get("plan_sha256") != plan["plan_sha256"]:
        raise RuntimeError("receipt does not reference this plan")

    repaired = 0
    unresolved = 0
    cleaned_later: list[dict[str, Any]] = []
    for entry in plan["entries"]:
        link = root / entry["link_path"]
        if entry["action"] == "leave_unresolved" and not link.exists() and not link.is_symlink():
            cleaned_later.append(entry)
            continue
        if not link.is_symlink():
            raise RuntimeError(f"planned link is no longer a symlink: {link}")
        if entry["action"] == "retarget_symlink":
            repaired += 1
            if os.readlink(link) != entry["new_target"]:
                raise RuntimeError(f"retargeted link text differs from plan: {link}")
            expected = root / entry["retained_target"]["artifact_relative_path"]
            if link.resolve(strict=True) != expected.resolve(strict=True):
                raise RuntimeError(f"retargeted link resolves to wrong target: {link}")
        else:
            unresolved += 1
            if os.readlink(link) != entry["old_target"] or link.exists():
                raise RuntimeError(f"unresolved link was unexpectedly changed: {link}")

    if cleaned_later:
        cleanup_plan_path = REPO / "artifacts/manifests/artifact_stale_symlink_cleanup_plan_20260730.json"
        cleanup_receipt_path = REPO / "artifacts/manifests/artifact_stale_symlink_cleanup_receipt_20260730.json"
        cleanup_plan = read_json(cleanup_plan_path)
        cleanup_receipt = read_json(cleanup_receipt_path)
        if cleanup_plan.get("plan_sha256") != digest_payload(cleanup_plan, "plan_sha256"):
            raise RuntimeError("downstream stale-link cleanup plan digest mismatch")
        if cleanup_receipt.get("receipt_sha256") != digest_payload(cleanup_receipt, "receipt_sha256"):
            raise RuntimeError("downstream stale-link cleanup receipt digest mismatch")
        if cleanup_receipt.get("plan_sha256") != cleanup_plan["plan_sha256"]:
            raise RuntimeError("downstream stale-link cleanup receipt/plan mismatch")
        cleaned_paths = {entry["link_path"] for entry in cleaned_later}
        cleanup_targets = {
            entry["link_path"]: entry["old_target"] for entry in cleanup_plan.get("entries", [])
        }
        if cleaned_paths != set(cleanup_receipt.get("deleted_symlinks", [])):
            raise RuntimeError("downstream cleanup receipt does not cover missing unresolved links")
        for entry in cleaned_later:
            if cleanup_targets.get(entry["link_path"]) != entry["old_target"]:
                raise RuntimeError("downstream cleanup plan target differs from retarget plan")

    current_snapshot = regular_file_snapshot(root)
    if current_snapshot != receipt["regular_file_snapshot_after"]:
        raise RuntimeError("regular-file inventory differs from apply receipt")
    current_broken = broken_symlinks(root)
    if len(current_broken) != unresolved:
        raise RuntimeError("current broken symlink count differs from unresolved count")
    print(
        json.dumps(
            {
                "status": "verified",
                "repaired_symlinks": repaired,
                "unresolved_symlinks": unresolved,
                "cleaned_stale_symlinks": len(cleaned_later),
                "regular_file_snapshot_matches_receipt": True,
                "unique_regular_file_bytes": current_snapshot["unique_regular_file_bytes"],
            },
            indent=2,
        )
    )


def main() -> int:
    args = parse_args()
    try:
        root = checked_root(args.artifact_root)
        if args.prepare:
            prepare(root, args.plan)
        elif args.apply:
            apply(root, args.plan, args.receipt)
        else:
            verify(root, args.plan, args.receipt)
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

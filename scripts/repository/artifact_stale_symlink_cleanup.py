#!/usr/bin/env python3
"""Remove the exact, reviewed Seongsu stale-link set and its empty directory."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from artifact_symlink_retarget import (
    REPO,
    artifact_rel,
    broken_symlinks,
    checked_root,
    digest_payload,
    read_json,
    regular_file_snapshot,
    write_new,
)


PLAN_SCHEMA = "jointbuildgs.artifact-stale-symlink-cleanup-plan.v1"
RECEIPT_SCHEMA = "jointbuildgs.artifact-stale-symlink-cleanup-receipt.v1"
DEFAULT_PLAN = REPO / "artifacts/manifests/artifact_stale_symlink_cleanup_plan_20260730.json"
DEFAULT_RECEIPT = REPO / "artifacts/manifests/artifact_stale_symlink_cleanup_receipt_20260730.json"
EMPTY_DIRECTORY = "data/seongsu"
EXPECTED_LINKS = {
    "data/seongsu/colmap_runs": (
        "/media/innopam/InnoPAM-8TB/hwiyoung/code/PlanarSplatting/"
        "planarSplat_ExpRes/seongsu_phase0/seongsu_colmap_example"
    ),
    "data/seongsu/colmap_sparse.ply": (
        "/media/innopam/InnoPAM-8TB/hwiyoung/code/PlanarSplatting/"
        "planarSplat_ExpRes/seongsu_phase0/colmap_sparse.ply"
    ),
    "data/seongsu/input_data.pth": (
        "/media/innopam/InnoPAM-8TB/hwiyoung/code/PlanarSplatting/"
        "planarSplat_ExpRes/seongsu_phase0/input_data.pth"
    ),
}
REFERENCE_SCAN_EXCLUSIONS = {
    "scripts/repository/artifact_stale_symlink_cleanup.py",
    "artifacts/manifests/artifact_symlink_retarget_plan_20260730.json",
    "artifacts/manifests/artifact_symlink_retarget_receipt_20260730.json",
    "artifacts/manifests/artifact_stale_symlink_cleanup_plan_20260730.json",
    "artifacts/manifests/artifact_stale_symlink_cleanup_receipt_20260730.json",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
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


def active_repo_references() -> list[dict[str, str]]:
    listed = subprocess.check_output(
        (
            "git",
            "-c",
            f"safe.directory={REPO}",
            "ls-files",
            "-co",
            "--exclude-standard",
            "-z",
        ),
        cwd=REPO,
    ).split(b"\0")
    needles = tuple(EXPECTED_LINKS) + tuple(EXPECTED_LINKS.values())
    suffixes = {".csv", ".json", ".jsonl", ".md", ".py", ".sh", ".toml", ".txt", ".yaml", ".yml"}
    matches: list[dict[str, str]] = []
    for encoded in listed:
        if not encoded:
            continue
        relative = os.fsdecode(encoded)
        if relative in REFERENCE_SCAN_EXCLUSIONS:
            continue
        path = REPO / relative
        if not path.is_file() or path.suffix.lower() not in suffixes or path.stat().st_size > 16 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for needle in needles:
            if needle in text:
                matches.append({"path": relative, "matched_text": needle})
    return matches


def link_entries(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for relative, expected_target in sorted(EXPECTED_LINKS.items()):
        link = root / relative
        if not link.is_symlink() or link.exists():
            raise RuntimeError(f"expected a broken symlink: {link}")
        actual_target = os.readlink(link)
        if actual_target != expected_target:
            raise RuntimeError(f"stale link target differs from reviewed target: {link}")
        info = link.lstat()
        entries.append(
            {
                "link_path": relative,
                "old_target": actual_target,
                "old_uid": info.st_uid,
                "old_gid": info.st_gid,
                "action": "delete_stale_symlink",
                "reason": "unreferenced broken pointer to unavailable external PlanarSplatting output",
            }
        )
    return entries


def validate_directory_contents(root: Path) -> None:
    directory = root / EMPTY_DIRECTORY
    if not directory.is_dir() or directory.is_symlink():
        raise RuntimeError(f"expected ordinary directory: {directory}")
    actual = {artifact_rel(root, path) for path in directory.iterdir()}
    if actual != set(EXPECTED_LINKS):
        raise RuntimeError("Seongsu directory contains content outside the reviewed stale-link set")


def prepare(root: Path, plan_path: Path) -> None:
    validate_directory_contents(root)
    current_broken = {artifact_rel(root, path) for path in broken_symlinks(root)}
    if current_broken != set(EXPECTED_LINKS):
        raise RuntimeError("artifact broken-link set differs from the reviewed three-link set")
    references = active_repo_references()
    if references:
        raise RuntimeError(f"operational repository references still exist: {references[:5]}")
    plan: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "created_at_utc": utc_now(),
        "artifact_root": str(root),
        "contract": {
            "deletion_scope": "exactly three reviewed broken symlinks",
            "empty_directory_cleanup": EMPTY_DIRECTORY,
            "regular_files_and_payload_bytes": "must remain unchanged",
        },
        "before_broken_symlink_count": len(current_broken),
        "before_regular_file_snapshot": regular_file_snapshot(root),
        "repository_reference_scan": {
            "active_reference_matches": 0,
            "excluded_audit_or_cleanup_files": sorted(REFERENCE_SCAN_EXCLUSIONS),
        },
        "entries": link_entries(root),
        "remove_empty_directories": [EMPTY_DIRECTORY],
    }
    plan["plan_sha256"] = digest_payload(plan, "plan_sha256")
    write_new(plan_path, plan)
    print(json.dumps({"plan": str(plan_path), "plan_sha256": plan["plan_sha256"], "delete_links": 3}, indent=2))


def validate_plan(root: Path, plan: dict[str, Any]) -> None:
    if plan.get("schema") != PLAN_SCHEMA:
        raise RuntimeError("unsupported cleanup plan schema")
    if plan.get("plan_sha256") != digest_payload(plan, "plan_sha256"):
        raise RuntimeError("cleanup plan digest mismatch")
    if Path(plan.get("artifact_root", "")).resolve(strict=True) != root:
        raise RuntimeError("artifact root differs from immutable cleanup plan")
    recorded = {entry["link_path"]: entry["old_target"] for entry in plan.get("entries", [])}
    if recorded != EXPECTED_LINKS:
        raise RuntimeError("cleanup plan target set differs from exact allowlist")
    if plan.get("remove_empty_directories") != [EMPTY_DIRECTORY]:
        raise RuntimeError("cleanup plan empty-directory target differs from allowlist")


def validate_preconditions(root: Path, plan: dict[str, Any]) -> None:
    validate_directory_contents(root)
    if regular_file_snapshot(root) != plan["before_regular_file_snapshot"]:
        raise RuntimeError("regular-file inventory changed after cleanup planning")
    if {artifact_rel(root, path) for path in broken_symlinks(root)} != set(EXPECTED_LINKS):
        raise RuntimeError("broken-link inventory changed after cleanup planning")
    if active_repo_references():
        raise RuntimeError("operational repository references appeared after cleanup planning")
    entries = {entry["link_path"]: entry for entry in plan["entries"]}
    for relative, old_target in EXPECTED_LINKS.items():
        link = root / relative
        entry = entries[relative]
        if not link.is_symlink() or link.exists() or os.readlink(link) != old_target:
            raise RuntimeError(f"stale link changed after cleanup planning: {link}")
        info = link.lstat()
        if (info.st_uid, info.st_gid) != (entry["old_uid"], entry["old_gid"]):
            raise RuntimeError(f"stale link ownership changed after cleanup planning: {link}")


def restore_link(link: Path, target: str, uid: int, gid: int) -> None:
    os.symlink(target, link)
    os.chown(link, uid, gid, follow_symlinks=False)


def apply(root: Path, plan_path: Path, receipt_path: Path) -> None:
    if receipt_path.exists() or receipt_path.is_symlink():
        raise RuntimeError(f"refusing to overwrite immutable file: {receipt_path}")
    plan = read_json(plan_path)
    validate_plan(root, plan)
    validate_preconditions(root, plan)
    before = regular_file_snapshot(root)
    removed: list[dict[str, Any]] = []
    directory = root / EMPTY_DIRECTORY
    entries = {entry["link_path"]: entry for entry in plan["entries"]}
    try:
        for relative in sorted(EXPECTED_LINKS):
            entry = entries[relative]
            link = root / relative
            link.unlink()
            removed.append(entry)
        directory.rmdir()
    except Exception:
        directory.mkdir(exist_ok=True)
        for entry in removed:
            link = root / entry["link_path"]
            if not link.exists() and not link.is_symlink():
                restore_link(link, entry["old_target"], entry["old_uid"], entry["old_gid"])
        raise

    after = regular_file_snapshot(root)
    if after != before:
        directory.mkdir(exist_ok=True)
        for entry in removed:
            restore_link(
                root / entry["link_path"],
                entry["old_target"],
                entry["old_uid"],
                entry["old_gid"],
            )
        raise RuntimeError("regular-file inventory changed; stale-link cleanup rolled back")
    after_broken = broken_symlinks(root)
    if after_broken:
        raise RuntimeError("broken symlinks remain after exact stale-link cleanup")

    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "created_at_utc": utc_now(),
        "artifact_root": str(root),
        "plan_path": str(plan_path.relative_to(REPO)) if plan_path.is_relative_to(REPO) else str(plan_path),
        "plan_sha256": plan["plan_sha256"],
        "deleted_symlinks": [entry["link_path"] for entry in removed],
        "deleted_symlink_count": len(removed),
        "removed_empty_directories": [EMPTY_DIRECTORY],
        "after_broken_symlink_count": 0,
        "regular_file_snapshot_before": before,
        "regular_file_snapshot_after": after,
        "regular_file_snapshot_unchanged": after == before,
    }
    receipt["receipt_sha256"] = digest_payload(receipt, "receipt_sha256")
    write_new(receipt_path, receipt)
    print(
        json.dumps(
            {
                "receipt": str(receipt_path),
                "receipt_sha256": receipt["receipt_sha256"],
                "deleted_symlinks": len(removed),
                "removed_empty_directories": 1,
                "broken_symlinks_after": 0,
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
        raise RuntimeError("unsupported cleanup receipt schema")
    if receipt.get("receipt_sha256") != digest_payload(receipt, "receipt_sha256"):
        raise RuntimeError("cleanup receipt digest mismatch")
    if receipt.get("plan_sha256") != plan["plan_sha256"]:
        raise RuntimeError("cleanup receipt does not reference this plan")
    for relative in EXPECTED_LINKS:
        path = root / relative
        if path.exists() or path.is_symlink():
            raise RuntimeError(f"reviewed stale link still exists: {path}")
    if (root / EMPTY_DIRECTORY).exists():
        raise RuntimeError("reviewed empty Seongsu directory still exists")
    if broken_symlinks(root):
        raise RuntimeError("artifact root still contains broken symlinks")
    current = regular_file_snapshot(root)
    if current != receipt["regular_file_snapshot_after"]:
        raise RuntimeError("regular-file inventory differs from cleanup receipt")
    print(
        json.dumps(
            {
                "status": "verified",
                "deleted_stale_symlinks": len(EXPECTED_LINKS),
                "removed_empty_directories": 1,
                "broken_symlinks": 0,
                "unique_regular_file_bytes": current["unique_regular_file_bytes"],
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
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

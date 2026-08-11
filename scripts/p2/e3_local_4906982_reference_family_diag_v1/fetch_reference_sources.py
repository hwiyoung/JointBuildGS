#!/usr/bin/env python3
"""Fetch immutable read-only reference snapshots into the task artifact namespace."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import yaml


def run(argv: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.run(
        argv, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ).stdout.strip()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_manifest(root: Path) -> dict[str, object]:
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            files.append({
                "path": str(path.relative_to(root)),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            })
    return {
        "file_count": len(files),
        "byte_count": sum(int(row["bytes"]) for row in files),
        "files": files,
    }


def atomic_json(path: Path, body: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text())
    output = args.artifact_root / cfg["artifact_subdir"]
    output.mkdir(parents=True, exist_ok=True)
    receipt_rows = {}
    for name, spec in cfg["sources"].items():
        destination = output / name
        if not destination.exists():
            run(["git", "clone", "--no-checkout", "--filter=blob:none", spec["url"], str(destination)])
        if not (destination / ".git").is_dir():
            raise RuntimeError(f"non-git destination already exists: {destination}")
        run(["git", "fetch", "--depth", "1", "origin", spec["commit"]], cwd=destination)
        # Always materialize the requested tree.  A --no-checkout clone can
        # resolve HEAD while its empty worktree appears as every file deleted.
        run(["git", "checkout", "--detach", "--force", spec["commit"]], cwd=destination)
        actual = run(["git", "rev-parse", "HEAD"], cwd=destination)
        dirty = run(["git", "status", "--porcelain"], cwd=destination)
        if actual != spec["commit"] or dirty:
            raise RuntimeError(f"reference binding failed for {name}: {actual=} {dirty=}")
        receipt_rows[name] = {
            "url": spec["url"], "requested_commit": spec["commit"],
            "actual_commit": actual, "tree": tree_manifest(destination),
        }
    receipt = {
        "schema": "jointbuildgs.reference_source_snapshot.v1",
        "task_id": cfg["task_id"], "sources": receipt_rows,
        "scientific_verdict": None,
    }
    atomic_json(output.parent / "reference_sources_receipt.json", receipt)
    print(json.dumps({
        "output": str(output),
        "sources": {name: row["actual_commit"] for name, row in receipt_rows.items()},
        "scientific_verdict": None,
    }, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Create a fail-closed, non-mutating snapshot of a dirty Git worktree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo}", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def zpaths(payload: bytes) -> list[str]:
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in payload.split(b"\0")
        if item
    ]


def write_component(path: Path, payload: bytes) -> dict[str, object]:
    path.write_bytes(payload)
    return {"file": path.name, "bytes": len(payload), "sha256": digest(payload)}


def snapshot(source: Path, output: Path) -> dict[str, object]:
    source = source.resolve()
    output = output.resolve()
    if output.exists():
        raise RuntimeError(f"snapshot target already exists: {output}")
    if not (source / ".git").exists():
        raise RuntimeError(f"source is not a Git worktree: {source}")
    output.mkdir(parents=True)

    status = git(source, "status", "--porcelain=v2", "-z", "--branch")
    staged = git(source, "diff", "--cached", "--binary", "--full-index", "HEAD")
    unstaged = git(source, "diff", "--binary", "--full-index")
    staged_names = git(source, "diff", "--cached", "--name-only", "-z")
    unstaged_names = git(source, "diff", "--name-only", "-z")
    untracked_names = git(source, "ls-files", "--others", "--exclude-standard", "-z")

    archive_paths = sorted(set(zpaths(staged_names) + zpaths(unstaged_names) + zpaths(untracked_names)))
    inventory: list[dict[str, object]] = []
    archive = output / "working_files.tar"
    with tarfile.open(archive, "w") as bundle:
        for relative in archive_paths:
            absolute = source / relative
            if not (absolute.exists() or absolute.is_symlink()):
                inventory.append({"path": relative, "state": "absent_in_worktree"})
                continue
            bundle.add(absolute, arcname=relative, recursive=True)
            if absolute.is_symlink():
                inventory.append(
                    {"path": relative, "state": "symlink", "target": os.readlink(absolute)}
                )
            elif absolute.is_file():
                inventory.append(
                    {
                        "path": relative,
                        "state": "regular",
                        "bytes": absolute.stat().st_size,
                        "sha256": file_digest(absolute),
                    }
                )
            else:
                inventory.append({"path": relative, "state": "directory"})

    components = {
        "status": write_component(output / "status.porcelain-v2.z", status),
        "staged_patch": write_component(output / "staged.patch", staged),
        "unstaged_patch": write_component(output / "unstaged.patch", unstaged),
        "staged_names": write_component(output / "staged-names.z", staged_names),
        "unstaged_names": write_component(output / "unstaged-names.z", unstaged_names),
        "untracked_names": write_component(output / "untracked-names.z", untracked_names),
        "working_files": {
            "file": archive.name,
            "bytes": archive.stat().st_size,
            "sha256": file_digest(archive),
        },
    }
    manifest = {
        "schema": "jointbuildgs.local_wip_snapshot.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_repo": str(source),
        "branch": git(source, "branch", "--show-current").decode().strip(),
        "base_commit": git(source, "rev-parse", "HEAD").decode().strip(),
        "counts": {
            "staged_paths": len(zpaths(staged_names)),
            "unstaged_paths": len(zpaths(unstaged_names)),
            "untracked_paths": len(zpaths(untracked_names)),
            "archive_paths": len(archive_paths),
        },
        "components": components,
        "working_file_inventory": inventory,
        "restore_order": [
            "checkout base_commit in a disposable worktree",
            "git apply --index staged.patch",
            "git apply unstaged.patch",
            "extract working_files.tar over the worktree without touching .git",
            "compare git status --porcelain=v2 -z with status.porcelain-v2.z",
        ],
        "durable_backup_claim": False,
    }
    encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    (output / "manifest.json").write_bytes(encoded)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    manifest = snapshot(Path(args.source_repo), Path(args.output_dir))
    print(json.dumps(manifest["counts"], sort_keys=True))
    print(f"wrote {Path(args.output_dir).resolve() / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

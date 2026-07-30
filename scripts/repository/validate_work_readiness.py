#!/usr/bin/env python3
"""Fail closed when the clean-main ChatGPT Work contract is not satisfied."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path


REPO_INVENTORY = Path(__file__).with_name("repo_inventory.py")
SPEC = importlib.util.spec_from_file_location("jointbuildgs_repo_inventory", REPO_INVENTORY)
assert SPEC and SPEC.loader
inventory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inventory
SPEC.loader.exec_module(inventory)

CONTROL_PATHS = {
    "README.md",
    "docs/README.md",
    "phases/README.md",
    "phases/p0-audit/README.md",
    "phases/p2-gsjso/README.md",
}
EXPECTED_RESOLUTION_COUNTS = {
    "deterministic_current_path": 55,
    "external_artifact": 62,
    "historical_migration": 23,
    "missing_evidence": 87,
}
WORK_REQUIRED_MARKERS = (
    "docs/evidence/archive/**",
    "missing://JointBuildGS/",
    "source-lock v4",
    "integrity_verified_external_unpromoted",
    "without the external artifact backend",
    "CHATGPT_WORK_CODEX_HANDOFF.md",
    "serialized ownership",
)
CATALOG_ISSUES = Path("docs/research/repository/CATALOG_ISSUES.md")
ZERO_UNCLASSIFIED_MARKER = "| Local Markdown links/embeds that do not resolve | 0 |"


def git_paths(repo: Path) -> set[str]:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo}", "ls-files", "-z"],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
    )
    return {
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    }


def canonical_paths(config: dict) -> set[str]:
    paths = {str(item["path"]) for item in config.get("canonical_documents", [])}
    for family in config.get("reviewed_family_maps", []):
        paths.update(
            str(item["path"])
            for item in family.get("documents", [])
            if item.get("status") == "canonical"
        )
    return paths


def is_sparse_checkout(repo: Path) -> bool:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo}", "config", "--bool", "core.sparseCheckout"],
        cwd=repo,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def validate_generated_catalog_summary(repo: Path, errors: list[str]) -> None:
    path = repo / CATALOG_ISSUES
    if not path.is_file() or path.is_symlink():
        errors.append(f"generated catalog summary is unavailable: {CATALOG_ISSUES}")
        return
    report = path.read_text(encoding="utf-8")
    if ZERO_UNCLASSIFIED_MARKER not in report:
        errors.append("generated catalog does not prove zero unclassified Markdown references")


def validate(repo: Path, config: dict, artifact_root: Path | None) -> list[str]:
    errors: list[str] = []
    tracked = git_paths(repo)
    if (repo / "AGENTS.md").read_bytes() != (repo / "CLAUDE.md").read_bytes():
        errors.append("root AGENTS.md and CLAUDE.md differ")
    nested = sorted(
        path for path in tracked
        if path not in {"AGENTS.md", "CLAUDE.md"}
        and Path(path).name in {"AGENTS.md", "CLAUDE.md"}
    )
    if nested:
        errors.append(f"nested agent instructions remain: {nested}")

    authority_paths = canonical_paths(config) | CONTROL_PATHS
    for path in sorted(authority_paths):
        if path not in tracked:
            errors.append(f"Work authority path is not tracked: {path}")
            continue
        relations, _, _, _ = inventory.scan_relations(
            repo,
            path,
            set(config["text_extensions"]),
            int(config["max_text_scan_bytes"]),
        )
        for relation in relations:
            if relation.relation in {"references", "embeds"} and relation.target_exists == "no":
                errors.append(
                    f"physical broken link in Work authority: {path}:{relation.line} -> {relation.evidence}"
                )

    ledger_path = repo / str(config["reference_resolution_manifest"])
    with ledger_path.open("r", encoding="utf-8", newline="") as handle:
        ledger = list(csv.DictReader(handle))
    counts = Counter(row["class"] for row in ledger)
    if dict(counts) != EXPECTED_RESOLUTION_COUNTS:
        errors.append(
            f"reference resolution counts changed: {dict(counts)} != {EXPECTED_RESOLUTION_COUNTS}"
        )
    for row in ledger:
        target = row["resolved_target"].split("#", 1)[0]
        if row["class"] in {"deterministic_current_path", "historical_migration"} and (
            row["verification"] in {"repo_exists", "frozen_source;repo_target_exists"}
        ):
            if not (repo / target).exists():
                errors.append(f"reviewed repository target disappeared: {target}")
        if artifact_root is not None and (
            row["class"] == "external_artifact"
            or row["verification"] == "frozen_source;artifact_target_exists"
        ):
            if not (artifact_root / target).exists():
                errors.append(f"reviewed external artifact disappeared: {target}")
        if row["class"] == "missing_evidence":
            if (repo / target).exists():
                errors.append(f"known-missing target now exists in Git; review ledger: {target}")
            if artifact_root is not None and (artifact_root / target).exists():
                errors.append(f"known-missing target now exists externally; review ledger: {target}")

    if is_sparse_checkout(repo):
        validate_generated_catalog_summary(repo, errors)
    else:
        _, relations, _ = inventory.build_inventory(repo, config)
        unclassified = [
            relation for relation in relations
            if relation.relation in {"references", "embeds"} and relation.target_exists == "no"
        ]
        if unclassified:
            errors.append(f"unclassified Markdown references remain: {len(unclassified)}")

    start = (repo / "docs/research/WORK_START_HERE.md").read_text(encoding="utf-8")
    for marker in WORK_REQUIRED_MARKERS:
        if marker not in start:
            errors.append(f"Work entrypoint lacks required boundary: {marker}")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/repository/repo_inventory.json"
    )
    parser.add_argument(
        "--artifact-root",
        help="Optional local JointBuildGS-artifacts root for live external verification",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = inventory.find_repo_root(Path.cwd())
    config = json.loads((repo / args.config).read_text(encoding="utf-8"))
    artifact_root = Path(args.artifact_root).resolve() if args.artifact_root else None
    errors = validate(repo, config, artifact_root)
    if errors:
        print("ChatGPT Work readiness: FAIL", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    mode = "Git + local artifact" if artifact_root else "Git-only"
    print(f"ChatGPT Work readiness: PASS ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

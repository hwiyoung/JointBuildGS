#!/usr/bin/env python3
"""Validate the single-root agent-instruction contract.

This command is read-only. Exact byte equality is intentionally stronger than a
best-effort semantic comparison: any root mirror drift fails closed.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable


CANONICAL_NAME = "AGENTS.md"
MIRROR_NAME = "CLAUDE.md"
REQUIRED_MARKERS = (
    "only seven top-level directories",
    "Fusion W1",
    "JBGS_ARTIFACT_ROOT=/artifacts/JointBuildGS",
    "only canonical agent instruction file",
    "Docker-based execution",
    "Reproducibility",
    "One task, one commit",
    "Failure visibility",
    "EPSG:25832",
    "미분 가능 렌더링",
    "never\n   “뉴럴 렌더링”",
    "Roofer-style evidence-to-CityGML read-out",
    "without an external roofprint",
    "GT separation",
    "terrain MVS normals",
    "never hardcode it",
    "P0 `data/raw` is immutable",
    "external P0 `data/work`",
    "ground=2 and\n    building=6",
    "Two-host handoff",
    "validate_two_host_handoff.py",
    "technical handoff always keeps `scientific_verdict` null",
    "separate approval document",
)
FORBIDDEN_MARKERS = (
    "Use the manifest and Compose compatibility mounts",
)
PHASE_READMES = (
    "phases/p0-audit/README.md",
    "phases/p2-gsjso/README.md",
)
PHASE_README_REQUIRED_MARKERS = {
    "phases/p0-audit/README.md": (
        "`/workspace/data`",
        "`/workspace/runs`",
        "`JBGS_ARTIFACT_ROOT=/artifacts/JointBuildGS`",
        "it does not create repo-local\n`phases/p0-audit/{data,runs}`",
    ),
}
PHASE_README_FORBIDDEN_MARKERS = {
    "phases/p0-audit/README.md": (
        "`/workspace/JointBuildGS/phases/p0-audit/{data,runs}`",
    ),
}
SUPPORT_FILE_CONTRACTS = {
    "docker-compose.yml": {
        "required": (
            "JBGS_ARTIFACT_ROOT=/artifacts/JointBuildGS",
            "${JBGS_ARTIFACT_HOST_ROOT:-../JointBuildGS-artifacts}:/artifacts/JointBuildGS",
        ),
        "forbidden": (
            ":/workspace/JointBuildGS/data",
            ":/workspace/JointBuildGS/results",
            ":/workspace/JointBuildGS/reports",
            ":/workspace/JointBuildGS/fair-pilot",
            ":/workspace/JointBuildGS/phases/p0-audit/data",
            ":/workspace/JointBuildGS/phases/p0-audit/runs",
        ),
    },
    "phases/p0-audit/env/docker-compose.p0.yml": {
        "required": (
            "JBGS_ARTIFACT_ROOT: /artifacts/JointBuildGS",
            "${JBGS_ARTIFACT_HOST_ROOT:-../../../../JointBuildGS-artifacts}:/artifacts/JointBuildGS",
            "phase-payloads/p0-audit/data:/workspace/data",
            "phase-payloads/p0-audit/runs:/workspace/runs",
        ),
        "forbidden": (
            "- ../data:/workspace/data",
            "- ../runs:/workspace/runs",
        ),
    },
    "artifacts/manifests/local_workspace_20260730.yaml": {
        "required": (
            "compatibility_snapshot_at_relocation:",
            "current_resolver_contract:",
            "canonical_host_root: file:../JointBuildGS-artifacts",
            "canonical_container_root: file:/artifacts/JointBuildGS",
            "environment_variable: JBGS_ARTIFACT_ROOT=/artifacts/JointBuildGS",
            "top_level_compose:\n    repository: /workspace/JointBuildGS\n    artifact_root: /artifacts/JointBuildGS\n    host_data_volume: /data",
            "p0_compose:\n    artifact_root: /artifacts/JointBuildGS\n    phase_data: /workspace/data\n    phase_runs: /workspace/runs",
            "compatibility_scope: explicit-phase-compose-only",
            "runtime_verification:\n    state: verified",
        ),
        "forbidden": (),
    },
}


def nested_instruction_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for name in (CANONICAL_NAME, MIRROR_NAME):
        found.extend(path for path in root.rglob(name) if path.parent != root)
    return sorted(found)


def validate(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    canonical = root / CANONICAL_NAME
    mirror = root / MIRROR_NAME

    if not canonical.is_file():
        errors.append(f"missing canonical instruction: {CANONICAL_NAME}")
    elif canonical.is_symlink():
        errors.append(f"canonical instruction must not be a symlink: {CANONICAL_NAME}")
    if not mirror.is_file():
        errors.append(f"missing compatibility mirror: {MIRROR_NAME}")
    elif mirror.is_symlink():
        errors.append(f"compatibility mirror must not be a symlink: {MIRROR_NAME}")
    if canonical.is_file() and mirror.is_file():
        canonical_bytes = canonical.read_bytes()
        mirror_bytes = mirror.read_bytes()
        if canonical_bytes != mirror_bytes:
            errors.append("root CLAUDE.md is not byte-identical to root AGENTS.md")
        text = canonical_bytes.decode("utf-8")
        comparable_text = text.casefold()
        for marker in REQUIRED_MARKERS:
            if marker.casefold() not in comparable_text:
                errors.append(f"canonical instruction missing marker: {marker}")
        for marker in FORBIDDEN_MARKERS:
            if marker.casefold() in comparable_text:
                errors.append(f"canonical instruction contains forbidden marker: {marker}")

    for path in nested_instruction_files(root):
        errors.append(f"nested agent instruction is forbidden: {path.relative_to(root)}")

    for relative in PHASE_READMES:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing phase status README: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        if "root `AGENTS.md`" not in text:
            errors.append(f"phase README does not defer to root AGENTS.md: {relative}")
        comparable_text = text.casefold()
        for marker in PHASE_README_REQUIRED_MARKERS.get(relative, ()):
            if marker.casefold() not in comparable_text:
                errors.append(f"phase README missing marker ({relative}): {marker}")
        for marker in PHASE_README_FORBIDDEN_MARKERS.get(relative, ()):
            if marker.casefold() in comparable_text:
                errors.append(f"phase README contains forbidden marker ({relative}): {marker}")

    for relative, contract in SUPPORT_FILE_CONTRACTS.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"missing instruction support file: {relative}")
            continue
        comparable_text = path.read_text(encoding="utf-8").casefold()
        for marker in contract["required"]:
            if marker.casefold() not in comparable_text:
                errors.append(f"instruction support file missing marker ({relative}): {marker}")
        for marker in contract["forbidden"]:
            if marker.casefold() in comparable_text:
                errors.append(f"instruction support file contains forbidden marker ({relative}): {marker}")

    return errors


def format_errors(errors: Iterable[str]) -> str:
    return "\n".join(f"ERROR: {error}" for error in errors)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root (default: inferred from this script)",
    )
    args = parser.parse_args()
    errors = validate(args.root)
    if errors:
        print(format_errors(errors))
        return 1
    print("agent-instruction contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

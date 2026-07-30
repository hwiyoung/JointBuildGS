"""Resolve repository-relative runtime payloads through the artifact backend.

Tracked code, configs, and compact receipts stay in the repository. Large phase
payloads may instead live below ``JBGS_ARTIFACT_ROOT/phase-payloads``. Resolution
is exact and fail-closed: no basename search or content substitution is used.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath


class ArtifactResolutionError(RuntimeError):
    """A logical payload path mapped to more than one external object."""


def receipt_compatible_path(value: str | Path) -> str:
    """Normalize only the reviewed Fusion run-directory insertion."""

    logical = PurePosixPath(Path(value).as_posix())
    prefix = ("phases", "p2-gsjso", "runs", "fusion_w1")
    if logical.parts[:4] == prefix:
        logical = PurePosixPath(*logical.parts[:3], *logical.parts[4:])
    return logical.as_posix()


def logical_display_path(repo_root: Path, path: Path) -> str:
    """Render a resolved repo/artifact path using its receipt-era logical path."""

    absolute = path.resolve()
    try:
        return absolute.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        pass
    raw_root = os.environ.get("JBGS_ARTIFACT_ROOT")
    if not raw_root:
        return str(absolute)
    try:
        relative = absolute.relative_to(Path(raw_root).resolve())
    except ValueError:
        return str(absolute)
    parts = relative.parts
    if parts[:1] in {("data",), ("results",)}:
        return relative.as_posix()
    if parts[:1] == ("phase-payloads",) and len(parts) >= 4:
        logical = PurePosixPath("phases", parts[1], parts[2], *parts[3:])
        return receipt_compatible_path(logical.as_posix())
    return str(absolute)


def external_candidates(artifact_root: Path, relative: PurePosixPath) -> tuple[Path, ...]:
    parts = relative.parts
    if parts[:1] in {("data",), ("results",)}:
        return (artifact_root / Path(*parts),)
    if len(parts) < 4 or parts[0] != "phases":
        return ()
    phase = parts[1]
    category = parts[2]
    if phase not in {"p0-audit", "p2-gsjso"} or category not in {"data", "runs"}:
        return ()
    remainder = parts[3:]
    direct = artifact_root / "phase-payloads" / phase / category / Path(*remainder)
    candidates = [direct]
    if phase == "p2-gsjso" and category == "runs" and remainder[:1] != ("fusion_w1",):
        candidates.append(
            artifact_root / "phase-payloads" / phase / category / "fusion_w1" / Path(*remainder)
        )
    return tuple(candidates)


def resolve_existing_path(repo_root: Path, value: str | Path) -> Path:
    """Return a tracked path or one exact existing external payload path.

    Missing paths remain repository-relative so callers retain their own error
    messages and output-path behavior.
    """

    path = Path(value)
    if path.is_absolute():
        return path
    logical = PurePosixPath(path.as_posix())
    if ".." in logical.parts:
        raise ArtifactResolutionError(f"parent traversal is not a repository payload path: {value}")
    repository_path = repo_root.resolve() / Path(*logical.parts)
    repository_candidates = [repository_path]
    if logical.parts[:3] == ("phases", "p2-gsjso", "runs") and logical.parts[3:4] != (
        "fusion_w1",
    ):
        repository_candidates.append(
            repo_root.resolve()
            / "phases/p2-gsjso/runs/fusion_w1"
            / Path(*logical.parts[3:])
        )
    repository_matches = [
        candidate for candidate in repository_candidates if candidate.exists() or candidate.is_symlink()
    ]
    if len(repository_matches) > 1:
        rendered = ", ".join(str(item) for item in repository_matches)
        raise ArtifactResolutionError(f"ambiguous repository path for {value}: {rendered}")
    if repository_matches:
        return repository_matches[0]

    raw_root = os.environ.get("JBGS_ARTIFACT_ROOT")
    if not raw_root:
        return repository_path
    matches = [candidate for candidate in external_candidates(Path(raw_root), logical) if candidate.exists()]
    if len(matches) > 1:
        rendered = ", ".join(str(item) for item in matches)
        raise ArtifactResolutionError(f"ambiguous external artifact path for {value}: {rendered}")
    return matches[0] if matches else repository_path

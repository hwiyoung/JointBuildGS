#!/usr/bin/env python3
"""Canonical P0 evidence paths inside the P0 Docker workspace."""

from __future__ import annotations

from pathlib import Path


WORKSPACE = Path("/workspace")
P0_EVIDENCE_ROOT = WORKSPACE / "evidence/p0-audit"
P0_G1_PACKAGE = WORKSPACE / "evidence/p0_g1_20260613"
P0_ISSUES = WORKSPACE / "phase/issues.md"

_WORK_PACKAGES = {
    "W1": P0_EVIDENCE_ROOT / "w1-input-diagnostics",
    "W2": P0_EVIDENCE_ROOT / "w2-reconstruction-audit",
    "W3": P0_EVIDENCE_ROOT / "w3-quality-integration",
    "W4": P0_EVIDENCE_ROOT / "w4-gate-population",
}
_W1_NAMES = {
    "data_inventory.md",
    "dim_v1_classification_stats.md",
    "dim_v1_stats.md",
    "footprints_summary.md",
    "opf2colmap_summary.md",
    "scene_aoi_buildings.csv",
}


class P0EvidenceRouter:
    """Route a legacy flat evidence filename to its semantic work-package role."""

    def __truediv__(self, name: str) -> Path:
        if name == "G1_package":
            return P0_G1_PACKAGE
        if name in _W1_NAMES:
            work_package = _WORK_PACKAGES["W1"]
        else:
            prefix = next((candidate for candidate in _WORK_PACKAGES if name.startswith(candidate)), None)
            if prefix is None:
                raise ValueError(f"unroutable P0 evidence path: {name}")
            work_package = _WORK_PACKAGES[prefix]
        role = "reports" if Path(name).suffix.lower() in {".md", ".docx"} else "tables"
        return work_package / role / name

    def figs(self, work_package: str) -> Path:
        return _WORK_PACKAGES[work_package] / "figs"

    def mkdir(self, *, parents: bool = False, exist_ok: bool = False) -> None:
        for work_package in _WORK_PACKAGES.values():
            for role in ("reports", "tables"):
                (work_package / role).mkdir(parents=parents, exist_ok=exist_ok)


P0_EVIDENCE = P0EvidenceRouter()

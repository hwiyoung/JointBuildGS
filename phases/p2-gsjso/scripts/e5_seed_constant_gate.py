#!/usr/bin/env python3
"""E5 seed constant transition gate.

Checks only the new execution-path files named by the recipe registry geoid
inventory, not historical run outputs. It writes a small markdown gate table and
a phase-local versions fingerprint. Observation only.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[3]
TARGET_PATHS = [
    Path("phases/p2-gsjso/scripts/seed_prep_acmp.json"),
    Path("phases/p2-gsjso/scripts/tum_mob_seed_prep.sh"),
    Path("phases/p2-gsjso/scripts/tum_mob_raw_to_npz.py"),
    Path("phases/p2-gsjso/scripts/seed_depth_bands.py"),
    Path("phases/p2-gsjso/scripts/seed_material_audit.py"),
    Path("configs/tum_mob/seed_semantic.yaml"),
    Path("configs/tum_mob/gs_seed_acmp.yaml"),
    Path("src/stage2/semantic_seed.py"),
]
OLD_CONSTANT_RE = re.compile(r"(?<![\d.])(-556(?:\.0)?|556(?:\.0)?|48\.0|\+48|-558\.24)(?![\d.])")
ACMP_LAZ = Path("results/tum_transfer/mob_analysis/p0c_step2/acmp_aoi_utm.laz")


def git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def grep_old_constants() -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    for rel in TARGET_PATHS:
        path = REPO / rel
        for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if OLD_CONSTANT_RE.search(line):
                hits.append((rel.as_posix(), i, line.strip()))
    return hits


def sample_acmp_z(limit: int = 1_000_000) -> np.ndarray:
    import laspy

    with laspy.open(REPO / ACMP_LAZ) as src:
        chunks = []
        remaining = limit
        for points in src.chunk_iterator(250_000):
            z = np.asarray(points.z, dtype=np.float64)
            if len(z) > remaining:
                z = z[:remaining]
            chunks.append(z)
            remaining -= len(z)
            if remaining <= 0:
                break
    if not chunks:
        raise RuntimeError("ACMP source has no sampleable points")
    return np.concatenate(chunks)


def q(values: np.ndarray) -> tuple[float, float, float]:
    return (
        float(np.quantile(values, 0.05)),
        float(np.quantile(values, 0.50)),
        float(np.quantile(values, 0.95)),
    )


def write_versions(path: Path, run_id: str, gate_doc: Path, hit_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id={run_id}",
        "task=e5p-const A2 seed constant transition gate",
        f"created_at={datetime.now().isoformat(timespec='seconds')}",
        f"branch={git(['branch', '--show-current'])}",
        f"head_before_commit={git(['rev-parse', 'HEAD'])}",
        "crs=EPSG:25832",
        "docker_image=jointbuildgs-p0-tools:t0",
        f"gate_doc={gate_doc.relative_to(REPO)}",
        f"old_constant_hit_count={hit_count}",
        f"script=phases/p2-gsjso/scripts/e5_seed_constant_gate.py sha256={sha256(Path(__file__))}",
        "",
        "new_execution_paths:",
    ]
    for rel in TARGET_PATHS:
        path2 = REPO / rel
        lines.append(f"- {rel} sha256={sha256(path2)}")
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=datetime.now().strftime("e5p_const_%Y%m%d_%H%M%S"))
    ap.add_argument("--out", default="docs/e5_seed_constant_gate.md")
    args = ap.parse_args()

    hits = grep_old_constants()
    z_ortho = sample_acmp_z()
    old_local = z_ortho - 556.0
    new_local = z_ortho - 558.3
    delta = new_local - old_local
    oq = q(old_local)
    nq = q(new_local)
    dq = q(delta)

    changed = [
        ("ACMP seed transform", "seed_prep_acmp.json", "-556", "-558.3"),
        ("ACMP seed prep comment", "tum_mob_seed_prep.sh", "-556", "-558.3"),
        ("semantic seed/label shift", "seed_semantic.yaml; semantic_seed.py", "604-48=556", "604-45.7=558.3"),
        ("seed band geoid", "seed_depth_bands.py; seed_material_audit.py", "48.0", "45.7"),
        ("raw unification geoid", "tum_mob_raw_to_npz.py", "+48.0", "+45.7"),
    ]

    lines = [
        "# E5 Seed Constant Gate (A2)",
        "",
        "- CRS: EPSG:25832",
        f"- Branch: `{git(['branch', '--show-current'])}`",
        f"- HEAD before A2 commit: `{git(['rev-parse', 'HEAD'])}`",
        f"- Phase run: `phases/p2-gsjso/runs/{args.run_id}/versions.txt`",
        "- Scope: new execution-path files from `docs/recipe_registry.md` §5. Historical run outputs are not scanned.",
        "",
        "## Transition Diff Table",
        "",
        "| linked constant | files | before | after |",
        "|---|---|---:|---:|",
    ]
    for row in changed:
        lines.append(f"| {row[0]} | `{row[1]}` | `{row[2]}` | `{row[3]}` |")
    lines.extend(
        [
            "",
            "## Gate A: Old Constant Grep",
            "",
            f"- Old constant hit count in scoped new execution paths: {len(hits)}",
        ]
    )
    if hits:
        lines.extend(["", "| file | line | text |", "|---|---:|---|"])
        for file, line, text in hits:
            lines.append(f"| `{file}` | {line} | `{text}` |")
    else:
        lines.append("- Scoped grep result: 0 hits.")

    lines.extend(
        [
            "",
            "## Gate B: ACMP Z Distribution",
            "",
            "ACMP source is orthometric. Old local formula was `z - 556`; E5 canonical is `z - 558.3`.",
            "",
            "| formula | p05 local z | p50 local z | p95 local z |",
            "|---|---:|---:|---:|",
            f"| old `z-556` | {oq[0]:.3f} | {oq[1]:.3f} | {oq[2]:.3f} |",
            f"| new `z-558.3` | {nq[0]:.3f} | {nq[1]:.3f} | {nq[2]:.3f} |",
            "",
            "| delta new-old | p05 | p50 | p95 |",
            "|---|---:|---:|---:|",
            f"| m | {dq[0]:.3f} | {dq[1]:.3f} | {dq[2]:.3f} |",
            "",
            "Observation: the new formula lowers ACMP local z by 2.300 m, matching the preregistered `-604 + 45.7 = -558.3` camera-world frame relation. This records the offset removal material only.",
        ]
    )
    out = REPO / args.out
    out.write_text("\n".join(lines) + "\n")
    write_versions(REPO / f"phases/p2-gsjso/runs/{args.run_id}/versions.txt", args.run_id, out, len(hits))
    print(f"gate_doc={args.out}")
    print(f"run_versions=phases/p2-gsjso/runs/{args.run_id}/versions.txt")
    print(f"old_constant_hits={len(hits)}")
    print(f"acmp_delta_p50={dq[1]:.3f}")
    return 0 if len(hits) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

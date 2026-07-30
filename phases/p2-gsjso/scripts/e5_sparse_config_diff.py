#!/usr/bin/env python3
"""Document the E5 GS-sparse config diff against D4 dense."""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
DENSE = Path("configs/tum_mob/gs_d4_dense.yaml")
SPARSE = Path("configs/tum_mob/gs_d4_sparse.yaml")
SPARSE_SEED = Path("results/tum_transfer/mob_analysis/seed/seed_sparse.ply")
SPARSE_SOURCE = Path("phases/p0-audit/data/work/mvs/openmvs/colmap_txt/sparse/points3D.txt")
RECIPE = "GS(D4; seed-protect; pho1·sem0.1·nc0.05·dep0.03·nrm-off·str1[g2;na0.08;cp0.01;warm15k]; gssem)"


def git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def top_level_scalars(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (REPO / path).read_text().splitlines():
        if not line or line.startswith("#") or line.startswith(" ") or line.startswith("-"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.split("#", 1)[0].strip()
        out[key.strip()] = value
    return out


def sparse_seed_count(path: Path) -> int:
    with (REPO / path).open() as f:
        for line in f:
            if line.startswith("element vertex "):
                return int(line.split()[-1])
            if line.strip() == "end_header":
                break
    raise ValueError(f"cannot read PLY vertex count: {path}")


def write_versions(path: Path, run_id: str, doc: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id={run_id}",
        "task=e5p-sparse-config A3 GS-sparse config diff proof",
        f"created_at={datetime.now().isoformat(timespec='seconds')}",
        f"branch={git(['branch', '--show-current'])}",
        f"head_before_commit={git(['rev-parse', 'HEAD'])}",
        "crs=EPSG:25832",
        "docker_image=jointbuildgs-p0-tools:t0",
        f"doc={doc.relative_to(REPO)}",
        f"dense_config={DENSE} sha256={sha256(REPO / DENSE)}",
        f"sparse_config={SPARSE} sha256={sha256(REPO / SPARSE)}",
        f"sparse_seed={SPARSE_SEED} sha256={sha256(REPO / SPARSE_SEED)}",
        f"sparse_source={SPARSE_SOURCE} sha256={sha256(REPO / SPARSE_SOURCE)}",
        f"script=phases/p2-gsjso/scripts/e5_sparse_config_diff.py sha256={sha256(Path(__file__))}",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=datetime.now().strftime("e5p_sparse_config_%Y%m%d_%H%M%S"))
    ap.add_argument("--out", default="docs/experiments/pilots/e5_pilot/reports/e5_gs_sparse_config_diff.md")
    args = ap.parse_args()

    dense = top_level_scalars(DENSE)
    sparse = top_level_scalars(SPARSE)
    keys = sorted(set(dense) | set(sparse))
    diffs = [(k, dense.get(k, ""), sparse.get(k, "")) for k in keys if dense.get(k, "") != sparse.get(k, "")]
    recipe_diffs = [d for d in diffs if d[0] not in {"init_pointcloud", "out_dir"}]

    dense_lines = (REPO / DENSE).read_text().splitlines()
    sparse_lines = (REPO / SPARSE).read_text().splitlines()
    unified = "\n".join(
        difflib.unified_diff(
            dense_lines,
            sparse_lines,
            fromfile=str(DENSE),
            tofile=str(SPARSE),
            lineterm="",
        )
    )

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# E5 GS-Sparse Config Diff (A3)",
        "",
        "- CRS: EPSG:25832",
        f"- Branch: `{git(['branch', '--show-current'])}`",
        f"- HEAD before A3 commit: `{git(['rev-parse', 'HEAD'])}`",
        f"- Phase run: `phases/p2-gsjso/runs/{args.run_id}/versions.txt`",
        f"- Recipe string: `{RECIPE}`",
        f"- Sparse seed: `{SPARSE_SEED}` ({sparse_seed_count(SPARSE_SEED)} points)",
        f"- Sparse seed source: `{SPARSE_SOURCE}`",
        "",
        "## Scalar Key Diff",
        "",
        "| key | D4 dense | E5 sparse | classification |",
        "|---|---|---|---|",
    ]
    for key, old, new in diffs:
        cls = "seed" if key == "init_pointcloud" else "bookkeeping" if key == "out_dir" else "recipe_diff"
        lines.append(f"| `{key}` | `{old}` | `{new}` | {cls} |")
    if not diffs:
        lines.append("| none |  |  |  |")
    lines.extend(
        [
            "",
            "## Recipe Equality Check",
            "",
            f"- Recipe scalar diffs excluding seed path and output directory: {len(recipe_diffs)}",
        ]
    )
    if recipe_diffs:
        lines.extend(["", "| key | dense | sparse |", "|---|---|---|"])
        for key, old, new in recipe_diffs:
            lines.append(f"| `{key}` | `{old}` | `{new}` |")
    else:
        lines.append("- Result: 0 recipe-term differences. `out_dir` differs only to prevent overwriting dense outputs.")
    lines.extend(["", "## Unified Diff", "", "```diff", unified, "```", ""])
    out.write_text("\n".join(lines))

    write_versions(REPO / f"phases/p2-gsjso/runs/{args.run_id}/versions.txt", args.run_id, out)
    print(f"doc={args.out}")
    print(f"run_versions=phases/p2-gsjso/runs/{args.run_id}/versions.txt")
    print(f"recipe_diffs={len(recipe_diffs)}")
    print(f"sparse_seed_points={sparse_seed_count(SPARSE_SEED)}")
    return 0 if len(recipe_diffs) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Second fail-closed retention pass for completed, regenerable artifacts.

This pass is deliberately separate from the first archive/checkpoint cleanup.
It removes reviewed OpenMVS caches, compacted P0 LAS readout intermediates,
superseded P0 diagnostic attempts, a closed fair-pilot workspace, and Python
bytecode.  Unique raw inputs, live COLMAP/Fusion inputs, compact result packs,
canonical runs, and regeneration NPZ files are mandatory retained gates.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.repository.artifact_retention_cleanup import (
    REPO,
    artifact_rel,
    artifact_root,
    canonical_write,
    git,
    sha256_file,
    tree_stats,
)


PLAN_PATH = REPO / "artifacts/manifests/local_artifact_retention_pass2_plan_20260730.json"
RECEIPT_PATH = REPO / "artifacts/manifests/local_artifact_retention_pass2_receipt_20260730.json"
P0_DATA = "phase-payloads/p0-audit/data"
P0_RUNS = "phase-payloads/p0-audit/runs"

EXPECTED_TOTAL_BYTES = 28_526_243_565
EXPECTED_TOTAL_FILES = 2_949
EXPECTED_P0_DATA_BYTES = 7_011_088_110
EXPECTED_P0_DATA_FILES = 927
EXPECTED_P0_RUN_BYTES = 19_233_008_234
EXPECTED_P0_RUN_FILES = 1_673
EXPECTED_FAIR_CACHE_BYTES = 2_282_147_221
EXPECTED_FAIR_CACHE_FILES = 349

P0_DATA_EXACT = (
    ("work/mvs/openmvs/dim_dense_relaxed.mvs", 1_302_230_702),
    ("work/mvs/openmvs/dim_dense_relaxed.ply", 642_870_143),
    ("work/mvs/openmvs/dim_dense.mvs", 1_330_168_128),
)
DMAP_RE = re.compile(r"^depth\d{4}\.dmap$")
EXPECTED_DMAP_COUNT = 924
EXPECTED_DMAP_BYTES = 3_735_819_137

PROTOTYPE_DIRS = (
    "t7_failure_diagnosis_20260615_133845",
    "t7_failure_diagnosis_20260615_133921",
    "t8_population_profile_20260615_142538",
    "t9_failure_surface_cause_20260615_202222",
    "t9_failure_surface_cause_20260615_203200",
    "t11_survivor_texture_refine_20260615_212951",
    "t12_figure_failure_story_20260615_223248",
    "t12_figure_failure_story_20260615_223346",
    "t14_qualitative_figures_20260616_231601",
    "t14_qualitative_figures_20260617_102137",
    "t14_qualitative_figures_20260617_102345",
    "t14_qualitative_figures_20260617_102858",
    "t14_qualitative_figures_20260617_103026",
    "t14_qualitative_figures_20260617_103904",
    "t14_qualitative_figures_20260617_104912",
    "t14_qualitative_figures_20260617_105027",
    "t14_qualitative_figures_final",
    "t14_qualitative_figures_fix",
    "t14_qualitative_model_render_20260616_220529",
    "t15_input_output_compare_20260616_224915",
    "v6c_no_points",
    "tum_floor_test",
)
CANONICAL_P0_RUNS = (
    "t7_failure_diagnosis_20260615_134149",
    "t8_population_profile_20260615_143004",
    "t9_failure_surface_cause_20260615_204200",
    "t10_survivor_texture_gap_20260615_204851",
    "t11_survivor_texture_refine_20260615_213358",
    "t12_figure_failure_story_20260615_223458",
    "t13_validity_error_breakdown_20260616_214359",
    "t14_qualitative_figures_v2",
)
GROUND_PLAN_SHA256 = "d84a3b0cb67fe52e53b0b3d9d3f3ca2ddf7d4b641ac262c8a1467e3955945c65"
GROUND_PLAN_BYTES = 10_601_714
EXPECTED_GROUND_PLAN_COPIES = 25

LAS_FAMILIES = {
    "e5p_readout_ablation_20260708_C001": (858, 15_643_851_516),
    "e5p_3b_s1_20260708_C001": (106, 445_246_282),
    "e5p_corrected_s1_20260709_C001": (94, 392_310_208),
    "e5p_corrected_s1_recheck_20260709_C001": (279, 1_071_963_993),
    "e5p_s1_full_factor_20260709_C001": (72, 240_249_744),
    "mob_eval_v6sem": (44, 823_193_198),
    "tum_e2e_proper": (2, 313_469_964),
}

FAIR_TARGETS = (
    ("fair-pilot/runs/20260714_vaihingen_area3/workspace", 71, 2_256_936_854),
    ("fair-pilot/runs/20260714_vaihingen_area3/tmp", 5, 22_184_087),
)
PY_CACHE_BASE = "results/tum_transfer/e5_s1_full_factor/C001/python_deps/timm_0_4_12"
EXPECTED_PY_CACHE_DIRS = 14
EXPECTED_PY_CACHE_FILES = 273
EXPECTED_PY_CACHE_BYTES = 3_026_280

RETAINED_P0_DATA = (
    "phase-payloads/p0-audit/data/raw/isprs/Vaihingen.zip",
    "phase-payloads/p0-audit/data/work/mvs/openmvs/scene.mvs",
    "phase-payloads/p0-audit/data/work/mvs/openmvs/dim_dense.ply",
    "phase-payloads/p0-audit/data/work/mvs/dim/dim_v1.laz",
    "phase-payloads/p0-audit/data/work/mvs/colmap_dense/stereo",
    "phase-payloads/p0-audit/data/work/mvs/colmap_dense/images",
    "phase-payloads/p0-audit/data/work/mvs/colmap_dense/sparse",
)
REGENERATION_GATES = (
    ("results/tum_transfer/e5_pilot/C001/readout_ablation", "tsdf_gssem.npz", 1),
    ("results/tum_transfer/e5_3b_s1/C001/readout_ablation", "tsdf_gssem.npz", 6),
    ("results/tum_transfer/e5_corrected_s1/C001/readout_ablation", "tsdf_gssem.npz", 6),
    ("results/tum_transfer/e5_corrected_s1_recheck/C001/readout_ablation", "tsdf_gssem.npz", 16),
    ("results/tum_transfer/e5_s1_full_factor/C001/readout_ablation", "tsdf_gssem.npz", 4),
)
REGENERATION_EXACT = (
    "results/tum_transfer/mob/tsdf_v6sem_gs_seed_acmp_protect.npz",
    "results/tum_transfer/mob/tsdf_v6sem_gs_seed_dense_protect.npz",
    "results/tum_transfer/analysis/tsdf_proper.npz",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--finalize", action="store_true")
    parser.add_argument("--artifact-root", type=Path, default=None)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_text_chunks() -> list[tuple[Path, bytes]]:
    import subprocess

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
    excluded = {PLAN_PATH.resolve(strict=False), RECEIPT_PATH.resolve(strict=False)}
    suffixes = {".csv", ".json", ".jsonl", ".md", ".py", ".sh", ".tsv", ".txt", ".yaml", ".yml"}
    chunks: list[tuple[Path, bytes]] = []
    for encoded in listed:
        if not encoded:
            continue
        path = REPO / os.fsdecode(encoded)
        if path.resolve(strict=False) in excluded or not path.is_file():
            continue
        if path.suffix.lower() not in suffixes or path.stat().st_size > 16 * 1024 * 1024:
            continue
        try:
            chunks.append((path, path.read_bytes()))
        except OSError:
            pass
    return chunks


def record(root: Path, path: Path, category: str) -> dict[str, Any]:
    return {"path": artifact_rel(root, path), "category": category, **tree_stats(path)}


def is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def p0_data_targets(root: Path) -> list[dict[str, Any]]:
    openmvs = root / P0_DATA / "work/mvs/openmvs"
    dmaps = sorted(path for path in openmvs.iterdir() if path.is_file() and DMAP_RE.match(path.name))
    if len(dmaps) != EXPECTED_DMAP_COUNT or sum(path.stat().st_size for path in dmaps) != EXPECTED_DMAP_BYTES:
        raise RuntimeError("OpenMVS dmap cache inventory differs from reviewed set")
    targets = [record(root, path, "openmvs_densification_cache") for path in dmaps]
    for relative, expected_bytes in P0_DATA_EXACT:
        path = root / P0_DATA / relative
        if not path.is_file() or path.stat().st_size != expected_bytes:
            raise RuntimeError(f"reviewed OpenMVS intermediate changed: {path}")
        targets.append(record(root, path, "openmvs_superseded_or_serialized_intermediate"))
    if sum(item["bytes"] for item in targets) != EXPECTED_P0_DATA_BYTES or sum(item["files"] for item in targets) != EXPECTED_P0_DATA_FILES:
        raise RuntimeError("P0 data cleanup total differs from reviewed set")
    return targets


def p0_run_targets(root: Path, chunks: list[tuple[Path, bytes]]) -> list[dict[str, Any]]:
    runs = root / P0_RUNS
    prototypes = [runs / name for name in PROTOTYPE_DIRS]
    targets = [record(root, path, "superseded_p0_diagnostic_attempt") for path in prototypes]
    if any(not path.is_dir() for path in prototypes):
        raise FileNotFoundError("reviewed P0 prototype directory is missing")

    copies = sorted(runs.rglob("scratch/lod2_ground_plan.geojson"))
    if len(copies) != EXPECTED_GROUND_PLAN_COPIES:
        raise RuntimeError("ground-plan duplicate count differs from reviewed set")
    canonical = runs / "t14_qualitative_figures_v2/scratch/lod2_ground_plan.geojson"
    for path in copies:
        if path.stat().st_size != GROUND_PLAN_BYTES or sha256_file(path) != GROUND_PLAN_SHA256:
            raise RuntimeError(f"ground-plan duplicate SHA mismatch: {path}")
        if path == canonical or any(is_inside(path, prototype) for prototype in prototypes):
            continue
        targets.append(record(root, path, "sha_verified_duplicate_scratch_input"))

    for family, (expected_count, expected_bytes) in LAS_FAMILIES.items():
        family_root = runs / family
        files = sorted(path for path in family_root.rglob("*.las") if path.is_file())
        if len(files) != expected_count or sum(path.stat().st_size for path in files) != expected_bytes:
            raise RuntimeError(f"P0 LAS inventory differs for {family}")
        internal_receipt = REPO / "phases/p0-audit/runs" / family / "prep_metrics.csv"
        for path in files:
            repo_style = f"phases/p0-audit/runs/{path.relative_to(runs).as_posix()}".encode()
            referencing = [source for source, chunk in chunks if repo_style in chunk]
            external = [
                source
                for source in referencing
                if source.resolve(strict=False) != internal_receipt.resolve(strict=False)
            ]
            if external:
                raise RuntimeError(
                    "external repository text directly references LAS: "
                    f"{repo_style.decode()} from {external[0].relative_to(REPO)}"
                )
            targets.append(record(root, path, "regenerable_p0_roofer_las"))

    if sum(item["bytes"] for item in targets) != EXPECTED_P0_RUN_BYTES or sum(item["files"] for item in targets) != EXPECTED_P0_RUN_FILES:
        raise RuntimeError("P0 run cleanup total differs from reviewed set")
    return targets


def fair_cache_targets(root: Path) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for relative, expected_files, expected_bytes in FAIR_TARGETS:
        path = root / relative
        stats = tree_stats(path)
        if stats["files"] != expected_files or stats["bytes"] != expected_bytes:
            raise RuntimeError(f"fair-pilot workspace differs from reviewed set: {relative}")
        targets.append({"path": relative, "category": "closed_fair_pilot_regenerable_workspace", **stats})
    cache_base = root / PY_CACHE_BASE
    caches = sorted(path for path in cache_base.rglob("__pycache__") if path.is_dir())
    if len(caches) != EXPECTED_PY_CACHE_DIRS:
        raise RuntimeError("Python cache directory count differs from reviewed set")
    cache_files = [path for cache in caches for path in cache.rglob("*") if path.is_file()]
    if len(cache_files) != EXPECTED_PY_CACHE_FILES or sum(path.stat().st_size for path in cache_files) != EXPECTED_PY_CACHE_BYTES:
        raise RuntimeError("Python bytecode cache total differs from reviewed set")
    if any(path.suffix != ".pyc" for path in cache_files):
        raise RuntimeError("non-pyc file found in reviewed Python cache set")
    targets.extend(record(root, path, "python_bytecode_cache") for path in caches)
    if sum(item["bytes"] for item in targets) != EXPECTED_FAIR_CACHE_BYTES or sum(item["files"] for item in targets) != EXPECTED_FAIR_CACHE_FILES:
        raise RuntimeError("fair/cache cleanup total differs from reviewed set")
    return targets


def retained_records(root: Path) -> dict[str, Any]:
    p0_data: list[dict[str, Any]] = []
    for relative in RETAINED_P0_DATA:
        path = root / relative
        stats = tree_stats(path)
        if stats["files"] <= 0:
            raise FileNotFoundError(f"retained P0 input missing: {relative}")
        p0_data.append({"path": relative, **stats})

    canonical_runs: list[dict[str, Any]] = []
    for name in CANONICAL_P0_RUNS:
        path = root / P0_RUNS / name
        stats = tree_stats(path)
        if stats["files"] <= 0:
            raise FileNotFoundError(f"canonical P0 run missing: {name}")
        canonical_runs.append({"path": artifact_rel(root, path), **stats})

    regeneration: list[dict[str, Any]] = []
    for relative, filename, minimum in REGENERATION_GATES:
        base = root / relative
        matches = sorted(base.rglob(filename))
        if len(matches) < minimum:
            raise FileNotFoundError(f"regeneration NPZ gate failed: {relative}")
        regeneration.append({"path": relative, "matching_files": len(matches)})
    for relative in REGENERATION_EXACT:
        path = root / relative
        if not path.is_file() or path.stat().st_size <= 0:
            raise FileNotFoundError(f"regeneration input missing: {relative}")
        regeneration.append({"path": relative, **tree_stats(path)})

    fair_receipts = root / "fair-pilot/runs/20260714_vaihingen_area3"
    fair = []
    for name in ("final_summary.json", "stage_manifest.csv", "run.log", "all_building_metrics.csv", "versions.txt"):
        path = fair_receipts / name
        if not path.is_file():
            raise FileNotFoundError(f"fair-pilot compact record missing: {path}")
        fair.append({"path": artifact_rel(root, path), **tree_stats(path)})
    return {
        "p0_data": p0_data,
        "canonical_p0_runs": canonical_runs,
        "regeneration_inputs": regeneration,
        "fair_pilot_records": fair,
    }


def build_plan(root: Path) -> dict[str, Any]:
    chunks = repo_text_chunks()
    data_targets = p0_data_targets(root)
    run_targets = p0_run_targets(root, chunks)
    other_targets = fair_cache_targets(root)
    targets = data_targets + run_targets + other_targets
    paths = [item["path"] for item in targets]
    if len(paths) != len(set(paths)):
        raise RuntimeError("duplicate path in pass-2 plan")
    if sum(item["bytes"] for item in targets) != EXPECTED_TOTAL_BYTES:
        raise RuntimeError("pass-2 planned bytes differ from reviewed total")
    if sum(item["files"] for item in targets) != EXPECTED_TOTAL_FILES:
        raise RuntimeError("pass-2 planned files differ from reviewed total")
    return {
        "schema": "jointbuildgs.local_artifact_retention_pass2_plan.v1",
        "created_utc": utc_now(),
        "git_head": git("rev-parse", "HEAD"),
        "artifact_root": str(root),
        "pre": tree_stats(root),
        "policy": {
            "raw_data_deleted": False,
            "active_fusion_deleted": False,
            "retained_pilot_1wave_deleted": False,
            "canonical_p0_run_deleted": False,
            "compact_non_las_results_retained": True,
            "expired_internal_prep_metrics_las_pointers": True,
        },
        "targets": targets,
        "planned_delete_bytes": EXPECTED_TOTAL_BYTES,
        "planned_delete_files": EXPECTED_TOTAL_FILES,
        "retained": retained_records(root),
    }


def remove_path(root: Path, relative: str) -> None:
    path = root / relative
    artifact_rel(root, path)
    if not path.exists() and not path.is_symlink():
        return
    if path.is_file() or path.is_symlink():
        path.unlink()
    else:
        shutil.rmtree(path)


def prepare(root: Path) -> None:
    if PLAN_PATH.exists() or RECEIPT_PATH.exists():
        raise RuntimeError("pass-2 plan or receipt already exists")
    plan = build_plan(root)
    canonical_write(PLAN_PATH, plan)
    print(json.dumps({"state": "prepared", "targets": len(plan["targets"]), "bytes": plan["planned_delete_bytes"], "files": plan["planned_delete_files"]}, indent=2))


def apply(root: Path) -> None:
    if not PLAN_PATH.is_file() or RECEIPT_PATH.exists():
        raise RuntimeError("an unfinalized pass-2 plan is required")
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    if Path(plan["artifact_root"]).resolve() != root:
        raise RuntimeError("artifact root differs from pass-2 plan")
    for item in plan["targets"]:
        path = root / item["path"]
        artifact_rel(root, path)
        if not path.exists() and not path.is_symlink():
            continue
        current = tree_stats(path)
        for field in ("bytes", "files", "symlinks"):
            if int(current[field]) != int(item[field]):
                raise RuntimeError(f"pass-2 target changed: {item['path']} {field}")
    retained_records(root)
    for item in plan["targets"]:
        remove_path(root, item["path"])
    print(json.dumps({"state": "applied", "targets": len(plan["targets"]), "bytes": plan["planned_delete_bytes"]}, indent=2))


def finalize(root: Path) -> None:
    if not PLAN_PATH.is_file() or RECEIPT_PATH.exists():
        raise RuntimeError("a prepared, unfinalized pass-2 plan is required")
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    remaining = [item["path"] for item in plan["targets"] if (root / item["path"]).exists() or (root / item["path"]).is_symlink()]
    if remaining:
        raise RuntimeError(f"pass-2 deletion remains: {remaining[0]}")
    retained = retained_records(root)
    post = tree_stats(root)
    removed_bytes = int(plan["pre"]["bytes"]) - int(post["bytes"])
    removed_files = int(plan["pre"]["files"]) - int(post["files"])
    if removed_bytes != EXPECTED_TOTAL_BYTES or removed_files != EXPECTED_TOTAL_FILES:
        raise RuntimeError("pass-2 observed totals differ from immutable plan")
    receipt = {
        "schema": "jointbuildgs.local_artifact_retention_pass2_receipt.v1",
        "sealed_utc": utc_now(),
        "state": "complete",
        "git_head_at_finalize": git("rev-parse", "HEAD"),
        "artifact_root": str(root),
        "pre": plan["pre"],
        "post": post,
        "removed_bytes": removed_bytes,
        "removed_files": removed_files,
        "target_count": len(plan["targets"]),
        "retention_policy": plan["policy"],
        "retained_gate_groups": {key: len(value) for key, value in retained.items()},
        "plan_sha256": sha256_file(PLAN_PATH),
        "unrelated_repository_files_deleted": False,
    }
    canonical_write(RECEIPT_PATH, receipt)
    print(json.dumps(receipt, indent=2))


def main() -> None:
    args = parse_args()
    root = artifact_root(args.artifact_root)
    if args.prepare:
        prepare(root)
    elif args.apply:
        apply(root)
    elif args.finalize:
        finalize(root)
    else:
        plan = build_plan(root)
        print(json.dumps({"state": "dry_run", "targets": len(plan["targets"]), "planned_delete_bytes": plan["planned_delete_bytes"], "planned_delete_gib": plan["planned_delete_bytes"] / (1024**3), "planned_delete_files": plan["planned_delete_files"]}, indent=2))


if __name__ == "__main__":
    main()

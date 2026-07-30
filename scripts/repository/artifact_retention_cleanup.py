#!/usr/bin/env python3
"""Fail-closed cleanup for reviewed local JointBuildGS artifact duplicates.

The sibling artifact workspace is not a backup.  This utility therefore deletes
only an immutable plan made from three evidence-backed classes:

* official MatrixCity archives whose SHA-256 matches the live Hugging Face LFS
  object and whose extracted working copy remains present;
* historical ``results/**/ckpt/step_*.pt`` intermediates that are not referenced
  by the current repository, while the latest step in every checkpoint directory
  remains present; and
* explicitly named caches, empty layouts, generated test temporaries, and exact
  duplicate evidence whose canonical Git copy has the recorded SHA-256.

Dry-run is the default.  Use ``--prepare``, then inspect the generated plan, run
``--apply`` in the pinned container as root, and finish with ``--finalize``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


REPO = Path(__file__).resolve().parents[2]
PLAN_PATH = REPO / "artifacts/manifests/local_artifact_retention_plan_20260730.json"
RECEIPT_PATH = (
    REPO / "artifacts/manifests/local_artifact_retention_receipt_20260730.json"
)
EXACT_DUPLICATE_MANIFEST = (
    REPO / "artifacts/manifests/exact_duplicate_quarantine_20260730.yaml"
)
HF_REPOSITORY = "BoDai/MatrixCity"
HF_REVISION = "22237509a7a16d5c0136b58b39597629a63b338d"
HF_API_ROOT = f"https://huggingface.co/api/datasets/{HF_REPOSITORY}/tree/{HF_REVISION}"
HF_RESOLVE_ROOT = f"https://huggingface.co/datasets/{HF_REPOSITORY}/resolve/{HF_REVISION}"
HF_API_PATHS = (
    "small_city_normal/aerial/train",
    "small_city_depth_float32/aerial/train",
    "small_city_pointcloud",
)

# path, bytes, Hugging Face LFS SHA-256, extracted counterpart
MATRIXCITY_ARCHIVES = (
    ("small_city_normal/aerial/train/block_10_normal.tar", 8561305600, "0525f4d4ae88015c9ebea2d712b9fdc09775195c42521cd489694d823c24ef4b", "block_10_normal"),
    ("small_city_normal/aerial/train/block_1_normal.tar", 6380318720, "b81da6bd4ee00cef72499308c0658ef475c33af1fcaa4d8d59b3f548045038a7", "block_1_normal"),
    ("small_city_normal/aerial/train/block_2_normal.tar", 2864814080, "123437dda0bb493d7e268edcbc3eb4a167eda1c8c031d92a22479875d5379d92", "block_2_normal"),
    ("small_city_normal/aerial/train/block_3_normal.tar", 1603522560, "acb01e0a17d4a3a19b1ba342f6d32fcd087ce462424c0346eb24c21220c20313", "block_3_normal"),
    ("small_city_normal/aerial/train/block_4_normal.tar", 4130928640, "62f775d6b4727fb1e621fc43b061adb7d0f44ccc8679c8a33ae2d9758859607b", "block_4_normal"),
    ("small_city_normal/aerial/train/block_5_normal.tar", 2264576000, "a287a4a6108ad075f372a2b22279378b15488600dc1c3500822ed06c6abea02a", "block_5_normal"),
    ("small_city_normal/aerial/train/block_6_normal.tar", 2862510080, "2d5b52de4458a9caafd95af4b3c8abdf8c8b98b61bab9c0699916d5cba475b4a", "block_6_normal"),
    ("small_city_normal/aerial/train/block_7_normal.tar", 2429132800, "f9005362c0d7de28d581a7f3141b42b7cb0766a3a948246de551e6184e4a5964", "block_7_normal"),
    ("small_city_normal/aerial/train/block_8_normal.tar", 3239598080, "942b4e8086d3bf68c9c09f22fe6d3be1d2369a9b2700a9c95d4ee2df72a78b62", "block_8_normal"),
    ("small_city_normal/aerial/train/block_9_normal.tar", 12997898240, "f9163fcfb170694a9773df28c52e3f9e7cc3237826ac272055fc67f9c4a1dab8", "block_9_normal"),
    ("small_city_depth_float32/aerial/train/block_10_depth.tar", 3224975360, "377a1af8a3f173470ae42866d834eee8c214d69dccd3afe79443c82d0e9db58b", "block_10_depth"),
    ("small_city_depth_float32/aerial/train/block_1_depth.tar", 3707074560, "e4f522ef1495691bd5babcd98f7e005979845690e3c0a344970f54a93a60052a", "block_1_depth"),
    ("small_city_depth_float32/aerial/train/block_2_depth.tar", 1231329280, "6b3a50c38d8397660eac433cb6d361e032334b6705f5545bab7e93575230d820", "block_2_depth"),
    ("small_city_depth_float32/aerial/train/block_3_depth.tar", 762603520, "2d27221efb7c5d5cda60b573aa66d06a4102caf5c53bcce6bac571ae27fbeadb", "block_3_depth"),
    ("small_city_depth_float32/aerial/train/block_4_depth.tar", 2930083840, "6346f5ebb12b6ec9dbfd0a74f97e0c7434e8b71e7471e95109fa2f488faa79c7", "block_4_depth"),
    ("small_city_depth_float32/aerial/train/block_5_depth.tar", 1048760320, "8bff82a925d2c86a28639869aa83bfb6fcc629f7a9eeced1b8091fa24864fb0c", "block_5_depth"),
    ("small_city_depth_float32/aerial/train/block_6_depth.tar", 1630167040, "f2e32ada44748f91b0e57dbf034a0fd3e9bbc284b35f459d7eccf49b1fb8d099", "block_6_depth"),
    ("small_city_depth_float32/aerial/train/block_7_depth.tar", 822917120, "c91138460753390e66442f4048754462c4f45be0d940c3d6f30b1424b868acea", "block_7_depth"),
    ("small_city_depth_float32/aerial/train/block_8_depth.tar", 2053888000, "bcfbbefd93c143dd9d16edec608e5af6e5dabb4bab7b43abd9426f8f772a8187", "block_8_depth"),
    ("small_city_depth_float32/aerial/train/block_9_depth.tar", 7085025280, "e6810e3bd0b6a40b62ca44cf0e6d48e0499a256d2cfeb2c4ca43d3244d65242f", "block_9_depth"),
    ("small_city_pointcloud/matrixcity_point_cloud_ds20.zip", 1640078843, "c229bda6f42ce10ce1260e93d0842f4041aafa1c75bdac77bb9c0ccee30068d0", "small_city_pointcloud/point_cloud_ds20/aerial/Block_all.ply"),
)

JUNK_TARGETS = (
    ("data/matrixcity/.cache", "download_cache"),
    ("quarantine/20260730-semantic-restructure/generated-caches", "python_bytecode_cache"),
    ("quarantine/20260730-semantic-restructure/empty-layouts", "empty_layout_record"),
    ("quarantine/20260730-final-layout", "reviewed_empty_generated_layout_quarantine"),
    ("migration-work/empty-evidence-layout-20260730", "completed_migration_empty_layout"),
    ("migration-work/empty-artifact-manifest-layout-20260730", "completed_migration_empty_layout"),
    ("migration-work/empty-role-layouts-20260730", "completed_migration_empty_layout"),
    ("migration-work/empty-notes-layout-20260730-phase1_ablation", "completed_migration_empty_layout"),
    ("migration-work/empty-notes-layout-20260730-phase2_ablation_citygml", "completed_migration_empty_layout"),
    ("migration-work/empty-notes-layout-20260730-phase1_vanilla", "completed_migration_empty_layout"),
    ("migration-work/empty-notes-layout-20260730-phase1_structure", "completed_migration_empty_layout"),
    ("migration-work/empty-notes-layout-20260730-phase1_mutual", "completed_migration_empty_layout"),
    ("migration-work/empty-layout-tools_experiments_footprint_conditioned_readout-20260730", "completed_migration_empty_layout"),
    ("migration-work/empty-layout-phases_p2-gsjso_legacy-result-receipts-20260730", "completed_migration_empty_layout"),
    ("repository-placeholders", "retired_empty_placeholder_tree"),
)

TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".conf",
    ".csv",
    ".ini",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".rst",
    ".sh",
    ".toml",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
}
STEP_RE = re.compile(r"^step_(\d+)\.pt$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--finalize", action="store_true")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help="defaults to /artifacts/JointBuildGS in Docker, else the sibling workspace",
    )
    return parser.parse_args()


def artifact_root(argument: Path | None) -> Path:
    candidate = argument
    if candidate is None:
        docker_root = Path("/artifacts/JointBuildGS")
        candidate = docker_root if docker_root.is_dir() else REPO.parent / "JointBuildGS-artifacts"
    root = candidate.resolve(strict=True)
    docker_root = Path("/artifacts/JointBuildGS").resolve(strict=False)
    if (
        root == Path("/")
        or root == REPO.resolve()
        or (root.name != "JointBuildGS-artifacts" and root != docker_root)
    ):
        raise RuntimeError(f"refusing unexpected artifact root: {root}")
    return root


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git(*args: str) -> str:
    return subprocess.check_output(
        ("git", "-c", f"safe.directory={REPO}", *args),
        cwd=REPO,
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def canonical_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_stats(path: Path) -> dict[str, int]:
    if not path.exists() and not path.is_symlink():
        return {"bytes": 0, "files": 0, "dirs": 0, "symlinks": 0}
    if path.is_symlink():
        return {"bytes": path.lstat().st_size, "files": 0, "dirs": 0, "symlinks": 1}
    if path.is_file():
        return {"bytes": path.stat().st_size, "files": 1, "dirs": 0, "symlinks": 0}
    totals = {"bytes": 0, "files": 0, "dirs": 1, "symlinks": 0}
    for current, dirnames, filenames in os.walk(path, followlinks=False):
        totals["dirs"] += len(dirnames)
        for name in filenames:
            item = Path(current) / name
            if item.is_symlink():
                totals["bytes"] += item.lstat().st_size
                totals["symlinks"] += 1
            else:
                totals["bytes"] += item.stat().st_size
                totals["files"] += 1
    return totals


def artifact_rel(root: Path, path: Path) -> str:
    resolved = path.resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"path escapes artifact root: {path}") from exc
    if relative == Path("."):
        raise RuntimeError("artifact root itself is never a valid deletion target")
    return relative.as_posix()


def current_repo_text() -> list[bytes]:
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
    chunks: list[bytes] = []
    for encoded in listed:
        if not encoded:
            continue
        path = REPO / os.fsdecode(encoded)
        if path.resolve(strict=False) in excluded or not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 16 * 1024 * 1024:
            continue
        try:
            chunks.append(path.read_bytes())
        except OSError:
            continue
    return chunks


def fetch_hf_inventory() -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for api_path in HF_API_PATHS:
        url = f"{HF_API_ROOT}/{api_path}?recursive=true&expand=false&limit=100"
        request = urllib.request.Request(url, headers={"User-Agent": "JointBuildGS-retention-audit/1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
        for record in payload:
            path = str(record.get("path", ""))
            if path.endswith((".tar", ".zip")):
                inventory[path] = record
    return inventory


def verify_extracted(root: Path, relative: str) -> dict[str, Any]:
    path = root / "data/matrixcity" / relative
    if path.is_file():
        if path.stat().st_size <= 0:
            raise RuntimeError(f"empty extracted counterpart: {path}")
        return {"path": artifact_rel(root, path), **tree_stats(path)}
    if not path.is_dir():
        raise FileNotFoundError(f"extracted counterpart missing: {path}")
    stats = tree_stats(path)
    if stats["files"] <= 0:
        raise RuntimeError(f"extracted counterpart has no files: {path}")
    return {"path": artifact_rel(root, path), **stats}


def archive_records(root: Path, *, verify_remote: bool, hash_local: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    remote = fetch_hf_inventory() if verify_remote else {}
    records: list[dict[str, Any]] = []
    retained: list[dict[str, Any]] = []
    for relative, expected_bytes, expected_sha, extracted in MATRIXCITY_ARCHIVES:
        path = root / "data/matrixcity" / relative
        if not path.is_file() or path.stat().st_size != expected_bytes:
            raise RuntimeError(f"MatrixCity archive size mismatch: {path}")
        if hash_local and sha256_file(path) != expected_sha:
            raise RuntimeError(f"MatrixCity archive SHA-256 mismatch: {path}")
        if verify_remote:
            item = remote.get(relative)
            lfs = (item or {}).get("lfs") or {}
            if int((item or {}).get("size", -1)) != expected_bytes:
                raise RuntimeError(f"MatrixCity remote size mismatch: {relative}")
            if str(lfs.get("oid", "")) != expected_sha:
                raise RuntimeError(f"MatrixCity remote LFS SHA mismatch: {relative}")
        extracted_record = verify_extracted(root, extracted)
        retained.append(extracted_record)
        records.append(
            {
                "path": artifact_rel(root, path),
                "category": "official_source_archive_with_extracted_copy",
                "bytes": expected_bytes,
                "files": 1,
                "dirs": 0,
                "symlinks": 0,
                "sha256": expected_sha,
                "remote_url": f"{HF_RESOLVE_ROOT}/{relative}?download=true",
                "remote_lfs_verified": verify_remote,
                "retained_extracted": extracted_record,
            }
        )
    return records, retained


def checkpoint_records(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    result_root = root / "results"
    chunks = current_repo_text()
    deletions: list[dict[str, Any]] = []
    retained: list[dict[str, Any]] = []
    for checkpoint_dir in sorted({path.parent for path in result_root.rglob("step_*.pt")}):
        steps: list[tuple[int, Path]] = []
        for path in checkpoint_dir.glob("step_*.pt"):
            match = STEP_RE.match(path.name)
            if match and path.is_file():
                steps.append((int(match.group(1)), path))
        if len(steps) < 2:
            continue
        steps.sort()
        latest_step, latest_path = steps[-1]
        latest_record = {
            "path": artifact_rel(root, latest_path),
            "bytes": latest_path.stat().st_size,
            "step": latest_step,
        }
        retained.append(latest_record)
        for step, path in steps[:-1]:
            relative = artifact_rel(root, path)
            if any(relative.encode("utf-8") in chunk for chunk in chunks):
                continue
            record = {
                "path": relative,
                "category": "unreferenced_intermediate_checkpoint",
                "bytes": path.stat().st_size,
                "files": 1,
                "dirs": 0,
                "symlinks": 0,
                "step": step,
                "retained_latest": latest_record,
            }
            deletions.append(record)
            sidecar = path.with_suffix(path.suffix + ".sha256")
            if sidecar.is_file():
                sidecar_relative = artifact_rel(root, sidecar)
                if any(sidecar_relative.encode("utf-8") in chunk for chunk in chunks):
                    raise RuntimeError(f"checkpoint sidecar is referenced: {sidecar_relative}")
                deletions.append(
                    {
                        "path": sidecar_relative,
                        "category": "unreferenced_intermediate_checkpoint_sidecar",
                        **tree_stats(sidecar),
                        "retained_latest": latest_record,
                    }
                )
    return deletions, retained


def verify_exact_duplicates(root: Path) -> list[dict[str, Any]]:
    manifest = yaml.safe_load(EXACT_DUPLICATE_MANIFEST.read_text(encoding="utf-8"))
    retained: list[dict[str, Any]] = []
    for record in manifest.get("files", []):
        canonical = REPO / str(record["canonical_path"])
        quarantined = (
            root
            / "quarantine/20260730-semantic-restructure/exact-duplicates/docs"
            / str(record["quarantine_path"])
        )
        expected_sha = str(record["sha256"])
        if not canonical.is_file() or not quarantined.is_file():
            raise FileNotFoundError(f"exact duplicate pair missing: {canonical} / {quarantined}")
        if sha256_file(canonical) != expected_sha or sha256_file(quarantined) != expected_sha:
            raise RuntimeError(f"exact duplicate SHA mismatch: {record['source_path']}")
        retained.append(
            {
                "path": canonical.relative_to(REPO).as_posix(),
                "bytes": canonical.stat().st_size,
                "sha256": expected_sha,
            }
        )
    return retained


def require_empty_of_files(path: Path) -> None:
    if not path.exists():
        return
    if not path.is_dir() or path.is_symlink():
        raise RuntimeError(f"expected an empty-layout directory: {path}")
    unexpected = [item for item in path.rglob("*") if item.is_file() or item.is_symlink()]
    if unexpected:
        raise RuntimeError(f"empty-layout tree acquired content: {unexpected[0]}")


def junk_records(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    retained = verify_exact_duplicates(root)
    records: list[dict[str, Any]] = []
    duplicate_root = root / "quarantine/20260730-semantic-restructure/exact-duplicates"
    records.append(
        {
            "path": artifact_rel(root, duplicate_root),
            "category": "sha_verified_exact_duplicate",
            **tree_stats(duplicate_root),
        }
    )
    empty_only = {
        relative
        for relative, category in JUNK_TARGETS
        if category in {"completed_migration_empty_layout", "retired_empty_placeholder_tree"}
    }
    for relative, category in JUNK_TARGETS:
        path = root / relative
        if relative in empty_only:
            require_empty_of_files(path)
        if relative == "quarantine/20260730-final-layout":
            allowed = {
                "empty-directories",
                "generated-by-inventory-test",
                "generated-test-temporaries",
                "retired-placeholders",
            }
            children = {child.name for child in path.iterdir()}
            if not children <= allowed:
                raise RuntimeError(f"unexpected final-layout quarantine content: {sorted(children - allowed)}")
        records.append({"path": artifact_rel(root, path), "category": category, **tree_stats(path)})
    return records, retained


def build_plan(root: Path, *, verify_remote: bool, hash_archives: bool) -> dict[str, Any]:
    archives, extracted = archive_records(
        root, verify_remote=verify_remote, hash_local=hash_archives
    )
    checkpoints, latest = checkpoint_records(root)
    junk, canonical = junk_records(root)
    targets = archives + checkpoints + junk
    paths = [record["path"] for record in targets]
    if len(paths) != len(set(paths)):
        raise RuntimeError("duplicate deletion path in cleanup plan")
    return {
        "schema": "jointbuildgs.local_artifact_retention_plan.v1",
        "created_utc": utc_now(),
        "git_head": git("rev-parse", "HEAD"),
        "git_branch": git("branch", "--show-current"),
        "artifact_root": str(root),
        "pre": tree_stats(root),
        "policy": {
            "raw_unique_data_deleted": False,
            "final_experiment_results_deleted": False,
            "active_fusion_payload_deleted": False,
            "history_rewritten": False,
            "gitignore_modified": False,
            "matrixcity_archives_recoverable_from": f"https://huggingface.co/datasets/{HF_REPOSITORY}/tree/{HF_REVISION}",
        },
        "targets": targets,
        "planned_delete_bytes": sum(int(record["bytes"]) for record in targets),
        "planned_delete_files": sum(int(record["files"]) for record in targets),
        "retained": {
            "matrixcity_extracted": extracted,
            "latest_checkpoints": latest,
            "canonical_exact_duplicates": canonical,
        },
    }


def remove_path(root: Path, relative: str) -> None:
    path = root / relative
    artifact_rel(root, path)
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def prepare(root: Path) -> None:
    if PLAN_PATH.exists() or RECEIPT_PATH.exists():
        raise RuntimeError("plan or receipt already exists; refusing to replace cleanup evidence")
    plan = build_plan(root, verify_remote=True, hash_archives=True)
    canonical_write(PLAN_PATH, plan)
    print(json.dumps({"state": "prepared", "plan": str(PLAN_PATH), "targets": len(plan["targets"]), "bytes": plan["planned_delete_bytes"]}, indent=2))


def apply(root: Path) -> None:
    if not PLAN_PATH.is_file() or RECEIPT_PATH.exists():
        raise RuntimeError("an unfinalized immutable plan is required")
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    if Path(plan["artifact_root"]).resolve() != root:
        raise RuntimeError("artifact root differs from prepared plan")
    allowed_categories = {
        "official_source_archive_with_extracted_copy",
        "unreferenced_intermediate_checkpoint",
        "unreferenced_intermediate_checkpoint_sidecar",
        "sha_verified_exact_duplicate",
        "download_cache",
        "python_bytecode_cache",
        "empty_layout_record",
        "reviewed_empty_generated_layout_quarantine",
        "completed_migration_empty_layout",
        "retired_empty_placeholder_tree",
    }
    for record in plan["targets"]:
        if str(record["category"]) not in allowed_categories:
            raise RuntimeError(f"unexpected planned category: {record['category']}")
        path = root / str(record["path"])
        artifact_rel(root, path)
        if not path.exists() and not path.is_symlink():
            # Idempotent resume after a mount-point EBUSY or other interrupted apply.
            continue
        current = tree_stats(path)
        for field in ("bytes", "files", "symlinks"):
            if int(current[field]) != int(record[field]):
                raise RuntimeError(
                    f"planned target changed before resume: {record['path']} {field}"
                )
    for record in plan["retained"]["matrixcity_extracted"]:
        verify_extracted(
            root, str(record["path"]).removeprefix("data/matrixcity/")
        )
    for record in plan["retained"]["latest_checkpoints"]:
        path = root / str(record["path"])
        if not path.is_file() or path.stat().st_size != int(record["bytes"]):
            raise RuntimeError(f"retained latest checkpoint changed: {record['path']}")
    for record in plan["retained"]["canonical_exact_duplicates"]:
        path = REPO / str(record["path"])
        if not path.is_file() or sha256_file(path) != str(record["sha256"]):
            raise RuntimeError(f"canonical evidence changed: {record['path']}")
    for record in plan["targets"]:
        remove_path(root, str(record["path"]))
    print(json.dumps({"state": "applied", "targets": len(plan["targets"]), "planned_bytes": plan["planned_delete_bytes"]}, indent=2))


def finalize(root: Path) -> None:
    if not PLAN_PATH.is_file() or RECEIPT_PATH.exists():
        raise RuntimeError("a prepared, unfinalized plan is required")
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    for record in plan["targets"]:
        path = root / str(record["path"])
        if path.exists() or path.is_symlink():
            raise RuntimeError(f"planned deletion still exists: {record['path']}")
    for record in plan["retained"]["matrixcity_extracted"]:
        verify_extracted(root, str(record["path"]).removeprefix("data/matrixcity/"))
    for record in plan["retained"]["latest_checkpoints"]:
        path = root / str(record["path"])
        if not path.is_file() or path.stat().st_size != int(record["bytes"]):
            raise RuntimeError(f"retained latest checkpoint changed: {record['path']}")
    for record in plan["retained"]["canonical_exact_duplicates"]:
        path = REPO / str(record["path"])
        if not path.is_file() or sha256_file(path) != str(record["sha256"]):
            raise RuntimeError(f"canonical evidence changed: {record['path']}")
    post = tree_stats(root)
    removed_bytes = int(plan["pre"]["bytes"]) - int(post["bytes"])
    removed_files = int(plan["pre"]["files"]) - int(post["files"])
    if removed_bytes <= 0 or removed_files <= 0:
        raise RuntimeError("cleanup did not reduce artifact storage")
    receipt = {
        "schema": "jointbuildgs.local_artifact_retention_receipt.v1",
        "sealed_utc": utc_now(),
        "state": "complete",
        "git_head_at_finalize": git("rev-parse", "HEAD"),
        "artifact_root": str(root),
        "pre": plan["pre"],
        "post": post,
        "removed_bytes": removed_bytes,
        "removed_files": removed_files,
        "planned_delete_bytes": plan["planned_delete_bytes"],
        "planned_delete_files": plan["planned_delete_files"],
        "target_count": len(plan["targets"]),
        "retention_policy": plan["policy"],
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
        plan = build_plan(root, verify_remote=True, hash_archives=True)
        print(
            json.dumps(
                {
                    "state": "dry_run",
                    "artifact_root": str(root),
                    "targets": len(plan["targets"]),
                    "planned_delete_bytes": plan["planned_delete_bytes"],
                    "planned_delete_gib": plan["planned_delete_bytes"] / (1024**3),
                    "planned_delete_files": plan["planned_delete_files"],
                    "categories": sorted({item["category"] for item in plan["targets"]}),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()

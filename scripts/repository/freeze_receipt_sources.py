#!/usr/bin/env python3
"""Freeze source bytes named by completed-run receipts before Git object pruning."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterator


SOURCE_SUFFIXES = {".json", ".py", ".sh", ".toml", ".yaml", ".yml"}
SOURCE_MARKERS = ("configs/", "scripts/", "src/", "tests/")
TRANSITIVE_SOURCE_LOCKS = (
    {
        "receipt_path": "phases/p2-gsjso/scripts/fusion_w1_aprime_report_20260726.py",
        "sha256": "5c35b05efe07728063fdc047a391e7abdced3ef587be0c56e2b4ee74a7fc221b",
        "bytes": 186776,
        "cited_by": [
            "receipt-source:phases/p2-gsjso/configs/fusion_w1_aprime_job_qualitative_v3_20260727.json#/locked_inputs/report_module"
        ],
    },
    {
        "receipt_path": "phases/p2-gsjso/configs/fusion_w1_training_v1_20260725.json",
        "sha256": "b57e20aee2c475ed766884e2cd39b17ffca522c2773f57d771932faed96bb367",
        "bytes": 7712,
        "cited_by": [
            "migration-lock:phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_v1_20260726.json#/training"
        ],
    },
    {
        "receipt_path": "docs/boundary_map_v4_1_ladder.csv",
        "sha256": "ae16170177ac0815eb6dd853b0469325c9a1018eeeac9b790b063927cbd7e7e2",
        "bytes": 136916,
        "cited_by": [
            "migration-lock:phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_v1_20260726.json#/texture_join"
        ],
    },
    {
        "receipt_path": "src/stage2/train.py",
        "sha256": "00c125e5de469ec43c1dbbf17393e91c9f700e52b93624309f76cc64bb5eb39e",
        "bytes": 202652,
        "cited_by": [
            "receipt-source:phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_v1_20260726.json#/training/trainer_source"
        ],
    },
    {
        "receipt_path": "scripts/stage3_readout/tum_mob_tsdf_extract.py",
        "sha256": "914cbad783b1eee27d1d2de24e702eb65e5caae1cd7bb142ebbe0fac200325bc",
        "bytes": 9944,
        "cited_by": [
            "migration-lock:phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_v1_20260726.json#/pointcloudification"
        ],
    },
    {
        "receipt_path": "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_seed_p0prime_20260725.py",
        "sha256": "582011ed0d68e8552827b21105e1fb9355ed708cd59b337dd6165394a10ff248",
        "bytes": 88254,
        "cited_by": [
            "migration-lock:phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_v1_20260726.json#/p0prime"
        ],
    },
    {
        "receipt_path": "docs/experiments/evaluation/qs_baseline178/tables/qs_baseline178_scores.csv",
        "sha256": "a3b89f1907e6e61aead702efe6b742b5c012615df77d90bdb2a859b5418d85ab",
        "bytes": 436898,
        "cited_by": [
            "migration-lock:phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_v1_20260726.json#/scoring/paired_baseline"
        ],
    },
    {
        "receipt_path": "phases/p0-audit/scripts/08_roofer_w2.py",
        "sha256": "ae655090915c56bfeee2be830a28e27520c2430e97d19e515a0aa046e4c79e97",
        "bytes": 26206,
        "cited_by": [
            "migration-lock:phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_v1_20260726.json#/scoring/canonical_helpers/roofer_status"
        ],
    },
    {
        "receipt_path": "scripts/e5_c001/e5_c001_8way.py",
        "sha256": "12322a7fd49c0904eaf7160946c7ef3b521ed091038452f9a863bef37f0bcbdc",
        "bytes": 59648,
        "cited_by": [
            "migration-lock:phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_v1_20260726.json#/scoring/canonical_helpers/roof_metrics"
        ],
    },
    {
        "receipt_path": "scripts/evaluation/quality_score/qs_baseline178_rescore.py",
        "sha256": "0d752dade0b8677460b55d381a69db77f7bf611061fb7479710434358db33e9d",
        "bytes": 37217,
        "cited_by": [
            "migration-lock:phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_v1_20260726.json#/scoring/canonical_helpers/coverage_and_xy"
        ],
    },
)


def git(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-c", f"safe.directory={repo}", "-C", str(repo), *args],
        input=input_bytes,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def nested_dicts(value: object) -> Iterator[dict[str, object]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nested_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_dicts(child)


def receipt_sources(receipts: list[Path]) -> list[dict[str, object]]:
    records: dict[tuple[str, str, int], dict[str, object]] = {}
    for receipt in receipts:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        for candidate in nested_dicts(payload):
            raw_path = candidate.get("path")
            raw_sha = candidate.get("sha256")
            raw_bytes = candidate.get("bytes")
            if not (
                isinstance(raw_path, str)
                and isinstance(raw_sha, str)
                and isinstance(raw_bytes, int)
            ):
                continue
            source_path = PurePosixPath(raw_path)
            if source_path.suffix not in SOURCE_SUFFIXES:
                continue
            if not any(marker in raw_path for marker in SOURCE_MARKERS):
                continue
            if source_path.is_absolute() or ".." in source_path.parts:
                raise RuntimeError(f"unsafe source path in receipt: {raw_path}")
            key = (raw_path, raw_sha, raw_bytes)
            record = records.setdefault(
                key,
                {
                    "receipt_path": raw_path,
                    "sha256": raw_sha,
                    "bytes": raw_bytes,
                    "cited_by": [],
                },
            )
            cited_by = record["cited_by"]
            assert isinstance(cited_by, list)
            receipt_name = receipt.as_posix()
            if receipt_name not in cited_by:
                cited_by.append(receipt_name)
    return [records[key] for key in sorted(records)]


def matching_git_blobs(repo: Path, records: list[dict[str, object]]) -> dict[tuple[str, int], str]:
    wanted = {(str(record["sha256"]), int(record["bytes"])) for record in records}
    wanted_sizes = {size for _, size in wanted}
    inventory = git(
        repo,
        "cat-file",
        "--batch-all-objects",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
    ).decode()
    by_size: dict[int, list[str]] = {}
    for line in inventory.splitlines():
        oid, object_type, raw_size = line.split()
        size = int(raw_size)
        if object_type == "blob" and size in wanted_sizes:
            by_size.setdefault(size, []).append(oid)

    matches: dict[tuple[str, int], str] = {}
    for size, oids in by_size.items():
        for oid in oids:
            payload = git(repo, "cat-file", "blob", oid)
            key = (digest(payload), size)
            if key in wanted:
                prior = matches.get(key)
                if prior is not None and prior != oid:
                    raise RuntimeError(f"multiple Git blobs match receipt source {key}: {prior}, {oid}")
                matches[key] = oid
    missing = sorted(wanted - set(matches))
    if missing:
        raise RuntimeError(f"receipt-bound source blobs are missing from Git object storage: {missing}")
    return matches


def freeze(
    repo: Path,
    artifact_run_root: Path,
    output: Path,
    repo_receipt: Path,
) -> dict[str, object]:
    repo = repo.resolve()
    artifact_run_root = artifact_run_root.resolve()
    output = output.resolve()
    repo_receipt = repo_receipt.resolve()
    if output.exists():
        raise RuntimeError(f"source-lock target already exists: {output}")

    receipts = [artifact_run_root / "20260728_fusion_w1_dense_baseline_qualitative_v5/manifest.json"]
    receipts.extend(
        sorted(
            (artifact_run_root / "20260726_fusion_w1_aprime/review_v6_roof_boundary").glob(
                "by_building/*/*/*/complete.json"
            )
        )
    )
    receipts.extend(
        sorted(
            (artifact_run_root / "20260726_fusion_w1_aprime/review_v7_reference_roof_boundary").glob(
                "by_building/*/*/*/complete.json"
            )
        )
    )
    if len(receipts) != 11 or any(not receipt.is_file() for receipt in receipts):
        raise RuntimeError(f"expected one v5, one v6, and nine v7 receipts; found {len(receipts)}")

    records = receipt_sources(receipts)
    records.extend(dict(record) for record in TRANSITIVE_SOURCE_LOCKS)
    records.sort(key=lambda record: (str(record["receipt_path"]), str(record["sha256"])))
    if len(records) != 40:
        raise RuntimeError(f"expected 40 receipt and migration source records; found {len(records)}")
    matches = matching_git_blobs(repo, records)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    temporary.chmod(0o755)
    try:
        source_root = temporary / "sources"
        for record in records:
            receipt_path = str(record["receipt_path"])
            target = source_root / receipt_path
            target.parent.mkdir(parents=True, exist_ok=True)
            key = (str(record["sha256"]), int(record["bytes"]))
            oid = matches[key]
            payload = git(repo, "cat-file", "blob", oid)
            if len(payload) != key[1] or digest(payload) != key[0]:
                raise RuntimeError(f"Git blob verification failed for {receipt_path}")
            target.write_bytes(payload)
            record["git_blob_oid"] = oid
            record["frozen_path"] = f"sources/{receipt_path}"
            record["cited_by"] = [
                item
                if str(item).startswith(("receipt-source:", "migration-lock:"))
                else str(Path(item).relative_to(artifact_run_root))
                for item in record["cited_by"]
            ]

        receipt_records = [
            {
                "path": str(path.relative_to(artifact_run_root)),
                "bytes": path.stat().st_size,
                "sha256": file_digest(path),
            }
            for path in receipts
        ]
        manifest = {
            "schema": "jointbuildgs.receipt_source_lock.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "base_commit": git(repo, "rev-parse", "HEAD").decode().strip(),
            "source_branch": "exp/fusion-w1",
            "scope": "completed Fusion W1 v5-v7 receipts plus exact pre-reorganization WIP and readout migration locks",
            "receipt_count": len(receipts),
            "source_record_count": len(records),
            "receipts": receipt_records,
            "sources": records,
            "policy": {
                "scientific_verdict": None,
                "completed_outputs_reproduction_source": "use these exact frozen bytes",
                "current_worktree_substitution_allowed": False,
                "git_object_pruning_allowed_before_freeze": False,
                "durable_backup_claim": False,
            },
        }
        encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
        (temporary / "manifest.json").write_bytes(encoded)

        for record in records:
            frozen = temporary / str(record["frozen_path"])
            if frozen.stat().st_size != record["bytes"] or file_digest(frozen) != record["sha256"]:
                raise RuntimeError(f"materialized source verification failed: {frozen}")
        os.replace(temporary, output)
        manifest_sha = file_digest(output / "manifest.json")
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    repo_record = {
        "schema": "jointbuildgs.receipt_source_lock_receipt.v1",
        "artifact_id": "fusion-w1-receipt-source-lock-v4-20260730",
        "role": "immutable-reproduction-source-for-completed-fusion-w1-receipts",
        "base_commit": manifest["base_commit"],
        "source_branch": manifest["source_branch"],
        "artifact_uri": "file:/artifacts/JointBuildGS/source-locks/fusion_w1/20260730-receipt-bound-v4",
        "host_uri": "file:../JointBuildGS-artifacts/source-locks/fusion_w1/20260730-receipt-bound-v4",
        "manifest_sha256": manifest_sha,
        "receipt_count": len(receipts),
        "source_record_count": len(records),
        "verification": {
            "all_receipt_source_hashes_matched": True,
            "all_git_blobs_materialized": True,
            "all_materialized_files_rehashed": True,
        },
        "durable_backup_claim": False,
        "warning": "This source-lock reproduces completed output receipts; it does not certify the later dirty WIP or a scientific verdict.",
    }
    repo_receipt.parent.mkdir(parents=True, exist_ok=True)
    repo_receipt.write_text(json.dumps(repo_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return repo_record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--artifact-run-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repo-receipt", required=True)
    args = parser.parse_args()
    receipt = freeze(
        Path(args.repo),
        Path(args.artifact_run_root),
        Path(args.output_dir),
        Path(args.repo_receipt),
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

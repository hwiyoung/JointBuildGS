#!/usr/bin/env python3
"""Verify external Fusion W1 completion artifacts and emit an unpromoted manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class VerificationError(RuntimeError):
    """An external artifact or receipt failed its locked contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise VerificationError(f"missing, non-regular, or symlink JSON: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VerificationError(f"JSON root is not an object: {path}")
    return value


def safe_child(root: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts:
        raise VerificationError(f"unsafe artifact path: {relative}")
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise VerificationError(f"artifact path escapes root: {relative}") from exc
    return candidate


def verify_record(root: Path, record: Mapping[str, Any], label: str) -> dict[str, Any]:
    path = safe_child(root, str(record.get("path", "")))
    if not path.is_file() or path.is_symlink():
        raise VerificationError(f"{label} is missing, non-regular, or symlink: {path}")
    observed_bytes = path.stat().st_size
    observed_sha = sha256_file(path)
    if observed_bytes != int(record.get("bytes", -1)):
        raise VerificationError(f"{label} byte count drift: {path}")
    if observed_sha != record.get("sha256"):
        raise VerificationError(f"{label} SHA256 drift: {path}")
    return {
        "path": path.relative_to(root.resolve()).as_posix(),
        "bytes": observed_bytes,
        "sha256": observed_sha,
    }


def artifact_path(artifact_root: Path, logical: str) -> Path:
    parts = Path(logical).parts
    prefix = ("phases", "p2-gsjso", "runs")
    if parts[:3] != prefix:
        raise VerificationError(f"unsupported Fusion artifact path: {logical}")
    remainder = parts[3:]
    if remainder[:1] == ("fusion_w1",):
        remainder = remainder[1:]
    return safe_child(
        artifact_root,
        str(Path("phase-payloads/p2-gsjso/runs/fusion_w1", *remainder)),
    )


def verify_panel_receipts(
    artifact_root: Path, run_root: Path, version: str, expected_count: int
) -> tuple[list[dict[str, Any]], int]:
    receipts = sorted(
        (run_root / "20260726_fusion_w1_aprime" / version).glob(
            "by_building/*/*/*/complete.json"
        )
    )
    if len(receipts) != expected_count:
        raise VerificationError(
            f"{version} completion count drift: {len(receipts)} != {expected_count}"
        )
    verified: list[dict[str, Any]] = []
    total_bytes = 0
    for receipt in receipts:
        payload = load_json(receipt)
        if payload.get("state") != "COMPLETE" or payload.get("scientific_verdict") is not None:
            raise VerificationError(f"{version} receipt state/verdict drift: {receipt}")
        panel = payload.get("outputs", {}).get("panel")
        if not isinstance(panel, Mapping):
            raise VerificationError(f"{version} panel record missing: {receipt}")
        panel_path = artifact_path(artifact_root, str(panel.get("path", "")))
        record = verify_record(
            panel_path.parent,
            {**panel, "path": panel_path.name},
            f"{version} panel",
        )
        receipt_record = {
            "path": receipt.relative_to(artifact_root.resolve()).as_posix(),
            "bytes": receipt.stat().st_size,
            "sha256": sha256_file(receipt),
        }
        total_bytes += record["bytes"]
        verified.append(
            {
                "identity": payload.get("identity"),
                "receipt": receipt_record,
                "panel": {
                    **record,
                    "path": panel_path.relative_to(artifact_root.resolve()).as_posix(),
                },
            }
        )
    return verified, total_bytes


def verify_source_lock(artifact_root: Path, repo_receipt: Path) -> dict[str, Any]:
    receipt = load_json(repo_receipt)
    if receipt.get("source_record_count") != 40 or receipt.get("receipt_count") != 11:
        raise VerificationError("source-lock receipt counts drift")
    lock_root = artifact_root / "source-locks/fusion_w1/20260730-receipt-bound-v4"
    manifest_path = lock_root / "manifest.json"
    if sha256_file(manifest_path) != receipt.get("manifest_sha256"):
        raise VerificationError("source-lock manifest SHA256 drift")
    manifest = load_json(manifest_path)
    if len(manifest.get("sources", [])) != 40 or len(manifest.get("receipts", [])) != 11:
        raise VerificationError("source-lock manifest counts drift")
    for record in manifest["sources"]:
        verify_record(lock_root, {**record, "path": record["frozen_path"]}, "source lock")
    run_root = artifact_root / "phase-payloads/p2-gsjso/runs/fusion_w1"
    for record in manifest["receipts"]:
        verify_record(run_root, record, "source-lock bound receipt")
    return {
        "artifact_id": receipt["artifact_id"],
        "manifest_sha256": receipt["manifest_sha256"],
        "receipt_count": 11,
        "source_record_count": 40,
        "all_records_rehashed": True,
    }


def build_manifest(artifact_root: Path, repo_source_lock_receipt: Path) -> dict[str, Any]:
    artifact_root = artifact_root.resolve()
    run_root = artifact_root / "phase-payloads/p2-gsjso/runs/fusion_w1"
    v5_root = run_root / "20260728_fusion_w1_dense_baseline_qualitative_v5"
    v5_manifest_path = v5_root / "manifest.json"
    v5 = load_json(v5_manifest_path)
    if (
        v5.get("state") != "COMPLETE"
        or v5.get("scientific_verdict") is not None
        or v5.get("interpretation") is not None
    ):
        raise VerificationError("V5 state/verdict contract drift")
    outputs = v5.get("outputs")
    if not isinstance(outputs, list) or len(outputs) != 35:
        raise VerificationError("V5 output count drift")
    v5_records = [verify_record(v5_root, record, "V5 output") for record in outputs]
    v6_records, v6_bytes = verify_panel_receipts(
        artifact_root, run_root, "review_v6_roof_boundary", 1
    )
    v7_records, v7_bytes = verify_panel_receipts(
        artifact_root, run_root, "review_v7_reference_roof_boundary", 9
    )
    source_lock = verify_source_lock(artifact_root, repo_source_lock_receipt)
    return {
        "schema": "jointbuildgs.fusion_w1.external_completion_inventory.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "state": "INTEGRITY_VERIFIED_EXTERNAL_UNPROMOTED",
        "scientific_verdict": None,
        "interpretation": None,
        "promotion_status": "not_promoted_to_canonical_evidence",
        "storage_class": "C_external_artifact_storage_plus_manifest",
        "source_lock": source_lock,
        "completed_sets": {
            "dense_v5": {
                "receipt": {
                    "path": v5_manifest_path.relative_to(artifact_root).as_posix(),
                    "bytes": v5_manifest_path.stat().st_size,
                    "sha256": sha256_file(v5_manifest_path),
                },
                "output_count": 35,
                "output_bytes": sum(record["bytes"] for record in v5_records),
                "output_set_sha256": v5.get("output_set_sha256"),
                "all_outputs_rehashed": True,
            },
            "panel_v6": {
                "completion_count": 1,
                "panel_count": 1,
                "panel_bytes": v6_bytes,
                "records": v6_records,
            },
            "panel_v7": {
                "completion_count": 9,
                "panel_count": 9,
                "panel_bytes": v7_bytes,
                "records": v7_records,
            },
        },
        "summary": {
            "completion_receipts": 11,
            "verified_output_records": 45,
            "all_declared_outputs_rehashed": True,
            "new_training_runs": 0,
            "canonical_evidence_claim": False,
        },
        "warning": "Integrity and technical reproducibility do not constitute scientific approval.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--source-lock-receipt", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    payload = build_manifest(Path(args.artifact_root), Path(args.source_lock_receipt))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

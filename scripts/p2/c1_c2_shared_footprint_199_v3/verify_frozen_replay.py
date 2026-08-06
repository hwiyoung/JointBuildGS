#!/usr/bin/env python3
"""Verify the exact frozen original-global v3 replay before downstream reuse."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPOSITORY = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = (
    REPOSITORY
    / "artifacts/manifests/p2/c1_c2_shared_footprint_199_original_global_v3"
    / "frozen_replay_20260806a_v1.json"
)
EXPECTED_SCHEMA = (
    "jointbuildgs.p2.c1_c2_shared_footprint_199.original_global.frozen_replay.v1"
)


class FreezeVerificationError(RuntimeError):
    """Raised when a frozen record is missing or has drifted."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_record_path(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise FreezeVerificationError(f"unsafe frozen record path: {relative}")
    path = root / rel
    if path.is_symlink():
        raise FreezeVerificationError(f"frozen record must not be a symlink: {relative}")
    return path


def verify(manifest_path: Path, artifact_root: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != EXPECTED_SCHEMA:
        raise FreezeVerificationError("unexpected freeze manifest schema")
    policy = manifest.get("policy", {})
    if policy.get("downstream_mode") != "EXACT_HASH_BOUND_REUSE_ONLY":
        raise FreezeVerificationError("freeze manifest does not require exact reuse")
    if policy.get("roofer_reconstruction_after_freeze_allowed") is not False:
        raise FreezeVerificationError("freeze manifest does not prohibit Roofer reruns")
    if policy.get("scientific_verdict") is not None or manifest.get("scientific_verdict") is not None:
        raise FreezeVerificationError("technical freeze must keep scientific_verdict null")

    records = manifest.get("records")
    if not isinstance(records, list) or len(records) != manifest.get("record_count"):
        raise FreezeVerificationError("freeze record count mismatch")
    source_root = artifact_root / manifest["artifact_relative_root"]
    verified = []
    for record in records:
        path = _safe_record_path(source_root, record["path"])
        if not path.is_file():
            raise FreezeVerificationError(f"missing frozen record: {record['path']}")
        observed_bytes = path.stat().st_size
        if observed_bytes != record["bytes"]:
            raise FreezeVerificationError(
                f"byte-size drift for {record['path']}: {observed_bytes} != {record['bytes']}"
            )
        observed_hash = sha256_file(path)
        if observed_hash != record["sha256"]:
            raise FreezeVerificationError(f"sha256 drift for {record['path']}")
        verified.append(
            {
                "path": record["path"],
                "bytes": observed_bytes,
                "sha256": observed_hash,
            }
        )
    return {
        "schema": "jointbuildgs.p2.frozen_replay_verification.v1",
        "freeze_id": manifest["freeze_id"],
        "status": "EXACT_FROZEN_REPLAY_VERIFIED",
        "verified_record_count": len(verified),
        "roofer_invocations": 0,
        "scientific_verdict": None,
        "records": verified,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    print(json.dumps(verify(args.manifest, args.artifact_root), sort_keys=True))


if __name__ == "__main__":
    main()

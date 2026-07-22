#!/usr/bin/env python3
"""Validate, explicitly fetch, and verify pilot reference artifacts.

The default ``audit`` command performs no network access and writes nothing.
``fetch`` requires explicit artifact IDs and a network acknowledgement.  It
stores code archives and model weights only in an external or git-ignored cache
and writes a SHA256 receipt; it never edits the lock JSON or stages an asset.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Iterable
from urllib.request import Request, urlopen


LOCK_SCHEMA = "jointbuildgs.pilot_1wave.reference_lock.v1"
RECEIPT_SCHEMA = "jointbuildgs.pilot_1wave.reference_receipt.v1"
EXPECTED_REVISIONS = {
    "pgsr": "de24f1a38b350387e8d8fe381b2cd70c1ae946e7",
    "planargs": "a68f22043e95146c4f1c52cc0e471a6a90e86f73",
    "grounded_segment_anything": "126abe633ffe333e16e4a0a4e946bc1003caf757",
    "groundingdino": "856dde20aee659246248e20734ef9ba5214f5e44",
    "segment_anything": "dca509fe793f601edb92606367a655c15ac00fdf",
}
EXPECTED_WEIGHT_FILENAMES = {
    "groundingdino_swint_ogc": "groundingdino_swint_ogc.pth",
    "sam_vit_h": "sam_vit_h_4b8939.pth",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256_file(path: Path, *, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _require_https(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.startswith("https://"):
        raise ValueError(f"{context} must be an https URL")
    return value


def _require_safe_filename(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty filename")
    if Path(value).name != value or value in {".", ".."}:
        raise ValueError(f"{context} must not contain a directory component")
    return value


def load_and_validate_lock(path: str | Path) -> dict[str, Any]:
    lock_path = Path(path)
    with lock_path.open("r", encoding="utf-8") as stream:
        lock = json.load(stream)
    if not isinstance(lock, dict) or lock.get("schema") != LOCK_SCHEMA:
        raise ValueError(f"lock schema must be {LOCK_SCHEMA}")
    if lock.get("training_started_by_this_lock") is not False:
        raise ValueError("reference lock must not claim to start training")

    references = lock.get("code_references")
    if not isinstance(references, dict) or set(references) != set(EXPECTED_REVISIONS):
        raise ValueError("code_references must contain exactly the five approved repositories")
    for ref_id, expected_revision in EXPECTED_REVISIONS.items():
        row = references[ref_id]
        if row.get("revision") != expected_revision:
            raise ValueError(f"{ref_id}: revision differs from the approved pin")
        _require_https(row.get("repository_url"), f"{ref_id}.repository_url")
        archive = row.get("source_archive")
        if not isinstance(archive, dict) or archive.get("state") != "unfetched":
            raise ValueError(f"{ref_id}: source archive must be explicitly unfetched")
        _require_https(archive.get("url"), f"{ref_id}.source_archive.url")
        _require_safe_filename(
            archive.get("expected_filename"),
            f"{ref_id}.source_archive.expected_filename",
        )
        license_row = row.get("license")
        if not isinstance(license_row, dict):
            raise ValueError(f"{ref_id}: license metadata is required")
        for key in ("spdx", "name", "source_url"):
            if not license_row.get(key):
                raise ValueError(f"{ref_id}: license.{key} is required")
        _require_https(license_row["source_url"], f"{ref_id}.license.source_url")

    weights = lock.get("model_weights")
    if not isinstance(weights, dict) or set(weights) != set(EXPECTED_WEIGHT_FILENAMES):
        raise ValueError("model_weights must contain exactly GroundingDINO Swin-T and SAM ViT-H")
    for weight_id, expected_filename in EXPECTED_WEIGHT_FILENAMES.items():
        row = weights[weight_id]
        if row.get("expected_filename") != expected_filename:
            raise ValueError(f"{weight_id}: unexpected model filename")
        _require_https(row.get("url"), f"{weight_id}.url")
        if row.get("state") != "unfetched":
            raise ValueError(f"{weight_id}: initial state must be unfetched")
        if row.get("tracked_in_git") is not False:
            raise ValueError(f"{weight_id}: model weights must be forbidden from git")
        expected_sha = row.get("expected_sha256")
        if expected_sha is not None and not SHA256_RE.fullmatch(str(expected_sha)):
            raise ValueError(f"{weight_id}: expected_sha256 is malformed")
        expected_size = row.get("expected_size_bytes")
        if expected_size is not None and int(expected_size) <= 0:
            raise ValueError(f"{weight_id}: expected_size_bytes must be positive")

    policy = lock.get("artifact_policy", {})
    if (
        policy.get("download_on_validation") is not False
        or policy.get("weight_files_in_git") != "forbidden"
        or policy.get("source_archives_in_git") != "forbidden"
        or policy.get("fetch_requires_explicit_artifact_ids") is not True
    ):
        raise ValueError("artifact policy must forbid implicit downloads and git assets")

    pipeline = lock.get("grounded_sam_pipeline")
    if not isinstance(pipeline, dict) or pipeline.get("prompt_literal") != "roof":
        raise ValueError("GroundedSAM prompt must be exactly 'roof'")
    thresholds = pipeline.get("thresholds") or {}
    expected_thresholds = {"box": 0.25, "text": 0.25, "nms_iou": 0.8}
    if any(float(thresholds.get(key, -1.0)) != value for key, value in expected_thresholds.items()):
        raise ValueError("GroundedSAM thresholds differ from the approved lock")
    fusion = pipeline.get("vision_fusion") or {}
    expected_fusion = {
        "footprint_dilation_px": 5,
        "footprint_core_erosion_px_default": 5,
        "footprint_core_erosion_px_small_building_if_default_empty": 1,
        "gt_used_for_selection": False,
    }
    if any(fusion.get(key) != value for key, value in expected_fusion.items()):
        raise ValueError("vision fusion morphology or GT-isolation contract mismatch")
    if fusion.get("no_sam_candidate_policy") != "retain the footprint erosion core and set fallback flag":
        raise ValueError("vision fusion must retain a flagged footprint core fallback")
    return lock


def lock_sha256(lock_path: str | Path) -> str:
    return sha256_file(Path(lock_path))


def iter_artifacts(lock: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for ref_id, row in lock["code_references"].items():
        archive = row["source_archive"]
        yield {
            "artifact_id": f"source:{ref_id}",
            "kind": "source_archive",
            "url": archive["url"],
            "expected_filename": archive["expected_filename"],
            "state_at_lock": archive["state"],
            "expected_sha256": None,
            "expected_size_bytes": None,
        }
    for weight_id, row in lock["model_weights"].items():
        yield {
            "artifact_id": f"weight:{weight_id}",
            "kind": "model_weight",
            "url": row["url"],
            "expected_filename": row["expected_filename"],
            "state_at_lock": row["state"],
            "expected_sha256": row.get("expected_sha256"),
            "expected_size_bytes": row.get("expected_size_bytes"),
        }


def artifact_map(lock: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = list(iter_artifacts(lock))
    result = {row["artifact_id"]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate artifact_id in reference lock")
    return result


def audit_local(lock: dict[str, Any], asset_root: str | Path) -> dict[str, Any]:
    root = Path(asset_root)
    rows = []
    for artifact in iter_artifacts(lock):
        path = root / artifact["expected_filename"]
        row = {
            "artifact_id": artifact["artifact_id"],
            "kind": artifact["kind"],
            "path": str(path),
            "state_at_lock": artifact["state_at_lock"],
            "local_state": "absent",
        }
        if path.is_file():
            row.update(
                {
                    "local_state": "present_unverified_without_receipt",
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
        elif path.exists():
            row["local_state"] = "invalid_not_regular_file"
        rows.append(row)
    return {
        "schema": "jointbuildgs.pilot_1wave.reference_audit.v1",
        "network_accessed": False,
        "artifacts": rows,
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _assert_cache_is_not_git_candidate(asset_root: Path) -> None:
    root = _repo_root()
    resolved = asset_root.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return
    probe = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", str(relative)],
        cwd=root,
        check=False,
    )
    if probe.returncode != 0:
        raise ValueError(
            f"asset root inside repository must be git-ignored, got {relative}"
        )


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
        temp_path = Path(stream.name)
    os.replace(temp_path, path)


def fetch_artifacts(
    lock: dict[str, Any],
    lock_path: str | Path,
    asset_root: str | Path,
    artifact_ids: list[str],
    receipt_path: str | Path,
) -> dict[str, Any]:
    if not artifact_ids:
        raise ValueError("fetch requires at least one explicit --artifact ID")
    known = artifact_map(lock)
    unknown = sorted(set(artifact_ids) - set(known))
    if unknown:
        raise ValueError(f"unknown artifact IDs: {unknown}")
    if len(set(artifact_ids)) != len(artifact_ids):
        raise ValueError("artifact IDs must not be repeated")

    root = Path(asset_root)
    _assert_cache_is_not_git_candidate(root)
    root.mkdir(parents=True, exist_ok=True)
    receipt_rows: dict[str, Any] = {}
    for artifact_id in artifact_ids:
        artifact = known[artifact_id]
        destination = root / artifact["expected_filename"]
        request = Request(
            artifact["url"],
            headers={"User-Agent": "JointBuildGS-reference-lock/1"},
        )
        with tempfile.NamedTemporaryFile(
            "wb", dir=root, prefix=f".{destination.name}.", delete=False
        ) as stream:
            temp_path = Path(stream.name)
            try:
                with urlopen(request) as response:
                    while True:
                        chunk = response.read(8 * 1024 * 1024)
                        if not chunk:
                            break
                        stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise
        size = temp_path.stat().st_size
        digest = sha256_file(temp_path)
        expected_sha = artifact.get("expected_sha256")
        expected_size = artifact.get("expected_size_bytes")
        if expected_sha is not None and digest != expected_sha:
            temp_path.unlink(missing_ok=True)
            raise ValueError(f"{artifact_id}: downloaded SHA256 mismatch")
        if expected_size is not None and size != int(expected_size):
            temp_path.unlink(missing_ok=True)
            raise ValueError(f"{artifact_id}: downloaded byte size mismatch")
        os.replace(temp_path, destination)
        receipt_rows[artifact_id] = {
            "kind": artifact["kind"],
            "source_url": artifact["url"],
            "filename": artifact["expected_filename"],
            "size_bytes": size,
            "sha256": digest,
        }

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "lock_sha256": lock_sha256(lock_path),
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
        "asset_root": str(root.resolve()),
        "artifacts": receipt_rows,
    }
    _atomic_json(Path(receipt_path), receipt)
    return receipt


def verify_receipt(
    lock: dict[str, Any],
    lock_path: str | Path,
    asset_root: str | Path,
    receipt_path: str | Path,
) -> dict[str, Any]:
    with Path(receipt_path).open("r", encoding="utf-8") as stream:
        receipt = json.load(stream)
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise ValueError(f"receipt schema must be {RECEIPT_SCHEMA}")
    if receipt.get("lock_sha256") != lock_sha256(lock_path):
        raise ValueError("receipt was created for a different lock JSON")
    known = artifact_map(lock)
    receipt_rows = receipt.get("artifacts")
    if not isinstance(receipt_rows, dict) or not receipt_rows:
        raise ValueError("receipt contains no artifacts")

    verified = []
    for artifact_id, row in receipt_rows.items():
        if artifact_id not in known:
            raise ValueError(f"receipt contains unknown artifact {artifact_id}")
        artifact = known[artifact_id]
        if row.get("source_url") != artifact["url"]:
            raise ValueError(f"{artifact_id}: receipt URL differs from lock")
        if row.get("filename") != artifact["expected_filename"]:
            raise ValueError(f"{artifact_id}: receipt filename differs from lock")
        expected_receipt_sha = str(row.get("sha256", ""))
        if not SHA256_RE.fullmatch(expected_receipt_sha):
            raise ValueError(f"{artifact_id}: receipt SHA256 is malformed")
        path = Path(asset_root) / artifact["expected_filename"]
        if not path.is_file():
            raise FileNotFoundError(path)
        actual_size = path.stat().st_size
        actual_sha = sha256_file(path)
        if actual_size != int(row.get("size_bytes", -1)) or actual_sha != expected_receipt_sha:
            raise ValueError(f"{artifact_id}: local artifact differs from receipt")
        if artifact.get("expected_sha256") not in (None, actual_sha):
            raise ValueError(f"{artifact_id}: local artifact differs from lock SHA256")
        if artifact.get("expected_size_bytes") not in (None, actual_size):
            raise ValueError(f"{artifact_id}: local artifact differs from lock byte size")
        verified.append(
            {
                "artifact_id": artifact_id,
                "filename": artifact["expected_filename"],
                "size_bytes": actual_size,
                "sha256": actual_sha,
            }
        )
    return {
        "schema": "jointbuildgs.pilot_1wave.reference_verification.v1",
        "lock_sha256": receipt["lock_sha256"],
        "verified": verified,
    }


def _parser() -> argparse.ArgumentParser:
    default_lock = Path(__file__).resolve().parents[1] / "configs" / "pilot_1wave_reference_lock.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=default_lock)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="validate lock and report local state without network")
    audit.add_argument("--asset-root", type=Path, required=True)

    fetch = subparsers.add_parser("fetch", help="explicitly download selected artifacts and write receipt")
    fetch.add_argument("--asset-root", type=Path, required=True)
    fetch.add_argument("--receipt", type=Path, required=True)
    fetch.add_argument("--artifact", action="append", required=True)
    fetch.add_argument(
        "--acknowledge-network-and-licenses",
        action="store_true",
        help="required guard; confirms that upstream licenses were reviewed",
    )

    verify = subparsers.add_parser("verify", help="verify local artifacts against a fetch receipt")
    verify.add_argument("--asset-root", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    lock = load_and_validate_lock(args.lock)
    if args.command == "audit":
        payload = audit_local(lock, args.asset_root)
    elif args.command == "fetch":
        if not args.acknowledge_network_and_licenses:
            raise SystemExit("fetch requires --acknowledge-network-and-licenses")
        payload = fetch_artifacts(
            lock,
            args.lock,
            args.asset_root,
            args.artifact,
            args.receipt,
        )
    elif args.command == "verify":
        payload = verify_receipt(lock, args.lock, args.asset_root, args.receipt)
    else:  # pragma: no cover - argparse enforces the choices
        raise AssertionError(args.command)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

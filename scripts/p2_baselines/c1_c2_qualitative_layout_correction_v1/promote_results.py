#!/usr/bin/env python3
"""Promote the layout-only correction without reopening its PNG or source CSV."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


TASK_ID = "P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R5-v1"
HANDOFF_ID = "P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R5-v1"
CONFIG_REL = "configs/p2_baselines/c1_c2_qualitative_layout_correction_v1/render_v1.json"
ACCEPTED_REL = f"artifacts/manifests/handoffs/{HANDOFF_ID}/100-accepted.json"
REPORT_REL = "docs/experiments/p2/c1_c2_qualitative_layout_correction_r5_v1/C1_C2_QUALITATIVE_LAYOUT_CORRECTION_R5_v1.md"
TECHNICAL_REL = "artifacts/manifests/p2_baselines/c1_c2_qualitative_layout_correction_r5_v1/technical_result_manifest_v1.json"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def _safe(root: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts:
        raise RuntimeError(f"unsafe promotion path: {relative}")
    root = root.resolve()
    result = (root / value).resolve()
    if root not in result.parents:
        raise RuntimeError(f"promotion path escaped repository: {relative}")
    return result


def _add_once(root: Path, relative: str, data: bytes) -> dict[str, Any]:
    path = _safe(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def promote(*, external_manifest: Path, repo_root: Path, source_commit: str, accepted_commit: str) -> dict[str, Any]:
    if _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise RuntimeError("promotion requires a clean accepted repository")
    config = json.loads(_safe(repo_root, CONFIG_REL).read_text(encoding="utf-8"))
    manifest = json.loads(external_manifest.read_text(encoding="utf-8"))
    accepted_path = _safe(repo_root, ACCEPTED_REL)
    accepted = json.loads(accepted_path.read_text(encoding="utf-8"))
    if _git(repo_root, "rev-parse", "HEAD") != accepted_commit or _git(repo_root, "rev-parse", "origin/main") != accepted_commit:
        raise RuntimeError("promotion HEAD/origin does not equal exact accepted commit")
    if _git(repo_root, "log", "-1", "--format=%H", "--", ACCEPTED_REL) != accepted_commit:
        raise RuntimeError("accepted receipt is not owned by exact accepted commit")
    if (
        accepted.get("handoff_id") != HANDOFF_ID
        or accepted.get("task_id") != TASK_ID
        or accepted.get("state") != "accepted"
        or accepted.get("transport", {}).get("exclusive_writer_ack") is not True
        or accepted.get("scientific", {}).get("scientific_verdict") is not None
        or len(accepted.get("artifacts", {}).get("records", [])) != 25
    ):
        raise RuntimeError("accepted receipt identity/ownership/artifact reuse mismatch")
    accepted_rows = accepted["artifacts"]["records"]
    accepted_identity = sorted(
        ({key: row[key] for key in ("uri", "bytes", "sha256")} for row in accepted_rows),
        key=lambda row: row["uri"],
    )
    identity_bytes = (json.dumps(accepted_identity, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    reuse = accepted["artifacts"].get("attestation_reuse", {})
    if (
        hashlib.sha256(identity_bytes).hexdigest() != config["predecessor"]["accepted_record_identity_sha256"]
        or sum(int(row["bytes"]) for row in accepted_identity) != config["predecessor"]["accepted_artifact_total_bytes"]
        or any(row.get("verification_method") != "closed_attestation_reuse" for row in accepted_rows)
        or reuse.get("source_receipt_path") != config["predecessor"]["closed_receipt_path"]
        or reuse.get("source_receipt_commit") != config["predecessor"]["closed_commit"]
        or reuse.get("source_receipt_sha256") != config["predecessor"]["closed_receipt_sha256"]
        or reuse.get("record_identity_sha256") != config["predecessor"]["accepted_record_identity_sha256"]
    ):
        raise RuntimeError("accepted receipt does not exactly inherit predecessor attestation")
    zero_tests = [
        row
        for row in accepted.get("verification", {}).get("tests", [])
        if row.get("name") == "acceptance artifact source full-read or hash passes"
    ]
    if (
        len(zero_tests) != 1
        or zero_tests[0].get("passed") != 0
        or zero_tests[0].get("failed") != 0
    ):
        raise RuntimeError("accepted receipt lacks exact zero-read/zero-hash evidence")
    if (
        manifest.get("schema") != "jointbuildgs.c1_c2_qualitative_layout_correction_manifest.v1"
        or manifest.get("task_id") != TASK_ID
        or manifest.get("run_id") != config["run_id"]
        or manifest.get("status") != "LAYOUT_CORRECTED_AUTOMATED_CONTAINMENT_PASS"
        or manifest.get("scientific_verdict") is not None
        or manifest.get("predecessor") != config["predecessor"]
        or manifest.get("scope") != config["scope"]
        or len(manifest.get("examples", [])) != 7
    ):
        raise RuntimeError("external layout-correction manifest mismatch")
    labels = list(config["example_labels"])
    if [row.get("label") for row in manifest["examples"]] != labels:
        raise RuntimeError("external eligibility example order mismatch")
    for observed in manifest["examples"]:
        label = observed["label"]
        expected = config["expected_examples"][label]
        observed_tuple = [
            observed.get("stable_id"),
            observed.get("candidate"),
            observed.get("recorded_reference_cells"),
            observed.get("current_image_views"),
            observed.get("mvs_support_cells"),
            observed.get("c4_support_cells"),
            observed.get("reason"),
        ]
        if (
            observed_tuple != expected[:7]
            or observed.get("actual_compact_rows") != expected[2]
            or observed.get("bbox") != expected[7]
        ):
            raise RuntimeError(f"external exact eligibility record mismatch: {label}")
    if manifest["compact_source_read"] != {
        "bytes": 3785261,
        "sha256": "bf87736227ea3c28bc8f966f36e2498f786d2de420a732fa0bfebbb73664275a",
        "rows": 20520,
        "full_read_and_digest_passes": 1,
    }:
        raise RuntimeError("compact source natural-read record mismatch")
    output = manifest["output"]
    if (
        output.get("path") != config["result"]["figure_filename"]
        or int(output.get("bytes", 0)) <= 0
        or re.fullmatch(r"[0-9a-f]{64}", str(output.get("sha256", ""))) is None
        or output.get("post_write_digest_passes") != 1
    ):
        raise RuntimeError("new corrected PNG output record mismatch")

    technical = {
        "schema": "jointbuildgs.c1_c2_qualitative_layout_correction_technical_result.v1",
        "task_id": TASK_ID,
        "handoff_id": HANDOFF_ID,
        "source_commit": source_commit,
        "accepted_commit": accepted_commit,
        "accepted_receipt_path": ACCEPTED_REL,
        "acceptance_evidence": {
            "test_name": zero_tests[0]["name"],
            "accepted_source_full_reads": int(zero_tests[0]["passed"]),
            "accepted_source_full_file_hash_passes": int(zero_tests[0]["passed"]),
            "failed": int(zero_tests[0]["failed"]),
            "derived_from_receipt": True
        },
        "predecessor": config["predecessor"],
        "external_uri": config["result"]["external_uri"],
        "corrected_figure": output,
        "example_count": 7,
        "layout_validation": {
            "automated_text_containment": "PASS",
            "constrained_layout_used": False,
            "original_pixel_visual_review": "PENDING_RETURN_REVIEW"
        },
        "preserved_scientific_results": {
            "c1_g0_g1": [51, 51],
            "c2_g0_g1": [50, 50],
            "c2_full_partial_absent": [46, 4, 1],
            "g2_g3_g4_pass_usable": "PENDING"
        },
        "scope": config["scope"],
        "scientific_verdict": None,
    }
    technical_bytes = (json.dumps(technical, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    report = f"""# C1/C2 qualitative layout correction R5 v1

## Answer first

This bounded successor corrects only the seven-cell `199 -> 72` eligibility explainer layout.
It does not alter or recompute the predecessor's 51 C1/C2 building sheets, stage counts,
coverage values, building roster, metrics, or scientific interpretation.

- corrected figure: `{config['result']['external_uri']}{output['path']}`
- automated exact-text containment: `PASS`
- original-pixel visual review: `PENDING_RETURN_REVIEW`
- C1 G0/G1: `51/51`, `51/51`
- C2 G0/G1: `50/51`, `50/51`
- C2 full/partial/absent: `46/50`, `4/50`, `1/51`
- G2/G3/G4/PASS_usable: `PENDING`
- scientific_verdict: `null`

## No-repeat and scope

The exact predecessor 25-record attestation was inherited at acceptance with zero new
acceptance source hashes. Runtime mounted only the exact compact reference-cell CSV,
which was parsed and digested once in its natural rendering stream. R1/raw UAS,
`Images.zip`, `OPF.zip`, the R3 namespace, C1/C2 geometry, validation, and held-out
payloads were not mounted. Eligibility, metrics, reconstruction, Roofer, GS, C3, C4,
and C5 computations were all zero. New-output hashing was limited to one post-write
digest of the corrected PNG.

The superseded R1 offer, blocked R2/R3/R4 handoffs, prior blocked namespaces, and every prior packet,
Return, receipt, report, table, and manifest remain immutable. Final technical closure belongs to the separately
committed Return and 200/300 receipts after original-pixel inspection.
""".encode("utf-8")
    records = [
        _add_once(repo_root, REPORT_REL, report),
        _add_once(repo_root, TECHNICAL_REL, technical_bytes),
    ]
    dirty = set(_git(repo_root, "status", "--porcelain=v1", "--untracked-files=all").splitlines())
    expected_dirty = {f"?? {REPORT_REL}", f"?? {TECHNICAL_REL}"}
    if dirty != expected_dirty:
        raise RuntimeError(f"promotion wrote outside exact add-once allowlist: {sorted(dirty)}")
    return {"status": "PROMOTED_PENDING_ORIGINAL_PIXEL_REVIEW", "outputs": records, "scientific_verdict": None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-manifest", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--accepted-commit", required=True)
    args = parser.parse_args()
    result = promote(
        external_manifest=args.external_manifest,
        repo_root=args.repo_root,
        source_commit=args.source_commit,
        accepted_commit=args.accepted_commit,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

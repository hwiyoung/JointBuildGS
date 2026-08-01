#!/usr/bin/env python3
"""Validate R2B lineage, no-repeat behavior, and portable write scope."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.input_and_alignment.gate_s0.common_base_r2b.resolve_existing_common_base import (
    CONFIG_PATH,
    CROSSWALK_PATH,
    LEDGER_PATH,
    LINEAGE_PATH,
    MANIFEST_ROOT,
    READINESS_PATH,
    SCRIPT_PATH,
    build_operation_identity,
    canonical_json_bytes,
    normalize_lf,
)


ACCEPTED_COMMIT = "1a4fb69d03dc156e54bb789baa1c4fa56ef2ea58"
DOC_ROOT = Path("docs/research/preregistration/gate_s0/common_base_r2b")
DECISION_PATH = DOC_ROOT / "reuse_or_generation_decision_v1.md"
ISSUE_PATH = DOC_ROOT / "issue_log_v1.md"
RETURN_PATH = Path(
    "docs/handoffs/returns/P2_C2W_GATE_S0_COMMON_BASE_LINEAGE_R2B_RETURN_v1.md"
)
VALIDATOR_PATH = Path(
    "scripts/input_and_alignment/gate_s0/common_base_r2b/validate_r2b_lineage.py"
)
TEST_PATH = Path(
    "tests/input_and_alignment/gate_s0/common_base_r2b/test_r2b_lineage.py"
)
OUTPUT_MANIFEST_PATH = MANIFEST_ROOT / "output_manifest_v1.json"
INDEXED_OUTPUTS = [
    CONFIG_PATH,
    SCRIPT_PATH,
    VALIDATOR_PATH,
    TEST_PATH,
    LINEAGE_PATH,
    CROSSWALK_PATH,
    READINESS_PATH,
    LEDGER_PATH,
    DECISION_PATH,
    ISSUE_PATH,
    RETURN_PATH,
]
ALLOWED_PREFIXES = (
    "artifacts/manifests/handoffs/P2-W2C-GATE-S0-COMMON-BASE-LINEAGE-R2B-v1/",
    "artifacts/manifests/gate_s0/common_base_r2b/",
    "configs/input_and_alignment/gate_s0/common_base_r2b/",
    "docs/handoffs/returns/P2_C2W_GATE_S0_COMMON_BASE_LINEAGE_R2B_RETURN_v1.md",
    "docs/research/preregistration/gate_s0/common_base_r2b/",
    "scripts/input_and_alignment/gate_s0/common_base_r2b/",
    "tests/input_and_alignment/gate_s0/common_base_r2b/",
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def lf_bytes(path: Path) -> bytes:
    return normalize_lf(path.read_bytes())


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git(repo: Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo.resolve()}", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
    )
    return result.stdout


def zpaths(repo: Path, *args: str) -> set[str]:
    value = git(repo, *args, binary=True)
    assert isinstance(value, bytes)
    return {
        item.decode("utf-8", errors="surrogateescape")
        for item in value.split(b"\0")
        if item
    }


def portable_changed_paths(repo: Path, base: str = ACCEPTED_COMMIT) -> set[str]:
    """Return semantic changes while ignoring a working-tree-only LF/CRLF rewrite."""
    changed = zpaths(repo, "diff", "--name-only", "-z", base, "HEAD", "--")
    changed |= zpaths(repo, "diff", "--cached", "--name-only", "-z", "--")
    unstaged = zpaths(repo, "diff", "--name-only", "-z", "--")
    for relative in unstaged:
        path = repo / relative
        if not path.is_file():
            changed.add(relative)
            continue
        try:
            head_value = git(repo, "show", f"HEAD:{relative}", binary=True)
        except subprocess.CalledProcessError:
            changed.add(relative)
            continue
        assert isinstance(head_value, bytes)
        if normalize_lf(head_value) != normalize_lf(path.read_bytes()):
            changed.add(relative)
    changed |= zpaths(repo, "ls-files", "--others", "--exclude-standard", "-z")
    return changed


def validate_scope(repo: Path, errors: list[str]) -> None:
    for path in sorted(portable_changed_paths(repo)):
        if not any(path == prefix or path.startswith(prefix) for prefix in ALLOWED_PREFIXES):
            errors.append(f"path outside exact R2B write scope: {path}")


def output_commit_for_path(repo: Path, path: Path) -> str | None:
    result = git(repo, "log", "--diff-filter=A", "--format=%H", "--", path.as_posix())
    assert isinstance(result, str)
    commits = [line for line in result.splitlines() if line]
    return commits[0] if len(commits) == 1 else None


def build_output_manifest(repo: Path = Path(".")) -> dict[str, Any]:
    missing = [path.as_posix() for path in INDEXED_OUTPUTS if not (repo / path).is_file()]
    if missing:
        raise RuntimeError(f"missing R2B indexed output: {missing}")
    ledger = read_json(repo / LEDGER_PATH)
    return {
        "schema": "jointbuildgs.gate_s0_common_base_r2b_output_manifest.v1",
        "handoff_id": "P2-W2C-GATE-S0-COMMON-BASE-LINEAGE-R2B-v1",
        "task_id": "P2-GATE-S0-COMMON-BASE-LINEAGE-R2B-v1",
        "input_commit": ACCEPTED_COMMIT,
        "output_commit": "SELF",
        "proposed_status": "BLOCKED_FOR_GATE_S0_TECHNICAL_AND_HUMAN_FREEZE",
        "artifact_verification_level": "git_only",
        "operation_id": ledger["operation_identity"]["operation_id"],
        "external_payload_read_bytes": ledger["first_invocation"][
            "external_payload_read_bytes"
        ],
        "external_payload_hashed_bytes": ledger["first_invocation"][
            "external_payload_hashed_bytes"
        ],
        "files": [
            {
                "path": path.as_posix(),
                "bytes": len(lf_bytes(repo / path)),
                "sha256": sha256_bytes(lf_bytes(repo / path)),
                "hash_scope": "Git LF-canonical bytes",
            }
            for path in INDEXED_OUTPUTS
        ],
        "scientific_verdict": None,
    }


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate(repo: Path = Path(".")) -> list[str]:
    errors: list[str] = []
    config = read_json(repo / CONFIG_PATH)
    lineage = read_json(repo / LINEAGE_PATH)
    crosswalk = read_json(repo / CROSSWALK_PATH)
    ledger = read_json(repo / LEDGER_PATH)
    manifest = read_json(repo / OUTPUT_MANIFEST_PATH)
    with (repo / READINESS_PATH).open(encoding="utf-8", newline="") as stream:
        readiness = list(csv.DictReader(stream))

    require(config["guards"]["performance_authority"] == "NONE", "performance authority differs", errors)
    for guard in (
        "generate_dense_mvs", "generate_depth", "generate_normal",
        "generate_confidence", "generate_segmentation", "generate_gravity",
        "rehash_large_payloads", "held_out_access", "fusion_w1_access",
        "r_ext_access", "overwrite_existing_payloads", "move_existing_payloads",
        "delete_existing_payloads", "primary_c5_promotion", "gate_s0_approval",
    ):
        require(config["guards"][guard] is False, f"forbidden guard enabled: {guard}", errors)

    require(lineage["source_membership"]["image_members"] == 962, "source image count differs", errors)
    require(lineage["source_membership"]["included_pairs"] == 937, "source pair count differs", errors)
    require(lineage["source_membership"]["excluded_no_pose"] == 25, "source exclusion count differs", errors)
    require(all(item["equals_exact_source"] for item in lineage["member_set_checks"].values()), "one or more exact-937 set checks failed", errors)
    require(lineage["producer_lineage"]["actual_script_containing_commit"] == "252ea1dce31acec53481876137941192fea9a9bc", "actual P0 producer commit differs", errors)
    require(lineage["producer_lineage"]["script_git_blob"] == "bf5cd4dac48b3ee622e0e82a1e00063eaa00c097", "actual P0 producer blob differs", errors)
    require(lineage["large_payload_full_read_bytes"] == 0, "large payload was read", errors)
    require(lineage["large_payload_full_hashed_bytes"] == 0, "large payload was hashed", errors)
    require(lineage["generated_derivatives"] == [], "a derivative was generated", errors)
    require(lineage["future_single_pass_hash"]["exact_byte_ceiling"] == 986_484_109, "future hash ceiling differs", errors)

    require(crosswalk["member_count"] == 937, "crosswalk member count differs", errors)
    require(len(crosswalk["rows"]) == 937, "crosswalk row count differs", errors)
    require(len({row["basename"] for row in crosswalk["rows"]}) == 937, "crosswalk basenames are not unique", errors)
    require(len({row["source_camera_uid"] for row in crosswalk["rows"]}) == 937, "source camera UIDs are not unique", errors)
    require(len({row["colmap_image_id"] for row in crosswalk["rows"]}) == 937, "COLMAP image IDs are not unique", errors)
    for row in crosswalk["rows"]:
        require(row["colmap_camera_model_id"] == 1, "COLMAP camera model ID differs", errors)
        require(all(row[key] is True for key in (
            "retained_image", "patch_match_member", "fusion_member",
            "geometric_depth", "photometric_depth", "geometric_normal",
            "photometric_normal"
        )), f"crosswalk component membership differs: {row['basename']}", errors)

    statuses = {row["component"]: row["gate_readiness"] for row in readiness}
    require(statuses == {
        "source_membership": "READY",
        "sfm_sparse": "PARTIAL",
        "dense_mvs": "PARTIAL",
        "depth": "PARTIAL",
        "normal": "PARTIAL",
        "confidence": "MISSING",
        "segmentation": "MISSING",
        "gravity": "MISSING",
    }, f"component readiness differs: {statuses}", errors)

    expected_identity = build_operation_identity(
        repo / CONFIG_PATH, repo / SCRIPT_PATH, repo
    )
    require(ledger["status"] == "COMPLETED", "ledger is not completed", errors)
    require(ledger["operation_identity"] == expected_identity, "operation identity drifted", errors)
    require(ledger["completed_lookup_precedes_external_access"] is True, "completed lookup ordering differs", errors)
    require(ledger["completed_ledger_overwrite_allowed"] is False, "completed ledger overwrite was enabled", errors)
    first = ledger["first_invocation"]
    require(first["external_payload_read_bytes"] == 0, "first run read payload bytes", errors)
    require(first["external_payload_hashed_bytes"] == 0, "first run hashed payload bytes", errors)
    require(first["external_metadata_read_bytes"] == 564_247, "bounded metadata read bytes differ", errors)
    require(first["external_metadata_hashed_bytes"] == 564_247, "bounded metadata hash bytes differ", errors)
    require(first["external_directory_entries_statted"] >= 4_698, "retained metadata stat count too small", errors)
    second = ledger["second_invocation_contract"]
    require(all(value == 0 for value in second.values()), "second invocation is not a zero-byte no-op", errors)
    require(ledger["forbidden_full_hashes_performed"] == [], "forbidden full hash recorded", errors)

    containing = output_commit_for_path(repo, SCRIPT_PATH)
    if containing is not None:
        blob = git(repo, "rev-parse", f"{containing}:{SCRIPT_PATH.as_posix()}")
        assert isinstance(blob, str)
        require(blob.strip() == expected_identity["executable"]["git_blob_oid"], "SELF executable blob/commit binding differs", errors)
        manifest_commit = output_commit_for_path(repo, OUTPUT_MANIFEST_PATH)
        require(manifest_commit in (None, containing), "output manifest not introduced in output commit", errors)

    require(manifest == build_output_manifest(repo), "LF-canonical output manifest is stale", errors)
    for path in (DECISION_PATH, ISSUE_PATH, RETURN_PATH):
        text = (repo / path).read_text(encoding="utf-8")
        require("scientific_verdict: null" in text, f"null scientific verdict missing: {path}", errors)
        require("P2 performance: PROHIBITED" in text, f"performance prohibition missing: {path}", errors)
    validate_scope(repo, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--write-output-manifest", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    if args.write_output_manifest:
        path = repo / OUTPUT_MANIFEST_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.write_bytes(canonical_json_bytes(build_output_manifest(repo)))
        else:
            with path.open("xb") as stream:
                stream.write(canonical_json_bytes(build_output_manifest(repo)))
    errors = validate(repo)
    if errors:
        print("Gate S0 R2B lineage evidence: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Gate S0 R2B lineage evidence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

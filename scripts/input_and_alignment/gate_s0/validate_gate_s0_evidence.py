#!/usr/bin/env python3
"""Validate the compact Gate S0 evidence package without scientific verdicts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


DOC_ROOT = Path("docs/research/preregistration/gate_s0")
MANIFEST_ROOT = Path("artifacts/manifests/gate_s0")
OUTPUT_MANIFEST = MANIFEST_ROOT / "gate_s0_output_manifest_v1.json"
REQUIRED_OUTPUTS = [
    DOC_ROOT / "GATE_S0_EVIDENCE_REPORT_v1.md",
    DOC_ROOT / "gate_s0_input_manifest_v1.json",
    DOC_ROOT / "gate_s0_image_camera_ledger_v1.csv",
    DOC_ROOT / "gate_s0_condition_readiness_v1.csv",
    DOC_ROOT / "gate_s0_eligibility_funnel_v1.csv",
    DOC_ROOT / "gate_s0_cost_bounds_v1.csv",
    DOC_ROOT / "gate_s0_split_proposal_v1.json",
    DOC_ROOT / "issues.md",
    Path("docs/handoffs/returns/P2_C2W_GATE_S0_PREPARATION_RETURN_v1.md"),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def build_output_manifest() -> dict[str, Any]:
    missing = [str(path) for path in REQUIRED_OUTPUTS if not path.is_file()]
    if missing:
        raise RuntimeError(f"cannot index missing required outputs: {missing}")
    return {
        "schema": "jointbuildgs.gate_s0_output_manifest.v1",
        "handoff_id": "P2-W2C-GATE-S0-PREP-v1",
        "input_commit": "9197de13725e6caef8b71887096eeeaf8c3f1da8",
        "output_commit": "SELF",
        "proposed_status": "BLOCKED_FOR_GATE_S0_REVIEW",
        "scientific_verdict": None,
        "files": [
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in REQUIRED_OUTPUTS
        ],
    }


def write_output_manifest() -> None:
    payload = build_output_manifest()
    OUTPUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MANIFEST.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def recompute_lod1_inventory(root: Path, max_depth: int) -> tuple[int, int, str, list[str], list[str]]:
    relative_scope = Path("phase-payloads/p0-audit/data/raw")
    search_root = root / relative_scope
    inventory: list[tuple[str, int]] = []
    candidates: list[str] = []
    lod1_matches: list[str] = []
    for path in sorted(search_root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative_inside = path.relative_to(search_root)
        if len(relative_inside.parts) > max_depth:
            continue
        relative = (relative_scope / relative_inside).as_posix()
        size = path.stat().st_size
        inventory.append((relative, size))
        name_lower = path.name.lower()
        if "lod1" in name_lower:
            lod1_matches.append(relative)
        if "lod1" in name_lower or path.suffix.lower() in {".gml", ".cityjson", ".jsonl"}:
            candidates.append(relative)
    inventory_bytes = "".join(f"{path}|{size}\n" for path, size in inventory).encode("utf-8")
    return (
        len(inventory),
        len(inventory_bytes),
        hashlib.sha256(inventory_bytes).hexdigest(),
        candidates,
        lod1_matches,
    )


def validate(artifact_root: Path) -> list[str]:
    errors: list[str] = []
    for path in [*REQUIRED_OUTPUTS, OUTPUT_MANIFEST]:
        require(path.is_file() and path.stat().st_size > 0, f"missing/empty: {path}", errors)
    if errors:
        return errors

    output_manifest = read_json(OUTPUT_MANIFEST)
    require(output_manifest["scientific_verdict"] is None, "output verdict must be null", errors)
    require(
        output_manifest["proposed_status"] == "BLOCKED_FOR_GATE_S0_REVIEW",
        "output status mismatch",
        errors,
    )
    indexed = {item["path"]: item for item in output_manifest["files"]}
    require(set(indexed) == {str(path) for path in REQUIRED_OUTPUTS}, "output index paths mismatch", errors)
    for path in REQUIRED_OUTPUTS:
        item = indexed.get(str(path), {})
        require(item.get("bytes") == path.stat().st_size, f"output bytes mismatch: {path}", errors)
        require(item.get("sha256") == sha256_file(path), f"output SHA mismatch: {path}", errors)

    ledger_path = DOC_ROOT / "gate_s0_image_camera_ledger_v1.csv"
    ledger = read_csv(ledger_path)
    require(len(ledger) == 962, "ledger must contain 962 rows", errors)
    require(len({row["basename"] for row in ledger}) == 962, "ledger basenames not unique", errors)
    require(ledger == sorted(ledger, key=lambda row: row["basename"]), "ledger not sorted", errors)
    counts = Counter(row["status"] for row in ledger)
    require(counts == {"INCLUDED": 937, "EXCLUDED": 25}, "ledger inclusion counts mismatch", errors)
    require(
        all(row["image_in_zip"] == "true" and row["input_capture_present"] == "true" for row in ledger),
        "ledger source membership mismatch",
        errors,
    )
    require(
        all(
            row["exclusion_reason"] == "NO_CALIBRATED_CAMERA_POSE_IN_OPF"
            for row in ledger
            if row["status"] == "EXCLUDED"
        ),
        "ledger exclusion reason mismatch",
        errors,
    )
    require(
        sha256_file(ledger_path) == "8c1e89040869e800c34ebd8a06c2b5185524330fc5d56e594b41686173c465b0",
        "ledger canonical SHA mismatch",
        errors,
    )

    image_inventory = read_csv(MANIFEST_ROOT / "gate_s0_image_member_inventory_v1.csv")
    require(len(image_inventory) == 962, "image member inventory count mismatch", errors)
    require(len({row["basename"] for row in image_inventory}) == 962, "image member inventory duplicate", errors)
    require(all(len(row["sha256"]) == 64 for row in image_inventory), "image member SHA missing", errors)

    inputs = read_json(DOC_ROOT / "gate_s0_input_manifest_v1.json")
    require(inputs["scientific_verdict"] is None, "input manifest verdict must be null", errors)
    require(inputs["verification"]["level"] == "artifact_verified", "input verification level mismatch", errors)
    require(inputs["verification"]["exact_file_count"] == 11, "exact file count mismatch", errors)
    require(inputs["verification"]["exact_total_bytes"] == 15743666051, "exact byte total mismatch", errors)
    require(len(inputs["files"]) == 11, "input files length mismatch", errors)
    require(
        all(item["verification_method"] == "sha256_rehash" and item["verified_by"] == "experiment_host" for item in inputs["files"]),
        "input live verification fields mismatch",
        errors,
    )
    require(inputs["c1_source_proposal"]["selection"] == "NADIR_ONLY", "C1 proposal mismatch", errors)
    require(inputs["c1_source_proposal"]["status"] == "PARTIAL", "C1 must remain partial", errors)
    require(inputs["lod1_search"]["status"] == "MISSING", "LoD1 must remain missing", errors)
    require(inputs["lod1_search"]["matches"] == [], "LoD1 matches must be empty", errors)
    require("Do not simplify" in inputs["lod1_search"]["prohibited_substitute"], "LoD2 guard missing", errors)
    search_path = Path(inputs["lod1_search"]["search_evidence_path"])
    require(search_path.is_file(), "LoD1 search evidence missing", errors)
    require(inputs["lod1_search"]["search_evidence_sha256"] == sha256_file(search_path), "LoD1 search evidence SHA mismatch", errors)
    search = read_json(search_path)
    require(search["status"] == "MISSING" and search["lod1_matches"] == [], "LoD1 search result mismatch", errors)
    require(all(not item["name_contains_lod1"] for item in search["candidate_matches"]), "LoD1 candidate unexpectedly present", errors)
    try:
        count, size, digest, candidates, lod1_matches = recompute_lod1_inventory(artifact_root, search["max_depth"])
    except OSError as exc:
        errors.append(f"cannot reproduce LoD1 search: {exc}")
    else:
        require(count == search["inventory_entry_count"], "LoD1 inventory count mismatch", errors)
        require(size == search["inventory_bytes"], "LoD1 inventory bytes mismatch", errors)
        require(digest == search["inventory_sha256"], "LoD1 inventory SHA mismatch", errors)
        require(candidates == [item["relative_path"] for item in search["candidate_matches"]], "LoD1 candidate inventory mismatch", errors)
        require(lod1_matches == search["lod1_matches"], "LoD1 live result mismatch", errors)
    require(inputs["image_camera_ledger"]["c2_same_base_status"] == "PARTIAL", "C2 same-base overclaim", errors)

    records = read_json(MANIFEST_ROOT / "gate_s0_live_artifact_records_v1.json")
    require(records["verification_level"] == "artifact_verified", "artifact records level mismatch", errors)
    require(len(records["records"]) == 11, "artifact records count mismatch", errors)
    input_tuples = {(item["uri"], item["bytes"], item["sha256"]) for item in inputs["files"]}
    record_tuples = {(item["uri"], item["bytes"], item["sha256"]) for item in records["records"]}
    require(input_tuples == record_tuples, "artifact records differ from input manifest", errors)

    readiness = read_csv(DOC_ROOT / "gate_s0_condition_readiness_v1.csv")
    status_by_key = {(row["condition"], row["field"]): row["status"] for row in readiness}
    require(status_by_key.get(("C5_GS_lod1_prior", "independent_lod1")) == "MISSING", "C5 readiness mismatch", errors)
    require(status_by_key.get(("ALL", "E_paired")) == "UNKNOWN", "E_paired readiness mismatch", errors)
    require(status_by_key.get(("ALL", "CityGML_cjval_val3dity")) == "MISSING", "tool readiness mismatch", errors)

    funnel = read_csv(DOC_ROOT / "gate_s0_eligibility_funnel_v1.csv")
    require(all(row["held_out_accessed"] == "false" for row in funnel), "held-out access flag mismatch", errors)
    e_paired = next(row for row in funnel if row["stage"] == "E_paired")
    require(e_paired["status"] == "UNKNOWN" and not e_paired["count"], "E_paired must not be fabricated", errors)

    split = read_json(DOC_ROOT / "gate_s0_split_proposal_v1.json")
    require(split["scientific_verdict"] is None, "split verdict must be null", errors)
    require(split["preferred_mode"] == "EXHAUSTIVE_PARTITION", "split preference mismatch", errors)
    require(split["status"] == "PROPOSAL_NOT_FREEZEABLE", "split status mismatch", errors)
    require(split["held_out_accessed"] is False, "held-out must remain unopened", errors)
    for key in ("U_target_ids", "E_paired_ids", "development_ids", "validation_ids", "held_out_ids"):
        require(split[key] == [], f"split IDs must remain empty: {key}", errors)

    costs = read_csv(DOC_ROOT / "gate_s0_cost_bounds_v1.csv")
    require(len(costs) == 5, "cost row count mismatch", errors)
    require(all(row["held_out_accessed"] == "false" for row in costs), "cost evidence accessed held-out", errors)
    require(all(row["runtime_bound"] == "UNKNOWN" for row in costs), "runtime overclaim", errors)

    report = (DOC_ROOT / "GATE_S0_EVIDENCE_REPORT_v1.md").read_text(encoding="utf-8")
    issues = (DOC_ROOT / "issues.md").read_text(encoding="utf-8")
    returned = Path("docs/handoffs/returns/P2_C2W_GATE_S0_PREPARATION_RETURN_v1.md").read_text(encoding="utf-8")
    for label, text in (("report", report), ("issues", issues), ("return", returned)):
        require("scientific_verdict: null" in text, f"{label} null verdict marker missing", errors)
        require("BLOCKED_FOR_GATE_S0_REVIEW" in text, f"{label} blocked review status missing", errors)
    require("no joint-prior synergy claim" in report, "synergy limitation missing", errors)
    require("output_commit: `SELF`" in returned, "Return SELF binding missing", errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-output-manifest", action="store_true")
    parser.add_argument("--artifact-root", default="/artifacts/JointBuildGS")
    args = parser.parse_args()
    if args.write_output_manifest:
        write_output_manifest()
    errors = validate(Path(args.artifact_root).resolve())
    if errors:
        print("Gate S0 evidence: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Gate S0 evidence: PASS (status=BLOCKED_FOR_GATE_S0_REVIEW, scientific_verdict=null)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

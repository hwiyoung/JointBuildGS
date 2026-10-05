"""Apply the verified native evaluator only after all matched candidate gates pass."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.phd.wu_vallet_regions_v4 import evaluate_regions as engine


POLICY_KEYS = ("view_selection", "image_mesh", "als_mesh", "context_rule",
               "distance_tolerance_m", "area_sensitivity_m2", "primary_area_m2",
               "changed_only_sensitivity_area_m2", "working_crs", "frame")
ARM_KEYS = ("name", "direction_mode", "tolerance_m", "small_region_area_m2", "raw_single_retained")


def canonical_source(path):
    text = str(path)
    for owner in ("scripts", "src", "tests"):
        token = "/" + owner + "/"
        if token in text:
            return owner + "/" + text.split(token, 1)[1]
    return text


def canonical_hashes(values):
    result = {canonical_source(path): value for path, value in values.items()}
    if len(result) != len(values):
        raise ValueError("Duplicate canonical implementation path")
    return result


def matched_gate(config):
    cfg = json.loads(config.read_text())
    policy_path = Path(cfg["matched_protocol_config"])
    policy = json.loads(policy_path.read_text())
    shared = {key: policy[key] for key in POLICY_KEYS}
    if [r["id"] for r in cfg["regions"]] != ["P1", "P2", "P3"]:
        raise ValueError("All three matched regions must be frozen together")
    if "raw_reference" in cfg or any("frozen_reference_npz" not in r for r in cfg["regions"]):
        raise ValueError("Matched evaluation may read exact frozen reference copies only")
    if shared["view_selection"]["decision_count"] != "ALL_FROZEN_REGIONAL_VIEWS":
        raise ValueError("Every region must audit its entire frozen view set")
    audit_path = Path(cfg["core_audit_receipt"])
    audit = json.loads(audit_path.read_text())
    if audit["status"] != "PASS" or audit["source_unchanged"] is not True or audit["reference_accessed"] is not False:
        raise ValueError("Completed source-stable reference-free core audit required")
    audit_hashes = canonical_hashes(audit["input_hashes"])
    rows, signatures, implementations, preparation_implementations = [], [], [], []
    for region in cfg["regions"]:
        rid = region["id"]
        root = Path(region["input_root"])
        protocol_path = root / "protocol_receipt.json"
        protocol = json.loads(protocol_path.read_text())
        if protocol["shared_policy"] != shared or protocol.get("reference_accessed") is not False:
            raise ValueError(f"Shared preparation policy differs: {rid}")
        if protocol["common_config_sha256"] != engine.sha(policy_path):
            raise ValueError(f"Preparation did not use the exact common config: {rid}")
        preparation_implementations.append(canonical_hashes(protocol["source_hashes"]))
        receipt_path = root / "receipt.json"
        receipt = json.loads(receipt_path.read_text())
        if receipt["reference_accessed"] is not False:
            raise ValueError("Reference entered candidate generation")
        for filename, expected in receipt["outputs"].items():
            if engine.sha(root / filename) != expected:
                raise ValueError(f"Input receipt payload mismatch: {rid}/{filename}")
        expected_n = policy["regions"][rid]["frozen_view_count"]
        if receipt["view_count"] != expected_n or receipt["decision_view_count"] != expected_n:
            raise ValueError(f"Only a subset of frozen regional views was audited: {rid}")
        selection = json.loads(Path(region["view_json"]).read_text())
        resolved = dict(shared["view_selection"], decision_count=expected_n)
        if selection["selection"] != resolved:
            raise ValueError(f"Selected master policy mismatch: {rid}")
        candidate_path = Path(region["update_root"]) / region["candidate_receipt"]
        candidate = json.loads(candidate_path.read_text())
        implementations.append(canonical_hashes(candidate["implementation_hashes"]))
        for source, expected in implementations[-1].items():
            if engine.sha(source) != expected:
                raise ValueError(f"Candidate implementation differs from evaluation snapshot: {rid}/{source}")
            if audit_hashes.get(source) != expected:
                raise ValueError(f"Candidate implementation differs from tested core source: {rid}/{source}")
        update_config = json.loads((Path(region["update_root"]) / "config.json").read_text())
        if {key: update_config[key] for key in POLICY_KEYS} != shared:
            raise ValueError(f"Update policy differs from common preparation policy: {rid}")
        signature = [{key: arm[key] for key in ARM_KEYS} for arm in candidate["arms"]]
        signatures.append(signature)
        if candidate["reference_accessed"] is not False or candidate["image_id"] != selection["image_id"]:
            raise ValueError(f"Update master/reference identity mismatch: {rid}")
        domain = policy["regions"][rid]["domain"]
        if candidate["domain"] != domain or region["domain"] != {
                "bbox_min": [domain[k][0] for k in "xyz"], "bbox_max": [domain[k][1] for k in "xyz"]}:
            raise ValueError(f"Input, update, and evaluation prisms differ: {rid}")
        rows.append(dict(id=rid, image_id=selection["image_id"], frozen_views=expected_n,
                         native_source_sha256=engine.sha(region["native_npz"]),
                         common_source_sha256=engine.sha(region["common_npz"]),
                         input_receipt_sha256=engine.sha(receipt_path),
                         input_protocol_sha256=engine.sha(protocol_path),
                         candidate_receipt_sha256=engine.sha(candidate_path),
                         core_policy=candidate["matched_core_policy"],
                         reference_sha256=region["frozen_reference_sha256"],
                         input_reference_accessed=False, update_reference_accessed=False))
    if any(signature != signatures[0] for signature in signatures[1:]):
        raise ValueError("Region-specific direction, tolerance, filter, or SINGLE policy detected")
    if any(item != implementations[0] for item in implementations[1:]):
        raise ValueError("Three regions did not execute byte-identical update implementations")
    if any(item != preparation_implementations[0] for item in preparation_implementations[1:]):
        raise ValueError("Three regions did not execute byte-identical preparation implementations")
    return dict(status="PASS_MATCHED_THREE_REGION_PROTOCOL_BEFORE_REFERENCE", scientific_verdict=None,
                reference_accessed=False, common_config_sha256=engine.sha(policy_path), shared_policy=shared,
                arm_policy=signatures[0], regions=rows, update_implementation_hashes=implementations[0],
                preparation_implementation_hashes=preparation_implementations[0],
                core_audit=dict(path=str(audit_path), sha256=engine.sha(audit_path), tests_run=audit["tests_run"],
                                status="PASS", executed_update_sources_match_tested_sources=True),
                evaluation_policy={key: cfg[key] for key in ("xy_cell_m", "distance_thresholds_m", "section_half_width_m", "frame")},
                main_comparison_methods=["ALS_before", "Image_before", "Naive_union", *cfg["regions"][0]["method_arms"]],
                context_only_methods=["MVS_context"],
                source_membership_validation="engine.verify_region checks every arm against the same old/new source rows before reference access")


def run(config, output):
    gate = matched_gate(config)
    original = engine.stream_reference

    def guarded_reference(cfg, regions):
        # Engine has now verified every native source/arm and persisted its
        # PRE_REFERENCE_CANDIDATE_SEAL. The policy gate is also persisted before
        # the first reference metadata or point payload is opened.
        if regions:
            raise ValueError("Raw reference reading is prohibited in matched v5")
        engine.write(output / "MATCHED_PROTOCOL.json", gate)
        return original(cfg, regions)

    engine.stream_reference = guarded_reference
    try:
        engine.run(config, output)
    finally:
        engine.stream_reference = original


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.config, args.output)

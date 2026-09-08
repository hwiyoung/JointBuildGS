"""Verify stage-audit lineage against the existing sealed SRDM evaluation."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--artifact-root", required=True)
    p.add_argument("--audit", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    root = Path(args.artifact_root)
    audit_path = Path(args.audit)
    audit = json.loads(audit_path.read_text())
    cfg = json.loads(Path("configs/phd/srdm_p1p2p3_v1/evaluation_v1.json").read_text())
    task = root / "phase-payloads/phd/srdm_p1p2p3_v1/PHD-SRDM-P1P2P3-v1"
    seal = json.loads((task / "run/CANDIDATE_SEAL.json").read_text())
    verified = {}
    for region in cfg["regions"]:
        rid = region["id"]
        item = audit["regions"][rid]
        assert item["inputs"]["reference"]["sha256"] == region["frozen_reference_sha256"]
        for key in ("pair", "decision", "SRDM_FILTER_OFF", "SRDM_NATIVE"):
            source = Path(item["inputs"][key]["path"])
            relative = str(source.relative_to(task / "run"))
            expected = seal["outputs"][relative]
            expected = expected["sha256"] if isinstance(expected, dict) else expected
            assert item["inputs"][key]["sha256"] == expected
        with np.load(task / "run" / rid / "decision.npz", allow_pickle=False) as decision, np.load(task / "run" / rid / "pair.npz", allow_pickle=False) as pair, np.load(task / "evaluation" / rid / "als_decision_reference.npz", allow_pickle=False) as old:
            assert all(np.array_equal(old[key], decision[key]) for key in ("keep", "rejected", "unassessed"))
            assert np.array_equal(old["in_roi"], pair["als_in_roi"])
        verified[rid] = {"reference_matches_frozen_hash": True, "candidate_inputs_match_original_seal": True,
                         "evaluation_masks_match_saved_decisions": True, "evaluation_roi_matches_input_roi": True}
    assert all(sha(audit_path.parent / name) == expected for name, expected in audit["output_hashes"].items())
    result = {"task_id": audit["task_id"], "scientific_verdict": None, "status": "PASS_LINEAGE_AND_SAVED_OUTPUTS",
              "audit_sha256": sha(audit_path), "regions": verified, "output_hashes_verified": len(audit["output_hashes"]),
              "matching_runs": 0, "training_runs": 0, "verifier_sha256": sha(__file__)}
    with Path(args.output).open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()

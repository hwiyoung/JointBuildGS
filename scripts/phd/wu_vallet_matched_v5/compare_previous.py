"""Post-evaluation paired diagnostic; never feeds any candidate decisions."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(artifacts, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker required")
    phd = artifacts / "phase-payloads/phd"
    b4, b5 = phd / "wu_vallet_regions_v4", phd / "wu_vallet_matched_v5"
    prior = {
        "P1": (b4 / "PHD-WU-VALLET-P1-VISIBLE-UPDATE-v4/run", b4 / "PHD-WU-VALLET-VISIBLE-EVALUATION-v4/run/P1_visible/evaluation.json"),
        "P2": (b4 / "PHD-WU-VALLET-P2-VISIBLE-UPDATE-v4/run", b4 / "PHD-WU-VALLET-VISIBLE-EVALUATION-v4/run/P2_visible/evaluation.json"),
        "P3": (phd / "wu_vallet_p3_v3/PHD-WU-VALLET-P3-FILTER-v3/run", b4 / "PHD-WU-VALLET-REGIONS-EVALUATION-v4/run/P3/evaluation.json"),
    }
    rows, inputs = [], {}
    for region, (old_root, old_eval_path) in prior.items():
        new_root = b5 / f"PHD-WU-VALLET-{region}-UPDATE-v5/run"
        new_eval_path = b5 / f"PHD-WU-VALLET-MATCHED-EVALUATION-v5/run/{region}/evaluation.json"
        old_payload = old_root / "corrected_area1/updated_points.npz"
        new_payload = new_root / "corrected_area1/updated_points.npz"
        for path in (old_eval_path, new_eval_path, old_payload, new_payload):
            inputs[str(path)] = sha(path)
        with np.load(old_payload) as before, np.load(new_payload) as after:
            equality = {key: bool(np.array_equal(before[key], after[key])) for key in
                        ("updated_points", "updated_source", "old_keep_mask", "new_keep_mask", "old_vertex_status", "new_vertex_status")}
            row = dict(region=region, original_comparison_array_equality=equality,
                       before_points=len(before["updated_points"]), after_points=len(after["updated_points"]))
        selected = json.loads((new_root / "selected_master.json").read_text())
        row["selected_image_id"] = selected["image_id"]
        old_eval, new_eval = json.loads(old_eval_path.read_text()), json.loads(new_eval_path.read_text())
        row["before_methods"] = old_eval["methods"]
        row["after_methods"] = new_eval["methods"]
        rows.append(row)
    output.mkdir(parents=True, exist_ok=False)
    result = dict(status="MATCHED_V5_PREVIOUS_OUTPUT_COMPARISON_COMPLETE", scientific_verdict=None,
                  reference_role="evaluation and posthoc diagnostic only", candidate_outputs_modified=False,
                  input_hashes=inputs, regions=rows)
    (output / "receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "regions": [{k: v for k, v in row.items() if k not in ("before_methods", "after_methods")} for row in rows]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.artifacts, args.output)

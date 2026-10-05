"""Reproducible known-truth scalar probe, no real P2/reference data input."""

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
import scipy

from src.phd.p2_ab_v3.joint_error import judge, truth_membership, variant


SOURCE_FILES = [
    "src/phd/p2_ab_v3/joint_error.py",
    "scripts/phd/p2_ab_v3/a_joint_error_probe.py",
    "configs/phd/p2_ab_v3/a_joint_error_probe_v1.json",
    "tests/phd/test_p2_ab_v3_joint_error.py",
    "docs/experiments/phd/p2_ab_v3/A_CONCRETE_METHOD_ko_v3.md",
]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_case(config, case):
    """Generate observations once; all method variants receive these bytes."""
    problem = deepcopy(config["base_problem"])
    problem.update(deepcopy(case.get("problem", {})))
    problem["bounds"].update(deepcopy(case.get("bounds", {})))
    truth = deepcopy(case["truth"])
    truth["e_I"] = truth["eta"] + truth["nu"]
    problem["observations"] = {
        "photo": truth["x"] + truth["c"] + truth["eta"],
        "mvs": truth["x"] + truth["c"] + truth["e_I"],
        "prior": truth["x"] + problem.get("prior_shared_loading", 0) * truth["c"]
                 - truth["delta"] - truth["Delta"] + truth["e_P"],
    }
    for name in case.get("missing", []):
        problem["observations"][name] = None
    return problem, truth


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise RuntimeError("New empty output directory required; existing runs are immutable")
    config = json.loads(Path(args.config).read_text())
    if config["input_kind"] != "KNOWN_TRUTH_SYNTHETIC_SCALAR_NORMAL_COMPONENT":
        raise ValueError("This driver only accepts its declared synthetic input schema")
    head = subprocess.check_output(["git", "-c", "safe.directory=*", "rev-parse", "HEAD"], text=True).strip()
    sources = {f: sha256(f) for f in SOURCE_FILES}
    snapshot = output / "source_snapshot"
    for f in SOURCE_FILES:
        target = snapshot / f
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(Path(f).read_bytes())
    metadata = {"started_utc": datetime.now(timezone.utc).isoformat(), "git_head": head,
                "source_sha256": sources, "config_sha256": sha256(args.config),
                "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
                "docker_image_id": os.environ.get("JBGS_PROBE_IMAGE_ID"), "argv": sys.argv,
                "scientific_verdict": None, "crs": config["crs"],
                "input_provenance": "Generated solely from frozen config latent truth; no P2/UAS/LoD2 read",
                "numeric_claim": "Floating-point HiGHS extrema, not rigorous interval certificates"}
    (output / "execution_setup.json").write_text(json.dumps(metadata, indent=2) + "\n")
    rows, inputs = [], []
    for case in config["cases"]:
        base, truth = build_case(config, case)
        inputs.append({"case_id": case["case_id"], "problem": base, "evaluation_truth": truth})
        for method in config["methods"]:
            problem = variant(base, method)
            decision = judge(problem)
            # Truth is first consumed here, after the complete decision.
            selected = decision["selected_value_m"]
            true_error = abs(selected - truth["x"]) if selected is not None else None
            evaluation = {"truth_membership": truth_membership(problem, truth),
                          "selected_true_error_m": true_error,
                          "false_adoption": (true_error > problem["tolerance_m"]) if true_error is not None else None,
                          "candidate_true_error_m": {c["candidate_id"]: abs(c["value_m"] - truth["x"])
                                                     for c in decision["candidates"]}}
            rows.append({"case_id": case["case_id"], "method": method, "purpose": case["purpose"],
                         "decision": decision, "evaluation_only": evaluation})
    summary = {}
    for method in config["methods"]:
        group = [r for r in rows if r["method"] == method]
        accepted = [r for r in group if r["decision"]["conditional_action"] != "ABSTAIN"]
        bad = sum(r["evaluation_only"]["false_adoption"] for r in accepted)
        summary[method] = {"case_count": len(group), "accepted_count": len(accepted),
                           "false_adoption_count": bad,
                           "false_adoption_fraction": bad / len(accepted) if accepted else None,
                           "action_counts": dict(Counter(r["decision"]["conditional_action"] for r in group)),
                           "status_counts": dict(Counter(r["decision"]["status"] for r in group)),
                           "full_generating_latent_truth_in_declared_model_count": sum(r["evaluation_only"]["truth_membership"]["included"] for r in group),
                           "current_x_truth_feasible_count": sum(r["evaluation_only"]["truth_membership"]["current_x_feasible"] is True for r in group),
                           "current_x_truth_unsolved_count": sum(r["evaluation_only"]["truth_membership"]["current_x_feasible"] is None for r in group)}
    (output / "synthetic_inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    (output / "decisions.jsonl").write_text("".join(json.dumps(r, allow_nan=False) + "\n" for r in rows))
    receipt = {**metadata, "completed_utc": datetime.now(timezone.utc).isoformat(),
               "row_count": len(rows), "designed_synthetic_scenarios": len(config["cases"]),
               "summary": summary, "source_unchanged": all(sha256(f) == h for f, h in sources.items()),
               "interpretation": "Designed sanity fixtures and assumption ablations, not sampled performance or P2 evidence",
               "output_sha256": {n: sha256(output / n) for n in ("synthetic_inputs.json", "decisions.jsonl")}}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(output), "row_count": len(rows), "summary": summary}, indent=2))


if __name__ == "__main__":
    main()

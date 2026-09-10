"""Synthetic purpose/edge-case audit of the unchanged v3.8 weighting candidate.

Run in Docker. This reads only its JSON config and source code; it does not load
photographs, references, scene results, targets, or a GS optimizer. Scalar targets
are deliberately synthetic. Sweep frequencies are not scene distributions.
"""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import traceback
from datetime import datetime, timezone

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from src.phd.local_source_weight_v3_8 import evidence_from_costs, weight_from_evidence


IMAGE = "sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e"
MODULE = REPO / "src/phd/local_source_weight_v3_8.py"
DEFAULT_CONFIG = {
    "schema": "jbgs_weight_intent_audit_v3_9",
    "scientific_verdict": None,
    "scope": "synthetic_algebra_only_no_gt_no_gpu_no_training",
    "runtime_image_id": IMAGE,
    "expected_source_sha256": "4699a64bb791d23f0ad4836c82337aad5a680f0af91a49927911d1b0f50bc70f",
    "cost_grid": {"start": 0.0, "stop": 1.0, "count": 101,
                  "three_scale_mode": "same_cost_at_all_scales", "observation_gate": 1.0,
                  "independent_scale_grid_count": 21,
                  "distribution_label": "synthetic_uniform_grid_not_scene_distribution"},
    "coefficient_cases": [
        {"id": "ratio_1", "cP": .005, "cI": .005},
        {"id": "ratio_10", "cP": .005, "cI": .05},
        {"id": "ratio_100", "cP": .0005, "cI": .05},
        {"id": "prior_disabled", "cP": 0., "cI": .05},
        {"id": "image_disabled", "cP": .005, "cI": 0.},
        {"id": "both_disabled", "cP": 0., "cI": 0.}],
    "partial_image_support": [0., .001, .005, .01, .02, .05, .1, .2, .5, 1.],
    "targets": {"prior": 0.0, "image": 1.0, "predictions": [-1., .25, .5, .75, 2.]},
    "activation_probe_coefficients": [0., 1e-12, 1e-9, 1e-6, .0005, .005],
    "tolerance": 1e-12,
}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def write_csv(path, rows):
    with Path(path).open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def stats(values, tolerance):
    values = np.asarray(values)
    n = values.size
    return {"n": n, "zero_count": int(np.sum(np.abs(values) <= tolerance)),
            "one_count": int(np.sum(np.abs(values - 1) <= tolerance)),
            "interior_count": int(np.sum((values > tolerance) & (values < 1 - tolerance))),
            "minimum": float(np.min(values)), "maximum": float(np.max(values)),
            "mean": float(np.mean(values))}


def scalar_loss_description(wp, wi, prior, image, predictions, tolerance):
    if wp + wi <= tolerance:
        optimum = "all_real_depths_no_depth_constraint"
    elif abs(wp - wi) <= tolerance:
        optimum = "entire_interval_between_targets"
    elif wp > wi:
        optimum = "prior_target"
    else:
        optimum = "image_target"
    gradients = [float(wp * np.sign(x - prior) + wi * np.sign(x - image)) for x in predictions]
    return optimum, gradients


def audit(config, output, checks):
    tol = config["tolerance"]

    def check(name, passed, **detail):
        checks.append({"name": name, "passed": bool(passed), **detail})
        if not passed:
            raise AssertionError(name)

    check("source_hash_matches_config", sha(MODULE) == config["expected_source_sha256"])
    check("pinned_runtime_image", os.environ.get("JBGS_RUNTIME_IMAGE_ID") == config["runtime_image_id"])
    check("verdict_and_scope", config["scientific_verdict"] is None and
          config["scope"] == "synthetic_algebra_only_no_gt_no_gpu_no_training")
    states = {"supported": (1., 0.), "unknown": (0., 0.), "rejected": (0., 1.)}
    ptarget, itarget = config["targets"]["prior"], config["targets"]["image"]
    predictions = config["targets"]["predictions"]
    check("ordered_synthetic_targets", ptarget < itarget)
    endpoints, partials, gradients, activation, thresholds = [], [], [], [], []
    for case in config["coefficient_cases"]:
        cp, ci, name = case["cP"], case["cI"], case["id"]
        for pn, (sp, rp) in states.items():
            for inn, (si, ri) in states.items():
                wp, wi = [float(v) for v in weight_from_evidence(cp, ci, sp, rp, si, ri)]
                budget = cp + ci
                check(f"endpoint_budget/{name}/{pn}/{inn}", 0 <= wp + wi <= budget + tol)
                check(f"disabled_sources/{name}/{pn}/{inn}", (cp > 0 or wp == 0) and (ci > 0 or wi == 0))
                # Independent explicit nine-corner table before source activation.
                table = {("supported", "supported"): (cp, ci),
                         ("supported", "unknown"): (cp, 0),
                         ("supported", "rejected"): (budget, 0),
                         ("unknown", "supported"): (cp, ci),
                         ("unknown", "unknown"): (cp, 0),
                         ("unknown", "rejected"): (cp, 0),
                         ("rejected", "supported"): (0, budget),
                         ("rejected", "unknown"): (0, 0),
                         ("rejected", "rejected"): (0, 0)}
                expected = table[(pn, inn)]
                expected = (expected[0] if cp > 0 else 0, expected[1] if ci > 0 else 0)
                check(f"nine_state_contract/{name}/{pn}/{inn}", np.allclose([wp, wi], expected, atol=tol, rtol=0))
                optimum, gs = scalar_loss_description(wp, wi, ptarget, itarget, predictions, tol)
                endpoints.append({"coefficient_case": name, "prior_evidence": pn, "image_evidence": inn,
                                  "cP": cp, "cI": ci, "wP": wp, "wI": wi, "strength": wp + wi,
                                  "image_share": wi / (wp + wi) if wp + wi > 0 else None,
                                  "prior_gain": wp / cp if cp > 0 else None,
                                  "scalar_l1_optimum": optimum})
                for x, analytic in zip(predictions, gs):
                    eps = 1e-5
                    def loss(v):
                        return wp * abs(v - ptarget) + wi * abs(v - itarget)
                    numeric = (loss(x + eps) - loss(x - eps)) / (2 * eps)
                    check(f"scalar_gradient/{name}/{pn}/{inn}/{x}", abs(analytic - numeric) < 1e-9)
                    gradients.append({"coefficient_case": name, "prior_evidence": pn, "image_evidence": inn,
                                      "prediction": x, "gradient": analytic, "finite_difference": numeric,
                                      "negative_gradient_direction": "lower_depth" if analytic > tol else
                                      "higher_depth" if analytic < -tol else "zero"})
        for pn, (sp, rp) in {**states, "partial_rejection": (0., .5)}.items():
            for si in config["partial_image_support"]:
                wp, wi = [float(v) for v in weight_from_evidence(cp, ci, sp, rp, si, 0)]
                optimum, _ = scalar_loss_description(wp, wi, ptarget, itarget, [.5], tol)
                partials.append({"coefficient_case": name, "prior_evidence": pn, "SP": sp, "RP": rp,
                                 "SI": si, "RI": 0, "wP": wp, "wI": wi,
                                 "scalar_l1_optimum": optimum,
                                 "interior_gradient": wp - wi, "strength": wp + wi,
                                 "image_share": wi / (wp + wi) if wp + wi else None})
                check(f"partial_budget/{name}/{pn}/{si}", 0 <= wp + wi <= cp + ci + tol)
            if cp > 0 and ci > 0:
                crossing = cp * (1 - rp) / (ci + cp * rp)
                wp, wi = weight_from_evidence(cp, ci, sp, rp, crossing, 0)
                check(f"analytic_crossing/{name}/{pn}", abs(float(wp - wi)) <= tol)
                thresholds.append({"coefficient_case": name, "prior_evidence": pn,
                                   "SI_tie": crossing, "image_dominates_when": "SI > SI_tie",
                                   "meaning": "synthetic_scalar_L1_targets_not_Gaussian_motion"})

    fixed = .05
    for active_coefficient in config["activation_probe_coefficients"]:
        wp, wi = map(float, weight_from_evidence(active_coefficient, fixed, 1, 0, 0, 1))
        activation.append({"varying_source": "prior", "coefficient": active_coefficient,
                           "other_coefficient": fixed, "wP": wp, "wI": wi,
                           "gain_of_varying_source": wp / active_coefficient if active_coefficient > 0 else None})
        wp, wi = map(float, weight_from_evidence(fixed, active_coefficient, 0, 1, 1, 0))
        activation.append({"varying_source": "image", "coefficient": active_coefficient,
                           "other_coefficient": fixed, "wP": wp, "wI": wi,
                           "gain_of_varying_source": wi / active_coefficient if active_coefficient > 0 else None})
    check("activation_zero_is_disabled", activation[0]["wP"] == 0 and activation[1]["wI"] == 0)
    check("positive_activation_can_accept_full_transfer", activation[2]["wP"] > .049 and activation[3]["wI"] > .049)

    cg = config["cost_grid"]
    costs = np.linspace(cg["start"], cg["stop"], cg["count"])
    three = np.repeat(costs[:, None], 3, axis=1)
    ss, rr, uu = evidence_from_costs(three, cg["observation_gate"])
    ep, ei = np.meshgrid(costs, costs, indexing="ij")
    sp, rp, _ = evidence_from_costs(np.repeat(ep[..., None], 3, axis=-1), 1)
    si, ri, _ = evidence_from_costs(np.repeat(ei[..., None], 3, axis=-1), 1)
    sweep_summary, sweep_payload = [], {"prior_cost": ep, "image_cost": ei}
    for case in config["coefficient_cases"]:
        cp, ci, name = case["cP"], case["cI"], case["id"]
        wp, wi = weight_from_evidence(cp, ci, sp, rp, si, ri)
        strength = wp + wi
        share = np.divide(wi, strength, out=np.zeros_like(wi), where=strength > tol)
        active = strength > tol
        q = share[active]
        check(f"whole_cost_grid_budget/{name}", np.all(strength <= cp + ci + tol))
        row = {"coefficient_case": name, "distribution_label": cg["distribution_label"],
               "total_pixels": int(strength.size), "zero_strength_count": int(np.sum(~active)),
               "active_count": int(np.sum(active)), "image_share_among_active": stats(q, tol) if q.size else None,
               "prior_dominant_count": int(np.sum(wp > wi + tol)),
               "image_dominant_count": int(np.sum(wi > wp + tol)),
               "active_tie_count": int(np.sum(active & (np.abs(wp - wi) <= tol))),
               "prior_gain_max": float(np.max(wp) / cp) if cp > 0 else None,
               "image_gain_max": float(np.max(wi) / ci) if ci > 0 else None,
               "strength_min": float(strength.min()), "strength_max": float(strength.max()),
               "baseline_budget": cp + ci}
        sweep_summary.append(row)
        sweep_payload.update({name + "_wP": wp, name + "_wI": wi, name + "_strength": strength,
                              name + "_image_share": share, name + "_active": active})
    independent = np.linspace(0, 1, cg["independent_scale_grid_count"])
    all_three = np.stack(np.meshgrid(independent, independent, independent, indexing="ij"), axis=-1)
    s3, r3, u3 = evidence_from_costs(all_three, 1)
    scale_summary = {"distribution_label": cg["distribution_label"],
                     "equal_three_scale_costs": {"support": stats(ss, tol), "rejection": stats(rr, tol), "unknown": stats(uu, tol)},
                     "independent_three_scale_costs": {"support": stats(s3, tol), "rejection": stats(r3, tol), "unknown": stats(u3, tol)}}
    check("cross_scale_unknown_nonzero", np.any(np.abs(u3 - 1) <= tol))
    # Independently verify endpoint weighted-median minimizers on a dense scalar grid.
    xgrid = np.linspace(-1, 2, 301)
    for row in endpoints:
        wp, wi = row["wP"], row["wI"]
        values = wp * np.abs(xgrid - ptarget) + wi * np.abs(xgrid - itarget)
        if wp > wi + tol:
            check("dense_argmin_prior/" + str(len(checks)), abs(float(xgrid[np.argmin(values)]) - ptarget) < 1e-10)
        elif wi > wp + tol:
            check("dense_argmin_image/" + str(len(checks)), abs(float(xgrid[np.argmin(values)]) - itarget) < 1e-10)
        elif wp + wi > tol:
            inside = (xgrid >= ptarget) & (xgrid <= itarget)
            check("dense_argmin_interval/" + str(len(checks)), float(np.ptp(values[inside])) < tol)

    for filename, rows in [("endpoints.csv", endpoints), ("partial_evidence.csv", partials),
                           ("scalar_gradients.csv", gradients), ("activation_barrier.csv", activation),
                           ("analytic_dominance_thresholds.csv", thresholds)]:
        write_csv(output / filename, rows)
    write_json(output / "cost_sweep_summary.json", sweep_summary)
    write_json(output / "scale_evidence_summary.json", scale_summary)
    with (output / "cost_sweep_arrays.npz").open("xb") as stream:
        np.savez_compressed(stream, **sweep_payload)
    findings = {
        "scientific_verdict": None,
        "algebra_status": "PASS",
        "method_effectiveness_status": "NOT_EVALUATED",
        "intent_findings": [
            {"id": "weak_image_support_can_dominate", "classification": "conditional_intent_counterexample",
             "finding": "With unrejected prior, SI > cP/cI makes the image target the scalar L1 optimum, even when most image evidence is unknown.",
             "condition": "Conflicts with an intent requiring strong image evidence before replacement; it does not violate the existing v3.8 equation.",
             "ratios_1_10_100_tie_SI": [1., .1, .01]},
            {"id": "both_supported_disagreeing_targets", "classification": "policy_consequence",
             "finding": "Weights remain the original cP,cI. Unequal coefficients select the stronger target in scalar L1; equal coefficients leave the complete inter-target interval optimal. This is not a reliability-based resolution of both-supported disagreement."},
            {"id": "prior_amplification", "classification": "policy_risk",
             "finding": "Supported prior plus rejected image reallocates the full budget to prior: gains 2,11,101 for the audited ratios. Fixed total budget does not bound amplification relative to the old prior coefficient."},
            {"id": "all_unknown_fallback", "classification": "explicit_policy_consequence",
             "finding": "All unknown retains cP prior supervision. A current depth between the targets is pulled toward prior; this preserves the prior target, not the current GS state. If cP=0, depth supervision is absent."},
            {"id": "activation_barrier", "classification": "mathematical_discontinuity",
             "finding": "Zero coefficients cannot reactivate. However, changing zero to any positive value permits receiving the other source budget: a discontinuity at zero. Within a fixed positive-source support set the mapping is continuous."},
            {"id": "clipping_and_scale_min", "classification": "synthetic_distribution_diagnostic",
             "finding": "The mapping is continuous but saturates; min requires all scales to support the same claim. Reported proportions describe the frozen uniform synthetic grids only, not actual scene pixels."}],
        "limits": ["No image geometry or visibility gate was measured.", "Gate=1 is hypothetical throughout the cost sweeps.",
                   "No GT was read or used to select thresholds.", "No proposed cost knots were changed or ranked.",
                   "Scalar L1 derivatives and minimizers are not Gaussian updates or final surfaces.",
                   "No spatial allocation benefit, reproducibility claim, or scientific verdict follows."]}
    write_json(output / "findings.json", findings)
    return {"endpoint_rows": len(endpoints), "partial_rows": len(partials), "gradient_rows": len(gradients),
            "activation_rows": len(activation), "dominance_threshold_rows": len(thresholds),
            "source_pair_grid_points_per_coefficient_case": int(ep.size),
            "independent_three_scale_grid_points": int(s3.size), "summary": findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-default-config", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.write_default_config:
        if args.config or args.output:
            parser.error("config creation and audit execution are separate invocations")
        args.write_default_config.parent.mkdir(parents=True, exist_ok=False)
        write_json(args.write_default_config, DEFAULT_CONFIG)
        print(json.dumps({"created": str(args.write_default_config), "sha256": sha(args.write_default_config)}))
        return
    if args.config is None or args.output is None:
        parser.error("--config and --output are required for execution")
    args.output.mkdir(parents=True, exist_ok=True)
    receipt_path = args.output / "receipt.json"
    if receipt_path.exists() or any((args.output / name).exists() for name in ("findings.json", "checks.json", "endpoints.csv")):
        raise FileExistsError("Use a new immutable output directory")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.config.resolve() != (args.output / "config.json").resolve():
        write_json(args.output / "config.json", config)
    receipt = {"schema": "jbgs_weight_intent_audit_receipt_v3_9", "started_at": timestamp(),
               "scientific_verdict": None, "status": "RUNNING", "scope": "synthetic_algebra_only_no_gt_no_gpu_no_training",
               "config_sha256": sha(args.output / "config.json"), "script_sha256": sha(__file__),
               "source_sha256": sha(MODULE), "git_commit": os.environ.get("JBGS_REPOSITORY_COMMIT"),
               "runtime_image_id": os.environ.get("JBGS_RUNTIME_IMAGE_ID"), "python": platform.python_version(),
               "numpy": np.__version__, "argv": sys.argv, "cpu_limit": 1, "memory_limit_mib": 512,
               "no_gpu_requested": True, "gt_read": False, "training_executed": False,
               "failures": [], "artifacts": []}
    checks = []
    error = None
    try:
        receipt["result"] = audit(config, args.output, checks)
        receipt["status"] = "PASS"
    except Exception as exc:
        error = exc
        receipt["status"] = "FAIL"
        receipt["failures"].append({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    finally:
        write_json(args.output / "checks.json", checks)
        receipt["check_count"] = len(checks)
        receipt["passed_check_count"] = sum(row["passed"] for row in checks)
        receipt["completed_at"] = timestamp()
        for path in sorted(args.output.iterdir()):
            if path.is_file():
                receipt["artifacts"].append({"name": path.name, "sha256": sha(path), "bytes": path.stat().st_size})
        write_json(receipt_path, receipt)
        print(json.dumps({"status": receipt["status"], "checks": len(checks), "output": str(args.output)}, ensure_ascii=False))
    if error is not None:
        raise error


if __name__ == "__main__":
    main()

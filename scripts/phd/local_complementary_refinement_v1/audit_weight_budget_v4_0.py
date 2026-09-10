"""Purpose-focused scalar audit; synthetic q, no observation/GT/training claims."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import traceback

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from src.phd.local_source_weight_v4_0 import weight_from_allocation

MODULE = REPO / "src/phd/local_source_weight_v4_0.py"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def write_csv(path, rows):
    with Path(path).open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def audit(config, output, checks):
    tol = config["tolerance"]

    def check(name, passed, **detail):
        checks.append({"name": name, "passed": bool(passed), **detail})
        if not passed:
            raise AssertionError(name)

    check("pinned_docker", os.environ.get("JBGS_RUNTIME_IMAGE_ID") == config["runtime"]["image_id"])
    check("nontraining_scope", config["scientific_verdict"] is None and not config["execution_ready_for_training"])
    qs = np.asarray(config["prescribed_q"])
    active_rows, inactive_rows, barrier_rows, scalar_rows = [], [], [], []
    for case in config["coefficient_cases"]:
        cp, ci, name = case["cP"], case["cI"], case["id"]
        result = weight_from_allocation(qs, cp, ci)
        wp, wi, strength = result["wP"], result["wI"], result["strength"]
        check(f"q_preserved_independent_of_ratio/{name}", np.allclose(result["q_effective"], qs, atol=tol, rtol=0))
        check(f"source_caps/{name}", np.all(wp <= cp + tol) and np.all(wi <= ci + tol))
        check(f"nonnegative_total_budget/{name}", np.all(strength >= 0) and np.all(strength <= cp + ci + tol))
        check(f"fallback_not_amplified/{name}", abs(wp[0] - cp) <= tol and wi[0] == 0)
        check(f"strong_image_not_capped_by_prior/{name}", wp[-1] == 0 and abs(wi[-1] - ci) <= tol)
        check(f"at_least_one_source_cap_saturated/{name}", np.all(np.isclose(wp, cp, atol=tol, rtol=0) |
                                                                                np.isclose(wi, ci, atol=tol, rtol=0)))
        kink = ci / (cp + ci)
        at_kink = weight_from_allocation(kink, cp, ci)
        check(f"unique_full_budget_allocation/{name}", abs(float(at_kink["strength"]) - cp - ci) <= tol)
        around = weight_from_allocation(np.array([0., 1e-9, kink - 1e-9, kink, kink + 1e-9, 1 - 1e-9, 1.]), cp, ci)
        check(f"continuous_fixed_active_endpoints_and_kink/{name}",
              abs(around["strength"][0] - around["strength"][1]) < 1e-8 and
              np.max(np.abs(around["strength"][2:5] - around["strength"][3])) < 1e-8 and
              abs(around["strength"][-1] - around["strength"][-2]) < 1e-8)
        for index, q in enumerate(qs):
            p, i, s = map(float, [wp[index], wi[index], strength[index]])
            active_rows.append({"case": name, "q_prescribed": float(q), "cP": cp, "cI": ci,
                                "wP": p, "wI": i, "strength": s, "q_effective": float(result["q_effective"][index]),
                                "prior_fraction_of_original": p / cp, "image_fraction_of_original": i / ci,
                                "total_fraction_of_original": s / (cp + ci)})
            for target_name, targets in [("distinct", config["synthetic_targets"]["distinct"]),
                                         ("identical", config["synthetic_targets"]["identical"])]:
                dp, di = targets
                for x in config["synthetic_targets"]["predictions"]:
                    analytic = p * np.sign(x - dp) + i * np.sign(x - di)
                    eps = 1e-5
                    def loss(v):
                        return p * abs(v - dp) + i * abs(v - di)
                    numeric = (loss(x + eps) - loss(x - eps)) / (2 * eps)
                    check(f"scalar_gradient/{name}/{q}/{target_name}/{x}", abs(analytic - numeric) < 1e-9)
                    if target_name == "distinct" and dp < x < di:
                        check(f"q_half_determines_scalar_direction/{name}/{q}/{x}",
                              abs(analytic - s * (1 - 2 * q)) <= tol)
                    scalar_rows.append({"case": name, "q_prescribed": float(q), "target_case": target_name,
                                        "prior_target": dp, "image_target": di, "prediction": x,
                                        "gradient": float(analytic), "finite_difference": float(numeric),
                                        "comparison_baseline_gradient": float(cp * np.sign(x - dp) + ci * np.sign(x - di)),
                                        "interpretation": "scalar_depth_loss_only_not_Gaussian_update"})

    # Inspect inactive policies without treating the two-source q as single-source quality.
    for ps, ins in [("disabled", "active"), ("missing", "active"), ("active", "disabled"),
                    ("active", "missing"), ("disabled", "missing")]:
        for admission in config["single_image_admission"]:
            result = weight_from_allocation(qs, .005, .05, prior_status=ps, image_status=ins,
                                             single_image_admission=admission)
            expected_p = .005 if ps == "active" else 0.
            expected_i = .05 * (admission or 0.) if ps != "active" and ins == "active" else 0.
            check(f"inactive_policy/{ps}/{ins}/{admission}", np.allclose(result["wP"], expected_p, atol=tol) and
                  np.allclose(result["wI"], expected_i, atol=tol))
            check(f"inactive_metadata/{ps}/{ins}/{admission}", np.all(result["prior_status"] == ps) and
                  np.all(result["image_status"] == ins) and not np.any(result["requested_q_applicable"]))
            inactive_rows.append({"prior_status": ps, "image_status": ins, "single_image_admission": admission,
                                  "q_values_checked": len(qs), "wP": float(result["wP"][0]), "wI": float(result["wI"][0]),
                                  "requested_two_source_q_used": False})
    for varying_source in ("prior", "image"):
        for coefficient in config["activation_probe_coefficients"]:
            for q in config["activation_probe_q"]:
                cp, ci = (coefficient, .05) if varying_source == "prior" else (.005, coefficient)
                result = weight_from_allocation(q, cp, ci)
                wp, wi = float(result["wP"]), float(result["wI"])
                check(f"zero_boundary_source_caps/{varying_source}/{coefficient}/{q}", wp <= cp + tol and wi <= ci + tol)
                barrier_rows.append({"varying_source": varying_source, "coefficient": coefficient, "q_prescribed": q,
                                     "cP": cp, "cI": ci, "wP": wp, "wI": wi,
                                     "strength": float(result["strength"]),
                                     "both_sources_active": bool(result["requested_q_applicable"]),
                                     "single_image_admission": None})
    # One broadcasting check ensures per-pixel availability is represented independently.
    result = weight_from_allocation([.9, .9], .005, .05, prior_status=["missing", "active"], single_image_admission=.2)
    check("per_pixel_missing_metadata_and_single_admission", result["wP"][0] == 0 and abs(result["wI"][0] - .01) < tol
          and result["requested_q_applicable"].tolist() == [False, True])
    for bad_kwargs in [{"q": 1.1, "cP": .005, "cI": .05}, {"q": .5, "cP": -1, "cI": .05},
                       {"q": np.nan, "cP": .005, "cI": .05},
                       {"q": .5, "cP": .005, "cI": .05, "single_image_admission": 1.1},
                       {"q": .5, "cP": .005, "cI": .05, "prior_status": "unknown_label"}]:
        rejected = False
        try:
            weight_from_allocation(**bad_kwargs)
        except ValueError:
            rejected = True
        check("invalid_domain_rejected/" + str(len(checks)), rejected)

    # Purpose-focused limitations, recorded as measured consequences rather than test failures.
    low_ratio = weight_from_allocation(.9, .0005, .05)
    check("ratio100_q90_retains_only_nine_percent_image_strength", abs(float(low_ratio["wI"]) / .05 - .09) < tol)
    agreement = weight_from_allocation(.5, .0005, .05)
    check("equal_targets_can_lose_total_strength", abs(float(agreement["strength"]) - .001) < tol)
    diminishing = weight_from_allocation(.5, np.array([1e-3, 1e-6, 1e-9, 1e-12]), .05)
    check("no_uniform_positive_strength_floor", np.all(np.diff(diminishing["strength"]) < 0) and
          diminishing["strength"][-1] < 3e-12)
    fixed_q = weight_from_allocation(.02, .0005, .05)
    check("fixed_q_not_reversed_by_coefficient_ratio", abs(float(fixed_q["q_effective"]) - .02) < tol and
          float(fixed_q["wP"]) > float(fixed_q["wI"]))
    for name, rows in [("active_budget.csv", active_rows), ("inactive_policy.csv", inactive_rows),
                       ("activation_boundary.csv", barrier_rows), ("scalar_gradients.csv", scalar_rows)]:
        write_csv(output / name, rows)
    result = {"scientific_verdict": None, "algebra_status": "PASS", "observation_to_q_status": "NOT_EVALUATED",
              "training_status": "NOT_EXECUTED", "active_rows": len(active_rows), "inactive_rows": len(inactive_rows),
              "activation_rows": len(barrier_rows), "scalar_gradient_rows": len(scalar_rows),
              "q09_ratio100": {"wP": float(low_ratio["wP"]), "wI": float(low_ratio["wI"]),
                                "image_fraction_of_original": float(low_ratio["wI"]) / .05},
              "same_target_q05_ratio100": {"strength": float(agreement["strength"]), "baseline_strength": .0505,
                                            "retained_fraction": float(agreement["strength"]) / .0505},
              "fixed_q002_ratio100": {"q_requested": .02, "wP": float(fixed_q["wP"]), "wI": float(fixed_q["wI"]),
                                      "meaning": "prescribed_q_budget_only_not_conversion_of_v38_SI_002"},
              "verified_invariants": ["two-active q preserved across coefficient ratios", "wP<=cP and wI<=cI",
                                      "q=0 retains prior cP without transfer", "q=1 retains image cI",
                                      "missing and disabled never reactivate", "prior-off q does not substitute for single-image admission"],
              "limitations": config["required_limitations"],
              "zero_boundary_detail": "No transfer-driven amplification exists. Discrete inactive policy still changes behavior: image-off returns prior cP, while a positive image coefficient with q=1 returns only that image coefficient; prior-off without admission returns zero even when q=1."}
    write_json(output / "summary.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    write_json(args.output / "config.json", config)
    binding = {"config_source": str(args.config), "config_sha256": sha(args.config),
               "script_sha256": sha(__file__), "module_sha256": sha(MODULE),
               "git_commit": os.environ.get("JBGS_REPOSITORY_COMMIT"),
               "runtime_image_id": os.environ.get("JBGS_RUNTIME_IMAGE_ID")}
    write_json(args.output / "binding.json", binding)
    receipt = {"schema": "jbgs_weight_budget_receipt_v4_0", "scientific_verdict": None, "status": "RUNNING",
               "started_at": datetime.now(timezone.utc).isoformat(), "binding": binding,
               "python": platform.python_version(), "numpy": np.__version__, "argv": sys.argv,
               "cpu_limit": 2, "memory_limit_mib": 2048, "network": "none", "gpu_requested": False,
               "gt_read": False, "training_executed": False, "q_source": "prescribed_synthetic",
               "failures": [], "artifacts": []}
    checks, error = [], None
    try:
        receipt["summary"] = audit(config, args.output, checks)
        if sha(args.config) != binding["config_sha256"] or sha(__file__) != binding["script_sha256"] or sha(MODULE) != binding["module_sha256"]:
            raise RuntimeError("Bound config or code changed during audit")
        receipt["status"] = "PASS"
    except Exception as exc:
        error = exc
        receipt["status"] = "FAIL"
        receipt["failures"].append({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    finally:
        write_json(args.output / "checks.json", checks)
        receipt["check_count"] = len(checks)
        receipt["passed_check_count"] = sum(c["passed"] for c in checks)
        receipt["completed_at"] = datetime.now(timezone.utc).isoformat()
        for path in sorted(args.output.iterdir()):
            if path.is_file():
                receipt["artifacts"].append({"name": path.name, "sha256": sha(path), "bytes": path.stat().st_size})
        write_json(args.output / "receipt.json", receipt)
        print(json.dumps({"status": receipt["status"], "checks": len(checks), "output": str(args.output)}, ensure_ascii=False))
    if error is not None:
        raise error


if __name__ == "__main__":
    main()

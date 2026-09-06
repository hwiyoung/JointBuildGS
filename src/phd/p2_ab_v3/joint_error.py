"""Finite-branch scalar joint-error development solver; not a P2 calibration.

``photo`` is a synthetic scalar geometric observation, NOT an RGB likelihood.
The supplied relation e_I = eta + nu is a fixture model, not an established
relationship between real P2 MVS and images. HiGHS returns floating-point
extrema, not verified interval certificates. All acceptance is conditional.
"""

from copy import deepcopy

import numpy as np
from scipy.optimize import linprog


VARIABLES = ("x", "c", "delta", "eta", "nu", "e_I", "e_P", "Delta")
METHODS = ("joint", "prior_error_zero", "image_error_zero", "drop_noise_link",
           "shared_error_zero", "force_same_epoch")


def variant(problem, method):
    """Same observations, one explicitly named assumption change."""
    p = deepcopy(problem)
    if method not in METHODS:
        raise ValueError(method)
    if method == "prior_error_zero":
        p["bounds"]["e_P"] = [0.0, 0.0]
    elif method == "image_error_zero":
        p["bounds"]["e_I"] = [0.0, 0.0]
    elif method == "drop_noise_link":
        p["link_image_noise"] = False
    elif method == "shared_error_zero":
        p["bounds"]["c"] = [0.0, 0.0]
    elif method == "force_same_epoch":
        p["branches"] = [{"id": "forced_same", "relation": "same", "change_bounds": [0, 0]}]
    return p


def _constraints(problem, branch):
    bounds = [tuple(problem["bounds"].get(k, [None, None])) for k in VARIABLES]
    relation = branch["relation"]
    if relation not in ("same", "changed", "unmatched"):
        raise ValueError("Unknown relation")
    bounds[-1] = (0, 0) if relation == "same" else tuple(branch["change_bounds"])
    rows, rhs = [], []

    def add(coefficients, value):
        rows.append([coefficients.get(k, 0.0) for k in VARIABLES])
        rhs.append(value)

    obs = problem["observations"]
    if obs.get("photo") is not None:
        add({"x": 1, "c": 1, "eta": 1}, obs["photo"])
    if obs.get("mvs") is not None:
        add({"x": 1, "c": 1, "e_I": 1}, obs["mvs"])
    if problem.get("link_image_noise", True) and obs.get("mvs") is not None:
        add({"e_I": 1, "eta": -1, "nu": -1}, 0)
    if obs.get("prior") is not None and relation != "unmatched":
        add({"x": 1, "c": problem.get("prior_shared_loading", 0),
             "delta": -1, "e_P": 1, "Delta": -1}, obs["prior"])
    # Repeated identical evidence must not shrink an interval constraint.
    copies = problem.get("observation_copies", 1)
    if not isinstance(copies, int) or copies < 1:
        raise ValueError("observation_copies must be a positive integer")
    return (np.asarray(rows * copies, dtype=float).reshape(-1, len(VARIABLES)),
            np.asarray(rhs * copies, dtype=float), bounds)


def _residual(point, a_eq, b_eq, bounds):
    eq = float(np.max(np.abs(a_eq @ point - b_eq))) if len(b_eq) else 0.0
    box = 0.0
    for value, (lo, hi) in zip(point, bounds):
        box = max(box, 0 if lo is None else lo - value, 0 if hi is None else value - hi)
    return max(eq, float(box))


def solve_branch(problem, branch):
    """Numerically project a supplied affine feasible set onto x and delta."""
    a_eq, b_eq, bounds = _constraints(problem, branch)
    tol = problem.get("solver_tolerance", 1e-8)
    output = {"branch_id": branch["id"], "relation": branch["relation"],
              "status": "SOLVED_NUMERICAL", "extrema": {}, "projection_status": {},
              "max_primal_residual": 0.0}
    for variable in ("x", "delta"):
        endpoints = []
        for sign in (1, -1):
            objective = np.zeros(len(VARIABLES))
            objective[VARIABLES.index(variable)] = sign
            result = linprog(objective, A_eq=a_eq if len(b_eq) else None,
                             b_eq=b_eq if len(b_eq) else None, bounds=bounds,
                             method="highs", options={"primal_feasibility_tolerance": tol,
                                                       "dual_feasibility_tolerance": tol})
            if result.status != 0:
                status = {2: "INFEASIBLE", 3: "UNBOUNDED"}.get(result.status, "UNSOLVED")
                if variable == "delta" and status == "UNBOUNDED":
                    output["extrema"][variable] = None
                    output["projection_status"][variable] = status
                    break
                output.update(status=status, solver_message=result.message)
                return output
            residual = _residual(result.x, a_eq, b_eq, bounds)
            output["max_primal_residual"] = max(output["max_primal_residual"], residual)
            if not np.isfinite(result.fun) or residual > tol:
                output.update(status="UNSOLVED", solver_message="Nonfinite optimum or excessive residual")
                return output
            endpoints.append(float(result.x[VARIABLES.index(variable)]))
        else:
            output["extrema"][variable] = endpoints
            output["projection_status"][variable] = "SOLVED_NUMERICAL"
    return output


def truth_membership(problem, truth):
    """Evaluation-only helper; never called by judge()."""
    point = np.asarray([truth[k] for k in VARIABLES], dtype=float)
    residuals, x_status = {}, {}
    for branch in problem["branches"]:
        a_eq, b_eq, bounds = _constraints(problem, branch)
        residuals[branch["id"]] = _residual(point, a_eq, b_eq, bounds)
        # Existential nuisance feasibility with x fixed to evaluation truth.
        # This is separate from checking the entire generating latent vector.
        fixed_bounds = list(bounds)
        xlo, xhi = bounds[0]
        if ((xlo is not None and truth["x"] < xlo) or
                (xhi is not None and truth["x"] > xhi)):
            x_status[branch["id"]] = "INFEASIBLE"
            continue
        fixed_bounds[0] = (truth["x"], truth["x"])
        tol = problem.get("solver_tolerance", 1e-8)
        result = linprog(np.zeros(len(VARIABLES)), A_eq=a_eq if len(b_eq) else None,
                         b_eq=b_eq if len(b_eq) else None, bounds=fixed_bounds, method="highs",
                         options={"primal_feasibility_tolerance": tol, "dual_feasibility_tolerance": tol})
        x_status[branch["id"]] = ("FEASIBLE_NUMERICAL" if result.status == 0 and
                                      _residual(result.x, a_eq, b_eq, fixed_bounds) <= tol
                                  else "INFEASIBLE" if result.status == 2 else "UNSOLVED")
    current_x = (True if "FEASIBLE_NUMERICAL" in x_status.values() else
                 None if "UNSOLVED" in x_status.values() else False)
    return {"included": any(r <= problem.get("solver_tolerance", 1e-8) for r in residuals.values()),
            "included_field_scope": "ENTIRE_GENERATING_LATENT_VECTOR_INCLUDING_UNUSED_VARIABLES",
            "branch_residuals": residuals, "current_x_feasible": current_x,
            "current_x_branch_status": x_status}


def candidate_bounds(value, intervals, guard):
    """Absolute scalar error extrema over the union of x projections."""
    expanded = [(lo - guard, hi + guard) for lo, hi in intervals]
    lower = min(max(lo - value, value - hi, 0.0) for lo, hi in expanded)
    upper = max(max(abs(value - lo), abs(value - hi)) for lo, hi in expanded)
    return {"lower_m": float(lower), "upper_m": float(upper)}


def judge(problem):
    """Observations -> joint feasible branches -> candidate bounds -> action.

    Only the model is input. Ground truth, UAS, textures and external labels
    cannot enter through an evaluation argument. This is a single-location
    normal-displacement contract, not a continuous roof/surface contract.
    """
    epsilon = float(problem["tolerance_m"])
    guard = float(problem.get("numerical_guard_m", 1e-8))
    if not np.isfinite(epsilon) or epsilon <= 0 or guard < 0:
        raise ValueError("Positive finite tolerance and nonnegative guard required")
    branches = [solve_branch(problem, b) for b in problem["branches"]]
    feasible = [b for b in branches if b["status"] == "SOLVED_NUMERICAL"]
    failures = [b for b in branches if b["status"] not in ("SOLVED_NUMERICAL", "INFEASIBLE")]
    model_status = (failures[0]["status"] if failures else
                    "SOLVED_NUMERICAL" if feasible else "MODEL_INCONSISTENT")
    calibrated = problem.get("calibration_status") == "SYNTHETIC_DECLARED"
    status = model_status if calibrated else "CALIBRATION_UNKNOWN"
    intervals = [b["extrema"]["x"] for b in feasible]
    candidates = []
    obs = problem["observations"]

    def append(identifier, action, value, parents=(), correction=0.0):
        bounds = (candidate_bounds(value, intervals, guard)
                  if model_status == "SOLVED_NUMERICAL" else {"lower_m": None, "upper_m": None})
        eligibility = "UNKNOWN"
        if status == "SOLVED_NUMERICAL":
            eligibility = ("ELIGIBLE" if bounds["upper_m"] <= epsilon else
                           "INELIGIBLE" if bounds["lower_m"] > epsilon else "UNKNOWN")
        candidate = {"candidate_id": identifier, "action": action, "value_m": float(value),
                     "error_bounds_m": bounds, "eligibility": eligibility,
                     "parent_candidate_ids": list(parents), "correction_m": float(correction),
                     "support": "ONE_SCALAR_NORMAL_COMPONENT_AT_ONE_FIXED_LOCATION"}
        candidates.append(candidate)
        return candidate

    image = append("IMAGE_RAW", "IMAGE", obs["mvs"]) if obs.get("mvs") is not None else None
    prior = append("PRIOR_RAW", "PRIOR", obs["prior"]) if obs.get("prior") is not None else None
    # Unknown/change/unmatched branches cannot authorize a same-surface fusion.
    same_surface = bool(feasible) and not failures and all(b["relation"] == "same" for b in feasible)
    corrected = None
    registration_bounded = all(b["extrema"].get("delta") is not None for b in feasible)
    if same_surface and prior and registration_bounded:
        lo = min(b["extrema"]["delta"][0] for b in feasible)
        hi = max(b["extrema"]["delta"][1] for b in feasible)
        delta = (lo + hi) / 2
        corrected = append("PRIOR_REGISTERED", "PRIOR", prior["value_m"] + delta,
                           (prior["candidate_id"],), delta)
    if same_surface and image and prior:
        parent = corrected or prior
        weight = float(problem.get("fusion_image_weight", 0.5))
        if not 0 <= weight <= 1:
            raise ValueError("fusion weight outside [0,1]")
        fusion = append("FUSION_FIXED_WEIGHT", "FUSION",
                        weight * image["value_m"] + (1 - weight) * parent["value_m"],
                        (image["candidate_id"], parent["candidate_id"]))
        fusion["image_weight"] = weight
        best_parent = min(image["error_bounds_m"]["upper_m"], parent["error_bounds_m"]["upper_m"])
        fusion["improves_best_parent_bound"] = fusion["error_bounds_m"]["upper_m"] < best_parent - guard
        if not fusion["improves_best_parent_bound"] and fusion["eligibility"] == "ELIGIBLE":
            fusion["eligibility"] = "ELIGIBLE_WITHOUT_FUSION_BENEFIT"
    eligible = [c for c in candidates if c["eligibility"] == "ELIGIBLE"]
    chosen = min(eligible, key=lambda c: (c["error_bounds_m"]["upper_m"], c["candidate_id"])) if eligible else None
    return {"schema": "PHD_SCALAR_JOINT_ERROR_v1", "status": status, "model_status": model_status,
            "calibration_status": problem.get("calibration_status"), "tolerance_m": epsilon,
            "numerical_guard_m": guard, "solver_tolerance": problem.get("solver_tolerance", 1e-8),
            "branches": branches, "candidates": candidates,
            "same_current_surface_supported_by_all_feasible_branches": same_surface,
            "registration_projection_bounded": registration_bounded if feasible else False,
            "selected_candidate_id": chosen["candidate_id"] if chosen else None,
            "selected_value_m": chosen["value_m"] if chosen else None,
            "selected_error_bounds_m": chosen["error_bounds_m"] if chosen else None,
            "conditional_action": chosen["action"] if chosen else "ABSTAIN",
            "strict_current_use_action": "ABSTAIN", "scientific_verdict": None,
            "decision_scope": "SYNTHETIC_SUPPLIED_AFFINE_MODEL_NUMERICAL_EXTREMA",
            "remaining_unknowns": ["P2 source-error calibration and dependency model",
                                   "actual image association/visibility and linearization remainder",
                                   "continuous 3D surface, absolute datum and rigorous numeric certification"]}

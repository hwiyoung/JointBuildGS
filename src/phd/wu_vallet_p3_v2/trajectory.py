"""Estimated ALS origins from multi-return pulse lines, never measured trajectory.

Karney and Kim (2022), https://arxiv.org/html/2208.12116v1, section 2,
motivates a return-separation-weighted reverse linear fit and a forward
return-to-ray refinement. This implementation uses local linear time windows;
it is NOT their PDAL cubic-spline/scan-angle implementation and is NOT a native
Wu--Vallet acquisition record. Quantization, pulse misassociation, systematic
georeferencing errors and deviations from linear motion can bias the result.

Only original ALS pulse times and first/last XYZ enter the estimator. The caller
must separate flight strips, identify matching pulse times and preserve the
coordinate/time bases. Parallel/narrow beams can make sensor range unidentifiable.
Passing internal validation does not certify an actual optical center.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.optimize import least_squares


ROLE = "ESTIMATED_SENSOR_ORIGINS_FROM_MULTIRETURN_LINES"


@dataclass(frozen=True)
class TrajectoryConfig:
    min_return_separation_m: float
    separation_weight_cap_m: float
    min_train_pulses: int
    min_holdout_pulses: int
    holdout_every: int
    max_condition_number: float
    robust_line_scale_m: float
    robust_endpoint_scale_m: float
    max_holdout_line_p90_m: float
    max_holdout_endpoint_p90_m: float
    min_sensor_range_m: float
    max_sensor_range_m: float
    min_forward_fraction: float
    max_speed_m_per_s: float
    bootstrap_repetitions: int
    max_bootstrap_origin_p95_m: float
    random_seed: int
    objective: str = "forward_endpoint"
    max_irls_iterations: int = 12
    max_nonlinear_evaluations: int = 80
    bootstrap_mode: str = "contiguous_time_blocks"
    bootstrap_blocks: int = 12

    def __post_init__(self):
        positive = ("min_return_separation_m", "separation_weight_cap_m", "max_condition_number",
                    "robust_line_scale_m", "robust_endpoint_scale_m", "max_holdout_line_p90_m",
                    "max_holdout_endpoint_p90_m", "min_sensor_range_m", "max_sensor_range_m",
                    "max_speed_m_per_s", "max_bootstrap_origin_p95_m")
        for name in positive:
            if not np.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive and finite")
        for name in ("min_train_pulses", "min_holdout_pulses", "holdout_every", "bootstrap_repetitions",
                     "max_irls_iterations", "max_nonlinear_evaluations"):
            if not isinstance(getattr(self, name), (int, np.integer)) or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.min_train_pulses < 6 or self.min_holdout_pulses < 3 or self.holdout_every < 2:
            raise ValueError("need >=6 training pulses, >=3 holdout pulses, holdout_every>=2")
        if self.bootstrap_repetitions < 8:
            raise ValueError("at least eight bootstrap replicates are required")
        if not 0 < self.min_forward_fraction <= 1:
            raise ValueError("min_forward_fraction must be in (0,1]")
        if self.max_sensor_range_m <= self.min_sensor_range_m:
            raise ValueError("max_sensor_range_m must exceed min_sensor_range_m")
        if self.separation_weight_cap_m < self.min_return_separation_m:
            raise ValueError("separation_weight_cap_m must exceed minimum return separation")
        if self.objective not in ("forward_endpoint", "weighted_reverse_line"):
            raise ValueError("objective must be forward_endpoint or weighted_reverse_line")
        if self.bootstrap_mode not in ("contiguous_time_blocks", "independent_pulses"):
            raise ValueError("invalid bootstrap_mode")
        if not isinstance(self.bootstrap_blocks, (int, np.integer)) or self.bootstrap_blocks < 4:
            raise ValueError("at least four contiguous bootstrap blocks are required")


def _describe(values: np.ndarray) -> dict:
    values = np.asarray(values, dtype=np.float64)
    if not len(values):
        return {"count": 0}
    return {"count": int(len(values)), "min": float(values.min()), "median": float(np.median(values)),
            "mean": float(values.mean()), "p90": float(np.quantile(values, .90)),
            "p95": float(np.quantile(values, .95)), "max": float(values.max())}


def _design(tau: np.ndarray, midpoint: np.ndarray, direction: np.ndarray):
    projector = np.eye(3)[None] - direction[:, :, None] * direction[:, None, :]
    design = np.concatenate((projector, projector * tau[:, None, None]), axis=2)
    rhs = np.einsum("nij,nj->ni", projector, midpoint)
    return design, rhs


def _forward_residual(coef, tau, midpoint, direction, separation):
    sensor = coef[:3] + tau[:, None] * coef[3:]
    q = sensor - midpoint
    qhat = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-12)
    # Half-separation times the first/last direction component perpendicular
    # to the sensor-to-midpoint line; exact endpoint-to-infinite-line residual.
    return .5 * separation[:, None] * (direction - qhat * np.sum(direction * qhat, axis=1)[:, None])


def _solve(tau, midpoint, direction, separation, config):
    design, rhs = _design(tau, midpoint, direction)
    base = np.minimum(separation, config.separation_weight_cap_m)
    base = base / np.median(base)
    weights = base.copy()
    coef = np.zeros(6, dtype=float)
    for iteration in range(config.max_irls_iterations):
        A = (design * weights[:, None, None]).reshape(-1, 6)
        b = (rhs * weights[:, None]).ravel()
        updated, _, rank, singular = np.linalg.lstsq(A, b, rcond=None)
        condition = float(singular[0] / singular[-1]) if singular[-1] > 0 else float("inf")
        residual = np.linalg.norm(np.einsum("nij,j->ni", design, updated) - rhs, axis=1)
        weights = base * np.sqrt(np.minimum(1., config.robust_line_scale_m / np.maximum(residual, 1e-12)))
        delta = np.linalg.norm(updated - coef)
        coef = updated
        if delta < 1e-8:
            break
    diagnostics = {"rank": int(rank), "condition_number": condition,
                   "irls_iterations": iteration + 1, "nonlinear_success": None}
    if rank == 6 and condition <= config.max_condition_number and config.objective == "forward_endpoint":
        optimized = least_squares(
            lambda x: _forward_residual(x, tau, midpoint, direction, separation).ravel(), coef,
            loss="soft_l1", f_scale=config.robust_endpoint_scale_m,
            max_nfev=config.max_nonlinear_evaluations, x_scale="jac",
            ftol=1e-10, xtol=1e-10, gtol=1e-10,
        )
        coef = optimized.x
        singular_forward = np.linalg.svd(optimized.jac, compute_uv=False)
        forward_condition = float(singular_forward[0] / singular_forward[-1]) if singular_forward[-1] > 0 else float("inf")
        diagnostics.update(nonlinear_success=bool(optimized.success), nonlinear_evaluations=int(optimized.nfev),
                           nonlinear_message=optimized.message, forward_condition_number=forward_condition)
    return coef, diagnostics


def fit_trajectory_window(gps_times: np.ndarray, first_xyz: np.ndarray, last_xyz: np.ndarray,
                          config: TrajectoryConfig, *, strip_id: str) -> dict:
    """Fit one local linear trajectory with deterministic, unused pulse holdout.

    Duplicate times are rejected: caller must already separate pulses/strips.
    No discarded pulse is relabelled as a sensor observation. Out-of-support
    predictions and predictions from rejected fits fail in ``predict_origins``.
    Coefficients are training-only; holdout data are never refitted into the model.
    """
    times = np.asarray(gps_times, dtype=np.float64)
    first, last = np.asarray(first_xyz, dtype=np.float64), np.asarray(last_xyz, dtype=np.float64)
    if times.ndim != 1 or first.shape != (len(times), 3) or last.shape != first.shape:
        raise ValueError("times [N], first_xyz [N,3] and last_xyz [N,3] required")
    if not np.isfinite(times).all() or not np.isfinite(first).all() or not np.isfinite(last).all():
        raise ValueError("all input pulse times and coordinates must be finite")
    if len(np.unique(times)) != len(times):
        raise ValueError("duplicate GPS times: identify pulses and separate flight strips upstream")
    if not str(strip_id):
        raise ValueError("explicit strip_id is required")
    order = np.argsort(times, kind="stable")
    separation = np.linalg.norm(last - first, axis=1)
    eligible = separation >= config.min_return_separation_m
    rows = order[eligible[order]]
    rejection = []
    result = {"role": ROLE, "native_Wu_Vallet_reproduction": False, "scientific_verdict": None,
              "strip_id": str(strip_id), "config": asdict(config), "accepted": False,
              "rejection_reasons": rejection, "input_pulses": int(len(times)),
              "eligible_pulses": int(len(rows)), "short_or_zero_separation_rejected": int((~eligible).sum()),
              "return_separation_m": _describe(separation),
              "uncertainty_scope": "bootstrap sampling stability only; systematic direction, time, datum and motion-model errors unbounded"}
    holdout = np.arange(len(rows)) % config.holdout_every == config.holdout_every - 1
    train_rows, test_rows = rows[~holdout], rows[holdout]
    result.update(train_input_rows=train_rows, holdout_input_rows=test_rows)
    if len(train_rows) < config.min_train_pulses or len(test_rows) < config.min_holdout_pulses:
        rejection.append("insufficient_train_or_holdout_pulses")
        return result
    t0 = float((times[train_rows].min() + times[train_rows].max()) * .5)
    time_scale = float((times[train_rows].max() - times[train_rows].min()) * .5)
    if time_scale <= 0:
        rejection.append("no_temporal_extent")
        return result
    anchor = np.mean(.5 * (first[train_rows] + last[train_rows]), axis=0)
    midpoint = .5 * (first + last) - anchor
    direction = np.zeros_like(first)
    direction[eligible] = (last[eligible] - first[eligible]) / separation[eligible, None]
    tau = (times - t0) / time_scale
    coef, solver = _solve(tau[train_rows], midpoint[train_rows], direction[train_rows], separation[train_rows], config)
    result.update(solver=solver, time_origin_s=t0, time_scale_s=time_scale, position_at_time_origin=coef[:3] + anchor,
                  velocity_m_per_s=coef[3:] / time_scale,
                  support_gps_time_s=[float(times[train_rows].min()), float(times[train_rows].max())],
                  fit_model="independent_local_linear_position_plus_velocity")
    if solver["rank"] < 6:
        rejection.append("rank_deficient_beam_time_geometry")
    if solver["condition_number"] > config.max_condition_number:
        rejection.append("ill_conditioned_reverse_fit")
    if solver.get("forward_condition_number", 0.) > config.max_condition_number:
        rejection.append("ill_conditioned_forward_fit")
    if solver["nonlinear_success"] is False:
        rejection.append("forward_optimizer_not_converged")
    if rejection:
        return result
    sensor = coef[:3] + tau[:, None] * coef[3:] + anchor
    qfirst = sensor - first
    line_distance = np.linalg.norm(np.cross(qfirst, direction), axis=1)
    endpoint_distance = np.linalg.norm(_forward_residual(coef, tau, midpoint, direction, separation), axis=1)
    signed_backward_range = -np.sum(qfirst * direction, axis=1)
    distance = np.linalg.norm(qfirst, axis=1)
    forward = (signed_backward_range > 0) & (distance >= config.min_sensor_range_m) & (distance <= config.max_sensor_range_m)
    # Holdout at an interval end can be outside training support; no such sample
    # may validate extrapolation. Record and exclude it explicitly.
    test_in_support = test_rows[(times[test_rows] >= times[train_rows].min()) & (times[test_rows] <= times[train_rows].max())]
    result["holdout_outside_training_support"] = int(len(test_rows) - len(test_in_support))
    result["holdout_validated_input_rows"] = test_in_support
    if len(test_in_support) < config.min_holdout_pulses:
        rejection.append("insufficient_in_support_holdout_pulses")
        return result
    for name, selection in (("train", train_rows), ("holdout", test_in_support)):
        result[name] = {"pulse_count": int(len(selection)), "origin_to_observed_line_m": _describe(line_distance[selection]),
                        "endpoint_to_predicted_ray_m": _describe(endpoint_distance[selection]),
                        "sensor_to_first_return_m": _describe(distance[selection]),
                        "sensor_before_first_and_in_range_fraction": float(forward[selection].mean())}
    if result["holdout"]["origin_to_observed_line_m"]["p90"] > config.max_holdout_line_p90_m:
        rejection.append("holdout_line_residual_exceeded")
    if result["holdout"]["endpoint_to_predicted_ray_m"]["p90"] > config.max_holdout_endpoint_p90_m:
        rejection.append("holdout_endpoint_residual_exceeded")
    if result["holdout"]["sensor_before_first_and_in_range_fraction"] < config.min_forward_fraction:
        rejection.append("sensor_not_before_first_return_or_outside_declared_range")
    if np.linalg.norm(result["velocity_m_per_s"]) > config.max_speed_m_per_s:
        rejection.append("speed_exceeds_declared_guard")
    if rejection:
        return result
    rng = np.random.default_rng(config.random_seed)
    probe_tau = np.array([-1., 0., 1.])
    original_probe = coef[:3] + probe_tau[:, None] * coef[3:]
    bootstrap_coefficients, failed = [], 0
    time_blocks = np.array_split(train_rows, min(config.bootstrap_blocks, len(train_rows)))
    for _ in range(config.bootstrap_repetitions):
        if config.bootstrap_mode == "contiguous_time_blocks":
            selected = np.concatenate([time_blocks[i] for i in rng.integers(0, len(time_blocks), len(time_blocks))])
        else:
            selected = rng.choice(train_rows, size=len(train_rows), replace=True)
        boot_coef, boot_solver = _solve(tau[selected], midpoint[selected], direction[selected], separation[selected], config)
        if (boot_solver["rank"] < 6 or boot_solver["condition_number"] > config.max_condition_number
                or boot_solver.get("forward_condition_number", 0.) > config.max_condition_number
                or boot_solver["nonlinear_success"] is False or not np.isfinite(boot_coef).all()):
            failed += 1
            continue
        bootstrap_coefficients.append(boot_coef)
    if failed or len(bootstrap_coefficients) < config.bootstrap_repetitions:
        rejection.append("bootstrap_fit_failed_or_degenerate")
    if bootstrap_coefficients:
        boot = np.asarray(bootstrap_coefficients)
        boot_probe = boot[:, None, :3] + probe_tau[None, :, None] * boot[:, None, 3:]
        deviations = np.linalg.norm(boot_probe - original_probe[None], axis=2)
        probe_p95 = np.quantile(deviations, .95, axis=0)
        result["bootstrap"] = {"successful": len(boot), "failed": failed, "seed": config.random_seed,
                               "probe_gps_times_s": (t0 + time_scale * probe_tau).tolist(),
                               "origin_displacement_p95_m": probe_p95.tolist(),
                               "max_probe_origin_displacement_p95_m": float(probe_p95.max()),
                               "resampling_unit": config.bootstrap_mode,
                               "time_blocks": len(time_blocks) if config.bootstrap_mode == "contiguous_time_blocks" else None,
                               "independent_sensor_observations": False}
        result["bootstrap_position_at_time_origin"] = boot[:, :3] + anchor
        result["bootstrap_velocity_m_per_s"] = boot[:, 3:] / time_scale
        if probe_p95.max() > config.max_bootstrap_origin_p95_m:
            rejection.append("bootstrap_origin_instability")
    result["accepted"] = not rejection
    return result


def predict_origins(fit: dict, gps_times: np.ndarray) -> np.ndarray:
    """Evaluate an accepted estimated-origin model only within training support."""
    if fit.get("role") != ROLE or not fit.get("accepted", False):
        raise ValueError("accepted estimated-origin fit required")
    times = np.asarray(gps_times, dtype=np.float64)
    if times.ndim != 1 or not np.isfinite(times).all():
        raise ValueError("gps_times must be finite [N]")
    lower, upper = fit["support_gps_time_s"]
    if np.any((times < lower) | (times > upper)):
        raise ValueError("GPS times outside training support; extrapolation prohibited")
    return np.asarray(fit["position_at_time_origin"])[None] + (times - fit["time_origin_s"])[:, None] * np.asarray(fit["velocity_m_per_s"])[None]


def json_safe(value):
    """Serialize diagnostics and arrays without non-standard JSON Infinity/NaN."""
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value

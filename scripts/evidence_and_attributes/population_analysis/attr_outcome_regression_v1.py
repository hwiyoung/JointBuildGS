#!/usr/bin/env python3
"""Attribute-to-outcome regression v1.

Observation only: no reconstruction, no retraining, and no image projection.
The container image has numpy/matplotlib but not pandas/scipy/statsmodels, so
the small regression routines below are implemented directly with numpy.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


RUN_ID = "20260706_regression_v1"
ROBUST_EXCLUDE_IDS = {
    "DEBY_LOD2_42364663",
    "DEBY_LOD2_42364667",
    "DEBY_LOD2_104586480",
}
ARMS = ("raw_dense", "raw_lidar", "raw_acmp")
ARM_LABELS = {"raw_dense": "DIM", "raw_lidar": "LiDAR", "raw_acmp": "ACMP"}
W2_INPUT = {"raw_dense": "DIM", "raw_lidar": "ALS"}
ATTR_COLS = [
    "pt_density_m2_reg",
    "coverage_frac_reg",
    "local_plane_rms_m",
    "floater_frac",
    "label_proxy_frac_all",
]
ATTR_LABELS = {
    "pt_density_m2_reg": "density",
    "coverage_frac_reg": "coverage",
    "local_plane_rms_m": "local_RMS",
    "floater_frac": "floater",
    "label_proxy_frac_all": "label_all",
    "label_proxy_frac_ground": "label_ground",
    "m3c2_rms_m": "M3C2_RMS",
}
OBS_COLS = [
    "median_incidence_deg",
    "median_pair_angle_deg",
    "n_views_nadir",
    "recon_score_median",
]
SPECS = {
    "attributes_only": ATTR_COLS,
    "observation_only": OBS_COLS,
    "attributes_plus_observation": ATTR_COLS + OBS_COLS,
}
OUTCOMES = [
    ("assembled", "binary"),
    ("val3dity_valid", "binary"),
    ("rf_rmse_lod22", "continuous"),
    ("rf_roof_planes", "continuous"),
]
COOK_THRESHOLD_FORMULA = "4/n"
SCOPE_SENTENCE = (
    "본 회귀의 주판 = 원래 점군(= §1.5 v1.13의 주 트랙이자 P0 canonical을 낳은 바로 그 점군 — "
    "재료→결과 짝이 인과적으로 정합). GS 점군은 빈7 확정 후 동일 잣대로 측정 "
    "(본 비교 실험), 공용 점군화 ablation은 그때 병기, 확증은 E5."
)
RUN_FINGERPRINT_ROWS = [
    ("status_csv", "phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv", "4412ee47f8665e1a12663629dd66f9c9612f2e9adca54be38c188f2bc521a9b6"),
    ("w2_config", "phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/config.yaml", "65a8435b8e95b5cbeb86d3a2b82a8fed0b07e62737dc7714062a4151eb24bdd3"),
    ("w2_versions", "phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/versions.txt", "4a786bdc66cc29732b208b665c5133aa57af848ff38da8e347d77dc001b9c113"),
    ("w3_repeatability_versions", "phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747/versions.txt", "0071622cde70adc2a4a62e106468fc7d98d59fc6d5587276db7bbe662caf9c82"),
    ("w3_run2_als_status", "phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747/status/run_2/als_default.csv", "43ad02e993ac250516d7ce75ffb7539276a1f2e7e4e3449cd461e0646f06d613"),
    ("w3_run2_dim_status", "phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747/status/run_2/dim_default.csv", "625d49898c140c6d1ecf2dc66196b46a962770a240124049ea9b9493fe826ce1"),
    ("w3_repeatability_building_status", "docs/evidence/p0-audit/w3-quality-integration/tables/W3_2b_roofer_repeatability_building_status.csv", "6a3ca7d8a13407ba0b7ac34cb1d682ccc66aada10adef988a5b4e7d58521c520"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: fmt(row.get(k)) for k in fieldnames})


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            h.update(block)
    return h.hexdigest()


def fmt(value: object, digits: int = 6) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (np.integer, int)):
        return str(int(value))
    if isinstance(value, (np.floating, float)):
        x = float(value)
        if not math.isfinite(x):
            return "none"
        return f"{x:.{digits}f}"
    return str(value)


def num(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        x = float(value)
        return x if math.isfinite(x) else None
    s = str(value).strip()
    if not s or s.lower() in {"none", "nan", "null"}:
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def bool_num(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    s = str(value).strip().lower()
    if s in {"true", "1", "yes"}:
        return 1
    if s in {"false", "0", "no"}:
        return 0
    return None


def median_iqr(vals: Iterable[float]) -> tuple[float | None, float | None, float | None]:
    arr = np.asarray([v for v in vals if v is not None and math.isfinite(float(v))], dtype=float)
    if len(arr) == 0:
        return None, None, None
    return float(np.median(arr)), float(np.percentile(arr, 25)), float(np.percentile(arr, 75))


def nonzero_rate(vals: Iterable[float]) -> tuple[int, int, float | None]:
    arr = [v for v in vals if v is not None and math.isfinite(float(v))]
    if not arr:
        return 0, 0, None
    nz = sum(abs(float(v)) > 1e-12 for v in arr)
    return nz, len(arr), nz / len(arr)


def rankdata(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    i = 0
    while i < len(values):
        j = i + 1
        while j < len(values) and values[order[j]] == values[order[i]]:
            j += 1
        ranks[order[i:j]] = (i + j - 1) / 2.0 + 1.0
        i = j
    return ranks


def pearson(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 3:
        return None
    xs = x - np.mean(x)
    ys = y - np.mean(y)
    den = float(np.sqrt(np.sum(xs * xs) * np.sum(ys * ys)))
    if den <= 0:
        return None
    return float(np.sum(xs * ys) / den)


def spearman(x: list[float], y: list[float]) -> float | None:
    pairs = [(float(a), float(b)) for a, b in zip(x, y) if a is not None and b is not None and math.isfinite(float(a)) and math.isfinite(float(b))]
    if len(pairs) < 3:
        return None
    xa = np.asarray([p[0] for p in pairs], dtype=float)
    ya = np.asarray([p[1] for p in pairs], dtype=float)
    return pearson(rankdata(xa), rankdata(ya))


def safe_sign(x: float | None) -> int:
    if x is None or not math.isfinite(float(x)) or abs(float(x)) < 1e-10:
        return 0
    return 1 if x > 0 else -1


def standardize_matrix(rows: list[dict[str, object]], predictors: list[str], outcome: str, binary: bool) -> dict[str, object] | None:
    used_rows: list[dict[str, object]] = []
    y_vals: list[float] = []
    x_vals: list[list[float]] = []
    for row in rows:
        y = bool_num(row.get(outcome)) if binary else num(row.get(outcome))
        if y is None:
            continue
        xs: list[float] = []
        ok = True
        for col in predictors:
            v = num(row.get(col))
            if v is None:
                ok = False
                break
            xs.append(float(v))
        if not ok:
            continue
        used_rows.append(row)
        y_vals.append(float(y))
        x_vals.append(xs)
    if len(used_rows) == 0:
        return None
    y = np.asarray(y_vals, dtype=float)
    x = np.asarray(x_vals, dtype=float)
    keep: list[int] = []
    means: list[float] = []
    stds: list[float] = []
    kept_predictors: list[str] = []
    for j, col in enumerate(predictors):
        sd = float(np.std(x[:, j], ddof=0))
        if sd <= 1e-12:
            continue
        keep.append(j)
        means.append(float(np.mean(x[:, j])))
        stds.append(sd)
        kept_predictors.append(col)
    if not keep:
        return None
    xk = x[:, keep]
    xz = (xk - np.asarray(means)) / np.asarray(stds)
    X = np.column_stack([np.ones(len(xz)), xz])
    if not binary:
        y_mean = float(np.mean(y))
        y_std = float(np.std(y, ddof=0))
        if y_std > 1e-12:
            yz = (y - y_mean) / y_std
        else:
            yz = y - y_mean
        y_model = yz
    else:
        y_model = y
        y_mean = float(np.mean(y))
        y_std = float(np.std(y, ddof=0))
    return {
        "rows": used_rows,
        "X": X,
        "y": y_model,
        "y_raw": y,
        "predictors": kept_predictors,
        "x_means": means,
        "x_stds": stds,
        "y_mean": y_mean,
        "y_std": y_std,
    }


def pinv_solve(A: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.linalg.pinv(A) @ b


def fit_ols(X: np.ndarray, y: np.ndarray) -> dict[str, object]:
    beta = pinv_solve(X.T @ X, X.T @ y)
    fitted = X @ beta
    resid = y - fitted
    n, p = X.shape
    xtx_inv = np.linalg.pinv(X.T @ X)
    h = np.einsum("ij,jk,ik->i", X, xtx_inv, X)
    sigma2 = float(np.sum(resid * resid) / max(n - p, 1))
    cov = xtx_inv * sigma2
    se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    denom = p * sigma2 * np.maximum((1.0 - h) ** 2, 1e-12)
    cook = (resid * resid) * h / np.maximum(denom, 1e-12)
    return {
        "beta": beta,
        "se": se,
        "cov": cov,
        "fitted": fitted,
        "resid": resid,
        "hat": h,
        "cook": cook,
        "status": "ok",
    }


def fit_huber(X: np.ndarray, y: np.ndarray, c: float = 1.345, max_iter: int = 80, tol: float = 1e-7) -> dict[str, object]:
    ols = fit_ols(X, y)
    beta = np.asarray(ols["beta"], dtype=float)
    weights = np.ones(len(y), dtype=float)
    for _ in range(max_iter):
        resid = y - X @ beta
        scale = 1.4826 * float(np.median(np.abs(resid - np.median(resid))))
        if scale <= 1e-12:
            scale = float(np.sqrt(np.mean(resid * resid))) if len(resid) else 1.0
        if scale <= 1e-12:
            break
        cutoff = c * scale
        weights = np.minimum(1.0, cutoff / np.maximum(np.abs(resid), 1e-12))
        Xw = X * weights[:, None]
        new_beta = pinv_solve(X.T @ Xw, Xw.T @ y)
        if np.max(np.abs(new_beta - beta)) < tol:
            beta = new_beta
            break
        beta = new_beta
    resid = y - X @ beta
    n, p = X.shape
    Xw = X * weights[:, None]
    xtwx_inv = np.linalg.pinv(X.T @ Xw)
    sigma2 = float(np.sum(weights * resid * resid) / max(n - p, 1))
    cov = xtwx_inv * sigma2
    se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    out = dict(ols)
    out.update({"beta": beta, "se": se, "cov": cov, "resid": resid, "weights": weights, "status": "ok"})
    return out


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))


def fit_logistic(X: np.ndarray, y: np.ndarray, max_iter: int = 80, tol: float = 1e-7) -> dict[str, object]:
    if len(np.unique(y)) < 2:
        return {"status": "outcome_single_class"}
    beta = np.zeros(X.shape[1], dtype=float)
    status = "ok"
    for _ in range(max_iter):
        p = sigmoid(X @ beta)
        w = np.maximum(p * (1.0 - p), 1e-8)
        grad = X.T @ (y - p)
        H = X.T @ (X * w[:, None])
        step = pinv_solve(H + np.eye(H.shape[0]) * 1e-8, grad)
        beta_new = beta + step
        if np.max(np.abs(step)) < tol:
            beta = beta_new
            break
        beta = beta_new
    else:
        status = "max_iter"
    p_hat = sigmoid(X @ beta)
    w = np.maximum(p_hat * (1.0 - p_hat), 1e-8)
    H = X.T @ (X * w[:, None])
    cov = np.linalg.pinv(H)
    se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    h = np.einsum("ij,jk,ik->i", X * np.sqrt(w)[:, None], cov, X * np.sqrt(w)[:, None])
    pear = (y - p_hat) / np.sqrt(w)
    p_dim = X.shape[1]
    cook = (pear * pear) * h / np.maximum(p_dim * (1.0 - h) ** 2, 1e-12)
    return {
        "beta": beta,
        "se": se,
        "cov": cov,
        "fitted": p_hat,
        "resid": y - p_hat,
        "hat": h,
        "cook": cook,
        "status": status,
    }


def fit_model(rows: list[dict[str, object]], arm: str, outcome: str, outcome_kind: str, spec: str, predictors: list[str]) -> dict[str, object]:
    binary = outcome_kind == "binary"
    data = standardize_matrix(rows, predictors, outcome, binary)
    result: dict[str, object] = {
        "arm": arm,
        "outcome": outcome,
        "outcome_kind": outcome_kind,
        "spec": spec,
        "predictor_requested": ";".join(predictors),
        "n": 0,
        "status": "no_complete_cases",
        "predictors": [],
        "rows": [],
    }
    if data is None:
        return result
    X = data["X"]
    y = data["y"]
    used_rows = data["rows"]
    result.update({"n": len(used_rows), "predictors": data["predictors"], "rows": used_rows})
    if len(used_rows) <= X.shape[1] + 2:
        result["status"] = "too_few_rows"
        return result
    if binary:
        fit = fit_logistic(X, y)
        fit_type = "logistic"
    else:
        fit = fit_huber(X, y)
        fit_type = "huber_rlm"
        result["ols_fit"] = fit_ols(X, y)
    if fit.get("status") not in {"ok", "max_iter"}:
        result["status"] = str(fit.get("status"))
        return result
    result.update({"status": str(fit.get("status")), "fit_type": fit_type, "fit": fit, "data": data})
    return result


def model_to_coef_rows(model: dict[str, object], variant: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if "fit" not in model:
        return rows
    fit = model["fit"]
    beta = np.asarray(fit["beta"], dtype=float)
    se = np.asarray(fit["se"], dtype=float)
    predictors = list(model["predictors"])
    for j, pred in enumerate(predictors, start=1):
        b = float(beta[j])
        s = float(se[j]) if j < len(se) else None
        rows.append(
            {
                "variant": variant,
                "arm": model["arm"],
                "outcome": model["outcome"],
                "outcome_kind": model["outcome_kind"],
                "spec": model["spec"],
                "fit_type": model.get("fit_type", "none"),
                "n": model["n"],
                "predictor": pred,
                "coef": b,
                "se": s,
                "ci_low": None if s is None else b - 1.96 * s,
                "ci_high": None if s is None else b + 1.96 * s,
                "status": model["status"],
            }
        )
    return rows


def influence_refit_rows(model: dict[str, object], all_rows: list[dict[str, object]], threshold_scale: float = 4.0) -> tuple[list[str], list[dict[str, object]]]:
    if "fit" not in model:
        return [], []
    used = model["rows"]
    fit = model["fit"]
    cooks = np.asarray(fit["cook"], dtype=float)
    threshold = threshold_scale / max(int(model["n"]), 1)
    influential = [str(row["building_id"]) for row, c in zip(used, cooks) if c > threshold]
    if not influential:
        return [], []
    drop = set(influential)
    rows_drop = [r for r in all_rows if r["building_id"] not in drop]
    refit = fit_model(rows_drop, str(model["arm"]), str(model["outcome"]), str(model["outcome_kind"]), str(model["spec"]), SPECS[str(model["spec"])])
    base_beta = {r["predictor"]: r["coef"] for r in model_to_coef_rows(model, "base")}
    out: list[dict[str, object]] = []
    for row in model_to_coef_rows(refit, "cook_excluded"):
        pred = row["predictor"]
        base = base_beta.get(pred)
        row["base_coef"] = base
        row["coef_delta_from_base"] = None if base is None else row["coef"] - base
        row["sign_flip_vs_base"] = safe_sign(row["coef"]) != safe_sign(base)
        out.append(row)
    return influential, out


def vif_rows(rows: list[dict[str, object]], arm: str, predictors: list[str]) -> list[dict[str, object]]:
    data = standardize_matrix(rows, predictors, predictors[0], binary=False)
    # standardize_matrix expects an outcome; use manual complete-case matrix instead.
    used: list[list[float]] = []
    for row in rows:
        vals: list[float] = []
        ok = True
        for col in predictors:
            v = num(row.get(col))
            if v is None:
                ok = False
                break
            vals.append(v)
        if ok:
            used.append(vals)
    if len(used) < len(predictors) + 3:
        return []
    Xraw = np.asarray(used, dtype=float)
    keep = [j for j in range(Xraw.shape[1]) if np.std(Xraw[:, j]) > 1e-12]
    out: list[dict[str, object]] = []
    for j in keep:
        y = Xraw[:, j]
        others = [k for k in keep if k != j]
        X = Xraw[:, others]
        X = (X - np.mean(X, axis=0)) / np.std(X, axis=0)
        X = np.column_stack([np.ones(len(X)), X])
        yz = (y - np.mean(y)) / np.std(y)
        fit = fit_ols(X, yz)
        resid = np.asarray(fit["resid"], dtype=float)
        sse = float(np.sum(resid * resid))
        sst = float(np.sum((yz - np.mean(yz)) ** 2))
        r2 = 1.0 - sse / sst if sst > 0 else None
        vif = None if r2 is None or r2 >= 0.999999 else 1.0 / (1.0 - r2)
        out.append({"arm": arm, "predictor": predictors[j], "n": len(Xraw), "r2_on_others": r2, "vif": vif})
    return out


def read_acmp_outcome(repo: Path, bid: str) -> dict[str, object]:
    city = repo / "phases/p0-audit/runs/mob_eval/raw_acmp" / f"{bid}_orig.city.json"
    out = {"rf_rmse_lod22": None, "rf_roof_planes": None}
    if not city.exists():
        return out
    data = json.loads(city.read_text(encoding="utf-8"))
    obj = data.get("CityObjects", {}).get(bid)
    if obj is None and data.get("CityObjects"):
        obj = next(iter(data["CityObjects"].values()))
    attrs = (obj or {}).get("attributes", {})
    out["rf_rmse_lod22"] = attrs.get("rf_rmse_lod22")
    out["rf_roof_planes"] = attrs.get("rf_roof_planes")
    return out


def build_snapshot(repo: Path, args) -> list[dict[str, object]]:
    attr = read_csv(repo / args.attr_csv)
    aux = {r["building_id"]: r for r in read_csv(repo / args.population)}
    manual = {r["building_id"]: r for r in read_csv(repo / args.manual_judgments)}
    status = {(r["input"], r["building_id"]): r for r in read_csv(repo / args.w2_status)}
    run2 = {}
    for input_label, rel in [
        ("ALS", "phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747/status/run_2/als_default.csv"),
        ("DIM", "phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747/status/run_2/dim_default.csv"),
    ]:
        for row in read_csv(repo / rel):
            run2[(input_label, row["building_id"])] = row
    gen = {f"DEBY_LOD2_{r['bid']}": r for r in read_csv(repo / args.gen_8way)}

    rows: list[dict[str, object]] = []
    for r in attr:
        arm = r["arm"]
        if arm == "raw_acmp" and r["building_id"] not in gen:
            continue
        if arm not in ARMS:
            continue
        bid = r["building_id"]
        ar = aux[bid]
        no_points = int(float(num(r.get("n_points_footprint")) or 0.0)) == 0
        row: dict[str, object] = {
            "building_id": bid,
            "arm": arm,
            "input_kind": ARM_LABELS[arm],
            "crs_xy": r.get("crs_xy", "EPSG:25832"),
            "clip_source": r.get("clip_source"),
            "fallback_clip_source": str(r.get("clip_source", "")).startswith("fallback"),
            "no_points_recode": no_points,
            "robust_exclude": bid in ROBUST_EXCLUDE_IDS,
            "robust_exclude_reason": (
                "ref_shape_confirmed" if bid == "DEBY_LOD2_42364663" else
                "ref_shape_likely" if bid == "DEBY_LOD2_42364667" else
                "temporal_candidate" if bid == "DEBY_LOD2_104586480" else "none"
            ),
            "manual_label": manual.get(bid, {}).get("label", "none"),
            "manual_label_available": bid in manual,
            "ref_roof_planes": num(r.get("ref_roof_surface_count")),
            "footprint_area_m2": num(r.get("footprint_area_m2")),
            "pt_density_m2": num(r.get("pt_density_m2")),
            "coverage_frac": num(r.get("coverage_frac")),
            "pt_density_m2_reg": 0.0 if no_points else num(r.get("pt_density_m2")),
            "coverage_frac_reg": 0.0 if no_points else num(r.get("coverage_frac")),
            "local_plane_rms_m": num(r.get("local_plane_rms_m")),
            "m3c2_rms_m": num(r.get("m3c2_rms_m")),
            "floater_frac": num(r.get("floater_frac")),
            "label_proxy_frac_all": num(r.get("label_proxy_frac_all")),
            "label_proxy_frac_ground": num(r.get("label_proxy_frac_ground")),
            "attr_missing_local_rms": num(r.get("local_plane_rms_m")) is None,
            "attr_missing_m3c2": num(r.get("m3c2_rms_m")) is None,
            "attr_missing_floater": num(r.get("floater_frac")) is None,
            "attr_missing_label_all": num(r.get("label_proxy_frac_all")) is None,
            "attr_missing_label_ground": num(r.get("label_proxy_frac_ground")) is None,
        }
        for col in [
            "n_exterior_vertices",
            "n_views_nadir",
            "n_views_oblique",
            "n_views_total",
            "median_pair_angle_deg",
            "frac_pairs_10_60deg",
            "median_incidence_deg",
            "frac_views_incidence_le60",
            "roof_obs_covered_frac",
            "recon_score_median",
            "recon_score_p10",
            "roof_lowtex_v5",
            "occlusion_frac_approx",
        ]:
            row[col] = num(ar.get(col))
        if arm in W2_INPUT:
            st = status[(W2_INPUT[arm], bid)]
            row.update(
                {
                    "outcome_source": "w2_1",
                    "assembled": bool_num(st.get("has_lod22")),
                    "val3dity_valid": bool_num(st.get("val3dity_valid")),
                    "rf_rmse_lod22": num(st.get("rf_rmse_lod22")),
                    "rf_roof_planes": num(st.get("rf_roof_planes")),
                }
            )
            st2 = run2.get((W2_INPUT[arm], bid))
            row.update(
                {
                    "run2_available": st2 is not None,
                    "run2_assembled": None if st2 is None else bool_num(st2.get("has_lod22")),
                    "run2_val3dity_valid": None if st2 is None else bool_num(st2.get("val3dity_valid")),
                    "run2_rf_rmse_lod22": None if st2 is None else num(st2.get("rf_rmse_lod22")),
                    "run2_rf_roof_planes": None if st2 is None else num(st2.get("rf_roof_planes")),
                }
            )
        else:
            gr = gen[bid]
            acmp = read_acmp_outcome(repo, bid)
            row.update(
                {
                    "outcome_source": "gen_8way_raw_acmp",
                    "assembled": bool_num(gr.get("raw_acmp")),
                    "val3dity_valid": bool_num(gr.get("raw_acmp_val")),
                    "rf_rmse_lod22": num(acmp.get("rf_rmse_lod22")),
                    "rf_roof_planes": num(acmp.get("rf_roof_planes")),
                    "run2_available": False,
                    "run2_assembled": None,
                    "run2_val3dity_valid": None,
                    "run2_rf_rmse_lod22": None,
                    "run2_rf_roof_planes": None,
                }
            )
        rows.append(row)
    return rows


def add_strata(rows: list[dict[str, object]]) -> None:
    def bins(values: dict[str, float]) -> dict[str, str]:
        arr = np.asarray(list(values.values()), dtype=float)
        q1, q2 = np.percentile(arr, [33.333, 66.667])
        out = {}
        for k, v in values.items():
            out[k] = "low" if v <= q1 else ("mid" if v <= q2 else "high")
        return out

    by_bid: dict[str, dict[str, object]] = {}
    for row in rows:
        by_bid.setdefault(str(row["building_id"]), row)
    complexity = bins({bid: float(row["ref_roof_planes"] or 0.0) for bid, row in by_bid.items()})
    size = bins({bid: float(row["footprint_area_m2"] or 0.0) for bid, row in by_bid.items()})
    obs = bins({bid: float(row["recon_score_median"] or 0.0) for bid, row in by_bid.items()})
    for row in rows:
        bid = str(row["building_id"])
        row["stratum_complexity_ref_roof_planes"] = complexity[bid]
        row["stratum_size_area"] = size[bid]
        row["stratum_observation_recon_score"] = obs[bid]


def fit_all(rows: list[dict[str, object]], variant: str = "main", outcome_prefix: str = "") -> tuple[list[dict[str, object]], list[dict[str, object]], dict[tuple[str, str, str], dict[str, object]]]:
    coef_rows: list[dict[str, object]] = []
    diag_rows: list[dict[str, object]] = []
    models: dict[tuple[str, str, str], dict[str, object]] = {}
    for arm in ARMS:
        arm_rows = [r for r in rows if r["arm"] == arm]
        for outcome_base, kind in OUTCOMES:
            outcome = f"{outcome_prefix}{outcome_base}" if outcome_prefix else outcome_base
            for spec, predictors in SPECS.items():
                model = fit_model(arm_rows, arm, outcome, kind, spec, predictors)
                models[(arm, outcome_base, spec)] = model
                coef_rows.extend(model_to_coef_rows(model, variant))
                infl, refit_rows = influence_refit_rows(model, arm_rows)
                coef_rows.extend([{**r, "variant": f"{variant}_cook_excluded"} for r in refit_rows])
                diag_rows.append(
                    {
                        "variant": variant,
                        "arm": arm,
                        "outcome": outcome_base,
                        "spec": spec,
                        "n": model.get("n", 0),
                        "status": model.get("status", "none"),
                        "cook_threshold": None if not model.get("n") else 4.0 / int(model["n"]),
                        "n_cook_gt_4_over_n": len(infl),
                        "cook_gt_4_over_n_buildings": ";".join(infl) if infl else "none",
                    }
                )
    return coef_rows, diag_rows, models


def robust_exclusion_models(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    kept = [r for r in rows if not r["robust_exclude"]]
    coefs, diag, _ = fit_all(kept, "robust_exclusion")
    return coefs, diag


def fallback_dummy_sensitivity(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    old = SPECS["attributes_plus_observation"]
    SPECS["attributes_plus_observation_fallback"] = old + ["fallback_clip_source"]
    out: list[dict[str, object]] = []
    for arm in ARMS:
        arm_rows = [r for r in rows if r["arm"] == arm]
        for outcome, kind in OUTCOMES:
            model = fit_model(arm_rows, arm, outcome, kind, "attributes_plus_observation_fallback", SPECS["attributes_plus_observation_fallback"])
            out.extend(model_to_coef_rows(model, "fallback_dummy_sensitivity"))
    SPECS.pop("attributes_plus_observation_fallback")
    return out


def label_ground_sensitivity(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    predictors = [
        "pt_density_m2_reg",
        "coverage_frac_reg",
        "local_plane_rms_m",
        "floater_frac",
        "label_proxy_frac_ground",
    ] + OBS_COLS
    out: list[dict[str, object]] = []
    for arm in ARMS:
        arm_rows = [r for r in rows if r["arm"] == arm]
        for outcome, kind in OUTCOMES:
            model = fit_model(arm_rows, arm, outcome, kind, "label_ground_plus_observation", predictors)
            out.extend(model_to_coef_rows(model, "label_ground_sensitivity"))
    return out


def run2_sensitivity(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    out: list[dict[str, object]] = []
    summary: list[dict[str, object]] = []
    overlap = [r for r in rows if r["arm"] in {"raw_dense", "raw_lidar"} and r["run2_available"]]
    # Fit w2 on the same 93-row overlap and run_2 with only the outcome columns swapped.
    w2_coefs, _, w2_models = fit_all(overlap, "w2_overlap")
    out.extend(w2_coefs)
    run2_rows = []
    for r in overlap:
        nr = dict(r)
        for outcome, _ in OUTCOMES:
            nr[outcome] = nr.get(f"run2_{outcome}")
        run2_rows.append(nr)
    run2_coefs, _, run2_models = fit_all(run2_rows, "run2_outcome_sensitivity")
    out.extend(run2_coefs)
    for arm in ("raw_dense", "raw_lidar"):
        for outcome, _ in OUTCOMES:
            key = (arm, outcome, "attributes_plus_observation")
            a = {r["predictor"]: r for r in model_to_coef_rows(w2_models.get(key, {}), "tmp") if r["predictor"] in ATTR_COLS}
            b = {r["predictor"]: r for r in model_to_coef_rows(run2_models.get(key, {}), "tmp") if r["predictor"] in ATTR_COLS}
            common = sorted(set(a).intersection(b))
            sign_matches = 0
            ratios = []
            for pred in common:
                ca = float(a[pred]["coef"])
                cb = float(b[pred]["coef"])
                if safe_sign(ca) == safe_sign(cb):
                    sign_matches += 1
                if abs(ca) > 1e-10:
                    ratios.append(abs(cb) / abs(ca))
            med_ratio, q1, q3 = median_iqr(ratios)
            summary.append(
                {
                    "arm": arm,
                    "outcome": outcome,
                    "common_attr_coef": len(common),
                    "sign_matches": sign_matches,
                    "median_abs_coef_ratio_run2_over_w2overlap": med_ratio,
                    "iqr_abs_coef_ratio": None if q1 is None else f"{q1:.3g}-{q3:.3g}",
                }
            )
    return out, summary


def ordinary_vs_robust(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for arm in ARMS:
        arm_rows = [r for r in rows if r["arm"] == arm]
        for outcome, kind in OUTCOMES:
            if kind != "continuous":
                continue
            for spec, predictors in SPECS.items():
                model = fit_model(arm_rows, arm, outcome, kind, spec, predictors)
                if "fit" not in model or "ols_fit" not in model:
                    continue
                robust_beta = np.asarray(model["fit"]["beta"])
                ols_beta = np.asarray(model["ols_fit"]["beta"])
                for j, pred in enumerate(model["predictors"], start=1):
                    mismatch = safe_sign(float(robust_beta[j])) != safe_sign(float(ols_beta[j]))
                    out.append(
                        {
                            "variant": "ordinary_vs_robust_sign",
                            "arm": arm,
                            "outcome": outcome,
                            "spec": spec,
                            "predictor": pred,
                            "robust_coef": float(robust_beta[j]),
                            "ordinary_coef": float(ols_beta[j]),
                            "sign_mismatch": mismatch,
                            "note": "소수 사례 의존 기록" if mismatch else "same_sign",
                        }
                    )
    return out


def attr_descriptive(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    features = ATTR_COLS + ["m3c2_rms_m", "label_proxy_frac_ground"]
    for arm in ARMS:
        arm_rows = [r for r in rows if r["arm"] == arm]
        for col in features:
            vals = [num(r.get(col)) for r in arm_rows]
            present = [v for v in vals if v is not None]
            med, q1, q3 = median_iqr(present)
            nz, n, rate = nonzero_rate(present)
            out.append(
                {
                    "arm": arm,
                    "axis": col,
                    "n": n,
                    "missing": len(arm_rows) - n,
                    "median": med,
                    "iqr": None if q1 is None else f"{q1:.4g}-{q3:.4g}",
                    "nonzero_n": nz,
                    "nonzero_rate": rate,
                }
            )
    return out


def correlation_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for arm in ARMS:
        arm_rows = [r for r in rows if r["arm"] == arm]
        for i, a in enumerate(ATTR_COLS):
            for b in ATTR_COLS[i + 1:]:
                xs, ys = [], []
                for r in arm_rows:
                    x, y = num(r.get(a)), num(r.get(b))
                    if x is not None and y is not None:
                        xs.append(x)
                        ys.append(y)
                out.append({"arm": arm, "x": a, "y": b, "n": len(xs), "pearson_r": pearson(np.asarray(xs), np.asarray(ys)) if xs else None, "spearman_rho": spearman(xs, ys)})
    return out


def spearman_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for arm in ARMS:
        arm_rows = [r for r in rows if r["arm"] == arm]
        for outcome, kind in OUTCOMES:
            if kind != "continuous":
                continue
            for col in ATTR_COLS + ["m3c2_rms_m"]:
                xs, ys = [], []
                for r in arm_rows:
                    x, y = num(r.get(col)), num(r.get(outcome))
                    if x is not None and y is not None:
                        xs.append(x)
                        ys.append(y)
                out.append({"arm": arm, "outcome": outcome, "axis": col, "n": len(xs), "spearman_rho": spearman(xs, ys)})
    return out


def stratification_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    lenses = [
        ("complexity", "stratum_complexity_ref_roof_planes"),
        ("size", "stratum_size_area"),
        ("observation", "stratum_observation_recon_score"),
        ("manual_failure_label", "manual_label"),
    ]
    out: list[dict[str, object]] = []
    for arm in ARMS:
        arm_rows = [r for r in rows if r["arm"] == arm]
        for lens, col in lenses:
            values = sorted({str(r.get(col, "none")) for r in arm_rows if lens != "manual_failure_label" or r.get("manual_label_available")})
            for val in values:
                sub = [r for r in arm_rows if str(r.get(col, "none")) == val and (lens != "manual_failure_label" or r.get("manual_label_available"))]
                if not sub:
                    continue
                assembled = [num(r.get("assembled")) for r in sub if num(r.get("assembled")) is not None]
                valid = [num(r.get("val3dity_valid")) for r in sub if num(r.get("val3dity_valid")) is not None]
                rmse = [num(r.get("rf_rmse_lod22")) for r in sub if num(r.get("rf_rmse_lod22")) is not None]
                density = [num(r.get("pt_density_m2_reg")) for r in sub if num(r.get("pt_density_m2_reg")) is not None]
                coverage = [num(r.get("coverage_frac_reg")) for r in sub if num(r.get("coverage_frac_reg")) is not None]
                out.append(
                    {
                        "arm": arm,
                        "lens": lens,
                        "stratum": val,
                        "n": len(sub),
                        "assembled_rate": None if not assembled else float(np.mean(assembled)),
                        "valid_rate": None if not valid else float(np.mean(valid)),
                        "rmse_median": median_iqr(rmse)[0],
                        "density_median": median_iqr(density)[0],
                        "coverage_median": median_iqr(coverage)[0],
                    }
                )
    return out


def select_representative_buildings(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    dim = [r for r in rows if r["arm"] == "raw_dense"]
    feature_direction = {
        "pt_density_m2_reg": -1.0,
        "coverage_frac_reg": -1.0,
        "local_plane_rms_m": 1.0,
        "floater_frac": 1.0,
        "label_proxy_frac_all": 1.0,
    }
    values: dict[str, tuple[float, float]] = {}
    for col in feature_direction:
        vals = [num(r.get(col)) for r in dim if num(r.get(col)) is not None]
        values[col] = (float(np.median(vals)), float(np.std(vals) or 1.0)) if vals else (0.0, 1.0)
    scored = []
    for r in dim:
        score = 0.0
        n = 0
        for col, direction in feature_direction.items():
            v = num(r.get(col))
            if v is None:
                continue
            med, sd = values[col]
            score += direction * ((v - med) / sd)
            n += 1
        if n:
            score /= n
        scored.append((score, r))
    failures = [x for x in scored if num(x[1].get("assembled")) == 0]
    successes = [x for x in scored if num(x[1].get("assembled")) == 1]
    high_rmse_success = sorted(successes, key=lambda t: num(t[1].get("rf_rmse_lod22")) or -1, reverse=True)
    picks = []
    if failures:
        picks.append(sorted(failures, key=lambda t: t[0], reverse=True)[0][1])
    if high_rmse_success:
        picks.append(high_rmse_success[0][1])
    if successes:
        picks.append(sorted(successes, key=lambda t: t[0])[0][1])
    # Deduplicate while preserving order.
    out = []
    seen = set()
    for r in picks:
        if r["building_id"] not in seen:
            out.append(r)
            seen.add(r["building_id"])
    return out[:3]


def plot_coefficients(coef_rows: list[dict[str, object]], out: Path) -> None:
    rows = [
        r for r in coef_rows
        if r["variant"] == "main"
        and r["spec"] == "attributes_plus_observation"
        and r["predictor"] in ATTR_COLS
    ]
    outcomes = [o for o, _ in OUTCOMES]
    fig, axes = plt.subplots(len(outcomes), 1, figsize=(12, 10), sharex=True)
    colors = {"raw_dense": "#0072B2", "raw_lidar": "#009E73", "raw_acmp": "#D55E00"}
    y_labels = [ATTR_LABELS[p] for p in ATTR_COLS]
    for ax, outcome in zip(axes, outcomes):
        ax.axvline(0, color="0.35", lw=1)
        for ai, arm in enumerate(ARMS):
            sub = [r for r in rows if r["outcome"] == outcome and r["arm"] == arm]
            by = {r["predictor"]: r for r in sub}
            ys, xs, xerr_low, xerr_high = [], [], [], []
            for pi, pred in enumerate(ATTR_COLS):
                rr = by.get(pred)
                if not rr:
                    continue
                b = float(rr["coef"])
                lo = num(rr.get("ci_low"))
                hi = num(rr.get("ci_high"))
                ys.append(pi + (ai - 1) * 0.18)
                xs.append(b)
                xerr_low.append(0 if lo is None else max(0.0, b - lo))
                xerr_high.append(0 if hi is None else max(0.0, hi - b))
            if xs:
                ax.errorbar(xs, ys, xerr=[xerr_low, xerr_high], fmt="o", ms=5, capsize=3, color=colors[arm], label=ARM_LABELS[arm])
        ax.set_yticks(range(len(ATTR_COLS)))
        ax.set_yticklabels(y_labels)
        ax.set_title(outcome)
        ax.grid(True, axis="x", alpha=0.25)
    axes[0].legend(loc="upper right", ncols=3, fontsize=8)
    axes[-1].set_xlabel("standardized coefficient")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)


def plot_representatives(rows: list[dict[str, object]], out: Path) -> None:
    picks = select_representative_buildings(rows)
    features = ATTR_COLS
    fig, axes = plt.subplots(len(picks), 1, figsize=(11, max(3, 2.8 * len(picks))))
    if len(picks) == 1:
        axes = [axes]
    for ax, row in zip(axes, picks):
        vals = []
        labels = []
        for col in features:
            labels.append(ATTR_LABELS[col])
            vals.append(num(row.get(col)) or 0.0)
        # Plot percentile ranks within DIM for a common 0..1 scale.
        dim = [r for r in rows if r["arm"] == "raw_dense"]
        pct = []
        for col, v in zip(features, vals):
            allv = sorted([num(r.get(col)) for r in dim if num(r.get(col)) is not None])
            if not allv:
                pct.append(0.0)
            else:
                pct.append(sum(x <= v for x in allv) / len(allv))
        ax.bar(labels, pct, color=["#0072B2", "#56B4E9", "#CC79A7", "#D55E00", "#E69F00"])
        ax.set_ylim(0, 1)
        ax.set_ylabel("DIM percentile")
        label_flag = "manual-label" if row.get("manual_label", "none") != "none" else "no-manual-label"
        outcome_text = (
            f"assembled={fmt(row.get('assembled'),0)}, valid={fmt(row.get('val3dity_valid'),0)}, "
            f"rmse={fmt(row.get('rf_rmse_lod22'),2)}, planes={fmt(row.get('rf_roof_planes'),0)}, "
            f"{label_flag}"
        )
        ax.set_title(f"{row['building_id']}  {outcome_text}", fontsize=9)
        ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)


def coef_table_lines(coef_rows: list[dict[str, object]], variant: str, spec_filter: str | None = None, max_rows: int | None = None) -> list[str]:
    rows = [r for r in coef_rows if r["variant"] == variant and (spec_filter is None or r["spec"] == spec_filter)]
    if max_rows is not None:
        rows = rows[:max_rows]
    lines = [
        "| arm | outcome | spec | n | predictor | coef | CI95 |",
        "|---|---|---|---:|---|---:|---|",
    ]
    for r in rows:
        ci = f"{fmt(r.get('ci_low'),3)}..{fmt(r.get('ci_high'),3)}"
        lines.append(
            f"| {r['arm']} | {r['outcome']} | {r['spec']} | {r['n']} | {r['predictor']} | {fmt(r['coef'],3)} | {ci} |"
        )
    return lines


def compact_summary_table(rows: list[dict[str, object]], keys: list[str], value_cols: list[str]) -> list[str]:
    lines = ["| " + " | ".join(keys + value_cols) + " |", "| " + " | ".join(["---"] * (len(keys) + len(value_cols))) + " |"]
    for r in rows:
        parts = [str(r.get(k, "none")) for k in keys]
        parts += [fmt(r.get(c), 3) for c in value_cols]
        lines.append("| " + " | ".join(parts) + " |")
    return lines


def sensitivity_compare_summary(
    base_coefs: list[dict[str, object]],
    sens_coefs: list[dict[str, object]],
    sens_variant: str,
    sens_spec: str,
    label_ground: bool = False,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    base_rows = [
        r for r in base_coefs
        if r.get("variant") == "main"
        and r.get("spec") == "attributes_plus_observation"
        and r.get("predictor") in ATTR_COLS
    ]
    sens_rows = [
        r for r in sens_coefs
        if r.get("variant") == sens_variant
        and r.get("spec") == sens_spec
    ]
    for arm in ARMS:
        for outcome, _ in OUTCOMES:
            base_by = {
                str(r["predictor"]): r
                for r in base_rows
                if r["arm"] == arm and r["outcome"] == outcome
            }
            sens_by = {
                str(r["predictor"]): r
                for r in sens_rows
                if r["arm"] == arm and r["outcome"] == outcome
            }
            pairs: list[tuple[str, str]] = []
            for pred in ATTR_COLS:
                spred = "label_proxy_frac_ground" if label_ground and pred == "label_proxy_frac_all" else pred
                if pred in base_by and spred in sens_by:
                    pairs.append((pred, spred))
            sign_matches = 0
            ratios: list[float] = []
            for pred, spred in pairs:
                b = num(base_by[pred].get("coef"))
                s = num(sens_by[spred].get("coef"))
                if b is None or s is None:
                    continue
                if safe_sign(b) == safe_sign(s):
                    sign_matches += 1
                if abs(b) > 1e-10:
                    ratios.append(abs(s) / abs(b))
            med, q1, q3 = median_iqr(ratios)
            out.append(
                {
                    "arm": arm,
                    "outcome": outcome,
                    "common_attr_coef": len(pairs),
                    "sign_matches": sign_matches,
                    "median_abs_coef_ratio": med,
                    "iqr_abs_coef_ratio": None if q1 is None else f"{q1:.3g}-{q3:.3g}",
                }
            )
    return out


def write_report(
    path: Path,
    rows: list[dict[str, object]],
    coef_rows: list[dict[str, object]],
    sensitivity_rows: list[dict[str, object]],
    diag_rows: list[dict[str, object]],
    desc_rows: list[dict[str, object]],
    corr_rows: list[dict[str, object]],
    vif_all: list[dict[str, object]],
    spearman_all: list[dict[str, object]],
    strat_rows: list[dict[str, object]],
    ordinary_sign: list[dict[str, object]],
    run2_summary: list[dict[str, object]],
    out_paths: dict[str, str],
) -> None:
    coverage = Counter((r["arm"], r["outcome_source"]) for r in rows)
    outcome_n = []
    for arm in ARMS:
        arm_rows = [r for r in rows if r["arm"] == arm]
        for outcome, _ in OUTCOMES:
            vals = [r for r in arm_rows if num(r.get(outcome)) is not None]
            outcome_n.append({"arm": arm, "outcome": outcome, "n": len(vals)})
    density_cov = [
        r for r in corr_rows if r["x"] == "pt_density_m2_reg" and r["y"] == "coverage_frac_reg"
    ]
    sign_mismatch = [r for r in ordinary_sign if r["sign_mismatch"]]
    combined_diag = [r for r in diag_rows if r["variant"] == "main" and r["spec"] == "attributes_plus_observation"]
    fallback_summary = sensitivity_compare_summary(
        coef_rows,
        sensitivity_rows,
        "fallback_dummy_sensitivity",
        "attributes_plus_observation_fallback",
    )
    label_summary = sensitivity_compare_summary(
        coef_rows,
        sensitivity_rows,
        "label_ground_sensitivity",
        "label_ground_plus_observation",
        label_ground=True,
    )
    run2_total_common = sum(int(r["common_attr_coef"]) for r in run2_summary)
    run2_total_sign = sum(int(r["sign_matches"]) for r in run2_summary)
    run2_ratios = [num(r.get("median_abs_coef_ratio_run2_over_w2overlap")) for r in run2_summary]
    run2_ratio_med = median_iqr([r for r in run2_ratios if r is not None])[0]
    lines: list[str] = [
        "# W attr-outcome regression v1",
        "",
        "> 재구성/재학습 없음. 이미지-투영 불사용. 판정 없이 수치와 관찰만 기록한다. CRS는 EPSG:25832.",
        "",
        "## 스코프",
        "",
        SCOPE_SENTENCE,
        "",
        "## 결과 런 지문",
        "",
        "| 항목 | 경로 | sha256 |",
        "|---|---|---|",
    ]
    for label, rel, sha in RUN_FINGERPRINT_ROWS:
        lines.append(f"| {label} | `{rel}` | `{sha}` |")
    lines += [
        "",
        "Roofer 1.0.0 · val3dity 2.6.0 · plane_detect_epsilon=0.3 · plane_detect_min_points=15 · complexity_factor=0.888. 결과 변수 4종은 Roofer 내부 산출이다. 외부 참조·높이 상수·이미지 투영과 절연(datum-free, attr-v1.1 [E] 확인).",
        "",
        "## 입력·결측 규약",
        "",
        "- attr 입력: `docs/evidence/archive/pointcloud_attributes/v1_2/tables/pointcloud_attributes_v1_2.csv`.",
        "- 결과 정본 런: w2_1. DIM·LiDAR는 각 199동 전수. ACMP는 `gen_8way` 64동 보조 대장.",
        "- 조립 성공 변수는 status CSV의 `has_lod22`를 썼다. 이는 §3.2의 `roofer_ok·roof_surfaces>0` 정의를 W2 status에서 건물 단위로 저장한 열이다.",
        "- no_points 행은 회귀 입력에서 밀도 0·커버리지 0으로 재코딩했다. 노이즈·M3C2·부유·라벨 미정의는 결측 유지, 모델별 complete-case n을 표에 기록했다.",
        "- 로버스트 제외 목록: 42364663, 42364667, 104586480. attr의 ref_invalid 플래그는 참고 열로 유지했다.",
        "- 라벨 축 주지표는 `label_proxy_frac_all`; `label_proxy_frac_ground`는 감도 재추정에만 썼다.",
        "",
        "입력 커버리지:",
        "",
        "| arm | source | rows |",
        "|---|---|---:|",
    ]
    for (arm, src), n in sorted(coverage.items()):
        lines.append(f"| {arm} | {src} | {n} |")
    lines += [
        "",
        "결과 변수별 사용 가능 행:",
        "",
        *compact_summary_table(outcome_n, ["arm", "outcome"], ["n"]),
        "",
        "## 기술 통계",
        "",
        "| arm | axis | n | missing | median | IQR | nonzero_n | nonzero_rate |",
        "|---|---|---:|---:|---:|---|---:|---:|",
    ]
    for r in desc_rows:
        lines.append(
            f"| {r['arm']} | {r['axis']} | {r['n']} | {r['missing']} | {fmt(r['median'],4)} | {r['iqr']} | {r['nonzero_n']} | {fmt(r['nonzero_rate'],3)} |"
        )
    lines += [
        "",
        "## 다중공선성 점검",
        "",
        "밀도↔커버리지 상관:",
        "",
        "| arm | n | Pearson r | Spearman rho |",
        "|---|---:|---:|---:|",
    ]
    for r in density_cov:
        lines.append(f"| {r['arm']} | {r['n']} | {fmt(r['pearson_r'],3)} | {fmt(r['spearman_rho'],3)} |")
    lines += [
        "",
        "VIF:",
        "",
        "| arm | predictor | n | VIF |",
        "|---|---|---:|---:|",
    ]
    for r in vif_all:
        lines.append(f"| {r['arm']} | {r['predictor']} | {r['n']} | {fmt(r['vif'],2)} |")
    lines += [
        "",
        "## 주 회귀 계수표",
        "",
        "아래 표는 3사양×4결과의 계수다. 모든 predictor는 모델 안에서 표준화했다. 연속 결과는 y도 표준화했다.",
        "",
        *coef_table_lines(coef_rows, "main"),
        "",
        "## 연속 결과 Spearman",
        "",
        "| arm | outcome | axis | n | Spearman rho |",
        "|---|---|---|---:|---:|",
    ]
    for r in spearman_all:
        lines.append(f"| {r['arm']} | {r['outcome']} | {r['axis']} | {r['n']} | {fmt(r['spearman_rho'],3)} |")
    lines += [
        "",
        "## 로버스트·감도",
        "",
        "로버스트 제외 재추정(속성+관측기하 사양):",
        "",
        *coef_table_lines(coef_rows, "robust_exclusion", "attributes_plus_observation"),
        "",
        "run_2 결과 변수 교체 감도(겹치는 93동, 속성+관측기하 사양의 속성 계수만 비교):",
        "",
        "| arm | outcome | common_attr_coef | sign_matches | median_abs_coef_ratio | IQR |",
        "|---|---|---:|---:|---:|---|",
    ]
    for r in run2_summary:
        lines.append(
            f"| {r['arm']} | {r['outcome']} | {r['common_attr_coef']} | {r['sign_matches']} | "
            f"{fmt(r['median_abs_coef_ratio_run2_over_w2overlap'],3)} | {r['iqr_abs_coef_ratio']} |"
        )
    lines += [
        "",
        f"- run_2 감도 전체: 속성 계수 부호 일치 {run2_total_sign}/{run2_total_common}, |계수| 비율 중앙값 {fmt(run2_ratio_med,3)}.",
        "",
        "label_proxy_frac_ground 교체 감도(속성+관측기하 사양):",
        "",
        "| arm | outcome | common_attr_coef | sign_matches | median_abs_coef_ratio | IQR |",
        "|---|---|---:|---:|---:|---|",
    ]
    for r in label_summary:
        lines.append(
            f"| {r['arm']} | {r['outcome']} | {r['common_attr_coef']} | {r['sign_matches']} | "
            f"{fmt(r['median_abs_coef_ratio'],3)} | {r['iqr_abs_coef_ratio']} |"
        )
    lines += [
        "",
        "fallback clip_source 더미 추가 감도(속성+관측기하 사양):",
        "",
        "| arm | outcome | common_attr_coef | sign_matches | median_abs_coef_ratio | IQR |",
        "|---|---|---:|---:|---:|---|",
    ]
    for r in fallback_summary:
        lines.append(
            f"| {r['arm']} | {r['outcome']} | {r['common_attr_coef']} | {r['sign_matches']} | "
            f"{fmt(r['median_abs_coef_ratio'],3)} | {r['iqr_abs_coef_ratio']} |"
        )
    lines += [
        "",
        "감도 계수 전수는 `docs/experiments/evaluation/attr_outcome_regression/tables/attr_outcome_regression_sensitivity_v1.csv`에 기록했다.",
        "",
        "일반 추정(OLS)과 로버스트 추정(Huber) 부호 불일치:",
        "",
    ]
    if sign_mismatch:
        lines += [
            "| arm | outcome | spec | predictor | robust | ordinary | note |",
            "|---|---|---|---|---:|---:|---|",
        ]
        for r in sign_mismatch:
            lines.append(
                f"| {r['arm']} | {r['outcome']} | {r['spec']} | {r['predictor']} | {fmt(r['robust_coef'],3)} | {fmt(r['ordinary_coef'],3)} | {r['note']} |"
            )
    else:
        lines.append("- none.")
    lines += [
        "",
        "## 영향점 진단",
        "",
        "Cook's distance > 4/n 목록(속성+관측기하 사양):",
        "",
        "| arm | outcome | n | threshold | n_ids | IDs |",
        "|---|---|---:|---:|---:|---|",
    ]
    for r in combined_diag:
        lines.append(
            f"| {r['arm']} | {r['outcome']} | {r['n']} | {fmt(r['cook_threshold'],4)} | {r['n_cook_gt_4_over_n']} | {r['cook_gt_4_over_n_buildings']} |"
        )
    lines += [
        "",
        "영향점 제외 재추정 계수는 `docs/experiments/evaluation/attr_outcome_regression/tables/attr_outcome_regression_coefficients_v1.csv`의 `*_cook_excluded` variant에 기록했다. 영향점 목록 전수는 `docs/experiments/evaluation/attr_outcome_regression/tables/attr_outcome_regression_diagnostics_v1.csv`에 기록했다.",
        "",
        "## 층화 병기",
        "",
        "| arm | lens | stratum | n | assembled_rate | valid_rate | rmse_median | density_median | coverage_median |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in strat_rows:
        lines.append(
            f"| {r['arm']} | {r['lens']} | {r['stratum']} | {r['n']} | {fmt(r['assembled_rate'],3)} | {fmt(r['valid_rate'],3)} | {fmt(r['rmse_median'],3)} | {fmt(r['density_median'],3)} | {fmt(r['coverage_median'],3)} |"
        )
    lines += [
        "",
        "## 그림",
        "",
        f"- 계수 그림: `{out_paths['coef_fig']}`",
        f"- 대표 건물 속성-결과 패널: `{out_paths['rep_fig']}`",
        "",
        "## 관찰",
        "",
    ]
    for arm in ARMS:
        sub = [r for r in coef_rows if r["variant"] == "main" and r["arm"] == arm and r["spec"] == "attributes_plus_observation" and r["predictor"] in ATTR_COLS]
        if not sub:
            continue
        strongest = sorted(sub, key=lambda r: abs(float(r["coef"])), reverse=True)[:3]
        txt = ", ".join(f"{r['outcome']}:{r['predictor']}={fmt(r['coef'],2)}" for r in strongest)
        lines.append(f"- {arm}: 속성+관측기하 사양에서 절대값 상위 속성 계수는 {txt}.")
    lines += [
        "- 위 문장은 계수 크기 순서만 적은 관찰이다. 원인·채택·강등 판정은 포함하지 않는다.",
        "",
        "## 산출 파일",
        "",
        f"- 회귀 입력 스냅샷: `{out_paths['snapshot']}`",
        "- 계수 전수: `docs/experiments/evaluation/attr_outcome_regression/tables/attr_outcome_regression_coefficients_v1.csv`",
        "- 영향점 전수: `docs/experiments/evaluation/attr_outcome_regression/tables/attr_outcome_regression_diagnostics_v1.csv`",
        "- 감도 전수: `docs/experiments/evaluation/attr_outcome_regression/tables/attr_outcome_regression_sensitivity_v1.csv`",
        f"- versions: `{out_paths['versions']}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_versions(path: Path, repo: Path, args, fps: dict[str, tuple[str, str]], counts: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def cmd_out(cmd: list[str]) -> str:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            return f"not_available:{exc.filename}"
        return (r.stdout or r.stderr).strip()

    lines = [
        f"run_id: {RUN_ID}",
        "task: regression-v1",
        f"created_utc: {datetime.now(timezone.utc).isoformat()}",
        "mode: observation only; no reconstruction; no retraining; no image projection",
        "crs_xy: EPSG:25832",
        f"git_head: {cmd_out(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch: {cmd_out(['git', 'branch', '--show-current'])}",
        "docker_image: jointbuildgs-p0-tools:t0",
        'run_command: docker run --rm --user "$(id -u):$(id -g)" -v "$PWD":/workspace/JointBuildGS -w /workspace/JointBuildGS jointbuildgs-p0-tools:t0 python3 scripts/evidence_and_attributes/population_analysis/attr_outcome_regression_v1.py',
        f"python: {cmd_out(['python3', '--version'])}",
        "packages: numpy + matplotlib; regression routines implemented in script",
        "",
        "design:",
        "  canonical_result_run: w2_1_roofer_default_20260612_152729",
        "  run2_role: sensitivity only, 93 overlap rows per DIM/LiDAR",
        "  robust_exclude_ids: DEBY_LOD2_42364663;DEBY_LOD2_42364667;DEBY_LOD2_104586480",
        "  label_main: label_proxy_frac_all",
        "  label_sensitivity: label_proxy_frac_ground",
        "  no_points_recode: density=0 coverage=0",
        "",
        "counts:",
    ]
    for k, v in counts.items():
        lines.append(f"  {k}: {v}")
    lines += ["", "inputs_with_sha256:"]
    for label, (rel, sha) in fps.items():
        lines.append(f"  {label}: {rel} sha256={sha}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def source_fingerprints(repo: Path, args) -> dict[str, tuple[str, str]]:
    paths = {
        "script": Path(__file__).resolve(),
        "attr_v1_2": repo / args.attr_csv,
        "population_aux_v4": repo / args.population,
        "manual_review_judgments": repo / args.manual_judgments,
        "w2_status": repo / args.w2_status,
        "w3_run2_als": repo / "phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747/status/run_2/als_default.csv",
        "w3_run2_dim": repo / "phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747/status/run_2/dim_default.csv",
        "gen_8way": repo / args.gen_8way,
        "basis_document": repo / "docs/research/methodology/기준문서_방법론·모집단·비교설계_v1.md",
    }
    out = {}
    for label, path in paths.items():
        if path.exists():
            rel = str(path.relative_to(repo)) if path.is_absolute() and path.is_relative_to(repo) else str(path)
            out[label] = (rel, sha256_file(path))
    return out


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attr-csv", default="docs/evidence/archive/pointcloud_attributes/v1_2/tables/pointcloud_attributes_v1_2.csv")
    ap.add_argument("--population", default="docs/experiments/input-and-alignment/population_aux/tables/population_aux_v4.csv")
    ap.add_argument("--manual-judgments", default="docs/research/methodology/tables/manual_review_judgments.csv")
    ap.add_argument("--w2-status", default="phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv")
    ap.add_argument("--gen-8way", default="results/tum_transfer/mob/overseg_lever/gen_8way.csv")
    ap.add_argument("--out-report", default="docs/experiments/evaluation/attr_outcome_regression/reports/W_attr_outcome_regression.md")
    ap.add_argument("--out-snapshot", default="docs/experiments/evaluation/attr_outcome_regression/tables/regression_input_snapshot.csv")
    ap.add_argument("--out-coefs", default="docs/experiments/evaluation/attr_outcome_regression/tables/attr_outcome_regression_coefficients_v1.csv")
    ap.add_argument("--out-diag", default="docs/experiments/evaluation/attr_outcome_regression/tables/attr_outcome_regression_diagnostics_v1.csv")
    ap.add_argument("--out-sens", default="docs/experiments/evaluation/attr_outcome_regression/tables/attr_outcome_regression_sensitivity_v1.csv")
    ap.add_argument("--fig-dir", default="docs/figs/attr_outcome_regression_v1")
    ap.add_argument("--versions", default=f"phases/p2-gsjso/runs/{RUN_ID}/versions.txt")
    return ap


def main() -> None:
    args = build_argparser().parse_args()
    repo = Path.cwd()
    rows = build_snapshot(repo, args)
    add_strata(rows)

    snapshot_fields = [
        "building_id", "arm", "input_kind", "outcome_source", "crs_xy", "clip_source", "fallback_clip_source",
        "no_points_recode", "robust_exclude", "robust_exclude_reason", "manual_label", "manual_label_available",
        "footprint_area_m2", "ref_roof_planes", "pt_density_m2", "coverage_frac", "pt_density_m2_reg",
        "coverage_frac_reg", "local_plane_rms_m", "m3c2_rms_m", "floater_frac", "label_proxy_frac_all",
        "label_proxy_frac_ground", "attr_missing_local_rms", "attr_missing_m3c2", "attr_missing_floater",
        "attr_missing_label_all", "attr_missing_label_ground", "median_incidence_deg", "median_pair_angle_deg",
        "n_views_nadir", "recon_score_median", "assembled", "val3dity_valid", "rf_rmse_lod22", "rf_roof_planes",
        "run2_available", "run2_assembled", "run2_val3dity_valid", "run2_rf_rmse_lod22", "run2_rf_roof_planes",
        "stratum_complexity_ref_roof_planes", "stratum_size_area", "stratum_observation_recon_score",
    ]
    write_csv(repo / args.out_snapshot, rows, snapshot_fields)

    main_coefs, main_diag, _ = fit_all(rows, "main")
    robust_coefs, robust_diag = robust_exclusion_models(rows)
    fallback_coefs = fallback_dummy_sensitivity(rows)
    label_coefs = label_ground_sensitivity(rows)
    run2_coefs, run2_summary = run2_sensitivity(rows)
    ordinary_sign = ordinary_vs_robust(rows)
    desc = attr_descriptive(rows)
    corr = correlation_rows(rows)
    spears = spearman_rows(rows)
    strata = stratification_rows(rows)
    vif = []
    for arm in ARMS:
        vif.extend(vif_rows([r for r in rows if r["arm"] == arm], arm, ATTR_COLS))

    all_coefs = main_coefs + robust_coefs + run2_coefs
    write_csv(
        repo / args.out_coefs,
        all_coefs,
        ["variant", "arm", "outcome", "outcome_kind", "spec", "fit_type", "n", "predictor", "coef", "se", "ci_low", "ci_high", "status"],
    )
    write_csv(
        repo / args.out_diag,
        main_diag + robust_diag,
        ["variant", "arm", "outcome", "spec", "n", "status", "cook_threshold", "n_cook_gt_4_over_n", "cook_gt_4_over_n_buildings"],
    )
    write_csv(
        repo / args.out_sens,
        fallback_coefs + label_coefs + run2_coefs + ordinary_sign,
        sorted(set().union(*(r.keys() for r in fallback_coefs + label_coefs + run2_coefs + ordinary_sign))) if (fallback_coefs + label_coefs + run2_coefs + ordinary_sign) else ["none"],
    )

    fig_dir = repo / args.fig_dir
    coef_fig = fig_dir / "coef_forest.png"
    rep_fig = fig_dir / "representative_buildings.png"
    plot_coefficients(main_coefs, coef_fig)
    plot_representatives(rows, rep_fig)

    out_paths = {
        "snapshot": args.out_snapshot,
        "coef_fig": str(coef_fig.relative_to(repo)),
        "rep_fig": str(rep_fig.relative_to(repo)),
        "versions": args.versions,
    }
    write_report(
        repo / args.out_report,
        rows,
        all_coefs,
        fallback_coefs + label_coefs + run2_coefs + ordinary_sign,
        main_diag + robust_diag,
        desc,
        corr,
        vif,
        spears,
        strata,
        ordinary_sign,
        run2_summary,
        out_paths,
    )

    fps = source_fingerprints(repo, args)
    counts = {
        "snapshot_rows": len(rows),
        "dim_rows": sum(1 for r in rows if r["arm"] == "raw_dense"),
        "lidar_rows": sum(1 for r in rows if r["arm"] == "raw_lidar"),
        "acmp_rows": sum(1 for r in rows if r["arm"] == "raw_acmp"),
        "coef_rows": len(all_coefs),
        "diagnostic_rows": len(main_diag + robust_diag),
        "sensitivity_rows": len(fallback_coefs + label_coefs + run2_coefs + ordinary_sign),
    }
    write_versions(repo / args.versions, repo, args, fps, counts)
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

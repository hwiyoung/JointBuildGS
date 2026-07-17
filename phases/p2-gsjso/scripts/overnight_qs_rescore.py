#!/usr/bin/env python3
"""A wave: exhaustive C001 assembled-CityJSON quality rescore.

This is a learning-zero measurement.  Existing CityJSON artifacts are read,
val3dity is rerun uniformly, and LoD2 reference geometry is opened only for
scoring and datum alignment.  No point cloud, checkpoint, or reconstruction
input is modified.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np
from shapely.ops import unary_union

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import e5_c001_8way as metric  # noqa: E402


RUN_ID = "20260716_qs_rescore"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
VAL_DIR = RUN_DIR / "val3dity"
LOG = RUN_DIR / "run.log"
MANIFEST = RUN_DIR / "manifest.json"
DOCS = REPO / "docs"
FIG_DIR = DOCS / "figs/qs_rescore"
INVENTORY_CSV = DOCS / "qs_rescore_inventory.csv"
SCORES_CSV = DOCS / "qs_rescore_scores.csv"
PAIRS_CSV = DOCS / "qs_rescore_pairs.csv"
SUMMARY_CSV = DOCS / "qs_rescore_summary.csv"
FIG_SCATTER = FIG_DIR / "qs_rescore_face_count_scatter.png"
FIG_RMS = FIG_DIR / "qs_rescore_rms_pairs.png"
FIG_TOP = FIG_DIR / "qs_rescore_topview_examples.png"

C001_IDS = tuple(metric.C001_IDS)
TARGET_SET = set(C001_IDS)
LOD2_DIR = REPO / "phases/p0-audit/data/raw/lod2"
P0_RUNS = REPO / "phases/p0-audit/runs"
S3AP_SCORE = DOCS / "e5_c001_s3ap_phase3_scores.csv"
POINT_V13 = DOCS / "pointcloud_attributes_v1_3.csv"
LENS_CSV = DOCS / "e5_c001_s1_audit_8way_joined.csv"

BASELINES = (
    (
        "canonical_dense_w2_1",
        "canonical_dense",
        "w2_1",
        P0_RUNS / "w2_1_roofer_default_20260612_152729/cityjson/dim_roofer.city.json",
        P0_RUNS / "w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv",
        "DIM",
    ),
    (
        "canonical_dense_run_2",
        "dense_sensitivity",
        "run_2",
        P0_RUNS / "w3_2b_roofer_repeatability_20260612_220747/cityjson/run_2/dim_default.city.json",
        P0_RUNS / "w3_2b_roofer_repeatability_20260612_220747/status/run_2/dim_default.csv",
        "DIM",
    ),
    (
        "als_w2_1",
        "als_upper",
        "w2_1",
        P0_RUNS / "w2_1_roofer_default_20260612_152729/cityjson/als_roofer.city.json",
        P0_RUNS / "w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv",
        "ALS",
    ),
)

Z_SHIFT_CANDIDATES = (0.0, -45.700, -45.934, -48.165)
RUN_REPEAT_RE = re.compile(r"^(?P<name>.+)_run_(?P<repeat>[123])$")


@dataclass(frozen=True)
class Model:
    model_id: str
    role: str
    wave: str
    arm: str
    run: str
    setting: str
    cityjson: Path | None
    status_path: Path | None
    status_input: str
    lineage: str
    s3ap_row: dict[str, str] | None = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path | str | None) -> str:
    if path is None:
        return ""
    value = Path(path)
    try:
        return str(value.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(value.resolve())


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: format_value(row.get(field)) for field in fields})
    os.replace(tmp, path)


def format_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (float, np.floating)):
        return "" if not math.isfinite(float(value)) else f"{float(value):.9f}"
    return value


def log(message: str) -> None:
    line = f"{now()} {message}"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(line, flush=True)


def bool_value(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def number(value: Any) -> float | None:
    try:
        if value in ("", None, "None", "none", "nan"):
            return None
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def short_arm(run_name: str) -> str:
    patterns = (
        r"_s3ap_b\d+_(a\d(?:_dz_[mp]\d(?:p\d)?)?)_r\d$",
        r"_s2p_(arm\d+p)_dense_r\d$",
        r"_s2_(arm\d+)_dense_r\d$",
        r"_s1fac_(w\d+_p\d+)_dense_(?:r\d|reuse)$",
        r"_(sparse|dense|acmp)_r\d$",
    )
    for pattern in patterns:
        match = re.search(pattern, run_name)
        if match:
            return match.group(1)
    return "unparsed"


def replicate(run_name: str) -> str:
    match = re.search(r"_(r\d)$", run_name)
    return match.group(1) if match else ("reuse" if run_name.endswith("_reuse") else "")


def discover_gs_models() -> list[Model]:
    models: list[Model] = []
    for path in sorted(P0_RUNS.glob("e5p*/**/cityjson/*.city.json")):
        text = rel(path)
        if "_failed_" in text or "/failed_" in text:
            continue
        stem_match = RUN_REPEAT_RE.match(path.stem.removesuffix(".city"))
        if stem_match is None:
            continue
        run_name = stem_match.group("name")
        if not run_name.startswith("gs_"):
            continue
        repeat = f"run_{stem_match.group('repeat')}"
        parts = path.relative_to(P0_RUNS).parts
        root = parts[0]
        setting_parts = list(parts[1:-2])
        setting = "/".join(setting_parts) if setting_parts else "base"
        lineage = "405_repaired_copy" if "repair" in root else "original_assembled"
        wave = root
        if "repair" in root and setting_parts and setting_parts[0].startswith("e5p_"):
            wave = f"{root}:{setting_parts[0]}"
            setting = "/".join(setting_parts[1:]) or "base"
        models.append(
            Model(
                model_id=f"{wave}:{setting}:{run_name}:{repeat}",
                role="gs",
                wave=wave,
                arm=short_arm(run_name),
                run=replicate(run_name) or repeat,
                setting=setting,
                cityjson=path,
                status_path=None,
                status_input="",
                lineage=lineage,
            )
        )
    for row in read_csv(S3AP_SCORE):
        path = REPO / row["cityjson_path"]
        if not path.is_file():
            continue
        run_name = row["run_id"]
        models.append(
            Model(
                model_id=f"s3ap_phase3:{run_name}",
                role="gs",
                wave="s3ap_phase3",
                arm=row.get("arm", short_arm(run_name)),
                run=row.get("replicate", replicate(run_name)),
                setting=(
                    f"{row.get('perturbation_type', 'none')}:{row.get('perturbation_value', '0')}"
                ),
                cityjson=path,
                status_path=S3AP_SCORE,
                status_input="",
                lineage="phase3_score_job",
                s3ap_row=row,
            )
        )
    return models


def discover_models() -> list[Model]:
    models = discover_gs_models()
    for model_id, role, wave, cityjson, status_path, label in BASELINES:
        if cityjson.is_file():
            models.append(
                Model(
                    model_id=model_id,
                    role=role,
                    wave=wave,
                    arm=label.lower(),
                    run=wave,
                    setting="canonical",
                    cityjson=cityjson,
                    status_path=status_path,
                    status_input=label,
                    lineage="comparison_baseline",
                )
            )
    models.append(
        Model(
            model_id="reference_lod2",
            role="reference",
            wave="reference",
            arm="reference",
            run="reference",
            setting="reference",
            cityjson=None,
            status_path=None,
            status_input="",
            lineage="score_only_reference",
        )
    )
    unique: dict[str, Model] = {}
    for model in models:
        unique[model.model_id] = model
    return [unique[key] for key in sorted(unique)]


def load_global_status() -> dict[tuple[str, str, str], list[tuple[Path, dict[str, str]]]]:
    output: dict[tuple[str, str, str], list[tuple[Path, dict[str, str]]]] = defaultdict(list)
    for path in sorted(P0_RUNS.glob("e5p*/**/building_reconstruction_status.csv")):
        if "_failed_" in rel(path):
            continue
        for row in read_csv(path):
            run_name = row.get("run_name", "")
            repeat = row.get("roofer_repeat", "run_1")
            building = row.get("building_id", "")
            if run_name and building in TARGET_SET:
                output[(run_name, repeat, building)].append((path, row))
    return output


def baseline_status(model: Model) -> dict[str, dict[str, str]]:
    rows = read_csv(model.status_path) if model.status_path else []
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        bid = row.get("building_id", "")
        if bid not in TARGET_SET:
            continue
        if model.status_input and row.get("input", model.status_input) != model.status_input:
            continue
        result[bid] = row
    return result


def status_for_model(
    model: Model,
    global_status: dict[tuple[str, str, str], list[tuple[Path, dict[str, str]]]],
) -> dict[str, dict[str, str]]:
    if model.role in {"canonical_dense", "dense_sensitivity", "als_upper"}:
        return baseline_status(model)
    if model.s3ap_row is not None:
        row = model.s3ap_row
        return {
            row["building_id"]: {
                "building_id": row["building_id"],
                "status": row.get("roofer_status", ""),
                "reason": row.get("roofer_reason", ""),
                "rf_extrusion_mode": row.get("rf_extrusion_mode", ""),
                "rf_roof_planes": row.get("rf_roof_planes", ""),
                "has_lod22": row.get("has_lod22", ""),
                "val3dity_valid": row.get("val3dity_valid", ""),
                "rf_rmse_lod22": row.get("citygml_roof_rms_m", ""),
                "rf_pt_density": "",
                "rf_nodata_frac": "",
                "status_source": rel(S3AP_SCORE),
            }
        }
    if model.cityjson is None:
        return {}
    stem_match = RUN_REPEAT_RE.match(model.cityjson.stem.removesuffix(".city"))
    if stem_match is None:
        return {}
    run_name = stem_match.group("name")
    repeat = f"run_{stem_match.group('repeat')}"
    root_tokens = set(model.wave.split(":"))
    selected: dict[str, dict[str, str]] = {}
    for bid in C001_IDS:
        candidates = global_status.get((run_name, repeat, bid), [])
        if not candidates:
            continue
        candidates = sorted(
            candidates,
            key=lambda item: (
                -sum(token in rel(item[0]) for token in root_tokens),
                rel(item[0]),
            ),
        )
        path, row = candidates[0]
        selected[bid] = {**row, "status_source": rel(path)}
    return selected


def run_val3dity(model: Model) -> tuple[dict[str, bool], str, int | None]:
    if model.cityjson is None:
        return {bid: True for bid in C001_IDS}, "reference_self_check", 0
    digest = sha256_file(model.cityjson)
    report = VAL_DIR / f"{digest}.json"
    log_path = VAL_DIR / f"{digest}.log"
    if not report.is_file():
        report.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["val3dity", model.cityjson.as_posix(), "--report", report.as_posix()],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        atomic_text(
            log_path,
            f"+ val3dity {model.cityjson} --report {report}\n{proc.stdout or ''}",
        )
        exit_code = int(proc.returncode)
    else:
        exit_code = 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    valid = {
        str(feature.get("id")): bool(feature.get("validity"))
        for feature in payload.get("features", [])
        if feature.get("id") in TARGET_SET
    }
    return valid, rel(report), exit_code


def median_rms(
    refs: dict[str, list[Any]],
    predictions: dict[str, list[Any]],
    shift: float,
) -> float:
    values = []
    for bid in C001_IDS:
        surfaces = metric.shift_surface_z(predictions.get(bid, []), shift)
        if not surfaces:
            continue
        rms = metric.compare_building(refs[bid], surfaces)["ref_rms_m"]
        if rms is not None and math.isfinite(float(rms)):
            values.append(float(rms))
    return float(np.median(values)) if values else math.inf


def choose_z_shift(
    model: Model,
    refs: dict[str, list[Any]],
    predictions: dict[str, list[Any]],
) -> tuple[float, str, dict[str, float]]:
    if model.role in {"canonical_dense", "dense_sensitivity", "als_upper", "reference"}:
        candidates = (0.0,)
    else:
        candidates = Z_SHIFT_CANDIDATES
    scores = {f"{candidate:.3f}": median_rms(refs, predictions, candidate) for candidate in candidates}
    shift = min(candidates, key=lambda value: (scores[f"{value:.3f}"], abs(value)))
    return shift, "candidate shift with minimum median per-building roof RMS", scores


def load_lenses() -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {bid: {} for bid in C001_IDS}
    for row in read_csv(LENS_CSV):
        bid = row.get("building_id", "")
        if bid not in output:
            continue
        for field in (
            "texture_lens",
            "observation_lens",
            "complexity_lens",
            "size_lens",
            "label_lens",
        ):
            if row.get(field) and not output[bid].get(field):
                output[bid][field] = row[field]
    return output


def load_point_metrics() -> dict[tuple[str, str], dict[str, str]]:
    output: dict[tuple[str, str], dict[str, str]] = {}
    for row in read_csv(POINT_V13):
        bid = row.get("building_id", "")
        arm = row.get("arm", "")
        if bid in TARGET_SET:
            output[(bid, arm)] = row
    return output


def model_point_row(
    model: Model,
    bid: str,
    status: dict[str, str],
    point_metrics: dict[tuple[str, str], dict[str, str]],
) -> dict[str, Any]:
    aliases = []
    if model.role == "canonical_dense":
        aliases = ["raw_dense"]
    elif model.role == "als_upper":
        aliases = ["raw_lidar"]
    elif model.role == "gs":
        arm = model.arm
        if arm in {"sparse", "dense", "acmp"}:
            aliases = [f"gs_{arm}_{model.run}"]
    source = next((point_metrics[(bid, alias)] for alias in aliases if (bid, alias) in point_metrics), {})
    return {
        "point_metric_arm": source.get("arm", ""),
        "point_count_footprint": source.get("n_points_footprint", ""),
        "point_density_m2": source.get("pt_density_m2", status.get("rf_pt_density", "")),
        "point_coverage_frac": source.get("coverage_frac", ""),
        "point_hole_frac": source.get("hole_frac", status.get("rf_nodata_frac", "")),
        "point_local_plane_rms_m": source.get("local_plane_rms_m", ""),
        "point_metric_source": rel(POINT_V13) if source else status.get("status_source", ""),
    }


def xy_check(refs: list[Any], preds: list[Any]) -> tuple[str, float | None]:
    if not preds:
        return "no_roof_geometry", None
    ref_union = unary_union([surface.polygon for surface in refs])
    pred_union = unary_union([surface.polygon for surface in preds])
    if pred_union.is_empty or ref_union.is_empty:
        return "empty_union", None
    overlap = float(pred_union.intersection(ref_union.buffer(1.0)).area)
    ratio = overlap / max(float(pred_union.area), 1e-9)
    return ("aligned" if ratio >= 0.5 else "low_overlap"), ratio


INVENTORY_FIELDS = [
    "model_id", "role", "wave", "arm", "run", "setting", "lineage", "building_id",
    "cityjson_path", "cityjson_sha256", "status_path", "cityjson_crs", "xy_alignment",
    "xy_overlap_ratio", "z_shift_to_reference_m", "z_shift_rule", "z_shift_candidate_median_rms_json",
    "val3dity_report", "val3dity_exit_code", "learning_runs_started", "inventory_status",
]

SCORE_FIELDS = [
    "model_id", "role", "wave", "arm", "run", "setting", "lineage", "building_id",
    "status", "status_reason", "rf_extrusion_mode", "has_lod22", "lod1_fallback",
    "val3dity_valid", "roof_face_count_model", "roof_face_count_ref", "face_count_ratio",
    "roof_rms_m", "roof_hausdorff_m", "roof_distance_samples", "status_rf_rmse_lod22",
    "point_metric_arm", "point_count_footprint", "point_density_m2", "point_coverage_frac",
    "point_hole_frac", "point_local_plane_rms_m", "point_metric_source",
    "texture_lens", "observation_lens", "complexity_lens", "size_lens", "label_lens",
    "cityjson_path", "cityjson_sha256", "status_path", "z_shift_to_reference_m",
    "xy_alignment", "xy_overlap_ratio", "gt_role", "learning_runs_started",
]

PAIR_FIELDS = [
    "row_type", "building_id", "population_role", "gs_selection_scope",
    "dense_model_id", "dense_has_lod22",
    "dense_val3dity_valid", "dense_lod1_fallback", "dense_roof_face_count",
    "dense_face_count_ratio", "dense_roof_rms_m", "gs_valid_count", "gs_total_count",
    "gs_lod2_count", "gs_best_model_id", "gs_best_wave", "gs_best_arm", "gs_best_run",
    "gs_best_selection_pool", "gs_best_invalid_best", "gs_best_has_lod22",
    "gs_best_val3dity_valid", "gs_best_lod1_fallback", "gs_best_roof_face_count",
    "gs_best_face_count_ratio", "gs_best_roof_rms_m", "als_model_id", "als_has_lod22",
    "als_val3dity_valid", "als_roof_face_count", "als_face_count_ratio", "als_roof_rms_m",
    "reference_roof_face_count", "texture_lens", "observation_lens", "complexity_lens",
    "size_lens", "label_lens", "learning_runs_started",
]

SUMMARY_FIELDS = [
    "scope", "stratum", "model", "n_buildings", "lod2_count", "val3dity_valid_count",
    "lod1_fallback_count", "median_face_count_ratio", "median_roof_rms_m",
    "learning_runs_started",
]


def build_rows(
    models: Sequence[Model],
    refs: dict[str, list[Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, dict[str, list[Any]]],
]:
    global_status = load_global_status()
    lenses = load_lenses()
    point_metrics = load_point_metrics()
    inventory: list[dict[str, Any]] = []
    scores: list[dict[str, Any]] = []
    surface_cache: dict[str, dict[str, list[Any]]] = {}
    for index, model in enumerate(models, start=1):
        log(f"model {index}/{len(models)} {model.model_id}")
        if model.role == "reference":
            predictions = refs
            shift = 0.0
            shift_rule = "reference self-check"
            shift_scores = {"0.000": 0.0}
            status_by_id: dict[str, dict[str, str]] = {}
            valid_by_id = {bid: True for bid in C001_IDS}
            val_report, val_exit = "reference_self_check", 0
            cityjson_sha = ""
            crs = "EPSG:25832"
        else:
            assert model.cityjson is not None
            predictions = metric.parse_cityjson_roofs(model.cityjson, TARGET_SET)
            shift, shift_rule, shift_scores = choose_z_shift(model, refs, predictions)
            predictions = {
                bid: metric.shift_surface_z(predictions.get(bid, []), shift)
                for bid in C001_IDS
            }
            status_by_id = status_for_model(model, global_status)
            valid_by_id, val_report, val_exit = run_val3dity(model)
            cityjson_sha = sha256_file(model.cityjson)
            payload = json.loads(model.cityjson.read_text(encoding="utf-8"))
            crs = str((payload.get("metadata") or {}).get("referenceSystem", ""))
        surface_cache[model.model_id] = predictions
        model_bids = (
            [model.s3ap_row["building_id"]]
            if model.s3ap_row is not None
            else C001_IDS
        )
        for bid in model_bids:
            status = status_by_id.get(bid, {})
            preds = predictions.get(bid, [])
            aligned, overlap = xy_check(refs[bid], preds)
            inventory.append(
                {
                    "model_id": model.model_id,
                    "role": model.role,
                    "wave": model.wave,
                    "arm": model.arm,
                    "run": model.run,
                    "setting": model.setting,
                    "lineage": model.lineage,
                    "building_id": bid,
                    "cityjson_path": rel(model.cityjson) if model.cityjson else "phases/p0-audit/data/raw/lod2/*.gml",
                    "cityjson_sha256": cityjson_sha,
                    "status_path": status.get("status_source", rel(model.status_path)),
                    "cityjson_crs": crs,
                    "xy_alignment": aligned,
                    "xy_overlap_ratio": overlap,
                    "z_shift_to_reference_m": shift,
                    "z_shift_rule": shift_rule,
                    "z_shift_candidate_median_rms_json": json.dumps(
                        shift_scores, sort_keys=True, separators=(",", ":")
                    ),
                    "val3dity_report": val_report,
                    "val3dity_exit_code": val_exit,
                    "learning_runs_started": 0,
                    "inventory_status": "present" if (model.role == "reference" or model.cityjson) else "missing",
                }
            )
            comparison = metric.compare_building(refs[bid], preds)
            mode = status.get("rf_extrusion_mode", "")
            fallback = mode == "lod11_fallback"
            if model.role == "reference":
                has_lod22 = True
                fallback = False
                valid = True
                roof_count = len(refs[bid])
                status_name, reason = "reference", "reference_self_check"
            else:
                has_lod22 = bool_value(status.get("has_lod22"))
                valid = bool(valid_by_id.get(bid, False))
                roof_count = 1 if fallback else len(preds)
                status_name = status.get("status", "missing_status")
                reason = status.get("reason", "")
            ref_count = len(refs[bid])
            lens = lenses.get(bid, {})
            point = model_point_row(model, bid, status, point_metrics)
            scores.append(
                {
                    "model_id": model.model_id,
                    "role": model.role,
                    "wave": model.wave,
                    "arm": model.arm,
                    "run": model.run,
                    "setting": model.setting,
                    "lineage": model.lineage,
                    "building_id": bid,
                    "status": status_name,
                    "status_reason": reason,
                    "rf_extrusion_mode": mode,
                    "has_lod22": has_lod22,
                    "lod1_fallback": fallback,
                    "val3dity_valid": valid,
                    "roof_face_count_model": roof_count,
                    "roof_face_count_ref": ref_count,
                    "face_count_ratio": roof_count / ref_count if ref_count else None,
                    "roof_rms_m": comparison["ref_rms_m"],
                    "roof_hausdorff_m": comparison["ref_hausdorff_m"],
                    "roof_distance_samples": comparison["ref_distance_samples"],
                    "status_rf_rmse_lod22": status.get("rf_rmse_lod22", ""),
                    **point,
                    "texture_lens": lens.get("texture_lens", ""),
                    "observation_lens": lens.get("observation_lens", ""),
                    "complexity_lens": lens.get("complexity_lens", ""),
                    "size_lens": lens.get("size_lens", ""),
                    "label_lens": lens.get("label_lens", ""),
                    "cityjson_path": rel(model.cityjson) if model.cityjson else "phases/p0-audit/data/raw/lod2/*.gml",
                    "cityjson_sha256": cityjson_sha,
                    "status_path": status.get("status_source", rel(model.status_path)),
                    "z_shift_to_reference_m": shift,
                    "xy_alignment": aligned,
                    "xy_overlap_ratio": overlap,
                    "gt_role": "LoD2 reference used for scoring/datum alignment only",
                    "learning_runs_started": 0,
                }
            )
        atomic_csv(INVENTORY_CSV, inventory, INVENTORY_FIELDS)
        atomic_csv(SCORES_CSV, scores, SCORE_FIELDS)
    return inventory, scores, surface_cache


def best_gs(rows: Sequence[dict[str, Any]]) -> tuple[dict[str, Any] | None, str, bool]:
    measurable = [row for row in rows if number(row.get("roof_rms_m")) is not None]
    if not measurable:
        return None, "none", False
    valid = [row for row in measurable if bool_value(row.get("val3dity_valid"))]
    pool = valid or measurable
    selected = min(pool, key=lambda row: (float(row["roof_rms_m"]), row["model_id"]))
    return selected, ("valid_models" if valid else "all_models"), not bool(valid)


def build_pairs(scores: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_building: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in scores:
        by_building[row["building_id"]].append(row)
    pairs: list[dict[str, Any]] = []
    for bid in C001_IDS:
        rows = by_building[bid]
        dense = next((row for row in rows if row["role"] == "canonical_dense"), None)
        als = next((row for row in rows if row["role"] == "als_upper"), None)
        reference = next(row for row in rows if row["role"] == "reference")
        gs_rows = [row for row in rows if row["role"] == "gs"]
        best, pool_name, invalid_best = best_gs(gs_rows)
        dense_success = bool(dense and bool_value(dense["has_lod22"]))
        gs_lod2 = sum(bool_value(row["has_lod22"]) for row in gs_rows)
        population = (
            "dense_success"
            if dense_success
            else ("gs_only_lod2" if gs_lod2 else "neither_lod2")
        )
        lens = reference
        pairs.append(
            {
                "row_type": "building",
                "building_id": bid,
                "population_role": population,
                "gs_selection_scope": "per_building_oracle_upper_bound_not_fixed_condition",
                "dense_model_id": dense["model_id"] if dense else "",
                "dense_has_lod22": dense["has_lod22"] if dense else None,
                "dense_val3dity_valid": dense["val3dity_valid"] if dense else None,
                "dense_lod1_fallback": dense["lod1_fallback"] if dense else None,
                "dense_roof_face_count": dense["roof_face_count_model"] if dense else None,
                "dense_face_count_ratio": dense["face_count_ratio"] if dense else None,
                "dense_roof_rms_m": dense["roof_rms_m"] if dense else None,
                "gs_valid_count": sum(bool_value(row["val3dity_valid"]) for row in gs_rows),
                "gs_total_count": len(gs_rows),
                "gs_lod2_count": gs_lod2,
                "gs_best_model_id": best["model_id"] if best else "",
                "gs_best_wave": best["wave"] if best else "",
                "gs_best_arm": best["arm"] if best else "",
                "gs_best_run": best["run"] if best else "",
                "gs_best_selection_pool": pool_name,
                "gs_best_invalid_best": invalid_best,
                "gs_best_has_lod22": best["has_lod22"] if best else None,
                "gs_best_val3dity_valid": best["val3dity_valid"] if best else None,
                "gs_best_lod1_fallback": best["lod1_fallback"] if best else None,
                "gs_best_roof_face_count": best["roof_face_count_model"] if best else None,
                "gs_best_face_count_ratio": best["face_count_ratio"] if best else None,
                "gs_best_roof_rms_m": best["roof_rms_m"] if best else None,
                "als_model_id": als["model_id"] if als else "",
                "als_has_lod22": als["has_lod22"] if als else None,
                "als_val3dity_valid": als["val3dity_valid"] if als else None,
                "als_roof_face_count": als["roof_face_count_model"] if als else None,
                "als_face_count_ratio": als["face_count_ratio"] if als else None,
                "als_roof_rms_m": als["roof_rms_m"] if als else None,
                "reference_roof_face_count": reference["roof_face_count_ref"],
                "texture_lens": lens.get("texture_lens", ""),
                "observation_lens": lens.get("observation_lens", ""),
                "complexity_lens": lens.get("complexity_lens", ""),
                "size_lens": lens.get("size_lens", ""),
                "label_lens": lens.get("label_lens", ""),
                "learning_runs_started": 0,
            }
        )
    summary: list[dict[str, Any]] = []
    for stratum_name, subset in [
        ("all_c001", pairs),
        ("dense_success", [row for row in pairs if row["population_role"] == "dense_success"]),
    ]:
        for label, prefix in (
            ("dense", "dense"),
            ("gs_per_building_oracle", "gs_best"),
            ("als", "als"),
        ):
            ratio = [number(row.get(f"{prefix}_face_count_ratio")) for row in subset]
            rms = [number(row.get(f"{prefix}_roof_rms_m")) for row in subset]
            ratio_values = [value for value in ratio if value is not None]
            rms_values = [value for value in rms if value is not None]
            summary.append(
                {
                    "scope": "population",
                    "stratum": stratum_name,
                    "model": label,
                    "n_buildings": len(subset),
                    "lod2_count": sum(bool_value(row.get(f"{prefix}_has_lod22")) for row in subset),
                    "val3dity_valid_count": sum(
                        bool_value(row.get(f"{prefix}_val3dity_valid")) for row in subset
                    ),
                    "lod1_fallback_count": sum(
                        bool_value(row.get(f"{prefix}_lod1_fallback")) for row in subset
                    ),
                    "median_face_count_ratio": float(np.median(ratio_values)) if ratio_values else None,
                    "median_roof_rms_m": float(np.median(rms_values)) if rms_values else None,
                    "learning_runs_started": 0,
                }
            )
    for lens_field in ("texture_lens", "observation_lens", "label_lens"):
        values = sorted({row.get(lens_field, "") for row in pairs if row.get(lens_field, "")})
        for value in values:
            subset = [row for row in pairs if row.get(lens_field) == value]
            for label, prefix in (
                ("dense", "dense"),
                ("gs_per_building_oracle", "gs_best"),
            ):
                ratio_values = [
                    float(row[f"{prefix}_face_count_ratio"])
                    for row in subset
                    if number(row.get(f"{prefix}_face_count_ratio")) is not None
                ]
                rms_values = [
                    float(row[f"{prefix}_roof_rms_m"])
                    for row in subset
                    if number(row.get(f"{prefix}_roof_rms_m")) is not None
                ]
                summary.append(
                    {
                        "scope": lens_field,
                        "stratum": value,
                        "model": label,
                        "n_buildings": len(subset),
                        "lod2_count": sum(bool_value(row.get(f"{prefix}_has_lod22")) for row in subset),
                        "val3dity_valid_count": sum(
                            bool_value(row.get(f"{prefix}_val3dity_valid")) for row in subset
                        ),
                        "lod1_fallback_count": sum(
                            bool_value(row.get(f"{prefix}_lod1_fallback")) for row in subset
                        ),
                        "median_face_count_ratio": float(np.median(ratio_values)) if ratio_values else None,
                        "median_roof_rms_m": float(np.median(rms_values)) if rms_values else None,
                        "learning_runs_started": 0,
                    }
                )
    return pairs, summary


def plot_surface_top(ax: Any, surfaces: Sequence[Any], title: str, fallback: bool = False) -> None:
    palette = plt.cm.tab20(np.linspace(0, 1, max(len(surfaces), 1)))
    for index, surface in enumerate(surfaces):
        for polygon in metric.flatten_polygons(surface.polygon):
            xy = np.asarray(polygon.exterior.coords)
            ax.fill(
                xy[:, 0],
                xy[:, 1],
                color=palette[index % len(palette)],
                alpha=0.72,
                edgecolor="black",
                linewidth=0.45,
            )
    if not surfaces:
        ax.text(0.5, 0.5, "no roof geometry", transform=ax.transAxes, ha="center", va="center")
    ax.set_aspect("equal")
    ax.set_title(title + ("\nLoD1 fallback: flat 1 face" if fallback else ""), fontsize=8)
    ax.tick_params(labelsize=6)


def make_figures(
    pairs: Sequence[dict[str, Any]],
    surfaces: dict[str, dict[str, list[Any]]],
) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    dense_rows = [row for row in pairs if row["population_role"] == "dense_success"]

    figure, axis = plt.subplots(figsize=(7.2, 6.2), dpi=180)
    for label, xfield, yfield, color, marker in (
        ("dense w2_1", "reference_roof_face_count", "dense_roof_face_count", "#1f77b4", "o"),
        (
            "GS per-building oracle",
            "reference_roof_face_count",
            "gs_best_roof_face_count",
            "#d62728",
            "^",
        ),
    ):
        x = [number(row[xfield]) for row in dense_rows]
        y = [number(row[yfield]) for row in dense_rows]
        keep = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
        if keep:
            axis.scatter(
                [value[0] for value in keep],
                [value[1] for value in keep],
                label=label,
                color=color,
                marker=marker,
                alpha=0.78,
            )
    maximum = max(
        [1.0]
        + [float(row["reference_roof_face_count"]) for row in dense_rows]
        + [
            float(value)
            for row in dense_rows
            for value in (row.get("dense_roof_face_count"), row.get("gs_best_roof_face_count"))
            if number(value) is not None
        ]
    )
    axis.plot([0, maximum], [0, maximum], color="black", linestyle="--", linewidth=0.9)
    axis.set_xlabel("reference roof-face count")
    axis.set_ylabel("model roof-face count")
    axis.set_title("C001 dense-success pairs: roof-face count")
    axis.legend()
    axis.grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(FIG_SCATTER)
    plt.close(figure)

    ordered = sorted(
        [
            row
            for row in dense_rows
            if number(row.get("dense_roof_rms_m")) is not None
            and number(row.get("gs_best_roof_rms_m")) is not None
        ],
        key=lambda row: row["building_id"],
    )
    figure, axis = plt.subplots(figsize=(max(9, 0.55 * len(ordered)), 5.6), dpi=180)
    positions = np.arange(len(ordered))
    width = 0.38
    axis.bar(
        positions - width / 2,
        [float(row["dense_roof_rms_m"]) for row in ordered],
        width,
        label="dense w2_1",
        color="#1f77b4",
    )
    axis.bar(
        positions + width / 2,
        [float(row["gs_best_roof_rms_m"]) for row in ordered],
        width,
        label="GS per-building oracle (not one fixed condition)",
        color="#d62728",
    )
    axis.set_xticks(positions)
    axis.set_xticklabels([row["building_id"].removeprefix("DEBY_LOD2_") for row in ordered], rotation=55, ha="right")
    axis.set_ylabel("roof RMS against reference [m]")
    axis.set_title("C001 dense-success pairs: roof RMS")
    axis.legend()
    axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    figure.savefig(FIG_RMS)
    plt.close(figure)

    candidates = [row for row in dense_rows if row.get("gs_best_model_id")]
    selected: list[dict[str, Any]] = []
    if candidates:
        selected.append(min(candidates, key=lambda row: abs(float(row["gs_best_face_count_ratio"] or 0) - 1.0)))
        selected.append(max(candidates, key=lambda row: float(row["gs_best_face_count_ratio"] or 0)))
        textureless = [
            row
            for row in candidates
            if "텍스처" in str(row.get("texture_lens", "")) or "텍스처" in str(row.get("label_lens", ""))
        ]
        if textureless:
            selected.append(textureless[0])
        selected.append(max(candidates, key=lambda row: float(row["gs_best_roof_rms_m"] or -1)))
    unique: dict[str, dict[str, Any]] = {row["building_id"]: row for row in selected}
    examples = list(unique.values())[:4]
    if not examples:
        return
    figure, axes = plt.subplots(len(examples), 3, figsize=(12, 3.7 * len(examples)), dpi=180)
    axes_array = np.asarray(axes, dtype=object).reshape(len(examples), 3)
    for row_index, row in enumerate(examples):
        bid = row["building_id"]
        dense_id = row["dense_model_id"]
        best_id = row["gs_best_model_id"]
        plot_surface_top(
            axes_array[row_index, 0],
            surfaces["reference_lod2"][bid],
            f"{bid}\nreference | faces={row['reference_roof_face_count']}",
        )
        plot_surface_top(
            axes_array[row_index, 1],
            surfaces.get(dense_id, {}).get(bid, []),
            f"dense | faces={row['dense_roof_face_count']} | RMS={float(row['dense_roof_rms_m']):.2f}",
            bool_value(row.get("dense_lod1_fallback")),
        )
        plot_surface_top(
            axes_array[row_index, 2],
            surfaces.get(best_id, {}).get(bid, []),
            f"GS per-building oracle | {row['gs_best_arm']} {row['gs_best_run']}\n"
            f"faces={row['gs_best_roof_face_count']} | RMS={float(row['gs_best_roof_rms_m']):.2f}",
            bool_value(row.get("gs_best_lod1_fallback")),
        )
    figure.suptitle(
        "C001 roof-surface instances: reference | dense | GS per-building oracle",
        fontsize=12,
    )
    figure.tight_layout(rect=[0, 0, 1, 0.98])
    figure.savefig(FIG_TOP)
    plt.close(figure)


def write_manifest(
    models: Sequence[Model],
    inventory: Sequence[dict[str, Any]],
    scores: Sequence[dict[str, Any]],
    pairs: Sequence[dict[str, Any]],
    summary: Sequence[dict[str, Any]],
) -> None:
    sources = {
        Path(__file__),
        REPO / "phases/p2-gsjso/scripts/e5_c001_8way.py",
        S3AP_SCORE,
        POINT_V13,
        LENS_CSV,
        *sorted(LOD2_DIR.glob("*.gml")),
        *[model.cityjson for model in models if model.cityjson],
        *[model.status_path for model in models if model.status_path],
    }
    outputs = [
        INVENTORY_CSV,
        SCORES_CSV,
        PAIRS_CSV,
        SUMMARY_CSV,
        FIG_SCATTER,
        FIG_RMS,
        FIG_TOP,
        LOG,
        *sorted(VAL_DIR.glob("*")),
    ]
    payload = {
        "schema": "jointbuildgs.qs_rescore.v1",
        "created_utc": now(),
        "git_head_at_measurement": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=REPO, text=True
        ).strip(),
        "crs": "EPSG:25832",
        "val3dity_version": "2.6.0",
        "z_shift_candidates_m": list(Z_SHIFT_CANDIDATES),
        "z_shift_selection": "minimum median per-building roof RMS; reference used for scoring only",
        "model_count": len(models),
        "gs_model_count": sum(model.role == "gs" for model in models),
        "inventory_rows": len(inventory),
        "score_rows": len(scores),
        "pair_rows": len(pairs),
        "summary_rows": len(summary),
        "gs_best_selection_scope": "per_building_oracle_upper_bound_not_fixed_condition",
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "gt_role": "LoD2 reference used only for scoring, self-check, datum alignment, and figures",
        "interpretation_or_verdict": None,
        "source_sha256": {
            rel(path): sha256_file(path)
            for path in sorted({Path(path) for path in sources if path and Path(path).is_file()})
        },
        "output_sha256": {
            rel(path): sha256_file(path)
            for path in outputs
            if path.is_file() and path != MANIFEST
        },
    }
    atomic_text(MANIFEST, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    atomic_text(LOG, "")
    models = discover_models()
    log(
        f"start models={len(models)} gs={sum(model.role == 'gs' for model in models)} "
        "learning_runs_started=0"
    )
    refs = metric.parse_lod2_roofs(LOD2_DIR, TARGET_SET)
    inventory, scores, surfaces = build_rows(models, refs)
    pairs, summary = build_pairs(scores)
    atomic_csv(PAIRS_CSV, pairs, PAIR_FIELDS)
    atomic_csv(SUMMARY_CSV, summary, SUMMARY_FIELDS)
    make_figures(pairs, surfaces)
    write_manifest(models, inventory, scores, pairs, summary)
    counts = Counter(row["population_role"] for row in pairs)
    log(
        f"complete inventory={len(inventory)} scores={len(scores)} pairs={len(pairs)} "
        f"population={dict(counts)} learning_runs_started=0"
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Fail-closed immutable archives for the two S3-A-prime Phase-3 waves.

The controller never opens raw footprint, LoD2, or ALS inputs.  It validates
the score-boundary attestations already written by Phase 3, copies only small
global outputs, and binds every per-job output by path, size, and SHA256.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import types
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[3]
CONTAINER_REPO = Path("/workspace/JointBuildGS")
DEFAULT_CONFIG = REPO / "phases/p2-gsjso/configs/e5_c001/e5_c001_s3ap_phase3_archive_lock.json"
EXECUTED_CONTROLLER_SHA256 = str(
    os.environ.get("S3AP_ARCHIVE_CONTROLLER_SHA256", "")
).strip().lower()

INVENTORY_FIELDS = [
    "sequence", "job_id", "job_class", "building_id", "arm", "replicate",
    "random_seed", "height_delta_m", "tilt_deg", "config_path", "config_sha256",
    "data_root", "surface_seed_npz", "surface_seed_sha256", "out_dir",
    "final_checkpoint", "iterations", "gt_used", "lod2_used", "als_used", "status",
]
PHASE2_INPUT_BINDING_SCHEMA = "jointbuildgs.s3ap.phase3.archive_phase2_input_binding.v1"
ARCHIVE_LOCK_SCHEMA = "jointbuildgs.s3ap.phase3.archive.lock.v2"
PARTIAL_NO_SCORED_ROOF_POINTS = "partial_no_scored_roof_points"


def locked_wave_policy(wave: str) -> dict[str, Any]:
    """Exact archive-v2 policy, independent of mutable config bytes."""

    common = {
        "base_jobs": 18,
        "height_nonzero_jobs": 24,
        "perturbation_rows": 27,
        "nonzero_height_rows": 24,
    }
    if wave == "base42":
        return {
            **common,
            "total_jobs": 42,
            "tilt_jobs": 0,
            "terminal_scores": 42,
            "complete_scores": 40,
            "certified_partial_scores": 2,
            "certified_partial_kind_counts": {
                "no_roof_evidence": 1,
                "prepared_zero_inside_points": 1,
            },
            "certified_partial_runs": {
                "gs_e5_C001_s3ap_b8568391_a1_dz_m4_r1": "no_roof_evidence",
                "gs_e5_C001_s3ap_b8568392_a1_dz_m4_r1": "prepared_zero_inside_points",
            },
            "allowed_partial_statuses": [PARTIAL_NO_SCORED_ROOF_POINTS],
            "require_all_scores_complete": False,
            "complete_perturbation_rows": 25,
            "partial_perturbation_rows": 2,
            "complete_nonzero_height_rows": 22,
            "require_evaluation_complete": False,
            "require_raw_return_signal": True,
            "require_return_signal": False,
        }
    if wave == "final60":
        return {
            **common,
            "total_jobs": 60,
            "tilt_jobs": 18,
            "terminal_scores": 60,
            "complete_scores": 60,
            "certified_partial_scores": 0,
            "certified_partial_kind_counts": {},
            "certified_partial_runs": {},
            "allowed_partial_statuses": [],
            "require_all_scores_complete": True,
            "complete_perturbation_rows": 27,
            "partial_perturbation_rows": 0,
            "complete_nonzero_height_rows": 24,
            "require_evaluation_complete": True,
            "require_raw_return_signal": True,
            "require_return_signal": True,
        }
    raise ArchiveError(f"wave_invalid:{wave}")


class ArchiveError(RuntimeError):
    pass


@dataclass(frozen=True)
class InventoryJob:
    run_id: str
    building_id: str
    arm: str
    replicate: str
    kind: str
    value: float
    random_seed: int
    config_path: str
    config_sha256: str
    data_root: str
    surface_seed_npz: str
    surface_seed_sha256: str
    out_dir: str
    final_checkpoint: str
    checkpoint_sha256: str
    source_inventory: str

    def phase3_job(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "building_id": self.building_id,
            "arm": self.arm,
            "replicate": self.replicate,
            "perturbation_type": "none" if self.kind == "base" else self.kind,
            "perturbation_value": self.value,
            "config_path": self.config_path,
            "prepared_root": self.data_root,
            "checkpoint": self.final_checkpoint,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ArchiveError(reason)


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    require(isinstance(value, dict), f"json_object_required:{path}")
    return value


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames is not None, f"csv_header_missing:{path}")
        return list(reader.fieldnames), [dict(row) for row in reader]


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no", ""}:
        return False
    raise ArchiveError(f"invalid_boolean:{value!r}")


def normalize_image_id(value: Any) -> str:
    text = str(value or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", text):
        text = "sha256:" + text
    require(bool(re.fullmatch(r"sha256:[0-9a-f]{64}", text)), f"invalid_image_id:{value!r}")
    return text


def repo_path(value: str | Path, repo: Path = REPO) -> Path:
    path = Path(value)
    if path.is_absolute() and str(path).startswith(str(CONTAINER_REPO)):
        path = repo / path.relative_to(CONTAINER_REPO)
    elif not path.is_absolute():
        path = repo / path
    resolved = path.resolve()
    try:
        resolved.relative_to(repo.resolve())
    except ValueError as exc:
        raise ArchiveError(f"path_outside_repository:{value}") from exc
    return resolved


def relative(path: Path, repo: Path = REPO) -> str:
    return path.resolve().relative_to(repo.resolve()).as_posix()


def regular_file(path: Path, label: str) -> None:
    require(path.is_file(), f"{label}_missing:{path}")
    require(not path.is_symlink(), f"{label}_symlink_forbidden:{path}")


def regular_directory(path: Path, label: str) -> None:
    require(path.is_dir(), f"{label}_missing:{path}")
    require(not path.is_symlink(), f"{label}_symlink_forbidden:{path}")


def valid_sha256(value: Any, label: str) -> str:
    text = str(value or "").strip().lower()
    require(bool(re.fullmatch(r"[0-9a-f]{64}", text)), f"{label}_invalid_sha256")
    return text


def normalized_repo_relative(value: Any, label: str, repo: Path = REPO) -> str:
    text = str(value or "").strip()
    require(text != "", f"{label}_empty")
    path = repo_path(text, repo)
    result = relative(path, repo)
    require(result == text, f"{label}_not_canonical:{text}")
    return result


def same_number(actual: Any, expected: float, label: str) -> None:
    try:
        value = float(actual)
    except (TypeError, ValueError) as exc:
        raise ArchiveError(f"{label}_not_numeric") from exc
    require(math.isfinite(value) and value == float(expected), f"{label}_mismatch")


def finite_decimal(value: Any, label: str, *, allow_empty: bool = False) -> Decimal | None:
    text = str(value if value is not None else "").strip()
    if allow_empty and text == "":
        return None
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ArchiveError(f"{label}_not_decimal") from exc
    require(result.is_finite(), f"{label}_nonfinite")
    return result


def csv_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return "" if not math.isfinite(value) else f"{value:.9f}"
    return str(value)


def exact_perturbation_trigger(
    rows: Sequence[Mapping[str, Any]], rule: str,
) -> dict[str, Any]:
    """Independent, tolerance-free reconstruction of Phase 3's trigger."""

    candidates: list[dict[str, Any]] = []
    for row in rows:
        try:
            delta = float(row.get("delta_m"))
        except (TypeError, ValueError) as exc:
            raise ArchiveError(
                f"trigger_source_numeric_invalid:{row.get('run_id', '')}"
            ) from exc
        require(math.isfinite(delta), f"trigger_source_numeric_nonfinite:{row.get('run_id', '')}")
        eligible = bool(
            str(row.get("arm", "")).lower() == "a1"
            and str(row.get("replicate", "")).lower() == "r1"
            and delta != 0.0
            and str(row.get("score_status", "")) == "complete"
        )
        if eligible:
            try:
                post = float(row.get("post_gs_signed_median_error_m"))
                seed = float(row.get("perturbed_p0_signed_median_error_m"))
            except (TypeError, ValueError) as exc:
                raise ArchiveError(
                    f"trigger_source_numeric_invalid:{row.get('run_id', '')}"
                ) from exc
            require(
                all(math.isfinite(value) for value in (post, seed)),
                f"trigger_source_numeric_nonfinite:{row.get('run_id', '')}",
            )
            condition = bool(abs(post) < abs(seed))
            candidates.append({
                "run_id": str(row.get("run_id", "")),
                "building_id": str(row.get("building_id", "")),
                "delta_m": delta,
                "post_gs_abs_signed_median_error_m": abs(post),
                "perturbed_p0_abs_signed_median_error_m": abs(seed),
                "condition_met": condition,
            })
    qualifying = [row for row in candidates if row["condition_met"]]
    return {
        "return_signal": bool(qualifying), "rule": rule,
        "candidates": candidates, "qualifying": qualifying,
    }


def ensure_within(path: Path, root: Path, label: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ArchiveError(f"{label}_outside_root:{path}") from exc


def file_hash(
    path: Path, label: str, cache: dict[Path, tuple[int, str]] | None = None,
) -> tuple[int, str]:
    regular_file(path, label)
    key = path.resolve()
    if cache is not None and key in cache:
        return cache[key]
    value = (path.stat().st_size, sha256_file(path))
    if cache is not None:
        cache[key] = value
    return value


def validate_file_bundle(
    bundle: Mapping[str, Any], label: str, *, repo: Path,
    reopen: bool, allowed_root: Path | None = None,
    cache: dict[Path, tuple[int, str]] | None = None,
) -> list[dict[str, Any]]:
    files = bundle.get("files")
    require(isinstance(files, list), f"{label}_files_not_list")
    require(int(bundle.get("file_count", -1)) == len(files), f"{label}_file_count_mismatch")
    require(bundle.get("digest") == canonical_digest({"files": files}), f"{label}_digest_mismatch")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(files):
        require(isinstance(row, dict), f"{label}_row_invalid:{index}")
        require(set(row) == {"path", "size_bytes", "sha256"}, f"{label}_row_schema:{index}")
        path_text = normalized_repo_relative(row.get("path"), f"{label}_path:{index}", repo)
        require(path_text not in seen, f"{label}_duplicate_path:{path_text}")
        seen.add(path_text)
        try:
            size = int(row.get("size_bytes", -1))
        except (TypeError, ValueError) as exc:
            raise ArchiveError(f"{label}_size_invalid:{path_text}") from exc
        require(size >= 0, f"{label}_size_negative:{path_text}")
        digest = valid_sha256(row.get("sha256"), f"{label}_hash:{path_text}")
        path = repo_path(path_text, repo)
        if allowed_root is not None:
            ensure_within(path, allowed_root, f"{label}_path")
        if reopen:
            observed_size, observed_hash = file_hash(path, label, cache)
            require(observed_size == size, f"{label}_source_size:{path_text}")
            require(observed_hash == digest, f"{label}_source_hash:{path_text}")
        normalized.append({"path": path_text, "size_bytes": size, "sha256": digest})
    require(files == sorted(normalized, key=lambda row: row["path"]), f"{label}_files_not_canonical")
    return normalized


def load_phase3_module(config: Mapping[str, Any], repo: Path = REPO) -> Any:
    path = repo_path(config["phase3_script"], repo)
    regular_file(path, "phase3_script")
    source = path.read_bytes()
    source_sha256 = hashlib.sha256(source).hexdigest()
    name = f"s3ap_phase3_archive_source_{os.getpid()}"
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    module.__spec__ = importlib.util.spec_from_loader(name, loader=None, origin=str(path))
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    module.__archive_executed_source_sha256__ = source_sha256
    return module


def validate_executed_controller_source(repo: Path = REPO) -> str:
    digest = valid_sha256(EXECUTED_CONTROLLER_SHA256, "executed_controller")
    current = sha256_file(repo_path(
        "phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase3_archive.py", repo,
    ))
    require(current == digest, "executed_controller_source_drift")
    return digest


def perturb_slug(value: float, *, tilt: bool = False) -> str:
    sign = "p" if value > 0 else "m"
    magnitude = abs(float(value))
    if tilt:
        token = f"{int(round(magnitude)):02d}"
    elif math.isclose(magnitude, 0.5):
        token = "0p5"
    else:
        token = str(int(round(magnitude)))
    return f"{sign}{token}"


def validate_inventory_rows(
    rows_by_source: Sequence[tuple[str, Sequence[Mapping[str, str]]]],
    wave: str,
    phase3: Mapping[str, Any],
    wave_spec: Mapping[str, Any],
    *,
    repo: Path | None = None,
    phase2_lock: Mapping[str, Any] | None = None,
    hash_cache: dict[Path, tuple[int, str]] | None = None,
) -> tuple[list[InventoryJob], dict[str, Any]]:
    targets = {str(value) for value in phase3["targets"]}
    physical = repo is not None
    effective_repo = repo or REPO
    replicates = dict((phase2_lock or {}).get("training", {}).get("replicates", {"r1": 2001, "r2": 2002}))
    require(set(replicates) == {"r1", "r2"}, "inventory_replicate_lock_mismatch")
    training_root = str(phase3.get("phase2", {}).get("training_root", "results/tum_transfer/e5_s3ap_phase2/runs"))
    prepared_template = str(
        phase3.get("phase2", {}).get(
            "prepared_template", "results/tum_transfer/e5_s3ap_phase2/prepared/DEBY_LOD2_{building}",
        )
    )
    checkpoint_template = str(
        phase3.get("phase2", {}).get(
            "checkpoint_template", f"{training_root}/{{run_id}}/ckpt/final.pt",
        )
    )
    jobs: list[InventoryJob] = []
    for source, rows in rows_by_source:
        source_path = repo_path(source, effective_repo)
        config_root = source_path.parent / "configs"
        sequences: list[int] = []
        for row in rows:
            try:
                sequence = int(row["sequence"])
                height = float(row["height_delta_m"])
                tilt = float(row["tilt_deg"])
                iterations = int(row["iterations"])
                random_seed = int(row["random_seed"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ArchiveError(f"inventory_scalar_invalid:{source}") from exc
            require(math.isfinite(height) and math.isfinite(tilt), f"inventory_perturbation_nonfinite:{source}:{sequence}")
            sequences.append(sequence)
            run_id = str(row.get("job_id", "")).strip()
            building = str(row.get("building_id", "")).strip()
            arm = str(row.get("arm", "")).strip().lower()
            replicate = str(row.get("replicate", "")).strip().lower()
            kind = str(row.get("job_class", "")).strip().lower()
            require(run_id != "", f"inventory_run_id_empty:{source}")
            require(building in targets, f"inventory_target_unknown:{building}")
            require(iterations == 30000, f"inventory_iterations_not_30000:{run_id}")
            require(str(row.get("status")) == "prepared", f"inventory_status_not_prepared:{run_id}")
            for key in ("gt_used", "lod2_used", "als_used"):
                require(not parse_bool(row.get(key)), f"inventory_{key}_true:{run_id}")
            if kind == "base":
                require(height == 0.0 and tilt == 0.0, f"base_perturbation_nonzero:{run_id}")
                value = 0.0
            elif kind == "height":
                require(height != 0.0 and tilt == 0.0, f"height_perturbation_invalid:{run_id}")
                value = height
            elif kind == "tilt":
                require(height == 0.0 and tilt != 0.0, f"tilt_perturbation_invalid:{run_id}")
                value = tilt
            else:
                raise ArchiveError(f"inventory_job_class_invalid:{run_id}:{kind}")
            expected_seed = int(replicates[replicate]) if replicate in replicates else None
            require(expected_seed is not None, f"inventory_replicate_invalid:{run_id}")
            require(random_seed == expected_seed, f"inventory_random_seed_mismatch:{run_id}")
            if kind == "base":
                expected_run_id = f"gs_e5_C001_s3ap_b{building}_{arm}_{replicate}"
            elif kind == "height":
                expected_run_id = f"gs_e5_C001_s3ap_b{building}_a1_dz_{perturb_slug(value)}_{replicate}"
            else:
                expected_run_id = f"gs_e5_C001_s3ap_b{building}_a1_tilt_{perturb_slug(value, tilt=True)}_{replicate}"
            require(run_id == expected_run_id, f"inventory_run_id_semantic_mismatch:{run_id}")
            config_text = normalized_repo_relative(
                row.get("config_path"), f"inventory_config_path:{run_id}", effective_repo,
            )
            config_hash = valid_sha256(row.get("config_sha256"), f"inventory_config_hash:{run_id}")
            data_text = normalized_repo_relative(
                row.get("data_root"), f"inventory_data_root:{run_id}", effective_repo,
            )
            seed_text = normalized_repo_relative(
                row.get("surface_seed_npz"), f"inventory_seed_path:{run_id}", effective_repo,
            )
            seed_hash = valid_sha256(row.get("surface_seed_sha256"), f"inventory_seed_hash:{run_id}")
            out_text = normalized_repo_relative(
                row.get("out_dir"), f"inventory_out_dir:{run_id}", effective_repo,
            )
            checkpoint_text = normalized_repo_relative(
                row.get("final_checkpoint"), f"inventory_checkpoint:{run_id}", effective_repo,
            )
            expected_config = relative(config_root / f"{run_id}.yaml", effective_repo)
            expected_data = prepared_template.format(building=building)
            if arm == "a0":
                expected_seed_path = str(
                    (phase2_lock or {}).get("sources", {}).get(
                        "p0_surface_seed_pattern",
                        "phases/p2-gsjso/runs/e5_c001/20260715_e5_c001_s3ap_phase1_seedprep/seeds/DEBY_LOD2_{building}_p0_surface_seed.npz",
                    )
                ).format(building=building)
            else:
                expected_seed_path = f"{expected_data}/seeds/DEBY_LOD2_{building}_a1a2_surface_seed.npz"
            expected_out = f"{training_root}/{run_id}"
            expected_checkpoint = checkpoint_template.format(run_id=run_id)
            require(config_text == expected_config, f"inventory_config_path_mismatch:{run_id}")
            require(data_text == expected_data, f"inventory_data_root_mismatch:{run_id}")
            require(seed_text == expected_seed_path, f"inventory_seed_path_mismatch:{run_id}")
            require(out_text == expected_out, f"inventory_out_dir_mismatch:{run_id}")
            require(checkpoint_text == expected_checkpoint, f"inventory_checkpoint_path_mismatch:{run_id}")
            checkpoint_hash = ""
            if physical:
                regular_directory(repo_path(data_text, effective_repo), f"inventory_data_root:{run_id}")
                _, observed_config = file_hash(
                    repo_path(config_text, effective_repo), f"inventory_config:{run_id}", hash_cache,
                )
                require(observed_config == config_hash, f"inventory_config_hash_mismatch:{run_id}")
                _, observed_seed = file_hash(
                    repo_path(seed_text, effective_repo), f"inventory_seed:{run_id}", hash_cache,
                )
                require(observed_seed == seed_hash, f"inventory_seed_hash_mismatch:{run_id}")
                _, checkpoint_hash = file_hash(
                    repo_path(checkpoint_text, effective_repo), f"inventory_checkpoint:{run_id}", hash_cache,
                )
            jobs.append(InventoryJob(
                run_id, building, arm, replicate, kind, value, random_seed,
                config_text, config_hash, data_text, seed_text, seed_hash,
                out_text, checkpoint_text, checkpoint_hash, source,
            ))
        require(
            sequences == list(range(1, len(rows) + 1)),
            f"inventory_sequence_not_contiguous:{source}",
        )
    run_ids = [job.run_id for job in jobs]
    require(len(run_ids) == len(set(run_ids)), "inventory_duplicate_run_ids")
    base = [job for job in jobs if job.kind == "base"]
    height = [job for job in jobs if job.kind == "height"]
    tilt = [job for job in jobs if job.kind == "tilt"]
    expected_base = {
        (building, arm, replicate)
        for building in targets for arm in ("a0", "a1", "a2")
        for replicate in ("r1", "r2")
    }
    expected_height_values = {
        float(value) for value in phase3["perturbation"]["height_deltas_m"]
        if float(value) != 0.0
    }
    expected_height = {
        (building, "a1", "r1", value)
        for building in targets for value in expected_height_values
    }
    expected_tilt_values = {
        float(value) for value in phase3["perturbation"]["tilt_deltas_deg"]
    }
    expected_tilt = {
        (building, "a1", "r1", value)
        for building in targets for value in expected_tilt_values
    }
    require(
        {(job.building_id, job.arm, job.replicate) for job in base} == expected_base,
        "inventory_base_tuple_grid_mismatch",
    )
    require(
        {(job.building_id, job.arm, job.replicate, job.value) for job in height}
        == expected_height,
        "inventory_height_tuple_grid_mismatch",
    )
    actual_tilt = {(job.building_id, job.arm, job.replicate, job.value) for job in tilt}
    if wave == "final60":
        require(actual_tilt == expected_tilt, "inventory_tilt_tuple_grid_mismatch")
    else:
        require(not actual_tilt, "base42_contains_tilt")
    counts = {
        "total": len(jobs), "base": len(base),
        "height_nonzero": len(height), "tilt": len(tilt),
    }
    for key, spec_key in (
        ("total", "total_jobs"), ("base", "base_jobs"),
        ("height_nonzero", "height_nonzero_jobs"), ("tilt", "tilt_jobs"),
    ):
        require(counts[key] == int(wave_spec[spec_key]), f"inventory_{key}_count_mismatch")
    return sorted(jobs, key=lambda item: item.run_id), {
        "wave": wave, "counts": counts, "run_ids": sorted(run_ids),
        "base_tuple_count": len(expected_base),
        "height_tuple_count": len(expected_height),
        "tilt_tuple_count": len(expected_tilt) if wave == "final60" else 0,
        "job_contract_digest": canonical_digest([
            asdict(job) for job in sorted(jobs, key=lambda item: item.run_id)
        ]),
    }


def validate_fingerprint(value: Mapping[str, Any], schema: str, label: str) -> None:
    require(set(value) == {"digest", "payload"}, f"{label}_wrapper_schema_mismatch")
    require(isinstance(value.get("payload"), dict), f"{label}_payload_not_object")
    require(value.get("payload", {}).get("schema") == schema, f"{label}_schema_mismatch")
    require(
        value.get("digest") == canonical_digest(value.get("payload", {})),
        f"{label}_digest_mismatch",
    )


def validate_image_verification(
    payload: Mapping[str, Any], archive: Mapping[str, Any], phase3: Mapping[str, Any],
) -> None:
    require(payload.get("schema") == archive["schemas"]["image_verification"], "image_schema_mismatch")
    require(payload.get("status") == "complete", "image_status_not_complete")
    require(payload.get("mismatched_roles") == [], "image_mismatch_roles_present")
    expected = {
        "render": normalize_image_id(phase3["containers"]["render_image_id"]),
        "tools": normalize_image_id(phase3["containers"]["tools_image_id"]),
        "roofer": normalize_image_id(phase3["roofer"]["image_id_record"]),
    }
    rows = payload.get("images")
    require(isinstance(rows, list) and len(rows) == 3, "image_row_count_mismatch")
    observed: dict[str, str] = {}
    for row in rows:
        require(isinstance(row, dict), "image_row_invalid")
        role = str(row.get("role"))
        require(parse_bool(row.get("matched")), f"image_not_matched:{role}")
        require(int(row.get("inspect_exit_code", -1)) == 0, f"image_inspect_failed:{role}")
        actual = normalize_image_id(row.get("actual_id"))
        require(actual == normalize_image_id(row.get("expected_id")), f"image_actual_expected_mismatch:{role}")
        observed[role] = actual
    require(observed == expected, "image_locked_ids_mismatch")


def validate_prewarm_verification(
    payload: Mapping[str, Any], archive: Mapping[str, Any], phase3: Mapping[str, Any],
) -> None:
    require(payload.get("schema") == archive["schemas"]["prewarm_verification"], "prewarm_schema_mismatch")
    require(payload.get("status") == "complete", "prewarm_status_not_complete")
    require(payload.get("errors") == [], "prewarm_errors_present")
    require(int(payload.get("launcher_exit_code", -1)) == 0, "prewarm_launcher_failed")
    require(
        normalize_image_id(payload.get("render_image_id"))
        == normalize_image_id(phase3["containers"]["render_image_id"]),
        "prewarm_render_image_mismatch",
    )
    require(
        payload.get("phase2_lock_sha256") == phase3["phase2_prewarm"]["lock_sha256"],
        "prewarm_phase2_lock_mismatch",
    )
    require(
        payload.get("phase2_prepare_manifest_sha256")
        == phase3["phase2_prewarm"]["prepare_manifest_sha256"],
        "prewarm_prepare_manifest_mismatch",
    )
    require(bool(re.fullmatch(r"[0-9a-f]{64}", str(payload.get("extension_sha256", "")))), "prewarm_extension_hash_invalid")


def validate_prewarm_binding(
    binding: Mapping[str, Any], verification: Mapping[str, Any],
    archive: Mapping[str, Any], phase3: Mapping[str, Any], repo: Path,
    cache: dict[Path, tuple[int, str]] | None = None,
) -> None:
    require(set(binding) == {
        "schema", "verification", "verification_sha256", "extension",
        "extension_sha256", "source_bundle", "digest",
    }, "prewarm_binding_fields_mismatch")
    require(binding.get("schema") == archive["schemas"]["prewarm_binding"], "prewarm_binding_schema_mismatch")
    verification_path = repo_path(phase3["outputs"]["prewarm_verification"], repo)
    require(binding.get("verification") == relative(verification_path, repo), "prewarm_binding_verification_path")
    require(binding.get("verification_sha256") == sha256_file(verification_path), "prewarm_binding_verification_hash")
    require(binding.get("extension") == verification.get("extension_path"), "prewarm_binding_extension_path")
    require(binding.get("extension_sha256") == verification.get("extension_sha256"), "prewarm_binding_extension_hash")
    bundle = binding.get("source_bundle", {})
    files = validate_file_bundle(
        bundle, "prewarm_binding_source", repo=repo, reopen=True, cache=cache,
    )
    require(files, "prewarm_binding_source_bundle_empty")
    expected_digest = canonical_digest({
        "verification_sha256": binding["verification_sha256"],
        "extension_sha256": binding["extension_sha256"],
        "source_bundle_digest": bundle["digest"],
    })
    require(binding.get("digest") == expected_digest, "prewarm_binding_digest_mismatch")


def validate_wave_contract(
    *, wave: str, archive: Mapping[str, Any], phase3: Mapping[str, Any],
    jobs: Sequence[InventoryJob], inventory: Mapping[str, Any], aggregate: Mapping[str, Any],
    trigger: Mapping[str, Any], score_header: Sequence[str],
    score_rows: Sequence[Mapping[str, str]], perturb_header: Sequence[str],
    perturb_rows: Sequence[Mapping[str, str]], cell_header: Sequence[str],
    cell_rows: Sequence[Mapping[str, str]], status_header: Sequence[str],
    status_rows: Sequence[Mapping[str, str]], phase3_module: Any,
    authoritative_perturb_rows: Sequence[Mapping[str, Any]] | None = None,
    authoritative_cell_rows: Sequence[Mapping[str, str]] | None = None,
    certified_partial_runs: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    spec = archive["waves"][wave]
    require(spec == locked_wave_policy(wave), f"wave_policy_mismatch:{wave}")
    certified_partials = dict(certified_partial_runs or {})
    run_ids = set(inventory["run_ids"])
    jobs_by_id = {job.run_id: job for job in jobs}
    require(set(jobs_by_id) == run_ids, "inventory_job_object_ids_mismatch")
    require(score_header == list(phase3_module.SCORE_FIELDS), "score_csv_schema_mismatch")
    require(perturb_header == list(phase3_module.PERTURB_FIELDS), "perturbation_csv_schema_mismatch")
    require(cell_header == list(phase3_module.PERTURB_CELL_FIELDS), "perturbation_cells_csv_schema_mismatch")
    require(status_header == list(phase3_module.STATUS_FIELDS), "status_csv_schema_mismatch")
    score_ids = [str(row.get("run_id", "")) for row in score_rows]
    require(len(score_ids) == int(spec["total_jobs"]), "score_row_count_mismatch")
    require(len(score_ids) == len(set(score_ids)), "score_run_ids_duplicate")
    require(set(score_ids) == run_ids, "score_run_ids_inventory_mismatch")
    score_by_id = {str(row["run_id"]): row for row in score_rows}
    allowed_partial = set(spec["allowed_partial_statuses"])
    score_status_counts: dict[str, int] = {}
    for row in score_rows:
        status = str(row.get("score_status", ""))
        require(status == "complete" or status in allowed_partial, f"score_status_not_terminal:{row.get('run_id')}")
        score_status_counts[status] = score_status_counts.get(status, 0) + 1
    partial_ids = {
        run_id for run_id, row in score_by_id.items()
        if str(row.get("score_status", "")) != "complete"
    }
    require(partial_ids == set(certified_partials), "score_partial_certification_mismatch")
    complete_score_count = score_status_counts.get("complete", 0)
    partial_score_count = len(partial_ids)
    partial_kind_counts: dict[str, int] = {}
    for kind in certified_partials.values():
        partial_kind_counts[kind] = partial_kind_counts.get(kind, 0) + 1
    require(len(score_rows) == int(spec["terminal_scores"]), "terminal_score_count_mismatch")
    require(complete_score_count == int(spec["complete_scores"]), "complete_score_count_mismatch")
    require(partial_score_count == int(spec["certified_partial_scores"]), "certified_partial_count_mismatch")
    require(partial_kind_counts == spec["certified_partial_kind_counts"], "certified_partial_kind_counts_mismatch")
    require(certified_partials == spec["certified_partial_runs"], "certified_partial_runs_mismatch")
    if bool(spec["require_all_scores_complete"]):
        require(partial_score_count == 0 and complete_score_count == len(score_rows), "score_rows_not_all_complete")
    for row in score_rows:
        run_id = str(row.get("run_id", ""))
        job = jobs_by_id[run_id]
        require(str(row.get("building_id")) == f"DEBY_LOD2_{job.building_id}", f"score_building_mismatch:{run_id}")
        require(str(row.get("arm")).lower() == job.arm, f"score_arm_mismatch:{run_id}")
        require(str(row.get("replicate")).lower() == job.replicate, f"score_replicate_mismatch:{run_id}")
        expected_kind = "none" if job.kind == "base" else job.kind
        require(str(row.get("perturbation_type")).lower() == expected_kind, f"score_perturbation_type_mismatch:{run_id}")
        same_number(row.get("perturbation_value"), job.value, f"score_perturbation_value:{run_id}")
        require(str(row.get("checkpoint")) == job.final_checkpoint, f"score_checkpoint_path_mismatch:{run_id}")
        require(str(row.get("prepared_root")) == job.data_root, f"score_prepared_root_mismatch:{run_id}")
        if job.checkpoint_sha256:
            require(str(row.get("checkpoint_sha256")) == job.checkpoint_sha256, f"score_checkpoint_hash_mismatch:{run_id}")
        require(str(row.get("crs")) == phase3["crs"], f"score_crs_mismatch:{row.get('run_id')}")
        require(str(row.get("supplied_footprint_passed_to_roofer")) == "false", f"score_footprint_passed:{row.get('run_id')}")
        require(str(row.get("gt_role")) == phase3["scoring"]["gt_open_boundary"], f"score_gt_role_mismatch:{row.get('run_id')}")
        require(
            str(row.get("footprint_role"))
            == "score-region and coverage mask opened after Roofer input finalization",
            f"score_footprint_role_mismatch:{row.get('run_id')}",
        )
    expected_perturb_jobs = {
        job.run_id: job for job in jobs
        if job.arm == "a1" and job.replicate == "r1" and job.kind in {"base", "height"}
    }
    perturb_ids = [str(row.get("run_id", "")) for row in perturb_rows]
    require(len(perturb_ids) == int(spec["perturbation_rows"]), "perturbation_row_count_mismatch")
    require(len(perturb_ids) == len(set(perturb_ids)), "perturbation_run_ids_duplicate")
    require(set(perturb_ids) == set(expected_perturb_jobs), "perturbation_run_ids_exact_set_mismatch")
    semantic_perturb_rows = list(authoritative_perturb_rows or perturb_rows)
    semantic_ids = [str(row.get("run_id", "")) for row in semantic_perturb_rows]
    require(len(semantic_ids) == len(set(semantic_ids)), "authoritative_perturbation_ids_duplicate")
    require(set(semantic_ids) == set(perturb_ids), "authoritative_perturbation_ids_mismatch")
    if authoritative_perturb_rows is not None:
        global_by_id = {str(row["run_id"]): row for row in perturb_rows}
        authoritative_by_id = {
            str(row["run_id"]): row for row in semantic_perturb_rows
        }
        for row in semantic_perturb_rows:
            require(set(row) == set(phase3_module.PERTURB_FIELDS), f"authoritative_perturbation_schema:{row.get('run_id')}")
            global_row = global_by_id[str(row["run_id"])]
            for field in phase3_module.PERTURB_FIELDS:
                require(
                    str(global_row.get(field, "")) == csv_scalar(row.get(field)),
                    f"authoritative_perturbation_csv_mismatch:{row.get('run_id')}:{field}",
                )
        # Phase 3 constructs the trigger from aggregate-CSV order.  Reorder
        # the authoritative per-job JSON values to that same order before the
        # exact nested-list comparison; sorting by run ID would manufacture a
        # false mismatch while also weakening the ordering contract.
        semantic_perturb_rows = [authoritative_by_id[run_id] for run_id in perturb_ids]
    nonzero = [row for row in semantic_perturb_rows if float(row.get("delta_m", "0")) != 0.0]
    require(len(nonzero) == int(spec["nonzero_height_rows"]), "nonzero_height_row_count_mismatch")
    complete_perturbation_count = 0
    partial_perturbation_count = 0
    for row in semantic_perturb_rows:
        run_id = str(row.get("run_id", ""))
        job = expected_perturb_jobs[run_id]
        delta = 0.0 if job.kind == "base" else job.value
        score_status = str(row.get("score_status", ""))
        require(score_status == str(score_by_id[run_id].get("score_status", "")), f"perturbation_score_status_mismatch:{run_id}")
        require(score_status == "complete" or run_id in certified_partials, f"perturbation_partial_not_certified:{run_id}")
        if score_status == "complete":
            complete_perturbation_count += 1
        else:
            partial_perturbation_count += 1
        require(str(row.get("building_id")) == f"DEBY_LOD2_{job.building_id}", f"perturbation_building_mismatch:{run_id}")
        require(str(row.get("arm")).lower() == job.arm, f"perturbation_arm_mismatch:{run_id}")
        require(str(row.get("replicate")).lower() == job.replicate, f"perturbation_replicate_mismatch:{run_id}")
        same_number(row.get("delta_m"), delta, f"perturbation_delta:{run_id}")
        seed_keys = (
            "p0_signed_median_error_m", "perturbed_p0_signed_median_error_m",
            "perturbed_p0_abs_signed_median_error_m",
        )
        post_keys = (
            "post_gs_signed_median_error_m", "post_gs_abs_signed_median_error_m",
            "signed_error_reduction_m", "post_minus_perturbed_seed_signed_m",
        )
        if authoritative_perturb_rows is not None:
            seed_values: list[float] = []
            for field in seed_keys:
                value = row.get(field)
                require(
                    isinstance(value, (int, float)) and not isinstance(value, bool),
                    f"perturbation_numeric_type:{run_id}:{field}",
                )
                number = float(value)
                require(math.isfinite(number), f"perturbation_numeric_nonfinite:{run_id}:{field}")
                seed_values.append(number)
            p0, perturbed, perturbed_abs = seed_values
            delta_number: float | Decimal = float(delta)
        else:
            seed_values = [
                finite_decimal(row.get(field), f"perturbation_numeric:{run_id}:{field}")
                for field in seed_keys
            ]
            require(
                all(value is not None for value in seed_values),
                f"perturbation_numeric_missing:{run_id}",
            )
            p0, perturbed, perturbed_abs = seed_values
            delta_number = Decimal(str(delta))
        require(perturbed == p0 + delta_number, f"perturbation_seed_equation:{run_id}")
        require(perturbed_abs == abs(perturbed), f"perturbation_seed_abs_equation:{run_id}")
        if authoritative_perturb_rows is not None:
            require(type(row.get("return_condition_met")) is bool, f"perturbation_condition_type:{run_id}")
            require(type(row.get("trigger_candidate")) is bool, f"perturbation_candidate_type:{run_id}")
            observed_condition = row.get("return_condition_met")
            observed_candidate = row.get("trigger_candidate")
        else:
            require(str(row.get("return_condition_met")) in {"true", "false"}, f"perturbation_condition_type:{run_id}")
            require(str(row.get("trigger_candidate")) in {"true", "false"}, f"perturbation_candidate_type:{run_id}")
            observed_condition = str(row.get("return_condition_met")) == "true"
            observed_candidate = str(row.get("trigger_candidate")) == "true"
        if score_status == "complete":
            if authoritative_perturb_rows is not None:
                post_values: list[float] = []
                for field in post_keys:
                    value = row.get(field)
                    require(
                        isinstance(value, (int, float)) and not isinstance(value, bool),
                        f"perturbation_numeric_type:{run_id}:{field}",
                    )
                    number = float(value)
                    require(math.isfinite(number), f"perturbation_numeric_nonfinite:{run_id}:{field}")
                    post_values.append(number)
            else:
                post_values = [
                    finite_decimal(row.get(field), f"perturbation_numeric:{run_id}:{field}")
                    for field in post_keys
                ]
                require(all(value is not None for value in post_values), f"perturbation_numeric_missing:{run_id}")
            post, post_abs, reduction, post_minus_seed = post_values
            require(post_abs == abs(post), f"perturbation_post_abs_equation:{run_id}")
            require(reduction == abs(perturbed) - abs(post), f"perturbation_reduction_equation:{run_id}")
            require(post_minus_seed == post - perturbed, f"perturbation_post_seed_equation:{run_id}")
            condition = bool(delta_number != 0 and abs(post) < abs(perturbed))
            candidate = bool(delta != 0.0)
        else:
            for field in post_keys:
                value = row.get(field)
                require(value is None if authoritative_perturb_rows is not None else str(value or "") == "", f"perturbation_partial_post_present:{run_id}:{field}")
            condition = False
            candidate = False
        require(observed_condition is condition, f"perturbation_condition_mismatch:{run_id}")
        require(observed_candidate is candidate, f"perturbation_candidate_mismatch:{run_id}")
        require(str(row.get("trigger_rule")) == phase3["perturbation"]["trigger_rule"], f"perturbation_rule_mismatch:{run_id}")
    semantic_cell_rows = list(authoritative_cell_rows or cell_rows)
    if authoritative_cell_rows is not None:
        def cell_sort_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
            return (
                str(row.get("run_id", "")), str(row.get("cell_ix", "")),
                str(row.get("cell_iy", "")),
            )

        require(
            sorted([dict(row) for row in cell_rows], key=cell_sort_key)
            == sorted([dict(row) for row in semantic_cell_rows], key=cell_sort_key),
            "authoritative_cells_global_mismatch",
        )
    cell_ids = {str(row.get("run_id", "")) for row in semantic_cell_rows}
    require(cell_ids == set(perturb_ids), "perturbation_cell_run_coverage_mismatch")
    cell_keys: set[tuple[str, int, int]] = set()
    cell_reference_by_building: dict[tuple[str, int, int], tuple[Decimal, Decimal, str, Decimal, Decimal]] = {}
    cell_grid_by_run: dict[str, set[tuple[int, int]]] = {}
    for row in semantic_cell_rows:
        run_id = str(row.get("run_id", ""))
        require(set(row) == set(phase3_module.PERTURB_CELL_FIELDS), f"cell_schema:{run_id}")
        job = expected_perturb_jobs[run_id]
        cell_status = str(row.get("score_status", ""))
        require(cell_status == str(score_by_id[run_id].get("score_status", "")), f"cell_score_status_mismatch:{run_id}")
        require(cell_status == "complete" or run_id in certified_partials, f"cell_partial_not_certified:{run_id}")
        delta = 0.0 if job.kind == "base" else job.value
        require(str(row.get("building_id")) == f"DEBY_LOD2_{job.building_id}", f"cell_building_mismatch:{run_id}")
        require(str(row.get("arm")).lower() == job.arm, f"cell_arm_mismatch:{run_id}")
        require(str(row.get("replicate")).lower() == job.replicate, f"cell_replicate_mismatch:{run_id}")
        same_number(row.get("delta_m"), delta, f"cell_delta:{run_id}")
        try:
            key = (run_id, int(row["cell_ix"]), int(row["cell_iy"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ArchiveError(f"cell_index_invalid:{run_id}") from exc
        require(key not in cell_keys, f"cell_duplicate:{run_id}:{key[1]}:{key[2]}")
        cell_keys.add(key)
        cell_grid_by_run.setdefault(run_id, set()).add((key[1], key[2]))
        center_x = finite_decimal(row.get("cell_center_x"), f"cell_center_x:{run_id}")
        center_y = finite_decimal(row.get("cell_center_y"), f"cell_center_y:{run_id}")
        grid_decimal = finite_decimal(row.get("coverage_grid_m"), f"cell_grid:{run_id}")
        require(
            grid_decimal == Decimal(str(phase3["scoring"]["coverage_grid_m"])),
            f"cell_grid_mismatch:{run_id}",
        )
        require(
            Decimal(key[1]) * grid_decimal <= center_x
            <= Decimal(key[1] + 1) * grid_decimal
            and Decimal(key[2]) * grid_decimal <= center_y
            <= Decimal(key[2] + 1) * grid_decimal,
            f"cell_center_grid_mismatch:{run_id}",
        )
        require(str(row.get("region")) in {"edge", "interior"}, f"cell_region_invalid:{run_id}")
        p0_cell = finite_decimal(row.get("p0_base_signed_error_m"), f"cell_p0:{run_id}")
        perturbed_cell = finite_decimal(row.get("perturbed_p0_signed_error_m"), f"cell_perturbed:{run_id}")
        perturbed_abs_cell = finite_decimal(row.get("perturbed_p0_abs_error_m"), f"cell_perturbed_abs:{run_id}")
        delta_decimal = Decimal(str(delta))
        require(perturbed_cell == p0_cell + delta_decimal, f"cell_perturbed_equation:{run_id}")
        require(perturbed_abs_cell == abs(perturbed_cell), f"cell_perturbed_abs_equation:{run_id}")
        try:
            post_count = int(str(row.get("post_gs_point_count", "")))
        except ValueError as exc:
            raise ArchiveError(f"cell_post_count_invalid:{run_id}") from exc
        require(post_count >= 0, f"cell_post_count_negative:{run_id}")
        if cell_status != "complete":
            require(post_count == 0, f"cell_partial_post_count_nonzero:{run_id}")
        post_cell = finite_decimal(
            row.get("post_gs_signed_error_m"), f"cell_post:{run_id}", allow_empty=True,
        )
        post_abs_cell = finite_decimal(
            row.get("post_gs_abs_error_m"), f"cell_post_abs:{run_id}", allow_empty=True,
        )
        return_amount = finite_decimal(
            row.get("return_amount_m"), f"cell_return_amount:{run_id}", allow_empty=True,
        )
        if post_count == 0:
            require(post_cell is None and post_abs_cell is None and return_amount is None, f"cell_empty_post_fields:{run_id}")
        else:
            require(post_cell is not None and post_abs_cell is not None and return_amount is not None, f"cell_nonempty_post_fields:{run_id}")
            require(post_abs_cell == abs(post_cell), f"cell_post_abs_equation:{run_id}")
            require(return_amount == abs(perturbed_cell) - abs(post_cell), f"cell_return_equation:{run_id}")
        expected_condition = bool(
            delta != 0.0 and post_cell is not None
            and abs(post_cell) < abs(perturbed_cell)
            and str(score_by_id[run_id].get("score_status")) == "complete"
        )
        require(str(row.get("return_condition_met")) in {"true", "false"}, f"cell_condition_type:{run_id}")
        require((str(row.get("return_condition_met")) == "true") is expected_condition, f"cell_condition_mismatch:{run_id}")
        reference_key = (job.building_id, key[1], key[2])
        reference_value = (
            center_x, center_y, str(row.get("region")), p0_cell,
            grid_decimal,
        )
        previous_reference = cell_reference_by_building.setdefault(
            reference_key, reference_value,
        )
        require(
            previous_reference == reference_value,
            f"cell_cross_run_reference_mismatch:{job.building_id}:{key[1]}:{key[2]}",
        )
    for building_id in sorted({job.building_id for job in expected_perturb_jobs.values()}):
        building_runs = sorted(
            run_id for run_id, job in expected_perturb_jobs.items()
            if job.building_id == building_id
        )
        reference_grid = cell_grid_by_run[building_runs[0]]
        for run_id in building_runs[1:]:
            require(
                cell_grid_by_run[run_id] == reference_grid,
                f"cell_cross_run_grid_mismatch:{building_id}:{run_id}",
            )
    complete_nonzero_count = sum(
        str(row.get("score_status", "")) == "complete" for row in nonzero
    )
    require(complete_perturbation_count == int(spec["complete_perturbation_rows"]), "complete_perturbation_count_mismatch")
    require(partial_perturbation_count == int(spec["partial_perturbation_rows"]), "partial_perturbation_count_mismatch")
    require(complete_nonzero_count == int(spec["complete_nonzero_height_rows"]), "complete_nonzero_height_count_mismatch")
    require(trigger.get("schema") == archive["schemas"]["return_signal"], "trigger_schema_mismatch")
    require(trigger.get("evaluation_complete") is bool(spec["require_evaluation_complete"]), "trigger_evaluation_policy_mismatch")
    for key in ("expected_nonzero_height_rows", "observed_nonzero_height_rows"):
        require(type(trigger.get(key)) is int, f"trigger_{key}_type")
        require(trigger.get(key) == int(spec["nonzero_height_rows"]), f"trigger_{key}_mismatch")
    require(type(trigger.get("complete_nonzero_height_rows")) is int, "trigger_complete_nonzero_height_rows_type")
    require(trigger.get("complete_nonzero_height_rows") == complete_nonzero_count, "trigger_complete_nonzero_height_rows_mismatch")
    require(type(trigger.get("candidate_count")) is int, "trigger_candidate_count_type")
    require(trigger.get("candidate_count") == complete_nonzero_count, "trigger_candidate_count_mismatch")
    require(type(trigger.get("qualifying_count")) is int, "trigger_qualifying_count_type")
    require(trigger.get("qualifying_count") == len(trigger.get("qualifying", [])), "trigger_qualifying_count_mismatch")
    require(len(trigger.get("candidates", [])) == complete_nonzero_count, "trigger_candidates_length_mismatch")
    recomputed = exact_perturbation_trigger(
        semantic_perturb_rows, phase3["perturbation"]["trigger_rule"],
    )
    require(trigger.get("rule") == recomputed["rule"], "trigger_rule_mismatch")
    require(trigger.get("equality_counts_as_return") is False, "trigger_equality_policy_mismatch")
    require(trigger.get("numeric_tolerance") is None, "trigger_numeric_tolerance_present")
    require(trigger.get("raw_return_signal") is recomputed["return_signal"], "trigger_raw_signal_semantic_mismatch")
    require(trigger.get("raw_return_signal") is spec["require_raw_return_signal"], "trigger_raw_signal_policy_mismatch")
    require(
        trigger.get("return_signal")
        is bool(recomputed["return_signal"] and trigger.get("evaluation_complete")),
        "trigger_signal_semantic_mismatch",
    )

    trigger_nested_fields = {
        "run_id", "building_id", "delta_m",
        "post_gs_abs_signed_median_error_m",
        "perturbed_p0_abs_signed_median_error_m", "condition_met",
    }
    for label in ("candidates", "qualifying"):
        nested = trigger.get(label)
        require(isinstance(nested, list), f"trigger_{label}_not_list")
        for index, item in enumerate(nested):
            require(isinstance(item, dict), f"trigger_{label}_row_invalid:{index}")
            require(set(item) == trigger_nested_fields, f"trigger_{label}_row_schema:{index}")
            require(type(item.get("run_id")) is str and item.get("run_id") != "", f"trigger_{label}_run_id_type:{index}")
            require(type(item.get("building_id")) is str and item.get("building_id") != "", f"trigger_{label}_building_id_type:{index}")
            require(type(item.get("condition_met")) is bool, f"trigger_{label}_condition_type:{index}")
            for key in (
                "delta_m", "post_gs_abs_signed_median_error_m",
                "perturbed_p0_abs_signed_median_error_m",
            ):
                value = item.get(key)
                require(type(value) is float, f"trigger_{label}_{key}_type:{index}")
                require(math.isfinite(value), f"trigger_{label}_{key}_nonfinite:{index}")
        require(nested == recomputed[label], f"trigger_{label}_semantic_mismatch")
    required_signal = spec["require_return_signal"]
    require(trigger.get("return_signal") is required_signal, "trigger_return_signal_policy_mismatch")
    if required_signal:
        require(trigger.get("raw_return_signal") is required_signal, "final60_raw_return_signal_not_true")
    require(aggregate.get("schema") == archive["phase3_aggregate_schema"], "aggregate_schema_mismatch")
    require(aggregate.get("status") == "complete", "aggregate_status_not_complete")
    require(aggregate.get("training_runs_started") == 0, "aggregate_training_runs_nonzero")
    require(aggregate.get("new_mast3r_inference_runs") == 0, "aggregate_mast3r_runs_nonzero")
    require(aggregate.get("interpretation_or_verdict") is None, "aggregate_verdict_present")
    require(aggregate.get("gt_boundary") == phase3["scoring"]["gt_open_boundary"], "aggregate_gt_boundary_mismatch")
    require(aggregate.get("supplied_footprint_passed_to_roofer") is False, "aggregate_footprint_passed")
    contract = aggregate.get("aggregate_contract", {})
    require(contract.get("status") == "complete" and contract.get("errors") == [], "aggregate_contract_incomplete")
    require(contract.get("invalid_current_rows") == [], "aggregate_invalid_current_rows")
    require(contract.get("stale_job_directories") == [], "aggregate_stale_job_directories")
    require(contract.get("inventory", {}).get("counts") == inventory["counts"], "aggregate_inventory_counts_mismatch")
    require(contract.get("inventory", {}).get("current_run_ids") == inventory["run_ids"], "aggregate_inventory_ids_mismatch")
    require(int(contract.get("score_row_count", -1)) == int(spec["total_jobs"]), "aggregate_score_count_mismatch")
    require(int(contract.get("complete_score_count", -1)) == complete_score_count, "aggregate_complete_score_count_mismatch")
    require(int(contract.get("nonzero_height_row_count", -1)) == int(spec["nonzero_height_rows"]), "aggregate_height_count_mismatch")
    require(int(contract.get("complete_nonzero_height_row_count", -1)) == complete_nonzero_count, "aggregate_complete_height_count_mismatch")
    require(aggregate.get("trigger") == trigger, "aggregate_trigger_mismatch")
    require(int(aggregate.get("status_row_count", -1)) == len(status_rows), "aggregate_status_row_count_mismatch")
    status_ids = {str(row.get("run_id", "")) for row in status_rows}
    require(status_ids == run_ids, "status_run_ids_inventory_mismatch")
    for row in status_rows:
        run_id = str(row.get("run_id", ""))
        job = jobs_by_id[run_id]
        require(str(row.get("building_id")) == f"DEBY_LOD2_{job.building_id}", f"status_building_mismatch:{run_id}")
        require(str(row.get("arm")).lower() == job.arm, f"status_arm_mismatch:{run_id}")
        require(str(row.get("replicate")).lower() == job.replicate, f"status_replicate_mismatch:{run_id}")
        expected_kind = "none" if job.kind == "base" else job.kind
        require(str(row.get("perturbation_type")).lower() == expected_kind, f"status_perturbation_type_mismatch:{run_id}")
        same_number(row.get("perturbation_value"), job.value, f"status_perturbation_value:{run_id}")
        require(str(row.get("checkpoint")) == job.final_checkpoint, f"status_checkpoint_mismatch:{run_id}")
        require(str(row.get("prepared_root")) == job.data_root, f"status_prepared_root_mismatch:{run_id}")
        require(str(row.get("job_dir")) == f"{phase3['outputs']['job_root']}/{run_id}", f"status_job_dir_mismatch:{run_id}")
    for run_id in sorted(run_ids):
        rows = [row for row in status_rows if str(row.get("run_id")) == run_id]
        expected_terminal_status = str(score_by_id[run_id].get("score_status", ""))
        terminal = any(
            (str(row.get("stage")) == "score" and str(row.get("status")) == expected_terminal_status)
            or (str(row.get("stage")) == "pipeline" and str(row.get("status")) == "reused")
            for row in rows
        )
        require(terminal, f"status_terminal_score_missing:{run_id}")
    return {
        "score_rows": len(score_rows), "terminal_score_count": len(score_rows),
        "complete_score_count": complete_score_count,
        "partial_score_count": partial_score_count,
        "score_status_counts": dict(sorted(score_status_counts.items())),
        "certified_partial_run_ids": sorted(certified_partials),
        "certified_partial_runs": dict(sorted(certified_partials.items())),
        "certified_partial_kind_counts": dict(sorted(partial_kind_counts.items())),
        "perturbation_rows": len(perturb_rows),
        "complete_perturbation_row_count": complete_perturbation_count,
        "partial_perturbation_row_count": partial_perturbation_count,
        "nonzero_height_rows": len(nonzero),
        "complete_nonzero_height_rows": complete_nonzero_count,
        "perturbation_cell_rows": len(cell_rows), "status_rows": len(status_rows),
        "raw_return_signal": trigger.get("raw_return_signal"),
        "return_signal": trigger.get("return_signal"),
        "evaluation_complete": trigger.get("evaluation_complete"),
    }


def verify_manifest_hashes(
    aggregate: Mapping[str, Any], archive: Mapping[str, Any],
    phase3: Mapping[str, Any], repo: Path,
) -> None:
    outputs = aggregate.get("outputs", {})
    pairs = (
        ("scores_csv", "scores_sha256"),
        ("perturbation_csv", "perturbation_sha256"),
        ("perturbation_cells_csv", "perturbation_cells_sha256"),
        ("report_md", "report_sha256"),
        ("tilt_trigger", "tilt_trigger_sha256"),
        ("prewarm_verification", "prewarm_verification_sha256"),
        ("prewarm_log", "prewarm_log_sha256"),
    )
    for path_key, hash_key in pairs:
        expected_path = phase3["outputs"].get(path_key)
        require(outputs.get(path_key) == expected_path, f"aggregate_output_path_mismatch:{path_key}")
        path = repo_path(expected_path, repo)
        regular_file(path, f"aggregate_output_{path_key}")
        require(sha256_file(path) == outputs.get(hash_key), f"aggregate_output_hash_mismatch:{path_key}")
    source_map = aggregate.get("source_sha256")
    require(isinstance(source_map, dict) and source_map, "aggregate_source_sha256_missing")
    expected_sources = {
        relative(repo_path(archive["phase3_lock"], repo), repo),
        relative(repo_path(archive["phase3_script"], repo), repo),
        relative(repo_path(phase3["scoring"]["p0_scores"], repo), repo),
        relative(repo_path(phase3["scoring"]["mvs_scores"], repo), repo),
        relative(repo_path(phase3["outputs"]["image_verification"], repo), repo),
        relative(repo_path(phase3["outputs"]["prewarm_verification"], repo), repo),
        relative(repo_path(phase3["outputs"]["prewarm_log"], repo), repo),
        relative(repo_path(phase3["phase2_prewarm"]["lock"], repo), repo),
        relative(repo_path(phase3["phase2_prewarm"]["prepare_manifest"], repo), repo),
        relative(repo_path(phase3["phase2_prewarm"]["manifest"], repo), repo),
        relative(repo_path(phase3["phase2_prewarm"]["script"], repo), repo),
        relative(repo_path(phase3["phase2_prewarm"]["launcher"], repo), repo),
    }
    require(set(source_map) == expected_sources, "aggregate_source_sha256_path_set_mismatch")
    for source, expected in source_map.items():
        path = repo_path(source, repo)
        regular_file(path, "aggregate_source")
        require(sha256_file(path) == expected, f"aggregate_source_hash_mismatch:{source}")


def _zero_number(value: Any, label: str) -> None:
    require(not isinstance(value, bool), f"{label}_type")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ArchiveError(f"{label}_not_numeric") from exc
    require(math.isfinite(number) and number == 0.0, f"{label}_not_zero")


def _exact_json_int(value: Any, expected: int, label: str) -> None:
    require(type(value) is int, f"{label}_type")
    require(value == expected, f"{label}_mismatch")


def certify_partial_score_bundle(
    score: Mapping[str, Any], roofer_input: Mapping[str, Any],
    score_manifest: Mapping[str, Any], job: InventoryJob,
) -> str | None:
    """Authenticate the two terminal zero-inside-point paths without opening GT."""

    status = str(score.get("score_status", ""))
    if status == "complete":
        return None
    require(status == PARTIAL_NO_SCORED_ROOF_POINTS, f"job_score_status_invalid:{job.run_id}")
    input_status = str(roofer_input.get("status", ""))
    require(input_status in {"no_roof_evidence", "prepared"}, f"job_partial_input_status:{job.run_id}")
    require(str(score.get("score_reason", "")) == input_status, f"job_partial_reason:{job.run_id}")
    _exact_json_int(score.get("fused_inside_point_count"), 0, f"job_partial_inside_count:{job.run_id}")
    for field in (
        "height_error_signed_median_m", "height_error_abs_median_m",
        "height_error_mad_m", "height_error_rms_m",
        "edge_height_error_signed_median_m", "edge_height_error_abs_median_m",
        "edge_height_error_mad_m", "edge_height_error_rms_m",
        "interior_height_error_signed_median_m", "interior_height_error_abs_median_m",
        "interior_height_error_mad_m", "interior_height_error_rms_m",
    ):
        require(score.get(field) is None, f"job_partial_metric_present:{job.run_id}:{field}")
    for field in (
        "coverage_occupied_cells", "edge_point_count", "edge_coverage_occupied_cells",
        "interior_point_count", "interior_coverage_occupied_cells",
    ):
        _exact_json_int(score.get(field), 0, f"job_partial_occupied:{job.run_id}:{field}")
    for field in ("coverage_ratio", "edge_coverage_ratio", "interior_coverage_ratio"):
        _zero_number(score.get(field), f"job_partial_ratio:{job.run_id}:{field}")
    require(
        type(score.get("roof_evidence_point_count")) is int
        and score.get("roof_evidence_point_count") == roofer_input.get("roof_evidence_point_count"),
        f"job_partial_roof_count:{job.run_id}",
    )
    require(score.get("derived_roofprint_area_m2") == roofer_input.get("derived_roofprint_area_m2"), f"job_partial_roofprint_area:{job.run_id}")
    require(score.get("supplied_footprint_passed_to_roofer") is False, f"job_partial_supplied_footprint:{job.run_id}")
    require(
        score.get("point_evidence_derived_roofprint_passed_to_roofer")
        is roofer_input.get("point_evidence_derived_roofprint_passed_to_roofer"),
        f"job_partial_roofprint_flag:{job.run_id}",
    )

    if input_status == "no_roof_evidence":
        _exact_json_int(roofer_input.get("roof_evidence_point_count"), 0, f"job_partial_no_evidence_count:{job.run_id}")
        _zero_number(roofer_input.get("derived_roofprint_area_m2"), f"job_partial_no_evidence_area:{job.run_id}")
        require(roofer_input.get("roofer_las") == "" and roofer_input.get("derived_roofprint") == "", f"job_partial_no_evidence_paths:{job.run_id}")
        require(roofer_input.get("point_evidence_derived_roofprint_passed_to_roofer") is False, f"job_partial_no_evidence_flag:{job.run_id}")
        _exact_json_int(score_manifest.get("roofer_exit_code"), 125, f"job_partial_no_evidence_exit:{job.run_id}")
        require(score.get("roofer_status") == "failed" and score.get("roofer_reason") == "roofer_exit_125", f"job_partial_no_evidence_roofer_status:{job.run_id}")
        require(score.get("cityjson_path") == "", f"job_partial_no_evidence_cityjson_row:{job.run_id}")
        _exact_json_int(score.get("citygml_roof_point_count"), 0, f"job_partial_no_evidence_city_points:{job.run_id}")
        for path_key, hash_key in (
            ("cityjson", "cityjson_sha256"),
            ("val3dity_report", "val3dity_report_sha256"),
            ("val3dity_log", "val3dity_log_sha256"),
        ):
            require(score_manifest.get(path_key) is None and score_manifest.get(hash_key) is None, f"job_partial_no_evidence_artifact:{job.run_id}:{path_key}")
        return "no_roof_evidence"

    roof_count = roofer_input.get("roof_evidence_point_count")
    require(type(roof_count) is int and roof_count > 0, f"job_partial_prepared_roof_count:{job.run_id}")
    try:
        area = float(roofer_input.get("derived_roofprint_area_m2"))
    except (TypeError, ValueError) as exc:
        raise ArchiveError(f"job_partial_prepared_roofprint_area:{job.run_id}") from exc
    require(math.isfinite(area) and area > 0.0, f"job_partial_prepared_roofprint_area:{job.run_id}")
    require(bool(roofer_input.get("roofer_las")) and bool(roofer_input.get("derived_roofprint")), f"job_partial_prepared_paths:{job.run_id}")
    require(roofer_input.get("point_evidence_derived_roofprint_passed_to_roofer") is True, f"job_partial_prepared_roofprint_flag:{job.run_id}")
    _exact_json_int(score_manifest.get("roofer_exit_code"), 0, f"job_partial_prepared_exit:{job.run_id}")
    require(str(score.get("roofer_status", "")) != "", f"job_partial_prepared_roofer_status:{job.run_id}")
    for path_key, hash_key in (
        ("cityjson", "cityjson_sha256"),
        ("val3dity_report", "val3dity_report_sha256"),
        ("val3dity_log", "val3dity_log_sha256"),
    ):
        require(bool(score_manifest.get(path_key)), f"job_partial_prepared_artifact_path:{job.run_id}:{path_key}")
        valid_sha256(score_manifest.get(hash_key), f"job_partial_prepared_artifact_hash:{job.run_id}:{path_key}")
    require(score.get("cityjson_path") == score_manifest.get("cityjson"), f"job_partial_prepared_cityjson_row:{job.run_id}")
    return "prepared_zero_inside_points"


def validate_job_bundles(
    jobs: Sequence[InventoryJob], score_rows: Sequence[Mapping[str, str]],
    archive: Mapping[str, Any], phase3: Mapping[str, Any], aggregate: Mapping[str, Any],
    repo: Path, cache: dict[Path, tuple[int, str]] | None = None,
    score_fields: Sequence[str] | None = None,
    perturb_fields: Sequence[str] | None = None,
    cell_fields: Sequence[str] | None = None,
) -> tuple[
    list[Path], list[dict[str, Any]], list[dict[str, Any]],
    list[dict[str, str]], list[Path], dict[str, str],
]:
    rows_by_id = {str(row["run_id"]): row for row in score_rows}
    root = repo_path(phase3["outputs"]["job_root"], repo)
    require(root.is_dir() and not root.is_symlink(), "phase3_job_root_missing_or_symlink")
    actual_dirs = {path.name for path in root.iterdir() if path.is_dir()}
    expected_ids = {job.run_id for job in jobs}
    require(actual_dirs == expected_ids, "phase3_job_directory_set_mismatch")
    all_files: list[Path] = []
    fingerprint_rows: list[dict[str, Any]] = []
    authoritative_perturb_rows: list[dict[str, Any]] = []
    authoritative_cell_rows: list[dict[str, str]] = []
    bound_input_files: set[Path] = set()
    certified_partial_runs: dict[str, str] = {}
    common_score_only: Mapping[str, Any] | None = None
    global_prewarm = aggregate.get("phase2_serialized_gsplat_prewarm", {})
    raw_gt_roots = [
        repo_path(phase3["scoring"]["footprints"], repo),
        repo_path(phase3["scoring"]["lod2_dir"], repo),
    ]

    def require_not_raw_gt(path: Path, label: str) -> None:
        for raw_root in raw_gt_roots:
            try:
                path.resolve().relative_to(raw_root.resolve())
            except ValueError:
                continue
            raise ArchiveError(f"{label}_raw_gt_forbidden")

    phase3_script_sha = sha256_file(repo_path(archive["phase3_script"], repo))
    phase3_lock_sha = sha256_file(repo_path(archive["phase3_lock"], repo))
    for job in jobs:
        job_dir = root / job.run_id
        score_path = job_dir / "score_row.json"
        score_manifest_path = job_dir / "score_manifest.json"
        input_manifest_path = job_dir / "roofer_input_manifest.json"
        extraction_manifest_path = job_dir / "extraction_manifest.json"
        fused_path = job_dir / "fused_depth.npz"
        roofer_input_npz = job_dir / "roofer_input.npz"
        for path, label in (
            (score_path, "score_row"), (score_manifest_path, "score_manifest"),
            (input_manifest_path, "roofer_input_manifest"),
            (extraction_manifest_path, "extraction_manifest"),
            (fused_path, "fused_depth"), (roofer_input_npz, "roofer_input_npz"),
        ):
            regular_file(path, f"{label}:{job.run_id}")
        score = load_json(score_path)
        score_manifest = load_json(score_manifest_path)
        roofer_input = load_json(input_manifest_path)
        extraction_manifest = load_json(extraction_manifest_path)
        expected_job = job.phase3_job()
        require(set(score) == set(rows_by_id[job.run_id]), f"job_score_json_csv_schema:{job.run_id}")
        if score_fields is not None:
            require(set(score) == set(score_fields), f"job_score_schema:{job.run_id}")
        require(score.get("run_id") == job.run_id, f"job_score_run_id_mismatch:{job.run_id}")
        require(score.get("building_id") == f"DEBY_LOD2_{job.building_id}", f"job_score_building:{job.run_id}")
        require(str(score.get("arm", "")).lower() == job.arm, f"job_score_arm:{job.run_id}")
        require(str(score.get("replicate", "")).lower() == job.replicate, f"job_score_replicate:{job.run_id}")
        require(score_manifest.get("schema") == archive["schemas"]["score_manifest"], f"job_score_manifest_schema:{job.run_id}")
        require(score_manifest.get("job") == expected_job, f"job_score_manifest_identity:{job.run_id}")
        require(score_manifest.get("score_row_sha256") == sha256_file(score_path), f"job_score_row_hash:{job.run_id}")
        require(score_manifest.get("phase3_script_sha256") == phase3_script_sha, f"job_phase3_script_hash:{job.run_id}")
        require(score_manifest.get("phase3_config_sha256") == phase3_lock_sha, f"job_phase3_lock_hash:{job.run_id}")
        require(roofer_input.get("schema") == archive["schemas"]["roofer_input_manifest"], f"job_roofer_input_schema:{job.run_id}")
        require(roofer_input.get("job") == expected_job, f"job_roofer_input_identity:{job.run_id}")
        for key in ("supplied_footprint_opened", "supplied_footprint_passed_to_roofer", "lod2_opened", "als_opened", "gt_used", "lod2_used", "als_used"):
            require(roofer_input.get(key) is False, f"job_pre_score_boundary_violation:{job.run_id}:{key}")
        require(score_manifest.get("gt_opened_after_roofer_input_finalized") is True, f"job_gt_boundary_attestation_missing:{job.run_id}")
        partial_kind = certify_partial_score_bundle(score, roofer_input, score_manifest, job)
        if partial_kind is not None:
            certified_partial_runs[job.run_id] = partial_kind
        pre = score_manifest.get("pre_readout_fingerprint", {})
        score_only = score_manifest.get("score_only_fingerprint", {})
        validate_fingerprint(pre, archive["schemas"]["pre_readout_fingerprint"], f"pre:{job.run_id}")
        validate_fingerprint(score_only, archive["schemas"]["score_only_fingerprint"], f"score_only:{job.run_id}")
        pre_payload = pre.get("payload", {})
        require(set(pre_payload) == {
            "schema", "job", "phase3_script_sha256", "phase3_config_sha256",
            "pre_readout_code_dependencies", "phase2_job_config", "checkpoint_sha256",
            "prepared_sparse_images", "world_offset_manifest", "observed_ground_source",
            "phase2_serialized_gsplat_prewarm", "locked_docker_image_ids",
        }, f"job_pre_payload_schema:{job.run_id}")
        require(pre_payload.get("job") == expected_job, f"job_pre_identity:{job.run_id}")
        require(pre_payload.get("phase2_serialized_gsplat_prewarm") == global_prewarm, f"job_pre_prewarm_binding:{job.run_id}")
        config_binding = pre_payload.get("phase2_job_config")
        require(config_binding == {
            "path": job.config_path, "sha256": job.config_sha256,
        }, f"job_pre_config_binding:{job.run_id}")
        require(pre_payload.get("checkpoint_sha256") == job.checkpoint_sha256, f"job_pre_checkpoint_hash:{job.run_id}")
        phase2_input_paths = {
            "config": (
                repo_path(job.config_path, repo), job.config_sha256,
            ),
            "surface_seed": (
                repo_path(job.surface_seed_npz, repo), job.surface_seed_sha256,
            ),
            "checkpoint": (
                repo_path(job.final_checkpoint, repo), job.checkpoint_sha256,
            ),
        }
        for label, (input_path, expected_hash) in phase2_input_paths.items():
            require_not_raw_gt(input_path, f"job_phase2_{label}:{job.run_id}")
            _, observed_hash = file_hash(
                input_path, f"job_phase2_{label}:{job.run_id}", cache,
            )
            require(
                observed_hash == expected_hash,
                f"job_phase2_{label}_hash_drift:{job.run_id}",
            )
            bound_input_files.add(input_path)
        prepared_bundle = pre_payload.get("prepared_sparse_images", {})
        require(prepared_bundle.get("prepared_root") == job.data_root, f"job_pre_prepared_root:{job.run_id}")
        prepared_files = validate_file_bundle(
            prepared_bundle, f"job_pre_prepared:{job.run_id}", repo=repo,
            reopen=True, allowed_root=repo_path(job.data_root, repo), cache=cache,
        )
        require(prepared_files, f"job_pre_prepared_empty:{job.run_id}")
        bound_input_files.update(repo_path(row["path"], repo) for row in prepared_files)
        code_files = validate_file_bundle(
            pre_payload.get("pre_readout_code_dependencies", {}),
            f"job_pre_code:{job.run_id}", repo=repo, reopen=True, cache=cache,
        )
        require(
            [row["path"] for row in code_files] == ["src/stage2/colmap_io.py"],
            f"job_pre_code_path_set:{job.run_id}",
        )
        bound_input_files.update(repo_path(row["path"], repo) for row in code_files)
        expected_bindings = {
            "world_offset_manifest": phase3["extraction"]["world_offset_manifest"],
            "observed_ground_source": phase3["roof_evidence"]["ground_source_csv"],
        }
        for binding_key in ("world_offset_manifest", "observed_ground_source"):
            binding = pre_payload.get(binding_key)
            require(isinstance(binding, dict) and set(binding) == {"path", "sha256"}, f"job_pre_{binding_key}_schema:{job.run_id}")
            path_text = normalized_repo_relative(binding.get("path"), f"job_pre_{binding_key}_path:{job.run_id}", repo)
            require(path_text == expected_bindings[binding_key], f"job_pre_{binding_key}_wrong_path:{job.run_id}")
            bound_path = repo_path(path_text, repo)
            require_not_raw_gt(bound_path, f"job_pre_{binding_key}:{job.run_id}")
            _, observed_hash = file_hash(bound_path, f"job_pre_{binding_key}:{job.run_id}", cache)
            require(observed_hash == valid_sha256(binding.get("sha256"), f"job_pre_{binding_key}_hash:{job.run_id}"), f"job_pre_{binding_key}_drift:{job.run_id}")
            bound_input_files.add(bound_path)
        score_payload = score_only.get("payload", {})
        require(set(score_payload) == {"schema", "boundary", "bundle"}, f"job_score_only_payload_schema:{job.run_id}")
        score_only_files = validate_file_bundle(
            score_payload.get("bundle", {}), f"job_score_only_bundle:{job.run_id}",
            repo=repo, reopen=False, cache=cache,
        )
        require(score_only_files, f"job_score_only_bundle_empty:{job.run_id}")
        if common_score_only is None:
            common_score_only = score_only
        else:
            require(score_only == common_score_only, f"job_score_only_not_common:{job.run_id}")
        pre_serialized = json.dumps(pre.get("payload", {}), ensure_ascii=False, sort_keys=True)
        for forbidden in (phase3["scoring"]["footprints"], phase3["scoring"]["lod2_dir"]):
            require(str(forbidden) not in pre_serialized, f"job_gt_path_in_pre_fingerprint:{job.run_id}")
        require(
            pre_payload.get("phase3_script_sha256") == phase3_script_sha
            and pre_payload.get("phase3_config_sha256") == phase3_lock_sha,
            f"job_pre_source_fingerprint_mismatch:{job.run_id}",
        )
        require(
            pre_payload.get("locked_docker_image_ids") == {
                "render": phase3["containers"]["render_image_id"],
                "tools": phase3["containers"]["tools_image_id"],
                "roofer": phase3["roofer"]["image_id_record"],
            },
            f"job_pre_image_ids_mismatch:{job.run_id}",
        )
        require(
            score_only.get("payload", {}).get("boundary") == phase3["scoring"]["gt_open_boundary"],
            f"job_score_boundary_mismatch:{job.run_id}",
        )
        expected_full = canonical_digest({
            "schema": "jointbuildgs.s3ap.phase3.full_reuse_fingerprint.v1",
            "pre_readout_digest": pre["digest"], "score_only_digest": score_only["digest"],
        })
        require(score_manifest.get("full_reuse_fingerprint") == expected_full, f"job_full_fingerprint_mismatch:{job.run_id}")
        require(score_manifest.get("roofer_input_manifest_sha256") == sha256_file(input_manifest_path), f"job_input_manifest_hash:{job.run_id}")
        require(score_manifest.get("score_row") == relative(score_path, repo), f"job_score_manifest_path:{job.run_id}")
        require(score_manifest.get("roofer_input_manifest") == relative(input_manifest_path, repo), f"job_input_manifest_path:{job.run_id}")
        require(roofer_input.get("pre_readout_fingerprint") == pre, f"job_input_pre_fingerprint_mismatch:{job.run_id}")
        require(extraction_manifest.get("job") == expected_job, f"job_extraction_identity:{job.run_id}")
        require(extraction_manifest.get("pre_readout_fingerprint") == pre, f"job_extraction_pre_fingerprint:{job.run_id}")
        require(extraction_manifest.get("checkpoint") == job.final_checkpoint, f"job_extraction_checkpoint_path:{job.run_id}")
        require(extraction_manifest.get("checkpoint_sha256") == job.checkpoint_sha256, f"job_extraction_checkpoint_hash:{job.run_id}")
        require(extraction_manifest.get("prepared_root") == job.data_root, f"job_extraction_prepared_root:{job.run_id}")
        for key in ("gt_used", "lod2_used", "als_used"):
            require(extraction_manifest.get(key) is False, f"job_extraction_gt_boundary:{job.run_id}:{key}")
        require(extraction_manifest.get("output_npz") == relative(fused_path, repo), f"job_extraction_output_path:{job.run_id}")
        require(extraction_manifest.get("output_sha256") == sha256_file(fused_path), f"job_extraction_output_hash:{job.run_id}")
        require(roofer_input.get("source_extraction_manifest") == relative(extraction_manifest_path, repo), f"job_roofer_source_manifest_path:{job.run_id}")
        require(roofer_input.get("source_extraction_sha256") == sha256_file(fused_path), f"job_roofer_source_hash:{job.run_id}")
        require(roofer_input.get("roofer_input_npz") == relative(roofer_input_npz, repo), f"job_roofer_npz_path:{job.run_id}")
        require(roofer_input.get("roofer_input_npz_sha256") == sha256_file(roofer_input_npz), f"job_roofer_npz_hash:{job.run_id}")
        for path_key, hash_key in (
            ("roofer_las", "roofer_las_sha256"),
            ("derived_roofprint", "derived_roofprint_sha256"),
        ):
            value = str(roofer_input.get(path_key, ""))
            digest = str(roofer_input.get(hash_key, ""))
            if value:
                artifact = repo_path(value, repo)
                ensure_within(artifact, job_dir, f"job_roofer_{path_key}:{job.run_id}")
                _, observed_hash = file_hash(artifact, f"job_roofer_{path_key}:{job.run_id}", cache)
                require(observed_hash == digest, f"job_roofer_{path_key}_hash:{job.run_id}")
            else:
                require(digest == "", f"job_roofer_{path_key}_hash_without_path:{job.run_id}")
        csv_row = rows_by_id[job.run_id]
        for field, value in score.items():
            require(str(csv_row.get(field, "")) == csv_scalar(value), f"job_csv_json_value_mismatch:{job.run_id}:{field}")
        require(score.get("extraction_manifest") == relative(job_dir / "extraction_manifest.json", repo), f"job_score_extraction_path:{job.run_id}")
        require(score.get("roofer_input_manifest") == relative(input_manifest_path, repo), f"job_score_input_path:{job.run_id}")
        perturbation_expected = bool(job.arm == "a1" and job.replicate == "r1" and job.kind in {"base", "height"})
        for path_key, hash_key, filename in (
            ("perturbation_row", "perturbation_row_sha256", "perturbation_row.json"),
            ("perturbation_cells", "perturbation_cells_sha256", "perturbation_cells.csv"),
        ):
            expected_path = job_dir / filename
            if perturbation_expected:
                regular_file(expected_path, f"job_{path_key}:{job.run_id}")
                require(score_manifest.get(path_key) == relative(expected_path, repo), f"job_{path_key}_path:{job.run_id}")
                require(score_manifest.get(hash_key) == sha256_file(expected_path), f"job_{path_key}_hash:{job.run_id}")
            else:
                require(score_manifest.get(path_key) is None, f"job_{path_key}_unexpected:{job.run_id}")
                require(score_manifest.get(hash_key) is None, f"job_{hash_key}_unexpected:{job.run_id}")
        if perturbation_expected:
            perturb_value = load_json(job_dir / "perturbation_row.json")
            if perturb_fields is not None:
                require(set(perturb_value) == set(perturb_fields), f"job_perturbation_schema:{job.run_id}")
            authoritative_perturb_rows.append(perturb_value)
            observed_cell_header, observed_cells = read_csv(job_dir / "perturbation_cells.csv")
            if cell_fields is not None:
                require(observed_cell_header == list(cell_fields), f"job_cells_schema:{job.run_id}")
            authoritative_cell_rows.extend(observed_cells)
        for path_key, hash_key in (
            ("cityjson", "cityjson_sha256"),
            ("val3dity_report", "val3dity_report_sha256"),
            ("val3dity_log", "val3dity_log_sha256"),
        ):
            value = score_manifest.get(path_key)
            digest = score_manifest.get(hash_key)
            if value:
                artifact = repo_path(str(value), repo)
                ensure_within(artifact, job_dir, f"job_{path_key}:{job.run_id}")
                _, observed_hash = file_hash(artifact, f"job_{path_key}:{job.run_id}", cache)
                require(observed_hash == digest, f"job_{path_key}_hash:{job.run_id}")
            else:
                require(digest is None, f"job_{path_key}_hash_without_path:{job.run_id}")
        phase2_input_binding = {
            "schema": PHASE2_INPUT_BINDING_SCHEMA,
            "random_seed": job.random_seed,
            "config": {"path": job.config_path, "sha256": job.config_sha256},
            "surface_seed": {
                "path": job.surface_seed_npz, "sha256": job.surface_seed_sha256,
            },
            "checkpoint": {
                "path": job.final_checkpoint, "sha256": job.checkpoint_sha256,
            },
        }
        fingerprint_rows.append({
            "run_id": job.run_id, "pre_readout_digest": pre["digest"],
            "score_only_digest": score_only["digest"],
            "full_reuse_fingerprint": expected_full,
            "score_status": str(score.get("score_status", "")),
            "certified_partial_kind": partial_kind,
            "score_only_bundle_file_count": int(score_only["payload"].get("bundle", {}).get("file_count", -1)),
            "gt_content_reopened_by_archive": False,
            "phase2_input_binding": phase2_input_binding,
            "phase2_input_binding_digest": canonical_digest(phase2_input_binding),
        })
        entries = list(job_dir.rglob("*"))
        require(not any(path.is_symlink() for path in entries), f"job_bundle_symlink:{job.run_id}")
        files = sorted(path for path in entries if path.is_file())
        require(files, f"job_bundle_empty:{job.run_id}")
        all_files.extend(files)
    require(aggregate.get("aggregate_contract", {}).get("invalid_current_rows") == [], "aggregate_invalid_jobs_present")
    require(common_score_only is not None, "job_score_only_common_missing")
    for job in jobs:
        bound_input_files.update({
            repo_path(job.config_path, repo), repo_path(job.surface_seed_npz, repo),
            repo_path(job.final_checkpoint, repo),
        })
    return (
        sorted(set(all_files)), fingerprint_rows,
        sorted(authoritative_perturb_rows, key=lambda row: str(row.get("run_id", ""))),
        authoritative_cell_rows, sorted(bound_input_files), certified_partial_runs,
    )


def file_record(path: Path, disposition: str, role: str, repo: Path, archive_path: str | None = None) -> dict[str, Any]:
    regular_file(path, role)
    record = {
        "source_path": relative(path, repo), "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path), "disposition": disposition, "role": role,
    }
    if archive_path is not None:
        record["archive_path"] = archive_path
    return record


def source_mapping(
    *, copied: Sequence[tuple[Path, str]], bound: Sequence[tuple[Path, str]],
    copy_prefix: str, repo: Path,
) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for path, role in copied:
        source = relative(path, repo)
        archive_path = f"{copy_prefix}/{source}"
        record = file_record(path, "copied", role, repo, archive_path)
        previous = records.get(source)
        require(previous is None or previous == record, f"source_mapping_conflict:{source}")
        records[source] = record
    for path, role in bound:
        source = relative(path, repo)
        if source in records:
            continue
        records[source] = file_record(path, "sha256_only", role, repo)
    return [records[key] for key in sorted(records)]


def validate_source_mapping_bytes(
    mapping: Sequence[Mapping[str, Any]], repo: Path, label: str,
) -> None:
    """Reopen every copied and SHA-only source and require the declared bytes."""

    require(isinstance(mapping, (list, tuple)) and bool(mapping), f"{label}_empty")
    observed_paths: list[str] = []
    for row in mapping:
        require(isinstance(row, dict), f"{label}_row_type")
        disposition = row.get("disposition")
        expected_fields = {
            "source_path", "size_bytes", "sha256", "disposition", "role",
        } | ({"archive_path"} if disposition == "copied" else set())
        require(
            disposition in {"copied", "sha256_only"} and set(row) == expected_fields,
            f"{label}_row_schema",
        )
        source_text = normalized_repo_relative(
            row.get("source_path"), f"{label}_source", repo,
        )
        require(source_text not in observed_paths, f"{label}_source_duplicate:{source_text}")
        observed_paths.append(source_text)
        require(
            type(row.get("size_bytes")) is int and int(row["size_bytes"]) >= 0,
            f"{label}_size:{source_text}",
        )
        expected_hash = valid_sha256(row.get("sha256"), f"{label}_hash:{source_text}")
        require(isinstance(row.get("role"), str) and row.get("role") != "", f"{label}_role:{source_text}")
        source = repo_path(source_text, repo)
        regular_file(source, f"{label}_file")
        require(source.stat().st_size == row["size_bytes"], f"{label}_size_drift:{source_text}")
        require(sha256_file(source) == expected_hash, f"{label}_hash_drift:{source_text}")
    require(observed_paths == sorted(observed_paths), f"{label}_not_sorted")


def validate_executed_source_mapping(
    mapping: Sequence[Mapping[str, Any]], executed_sources: Mapping[str, Any],
) -> None:
    require(set(executed_sources) == {
        "archive_controller", "phase3_controller",
    }, "executed_source_labels_mismatch")
    mapped = {str(row.get("source_path", "")): row for row in mapping}
    for label, binding in executed_sources.items():
        require(
            isinstance(binding, dict) and set(binding) == {"path", "sha256"},
            f"executed_{label}_binding_schema",
        )
        digest = valid_sha256(binding.get("sha256"), f"executed_{label}_binding_hash")
        require(
            mapped.get(str(binding.get("path", "")), {}).get("sha256") == digest,
            f"executed_{label}_mapping_mismatch",
        )


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    require(not destination.exists(), f"archive_staging_destination_exists:{destination}")
    temporary = destination.with_name(destination.name + f".tmp.{os.getpid()}")
    require(not temporary.exists(), f"archive_copy_temporary_exists:{temporary}")
    with source.open("rb") as src, temporary.open("xb") as dst:
        shutil.copyfileobj(src, dst, length=1 << 20)
        dst.flush()
        os.fsync(dst.fileno())
    require(sha256_file(temporary) == sha256_file(source), f"archive_copy_hash_mismatch:{source}")
    os.replace(temporary, destination)


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    require(not path.exists() and not temporary.exists(), f"archive_metadata_destination_exists:{path}")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


ARCHIVE_MANIFEST_METADATA = {
    "schema", "status", "created_utc", "source_mapping", "source_mapping_digest",
    "archive_payload_digest", "copied_file_count", "sha256_only_file_count",
}
ARCHIVE_PAYLOAD_FIELDS = {
    "wave", "task_date", "crs", "archive_lock", "archive_lock_sha256",
    "phase3_lock", "phase3_lock_sha256", "phase3_aggregate_manifest",
    "phase3_aggregate_manifest_sha256", "inventory_contract",
    "measurement_counts", "wave_reconciliation", "executed_sources",
    "image_verification", "prewarm_verification", "source_fingerprints",
    "gt_boundary", "large_output_policy", "training_runs_started",
    "new_mast3r_inference_runs", "interpretation_or_verdict",
}


def validate_archive_payload_contract(
    payload: Mapping[str, Any], mapping: Sequence[Mapping[str, Any]],
    *, archive: Mapping[str, Any] | None,
) -> None:
    require(set(payload) == ARCHIVE_PAYLOAD_FIELDS, "existing_archive_payload_fields")
    require(isinstance(mapping, (list, tuple)) and bool(mapping), "existing_archive_payload_mapping_empty")
    require(all(isinstance(row, dict) for row in mapping), "existing_archive_payload_mapping_row")
    mapping_sources = [str(row.get("source_path", "")) for row in mapping]
    require(
        len(mapping_sources) == len(set(mapping_sources))
        and mapping_sources == sorted(mapping_sources),
        "existing_archive_payload_mapping_sources",
    )
    wave = str(payload.get("wave", ""))
    require(wave in {"base42", "final60"}, "existing_archive_payload_wave")
    spec = locked_wave_policy(wave)

    def exact_int(value: Any, label: str, *, minimum: int | None = None) -> int:
        require(type(value) is int, f"{label}_type")
        result = int(value)
        if minimum is not None:
            require(result >= minimum, f"{label}_minimum")
        return result

    if archive is not None:
        require(archive.get("schema") == ARCHIVE_LOCK_SCHEMA, "existing_archive_lock_schema")
        require(payload.get("task_date") == archive.get("task_date"), "existing_archive_task_date")
        require(payload.get("crs") == archive.get("crs"), "existing_archive_crs")
        require(archive.get("waves", {}).get(wave, {}) == spec, "existing_archive_wave_lock_contract")
    require(payload.get("task_date") == "2026-07-15", "existing_archive_locked_task_date")
    require(payload.get("crs") == "EPSG:25832", "existing_archive_locked_crs")
    require(exact_int(payload.get("training_runs_started"), "existing_archive_training_runs") == 0, "existing_archive_training_runs")
    require(exact_int(payload.get("new_mast3r_inference_runs"), "existing_archive_mast3r_runs") == 0, "existing_archive_mast3r_runs")
    require(payload.get("interpretation_or_verdict") is None, "existing_archive_verdict")
    inventory = payload.get("inventory_contract")
    require(isinstance(inventory, dict) and set(inventory) == {
        "wave", "counts", "run_ids", "base_tuple_count", "height_tuple_count",
        "tilt_tuple_count", "job_contract_digest",
    }, "existing_archive_inventory_fields")
    require(inventory.get("wave") == wave, "existing_archive_inventory_wave")
    counts = inventory.get("counts")
    require(counts == {
        "total": spec["total_jobs"], "base": spec["base_jobs"],
        "height_nonzero": spec["height_nonzero_jobs"], "tilt": spec["tilt_jobs"],
    }, "existing_archive_inventory_locked_counts")
    run_ids = inventory.get("run_ids")
    require(
        isinstance(run_ids, list) and len(run_ids) == spec["total_jobs"]
        and len(set(run_ids)) == spec["total_jobs"] and run_ids == sorted(run_ids),
        "existing_archive_inventory_run_ids",
    )
    require(exact_int(inventory.get("base_tuple_count"), "existing_archive_base_tuple_count") == 18, "existing_archive_base_tuple_count")
    require(exact_int(inventory.get("height_tuple_count"), "existing_archive_height_tuple_count") == 24, "existing_archive_height_tuple_count")
    require(exact_int(inventory.get("tilt_tuple_count"), "existing_archive_tilt_tuple_count") == spec["tilt_jobs"], "existing_archive_tilt_tuple_count")
    valid_sha256(inventory.get("job_contract_digest"), "existing_archive_inventory_digest")
    measurements = payload.get("measurement_counts")
    require(isinstance(measurements, dict) and set(measurements) == {
        "score_rows", "terminal_score_count", "complete_score_count",
        "partial_score_count", "score_status_counts", "certified_partial_run_ids",
        "certified_partial_runs", "certified_partial_kind_counts", "perturbation_rows",
        "complete_perturbation_row_count", "partial_perturbation_row_count",
        "nonzero_height_rows", "complete_nonzero_height_rows",
        "perturbation_cell_rows", "status_rows",
        "raw_return_signal", "return_signal", "evaluation_complete", "declared_figure_files",
        "skipped_figure_records",
    }, "existing_archive_measurement_fields")
    require(exact_int(measurements.get("score_rows"), "existing_archive_score_rows") == spec["total_jobs"], "existing_archive_score_rows")
    require(exact_int(measurements.get("terminal_score_count"), "existing_archive_terminal_scores") == spec["terminal_scores"], "existing_archive_terminal_scores")
    require(exact_int(measurements.get("complete_score_count"), "existing_archive_complete_scores") == spec["complete_scores"], "existing_archive_complete_scores")
    require(exact_int(measurements.get("partial_score_count"), "existing_archive_partial_scores") == spec["certified_partial_scores"], "existing_archive_partial_scores")
    require(measurements.get("certified_partial_kind_counts") == spec["certified_partial_kind_counts"], "existing_archive_partial_kind_counts")
    require(measurements.get("certified_partial_runs") == spec["certified_partial_runs"], "existing_archive_partial_runs")
    expected_status_counts = {"complete": spec["complete_scores"]}
    if spec["certified_partial_scores"]:
        expected_status_counts[PARTIAL_NO_SCORED_ROOF_POINTS] = spec["certified_partial_scores"]
    require(measurements.get("score_status_counts") == expected_status_counts, "existing_archive_score_status_counts")
    partial_ids = measurements.get("certified_partial_run_ids")
    require(
        isinstance(partial_ids, list)
        and len(partial_ids) == spec["certified_partial_scores"]
        and len(set(partial_ids)) == len(partial_ids)
        and partial_ids == sorted(partial_ids)
        and set(partial_ids).issubset(set(run_ids)),
        "existing_archive_certified_partial_ids",
    )
    require(exact_int(measurements.get("perturbation_rows"), "existing_archive_perturbation_rows") == spec["perturbation_rows"], "existing_archive_perturbation_rows")
    require(exact_int(measurements.get("complete_perturbation_row_count"), "existing_archive_complete_perturbation_rows") == spec["complete_perturbation_rows"], "existing_archive_complete_perturbation_rows")
    require(exact_int(measurements.get("partial_perturbation_row_count"), "existing_archive_partial_perturbation_rows") == spec["partial_perturbation_rows"], "existing_archive_partial_perturbation_rows")
    require(exact_int(measurements.get("nonzero_height_rows"), "existing_archive_height_rows") == spec["nonzero_height_rows"], "existing_archive_height_rows")
    require(exact_int(measurements.get("complete_nonzero_height_rows"), "existing_archive_complete_height_rows") == spec["complete_nonzero_height_rows"], "existing_archive_complete_height_rows")
    require(exact_int(measurements.get("perturbation_cell_rows"), "existing_archive_cell_rows") >= 27, "existing_archive_cell_rows")
    require(exact_int(measurements.get("status_rows"), "existing_archive_status_rows") >= spec["total_jobs"], "existing_archive_status_rows")
    require(measurements.get("evaluation_complete") is spec["require_evaluation_complete"], "existing_archive_evaluation_policy")
    require(measurements.get("raw_return_signal") is spec["require_raw_return_signal"], "existing_archive_raw_return_signal_policy")
    require(isinstance(measurements.get("return_signal"), bool), "existing_archive_return_signal_type")
    require(measurements.get("return_signal") is spec["require_return_signal"], "existing_archive_return_signal_policy")
    require(exact_int(measurements.get("declared_figure_files"), "existing_archive_figure_count") > 0, "existing_archive_figure_count")
    require(exact_int(measurements.get("skipped_figure_records"), "existing_archive_skipped_figures") >= 0, "existing_archive_skipped_figures")
    mapping_lookup = {str(row.get("source_path", "")): row for row in mapping}
    reconciliation = payload.get("wave_reconciliation")
    require(isinstance(reconciliation, dict) and set(reconciliation) == {
        "schema", "wave", "inventory_job_contract_digest",
        "phase3_aggregate_manifest", "phase3_aggregate_manifest_sha256",
        "source_mapping_digest", "terminal_score_count", "complete_score_count",
        "partial_score_count", "score_status_counts", "certified_partial_run_ids",
        "certified_partial_runs", "certified_partial_kind_counts", "complete_perturbation_row_count",
        "partial_perturbation_row_count", "nonzero_height_rows",
        "complete_nonzero_height_rows",
        "evaluation_complete", "raw_return_signal", "return_signal", "outputs",
    }, "existing_archive_reconciliation_fields")
    expected_reconciliation_schema = (
        archive["schemas"]["wave_reconciliation"] if archive is not None
        else "jointbuildgs.s3ap.phase3.wave_reconciliation.v2"
    )
    require(reconciliation.get("schema") == expected_reconciliation_schema, "existing_archive_reconciliation_schema")
    require(reconciliation.get("wave") == wave, "existing_archive_reconciliation_wave")
    require(
        reconciliation.get("inventory_job_contract_digest")
        == inventory.get("job_contract_digest"),
        "existing_archive_reconciliation_inventory",
    )
    require(
        reconciliation.get("phase3_aggregate_manifest")
        == payload.get("phase3_aggregate_manifest")
        and reconciliation.get("phase3_aggregate_manifest_sha256")
        == payload.get("phase3_aggregate_manifest_sha256"),
        "existing_archive_reconciliation_aggregate",
    )
    require(
        reconciliation.get("source_mapping_digest") == canonical_digest(list(mapping)),
        "existing_archive_reconciliation_mapping",
    )
    for key in (
        "terminal_score_count", "complete_score_count", "partial_score_count",
        "score_status_counts", "certified_partial_run_ids",
        "certified_partial_runs", "certified_partial_kind_counts", "complete_perturbation_row_count",
        "partial_perturbation_row_count", "nonzero_height_rows",
        "complete_nonzero_height_rows", "evaluation_complete", "raw_return_signal",
        "return_signal",
    ):
        require(reconciliation.get(key) == measurements.get(key), f"existing_archive_reconciliation_measurement:{key}")
    reconciliation_outputs = reconciliation.get("outputs")
    require(
        isinstance(reconciliation_outputs, dict)
        and set(reconciliation_outputs) == {"scores", "perturbation", "cells", "trigger"},
        "existing_archive_reconciliation_outputs",
    )
    require(
        all(isinstance(row, dict) for row in reconciliation_outputs.values()),
        "existing_archive_reconciliation_output_rows",
    )
    require(
        len({str(row.get("source_path", "")) for row in reconciliation_outputs.values()}) == 4,
        "existing_archive_reconciliation_output_sources_not_unique",
    )
    require(
        len({str(row.get("archive_path", "")) for row in reconciliation_outputs.values()}) == 4,
        "existing_archive_reconciliation_output_archives_not_unique",
    )
    for label, output in reconciliation_outputs.items():
        require(isinstance(output, dict) and set(output) == {
            "source_path", "archive_path", "size_bytes", "sha256",
        }, f"existing_archive_reconciliation_output_schema:{label}")
        mapped_output = mapping_lookup.get(str(output.get("source_path", "")))
        require(
            mapped_output is not None and mapped_output.get("disposition") == "copied"
            and output == {
                "source_path": mapped_output["source_path"],
                "archive_path": mapped_output["archive_path"],
                "size_bytes": mapped_output["size_bytes"],
                "sha256": mapped_output["sha256"],
            }, f"existing_archive_reconciliation_output_mismatch:{label}",
        )
    fingerprints = payload.get("source_fingerprints")
    require(isinstance(fingerprints, list) and len(fingerprints) == spec["total_jobs"], "existing_archive_fingerprint_count")
    fingerprint_ids: list[str] = []
    for row in fingerprints:
        require(isinstance(row, dict) and set(row) == {
            "run_id", "pre_readout_digest", "score_only_digest",
            "full_reuse_fingerprint", "score_only_bundle_file_count",
            "score_status", "certified_partial_kind",
            "gt_content_reopened_by_archive", "phase2_input_binding",
            "phase2_input_binding_digest",
        }, "existing_archive_fingerprint_fields")
        fingerprint_ids.append(str(row.get("run_id", "")))
        for key in ("pre_readout_digest", "score_only_digest", "full_reuse_fingerprint"):
            valid_sha256(row.get(key), f"existing_archive_fingerprint:{key}")
        require(exact_int(row.get("score_only_bundle_file_count"), "existing_archive_fingerprint_bundle_count") > 0, "existing_archive_fingerprint_bundle_count")
        require(row.get("gt_content_reopened_by_archive") is False, "existing_archive_fingerprint_gt_reopened")
        run_id = str(row.get("run_id", ""))
        if run_id in set(partial_ids):
            require(row.get("score_status") == PARTIAL_NO_SCORED_ROOF_POINTS, f"existing_archive_fingerprint_partial_status:{run_id}")
            require(
                row.get("certified_partial_kind") == spec["certified_partial_runs"].get(run_id),
                f"existing_archive_fingerprint_partial_kind:{run_id}",
            )
        else:
            require(row.get("score_status") == "complete", f"existing_archive_fingerprint_complete_status:{run_id}")
            require(row.get("certified_partial_kind") is None, f"existing_archive_fingerprint_complete_kind:{run_id}")
        input_binding = row.get("phase2_input_binding")
        require(isinstance(input_binding, dict) and set(input_binding) == {
            "schema", "random_seed", "config", "surface_seed", "checkpoint",
        }, "existing_archive_phase2_binding_fields")
        require(input_binding.get("schema") == PHASE2_INPUT_BINDING_SCHEMA, "existing_archive_phase2_binding_schema")
        exact_int(input_binding.get("random_seed"), "existing_archive_phase2_binding_seed", minimum=1)
        require(
            row.get("phase2_input_binding_digest") == canonical_digest(input_binding),
            "existing_archive_phase2_binding_digest",
        )
        for label in ("config", "surface_seed", "checkpoint"):
            binding = input_binding.get(label)
            require(
                isinstance(binding, dict) and set(binding) == {"path", "sha256"},
                f"existing_archive_phase2_binding_file_fields:{label}",
            )
            digest = valid_sha256(
                binding.get("sha256"), f"existing_archive_phase2_binding_file_hash:{label}",
            )
            require(
                mapping_lookup.get(str(binding.get("path", "")), {}).get("sha256") == digest,
                f"existing_archive_phase2_binding_mapping:{label}",
            )
    require(fingerprint_ids == run_ids, "existing_archive_fingerprint_ids")
    fingerprint_kind_counts: dict[str, int] = {}
    for row in fingerprints:
        kind = row.get("certified_partial_kind")
        if kind is not None:
            fingerprint_kind_counts[str(kind)] = fingerprint_kind_counts.get(str(kind), 0) + 1
    require(fingerprint_kind_counts == spec["certified_partial_kind_counts"], "existing_archive_fingerprint_partial_kind_counts")
    for payload_path_key, payload_hash_key in (
        ("archive_lock", "archive_lock_sha256"),
        ("phase3_lock", "phase3_lock_sha256"),
        ("phase3_aggregate_manifest", "phase3_aggregate_manifest_sha256"),
    ):
        path = str(payload.get(payload_path_key, ""))
        digest = valid_sha256(payload.get(payload_hash_key), f"existing_archive_{payload_hash_key}")
        require(mapping_lookup.get(path, {}).get("sha256") == digest, f"existing_archive_payload_mapping:{payload_path_key}")
    executed = payload.get("executed_sources")
    require(isinstance(executed, dict) and set(executed) == {
        "archive_controller", "phase3_controller",
    }, "existing_archive_executed_sources")
    for label, row in executed.items():
        require(isinstance(row, dict) and set(row) == {"path", "sha256"}, f"existing_archive_executed_fields:{label}")
        digest = valid_sha256(row.get("sha256"), f"existing_archive_executed_hash:{label}")
        require(mapping_lookup.get(str(row.get("path", "")), {}).get("sha256") == digest, f"existing_archive_executed_mapping:{label}")
    image_verification = payload.get("image_verification")
    require(isinstance(image_verification, dict) and set(image_verification) == {
        "path", "sha256", "tools_image_id",
    }, "existing_archive_image_verification_fields")
    image_digest = valid_sha256(image_verification.get("sha256"), "existing_archive_image_verification_hash")
    require(
        mapping_lookup.get(str(image_verification.get("path", "")), {}).get("sha256") == image_digest,
        "existing_archive_image_verification_mapping",
    )
    normalize_image_id(image_verification.get("tools_image_id"))
    if archive is not None:
        require(
            normalize_image_id(image_verification.get("tools_image_id"))
            == normalize_image_id(archive["containers"]["tools_image_id"]),
            "existing_archive_image_tools_id",
        )
    prewarm_verification = payload.get("prewarm_verification")
    require(isinstance(prewarm_verification, dict) and set(prewarm_verification) == {
        "path", "sha256", "extension_path", "extension_sha256",
    }, "existing_archive_prewarm_verification_fields")
    for path_key, hash_key in (("path", "sha256"), ("extension_path", "extension_sha256")):
        digest = valid_sha256(
            prewarm_verification.get(hash_key), f"existing_archive_prewarm_{hash_key}",
        )
        require(
            mapping_lookup.get(str(prewarm_verification.get(path_key, "")), {}).get("sha256") == digest,
            f"existing_archive_prewarm_mapping:{path_key}",
        )
    boundary = payload.get("gt_boundary")
    require(isinstance(boundary, dict) and set(boundary) == {
        "contract", "supplied_footprint_passed_to_roofer",
        "raw_gt_content_opened_by_archive", "validation_method",
    }, "existing_archive_gt_boundary_fields")
    require(boundary.get("supplied_footprint_passed_to_roofer") is False, "existing_archive_gt_boundary")
    require(boundary.get("raw_gt_content_opened_by_archive") is False, "existing_archive_raw_gt_opened")
    require(isinstance(boundary.get("contract"), str) and boundary.get("contract") != "", "existing_archive_gt_contract")
    require(isinstance(boundary.get("validation_method"), str) and boundary.get("validation_method") != "", "existing_archive_gt_validation_method")
    require(isinstance(payload.get("large_output_policy"), str) and payload.get("large_output_policy") != "", "existing_archive_large_output_policy")


def archive_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in manifest.items() if key not in ARCHIVE_MANIFEST_METADATA}


def safe_archive_relative(value: Any, label: str) -> str:
    text = str(value or "").strip()
    path = Path(text)
    require(text != "" and not path.is_absolute(), f"{label}_not_relative")
    require(".." not in path.parts and "." not in path.parts, f"{label}_traversal")
    require(path.as_posix() == text, f"{label}_not_canonical")
    return text


def verify_archive_directory(
    destination: Path, verify_bound_sources: bool, repo: Path = REPO,
    *, expected_wave: str | None = None, archive: Mapping[str, Any] | None = None,
    expected_payload: Mapping[str, Any] | None = None,
    expected_mapping: Sequence[Mapping[str, Any]] | None = None,
    forbidden_source_roots: Sequence[Path] = (),
) -> dict[str, Any]:
    require(destination.is_dir() and not destination.is_symlink(), "existing_archive_directory_invalid")
    manifest_path = destination / "archive_manifest.json"
    completion_path = destination / "COMPLETED.json"
    manifest = load_json(manifest_path)
    completion = load_json(completion_path)
    manifest_schema = (
        archive["schemas"]["archive_manifest"] if archive is not None
        else "jointbuildgs.s3ap.phase3.wave_archive.v1"
    )
    completion_schema = (
        archive["schemas"]["archive_completion"] if archive is not None
        else "jointbuildgs.s3ap.phase3.wave_archive_completion.v1"
    )
    require(manifest.get("schema") == manifest_schema, "existing_archive_manifest_schema")
    require(manifest.get("status") == "complete", "existing_archive_manifest_incomplete")
    require(completion.get("schema") == completion_schema, "existing_archive_completion_schema")
    require(completion.get("status") == "complete", "existing_archive_completion_incomplete")
    require(set(completion) == {
        "schema", "status", "created_utc", "wave", "archive_manifest_sha256",
        "source_mapping_digest", "archive_payload_digest", "copied_file_count",
        "sha256_only_file_count",
    }, "existing_archive_completion_fields")
    require(completion.get("archive_manifest_sha256") == sha256_file(manifest_path), "existing_archive_manifest_hash")
    mapping = manifest.get("source_mapping", [])
    require(isinstance(mapping, list) and mapping, "existing_archive_source_mapping_empty")
    require(manifest.get("source_mapping_digest") == canonical_digest(mapping), "existing_archive_mapping_digest")
    require(completion.get("source_mapping_digest") == manifest.get("source_mapping_digest"), "existing_archive_completion_mapping_digest")
    payload = archive_payload(manifest)
    require(manifest.get("archive_payload_digest") == canonical_digest(payload), "existing_archive_payload_digest")
    require(completion.get("archive_payload_digest") == manifest.get("archive_payload_digest"), "existing_archive_completion_payload_digest")
    wave = str(payload.get("wave", ""))
    require(wave in {"base42", "final60"}, "existing_archive_wave_invalid")
    require(completion.get("wave") == wave, "existing_archive_completion_wave_mismatch")
    if expected_wave is not None:
        require(wave == expected_wave, "existing_archive_expected_wave_mismatch")
    if expected_payload is not None:
        require(payload == dict(expected_payload), "existing_archive_payload_contract_mismatch")
    if expected_mapping is not None:
        require(mapping == list(expected_mapping), "existing_archive_mapping_contract_mismatch")
    copy_prefix = str((archive or {}).get("policy", {}).get("copy_prefix", "snapshot"))
    source_paths: list[str] = []
    archive_paths: list[str] = []
    copied_count = 0
    bound_count = 0
    for row in mapping:
        require(isinstance(row, dict), "existing_archive_mapping_row_invalid")
        source_text = normalized_repo_relative(row.get("source_path"), "existing_archive_source", repo)
        require(source_text not in source_paths, f"existing_archive_source_duplicate:{source_text}")
        source_paths.append(source_text)
        require(type(row.get("size_bytes")) is int, f"existing_archive_size_invalid:{source_text}")
        size = int(row["size_bytes"])
        require(size >= 0, f"existing_archive_size_negative:{source_text}")
        valid_sha256(row.get("sha256"), f"existing_archive_hash:{source_text}")
        require(str(row.get("role", "")).strip() != "", f"existing_archive_role_empty:{source_text}")
        source_resolved = repo_path(source_text, repo)
        for forbidden in forbidden_source_roots:
            try:
                source_resolved.relative_to(forbidden.resolve())
            except ValueError:
                continue
            raise ArchiveError(f"existing_archive_raw_gt_source_forbidden:{source_text}")
        if row.get("disposition") == "copied":
            require(set(row) == {"source_path", "size_bytes", "sha256", "disposition", "role", "archive_path"}, f"existing_archive_copy_row_schema:{source_text}")
            archive_text = safe_archive_relative(row.get("archive_path"), f"existing_archive_path:{source_text}")
            require(archive_text == f"{copy_prefix}/{source_text}", f"existing_archive_copy_path_contract:{source_text}")
            require(archive_text not in archive_paths, f"existing_archive_path_duplicate:{archive_text}")
            archive_paths.append(archive_text)
            archived = destination / archive_text
            regular_file(archived, "existing_archive_copy")
            require(archived.stat().st_size == int(row["size_bytes"]), f"existing_archive_copy_size:{row.get('source_path')}")
            require(sha256_file(archived) == row.get("sha256"), f"existing_archive_copy_hash:{row.get('source_path')}")
            copied_count += 1
        elif row.get("disposition") == "sha256_only":
            require(set(row) == {"source_path", "size_bytes", "sha256", "disposition", "role"}, f"existing_archive_bound_row_schema:{source_text}")
            require("archive_path" not in row, f"existing_bound_has_archive_path:{row.get('source_path')}")
            if verify_bound_sources:
                source = repo_path(source_text, repo)
                regular_file(source, "existing_bound_source")
                require(source.stat().st_size == int(row["size_bytes"]), f"existing_bound_size:{row.get('source_path')}")
                require(sha256_file(source) == row.get("sha256"), f"existing_bound_hash:{row.get('source_path')}")
            bound_count += 1
        else:
            raise ArchiveError(f"existing_archive_disposition_invalid:{row.get('disposition')}")
    require(source_paths == sorted(source_paths), "existing_archive_mapping_not_sorted")
    require(type(manifest.get("copied_file_count")) is int and manifest.get("copied_file_count") == copied_count, "existing_archive_manifest_copy_count")
    require(type(manifest.get("sha256_only_file_count")) is int and manifest.get("sha256_only_file_count") == bound_count, "existing_archive_manifest_bound_count")
    require(type(completion.get("copied_file_count")) is int and completion.get("copied_file_count") == copied_count, "existing_archive_completion_copy_count")
    require(type(completion.get("sha256_only_file_count")) is int and completion.get("sha256_only_file_count") == bound_count, "existing_archive_completion_bound_count")
    validate_archive_payload_contract(payload, mapping, archive=archive)
    reconciliation = payload.get("wave_reconciliation")
    require(isinstance(reconciliation, dict), "existing_archive_reconciliation_missing")
    expected_reconciliation_schema = (
        archive["schemas"]["wave_reconciliation"] if archive is not None
        else "jointbuildgs.s3ap.phase3.wave_reconciliation.v2"
    )
    require(set(reconciliation) == {
        "schema", "wave", "inventory_job_contract_digest",
        "phase3_aggregate_manifest", "phase3_aggregate_manifest_sha256",
        "source_mapping_digest", "terminal_score_count", "complete_score_count",
        "partial_score_count", "score_status_counts", "certified_partial_run_ids",
        "certified_partial_runs", "certified_partial_kind_counts", "complete_perturbation_row_count",
        "partial_perturbation_row_count", "nonzero_height_rows",
        "complete_nonzero_height_rows",
        "evaluation_complete", "raw_return_signal", "return_signal", "outputs",
    }, "existing_archive_reconciliation_fields")
    require(reconciliation.get("schema") == expected_reconciliation_schema, "existing_archive_reconciliation_schema")
    require(reconciliation.get("wave") == wave, "existing_archive_reconciliation_wave")
    require(reconciliation.get("source_mapping_digest") == manifest.get("source_mapping_digest"), "existing_archive_reconciliation_mapping")
    require(
        reconciliation.get("inventory_job_contract_digest")
        == payload.get("inventory_contract", {}).get("job_contract_digest"),
        "existing_archive_reconciliation_inventory",
    )
    require(
        reconciliation.get("phase3_aggregate_manifest") == payload.get("phase3_aggregate_manifest")
        and reconciliation.get("phase3_aggregate_manifest_sha256")
        == payload.get("phase3_aggregate_manifest_sha256"),
        "existing_archive_reconciliation_aggregate",
    )
    measurement = payload.get("measurement_counts", {})
    for reconciliation_key in (
        "terminal_score_count", "complete_score_count", "partial_score_count",
        "score_status_counts", "certified_partial_run_ids",
        "certified_partial_runs", "certified_partial_kind_counts", "complete_perturbation_row_count",
        "partial_perturbation_row_count", "nonzero_height_rows",
        "complete_nonzero_height_rows", "evaluation_complete", "raw_return_signal",
        "return_signal",
    ):
        require(
            reconciliation.get(reconciliation_key) == measurement.get(reconciliation_key),
            f"existing_archive_reconciliation_measurement:{reconciliation_key}",
        )
    outputs = reconciliation.get("outputs")
    require(isinstance(outputs, dict) and set(outputs) == {"scores", "perturbation", "cells", "trigger"}, "existing_archive_reconciliation_outputs")
    require(
        len({str(output.get("source_path", "")) for output in outputs.values()}) == 4,
        "existing_archive_reconciliation_output_sources_not_unique",
    )
    require(
        len({str(output.get("archive_path", "")) for output in outputs.values()}) == 4,
        "existing_archive_reconciliation_output_archives_not_unique",
    )
    mapping_lookup = {row["source_path"]: row for row in mapping}
    for label, output in outputs.items():
        require(isinstance(output, dict) and set(output) == {
            "source_path", "archive_path", "size_bytes", "sha256",
        }, f"existing_archive_reconciliation_output_schema:{label}")
        source = output.get("source_path")
        mapped = mapping_lookup.get(source)
        require(mapped is not None and mapped.get("disposition") == "copied", f"existing_archive_reconciliation_output_mapping:{label}")
        require(output == {
            "source_path": source, "archive_path": mapped["archive_path"],
            "size_bytes": mapped["size_bytes"], "sha256": mapped["sha256"],
        }, f"existing_archive_reconciliation_output_mismatch:{label}")
    expected_files = {"archive_manifest.json", "COMPLETED.json", *archive_paths}
    actual_files: set[str] = set()
    actual_dirs: set[str] = set()
    for path in destination.rglob("*"):
        require(not path.is_symlink(), f"existing_archive_symlink_forbidden:{path}")
        if path.is_file():
            actual_files.add(path.relative_to(destination).as_posix())
        elif path.is_dir():
            actual_dirs.add(path.relative_to(destination).as_posix())
    expected_dirs: set[str] = set()
    for filename in expected_files:
        parent = Path(filename).parent
        while parent != Path("."):
            expected_dirs.add(parent.as_posix())
            parent = parent.parent
    require(actual_files == expected_files, "existing_archive_file_set_mismatch")
    require(actual_dirs == expected_dirs, "existing_archive_directory_set_mismatch")
    return manifest


def materialize_archive(
    *, destination: Path, mapping: Sequence[Mapping[str, Any]], payload: Mapping[str, Any],
    archive: Mapping[str, Any], repo: Path = REPO,
    forbidden_source_roots: Sequence[Path] = (),
) -> dict[str, Any]:
    digest = canonical_digest(list(mapping))
    for row in mapping:
        source = repo_path(str(row.get("source_path", "")), repo)
        for forbidden in forbidden_source_roots:
            try:
                source.relative_to(forbidden.resolve())
            except ValueError:
                continue
            raise ArchiveError(f"archive_raw_gt_source_forbidden:{relative(source, repo)}")
    validate_archive_payload_contract(payload, mapping, archive=archive)
    validate_source_mapping_bytes(mapping, repo, "archive_prewrite_source")
    if destination.exists():
        existing = verify_archive_directory(
            destination, True, repo, expected_wave=str(payload.get("wave", "")),
            archive=archive, expected_payload=payload, expected_mapping=mapping,
            forbidden_source_roots=forbidden_source_roots,
        )
        require(existing.get("source_mapping_digest") == digest, "archive_exists_with_different_bytes")
        return {"status": "already_complete", "destination": relative(destination, repo), "source_mapping_digest": digest}
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    require(not parent.is_symlink(), "archive_parent_symlink_forbidden")
    staging = parent / f".{destination.name}.staging.{os.getpid()}"
    require(not staging.exists(), f"archive_staging_exists:{staging}")
    staging.mkdir()
    try:
        for row in mapping:
            if row["disposition"] != "copied":
                continue
            source = repo_path(str(row["source_path"]), repo)
            target = staging / str(row["archive_path"])
            atomic_copy(source, target)
            require(target.stat().st_size == int(row["size_bytes"]), f"staged_copy_size:{row['source_path']}")
            require(sha256_file(target) == row["sha256"], f"staged_copy_hash:{row['source_path']}")
        # Rehash SHA-only inputs as well as copied inputs at the last point
        # before the manifest is written.  This closes post-inventory and
        # copy-time drift instead of discovering it only after publication.
        validate_source_mapping_bytes(mapping, repo, "archive_final_prewrite_source")
        manifest = dict(payload)
        payload_digest = canonical_digest(payload)
        manifest.update({
            "schema": archive["schemas"]["archive_manifest"], "status": "complete",
            "created_utc": utc_now(), "source_mapping": list(mapping),
            "source_mapping_digest": digest, "archive_payload_digest": payload_digest,
            "copied_file_count": sum(row["disposition"] == "copied" for row in mapping),
            "sha256_only_file_count": sum(row["disposition"] == "sha256_only" for row in mapping),
        })
        manifest_path = staging / "archive_manifest.json"
        atomic_json(manifest_path, manifest)
        completion = {
            "schema": archive["schemas"]["archive_completion"], "status": "complete",
            "created_utc": utc_now(), "wave": manifest["wave"],
            "archive_manifest_sha256": sha256_file(manifest_path),
            "source_mapping_digest": digest, "archive_payload_digest": payload_digest,
            "copied_file_count": manifest["copied_file_count"],
            "sha256_only_file_count": manifest["sha256_only_file_count"],
        }
        atomic_json(staging / "COMPLETED.json", completion)
        fsync_directory(staging)
        os.rename(staging, destination)
        fsync_directory(parent)
    except Exception:
        # A failed staging tree is evidence.  Do not delete or overwrite it.
        raise
    verified = verify_archive_directory(
        destination, True, repo, expected_wave=str(payload.get("wave", "")),
        archive=archive, expected_payload=payload, expected_mapping=mapping,
        forbidden_source_roots=forbidden_source_roots,
    )
    return {
        "status": "complete", "destination": relative(destination, repo),
        "source_mapping_digest": verified["source_mapping_digest"],
    }


def validate_paths_only(archive: Mapping[str, Any], repo: Path = REPO) -> dict[str, Any]:
    require(archive.get("schema") == ARCHIVE_LOCK_SCHEMA, "archive_lock_schema_mismatch")
    require(archive.get("waves") == {
        wave: locked_wave_policy(wave) for wave in ("base42", "final60")
    }, "archive_wave_policies_mismatch")
    require(
        archive.get("schemas", {}).get("wave_reconciliation")
        == "jointbuildgs.s3ap.phase3.wave_reconciliation.v2",
        "archive_reconciliation_schema_mismatch",
    )
    require(
        archive.get("schemas", {}).get("archive_manifest")
        == "jointbuildgs.s3ap.phase3.wave_archive.v2",
        "archive_manifest_schema_mismatch",
    )
    require(
        archive.get("schemas", {}).get("archive_completion")
        == "jointbuildgs.s3ap.phase3.wave_archive_completion.v2",
        "archive_completion_schema_mismatch",
    )
    phase3_lock = repo_path(archive["phase3_lock"], repo)
    phase3_script = repo_path(archive["phase3_script"], repo)
    archive_root = repo_path(archive["archive_root"], repo)
    runs_root = repo_path("phases/p2-gsjso/runs", repo)
    try:
        archive_root.relative_to(runs_root)
    except ValueError as exc:
        raise ArchiveError("archive_root_outside_phase_runs") from exc
    for path, label in ((phase3_lock, "phase3_lock"), (phase3_script, "phase3_script")):
        regular_file(path, label)
    phase3 = load_json(phase3_lock)
    require(phase3.get("schema") == archive["phase3_lock_schema"], "phase3_lock_schema_mismatch")
    require(phase3.get("training_runs_allowed") == 0, "phase3_training_allowed_nonzero")
    require(phase3.get("new_mast3r_inference_allowed") is False, "phase3_mast3r_allowed")
    raw_gt = {
        repo_path(phase3["scoring"]["footprints"], repo),
        repo_path(phase3["scoring"]["lod2_dir"], repo),
    }
    declared_copy = {
        repo_path(archive["inventories"]["base"], repo), phase3_lock, phase3_script,
        *[repo_path(value, repo) for value in phase3["outputs"].values() if isinstance(value, str)],
    }
    require(not (raw_gt & declared_copy), "raw_gt_declared_for_copy")
    expected_tools = normalize_image_id(archive["containers"]["tools_image_id"])
    require(expected_tools == normalize_image_id(phase3["containers"]["tools_image_id"]), "archive_tools_id_phase3_mismatch")
    runtime_paths = {
        "base_inventory": repo_path(archive["inventories"]["base"], repo).is_file(),
        "tilt_inventory": repo_path(archive["inventories"]["tilt"], repo).is_file(),
        "aggregate_manifest": repo_path(phase3["outputs"]["manifest"], repo).is_file(),
        "scores_csv": repo_path(phase3["outputs"]["scores_csv"], repo).is_file(),
        "figure_dir": repo_path(phase3["outputs"]["figure_dir"], repo).is_dir(),
    }
    return {
        "schema": "jointbuildgs.s3ap.phase3.archive.preflight.v1",
        "status": "path_contract_valid", "raw_gt_content_opened": False,
        "archive_root": relative(archive_root, repo),
        "tools_image_id": expected_tools, "runtime_paths_present": runtime_paths,
    }


def archive_wave(wave: str, archive_path: Path = DEFAULT_CONFIG, repo: Path = REPO) -> dict[str, Any]:
    executed_controller_sha256 = validate_executed_controller_source(repo)
    archive = load_json(archive_path)
    validate_paths_only(archive, repo)
    require(wave in archive["waves"], f"wave_invalid:{wave}")
    wrapper_id = normalize_image_id(os.environ.get("S3AP_ARCHIVE_TOOLS_IMAGE_ID"))
    require(wrapper_id == normalize_image_id(archive["containers"]["tools_image_id"]), "wrapper_tools_image_attestation_mismatch")
    phase3_path = repo_path(archive["phase3_lock"], repo)
    phase3 = load_json(phase3_path)
    phase3_module = load_phase3_module(archive, repo)
    executed_phase3_sha256 = str(
        phase3_module.__archive_executed_source_sha256__
    )
    hash_cache: dict[Path, tuple[int, str]] = {}
    phase2_lock_path = repo_path(phase3["phase2_prewarm"]["lock"], repo)
    regular_file(phase2_lock_path, "phase2_lock")
    require(
        sha256_file(phase2_lock_path) == phase3["phase2_prewarm"]["lock_sha256"],
        "phase2_lock_hash_mismatch",
    )
    phase2_lock = load_json(phase2_lock_path)
    inventory_paths = [repo_path(archive["inventories"]["base"], repo)]
    if wave == "final60":
        inventory_paths.append(repo_path(archive["inventories"]["tilt"], repo))
    rows_by_source: list[tuple[str, Sequence[Mapping[str, str]]]] = []
    for path in inventory_paths:
        regular_file(path, "inventory")
        header, rows = read_csv(path)
        require(header == INVENTORY_FIELDS, f"inventory_csv_schema_mismatch:{relative(path, repo)}")
        rows_by_source.append((relative(path, repo), rows))
    jobs, inventory = validate_inventory_rows(
        rows_by_source, wave, phase3, archive["waves"][wave], repo=repo,
        phase2_lock=phase2_lock, hash_cache=hash_cache,
    )
    outputs = phase3["outputs"]
    paths = {
        "aggregate": repo_path(outputs["manifest"], repo),
        "status": repo_path(outputs["status_csv"], repo),
        "scores": repo_path(outputs["scores_csv"], repo),
        "perturbation": repo_path(outputs["perturbation_csv"], repo),
        "cells": repo_path(outputs["perturbation_cells_csv"], repo),
        "report": repo_path(outputs["report_md"], repo),
        "trigger": repo_path(outputs["tilt_trigger"], repo),
        "images": repo_path(outputs["image_verification"], repo),
        "prewarm": repo_path(outputs["prewarm_verification"], repo),
        "prewarm_log": repo_path(outputs["prewarm_log"], repo),
        "run_log": repo_path(outputs["run_log"], repo),
        "aggregate_log": repo_path(outputs["phase3_root"], repo) / "aggregate.log",
    }
    for label, path in paths.items():
        regular_file(path, label)
    aggregate = load_json(paths["aggregate"])
    trigger = load_json(paths["trigger"])
    image_payload = load_json(paths["images"])
    prewarm_payload = load_json(paths["prewarm"])
    score_header, score_rows = read_csv(paths["scores"])
    perturb_header, perturb_rows = read_csv(paths["perturbation"])
    cell_header, cell_rows = read_csv(paths["cells"])
    status_header, status_rows = read_csv(paths["status"])
    validate_image_verification(image_payload, archive, phase3)
    validate_prewarm_verification(prewarm_payload, archive, phase3)
    validate_prewarm_binding(
        aggregate.get("phase2_serialized_gsplat_prewarm", {}),
        prewarm_payload, archive, phase3, repo, hash_cache,
    )
    verify_manifest_hashes(aggregate, archive, phase3, repo)
    (
        job_files, fingerprint_rows, authoritative_perturb_rows,
        authoritative_cell_rows, job_bound_input_files, certified_partial_runs,
    ) = validate_job_bundles(
        jobs, score_rows, archive, phase3, aggregate, repo, hash_cache,
        phase3_module.SCORE_FIELDS, phase3_module.PERTURB_FIELDS,
        phase3_module.PERTURB_CELL_FIELDS,
    )
    counts = validate_wave_contract(
        wave=wave, archive=archive, phase3=phase3, jobs=jobs, inventory=inventory,
        aggregate=aggregate, trigger=trigger, score_header=score_header,
        score_rows=score_rows, perturb_header=perturb_header,
        perturb_rows=perturb_rows, cell_header=cell_header, cell_rows=cell_rows,
        status_header=status_header, status_rows=status_rows, phase3_module=phase3_module,
        authoritative_perturb_rows=authoritative_perturb_rows,
        authoritative_cell_rows=authoritative_cell_rows,
        certified_partial_runs=certified_partial_runs,
    )
    expected_trigger_fields = {
        "schema", "created_utc", "return_signal", "rule",
        "equality_counts_as_return", "numeric_tolerance", "candidate_count",
        "qualifying_count", "candidates", "qualifying", "raw_return_signal",
        "expected_nonzero_height_rows", "observed_nonzero_height_rows",
        "complete_nonzero_height_rows", "evaluation_complete", "scores_csv",
        "perturbation_csv", "perturbation_cells_csv", "source_score_sha256",
        "source_perturbation_sha256", "source_perturbation_cells_sha256",
        "tilt_deltas_deg",
    }
    require(set(trigger) == expected_trigger_fields, "trigger_fields_mismatch")
    for key, label in (
        ("scores_csv", "scores"), ("perturbation_csv", "perturbation"),
        ("perturbation_cells_csv", "cells"),
    ):
        require(trigger.get(key) == outputs[key if key != "perturbation_cells_csv" else "perturbation_cells_csv"], f"trigger_path_mismatch:{key}")
        require(
            trigger.get({
                "scores_csv": "source_score_sha256",
                "perturbation_csv": "source_perturbation_sha256",
                "perturbation_cells_csv": "source_perturbation_cells_sha256",
            }[key]) == sha256_file(paths[label]),
            f"trigger_source_hash_mismatch:{key}",
        )
    require(trigger.get("tilt_deltas_deg") == phase3["perturbation"]["tilt_deltas_deg"], "trigger_tilt_grid_mismatch")
    figures = aggregate.get("figures", {}).get("generated", [])
    require(isinstance(figures, list) and figures, "aggregate_figures_empty")
    figure_root = repo_path(outputs["figure_dir"], repo)
    declared_figures: list[Path] = []
    for value in figures:
        path = repo_path(str(value), repo)
        regular_file(path, "declared_figure")
        try:
            path.relative_to(figure_root)
        except ValueError as exc:
            raise ArchiveError(f"declared_figure_outside_figure_dir:{value}") from exc
        declared_figures.append(path)
    actual_figures = sorted(path for path in figure_root.rglob("*") if path.is_file())
    require(set(actual_figures) == set(declared_figures), "figure_directory_contains_undeclared_or_missing_files")
    counts["declared_figure_files"] = len(declared_figures)
    counts["skipped_figure_records"] = len(aggregate.get("figures", {}).get("skipped", []))
    copied: list[tuple[Path, str]] = []
    copied.extend((path, "phase2_inventory") for path in inventory_paths)
    copied.extend([
        (phase3_path, "phase3_lock"),
        (repo_path(archive["phase3_script"], repo), "phase3_controller_source"),
        (archive_path.resolve(), "archive_lock"),
    ])
    copied.extend((path, f"phase3_global_{label}") for label, path in paths.items())
    copied.extend((path, "phase3_declared_figure") for path in declared_figures)
    bound: list[tuple[Path, str]] = [(path, "phase3_per_job_output") for path in job_files]
    bound.extend((path, "phase2_job_bound_input") for path in job_bound_input_files)
    for source in aggregate.get("source_sha256", {}):
        bound.append((repo_path(source, repo), "phase3_aggregate_source"))
    extension = repo_path(prewarm_payload["extension_path"], repo)
    regular_file(extension, "prewarm_extension")
    require(sha256_file(extension) == prewarm_payload["extension_sha256"], "prewarm_extension_hash_drift")
    bound.append((extension, "verified_prewarm_extension"))
    for value in archive["archive_controller_sources"]:
        bound.append((repo_path(value, repo), "archive_controller_source"))
    forbidden_gt = [
        repo_path(phase3["scoring"]["footprints"], repo),
        repo_path(phase3["scoring"]["lod2_dir"], repo),
    ]
    for path, role in [*copied, *bound]:
        resolved = path.resolve()
        for forbidden in forbidden_gt:
            try:
                resolved.relative_to(forbidden.resolve())
            except ValueError:
                continue
            raise ArchiveError(f"archive_source_raw_gt_forbidden:{role}:{relative(path, repo)}")
    mapping = source_mapping(
        copied=copied, bound=bound, copy_prefix=archive["policy"]["copy_prefix"], repo=repo,
    )
    aggregate_sha = sha256_file(paths["aggregate"])
    mapping_by_source = {str(row["source_path"]): row for row in mapping}
    archive_controller_source = relative(Path(__file__), repo)
    phase3_controller_source = relative(repo_path(archive["phase3_script"], repo), repo)
    executed_sources = {
        "archive_controller": {
            "path": archive_controller_source, "sha256": executed_controller_sha256,
        },
        "phase3_controller": {
            "path": phase3_controller_source, "sha256": executed_phase3_sha256,
        },
    }
    validate_executed_source_mapping(mapping, executed_sources)
    reconciliation_outputs: dict[str, dict[str, Any]] = {}
    for label in ("scores", "perturbation", "cells", "trigger"):
        source = relative(paths[label], repo)
        row = mapping_by_source.get(source)
        require(row is not None and row.get("disposition") == "copied", f"reconciliation_output_not_copied:{label}")
        reconciliation_outputs[label] = {
            "source_path": source, "archive_path": row["archive_path"],
            "size_bytes": row["size_bytes"], "sha256": row["sha256"],
        }
    wave_reconciliation = {
        "schema": archive["schemas"]["wave_reconciliation"], "wave": wave,
        "inventory_job_contract_digest": inventory["job_contract_digest"],
        "phase3_aggregate_manifest": relative(paths["aggregate"], repo),
        "phase3_aggregate_manifest_sha256": aggregate_sha,
        "source_mapping_digest": canonical_digest(mapping),
        **{
            key: counts[key] for key in (
                "terminal_score_count", "complete_score_count", "partial_score_count",
                "score_status_counts", "certified_partial_run_ids",
                "certified_partial_runs", "certified_partial_kind_counts",
                "complete_perturbation_row_count",
                "partial_perturbation_row_count", "nonzero_height_rows",
                "complete_nonzero_height_rows", "evaluation_complete",
                "raw_return_signal", "return_signal",
            )
        },
        "outputs": reconciliation_outputs,
    }
    payload = {
        "wave": wave, "task_date": archive["task_date"], "crs": archive["crs"],
        "archive_lock": relative(archive_path.resolve(), repo),
        "archive_lock_sha256": sha256_file(archive_path),
        "phase3_lock": relative(phase3_path, repo),
        "phase3_lock_sha256": sha256_file(phase3_path),
        "phase3_aggregate_manifest": relative(paths["aggregate"], repo),
        "phase3_aggregate_manifest_sha256": aggregate_sha,
        "inventory_contract": inventory, "measurement_counts": counts,
        "wave_reconciliation": wave_reconciliation,
        "executed_sources": executed_sources,
        "image_verification": {
            "path": relative(paths["images"], repo), "sha256": sha256_file(paths["images"]),
            "tools_image_id": wrapper_id,
        },
        "prewarm_verification": {
            "path": relative(paths["prewarm"], repo), "sha256": sha256_file(paths["prewarm"]),
            "extension_path": relative(extension, repo),
            "extension_sha256": prewarm_payload["extension_sha256"],
        },
        "source_fingerprints": fingerprint_rows,
        "gt_boundary": {
            "contract": phase3["scoring"]["gt_open_boundary"],
            "supplied_footprint_passed_to_roofer": False,
            "raw_gt_content_opened_by_archive": False,
            "validation_method": "score manifests and fingerprint digests only",
        },
        "large_output_policy": "per-job, Roofer, fused point, and render outputs remain in place and are bound by path+size+SHA256 only",
        "training_runs_started": 0, "new_mast3r_inference_runs": 0,
        "interpretation_or_verdict": None,
    }
    # Final fail-closed read: no cached hash or earlier semantic check may
    # authorize bytes that drifted while the archive contract was assembled.
    require(
        sha256_file(Path(__file__)) == executed_controller_sha256,
        "final_executed_archive_controller_drift",
    )
    require(
        sha256_file(repo_path(archive["phase3_script"], repo))
        == executed_phase3_sha256,
        "final_executed_phase3_controller_drift",
    )
    final_rows_by_source: list[tuple[str, Sequence[Mapping[str, str]]]] = []
    for path in inventory_paths:
        final_header, final_rows = read_csv(path)
        require(final_header == INVENTORY_FIELDS, f"final_inventory_schema:{relative(path, repo)}")
        final_rows_by_source.append((relative(path, repo), final_rows))
    final_jobs, final_inventory = validate_inventory_rows(
        final_rows_by_source, wave, phase3, archive["waves"][wave], repo=repo,
        phase2_lock=phase2_lock, hash_cache={},
    )
    require(final_jobs == jobs and final_inventory == inventory, "final_inventory_drift")
    (
        final_job_files, final_fingerprints, final_perturb_rows,
        final_cell_rows, final_bound_inputs, final_certified_partial_runs,
    ) = validate_job_bundles(
        final_jobs, score_rows, archive, phase3, aggregate, repo, {},
        phase3_module.SCORE_FIELDS, phase3_module.PERTURB_FIELDS,
        phase3_module.PERTURB_CELL_FIELDS,
    )
    require(final_job_files == job_files, "final_job_file_set_drift")
    require(final_fingerprints == fingerprint_rows, "final_job_fingerprint_drift")
    require(final_perturb_rows == authoritative_perturb_rows, "final_perturbation_drift")
    require(final_cell_rows == authoritative_cell_rows, "final_cells_drift")
    require(final_bound_inputs == job_bound_input_files, "final_job_bound_inputs_drift")
    require(final_certified_partial_runs == certified_partial_runs, "final_certified_partial_runs_drift")
    final_mapping = source_mapping(
        copied=copied, bound=bound, copy_prefix=archive["policy"]["copy_prefix"], repo=repo,
    )
    require(final_mapping == mapping, "final_source_mapping_drift")
    validate_executed_source_mapping(final_mapping, executed_sources)
    destination = repo_path(archive["archive_root"], repo) / wave
    return materialize_archive(
        destination=destination, mapping=final_mapping, payload=payload, archive=archive,
        repo=repo, forbidden_source_roots=forbidden_gt,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "archive", "verify"))
    parser.add_argument("--wave", choices=("base42", "final60"), required=True)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument(
        "--verify-bound-sources", action=argparse.BooleanOptionalAction, default=True,
        help="verify in-place SHA-only files for the verify command",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    validate_executed_controller_source()
    config_path = Path(args.config).resolve()
    archive = load_json(config_path)
    validate_paths_only(archive)
    wrapper_id = normalize_image_id(os.environ.get("S3AP_ARCHIVE_TOOLS_IMAGE_ID"))
    require(
        wrapper_id == normalize_image_id(archive["containers"]["tools_image_id"]),
        "wrapper_tools_image_attestation_mismatch",
    )
    if args.command == "preflight":
        result = validate_paths_only(archive)
        result["wave"] = args.wave
    elif args.command == "archive":
        result = archive_wave(args.wave, config_path)
    else:
        destination = repo_path(archive["archive_root"]) / args.wave
        phase3 = load_json(repo_path(archive["phase3_lock"]))
        forbidden_gt = [
            repo_path(phase3["scoring"]["footprints"]),
            repo_path(phase3["scoring"]["lod2_dir"]),
        ]
        manifest = verify_archive_directory(
            destination, args.verify_bound_sources, expected_wave=args.wave,
            archive=archive, forbidden_source_roots=forbidden_gt,
        )
        result = {
            "status": "complete", "wave": args.wave,
            "destination": relative(destination),
            "source_mapping_digest": manifest["source_mapping_digest"],
            "verify_bound_sources": args.verify_bound_sources,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

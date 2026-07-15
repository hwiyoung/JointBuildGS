#!/usr/bin/env python3
"""Stdlib tests for the fail-closed S3-A-prime tilt-18 archive."""
from __future__ import annotations

import ast
import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT = SCRIPT_DIR / "e5_c001_s3ap_phase2_archive_tilt18.py"
WRAPPER = SCRIPT_DIR / "run_e5_c001_s3ap_phase2_archive_tilt18.sh"
BASE_TEST_SCRIPT = SCRIPT_DIR / "test_e5_c001_s3ap_phase2_archive_base42.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


archive = load_module("s3ap_tilt18_archive", SCRIPT)
base_test = load_module("s3ap_base42_archive_tests", BASE_TEST_SCRIPT)

JOB_FIELDS = archive.JOB_CSV_FIELDS
STATUS_FIELDS = archive.STATUS_CSV_FIELDS


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clone(payload):
    return json.loads(json.dumps(payload))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def csv_bytes(rows: list[dict[str, str]], fields) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=fields, lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_csv(path: Path, rows: list[dict[str, str]], fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(csv_bytes(rows, fields))


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError(path)
        return list(reader.fieldnames), list(reader)


def runner_runtime() -> dict:
    return base_test.runner_runtime()


def prepare_runtime() -> dict:
    return base_test.prepare_runtime()


class Fixture:
    def __init__(self, repo: Path):
        self.repo = repo
        self.base = base_test.Fixture(repo)
        self.run_root = repo / archive.DEFAULT_RUN_ROOT
        self.jobs_path = repo / archive.DEFAULT_JOBS
        self.status_path = repo / archive.DEFAULT_STATUS
        self.output_dir = repo / archive.DEFAULT_OUTPUT_DIR
        self.manifest_path = repo / archive.DEFAULT_TILT_MANIFEST
        self.trigger_path = repo / archive.DEFAULT_TRIGGER
        self.jobs: list[dict[str, str]] = []
        self.status_rows: list[dict[str, str]] = []
        self._augment_shared_lock_and_freeze_base()
        self._build_tilt_wave()

    def rel(self, path: Path) -> str:
        return str(path.relative_to(self.repo))

    def _augment_shared_lock_and_freeze_base(self) -> None:
        lock = self.base.load_lock()
        lock["crs"] = "EPSG:25832"
        lock["training"].update({
            "tilt_perturbation_deg": archive.EXPECTED_TILT_DELTAS,
            "tilt_trigger_schema": "jointbuildgs.s3ap.return_signal.v1",
        })
        lock["outputs"].update({
            "tilt_inventory": str(archive.DEFAULT_JOBS),
            "tilt_trigger": str(archive.DEFAULT_TRIGGER),
            "tilt_prepare_manifest": str(archive.DEFAULT_TILT_MANIFEST),
            "tilt_prepare_progress": str(
                archive.DEFAULT_RUN_ROOT / "tilt_progress.csv"
            ),
        })
        lock["tilt_score_source"] = {
            "scores_csv": "docs/e5_c001_s3ap_phase3_scores.csv",
            "perturbation_csv": "docs/e5_c001_s3ap_perturbation.csv",
            "expected_nonzero_height_rows": 24,
            "require_evaluation_complete": True,
        }
        write_json(self.base.lock_path, lock)

        prewarm = self.base.load_prewarm()
        prewarm["lock_sha256"] = digest(self.base.lock_path)
        write_json(self.base.prewarm_path, prewarm)
        prepare = self.base.load_prepare()
        prepare["lock_sha256"] = digest(self.base.lock_path)
        write_json(self.base.prepare_path, prepare)
        prepare_hash = digest(self.base.prepare_path)
        for row in self.base.status_rows:
            row["prepare_manifest_sha256"] = prepare_hash
        self.base.runner_attestation["prepare_manifest_sha256"] = prepare_hash
        self.base.write_status()
        self.base.archive()

        # Additional static files are merely provenance inputs in the fixture.
        for rel in archive.STATIC_PROVENANCE:
            path = self.repo / rel
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                live = archive.REPO / rel
                if (
                    rel in {
                        archive.DEFAULT_PHASE3_ARCHIVE_CONTROLLER,
                        archive.DEFAULT_PHASE3_ARCHIVE_WRAPPER,
                        archive.DEFAULT_PHASE3_ARCHIVE_TEST,
                    }
                    and live.is_file()
                ):
                    path.write_bytes(live.read_bytes())
                else:
                    path.write_text(f"fixture {rel}\n", encoding="utf-8")
        live_archive_lock = archive.REPO / archive.DEFAULT_PHASE3_ARCHIVE_LOCK
        (self.repo / archive.DEFAULT_PHASE3_ARCHIVE_LOCK).write_bytes(
            live_archive_lock.read_bytes()
        )
        write_json(self.repo / archive.DEFAULT_PHASE3_LOCK, {
            "schema": "jointbuildgs.s3ap.phase3.lock.v1",
            "training_runs_allowed": 0,
            "new_mast3r_inference_allowed": False,
            "perturbation": {
                "trigger_rule": archive.EXPECTED_TRIGGER_RULE,
                "tilt_deltas_deg": archive.EXPECTED_TILT_DELTAS,
            },
            "outputs": {
                "manifest": "results/tum_transfer/e5_s3ap_phase3/manifest.json",
                "scores_csv": "docs/e5_c001_s3ap_phase3_scores.csv",
                "perturbation_csv": "docs/e5_c001_s3ap_perturbation.csv",
                "perturbation_cells_csv": (
                    "docs/e5_c001_s3ap_perturbation_cells.csv"
                ),
                "tilt_trigger": str(archive.DEFAULT_TRIGGER),
            },
        })

    def _build_phase3_sources(self) -> dict:
        score_path = self.repo / "docs/e5_c001_s3ap_phase3_scores.csv"
        perturb_path = self.repo / "docs/e5_c001_s3ap_perturbation.csv"
        cells_path = self.repo / "docs/e5_c001_s3ap_perturbation_cells.csv"
        score_path.parent.mkdir(parents=True, exist_ok=True)
        score_jobs, perturb_jobs = archive.phase3_job_contract(self.base.jobs)
        first_nonzero = next(
            job for job in perturb_jobs
            if float(job["height_delta_m"]) != 0.0
        )["job_id"]
        metrics: dict[str, dict] = {}
        perturb_rows: list[dict] = []
        cell_rows: list[dict] = []
        candidates: list[dict] = []
        rule = archive.EXPECTED_TRIGGER_RULE
        for index, job in enumerate(perturb_jobs):
            run_id = job["job_id"]
            delta = float(job["height_delta_m"])
            p0 = 0.1
            perturbed = p0 + delta
            post = 0.0 if run_id == first_nonzero else abs(perturbed) + 1.0
            condition = bool(delta != 0.0 and abs(post) < abs(perturbed))
            metrics[run_id] = {"p0": p0, "post": post}
            perturb_rows.append({
                "run_id": run_id,
                "building_id": f"DEBY_LOD2_{job['building_id']}",
                "arm": "a1",
                "replicate": "r1",
                "delta_m": delta,
                "score_status": "complete",
                "p0_signed_median_error_m": p0,
                "perturbed_p0_signed_median_error_m": perturbed,
                "perturbed_p0_abs_signed_median_error_m": abs(perturbed),
                "post_gs_signed_median_error_m": post,
                "post_gs_abs_signed_median_error_m": abs(post),
                "signed_error_reduction_m": abs(perturbed) - abs(post),
                "post_minus_perturbed_seed_signed_m": post - perturbed,
                "return_condition_met": condition,
                "trigger_candidate": delta != 0.0,
                "trigger_rule": rule,
            })
            cell_rows.append({
                "run_id": run_id,
                "building_id": f"DEBY_LOD2_{job['building_id']}",
                "arm": "a1",
                "replicate": "r1",
                "delta_m": delta,
                "cell_ix": 0,
                "cell_iy": 0,
                "cell_center_x": 0.25,
                "cell_center_y": 0.25,
                "region": "interior",
                "p0_base_signed_error_m": p0,
                "perturbed_p0_signed_error_m": perturbed,
                "perturbed_p0_abs_error_m": abs(perturbed),
                "post_gs_point_count": 1,
                "post_gs_signed_error_m": post,
                "post_gs_abs_error_m": abs(post),
                "return_amount_m": abs(perturbed) - abs(post),
                "return_condition_met": condition,
                "coverage_grid_m": 0.5,
                "score_status": "complete",
            })
            if delta != 0.0:
                candidates.append({
                    "run_id": run_id,
                    "building_id": f"DEBY_LOD2_{job['building_id']}",
                    "delta_m": delta,
                    "post_gs_abs_signed_median_error_m": abs(post),
                    "perturbed_p0_abs_signed_median_error_m": abs(perturbed),
                    "condition_met": condition,
                })
        score_fields = (
            "run_id", "building_id", "arm", "replicate",
            "perturbation_type", "perturbation_value", "score_status",
            "checkpoint", "height_error_signed_median_m",
            "p0_height_error_signed_median_m",
        )
        score_rows: list[dict] = []
        for job in score_jobs:
            values = metrics.get(job["job_id"], {"p0": 0.1, "post": 0.2})
            score_rows.append({
                "run_id": job["job_id"],
                "building_id": f"DEBY_LOD2_{job['building_id']}",
                "arm": job["arm"],
                "replicate": job["replicate"],
                "perturbation_type": (
                    "height" if job["job_class"] == "height" else "none"
                ),
                "perturbation_value": float(job["height_delta_m"]),
                "score_status": "complete",
                "checkpoint": job["final_checkpoint"],
                "height_error_signed_median_m": values["post"],
                "p0_height_error_signed_median_m": values["p0"],
            })
        write_csv(score_path, score_rows, score_fields)
        write_csv(perturb_path, perturb_rows, archive.PERTURB_FIELDS)
        write_csv(cells_path, cell_rows, archive.PERTURB_CELL_FIELDS)
        qualifying = [row for row in candidates if row["condition_met"]]
        trigger = {
            "schema": "jointbuildgs.s3ap.return_signal.v1",
            "created_utc": "2026-07-15T12:00:00+00:00",
            "return_signal": bool(qualifying),
            "raw_return_signal": bool(qualifying),
            "rule": rule,
            "equality_counts_as_return": False,
            "numeric_tolerance": None,
            "candidate_count": 24,
            "qualifying_count": len(qualifying),
            "candidates": candidates,
            "qualifying": qualifying,
            "expected_nonzero_height_rows": 24,
            "observed_nonzero_height_rows": 24,
            "complete_nonzero_height_rows": 24,
            "evaluation_complete": True,
            "scores_csv": self.rel(score_path),
            "perturbation_csv": self.rel(perturb_path),
            "perturbation_cells_csv": self.rel(cells_path),
            "source_score_sha256": digest(score_path),
            "source_perturbation_sha256": digest(perturb_path),
            "source_perturbation_cells_sha256": digest(cells_path),
            "tilt_deltas_deg": archive.EXPECTED_TILT_DELTAS,
        }
        write_json(self.trigger_path, trigger)
        return trigger

    def _build_phase3_base42_archive(self, trigger: dict) -> None:
        controller = archive._load_phase3_archive_controller(self.repo)
        archive_lock_path = self.repo / archive.DEFAULT_PHASE3_ARCHIVE_LOCK
        archive_lock = json.loads(
            archive_lock_path.read_text(encoding="utf-8")
        )
        phase3_lock_path = self.repo / archive.DEFAULT_PHASE3_LOCK
        phase3 = json.loads(phase3_lock_path.read_text(encoding="utf-8"))
        aggregate_path = self.repo / phase3["outputs"]["manifest"]
        write_json(aggregate_path, {
            "schema": archive_lock["phase3_aggregate_schema"],
            "status": "complete",
            "fixture": True,
        })
        image_path = (
            self.repo
            / "results/tum_transfer/e5_s3ap_phase3/"
            "docker_image_verification.json"
        )
        prewarm_path = (
            self.repo
            / "results/tum_transfer/e5_s3ap_phase3/"
            "gsplat_prewarm_verification.json"
        )
        extension_path = (
            self.repo
            / "results/tum_transfer/e5_s3ap_phase2/runtime/"
            "torch_extensions/fixture_extension.so"
        )
        figure_path = (
            self.repo / "docs/figs/e5_c001_s3ap_phase3/fixture.png"
        )
        write_json(image_path, {"schema": "fixture.image.v1"})
        write_json(prewarm_path, {"schema": "fixture.prewarm.v1"})
        extension_path.parent.mkdir(parents=True, exist_ok=True)
        extension_path.write_bytes(b"fixture-extension")
        figure_path.parent.mkdir(parents=True, exist_ok=True)
        figure_path.write_bytes(b"fixture-figure")
        core = {
            "scores": self.repo / trigger["scores_csv"],
            "perturbation": self.repo / trigger["perturbation_csv"],
            "cells": self.repo / trigger["perturbation_cells_csv"],
            "trigger": self.trigger_path,
        }
        phase3_controller_path = self.repo / archive.PHASE3_SCRIPT
        archive_controller_path = (
            self.repo / archive.DEFAULT_PHASE3_ARCHIVE_CONTROLLER
        )
        input_job = self.base.jobs[0]
        config_path = self.repo / input_job["config_path"]
        seed_path = self.repo / input_job["surface_seed_npz"]
        checkpoint_path = self.repo / input_job["final_checkpoint"]
        copied = [
            *((path, f"phase3_global_{label}")
              for label, path in core.items()),
            (phase3_lock_path, "phase3_lock"),
            (phase3_controller_path, "phase3_controller_source"),
            (archive_lock_path, "archive_lock"),
            (aggregate_path, "phase3_global_aggregate"),
            (image_path, "phase3_global_image_verification"),
            (prewarm_path, "phase3_global_prewarm_verification"),
            (figure_path, "phase3_declared_figure"),
        ]
        bound = [
            (archive_controller_path, "archive_controller_source"),
            (
                self.repo / archive.DEFAULT_PHASE3_ARCHIVE_WRAPPER,
                "archive_controller_source",
            ),
            (
                self.repo / archive.DEFAULT_PHASE3_ARCHIVE_TEST,
                "archive_controller_source",
            ),
            (config_path, "phase2_job_bound_input"),
            (seed_path, "phase2_job_bound_input"),
            (checkpoint_path, "phase2_job_bound_input"),
            (extension_path, "verified_prewarm_extension"),
        ]
        mapping = controller.source_mapping(
            copied=copied,
            bound=bound,
            copy_prefix=archive_lock["policy"]["copy_prefix"],
            repo=self.repo,
        )
        by_source = {row["source_path"]: row for row in mapping}
        reconciliation_outputs = {}
        for label, path in core.items():
            source = self.rel(path)
            row = by_source[source]
            reconciliation_outputs[label] = {
                "source_path": source,
                "archive_path": row["archive_path"],
                "size_bytes": row["size_bytes"],
                "sha256": row["sha256"],
            }
        mapping_digest = controller.canonical_digest(mapping)
        inventory_digest = "a" * 64
        aggregate_source = self.rel(aggregate_path)
        aggregate_hash = digest(aggregate_path)
        score_jobs, _ = archive.phase3_job_contract(self.base.jobs)
        run_ids = sorted(job["job_id"] for job in score_jobs)
        inventory = {
            "wave": "base42",
            "counts": {
                "total": 42,
                "base": 18,
                "height_nonzero": 24,
                "tilt": 0,
            },
            "run_ids": run_ids,
            "base_tuple_count": 18,
            "height_tuple_count": 24,
            "tilt_tuple_count": 0,
            "job_contract_digest": inventory_digest,
        }
        input_binding = {
            "schema": controller.PHASE2_INPUT_BINDING_SCHEMA,
            "random_seed": int(input_job["random_seed"]),
            "config": {
                "path": self.rel(config_path),
                "sha256": digest(config_path),
            },
            "surface_seed": {
                "path": self.rel(seed_path),
                "sha256": digest(seed_path),
            },
            "checkpoint": {
                "path": self.rel(checkpoint_path),
                "sha256": digest(checkpoint_path),
            },
        }
        input_binding_digest = controller.canonical_digest(input_binding)
        source_fingerprints = [{
            "run_id": run_id,
            "pre_readout_digest": "1" * 64,
            "score_only_digest": "2" * 64,
            "full_reuse_fingerprint": "3" * 64,
            "score_only_bundle_file_count": 1,
            "gt_content_reopened_by_archive": False,
            "phase2_input_binding": clone(input_binding),
            "phase2_input_binding_digest": input_binding_digest,
        } for run_id in run_ids]
        measurements = {
            "score_rows": 42,
            "complete_scores": 42,
            "perturbation_rows": 27,
            "nonzero_height_rows": 24,
            "perturbation_cell_rows": 27,
            "status_rows": 42,
            "return_signal": True,
            "evaluation_complete": True,
            "declared_figure_files": 1,
            "skipped_figure_records": 0,
        }
        reconciliation = {
            "schema": archive_lock["schemas"]["wave_reconciliation"],
            "wave": "base42",
            "inventory_job_contract_digest": inventory_digest,
            "phase3_aggregate_manifest": aggregate_source,
            "phase3_aggregate_manifest_sha256": aggregate_hash,
            "source_mapping_digest": mapping_digest,
            "complete_score_count": 42,
            "nonzero_height_rows": 24,
            "evaluation_complete": True,
            "return_signal": True,
            "outputs": reconciliation_outputs,
        }
        payload = {
            "wave": "base42",
            "task_date": archive_lock["task_date"],
            "crs": archive_lock["crs"],
            "archive_lock": self.rel(archive_lock_path),
            "archive_lock_sha256": digest(archive_lock_path),
            "phase3_lock": self.rel(phase3_lock_path),
            "phase3_lock_sha256": digest(phase3_lock_path),
            "phase3_aggregate_manifest": aggregate_source,
            "phase3_aggregate_manifest_sha256": aggregate_hash,
            "inventory_contract": inventory,
            "measurement_counts": measurements,
            "wave_reconciliation": reconciliation,
            "executed_sources": {
                "archive_controller": {
                    "path": self.rel(archive_controller_path),
                    "sha256": digest(archive_controller_path),
                },
                "phase3_controller": {
                    "path": self.rel(phase3_controller_path),
                    "sha256": digest(phase3_controller_path),
                },
            },
            "image_verification": {
                "path": self.rel(image_path),
                "sha256": digest(image_path),
                "tools_image_id": archive.base.TOOLS_IMAGE_ID,
            },
            "prewarm_verification": {
                "path": self.rel(prewarm_path),
                "sha256": digest(prewarm_path),
                "extension_path": self.rel(extension_path),
                "extension_sha256": digest(extension_path),
            },
            "source_fingerprints": source_fingerprints,
            "gt_boundary": {
                "contract": "score-only fixture boundary",
                "supplied_footprint_passed_to_roofer": False,
                "raw_gt_content_opened_by_archive": False,
                "validation_method": "fixture manifests only",
            },
            "large_output_policy": "fixture sha256-only payloads",
            "training_runs_started": 0,
            "new_mast3r_inference_runs": 0,
            "interpretation_or_verdict": None,
        }
        controller.materialize_archive(
            destination=self.repo / archive.DEFAULT_PHASE3_BASE42_ARCHIVE,
            mapping=mapping,
            payload=payload,
            archive=archive_lock,
            repo=self.repo,
        )

    def _build_tilt_wave(self) -> None:
        trigger = self._build_phase3_sources()
        self._build_phase3_base42_archive(trigger)

        data_hashes: dict[str, str] = {}
        base_prepare = self.base.load_prepare()
        for building in archive.base.BUILDINGS:
            data_path = self.repo / (
                "results/tum_transfer/e5_s3ap_phase2/prepared/"
                f"DEBY_LOD2_{building}/data_manifest.json"
            )
            data_hashes[building] = digest(data_path)

        pending: list[dict[str, str]] = []
        for sequence, expected in enumerate(archive.expected_job_grid(), 1):
            job_id = expected["job_id"]
            config = self.repo / expected["config_path"]
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(
                "\n".join([
                    "max_iter: 30000",
                    "surface_seed_height_delta_m: 0.0",
                    f"surface_seed_tilt_deg: {expected['tilt_deg']}",
                    "phase2_input_contract:",
                    "  gt_used: false",
                    "  lod2_used: false",
                    "  als_used: false",
                    "",
                ]),
                encoding="utf-8",
            )
            seed = self.repo / expected["surface_seed_npz"]
            if not seed.is_file():
                seed.parent.mkdir(parents=True, exist_ok=True)
                seed.write_bytes(f"tilt-seed:{expected['building_id']}".encode())
            out_dir = self.repo / expected["out_dir"]
            final = self.repo / expected["final_checkpoint"]
            final.parent.mkdir(parents=True, exist_ok=True)
            final.write_bytes(
                f"tilt-final:{job_id}:it30000:nprim{300 + sequence}".encode()
            )
            for name in (
                "effective_config.json", "view_roles.json",
                "surface_seed_audit.json",
            ):
                write_json(out_dir / name, {"job_id": job_id, "role": name})
            binding = {
                "schema": "jointbuildgs.s3ap.phase2.job_binding.v1",
                "job_id": job_id,
                "config_path": expected["config_path"],
                "config_sha256": digest(config),
                "data_root": expected["data_root"],
                "surface_seed_npz": expected["surface_seed_npz"],
                "surface_seed_sha256": digest(seed),
                "iterations": 30000,
            }
            binding_path = out_dir / "phase2_job_binding.json"
            write_json(binding_path, binding)
            log = self.run_root / "runner/logs" / f"{job_id}.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text("[done] 30000\n", encoding="utf-8")
            job = {
                "sequence": str(sequence),
                **expected,
                "config_sha256": digest(config),
                "surface_seed_sha256": digest(seed),
                "gt_used": "False",
                "lod2_used": "False",
                "als_used": "False",
                "status": "prepared",
            }
            self.jobs.append(job)
            pending.append({
                "sequence": str(sequence),
                "job_id": job_id,
                "gpu_id": str((sequence - 1) % 2),
                "status": "complete",
                "attempt": "1",
                "config_path": job["config_path"],
                "config_sha256": job["config_sha256"],
                "out_dir": job["out_dir"],
                "final_checkpoint": job["final_checkpoint"],
                "partial_checkpoints": "",
                "started_utc": "2026-07-15T12:00:00+00:00",
                "ended_utc": "2026-07-15T12:10:00+00:00",
                "elapsed_s": "600.0",
                "timeout_s": "7200",
                "returncode": "0",
                "log_path": self.rel(log),
                "prepare_manifest_sha256": "",
                "data_manifest_sha256": data_hashes[job["building_id"]],
                "surface_seed_sha256": job["surface_seed_sha256"],
                "job_binding_sha256": digest(binding_path),
                "final_checkpoint_sha256": digest(final),
                "final_checkpoint_it": "30000",
                "final_checkpoint_n_prim": str(300 + sequence),
                "message": "",
            })
        write_csv(self.jobs_path, self.jobs, JOB_FIELDS)
        manifest = {
            "schema": "jointbuildgs.s3ap.phase2.prepare_manifest.v1",
            "status": "complete",
            "created_utc": "2026-07-15T12:00:00+00:00",
            "completed_utc": "2026-07-15T12:01:00+00:00",
            "mode": "tilt",
            "git_head": "b" * 40,
            "git_branch": "fixture",
            "lock_path": str(archive.base.DEFAULT_LOCK),
            "lock_sha256": digest(self.base.lock_path),
            "runtime_attestation": prepare_runtime(),
            "gt_used": False,
            "lod2_used": False,
            "als_used": False,
            "training_started": False,
            "prepared_buildings": base_prepare["prepared_buildings"],
            "prepared_data_rewritten": False,
            "base_prepare_reference": {
                "path": self.rel(self.base.prepare_path),
                "sha256": digest(self.base.prepare_path),
                "inventory": self.rel(self.base.jobs_path),
                "inventory_sha256": digest(self.base.jobs_path),
            },
            "tilt_trigger": {
                "path": self.rel(self.trigger_path),
                "sha256": digest(self.trigger_path),
                "payload": trigger,
            },
            "inventory": self.rel(self.jobs_path),
            "inventory_sha256": digest(self.jobs_path),
            "job_count": 18,
            "jobs": [{
                key: row[key]
                for key in (
                    "job_id", "config_path", "config_sha256",
                    "final_checkpoint",
                )
            } for row in self.jobs],
        }
        write_json(self.manifest_path, manifest)
        manifest_hash = digest(self.manifest_path)
        for row in pending:
            row["prepare_manifest_sha256"] = manifest_hash
        self.status_rows = pending
        self.runner_attestation = {
            "inventory": self.rel(self.jobs_path),
            "jobs": 18,
            "status_counts": {"skipped_final_exists": 18},
            "gpu_ids": [0, 1],
            "timeout_s": 7200,
            "runtime_attestation": runner_runtime(),
            "prepare_manifest_sha256": manifest_hash,
            "training_started": False,
        }
        self.write_status()

    def write_status(self) -> None:
        write_csv(self.status_path, self.status_rows, STATUS_FIELDS)

    def load_trigger(self) -> dict:
        return json.loads(self.trigger_path.read_text(encoding="utf-8"))

    def load_manifest(self) -> dict:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def refresh_trigger_lineage(self, trigger: dict | None = None) -> None:
        trigger = self.load_trigger() if trigger is None else trigger
        sources = (
            ("scores_csv", "source_score_sha256"),
            ("perturbation_csv", "source_perturbation_sha256"),
            ("perturbation_cells_csv", "source_perturbation_cells_sha256"),
        )
        for path_field, hash_field in sources:
            trigger[hash_field] = digest(self.repo / trigger[path_field])
        write_json(self.trigger_path, trigger)
        manifest = self.load_manifest()
        manifest["tilt_trigger"] = {
            "path": self.rel(self.trigger_path),
            "sha256": digest(self.trigger_path),
            "payload": trigger,
        }
        write_json(self.manifest_path, manifest)
        manifest_hash = digest(self.manifest_path)
        for row in self.status_rows:
            row["prepare_manifest_sha256"] = manifest_hash
        self.runner_attestation["prepare_manifest_sha256"] = manifest_hash
        self.write_status()

    def archive(
        self,
        *,
        dry_run: bool = False,
        before_final_revalidation_hook=None,
    ):
        return archive.archive_tilt18(
            repo=self.repo,
            jobs_path=self.jobs_path,
            status_path=self.status_path,
            output_dir=self.output_dir,
            runner_dry_run_attestation=self.runner_attestation,
            tools_image_id=archive.base.TOOLS_IMAGE_ID,
            dry_run=dry_run,
            _before_final_revalidation_hook=(
                before_final_revalidation_hook
            ),
        )


class Tilt18ArchiveTest(unittest.TestCase):
    def assert_no_tilt_outputs(self, fixture: Fixture) -> None:
        for name in (
            archive.SNAPSHOT_NAME,
            archive.ARTIFACTS_NAME,
            archive.COMPLETION_NAME,
        ):
            self.assertFalse((fixture.output_dir / name).exists())

    def test_success_writes_only_three_files_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            before = {
                path.relative_to(fixture.repo)
                for path in fixture.repo.rglob("*") if path.is_file()
            }
            dry = fixture.archive(dry_run=True)
            self.assertTrue(dry["dry_run"])
            self.assert_no_tilt_outputs(fixture)
            result = fixture.archive()
            self.assertEqual(result["job_count"], 18)
            self.assertEqual(
                result["runner_dry_run_status_counts"],
                {"skipped_final_exists": 18},
            )
            self.assertFalse(result["gt_used"])
            self.assertFalse(result["raw_logs_copied"])
            self.assertFalse(result["raw_checkpoints_copied"])
            self.assertFalse(result["raw_bindings_copied"])
            self.assertFalse(result["raw_configs_copied"])
            self.assertEqual(
                result["docker_image_id"], archive.base.TRAINING_IMAGE_ID
            )
            self.assertEqual(
                result["archive_tools_image_id"], archive.base.TOOLS_IMAGE_ID
            )
            self.assertEqual(
                result["training_launcher_sha256"],
                digest(fixture.repo / archive.base.HOST_LAUNCHER),
            )
            self.assertEqual(
                result["archive_launcher_sha256"],
                digest(fixture.repo / archive.ARCHIVE_LAUNCHER),
            )
            self.assertEqual(
                result["base42_completion_sha256"],
                digest(fixture.repo / archive.DEFAULT_BASE_COMPLETION),
            )
            self.assertEqual(
                result["phase3_base42_archive_manifest_sha256"],
                digest(fixture.repo / archive.DEFAULT_PHASE3_BASE42_MANIFEST),
            )
            self.assertEqual(
                result["phase3_base42_archive_completion_sha256"],
                digest(
                    fixture.repo / archive.DEFAULT_PHASE3_BASE42_COMPLETION
                ),
            )
            self.assertEqual(
                {
                    str(archive.DEFAULT_PHASE3_ARCHIVE_LOCK): result[
                        "phase3_archive_lock_sha256"
                    ],
                    str(archive.DEFAULT_PHASE3_ARCHIVE_CONTROLLER): result[
                        "phase3_archive_controller_sha256"
                    ],
                    str(archive.DEFAULT_PHASE3_ARCHIVE_WRAPPER): result[
                        "phase3_archive_wrapper_sha256"
                    ],
                    str(archive.DEFAULT_PHASE3_ARCHIVE_TEST): result[
                        "phase3_archive_test_sha256"
                    ],
                },
                archive.PHASE3_ARCHIVE_STATIC_SHA256,
            )
            after = {
                path.relative_to(fixture.repo)
                for path in fixture.repo.rglob("*") if path.is_file()
            }
            expected = {
                (fixture.output_dir / name).relative_to(fixture.repo)
                for name in (
                    archive.SNAPSHOT_NAME,
                    archive.ARTIFACTS_NAME,
                    archive.COMPLETION_NAME,
                )
            }
            self.assertEqual(after - before, expected)
            lines = (
                fixture.output_dir / archive.ARTIFACTS_NAME
            ).read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                sum("/ckpt/final.pt" in line for line in lines), 18
            )
            self.assertEqual(
                sum("/runner/logs/" in line and "tilt_" in line for line in lines),
                18,
            )
            second = fixture.archive()
            self.assertEqual(
                second["write_results"][archive.SNAPSHOT_NAME],
                "existing_identical",
            )

    def test_jobs_and_status_headers_are_exact(self):
        self.assertEqual(JOB_FIELDS, archive.base.JOB_CSV_FIELDS)
        self.assertEqual(STATUS_FIELDS, archive.base.STATUS_CSV_FIELDS)
        for role in ("jobs", "status"):
            for drift in ("duplicate", "extra", "missing", "order"):
                with self.subTest(role=role, drift=drift), tempfile.TemporaryDirectory() as tmp:
                    fixture = Fixture(Path(tmp))
                    path = fixture.jobs_path if role == "jobs" else fixture.status_path
                    lines = path.read_text(encoding="utf-8").splitlines()
                    fields = lines[0].split(",")
                    if drift == "duplicate":
                        fields[-1] = fields[0]
                    elif drift == "extra":
                        fields.append("unexpected")
                    elif drift == "missing":
                        fields.pop()
                    else:
                        fields[0], fields[1] = fields[1], fields[0]
                    lines[0] = ",".join(fields)
                    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    with self.assertRaisesRegex(
                        archive.ArchiveError, "header/order drift"
                    ):
                        fixture.archive()
                    self.assert_no_tilt_outputs(fixture)

    def test_exact_tilt_grid_and_no_gt_contract_fail_closed(self):
        cases = (
            (0, "building_id", "8568392"),
            (0, "arm", "a2"),
            (0, "replicate", "r2"),
            (0, "random_seed", "2002"),
            (0, "height_delta_m", "0.5"),
            (0, "tilt_deg", "-5.0"),
            (0, "job_id", "gs_e5_C001_s3ap_b4907199_a1_tilt_p06_r1"),
            (6, "sequence", "8"),
            (0, "gt_used", "True"),
            (0, "lod2_used", "True"),
            (0, "als_used", "True"),
        )
        for index, field, value in cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                fixture.jobs[index][field] = value
                write_csv(fixture.jobs_path, fixture.jobs, JOB_FIELDS)
                with self.assertRaises(archive.ArchiveError):
                    fixture.archive()
                self.assert_no_tilt_outputs(fixture)

    def test_trigger_and_source_score_hashes_are_mandatory(self):
        cases = {
            "return_signal": lambda x: x.__setitem__("return_signal", False),
            "raw_signal": lambda x: x.__setitem__("raw_return_signal", False),
            "evaluation": lambda x: x.__setitem__("evaluation_complete", False),
            "observed": lambda x: x.__setitem__("observed_nonzero_height_rows", 23),
            "grid_order": lambda x: x.__setitem__(
                "tilt_deltas_deg", [-5.0, 5.0, 10.0, -10.0, 20.0, -20.0]
            ),
            "score_hash": lambda x: x.__setitem__("source_score_sha256", "0" * 64),
            "qualifying": lambda x: x.__setitem__("qualifying_count", 0),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                trigger = fixture.load_trigger()
                mutate(trigger)
                write_json(fixture.trigger_path, trigger)
                manifest = fixture.load_manifest()
                manifest["tilt_trigger"] = {
                    "path": fixture.rel(fixture.trigger_path),
                    "sha256": digest(fixture.trigger_path),
                    "payload": trigger,
                }
                write_json(fixture.manifest_path, manifest)
                with self.assertRaises(archive.ArchiveError):
                    fixture.archive()
                self.assert_no_tilt_outputs(fixture)
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            score = fixture.repo / "docs/e5_c001_s3ap_phase3_scores.csv"
            score.write_bytes(score.read_bytes() + b"tamper\n")
            with self.assertRaisesRegex(archive.ArchiveError, "hash mismatch"):
                fixture.archive()

    def test_self_consistent_perturbation_csv_attacks_fail_reconstruction(self):
        cases = (
            "header_order", "header_duplicate", "header_missing",
            "drop_row", "row_order", "delta_grid", "nonfinite_post",
            "nonfinite_perturbed", "condition_bool", "candidate_bool",
            "algebra_abs", "p0_algebra", "perturbed_algebra",
            "reduction_algebra", "post_minus_algebra", "score_status",
            "row_trigger_rule", "zero_row_algebra",
        )
        for name in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                path = fixture.repo / "docs/e5_c001_s3ap_perturbation.csv"
                fields, rows = read_csv(path)
                nonzero = next(
                    index for index, row in enumerate(rows)
                    if float(row["delta_m"]) != 0.0
                )
                if name == "header_order":
                    fields[0], fields[1] = fields[1], fields[0]
                elif name == "header_duplicate":
                    fields[-1] = fields[0]
                    rows = [
                        {key: value for key, value in row.items() if key in fields}
                        for row in rows
                    ]
                elif name == "header_missing":
                    fields.remove("trigger_rule")
                    rows = [
                        {key: value for key, value in row.items() if key in fields}
                        for row in rows
                    ]
                elif name == "drop_row":
                    rows.pop(nonzero)
                elif name == "row_order":
                    rows[nonzero], rows[nonzero + 1] = (
                        rows[nonzero + 1], rows[nonzero]
                    )
                elif name == "delta_grid":
                    rows[nonzero]["delta_m"] = "-3.5"
                elif name == "nonfinite_post":
                    rows[nonzero]["post_gs_signed_median_error_m"] = "nan"
                elif name == "nonfinite_perturbed":
                    rows[nonzero][
                        "perturbed_p0_signed_median_error_m"
                    ] = "inf"
                elif name == "condition_bool":
                    rows[nonzero]["return_condition_met"] = "False"
                elif name == "candidate_bool":
                    rows[nonzero]["trigger_candidate"] = "False"
                elif name == "algebra_abs":
                    rows[nonzero][
                        "post_gs_abs_signed_median_error_m"
                    ] = "999.0"
                elif name == "p0_algebra":
                    rows[nonzero]["p0_signed_median_error_m"] = "9.0"
                elif name == "perturbed_algebra":
                    rows[nonzero][
                        "perturbed_p0_signed_median_error_m"
                    ] = "9.0"
                elif name == "reduction_algebra":
                    rows[nonzero]["signed_error_reduction_m"] = "9.0"
                elif name == "post_minus_algebra":
                    rows[nonzero][
                        "post_minus_perturbed_seed_signed_m"
                    ] = "9.0"
                elif name == "score_status":
                    rows[nonzero]["score_status"] = "partial"
                elif name == "row_trigger_rule":
                    rows[nonzero]["trigger_rule"] = "forged rule"
                elif name == "zero_row_algebra":
                    zero = next(
                        index for index, row in enumerate(rows)
                        if float(row["delta_m"]) == 0.0
                    )
                    rows[zero][
                        "perturbed_p0_signed_median_error_m"
                    ] = "999.0"
                write_csv(path, rows, fields)
                fixture.refresh_trigger_lineage()
                with self.assertRaises(archive.ArchiveError):
                    fixture.archive()
                self.assert_no_tilt_outputs(fixture)

    def test_trigger_candidate_schema_order_values_and_qualifying_are_exact(self):
        cases = (
            "extra_candidate_key", "candidate_order", "candidate_value",
            "qualifying_false_row", "qualifying_order", "signal_formula",
        )
        for name in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                trigger = fixture.load_trigger()
                if name == "extra_candidate_key":
                    trigger["candidates"][0]["extra"] = "attack"
                elif name == "candidate_order":
                    trigger["candidates"][0], trigger["candidates"][1] = (
                        trigger["candidates"][1], trigger["candidates"][0]
                    )
                elif name == "candidate_value":
                    trigger["candidates"][0][
                        "post_gs_abs_signed_median_error_m"
                    ] = 123.0
                elif name == "qualifying_false_row":
                    trigger["qualifying"] = [trigger["candidates"][1]]
                elif name == "qualifying_order":
                    # First make a second candidate genuinely qualifying only
                    # in the trigger; source reconstruction must reject it.
                    forged = clone(trigger["candidates"][1])
                    forged["condition_met"] = True
                    trigger["qualifying"] = [forged, trigger["qualifying"][0]]
                    trigger["qualifying_count"] = 2
                elif name == "signal_formula":
                    trigger["return_signal"] = False
                fixture.refresh_trigger_lineage(trigger)
                with self.assertRaises(archive.ArchiveError):
                    fixture.archive()
                self.assert_no_tilt_outputs(fixture)

    def test_self_consistent_source_score_attacks_fail_linkage(self):
        cases = (
            "missing_header", "drop_row", "row_order", "run_id",
            "building", "post_metric", "p0_metric",
        )
        for name in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                path = fixture.repo / "docs/e5_c001_s3ap_phase3_scores.csv"
                fields, rows = read_csv(path)
                height = next(
                    index for index, row in enumerate(rows)
                    if row["perturbation_type"] == "height"
                )
                if name == "missing_header":
                    fields.remove("p0_height_error_signed_median_m")
                    rows = [
                        {key: value for key, value in row.items() if key in fields}
                        for row in rows
                    ]
                elif name == "drop_row":
                    rows.pop(height)
                elif name == "row_order":
                    rows[height], rows[height + 1] = rows[height + 1], rows[height]
                elif name == "run_id":
                    rows[height]["run_id"] = "forged-height-run"
                elif name == "building":
                    rows[height]["building_id"] = "DEBY_LOD2_8568392"
                elif name == "post_metric":
                    rows[height]["height_error_signed_median_m"] = "55.0"
                elif name == "p0_metric":
                    rows[height]["p0_height_error_signed_median_m"] = "55.0"
                write_csv(path, rows, fields)
                fixture.refresh_trigger_lineage()
                with self.assertRaises(archive.ArchiveError):
                    fixture.archive()
                self.assert_no_tilt_outputs(fixture)

    def test_self_consistent_unlinked_score_forgery_hits_external_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            path = fixture.repo / "docs/e5_c001_s3ap_phase3_scores.csv"
            fields, rows = read_csv(path)
            row = next(
                item for item in rows
                if item["arm"] == "a0"
                and item["perturbation_type"] == "none"
            )
            row["height_error_signed_median_m"] = "123.0"
            row["p0_height_error_signed_median_m"] = "122.0"
            write_csv(path, rows, fields)
            fixture.refresh_trigger_lineage()
            with self.assertRaisesRegex(
                archive.ArchiveError, "base42|archive|hash"
            ):
                fixture.archive()
            self.assert_no_tilt_outputs(fixture)

    def test_self_consistent_perturbation_cell_attacks_fail_linkage(self):
        cases = (
            "missing_header", "missing_run", "unexpected_run", "delta",
            "duplicate_cell", "row_order", "grid",
        )
        for name in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                path = fixture.repo / "docs/e5_c001_s3ap_perturbation_cells.csv"
                fields, rows = read_csv(path)
                nonzero = next(
                    index for index, row in enumerate(rows)
                    if float(row["delta_m"]) != 0.0
                )
                if name == "missing_header":
                    fields.remove("coverage_grid_m")
                    rows = [
                        {key: value for key, value in row.items() if key in fields}
                        for row in rows
                    ]
                elif name == "missing_run":
                    run_id = rows[nonzero]["run_id"]
                    rows = [row for row in rows if row["run_id"] != run_id]
                elif name == "unexpected_run":
                    rows[nonzero]["run_id"] = "forged-height-run"
                elif name == "delta":
                    rows[nonzero]["delta_m"] = "99.0"
                elif name == "duplicate_cell":
                    rows.insert(nonzero + 1, clone(rows[nonzero]))
                elif name == "row_order":
                    rows[nonzero], rows[nonzero + 1] = (
                        rows[nonzero + 1], rows[nonzero]
                    )
                elif name == "grid":
                    rows[nonzero]["coverage_grid_m"] = "1.0"
                write_csv(path, rows, fields)
                fixture.refresh_trigger_lineage()
                with self.assertRaises(archive.ArchiveError):
                    fixture.archive()
                self.assert_no_tilt_outputs(fixture)

    def test_every_cell_numeric_status_and_grid_field_is_recomputed(self):
        cases = (
            "p0", "perturbed", "perturbed_abs", "count_negative",
            "count_fractional", "post", "post_abs", "return_amount",
            "return_condition", "region_enum", "center_x", "center_y",
            "ix_fractional", "grid", "score_status", "zero_count_fields",
            "zero_count_return",
        )
        for name in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                perturb_path = (
                    fixture.repo / "docs/e5_c001_s3ap_perturbation.csv"
                )
                _, perturb_rows = read_csv(perturb_path)
                perturb_by_id = {
                    row["run_id"]: {
                        "building_id": row["building_id"].removeprefix(
                            "DEBY_LOD2_"
                        ),
                        "delta_m": float(row["delta_m"]),
                    }
                    for row in perturb_rows
                }
                path = (
                    fixture.repo / "docs/e5_c001_s3ap_perturbation_cells.csv"
                )
                fields, rows = read_csv(path)
                index = next(
                    i for i, row in enumerate(rows)
                    if float(row["delta_m"]) != 0.0
                    and row["return_condition_met"] == "True"
                )
                row = rows[index]
                if name == "p0":
                    row["p0_base_signed_error_m"] = "3.0"
                elif name == "perturbed":
                    row["perturbed_p0_signed_error_m"] = "3.0"
                elif name == "perturbed_abs":
                    row["perturbed_p0_abs_error_m"] = "3.0"
                elif name == "count_negative":
                    row["post_gs_point_count"] = "-1"
                elif name == "count_fractional":
                    row["post_gs_point_count"] = "1.5"
                elif name == "post":
                    row["post_gs_signed_error_m"] = "3.0"
                elif name == "post_abs":
                    row["post_gs_abs_error_m"] = "3.0"
                elif name == "return_amount":
                    row["return_amount_m"] = "3.0"
                elif name == "return_condition":
                    row["return_condition_met"] = "False"
                elif name == "region_enum":
                    row["region"] = "roof"
                elif name == "center_x":
                    row["cell_center_x"] = "0.75"
                elif name == "center_y":
                    row["cell_center_y"] = "0.75"
                elif name == "ix_fractional":
                    row["cell_ix"] = "0.5"
                elif name == "grid":
                    row["coverage_grid_m"] = "1.0"
                elif name == "score_status":
                    row["score_status"] = "partial"
                elif name == "zero_count_fields":
                    row["post_gs_point_count"] = "0"
                elif name == "zero_count_return":
                    row["post_gs_point_count"] = "0"
                    row["post_gs_signed_error_m"] = ""
                    row["post_gs_abs_error_m"] = ""
                    row["return_amount_m"] = ""
                    row["return_condition_met"] = "True"
                write_csv(path, rows, fields)
                with self.assertRaises(archive.ArchiveError):
                    archive.validate_cell_source(path, perturb_by_id)

    def test_valid_but_forged_cell_values_are_rejected_by_external_root(self):
        cases = ("region", "self_consistent_metrics")
        for name in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                path = (
                    fixture.repo / "docs/e5_c001_s3ap_perturbation_cells.csv"
                )
                fields, rows = read_csv(path)
                row = next(
                    item for item in rows
                    if float(item["delta_m"]) != 0.0
                )
                if name == "region":
                    row["region"] = (
                        "edge" if row["region"] == "interior" else "interior"
                    )
                else:
                    p0 = 0.2
                    delta = float(row["delta_m"])
                    perturbed = p0 + delta
                    post = 0.1
                    row.update({
                        "p0_base_signed_error_m": str(p0),
                        "perturbed_p0_signed_error_m": str(perturbed),
                        "perturbed_p0_abs_error_m": str(abs(perturbed)),
                        "post_gs_signed_error_m": str(post),
                        "post_gs_abs_error_m": str(abs(post)),
                        "return_amount_m": str(
                            abs(perturbed) - abs(post)
                        ),
                        "return_condition_met": str(
                            abs(post) < abs(perturbed)
                        ),
                    })
                write_csv(path, rows, fields)
                fixture.refresh_trigger_lineage()
                with self.assertRaisesRegex(
                    archive.ArchiveError,
                    "base42|archive|hash",
                ):
                    fixture.archive()
                self.assert_no_tilt_outputs(fixture)

    def test_trigger_rule_cannot_be_forged_self_consistently(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            forged_rule = "forged but internally consistent return rule"
            phase3_path = fixture.repo / archive.DEFAULT_PHASE3_LOCK
            phase3 = json.loads(phase3_path.read_text(encoding="utf-8"))
            phase3["perturbation"]["trigger_rule"] = forged_rule
            write_json(phase3_path, phase3)
            perturb_path = (
                fixture.repo / "docs/e5_c001_s3ap_perturbation.csv"
            )
            fields, rows = read_csv(perturb_path)
            for row in rows:
                row["trigger_rule"] = forged_rule
            write_csv(perturb_path, rows, fields)
            trigger = fixture.load_trigger()
            trigger["rule"] = forged_rule
            fixture.refresh_trigger_lineage(trigger)
            with self.assertRaisesRegex(
                archive.ArchiveError, "immutable trigger-rule"
            ):
                fixture.archive()
            self.assert_no_tilt_outputs(fixture)

    def test_phase3_base42_external_archive_is_mandatory_and_immutable(self):
        cases = ("completion", "manifest", "archived_score")
        for name in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                root = fixture.repo / archive.DEFAULT_PHASE3_BASE42_ARCHIVE
                if name == "completion":
                    (root / "COMPLETED.json").unlink()
                elif name == "manifest":
                    path = root / "archive_manifest.json"
                    path.write_bytes(path.read_bytes() + b" ")
                else:
                    archived = root / "snapshot" / (
                        "docs/e5_c001_s3ap_phase3_scores.csv"
                    )
                    archived.write_bytes(archived.read_bytes() + b"tamper")
                with self.assertRaises(archive.ArchiveError):
                    fixture.archive()
                self.assert_no_tilt_outputs(fixture)

    def test_phase3_archive_old_or_extra_payload_schema_is_rejected(self):
        for name in ("old", "extra"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                controller = archive._load_phase3_archive_controller(
                    fixture.repo
                )
                root = fixture.repo / archive.DEFAULT_PHASE3_BASE42_ARCHIVE
                manifest_path = root / "archive_manifest.json"
                completion_path = root / "COMPLETED.json"
                manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
                if name == "old":
                    del manifest["executed_sources"]
                else:
                    manifest["rogue_payload_field"] = "forged"
                payload = controller.archive_payload(manifest)
                manifest["archive_payload_digest"] = (
                    controller.canonical_digest(payload)
                )
                write_json(manifest_path, manifest)
                completion = json.loads(
                    completion_path.read_text(encoding="utf-8")
                )
                completion["archive_manifest_sha256"] = digest(manifest_path)
                completion["archive_payload_digest"] = manifest[
                    "archive_payload_digest"
                ]
                write_json(completion_path, completion)
                with self.assertRaisesRegex(
                    archive.ArchiveError, "payload_fields"
                ):
                    fixture.archive()
                self.assert_no_tilt_outputs(fixture)

    def test_final_phase3_archive_sources_are_statically_pinned(self):
        for source_text in archive.PHASE3_ARCHIVE_STATIC_SHA256:
            with (
                self.subTest(source=source_text),
                tempfile.TemporaryDirectory() as tmp,
            ):
                fixture = Fixture(Path(tmp))
                path = fixture.repo / source_text
                path.write_bytes(path.read_bytes() + b"\n")
                with self.assertRaisesRegex(
                    archive.ArchiveError, "hash mismatch"
                ):
                    fixture.archive()
                self.assert_no_tilt_outputs(fixture)

    def test_final_revalidation_closes_collection_manifest_toctou(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            score = fixture.repo / "docs/e5_c001_s3ap_phase3_scores.csv"

            def mutate_after_collection() -> None:
                score.write_bytes(score.read_bytes() + b"toctou")

            with self.assertRaisesRegex(
                archive.ArchiveError, "final artifact drift"
            ):
                fixture.archive(
                    before_final_revalidation_hook=mutate_after_collection
                )
            self.assert_no_tilt_outputs(fixture)

    def test_base42_completion_and_snapshot_are_required_and_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            completion = fixture.repo / archive.DEFAULT_BASE_COMPLETION
            completion.unlink()
            with self.assertRaisesRegex(archive.ArchiveError, "missing"):
                fixture.archive()
            self.assert_no_tilt_outputs(fixture)
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            snapshot = fixture.repo / archive.DEFAULT_BASE_SNAPSHOT
            snapshot.write_bytes(snapshot.read_bytes() + b"tamper\n")
            with self.assertRaisesRegex(archive.ArchiveError, "hash drift"):
                fixture.archive()
            self.assert_no_tilt_outputs(fixture)
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            completion = fixture.repo / archive.DEFAULT_BASE_COMPLETION
            payload = json.loads(completion.read_text(encoding="utf-8"))
            payload["raw_logs_copied"] = True
            write_json(completion, payload)
            with self.assertRaisesRegex(archive.ArchiveError, "base-42 completion"):
                fixture.archive()

    def test_valid_later_prewarm_regeneration_does_not_break_base_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            prewarm_path = fixture.base.prewarm_path
            old_hash = json.loads(
                (fixture.repo / archive.DEFAULT_BASE_COMPLETION).read_text(
                    encoding="utf-8"
                )
            )["prewarm_manifest_sha256"]
            payload = fixture.base.load_prewarm()
            payload["completed_utc"] = "2026-07-15T23:00:00+00:00"
            payload["elapsed_s"] = 0.123
            payload["git_head"] = "c" * 40
            write_json(prewarm_path, payload)
            self.assertNotEqual(digest(prewarm_path), old_hash)
            result = fixture.archive()
            self.assertEqual(
                result["prewarm_manifest_sha256"], digest(prewarm_path)
            )
            self.assertEqual(
                result["base42_completion_sha256"],
                digest(fixture.repo / archive.DEFAULT_BASE_COMPLETION),
            )

    def test_status_final_binding_config_seed_data_and_log_hashes_are_bound(self):
        status_cases = {
            "failed": ("status", "failed"),
            "returncode": ("returncode", "9"),
            "iteration": ("final_checkpoint_it", "29999"),
            "primitive": ("final_checkpoint_n_prim", "0"),
            "hash": ("final_checkpoint_sha256", "A" * 64),
            "gpu": ("gpu_id", "2"),
        }
        for name, (field, value) in status_cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                fixture.status_rows[0][field] = value
                fixture.write_status()
                with self.assertRaises(archive.ArchiveError):
                    fixture.archive()
                self.assert_no_tilt_outputs(fixture)
        artifact_suffixes = (
            "final_checkpoint", "config_path", "surface_seed_npz",
        )
        for field in artifact_suffixes:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                path = fixture.repo / fixture.jobs[0][field]
                path.write_bytes(path.read_bytes() + b"tamper")
                with self.assertRaisesRegex(archive.ArchiveError, "hash mismatch"):
                    fixture.archive()
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            log = fixture.run_root / "runner/logs" / f"{fixture.jobs[0]['job_id']}.log"
            log.unlink()
            with self.assertRaisesRegex(archive.ArchiveError, "missing artifact"):
                fixture.archive()

    def test_runner_dry_run_is_exact_skipped_final_exists_18(self):
        cases = {
            "inventory": lambda x: x.__setitem__("inventory", "drift.csv"),
            "jobs": lambda x: x.__setitem__("jobs", 17),
            "status": lambda x: x.__setitem__(
                "status_counts", {"skipped_final_exists": 17, "pending": 1}
            ),
            "manifest": lambda x: x.__setitem__("prepare_manifest_sha256", "0" * 64),
            "image": lambda x: x["runtime_attestation"].__setitem__(
                "docker_image_id", "sha256:" + "0" * 64
            ),
            "started": lambda x: x.__setitem__("training_started", True),
            "extra": lambda x: x.__setitem__("extra", False),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                payload = clone(fixture.runner_attestation)
                mutate(payload)
                with self.assertRaises(archive.ArchiveError):
                    archive.validate_runner_dry_run_attestation(
                        payload,
                        repo=fixture.repo,
                        jobs_path=fixture.jobs_path,
                        tilt_manifest_sha256=digest(fixture.manifest_path),
                        lock=fixture.base.load_lock(),
                    )

    def test_preexisting_immutable_outputs_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            snapshot = fixture.output_dir / archive.SNAPSHOT_NAME
            snapshot.write_bytes(b"foreign\n")
            with self.assertRaisesRegex(archive.ArchiveError, "already exists"):
                fixture.archive()
            self.assertEqual(snapshot.read_bytes(), b"foreign\n")
            self.assertFalse((fixture.output_dir / archive.ARTIFACTS_NAME).exists())

    def test_completion_tamper_is_fail_closed(self):
        cases = {
            "raw_logs": lambda x: x.__setitem__("raw_logs_copied", True),
            "raw_bindings": lambda x: x.__setitem__("raw_bindings_copied", True),
            "base_hash": lambda x: x.__setitem__("base42_completion_sha256", "0" * 64),
            "score_hash": lambda x: x.__setitem__("source_score_sha256", "0" * 64),
            "runner": lambda x: x["runner_dry_run_attestation"].__setitem__("jobs", 17),
            "extra": lambda x: x.__setitem__("unexpected", False),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                fixture.archive()
                path = fixture.output_dir / archive.COMPLETION_NAME
                payload = json.loads(path.read_text(encoding="utf-8"))
                mutate(payload)
                write_json(path, payload)
                tampered = path.read_bytes()
                with self.assertRaisesRegex(
                    archive.ArchiveError, "completion_tilt18"
                ):
                    fixture.archive()
                self.assertEqual(path.read_bytes(), tampered)

    def test_canonical_paths_and_tools_image_are_mandatory(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            alternate = fixture.run_root / "other_tilt.csv"
            alternate.write_bytes(fixture.jobs_path.read_bytes())
            with self.assertRaisesRegex(archive.ArchiveError, "canonical"):
                archive.archive_tilt18(
                    repo=fixture.repo,
                    jobs_path=alternate,
                    status_path=fixture.status_path,
                    output_dir=fixture.output_dir,
                    runner_dry_run_attestation=fixture.runner_attestation,
                    tools_image_id=archive.base.TOOLS_IMAGE_ID,
                )
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            with self.assertRaisesRegex(archive.ArchiveError, "tools image ID drift"):
                archive.archive_tilt18(
                    repo=fixture.repo,
                    jobs_path=fixture.jobs_path,
                    status_path=fixture.status_path,
                    output_dir=fixture.output_dir,
                    runner_dry_run_attestation=fixture.runner_attestation,
                    tools_image_id="sha256:" + "0" * 64,
                )

    def test_host_wrapper_is_pinned_and_uses_in_memory_tilt_attestation(self):
        subprocess.run(
            ["bash", "-n", str(WRAPPER)], check=True,
            capture_output=True, text=True,
        )
        launcher = WRAPPER.read_text(encoding="utf-8")
        self.assertIn(
            'run --inventory "${TILT_INVENTORY}" --dry-run', launcher
        )
        self.assertIn(
            'RUNNER_DRY_RUN_JSON="${RUNNER_DRY_RUN_OUTPUT##*$\'\\n\'}"',
            launcher,
        )
        self.assertIn(
            'RUNNER_DRY_RUN_PREFIX="${RUNNER_DRY_RUN_OUTPUT%$\'\\n\'*}"',
            launcher,
        )
        self.assertIn("ambiguous JSON-like stdout", launcher)
        self.assertIn(
            '--runner-dry-run-attestation-json "${RUNNER_DRY_RUN_JSON}"',
            launcher,
        )
        self.assertIn(archive.base.TOOLS_IMAGE_ID, launcher)
        self.assertIn('docker image inspect --format \'{{.Id}}\'', launcher)
        self.assertIn('--user "$(id -u):$(id -g)"', launcher)
        self.assertNotIn("mktemp", launcher)
        self.assertNotIn("tee ", launcher)

    def test_live_static_contract_is_read_only_and_current(self):
        before = {
            path: path.stat().st_mtime_ns
            for path in archive.STATIC_PROVENANCE
            if path.is_file()
        }
        archive.validate_live_static_contract(archive.REPO)
        after = {path: path.stat().st_mtime_ns for path in before}
        self.assertEqual(before, after)

    def test_exact_perturb_headers_match_current_phase3_writer(self):
        source = archive.REPO / archive.PHASE3_SCRIPT
        tree = ast.parse(source.read_text(encoding="utf-8"))
        values = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id in {"PERTURB_FIELDS", "PERTURB_CELL_FIELDS"}
                ):
                    values[target.id] = tuple(ast.literal_eval(node.value))
        self.assertEqual(values["PERTURB_FIELDS"], archive.PERTURB_FIELDS)
        self.assertEqual(
            values["PERTURB_CELL_FIELDS"], archive.PERTURB_CELL_FIELDS
        )


if __name__ == "__main__":
    unittest.main()

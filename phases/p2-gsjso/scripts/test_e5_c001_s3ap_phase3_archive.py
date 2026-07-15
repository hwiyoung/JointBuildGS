#!/usr/bin/env python3
"""Fixture-only adversarial tests for the immutable S3-A-prime Phase-3 archive."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("e5_c001_s3ap_phase3_archive.py")
SPEC = importlib.util.spec_from_file_location("s3ap_phase3_archive_tested", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def bundle(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    files = sorted([dict(row) for row in rows], key=lambda row: str(row["path"]))
    return {
        "file_count": len(files), "files": files,
        "digest": MODULE.canonical_digest({"files": files}),
    }


def trigger_from_rows(rows: Sequence[Mapping[str, Any]], rule: str) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        delta = float(row["delta_m"])
        post = float(row["post_gs_signed_median_error_m"])
        seed = float(row["perturbed_p0_signed_median_error_m"])
        eligible = bool(
            str(row["arm"]).lower() == "a1" and str(row["replicate"]).lower() == "r1"
            and delta != 0.0 and str(row["score_status"]) == "complete"
        )
        if eligible:
            candidates.append({
                "run_id": str(row["run_id"]), "building_id": str(row["building_id"]),
                "delta_m": delta, "post_gs_abs_signed_median_error_m": abs(post),
                "perturbed_p0_abs_signed_median_error_m": abs(seed),
                "condition_met": bool(abs(post) < abs(seed)),
            })
    qualifying = [row for row in candidates if row["condition_met"]]
    return {
        "schema": "jointbuildgs.s3ap.return_signal.v1", "created_utc": "fixture",
        "return_signal": bool(qualifying), "rule": rule,
        "equality_counts_as_return": False, "numeric_tolerance": None,
        "candidate_count": len(candidates), "qualifying_count": len(qualifying),
        "candidates": candidates, "qualifying": qualifying,
    }


class Phase3ArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = "exact fixture return rule"
        self.phase3 = {
            "targets": ["4907199", "8568391", "8568392"], "crs": "EPSG:25832",
            "perturbation": {
                "height_deltas_m": [0, .5, -.5, 1, -1, 2, -2, 4, -4],
                "tilt_deltas_deg": [5, -5, 10, -10, 20, -20],
                "trigger_rule": self.rule,
            },
            "phase2": {
                "training_root": "results/tum_transfer/e5_s3ap_phase2/runs",
                "prepared_template": "results/tum_transfer/e5_s3ap_phase2/prepared/DEBY_LOD2_{building}",
                "checkpoint_template": "results/tum_transfer/e5_s3ap_phase2/runs/{run_id}/ckpt/final.pt",
            },
            "scoring": {
                "gt_open_boundary": "score-only boundary",
                "footprints": "raw/footprints.geojson", "lod2_dir": "raw/lod2",
                "coverage_grid_m": 0.5,
            },
            "containers": {
                "render_image_id": "sha256:" + "1" * 64,
                "tools_image_id": "sha256:" + "2" * 64,
            },
            "roofer": {"image_id_record": "sha256:" + "3" * 64},
            "outputs": {"job_root": "jobs"},
            "extraction": {"world_offset_manifest": "inputs/world.json"},
            "roof_evidence": {"ground_source_csv": "inputs/ground.csv"},
        }
        self.archive = {
            "task_date": "2026-07-15", "crs": "EPSG:25832",
            "schemas": {
                "archive_manifest": "jointbuildgs.s3ap.phase3.wave_archive.v1",
                "archive_completion": "jointbuildgs.s3ap.phase3.wave_archive_completion.v1",
                "return_signal": "jointbuildgs.s3ap.return_signal.v1",
                "score_manifest": "jointbuildgs.s3ap.phase3.score.v1",
                "roofer_input_manifest": "jointbuildgs.s3ap.phase3.roofer_input.v1",
                "pre_readout_fingerprint": "jointbuildgs.s3ap.phase3.pre_readout_fingerprint.v1",
                "score_only_fingerprint": "jointbuildgs.s3ap.phase3.score_only_fingerprint.v1",
                "prewarm_binding": "jointbuildgs.s3ap.phase3.gsplat_prewarm_binding.v1",
                "wave_reconciliation": "jointbuildgs.s3ap.phase3.wave_reconciliation.v1",
            },
            "phase3_aggregate_schema": "jointbuildgs.s3ap.phase3.aggregate.v2",
            "phase3_script": "phase3.py", "phase3_lock": "phase3.json",
            "containers": {"tools_image_id": "sha256:" + "2" * 64},
            "policy": {"copy_prefix": "snapshot"},
            "waves": {
                "base42": {
                    "total_jobs": 42, "base_jobs": 18, "height_nonzero_jobs": 24,
                    "tilt_jobs": 0, "complete_scores": 42,
                    "perturbation_rows": 27, "nonzero_height_rows": 24,
                    "require_return_signal": None,
                },
                "final60": {
                    "total_jobs": 60, "base_jobs": 18, "height_nonzero_jobs": 24,
                    "tilt_jobs": 18, "complete_scores": 60,
                    "perturbation_rows": 27, "nonzero_height_rows": 24,
                    "require_return_signal": True,
                },
            },
        }
        self.phase2_lock = {
            "training": {"replicates": {"r1": 2001, "r2": 2002}},
            "sources": {
                "p0_surface_seed_pattern": "phases/p2-gsjso/runs/20260715_e5_c001_s3ap_phase1_seedprep/seeds/DEBY_LOD2_{building}_p0_surface_seed.npz",
            },
        }

    def inventory_row(
        self, sequence: int, run_id: str, kind: str, building: str,
        arm: str, replicate: str, value: float = 0.0,
    ) -> dict[str, str]:
        row = {key: "" for key in MODULE.INVENTORY_FIELDS}
        row.update({
            "sequence": str(sequence), "job_id": run_id, "job_class": kind,
            "building_id": building, "arm": arm, "replicate": replicate,
            "random_seed": str(self.phase2_lock["training"]["replicates"][replicate]),
            "height_delta_m": str(value if kind == "height" else 0.0),
            "tilt_deg": str(value if kind == "tilt" else 0.0),
            "config_path": f"configs/{run_id}.yaml", "config_sha256": "a" * 64,
            "data_root": f"results/tum_transfer/e5_s3ap_phase2/prepared/DEBY_LOD2_{building}",
            "surface_seed_npz": (
                f"phases/p2-gsjso/runs/20260715_e5_c001_s3ap_phase1_seedprep/seeds/DEBY_LOD2_{building}_p0_surface_seed.npz"
                if arm == "a0" else
                f"results/tum_transfer/e5_s3ap_phase2/prepared/DEBY_LOD2_{building}/seeds/DEBY_LOD2_{building}_a1a2_surface_seed.npz"
            ),
            "surface_seed_sha256": "b" * 64,
            "out_dir": f"results/tum_transfer/e5_s3ap_phase2/runs/{run_id}",
            "final_checkpoint": f"results/tum_transfer/e5_s3ap_phase2/runs/{run_id}/ckpt/final.pt",
            "iterations": "30000", "gt_used": "False", "lod2_used": "False",
            "als_used": "False", "status": "prepared",
        })
        return row

    def inventory_fixtures(self) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        base: list[dict[str, str]] = []
        for building in self.phase3["targets"]:
            for arm in ("a0", "a1", "a2"):
                for replicate in ("r1", "r2"):
                    run = f"gs_e5_C001_s3ap_b{building}_{arm}_{replicate}"
                    base.append(self.inventory_row(len(base) + 1, run, "base", building, arm, replicate))
        for building in self.phase3["targets"]:
            for value in (.5, -.5, 1, -1, 2, -2, 4, -4):
                run = f"gs_e5_C001_s3ap_b{building}_a1_dz_{MODULE.perturb_slug(value)}_r1"
                base.append(self.inventory_row(len(base) + 1, run, "height", building, "a1", "r1", value))
        tilt: list[dict[str, str]] = []
        for building in self.phase3["targets"]:
            for value in (5, -5, 10, -10, 20, -20):
                run = f"gs_e5_C001_s3ap_b{building}_a1_tilt_{MODULE.perturb_slug(value, tilt=True)}_r1"
                tilt.append(self.inventory_row(len(tilt) + 1, run, "tilt", building, "a1", "r1", value))
        return base, tilt

    def validated_inventory(self, wave: str) -> tuple[list[Any], dict[str, Any]]:
        base, tilt = self.inventory_fixtures()
        sources = [("jobs.csv", base)] + ([("tilt_jobs.csv", tilt)] if wave == "final60" else [])
        return MODULE.validate_inventory_rows(
            sources, wave, self.phase3, self.archive["waves"][wave],
            phase2_lock=self.phase2_lock,
        )

    def test_exact_base42_and_final60_inventory_grids(self) -> None:
        jobs, contract = self.validated_inventory("base42")
        self.assertEqual(len(jobs), 42)
        self.assertEqual(contract["counts"], {"total": 42, "base": 18, "height_nonzero": 24, "tilt": 0})
        jobs, contract = self.validated_inventory("final60")
        self.assertEqual(len(jobs), 60)
        self.assertEqual(contract["counts"]["tilt"], 18)

    def test_inventory_missing_wrong_tuple_or_semantic_run_id_fails(self) -> None:
        base, _ = self.inventory_fixtures()
        with self.assertRaises(MODULE.ArchiveError):
            MODULE.validate_inventory_rows([("jobs.csv", base[:-1])], "base42", self.phase3, self.archive["waves"]["base42"], phase2_lock=self.phase2_lock)
        base[0]["building_id"] = "8568391"
        with self.assertRaisesRegex(MODULE.ArchiveError, "run_id_semantic"):
            MODULE.validate_inventory_rows([("jobs.csv", base)], "base42", self.phase3, self.archive["waves"]["base42"], phase2_lock=self.phase2_lock)

    def materialize_inventory_files(self, repo: Path, rows: Sequence[dict[str, str]]) -> None:
        for row in rows:
            config = repo / row["config_path"]
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_bytes((row["job_id"] + "\n").encode())
            row["config_sha256"] = MODULE.sha256_file(config)
            seed = repo / row["surface_seed_npz"]
            seed.parent.mkdir(parents=True, exist_ok=True)
            seed.write_bytes(row["surface_seed_npz"].encode())
            row["surface_seed_sha256"] = MODULE.sha256_file(seed)
            (repo / row["data_root"]).mkdir(parents=True, exist_ok=True)
            checkpoint = repo / row["final_checkpoint"]
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            checkpoint.write_bytes((row["job_id"] + " checkpoint").encode())

    def test_inventory_physical_paths_and_hashes_fail_closed(self) -> None:
        base, _ = self.inventory_fixtures()
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            # Source jobs.csv lives at repo root, so configs/* is the exact generated config root.
            self.materialize_inventory_files(repo, base)
            MODULE.validate_inventory_rows(
                [("jobs.csv", base)], "base42", self.phase3, self.archive["waves"]["base42"],
                repo=repo, phase2_lock=self.phase2_lock,
            )
            base[0]["config_sha256"] = "f" * 64
            with self.assertRaisesRegex(MODULE.ArchiveError, "config_hash_mismatch"):
                MODULE.validate_inventory_rows(
                    [("jobs.csv", base)], "base42", self.phase3, self.archive["waves"]["base42"],
                    repo=repo, phase2_lock=self.phase2_lock,
                )

    def contract_fixture(self, wave: str, return_signal: bool) -> dict[str, Any]:
        jobs, inventory = self.validated_inventory(wave)
        scores: list[dict[str, Any]] = []
        status: list[dict[str, Any]] = []
        perturb: list[dict[str, Any]] = []
        cells: list[dict[str, Any]] = []
        for job in jobs:
            kind = "none" if job.kind == "base" else job.kind
            scores.append({
                "run_id": job.run_id, "building_id": f"DEBY_LOD2_{job.building_id}",
                "arm": job.arm, "replicate": job.replicate,
                "perturbation_type": kind, "perturbation_value": f"{job.value:.9f}",
                "checkpoint": job.final_checkpoint, "checkpoint_sha256": "",
                "prepared_root": job.data_root, "score_status": "complete", "crs": "EPSG:25832",
                "supplied_footprint_passed_to_roofer": "false", "gt_role": "score-only boundary",
                "footprint_role": "score-region and coverage mask opened after Roofer input finalization",
            })
            status.append({
                "run_id": job.run_id, "building_id": f"DEBY_LOD2_{job.building_id}",
                "arm": job.arm, "replicate": job.replicate,
                "perturbation_type": kind, "perturbation_value": f"{job.value:.9f}",
                "stage": "score", "status": "complete", "checkpoint": job.final_checkpoint,
                "prepared_root": job.data_root, "job_dir": f"jobs/{job.run_id}",
            })
            if job.arm == "a1" and job.replicate == "r1" and job.kind in {"base", "height"}:
                delta = 0.0 if job.kind == "base" else job.value
                p0 = 0.1
                seed = p0 + delta
                post = 0.0 if return_signal else abs(seed) + 1.0
                condition = bool(delta != 0.0 and abs(post) < abs(seed))
                row = {
                    "run_id": job.run_id, "building_id": f"DEBY_LOD2_{job.building_id}",
                    "arm": job.arm, "replicate": job.replicate, "delta_m": f"{delta:.9f}",
                    "score_status": "complete", "p0_signed_median_error_m": f"{p0:.9f}",
                    "perturbed_p0_signed_median_error_m": f"{seed:.9f}",
                    "perturbed_p0_abs_signed_median_error_m": f"{abs(seed):.9f}",
                    "post_gs_signed_median_error_m": f"{post:.9f}",
                    "post_gs_abs_signed_median_error_m": f"{abs(post):.9f}",
                    "signed_error_reduction_m": f"{abs(seed) - abs(post):.9f}",
                    "post_minus_perturbed_seed_signed_m": f"{post - seed:.9f}",
                    "return_condition_met": str(condition).lower(),
                    "trigger_candidate": str(delta != 0.0).lower(), "trigger_rule": self.rule,
                }
                perturb.append(row)
                cells.append({
                    "run_id": job.run_id, "building_id": f"DEBY_LOD2_{job.building_id}",
                    "arm": job.arm, "replicate": job.replicate, "delta_m": f"{delta:.9f}",
                    "cell_ix": "0", "cell_iy": "0", "cell_center_x": "0.250000000",
                    "cell_center_y": "0.250000000", "region": "edge",
                    "p0_base_signed_error_m": f"{p0:.9f}",
                    "perturbed_p0_signed_error_m": f"{seed:.9f}",
                    "perturbed_p0_abs_error_m": f"{abs(seed):.9f}",
                    "post_gs_point_count": "1", "post_gs_signed_error_m": f"{post:.9f}",
                    "post_gs_abs_error_m": f"{abs(post):.9f}",
                    "return_amount_m": f"{abs(seed) - abs(post):.9f}",
                    "return_condition_met": str(condition).lower(),
                    "coverage_grid_m": "0.500000000", "score_status": "complete",
                })
        trigger = trigger_from_rows(perturb, self.rule)
        trigger.update({
            "raw_return_signal": trigger["return_signal"], "evaluation_complete": True,
            "expected_nonzero_height_rows": 24, "observed_nonzero_height_rows": 24,
            "complete_nonzero_height_rows": 24,
        })
        aggregate = {
            "schema": "jointbuildgs.s3ap.phase3.aggregate.v2", "status": "complete",
            "training_runs_started": 0, "new_mast3r_inference_runs": 0,
            "interpretation_or_verdict": None, "gt_boundary": "score-only boundary",
            "supplied_footprint_passed_to_roofer": False, "trigger": trigger,
            "status_row_count": len(status),
            "aggregate_contract": {
                "status": "complete", "errors": [], "invalid_current_rows": [],
                "stale_job_directories": [],
                "inventory": {"counts": inventory["counts"], "current_run_ids": inventory["run_ids"]},
                "score_row_count": len(scores), "complete_score_count": len(scores),
                "nonzero_height_row_count": 24, "complete_nonzero_height_row_count": 24,
            },
        }
        module = SimpleNamespace(
            SCORE_FIELDS=list(scores[0]), PERTURB_FIELDS=list(perturb[0]),
            PERTURB_CELL_FIELDS=list(cells[0]), STATUS_FIELDS=list(status[0]),
            perturbation_trigger=trigger_from_rows,
        )
        return {"jobs": jobs, "inventory": inventory, "scores": scores, "perturb": perturb, "cells": cells, "status": status, "trigger": trigger, "aggregate": aggregate, "module": module}

    def validate_contract_fixture(self, wave: str, fixture: dict[str, Any]) -> dict[str, Any]:
        return MODULE.validate_wave_contract(
            wave=wave, archive=self.archive, phase3=self.phase3, jobs=fixture["jobs"],
            inventory=fixture["inventory"], aggregate=fixture["aggregate"], trigger=fixture["trigger"],
            score_header=list(fixture["scores"][0]), score_rows=fixture["scores"],
            perturb_header=list(fixture["perturb"][0]), perturb_rows=fixture["perturb"],
            cell_header=list(fixture["cells"][0]), cell_rows=fixture["cells"],
            status_header=list(fixture["status"][0]), status_rows=fixture["status"],
            phase3_module=fixture["module"],
        )

    def authoritative_perturb_fixture(self, fixture: Mapping[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for source in fixture["perturb"]:
            row: dict[str, Any] = dict(source)
            for field in (
                "delta_m", "p0_signed_median_error_m",
                "perturbed_p0_signed_median_error_m",
                "perturbed_p0_abs_signed_median_error_m",
                "post_gs_signed_median_error_m", "post_gs_abs_signed_median_error_m",
                "signed_error_reduction_m", "post_minus_perturbed_seed_signed_m",
            ):
                row[field] = float(source[field])
            delta = row["delta_m"]
            p0 = row["p0_signed_median_error_m"]
            perturbed = p0 + delta
            post = 0.0 if fixture["trigger"]["return_signal"] else abs(perturbed) + 1.0
            row.update({
                "perturbed_p0_signed_median_error_m": perturbed,
                "perturbed_p0_abs_signed_median_error_m": abs(perturbed),
                "post_gs_signed_median_error_m": post,
                "post_gs_abs_signed_median_error_m": abs(post),
                "signed_error_reduction_m": abs(perturbed) - abs(post),
                "post_minus_perturbed_seed_signed_m": post - perturbed,
                "return_condition_met": bool(delta != 0.0 and abs(post) < abs(perturbed)),
                "trigger_candidate": bool(delta != 0.0),
            })
            rows.append(row)
        return rows

    def test_wave_contract_requires_all_scores_and_exact_height_evaluation(self) -> None:
        fixture = self.contract_fixture("base42", False)
        self.assertEqual(self.validate_contract_fixture("base42", fixture)["complete_scores"], 42)
        fixture["scores"][0]["score_status"] = "partial"
        with self.assertRaisesRegex(MODULE.ArchiveError, "not_all_complete"):
            self.validate_contract_fixture("base42", fixture)

    def test_score_identity_and_locked_height_grid_attacks_fail(self) -> None:
        fixture = self.contract_fixture("base42", False)
        fixture["scores"][0]["building_id"] = "DEBY_LOD2_8568392"
        with self.assertRaisesRegex(MODULE.ArchiveError, "score_building"):
            self.validate_contract_fixture("base42", fixture)
        fixture = self.contract_fixture("base42", False)
        fixture["perturb"][0]["delta_m"] = "123.000000000"
        with self.assertRaisesRegex(MODULE.ArchiveError, "perturbation_delta"):
            self.validate_contract_fixture("base42", fixture)
        fixture = self.contract_fixture("base42", False)
        old = fixture["perturb"][0]["run_id"]
        replacement = next(
            job.run_id for job in fixture["jobs"]
            if job.kind == "base" and job.arm == "a0"
        )
        fixture["perturb"][0]["run_id"] = replacement
        fixture["cells"][0]["run_id"] = replacement
        self.assertNotEqual(old, replacement)
        with self.assertRaisesRegex(MODULE.ArchiveError, "exact_set"):
            self.validate_contract_fixture("base42", fixture)

    def test_forged_final60_trigger_candidates_fail_semantic_recompute(self) -> None:
        fixture = self.contract_fixture("final60", True)
        fixture["trigger"]["candidates"][0]["run_id"] = "forged"
        fixture["aggregate"]["trigger"] = fixture["trigger"]
        with self.assertRaisesRegex(MODULE.ArchiveError, "trigger_candidates_semantic"):
            self.validate_contract_fixture("final60", fixture)

    def test_reviewer_trigger_exact_schema_subnanometric_and_nan_attacks_fail(self) -> None:
        fixture = self.contract_fixture("final60", True)
        fixture["trigger"]["candidates"][0]["rogue"] = "forged"
        with self.assertRaisesRegex(MODULE.ArchiveError, "trigger_candidates_row_schema"):
            self.validate_contract_fixture("final60", fixture)

        fixture = self.contract_fixture("final60", True)
        del fixture["trigger"]["candidates"][0]["condition_met"]
        with self.assertRaisesRegex(MODULE.ArchiveError, "trigger_candidates_row_schema"):
            self.validate_contract_fixture("final60", fixture)

        fixture = self.contract_fixture("final60", True)
        fixture["trigger"]["candidates"][0]["post_gs_abs_signed_median_error_m"] += 1e-12
        with self.assertRaisesRegex(MODULE.ArchiveError, "trigger_candidates_semantic"):
            self.validate_contract_fixture("final60", fixture)

        fixture = self.contract_fixture("final60", True)
        fixture["trigger"]["candidates"][0]["delta_m"] = float("nan")
        with self.assertRaisesRegex(MODULE.ArchiveError, "trigger_candidates_delta_m_nonfinite"):
            self.validate_contract_fixture("final60", fixture)

    def test_reviewer_authoritative_json_float_algebra_and_global_order_are_exact(self) -> None:
        fixture = self.contract_fixture("final60", True)
        authoritative = list(reversed(self.authoritative_perturb_fixture(fixture)))
        counts = MODULE.validate_wave_contract(
            wave="final60", archive=self.archive, phase3=self.phase3,
            jobs=fixture["jobs"], inventory=fixture["inventory"],
            aggregate=fixture["aggregate"], trigger=fixture["trigger"],
            score_header=list(fixture["scores"][0]), score_rows=fixture["scores"],
            perturb_header=list(fixture["perturb"][0]), perturb_rows=fixture["perturb"],
            cell_header=list(fixture["cells"][0]), cell_rows=fixture["cells"],
            status_header=list(fixture["status"][0]), status_rows=fixture["status"],
            phase3_module=fixture["module"],
            authoritative_perturb_rows=authoritative,
        )
        self.assertEqual(counts["complete_scores"], 60)

    def test_reviewer_every_perturbation_cell_field_attack_fails_closed(self) -> None:
        attacks = (
            ("cell_center_x", "nan", "cell_center_x.*nonfinite"),
            ("cell_center_x", "0.750000000", "cell_center_grid_mismatch"),
            ("perturbed_p0_signed_error_m", "0.100000001", "cell_perturbed_equation"),
            ("region", "roof", "cell_region_invalid"),
            ("post_gs_point_count", "0", "cell_empty_post_fields"),
            ("return_condition_met", "true", "cell_condition_mismatch"),
            ("coverage_grid_m", "0.500000001", "cell_grid_mismatch"),
            ("score_status", "forged", "perturbation_cells_not_complete"),
        )
        for field, value, reason in attacks:
            with self.subTest(field=field):
                fixture = self.contract_fixture("base42", False)
                fixture["cells"][0][field] = value
                with self.assertRaisesRegex(MODULE.ArchiveError, reason):
                    self.validate_contract_fixture("base42", fixture)

        fixture = self.contract_fixture("base42", False)
        first = fixture["cells"][0]
        same_building = next(
            row for row in fixture["cells"][1:]
            if row["building_id"] == first["building_id"]
        )
        same_building["region"] = "interior"
        with self.assertRaisesRegex(MODULE.ArchiveError, "cell_cross_run_reference_mismatch"):
            self.validate_contract_fixture("base42", fixture)

    def test_fingerprint_digest_is_schema_and_byte_sensitive(self) -> None:
        payload = {"schema": "locked.schema", "boundary": "score-only"}
        fingerprint = {"payload": payload, "digest": MODULE.canonical_digest(payload)}
        MODULE.validate_fingerprint(fingerprint, "locked.schema", "fixture")
        fingerprint["payload"]["boundary"] = "before-readout"
        with self.assertRaisesRegex(MODULE.ArchiveError, "digest_mismatch"):
            MODULE.validate_fingerprint(fingerprint, "locked.schema", "fixture")

    def test_prewarm_binding_rechecks_full_source_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            verification_path = repo / "prewarm_verification.json"
            source = repo / "extension.so"
            verification_path.write_bytes(b"verification")
            source.write_bytes(b"extension")
            phase3 = {"outputs": {"prewarm_verification": "prewarm_verification.json"}}
            archive = {"schemas": {"prewarm_binding": "binding.v1"}}
            source_bundle = bundle([{"path": "extension.so", "size_bytes": source.stat().st_size, "sha256": MODULE.sha256_file(source)}])
            verification = {"extension_path": "extension.so", "extension_sha256": MODULE.sha256_file(source)}
            binding = {
                "schema": "binding.v1", "verification": "prewarm_verification.json",
                "verification_sha256": MODULE.sha256_file(verification_path),
                "extension": "extension.so", "extension_sha256": MODULE.sha256_file(source),
                "source_bundle": source_bundle,
            }
            binding["digest"] = MODULE.canonical_digest({
                "verification_sha256": binding["verification_sha256"],
                "extension_sha256": binding["extension_sha256"],
                "source_bundle_digest": source_bundle["digest"],
            })
            MODULE.validate_prewarm_binding(binding, verification, archive, phase3, repo)
            source.write_bytes(b"drift")
            with self.assertRaisesRegex(MODULE.ArchiveError, "source_size|source_hash"):
                MODULE.validate_prewarm_binding(binding, verification, archive, phase3, repo)

    def make_job_bundle(self, repo: Path) -> tuple[Any, list[dict[str, str]], dict[str, Any], dict[str, Any]]:
        (repo / "phase3.py").write_text("# fixture\n", encoding="utf-8")
        write_json(repo / "phase3.json", {"schema": "fixture"})
        (repo / "src/stage2").mkdir(parents=True)
        (repo / "src/stage2/colmap_io.py").write_text("# io\n", encoding="utf-8")
        (repo / "inputs").mkdir()
        (repo / "inputs/world.json").write_text("{}\n")
        (repo / "inputs/ground.csv").write_text("z\n")
        config = repo / "configs/run1.yaml"; config.parent.mkdir(); config.write_text("x\n")
        seed = repo / "seed.npz"; seed.write_bytes(b"surface-seed")
        checkpoint = repo / "runs/run1/ckpt/final.pt"; checkpoint.parent.mkdir(parents=True); checkpoint.write_bytes(b"checkpoint")
        prepared_file = repo / "prepared/DEBY_LOD2_4907199/images/a.png"; prepared_file.parent.mkdir(parents=True); prepared_file.write_bytes(b"image")
        job = MODULE.InventoryJob(
            run_id="run1", building_id="4907199", arm="a0", replicate="r1", kind="base", value=0.0,
            random_seed=2001, config_path="configs/run1.yaml", config_sha256=MODULE.sha256_file(config),
            data_root="prepared/DEBY_LOD2_4907199", surface_seed_npz="seed.npz",
            surface_seed_sha256=MODULE.sha256_file(seed), out_dir="runs/run1", final_checkpoint="runs/run1/ckpt/final.pt",
            checkpoint_sha256=MODULE.sha256_file(checkpoint), source_inventory="jobs.csv",
        )
        expected_job = job.phase3_job()
        job_dir = repo / "jobs/run1"; job_dir.mkdir(parents=True)
        (job_dir / "fused_depth.npz").write_bytes(b"fused")
        (job_dir / "roofer_input.npz").write_bytes(b"roofer-input")
        prewarm = {"schema": "binding.v1", "digest": "locked"}
        pre_payload = {
            "schema": self.archive["schemas"]["pre_readout_fingerprint"], "job": expected_job,
            "phase3_script_sha256": MODULE.sha256_file(repo / "phase3.py"),
            "phase3_config_sha256": MODULE.sha256_file(repo / "phase3.json"),
            "pre_readout_code_dependencies": bundle([{
                "path": "src/stage2/colmap_io.py", "size_bytes": (repo / "src/stage2/colmap_io.py").stat().st_size,
                "sha256": MODULE.sha256_file(repo / "src/stage2/colmap_io.py"),
            }]),
            "phase2_job_config": {"path": job.config_path, "sha256": job.config_sha256},
            "checkpoint_sha256": job.checkpoint_sha256,
            "prepared_sparse_images": {
                **bundle([{"path": "prepared/DEBY_LOD2_4907199/images/a.png", "size_bytes": prepared_file.stat().st_size, "sha256": MODULE.sha256_file(prepared_file)}]),
                "prepared_root": job.data_root,
            },
            "world_offset_manifest": {"path": "inputs/world.json", "sha256": MODULE.sha256_file(repo / "inputs/world.json")},
            "observed_ground_source": {"path": "inputs/ground.csv", "sha256": MODULE.sha256_file(repo / "inputs/ground.csv")},
            "phase2_serialized_gsplat_prewarm": prewarm,
            "locked_docker_image_ids": {
                "render": self.phase3["containers"]["render_image_id"],
                "tools": self.phase3["containers"]["tools_image_id"],
                "roofer": self.phase3["roofer"]["image_id_record"],
            },
        }
        pre = {"payload": pre_payload, "digest": MODULE.canonical_digest(pre_payload)}
        extraction_manifest = {
            "schema": "jointbuildgs.s3ap.phase3.extraction.v1", "job": expected_job,
            "pre_readout_fingerprint": pre, "checkpoint": job.final_checkpoint,
            "checkpoint_sha256": job.checkpoint_sha256, "prepared_root": job.data_root,
            "gt_used": False, "lod2_used": False, "als_used": False,
            "output_npz": "jobs/run1/fused_depth.npz",
            "output_sha256": MODULE.sha256_file(job_dir / "fused_depth.npz"),
        }
        write_json(job_dir / "extraction_manifest.json", extraction_manifest)
        score_bundle = bundle([{"path": "raw/lod2/roof.gml", "size_bytes": 12, "sha256": "d" * 64}])
        score_payload = {"schema": self.archive["schemas"]["score_only_fingerprint"], "boundary": "score-only boundary", "bundle": score_bundle}
        score_only = {"payload": score_payload, "digest": MODULE.canonical_digest(score_payload)}
        full = MODULE.canonical_digest({"schema": "jointbuildgs.s3ap.phase3.full_reuse_fingerprint.v1", "pre_readout_digest": pre["digest"], "score_only_digest": score_only["digest"]})
        input_manifest = {
            "schema": self.archive["schemas"]["roofer_input_manifest"], "job": expected_job,
            "supplied_footprint_opened": False, "supplied_footprint_passed_to_roofer": False,
            "lod2_opened": False, "als_opened": False, "gt_used": False,
            "lod2_used": False, "als_used": False, "pre_readout_fingerprint": pre,
            "source_extraction_manifest": "jobs/run1/extraction_manifest.json",
            "source_extraction_sha256": MODULE.sha256_file(job_dir / "fused_depth.npz"),
            "roofer_input_npz": "jobs/run1/roofer_input.npz",
            "roofer_input_npz_sha256": MODULE.sha256_file(job_dir / "roofer_input.npz"),
            "roofer_las": "", "roofer_las_sha256": "",
            "derived_roofprint": "", "derived_roofprint_sha256": "",
        }
        write_json(job_dir / "roofer_input_manifest.json", input_manifest)
        score = {
            "run_id": "run1", "building_id": "DEBY_LOD2_4907199", "arm": "a0", "replicate": "r1",
            "score_status": "complete", "extraction_manifest": "jobs/run1/extraction_manifest.json",
            "roofer_input_manifest": "jobs/run1/roofer_input_manifest.json",
        }
        write_json(job_dir / "score_row.json", score)
        score_manifest = {
            "schema": self.archive["schemas"]["score_manifest"], "job": expected_job,
            "score_row": "jobs/run1/score_row.json", "score_row_sha256": MODULE.sha256_file(job_dir / "score_row.json"),
            "phase3_script_sha256": MODULE.sha256_file(repo / "phase3.py"),
            "phase3_config_sha256": MODULE.sha256_file(repo / "phase3.json"),
            "pre_readout_fingerprint": pre, "score_only_fingerprint": score_only,
            "full_reuse_fingerprint": full, "roofer_input_manifest": "jobs/run1/roofer_input_manifest.json",
            "roofer_input_manifest_sha256": MODULE.sha256_file(job_dir / "roofer_input_manifest.json"),
            "perturbation_row": None, "perturbation_row_sha256": None,
            "perturbation_cells": None, "perturbation_cells_sha256": None,
            "gt_opened_after_roofer_input_finalized": True,
            "cityjson": None, "cityjson_sha256": None, "val3dity_report": None,
            "val3dity_report_sha256": None, "val3dity_log": None, "val3dity_log_sha256": None,
        }
        write_json(job_dir / "score_manifest.json", score_manifest)
        csv_row = {key: MODULE.csv_scalar(value) for key, value in score.items()}
        aggregate = {"aggregate_contract": {"invalid_current_rows": []}, "phase2_serialized_gsplat_prewarm": prewarm}
        return job, [csv_row], aggregate, score_manifest

    def test_job_bundle_cross_binds_identity_prewarm_and_canonical_bundles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            job, rows, aggregate, manifest = self.make_job_bundle(repo)
            _, fingerprints, _, _, bound_inputs = MODULE.validate_job_bundles(
                [job], rows, self.archive, self.phase3, aggregate, repo, score_fields=list(rows[0]),
            )
            self.assertEqual(fingerprints[0]["run_id"], "run1")
            self.assertIn(repo / "configs/run1.yaml", bound_inputs)
            manifest["job"]["building_id"] = "8568392"
            write_json(repo / "jobs/run1/score_manifest.json", manifest)
            with self.assertRaisesRegex(MODULE.ArchiveError, "manifest_identity"):
                MODULE.validate_job_bundles([job], rows, self.archive, self.phase3, aggregate, repo, score_fields=list(rows[0]))

    def test_reviewer_post_inventory_seed_config_and_checkpoint_drift_fail(self) -> None:
        for filename, reason in (
            ("seed.npz", "job_phase2_surface_seed_hash_drift"),
            ("configs/run1.yaml", "job_phase2_config_hash_drift"),
            ("runs/run1/ckpt/final.pt", "job_phase2_checkpoint_hash_drift"),
        ):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                repo = Path(directory)
                job, rows, aggregate, _ = self.make_job_bundle(repo)
                (repo / filename).write_bytes(b"post-inventory-drift")
                with self.assertRaisesRegex(MODULE.ArchiveError, reason):
                    MODULE.validate_job_bundles(
                        [job], rows, self.archive, self.phase3, aggregate, repo,
                        score_fields=list(rows[0]),
                    )

    def test_job_bundle_rejects_forged_prewarm_and_score_only_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            job, rows, aggregate, manifest = self.make_job_bundle(repo)
            pre = manifest["pre_readout_fingerprint"]
            pre["payload"]["phase2_serialized_gsplat_prewarm"] = {"schema": "binding.v1", "digest": "forged"}
            pre["digest"] = MODULE.canonical_digest(pre["payload"])
            input_path = repo / "jobs/run1/roofer_input_manifest.json"
            input_manifest = json.loads(input_path.read_text())
            input_manifest["pre_readout_fingerprint"] = pre
            write_json(input_path, input_manifest)
            manifest["pre_readout_fingerprint"] = pre
            manifest["roofer_input_manifest_sha256"] = MODULE.sha256_file(input_path)
            manifest["full_reuse_fingerprint"] = MODULE.canonical_digest({
                "schema": "jointbuildgs.s3ap.phase3.full_reuse_fingerprint.v1",
                "pre_readout_digest": pre["digest"],
                "score_only_digest": manifest["score_only_fingerprint"]["digest"],
            })
            write_json(repo / "jobs/run1/score_manifest.json", manifest)
            with self.assertRaisesRegex(MODULE.ArchiveError, "pre_prewarm_binding"):
                MODULE.validate_job_bundles([job], rows, self.archive, self.phase3, aggregate, repo, score_fields=list(rows[0]))
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            job, rows, aggregate, manifest = self.make_job_bundle(repo)
            score_only = manifest["score_only_fingerprint"]
            score_only["payload"]["bundle"]["file_count"] = -99
            score_only["digest"] = MODULE.canonical_digest(score_only["payload"])
            manifest["score_only_fingerprint"] = score_only
            manifest["full_reuse_fingerprint"] = MODULE.canonical_digest({
                "schema": "jointbuildgs.s3ap.phase3.full_reuse_fingerprint.v1",
                "pre_readout_digest": manifest["pre_readout_fingerprint"]["digest"],
                "score_only_digest": score_only["digest"],
            })
            write_json(repo / "jobs/run1/score_manifest.json", manifest)
            with self.assertRaisesRegex(MODULE.ArchiveError, "file_count_mismatch"):
                MODULE.validate_job_bundles([job], rows, self.archive, self.phase3, aggregate, repo, score_fields=list(rows[0]))

    def archive_payload_fixture(
        self, mapping: Sequence[Mapping[str, Any]], wave: str,
    ) -> dict[str, Any]:
        mapped = {Path(str(row["source_path"])).stem: row for row in mapping}
        counts = {
            "score_rows": 42 if wave == "base42" else 60,
            "complete_scores": 42 if wave == "base42" else 60,
            "perturbation_rows": 27, "nonzero_height_rows": 24,
            "perturbation_cell_rows": 27,
            "status_rows": 42 if wave == "base42" else 60,
            "evaluation_complete": True,
            "return_signal": wave == "final60",
            "declared_figure_files": 1, "skipped_figure_records": 0,
        }
        total = counts["score_rows"]
        run_ids = [f"run{i:02d}" for i in range(total)]
        inventory = {
            "wave": wave,
            "counts": {"total": total, "base": 18, "height_nonzero": 24, "tilt": 0 if wave == "base42" else 18},
            "run_ids": run_ids, "base_tuple_count": 18, "height_tuple_count": 24,
            "tilt_tuple_count": 0 if wave == "base42" else 18,
            "job_contract_digest": "c" * 64,
        }
        source_fingerprints = [{
            "run_id": run_id, "pre_readout_digest": "1" * 64,
            "score_only_digest": "2" * 64, "full_reuse_fingerprint": "3" * 64,
            "score_only_bundle_file_count": 1, "gt_content_reopened_by_archive": False,
            "phase2_input_binding": {
                "schema": MODULE.PHASE2_INPUT_BINDING_SCHEMA, "random_seed": 2001,
                "config": {"path": "config.yaml", "sha256": mapped["config"]["sha256"]},
                "surface_seed": {"path": "seed.npz", "sha256": mapped["seed"]["sha256"]},
                "checkpoint": {"path": "checkpoint.pt", "sha256": mapped["checkpoint"]["sha256"]},
            },
        } for run_id in run_ids]
        for row in source_fingerprints:
            row["phase2_input_binding_digest"] = MODULE.canonical_digest(
                row["phase2_input_binding"]
            )
        return {
            "wave": wave, "task_date": self.archive["task_date"], "crs": self.archive["crs"],
            "archive_lock": "archive_lock.json", "archive_lock_sha256": mapped["archive_lock"]["sha256"],
            "phase3_lock": "phase3_lock.json", "phase3_lock_sha256": mapped["phase3_lock"]["sha256"],
            "phase3_aggregate_manifest": "manifest.json",
            "phase3_aggregate_manifest_sha256": mapped["manifest"]["sha256"],
            "inventory_contract": inventory, "measurement_counts": counts,
            "wave_reconciliation": {
                "schema": self.archive["schemas"]["wave_reconciliation"], "wave": wave,
                "inventory_job_contract_digest": inventory["job_contract_digest"],
                "phase3_aggregate_manifest": "manifest.json",
                "phase3_aggregate_manifest_sha256": mapped["manifest"]["sha256"],
                "source_mapping_digest": MODULE.canonical_digest(list(mapping)),
                "complete_score_count": counts["complete_scores"],
                "nonzero_height_rows": 24, "evaluation_complete": True,
                "return_signal": counts["return_signal"],
                "outputs": {
                    key: {
                        "source_path": mapped[key]["source_path"],
                        "archive_path": mapped[key]["archive_path"],
                        "size_bytes": mapped[key]["size_bytes"],
                        "sha256": mapped[key]["sha256"],
                    }
                    for key in ("scores", "perturbation", "cells", "trigger")
                },
            },
            "executed_sources": {
                "archive_controller": {"path": "archive_controller.py", "sha256": mapped["archive_controller"]["sha256"]},
                "phase3_controller": {"path": "phase3_controller.py", "sha256": mapped["phase3_controller"]["sha256"]},
            },
            "image_verification": {"path": "images.dat", "sha256": mapped["images"]["sha256"], "tools_image_id": "sha256:" + "2" * 64},
            "prewarm_verification": {"path": "prewarm.dat", "sha256": mapped["prewarm"]["sha256"], "extension_path": "extension.so", "extension_sha256": mapped["extension"]["sha256"]},
            "source_fingerprints": source_fingerprints,
            "gt_boundary": {"contract": "score-only", "supplied_footprint_passed_to_roofer": False, "raw_gt_content_opened_by_archive": False, "validation_method": "manifests"},
            "large_output_policy": "sha256_only", "training_runs_started": 0,
            "new_mast3r_inference_runs": 0, "interpretation_or_verdict": None,
        }

    def archive_mapping_fixture(self, repo: Path, *, include_large: bool = True) -> list[dict[str, Any]]:
        copied_paths: list[tuple[Path, str]] = []
        for name in (
            "scores", "perturbation", "cells", "trigger", "archive_lock",
            "phase3_lock", "manifest", "phase3_controller", "images", "prewarm",
        ):
            path = repo / (f"{name}.json" if "lock" in name or name == "manifest" else f"{name}.dat")
            if name == "phase3_controller":
                path = repo / "phase3_controller.py"
            path.write_bytes((name + "-v1").encode())
            copied_paths.append((path, name))
        archive_controller = repo / "archive_controller.py"
        archive_controller.write_bytes(b"archive-controller-v1")
        bound: list[tuple[Path, str]] = [(archive_controller, "archive_controller")]
        for filename, role in (
            ("extension.so", "extension"), ("config.yaml", "config"),
            ("seed.npz", "seed"), ("checkpoint.pt", "checkpoint"),
        ):
            path = repo / filename
            path.write_bytes((role + "-v1").encode())
            bound.append((path, role))
        if include_large:
            large = repo / "large.bin"; large.write_bytes(b"large-v1"); bound.append((large, "large"))
        return MODULE.source_mapping(copied=copied_paths, bound=bound, copy_prefix="snapshot", repo=repo)
    def test_archive_is_atomic_exact_idempotent_and_wave_specific(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            mapping = self.archive_mapping_fixture(repo)
            destination = repo / "archives/base42"
            payload = self.archive_payload_fixture(mapping, "base42")
            self.assertEqual(MODULE.materialize_archive(destination=destination, mapping=mapping, payload=payload, archive=self.archive, repo=repo)["status"], "complete")
            self.assertEqual(MODULE.materialize_archive(destination=destination, mapping=mapping, payload=payload, archive=self.archive, repo=repo)["status"], "already_complete")
            (repo / "scores.dat").write_bytes(b"scores-drift")
            changed_mapping = MODULE.source_mapping(
                copied=[
                    (repo / (f"{name}.json" if "lock" in name or name == "manifest" else f"{name}.dat"), name)
                    for name in ("scores", "perturbation", "cells", "trigger", "archive_lock", "phase3_lock", "manifest", "images", "prewarm")
                ] + [(repo / "phase3_controller.py", "phase3_controller")],
                bound=[
                    (repo / "archive_controller.py", "archive_controller"),
                    (repo / "extension.so", "extension"),
                    (repo / "config.yaml", "config"), (repo / "seed.npz", "seed"),
                    (repo / "checkpoint.pt", "checkpoint"), (repo / "large.bin", "large"),
                ],
                copy_prefix="snapshot", repo=repo,
            )
            with self.assertRaisesRegex(MODULE.ArchiveError, "payload_contract|mapping_contract"):
                MODULE.materialize_archive(destination=destination, mapping=changed_mapping, payload=self.archive_payload_fixture(changed_mapping, "base42"), archive=self.archive, repo=repo)
            (repo / "scores.dat").write_bytes(b"scores-v1")
            with self.assertRaisesRegex(MODULE.ArchiveError, "expected_wave|payload_contract"):
                MODULE.materialize_archive(destination=destination, mapping=mapping, payload=self.archive_payload_fixture(mapping, "final60"), archive=self.archive, repo=repo)
            (destination / "rogue.txt").write_bytes(b"rogue")
            with self.assertRaisesRegex(MODULE.ArchiveError, "file_set"):
                MODULE.verify_archive_directory(destination, True, repo, expected_wave="base42", archive=self.archive)

    def test_completion_wave_mismatch_and_raw_gt_mapping_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            mapping = self.archive_mapping_fixture(repo, include_large=False)
            destination = repo / "archives/base42"
            MODULE.materialize_archive(destination=destination, mapping=mapping, payload=self.archive_payload_fixture(mapping, "base42"), archive=self.archive, repo=repo)
            completion = json.loads((destination / "COMPLETED.json").read_text())
            completion["wave"] = "final60"
            write_json(destination / "COMPLETED.json", completion)
            with self.assertRaisesRegex(MODULE.ArchiveError, "completion_wave"):
                MODULE.verify_archive_directory(destination, True, repo, expected_wave="base42", archive=self.archive)
            raw = repo / "raw/lod2/roof.gml"; raw.parent.mkdir(parents=True); raw.write_bytes(b"gt")
            raw_mapping = MODULE.source_mapping(copied=[], bound=[(raw, "forbidden")], copy_prefix="snapshot", repo=repo)
            with self.assertRaisesRegex(MODULE.ArchiveError, "raw_gt_source"):
                MODULE.materialize_archive(destination=repo / "archives/final60", mapping=raw_mapping, payload={"wave": "final60"}, archive=self.archive, repo=repo, forbidden_source_roots=[repo / "raw/lod2"])

    def test_reviewer_standalone_payload_exact_schema_counts_and_return_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            mapping = self.archive_mapping_fixture(repo)
            payload = self.archive_payload_fixture(mapping, "final60")
            MODULE.validate_archive_payload_contract(payload, mapping, archive=self.archive)

            rogue = deepcopy(payload); rogue["rogue"] = True
            with self.assertRaisesRegex(MODULE.ArchiveError, "payload_fields"):
                MODULE.validate_archive_payload_contract(rogue, mapping, archive=self.archive)
            rogue = deepcopy(payload); rogue["measurement_counts"]["rogue"] = 1
            with self.assertRaisesRegex(MODULE.ArchiveError, "measurement_fields"):
                MODULE.validate_archive_payload_contract(rogue, mapping, archive=self.archive)
            rogue = deepcopy(payload); rogue["wave_reconciliation"]["rogue"] = 1
            with self.assertRaisesRegex(MODULE.ArchiveError, "reconciliation_fields"):
                MODULE.validate_archive_payload_contract(rogue, mapping, archive=self.archive)
            duplicate_output = deepcopy(payload)
            duplicate_output["wave_reconciliation"]["outputs"]["trigger"] = deepcopy(
                duplicate_output["wave_reconciliation"]["outputs"]["scores"]
            )
            with self.assertRaisesRegex(MODULE.ArchiveError, "output_sources_not_unique"):
                MODULE.validate_archive_payload_contract(duplicate_output, mapping, archive=self.archive)
            wrong_count = deepcopy(payload); wrong_count["measurement_counts"]["score_rows"] = 59
            with self.assertRaisesRegex(MODULE.ArchiveError, "score_rows"):
                MODULE.validate_archive_payload_contract(wrong_count, mapping, archive=self.archive)
            string_count = deepcopy(payload); string_count["measurement_counts"]["score_rows"] = "60"
            with self.assertRaisesRegex(MODULE.ArchiveError, "score_rows_type"):
                MODULE.validate_archive_payload_contract(string_count, mapping, archive=self.archive)
            incomplete = deepcopy(payload); incomplete["measurement_counts"]["evaluation_complete"] = False
            with self.assertRaisesRegex(MODULE.ArchiveError, "evaluation_incomplete"):
                MODULE.validate_archive_payload_contract(incomplete, mapping, archive=self.archive)
            no_return = deepcopy(payload); no_return["measurement_counts"]["return_signal"] = False
            with self.assertRaisesRegex(MODULE.ArchiveError, "final60_return_signal"):
                MODULE.validate_archive_payload_contract(no_return, mapping, archive=self.archive)

    def test_reviewer_seed_binding_and_executed_source_mapping_mismatch_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            mapping = self.archive_mapping_fixture(repo)
            payload = self.archive_payload_fixture(mapping, "base42")
            forged_seed = deepcopy(payload)
            binding = forged_seed["source_fingerprints"][0]["phase2_input_binding"]
            binding["surface_seed"]["sha256"] = "f" * 64
            forged_seed["source_fingerprints"][0]["phase2_input_binding_digest"] = MODULE.canonical_digest(binding)
            with self.assertRaisesRegex(MODULE.ArchiveError, "phase2_binding_mapping:surface_seed"):
                MODULE.validate_archive_payload_contract(forged_seed, mapping, archive=self.archive)
            forged_source = deepcopy(payload)
            forged_source["executed_sources"]["archive_controller"]["sha256"] = "e" * 64
            with self.assertRaisesRegex(MODULE.ArchiveError, "executed_mapping:archive_controller"):
                MODULE.validate_archive_payload_contract(forged_source, mapping, archive=self.archive)
            with self.assertRaisesRegex(MODULE.ArchiveError, "executed_archive_controller_mapping_mismatch"):
                MODULE.validate_executed_source_mapping(
                    mapping, forged_source["executed_sources"],
                )

    def test_reviewer_final_prewrite_rehash_rejects_bound_source_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            mapping = self.archive_mapping_fixture(repo)
            payload = self.archive_payload_fixture(mapping, "base42")
            destination = repo / "archives/base42"
            original_atomic_copy = MODULE.atomic_copy
            changed = False

            def copy_and_drift(source: Path, target: Path) -> None:
                nonlocal changed
                original_atomic_copy(source, target)
                if not changed:
                    (repo / "seed.npz").write_bytes(b"copy-time-seed-drift")
                    changed = True

            with patch.object(MODULE, "atomic_copy", side_effect=copy_and_drift):
                with self.assertRaisesRegex(MODULE.ArchiveError, "archive_final_prewrite_source_.*drift:seed.npz"):
                    MODULE.materialize_archive(
                        destination=destination, mapping=mapping, payload=payload,
                        archive=self.archive, repo=repo,
                    )
            self.assertFalse(destination.exists())

    def test_host_wrapper_pins_inspected_id_user_and_exact_controller(self) -> None:
        wrapper = Path(__file__).with_name("run_e5_c001_s3ap_phase3_archive.sh").read_text(encoding="utf-8")
        self.assertIn("sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0", wrapper)
        self.assertIn('--user "$(id -u):$(id -g)"', wrapper)
        self.assertIn("e5_c001_s3ap_phase3_archive.py", wrapper)
        self.assertIn('"${ACTUAL_ID}"', wrapper)
        self.assertIn("S3AP_ARCHIVE_CONTROLLER_SHA256", wrapper)
        self.assertIn('open(p,"rb").read()', wrapper)
        self.assertIn('exec(compile(b,p,"exec"),g)', wrapper)
        self.assertNotIn(":latest", wrapper)


if __name__ == "__main__":
    unittest.main()

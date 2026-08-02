from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from scripts.p2_baselines.c1_c2_qualitative_evaluator_backfill_v1.promote_results import (
    ACCEPTED_RECEIPT_RELATIVE,
    ELIGIBILITY,
    HANDOFF_ID,
    PARTIAL_IDS,
    PENDING_REASON,
    TASK_ID,
    promote,
)


REPOSITORY = Path(__file__).resolve().parents[3]
CONFIG_RELATIVE = Path("configs/p2_baselines/c1_c2_qualitative_evaluator_backfill_v1/render_v1.json")


def digest_record(path: str, marker: int) -> dict[str, object]:
    return {"path": path, "bytes": marker + 1, "sha256": hashlib.sha256(f"{path}:{marker}".encode()).hexdigest()}


def external_manifest() -> dict[str, object]:
    representatives = ["DEBY_LOD2_4906981", "DEBY_LOD2_4906982", "DEBY_LOD2_4959314", "DEBY_LOD2_4959327", "DEBY_LOD2_4959461"]
    absent = "DEBY_LOD2_4907183"
    fillers = [f"DEBY_LOD2_{8000000 + index}" for index in range(41)]
    roster = representatives + list(PARTIAL_IDS) + [absent] + fillers
    units = ["C1"] + [f"C2_{index}" for index in range(6)]
    case_sheets = []
    output_rows = []
    for index, building in enumerate(roster):
        if building in representatives:
            role = "OUTCOME_FREE_PRESELECTED_REPRESENTATIVE"
        elif building in PARTIAL_IDS:
            role = "POST_HOC_DIAGNOSTIC_PARTIAL_COVERAGE"
        elif building == absent:
            role = "POST_HOC_DIAGNOSTIC_UNASSOCIATED_C2_EMPTY"
        else:
            role = "FULL_DEVELOPMENT_ROSTER_DESCRIPTIVE"
        filename = f"{building}_fixed_views_v1.png"
        c2_unit = None if building == absent else units[1 + index % 6]
        case_sheets.append({
            "building_id": building,
            "selection_role": role,
            "file": filename,
            "methods": {
                "C1_L_upper": {"operation_unit_id": "C1", "empty_reason": None},
                "C2_MVS": {"operation_unit_id": c2_unit, "empty_reason": "UNASSOCIATED_CONDITION_COMPONENT" if c2_unit is None else None},
            },
        })
        output_rows.append(digest_record(filename, index))
    examples = []
    for label, expected in ELIGIBILITY.items():
        stable_id, candidate, cells, views, mvs, c4, reason = expected
        examples.append({
            "label": label, "stable_id": stable_id, "candidate": candidate,
            "actual_compact_rows": cells, "recorded_reference_cells": cells,
            "current_image_views": views, "mvs_support_cells": mvs, "c4_support_cells": c4,
            "bbox": [0.0, 0.0, 1.0, 1.0], "reason": reason,
        })
    eligibility_file = "eligibility_199_to_72_fixed_cells_v1.png"
    output_rows.append(digest_record(eligibility_file, 100))
    output_rows.append(digest_record("stage_and_coverage_correction_v1.csv", 101))
    unit_reads = {
        unit: {
            key: {**digest_record(f"{unit}/{key}", index), "full_read_and_digest_passes": 1}
            for index, key in enumerate(("input_las", "r_derived", "cityjsonseq"))
        }
        for unit in units
    }
    accepted_records = [
        {"source": "R3", "role": "TEST", **digest_record(f"accepted/{index}", 200 + index)}
        for index in range(25)
    ]
    pending = {
        stage: {
            method: {"status": "PENDING", "value": None, "denominator": 51, "reason": PENDING_REASON}
            for method in ("C1_L_upper", "C2_MVS")
        }
        for stage in ("G2_GEOMETRY_TOPOLOGY_VALID", "G3_ROOF_STRUCTURE_ACCEPTABLE", "G4_GEOMETRIC_ACCURACY_ACCEPTABLE", "PASS_USABLE")
    }
    return {
        "schema": "jointbuildgs.c1_c2_fixed_view_qualitative_manifest.v1",
        "task_id": TASK_ID,
        "status": "POST_HOC_FIXED_RULE_VISUALIZATION_SUPPLEMENT",
        "scientific_verdict": None,
        "case_sheets": case_sheets,
        "input_reads": {
            "artifact_allowlist_record_count": 25, "artifact_allowlist_records": accepted_records,
            "sealed_association_rows": 102, "sealed_execution_unit_rows": 7,
            "unique_execution_units": 7, "associated_render_uses": 101,
            "duplicate_payload_reads_prevented": 94, "units": unit_reads,
        },
        "scope": {
            "metric_recomputation_count": 0, "roofer_invocation_count": 0, "reconstruction_invocation_count": 0,
            "original_scientific_source_reads_or_hashes": 0, "validation_payload_accesses": 0, "held_out_payload_accesses": 0,
        },
        "eligibility": {
            "compact_source_read": {"full_read_and_digest_passes": 1},
            "examples": examples,
            "file": eligibility_file,
        },
        "stage_and_coverage_correction": {
            "g0": {"C1_L_upper": {"numerator": 51, "denominator": 51}, "C2_MVS": {"numerator": 50, "denominator": 51}},
            "g1": {"C1_L_upper": {"numerator": 51, "denominator": 51}, "C2_MVS": {"numerator": 50, "denominator": 51}},
            "pending": pending,
            "coverage_correction": {
                "full": {"numerator": 46, "denominator": 50},
                "partial": {"numerator": 4, "denominator": 50},
                "absent": {"numerator": 1, "denominator": 51},
                "partial_building_ids": list(PARTIAL_IDS), "absent_building_id": absent,
            },
        },
        "outputs": output_rows,
    }


class PromotionTest(unittest.TestCase):
    def test_manifest_only_promotion_creates_exact_four_git_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            external = root / "external"
            config_target = repo / CONFIG_RELATIVE
            config_target.parent.mkdir(parents=True)
            shutil.copyfile(REPOSITORY / CONFIG_RELATIVE, config_target)
            external.mkdir()
            manifest_path = external / "fixed_view_manifest_v1.json"
            external_body = external_manifest()
            manifest_path.write_text(json.dumps(external_body, sort_keys=True) + "\n", encoding="utf-8")
            config = json.loads(config_target.read_text(encoding="utf-8"))
            receipt_records = []
            for row in external_body["input_reads"]["artifact_allowlist_records"]:
                relative = f"phase-payloads/p2-baselines/c1_c2_feasibility_pilot_recovery_r3_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1/{row['path']}"
                receipt_records.append({
                    "uri": f"artifact://JointBuildGS/{relative}", "bytes": row["bytes"], "sha256": row["sha256"],
                    "verification_method": "sha256_rehash", "verified_by": "experiment_host", "verified_at": "2026-08-02T12:00:00+09:00",
                })
            receipt_path = repo / f"artifacts/manifests/handoffs/{HANDOFF_ID}/100-accepted.json"
            receipt_path.parent.mkdir(parents=True)
            receipt_path.write_text(json.dumps({
                "schema": "jointbuildgs.two_host_handoff.v1", "template_only": False,
                "handoff_id": HANDOFF_ID, "task_id": TASK_ID, "state": "accepted", "direction": "work_to_experiment",
                "sender_role": "work_host", "receiver_role": "experiment_host",
                "transport": {"exclusive_writer_ack": True}, "commits": {"receipt_head": "SELF"},
                "receiver_ack": {"role": "experiment_host", "status": "accepted"},
                "verification": {
                    "docker_image_digest": config["project_image_id"],
                    "commands": ["PRE-PUSH EXACT 25-RECORD ALLOWLIST SHA-256", "POST-PUSH EXACT 25-RECORD ALLOWLIST SHA-256"],
                    "tests": [
                        {"name": "exact 25-record pre-push SHA-256 verification", "passed": 25, "failed": 0},
                        {"name": "exact 25-record post-push SHA-256 verification", "passed": 25, "failed": 0},
                    ],
                },
                "artifacts": {"records": receipt_records},
                "scientific": {"scientific_verdict": None},
            }, sort_keys=True) + "\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "fixture"], check=True, capture_output=True)
            head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
            technical = promote(
                external_manifest_path=manifest_path,
                repo_root=repo,
                promotion_parent_commit=head,
                source_commit="1" * 40,
                project_image_id=config["project_image_id"],
                run_id=config["run_id"],
            )
            prefix = repo / "docs/experiments/p2/c1_c2_qualitative_evaluator_backfill_v1"
            with (prefix / "c1_c2_stage_funnel_v1.csv").open(encoding="utf-8", newline="") as stream:
                funnel = list(csv.DictReader(stream))
            with (prefix / "uas_199_to_72_fixed_examples_v1.csv").open(encoding="utf-8", newline="") as stream:
                examples = list(csv.DictReader(stream))
            technical_path = repo / "artifacts/manifests/p2_baselines/c1_c2_qualitative_evaluator_backfill_v1/technical_result_manifest_v1.json"
            self.assertTrue((prefix / "C1_C2_QUALITATIVE_EVALUATOR_SUPPLEMENT_v1.md").is_file())
            self.assertTrue(technical_path.is_file())
            self.assertEqual(len(funnel), 2)
            self.assertEqual([row["denominator"] for row in funnel], ["51", "51"])
            self.assertEqual(len(examples), 7)
            self.assertEqual(technical["unique_execution_units"], 7)
            self.assertEqual(technical["associated_render_uses"], 101)
            self.assertEqual(technical["duplicate_payload_reads_prevented"], 94)
            self.assertEqual(technical["png_rehashes_during_promotion"], 0)
            self.assertEqual(technical["source_scientific_inputs_read"], 0)
            self.assertEqual(technical["accepted_artifact_record_count"], 25)
            self.assertEqual(technical["accepted_sha256_verifications_total"], 50)
            self.assertEqual(technical["accepted_receipt"]["commit"], head)
            self.assertEqual(technical["accepted_receipt"]["path"], f"artifacts/manifests/handoffs/{HANDOFF_ID}/100-accepted.json")
            self.assertEqual(technical["runtime_sealed_derived_hash_only_passes"], 0)
            self.assertEqual(technical["successor_200_300_source_rehashes"], 0)
            self.assertFalse(any(external.glob("*.png")), "promotion must not require PNG files to exist")
            self.assertFalse((repo / "docs/handoffs/returns").exists(), "promotion must not create the Return packet")

            # The accepted counters are receipt-derived: changing the tracked
            # pre-push proof to 24 must fail even when all external outputs and
            # artifact identities remain otherwise identical.
            shutil.rmtree(repo / "docs")
            shutil.rmtree(repo / "artifacts/manifests/p2_baselines")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["verification"]["tests"][0]["passed"] = 24
            receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", ACCEPTED_RECEIPT_RELATIVE], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "invalid receipt fixture"], check=True, capture_output=True)
            invalid_head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
            with self.assertRaisesRegex(RuntimeError, "pre-push proof mismatch"):
                promote(
                    external_manifest_path=manifest_path, repo_root=repo,
                    promotion_parent_commit=invalid_head, source_commit="1" * 40,
                    project_image_id=config["project_image_id"], run_id=config["run_id"],
                )


class WrapperBoundaryTest(unittest.TestCase):
    def test_wrapper_mounts_only_exact_render_sources_then_no_source_promotion(self) -> None:
        script = (REPOSITORY / "scripts/p2_baselines/c1_c2_qualitative_evaluator_backfill_v1/run_backfill_host.sh").read_text(encoding="utf-8")
        self.assertGreaterEqual(script.count("--network none"), 3)
        self.assertIn("exact 25-record pre-push SHA-256 verification", script)
        self.assertIn("exact 25-record post-push SHA-256 verification", script)
        self.assertIn('"${R3_ROOT}:/sealed_r3:ro"', script)
        self.assertIn('"${COMPACT_CELLS}:/bound_inputs/reference_candidate_cells_v1.csv:ro"', script)
        promotion = script.split("# Promotion has no R3", 1)[1]
        self.assertNotIn("${R3_ROOT}:", promotion)
        self.assertNotIn("${COMPACT_CELLS}:", promotion)
        mount_lines = [line for line in script.splitlines() if line.lstrip().startswith("-v ")]
        for prohibited in ("Images.zip", "OPF.zip", "validation", "held_out", "lod1", "lod2", "raw/"):
            self.assertFalse(any(prohibited in line for line in mount_lines), prohibited)


class ArtifactAllowlistTest(unittest.TestCase):
    def test_exact_25_record_allowlist_matches_r4_city_attestation(self) -> None:
        allow = json.loads((REPOSITORY / "configs/p2_baselines/c1_c2_qualitative_evaluator_backfill_v1/artifact_allowlist_v1.json").read_text(encoding="utf-8"))
        records = allow["records"]
        self.assertEqual(allow["record_count"], 25)
        self.assertEqual(len(records), 25)
        self.assertEqual(allow["total_bytes"], 30432763)
        identity = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(allow["record_identity_sha256"], identity)
        self.assertEqual(len({(row["source"], row["path"]) for row in records}), 25)
        self.assertEqual(Counter(row["role"] for row in records), Counter({
            "SEALED_ASSOCIATION_CONTROL": 1, "SEALED_DEVELOPMENT_REFERENCE_CONTROL": 1,
            "SEALED_EXECUTION_UNIT_CONTROL": 1, "DERIVED_OPERATION_LAS": 7,
            "DERIVED_R_DERIVED": 7, "DERIVED_CITYJSONSEQ": 7,
            "BOUND_COMPACT_REFERENCE_CELLS": 1,
        }))
        source = json.loads((REPOSITORY / "configs/p2_baselines/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/r3_finalize_source_manifest_v1.json").read_text(encoding="utf-8"))
        accepted_city = {
            row["path"]: (row["bytes"], row["sha256"])
            for row in source["records"] if row["path"].endswith(".city.jsonl")
        }
        allowed_city = {
            row["path"]: (row["bytes"], row["sha256"])
            for row in records if row["role"] == "DERIVED_CITYJSONSEQ"
        }
        self.assertEqual(allowed_city, accepted_city)
        compact = next(row for row in records if row["role"] == "BOUND_COMPACT_REFERENCE_CELLS")
        self.assertEqual((compact["bytes"], compact["sha256"]), (3785261, "bf87736227ea3c28bc8f966f36e2498f786d2de420a732fa0bfebbb73664275a"))


if __name__ == "__main__":
    unittest.main()

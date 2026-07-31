from __future__ import annotations

import csv
import hashlib
import json
import unittest
from pathlib import Path

from scripts.input_and_alignment.gate_s0.remediation_r1.validate_remediation_evidence import (
    OUTPUT_MANIFEST,
    REQUIRED_OUTPUTS,
    lf_bytes,
    validate_funnel_rows,
)


DOC_ROOT = Path("docs/research/preregistration/gate_s0/remediation_r1")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class RemediationEvidenceTests(unittest.TestCase):
    def test_sparse_source_is_exact_and_integration_remains_partial(self) -> None:
        data = read_json(DOC_ROOT / "sfm_sparse_initialization_v1.json")
        self.assertEqual(data["status"], "READY")
        self.assertEqual(data["integration_replay_status"], "PARTIAL")
        self.assertEqual(data["sparse"]["point_count"], 4_131_648)
        self.assertEqual(data["sparse"]["camera_uid_count"], 937)
        self.assertTrue(data["sparse"]["camera_uids_equal_calibrated_camera_ids"])
        self.assertEqual(len(data["member_records"]), 16)
        self.assertEqual(
            sum(
                item["decompressed_bytes"]
                for item in data["member_records"]
                if item["archive_member"].startswith("opf/sparse/")
            ),
            469_147_486,
        )

    def test_lod1_remains_missing_without_lod2_substitution(self) -> None:
        data = read_json(DOC_ROOT / "lod1_discovery_v1.json")
        self.assertEqual(data["status"], "MISSING")
        self.assertEqual(data["local_artifact_search"]["matches"], [])
        self.assertEqual(data["local_artifact_search"]["inventory_entry_count"], 13)
        candidate = data["official_scope"]["provider_candidates"][0]
        self.assertFalse(candidate["independent_from_scored_lod2"])
        self.assertEqual(candidate["admissibility"], "INADMISSIBLE_AS_INDEPENDENT_C5")
        self.assertIn("Do not simplify", data["prohibited_substitute"])

    def test_reference_lineage_marks_c1_self_reference(self) -> None:
        data = read_json(DOC_ROOT / "evaluation_reference_lineage_v1.json")
        classes = {
            item["condition"]: item["class"]
            for item in data["geometry_reference_candidate"]["condition_overlap_class"]
        }
        self.assertEqual(classes["C1_L_upper"], "SELF_REFERENCE")
        self.assertIn("RoofSurface", data["structure_reference"]["forbidden_input_fields"])
        structure = {
            item["condition"]: item["class"]
            for item in data["structure_reference_overlap_class"]
        }
        self.assertEqual(structure["C2_MVS"], "UNKNOWN")
        self.assertEqual(structure["C3_GS_image"], "UNKNOWN")
        self.assertEqual(structure["C4_GS_lidar_prior"], "UNKNOWN_OR_PARTIALLY_SHARED")
        self.assertIsNone(data["scientific_verdict"])

    def test_funnel_contains_199_outcome_free_stable_ids(self) -> None:
        rows = read_csv(DOC_ROOT / "eligibility_funnel_v2.csv")
        self.assertEqual(len(rows), 199)
        self.assertEqual(len({row["stable_id"] for row in rows}), 199)
        self.assertEqual(len({row["provider_external_id"] for row in rows}), 199)
        self.assertEqual(rows, sorted(rows, key=lambda row: row["stable_id"]))
        stable = "".join(f"{row['stable_id']}\n" for row in rows).encode()
        pairs = "".join(
            f"{row['stable_id']}|{row['provider_external_id']}\n" for row in rows
        ).encode()
        self.assertEqual(
            hashlib.sha256(stable).hexdigest(),
            "047717a5d678aeed540602a2d4fc9a57a076e2ac9205b22a4de75315c1622fe5",
        )
        self.assertEqual(
            hashlib.sha256(pairs).hexdigest(),
            "330598a07840972e1371aa77b21ee42f19065c8c401fa8f1b78b3bb82f6f44da",
        )

    def test_funnel_diagnostics_do_not_become_eligibility(self) -> None:
        rows = read_csv(DOC_ROOT / "eligibility_funnel_v2.csv")
        self.assertEqual(sum(row["c1_numeric_bbox_full_unregistered"] == "true" for row in rows), 187)
        self.assertEqual(sum(row["c2_numeric_bbox_full_unregistered"] == "true" for row in rows), 197)
        self.assertEqual(sum(row["c4_provider_tile_full_unregistered"] == "true" for row in rows), 199)
        self.assertTrue(all(row["c1_eligible"] == "UNKNOWN" for row in rows))
        self.assertTrue(all(row["c2_eligible"] == "UNKNOWN" for row in rows))
        self.assertTrue(all(row["c3_eligible"] == "UNKNOWN" for row in rows))
        self.assertTrue(all(row["c4_eligible"] == "UNKNOWN" for row in rows))
        self.assertTrue(all(row["c5_eligible"] == "false" for row in rows))
        self.assertTrue(all(row["held_out_accessed"] == "false" for row in rows))

    def test_funnel_validator_rejects_per_id_field_drift(self) -> None:
        expected = read_csv(DOC_ROOT / "eligibility_funnel_v2.csv")
        for field, value in (
            ("reference_tile", "LOD2_REFERENCE_WRONG"),
            ("groundsurface_bbox_epsg25832", "0,0,0,0"),
            ("c1_numeric_bbox_full_unregistered", "false"),
            ("exclusion_reason", ""),
            ("held_out_accessed", "true"),
        ):
            with self.subTest(field=field):
                actual = [dict(row) for row in expected]
                actual[0][field] = value
                errors: list[str] = []
                validate_funnel_rows(actual, expected, errors)
                self.assertEqual(
                    errors, ["funnel rows differ from exact live per-ID reconstruction"]
                )

    def test_c2_is_not_overclaimed_as_same_937_base(self) -> None:
        rows = read_csv(DOC_ROOT / "condition_provenance_matrix_v1.csv")
        by_key = {(row["condition"], row["field"]): row for row in rows}
        self.assertEqual(by_key[("C2_MVS", "same_937_image_base")]["status"], "MISSING")
        self.assertIn("1104", by_key[("C2_MVS", "same_937_image_base")]["evidence"])
        self.assertEqual(by_key[("C2_MVS", "interpretation")]["status"], "READY")

    def test_coordinate_matrix_preserves_unknowns(self) -> None:
        rows = read_csv(DOC_ROOT / "coordinate_reference_matrix_v1.csv")
        by_condition = {row["condition"]: row for row in rows}
        self.assertEqual(len(rows), 6)
        self.assertEqual(by_condition["C1_L_upper"]["status"], "PARTIAL")
        self.assertEqual(by_condition["C5_GS_lod1_prior"]["status"], "MISSING")
        self.assertIn("UNKNOWN", by_condition["C1_L_upper"]["vertical_datum"])

    def test_toolchain_records_missing_capabilities(self) -> None:
        data = read_json(DOC_ROOT / "stage3_toolchain_inventory_v1.json")
        commands = {item["command"]: item["status"] for item in data["command_inventory"]}
        self.assertEqual(commands["cjio"], "FOUND")
        for command in ("roofer", "roofer-cli", "cjval", "val3dity", "ogr2ogr", "pdal"):
            self.assertEqual(commands[command], "MISSING")
        self.assertEqual(data["overall_status"], "BLOCKED")
        self.assertFalse(data["thresholds_or_adapter_selected"])

    def test_documents_keep_blocked_proposal_and_null_verdict(self) -> None:
        for path in (
            DOC_ROOT / "REMEDIATION_EVIDENCE_REPORT_v1.md",
            DOC_ROOT / "remediation_issue_log_v1.md",
            Path("docs/handoffs/returns/P2_C2W_GATE_S0_REMEDIATION_R1_RETURN_v1.md"),
        ):
            text = path.read_text(encoding="utf-8")
            self.assertIn("BLOCKED_FOR_GATE_S0_REMEDIATION_REVIEW", text)
            self.assertIn("scientific_verdict: null", text)

    def test_output_manifest_hashes_all_outputs(self) -> None:
        data = read_json(OUTPUT_MANIFEST)
        indexed = {item["path"]: item for item in data["files"]}
        self.assertEqual(set(indexed), {path.as_posix() for path in REQUIRED_OUTPUTS})
        self.assertEqual(len(indexed), 10)
        for path in REQUIRED_OUTPUTS:
            value = lf_bytes(path)
            self.assertEqual(indexed[path.as_posix()]["bytes"], len(value))
            self.assertEqual(indexed[path.as_posix()]["sha256"], hashlib.sha256(value).hexdigest())
        self.assertIsNone(data["scientific_verdict"])


if __name__ == "__main__":
    unittest.main()

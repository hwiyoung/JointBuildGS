from __future__ import annotations

import hashlib
import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.input_and_alignment.gate_s0.common_base_r2a.prepare_r2a_evidence import (
    CONFIG_PATH,
    EVALUATION_CLASS,
    PRIOR_ROLE,
    build_cityjson,
    build_preprocessing_dag,
    cityjsonseq_bytes,
    initialize_ledger,
    process_source_once,
    promote_add_once,
    read_json,
)
from scripts.input_and_alignment.gate_s0.common_base_r2a.validate_r2a_evidence import (
    MANIFEST_ROOT,
    OUTPUT_MANIFEST_PATH,
    REQUIRED_OUTPUTS,
    lf_bytes,
)


GML = b"""<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel
 xmlns:core="http://www.opengis.net/citygml/2.0"
 xmlns:gml="http://www.opengis.net/gml"
 xmlns:bldg="http://www.opengis.net/citygml/building/2.0">
  <core:cityObjectMember>
    <bldg:Building gml:id="DEBY_LOD2_0001">
      <bldg:roofType>1000</bldg:roofType>
      <bldg:boundedBy>
        <bldg:GroundSurface>
          <bldg:lod2MultiSurface>
            <gml:MultiSurface><gml:surfaceMember><gml:Polygon>
              <gml:exterior><gml:LinearRing>
                <gml:posList srsDimension="3">690000 5334000 500 690010 5334000 500 690010 5334010 501 690000 5334010 501 690000 5334000 500</gml:posList>
              </gml:LinearRing></gml:exterior>
            </gml:Polygon></gml:surfaceMember></gml:MultiSurface>
          </bldg:lod2MultiSurface>
        </bldg:GroundSurface>
      </bldg:boundedBy>
      <bldg:boundedBy>
        <bldg:RoofSurface>
          <bldg:lod2MultiSurface>
            <gml:MultiSurface><gml:surfaceMember><gml:Polygon>
              <gml:exterior><gml:LinearRing>
                <gml:posList srsDimension="3">690000 5334000 510 690010 5334000 512 690010 5334010 512 690000 5334010 510 690000 5334000 510</gml:posList>
              </gml:LinearRing></gml:exterior>
            </gml:Polygon></gml:surfaceMember></gml:MultiSurface>
          </bldg:lod2MultiSurface>
        </bldg:RoofSurface>
      </bldg:boundedBy>
    </bldg:Building>
  </core:cityObjectMember>
</core:CityModel>
"""


class R2AEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = read_json(CONFIG_PATH)

    def test_initial_ledger_precedes_external_payload_and_has_zero_reuse_bytes(self) -> None:
        ledger = initialize_ledger(self.config)
        self.assertTrue(ledger["initialized_before_external_payload_access"])
        self.assertFalse(ledger["payload_operations_started"])
        self.assertFalse(ledger["completed"])
        by_name = {item["name"]: item for item in ledger["operations"]}
        self.assertEqual(by_name["closed_r1_input_bundle_attestation"]["status"], "REUSED")
        self.assertEqual(by_name["closed_r1_input_bundle_attestation"]["read_bytes"], 0)
        self.assertEqual(by_name["closed_r1_input_bundle_attestation"]["hashed_bytes"], 0)
        self.assertEqual(len({item["identity"]["operation_id"] for item in ledger["operations"]}), len(ledger["operations"]))

    def test_shared_dag_keeps_missing_decisions_null(self) -> None:
        dag = build_preprocessing_dag(self.config)
        self.assertEqual(dag["arm_specific_duplicate_generation"], "INVALID")
        self.assertIsNone(dag["component_enablement"])
        self.assertIsNone(dag["mvs_algorithm"])
        self.assertIsNone(dag["gs_loss"])
        self.assertIsNone(dag["adapter"])
        self.assertIsNone(dag["threshold"])
        by_id = {item["node_id"]: item for item in dag["nodes"]}
        for component in ("dense_mvs", "depth", "normal", "confidence"):
            self.assertEqual(by_id[component]["status"], "MISSING")
            self.assertFalse(by_id[component]["execution_identity_final"])

    def test_single_stream_digest_and_lod1_simplification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.gml"
            path.write_bytes(GML)
            source = {
                "tile_id": "690_5334",
                "asset_id": "LOD2_REFERENCE_TEST",
                "uri": "artifact://JointBuildGS/test/source.gml",
                "bytes": len(GML),
                "sha256": hashlib.sha256(GML).hexdigest(),
            }
            records, stream = process_source_once(path, source)
        self.assertEqual(stream["bytes"], len(GML))
        self.assertEqual(stream["sha256"], hashlib.sha256(GML).hexdigest())
        self.assertEqual(stream["full_byte_passes"], 1)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["stable_building_id"], "DEBY_LOD2_0001")
        self.assertEqual(record["ground_height_m"], 500.0)
        self.assertEqual(record["top_height_m"], 512.0)
        self.assertEqual(record["prior_role"], PRIOR_ROLE)
        self.assertEqual(record["evaluation_class"], EVALUATION_CLASS)
        self.assertFalse(record["primary_c5_eligible"])
        for forbidden in ("roofType", "roof_slope", "ridge", "face_adjacency"):
            self.assertNotIn(forbidden, record)
        for removed in ("roof_slope", "ridge", "face_adjacency", "roof_type"):
            self.assertIn(removed, record["removed_information"])

    def test_cityjsonseq_is_deterministic_roundtrippable_and_has_no_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.gml"
            path.write_bytes(GML)
            source = {
                "tile_id": "690_5334",
                "asset_id": "LOD2_REFERENCE_TEST",
                "uri": "artifact://JointBuildGS/test/source.gml",
                "bytes": len(GML),
                "sha256": hashlib.sha256(GML).hexdigest(),
            }
            records, _stream = process_source_once(path, source)
        first, first_check = cityjsonseq_bytes(records)
        second, second_check = cityjsonseq_bytes(records)
        self.assertEqual(first, second)
        self.assertEqual(first_check, second_check)
        self.assertTrue(first_check["parsed"])
        lines = [json.loads(line) for line in first.decode().splitlines()]
        self.assertEqual(lines[0]["type"], "CityJSON")
        self.assertEqual(lines[1]["type"], "CityJSONFeature")
        geometry = lines[1]["CityObjects"]["DEBY_LOD2_0001"]["geometry"][0]
        self.assertEqual(geometry["type"], "MultiSolid")
        self.assertEqual(geometry["lod"], "1")
        self.assertNotIn("semantics", geometry)
        model = build_cityjson(records)
        self.assertNotIn("roofType", json.dumps(model))

    def test_add_once_is_noop_for_exact_identity_and_blocks_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            namespace = Path(directory) / "P2-GATE-S0-EVIDENCE-R2A-v1"
            payloads = {"a.jsonl": b"one\n", "b.jsonl": b"two\n"}
            status, records = promote_add_once(namespace, payloads)
            self.assertEqual(status, "EXECUTED_ADD_ONCE")
            self.assertEqual(len(records), 2)
            status, _records = promote_add_once(namespace, payloads)
            self.assertEqual(status, "REUSED")
            with self.assertRaisesRegex(RuntimeError, "BLOCKED_NAMESPACE_CONFLICT"):
                promote_add_once(namespace, {**payloads, "a.jsonl": b"changed\n"})
            self.assertEqual(
                sorted(path.name for path in Path(directory).iterdir()),
                ["P2-GATE-S0-EVIDENCE-R2A-v1"],
            )

    def test_config_keeps_forbidden_work_disabled(self) -> None:
        guards = self.config["guards"]
        self.assertEqual(guards["performance_authority"], "NONE")
        self.assertFalse(guards["held_out_access"])
        self.assertFalse(guards["fusion_w1_access"])
        self.assertFalse(guards["r_ext_access"])
        self.assertFalse(guards["generate_missing_common_derivatives"])
        self.assertFalse(guards["overwrite_existing_external_paths"])
        self.assertFalse(guards["delete_existing_external_paths"])

    def test_compact_replay_derivative_and_diagnostic_results(self) -> None:
        replay = read_json(MANIFEST_ROOT / "source_candidate_replay_v1.json")
        self.assertEqual(replay["counts"]["image_members"], 962)
        self.assertEqual(replay["counts"]["included_image_pose_pairs"], 937)
        self.assertEqual(replay["counts"]["excluded_no_pose"], 25)
        self.assertTrue(all(replay["checks"].values()))
        matrix = read_json(MANIFEST_ROOT / "derivative_provenance_matrix_v1.json")
        statuses = {item["component"]: item["status"] for item in matrix["components"]}
        self.assertEqual(
            statuses,
            {
                "sfm_sparse": "REUSED_EXACT",
                "dense_mvs": "AMBIGUOUS",
                "depth": "MISSING",
                "normal": "MISSING",
                "confidence": "MISSING",
            },
        )
        self.assertFalse(matrix["missing_derivatives_generated"])
        diagnostic = read_json(
            MANIFEST_ROOT / "lod2_derived_lod1_diagnostic_manifest_v1.json"
        )
        self.assertEqual(diagnostic["combined_building_count"], 12_049)
        self.assertEqual(diagnostic["combined_stable_id_unique_count"], 12_049)
        self.assertFalse(diagnostic["primary_c5_eligible"])
        self.assertFalse(diagnostic["performance_scored"])
        self.assertFalse(diagnostic["e_paired_promoted"])
        self.assertIsNone(diagnostic["scientific_verdict"])

    def test_lineage_labels_every_stable_building_diagnostic_only(self) -> None:
        path = MANIFEST_ROOT / "lod2_derived_lod1_lineage_v1.csv"
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 12_049)
        self.assertEqual(len({row["stable_building_id"] for row in rows}), 12_049)
        self.assertTrue(all(row["prior_role"] == PRIOR_ROLE for row in rows))
        self.assertTrue(
            all(row["evaluation_class"] == EVALUATION_CLASS for row in rows)
        )
        self.assertTrue(all(row["primary_c5_eligible"] == "false" for row in rows))

    def test_output_manifest_hashes_required_git_outputs(self) -> None:
        manifest = read_json(OUTPUT_MANIFEST_PATH)
        indexed = {item["path"]: item for item in manifest["files"]}
        self.assertEqual(set(indexed), {path.as_posix() for path in REQUIRED_OUTPUTS})
        for path in REQUIRED_OUTPUTS:
            value = lf_bytes(path)
            self.assertEqual(indexed[path.as_posix()]["bytes"], len(value))
            self.assertEqual(
                indexed[path.as_posix()]["sha256"], hashlib.sha256(value).hexdigest()
            )
        self.assertIsNone(manifest["scientific_verdict"])


if __name__ == "__main__":
    unittest.main()

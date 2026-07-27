#!/usr/bin/env python3
"""Contract tests for the generic per-job qualitative v3 publisher."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1_aprime_job_qualitative_v3_20260727.py"
)
SPEC = importlib.util.spec_from_file_location("fusion_w1_aprime_job_qualitative_v3", MODULE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot import {MODULE_PATH}")
qualitative = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = qualitative
SPEC.loader.exec_module(qualitative)


SMOKE_IDENTITY = ("DEBY_LOD2_42364609", "Aprime", "r1")


class JobQualitativeV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = qualitative.load_config()
        cls.report = qualitative.load_report_module(cls.config)
        cls.evidence = qualitative.resolve_evidence(
            cls.config, cls.report, *SMOKE_IDENTITY
        )

    def test_fixed_hook_schema_identity_and_output_path(self) -> None:
        self.assertEqual(
            qualitative.RECEIPT_SCHEMA,
            "jointbuildgs.fusion_w1_aprime.job_qualitative.complete.v3",
        )
        expected = {
            "run_id": "20260726_fusion_w1_aprime",
            "building_id": "DEBY_LOD2_42364609",
            "arm": "Aprime",
            "replicate": "r1",
        }
        self.assertEqual(self.evidence["identity"], expected)
        output = qualitative.output_job_dir(
            self.config, *SMOKE_IDENTITY, output_root=None
        )
        self.assertEqual(
            qualitative.display_path(output),
            "phases/p2-gsjso/runs/20260726_fusion_w1_aprime/review_v3/"
            "by_building/DEBY_LOD2_42364609/arm_Aprime/r1",
        )

    def test_A_to_I_contract_is_bilingual_and_placeholder_free(self) -> None:
        visual = self.config["visual_contract"]
        self.assertEqual(tuple(visual["component_order"]), tuple("ABCDEFGHI"))
        self.assertFalse(visual["placeholders_allowed_for_measured"])
        self.assertEqual(
            tuple(item["key"] for item in visual["components"]), tuple("ABCDEFGHI")
        )
        for component in visual["components"]:
            self.assertTrue(component["title_ko"])
            self.assertTrue(component["title_en"])
            self.assertIn("범례/Legend:", component["legend_bilingual"])
        overlay = visual["components"][7]
        self.assertIn("평가 전용", overlay["title_ko"])
        self.assertIn("evaluation only", overlay["title_en"])
        panel_a = visual["components"][0]
        self.assertIn("지붕 실루엣", panel_a["title_ko"])
        self.assertIn("roof silhouette", panel_a["title_en"])
        self.assertIn("평면 footprint 아님", panel_a["legend_bilingual"])
        self.assertEqual(
            panel_a["geometry_semantics"],
            "target roof silhouette M_j; not a planimetric footprint",
        )

    def test_real_smoke_sources_resolve_all_nine_components(self) -> None:
        inspection = self.evidence["inspection"]
        self.assertGreater(inspection["input_view"]["mask_pixels_n"], 0)
        self.assertGreater(inspection["seed"]["points_n"], 2)
        self.assertGreater(inspection["tsdf_mesh"]["points_n"], 2)
        self.assertGreater(inspection["tsdf_mesh"]["faces_n"], 0)
        self.assertEqual(
            inspection["tsdf_mesh"]["rendered_as"], "triangle_faces_top_view"
        )
        self.assertGreater(inspection["tsdf_surface_samples"]["points_n"], 2)
        self.assertGreater(inspection["canonical_roofer_cityjson"]["rings_n"], 0)
        self.assertGreater(inspection["evaluation_only_reference_gml"]["rings_n"], 0)
        self.assertEqual(inspection["opacity"]["state"], "measured")
        self.assertGreaterEqual(inspection["opacity"]["maximum_iteration"], 20000)

    def test_cityjson_is_canonical_and_citygml_is_explicitly_unavailable(self) -> None:
        capability = self.evidence["serialization_capability"]
        self.assertEqual(capability["state"], "CENSORED")
        self.assertEqual(capability["availability"], "UNAVAILABLE")
        self.assertFalse(capability["generation_attempted"])
        self.assertIsNone(capability["generated_artifact"])
        self.assertFalse(capability["cjio"]["citygml_or_gml_export_supported"])
        self.assertEqual(
            capability["cjio"]["observed_export_formats"],
            ["b3dm", "glb", "jsonl", "obj", "stl"],
        )
        self.assertFalse(
            capability["repo_exporter"]["cityjson_to_citygml_serializer_present"]
        )
        self.assertEqual(
            qualitative.load_json(self.evidence["cityjson_path"])["type"], "CityJSON"
        )

    def test_nonmeasured_readout_is_rejected_before_artifact_resolution(self) -> None:
        tampered = copy.deepcopy(self.config)
        with tempfile.TemporaryDirectory() as temporary:
            complete = Path(temporary) / "complete.json"
            complete.write_text(
                json.dumps(
                    {
                        "schema": "jointbuildgs.fusion_w1_aprime.readout.complete.v1",
                        "state": "COMPLETE",
                        "identity": {
                            "building_id": SMOKE_IDENTITY[0],
                            "arm": SMOKE_IDENTITY[1],
                            "replicate": SMOKE_IDENTITY[2],
                        },
                        "primary": {
                            "measurement_status": "NOT_MEASURED",
                            "assembly_status": "NOT_ASSEMBLED",
                        },
                        "interpretation_or_verdict": None,
                    }
                ),
                encoding="utf-8",
            )
            tampered["sources"]["canonical_readout_complete_template"] = str(
                Path(temporary) / "absent/{building_id}/{arm}/{replicate}/complete.json"
            )
            tampered["sources"]["readout_complete_overrides"] = {
                "DEBY_LOD2_42364609/arm_Aprime/r1": str(complete)
            }
            with self.assertRaisesRegex(
                qualitative.JobQualitativeError, "primary MEASURED"
            ):
                qualitative.resolve_evidence(
                    tampered, self.report, *SMOKE_IDENTITY
                )

    def test_temp_publish_is_complete_atomic_and_source_preserving(self) -> None:
        source_before = qualitative.current_source_snapshot(self.evidence)
        with tempfile.TemporaryDirectory(prefix="job-qualitative-v3-test-") as temporary:
            output_root = Path(temporary) / "review-v3"
            production_root = qualitative.repo_path(self.config["outputs"]["root"])
            self.assertFalse(qualitative.is_within(output_root, production_root))
            receipt = qualitative.publish_job(
                self.config,
                self.report,
                *SMOKE_IDENTITY,
                output_root=output_root,
            )
            self.assertEqual(receipt["schema"], qualitative.RECEIPT_SCHEMA)
            self.assertEqual(receipt["state"], "COMPLETE")
            self.assertEqual(receipt["measurement_state"], "MEASURED")
            self.assertEqual(receipt["components"], {key: True for key in "ABCDEFGHI"})
            self.assertEqual(receipt["placeholder_count"], 0)
            self.assertEqual(receipt["citygml_export"]["state"], "CENSORED")
            self.assertEqual(receipt["citygml_export"]["availability"], "UNAVAILABLE")
            self.assertTrue(
                receipt["canonical_roofer_cityjson"]["byte_identical_copy"]
            )
            job = qualitative.output_job_dir(
                self.config, *SMOKE_IDENTITY, output_root=output_root
            )
            self.assertEqual(
                {path.name for path in job.iterdir()},
                {"panel.png", "opacity.csv", "roofer.city.json", "complete.json"},
            )
            verified = qualitative.verify_bundle(
                self.config, *SMOKE_IDENTITY, output_root=output_root
            )
            self.assertEqual(verified["outputs"], receipt["outputs"])
        self.assertEqual(
            qualitative.current_source_snapshot(self.evidence), source_before
        )

    def test_existing_complete_bundle_rejects_stale_sources_and_implementation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="job-qualitative-v3-stale-") as temporary:
            output_root = Path(temporary) / "review-v3"
            receipt = qualitative.publish_job(
                self.config,
                self.report,
                *SMOKE_IDENTITY,
                output_root=output_root,
            )
            receipt_path = qualitative.output_job_dir(
                self.config, *SMOKE_IDENTITY, output_root=output_root
            ) / self.config["outputs"]["complete"]

            def write_receipt(value: dict) -> None:
                receipt_path.write_text(
                    json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

            stale_source = copy.deepcopy(receipt)
            stale_source["source_records"]["pretraining_seed"]["sha256"] = "0" * 64
            write_receipt(stale_source)
            with self.assertRaisesRegex(
                qualitative.JobQualitativeError, "receipt source pretraining_seed sha256 drift"
            ):
                qualitative.publish_job(
                    self.config,
                    self.report,
                    *SMOKE_IDENTITY,
                    output_root=output_root,
                )

            stale_readout = copy.deepcopy(receipt)
            stale_readout["source_records"]["readout_complete"] = copy.deepcopy(
                receipt["source_records"]["attempt"]
            )
            stale_readout["source_readout_complete"] = copy.deepcopy(
                receipt["source_records"]["attempt"]
            )
            write_receipt(stale_readout)
            with self.assertRaisesRegex(
                qualitative.JobQualitativeError,
                "source readout is not the current readout complete",
            ):
                qualitative.publish_job(
                    self.config,
                    self.report,
                    *SMOKE_IDENTITY,
                    output_root=output_root,
                )

            stale_implementation = copy.deepcopy(receipt)
            stale_implementation["implementation"][0]["sha256"] = "f" * 64
            write_receipt(stale_implementation)
            with self.assertRaisesRegex(
                qualitative.JobQualitativeError,
                "implementation does not match current implementation hashes",
            ):
                qualitative.publish_job(
                    self.config,
                    self.report,
                    *SMOKE_IDENTITY,
                    output_root=output_root,
                )

            write_receipt(receipt)
            verified = qualitative.publish_job(
                self.config,
                self.report,
                *SMOKE_IDENTITY,
                output_root=output_root,
            )
            self.assertEqual(verified["outputs"], receipt["outputs"])

    def test_wrapper_is_fixed_cpu_only_hook_with_temp_smoke(self) -> None:
        wrapper_path = (
            REPO
            / "phases/p2-gsjso/scripts/"
            "run_fusion_w1_aprime_job_qualitative_v3_20260727.sh"
        )
        wrapper = wrapper_path.read_text(encoding="utf-8")
        self.assertIn("one)", wrapper)
        self.assertIn("one <building_id> <arm> <replicate>", wrapper)
        self.assertIn("--network=none", wrapper)
        self.assertIn("--read-only", wrapper)
        self.assertIn('--user "$(id -u):$(id -g)"', wrapper)
        self.assertIn('--volume "$REPO_ROOT:$CONTAINER_REPO:ro"', wrapper)
        self.assertIn("EXPECTED_IMAGE_ID=", wrapper)
        self.assertIn("EXPECTED_FONT_SHA256=", wrapper)
        self.assertIn("smoke-temp)", wrapper)
        self.assertIn("mktemp -d", wrapper)
        self.assertNotIn("--gpus", wrapper)
        self.assertNotIn("src.stage2.train", wrapper)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Focused unit tests for the S3-A 07-14 ID-map/class supplement."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image as PILImage


SCRIPT = Path(__file__).with_name("e5_c001_s3_idmap_class_supplement.py")
SPEC = importlib.util.spec_from_file_location("e5_c001_s3_idmap_class_supplement", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
SUPPLEMENT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SUPPLEMENT
SPEC.loader.exec_module(SUPPLEMENT)


class AgreementMaskTest(unittest.TestCase):
    def test_one_pixel_band_excludes_exactly_one_pixel_each_side(self) -> None:
        mask = np.zeros((5, 8), dtype=bool)
        mask[:, :4] = True
        band = SUPPLEMENT.one_pixel_transition_band(mask)
        columns = np.flatnonzero(np.any(band, axis=0)).tolist()
        self.assertEqual(columns, [3, 4])
        counts = SUPPLEMENT.agreement_counts(mask, mask)
        self.assertEqual(counts["boundary_excluded_pixels"], 10)
        self.assertEqual(counts["false_positive_pixels"], 0)
        self.assertEqual(counts["false_negative_pixels"], 0)
        self.assertEqual(SUPPLEMENT.agreement_metrics(counts)["binary_agreement"], 1.0)

    def test_large_interior_disagreement_survives_boundary_exclusion(self) -> None:
        fixed = np.zeros((15, 15), dtype=bool)
        fixed[2:13, 2:13] = True
        id_roof = fixed.copy()
        id_roof[5:10, 5:10] = False
        counts = SUPPLEMENT.agreement_counts(fixed, id_roof)
        # The 5x5 hole has a one-pixel excluded rim; its 3x3 core remains a mismatch.
        self.assertEqual(counts["false_negative_pixels"], 9)
        self.assertEqual(counts["false_positive_pixels"], 0)
        self.assertLess(SUPPLEMENT.agreement_metrics(counts)["roof_iou"], 1.0)

    def test_building_domain_adds_its_own_boundary_exclusion(self) -> None:
        fixed = np.ones((9, 12), dtype=bool)
        id_roof = fixed.copy()
        support = np.zeros_like(fixed)
        support[:, 3:9] = True
        counts = SUPPLEMENT.agreement_counts(
            fixed, id_roof, domain=support, extra_boundary_masks=(support,)
        )
        # The support's columns 3 and 8 are the one-pixel inside boundary.
        self.assertEqual(counts["domain_pixels"], 54)
        self.assertEqual(counts["boundary_excluded_pixels"], 18)
        self.assertEqual(counts["evaluable_pixels"], 36)


class ReplayValidationTest(unittest.TestCase):
    @staticmethod
    def inventory() -> dict[str, str]:
        return {
            "actual_source_class_mismatch_pixels": "0",
            "actual_source_class_agreement": "1.0",
            "actual_source_roof_iou": "1.0",
        }

    def test_pixel_replay_difference_is_recorded_not_rejected(self) -> None:
        fixed = np.ones((6, 6), dtype=np.uint8)
        replay = fixed.copy()
        replay[2, 2] = 2
        bidmap = np.zeros((6, 6), dtype=np.int32)
        audit = SUPPLEMENT.actual_source_replay_audit(
            fixed,
            replay,
            bidmap,
            self.inventory(),
            mesh_building_count=1,
        )
        self.assertEqual(audit["actual_source_class_mismatch_pixels_inventory"], 0)
        self.assertEqual(audit["actual_source_class_mismatch_pixels_replay"], 1)
        self.assertEqual(
            audit["actual_source_class_mismatch_pixels_delta_replay_minus_inventory"], 1
        )
        self.assertFalse(audit["actual_source_replay_inventory_exact_match"])
        self.assertEqual(
            audit[
                "actual_source_roof_membership_mismatch_boundary_excluded_pixels_replay"
            ],
            1,
        )
        self.assertEqual(
            audit["actual_source_roof_membership_mismatch_evaluable_pixels_replay"], 0
        )

    def test_structurally_invalid_class_id_replay_still_fails_closed(self) -> None:
        fixed = np.ones((4, 4), dtype=np.uint8)
        replay = fixed.copy()
        bidmap = np.zeros((4, 4), dtype=np.int32)
        bidmap[0, 0] = -1
        with self.assertRaisesRegex(RuntimeError, "class/hit"):
            SUPPLEMENT.actual_source_replay_audit(
                fixed,
                replay,
                bidmap,
                self.inventory(),
                mesh_building_count=1,
            )


class ContractTest(unittest.TestCase):
    @staticmethod
    def manifest() -> dict:
        digest = "a" * 64
        buildings = [f"B{i:02d}" for i in range(18)]
        return {
            "run_id": SUPPLEMENT.EXPECTED_RUN_ID,
            "script": SUPPLEMENT.rel(SUPPLEMENT.PRODUCER),
            "script_sha256": digest,
            "container_image": "jointbuildgs:dev",
            "container_image_id": "sha256:" + digest,
            "inputs": {
                "arm1p_candidate_buildings_assignment_order": buildings,
                "hashes": {"input": digest},
            },
            "locks": {
                "crs": "EPSG:25832",
                "source_component_connectivity": 8,
                "source_component_min_pixels": 256,
                "cutline_half_width_px": 7,
                "loss_address_mode": "oracle_class_plus_raycast_building_id",
                "raycast_building_id_loss_role": "region address only",
                "l_nb_boundary_source": "class boundary only; no instance cutline",
                "loss_value_contract": {
                    "lod2_depth_or_height_loss_input": False,
                    "raycast_hit_distance_stored": False,
                    "raycast_intersection_xyz_stored": False,
                },
            },
            "datum_provenance": {
                "actual_label_source": {
                    "geoid_m": 48.0,
                    "shift_z_m": 556.0,
                    "building_id_role": "region address only",
                }
            },
            "oracle_id_address_aggregate": {
                "provenance": "actual_label_source_legacy48p0_oracle_address",
                "building_id_is_loss_input": True,
                "loss_role": "region address only",
                "lod2_depth_or_height_loss_input": False,
                "totals": {"wrong": 0},
            },
            "outputs": {
                "cache_files": 428,
                "priority_crop_count": 9,
                "priority_contact_sheet_count": 1,
                "output_sha256": {},
            },
        }

    def test_manifest_contract_rejects_actual_source_datum_drift(self) -> None:
        manifest = self.manifest()
        SUPPLEMENT.validate_manifest_fields(manifest)
        drifted = copy.deepcopy(manifest)
        drifted["datum_provenance"]["actual_label_source"]["shift_z_m"] = 558.3
        with self.assertRaisesRegex(RuntimeError, "actual-source shift changed"):
            SUPPLEMENT.validate_manifest_fields(drifted)

    def test_priority_contract_is_exact_nine_over_six_unique_views(self) -> None:
        view_by_key = {
            (0, 1): "v0",
            (0, 2): "v1",
            (0, 3): "v2",
            (1, 1): "v0",
            (1, 2): "v3",
            (1, 3): "v2",
            (2, 1): "v0",
            (2, 2): "v4",
            (2, 3): "v5",
        }
        artifacts = []
        for building_index, building_id in enumerate(SUPPLEMENT.REGIONS.TEXTURELESS3):
            for rank in (1, 2, 3):
                stem = view_by_key[(building_index, rank)]
                artifacts.extend(
                    [
                        {
                            "kind": "full_overlay",
                            "building_id": building_id,
                            "view_stem": stem,
                            "path": f"full_{building_index}_{rank}.png",
                        },
                        {
                            "kind": "priority_crop",
                            "building_id": building_id,
                            "view_stem": stem,
                            "rank": rank,
                            "path": f"crop_{building_index}_{rank}.png",
                            "crop_box_xyxy": [0, 0, 10, 10],
                        },
                    ]
                )
        artifacts.append({"kind": "priority_contact_sheet", "path": "sheet.png"})
        priority, _full, _contact = SUPPLEMENT.validate_priority_artifact_contract(artifacts)
        self.assertEqual(len(priority), 9)
        self.assertEqual(len({row["view_stem"] for row in priority}), 6)
        broken = copy.deepcopy(artifacts)
        next(row for row in broken if row.get("kind") == "priority_crop")["view_stem"] = "v6"
        with self.assertRaisesRegex(RuntimeError, "six"):
            SUPPLEMENT.validate_priority_artifact_contract(broken)


class GalleryTest(unittest.TestCase):
    @staticmethod
    def artifact() -> dict:
        return {
            "building_id": "DEBY_LOD2_8568392",
            "rank": 2,
            "view_stem": "DJI_20241217095439_0022_D",
            "path": "frozen.png",
            "crop_box_xyxy": [0, 0, 20, 20],
            "support_label": "P_ref support: 955 px (>=64)",
            "selected_low_support_count": 1,
            "target_touches_frame": True,
        }

    @staticmethod
    def gate_row() -> dict[str, str]:
        return {
            "boundary_offset_px": "1.0",
            "boundary_offset_m": "0.1",
            "boundary_offset_defined": "True",
            "boundary_offset_status": "defined",
            "iou": "0.5",
            "fragment_count_ge64": "1",
        }

    def test_boundary_paint_and_contact_sheet_are_deterministic_shapes(self) -> None:
        base = PILImage.new("RGB", (20, 20), (0, 0, 0))
        mask = np.zeros((20, 20), dtype=bool)
        mask[4:16, 4:16] = True
        painted, line = SUPPLEMENT.paint_id_boundary(base, mask)
        pixels = np.asarray(painted)
        self.assertGreater(int(line.sum()), 0)
        self.assertTrue(
            np.all(pixels[line] == np.asarray(SUPPLEMENT.ID_BOUNDARY_COLOR_RGB))
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            crops = {}
            for building_id in SUPPLEMENT.REGIONS.TEXTURELESS3:
                for rank in (1, 2, 3):
                    path = root / f"{building_id}_{rank}.png"
                    PILImage.new("RGB", (80, 60), (rank * 40, 20, 20)).save(path)
                    crops[(building_id, rank)] = path
            out = root / "sheet.png"
            sheet = SUPPLEMENT.make_contact_sheet(crops, out)
            self.assertEqual(sheet.size, (1440, 1188))
            self.assertTrue(out.is_file())

    def test_present_target_keeps_real_boundary_painted_and_counted(self) -> None:
        base = PILImage.new("RGB", (20, 20), (0, 0, 0))
        mask = np.zeros((20, 20), dtype=bool)
        mask[4:16, 4:16] = True
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "present.png"
            record = SUPPLEMENT.render_priority_crop_with_id_boundary(
                out,
                base,
                mask,
                self.artifact(),
                self.gate_row(),
            )
            self.assertEqual(
                record["target_id_status"],
                "target_id_boundary_visible_in_frozen_crop",
            )
            self.assertGreater(record["target_id_pixels_full"], 0)
            self.assertGreater(record["target_id_boundary_pixels_crop"], 0)
            self.assertGreater(record["target_id_painted_line_pixels_crop"], 0)
            self.assertFalse(record["boundary_fabricated"])
            self.assertTrue(out.is_file())

    def test_missing_target_preserves_crop_and_annotates_without_boundary(self) -> None:
        base = PILImage.new("RGB", (20, 20), (12, 34, 56))
        mask = np.zeros((20, 20), dtype=bool)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "missing.png"
            record = SUPPLEMENT.render_priority_crop_with_id_boundary(
                out,
                base,
                mask,
                self.artifact(),
                self.gate_row(),
            )
            self.assertEqual(record["target_id_status"], "target_id_not_raycast_visible")
            self.assertEqual(record["target_id_annotation"], SUPPLEMENT.TARGET_ID_NOT_VISIBLE_LABEL)
            for field in (
                "target_id_pixels_full",
                "target_id_pixels_crop",
                "target_id_boundary_pixels_full",
                "target_id_boundary_pixels_crop",
                "target_id_painted_line_pixels_full",
                "target_id_painted_line_pixels_crop",
            ):
                self.assertEqual(record[field], 0)
            self.assertFalse(record["boundary_fabricated"])
            summary = SUPPLEMENT.summarize_priority_gallery([record])
            self.assertEqual(
                summary["status_counts"], {"target_id_not_raycast_visible": 1}
            )
            self.assertEqual(summary["target_id_pixels_full_sum"], 0)
            self.assertEqual(summary["target_id_boundary_pixels_crop_sum"], 0)
            self.assertEqual(summary["boundary_fabricated_count"], 0)
            with PILImage.open(out) as image:
                rendered = np.asarray(image.convert("RGB"))
            # The frozen 20x20 crop is centred below the 108 px annotation header.
            body = rendered[108:128, 315:335]
            self.assertTrue(np.all(body == np.asarray([12, 34, 56], dtype=np.uint8)))


class DurableOutputManifestTest(unittest.TestCase):
    def test_manifest_hashes_complete_bundle_without_self_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staged_csv = root / "agreement.csv"
            SUPPLEMENT._write_csv(
                staged_csv,
                [{} for _ in range(SUPPLEMENT.EXPECTED_VIEWS + 1 + 18)],
            )
            staged_crops = {}
            records = []
            index = 0
            for building_id in SUPPLEMENT.REGIONS.TEXTURELESS3:
                for rank in (1, 2, 3):
                    path = root / f"crop_{index}.png"
                    PILImage.new("RGB", (10, 10), (index, 0, 0)).save(path)
                    key = (building_id, rank)
                    staged_crops[key] = path
                    visible = index != 4
                    records.append(
                        {
                            "building_id": building_id,
                            "rank": rank,
                            "view_stem": f"view_{index}",
                            "path": f"docs/crop_{index}.png",
                            "target_id_status": (
                                "target_id_boundary_visible_in_frozen_crop"
                                if visible
                                else "target_id_not_raycast_visible"
                            ),
                            "target_id_pixels_full": 100 if visible else 0,
                            "target_id_pixels_crop": 50 if visible else 0,
                            "target_id_boundary_pixels_full": 20 if visible else 0,
                            "target_id_boundary_pixels_crop": 10 if visible else 0,
                            "target_id_painted_line_pixels_full": 40 if visible else 0,
                            "target_id_painted_line_pixels_crop": 20 if visible else 0,
                            "boundary_fabricated": False,
                            "sha256": SUPPLEMENT.REGIONS.sha256_file(path),
                        }
                    )
                    index += 1
            summary = SUPPLEMENT.summarize_priority_gallery(records)
            self.assertEqual(summary["boundary_visible_crop_count"], 8)
            self.assertEqual(summary["not_raycast_visible_crop_count"], 1)
            staged_contact = root / "contact.png"
            PILImage.new("RGB", (20, 20), (1, 2, 3)).save(staged_contact)
            contact_record = {
                "kind": "priority_contact_sheet",
                "path": "docs/contact.png",
                "target_id_summary": summary,
                "boundary_fabricated": False,
                "sha256": SUPPLEMENT.REGIONS.sha256_file(staged_contact),
            }
            input_hash_set = {"source": "a" * 64}
            context = {
                "manifest_path": SUPPLEMENT.DEFAULT_MANIFEST,
                "manifest_sha256": "b" * 64,
                "input_hash_set": input_hash_set,
                "manifest_input_hash_set_sha256": SUPPLEMENT.REGIONS.sha256_json(
                    input_hash_set
                ),
            }
            gallery_hash = SUPPLEMENT.REGIONS.sha256_json([*records, contact_record])
            payload = SUPPLEMENT.build_durable_output_manifest(
                context,
                staged_csv=staged_csv,
                crop_records=records,
                contact_record=contact_record,
                target_id_summary=summary,
                gallery_output_set_sha256=gallery_hash,
                supplement_script_sha256="c" * 64,
            )
            SUPPLEMENT.validate_staged_output_bundle(
                payload,
                staged_csv=staged_csv,
                staged_crops=staged_crops,
                staged_contact=staged_contact,
            )
            artifact_set = payload["outputs"]["artifact_set"]
            self.assertTrue(payload["outputs"]["artifact_set_excludes_manifest"])
            self.assertNotIn(
                SUPPLEMENT.rel(SUPPLEMENT.OUTPUT_MANIFEST),
                str(artifact_set),
            )
            self.assertEqual(
                payload["outputs"]["output_set_sha256"],
                SUPPLEMENT.REGIONS.sha256_json(artifact_set),
            )
            self.assertEqual(payload["boundary_fabricated_count"], 0)
            self.assertEqual(
                payload["priority_target_id_summary"]["status_counts"],
                SUPPLEMENT.EXPECTED_PRIORITY_STATUS_COUNTS,
            )

            # Staged-image drift must be caught before any destination replace.
            PILImage.new("RGB", (10, 10), (255, 255, 255)).save(staged_crops[records[0]["building_id"], 1])
            with self.assertRaisesRegex(RuntimeError, "crop hash mismatch"):
                SUPPLEMENT.validate_staged_output_bundle(
                    payload,
                    staged_csv=staged_csv,
                    staged_crops=staged_crops,
                    staged_contact=staged_contact,
                )


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Focused unit tests for the adjudicated S3-A oracle-ID address producer."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image as PILImage


SCRIPT = Path(__file__).with_name("e5_c001_s3_semantic_regions.py")
SPEC = importlib.util.spec_from_file_location("e5_c001_s3_semantic_regions", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REGIONS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REGIONS
SPEC.loader.exec_module(REGIONS)


class OracleIdAddressTest(unittest.TestCase):
    def test_actual_source_id_splits_component_and_excludes_seven_each_side(self) -> None:
        clean = np.ones((31, 40), dtype=bool)
        label = np.ones((31, 40), dtype=np.uint8)
        bidmap = np.zeros((31, 40), dtype=np.int32)
        bidmap[:, 20:] = 1
        lookup = np.asarray([1, 2], dtype=np.int32)
        (
            region_ids,
            cutline,
            regions,
            stats,
            owner,
            eligible,
            inactive_veto,
        ) = REGIONS.build_oracle_id_regions(
            clean,
            label,
            bidmap,
            lookup,
            ["A", "B"],
            {1: 2},
        )
        self.assertEqual(np.flatnonzero(np.any(cutline & (owner == 1), axis=0)).tolist(), list(range(13, 20)))
        self.assertEqual(np.flatnonzero(np.any(cutline & (owner == 2), axis=0)).tolist(), list(range(20, 27)))
        self.assertEqual(int(np.sum(cutline)), 31 * 14)
        self.assertEqual(int(np.sum(region_ids > 0)), 31 * (40 - 14))
        self.assertEqual({row["building_id"] for row in regions}, {"A", "B"})
        self.assertEqual({row["pre_split_oracle_instance_count"] for row in regions}, {2})
        self.assertTrue(all(row["pre_split_overlap_count"] == 2 for row in regions))
        self.assertTrue(all(row["lod2_depth_or_height_loss_input"] is False for row in regions))
        self.assertTrue(all("projection_z_local_m" not in row for row in regions))
        self.assertTrue(bool(eligible.all()))
        self.assertFalse(bool(inactive_veto.any()))
        self.assertEqual(stats["address_datum_geoid_m"], 48.0)
        self.assertEqual(stats["address_datum_shift_z_m"], 556.0)

    def test_fixed_class_remains_authoritative_at_one_pixel_raster_mismatch(self) -> None:
        clean = np.ones((20, 20), dtype=bool)
        label = np.ones((20, 20), dtype=np.uint8)
        label[0, 0] = 0
        region_ids, _cutline, _regions, stats, owner, *_rest = (
            REGIONS.build_oracle_id_regions(
                clean,
                label,
                np.zeros((20, 20), dtype=np.int32),
                np.asarray([1], dtype=np.int32),
                ["A"],
                {1: 1},
            )
        )
        self.assertEqual(int(owner[0, 0]), 1)
        self.assertGreater(int(region_ids[0, 0]), 0)
        self.assertEqual(stats["actual_source_class_mismatch_pixels"], 1)
        self.assertTrue(stats["fixed_clean_class_mask_is_authoritative"])

    def test_non_c00118_raycast_id_remains_unassigned(self) -> None:
        clean = np.ones((20, 20), dtype=bool)
        label = np.ones((20, 20), dtype=np.uint8)
        # Mesh index 1 maps to owner 0 (outside the locked candidate set).
        owner = REGIONS.raycast_owner_map(
            label == 1,
            np.ones((20, 20), dtype=np.int32),
            np.asarray([1, 0], dtype=np.int32),
        )
        self.assertFalse(bool(owner.any()))


class T01OutputContractTest(unittest.TestCase):
    @staticmethod
    def measurement(building_id: str, stem: str, ref_pixels: int) -> object:
        return REGIONS.GateMeasurement(
            building_id=building_id,
            view_stem=stem,
            view_name=f"{stem}.JPG",
            ref_pixels=ref_pixels,
            clean_clipped_pixels=ref_pixels,
            intersection_pixels=ref_pixels,
            union_pixels=ref_pixels,
            iou=1.0,
            fragment_count_ge64=1,
            boundary_offset_px=0.0,
            jacobian_m_per_px_x=1.0,
            jacobian_m_per_px_y=1.0,
            jacobian_m_per_px=1.0,
            boundary_offset_m=0.0,
            roof_height_local_m=100.0,
        )

    def test_canonical_guards_and_debug_escape_hatch(self) -> None:
        payload = REGIONS.validate_run_mode_contract(
            debug_subset=False,
            frame_count=428,
            core_buildings=REGIONS.CORE9,
            views_per_building=3,
            skip_overlays=False,
            legacy_label_geoid_m=48.0,
        )
        self.assertEqual(payload["mode"], "canonical_full")
        invalid = [
            {"frame_count": 427},
            {"core_buildings": list(reversed(REGIONS.CORE9))},
            {"views_per_building": 2},
            {"skip_overlays": True},
        ]
        defaults = {
            "debug_subset": False,
            "frame_count": 428,
            "core_buildings": REGIONS.CORE9,
            "views_per_building": 3,
            "skip_overlays": False,
            "legacy_label_geoid_m": 48.0,
        }
        for override in invalid:
            with self.subTest(override=override), self.assertRaises(AssertionError):
                REGIONS.validate_run_mode_contract(**{**defaults, **override})
        debug = REGIONS.validate_run_mode_contract(
            debug_subset=True,
            frame_count=3,
            core_buildings=[REGIONS.CORE9[0]],
            views_per_building=0,
            skip_overlays=True,
            legacy_label_geoid_m=48.0,
        )
        self.assertEqual(debug["mode"], "debug_subset")

    def test_candidate_selection_is_area_ranked_with_stem_tie_break(self) -> None:
        building = REGIONS.CORE9[0]
        measurements = [
            self.measurement(building, "z", 100),
            self.measurement(building, "b", 200),
            self.measurement(building, "a", 200),
            self.measurement(building, "c", 150),
        ]
        selected, rows = REGIONS.select_gate_candidates(
            measurements,
            [building],
            3,
            official_geoid_m=45.7,
            official_shift_z_m=558.3,
            label_actual_source_shift_z_m=556.0,
        )
        self.assertEqual([row.view_stem for row in selected[building]], ["a", "b", "c"])
        self.assertEqual([row["rank_by_ref_area"] for row in rows], [1, 2, 3, 4])
        self.assertEqual(
            [row["selected_for_primary"] for row in rows], [True, True, True, False]
        )

    def test_priority_crop_and_contact_sheet(self) -> None:
        measured = np.zeros((300, 400), dtype=bool)
        reference = np.zeros_like(measured)
        measured[100:120, 190:210] = True
        reference[102:122, 192:212] = True
        box, edge = REGIONS.priority_crop_box(measured, reference)
        self.assertEqual(box[2] - box[0], 256)
        self.assertEqual(box[3] - box[1], 256)
        self.assertFalse(edge)
        measured[:, 0] = True
        edge_box, edge = REGIONS.priority_crop_box(measured, reference)
        self.assertEqual(edge_box[0], 0)
        self.assertTrue(edge)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {}
            for building_id in REGIONS.TEXTURELESS3:
                for rank in (1, 2, 3):
                    path = root / f"{building_id}_{rank}.png"
                    PILImage.new("RGB", (80, 60), (rank * 50, 20, 20)).save(path)
                    paths[(building_id, rank)] = path
            sheet_path = root / "sheet.png"
            sheet = REGIONS.make_textureless_contact_sheet(paths, sheet_path)
            self.assertEqual(sheet.size, (1440, 1144))
            self.assertTrue(sheet_path.is_file())

    def test_canonical_output_self_validation_and_hashes(self) -> None:
        measurements = []
        for building_index, building_id in enumerate(REGIONS.CORE9):
            for rank in range(1, 4):
                measurements.append(
                    self.measurement(
                        building_id,
                        f"view_{building_index:02d}_{rank}",
                        1000 - rank,
                    )
                )
        selected, candidate_rows = REGIONS.select_gate_candidates(
            measurements,
            REGIONS.CORE9,
            3,
            official_geoid_m=45.7,
            official_shift_z_m=558.3,
            label_actual_source_shift_z_m=556.0,
        )
        metric_names = [
            "ref_pixels",
            "clean_clipped_pixels",
            "intersection_pixels",
            "union_pixels",
            "iou",
            "fragment_count_ge64",
            "boundary_offset_px",
            "jacobian_m_per_px_x",
            "jacobian_m_per_px_y",
            "jacobian_m_per_px",
            "boundary_offset_m",
            "roof_height_local_m",
        ]
        gate_rows = []
        for building_id in REGIONS.CORE9:
            rows = selected[building_id]
            for rank, measurement in enumerate(rows, start=1):
                payload = vars(measurement)
                gate_rows.append(
                    {
                        "measurement_role": "reference_only",
                        "gate_role": "self_consistency_not_a_gate",
                        "decision": "not_applicable",
                        "row_type": "view",
                        "building_id": building_id,
                        "view_stem": measurement.view_stem,
                        "view_rank_by_ref_area": rank,
                        **{
                            key: value
                            for key, value in payload.items()
                            if key not in {"building_id", "view_stem", "view_name"}
                        },
                    }
                )
            gate_rows.append(
                {
                    "measurement_role": "reference_only",
                    "gate_role": "self_consistency_not_a_gate",
                    "decision": "not_applicable",
                    "row_type": "building_median",
                    "building_id": building_id,
                    "view_stem": "MEDIAN",
                    **{
                        key: float(np.median([getattr(row, key) for row in rows]))
                        for key in metric_names
                    },
                }
            )

        with tempfile.TemporaryDirectory() as tmp:
            fig_dir = Path(tmp) / "semantic_gate"
            priority_dir = fig_dir / "priority"
            priority_dir.mkdir(parents=True)
            artifacts = []
            for building_id, rows in selected.items():
                for rank, measurement in enumerate(rows, start=1):
                    full_path = fig_dir / f"{building_id}__{measurement.view_stem}.png"
                    PILImage.new("RGB", (32, 24), "white").save(full_path)
                    artifacts.append(
                        REGIONS.image_artifact(
                            full_path,
                            kind="full_overlay",
                            building_id=building_id,
                            view_stem=measurement.view_stem,
                            rank=rank,
                        )
                    )
                    if building_id in REGIONS.TEXTURELESS3:
                        crop_path = priority_dir / f"{building_id}__rank{rank}.png"
                        PILImage.new("RGB", (20, 20), "gray").save(crop_path)
                        artifacts.append(
                            REGIONS.image_artifact(
                                crop_path,
                                kind="priority_crop",
                                building_id=building_id,
                                view_stem=measurement.view_stem,
                                rank=rank,
                                crop_box_xyxy=(0, 0, 20, 20),
                                target_touches_frame=False,
                            )
                        )
            contact_path = priority_dir / "textureless3_contact_sheet.png"
            PILImage.new("RGB", (30, 30), "black").save(contact_path)
            artifacts.append(
                REGIONS.image_artifact(contact_path, kind="priority_contact_sheet")
            )
            result = REGIONS.validate_t0_1_outputs(
                gate_rows=gate_rows,
                candidate_rows=candidate_rows,
                core_buildings=REGIONS.CORE9,
                views_per_building=3,
                overlay_artifacts=artifacts,
                fig_dir=fig_dir,
                debug_subset=False,
                skip_overlays=False,
            )
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["primary_view_rows"], 27)
            self.assertEqual(result["priority_crop_count"], 9)
            self.assertRegex(result["overlay_artifact_aggregate_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()

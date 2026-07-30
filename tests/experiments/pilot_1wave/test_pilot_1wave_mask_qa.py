#!/usr/bin/env python3
"""Synthetic contract tests for P1W 04a-versus-04b mask QA."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

import numpy as np


REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO / "scripts/pilot_1wave"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pilot_1wave_mask_qa as qa
from src.stage2 import pilot_mask_schema as schema


def digest(value: str) -> str:
    return schema.sha256_bytes(value.encode("utf-8"))


class PilotMaskQaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.view_ids = ["a.jpg", "b.jpg"]
        self.vision = {
            "a.jpg": np.asarray([[True, True], [False, False]], dtype=np.bool_),
            "b.jpg": np.asarray([[True, False], [True, False]], dtype=np.bool_),
        }
        self.gt = {
            "a.jpg": np.zeros((2, 2), dtype=np.bool_),
            "b.jpg": np.asarray([[True, False], [False, True]], dtype=np.bool_),
        }
        self.reference = {
            view_id: np.ones((2, 2), dtype=np.bool_) for view_id in self.view_ids
        }

    def _write_mask_set(
        self,
        root: Path,
        masks: dict[str, np.ndarray],
        *,
        purpose: schema.MaskPurpose,
        source: schema.MaskSource,
        geometry: dict[str, str] | None = None,
    ) -> Path:
        return schema.write_binary_mask_set(
            root,
            masks,
            purpose=purpose,
            source=source,
            source_disclosure="synthetic unit-test source disclosure",
            input_sha256=digest(f"input:{root.name}"),
            config_sha256=digest("config"),
            geometry_sha256_by_view=geometry
            or {view_id: digest(f"geometry:{view_id}") for view_id in masks},
        )

    def _write_producers(
        self,
        manifest_04a: Path,
        manifest_04b: Path,
        masks_04b: dict[str, np.ndarray],
        *,
        empty_ids: list[str] | None = None,
        total_positive: int | None = None,
    ) -> None:
        manifest_04a.parent.joinpath("producer_manifest.json").write_text(
            json.dumps(
                {
                    "schema": qa.EXPECTED_04A_PRODUCER_SCHEMA,
                    "run_id": qa.RUN_ID,
                    "source": schema.MaskSource.VISION_GROUNDEDSAM_ROOF.value,
                    "mask_manifest": manifest_04a.name,
                    "mask_manifest_sha256": schema.sha256_file(manifest_04a),
                    "view_count": len(self.view_ids),
                    "gt_read_for_selection": False,
                    "gt_iou_computed": False,
                    "prior_inference_runs_started": 1,
                    "inference_runs_started": 2,
                    "inference_runs_successful": 1,
                    "inference_runs_failed": 1,
                    "small_core_1px_fallback_view_count": 0,
                    "small_core_1px_fallback_view_ids": [],
                    "small_core_1px_fallback_building_event_count": 0,
                    "small_core_0px_fallback_view_count": 0,
                    "small_core_0px_fallback_view_ids": [],
                    "small_core_0px_fallback_building_event_count": 0,
                    "producer_lock_sha256": schema.sha256_file(qa.PRODUCER_LOCK),
                    "learning_runs_started": 0,
                    "audit": [
                        {
                            "view_id": view_id,
                            "small_core_1px_fallback_count": 0,
                            "small_core_1px_fallback_building_ids": [],
                            "small_core_0px_fallback_count": 0,
                            "small_core_0px_fallback_building_ids": [],
                        }
                        for view_id in self.view_ids
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        actual_empty = [
            view_id for view_id in self.view_ids if not bool(masks_04b[view_id].any())
        ]
        actual_total = sum(int(masks_04b[view_id].sum()) for view_id in self.view_ids)
        reported_empty = actual_empty if empty_ids is None else empty_ids
        reported_total = actual_total if total_positive is None else total_positive
        manifest_04b.parent.joinpath("producer_manifest.json").write_text(
            json.dumps(
                {
                    "schema": qa.EXPECTED_04B_PRODUCER_SCHEMA,
                    "run_id": qa.RUN_ID,
                    "source": schema.MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND.value,
                    "mask_manifest": manifest_04b.name,
                    "mask_manifest_sha256": schema.sha256_file(manifest_04b),
                    "view_count": len(self.view_ids),
                    "empty_view_count": len(reported_empty),
                    "empty_view_ids": reported_empty,
                    "total_roof_mask_pixels": reported_total,
                    "selected_building_roof_geometry_coverage_count": 30,
                    "selected_building_roof_geometry_coverage_complete": True,
                    "archive_arrays": ["mask:bool"],
                    "forbidden_archive_arrays": [
                        "roof_z",
                        "hit_depth",
                        "face_ids",
                        "building_ids",
                        "semantic_class",
                        "primitive_ids",
                    ],
                    "inference_runs_started": 1,
                    "producer_lock_sha256": schema.sha256_file(qa.PRODUCER_LOCK),
                    "learning_runs_started": 0,
                    "audit": [
                        {
                            "view_id": view_id,
                            "roof_mask_pixels": int(masks_04b[view_id].sum()),
                            "empty_view": not bool(masks_04b[view_id].any()),
                        }
                        for view_id in self.view_ids
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        manifest_04a.chmod(0o444)
        manifest_04b.chmod(0o444)
        manifest_04a.parent.joinpath("producer_manifest.json").chmod(0o444)
        manifest_04b.parent.joinpath("producer_manifest.json").chmod(0o444)

    def _fixture(
        self,
        root: Path,
        *,
        gt_masks: dict[str, np.ndarray] | None = None,
        gt_geometry: dict[str, str] | None = None,
        empty_ids: list[str] | None = None,
        total_positive: int | None = None,
    ) -> tuple[Path, Path, Path]:
        geometry = {view_id: digest(f"geometry:{view_id}") for view_id in self.view_ids}
        manifest_04a = self._write_mask_set(
            root / "04a",
            self.vision,
            purpose=schema.MaskPurpose.PLANE_REGION,
            source=schema.MaskSource.VISION_GROUNDEDSAM_ROOF,
            geometry=geometry,
        )
        actual_gt = self.gt if gt_masks is None else gt_masks
        manifest_04b = self._write_mask_set(
            root / "04b",
            actual_gt,
            purpose=schema.MaskPurpose.PLANE_REGION,
            source=schema.MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND,
            geometry=geometry if gt_geometry is None else gt_geometry,
        )
        reference = self._write_mask_set(
            root / "reference",
            self.reference,
            purpose=schema.MaskPurpose.PHOTO_SUPPORT,
            source=schema.MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
            geometry=geometry,
        )
        self._write_producers(
            manifest_04a,
            manifest_04b,
            actual_gt,
            empty_ids=empty_ids,
            total_positive=total_positive,
        )
        return manifest_04a, manifest_04b, reference

    def test_successfully_audits_empty_gt_view_and_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifests = self._fixture(Path(directory))
            audit, rows = qa.audit_and_compare(*manifests, expected_view_count=2)
            self.assertEqual(audit["view_count"], 2)
            self.assertEqual(audit["empty_view_ids_04b"], ["a.jpg"])
            self.assertTrue(audit["forbidden_gt_array_gate_passed"])
            self.assertEqual(audit["optimizer_steps"], 0)
            self.assertEqual(audit["learning_runs_started"], 0)
            first, second = rows
            self.assertEqual(first["positive_pixels_04b_gt"], 0)
            self.assertIsNone(first["recall"])
            self.assertEqual(first["iou"], 0.0)
            self.assertAlmostEqual(second["iou"], 1.0 / 3.0)
            self.assertAlmostEqual(second["precision"], 0.5)
            self.assertAlmostEqual(second["recall"], 0.5)

    def test_geometry_sha_mismatch_hard_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            geometry = {
                "a.jpg": digest("wrong-geometry"),
                "b.jpg": digest("geometry:b.jpg"),
            }
            manifests = self._fixture(Path(directory), gt_geometry=geometry)
            with self.assertRaisesRegex(qa.MaskQaError, "geometry SHA mismatch"):
                qa.audit_and_compare(*manifests, expected_view_count=2)

    def test_all_empty_gt_aggregate_hard_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            empty = {
                view_id: np.zeros((2, 2), dtype=np.bool_)
                for view_id in self.view_ids
            }
            manifests = self._fixture(Path(directory), gt_masks=empty)
            with self.assertRaisesRegex(qa.MaskQaError, "positive aggregate pixels"):
                qa.audit_and_compare(*manifests, expected_view_count=2)

    def test_producer_empty_view_claim_mismatch_hard_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifests = self._fixture(Path(directory), empty_ids=[])
            with self.assertRaisesRegex(qa.MaskQaError, "empty-view count differs"):
                qa.audit_and_compare(*manifests, expected_view_count=2)

    def test_qa_outputs_are_separate_and_record_optimizer_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifests = self._fixture(root)
            audit, rows = qa.audit_and_compare(*manifests, expected_view_count=2)
            output = root / "qa-output"
            manifest_path = qa.write_qa(output, audit, rows)
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], qa.QA_SCHEMA)
            self.assertEqual(payload["row_count"], 2)
            self.assertEqual(payload["learning_runs_started"], 0)
            self.assertEqual(payload["optimizer_steps"], 0)
            self.assertFalse(payload["training_config_read"])
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o555)
            for path in output.iterdir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
                self.assertTrue(os.access(path, os.R_OK))
            with (output / payload["csv"]).open(newline="", encoding="utf-8") as handle:
                csv_rows = list(csv.DictReader(handle))
            self.assertEqual([row["view_id"] for row in csv_rows], self.view_ids)
            self.assertEqual(csv_rows[0]["recall"], "")
            with self.assertRaisesRegex(qa.MaskQaError, "must not already exist"):
                qa.write_qa(output, audit, rows)


if __name__ == "__main__":
    unittest.main()

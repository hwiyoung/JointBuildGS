#!/usr/bin/env python3
"""Regression checks for the result-blind first-wave calibration lock."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
LOCK = REPO / "phases/p2-gsjso/configs/pilot_1wave/pilot_1wave_calibration_lock.json"
LOCK_SHA256 = "7eb4db2df284388c076b4e6876b169be389edb8d3da601931d3ca7997cdf54b4"
CALIBRATION_SEED_REASON = (
    "lowest registered training seed; locked result-blind before forward-only calibration"
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CalibrationLockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lock = json.loads(LOCK.read_text(encoding="utf-8"))

    def test_all_declared_inputs_match_bytes(self) -> None:
        self.assertEqual(sha256_file(LOCK), LOCK_SHA256)
        for binding in self.lock["input_bindings"].values():
            path = REPO / binding["path"]
            self.assertTrue(path.is_file(), path)
            self.assertEqual(sha256_file(path), binding["sha256"], path)

    def test_calibration_views_are_hash_ranked_training_views(self) -> None:
        binding = self.lock["input_bindings"]["projected_footprint_mask_manifest"]
        manifest = json.loads((REPO / binding["path"]).read_text(encoding="utf-8"))
        names = sorted(record["view_id"] for record in manifest["records"])
        self.assertEqual(len(names), 481)
        training = [name for index, name in enumerate(names) if index % 10 != 9]
        selection = self.lock["selection_sha256"]
        expected = sorted(
            training,
            key=lambda name: hashlib.sha256(
                f"{selection}|{name}".encode("utf-8")
            ).hexdigest(),
        )[:16]
        actual = self.lock["view_selection"]["calibration_view_ids"]
        self.assertEqual(actual, expected)
        self.assertEqual(
            hashlib.sha256("\n".join(actual).encode("utf-8")).hexdigest(),
            self.lock["view_selection"][
                "calibration_view_ids_sha256_newline_joined"
            ],
        )

    def test_soft_is_below_medium_and_pair_shares_one_weight(self) -> None:
        resolution = self.lock["forward_only_resolution"]
        self.assertEqual(resolution["calibration_seed"], 1001)
        self.assertEqual(
            resolution["calibration_seed_reason"], CALIBRATION_SEED_REASON
        )
        soft = resolution["soft_03"]["target_plane_to_photo_ratio"]
        medium = resolution["medium_04a"]["target_plane_to_photo_ratio"]
        lower, upper = resolution["medium_verification"]["inclusive_ratio_range"]
        self.assertLess(soft, lower)
        self.assertEqual(medium, 1.0)
        self.assertLessEqual(lower, medium)
        self.assertLessEqual(medium, upper)
        self.assertEqual(
            resolution["medium_04a"]["weight_reused_for_conditions"],
            ["04a", "04b"],
        )
        self.assertTrue(resolution["no_post_update_recalibration"])

    def test_recommended_mono_and_approved_budget_are_numeric(self) -> None:
        recipe = self.lock["base_recipe"]
        self.assertEqual(recipe["w_mono_normal_aux"], 0.05)
        self.assertEqual(recipe["structure_grouping"], "g2_geometry")
        budget = self.lock["training_budget"]
        self.assertEqual(budget["max_optimizer_updates"], 20000)
        self.assertEqual(
            budget["full_state_checkpoint_updates"], [5000, 10000, 15000, 20000]
        )
        self.assertEqual(budget["wall_guard_hours"], 9.0)
        self.assertFalse(budget["partial_is_winner_eligible"])

    def test_forward_runtime_is_exactly_pinned_and_host_attested(self) -> None:
        runtime = self.lock["forward_runtime"]
        self.assertTrue(runtime["container_required"])
        self.assertEqual(runtime["image_tag"], "jointbuildgs:dev")
        self.assertEqual(
            runtime["image_id"],
            "sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396",
        )
        self.assertEqual(
            runtime["host_attestation_environment"],
            {
                "image_tag": "P1W_HOST_IMAGE_TAG",
                "image_id": "P1W_HOST_IMAGE_ID",
            },
        )
        self.assertEqual(
            {key: runtime[key] for key in ("python", "torch", "cuda", "gsplat", "numpy", "scipy", "pillow")},
            {
                "python": "3.11.15",
                "torch": "2.4.1+cu121",
                "cuda": "12.1",
                "gsplat": "1.4.0",
                "numpy": "1.26.4",
                "scipy": "1.13.1",
                "pillow": "10.4.0",
            },
        )

    def test_plane_guided_init_is_explicit_and_shared_by_medium_pair(self) -> None:
        init = self.lock["plane_guided_initialization"]
        self.assertEqual(init["conditions"], ["04a", "04b"])
        self.assertEqual(init["pilot_plane_init_stride_px"], 8)
        self.assertEqual(init["pilot_plane_init_grid_offset_px"], 4)
        self.assertLess(
            init["pilot_plane_init_grid_offset_px"],
            init["pilot_plane_init_stride_px"],
        )
        self.assertEqual(init["pilot_plane_init_knn"], 4)
        self.assertEqual(init["pilot_plane_init_tolerance_m"], 0.5)
        self.assertEqual(init["pilot_plane_init_min_coverage"], 0.05)
        self.assertEqual(init["unmatched_normal_world"], [0.0, 0.0, 1.0])
        self.assertIn("not reapplied", init["resume"])


if __name__ == "__main__":
    unittest.main()

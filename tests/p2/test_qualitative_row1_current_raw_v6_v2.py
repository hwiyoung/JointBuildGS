import json
from pathlib import Path
import unittest

import numpy as np

from scripts.p2.qualitative_row1_current_raw_v6.preview10_v2 import choose_views


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v6/preview10_v2.json"


def candidate(name, nadir, vector, center):
    return {
        "eligible": True,
        "camera_name": name,
        "nadir_deg": float(nadir),
        "representative_projected_bbox_area_px2": 2000.0,
        "valid_actual_observation_count": 10,
        "visible_component_ids_in_crop": [1],
        "visible_component_count_in_crop": 1,
        "source_component_count": 1,
        "_view_vector": np.asarray(vector, dtype=np.float64),
        "_camera_center": np.asarray(center, dtype=np.float64),
    }


class SelectionFallbackTest(unittest.TestCase):
    def setUp(self):
        self.selection = {
            "roles": ["TOP", "RANDOM_1", "RANDOM_2", "RANDOM_3"],
            "random_seed_namespace": "test-v6-v2",
            "near_nadir_max_deg": 20.0,
            "minimum_view_direction_separation_deg": 15.0,
            "minimum_camera_center_separation_m": 5.0,
        }

    def test_diverse_candidates_are_selected_before_validated_fallback(self):
        candidates = [
            candidate("top.jpg", 5, [0, 0, 1], [0, 0, 0]),
            candidate("diverse.jpg", 40, [1, 0, 0], [10, 0, 0]),
            candidate("similar-a.jpg", 10, [0, 0, 1], [1, 0, 0]),
            candidate("similar-b.jpg", 15, [0, 0, 1], [2, 0, 0]),
        ]

        views, top_status, _, _ = choose_views("building", candidates, self.selection)

        self.assertEqual(top_status, "NEAR_NADIR")
        self.assertEqual(sum(view["status"] == "SELECTED" for view in views), 4)
        sources = [view.get("source") for view in views[1:]]
        self.assertEqual(
            sources.count("DETERMINISTIC_POSE_DIVERSE_RANDOM_REPRESENTATIVE_COMPONENT"),
            1,
        )
        self.assertEqual(sources.count("DETERMINISTIC_VALIDATED_RANDOM_FALLBACK"), 2)

    def test_fallback_never_creates_a_camera_when_no_candidate_is_valid(self):
        invalid = candidate("invalid.jpg", 5, [0, 0, 1], [0, 0, 0])
        invalid["eligible"] = False

        views, top_status, _, _ = choose_views("building", [invalid], self.selection)

        self.assertEqual(top_status, "REPRESENTATIVE_ROOF_CAMERA_MISSING")
        self.assertTrue(all(view["status"] == "REPRESENTATIVE_ROOF_CAMERA_MISSING" for view in views))


class PreviewContractTest(unittest.TestCase):
    def test_v2_contract_freezes_validated_only_fallback(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        fallback = config["selection_fallback"]

        self.assertTrue(fallback["pose_diversity_has_priority"])
        self.assertTrue(fallback["fallback_uses_only_fully_validated_candidates"])
        self.assertTrue(fallback["fallback_is_deterministic"])
        self.assertTrue(fallback["fallback_may_not_replace_a_missing_candidate_pool"])
        self.assertFalse(config["preview"]["full_199_render_authorized"])
        self.assertIsNone(config["scientific_verdict"])


if __name__ == "__main__":
    unittest.main()

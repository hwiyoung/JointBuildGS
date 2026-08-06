import json
from pathlib import Path
import unittest


from scripts.p2.qualitative_row1_current_raw_v6.preview10_v3 import (
    GEOMETRY_FALLBACK_SOURCE,
    choose_views,
    geometry_fallback_candidates,
)


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v6/preview10_v3.json"


def geometry_candidate(name, nadir, visible=True):
    return {
        "eligible": False,
        "camera_name": name,
        "nadir_deg": float(nadir),
        "representative_component_id": 1,
        "representative_projected_bbox_area_px2": 2000.0,
        "visible_component_ids_in_crop": [1] if visible else [],
        "visible_component_count_in_crop": 1 if visible else 0,
        "source_component_count": 1,
        "building_sparse_track_linked": False,
        "rejection_reasons": [
            "INSUFFICIENT_TRACK_POINTS",
            "INSUFFICIENT_VALID_ACTUAL_OBSERVATIONS",
        ],
    }


class GeometryFallbackTest(unittest.TestCase):
    def setUp(self):
        self.selection = {
            "roles": ["TOP", "RANDOM_1", "RANDOM_2", "RANDOM_3"],
            "random_seed_namespace": "test-v6-v3",
        }

    def test_only_complete_projectable_components_enter_terminal_pool(self):
        complete = geometry_candidate("complete.jpg", 10, True)
        outside = geometry_candidate("outside.jpg", 20, False)
        too_small = geometry_candidate("small.jpg", 30, True)
        too_small["rejection_reasons"].append("PROJECTED_REPRESENTATIVE_BOUNDARY_TOO_SMALL")

        result = geometry_fallback_candidates([complete, outside, too_small])

        self.assertEqual([row["camera_name"] for row in result], ["complete.jpg"])

    def test_zero_validated_pool_is_filled_deterministically_from_geometry(self):
        candidates = [
            geometry_candidate("a.jpg", 20),
            geometry_candidate("b.jpg", 10),
            geometry_candidate("c.jpg", 30),
            geometry_candidate("d.jpg", 40),
            geometry_candidate("e.jpg", 50),
        ]

        first, status, seed, pool_hash = choose_views("building", candidates, self.selection)
        second, status2, seed2, pool_hash2 = choose_views("building", candidates, self.selection)

        self.assertEqual(first, second)
        self.assertEqual((status, seed, pool_hash), (status2, seed2, pool_hash2))
        self.assertEqual(status, GEOMETRY_FALLBACK_SOURCE)
        self.assertEqual(len(first), 4)
        self.assertTrue(all(view["status"] == "SELECTED" for view in first))
        self.assertTrue(all(view["source"] == GEOMETRY_FALLBACK_SOURCE for view in first))
        self.assertEqual(first[0]["camera"]["camera_name"], "b.jpg")


class PreviewContractTest(unittest.TestCase):
    def test_v3_contract_labels_no_sparse_confirmation(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        fallback = config["selection_fallback"]

        self.assertEqual(fallback["terminal_fallback_trigger"], "ZERO_VALIDATED_CAMERAS")
        self.assertEqual(
            fallback["terminal_fallback_pool"],
            "ALL_EXACT_937_SFM_CAMERAS_WITH_COMPLETE_REPRESENTATIVE_BOUNDARY_IN_FRAME",
        )
        self.assertTrue(fallback["terminal_fallback_is_deterministic"])
        self.assertTrue(fallback["terminal_fallback_has_no_building_sparse_confirmation"])
        self.assertIn("NO BUILDING-SPARSE CONFIRMATION", fallback["terminal_fallback_image_label"])
        self.assertFalse(config["preview"]["full_199_render_authorized"])
        self.assertIsNone(config["scientific_verdict"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.p2.qualitative_row1_current_raw_v2.preview import (
    deterministic_preferred_sample,
    deterministic_sample,
    stable_seed,
)


REPO = Path(__file__).resolve().parents[2]


class Row1V2SelectionTest(unittest.TestCase):
    def test_seed_and_sample_are_stable_and_order_independent(self) -> None:
        seed = stable_seed("namespace", "DEBY_LOD2_1")
        self.assertEqual(seed, stable_seed("namespace", "DEBY_LOD2_1"))
        self.assertEqual(
            deterministic_sample(["d", "b", "a", "c"], 3, seed),
            deterministic_sample(["c", "a", "d", "b"], 3, seed),
        )

    def test_contract_blocks_full_render_and_next_row(self) -> None:
        config = json.loads((REPO / "configs/p2/qualitative_row1_current_raw_v2/preview_v1.json").read_text())
        self.assertEqual(config["selection"]["roles"], ["TOP", "RANDOM_1", "RANDOM_2", "RANDOM_3"])
        self.assertFalse(config["selection"]["roof_boundary_used_for_selection"])
        self.assertFalse(config["preview"]["full_199_render_authorized"])
        self.assertFalse(config["next_row_authorized"])

    def test_partial_candidates_only_supplement_missing_full_slots(self) -> None:
        first, status = deterministic_preferred_sample(["full_a", "full_b"], ["partial_a", "partial_b"], 3, 7)
        second, second_status = deterministic_preferred_sample(["full_b", "full_a"], ["partial_b", "partial_a"], 3, 7)
        self.assertEqual(first, second)
        self.assertEqual(status, "SUPPLEMENTED_PARTIAL_PRISM")
        self.assertEqual(second_status, status)
        self.assertTrue({"full_a", "full_b"} <= set(first))


if __name__ == "__main__":
    unittest.main()

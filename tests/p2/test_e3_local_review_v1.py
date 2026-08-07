from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import numpy as np


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/p2/e3_local_review_v1/build_review.py"
SPEC = importlib.util.spec_from_file_location("e3_local_review", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class LocalValidationTest(unittest.TestCase):
    def test_protects_global_eval_and_adds_only_global_train(self) -> None:
        rows = []
        for index in range(16):
            angle = np.deg2rad(index * 22.5)
            rows.append(
                {
                    "view_name": f"v{index:02d}.jpg",
                    "global_role": "eval" if index in {0, 4} else "train",
                    "azimuth_deg": index * 22.5,
                    "nadir_deg": 20.0 + (index % 3) * 30.0,
                    "view_direction": np.asarray([np.cos(angle), np.sin(angle), 0.2]),
                    "projected_area_px2": 1000.0 + index,
                }
            )
            rows[-1]["view_direction"] /= np.linalg.norm(rows[-1]["view_direction"])
        protected, additions = MODULE.augment_validation(
            rows,
            {
                "minimum_validation_views": 4,
                "validation_fraction": 0.125,
                "azimuth_bin_count": 8,
                "nadir_bin_edges_deg": [35.0, 70.0],
            },
        )
        self.assertEqual(protected, {"v00.jpg", "v04.jpg"})
        self.assertEqual(len(additions), 2)
        self.assertTrue(all(rows[int(name[1:3])]["global_role"] == "train" for name in additions))
        self.assertFalse(protected & additions)


if __name__ == "__main__":
    unittest.main()

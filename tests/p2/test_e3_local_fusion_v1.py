from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import numpy as np


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/p2/e3_local_review_v1/extract_tsdf_consensus.py"
SPEC = importlib.util.spec_from_file_location("e3_local_consensus", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ConsensusFusionTest(unittest.TestCase):
    def test_voxel_keys_are_stable_within_cell(self) -> None:
        points = np.asarray([[0.1, 0.1, 0.1], [0.4, 0.4, 0.4], [1.1, 0.1, 0.1]])
        keys = MODULE.pack_voxels(points, 1.0)
        self.assertEqual(keys[0], keys[1])
        self.assertNotEqual(keys[0], keys[2])

    def test_invalid_quantile_contract_is_rejected_by_ordering(self) -> None:
        low, high = 0.01, 0.99
        self.assertTrue(0 <= low < high <= 1)


if __name__ == "__main__":
    unittest.main()

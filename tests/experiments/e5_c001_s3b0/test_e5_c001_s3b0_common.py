#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts/e5_c001/s3b0/e5_c001_s3b0_common.py"
SPEC = importlib.util.spec_from_file_location("e5_c001_s3b0_common", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
common = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(common)


class S3B0CommonTest(unittest.TestCase):
    def test_deterministic_npz(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            first = Path(root) / "a.npz"
            second = Path(root) / "b.npz"
            arrays = {
                "mask": np.asarray([[True, False], [False, True]], dtype=np.bool_),
                "metadata_json": np.asarray('{"learning_runs_started":0}'),
            }
            common.atomic_deterministic_npz(first, arrays)
            common.atomic_deterministic_npz(second, arrays)
            self.assertEqual(common.sha256_file(first), common.sha256_file(second))

    def test_projection_mask_identity_camera(self) -> None:
        geom = Polygon([(1, 1), (4, 1), (4, 4), (1, 4)])
        view = {
            "R_w2c": np.eye(3).tolist(),
            "t_w2c": [0, 0, 10],
            "K_crop": [[10, 0, 0], [0, 10, 0], [0, 0, 1]],
        }
        mask, uvs, depths = common.project_geometry_mask(
            geom,
            np.asarray([0.0, 0.0, 0.0]),
            view,
            np.zeros(3),
            (8, 8),
            max_step_m=0.5,
        )
        self.assertTrue(mask.any())
        self.assertEqual(len(uvs), 1)
        self.assertTrue(np.all(depths[0] > 0))

    def test_iou_empty_is_one(self) -> None:
        empty = np.zeros((3, 3), dtype=bool)
        self.assertEqual(common.iou(empty, empty), (0, 0, 1.0))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from scripts.phd.mvs_als_source_relation_v1 import run as relation


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/phd/mvs_als_source_relation_v1/run_v1.json"


class SourceRelationV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = relation.load_config(CONFIG)
        self.cfg["domain"]["world_xy_bbox_m"] = [-100.0, -100.0, 100.0, 100.0]
        self.cfg["frame"]["world_shift_xyz_m"] = [0.0, 0.0, 0.0]

    def plane(self, z: float, step: float = 0.25) -> np.ndarray:
        xy = np.arange(-2.0, 2.001, step)
        x, y = np.meshgrid(xy, xy)
        return np.column_stack((x.ravel(), y.ravel(), np.full(x.size, z))).astype(np.float32)

    def classify(self, mvs: np.ndarray, als: np.ndarray, core_source: int = 0):
        core = np.array([0.0, 0.0, mvs[0, 2] if core_source == 0 else als[0, 2]], np.float32)
        normal = np.array([0.0, 0.0, 1.0], np.float32)
        return relation.classify_core(
            core, normal, core_source, 20, 0.0,
            cKDTree(mvs.astype(np.float64)) if len(mvs) else None, mvs,
            cKDTree(als.astype(np.float64)) if len(als) else None, als,
            self.cfg, reciprocal=core_source == 1,
        )

    def test_config_has_exact_five_classes_and_no_prohibited_input_path(self):
        self.assertEqual(
            set(self.cfg["classes"].values()), set(relation.CLASS_NAMES.values())
        )
        inputs = json.dumps(self.cfg["inputs"]).lower()
        for token in ("uas", "lod2", "footprint", "stable_id", "journal1"):
            self.assertNotIn(token, inputs)
        self.assertIsNone(self.cfg["scientific_verdict"])

    def test_lod95_formula(self):
        observed = relation.lod95(0.2, 16, 0.3, 9, 1.96, 0.5)
        expected = 1.96 * (math.sqrt(0.2 ** 2 / 16 + 0.3 ** 2 / 9) + 0.5)
        self.assertAlmostEqual(observed, expected)

    def test_compatible_and_significant_planes(self):
        mvs = self.plane(0.0)
        same = self.plane(0.0)
        compatible = self.classify(mvs, same)
        self.assertEqual(int(compatible["relation_class"]), 1)
        shifted = self.plane(1.2)
        significant = self.classify(mvs, shifted)
        self.assertEqual(int(significant["relation_class"]), 2)
        self.assertGreater(abs(float(significant["m3c2_signed_m"])), 1.0)
        self.assertTrue(bool(significant["robust_significant"]))

    def test_mvs_only_and_prior_only_support(self):
        mvs = self.plane(0.0)
        empty = np.empty((0, 3), np.float32)
        mvs_only = self.classify(mvs, empty)
        self.assertEqual(int(mvs_only["relation_class"]), 3)
        als = self.plane(0.0)
        prior_only = self.classify(empty, als, core_source=1)
        self.assertEqual(int(prior_only["relation_class"]), 4)

    def test_sparse_other_source_is_not_comparable(self):
        mvs = self.plane(0.0)
        als = np.array([[0.0, 0.0, 0.2]], np.float32)
        result = self.classify(mvs, als)
        self.assertEqual(int(result["relation_class"]), 5)
        self.assertEqual(int(result["reason"]), relation.REASON_OTHER_SUPPORT_SPARSE)

    def test_binary_ply_writer_roundtrip_header_size(self):
        rows = np.zeros(2, dtype=relation.OUTPUT_DTYPE)
        rows["relation_class"] = [1, 2]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "map.ply"
            relation.write_relation_ply(path, rows)
            raw = path.read_bytes()
            self.assertIn(b"element vertex 2\n", raw)
            self.assertIn(b"property uchar relation_class\n", raw)


if __name__ == "__main__":
    unittest.main()

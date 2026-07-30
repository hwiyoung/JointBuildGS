#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "scripts/prepare_tum2twin_rv1_cache.py"
SPEC = importlib.util.spec_from_file_location("prepare_rv1", MODULE_PATH)
assert SPEC and SPEC.loader
PREP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREP)


def square(surface_id: str, x0: float, y0: float, size: float):
    ring = np.asarray(
        [
            [x0, y0, 10.0],
            [x0 + size, y0, 10.0],
            [x0 + size, y0 + size, 10.0],
            [x0, y0 + size, 10.0],
            [x0, y0, 10.0],
        ]
    )
    return PREP.e5.roof_surface_from_rings(surface_id, [ring])


class TestCacheAndPlaneOverlap(unittest.TestCase):
    def test_plane_overlap_matching_synthetic_polygon(self) -> None:
        ref = square("ref", 0.0, 0.0, 2.0)
        pred_match = square("pred_match", 0.5, 0.0, 2.0)
        pred_no = square("pred_no", 1.5, 0.0, 2.0)
        self.assertIsNotNone(ref)
        edges = PREP.strict_overlap_edges([ref], [pred_match], 0.5)
        self.assertEqual(len(edges), 1)
        self.assertGreaterEqual(edges[0]["ref_overlap_fraction"], 0.5)
        self.assertEqual(PREP.strict_overlap_edges([ref], [pred_no], 0.5), [])
        metrics = PREP.roof_metrics([ref], [pred_match], 0.5)
        self.assertEqual(metrics["roof_plane_f1"], 1.0)

    def test_resume_cache_complete_and_atomic_npz(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bid = "B1"
            target = root / bid
            PREP.atomic_npz(target / "dense.npz", xyz=np.zeros((1, 3)), classification=np.asarray([6]), inside=np.asarray([True]))
            PREP.atomic_npz(target / "reference.npz", xyz=np.zeros((1, 3)), classification=np.asarray([6]), inside=np.asarray([True]))
            PREP.atomic_json(target / "lod2.json", {})
            PREP.atomic_json(target / "complete.json", {})
            self.assertTrue(PREP.cache_complete(root, bid))
            self.assertFalse((target / "dense.npz.tmp").exists())

    def test_selected_source_file_is_not_modified_by_read(self) -> None:
        source = REPO / "docs/regression_input_snapshot.csv"
        before = PREP.source_snapshot([source])
        _ = source.read_bytes()[:256]
        after = PREP.source_snapshot([source])
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)

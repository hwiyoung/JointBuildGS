from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts.p2.c1_c2_shared_footprint_199_v3.build_cloudcompare_review10 import (
    DEFAULT_CONFIG,
    descendant_ids,
    footprint_line_obj,
    load_config,
    triangles_obj,
)


class CloudCompareReview10V1Tests(unittest.TestCase):
    def test_config_is_outcome_free_frozen_v3_only(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        self.assertTrue(config["selection"]["outcome_free"])
        self.assertEqual(config["selection"]["population_indices"], [1, 23, 45, 67, 89, 111, 133, 155, 177, 199])
        self.assertEqual(len(config["selection"]["building_ids"]), 10)
        self.assertEqual(config["review"]["primary_tool"], "CloudCompare")
        self.assertFalse(config["review"]["full_199_generation_authorized"])
        self.assertEqual(config["execution"]["roofer_invocations"], 0)
        self.assertEqual(config["mesh_display"]["C1_L_upper_rgb"], [25, 220, 100])
        self.assertEqual(config["mesh_display"]["C2_MVS_rgb"], [230, 45, 210])
        self.assertIsNone(config["scientific_verdict"])

    def test_descendant_traversal_is_building_scoped(self) -> None:
        objects = {
            "B": {"children": ["B-0", "B-1"]},
            "B-0": {"children": ["B-0-0"]},
            "B-0-0": {},
            "B-1": {},
            "OTHER": {},
        }
        self.assertEqual(descendant_ids(objects, "B"), ["B", "B-0", "B-1", "B-0-0"])
        self.assertEqual(descendant_ids(objects, "MISSING"), [])

    def test_obj_outputs_have_named_entities_and_local_coordinates(self) -> None:
        feature = {
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[10.0, 20.0], [12.0, 20.0], [12.0, 22.0], [10.0, 22.0], [10.0, 20.0]]],
            }
        }
        line = footprint_line_obj("TEST", feature, 30.0, np.asarray([10.0, 20.0, 25.0])).decode("ascii")
        self.assertIn("o 02_FOOTPRINT_TEST", line)
        self.assertIn("v 0.000000 0.000000 5.000000", line)
        triangle = np.asarray([[10.0, 20.0, 30.0], [11.0, 20.0, 30.0], [10.0, 21.0, 30.0]])
        mesh = triangles_obj("MESH_TEST", "mesh.mtl", "mesh", [triangle], np.asarray([10.0, 20.0, 25.0])).decode("ascii")
        self.assertIn("g MESH_TEST", mesh)
        self.assertIn("f 1 2 3", mesh)

    def test_host_wrapper_has_no_roofer_or_training_command(self) -> None:
        wrapper = DEFAULT_CONFIG.parents[3] / "scripts/p2/c1_c2_shared_footprint_199_v3/run_cloudcompare_review10_host.sh"
        text = wrapper.read_text(encoding="utf-8")
        self.assertIn("build_cloudcompare_review10.py", text)
        self.assertNotIn("3dgi/roofer", text)
        self.assertNotIn("src.stage2.train", text)


if __name__ == "__main__":
    unittest.main()

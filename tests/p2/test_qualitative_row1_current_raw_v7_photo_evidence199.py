import json
from pathlib import Path
import unittest

import numpy as np

from scripts.p2.qualitative_row1_current_raw_v7.build_photo_evidence199 import (
    boundary_loops,
    cityjson_roof_rings,
    load_config,
    project_overlay,
)


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v7/photo_evidence199_v3.json"


class PhotoEvidence199ContractTest(unittest.TestCase):
    def test_frozen_contract_is_full_population_and_no_keypoints(self):
        config = load_config(CONFIG)
        self.assertEqual(config["population"]["building_count"], 199)
        self.assertEqual(config["population"]["panels_per_building"], 4)
        self.assertFalse(config["overlays"]["keypoints_rendered"])
        self.assertFalse(config["overlays"]["partial_loops_rendered"])
        self.assertEqual(config["overlays"]["terminal_geometry_fallback"], "PHOTO_ONLY_NO_OVERLAY")
        self.assertIsNone(config["scientific_verdict"])

    def test_cityjson_extracts_only_roof_semantic_surface(self):
        data = {
            "transform": {"scale": [1, 1, 1], "translate": [0, 0, 0]},
            "vertices": [[0, 0, 5], [2, 0, 5], [2, 2, 5], [0, 2, 5], [0, 0, 0]],
            "CityObjects": {
                "B": {"children": ["B-part"]},
                "B-part": {
                    "geometry": [{
                        "lod": "2.2", "type": "Solid",
                        "boundaries": [[[[0, 1, 2, 3]], [[0, 1, 4]]]],
                        "semantics": {
                            "surfaces": [{"type": "RoofSurface"}, {"type": "WallSurface"}],
                            "values": [[0, 1]],
                        },
                    }]
                },
            },
        }
        rings = cityjson_roof_rings(data, "B")
        self.assertEqual(len(rings), 1)
        self.assertTrue(np.allclose(rings[0][0], rings[0][-1]))
        self.assertEqual(len(rings[0]), 5)

    def test_missing_and_terminal_fallback_are_explicit(self):
        loops, status = boundary_loops([], 0.005)
        self.assertEqual(loops, [])
        self.assertEqual(status["status"], "OUTPUT_MISSING")
        result = project_overlay([], None, (1, 1, np.asarray([])), {}, [0, 0, 1, 1], [1, 1], status, True, "orthometric")
        self.assertEqual(result["status"], "OMITTED_NO_BUILDING_SPARSE_CONFIRMATION")
        self.assertEqual(result["polylines"], [])

    def test_reference_temporal_labels_require_current_match(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        review = config["reference_temporal_review"]
        self.assertEqual(review["official_structure_reference_requires"], "CURRENT_MATCH_VERIFIED")
        self.assertTrue(review["per_building_best_condition_is_not_reference"])


class IntegratedViewerSourceTest(unittest.TestCase):
    def test_photo_drawer_and_temporal_csv_are_present(self):
        html = (REPO / "src/apps/c1_c2_roofer_web_review/index.html").read_text(encoding="utf-8")
        javascript = (REPO / "src/apps/c1_c2_roofer_web_review/app.js").read_text(encoding="utf-8")
        self.assertIn("photoDrawer", html)
        self.assertIn("photoDrawer", javascript)
        self.assertNotIn("openPhotos", html)
        self.assertNotIn("openPhotos", javascript)
        self.assertLess(html.index('id="photoDrawer"'), html.index('id="reviewbar"'))
        self.assertIn("jointbuildgs-c1-c2-roofer-ox-v1", javascript)
        self.assertIn("projectedRowImage", javascript)
        self.assertIn("building.projected_row.path", javascript)
        self.assertNotIn("polylineSvg", javascript)
        self.assertNotIn("<svg", javascript)
        self.assertNotIn("photoLidar", html)
        self.assertNotIn("photoMvs", html)


if __name__ == "__main__":
    unittest.main()

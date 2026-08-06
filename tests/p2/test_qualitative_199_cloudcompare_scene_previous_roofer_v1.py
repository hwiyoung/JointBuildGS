from __future__ import annotations

import json
import unittest

import numpy as np

from scripts.p2.qualitative_199_cloudcompare_scene_v1 import add_previous_roofer as extension


class PreviousRooferExtensionV1Tests(unittest.TestCase):
    def test_config_marks_historical_mvs_as_visual_only(self) -> None:
        config = extension.load_config(extension.DEFAULT_CONFIG)
        self.assertFalse(config["formal_six_row_reuse_allowed"])
        self.assertIn("MISMATCH", config["methods"]["C2_MVS"]["lineage_compatibility_with_parent_cloud"])
        self.assertEqual(config["execution"]["roofer_invocations"], 0)
        self.assertIsNone(config["scientific_verdict"])

    def test_cityjsonseq_solid_is_transformed_and_triangulated(self) -> None:
        header = {
            "type": "CityJSON",
            "version": "2.0",
            "CityObjects": {},
            "vertices": [],
            "transform": {"scale": [0.1, 0.1, 0.1], "translate": [100.0, 200.0, 300.0]},
        }
        feature = {
            "type": "CityJSONFeature",
            "id": "COMP_TEST",
            "vertices": [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]],
            "CityObjects": {
                "COMP_TEST-0": {
                    "type": "BuildingPart",
                    "geometry": [
                        {
                            "type": "Solid",
                            "lod": "2.2",
                            "boundaries": [[[[0, 1, 2, 3]]]],
                            "semantics": {"surfaces": [{"type": "RoofSurface"}], "values": [[0]]},
                        }
                    ],
                }
            },
        }
        data = (json.dumps(header) + "\n" + json.dumps(feature) + "\n").encode()
        feature_id, triangles = extension.cityjsonseq_surfaces(data, np.asarray([90.0, 190.0, 295.0]))
        self.assertEqual(feature_id, "COMP_TEST")
        self.assertEqual(len(triangles), 2)
        self.assertTrue(all(surface_type == "RoofSurface" for surface_type, _triangle in triangles))
        points = np.concatenate([triangle for _surface_type, triangle in triangles], axis=0)
        np.testing.assert_allclose(points.min(axis=0), [10.0, 10.0, 5.0])
        np.testing.assert_allclose(points.max(axis=0), [11.0, 11.0, 5.0])


if __name__ == "__main__":
    unittest.main()

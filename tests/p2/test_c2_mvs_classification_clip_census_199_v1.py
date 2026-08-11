import json
from pathlib import Path
import tempfile
import unittest

from shapely.geometry import Polygon

from scripts.p2.c2_mvs_classification_clip_census_199_v1.analyze import (
    _ground_union,
    _status,
    load_config,
    validate_config,
)


class C2MVSClassificationClipCensusTest(unittest.TestCase):
    def test_config_keeps_nonconfirmatory_boundary(self):
        config = load_config()
        validate_config(config)
        self.assertIsNone(config["interpretation"]["official_PASS_usable"])
        self.assertIsNone(config["interpretation"]["scientific_verdict"])
        self.assertEqual(config["population"]["building_count"], 199)

    def test_status_requires_valid_lod22(self):
        feature = {
            "id": "B1",
            "vertices": [[0, 0, 0]],
            "CityObjects": {
                "B1": {
                    "type": "Building",
                    "attributes": {"rf_success": True, "rf_pointcloud_unusable": False},
                    "geometry": [],
                }
            },
        }
        self.assertEqual(_status(feature, True), ("FAILED", "missing_lod22_geometry"))

    def test_ground_union_uses_ground_surface_only(self):
        feature = {
            "id": "B1",
            "vertices": [
                [0, 0, 0], [1000, 0, 0], [1000, 1000, 0], [0, 1000, 0],
                [0, 0, 1000], [1000, 0, 1000], [1000, 1000, 1000], [0, 1000, 1000],
            ],
            "CityObjects": {
                "B1": {
                    "type": "Building",
                    "geometry": [{
                        "type": "Solid",
                        "lod": "2.2",
                        "boundaries": [[
                            [[0, 1, 2, 3]],
                            [[4, 5, 6, 7]],
                        ]],
                        "semantics": {
                            "surfaces": [{"type": "GroundSurface"}, {"type": "RoofSurface"}],
                            "values": [[0, 1]],
                        },
                    }],
                }
            },
        }
        transform = {"scale": [0.001, 0.001, 0.001], "translate": [10.0, 20.0, 0.0]}
        geometry = _ground_union(feature, transform)
        self.assertIsNotNone(geometry)
        self.assertAlmostEqual(geometry.area, 1.0)
        self.assertTrue(geometry.equals(Polygon([(10, 20), (11, 20), (11, 21), (10, 21)])))


if __name__ == "__main__":
    unittest.main()

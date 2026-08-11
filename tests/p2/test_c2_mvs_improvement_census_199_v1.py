import unittest
import json

import numpy as np

from scripts.p2.c2_mvs_improvement_census_199_v1.analyze import (
    candidate_accuracy,
    primary_track,
    roof_triangles_by_building,
)


class C2MVSImprovementCensusTest(unittest.TestCase):
    def test_aoi_boundary_has_precedence(self):
        self.assertEqual(primary_track({"AOI_BOUNDARY_CONFOUNDED", "RAW_MVS_SUPPORT_LOW"}, None), "AOI_BOUNDARY_REPLAY")

    def test_raw_support_precedes_downstream_flags(self):
        self.assertEqual(primary_track({"RAW_MVS_SUPPORT_LOW", "NO_CLIP_TOPOLOGY_INVALID"}, False), "MVS_RAW_GEOMETRY_SUPPORT")

    def test_candidate_accuracy_applies_all_bands(self):
        thresholds = {
            "reference_vertical_coverage_min": 0.8,
            "height_error_mae_m_max": 1.0,
            "RMSZ_m_max": 1.0,
            "RMSXY_m_max": 1.0,
            "surface_distance_rmse_m_max": 1.0,
            "surface_distance_p95_m_max": 2.0,
        }
        metrics = {
            "reference_vertical_coverage": 1.0,
            "height_error_mae_m": 0.5,
            "RMSZ_m": 0.7,
            "RMSXY_m": 0.1,
            "surface_distance_rmse_m": 0.8,
            "surface_distance_p95_m": 2.1,
        }
        self.assertFalse(candidate_accuracy(metrics, thresholds))
        metrics["surface_distance_p95_m"] = 1.9
        self.assertTrue(candidate_accuracy(metrics, thresholds))

    def test_roof_triangulation_preserves_inner_ring(self):
        header = {
            "type": "CityJSON", "version": "2.0", "CityObjects": {}, "vertices": [],
            "transform": {"scale": [1, 1, 1], "translate": [0, 0, 0]},
        }
        feature = {
            "type": "CityJSONFeature",
            "CityObjects": {
                "B1": {
                    "type": "Building",
                    "geometry": [{
                        "type": "MultiSurface", "lod": "2.2",
                        "boundaries": [[[0, 1, 2, 3], [4, 5, 6, 7]]],
                        "semantics": {"surfaces": [{"type": "RoofSurface"}], "values": [0]},
                    }],
                }
            },
            "vertices": [[0, 0, 1], [10, 0, 1], [10, 10, 1], [0, 10, 1], [4, 4, 1], [6, 4, 1], [6, 6, 1], [4, 6, 1]],
        }
        data = (json.dumps(header) + "\n" + json.dumps(feature) + "\n").encode()
        triangles = roof_triangles_by_building(data)["B1"]
        area = sum(abs(float(np.cross(t[1, :2] - t[0, :2], t[2, :2] - t[0, :2]))) / 2 for t in triangles)
        self.assertAlmostEqual(area, 96.0)


if __name__ == "__main__":
    unittest.main()

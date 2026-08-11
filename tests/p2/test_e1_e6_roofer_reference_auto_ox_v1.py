import json
from pathlib import Path
import unittest

import numpy as np
from shapely.geometry import Polygon

from scripts.p2.e1_e6_roofer_ox_review_v1.build_reference_auto_ox_v1 import (
    classify_binary,
    cityjson_g0_g1,
    load_config,
    plane_match_metrics,
)


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/p2/e1_e6_roofer_ox_review_v1/reference_auto_ox_v1.json"


def plane(points, normal=(0.0, 0.0, 1.0), z=5.0):
    polygon = Polygon(points)
    normal = np.asarray(normal, dtype=np.float64)
    normal /= np.linalg.norm(normal)
    a = -normal[0] / normal[2]
    b = -normal[1] / normal[2]
    center = polygon.centroid
    c = z - a * center.x - b * center.y
    return {
        "polygon": polygon,
        "area_m2": polygon.area,
        "normal": normal,
        "z_center": z,
        "plane_coefficients": (a, b, c),
    }


class ReferenceAutoOxV1Tests(unittest.TestCase):
    def test_config_is_binary_development_only(self):
        config = load_config(CONFIG)
        self.assertEqual(config["classification_labels"], ["O", "X", "NA"])
        self.assertFalse(config["review_is_outcome"])
        self.assertEqual(config["primary_threshold"], "O50")
        self.assertIsNone(config["official_PASS_usable"])
        self.assertIsNone(config["scientific_verdict"])

    def test_cityjson_contract_requires_lod2_and_roof_wall_ground(self):
        geometry = {
            "lod": "2.2",
            "boundaries": [[[[0, 1, 2]]]],
            "semantics": {"surfaces": [{"type": "RoofSurface"}, {"type": "WallSurface"}, {"type": "GroundSurface"}]},
        }
        cityjson = {"CityObjects": {"b": {"type": "Building", "geometry": [geometry]}}}
        self.assertEqual(cityjson_g0_g1(cityjson, "b")[:2], (True, True))
        geometry["semantics"]["surfaces"].pop()
        self.assertEqual(cityjson_g0_g1(cityjson, "b")[:2], (True, False))

    def test_one_to_one_plane_matching_exposes_gable_collapse(self):
        reference = [
            plane([(0, 0), (10, 0), (10, 5), (0, 5)]),
            plane([(0, 5), (10, 5), (10, 10), (0, 10)], normal=(0.0, 0.2, 0.98)),
        ]
        prediction = [plane([(0, 0), (10, 0), (10, 10), (0, 10)])]
        metrics = plane_match_metrics(reference, prediction, 0.5, 15.0, 0.5)
        self.assertEqual(metrics["reference_plane_count"], 2)
        self.assertEqual(metrics["prediction_plane_count"], 1)
        self.assertEqual(metrics["match_count"], 1)
        self.assertEqual(metrics["area_completeness"], 1.0)
        self.assertLess(metrics["plane_area_recall"], 0.8)

    def test_missing_prediction_is_x_and_missing_reference_only_is_na(self):
        thresholds = json.loads(CONFIG.read_text())["acceptance_thresholds"]
        missing = classify_binary(g0=False, g1=False, g2=False, g3={}, g4={}, reference_available=False, thresholds=thresholds)
        self.assertEqual(missing["verdict"], "X")
        no_reference = classify_binary(g0=True, g1=True, g2=True, g3={}, g4={}, reference_available=False, thresholds=thresholds)
        self.assertEqual(no_reference["verdict"], "NA")

    def test_primary_pass_is_conjunction_without_review(self):
        thresholds = json.loads(CONFIG.read_text())["acceptance_thresholds"]
        g3 = {
            "reference_plane_count": 2,
            "prediction_plane_count": 2,
            "area_completeness": .9,
            "area_correctness": .9,
            "area_quality": .82,
            "plane_area_recall": .9,
            "plane_area_precision": .9,
        }
        g4 = {"reference_cell_count": 20, "coverage": .9, "rmse_z_m": .4, "p95_abs_z_m": 1.0, "median_bias_z_m": .2}
        result = classify_binary(g0=True, g1=True, g2=True, g3=g3, g4=g4, reference_available=True, thresholds=thresholds)
        self.assertEqual(result["verdict"], "O")
        self.assertNotIn("REVIEW", json.dumps(result))
        g4["rmse_z_m"] = 1.01
        result = classify_binary(g0=True, g1=True, g2=True, g3=g3, g4=g4, reference_available=True, thresholds=thresholds)
        self.assertEqual(result["verdict"], "X")
        self.assertIn("G4_RMSZ_HIGH", result["failure_reasons"])


if __name__ == "__main__":
    unittest.main()

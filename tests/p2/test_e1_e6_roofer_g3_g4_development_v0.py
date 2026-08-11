import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from scripts.p2.e1_e6_roofer_ox_review_v1.add_development_g3_g4_v0 import (
    classify_g3,
    classify_g4,
    load_config,
    patch_app,
    patch_index,
    top_surface_z,
)


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/p2/e1_e6_roofer_ox_review_v1/development_g3_g4_v0.json"


class DevelopmentG3G4V0Tests(unittest.TestCase):
    def test_contract_is_development_only(self):
        config = load_config(CONFIG)
        self.assertEqual(config["criterion_version"], "ROOFER_G3G4_DEVELOPMENT_V0P1_NOT_FROZEN")
        self.assertIsNone(config["official_PASS_usable"])
        self.assertIsNone(config["scientific_verdict"])
        self.assertIn("SELF_REFERENCE", config["structure_reference"]["independence_class"])

    def test_g3_o_review_x_bands(self):
        thresholds = json.loads(CONFIG.read_text())["thresholds"]
        base = {"reference_plane_count": 2, "prediction_plane_count": 2}
        self.assertEqual(classify_g3({**base, "area_completeness": .9, "area_correctness": .9, "area_quality": .8}, thresholds)[0], "O_CANDIDATE")
        self.assertEqual(classify_g3({**base, "area_completeness": .75, "area_correctness": .85, "area_quality": .65}, thresholds)[0], "REVIEW")
        self.assertEqual(classify_g3({**base, "area_completeness": .6, "area_correctness": .9, "area_quality": .6}, thresholds)[0], "X_CANDIDATE")
        self.assertEqual(classify_g3({**base, "prediction_plane_count": 1, "area_completeness": .9, "area_correctness": .9, "area_quality": .8}, thresholds)[0], "X_CANDIDATE")

    def test_g4_o_review_x_bands(self):
        thresholds = json.loads(CONFIG.read_text())["thresholds"]
        self.assertEqual(classify_g4({"reference_cell_count": 30, "coverage": .9, "rmse_z_m": .8, "p95_abs_z_m": 1.8, "median_bias_z_m": .2}, thresholds, 20)[0], "O_CANDIDATE")
        self.assertEqual(classify_g4({"reference_cell_count": 30, "coverage": .75, "rmse_z_m": 1.2, "p95_abs_z_m": 2.4, "median_bias_z_m": .6}, thresholds, 20)[0], "REVIEW")
        self.assertEqual(classify_g4({"reference_cell_count": 30, "coverage": .9, "rmse_z_m": 1.6, "p95_abs_z_m": 2.4, "median_bias_z_m": .6}, thresholds, 20)[0], "X_CANDIDATE")
        self.assertEqual(classify_g4({"reference_cell_count": 10}, thresholds, 20)[0], "NOT_ASSESSED")

    def test_top_surface_interpolation(self):
        triangles = np.asarray([[[0., 0., 1.], [1., 0., 2.], [0., 1., 1.]]])
        values = top_surface_z(triangles, np.asarray([[.25, .25], [2., 2.]]))
        self.assertAlmostEqual(values[0], 1.25)
        self.assertTrue(np.isnan(values[1]))

    def test_v14_application_patch_is_explicitly_nonofficial(self):
        artifact = Path("/artifacts/JointBuildGS/phase-payloads/p2/e1_e6_roofer_ox_review_v1/P2-E1-E6-ROOFER-OX-REVIEW-v14")
        app = patch_app((artifact / "app.js").read_text(encoding="utf-8"))
        index = patch_index((artifact / "index.html").read_text(encoding="utf-8"))
        self.assertIn("developmentLabel", app)
        self.assertIn("NOT_ASSESSED_AOI", app)
        self.assertIn("development v0", index)
        self.assertIn("v16-g3g4-dev0p1", index)


if __name__ == "__main__":
    unittest.main()

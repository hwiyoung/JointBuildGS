import json
from pathlib import Path
import unittest

from scripts.p2.e1_e6_roofer_ox_review_v1.build_adjudication_e2_baseline_v1 import (
    load_config,
    patch_app,
    patch_index,
)


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/p2/e1_e6_roofer_ox_review_v1/adjudication_e2_baseline_v1.json"
BLIND_CONFIG = REPO / "configs/p2/e1_e6_roofer_ox_review_v1/adjudication_e2_baseline_blind_v2.json"


class E2BaselineAdjudicationTests(unittest.TestCase):
    def test_contract_keeps_e2_product_and_e3_mechanism_separate(self):
        config = load_config(CONFIG)
        self.assertEqual(config["product_baseline"], "E2_MVS")
        self.assertEqual(config["mechanism_ablation"], "E3_GS_image")
        self.assertEqual(config["primary_product_contrast"], "E5-vs-E2")
        self.assertIsNone(config["official_PASS_usable"])
        self.assertIsNone(config["scientific_verdict"])

    def test_adjudication_source_shows_product_and_mechanism_transitions(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        source = (REPO / config["application_sources"]["js"]["path"]).read_text(encoding="utf-8")
        self.assertIn("E2 product baseline", source)
        self.assertIn("E3 GS-only", source)
        self.assertIn("E2 → E5 · PRIMARY", source)
        self.assertIn("prior incremental rescue", source)
        self.assertIn("REGRESSION", source)
        self.assertIn("jointbuildgs-e1-e6-roofer-ox-v4", source)

    def test_parent_index_patch_is_additive(self):
        parent = "<html><head><title>JointBuildGS E1-E6 Roofer O/X Review</title><style>x</style>\n</head><body>x</body></html>"
        result = patch_index(parent)
        self.assertIn("adjudication.css?v=e2-baseline-v1", result)
        self.assertIn("adjudication.js?v=e2-baseline-v1", result)
        self.assertIn("E2-baseline Roofer O/X Adjudication", result)

    def test_blind_mode_separates_reviewers_and_hides_condition_labels(self):
        config = load_config(BLIND_CONFIG)
        self.assertEqual(config["reviewer_profiles"], ["R1", "R2"])
        self.assertEqual(config["calibration_sample_status"], "NOT_FROZEN_DEVELOPMENT_POOL_ONLY")
        source = (REPO / config["application_sources"]["js"]["path"]).read_text(encoding="utf-8")
        self.assertIn("blindPermutation", source)
        self.assertIn("결과 ${code}", source)
        self.assertIn("panel-stats", source)
        app = patch_app("const STORAGE_KEY = 'jointbuildgs-e1-e6-roofer-ox-v4';", config)
        self.assertIn("REVIEWER_ID", app)
        self.assertIn("-${REVIEWER_ID}", app)


if __name__ == "__main__":
    unittest.main()

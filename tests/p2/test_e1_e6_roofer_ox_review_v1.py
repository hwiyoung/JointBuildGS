import json
from pathlib import Path
import unittest

from scripts.p2.e1_e6_roofer_ox_review_v1.build import build_app, build_index, load_config


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/p2/e1_e6_roofer_ox_review_v1/run_v1.json"


class E1E6RooferOxReviewTests(unittest.TestCase):
    def test_condition_availability_and_verdict_contract(self):
        config = load_config(CONFIG)
        self.assertEqual(
            config["conditions"],
            {
                "E1": "AVAILABLE_CURRENT_UAS_LIDAR",
                "E2": "AVAILABLE_CURRENT_IMAGE_MVS",
                "E3": "AVAILABLE_NEW_30K_IMAGE_ONLY_GS",
                "E4": "AVAILABLE_EXISTING_LEGACY_BASE",
                "E5": "AVAILABLE_EXISTING_LEGACY_BASE",
                "E6": "AVAILABLE_EXISTING_LEGACY_BASE",
            },
        )
        self.assertIsNone(config["official_PASS_usable"])
        self.assertIsNone(config["scientific_verdict"])
        self.assertEqual(config["comparison_priors"]["existing_lod2"]["role"], "REFERENCE_DERIVED_DIAGNOSTIC_COMPARISON_ONLY")
        self.assertEqual(config["comparison_priors"]["source_world_shift_xyz"], [690953.0, 5336071.0, 604.0])

    def test_generated_app_exports_long_e1_e6_rows(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        source = (REPO / config["application_sources"]["app"]["path"]).read_text(encoding="utf-8")
        app = build_app(source, config["local_storage_key"])
        self.assertIn("building.conditions.E3.technical_status", app)
        self.assertIn("building.conditions.E4.technical_status", app)
        self.assertIn("new ReviewViewer('e6Viewport'", app)
        self.assertIn("new ReviewViewer('priorAlsViewport'", app)
        self.assertIn("new ReviewViewer('priorLod2Viewport'", app)
        self.assertIn("building.comparison_priors", app)
        self.assertIn("priorLod2Mesh", app)
        self.assertIn("'human_roofer_ox'", app)
        self.assertIn("'x_reason'", app)
        self.assertIn("'reviewer_reason'", app)
        self.assertIn("lidarReasonNote", app)
        self.assertIn("e6ReasonNote", app)
        self.assertIn("diagnostic_summary", app)
        self.assertIn("compactGateSummary", app)
        self.assertIn("G3 ? · G4 ?", app)
        self.assertIn("LoD2 없음 · coverage 부족", app)
        self.assertIn("auto-x", app)
        self.assertNotIn("c3_1", app)
        self.assertNotIn("c3_2", app)

    def test_generated_index_has_eight_panel_layout_and_separate_mesh_notice(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        source = (REPO / config["application_sources"]["index"]["path"]).read_text(encoding="utf-8")
        index = build_index(source)
        self.assertIn("grid-template-rows: auto auto auto auto auto minmax(0, 1fr);", index)
        self.assertIn('id="e4Viewport"', index)
        self.assertIn('id="e5Viewport"', index)
        self.assertIn('id="e6Viewport"', index)
        self.assertIn('id="priorAlsViewport"', index)
        self.assertIn('id="priorLod2Viewport"', index)
        self.assertIn("repeat(4, minmax(260px, 1fr))", index)
        self.assertIn("reference-derived diagnostic", index)
        self.assertIn("LEGACY BASE", index)
        self.assertIn("Semantic textured mesh O/X는 별도 계약", index)
        self.assertIn("자동 후보 X", index)
        self.assertIn("G3/G4는 threshold 미동결", index)
        self.assertIn("app.js?v=e1e6-roofer-ox-v14", index)
        self.assertIn('id="lidarReasonNote"', index)
        self.assertIn('id="e6ReasonNote"', index)
        self.assertIn("성공/실패 이유를 짧게 입력", index)
        self.assertIn("사람 판정 O/X", index)
        self.assertIn("#lidarViewport + .panel-label", index)
        self.assertIn('value="E3_GS_image"', index)


if __name__ == "__main__":
    unittest.main()

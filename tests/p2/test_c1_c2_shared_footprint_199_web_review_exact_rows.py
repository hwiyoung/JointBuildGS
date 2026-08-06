import json
from pathlib import Path
import unittest

from scripts.p2.c1_c2_shared_footprint_199_v3.build_web_review199_exact_rows import load_config


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/p2/c1_c2_shared_footprint_199_v3/web_review199_exact_rows_v5.json"


class ExactRowsWebReviewContractTest(unittest.TestCase):
    def test_web_consumes_exact_png_without_redraw(self):
        config = load_config(CONFIG)
        self.assertEqual(config["features"]["building_count"], 199)
        self.assertEqual(config["features"]["row_png_count"], 199)
        self.assertEqual(config["features"]["source"], "EXACT_FROZEN_PREVIEW10_V4_RENDERED_PNG_BYTES")
        self.assertFalse(config["features"]["browser_redraw"])
        self.assertIsNone(config["scientific_verdict"])

    def test_application_has_one_exact_row_image_and_no_projection_code(self):
        html = (REPO / "src/apps/c1_c2_roofer_web_review/index.html").read_text(encoding="utf-8")
        javascript = (REPO / "src/apps/c1_c2_roofer_web_review/app.js").read_text(encoding="utf-8")
        self.assertIn('id="projectedRowImage"', html)
        self.assertIn("grid-template-rows: auto 220px", html)
        self.assertIn("width: 100%; height: 210px; object-fit: contain", html)
        self.assertIn("#projectedRowImage { height: 160px; }", html)
        self.assertIn("place-items: center; overflow: hidden", html)
        self.assertNotIn("32vh", html)
        self.assertLess(html.index('id="photoDrawer"'), html.index('id="reviewbar"'))
        self.assertIn("building.projected_row.path", javascript)
        for forbidden in ("polylineSvg", "createElementNS", "projection.polylines", "<svg"):
            self.assertNotIn(forbidden, html + javascript)
        self.assertIn("jointbuildgs-c1-c2-roofer-ox-v1", javascript)


if __name__ == "__main__":
    unittest.main()

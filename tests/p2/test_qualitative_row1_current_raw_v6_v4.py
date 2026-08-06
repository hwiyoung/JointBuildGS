import json
from pathlib import Path
import unittest

from PIL import Image, ImageFont

from scripts.p2.qualitative_row1_current_raw_v6.preview10_v4 import photo_only_panel


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v6/preview10_v4.json"


class PhotoOnlyPanelTest(unittest.TestCase):
    def test_photo_region_is_not_modified_by_a_roofline(self):
        raw = Image.new("RGB", (40, 30), (0, 0, 0))
        render = {
            "cell_width_px": 80,
            "cell_header_height_px": 116,
            "cell_image_height_px": 60,
            "cell_background_rgb": [0, 0, 0],
            "text_rgb": [255, 255, 255],
            "muted_text_rgb": [150, 150, 150],
        }
        font = ImageFont.load_default()

        panel = photo_only_panel(raw, "TOP", "camera", render, font, font)

        image_region = panel.crop((0, 116, 80, 176))
        self.assertEqual(image_region.getbbox(), None)


class PreviewContractTest(unittest.TestCase):
    def test_v4_contract_omits_roofline_for_terminal_fallback(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        fallback = config["selection_fallback"]

        self.assertEqual(fallback["terminal_fallback_render"], "PHOTO_ONLY_NO_ROOFLINE")
        self.assertIn("ROOFLINE OMITTED", fallback["terminal_fallback_image_label"])
        self.assertTrue(fallback["terminal_fallback_has_no_building_sparse_confirmation"])
        self.assertFalse(config["preview"]["full_199_render_authorized"])
        self.assertIsNone(config["scientific_verdict"])


if __name__ == "__main__":
    unittest.main()

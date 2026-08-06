import json
from pathlib import Path
import unittest

from scripts.p2.qualitative_row1_current_raw_v6 import preview10_v4
from scripts.p2.qualitative_row1_current_raw_v6.render199_v1 import load_config


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v6/render199_v1.json"


class FrozenV6V4Render199ContractTest(unittest.TestCase):
    def test_only_membership_is_extended(self):
        config = load_config(CONFIG)
        self.assertEqual(config["population"]["building_count"], 199)
        self.assertEqual(config["extension_boundary"]["changed"], "ONLY_PREVIEW_MEMBERSHIP_FROM_FIXED_10_TO_ORDERED_199")
        self.assertEqual(config["extension_boundary"]["web_consumption"], "COPY_EXACT_RENDERED_ROW_PNG_BYTES_NO_REDRAW")
        self.assertEqual(config["frozen_entrypoint"]["git_path"], "scripts/p2/qualitative_row1_current_raw_v6/preview10_v4.py")
        self.assertIsNone(config["scientific_verdict"])

    def test_exact_frozen_renderer_is_imported(self):
        self.assertEqual(
            preview10_v4.render_building.__module__,
            "scripts.p2.qualitative_row1_current_raw_v6.preview10_v4",
        )

    def test_frozen_contract_stays_preview10_only(self):
        frozen = json.loads((REPO / "configs/p2/qualitative_row1_current_raw_v6/preview10_v4.json").read_text(encoding="utf-8"))
        self.assertEqual(frozen["preview"]["building_count"], 10)
        self.assertFalse(frozen["preview"]["full_199_render_authorized"])


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


class ViewerConsolidationContractTest(unittest.TestCase):
    def test_two_viewer_roles_and_ring_variants(self):
        cfg = yaml.safe_load((ROOT / "configs/p2/viewer_consolidation_8876_8878_v1/viewer.yaml").read_text())
        self.assertIn("integrated", cfg["viewer_8876"]["role"])
        self.assertIn("detailed", cfg["viewer_8878"]["role"])
        self.assertTrue(cfg["e3"]["variant_id"].startswith("RING_"))
        self.assertTrue(cfg["e4"]["variant_id"].startswith("RING_"))
        self.assertIsNone(cfg["scientific_verdict"])

    def test_responsive_and_preservation_contract_is_explicit(self):
        text = (ROOT / "scripts/p2/viewer_consolidation_8876_8878_v1/build.py").read_text()
        self.assertIn("max-width:1400px", text)
        self.assertIn("max-width:720px", text)
        self.assertIn("mvs-seed-color-v3 application state changed", text)
        self.assertIn('"viewer_8878_slots_deleted": 0', text)
        self.assertIn('id="toggleRooferWireframe"', text)
        self.assertIn("function setRooferWireframe", text)
        self.assertIn("const minOrbitDistance = 0.75", text)
        self.assertIn('"roofer_mesh_display_modes": ["solid", "wireframe"]', text)


if __name__ == "__main__":
    unittest.main()

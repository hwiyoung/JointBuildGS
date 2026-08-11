import json
from pathlib import Path
import unittest

from scripts.p2.viewer_8876_new_e3_fullscene_30k_v1.build import (
    load_config,
    patch_app,
    updated_manifest,
)


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/p2/viewer_8876_new_e3_fullscene_30k_v1/run_v1.json"


class Viewer8876NewE3Tests(unittest.TestCase):
    def test_config_is_viewer_only_and_null_verdict(self):
        config = load_config(CONFIG)
        self.assertEqual(config["variant"]["step"], 30000)
        self.assertEqual(sum(config["execution"].values()), 0)
        self.assertIsNone(config["official_PASS_usable"])
        self.assertIsNone(config["scientific_verdict"])

    def test_manifest_preserves_variants_and_selects_new_default(self):
        manifest = {"panels": [{"condition": "E3", "id": "OLD", "variants": [{"id": "OLD"}]}], "scientific_verdict": None}
        variant = {"id": "NEW", "condition": "E3", "scientific_verdict": None}
        result = updated_manifest(manifest, variant, "receipt.json")
        panel = result["panels"][0]
        self.assertEqual([item["id"] for item in panel["variants"]], ["OLD", "NEW"])
        self.assertEqual(panel["id"], "NEW")
        self.assertEqual(result["e3_default_variant"], "NEW")
        self.assertIsNone(result["scientific_verdict"])

    def test_surface_mode_uses_explicit_roofer_fallback(self):
        source = """let surfaceMeshesVisible = true;
let rooferMeshesVisible = false;
function setRooferWireframe(object, enabled) {}
  object.visible = rooferMeshesVisible;
    viewer.object.visible = rooferMeshesVisible;
  for (const viewer of viewers) viewer.surface.visible = surfaceMeshesVisible;
  for (const viewer of viewers) viewer.object.visible = rooferMeshesVisible;
? 'E1 UAS LiDAR 전체 범위 + E2 OpenMVS + E3-E6 TSDF 표면 mesh 표시'
"""
        result = patch_app(source)
        self.assertIn("surface_fallback_to_roofer", result)
        self.assertIn("rooferObjectVisible(next.spec)", result)
        self.assertIn("surface 미생성으로 Roofer LoD fallback", result)


if __name__ == "__main__":
    unittest.main()

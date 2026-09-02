from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.phd.mvs_als_source_relation_viewer_v1 import build as viewer


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/phd/mvs_als_source_relation_viewer_v1/viewer_v1.json"
APP = REPO / "src/apps/mvs_als_source_relation_viewer_v1"


class SourceRelationViewerV1Tests(unittest.TestCase):
    def test_config_freezes_five_classes_and_null_verdict(self):
        cfg = viewer.load_config(CONFIG)
        self.assertIsNone(cfg["scientific_verdict"])
        self.assertEqual(set(cfg["classes"]), {"1", "2", "3", "4", "5"})
        self.assertEqual(cfg["render_queue_classes"], [2, 3, 4])
        self.assertEqual(cfg["display_sampling"]["role"], "DISPLAY_ONLY_NO_METHOD_FEEDBACK")

    def test_input_paths_exclude_evaluation_sources(self):
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        inputs = json.dumps({
            "root": cfg["source_relation_relative_root"],
            "expected": cfg["expected_inputs"],
        }).lower()
        for token in ("uas", "lod2", "footprint", "stable_id", "journal1"):
            self.assertNotIn(token, inputs)

    def test_app_exposes_both_sources_and_all_label_controls(self):
        html = (APP / "index.html").read_text(encoding="utf-8")
        app = (APP / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="show-mvs"', html)
        self.assertIn('id="show-als"', html)
        self.assertIn('id="class-controls"', html)
        self.assertIn('id="preset-queue"', html)
        self.assertIn('id="preset-robust"', html)
        self.assertIn("for (let classId = 1; classId <= 5; classId++)", app)
        self.assertIn("selectCore", app)

    def test_app_has_no_remote_browser_dependency(self):
        for name in ("index.html", "app.js", "styles.css"):
            text = (APP / name).read_text(encoding="utf-8")
            self.assertNotIn("https://", text)
            self.assertNotIn("http://", text)


if __name__ == "__main__":
    unittest.main()

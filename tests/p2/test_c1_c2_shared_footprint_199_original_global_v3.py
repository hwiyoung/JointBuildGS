from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.p2.c1_c2_shared_footprint_199_v3 import run


CONFIG = Path("configs/p2/c1_c2_shared_footprint_199_v3/original_global_v3.json")


class OriginalGlobalV3Tests(unittest.TestCase):
    def test_contract_is_two_global_roofer_calls_with_defaults(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        run.validate_config(config)
        self.assertEqual(config["roofer"]["expected_invocations"], 2)
        self.assertEqual(config["roofer"]["quality_parameters"], "ROOFER_DEFAULTS")
        self.assertFalse(config["classification"]["voxel_downsampling"])
        self.assertTrue(config["classification"]["same_adapter_for_both_conditions"])

    def test_lidar_pipeline_retags_without_coordinate_transform(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        pipeline = run._classification_pipeline(
            "C1_L_upper", Path("/input.laz"), Path("/footprints.geojson"), Path("/output.laz"), config
        )["pipeline"]
        self.assertEqual(pipeline[0]["override_srs"], "EPSG:25832")
        self.assertFalse(any(stage.get("type") == "filters.reprojection" for stage in pipeline))
        self.assertEqual([stage["type"] for stage in pipeline].count("filters.overlay"), 1)

    def test_mvs_pipeline_uses_frozen_translation_and_same_classifier(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        pipeline = run._classification_pipeline(
            "C2_MVS", Path("/input.ply"), Path("/footprints.geojson"), Path("/output.laz"), config
        )["pipeline"]
        transform = next(stage for stage in pipeline if stage["type"] == "filters.transformation")
        self.assertIn("690953.000000000", transform["matrix"])
        self.assertEqual([stage["type"] for stage in pipeline].count("filters.smrf"), 1)
        self.assertEqual([stage["type"] for stage in pipeline].count("filters.overlay"), 1)

    def test_config_keeps_scientific_verdict_null(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertIsNone(config["official_PASS_usable"])
        self.assertIsNone(config["scientific_verdict"])


if __name__ == "__main__":
    unittest.main()

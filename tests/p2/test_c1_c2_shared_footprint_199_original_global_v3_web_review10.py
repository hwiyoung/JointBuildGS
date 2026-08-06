from __future__ import annotations

import re
import json
import unittest

from scripts.p2.c1_c2_shared_footprint_199_v3.build_web_review10 import (
    DEFAULT_CONFIG,
    load_config,
)


class WebReview10V1Tests(unittest.TestCase):
    def test_human_review_lock_is_exactly_ox_and_not_official_pass(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        criterion_path = DEFAULT_CONFIG.parents[3] / config["review"]["criterion_git_path"]
        criterion = json.loads(criterion_path.read_text(encoding="utf-8"))
        self.assertEqual(criterion["criterion_id"], "P2-ROOFER-HUMAN-OX-v1")
        self.assertEqual(criterion["allowed_labels"], ["", "O", "X"])
        self.assertEqual(criterion["gs_transition"]["rescue"], "C2_MVS=X and C3_GS_image=O")
        self.assertIsNone(criterion["official_pass_usable"])
        self.assertIsNone(criterion["scientific_verdict"])

    def test_config_is_frozen_static_dual_view_with_precision_tools(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        self.assertEqual(config["features"]["building_count"], 199)
        self.assertTrue(config["features"]["synchronized_dual_view"])
        self.assertEqual(config["features"]["fixed_views"], ["TOP", "OBLIQUE", "SIDE"])
        self.assertIn("TWO_POINT_DISTANCE", config["features"]["precision_tools"])
        self.assertIn("Z_CLIPPING", config["features"]["precision_tools"])
        self.assertIn("ROOF_CENTRIC_FIT", config["features"]["precision_tools"])
        self.assertTrue(config["application"]["offline_static"])
        self.assertEqual(config["features"]["review_labels"], ["", "O", "X"])
        self.assertEqual(config["features"]["review_input_ui"], "TWO_TOGGLE_BUTTONS_O_X")
        self.assertEqual(config["features"]["point_color_modes"], ["RGB", "CONDITION_SOLID"])
        self.assertTrue(config["features"]["whole_scene_overview"])
        self.assertEqual(config["features"]["overview_building_count"], 199)
        self.assertEqual(config["features"]["detail_overview_minimap"], "TOP_VIEW_199_BUILDINGS_WITH_POINT_AVAILABILITY")
        self.assertEqual(config["point_display"]["rgb_divisor"], {"C1_L_upper": 256, "C2_MVS": 1})
        self.assertEqual(config["point_display"]["default_point_size_px"], 3.5)
        self.assertEqual(config["point_display"]["detail_spatial_index_tile_m"], 32.0)
        self.assertEqual(config["execution"]["roofer_invocations"], 0)
        self.assertIsNone(config["scientific_verdict"])

    def test_application_contains_required_controls_and_no_remote_dependency(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        index = (DEFAULT_CONFIG.parents[3] / config["application"]["index_git_path"]).read_text(encoding="utf-8")
        script = (DEFAULT_CONFIG.parents[3] / config["application"]["javascript_git_path"]).read_text(encoding="utf-8")
        for element_id in (
            "lidarViewport", "mvsViewport", "buildingSelect", "syncCamera", "miniMapCanvas",
            "clipEnabled", "measureMode", "lidarReview", "mvsReview", "exportCsv", "colorMode",
        ):
            self.assertIn(f'id="{element_id}"', index)
        self.assertIn("parseBinaryPly", script)
        self.assertIn("parseObj", script)
        self.assertIn("TWO", "TWO")
        self.assertIn("localStorage", script)
        self.assertIn("distanceTo", script)
        self.assertIn("clippingPlane", script)
        self.assertIn("sizeAttenuation: false", script)
        self.assertIn("new URLSearchParams", script)
        self.assertIn("function roofFocus", script)
        self.assertIn("shareRoofFocus", script)
        self.assertIn('data-review-method="lidar" data-value="O"', index)
        self.assertIn('data-review-method="lidar" data-value="X"', index)
        self.assertIn('data-review-method="mvs" data-value="O"', index)
        self.assertIn('data-review-method="mvs" data-value="X"', index)
        self.assertIn("function setReviewButtons", script)
        self.assertIn("function selectedReviewValue", script)
        self.assertIn("makeConditionColors", script)
        self.assertIn('value="3.5"', index)
        self.assertIn("pointSize: 3.5", script)
        self.assertIn("manifest.buildings.length", script)
        self.assertIn("WEB_REVIEW199_evaluation.csv", script)
        self.assertIn("function drawMiniMap", script)
        self.assertIn("두 조건 모두 표시점 없음", script)
        self.assertIn("overview.html?building=", script)
        self.assertNotIn("https://", index + script)
        self.assertNotIn("http://", index + script)
        html_ids = set(re.findall(r'id="([A-Za-z][A-Za-z0-9]*)"', index))
        used_elements = set(re.findall(r'elements\.([A-Za-z][A-Za-z0-9]*)', script))
        self.assertEqual(used_elements - html_ids, set())
        overview_index = (DEFAULT_CONFIG.parents[3] / config["application"]["overview_index_git_path"]).read_text(encoding="utf-8")
        overview_script = (DEFAULT_CONFIG.parents[3] / config["application"]["overview_javascript_git_path"]).read_text(encoding="utf-8")
        for element_id in ("overviewViewport", "overviewMethod", "buildingSelect", "colorMode", "focusBuilding"):
            self.assertIn(f'id="{element_id}"', overview_index)
        overview_ids = set(re.findall(r'id="([A-Za-z][A-Za-z0-9]*)"', overview_index))
        overview_used = set(re.findall(r'elements\.([A-Za-z][A-Za-z0-9]*)', overview_script))
        self.assertEqual(overview_used - overview_ids, set())
        self.assertIn("InstancedMesh", overview_script)
        self.assertIn('value="3.5"', overview_index)
        self.assertIn("pointSize: 3.5", overview_script)
        self.assertNotIn("https://", overview_index + overview_script)

    def test_host_wrappers_do_not_invoke_scientific_processing(self) -> None:
        repository = DEFAULT_CONFIG.parents[3]
        for name in ("run_web_review10_host.sh", "serve_web_review10_host.sh"):
            text = (repository / "scripts/p2/c1_c2_shared_footprint_199_v3" / name).read_text(encoding="utf-8")
            self.assertNotIn("3dgi/roofer", text)
            self.assertNotIn("src.stage2.train", text)
        wrapper = (repository / "scripts/p2/c1_c2_shared_footprint_199_v3/serve_web_review10_host.sh").read_text(encoding="utf-8")
        self.assertIn("serve_web_review199_exact_rows_host.sh", wrapper)
        serve = (repository / "scripts/p2/c1_c2_shared_footprint_199_v3/serve_web_review199_exact_rows_host.sh").read_text(encoding="utf-8")
        self.assertIn('bind_host="${3:-0.0.0.0}"', serve)
        self.assertIn('${bind_host}:${port}:8765', serve)
        self.assertIn('no authentication; trusted LAN only', serve)


if __name__ == "__main__":
    unittest.main()

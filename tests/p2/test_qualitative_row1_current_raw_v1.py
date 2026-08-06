from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from PIL import Image, ImageFont

from scripts.p2.qualitative_row1_current_raw_v1.render import png_bytes, render_cell, validate_review_selection


REPO = Path(__file__).resolve().parents[2]


class Row1DeterminismTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads((REPO / "configs/p2/qualitative_row1_current_raw_v1/render_v1.json").read_text())

    def test_contract_is_row1_only_and_reuses_camera_crop(self) -> None:
        self.assertEqual(self.config["row"]["number"], 1)
        self.assertFalse(self.config["row"]["camera_reselection_allowed"])
        self.assertFalse(self.config["row"]["crop_recomputation_allowed"])
        self.assertFalse(self.config["row"]["roof_boundary_used_for_camera_or_crop_selection"])
        self.assertFalse(self.config["next_row_authorized"])

    def test_outcome_free_selection_is_bound_by_population_position(self) -> None:
        buildings = [{"building_id": value} for value in ("A", "B", "C", "D", "E")]
        selected = validate_review_selection(
            buildings,
            {"population_indices": [1, 3, 5], "building_ids": ["A", "C", "E"]},
        )
        self.assertEqual([row["building_id"] for row in selected], ["A", "C", "E"])

    def test_same_inputs_produce_byte_identical_png(self) -> None:
        render = dict(self.config["render"])
        render.update({"cell_width_px": 120, "cell_header_height_px": 40, "cell_image_height_px": 80})
        regular = ImageFont.truetype(render["font_regular_path"], 8)
        bold = ImageFont.truetype(render["font_bold_path"], 10)
        source = Image.new("RGB", (75, 55), (34, 90, 144))
        first = png_bytes(render_cell(source, "TOP", "camera.JPG", "FULL_ROOF_RING_PROJECTABLE", render, regular, bold), render)
        second = png_bytes(render_cell(source, "TOP", "camera.JPG", "FULL_ROOF_RING_PROJECTABLE", render, regular, bold), render)
        self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest())
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

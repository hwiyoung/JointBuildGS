from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.p2.qualitative_199_common_manifest_v1.build_manifest import padded_bbox, select_cameras


REPO = Path(__file__).resolve().parents[2]


class Camera:
    def __init__(self, name: str) -> None:
        self.name = name


def candidate(name: str, nadir: float, principal: float, cross: float, *, full: bool = True, area: float = 5000.0):
    return {
        "camera": Camera(name),
        "coverage": 1.0,
        "area_px2": area,
        "nadir_deg": nadir,
        "principal_dot": principal,
        "cross_dot": cross,
        "full_selection_prism": full,
        "selection_uv": None,
    }


class CommonManifestContractTest(unittest.TestCase):
    def test_six_rows_share_new_dense_lineage(self) -> None:
        config = json.loads(
            (REPO / "configs/p2/qualitative_199_common_manifest_v1/contract_v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual([row["row"] for row in config["row_order"]], list(range(1, 7)))
        self.assertEqual(config["row_order"][3]["source"], "RECOVERED_DENSE_PAIR_V2_PLY")
        self.assertEqual(config["row_order"][4]["source"], "ROW4_EXACT_DERIVATIVE_REBUILD_REQUIRED")
        self.assertEqual(config["row_order"][5]["source"], "RECOVERED_DENSE_PAIR_V2_MVS")
        self.assertTrue(config["dense_lineage"]["excluded_historical_c2_products"])

    def test_camera_selection_is_unique_and_role_complete(self) -> None:
        candidates = [
            candidate("top.jpg", 5.0, 0.0, 0.0),
            candidate("section.jpg", 55.0, 0.1, 0.99),
            candidate("positive.jpg", 52.0, 0.9, 0.1),
            candidate("negative.jpg", 58.0, -0.9, -0.1),
        ]
        selected = select_cameras(candidates, 55.0, [35.0, 70.0])
        self.assertEqual(set(selected), {"TOP", "OBLIQUE_1", "OBLIQUE_2", "PRINCIPAL_SECTION"})
        self.assertEqual(len({row["camera"].name for row in selected.values()}), 4)
        self.assertEqual(selected["TOP"]["camera"].name, "top.jpg")
        self.assertEqual(selected["PRINCIPAL_SECTION"]["camera"].name, "section.jpg")

    def test_world_crop_padding_is_deterministic(self) -> None:
        self.assertEqual(padded_bbox([10.0, 20.0, 20.0, 24.0], 0.35, 5.0), [5.0, 15.0, 25.0, 29.0])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from scripts.p2.qualitative_199_cloudcompare_scene_v1 import add_shared_footprint_roofer as extension


class SharedFootprintRooferExtensionV1Tests(unittest.TestCase):
    def test_config_binds_decision_and_zero_new_execution(self) -> None:
        config = extension.load_config(extension.DEFAULT_CONFIG)
        self.assertEqual(config["decision_id"], "DEC-P1-019")
        self.assertEqual(config["execution"]["roofer_invocations"], 0)
        self.assertEqual(config["methods"]["C1_L_upper"]["expected_lod22_groups"], 104)
        self.assertEqual(config["methods"]["C2_MVS"]["expected_lod22_groups"], 119)
        self.assertIsNone(config["scientific_verdict"])

    def test_group_name_is_population_index_and_stable_id(self) -> None:
        self.assertEqual(
            extension.group_name({"population_index": 3, "stable_id": "DEBY_LOD2_104586480"}),
            "B003_DEBY_LOD2_104586480",
        )

    def test_named_obj_contains_one_named_group_for_completed_row(self) -> None:
        header = {
            "type": "CityJSON",
            "version": "2.0",
            "CityObjects": {},
            "vertices": [],
            "transform": {"scale": [0.1, 0.1, 0.1], "translate": [100.0, 200.0, 300.0]},
        }
        feature = {
            "type": "CityJSONFeature",
            "id": "DEBY_LOD2_TEST",
            "vertices": [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]],
            "CityObjects": {
                "DEBY_LOD2_TEST-0": {
                    "type": "BuildingPart",
                    "geometry": [{
                        "type": "Solid",
                        "lod": "2.2",
                        "boundaries": [[[[0, 1, 2, 3]]]],
                        "semantics": {"surfaces": [{"type": "RoofSurface"}], "values": [[0]]},
                    }],
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            city_path = root / "test.city.jsonl"
            city_path.write_text(json.dumps(header) + "\n" + json.dumps(feature) + "\n", encoding="utf-8")
            size, digest = extension.sha256_file(city_path)
            row = {
                "population_index": 1,
                "condition_id": "C1_L_upper",
                "stable_id": "DEBY_LOD2_TEST",
                "status": "COMPLETED",
                "outputs": [{"path": city_path.name, "bytes": size, "sha256": digest}],
            }
            data, index, stats = extension.build_named_obj([row], root, np.asarray([90.0, 190.0, 295.0]))
        text = data.decode("ascii")
        self.assertIn("g B001_DEBY_LOD2_TEST\n", text)
        self.assertEqual(text.count("\nf "), 2)
        self.assertEqual(index[0]["triangle_count"], 2)
        self.assertEqual(stats["completed_building_group_count"], 1)

    def test_surface_triangulation_preserves_a_hole(self) -> None:
        vertices = np.asarray([
            [0.0, 0.0, 0.0], [4.0, 0.0, 0.0], [4.0, 4.0, 0.0], [0.0, 4.0, 0.0],
            [1.0, 1.0, 0.0], [1.0, 3.0, 0.0], [3.0, 3.0, 0.0], [3.0, 1.0, 0.0],
        ])
        triangles = extension.triangulate_surface(vertices, [[0, 1, 2, 3], [4, 5, 6, 7]])
        area = sum(abs(float(np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])[2])) / 2 for triangle in triangles)
        self.assertAlmostEqual(area, 12.0)


if __name__ == "__main__":
    unittest.main()

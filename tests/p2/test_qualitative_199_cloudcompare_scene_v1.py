from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import laspy
import numpy as np
from shapely.geometry import Polygon

from scripts.p2.qualitative_199_cloudcompare_scene_v1 import add_named_footprints as named_dxf
from scripts.p2.qualitative_199_cloudcompare_scene_v1 import add_cloudcompare_named_footprints_v2 as named_obj
from scripts.p2.qualitative_199_cloudcompare_scene_v1 import build_scene as scene


class CloudCompareSceneV1Tests(unittest.TestCase):
    def test_committed_config_is_locked_and_non_verdict(self) -> None:
        config = scene.load_config(scene.DEFAULT_CONFIG)
        self.assertEqual(config["population"]["building_count"], 199)
        self.assertEqual(config["frame"]["source_horizontal_crs"], "EPSG:25832")
        self.assertEqual(config["inputs"]["current_uas_lidar"]["applied_vertical_shift_m"], 0.0)
        self.assertEqual(config["inputs"]["current_mvs_dense"]["applied_vertical_shift_m"], 0.0)
        self.assertFalse(config["display"]["roofsurface_geometry_access_allowed"])
        self.assertIsNone(config["scientific_verdict"])

    def test_union_extent_is_deterministic(self) -> None:
        rows = [
            {"viewport_bbox_xy": [10.0, 20.0, 30.0, 40.0]},
            {"viewport_bbox_xy": [5.0, 25.0, 35.0, 38.0]},
        ]
        self.assertEqual(scene.union_extent(rows, 2.0), [3.0, 18.0, 37.0, 42.0])

    def test_mvs_crop_preserves_rgb_and_applies_one_transform(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.ply"
            points = np.array(
                [
                    (0.0, 0.0, 1.0, 1, 2, 3),
                    (5.0, 5.0, 2.0, 4, 5, 6),
                    (50.0, 50.0, 3.0, 7, 8, 9),
                ],
                dtype=scene.POINT_DTYPE,
            )
            header = (
                "ply\nformat binary_little_endian 1.0\n"
                "element vertex 3\nproperty float32 x\nproperty float32 y\nproperty float32 z\n"
                "property uint8 red\nproperty uint8 green\nproperty uint8 blue\nend_header\n"
            ).encode("ascii")
            source.write_bytes(header + points.tobytes())
            output = root / "output.ply"
            stats = scene.crop_mvs_to_local_ply(
                source,
                output,
                [100.0, 200.0, 110.0, 210.0],
                np.asarray([100.0, 200.0, 300.0]),
                np.asarray([90.0, 190.0, 295.0]),
                2,
            )
            offset, count = scene.read_mvs_header(output)
            result = np.memmap(output, mode="r", dtype=scene.POINT_DTYPE, offset=offset, shape=(count,))
            self.assertEqual(stats["output_point_count"], 2)
            np.testing.assert_allclose(result["x"], [10.0, 15.0])
            np.testing.assert_allclose(result["y"], [10.0, 15.0])
            np.testing.assert_allclose(result["z"], [6.0, 7.0])
            self.assertEqual(result["red"].tolist(), [1, 4])

    def test_lidar_crop_preserves_dimensions_and_localizes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.laz"
            header = laspy.LasHeader(point_format=3, version="1.2")
            header.scales = np.asarray([0.001, 0.001, 0.001])
            data = laspy.LasData(header)
            data.x = [100.0, 105.0, 150.0]
            data.y = [200.0, 205.0, 250.0]
            data.z = [300.0, 301.0, 302.0]
            data.red = [100, 200, 300]
            data.write(source)
            output = root / "output.laz"
            stats = scene.crop_lidar_to_local_laz(
                source,
                output,
                [99.0, 199.0, 110.0, 210.0],
                np.asarray([90.0, 190.0, 295.0]),
                2,
            )
            result = laspy.read(output)
            self.assertEqual(stats["output_point_count"], 2)
            np.testing.assert_allclose(result.x, [10.0, 15.0])
            np.testing.assert_allclose(result.y, [10.0, 15.0])
            np.testing.assert_allclose(result.z, [5.0, 6.0])
            self.assertEqual(result.red.tolist(), [100, 200])

    def test_footprint_outputs_use_constant_curtain_not_roof_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [{"population_index": 1, "building_id": "DEBY_LOD2_TEST"}]
            references = {
                "DEBY_LOD2_TEST": {
                    "geometry": Polygon([(100, 200), (110, 200), (110, 210), (100, 210)]),
                    "ground_z_orthometric_m": 250.0,
                }
            }
            origin = np.asarray([90.0, 190.0, 295.0])
            dxf_stats = scene.write_footprint_dxf(root / "footprint.dxf", rows, references, origin, 45.7)
            curtain_stats = scene.write_curtain_ply(root / "curtain.ply", rows, references, origin, 45.7, 30.0, [255, 140, 0])
            self.assertEqual(dxf_stats["building_count"], 1)
            self.assertEqual(curtain_stats["vertex_count"], 8)
            self.assertEqual(curtain_stats["triangle_count"], 8)
            self.assertEqual(curtain_stats["constant_height_m"], 30.0)
            dxf = (root / "footprint.dxf").read_text(encoding="ascii")
            self.assertNotIn("RoofSurface", dxf)
            self.assertIn("SECTION\n2\nTABLES\n", dxf)
            self.assertIn("0\nLAYER\n2\nB001_DEBY_LOD2_TEST\n", dxf)
            self.assertEqual(dxf.count("0\nPOLYLINE\n8\nB001_DEBY_LOD2_TEST\n"), 1)

    def test_dxf_layer_names_must_be_unique(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "must be unique"):
            scene.dxf_tables(["B001_DUPLICATE", "B001_DUPLICATE"])

    def test_named_dxf_repair_inserts_tables_without_changing_entities(self) -> None:
        source = b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n0\nPOLYLINE\n8\nB001_TEST\n0\nENDSEC\n0\nEOF\n"
        repaired = named_dxf.insert_layer_tables(source, ["B001_TEST"])
        self.assertIn(b"0\nLAYER\n2\nB001_TEST\n", repaired)
        self.assertEqual(
            repaired.split(b"0\nSECTION\n2\nENTITIES\n", 1)[1],
            source.split(b"0\nSECTION\n2\nENTITIES\n", 1)[1],
        )

    def test_cloudcompare_named_obj_preserves_group_and_vertices(self) -> None:
        source = (
            b"0\nSECTION\n2\nENTITIES\n0\nPOLYLINE\n8\nB001_TEST\n70\n9\n"
            b"0\nVERTEX\n8\nB001_TEST\n10\n1\n20\n2\n30\n3\n"
            b"0\nVERTEX\n8\nB001_TEST\n10\n4\n20\n5\n30\n6\n"
            b"0\nVERTEX\n8\nB001_TEST\n10\n7\n20\n8\n30\n9\n"
            b"0\nSEQEND\n8\nB001_TEST\n0\nENDSEC\n0\nEOF\n"
        )
        entities = named_obj.parse_polyline_entities(source)
        output = named_obj.named_obj_bytes(entities, ["B001_TEST"]).decode("ascii")
        self.assertIn("g B001_TEST\n", output)
        self.assertIn("v 1.000000 2.000000 3.000000\n", output)
        self.assertIn("l 1 2 3 1\n", output)


if __name__ == "__main__":
    unittest.main()

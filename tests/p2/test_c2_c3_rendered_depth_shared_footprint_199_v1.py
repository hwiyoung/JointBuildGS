from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import numpy as np

from scripts.p2.c2_c3_rendered_depth_shared_footprint_199_v1.run import (
    CONFIG_PATH,
    SHARD_DTYPE,
    _collapse_view,
    _write_fused_laz,
    load_config,
    validate_config,
)
from src.stage3.common_classification_adapter_v1 import common_stages, pipeline
from scripts.p2.c2_c3_rendered_depth_shared_footprint_199_v1.build_web import (
    deterministic_coordinate_sample,
    load_config as load_web_config,
    transform_app,
    transform_index,
)


class RenderedDepthDirectComparisonTest(unittest.TestCase):
    def test_config_freezes_scientific_boundary(self) -> None:
        config = load_config(CONFIG_PATH)
        validate_config(config)
        self.assertEqual([row["condition_id"] for row in config["inputs"]["conditions"]], ["C3_1", "C3_2"])
        self.assertFalse(config["classification"]["semantic_used_for_classification"])
        self.assertFalse(config["fusion"]["post_fusion_voxel_downsampling"])
        self.assertIsNone(config["official_PASS_usable"])
        self.assertIsNone(config["scientific_verdict"])

    def test_common_adapter_has_no_semantic_classification_stage(self) -> None:
        config = load_config(CONFIG_PATH)
        stages = common_stages(
            scene=config["scene"], classification=config["classification"],
            footprint_path=Path("/task/freeze/shared.geojson"), output_path=Path("/task/classified.laz"),
        )
        self.assertEqual([row["type"] for row in stages], ["filters.crop", "filters.smrf", "filters.overlay", "writers.las"])
        self.assertNotIn("semantic", json.dumps(stages).lower())
        self.assertEqual(stages[1]["ground_class"], 2)
        self.assertEqual(stages[1]["other_class"], 1)
        self.assertEqual(stages[2]["where"], "Classification != 2")
        self.assertEqual(stages[3]["extra_dims"], "all")

    def test_only_source_reader_differs_between_c2_and_c3(self) -> None:
        config = load_config(CONFIG_PATH)
        kwargs = {
            "scene": config["scene"], "classification": config["classification"],
            "footprint_path": Path("/task/freeze/shared.geojson"), "output_path": Path("/task/out.laz"),
        }
        c2 = pipeline(source_stages=[{"type": "readers.ply", "filename": "/c2.ply"}, {"type": "filters.transformation", "matrix": "m"}], **kwargs)
        c3 = pipeline(source_stages=[{"type": "readers.las", "filename": "/c3.laz"}], **kwargs)
        self.assertEqual(c2["pipeline"][2:], c3["pipeline"][1:])

    def test_same_view_duplicates_count_once_for_support(self) -> None:
        shift = np.asarray([100.0, 200.0, 10.0])
        xyz = np.asarray([[100.01, 200.01, 10.01], [100.02, 200.02, 10.02], [100.31, 200.01, 10.01]])
        rgb = np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        probabilities = np.tile(np.asarray([[0.1, 0.2, 0.3, 0.4]]), (3, 1))
        rows = _collapse_view(xyz, rgb, probabilities, shift, 0.15)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(rows["pixel_count"].tolist()), [1, 2])

    def test_minimum_distinct_view_support_and_audit_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shard = root / "shard.bin"
            rows = np.zeros(3, dtype=SHARD_DTYPE)
            rows["qx"] = [1, 1, 2]; rows["qy"] = [1, 1, 2]; rows["qz"] = [1, 1, 2]
            rows["sx"] = [690900.0, 690900.2, 690920.0]
            rows["sy"] = [5336000.0, 5336000.2, 5336040.0]
            rows["sz"] = [650.0, 650.2, 660.0]
            rows["sr"] = rows["sg"] = rows["sb"] = 1.0
            rows["sp0"] = 0.1; rows["sp1"] = 0.2; rows["sp2"] = 0.3; rows["sp3"] = 0.4
            rows["pixel_count"] = 1
            rows.tofile(shard)
            destination = root / "fused.laz"
            total, histogram, rejected, input_rows = _write_fused_laz(shard_paths=[shard], destination=destination, minimum_support=2)
            self.assertEqual((total, rejected, input_rows), (1, 1, 3))
            self.assertEqual(histogram, {"2": 1})
            import laspy
            cloud = laspy.read(destination)
            wkt_vlrs = [vlr for vlr in cloud.header.vlrs if type(vlr).__name__ == "WktCoordinateSystemVlr"]
            self.assertEqual(len(wkt_vlrs), 1)
            self.assertIn('AUTHORITY["EPSG","25832"]', wkt_vlrs[0].string)
            self.assertEqual(int(cloud.view_support[0]), 2)
            self.assertEqual(int(cloud.semantic_argmax[0]), 3)
            self.assertEqual(int(cloud.classification[0]), 1)

    @unittest.skipUnless(shutil.which("pdal"), "PDAL integration image only")
    def test_pdal_roundtrip_preserves_c3_audit_dimensions(self) -> None:
        config = load_config(CONFIG_PATH)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shard = root / "shard.bin"
            rows = np.zeros(24, dtype=SHARD_DTYPE)
            # Twelve voxels, each observed by two distinct synthetic views.
            base_x = 690900.0 + np.arange(12) * 0.4
            rows["qx"] = np.repeat(np.arange(12), 2)
            rows["qy"] = 1; rows["qz"] = np.repeat(np.arange(12), 2)
            rows["sx"] = np.repeat(base_x, 2)
            rows["sy"] = 5336000.0
            rows["sz"] = np.repeat(640.0 + np.arange(12) * 0.15, 2)
            rows["sr"] = rows["sg"] = rows["sb"] = 0.5
            rows["sp0"] = 0.1; rows["sp1"] = 0.2; rows["sp2"] = 0.3; rows["sp3"] = 0.4
            rows["pixel_count"] = 1
            rows.tofile(shard)
            source = root / "source.laz"
            _write_fused_laz(shard_paths=[shard], destination=source, minimum_support=2)
            footprint = root / "footprint.geojson"
            footprint.write_text(json.dumps({
                "type": "FeatureCollection", "features": [{
                    "type": "Feature", "properties": {"class": 6},
                    "geometry": {"type": "Polygon", "coordinates": [[[690899, 5335999], [690906, 5335999], [690906, 5336001], [690899, 5336001], [690899, 5335999]]]},
                }],
            }), encoding="utf-8")
            destination = root / "classified.laz"
            scene = {**config["scene"], "roofer_aoi_bbox": [690899, 5335999, 690906, 5336001], "classification_context_buffer_m": 0.0}
            body = pipeline(
                source_stages=[{"type": "readers.las", "filename": source.as_posix()}],
                scene=scene, classification=config["classification"],
                footprint_path=footprint, output_path=destination,
            )
            pipeline_path = root / "pipeline.json"
            pipeline_path.write_text(json.dumps(body), encoding="utf-8")
            process = subprocess.run(["pdal", "pipeline", pipeline_path.as_posix()], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
            self.assertEqual(process.returncode, 0, process.stdout)
            import laspy
            result = laspy.read(destination)
            dimensions = set(result.point_format.dimension_names)
            self.assertTrue({"view_support", "semantic_argmax", "semantic_prob_0", "semantic_prob_1", "semantic_prob_2", "semantic_prob_3"}.issubset(dimensions))

    def test_coordinate_sampling_is_input_order_independent(self) -> None:
        rows = np.zeros((6, 13), dtype=np.float64)
        rows[:, :3] = np.asarray([
            [690900.01, 5336000.01, 650.01], [690900.02, 5336000.02, 650.02],
            [690900.21, 5336000.01, 650.01], [690900.22, 5336000.02, 650.02],
            [690900.41, 5336000.01, 650.01], [690900.42, 5336000.02, 650.02],
        ])
        rows[:, 3] = 6
        left = deterministic_coordinate_sample(rows, 0.2, 75_000)
        right = deterministic_coordinate_sample(rows[::-1], 0.2, 75_000)
        np.testing.assert_array_equal(left, right)
        self.assertEqual(len(left), 3)

    def test_viewer_transform_adds_one_c3_panel_and_compatible_csv(self) -> None:
        config = load_web_config()
        app = transform_app((Path(__file__).resolve().parents[2] / config["application_sources"]["app"]["path"]).read_text(encoding="utf-8"))
        index = transform_index((Path(__file__).resolve().parents[2] / config["application_sources"]["index"]["path"]).read_text(encoding="utf-8"))
        self.assertIn("new ReviewViewer('c3Viewport', 'c3Stats', 'c3', 2)", app)
        self.assertIn("'c3_1_ox', 'c3_2_ox'", app)
        self.assertIn("viewers.length === 3", app)
        self.assertIn("drawMiniMap(building); loadReviewForm(building.stable_id);", app)
        self.assertIn("building.c3[state.c3Condition].technical_status", app)
        self.assertEqual(index.count('id="c3Viewport"'), 1)
        self.assertEqual(index.count('id="lidarViewport"'), 1)
        self.assertEqual(index.count('id="mvsViewport"'), 1)
        self.assertLess(index.index('id="reviewbar"'), index.index('id="photoDrawer"'))


if __name__ == "__main__":
    unittest.main()

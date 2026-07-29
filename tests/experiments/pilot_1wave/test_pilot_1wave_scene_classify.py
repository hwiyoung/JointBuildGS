#!/usr/bin/env python3
"""Unit tests for the expanded-pilot geometry-only scene classifier."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import laspy
import numpy as np


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts/experiments/pilot_1wave/pilot_1wave_scene_classify.py"
SPEC = importlib.util.spec_from_file_location("pilot_1wave_scene_classify", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def roofprints(*, coordinate_dimension: int = 2, overlay_class: int = 6) -> dict:
    features = []
    for index in range(30):
        x = float(index)
        point = [x, 0.0] if coordinate_dimension == 2 else [x, 0.0, 123.0]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "building_id": f"DEBY_LOD2_{index}",
                    "class": overlay_class,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        point,
                        [*point[:-1], 1.0] if coordinate_dimension == 2 else [x, 1.0, 123.0],
                        [x + 0.5, 1.0] if coordinate_dimension == 2 else [x + 0.5, 1.0, 123.0],
                        point,
                    ]],
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::25832"},
        },
        "features": features,
    }


class SceneClassifierTest(unittest.TestCase):
    def test_pipeline_is_historical_smrf_then_non_ground_overlay(self) -> None:
        pipeline = MODULE.pdal_pipeline(
            Path("/tmp/raw.las"), Path("/tmp/roofprints.geojson"), Path("/tmp/out.las")
        )["pipeline"]
        self.assertEqual([stage["type"] for stage in pipeline], [
            "readers.las", "filters.smrf", "filters.overlay", "writers.las"
        ])
        self.assertEqual(pipeline[1]["ground_class"], 2)
        self.assertEqual(pipeline[1]["other_class"], 1)
        self.assertEqual(
            {key: pipeline[1][key] for key in MODULE.SMRF}, MODULE.SMRF
        )
        self.assertEqual(pipeline[2]["column"], "class")
        self.assertEqual(pipeline[2]["where"], "Classification != 2")
        self.assertEqual(pipeline[3]["a_srs"], "EPSG:25832")

    def test_roofprints_require_30_xy_features_and_class6(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roofprints.geojson"
            path.write_text(json.dumps(roofprints()), encoding="utf-8")
            record = MODULE.validate_roofprints(path)
            self.assertEqual(record["feature_count"], 30)
            self.assertEqual(record["coordinate_dimension"], 2)

            path.write_text(
                json.dumps(roofprints(coordinate_dimension=3)), encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "not XY-only"):
                MODULE.validate_roofprints(path)

            path.write_text(
                json.dumps(roofprints(overlay_class=5)), encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "overlay class drift"):
                MODULE.validate_roofprints(path)

    def test_scene_npz_is_finite_nonempty_nx3(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "scene.npz"
            points = np.array([[690800.0, 5336000.0, 570.0], [690801.0, 5336001.0, 571.0]])
            np.savez(path, P_utm_clean=points)
            loaded, key = MODULE.load_scene_points(path)
            np.testing.assert_array_equal(loaded, points)
            self.assertEqual(key, "P_utm_clean")

            np.savez(path, P_utm_clean=np.array([[np.nan, 0.0, 0.0]]))
            with self.assertRaisesRegex(RuntimeError, "non-finite"):
                MODULE.load_scene_points(path)

    def test_scene_lineage_is_required_and_never_pickled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scene.npz"
            points = np.array([[690800.0, 5336000.0, 570.0]])
            np.savez(path, P_utm_clean=points)
            with self.assertRaisesRegex(RuntimeError, "lacks readout_lineage_json"):
                MODULE.load_scene_lineage(path)

            np.savez(
                path,
                P_utm_clean=points,
                readout_lineage_json=np.array({"unsafe": True}, dtype=object),
            )
            with self.assertRaisesRegex(RuntimeError, "must not require pickle"):
                MODULE.load_scene_lineage(path)

    def test_raw_las_has_epsg_and_unclassified_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.las"
            points = np.array([[690800.0, 5336000.0, 570.0], [690801.0, 5336001.0, 571.0]])
            MODULE.write_raw_las(path, points)
            las = laspy.read(path)
            self.assertEqual(las.header.parse_crs().to_epsg(), 25832)
            self.assertEqual(set(np.asarray(las.classification)), {1})
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                MODULE.write_raw_las(path, points)


if __name__ == "__main__":
    unittest.main()

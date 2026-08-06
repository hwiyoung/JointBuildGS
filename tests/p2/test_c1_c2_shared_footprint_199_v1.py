from __future__ import annotations

import io
from pathlib import Path
import tempfile
import unittest

import numpy as np
from shapely.geometry import Polygon

from scripts.p2.c1_c2_shared_footprint_199_v1 import run


class SharedFootprint199Tests(unittest.TestCase):
    def test_config_freezes_shared_xy_and_398_rows(self) -> None:
        config = run.load_config()
        run.validate_config(config)
        self.assertEqual(config["decision_id"], "DEC-P1-019")
        self.assertEqual(config["methods"], ["C1_L_upper", "C2_MVS"])
        self.assertEqual(config["execution"]["expected_building_method_rows"], 398)
        self.assertIn("RoofSurface XYZ", config["inputs"]["shared_footprint_prohibited_fields"])

    def test_groundsurface_loader_ignores_roof_geometry_and_z(self) -> None:
        gml = """<core:CityModel xmlns:core="urn:core" xmlns:bldg="urn:bldg" xmlns:gml="http://www.opengis.net/gml">
<core:cityObjectMember><bldg:Building gml:id="DEBY_LOD2_TEST">
<bldg:boundedBy><bldg:GroundSurface><gml:Polygon><gml:exterior><gml:LinearRing>
<gml:posList srsDimension="3">0 0 123 10 0 123 10 10 123 0 10 123 0 0 123</gml:posList>
</gml:LinearRing></gml:exterior></gml:Polygon></bldg:GroundSurface></bldg:boundedBy>
<bldg:boundedBy><bldg:RoofSurface><gml:Polygon><gml:exterior><gml:LinearRing>
<gml:posList srsDimension="3">0 0 999 10 0 999 10 10 999 0 10 999 0 0 999</gml:posList>
</gml:LinearRing></gml:exterior></gml:Polygon></bldg:RoofSurface></bldg:boundedBy>
</bldg:Building></core:cityObjectMember></core:CityModel>"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.gml"
            path.write_text(gml, encoding="utf-8")
            reference = run.load_groundsurface_xy([path], ["DEBY_LOD2_TEST"])["DEBY_LOD2_TEST"]
        self.assertEqual(reference.footprint.bounds, (0.0, 0.0, 10.0, 10.0))
        payload = run.shared_footprint_geojson(reference)
        coordinates = payload["features"][0]["geometry"]["coordinates"][0]
        self.assertTrue(all(len(point) == 2 for point in coordinates))
        self.assertFalse(payload["features"][0]["properties"]["roofsurface_used"])

    def test_spatial_bins_write_only_matching_buildings(self) -> None:
        references = {
            "A": run.FootprintReference("A", Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])),
            "B": run.FootprintReference("B", Polygon([(20, 20), (22, 20), (22, 22), (20, 22)])),
        }
        bins = run.build_spatial_bins(references, 1.0, 4.0)
        handles = {"A": io.BytesIO(), "B": io.BytesIO()}
        written = run.scatter_chunk(np.asarray([[1, 1, 5], [21, 21, 6], [100, 100, 7]], dtype=float), bins, handles)
        self.assertEqual(written, 2)
        np.testing.assert_allclose(np.frombuffer(handles["A"].getvalue(), dtype="<f8").reshape((-1, 3)), [[1, 1, 5]])
        np.testing.assert_allclose(np.frombuffer(handles["B"].getvalue(), dtype="<f8").reshape((-1, 3)), [[21, 21, 6]])

    def test_classification_uses_xy_footprint_and_point_ground(self) -> None:
        reference = run.FootprintReference("A", Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]))
        axis = np.arange(1.0, 9.01, 0.25)
        xx, yy = np.meshgrid(axis, axis)
        building = np.column_stack((xx.ravel(), yy.ravel(), np.full(xx.size, 10.0)))
        gx = np.linspace(-4.0, -2.0, 30)
        ground = np.column_stack((gx, np.linspace(0.0, 10.0, 30), np.zeros(30)))
        points = np.vstack((building, ground))
        prepared = run.load_config()["preparation"]
        class6, class2, stats, failure = run.classify_points(points, reference, prepared)
        self.assertIsNone(failure)
        self.assertGreaterEqual(len(class6), 100)
        self.assertGreater(len(class2), 0)
        self.assertEqual(stats["local_ground_z_from_point_evidence"], 0.0)


if __name__ == "__main__":
    unittest.main()

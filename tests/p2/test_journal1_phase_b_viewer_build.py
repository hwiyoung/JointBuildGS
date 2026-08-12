"""Synthetic unit tests for the journal1 Phase-B label-review viewer builder
and its E1/E2 coverage diagnostic."""

import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parents[2] / "scripts/p2/journal1_phase_b_v1"


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, _HERE / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bb = _load("journal1_phase_b_build", "build_label_review_viewer.py")
cd = _load("journal1_phase_b_covdiag", "coverage_diagnostic.py")
om = _load("journal1_phase_b_map", "build_overview_map.py")
sr = _load("journal1_phase_b_rasters", "build_sensor_extent_rasters.py")

GML_DOC = """<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel xmlns:core="http://www.opengis.net/citygml/1.0"
    xmlns:gml="http://www.opengis.net/gml"
    xmlns:bldg="http://www.opengis.net/citygml/building/1.0">
  <core:cityObjectMember>
    <bldg:Building gml:id="B_TARGET">
      <bldg:boundedBy><bldg:RoofSurface>
        <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember>
          <gml:Polygon>
            <gml:exterior><gml:LinearRing><gml:posList>
              690710 5335710 560 690720 5335710 560 690720 5335720 562
              690710 5335720 562 690710 5335710 560
            </gml:posList></gml:LinearRing></gml:exterior>
            <gml:interior><gml:LinearRing><gml:posList>
              690712 5335712 560.5 690714 5335712 560.5 690714 5335714 560.5
              690712 5335712 560.5
            </gml:posList></gml:LinearRing></gml:interior>
          </gml:Polygon>
        </gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
      </bldg:RoofSurface></bldg:boundedBy>
    </bldg:Building>
    <bldg:Building gml:id="B_OTHER">
      <bldg:boundedBy><bldg:RoofSurface>
        <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember>
          <gml:Polygon><gml:exterior><gml:LinearRing><gml:posList>
            0 0 0 1 0 0 1 1 0 0 0 0
          </gml:posList></gml:LinearRing></gml:exterior></gml:Polygon>
        </gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
      </bldg:RoofSurface></bldg:boundedBy>
    </bldg:Building>
  </core:cityObjectMember>
</core:CityModel>
"""

CSV_DOC = """stable_id,tier,e1_lod2_completeness@0.5,e1_lod2_acc_median_m,e1_lod2_f1@0.5,n_e1_roof_pts,flag
SID_A,A_STRONG_MISMATCH,0.0,3.4,0.0,100,
SID_B,B_MODERATE_MISMATCH,0.2,1.1,0.1,200,EMPTY_ARM
SID_C,C_CONSISTENT,0.9,0.1,0.9,300,
SID_N,NA_E1_INSUFFICIENT,0.0,0.0,0.0,0,NO_CLASS_FIELD+EMPTY_ARM
"""


class ViewerLocalRingsTest(unittest.TestCase):
    def test_z_bridge_and_exterior_only(self):
        with tempfile.TemporaryDirectory() as td:
            tile = Path(td) / "tile.gml"
            tile.write_text(GML_DOC)
            out = bb.viewer_local_rings(
                [tile], {"B_TARGET"}, [690700.0, 5335700.0, 550.0], 45.7)
        self.assertEqual(set(out), {"B_TARGET"})
        got = out["B_TARGET"]
        # interior ring skipped but counted; exterior ring kept once
        self.assertEqual(len(got["rings"]), 1)
        self.assertEqual(got["interior_skipped"], 1)
        ring = got["rings"][0]
        self.assertEqual(len(ring), 5)
        # viewer-local = world - origin, then z + 45.7 (LoD2 datum bridge)
        self.assertEqual(ring[0], [10.0, 10.0, round(560 - 550 + 45.7, 3)])
        self.assertEqual(ring[2][2], round(562 - 550 + 45.7, 3))

    def test_untargeted_building_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            tile = Path(td) / "tile.gml"
            tile.write_text(GML_DOC)
            out = bb.viewer_local_rings(
                [tile], {"B_TARGET", "B_OTHER"}, [690700.0, 5335700.0, 550.0], 45.7)
        self.assertEqual(set(out), {"B_TARGET", "B_OTHER"})


def write_crop_ply(path, rows):
    """rows: [(x, y, z, cls)] in the sealed 16-byte crop layout."""
    with open(path, "wb") as f:
        f.write((
            "ply\nformat binary_little_endian 1.0\n"
            f"element vertex {len(rows)}\n"
            "property float x\nproperty float y\nproperty float z\n"
            "property uchar red\nproperty uchar green\nproperty uchar blue\n"
            "property uchar classification\nend_header\n").encode("ascii"))
        for x, y, z, c in rows:
            f.write(struct.pack("<fffBBBB", x, y, z, 0, 0, 0, int(c)))


class CoverageDiagnosticTest(unittest.TestCase):
    def test_arm_stats_separates_gap_ground_and_vegetation(self):
        # flat 10x10 roof at z=10; class-6 covers x<5 at the plane, x>=5 is
        # ground-class only, one cell carries a thick class-6 canopy column
        ring = [[0, 0, 10], [10, 0, 10], [10, 10, 10], [0, 10, 10], [0, 0, 10]]
        rows = []
        step = 0.25
        for i in range(40):
            for j in range(40):
                x, y = i * step + 0.125, j * step + 0.125
                if x < 5:
                    rows.append((x, y, 10.0, 6))
                else:
                    rows.append((x, y, 0.0, 2))
        for k in range(8):  # canopy column, z 10..15 in one left-half cell
            rows.append((2.6, 2.6, 10.0 + k * 0.7, 6))
        with tempfile.TemporaryDirectory() as td:
            ply = Path(td) / "crop.ply"
            write_crop_ply(ply, rows)
            pts = cd.read_crop(ply)
        planes = cd.ring_planes([ring])
        self.assertEqual(len(planes), 1)
        self.assertAlmostEqual(planes[0][3], 0.0, places=3)  # flat tilt
        _roof, centers = cd.roof_cells(planes, 0.5)
        cfg = {"veg_ziqr_m": 1.5, "above_ridge_m": 2.0}
        st = cd.arm_stats(pts, planes, centers, 0.5, cfg)
        st["above_ridge_share"] = cd.above_ridge_share(pts, [ring], 2.0)
        self.assertGreater(st["any_xy"], 0.95)          # data everywhere
        self.assertAlmostEqual(st["cls6_xy"], 0.5, delta=0.08)
        self.assertAlmostEqual(st["groundonly_xy"], 0.5, delta=0.08)
        self.assertAlmostEqual(st["dz_med_m"], 0.0, delta=0.15)
        self.assertGreater(st["veg_cell_share"], 0.0)   # canopy cell detected
        self.assertGreater(st["above_ridge_share"], 0.0)


class ClassifyTest(unittest.TestCase):
    THR = {"gate_min_cover": 0.7, "displaced_min_pts": 20000, "ground_min": 0.3,
           "above_ridge_min": 0.25, "veg_min": 0.3, "dz_min": 1.0, "dz_cover_min": 0.5}

    def arm(self, **kw):
        base = {"n_pts": 50000, "any_xy": 0.9, "cls6_xy": 0.85, "groundonly_xy": 0.0,
                "dz_med_m": 0.1, "above_ridge_share": 0.0, "veg_cell_share": 0.0}
        base.update(kw)
        return base

    def test_tier_passthrough(self):
        self.assertEqual(om.classify("C_CONSISTENT", None, None, True, self.THR),
                         "C_CONSISTENT")
        self.assertEqual(om.classify("B_MODERATE_MISMATCH", self.arm(), None, True,
                                     self.THR), "B_NOCHANGE_1ST")

    def test_na_split_by_e2(self):
        self.assertEqual(om.classify("NA_E1_INSUFFICIENT", None,
                                     self.arm(any_xy=0.8), False, self.THR), "NA_E2_OK")
        self.assertEqual(om.classify("NA_E1_INSUFFICIENT", None,
                                     self.arm(any_xy=0.2), False, self.THR), "NA_EMPTY")

    def test_a_gate_fail_split_by_points(self):
        self.assertEqual(om.classify("A_STRONG_MISMATCH", self.arm(n_pts=90000),
                                     None, False, self.THR), "A_DISPLACED")
        self.assertEqual(om.classify("A_STRONG_MISMATCH", self.arm(n_pts=300),
                                     self.arm(n_pts=200), False, self.THR), "A_EMPTY")

    def test_a_signal_priority(self):
        self.assertEqual(om.classify("A_STRONG_MISMATCH", self.arm(groundonly_xy=0.5),
                                     None, True, self.THR), "A_DEMOLITION_SUSPECT")
        self.assertEqual(om.classify("A_STRONG_MISMATCH", self.arm(veg_cell_share=0.4),
                                     None, True, self.THR), "A_VEG_SUSPECT")
        self.assertEqual(om.classify("A_STRONG_MISMATCH", self.arm(dz_med_m=1.6),
                                     None, True, self.THR), "A_ZOFFSET")
        self.assertEqual(om.classify("A_STRONG_MISMATCH", self.arm(), None, True,
                                     self.THR), "A_REVIEW")


class SensorRasterTest(unittest.TestCase):
    def test_bin_counts_orientation_and_totals(self):
        import numpy as np
        # bounds 0..10 x 0..10, cell 0.5 -> 20x20; row 0 must be the north edge
        xs = np.array([0.25, 0.25, 9.75])
        ys = np.array([9.75, 9.75, 0.25])
        g = sr.bin_counts(xs, ys, (0.0, 0.0, 10.0, 10.0), 0.5)
        self.assertEqual(g.shape, (20, 20))
        self.assertEqual(int(g.sum()), 3)
        self.assertEqual(int(g[0, 0]), 2)     # north-west pair
        self.assertEqual(int(g[19, 19]), 1)   # south-east single

    def test_png_writer_emits_valid_header(self):
        import numpy as np
        rgba = np.zeros((4, 6, 4), dtype=np.uint8)
        rgba[..., 3] = 255
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.png"
            sr.write_png_rgba(p, rgba)
            raw = p.read_bytes()
        self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))
        w, h = struct.unpack(">II", raw[16:24])
        self.assertEqual((w, h), (6, 4))


class ReadCandidatesTest(unittest.TestCase):
    def test_tier_filter_keeps_order(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "cand.csv"
            csv_path.write_text(CSV_DOC)
            rows = bb.read_candidates(
                csv_path, {"A_STRONG_MISMATCH", "B_MODERATE_MISMATCH"})
        self.assertEqual([r["stable_id"] for r in rows], ["SID_A", "SID_B"])
        self.assertEqual(rows[1]["flag"], "EMPTY_ARM")


if __name__ == "__main__":
    unittest.main()

"""CPU unit tests of src/phd/prior_propagation_v4 (PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1).

The tests of tests/phd/test_prior_propagation_v3.py (which include the v2 tests) run again against v4 (the same files,
their imports pointed at v4; classes prefixed V3onV4_). v4 adds:
  PartyWallCutV4  : the party-wall cut of the method document 3.1 (2026-10-02, order r10 2-2) on four cases of the order --
                    two walls that overlap completely (both are cut away), two walls 0.2 m apart (no cut), a wall that
                    stands above a lower neighbour (only the overlapping lower part is cut, the upper part stays), two
                    walls whose normals point the same way (no cut) -- plus planes that cross (the cut is clipped to the
                    0.1 m strip) and a neighbour on each side (two cuts on one wall)
  EarClipV4       : the triangles of a simple non-convex polygon cover it exactly
  GridOriginV4    : build_plane_store with the uncut polygon's grid origin keeps the cells of the remaining part (same
                    centres, same areas) and drops the cut ones
  FilesV4         : v4 differs from v3 only in faces.py and locations.py
Run in jointbuildgs:dev from the repository root: python -m unittest tests.phd.test_prior_propagation_v4"""
import hashlib
import sys
import types
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.phd.prior_propagation_v4 import faces as FA  # noqa: E402
from src.phd.prior_propagation_v4 import locations as L  # noqa: E402

# ---- the v3 tests (with the v2 tests inside), unchanged, against v4
_src = (Path(__file__).with_name("test_prior_propagation_v3.py")).read_text().replace("src.phd.prior_propagation_v3", "src.phd.prior_propagation_v4")
_v3 = types.ModuleType("test_prior_propagation_v3_on_v4")
_v3.__file__ = str(Path(__file__).with_name("test_prior_propagation_v3.py"))
exec(compile(_src, "test_prior_propagation_v3.py (imports -> v4)", "exec"), _v3.__dict__)
for _name, _obj in list(_v3.__dict__.items()):
    if isinstance(_obj, type) and issubclass(_obj, unittest.TestCase) and _obj is not unittest.TestCase:
        globals()[f"V3onV4_{_name}"] = type(f"V3onV4_{_name}", (_obj,), {})
del _name, _obj


def wall(x0, x1, z0, z1, y=0.0, outward=+1):
    """vertical rectangle in the plane y = const between x0..x1 and z0..z1 as two triangles; outward normal = (0, outward, 0)."""
    a, b, c, d = [x0, y, z0], [x1, y, z0], [x1, y, z1], [x0, y, z1]
    t = np.array([[a, b, c], [a, c, d]], np.float64)
    n = np.cross(t[0, 1] - t[0, 0], t[0, 2] - t[0, 0])
    if np.sign(n[1]) != outward:
        t = t[:, [0, 2, 1]]
    return t


def area(tris):
    tris = np.asarray(tris, np.float64)
    return float(0.5 * np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1).sum()) if len(tris) else 0.0


def cut_all(polys):
    """party_wall_overlaps + cut_triangles for every polygon; returns {id: remaining triangles}, overlaps."""
    ov = FA.party_wall_overlaps(polys)
    out = {}
    for p in polys:
        cuts = [(o["frame"], o["region"]) for o in ov if p["id"] in (o["a"], o["b"])]
        new, src, touched, _ = FA.cut_triangles(p["tris"], cuts)
        out[p["id"]] = new
    return out, ov


class PartyWallCutV4(unittest.TestCase):
    def test_full_overlap(self):
        A = dict(id=1, building="A", normal=[0, 1, 0], tris=wall(0, 10, 0, 6, y=0.0, outward=+1))
        B = dict(id=2, building="B", normal=[0, -1, 0], tris=wall(0, 10, 0, 6, y=0.0, outward=-1))
        out, ov = cut_all([A, B])
        self.assertEqual(len(ov), 1)
        self.assertAlmostEqual(ov[0]["area"], 60.0, places=6)
        self.assertAlmostEqual(area(out[1]), 0.0, places=6)
        self.assertAlmostEqual(area(out[2]), 0.0, places=6)

    def test_apart_02m(self):
        A = dict(id=1, building="A", normal=[0, 1, 0], tris=wall(0, 10, 0, 6, y=0.0, outward=+1))
        B = dict(id=2, building="B", normal=[0, -1, 0], tris=wall(0, 10, 0, 6, y=0.2, outward=-1))
        out, ov = cut_all([A, B])
        self.assertEqual(ov, [])
        self.assertAlmostEqual(area(out[1]), 60.0, places=6)
        self.assertTrue(np.array_equal(out[1], A["tris"]))       # untouched triangles pass through unchanged

    def test_upper_part_stays(self):
        A = dict(id=1, building="A", normal=[0, 1, 0], tris=wall(0, 10, 0, 10, y=0.0, outward=+1))     # tall
        B = dict(id=2, building="B", normal=[0, -1, 0], tris=wall(2, 8, 0, 6, y=0.05, outward=-1))    # lower neighbour, 5 cm off
        out, ov = cut_all([A, B])
        self.assertEqual(len(ov), 1)
        self.assertAlmostEqual(ov[0]["area"], 36.0, places=6)
        self.assertAlmostEqual(area(out[1]), 100.0 - 36.0, places=6)
        self.assertAlmostEqual(area(out[2]), 0.0, places=6)
        T = out[1]
        self.assertTrue(np.allclose(T[..., 1], 0.0))                 # lifted back onto A's own plane
        c = T.mean(1)
        inside_cut = (c[:, 0] > 2 + 1e-9) & (c[:, 0] < 8 - 1e-9) & (c[:, 2] < 6 - 1e-9)
        self.assertFalse(inside_cut.any())
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        self.assertTrue((n[:, 1] > 0).all())                         # winding (outward side) kept

    def test_same_direction(self):
        A = dict(id=1, building="A", normal=[0, 1, 0], tris=wall(0, 10, 0, 6, y=0.0, outward=+1))
        B = dict(id=2, building="B", normal=[0, 1, 0], tris=wall(0, 10, 0, 6, y=0.0, outward=+1))
        out, ov = cut_all([A, B])
        self.assertEqual(ov, [])
        self.assertAlmostEqual(area(out[1]) + area(out[2]), 120.0, places=6)

    def test_same_building_not_cut(self):
        A = dict(id=1, building="A", normal=[0, 1, 0], tris=wall(0, 10, 0, 6, y=0.0, outward=+1))
        B = dict(id=2, building="A", normal=[0, -1, 0], tris=wall(0, 10, 0, 6, y=0.0, outward=-1))
        self.assertEqual(cut_all([A, B])[1], [])

    def test_crossing_planes_strip(self):
        # B leans: its plane crosses A's along the line x = 5 (y = 0.04 (x - 5)); within 0.1 m for |x - 5| <= 2.5
        tb = wall(0, 10, 0, 6, y=0.0, outward=-1)
        tb[..., 1] = 0.04 * (tb[..., 0] - 5.0)
        nb = np.cross(tb[0, 1] - tb[0, 0], tb[0, 2] - tb[0, 0]); nb /= np.linalg.norm(nb)
        A = dict(id=1, building="A", normal=[0, 1, 0], tris=wall(0, 10, 0, 6, y=0.0, outward=+1))
        B = dict(id=2, building="B", normal=nb, tris=tb)
        out, ov = cut_all([A, B])
        self.assertEqual(len(ov), 1)
        self.assertLessEqual(ov[0]["gap_max"], 0.1 + 1e-9)
        self.assertAlmostEqual(ov[0]["area"], 5.0 * 6.0, delta=0.05)   # |x - 5| <= 2.5 (common-plane coordinates)
        self.assertAlmostEqual(area(out[1]), 60.0 - 30.0, delta=0.05)

    def test_two_neighbours(self):
        A = dict(id=1, building="A", normal=[0, 1, 0], tris=wall(0, 10, 0, 8, y=0.0, outward=+1))
        B = dict(id=2, building="B", normal=[0, -1, 0], tris=wall(0, 4, 0, 5, y=0.0, outward=-1))
        C = dict(id=3, building="C", normal=[0, -1, 0], tris=wall(6, 10, 0, 7, y=0.02, outward=-1))
        out, ov = cut_all([A, B, C])
        self.assertEqual(len(ov), 2)
        self.assertAlmostEqual(area(out[1]), 80.0 - 20.0 - 28.0, places=6)


class EarClipV4(unittest.TestCase):
    def test_l_shape(self):
        xy = np.array([[0, 0], [4, 0], [4, 1], [1, 1], [1, 3], [0, 3]], float)
        t = FA.ear_clip(xy)
        a = sum(abs(0.5 * np.cross(xy[j] - xy[i], xy[k] - xy[i])) for i, j, k in t)
        self.assertEqual(len(t), 4)
        self.assertAlmostEqual(a, 4.0 + 2.0, places=9)

    def test_collinear_vertex(self):
        xy = np.array([[0, 0], [1, 0], [2, 0], [2, 2], [0, 2]], float)
        t = FA.ear_clip(xy)
        a = sum(abs(0.5 * np.cross(xy[j] - xy[i], xy[k] - xy[i])) for i, j, k in t)
        self.assertAlmostEqual(a, 4.0, places=9)


class GridOriginV4(unittest.TestCase):
    def test_remaining_cells_kept(self):
        rect = np.array([[-50.0, -50.0], [50.0, 50.0]])
        full = wall(0, 10, 0, 10, y=0.0, outward=+1)
        nb = dict(id=2, building="B", normal=[0, -1, 0], tris=wall(2, 8, 0, 6, y=0.0, outward=-1))
        A = dict(id=1, building="A", normal=[0, 1, 0], tris=full)
        out, ov = cut_all([A, nb])
        rest = out[1]
        V0 = full.reshape(-1, 3); F0 = np.arange(len(V0)).reshape(-1, 3)
        V1 = rest.reshape(-1, 3); F1 = np.arange(len(V1)).reshape(-1, 3)
        n = [0.0, 1.0, 0.0]
        st0 = L.build_plane_store(V0, F0, np.ones(len(F0), int), [dict(ext=1, normal=n)], rect, 0.25)
        st1 = L.build_plane_store(V1, F1, np.ones(len(F1), int), [dict(ext=1, normal=n, o=V0[F0[0, 0]])], rect, 0.25)
        c0 = {tuple(np.round(c, 6)) for c in st0["loc_center"]}; c1 = {tuple(np.round(c, 6)) for c in st1["loc_center"]}
        self.assertTrue(c1 <= c0)
        cut_c = {c for c in c0 - c1}
        self.assertTrue(all(2.0 < c[0] < 8.0 and c[2] < 6.0 for c in cut_c))
        self.assertEqual(len(c0) - len(c1), 24 * 24)
        st1b = L.build_plane_store(V1, F1, np.ones(len(F1), int), [dict(ext=1, normal=n)], rect, 0.25)
        self.assertEqual(len(st1b["loc_center"]), len(st1["loc_center"]))   # same count here (origin at a grid corner)


class FilesV4(unittest.TestCase):
    def test_only_two_files_changed(self):
        v3 = ROOT / "src/phd/prior_propagation_v3"; v4 = ROOT / "src/phd/prior_propagation_v4"
        names = sorted(p.name for p in v3.glob("*.py"))
        self.assertEqual(names, sorted(p.name for p in v4.glob("*.py")))
        diff = [n for n in names if hashlib.sha256((v3 / n).read_bytes()).digest() != hashlib.sha256((v4 / n).read_bytes()).digest()]
        self.assertEqual(diff, ["faces.py", "locations.py"])


if __name__ == "__main__":
    unittest.main()

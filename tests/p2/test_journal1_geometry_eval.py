"""Synthetic unit tests for the journal1 Phase-A geometry evaluator."""

import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

_SPEC = importlib.util.spec_from_file_location(
    "journal1_geometry_eval",
    Path(__file__).resolve().parents[2] / "scripts/p2/journal1_phase_a_v1/geometry_eval.py")
ge = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ge)


def write_ply(path, xyz, cls):
    with open(path, "wb") as f:
        f.write((
            "ply\nformat binary_little_endian 1.0\n"
            f"element vertex {len(xyz)}\n"
            "property float x\nproperty float y\nproperty float z\n"
            "property uchar red\nproperty uchar green\nproperty uchar blue\n"
            "property uchar classification\nend_header\n").encode("ascii"))
        for (x, y, z), c in zip(xyz, cls):
            f.write(struct.pack("<fffBBBB", x, y, z, 0, 0, 0, int(c)))


def flat_grid(step=0.5, z=5.0, size=10.0):
    g = np.arange(step / 2, size, step)
    gx, gy = np.meshgrid(g, g)
    return np.stack([gx.ravel(), gy.ravel(), np.full(gx.size, z)], axis=1)


def square_faces(z=5.0, size=10.0):
    ring = np.array([[0, 0, z], [size, 0, z], [size, size, z], [0, size, z], [0, 0, z]],
                    dtype=np.float64)
    return [(ring, np.array([0.0, 0.0, 1.0]))]


class TestPly(unittest.TestCase):
    def test_roundtrip(self):
        pts = flat_grid()
        cls = np.full(len(pts), 6)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.points.ply"
            write_ply(p, pts, cls)
            xyz, c = ge.read_ply(p)
        self.assertEqual(len(xyz), len(pts))
        np.testing.assert_allclose(xyz, pts, atol=1e-5)
        self.assertTrue((c == 6).all())

    def test_roof_filter(self):
        xyz = flat_grid()
        cls = np.full(len(xyz), 6)
        cls[:10] = 2
        roof, flag = ge.roof_points(xyz, cls)
        self.assertIsNone(flag)
        self.assertEqual(len(roof), len(xyz) - 10)


class TestFaceSet(unittest.TestCase):
    def setUp(self):
        self.fs = ge.FaceSet(square_faces(), sample_step=0.5)

    def test_samples_on_plane(self):
        self.assertGreater(len(self.fs.samples), 300)
        self.assertTrue(np.allclose(self.fs.samples[:, 2], 5.0))
        self.assertTrue(np.allclose(np.abs(self.fs.sample_normals[:, 2]), 1.0))

    def test_distances(self):
        pts = np.array([[5.0, 5.0, 5.0],   # on plane
                        [5.0, 5.0, 6.0],   # 1 m above
                        [12.0, 5.0, 5.0]])  # 2 m past the edge
        d, n = self.fs.distances(pts)
        np.testing.assert_allclose(d, [0.0, 1.0, 2.0], atol=1e-6)
        self.assertTrue(np.allclose(np.abs(n[:, 2]), 1.0))


class TestMetrics(unittest.TestCase):
    def test_distance_metrics(self):
        d_a = np.array([0.05] * 90 + [2.0] * 10)
        d_r = np.array([0.05] * 100)
        row = ge.distance_metrics(d_a, d_r, [0.1, 0.5], 1.0)
        self.assertAlmostEqual(row["precision@0.1"], 0.9)
        self.assertAlmostEqual(row["completeness@0.1"], 1.0)
        self.assertAlmostEqual(row["outlier_rate"], 0.1)
        self.assertAlmostEqual(row["f1@0.1"], 2 * 0.9 / 1.9)

    def test_z_spread_double_surface(self):
        a = flat_grid(step=0.1, z=0.0)
        b = flat_grid(step=0.1, z=0.4)
        spread = ge.z_spread(np.concatenate([a, b]), cell=0.25)
        self.assertAlmostEqual(spread, 0.4, delta=0.05)
        single = ge.z_spread(a, cell=0.25)
        self.assertLess(single, 0.05)

    def test_coverage(self):
        r = flat_grid(step=0.25)
        full = ge.coverage(r.copy(), r, cell=0.25, z_tol=1.0)
        self.assertAlmostEqual(full, 1.0)
        half = ge.coverage(r[r[:, 0] < 5.0], r, cell=0.25, z_tol=1.0)
        self.assertAlmostEqual(half, 0.5, delta=0.05)

    def test_pca_normals_flat(self):
        n = ge.pca_normals(flat_grid(step=0.2), k=8)
        self.assertGreater(np.nanmedian(np.abs(n[:, 2])), 0.99)


class TestEvalBuildingArm(unittest.TestCase):
    def _cfg(self):
        return {"min_points": 30, "max_points_per_arm": 0, "knn": 8,
                "normal_match_tau": 0.5, "taus": [0.1, 0.25, 0.5],
                "tau_outlier": 1.0, "cell": 0.25, "coverage_z_tol": 1.0}

    def test_exact_and_offset(self):
        cfg = self._cfg()
        fs = ge.FaceSet(square_faces(), sample_step=0.25)
        e1 = flat_grid(step=0.2)
        e1n = ge.pca_normals(e1, k=8)
        exact = flat_grid(step=0.1)
        cls = np.full(len(exact), 6)
        rows = ge.eval_building_arm(exact, cls, fs, e1, e1n, cfg, False)
        by = {r["gt"]: r for r in rows}
        self.assertGreater(by["lod2"]["f1@0.1"], 0.99)
        self.assertLess(by["lod2"]["acc_median"], 0.01)
        self.assertGreater(by["e1"]["f1@0.1"], 0.99)
        offset = exact + np.array([0.0, 0.0, 0.3])
        rows = ge.eval_building_arm(offset, cls, fs, e1, e1n, cfg, False)
        by = {r["gt"]: r for r in rows}
        self.assertAlmostEqual(by["lod2"]["acc_median"], 0.3, delta=0.01)
        self.assertLess(by["lod2"]["precision@0.25"], 0.01)
        self.assertGreater(by["lod2"]["precision@0.5"], 0.99)

    def test_reference_arm_skips_e1(self):
        cfg = self._cfg()
        fs = ge.FaceSet(square_faces(), sample_step=0.25)
        pts = flat_grid(step=0.2)
        rows = ge.eval_building_arm(pts, np.full(len(pts), 6), fs, pts,
                                    ge.pca_normals(pts, 8), cfg, True)
        self.assertEqual([r["gt"] for r in rows], ["lod2"])

    def test_empty_arm_flag(self):
        cfg = self._cfg()
        fs = ge.FaceSet(square_faces(), sample_step=0.25)
        rows = ge.eval_building_arm(np.zeros((0, 3)), None, fs, None, None, cfg, False)
        self.assertTrue(all("EMPTY_ARM" in r["flag"] for r in rows))


if __name__ == "__main__":
    unittest.main()

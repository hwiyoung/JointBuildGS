"""Unit checks for the stage-1 confidence/tolerance/conflict helpers (run in jointbuildgs:dev)."""
import os
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("JBGS_EXPERIMENT_CONFIG", str(ROOT / "configs/phd/stage1_conf_tol_conflict_v1/experiment.json"))
os.environ.setdefault("JBGS_REPO_ROOT", str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/phd/stage1_conf_tol_conflict_v1"))
import common as cm  # noqa: E402


class StatsTests(unittest.TestCase):
    def test_nmad_of_gaussian(self):
        rng = np.random.default_rng(0)
        x = rng.normal(0.3, 0.05, 200000)
        m, s = cm.median_nmad(x)
        self.assertAlmostEqual(m, 0.3, places=2)
        self.assertAlmostEqual(s, 0.05, places=2)

    def test_two_pass_removes_tail(self):
        rng = np.random.default_rng(1)
        x = np.concatenate([rng.normal(0, 0.1, 10000), np.full(500, 5.0)])
        r = cm.two_pass(x)
        self.assertGreater(r["out_frac"], 0.04)
        self.assertLess(abs(r["m2"]), 0.01)
        self.assertLess(abs(r["s2"] - 0.1), 0.01)

    def test_two_pass_empty(self):
        r = cm.two_pass(np.array([np.nan, np.nan]))
        self.assertEqual(r["n"], 0)
        self.assertIsNone(r["m"])

    def test_constants_frozen(self):
        self.assertEqual(cm.C["consistent_views_threshold"], 3)
        self.assertEqual(cm.C["k_tolerance"], 2.5)
        self.assertEqual(cm.C["outlier_sigma"], 3.0)
        self.assertEqual(cm.CFG["priors"]["L"]["tau_spec_m"], 0.12)
        self.assertEqual(cm.CFG["priors"]["M"]["tau_spec_m"], 1.0)


class CameraTests(unittest.TestCase):
    def _view(self):
        q = [1.0, 0.0, 0.0, 0.0]
        return {"W": 4, "H": 2, "K": np.array([[2.0, 0, 2.0], [0, 2.0, 1.0], [0, 0, 1]]), "R": cm.qvec2rotmat(q), "t": np.zeros(3), "C": np.zeros(3)}

    def test_pixel_centre_convention(self):
        u, v = cm.pixel_dirs(self._view())
        np.testing.assert_allclose(u, [-0.75, -0.25, 0.25, 0.75])
        np.testing.assert_allclose(v, [-0.25, 0.25])

    def test_project_roundtrip(self):
        view = self._view()
        u, v = cm.pixel_dirs(view)
        X = np.array([[u[2] * 10, v[1] * 10, 10.0]])
        ui, vi, z = cm.project(view, X)
        self.assertEqual((int(ui[0]), int(vi[0])), (2, 1))
        self.assertAlmostEqual(float(z[0]), 10.0)

    def test_vertical_factor_nadir(self):
        view = self._view()
        view["R"] = np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1.0]])  # camera looking straight down
        dz = cm.world_dir_z(view)
        np.testing.assert_allclose(np.abs(dz), 1.0)


class ColourTests(unittest.TestCase):
    def test_diverging_fixed_scale(self):
        rgb = cm.diverging_rgb(np.array([[-1.5, 0.0, 1.5, np.nan]]), -1.5, 1.5)
        self.assertEqual(rgb[0, 1].tolist(), [255, 255, 255])
        self.assertEqual(rgb[0, 3].tolist(), [128, 128, 128])
        self.assertGreater(rgb[0, 2, 0], rgb[0, 2, 2])
        self.assertGreater(rgb[0, 0, 2], rgb[0, 0, 0])

    def test_downscale_nearest(self):
        a = np.arange(40).reshape(4, 10)
        b = cm.downscale_nearest(a, 5)
        self.assertEqual(b.shape, (2, 5))


if __name__ == "__main__":
    unittest.main()

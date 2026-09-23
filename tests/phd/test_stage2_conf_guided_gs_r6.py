"""CPU unit tests of the r6 rules of the stage-2 judgment module (PHD-STAGE2-R6-FIX-v1), one class per fix:
  (1)  compute_E_render: one-sided occlusion by the current render, empty pixels occlude nothing; first E uses the prior
  (1a) due_E_iteration: iteration 1 and multiples of the interval
  (2)  lock_rule_r6: E < threshold and drift <= 4 tau_v, independent of the number of seeing views
  (3)  floor at the moment of protection (update_E with a fake model and a fake renderer)
  (4)  init_visible_filter: prior points no training view sees are removed, image points kept
  (5)  depth-term normalisation by the pixel count
and a guard that the lock code is byte-identical to r5.
The r6 fork root is taken from JBGS_R6_FORK (default /r6/sources/GeoGS-conf-guided-v1-r6), the r5 overlay for the guard from
JBGS_R5_OVERLAY (default /repo/scripts/phd/stage2_conf_guided_gs_v1/jbgs_judgment.py)."""
import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

FORK = Path(os.environ.get("JBGS_R6_FORK", "/r6/sources/GeoGS-conf-guided-v1-r6"))
R5 = Path(os.environ.get("JBGS_R5_OVERLAY", "/repo/scripts/phd/stage2_conf_guided_gs_v1/jbgs_judgment.py"))
if not FORK.exists():
    raise unittest.SkipTest(f"r6 fork not found: {FORK}")
sys.path.insert(0, str(FORK))
import jbgs_judgment as J  # noqa: E402

W_, H_ = 160, 120
FX, FY, CX, CY = 200.0, 205.0, 82.3, 58.7


def make_camera(R, T, name="cam"):
    """Camera stand-in with the fork's conventions (same helper as tests/phd/test_stage2_conf_guided_gs_v1.py)."""
    from utils.graphics_utils import getWorld2View2, getProjectionMatrix, focal2fov
    wvt = torch.tensor(getWorld2View2(R, T)).transpose(0, 1)
    proj = getProjectionMatrix(znear=0.01, zfar=100.0, fovX=focal2fov(FX, W_), fovY=focal2fov(FY, H_)).transpose(0, 1)
    p = proj.T.clone()
    p[0, 0] = 2 * FX / W_; p[1, 1] = 2 * FY / H_
    p[0, 2] = (2 * CX + 1 - W_) / W_; p[1, 2] = (2 * CY + 1 - H_) / H_
    proj = p.T.contiguous()
    return SimpleNamespace(image_name=name, image_width=W_, image_height=H_, world_view_transform=wvt,
                           projection_matrix=proj, full_proj_transform=wvt @ proj)


CAM0 = make_camera(np.eye(3), np.zeros(3), "v0")
CAM1 = make_camera(np.eye(3), np.zeros(3), "v1")


class DueE(unittest.TestCase):
    def test_schedule(self):
        due = [i for i in range(1, 3601) if J.due_E_iteration(i, 500)]
        self.assertEqual(due, [1, 500, 1000, 1500, 2000, 2500, 3000, 3500])
        self.assertFalse(J.due_E_iteration(501, 500)); self.assertFalse(J.due_E_iteration(3001, 500))


class RenderOcclusion(unittest.TestCase):
    def setUp(self):
        self.A = {"v0": torch.ones(H_, W_), "v1": torch.zeros(H_, W_)}
        self.D = {"v0": torch.full((H_, W_), 10.0), "v1": torch.full((H_, W_), 10.0)}
        self.AL = {"v0": torch.ones(H_, W_), "v1": torch.ones(H_, W_)}

    def test_one_sided(self):
        pts = torch.tensor([[0.0, 0.0, 9.0],     # 1 m in front of the rendered surface -> seen in both views
                            [0.0, 0.0, 10.4],    # 0.4 m behind -> seen
                            [0.0, 0.0, 10.6],    # 0.6 m behind -> hidden in both -> E = 0, cnt = 0
                            [50.0, 0.0, 10.0]])  # outside both images -> not counted
        E, cnt, n_empty = J.compute_E_render(pts, [CAM0, CAM1], self.A, self.D, self.AL, 0.5, 0.05)
        np.testing.assert_allclose(cnt.numpy(), [2, 2, 0, 0])
        np.testing.assert_allclose(E.numpy(), [0.5, 0.5, 0.0, 0.0], atol=1e-6)
        self.assertEqual(n_empty, 0)

    def test_empty_pixels_occlude_nothing(self):
        AL = {"v0": torch.full((H_, W_), 0.01), "v1": torch.ones(H_, W_)}   # v0 renders (almost) nothing
        pts = torch.tensor([[0.0, 0.0, 30.0]])                              # far behind D = 10
        E, cnt, n_empty = J.compute_E_render(pts, [CAM0, CAM1], self.A, self.D, AL, 0.5, 0.05)
        self.assertEqual(cnt.tolist(), [1.0])      # seen in v0 (empty pixel), hidden in v1
        self.assertAlmostEqual(float(E[0]), 1.0)   # A of v0
        self.assertEqual(n_empty, 1)
        D0 = {"v0": torch.zeros(H_, W_), "v1": self.D["v1"]}                 # empty depth also occludes nothing
        _, cnt0, _ = J.compute_E_render(pts, [CAM0, CAM1], self.A, D0, self.AL, 0.5, 0.05)
        self.assertEqual(cnt0.tolist(), [1.0])

    def test_prior_rule_is_two_sided(self):
        P = {"v0": torch.full((H_, W_), 10.0), "v1": torch.full((H_, W_), 10.0)}
        pts = torch.tensor([[0.0, 0.0, 9.0], [0.0, 0.0, 10.4]])
        E, cnt = J.compute_E(pts, [CAM0, CAM1], self.A, P, 0.5)
        np.testing.assert_allclose(cnt.numpy(), [0, 2])   # 1 m in front of the prior surface does not count (r5 rule)


class LockRule(unittest.TestCase):
    def test_rule(self):
        E = torch.tensor([0.0, 0.2, 0.2, 0.5, 0.9, 0.0])
        drift = torch.tensor([0.0, 0.227, 0.228, 0.0, 0.0, 0.1])
        prior = torch.tensor([True, True, True, True, True, False])
        lock, far = J.lock_rule_r6(E, drift, prior, 0.5, 0.227)
        self.assertEqual(lock.tolist(), [True, True, False, False, False, False])
        self.assertEqual(far.tolist(), [False, False, True, False, False, False])

    def test_threshold_from_tau(self):
        self.assertAlmostEqual(4.0 * 0.05677034870849456, 0.2270813948, places=6)


class FakeModel:
    """Minimal GaussianModel stand-in on the CPU (the fields update_E and init_visible_filter touch)."""

    def __init__(self, xyz, origin, opacity):
        self._xyz = torch.nn.Parameter(torch.as_tensor(xyz, dtype=torch.float32))
        self._opacity = torch.nn.Parameter(torch.logit(torch.as_tensor(opacity, dtype=torch.float32)).reshape(-1, 1))
        self.origin = torch.as_tensor(origin, dtype=torch.int8)
        self.frozen_mask = torch.zeros(len(origin), dtype=torch.bool)
        self.init_id = torch.arange(len(origin), dtype=torch.int32)

    @property
    def get_xyz(self):
        return self._xyz

    @property
    def get_opacity(self):
        return torch.sigmoid(self._opacity)

    @staticmethod
    def inverse_opacity_activation(x):
        return torch.log(x / (1 - x))

    def set_frozen_mask(self, m):
        self.frozen_mask = m.bool()

    def prune_points(self, mask):
        keep = ~mask
        self._xyz = torch.nn.Parameter(self._xyz.detach()[keep]); self._opacity = torch.nn.Parameter(self._opacity.detach()[keep])
        self.origin = self.origin[keep]; self.frozen_mask = self.frozen_mask[keep]; self.init_id = self.init_id[keep]


class InitFilter(unittest.TestCase):
    def test_filter(self):
        P = {"v0": torch.full((H_, W_), 10.0), "v1": torch.full((H_, W_), 10.0)}
        A = {"v0": torch.ones(H_, W_), "v1": torch.ones(H_, W_)}
        xyz = [[0.0, 0.0, 10.0],    # prior on the prior surface -> kept
               [0.0, 0.0, 15.0],    # prior 5 m behind the prior surface (e.g. a ground face under a roof) -> dropped
               [50.0, 0.0, 10.0],   # prior outside every image -> dropped
               [0.0, 0.0, 15.0]]    # image-origin point, never filtered
        g = FakeModel(xyz, [1, 1, 1, 0], [0.1] * 4)
        info = J.init_visible_filter(g, [CAM0, CAM1], A, P, 0.5)
        self.assertEqual((info["n_prior_before"], info["n_prior_dropped"], info["n_prior_kept"]), (3, 2, 1))
        self.assertEqual(g.get_xyz.shape[0], 2)
        self.assertEqual(g.origin.tolist(), [1, 0])
        self.assertEqual(g.init_id.tolist(), [0, 3])


class UpdateE(unittest.TestCase):
    """update_E end to end on the CPU: first computation with the prior depth, later ones with the render; protection by
    E and distance; the opacity floor holds the moment protection is set."""

    def test_update(self):
        tmp = Path(tempfile.mkdtemp())
        xyz = [[0.0, 0.0, 10.0], [0.0, 0.0, 10.0], [0.0, 0.0, 10.0], [0.0, 0.0, 10.0]]
        g = FakeModel(xyz, [1, 1, 1, 0], [0.01, 0.01, 0.9, 0.01])
        jd = object.__new__(J.Judgment)
        jd.mode = "P"; jd.tb = None; jd.mon = tmp
        jd.args = SimpleNamespace(jbgs_e_depth_tol=0.5, jbgs_e_alpha_min=0.05, jbgs_e_threshold=0.5,
                                  jbgs_lock_opacity_floor=0.5, jbgs_e_interval=500)
        jd.train_cams = [CAM0, CAM1]
        jd.A = {"v0": torch.zeros(H_, W_), "v1": torch.zeros(H_, W_)}   # nothing measured: every seen disk has E = 0
        jd.P = {"v0": torch.full((H_, W_), 10.0), "v1": torch.full((H_, W_), 10.0)}
        jd.init_xyz = g.get_xyz.detach().clone()
        jd.lock_drift_max = 0.227
        jd.E_calls = 0; jd.keep_maps = False; jd.last_maps = None
        calls = []

        def fake_render(cam, model, pipe, bg):
            calls.append(cam.image_name)
            return {"surf_depth": torch.full((1, H_, W_), 10.0), "rend_alpha": torch.ones(1, H_, W_)}
        jd.render_fn, jd.pipe, jd.background = fake_render, None, None
        J.Judgment.update_E(jd, 1, g)
        self.assertEqual(jd.E_how, "prior_depth"); self.assertEqual(calls, [])
        self.assertEqual(g.frozen_mask.tolist(), [True, True, True, False])
        op = g.get_opacity.detach().squeeze(-1)
        self.assertTrue(bool((op[:3] >= 0.5 - 1e-6).all()))          # floor at the moment of protection (fix 3)
        self.assertAlmostEqual(float(op[2]), 0.9, places=5)            # higher opacity untouched
        self.assertAlmostEqual(float(op[3]), 0.01, places=5)           # image disk untouched
        with torch.no_grad():                                          # disk 0 moves 0.3 m (> 0.227), disk 1 goes 2 m behind D
            g._xyz.data[0, 0] += 0.3
            g._xyz.data[1, 2] += 2.0
        J.Judgment.update_E(jd, 500, g)
        self.assertEqual(jd.E_how, "render_depth"); self.assertEqual(calls, ["v0", "v1"])
        self.assertEqual(g.frozen_mask.tolist(), [False, False, True, False])   # 0: too far; 1: too far (2 m) although hidden
        self.assertEqual(jd.E_cnt.tolist()[:3], [2.0, 0.0, 2.0])               # disk 1 hidden behind the render in both views
        rows = [l for l in (tmp / "E.jsonl").read_text().splitlines() if l.strip()]
        self.assertEqual(len(rows), 2)
        import json
        last = json.loads(rows[-1])
        self.assertEqual((last["n_released"], last["n_released_far"]), (2, 2))


class Normalisation(unittest.TestCase):
    def test_pixel_denominator(self):
        D = torch.full((4, 5), 2.0); M = torch.full((4, 5), float("nan")); M[0, :2] = 1.0
        A = torch.zeros(4, 5); A[0, :2] = 1.0
        old, n, _ = J.weighted_l1(D, M, A)
        new, n2, _ = J.weighted_l1(D, M, A, float(D.numel()))
        self.assertAlmostEqual(float(old), 1.0, places=6); self.assertAlmostEqual(float(new), 2.0 / 20.0, places=6)
        self.assertEqual((n, n2), (2, 2))
        P = torch.full((4, 5), 2.5); tau = torch.full((4, 5), 0.1); w = 1.0 - A
        old_p, *_ = J.truncated_prior_loss(D, P, tau, w, 4.0)
        new_p, *_ = J.truncated_prior_loss(D, P, tau, w, 4.0, float(D.numel()))
        self.assertAlmostEqual(float(old_p), 0.3, places=5)                      # rho = 3 tau (|r| = 0.5 > 4 tau)
        self.assertAlmostEqual(float(new_p), 0.3 * 18 / 20, places=5)


class LockCodeUnchanged(unittest.TestCase):
    @unittest.skipUnless(R5.exists(), "r5 overlay not mounted")
    def test_lock_and_colour_code_identical_to_r5(self):
        src5 = R5.read_text()
        for fn in (J.scale_locked_update, J.Judgment.before_step, J.Judgment.after_step, J.Judgment.exempt_mask, J.rho_truncated):
            self.assertIn(inspect.getsource(fn), src5, fn.__name__)


if __name__ == "__main__":
    unittest.main()

"""CPU unit tests for the stage-2 judgment module (ORDER_ko_v1 section 6 step 2): rho_tau, tau_p conversion and the
stage-1 sign convention, section-7 roof rules, the Adam-proof lock, projection/E on a synthetic camera, face read-out
labels, NaN handling of the weighted terms.
The fork root is taken from JBGS_S2_FORK (default: the payload's sources/GeoGS-conf-guided-v1 under /s2)."""
import math
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

FORK = Path(os.environ.get("JBGS_S2_FORK", "/s2/sources/GeoGS-conf-guided-v1"))
if not FORK.exists():
    raise unittest.SkipTest(f"fork not found: {FORK}")
sys.path.insert(0, str(FORK))
import jbgs_judgment as J  # noqa: E402


def make_camera(R, T, fx, fy, cx, cy, W, H, name="cam"):
    """Camera stand-in with the fork's conventions (world_view_transform transposed; projection from K like the
    jbgs_camera_adapter)."""
    from utils.graphics_utils import getWorld2View2, getProjectionMatrix, focal2fov
    wvt = torch.tensor(getWorld2View2(R, T)).transpose(0, 1)
    proj = getProjectionMatrix(znear=0.01, zfar=100.0, fovX=focal2fov(fx, W), fovY=focal2fov(fy, H)).transpose(0, 1)
    p = proj.T.clone()
    p[0, 0] = 2 * fx / W; p[1, 1] = 2 * fy / H
    p[0, 2] = (2 * cx + 1 - W) / W; p[1, 2] = (2 * cy + 1 - H) / H
    proj = p.T.contiguous()
    return SimpleNamespace(image_name=name, image_width=W, image_height=H, world_view_transform=wvt,
                           projection_matrix=proj, full_proj_transform=wvt @ proj)


class RhoTests(unittest.TestCase):
    def test_values(self):
        tau = torch.tensor([0.05, 0.05, 0.05, 0.05])
        r = torch.tensor([0.03, -0.1, 0.2, 1.0])
        out = J.rho_truncated(r, tau, 4.0)
        np.testing.assert_allclose(out.numpy(), [0.0, 0.05, 0.15, 0.15], atol=1e-7)

    def test_gradient_zero_beyond_4tau(self):
        tau = torch.full((3,), 0.05)
        r = torch.tensor([0.1, 0.19, 1.0], requires_grad=True)
        J.rho_truncated(r, tau, 4.0).sum().backward()
        np.testing.assert_allclose(r.grad.numpy(), [1.0, 1.0, 0.0], atol=1e-7)


class TauConversionTests(unittest.TestCase):
    def test_vertical_residual_sign_convention(self):
        """Stage-1 convention: (D - P) * f is +dz when the prior P lies dz ABOVE the rendered surface D."""
        # sloped plane through the origin with unit normal n; ray d from the camera at C; the prior is the same plane
        # raised by dz = 0.7 m vertically (plane offset n_z * dz)
        n = np.array([0.0, 0.5, math.sqrt(0.75)]); C = np.array([3.0, -4.0, 40.0]); d = np.array([0.2, 0.1, -1.0])
        dz = 0.7
        t_surface = -(n @ C) / (n @ d); t_prior = -(n @ C - n[2] * dz) / (n @ d)
        D, P = t_surface * abs(d[2]), t_prior * abs(d[2])                # camera-Z depth (looking down, d_z = -1)
        self.assertLess(P, D)                                           # a raised prior is closer to the camera
        f = abs(n @ d) / abs(n[2])
        self.assertAlmostEqual((D - P) * f, +dz, places=6)
        # tau_p = tau_v / f turns the vertical width into the camera-depth width of this pixel
        tau_v = 0.05
        self.assertAlmostEqual(abs(D - P) - tau_v / f, (dz - tau_v) / f, places=6)


class RoofCheckTests(unittest.TestCase):
    """ORDER section 7 rows for the main roof with the stage-1 sign (+ = prior above the render)."""
    tau = 0.057

    def test_nominal(self):
        self.assertEqual(J.roof_check("N", 1000, 0.5, self.tau)[1], "pending")
        self.assertEqual(J.roof_check("N", 2000, 0.01, self.tau)[1], "green")
        self.assertEqual(J.roof_check("N", 2000, -0.1, self.tau)[1], "yellow")
        self.assertEqual(J.roof_check("N", 30000, 0.3, self.tau)[1], "red")

    def test_injected_moving(self):
        self.assertEqual(J.roof_check("B", 2000, 0.4, self.tau)[1], "green")    # surface left the raised prior
        self.assertEqual(J.roof_check("B", 2000, 0.0, self.tau)[1], "red")      # stays on the prior
        self.assertEqual(J.roof_check("B", 5000, -0.4, self.tau)[1], "red")     # moved the wrong way (above the prior)

    def test_injected_returned(self):
        self.assertEqual(J.roof_check("B", 15000, 0.98, self.tau)[1], "green")
        self.assertEqual(J.roof_check("B", 15000, 0.75, self.tau)[1], "yellow")  # 4 tau = 0.228 < |d-1| < 0.3
        self.assertEqual(J.roof_check("B", 30000, 0.5, self.tau)[1], "red")
        self.assertEqual(J.roof_check("B", 30000, -1.0, self.tau)[1], "red")


class LockUpdateTests(unittest.TestCase):
    """Why the lock scales the applied update and not the gradient: Adam divides by the gradient scale."""

    def _run(self, kind, steps=200, scale=0.01):
        torch.manual_seed(0)
        x = torch.nn.Parameter(torch.zeros(4, 3))
        opt = torch.optim.Adam([x], lr=1e-3, eps=1e-15)
        lock = torch.tensor([True, True, False, False])
        if kind == "grad":
            x.register_hook(lambda g: g * torch.where(lock, scale, 1.0).view(-1, 1))
        target = torch.tensor([1.0, -2.0, 0.5]).repeat(4, 1)
        for _ in range(steps):
            opt.zero_grad()
            ((x - target) ** 2 * (1 + 0.3 * torch.randn(4, 3))).sum().backward()
            old = x.detach()[lock].clone()
            opt.step()
            if kind == "update":
                J.scale_locked_update(x, old, lock, scale)
        dist = x.detach().norm(dim=1)
        return float(dist[lock].mean() / dist[~lock].mean())

    def test_gradient_scaling_does_not_lock(self):
        self.assertGreater(self._run("grad"), 0.9)

    def test_update_scaling_locks(self):
        self.assertAlmostEqual(self._run("update"), 0.01, delta=0.002)


class LockRuleTests(unittest.TestCase):
    def test_lock_rule(self):
        # prior disks: unseen in place | unseen after moving 0.8 m | seen on the prior with A mostly 0 | seen, measured
        # image disk: unseen
        E = torch.tensor([0.0, 0.0, 0.2, 0.9, 0.0]); cnt = torch.tensor([0, 0, 3, 5, 0])
        drift = torch.tensor([0.1, 0.8, 0.8, 0.0, 0.9]); prior = torch.tensor([True, True, True, True, False])
        lock, off = J.lock_rule(E, cnt, drift, prior, 0.5, 0.5)
        self.assertEqual(lock.tolist(), [True, False, True, False, False])
        self.assertEqual(off.tolist(), [False, True, False, False, False])


class ProjectionAndETests(unittest.TestCase):
    def setUp(self):
        self.W, self.H = 160, 120
        self.fx, self.fy, self.cx, self.cy = 200.0, 205.0, 82.3, 58.7
        R = np.eye(3); T = np.array([0.0, 0.0, 0.0])
        self.cam = make_camera(R, T, self.fx, self.fy, self.cx, self.cy, self.W, self.H, "v0")

    def test_projection_matches_pinhole(self):
        pts = torch.tensor([[0.5, -0.3, 10.0], [-1.0, 0.7, 25.0], [2.0, 2.0, 8.0]])
        u, v, z = J.project_points(pts, self.cam)
        x, y, zz = pts[:, 0], pts[:, 1], pts[:, 2]
        np.testing.assert_allclose(z.numpy(), zz.numpy(), atol=1e-4)
        np.testing.assert_allclose(u.numpy(), (self.fx * x / zz + self.cx).numpy(), atol=1e-3)
        np.testing.assert_allclose(v.numpy(), (self.fy * y / zz + self.cy).numpy(), atol=1e-3)

    def test_E_from_A_and_prior_depth(self):
        A = torch.zeros(self.H, self.W); A[:, : self.W // 2] = 1.0            # photos measure the left half only
        P = torch.full((self.H, self.W), 10.0)                                # prior surface at depth 10
        cam2 = make_camera(np.eye(3), np.array([0.0, 0.0, 0.0]), self.fx, self.fy, self.cx, self.cy, self.W, self.H, "v1")
        A2 = torch.ones(self.H, self.W); P2 = P.clone()
        pts = torch.tensor([[-2.0, 0.0, 10.0],   # left half in both views -> E = 1
                            [2.0, 0.0, 10.0],    # right half: A=0 in v0, A=1 in v1 -> E = 0.5
                            [2.0, 0.0, 12.0],    # 2 m behind the prior surface -> no seeing view -> E = 0
                            [50.0, 0.0, 10.0]])  # outside both images -> E = 0
        E, cnt = J.compute_E(pts, [self.cam, cam2], {"v0": A, "v1": A2}, {"v0": P, "v1": P2}, 0.5)
        np.testing.assert_allclose(E.numpy(), [1.0, 0.5, 0.0, 0.0], atol=1e-6)
        np.testing.assert_allclose(cnt.numpy(), [2, 2, 0, 0])


class LossTests(unittest.TestCase):
    def test_weighted_l1_ignores_nan_and_unrendered(self):
        D = torch.tensor([[1.0, 2.0, 0.0, 3.0]]); M = torch.tensor([[1.5, float("nan"), 2.0, 3.0]]); w = torch.tensor([[1.0, 1.0, 1.0, 0.0]])
        loss, n, hole = J.weighted_l1(D, M, w)
        self.assertEqual((n, hole), (1, 1)); self.assertAlmostEqual(float(loss), 0.5, places=6)

    def test_truncated_prior_loss_weights_and_counts(self):
        D = torch.tensor([[1.0, 1.0, 1.0]]); P = torch.tensor([[1.02, 1.10, 2.0]]); tau = torch.full((1, 3), 0.05); w = torch.tensor([[1.0, 1.0, 1.0]])
        loss, n, hole, beyond = J.truncated_prior_loss(D, P, tau, w, 4.0)
        self.assertEqual((n, hole, beyond), (3, 0, 1))
        self.assertAlmostEqual(float(loss), (0.0 + 0.05 + 0.15) / 3, places=6)


class ReadoutTests(unittest.TestCase):
    def test_labels(self):
        def rec(d, e, cov, n=100):
            return dict(d=[torch.full((n,), d)], e=[torch.full((n,), e)], g=[], d_all=[torch.full((n,), d)], n_pixels=n, n_A=int(cov * n))
        # face 2 = injected roof back on the photos: 1 m below the raised prior (d = +1), on the MVS (e ~ 0)
        records = {1: rec(0.01, 0.0, 0.9), 2: rec(1.0, 0.01, 0.9), 3: rec(0.5, 0.5, 0.2), 4: rec(0.5, 0.5, 0.9)}
        rows = J.face_readout(records, 0.05, [1, 2, 3, 4], [])
        self.assertEqual([r["label"] for r in rows], ["preserve", "correct", "undecided", "other"])
        self.assertAlmostEqual(rows[1]["d"], 1.0)


if __name__ == "__main__":
    unittest.main()

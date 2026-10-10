"""Code tests of fork r13's three ablation flags (PHD-MAIN-STAGE2-v1 4.2): hand-made values, no scene, no training.

Run in Docker (the fork's image, one GPU):
  docker run --rm --gpus device=0 --network none -v $PWD:/repo:ro -w /repo --entrypoint python jointbuildgs:geogs-conf-guided-v1 \
      -m unittest tests.phd.test_fork_r13_ablations
r12's jbgs_judgment / gaussian_model are loaded next to r13's (by file path) to show that the default path computes the same.
scientific_verdict: null."""
import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[2]
R12 = REPO / "src/phd/forks/GeoGS-conf-guided-v1-r12"
R13 = REPO / "src/phd/forks/GeoGS-conf-guided-v1-r13"
CUDA = torch.cuda.is_available()


def load(path, name, root):
    sys.path.insert(0, str(root))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        sys.path.remove(str(root))


J12 = load(R12 / "jbgs_judgment.py", "jbgs_judgment_r12", R12)
J13 = load(R13 / "jbgs_judgment.py", "jbgs_judgment_r13", R13)


class Penalty(unittest.TestCase):
    def test_noband_shape(self):
        tau = torch.tensor(0.2, dtype=torch.float64)
        r = torch.tensor([0.0, 0.05, 0.2, 0.4, 0.8, 1.0, -0.4, -1.0], dtype=torch.float64)
        got = J13.rho_noband(r, tau, 4.0)
        want = torch.tensor([0.0, 0.05, 0.2, 0.4, 0.8, 0.8, 0.4, 0.8], dtype=torch.float64)
        self.assertTrue(torch.allclose(got, want))
        band = J13.rho_truncated(r, tau, 4.0)
        self.assertTrue(torch.allclose(band, torch.tensor([0.0, 0.0, 0.0, 0.2, 0.6, 0.6, 0.2, 0.6], dtype=torch.float64)))

    def test_noband_gradient(self):
        tau = torch.tensor(0.2, dtype=torch.float64)
        r = torch.tensor([0.05, 0.15, 0.3, 0.7, 0.9, -0.1, -0.5, -0.85], dtype=torch.float64, requires_grad=True)
        g, = torch.autograd.grad(J13.rho_noband(r, tau, 4.0).sum(), r)
        self.assertEqual(g.tolist(), [1.0, 1.0, 1.0, 1.0, 0.0, -1.0, -1.0, 0.0])          # pull from 0 to 4 tau, none beyond
        g2, = torch.autograd.grad(J13.rho_truncated(r, tau, 4.0).sum(), r)
        self.assertEqual(g2.tolist(), [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, -1.0, 0.0])         # r12: nothing inside tau

    def test_default_loss_equals_r12(self):
        g = torch.Generator().manual_seed(0)
        D = torch.rand((40, 60), generator=g, dtype=torch.float64) * 3 + 10
        P = D + (torch.rand((40, 60), generator=g, dtype=torch.float64) - 0.5) * 2.0
        P[0, :5] = float("nan")
        T = torch.full_like(D, 0.15); T[1, :3] = float("nan")
        W = (torch.rand((40, 60), generator=g) > 0.3).double()
        a = J12.truncated_prior_loss(D, P, T, W, 4.0, float(D.numel()))
        b = J13.truncated_prior_loss(D, P, T, W, 4.0, float(D.numel()))
        self.assertEqual(float(a[0]), float(b[0]))
        self.assertEqual(a[1:], b[1:])
        c = J13.truncated_prior_loss(D, P, T, W, 4.0, float(D.numel()), rho=J13.rho_noband)
        self.assertEqual(c[1:], a[1:])                                     # same pixels, same counts beyond 4 tau
        self.assertGreater(float(c[0]), float(a[0]))                       # the band's part is now charged

    def test_flags_registered_off(self):
        import argparse
        p = argparse.ArgumentParser()
        J13.register_args(p)
        a = p.parse_args([])
        self.assertEqual([getattr(a, f"jbgs_ablate_{n}") for n in J13.ABLATIONS], [0, 0, 0])
        self.assertEqual(J13.REVISION, "r13")


@unittest.skipUnless(CUDA, "needs a GPU (GaussianModel lives on cuda)")
class DensityMask(unittest.TestCase):
    def model(self, gm_mod, n=8):
        g = gm_mod.GaussianModel(0)
        g._xyz = torch.nn.Parameter(torch.arange(n * 3, dtype=torch.float, device="cuda").reshape(n, 3) * 0.01)
        g._features_dc = torch.nn.Parameter(torch.zeros((n, 1, 3), device="cuda"))
        g._features_rest = torch.nn.Parameter(torch.zeros((n, 0, 3), device="cuda"))
        g._scaling = torch.nn.Parameter(torch.full((n, 2), -5.0, device="cuda"))
        g._rotation = torch.nn.Parameter(torch.tensor([[1.0, 0, 0, 0]] * n, device="cuda"))
        op = torch.full((n, 1), 2.0, device="cuda"); op[:4] = -6.0              # rows 0-3 below opacity_cull
        g._opacity = torch.nn.Parameter(op)
        g.max_radii2D = torch.zeros(n, device="cuda")
        g.spatial_lr_scale = 1.0
        g.origin = torch.ones(n, dtype=torch.int8, device="cuda")
        g.init_id = torch.arange(n, dtype=torch.int32, device="cuda")
        g.training_setup(SimpleNamespace(percent_dense=0.01, position_lr_init=1e-4, position_lr_final=1e-6, position_lr_delay_mult=0.01,
                                         position_lr_max_steps=30000, feature_lr=0.0025, opacity_lr=0.05, scaling_lr=0.005, rotation_lr=0.001))
        return g

    def gm(self, root, name):
        return load(root / "scene/gaussian_model.py", name, root)

    def test_default_uses_frozen_mask(self):
        G13 = self.gm(R13, "gm_r13_a")
        g = self.model(G13)
        g.set_frozen_mask(torch.tensor([1, 0, 1, 0, 0, 0, 0, 0], dtype=torch.bool, device="cuda"))
        self.assertIsNone(g.density_mask)
        self.assertTrue(torch.equal(g.density_exempt(), g.frozen_mask))
        g.densify_and_prune(1e9, 0.05, 10.0, None)                          # no densification (huge threshold), prune rows 1, 3
        self.assertEqual(g.init_id.tolist(), [0, 2, 4, 5, 6, 7])

    def test_same_as_r12(self):
        G12, G13 = self.gm(R12, "gm_r12_b"), self.gm(R13, "gm_r13_b")
        a, b = self.model(G12), self.model(G13)
        m = torch.tensor([0, 1, 1, 0, 1, 0, 0, 1], dtype=torch.bool, device="cuda")
        a.set_frozen_mask(m.clone()); b.set_frozen_mask(m.clone())
        a.densify_and_prune(1e9, 0.05, 10.0, None); b.densify_and_prune(1e9, 0.05, 10.0, None)
        self.assertEqual(a.init_id.tolist(), b.init_id.tolist())
        self.assertTrue(torch.equal(a.frozen_mask, b.frozen_mask))

    def test_density_mask_used_and_aligned(self):
        G13 = self.gm(R13, "gm_r13_c")
        g = self.model(G13)
        g.set_frozen_mask(torch.tensor([1, 0, 0, 0, 0, 0, 0, 0], dtype=torch.bool, device="cuda"))       # gradient protection: row 0
        g.set_density_mask(torch.tensor([0, 1, 0, 1, 0, 0, 1, 0], dtype=torch.bool, device="cuda"))     # density exemption: rows 1, 3, 6
        self.assertTrue(torch.equal(g.density_exempt(), g.density_mask))
        g.densify_and_prune(1e9, 0.05, 10.0, None)                          # low opacity 0-3: 0 and 2 pruned, 1 and 3 kept
        self.assertEqual(g.init_id.tolist(), [1, 3, 4, 5, 6, 7])
        self.assertEqual(g.density_mask.tolist(), [True, True, False, False, True, False])
        self.assertEqual(g.frozen_mask.tolist(), [False] * 6)
        n0 = g.get_xyz.shape[0]
        g.densification_postfix(g._xyz[:2].detach(), g._features_dc[:2].detach(), g._features_rest[:2].detach(), g._opacity[:2].detach(),
                                g._scaling[:2].detach(), g._rotation[:2].detach(), new_origin=g.origin[:2], new_init_id=g.init_id[:2])
        self.assertEqual(g.get_xyz.shape[0], n0 + 2)
        self.assertEqual(g.density_mask.tolist()[-2:], [False, False])     # new rows: no exemption until the next re-read
        self.assertEqual(g.frozen_mask.shape[0], n0 + 2)

    def test_statistics_follow_density_mask(self):
        G13 = self.gm(R13, "gm_r13_d")
        g = self.model(G13)
        g.set_frozen_mask(torch.zeros(8, dtype=torch.bool, device="cuda"))
        g.set_density_mask(torch.tensor([1, 0, 0, 0, 0, 0, 0, 0], dtype=torch.bool, device="cuda"))
        vp = torch.ones((8, 3), device="cuda", requires_grad=True)
        vp.grad = torch.ones((8, 3), device="cuda")
        g.add_densification_stats(vp, torch.ones(8, dtype=torch.bool, device="cuda"))
        self.assertEqual(g.denom.squeeze(1).tolist(), [0.0] + [1.0] * 7)


if __name__ == "__main__":
    unittest.main()

"""Tests for the 4.4 audit (PHD-STAGE2-PROTECTION-AUDIT-v1), CPU only (run in jointbuildgs:geogs-conf-guided-v1):
  * every train.py anchor of build_audit_fork.py occurs exactly once in the frozen parent fork (the copy can be rebuilt),
  * the instrumented copy differs from the parent only by guarded insertions,
  * the Adam facts the audit relies on: gradient x0.01 leaves the Adam step unchanged, lr x0.01 and the implementation's
    post-step blend give 0.01 of the step, a gradient scale switched on mid-run only slows temporarily.
Paths: JBGS_S2_FORK (parent fork) and JBGS_AUDIT_FORK (audit copy); tests needing a missing path are skipped."""
import importlib.util
import os
import sys
import unittest
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "scripts/phd/stage2_protection_audit_v1"
PARENT = Path(os.environ.get("JBGS_S2_FORK", "/s2/sources/GeoGS-conf-guided-v1"))
AUDIT = Path(os.environ.get("JBGS_AUDIT_FORK", "/audit/sources/GeoGS-conf-guided-v1-audit"))


def edits():
    src = (HERE / "build_audit_fork.py").read_text()
    start = src.index("EDITS = [")
    ns = {"MARK": "# [jbgs_audit]"}
    exec(src[start:src.index("]\n\nshutil.copytree") + 2], ns)
    return ns["EDITS"]


class AnchorTests(unittest.TestCase):
    @unittest.skipUnless((PARENT / "train.py").exists(), "parent fork not mounted")
    def test_anchors_unique_in_parent(self):
        s = (PARENT / "train.py").read_text()
        for old, _ in edits():
            self.assertEqual(s.count(old), 1, old)

    @unittest.skipUnless((AUDIT / "train.py").exists() and (PARENT / "train.py").exists(), "audit copy not mounted")
    def test_copy_is_parent_plus_guarded_lines(self):
        a = (AUDIT / "train.py").read_text().splitlines()
        p = (PARENT / "train.py").read_text().splitlines()
        added = [ln for ln in a if "# [jbgs_audit]" in ln]
        self.assertEqual([ln for ln in a if "# [jbgs_audit]" not in ln], p)
        self.assertTrue(all(("audit is not None" in ln) or ln.strip().startswith(("import jbgs_audit", "audit = ",
                                                                                   "jbgs_audit.register_args"))
                            for ln in added), added)


def adam_move(kind, steps=1000, switch=500, scale=0.01, seed=0):
    g = torch.Generator().manual_seed(seed)
    grads = 1.0 + 2.0 * torch.randn(steps, generator=g, dtype=torch.float64)
    x = torch.nn.Parameter(torch.zeros(1, dtype=torch.float64))
    opt = torch.optim.Adam([x], lr=1e-3 * (scale if kind == "lr" else 1.0), betas=(0.9, 0.999), eps=1e-15)
    for t in range(steps):
        gs = scale if (kind == "grad" or (kind == "grad_late" and t >= switch)) else 1.0
        opt.zero_grad(); x.grad = (grads[t] * gs).reshape(1)
        old = x.detach().clone(); opt.step()
        if kind == "update":
            with torch.no_grad():
                x.data = old + scale * (x.data - old)
    return float(x.detach().abs())


class AdamFacts(unittest.TestCase):
    def test_gradient_scale_from_start_is_ineffective(self):
        self.assertAlmostEqual(adam_move("grad") / adam_move("none"), 1.0, places=6)

    def test_lr_and_update_scale_are_effective_and_equal(self):
        self.assertAlmostEqual(adam_move("lr") / adam_move("none"), 0.01, places=6)
        self.assertAlmostEqual(adam_move("update") / adam_move("lr"), 1.0, places=6)

    def test_gradient_scale_switched_on_late_slows_only_temporarily(self):
        r = adam_move("grad_late", steps=1000) / adam_move("none", steps=1000)
        self.assertTrue(0.01 < r < 1.0)


if __name__ == "__main__":
    unittest.main()

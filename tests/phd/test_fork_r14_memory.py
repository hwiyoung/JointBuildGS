"""Code tests of fork r14 (PHD-MAIN-FIX-v1 4.1, memory only): r13's eight tests run on r14, and the host maps.

Run in Docker (the fork's image, one GPU):
  docker run --rm --gpus device=0 --network none -v $PWD:/repo:ro -w /repo --entrypoint python jointbuildgs:geogs-conf-guided-v1 \
      -m unittest tests.phd.test_fork_r14_memory
r13's test module is imported with its fork root and module set to r14 (its revision check expects 'r14'); r12's files stay its
reference. scientific_verdict: null."""
import unittest

import torch

from tests.phd import test_fork_r13_ablations as T13

R14 = T13.REPO / "src/phd/forks/GeoGS-conf-guided-v1-r14"
J14 = T13.load(R14 / "jbgs_judgment.py", "jbgs_judgment_r14", R14)
T13.R13, T13.J13 = R14, J14          # r13's tests now read r14 (penalty, flags, density mask: unchanged files and code)


class PenaltyR14(T13.Penalty):
    def test_flags_registered_off(self):
        import argparse
        p = argparse.ArgumentParser()
        J14.register_args(p)
        a = p.parse_args([])
        self.assertEqual([getattr(a, f"jbgs_ablate_{n}") for n in J14.ABLATIONS], [0, 0, 0])
        self.assertEqual([a.jbgs_memlog_from, a.jbgs_memlog_to], [0, 0])        # r14-3 record off by default
        self.assertEqual(J14.REVISION, "r14")


class DensityMaskR14(T13.DensityMask):
    pass


@unittest.skipUnless(T13.CUDA, "needs a GPU")
class HostMapsTest(unittest.TestCase):
    def test_values_and_devices(self):
        g = torch.Generator().manual_seed(0)
        src = {f"v{i}": torch.rand((7, 9), generator=g) for i in range(3)}
        src["v1"][2, 3] = float("nan")
        h = J14.HostMaps(src)
        self.assertEqual(len(h), 3)
        self.assertIn("v0", h)
        self.assertNotIn("x", h)
        self.assertIsNone(h.get("x"))
        for k, v in src.items():
            self.assertFalse(h._h[k].is_cuda)
            self.assertTrue(h._h[k].is_pinned())
            out = h[k]
            self.assertTrue(out.is_cuda)
            self.assertTrue(torch.equal(torch.nan_to_num(out.cpu(), nan=-1.0), torch.nan_to_num(v, nan=-1.0)))
        self.assertEqual(sorted(h), sorted(src))
        self.assertTrue(all(v.is_cuda for v in h.values()))
        self.assertTrue(all(v.is_cuda for _, v in h.items()))

    def test_setitem_from_cuda_keeps_value(self):
        h = J14.HostMaps()
        x = (torch.arange(12, device="cuda").reshape(3, 4) % 3 == 0).float()
        h["a"] = x
        self.assertFalse(h._h["a"].is_cuda)
        self.assertTrue(torch.equal(h["a"], x))
        self.assertEqual(h.host_bytes(), 12 * 4)

    def test_reader_does_not_write_back(self):
        h = J14.HostMaps({"a": torch.zeros((2, 2))})
        y = h["a"]
        y += 1.0                        # a reader changing its copy does not change the map (no reader does this; checked)
        self.assertEqual(float(h["a"].sum()), 0.0)


if __name__ == "__main__":
    unittest.main()

"""Code tests of fork r15 (PHD-MAIN-STAGE3-v1 4.1 / 6.1: r14 + the read-only out-of-memory record, default off).

Run in Docker (the fork's image; no GPU needed):
  docker run --rm --network none -v $PWD:/repo:ro -w /repo --entrypoint python jointbuildgs:geogs-conf-guided-v1 \
      -m unittest tests.phd.test_fork_r15_oom_record
What is tested here: r15 differs from r14 only by train.py (three places) and the new jbgs_oom_record.py; the flag is off by default; off,
the wrapper is a plain call (no record, the error passes); on, a CUDA out-of-memory error writes monitor/oom_record.json from the training
frame's locals and is raised again, any other error passes without a record. The Python screen radius against the rasterizer's own radii
is checked on six fixed checkpoints by the task's probe (checks/compare_probe.json: 99.65-99.74 % equal, the 99th percentile within 0.5 %).
scientific_verdict: null."""
import difflib
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[2]
R14 = REPO / "src/phd/forks/GeoGS-conf-guided-v1-r14"
R15 = REPO / "src/phd/forks/GeoGS-conf-guided-v1-r15"
spec = importlib.util.spec_from_file_location("jbgs_oom_record_r15", R15 / "jbgs_oom_record.py")
OR = importlib.util.module_from_spec(spec)
spec.loader.exec_module(OR)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Files(unittest.TestCase):
    def test_only_two_files_differ(self):
        skip = ("media/", "submodules/")
        f14 = {str(p.relative_to(R14)) for p in R14.rglob("*") if p.is_file() and "__pycache__" not in p.parts and not str(p.relative_to(R14)).startswith(skip)}
        f15 = {str(p.relative_to(R15)) for p in R15.rglob("*") if p.is_file() and "__pycache__" not in p.parts and not str(p.relative_to(R15)).startswith(skip)}
        self.assertEqual(f15 - f14, {"jbgs_oom_record.py"})
        self.assertEqual(f14 - f15, set())
        changed = {f for f in f14 if sha(R14 / f) != sha(R15 / f)}
        self.assertEqual(changed, {"train.py"})

    def test_train_diff_three_places(self):
        a = (R14 / "train.py").read_text().splitlines()
        b = (R15 / "train.py").read_text().splitlines()
        added = [l for l in difflib.ndiff(a, b) if l.startswith("+ ")]
        removed = [l for l in difflib.ndiff(a, b) if l.startswith("- ")]
        self.assertEqual(len(removed), 1)                       # the call of training()
        self.assertTrue(removed[0].strip("- ").startswith("training(dataset"))
        self.assertEqual(len(added), 4)                         # import, register_args, the wrapped call (two lines)
        self.assertTrue(all("jbgs_oom_record" in l or "args.checkpoint_iterations" in l for l in added))


class Flag(unittest.TestCase):
    def test_default_off(self):
        import argparse
        p = argparse.ArgumentParser()
        OR.register_args(p)
        self.assertEqual(p.parse_args([]).jbgs_oom_record, 0)


class Guarded(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.args = type("A", (), {})()
        self.args.model_path = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def rec(self):
        return Path(self.tmp.name) / "monitor/oom_record.json"

    def test_off_is_plain_call(self):
        self.args.jbgs_oom_record = 0
        self.assertEqual(OR.run_guarded(lambda x: x + 1, self.args, 1), 2)

        def boom():
            raise torch.cuda.OutOfMemoryError("CUDA out of memory. Tried to allocate 1.00 GiB")
        with self.assertRaises(torch.cuda.OutOfMemoryError):
            OR.run_guarded(boom, self.args)
        self.assertFalse(self.rec().exists())

    def test_on_records_and_reraises(self):
        self.args.jbgs_oom_record = 1

        class G:
            get_xyz = torch.zeros((5, 3))

        # the record reads the frame of train.py's training(): compile a stand-in under that file name
        ns = dict(torch=torch, G=G)
        exec(compile("def training():\n    gaussians, iteration, viewpoint_cam = G(), 1234, None\n"
                     "    raise torch.cuda.OutOfMemoryError('CUDA out of memory. Tried to allocate 19.02 GiB')\n", "train.py", "exec"), ns)
        training = ns["training"]
        with self.assertRaises(torch.cuda.OutOfMemoryError):
            OR.run_guarded(training, self.args)
        self.assertTrue(self.rec().exists())
        d = json.loads(self.rec().read_text())
        self.assertEqual(d["iteration"], 1234)
        self.assertEqual(d["n_gaussians"], 5)
        self.assertIn("19.02 GiB", d["error"])
        self.assertTrue(any("training" in s for s in d["stack"]))

    def test_on_other_error_passes(self):
        self.args.jbgs_oom_record = 1

        def training():
            raise ValueError("not a memory error")
        with self.assertRaises(ValueError):
            OR.run_guarded(training, self.args)
        self.assertFalse(self.rec().exists())


if __name__ == "__main__":
    unittest.main()

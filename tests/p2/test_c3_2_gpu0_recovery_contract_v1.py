import pathlib
import unittest

import yaml


ROOT = pathlib.Path(__file__).resolve().parents[2]


class C3TwoGpuZeroRecoveryContractTest(unittest.TestCase):
    def test_recovery_changes_only_comment_and_output_directory(self):
        base_path = ROOT / "configs/p2/c1_c2_c3_utarget199_v1/c3_2_sem_depth_seed0.yaml"
        recovery_path = ROOT / "configs/p2/c1_c2_c3_utarget199_v1/c3_2_sem_depth_seed0_gpu0_recovery.yaml"
        base = yaml.safe_load(base_path.read_text(encoding="utf-8"))
        recovery = yaml.safe_load(recovery_path.read_text(encoding="utf-8"))
        differing = {key for key in base if base[key] != recovery[key]}
        self.assertEqual(differing, {"out_dir"})
        self.assertIn("GPU0-RECOVERY", recovery["out_dir"])
        self.assertEqual(recovery["seed"], 0)
        self.assertEqual(recovery["max_iter"], 30000)
        self.assertEqual(recovery["w_depth"], 0.03)
        self.assertIsNone(recovery["scientific_verdict"])


if __name__ == "__main__":
    unittest.main()

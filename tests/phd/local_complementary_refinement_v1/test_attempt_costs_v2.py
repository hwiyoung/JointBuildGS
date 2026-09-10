"""Parallel wall time and device-sampling scope checks."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/phd/local_complementary_refinement_v1'))
from attempt_costs_v2 import interval_union_seconds, sampled_device_usage


class AttemptCostTests(unittest.TestCase):
    def test_parallel_nested_and_separate_intervals_are_not_added(self):
        self.assertEqual(interval_union_seconds([(4,7),(0,5),(1,2),(9,10),(7,7)]),8.)
        self.assertEqual(interval_union_seconds([(2,3),(0,1)]),2.)
        self.assertEqual(interval_union_seconds([]),0.)

    def test_invalid_or_reversed_intervals_fail(self):
        for intervals in [[(2,1)],[(0,float('inf'))],[(float('nan'),1)]]:
            with self.subTest(intervals=intervals),self.assertRaises(ValueError):interval_union_seconds(intervals)

    def test_whole_device_samples_keep_uuid_and_observed_maximum(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'gpu.csv';path.write_text('time, GPU-one, 465, 0\ntime, GPU-one, 20000, 98\n')
            self.assertEqual(sampled_device_usage(path),dict(sample_count=2,device_uuids='GPU-one',sampled_device_memory_peak_mib=20000.,sampled_device_utilization_peak_pct=98.))

    def test_absent_gpu_sampling_is_unmeasured_not_zero_usage(self):
        with tempfile.TemporaryDirectory() as root:
            r=sampled_device_usage(Path(root)/'absent.csv');self.assertEqual(r['sample_count'],0)
            self.assertIsNone(r['sampled_device_memory_peak_mib'])

    def test_malformed_nonfinite_or_invalid_device_sample_fails(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'gpu.csv'
            for payload in ['time, GPU-one, 3\n','time, GPU-one, nan, 20\n','time, GPU-one, -3, 20\n','time, GPU-one, 3, 101\n']:
                path.write_text(payload)
                with self.subTest(payload=payload),self.assertRaises(ValueError):sampled_device_usage(path)


if __name__=='__main__':unittest.main()

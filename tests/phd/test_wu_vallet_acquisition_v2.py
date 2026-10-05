import unittest

import numpy as np

from src.phd.wu_vallet_p3_v2.acquisition import group_pulses, recover_scan_coordinates


class PulseTests(unittest.TestCase):
    def test_strip_separation_unsorted_returns(self):
        result = group_pulses([1, 1, 1, 2], [31, 31, 32, 31], [2, 1, 1, 1], [2, 2, 1, 1],
                              [[0, 0, 1], [0, 0, 2], [1, 0, 0], [0, 1, 0]])
        np.testing.assert_array_equal(result["context_pulse_id"], [0, 0, 2, 1])
        np.testing.assert_array_equal(result["pulse_complete"], [True, True, True])
        self.assertEqual(result["pulse_first_context_row"][0], 1)

    def test_duplicate_return_is_ambiguous(self):
        result = group_pulses([1, 1], [31, 31], [1, 1], [2, 2], [[0, 0, 0], [0, 0, 1]])
        self.assertTrue(result["pulse_ambiguous"][0])
        self.assertFalse(result["pulse_complete"][0])

    def test_missing_return_preserved_incomplete(self):
        result = group_pulses([1, 1], [31, 31], [1, 3], [3, 3], [[0, 0, 2], [0, 0, 0]])
        self.assertFalse(result["pulse_ambiguous"][0])
        self.assertFalse(result["pulse_complete"][0])
        self.assertEqual(result["pulse_return_count"][0], 2)

    def test_missing_gps_rejected(self):
        with self.assertRaises(ValueError):
            group_pulses([np.nan], [31], [1], [1], [[0, 0, 0]])


class ScanTests(unittest.TestCase):
    @staticmethod
    def fixture():
        t = np.concatenate([k * .01 + np.arange(30) * .0001 for k in range(8)])
        a = np.tile(np.linspace(26, -26, 30), 8)
        return t, a

    def test_angle_resets_recover_scan_membership(self):
        t, a = self.fixture()
        out = recover_scan_coordinates(t, a)
        np.testing.assert_array_equal(out["scan_id"], np.repeat(np.arange(8), 30))
        self.assertEqual(out["report"]["boundary_count"], 7)
        self.assertEqual(out["complete_scan"].sum(), 180)

    def test_missing_pulse_does_not_compress_time_coordinate(self):
        t, a = self.fixture()
        keep = np.arange(len(t)) != 63
        out = recover_scan_coordinates(t[keep], a[keep])
        line = out["beam_coordinate"][out["scan_id"] == 2]
        self.assertGreater(line[3] - line[2], 1.9)

    def test_negative_reset_supported(self):
        t, a = self.fixture()
        out = recover_scan_coordinates(t, -a)
        self.assertEqual(out["report"]["reset_sign"], -1)

    def test_no_recurrent_reset_fails_closed(self):
        with self.assertRaises(ValueError):
            recover_scan_coordinates(np.arange(50.) * .0001, np.zeros(50))

    def test_unsorted_time_fails_closed(self):
        t, a = self.fixture()
        t[2] = t[1]
        with self.assertRaises(ValueError):
            recover_scan_coordinates(t, a)


if __name__ == "__main__":
    unittest.main()

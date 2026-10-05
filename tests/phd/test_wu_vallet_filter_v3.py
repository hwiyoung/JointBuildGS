import unittest

import numpy as np

from scripts.phd.wu_vallet_p3_v3.analyze_filtered_update import (
    assemble_status, components, legacy_vertex_labels,
)


class RegionFilterTests(unittest.TestCase):
    def setUp(self):
        self.xyz = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [1., 1., 0.],
                             [3., 0., 0.], [4., 0., 0.], [3., 1., 0.]])
        self.tri = np.array([[0, 1, 2], [1, 3, 2], [4, 5, 6]])

    def select(self, labels, threshold):
        raw = np.array(labels)
        return assemble_status(len(self.xyz), self.tri, raw,
                               components(self.xyz, self.tri, raw), threshold)

    def test_small_new_region_is_excluded_and_old_retained(self):
        result = self.select(["changed"] * 3, .75)
        np.testing.assert_array_equal(result["new_keep"], [1, 1, 1, 1, 0, 0, 0])
        np.testing.assert_array_equal(result["old_keep"], [0, 0, 0, 0, 1, 1, 1])
        self.assertTrue((result["status"][4:] == "filtered").all())

    def test_legacy_demoted_region_reenters_new_output(self):
        legacy = legacy_vertex_labels(7, self.tri, np.array(["changed", "changed", "single"]))
        self.assertTrue((legacy[4:] != "consistent").all())
        self.assertFalse(self.select(["changed"] * 3, .75)["new_keep"][4:].any())

    def test_raw_single_survives_independently(self):
        result = self.select(["changed", "changed", "single"], 2.)
        self.assertTrue((result["status"][4:] == "raw_single").all())
        self.assertTrue(result["new_keep"][4:].all())
        self.assertFalse(result["new_keep"][:4].any())

    def test_shared_vertex_does_not_join_regions(self):
        tri = np.array([[0, 1, 2], [2, 4, 5]])
        result = components(self.xyz, tri, np.array(["changed", "changed"]))
        self.assertEqual(len(result["area_m2"]), 2)

    def test_threshold_equality_retains_component(self):
        result = self.select(["changed"] * 3, .5)
        self.assertTrue(result["new_keep"].all())

    def test_mixed_consistent_precedes_retained_changed(self):
        result = self.select(["consistent", "changed", "changed"], .1)
        self.assertEqual(result["status"][1], "consistent")
        self.assertEqual(result["status"][3], "accepted_changed")
        self.assertFalse(result["new_keep"][1])

    def test_mixed_raw_single_precedes_filtered(self):
        result = self.select(["single", "changed", "changed"], 1.)
        self.assertEqual(result["status"][1], "raw_single")
        self.assertTrue(result["incident"]["filtered"][1])
        self.assertTrue(result["new_keep"][1])
        self.assertEqual(result["status"][3], "filtered")

    def test_isolated_vertex_unassessed_and_not_new_admitted(self):
        raw = np.array(["single"])
        tri = self.tri[:1]
        result = assemble_status(7, tri, raw, components(self.xyz, tri, raw), 1.)
        self.assertEqual(result["status"][6], "unassessed")
        self.assertFalse(result["new_keep"][6])
        self.assertTrue(result["old_keep"][6])

    def test_no_changed_faces(self):
        result = self.select(["consistent", "single", "single"], 1.)
        self.assertFalse(result["removed_face_mask"].any())
        self.assertEqual(result["status"][3], "raw_single")

    def test_invalid_area_rejected(self):
        for area in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.select(["changed"] * 3, area)


if __name__ == "__main__":
    unittest.main()

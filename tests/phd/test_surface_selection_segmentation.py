"""Synthetic geometry checks; no reference data or experiment payload required."""
import json
import unittest

import numpy as np

from src.phd.surface_selection_v1.segmentation import segment_source


def plane(x=(0, 6), y=(0, 5), z=4, slope=0, step=0.15):
    xx, yy = np.meshgrid(np.arange(*x, step), np.arange(*y, step))
    return np.column_stack((xx.ravel(), yy.ravel(), z + slope * xx.ravel()))


class SurfaceSegmentationTests(unittest.TestCase):
    def test_slope_not_cut_into_fixed_height_bins(self):
        points = plane(slope=0.4)
        original = points.copy()
        components, labels, graph = segment_source(points, [0, 0, 1])
        self.assertEqual(len(components), 1)
        self.assertGreater(np.mean(labels == 0), 0.97)
        self.assertLess(components[0]["rms_m"], 1e-10)
        self.assertGreater(components[0]["tilt_from_up_deg"], 20)
        np.testing.assert_array_equal(points, original)
        self.assertFalse(graph["summary"]["native_geometry_replaced"])
        self.assertEqual(labels.dtype, np.int32)

    def test_parallel_step_separate_and_graph_records_seam(self):
        a, b = plane(x=(0, 3), z=4), plane(x=(3, 6), z=5)
        components, labels, graph = segment_source(np.vstack((a, b)), [0, 0, 1])
        self.assertEqual(len(components), 2)
        self.assertNotEqual(int(np.median(labels[:len(a)])), int(np.median(labels[len(a):])))
        self.assertTrue(any(e["relation"] == "CREASE_OR_STEP" for e in graph["edges"]))
        self.assertTrue(all(not e["label_propagation"] for e in graph["edges"]))

    def test_disconnected_coplanar_roofs_do_not_merge(self):
        a, b = plane(x=(0, 3)), plane(x=(7, 10))
        components, labels, graph = segment_source(np.vstack((a, b)), [0, 0, 1])
        self.assertEqual(len(components), 2)
        self.assertFalse(graph["edges"])
        self.assertGreater(np.mean(labels >= 0), 0.95)

    def test_ridge_preserves_two_slopes(self):
        a = plane(x=(-5, 0), z=6, slope=0.5)
        b = plane(x=(0.15, 5), z=6, slope=-0.5)
        components, labels, graph = segment_source(np.vstack((a, b)), [0, 0, 1])
        large = [c for c in components if c["native_count"] > 300]
        self.assertEqual(len(large), 2)
        self.assertLess(np.dot(large[0]["normal"], large[1]["normal"]), 0.8)
        self.assertGreater(np.mean(labels >= 0), 0.85)
        self.assertGreater(len(graph["edges"]), 0)

    def test_native_rows_duplicates_and_unsupported_are_accounted(self):
        surface = plane()
        points = np.vstack((surface, surface[20:35], [[30, 30, 30], [np.nan, 0, 0]]))
        components, labels, graph = segment_source(points, [0, 0, 1])
        self.assertEqual(len(labels), len(points))
        self.assertEqual(labels[-1], -1)
        self.assertEqual(labels[-2], -1)
        self.assertTrue(np.all(labels[len(surface):len(surface) + 15] == labels[20:35]))
        self.assertEqual(sum(c["native_count"] for c in components), int(np.sum(labels >= 0)))
        self.assertEqual(sum(graph["summary"]["unassigned_native_reason_counts"].values()), int(np.sum(labels < 0)))
        json.dumps(graph, allow_nan=False)
        json.dumps(components, allow_nan=False)

    def test_translation_and_determinism(self):
        points = np.vstack((plane(x=(0, 3), slope=.25), plane(x=(4, 7), z=7)))
        c1, m1, g1 = segment_source(points, [0, 0, 1])
        c2, m2, g2 = segment_source(points.copy(), [0, 0, 1])
        c3, m3, _ = segment_source(points + [691000, 5335000, 550], [0, 0, 1])
        np.testing.assert_array_equal(m1, m2)
        np.testing.assert_array_equal(m1, m3)
        self.assertEqual(c1, c2)
        self.assertEqual(g1, g2)
        np.testing.assert_allclose(np.array([c["center"] for c in c3]) - [691000, 5335000, 550],
                                   [c["center"] for c in c1], atol=1e-7)

    def test_supplied_gravity_and_invalid_input(self):
        points = plane(slope=.2)
        theta = .3
        rotation = np.array([[1, 0, 0], [0, np.cos(theta), -np.sin(theta)],
                             [0, np.sin(theta), np.cos(theta)]])
        components, labels, _ = segment_source(points @ rotation.T, rotation @ [0, 0, 1])
        self.assertEqual(len(components), 1)
        self.assertGreater(np.mean(labels >= 0), .9)
        self.assertAlmostEqual(components[0]["tilt_from_up_deg"], np.rad2deg(np.arctan(.2)), places=7)
        for bad in ([0, 0, 0], [0, 0, float("nan")], [1, 2]):
            with self.assertRaises(ValueError):
                segment_source(points, bad)
        with self.assertRaises(ValueError):
            segment_source(points, [0, 0, 1], {"unknown": 1})

    def test_empty_and_line_are_explicitly_unassigned(self):
        for points in (np.empty((0, 3)), np.column_stack((np.arange(30) * .15, np.zeros(30), np.ones(30)))):
            components, labels, graph = segment_source(points, [0, 0, 1])
            self.assertFalse(components)
            self.assertTrue(np.all(labels == -1))
            self.assertEqual(graph["summary"]["unassigned_native_count"], len(points))


if __name__ == "__main__":
    unittest.main()

"""Topology/area fixtures; no source scene, GT, or GPU access."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

PATH = Path(__file__).resolve().parents[3] / 'scripts/phd/geogs_mvs_pgsr_v1/matched_components.py'
SPEC = importlib.util.spec_from_file_location('matched_components', PATH)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
BOX = {'min': [0, 0, -1], 'max': [1, 1, 1]}


class ComponentsTest(unittest.TestCase):
    def test_frozen_plan_xyz_interval_schema(self):
        vertices = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float)
        faces = np.array([[0, 1, 2], [0, 2, 3]])
        actual = m.measure(vertices, faces, {'x': [0, 1], 'y': [0, 1], 'z': [-1, 1]})
        self.assertEqual(actual, m.measure(vertices, faces, BOX))

    def test_square_shared_native_diagonal_is_one_component(self):
        vertices = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float)
        result = m.measure(vertices, np.array([[0, 1, 2], [0, 2, 3]]), BOX)
        self.assertEqual(result['component_count'], 1)
        self.assertAlmostEqual(result['surface_area_m2'], 1.)
        self.assertEqual(result['largest_area_component_share'], 1.)

    def test_coordinate_duplicates_do_not_weld(self):
        vertices = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0],
                             [0, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float)
        result = m.measure(vertices, np.array([[0, 1, 2], [3, 4, 5]]), BOX)
        self.assertEqual(result['component_count'], 2)
        self.assertAlmostEqual(result['largest_area_component_share'], .5)

    def test_clipped_triangle_area_is_not_whole_native_area(self):
        vertices = np.array([[-1, 0, 0], [1, 0, 0], [1, 2, 0]], dtype=float)
        result = m.measure(vertices, np.array([[0, 1, 2]]), BOX)
        self.assertAlmostEqual(result['surface_area_m2'], 1.)
        self.assertEqual(result['clipped_boundary_face_count'], 1)

    def test_shared_edge_outside_roi_does_not_connect(self):
        vertices = np.array([[-1, 0, 0], [-1, 1, 0], [1, .2, 0], [1, .8, .5]], dtype=float)
        result = m.measure(vertices, np.array([[0, 1, 2], [0, 1, 3]]), BOX)
        self.assertEqual(result['positive_area_native_faces_in_roi'], 2)
        self.assertEqual(result['component_count'], 2)

    def test_shared_edge_crossing_roi_connects(self):
        vertices = np.array([[-1, .5, 0], [2, .5, 0], [.5, 0, 0], [.5, 1, 0]], dtype=float)
        result = m.measure(vertices, np.array([[0, 1, 2], [0, 1, 3]]), BOX)
        self.assertEqual(result['component_count'], 1)
        self.assertEqual(result['clipped_boundary_face_count'], 2)

    def test_nonmanifold_edge_connects_all_incident_faces(self):
        vertices = np.array([[0, .5, 0], [1, .5, 0], [.5, 0, 0], [.5, 1, 0], [.5, .5, .5]], dtype=float)
        result = m.measure(vertices, np.array([[0, 1, 2], [0, 1, 3], [0, 1, 4]]), BOX)
        self.assertEqual(result['component_count'], 1)
        self.assertAlmostEqual(result['surface_area_m2'], .75)

    def test_point_contact_edge_does_not_connect(self):
        box = np.array([BOX['min'], BOX['max']], dtype=float)
        self.assertFalse(m.positive_clipped_edges(np.array([[-1, -1, 0.]]), np.array([[0, 0, 0.]]), box)[0])

    def test_empty_crop_has_null_share(self):
        vertices = np.array([[-2, 0, 0], [-1, 0, 0], [-1, 1, 0]], dtype=float)
        result = m.measure(vertices, np.array([[0, 1, 2]]), BOX)
        self.assertEqual(result['component_count'], 0)
        self.assertIsNone(result['largest_area_component_share'])
        self.assertEqual(result['surface_area_m2'], 0.)


if __name__ == '__main__':
    unittest.main()

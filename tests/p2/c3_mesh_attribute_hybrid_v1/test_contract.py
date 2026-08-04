from __future__ import annotations

import unittest

import numpy as np
import open3d as o3d
from shapely.geometry import Polygon

from scripts.p2.c3_mesh_attribute_hybrid_v1.contract import load_config, validate_config
from scripts.p2.c3_mesh_attribute_hybrid_v1.render import _hybrid_mesh, _resample_ring


class MeshAttributeHybridTest(unittest.TestCase):
    def test_config(self) -> None:
        result = validate_config(load_config())
        self.assertEqual(result["hybrid_count"], 12)
        self.assertIsNone(result["scientific_verdict"])

    def test_ring_resampling(self) -> None:
        ring = np.asarray([[0, 0], [4, 0], [4, 2], [0, 2], [0, 0]], dtype=float)
        sampled = _resample_ring(ring, 1.0)
        self.assertEqual(len(sampled), 12)
        self.assertFalse(np.allclose(sampled[0], sampled[-1]))

    def test_hybrid_labels_and_faces(self) -> None:
        mesh = o3d.geometry.TriangleMesh()
        mesh.vertices = o3d.utility.Vector3dVector(np.asarray([[0, 0, 5], [4, 0, 5], [4, 2, 5], [0, 2, 5]], dtype=float))
        mesh.triangles = o3d.utility.Vector3iVector(np.asarray([[0, 1, 2], [0, 2, 3]], dtype=np.int32))
        mesh.vertex_colors = o3d.utility.Vector3dVector(np.full((4, 3), 0.7))
        mesh.compute_vertex_normals()
        hybrid, labels, receipt = _hybrid_mesh(mesh, Polygon([(0, 0), (4, 0), (4, 2), (0, 2)]), 0.0, 1.0, 2, 2.0)
        self.assertGreater(len(hybrid.vertices), len(mesh.vertices))
        self.assertGreater(len(hybrid.triangles), len(mesh.triangles))
        self.assertIn(2, set(labels.tolist()))
        self.assertIn(3, set(labels.tolist()))
        self.assertGreater(receipt["wall_face_count"], 0)
        self.assertFalse(receipt["watertight_claim"])


if __name__ == "__main__":
    unittest.main()

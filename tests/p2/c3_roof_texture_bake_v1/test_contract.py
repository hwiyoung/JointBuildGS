from __future__ import annotations

import unittest
import numpy as np
import open3d as o3d
from shapely.geometry import Polygon
from scripts.p2.c3_roof_texture_bake_v1.contract import load_config, validate_config
from scripts.p2.c3_roof_texture_bake_v1.bake import _bilinear, _display_wall_hybrid, _top_surface, _top_triangle_mesh, _uv


class RoofTextureBakeTest(unittest.TestCase):
    def test_config(self) -> None:
        self.assertEqual(validate_config(load_config())["texture_bake_count"], 12)

    def test_uv(self) -> None:
        value=_uv(np.asarray([[0,0,1],[10,20,1]],float),(0,0,10,20))
        np.testing.assert_allclose(value,[[0,0],[1,1]])

    def test_bilinear(self) -> None:
        image=np.asarray([[[0.,0.,0.],[1.,0.,0.]],[[0.,1.,0.],[1.,1.,0.]]])
        np.testing.assert_allclose(_bilinear(image,np.asarray([[0.5,0.5]])),[[0.5,0.5,0.]])

    def test_top_surface_excludes_vertical_wall(self) -> None:
        vertices=np.asarray([[0,0,1],[1,0,1],[1,1,1],[0,1,1],[0,0,0],[1,0,0]],float)
        triangles=np.asarray([[0,1,2],[0,2,3],[4,5,1],[4,1,0]],int)
        mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices),o3d.utility.Vector3iVector(triangles))
        _,_,_,primitive_ids=_top_surface(mesh,(0,0,1,1),16)
        roof=_top_triangle_mesh(mesh,primitive_ids)
        self.assertEqual(len(np.asarray(roof.triangles)),2)
        self.assertTrue(np.allclose(np.asarray(roof.vertices)[:,2],1.0))

    def test_display_wall_is_separate_and_untextured(self) -> None:
        vertices=np.asarray([[0,0,5],[2,0,5],[2,2,5],[0,2,5]],float); triangles=np.asarray([[0,1,2],[0,2,3]],int)
        roof=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices),o3d.utility.Vector3iVector(triangles))
        hybrid,roof_faces,receipt=_display_wall_hybrid(roof,Polygon([(0,0),(2,0),(2,2),(0,2)]),0.0,1.0,2,2.0)
        self.assertEqual(roof_faces,2)
        self.assertGreater(receipt["wall_face_count"],0)
        self.assertFalse(receipt["wall_texture_created"])
        self.assertFalse(receipt["ground_cap_created"])
        self.assertFalse(receipt["honest_stage3_output"])


if __name__ == "__main__": unittest.main()

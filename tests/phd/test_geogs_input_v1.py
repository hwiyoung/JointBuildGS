"""Input-boundary checks for the official GeoGS ALS experiment adapter."""
import tempfile
from pathlib import Path
import unittest

import numpy as np

from scripts.phd.geogs_p1p2p3_v1.input.prepare import (
    partition_views, qvec_rotation, read_pose_metadata, write_colmap,
)


class GeoGSInputBoundaryTests(unittest.TestCase):
    def test_regional_holdout_never_enters_da3(self):
        for count, expected in ((113, (98, 15)), (66, (57, 9)), (157, (137, 20))):
            views = [{"name": f"image_{i:04d}.JPG", "image_id": i} for i in reversed(range(count))]
            ordered, train, evaluation, batches = partition_views(views, 8, 8)
            self.assertEqual((len(train), len(evaluation)), expected)
            self.assertEqual([v["image_id"] for v in ordered], list(range(count)))
            train_ids = {v["image_id"] for v in train}
            eval_ids = {v["image_id"] for v in evaluation}
            inferred = [v["image_id"] for batch in batches for v in batch]
            self.assertEqual(set(inferred), train_ids)
            self.assertEqual(len(inferred), len(train_ids))
            self.assertFalse(set(inferred) & eval_ids)
            self.assertTrue(all(2 <= len(batch) <= 8 for batch in batches))

    def test_camera_binary_roundtrip_preserves_pose_doubles(self):
        q = (np.sqrt(.5), 0., 0., np.sqrt(.5))
        camera = {3: dict(id=3, model=1, width=1400, height=1013,
                          params=(922.0550838163813, 922.470063461439, 702.6193018201524, 499.79701601553825))}
        image = dict(id=90, qvec=q, tvec=(0.12345678912345678, -9.75, 125.125),
                     camera_id=3, name="heldout.JPG")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_colmap(root / "sparse", camera, [image], empty_points=True)
            actual_cam, actual_img = read_pose_metadata(root)
        self.assertEqual(actual_cam, camera)
        self.assertEqual(actual_img[90], image)
        np.testing.assert_allclose(qvec_rotation(actual_img[90]["qvec"]) @ [2., 0., 0.], [0., 2., 0.], atol=1e-14)

    def test_pinhole_raycast_depth_is_camera_z(self):
        # Off-axis rays make a Euclidean-range/z-depth mixup observable.
        import open3d as o3d
        K = np.array([[2., 0., 1.5], [0., 2., 1.5], [0., 0., 1.]])
        rays = o3d.t.geometry.RaycastingScene.create_rays_pinhole(
            intrinsic_matrix=K, extrinsic_matrix=np.eye(4), width_px=3, height_px=3)
        mesh = o3d.geometry.TriangleMesh()
        mesh.vertices = o3d.utility.Vector3dVector([[-20., -20., 5.], [20., -20., 5.],
                                                   [20., 20., 5.], [-20., 20., 5.]])
        mesh.triangles = o3d.utility.Vector3iVector([[0, 1, 2], [0, 2, 3]])
        scene = o3d.t.geometry.RaycastingScene()
        scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
        depths = scene.cast_rays(rays)["t_hit"].numpy()
        np.testing.assert_allclose(depths, 5., atol=1e-5)
        self.assertGreater(np.linalg.norm(rays.numpy()[0, 0, 3:]) * depths[0, 0], 5.)


if __name__ == "__main__":
    unittest.main()

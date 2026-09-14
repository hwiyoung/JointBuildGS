"""Numerical controls for the bounded GeoGS inference intervention."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np

SPEC = importlib.util.spec_from_file_location('gaussian_probe', Path(__file__).resolve().parents[2]/'scripts/phd/mvs_surface_update_v1/gaussian_probe.py')
m = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)


def camera(t=(0, 0, 0)):
    return dict(width=100, height=100, K=[[100, 0, 50], [0, 100, 50], [0, 0, 1]], R=np.eye(3).tolist(), t=list(t))


class BoundedProbeTests(unittest.TestCase):
    def test_plane_step_is_signed_bounded_and_tangentially_unchanged(self):
        xyz = np.array([[1., 2., 0.], [4., 5., 2.], [6., 7., .97]])
        delta, distance = m.bounded_plane_displacement(xyz, [0, 0, 1], [0, 0, -5], .1)
        np.testing.assert_allclose(delta, [[0, 0, .1], [0, 0, -.1], [0, 0, .03]])
        self.assertLessEqual(np.linalg.norm(delta, axis=1).max(), .1)
        with self.assertRaises(ValueError): m.bounded_plane_displacement(xyz, [0, 0, 1], [0, 0, 0], .1)

    def test_fixed_mask_includes_both_source_projection_hypotheses(self):
        ref = camera(); nb = camera((1, 0, 0))
        case = dict(reference_camera=ref, bbox=[47, 47, 54, 54], uv=[50, 50], prior_depth=5., mvs_depth=10., prior_xyz_world=[0, 0, 5])
        masks = m.frozen_masks(nb, case, False, 5)
        self.assertTrue(masks['target'][50, 70])
        self.assertTrue(masks['target'][50, 60])
        self.assertFalse(masks['target'][50, 50])
        self.assertTrue(np.all(sum(value.astype(int) for value in masks.values()) == 1))
        self.assertEqual(m.frozen_masks(ref, case, True)['target'].sum(), 49)

    def test_photo_denominator_does_not_shrink_after_alpha_loss(self):
        photo = np.ones((2, 2, 3), np.float32)
        before = dict(rgb=photo.copy(), depth=np.ones((2, 2)), alpha=np.ones((2, 2)), normal=np.broadcast_to([0., 0., 1.], (2, 2, 3)).copy())
        after = {k: v.copy() for k, v in before.items()}
        after['rgb'][0, 0] = 0; after['alpha'][0, 0] = 0; after['depth'][0, 0] = 0
        result = m.paired_metrics(photo, before, after, np.ones((2, 2), bool))
        self.assertEqual(result['pixels'], 4)
        self.assertEqual(result['photo_mae_after'], .25)
        self.assertEqual(result['alpha_coverage_lost_pixels'], 1)
        self.assertEqual(result['depth_paired_alpha05_pixels'], 3)

    def test_raw_patch_projection_overrides_constant_depth_corners(self):
        ref = camera(); nb = camera((1, 0, 0))
        case = dict(reference_camera=ref, bbox=[47, 47, 54, 54], uv=[50, 50], prior_depth=5., mvs_depth=10., prior_xyz_world=[0, 0, 5])
        case['prior_patch_world'] = [m.ray_world(ref, [x, y], 5).tolist() for y in range(47, 54) for x in range(47, 54)]
        case['mvs_patch_world'] = [m.ray_world(ref, [x, y], 10).tolist() for y in range(47, 54) for x in range(77, 84)]
        masks = m.frozen_masks(nb, case)
        self.assertTrue(masks['target'][50, 90])
        self.assertFalse(masks['target'][50, 60])
        self.assertTrue(np.all(sum(value.astype(int) for value in masks.values()) == 1))

    def test_ray_projection_roundtrip_and_shifted_world(self):
        c = camera((1, 2, 3)); uv = [17., 29.]
        xyz = m.ray_world(c, uv, 12.)
        actual, depth = m.project(c, xyz[None])
        np.testing.assert_allclose(actual[0], uv)
        self.assertEqual(depth[0], 12.)


if __name__ == '__main__': unittest.main()

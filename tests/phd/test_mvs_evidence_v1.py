"""Analytic geometry and adversarial support tests for diagnostic-only evidence."""
import unittest

import numpy as np

from src.phd.mvs_evidence_v1 import (project, bilinear, sample_mvs, sample_prior, visibility,
                                    batched_patch_cost, pair_patch_cost, _patch_geometry)


def camera(center=(0., 0., 0.), R=None, width=101, height=81):
    R = np.eye(3) if R is None else np.asarray(R, float)
    K = np.array([[60., 0., 50.], [0., 60., 40.], [0., 0., 1.]])
    return dict(K=K, R=R, t=-R @ np.asarray(center), width=width, height=height,
                maps={'depth': {'K': K.copy()}})


def texture():
    y, x = np.mgrid[:81, :101]
    a = .5 + .18*np.sin(x*.29+y*.09) + .13*np.cos(y*.33-x*.12)
    return np.repeat(a[..., None], 3, axis=-1)


class EvidenceTests(unittest.TestCase):
    def test_camera_z_translation_and_rotated_world_to_camera(self):
        ref, nb = camera(), camera((1., 0., 0.))
        uv = np.array([[50., 40.], [62., 46.]])
        xy, z, world = project(uv, np.full(2, 10.), ref, nb)
        np.testing.assert_allclose(xy, uv-[6., 0.], atol=1e-12)
        np.testing.assert_allclose(world, [[0., 0., 10.], [2., 1., 10.]], atol=1e-12)
        np.testing.assert_allclose(z, 10.)
        angle = np.deg2rad(20)
        R = np.array([[np.cos(angle), 0, np.sin(angle)], [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]])
        rot = camera(R=R)
        xy, z, _ = project(uv[:1], np.array([10.]), ref, rot)
        self.assertAlmostEqual(xy[0, 0], 50+60*np.tan(angle))
        self.assertAlmostEqual(z[0], 10*np.cos(angle))

    def test_sampling_odd_intrinsics_holes_and_half_pixel(self):
        raw = np.arange(15, dtype=float).reshape(3, 5)+10
        raw[1, 2] = 0
        view = camera(width=7, height=5)
        Kn = np.array([[5., 0, 2.], [0, 3., 1.], [0, 0, 1.]])
        view['K'] = np.diag([7/5, 5/3, 1.]) @ Kn
        view['maps']['depth']['K'] = Kn
        uv = np.array([[0, 0], [3, 2], [6, 4], [np.nan, 0]])
        d, valid = sample_mvs(raw, uv, view)
        self.assertTrue(valid[0]); self.assertEqual(d[0], 10)
        self.assertFalse(valid[1]); self.assertTrue(np.isnan(d[1]))
        self.assertTrue(valid[2]); self.assertEqual(d[2], raw[2, 4]); self.assertFalse(valid[3])
        ramp = np.arange(16., dtype=float).reshape(4, 4)+1
        d, valid = sample_prior(ramp, np.array([[1.5, 1.5], [.25, .25]]))
        self.assertEqual(d[0], 6.); self.assertFalse(valid[1]); self.assertTrue(np.isnan(d[1]))
        ramp[2, 2] = 0
        d, valid = sample_prior(ramp, np.array([[1.5, 1.5]]))
        self.assertFalse(valid[0]); self.assertTrue(np.isnan(d[0]))

    def test_bilinear_out_of_bounds_nan_and_scalar_fixture(self):
        a = np.arange(16.).reshape(4, 4)
        q, mask = bilinear(a, np.array([[1.25, 1.5], [-1., 0], [1e30, 0.], [np.nan, 0.]]))
        self.assertEqual(q[0], 7.25)
        np.testing.assert_array_equal(mask, [True, False, False, False])
        self.assertTrue(np.isnan(q[1:]).all())

    def test_model_depth_ordering_holes_roundtrip_and_parallax(self):
        ref, nb = camera(), camera((1., 0., 0.))
        uv = np.array([[50., 40.]]*6)
        depths = np.array([10., 12., 8., 0., 10., 10.])
        uv[4] = [10000, 40]; uv[5] = [50, 10]
        model = np.full((81, 101), 10.)
        model[10, 44] = np.nan
        result = visibility(uv, depths, ref, nb, model, .5)
        np.testing.assert_array_equal(result['status'], [3, 4, 5, 0, 1, 2])
        np.testing.assert_allclose(result['z_residual'][:3], [0., 2., -2.])
        self.assertAlmostEqual(result['roundtrip_px'][0], 0., places=12)
        self.assertAlmostEqual(result['roundtrip_px'][1], 1., places=12)
        self.assertAlmostEqual(result['parallax_deg'][0], np.degrees(np.arctan(.1)))
        self.assertEqual(result['conditioning'], 'MVS_MODEL_CONDITIONED')
        prior = visibility(uv[:1], depths[:1], ref, nb, np.full((81, 101), 10.), .5, neighbor_kind='prior')
        self.assertEqual(prior['conditioning'], 'PRIOR_MODEL_CONDITIONED')
        self.assertEqual(prior['status'][0], 3)

    def test_pure_rotation_roundtrip_cannot_certify_depth(self):
        ref = camera()
        a = np.deg2rad(10)
        nb = camera(R=[[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        result = visibility(np.array([[50., 40.]]), np.array([10.]), ref, nb,
                            np.full((81, 101), 20.), .5)
        self.assertEqual(result['status'][0], 5)
        self.assertLess(result['roundtrip_px'][0], 1e-10)
        self.assertLess(result['parallax_deg'][0], 1e-5)

    def test_off_axis_normal_plane_keeps_center_and_missing_source(self):
        ref = camera(); centers = np.array([[62., 46.], [50., 40.]])
        depths = np.array([10., np.nan]); normal = np.array([[.2, .1, 1.], [0., 0., 1.]])
        uv, d = _patch_geometry(centers, depths, ref, 2, normal=normal)
        self.assertAlmostEqual(d[0, 12], 10.)
        rays = np.concatenate((uv[0], np.ones((25, 1))), -1) @ np.linalg.inv(ref['K']).T
        expected_offset = np.array([2., 1., 10.]) @ normal[0]
        np.testing.assert_allclose((rays*d[0, :, None]) @ normal[0], expected_offset, atol=1e-12)
        self.assertTrue(np.isnan(d[1]).all())

    def test_photo_cost_known_plane_affine_brightness_and_source_swap(self):
        ref, nb = camera(), camera((1., 0., 0.))
        rgb = texture()
        # At Z=10 the neighbor sees reference texture at x+6; create it exactly.
        near = np.full_like(rgb, np.nan); near[:, :-6] = rgb[:, 6:]*.7+.1
        centers = np.array([[50., 40.], [60., 50.]])
        p, m = np.full(2, 10.), np.full(2, 20.)
        result = pair_patch_cost(centers, p, m, ref, nb, rgb, near, 3, texture_std=.01)
        self.assertTrue(result['eligible'].all())
        np.testing.assert_allclose(result['costs'][:, 0], 0., atol=1e-12)
        self.assertTrue((result['costs'][:, 1] > .005).all())
        swap = pair_patch_cost(centers, m, p, ref, nb, rgb, near, 3, texture_std=.01)
        np.testing.assert_allclose(result['costs'], swap['costs'][:, ::-1])
        np.testing.assert_array_equal(result['common_mask'], swap['common_mask'])

    def test_pair_support_excludes_missing_pixels_for_both_sources(self):
        ref = camera(); rgb = texture(); centers = np.array([[50., 40.]])
        ppatch = np.full((1, 25), 10.); mpatch = np.full((1, 25), 10.)
        ppatch[0, :3] = np.nan
        result = pair_patch_cost(centers, [10.], [10.], ref, ref, rgb, rgb, 2,
                                 prior_patch_depth=ppatch, mvs_patch_depth=mpatch)
        self.assertEqual(result['common_count'][0], 22)
        np.testing.assert_allclose(result['costs'], 0., atol=1e-12)
        ppatch[0, :10] = np.nan
        result = pair_patch_cost(centers, [10.], [10.], ref, ref, rgb, rgb, 2,
                                 prior_patch_depth=ppatch, mvs_patch_depth=mpatch)
        self.assertFalse(result['eligible'][0]); self.assertTrue(np.isnan(result['costs']).all())
        self.assertTrue(np.isfinite(result['raw_costs']).all())
        with self.assertRaises(ValueError):
            pair_patch_cost(centers, [11.], [10.], ref, ref, rgb, rgb, 2,
                            prior_patch_depth=np.full((1, 25), 10.))

    def test_flat_empty_negative_and_behind_camera_are_not_zero_cost(self):
        ref = camera(); flat = np.full((81, 101, 3), .5)
        centers = np.array([[50., 40.], [50., 40.], [50., 40.]])
        result = pair_patch_cost(centers, [10., np.nan, -1.], [10., 10., 10.], ref, ref, flat, flat, 2)
        self.assertFalse(result['eligible'].any()); self.assertTrue(np.isnan(result['costs']).all())
        np.testing.assert_array_equal(result['common_count'], [25, 0, 0])
        nb = camera((0., 0., 20.))
        cost, _, fraction = batched_patch_cost(centers[:1], [10.], ref, nb, texture(), texture(), 2)
        self.assertTrue(np.isnan(cost[0])); self.assertEqual(fraction[0], 0.)


if __name__ == '__main__':
    unittest.main()

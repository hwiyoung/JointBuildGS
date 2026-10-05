"""Synthetic camera/plane tests independent of scene evaluation references."""
from __future__ import annotations

import unittest

import numpy as np

from src.phd.source_candidate_v1.photometry import (
    ScoringConfig, _cost, _disjoint_count, _sample_gray, _visibility, project, score_candidates,
)


def plane(z=10., xmin=-5., xmax=5.):
    x, y = np.meshgrid(np.linspace(xmin, xmax, 51), np.linspace(-5, 5, 51))
    return {"center": np.array([(xmin + xmax) / 2, 0., z]),
            "normal": np.array([0., 0., 1.]), "valid": True,
            "support_points": np.column_stack((x.ravel(), y.ravel(), np.full(x.size, z))),
            "support_tolerance_m": 0.22}


def synthetic_views(flat=False, center_offset=0.):
    width, height, focal = 192, 192, 130.
    K = np.array([[focal, 0., 96. + center_offset], [0., focal, 96. + center_offset], [0., 0., 1.]])
    u, v = np.meshgrid(np.arange(width) + center_offset, np.arange(height) + center_offset)
    views = []
    for index, (cx, cy) in enumerate([(-2., -1.), (2., -1.), (-2., 1.), (2., 1.)]):
        x = cx + (u - K[0, 2]) * 10 / focal
        y = cy + (v - K[1, 2]) * 10 / focal
        gray = (125 + 38 * np.sin(3.7*x + 1.3*y) + 32*np.cos(4.1*y - .8*x)
                + 25*np.sin(6.1*x - 3.3*y))
        if flat:
            gray[:] = 100
        center = np.array([cx, cy, 0.])
        views.append({"id": index, "center": center, "R": np.eye(3), "t": -center,
                      "K": K.copy(), "width": width, "height": height,
                      "gray": gray.astype(np.float32)})
    return views


class SourceCandidatePhotometryTest(unittest.TestCase):
    def setUp(self):
        self.cfg = {"max_views": 4, "max_pairs": 6, "max_patch_centers": 9,
                    "minimum_patch_std": 2.0, "profile_offsets_m": (-2., -1., -.5, 0., .5, 1., 2.)}

    def test_true_plane_wins_and_wrong_plane_profile_recovers_true_depth(self):
        result = score_candidates({"mvs": plane(10), "als": plane(12)}, synthetic_views(), self.cfg)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["shared"]["distinct_view_count"], 4)
        self.assertEqual(result["shared"]["disjoint_pair_count"], 2)
        self.assertLess(result["candidates"]["mvs"]["cost"], .002)
        self.assertGreater(result["candidates"]["als"]["cost"], .12)
        self.assertLess(result["contrast"]["cost_mvs_minus_als"], -.12)
        self.assertEqual(result["candidates"]["als"]["profile_best_offset_m"], -2.)
        self.assertEqual(result["candidates"]["mvs"]["profile_best_offset_m"], 0.)
        for name in ("mvs", "als"):
            nominal = next(p for p in result["candidates"][name]["profile"] if p["offset_m"] == 0)
            self.assertEqual(nominal["paired_delta_cost"], 0.)
            self.assertEqual(nominal["paired_nominal_cost"], nominal["cost"])
        wrong_recovered = next(p for p in result["candidates"]["als"]["profile"] if p["offset_m"] == -2)
        self.assertLess(wrong_recovered["paired_delta_cost"], -.12)
        for a, b in zip(result["candidates"]["als"]["pairs"], result["candidates"]["mvs"]["pairs"]):
            self.assertEqual(a["pair_id"], b["pair_id"])
            self.assertEqual(a["reference_pixel_centers"], b["reference_pixel_centers"])
            self.assertEqual(a["common_patch_count"], b["common_patch_count"])

    def test_source_renaming_does_not_change_measurements_or_sampling(self):
        a = score_candidates({"mvs": plane(10), "als": plane(12)}, synthetic_views(), self.cfg)
        b = score_candidates({"mvs": plane(12), "als": plane(10)}, synthetic_views(), self.cfg)
        self.assertEqual(a["shared"], b["shared"])
        self.assertAlmostEqual(a["candidates"]["mvs"]["cost"], b["candidates"]["als"]["cost"], places=10)
        self.assertAlmostEqual(a["contrast"]["cost_mvs_minus_als"], -b["contrast"]["cost_mvs_minus_als"], places=10)

    def test_equal_candidates_and_flat_images_do_not_invent_evidence(self):
        equal = score_candidates({"mvs": plane(), "als": plane()}, synthetic_views(), self.cfg)
        self.assertAlmostEqual(equal["contrast"]["cost_mvs_minus_als"], 0., places=12)
        flat = score_candidates({"mvs": plane(), "als": plane(12)}, synthetic_views(flat=True), self.cfg)
        self.assertEqual(flat["status"], "untextured")
        self.assertIsNone(flat["candidates"]["mvs"]["cost"])
        self.assertIsNone(flat["contrast"]["cost_mvs_minus_als"])

    def test_disjoint_native_support_is_untestable_not_an_infinite_plane_match(self):
        result = score_candidates({"mvs": plane(10, -4, -2), "als": plane(10, 2, 4)},
                                  synthetic_views(), self.cfg)
        self.assertEqual(result["status"], "no_common_support")
        self.assertEqual(result["shared"]["common_patch_count"], 0)
        self.assertIsNone(result["contrast"]["cost_mvs_minus_als"])

    def test_flat_wrong_target_cannot_remove_a_textured_candidate(self):
        reference = np.arange(81, dtype=float)[None]
        mask = np.ones(reference.shape, bool)
        cfg = ScoringConfig()
        good, _, _ = _cost(reference, reference * 1.7 + 4, mask, cfg)
        bad, informative, low = _cost(reference, np.full(reference.shape, 60.), mask, cfg)
        self.assertLess(good[0], 1e-12)
        self.assertEqual(bad[0], cfg.low_target_texture_cost)
        self.assertTrue(informative[0])
        self.assertTrue(low[0])

    def test_native_integer_centers_and_explicit_half_pixel_conversion_agree(self):
        native, half = synthetic_views(), synthetic_views(center_offset=.5)
        xyz = np.array([[0., 0., 10.]])
        uv, z = project(xyz, native[0])
        self.assertAlmostEqual(z[0], 10.)
        np.testing.assert_allclose(uv[0], [122., 109.])
        pixels = np.array([[[122., 109.]]])
        sampled = _sample_gray(pixels, native[0], ScoringConfig())
        self.assertAlmostEqual(sampled[0, 0], native[0]["gray"][109, 122])
        a = score_candidates({"mvs": plane(), "als": plane(12)}, native, self.cfg)
        b = score_candidates({"mvs": plane(), "als": plane(12)}, half,
                             {**self.cfg, "pixel_center_offset": .5})
        self.assertAlmostEqual(a["contrast"]["cost_mvs_minus_als"], b["contrast"]["cost_mvs_minus_als"], places=6)

    def test_missing_depth_is_unknown_and_own_depth_is_not_a_cross_source_veto(self):
        view = synthetic_views()[0]
        uv = np.array([[[20., 20.], [21., 21.], [22., 22.]]])
        z = np.array([[10., 10., 10.]])
        own = np.full((192, 192), np.nan)
        own[20, 20], own[21, 21], own[22, 22] = 10., 5., np.nan
        candidate = {"context_depths": {view["id"]: own}}
        visible, matched = _visibility(uv, z, view, candidate, ScoringConfig())
        self.assertEqual(visible.tolist(), [[True, False, True]])
        self.assertEqual(matched.tolist(), [[True, False, False]])
        other_visible, other_matched = _visibility(uv, z, view, {}, ScoringConfig())
        self.assertTrue(other_visible.all())
        self.assertFalse(other_matched.any())
        result = score_candidates({"mvs": plane(), "als": plane(12)}, synthetic_views(), self.cfg)
        self.assertEqual(result["shared"]["common_visibility_verified_fraction"], 0.)
        self.assertEqual(result["shared"]["visibility_semantics"], "MODEL_SELF_VISIBILITY")

    def test_shifted_controls_are_not_vetoed_by_nominal_source_depth(self):
        views = synthetic_views()
        a, b = plane(10), plane(12)
        a["context_depths"] = {v["id"]: np.full((192, 192), 10.) for v in views}
        b["context_depths"] = {v["id"]: np.full((192, 192), 12.) for v in views}
        result = score_candidates({"mvs": a, "als": b}, views, self.cfg)
        self.assertEqual(result["shared"]["common_visibility_verified_fraction"], 1.)
        plus2 = next(p for p in result["candidates"]["mvs"]["profile"] if p["offset_m"] == 2.)
        self.assertIsNotNone(plus2["cost"])
        self.assertGreater(plus2["common_patch_count"], 0)

    def test_disjoint_camera_count_cannot_be_replaced_by_pair_count(self):
        self.assertEqual(_disjoint_count([("a", "b"), ("a", "c"), ("a", "d")]), 1)
        self.assertEqual(_disjoint_count([("a", "b"), ("a", "c"), ("b", "d")]), 2)
        result = score_candidates({"mvs": plane(), "als": plane(12)}, synthetic_views()[:3], self.cfg)
        self.assertEqual(result["status"], "insufficient_views")
        self.assertEqual(result["shared"]["disjoint_pair_count"], 1)


if __name__ == "__main__":
    unittest.main()

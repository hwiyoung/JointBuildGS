"""Synthetic camera/visibility invariants for manual diagnostic label transfer.

These tests establish geometry and mask behavior, not scene-label accuracy or
calibration of the diagnostic depth/reprojection tolerances.
"""
import copy
import itertools
import unittest

import numpy as np

from src.phd.manual_region_masks_v1 import (
    boundary_band,
    correspondence,
    make_regions,
    polygon_mask,
    project,
    resample_nearest,
    unproject,
)


class ManualRegionGeometryTests(unittest.TestCase):
    def test_nearest_preserves_boolean_dtype_with_integer_default_fill(self):
        mask = np.array([[True, False], [False, True]])
        sampled = resample_nearest(mask, np.eye(3), np.eye(3), 3, 3, outside=0)
        self.assertEqual(sampled.dtype, np.dtype(bool))
        self.assertEqual((~sampled).dtype, np.dtype(bool))
        self.assertFalse(sampled[2, 2])
        labels = resample_nearest(np.array([[1,2],[3,4]], dtype=np.uint8), np.eye(3), np.eye(3), 3, 3, outside=5)
        self.assertEqual(labels.dtype, np.dtype(np.uint8))
        self.assertEqual(labels[2, 2], 5)

    def setUp(self):
        self.shape = (9, 11)
        self.depth = np.full(self.shape, 10.0)
        self.K = np.array([[10., 0., 5.], [0., 10., 4.], [0., 0., 1.]])
        self.view = self.camera("target")
        self.cfg = {
            "training_context": {"x": [-100., 100.], "y": [-100., 100.], "z": [0., 100.]},
            "depth_match_m": .5,
            "roundtrip_native_px": 2.,
            "target_boundary_native_px": 0,
            "depth_edge_native_px": 0,
            "depth_edge_m": 1.,
            "display_alpha": 4.,
        }

    def camera(self, name, t=None):
        return {"name": name, "maps": {"depth": {"K": self.K.copy()}},
                "R": np.eye(3), "t": np.zeros(3) if t is None else np.asarray(t, dtype=float)}

    def source(self, name="source", label=3, depth=None, view=None, candidate=None):
        view = self.camera(name) if view is None else view
        depth = self.depth.copy() if depth is None else np.array(depth, dtype=float, copy=True)
        labels = (np.full(self.shape, label, np.uint8) if np.isscalar(label)
                  else np.array(label, dtype=np.uint8, copy=True))
        return {"view": view, "depth": depth, "labels": labels,
                "xyz": unproject(depth, view["maps"]["depth"]["K"], view["R"], view["t"]),
                "candidate": candidate}

    def match(self, source, depth=None, view=None, roundtrip=2.):
        view = self.view if view is None else view
        depth = self.depth if depth is None else depth
        xyz = unproject(depth, view["maps"]["depth"]["K"], view["R"], view["t"])
        return correspondence(xyz, view, source, .5, roundtrip)

    def test_identity_uses_camera_z_even_for_off_axis_pixels(self):
        source = self.source()
        yy, xx = np.indices(self.shape)
        sy, sx, accepted = self.match(source)
        np.testing.assert_array_equal(sy, yy)
        np.testing.assert_array_equal(sx, xx)
        self.assertTrue(accepted.all())
        self.assertGreater(np.linalg.norm(source["xyz"][0, 0]), self.depth[0, 0])
        uv, z, in_front = project(source["xyz"], self.K, np.eye(3), np.zeros(3))
        np.testing.assert_allclose(uv, np.stack((xx, yy), -1), atol=1e-12)
        np.testing.assert_allclose(z, self.depth)
        self.assertTrue(in_front.all())

    def test_known_baseline_projects_one_pixel_left_and_rejects_outside(self):
        source = self.source(view=self.camera("translated", [-1., 0., 0.]))
        sy, sx, accepted = self.match(source)
        yy, xx = np.indices(self.shape)
        np.testing.assert_array_equal(sy[:, 1:], yy[:, 1:])
        np.testing.assert_array_equal(sx[:, 1:], xx[:, 1:] - 1)
        self.assertTrue(accepted[:, 1:].all())
        self.assertFalse(accepted[:, 0].any())

    def test_depth_agreement_alone_does_not_bypass_roundtrip(self):
        source = self.source(depth=np.full(self.shape, 10.4),
                             view=self.camera("translated", [-2., 0., 0.]))
        self.assertTrue(self.match(source, roundtrip=.1)[2][:, 2:].all())
        self.assertFalse(self.match(source, roundtrip=.05)[2].any())

    def test_occluding_plane_and_points_behind_camera_do_not_transfer(self):
        self.assertFalse(self.match(self.source(depth=np.full(self.shape, 5.)))[2].any())
        behind = self.source(view=self.camera("behind", [0., 0., -20.]))
        self.assertFalse(self.match(behind)[2].any())

    def test_target_and_source_depth_holes_do_not_transfer(self):
        target_depth = self.depth.copy()
        target_depth[2, 2] = np.nan
        target_depth[2, 3] = 0
        source_depth = self.depth.copy()
        source_depth[4, 4] = np.nan
        source_depth[4, 5] = 0
        accepted = self.match(self.source(depth=source_depth), depth=target_depth)[2]
        expected = np.ones(self.shape, bool)
        expected[2, 2:4] = False
        expected[4, 4:6] = False
        np.testing.assert_array_equal(accepted, expected)

    def test_common_world_rigid_transform_preserves_correspondence(self):
        source = self.source(view=self.camera("translated", [-1., 0., 0.]))
        before = self.match(source)
        angle = .37
        q = np.array([[np.cos(angle), 0., np.sin(angle)], [0., 1., 0.],
                      [-np.sin(angle), 0., np.cos(angle)]])
        shift = np.array([173., -42., 9.])

        def transformed(view):
            result = copy.deepcopy(view)
            result["R"] = view["R"] @ q.T
            result["t"] = view["t"] - result["R"] @ shift
            return result

        target_view = transformed(self.view)
        source_after = self.source(view=transformed(source["view"]))
        after = self.match(source_after, view=target_view)
        for expected, actual in zip(before, after):
            np.testing.assert_array_equal(actual, expected)

    def test_source_order_unknown_abstention_and_duplicate_agreement(self):
        known = self.source("known", 3)
        unknown = self.source("unobserved", 5)
        duplicate = self.source("also_known", 3)
        expected = make_regions(self.depth, self.view, [known], self.cfg)
        for sources in itertools.permutations([known, unknown, duplicate]):
            result = make_regions(self.depth, self.view, sources, self.cfg)
            np.testing.assert_array_equal(result["region_id"], expected["region_id"])
            np.testing.assert_array_equal(result["weight"], expected["weight"])
            self.assertFalse(result["cross_view_conflict"].any())

    def test_static_conflict_and_visible_exclusion_veto_are_distinct(self):
        building = self.source("building", 2)
        ground = self.source("ground", 3)
        excluded = self.source("excluded", 4)
        for sources in ([building, ground], [ground, building]):
            conflict = make_regions(self.depth, self.view, sources, self.cfg)
            self.assertTrue((conflict["region_id"] == 5).all())
            self.assertTrue(conflict["cross_view_conflict"].all())
            self.assertFalse(conflict["exclusion_veto"].any())
        for sources in ([ground, excluded], [excluded, ground]):
            veto = make_regions(self.depth, self.view, sources, self.cfg)
            self.assertTrue((veto["region_id"] == 5).all())
            self.assertTrue(veto["exclusion_veto"].all())
            self.assertFalse(veto["cross_view_conflict"].any())
        hidden_exclusion = self.source("hidden_exclusion", 4, depth=np.full(self.shape, 5.))
        hidden = make_regions(self.depth, self.view, [ground, hidden_exclusion], self.cfg)
        self.assertTrue((hidden["region_id"] == 3).all())
        self.assertFalse(hidden["exclusion_veto"].any())

    def test_local_manual_labels_override_other_views_but_keep_conflict_evidence(self):
        local = self.source(view=self.view, label=3)
        other = self.source("other", 2)
        result = make_regions(self.depth, self.view, [local, other], self.cfg)
        self.assertTrue((result["region_id"] == 3).all())
        self.assertTrue(result["cross_view_conflict"].all())
        local["labels"].fill(4)
        excluded = make_regions(self.depth, self.view, [other, local], self.cfg)
        self.assertTrue((excluded["region_id"] == 4).all())
        self.assertFalse(excluded["weight"].any())

    def test_intervention_requires_final_ground_and_visible_candidate_support(self):
        candidate = np.ones(self.shape, bool)
        for label, expected in ((2, 2), (3, 1), (5, 5)):
            source = self.source(label=label, candidate=candidate)
            result = make_regions(self.depth, self.view, [source], self.cfg)
            self.assertTrue((result["region_id"] == expected).all())
            if expected == 1:
                self.assertTrue((result["weight"] == self.cfg["display_alpha"]).all())
        hidden = self.source("candidate", 3, depth=np.full(self.shape, 5.), candidate=candidate)
        result = make_regions(self.depth, self.view, [hidden, self.source("ground", 3)], self.cfg)
        self.assertTrue((result["region_id"] == 3).all())
        self.assertFalse(result["candidate_support"].any())

    def test_building_intervention_requires_explicit_policy_and_cannot_promote_unknown(self):
        cfg = dict(self.cfg, intervention_base_regions=[2])
        for label, expected in ((2, 1), (3, 3), (4, 4), (5, 5)):
            source = self.source(view=self.view, label=label, candidate=np.ones(self.shape, bool))
            result = make_regions(self.depth, self.view, [source], cfg)
            self.assertTrue((result['region_id'] == expected).all())
        with self.assertRaises(ValueError):
            make_regions(self.depth, self.view, [], dict(cfg, intervention_base_regions=[5]))

    def test_complete_partition_distinguishes_missing_depth_and_outside_context(self):
        depth = self.depth.copy()
        depth[4, 5] = np.nan
        cfg = copy.deepcopy(self.cfg)
        cfg["training_context"]["x"] = [-2., 2.]
        result = make_regions(depth, self.view, [self.source()], cfg)
        self.assertEqual(result["region_id"].shape, self.shape)
        self.assertTrue(np.isin(result["region_id"], [1, 2, 3, 4, 5, 6]).all())
        self.assertFalse(result["valid"][4, 5])
        self.assertEqual(result["region_id"][4, 5], 5)
        self.assertTrue((result["region_id"][:, :3] == 6).all())
        self.assertTrue((result["region_id"][:, 8:] == 6).all())
        self.assertTrue(result["valid"][:, :3].all())
        self.assertFalse(result["weight"][~result["valid"]].any())
        self.assertFalse(result["weight"][result["region_id"] == 6].any())

    def test_label_boundary_is_unknown_without_erasing_local_exclusions(self):
        labels = np.full(self.shape, 2, np.uint8)
        labels[:, 6:] = 3
        band = boundary_band(labels, 1)
        self.assertTrue(band[:, 4:8].all())
        self.assertFalse(band[:, :4].any())
        self.assertFalse(band[:, 8:].any())
        cfg = copy.deepcopy(self.cfg)
        cfg["target_boundary_native_px"] = 1
        result = make_regions(self.depth, self.view, [self.source(view=self.view, label=labels)], cfg)
        self.assertTrue((result["region_id"][:, 4:8] == 5).all())
        self.assertTrue((result["region_id"][:, :4] == 2).all())
        self.assertTrue((result["region_id"][:, 8:] == 3).all())
        labels[:, 6:] = 4
        result = make_regions(self.depth, self.view, [self.source(view=self.view, label=labels)], cfg)
        self.assertTrue((result["region_id"][:, 6:] == 4).all())

    def test_native_to_rgb_nearest_shares_indices_and_preserves_holes(self):
        labels = np.array([[2, 3, 4], [5, 6, 1]], dtype=np.uint8)
        valid = np.array([[True, False, True], [False, True, True]])
        target_k = np.diag([2., 2., 1.])
        expected_x = np.array([0, 1, 1, 2, 2])
        expected_y = np.array([0, 1, 1])
        expected_labels = labels[expected_y[:, None], expected_x]
        expected_valid = valid[expected_y[:, None], expected_x]
        np.testing.assert_array_equal(resample_nearest(labels, np.eye(3), target_k, 5, 3), expected_labels)
        np.testing.assert_array_equal(resample_nearest(valid, np.eye(3), target_k, 5, 3), expected_valid)
        paired = np.stack((labels, valid.astype(np.uint8)), -1)
        actual_pair = resample_nearest(paired, np.eye(3), target_k, 5, 3)
        np.testing.assert_array_equal(actual_pair[..., 0], expected_labels)
        np.testing.assert_array_equal(actual_pair[..., 1], expected_valid)
        wider = resample_nearest(labels, np.eye(3), target_k, 7, 3, outside=6)
        self.assertTrue((wider[:, 5:] == 6).all())

    def test_manual_polygon_priority_keeps_unannotated_pixels_unknown(self):
        labels = polygon_mask(11, 9, [
            {"region": 3, "xy": [[1, 1], [9, 1], [9, 7], [1, 7]]},
            {"region": 2, "xy": [[3, 3], [7, 3], [7, 5], [3, 5]]},
            {"region": 4, "xy": [[4, 3], [6, 3], [6, 4], [4, 4]]},
        ])
        self.assertEqual(labels[0, 0], 5)
        self.assertEqual(labels[2, 2], 3)
        self.assertEqual(labels[5, 3], 2)
        self.assertEqual(labels[3, 5], 4)
        self.assertTrue(np.isin(labels, [2, 3, 4, 5]).all())


if __name__ == "__main__":
    unittest.main()

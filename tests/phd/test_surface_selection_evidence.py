"""Meaningful synthetic checks for unit evidence and bounded acceptance scope."""
import unittest

import numpy as np

from src.phd.surface_selection_v1.evidence import DEFAULT_CONFIG, _decide, evaluate_unit, replay_evidence
from tests.phd.test_source_candidate_photometry import plane, synthetic_views


def unit():
    x, y = np.meshgrid(np.arange(-3., 3.01, .5), np.arange(-3., 3.01, .5))
    xy = np.column_stack((x.ravel(), y.ravel()))
    return {"id": 7, "mvs_ids": [12], "als_ids": [20], "area_m2": len(xy)*.25,
            "tile_ids": list(range(1000, 1000+len(xy))), "footprint_xy": xy.tolist()}


class SurfaceSelectionEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.config = {"photometry": {"max_views": 4, "max_pairs": 6}}

    def test_supported_surface_uses_distributed_anchors_and_only_observed_scope(self):
        observation, decision = evaluate_unit(unit(), {"mvs": plane(10), "als": plane(12)},
                                              synthetic_views(), self.config)
        self.assertEqual(observation["source_assessments"]["mvs"]["status"], "SUPPORT")
        self.assertEqual(decision["action"], "IMAGE")
        anchors = np.array([a["xyz"] for a in observation["anchors"]])
        self.assertGreater(np.ptp(anchors[:, 0]), 5.)
        self.assertGreater(np.ptp(anchors[:, 1]), 5.)
        scope = decision["accepted_scope"]
        self.assertGreaterEqual(len(scope["tile_ids"]), 3)
        self.assertLess(len(scope["tile_ids"]), len(unit()["tile_ids"]))
        self.assertTrue(all(t >= 1000 for t in scope["tile_ids"]))
        self.assertEqual(decision["unknown_tile_count"], len(unit()["tile_ids"])-len(scope["tile_ids"]))
        self.assertIsNone(decision["scientific_verdict"])

    def test_source_swap_preserves_photometry_and_flips_selection(self):
        a, da = evaluate_unit(unit(), {"mvs": plane(10), "als": plane(12)}, synthetic_views(), self.config)
        b, db = evaluate_unit(unit(), {"mvs": plane(12), "als": plane(10)}, synthetic_views(), self.config)
        self.assertEqual(a["shared"], b["shared"])
        self.assertAlmostEqual(a["candidates"]["mvs"]["cost"], b["candidates"]["als"]["cost"], places=10)
        self.assertEqual((da["action"], db["action"]), ("IMAGE", "PRIOR"))

    def test_singleton_requires_own_observations_and_profile(self):
        one = {**unit(), "mvs_ids": [], "als_ids": [20]}
        source = {"als": plane(10), "mvs": {"valid": False}}
        observation, selected = evaluate_unit(one, source, synthetic_views(), self.config)
        self.assertEqual(selected["action"], "PRIOR")
        self.assertEqual(selected["reason"], "SINGLE_SOURCE_INDEPENDENTLY_OBSERVATION_SUPPORTED")
        self.assertEqual(observation["shared"]["common_scored_pair_count"], 0)
        _, flat = evaluate_unit(one, source, synthetic_views(flat=True), self.config)
        self.assertEqual(flat["action"], "ABSTAIN")
        _, few_views = evaluate_unit(one, source, synthetic_views()[:2], self.config)
        self.assertEqual(few_views["action"], "ABSTAIN")
        _, wrong = evaluate_unit(one, {"als": plane(12)}, synthetic_views(), self.config)
        self.assertEqual(wrong["action"], "ABSTAIN")

    def test_equal_candidates_and_ambiguous_components_are_not_forced_choices(self):
        sources = {"mvs": plane(), "als": plane()}
        _, equal = evaluate_unit(unit(), sources, synthetic_views(), self.config)
        self.assertEqual(equal["action"], "ABSTAIN")
        ambiguous = {**unit(), "mvs_ids": [12, 13]}
        _, multiple = evaluate_unit(ambiguous, {"mvs": plane(10), "als": plane(12)}, synthetic_views(), self.config)
        self.assertEqual(multiple["reason"], "AMBIGUOUS_MULTIPLE_SURFACE_COMPONENTS")

    def test_replay_matches_saved_pair_and_patch_costs(self):
        sources, views = {"mvs": plane(10), "als": plane(12)}, synthetic_views()
        observation, _ = evaluate_unit(unit(), sources, views, self.config)
        selected = next(p for p in observation["patches"] if all(v is not None for v in p["paired_costs"].values()))
        replay = replay_evidence(observation, sources, views, selected["pair_id"], selected["patch_index"])
        self.assertTrue(replay["available"])
        self.assertEqual(replay["common_pixels"], selected["common_pixels"])
        for source in ("mvs", "als"):
            self.assertAlmostEqual(replay["costs"][source], selected["paired_costs"][source], places=10)
            saved = next(p for p in observation["candidates"][source]["pairs"] if p["pair_id"] == selected["pair_id"])
            self.assertAlmostEqual(replay["reproduced_pair_costs"][source], saved["cost"], places=10)
        with self.assertRaises(ValueError):
            replay_evidence(observation, sources, views, "not-a-saved-pair")

    def test_disjoint_sources_cannot_rank_unrelated_photometric_means(self):
        sources = {"mvs": plane(10, -4, -2), "als": plane(10, 2, 4)}
        observation, decision = evaluate_unit(unit(), sources, synthetic_views(), self.config)
        self.assertEqual(observation["shared"]["common_scored_pair_count"], 0)
        self.assertIsNone(observation["contrast"]["signed_mvs_advantage"])
        self.assertEqual(decision["action"], "ABSTAIN")

    def test_spatial_opposition_is_not_overwritten_by_global_surface_winner(self):
        observation, selected = evaluate_unit(unit(), {"mvs": plane(10), "als": plane(12)},
                                              synthetic_views(), self.config)
        self.assertEqual(selected["action"], "IMAGE")
        scope = selected["accepted_scope"]["local_tile_indices"]
        # Controlled counter-evidence models a changed subarea after independent
        # tile/view aggregation. Minority opposition is excluded from scope;
        # balanced opposition demands subdivision of the surface context.
        observation["spatial"]["source_preference_tiles"] = {
            "mvs": scope[:-1], "als": scope[-1:], "inconsistent": []}
        partial = _decide(unit(), observation, DEFAULT_CONFIG["decision"], np.array(unit()["footprint_xy"]), .5)
        self.assertEqual(partial["action"], "IMAGE")
        self.assertNotIn(scope[-1], partial["accepted_scope"]["local_tile_indices"])
        split = len(scope)//2
        observation["spatial"]["source_preference_tiles"] = {
            "mvs": scope[:split], "als": scope[split:], "inconsistent": []}
        conflict = _decide(unit(), observation, DEFAULT_CONFIG["decision"], np.array(unit()["footprint_xy"]), .5)
        self.assertEqual(conflict["action"], "ABSTAIN")
        self.assertEqual(conflict["reason"], "SPATIAL_SOURCE_CONFLICT_REQUIRES_SUBDIVISION")


if __name__ == "__main__":
    unittest.main()

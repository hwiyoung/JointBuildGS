"""Failure-oriented checks for reference-free conditional source selection."""
import copy
import unittest

from src.phd.source_candidate_v1.decision import decide, _maximum_disjoint_pairs


def fixture():
    profile = [{"offset_m": offset, "cost": cost, "paired_delta_cost": cost-.1,
                "paired_nominal_cost": .1, "coverage_fraction": 1., "common_patch_count": 100}
               for offset, cost in zip([-2, -1, -.5, 0, .5, 1, 2], [.45, .3, .14, .1, .16, .3, .4])]
    observation = {"status": "ok", "shared": {"selected_pairs": []},
                   "candidates": {s: {"pairs": [], "profile": copy.deepcopy(profile)} for s in ("mvs", "als")}}
    for a, b in [(1, 2), (3, 4), (1, 3), (2, 4)]:
        pid = f"{a}->{b}"
        observation["shared"]["selected_pairs"].append({"pair_id": pid, "reference_id": a, "target_id": b})
        for source, cost in [("mvs", .1), ("als", .4)]:
            observation["candidates"][source]["pairs"].append({"pair_id": pid, "cost": cost, "common_patch_count": 25})
    metadata = {s: {"valid": True, "center": [0, 0, 0], "normal": [0, 0, 1],
                    "count": 20, "inlier_fraction": .95, "rms_m": .03, "p90_m": .05}
                for s in ("mvs", "als")}
    return observation, metadata


def set_costs(obs, mvs, als):
    for source, costs in [("mvs", mvs), ("als", als)]:
        for row, cost in zip(obs["candidates"][source]["pairs"], costs):
            row["cost"] = cost


class DecisionTests(unittest.TestCase):
    def test_source_swap_reverses_action_and_preserves_gates(self):
        obs, meta = fixture()
        image = decide(obs, meta)
        obs["candidates"]["mvs"], obs["candidates"]["als"] = obs["candidates"]["als"], obs["candidates"]["mvs"]
        prior = decide(obs, meta)
        self.assertEqual((image["action"], prior["action"]), ("IMAGE", "PRIOR"))
        self.assertEqual(image["score_margin"], prior["score_margin"])
        self.assertEqual(image["temporal_status"], "OBSERVATION_SUPPORTED_CONDITIONAL")
        self.assertIsNone(prior["scientific_verdict"])

    def test_weak_current_source_does_not_make_weak_prior_valid(self):
        obs, meta = fixture()
        set_costs(obs, [.8]*4, [.5]*4)
        result = decide(obs, meta)
        self.assertEqual(result["action"], "ABSTAIN")
        self.assertEqual(result["provisional_best_source"], "als")
        self.assertEqual(result["reason"], "BOTH_SOURCES_POOR_IMAGE_SUPPORT")

    def test_equal_and_near_equal_sources_abstain(self):
        for prior_cost in [.1, .12]:
            obs, meta = fixture()
            set_costs(obs, [.1]*4, [prior_cost]*4)
            self.assertEqual(decide(obs, meta)["reason"], "SOURCES_NOT_DISTINGUISHABLE")

    def test_single_source_cell_does_not_default_to_prior(self):
        obs, meta = fixture()
        meta["mvs"]["valid"] = False
        self.assertEqual(decide(obs, meta)["action"], "ABSTAIN")

    def test_distinct_views_and_disjoint_pairs_are_checked(self):
        obs, meta = fixture()
        geometry = obs["shared"]["selected_pairs"]
        geometry.pop()
        geometry[1].update(reference_id=1, target_id=3)
        geometry[2].update(reference_id=2, target_id=3)
        self.assertEqual(decide(obs, meta)["reason"], "INSUFFICIENT_DISTINCT_VIEWS")
        geometry[2].update(reference_id=1, target_id=4)
        self.assertEqual(decide(obs, meta)["reason"], "INSUFFICIENT_DISJOINT_PAIRS")

    def test_duplicate_and_nonfinite_pairs_do_not_create_support(self):
        obs, meta = fixture()
        obs["shared"]["selected_pairs"] = [obs["shared"]["selected_pairs"][0]]*10 + [obs["shared"]["selected_pairs"][1]]
        obs["candidates"]["mvs"]["pairs"][1]["cost"] = float("nan")
        result = decide(obs, meta)
        self.assertEqual(result["common_pairs"], 1)
        self.assertEqual(result["reason"], "INSUFFICIENT_COMMON_PAIRS")

    def test_conflicting_pairs_abstain_despite_good_median(self):
        obs, meta = fixture()
        set_costs(obs, [.1, .1, .3, .5], [.4, .4, .31, .1])
        self.assertEqual(decide(obs, meta)["reason"], "INCONSISTENT_PAIRED_SOURCE_PREFERENCE")

    def test_paired_difference_not_difference_of_independent_medians(self):
        obs, meta = fixture()
        obs["shared"]["selected_pairs"].pop()
        set_costs(obs, [0., .3, .2], [.1, .1, .3])
        result = decide(obs, meta)
        self.assertEqual(result["provisional_best_source"], "mvs")
        self.assertGreater(result["costs"]["mvs"], result["costs"]["als"])
        self.assertEqual(result["action"], "ABSTAIN")

    def test_wrong_shift_and_remote_secondary_minimum_abstain(self):
        obs, meta = fixture()
        obs["candidates"]["mvs"]["profile"][-1]["paired_delta_cost"] = -.05
        self.assertEqual(decide(obs, meta)["reason"], "PROFILE_REQUIRES_GEOMETRY_CORRECTION")
        obs["candidates"]["mvs"]["profile"][-1]["paired_delta_cost"] = .01
        self.assertEqual(decide(obs, meta)["reason"], "PROFILE_FLAT_OR_REMOTE_AMBIGUITY")

    def test_winner_flat_profile_abstains_loser_flat_does_not(self):
        obs, meta = fixture()
        for row in obs["candidates"]["als"]["profile"]:
            row["paired_delta_cost"] = 0.
        self.assertEqual(decide(obs, meta)["action"], "IMAGE")
        for row in obs["candidates"]["mvs"]["profile"]:
            row["paired_delta_cost"] = 0.
        self.assertEqual(decide(obs, meta)["action"], "ABSTAIN")

    def test_sparse_profile_control_support_abstains(self):
        obs, meta = fixture()
        for i in [0, 1, 5, 6]:
            obs["candidates"]["mvs"]["profile"][i]["coverage_fraction"] = .25
        self.assertEqual(decide(obs, meta)["reason"], "PROFILE_INSUFFICIENT_COVERAGE")

    def test_raw_profile_alone_does_not_establish_matched_control(self):
        obs, meta = fixture()
        for row in obs["candidates"]["mvs"]["profile"]:
            del row["paired_delta_cost"]
        self.assertEqual(decide(obs, meta)["reason"], "PROFILE_INSUFFICIENT_COVERAGE")

    def test_matching_is_not_order_dependent_greedy(self):
        self.assertEqual(_maximum_disjoint_pairs([(1, 2), (1, 3), (2, 4)]), 2)

    def test_actual_photometry_schema_selects_symmetric_true_plane(self):
        from src.phd.source_candidate_v1.photometry import score_candidates
        from tests.phd.test_source_candidate_photometry import plane, synthetic_views
        cfg = {"max_views": 4, "max_pairs": 6, "max_patch_centers": 9,
               "minimum_patch_std": 2.0, "profile_offsets_m": (-2., -1., -.5, 0., .5, 1., 2.)}
        for depths, action in [((10, 12), "IMAGE"), ((12, 10), "PRIOR")]:
            candidates = {"mvs": plane(depths[0]), "als": plane(depths[1])}
            measured = score_candidates(candidates, synthetic_views(), cfg)
            result = decide(measured, candidates)
            self.assertEqual(result["action"], action, result)
            self.assertEqual(result["winner_profile"]["metric"], "PAIRED_SHIFTED_MINUS_NOMINAL_COST_SAME_MASK")


if __name__ == "__main__":
    unittest.main()

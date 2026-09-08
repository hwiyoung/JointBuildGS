"""Post-seal scope, common-area, missing-output and lineage checks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from scripts.phd.surface_selection_v1.common import REQUIRED, sha
from scripts.phd.surface_selection_v1.evaluate import (
    evaluate_region, scope_tiles, summarize_tiles, tile_layout, verify_inputs_before_reference,
)
from scripts.phd.surface_selection_v1.report import build_report
from scripts.phd.source_candidate_v1.common import write


def fixture():
    xy = np.array([[x + dx, y + dy] for y in (0., .5) for x in (0., .5)
                   for dx, dy in ((.1, .1), (.2, .1), (.1, .2))])
    native = {s + "_xyz":np.column_stack((xy, np.full(len(xy), z))) for s, z in (("mvs", 1.), ("als", 3.))}
    membership = {s + "_component":np.zeros(len(xy), np.int32) for s in ("mvs", "als")}
    membership.update({s + "_unit":np.zeros(len(xy), np.int32) for s in ("mvs", "als")})
    membership.update(tile_unit=np.zeros(4, np.int32), shape=np.array([2, 2]), low=np.zeros(2), spacing=np.array(.5))
    components = {s:[dict(id=0, valid=True)] for s in ("mvs", "als")}
    units = [dict(id=0, mvs_ids=[0], als_ids=[0], tile_ids=[0, 1, 2, 3], area_m2=1., status="PAIRED")]
    decisions = [dict(unit_id=0, action="IMAGE", reason="OBSERVATION_SUPPORT", accepted_scope={"tile_ids":[0]})]
    legacy_membership = {s + "_cell":np.zeros(len(xy), np.int32) for s in ("mvs", "als")}
    legacy_membership.update({s + "_inlier":np.ones(len(xy), bool) for s in ("mvs", "als")})
    legacy_decisions = [dict(cell_id=0, action="IMAGE")]
    domain = dict(x=[0, 1], y=[0, 1], z=[0, 5])
    return native, membership, components, units, decisions, native["mvs_xyz"].copy(), domain, legacy_membership, legacy_decisions


def frozen_pair(root):
    new, old = root / "new", root / "old"
    new.mkdir(); old.mkdir()
    spec = dict(native_sha256="fixed-native", domain=dict(x=[0, 1], y=[0, 1], z=[0, 5]))
    config = dict(regions={r:spec for r in ("P1", "P2", "P3")})
    for run, names in ((new, REQUIRED), (old, ("candidates.json", "membership.npz", "observations.json", "decisions.json",
            "input_summary.json", "observation_summary.json", "decision_summary.json", "rgb_ledger.json"))):
        (run / "config.json").write_text(json.dumps(config))
        files = {}
        for region in config["regions"]:
            (run / region).mkdir()
            for name in names:
                path = run / region / name
                path.write_text("[]")
                files[f"{region}/{name}"] = sha(path)
        if run == old:
            (run / "sensitivity.json").write_text("[]")
            files["sensitivity.json"] = sha(run / "sensitivity.json")
        seal = dict(status="METHOD_FROZEN_BEFORE_REFERENCE_ACCESS", reference_accessed=False,
                    scientific_verdict=None, config_sha256=sha(run / "config.json"), files=files)
        (run / "method_seal.json").write_text(json.dumps(seal))
    return new, old


class SurfaceSelectionEvaluationTests(unittest.TestCase):
    def test_sampled_scope_does_not_propagate_to_whole_surface(self):
        units, tiles, summary = evaluate_region("P1", *fixture())
        self.assertEqual(summary["directly_sampled_accepted_area_m2"], .25)
        self.assertEqual(summary["conditional_whole_unit_area_m2"], 1.)
        self.assertEqual(summary["legacy_accepted_area_m2"], 1.)
        self.assertEqual(summary["selected_native_counts"], {"mvs":3, "als":0})
        self.assertEqual([r["action"] for r in tiles], ["IMAGE", "ABSTAIN", "ABSTAIN", "ABSTAIN"])
        self.assertEqual(units[0]["directly_sampled_scope"]["reference_count"], 3)
        self.assertEqual(units[0]["conditional_unit_scope"]["reference_count"], 12)
        self.assertEqual(summary["tile_constrained_completeness"]["directly_sampled"][0]["recall"], .25)
        self.assertEqual(summary["tile_constrained_completeness"]["conditional_whole_unit"][0]["recall"], 1.)

    def test_paired_regret_uses_identical_reference_tile(self):
        args = list(fixture())
        args[4][0]["action"] = "PRIOR"
        units, tiles, summary = evaluate_region("P1", *args)
        self.assertEqual(tiles[0]["mvs_error_m"], 0.)
        self.assertEqual(tiles[0]["als_error_m"], 2.)
        self.assertEqual(tiles[0]["regret_m"], 2.)
        self.assertFalse(tiles[0]["selection_correct"])
        self.assertEqual(summary["accepted_incorrect_clear_gap_area_m2"], .25)
        self.assertEqual(summary["same_new_and_legacy_accepted_tiles"]["new_minus_legacy_error_m"]["mean"], 2.)

    def test_singleton_has_no_fabricated_paired_oracle(self):
        args = list(fixture())
        args[1]["als_component"][:] = -1
        args[2]["als"] = []
        args[3][0].update(als_ids=[], status="SINGLE_SOURCE")
        units, tiles, summary = evaluate_region("P1", *args)
        self.assertEqual(tiles[0]["selected_error_m"], 0.)
        self.assertIsNone(tiles[0]["regret_m"])
        self.assertIsNone(tiles[0]["selection_correct"])
        self.assertEqual(summary["accepted_singleton_area_m2"], .25)

    def test_abstention_and_absent_reference_remain_distinct(self):
        args = list(fixture())
        args[4][0].update(action="ABSTAIN", accepted_scope={"tile_ids":[]})
        _, _, summary = evaluate_region("P1", *args)
        self.assertEqual(summary["directly_sampled_coverage"], 0.)
        self.assertEqual(summary["tile_constrained_completeness"]["directly_sampled"][0]["recall"], 0.)
        args[5] = np.empty((0, 3))
        _, tiles, no_ref = evaluate_region("P1", *args)
        self.assertEqual(no_ref["total_area_m2"], 1.)
        self.assertEqual(no_ref["reference_supported_area_m2"], 0.)
        self.assertIsNone(no_ref["tile_constrained_completeness"]["directly_sampled"][0]["recall"])
        self.assertTrue(all(r["mvs_error_m"] is None for r in tiles))

    def test_clipped_edge_tiles_weight_by_area_not_unit_count(self):
        centers, area = tile_layout(dict(x=[0, .75], y=[0, .5]), .5, [2, 1])
        np.testing.assert_allclose(area, [.25, .125])
        _, rows, _ = evaluate_region("P1", *fixture())
        small = copy.deepcopy(rows[:2])
        small[0].update(area_m2=.25, mvs_raw_error_m=0., mvs_error_m=0.)
        small[1].update(area_m2=.125, mvs_raw_error_m=3., mvs_error_m=3.)
        result = summarize_tiles(small)
        self.assertAlmostEqual(result["native_geometry_on_all_tiles"]["mvs_raw_error_m"]["mean"], 1.)
        self.assertAlmostEqual(result["directly_sampled_coverage"], 2 / 3)

    def test_scope_and_point_identity_cannot_escape_frozen_units(self):
        _, membership, _, units, decisions, *_ = fixture()
        for ids in ([8], [0, 0]):
            bad = copy.deepcopy(decisions[0]); bad["accepted_scope"]["tile_ids"] = ids
            with self.assertRaisesRegex(ValueError, "escapes or duplicates"):
                scope_tiles(units[0], bad)
        args = list(fixture())
        args[1]["mvs_unit"][0] = 9
        with self.assertRaisesRegex(ValueError, "Native unit identity changed"):
            evaluate_region("P1", *args)

    def test_native_diagnostics_preserve_rejected_points(self):
        args = list(fixture())
        args[1]["mvs_component"][0] = -1
        _, _, summary = evaluate_region("P1", *args)
        whole = summary["whole_native_point_weighted_diagnostics"]
        self.assertEqual(whole["mvs_whole_native"]["prediction_count"], 12)
        self.assertEqual(whole["mvs_segmented_native"]["prediction_count"], 11)
        self.assertEqual(summary["native_counts"]["mvs"], 12)
        self.assertEqual(summary["segmented_native_counts"]["mvs"], 11)

    def test_all_three_methods_and_legacy_verify_before_reference_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, old = frozen_pair(Path(tmp))
            with patch("numpy.load", side_effect=AssertionError("Reference cannot open during seal verification")):
                verify_inputs_before_reference(new, old)
                (new / "P3/decisions.json").write_text("[42]")
                with self.assertRaisesRegex(ValueError, "Method bytes changed"):
                    verify_inputs_before_reference(new, old)
        with tempfile.TemporaryDirectory() as tmp:
            new, old = frozen_pair(Path(tmp))
            (old / "P2/decisions.json").write_text("[42]")
            with self.assertRaisesRegex(ValueError, "Sealed method bytes changed"):
                verify_inputs_before_reference(new, old)

    def test_nonrefining_legacy_grid_is_not_silently_projected(self):
        with self.assertRaisesRegex(ValueError, "exactly refine"):
            evaluate_region("P1", *fixture(), legacy_cell_m=.7)

    def test_report_verifies_evaluation_receipt_and_preserves_scope_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run, _ = frozen_pair(root)
            evaluation = run / "evaluation"
            evaluation.mkdir()
            summaries, units, tiles = {}, [], []
            seal = json.loads((run / "method_seal.json").read_text())
            for region in ("P1", "P2", "P3"):
                ur, tr, summary = evaluate_region(region, *fixture())
                summaries[region] = summary; units.extend(ur); tiles.extend(tr)
                path = run / region / "input_summary.json"
                path.write_text(json.dumps(dict(components=dict(mvs=1, als=1))))
                seal["files"][f"{region}/input_summary.json"] = sha(path)
            (run / "method_seal.json").write_text(json.dumps(seal))
            write(evaluation / "summary.json", dict(regions=summaries, legacy_method_seal_sha256="old-seal"))
            write(evaluation / "per_unit.json", units)
            write(evaluation / "per_tile.json", tiles)
            (evaluation / "per_unit.csv").write_text("region,unit_id\nP1,0\n")
            (evaluation / "per_tile.csv").write_text("region,tile_id\nP1,0\n")
            write(evaluation / "evaluation_receipt.json", dict(scientific_verdict=None,
                method_seal_sha256=sha(run / "method_seal.json"),
                reference_accessed_only_after_all_method_verification=True,
                output_sha256={p.name:sha(p) for p in evaluation.iterdir()}))
            path = build_report(run, root / "report", "/host/test-run")
            text = path.read_text()
            self.assertIn("직접 채택", text)
            self.assertIn("단위 전체 전파 가정", text)
            self.assertIn("scientific_verdict: null", text)
            self.assertIn("stage=3", text)
            self.assertIn("/host/test-run/run/evaluation/per_tile.csv", text)
            with self.assertRaises(FileExistsError):
                build_report(run, root / "report", "/host/test-run")
            (evaluation / "per_unit.json").write_text("[]")
            with self.assertRaisesRegex(ValueError, "Evaluation output changed"):
                build_report(run, root / "another-report", "/host/test-run")


if __name__ == "__main__":
    unittest.main()

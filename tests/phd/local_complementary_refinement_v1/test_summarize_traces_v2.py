"""Trace alignment, partial-write handling, provenance and static export checks."""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/phd/local_complementary_refinement_v1"))
from summarize_traces_v2 import (build_report, digest_bytes, pair_trajectories,
                                 parse_trace, source_cost, summarize_pair,
                                 capture_iterations, compare_cost_scopes, CHART_CONTRACT)


def native(iteration, camera="cameraA", visual_weight=.05, offset=0):
    return dict(iteration=iteration, camera=camera, rgb_loss=.1 + offset,
                lod_loss=2. + offset, da_loss=4. + offset, lod_weight=.005,
                da_weight=visual_weight, gaussians=100 + iteration,
                protected=50, elapsed_seconds=iteration / 100.,
                peak_cuda_allocated_bytes=1024, peak_cuda_reserved_bytes=2048,
                peak_rss_bytes=4096)


def local(row, config_hash="cfg", binding_hash="binding"):
    return dict(schema="JBGS_LOCAL_COMPLEMENTARY_TRACE_v2", iteration=row["iteration"],
                camera=row["camera"], config_sha256=config_hash, input_binding_sha256=binding_hash,
                tau0=.5, tau1=2., lambda_prior=.005, lambda_visual=row["da_weight"],
                raw_prior_loss=row["lod_loss"], raw_visual_loss=row["da_loss"], rgb_loss=row["rgb_loss"],
                weighted_prior_loss=row["lod_loss"] / 2, weighted_visual_loss=row["da_loss"] / 2,
                weighted_depth_total=.005 * row["lod_loss"] / 2 + row["da_weight"] * row["da_loss"] / 2,
                prior_valid=20, visual_valid=20, both_valid=20, prior_only=0, visual_only=0,
                neither_valid=0, a_mean_both=.5, a_zero_both=0, a_one_both=0,
                prior_multiplier_mean_valid=.5, visual_multiplier_mean_valid=.5,
                prior_effective_global_coefficient=.0025,
                visual_effective_global_coefficient=row["da_weight"] / 2,
                prior_denominator=20, visual_denominator=20,
                controller_state={"phase": 1}, gaussians=row["gaussians"] - 3, protected=50)


def pair(g, lc, weights=None):
    return pair_trajectories(g, lc, weights if weights is not None else [local(r) for r in lc],
                            cfg_hash="cfg", binding_hash="binding", tau0=.5, tau1=2., lambda_prior=.005)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value).encode()
    path.write_bytes(data)
    return data


class TraceSemanticsTests(unittest.TestCase):
    def test_incomplete_final_line_is_visible_but_corrupt_complete_line_fails(self):
        complete = json.dumps(native(8100)).encode() + b"\n"
        rows, ignored = parse_trace(complete + b'{"iteration": 82')
        self.assertEqual([r["iteration"] for r in rows], [8100])
        self.assertEqual(ignored, 16)
        with self.assertRaises(ValueError):
            parse_trace(complete + b'{"iteration": 82\n')

    def test_duplicate_or_nonfinite_trace_is_rejected(self):
        row = json.dumps(native(8100)).encode() + b"\n"
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            parse_trace(row + row)
        with self.assertRaises(ValueError):
            parse_trace(b'{"iteration": 8100, "camera": "a", "loss": NaN}\n')

    def test_only_refinement_exact_intersection_is_paired_without_camera_or_lambda_assumption(self):
        g = [native(8000), native(8100), native(8200), native(8300)]
        lc = [native(8100, "different", .01, .2), native(8300, "cameraA", .05, .3)]
        weights = [local(native(8001))] + [local(r) for r in lc]
        pairs, coverage = pair(g, lc, weights)
        self.assertEqual([r["iteration"] for r in pairs], [8100, 8300])
        self.assertEqual(coverage["same_camera_rows"], 1)
        self.assertEqual(coverage["differing_lambda_visual_rows"], 1)
        self.assertEqual(coverage["local_without_native_iterations"], [8001])
        self.assertIsNone(pairs[0]["controller_phase_G"])
        self.assertEqual(pairs[0]["controller_phase_LC"], 1)
        self.assertNotEqual(pairs[0]["lc_objective_gaussians_before_backward"], pairs[0]["gaussians_LC"])
        summary = summarize_pair(pairs)
        self.assertAlmostEqual(summary["rgb_loss_paired_delta_sample_mean"], .25)
        self.assertAlmostEqual(summary["rgb_loss_same_camera_delta_sample_mean"], .3)

    def test_missing_or_changed_binding_and_wrong_raw_controller_values_fail(self):
        g, lc = [native(8100)], [native(8100)]
        for field, value in (("config_sha256", "wrong"), ("input_binding_sha256", None),
                             ("tau0", 30.), ("raw_visual_loss", 900.), ("camera", "different")):
            weights = [local(lc[0])]
            weights[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                pair(g, lc, weights)

    def test_native_zero_start_has_only_one_anchor_prefix_subtraction(self):
        rows = [native(8000), native(30000)]
        actual = source_cost({"training_start_iteration": 0, "wall_seconds": 400.}, rows)
        self.assertEqual(actual["driver_wall_minus_anchor_prefix_seconds_approx"], 320.)
        resumed = source_cost({"training_start_iteration": 8000, "wall_seconds": 400.}, rows)
        self.assertEqual(resumed["driver_wall_minus_anchor_prefix_seconds_approx"], 400.)
        missing_prefix = source_cost({"training_start_iteration": 0, "wall_seconds": 400.}, rows[1:])
        self.assertIsNone(missing_prefix["driver_wall_minus_anchor_prefix_seconds_approx"])

    def test_checkpoint_schedule_separates_declared_resumed_active_and_observed(self):
        command = ["python", "train.py", "--jbgs_capture_iterations", "8000", "8100", "30000", "--eval"]
        self.assertEqual(capture_iterations(command), [8000, 8100, 30000])
        cost = source_cost({"training_start_iteration": 8000}, [native(8100)],
                           {"command": command}, [8100])
        self.assertEqual(cost["complete_capture_iterations_active_after_start"], [8100, 30000])
        self.assertEqual(cost["complete_capture_iterations_observed"], [8100])
        self.assertFalse(cost["pure_refinement_peak_identified"])
        self.assertFalse(cost["cumulative_peak_subtraction_performed"])
        self.assertIsNone(cost["driver_wall_seconds"])
        with self.assertRaises(ValueError):
            capture_iterations(["--jbgs_capture_iterations", "8000", "8000"])

    def test_capture_at_first_trace_endpoint_contributes_to_following_elapsed_span(self):
        g = source_cost({"training_start_iteration": 0, "command": ["--jbgs_capture_iterations", "8000", "8100", "30000"]}, [])
        lc = source_cost({"training_start_iteration": 8000, "command": ["--jbgs_capture_iterations", "30000"]}, [])
        pairs, _ = pair([native(8100), native(30000)], [native(8100), native(30000)])
        comparison = compare_cost_scopes(g, lc, pairs)
        self.assertFalse(comparison["capture_schedule_match"])
        self.assertFalse(comparison["training_start_match"])
        self.assertTrue(comparison["wall_comparison_has_unequal_checkpoint_schedule"])
        self.assertEqual(comparison["complete_captures_potentially_inside_observed_span_G"], [8100])
        self.assertEqual(comparison["complete_captures_potentially_inside_observed_span_LC"], [])
        self.assertFalse(comparison["local_loss_memory_gain_established"])
        self.assertIn("ordered optimization iterations", CHART_CONTRACT["family_rationale"])


class TraceReportTests(unittest.TestCase):
    def fixture(self, root, lc_started=True):
        g_root, new_root = root / "G", root / "LC"
        config = dict(schema="jbgs.local_complementary_refinement.v2", regions=["P2"],
            conditions=[dict(id="LC_D005_Pnative", parent_condition="D005_Pnative", lambda_p=.005)],
            local_weight={"tau0_m": .5, "tau1_m": 2.})
        config_path, binding_path = root / "config.json", root / "binding.json"
        cfg_data = write(config_path, config)
        g_run = g_root / "P2/D005_Pnative"
        g_inv = write(g_run / "train_invocation.json", dict(region="P2", condition="D005_Pnative", config_sha256="parentcfg",
            training_start_iteration=0, command=["--jbgs_capture_iterations", "8000", "8100", "30000"]))
        g_receipt = write(g_run / "train_receipt.json", dict(status="PASS", training_start_iteration=0, wall_seconds=400.))
        native_rows = [native(i) for i in (8000, 8100, 8200, 8300, 30000)]
        (g_run / "model").mkdir()
        (g_run / "model/jbgs_trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in native_rows))
        for iteration in (8000, 8100, 30000):
            write(g_run / f"model/jbgs_complete/iteration_{iteration}/receipt.json", {"iteration": iteration})
        binding = dict(config={"sha256": digest_bytes(cfg_data)}, tau0_m=.5, tau1_m=2.,
            regions={"P2": {"baselines": {"D005_Pnative": {
                "train_invocation": {"sha256": digest_bytes(g_inv)},
                "train_receipt": {"sha256": digest_bytes(g_receipt)}}}}})
        binding_data = write(binding_path, binding)
        new_run = new_root / "P2/LC_D005_Pnative"
        if lc_started:
            write(new_run / "train_invocation.json", dict(region="P2", condition="LC_D005_Pnative",
                config_sha256=digest_bytes(cfg_data), input_binding={"sha256": digest_bytes(binding_data)}, training_start_iteration=8000,
                command=["--jbgs_capture_iterations", "30000"]))
            (new_run / "model").mkdir()
            lc_rows = [native(i, offset=.05) for i in (8100, 8200, 8300)]
            (new_run / "model/jbgs_trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in lc_rows))
            (new_run / "model/local_trace.jsonl").write_text("".join(json.dumps(local(r, digest_bytes(cfg_data), digest_bytes(binding_data))) + "\n" for r in lc_rows))
        return g_root, new_root, config_path, binding_path, new_run

    def test_partial_run_reports_snapshots_exact_hashes_csv_and_sparse_plot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            g, lc, cfg, binding, new_run = self.fixture(root)
            output = root / "report"
            report = build_report(g, lc, cfg, binding, output)
            self.assertEqual(report["status_counts"], {"PARTIAL": 1})
            self.assertEqual(report["paired_iterations"], 3)
            self.assertIsNone(report["scientific_verdict"])
            self.assertFalse(report["reference_accessed"])
            self.assertEqual(report["report_revision"], "v2.1_checkpoint_cost_scope")
            self.assertTrue((output / "report_change_record.json").is_file())
            cost = report["conditions"][0]
            self.assertEqual(cost["baseline_cost"]["complete_capture_iterations_observed"], [8000, 8100, 30000])
            self.assertEqual(cost["lc_cost"]["complete_capture_iterations_observed"], [])
            self.assertFalse(cost["cost_comparison"]["capture_schedule_match"])
            self.assertTrue((output / "paired_iterations.csv").is_file())
            for source in report["sources"]:
                self.assertEqual(digest_bytes((output / source["snapshot_path"]).read_bytes()), source["sha256"])
            png = output / "P2_LC_D005_Pnative_trace.png"
            self.assertGreater(png.stat().st_size, 10000)
            qa = os.environ.get("JBGS_TRACE_QA_OUTPUT")
            if qa:
                shutil.copyfile(png, Path(qa) / "synthetic_partial_trace.png")
            with self.assertRaises(FileExistsError):
                build_report(g, lc, cfg, binding, output)

    def test_unstarted_run_is_retained_and_does_not_make_fake_plot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            g, lc, cfg, binding, _ = self.fixture(root, lc_started=False)
            output = root / "report"
            report = build_report(g, lc, cfg, binding, output)
            self.assertEqual(report["status_counts"], {"NOT_STARTED": 1})
            self.assertEqual(report["paired_iterations"], 0)
            self.assertEqual(list(output.glob("*.png")), [])

    def test_completed_claim_without_final_trace_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            g, lc, cfg, binding, new_run = self.fixture(root)
            receipt = json.loads((new_run / "train_invocation.json").read_text())
            receipt["status"] = "PASS"
            write(new_run / "train_receipt.json", receipt)
            with self.assertRaisesRegex(ValueError, "final matched trace"):
                build_report(g, lc, cfg, binding, root / "report", plots=False)

    def test_bound_baseline_mutation_and_output_in_run_tree_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            g, lc, cfg, binding, _ = self.fixture(root)
            with self.assertRaisesRegex(ValueError, "separate"):
                build_report(g, lc, cfg, binding, lc / "bad-output", plots=False)
            (g / "P2/D005_Pnative/train_invocation.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "reuse binding"):
                build_report(g, lc, cfg, binding, root / "report", plots=False)


if __name__ == "__main__":
    unittest.main()

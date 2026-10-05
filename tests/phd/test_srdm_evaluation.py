"""Synthetic-only checks; no research input or UAS payload is opened."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("srdm_evaluation", REPO / "scripts/phd/srdm_p1p2p3_v1/evaluate.py")
ev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ev)


def fixture(base, empty_reference=False, empty_prediction=False):
    run = base / "run"
    run.mkdir()
    ref = base / "fake_reference"
    ref.mkdir()
    points = np.array([[.25, .25, .5], [.3, .3, 1.5]], dtype=np.float64)
    reference = np.empty((0, 3)) if empty_reference else points[:1]
    candidate = np.empty((0, 3)) if empty_prediction else points
    domain = {"bbox_min": [0., 0., 0.], "bbox_max": [3., 3., 3.]}
    outputs, regions = {}, []
    for rid in ev.REGIONS:
        directory = run / rid
        directory.mkdir()
        pair = {"bbox_min": domain["bbox_min"], "bbox_max": domain["bbox_max"],
                "left_rgb": np.full((4, 4, 3), 128, np.uint8), "right_rgb": np.full((4, 4, 3), 128, np.uint8),
                "sparse_disparity": np.ones((4, 4)), "disparity_min": 0, "disparity_max": 4,
                "als_xyz": points, "als_source_row": np.array([17, 92]), "als_source_file_index": np.array([0, 0]),
                "als_pixel_xy": np.array([[0., 0.], [1., 0.]]), "rectified_left_to_world_R": np.eye(3),
                "rectified_left_to_world_t": np.zeros(3), "P1": np.c_[np.eye(3), np.zeros(3)]}
        np.savez_compressed(directory / "pair.npz", **pair)
        np.savez_compressed(directory / "decision.npz", als_xyz=points, source_row=np.array([17, 92]),
                            keep=np.array([True, False]), rejected=np.array([False, True]), unassessed=np.array([False, False]),
                            weak_disparity=np.ones((4, 4)), weak_valid=np.ones((4, 4), bool),
                            prior_keep=np.zeros((4, 4), bool), prior_reject=np.zeros((4, 4), bool), prior_untestable=np.zeros((4, 4), bool))
        for arm in ev.ARMS:
            arm_root = directory / arm
            arm_root.mkdir()
            interp = np.zeros((4, 4), bool)
            interp[0, 1] = True
            np.savez_compressed(arm_root / "result.npz", xyz=candidate, rgb=np.full(candidate.shape, 128, np.uint8),
                                pixel_uv=np.empty((0, 2), int) if empty_prediction else np.array([[0, 0], [1, 0]]),
                                interpolated_mask=interp, disparity=np.ones((4, 4)), valid=np.ones((4, 4), bool))
        for filename in ("pair.npz", "decision.npz", *[f"{a}/result.npz" for a in ev.ARMS]):
            outputs[f"{rid}/{filename}"] = ev.sha(directory / filename)
        ref_path = ref / (rid + ".npz")
        np.savez_compressed(ref_path, uas_xyz=reference)
        regions.append({"id": rid, "domain": domain, "frozen_reference_npz": str(ref_path), "frozen_reference_sha256": ev.sha(ref_path)})
    cfg = {"scientific_verdict": None, "frame": {"working_crs": "EPSG:25832", "world_shift_xyz_m": [0, 0, 0]},
           "xy_cell_m": .5, "distance_thresholds_m": [.1, .5, 1.], "density_voxel_m": [.1, .5],
           "workers": 1, "display_max_points": 100, "section_half_width_m": .25, "regions": regions}
    config_path, seal_path = base / "config.json", run / "CANDIDATE_SEAL.json"
    config_path.write_text(json.dumps(cfg))
    seal_path.write_text(json.dumps({"scientific_verdict": None, "reference_accessed": False, "outputs": outputs}))
    return run, config_path, seal_path


class SRDMEvaluationTests(unittest.TestCase):
    def run_fixture(self, directory, **options):
        run, config, seal = fixture(directory, **options)
        output = directory / "evaluation"
        ev.run(run, config, seal, output)
        return run, output, ev.read_json(output / "evaluation.json")

    def test_empty_reference_is_na_not_zero_precision(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, summary = self.run_fixture(Path(temp), empty_reference=True)
            for region in summary["regions"]:
                self.assertEqual(region["status"], "REFERENCE_EMPTY")
                for arm in ev.ARMS:
                    self.assertEqual(region["arms"][arm]["status"], "REFERENCE_ABSENT")
                    stats = region["arms"][arm]["measurements"]["native"]["candidate_to_reference"]
                    self.assertEqual(stats["n_total"], 2)
                    self.assertEqual(stats["reference_status"], "REFERENCE_ABSENT")
                    self.assertIsNone(stats["fraction_within_m"]["0.5"])
                    self.assertIsNone(stats["mean_m"])

    def test_empty_prediction_has_zero_reference_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, summary = self.run_fixture(Path(temp), empty_prediction=True)
            for region in summary["regions"]:
                self.assertEqual(region["status"], "MEASURED")
                for arm in ev.ARMS:
                    self.assertEqual(region["arms"][arm]["status"], "EMPTY_PREDICTION")
                    stats = region["arms"][arm]["measurements"]["native"]["reference_to_candidate"]
                    self.assertEqual(stats["reference_status"], "AVAILABLE")
                    self.assertEqual(stats["n_total"], 1)
                    self.assertEqual(stats["n_without_target"], 1)
                    self.assertEqual(stats["fraction_within_m"]["0.5"], 0.)
                    self.assertIsNone(stats["median_m"])

    def test_native_points_are_not_replaced_by_grid_or_voxels(self):
        with tempfile.TemporaryDirectory() as temp:
            _, output, summary = self.run_fixture(Path(temp))
            data = summary["regions"][0]["arms"]["SRDM_NATIVE"]
            self.assertEqual(data["status"], "MEASURED")
            native = data["measurements"]["native"]["candidate_to_reference"]
            self.assertEqual(native["n_total"], 2)
            self.assertEqual(data["interpolated_points"], 1)
            self.assertEqual(data["original_points"], 1)
            self.assertEqual(data["measurements"]["original_points_only"]["candidate_to_reference"]["mean_m"], 0.)
            self.assertEqual(native["fraction_within_m"]["0.5"], .5)
            self.assertGreater(native["mean_m"], .5)
            self.assertEqual(summary["regions"][0]["common_all_arm_reference_xy_cells"], 1)
            raw = ev.load_npz(output / "P1/SRDM_NATIVE/native_distances.npz")
            np.testing.assert_array_equal(raw["candidate_source_index"], [0, 1])
            np.testing.assert_array_equal(raw["interpolated"], [False, True])
            self.assertIsNone(summary["scientific_verdict"])

    def test_mask_alignment_and_uv_order(self):
        mask = np.array([[False, True], [False, False]])
        np.testing.assert_array_equal(ev.interpolation_flags({"pixel_uv": np.array([[1, 0], [0, 1]]), "interpolated_mask": mask}, 2), [True, False])
        for uv in (np.array([[2, 0]]), np.array([[.5, 0]]), np.array([[0, 0], [1, 1]])):
            with self.assertRaises(ValueError):
                ev.interpolation_flags({"pixel_uv": uv, "interpolated_mask": mask}, 1)
        aligned = {"pixel_uv": np.array([[1, 0]]), "interpolated_mask": mask}
        for malformed in ({"valid": np.zeros((2, 2), bool)},
                          {"valid": np.ones((1, 1), bool)},
                          {"disparity": np.full((2, 2), np.nan)},
                          {"interpolated_mask": np.zeros(4, bool)}):
            with self.assertRaises(ValueError):
                ev.interpolation_flags({**aligned, **malformed}, 1)

    def test_incomplete_seal_stops_before_reference_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, config, seal = fixture(root)
            document = ev.read_json(seal)
            del document["outputs"]["P3/SRDM_NATIVE/result.npz"]
            seal.write_text(json.dumps(document))
            with mock.patch.object(ev, "evaluate_region") as reference_stage:
                with self.assertRaisesRegex(ValueError, "Incomplete three-region seal"):
                    ev.run(run, config, seal, root / "evaluation")
                reference_stage.assert_not_called()
            self.assertFalse((root / "evaluation").exists())

    def test_mutated_candidate_stops_before_reference_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, config, seal = fixture(root)
            with (run / "P2/SRDM_FILTER_OFF/result.npz").open("ab") as handle:
                handle.write(b"changed after seal")
            with mock.patch.object(ev, "evaluate_region") as reference_stage:
                with self.assertRaisesRegex(ValueError, "Candidate hash mismatch"):
                    ev.run(run, config, seal, root / "evaluation")
                reference_stage.assert_not_called()

    def test_report_smoke_uses_synthetic_evaluation_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, output, _ = self.run_fixture(root)
            spec = importlib.util.spec_from_file_location("srdm_report", REPO / "scripts/phd/srdm_p1p2p3_v1/build_report.py")
            report = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(report)
            report.run(run, output, root / "report")
            document = (root / "report/index.html").read_text()
            self.assertIn("SRDM 두 단계 재구현", document)
            self.assertIn("scientific_verdict: null", document)
            for rid in ev.REGIONS:
                self.assertTrue((root / f"report/{rid}/fixed_sections.png").stat().st_size > 0)
                self.assertTrue((root / f"report/{rid}/data/SRDM_NATIVE.ply").stat().st_size > 0)
            receipt = ev.read_json(root / "report/report_receipt.json")
            self.assertIsNone(receipt["scientific_verdict"])
            empty_region = ev.read_json(output / "P1/evaluation.json")
            empty_region["arms"]["SRDM_NATIVE"]["status"] = "EMPTY_PREDICTION"
            empty_region["arms"]["SRDM_NATIVE"]["native_points_in_roi"] = 0
            label = report.metric_table(empty_region)
            self.assertIn("EMPTY_PREDICTION", label)
            self.assertIn("이 단일 영상쌍의 ROI 예측 점 없음", label)

    def test_optional_paired_report_preserves_portable_files_and_evaluation_lineage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, config, seal = fixture(root)
            cfg = ev.read_json(config)
            cfg["distance_thresholds_m"] = [.1, .25, .5, 1.]
            config.write_text(json.dumps(cfg))
            output = root / "evaluation"
            ev.run(run, config, seal, output)
            modules = {}
            for name in ("analyze_paired", "build_report"):
                spec = importlib.util.spec_from_file_location("srdm_" + name, REPO / f"scripts/phd/srdm_p1p2p3_v1/{name}.py")
                modules[name] = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(modules[name])
            modules["analyze_paired"].run(run, output, root / "paired")
            report = modules["build_report"]
            # Existing smoke test covers ordinary figures; exercise the actual
            # optional section and full report packaging without plotting them twice.
            def paired_only(run_root, eval_root, destination, region, config, paired_root):
                return report.paired_region_section(paired_root, destination, region["id"])
            with mock.patch.object(report, "region_figures", side_effect=paired_only):
                report.run(run, output, root / "report", root / "paired")
            document = (root / "report/index.html").read_text()
            self.assertIn("거리 감소 ≥ 0.25 m", document)
            self.assertIn("추가(gained) 0개", document)
            self.assertIn("소실(lost) 0개", document)
            for rid in ev.REGIONS:
                for name in ("common_pixel_delta.png", "common_pixel_deltas.csv.gz", "measured_pixel_union.csv.gz"):
                    copied = root / "report" / rid / "data/paired" / name
                    self.assertEqual(ev.sha(copied), ev.sha(root / "paired" / rid / name))
            receipt = ev.read_json(root / "report/report_receipt.json")
            self.assertEqual(receipt["paired_analysis_sha256"], ev.sha(root / "paired/paired_analysis.json"))
            paired = ev.read_json(root / "paired/paired_analysis.json")
            paired["evaluation_input_sha256"]["evaluation.json"] = "wrong-evaluation"
            (root / "paired/paired_analysis.json").write_text(json.dumps(paired))
            with self.assertRaisesRegex(ValueError, "does not refer to this evaluation"):
                report.run(run, output, root / "wrong-report", root / "paired")
            self.assertFalse((root / "wrong-report").exists())


if __name__ == "__main__":
    unittest.main()

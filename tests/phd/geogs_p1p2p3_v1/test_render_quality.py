import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

MODULE = Path(__file__).resolve().parents[3] / "scripts/phd/geogs_p1p2p3_v1/evaluation/render_quality.py"
spec = importlib.util.spec_from_file_location("geogs_render_quality", MODULE)
quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality)


class RecordingScorer:
    metadata = {"fixture_only": True}

    def __init__(self):
        self.calls = []

    def score(self, photo, render):
        self.calls.append((photo.copy(), render.copy()))
        return {"psnr_native_db": 0.0, "ssim_native": 0.0, "lpips_vgg_native_01": None,
                "lpips_vgg_signed_11": None, "lpips_status": "FIXTURE_NO_NETWORK"}


class ProjectedDomainTests(unittest.TestCase):
    def setUp(self):
        self.K = np.array([[10, 0, 50], [0, 10, 40], [0, 0, 1]], dtype=float)

    def bbox(self, bounds, K=None):
        return quality.projected_prism_bbox(bounds, np.eye(3), np.zeros(3), self.K if K is None else K, 100, 80)

    def test_front_prism_uses_actual_principal_point(self):
        bounds = [[-1, 1], [-1, 1], [2, 4]]
        self.assertEqual(self.bbox(bounds), [45, 35, 55, 45])
        shifted = self.K.copy()
        shifted[0, 2] += 5
        self.assertEqual(self.bbox(bounds, shifted), [50, 35, 60, 45])

    def test_camera_plane_crossing_clips_to_full_image(self):
        self.assertEqual(self.bbox([[-1, 1], [-1, 1], [-1, 1]]), [0, 0, 100, 80])

    def test_behind_camera_and_outside_image_have_no_domain(self):
        self.assertIsNone(self.bbox([[-1, 1], [-1, 1], [-4, -2]]))
        self.assertIsNone(self.bbox([[10, 12], [-1, 1], [1, 2]]))

    def test_invalid_bounds_fail_instead_of_selecting_a_region(self):
        with self.assertRaises(ValueError):
            self.bbox([[1, -1], [-1, 1], [2, 4]])


class EvaluationIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.photos = self.root / "photos"
        self.photos.mkdir()
        self.photo = np.full((40, 48, 3), 255, dtype=np.uint8)
        self.render = np.zeros_like(self.photo)
        Image.fromarray(self.photo).save(self.photos / "photo.png")
        Image.fromarray(self.render).save(self.root / "render.png")
        self.view = dict(name="photo.png", image_id=91, camera_id=2, width=48, height=40,
                         sha256=quality.sha(self.photos / "photo.png"), R=np.eye(3).tolist(), t=[0, 0, 0],
                         K=[[10, 0, 24], [0, 10, 20], [0, 0, 1]])
        self.split = dict(train=[], evaluation=[self.view])
        self.record = dict(name="photo.png", evaluation_index=0, image_id=91, camera_id=2,
                           render_path=str(self.root / "render.png"), render_sha256=quality.sha(self.root / "render.png"))
        self.bounds = [[-1, 1], [-1, 1], [2, 4]]
        self.scorer = RecordingScorer()

    def tearDown(self):
        self.temp.cleanup()

    def evaluate(self, records):
        return quality.evaluate_render_set(self.split, records, self.bounds, self.photos,
                self.scorer, self.root / "results", "P1", "synthetic_fixture", "fixture", 0, "a"*64)

    def test_black_prediction_is_scored_on_every_domain_pixel(self):
        result = self.evaluate([self.record])
        full, roi = result["rows"]
        self.assertEqual(full["pixel_count"], 40*48)
        self.assertEqual(roi["pixel_count"], 100)
        self.assertEqual(len(self.scorer.calls), 2)
        for photo, render in self.scorer.calls:
            self.assertTrue(np.all(photo == 255))
            self.assertTrue(np.all(render == 0))
        with Image.open(self.root / "results" / full["montage"]) as figure:
            pixels = np.array(figure)
            # Error panel is fixed-scale white for full 255 intensity error.
            np.testing.assert_array_equal(pixels[31:34, 2*48+1:2*48+4], 255)
        with (self.root / "results/receipt.json").open() as stream:
            self.assertEqual(json.load(stream)["expected_evaluation_views"], 1)

    def test_missing_render_is_failure_not_an_omitted_image(self):
        result = self.evaluate([])
        self.assertEqual(len(result["rows"]), 2)
        self.assertTrue(all(row["status"] == "RENDER_MISSING" for row in result["rows"]))
        self.assertTrue(all(row["psnr_native_db"] is None for row in result["rows"]))
        self.assertEqual(self.scorer.calls, [])

    def test_pose_identity_mismatch_is_not_repaired_by_filename(self):
        self.record["image_id"] = 92
        result = self.evaluate([self.record])
        self.assertTrue(all(row["status"] == "RENDER_POSE_IDENTITY_MISMATCH" for row in result["rows"]))
        self.assertEqual(self.scorer.calls, [])

    def test_shape_mismatch_is_not_resized_to_match(self):
        Image.fromarray(self.render[:20]).save(self.root / "render.png")
        self.record["render_sha256"] = quality.sha(self.root / "render.png")
        result = self.evaluate([self.record])
        self.assertTrue(all(row["status"] == "RGB_SHAPE_MISMATCH" for row in result["rows"]))

    def test_cannot_overwrite_result_or_montage(self):
        self.evaluate([self.record])
        with self.assertRaises(FileExistsError):
            self.evaluate([self.record])
        target = self.root / "fixture.png"
        quality.write_montage(self.photo, self.render, target)
        with self.assertRaises(FileExistsError):
            quality.write_montage(self.photo, self.render, target)


@unittest.skipUnless(os.environ.get("JBGS_GEOGS_SOURCE_ROOT") and os.environ.get("JBGS_METRIC_WEIGHTS_ROOT"),
                     "Exact official code/cache mounts required for metric parity checks")
class NativeMetricParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        torch.set_num_threads(4)
        cls.scorer = quality.NativeMetrics(os.environ["JBGS_GEOGS_SOURCE_ROOT"], os.environ["JBGS_METRIC_WEIGHTS_ROOT"],
                                          device="cpu", signed_lpips=True)

    def test_identical_image_and_known_constant_psnr(self):
        empty = np.zeros((32, 32, 3), dtype=np.uint8)
        identical = self.scorer.score(empty, empty)
        self.assertTrue(identical["psnr_positive_infinity"])
        self.assertIsNone(identical["psnr_native_db"])
        self.assertAlmostEqual(identical["ssim_native"], 1.0, places=6)
        self.assertAlmostEqual(identical["lpips_vgg_native_01"], 0.0, places=7)
        self.assertAlmostEqual(identical["lpips_vgg_signed_11"], 0.0, places=7)
        shifted = self.scorer.score(empty, np.full_like(empty, 128))
        self.assertAlmostEqual(shifted["psnr_native_db"], 20*np.log10(255/128), places=5)

    def test_small_domain_reports_lpips_unassessed_but_keeps_psnr_ssim(self):
        fixture = np.zeros((31, 40, 3), dtype=np.uint8)
        result = self.scorer.score(fixture, fixture)
        self.assertEqual(result["lpips_status"], "NOT_ASSESSED_DOMAIN_SIDE_LT_32")
        self.assertIsNone(result["lpips_vgg_native_01"])
        self.assertAlmostEqual(result["ssim_native"], 1.0, places=6)

    def test_cached_criterion_matches_upstream_function_on_zero_one_inputs(self):
        torch = self.scorer.torch
        random = np.random.default_rng(10)
        photo = random.integers(0, 256, size=(32, 32, 3), dtype=np.uint8)
        render = np.roll(photo, 1, axis=1)
        result = self.scorer.score(photo, render)
        reference = torch.from_numpy(np.ascontiguousarray(photo.transpose(2, 0, 1))).float().unsqueeze(0)/255
        prediction = torch.from_numpy(np.ascontiguousarray(render.transpose(2, 0, 1))).float().unsqueeze(0)/255
        with torch.inference_mode():
            direct = self.scorer.native_lpips_function(prediction, reference, net_type="vgg").item()
        self.assertAlmostEqual(result["lpips_vgg_native_01"], direct, places=7)


if __name__ == "__main__":
    unittest.main()

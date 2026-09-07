import unittest
import hashlib
import json
from pathlib import Path
import tempfile
import numpy as np
from scipy.spatial import cKDTree
from scripts.phd.wu_vallet_regions_v4.evaluate_regions import membership, median_grid, measure, summary, validate_update, stream_reference


class RegionalEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.domain = dict(bbox_min=[0., 0., -5.], bbox_max=[2., 2., 5.])
        self.cfg = dict(xy_cell_m=.5, workers=1, distance_thresholds_m=[.1, .5, 1., 2.])

    def metric(self, prediction, reference):
        h, c = median_grid(reference, self.domain, .5)
        return measure(prediction, reference, cKDTree(reference), h, c, self.domain, self.cfg)[0]

    def test_half_open_prism_does_not_include_upper_face(self):
        xyz = np.array([[0, 0, -5], [2, 1, 0], [1, 2, 0], [1, 1, 5], [1, 1, -5.001]])
        np.testing.assert_array_equal(membership(xyz, self.domain), [1, 0, 0, 0, 0])

    def test_representable_last_cell_is_retained(self):
        xyz = np.array([[np.nextafter(2., 0.), np.nextafter(2., 0.), 0.]])
        _, count = median_grid(xyz, self.domain, .5)
        self.assertEqual(count[-1, -1], 1)
        self.assertEqual(count.sum(), 1)

    def test_nonfinite_and_outside_are_not_silently_discarded(self):
        for xyz in (np.array([[0., 0., np.nan]]), np.array([[2., 0., 0.]])):
            with self.assertRaises(ValueError):
                median_grid(xyz, self.domain, .5)

    def test_missing_geometry_cannot_improve_both_directions(self):
        ref = np.array([[.1, .1, 0.], [1.1, .1, 0.]])
        result = self.metric(ref[:1], ref)
        self.assertEqual(result["to_reference"]["mean_m"], 0.)
        self.assertEqual(result["reference_to"]["mean_m"], .5)
        self.assertEqual(result["coverage"]["precision"][0], 1.)
        self.assertEqual(result["coverage"]["recall"][0], .5)
        self.assertEqual(result["xy_cells"]["missed_reference_cells"], 1)

    def test_outlying_native_points_remain_in_metric_denominator(self):
        ref = np.array([[.1, .1, 0.]])
        pred = np.array([[.1, .1, 0.], [.1, .1, 4.]])
        result = self.metric(pred, ref)
        self.assertEqual(result["point_count"], 2)
        self.assertEqual(result["to_reference"]["mean_m"], 2.)
        self.assertEqual(result["coverage"]["precision"][0], .5)

    def test_empty_prediction_reports_zero_coverage_and_missing_reference(self):
        ref = np.array([[.1, .1, 0.]])
        result = self.metric(np.empty((0, 3)), ref)
        self.assertEqual(result["coverage"]["recall"], [0.] * 4)
        self.assertEqual(result["reference_distance_unavailable_count"], 1)
        self.assertIsNone(result["reference_to"]["mean_m"])
        self.assertEqual(result["xy_cells"]["missed_reference_cells"], 1)

    def test_height_uses_all_layers_median_and_signed_difference(self):
        xyz = np.array([[.1, .1, -2.], [.1, .1, 0.], [.1, .1, 4.]])
        h, c = median_grid(xyz, self.domain, .5)
        self.assertEqual(h[0, 0], 0.)
        self.assertEqual(c[0, 0], 3)
        self.assertEqual(summary(np.array([-2., 1.]), signed=True)["mean_m"], -.5)

    def test_update_requires_exact_source_order_and_coordinates(self):
        common = dict(old_xyz=np.array([[0., 0., 0.]]), new_xyz=np.array([[1., 0., 0.]]), new_pixel_id=np.array([9]))
        payload = dict(old_keep_mask=np.array([True]), new_keep_mask=np.array([True]),
                       updated_points=np.array([[0., 0., 0.], [1., 0., 0.]]), updated_source=np.array([0, 1]),
                       updated_pixel_id=np.array([-1, 9]))
        np.testing.assert_array_equal(validate_update(common, payload), payload["updated_points"])
        payload["updated_points"][1, 0] = 1.01
        with self.assertRaises(ValueError):
            validate_update(common, payload)

    def test_frozen_reference_reuse_does_not_open_raw_laz(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evaluation.json"
            path.write_text(json.dumps(dict(outputs={"reference.npz": "frozen_hash"}, domain=self.domain,
                                           reference_crs_header="EPSG:32632")))
            cfg = dict(raw_reference={"path": "/definitely/not/a/raw_reference.laz"},
                       frozen_reference_metadata=dict(source_evaluation_json=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()),
                       regions=[dict(domain=self.domain, frozen_reference_sha256="frozen_hash")])
            data, receipt = stream_reference(cfg, [])
            self.assertEqual(data, {})
            self.assertEqual(receipt["decompressed_passes"], 0)
            self.assertFalse(receipt["raw_reference_accessed"])

    def test_frozen_reference_reuse_requires_bound_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evaluation.json"
            path.write_text(json.dumps(dict(outputs={"reference.npz": "original"}, domain=self.domain,
                                           reference_crs_header="EPSG:32632")))
            cfg = dict(frozen_reference_metadata=dict(source_evaluation_json=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()),
                       regions=[dict(domain=self.domain, frozen_reference_sha256="different")])
            with self.assertRaises(ValueError):
                stream_reference(cfg, [])

    def test_each_visible_region_uses_its_own_frozen_reference_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = dict(frozen_reference_metadata={}, regions=[])
            for index in (1, 2):
                rid = f"P{index}_visible"
                domain = dict(bbox_min=[float(index), 0., -5.], bbox_max=[float(index + 1), 2., 5.])
                path = Path(directory) / f"{rid}.json"
                path.write_text(json.dumps(dict(outputs={"reference.npz": f"hash{index}"}, domain=domain,
                                               reference_crs_header="EPSG:32632")))
                cfg["frozen_reference_metadata"][rid] = dict(source_evaluation_json=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                cfg["regions"].append(dict(id=rid, domain=domain, frozen_reference_sha256=f"hash{index}"))
            _, receipt = stream_reference(cfg, [])
            self.assertEqual([r["id"] for r in receipt["sources"]], ["P1_visible", "P2_visible"])
            cfg["regions"][1]["frozen_reference_sha256"] = "hash1"
            with self.assertRaises(ValueError):
                stream_reference(cfg, [])


if __name__ == "__main__":
    unittest.main()

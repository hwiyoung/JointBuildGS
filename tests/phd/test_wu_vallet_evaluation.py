"""Numerical safeguards for P3 post-training evaluation, with synthetic inputs."""
import struct
from types import SimpleNamespace
import unittest

import numpy as np
from scipy.spatial import cKDTree

from scripts.phd.wu_vallet_p3_v1 import evaluate as ev


def evaluate_points(prediction, reference):
    height, count = ev.median_grid(reference)
    return ev.measure(prediction, reference, cKDTree(reference), height, count)


class WuValletEvaluationTests(unittest.TestCase):
    def test_large_discrepancy_remains_in_both_direction_denominators(self):
        reference = np.array([[-50., -30., -40.]])
        prediction = np.array([[-50., -30., -17.]])
        result, _ = evaluate_points(prediction, reference)
        distances = result["native_3d_nearest_distances"]
        for direction in ("prediction_to_reference", "reference_to_prediction"):
            self.assertEqual(distances[direction]["count"], 1)
            self.assertEqual(distances[direction]["max_abs_m"], 23.)
            self.assertEqual(distances[direction]["rmse_m"], 23.)
        for threshold in distances["within_distance"]:
            self.assertEqual(threshold["prediction_denominator"], 1)
            self.assertEqual(threshold["reference_denominator"], 1)
            self.assertEqual(threshold["prediction_numerator"], 0)
            self.assertEqual(threshold["reference_numerator"], 0)
        self.assertEqual(result["xy_height_grid"]["signed_height_difference_prediction_minus_reference"]["mean_m"], 23.)

    def test_missing_prediction_cells_stay_in_fixed_and_reference_accounting(self):
        reference = np.array([[-59.75, -41.75, -40.], [-58.75, -41.75, -40.]])
        result, fields = evaluate_points(reference[:1], reference)
        grid = result["xy_height_grid"]
        self.assertEqual(grid["fixed_domain_cells"], 8640)
        self.assertEqual(grid["prediction_occupied_cells"], 1)
        self.assertEqual(grid["prediction_missing_fixed_domain_cells"], 8639)
        self.assertEqual(grid["reference_occupied_cells"], 2)
        self.assertEqual(grid["matched_reference_cells"], 1)
        self.assertEqual(grid["missing_prediction_on_reference_cells"], 1)
        self.assertEqual(grid["prediction_coverage_reference_cells"], .5)
        self.assertEqual(grid["signed_height_difference_prediction_minus_reference"]["count"], 1)
        self.assertTrue(np.isnan(fields["delta_z"][0, 2]))
        distances = result["native_3d_nearest_distances"]
        self.assertEqual(distances["reference_to_prediction"]["count"], 2)
        self.assertEqual(distances["reference_to_prediction"]["max_abs_m"], 1.)

    def test_empty_prediction_has_missing_reference_without_fabricated_zero_error(self):
        reference = np.array([[-50., -30., -40.]])
        result, _ = evaluate_points(np.empty((0, 3)), reference)
        distances = result["native_3d_nearest_distances"]
        self.assertEqual(distances["reference_distance_unavailable_points"], 1)
        self.assertIsNone(distances["reference_to_prediction"]["rmse_m"])
        self.assertIsNone(distances["symmetric_mean_distance_m"])
        self.assertEqual(result["xy_height_grid"]["missing_prediction_on_reference_cells"], 1)
        self.assertEqual(result["xy_height_grid"]["prediction_missing_fixed_domain_cells"], 8640)
        for threshold in distances["within_distance"]:
            self.assertEqual(threshold["reference_denominator"], 1)
            self.assertEqual(threshold["reference_numerator"], 0)

    def test_native_self_identity_has_zero_discrepancy_and_full_reference_coverage(self):
        points = np.array([[-59.75, -41.75, -40.], [-59.70, -41.70, -39.], [-58.75, -41.75, -42.]])
        result, _ = evaluate_points(points, points)
        for direction in ("prediction_to_reference", "reference_to_prediction"):
            metric = result["native_3d_nearest_distances"][direction]
            self.assertEqual(metric["count"], 3)
            self.assertEqual(metric["rmse_m"], 0.)
        grid = result["xy_height_grid"]
        self.assertEqual(grid["prediction_coverage_reference_cells"], 1.)
        self.assertEqual(grid["signed_height_difference_prediction_minus_reference"]["count"], 2)
        self.assertEqual(grid["signed_height_difference_prediction_minus_reference"]["rmse_m"], 0.)

    def test_surface_crop_is_half_open_on_each_axis_and_preserves_last_grid_cell(self):
        middle = (ev.LOW + ev.HIGH) / 2
        points = [ev.LOW.copy(), np.nextafter(ev.HIGH, ev.LOW)]
        for axis in range(3):
            point = middle.copy()
            point[axis] = ev.HIGH[axis]
            points.append(point)
            point = middle.copy()
            point[axis] = np.nextafter(ev.LOW[axis], -np.inf)
            points.append(point)
        cropped, counts = ev.crop(np.array(points))
        self.assertEqual(counts, {"input_points": 8, "inside_fixed_crop": 2, "outside_fixed_crop": 6})
        np.testing.assert_array_equal(cropped, points[:2])
        _, grid_counts = ev.median_grid(cropped)
        self.assertEqual(grid_counts.sum(), 2)
        self.assertEqual(grid_counts[0, 0], 1)
        self.assertEqual(grid_counts[-1, -1], 1)
        with self.assertRaises(ValueError):
            ev.median_grid(np.array([ev.HIGH]))

    def test_header_geokey_reading_does_not_require_pyproj_or_infer_vertical_datum(self):
        payload = struct.pack("<12H", 1, 1, 0, 2, 3072, 0, 1, 25832, 2048, 0, 1, 4258)
        vlr = SimpleNamespace(user_id="LASF_Projection", record_id=34735, record_data_bytes=lambda: payload)
        # No parse_crs method exists on this stand-in; the direct reader must not call one.
        header = SimpleNamespace(vlrs=[vlr], evlrs=None)
        metadata = ev.header_crs_metadata(header)
        self.assertEqual(metadata["header_crs"], "EPSG:25832")
        self.assertEqual(metadata["header_geokey_scalars"], {"3072": 25832, "2048": 4258})
        self.assertFalse(metadata["header_vertical_datum_calibrated"])
        self.assertEqual(metadata["header_projection_vlrs"][0]["bytes"], len(payload))

    def test_header_missing_geokeys_is_explicitly_unknown(self):
        metadata = ev.header_crs_metadata(SimpleNamespace(vlrs=[], evlrs=None))
        self.assertIsNone(metadata["header_crs"])
        self.assertEqual(metadata["header_geokey_scalars"], {})
        self.assertFalse(metadata["header_vertical_datum_calibrated"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import replace
import json
import unittest

import numpy as np

from src.phd.wu_vallet_p3_v2.trajectory import (
    ROLE, TrajectoryConfig, fit_trajectory_window, json_safe, predict_origins,
)


def synthetic_pulses(count=240, noise=0., seed=31):
    rng = np.random.default_rng(seed)
    time = 330021090. + np.linspace(-.5, .5, count)
    sensor = np.array([690900., 5336000., 1200.])[None] + (time - 330021090.)[:, None] * [40., 6., -.4]
    direction = np.column_stack((rng.uniform(-.45, .45, count), rng.uniform(-.2, .2, count), -np.ones(count)))
    direction /= np.linalg.norm(direction, axis=1, keepdims=True)
    ranges = rng.uniform(450, 650, count)
    separation = rng.uniform(5, 25, count)
    first = sensor + ranges[:, None] * direction
    last = first + separation[:, None] * direction
    first += rng.normal(0., noise, first.shape)
    last += rng.normal(0., noise, last.shape)
    return time, first, last, sensor


class EstimatedTrajectoryTest(unittest.TestCase):
    def setUp(self):
        self.config = TrajectoryConfig(
            min_return_separation_m=2., separation_weight_cap_m=50., min_train_pulses=30,
            min_holdout_pulses=10, holdout_every=5, max_condition_number=1000., robust_line_scale_m=1.,
            robust_endpoint_scale_m=.02, max_holdout_line_p90_m=2., max_holdout_endpoint_p90_m=.05,
            min_sensor_range_m=50., max_sensor_range_m=3000., min_forward_fraction=.99,
            max_speed_m_per_s=150., bootstrap_repetitions=8, max_bootstrap_origin_p95_m=3., random_seed=7,
        )

    def fit(self, data=None, config=None):
        if data is None:
            data = synthetic_pulses()
        return fit_trajectory_window(*data[:3], config or self.config, strip_id="31")

    def test_exact_linear_origin_recovered_with_large_global_coordinates_and_gps(self):
        data = synthetic_pulses()
        fit = self.fit(data)
        self.assertTrue(fit["accepted"], fit["rejection_reasons"])
        ids = fit["holdout_validated_input_rows"]
        np.testing.assert_allclose(predict_origins(fit, data[0][ids]), data[3][ids], atol=2e-6, rtol=0)
        np.testing.assert_allclose(fit["velocity_m_per_s"], [40., 6., -.4], atol=2e-6, rtol=0)
        self.assertEqual(fit["role"], ROLE)
        self.assertFalse(fit["native_Wu_Vallet_reproduction"])
        self.assertIsNone(fit["scientific_verdict"])

    def test_quantized_scale_noise_has_measured_holdout_and_bootstrap_uncertainty(self):
        data = synthetic_pulses(count=600, noise=.005)
        fit = self.fit(data)
        self.assertTrue(fit["accepted"], fit["rejection_reasons"])
        self.assertGreater(fit["holdout"]["endpoint_to_predicted_ray_m"]["p90"], 0.)
        self.assertGreater(fit["bootstrap"]["max_probe_origin_displacement_p95_m"], 0.)
        ids = fit["holdout_validated_input_rows"]
        self.assertLess(np.linalg.norm(predict_origins(fit, data[0][ids]) - data[3][ids], axis=1).max(), .5)

    def test_parallel_beams_reject_unidentifiable_sensor_range(self):
        time, first, last, _ = synthetic_pulses()
        sensor = np.column_stack((40. * (time-time[0]), np.zeros(len(time)), np.full(len(time), 500.)))
        first = sensor + [0., 0., -500.]
        last = first + [0., 0., -10.]
        fit = self.fit((time, first, last))
        self.assertFalse(fit["accepted"])
        self.assertIn("rank_deficient_beam_time_geometry", fit["rejection_reasons"])
        with self.assertRaisesRegex(ValueError, "accepted"):
            predict_origins(fit, time)

    def test_narrow_angles_reject_condition_even_with_exact_lines(self):
        time, first, last, sensor = synthetic_pulses()
        direction = last-first
        direction[:, :2] *= 1e-8
        direction /= np.linalg.norm(direction, axis=1, keepdims=True)
        fit = self.fit((time, sensor+500.*direction, sensor+510.*direction))
        self.assertFalse(fit["accepted"])
        self.assertIn("ill_conditioned_reverse_fit", fit["rejection_reasons"])

    def test_reversed_returns_do_not_move_sensor_to_wrong_side(self):
        time, first, last, _ = synthetic_pulses()
        fit = self.fit((time, last, first))
        self.assertFalse(fit["accepted"])
        self.assertIn("sensor_not_before_first_return_or_outside_declared_range", fit["rejection_reasons"])

    def test_holdout_corruption_does_not_refit_training_solution(self):
        time, first, last, _ = synthetic_pulses()
        altered_first, altered_last = first.copy(), last.copy()
        holdout = np.arange(len(time)) % self.config.holdout_every == self.config.holdout_every - 1
        altered_first[holdout, 0] += 50.
        altered_last[holdout, 0] += 50.
        baseline = self.fit((time, first, last))
        corrupted = self.fit((time, altered_first, altered_last))
        self.assertFalse(corrupted["accepted"])
        self.assertIn("holdout_line_residual_exceeded", corrupted["rejection_reasons"])
        np.testing.assert_array_equal(baseline["position_at_time_origin"], corrupted["position_at_time_origin"])
        self.assertEqual(set(baseline["train_input_rows"]) & set(baseline["holdout_input_rows"]), set())

    def test_extrapolation_fails_even_for_accepted_fit(self):
        fit = self.fit()
        lower, upper = fit["support_gps_time_s"]
        with self.assertRaisesRegex(ValueError, "extrapolation prohibited"):
            predict_origins(fit, np.array([lower-1e-5]))
        with self.assertRaisesRegex(ValueError, "extrapolation prohibited"):
            predict_origins(fit, np.array([upper+1e-5]))
        self.assertEqual(predict_origins(fit, np.array([lower, upper])).shape, (2, 3))

    def test_short_return_separation_and_insufficient_data_rejected(self):
        time, first, last, _ = synthetic_pulses(count=20)
        fit = self.fit((time, first, first+.001*(last-first)))
        self.assertFalse(fit["accepted"])
        self.assertEqual(fit["short_or_zero_separation_rejected"], 20)
        self.assertIn("insufficient_train_or_holdout_pulses", fit["rejection_reasons"])

    def test_mixed_strip_duplicate_times_cannot_be_silently_fit(self):
        time, first, last, _ = synthetic_pulses()
        time[1] = time[0]
        with self.assertRaisesRegex(ValueError, "separate flight strips"):
            self.fit((time, first, last))

    def test_order_independence_and_weighted_reverse_alternative(self):
        time, first, last, _ = synthetic_pulses()
        config = replace(self.config, objective="weighted_reverse_line")
        fit = self.fit((time, first, last), config=config)
        reverse = self.fit((time[::-1], first[::-1], last[::-1]), config=config)
        self.assertTrue(fit["accepted"])
        self.assertTrue(reverse["accepted"])
        np.testing.assert_allclose(fit["position_at_time_origin"], reverse["position_at_time_origin"], atol=1e-9)

    def test_rejected_fit_has_standard_json_without_nan_or_infinity(self):
        result = json_safe({"array": np.array([np.nan, np.inf]), "value": np.int64(3)})
        self.assertEqual(json.dumps(result, allow_nan=False), '{"array": [null, null], "value": 3}')

    def test_missing_explicit_thresholds_and_nonfinite_inputs_fail(self):
        with self.assertRaises(TypeError):
            TrajectoryConfig()
        with self.assertRaises(ValueError):
            replace(self.config, min_return_separation_m=-1.)
        data = list(synthetic_pulses())
        data[0][2] = np.nan
        with self.assertRaisesRegex(ValueError, "finite"):
            self.fit(data)


if __name__ == "__main__":
    unittest.main()

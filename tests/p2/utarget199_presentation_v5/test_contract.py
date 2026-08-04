from __future__ import annotations

import unittest

import numpy as np

from scripts.p2.utarget199_presentation_v5.render import (
    _point_triangle_z,
    load_config,
    validate_config,
)


class UTarget199PresentationV5Test(unittest.TestCase):
    def test_config_keeps_verdicts_null_and_c5_not_run(self) -> None:
        config = load_config()
        validate_config(config)
        self.assertIsNone(config["scientific_verdict"])
        self.assertIsNone(config["official_G3_G4_PASS_usable"])
        self.assertEqual(config["presentation"]["c5_missing_state"], "NOT_RUN")

    def test_triangle_interpolation(self) -> None:
        triangle = np.asarray([[0.0, 0.0, 10.0], [2.0, 0.0, 12.0], [0.0, 2.0, 14.0]])
        self.assertAlmostEqual(_point_triangle_z(0.5, 0.5, triangle), 11.5)
        self.assertIsNone(_point_triangle_z(3.0, 3.0, triangle))

    def test_exact_hashes_are_frozen(self) -> None:
        config = load_config()
        self.assertEqual(config["exact_hashes"]["building_method_metrics_v1.jsonl"], "13728f8e56ddfa502fea9d6345bb38b29931737f8e33d73d40b1b3b8171f6c8e")
        self.assertEqual(config["exact_hashes"]["building_acceptance_gates_v1.csv"], "f99f931ffde7943f65cabcdd682ee03ec00fe095945af6e5e609342ace748bd3")


if __name__ == "__main__":
    unittest.main()

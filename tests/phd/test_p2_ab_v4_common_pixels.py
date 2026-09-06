import unittest
import numpy as np

from scripts.phd.p2_ab_v4.build_qualitative_viewer import pixel_metrics


class CommonPixelTests(unittest.TestCase):
    def test_missing_prediction_stays_in_fixed_denominator(self):
        target = np.full((1, 2, 3), 255, dtype=np.uint8)
        prediction = target.copy()
        prediction[0, 1] = 0
        result = pixel_metrics(prediction, target, np.ones((1, 2), bool), np.array([[1., 0.]]))
        self.assertEqual(result["pixels"], 2)
        self.assertEqual(result["mae"], .5)
        self.assertEqual(result["geometry_present_fraction"], .5)

    def test_pixel_support_and_geometry_mass_are_separate(self):
        image = np.zeros((2, 2, 3), dtype=np.uint8)
        mask = np.array([[True, False], [False, True]])
        result = pixel_metrics(image, image, mask, np.zeros((2, 2)))
        self.assertEqual(result["mae"], 0.)
        self.assertEqual(result["pixels"], 2)
        self.assertEqual(result["geometry_present_pixels"], 0)
        with self.assertRaisesRegex(ValueError, "unaligned"):
            pixel_metrics(image, image, mask[:1], np.zeros((2, 2)))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Unit tests for the shared, datum-explicit image projection path."""
from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.stage2.colmap_io import Camera, Image, read_cameras_bin, read_images_bin
from src.stage2.image_projection import (
    ELLIPSOIDAL,
    ORTHOMETRIC,
    ProjectionError,
    base_to_canonical,
    canonical_to_base,
    in_frame_mask,
    project_base_points,
    project_camera_points,
    project_canonical_points,
)


def _identity_image(camera_id: int = 1) -> Image:
    return Image(
        id=1,
        qvec=np.array([1.0, 0.0, 0.0, 0.0]),
        tvec=np.zeros(3, dtype=np.float64),
        camera_id=camera_id,
        name="frame.jpg",
    )


def _pinhole_camera(camera_id: int = 1) -> Camera:
    return Camera(
        id=camera_id,
        model="PINHOLE",
        width=100,
        height=80,
        params=np.array([10.0, 20.0, 50.0, 40.0]),
    )


class DatumConversionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scene = {
            "base_to_canonical": {
                "shift": [0.0, 0.0, -604.0],
                "scale": [1.0, 1.0, 1.0],
                "swap_xy": False,
            }
        }

    def test_input_datum_is_mandatory(self) -> None:
        with self.assertRaises(TypeError):
            base_to_canonical(np.array([[0.0, 0.0, 605.0]]), self.scene)
        with self.assertRaises(TypeError):
            project_base_points(
                np.array([[0.0, 0.0, 605.0]]),
                _identity_image(),
                _pinhole_camera(),
                self.scene,
            )

    def test_orthometric_round_trip_and_ellipsoidal_output(self) -> None:
        base_orthometric = np.array([[690000.0, 5336000.0, 514.0]])
        canonical = base_to_canonical(
            base_orthometric,
            self.scene,
            input_datum=ORTHOMETRIC,
            geoid_m=45.7,
        )
        np.testing.assert_allclose(canonical, [[690000.0, 5336000.0, -44.3]])

        recovered_orthometric = canonical_to_base(
            canonical,
            self.scene,
            output_datum=ORTHOMETRIC,
            geoid_m=45.7,
        )
        recovered_ellipsoidal = canonical_to_base(
            canonical,
            self.scene,
            output_datum=ELLIPSOIDAL,
            geoid_m=45.7,
        )
        np.testing.assert_allclose(recovered_orthometric, base_orthometric)
        np.testing.assert_allclose(
            recovered_ellipsoidal, [[690000.0, 5336000.0, 559.7]]
        )

    def test_base_projection_applies_geoid_once_and_returns_depth(self) -> None:
        result = project_base_points(
            np.array([[0.0, 0.0, 560.0]]),
            _identity_image(),
            _pinhole_camera(),
            self.scene,
            input_datum=ORTHOMETRIC,
            geoid_m=45.7,
        )
        np.testing.assert_allclose(result.depth, [1.7])
        np.testing.assert_allclose(result.uv, [[50.0, 40.0]])
        np.testing.assert_array_equal(result.valid, [True])

    def test_missing_scene_transform_fields_fail_closed(self) -> None:
        with self.assertRaisesRegex(ProjectionError, "missing explicit fields"):
            base_to_canonical(
                np.array([[1.0, 2.0, 3.0]]),
                {},
                input_datum=ELLIPSOIDAL,
            )

    def test_zero_or_nonfinite_scene_scale_fails_closed(self) -> None:
        for scale in ([1.0, 1.0, 0.0], [1.0, np.inf, 1.0]):
            with self.subTest(scale=scale), self.assertRaisesRegex(
                ProjectionError, "scale must"
            ):
                canonical_to_base(
                    np.array([[1.0, 2.0, 3.0]]),
                    {
                        "shift": [0.0, 0.0, 0.0],
                        "scale": scale,
                        "swap_xy": False,
                    },
                    output_datum=ELLIPSOIDAL,
                )

    def test_nonfinite_base_input_fails_closed_before_conversion(self) -> None:
        with self.assertRaisesRegex(ProjectionError, "only finite"):
            base_to_canonical(
                np.array([[1.0, 2.0, np.nan]]),
                self.scene,
                input_datum=ELLIPSOIDAL,
            )


class CameraProjectionTests(unittest.TestCase):
    def test_depth_validity_and_pixels_are_returned_together(self) -> None:
        points = np.array(
            [
                [0.0, 0.0, 2.0],
                [2.0, 1.0, 2.0],
                [0.0, 0.0, 0.5],
                [np.nan, 0.0, 2.0],
            ]
        )
        result = project_canonical_points(
            points,
            _identity_image(),
            _pinhole_camera(),
            min_depth_m=1.0,
        )
        np.testing.assert_allclose(result.depth[:3], [2.0, 2.0, 0.5])
        self.assertTrue(np.isnan(result.depth[3]))
        np.testing.assert_allclose(result.uv[:2], [[50.0, 40.0], [60.0, 50.0]])
        self.assertTrue(np.all(np.isnan(result.uv[2:])))
        np.testing.assert_array_equal(result.valid, [True, True, False, False])

    def test_supported_colmap_models_match_when_distortion_is_zero(self) -> None:
        models = {
            "SIMPLE_PINHOLE": [100.0, 50.0, 40.0],
            "PINHOLE": [100.0, 110.0, 50.0, 40.0],
            "SIMPLE_RADIAL": [100.0, 50.0, 40.0, 0.0],
            "RADIAL": [100.0, 50.0, 40.0, 0.0, 0.0],
            "OPENCV": [100.0, 110.0, 50.0, 40.0, 0.0, 0.0, 0.0, 0.0],
            "FULL_OPENCV": [
                100.0,
                110.0,
                50.0,
                40.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
            ],
        }
        point = np.array([[1.0, 2.0, 10.0]])
        for model, params in models.items():
            with self.subTest(model=model):
                camera = Camera(1, model, 100, 80, np.asarray(params))
                result = project_camera_points(camera, point, min_depth_m=0.1)
                expected_y = 60.0 if model in {"SIMPLE_PINHOLE", "SIMPLE_RADIAL", "RADIAL"} else 62.0
                np.testing.assert_allclose(result.uv, [[60.0, expected_y]])
                np.testing.assert_allclose(result.depth, [10.0])
                np.testing.assert_array_equal(result.valid, [True])

    def test_full_opencv_singular_denominator_fails_closed(self) -> None:
        camera = Camera(
            1,
            "FULL_OPENCV",
            100,
            80,
            np.array(
                [100.0, 100.0, 50.0, 40.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0]
            ),
        )
        with self.assertRaisesRegex(ProjectionError, "denominator is singular"):
            project_camera_points(camera, np.array([[1.0, 0.0, 1.0]]), min_depth_m=0.1)

    def test_unsupported_camera_model_fails_closed(self) -> None:
        camera = Camera(1, "FOV", 100, 80, np.ones(5))
        with self.assertRaisesRegex(ProjectionError, "unsupported COLMAP camera model"):
            project_camera_points(camera, np.array([[0.0, 0.0, 2.0]]))

    def test_in_frame_is_separate_from_projection_validity(self) -> None:
        result = project_camera_points(
            _pinhole_camera(),
            np.array([[0.0, 0.0, 2.0], [10.0, 0.0, 2.0]]),
        )
        np.testing.assert_array_equal(result.valid, [True, True])
        np.testing.assert_array_equal(in_frame_mask(result, _pinhole_camera()), [True, False])


class BinaryColmapCompatibilityTests(unittest.TestCase):
    def test_objects_loaded_from_colmap_binary_project_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            camera_path = root / "cameras.bin"
            image_path = root / "images.bin"

            with open(camera_path, "wb") as stream:
                stream.write(struct.pack("<Q", 1))
                stream.write(struct.pack("<iiQQ", 7, 1, 100, 80))
                stream.write(struct.pack("<dddd", 10.0, 20.0, 50.0, 40.0))
            with open(image_path, "wb") as stream:
                stream.write(struct.pack("<Q", 1))
                stream.write(struct.pack("<I", 9))
                stream.write(struct.pack("<dddd", 1.0, 0.0, 0.0, 0.0))
                stream.write(struct.pack("<ddd", 0.0, 0.0, 0.0))
                stream.write(struct.pack("<I", 7))
                stream.write(b"frame.jpg\x00")
                stream.write(struct.pack("<Q", 0))

            camera = read_cameras_bin(camera_path)[7]
            image = read_images_bin(image_path)[9]
            result = project_canonical_points(
                np.array([[2.0, 1.0, 2.0]]), image, camera
            )
            np.testing.assert_allclose(result.uv, [[60.0, 50.0]])
            np.testing.assert_allclose(result.depth, [2.0])
            np.testing.assert_array_equal(result.valid, [True])


if __name__ == "__main__":
    unittest.main(verbosity=2)

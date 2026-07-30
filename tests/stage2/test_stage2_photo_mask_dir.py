#!/usr/bin/env python3
"""Focused tests for the non-pilot per-view photo-support mask input."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from src.stage2.colmap_io import Camera, Image
from src.stage2.pilot_scene_prep import (
    write_cameras_bin,
    write_images_bin,
    write_points3d_bin,
)
from src.stage2.dataloader import ColmapDataset


def _synthetic_dataset(root: Path) -> None:
    sparse = root / "sparse/0"
    camera = Camera(
        id=1,
        model="SIMPLE_PINHOLE",
        width=10,
        height=8,
        params=np.asarray([8.0, 5.0, 4.0]),
    )
    image = Image(
        id=7,
        qvec=np.asarray([1.0, 0.0, 0.0, 0.0]),
        tvec=np.zeros(3),
        camera_id=1,
        name="view.jpg",
    )
    write_cameras_bin(sparse / "cameras.bin", {1: camera})
    write_images_bin(sparse / "images.bin", {7: image})
    write_points3d_bin(
        sparse / "points3D.bin",
        np.asarray([[0.0, 0.0, 10.0, 100, 120, 140]], dtype=np.float64),
    )
    (root / "images").mkdir(parents=True)
    PILImage.fromarray(np.full((8, 10, 3), 127, dtype=np.uint8)).save(
        root / "images/view.jpg"
    )


class PhotoMaskDirTest(unittest.TestCase):
    def test_bool_mask_is_bound_to_the_exact_visible_view(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _synthetic_dataset(root)
            masks = root / "photo_support_masks"
            masks.mkdir()
            mask = np.zeros((8, 10), dtype=np.bool_)
            mask[2:6, 3:8] = True
            np.save(masks / "view.npy", mask, allow_pickle=False)

            dataset = ColmapDataset(
                root,
                load_depth=False,
                load_normal=False,
                photo_mask_dir="photo_support_masks",
            )
            batch = dataset[0]
            np.testing.assert_array_equal(batch["photo_mask"].numpy(), mask)
            self.assertEqual(
                dataset.photo_mask_dir_audit["inventory_match"],
                "exact_visible_view_coverage",
            )

    def test_missing_empty_and_nonbool_masks_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _synthetic_dataset(root)
            masks = root / "photo_support_masks"
            masks.mkdir()
            with self.assertRaisesRegex(FileNotFoundError, "misses visible views"):
                ColmapDataset(
                    root,
                    load_depth=False,
                    load_normal=False,
                    photo_mask_dir=masks,
                )

            np.save(masks / "view.npy", np.zeros((8, 10), dtype=np.bool_))
            dataset = ColmapDataset(
                root,
                load_depth=False,
                load_normal=False,
                photo_mask_dir=masks,
            )
            with self.assertRaisesRegex(ValueError, "empty"):
                dataset[0]

            np.save(masks / "view.npy", np.ones((8, 10), dtype=np.uint8))
            dataset = ColmapDataset(
                root,
                load_depth=False,
                load_normal=False,
                photo_mask_dir=masks,
            )
            with self.assertRaisesRegex(ValueError, "bool HxW"):
                dataset[0]

    def test_pilot_manifest_and_directory_cannot_both_be_configured(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _synthetic_dataset(root)
            with self.assertRaisesRegex(ValueError, "mutually exclusive"):
                ColmapDataset(
                    root,
                    load_depth=False,
                    load_normal=False,
                    photo_mask_manifest=root / "pilot.json",
                    photo_mask_dir=root / "photo_support_masks",
                )


if __name__ == "__main__":
    unittest.main()

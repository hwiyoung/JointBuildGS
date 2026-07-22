#!/usr/bin/env python3
"""Ensure MVS and Omnidata normals remain two independent data channels."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.stage2.dataloader import ColmapDataset, Frame


class PilotDualNormalChannelsTest(unittest.TestCase):
    def test_world_npy_loader_does_not_overwrite_primary_frame_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mvs_path = root / "mvs.npy"
            mono_path = root / "mono.npy"
            mvs = np.zeros((3, 4, 3), dtype=np.float32)
            mono = np.zeros((3, 4, 3), dtype=np.float32)
            mvs[..., 2] = 1.0
            mono[..., 0] = 1.0
            np.save(mvs_path, mvs)
            np.save(mono_path, mono)

            frame = Frame(
                image_id=1,
                name="view.jpg",
                cam_id=1,
                image_path=root / "view.jpg",
                depth_path=None,
                normal_path=mvs_path,
                mono_normal_path=mono_path,
                mono_depth_path=None,
                depth_format=None,
                normal_format="npy_world",
                mono_normal_format="npy_world",
                mono_depth_format=None,
                K=np.eye(3),
                R=np.eye(3),
                t=np.zeros(3),
                width=4,
                height=3,
            )
            dataset = ColmapDataset.__new__(ColmapDataset)
            dataset.normal_encoding = "raw"
            primary, primary_mask = dataset._load_normal(frame, 3, 4)
            auxiliary, auxiliary_mask = dataset._load_mono_normal(frame, 3, 4)

            np.testing.assert_array_equal(primary, mvs)
            np.testing.assert_array_equal(auxiliary, mono)
            self.assertTrue(primary_mask.all())
            self.assertTrue(auxiliary_mask.all())
            self.assertEqual(frame.normal_path, mvs_path)
            self.assertEqual(frame.mono_normal_path, mono_path)

    def test_missing_auxiliary_channel_is_explicitly_none(self) -> None:
        dataset = ColmapDataset.__new__(ColmapDataset)
        dataset.mono_normal_dir = None
        self.assertEqual(dataset._find_mono_normal("view.jpg"), (None, None))


if __name__ == "__main__":
    unittest.main()

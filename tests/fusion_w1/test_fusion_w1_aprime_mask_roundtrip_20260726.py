#!/usr/bin/env python3
"""Dataloader roundtrip gate for the A-prime exact roof mask M_j."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image as PILImage


REPO = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_preprocess_20260726.py"
)
SPEC = importlib.util.spec_from_file_location(
    "fusion_w1_aprime_preprocess_mask_roundtrip", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
prep = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prep
SPEC.loader.exec_module(prep)

from src.stage2.colmap_io import Camera, Image  # noqa: E402
from src.stage2.dataloader import ColmapDataset  # noqa: E402


class FakeGate:
    @staticmethod
    def project_camera_points(
        camera: Camera, camera_xyz: np.ndarray
    ) -> np.ndarray:
        xyz = np.asarray(camera_xyz, dtype=np.float64)
        focal, cx, cy = camera.params
        return np.column_stack(
            [
                focal * xyz[:, 0] / xyz[:, 2] + cx,
                focal * xyz[:, 1] / xyz[:, 2] + cy,
            ]
        )


class ExactMaskRoundtripTest(unittest.TestCase):
    def test_saved_depth_normal_and_photo_masks_equal_native_M_j(self) -> None:
        camera = Camera(
            id=1,
            model="SIMPLE_PINHOLE",
            width=64,
            height=64,
            params=np.asarray([40.0, 32.0, 32.0]),
        )
        image = Image(
            id=1,
            qvec=np.asarray([1.0, 0.0, 0.0, 0.0]),
            tvec=np.zeros(3, dtype=np.float64),
            camera_id=1,
            name="view_01.png",
        )
        view = prep.V1.SelectedView(
            selection_order=1,
            image=image,
            camera=camera,
            class6_inframe_n=9,
            class6_visible_n=9,
            frame_radius=0.0,
            nadir_deg=0.0,
            azimuth_bin=0,
        )
        points = np.asarray(
            [
                [-1.0, -1.0, 10.0],
                [0.0, -1.0, 10.0],
                [1.0, -1.0, 10.0],
                [-1.0, 0.0, 10.0],
                [0.0, 0.0, 10.0],
                [1.0, 0.0, 10.0],
                [-1.0, 1.0, 10.0],
                [0.0, 1.0, 10.0],
                [1.0, 1.0, 10.0],
            ],
            dtype=np.float64,
        )
        tin = prep.V1.build_tin(
            points,
            maximum_xy_edge_m=3.0,
            maximum_slope_deg=75.0,
            minimum_xy_triangle_area_m2=0.005,
        )
        rendered = prep.render_roof_supervision(
            FakeGate(),
            tin,
            view,
            {
                "screen_barycentric_edge_margin": 0.02,
                "outer_valid_mask_erosion_px": 1,
                "invalid_depth": 0.0,
            },
        )
        expected = rendered["valid_M_j"]
        self.assertGreater(int(expected.sum()), 0)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "images").mkdir(parents=True)
            PILImage.fromarray(
                np.zeros((camera.height, camera.width, 3), dtype=np.uint8)
            ).save(root / "images" / image.name)
            sparse = root / "sparse" / "0"
            prep.V1.write_cameras_bin(sparse / "cameras.bin", {1: camera})
            prep.V1.write_images_bin(sparse / "images.bin", {1: image})
            prep.V1.write_points3d_bin(
                sparse / "points3D.bin",
                np.asarray(
                    [[0.0, 0.0, 10.0, 128.0, 128.0, 128.0]],
                    dtype=np.float64,
                ),
            )
            prep.V1.write_colmap_array(
                root
                / "stereo"
                / "depth_maps"
                / f"{image.name}.geometric.bin",
                rendered["depth_camera_z_m"],
            )
            prep.V1.write_colmap_array(
                root
                / "stereo"
                / "normal_maps"
                / f"{image.name}.geometric.bin",
                rendered["normal_camera"],
            )
            prep.V1.atomic_npy(
                root / "photo_support_masks" / f"{Path(image.name).stem}.npy",
                expected,
            )
            dataset = ColmapDataset(
                root,
                downscale=1.0,
                load_depth=True,
                load_normal=True,
                load_semantic=False,
                visible_views=[image.name],
                photo_mask_dir=root / "photo_support_masks",
            )
            item = dataset[0]

        self.assertTrue(np.array_equal(item["depth_mask"].numpy(), expected))
        self.assertTrue(np.array_equal(item["normal_mask"].numpy(), expected))
        self.assertTrue(np.array_equal(item["photo_mask"].numpy(), expected))


if __name__ == "__main__":
    unittest.main(verbosity=2)

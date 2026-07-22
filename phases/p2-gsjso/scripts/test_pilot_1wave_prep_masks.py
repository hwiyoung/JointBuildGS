#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch
from PIL import Image as PILImage
from shapely.geometry import Polygon

from src.stage2.colmap_io import Camera, Image
from src.stage2.colmap_io import read_array, read_cameras_bin
from src.stage2 import pilot_mask_schema as schema
from src.stage2.pilot_scene_prep import (
    HeightEstimate,
    ViewCrop,
    WORLD_SHIFT,
    derive_sfm_mvs_footprint_heights,
    materialize_scene_crop,
    rasterize_photo_support_mask,
    write_cameras_bin,
    write_colmap_array,
    write_images_bin,
    write_points3d_bin,
)


def digest(value: str) -> str:
    return schema.sha256_bytes(value.encode("utf-8"))


class BinaryMaskSchemaTests(unittest.TestCase):
    def test_schema_roundtrip_and_photo_consumer_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "set"
            masks = {
                "view_b.jpg": np.asarray([[False, True], [True, False]], dtype=bool),
                "view_a.jpg": np.asarray([[True, False], [False, False]], dtype=bool),
            }
            manifest = schema.write_binary_mask_set(
                root,
                masks,
                purpose=schema.MaskPurpose.PHOTO_SUPPORT,
                source=schema.MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
                source_disclosure="GT-derived GroundSurface XY plus dense-MVS height",
                input_sha256=digest("inputs"),
                config_sha256=digest("config"),
                geometry_sha256_by_view={key: digest(key) for key in masks},
            )
            loaded = schema.BinaryMaskSet(manifest)
            self.assertEqual(loaded.purpose, schema.MaskPurpose.PHOTO_SUPPORT)
            self.assertEqual(
                loaded.consumer_arms, schema.PHOTO_SUPPORT_CONSUMER_ARMS
            )
            np.testing.assert_array_equal(loaded.load("view_a.jpg"), masks["view_a.jpg"])
            self.assertFalse(any(root.rglob("*.tmp")))
            self.assertEqual([*loaded.records], sorted(masks))

    def test_plane_region_contracts_are_not_shared_with_photo_arms(self) -> None:
        cases = (
            (
                schema.MaskSource.VISION_GROUNDEDSAM_ROOF,
                ("04a_plane_medium_vision",),
            ),
            (
                schema.MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND,
                ("04b_plane_medium_gt_upperbound",),
            ),
        )
        for source, expected_consumers in cases:
            with self.subTest(source=source.value), tempfile.TemporaryDirectory() as directory:
                manifest = schema.write_binary_mask_set(
                    Path(directory) / "set",
                    {"view.jpg": np.ones((2, 3), dtype=bool)},
                    purpose=schema.MaskPurpose.PLANE_REGION,
                    source=source,
                    source_disclosure="test disclosure",
                    input_sha256=digest("input"),
                    config_sha256=digest("config"),
                    geometry_sha256_by_view={"view.jpg": digest("geometry")},
                )
                loaded = schema.BinaryMaskSet(manifest)
                self.assertEqual(loaded.consumer_arms, expected_consumers)

    def test_mono_gate_has_its_own_all_condition_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = schema.write_binary_mask_set(
                Path(directory) / "set",
                {"view.jpg": np.ones((2, 3), dtype=bool)},
                purpose=schema.MaskPurpose.MONO_GATE,
                source=schema.MaskSource.OMNIDATA_MVS_NORMAL_ANGLE_GATE,
                source_disclosure="Omnidata auxiliary compared with primary MVS normal",
                input_sha256=digest("input"),
                config_sha256=digest("config"),
                geometry_sha256_by_view={"view.jpg": digest("geometry")},
            )
            loaded = schema.BinaryMaskSet(manifest)
            self.assertEqual(loaded.consumer_arms, schema.MONO_GATE_CONSUMER_ARMS)

    def test_forbidden_gt_numeric_array_is_rejected_even_with_matching_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "set"
            manifest_path = schema.write_binary_mask_set(
                root,
                {"view.jpg": np.ones((2, 3), dtype=bool)},
                purpose=schema.MaskPurpose.PHOTO_SUPPORT,
                source=schema.MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
                source_disclosure="test disclosure",
                input_sha256=digest("input"),
                config_sha256=digest("config"),
                geometry_sha256_by_view={"view.jpg": digest("geometry")},
            )
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            record_payload = payload["records"][0]
            mask_path = root / record_payload["file"]
            mask_path.chmod(0o644)
            np.savez(
                mask_path,
                mask=np.ones((2, 3), dtype=bool),
                lod2_z=np.asarray([612.5], dtype=np.float64),
            )
            record_payload["mask_sha256"] = schema.sha256_file(mask_path)
            record = schema.MaskRecord(
                view_id=record_payload["view_id"],
                shape=tuple(record_payload["shape"]),
                file=record_payload["file"],
                mask_sha256=record_payload["mask_sha256"],
                input_sha256=record_payload["input_sha256"],
                config_sha256=record_payload["config_sha256"],
                geometry_sha256=record_payload["geometry_sha256"],
            )
            payload["inventory_sha256"] = schema._inventory_sha256(
                [record],
                schema.MaskPurpose.PHOTO_SUPPORT,
                schema.MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
                schema.PHOTO_SUPPORT_CONSUMER_ARMS,
            )
            manifest_path.chmod(0o644)
            manifest_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            loaded = schema.BinaryMaskSet(manifest_path)
            with self.assertRaisesRegex(schema.MaskSchemaError, "extra numeric arrays"):
                loaded.load("view.jpg")

    def test_empty_mask_and_wrong_purpose_source_pair_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(schema.MaskSchemaError, "empty projected mask"):
                schema.write_binary_mask_set(
                    Path(directory) / "empty",
                    {"view.jpg": np.zeros((2, 2), dtype=bool)},
                    purpose=schema.MaskPurpose.PHOTO_SUPPORT,
                    source=schema.MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
                    source_disclosure="test",
                    input_sha256=digest("input"),
                    config_sha256=digest("config"),
                    geometry_sha256_by_view={"view.jpg": digest("geometry")},
                )
            with self.assertRaisesRegex(schema.MaskSchemaError, "unsupported purpose/source"):
                schema.write_binary_mask_set(
                    Path(directory) / "bad_pair",
                    {"view.jpg": np.ones((2, 2), dtype=bool)},
                    purpose=schema.MaskPurpose.PHOTO_SUPPORT,
                    source=schema.MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND,
                    source_disclosure="test",
                    input_sha256=digest("input"),
                    config_sha256=digest("config"),
                    geometry_sha256_by_view={"view.jpg": digest("geometry")},
                )

    def test_masked_l1_is_invariant_to_outside_pixel_mutation(self) -> None:
        prediction = torch.tensor(
            [
                [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
                [[0.7, 0.8, 0.9], [0.2, 0.4, 0.6]],
            ],
            dtype=torch.float32,
        )
        target = torch.zeros_like(prediction)
        mask = torch.tensor([[True, False], [False, True]], dtype=torch.bool)
        baseline = schema.masked_l1(prediction, target, mask)
        mutated_prediction = prediction.clone()
        mutated_target = target.clone()
        mutated_prediction[~mask] = 1_000_000.0
        mutated_target[~mask] = -1_000_000.0
        mutated = schema.masked_l1(mutated_prediction, mutated_target, mask)
        self.assertTrue(torch.equal(baseline, mutated))


class FootprintProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.building_id = "DEBY_LOD2_TEST"
        self.footprint = Polygon(
            [
                (WORLD_SHIFT[0] - 2.0, WORLD_SHIFT[1] - 2.0),
                (WORLD_SHIFT[0] + 2.0, WORLD_SHIFT[1] - 2.0),
                (WORLD_SHIFT[0] + 2.0, WORLD_SHIFT[1] + 2.0),
                (WORLD_SHIFT[0] - 2.0, WORLD_SHIFT[1] + 2.0),
            ]
        )
        self.camera = Camera(
            id=1,
            model="SIMPLE_PINHOLE",
            width=100,
            height=100,
            params=np.asarray([50.0, 50.0, 50.0]),
        )
        self.image = Image(
            id=1,
            qvec=np.asarray([1.0, 0.0, 0.0, 0.0]),
            tvec=np.zeros(3),
            camera_id=1,
            name="view.jpg",
        )

    def test_height_is_derived_from_dense_mvs_points_and_mask_is_nonempty(self) -> None:
        grid = np.asarray(
            [
                [x, y, 8.0 + 0.1 * index]
                for index, (x, y) in enumerate(
                    ([(x, y) for x in np.linspace(-1.5, 1.5, 5) for y in np.linspace(-1.5, 1.5, 5)])
                )
            ],
            dtype=np.float64,
        )
        heights = derive_sfm_mvs_footprint_heights(
            {self.building_id: self.footprint}, grid
        )
        self.assertEqual(heights[self.building_id].seed_point_count, 25)
        mask, audit = rasterize_photo_support_mask(
            100,
            100,
            self.image,
            self.camera,
            {self.building_id: self.footprint},
            heights,
        )
        self.assertTrue(mask.dtype == np.bool_)
        self.assertGreater(int(mask.sum()), 0)
        self.assertEqual(audit["visible_selected_building_count"], 1)

    def test_empty_projection_is_hard_failure(self) -> None:
        height = HeightEstimate(
            building_id=self.building_id,
            local_z_m=-10.0,
            seed_point_count=20,
            upper_quantile=0.8,
            upper_point_count=4,
        )
        with self.assertRaisesRegex(RuntimeError, "empty footprint"):
            rasterize_photo_support_mask(
                100,
                100,
                self.image,
                self.camera,
                {self.building_id: self.footprint},
                {self.building_id: height},
            )


class SceneMaterializationTests(unittest.TestCase):
    def test_rgb_sfm_and_both_mvs_map_kinds_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            sparse = source / "sparse/0"
            output = root / "output/data"
            camera = Camera(
                id=1,
                model="SIMPLE_PINHOLE",
                width=10,
                height=10,
                params=np.asarray([8.0, 5.0, 5.0]),
            )
            image = Image(
                id=7,
                qvec=np.asarray([1.0, 0.0, 0.0, 0.0]),
                tvec=np.zeros(3),
                camera_id=1,
                name="synthetic.jpg",
            )
            write_cameras_bin(sparse / "cameras.bin", {1: camera})
            write_images_bin(sparse / "images.bin", {7: image})
            points = np.asarray(
                [
                    [float(index % 3), float(index // 3), 10.0, 10, 20, 30]
                    for index in range(12)
                ]
            )
            write_points3d_bin(sparse / "points3D.bin", points)
            (source / "images").mkdir(parents=True)
            PILImage.fromarray(np.full((10, 10, 3), 127, dtype=np.uint8)).save(
                source / "images/synthetic.jpg"
            )
            depth = np.arange(25, dtype=np.float32).reshape(5, 5) + 1.0
            normal = np.dstack(
                [np.zeros((5, 5)), np.zeros((5, 5)), np.ones((5, 5))]
            ).astype(np.float32)
            for suffix in ("geometric", "photometric"):
                write_colmap_array(
                    source / f"stereo/depth_maps/synthetic.jpg.{suffix}.bin",
                    depth,
                )
                write_colmap_array(
                    source / f"stereo/normal_maps/synthetic.jpg.{suffix}.bin",
                    normal,
                )
            stats = materialize_scene_crop(
                source,
                sparse,
                output,
                [ViewCrop(7, "synthetic.jpg", 1, (2, 2, 8, 8), 1)],
                [
                    WORLD_SHIFT[0] - 1.0,
                    WORLD_SHIFT[1] - 1.0,
                    WORLD_SHIFT[0] + 5.0,
                    WORLD_SHIFT[1] + 5.0,
                ],
            )
            self.assertEqual(
                stats["mvs_map_counts"],
                {
                    "depth_geometric": 1,
                    "depth_photometric": 1,
                    "normal_geometric": 1,
                    "normal_photometric": 1,
                },
            )
            self.assertFalse((output / "semantic").exists())
            cropped_camera = read_cameras_bin(output / "sparse/0/cameras.bin")[7]
            self.assertEqual((cropped_camera.width, cropped_camera.height), (6, 6))
            self.assertEqual(
                read_array(
                    output / "stereo/depth_maps/synthetic.jpg.geometric.bin"
                ).shape,
                (3, 3),
            )
            self.assertEqual(
                read_array(
                    output / "stereo/normal_maps/synthetic.jpg.photometric.bin"
                ).shape,
                (3, 3, 3),
            )


if __name__ == "__main__":
    unittest.main()

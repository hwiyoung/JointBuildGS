#!/usr/bin/env python3
"""Synthetic unit tests for FUS-W1 section-3 preprocessing."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image as PILImage


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_preprocess_v1_20260725.py"
SPEC = importlib.util.spec_from_file_location("fusion_w1_preprocess_tested", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
prep = importlib.util.module_from_spec(SPEC)
import sys

sys.modules[SPEC.name] = prep
SPEC.loader.exec_module(prep)

from src.stage2.colmap_io import Camera, Image, read_array, read_images_bin


class FakeGate:
    @staticmethod
    def project_camera_points(camera: Camera, camera_xyz: np.ndarray) -> np.ndarray:
        xyz = np.asarray(camera_xyz, dtype=np.float64)
        f, cx, cy = camera.params
        return np.column_stack(
            [
                f * xyz[:, 0] / xyz[:, 2] + cx,
                f * xyz[:, 1] / xyz[:, 2] + cy,
            ]
        )


def camera() -> Camera:
    return Camera(
        id=1,
        model="SIMPLE_PINHOLE",
        width=64,
        height=64,
        params=np.asarray([40.0, 32.0, 32.0]),
    )


def image(name: str = "synthetic.png") -> Image:
    return Image(
        id=1,
        qvec=np.asarray([1.0, 0.0, 0.0, 0.0]),
        tvec=np.zeros(3, dtype=np.float64),
        camera_id=1,
        name=name,
    )


class GeometryTests(unittest.TestCase):
    def test_polygon_buffer_membership_is_metric_and_includes_interior(self) -> None:
        ring = np.asarray(
            [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], dtype=np.float64
        )
        points = np.asarray(
            [[5, 5], [10.5, 5], [11.1, 5], [-0.7, -0.7]], dtype=np.float64
        )
        observed = prep.points_within_polygon_buffer(points, ring, 1.0)
        self.assertEqual(observed.tolist(), [True, True, False, True])

    def test_visibility_zbuffer_keeps_surface_tolerance_only(self) -> None:
        uv = np.asarray([[10.2, 10.4], [10.8, 10.1], [20.0, 20.0]])
        depth = np.asarray([10.0, 10.3, 12.0])
        observed = prep.visibility_mask(uv, depth, 64, 64, 0.15)
        self.assertEqual(observed.tolist(), [True, False, True])

    def test_tin_masks_long_edges_and_rasterizes_camera_z(self) -> None:
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
                [20.0, 20.0, 10.0],
            ],
            dtype=np.float64,
        )
        tin = prep.build_tin(
            points,
            maximum_xy_edge_m=2.0,
            maximum_slope_deg=5.0,
            minimum_xy_triangle_area_m2=0.01,
        )
        self.assertGreater(tin.stats["triangles_valid_n"], 0)
        self.assertGreater(tin.stats["triangles_dropped_long_edge_n"], 0)
        depth, normal, valid, stats = prep.rasterize_tin(
            FakeGate(),
            tin,
            image(),
            camera(),
            edge_margin=0.0,
            erosion_pixels=1,
        )
        self.assertGreater(int(valid.sum()), 0)
        self.assertTrue(np.allclose(depth[valid], 10.0, atol=1.0e-5))
        self.assertTrue(np.allclose(normal[valid, 2], 1.0, atol=1.0e-6))
        self.assertGreater(stats["outer_edge_masked_pixels_n"], 0)

    def test_steep_tin_is_rejected(self) -> None:
        points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 10.0],
                [0.0, 1.0, 10.0],
                [1.0, 1.0, 20.0],
            ]
        )
        with self.assertRaises(prep.PreprocessError):
            prep.build_tin(
                points,
                maximum_xy_edge_m=2.0,
                maximum_slope_deg=20.0,
                minimum_xy_triangle_area_m2=0.01,
            )

    def test_screen_rasterizer_handles_overlap_flip_and_degenerate(self) -> None:
        # The first two triangles project to exactly the same footprint. The
        # near triangle is deliberately flipped, while the last triangle is
        # non-degenerate in 3D but edge-on and degenerate after projection.
        vertices = np.asarray(
            [
                [-1.0, -1.0, 5.0],
                [1.0, -1.0, 5.0],
                [0.0, 1.0, 5.0],
                [-2.0, -2.0, 10.0],
                [2.0, -2.0, 10.0],
                [0.0, 2.0, 10.0],
                [3.0, 0.0, 5.0],
                [4.0, 0.0, 5.0],
                [6.0, 0.0, 10.0],
            ],
            dtype=np.float64,
        )
        tin = prep.Tin(
            vertices=vertices,
            simplices=np.asarray(
                [[3, 4, 5], [0, 2, 1], [6, 7, 8]], dtype=np.int64
            ),
            normals_world=np.asarray(
                [[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]],
                dtype=np.float64,
            ),
            stats={},
        )
        previous_chunk_limit = prep.SCREEN_RASTER_MAX_BBOX_SAMPLES
        prep.SCREEN_RASTER_MAX_BBOX_SAMPLES = 100
        try:
            first = prep.rasterize_tin(
                FakeGate(),
                tin,
                image(),
                camera(),
                edge_margin=0.0,
                erosion_pixels=0,
            )
            second = prep.rasterize_tin(
                FakeGate(),
                tin,
                image(),
                camera(),
                edge_margin=0.0,
                erosion_pixels=0,
            )
        finally:
            prep.SCREEN_RASTER_MAX_BBOX_SAMPLES = previous_chunk_limit
        depth, normal, valid, stats = first
        self.assertTrue(valid[32, 32])
        self.assertAlmostEqual(float(depth[32, 32]), 5.0, places=6)
        self.assertEqual(normal[32, 32].tolist(), [0.0, 0.0, 1.0])
        self.assertEqual(stats["triangles_screen_degenerate_n"], 1)
        self.assertEqual(stats["triangles_projected_n"], 2)
        self.assertEqual(stats["raster_chunks_n"], 2)
        self.assertGreater(
            stats["candidate_pixel_writes_n"],
            stats["valid_pixels_before_outer_edge_mask_n"],
        )
        for observed, repeated in zip(first[:3], second[:3]):
            self.assertTrue(np.array_equal(observed, repeated))
        self.assertEqual(first[3], second[3])

    def test_screen_rasterizer_keeps_pixel_center_boundary_sliver(self) -> None:
        # This triangle only reaches the frame through the final pixel centre
        # x=63.5. A vertex-domain [0,width-1] overlap test drops it incorrectly.
        projected_uv = np.asarray(
            [[63.4, 31.4], [64.2, 32.0], [63.4, 32.6]], dtype=np.float64
        )
        z = 10.0
        vertices = np.column_stack(
            [
                (projected_uv[:, 0] - 32.0) * z / 40.0,
                (projected_uv[:, 1] - 32.0) * z / 40.0,
                np.full(3, z),
            ]
        )
        tin = prep.Tin(
            vertices=vertices,
            simplices=np.asarray([[0, 1, 2]], dtype=np.int64),
            normals_world=np.asarray([[0.0, 0.0, 1.0]], dtype=np.float64),
            stats={},
        )
        depth, _normal, valid, stats = prep.rasterize_tin(
            FakeGate(), tin, image(), camera(), edge_margin=0.0, erosion_pixels=0
        )
        self.assertTrue(valid[32, 63])
        self.assertAlmostEqual(float(depth[32, 63]), z, places=6)
        self.assertEqual(stats["triangles_screen_offframe_n"], 0)

    def test_combined_supervision_selects_nearest_class(self) -> None:
        depth6 = np.asarray([[5.0, 0.0], [8.0, 0.0]], dtype=np.float32)
        depth2 = np.asarray([[7.0, 6.0], [4.0, 0.0]], dtype=np.float32)
        valid6 = depth6 > 0
        valid2 = depth2 > 0
        normal6 = np.zeros((2, 2, 3), dtype=np.float32)
        normal2 = np.zeros((2, 2, 3), dtype=np.float32)
        normal6[..., 2] = 1
        normal2[..., 1] = 1
        depth, normal, valid, source = prep.combine_supervision(
            depth6, normal6, valid6, depth2, normal2, valid2
        )
        self.assertEqual(source.tolist(), [[6, 2], [2, 0]])
        self.assertEqual(depth.tolist(), [[5.0, 6.0], [4.0, 0.0]])
        self.assertEqual(valid.tolist(), [[True, True], [True, False]])
        self.assertEqual(normal[0, 0].tolist(), [0.0, 0.0, 1.0])

    def test_photo_support_is_target_footprint_not_buffered_ground(self) -> None:
        ring = np.asarray(
            [
                [-1.0, -1.0],
                [1.0, -1.0],
                [1.0, 1.0],
                [-1.0, 1.0],
                [-1.0, -1.0],
            ]
        )
        roof = np.asarray(
            [
                [-1.0, -1.0, 10.0],
                [1.0, -1.0, 10.0],
                [1.0, 1.0, 10.0],
                [-1.0, 1.0, 10.0],
            ]
        )
        mask, audit = prep.rasterize_target_photo_support_mask(
            FakeGate(),
            ring,
            roof,
            image(),
            camera(),
            {
                "base_to_canonical": {
                    "shift": [0, 0, 0],
                    "scale": [1, 1, 1],
                }
            },
            {
                "base_vertical_datum": "ellipsoidal",
                "orthometric_to_ellipsoidal_geoid_m": 0.0,
            },
        )
        self.assertTrue(mask[32, 32])
        self.assertFalse(mask[5, 5])
        self.assertFalse(audit["buffered_class2_included"])
        self.assertFalse(audit["non_target_class6_included"])


class ArtifactTests(unittest.TestCase):
    def test_rgb_sampling_retains_occluded_unsampled_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.png"
            pixels = np.zeros((64, 64, 3), dtype=np.uint8)
            pixels[..., 0] = np.arange(64, dtype=np.uint8)[None, :]
            pixels[..., 1] = np.arange(64, dtype=np.uint8)[:, None]
            PILImage.fromarray(pixels).save(path)
            selected = [
                prep.SelectedView(
                    selection_order=1,
                    image=image(),
                    camera=camera(),
                    class6_inframe_n=2,
                    class6_visible_n=1,
                    frame_radius=0.0,
                    nadir_deg=0.0,
                    azimuth_bin=0,
                )
            ]
            points = np.asarray([[0.0, 0.0, 10.0], [0.0, 0.0, 12.0]])
            config = {
                "rgb_sampling": {
                    "zbuffer_absolute_tolerance_m": 0.15,
                    "default_unsampled_rgb": [128, 128, 128],
                    "method": "synthetic",
                }
            }
            rgb, counts, stats = prep.sample_seed_rgb(
                FakeGate(), points, selected, {"synthetic.png": path}, config
            )
            self.assertEqual(counts.tolist(), [1, 0])
            self.assertEqual(rgb[1].tolist(), [128, 128, 128])
            self.assertEqual(stats["unsampled_points_n"], 1)
            self.assertTrue(stats["unsampled_points_retained"])

    def test_deterministic_npz_is_byte_stable(self) -> None:
        arrays = {
            "z": np.asarray([3, 2, 1], dtype=np.int16),
            "a": np.eye(2, dtype=np.float32),
        }
        self.assertEqual(
            prep.deterministic_npz_bytes(arrays),
            prep.deterministic_npz_bytes(arrays),
        )

    def test_colmap_array_writer_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "map.geometric.bin"
            expected = np.arange(24, dtype=np.float32).reshape(2, 4, 3)
            prep.write_colmap_array(path, expected)
            observed = read_array(path)
            self.assertTrue(np.array_equal(observed, expected))

    def test_subset_colmap_image_inventory_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "images.bin"
            values = {
                5: Image(
                    5,
                    np.asarray([1.0, 0.0, 0.0, 0.0]),
                    np.asarray([1.0, 2.0, 3.0]),
                    1,
                    "a.JPG",
                ),
                9: Image(
                    9,
                    np.asarray([1.0, 0.0, 0.0, 0.0]),
                    np.asarray([4.0, 5.0, 6.0]),
                    1,
                    "b.JPG",
                ),
            }
            prep.write_images_bin(path, values)
            observed = read_images_bin(path)
            self.assertEqual(
                sorted(item.name for item in observed.values()),
                ["a.JPG", "b.JPG"],
            )
            self.assertTrue(np.array_equal(observed[9].tvec, values[9].tvec))

    def test_base_las_preserves_rows_classes_and_crs(self) -> None:
        import laspy

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seed.las"
            xyz = np.asarray(
                [
                    [690000.001, 5336000.002, 100.003],
                    [690001.004, 5336001.005, 101.006],
                ]
            )
            cls = np.asarray([6, 2], dtype=np.uint8)
            rgb = np.asarray([[1, 2, 3], [250, 240, 230]], dtype=np.uint8)
            stats = prep.write_seed_las(path, xyz, cls, rgb)
            observed = laspy.read(path)
            self.assertEqual(np.asarray(observed.classification).tolist(), [6, 2])
            self.assertEqual(
                np.column_stack([observed.x, observed.y, observed.z]).shape,
                xyz.shape,
            )
            self.assertLessEqual(
                stats["maximum_coordinate_roundtrip_error_m"], 0.0005001
            )
            self.assertEqual(observed.header.parse_crs().to_epsg(), 25832)

    def test_building_manifest_verifier_checks_pose_and_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "seed.bin"
            artifact.write_bytes(b"seed")
            manifest = root / "preprocess_manifest.json"
            pose = "2" * 64
            payload = {
                "schema": prep.BUILDING_SCHEMA,
                "status": "PASSED",
                "pose_binding": {"corrected_images_sha256": pose},
                "artifact_sha256": {
                    str(artifact): prep.sha256_file(artifact)
                },
                "seed": {
                    "classification_counts": {"2": 3, "6": 2},
                    "output_points_n": 5,
                    "downsample_applied": False,
                },
                "views": {
                    "selected_names": [f"v{i:02d}.JPG" for i in range(10)]
                },
            }
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            observed = prep.verify_building_manifest(manifest, pose)
            self.assertEqual(observed["seed"]["output_points_n"], 5)


class ContractTests(unittest.TestCase):
    def test_config_locks_corrected_pose_namespace_and_no_learning_scope(self) -> None:
        config = prep.load_config(
            REPO
            / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_preprocess_v1_20260725.json"
        )
        self.assertEqual(
            config["r1_contract"]["corrected_images_sha256"],
            "28b38383a0b6d82656108e8f0e5e79711dcda93948ab2e89c1cd8f47215962a5",
        )
        self.assertEqual(
            config["outputs"]["cache_namespace"], "pose_28b38383a0b6d826"
        )
        self.assertFalse(config["subset_contract"]["downsample_default"])
        self.assertIn("no_learning", config["scope"])
        self.assertTrue(config["photo_support_masks"]["enabled"])

    def test_cli_requires_exactly_one_target_scope(self) -> None:
        parser = prep.build_parser()
        parsed = parser.parse_args(["--building-id", "42364609"])
        self.assertEqual(parsed.building_id, "42364609")
        parsed = parser.parse_args(["--all-core"])
        self.assertTrue(parsed.all_core)


if __name__ == "__main__":
    unittest.main(verbosity=2)

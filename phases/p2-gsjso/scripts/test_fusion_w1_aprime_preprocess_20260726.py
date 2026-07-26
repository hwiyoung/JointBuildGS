#!/usr/bin/env python3
"""Synthetic contract tests for the A-prime P1/P2 preprocessor."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np


REPO = Path(__file__).resolve().parents[3]
SCRIPT = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1_aprime_preprocess_20260726.py"
)
SPEC = importlib.util.spec_from_file_location(
    "fusion_w1_aprime_preprocess_tested", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
prep = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prep
SPEC.loader.exec_module(prep)

from src.stage2.colmap_io import Camera, Image, read_points3d_bin  # noqa: E402


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


def image(name: str, image_id: int = 1) -> Image:
    return Image(
        id=image_id,
        qvec=np.asarray([1.0, 0.0, 0.0, 0.0]),
        tvec=np.zeros(3, dtype=np.float64),
        camera_id=1,
        name=name,
    )


def selected_views(count: int) -> list[object]:
    return [
        prep.V1.SelectedView(
            selection_order=index,
            image=image(f"view_{index:02d}.png", index),
            camera=camera(),
            class6_inframe_n=4,
            class6_visible_n=4,
            frame_radius=0.0,
            nadir_deg=0.0,
            azimuth_bin=0,
        )
        for index in range(1, count + 1)
    ]


def overlapping_tin() -> object:
    # Two parallel triangles cover the same camera ray.  The z=5 triangle is
    # the genuine first intersection and must occlude the z=10 triangle.
    vertices = np.asarray(
        [
            [-2.0, -2.0, 5.0],
            [2.0, -2.0, 5.0],
            [0.0, 2.0, 5.0],
            [-4.0, -4.0, 10.0],
            [4.0, -4.0, 10.0],
            [0.0, 4.0, 10.0],
        ],
        dtype=np.float64,
    )
    return prep.V1.Tin(
        vertices=vertices,
        simplices=np.asarray([[3, 4, 5], [0, 1, 2]], dtype=np.int64),
        normals_world=np.asarray(
            [[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]], dtype=np.float64
        ),
        stats={"source_points_n": 6, "triangles_valid_n": 2},
    )


class RayGeometryTests(unittest.TestCase):
    def test_first_intersection_is_nearest_triangle_not_point_zbuffer(self) -> None:
        observed = prep.first_ray_tin_intersection_distances(
            np.zeros(3),
            np.asarray([[0.0, 0.0, 2.0], [0.1, 0.0, 1.0]]),
            overlapping_tin(),
            ray_chunk_size=1,
            triangle_chunk_size=1,
        )
        self.assertAlmostEqual(float(observed[0]), 5.0, places=10)
        self.assertTrue(np.isfinite(observed[1]))
        self.assertLess(float(observed[1]), 10.0)

    def test_epsilon_occlusion_and_k3_votes_are_strict(self) -> None:
        points = np.asarray(
            [
                [0.0, 0.0, 5.0],
                [0.0, 0.0, 10.0],
                [0.0, 0.0, 5.049],
                [0.0, 0.0, 5.051],
            ],
            dtype=np.float64,
        )
        cfg = {
            "epsilon_m": 0.05,
            "minimum_views_k": 3,
            "ray_chunk_size": 2,
            "triangle_chunk_size": 1,
            "intersection_parallel_epsilon": 1.0e-10,
            "intersection_barycentric_epsilon": 1.0e-9,
            "minimum_positive_hit_distance_m": 1.0e-6,
        }
        votes, matrix, rows, histogram = prep.raycast_seed_visibility(
            FakeGate(), points, overlapping_tin(), selected_views(3), cfg
        )
        self.assertEqual(votes.tolist(), [3, 0, 3, 0])
        self.assertEqual(matrix[:, 0].tolist(), [1, 0, 1, 0])
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(not row["point_zbuffer_used"] for row in rows))
        self.assertEqual(histogram["0"], 2)
        self.assertEqual(histogram["3"], 2)

        two_votes, _matrix, _rows, _histogram = prep.raycast_seed_visibility(
            FakeGate(), points[:1], overlapping_tin(), selected_views(2), cfg
        )
        self.assertEqual(two_votes.tolist(), [2])
        self.assertFalse(bool((two_votes >= cfg["minimum_views_k"])[0]))

    def test_parallel_and_miss_rays_return_infinity(self) -> None:
        observed = prep.first_ray_tin_intersection_distances(
            np.zeros(3),
            np.asarray([[1.0, 0.0, 0.0], [1.0, 1.0, 0.1]]),
            overlapping_tin(),
        )
        self.assertTrue(np.isinf(observed).all())


class MaskTests(unittest.TestCase):
    def test_roof_mask_is_exact_for_depth_normal_and_photo(self) -> None:
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
        view = selected_views(1)[0]
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
        mask = rendered["valid_M_j"]
        self.assertGreater(int(mask.sum()), 0)
        self.assertTrue(np.array_equal(mask, rendered["photo_mask"]))
        self.assertTrue(np.all(rendered["depth_camera_z_m"][mask] > 0.0))
        self.assertTrue(np.all(rendered["depth_camera_z_m"][~mask] == 0.0))
        self.assertTrue(np.all(rendered["normal_world"][~mask] == 0.0))
        fraction = float(mask.sum() / (camera().width * camera().height))
        self.assertGreater(fraction, 0.0)
        self.assertLess(fraction, 1.0)
        self.assertGreater(rendered["stats"]["outer_edge_masked_pixels_n"], 0)

class ArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = prep.load_config(
            REPO
            / "phases/p2-gsjso/configs/fusion_w1_aprime_preprocess_20260726.json"
        )

    def test_training_bundle_has_class6_only_and_no_sfm_or_ground_rows(self) -> None:
        canonical = np.asarray(
            [[0.0, 0.0, 10.0], [1.0, 1.0, 11.0]], dtype=np.float64
        )
        base = np.asarray(
            [
                [690953.0, 5336071.0, 560.0],
                [690954.0, 5336072.0, 561.0],
            ],
            dtype=np.float64,
        )
        rgb = np.asarray([[10, 20, 30], [40, 50, 60]], dtype=np.uint8)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stats = prep.write_training_seed_bundle(
                root,
                self.config,
                canonical,
                base,
                rgb,
                np.asarray([3, 4], dtype=np.uint16),
                np.asarray([3, 5], dtype=np.uint16),
            )
            self.assertEqual(stats["classification_counts"], {"6": 2})
            self.assertEqual(stats["class2_rows_n"], 0)
            self.assertEqual(stats["sfm_rows_n"], 0)
            seed_path = root / self.config["outputs"]["canonical_seed_npz"]
            with np.load(seed_path, allow_pickle=False) as seed:
                self.assertEqual(seed["classification"].tolist(), [6, 6])
                self.assertTrue(np.allclose(seed["init_opacity"], 0.1))
                self.assertEqual(seed["visibility_votes"].tolist(), [3, 5])
            points = read_points3d_bin(root / "sparse/0/points3D.bin")
            self.assertEqual(len(points), 2)
            self.assertTrue(np.allclose(points[:, :3], canonical))

    def test_ground_bundle_is_separate_class2_readout_artifact(self) -> None:
        base = np.asarray(
            [
                [690950.0, 5336070.0, 550.0],
                [690951.0, 5336071.0, 550.1],
            ],
            dtype=np.float64,
        )
        canonical = base - np.asarray([690953.0, 5336071.0, 550.0])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stats = prep.write_ground_bundle(root, self.config, base, canonical)
            self.assertEqual(stats["classification_counts"], {"2": 2})
            self.assertFalse(stats["trainer_path_reference"])
            ground_path = root / self.config["outputs"]["ground_base_npz"]
            with np.load(ground_path, allow_pickle=False) as ground:
                self.assertTrue(np.array_equal(ground["xyz_epsg25832_orthometric"], base))
                self.assertEqual(ground["classification"].tolist(), [2, 2])
            self.assertFalse((root / "sparse/0/points3D.bin").exists())
            self.assertTrue(stats["coordinate_rows_unaltered"])
            self.assertFalse(stats["source_row_order_preserved"])


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config_path = (
            REPO
            / "phases/p2-gsjso/configs/fusion_w1_aprime_preprocess_20260726.json"
        )
        self.config = prep.load_config(self.config_path)

    def test_config_locks_pose_seed_mask_and_new_cache(self) -> None:
        self.assertEqual(
            self.config["r1_contract"]["corrected_images_sha256"],
            prep.CORRECTED_IMAGES_SHA256,
        )
        self.assertEqual(self.config["subset_contract"]["training_classes"], [6])
        self.assertEqual(self.config["visibility_filter"]["minimum_views_k"], 3)
        self.assertEqual(self.config["visibility_filter"]["epsilon_m"], 0.05)
        self.assertEqual(self.config["tin_supervision"]["photo_mask"], "exact_M_j")
        self.assertFalse(self.config["tin_supervision"]["ground_supervision"])
        self.assertEqual(
            self.config["view_selection"]["role_policy"],
            "all_selected_views_are_training_views_no_holdout",
        )
        self.assertEqual(
            self.config["data_root_contract"]["training_downscale_required"],
            1.0,
        )
        self.assertIn("aprime", self.config["outputs"]["cache_namespace"])
        self.assertNotEqual(
            self.config["outputs"]["cache_namespace"], "pose_28b38383a0b6d826"
        )

    def test_nine_targets_are_machine_joined_to_canonical_csv(self) -> None:
        targets = prep.load_aprime_targets(
            prep.repo_path(self.config["inputs"]["aprime_targets_csv"]),
            prep.repo_path(self.config["inputs"]["canonical_targets_csv"]),
            self.config,
        )
        self.assertEqual(len(targets), 9)
        self.assertEqual([target.aprime_order for target in targets], list(range(1, 10)))
        self.assertEqual(sum(target.target_role == "dim_failure" for target in targets), 8)
        self.assertEqual(sum(target.target_role == "textured_control" for target in targets), 1)

    def test_locked_target_and_helper_hashes_are_current(self) -> None:
        for logical in (
            self.config["inputs"]["aprime_targets_csv"],
            self.config["inputs"]["aprime_targets_manifest"],
            self.config["inputs"]["v1_helper_script"],
        ):
            self.assertEqual(
                prep.V1.sha256_file(prep.repo_path(logical)),
                self.config["input_sha256"][logical],
            )

    def test_committed_method_contract_includes_docker_wrapper(self) -> None:
        wrapper = (
            "phases/p2-gsjso/scripts/"
            "run_fusion_w1_aprime_preprocess_20260726.sh"
        )
        self.assertIn(wrapper, self.config["implementation_files"])
        self.assertTrue(prep.repo_path(wrapper).is_file())

    def test_cli_requires_exactly_one_target_scope(self) -> None:
        parser = prep.build_parser()
        self.assertEqual(parser.parse_args(["--building-id", "42364609"]).building_id, "42364609")
        self.assertTrue(parser.parse_args(["--all-aprime"]).all_aprime)


if __name__ == "__main__":
    unittest.main(verbosity=2)

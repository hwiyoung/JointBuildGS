#!/usr/bin/env python3
"""Docker unit tests for the arm A-prime real TSDF read-out."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch


SCRIPT = Path(__file__).with_name("fusion_w1_aprime_tsdf_20260726.py")
SPEC = importlib.util.spec_from_file_location("aprime_tsdf", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)
SOURCE = SCRIPT.read_text(encoding="utf-8")
WRAPPER = SCRIPT.with_name("run_fusion_w1_aprime_t2_20260726.sh").read_text(
    encoding="utf-8"
)


class AprimeTsdfTests(unittest.TestCase):
    def test_locked_config(self) -> None:
        config = MOD.load_config(MOD.DEFAULT_CONFIG)
        self.assertEqual(config["method"]["voxel_size_m"], 0.05)
        self.assertEqual(config["method"]["sdf_trunc_m"], 0.25)
        self.assertIsNone(config["method"]["alpha_threshold"])
        self.assertEqual(config["method"]["mesh_sample_classification"], 6)
        self.assertEqual(len(config["implementation_files"]), 4)
        self.assertTrue(
            config["aprime_custom_input_contract"]["required_cache_namespace"].endswith(
                "_v2"
            )
        )

    def test_custom_invocation_is_all_or_none(self) -> None:
        parser = MOD.parse_args
        import sys
        from unittest.mock import patch

        with patch.object(sys, "argv", ["tsdf", "--output-dir", "somewhere"]):
            args = parser()
        with self.assertRaisesRegex(MOD.TsdfReadoutError, "must override"):
            MOD.resolved_arguments(args, MOD.load_config(MOD.DEFAULT_CONFIG))

    def test_wrapper_is_offline_bounded_and_nonroot(self) -> None:
        self.assertIn("--network none", WRAPPER)
        self.assertIn("--pull=never", WRAPPER)
        self.assertIn('--user "$HOST_UID:$HOST_GID"', WRAPPER)
        self.assertIn("--memory 24g", WRAPPER)
        self.assertIn('-e "HOME=/tmp/aprime-t2-home"', WRAPPER)
        self.assertIn('-e "XDG_CACHE_HOME=/tmp/aprime-t2-cache"', WRAPPER)
        self.assertIn(
            '-e "TORCH_EXTENSIONS_DIR=/tmp/aprime-t2-torch-extensions"',
            WRAPPER,
        )
        self.assertIn('-e "MAX_JOBS=2"', WRAPPER)

    def test_committed_gate_and_stale_receipt_archive_are_wired(self) -> None:
        self.assertIn("verify_git_runtime(config)", SOURCE)
        self.assertIn("archive_existing_receipt(output_dir, receipt_name)", SOURCE)
        self.assertIn("staged_artifacts_published_before_receipt", SOURCE)

    def test_checkpoint_formats(self) -> None:
        state = {"means": torch.zeros(2, 3)}
        loaded, meta = MOD.checkpoint_state({"it": 30000, "state_dict": state})
        self.assertIs(loaded, state)
        self.assertEqual(meta["completed_steps"], 30000)
        loaded, meta = MOD.checkpoint_state(
            {
                "checkpoint_format": "jointbuildgs.stage2.full_state",
                "completed_steps": 123,
                "model": {"state_dict": state},
            }
        )
        self.assertIs(loaded, state)
        self.assertEqual(meta["completed_steps"], 123)

    def test_exact_mask_has_no_alpha_path(self) -> None:
        depth = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
        mask = np.array([[True, False], [True, False]])
        output, stats = MOD.masked_surface_depth(depth, mask, 10.0)
        np.testing.assert_array_equal(output, np.array([[1.0, 0.0], [3.0, 0.0]]))
        self.assertEqual(stats["M_j_pixels_n"], 2)
        self.assertEqual(stats["integrated_pixels_n"], 2)
        self.assertEqual(stats["outside_M_j_nonzero_after_mask_n"], 0)
        self.assertEqual(stats["alpha_threshold_exclusions_n"], 0)

    def test_invalid_render_depth_is_observed_not_mask_redefined(self) -> None:
        depth = np.array([[0.0, np.nan], [3.0, 50.0]], dtype=np.float32)
        mask = np.ones((2, 2), dtype=bool)
        output, stats = MOD.masked_surface_depth(depth, mask, 10.0)
        self.assertEqual(stats["M_j_pixels_n"], 4)
        self.assertEqual(stats["invalid_surface_depth_inside_M_j_n"], 2)
        self.assertEqual(stats["over_depth_trunc_inside_M_j_n"], 1)
        self.assertEqual(stats["integrated_pixels_n"], 1)
        self.assertEqual(float(output[1, 0]), 3.0)

    def test_depth_truncation_formula(self) -> None:
        centers = np.array([[10.0, 0.0, 0.0], [20.0, 0.0, 0.0]])
        value, stats = MOD.compute_depth_truncation(centers, np.zeros(3), 30.0)
        self.assertEqual(value, 31.0)
        self.assertEqual(stats["minimum_camera_radius_m"], 10.0)
        value, _ = MOD.compute_depth_truncation(centers, np.zeros(3), 5.0)
        self.assertEqual(value, 20.0)

    def test_vertical_conversion_once(self) -> None:
        config = MOD.load_config(MOD.DEFAULT_CONFIG)
        scene_path = MOD.repo_path(
            config["coordinate_contract"]["scene_reference_frame"]
        )
        scene = json.loads(scene_path.read_text(encoding="utf-8"))
        canonical = np.array([[-90.0, 112.0, -41.0]])
        base = MOD.canonical_to_orthometric(canonical, scene, 45.7)
        np.testing.assert_allclose(base, [[690863.0, 5336183.0, 517.3]])

    def test_component_filter_keeps_50_and_removes_49_triangles(self) -> None:
        class FakeMesh:
            def __init__(self) -> None:
                self.triangles = list(range(99))

            def cluster_connected_triangles(self):
                return [0] * 49 + [1] * 50, [49, 50], [1.0, 1.0]

            def remove_triangles_by_mask(self, mask):
                self.triangles = [
                    triangle
                    for triangle, remove in zip(self.triangles, mask, strict=True)
                    if not remove
                ]

            def remove_unreferenced_vertices(self):
                return None

            def remove_degenerate_triangles(self):
                return None

            def remove_duplicated_triangles(self):
                return None

            def remove_duplicated_vertices(self):
                return None

        mesh = FakeMesh()
        stats = MOD.filter_small_components(mesh, 50)
        self.assertEqual(stats["triangles_removed_n"], 49)
        self.assertEqual(stats["triangles_after_n"], 50)
        self.assertEqual(len(mesh.triangles), 50)

    def test_load_exact_M_j_new_and_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            depth = np.ones((3, 4), dtype=np.float32)
            mask = np.zeros((3, 4), dtype=np.uint8)
            mask[1, 2] = 1
            modern = root / "modern.npz"
            legacy = root / "legacy.npz"
            np.savez(modern, depth_camera_z_m=depth, valid_M_j=mask)
            np.savez(legacy, depth_camera_z_m=depth, valid=mask)
            _, loaded, field = MOD.load_exact_mask_prior(modern)
            self.assertTrue(np.array_equal(loaded, mask.astype(bool)))
            self.assertEqual(field, "valid_M_j")
            _, loaded, field = MOD.load_exact_mask_prior(legacy)
            self.assertTrue(np.array_equal(loaded, mask.astype(bool)))
            self.assertEqual(field, "valid")

    def test_empty_exact_M_j_is_a_measured_noop_view(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.npz"
            np.savez(
                path,
                depth_camera_z_m=np.zeros((3, 4), dtype=np.float32),
                valid_M_j=np.zeros((3, 4), dtype=np.uint8),
            )
            _, loaded, field = MOD.load_exact_mask_prior(path)
            self.assertFalse(loaded.any())
            self.assertEqual(field, "valid_M_j")

    def test_real_open3d_tsdf_and_marching_cubes(self) -> None:
        import open3d as o3d

        volume = MOD.create_tsdf_volume(o3d, 0.05, 0.15)
        height = width = 64
        color = np.full((height, width, 3), 128, dtype=np.uint8)
        depth = np.ones((height, width), dtype=np.float32)
        intrinsic = o3d.camera.PinholeCameraIntrinsic(
            width, height, 60.0, 60.0, width / 2.0, height / 2.0
        )
        MOD.integrate_open3d_frame(
            o3d, volume, color, depth, intrinsic, np.eye(4), 3.0
        )
        mesh = volume.extract_triangle_mesh()
        self.assertGreater(len(mesh.vertices), 0)
        self.assertGreater(len(mesh.triangles), 0)


if __name__ == "__main__":
    unittest.main()

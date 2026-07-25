#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import copy
import json
import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "phases/p2-gsjso/scripts/fusion_w1_coreg_lock1.py"
SPEC = importlib.util.spec_from_file_location("fusion_w1_coreg_lock1", MODULE_PATH)
assert SPEC and SPEC.loader
coreg = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = coreg
SPEC.loader.exec_module(coreg)


class CoregMathTests(unittest.TestCase):
    @staticmethod
    def synthetic_groups(transform: np.ndarray) -> list[coreg.SurfaceGroup]:
        rng = np.random.default_rng(20260725)
        groups = []
        definitions = [
            ("b1", "roof", np.array([1.0, 0.0, 0.0])),
            ("b1", "ground", np.array([0.0, 1.0, 0.0])),
            ("b2", "roof", np.array([0.0, 0.0, 1.0])),
            ("b2", "ground", np.array([1.0, 1.0, 1.0]) / math.sqrt(3.0)),
        ]
        inverse = np.linalg.inv(transform)
        for index, (bid, surface, normal) in enumerate(definitions):
            basis1 = np.cross(normal, [0.0, 0.0, 1.0])
            if np.linalg.norm(basis1) < 0.1:
                basis1 = np.cross(normal, [0.0, 1.0, 0.0])
            basis1 /= np.linalg.norm(basis1)
            basis2 = np.cross(normal, basis1)
            uv = rng.uniform(-8.0, 8.0, size=(180, 2))
            center = np.array([index * 4.0 - 6.0, index * 2.0 - 3.0, index])
            fixed = center + uv[:, :1] * basis1 + uv[:, 1:] * basis2
            moving = (inverse @ np.column_stack([fixed, np.ones(len(fixed))]).T).T[:, :3]
            moving_normals = (inverse[:3, :3] @ np.tile(normal, (len(fixed), 1)).T).T
            groups.append(
                coreg.SurfaceGroup(
                    bid,
                    "fit",
                    surface,
                    fixed,
                    moving,
                    np.tile(normal, (len(fixed), 1)),
                    moving_normals,
                )
            )
        return groups

    def test_rotation_exp_is_proper(self) -> None:
        rotation = coreg.rotation_exp([0.01, -0.02, 0.03])
        self.assertTrue(np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-12))
        self.assertAlmostEqual(float(np.linalg.det(rotation)), 1.0, places=12)

    def test_pivot_homogeneous_equivalence(self) -> None:
        pivot = np.array([690953.0, 5336071.0, 604.0])
        transform = np.eye(4)
        transform[:3, :3] = coreg.rotation_exp([0.001, -0.002, 0.0005])
        transform[:3, 3] = [0.1, -0.05, 0.02]
        point = np.array([[690960.0, 5336080.0, 561.0]])
        direct = coreg.transform_points_local(point, transform, pivot)[0]
        homogeneous = coreg.pivot_global_to_homogeneous(transform, pivot)
        matrix_value = (homogeneous @ np.append(point[0], 1.0))[:3]
        self.assertTrue(np.allclose(direct, matrix_value, atol=1e-10))

    def test_current_pivot_makes_canonical_transform_simple(self) -> None:
        pivot = np.array([690953.0, 5336071.0, 604.0])
        shift = -pivot
        transform = np.eye(4)
        transform[:3, :3] = coreg.rotation_exp([0.001, 0.002, -0.001])
        transform[:3, 3] = [0.2, -0.1, 0.05]
        global_matrix = coreg.pivot_global_to_homogeneous(transform, pivot)
        local_matrix = coreg.conjugate_global_to_canonical(global_matrix, shift)
        self.assertTrue(np.allclose(local_matrix, transform, atol=1e-10))

    def test_qvec_rotation_roundtrip_near_pi(self) -> None:
        rotation = coreg.rotation_exp([math.pi - 1e-7, 0.0, 0.0])
        qvec = coreg.rotmat_to_qvec(rotation)
        recovered = coreg.qvec_to_rotmat(qvec)
        self.assertGreaterEqual(qvec[0], 0.0)
        self.assertTrue(np.allclose(recovered, rotation, atol=1e-8))

    def test_pose_update_projection_invariance(self) -> None:
        old_q = coreg.rotmat_to_qvec(coreg.rotation_exp([0.1, -0.2, 0.05]))
        old_t = np.array([1.0, -2.0, 3.0])
        world_transform = np.eye(4)
        world_transform[:3, :3] = coreg.rotation_exp([0.002, -0.001, 0.003])
        world_transform[:3, 3] = [0.1, -0.05, 0.02]
        new_q, new_t = coreg.update_colmap_pose(old_q, old_t, world_transform)
        old = coreg.ColmapImageRecord(1, old_q, old_t, 1, "a.jpg", b"\0" * 8)
        new = coreg.ColmapImageRecord(1, new_q, new_t, 1, "a.jpg", b"\0" * 8)
        error = coreg.verify_projection_invariance(old, new, world_transform)
        self.assertLess(error, 1e-10)

    def test_geoid_precedes_transform(self) -> None:
        orthometric = np.array([[690953.0, 5336071.0, 515.0]])
        ellipsoidal = orthometric.copy()
        ellipsoidal[:, 2] += 45.7
        transform = np.eye(4)
        transform[:3, :3] = coreg.rotation_exp([0.001, 0.0, 0.0])
        pivot = np.array([690953.0, 5336071.0, 604.0])
        expected = coreg.transform_points_local(ellipsoidal, transform, pivot)
        wrong = coreg.transform_points_local(orthometric, transform, pivot)
        wrong[:, 2] += 45.7
        self.assertGreater(float(np.linalg.norm(expected - wrong)), 1e-3)

    def test_point_to_plane_jacobian_finite_difference(self) -> None:
        point = np.array([3.0, -2.0, 1.0])
        normal = np.array([0.3, -0.4, 0.866025403784])
        normal /= np.linalg.norm(normal)
        analytic = np.concatenate([np.cross(point, normal), normal])
        numeric = []
        epsilon = 1e-7
        for index in range(6):
            omega = np.zeros(3)
            translation = np.zeros(3)
            if index < 3:
                omega[index] = epsilon
            else:
                translation[index - 3] = epsilon
            transformed = coreg.rotation_exp(omega) @ point + translation
            numeric.append(float(normal @ (transformed - point)) / epsilon)
        self.assertTrue(np.allclose(analytic, numeric, atol=1e-6))

    def test_parallel_horizontal_planes_are_rank_deficient(self) -> None:
        rng = np.random.default_rng(7)
        points = rng.normal(size=(200, 3))
        points[:, 2] = np.repeat([0.0, 5.0], 100)
        normals = np.tile([0.0, 0.0, 1.0], (200, 1))
        design = np.column_stack([np.cross(points, normals), normals])
        rank, condition, _ = coreg.normalized_design_diagnostics(
            design, np.ones(len(design))
        )
        self.assertLess(rank, 6)
        self.assertTrue(math.isinf(condition))

    def test_multiple_normals_are_full_rank(self) -> None:
        rng = np.random.default_rng(8)
        points = rng.uniform(-10, 10, size=(600, 3))
        normals = np.vstack(
            [
                np.tile([1.0, 0.0, 0.0], (200, 1)),
                np.tile([0.0, 1.0, 0.0], (200, 1)),
                np.tile([0.0, 0.0, 1.0], (200, 1)),
            ]
        )
        design = np.column_stack([np.cross(points, normals) / 10.0, normals])
        rank, condition, _ = coreg.normalized_design_diagnostics(
            design, np.ones(len(design))
        )
        self.assertEqual(rank, 6)
        self.assertLess(condition, 10.0)

    def test_known_small_se3_is_recovered(self) -> None:
        truth = np.eye(4)
        truth[:3, :3] = coreg.rotation_exp([0.0008, -0.0005, 0.0006])
        truth[:3, 3] = [0.03, -0.02, 0.015]
        config = copy.deepcopy(coreg.load_config())
        config["input_locks"]["rotation_pivot_global_m"] = [0.0, 0.0, 0.0]
        estimated, diagnostics = coreg.fit_global_transform(
            self.synthetic_groups(truth), config
        )
        self.assertTrue(diagnostics["candidate_valid"])
        self.assertTrue(diagnostics["final_level_converged"])
        self.assertTrue(np.allclose(estimated, truth, atol=2e-5))

    def test_nonconverged_candidate_is_rejected(self) -> None:
        truth = np.eye(4)
        truth[:3, :3] = coreg.rotation_exp([0.003, -0.002, 0.001])
        truth[:3, 3] = [0.25, -0.15, 0.1]
        config = copy.deepcopy(coreg.load_config())
        config["input_locks"]["rotation_pivot_global_m"] = [0.0, 0.0, 0.0]
        config["global_registration"]["maximum_iterations"] = [1, 1, 1]
        config["global_registration"]["convergence_rotation_rad"] = 1e-14
        config["global_registration"]["convergence_translation_m"] = 1e-14
        _, diagnostics = coreg.fit_global_transform(
            self.synthetic_groups(truth), config
        )
        self.assertFalse(diagnostics["candidate_valid"])
        self.assertEqual(diagnostics["invalid_reason"], "final_level_not_converged")

    def test_invalid_sparse_normals_are_excluded(self) -> None:
        points = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]])
        normals, valid = coreg.estimate_normals(points, 8, 0.5, 3, 0.15)
        self.assertFalse(np.any(valid))
        self.assertTrue(np.all(np.isnan(normals)))

    def test_block_composition_is_delta_after_global(self) -> None:
        global_transform = np.eye(4)
        global_transform[:3, 3] = [0.1, 0.0, 0.0]
        delta = np.eye(4)
        delta[:3, :3] = coreg.rotation_exp([0.0, 0.0, 0.001])
        delta[:3, 3] = [0.0, 0.02, 0.0]
        point = np.array([[2.0, 3.0, 4.0]])
        expected = coreg.transform_points_local(
            coreg.transform_points_local(point, global_transform, np.zeros(3)),
            delta,
            np.zeros(3),
        )
        total = delta @ global_transform
        observed = coreg.transform_points_local(point, total, np.zeros(3))
        self.assertTrue(np.allclose(expected, observed, atol=1e-12))

    def test_both_surface_filter(self) -> None:
        points = np.zeros((3, 3))
        normals = np.tile([0.0, 0.0, 1.0], (3, 1))
        groups = [
            coreg.SurfaceGroup("a", "fit", "roof", points, points, normals, normals, "b1"),
            coreg.SurfaceGroup("a", "fit", "ground", points, points, normals, normals, "b1"),
            coreg.SurfaceGroup("b", "fit", "roof", points, points, normals, normals, "b1"),
        ]
        filtered = coreg._groups_with_both_surfaces(groups)
        self.assertEqual({group.building_id for group in filtered}, {"a"})

    def test_parent_binding_tamper_is_rejected(self) -> None:
        current = {"head": "abc", "config_sha256": "def"}
        coreg.verify_parent_binding({"stage_binding": current}, current, label="ok")
        with self.assertRaises(coreg.CoregError):
            coreg.verify_parent_binding(
                {"stage_binding": {"head": "other"}}, current, label="tampered"
            )

    def test_stage_open_receipt_is_exact_once_and_binds_parents(self) -> None:
        binding = {"head": "abc", "config_sha256": "def"}
        parents = {"fit_candidate": "123"}
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            receipt = coreg.open_exact_stage(
                runtime, "select", binding, parents
            )
            payload = json.loads(receipt.read_text())
            self.assertEqual(payload["stage"], "select")
            self.assertEqual(payload["stage_binding"], binding)
            self.assertEqual(payload["parent_receipt_sha256"], parents)
            with self.assertRaises(coreg.CoregError):
                coreg.open_exact_stage(runtime, "select", binding, parents)

    def test_frozen_global_transform_must_equal_selection_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            fit_path = runtime / "fit_candidate.json"
            coreg.write_json(fit_path, {"candidate": "locked"})
            coreg.open_exact_stage(
                runtime,
                "select",
                {"head": "abc"},
                {"fit_candidate": coreg.sha256_file(fit_path)},
            )
            selection = {
                "schema": "jointbuildgs.fusion_w1.coreg_frozen_transform.v1",
                "status": "FROZEN",
                "fit_candidate_sha256": coreg.sha256_file(fit_path),
                "selected_transform_sha256": "one",
            }
            selection_path = runtime / "global_selection.json"
            coreg.write_json(selection_path, selection)
            frozen = dict(selection)
            frozen["global_selection_receipt_sha256"] = coreg.sha256_file(
                selection_path
            )
            frozen["block_transforms"] = {}
            coreg.verify_frozen_selection_chain(runtime, frozen)
            frozen["selected_transform_sha256"] = "tampered"
            with self.assertRaises(coreg.CoregError):
                coreg.verify_frozen_selection_chain(runtime, frozen)

    def test_condition_is_translation_origin_invariant_with_fixed_pivot(self) -> None:
        rng = np.random.default_rng(9)
        local = rng.normal(size=(500, 3))
        normals = rng.normal(size=(500, 3))
        normals /= np.linalg.norm(normals, axis=1, keepdims=True)
        design1 = np.column_stack([np.cross(local, normals) / 2.0, normals])
        global_origin = np.array([690953.0, 5336071.0, 604.0])
        points = local + global_origin
        design2 = np.column_stack(
            [np.cross(points - global_origin, normals) / 2.0, normals]
        )
        _, condition1, _ = coreg.normalized_design_diagnostics(
            design1, np.ones(len(design1))
        )
        _, condition2, _ = coreg.normalized_design_diagnostics(
            design2, np.ones(len(design2))
        )
        self.assertAlmostEqual(condition1, condition2, places=10)


class CoregProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = coreg.load_config()

    def test_locked_inputs_have_expected_hashes(self) -> None:
        observed = coreg.verify_input_hashes(self.config)
        self.assertIn(
            "results/tum_transfer/mob_analysis/p0c_step2/als_aoi.laz", observed
        )

    def test_generated_prereg_artifacts_match_locked_hashes(self) -> None:
        observed = coreg.verify_generated_locks(self.config)
        self.assertEqual(
            observed["splits_csv"],
            self.config["input_locks"]["generated_lock_sha256"]["splits_csv"],
        )

    def test_selector_uses_no_core_and_exact_roles(self) -> None:
        rows = coreg.select_control_rows(self.config)
        targets = {
            row["building_id"]: row
            for row in coreg._read_csv(self.config["inputs"]["targets_csv"])
        }
        self.assertEqual(len(rows), 36)
        self.assertTrue(all(targets[row["building_id"]]["cohort"] == "extension" for row in rows))
        self.assertTrue(all(row["tier"] == "surface" for row in rows))
        self.assertEqual(sum(row["role"] == "fit" for row in rows), 18)
        self.assertEqual(sum(row["role"] == "trigger" for row in rows), 9)
        self.assertEqual(sum(row["role"] == "check" for row in rows), 9)
        self.assertGreaterEqual(
            min(float(row["core_footprint_distance_m"]) for row in rows), 20.0
        )

    def test_camera_blocks_cover_exact_pose_inventory(self) -> None:
        rows = coreg.build_camera_block_rows(self.config)
        self.assertEqual(len(rows), 937)
        self.assertEqual(len({row["image_name"] for row in rows}), 937)
        self.assertGreaterEqual(len({row["block_id"] for row in rows}), 3)

    def test_images_bin_complete_roundtrip_preserves_points2d(self) -> None:
        tail = struct.pack("<Qddq", 1, 12.5, 8.25, 42)
        image = coreg.ColmapImageRecord(
            7,
            np.array([1.0, 0.0, 0.0, 0.0]),
            np.array([1.0, 2.0, 3.0]),
            2,
            "test.JPG",
            tail,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "images.bin"
            coreg.write_images_bin_complete(path, {7: image})
            observed = coreg.read_images_bin_complete(path)[7]
        self.assertEqual(observed.points2d_tail, tail)
        self.assertEqual(observed.name, image.name)

    def test_block_pose_detaches_all_shared_point3d_ids(self) -> None:
        tail = (
            struct.pack("<Q", 2)
            + struct.pack("<ddq", 12.5, 8.25, 42)
            + struct.pack("<ddq", 4.0, 3.0, 99)
        )
        detached = coreg.invalidate_points2d_point3d_ids(tail)
        self.assertEqual(struct.unpack_from("<dd", detached, 8), (12.5, 8.25))
        self.assertEqual(struct.unpack_from("<q", detached, 24)[0], -1)
        self.assertEqual(struct.unpack_from("<q", detached, 48)[0], -1)

    def test_config_forbids_scale_and_zeta_search(self) -> None:
        locks = self.config["input_locks"]
        self.assertEqual(locks["orthometric_to_ellipsoidal_zeta_m"], 45.7)
        self.assertEqual(locks["scale"], 1.0)
        self.assertTrue(locks["zeta_search_forbidden"])
        self.assertTrue(locks["scale_estimation_forbidden"])

    def test_run004_exposed_ids_are_not_controls(self) -> None:
        controls = {row["building_id"] for row in coreg.select_control_rows(self.config)}
        exposed = set(self.config["split"]["run004_exposed_core_ids"])
        self.assertFalse(controls & exposed)

    def test_recovery_lock2_uses_fresh_namespace_and_exposure_policy(self) -> None:
        recovered = coreg.activate_recovery_lock2(self.config)
        self.assertEqual(
            recovered["inputs"]["runtime_dir"],
            "results/tum_transfer/fusion_w1_coreg_lock2",
        )
        self.assertTrue(
            recovered["split"]["geometry_feasibility_screen_required"]
        )
        self.assertEqual(
            recovered["split"]["prior_fit_residual_exposure_policy"],
            "fit_only",
        )
        self.assertEqual(
            self.config["inputs"]["splits_csv"],
            recovered["split"]["prior_exposure_split_csv"],
        )
        self.assertEqual(
            recovered["recovery_lock2"][
                "geometry_feasibility_screen_uses_correspondence_residuals"
            ],
            False,
        )
        self.assertTrue(
            recovered["split"][
                "geometry_feasibility_screen_nominal_alignment_sensitive"
            ]
        )
        self.assertEqual(
            recovered["split"]["alignment_judgment_scope"],
            "coreg evidence conditional on support screen; final decision is "
            "predeclared core-building Gate A2",
        )

    def test_recovery_predecessor_and_prereg_ledgers_are_locked(self) -> None:
        recovered = coreg.activate_recovery_lock2(self.config)
        predecessor = coreg.validate_recovery_predecessor(
            self.config, self.config["recovery_lock2"]
        )
        self.assertEqual(len(predecessor), 8)
        ledger = coreg.verify_recovery_prereg_ledger_separation(recovered)
        self.assertTrue(ledger["active"])
        self.assertEqual(ledger["prereg_failure_count"], 2)

        tampered = copy.deepcopy(self.config)
        tampered["recovery_lock2"]["predecessor_contract"]["file_sha256"][
            tampered["recovery_lock2"]["predecessor_contract"][
                "publication_manifest"
            ]
        ] = "0" * 64
        with self.assertRaises(coreg.CoregError):
            coreg.activate_recovery_lock2(tampered)

    def test_recovery_split_keeps_prior_fit_exposure_out_of_holdout(self) -> None:
        recovered = coreg.activate_recovery_lock2(self.config)
        rows = coreg._read_csv(recovered["inputs"]["splits_csv"])
        self.assertEqual(len(rows), 36)
        self.assertEqual(sum(row["role"] == "fit" for row in rows), 18)
        self.assertEqual(sum(row["role"] == "trigger" for row in rows), 9)
        self.assertEqual(sum(row["role"] == "check" for row in rows), 9)
        self.assertTrue(
            all(row["geometry_feasibility_pass"] == "true" for row in rows)
        )
        self.assertFalse(
            any(
                row["prior_fit_residual_exposed"] == "true"
                and row["role"] in {"trigger", "check"}
                for row in rows
            )
        )
        self.assertNotIn(
            "DEBY_LOD2_4907165",
            {row["building_id"] for row in rows},
        )
        coreg.verify_generated_locks(recovered)


if __name__ == "__main__":
    unittest.main()

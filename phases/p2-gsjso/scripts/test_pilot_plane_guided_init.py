#!/usr/bin/env python3
"""CPU tests for deterministic pilot plane initialization and medium windows."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from src.stage2.model import GaussianModel2D
from src.stage2.plane_guided_init import (
    PlaneGuidedInitConfig,
    PlaneGuidedInitialization,
    assign_seed_normals_knn,
    build_plane_guided_initialization,
    sample_masked_mvs_view,
    verify_resume_initialization_audit,
)
from src.stage2.train import (
    _execute_pilot_plane_init_start_gate,
    _pilot_plane_init_config,
    _pilot_plane_init_start_mode,
    _pilot_plane_window_coplanarity,
    _validate_pilot_config_contract,
)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _FakeDataset:
    def __init__(self) -> None:
        self.frames = [
            SimpleNamespace(
                name="a.png",
                R=np.eye(3, dtype=np.float64),
                t=np.zeros(3, dtype=np.float64),
            ),
            SimpleNamespace(
                name="b.png",
                R=np.eye(3, dtype=np.float64),
                t=np.zeros(3, dtype=np.float64),
            ),
        ]
        self.depth = np.full((3, 3), 2.0, dtype=np.float32)
        self.valid = np.ones((3, 3), dtype=np.bool_)
        self.normal = np.zeros((3, 3, 3), dtype=np.float32)
        self.normal[..., 2] = -1.0

    def image_size(self, index: int) -> tuple[int, int]:
        return 3, 3

    def scaled_K(self, index: int) -> np.ndarray:
        return np.eye(3, dtype=np.float64)

    def _load_depth(self, frame, height: int, width: int):
        return self.depth.copy(), self.valid.copy()

    def _load_normal(self, frame, height: int, width: int):
        return self.normal.copy(), self.valid.copy()


class _FakeBinding:
    def __init__(self, manifest_path: Path, masks: dict[str, np.ndarray]) -> None:
        self.masks = masks
        self.audit = {
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": _file_sha256(manifest_path),
            "inventory_sha256": "1" * 64,
            "purpose": "plane_region",
            "source": "vision_groundedsam_roof",
            "view_count": len(masks),
        }

    def load(self, frame, size_hw: tuple[int, int]) -> np.ndarray:
        value = self.masks[frame.name]
        if value.shape != size_hw:
            raise AssertionError("fake mask shape mismatch")
        return value.copy()


class PilotPlaneGuidedInitTests(unittest.TestCase):
    def test_sample_grid_backprojection_and_positive_z_sign(self) -> None:
        depth = np.full((3, 3), 2.0, dtype=np.float32)
        normals = np.zeros((3, 3, 3), dtype=np.float32)
        normals[..., 2] = -1.0
        mask = np.ones((3, 3), dtype=np.bool_)
        result = sample_masked_mvs_view(
            depth=depth,
            depth_valid=mask,
            normals_world=normals,
            normal_valid=mask,
            plane_region_mask=mask,
            intrinsics=np.eye(3),
            rotation_world_to_camera=np.eye(3),
            translation_world_to_camera=np.array([1.0, 0.0, 0.0]),
            stride_px=2,
            grid_offset_px=1,
        )
        self.assertEqual(result.xyz_world.shape, (1, 3))
        np.testing.assert_allclose(result.xyz_world[0], [1.0, 2.0, 2.0])
        np.testing.assert_allclose(result.normals_world_up[0], [0.0, 0.0, 1.0])

    def test_chunked_knn_is_deterministic_and_unmatched_is_positive_z(self) -> None:
        seeds = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]], np.float32)
        evidence = np.array([[0.1, 0.0, 0.0], [0.2, 0.0, 0.0]], np.float32)
        normals = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], np.float32)
        first = assign_seed_normals_knn(
            seeds,
            evidence,
            normals,
            knn=2,
            tolerance_m=0.5,
            query_chunk_size=1,
        )
        second = assign_seed_normals_knn(
            seeds,
            evidence,
            normals,
            knn=2,
            tolerance_m=0.5,
            query_chunk_size=2,
        )
        self.assertEqual(first.matched_mask.tolist(), [True, False])
        np.testing.assert_allclose(
            first.normals_world_up[0],
            [2.0**-0.5, 2.0**-0.5, 0.0],
            atol=1.0e-6,
        )
        np.testing.assert_array_equal(first.normals_world_up[1], [0.0, 0.0, 1.0])
        np.testing.assert_array_equal(first.normals_world_up, second.normals_world_up)

    def test_build_allows_empty_view_requires_positive_aggregate_and_audits_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "mask_manifest.json"
            manifest_path.write_text(
                json.dumps({"source_disclosure": "synthetic vision mask"}) + "\n",
                encoding="utf-8",
            )
            masks = {
                "a.png": np.pad(
                    np.ones((1, 1), dtype=np.bool_), ((0, 2), (0, 2))
                ),
                "b.png": np.zeros((3, 3), dtype=np.bool_),
            }
            dataset = _FakeDataset()
            binding = _FakeBinding(manifest_path, masks)
            config = PlaneGuidedInitConfig(
                stride_px=1,
                grid_offset_px=0,
                knn=1,
                tolerance_m=0.1,
                min_coverage=0.5,
                query_chunk_size=1,
            )
            result = build_plane_guided_initialization(
                dataset=dataset,
                training_view_indices=[1, 0],
                mvs_seed_xyz=np.array([[0.0, 0.0, 2.0], [9.0, 9.0, 9.0]], np.float32),
                plane_mask_binding=binding,
                pilot_arm="04a_plane_medium_vision",
                config=config,
            )
            self.assertEqual(result.audit["source"]["training_empty_mask_view_count"], 1)
            self.assertEqual(result.audit["source"]["training_evidence_view_count"], 1)
            self.assertEqual(result.audit["counts"]["matched_seed_count"], 1)
            self.assertEqual(result.audit["counts"]["matched_seed_fraction"], 0.5)
            self.assertEqual(
                [row["view_id"] for row in result.audit["views"]],
                ["a.png", "b.png"],
            )
            upper = build_plane_guided_initialization(
                dataset=dataset,
                training_view_indices=[1, 0],
                mvs_seed_xyz=np.array(
                    [[0.0, 0.0, 2.0], [9.0, 9.0, 9.0]], np.float32
                ),
                plane_mask_binding=binding,
                pilot_arm="04b_plane_medium_gt_upperbound",
                config=config,
            )
            self.assertEqual(
                result.audit["algorithm_sha256"], upper.audit["algorithm_sha256"]
            )
            np.testing.assert_array_equal(
                result.normals_world_up, upper.normals_world_up
            )

            previous_path = root / "pilot_plane_guided_init.json"
            previous_path.write_text(
                json.dumps({**result.audit, "application": {"mode": "fresh_start"}})
                + "\n",
                encoding="utf-8",
            )
            verification = verify_resume_initialization_audit(previous_path, result)
            self.assertTrue(verification["passed"])
            self.assertFalse(verification["initializer_reapplied"])

            class NoApplyResumeModel:
                def __init__(self) -> None:
                    self.calls = 0

                def initialize_normals_from_world(self, target, selection):
                    self.calls += 1
                    raise AssertionError("resume must not call the initializer")

            resume_model = NoApplyResumeModel()
            resume_verification_path = root / "resume_verification.json"
            returned_path = _execute_pilot_plane_init_start_gate(
                model=resume_model,
                result=result,
                mvs_seed_mask=np.array([True, True]),
                start_mode="resume_verify_only",
                fresh_audit_path=previous_path,
                resume_audit_path=resume_verification_path,
            )
            self.assertEqual(resume_model.calls, 0)
            self.assertEqual(returned_path, resume_verification_path)
            persisted_verification = json.loads(
                resume_verification_path.read_text(encoding="utf-8")
            )
            self.assertFalse(persisted_verification["initializer_reapplied"])

            changed_audit = dict(result.audit)
            changed_audit["binding_sha256"] = "0" * 64
            changed = PlaneGuidedInitialization(
                normals_world_up=result.normals_world_up,
                matched_mask=result.matched_mask,
                audit=changed_audit,
            )
            with self.assertRaisesRegex(RuntimeError, "binding mismatch"):
                verify_resume_initialization_audit(previous_path, changed)

            with self.assertRaisesRegex(RuntimeError, "matched zero"):
                build_plane_guided_initialization(
                    dataset=dataset,
                    training_view_indices=[0, 1],
                    mvs_seed_xyz=np.array([[50.0, 50.0, 50.0]], np.float32),
                    plane_mask_binding=binding,
                    pilot_arm="04a_plane_medium_vision",
                    config=config,
                )
            high_coverage = PlaneGuidedInitConfig(
                stride_px=1,
                grid_offset_px=0,
                knn=1,
                tolerance_m=0.1,
                min_coverage=0.75,
                query_chunk_size=1,
            )
            with self.assertRaisesRegex(RuntimeError, "coverage below"):
                build_plane_guided_initialization(
                    dataset=dataset,
                    training_view_indices=[0, 1],
                    mvs_seed_xyz=np.array(
                        [[0.0, 0.0, 2.0], [9.0, 9.0, 9.0]], np.float32
                    ),
                    plane_mask_binding=binding,
                    pilot_arm="04a_plane_medium_vision",
                    config=high_coverage,
                )

            binding.masks["a.png"][:] = False
            with self.assertRaisesRegex(RuntimeError, "zero aggregate"):
                build_plane_guided_initialization(
                    dataset=dataset,
                    training_view_indices=[0, 1],
                    mvs_seed_xyz=np.array([[0.0, 0.0, 2.0]], np.float32),
                    plane_mask_binding=binding,
                    pilot_arm="04a_plane_medium_vision",
                    config=config,
                )

    def test_model_quaternion_maps_local_z_only_for_selected_rows(self) -> None:
        points = np.array(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            dtype=np.float32,
        )
        model = GaussianModel2D(
            points,
            np.full((4, 3), 0.5, dtype=np.float32),
            sh_degree=0,
            device="cpu",
        )
        selection = torch.tensor([True, True, True, False])
        target = torch.tensor(
            [[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            dtype=torch.float32,
        )
        quats_before = model.quats.detach().clone()
        self.assertEqual(model.initialize_normals_from_world(target, selection), 3)
        self.assertFalse(torch.equal(model.quats.detach()[1:3], quats_before[1:3]))
        self.assertTrue(torch.equal(model.quats.detach()[3], quats_before[3]))
        np.testing.assert_allclose(
            model.normals()[selection].detach().numpy(), target.numpy(), atol=1.0e-6
        )
        np.testing.assert_allclose(
            model.normals()[~selection].detach().numpy(), [[0.0, 0.0, 1.0]], atol=1.0e-6
        )

    def test_medium_arms_share_local_window_and_do_not_fit_binary_union_plane(self) -> None:
        height, width = 21, 31
        K = torch.tensor(
            [[120.0, 0.0, 15.0], [0.0, 120.0, 10.0], [0.0, 0.0, 1.0]],
            dtype=torch.float64,
        )
        depth = torch.full((height, width), 5.0, dtype=torch.float64)
        depth[:, width // 2 :] = 8.0
        depth.requires_grad_(True)
        mask = torch.ones((height, width), dtype=torch.bool)
        kwargs = dict(
            depth=depth,
            intrinsics=K,
            alpha=torch.ones_like(depth),
            plane_region_mask=mask,
            audit_mask=None,
            window_size=7,
            stride=1,
            min_points=30,
            alpha_threshold=0.5,
            max_depth_range=0.5,
            min_second_eigenvalue=1.0e-10,
        )
        vision = _pilot_plane_window_coplanarity(
            pilot_arm="04a_plane_medium_vision", **kwargs
        )
        upper = _pilot_plane_window_coplanarity(
            pilot_arm="04b_plane_medium_gt_upperbound", **kwargs
        )
        self.assertGreater(vision.plane_count, 0)
        self.assertGreater(vision.diagnostics["rejected_depth_edge_count"], 0)
        self.assertLess(float(vision.loss), 1.0e-12)
        self.assertEqual(vision.plane_count, upper.plane_count)
        self.assertEqual(float(vision.loss), float(upper.loss))

    def test_init_config_has_no_implicit_protocol_defaults(self) -> None:
        cfg = {
            "pilot_plane_init_stride_px": 8,
            "pilot_plane_init_grid_offset_px": 3,
            "pilot_plane_init_knn": 4,
            "pilot_plane_init_tolerance_m": 0.75,
            "pilot_plane_init_min_coverage": 0.2,
            "pilot_plane_init_query_chunk_size": 4096,
        }
        resolved = _pilot_plane_init_config(cfg)
        self.assertEqual(resolved.as_dict()["grid_offset_px"], 3)
        for key in tuple(cfg):
            incomplete = dict(cfg)
            incomplete.pop(key)
            with self.assertRaises(ValueError, msg=key):
                _pilot_plane_init_config(incomplete)

    def test_medium_trainer_contract_forces_initializer_keys_and_mvs_seed(self) -> None:
        cfg = {
            "pilot_arm": "04a_plane_medium_vision",
            "max_iter": 20000,
            "load_depth": True,
            "load_normal": True,
            "load_semantic": False,
            "mono_normal_dir": "/mono",
            "roof_audit_mask_manifest": "/masks/footprint.json",
            "photo_mask_manifest": "/masks/footprint.json",
            "plane_region_mask_manifest": "/masks/vision.json",
            "init_pointcloud": "/seeds/dense.ply",
            "structure_grouping": "g2_geometry",
            "w_photo": 1.0,
            "w_depth": 0.1,
            "w_normal": 0.15,
            "w_mono_normal_aux": 0.05,
            "w_nc": 0.05,
            "w_structure": 0.08,
            "w_structure_na": 1.0,
            "w_structure_cp": 1.0,
            "w_plane": 1.0,
            "w_distort": 0.0,
            "w_sem": 0.0,
            "pilot_loss_audit_every": 100,
            "pilot_plane_window_size": 7,
            "pilot_plane_stride": 4,
            "pilot_plane_min_points": 16,
            "pilot_plane_alpha_threshold": 0.5,
            "pilot_plane_max_depth_range": 1.0,
            "pilot_plane_min_second_eigenvalue": 1.0e-10,
            "pilot_plane_init_stride_px": 8,
            "pilot_plane_init_grid_offset_px": 4,
            "pilot_plane_init_knn": 4,
            "pilot_plane_init_tolerance_m": 0.5,
            "pilot_plane_init_min_coverage": 0.05,
            "pilot_plane_init_query_chunk_size": 100000,
        }
        full_state = {
            "enabled": True,
            "checkpoint_steps": (5000, 10000, 15000, 20000),
            "loss_csv_paths": (
                "audit/pilot_loss_shares.csv",
                "audit/pilot_loss_details.csv",
                "audit/pilot_plane_photo_ratio.csv",
            ),
        }
        for arm in (
            "04a_plane_medium_vision",
            "04b_plane_medium_gt_upperbound",
        ):
            cfg["pilot_arm"] = arm
            self.assertEqual(_validate_pilot_config_contract(cfg, full_state), arm)
        cfg["pilot_arm"] = "04a_plane_medium_vision"
        for key in (
            "init_pointcloud",
            "pilot_plane_init_stride_px",
            "pilot_plane_init_grid_offset_px",
            "pilot_plane_init_knn",
            "pilot_plane_init_tolerance_m",
            "pilot_plane_init_min_coverage",
            "pilot_plane_init_query_chunk_size",
        ):
            incomplete = dict(cfg)
            incomplete.pop(key)
            with self.assertRaises(ValueError, msg=key):
                _validate_pilot_config_contract(incomplete, full_state)

    def test_auto_without_prior_audit_is_fresh_but_other_resume_is_verify_only(self) -> None:
        self.assertEqual(
            _pilot_plane_init_start_mode(
                None,
                fresh_audit_exists=False,
                checkpoint_candidate_exists=False,
            ),
            "fresh",
        )
        self.assertEqual(
            _pilot_plane_init_start_mode(
                "auto",
                fresh_audit_exists=False,
                checkpoint_candidate_exists=False,
            ),
            "fresh_auto_candidate",
        )
        self.assertEqual(
            _pilot_plane_init_start_mode(
                "auto",
                fresh_audit_exists=True,
                checkpoint_candidate_exists=False,
            ),
            "resume_verify_only",
        )
        self.assertEqual(
            _pilot_plane_init_start_mode(
                "auto",
                fresh_audit_exists=False,
                checkpoint_candidate_exists=True,
            ),
            "resume_verify_only",
        )
        self.assertEqual(
            _pilot_plane_init_start_mode(
                "latest",
                fresh_audit_exists=False,
                checkpoint_candidate_exists=False,
            ),
            "resume_verify_only",
        )
        self.assertEqual(
            _pilot_plane_init_start_mode(
                "/tmp/step_5000.pt",
                fresh_audit_exists=False,
                checkpoint_candidate_exists=False,
            ),
            "resume_verify_only",
        )


if __name__ == "__main__":
    unittest.main()

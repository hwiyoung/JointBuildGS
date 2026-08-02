"""CPU regression tests for S3-A-prime surface-seed engine extensions."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

import numpy as np
import torch
from gsplat.strategy import DefaultStrategy

from src.stage2.dataloader import resolve_view_roles
from src.stage2.densification import (
    build_elongation_filter_strategy,
    build_seed_protect_strategy,
)
from src.stage2.loss.data_fitting import l_mono_depth_ssi
from src.stage2.model import GaussianModel2D
from src.stage2.semantic_seed import (
    SURFACE_SEED_SCHEMA,
    SeedResult,
    concat_seeds,
    load_surface_seed_npz,
    perturb_surface_seed,
)
from src.stage2.train import _mono_depth_geometry_contract, _target_region_mask


def _metadata() -> dict:
    return {
        "schema": SURFACE_SEED_SCHEMA,
        "seed_type": "surface",
        "coordinate_frame": "GS-local",
        "crs": "EPSG:25832",
        "gt_used_for_seed_generation": False,
        "lod2_used_for_seed_generation": False,
        "als_used_for_seed_generation": False,
    }


def _write_seed(path: Path, metadata: dict | None = None, **extra) -> None:
    xyz = np.array([[0, 0, 1], [1, 0, 1]], dtype=np.float32)
    arrays = {
        "xyz": xyz,
        "rgb": np.full_like(xyz, 0.4),
        "sem": np.ones(2, dtype=np.int64),
        "metadata_json": np.asarray(json.dumps(metadata or _metadata())),
        **extra,
    }
    np.savez(path, **arrays)


class SurfaceSeedContractTest(unittest.TestCase):
    def test_strict_schema_and_truth_sidechannel_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.npz"
            _write_seed(good)
            loaded = load_surface_seed_npz(good)
            self.assertEqual(loaded.xyz.shape, (2, 3))
            self.assertTrue(loaded.is_surface_seed.all())
            np.testing.assert_array_equal(loaded.init_opacity, np.full(2, 0.1, np.float32))

            extra = Path(tmp) / "extra.npz"
            _write_seed(extra, lod2_height=np.ones(2, np.float32))
            with self.assertRaisesRegex(ValueError, "unexpected arrays"):
                load_surface_seed_npz(extra)

            disguised = _metadata()
            disguised["provenance"] = {"reference_roof_z": 12.0}
            bad_meta = Path(tmp) / "bad_meta.npz"
            _write_seed(bad_meta, disguised)
            with self.assertRaisesRegex(ValueError, "truth-geometry metadata"):
                load_surface_seed_npz(bad_meta)

    def test_concat_preserves_semantics_opacity_and_surface_lineage(self):
        base_xyz = np.array([[0, 0, 0], [1, 1, 0]], np.float32)
        base_rgb = np.full((2, 3), 0.5, np.float32)
        semantic_seed = SeedResult(
            xyz=np.array([[2, 0, 0]], np.float32),
            rgb=np.full((1, 3), 0.5, np.float32),
            sem=np.array([2], np.int64),
            per_building={},
            init_opacity=np.array([0.25], np.float32),
            is_surface_seed=np.array([False]),
        )
        first = concat_seeds(
            base_xyz,
            base_rgb,
            semantic_seed,
            points_sem=np.array([3, -1], np.int64),
        )
        surface = SeedResult(
            xyz=np.array([[3, 0, 0]], np.float32),
            rgb=np.full((1, 3), 0.5, np.float32),
            sem=np.array([1], np.int64),
            per_building={},
            init_opacity=np.array([0.10], np.float32),
            is_surface_seed=np.array([True]),
        )
        second = concat_seeds(
            first.xyz,
            first.rgb,
            surface,
            points_sem=first.sem,
            points_init_opacity=first.init_opacity,
            points_surface_seed=first.is_surface_seed,
        )
        np.testing.assert_array_equal(second.sem, [3, -1, 2, 1])
        np.testing.assert_allclose(second.init_opacity, [0.1, 0.1, 0.25, 0.1])
        np.testing.assert_array_equal(second.is_surface_seed, [False, False, False, True])

        model = GaussianModel2D(
            second.xyz,
            second.rgb,
            points_sem=second.sem,
            points_init_opacity=second.init_opacity,
            surface_seed_mask=second.is_surface_seed,
            sh_degree=0,
            device="cpu",
        )
        np.testing.assert_allclose(model.opacities.detach().numpy(), second.init_opacity, atol=1e-7)
        np.testing.assert_array_equal(model.surface_seed_mask.numpy(), second.is_surface_seed)

    def test_legacy_opacity_and_three_value_unpack_are_unchanged(self):
        base_xyz = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], np.float32)
        base_rgb = np.full((4, 3), 0.5, np.float32)
        seeds = SeedResult(
            xyz=np.array([[0.5, 0.5, 1]], np.float32),
            rgb=np.full((1, 3), 0.5, np.float32),
            sem=np.array([1], np.int64),
            per_building={},
        )
        xyz, rgb, sem = concat_seeds(base_xyz, base_rgb, seeds)
        model = GaussianModel2D(xyz, rgb, points_sem=sem, sh_degree=0, device="cpu")
        np.testing.assert_allclose(model.opacities.detach().numpy()[:4], 0.10, atol=1e-7)
        self.assertAlmostEqual(float(model.opacities.detach()[-1]), 0.25, places=7)

    def test_surface_perturbation_changes_only_xyz(self):
        seed = SeedResult(
            xyz=np.array([[-1, 0, 2], [1, 0, 2]], np.float32),
            rgb=np.full((2, 3), 0.5, np.float32),
            sem=np.ones(2, np.int64),
            per_building={},
            init_opacity=np.full(2, 0.1, np.float32),
            is_surface_seed=np.ones(2, np.bool_),
            metadata=_metadata(),
        )
        out = perturb_surface_seed(
            seed,
            height_delta_m=1.0,
            tilt_deg=10,
            tilt_axis_xy=[1, 0],
            tilt_pivot_xy=[0, 0],
        )
        self.assertFalse(np.array_equal(out.xyz, seed.xyz))
        np.testing.assert_array_equal(out.rgb, seed.rgb)
        np.testing.assert_array_equal(out.sem, seed.sem)


class StrategyAndViewRoleTest(unittest.TestCase):
    @staticmethod
    def _params_and_state(seed_opacity: float):
        n = 2
        tensors = {
            "means": torch.nn.Parameter(torch.zeros(n, 3)),
            "scales": torch.nn.Parameter(torch.full((n, 3), float(np.log(0.001)))),
            "quats": torch.nn.Parameter(torch.tensor([[1.0, 0, 0, 0]] * n)),
            "opacities": torch.nn.Parameter(
                torch.logit(torch.tensor([seed_opacity, 0.9]))
            ),
            "sh0": torch.nn.Parameter(torch.zeros(n, 1, 3)),
            "shN": torch.nn.Parameter(torch.zeros(n, 0, 3)),
            "sem_logits": torch.nn.Parameter(torch.zeros(n, 4)),
        }
        optimizers = {key: torch.optim.Adam([value], lr=1e-3) for key, value in tensors.items()}
        state = {
            "is_seed": torch.tensor([True, False]),
            "surface_seed_lineage": torch.tensor([True, False]),
            "scene_scale": 1.0,
            "radii": torch.zeros(n),
        }
        return tensors, optimizers, state

    def test_a2_boundary_step_protection_threshold_and_reset(self):
        strategy = build_seed_protect_strategy(
            prune_opa=0.005,
            seed_protect_until_iter=10000,
            seed_prune_opa_initial=0.05,
            seed_prune_opa_final=0.01,
            seed_prune_switch_iter=10000,
        )
        self.assertEqual(strategy.effective_prune_opa(9999), 0.05)
        self.assertEqual(strategy.effective_prune_opa(10000), 0.01)
        self.assertEqual(2 * strategy.effective_prune_opa(9999), 0.10)
        self.assertEqual(2 * strategy.effective_prune_opa(10000), 0.02)
        schedule_state = {}
        with mock.patch.object(DefaultStrategy, "step_post_backward", return_value=None):
            strategy.step_post_backward({}, {}, schedule_state, 9999, {})
            self.assertEqual(schedule_state["effective_prune_opa"], 0.05)
            self.assertEqual(schedule_state["effective_reset_opa"], 0.10)
            strategy.step_post_backward({}, {}, schedule_state, 10000, {})
            self.assertEqual(schedule_state["effective_prune_opa"], 0.01)
            self.assertEqual(schedule_state["effective_reset_opa"], 0.02)

        params, opts, state = self._params_and_state(0.02)
        strategy.prune_opa = strategy.effective_prune_opa(9999)
        self.assertEqual(strategy._prune_gs(params, opts, state, 9999), 0)
        self.assertTrue(state["last_seed_protect_active"])
        self.assertEqual(state["last_prune_seed_protected"], 1)

        params, opts, state = self._params_and_state(0.005)
        strategy.prune_opa = strategy.effective_prune_opa(10000)
        self.assertEqual(strategy._prune_gs(params, opts, state, 10000), 1)
        self.assertFalse(state["last_seed_protect_active"])
        self.assertEqual(len(params["means"]), 1)
        self.assertTrue(torch.equal(state["surface_seed_lineage"], torch.tensor([False])))
        self.assertEqual(state["seed_protected_count"], 0)

    def test_dense_scene_growth_cap_skips_whole_overflow_event(self):
        params, opts, state = self._params_and_state(0.9)
        state.update(
            {
                "count": torch.ones(2),
                "grad2d": torch.ones(2),
                "radii": torch.zeros(2),
            }
        )
        strategy = build_elongation_filter_strategy(
            max_gaussians=3,
            grow_grad2d=0.1,
            grow_scale3d=1.0,
        )
        duplicated, split_count = strategy._grow_gs(params, opts, state, 500)
        self.assertEqual((duplicated, split_count), (0, 0))
        self.assertEqual(len(params["means"]), 2)
        self.assertTrue(state["growth_cap_blocked"])
        self.assertEqual(state["max_gaussians"], 3)

    def test_explicit_roles_and_legacy_split(self):
        frames = [SimpleNamespace(name=f"view_{i:02d}.jpg") for i in range(12)]
        train, test, audit = resolve_view_roles(frames)
        self.assertEqual(test, [9])
        self.assertEqual(train, [i for i in range(12) if i != 9])
        self.assertEqual(audit["mode"], "legacy_every_10th_eval")

        short = frames[:3]
        train, test, audit = resolve_view_roles(
            short,
            train_views=["view_00", "view_01", "view_02"],
            eval_views=[],
        )
        self.assertEqual(train, [0, 1, 2])
        self.assertEqual(test, [])
        self.assertEqual(audit["mode"], "explicit_locked_roles")
        with self.assertRaisesRegex(ValueError, "overlap"):
            resolve_view_roles(short, ["view_00", "view_01"], ["view_01", "view_02"])


class TargetPriorLossTest(unittest.TestCase):
    def test_a1_semantic_geometry_allows_only_explicit_ssi(self):
        contract = _mono_depth_geometry_contract(
            semantic_geometry_enabled=True,
            w_mono_depth=0.05,
            mono_depth_loss="ssi",
        )
        self.assertTrue(contract["mono_depth_ssi_enabled"])
        self.assertFalse(contract["absolute_mono_depth_active"])
        with self.assertRaisesRegex(RuntimeError, "absolute monocular-depth L1"):
            _mono_depth_geometry_contract(
                semantic_geometry_enabled=True,
                w_mono_depth=0.05,
                mono_depth_loss="absolute_l1",
            )

    def test_ssi_affine_invariance_and_outside_zero_gradient(self):
        mono = torch.linspace(1, 5, 144).reshape(12, 12)
        target = torch.zeros(12, 12, dtype=torch.int32)
        target[2:10, 2:10] = 7  # exactly 64 pixels
        valid = target > 0
        pred = (2.5 * mono + 3.0).clone().requires_grad_(True)
        loss, stats = l_mono_depth_ssi(pred, mono, target, valid, min_pixels=64)
        self.assertLess(float(loss), 2e-6)
        self.assertEqual(stats["eligible_region_count"], 1)
        loss.backward()
        self.assertTrue(torch.equal(pred.grad[~valid], torch.zeros_like(pred.grad[~valid])))

        pred2 = (mono.square() + 1).clone().requires_grad_(True)
        loss2, _ = l_mono_depth_ssi(pred2, mono, target, valid, min_pixels=64)
        self.assertGreater(float(loss2), 0)
        loss2.backward()
        self.assertGreater(float(pred2.grad[valid].abs().sum()), 0)
        self.assertEqual(float(pred2.grad[~valid].abs().sum()), 0.0)

    def test_ssi_lt64_and_constant_are_graph_zero(self):
        pred = torch.ones(10, 10, requires_grad=True)
        mono = torch.arange(100, dtype=torch.float32).reshape(10, 10) + 1
        ids = torch.zeros(10, 10, dtype=torch.int32)
        ids[:7, :9] = 1  # 63
        loss, stats = l_mono_depth_ssi(pred, mono, ids, ids > 0, min_pixels=64)
        self.assertEqual(float(loss), 0.0)
        self.assertTrue(loss.requires_grad)
        loss.backward()
        self.assertEqual(float(pred.grad.abs().sum()), 0.0)
        self.assertEqual(stats["eligible_region_count"], 0)

        pred = torch.ones(8, 8, requires_grad=True)
        mono = torch.ones(8, 8)
        ids = torch.ones(8, 8, dtype=torch.int32)
        loss, stats = l_mono_depth_ssi(pred, mono, ids, ids > 0, min_pixels=64)
        self.assertEqual(float(loss), 0.0)
        self.assertEqual(stats["per_region"][1]["status"], "skipped_degenerate_constant_mono")
        loss.backward()
        self.assertEqual(float(pred.grad.abs().sum()), 0.0)

    def test_target_mask_uses_metadata_membership_only(self):
        frame = SimpleNamespace(
            region_ids=torch.tensor([[1, 2], [0, 2]], dtype=torch.int32),
            cutline_mask=torch.tensor([[False, False], [False, True]]),
            metadata={
                "regions": {
                    "1": {"building_id": "DEBY_LOD2_8568391"},
                    "2": {"building_id": "DEBY_LOD2_4907199"},
                }
            },
        )
        mask, ids, audit = _target_region_mask(frame, {"8568391"})
        self.assertTrue(torch.equal(mask, torch.tensor([[True, False], [False, False]])))
        self.assertTrue(torch.equal(ids, torch.tensor([[1, 0], [0, 0]], dtype=torch.int32)))
        self.assertEqual(audit["address_role"], "region membership only")


if __name__ == "__main__":
    unittest.main()

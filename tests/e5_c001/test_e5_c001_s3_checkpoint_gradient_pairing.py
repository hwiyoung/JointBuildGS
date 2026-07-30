#!/usr/bin/env python3
"""Focused CPU contract tests for the S3-A checkpoint-gradient supplement."""

from __future__ import annotations

import math
import unittest
from pathlib import Path
from types import SimpleNamespace

import torch

import e5_c001_s3_checkpoint_gradient_pairing as pairing
import e5_c001_s3_downstream as downstream


class _FakeCache:
    def __init__(self, frames: dict[str, object]):
        self.frames = frames
        self._cpu_cache: dict[str, object] = {}

    def get(self, name: str, _height: int, _width: int, _device: str) -> object:
        return self.frames[Path(name).stem]


def _state(count: int = 2) -> dict[str, torch.Tensor]:
    return {
        "means": torch.zeros((count, 3)),
        "quats": torch.zeros((count, 4)),
        "log_scales": torch.zeros((count, 2)),
        "opacities_raw": torch.zeros((count, 1)),
        "sh0": torch.zeros((count, 1, 3)),
        "shN": torch.zeros((count, 15, 3)),
        "sem_logits": torch.zeros((count, 4)),
    }


def _view_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for run_name in pairing.FULL_RUNS:
        for step in pairing.CHECKPOINT_STEPS:
            for building_id in pairing.ALL_TARGETS:
                for rank in range(1, 4):
                    rows.append(
                        {
                            "record_type": "fixed_view",
                            "claim_scope": pairing.CLAIM_SCOPE,
                            "measurement_mode": pairing.MEASUREMENT_MODE,
                            "plane_fit_scope": pairing.PLANE_FIT_SCOPE,
                            "view_selection_scope": pairing.VIEW_SELECTION_SCOPE,
                            "run_name": run_name,
                            "step": step,
                            "building_id": building_id,
                            "view_stem": f"{building_id}_v{rank}",
                            "view_rank": rank,
                            "address_pixel_count": 100 + rank,
                            "alpha_valid_pixel_count": 90 + rank,
                            "alpha_valid_fraction": 0.9,
                            "depth_anchor_pixel_count": 20 + rank,
                            "depth_anchor_fraction": 0.2,
                            "plane_valid_pixel_count": 80 + rank,
                            "plane_residual_huber_mean": 0.1 * rank,
                            "semdepth_depth_grad_norm": 0.01 * rank,
                            "semdepth_depth_grad_rms": 0.001 * rank,
                            "semdepth_depth_grad_norm_share": 0.1 * rank,
                            "semdepth_depth_grad_nonzero_pixel_count": 10 + rank,
                            "semdepth_depth_grad_nonzero_fraction": 0.1,
                            "view_semdepth_depth_grad_norm": 1.0,
                        }
                    )
    return rows


class CheckpointGradientPairingTests(unittest.TestCase):
    def test_oracle_cache_selector_replaces_prior_zero_address_top3(self) -> None:
        frames = [
            SimpleNamespace(name=f"view_{index}.png", height=2, width=3)
            for index in range(5)
        ]
        dataset = SimpleNamespace(frames=frames, downscale=1.0)
        pixel_counts = [5, 4, 0, 3, 2]
        cached = {}
        for index, pixel_count in enumerate(pixel_counts):
            region_ids = torch.zeros((2, 3), dtype=torch.int32)
            region_ids.flatten()[:pixel_count] = 1
            cached[f"view_{index}"] = SimpleNamespace(
                metadata={"regions": {"1": {"building_id": "DEBY_LOD2_1"}}},
                region_ids=region_ids,
                cutline_mask=torch.zeros((2, 3), dtype=torch.bool),
            )
        prior_reference_area_top3 = {"view_0", "view_1", "view_2"}
        self.assertEqual(pixel_counts[2], 0)
        selected, ranked = pairing.select_oracle_cache_fixed_views(
            dataset,
            _FakeCache(cached),
            targets=("1",),
        )
        self.assertEqual([row.view_stem for row in selected["1"]], ["view_0", "view_1", "view_3"])
        self.assertEqual([row.address_pixel_count for row in selected["1"]], [5, 4, 3])
        self.assertEqual([row.view_stem for row in ranked["1"]], ["view_0", "view_1", "view_3", "view_4"])
        self.assertIn("view_2", prior_reference_area_top3)
        self.assertNotIn("view_2", {row.view_stem for row in selected["1"]})

    def test_one_view_gradient_can_be_measured_for_multiple_buildings(self) -> None:
        depth = torch.tensor([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], requires_grad=True)
        weighted = 0.5 * (depth**2).sum()
        gradient = pairing.compute_semdepth_gradient(
            weighted_semdepth=weighted,
            depth_leaf=depth,
        )
        result = {
            "region_ids": torch.tensor([[1, 1, 2], [1, 2, 2]]),
            "cutline_mask": torch.zeros((2, 3), dtype=torch.bool),
            "region_rows": [
                {
                    "building_id": "DEBY_LOD2_A",
                    "region_id": 1,
                    "render_valid_pixel_count": 3,
                    "depth_anchor_pixel_count": 1,
                    "plane_valid_pixel_count": 3,
                    "plane_loss": 0.2,
                },
                {
                    "building_id": "DEBY_LOD2_B",
                    "region_id": 2,
                    "render_valid_pixel_count": 3,
                    "depth_anchor_pixel_count": 2,
                    "plane_valid_pixel_count": 3,
                    "plane_loss": 0.4,
                },
            ],
        }
        first = pairing.measure_target_gradient(gradient=gradient, result=result, building_id="A")
        second = pairing.measure_target_gradient(gradient=gradient, result=result, building_id="B")
        self.assertIsNone(depth.grad)
        self.assertFalse(gradient.requires_grad)
        self.assertAlmostEqual(first["semdepth_depth_grad_norm"], math.sqrt(21.0), places=6)
        self.assertAlmostEqual(second["semdepth_depth_grad_norm"], math.sqrt(70.0), places=6)
        self.assertAlmostEqual(
            first["semdepth_depth_grad_rms"],
            math.sqrt(21.0 / 3.0),
            places=6,
        )
        self.assertEqual(first["semdepth_depth_grad_nonzero_pixel_count"], 3)
        self.assertEqual(second["depth_anchor_pixel_count"], 2)

    def test_manifest_selection_provenance_records_full_candidates_and_recovery(self) -> None:
        ranked: dict[str, list[pairing.ViewCandidate]] = {}
        prior_rows: list[dict[str, str]] = []
        for building_id in pairing.ALL_TARGETS:
            ranked[building_id] = [
                pairing.ViewCandidate(
                    building_id=building_id,
                    dataset_index=rank,
                    view=f"{building_id}_v{rank}.png",
                    view_stem=f"{building_id}_v{rank}",
                    address_pixel_count=100 - rank,
                )
                for rank in range(1, 5)
            ]
            prior_stems = [row.view_stem for row in ranked[building_id][:3]]
            if building_id == "4908168":
                prior_stems[-1] = "DJI_20241217084851_0189_D"
            if building_id == "4907199":
                prior_stems[-1] = "DJI_20241217102653_0002_D"
            prior_rows.extend(
                {
                    "row_type": "view",
                    "building_id": f"DEBY_LOD2_{building_id}",
                    "view_stem": stem,
                    "selected_top3_by_reference_area": "True",
                }
                for stem in prior_stems
            )
        selected = {building_id: rows[:3] for building_id, rows in ranked.items()}
        provenance = pairing.build_view_selection_provenance(
            selected=selected,
            ranked_candidates=ranked,
            prior_audit_rows=prior_rows,
        )
        self.assertEqual(provenance["scope"], pairing.VIEW_SELECTION_SCOPE)
        self.assertEqual(
            {row["address_pixel_count"] for row in provenance["all_visible_candidates"]["4907202"]},
            {96, 97, 98, 99},
        )
        self.assertEqual(len(provenance["chosen"]["4907202"]), 3)
        self.assertEqual(len(provenance["preflight_recovery"]["prior_zero_address"]), 2)
        self.assertFalse(
            provenance["preflight_recovery"][
                "recovery_decision_used_checkpoint_or_gpu_results"
            ]
        )

    def test_frozen_checkpoint_facade_does_not_mutate_or_accumulate_gradients(self) -> None:
        model = pairing.FrozenCheckpointModel(_state(), sh_degree=3, device="cpu")
        before = model.state_signature()
        _ = model.scales, model.opacities, model.colors_sh()
        model.assert_frozen()
        self.assertEqual(model.state_signature(), before)
        for key in pairing.REQUIRED_STATE_KEYS:
            tensor = getattr(model, key)
            self.assertFalse(tensor.requires_grad)
            self.assertIsNone(tensor.grad)

    def test_exact_median_and_timeline_pair_coverage(self) -> None:
        views = _view_rows()
        self.assertEqual(len(views), 144)
        medians = pairing.build_median_rows(views)
        self.assertEqual(len(medians), 48)
        self.assertEqual(
            sum(row["record_type"] == "collapse_building_median" for row in medians),
            36,
        )
        self.assertEqual(
            sum(row["record_type"] == "organization_building_median" for row in medians),
            12,
        )
        timeline = [
            {
                "run_name": run_name,
                "step": step,
                "building_id": f"DEBY_LOD2_{building_id}",
                "ckpt": f"{run_name}/{step}",
                "n_gaussians_in_footprint": "42",
                "z_p50": "100",
                "z_std": "1",
                "opacity_p50": "0.5",
                "count_definition": "exact footprint",
            }
            for run_name in pairing.FULL_RUNS
            for step in pairing.CHECKPOINT_STEPS
            for building_id in pairing.COLLAPSE_TARGETS
        ]
        pairs = pairing.build_pair_rows(medians, timeline)
        self.assertEqual(len(pairs), 36)
        self.assertEqual(
            len({(row["run_name"], row["step"], row["building_id"]) for row in pairs}),
            36,
        )

    def test_downstream_inventory_contract_fails_when_pair_is_missing(self) -> None:
        views = _view_rows()
        medians = pairing.build_median_rows(views)
        timeline = [
            {
                "run_name": run_name,
                "step": step,
                "building_id": f"DEBY_LOD2_{building_id}",
                "ckpt": f"{run_name}/{step}",
                "n_gaussians_in_footprint": "42",
                "z_p50": "100",
                "z_std": "1",
                "opacity_p50": "0.5",
                "count_definition": "exact footprint",
            }
            for run_name in pairing.FULL_RUNS
            for step in pairing.CHECKPOINT_STEPS
            for building_id in pairing.COLLAPSE_TARGETS
        ]
        pairs = pairing.build_pair_rows(medians, timeline)
        combined = views + medians + pairs
        csv_rows = [
            {key: "" if value is None else str(value) for key, value in row.items()}
            for row in combined
        ]
        downstream._validate_final_artifact_contract(
            "checkpoint_gradient_pairing",
            downstream.CSV_CHECKPOINT_GRADIENT_PAIRING,
            csv_rows,
        )
        with self.assertRaisesRegex(RuntimeError, "timeline pairs"):
            downstream._validate_final_artifact_contract(
                "checkpoint_gradient_pairing",
                downstream.CSV_CHECKPOINT_GRADIENT_PAIRING,
                csv_rows[:-1],
            )

    def test_source_has_no_training_or_backward_entrypoint(self) -> None:
        source = pairing.SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertNotIn(".backward(", source)
        self.assertNotIn("torch.optim", source)
        self.assertNotIn("build_optimizers(", source)
        self.assertNotIn("strategy.step", source)


if __name__ == "__main__":
    unittest.main()

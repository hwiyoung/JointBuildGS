from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from src.stage3.c3_checkpoint_roofer_adapter_v1 import (
    C3CheckpointAdapterError,
    LOCAL_SHIFT_XYZ,
    load_c3_checkpoint,
    materialize_component_ready_evidence,
    validate_c3_checkpoint_mapping,
)


def _logits(label: int) -> list[float]:
    values = [-4.0, -4.0, -4.0, -4.0]
    values[label] = 4.0
    return values


def _checkpoint() -> dict:
    shift = np.asarray(LOCAL_SHIFT_XYZ)
    world = np.asarray(
        [
            [690792.20, 5335864.20, 615.0],  # group 0 roof; cell (0,0), selected class 6
            [690792.30, 5335864.30, 613.0],  # group 1 wall; same cell, lower
            [690792.40, 5335864.40, 606.0],  # group 2 terrain; same cell, higher
            [690792.50, 5335864.50, 604.5],  # group 3 terrain; same cell, selected class 2
            [690793.20, 5335864.20, 612.0],  # group 4 wall; cell (1,0), selected class 6
            [690790.00, 5335864.20, 616.0],  # group 5 roof; outside AOI
            [690794.20, 5335864.20, 610.0],  # group 6 background; dropped
            [690795.20, 5335864.20, 617.0],  # ungrouped roof; dropped
        ],
        dtype=np.float64,
    )
    labels = [1, 2, 3, 3, 2, 1, 0, 1]
    return {
        "it": 30000,
        "n_prim": len(world),
        "state_dict": {
            "means": torch.tensor(world - shift, dtype=torch.float32),
            "sem_logits": torch.tensor([_logits(value) for value in labels]),
            "opacities_raw": torch.tensor([-4.0, -2.0, 0.0, 2.0, 4.0, 0.0, 0.0, 0.0]),
        },
        "stage2_group_ids": torch.tensor([0, 1, 2, 3, 4, 5, 6, -1]),
        "stage2_rep_normals": torch.tensor(
            [
                [0.0, 0.0, 1.0],
                [1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0],
                [0.0, 0.0, 1.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [0.0, 0.0, 1.0],
            ]
        ),
        "stage2_rep_d": torch.arange(7, dtype=torch.float32),
    }


class C3CheckpointRooferAdapterTests(unittest.TestCase):
    def test_exact_stored_groups_materialize_deterministic_class26_cells(self) -> None:
        arrays = validate_c3_checkpoint_mapping(_checkpoint())
        result = materialize_component_ready_evidence(arrays)

        self.assertEqual(3, len(result.points))
        by_key = {(point.classification, point.ix, point.iy): point for point in result.points}
        building_0 = by_key[(6, 0, 0)]
        ground_0 = by_key[(2, 0, 0)]
        building_1 = by_key[(6, 1, 0)]
        self.assertEqual(0, building_0.source_primitive_index)
        self.assertEqual(1, building_0.semantic_class)
        self.assertAlmostEqual(690792.24, building_0.x, places=6)
        self.assertAlmostEqual(5335864.55, building_0.y, places=6)
        self.assertAlmostEqual(615.0, building_0.z, places=4)
        self.assertEqual("BUILDING_MAX_Z", building_0.selection_rule)
        self.assertEqual(3, ground_0.source_primitive_index)
        self.assertAlmostEqual(604.5, ground_0.z, places=4)
        self.assertEqual("TERRAIN_MIN_Z", ground_0.selection_rule)
        self.assertEqual(4, building_1.source_primitive_index)

        stats = result.lineage_stats
        self.assertEqual({"2": 1, "6": 2}, stats["output_class_counts"])
        self.assertEqual(7, stats["stored_stage2_group_count"])
        self.assertEqual(7, stats["stored_grouped_primitive_count"])
        self.assertEqual(1, stats["ungrouped_primitive_count"])
        self.assertEqual(1, stats["mapped_grouped_primitives_outside_aoi"])
        self.assertEqual(1, stats["grouped_background_dropped"])
        self.assertTrue(stats["stored_stage2_groups_reused_exact"])
        self.assertEqual(0, stats["regroup_invocation_count"])
        self.assertFalse(stats["opacity_used"])
        self.assertTrue(stats["low_opacity_primitives_are_not_filtered"])
        self.assertIn("p50", stats["stored_grouped_opacity_quantiles_diagnostic_only"])
        self.assertIsNone(stats["scientific_verdict"])
        self.assertIsNone(result.scientific_verdict)
        self.assertEqual(1, result.groups[0].selected_point_count)
        self.assertEqual(0, result.groups[1].selected_point_count)

    def test_exact_height_tie_prefers_roof_then_stable_source_order(self) -> None:
        checkpoint = _checkpoint()
        checkpoint["state_dict"]["means"][1] = checkpoint["state_dict"]["means"][0]
        arrays = validate_c3_checkpoint_mapping(checkpoint)
        result = materialize_component_ready_evidence(arrays)
        point = next(p for p in result.points if (p.classification, p.ix, p.iy) == (6, 0, 0))
        self.assertEqual(1, point.semantic_class)
        self.assertEqual(0, point.source_primitive_index)

    def test_safe_file_loader_accepts_synthetic_tensor_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.pt"
            torch.save(_checkpoint(), path)
            arrays = load_c3_checkpoint(path)
        self.assertEqual(30000, arrays.iteration)
        self.assertFalse(arrays.means.flags.writeable)
        self.assertFalse(arrays.group_ids.flags.writeable)

    def test_missing_or_malformed_stored_arrays_fail_closed(self) -> None:
        cases = []
        missing = _checkpoint()
        del missing["stage2_group_ids"]
        cases.append(missing)

        bad_length = _checkpoint()
        bad_length["stage2_group_ids"] = torch.tensor([0, 1])
        cases.append(bad_length)

        bad_index = _checkpoint()
        bad_index["stage2_group_ids"][0] = 99
        cases.append(bad_index)

        bad_normal = _checkpoint()
        bad_normal["stage2_rep_normals"][0] = torch.tensor([0.0, 0.0, 2.0])
        cases.append(bad_normal)

        mixed_group = _checkpoint()
        mixed_group["stage2_group_ids"][1] = 0
        cases.append(mixed_group)

        nonfinite = _checkpoint()
        nonfinite["state_dict"]["means"][0, 0] = float("nan")
        cases.append(nonfinite)

        for checkpoint in cases:
            with self.subTest(case=len(cases)):
                with self.assertRaises(C3CheckpointAdapterError):
                    validate_c3_checkpoint_mapping(checkpoint)

    def test_api_has_no_gt_or_reference_input(self) -> None:
        arrays = validate_c3_checkpoint_mapping(_checkpoint())
        with self.assertRaises(TypeError):
            materialize_component_ready_evidence(arrays, footprint={})  # type: ignore[call-arg]


if __name__ == "__main__":
    unittest.main()

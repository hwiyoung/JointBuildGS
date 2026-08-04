from __future__ import annotations

import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np
import torch

from scripts.p2.c3_utarget199_postprocess_v1.contract import (
    gaussian_point_cloud_ply,
    gaussian_surfel_mesh_ply,
    load_config,
    prepare_condition,
    validate_config,
)
from scripts.p2.c3_utarget199_postprocess_render_recovery_v1.recover_render import (
    complete as complete_render_recovery,
    recover as recover_render_payload,
)
from scripts.p2_baselines.c1_c2_feasibility_pilot_v1.contract import AddOnceStore
from src.stage2.renderer import _backgrounds_for_render


REPO = Path(__file__).resolve().parents[3]


def tiny_state() -> dict[str, torch.Tensor]:
    return {
        "means": torch.tensor([[0.0, 0.0, 1.0], [1.0, 2.0, 3.0]], dtype=torch.float32),
        "quats": torch.tensor([[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]], dtype=torch.float32),
        "log_scales": torch.log(torch.tensor([[0.5, 0.25, 1.0e-6], [1.0, 0.5, 1.0e-6]])),
        "opacities_raw": torch.tensor([0.0, 1.0], dtype=torch.float32),
        "sh0": torch.zeros((2, 1, 3), dtype=torch.float32),
        "sem_logits": torch.tensor([[0.0, 2.0, 0.0, 0.0], [0.0, 0.0, 2.0, 0.0]], dtype=torch.float32),
    }


class C3Utarget199PostprocessContractTest(unittest.TestCase):
    def test_rgb_expected_depth_background_appends_zero_depth_channel(self) -> None:
        background = _backgrounds_for_render(torch.ones(3), "RGB+ED")
        self.assertEqual(tuple(background.shape), (1, 4))
        self.assertEqual(background.tolist(), [[1.0, 1.0, 1.0, 0.0]])

    def test_rgb_background_keeps_three_channels(self) -> None:
        background = _backgrounds_for_render(torch.ones(3), "RGB")
        self.assertEqual(tuple(background.shape), (1, 3))

    def test_render_recovery_copies_exact_pre_render_payload_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "output"
            for relative in ("conditions", "freeze", "results", "control"):
                (source / relative).mkdir(parents=True)
            for index in range(25):
                terminal = source / f"conditions/C3/operations/{index:02d}/roofer_terminal_v1.json"
                terminal.parent.mkdir(parents=True, exist_ok=True)
                terminal.write_text("{}\n", encoding="utf-8")
            (source / "freeze/execution_units_v1.tsv").write_text("unit\n", encoding="utf-8")
            (source / "results/method_summary_v1.csv").write_text("condition\n", encoding="utf-8")
            for name in (
                "C3_1_SEM_geometry_frozen_v1.json",
                "C3_2_SEM_DEPTH_geometry_frozen_v1.json",
                "population_associated_v1.json",
            ):
                (source / "control" / name).write_text("{}\n", encoding="utf-8")
            (source / "control/finalized_v1.json").write_text(
                '{"result_rows":398}\n', encoding="utf-8"
            )
            recovered = recover_render_payload(source, output)
            self.assertEqual(recovered["roofer_terminal_count"], 25)
            self.assertEqual(recovered["result_rows"], 398)
            self.assertTrue((output / "results/method_summary_v1.csv").is_file())
            (output / "control/gs_render_complete_v1.json").write_text(
                '{"render_panel_count":8}\n', encoding="utf-8"
            )
            (output / "control/qualitative_complete_v1.json").write_text(
                '{"case_sheet_count":199}\n', encoding="utf-8"
            )
            completed = complete_render_recovery(output)
            self.assertEqual(completed["status"], "TECHNICAL_COMPLETE")
            self.assertEqual(completed["case_sheet_count"], 199)
            self.assertIsNone(completed["scientific_verdict"])

    def test_activated_config_has_exact_scope_and_closed_scientific_boundary(self) -> None:
        config = load_config()
        result = validate_config(config, require_activation=False)
        self.assertEqual(result["condition_ids"], ["C3_1_SEM", "C3_2_SEM_DEPTH"])
        self.assertEqual(result["result_rows"], 398)
        self.assertFalse(config["scope"]["visible_72_10_subgroup_rows"])
        self.assertFalse(config["scope"]["c4_c5_access_allowed"])
        self.assertFalse(config["roofer"]["external_roofprint_allowed"])
        self.assertIsNone(config["scientific_verdict"])
        self.assertIsNone(config["official_G3_G4_PASS_usable"])

    def test_activation_requires_exact_checkpoint_bindings(self) -> None:
        self.assertEqual(validate_config(load_config())["status"], "PASS")
        draft = json.loads(json.dumps(load_config()))
        draft["status"] = "DRAFT_AWAITING_EXACT_PAIRED_CHECKPOINT_BINDING"
        with self.assertRaisesRegex(RuntimeError, "not activated"):
            validate_config(draft)
        config = json.loads(json.dumps(load_config()))
        config["status"] = "APPROVED_FOR_EXECUTION"
        for row in config["conditions"]:
            row["expected_bytes"] = 123
            row["expected_sha256"] = "a" * 64
        self.assertEqual(validate_config(config)["status"], "PASS")

    def test_native_point_export_keeps_every_checkpoint_center(self) -> None:
        data = gaussian_point_cloud_ply(tiny_state(), (10.0, 20.0, 30.0))
        header, payload = data.split(b"end_header\n", 1)
        self.assertIn(b"element vertex 2", header)
        dtype = np.dtype([
            ("x", "<f8"), ("y", "<f8"), ("z", "<f8"),
            ("red", "u1"), ("green", "u1"), ("blue", "u1"),
            ("semantic_class", "u1"), ("opacity", "<f4"),
        ])
        rows = np.frombuffer(payload, dtype=dtype)
        self.assertEqual(len(rows), 2)
        np.testing.assert_allclose(rows["x"], [10.0, 11.0])
        np.testing.assert_allclose(rows["y"], [20.0, 22.0])
        np.testing.assert_allclose(rows["z"], [31.0, 33.0])
        self.assertEqual(rows["semantic_class"].tolist(), [1, 2])

    def test_surfel_mesh_is_exact_quad_per_gaussian(self) -> None:
        data = gaussian_surfel_mesh_ply(tiny_state(), (0.0, 0.0, 0.0))
        header, payload = data.split(b"end_header\n", 1)
        self.assertIn(b"element vertex 8", header)
        self.assertIn(b"element face 4", header)
        vertex_dtype = np.dtype([
            ("x", "<f8"), ("y", "<f8"), ("z", "<f8"),
            ("red", "u1"), ("green", "u1"), ("blue", "u1"),
            ("semantic_class", "u1"),
        ])
        face_dtype = np.dtype([("count", "u1"), ("indices", "<i4", (3,))])
        vertices = np.frombuffer(payload[: 8 * vertex_dtype.itemsize], dtype=vertex_dtype)
        faces = np.frombuffer(payload[8 * vertex_dtype.itemsize :], dtype=face_dtype)
        self.assertEqual(len(vertices), 8)
        self.assertEqual(len(faces), 4)
        self.assertTrue(np.all(faces["count"] == 3))
        self.assertEqual(faces["indices"].tolist(), [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]])

    def test_prepare_freezes_native_exports_before_identity_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoint = root / "final.pt"
            count = 4
            world = np.asarray([
                [690800.24 + (index % 2), 5335870.55 + (index // 2), 560.0 + 0.1 * index]
                for index in range(count)
            ])
            local = world - np.asarray([690953.0, 5336071.0, 604.0])
            state = {
                "means": torch.from_numpy(local.astype(np.float32)),
                "quats": torch.tensor([[1.0, 0.0, 0.0, 0.0]] * count),
                "log_scales": torch.log(torch.tensor([[0.5, 0.5, 1.0e-6]] * count)),
                "opacities_raw": torch.zeros(count),
                "sh0": torch.zeros((count, 1, 3)),
                "shN": torch.zeros((count, 15, 3)),
                "sem_logits": torch.tensor([[0.0, 3.0, 0.0, 0.0]] * count),
            }
            torch.save({
                "it": 30000,
                "n_prim": count,
                "state_dict": state,
                "stage2_group_ids": torch.zeros(count, dtype=torch.int64),
                "stage2_rep_normals": torch.tensor([[0.0, 0.0, 1.0]]),
                "stage2_rep_d": torch.tensor([-560.0]),
            }, checkpoint)
            data = checkpoint.read_bytes()
            config = json.loads(json.dumps(load_config()))
            config["status"] = "APPROVED_FOR_EXECUTION"
            spec = config["conditions"][0]
            spec["expected_bytes"] = len(data)
            spec["expected_sha256"] = hashlib.sha256(data).hexdigest()
            config["conditions"][1]["expected_bytes"] = 1
            config["conditions"][1]["expected_sha256"] = "b" * 64
            with mock.patch(
                "scripts.p2.c3_utarget199_postprocess_v1.contract.load_config",
                return_value=config,
            ):
                result = prepare_condition(
                    AddOnceStore(root / "output"),
                    condition_id="C3_1_SEM",
                    checkpoint_path=checkpoint,
                    source_commit="a" * 40,
                    run_id="synthetic",
                )
            self.assertEqual(result["status"], "FROZEN_BEFORE_BUILDING_IDENTITY_OR_REFERENCE_ACCESS")
            self.assertEqual(result["building_bbox_accesses"], 0)
            self.assertEqual(result["reference_cell_accesses"], 0)
            self.assertEqual(result["external_roofprint_accesses"], 0)
            self.assertEqual(result["component_count"], 1)
            self.assertEqual(result["roofer_eligible_component_count"], 1)
            self.assertTrue((root / "output/conditions/C3_1_SEM/intermediate/native_gaussian_centers_v1.ply").is_file())
            self.assertTrue((root / "output/conditions/C3_1_SEM/intermediate/native_gaussian_surfel_mesh_v1.ply").is_file())


if __name__ == "__main__":
    unittest.main()

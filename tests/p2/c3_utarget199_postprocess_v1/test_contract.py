from __future__ import annotations

import json
from pathlib import Path
import unittest

import numpy as np
import torch

from scripts.p2.c3_utarget199_postprocess_v1.contract import (
    gaussian_point_cloud_ply,
    gaussian_surfel_mesh_ply,
    load_config,
    validate_config,
)


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
    def test_draft_config_has_exact_scope_and_closed_scientific_boundary(self) -> None:
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
        with self.assertRaisesRegex(RuntimeError, "not activated"):
            validate_config(load_config())
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


if __name__ == "__main__":
    unittest.main()

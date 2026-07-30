#!/usr/bin/env python3
"""CPU tests for the first-wave trainer loss and audit contracts."""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image as PILImage
import torch

from src.stage2 import pilot_mask_schema as mask_schema
from src.stage2.dataloader import ColmapDataset, Frame, _bind_pilot_mask_manifest
from src.stage2.pilot_loss_audit import (
    PUBLIC_TERMS,
    absolute_shares,
    append_loss_share_rows,
    append_plane_photo_ratio,
    public_normal_term,
    structure_terms_in_scope,
)
from src.stage2.train import _validate_pilot_config_contract


def _digest(value: str) -> str:
    return mask_schema.sha256_bytes(value.encode("utf-8"))


def _frame(path: Path) -> Frame:
    return Frame(
        image_id=1,
        name=path.name,
        cam_id=1,
        image_path=path,
        depth_path=None,
        normal_path=None,
        mono_normal_path=None,
        mono_depth_path=None,
        depth_format=None,
        normal_format=None,
        mono_normal_format=None,
        mono_depth_format=None,
        K=np.eye(3, dtype=np.float64),
        R=np.eye(3, dtype=np.float64),
        t=np.zeros(3, dtype=np.float64),
        width=4,
        height=4,
    )


class PilotLossIntegrationTests(unittest.TestCase):
    def test_arm01_has_audit_scope_but_no_photo_loss_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "view.jpg"
            PILImage.fromarray(np.full((4, 4, 3), 127, dtype=np.uint8)).save(
                image_path
            )
            frame = _frame(image_path)
            mask = np.ones((4, 4), dtype=np.bool_)
            manifest = mask_schema.write_binary_mask_set(
                root / "mask_set",
                {frame.name: mask},
                purpose=mask_schema.MaskPurpose.PHOTO_SUPPORT,
                source=mask_schema.MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
                source_disclosure="unit-test projected footprint",
                input_sha256=_digest("input"),
                config_sha256=_digest("config"),
                geometry_sha256_by_view={frame.name: _digest("geometry")},
            )
            dataset = ColmapDataset.__new__(ColmapDataset)
            dataset.frames = [frame]
            dataset.downscale = 1.0
            dataset.load_depth = False
            dataset.load_normal = False
            dataset.load_semantic = False
            dataset.semantic_dir = root / "semantic"
            dataset.photo_mask_binding = None
            dataset.plane_region_mask_binding = None
            dataset.roof_audit_mask_binding = _bind_pilot_mask_manifest(
                manifest,
                frames=dataset.frames,
                downscale=1.0,
                pilot_arm="01_surface",
                role="roof_audit",
            )
            item = dataset[0]
            self.assertNotIn("photo_mask", item)
            self.assertIn("roof_audit_mask", item)
            self.assertTrue(bool(item["roof_audit_mask"].all()))
            self.assertFalse(dataset.roof_audit_mask_binding.audit["loss_consuming"])

    def test_public_normal_is_weighted_sum_not_target_replacement(self) -> None:
        primary = torch.tensor(2.0, requires_grad=True)
        auxiliary = torch.tensor(3.0, requires_grad=True)
        raw, weighted = public_normal_term(
            primary,
            auxiliary,
            primary_weight=0.15,
            auxiliary_weight=0.02,
        )
        self.assertAlmostEqual(float(raw), 5.0)
        self.assertAlmostEqual(float(weighted), 0.36, places=7)
        weighted.backward()
        self.assertAlmostEqual(float(primary.grad), 0.15, places=7)
        self.assertAlmostEqual(float(auxiliary.grad), 0.02, places=7)

    def test_fixed_share_schema_zero_rule_and_strong_ratio(self) -> None:
        zeros = {term: 0.0 for term in PUBLIC_TERMS}
        self.assertEqual(absolute_shares(zeros), zeros)
        raw = {term: float(index + 1) for index, term in enumerate(PUBLIC_TERMS)}
        weighted = {term: 0.0 for term in PUBLIC_TERMS}
        weighted["pho"] = 2.0
        weighted["plane"] = 1.0
        roof_weighted = dict(weighted)
        with tempfile.TemporaryDirectory() as directory:
            out_dir = Path(directory)
            append_loss_share_rows(
                out_dir,
                iteration=5000,
                raw=raw,
                weighted=weighted,
                roof_weighted=roof_weighted,
            )
            path = out_dir / "audit/pilot_loss_shares.csv"
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                self.assertEqual(
                    reader.fieldnames,
                    ["iter", "term", "raw", "weighted", "share", "roof_share"],
                )
            self.assertEqual([row["term"] for row in rows], list(PUBLIC_TERMS))
            by_term = {row["term"]: row for row in rows}
            self.assertAlmostEqual(float(by_term["pho"]["share"]), 2.0 / 3.0)
            self.assertAlmostEqual(float(by_term["plane"]["roof_share"]), 1.0 / 3.0)
            ratio = append_plane_photo_ratio(
                out_dir,
                iteration=5000,
                weighted_roof_plane=1.0,
                weighted_roof_photo=2.0,
            )
            self.assertEqual(ratio, 0.5)

    def test_structure_roof_scope_excludes_outside_primitive(self) -> None:
        normals = torch.tensor(
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]]
        )
        centers = torch.tensor(
            [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [9.0, 0.0, 0.0]]
        )
        group_ids = torch.tensor([0, 0, 0], dtype=torch.int64)
        rep_normals = torch.tensor([[1.0, 0.0, 0.0]])
        rep_d = torch.tensor([0.0])
        na, cp, count = structure_terms_in_scope(
            normals=normals,
            centers=centers,
            group_ids=group_ids,
            rep_normals=rep_normals,
            rep_d=rep_d,
            primitive_scope=torch.tensor([True, True, False]),
        )
        self.assertEqual(count, 2)
        self.assertAlmostEqual(float(na), 0.5)
        self.assertAlmostEqual(float(cp), 2.0)

    def test_strict_arm_contract_forbids_arm01_photo_and_hidden_distort(self) -> None:
        cfg = {
            "pilot_arm": "01_surface",
            "max_iter": 20000,
            "load_depth": True,
            "load_normal": True,
            "load_semantic": False,
            "mono_normal_dir": "/mono",
            "roof_audit_mask_manifest": "/masks/footprint.json",
            "structure_grouping": "g2_geometry",
            "w_photo": 1.0,
            "w_depth": 0.1,
            "w_normal": 0.15,
            "w_mono_normal_aux": 0.02,
            "w_nc": 0.05,
            "w_structure": 0.08,
            "w_structure_na": 1.0,
            "w_structure_cp": 1.0,
            "w_distort": 0.0,
            "w_sem": 0.0,
            "pilot_loss_audit_every": 100,
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
        self.assertEqual(_validate_pilot_config_contract(cfg, full_state), "01_surface")
        cfg["photo_mask_manifest"] = "/masks/footprint.json"
        with self.assertRaisesRegex(ValueError, "arm 01 forbids photo_mask_manifest"):
            _validate_pilot_config_contract(cfg, full_state)
        cfg.pop("photo_mask_manifest")
        cfg["w_distort"] = 1.0
        with self.assertRaisesRegex(ValueError, "forbids hidden/non-registered term"):
            _validate_pilot_config_contract(cfg, full_state)


if __name__ == "__main__":
    unittest.main()

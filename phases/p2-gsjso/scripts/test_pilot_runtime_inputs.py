#!/usr/bin/env python3
"""Unit tests for first-wave runtime mask binding and mono-normal gating."""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image as PILImage
import torch

from src.stage2 import pilot_mask_schema as schema
from src.stage2.dataloader import (
    ColmapDataset,
    Frame,
    _bind_pilot_mask_manifest,
    _resize_binary_mask,
)
from src.stage2.mono_normal_gate import (
    build_mono_normal_gate,
    l_auxiliary_mono_normal,
)


def digest(value: str) -> str:
    return schema.sha256_bytes(value.encode("utf-8"))


def make_frame(
    name: str,
    *,
    image_path: Path | None = None,
    height: int = 4,
    width: int = 4,
) -> Frame:
    return Frame(
        image_id=1,
        name=name,
        cam_id=1,
        image_path=image_path or Path(name),
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
        width=width,
        height=height,
    )


def write_set(
    root: Path,
    view_masks: dict[str, np.ndarray],
    *,
    purpose: schema.MaskPurpose,
    source: schema.MaskSource,
) -> Path:
    return schema.write_binary_mask_set(
        root,
        view_masks,
        purpose=purpose,
        source=source,
        source_disclosure="unit-test provenance disclosure",
        input_sha256=digest("input"),
        config_sha256=digest("config"),
        geometry_sha256_by_view={name: digest(name) for name in view_masks},
    )


class PilotRuntimeMaskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mask = np.asarray(
            [
                [True, True, False, False],
                [True, True, False, False],
                [False, False, True, True],
                [False, False, True, True],
            ],
            dtype=np.bool_,
        )
        self.frames = [make_frame("a.jpg"), make_frame("b.jpg")]

    def test_photo_source_and_consumer_arm_are_strict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            photo = write_set(
                root / "photo",
                {frame.name: self.mask for frame in self.frames},
                purpose=schema.MaskPurpose.PHOTO_SUPPORT,
                source=schema.MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
            )
            binding = _bind_pilot_mask_manifest(
                photo,
                frames=self.frames,
                downscale=0.5,
                pilot_arm="02_photo_control",
                role="photo",
            )
            np.testing.assert_array_equal(
                binding.load(self.frames[0], (2, 2)),
                np.asarray([[True, False], [False, True]], dtype=np.bool_),
            )
            self.assertEqual(binding.audit["resize_interpolation"], "nearest")
            with self.assertRaisesRegex(schema.MaskSchemaError, "not a declared consumer"):
                _bind_pilot_mask_manifest(
                    photo,
                    frames=self.frames,
                    downscale=1.0,
                    pilot_arm="01_surface",
                    role="photo",
                )
            with self.assertRaisesRegex(schema.MaskSchemaError, "pilot_arm is required"):
                _bind_pilot_mask_manifest(
                    photo,
                    frames=self.frames,
                    downscale=1.0,
                    pilot_arm=None,
                    role="photo",
                )

    def test_vision_plane_is_04a_and_gt_plane_is_04b_only(self) -> None:
        cases = (
            (
                schema.MaskSource.VISION_GROUNDEDSAM_ROOF,
                "04a_plane_medium_vision",
                "04b_plane_medium_gt_upperbound",
            ),
            (
                schema.MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND,
                "04b_plane_medium_gt_upperbound",
                "04a_plane_medium_vision",
            ),
        )
        for source, allowed_arm, forbidden_arm in cases:
            with self.subTest(source=source.value), tempfile.TemporaryDirectory() as directory:
                manifest = write_set(
                    Path(directory) / "plane",
                    {frame.name: self.mask for frame in self.frames},
                    purpose=schema.MaskPurpose.PLANE_REGION,
                    source=source,
                )
                binding = _bind_pilot_mask_manifest(
                    manifest,
                    frames=self.frames,
                    downscale=1.0,
                    pilot_arm=allowed_arm,
                    role="plane_region",
                )
                self.assertEqual(binding.audit["pilot_arm"], allowed_arm)
                with self.assertRaisesRegex(schema.MaskSchemaError, "source mismatch"):
                    _bind_pilot_mask_manifest(
                        manifest,
                        frames=self.frames,
                        downscale=1.0,
                        pilot_arm=forbidden_arm,
                        role="plane_region",
                    )

    def test_role_purpose_mismatch_hard_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = write_set(
                Path(directory) / "vision",
                {frame.name: self.mask for frame in self.frames},
                purpose=schema.MaskPurpose.PLANE_REGION,
                source=schema.MaskSource.VISION_GROUNDEDSAM_ROOF,
            )
            with self.assertRaisesRegex(schema.MaskSchemaError, "purpose mismatch"):
                _bind_pilot_mask_manifest(
                    manifest,
                    frames=self.frames,
                    downscale=1.0,
                    pilot_arm="04a_plane_medium_vision",
                    role="photo",
                )

    def test_outside_missing_and_archive_shape_issues_fail_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = write_set(
                root / "outside",
                {"a.jpg": self.mask, "outside.jpg": self.mask},
                purpose=schema.MaskPurpose.PHOTO_SUPPORT,
                source=schema.MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
            )
            with self.assertRaisesRegex(schema.MaskSchemaError, "outside/unknown"):
                _bind_pilot_mask_manifest(
                    outside,
                    frames=self.frames,
                    downscale=1.0,
                    pilot_arm="02_photo_control",
                    role="photo",
                )

            missing = write_set(
                root / "missing",
                {"a.jpg": self.mask},
                purpose=schema.MaskPurpose.PHOTO_SUPPORT,
                source=schema.MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
            )
            with self.assertRaisesRegex(schema.MaskSchemaError, "missing views"):
                _bind_pilot_mask_manifest(
                    missing,
                    frames=self.frames,
                    downscale=1.0,
                    pilot_arm="02_photo_control",
                    role="photo",
                )

            malformed = write_set(
                root / "malformed",
                {frame.name: self.mask for frame in self.frames},
                purpose=schema.MaskPurpose.PHOTO_SUPPORT,
                source=schema.MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
            )
            payload = json.loads(malformed.read_text(encoding="utf-8"))
            record_payload = payload["records"][0]
            archive = malformed.parent / record_payload["file"]
            archive.chmod(0o644)
            np.savez(archive, mask=np.ones((3, 4), dtype=np.bool_))
            record_payload["mask_sha256"] = schema.sha256_file(archive)
            records = [
                schema.MaskRecord(
                    view_id=raw["view_id"],
                    shape=tuple(raw["shape"]),
                    file=raw["file"],
                    mask_sha256=raw["mask_sha256"],
                    input_sha256=raw["input_sha256"],
                    config_sha256=raw["config_sha256"],
                    geometry_sha256=raw["geometry_sha256"],
                )
                for raw in payload["records"]
            ]
            payload["inventory_sha256"] = schema._inventory_sha256(
                records,
                schema.MaskPurpose.PHOTO_SUPPORT,
                schema.MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
                schema.PHOTO_SUPPORT_CONSUMER_ARMS,
            )
            malformed.chmod(0o644)
            malformed.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(schema.MaskSchemaError, "shape mismatch"):
                _bind_pilot_mask_manifest(
                    malformed,
                    frames=self.frames,
                    downscale=1.0,
                    pilot_arm="02_photo_control",
                    role="photo",
                )

            with self.assertRaisesRegex(schema.MaskSchemaError, "bool HxW"):
                _resize_binary_mask(np.ones((4, 4), dtype=np.uint8), (2, 2))

    def test_colmap_getitem_emits_both_bool_runtime_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "view.jpg"
            PILImage.fromarray(np.full((4, 4, 3), 128, dtype=np.uint8)).save(image_path)
            frame = make_frame("view.jpg", image_path=image_path)
            photo_manifest = write_set(
                root / "photo",
                {frame.name: self.mask},
                purpose=schema.MaskPurpose.PHOTO_SUPPORT,
                source=schema.MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
            )
            plane_manifest = write_set(
                root / "plane",
                {frame.name: self.mask},
                purpose=schema.MaskPurpose.PLANE_REGION,
                source=schema.MaskSource.VISION_GROUNDEDSAM_ROOF,
            )
            dataset = ColmapDataset.__new__(ColmapDataset)
            dataset.frames = [frame]
            dataset.downscale = 0.5
            dataset.load_depth = False
            dataset.load_normal = False
            dataset.load_semantic = False
            dataset.semantic_dir = root / "semantic"
            dataset.photo_mask_binding = _bind_pilot_mask_manifest(
                photo_manifest,
                frames=dataset.frames,
                downscale=dataset.downscale,
                pilot_arm="04a_plane_medium_vision",
                role="photo",
            )
            dataset.plane_region_mask_binding = _bind_pilot_mask_manifest(
                plane_manifest,
                frames=dataset.frames,
                downscale=dataset.downscale,
                pilot_arm="04a_plane_medium_vision",
                role="plane_region",
            )
            item = dataset[0]
            self.assertEqual(item["photo_mask"].dtype, torch.bool)
            self.assertEqual(item["plane_region_mask"].dtype, torch.bool)
            self.assertEqual(tuple(item["photo_mask"].shape), (2, 2))
            self.assertTrue(torch.equal(item["photo_mask"], item["plane_region_mask"]))


def normals_at_angle(angle_deg: float, height: int = 16, width: int = 16) -> torch.Tensor:
    radians = math.radians(angle_deg)
    vector = torch.tensor(
        [math.sin(radians), 0.0, math.cos(radians)], dtype=torch.float64
    )
    return vector.view(1, 1, 3).expand(height, width, 3).clone()


class MonoNormalGateTests(unittest.TestCase):
    def test_locked_angular_examples_and_exact_audit_counts(self) -> None:
        primary = normals_at_angle(0.0, width=48)
        auxiliary = torch.cat(
            [
                normals_at_angle(9.81),
                normals_at_angle(18.11),
                normals_at_angle(45.46),
            ],
            dim=1,
        )
        gate, audit = build_mono_normal_gate(primary, auxiliary)
        self.assertTrue(bool(gate[:, :16].all()))
        self.assertFalse(bool(gate[:, 16:].any()))
        self.assertEqual(audit["full_patch_count"], 3)
        self.assertEqual(audit["eligible_patch_count"], 1)
        self.assertEqual(audit["rejected_angle_patch_count"], 2)
        self.assertEqual(audit["rejected_insufficient_valid_patch_count"], 0)
        self.assertEqual(audit["mutual_valid_pixel_count"], 16 * 48)
        self.assertEqual(audit["gated_pixel_count"], 16 * 16)
        self.assertAlmostEqual(audit["patches"][0]["median_angle_deg"], 9.81, places=8)
        self.assertAlmostEqual(audit["patches"][1]["median_angle_deg"], 18.11, places=8)
        self.assertAlmostEqual(audit["patches"][2]["median_angle_deg"], 45.46, places=8)

    def test_mutual_valid_minimum_is_inclusive_and_border_is_excluded(self) -> None:
        primary = normals_at_angle(9.81, height=17, width=17)
        auxiliary = normals_at_angle(0.0, height=17, width=17)
        valid = torch.zeros((17, 17), dtype=torch.bool)
        valid[:4, :16] = True  # exactly 64 in the only full patch
        valid[16, 16] = True   # incomplete border never enters the gate
        gate, audit = build_mono_normal_gate(
            primary, auxiliary, primary_valid=valid, auxiliary_valid=valid
        )
        self.assertEqual(audit["eligible_patch_count"], 1)
        self.assertEqual(audit["gated_pixel_count"], 64)
        self.assertEqual(audit["border_mutual_valid_pixel_count"], 1)
        self.assertFalse(bool(gate[16, 16]))

        valid[3, 15] = False
        gate, audit = build_mono_normal_gate(
            primary, auxiliary, primary_valid=valid, auxiliary_valid=valid
        )
        self.assertFalse(bool(gate.any()))
        self.assertEqual(audit["rejected_insufficient_valid_patch_count"], 1)

    def test_bad_patch_auxiliary_loss_is_zero_with_exact_zero_gradient(self) -> None:
        primary = normals_at_angle(0.0)
        auxiliary = normals_at_angle(18.11)
        gate, audit = build_mono_normal_gate(primary, auxiliary)
        self.assertEqual(audit["eligible_patch_count"], 0)
        prediction = normals_at_angle(4.0).requires_grad_(True)
        loss = l_auxiliary_mono_normal(prediction, auxiliary, gate)
        self.assertEqual(float(loss.item()), 0.0)
        loss.backward()
        self.assertIsNotNone(prediction.grad)
        self.assertTrue(torch.equal(prediction.grad, torch.zeros_like(prediction.grad)))

    def test_angle_comparison_is_sign_invariant(self) -> None:
        primary = normals_at_angle(0.0)
        auxiliary = -normals_at_angle(9.81)
        gate, audit = build_mono_normal_gate(primary, auxiliary)
        self.assertTrue(bool(gate.all()))
        self.assertEqual(audit["eligible_patch_count"], 1)


if __name__ == "__main__":
    unittest.main()

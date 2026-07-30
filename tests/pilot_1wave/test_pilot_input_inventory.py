#!/usr/bin/env python3
"""Focused no-training tests for the first-wave materialized-input gates."""
from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from src.stage2.pilot_input_inventory import (
    PilotInputInventoryError,
    build_materialized_input_inventory,
    validate_pilot_config_materialized_inputs,
)


REPO = Path(__file__).resolve().parents[3]


def _write_colmap_images(path: Path, names: list[str]) -> None:
    payload = bytearray(struct.pack("<Q", len(names)))
    for image_id, name in enumerate(names, start=1):
        payload.extend(struct.pack("<I", image_id))
        payload.extend(struct.pack("<dddd", 1.0, 0.0, 0.0, 0.0))
        payload.extend(struct.pack("<ddd", 0.0, 0.0, 0.0))
        payload.extend(struct.pack("<I", 1))
        payload.extend(name.encode("utf-8") + b"\0")
        payload.extend(struct.pack("<Q", 0))
    path.write_bytes(bytes(payload))


class InventoryFixture:
    def __init__(
        self,
        root: Path,
        *,
        colmap_views: list[str] | None = None,
        inventory_views: list[str] | None = None,
    ) -> None:
        self.repo = root
        self.data_root = root / "locked/data"
        self.mono_dir = root / "locked/mono"
        self.inventory_path = root / "locked/materialized_input_inventory.json"
        colmap_views = colmap_views or ["view.png"]
        inventory_views = inventory_views or ["view.png"]
        for directory in (
            self.data_root / "images",
            self.data_root / "sparse/0",
            self.data_root / "stereo/depth_maps",
            self.data_root / "stereo/normal_maps",
            self.mono_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        (self.data_root / "sparse/0/cameras.bin").write_bytes(b"cameras")
        _write_colmap_images(
            self.data_root / "sparse/0/images.bin", colmap_views
        )
        (self.data_root / "sparse/0/points3D.bin").write_bytes(b"points")
        for view in inventory_views:
            (self.data_root / "images" / view).write_bytes(b"rgb")
            (self.data_root / "stereo/depth_maps" / f"{view}.geometric.bin").write_bytes(
                b"depth"
            )
            (self.data_root / "stereo/normal_maps" / f"{view}.geometric.bin").write_bytes(
                b"normal"
            )
            (self.mono_dir / f"{Path(view).stem}.npy").write_bytes(b"omnidata")
        payload = build_materialized_input_inventory(
            repo=self.repo,
            data_root=self.data_root,
            mono_dir=self.mono_dir,
            view_ids=inventory_views,
        )
        self.inventory_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.inventory_sha256 = hashlib.sha256(
            self.inventory_path.read_bytes()
        ).hexdigest()
        self.cfg = {
            "data_root": str(self.data_root),
            "mono_normal_dir": str(self.mono_dir),
            "normal_dir": None,
            "normal_encoding": "half_range",
            "pilot_materialized_input_inventory_path": str(self.inventory_path),
            "pilot_materialized_input_inventory_sha256": self.inventory_sha256,
        }


class PilotInputInventoryTests(unittest.TestCase):
    def test_full_sha_and_exact_colmap_view_inventory_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = InventoryFixture(Path(tmp))
            audit = validate_pilot_config_materialized_inputs(
                fixture.cfg, repo=fixture.repo
            )
        self.assertEqual(audit["status"], "passed")
        self.assertEqual(audit["view_count"], 1)
        self.assertEqual(audit["file_count"], 7)
        self.assertEqual(audit["role_counts"]["rgb"], 1)
        self.assertEqual(
            audit["view_identity"], "exact_sorted_colmap_images_bin_names"
        )

    def test_same_size_byte_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = InventoryFixture(Path(tmp))
            (fixture.data_root / "images/view.png").write_bytes(b"rbg")
            with self.assertRaisesRegex(PilotInputInventoryError, "SHA256 drifted"):
                validate_pilot_config_materialized_inputs(
                    fixture.cfg, repo=fixture.repo
                )

    def test_inventory_must_cover_exact_colmap_view_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = InventoryFixture(
                Path(tmp),
                colmap_views=["view.png"],
                inventory_views=["other.png"],
            )
            with self.assertRaisesRegex(
                PilotInputInventoryError, "do not equal the pinned COLMAP"
            ):
                validate_pilot_config_materialized_inputs(
                    fixture.cfg, repo=fixture.repo
                )

    def test_config_roots_and_visible_views_are_exact_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = InventoryFixture(Path(tmp))
            wrong_mono = fixture.repo / "locked/wrong_mono"
            wrong_mono.mkdir()
            bad_root = {**fixture.cfg, "mono_normal_dir": str(wrong_mono)}
            with self.assertRaisesRegex(
                PilotInputInventoryError, "mono_normal_dir mismatch"
            ):
                validate_pilot_config_materialized_inputs(
                    bad_root, repo=fixture.repo
                )
            bad_views = {**fixture.cfg, "visible_views": []}
            with self.assertRaisesRegex(PilotInputInventoryError, "visible_views"):
                validate_pilot_config_materialized_inputs(
                    bad_views, repo=fixture.repo
                )
            override_dir = fixture.repo / "locked/override_normals"
            override_dir.mkdir()
            bad_override = {**fixture.cfg, "normal_dir": str(override_dir)}
            with self.assertRaisesRegex(PilotInputInventoryError, "normal_dir must be null"):
                validate_pilot_config_materialized_inputs(
                    bad_override, repo=fixture.repo
                )
            bad_encoding = {**fixture.cfg, "normal_encoding": "raw"}
            with self.assertRaisesRegex(
                PilotInputInventoryError, "normal_encoding must be"
            ):
                validate_pilot_config_materialized_inputs(
                    bad_encoding, repo=fixture.repo
                )

    def test_symlink_alias_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = InventoryFixture(Path(tmp))
            alias = fixture.repo / "locked/inventory_alias.json"
            alias.symlink_to(fixture.inventory_path)
            cfg = {
                **fixture.cfg,
                "pilot_materialized_input_inventory_path": str(alias),
            }
            with self.assertRaisesRegex(PilotInputInventoryError, "symlink"):
                validate_pilot_config_materialized_inputs(cfg, repo=fixture.repo)

    def test_train_orders_both_gates_around_all_writable_completion_state(self) -> None:
        source = (REPO / "src/stage2/train.py").read_text(encoding="utf-8")
        main_source = source[source.index("def main():") :]
        first_gate = main_source.index("validate_pilot_config_materialized_inputs(cfg)")
        self.assertLess(first_gate, main_source.index("out_dir.mkdir"))
        self.assertLess(first_gate, main_source.index("ColmapDataset("))
        self.assertLess(first_gate, main_source.index("GaussianModel2D("))
        completion_gate = main_source.rindex(
            "validate_pilot_config_materialized_inputs(cfg)"
        )
        completed_true = main_source.index(
            'full_state_manifest["process_completed"] = True'
        )
        self.assertLess(completion_gate, completed_true)
        self.assertIn(
            'full_state_manifest["process_completed"] = False', main_source
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

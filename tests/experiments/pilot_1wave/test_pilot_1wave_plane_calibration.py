#!/usr/bin/env python3
"""Contract tests for the pre-optimizer plane calibration publisher."""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import yaml


REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO / "scripts/pilot_1wave"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pilot_1wave_plane_calibration as calibration
import pilot_1wave_resolved_configs as resolver
from src.stage2.pilot_mask_schema import (
    MaskPurpose,
    MaskSource,
    write_binary_mask_set,
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_relative(path: Path) -> str:
    return str(path.resolve().relative_to(calibration.REPO.resolve()))


class SyntheticBackend:
    def __init__(
        self,
        *,
        eligible_count: int = 16,
        reverse_views: bool = False,
        nonzero_optimizer_audit: bool = False,
        failing_04b_ratio: bool = False,
        mutate_first_config: bool = False,
    ) -> None:
        self.eligible_count = eligible_count
        self.reverse_views = reverse_views
        self.nonzero_optimizer_audit = nonzero_optimizer_audit
        self.failing_04b_ratio = failing_04b_ratio
        self.mutate_first_config = mutate_first_config
        self.calls: list[str] = []

    def evaluate(self, binding, *, view_ids, lock):
        del lock
        self.calls.append(binding.condition_id)
        if self.mutate_first_config and len(self.calls) == 1:
            binding.config_path.write_text(
                binding.config_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
        ordered = list(reversed(view_ids)) if self.reverse_views else list(view_ids)
        values = {
            "03": (2.0, 4.0),
            "04a": (4.0, 2.0),
            "04b": ((1.0, 10.0) if self.failing_04b_ratio else (4.0, 2.0)),
        }
        photo, plane = values[binding.condition_id]
        rows = []
        for index, view_id in enumerate(ordered):
            eligible = index < self.eligible_count
            rows.append(
                calibration.ForwardMeasurement(
                    condition_id=binding.condition_id,
                    view_id=view_id,
                    weighted_roof_photo=photo if eligible else None,
                    raw_roof_plane=plane if eligible else None,
                    plane_count=1 if eligible else 0,
                    plane_point_count=16 if eligible else 0,
                    eligible=eligible,
                    reason="eligible" if eligible else "synthetic_ineligible",
                )
            )
        return rows, {
            "backend_id": calibration.SYNTHETIC_BACKEND_ID,
            "synthetic": True,
            "forward_only": True,
            "optimizer_objects_created": 1 if self.nonzero_optimizer_audit else 0,
            "backward_calls": 0,
            "optimizer_updates": 0,
        }


class SyntheticContract:
    """Small but byte-complete scaffold bundle and mask/input inventories."""

    def __init__(self, root: Path, *, geometry_drift_04b: bool = False) -> None:
        self.root = root
        self.root.mkdir(parents=True)
        self.official_lock = calibration.load_calibration_lock()
        self.calibration_views = list(
            self.official_lock["view_selection"]["calibration_view_ids"]
        )
        self.inventory_views = sorted(self.calibration_views)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        self.dense_seed = self.inputs / "dense_seed.ply"
        self.dense_seed.write_bytes(b"synthetic dense seed\n")
        geometry = {
            view_id: hashlib.sha256(f"geometry:{view_id}".encode()).hexdigest()
            for view_id in self.inventory_views
        }
        masks = {
            view_id: np.pad(
                np.ones((2, 3), dtype=np.bool_),
                ((1, 1), (1, 1)),
                constant_values=False,
            )
            for view_id in self.inventory_views
        }
        self.common_mask = write_binary_mask_set(
            self.inputs / "common_masks",
            masks,
            purpose=MaskPurpose.PHOTO_SUPPORT,
            source=MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
            source_disclosure="synthetic contract fixture",
            input_sha256="1" * 64,
            config_sha256="2" * 64,
            geometry_sha256_by_view=geometry,
        )
        self.mask_04a = write_binary_mask_set(
            self.inputs / "plane_04a",
            masks,
            purpose=MaskPurpose.PLANE_REGION,
            source=MaskSource.VISION_GROUNDEDSAM_ROOF,
            source_disclosure="synthetic vision contract fixture",
            input_sha256="3" * 64,
            config_sha256="4" * 64,
            geometry_sha256_by_view=geometry,
        )
        geometry_04b = dict(geometry)
        if geometry_drift_04b:
            geometry_04b[self.inventory_views[0]] = "f" * 64
        self.mask_04b = write_binary_mask_set(
            self.inputs / "plane_04b",
            masks,
            purpose=MaskPurpose.PLANE_REGION,
            source=MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND,
            source_disclosure="synthetic GT upper-bound contract fixture",
            input_sha256="5" * 64,
            config_sha256="6" * 64,
            geometry_sha256_by_view=geometry_04b,
        )
        self.data_root = self.inputs / "data"
        self.mono_dir = self.inputs / "mono"
        self._write_materialized_files()
        self.lock_path = self.inputs / "calibration_lock.json"
        lock = copy.deepcopy(self.official_lock)
        lock["input_bindings"]["dense_seed"] = {
            "path": repo_relative(self.dense_seed),
            "sha256": sha256_file(self.dense_seed),
        }
        lock["input_bindings"]["projected_footprint_mask_manifest"] = {
            "path": repo_relative(self.common_mask),
            "sha256": sha256_file(self.common_mask),
        }
        self.lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
        self.bundle = self.root / "scaffolds"
        self.bundle.mkdir()
        self.inventory = resolver.build_materialized_input_inventory(
            repo=calibration.REPO,
            data_root=self.data_root,
            mono_dir=self.mono_dir,
            view_ids=self.inventory_views,
        )
        self.inventory_path = self.bundle / "materialized_input_inventory.json"
        self.inventory_path.write_text(
            json.dumps(self.inventory, indent=2) + "\n", encoding="utf-8"
        )
        self.config_paths = self._write_configs()
        self.manifest_path = self._write_manifest()
        self._freeze_bundle()

    def _write_materialized_files(self) -> None:
        sparse = self.data_root / "sparse/0"
        sparse.mkdir(parents=True)
        for name in ("cameras.bin", "images.bin", "points3D.bin"):
            (sparse / name).write_bytes(f"synthetic {name}\n".encode())
        (self.data_root / "images").mkdir()
        (self.data_root / "stereo/depth_maps").mkdir(parents=True)
        (self.data_root / "stereo/normal_maps").mkdir(parents=True)
        self.mono_dir.mkdir()
        for view_id in self.inventory_views:
            (self.data_root / "images" / view_id).write_bytes(f"rgb:{view_id}".encode())
            (self.data_root / "stereo/depth_maps" / f"{view_id}.geometric.bin").write_bytes(
                f"depth:{view_id}".encode()
            )
            (self.data_root / "stereo/normal_maps" / f"{view_id}.geometric.bin").write_bytes(
                f"normal:{view_id}".encode()
            )
            (self.mono_dir / f"{Path(view_id).stem}.npy").write_bytes(
                f"mono:{view_id}".encode()
            )

    def _base_config(self, condition: str) -> dict[str, object]:
        recipe = self.official_lock["base_recipe"]
        primitive = self.official_lock["plane_primitive"]
        arm = calibration.CONDITION_ARM[condition]
        return {
            "pilot_calibration_scaffold_schema": calibration.SCAFFOLD_SCHEMA,
            "pilot_calibration_only": True,
            "pilot_calibration_optimizer_objects_created": 0,
            "pilot_calibration_backward_calls": 0,
            "pilot_calibration_optimizer_updates": 0,
            "pilot_run_id": calibration.RUN_ID,
            "pilot_condition": condition,
            "pilot_arm": arm,
            "pilot_job_id": f"calibration_{condition}_seed1001",
            "pilot_calibration_lock_path": str(self.lock_path),
            "pilot_calibration_lock_sha256": sha256_file(self.lock_path),
            "pilot_materialized_input_inventory_path": str(self.inventory_path),
            "pilot_materialized_input_inventory_sha256": sha256_file(self.inventory_path),
            "seed": 1001,
            "device": "cuda",
            "data_root": str(self.data_root),
            "init_pointcloud": str(self.dense_seed),
            "init_pointcloud_mode": "concat",
            "mvs_seed_init_opacity": 0.25,
            "downscale": 1.0,
            "sh_degree": 3,
            "max_iter": 20000,
            "load_depth": True,
            "load_normal": True,
            "load_semantic": False,
            "seed_semantic": False,
            "normal_dir": None,
            "normal_encoding": "half_range",
            "depth_scale": 1.0,
            "mono_normal_dir": str(self.mono_dir),
            "mono_normal_loss": "global",
            "w_photo": recipe["w_photo"],
            "photo_lam": recipe["photo_lam"],
            "w_depth": recipe["w_depth"],
            "w_normal": recipe["w_normal_mvs"],
            "w_mono_normal_aux": recipe["w_mono_normal_aux"],
            "pilot_plane_window_size": primitive["window_size_px"],
            "pilot_plane_stride": primitive["stride_px"],
            "pilot_plane_min_points": primitive["minimum_points"],
            "pilot_plane_alpha_threshold": primitive["alpha_threshold"],
            "pilot_plane_max_depth_range": primitive["maximum_depth_range_m"],
            "pilot_plane_min_second_eigenvalue": primitive["minimum_second_eigenvalue"],
            "photo_mask_manifest": str(self.common_mask),
            "roof_audit_mask_manifest": str(self.common_mask),
        }

    def _write_configs(self) -> dict[str, Path]:
        paths: dict[str, Path] = {}
        for condition in ("03", "04a", "04b"):
            config = self._base_config(condition)
            if condition in {"04a", "04b"}:
                mask = self.mask_04a if condition == "04a" else self.mask_04b
                config.update(
                    {
                        "plane_region_mask_manifest": str(mask),
                        "pilot_plane_region_source": calibration.PLANE_MASK_SOURCE[condition],
                        "pilot_plane_region_manifest_sha256": sha256_file(mask),
                    }
                )
                initialization = self.official_lock["plane_guided_initialization"]
                for key in (
                    "pilot_plane_init_stride_px",
                    "pilot_plane_init_grid_offset_px",
                    "pilot_plane_init_knn",
                    "pilot_plane_init_tolerance_m",
                    "pilot_plane_init_min_coverage",
                    "pilot_plane_init_query_chunk_size",
                ):
                    config[key] = initialization[key]
            path = self.bundle / f"calibration_{condition}_seed1001.yaml"
            path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
            paths[condition] = path
        return paths

    def _write_manifest(self) -> Path:
        manifest = {
            "schema": calibration.SCAFFOLD_MANIFEST_SCHEMA,
            "run_id": calibration.RUN_ID,
            "state": "prepared_forward_only",
            "pilot_calibration_only": True,
            "learning_runs_started": 0,
            "optimizer_audit": {
                "optimizer_objects_created": 0,
                "backward_calls": 0,
                "optimizer_updates": 0,
            },
            "calibration_seed": 1001,
            "inputs": {
                "materialized_input_inventory": {
                    "path": repo_relative(self.inventory_path),
                    "sha256": sha256_file(self.inventory_path),
                    "records_sha256": self.inventory["records_sha256"],
                    "file_count": self.inventory["file_count"],
                    "total_bytes": self.inventory["total_bytes"],
                }
            },
            "pair_control": {"passed": True},
            "config_count": 3,
            "configs": [
                {
                    "condition": condition,
                    "pilot_arm": calibration.CONDITION_ARM[condition],
                    "seed": 1001,
                    "path": repo_relative(self.config_paths[condition]),
                    "sha256": sha256_file(self.config_paths[condition]),
                }
                for condition in ("03", "04a", "04b")
            ],
        }
        path = self.bundle / "calibration_scaffolds_manifest.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return path

    def _freeze_bundle(self) -> None:
        for child in self.bundle.iterdir():
            child.chmod(0o444)
        self.bundle.chmod(0o555)

    def run(self, backend: SyntheticBackend, *, output_name: str = "receipt.json"):
        return calibration._run_synthetic_calibration_for_test(
            config_paths=self.config_paths,
            calibration_seed=1001,
            output=self.root / output_name,
            backend=backend,
            scaffold_manifest_path=self.manifest_path,
            scaffold_manifest_sha256=sha256_file(self.manifest_path),
            lock_path=self.lock_path,
        )


class PlaneCalibrationTests(unittest.TestCase):
    def setUp(self) -> None:
        parent = calibration.REPO / "phases/p2-gsjso/runs"
        self.temp = Path(tempfile.mkdtemp(prefix=".p1w_calibration_test_", dir=parent))
        self.fixture = SyntheticContract(self.temp / "fixture")

    def tearDown(self) -> None:
        for root, directories, files in os.walk(self.temp):
            for name in directories:
                Path(root, name).chmod(0o755)
            for name in files:
                Path(root, name).chmod(0o644)
        shutil.rmtree(self.temp)

    def test_synthetic_path_can_never_publish_an_official_receipt(self) -> None:
        backend = SyntheticBackend()
        receipt = self.fixture.run(backend)
        self.assertEqual(backend.calls, ["03", "04a", "04b"])
        self.assertEqual(receipt["schema"], calibration.SYNTHETIC_RECEIPT_SCHEMA)
        self.assertEqual(receipt["state"], "nonofficial_test_only")
        self.assertFalse(receipt["official"])
        self.assertEqual(
            receipt["backend"],
            {"id": calibration.SYNTHETIC_BACKEND_ID, "synthetic": True},
        )
        self.assertTrue(receipt["runtime_attestation"]["synthetic"])
        self.assertAlmostEqual(receipt["resolved_weights"]["03"]["w_plane"], 0.125)
        self.assertAlmostEqual(receipt["resolved_weights"]["04a"]["w_plane"], 2.0)
        self.assertEqual(
            receipt["resolved_weights"]["04a"]["w_plane"],
            receipt["resolved_weights"]["04b"]["w_plane"],
        )
        self.assertTrue(
            receipt["input_validation"]["verified_before_and_after_forward"]
        )
        self.assertTrue(
            receipt["input_validation"][
                "common_04a_04b_view_shape_geometry_exact"
            ]
        )

    def test_downstream_resolver_rejects_synthetic_receipt(self) -> None:
        self.fixture.run(SyntheticBackend())
        with self.assertRaisesRegex(resolver.ContractError, "receipt schema"):
            resolver.validate_receipt(
                calibration.REPO,
                self.fixture.root / "receipt.json",
                self.fixture.lock_path,
                json.loads(self.fixture.lock_path.read_text()),
            )

    def test_official_entrypoint_has_no_backend_injection_parameter(self) -> None:
        self.assertNotIn("backend", inspect.signature(calibration.run_calibration).parameters)
        source = inspect.getsource(calibration.run_calibration)
        self.assertIn("Stage2ForwardBackend()", source)

    def test_full_receipt_binds_scaffold_inventory_masks_and_code(self) -> None:
        receipt = self.fixture.run(SyntheticBackend())
        inputs = receipt["inputs"]
        for name in (
            "calibration_lock",
            "calibration_scaffolds_manifest",
            "materialized_input_inventory",
            "dense_seed",
        ):
            self.assertEqual(set(inputs[name]), {"path", "sha256"})
        for group in ("configs", "masks", "code"):
            for binding in inputs[group].values():
                path = Path(binding["path"])
                if not path.is_absolute():
                    path = calibration.REPO / path
                self.assertEqual(sha256_file(path), binding["sha256"])
        self.assertIn("colmap_io", inputs["code"])
        self.assertIn("config_resolver", inputs["code"])

    def test_canonical_scaffold_fields_are_exact(self) -> None:
        binding = calibration.validate_condition_binding(
            "03",
            self.fixture.config_paths["03"],
            lock=json.loads(self.fixture.lock_path.read_text()),
            lock_path=self.fixture.lock_path,
            calibration_seed=1001,
            materialized_inventory_path=self.fixture.inventory_path,
            materialized_inventory=self.fixture.inventory,
        )
        self.assertEqual(binding.config["init_pointcloud_mode"], "concat")
        self.assertEqual(binding.config["mvs_seed_init_opacity"], 0.25)
        self.assertEqual(binding.config["downscale"], 1.0)
        self.assertEqual(binding.config["sh_degree"], 3)
        self.assertTrue(binding.config["load_depth"])
        self.assertTrue(binding.config["load_normal"])
        self.assertEqual(binding.config["normal_dir"], None)
        self.assertEqual(binding.config["mono_normal_loss"], "global")

    def test_full_mask_payload_tamper_hard_fails(self) -> None:
        payload = json.loads(self.fixture.mask_04a.read_text())
        mask_path = self.fixture.mask_04a.parent / payload["records"][0]["file"]
        mask_path.chmod(0o644)
        mask_path.write_bytes(mask_path.read_bytes() + b"tamper")
        with self.assertRaisesRegex(Exception, "mask SHA mismatch"):
            self.fixture.run(SyntheticBackend())

    def test_common_04_pair_geometry_drift_hard_fails(self) -> None:
        drift = SyntheticContract(self.temp / "geometry_drift", geometry_drift_04b=True)
        with self.assertRaisesRegex(RuntimeError, "04b/common view-shape-geometry"):
            drift.run(SyntheticBackend())

    def test_materialized_input_tamper_hard_fails(self) -> None:
        record = self.fixture.inventory["records"][3]
        path = calibration.REPO / record["path"]
        path.write_bytes(path.read_bytes() + b"tamper")
        with self.assertRaisesRegex(Exception, "input size|input SHA256"):
            self.fixture.run(SyntheticBackend())

    def test_input_mutation_during_forward_hard_fails(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "scaffold config SHA256 drift"):
            self.fixture.run(SyntheticBackend(mutate_first_config=True))

    def test_scaffold_bundle_modes_are_required(self) -> None:
        self.fixture.bundle.chmod(0o755)
        with self.assertRaisesRegex(RuntimeError, "scaffold bundle mode drift"):
            self.fixture.run(SyntheticBackend())

    def test_fewer_than_eight_eligible_views_hard_fails(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "eligible views below lock"):
            self.fixture.run(SyntheticBackend(eligible_count=7))

    def test_fixed_view_order_drift_hard_fails(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "fixed view order"):
            self.fixture.run(SyntheticBackend(reverse_views=True))

    def test_medium_04b_gate_fails_without_retuning(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "without retuning"):
            self.fixture.run(SyntheticBackend(failing_04b_ratio=True))

    def test_nonzero_optimizer_audit_hard_fails(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "optimizer_objects_created"):
            self.fixture.run(SyntheticBackend(nonzero_optimizer_audit=True))

    def test_any_existing_output_including_zero_bytes_is_rejected(self) -> None:
        output = self.fixture.root / "zero.json"
        output.touch()
        with self.assertRaisesRegex(RuntimeError, "refusing to overwrite"):
            self.fixture.run(SyntheticBackend(), output_name="zero.json")
        self.assertEqual(output.read_bytes(), b"")

    def test_published_receipt_is_host_readable_immutable(self) -> None:
        self.fixture.run(SyntheticBackend())
        output = self.fixture.root / "receipt.json"
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o444)
        self.assertTrue(os.access(output, os.R_OK))
        self.assertFalse(any(output.parent.glob(f".{output.name}.*.tmp")))

    def test_locked_runtime_and_code_boundary_are_exact(self) -> None:
        lock = calibration.load_calibration_lock()
        self.assertEqual(lock["forward_runtime"], calibration.OFFICIAL_RUNTIME)
        self.assertEqual(
            lock["forward_runtime"]["image_id"],
            "sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396",
        )
        self.assertEqual(lock["forward_runtime"]["python"], "3.11.15")
        self.assertEqual(lock["forward_runtime"]["torch"], "2.4.1+cu121")
        self.assertEqual(lock["forward_runtime"]["cuda"], "12.1")

    def test_runner_source_has_no_optimizer_or_update_calls(self) -> None:
        source = Path(calibration.__file__).read_text(encoding="utf-8")
        self.assertNotIn("build_optimizers(", source)
        self.assertNotIn("torch.optim", source)
        self.assertNotIn(".backward(", source)
        self.assertNotIn("optimizer.step(", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)

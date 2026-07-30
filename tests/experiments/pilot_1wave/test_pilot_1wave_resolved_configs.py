#!/usr/bin/env python3
"""Synthetic contract tests for the two-stage P1W config resolver."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest

import numpy as np
import yaml

from src.stage2.pilot_mask_schema import (
    MaskPurpose,
    MaskSource,
    write_binary_mask_set,
)


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts/pilot_1wave/pilot_1wave_resolved_configs.py"
SPEC = importlib.util.spec_from_file_location("pilot_1wave_resolved_configs", SCRIPT)
resolver = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(resolver)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def binding(repo: Path, path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(repo)), "sha256": digest(path)}


class SyntheticContract:
    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.run = repo / "phases/p2-gsjso/runs/20260721_pilot_1wave"
        self.prep = self.run / "prep_artifacts"
        (self.prep / "data").mkdir(parents=True)
        (self.prep / "mono").mkdir()
        self.seed = self.prep / "seed.ply"
        self.seed.write_bytes(b"ply\nsynthetic\n")
        self.pilot_manifest = write_json(self.run / "pilot_manifest.json", {"ok": True})
        self.footprint = repo / "results/tum_transfer/analysis/footprints_aoi.geojson"
        self.footprint.parent.mkdir(parents=True)
        self.footprint.write_text('{"type":"FeatureCollection","features":[]}\n', encoding="utf-8")
        self.views = [f"view_{index:02d}.JPG" for index in range(16)]
        self._materialize_stage2_inputs()
        self.photo = self._photo_manifest()
        self.prep_manifest = write_json(
            self.prep / "prep_manifest.json",
            {
                "schema": "jointbuildgs.pilot_1wave.prep_manifest.v1",
                "score_building_ids_rank_order": ["B001", "B002"],
                "world_shift": [690953, 5336071, 604],
                "source_sha256": {
                    "results/tum_transfer/analysis/footprints_aoi.geojson": digest(self.footprint)
                },
            },
        )
        self.omnidata = write_json(
            self.prep / "mono_normal_manifest.json",
            {
                "schema": "jointbuildgs.pilot_1wave.omnidata_normal.manifest.v1",
                "status": "complete",
                "normal_dir": str((self.prep / "mono").relative_to(repo)),
            },
        )
        self.mask_04a = self._plane_manifest("04a", "vision_groundedsam_roof")
        self.mask_04b = self._plane_manifest("04b", "lod2_roofsurface_gt_upperbound")
        self.lock = self._lock()

    def _materialize_stage2_inputs(self) -> None:
        data = self.prep / "data"
        for relative in (
            "sparse/0/cameras.bin",
            "sparse/0/images.bin",
            "sparse/0/points3D.bin",
        ):
            path = data / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"synthetic:{relative}\n".encode())
        for view in self.views:
            paths = (
                data / "images" / view,
                data / "stereo/depth_maps" / f"{view}.geometric.bin",
                data / "stereo/normal_maps" / f"{view}.geometric.bin",
                self.prep / "mono" / f"{Path(view).stem}.npy",
            )
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"synthetic:{path.name}\n".encode())

    def _photo_manifest(self) -> Path:
        masks = {
            view: np.ones((4, 5), dtype=np.bool_) for view in self.views
        }
        geometry = {
            view: hashlib.sha256(view.encode()).hexdigest() for view in self.views
        }
        return write_binary_mask_set(
            self.prep / "photo_masks",
            masks,
            purpose=MaskPurpose.PHOTO_SUPPORT,
            source=MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
            source_disclosure="synthetic GroundSurface XY photo support",
            input_sha256="1" * 64,
            config_sha256="2" * 64,
            geometry_sha256_by_view=geometry,
        )

    def _plane_manifest(self, condition: str, source: str) -> Path:
        root = self.prep / f"masks_{condition}"
        masks = {
            view: np.ones((4, 5), dtype=np.bool_) for view in self.views
        }
        geometry = {
            view: hashlib.sha256(view.encode()).hexdigest() for view in self.views
        }
        mask_source = (
            MaskSource.VISION_GROUNDEDSAM_ROOF
            if condition == "04a"
            else MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND
        )
        if mask_source.value != source:
            raise AssertionError("synthetic mask source mismatch")
        return write_binary_mask_set(
            root,
            masks,
            purpose=MaskPurpose.PLANE_REGION,
            source=mask_source,
            source_disclosure=f"synthetic {condition} plane region",
            input_sha256="3" * 64,
            config_sha256="4" * 64,
            geometry_sha256_by_view=geometry,
        )

    def _lock(self) -> Path:
        lock_path = self.repo / "phases/p2-gsjso/configs/calibration_lock.json"
        lock = {
            "schema": "jointbuildgs.pilot_1wave.calibration_lock.v1",
            "run_id": "20260721_pilot_1wave",
            "created_before_optimizer_results": True,
            "input_bindings": {
                "prep_manifest": binding(self.repo, self.prep_manifest),
                "pilot_set_manifest": binding(self.repo, self.pilot_manifest),
                "dense_seed": binding(self.repo, self.seed),
                "projected_footprint_mask_manifest": binding(self.repo, self.photo),
                "omnidata_manifest": binding(self.repo, self.omnidata),
            },
            "base_recipe": {
                "w_photo": 1.0,
                "photo_lam": 0.2,
                "w_depth": 0.1,
                "w_normal_mvs": 0.15,
                "w_mono_normal_aux": 0.05,
                "w_nc": 0.05,
                "w_structure": 0.08,
                "w_structure_na": 1.0,
                "w_structure_cp": 1.0,
                "depth_normal_warmup_updates": 5000,
                "depth_normal_ramp_updates": 5000,
                "structure_warmup_updates": 15000,
                "structure_regroup_every_updates": 1000,
                "structure_grouping": "g2_geometry",
                "structure_voxel_size_m": 2.0,
                "structure_merge_normal_cos": 0.92,
                "structure_merge_distance_m": 0.5,
                "structure_min_group": 30,
                "forbidden_weights_zero": list(resolver.FORBIDDEN_WEIGHTS),
            },
            "plane_primitive": {
                "window_size_px": 7,
                "stride_px": 4,
                "minimum_points": 16,
                "alpha_threshold": 0.5,
                "maximum_depth_range_m": 1.0,
                "minimum_second_eigenvalue": 1e-10,
            },
            "plane_guided_initialization": {
                "pilot_plane_init_stride_px": 8,
                "pilot_plane_init_grid_offset_px": 4,
                "pilot_plane_init_knn": 4,
                "pilot_plane_init_tolerance_m": 0.5,
                "pilot_plane_init_min_coverage": 0.05,
                "pilot_plane_init_query_chunk_size": 100000,
            },
            "view_selection": {
                "calibration_view_ids": self.views,
                "calibration_view_ids_sha256_newline_joined": hashlib.sha256(
                    "\n".join(self.views).encode()
                ).hexdigest(),
            },
            "forward_only_resolution": {"calibration_seed": 1001},
            "forward_runtime": {
                "container_required": True,
                "image_tag": "jointbuildgs:dev",
                "image_id": "sha256:" + "9" * 64,
                "host_attestation_environment": {
                    "image_tag": "P1W_HOST_IMAGE_TAG",
                    "image_id": "P1W_HOST_IMAGE_ID",
                },
                "python": "3.11.15",
                "torch": "2.4.1+cu121",
                "cuda": "12.1",
                "gsplat": "1.4.0",
                "numpy": "1.26.4",
                "scipy": "1.13.1",
                "pillow": "10.4.0",
            },
            "training_budget": {
                "seeds": [1001, 1002],
                "max_optimizer_updates": 20000,
                "full_state_checkpoint_updates": [5000, 10000, 15000, 20000],
                "gpu_count": 2,
                "wall_guard_hours": 9.0,
                "stop_starting_new_runs_hours": 8.5,
                "partial_is_winner_eligible": False,
            },
        }
        return write_json(lock_path, lock)

    def receipt(self, scaffolds: Path) -> Path:
        code = self.repo / "code.py"
        code.write_text("# synthetic\n", encoding="utf-8")
        configs = {
            condition: scaffolds / f"calibration_{condition}_seed1001.yaml"
            for condition in ("03", "04a", "04b")
        }
        scaffold_manifest = scaffolds / "calibration_scaffolds_manifest.json"
        materialized_inventory = scaffolds / "materialized_input_inventory.json"
        runtime = json.loads(self.lock.read_text())["forward_runtime"]
        payload = {
            "schema": "jointbuildgs.pilot_1wave.plane_calibration_receipt.v1",
            "run_id": "20260721_pilot_1wave",
            "state": "complete",
            "official": True,
            "official_backend_id": resolver.OFFICIAL_BACKEND_ID,
            "synthetic": False,
            "backend": {
                "id": resolver.OFFICIAL_BACKEND_ID,
                "synthetic": False,
            },
            "runtime_attestation": {
                "state": "official_attested",
                "synthetic": False,
                "container": True,
                **{
                    key: runtime[key]
                    for key in (
                        "image_tag",
                        "image_id",
                        "host_attestation_environment",
                        "python",
                        "torch",
                        "cuda",
                        "gsplat",
                        "numpy",
                        "scipy",
                        "pillow",
                    )
                },
                "cuda_available": True,
                "cuda_device_count": 1,
            },
            "seed_lock": {
                "calibration_seed": 1001,
                "weight_reused_for_seeds": [1001, 1002],
            },
            "optimizer_audit": {
                "optimizer_objects_created": 0,
                "backward_calls": 0,
                "optimizer_updates": 0,
            },
            "view_lock": {
                "view_ids": self.views,
                "view_ids_sha256": hashlib.sha256("\n".join(self.views).encode()).hexdigest(),
                "minimum_eligible_views": 8,
                "random_view_sampling": False,
            },
            "inputs": {
                "calibration_lock": binding(self.repo, self.lock),
                "calibration_scaffolds_manifest": binding(
                    self.repo, scaffold_manifest
                ),
                "materialized_input_inventory": binding(
                    self.repo, materialized_inventory
                ),
                "dense_seed": binding(self.repo, self.seed),
                "configs": {key: binding(self.repo, value) for key, value in configs.items()},
                "masks": {
                    "common_roof_audit": binding(self.repo, self.photo),
                    "04a_plane": binding(self.repo, self.mask_04a),
                    "04b_plane": binding(self.repo, self.mask_04b),
                },
                "code": {"synthetic": binding(self.repo, code)},
            },
            "input_validation": {
                "verified_before_and_after_forward": True,
                "materialized_input_inventory": {
                    **{
                        key: json.loads(materialized_inventory.read_text())[key]
                        for key in (
                            "schema",
                            "records_sha256",
                            "view_count",
                            "file_count",
                            "total_bytes",
                        )
                    },
                    "sha256": digest(materialized_inventory),
                },
                "common_04a_04b_view_shape_geometry_exact": True,
            },
            "resolved_weights": {
                "03": {
                    "w_plane": 0.5,
                    "target_ratio": 0.25,
                    "aggregate_weighted_roof_photo": 2.0,
                    "aggregate_raw_roof_plane": 1.0,
                    "achieved_ratio": 0.25,
                    "eligible_view_count": 16,
                },
                "04a": {
                    "w_plane": 2.0,
                    "target_ratio": 1.0,
                    "aggregate_weighted_roof_photo": 2.0,
                    "aggregate_raw_roof_plane": 1.0,
                    "achieved_ratio": 1.0,
                    "eligible_view_count": 16,
                },
                "04b": {
                    "w_plane": 2.0,
                    "source_weight_condition": "04a",
                    "target_ratio": None,
                    "aggregate_weighted_roof_photo": 2.0,
                    "aggregate_raw_roof_plane": 0.75,
                    "achieved_ratio": 0.75,
                    "eligible_view_count": 16,
                },
            },
            "medium_verification": {
                "inclusive_ratio_range": [0.5, 2.0],
                "conditions": {
                    "04a": {"achieved_ratio": 1.0, "passed": True},
                    "04b": {"achieved_ratio": 0.75, "passed": True},
                },
                "shared_weight_exact": True,
                "passed": True,
                "retuned_04b": False,
            },
        }
        return write_json(self.run / "calibration/receipt.json", payload)


class ResolvedConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.mkdtemp(prefix="p1w-resolver-")
        self.repo = Path(self.temp) / "repo"
        self.repo.mkdir()
        self.fixture = SyntheticContract(self.repo)

    def tearDown(self) -> None:
        for root, directories, files in os.walk(self.temp):
            for name in directories:
                Path(root, name).chmod(0o755)
            for name in files:
                Path(root, name).chmod(0o644)
        shutil.rmtree(self.temp)

    def _publish_scaffolds(self) -> Path:
        output = self.fixture.run / "calibration/scaffolds"
        configs, manifest, materialized_inventory = resolver.build_calibration_plan(
            repo=self.repo,
            lock_path=self.fixture.lock,
            mask_04a_path=self.fixture.mask_04a,
            mask_04b_path=self.fixture.mask_04b,
            output_dir=output,
            calibration_seed=1001,
        )
        resolver.publish_calibration_scaffolds(
            repo=self.repo,
            output_dir=output,
            configs=configs,
            manifest=manifest,
            materialized_input_inventory=materialized_inventory,
        )
        return output

    def test_two_stage_contract_and_immutable_bundles(self) -> None:
        scaffolds = self._publish_scaffolds()
        self.assertEqual(stat.S_IMODE(scaffolds.stat().st_mode), 0o555)
        for path in scaffolds.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertTrue(path.read_bytes())
        scaffold_03 = yaml.safe_load((scaffolds / "calibration_03_seed1001.yaml").read_text())
        self.assertTrue(scaffold_03["pilot_calibration_only"])
        self.assertEqual(scaffold_03["pilot_calibration_optimizer_updates"], 0)
        self.assertNotIn("plane_region_mask_manifest", scaffold_03)
        inventory_path = scaffolds / "materialized_input_inventory.json"
        inventory = resolver.validate_materialized_input_inventory(
            self.repo,
            inventory_path,
            expected_sha256=scaffold_03[
                "pilot_materialized_input_inventory_sha256"
            ],
        )
        self.assertEqual(inventory["view_count"], 16)
        self.assertEqual(inventory["file_count"], 3 + 4 * 16)
        self.assertEqual(
            scaffold_03["pilot_materialized_input_inventory_path"],
            resolver.container_path(self.repo, inventory_path),
        )
        self.assertEqual(scaffold_03["init_pointcloud_mode"], "concat")
        self.assertEqual(scaffold_03["mvs_seed_init_opacity"], 0.25)
        self.assertEqual(scaffold_03["downscale"], 1.0)
        self.assertEqual(scaffold_03["sh_degree"], 3)

        receipt = self.fixture.receipt(scaffolds)
        bundle = self.fixture.run / "training/resolved_configs"
        runs = self.fixture.run / "training/runs"
        configs, manifest = resolver.build_resolved_plan(
            repo=self.repo,
            lock_path=self.fixture.lock,
            receipt_path=receipt,
            mask_04a_path=self.fixture.mask_04a,
            mask_04b_path=self.fixture.mask_04b,
            output_dir=bundle,
            training_output_root=runs,
        )
        self.assertEqual(len(configs), 10)
        from src.stage2.train import _validate_pilot_config_contract
        from src.stage2.train_resume import full_state_options

        for row in configs:
            self.assertEqual(
                _validate_pilot_config_contract(row, full_state_options(row)),
                row["pilot_arm"],
            )
        by_key = {(row["pilot_condition"], row["seed"]): row for row in configs}
        arm01 = by_key[("01", 1001)]
        self.assertEqual(arm01["mvs_seed_init_opacity"], 0.10)
        self.assertFalse(arm01["seed_protect"])
        self.assertNotIn("photo_mask_manifest", arm01)
        for condition in ("02", "03", "04a", "04b"):
            row = by_key[(condition, 1002)]
            self.assertEqual(row["mvs_seed_init_opacity"], 0.25)
            self.assertTrue(row["seed_protect"])
            self.assertIsNone(row["seed_protect_until_iter"])
            self.assertEqual(row["photo_mask_manifest"], row["roof_audit_mask_manifest"])
        self.assertEqual(by_key[("03", 1001)]["w_plane"], 0.5)
        self.assertEqual(by_key[("04a", 1001)]["w_plane"], 2.0)
        self.assertEqual(by_key[("04b", 1001)]["w_plane"], 2.0)
        self.assertEqual(
            resolver.pair_differences(by_key[("04a", 1001)], by_key[("04b", 1001)]),
            resolver.PAIR_REQUIRED_TRAINING_DIFFERENCE_KEYS,
        )
        for row in configs:
            self.assertEqual(row["full_state_checkpoint_steps"], [5000, 10000, 15000, 20000])
            self.assertEqual(
                row["pilot_materialized_input_inventory_path"],
                resolver.container_path(
                    self.repo, scaffolds / "materialized_input_inventory.json"
                ),
            )
            self.assertEqual(
                row["pilot_materialized_input_inventory_sha256"],
                digest(scaffolds / "materialized_input_inventory.json"),
            )
            self.assertIsNone(row["normal_dir"])
            self.assertEqual(row["normal_encoding"], "half_range")
            self.assertTrue(row["out_dir"].startswith("/workspace/JointBuildGS/"))
            self.assertIn("/training/runs/", row["out_dir"])
            self.assertNotIn("/resolved_configs/", row["out_dir"])
            for key in resolver.FORBIDDEN_WEIGHTS:
                self.assertEqual(row[key], 0.0)
        resolver.publish_configs(
            repo=self.repo, output_dir=bundle, configs=configs, manifest=manifest
        )
        self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o555)
        self.assertFalse(runs.exists(), "resolver must not write into the training output root")
        for path in bundle.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertTrue(path.read_bytes())
        published_manifest = json.loads(
            (bundle / "resolved_configs_manifest.json").read_text()
        )
        self.assertEqual(
            published_manifest["inputs"]["materialized_input_inventory"]["sha256"],
            digest(scaffolds / "materialized_input_inventory.json"),
        )
        self.assertEqual(
            published_manifest["inputs"]["calibration_scaffolds_manifest"]["sha256"],
            digest(scaffolds / "calibration_scaffolds_manifest.json"),
        )

    def test_calibration_seed_is_exactly_1001(self) -> None:
        with self.assertRaisesRegex(resolver.ContractError, "exactly 1001"):
            resolver.build_calibration_plan(
                repo=self.repo,
                lock_path=self.fixture.lock,
                mask_04a_path=self.fixture.mask_04a,
                mask_04b_path=self.fixture.mask_04b,
                output_dir=self.fixture.run / "bad",
                calibration_seed=1002,
            )

    def test_04b_target_must_be_null_and_no_retune(self) -> None:
        scaffolds = self._publish_scaffolds()
        receipt = self.fixture.receipt(scaffolds)
        payload = json.loads(receipt.read_text())
        payload["resolved_weights"]["04b"]["target_ratio"] = 1.0
        write_json(receipt, payload)
        with self.assertRaisesRegex(resolver.ContractError, "04b.target_ratio"):
            resolver.build_resolved_plan(
                repo=self.repo,
                lock_path=self.fixture.lock,
                receipt_path=receipt,
                mask_04a_path=self.fixture.mask_04a,
                mask_04b_path=self.fixture.mask_04b,
                output_dir=self.fixture.run / "training/configs",
                training_output_root=self.fixture.run / "training/runs",
            )

    def test_config_bundle_and_training_root_must_not_overlap(self) -> None:
        scaffolds = self._publish_scaffolds()
        receipt = self.fixture.receipt(scaffolds)
        bundle = self.fixture.run / "training/resolved_configs"
        with self.assertRaisesRegex(resolver.ContractError, "must not overlap"):
            resolver.build_resolved_plan(
                repo=self.repo,
                lock_path=self.fixture.lock,
                receipt_path=receipt,
                mask_04a_path=self.fixture.mask_04a,
                mask_04b_path=self.fixture.mask_04b,
                output_dir=bundle,
                training_output_root=bundle / "runs",
            )

    def test_same_plane_manifest_cannot_fill_both_control_arms(self) -> None:
        with self.assertRaisesRegex(resolver.ContractError, "loader source"):
            resolver.build_calibration_plan(
                repo=self.repo,
                lock_path=self.fixture.lock,
                mask_04a_path=self.fixture.mask_04a,
                mask_04b_path=self.fixture.mask_04a,
                output_dir=self.fixture.run / "calibration/bad_pair",
                calibration_seed=1001,
            )

    def test_materialized_inventory_requires_exact_role_for_each_view(self) -> None:
        scaffolds = self._publish_scaffolds()
        source = scaffolds / "materialized_input_inventory.json"
        payload = json.loads(source.read_text())
        payload["records"][3]["view_id"] = payload["view_ids"][1]
        payload["records_sha256"] = hashlib.sha256(
            resolver.canonical_json_bytes(payload["records"])
        ).hexdigest()
        tampered = write_json(self.fixture.run / "tampered_inventory.json", payload)
        with self.assertRaisesRegex(resolver.ContractError, "identity"):
            resolver.validate_materialized_input_inventory(
                self.repo, tampered, expected_sha256=digest(tampered)
            )

    def test_nonofficial_receipt_cannot_resolve_training(self) -> None:
        scaffolds = self._publish_scaffolds()
        receipt = self.fixture.receipt(scaffolds)
        payload = json.loads(receipt.read_text())
        payload["official"] = False
        payload["synthetic"] = True
        write_json(receipt, payload)
        with self.assertRaisesRegex(resolver.ContractError, "official calibration receipt"):
            resolver.build_resolved_plan(
                repo=self.repo,
                lock_path=self.fixture.lock,
                receipt_path=receipt,
                mask_04a_path=self.fixture.mask_04a,
                mask_04b_path=self.fixture.mask_04b,
                output_dir=self.fixture.run / "training/configs",
                training_output_root=self.fixture.run / "training/runs",
            )


if __name__ == "__main__":
    unittest.main()

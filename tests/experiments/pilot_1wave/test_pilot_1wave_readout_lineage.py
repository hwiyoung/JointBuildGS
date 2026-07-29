#!/usr/bin/env python3
"""Synthetic tests for full-state/legacy read-out checkpoint provenance."""
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import torch


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "phases/p2-gsjso/scripts/e5_c001_readout_extract_ablation.py"
SPEC = importlib.util.spec_from_file_location("p1w_readout_extract", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
EXTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXTRACT)


class PilotReadoutLineageTests(unittest.TestCase):
    def test_chunked_voxel_decode_is_bitwise_equal_to_original_formula(self) -> None:
        q = EXTRACT.torch.tensor([
            [-37, 0, 81],
            [0, 0, 0],
            [1, -1, 2],
            [EXTRACT.OFF - 1, -EXTRACT.OFF + 1, 17],
            [-EXTRACT.OFF + 2, EXTRACT.OFF - 2, -19],
        ], dtype=EXTRACT.torch.int64)
        shifted = q + EXTRACT.OFF
        keys = (
            (shifted[:, 0] * EXTRACT.MUL + shifted[:, 1]) * EXTRACT.MUL
            + shifted[:, 2]
        )

        work = keys.detach().cpu().numpy().astype(EXTRACT.np.int64, copy=True)
        iz = (work % EXTRACT.MUL) - EXTRACT.OFF
        work //= EXTRACT.MUL
        iy = (work % EXTRACT.MUL) - EXTRACT.OFF
        ix = (work // EXTRACT.MUL) - EXTRACT.OFF
        expected = (
            EXTRACT.np.stack([ix, iy, iz], axis=1).astype(EXTRACT.np.float64)
            + 0.5
        ) * 0.05 + EXTRACT.SHIFT

        for chunk_size in (1, 2, len(keys), len(keys) + 10):
            with self.subTest(chunk_size=chunk_size):
                actual = EXTRACT.decode_keys(keys, 0.05, chunk_size=chunk_size)
                self.assertTrue(EXTRACT.np.array_equal(actual, expected))

        with self.assertRaisesRegex(ValueError, "must be positive"):
            EXTRACT.decode_keys(keys, 0.05, chunk_size=0)

    def test_locked_pilot_crop_contract_is_exact_and_single_box(self) -> None:
        contract = EXTRACT.build_pilot_crop_contract()
        self.assertEqual(
            contract["schema"], EXTRACT.PILOT_CROP_CONTRACT_SCHEMA
        )
        self.assertEqual(
            contract["crop"]["bbox_utm"], list(EXTRACT.PILOT_CROP_BBOX_UTM)
        )
        self.assertEqual(
            contract["crop"]["area_m2"], EXTRACT.PILOT_CROP_AREA_M2
        )
        self.assertEqual(contract["population"]["count"], 30)
        self.assertEqual(
            contract["population"]["ordered_building_ids"],
            list(EXTRACT.PILOT_BUILDING_IDS),
        )
        self.assertEqual(
            contract["population"]["ordered_ids_sha256"],
            EXTRACT._ordered_ids_sha256(EXTRACT.PILOT_BUILDING_IDS),
        )
        self.assertEqual(
            contract["materialized_input_inventory"]["view_count"], 481
        )

        args = SimpleNamespace(
            targets=None,
            buffer=None,
            max_views=0,
            geojson=None,
            data_root=None,
        )
        footprints, boxes, footprint_path, data_root, lineage, view_ids = (
            EXTRACT._resolve_readout_scope(
                args,
                {"verified_full_state": True},
            )
        )
        self.assertEqual(tuple(footprints), EXTRACT.PILOT_BUILDING_IDS)
        self.assertEqual(len(boxes), 1)
        np_box = EXTRACT.np.asarray(boxes[0]) + EXTRACT.SHIFT[[0, 1, 0, 1]]
        self.assertTrue(
            EXTRACT.np.array_equal(np_box, EXTRACT.np.asarray(EXTRACT.PILOT_CROP_BBOX_UTM))
        )
        self.assertEqual(footprint_path, EXTRACT.REPO_PATH / EXTRACT.PILOT_FOOTPRINT_REL)
        self.assertEqual(data_root, EXTRACT.REPO_PATH / EXTRACT.PILOT_DATA_ROOT_REL)
        self.assertEqual(len(view_ids or ()), 481)
        self.assertIn("crop_contract_json", lineage)
        self.assertIn("crop_contract_sha256", lineage)

    def test_verified_pilot_scope_rejects_legacy_crop_options(self) -> None:
        base = {
            "targets": None,
            "buffer": None,
            "max_views": 0,
            "geojson": None,
            "data_root": None,
        }
        cases = (
            ("targets", [], "--targets"),
            ("buffer", 15.0, "--buffer"),
            ("max_views", 1, "--max-views"),
            ("geojson", "/tmp/not-the-lock.geojson", "footprint source path"),
            ("data_root", "/tmp/not-the-materialized-root", "materialized data root"),
        )
        for field, value, error in cases:
            with self.subTest(field=field):
                values = dict(base)
                values[field] = value
                with self.assertRaisesRegex(RuntimeError, error):
                    EXTRACT._resolve_readout_scope(
                        SimpleNamespace(**values),
                        {"verified_full_state": True},
                    )

    def test_unverified_legacy_scope_keeps_c001_fallback(self) -> None:
        args = SimpleNamespace(
            targets=None,
            buffer=None,
            max_views=0,
            geojson=None,
            data_root=None,
        )
        footprints, boxes, _footprint, data_root, lineage, view_ids = (
            EXTRACT._resolve_readout_scope(
                args,
                {"verified_full_state": False},
            )
        )
        self.assertEqual(len(footprints), len(EXTRACT.C001_SHORT_IDS))
        self.assertEqual(len(boxes), len(EXTRACT.C001_SHORT_IDS))
        self.assertEqual(data_root, Path(EXTRACT.DENSE))
        self.assertNotIn("crop_contract_json", lineage)
        self.assertIsNone(view_ids)

    def test_locked_crop_contract_fails_closed_on_source_byte_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="p1w_crop_drift_") as raw:
            root = Path(raw)
            for relative in (
                EXTRACT.PILOT_SET_CSV_REL,
                EXTRACT.PILOT_SET_MANIFEST_REL,
                EXTRACT.PILOT_FOOTPRINT_REL,
                EXTRACT.PILOT_INVENTORY_REL,
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(EXTRACT.REPO_PATH / relative, target)
            EXTRACT.build_pilot_crop_contract(repo_root=root)
            inventory = root / EXTRACT.PILOT_INVENTORY_REL
            inventory.write_bytes(inventory.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                RuntimeError, "materialized input inventory SHA256"
            ):
                EXTRACT.build_pilot_crop_contract(repo_root=root)

    def test_crop_contract_is_identical_in_lineage_npz_and_provenance(self) -> None:
        contract = EXTRACT.build_pilot_crop_contract()
        lineage = EXTRACT._attach_crop_contract(
            {"verified_full_state": True, "geometry_only": True}, contract
        )
        fields = EXTRACT._crop_contract_fields(lineage)
        expected_json = lineage["crop_contract_json"]
        expected_sha = lineage["crop_contract_sha256"]
        self.assertEqual(fields["crop_contract_json"].item(), expected_json)
        self.assertEqual(fields["crop_contract_sha256"].item(), expected_sha)

        with tempfile.TemporaryDirectory(prefix="p1w_crop_embed_") as raw:
            root = Path(raw)
            output = root / "scene.npz"
            provenance = root / "scene.provenance.json"
            EXTRACT.np.savez(
                output,
                readout_lineage_json=EXTRACT.np.array(
                    EXTRACT._canonical_json(lineage)
                ),
                **fields,
            )
            with EXTRACT.np.load(output, allow_pickle=False) as payload:
                self.assertEqual(payload["crop_contract_json"].item(), expected_json)
                self.assertEqual(payload["crop_contract_sha256"].item(), expected_sha)
            args = SimpleNamespace(
                out=str(output),
                provenance_json=str(provenance),
                no_sem=True,
            )
            EXTRACT._write_provenance(
                args,
                lineage=lineage,
                point_count=0,
                footprint_path=EXTRACT.REPO_PATH / EXTRACT.PILOT_FOOTPRINT_REL,
            )
            receipt = json.loads(provenance.read_text(encoding="utf-8"))
            self.assertEqual(receipt["crop_contract_json"], expected_json)
            self.assertEqual(receipt["crop_contract_sha256"], expected_sha)
            self.assertEqual(
                receipt["readout_lineage"]["crop_contract_json"], expected_json
            )
            self.assertEqual(
                receipt["readout_lineage"]["crop_contract_sha256"], expected_sha
            )

        tampered = dict(lineage)
        tampered["crop_contract_json"] += " "
        with self.assertRaisesRegex(RuntimeError, "crop contract SHA256"):
            EXTRACT._crop_contract_fields(tampered)

    def test_full_state_model_state_dict_is_bound_to_exact_manifest(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix=".p1w_readout_", dir=SCRIPT.parent
        ) as raw:
            root = Path(raw)
            checkpoint = root / "step_020000.pt"
            binding = {
                "training_config": "1" * 64,
                "effective_training_config": "2" * 64,
                "output_path": "3" * 64,
            }
            payload = {
                "checkpoint_format": "jointbuildgs.stage2.full_state",
                "completed_steps": 20_000,
                "binding_sha256": binding,
                "model": {"state_dict": {"means": torch.ones((2, 3))}},
            }
            torch.save(payload, checkpoint)
            config = root / "train.json"
            config.write_text(
                json.dumps(
                    {"max_iter": 20_000, "pilot_arm": "01_surface", "seed": 1001}
                )
                + "\n",
                encoding="utf-8",
            )
            manifest = root / "full_state_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": "jointbuildgs.stage2.resume_manifest.v1",
                        "max_iter": 20_000,
                        "step_semantics": "completed_optimizer_updates",
                        "checkpoint_steps": [5_000, 10_000, 15_000, 20_000],
                        "learning_runs_started": 1,
                        "last_completed_steps": 20_000,
                        "process_completed": True,
                        "process_completed_steps": 20_000,
                        "binding_sha256": binding,
                        "config_path": str(config),
                        "config_file_sha256": EXTRACT.sha256_file(config),
                        "latest_full_checkpoint": {
                            "path": str(checkpoint),
                            "sha256": EXTRACT.sha256_file(checkpoint),
                            "completed_steps": 20_000,
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            state, lineage = EXTRACT._checkpoint_identity(
                checkpoint,
                payload,
                condition="01",
                seed=1001,
                checkpoint_step=None,
                full_state_manifest=str(manifest),
            )
            self.assertTrue(torch.equal(state["means"], torch.ones((2, 3))))
            self.assertTrue(lineage["verified_full_state"])
            self.assertTrue(lineage["eligible_20k_full_state"])
            self.assertEqual(lineage["checkpoint"]["sha256"], EXTRACT.sha256_file(checkpoint))

            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            manifest_payload["latest_full_checkpoint"]["sha256"] = "0" * 64
            manifest.write_text(json.dumps(manifest_payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "manifest checkpoint SHA256"):
                EXTRACT._checkpoint_identity(
                    checkpoint,
                    payload,
                    condition="01",
                    seed=1001,
                    checkpoint_step=None,
                    full_state_manifest=str(manifest),
                )

    def test_legacy_state_dict_remains_explicitly_supported_but_unverified(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix=".p1w_readout_", dir=SCRIPT.parent
        ) as raw:
            checkpoint = Path(raw) / "final.pt"
            payload = {"it": 20_000, "state_dict": {"means": torch.zeros((1, 3))}}
            torch.save(payload, checkpoint)
            state, lineage = EXTRACT._checkpoint_identity(
                checkpoint,
                payload,
                condition="02",
                seed=1002,
                checkpoint_step=None,
                full_state_manifest=None,
            )
            self.assertIn("means", state)
            self.assertEqual(lineage["checkpoint"]["format"], "legacy_state_dict")
            self.assertFalse(lineage["verified_full_state"])
            self.assertFalse(lineage["eligible_20k_full_state"])

    def test_host_and_container_roots_canonicalize_to_same_posix_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="p1w_path_roots_") as raw:
            base = Path(raw)
            host_root = base / "media/checkout"
            container_root = base / "workspace/JointBuildGS"
            relative = Path("phases/p2-gsjso/runs/run/ckpt/step_020000.pt")
            host_path = host_root / relative
            container_path = container_root / relative
            host_path.parent.mkdir(parents=True)
            container_path.parent.mkdir(parents=True)
            host_path.write_bytes(b"host-view")
            container_path.write_bytes(b"container-view")
            self.assertEqual(
                EXTRACT.canonical_repo_path(host_path, repo_root=host_root),
                relative.as_posix(),
            )
            self.assertEqual(
                EXTRACT.canonical_repo_path(
                    container_path, repo_root=container_root
                ),
                relative.as_posix(),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

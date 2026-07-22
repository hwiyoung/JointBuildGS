#!/usr/bin/env python3
"""Synthetic tests for full-state/legacy read-out checkpoint provenance."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import torch


SCRIPT = Path(__file__).with_name("e5_c001_readout_extract_ablation.py")
SPEC = importlib.util.spec_from_file_location("p1w_readout_extract", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
EXTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXTRACT)


class PilotReadoutLineageTests(unittest.TestCase):
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

#!/usr/bin/env python3
"""CPU-only contract tests for the S3-A-prime CUDA smoke harness."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch
import yaml
from torch.utils.tensorboard import SummaryWriter


REPO = Path(__file__).resolve().parents[3]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke_module = load_module(
    "s3ap_phase2_smoke",
    REPO / "phases/p2-gsjso/scripts/e5_c001_s3ap_phase2_smoke.py",
)


class Phase2SmokeHarnessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = smoke_module.load_lock()

    def test_locked_schedule_and_source_only_config_delta(self):
        schedule = [
            (row["arm"], row["max_iter"], row["gpu_id"], row["stage"])
            for row in self.lock["smokes"]
        ]
        self.assertEqual(schedule, [("a0", 2, 0, 0), ("a1", 2, 1, 0), ("a2", 702, 0, 1)])
        source_hash_before = {
            row["arm"]: smoke_module.sha256_file(row["source_config"])
            for row in self.lock["smokes"]
        }
        for row in self.lock["smokes"]:
            source = yaml.safe_load(smoke_module.resolve(row["source_config"]).read_text(encoding="utf-8"))
            derived, output = smoke_module.derive_smoke_config(source, row, self.lock)
            self.assertEqual(derived["max_iter"], row["max_iter"])
            self.assertEqual(derived["out_dir"], smoke_module.container_path(output, self.lock))
            self.assertEqual(
                {key: value for key, value in source.items() if key not in {"max_iter", "out_dir"}},
                {key: value for key, value in derived.items() if key not in {"max_iter", "out_dir"}},
            )
        self.assertEqual(
            source_hash_before,
            {row["arm"]: smoke_module.sha256_file(row["source_config"]) for row in self.lock["smokes"]},
        )

    def test_runtime_attestation_is_exact_and_launcher_is_locked(self):
        names = self.lock["runtime"]["attestation_env"]
        environment = {
            names["image_id"]: self.lock["runtime"]["docker_image_id"],
            names["host_uid"]: str(os.getuid()),
            names["host_gid"]: str(os.getgid()),
        }
        with mock.patch.dict(os.environ, environment, clear=False):
            audit = smoke_module.validate_runtime_attestation(self.lock)
        self.assertTrue(audit["user_mapping_exact"])
        launcher = smoke_module.resolve(self.lock["runtime"]["host_launcher"]).read_text(encoding="utf-8")
        self.assertIn(self.lock["runtime"]["docker_image_id"], launcher)
        self.assertIn('--user "${HOST_UID}:${HOST_GID}"', launcher)
        self.assertIn("--gpus all", launcher)

    def test_live_source_contract_reuses_strict_phase2_payload_validation(self):
        audit = smoke_module.validate_source_contract(self.lock)
        self.assertEqual(set(audit["selected"]), {row["smoke_id"] for row in self.lock["smokes"]})
        self.assertEqual(audit["prepare_manifest_sha256"], self.lock["source_contract"]["prepare_manifest_sha256"])
        for row in self.lock["smokes"]:
            selected = audit["selected"][row["smoke_id"]]
            self.assertEqual(selected["source_job"]["arm"], row["arm"])
            self.assertEqual(selected["payload_audit"]["surface_seed_sha256"], selected["source_job"]["surface_seed_sha256"])

    def _synthetic_output(self, root: Path, arm: str):
        source_smoke = next(row for row in self.lock["smokes"] if row["arm"] == arm)
        local_lock = copy.deepcopy(self.lock)
        local_lock["outputs"] = {
            **local_lock["outputs"],
            "root": str(root),
            "config_dir": str(root / "configs"),
            "run_dir": str(root / "runs"),
            "log_dir": str(root / "logs"),
            "manifest": str(root / "manifest.json"),
        }
        source = yaml.safe_load(smoke_module.resolve(source_smoke["source_config"]).read_text(encoding="utf-8"))
        config, output_dir = smoke_module.derive_smoke_config(source, source_smoke, local_lock)
        config_path = root / "configs" / f"{source_smoke['smoke_id']}.yaml"
        smoke_module.atomic_yaml(config_path, config)
        output_dir.mkdir(parents=True)
        seed_hash = (
            "237fbb2f4a4737cef95874f73bc46b365bc55c574a65c52dfebabd92b1fbf33e"
            if arm == "a0"
            else "ed5c5f90fb9adc2853c0b8744905e5a2f951bca8ffdf96095e0ca6a49eb7247a"
        )
        record = {
            "generated_config": smoke_module.relative(config_path),
            "generated_config_sha256": smoke_module.sha256_file(config_path),
            "source_config_sha256": source_smoke["source_config_sha256"],
            "surface_seed_sha256": seed_hash,
            "output_dir": smoke_module.relative(output_dir),
        }
        smoke_module.atomic_json(output_dir / "smoke_binding.json", {
            "schema": smoke_module.BINDING_SCHEMA,
            "smoke_id": source_smoke["smoke_id"],
            "generated_config_sha256": record["generated_config_sha256"],
            "source_config_sha256": source_smoke["source_config_sha256"],
        })
        smoke_module.atomic_json(output_dir / "surface_seed_audit.json", {
            "sha256": seed_hash,
            "n_surface_seed": 4,
            "init_opacity": 0.1,
        })
        effective = {
            "surface_seed_protect": arm == "a2",
            "surface_seed": {"sha256": seed_hash},
            "mono_normal_loss": "target_region" if arm != "a0" else "global",
            "mono_depth_loss": "ssi" if arm != "a0" else "absolute_l1",
            "seed_protect_until_iter": 10000 if arm == "a2" else None,
            "surface_seed_prune_opa_initial": 0.05 if arm == "a2" else None,
            "surface_seed_prune_opa_final": 0.01 if arm == "a2" else None,
            "surface_seed_prune_switch_iter": 10000 if arm == "a2" else None,
        }
        smoke_module.atomic_json(output_dir / "effective_config.json", effective)
        (output_dir / "ckpt").mkdir()
        torch.save({
            "it": source_smoke["max_iter"],
            "n_prim": 4,
            "state_dict": {},
            "surface_seed_lineage_mask": torch.ones(4, dtype=torch.bool),
            "surface_seed_lineage_count": 4,
        }, output_dir / "ckpt/final.pt")
        writer = SummaryWriter(output_dir / "tb")
        writer.add_scalar("loss/total", 1.25, 0)
        if arm in {"a1", "a2"}:
            writer.add_scalar("loss/normal", 0.2, 0)
            writer.add_scalar("loss/mono_depth", 0.3, 0)
            audit_dir = output_dir / "audit"
            audit_dir.mkdir()
            (audit_dir / "mono_target_regions.jsonl").write_text(json.dumps({
                "step": 0,
                "view": "v0.png",
                "target_buildings": ["8568391"],
                "mono_depth": {"eligible_region_count": 1},
                "mono_normal": {"eligible_region_count": 1},
            }) + "\n", encoding="utf-8")
        if arm == "a2":
            for step, active, count in ((0, 0, 0), (600, 1, 4)):
                writer.add_scalar("stats/seed_protect_active", active, step)
                writer.add_scalar("stats/seed_protected_count", count, step)
                writer.add_scalar("stats/prune_candidates", 2 if step == 600 else 0, step)
                writer.add_scalar("stats/prune_seed_protected", 1 if step == 600 else 0, step)
                writer.add_scalar("stats/pruned", 1 if step == 600 else 0, step)
                writer.add_scalar("stats/effective_prune_opa", 0.05, step)
        writer.close()
        return record, source_smoke, local_lock

    def test_postflight_summarizes_a1_mono_and_a2_refine_protection(self):
        results_root = REPO / "results"
        results_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="_s3ap_smoke_test_", dir=results_root) as tmp:
            root = Path(tmp)
            a1_record, a1_smoke, local_lock = self._synthetic_output(root / "a1", "a1")
            a1 = smoke_module.summarize_output(a1_record, a1_smoke, local_lock)
            self.assertEqual(a1["checkpoint"]["it"], 2)
            self.assertEqual(a1["mono_target_audit"]["jointly_eligible_row_count"], 1)
            self.assertIsNone(a1["refine_protection_event"])

            a2_record, a2_smoke, local_lock = self._synthetic_output(root / "a2", "a2")
            a2 = smoke_module.summarize_output(a2_record, a2_smoke, local_lock)
            self.assertEqual(a2["checkpoint"]["it"], 702)
            self.assertEqual(a2["surface_seed_lineage"]["final_lineage_count"], 4)
            self.assertEqual(a2["refine_protection_event"]["observed_seed_protect_transition_step"], 600)
            self.assertAlmostEqual(a2["refine_protection_event"]["effective_prune_opa"], 0.05)

    def test_failure_is_recorded_and_later_stages_continue(self):
        manifest = {
            "schema": smoke_module.MANIFEST_SCHEMA,
            "smokes": [
                {
                    "sequence": row["sequence"], "stage": row["stage"],
                    "smoke_id": row["smoke_id"], "arm": row["arm"],
                    "status": "prepared",
                }
                for row in self.lock["smokes"]
            ],
        }
        called = []

        def fake_execute(record, smoke, _lock):
            called.append(smoke["smoke_id"])
            result = copy.deepcopy(record)
            result["status"] = "failed" if smoke["arm"] == "a0" else "complete"
            return result

        snapshots = []
        final = smoke_module.run_schedule(
            manifest,
            self.lock,
            execute=fake_execute,
            persist=lambda value: snapshots.append(copy.deepcopy(value)),
        )
        self.assertEqual(set(called), {row["smoke_id"] for row in self.lock["smokes"]})
        self.assertEqual(next(row for row in final["smokes"] if row["arm"] == "a0")["status"], "failed")
        self.assertEqual(next(row for row in final["smokes"] if row["arm"] == "a2")["status"], "complete")
        self.assertEqual(final["status"], "partial")
        self.assertTrue(snapshots)


if __name__ == "__main__":
    unittest.main()

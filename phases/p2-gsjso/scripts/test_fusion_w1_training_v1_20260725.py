#!/usr/bin/env python3
"""Contract tests for the Fusion-W1 §4 materializer/launcher.

No test starts Docker or training.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("fusion_w1_training_v1_20260725.py")
SPEC = importlib.util.spec_from_file_location("fusion_w1_training_v1", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
fw = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fw)

REAL_CONFIG = (
    Path(__file__).parents[1]
    / "configs"
    / "fusion_w1_training_v1_20260725.json"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeProcess:
    def __init__(self, command, **kwargs):
        self.command = list(command)
        self.pid = 424242
        self.returncode = 0

    def wait(self):
        return self.returncode


class FusionW1TrainingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name)
        self.config = json.loads(REAL_CONFIG.read_text(encoding="utf-8"))
        self.config["inputs"]["preprocess_root"] = "preprocess"
        self.config["outputs"]["training_root"] = "training"
        self.config["git_contract"]["allowed_runtime_untracked_prefixes"] = [
            "preprocess/",
            "training/",
        ]
        self.building_id = "DEBY_LOD2_42364609"
        self.manifest_path = (
            self.repo
            / "preprocess"
            / "by_building"
            / self.building_id
            / "preprocess_manifest.json"
        )
        self.preprocess = self._make_preprocess(view_count=11)
        self.config_path = self.repo / "driver.json"
        self.config_path.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def _write(self, relative: str, payload: bytes) -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def _make_preprocess(self, *, view_count: int) -> dict:
        building_root = self.manifest_path.parent
        data_root = building_root / "data_root"
        selected = [f"IMG_{index:03d}.JPG" for index in range(view_count)]
        views_csv = building_root / "views.csv"
        views_csv.parent.mkdir(parents=True, exist_ok=True)
        views_csv.write_text(
            "image_name,selection_order\n"
            + "".join(f"{name},{index + 1}\n" for index, name in enumerate(selected)),
            encoding="utf-8",
        )
        corrected_images = self._write(
            str((data_root / "sparse/0/images.bin").relative_to(self.repo)),
            b"corrected-pose-model",
        )
        self.config["inputs"]["corrected_images_sha256"] = digest(corrected_images)
        self._write(
            str((data_root / "sparse/0/cameras.bin").relative_to(self.repo)),
            b"cameras",
        )
        self._write(
            str((data_root / "sparse/0/points3D.bin").relative_to(self.repo)),
            b"points",
        )
        for name in selected:
            self._write(
                str((data_root / "images" / name).relative_to(self.repo)),
                f"rgb:{name}".encode(),
            )
            self._write(
                str(
                    (
                        data_root / "stereo/depth_maps" / f"{name}.geometric.bin"
                    ).relative_to(self.repo)
                ),
                f"depth:{name}".encode(),
            )
            self._write(
                str(
                    (
                        data_root / "stereo/normal_maps" / f"{name}.geometric.bin"
                    ).relative_to(self.repo)
                ),
                f"normal:{name}".encode(),
            )
            self._write(
                str(
                    (
                        building_root
                        / "photo_support_masks"
                        / f"{Path(name).stem}.npy"
                    ).relative_to(self.repo)
                ),
                f"mask:{name}".encode(),
            )
        seed = self._write(
            str((building_root / "seed_canonical.npz").relative_to(self.repo)),
            b"canonical-xyz-rgb",
        )
        supervision_index = building_root / "supervision_index.csv"
        supervision_index.write_text(
            "image_name,photo_support_mask_path\n"
            + "".join(
                f"{name},{(building_root / 'photo_support_masks' / f'{Path(name).stem}.npy').relative_to(self.repo)}\n"
                for name in selected
            ),
            encoding="utf-8",
        )
        artifacts = {}
        for path in sorted(building_root.rglob("*")):
            if path.is_file() and path != self.manifest_path:
                artifacts[str(path.relative_to(self.repo))] = digest(path)
        manifest = {
            "schema": fw.PREPROCESS_SCHEMA,
            "status": "PASSED",
            "building": {"building_id": self.building_id},
            "data_root": str(data_root.relative_to(self.repo)),
            "colmap_data_root": str(data_root.relative_to(self.repo)),
            "pose_binding": {
                "corrected_images_sha256": self.config["inputs"][
                    "corrected_images_sha256"
                ],
                "r1_manifest_sha256": self.config["inputs"][
                    "r1_pose_manifest_sha256"
                ],
                "cache_namespace": "pose_test",
            },
            "gate_binding": {
                "r2_manifest_sha256": self.config["inputs"][
                    "r2_gate_manifest_sha256"
                ],
                "status": "PASS",
            },
            "views": {
                "csv": {
                    "path": str(views_csv.relative_to(self.repo)),
                    "sha256": digest(views_csv),
                },
                "count": len(selected),
                "selected_names": selected,
            },
            "seed": {
                "canonical_npz": {
                    "path": str(seed.relative_to(self.repo)),
                    "sha256": digest(seed),
                }
            },
            "supervision": {
                "index": {
                    "path": str(supervision_index.relative_to(self.repo)),
                    "sha256": digest(supervision_index),
                },
                "views_n": len(selected),
            },
            "photo_support_masks": {
                "enabled": True,
                "views_n": len(selected),
            },
            "artifact_sha256": artifacts,
            "publication": {"manifest_written_last": True},
        }
        self.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return manifest

    def _snapshot(self):
        return fw.validate_preprocess(
            self.repo, self.config, self.building_id, hash_artifacts=True
        )

    def test_locked_config_contains_required_recipe(self):
        cfg = fw.load_driver_config(REAL_CONFIG)
        recipe = cfg["recipe"]
        self.assertEqual(recipe["max_iter"], 30000)
        self.assertEqual(recipe["run_seeds"], {"r1": 1001, "r2": 1002})
        self.assertEqual(recipe["init_pointcloud_mode"], "replace")
        self.assertEqual(recipe["mvs_seed_init_opacity"], 0.25)
        self.assertTrue(recipe["seed_protect"])
        self.assertIsNone(recipe["seed_protect_until_iter"])
        self.assertEqual(recipe["arm_A_depth_weight"], 0.5)
        self.assertEqual(recipe["arm_A_normal_weight"], 0.05)
        self.assertEqual(recipe["w_distort"], 100.0)
        self.assertEqual(recipe["distort_normalization"], "scene_scale_sq")
        self.assertEqual(recipe["distort_warmup"], 15000)
        self.assertEqual(recipe["distort_ramp_steps"], 5000)
        self.assertEqual(recipe["grow_grad2d"], 0.001)
        self.assertEqual(recipe["refine_stop_iter"], 15000)
        self.assertEqual(recipe["refine_every"], 200)
        self.assertEqual(recipe["eval_every"], 2000)
        self.assertEqual(
            recipe["full_state_checkpoint_steps"],
            [5000, 10000, 15000, 20000, 25000, 30000],
        )
        self.assertEqual(recipe["loss_grad_audit_every"], 500)
        base = fw.validate_optimizer_densification_base(fw.REPO, cfg)
        self.assertEqual(
            base["sha256"],
            "47e3f10335bc7ced21bfe842c8ea33387bded5e3f198234d7ac8037840d69a40",
        )
        self.assertIn("grow_grad2d", base["exact_inherited_keys"])

    def test_view_split_exact_10_11_30(self):
        contract = self.config["view_contract"]
        ten = [f"v{i}" for i in range(10)]
        eleven = [f"v{i}" for i in range(11)]
        thirty = [f"v{i}" for i in range(30)]
        self.assertEqual(fw.split_views(ten, contract), (ten, []))
        self.assertEqual(fw.split_views(eleven, contract), (eleven[:-1], eleven[-1:]))
        self.assertEqual(fw.split_views(thirty, contract), (thirty[:-1], thirty[-1:]))

    def test_preprocess_full_sha_and_mutation_guard(self):
        snapshot = self._snapshot()
        self.assertEqual(snapshot["view_count"], 11)
        self.assertEqual(snapshot["corrected_images_sha256"], self.config["inputs"][
            "corrected_images_sha256"
        ])
        self.assertEqual(len(snapshot["selected_names"]), 11)
        mask = self.repo / next(iter(snapshot["photo_mask_paths"].values()))
        mask.write_bytes(b"mutated")
        with self.assertRaisesRegex(fw.ContractError, "artifact SHA-256"):
            self._snapshot()

    def test_ablation_diff_is_exactly_four_weights(self):
        snapshot = self._snapshot()
        out = self.repo / "same-output"
        arm_a = fw.build_training_config(
            repo=self.repo,
            config=self.config,
            preprocess=snapshot,
            arm="A",
            run="r1",
            out_dir=out,
        )
        arm_b = fw.build_training_config(
            repo=self.repo,
            config=self.config,
            preprocess=snapshot,
            arm="B",
            run="r1",
            out_dir=out,
        )
        audit = fw.validate_ablation_pair(arm_a, arm_b)
        self.assertEqual(set(audit["difference_keys"]), fw.ABLATION_DIFFERENCES)
        self.assertEqual(arm_a["seed"], arm_b["seed"])
        self.assertEqual(arm_a["photo_mask_dir"], arm_b["photo_mask_dir"])
        self.assertTrue(arm_a["load_depth"] and arm_b["load_depth"])
        self.assertTrue(arm_a["load_normal"] and arm_b["load_normal"])
        self.assertEqual(len(arm_a["train_views"]), 10)
        self.assertEqual(len(arm_a["eval_views"]), 1)
        altered = copy.deepcopy(arm_b)
        altered["w_nc"] = 0.0
        with self.assertRaisesRegex(fw.ContractError, "one-variable"):
            fw.validate_ablation_pair(arm_a, altered)

    def test_materialization_publishes_no_runtime_receipt(self):
        snapshot = self._snapshot()
        fake_git = {
            "branch": "exp/fusion-w1",
            "head": "a" * 40,
            "required_ancestor": self.config["git_contract"]["required_ancestor"],
            "required_ancestor_of_head": True,
            "unexpected_porcelain": [],
            "allowed_runtime_untracked_count": 0,
        }
        fake_bindings = {"r1": "bound", "r2": "PASS"}
        with mock.patch.object(fw, "validate_git_state", return_value=fake_git), mock.patch.object(
            fw, "validate_r1_r2", return_value=fake_bindings
        ), mock.patch.object(fw, "validate_preprocess", return_value=snapshot):
            result = fw.materialize(
                repo=self.repo,
                config_path=self.config_path,
                config=self.config,
                building_id=self.building_id,
                arm="A",
                run="r1",
                require_docker=False,
            )
        self.assertEqual(result["status"], "PASSED")
        target = fw.job_dir(
            self.repo, self.config, self.building_id, "A", "r1"
        )
        self.assertTrue((target / "resolved_config.yaml").is_file())
        self.assertTrue((target / "materialization_manifest.json").is_file())
        for receipt in ("started.json", "completed.json", "failed.json"):
            self.assertFalse((target / receipt).exists())
        self.assertEqual(result["view_roles"]["train_n"], 10)
        self.assertEqual(result["view_roles"]["eval_n"], 1)

    def test_launch_uses_docker_and_atomic_receipts_without_real_docker(self):
        snapshot = self._snapshot()
        fake_git = {
            "branch": "exp/fusion-w1",
            "head": "b" * 40,
            "required_ancestor": self.config["git_contract"]["required_ancestor"],
            "required_ancestor_of_head": True,
            "unexpected_porcelain": [],
            "allowed_runtime_untracked_count": 0,
        }
        fake_bindings = {"r1": "bound", "r2": "PASS"}
        with mock.patch.object(fw, "validate_git_state", return_value=fake_git), mock.patch.object(
            fw, "validate_r1_r2", return_value=fake_bindings
        ), mock.patch.object(fw, "validate_preprocess", return_value=snapshot):
            fw.materialize(
                repo=self.repo,
                config_path=self.config_path,
                config=self.config,
                building_id=self.building_id,
                arm="A",
                run="r1",
                require_docker=False,
            )
        completion = {
            "status": "PASSED",
            "completed_optimizer_updates": 30000,
        }
        target = fw.job_dir(
            self.repo, self.config, self.building_id, "A", "r1"
        )

        def fake_aggregate(**_kwargs):
            payload = {
                "source_rows": 2,
                "aggregate_rows_after_operation": 2,
                "aggregate_sha256_after_operation": "c" * 64,
            }
            fw.atomic_json(
                target / self.config["outputs"]["loss_share_aggregation_receipt"],
                payload,
            )
            return payload

        with mock.patch.object(fw, "validate_git_state", return_value=fake_git), mock.patch.object(
            fw, "validate_r1_r2", return_value=fake_bindings
        ), mock.patch.object(
            fw, "validate_preprocess", return_value=snapshot
        ), mock.patch.object(
            fw, "_probe_forbidden_processes", return_value={"status": "PASSED"}
        ), mock.patch.object(
            fw,
            "_verify_image",
            return_value={"image": "jointbuildgs:dev", "image_id": "pinned"},
        ), mock.patch.object(
            fw, "_verify_training_completion", return_value=completion
        ), mock.patch.object(
            fw, "aggregate_loss_shares", side_effect=fake_aggregate
        ):
            result = fw.launch(
                repo=self.repo,
                config_path=self.config_path,
                config=self.config,
                building_id=self.building_id,
                arm="A",
                run="r1",
                gpu=1,
                now=datetime(2026, 7, 25, 20, 0, tzinfo=timezone.utc),
                popen_factory=FakeProcess,
            )
        self.assertEqual(result["return_code"], 0)
        started = json.loads((target / "started.json").read_text(encoding="utf-8"))
        self.assertEqual(started["command"][:3], ["docker", "compose", "run"])
        self.assertIn("NVIDIA_VISIBLE_DEVICES=1", started["command"])
        self.assertEqual(started["claim_mode"], "atomic_O_EXCL")
        self.assertTrue((target / "completed.json").is_file())
        self.assertFalse((target / "failed.json").exists())
        counters = json.loads(
            (self.repo / "training/runtime_counters.json").read_text(encoding="utf-8")
        )
        self.assertEqual(counters["jobs_claimed"], 1)
        self.assertEqual(counters["docker_processes_started"], 1)
        self.assertEqual(counters["jobs_completed"], 1)
        self.assertEqual(counters["jobs_failed"], 0)

    def test_incremental_loss_share_aggregation_is_atomic_and_idempotent(self):
        snapshot = self._snapshot()
        fake_git = {
            "branch": "exp/fusion-w1",
            "head": "c" * 40,
            "required_ancestor": self.config["git_contract"]["required_ancestor"],
            "required_ancestor_of_head": True,
            "unexpected_porcelain": [],
            "allowed_runtime_untracked_count": 0,
        }
        fake_bindings = {"r1": "bound", "r2": "PASS"}
        with mock.patch.object(fw, "validate_git_state", return_value=fake_git), mock.patch.object(
            fw, "validate_r1_r2", return_value=fake_bindings
        ), mock.patch.object(fw, "validate_preprocess", return_value=snapshot):
            fw.materialize(
                repo=self.repo,
                config_path=self.config_path,
                config=self.config,
                building_id=self.building_id,
                arm="A",
                run="r1",
                require_docker=False,
            )
        target = fw.job_dir(
            self.repo, self.config, self.building_id, "A", "r1"
        )
        source = target / "audit/loss_grad_norms.csv"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "step,component,raw_loss,weight,weighted_loss,weighted_loss_share,"
            "grad_norm,grad_norm_share,grad_status,total_loss,psnr_train,n_primitives\n"
            "0,photo,1,1,1,0.8,2,0.8,,1.25,20,100\n"
            "0,depth,0.5,0.5,0.25,0.2,0.5,0.2,,1.25,20,100\n",
            encoding="utf-8",
        )
        first = fw.aggregate_loss_shares(
            repo=self.repo,
            config=self.config,
            building_id=self.building_id,
            arm="A",
            run="r1",
        )
        second = fw.aggregate_loss_shares(
            repo=self.repo,
            config=self.config,
            building_id=self.building_id,
            arm="A",
            run="r1",
        )
        self.assertTrue(first["append_performed"])
        self.assertFalse(second["append_performed"])
        self.assertEqual(first["source_rows"], 2)
        aggregate = self.repo / self.config["outputs"]["loss_share_csv"]
        with aggregate.open(encoding="utf-8", newline="") as stream:
            rows = list(__import__("csv").DictReader(stream))
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {(row["building_id"], row["arm"], row["run"]) for row in rows},
            {(self.building_id, "A", "r1")},
        )
        receipt = target / self.config["outputs"]["loss_share_aggregation_receipt"]
        self.assertTrue(receipt.is_file())
        self.assertEqual(len(first["aggregate_sha256_after_operation"]), 64)

    def test_cutoff_blocks_start_at_exact_boundary(self):
        cutoff = self.config["launch_contract"]["cutoff_kst"]
        at_cutoff = datetime.fromisoformat(cutoff)
        with self.assertRaisesRegex(fw.ContractError, "at/after cutoff"):
            fw._cutoff_check(cutoff, now=at_cutoff)
        before = at_cutoff.replace(minute=29, second=59)
        result = fw._cutoff_check(cutoff, now=before)
        self.assertEqual(result["seconds_remaining"], 1.0)

    def test_exclusive_receipt_rejects_second_claim(self):
        path = self.repo / "started.json"
        fw.exclusive_json(path, {"schema": fw.STARTED_SCHEMA})
        with self.assertRaisesRegex(fw.ContractError, "already exists"):
            fw.exclusive_json(path, {"schema": fw.STARTED_SCHEMA})


if __name__ == "__main__":
    unittest.main()

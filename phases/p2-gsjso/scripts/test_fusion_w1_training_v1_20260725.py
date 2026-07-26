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
REAL_RETRY_POLICY = (
    Path(__file__).parents[1]
    / "configs"
    / "fusion_w1_training_infra_retry_20260726.json"
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
        self.config["launch_contract"]["writable_environment"]["root"] = (
            "runtime_env"
        )
        self.config["git_contract"]["allowed_runtime_untracked_prefixes"] = [
            "preprocess/",
            "runtime_env/",
            "training/",
        ]
        amendment = json.loads(
            (
                REAL_CONFIG.parent
                / "fusion_w1_cutoff_amendment_20260726.json"
            ).read_text(encoding="utf-8")
        )
        amendment_path = self.repo / "cutoff_amendment.json"
        amendment_path.write_text(
            json.dumps(amendment, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.config["launch_contract"]["cutoff_amendment"] = {
            "path": "cutoff_amendment.json",
            "sha256": digest(amendment_path),
        }
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
        amendment = fw.validate_cutoff_amendment(fw.REPO, cfg)
        self.assertEqual(amendment["status"], "PASSED")
        self.assertEqual(amendment["decision"], "ABOLISH_0630_CUTOFF")
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
        self.assertEqual(
            cfg["launch_contract"]["writable_environment"],
            {
                "root": "phases/p2-gsjso/runs/20260724_fusion_w1/runtime_env",
                "variables": {
                    "HOME": "home",
                    "XDG_CACHE_HOME": "xdg_cache",
                    "TORCH_EXTENSIONS_DIR": "torch_extensions",
                },
            },
        )
        self.assertIn(
            "phases/p2-gsjso/runs/20260724_fusion_w1/runtime_env/",
            cfg["git_contract"]["allowed_runtime_untracked_prefixes"],
        )
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
        environment = result["writable_environment"]
        self.assertEqual(environment["scope"], "shared_fusion_w1_run")
        self.assertEqual(environment["environment_root"], "runtime_env")
        self.assertTrue(environment["validated_within_run_root"])
        self.assertFalse((self.repo / "runtime_env").exists())

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
        environment = started["writable_environment"]
        expected = {
            "HOME": self.repo / "runtime_env/home",
            "TORCH_EXTENSIONS_DIR": self.repo / "runtime_env/torch_extensions",
            "XDG_CACHE_HOME": self.repo / "runtime_env/xdg_cache",
        }
        for key, path in expected.items():
            self.assertTrue(path.is_dir())
            self.assertFalse(path.is_symlink())
            self.assertIn(
                f"{key}={fw.container_path(self.repo, path)}",
                started["command"],
            )
            self.assertTrue(
                environment["directory_state"][key]["writable_and_searchable"]
            )
        self.assertEqual(
            environment["contract"],
            json.loads(
                (target / "materialization_manifest.json").read_text(
                    encoding="utf-8"
                )
            )["writable_environment"],
        )
        self.assertTrue(environment["prepared_before_started_receipt"])
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

    def test_normal_writable_environment_is_fixed_shared_and_fail_closed(self):
        target = fw.job_dir(
            self.repo, self.config, self.building_id, "A", "r1"
        )
        contract = fw.writable_environment_contract(
            repo=self.repo,
            config=self.config,
            target=target,
        )
        self.assertEqual(contract["environment_root"], "runtime_env")
        self.assertEqual(
            contract["variables"]["TORCH_EXTENSIONS_DIR"],
            fw.container_path(self.repo, self.repo / "runtime_env/torch_extensions"),
        )

        escaped = copy.deepcopy(self.config)
        escaped["launch_contract"]["writable_environment"]["variables"][
            "HOME"
        ] = "../outside"
        with self.assertRaisesRegex(fw.ContractError, "escapes run root"):
            fw.writable_environment_contract(
                repo=self.repo,
                config=escaped,
                target=target,
            )

        wrong_root = copy.deepcopy(self.config)
        wrong_root["launch_contract"]["writable_environment"]["root"] = (
            "other_runtime_env"
        )
        with self.assertRaisesRegex(fw.ContractError, "declared run root"):
            fw.writable_environment_contract(
                repo=self.repo,
                config=wrong_root,
                target=target,
            )

        duplicate = copy.deepcopy(self.config)
        duplicate["launch_contract"]["writable_environment"]["variables"][
            "HOME"
        ] = "xdg_cache"
        with self.assertRaisesRegex(fw.ContractError, "must be distinct"):
            fw.writable_environment_contract(
                repo=self.repo,
                config=duplicate,
                target=target,
            )

        outside = self.repo / "outside"
        outside.mkdir()
        (self.repo / "runtime_env").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(fw.ContractError, "root is a symlink"):
            fw.prepare_writable_environment(
                repo=self.repo,
                config=self.config,
                target=target,
            )

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

    def test_human_amendment_allows_start_after_original_cutoff(self):
        cutoff = self.config["launch_contract"]["cutoff_kst"]
        amendment = fw.validate_cutoff_amendment(self.repo, self.config)
        after = datetime.fromisoformat(cutoff).replace(hour=7, minute=0)
        result = fw._cutoff_check(cutoff, now=after, amendment=amendment)
        self.assertTrue(result["original_cutoff_reached"])
        self.assertEqual(result["seconds_since_original_cutoff"], 1800.0)
        self.assertEqual(result["policy"], "HUMAN_AMENDMENT_ABOLISHED_CUTOFF")
        self.assertEqual(result["amendment"]["sha256"], amendment["sha256"])

    def test_cutoff_amendment_hash_drift_fails_closed(self):
        path = self.repo / self.config["launch_contract"]["cutoff_amendment"]["path"]
        path.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(fw.ContractError, "cutoff amendment SHA-256"):
            fw.validate_cutoff_amendment(self.repo, self.config)

    def test_exclusive_receipt_rejects_second_claim(self):
        path = self.repo / "started.json"
        fw.exclusive_json(path, {"schema": fw.STARTED_SCHEMA})
        with self.assertRaisesRegex(fw.ContractError, "already exists"):
            fw.exclusive_json(path, {"schema": fw.STARTED_SCHEMA})

    def test_preoptimizer_cache_failure_retry_is_env_only_and_preserves_root(self):
        snapshot = self._snapshot()
        fake_git = {
            "branch": "exp/fusion-w1",
            "head": "d" * 40,
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
        target = fw.job_dir(self.repo, self.config, self.building_id, "A", "r1")
        materialization_path = target / "materialization_manifest.json"
        materialization = json.loads(materialization_path.read_text(encoding="utf-8"))
        job_key = f"{self.building_id}/arm_A/r1"
        log_path = target / "training.log"
        log_path.write_text(
            "gsplat/cuda/_backend.py\n"
            "PermissionError: [Errno 13] Permission denied: '/.cache'\n",
            encoding="utf-8",
        )
        fw.atomic_json(
            target / "started.json",
            {
                "schema": fw.STARTED_SCHEMA,
                "job_key": job_key,
                "materialization_manifest_sha256": digest(materialization_path),
            },
        )
        fw.atomic_json(
            target / "failed.json",
            {
                "schema": fw.FAILED_SCHEMA,
                "job_key": job_key,
                "return_code": 1,
                "log_sha256": digest(log_path),
            },
        )
        fw.atomic_json(
            target / "full_state_manifest.json",
            {
                "schema": "jointbuildgs.stage2.resume_manifest.v1",
                "learning_runs_started": 0,
                "learning_runs_incremented_this_process": False,
                "start_completed_steps": 0,
                "last_completed_steps": 0,
                "latest_full_checkpoint": None,
            },
        )
        policy = json.loads(REAL_RETRY_POLICY.read_text(encoding="utf-8"))
        policy["required_materialization_head"] = fake_git["head"]
        pinned_paths = {
            "started": target / "started.json",
            "failed": target / "failed.json",
            "log": log_path,
            "full_state": target / "full_state_manifest.json",
        }
        policy["required_failure"]["artifact_sha256"] = {
            label: digest(path) for label, path in pinned_paths.items()
        }
        policy_path = self.repo / "retry_policy.json"
        policy_path.write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        validated_policy = fw.validate_retry_policy(
            self.repo, policy_path, self.config
        )[0]
        original_started = pinned_paths["started"].read_text(encoding="utf-8")
        drifted_started = json.loads(original_started)
        drifted_started["unapproved_drift"] = True
        fw.atomic_json(pinned_paths["started"], drifted_started)
        with self.assertRaisesRegex(fw.ContractError, "original started SHA-256"):
            fw._verify_preoptimizer_cache_failure(
                repo=self.repo,
                config=self.config,
                target=target,
                materialization=materialization,
                materialization_sha256=digest(materialization_path),
                policy=validated_policy,
            )
        fw.atomic_text(pinned_paths["started"], original_started)
        original = fw._job_file_snapshot(target, excluded_directory="infra_retry_01")
        completion = {"status": "PASSED", "completed_optimizer_updates": 30000}
        aggregate = {
            "source_rows": 2,
            "aggregate_rows_after_operation": 2,
            "aggregate_sha256_after_operation": "c" * 64,
        }
        with mock.patch.object(
            fw, "_validate_retry_git_state", return_value={**fake_git, "commit_distance": 1}
        ), mock.patch.object(
            fw, "validate_r1_r2", return_value=fake_bindings
        ), mock.patch.object(
            fw, "validate_preprocess", return_value=snapshot
        ), mock.patch.object(
            fw, "_probe_forbidden_processes", return_value={"status": "PASSED"}
        ), mock.patch.object(
            fw, "_verify_image", return_value={"image": "jointbuildgs:dev", "image_id": "pinned"}
        ), mock.patch.object(
            fw, "_verify_training_completion", return_value=completion
        ), mock.patch.object(
            fw, "aggregate_loss_shares", return_value=aggregate
        ):
            result = fw.retry_infrastructure_failure(
                repo=self.repo,
                config_path=self.config_path,
                config=self.config,
                policy_path=policy_path,
                building_id=self.building_id,
                arm="A",
                run="r1",
                gpu=1,
                now=datetime(2026, 7, 26, 0, 0, tzinfo=timezone.utc),
                popen_factory=FakeProcess,
            )
        self.assertEqual(result["return_code"], 0)
        self.assertTrue((target / "started.json").is_file())
        self.assertTrue((target / "failed.json").is_file())
        self.assertTrue((target / "completed.json").is_file())
        self.assertEqual(
            fw._job_file_snapshot(target, excluded_directory="infra_retry_01"),
            {**original, "completed.json": digest(target / "completed.json")},
        )
        attempt = target / "infra_retry_01"
        retry_started = json.loads(
            (attempt / "retry_started.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            retry_started["retry_config"]["difference_keys"], ["out_dir"]
        )
        retry_yaml = __import__("yaml").safe_load(
            (attempt / "resolved_config.yaml").read_text(encoding="utf-8")
        )
        self.assertIn("out_dir", retry_yaml)
        self.assertNotIn("out", retry_yaml)
        command = retry_started["command"]
        self.assertIn(f"HOME={fw.container_path(self.repo, attempt / 'runtime_env/home')}", command)
        self.assertIn(
            f"XDG_CACHE_HOME={fw.container_path(self.repo, attempt / 'runtime_env/xdg_cache')}",
            command,
        )
        self.assertIn(
            f"TORCH_EXTENSIONS_DIR={fw.container_path(self.repo, attempt / 'runtime_env/torch_extensions')}",
            command,
        )
        counters = json.loads(
            (self.repo / "training/runtime_counters.json").read_text(encoding="utf-8")
        )
        self.assertEqual(counters["infrastructure_retries_claimed"], 1)
        self.assertEqual(counters["infrastructure_retry_docker_processes_started"], 1)
        self.assertEqual(counters["jobs_completed"], 1)
        with self.assertRaisesRegex(fw.ContractError, "completion receipt"):
            fw._verify_preoptimizer_cache_failure(
                repo=self.repo,
                config=self.config,
                target=target,
                materialization=materialization,
                materialization_sha256=digest(materialization_path),
                policy=fw.validate_retry_policy(self.repo, policy_path, self.config)[0],
            )


if __name__ == "__main__":
    unittest.main()

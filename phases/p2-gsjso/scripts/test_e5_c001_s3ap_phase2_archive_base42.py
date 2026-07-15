#!/usr/bin/env python3
"""Stdlib tests for the fail-closed S3-A-prime base-42 archive."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name(
    "e5_c001_s3ap_phase2_archive_base42.py"
)
WRAPPER = Path(__file__).with_name(
    "run_e5_c001_s3ap_phase2_archive_base42.sh"
)
SPEC = importlib.util.spec_from_file_location(
    "s3ap_base42_archive", SCRIPT
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(SCRIPT)
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


JOB_FIELDS = (
    "sequence", "job_id", "job_class", "building_id", "arm", "replicate",
    "random_seed", "height_delta_m", "tilt_deg", "config_path",
    "config_sha256", "data_root", "surface_seed_npz",
    "surface_seed_sha256", "out_dir", "final_checkpoint", "iterations",
    "gt_used", "lod2_used", "als_used", "status",
)

STATUS_FIELDS = (
    "sequence", "job_id", "gpu_id", "status", "attempt", "config_path",
    "config_sha256", "out_dir", "final_checkpoint", "partial_checkpoints",
    "started_utc", "ended_utc", "elapsed_s", "timeout_s", "returncode",
    "log_path", "prepare_manifest_sha256", "data_manifest_sha256",
    "surface_seed_sha256", "job_binding_sha256",
    "final_checkpoint_sha256", "final_checkpoint_it",
    "final_checkpoint_n_prim", "message",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clone(payload):
    return json.loads(json.dumps(payload))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def csv_bytes(
    rows: list[dict[str, str]], fields: tuple[str, ...],
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=fields, lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_csv(
    path: Path,
    rows: list[dict[str, str]],
    fields: tuple[str, ...],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(csv_bytes(rows, fields))


def runner_runtime() -> dict:
    return {
        "docker_image_id": archive.TRAINING_IMAGE_ID,
        "container_uid": 1000,
        "container_gid": 1000,
        "host_uid": 1000,
        "host_gid": 1000,
        "writable_cache_env": {
            name: {"path": path, "writable": True}
            for name, path in archive.EXPECTED_CACHE_ENV.items()
        },
    }


def prepare_runtime() -> dict:
    return {
        "docker_image": archive.TRAINING_IMAGE,
        "docker_image_id": archive.TRAINING_IMAGE_ID,
        "container_uid": 1000,
        "container_gid": 1000,
        "host_uid": 1000,
        "host_gid": 1000,
        "user_mapping_exact": True,
        "writable_cache_env": {
            name: {"path": path, "writable": True}
            for name, path in archive.EXPECTED_CACHE_ENV.items()
        },
    }


class Fixture:
    def __init__(self, repo: Path):
        self.repo = repo
        self.run_root = repo / archive.DEFAULT_RUN_ROOT
        self.jobs_path = self.run_root / "jobs.csv"
        self.status_path = self.run_root / "runner/status.csv"
        self.output_dir = self.run_root / "runner"
        self.lock_path = repo / archive.DEFAULT_LOCK
        self.prewarm_path = repo / archive.PREWARM_MANIFEST
        self.prepare_path = self.run_root / "manifest.json"
        self.extension_path = repo / (
            "results/tum_transfer/e5_s3ap_phase2/runtime/"
            "torch_extensions/gsplat_cuda/gsplat_cuda.so"
        )
        self.jobs: list[dict[str, str]] = []
        self.status_rows: list[dict[str, str]] = []
        self.data_paths: dict[str, Path] = {}
        self._build()

    def rel(self, path: Path) -> str:
        return str(path.relative_to(self.repo))

    def _static_contract(self) -> None:
        for rel in archive.STATIC_PROVENANCE:
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"fixture {rel}\n", encoding="utf-8")
        for container_path in archive.EXPECTED_CACHE_ENV.values():
            suffix = Path(container_path).relative_to(
                archive.CONTAINER_REPO_ROOT
            )
            (self.repo / suffix).mkdir(parents=True, exist_ok=True)
        self.extension_path.parent.mkdir(parents=True, exist_ok=True)
        self.extension_path.write_bytes(b"fixture gsplat cuda extension\n")

        lock = {
            "schema": "jointbuildgs.s3ap.phase2.lock.v1",
            "container_repo_root": archive.CONTAINER_REPO_ROOT,
            "targets": {
                "4907199": {},
                "8568391": {},
                "8568392": {},
            },
            "training": {
                "iterations": 30000,
                "replicates": {"r1": 2001, "r2": 2002},
                "arms": {"a0": {}, "a1": {}, "a2": {}},
                "height_perturbation_m": [
                    0.5, -0.5, 1.0, -1.0, 2.0, -2.0, 4.0, -4.0,
                ],
            },
            "outputs": {
                "prepared_root": (
                    "results/tum_transfer/e5_s3ap_phase2/prepared"
                ),
                "training_root": (
                    "results/tum_transfer/e5_s3ap_phase2/runs"
                ),
                "prepare_run_root": str(archive.DEFAULT_RUN_ROOT),
                "generated_config_dir": str(
                    archive.DEFAULT_RUN_ROOT / "configs"
                ),
                "base_inventory": str(archive.DEFAULT_JOBS),
                "prepare_manifest": str(
                    archive.DEFAULT_RUN_ROOT / "manifest.json"
                ),
                "runner_status": str(archive.DEFAULT_STATUS),
                "runner_log_dir": str(
                    archive.DEFAULT_RUN_ROOT / "runner/logs"
                ),
            },
            "safety": {
                "prepare_starts_training": False,
                "gt_lod2_or_als_allowed_for_input_generation": False,
                "mvs_initialization_allowed": False,
                "output_metadata": {
                    "gt_used": False,
                    "lod2_used": False,
                    "als_used": False,
                },
            },
            "runtime": {
                "docker_image": archive.TRAINING_IMAGE,
                "docker_image_id": archive.TRAINING_IMAGE_ID,
                "gpu_ids": [0, 1],
                "default_run_timeout_s": 7200,
                "host_launcher": archive.HOST_LAUNCHER,
                "writable_cache_env": dict(
                    archive.EXPECTED_CACHE_ENV
                ),
                "gsplat_prewarm": {
                    "script": archive.PREWARM_SCRIPT,
                    "manifest": archive.PREWARM_MANIFEST,
                },
            },
        }
        write_json(self.lock_path, lock)
        prewarm = {
            "schema": archive.PREWARM_SCHEMA,
            "status": "complete",
            "lock_path": self.rel(self.lock_path),
            "lock_sha256": digest(self.lock_path),
            "runtime_attestation": runner_runtime(),
            "script": archive.PREWARM_SCRIPT,
            "script_sha256": digest(
                self.repo / archive.PREWARM_SCRIPT
            ),
            "torch_extensions_dir": (
                archive.EXPECTED_CACHE_ENV["TORCH_EXTENSIONS_DIR"]
            ),
            "extension_module": "gsplat.cuda._backend._C",
            "extension_path": (
                archive.EXPECTED_CACHE_ENV["TORCH_EXTENSIONS_DIR"]
                + "/gsplat_cuda/gsplat_cuda.so"
            ),
            "extension_sha256": digest(self.extension_path),
        }
        write_json(self.prewarm_path, prewarm)

    @staticmethod
    def specs():
        for building in archive.BUILDINGS:
            for arm in archive.BASE_ARMS:
                for replicate in ("r1", "r2"):
                    yield (
                        f"gs_e5_C001_s3ap_b{building}_{arm}_{replicate}",
                        "base",
                        building,
                        arm,
                        replicate,
                        "0.0",
                    )
        for building in archive.BUILDINGS:
            for delta, slug in archive.HEIGHT_GRID:
                yield (
                    f"gs_e5_C001_s3ap_b{building}_a1_dz_{slug}_r1",
                    "height",
                    building,
                    "a1",
                    "r1",
                    delta,
                )

    def _build(self) -> None:
        self._static_contract()
        data_hashes: dict[str, str] = {}
        prepared_buildings: dict[str, dict] = {}
        for building in archive.BUILDINGS:
            data_root_rel = (
                "results/tum_transfer/e5_s3ap_phase2/prepared/"
                f"DEBY_LOD2_{building}"
            )
            data_root = self.repo / data_root_rel
            data_path = data_root / "data_manifest.json"
            write_json(data_path, {
                "schema": archive.PREPARED_SCHEMA,
                "building_id": f"DEBY_LOD2_{building}",
                "data_root": data_root_rel,
                "gt_used": False,
                "lod2_used": False,
                "als_used": False,
            })
            self.data_paths[building] = data_path
            data_hashes[building] = digest(data_path)
            prepared_buildings[building] = {
                "schema": archive.PREPARED_SCHEMA,
                "building_id": f"DEBY_LOD2_{building}",
                "data_root": data_root_rel,
                "data_manifest": f"{data_root_rel}/data_manifest.json",
                "data_manifest_sha256": data_hashes[building],
                "gt_used": False,
                "lod2_used": False,
                "als_used": False,
            }

        pending_status: list[dict[str, str]] = []
        for sequence, spec in enumerate(self.specs(), 1):
            job_id, job_class, building, arm, replicate, delta = spec
            config = (
                self.run_root / "configs" / f"{job_id}.yaml"
            )
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(
                f"max_iter: 30000\nout_dir: fixture/{job_id}\n",
                encoding="utf-8",
            )
            data_root = self.data_paths[building].parent
            if arm == "a0":
                seed = self.repo / (
                    "phases/p2-gsjso/runs/"
                    "20260715_e5_c001_s3ap_phase1_seedprep/seeds/"
                    f"DEBY_LOD2_{building}_p0_surface_seed.npz"
                )
            else:
                seed = data_root / "seeds" / (
                    f"DEBY_LOD2_{building}_a1a2_surface_seed.npz"
                )
            seed.parent.mkdir(parents=True, exist_ok=True)
            if not seed.exists():
                seed.write_bytes(f"seed:{building}:{arm}".encode())
            out_dir = self.repo / (
                "results/tum_transfer/e5_s3ap_phase2/runs/"
                f"{job_id}"
            )
            out_dir.mkdir(parents=True, exist_ok=True)
            final_path = out_dir / "ckpt/final.pt"
            final_path.parent.mkdir()
            final_path.write_bytes(
                f"final:{job_id}:it30000:nprim{100 + sequence}".encode()
            )
            for name in (
                "effective_config.json",
                "view_roles.json",
                "surface_seed_audit.json",
            ):
                write_json(
                    out_dir / name, {"job_id": job_id, "role": name}
                )
            binding = {
                "schema": "jointbuildgs.s3ap.phase2.job_binding.v1",
                "job_id": job_id,
                "config_path": self.rel(config),
                "config_sha256": digest(config),
                "data_root": self.rel(data_root),
                "surface_seed_npz": self.rel(seed),
                "surface_seed_sha256": digest(seed),
                "iterations": 30000,
            }
            write_json(
                out_dir / "phase2_job_binding.json", binding
            )
            log = (
                self.run_root / "runner/logs" / f"{job_id}.log"
            )
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(
                f"[done] 30000 iter final N={100 + sequence}\n",
                encoding="utf-8",
            )
            job = {
                "sequence": str(sequence),
                "job_id": job_id,
                "job_class": job_class,
                "building_id": building,
                "arm": arm,
                "replicate": replicate,
                "random_seed": (
                    "2001" if replicate == "r1" else "2002"
                ),
                "height_delta_m": delta,
                "tilt_deg": "0.0",
                "config_path": self.rel(config),
                "config_sha256": digest(config),
                "data_root": self.rel(data_root),
                "surface_seed_npz": self.rel(seed),
                "surface_seed_sha256": digest(seed),
                "out_dir": self.rel(out_dir),
                "final_checkpoint": self.rel(final_path),
                "iterations": "30000",
                "gt_used": "False",
                "lod2_used": "False",
                "als_used": "False",
                "status": "prepared",
            }
            self.jobs.append(job)
            pending_status.append({
                "sequence": str(sequence),
                "job_id": job_id,
                "gpu_id": str((sequence - 1) % 2),
                "status": "complete",
                "attempt": "1",
                "config_path": job["config_path"],
                "config_sha256": job["config_sha256"],
                "out_dir": job["out_dir"],
                "final_checkpoint": job["final_checkpoint"],
                "partial_checkpoints": "",
                "started_utc": "2026-07-15T00:00:00+00:00",
                "ended_utc": "2026-07-15T00:01:00+00:00",
                "elapsed_s": "60.0",
                "timeout_s": "7200",
                "returncode": "0",
                "log_path": self.rel(log),
                "prepare_manifest_sha256": "",
                "data_manifest_sha256": data_hashes[building],
                "surface_seed_sha256": job["surface_seed_sha256"],
                "job_binding_sha256": digest(
                    out_dir / "phase2_job_binding.json"
                ),
                "final_checkpoint_sha256": digest(final_path),
                "final_checkpoint_it": "30000",
                "final_checkpoint_n_prim": str(100 + sequence),
                "message": "",
            })

        write_csv(self.jobs_path, self.jobs, JOB_FIELDS)
        prepare = {
            "schema": "jointbuildgs.s3ap.phase2.prepare_manifest.v1",
            "status": "complete",
            "mode": "base",
            "training_started": False,
            "job_count": 42,
            "inventory": self.rel(self.jobs_path),
            "inventory_sha256": digest(self.jobs_path),
            "jobs": [{
                "job_id": job["job_id"],
                "config_path": job["config_path"],
                "config_sha256": job["config_sha256"],
                "final_checkpoint": job["final_checkpoint"],
            } for job in self.jobs],
            "lock_path": self.rel(self.lock_path),
            "lock_sha256": digest(self.lock_path),
            "git_head": "a" * 40,
            "runtime_attestation": prepare_runtime(),
            "prepared_buildings": prepared_buildings,
            "gt_used": False,
            "lod2_used": False,
            "als_used": False,
        }
        write_json(self.prepare_path, prepare)
        prepare_hash = digest(self.prepare_path)
        for row in pending_status:
            row["prepare_manifest_sha256"] = prepare_hash
        self.status_rows = pending_status
        self.runner_attestation = {
            "inventory": self.rel(self.jobs_path),
            "jobs": 42,
            "status_counts": {"skipped_final_exists": 42},
            "gpu_ids": [0, 1],
            "timeout_s": 7200,
            "runtime_attestation": runner_runtime(),
            "prepare_manifest_sha256": prepare_hash,
            "training_started": False,
        }
        self.write_status()

    def load_lock(self) -> dict:
        return json.loads(self.lock_path.read_text(encoding="utf-8"))

    def load_prepare(self) -> dict:
        return json.loads(self.prepare_path.read_text(encoding="utf-8"))

    def load_prewarm(self) -> dict:
        return json.loads(self.prewarm_path.read_text(encoding="utf-8"))

    def write_status(self) -> None:
        write_csv(self.status_path, self.status_rows, STATUS_FIELDS)

    def archive(self, *, dry_run: bool = False):
        return archive.archive_base42(
            repo=self.repo,
            jobs_path=self.jobs_path,
            status_path=self.status_path,
            output_dir=self.output_dir,
            runner_dry_run_attestation=self.runner_attestation,
            tools_image_id=archive.TOOLS_IMAGE_ID,
            dry_run=dry_run,
        )


class Base42ArchiveTest(unittest.TestCase):
    def assert_no_archive_outputs(self, fixture: Fixture) -> None:
        for name in (
            archive.SNAPSHOT_NAME,
            archive.ARTIFACTS_NAME,
            archive.COMPLETION_NAME,
        ):
            self.assertFalse((fixture.output_dir / name).exists())

    def validate_fixture_lock(
        self, fixture: Fixture, lock: dict,
    ) -> None:
        archive.validate_lock_contract(
            fixture.repo,
            lock,
            fixture.run_root,
            fixture.jobs_path,
            fixture.status_path,
        )

    def test_success_writes_only_three_files_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            before = {
                path.relative_to(fixture.repo)
                for path in fixture.repo.rglob("*")
                if path.is_file()
            }
            dry = fixture.archive(dry_run=True)
            self.assertTrue(dry["dry_run"])
            self.assert_no_archive_outputs(fixture)
            result = fixture.archive()
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["job_count"], 42)
            self.assertFalse(result["raw_logs_copied"])
            self.assertFalse(result["raw_checkpoints_copied"])
            self.assertEqual(
                result["archive_tools_image_id"],
                archive.TOOLS_IMAGE_ID,
            )
            self.assertEqual(
                result["runner_dry_run_attestation_sha256"],
                hashlib.sha256(
                    archive.canonical_json_bytes(
                        fixture.runner_attestation
                    )
                ).hexdigest(),
            )
            self.assertEqual(
                result["runner_dry_run_attestation"],
                fixture.runner_attestation,
            )
            after = {
                path.relative_to(fixture.repo)
                for path in fixture.repo.rglob("*")
                if path.is_file()
            }
            self.assertEqual(
                after - before,
                {
                    (
                        fixture.output_dir / archive.SNAPSHOT_NAME
                    ).relative_to(fixture.repo),
                    (
                        fixture.output_dir / archive.ARTIFACTS_NAME
                    ).relative_to(fixture.repo),
                    (
                        fixture.output_dir / archive.COMPLETION_NAME
                    ).relative_to(fixture.repo),
                },
            )
            artifact_lines = (
                fixture.output_dir / archive.ARTIFACTS_NAME
            ).read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                len(artifact_lines),
                result["artifacts_manifest_entry_count"],
            )
            self.assertEqual(
                sum("/ckpt/final.pt" in line for line in artifact_lines),
                42,
            )
            self.assertEqual(
                sum("/runner/logs/" in line for line in artifact_lines),
                42,
            )
            self.assertEqual(
                sum("gsplat_cuda.so" in line for line in artifact_lines),
                1,
            )
            second = fixture.archive()
            self.assertEqual(
                second["write_results"][archive.SNAPSHOT_NAME],
                "existing_identical",
            )
            self.assertEqual(
                second["write_results"][archive.COMPLETION_NAME],
                "existing_identical",
            )

    def test_jobs_and_status_headers_are_exact_and_fail_closed(self):
        self.assertEqual(JOB_FIELDS, archive.JOB_CSV_FIELDS)
        self.assertEqual(STATUS_FIELDS, archive.STATUS_CSV_FIELDS)
        for role in ("jobs", "status"):
            for drift in ("duplicate", "extra", "missing", "order"):
                with self.subTest(
                    role=role, drift=drift
                ), tempfile.TemporaryDirectory() as tmp:
                    fixture = Fixture(Path(tmp))
                    path = (
                        fixture.jobs_path
                        if role == "jobs"
                        else fixture.status_path
                    )
                    lines = path.read_text(encoding="utf-8").splitlines()
                    fields = lines[0].split(",")
                    if drift == "duplicate":
                        fields[-1] = fields[0]
                    elif drift == "extra":
                        fields.append("unexpected_extra")
                    elif drift == "missing":
                        fields.pop()
                    else:
                        fields[0], fields[1] = fields[1], fields[0]
                    lines[0] = ",".join(fields)
                    path.write_text(
                        "\n".join(lines) + "\n", encoding="utf-8"
                    )
                    with self.assertRaisesRegex(
                        archive.ArchiveError, "header/order drift"
                    ):
                        fixture.archive()
                    self.assert_no_archive_outputs(fixture)

    def test_completion_tamper_is_fail_closed_for_every_non_observation(self):
        cases = {
            "raw_logs": lambda x: x.__setitem__(
                "raw_logs_copied", True
            ),
            "raw_logs_numeric_false": lambda x: x.__setitem__(
                "raw_logs_copied", 0
            ),
            "raw_checkpoints": lambda x: x.__setitem__(
                "raw_checkpoints_copied", True
            ),
            "job_count": lambda x: x.__setitem__("job_count", 41),
            "job_count_float": lambda x: x.__setitem__(
                "job_count", 42.0
            ),
            "artifact_policy": lambda x: x.__setitem__(
                "artifact_policy", "tampered"
            ),
            "runner_attestation_payload": lambda x: x[
                "runner_dry_run_attestation"
            ].__setitem__("jobs", 41),
            "runner_attestation_sha": lambda x: x.__setitem__(
                "runner_dry_run_attestation_sha256", "0" * 64
            ),
            "runner_payload_and_sha": lambda x: (
                x["runner_dry_run_attestation"].__setitem__("jobs", 41),
                x.__setitem__(
                    "runner_dry_run_attestation_sha256",
                    hashlib.sha256(
                        archive.canonical_json_bytes(
                            x["runner_dry_run_attestation"]
                        )
                    ).hexdigest(),
                ),
            ),
            "extra_key": lambda x: x.__setitem__("extra", "tampered"),
            "missing_key": lambda x: x.pop("prewarm_status"),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                fixture.archive()
                completion_path = (
                    fixture.output_dir / archive.COMPLETION_NAME
                )
                payload = json.loads(
                    completion_path.read_text(encoding="utf-8")
                )
                mutate(payload)
                write_json(completion_path, payload)
                tampered = completion_path.read_bytes()
                with self.assertRaisesRegex(
                    archive.ArchiveError, "completion_base42"
                ):
                    fixture.archive()
                self.assertEqual(completion_path.read_bytes(), tampered)

    def test_completion_allows_only_valid_time_and_git_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            fixture.archive()
            completion_path = (
                fixture.output_dir / archive.COMPLETION_NAME
            )
            payload = json.loads(
                completion_path.read_text(encoding="utf-8")
            )
            payload["created_utc"] = "2026-07-15T00:00:00+00:00"
            payload["archive_git_head"] = "c" * 40
            payload["archive_git_branch"] = "retained-observation"
            write_json(completion_path, payload)
            result = fixture.archive()
            self.assertEqual(
                result["archive_git_branch"], "retained-observation"
            )
            payload["created_utc"] = "not-a-time"
            write_json(completion_path, payload)
            with self.assertRaisesRegex(
                archive.ArchiveError, "created_utc"
            ):
                fixture.archive()

    def test_locked_phase2_grid_and_runtime_drifts_fail_closed(self):
        cases = {
            "target_order": lambda x: x.__setitem__(
                "targets",
                {"8568391": {}, "4907199": {}, "8568392": {}},
            ),
            "target_key": lambda x: x["targets"].pop("8568392"),
            "iterations": lambda x: x["training"].__setitem__(
                "iterations", 29999
            ),
            "replicate_order": lambda x: x["training"].__setitem__(
                "replicates", {"r2": 2002, "r1": 2001}
            ),
            "replicate_seed": lambda x: x["training"][
                "replicates"
            ].__setitem__("r1", 7),
            "arm_keys": lambda x: x["training"]["arms"].pop("a2"),
            "height_order": lambda x: x["training"].__setitem__(
                "height_perturbation_m",
                [-0.5, 0.5, 1.0, -1.0, 2.0, -2.0, 4.0, -4.0],
            ),
            "base_inventory": lambda x: x["outputs"].__setitem__(
                "base_inventory", "drift/jobs.csv"
            ),
            "prepare_manifest": lambda x: x["outputs"].__setitem__(
                "prepare_manifest", "drift/manifest.json"
            ),
            "runner_status": lambda x: x["outputs"].__setitem__(
                "runner_status", "drift/status.csv"
            ),
            "training_root": lambda x: x["outputs"].__setitem__(
                "training_root", "drift/runs"
            ),
            "safety": lambda x: x["safety"].__setitem__(
                "prepare_starts_training", True
            ),
            "output_gt": lambda x: x["safety"][
                "output_metadata"
            ].__setitem__("gt_used", True),
            "image_id": lambda x: x["runtime"].__setitem__(
                "docker_image_id", "sha256:" + "0" * 64
            ),
            "gpu_id_type": lambda x: x["runtime"].__setitem__(
                "gpu_ids", [0.0, 1.0]
            ),
            "cache": lambda x: x["runtime"][
                "writable_cache_env"
            ].__setitem__("HOME", "/tmp/drift"),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                lock = fixture.load_lock()
                mutate(lock)
                with self.assertRaises(archive.ArchiveError):
                    self.validate_fixture_lock(fixture, lock)

    def test_prepare_runtime_attestation_drifts_fail_closed(self):
        valid = prepare_runtime()
        archive.validate_prepare_runtime_attestation(valid)
        cases = {
            "image_tag": lambda x: x.__setitem__(
                "docker_image", "drift:tag"
            ),
            "image_id": lambda x: x.__setitem__(
                "docker_image_id", "sha256:" + "0" * 64
            ),
            "mapping": lambda x: x.__setitem__(
                "user_mapping_exact", False
            ),
            "uid": lambda x: x.__setitem__("container_uid", 999),
            "cache_path": lambda x: x["writable_cache_env"][
                "HOME"
            ].__setitem__("path", "/tmp/drift"),
            "cache_writable": lambda x: x["writable_cache_env"][
                "HOME"
            ].__setitem__("writable", False),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                value = clone(valid)
                mutate(value)
                with self.assertRaises(archive.ArchiveError):
                    archive.validate_prepare_runtime_attestation(value)

    def test_prewarm_schema_paths_hashes_and_cache_drifts_fail_closed(self):
        cases = {
            "schema": lambda x: x.__setitem__("schema", "drift.v1"),
            "status": lambda x: x.__setitem__("status", "failed"),
            "lock_path": lambda x: x.__setitem__(
                "lock_path", "drift/lock.json"
            ),
            "lock_hash": lambda x: x.__setitem__(
                "lock_sha256", "0" * 64
            ),
            "docker": lambda x: x["runtime_attestation"].__setitem__(
                "docker_image_id", "sha256:" + "0" * 64
            ),
            "script": lambda x: x.__setitem__(
                "script", "drift/prewarm.py"
            ),
            "script_hash": lambda x: x.__setitem__(
                "script_sha256", "0" * 64
            ),
            "cache": lambda x: x.__setitem__(
                "torch_extensions_dir", "/tmp/cache"
            ),
            "cache_attestation": lambda x: x[
                "runtime_attestation"
            ]["writable_cache_env"]["HOME"].__setitem__(
                "writable", False
            ),
            "extension_path": lambda x: x.__setitem__(
                "extension_path", "/tmp/gsplat_cuda.so"
            ),
            "extension_hash": lambda x: x.__setitem__(
                "extension_sha256", "0" * 64
            ),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                prewarm = fixture.load_prewarm()
                mutate(prewarm)
                with self.assertRaises(archive.ArchiveError):
                    archive.validate_prewarm_contract(
                        fixture.repo,
                        fixture.lock_path,
                        digest(fixture.lock_path),
                        fixture.load_lock(),
                        fixture.prewarm_path,
                        prewarm,
                        {},
                    )
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            fixture.extension_path.write_bytes(b"actual drift")
            with self.assertRaisesRegex(
                archive.ArchiveError, "actual shared object"
            ):
                archive.validate_prewarm_contract(
                    fixture.repo,
                    fixture.lock_path,
                    digest(fixture.lock_path),
                    fixture.load_lock(),
                    fixture.prewarm_path,
                    fixture.load_prewarm(),
                    {},
                )

    def test_prepared_data_semantic_and_prepare_entry_drifts_fail_closed(self):
        cases = {
            "schema": ("schema", "drift.v1"),
            "building_id": ("building_id", "DEBY_LOD2_wrong"),
            "data_root": ("data_root", "drift/root"),
            "gt": ("gt_used", True),
            "lod2": ("lod2_used", True),
            "als": ("als_used", True),
        }
        for name, (field, value) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                building = archive.BUILDINGS[0]
                path = fixture.data_paths[building]
                data = json.loads(path.read_text(encoding="utf-8"))
                data[field] = value
                write_json(path, data)
                with self.assertRaisesRegex(
                    archive.ArchiveError, "prepared data manifest"
                ):
                    archive.validate_prepared_data_manifest(
                        fixture.repo,
                        fixture.load_prepare(),
                        building,
                        fixture.jobs[0]["data_root"],
                        fixture.status_rows[0]["data_manifest_sha256"],
                        {},
                    )
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            building = archive.BUILDINGS[0]
            prepare = fixture.load_prepare()
            prepare["prepared_buildings"][building][
                "data_manifest_sha256"
            ] = "0" * 64
            with self.assertRaisesRegex(
                archive.ArchiveError, "prepare data manifest hash"
            ):
                archive.validate_prepared_data_manifest(
                    fixture.repo,
                    prepare,
                    building,
                    fixture.jobs[0]["data_root"],
                    fixture.status_rows[0]["data_manifest_sha256"],
                    {},
                )

    def test_runner_dry_run_attestation_is_mandatory_and_bound(self):
        cases = {
            "inventory": lambda x: x.__setitem__(
                "inventory", "drift/jobs.csv"
            ),
            "jobs": lambda x: x.__setitem__("jobs", 41),
            "status": lambda x: x.__setitem__(
                "status_counts", {"skipped_final_exists": 41, "ready": 1}
            ),
            "status_count_type": lambda x: x.__setitem__(
                "status_counts", {"skipped_final_exists": 42.0}
            ),
            "image": lambda x: x["runtime_attestation"].__setitem__(
                "docker_image_id", "sha256:" + "0" * 64
            ),
            "prepare_hash": lambda x: x.__setitem__(
                "prepare_manifest_sha256", "0" * 64
            ),
            "training_started": lambda x: x.__setitem__(
                "training_started", True
            ),
            "extra": lambda x: x.__setitem__("extra", False),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                payload = clone(fixture.runner_attestation)
                mutate(payload)
                with self.assertRaises(archive.ArchiveError):
                    archive.validate_runner_dry_run_attestation(
                        payload,
                        repo=fixture.repo,
                        jobs_path=fixture.jobs_path,
                        prepare_manifest_sha256=digest(
                            fixture.prepare_path
                        ),
                        lock=fixture.load_lock(),
                    )

    def test_status_and_binding_contract_violations_fail_before_writing(self):
        status_cases = {
            "failed_status": ("status", "failed"),
            "nonzero_return": ("returncode", "7"),
            "wrong_iteration": ("final_checkpoint_it", "29999"),
            "zero_primitives": ("final_checkpoint_n_prim", "0"),
            "bad_hash": ("final_checkpoint_sha256", "ABC"),
        }
        for name, (field, value) in status_cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                fixture.status_rows[0][field] = value
                fixture.write_status()
                with self.assertRaises(archive.ArchiveError):
                    fixture.archive()
                self.assert_no_archive_outputs(fixture)

        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            job = fixture.jobs[0]
            binding_path = (
                fixture.repo / job["out_dir"] / "phase2_job_binding.json"
            )
            binding = json.loads(
                binding_path.read_text(encoding="utf-8")
            )
            binding["unbound_extra"] = "tamper"
            write_json(binding_path, binding)
            fixture.status_rows[0]["job_binding_sha256"] = digest(
                binding_path
            )
            fixture.write_status()
            with self.assertRaisesRegex(
                archive.ArchiveError, "key-set drift"
            ):
                fixture.archive()
            self.assert_no_archive_outputs(fixture)

    def test_exact_job_tuple_and_actual_final_hash_drifts_fail_closed(self):
        cases = (
            (0, "building_id", "8568392"),
            (0, "arm", "a1"),
            (1, "random_seed", "2001"),
            (
                18,
                "job_id",
                "gs_e5_C001_s3ap_b4907199_a1_dz_p0p6_r1",
            ),
            (18, "height_delta_m", "0.6"),
            (18, "replicate", "r2"),
            (18, "tilt_deg", "5.0"),
            (0, "config_path", "configs/drift.yaml"),
            (0, "surface_seed_npz", "seeds/drift.npz"),
            (0, "iterations", "29999"),
        )
        for index, field, value in cases:
            with self.subTest(
                index=index, field=field
            ), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                fixture.jobs[index][field] = value
                write_csv(fixture.jobs_path, fixture.jobs, JOB_FIELDS)
                with self.assertRaisesRegex(
                    archive.ArchiveError, "locked tuple drift"
                ):
                    fixture.archive()
                self.assert_no_archive_outputs(fixture)
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            final_path = (
                fixture.repo / fixture.jobs[0]["final_checkpoint"]
            )
            final_path.write_bytes(final_path.read_bytes() + b"drift")
            with self.assertRaisesRegex(
                archive.ArchiveError, "hash mismatch"
            ):
                fixture.archive()
            self.assert_no_archive_outputs(fixture)

    def test_preexisting_different_snapshot_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            snapshot = fixture.output_dir / archive.SNAPSHOT_NAME
            snapshot.write_bytes(b"foreign\n")
            with self.assertRaisesRegex(
                archive.ArchiveError, "already exists"
            ):
                fixture.archive()
            self.assertEqual(snapshot.read_bytes(), b"foreign\n")
            self.assertFalse(
                (fixture.output_dir / archive.ARTIFACTS_NAME).exists()
            )

    def test_canonical_jobs_path_and_tools_image_id_are_mandatory(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            alternate_jobs = fixture.run_root / "same_root_other.csv"
            alternate_jobs.write_bytes(fixture.jobs_path.read_bytes())
            with self.assertRaisesRegex(
                archive.ArchiveError, "canonical locked path"
            ):
                archive.archive_base42(
                    repo=fixture.repo,
                    jobs_path=alternate_jobs,
                    status_path=fixture.status_path,
                    output_dir=fixture.output_dir,
                    runner_dry_run_attestation=(
                        fixture.runner_attestation
                    ),
                    tools_image_id=archive.TOOLS_IMAGE_ID,
                )
            self.assert_no_archive_outputs(fixture)
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            with self.assertRaisesRegex(
                archive.ArchiveError, "tools image ID drift"
            ):
                archive.archive_base42(
                    repo=fixture.repo,
                    jobs_path=fixture.jobs_path,
                    status_path=fixture.status_path,
                    output_dir=fixture.output_dir,
                    runner_dry_run_attestation=(
                        fixture.runner_attestation
                    ),
                    tools_image_id="sha256:" + "0" * 64,
                )
            self.assert_no_archive_outputs(fixture)

    def test_host_wrapper_is_syntax_valid_and_uses_memory_attestation(self):
        subprocess.run(
            ["bash", "-n", str(WRAPPER)],
            check=True,
            capture_output=True,
            text=True,
        )
        launcher = WRAPPER.read_text(encoding="utf-8")
        self.assertIn(
            'RUNNER_DRY_RUN_JSON="$("${TRAINING_LAUNCHER}" run --dry-run)"',
            launcher,
        )
        self.assertIn(
            '--runner-dry-run-attestation-json "${RUNNER_DRY_RUN_JSON}"',
            launcher,
        )
        self.assertIn('"jointbuildgs-p0-tools:t0"', launcher)
        self.assertIn(archive.TOOLS_IMAGE_ID, launcher)
        self.assertIn("docker image inspect --format '{{.Id}}'", launcher)
        self.assertIn(
            '--tools-image-id "${ACTUAL_TOOLS_IMAGE_ID}"',
            launcher,
        )
        self.assertIn(
            '"${ACTUAL_TOOLS_IMAGE_ID}" python "${ARCHIVER}"',
            launcher,
        )
        self.assertNotIn("mktemp", launcher)
        self.assertNotIn("attestation.json", launcher)
        self.assertNotIn("tee ", launcher)


if __name__ == "__main__":
    unittest.main()

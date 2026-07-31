from __future__ import annotations

import copy
import hashlib
import io
import importlib.util
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/repository/validate_two_host_handoff.py"
SCHEMA = json.loads(
    (ROOT / "artifacts/manifests/schemas/two_host_handoff.schema.json").read_text(
        encoding="utf-8"
    )
)
SNAPSHOT_SCHEMA = json.loads(
    (ROOT / "artifacts/manifests/schemas/local_wip_snapshot.schema.json").read_text(
        encoding="utf-8"
    )
)
SPEC = importlib.util.spec_from_file_location("two_host_handoff", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def run(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TwoHostHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.art_temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.artifact_root = Path(self.art_temp.name)
        run(self.repo, "init", "-b", "main")
        run(self.repo, "config", "user.name", "Test")
        run(self.repo, "config", "user.email", "test@example.invalid")
        (self.repo / "base.txt").write_text("base\n", encoding="utf-8")
        run(self.repo, "add", "base.txt")
        run(self.repo, "commit", "-m", "base")
        self.base = run(self.repo, "rev-parse", "HEAD")
        self.handoff_rel = "artifacts/manifests/handoffs/task-001-handoff"
        self.handoff_dir = self.repo / self.handoff_rel
        self.payload = self.offer_payload()
        (self.repo / "offer.txt").write_text("offer\n", encoding="utf-8")
        self.handoff_dir.mkdir(parents=True)
        self.manifest = self.handoff_dir / "000-offered.json"
        self.write_manifest(self.manifest, self.payload)
        run(self.repo, "add", "offer.txt", f"{self.handoff_rel}/000-offered.json")
        run(self.repo, "commit", "-m", "offer")
        self.offer_head = run(self.repo, "rev-parse", "HEAD")
        run(self.repo, "update-ref", "refs/remotes/origin/main", self.offer_head)

    def tearDown(self) -> None:
        self.art_temp.cleanup()
        self.temp.cleanup()

    def offer_payload(self) -> dict:
        return {
            "schema": "jointbuildgs.two_host_handoff.v1",
            "template_only": False,
            "handoff_id": "task-001-handoff",
            "task_id": "TASK-001",
            "created_at": "2026-07-30T00:00:00Z",
            "direction": "work_to_experiment",
            "sender_role": "work_host",
            "receiver_role": "experiment_host",
            "state": "offered",
            "previous_receipt": None,
            "transport": {
                "mode": "serialized_main",
                "branch": "main",
                "target_branch": "main",
                "exclusive_writer_ack": True,
            },
            "commits": {
                "base_main": self.base,
                "offered_head": "SELF",
                "receipt_head": "SELF",
            },
            "scope": {
                "allowed_paths": ["offer.txt", self.handoff_rel],
                "protected_paths": ["docs/evidence"],
                "dirty_wip": False,
                "snapshot_manifest": None,
            },
            "verification": {
                "level": "git_only",
                "verifier_role": "work_host",
                "docker_image_digest": None,
                "commands": [],
                "tests": [],
            },
            "artifacts": {
                "required_for_task": False,
                "availability": {"work_host": "none", "experiment_host": "none"},
                "records": [],
            },
            "scientific": {
                "technical_state": "pending",
                "scientific_verdict": None,
                "promotion_status": "not_requested",
            },
            "receiver_ack": None,
        }

    @staticmethod
    def write_manifest(path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def errors(
        self,
        payload: dict | None = None,
        *,
        manifest: Path | None = None,
        artifact_root: Path | None = None,
    ) -> list[str]:
        errors, _ = MODULE.validate(
            self.repo,
            payload or self.payload,
            schema=SCHEMA,
            manifest_path=manifest or self.manifest,
            artifact_root=artifact_root,
        )
        return errors

    def verified_payload(self) -> tuple[dict, Path, Path]:
        artifact = self.artifact_root / "runs/result.bin"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"verified artifact\n")
        accepted_payload = copy.deepcopy(self.payload)
        accepted_payload.update(
            state="accepted",
            created_at="2026-07-30T00:05:00Z",
            previous_receipt={
                "path": f"{self.handoff_rel}/000-offered.json",
                "sha256": digest(self.manifest),
            },
            receiver_ack={
                "role": "experiment_host",
                "accepted_at": "2026-07-30T00:05:00Z",
                "status": "accepted",
                "issue": None,
            },
        )
        accepted_payload["commits"] = {
            "base_main": self.base,
            "offered_head": self.offer_head,
            "receipt_head": "SELF",
        }
        accepted = self.handoff_dir / "100-accepted.json"
        self.write_manifest(accepted, accepted_payload)
        run(self.repo, "add", f"{self.handoff_rel}/100-accepted.json")
        run(self.repo, "commit", "-m", "accepted")

        payload = copy.deepcopy(self.payload)
        payload.update(
            state="verified",
            created_at="2026-07-30T00:10:00Z",
            previous_receipt={
                "path": f"{self.handoff_rel}/100-accepted.json",
                "sha256": digest(accepted),
            },
            receiver_ack={
                "role": "experiment_host",
                "accepted_at": "2026-07-30T00:10:00Z",
                "status": "verified",
                "issue": None,
            },
        )
        payload["commits"] = {
            "base_main": self.base,
            "offered_head": self.offer_head,
            "receipt_head": "SELF",
        }
        payload["verification"] = {
            "level": "artifact_verified",
            "verifier_role": "experiment_host",
            "docker_image_digest": "sha256:" + "1" * 64,
            "commands": ["python run.py --config config.json"],
            "tests": [{"name": "technical gate", "passed": 1, "failed": 0}],
        }
        payload["artifacts"] = {
            "required_for_task": False,
            "availability": {"work_host": "manifest_only", "experiment_host": "verified_local"},
            "records": [
                {
                    "uri": "artifact://JointBuildGS/runs/result.bin",
                    "bytes": artifact.stat().st_size,
                    "sha256": digest(artifact),
                    "verification_method": "sha256_rehash",
                    "verified_by": "experiment_host",
                    "verified_at": "2026-07-30T00:09:00Z",
                }
            ],
        }
        payload["scientific"] = {
            "technical_state": "complete",
            "scientific_verdict": None,
            "promotion_status": "human_review_required",
        }
        verified = self.handoff_dir / "200-verified.json"
        self.write_manifest(verified, payload)
        run(self.repo, "add", f"{self.handoff_rel}/200-verified.json")
        run(self.repo, "commit", "-m", "verified")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        return payload, verified, artifact

    def required_accepted_payload(
        self,
        *,
        artifact_verified: bool = True,
    ) -> tuple[dict, Path, Path]:
        handoff_id = "task-required-handoff"
        handoff_rel = f"artifacts/manifests/handoffs/{handoff_id}"
        handoff_dir = self.repo / handoff_rel
        artifact = self.artifact_root / "runs/required.bin"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"required artifact\n")

        offered_payload = copy.deepcopy(self.payload)
        offered_payload.update(
            handoff_id=handoff_id,
            task_id="TASK-REQUIRED",
            created_at="2026-07-30T01:00:00Z",
        )
        offered_payload["commits"] = {
            "base_main": self.offer_head,
            "offered_head": "SELF",
            "receipt_head": "SELF",
        }
        offered_payload["scope"]["allowed_paths"] = [handoff_rel, "required-output.txt"]
        offered_payload["artifacts"]["required_for_task"] = True
        offered = handoff_dir / "000-offered.json"
        offered.parent.mkdir(parents=True)
        self.write_manifest(offered, offered_payload)
        run(self.repo, "add", f"{handoff_rel}/000-offered.json")
        run(self.repo, "commit", "-m", "required offer")
        offered_head = run(self.repo, "rev-parse", "HEAD")

        accepted_payload = copy.deepcopy(offered_payload)
        accepted_payload.update(
            state="accepted",
            created_at="2026-07-30T01:05:00Z",
            previous_receipt={
                "path": f"{handoff_rel}/000-offered.json",
                "sha256": digest(offered),
            },
            receiver_ack={
                "role": "experiment_host",
                "accepted_at": "2026-07-30T01:05:00Z",
                "status": "accepted",
                "issue": None,
            },
        )
        accepted_payload["commits"] = {
            "base_main": self.offer_head,
            "offered_head": offered_head,
            "receipt_head": "SELF",
        }
        if artifact_verified:
            accepted_payload["verification"] = {
                "level": "artifact_verified",
                "verifier_role": "experiment_host",
                "docker_image_digest": "sha256:" + "3" * 64,
                "commands": ["sha256sum required input"],
                "tests": [{"name": "required input", "passed": 1, "failed": 0}],
            }
            accepted_payload["artifacts"] = {
                "required_for_task": True,
                "availability": {
                    "work_host": "manifest_only",
                    "experiment_host": "verified_local",
                },
                "records": [
                    {
                        "uri": "artifact://JointBuildGS/runs/required.bin",
                        "bytes": artifact.stat().st_size,
                        "sha256": digest(artifact),
                        "verification_method": "sha256_rehash",
                        "verified_by": "experiment_host",
                        "verified_at": "2026-07-30T01:04:00Z",
                    }
                ],
            }
        accepted = handoff_dir / "100-accepted.json"
        self.write_manifest(accepted, accepted_payload)
        run(self.repo, "add", f"{handoff_rel}/100-accepted.json")
        run(self.repo, "commit", "-m", "required accepted")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        return accepted_payload, accepted, artifact

    def verified_from_required_accepted(
        self,
        accepted_payload: dict,
        accepted: Path,
    ) -> tuple[dict, Path]:
        (self.repo / "required-output.txt").write_text("output\n", encoding="utf-8")
        run(self.repo, "add", "required-output.txt")
        run(self.repo, "commit", "-m", "required output")

        payload = copy.deepcopy(accepted_payload)
        payload.update(
            state="verified",
            created_at="2026-07-30T01:10:00Z",
            previous_receipt={
                "path": accepted.absolute().relative_to(self.repo).as_posix(),
                "sha256": digest(accepted),
            },
            receiver_ack={
                "role": "experiment_host",
                "accepted_at": "2026-07-30T01:10:00Z",
                "status": "verified",
                "issue": None,
            },
        )
        payload["verification"]["commands"] = ["python -m unittest"]
        payload["verification"]["tests"] = [
            {"name": "technical gate", "passed": 1, "failed": 0}
        ]
        payload["scientific"] = {
            "technical_state": "complete",
            "scientific_verdict": None,
            "promotion_status": "human_review_required",
        }
        verified = accepted.parent / "200-verified.json"
        self.write_manifest(verified, payload)
        run(self.repo, "add", verified.absolute().relative_to(self.repo).as_posix())
        run(self.repo, "commit", "-m", "required verified")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        return payload, verified

    def git_only_verified_payload(self) -> tuple[dict, Path]:
        accepted_payload = copy.deepcopy(self.payload)
        accepted_payload.update(
            state="accepted",
            created_at="2026-07-30T00:05:00Z",
            previous_receipt={
                "path": f"{self.handoff_rel}/000-offered.json",
                "sha256": digest(self.manifest),
            },
            receiver_ack={
                "role": "experiment_host",
                "accepted_at": "2026-07-30T00:05:00Z",
                "status": "accepted",
                "issue": None,
            },
        )
        accepted_payload["commits"] = {
            "base_main": self.base,
            "offered_head": self.offer_head,
            "receipt_head": "SELF",
        }
        accepted = self.handoff_dir / "100-accepted.json"
        self.write_manifest(accepted, accepted_payload)
        run(self.repo, "add", f"{self.handoff_rel}/100-accepted.json")
        run(self.repo, "commit", "-m", "git-only accepted")

        payload = copy.deepcopy(accepted_payload)
        payload.update(
            state="verified",
            created_at="2026-07-30T00:10:00Z",
            previous_receipt={
                "path": f"{self.handoff_rel}/100-accepted.json",
                "sha256": digest(accepted),
            },
            receiver_ack={
                "role": "experiment_host",
                "accepted_at": "2026-07-30T00:10:00Z",
                "status": "verified",
                "issue": None,
            },
        )
        payload["verification"] = {
            "level": "git_only",
            "verifier_role": "experiment_host",
            "docker_image_digest": "sha256:" + "4" * 64,
            "commands": ["python -m unittest"],
            "tests": [{"name": "technical gate", "passed": 1, "failed": 0}],
        }
        payload["scientific"] = {
            "technical_state": "complete",
            "scientific_verdict": None,
            "promotion_status": "human_review_required",
        }
        verified = self.handoff_dir / "200-verified.json"
        self.write_manifest(verified, payload)
        run(self.repo, "add", f"{self.handoff_rel}/200-verified.json")
        run(self.repo, "commit", "-m", "git-only verified")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        return payload, verified

    def closed_payload(self, verified_payload: dict, verified: Path) -> dict:
        payload = copy.deepcopy(verified_payload)
        payload.update(
            state="closed",
            created_at="2026-07-30T00:15:00Z",
            previous_receipt={
                "path": f"{self.handoff_rel}/200-verified.json",
                "sha256": digest(verified),
            },
            receiver_ack={
                "role": "experiment_host",
                "accepted_at": "2026-07-30T00:15:00Z",
                "status": "closed",
                "issue": None,
            },
        )
        return payload

    def commit_closed(self, payload: dict) -> Path:
        closed = self.handoff_dir / "300-closed.json"
        self.write_manifest(closed, payload)
        run(self.repo, "add", f"{self.handoff_rel}/300-closed.json")
        run(self.repo, "commit", "-m", "closed")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        return closed

    def test_valid_serialized_main_offer(self) -> None:
        errors, receipt = MODULE.validate(
            self.repo,
            self.payload,
            schema=SCHEMA,
            manifest_path=self.manifest,
        )
        self.assertEqual([], errors)
        self.assertEqual(self.offer_head, receipt)

    def test_schema_required_field_and_extra_field_fail(self) -> None:
        payload = copy.deepcopy(self.payload)
        del payload["handoff_id"]
        payload["unknown"] = True
        errors = self.errors(payload)
        self.assertTrue(any("handoff_id" in item for item in errors))
        self.assertTrue(any("Additional properties" in item for item in errors))

    def test_schema_rejects_short_branch_and_bad_timestamp(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["transport"].update(mode="short_lived_branch", branch="codex/task")
        errors = self.errors(payload)
        self.assertTrue(any("transport.mode" in item for item in errors))
        payload = copy.deepcopy(self.payload)
        payload["created_at"] = "not-a-date"
        self.assertTrue(any("created_at" in item for item in self.errors(payload)))

    def test_actual_commit_diff_must_fit_allowed_scope(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["scope"]["allowed_paths"] = ["src/declared-only"]
        errors = self.errors(payload)
        self.assertTrue(any("outside allowed scope" in item for item in errors))

    def test_protected_path_overlap_fails(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["scope"]["protected_paths"] = ["offer.txt"]
        self.assertTrue(any("overlap" in item for item in self.errors(payload)))

    def test_dirty_tree_requires_dirty_wip_snapshot(self) -> None:
        (self.repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")
        self.assertTrue(any("dirty_wip=false" in item for item in self.errors()))

    def test_stale_origin_fails(self) -> None:
        run(self.repo, "update-ref", "refs/remotes/origin/main", self.base)
        self.assertTrue(any("stale" in item for item in self.errors()))

    def test_working_manifest_must_equal_committed_receipt(self) -> None:
        self.manifest.write_text("{}\n", encoding="utf-8")
        self.assertTrue(any("bytes differ" in item for item in self.errors()))

    def test_receipt_file_modified_in_later_commit_is_not_immutable(self) -> None:
        self.write_manifest(self.manifest, self.payload)
        with self.manifest.open("a", encoding="utf-8") as stream:
            stream.write("\n")
        run(self.repo, "add", f"{self.handoff_rel}/000-offered.json")
        run(self.repo, "commit", "-m", "rewrite receipt")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        errors = self.errors()
        self.assertTrue(any("immutable add-once" in item for item in errors))

    def test_handoff_id_cannot_start_a_second_offered_root(self) -> None:
        second = self.handoff_dir / "999-offered.json"
        self.write_manifest(second, self.payload)
        run(self.repo, "add", f"{self.handoff_rel}/999-offered.json")
        run(self.repo, "commit", "-m", "second offered root")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        errors = self.errors(manifest=second)
        self.assertTrue(any("exactly one offered root" in item for item in errors))

    def test_repo_wide_duplicate_root_and_two_event_commit_fail(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["handoff_id"] = "duplicate-id"
        payload["task_id"] = "TASK-DUPLICATE"
        payload["commits"]["base_main"] = self.offer_head
        payload["scope"]["allowed_paths"] = [
            "offer.txt",
            "artifacts/manifests/handoffs",
        ]
        canonical = (
            self.repo
            / "artifacts/manifests/handoffs/duplicate-id/000-offered.json"
        )
        rogue = (
            self.repo
            / "artifacts/manifests/handoffs/other-directory/000-offered.json"
        )
        canonical.parent.mkdir()
        rogue.parent.mkdir()
        self.write_manifest(canonical, payload)
        self.write_manifest(rogue, payload)
        run(
            self.repo,
            "add",
            "artifacts/manifests/handoffs/duplicate-id/000-offered.json",
            "artifacts/manifests/handoffs/other-directory/000-offered.json",
        )
        run(self.repo, "commit", "-m", "two offered events")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")

        errors = self.errors(payload, manifest=canonical)
        self.assertTrue(any("exactly one offered root" in item for item in errors))
        self.assertTrue(any("exactly one handoff event" in item for item in errors))

    def test_new_handoff_commit_cannot_modify_existing_receipt(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["handoff_id"] = "new-handoff"
        payload["task_id"] = "TASK-NEW"
        payload["commits"]["base_main"] = self.offer_head
        payload["scope"]["allowed_paths"] = [
            "offer.txt",
            "artifacts/manifests/handoffs",
        ]
        new_receipt = (
            self.repo
            / "artifacts/manifests/handoffs/new-handoff/000-offered.json"
        )
        new_receipt.parent.mkdir()
        self.write_manifest(new_receipt, payload)
        with self.manifest.open("a", encoding="utf-8") as stream:
            stream.write("\n")
        run(
            self.repo,
            "add",
            f"{self.handoff_rel}/000-offered.json",
            "artifacts/manifests/handoffs/new-handoff/000-offered.json",
        )
        run(self.repo, "commit", "-m", "new event plus old receipt mutation")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")

        errors = self.errors(payload, manifest=new_receipt)
        self.assertTrue(any("handoff subtree is add-only" in item for item in errors))

    def test_dirty_wip_requires_real_rehearsed_snapshot(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["scope"]["dirty_wip"] = True
        payload["scope"]["snapshot_manifest"] = None
        self.assertTrue(any("snapshot_manifest" in item for item in self.errors(payload)))

        payload["scope"]["snapshot_manifest"] = {
            "path": f"{self.handoff_rel}/missing-snapshot.json",
            "sha256": "0" * 64,
            "restore_rehearsal": "passed",
        }
        errors = self.errors(payload)
        self.assertTrue(any("missing, non-regular" in item for item in errors))

    def test_ordinary_file_cannot_claim_to_be_a_snapshot(self) -> None:
        handoff_rel = "artifacts/manifests/handoffs/opaque-snapshot"
        handoff_dir = self.repo / handoff_rel
        handoff_dir.mkdir()
        ordinary = handoff_dir / "ordinary.txt"
        ordinary.write_text("not a recovery manifest\n", encoding="utf-8")
        payload = copy.deepcopy(self.payload)
        payload["handoff_id"] = "opaque-snapshot"
        payload["task_id"] = "TASK-OPAQUE"
        payload["commits"]["base_main"] = self.offer_head
        payload["scope"]["allowed_paths"] = ["offer.txt", handoff_rel]
        payload["scope"]["dirty_wip"] = True
        payload["scope"]["snapshot_manifest"] = {
            "path": f"{handoff_rel}/ordinary.txt",
            "sha256": digest(ordinary),
            "restore_rehearsal": "passed",
        }
        manifest = handoff_dir / "000-offered.json"
        self.write_manifest(manifest, payload)
        run(self.repo, "add", handoff_rel)
        run(self.repo, "commit", "-m", "opaque snapshot claim")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        errors = self.errors(payload, manifest=manifest)
        self.assertTrue(any("snapshot_manifest is not readable JSON" in item for item in errors))

    def test_valid_structured_dirty_snapshot(self) -> None:
        handoff_rel = "artifacts/manifests/handoffs/valid-snapshot"
        handoff_dir = self.repo / handoff_rel
        snapshot_dir = handoff_dir / "snapshot"
        snapshot_dir.mkdir(parents=True)
        scratch_bytes = b"recover me\n"
        component_bytes = {
            "status": b"? scratch.txt\0",
            "staged_patch": b"",
            "unstaged_patch": b"",
            "staged_names": b"",
            "unstaged_names": b"",
            "untracked_names": b"scratch.txt\0",
        }
        component_paths: dict[str, Path] = {}
        for name, content in component_bytes.items():
            path = snapshot_dir / name
            path.write_bytes(content)
            component_paths[name] = path
        working_files = snapshot_dir / "working_files.tar"
        with tarfile.open(working_files, "w") as archive:
            member = tarfile.TarInfo("scratch.txt")
            member.size = len(scratch_bytes)
            archive.addfile(member, io.BytesIO(scratch_bytes))
        component_paths["working_files"] = working_files

        snapshot_payload = {
            "schema": "jointbuildgs.local_wip_snapshot.v1",
            "created_at": "2026-07-30T00:00:00Z",
            "source_repo": "/test/JointBuildGS",
            "branch": "main",
            "base_commit": self.offer_head,
            "counts": {
                "staged_paths": 0,
                "unstaged_paths": 0,
                "untracked_paths": 1,
                "archive_paths": 1,
            },
            "components": {
                name: {
                    "file": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": digest(path),
                }
                for name, path in component_paths.items()
            },
            "working_file_inventory": [
                {
                    "path": "scratch.txt",
                    "state": "regular",
                    "bytes": len(scratch_bytes),
                    "sha256": hashlib.sha256(scratch_bytes).hexdigest(),
                }
            ],
            "restore_verification": {
                "status": "passed",
                "verified_at": "2026-07-30T00:01:00Z",
                "base_commit": self.offer_head,
                "restored_counts": {
                    "staged_paths": 0,
                    "unstaged_paths": 0,
                    "untracked_paths": 1,
                    "archive_paths": 1,
                },
                "path_sets_match": True,
                "component_hashes_match": True,
            },
        }
        snapshot_manifest = snapshot_dir / "manifest.json"
        self.write_manifest(snapshot_manifest, snapshot_payload)

        payload = copy.deepcopy(self.payload)
        payload["handoff_id"] = "valid-snapshot"
        payload["task_id"] = "TASK-VALID-SNAPSHOT"
        payload["commits"]["base_main"] = self.offer_head
        payload["scope"]["dirty_wip"] = True
        payload["scope"]["allowed_paths"] = ["offer.txt", handoff_rel, "scratch.txt"]
        payload["scope"]["snapshot_manifest"] = {
            "path": f"{handoff_rel}/snapshot/manifest.json",
            "sha256": digest(snapshot_manifest),
            "restore_rehearsal": "passed",
        }
        manifest = handoff_dir / "000-offered.json"
        self.write_manifest(manifest, payload)
        run(self.repo, "add", handoff_rel)
        run(self.repo, "commit", "-m", "valid structured snapshot")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        (self.repo / "scratch.txt").write_bytes(scratch_bytes)

        self.assertEqual([], self.errors(payload, manifest=manifest))
        category_errors: list[str] = []
        MODULE.validate_snapshot_claim(
            self.repo,
            payload,
            category_errors,
            snapshot_schema=SNAPSHOT_SCHEMA,
            dirty={"scratch.txt"},
            dirty_categories={
                "staged_names": {"scratch.txt"},
                "unstaged_names": set(),
                "untracked_names": set(),
            },
        )
        self.assertTrue(
            any("ledger does not match current Git state" in item for item in category_errors)
        )
        (self.repo / "scratch.txt").write_bytes(b"drifted\n")
        errors = self.errors(payload, manifest=manifest)
        self.assertTrue(
            any(
                "current WIP byte count mismatch" in item
                or "current WIP SHA-256 mismatch" in item
                for item in errors
            )
        )
        component_paths["staged_names"].write_bytes(b"scratch.txt\0")
        component_paths["untracked_names"].write_bytes(b"")
        replay_errors: list[str] = []
        MODULE.validate_snapshot_claim(
            self.repo,
            payload,
            replay_errors,
            snapshot_schema=SNAPSHOT_SCHEMA,
        )
        self.assertTrue(
            any("snapshot replay does not reproduce" in item for item in replay_errors)
        )

    def test_required_artifacts_are_rehashed_once_at_accepted(self) -> None:
        payload, manifest, artifact = self.required_accepted_payload()
        with mock.patch.object(
            MODULE,
            "sha256_file",
            wraps=MODULE.sha256_file,
        ) as sha256:
            self.assertEqual(
                [],
                self.errors(
                    payload,
                    manifest=manifest,
                    artifact_root=self.artifact_root,
                ),
            )

        artifact_calls = [
            call
            for call in sha256.call_args_list
            if Path(call.args[0]).resolve() == artifact.resolve()
        ]
        self.assertEqual(1, len(artifact_calls))

    def test_required_accepted_rejects_git_only_without_rehash(self) -> None:
        payload, manifest, _ = self.required_accepted_payload(artifact_verified=False)
        with mock.patch.object(
            MODULE,
            "validate_artifacts",
            wraps=MODULE.validate_artifacts,
        ) as live_validation:
            errors = self.errors(payload, manifest=manifest)

        self.assertTrue(
            any("artifact-required accepted event must be artifact_verified" in item for item in errors)
        )
        self.assertEqual(0, live_validation.call_count)

    def test_verified_inherits_accepted_attestation_without_live_rehash(self) -> None:
        accepted_payload, accepted, _ = self.required_accepted_payload()
        payload, verified = self.verified_from_required_accepted(
            accepted_payload,
            accepted,
        )
        with mock.patch.object(
            MODULE,
            "validate_artifacts",
            wraps=MODULE.validate_artifacts,
        ) as live_validation:
            errors = self.errors(payload, manifest=verified)

        self.assertEqual([], errors)
        self.assertEqual(0, live_validation.call_count)

    def test_valid_first_live_artifact_verification_at_200(self) -> None:
        payload, manifest, _ = self.verified_payload()
        with mock.patch.object(
            MODULE,
            "validate_artifacts",
            wraps=MODULE.validate_artifacts,
        ) as live_validation:
            self.assertEqual(
                [],
                self.errors(
                    payload,
                    manifest=manifest,
                    artifact_root=self.artifact_root,
                ),
            )
        self.assertEqual(1, live_validation.call_count)

    def test_artifact_requirement_cannot_change_after_offer(self) -> None:
        payload, manifest, _ = self.verified_payload()
        payload["artifacts"]["required_for_task"] = True
        errors = self.errors(payload, manifest=manifest, artifact_root=self.artifact_root)
        self.assertTrue(
            any("artifact requirement cannot change" in item for item in errors)
        )

    def test_live_artifact_hash_mismatch_fails(self) -> None:
        payload, manifest, artifact = self.verified_payload()
        artifact.write_bytes(b"drift\n")
        errors = self.errors(payload, manifest=manifest, artifact_root=self.artifact_root)
        self.assertTrue(any("byte count mismatch" in item or "SHA-256 mismatch" in item for item in errors))

    def test_artifact_verified_requires_live_root(self) -> None:
        payload, manifest, _ = self.verified_payload()
        self.assertTrue(any("--artifact-root" in item for item in self.errors(payload, manifest=manifest)))

    def test_verified_event_rejects_failed_tests_and_bad_ack(self) -> None:
        payload, manifest, _ = self.verified_payload()
        payload["verification"]["tests"][0]["failed"] = 7
        payload["receiver_ack"]["status"] = "accepted"
        errors = self.errors(payload, manifest=manifest, artifact_root=self.artifact_root)
        self.assertTrue(any("failed tests" in item for item in errors))
        self.assertTrue(any("status must equal" in item for item in errors))

    def test_verified_event_requires_complete_docker_and_test_evidence(self) -> None:
        payload, manifest, _ = self.verified_payload()
        payload["scientific"]["technical_state"] = "pending"
        payload["verification"]["docker_image_digest"] = None
        payload["verification"]["commands"] = []
        payload["verification"]["tests"] = []
        errors = self.errors(payload, manifest=manifest, artifact_root=self.artifact_root)
        self.assertTrue(any("technical_state=complete" in item for item in errors))
        self.assertTrue(any("command and test evidence" in item for item in errors))
        self.assertTrue(any("Docker image digest" in item for item in errors))

    def test_artifact_required_verified_event_cannot_be_git_only(self) -> None:
        payload, manifest, _ = self.verified_payload()
        payload["artifacts"]["required_for_task"] = True
        payload["verification"]["level"] = "git_only"
        for record in payload["artifacts"]["records"]:
            record["verification_method"] = "not_verified"
            record["verified_by"] = None
            record["verified_at"] = None
        errors = self.errors(payload, manifest=manifest, artifact_root=self.artifact_root)
        self.assertTrue(any("cannot remain git_only" in item for item in errors))

    def test_closed_event_cannot_downgrade_prior_artifact_verification(self) -> None:
        verified_payload, verified, _ = self.verified_payload()
        closed_payload = self.closed_payload(verified_payload, verified)
        closed_payload["verification"]["level"] = "git_only"
        closed_payload["verification"]["verifier_role"] = "work_host"
        closed_payload["artifacts"] = {
            "required_for_task": False,
            "availability": {"work_host": "none", "experiment_host": "none"},
            "records": [],
        }
        closed = self.handoff_dir / "300-closed.json"
        self.write_manifest(closed, closed_payload)
        run(self.repo, "add", f"{self.handoff_rel}/300-closed.json")
        run(self.repo, "commit", "-m", "closed downgrade")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")

        errors = self.errors(
            closed_payload,
            manifest=closed,
            artifact_root=self.artifact_root,
        )
        self.assertTrue(any("verification level cannot be downgraded" in item for item in errors))

    def test_closed_inherits_artifact_attestation_without_live_rehash(self) -> None:
        verified_payload, verified, artifact = self.verified_payload()
        closed_payload = self.closed_payload(verified_payload, verified)
        closed = self.commit_closed(closed_payload)
        artifact.write_bytes(b"changed after immutable verified attestation\n")

        with mock.patch.object(
            MODULE,
            "validate_artifacts",
            wraps=MODULE.validate_artifacts,
        ) as live_validation:
            errors = self.errors(closed_payload, manifest=closed)

        self.assertEqual([], errors)
        self.assertEqual(0, live_validation.call_count)

    def test_closed_cannot_introduce_artifact_verification(self) -> None:
        verified_payload, verified = self.git_only_verified_payload()
        artifact = self.artifact_root / "runs/late.bin"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"late artifact\n")
        closed_payload = self.closed_payload(verified_payload, verified)
        closed_payload["verification"]["level"] = "artifact_verified"
        closed_payload["artifacts"] = {
            "required_for_task": False,
            "availability": {
                "work_host": "manifest_only",
                "experiment_host": "verified_local",
            },
            "records": [
                {
                    "uri": "artifact://JointBuildGS/runs/late.bin",
                    "bytes": artifact.stat().st_size,
                    "sha256": digest(artifact),
                    "verification_method": "sha256_rehash",
                    "verified_by": "experiment_host",
                    "verified_at": "2026-07-30T00:14:00Z",
                }
            ],
        }
        closed = self.commit_closed(closed_payload)

        with mock.patch.object(
            MODULE,
            "validate_artifacts",
            wraps=MODULE.validate_artifacts,
        ) as live_validation:
            errors = self.errors(closed_payload, manifest=closed)

        self.assertTrue(
            any("closed receipt cannot introduce artifact verification" in item for item in errors)
        )
        self.assertEqual(0, live_validation.call_count)

    def test_closed_rejects_changed_artifact_attestation(self) -> None:
        verified_payload, verified, _ = self.verified_payload()
        closed_payload = self.closed_payload(verified_payload, verified)
        closed_payload["artifacts"]["availability"]["work_host"] = "verified_local"
        closed = self.commit_closed(closed_payload)

        errors = self.errors(closed_payload, manifest=closed)
        self.assertTrue(
            any("artifact-verified attestation cannot change" in item for item in errors)
        )

    def test_closed_must_directly_follow_previous_receipt_commit(self) -> None:
        verified_payload, verified, _ = self.verified_payload()
        (self.repo / "offer.txt").write_text("intermediate\n", encoding="utf-8")
        run(self.repo, "add", "offer.txt")
        run(self.repo, "commit", "-m", "intermediate allowed change")
        closed_payload = self.closed_payload(verified_payload, verified)
        closed = self.commit_closed(closed_payload)

        errors = self.errors(closed_payload, manifest=closed)
        self.assertTrue(
            any("closed receipt must directly follow" in item for item in errors)
        )

    def test_closed_commit_rejects_an_extra_allowed_path(self) -> None:
        verified_payload, verified, _ = self.verified_payload()
        closed_payload = self.closed_payload(verified_payload, verified)
        closed = self.handoff_dir / "300-closed.json"
        self.write_manifest(closed, closed_payload)
        (self.repo / "offer.txt").write_text("changed during close\n", encoding="utf-8")
        run(
            self.repo,
            "add",
            f"{self.handoff_rel}/300-closed.json",
            "offer.txt",
        )
        run(self.repo, "commit", "-m", "closed with extra allowed path")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")

        errors = self.errors(closed_payload, manifest=closed)
        self.assertTrue(
            any("closed receipt commit must change exactly" in item for item in errors)
        )

    def test_previous_chain_invariants_are_enforced(self) -> None:
        payload, manifest, _ = self.verified_payload()
        accepted = self.handoff_dir / "100-accepted.json"
        accepted_payload = json.loads(accepted.read_text(encoding="utf-8"))
        accepted_payload["transport"]["exclusive_writer_ack"] = False
        self.write_manifest(accepted, accepted_payload)
        payload["previous_receipt"]["sha256"] = digest(accepted)
        self.write_manifest(manifest, payload)
        run(
            self.repo,
            "add",
            f"{self.handoff_rel}/100-accepted.json",
            f"{self.handoff_rel}/200-verified.json",
        )
        run(self.repo, "commit", "-m", "forge prior receipt")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        errors = self.errors(payload, manifest=manifest, artifact_root=self.artifact_root)
        self.assertTrue(
            any("previous_receipt schema" in item or "immutable add-once" in item for item in errors)
        )

    def test_previous_chain_rechecks_dirty_snapshot_claim(self) -> None:
        offered = copy.deepcopy(self.payload)
        offered["scope"]["dirty_wip"] = True
        offered["scope"]["snapshot_manifest"] = {
            "path": f"{self.handoff_rel}/nonexistent-snapshot.json",
            "sha256": "0" * 64,
            "restore_rehearsal": "passed",
        }
        self.write_manifest(self.manifest, offered)
        run(self.repo, "add", f"{self.handoff_rel}/000-offered.json")
        run(self.repo, "commit", "-m", "offer with fake snapshot")
        offered_commit = run(self.repo, "rev-parse", "HEAD")

        accepted_payload = copy.deepcopy(self.payload)
        accepted_payload.update(
            state="accepted",
            created_at="2026-07-30T00:05:00Z",
            previous_receipt={
                "path": f"{self.handoff_rel}/000-offered.json",
                "sha256": digest(self.manifest),
            },
            receiver_ack={
                "role": "experiment_host",
                "accepted_at": "2026-07-30T00:05:00Z",
                "status": "accepted",
                "issue": None,
            },
        )
        accepted_payload["commits"] = {
            "base_main": self.base,
            "offered_head": offered_commit,
            "receipt_head": "SELF",
        }
        accepted = self.handoff_dir / "100-accepted.json"
        self.write_manifest(accepted, accepted_payload)
        run(self.repo, "add", f"{self.handoff_rel}/100-accepted.json")
        run(self.repo, "commit", "-m", "accepted fake snapshot chain")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")

        errors = self.errors(accepted_payload, manifest=accepted)
        self.assertTrue(
            any(
                "previous_receipt snapshot_manifest is missing" in item
                for item in errors
            )
        )

    def test_receipt_links_must_follow_actual_commit_ancestry(self) -> None:
        accepted_payload = copy.deepcopy(self.payload)
        accepted_payload.update(
            state="accepted",
            created_at="2026-07-30T00:05:00Z",
            previous_receipt={
                "path": f"{self.handoff_rel}/000-offered.json",
                "sha256": digest(self.manifest),
            },
            receiver_ack={
                "role": "experiment_host",
                "accepted_at": "2026-07-30T00:05:00Z",
                "status": "accepted",
                "issue": None,
            },
        )
        accepted_payload["commits"] = {
            "base_main": self.base,
            "offered_head": self.offer_head,
            "receipt_head": "SELF",
        }
        accepted = self.handoff_dir / "100-accepted.json"
        self.write_manifest(accepted, accepted_payload)

        verified_payload = copy.deepcopy(accepted_payload)
        verified_payload.update(
            state="verified",
            created_at="2026-07-30T00:10:00Z",
            previous_receipt={
                "path": f"{self.handoff_rel}/100-accepted.json",
                "sha256": digest(accepted),
            },
            receiver_ack={
                "role": "experiment_host",
                "accepted_at": "2026-07-30T00:10:00Z",
                "status": "verified",
                "issue": None,
            },
        )
        verified_payload["verification"] = {
            "level": "git_only",
            "verifier_role": "experiment_host",
            "docker_image_digest": "sha256:" + "2" * 64,
            "commands": ["python -m unittest"],
            "tests": [{"name": "gate", "passed": 1, "failed": 0}],
        }
        verified_payload["scientific"] = {
            "technical_state": "complete",
            "scientific_verdict": None,
            "promotion_status": "human_review_required",
        }
        verified = self.handoff_dir / "200-verified.json"
        self.write_manifest(verified, verified_payload)
        run(self.repo, "add", f"{self.handoff_rel}/200-verified.json")
        run(self.repo, "commit", "-m", "verified before accepted")
        run(self.repo, "add", f"{self.handoff_rel}/100-accepted.json")
        run(self.repo, "commit", "-m", "accepted too late")

        closed_payload = copy.deepcopy(verified_payload)
        closed_payload.update(
            state="closed",
            created_at="2026-07-30T00:15:00Z",
            previous_receipt={
                "path": f"{self.handoff_rel}/200-verified.json",
                "sha256": digest(verified),
            },
            receiver_ack={
                "role": "experiment_host",
                "accepted_at": "2026-07-30T00:15:00Z",
                "status": "closed",
                "issue": None,
            },
        )
        closed = self.handoff_dir / "300-closed.json"
        self.write_manifest(closed, closed_payload)
        run(self.repo, "add", f"{self.handoff_rel}/300-closed.json")
        run(self.repo, "commit", "-m", "close out-of-order chain")
        run(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")

        errors = self.errors(closed_payload, manifest=closed)
        self.assertTrue(
            any("not an ancestor of its successor" in item for item in errors)
        )

    def test_template_is_not_an_actual_handoff(self) -> None:
        template = json.loads(
            (ROOT / "artifacts/manifests/templates/two_host_handoff.json").read_text(
                encoding="utf-8"
            )
        )
        errors, _ = MODULE.validate(self.repo, template, schema=SCHEMA)
        self.assertTrue(any("template_only" in item for item in errors))


if __name__ == "__main__":
    unittest.main()

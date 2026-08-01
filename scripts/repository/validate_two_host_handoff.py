#!/usr/bin/env python3
"""Validate a JointBuildGS Work Host <-> Experiment Host handoff event."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError


SCHEMA_PATH = Path("artifacts/manifests/schemas/two_host_handoff.schema.json")
SNAPSHOT_SCHEMA_PATH = Path("artifacts/manifests/schemas/local_wip_snapshot.schema.json")
EXPECTED_ROLES = {
    "work_to_experiment": ("work_host", "experiment_host"),
    "experiment_to_work": ("experiment_host", "work_host"),
}
PREDECESSORS = {
    "accepted": {"offered"},
    "verified": {"accepted"},
    "blocked": {"offered", "accepted"},
    "closed": {"verified", "blocked"},
}
STATE_FILENAMES = {
    "offered": "000-offered.json",
    "accepted": "100-accepted.json",
    "verified": "200-verified.json",
    "blocked": "200-blocked.json",
    "closed": "300-closed.json",
}


def git(repo: Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo}", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
    )
    return result.stdout if binary else result.stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_crlf(value: bytes) -> bytes:
    """Normalize only Git checkout CRLF; preserve every other byte."""
    return value.replace(b"\r\n", b"\n")


def valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and value != "."


def path_is_within(path: str, owner: str) -> bool:
    path = path.rstrip("/")
    owner = owner.rstrip("/")
    return path == owner or path.startswith(owner + "/")


def paths_overlap(left: str, right: str) -> bool:
    return path_is_within(left, right) or path_is_within(right, left)


def commit_exists(repo: Path, value: str) -> bool:
    try:
        git(repo, "cat-file", "-e", f"{value}^{{commit}}")
    except subprocess.CalledProcessError:
        return False
    return True


def zpaths(repo: Path, *args: str) -> set[str]:
    output = git(repo, *args, binary=True)
    assert isinstance(output, bytes)
    return {
        item.decode("utf-8", errors="surrogateescape")
        for item in output.split(b"\0")
        if item
    }


def dirty_path_sets(repo: Path) -> dict[str, set[str]]:
    return {
        "staged_names": zpaths(repo, "diff", "--cached", "--name-only", "-z"),
        "unstaged_names": zpaths(repo, "diff", "--name-only", "-z"),
        "untracked_names": zpaths(
            repo,
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ),
    }


def changed_paths(repo: Path, start: str, end: str) -> set[str]:
    return zpaths(repo, "diff", "--name-only", "-z", start, end)


def schema_errors(payload: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path)):
        location = ".".join(str(item) for item in error.absolute_path) or "<root>"
        errors.append(f"schema {location}: {error.message}")
    return errors


def immutable_repo_file(
    repo: Path,
    relative: str,
    errors: list[str],
    *,
    label: str,
    expected_sha256: str | None = None,
    text_eol_portable: bool = False,
) -> tuple[Path | None, str | None]:
    """Resolve an add-once, byte-identical repository receipt or snapshot."""
    if not safe_relative_path(relative):
        errors.append(f"{label} path is unsafe")
        return None, None
    path = repo / relative
    if path.is_symlink():
        errors.append(f"{label} is missing, non-regular, or a symlink")
        return None, None
    resolved = path.resolve()
    if resolved != path.absolute():
        errors.append(f"{label} traverses a symlink")
        return None, None
    try:
        resolved.relative_to(repo)
    except ValueError:
        errors.append(f"{label} escapes repository")
        return None, None
    if not path.is_file():
        errors.append(f"{label} is missing, non-regular, or a symlink")
        return None, None
    try:
        history_raw = git(repo, "log", "--format=%H", "--", relative)
        assert isinstance(history_raw, str)
        history = [item for item in history_raw.splitlines() if item]
    except subprocess.CalledProcessError:
        history = []
    if len(history) != 1:
        errors.append(f"{label} must be an immutable add-once file (history entries={len(history)})")
        return path, history[0] if history else None
    commit = history[0]
    try:
        status_raw = git(
            repo,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-status",
            "-r",
            commit,
            "--",
            relative,
        )
        assert isinstance(status_raw, str)
        statuses = [item for item in status_raw.splitlines() if item]
        committed = git(repo, "show", f"{commit}:{relative}", binary=True)
    except subprocess.CalledProcessError:
        errors.append(f"{label} is not readable from its commit")
        return path, commit
    if statuses != [f"A\t{relative}"]:
        errors.append(f"{label} must be introduced once with Git status A")
    if expected_sha256 is not None and sha256_bytes(committed) != expected_sha256:
        errors.append(f"{label} SHA-256 mismatch")
    working = path.read_bytes()
    if text_eol_portable:
        committed = normalize_crlf(committed)
        working = normalize_crlf(working)
    if committed != working:
        errors.append(f"{label} bytes differ from immutable committed file")
    return path, commit


def resolve_receipt_commit(
    repo: Path,
    manifest_path: Path | None,
    head_ref: str,
    errors: list[str],
) -> str | None:
    if manifest_path is None:
        try:
            value = git(repo, "rev-parse", head_ref)
            assert isinstance(value, str)
            return value
        except subprocess.CalledProcessError:
            errors.append(f"cannot resolve receipt SELF from {head_ref}")
            return None

    manifest_path = manifest_path.absolute()
    try:
        relative = manifest_path.relative_to(repo).as_posix()
    except ValueError:
        errors.append("manifest must be inside the repository")
        return None
    _, commit = immutable_repo_file(
        repo,
        relative,
        errors,
        label="manifest",
        text_eol_portable=True,
    )
    return commit


def validate_receipt_location(
    repo: Path,
    manifest_path: Path | None,
    payload: dict[str, Any],
    errors: list[str],
) -> None:
    if manifest_path is None:
        return
    manifest = manifest_path.absolute()
    try:
        relative = manifest.relative_to(repo)
    except ValueError:
        errors.append("manifest must be inside the repository")
        return
    expected_dir = Path("artifacts/manifests/handoffs") / payload["handoff_id"]
    if relative.parent != expected_dir:
        errors.append(
            "manifest path must be artifacts/manifests/handoffs/<handoff_id>/<event>.json"
        )
        return
    expected_name = STATE_FILENAMES[payload["state"]]
    if relative.name != expected_name:
        errors.append(f"manifest filename for {payload['state']} must be {expected_name}")

    roots = 0
    handoff_root = repo / "artifacts/manifests/handoffs"
    if handoff_root.is_dir() and not handoff_root.is_symlink():
        for candidate in handoff_root.glob("*/*.json"):
            if not candidate.is_file() or candidate.is_symlink():
                continue
            try:
                candidate_payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                candidate_payload.get("handoff_id") == payload["handoff_id"]
                and candidate_payload.get("state") == "offered"
            ):
                roots += 1
    if roots != 1:
        errors.append(f"handoff_id must have exactly one offered root (found={roots})")


def validate_single_event_commit(
    repo: Path,
    receipt: str | None,
    manifest_path: Path | None,
    payload: dict[str, Any],
    errors: list[str],
) -> None:
    if receipt is None or manifest_path is None:
        return
    try:
        raw = git(
            repo,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-status",
            "-r",
            "-z",
            receipt,
            "--",
            "artifacts/manifests/handoffs",
            binary=True,
        )
        assert isinstance(raw, bytes)
    except subprocess.CalledProcessError:
        errors.append("cannot inspect receipt commit handoff changes")
        return
    fields = [item for item in raw.split(b"\0") if item]
    changes: list[tuple[str, list[str]]] = []
    index = 0
    while index < len(fields):
        status = fields[index].decode("ascii", errors="replace")
        index += 1
        path_count = 2 if status[:1] in {"R", "C"} else 1
        if index + path_count > len(fields):
            errors.append("cannot parse receipt commit handoff changes")
            return
        paths = [
            item.decode("utf-8", errors="surrogateescape")
            for item in fields[index : index + path_count]
        ]
        index += path_count
        changes.append((status, paths))

    handoff_dir = f"artifacts/manifests/handoffs/{payload['handoff_id']}"
    event_names = set(STATE_FILENAMES.values())
    events: set[str] = set()
    for status, paths in changes:
        if status != "A":
            errors.append(
                f"handoff subtree is add-only; receipt commit contains {status}: "
                f"{', '.join(paths)}"
            )
            continue
        relative = paths[0]
        if not path_is_within(relative, handoff_dir):
            errors.append(f"receipt commit added path for another handoff: {relative}")
        path = Path(relative)
        if len(path.parts) == 5 and path.name in event_names:
            events.add(relative)
    manifest_relative = manifest_path.absolute().relative_to(repo).as_posix()
    if events != {manifest_relative}:
        errors.append(
            "receipt commit must add exactly one handoff event: the current manifest"
        )


def validate_event_semantics(
    payload: dict[str, Any],
    errors: list[str],
    *,
    prefix: str = "",
) -> None:
    def add(message: str) -> None:
        errors.append(f"{prefix}{message}")

    if not valid_timestamp(payload["created_at"]):
        add("created_at must be a timezone-aware ISO-8601 timestamp")
    if EXPECTED_ROLES[payload["direction"]] != (
        payload["sender_role"],
        payload["receiver_role"],
    ):
        add("direction does not match sender/receiver roles")

    state = payload["state"]
    ack = payload["receiver_ack"]
    if state == "offered":
        if ack is not None:
            add("offered event must not contain receiver_ack")
    else:
        if not isinstance(ack, dict) or ack.get("role") != payload["receiver_role"]:
            add("non-offered event requires acknowledgement by receiver_role")
        elif ack.get("status") != state:
            add("receiver_ack status must equal receipt state")
        if isinstance(ack, dict) and not valid_timestamp(ack.get("accepted_at")):
            add("receiver_ack accepted_at must be a timezone-aware ISO-8601 timestamp")
        if state == "blocked" and not str((ack or {}).get("issue") or "").strip():
            add("blocked event requires a non-empty issue")

    verification = payload["verification"]
    records = payload["artifacts"]["records"]
    required_for_task = payload["artifacts"]["required_for_task"]
    level = verification["level"]
    availability = payload["artifacts"]["availability"]
    if state == "offered" and level != "git_only":
        add("offered event must remain git_only")
    if state == "accepted" and required_for_task:
        if level != "artifact_verified":
            add("artifact-required accepted event must be artifact_verified")
        if verification["docker_image_digest"] is None:
            add("artifact-required accepted event requires Docker image digest")
        if not verification["commands"] or not verification["tests"]:
            add("artifact-required accepted event requires command and test evidence")
    if level == "git_only":
        for record in records:
            if record["verification_method"] != "not_verified":
                add("git_only records must use verification_method=not_verified")
            if record["verified_by"] is not None or record["verified_at"] is not None:
                add("git_only records must not claim a verifier or verification time")
    elif level == "artifact_verified":
        if verification["verifier_role"] != "experiment_host":
            add("artifact_verified requires experiment_host verifier")
        if availability["experiment_host"] != "verified_local":
            add("artifact_verified requires Experiment Host verified_local access")
        if not records:
            add("artifact_verified requires at least one artifact record")
        for record in records:
            if record["verification_method"] != "sha256_rehash":
                add("artifact_verified records require sha256_rehash")
            if record["verified_by"] != "experiment_host" or not record["verified_at"]:
                add("live artifact verification requires Experiment Host timestamp")
    for record in records:
        if record["verified_at"] is not None and not valid_timestamp(record["verified_at"]):
            add("artifact verified_at must be a timezone-aware ISO-8601 timestamp")
    failed = sum(item["failed"] for item in verification["tests"])
    technical = payload["scientific"]["technical_state"]
    if state in {"offered", "accepted"} and technical != "pending":
        add(f"{state} event requires technical_state=pending")
    if state in {"verified", "closed"}:
        if technical != "complete":
            add(f"{state} event requires technical_state=complete")
        if not verification["commands"] or not verification["tests"]:
            add(f"{state} event requires non-empty command and test evidence")
        if verification["docker_image_digest"] is None:
            add(f"{state} event requires Docker image digest")
        if failed:
            add(f"{state} event contains {failed} failed tests")
        if payload["artifacts"]["required_for_task"] and verification["level"] == "git_only":
            add(f"{state} artifact-required event cannot remain git_only")
    if state == "blocked" and technical != "blocked":
        add("blocked event requires technical_state=blocked")
    if state != "blocked" and failed:
        add(f"non-blocked event contains {failed} failed tests")
    if payload["scientific"]["scientific_verdict"] is not None:
        add("scientific_verdict must remain null in every technical handoff")


def validate_snapshot_claim(
    repo: Path,
    payload: dict[str, Any],
    errors: list[str],
    *,
    snapshot_schema: dict[str, Any],
    dirty: set[str] | None = None,
    dirty_categories: dict[str, set[str]] | None = None,
    prefix: str = "",
) -> None:
    scope = payload["scope"]
    snapshot = scope["snapshot_manifest"]
    if scope["dirty_wip"]:
        if not isinstance(snapshot, dict):
            errors.append(f"{prefix}dirty_wip=true requires a snapshot_manifest")
            return
        manifest_path, _ = immutable_repo_file(
            repo,
            snapshot.get("path", ""),
            errors,
            label=f"{prefix}snapshot_manifest".strip(),
            expected_sha256=snapshot.get("sha256"),
            text_eol_portable=True,
        )
        if snapshot.get("restore_rehearsal") != "passed":
            errors.append(f"{prefix}snapshot_manifest restore rehearsal must be passed")
        if manifest_path is None:
            return
        try:
            snapshot_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append(f"{prefix}snapshot_manifest is not readable JSON")
            return
        snapshot_errors = schema_errors(snapshot_payload, snapshot_schema)
        errors.extend(f"{prefix}snapshot_manifest {item}" for item in snapshot_errors)
        if snapshot_errors:
            return
        if snapshot_payload["base_commit"] != payload["commits"]["base_main"]:
            errors.append(f"{prefix}snapshot_manifest base_commit mismatch")
        if not commit_exists(repo, snapshot_payload["base_commit"]):
            errors.append(f"{prefix}snapshot_manifest base_commit is unavailable")

        counts = snapshot_payload["counts"]
        restore = snapshot_payload["restore_verification"]
        if restore["base_commit"] != snapshot_payload["base_commit"]:
            errors.append(f"{prefix}snapshot restore base_commit mismatch")
        if restore["restored_counts"] != counts:
            errors.append(f"{prefix}snapshot restored counts mismatch")

        inventory: dict[str, dict[str, Any]] = {}
        for record in snapshot_payload["working_file_inventory"]:
            relative = record["path"]
            if not safe_relative_path(relative):
                errors.append(f"{prefix}snapshot inventory path is unsafe: {relative!r}")
            if relative in inventory:
                errors.append(f"{prefix}snapshot inventory path is duplicated: {relative}")
            inventory[relative] = record
        if counts["archive_paths"] != len(inventory):
            errors.append(f"{prefix}snapshot archive path count mismatch")

        component_paths: dict[str, Path] = {}
        manifest_parent = manifest_path.parent
        for name, component in snapshot_payload["components"].items():
            component_file = component["file"]
            if not safe_relative_path(component_file):
                errors.append(f"{prefix}snapshot component path is unsafe: {component_file!r}")
                continue
            candidate = manifest_parent / component_file
            try:
                component_relative = candidate.relative_to(repo).as_posix()
            except ValueError:
                errors.append(f"{prefix}snapshot component escapes repository: {component_file}")
                continue
            component_path, _ = immutable_repo_file(
                repo,
                component_relative,
                errors,
                label=f"{prefix}snapshot component {name}".strip(),
                expected_sha256=component["sha256"],
            )
            if component_path is None:
                continue
            if component_path.stat().st_size != component["bytes"]:
                errors.append(f"{prefix}snapshot component byte count mismatch: {name}")
            component_paths[name] = component_path

        ledgers: dict[str, set[str]] = {}
        for name, count_key in (
            ("staged_names", "staged_paths"),
            ("unstaged_names", "unstaged_paths"),
            ("untracked_names", "untracked_paths"),
        ):
            path = component_paths.get(name)
            if path is None:
                continue
            try:
                names = {
                    item.decode("utf-8", errors="surrogateescape")
                    for item in path.read_bytes().split(b"\0")
                    if item
                }
            except OSError:
                errors.append(f"{prefix}snapshot ledger is unreadable: {name}")
                continue
            if any(not safe_relative_path(item) for item in names):
                errors.append(f"{prefix}snapshot ledger contains an unsafe path: {name}")
            if len(names) != counts[count_key]:
                errors.append(f"{prefix}snapshot ledger count mismatch: {name}")
            ledgers[name] = names

        captured = set().union(*ledgers.values()) if ledgers else set()
        if captured != set(inventory):
            errors.append(f"{prefix}snapshot path ledgers do not match working inventory")
        if dirty is not None and captured != dirty:
            errors.append(f"{prefix}snapshot path ledgers do not match current dirty paths")
        if dirty_categories is not None:
            for name, actual in dirty_categories.items():
                if ledgers.get(name, set()) != actual:
                    errors.append(
                        f"{prefix}snapshot {name} ledger does not match current Git state"
                    )
        if dirty is not None:
            for relative, record in inventory.items():
                candidate = repo / relative
                resolved = candidate.resolve()
                if (
                    resolved != candidate.absolute()
                    or not candidate.is_file()
                    or candidate.is_symlink()
                ):
                    errors.append(
                        f"{prefix}snapshot current WIP file is missing, non-regular, or symlink: "
                        f"{relative}"
                    )
                    continue
                if candidate.stat().st_size != record["bytes"]:
                    errors.append(f"{prefix}snapshot current WIP byte count mismatch: {relative}")
                    continue
                if sha256_file(candidate) != record["sha256"]:
                    errors.append(f"{prefix}snapshot current WIP SHA-256 mismatch: {relative}")

        working_files = component_paths.get("working_files")
        if working_files is not None:
            archived: dict[str, tuple[int, str]] = {}
            try:
                with tarfile.open(working_files, "r:*") as archive:
                    for member in archive.getmembers():
                        if member.isdir():
                            continue
                        if not member.isfile() or not safe_relative_path(member.name):
                            errors.append(
                                f"{prefix}snapshot working archive has unsafe member: {member.name}"
                            )
                            continue
                        if member.name in archived:
                            errors.append(
                                f"{prefix}snapshot working archive has duplicate member: "
                                f"{member.name}"
                            )
                            continue
                        stream = archive.extractfile(member)
                        if stream is None:
                            errors.append(
                                f"{prefix}snapshot working archive member is unreadable: {member.name}"
                            )
                            continue
                        digest = hashlib.sha256()
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(block)
                        archived[member.name] = (member.size, digest.hexdigest())
            except (OSError, tarfile.TarError):
                errors.append(f"{prefix}snapshot working_files is not a readable tar archive")
            expected = {
                path: (record["bytes"], record["sha256"])
                for path, record in inventory.items()
            }
            if archived != expected:
                errors.append(f"{prefix}snapshot working archive does not match inventory")

        required_replay = {
            "status",
            "staged_patch",
            "unstaged_patch",
            "staged_names",
            "unstaged_names",
            "untracked_names",
            "working_files",
        }
        if required_replay.issubset(component_paths):
            try:
                with tempfile.TemporaryDirectory(prefix="jbgs-wip-replay-") as temp:
                    replay_repo = Path(temp) / "repo"
                    subprocess.run(
                        [
                            "git",
                            "-c",
                            f"safe.directory={repo}",
                            "clone",
                            "--shared",
                            "--no-checkout",
                            str(repo),
                            str(replay_repo),
                        ],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )

                    def replay(*args: str, binary: bool = False) -> str | bytes:
                        result = subprocess.run(
                            ["git", "-c", f"safe.directory={replay_repo}", *args],
                            cwd=replay_repo,
                            check=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=not binary,
                        )
                        return result.stdout if binary else result.stdout.strip()

                    replay("checkout", "--detach", snapshot_payload["base_commit"])
                    staged_patch = component_paths["staged_patch"]
                    if staged_patch.stat().st_size:
                        replay("apply", "--cached", str(staged_patch))
                        replay("apply", str(staged_patch))
                    unstaged_patch = component_paths["unstaged_patch"]
                    if unstaged_patch.stat().st_size:
                        replay("apply", str(unstaged_patch))

                    with tarfile.open(component_paths["working_files"], "r:*") as archive:
                        for member in archive.getmembers():
                            if member.isdir():
                                continue
                            if not member.isfile() or not safe_relative_path(member.name):
                                continue
                            target = replay_repo / member.name
                            if target.resolve() != target.absolute():
                                errors.append(
                                    f"{prefix}snapshot replay target traverses a symlink: "
                                    f"{member.name}"
                                )
                                continue
                            try:
                                target.resolve().relative_to(replay_repo.resolve())
                            except ValueError:
                                errors.append(
                                    f"{prefix}snapshot replay target escapes temp repository: "
                                    f"{member.name}"
                                )
                                continue
                            target.parent.mkdir(parents=True, exist_ok=True)
                            stream = archive.extractfile(member)
                            if stream is None:
                                continue
                            with target.open("wb") as output:
                                for block in iter(lambda: stream.read(1024 * 1024), b""):
                                    output.write(block)
                            target.chmod(member.mode & 0o777)

                    replay_categories = {
                        "staged_names": zpaths(replay_repo, "diff", "--cached", "--name-only", "-z"),
                        "unstaged_names": zpaths(replay_repo, "diff", "--name-only", "-z"),
                        "untracked_names": zpaths(
                            replay_repo,
                            "ls-files",
                            "--others",
                            "--exclude-standard",
                            "-z",
                        ),
                    }
                    for name, expected_names in ledgers.items():
                        if replay_categories[name] != expected_names:
                            errors.append(
                                f"{prefix}snapshot replay does not reproduce {name}"
                            )
                    replay_status = replay("status", "--porcelain=v2", "-z", binary=True)
                    if replay_status != component_paths["status"].read_bytes():
                        errors.append(
                            f"{prefix}snapshot replay porcelain-v2 status mismatch"
                        )
                    for relative, record in inventory.items():
                        restored = replay_repo / relative
                        if not restored.is_file() or restored.is_symlink():
                            errors.append(
                                f"{prefix}snapshot replay file is missing or non-regular: "
                                f"{relative}"
                            )
                            continue
                        if (
                            restored.stat().st_size != record["bytes"]
                            or sha256_file(restored) != record["sha256"]
                        ):
                            errors.append(
                                f"{prefix}snapshot replay file bytes mismatch: {relative}"
                            )
            except (OSError, subprocess.CalledProcessError, tarfile.TarError):
                errors.append(f"{prefix}snapshot restore replay failed")
    elif snapshot is not None:
        errors.append(f"{prefix}dirty_wip=false requires snapshot_manifest=null")


def validate_previous_chain(
    repo: Path,
    payload: dict[str, Any],
    schema: dict[str, Any],
    snapshot_schema: dict[str, Any],
    errors: list[str],
    *,
    current_receipt: str | None,
) -> tuple[str | None, bool]:
    state = payload["state"]
    previous = payload["previous_receipt"]
    if state == "offered":
        if previous is not None:
            errors.append("offered event must not have a previous_receipt")
        if payload["commits"]["offered_head"] != "SELF":
            errors.append("offered event must use offered_head=SELF")
        return None, False
    if not isinstance(previous, dict):
        errors.append("non-offered event requires previous_receipt")
        return None, False
    if payload["commits"]["offered_head"] == "SELF":
        errors.append("non-offered event must name the immutable offered_head commit")

    invariant_fields = (
        "handoff_id",
        "task_id",
        "direction",
        "sender_role",
        "receiver_role",
        "transport",
    )
    invariant_scope = {
        key: payload["scope"][key] for key in ("allowed_paths", "protected_paths")
    }
    current = payload
    first_previous_commit: str | None = None
    prior_events: list[tuple[dict[str, Any], str, str]] = []
    visited: set[str] = set()
    current_commit = current_receipt
    immediate_predecessor_has_artifact_attestation = False
    while current["state"] != "offered":
        link = current.get("previous_receipt")
        if not isinstance(link, dict):
            errors.append("receipt chain ended before offered event")
            break
        relative = link.get("path")
        if relative in visited:
            errors.append("previous_receipt chain contains a cycle")
            break
        visited.add(str(relative))
        path, commit = immutable_repo_file(
            repo,
            str(relative),
            errors,
            label="previous_receipt",
            expected_sha256=link.get("sha256"),
            text_eol_portable=True,
        )
        if path is None or commit is None:
            break
        if first_previous_commit is None:
            first_previous_commit = commit
        if current_commit is not None:
            if commit == current_commit:
                errors.append("previous_receipt commit must be a strict ancestor")
            else:
                try:
                    git(repo, "merge-base", "--is-ancestor", commit, current_commit)
                except subprocess.CalledProcessError:
                    errors.append("previous_receipt commit is not an ancestor of its successor")
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append("previous_receipt is not readable JSON")
            break
        prior_schema_errors = schema_errors(prior, schema)
        errors.extend(f"previous_receipt {item}" for item in prior_schema_errors)
        if prior_schema_errors:
            break
        is_immediate_predecessor = not prior_events
        if is_immediate_predecessor:
            immediate_predecessor_has_artifact_attestation = (
                prior["verification"]["level"] == "artifact_verified"
            )
        validate_event_semantics(prior, errors, prefix="previous_receipt ")
        validate_snapshot_claim(
            repo,
            prior,
            errors,
            snapshot_schema=snapshot_schema,
            prefix="previous_receipt ",
        )
        for field in invariant_fields:
            if prior[field] != payload[field]:
                errors.append(f"previous_receipt invariant mismatch: {field}")
        if prior["commits"]["base_main"] != payload["commits"]["base_main"]:
            errors.append("previous_receipt invariant mismatch: commits.base_main")
        prior_scope = {
            key: prior["scope"][key] for key in ("allowed_paths", "protected_paths")
        }
        if prior_scope != invariant_scope:
            errors.append("previous_receipt invariant mismatch: task scope")
        if prior["state"] not in PREDECESSORS.get(current["state"], set()):
            errors.append(
                f"invalid immutable state transition: {prior['state']} -> {current['state']}"
            )
        if parse_timestamp(prior["created_at"]) >= parse_timestamp(current["created_at"]):
            errors.append("previous_receipt timestamp is not earlier than its successor")
        if (
            prior["artifacts"]["required_for_task"]
            != current["artifacts"]["required_for_task"]
        ):
            errors.append("artifact requirement cannot change in a successor receipt")
        if (
            is_immediate_predecessor
            and current["state"] == "closed"
            and current["verification"]["level"] == "artifact_verified"
            and prior["verification"]["level"] != "artifact_verified"
        ):
            errors.append("closed receipt cannot introduce artifact verification")
        if prior["verification"]["level"] == "artifact_verified":
            if current["verification"]["level"] != "artifact_verified":
                errors.append("artifact verification level cannot be downgraded")
            if prior["artifacts"] != current["artifacts"]:
                errors.append(
                    "artifact-verified attestation cannot change in a successor receipt"
                )
            for field in ("verifier_role", "docker_image_digest"):
                if prior["verification"][field] != current["verification"][field]:
                    errors.append(
                        "artifact-verified attestation cannot change in a successor "
                        f"receipt: verification.{field}"
                    )
        prior_events.append((prior, commit, str(relative)))
        current = prior
        current_commit = commit

    if not prior_events or prior_events[-1][0]["state"] != "offered":
        errors.append("receipt chain does not terminate at an offered event")
        return first_previous_commit, immediate_predecessor_has_artifact_attestation

    offered_payload, offered_commit, _ = prior_events[-1]
    if offered_payload["previous_receipt"] is not None:
        errors.append("offered event must not have a previous_receipt")
    if offered_payload["commits"]["offered_head"] != "SELF":
        errors.append("offered event must use offered_head=SELF")
    expected_offered = payload["commits"]["offered_head"]
    if expected_offered != offered_commit:
        errors.append("offered_head does not match immutable offered receipt commit")
    for prior, _, _ in prior_events[:-1]:
        if prior["commits"]["offered_head"] != offered_commit:
            errors.append("previous_receipt offered_head chain mismatch")

    chronological = list(reversed(prior_events))
    previous_commit = payload["commits"]["base_main"]
    allowed = payload["scope"]["allowed_paths"]
    protected = payload["scope"]["protected_paths"]
    for _, commit, relative in chronological:
        if commit_exists(repo, previous_commit):
            for changed in sorted(changed_paths(repo, previous_commit, commit)):
                if not any(path_is_within(changed, owner) for owner in allowed):
                    errors.append(f"previous receipt changed path outside allowed scope: {changed}")
                if any(path_is_within(changed, owner) for owner in protected):
                    errors.append(f"previous receipt changed protected path: {changed}")
        else:
            errors.append(f"previous_receipt base commit is unavailable: {previous_commit}")
        previous_commit = commit
    if state == "closed" and current_receipt and first_previous_commit:
        try:
            parent_line = git(repo, "rev-list", "--parents", "-n", "1", current_receipt)
            assert isinstance(parent_line, str)
            parents = parent_line.split()[1:]
        except subprocess.CalledProcessError:
            errors.append("cannot inspect closed receipt commit parent")
        else:
            if parents != [first_previous_commit]:
                errors.append(
                    "closed receipt must directly follow its verified or blocked receipt"
                )
        expected_closed_path = (
            f"artifacts/manifests/handoffs/{payload['handoff_id']}/300-closed.json"
        )
        if changed_paths(repo, first_previous_commit, current_receipt) != {
            expected_closed_path
        }:
            errors.append("closed receipt commit must change exactly 300-closed.json")
    return first_previous_commit, immediate_predecessor_has_artifact_attestation


def artifact_path(root: Path, uri: str) -> Path | None:
    prefixes = ("artifact://JointBuildGS/", "file:/artifacts/JointBuildGS/")
    relative: str | None = None
    for prefix in prefixes:
        if uri.startswith(prefix):
            relative = uri[len(prefix) :]
            break
    if relative is None or not safe_relative_path(relative):
        return None
    candidate = root / relative
    if candidate.is_symlink():
        return None
    resolved = candidate.resolve()
    if resolved != candidate.absolute():
        return None
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def validate_artifacts(
    payload: dict[str, Any],
    artifact_root: Path | None,
    errors: list[str],
    *,
    prefix: str = "",
) -> None:
    def add(message: str) -> None:
        errors.append(f"{prefix}{message}")

    verification = payload.get("verification", {})
    artifacts = payload.get("artifacts", {})
    level = verification.get("level")
    records = artifacts.get("records", [])
    if level == "git_only":
        return
    if level != "artifact_verified":
        return
    if artifact_root is None:
        add("artifact_verified requires --artifact-root for live verification")
        return
    root = artifact_root.resolve()
    for record in records:
        path = artifact_path(root, str(record.get("uri", "")))
        if path is None:
            add(f"unsupported or unsafe artifact URI: {record.get('uri')}")
            continue
        if not path.is_file() or path.is_symlink():
            add(f"artifact is missing, non-regular, or symlink: {path}")
            continue
        if path.stat().st_size != record.get("bytes"):
            add(f"artifact byte count mismatch: {path}")
            continue
        if sha256_file(path) != record.get("sha256"):
            add(f"artifact SHA-256 mismatch: {path}")


def validate(
    repo: Path,
    payload: dict[str, Any],
    *,
    schema: dict[str, Any],
    snapshot_schema: dict[str, Any] | None = None,
    manifest_path: Path | None = None,
    artifact_root: Path | None = None,
    origin_ref: str = "origin/main",
    head_ref: str = "HEAD",
) -> tuple[list[str], str | None]:
    repo = repo.resolve()
    errors = schema_errors(payload, schema)
    if errors:
        return errors, None
    if snapshot_schema is None:
        candidates = (
            repo / SNAPSHOT_SCHEMA_PATH,
            Path(__file__).resolve().parents[2] / SNAPSHOT_SCHEMA_PATH,
        )
        for candidate in candidates:
            if candidate.is_file():
                try:
                    snapshot_schema = json.loads(candidate.read_text(encoding="utf-8"))
                    Draft202012Validator.check_schema(snapshot_schema)
                except (OSError, json.JSONDecodeError, SchemaError) as exc:
                    errors.append(f"cannot load local WIP snapshot schema: {exc}")
                break
        else:
            errors.append("cannot locate local WIP snapshot schema")
    if snapshot_schema is None:
        return errors, None
    if payload["template_only"] is not False:
        errors.append("template_only must be false for an actual handoff")
    validate_event_semantics(payload, errors)

    state = payload["state"]
    validate_receipt_location(repo, manifest_path, payload, errors)
    receipt = resolve_receipt_commit(repo, manifest_path, head_ref, errors)
    validate_single_event_commit(repo, receipt, manifest_path, payload, errors)
    previous_commit, inherited_artifact_attestation = validate_previous_chain(
        repo,
        payload,
        schema,
        snapshot_schema,
        errors,
        current_receipt=receipt,
    )
    base = payload["commits"]["base_main"]
    offered_raw = payload["commits"]["offered_head"]
    offered = receipt if offered_raw == "SELF" else offered_raw
    for label, value in (("base_main", base), ("offered_head", offered), ("receipt_head", receipt)):
        if value and not commit_exists(repo, value):
            errors.append(f"{label} commit is unavailable: {value}")
    if offered and commit_exists(repo, base) and commit_exists(repo, offered):
        try:
            git(repo, "merge-base", "--is-ancestor", base, offered)
        except subprocess.CalledProcessError:
            errors.append("base_main is not an ancestor of offered_head")
    if receipt and offered and commit_exists(repo, offered) and commit_exists(repo, receipt):
        try:
            git(repo, "merge-base", "--is-ancestor", offered, receipt)
        except subprocess.CalledProcessError:
            errors.append("offered_head is not an ancestor of receipt_head")
    try:
        origin = git(repo, "rev-parse", origin_ref)
        assert isinstance(origin, str)
    except subprocess.CalledProcessError:
        errors.append(f"cannot resolve origin reference: {origin_ref}")
        origin = None
    if origin and receipt and origin != receipt:
        errors.append("serialized_main is stale: origin reference != receipt_head")

    allowed = payload["scope"]["allowed_paths"]
    protected = payload["scope"]["protected_paths"]
    for value in [*allowed, *protected]:
        if not safe_relative_path(value):
            errors.append(f"unsafe repository path: {value!r}")
    for left in allowed:
        for right in protected:
            if paths_overlap(left, right):
                errors.append(f"allowed/protected scope overlap: {left} <> {right}")
    if receipt and commit_exists(repo, receipt):
        diff_start = base if state == "offered" else previous_commit
        if diff_start and commit_exists(repo, diff_start):
            for path in sorted(changed_paths(repo, diff_start, receipt)):
                if not any(path_is_within(path, owner) for owner in allowed):
                    errors.append(f"commit changed path outside allowed scope: {path}")
                if any(path_is_within(path, owner) for owner in protected):
                    errors.append(f"commit changed protected path: {path}")

    dirty_categories = dirty_path_sets(repo)
    dirty = set().union(*dirty_categories.values())
    validate_snapshot_claim(
        repo,
        payload,
        errors,
        snapshot_schema=snapshot_schema,
        dirty=dirty if payload["scope"]["dirty_wip"] else None,
        dirty_categories=dirty_categories if payload["scope"]["dirty_wip"] else None,
    )
    if payload["scope"]["dirty_wip"]:
        for path in sorted(dirty):
            if not any(path_is_within(path, owner) for owner in allowed):
                errors.append(f"dirty path outside allowed scope: {path}")
    else:
        if dirty:
            errors.append(f"dirty_wip=false but working tree has {len(dirty)} changed paths")

    if (
        payload["verification"]["level"] == "artifact_verified"
        and not inherited_artifact_attestation
        and not errors
    ):
        validate_artifacts(payload, artifact_root, errors)
    return errors, receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--schema")
    parser.add_argument("--artifact-root")
    parser.add_argument("--origin-ref", default="origin/main")
    parser.add_argument("--head-ref", default="HEAD")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    manifest = Path(args.manifest)
    if not manifest.is_absolute():
        manifest = (Path.cwd() / manifest).absolute()
    schema_path = Path(args.schema).resolve() if args.schema else repo / SCHEMA_PATH
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors, receipt = validate(
        repo,
        payload,
        schema=schema,
        manifest_path=manifest,
        artifact_root=Path(args.artifact_root).resolve() if args.artifact_root else None,
        origin_ref=args.origin_ref,
        head_ref=args.head_ref,
    )
    if errors:
        print("Two-host handoff: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "Two-host handoff: PASS "
        f"(state={payload['state']}, level={payload['verification']['level']}, receipt={receipt})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

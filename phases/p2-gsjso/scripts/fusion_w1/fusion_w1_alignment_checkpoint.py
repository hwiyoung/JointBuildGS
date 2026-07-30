#!/usr/bin/env python3
"""Durable per-building checkpoints for the FUS-W1 alignment gate.

This module is deliberately independent of ``fusion_w1_alignment_gate.py`` so
the numerical implementation can call it without making durability part of the
measurement formula.  It provides:

* hash-bound ``raw``/``micro1`` per-building checkpoints;
* crash-safe, fsync-backed JSON, CSV, and PNG publication;
* chained journals, immutable completion receipts, and verified resume;
* the overnight repeated-error stop rules and durable ``BLOCKED`` receipts;
* content-addressed final bundles with an atomically replaced reader pointer.

All paths are rejected if any existing component is a symbolic link.  Published
files are written through a same-directory temporary file, fsync-ed, renamed,
and followed by a directory fsync.
"""
from __future__ import annotations

import contextlib
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Callable, Iterable, Mapping, Sequence
import uuid


SCHEMA_PREFIX = "jointbuildgs.fusion_w1.alignment_checkpoint"
CHECKPOINT_SCHEMA = f"{SCHEMA_PREFIX}.completed.v1"
IDENTITY_SCHEMA = f"{SCHEMA_PREFIX}.identity.v1"
JOURNAL_SCHEMA = f"{SCHEMA_PREFIX}.journal_event.v1"
BLOCKED_SCHEMA = f"{SCHEMA_PREFIX}.blocked.v1"
BUNDLE_SCHEMA = f"{SCHEMA_PREFIX}.bundle.v1"
POINTER_SCHEMA = f"{SCHEMA_PREFIX}.pointer.v1"
ERROR_POLICY_SCHEMA = f"{SCHEMA_PREFIX}.error_policy.v1"

ALLOWED_ATTEMPTS = frozenset({"raw", "micro1"})
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EVENT_FILE_RE = re.compile(r"^(\d{6})_([0-9a-f]{64})\.json$")
SAFE_ERROR_TYPE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")

FaultHook = Callable[[str, Path], None]
OverlaySource = bytes | bytearray | memoryview | Callable[[], bytes]


class CheckpointError(RuntimeError):
    """Base class for checkpoint and bundle failures."""


class PathSecurityError(CheckpointError):
    """A path could traverse a symlink or an unexpected non-directory."""


class CheckpointIntegrityError(CheckpointError):
    """Published bytes or a journal chain failed verification."""


class CheckpointBindingError(CheckpointError):
    """A caller attempted to reuse a checkpoint under different hash bindings."""


class ImmutableCheckpointError(CheckpointError):
    """A completed checkpoint or pre-checkpoint artifact would be mutated."""


@dataclass(frozen=True)
class CheckpointIdentity:
    """The four result-blind hashes that bind a Gate A measurement run.

    ``input_sha256`` should be the canonical aggregate hash of the locked input
    hash manifest.  ``view_sha256`` binds the selected building/view inventory.
    ``implementation_sha256`` binds the committed numerical implementation.
    """

    config_sha256: str
    input_sha256: str
    view_sha256: str
    implementation_sha256: str

    def __post_init__(self) -> None:
        for name, value in self.as_dict().items():
            _require_sha256(name, value)

    def as_dict(self) -> dict[str, str]:
        return {
            "config_sha256": self.config_sha256,
            "input_sha256": self.input_sha256,
            "view_sha256": self.view_sha256,
            "implementation_sha256": self.implementation_sha256,
        }

    @property
    def key(self) -> str:
        return sha256_bytes(_canonical_json_bytes(self.as_dict()))


@dataclass(frozen=True)
class CheckpointRef:
    building_id: str
    attempt: str

    def __post_init__(self) -> None:
        _require_building_id(self.building_id)
        _require_attempt(self.attempt)


@dataclass(frozen=True)
class ResumeState:
    state: str
    attempt_dir: Path
    checkpoint: Mapping[str, Any] | None
    journal_event_count: int


@dataclass(frozen=True)
class ErrorDecision:
    building_id: str
    error_type: str
    same_error_count_for_building: int
    skip_building: bool
    consecutive_building_count: int
    stop_stage: bool
    blocked_receipt: Path | None


@dataclass(frozen=True)
class BundleResult:
    bundle_id: str
    bundle_dir: Path
    manifest: Mapping[str, Any]
    current_pointer: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    _assert_no_symlink_path(path, require_leaf=True)
    digest = hashlib.sha256()
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        with os.fdopen(fd, "rb", closefd=False) as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    finally:
        os.close(fd)
    return digest.hexdigest()


def canonical_hash_manifest(hashes: Mapping[str, str]) -> str:
    """Return the aggregate input/view hash used by :class:`CheckpointIdentity`."""

    if not hashes:
        raise CheckpointBindingError("hash manifest must not be empty")
    normalized: dict[str, str] = {}
    for name, digest in sorted(hashes.items()):
        if not isinstance(name, str) or not name or "\x00" in name:
            raise CheckpointBindingError("hash manifest names must be non-empty")
        normalized[name] = _require_sha256(f"hash manifest {name}", digest)
    return sha256_bytes(_canonical_json_bytes(normalized))


def _require_sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise CheckpointBindingError(f"{name} must be a lowercase SHA256")
    return value


def _require_building_id(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 512
        or "\x00" in value
    ):
        raise CheckpointBindingError("building_id must be a non-empty safe string")
    return value


def _require_attempt(value: Any) -> str:
    if value not in ALLOWED_ATTEMPTS:
        raise CheckpointBindingError(
            f"attempt must be one of {sorted(ALLOWED_ATTEMPTS)}"
        )
    return str(value)


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CheckpointIntegrityError("JSON payload contains NaN or infinity")
        return value
    if isinstance(value, str):
        return value
    raise CheckpointIntegrityError(
        f"unsupported JSON value type: {type(value).__name__}"
    )


def _canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            _json_value(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _pretty_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            _json_value(payload),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    if isinstance(value, (Mapping, list, tuple)):
        return _canonical_json_bytes(value).decode("utf-8").strip()
    return value


def csv_bytes(
    rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]
) -> bytes:
    fields = list(fieldnames)
    if not fields or len(fields) != len(set(fields)):
        raise CheckpointIntegrityError("CSV fieldnames must be unique and non-empty")
    if any(not isinstance(field, str) or not field for field in fields):
        raise CheckpointIntegrityError("CSV fieldnames must be non-empty strings")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=fields,
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _csv_cell(row.get(field)) for field in fields})
    return output.getvalue().encode("utf-8")


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _assert_no_symlink_path(path: Path, *, require_leaf: bool) -> Path:
    absolute = _lexical_absolute(path)
    parts = absolute.parts
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            if require_leaf or current != absolute:
                raise PathSecurityError(f"path component does not exist: {current}")
            return absolute
        if stat.S_ISLNK(info.st_mode):
            raise PathSecurityError(f"symbolic-link traversal is forbidden: {current}")
        if current != absolute and not stat.S_ISDIR(info.st_mode):
            raise PathSecurityError(f"path parent is not a directory: {current}")
    return absolute


def _ensure_secure_dir(path: Path) -> Path:
    absolute = _lexical_absolute(path)
    parts = absolute.parts
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            try:
                os.mkdir(current, 0o755)
            except FileExistsError:
                pass
            info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode):
            raise PathSecurityError(f"symbolic-link traversal is forbidden: {current}")
        if not stat.S_ISDIR(info.st_mode):
            raise PathSecurityError(f"expected directory: {current}")
    return absolute


def _directory_fd(path: Path) -> int:
    _assert_no_symlink_path(path, require_leaf=True)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return os.open(path, flags)


def _fsync_directory(path: Path) -> None:
    fd = _directory_fd(path)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _leaf_info(parent_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def atomic_write_bytes(
    path: Path,
    data: bytes,
    *,
    replace: bool,
    mode: int = 0o644,
    fault_hook: FaultHook | None = None,
) -> Path:
    """Publish bytes with file fsync, same-dir rename, then directory fsync."""

    if not isinstance(data, bytes):
        raise TypeError("atomic_write_bytes requires bytes")
    destination = _lexical_absolute(path)
    parent = _ensure_secure_dir(destination.parent)
    if destination.name in {"", ".", ".."}:
        raise PathSecurityError("invalid destination filename")
    parent_fd = _directory_fd(parent)
    temp_name = f".{destination.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}"
    temp_created = False
    try:
        existing = _leaf_info(parent_fd, destination.name)
        if existing is not None:
            if stat.S_ISLNK(existing.st_mode):
                raise PathSecurityError(
                    f"refusing to replace symbolic link: {destination}"
                )
            if not stat.S_ISREG(existing.st_mode):
                raise PathSecurityError(
                    f"destination is not a regular file: {destination}"
                )
            if not replace:
                raise FileExistsError(destination)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(temp_name, flags, mode, dir_fd=parent_fd)
        temp_created = True
        try:
            view = memoryview(data)
            written = 0
            while written < len(view):
                count = os.write(fd, view[written:])
                if count <= 0:
                    raise OSError("short atomic write")
                written += count
            os.fsync(fd)
            if fault_hook is not None:
                fault_hook("after_file_fsync", destination)
        finally:
            os.close(fd)
        if not replace and _leaf_info(parent_fd, destination.name) is not None:
            raise FileExistsError(destination)
        latest = _leaf_info(parent_fd, destination.name)
        if latest is not None and stat.S_ISLNK(latest.st_mode):
            raise PathSecurityError(
                f"destination became a symbolic link: {destination}"
            )
        os.replace(
            temp_name,
            destination.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temp_created = False
        if fault_hook is not None:
            fault_hook("after_replace_before_dir_fsync", destination)
        os.fsync(parent_fd)
        if fault_hook is not None:
            fault_hook("after_dir_fsync", destination)
    except BaseException:
        if temp_created:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        raise
    finally:
        os.close(parent_fd)
    return destination


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    replace: bool = False,
    fault_hook: FaultHook | None = None,
) -> Path:
    return atomic_write_bytes(
        path,
        _pretty_json_bytes(payload),
        replace=replace,
        fault_hook=fault_hook,
    )


def atomic_write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fieldnames: Sequence[str],
    *,
    replace: bool = False,
    fault_hook: FaultHook | None = None,
) -> Path:
    return atomic_write_bytes(
        path,
        csv_bytes(rows, fieldnames),
        replace=replace,
        fault_hook=fault_hook,
    )


def atomic_write_png(
    path: Path,
    png_bytes: bytes,
    *,
    replace: bool = False,
    fault_hook: FaultHook | None = None,
) -> Path:
    if not isinstance(png_bytes, bytes) or not png_bytes.startswith(PNG_SIGNATURE):
        raise CheckpointIntegrityError("overlay payload is not PNG bytes")
    return atomic_write_bytes(
        path,
        png_bytes,
        replace=replace,
        fault_hook=fault_hook,
    )


def _read_bytes(path: Path) -> bytes:
    secure = _assert_no_symlink_path(path, require_leaf=True)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(secure, flags)
    try:
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(fd)


def _read_json(path: Path, *, require_canonical_bytes: bool = False) -> Any:
    raw = _read_bytes(path)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckpointIntegrityError(f"invalid JSON: {path}: {exc}") from exc
    if require_canonical_bytes and raw != _pretty_json_bytes(payload):
        raise CheckpointIntegrityError(
            f"JSON control-file bytes are non-canonical or tampered: {path}"
        )
    return payload


def _write_or_verify_bytes(
    path: Path,
    data: bytes,
    *,
    fault_hook: FaultHook | None,
) -> str:
    if path.exists() or path.is_symlink():
        _assert_no_symlink_path(path, require_leaf=True)
        current = _read_bytes(path)
        if current != data:
            raise ImmutableCheckpointError(
                f"existing immutable artifact differs: {path}"
            )
        return sha256_bytes(current)
    atomic_write_bytes(
        path,
        data,
        replace=False,
        fault_hook=fault_hook,
    )
    return sha256_bytes(data)


def _artifact_record(base: Path, path: Path) -> dict[str, Any]:
    data = _read_bytes(path)
    try:
        relative = path.relative_to(base)
    except ValueError as exc:
        raise CheckpointIntegrityError("artifact escaped attempt directory") from exc
    return {
        "path": relative.as_posix(),
        "sha256": sha256_bytes(data),
        "size_bytes": len(data),
    }


def _verify_artifact(base: Path, record: Mapping[str, Any]) -> Path:
    relative = record.get("path")
    if (
        not isinstance(relative, str)
        or not relative
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise CheckpointIntegrityError("invalid artifact-relative path")
    path = base / relative
    _assert_no_symlink_path(path, require_leaf=True)
    data = _read_bytes(path)
    expected_hash = _require_sha256("artifact sha256", record.get("sha256"))
    if sha256_bytes(data) != expected_hash:
        raise CheckpointIntegrityError(f"artifact SHA256 mismatch: {path}")
    if len(data) != record.get("size_bytes"):
        raise CheckpointIntegrityError(f"artifact size mismatch: {path}")
    return path


class AlignmentCheckpointStore:
    """Fsync-backed store used by the per-building Gate A driver."""

    def __init__(self, root: Path):
        self.root = _ensure_secure_dir(Path(root))

    def _run_dir(self, identity: CheckpointIdentity) -> Path:
        return self.root / "runs" / identity.key

    def _identity_path(self, identity: CheckpointIdentity) -> Path:
        return self._run_dir(identity) / "identity.json"

    @staticmethod
    def _building_key(building_id: str) -> str:
        return sha256_bytes(_require_building_id(building_id).encode("utf-8"))

    def attempt_dir(
        self,
        identity: CheckpointIdentity,
        building_id: str,
        attempt: str,
    ) -> Path:
        return (
            self._run_dir(identity)
            / "buildings"
            / self._building_key(building_id)
            / _require_attempt(attempt)
        )

    @contextlib.contextmanager
    def _mutation_lock(self, identity: CheckpointIdentity) -> Iterable[None]:
        run_dir = _ensure_secure_dir(self._run_dir(identity))
        lock_path = run_dir / ".mutation.lock"
        if lock_path.is_symlink():
            raise PathSecurityError(f"lock path is a symlink: {lock_path}")
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(lock_path, flags, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.fsync(fd)
            _fsync_directory(run_dir)
            self._ensure_identity_locked(identity)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _ensure_identity_locked(
        self,
        identity: CheckpointIdentity,
        fault_hook: FaultHook | None = None,
    ) -> None:
        payload = {
            "schema": IDENTITY_SCHEMA,
            "identity_key": identity.key,
            "bindings": identity.as_dict(),
        }
        path = self._identity_path(identity)
        data = _pretty_json_bytes(payload)
        _write_or_verify_bytes(path, data, fault_hook=fault_hook)

    def cleanup_stale_temps(self) -> int:
        """Remove only unpublished helper temp files after verifying no symlinks."""

        _assert_no_symlink_path(self.root, require_leaf=True)
        removed = 0
        for directory, dirnames, filenames in os.walk(
            self.root, topdown=True, followlinks=False
        ):
            directory_path = Path(directory)
            _assert_no_symlink_path(directory_path, require_leaf=True)
            for dirname in list(dirnames):
                candidate = directory_path / dirname
                info = os.lstat(candidate)
                if stat.S_ISLNK(info.st_mode):
                    raise PathSecurityError(
                        f"symbolic link found in checkpoint store: {candidate}"
                    )
                if dirname.startswith(".bundle-tmp-"):
                    _remove_temp_tree(candidate)
                    dirnames.remove(dirname)
                    removed += 1
            for filename in filenames:
                if ".tmp-" not in filename:
                    continue
                candidate = directory_path / filename
                info = os.lstat(candidate)
                if stat.S_ISLNK(info.st_mode):
                    raise PathSecurityError(
                        f"temporary path is a symlink: {candidate}"
                    )
                if not stat.S_ISREG(info.st_mode):
                    raise PathSecurityError(
                        f"temporary path is not a file: {candidate}"
                    )
                os.unlink(candidate)
                removed += 1
            _fsync_directory(directory_path)
        return removed

    def _journal_dir(
        self,
        identity: CheckpointIdentity,
        building_id: str,
        attempt: str,
    ) -> Path:
        return self.attempt_dir(identity, building_id, attempt) / "journal"

    def _append_event_locked(
        self,
        journal_dir: Path,
        *,
        identity: CheckpointIdentity,
        scope: Mapping[str, Any],
        event: str,
        details: Mapping[str, Any],
        fault_hook: FaultHook | None,
    ) -> Mapping[str, Any]:
        events = self._verify_journal(journal_dir, allow_missing=True)
        sequence = len(events) + 1
        previous = events[-1]["event_sha256"] if events else None
        body: dict[str, Any] = {
            "schema": JOURNAL_SCHEMA,
            "sequence": sequence,
            "created_utc": utc_now(),
            "identity_key": identity.key,
            "scope": dict(scope),
            "event": event,
            "details": dict(details),
            "previous_event_sha256": previous,
        }
        event_sha = sha256_bytes(_canonical_json_bytes(body))
        payload = dict(body)
        payload["event_sha256"] = event_sha
        filename = f"{sequence:06d}_{event_sha}.json"
        atomic_write_json(
            _ensure_secure_dir(journal_dir) / filename,
            payload,
            replace=False,
            fault_hook=fault_hook,
        )
        return payload

    def _verify_journal(
        self, journal_dir: Path, *, allow_missing: bool
    ) -> list[Mapping[str, Any]]:
        if not journal_dir.exists() and not journal_dir.is_symlink():
            if allow_missing:
                return []
            raise CheckpointIntegrityError(f"journal missing: {journal_dir}")
        _assert_no_symlink_path(journal_dir, require_leaf=True)
        files = sorted(
            path
            for path in journal_dir.iterdir()
            if path.name.endswith(".json")
        )
        events: list[Mapping[str, Any]] = []
        previous: str | None = None
        for expected_sequence, path in enumerate(files, start=1):
            match = EVENT_FILE_RE.fullmatch(path.name)
            if match is None or int(match.group(1)) != expected_sequence:
                raise CheckpointIntegrityError(
                    f"journal sequence or filename invalid: {path}"
                )
            payload = _read_json(path, require_canonical_bytes=True)
            if not isinstance(payload, Mapping):
                raise CheckpointIntegrityError(f"journal event is not an object: {path}")
            claimed = _require_sha256(
                "journal event_sha256", payload.get("event_sha256")
            )
            body = dict(payload)
            body.pop("event_sha256", None)
            actual = sha256_bytes(_canonical_json_bytes(body))
            if actual != claimed or match.group(2) != claimed:
                raise CheckpointIntegrityError(f"journal event tampered: {path}")
            if payload.get("sequence") != expected_sequence:
                raise CheckpointIntegrityError(f"journal sequence mismatch: {path}")
            if payload.get("previous_event_sha256") != previous:
                raise CheckpointIntegrityError(f"journal chain mismatch: {path}")
            previous = claimed
            events.append(payload)
        return events

    def resume_status(
        self,
        identity: CheckpointIdentity,
        building_id: str,
        attempt: str,
    ) -> ResumeState:
        _require_building_id(building_id)
        _require_attempt(attempt)
        with self._mutation_lock(identity):
            self.cleanup_stale_temps()
            attempt_dir = self.attempt_dir(identity, building_id, attempt)
            checkpoint_path = attempt_dir / "checkpoint.json"
            if checkpoint_path.exists() or checkpoint_path.is_symlink():
                checkpoint = self._verify_completed_locked(
                    identity, building_id, attempt
                )
                events = self._verify_journal(
                    self._journal_dir(identity, building_id, attempt),
                    allow_missing=False,
                )
                return ResumeState(
                    "completed", attempt_dir, checkpoint, len(events)
                )
            if attempt_dir.exists() or attempt_dir.is_symlink():
                _assert_no_symlink_path(attempt_dir, require_leaf=True)
                events = self._verify_journal(
                    self._journal_dir(identity, building_id, attempt),
                    allow_missing=True,
                )
                return ResumeState(
                    "incomplete", attempt_dir, None, len(events)
                )
            return ResumeState("new", attempt_dir, None, 0)

    @staticmethod
    def _validate_numeric_rows(
        building_id: str,
        attempt: str,
        rows: Sequence[Mapping[str, Any]],
        fields: Sequence[str],
    ) -> None:
        if "building_id" not in fields or "attempt" not in fields:
            raise CheckpointBindingError(
                "residual CSV must bind building_id and attempt"
            )
        for index, row in enumerate(rows):
            if row.get("building_id") != building_id:
                raise CheckpointBindingError(
                    f"residual row {index} building_id binding mismatch"
                )
            if row.get("attempt") != attempt:
                raise CheckpointBindingError(
                    f"residual row {index} attempt binding mismatch"
                )

    def complete_attempt(
        self,
        identity: CheckpointIdentity,
        *,
        building_id: str,
        attempt: str,
        residual_rows: Sequence[Mapping[str, Any]],
        residual_fields: Sequence[str],
        summary: Mapping[str, Any],
        overlay: OverlaySource | None,
        fault_hook: FaultHook | None = None,
    ) -> Mapping[str, Any]:
        """Durably complete one building/attempt, or verify an existing result.

        Numeric evidence is made durable before overlay generation.  Overlay
        exceptions are converted to a durable issue artifact; they do not
        remove or invalidate the numeric checkpoint.
        """

        building_id = _require_building_id(building_id)
        attempt = _require_attempt(attempt)
        self._validate_numeric_rows(
            building_id, attempt, residual_rows, residual_fields
        )
        summary_payload = dict(summary)
        for key, expected in (
            ("building_id", building_id),
            ("attempt", attempt),
        ):
            if key in summary_payload and summary_payload[key] != expected:
                raise CheckpointBindingError(f"summary {key} binding mismatch")
            summary_payload[key] = expected
        residual_data = csv_bytes(residual_rows, residual_fields)
        summary_data = _pretty_json_bytes(summary_payload)

        with self._mutation_lock(identity):
            self.cleanup_stale_temps()
            attempt_dir = _ensure_secure_dir(
                self.attempt_dir(identity, building_id, attempt)
            )
            checkpoint_path = attempt_dir / "checkpoint.json"
            if checkpoint_path.exists() or checkpoint_path.is_symlink():
                checkpoint = self._verify_completed_locked(
                    identity, building_id, attempt
                )
                artifacts = checkpoint["artifacts"]
                if artifacts["residuals_csv"]["sha256"] != sha256_bytes(
                    residual_data
                ):
                    raise ImmutableCheckpointError(
                        "completed residual evidence differs from resume input"
                    )
                if artifacts["summary_json"]["sha256"] != sha256_bytes(
                    summary_data
                ):
                    raise ImmutableCheckpointError(
                        "completed summary differs from resume input"
                    )
                return checkpoint

            journal = self._journal_dir(identity, building_id, attempt)
            previous_events = self._verify_journal(journal, allow_missing=True)
            self._append_event_locked(
                journal,
                identity=identity,
                scope={"building_id": building_id, "attempt": attempt},
                event="BEGIN" if not previous_events else "RESUME",
                details={"prior_event_count": len(previous_events)},
                fault_hook=fault_hook,
            )

            residual_path = attempt_dir / "residuals.csv"
            summary_path = attempt_dir / "summary.json"
            residual_sha = _write_or_verify_bytes(
                residual_path, residual_data, fault_hook=fault_hook
            )
            summary_sha = _write_or_verify_bytes(
                summary_path, summary_data, fault_hook=fault_hook
            )
            self._append_event_locked(
                journal,
                identity=identity,
                scope={"building_id": building_id, "attempt": attempt},
                event="NUMERIC_DURABLE",
                details={
                    "residuals_sha256": residual_sha,
                    "summary_sha256": summary_sha,
                    "row_count": len(residual_rows),
                },
                fault_hook=fault_hook,
            )

            overlay_path = attempt_dir / "overlay.png"
            overlay_error_path = attempt_dir / "overlay_error.json"
            if (
                (overlay_path.exists() or overlay_path.is_symlink())
                and (overlay_error_path.exists() or overlay_error_path.is_symlink())
            ):
                raise CheckpointIntegrityError(
                    "attempt contains both overlay and overlay_error"
                )
            if not overlay_path.exists() and not overlay_error_path.exists():
                try:
                    if overlay is None:
                        raise CheckpointError("overlay was not provided")
                    produced = overlay() if callable(overlay) else overlay
                    png = bytes(produced)
                    if not png.startswith(PNG_SIGNATURE):
                        raise CheckpointIntegrityError(
                            "overlay producer returned non-PNG bytes"
                        )
                except Exception as exc:
                    issue = {
                        "schema": f"{SCHEMA_PREFIX}.overlay_issue.v1",
                        "created_utc": utc_now(),
                        "building_id": building_id,
                        "attempt": attempt,
                        "error_type": type(exc).__name__,
                        "message": str(exc)[:4000],
                        "numeric_evidence_preserved": True,
                    }
                    atomic_write_json(
                        overlay_error_path,
                        issue,
                        replace=False,
                        fault_hook=fault_hook,
                    )
                    self._append_event_locked(
                        journal,
                        identity=identity,
                        scope={"building_id": building_id, "attempt": attempt},
                        event="OVERLAY_FAILED",
                        details={
                            "error_type": type(exc).__name__,
                            "message": str(exc)[:4000],
                            "numeric_evidence_preserved": True,
                        },
                        fault_hook=fault_hook,
                    )
                else:
                    atomic_write_png(
                        overlay_path,
                        png,
                        replace=False,
                        fault_hook=fault_hook,
                    )
                    self._append_event_locked(
                        journal,
                        identity=identity,
                        scope={"building_id": building_id, "attempt": attempt},
                        event="OVERLAY_DURABLE",
                        details={"overlay_sha256": sha256_bytes(png)},
                        fault_hook=fault_hook,
                    )

            events_before_ready = self._verify_journal(journal, allow_missing=False)
            ready = self._append_event_locked(
                journal,
                identity=identity,
                scope={"building_id": building_id, "attempt": attempt},
                event="CHECKPOINT_READY",
                details={"prior_event_count": len(events_before_ready)},
                fault_hook=fault_hook,
            )
            artifacts = {
                "residuals_csv": _artifact_record(attempt_dir, residual_path),
                "summary_json": _artifact_record(attempt_dir, summary_path),
            }
            overlay_status: str
            if overlay_path.exists():
                artifacts["overlay_png"] = _artifact_record(
                    attempt_dir, overlay_path
                )
                overlay_status = "available"
            else:
                artifacts["overlay_error_json"] = _artifact_record(
                    attempt_dir, overlay_error_path
                )
                overlay_status = "failed_numeric_preserved"
            body: dict[str, Any] = {
                "schema": CHECKPOINT_SCHEMA,
                "created_utc": utc_now(),
                "status": "COMPLETED",
                "identity_key": identity.key,
                "bindings": identity.as_dict(),
                "building_id": building_id,
                "building_key": self._building_key(building_id),
                "attempt": attempt,
                "artifacts": artifacts,
                "overlay_status": overlay_status,
                "journal_head_sha256": ready["event_sha256"],
                "journal_event_count": ready["sequence"],
                "numeric_evidence_complete": True,
            }
            checkpoint_sha = sha256_bytes(_canonical_json_bytes(body))
            checkpoint_payload = dict(body)
            checkpoint_payload["checkpoint_sha256"] = checkpoint_sha
            atomic_write_json(
                checkpoint_path,
                checkpoint_payload,
                replace=False,
                fault_hook=fault_hook,
            )
            return self._verify_completed_locked(
                identity, building_id, attempt
            )

    def verify_completed(
        self,
        identity: CheckpointIdentity,
        building_id: str,
        attempt: str,
    ) -> Mapping[str, Any]:
        with self._mutation_lock(identity):
            return self._verify_completed_locked(
                identity,
                _require_building_id(building_id),
                _require_attempt(attempt),
            )

    def _verify_completed_locked(
        self,
        identity: CheckpointIdentity,
        building_id: str,
        attempt: str,
    ) -> Mapping[str, Any]:
        attempt_dir = self.attempt_dir(identity, building_id, attempt)
        checkpoint_path = attempt_dir / "checkpoint.json"
        payload = _read_json(
            checkpoint_path, require_canonical_bytes=True
        )
        if not isinstance(payload, Mapping):
            raise CheckpointIntegrityError("checkpoint receipt is not an object")
        if payload.get("schema") != CHECKPOINT_SCHEMA:
            raise CheckpointIntegrityError("checkpoint schema mismatch")
        if payload.get("status") != "COMPLETED":
            raise CheckpointIntegrityError("checkpoint status is not COMPLETED")
        if payload.get("identity_key") != identity.key:
            raise CheckpointBindingError("checkpoint identity key mismatch")
        if payload.get("bindings") != identity.as_dict():
            raise CheckpointBindingError("checkpoint binding hashes mismatch")
        if payload.get("building_id") != building_id:
            raise CheckpointBindingError("checkpoint building_id mismatch")
        if payload.get("building_key") != self._building_key(building_id):
            raise CheckpointBindingError("checkpoint building key mismatch")
        if payload.get("attempt") != attempt:
            raise CheckpointBindingError("checkpoint attempt mismatch")
        claimed = _require_sha256(
            "checkpoint_sha256", payload.get("checkpoint_sha256")
        )
        body = dict(payload)
        body.pop("checkpoint_sha256", None)
        if sha256_bytes(_canonical_json_bytes(body)) != claimed:
            raise CheckpointIntegrityError("checkpoint receipt was tampered")
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise CheckpointIntegrityError("checkpoint artifacts missing")
        required = {"residuals_csv", "summary_json"}
        if not required.issubset(artifacts):
            raise CheckpointIntegrityError("numeric checkpoint artifacts missing")
        overlay_keys = {"overlay_png", "overlay_error_json"}.intersection(artifacts)
        if len(overlay_keys) != 1:
            raise CheckpointIntegrityError(
                "checkpoint must bind exactly one overlay outcome"
            )
        for record in artifacts.values():
            if not isinstance(record, Mapping):
                raise CheckpointIntegrityError("artifact record is not an object")
            _verify_artifact(attempt_dir, record)
        events = self._verify_journal(
            self._journal_dir(identity, building_id, attempt),
            allow_missing=False,
        )
        if len(events) != payload.get("journal_event_count"):
            raise CheckpointIntegrityError("journal event count mismatch")
        if not events or events[-1].get("event_sha256") != payload.get(
            "journal_head_sha256"
        ):
            raise CheckpointIntegrityError("checkpoint journal head mismatch")
        if events[-1].get("event") != "CHECKPOINT_READY":
            raise CheckpointIntegrityError(
                "checkpoint journal does not end at CHECKPOINT_READY"
            )
        return payload

    def _error_journal_dir(self, identity: CheckpointIdentity) -> Path:
        return self._run_dir(identity) / "error_policy" / "journal"

    def _error_events_locked(
        self, identity: CheckpointIdentity
    ) -> list[Mapping[str, Any]]:
        return self._verify_journal(
            self._error_journal_dir(identity), allow_missing=True
        )

    @staticmethod
    def _error_building_groups(
        events: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for event in events:
            kind = event.get("event")
            details = event.get("details", {})
            if kind not in {"ERROR", "BUILDING_SUCCESS"}:
                continue
            building_id = details.get("building_id")
            if not isinstance(building_id, str):
                continue
            if not groups or groups[-1]["building_id"] != building_id:
                groups.append(
                    {
                        "building_id": building_id,
                        "error_types": set(),
                    }
                )
            if kind == "ERROR" and isinstance(details.get("error_type"), str):
                groups[-1]["error_types"].add(details["error_type"])
        return groups

    def mark_building_success(
        self,
        identity: CheckpointIdentity,
        *,
        building_id: str,
        fault_hook: FaultHook | None = None,
    ) -> None:
        """Record an error-free processed building so it resets consecutiveness."""

        building_id = _require_building_id(building_id)
        with self._mutation_lock(identity):
            events = self._error_events_locked(identity)
            groups = self._error_building_groups(events)
            if groups and groups[-1]["building_id"] == building_id:
                if groups[-1]["error_types"]:
                    raise CheckpointError(
                        "mark_building_success is only for an error-free building"
                    )
                return
            self._append_event_locked(
                self._error_journal_dir(identity),
                identity=identity,
                scope={"policy": ERROR_POLICY_SCHEMA},
                event="BUILDING_SUCCESS",
                details={"building_id": building_id},
                fault_hook=fault_hook,
            )

    def record_error(
        self,
        identity: CheckpointIdentity,
        *,
        building_id: str,
        attempt: str,
        error_type: str,
        message: str,
        fault_hook: FaultHook | None = None,
    ) -> ErrorDecision:
        """Record an error and enforce the two dispatch stop rules."""

        building_id = _require_building_id(building_id)
        attempt = _require_attempt(attempt)
        if not isinstance(error_type, str) or SAFE_ERROR_TYPE_RE.fullmatch(
            error_type
        ) is None:
            raise CheckpointBindingError(
                "error_type must match [A-Za-z0-9_.:-]{1,200}"
            )
        if not isinstance(message, str):
            raise CheckpointBindingError("error message must be a string")
        with self._mutation_lock(identity):
            journal = self._error_journal_dir(identity)
            self._append_event_locked(
                journal,
                identity=identity,
                scope={"policy": ERROR_POLICY_SCHEMA},
                event="ERROR",
                details={
                    "building_id": building_id,
                    "attempt": attempt,
                    "error_type": error_type,
                    "message": message[:4000],
                },
                fault_hook=fault_hook,
            )
            events = self._error_events_locked(identity)
            matching = [
                event
                for event in events
                if event.get("event") == "ERROR"
                and event.get("details", {}).get("building_id") == building_id
                and event.get("details", {}).get("error_type") == error_type
            ]
            same_count = len(matching)
            skip = same_count >= 3
            skip_already_recorded = any(
                event.get("event") == "BUILDING_SKIP"
                and event.get("details", {}).get("building_id") == building_id
                and event.get("details", {}).get("error_type") == error_type
                for event in events
            )
            if skip and not skip_already_recorded:
                self._append_event_locked(
                    journal,
                    identity=identity,
                    scope={"policy": ERROR_POLICY_SCHEMA},
                    event="BUILDING_SKIP",
                    details={
                        "building_id": building_id,
                        "attempt": attempt,
                        "error_type": error_type,
                        "same_error_count": same_count,
                        "rule": "same_error_three_times_for_building",
                    },
                    fault_hook=fault_hook,
                )
                events = self._error_events_locked(identity)

            groups = self._error_building_groups(events)
            consecutive = 0
            for group in reversed(groups):
                if error_type not in group["error_types"]:
                    break
                consecutive += 1
            stop_stage = consecutive >= 3
            blocked_path: Path | None = None
            if stop_stage:
                affected = [
                    group["building_id"] for group in groups[-consecutive:]
                ]
                stage_already_recorded = any(
                    event.get("event") == "STAGE_STOP"
                    and event.get("details", {}).get("error_type") == error_type
                    for event in events
                )
                stop_details = {
                    "error_type": error_type,
                    "consecutive_building_count": consecutive,
                    "building_ids": affected,
                    "rule": "same_error_type_across_three_consecutive_buildings",
                }
                if not stage_already_recorded:
                    self._append_event_locked(
                        journal,
                        identity=identity,
                        scope={"policy": ERROR_POLICY_SCHEMA},
                        event="STAGE_STOP",
                        details=stop_details,
                        fault_hook=fault_hook,
                    )
                blocked_path = self._write_blocked_receipt_locked(
                    identity,
                    reason=(
                        "same_error_type_across_three_consecutive_buildings"
                    ),
                    details=stop_details,
                    fault_hook=fault_hook,
                )
            return ErrorDecision(
                building_id=building_id,
                error_type=error_type,
                same_error_count_for_building=same_count,
                skip_building=skip,
                consecutive_building_count=consecutive,
                stop_stage=stop_stage,
                blocked_receipt=blocked_path,
            )

    def write_blocked_receipt(
        self,
        identity: CheckpointIdentity,
        *,
        reason: str,
        details: Mapping[str, Any],
        fault_hook: FaultHook | None = None,
    ) -> Path:
        with self._mutation_lock(identity):
            return self._write_blocked_receipt_locked(
                identity,
                reason=reason,
                details=details,
                fault_hook=fault_hook,
            )

    def _write_blocked_receipt_locked(
        self,
        identity: CheckpointIdentity,
        *,
        reason: str,
        details: Mapping[str, Any],
        fault_hook: FaultHook | None,
    ) -> Path:
        if not isinstance(reason, str) or not reason or len(reason) > 500:
            raise CheckpointBindingError("BLOCKED reason must be a non-empty string")
        stable = {
            "identity_key": identity.key,
            "reason": reason,
            "details": dict(details),
        }
        receipt_id = sha256_bytes(_canonical_json_bytes(stable))
        body = {
            "schema": BLOCKED_SCHEMA,
            "created_utc": utc_now(),
            "status": "BLOCKED",
            "learning_allowed": False,
            "identity_key": identity.key,
            "bindings": identity.as_dict(),
            "reason": reason,
            "details": dict(details),
            "receipt_id": receipt_id,
        }
        receipt_sha = sha256_bytes(_canonical_json_bytes(body))
        payload = dict(body)
        payload["receipt_sha256"] = receipt_sha
        blocked_dir = _ensure_secure_dir(
            self._run_dir(identity) / "blocked"
        )
        receipt_path = blocked_dir / f"{receipt_id}.json"
        if receipt_path.exists() or receipt_path.is_symlink():
            existing = self._verify_blocked_receipt(receipt_path, identity)
            if (
                existing.get("reason") != reason
                or existing.get("details") != dict(details)
            ):
                raise ImmutableCheckpointError("BLOCKED receipt ID collision")
        else:
            atomic_write_json(
                receipt_path,
                payload,
                replace=False,
                fault_hook=fault_hook,
            )
        pointer = {
            "schema": POINTER_SCHEMA,
            "kind": "blocked_receipt",
            "identity_key": identity.key,
            "receipt_id": receipt_id,
            "receipt_path": receipt_path.name,
            "receipt_sha256": sha256_file(receipt_path),
        }
        atomic_write_json(
            blocked_dir / "current.json",
            pointer,
            replace=True,
            fault_hook=fault_hook,
        )
        return receipt_path

    def _verify_blocked_receipt(
        self, path: Path, identity: CheckpointIdentity
    ) -> Mapping[str, Any]:
        payload = _read_json(path, require_canonical_bytes=True)
        if not isinstance(payload, Mapping) or payload.get("schema") != BLOCKED_SCHEMA:
            raise CheckpointIntegrityError("invalid BLOCKED receipt schema")
        if payload.get("status") != "BLOCKED" or payload.get(
            "learning_allowed"
        ) is not False:
            raise CheckpointIntegrityError("invalid BLOCKED receipt status")
        if payload.get("identity_key") != identity.key:
            raise CheckpointBindingError("BLOCKED receipt identity mismatch")
        claimed = _require_sha256(
            "receipt_sha256", payload.get("receipt_sha256")
        )
        body = dict(payload)
        body.pop("receipt_sha256", None)
        if sha256_bytes(_canonical_json_bytes(body)) != claimed:
            raise CheckpointIntegrityError("BLOCKED receipt was tampered")
        stable = {
            "identity_key": identity.key,
            "reason": payload.get("reason"),
            "details": payload.get("details"),
        }
        if sha256_bytes(_canonical_json_bytes(stable)) != payload.get(
            "receipt_id"
        ):
            raise CheckpointIntegrityError("BLOCKED receipt ID mismatch")
        return payload

    def resolve_current_blocked(
        self, identity: CheckpointIdentity
    ) -> Mapping[str, Any] | None:
        with self._mutation_lock(identity):
            blocked_dir = self._run_dir(identity) / "blocked"
            pointer_path = blocked_dir / "current.json"
            if not pointer_path.exists() and not pointer_path.is_symlink():
                return None
            pointer = _read_json(
                pointer_path, require_canonical_bytes=True
            )
            if (
                not isinstance(pointer, Mapping)
                or pointer.get("schema") != POINTER_SCHEMA
                or pointer.get("kind") != "blocked_receipt"
                or pointer.get("identity_key") != identity.key
            ):
                raise CheckpointIntegrityError("invalid BLOCKED current pointer")
            relative = pointer.get("receipt_path")
            if (
                not isinstance(relative, str)
                or Path(relative).name != relative
            ):
                raise CheckpointIntegrityError("invalid BLOCKED receipt path")
            receipt_path = blocked_dir / relative
            if sha256_file(receipt_path) != pointer.get("receipt_sha256"):
                raise CheckpointIntegrityError(
                    "BLOCKED pointer receipt hash mismatch"
                )
            return self._verify_blocked_receipt(receipt_path, identity)

    def assemble_bundle(
        self,
        identity: CheckpointIdentity,
        refs: Sequence[CheckpointRef],
        *,
        fault_hook: FaultHook | None = None,
    ) -> BundleResult:
        """Assemble verified checkpoints and atomically move ``current.json``."""

        if not refs:
            raise CheckpointBindingError("bundle requires at least one checkpoint")
        if len({(ref.building_id, ref.attempt) for ref in refs}) != len(refs):
            raise CheckpointBindingError("bundle checkpoint refs must be unique")
        with self._mutation_lock(identity):
            self.cleanup_stale_temps()
            verified: list[Mapping[str, Any]] = [
                self._verify_completed_locked(
                    identity, ref.building_id, ref.attempt
                )
                for ref in refs
            ]
            residual_fields: list[str] | None = None
            residual_rows: list[dict[str, str]] = []
            summary_rows: list[dict[str, Any]] = []
            overlay_payloads: list[tuple[str, bytes, str, str]] = []
            overlay_issues: list[dict[str, Any]] = []
            selected: list[dict[str, Any]] = []
            for ref, checkpoint in zip(refs, verified):
                attempt_dir = self.attempt_dir(
                    identity, ref.building_id, ref.attempt
                )
                artifacts = checkpoint["artifacts"]
                residual_path = _verify_artifact(
                    attempt_dir, artifacts["residuals_csv"]
                )
                text = _read_bytes(residual_path).decode("utf-8")
                reader = csv.DictReader(io.StringIO(text))
                current_fields = list(reader.fieldnames or [])
                if residual_fields is None:
                    residual_fields = current_fields
                elif residual_fields != current_fields:
                    raise CheckpointIntegrityError(
                        "checkpoint residual CSV headers differ"
                    )
                residual_rows.extend(dict(row) for row in reader)
                summary_path = _verify_artifact(
                    attempt_dir, artifacts["summary_json"]
                )
                summary = _read_json(summary_path)
                if not isinstance(summary, Mapping):
                    raise CheckpointIntegrityError(
                        "building summary is not an object"
                    )
                summary_rows.append(dict(summary))
                if "overlay_png" in artifacts:
                    overlay_path = _verify_artifact(
                        attempt_dir, artifacts["overlay_png"]
                    )
                    overlay_payloads.append(
                        (
                            self._building_key(ref.building_id)
                            + f"_{ref.attempt}.png",
                            _read_bytes(overlay_path),
                            ref.building_id,
                            ref.attempt,
                        )
                    )
                else:
                    issue_path = _verify_artifact(
                        attempt_dir, artifacts["overlay_error_json"]
                    )
                    issue = _read_json(issue_path)
                    if not isinstance(issue, Mapping):
                        raise CheckpointIntegrityError(
                            "overlay issue is not an object"
                        )
                    overlay_issues.append(dict(issue))
                selected.append(
                    {
                        "building_id": ref.building_id,
                        "attempt": ref.attempt,
                        "checkpoint_sha256": checkpoint["checkpoint_sha256"],
                    }
                )
            assert residual_fields is not None
            residual_data = csv_bytes(residual_rows, residual_fields)
            preferred = ["building_id", "attempt"]
            summary_fields = preferred + sorted(
                {
                    key
                    for row in summary_rows
                    for key in row
                    if key not in preferred
                }
            )
            summary_data = csv_bytes(summary_rows, summary_fields)
            issue_fields = [
                "building_id",
                "attempt",
                "error_type",
                "message",
                "numeric_evidence_preserved",
            ]
            issue_data = csv_bytes(overlay_issues, issue_fields)
            content_descriptor = {
                "identity_key": identity.key,
                "checkpoints": selected,
                "artifacts": {
                    "w1_align_residuals.csv": sha256_bytes(residual_data),
                    "w1_align_buildings.csv": sha256_bytes(summary_data),
                    "w1_align_overlay_issues.csv": sha256_bytes(issue_data),
                    "overlays": [
                        {
                            "filename": filename,
                            "sha256": sha256_bytes(data),
                            "building_id": building_id,
                            "attempt": attempt,
                        }
                        for filename, data, building_id, attempt in overlay_payloads
                    ],
                },
            }
            bundle_digest = sha256_bytes(
                _canonical_json_bytes(content_descriptor)
            )
            bundle_id = f"bundle-{bundle_digest}"
            bundle_root = _ensure_secure_dir(
                self.root / "bundles" / identity.key
            )
            final_dir = bundle_root / bundle_id
            if final_dir.exists() or final_dir.is_symlink():
                manifest = self._verify_bundle_locked(
                    identity, final_dir, bundle_id
                )
            else:
                staging = bundle_root / (
                    f".bundle-tmp-{os.getpid()}-{uuid.uuid4().hex}"
                )
                _ensure_secure_dir(staging)
                try:
                    atomic_write_bytes(
                        staging / "w1_align_residuals.csv",
                        residual_data,
                        replace=False,
                        fault_hook=fault_hook,
                    )
                    atomic_write_bytes(
                        staging / "w1_align_buildings.csv",
                        summary_data,
                        replace=False,
                        fault_hook=fault_hook,
                    )
                    atomic_write_bytes(
                        staging / "w1_align_overlay_issues.csv",
                        issue_data,
                        replace=False,
                        fault_hook=fault_hook,
                    )
                    overlays_dir = _ensure_secure_dir(staging / "overlays")
                    for filename, data, _building_id, _attempt in overlay_payloads:
                        atomic_write_png(
                            overlays_dir / filename,
                            data,
                            replace=False,
                            fault_hook=fault_hook,
                        )
                    artifact_records = {
                        "residuals_csv": _artifact_record(
                            staging, staging / "w1_align_residuals.csv"
                        ),
                        "buildings_csv": _artifact_record(
                            staging, staging / "w1_align_buildings.csv"
                        ),
                        "overlay_issues_csv": _artifact_record(
                            staging, staging / "w1_align_overlay_issues.csv"
                        ),
                        "overlays": [
                            {
                                "building_id": building_id,
                                "attempt": attempt,
                                **_artifact_record(
                                    staging, overlays_dir / filename
                                ),
                            }
                            for filename, _data, building_id, attempt in (
                                overlay_payloads
                            )
                        ],
                    }
                    manifest = {
                        "schema": BUNDLE_SCHEMA,
                        "created_utc": utc_now(),
                        "bundle_id": bundle_id,
                        "bundle_content_sha256": bundle_digest,
                        "identity_key": identity.key,
                        "bindings": identity.as_dict(),
                        "checkpoints": selected,
                        "artifacts": artifact_records,
                        "checkpoint_count": len(selected),
                        "overlay_available_count": len(overlay_payloads),
                        "overlay_failure_count": len(overlay_issues),
                        "numeric_evidence_preserved_for_overlay_failures": True,
                    }
                    atomic_write_json(
                        staging / "bundle_manifest.json",
                        manifest,
                        replace=False,
                        fault_hook=fault_hook,
                    )
                    _fsync_tree(staging)
                    self._publish_directory(
                        staging,
                        final_dir,
                        fault_hook=fault_hook,
                    )
                except BaseException:
                    if staging.exists() and not staging.is_symlink():
                        _remove_temp_tree(staging)
                    raise
                manifest = self._verify_bundle_locked(
                    identity, final_dir, bundle_id
                )

            pointer_path = bundle_root / "current.json"
            previous_bundle_id: str | None = None
            if pointer_path.exists() or pointer_path.is_symlink():
                previous_pointer = self._verify_bundle_pointer_locked(
                    identity, pointer_path
                )
                if previous_pointer.get("bundle_id") != bundle_id:
                    previous_bundle_id = str(previous_pointer["bundle_id"])
                else:
                    previous_bundle_id = previous_pointer.get(
                        "previous_bundle_id"
                    )
            manifest_path = final_dir / "bundle_manifest.json"
            pointer = {
                "schema": POINTER_SCHEMA,
                "kind": "alignment_bundle",
                "identity_key": identity.key,
                "bundle_id": bundle_id,
                "bundle_path": bundle_id,
                "manifest_sha256": sha256_file(manifest_path),
                "previous_bundle_id": previous_bundle_id,
            }
            atomic_write_json(
                pointer_path,
                pointer,
                replace=True,
                fault_hook=fault_hook,
            )
            self._verify_bundle_pointer_locked(identity, pointer_path)
            return BundleResult(
                bundle_id=bundle_id,
                bundle_dir=final_dir,
                manifest=manifest,
                current_pointer=pointer_path,
            )

    def _publish_directory(
        self,
        staging: Path,
        destination: Path,
        *,
        fault_hook: FaultHook | None,
    ) -> None:
        if staging.parent != destination.parent:
            raise PathSecurityError("bundle staging must share destination parent")
        parent = _ensure_secure_dir(destination.parent)
        parent_fd = _directory_fd(parent)
        try:
            existing = _leaf_info(parent_fd, destination.name)
            if existing is not None:
                raise FileExistsError(destination)
            os.replace(
                staging.name,
                destination.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            if fault_hook is not None:
                fault_hook("after_bundle_replace_before_dir_fsync", destination)
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)

    def _verify_bundle_locked(
        self,
        identity: CheckpointIdentity,
        bundle_dir: Path,
        bundle_id: str,
    ) -> Mapping[str, Any]:
        _assert_no_symlink_path(bundle_dir, require_leaf=True)
        manifest = _read_json(
            bundle_dir / "bundle_manifest.json",
            require_canonical_bytes=True,
        )
        if (
            not isinstance(manifest, Mapping)
            or manifest.get("schema") != BUNDLE_SCHEMA
            or manifest.get("bundle_id") != bundle_id
            or manifest.get("identity_key") != identity.key
            or manifest.get("bindings") != identity.as_dict()
        ):
            raise CheckpointIntegrityError("bundle manifest binding mismatch")
        if bundle_id != f"bundle-{manifest.get('bundle_content_sha256')}":
            raise CheckpointIntegrityError("bundle content-address mismatch")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise CheckpointIntegrityError("bundle artifacts missing")
        for key in ("residuals_csv", "buildings_csv", "overlay_issues_csv"):
            record = artifacts.get(key)
            if not isinstance(record, Mapping):
                raise CheckpointIntegrityError(f"bundle {key} record missing")
            _verify_artifact(bundle_dir, record)
        overlays = artifacts.get("overlays")
        if not isinstance(overlays, list):
            raise CheckpointIntegrityError("bundle overlays list missing")
        for record in overlays:
            if not isinstance(record, Mapping):
                raise CheckpointIntegrityError("bundle overlay record invalid")
            _verify_artifact(bundle_dir, record)
        for selected in manifest.get("checkpoints", []):
            if not isinstance(selected, Mapping):
                raise CheckpointIntegrityError("bundle checkpoint ref invalid")
            checkpoint = self._verify_completed_locked(
                identity,
                _require_building_id(selected.get("building_id")),
                _require_attempt(selected.get("attempt")),
            )
            if checkpoint.get("checkpoint_sha256") != selected.get(
                "checkpoint_sha256"
            ):
                raise CheckpointIntegrityError(
                    "bundle source checkpoint SHA mismatch"
                )
        descriptor = {
            "identity_key": identity.key,
            "checkpoints": manifest.get("checkpoints"),
            "artifacts": {
                "w1_align_residuals.csv": artifacts["residuals_csv"]["sha256"],
                "w1_align_buildings.csv": artifacts["buildings_csv"]["sha256"],
                "w1_align_overlay_issues.csv": artifacts[
                    "overlay_issues_csv"
                ]["sha256"],
                "overlays": [
                    {
                        "filename": Path(record["path"]).name,
                        "sha256": record["sha256"],
                        "building_id": record["building_id"],
                        "attempt": record["attempt"],
                    }
                    for record in overlays
                ],
            },
        }
        if sha256_bytes(_canonical_json_bytes(descriptor)) != manifest.get(
            "bundle_content_sha256"
        ):
            raise CheckpointIntegrityError(
                "bundle content descriptor SHA mismatch"
            )
        return manifest

    def _verify_bundle_pointer_locked(
        self,
        identity: CheckpointIdentity,
        pointer_path: Path,
    ) -> Mapping[str, Any]:
        pointer = _read_json(
            pointer_path, require_canonical_bytes=True
        )
        if (
            not isinstance(pointer, Mapping)
            or pointer.get("schema") != POINTER_SCHEMA
            or pointer.get("kind") != "alignment_bundle"
            or pointer.get("identity_key") != identity.key
        ):
            raise CheckpointIntegrityError("invalid alignment bundle pointer")
        bundle_id = pointer.get("bundle_id")
        relative = pointer.get("bundle_path")
        if (
            not isinstance(bundle_id, str)
            or relative != bundle_id
            or Path(relative).name != relative
        ):
            raise CheckpointIntegrityError("invalid bundle pointer path")
        bundle_dir = pointer_path.parent / relative
        manifest_path = bundle_dir / "bundle_manifest.json"
        if sha256_file(manifest_path) != pointer.get("manifest_sha256"):
            raise CheckpointIntegrityError("bundle pointer manifest hash mismatch")
        self._verify_bundle_locked(identity, bundle_dir, bundle_id)
        return pointer

    def resolve_current_bundle(
        self, identity: CheckpointIdentity
    ) -> BundleResult | None:
        with self._mutation_lock(identity):
            pointer_path = (
                self.root / "bundles" / identity.key / "current.json"
            )
            if not pointer_path.exists() and not pointer_path.is_symlink():
                return None
            pointer = self._verify_bundle_pointer_locked(identity, pointer_path)
            bundle_dir = pointer_path.parent / str(pointer["bundle_path"])
            manifest = self._verify_bundle_locked(
                identity, bundle_dir, str(pointer["bundle_id"])
            )
            return BundleResult(
                bundle_id=str(pointer["bundle_id"]),
                bundle_dir=bundle_dir,
                manifest=manifest,
                current_pointer=pointer_path,
            )


def _remove_temp_tree(path: Path) -> None:
    """Remove only a hidden helper staging tree, never a published bundle."""

    _assert_no_symlink_path(path, require_leaf=True)
    if not path.name.startswith(".bundle-tmp-"):
        raise PathSecurityError(f"refusing to remove non-temp tree: {path}")
    for directory, dirnames, filenames in os.walk(
        path, topdown=False, followlinks=False
    ):
        directory_path = Path(directory)
        for filename in filenames:
            candidate = directory_path / filename
            info = os.lstat(candidate)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise PathSecurityError(
                    f"unexpected staging artifact type: {candidate}"
                )
            os.unlink(candidate)
        for dirname in dirnames:
            candidate = directory_path / dirname
            info = os.lstat(candidate)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise PathSecurityError(
                    f"unexpected staging directory type: {candidate}"
                )
            os.rmdir(candidate)
    os.rmdir(path)
    _fsync_directory(path.parent)


def _fsync_tree(root: Path) -> None:
    _assert_no_symlink_path(root, require_leaf=True)
    directories: list[Path] = []
    for directory, dirnames, filenames in os.walk(
        root, topdown=False, followlinks=False
    ):
        directory_path = Path(directory)
        directories.append(directory_path)
        for dirname in dirnames:
            info = os.lstat(directory_path / dirname)
            if stat.S_ISLNK(info.st_mode):
                raise PathSecurityError("symlink in bundle staging tree")
        for filename in filenames:
            path = directory_path / filename
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise PathSecurityError(
                    f"unexpected bundle artifact type: {path}"
                )
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(path, flags)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    for directory in directories:
        _fsync_directory(directory)


__all__ = [
    "ALLOWED_ATTEMPTS",
    "AlignmentCheckpointStore",
    "BundleResult",
    "CheckpointBindingError",
    "CheckpointError",
    "CheckpointIdentity",
    "CheckpointIntegrityError",
    "CheckpointRef",
    "ErrorDecision",
    "ImmutableCheckpointError",
    "PathSecurityError",
    "ResumeState",
    "atomic_write_bytes",
    "atomic_write_csv",
    "atomic_write_json",
    "atomic_write_png",
    "canonical_hash_manifest",
    "csv_bytes",
    "sha256_bytes",
    "sha256_file",
]

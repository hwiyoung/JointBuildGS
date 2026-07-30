#!/usr/bin/env python3
"""Read-only, pinned-container verification of one completed P1W checkpoint."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping, Sequence

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.stage2.checkpoint import load_training_checkpoint


SCHEMA = "jointbuildgs.pilot_1wave.checkpoint_verification.v1"
CHECKPOINT_STEP = 20_000
STEP_SEMANTICS = "completed_optimizer_updates"
LOSS_CURSOR_SCHEMA = "jointbuildgs.stage2.loss_csv_cursor.v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RESULT_PREFIX = "P1W_CHECKPOINT_VERIFY_JSON="


class VerificationError(RuntimeError):
    """The checkpoint is not the exact, bound P1W 20k full state."""


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def require_container() -> None:
    if not Path("/.dockerenv").is_file():
        raise VerificationError("checkpoint verifier must run inside the pinned container")


def _normalize_binding(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {
        "training_config",
        "effective_training_config",
        "output_path",
    }:
        raise VerificationError("expected binding must contain exactly three locked keys")
    result: dict[str, str] = {}
    for key, digest in value.items():
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise VerificationError(f"expected binding digest is invalid: {key}")
        result[str(key)] = digest
    return result


def verify_checkpoint(
    *,
    checkpoint: Path,
    expected_sha256: str,
    expected_binding_sha256: Mapping[str, str],
    expected_loss_csv_paths: Sequence[str],
    loader: Callable[..., Any] = load_training_checkpoint,
) -> dict[str, Any]:
    if checkpoint.is_symlink():
        raise VerificationError(f"checkpoint must not be a symlink: {checkpoint}")
    checkpoint = checkpoint.resolve()
    if not checkpoint.is_file():
        raise VerificationError(f"checkpoint must be a regular non-symlink file: {checkpoint}")
    if checkpoint.name != "step_020000.pt":
        raise VerificationError(f"checkpoint filename is not exact 20k: {checkpoint.name}")
    if _SHA256_RE.fullmatch(expected_sha256) is None:
        raise VerificationError("expected checkpoint SHA256 is malformed")
    binding = _normalize_binding(expected_binding_sha256)
    loss_paths = tuple(str(value) for value in expected_loss_csv_paths)
    if not loss_paths or len(loss_paths) != len(set(loss_paths)) or list(loss_paths) != sorted(loss_paths):
        raise VerificationError("expected loss CSV paths must be nonempty, unique, and sorted")

    loaded = loader(
        checkpoint,
        expected_binding_sha256=binding,
        map_location="cpu",
    )
    if loaded.sha256 != expected_sha256:
        raise VerificationError(
            f"loaded checkpoint SHA mismatch: {loaded.sha256} != {expected_sha256}"
        )
    if int(loaded.completed_steps) != CHECKPOINT_STEP:
        raise VerificationError(
            f"checkpoint payload is not exact 20k: {loaded.completed_steps}"
        )
    payload = loaded.payload
    if payload.get("step_semantics") != STEP_SEMANTICS:
        raise VerificationError("checkpoint payload step semantics changed")
    if payload.get("binding_sha256") != binding:
        raise VerificationError("checkpoint payload binding is not exact")
    learning_runs_started = int(payload.get("learning_runs_started", 0) or 0)
    if learning_runs_started < 1:
        raise VerificationError("checkpoint payload has no learning run")
    cursor = payload.get("loss_log_cursor")
    if not isinstance(cursor, Mapping):
        raise VerificationError("checkpoint loss cursor is not a mapping")
    if cursor.get("schema") != LOSS_CURSOR_SCHEMA:
        raise VerificationError("checkpoint loss cursor schema changed")
    if int(cursor.get("completed_steps", -1)) != CHECKPOINT_STEP:
        raise VerificationError("checkpoint loss cursor is not exact 20k")
    files = cursor.get("files")
    if not isinstance(files, Mapping) or set(files) != set(loss_paths):
        raise VerificationError("checkpoint loss cursor paths changed")

    verifier_path = Path(__file__).resolve()
    return {
        "schema": SCHEMA,
        "state": "verified",
        "checkpoint_path": str(checkpoint),
        "checkpoint_sha256": loaded.sha256,
        "completed_steps": CHECKPOINT_STEP,
        "step_semantics": STEP_SEMANTICS,
        "binding_sha256": binding,
        "loss_csv_paths": list(loss_paths),
        "learning_runs_started": learning_runs_started,
        "verifier_source_path": str(verifier_path),
        "verifier_source_sha256": sha256_file(verifier_path),
        "read_only": True,
        "gpu_required": False,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--checkpoint", type=Path, required=True)
    result.add_argument("--expected-sha256", required=True)
    result.add_argument("--expected-binding-json", required=True)
    result.add_argument("--expected-loss-csv-path", action="append", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    require_container()
    args = parser().parse_args(argv)
    try:
        binding = json.loads(args.expected_binding_json)
    except json.JSONDecodeError as exc:
        raise VerificationError(f"expected binding JSON is invalid: {exc}") from exc
    result = verify_checkpoint(
        checkpoint=args.checkpoint,
        expected_sha256=args.expected_sha256,
        expected_binding_sha256=binding,
        expected_loss_csv_paths=args.expected_loss_csv_path,
    )
    print(
        RESULT_PREFIX
        + json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

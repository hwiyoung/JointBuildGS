"""Full-state, atomic checkpoints for resumable Stage 2 training.

The legacy checkpoints written by :mod:`src.stage2.train` are inference
snapshots.  They deliberately do not contain enough state to resume an Adam +
densification run exactly.  This module provides the stricter format needed by
the quality-axis pilot without changing the legacy trainer yet.

``completed_steps`` always means *completed optimizer updates*.  Consequently,
``step_005000.pt`` is written only after update 5,000 has completed; the next
update after restoring it is update 5,001.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
import random
import re
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .densification import (
    ElongationFilterStrategy,
    SeedProtectElongationFilterStrategy,
    SeedProtectStrategy,
    build_optimizers,
)
from .model import GaussianModel2D


CHECKPOINT_FORMAT = "jointbuildgs.stage2.full_state"
CHECKPOINT_VERSION = 1
STEP_SEMANTICS = "completed_optimizer_updates"
PUBLISHED_FILE_MODE = 0o644
_STEP_RE = re.compile(r"^step_(\d{6,})\.pt$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CheckpointError(RuntimeError):
    """Base class for checkpoint validation/restoration failures."""


class CheckpointIntegrityError(CheckpointError):
    """The bytes, sidecar, or checkpoint schema are invalid."""


class CheckpointBindingError(CheckpointError):
    """The checkpoint was produced from different bound inputs/configs."""


class CheckpointReconstructionError(CheckpointError):
    """The saved dynamic training objects cannot be reconstructed safely."""


@dataclass(frozen=True)
class SavedCheckpoint:
    path: Path
    sidecar_path: Path
    sha256: str
    completed_steps: int


@dataclass(frozen=True)
class LoadedCheckpoint:
    path: Path
    sidecar_path: Path
    sha256: str
    payload: dict[str, Any]

    @property
    def completed_steps(self) -> int:
        return int(self.payload["completed_steps"])


@dataclass(frozen=True)
class SkippedCheckpoint:
    path: Path
    error_type: str
    reason: str


@dataclass(frozen=True)
class CheckpointDiscovery:
    """Newest valid checkpoint and the newer candidates rejected before it."""

    selected: LoadedCheckpoint | None
    skipped: tuple[SkippedCheckpoint, ...]


@dataclass
class RestoredTrainingState:
    """Objects and cursors required to continue with the next optimizer update."""

    checkpoint: LoadedCheckpoint
    model: GaussianModel2D
    optimizers: dict[str, torch.optim.Optimizer]
    strategy: Any
    strategy_state: Any
    grouping_state: Any
    completed_steps: int
    loss_log_cursor: Any
    learning_runs_started: int


def checkpoint_path(checkpoint_dir: str | os.PathLike[str], completed_steps: int) -> Path:
    """Return the canonical path for an exact count of completed updates."""

    steps = _require_nonnegative_int("completed_steps", completed_steps)
    return Path(checkpoint_dir) / f"step_{steps:06d}.pt"


def checkpoint_sidecar_path(path: str | os.PathLike[str]) -> Path:
    """Return the SHA-256 sidecar path (``<checkpoint>.sha256``)."""

    return Path(f"{Path(path)}.sha256")


def capture_rng_state() -> dict[str, Any]:
    """Capture Python, NumPy, Torch CPU, and every visible CUDA RNG stream."""

    cuda_states: list[torch.Tensor] = []
    if torch.cuda.is_available():
        try:
            cuda_states = [state.cpu() for state in torch.cuda.get_rng_state_all()]
        except (RuntimeError, AssertionError) as exc:
            raise CheckpointError(f"failed to capture CUDA RNG state: {exc}") from exc
    return {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch_cpu": torch.get_rng_state().cpu(),
        "torch_cuda": cuda_states,
        "torch_cuda_device_count": len(cuda_states),
    }


def restore_rng_state(state: Mapping[str, Any], *, strict_cuda: bool = True) -> None:
    """Restore RNG streams, rejecting CUDA topology drift in strict mode."""

    required = {"python", "numpy", "torch_cpu", "torch_cuda", "torch_cuda_device_count"}
    missing = sorted(required - set(state))
    if missing:
        raise CheckpointIntegrityError(f"RNG state is missing keys: {missing}")

    saved_cuda = list(state["torch_cuda"])
    try:
        saved_count = _require_nonnegative_int(
            "torch_cuda_device_count", state["torch_cuda_device_count"]
        )
    except ValueError as exc:
        raise CheckpointIntegrityError(str(exc)) from exc
    if saved_count != len(saved_cuda):
        raise CheckpointIntegrityError(
            "CUDA RNG metadata count does not match the saved state list"
        )
    available_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
    if saved_cuda and strict_cuda and available_count != saved_count:
        raise CheckpointReconstructionError(
            "CUDA RNG topology mismatch: "
            f"checkpoint={saved_count}, visible_now={available_count}"
        )

    # Validate topology and tensors before changing any live RNG stream.
    cpu_rng = _as_cpu_byte_tensor(state["torch_cpu"], "torch_cpu")
    cuda_rngs = [
        _as_cpu_byte_tensor(rng, f"torch_cuda[{device_index}]")
        for device_index, rng in enumerate(saved_cuda)
    ]
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(cpu_rng)
    for device_index, rng in enumerate(saved_cuda[:available_count]):
        torch.cuda.set_rng_state(
            cuda_rngs[device_index],
            device=device_index,
        )


def save_training_checkpoint(
    checkpoint_dir: str | os.PathLike[str],
    *,
    completed_steps: int,
    model: GaussianModel2D,
    optimizers: Mapping[str, torch.optim.Optimizer],
    strategy: Any,
    strategy_state: Any,
    grouping_state: Any,
    binding_sha256: Mapping[str, str],
    loss_log_cursor: Any,
    learning_runs_started: int,
) -> SavedCheckpoint:
    """Atomically save every state required for an exact training continuation.

    The checkpoint and its SHA-256 sidecar are each written through a temporary
    file, ``fsync``-ed, and installed with :func:`os.replace`.  A crash between
    the two replaces can leave a digest mismatch, which discovery treats as an
    invalid newest candidate and falls back from safely.
    """

    steps = _require_nonnegative_int("completed_steps", completed_steps)
    runs_started = _require_nonnegative_int(
        "learning_runs_started", learning_runs_started
    )
    binding = _normalize_binding_sha256(binding_sha256)
    destination = checkpoint_path(checkpoint_dir, steps)
    destination.parent.mkdir(parents=True, exist_ok=True)

    model_state = model.state_dict()
    tensor_shapes = {
        name: list(tensor.shape)
        for name, tensor in model_state.items()
        if isinstance(tensor, torch.Tensor)
    }
    tensor_dtypes = {
        name: str(tensor.dtype)
        for name, tensor in model_state.items()
        if isinstance(tensor, torch.Tensor)
    }
    surface_seed_mask = getattr(model, "surface_seed_mask", None)
    if surface_seed_mask is not None:
        surface_seed_mask = surface_seed_mask.detach().to(device="cpu", dtype=torch.bool)

    optimizer_payload: dict[str, dict[str, Any]] = {}
    for name, optimizer in sorted(optimizers.items()):
        if not isinstance(name, str) or not name:
            raise ValueError("optimizer names must be non-empty strings")
        optimizer_payload[name] = {
            "kind": _qualified_kind(optimizer),
            "state_dict": optimizer.state_dict(),
        }

    payload: dict[str, Any] = {
        "checkpoint_format": CHECKPOINT_FORMAT,
        "checkpoint_version": CHECKPOINT_VERSION,
        "step_semantics": STEP_SEMANTICS,
        "completed_steps": steps,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": {
            "kind": _qualified_kind(model),
            "state_dict": model_state,
            "tensor_shapes": tensor_shapes,
            "tensor_dtypes": tensor_dtypes,
            "sh_degree": int(model.sh_degree),
            "max_sh_degree": int(model.max_sh_degree),
            "active_sh_degree": int(model.active_sh_degree),
            "surface_seed_mask": surface_seed_mask,
        },
        "optimizers": optimizer_payload,
        "strategy": {
            "kind": None if strategy is None else _qualified_kind(strategy),
            "config": _capture_strategy_config(strategy),
            "state": strategy_state,
        },
        "grouping_state": grouping_state,
        "rng_state": capture_rng_state(),
        "binding_sha256": binding,
        "loss_log_cursor": loss_log_cursor,
        "learning_runs_started": runs_started,
    }
    _validate_payload(payload)

    sidecar = checkpoint_sidecar_path(destination)
    checkpoint_tmp: Path | None = None
    sidecar_tmp: Path | None = None
    try:
        checkpoint_tmp = _new_temp_path(destination.parent, destination.name)
        with checkpoint_tmp.open("wb") as stream:
            torch.save(payload, stream)
            os.fchmod(stream.fileno(), PUBLISHED_FILE_MODE)
            stream.flush()
            os.fsync(stream.fileno())
        digest = _sha256_file(checkpoint_tmp)

        sidecar_tmp = _new_temp_path(destination.parent, sidecar.name)
        with sidecar_tmp.open("w", encoding="ascii", newline="\n") as stream:
            stream.write(f"{digest}  {destination.name}\n")
            os.fchmod(stream.fileno(), PUBLISHED_FILE_MODE)
            stream.flush()
            os.fsync(stream.fileno())

        os.replace(checkpoint_tmp, destination)
        checkpoint_tmp = None
        os.replace(sidecar_tmp, sidecar)
        sidecar_tmp = None
        _fsync_directory(destination.parent)
    finally:
        for temporary in (checkpoint_tmp, sidecar_tmp):
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass

    return SavedCheckpoint(
        path=destination,
        sidecar_path=sidecar,
        sha256=digest,
        completed_steps=steps,
    )


def load_training_checkpoint(
    path: str | os.PathLike[str],
    *,
    expected_binding_sha256: Mapping[str, str] | None = None,
    map_location: str | torch.device | Callable | Mapping | None = "cpu",
) -> LoadedCheckpoint:
    """Load one explicitly selected checkpoint.

    An expected binding mismatch is always a hard failure here.  Automatic
    fallback belongs only in :func:`discover_latest_checkpoint`.
    """

    checkpoint = Path(path)
    sidecar = checkpoint_sidecar_path(checkpoint)
    expected_digest = _read_sidecar(sidecar, checkpoint.name)
    try:
        with checkpoint.open("rb") as stream:
            actual_digest = _sha256_stream(stream)
            if actual_digest != expected_digest:
                raise CheckpointIntegrityError(
                    f"SHA-256 mismatch for {checkpoint}: "
                    f"sidecar={expected_digest}, actual={actual_digest}"
                )
            stream.seek(0)
            try:
                payload = torch.load(
                    stream, map_location=map_location, weights_only=False
                )
            except Exception as exc:  # torch emits several backend-specific errors
                raise CheckpointIntegrityError(
                    f"cannot deserialize checkpoint {checkpoint}: {type(exc).__name__}: {exc}"
                ) from exc
    except FileNotFoundError as exc:
        raise CheckpointIntegrityError(f"checkpoint does not exist: {checkpoint}") from exc

    _validate_payload(payload)
    match = _STEP_RE.match(checkpoint.name)
    if match and int(match.group(1)) != int(payload["completed_steps"]):
        raise CheckpointIntegrityError(
            f"filename/payload step mismatch for {checkpoint.name}: "
            f"filename={int(match.group(1))}, payload={payload['completed_steps']}"
        )

    if expected_binding_sha256 is not None:
        expected_binding = _normalize_binding_sha256(expected_binding_sha256)
        actual_binding = _normalize_binding_sha256(payload["binding_sha256"])
        if actual_binding != expected_binding:
            raise CheckpointBindingError(
                _binding_mismatch_message(checkpoint, expected_binding, actual_binding)
            )

    return LoadedCheckpoint(
        path=checkpoint,
        sidecar_path=sidecar,
        sha256=actual_digest,
        payload=payload,
    )


def discover_latest_checkpoint(
    checkpoint_dir: str | os.PathLike[str],
    *,
    expected_binding_sha256: Mapping[str, str],
    map_location: str | torch.device | Callable | Mapping | None = "cpu",
) -> CheckpointDiscovery:
    """Select the newest valid, binding-matched checkpoint.

    Corrupt and binding-mismatched newer candidates are reported in ``skipped``
    and do not block selection of a previous valid checkpoint.
    """

    directory = Path(checkpoint_dir)
    candidates: list[tuple[int, Path]] = []
    if directory.is_dir():
        for candidate in directory.iterdir():
            match = _STEP_RE.match(candidate.name)
            if candidate.is_file() and match:
                candidates.append((int(match.group(1)), candidate))
    candidates.sort(key=lambda item: item[0], reverse=True)

    skipped: list[SkippedCheckpoint] = []
    for _, candidate in candidates:
        try:
            selected = load_training_checkpoint(
                candidate,
                expected_binding_sha256=expected_binding_sha256,
                map_location=map_location,
            )
            return CheckpointDiscovery(selected=selected, skipped=tuple(skipped))
        except CheckpointError as exc:
            skipped.append(
                SkippedCheckpoint(
                    path=candidate,
                    error_type=type(exc).__name__,
                    reason=str(exc),
                )
            )
    return CheckpointDiscovery(selected=None, skipped=tuple(skipped))


def restore_training_checkpoint(
    checkpoint: LoadedCheckpoint | str | os.PathLike[str],
    *,
    expected_binding_sha256: Mapping[str, str],
    device: str | torch.device = "cpu",
    optimizer_builder: Callable[[GaussianModel2D], Mapping[str, torch.optim.Optimizer]] = build_optimizers,
    restore_rng: bool = True,
    strict_cuda_rng: bool = True,
) -> RestoredTrainingState:
    """Reconstruct a dynamic Gaussian model, optimizers, strategy, and cursors."""

    expected_binding = _normalize_binding_sha256(expected_binding_sha256)
    if isinstance(checkpoint, LoadedCheckpoint):
        # Discovery normally maps tensors to CPU.  Reload the selected inode for
        # the requested training device so strategy/grouping tensors are not
        # accidentally left on CPU when the model resumes on CUDA.  This also
        # rechecks integrity and bindings after selection.
        loaded = load_training_checkpoint(
            checkpoint.path,
            expected_binding_sha256=expected_binding,
            map_location=device,
        )
    else:
        loaded = load_training_checkpoint(
            checkpoint,
            expected_binding_sha256=expected_binding,
            map_location=device,
        )

    payload = loaded.payload
    model = reconstruct_gaussian_model(payload["model"], device=device)
    built = dict(optimizer_builder(model))
    saved_optimizers = payload["optimizers"]
    if set(built) != set(saved_optimizers):
        raise CheckpointReconstructionError(
            "optimizer key mismatch: "
            f"builder={sorted(built)}, checkpoint={sorted(saved_optimizers)}"
        )
    for name, optimizer in built.items():
        saved_kind = saved_optimizers[name]["kind"]
        actual_kind = _qualified_kind(optimizer)
        if saved_kind != actual_kind:
            raise CheckpointReconstructionError(
                f"optimizer kind mismatch for {name}: "
                f"checkpoint={saved_kind}, builder={actual_kind}"
            )
        try:
            optimizer.load_state_dict(saved_optimizers[name]["state_dict"])
        except Exception as exc:
            raise CheckpointReconstructionError(
                f"cannot restore optimizer {name}: {type(exc).__name__}: {exc}"
            ) from exc

    strategy = reconstruct_strategy(payload["strategy"])
    restored = RestoredTrainingState(
        checkpoint=loaded,
        model=model,
        optimizers=built,
        strategy=strategy,
        strategy_state=payload["strategy"]["state"],
        grouping_state=payload["grouping_state"],
        completed_steps=int(payload["completed_steps"]),
        loss_log_cursor=payload["loss_log_cursor"],
        learning_runs_started=int(payload["learning_runs_started"]),
    )
    # Restore last in case a future model/optimizer/strategy builder consumes RNG.
    if restore_rng:
        restore_rng_state(payload["rng_state"], strict_cuda=strict_cuda_rng)
    return restored


def reconstruct_gaussian_model(
    model_payload: Mapping[str, Any], *, device: str | torch.device = "cpu"
) -> GaussianModel2D:
    """Rebuild a densified/pruned :class:`GaussianModel2D` from saved shapes.

    Calling the public constructor would rerun its k-NN scale initializer over
    every saved Gaussian, only to overwrite the result immediately.  A pilot
    scene can contain millions of post-densification rows, so the current model
    layout is allocated directly and then populated with ``load_state_dict``.
    """

    expected_kind = f"{GaussianModel2D.__module__}.{GaussianModel2D.__qualname__}"
    if model_payload.get("kind") != expected_kind:
        raise CheckpointReconstructionError(
            f"unsupported model kind: {model_payload.get('kind')!r}"
        )
    state = model_payload.get("state_dict")
    parameter_names = (
        "means",
        "quats",
        "log_scales",
        "opacities_raw",
        "sh0",
        "shN",
        "sem_logits",
    )
    if not isinstance(state, Mapping) or set(state) != set(parameter_names):
        raise CheckpointIntegrityError(
            "model state_dict does not match the current GaussianModel2D layout"
        )
    means = state["means"]
    if not isinstance(means, torch.Tensor) or means.ndim != 2 or means.shape[1] != 3:
        raise CheckpointIntegrityError("model means must have shape (N, 3)")
    count = int(means.shape[0])
    if count <= 0:
        raise CheckpointReconstructionError("cannot reconstruct an empty Gaussian model")

    try:
        sh_degree = _require_nonnegative_int(
            "model.sh_degree", model_payload["sh_degree"]
        )
        max_sh_degree = _require_nonnegative_int(
            "model.max_sh_degree", model_payload["max_sh_degree"]
        )
        active_sh_degree = _require_nonnegative_int(
            "model.active_sh_degree", model_payload["active_sh_degree"]
        )
    except ValueError as exc:
        raise CheckpointIntegrityError(str(exc)) from exc
    if sh_degree != max_sh_degree or active_sh_degree > max_sh_degree:
        raise CheckpointIntegrityError(
            "invalid SH metadata: "
            f"sh={sh_degree}, max={max_sh_degree}, active={active_sh_degree}"
        )
    expected_rest = (max_sh_degree + 1) ** 2 - 1
    if state["shN"].shape != (count, expected_rest, 3):
        raise CheckpointIntegrityError(
            f"shN shape {tuple(state['shN'].shape)} does not match degree {max_sh_degree}"
        )

    expected_shapes = {
        "means": (count, 3),
        "quats": (count, 4),
        "log_scales": (count, 3),
        "opacities_raw": (count,),
        "sh0": (count, 1, 3),
        "shN": (count, expected_rest, 3),
    }
    for name, expected_shape in expected_shapes.items():
        tensor = state[name]
        if not isinstance(tensor, torch.Tensor) or tensor.shape != expected_shape:
            raise CheckpointIntegrityError(
                f"model tensor {name} has shape {getattr(tensor, 'shape', None)}, "
                f"expected {expected_shape}"
            )
    sem_logits = state["sem_logits"]
    if (
        not isinstance(sem_logits, torch.Tensor)
        or sem_logits.ndim != 2
        or sem_logits.shape[0] != count
        or sem_logits.shape[1] <= 0
    ):
        raise CheckpointIntegrityError("sem_logits must have shape (N, K), K > 0")

    surface_mask = model_payload.get("surface_seed_mask")
    if surface_mask is not None:
        if not isinstance(surface_mask, torch.Tensor) or surface_mask.shape != (count,):
            raise CheckpointIntegrityError(
                "surface_seed_mask must be a tensor with one row per Gaussian"
            )

    try:
        model = GaussianModel2D.__new__(GaussianModel2D)
        torch.nn.Module.__init__(model)
        model.sh_degree = sh_degree
        model.max_sh_degree = max_sh_degree
        model.active_sh_degree = active_sh_degree
        model.num_classes = int(sem_logits.shape[1])
        for name in parameter_names:
            saved_tensor = state[name]
            empty = torch.empty_like(saved_tensor, device=device)
            setattr(model, name, torch.nn.Parameter(empty, requires_grad=True))
        if surface_mask is None:
            model.surface_seed_mask = torch.zeros(
                count, dtype=torch.bool, device=device
            )
        else:
            model.surface_seed_mask = surface_mask.detach().to(
                device=device, dtype=torch.bool
            )
        model.load_state_dict(state, strict=True)
    except Exception as exc:
        raise CheckpointReconstructionError(
            f"cannot reconstruct GaussianModel2D: {type(exc).__name__}: {exc}"
        ) from exc
    return model


def reconstruct_strategy(strategy_payload: Mapping[str, Any]) -> Any:
    """Recreate known gsplat/JointBuildGS strategy classes and custom attrs."""

    kind = strategy_payload.get("kind")
    if kind is None:
        return None
    config = strategy_payload.get("config")
    if not isinstance(config, Mapping):
        raise CheckpointIntegrityError("strategy config must be a mapping")

    # Imported here so the key reflects the actually installed gsplat module.
    from gsplat.strategy import DefaultStrategy

    known_classes = (
        DefaultStrategy,
        SeedProtectStrategy,
        ElongationFilterStrategy,
        SeedProtectElongationFilterStrategy,
    )
    classes = {_qualified_kind(cls): cls for cls in known_classes}
    cls = classes.get(kind)
    if cls is None:
        raise CheckpointReconstructionError(f"unsupported strategy kind: {kind!r}")

    fields = config.get("dataclass_fields", {})
    extras = config.get("extra_attributes", {})
    if not isinstance(fields, Mapping) or not isinstance(extras, Mapping):
        raise CheckpointIntegrityError("strategy config sections must be mappings")
    valid_fields = {field.name for field in dataclasses.fields(cls)}
    unknown_fields = sorted(set(fields) - valid_fields)
    if unknown_fields:
        raise CheckpointReconstructionError(
            f"strategy dataclass fields no longer exist: {unknown_fields}"
        )
    try:
        strategy = cls(**dict(fields))
        for name, value in extras.items():
            setattr(strategy, name, value)
    except Exception as exc:
        raise CheckpointReconstructionError(
            f"cannot reconstruct strategy {kind}: {type(exc).__name__}: {exc}"
        ) from exc
    return strategy


def _capture_strategy_config(strategy: Any) -> dict[str, Any]:
    if strategy is None:
        return {"dataclass_fields": {}, "extra_attributes": {}}
    fields: dict[str, Any] = {}
    if dataclasses.is_dataclass(strategy):
        fields = {
            field.name: getattr(strategy, field.name)
            for field in dataclasses.fields(strategy)
        }
    extras = {
        name: value
        for name, value in vars(strategy).items()
        if name not in fields
    }
    # These custom strategy controls are class attributes until configured, so
    # they may not occur in vars(strategy) even though they affect resumption.
    for name in (
        "axis_ratio_threshold",
        "seed_protect_until_iter",
        "seed_prune_opa_initial",
        "seed_prune_opa_final",
        "seed_prune_switch_iter",
    ):
        if hasattr(strategy, name) and name not in fields:
            extras[name] = getattr(strategy, name)
    return {"dataclass_fields": fields, "extra_attributes": extras}


def _validate_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise CheckpointIntegrityError("checkpoint payload must be a dictionary")
    required = {
        "checkpoint_format",
        "checkpoint_version",
        "step_semantics",
        "completed_steps",
        "model",
        "optimizers",
        "strategy",
        "grouping_state",
        "rng_state",
        "binding_sha256",
        "loss_log_cursor",
        "learning_runs_started",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise CheckpointIntegrityError(f"checkpoint is missing keys: {missing}")
    if payload["checkpoint_format"] != CHECKPOINT_FORMAT:
        raise CheckpointIntegrityError(
            f"unsupported checkpoint format: {payload['checkpoint_format']!r}"
        )
    if payload["checkpoint_version"] != CHECKPOINT_VERSION:
        raise CheckpointIntegrityError(
            f"unsupported checkpoint version: {payload['checkpoint_version']!r}"
        )
    if payload["step_semantics"] != STEP_SEMANTICS:
        raise CheckpointIntegrityError(
            f"invalid step semantics: {payload['step_semantics']!r}"
        )
    try:
        _require_nonnegative_int("completed_steps", payload["completed_steps"])
        _require_nonnegative_int(
            "learning_runs_started", payload["learning_runs_started"]
        )
        _normalize_binding_sha256(payload["binding_sha256"])
    except ValueError as exc:
        raise CheckpointIntegrityError(str(exc)) from exc

    model = payload["model"]
    if not isinstance(model, Mapping):
        raise CheckpointIntegrityError("model payload must be a mapping")
    model_required = {
        "kind",
        "state_dict",
        "tensor_shapes",
        "tensor_dtypes",
        "sh_degree",
        "max_sh_degree",
        "active_sh_degree",
        "surface_seed_mask",
    }
    model_missing = sorted(model_required - set(model))
    if model_missing:
        raise CheckpointIntegrityError(f"model payload is missing keys: {model_missing}")
    state_dict = model["state_dict"]
    shapes = model["tensor_shapes"]
    dtypes = model["tensor_dtypes"]
    if (
        not isinstance(state_dict, Mapping)
        or not isinstance(shapes, Mapping)
        or not isinstance(dtypes, Mapping)
    ):
        raise CheckpointIntegrityError(
            "model state_dict/tensor_shapes/tensor_dtypes must be mappings"
        )
    non_tensor_state = sorted(
        name for name, value in state_dict.items() if not isinstance(value, torch.Tensor)
    )
    if non_tensor_state:
        raise CheckpointIntegrityError(
            f"model state_dict contains non-tensor entries: {non_tensor_state}"
        )
    actual_shapes = {
        name: list(tensor.shape)
        for name, tensor in state_dict.items()
        if isinstance(tensor, torch.Tensor)
    }
    actual_dtypes = {
        name: str(tensor.dtype)
        for name, tensor in state_dict.items()
        if isinstance(tensor, torch.Tensor)
    }
    if dict(shapes) != actual_shapes:
        raise CheckpointIntegrityError("saved model tensor shape metadata is inconsistent")
    if dict(dtypes) != actual_dtypes:
        raise CheckpointIntegrityError("saved model tensor dtype metadata is inconsistent")
    try:
        sh_degree = _require_nonnegative_int("model.sh_degree", model["sh_degree"])
        max_sh_degree = _require_nonnegative_int(
            "model.max_sh_degree", model["max_sh_degree"]
        )
        active_sh_degree = _require_nonnegative_int(
            "model.active_sh_degree", model["active_sh_degree"]
        )
    except ValueError as exc:
        raise CheckpointIntegrityError(str(exc)) from exc
    if sh_degree != max_sh_degree or active_sh_degree > max_sh_degree:
        raise CheckpointIntegrityError("saved model SH metadata is inconsistent")
    means = state_dict.get("means")
    surface_seed_mask = model["surface_seed_mask"]
    if surface_seed_mask is not None:
        if (
            not isinstance(means, torch.Tensor)
            or not isinstance(surface_seed_mask, torch.Tensor)
            or surface_seed_mask.dtype != torch.bool
            or surface_seed_mask.shape != (means.shape[0],)
        ):
            raise CheckpointIntegrityError(
                "surface_seed_mask must be bool with one row per saved Gaussian"
            )

    optimizers = payload["optimizers"]
    if not isinstance(optimizers, Mapping):
        raise CheckpointIntegrityError("optimizers payload must be a mapping")
    for name, saved in optimizers.items():
        if not isinstance(name, str) or not isinstance(saved, Mapping):
            raise CheckpointIntegrityError("optimizer entries are malformed")
        if set(saved) != {"kind", "state_dict"}:
            raise CheckpointIntegrityError(f"optimizer {name} entry is malformed")
    strategy = payload["strategy"]
    if not isinstance(strategy, Mapping) or set(strategy) != {"kind", "config", "state"}:
        raise CheckpointIntegrityError("strategy payload is malformed")
    rng_state = payload["rng_state"]
    if not isinstance(rng_state, Mapping):
        raise CheckpointIntegrityError("RNG state must be a mapping")
    rng_required = {
        "python",
        "numpy",
        "torch_cpu",
        "torch_cuda",
        "torch_cuda_device_count",
    }
    rng_missing = sorted(rng_required - set(rng_state))
    if rng_missing:
        raise CheckpointIntegrityError(f"RNG state is missing keys: {rng_missing}")
    _as_cpu_byte_tensor(rng_state["torch_cpu"], "torch_cpu")
    if not isinstance(rng_state["torch_cuda"], (list, tuple)):
        raise CheckpointIntegrityError("torch_cuda RNG state must be a list")
    for device_index, rng in enumerate(rng_state["torch_cuda"]):
        _as_cpu_byte_tensor(rng, f"torch_cuda[{device_index}]")
    try:
        cuda_count = _require_nonnegative_int(
            "torch_cuda_device_count", rng_state["torch_cuda_device_count"]
        )
    except ValueError as exc:
        raise CheckpointIntegrityError(str(exc)) from exc
    if cuda_count != len(rng_state["torch_cuda"]):
        raise CheckpointIntegrityError(
            "CUDA RNG metadata count does not match the saved state list"
        )


def _normalize_binding_sha256(binding: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(binding, Mapping):
        raise ValueError("binding_sha256 must be a mapping")
    normalized: dict[str, str] = {}
    for key, digest in binding.items():
        if not isinstance(key, str) or not key:
            raise ValueError("binding_sha256 keys must be non-empty strings")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest.lower()):
            raise ValueError(f"binding_sha256[{key!r}] is not a SHA-256 hex digest")
        normalized[key] = digest.lower()
    return dict(sorted(normalized.items()))


def _binding_mismatch_message(
    checkpoint: Path,
    expected: Mapping[str, str],
    actual: Mapping[str, str],
) -> str:
    keys = sorted(set(expected) | set(actual))
    differences = [
        f"{key}: expected={expected.get(key, '<missing>')}, "
        f"actual={actual.get(key, '<missing>')}"
        for key in keys
        if expected.get(key) != actual.get(key)
    ]
    return f"binding SHA mismatch for {checkpoint}: " + "; ".join(differences)


def _read_sidecar(sidecar: Path, checkpoint_name: str) -> str:
    try:
        parts = sidecar.read_text(encoding="ascii").strip().split()
    except (FileNotFoundError, OSError, UnicodeError) as exc:
        raise CheckpointIntegrityError(
            f"cannot read checkpoint sidecar {sidecar}: {type(exc).__name__}: {exc}"
        ) from exc
    if len(parts) != 2 or not _SHA256_RE.fullmatch(parts[0].lower()):
        raise CheckpointIntegrityError(f"malformed SHA-256 sidecar: {sidecar}")
    if parts[1] != checkpoint_name:
        raise CheckpointIntegrityError(
            f"sidecar filename mismatch: expected={checkpoint_name}, recorded={parts[1]}"
        )
    return parts[0].lower()


def _new_temp_path(directory: Path, destination_name: str) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{destination_name}.", suffix=".tmp", dir=directory
    )
    os.close(descriptor)
    return Path(raw_path)


def _sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return _sha256_stream(stream)


def _sha256_stream(stream) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _qualified_kind(value_or_class: Any) -> str:
    cls = value_or_class if isinstance(value_or_class, type) else type(value_or_class)
    return f"{cls.__module__}.{cls.__qualname__}"


def _require_nonnegative_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _as_cpu_byte_tensor(value: Any, name: str) -> torch.Tensor:
    if not isinstance(value, torch.Tensor) or value.dtype != torch.uint8 or value.ndim != 1:
        raise CheckpointIntegrityError(f"{name} RNG state must be a 1-D uint8 tensor")
    return value.detach().cpu()

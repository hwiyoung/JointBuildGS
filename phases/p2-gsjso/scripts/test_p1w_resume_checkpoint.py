"""Focused CPU tests for the P1W full-state resume checkpoint contract."""
from __future__ import annotations

import hashlib
import random
import stat
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch

from src.stage2.checkpoint import (
    CheckpointBindingError,
    CheckpointIntegrityError,
    discover_latest_checkpoint,
    load_training_checkpoint,
    restore_training_checkpoint,
    save_training_checkpoint,
)
from src.stage2.densification import (
    build_optimizers,
    build_seed_protect_elongation_filter_strategy,
)
from src.stage2.model import GaussianModel2D


GOOD_BINDING = {
    "config": "1" * 64,
    "pilot_set": "2" * 64,
    "source_images": "3" * 64,
}
OTHER_BINDING = {
    "config": "a" * 64,
    "pilot_set": "b" * 64,
    "source_images": "c" * 64,
}


def _seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def _new_training_state(seed: int = 731):
    _seed_all(seed)
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.1],
            [0.0, 1.0, 0.2],
            [1.0, 1.0, 0.3],
            [0.5, 0.2, 0.4],
            [0.2, 0.7, 0.5],
        ],
        dtype=np.float32,
    )
    colors = np.array(
        [
            [0.2, 0.3, 0.4],
            [0.3, 0.4, 0.5],
            [0.4, 0.5, 0.6],
            [0.5, 0.6, 0.7],
            [0.6, 0.7, 0.8],
            [0.7, 0.8, 0.9],
        ],
        dtype=np.float32,
    )
    surface_seed_mask = np.array([True, False, True, False, False, True])
    model = GaussianModel2D(
        points,
        colors,
        sh_degree=2,
        device="cpu",
        surface_seed_mask=surface_seed_mask,
    )
    # Mimic two gsplat clone rows so reconstruction is tested against a dynamic
    # post-densification shape, not only the constructor's original population.
    for name in (
        "means",
        "quats",
        "log_scales",
        "opacities_raw",
        "sh0",
        "shN",
        "sem_logits",
    ):
        parameter = getattr(model, name)
        setattr(
            model,
            name,
            torch.nn.Parameter(
                torch.cat([parameter.detach(), parameter.detach()[:2]], dim=0)
            ),
        )
    model.surface_seed_mask = torch.cat(
        [model.surface_seed_mask, model.surface_seed_mask[:2]], dim=0
    )
    optimizers = build_optimizers(model)
    strategy = build_seed_protect_elongation_filter_strategy(
        axis_ratio_threshold=0.023,
        seed_protect_until_iter=20_000,
        seed_prune_opa_initial=0.10,
        seed_prune_opa_final=0.25,
        seed_prune_switch_iter=5_000,
        refine_start_iter=25,
        refine_stop_iter=20_000,
    )
    strategy.densify_audit_boxes = {"B001": (0.0, 0.0, 1.0, 1.0)}
    strategy_state = {
        "scene_scale": 2.5,
        "is_seed": model.surface_seed_mask.clone(),
        "counter": 0,
    }
    grouping_state = {"revision": 2, "history": []}
    loss_log_cursor = {"rows": 0, "last_completed_step": 0}
    return (
        model,
        optimizers,
        strategy,
        strategy_state,
        grouping_state,
        loss_log_cursor,
    )


def _run_updates(
    model: GaussianModel2D,
    optimizers,
    strategy_state: dict[str, Any],
    grouping_state: dict[str, Any],
    loss_log_cursor: dict[str, int],
    *,
    first_completed_step: int,
    final_completed_step: int,
) -> None:
    """Deterministic toy loop that consumes all three host/CPU RNG streams."""

    for completed_step in range(first_completed_step, final_completed_step + 1):
        for optimizer in optimizers.values():
            optimizer.zero_grad(set_to_none=True)

        random_factor = random.random()
        numpy_factor = float(np.random.random())
        torch_factor = torch.rand((), dtype=torch.float32)
        shared = torch_factor + 0.01 * (random_factor + numpy_factor)
        loss = torch.zeros((), dtype=torch.float32)
        for index, parameter in enumerate(model.parameters(), start=1):
            coefficient = shared * (index * 1.0e-3) + index * 1.0e-4
            loss = loss + (parameter * coefficient).square().mean()
        loss.backward()
        for optimizer in optimizers.values():
            optimizer.step()

        if completed_step in (2, 4):
            model.oneup_sh_degree()
        strategy_state["counter"] += 1
        grouping_state["history"].append(
            {"completed_step": completed_step, "n": model.num_points}
        )
        loss_log_cursor["rows"] += 1
        loss_log_cursor["last_completed_step"] = completed_step


def _assert_nested_equal(left: Any, right: Any) -> None:
    if isinstance(left, torch.Tensor):
        assert isinstance(right, torch.Tensor)
        assert left.dtype == right.dtype
        assert left.shape == right.shape
        assert torch.equal(left.cpu(), right.cpu())
    elif isinstance(left, dict):
        assert isinstance(right, dict)
        assert set(left) == set(right)
        for key in left:
            _assert_nested_equal(left[key], right[key])
    elif isinstance(left, (list, tuple)):
        assert type(left) is type(right)
        assert len(left) == len(right)
        for left_item, right_item in zip(left, right):
            _assert_nested_equal(left_item, right_item)
    else:
        assert left == right


def test_atomic_save_has_completed_update_semantics_and_sha_sidecar(tmp_path: Path) -> None:
    model, optimizers, strategy, strategy_state, grouping_state, cursor = (
        _new_training_state()
    )
    model.oneup_sh_degree()
    saved = save_training_checkpoint(
        tmp_path,
        completed_steps=5_000,
        model=model,
        optimizers=optimizers,
        strategy=strategy,
        strategy_state=strategy_state,
        grouping_state=grouping_state,
        binding_sha256=GOOD_BINDING,
        loss_log_cursor=cursor,
        learning_runs_started=1,
    )

    assert saved.path.name == "step_005000.pt"
    assert saved.sidecar_path.name == "step_005000.pt.sha256"
    assert saved.completed_steps == 5_000
    assert hashlib.sha256(saved.path.read_bytes()).hexdigest() == saved.sha256
    assert saved.sidecar_path.read_text(encoding="ascii") == (
        f"{saved.sha256}  step_005000.pt\n"
    )
    assert stat.S_IMODE(saved.path.stat().st_mode) == 0o644
    assert stat.S_IMODE(saved.sidecar_path.stat().st_mode) == 0o644
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob(".*.tmp"))

    loaded = load_training_checkpoint(
        saved.path, expected_binding_sha256=GOOD_BINDING
    )
    assert loaded.completed_steps == 5_000
    assert loaded.payload["step_semantics"] == "completed_optimizer_updates"
    assert loaded.payload["model"]["active_sh_degree"] == 1
    assert loaded.payload["model"]["tensor_shapes"]["means"] == [8, 3]
    assert set(loaded.payload["optimizers"]) == set(optimizers)


def test_discovery_skips_corrupt_and_binding_mismatched_newest(tmp_path: Path) -> None:
    model, optimizers, strategy, strategy_state, grouping_state, cursor = (
        _new_training_state()
    )

    valid = save_training_checkpoint(
        tmp_path,
        completed_steps=100,
        model=model,
        optimizers=optimizers,
        strategy=strategy,
        strategy_state=strategy_state,
        grouping_state=grouping_state,
        binding_sha256=GOOD_BINDING,
        loss_log_cursor=cursor,
        learning_runs_started=1,
    )
    mismatched = save_training_checkpoint(
        tmp_path,
        completed_steps=200,
        model=model,
        optimizers=optimizers,
        strategy=strategy,
        strategy_state=strategy_state,
        grouping_state=grouping_state,
        binding_sha256=OTHER_BINDING,
        loss_log_cursor=cursor,
        learning_runs_started=1,
    )
    corrupt = save_training_checkpoint(
        tmp_path,
        completed_steps=300,
        model=model,
        optimizers=optimizers,
        strategy=strategy,
        strategy_state=strategy_state,
        grouping_state=grouping_state,
        binding_sha256=GOOD_BINDING,
        loss_log_cursor=cursor,
        learning_runs_started=1,
    )
    with corrupt.path.open("ab") as stream:
        stream.write(b"deliberate corruption")

    discovery = discover_latest_checkpoint(
        tmp_path, expected_binding_sha256=GOOD_BINDING
    )
    assert discovery.selected is not None
    assert discovery.selected.path == valid.path
    assert [item.path.name for item in discovery.skipped] == [
        "step_000300.pt",
        "step_000200.pt",
    ]
    assert [item.error_type for item in discovery.skipped] == [
        "CheckpointIntegrityError",
        "CheckpointBindingError",
    ]

    with pytest.raises(CheckpointBindingError):
        load_training_checkpoint(
            mismatched.path, expected_binding_sha256=GOOD_BINDING
        )
    with pytest.raises(CheckpointBindingError):
        restore_training_checkpoint(
            mismatched.path,
            expected_binding_sha256=GOOD_BINDING,
            device="cpu",
        )
    with pytest.raises(CheckpointIntegrityError):
        load_training_checkpoint(corrupt.path, expected_binding_sha256=GOOD_BINDING)


def test_uninterrupted_n_matches_k_plus_exact_resume_on_cpu(tmp_path: Path) -> None:
    total_steps = 8
    split_steps = 3

    full = _new_training_state(seed=919)
    _run_updates(
        full[0],
        full[1],
        full[3],
        full[4],
        full[5],
        first_completed_step=1,
        final_completed_step=total_steps,
    )
    full_next_rng = (random.random(), float(np.random.random()), torch.rand(()))

    split = _new_training_state(seed=919)
    _run_updates(
        split[0],
        split[1],
        split[3],
        split[4],
        split[5],
        first_completed_step=1,
        final_completed_step=split_steps,
    )
    saved = save_training_checkpoint(
        tmp_path,
        completed_steps=split_steps,
        model=split[0],
        optimizers=split[1],
        strategy=split[2],
        strategy_state=split[3],
        grouping_state=split[4],
        binding_sha256=GOOD_BINDING,
        loss_log_cursor=split[5],
        learning_runs_started=1,
    )

    # Prove restoration, rather than accidental continuation, supplies state.
    random.random()
    np.random.random()
    torch.rand(17)
    selected = discover_latest_checkpoint(
        tmp_path, expected_binding_sha256=GOOD_BINDING
    ).selected
    assert selected is not None
    assert selected.path == saved.path
    restored = restore_training_checkpoint(
        selected,
        expected_binding_sha256=GOOD_BINDING,
        device="cpu",
    )
    assert restored.completed_steps == split_steps
    assert restored.model.num_points == 8
    assert restored.learning_runs_started == 1
    assert restored.strategy.axis_ratio_threshold == pytest.approx(0.023)
    assert restored.strategy.seed_prune_opa_initial == pytest.approx(0.10)
    assert restored.strategy.seed_prune_opa_final == pytest.approx(0.25)
    assert restored.strategy.densify_audit_boxes == {
        "B001": (0.0, 0.0, 1.0, 1.0)
    }

    _run_updates(
        restored.model,
        restored.optimizers,
        restored.strategy_state,
        restored.grouping_state,
        restored.loss_log_cursor,
        first_completed_step=restored.completed_steps + 1,
        final_completed_step=total_steps,
    )
    resumed_next_rng = (random.random(), float(np.random.random()), torch.rand(()))

    _assert_nested_equal(full[0].state_dict(), restored.model.state_dict())
    _assert_nested_equal(
        {name: opt.state_dict() for name, opt in full[1].items()},
        {name: opt.state_dict() for name, opt in restored.optimizers.items()},
    )
    _assert_nested_equal(full[3], restored.strategy_state)
    _assert_nested_equal(full[4], restored.grouping_state)
    _assert_nested_equal(full[5], restored.loss_log_cursor)
    _assert_nested_equal(full_next_rng, resumed_next_rng)
    assert full[0].active_sh_degree == restored.model.active_sh_degree == 2

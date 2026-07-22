"""Trainer-side tests for the P1W full-state checkpoint integration."""
from __future__ import annotations

import random
import stat
from pathlib import Path

import pytest
import torch

from src.stage2.checkpoint import capture_rng_state, restore_rng_state
from src.stage2.train import set_seed
from src.stage2.train_resume import (
    FULL_STATE_MANIFEST_SCHEMA,
    atomic_write_json,
    capture_loss_csv_cursor,
    capture_trainer_runtime_state,
    full_state_binding_sha256,
    full_state_checkpoint_due,
    full_state_options,
    learning_runs_for_process,
    read_learning_runs_started,
    restore_loss_csv_cursor,
    restore_trainer_runtime_state,
    training_view_index,
)


def test_full_state_options_are_opt_in_and_keep_four_guard_steps() -> None:
    legacy = full_state_options({})
    assert legacy["enabled"] is False
    assert legacy["checkpoint_steps"] == ()

    enabled = full_state_options(
        {
            "full_state_checkpoint": True,
            "full_state_checkpoint_steps": [17],
            "full_state_loss_csv_paths": ["pilot_1wave_loss_shares.csv"],
        }
    )
    assert enabled["checkpoint_steps"] == (17, 5000, 10000, 15000, 20000)
    assert "pilot_1wave_loss_shares.csv" in enabled["loss_csv_paths"]
    assert full_state_options({"full_state_resume": "auto"})["enabled"] is True
    assert full_state_options({"full_state_resume": "off"})["enabled"] is False

    with pytest.raises(ValueError, match="escape"):
        full_state_options({"full_state_loss_csv_paths": ["../outside.csv"]})


def test_binding_ignores_resume_transport_but_binds_training_and_output(
    tmp_path: Path,
) -> None:
    effective = {
        "full_state_checkpoint_enabled": True,
        "full_state_checkpoint_steps": [5000, 10000, 15000, 20000],
        "seed_protect": True,
    }
    auto_cfg = {
        "seed": 1001,
        "max_iter": 20000,
        "full_state_checkpoint": True,
        "full_state_resume": "auto",
    }
    explicit_cfg = {
        **auto_cfg,
        "full_state_resume": str(tmp_path / "ckpt" / "step_005000.pt"),
    }
    auto_binding = full_state_binding_sha256(
        cfg=auto_cfg,
        effective_training_config=effective,
        out_dir=tmp_path / "run",
    )
    explicit_binding = full_state_binding_sha256(
        cfg=explicit_cfg,
        effective_training_config=effective,
        out_dir=tmp_path / "run",
    )
    assert auto_binding == explicit_binding

    changed_seed = full_state_binding_sha256(
        cfg={**auto_cfg, "seed": 1002},
        effective_training_config=effective,
        out_dir=tmp_path / "run",
    )
    changed_output = full_state_binding_sha256(
        cfg=auto_cfg,
        effective_training_config=effective,
        out_dir=tmp_path / "other_run",
    )
    assert changed_seed["training_config"] != auto_binding["training_config"]
    assert changed_output["output_path"] != auto_binding["output_path"]


def test_completed_update_schedule_and_random_view_sequence_resume_exact() -> None:
    options = full_state_options({"full_state_checkpoint": True})
    due = [
        iteration + 1
        for iteration in range(20000)
        if full_state_checkpoint_due(options, completed_steps=iteration + 1)
    ]
    assert due == [5000, 10000, 15000, 20000]

    train_indices = [2, 5, 8, 13, 21]
    total_updates = 41
    split_updates = 17

    set_seed(551)
    uninterrupted = [
        training_view_index(train_indices, iteration=it, sequential=False)
        for it in range(total_updates)
    ]

    set_seed(551)
    prefix = [
        training_view_index(train_indices, iteration=it, sequential=False)
        for it in range(split_updates)
    ]
    saved_rng = capture_rng_state()
    random.random()
    torch.rand(19)
    restore_rng_state(saved_rng)
    suffix = [
        training_view_index(train_indices, iteration=it, sequential=False)
        for it in range(split_updates, total_updates)
    ]
    assert prefix + suffix == uninterrupted

    sequential_suffix = [
        training_view_index(train_indices, iteration=it, sequential=True)
        for it in range(split_updates, total_updates)
    ]
    assert sequential_suffix[0] == train_indices[split_updates % len(train_indices)]


def test_loss_csv_cursor_validates_prefix_and_rolls_back_only_tail(
    tmp_path: Path,
) -> None:
    paths = (
        "audit/loss_grad_norms.csv",
        "audit/semantic_geometry.csv",
    )
    loss_path = tmp_path / paths[0]
    loss_path.parent.mkdir(parents=True)
    checkpoint_bytes = b"step,loss\n0,1.0\n"
    loss_path.write_bytes(checkpoint_bytes)
    cursor = capture_loss_csv_cursor(tmp_path, paths, completed_steps=5000)

    loss_path.write_bytes(checkpoint_bytes + b"5000,9.9\n")
    post_checkpoint_file = tmp_path / paths[1]
    post_checkpoint_file.write_text("post-checkpoint\n", encoding="utf-8")
    actions = restore_loss_csv_cursor(
        tmp_path,
        paths,
        cursor,
        expected_completed_steps=5000,
    )
    assert loss_path.read_bytes() == checkpoint_bytes
    assert not post_checkpoint_file.exists()
    assert len(actions) == 2

    loss_path.write_bytes(b"X" + checkpoint_bytes[1:])
    with pytest.raises(RuntimeError, match="prefix changed"):
        restore_loss_csv_cursor(
            tmp_path,
            paths,
            cursor,
            expected_completed_steps=5000,
        )


def test_runtime_bundle_restores_groups_planes_and_audit_counters() -> None:
    class Geometry:
        def __init__(self):
            self._planes = {}

    source_geometry = Geometry()
    source_geometry._planes = {("view", 7): {"normal": torch.tensor([0.0, 0.0, 1.0])}}
    groups = {
        "group_ids": torch.tensor([0, 0, -1]),
        "rep_n": torch.tensor([[0.0, 0.0, 1.0]]),
        "rep_d": torch.tensor([2.0]),
    }
    saved = capture_trainer_runtime_state(
        structure_groups=groups,
        semantic_geometry=source_geometry,
        semantic_target_observations={"B001": 4, "B002": 0},
        semantic_pi_audited_targets={"B001"},
    )

    restored_geometry = Geometry()
    restored_groups, observations, audited = restore_trainer_runtime_state(
        saved,
        semantic_geometry=restored_geometry,
        expected_semantic_targets={"B001", "B002"},
    )
    assert torch.equal(restored_groups["group_ids"], groups["group_ids"])
    assert torch.equal(
        restored_geometry._planes[("view", 7)]["normal"],
        torch.tensor([0.0, 0.0, 1.0]),
    )
    assert observations == {"B001": 4, "B002": 0}
    assert audited == {"B001"}


def test_learning_run_counter_increments_fresh_only_and_manifest_is_atomic(
    tmp_path: Path,
) -> None:
    # The helper returns the value planned for the first completed optimizer
    # update.  train.py deliberately does not persist it during setup.
    assert learning_runs_for_process(0, resuming=False, will_train=True) == (1, True)
    assert learning_runs_for_process(1, resuming=True, will_train=True) == (1, False)
    assert learning_runs_for_process(1, resuming=False, will_train=False) == (1, False)

    manifest = tmp_path / "full_state_manifest.json"
    atomic_write_json(
        manifest,
        {
            "schema": FULL_STATE_MANIFEST_SCHEMA,
            "learning_runs_started": 3,
        },
    )
    assert read_learning_runs_started(manifest) == 3
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o644
    assert not list(tmp_path.glob(".*.tmp"))

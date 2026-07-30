#!/usr/bin/env python3
"""Read-only S3-A checkpoint gradient-potential pairing audit.

This audit closes one deliberately post-hoc measurement gap without changing
either training run.  For each locked S3-A checkpoint it renders the same
three pre-execution committed-oracle-cache views per target building,
ranked by target address pixels before any checkpoint is opened, evaluates the
*existing* :class:`SemanticGuidedGeometry` smooth+plane loss, and differentiates
that weighted loss only with respect to a detached rendered-depth leaf.

The result is therefore a ``posthoc checkpoint gradient potential``.  It is
not the exact online optimizer-time gradient: the original random training
view and stateful plane cache were not checkpointed.  No optimizer is created,
``Tensor.backward`` is never called, model tensors are frozen, and checkpoint,
config, cache, timeline, and selected-view input hashes are checked before and
after the sweep.

Locked coverage:

* r1/r2 x {5k,10k,15k,20k,25k,final};
* collapse targets 4907202, 4908168, 4908178, exactly three fixed views each;
* organization target 4907199, exactly three fixed views;
* 36 collapse building-median rows paired to the existing roof-crop timeline.

Scientific execution is GPU/Docker only.  The downstream adapter owns the
host-side launcher; this file is the in-container worker.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import numpy as np
import torch
import yaml


SCRIPT_PATH = Path(__file__).resolve()
REPO = SCRIPT_PATH.parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(SCRIPT_PATH.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_PATH.parent))

from src.stage2.dataloader import ColmapDataset  # noqa: E402
from src.stage2.loss.semantic_guided import (  # noqa: E402
    SemanticGuidedGeometry,
    SemanticRegionCache,
)


RUN_ID = "20260713_e5_c001_s3_semantic_guided"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
CONFIG_DIR = REPO / "configs/tum_mob/e5_s3_semantic_guided"
RESULTS_ROOT = REPO / "results/tum_transfer/e5_s3_semantic_guided/C001"
CKPT_ROOT = RESULTS_ROOT / "runs"
FULL_RUNS = [
    "gs_e5_C001_s3a_semantic_guided_r1",
    "gs_e5_C001_s3a_semantic_guided_r2",
]
RUN_TO_REPLICATE = {FULL_RUNS[0]: "r1", FULL_RUNS[1]: "r2"}

CHECKPOINT_STEPS = (5000, 10000, 15000, 20000, 25000, 30000)
COLLAPSE_TARGETS = ("4907202", "4908168", "4908178")
ORGANIZATION_TARGETS = ("4907199",)
ALL_TARGETS = COLLAPSE_TARGETS + ORGANIZATION_TARGETS
VIEWS_PER_BUILDING = 3

TIMELINE_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_timeline_roofcrop.csv"
CACHE_INVENTORY = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_semantic_region_inventory.csv"
PRIOR_FIXED_VIEW_AUDIT = (
    REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_semantic_region_projection_height_audit.csv"
)
OUTPUT_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_checkpoint_gradient_pairing.csv"
FIG_SURVIVAL = REPO / "docs/figs/e5_c001_s3/timeline/survival_gradient_pairing.png"
FIG_ORGANIZATION = REPO / "docs/figs/e5_c001_s3/timeline/organization_plane_residual.png"
OUTPUT_MANIFEST = RUN_DIR / "checkpoint_gradient_pairing.json"

SEMANTIC_LOSS_PATH = REPO / "src/stage2/loss/semantic_guided.py"
TRAIN_PATH = REPO / "src/stage2/train.py"
RENDERER_PATH = REPO / "src/stage2/renderer.py"
DATALOADER_PATH = REPO / "src/stage2/dataloader.py"
DOWNSTREAM_PATH = SCRIPT_PATH.parent / "e5_c001_s3_downstream.py"

CLAIM_SCOPE = (
    "posthoc checkpoint gradient potential; fixed-view read-only measurement; "
    "not exact online optimizer-time gradient; no FM/paper claim"
)
MEASUREMENT_MODE = "detached_render_depth_autograd_grad_no_optimizer_no_backward"
PLANE_FIT_SCOPE = "fresh_detached_robust_plane_per_checkpoint_view"
VIEW_SELECTION_SCOPE = "preexecution_committed_oracle_cache_top3_by_address_pixels"
PRIOR_VIEW_SELECTION_SCOPE = "locked_projection_height_audit_top3_by_reference_area"
EXPECTED_PRIOR_ZERO_ADDRESS = {
    ("4908168", "DJI_20241217084851_0189_D"),
    ("4907199", "DJI_20241217102653_0002_D"),
}

REQUIRED_STATE_KEYS = (
    "means",
    "quats",
    "log_scales",
    "opacities_raw",
    "sh0",
    "shN",
    "sem_logits",
)
LOCKED_CONFIG_VALUES: dict[str, Any] = {
    "seed": 2001,
    "max_iter": 30000,
    "ckpt_every": 5000,
    "w_semdepth_smooth": 0.125,
    "w_semdepth_plane": 0.125,
    "w_boundary_normal": 0.01,
    "semantic_geometry_warmup": 1500,
    "semantic_alpha_threshold": 0.5,
    "semantic_source_component_min_pixels": 256,
    "semantic_component_connectivity": 8,
    "semantic_footprint_buffer_m": 20.0,
    "semantic_cutline_half_width_px": 7,
    "semantic_plane_min_pixels": 64,
    "semantic_plane_refit_every": 500,
    "semantic_huber_delta": 1.0,
    "semantic_plane_irls_iterations": 5,
    "semantic_boundary_band_px": 5,
    "s3_gate_attempt": 0,
    "w_mono_depth": 0.0,
    "s3_no_monocular_depth": True,
}


def rel(path: Path | str) -> str:
    value = Path(path)
    for root in (REPO, Path("/workspace/JointBuildGS")):
        try:
            return str(value.relative_to(root))
        except ValueError:
            pass
    return str(value)


def repo_path(value: str | Path) -> Path:
    text = str(value)
    prefix = "/workspace/JointBuildGS/"
    if text.startswith(prefix):
        return REPO / text[len(prefix):]
    path = Path(text)
    return path if path.is_absolute() else REPO / path


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"required CSV missing or empty: {rel(path)}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_versions(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(path)
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        if key in result:
            raise RuntimeError(f"duplicate versions key {key!r}: {rel(path)}")
        result[key] = value
    return result


def same_value(left: Any, right: Any) -> bool:
    if isinstance(right, bool):
        return bool(left) is right
    if isinstance(right, (int, float)) and not isinstance(right, bool):
        try:
            return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    return left == right


def require_committed_clean(paths: Sequence[Path]) -> str:
    """Fail closed unless every implementation input is tracked and clean."""

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    ).stdout.strip()
    for path in paths:
        relative = rel(path)
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=REPO,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if tracked.returncode != 0:
            raise RuntimeError(f"implementation input is not committed: {relative}")
        dirty = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", relative],
            cwd=REPO,
            check=False,
        )
        if dirty.returncode != 0:
            raise RuntimeError(f"implementation input differs from HEAD: {relative}")
    return head


def git_blob_sha256(commit: str, path: Path) -> str:
    process = subprocess.run(
        ["git", "show", f"{commit}:{rel(path)}"],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"cannot read launch-time git blob {commit}:{rel(path)}: "
            f"{process.stderr.decode('utf-8', errors='replace')[-300:]}"
        )
    return hashlib.sha256(process.stdout).hexdigest()


def validate_config(config: Mapping[str, Any], run_name: str) -> None:
    mismatches = {
        key: {"actual": config.get(key), "expected": expected}
        for key, expected in LOCKED_CONFIG_VALUES.items()
        if not same_value(config.get(key), expected)
    }
    expected_out = CKPT_ROOT / run_name
    if repo_path(config.get("out_dir", "")) != expected_out:
        mismatches["out_dir"] = {
            "actual": config.get("out_dir"),
            "expected": rel(expected_out),
        }
    if not bool(config.get("load_depth")) or not bool(config.get("load_semantic")):
        mismatches["data_load"] = {
            "actual": {
                "load_depth": config.get("load_depth"),
                "load_semantic": config.get("load_semantic"),
            },
            "expected": {"load_depth": True, "load_semantic": True},
        }
    if mismatches:
        raise RuntimeError(
            f"locked checkpoint-pairing config mismatch for {run_name}: "
            f"{json.dumps(mismatches, ensure_ascii=False, sort_keys=True)}"
        )


def validate_effective_config(config: Mapping[str, Any], path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    effective = json.loads(path.read_text(encoding="utf-8"))
    keys = (
        "normal_dir",
        "w_semdepth_smooth",
        "w_semdepth_plane",
        "w_boundary_normal",
        "semantic_geometry_warmup",
        "semantic_alpha_threshold",
        "semantic_source_component_min_pixels",
        "semantic_component_connectivity",
        "semantic_footprint_buffer_m",
        "semantic_cutline_half_width_px",
        "semantic_plane_min_pixels",
        "semantic_plane_refit_every",
        "semantic_region_cache",
    )
    mismatches: dict[str, Any] = {
        key: {"effective": effective.get(key), "config": config.get(key)}
        for key in keys
        if key not in effective or not same_value(effective.get(key), config.get(key))
    }
    if mismatches:
        raise RuntimeError(
            f"effective config disagrees with launch config: "
            f"{json.dumps(mismatches, ensure_ascii=False, sort_keys=True)}"
        )
    return sha256_file(path)


def validate_cache_hashes(
    *,
    cache_root: Path,
    semantic_root: Path,
    expected_aggregate: str,
    expected_inventory_sha: str,
) -> dict[str, Any]:
    """Hash all 428 canonical cache/semantic pairs against the producer ledger."""

    if sha256_file(CACHE_INVENTORY) != expected_inventory_sha:
        raise RuntimeError("semantic-region inventory hash differs from launch ledger")
    rows = read_csv(CACHE_INVENTORY)
    if len(rows) != 428:
        raise RuntimeError(f"semantic-region inventory must have 428 rows, got {len(rows)}")
    pairs: list[list[str]] = []
    seen: set[str] = set()
    for row in rows:
        stem = row.get("view_stem", "")
        if not stem or stem in seen:
            raise RuntimeError(f"empty/duplicate cache view stem: {stem!r}")
        seen.add(stem)
        cache_path = cache_root / f"{stem}.npz"
        semantic_path = semantic_root / f"{stem}.png"
        expected_cache_path = rel(cache_path)
        expected_semantic_path = rel(semantic_path)
        if (
            row.get("status") != "ok"
            or row.get("cache_path") != expected_cache_path
            or row.get("semantic_mask_path") != expected_semantic_path
        ):
            raise RuntimeError(f"cache inventory path/status mismatch for {stem}")
        cache_sha = sha256_file(cache_path)
        semantic_sha = sha256_file(semantic_path)
        if cache_sha != row.get("cache_sha256"):
            raise RuntimeError(f"cache hash mismatch for {stem}")
        if semantic_sha != row.get("semantic_mask_sha256"):
            raise RuntimeError(f"semantic-mask hash mismatch for {stem}")
        pairs.append([stem, cache_sha])
    aggregate = sha256_json(pairs)
    if aggregate != expected_aggregate:
        raise RuntimeError(
            f"cache aggregate differs from launch ledger: "
            f"expected={expected_aggregate}, observed={aggregate}"
        )
    return {
        "cache_inventory_sha256": expected_inventory_sha,
        "cache_aggregate_sha256": aggregate,
        "cache_file_count": len(rows),
    }


def _tensor_signature(tensor: torch.Tensor) -> tuple[Any, ...]:
    return (
        tuple(tensor.shape),
        str(tensor.dtype),
        str(tensor.device),
        int(tensor.data_ptr()),
        int(tensor._version),
        bool(tensor.requires_grad),
    )


class FrozenCheckpointModel:
    """Minimal immutable model interface consumed by ``src.stage2.renderer``."""

    def __init__(self, state: Mapping[str, torch.Tensor], *, sh_degree: int, device: str):
        missing = sorted(set(REQUIRED_STATE_KEYS) - set(state))
        if missing:
            raise RuntimeError(f"checkpoint state misses renderer tensors: {missing}")
        lengths = {int(state[key].shape[0]) for key in REQUIRED_STATE_KEYS}
        if len(lengths) != 1:
            raise RuntimeError(f"checkpoint tensor leading dimensions disagree: {sorted(lengths)}")
        self.sh_degree = int(sh_degree)
        self.max_sh_degree = int(sh_degree)
        self.active_sh_degree = int(sh_degree)
        for key in REQUIRED_STATE_KEYS:
            value = state[key]
            if not torch.is_tensor(value):
                raise TypeError(f"checkpoint state {key} is not a tensor")
            frozen = value.detach().to(device=device).contiguous()
            frozen.requires_grad_(False)
            setattr(self, key, frozen)

    @property
    def scales(self) -> torch.Tensor:
        return torch.exp(self.log_scales)

    @property
    def opacities(self) -> torch.Tensor:
        return torch.sigmoid(self.opacities_raw)

    def colors_sh(self) -> torch.Tensor:
        return torch.cat([self.sh0, self.shN], dim=1)

    def state_signature(self) -> dict[str, tuple[Any, ...]]:
        return {key: _tensor_signature(getattr(self, key)) for key in REQUIRED_STATE_KEYS}

    def assert_frozen(self) -> None:
        offenders = [key for key in REQUIRED_STATE_KEYS if getattr(self, key).requires_grad]
        if offenders:
            raise RuntimeError(f"checkpoint model tensors unexpectedly require gradients: {offenders}")
        grads = [key for key in REQUIRED_STATE_KEYS if getattr(self, key).grad is not None]
        if grads:
            raise RuntimeError(f"checkpoint model tensors unexpectedly accumulated gradients: {grads}")


@dataclass(frozen=True)
class ViewCandidate:
    building_id: str
    dataset_index: int
    view: str
    view_stem: str
    address_pixel_count: int


def short_id(value: Any) -> str:
    return str(value or "").replace("DEBY_LOD2_", "")


def rank_oracle_cache_candidates(
    candidates: Sequence[ViewCandidate],
    *,
    targets: Sequence[str] = ALL_TARGETS,
    views_per_building: int = VIEWS_PER_BUILDING,
) -> tuple[dict[str, list[ViewCandidate]], dict[str, list[ViewCandidate]]]:
    if views_per_building != VIEWS_PER_BUILDING:
        raise ValueError(f"checkpoint gradient pairing requires exactly {VIEWS_PER_BUILDING} views")
    grouped: dict[str, list[ViewCandidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.building_id in targets and candidate.address_pixel_count > 0:
            grouped[candidate.building_id].append(candidate)
    ranked: dict[str, list[ViewCandidate]] = {}
    selected: dict[str, list[ViewCandidate]] = {}
    for building_id in targets:
        ordered = sorted(
            grouped.get(building_id, []),
            key=lambda row: (-row.address_pixel_count, row.view_stem),
        )
        stems = [row.view_stem for row in ordered]
        if len(stems) != len(set(stems)):
            raise RuntimeError(f"duplicate oracle-cache candidate stems for {building_id}")
        if len(ordered) < views_per_building:
            raise RuntimeError(
                f"oracle-cache positive-address coverage below {views_per_building} for "
                f"{building_id}: observed={len(ordered)}"
            )
        ranked[building_id] = ordered
        selected[building_id] = ordered[:views_per_building]
    return selected, ranked


def select_oracle_cache_fixed_views(
    dataset: ColmapDataset,
    cache: SemanticRegionCache,
    *,
    targets: Sequence[str] = ALL_TARGETS,
    views_per_building: int = VIEWS_PER_BUILDING,
) -> tuple[dict[str, list[ViewCandidate]], dict[str, list[ViewCandidate]]]:
    """Rank every training view with a positive committed-oracle address.

    Selection uses only committed cache contents before any checkpoint/GPU
    result is opened: target address pixels descending, then view stem
    ascending.  Test-split views and zero-address views are ineligible.
    """

    candidates: list[ViewCandidate] = []
    for index, frame_info in enumerate(dataset.frames):
        if index % 10 == 9:
            continue
        stem = Path(frame_info.name).stem
        height = int(round(frame_info.height * dataset.downscale))
        width = int(round(frame_info.width * dataset.downscale))
        frame = cache.get(frame_info.name, height, width, "cpu")
        metadata_regions = frame.metadata.get("regions", {})
        counts: dict[str, int] = defaultdict(int)
        for rid_value, metadata in metadata_regions.items():
            building_id = short_id(metadata.get("building_id"))
            if building_id not in targets:
                continue
            rid = int(rid_value)
            counts[building_id] += int(
                ((frame.region_ids == rid) & (~frame.cutline_mask)).sum().item()
            )
        for building_id, address_count in counts.items():
            if address_count <= 0:
                continue
            candidates.append(
                ViewCandidate(
                    building_id=building_id,
                    dataset_index=index,
                    view=frame_info.name,
                    view_stem=stem,
                    address_pixel_count=address_count,
                )
            )
        cache._cpu_cache.pop(stem, None)
    return rank_oracle_cache_candidates(
        candidates,
        targets=targets,
        views_per_building=views_per_building,
    )


def build_view_selection_provenance(
    *,
    selected: Mapping[str, Sequence[ViewCandidate]],
    ranked_candidates: Mapping[str, Sequence[ViewCandidate]],
    prior_audit_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Record the full pre-execution candidate ledger and recovery reason."""

    candidate_counts = {
        building_id: {row.view_stem: row.address_pixel_count for row in candidates}
        for building_id, candidates in ranked_candidates.items()
    }
    prior_selected: list[dict[str, Any]] = []
    for row in prior_audit_rows:
        building_id = short_id(row.get("building_id"))
        if (
            building_id not in ALL_TARGETS
            or row.get("row_type") != "view"
            or str(row.get("selected_top3_by_reference_area", "")).strip().lower()
            not in {"true", "1", "yes"}
        ):
            continue
        stem = str(row.get("view_stem", ""))
        count = int(candidate_counts.get(building_id, {}).get(stem, 0))
        prior_selected.append(
            {
                "building_id": building_id,
                "view_stem": stem,
                "committed_oracle_cache_target_address_pixel_count": count,
                "eligible_positive_train_address": count > 0,
            }
        )
    if len(prior_selected) != len(ALL_TARGETS) * VIEWS_PER_BUILDING:
        raise RuntimeError(
            f"prior top3 audit recovery expected 12 rows, got {len(prior_selected)}"
        )
    invalid = {
        (row["building_id"], row["view_stem"])
        for row in prior_selected
        if not row["eligible_positive_train_address"]
    }
    if invalid != EXPECTED_PRIOR_ZERO_ADDRESS:
        raise RuntimeError(
            "prior top3 zero-address recovery set drifted: "
            f"expected={sorted(EXPECTED_PRIOR_ZERO_ADDRESS)}, observed={sorted(invalid)}"
        )

    candidates_payload: dict[str, list[dict[str, Any]]] = {}
    chosen_payload: dict[str, list[dict[str, Any]]] = {}
    for building_id in ALL_TARGETS:
        chosen_stems = {row.view_stem for row in selected[building_id]}
        candidates_payload[building_id] = [
            {
                "candidate_rank": rank,
                "view": row.view,
                "view_stem": row.view_stem,
                "dataset_index": row.dataset_index,
                "address_pixel_count": row.address_pixel_count,
                "chosen": row.view_stem in chosen_stems,
            }
            for rank, row in enumerate(ranked_candidates[building_id], start=1)
        ]
        chosen_payload[building_id] = [
            {
                "chosen_rank": rank,
                "view": row.view,
                "view_stem": row.view_stem,
                "dataset_index": row.dataset_index,
                "address_pixel_count": row.address_pixel_count,
            }
            for rank, row in enumerate(selected[building_id], start=1)
        ]
    return {
        "scope": VIEW_SELECTION_SCOPE,
        "rule": (
            "all train-split views with committed oracle cache target address pixels >0; "
            "sort address_pixel_count desc, view_stem asc; choose first 3"
        ),
        "checkpoint_or_gpu_result_consulted_for_selection": False,
        "all_visible_candidates": candidates_payload,
        "chosen": chosen_payload,
        "preflight_recovery": {
            "prior_scope": PRIOR_VIEW_SELECTION_SCOPE,
            "prior_source": rel(PRIOR_FIXED_VIEW_AUDIT),
            "prior_source_sha256": sha256_file(PRIOR_FIXED_VIEW_AUDIT),
            "detected_stage": "CPU preflight before checkpoint load or GPU render",
            "reason": "prior reference-area top3 contained committed oracle-cache zero-address views",
            "prior_selected": prior_selected,
            "prior_zero_address": [
                row for row in prior_selected if not row["eligible_positive_train_address"]
            ],
            "recovery_decision_used_checkpoint_or_gpu_results": False,
        },
    }


def checkpoint_path(run_name: str, step: int) -> Path:
    if run_name not in FULL_RUNS or step not in CHECKPOINT_STEPS:
        raise RuntimeError(f"checkpoint outside locked pairing cells: {run_name}/{step}")
    if step == 30000:
        return CKPT_ROOT / run_name / "ckpt/final.pt"
    return CKPT_ROOT / run_name / "ckpt" / f"step_{step:06d}.pt"


def load_frozen_checkpoint(
    path: Path,
    *,
    expected_step: int,
    sh_degree: int,
    device: str,
) -> tuple[FrozenCheckpointModel, str]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise FileNotFoundError(path)
    digest = sha256_file(path)
    payload = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(payload, dict) or not isinstance(payload.get("state_dict"), dict):
        raise RuntimeError(f"checkpoint payload contract failed: {rel(path)}")
    if int(payload.get("it", -1)) != int(expected_step):
        raise RuntimeError(
            f"checkpoint iteration mismatch for {rel(path)}: "
            f"expected={expected_step}, observed={payload.get('it')}"
        )
    model = FrozenCheckpointModel(
        payload["state_dict"],
        sh_degree=sh_degree,
        device=device,
    )
    model.assert_frozen()
    return model, digest


def weighted_region_plane_loss(rows: Sequence[Mapping[str, Any]]) -> float | None:
    numerator = 0.0
    denominator = 0
    for row in rows:
        value = row.get("plane_loss")
        count = int(row.get("plane_valid_pixel_count", 0) or 0)
        if value in {None, ""} or count <= 0:
            continue
        number = float(value)
        if not math.isfinite(number):
            continue
        numerator += number * count
        denominator += count
    return numerator / denominator if denominator else None


def compute_semdepth_gradient(
    *,
    weighted_semdepth: torch.Tensor,
    depth_leaf: torch.Tensor,
) -> torch.Tensor:
    """Differentiate once per rendered view and return an immutable gradient.

    One selected view may contain several target buildings.  Computing this
    once avoids repeated traversal of the same freed autograd graph and makes
    all building-local measurements share exactly the same view gradient.
    """

    if not depth_leaf.is_leaf or not depth_leaf.requires_grad:
        raise ValueError("depth_leaf must be a detached gradient-enabled leaf")
    gradient = None
    if weighted_semdepth.requires_grad:
        gradient = torch.autograd.grad(
            weighted_semdepth,
            depth_leaf,
            retain_graph=False,
            create_graph=False,
            allow_unused=True,
        )[0]
    if gradient is None:
        gradient = torch.zeros_like(depth_leaf)
    return gradient.detach()


def measure_target_gradient(
    *,
    gradient: torch.Tensor,
    result: Mapping[str, Any],
    building_id: str,
) -> dict[str, Any]:
    """Measure one building union without touching model or optimizer state."""

    if gradient.requires_grad:
        raise ValueError("gradient measurement must be detached")
    region_ids = result.get("region_ids")
    cutline_mask = result.get("cutline_mask")
    if not torch.is_tensor(region_ids) or not torch.is_tensor(cutline_mask):
        raise RuntimeError("semantic result lacks region address tensors")
    rows = [
        row
        for row in list(result.get("region_rows") or [])
        if short_id(row.get("building_id")) == building_id
    ]
    if not rows:
        raise RuntimeError(f"selected fixed view lost target region {building_id}")
    target_ids = sorted({int(row["region_id"]) for row in rows})
    mask = torch.zeros_like(region_ids, dtype=torch.bool)
    for rid in target_ids:
        mask |= region_ids == rid
    mask &= ~cutline_mask.bool()
    address_count = int(mask.sum().detach().cpu().item())
    if address_count <= 0:
        raise RuntimeError(f"selected fixed view has zero target address pixels: {building_id}")

    if gradient.shape != region_ids.shape:
        raise RuntimeError(
            f"gradient/address shape mismatch: {tuple(gradient.shape)} vs {tuple(region_ids.shape)}"
        )
    total_norm = float(gradient.norm().cpu().item())
    target_values = gradient[mask]
    target_norm = float(target_values.norm().cpu().item())
    nonzero = int((target_values != 0).sum().cpu().item())
    render_valid = sum(int(row.get("render_valid_pixel_count", 0) or 0) for row in rows)
    depth_anchor = sum(int(row.get("depth_anchor_pixel_count", 0) or 0) for row in rows)
    plane_valid = sum(int(row.get("plane_valid_pixel_count", 0) or 0) for row in rows)
    return {
        "region_count": len(target_ids),
        "region_ids": ";".join(str(value) for value in target_ids),
        "address_pixel_count": address_count,
        "alpha_valid_pixel_count": render_valid,
        "alpha_valid_fraction": render_valid / address_count,
        "depth_anchor_pixel_count": depth_anchor,
        "depth_anchor_fraction": depth_anchor / address_count,
        "plane_valid_pixel_count": plane_valid,
        "plane_residual_huber_mean": weighted_region_plane_loss(rows),
        "semdepth_depth_grad_norm": target_norm,
        "semdepth_depth_grad_rms": target_norm / math.sqrt(address_count),
        "semdepth_depth_grad_norm_share": target_norm / total_norm if total_norm > 0 else 0.0,
        "semdepth_depth_grad_nonzero_pixel_count": nonzero,
        "semdepth_depth_grad_nonzero_fraction": nonzero / address_count,
        "view_semdepth_depth_grad_norm": total_norm,
    }


def optional_median(rows: Sequence[Mapping[str, Any]], field: str) -> float | None:
    values: list[float] = []
    for row in rows:
        value = row.get(field)
        if value in {None, ""}:
            continue
        parsed = float(value)
        if math.isfinite(parsed):
            values.append(parsed)
    return float(np.median(values)) if values else None


MEDIAN_FIELDS = (
    "address_pixel_count",
    "alpha_valid_pixel_count",
    "alpha_valid_fraction",
    "depth_anchor_pixel_count",
    "depth_anchor_fraction",
    "plane_valid_pixel_count",
    "plane_residual_huber_mean",
    "semdepth_depth_grad_norm",
    "semdepth_depth_grad_rms",
    "semdepth_depth_grad_norm_share",
    "semdepth_depth_grad_nonzero_pixel_count",
    "semdepth_depth_grad_nonzero_fraction",
    "view_semdepth_depth_grad_norm",
)


def build_median_rows(view_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in view_rows:
        grouped[(str(row["run_name"]), int(row["step"]), str(row["building_id"]))].append(row)
    expected = {
        (run_name, step, building_id)
        for run_name in FULL_RUNS
        for step in CHECKPOINT_STEPS
        for building_id in ALL_TARGETS
    }
    if set(grouped) != expected:
        raise RuntimeError(
            "view-row target coverage mismatch: "
            f"missing={sorted(expected - set(grouped))[:5]}, "
            f"extra={sorted(set(grouped) - expected)[:5]}"
        )
    medians: list[dict[str, Any]] = []
    for key in sorted(grouped, key=lambda item: (FULL_RUNS.index(item[0]), item[1], item[2])):
        run_name, step, building_id = key
        rows = grouped[key]
        unique_views = sorted({str(row["view_stem"]) for row in rows})
        if len(rows) < 3 or len(unique_views) < 3:
            raise RuntimeError(f"building median requires >=3 fixed views: {key}")
        role = "collapse" if building_id in COLLAPSE_TARGETS else "organization"
        medians.append(
            {
                "record_type": f"{role}_building_median",
                "claim_scope": CLAIM_SCOPE,
                "measurement_mode": MEASUREMENT_MODE,
                "plane_fit_scope": PLANE_FIT_SCOPE,
                "view_selection_scope": VIEW_SELECTION_SCOPE,
                "arm": "s3a",
                "replicate": RUN_TO_REPLICATE[run_name],
                "run_name": run_name,
                "step": step,
                "building_id": building_id,
                "target_role": role,
                "selected_view_count": len(unique_views),
                "selected_views": ";".join(unique_views),
                **{field: optional_median(rows, field) for field in MEDIAN_FIELDS},
            }
        )
    return medians


def timeline_lookup(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, int, str], Mapping[str, Any]]:
    expected = {
        (run_name, step, f"DEBY_LOD2_{building_id}")
        for run_name in FULL_RUNS
        for step in CHECKPOINT_STEPS
        for building_id in COLLAPSE_TARGETS
    }
    selected: dict[tuple[str, int, str], Mapping[str, Any]] = {}
    for row in rows:
        run_name = str(row.get("run_name", ""))
        building_id = str(row.get("building_id", ""))
        try:
            step = int(row.get("step", -1))
        except (TypeError, ValueError):
            continue
        key = (run_name, step, building_id)
        if key not in expected:
            continue
        if key in selected:
            raise RuntimeError(f"duplicate timeline key for pairing: {key}")
        selected[key] = row
    if set(selected) != expected:
        raise RuntimeError(
            "timeline lacks locked collapse pairing rows: "
            f"missing={sorted(expected - set(selected))[:5]}"
        )
    return selected


def build_pair_rows(
    median_rows: Sequence[Mapping[str, Any]],
    timeline_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    medians = {
        (str(row["run_name"]), int(row["step"]), str(row["building_id"])): row
        for row in median_rows
        if row.get("record_type") == "collapse_building_median"
    }
    expected = {
        (run_name, step, building_id)
        for run_name in FULL_RUNS
        for step in CHECKPOINT_STEPS
        for building_id in COLLAPSE_TARGETS
    }
    if set(medians) != expected:
        raise RuntimeError("collapse median coverage is not exact 2x6x3")
    timeline = timeline_lookup(timeline_rows)
    pairs: list[dict[str, Any]] = []
    for run_name, step, building_id in sorted(
        expected,
        key=lambda item: (FULL_RUNS.index(item[0]), item[1], COLLAPSE_TARGETS.index(item[2])),
    ):
        median = medians[(run_name, step, building_id)]
        material = timeline[(run_name, step, f"DEBY_LOD2_{building_id}")]
        pairs.append(
            {
                **dict(median),
                "record_type": "collapse_timeline_pair",
                "timeline_ckpt": material.get("ckpt", ""),
                "n_gaussians_in_footprint": material.get("n_gaussians_in_footprint", ""),
                "z_p50": material.get("z_p50", ""),
                "z_std": material.get("z_std", ""),
                "opacity_p50": material.get("opacity_p50", ""),
                "count_definition": material.get("count_definition", ""),
                "pairing_rule": (
                    "same run+checkpoint+building: exact-footprint material count paired with "
                    "fixed-view building-median posthoc semantic-depth gradient potential"
                ),
            }
        )
    if len(pairs) != 36:
        raise RuntimeError(f"collapse timeline pairing must emit 36 rows, got {len(pairs)}")
    return pairs


def _input_hashes_for_selected_views(
    dataset: ColmapDataset,
    selected: Mapping[str, Sequence[ViewCandidate]],
) -> dict[str, str]:
    indices = sorted({row.dataset_index for rows in selected.values() for row in rows})
    paths: set[Path] = set()
    for index in indices:
        frame = dataset.frames[index]
        paths.add(frame.image_path)
        if frame.depth_path is not None:
            paths.add(frame.depth_path)
        semantic = dataset.semantic_dir / f"{Path(frame.name).stem}.png"
        paths.add(semantic)
    sparse_root = dataset.root / "sparse"
    if (sparse_root / "0" / "cameras.bin").is_file():
        sparse_root = sparse_root / "0"
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        paths.add(sparse_root / name)
    missing = [rel(path) for path in sorted(paths) if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"selected-view inputs missing: {missing[:5]}")
    return {rel(path): sha256_file(path) for path in sorted(paths)}


def _union_fields(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    preferred = [
        "record_type",
        "claim_scope",
        "measurement_mode",
        "plane_fit_scope",
        "arm",
        "replicate",
        "run_name",
        "step",
        "building_id",
        "target_role",
        "view",
        "view_stem",
        "view_rank",
    ]
    fields = list(preferred)
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    return fields


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = _union_fields(rows)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def plot_pairing(pair_rows: Sequence[Mapping[str, Any]], output: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(3, 1, figsize=(9.5, 10.2), constrained_layout=True)
    colors = {"r1": "#2F6B4F", "r2": "#496F9B"}
    for axis, building_id in zip(axes, COLLAPSE_TARGETS):
        gradient_axis = axis.twinx()
        for run_name in FULL_RUNS:
            replicate = RUN_TO_REPLICATE[run_name]
            part = sorted(
                [
                    row for row in pair_rows
                    if row["run_name"] == run_name and row["building_id"] == building_id
                ],
                key=lambda row: int(row["step"]),
            )
            x = [int(row["step"]) / 1000.0 for row in part]
            counts = [int(row["n_gaussians_in_footprint"]) for row in part]
            gradients = [float(row["semdepth_depth_grad_norm"]) for row in part]
            axis.plot(x, counts, marker="o", color=colors[replicate], label=f"{replicate} material")
            gradient_axis.plot(
                x,
                gradients,
                marker="x",
                linestyle="--",
                color=colors[replicate],
                alpha=0.75,
                label=f"{replicate} gradient potential",
            )
        axis.set_yscale("symlog", linthresh=10)
        gradient_axis.set_yscale("symlog", linthresh=1e-8)
        axis.set_ylabel("Gaussians in footprint")
        gradient_axis.set_ylabel("Median depth-gradient norm")
        axis.set_title(f"Collapse survival pairing: {building_id}")
        axis.grid(alpha=0.25)
        handles, labels = axis.get_legend_handles_labels()
        handles2, labels2 = gradient_axis.get_legend_handles_labels()
        axis.legend(handles + handles2, labels + labels2, fontsize=7, ncol=2)
    axes[-1].set_xlabel("Checkpoint (k steps)")
    figure.suptitle("S3-A posthoc checkpoint gradient potential (not online gradient)", fontsize=11)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def plot_organization(median_rows: Sequence[Mapping[str, Any]], output: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(8.6, 4.6), constrained_layout=True)
    for run_name in FULL_RUNS:
        part = sorted(
            [
                row for row in median_rows
                if row.get("record_type") == "organization_building_median"
                and row["run_name"] == run_name
            ],
            key=lambda row: int(row["step"]),
        )
        x = [int(row["step"]) / 1000.0 for row in part]
        values = [row.get("plane_residual_huber_mean") for row in part]
        valid = [(xv, float(value)) for xv, value in zip(x, values) if value not in {None, ""}]
        if valid:
            axis.plot(
                [item[0] for item in valid],
                [item[1] for item in valid],
                marker="o",
                label=f"{RUN_TO_REPLICATE[run_name]} 4907199",
            )
    axis.set_xlabel("Checkpoint (k steps)")
    axis.set_ylabel("Median per-view plane residual (Huber mean)")
    axis.set_title("4907199 organization audit: posthoc fitted-plane residual")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.savefig(output, dpi=180)
    plt.close(figure)


def _geometry_from_config(config: Mapping[str, Any], cache: SemanticRegionCache) -> SemanticGuidedGeometry:
    return SemanticGuidedGeometry(
        cache,
        roof_class=int(config.get("semantic_roof_class", 1)),
        alpha_threshold=float(config["semantic_alpha_threshold"]),
        plane_min_pixels=int(config["semantic_plane_min_pixels"]),
        plane_refit_every=int(config["semantic_plane_refit_every"]),
        huber_delta=float(config["semantic_huber_delta"]),
        plane_irls_iterations=int(config["semantic_plane_irls_iterations"]),
        boundary_kernel_size=int(config["semantic_boundary_band_px"]),
    )


def run(args: argparse.Namespace) -> None:
    if os.environ.get("E5_S3A_GRADIENT_PAIRING_CONTAINER") != "1":
        raise RuntimeError("checkpoint gradient pairing must run through the Docker launcher")
    if int(args.views_per_building) != VIEWS_PER_BUILDING:
        raise RuntimeError(f"locked pairing uses exactly {VIEWS_PER_BUILDING} fixed views")
    outputs = [OUTPUT_CSV, FIG_SURVIVAL, FIG_ORGANIZATION, OUTPUT_MANIFEST]
    existing = [rel(path) for path in outputs if path.exists()]
    if existing and not args.force and not args.preflight_only:
        raise RuntimeError(f"pairing outputs already exist; use --force after review: {existing}")

    implementation_paths = [
        SCRIPT_PATH,
        DOWNSTREAM_PATH,
        SEMANTIC_LOSS_PATH,
        TRAIN_PATH,
        RENDERER_PATH,
        DATALOADER_PATH,
    ]
    config_paths = [CONFIG_DIR / f"{run_name}.yaml" for run_name in FULL_RUNS]
    if args.preflight_only:
        current_head = require_committed_clean(
            [PRIOR_FIXED_VIEW_AUDIT, CACHE_INVENTORY, *config_paths]
        )
    else:
        current_head = require_committed_clean(
            implementation_paths + [PRIOR_FIXED_VIEW_AUDIT, CACHE_INVENTORY, *config_paths]
        )
    prior_fixed_view_audit_sha_before = sha256_file(PRIOR_FIXED_VIEW_AUDIT)

    configs: dict[str, dict[str, Any]] = {}
    provenance: dict[str, Any] = {
        "claim_scope": CLAIM_SCOPE,
        "measurement_mode": MEASUREMENT_MODE,
        "plane_fit_scope": PLANE_FIT_SCOPE,
        "view_selection_scope": VIEW_SELECTION_SCOPE,
        "current_git_head": current_head,
        "implementation_hashes": {rel(path): sha256_file(path) for path in implementation_paths},
        "runs": {},
    }
    launch_heads: set[str] = set()
    expected_cache_aggregates: set[str] = set()
    expected_cache_inventories: set[str] = set()
    for run_name in FULL_RUNS:
        config_path = CONFIG_DIR / f"{run_name}.yaml"
        versions_path = RUN_DIR / "versions" / f"{run_name}.txt"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        versions = parse_versions(versions_path)
        validate_config(config, run_name)
        if versions.get("config") != rel(config_path):
            raise RuntimeError(f"launch versions bind a different config for {run_name}")
        if versions.get("config_sha256") != sha256_file(config_path):
            raise RuntimeError(f"config hash differs from launch ledger for {run_name}")
        if versions.get("semantic_loss_py_sha256") != sha256_file(SEMANTIC_LOSS_PATH):
            raise RuntimeError(f"semantic loss differs from launch ledger for {run_name}")
        if versions.get("train_py_sha256") != sha256_file(TRAIN_PATH):
            raise RuntimeError(f"train.py differs from launch ledger for {run_name}")
        launch_head = versions.get("git_head", "")
        if not launch_head:
            raise RuntimeError(f"launch git head missing for {run_name}")
        for path in (RENDERER_PATH, DATALOADER_PATH):
            if git_blob_sha256(launch_head, path) != sha256_file(path):
                raise RuntimeError(f"{rel(path)} differs from launch-time implementation")
        effective_path = CKPT_ROOT / run_name / "effective_config.json"
        effective_sha = validate_effective_config(config, effective_path)
        launch_heads.add(launch_head)
        expected_cache_aggregates.add(versions.get("cache_aggregate_sha256", ""))
        expected_cache_inventories.add(versions.get("cache_inventory_sha256", ""))
        configs[run_name] = config
        provenance["runs"][run_name] = {
            "launch_versions": rel(versions_path),
            "launch_versions_sha256": sha256_file(versions_path),
            "launch_git_head": launch_head,
            "config": rel(config_path),
            "config_sha256": sha256_file(config_path),
            "effective_config": rel(effective_path),
            "effective_config_sha256": effective_sha,
        }
    if len(launch_heads) != 1:
        raise RuntimeError(f"r1/r2 launch heads differ: {sorted(launch_heads)}")
    if len(expected_cache_aggregates) != 1 or "" in expected_cache_aggregates:
        raise RuntimeError("r1/r2 cache aggregate provenance is missing or inconsistent")
    if len(expected_cache_inventories) != 1 or "" in expected_cache_inventories:
        raise RuntimeError("r1/r2 cache inventory provenance is missing or inconsistent")

    config0 = configs[FULL_RUNS[0]]
    cache_root = repo_path(config0["semantic_region_cache"])
    data_root = repo_path(config0["data_root"])
    semantic_root = data_root / "semantic"
    cache_provenance = validate_cache_hashes(
        cache_root=cache_root,
        semantic_root=semantic_root,
        expected_aggregate=next(iter(expected_cache_aggregates)),
        expected_inventory_sha=next(iter(expected_cache_inventories)),
    )
    provenance.update(cache_provenance)

    dataset = ColmapDataset(
        root=data_root,
        downscale=float(config0.get("downscale", 1.0)),
        load_depth=True,
        load_normal=False,
        load_semantic=True,
        depth_scale=float(config0.get("depth_scale", 1.0)),
    )
    if len(dataset) != 428:
        raise RuntimeError(f"locked C001 dataset must contain 428 views, got {len(dataset)}")
    cache = SemanticRegionCache(
        cache_root,
        expected_cutline_half_width_px=int(config0["semantic_cutline_half_width_px"]),
        expected_source_component_min_pixels=int(config0["semantic_source_component_min_pixels"]),
        expected_connectivity=int(config0["semantic_component_connectivity"]),
        expected_footprint_buffer_m=float(config0["semantic_footprint_buffer_m"]),
    )
    selected, ranked_candidates = select_oracle_cache_fixed_views(
        dataset,
        cache,
        views_per_building=args.views_per_building,
    )
    selection_provenance = build_view_selection_provenance(
        selected=selected,
        ranked_candidates=ranked_candidates,
        prior_audit_rows=read_csv(PRIOR_FIXED_VIEW_AUDIT),
    )
    selected_input_hashes = _input_hashes_for_selected_views(dataset, selected)
    provenance["view_selection"] = selection_provenance
    provenance["selected_view_input_hashes"] = selected_input_hashes
    provenance["selected_view_input_aggregate_sha256"] = sha256_json(selected_input_hashes)
    provenance["prior_fixed_view_audit"] = rel(PRIOR_FIXED_VIEW_AUDIT)
    provenance["prior_fixed_view_audit_sha256"] = prior_fixed_view_audit_sha_before

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "pass",
                    "mode": "CPU selection preflight only",
                    "view_selection_scope": VIEW_SELECTION_SCOPE,
                    "chosen": selection_provenance["chosen"],
                    "visible_candidate_counts": {
                        building_id: len(rows)
                        for building_id, rows in ranked_candidates.items()
                    },
                    "preflight_recovery": selection_provenance["preflight_recovery"],
                    "checkpoint_loaded": False,
                    "gpu_rendered": False,
                    "measurement_outputs_written": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return

    if not torch.cuda.is_available():
        raise RuntimeError("checkpoint gradient pairing requires a CUDA-visible gsplat device")

    timeline_rows = read_csv(TIMELINE_CSV)
    timeline_sha_before = sha256_file(TIMELINE_CSV)
    timeline_lookup(timeline_rows)
    checkpoint_hashes_before = {
        rel(checkpoint_path(run_name, step)): sha256_file(checkpoint_path(run_name, step))
        for run_name in FULL_RUNS
        for step in CHECKPOINT_STEPS
    }

    from src.stage2.renderer import render

    device = "cuda"
    view_rows: list[dict[str, Any]] = []
    selected_by_index: dict[int, list[tuple[str, int, ViewCandidate]]] = defaultdict(list)
    for building_id, candidates in selected.items():
        for rank, candidate in enumerate(candidates, start=1):
            selected_by_index[candidate.dataset_index].append((building_id, rank, candidate))

    for run_name in FULL_RUNS:
        config = configs[run_name]
        w_smooth = float(config["w_semdepth_smooth"])
        w_plane = float(config["w_semdepth_plane"])
        for step in CHECKPOINT_STEPS:
            path = checkpoint_path(run_name, step)
            model, checkpoint_sha = load_frozen_checkpoint(
                path,
                expected_step=step,
                sh_degree=int(config.get("sh_degree", 3)),
                device=device,
            )
            signature_before = model.state_signature()
            geometry = _geometry_from_config(config, cache)
            for dataset_index in sorted(selected_by_index):
                batch = dataset[dataset_index]
                if "semantic" not in batch or "depth_mask" not in batch:
                    raise RuntimeError(f"selected view lacks semantic/depth mask: {batch['name']}")
                with torch.no_grad():
                    rendered = render(
                        model,
                        batch["w2c"].to(device),
                        batch["K"].to(device),
                        int(batch["width"]),
                        int(batch["height"]),
                        sh_degree=model.active_sh_degree,
                        render_mode="RGB+ED",
                    )
                depth_leaf = rendered["depth"].detach().requires_grad_(True)
                alpha = rendered["alpha"].detach()
                result = geometry(
                    iteration=step,
                    view_key=str(batch["name"]),
                    depth=depth_leaf,
                    alpha=alpha,
                    K=batch["K"].to(device),
                    semantic=batch["semantic"].to(device),
                    normal_render=rendered["normal_render"].detach(),
                    normal_target=None,
                    normal_mask=None,
                    depth_anchor_mask=batch["depth_mask"].to(device),
                    enable_semdepth=True,
                    enable_boundary_normal=False,
                )
                weighted_semdepth = w_smooth * result["smooth"] + w_plane * result["plane"]
                gradient = compute_semdepth_gradient(
                    weighted_semdepth=weighted_semdepth,
                    depth_leaf=depth_leaf,
                )
                for building_id, rank, candidate in selected_by_index[dataset_index]:
                    metrics = measure_target_gradient(
                        gradient=gradient,
                        result=result,
                        building_id=building_id,
                    )
                    view_rows.append(
                        {
                            "record_type": "fixed_view",
                            "claim_scope": CLAIM_SCOPE,
                            "measurement_mode": MEASUREMENT_MODE,
                            "plane_fit_scope": PLANE_FIT_SCOPE,
                            "arm": "s3a",
                            "replicate": RUN_TO_REPLICATE[run_name],
                            "run_name": run_name,
                            "step": step,
                            "checkpoint": rel(path),
                            "checkpoint_sha256": checkpoint_sha,
                            "building_id": building_id,
                            "target_role": (
                                "collapse" if building_id in COLLAPSE_TARGETS else "organization"
                            ),
                            "view": candidate.view,
                            "view_stem": candidate.view_stem,
                            "view_rank": rank,
                            "view_selection_scope": VIEW_SELECTION_SCOPE,
                            "selection_address_pixel_count": candidate.address_pixel_count,
                            "weight_smooth": w_smooth,
                            "weight_plane": w_plane,
                            "loss_smooth_view": float(result["smooth"].detach().cpu().item()),
                            "loss_plane_view": float(result["plane"].detach().cpu().item()),
                            "loss_semdepth_weighted_view": float(
                                weighted_semdepth.detach().cpu().item()
                            ),
                            **metrics,
                        }
                    )
                del depth_leaf, rendered, result, weighted_semdepth, gradient, batch
            model.assert_frozen()
            if model.state_signature() != signature_before:
                raise RuntimeError(f"frozen checkpoint tensors changed in memory: {run_name}/{step}")
            del model, geometry
            torch.cuda.empty_cache()

    median_rows = build_median_rows(view_rows)
    pair_rows = build_pair_rows(median_rows, timeline_rows)
    all_rows = view_rows + median_rows + pair_rows

    checkpoint_hashes_after = {
        path: sha256_file(REPO / path) for path in checkpoint_hashes_before
    }
    if checkpoint_hashes_after != checkpoint_hashes_before:
        raise RuntimeError("one or more checkpoint files changed during read-only pairing")
    if sha256_file(TIMELINE_CSV) != timeline_sha_before:
        raise RuntimeError("timeline CSV changed during read-only pairing")
    if sha256_file(PRIOR_FIXED_VIEW_AUDIT) != prior_fixed_view_audit_sha_before:
        raise RuntimeError("prior fixed-view audit changed during read-only pairing")
    selected_input_hashes_after = _input_hashes_for_selected_views(dataset, selected)
    if selected_input_hashes_after != selected_input_hashes:
        raise RuntimeError("selected-view inputs changed during read-only pairing")
    cache_provenance_after = validate_cache_hashes(
        cache_root=cache_root,
        semantic_root=semantic_root,
        expected_aggregate=next(iter(expected_cache_aggregates)),
        expected_inventory_sha=next(iter(expected_cache_inventories)),
    )
    if cache_provenance_after != cache_provenance:
        raise RuntimeError("semantic-region cache provenance changed during pairing")

    provenance.update(
        {
            "checkpoint_hashes": checkpoint_hashes_before,
            "timeline": rel(TIMELINE_CSV),
            "timeline_sha256": timeline_sha_before,
            "views_per_building": VIEWS_PER_BUILDING,
            "collapse_targets": list(COLLAPSE_TARGETS),
            "organization_targets": list(ORGANIZATION_TARGETS),
            "steps": list(CHECKPOINT_STEPS),
            "view_rows": len(view_rows),
            "median_rows": len(median_rows),
            "collapse_pair_rows": len(pair_rows),
            "outputs": [rel(path) for path in outputs],
            "checkpoint_or_input_mutated": False,
            "optimizer_created": False,
            "tensor_backward_called": False,
        }
    )

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="s3-gradient-pairing-", dir=RUN_DIR) as tmp:
        stage = Path(tmp)
        staged_csv = stage / OUTPUT_CSV.name
        staged_survival = stage / FIG_SURVIVAL.name
        staged_organization = stage / FIG_ORGANIZATION.name
        staged_manifest = stage / OUTPUT_MANIFEST.name
        write_csv(staged_csv, all_rows)
        plot_pairing(pair_rows, staged_survival)
        plot_organization(median_rows, staged_organization)
        staged_manifest.write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for path in (staged_csv, staged_survival, staged_organization, staged_manifest):
            if not path.is_file() or path.stat().st_size <= 0:
                raise RuntimeError(f"staged pairing output missing/empty: {path.name}")
        for target in outputs:
            target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged_csv, OUTPUT_CSV)
        os.replace(staged_survival, FIG_SURVIVAL)
        os.replace(staged_organization, FIG_ORGANIZATION)
        os.replace(staged_manifest, OUTPUT_MANIFEST)

    print(
        json.dumps(
            {
                "checkpoint_gradient_pairing": rel(OUTPUT_CSV),
                "view_rows": len(view_rows),
                "median_rows": len(median_rows),
                "collapse_pair_rows": len(pair_rows),
                "claim_scope": CLAIM_SCOPE,
                "checkpoint_or_input_mutated": False,
            },
            ensure_ascii=False,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--views-per-building", type=int, default=VIEWS_PER_BUILDING)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()

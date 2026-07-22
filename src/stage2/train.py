"""Stage-2 vanilla 2DGS training loop.

Usage (inside container):
    python -m src.stage2.train --config configs/vanilla.yaml

The config file specifies data root, output dir, max iterations, loss weights,
and densification schedule. This Phase-1 Step-1-1 trainer uses only the
data-fitting losses: L_photo, L_depth, L_normal, L_nc.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import numpy as np
import torch
import yaml
from torch.utils.tensorboard import SummaryWriter
from tqdm import tqdm

from .checkpoint import (
    discover_latest_checkpoint,
    restore_rng_state,
    restore_training_checkpoint,
    save_training_checkpoint,
)
from .dataloader import ColmapDataset, resolve_view_roles
from .densification import build_optimizers, build_param_dict, build_strategy
from .geometry_partition import assign_partition_ids, load_xy_partitions
from .grouping import (
    group_primitives,
    group_primitives_g2,
    group_primitives_g2_partitioned,
)
from .loss import data_fitting as L
from .loss.mutual import l_mutual
from .loss.multiview import l_multiview_consistency
from .loss.planarity import (
    audit_2dgs_flattening_invariant,
    local_rendered_depth_coplanarity,
)
from .loss.semantic_guided import SemanticGuidedGeometry, SemanticRegionCache
from .loss.structure import l_structure
from .model import GaussianModel2D
from .mono_normal_gate import build_mono_normal_gate, l_auxiliary_mono_normal
from .pilot_loss_audit import (
    FULL_STATE_CSV_PATHS as PILOT_FULL_STATE_CSV_PATHS,
    append_detail_rows as append_pilot_loss_detail_rows,
    append_loss_share_rows as append_pilot_loss_share_rows,
    append_plane_photo_ratio as append_pilot_plane_photo_ratio,
    masked_normal_consistency as pilot_masked_normal_consistency,
    public_normal_term as pilot_public_normal_term,
    structure_terms_in_scope as pilot_structure_terms_in_scope,
)
from .plane_guided_init import (
    PlaneGuidedInitConfig,
    build_plane_guided_initialization,
    verify_resume_initialization_audit,
)
from .renderer import render
from .seed_control import apply_mvs_seed_init_opacity
from .train_resume import (
    FULL_STATE_BINDING_EXCLUDED_CONFIG_KEYS,
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


def _build_mvc_neighbors(frames, train_idx, k, max_angle_deg, min_baseline):
    """(Phase B / B1) Per-view covisible-neighbor index for L_mvc, from poses only.

    A neighbor j of view i is a training frame whose viewing direction is within
    `max_angle_deg` of i's (so they see roughly the same surface) and whose camera
    centre is at least `min_baseline` away (so the depth-consistency signal has a
    non-trivial parallax). Returns {i: [j,...]} (up to k nearest-by-baseline). If no
    candidate satisfies the gates, falls back to the k nearest cameras by centre
    distance (still a valid consistency pair). All indices are restricted to
    train_idx so the every-10th test frames never leak into the consistency term.
    """
    idxs = list(train_idx)
    C, D = {}, {}
    for i in idxs:
        fr = frames[i]
        R = np.asarray(fr.R, dtype=np.float64)
        t = np.asarray(fr.t, dtype=np.float64).reshape(3)
        C[i] = -R.T @ t                                  # camera centre (world)
        d = R.T @ np.array([0.0, 0.0, 1.0])              # viewing direction (world)
        D[i] = d / (np.linalg.norm(d) + 1e-9)
    cos_thr = float(np.cos(np.deg2rad(max_angle_deg)))
    nbr = {}
    for i in idxs:
        cand = []
        for j in idxs:
            if j == i:
                continue
            if float(D[i] @ D[j]) < cos_thr:
                continue
            base = float(np.linalg.norm(C[i] - C[j]))
            if base < min_baseline:
                continue
            cand.append((base, j))
        cand.sort()
        nbr[i] = [j for _, j in cand[:k]]
        if not nbr[i]:
            allj = sorted((float(np.linalg.norm(C[i] - C[j])), j) for j in idxs if j != i)
            nbr[i] = [j for _, j in allj[:k]]
    return nbr


def _load_footprint_boxes_local(geojson_path, world_offset, building_ids=None):
    """(P2 C seed-survival) {bid: (x0,y0,x1,y1)} GS-LOCAL bboxes from a UTM footprint geojson."""
    if not geojson_path:
        return None
    feats = json.loads(Path(geojson_path).read_text())["features"]
    wx, wy = float(world_offset[0]), float(world_offset[1])
    want = set(building_ids) if building_ids else None
    boxes = {}
    for f in feats:
        bid = f["properties"].get("building_id")
        if want is not None and bid not in want:
            continue
        g = f["geometry"]
        r = np.asarray(g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])
        x, y = r[:, 0] - wx, r[:, 1] - wy
        boxes[bid] = (float(x.min()), float(y.min()), float(x.max()), float(y.max()))
    return boxes


def _log_seed_survival(it, model, is_seed, boxes, writer):
    """(P2 C) log surviving seed count (+ per-building footprint seed count / median opacity)."""
    with torch.no_grad():
        n_seed = int(is_seed.sum().item())
        msg = f"[seed-survival] it={it} N={model.num_points} seeds={n_seed}"
        writer.add_scalar("seed/surviving", n_seed, it)
        if boxes:
            m = model.means.detach(); op = model.opacities.detach().flatten()
            for bid, (x0, y0, x1, y1) in boxes.items():
                inb = (m[:, 0] >= x0) & (m[:, 0] <= x1) & (m[:, 1] >= y0) & (m[:, 1] <= y1) & is_seed
                c = int(inb.sum().item())
                medop = float(op[inb].median().item()) if c > 0 else 0.0
                short = bid.replace("DEBY_LOD2_", "")
                msg += f" | {short}={c}(op{medop:.2f})"
                writer.add_scalar(f"seed/fp_{short}", c, it)
        print(msg, flush=True)


def _append_densify_audit(out_dir: Path, events: list[dict]) -> None:
    """Append recording-only per-footprint split/duplicate counts."""
    if not events:
        return
    audit_dir = out_dir / "audit"
    audit_dir.mkdir(exist_ok=True)
    path = audit_dir / "densify_events.csv"
    fields = ["iteration", "building_id", "duplicate_events", "split_events", "total_events"]
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if write_header:
            writer.writeheader()
        writer.writerows(events)


def _append_mono_target_audit(out_dir: Path, row: dict) -> None:
    audit_dir = out_dir / "audit"
    audit_dir.mkdir(exist_ok=True)
    with (audit_dir / "mono_target_regions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


# Map from gsplat strategy dict keys -> model attribute names
_STRATEGY_TO_MODEL = {
    "means": "means",
    "scales": "log_scales",
    "quats": "quats",
    "opacities": "opacities_raw",
    "sh0": "sh0",
    "shN": "shN",
    "sem_logits": "sem_logits",
}


def _sync_params_to_model(params: Dict[str, torch.nn.Parameter], model: GaussianModel2D):
    """After gsplat DefaultStrategy grow/prune, params dict entries may have been
    replaced with new nn.Parameters. Sync them back into the model so model.means etc.
    reflect the updated tensors."""
    for strategy_key, model_attr in _STRATEGY_TO_MODEL.items():
        p = params.get(strategy_key)
        if p is None:
            continue
        current = getattr(model, model_attr, None)
        if current is not p:
            setattr(model, model_attr, p)


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


_PILOT_ARMS = frozenset(
    {
        "01_surface",
        "02_photo_control",
        "03_plane_soft",
        "04a_plane_medium_vision",
        "04b_plane_medium_gt_upperbound",
    }
)
_PILOT_PHOTO_MASK_ARMS = _PILOT_ARMS - {"01_surface"}
_PILOT_MEDIUM_ARMS = frozenset(
    {"04a_plane_medium_vision", "04b_plane_medium_gt_upperbound"}
)
_PILOT_PLANE_INIT_CONFIG_KEYS = (
    "pilot_plane_init_stride_px",
    "pilot_plane_init_grid_offset_px",
    "pilot_plane_init_knn",
    "pilot_plane_init_tolerance_m",
    "pilot_plane_init_min_coverage",
    "pilot_plane_init_query_chunk_size",
)


def _require_finite_config_number(
    cfg: Dict[str, Any], key: str, *, positive: bool = False
) -> float:
    value = cfg.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"pilot config {key} must be an explicit numeric scalar")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"pilot config {key} must be finite")
    if positive and result <= 0.0:
        raise ValueError(f"pilot config {key} must be >0")
    return result


def _require_explicit_config_int(
    cfg: Dict[str, Any],
    key: str,
    *,
    minimum: int,
    maximum: Optional[int] = None,
) -> int:
    value = cfg.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"pilot config {key} must be an explicit integer")
    result = int(value)
    if result < minimum or (maximum is not None and result > maximum):
        upper = "" if maximum is None else f" and <={maximum}"
        raise ValueError(f"pilot config {key} must be >={minimum}{upper}")
    return result


def _pilot_plane_init_config(cfg: Dict[str, Any]) -> PlaneGuidedInitConfig:
    """Resolve only explicit, prelocked plane-guided initialization controls."""

    stride = _require_explicit_config_int(
        cfg, "pilot_plane_init_stride_px", minimum=1
    )
    offset = _require_explicit_config_int(
        cfg, "pilot_plane_init_grid_offset_px", minimum=0
    )
    if offset >= stride:
        raise ValueError(
            "pilot config pilot_plane_init_grid_offset_px must be < stride"
        )
    knn = _require_explicit_config_int(
        cfg, "pilot_plane_init_knn", minimum=1, maximum=64
    )
    tolerance = _require_finite_config_number(
        cfg, "pilot_plane_init_tolerance_m", positive=True
    )
    min_coverage = _require_finite_config_number(
        cfg, "pilot_plane_init_min_coverage", positive=True
    )
    if min_coverage > 1.0:
        raise ValueError("pilot_plane_init_min_coverage must be <=1")
    chunk_size = _require_explicit_config_int(
        cfg, "pilot_plane_init_query_chunk_size", minimum=1
    )
    return PlaneGuidedInitConfig(
        stride_px=stride,
        grid_offset_px=offset,
        knn=knn,
        tolerance_m=tolerance,
        min_coverage=min_coverage,
        query_chunk_size=chunk_size,
    )


def _pilot_plane_window_coplanarity(
    *,
    pilot_arm: str,
    depth: torch.Tensor,
    intrinsics: torch.Tensor,
    alpha: torch.Tensor,
    plane_region_mask: Optional[torch.Tensor],
    audit_mask: Optional[torch.Tensor],
    window_size: int,
    stride: int,
    min_points: int,
    alpha_threshold: float,
    max_depth_range: Optional[float],
    min_second_eigenvalue: float,
):
    """One local-window primitive for soft and both controlled medium arms."""

    if pilot_arm not in {"03_plane_soft", *_PILOT_MEDIUM_ARMS}:
        raise ValueError(f"pilot arm has no plane loss: {pilot_arm}")
    if pilot_arm in _PILOT_MEDIUM_ARMS:
        if plane_region_mask is None:
            raise RuntimeError(f"{pilot_arm} requires plane_region_mask")
        valid_mask = plane_region_mask.to(device=depth.device, dtype=torch.bool)
    else:
        if plane_region_mask is not None:
            raise RuntimeError("03_plane_soft must not receive a plane-region mask")
        valid_mask = None
    if audit_mask is not None:
        audit = audit_mask.to(device=depth.device, dtype=torch.bool)
        valid_mask = audit if valid_mask is None else valid_mask & audit
    return local_rendered_depth_coplanarity(
        depth,
        intrinsics,
        alpha=alpha,
        valid_mask=valid_mask,
        window_size=window_size,
        stride=stride,
        min_points=min_points,
        alpha_threshold=alpha_threshold,
        max_depth_range=max_depth_range,
        min_second_eigenvalue=min_second_eigenvalue,
    )


def _pilot_plane_init_start_mode(
    resume_request: Optional[str],
    *,
    fresh_audit_exists: bool,
    checkpoint_candidate_exists: bool,
) -> str:
    """Resolve the only safe action available before checkpoint discovery.

    ``auto`` with neither a checkpoint candidate nor a fresh audit is the
    supported first-run convenience path.  It initializes fresh before
    optimizers and is checked again after strict discovery.  Every other resume
    request is verify-only here, so a checkpoint cannot manufacture its missing
    historical initialization audit.
    """

    if resume_request is None:
        return "fresh"
    if (
        resume_request.lower() == "auto"
        and not fresh_audit_exists
        and not checkpoint_candidate_exists
    ):
        return "fresh_auto_candidate"
    return "resume_verify_only"


def _execute_pilot_plane_init_start_gate(
    *,
    model: GaussianModel2D,
    result: Any,
    mvs_seed_mask: np.ndarray,
    start_mode: str,
    fresh_audit_path: Path,
    resume_audit_path: Path,
) -> Optional[Path]:
    """Apply on a fresh scaffold or verify-only on a resume scaffold."""

    if start_mode == "resume_verify_only":
        verification = verify_resume_initialization_audit(
            fresh_audit_path,
            result,
        )
        atomic_write_json(resume_audit_path, verification)
        return resume_audit_path
    if start_mode not in {"fresh", "fresh_auto_candidate"}:
        raise ValueError(f"unsupported plane initialization start mode: {start_mode}")

    applied_count = model.initialize_normals_from_world(
        torch.from_numpy(result.normals_world_up),
        torch.from_numpy(mvs_seed_mask),
    )
    fresh_audit = {
        **result.audit,
        "application": {
            "mode": "fresh_start",
            "applied": True,
            "applied_model_row_count": int(applied_count),
            "selection": "dense_mvs_seed_rows_only",
            "performed_before_optimizer_creation": True,
            "unmatched_rows_initialized_to_positive_z": True,
        },
    }
    atomic_write_json(fresh_audit_path, fresh_audit)
    return None


def _validate_pilot_config_contract(
    cfg: Dict[str, Any], full_state: Dict[str, Any]
) -> Optional[str]:
    """Hard-fail first-wave forbidden combinations before dataset/model creation."""

    arm_value = cfg.get("pilot_arm")
    if arm_value is None:
        return None
    if not isinstance(arm_value, str) or arm_value not in _PILOT_ARMS:
        raise ValueError(f"pilot_arm must be one of {sorted(_PILOT_ARMS)}")
    arm = arm_value

    if int(cfg.get("max_iter", -1)) != 20000:
        raise ValueError("pilot wave 1 requires max_iter=20000")
    if not full_state["enabled"]:
        raise ValueError("pilot wave 1 requires full_state_checkpoint=true")
    missing_steps = {5000, 10000, 15000, 20000} - set(full_state["checkpoint_steps"])
    if missing_steps:
        raise ValueError(f"pilot full-state checkpoints missing: {sorted(missing_steps)}")
    missing_cursor_paths = set(PILOT_FULL_STATE_CSV_PATHS) - set(
        full_state["loss_csv_paths"]
    )
    if missing_cursor_paths:
        raise ValueError(
            "pilot audit CSVs must be listed in full_state_loss_csv_paths: "
            f"{sorted(missing_cursor_paths)}"
        )

    if not bool(cfg.get("load_depth", True)) or not bool(cfg.get("load_normal", True)):
        raise ValueError("pilot wave 1 requires separate MVS depth and normal supervision")
    if bool(cfg.get("load_semantic", False)):
        raise ValueError("pilot wave 1 geometry arms require load_semantic=false")
    if not cfg.get("mono_normal_dir"):
        raise ValueError("pilot wave 1 requires pinned Omnidata via mono_normal_dir")
    if not cfg.get("roof_audit_mask_manifest"):
        raise ValueError("every pilot arm requires roof_audit_mask_manifest")

    photo_manifest = cfg.get("photo_mask_manifest")
    if arm == "01_surface":
        if photo_manifest is not None:
            raise ValueError("arm 01 forbids photo_mask_manifest; audit mask is a separate key")
    else:
        if not photo_manifest:
            raise ValueError(f"{arm} requires photo_mask_manifest")
        if Path(photo_manifest).resolve() != Path(cfg["roof_audit_mask_manifest"]).resolve():
            raise ValueError(
                "photo_mask_manifest and roof_audit_mask_manifest must reference the "
                "same immutable projected-footprint inventory"
            )

    plane_manifest = cfg.get("plane_region_mask_manifest")
    if arm in _PILOT_MEDIUM_ARMS:
        if not plane_manifest:
            raise ValueError(f"{arm} requires plane_region_mask_manifest")
        if not cfg.get("init_pointcloud"):
            raise ValueError(f"{arm} requires dense MVS init_pointcloud")
        _pilot_plane_init_config(cfg)
    elif plane_manifest is not None:
        raise ValueError(f"{arm} forbids plane_region_mask_manifest")
    elif any(key in cfg for key in _PILOT_PLANE_INIT_CONFIG_KEYS):
        raise ValueError(
            f"{arm} forbids plane-guided initialization config keys"
        )

    forbidden_nonzero_defaults = {
        "w_distort": 100.0,
        "w_sem": 0.1,
        "w_mvc": 0.0,
        "w_mutual": 0.0,
        "w_mono_depth": 0.0,
        "w_semdepth_smooth": 0.0,
        "w_semdepth_plane": 0.0,
        "w_boundary_normal": 0.0,
    }
    for key, default in forbidden_nonzero_defaults.items():
        value = float(cfg.get(key, default) or 0.0)
        if value != 0.0:
            raise ValueError(f"pilot wave 1 forbids hidden/non-registered term {key}={value}")
    if bool(cfg.get("seed_semantic", False)):
        raise ValueError("pilot wave 1 forbids semantic seeding")
    if cfg.get("mono_normal_loss", "global") != "global":
        raise ValueError("pilot wave 1 uses only the fixed patch-gated mono auxiliary")
    if cfg.get("structure_grouping") != "g2_geometry":
        raise ValueError("pilot wave 1 requires structure_grouping=g2_geometry")

    for key in ("w_photo", "w_depth", "w_normal", "w_nc", "w_structure"):
        _require_finite_config_number(cfg, key, positive=True)
    _require_finite_config_number(cfg, "w_mono_normal_aux", positive=True)
    _require_finite_config_number(cfg, "w_structure_na", positive=True)
    _require_finite_config_number(cfg, "w_structure_cp", positive=True)
    if arm in {"03_plane_soft", *_PILOT_MEDIUM_ARMS}:
        _require_finite_config_number(cfg, "w_plane", positive=True)
        window_size = int(cfg.get("pilot_plane_window_size", 7))
        stride = int(cfg.get("pilot_plane_stride", 4))
        min_points = int(cfg.get("pilot_plane_min_points", 16))
        alpha_threshold = float(cfg.get("pilot_plane_alpha_threshold", 0.5))
        max_depth_range = cfg.get("pilot_plane_max_depth_range", 1.0)
        min_second_eigenvalue = float(
            cfg.get("pilot_plane_min_second_eigenvalue", 1.0e-10)
        )
        if window_size < 3 or window_size % 2 == 0:
            raise ValueError("pilot_plane_window_size must be odd and >=3")
        if stride < 1:
            raise ValueError("pilot_plane_stride must be >=1")
        if min_points < 3 or min_points > window_size * window_size:
            raise ValueError("pilot_plane_min_points is invalid for the selected arm")
        if not 0.0 <= alpha_threshold <= 1.0:
            raise ValueError("pilot_plane_alpha_threshold must be in [0,1]")
        if max_depth_range is not None and float(max_depth_range) <= 0.0:
            raise ValueError("pilot_plane_max_depth_range must be positive or null")
        if min_second_eigenvalue < 0.0:
            raise ValueError("pilot_plane_min_second_eigenvalue must be non-negative")
    elif float(cfg.get("w_plane", 0.0) or 0.0) != 0.0:
        raise ValueError(f"{arm} requires w_plane=0")

    audit_every = cfg.get("pilot_loss_audit_every")
    if isinstance(audit_every, bool) or not isinstance(audit_every, int) or audit_every <= 0:
        raise ValueError("pilot_loss_audit_every must be an explicit positive integer")
    return arm


def psnr(a: torch.Tensor, b: torch.Tensor) -> float:
    mse = ((a - b) ** 2).mean().item()
    return 20 * math.log10(1.0) - 10 * math.log10(max(mse, 1e-10))


def _ramp_weight_scale(it: int, warmup: int, schedule: str, ramp_steps: int) -> float:
    """Generic warm-up→ramp scale in [0, 1].

    0.0 before `warmup`, then either constant 1.0 or a linear ramp to 1.0 over
    `ramp_steps`. Used by L_mutual and (P2-D) by L_depth / L_normal priors.
    Defaults (warmup=0, schedule='constant') reproduce a plain constant weight, so
    configs that set w_depth/w_normal without schedule keys are unaffected.
    """
    if it < warmup:
        return 0.0
    if schedule == "constant":
        return 1.0
    if schedule == "ramp":
        if ramp_steps <= 0:
            return 1.0
        return min(1.0, float(it - warmup + 1) / float(ramp_steps))
    raise ValueError(f"Unsupported schedule={schedule!r}; expected 'constant' or 'ramp'")


def _scheduled_weight(
    base_weight: float,
    it: int,
    warmup: int,
    schedule: str,
    ramp_steps: int,
    *,
    final_weight: Optional[float] = None,
    final_factor: Optional[float] = None,
) -> float:
    """Return the effective scalar for depth/normal priors.

    Existing configs use ``constant`` or ``ramp`` and are unchanged. ``exp_decay``
    mirrors CityGSV2's multiplicative decay, with an optional absolute final
    weight for experiments that state the endpoint directly.
    """
    if schedule in ("constant", "ramp"):
        return base_weight * _ramp_weight_scale(it, warmup, schedule, ramp_steps)
    if it < warmup:
        return 0.0
    if schedule in ("exp_decay", "exponential_decay"):
        if ramp_steps <= 0:
            ramp_steps = max(1, it - warmup + 1)
        if final_weight is None:
            factor = 0.01 if final_factor is None else float(final_factor)
            final_weight = float(base_weight) * factor
        start = max(float(base_weight), 1e-12)
        end = max(float(final_weight), 1e-12)
        t = min(1.0, float(it - warmup + 1) / float(ramp_steps))
        return float(math.exp(math.log(start) * (1.0 - t) + math.log(end) * t))
    raise ValueError(
        f"Unsupported schedule={schedule!r}; expected 'constant', 'ramp', or 'exp_decay'"
    )


def _height_values(centers: torch.Tensor, e_gravity: torch.Tensor) -> torch.Tensor:
    ax = int(e_gravity.abs().argmax().item())
    sign = -torch.sign(e_gravity[ax])
    return sign * centers[:, ax]


def _weighted_quantile(values: torch.Tensor, weights: torch.Tensor, q: float) -> float:
    weights = weights.clamp_min(0)
    total = weights.sum()
    if total <= 1e-8 or values.numel() == 0:
        return float("nan")
    order = torch.argsort(values)
    v = values[order]
    w = weights[order]
    cdf = torch.cumsum(w, dim=0) / total
    idx = int(torch.searchsorted(cdf, torch.tensor(float(q), device=values.device)).clamp(max=len(v) - 1).item())
    return float(v[idx].detach().cpu().item())


def _mutual_class_stats(model: GaussianModel2D, e_gravity: torch.Tensor) -> Dict[str, float]:
    with torch.no_grad():
        p = torch.softmax(model.sem_logits, dim=-1)
        height = _height_values(model.means, e_gravity.to(model.means.device))
        entropy = -(p * p.clamp_min(1e-8).log()).sum(dim=-1)
        entropy = entropy / math.log(float(p.shape[-1]))
        stats: Dict[str, float] = {}
        for idx, name in [(1, "roof"), (2, "wall"), (3, "terrain")]:
            w = p[:, idx]
            mass = w.mean()
            stats[f"mutual/mass_{name}"] = float(mass.detach().cpu().item())
            stats[f"entropy/{name}"] = float(((w * entropy).sum() / w.sum().clamp_min(1e-8)).detach().cpu().item())
            p10 = _weighted_quantile(height, w, 0.10)
            p50 = _weighted_quantile(height, w, 0.50)
            p90 = _weighted_quantile(height, w, 0.90)
            stats[f"height/{name}_p10"] = p10
            stats[f"height/{name}_median"] = p50
            stats[f"height/{name}_p90"] = p90
            stats[f"mutual/height_{name}_p10"] = p10
            stats[f"mutual/height_{name}_p50"] = p50
            stats[f"mutual/height_{name}_p90"] = p90
        return stats


def _grad_params(model: GaussianModel2D) -> Iterable[torch.nn.Parameter]:
    params = [model.means, model.quats]
    if hasattr(model, "sem_logits"):
        params.append(model.sem_logits)
    return [p for p in params if p.requires_grad]


def _audit_params(model: GaussianModel2D, mode: str) -> list[torch.nn.Parameter]:
    """Parameters used for component-force diagnostics.

    The default geometry set excludes SH/color parameters so the reported norms
    describe surface-shaping force rather than appearance-only updates.
    """

    if mode == "all":
        return [p for p in model.parameters() if p.requires_grad]
    names = ["means", "quats", "log_scales", "opacities_raw"]
    if mode == "geometry_semantic":
        names.append("sem_logits")
    params = [getattr(model, name) for name in names if hasattr(model, name)]
    return [p for p in params if p.requires_grad]


def _grad_vector(
    loss: torch.Tensor,
    params: Iterable[torch.nn.Parameter],
) -> tuple[Optional[torch.Tensor], Optional[str]]:
    params = list(params)
    if not params:
        return None, "no_audit_parameters"
    if not torch.is_tensor(loss) or not loss.requires_grad:
        return None, "loss_has_no_grad_graph"
    grads = torch.autograd.grad(
        loss,
        params,
        retain_graph=True,
        allow_unused=True,
    )
    if all(g is None for g in grads):
        return None, "loss_unused_by_audit_parameters"
    pieces = [
        (torch.zeros_like(p) if g is None else g).detach().reshape(-1)
        for p, g in zip(params, grads)
    ]
    return torch.cat(pieces), None


def _record_grad_skip(
    writer: SummaryWriter,
    out_dir: Path,
    it: int,
    name: str,
    reason: str,
) -> None:
    tag_name = (
        name.replace("grad_cosine(", "grad_cosine_")
        .replace(")", "")
        .replace(", ", "_")
        .replace("/", "_")
    )
    writer.add_text(f"grad_diag/skipped/{tag_name}", reason, it)
    audit_dir = out_dir / "audit"
    audit_dir.mkdir(exist_ok=True)
    with (audit_dir / "gradient_skipped.jsonl").open("a") as f:
        f.write(json.dumps({"step": it, "diagnostic": name, "reason": reason}) + "\n")


def _write_mutual_grad_diagnostics(
    writer: SummaryWriter,
    out_dir: Path,
    it: int,
    model: GaussianModel2D,
    losses: Dict[str, torch.Tensor],
) -> None:
    params = list(_grad_params(model))
    vectors: Dict[str, torch.Tensor] = {}
    for name, loss in losses.items():
        tag = f"grad_norm/{name}"
        vec, reason = _grad_vector(loss, params)
        if vec is None:
            _record_grad_skip(writer, out_dir, it, tag, reason or "unavailable")
            continue
        vectors[name] = vec
        writer.add_scalar(tag, float(vec.norm().detach().cpu().item()), it)

    for other in ["photo", "depth", "normal", "semantic"]:
        tag = f"grad_cosine(mutual, {other})"
        if "mutual" not in vectors:
            _record_grad_skip(writer, out_dir, it, tag, "mutual_gradient_unavailable")
            continue
        if other not in vectors:
            _record_grad_skip(writer, out_dir, it, tag, f"{other}_gradient_unavailable")
            continue
        a = vectors["mutual"]
        b = vectors[other]
        denom = a.norm() * b.norm()
        if denom <= 1e-12:
            _record_grad_skip(writer, out_dir, it, tag, "zero_norm_gradient")
            continue
        writer.add_scalar(tag, float((a @ b / denom).detach().cpu().item()), it)


def _grad_norm_value(
    loss: torch.Tensor,
    params: list[torch.nn.Parameter],
) -> tuple[float, str]:
    if not params:
        return float("nan"), "no_audit_parameters"
    if not torch.is_tensor(loss) or not loss.requires_grad:
        return 0.0, "loss_has_no_grad_graph"
    grads = torch.autograd.grad(loss, params, retain_graph=True, allow_unused=True)
    sq = torch.zeros((), device=params[0].device)
    used = False
    for grad in grads:
        if grad is None:
            continue
        used = True
        sq = sq + grad.detach().pow(2).sum()
    if not used:
        return 0.0, "loss_unused_by_audit_parameters"
    return float(torch.sqrt(sq).detach().cpu().item()), ""


def _write_loss_grad_audit(
    out_dir: Path,
    writer: SummaryWriter,
    it: int,
    model: GaussianModel2D,
    params: list[torch.nn.Parameter],
    rowspec: Dict[str, tuple[torch.Tensor, float, torch.Tensor]],
    total_loss: torch.Tensor,
    psnr_value: float,
    n_primitives: int,
    audit_only_rowspec: Optional[Dict[str, tuple[torch.Tensor, float, torch.Tensor]]] = None,
) -> None:
    audit_dir = out_dir / "audit"
    audit_dir.mkdir(exist_ok=True)
    path = audit_dir / "loss_grad_norms.csv"
    fields = [
        "step",
        "component",
        "raw_loss",
        "weight",
        "weighted_loss",
        "weighted_loss_share",
        "grad_norm",
        "grad_norm_share",
        "grad_status",
        "total_loss",
        "psnr_train",
        "n_primitives",
    ]
    detail_rows = audit_only_rowspec or {}
    if detail_rows:
        fields.append("denominator_role")
    overlap = set(rowspec) & set(detail_rows)
    if overlap:
        raise ValueError(f"duplicate primary/audit-only loss components: {sorted(overlap)}")
    all_rowspec = {**rowspec, **detail_rows}
    weighted_vals = {
        name: float(weighted.detach().cpu().item())
        for name, (_raw, _weight, weighted) in rowspec.items()
    }
    denom_loss = sum(abs(v) for v in weighted_vals.values())
    grad_vals: dict[str, float] = {}
    grad_status: dict[str, str] = {}
    for name, (_raw, _weight, weighted) in all_rowspec.items():
        grad_vals[name], grad_status[name] = _grad_norm_value(weighted, params)
    # Gate denominator: primary effective components only.  The smooth/plane
    # detail rows are measured against it but never added to it, because their
    # combined weighted gradient already appears as the primary semdepth row.
    denom_grad = sum(
        grad_vals[name]
        for name in rowspec
        if math.isfinite(grad_vals[name])
    )
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer_csv = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        if new_file:
            writer_csv.writeheader()
        for name, (raw, weight, weighted) in all_rowspec.items():
            raw_v = float(raw.detach().cpu().item()) if torch.is_tensor(raw) else float(raw)
            weighted_v = float(weighted.detach().cpu().item())
            grad_v = grad_vals[name]
            loss_share = abs(weighted_v) / denom_loss if denom_loss > 0 else 0.0
            grad_share = grad_v / denom_grad if denom_grad > 0 and math.isfinite(grad_v) else 0.0
            writer.add_scalar(f"grad_component/{name}", grad_v, it)
            writer.add_scalar(f"grad_component_share/{name}", grad_share, it)
            output_row = {
                    "step": it,
                    "component": name,
                    "raw_loss": raw_v,
                    "weight": float(weight),
                    "weighted_loss": weighted_v,
                    "weighted_loss_share": loss_share,
                    "grad_norm": grad_v,
                    "grad_norm_share": grad_share,
                    "grad_status": grad_status[name],
                    "total_loss": float(total_loss.detach().cpu().item()),
                    "psnr_train": psnr_value,
                    "n_primitives": int(n_primitives),
                }
            if detail_rows:
                output_row["denominator_role"] = (
                    "audit_only" if name in detail_rows else "primary"
                )
            writer_csv.writerow(output_row)


def _short_building_id(value: object) -> str:
    return str(value or "").replace("DEBY_LOD2_", "")


def _target_region_mask(
    region_frame,
    target_buildings: set[str],
) -> tuple[torch.Tensor, torch.Tensor, dict]:
    """Select oracle-address regions by building ID, without reading GT values."""

    metadata_regions = region_frame.metadata.get("regions", {})
    if not isinstance(metadata_regions, dict):
        raise ValueError("semantic region metadata.regions must be an object")
    selected_ids: list[int] = []
    mapping: dict[int, str] = {}
    for raw_rid, row in metadata_regions.items():
        if not isinstance(row, dict):
            continue
        rid = int(raw_rid)
        bid = _short_building_id(row.get("building_id"))
        if bid in target_buildings:
            selected_ids.append(rid)
            mapping[rid] = bid
    if selected_ids:
        ids = torch.tensor(
            sorted(set(selected_ids)),
            device=region_frame.region_ids.device,
            dtype=region_frame.region_ids.dtype,
        )
        mask = (region_frame.region_ids[..., None] == ids).any(dim=-1)
        target_region_ids = torch.where(mask, region_frame.region_ids, 0)
    else:
        mask = torch.zeros_like(region_frame.region_ids, dtype=torch.bool)
        target_region_ids = torch.zeros_like(region_frame.region_ids)
    mask = mask & (~region_frame.cutline_mask)
    target_region_ids = torch.where(mask, target_region_ids, 0)
    return mask, target_region_ids, {
        "selected_region_ids": sorted(set(selected_ids)),
        "region_to_building": mapping,
        "address_role": "region membership only",
    }


PJPL_VIEW_AUDIT_SCHEMA = "jointbuildgs.s3a.pjpl_depth_anchor_views.v2"
PJPL_VIEW_AUDIT_FILENAME = "pjpl_depth_anchor_views.csv"


def _semantic_geometry_execution_flags(
    *,
    w_semdepth_smooth: float,
    w_semdepth_plane: float,
    w_boundary_normal: float,
    gate_attempt: int,
) -> tuple[bool, bool, bool, bool]:
    """Separate semantic-loss activation from the gate-only P-J/P-L sweep."""

    semantic_depth_enabled = w_semdepth_smooth > 0 or w_semdepth_plane > 0
    boundary_normal_enabled = w_boundary_normal > 0
    semantic_geometry_enabled = semantic_depth_enabled or boundary_normal_enabled
    pjpl_gate_sweep_enabled = semantic_geometry_enabled and int(gate_attempt) in {1, 2}
    return (
        semantic_depth_enabled,
        boundary_normal_enabled,
        semantic_geometry_enabled,
        pjpl_gate_sweep_enabled,
    )


def _mono_depth_geometry_contract(
    *,
    semantic_geometry_enabled: bool,
    w_mono_depth: float,
    mono_depth_loss: str,
) -> dict:
    """Validate and describe the no-absolute-depth S3-A-prime contract."""

    absolute_active = float(w_mono_depth) > 0 and mono_depth_loss == "absolute_l1"
    ssi_active = float(w_mono_depth) > 0 and mono_depth_loss == "ssi"
    if semantic_geometry_enabled and absolute_active:
        raise RuntimeError(
            "semantic geometry permits mono depth only with explicit mono_depth_loss=ssi; "
            "absolute monocular-depth L1 remains forbidden"
        )
    return {
        "absolute_mono_depth_forbidden_with_semantic_geometry": True,
        "absolute_mono_depth_active": absolute_active,
        "mono_depth_ssi_enabled": ssi_active,
        "semantic_geometry_enabled": bool(semantic_geometry_enabled),
    }


def _update_pjpl_view_audit(
    latest: Dict[tuple[str, str], Dict[str, object]],
    *,
    it: int,
    view_name: str,
    result: Dict[str, object],
    alpha: torch.Tensor,
    depth_valid_mask: Optional[torch.Tensor],
    target_buildings: set[str],
    oracle_visible_roof_pixels: Dict[str, int],
    alpha_threshold: float,
    snapshot_kind: str = "latest_active_sample_per_unique_view",
) -> None:
    """Keep the latest alpha/L_depth-valid pixel count for each target view.

    ``region_ids`` is the oracle class+instance *address* only.  It selects
    which pixels belong to a building, while the counted signal is strictly
    ``alpha >= threshold AND batch.depth_mask``.  No raycast distance,
    intersection coordinate, depth value, or height value is read here.
    """

    region_ids = result.get("region_ids")
    cutline_mask = result.get("cutline_mask")
    region_rows = list(result.get("region_rows") or [])
    if not torch.is_tensor(region_ids) or not torch.is_tensor(cutline_mask):
        return
    if region_ids.shape != alpha.shape or cutline_mask.shape != alpha.shape:
        raise ValueError("P-J/P-L audit expects alpha, region_ids, and cutline_mask at HxW")
    if depth_valid_mask is None:
        depth_valid = torch.zeros_like(alpha, dtype=torch.bool)
        depth_mask_present = False
    else:
        depth_valid = depth_valid_mask.to(device=alpha.device, dtype=torch.bool)
        if depth_valid.shape != alpha.shape:
            raise ValueError("P-J/P-L L_depth-valid mask must match rendered alpha HxW")
        depth_mask_present = True

    with torch.no_grad():
        outside_cut = ~cutline_mask.bool()
        alpha_valid = torch.isfinite(alpha) & (alpha >= float(alpha_threshold))
        rows_by_building: Dict[str, list[int]] = {
            bid: []
            for bid, visible_pixels in oracle_visible_roof_pixels.items()
            if bid in target_buildings and int(visible_pixels) > 0
        }
        for row in region_rows:
            bid = _short_building_id(row.get("building_id"))
            if bid not in target_buildings:
                continue
            if bid not in rows_by_building:
                raise ValueError(
                    f"P-J/P-L retained region {bid} lacks positive oracle visibility metadata"
                )
            try:
                rid = int(row["region_id"])
            except (KeyError, TypeError, ValueError):
                continue
            rows_by_building.setdefault(bid, []).append(rid)

        view = str(view_name)
        view_stem = Path(view).stem
        for bid, region_id_values in rows_by_building.items():
            unique_region_ids = sorted(set(region_id_values))
            address = torch.zeros_like(alpha_valid)
            for rid in unique_region_ids:
                address |= region_ids == rid
            address &= outside_cut
            address_count = int(address.sum().detach().cpu().item())
            alpha_count = int((address & alpha_valid).sum().detach().cpu().item())
            depth_count = int((address & depth_valid).sum().detach().cpu().item())
            joint_count = int(
                (address & alpha_valid & depth_valid).sum().detach().cpu().item()
            )
            latest[(bid, view_stem)] = {
                "schema": PJPL_VIEW_AUDIT_SCHEMA,
                "building_id": bid,
                "view": view,
                "view_stem": view_stem,
                "measurement_step": int(it),
                "source_region_count": len(unique_region_ids),
                "retained_region_present": str(bool(unique_region_ids)).lower(),
                "oracle_visible_roof_pixel_count": int(oracle_visible_roof_pixels[bid]),
                "visibility_source": "oracle_address_check.by_building.true_roof_total",
                "address_pixel_count": address_count,
                "alpha_valid_pixel_count": alpha_count,
                "ldepth_valid_pixel_count": depth_count,
                "alpha_and_ldepth_valid_pixel_count": joint_count,
                "alpha_threshold": float(alpha_threshold),
                "depth_mask_present": str(depth_mask_present).lower(),
                "depth_valid_source": "batch.depth_mask_existing_L_depth",
                "valid_pixel_rule": "alpha>=0.5 AND existing_L_depth_valid",
                "view_aggregation_snapshot": str(snapshot_kind),
                "region_address_mode": "oracle_class_plus_raycast_building_id",
                "raycast_building_id_role": "region_membership_only",
                "raycast_id_depth_or_height_supervision": "false",
                "cutline_policy": "exclude_instance_cutline_plus_minus_7px",
            }


def _write_pjpl_view_audit(
    out_dir: Path,
    latest: Dict[tuple[str, str], Dict[str, object]],
) -> Path:
    """Write one deterministic, latest active observation per building/view."""

    audit_dir = out_dir / "audit"
    audit_dir.mkdir(exist_ok=True)
    path = audit_dir / PJPL_VIEW_AUDIT_FILENAME
    fields = [
        "schema",
        "building_id",
        "view",
        "view_stem",
        "measurement_step",
        "source_region_count",
        "retained_region_present",
        "oracle_visible_roof_pixel_count",
        "visibility_source",
        "address_pixel_count",
        "alpha_valid_pixel_count",
        "ldepth_valid_pixel_count",
        "alpha_and_ldepth_valid_pixel_count",
        "alpha_threshold",
        "depth_mask_present",
        "depth_valid_source",
        "valid_pixel_rule",
        "view_aggregation_snapshot",
        "region_address_mode",
        "raycast_building_id_role",
        "raycast_id_depth_or_height_supervision",
        "cutline_policy",
    ]
    with path.open("x", newline="", encoding="utf-8") as fh:
        writer_csv = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer_csv.writeheader()
        for key in sorted(latest):
            writer_csv.writerow(latest[key])
    return path


@torch.no_grad()
def _collect_pjpl_view_audit(
    *,
    model: GaussianModel2D,
    ds: ColmapDataset,
    view_indices: Iterable[int],
    device: str,
    region_cache: SemanticRegionCache,
    target_buildings: set[str],
    alpha_threshold: float,
    measurement_step: int,
) -> Dict[tuple[str, str], Dict[str, object]]:
    """Render one fixed post-probe snapshot for every visible training view.

    This audit sweep has no optimizer/backward call.  It prevents the P-J/P-L
    classification from depending on which views happened to be sampled at a
    periodic logging tick and makes every per-view count describe the same
    post-1k model state.
    """

    latest: Dict[tuple[str, str], Dict[str, object]] = {}
    total_view_count = 0
    visible_view_count = 0
    rendered_view_count = 0
    skipped_zero_visibility_view_count = 0
    for idx in view_indices:
        total_view_count += 1
        batch = ds[idx]
        height, width = batch["height"], batch["width"]
        frame = region_cache.get(batch["name"], height, width, device)
        oracle_by_building = (
            (frame.metadata.get("oracle_address_check") or {}).get("by_building") or {}
        )
        if not isinstance(oracle_by_building, dict):
            raise ValueError("P-J/P-L oracle visibility inventory must be a building mapping")
        oracle_visible_roof_pixels: Dict[str, int] = {}
        for raw_bid, counts in oracle_by_building.items():
            bid = _short_building_id(raw_bid)
            if bid not in target_buildings:
                continue
            if not isinstance(counts, dict):
                raise ValueError(f"P-J/P-L visibility metadata for {bid} must be a mapping")
            try:
                visible_pixels = int(counts["true_roof_total"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"P-J/P-L visibility metadata for {bid} lacks integer true_roof_total"
                ) from exc
            if visible_pixels < 0:
                raise ValueError(f"P-J/P-L visibility count for {bid} must be nonnegative")
            oracle_visible_roof_pixels[bid] = visible_pixels
        if set(oracle_visible_roof_pixels) != target_buildings:
            raise ValueError(
                "P-J/P-L visibility metadata target set mismatch: "
                f"observed={sorted(oracle_visible_roof_pixels)}, "
                f"expected={sorted(target_buildings)}"
            )
        if not any(count > 0 for count in oracle_visible_roof_pixels.values()):
            skipped_zero_visibility_view_count += 1
            continue
        visible_view_count += 1
        w2c = batch["w2c"].to(device)
        K = batch["K"].to(device)
        rendered = render(
            model,
            w2c,
            K,
            width,
            height,
            sh_degree=model.active_sh_degree,
            render_mode="RGB+ED",
        )
        rendered_view_count += 1
        metadata_regions = frame.metadata.get("regions", {})
        region_rows: list[Dict[str, object]] = []
        for rid_t in torch.unique(frame.region_ids[frame.region_ids > 0]):
            rid = int(rid_t.detach().cpu().item())
            metadata = metadata_regions.get(str(rid), metadata_regions.get(rid, {}))
            region_rows.append(
                {
                    "region_id": rid,
                    "building_id": metadata.get("building_id", ""),
                }
            )
        _update_pjpl_view_audit(
            latest,
            it=measurement_step,
            view_name=str(batch["name"]),
            result={
                "region_ids": frame.region_ids,
                "cutline_mask": frame.cutline_mask,
                "region_rows": region_rows,
            },
            alpha=rendered["alpha"],
            depth_valid_mask=(batch["depth_mask"] if "depth_mask" in batch else None),
            target_buildings=target_buildings,
            oracle_visible_roof_pixels=oracle_visible_roof_pixels,
            alpha_threshold=alpha_threshold,
            snapshot_kind="post_probe_full_training_view_sweep",
        )
    print(
        "[S3-A P-J/P-L sweep views] "
        f"total={total_view_count} visible={visible_view_count} "
        f"rendered={rendered_view_count} "
        f"skipped_zero_visibility={skipped_zero_visibility_view_count}",
        flush=True,
    )
    return latest


def _write_semantic_geometry_audit(
    *,
    out_dir: Path,
    it: int,
    view_name: str,
    result: Dict[str, object],
    weighted_semdepth: torch.Tensor,
    weighted_boundary_normal: torch.Tensor,
    depth_pred: torch.Tensor,
    target_buildings: set[str],
    target_observations: Dict[str, int],
) -> set[str]:
    """Write audit-only S3 rows without double-counting the gate denominator.

    The generic ``loss_grad_norms.csv`` owns gate shares and contains only the
    combined weighted ``semdepth`` component plus ``boundary_normal``.  This
    companion file records smooth/plane detail, per-region validity/mapping, and
    P-I rendered-depth gradient delivery.  Its rows are explicitly
    ``denominator_role=audit_only``.
    """

    audit_dir = out_dir / "audit"
    audit_dir.mkdir(exist_ok=True)
    path = audit_dir / "semantic_geometry.csv"
    fields = [
        "step", "view", "region_id", "building_id", "is_pi_target",
        "denominator_role", "loss_smooth", "weight_smooth", "weighted_smooth",
        "loss_plane", "weight_plane", "weighted_plane", "loss_semdepth_weighted",
        "loss_boundary_normal", "weight_boundary_normal", "weighted_boundary_normal",
        "view_smooth_valid_stencil_count", "smooth_valid_stencil_count",
        "boundary_valid_pixel_count", "boundary_kernel_size", "boundary_radius_px",
        "source_component_id", "source_component_pixel_count",
        "pre_split_overlap_count", "region_pixel_count",
        "render_valid_pixel_count", "render_valid_fraction", "depth_anchor_pixel_count",
        "depth_anchor_fraction", "plane_valid_pixel_count", "plane_skipped_lt64",
        "plane_fitted_iteration", "plane_loss", "semdepth_depth_grad_norm",
        "semdepth_depth_grad_norm_share", "semdepth_depth_grad_nonzero_pixel_count",
        "semdepth_depth_grad_nonzero_fraction", "target_observation_count",
        "view_region_count", "plane_active_region_count", "plane_skipped_region_count",
        "raycast_assignment_primary_provenance", "raycast_misassignment_rate",
        "raycast_misassignment_numerator", "raycast_misassignment_denominator",
        "raycast_official_provenance", "raycast_official_misassignment_rate",
        "raycast_official_misassignment_numerator", "raycast_official_misassignment_denominator",
    ]

    grad = None
    if torch.is_tensor(weighted_semdepth) and weighted_semdepth.requires_grad:
        grad = torch.autograd.grad(
            weighted_semdepth,
            depth_pred,
            retain_graph=True,
            allow_unused=True,
        )[0]
    grad_norm_total = float(grad.detach().norm().cpu().item()) if grad is not None else 0.0

    smooth = result["smooth"]
    plane = result["plane"]
    boundary = result["boundary_normal"]
    region_ids = result.get("region_ids")
    cutline_mask = result.get("cutline_mask")
    metadata = result.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    checks = metadata.get("raycast_assignment_check", {})
    if not isinstance(checks, dict):
        checks = {}
    check_primary = checks.get("primary_actual_label_source", {})
    check_official = checks.get("secondary_official_v2", {})
    if not isinstance(check_primary, dict):
        check_primary = {}
    if not isinstance(check_official, dict):
        check_official = {}

    region_rows = list(result.get("region_rows") or [])
    view_region_count = len(region_rows)
    plane_active_region_count = sum(
        row.get("plane_fitted_iteration", "") not in {"", None}
        for row in region_rows
    )
    plane_skipped_region_count = sum(
        int(row.get("plane_skipped_lt64", 0) or 0) for row in region_rows
    )
    if not region_rows:
        # Keep a view-level row so zero-signal/zero-region events are observable.
        region_rows = [{"region_id": "", "building_id": ""}]
    new_file = not path.exists()
    positive_targets: set[str] = set()
    with path.open("a", newline="", encoding="utf-8") as fh:
        csv_writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        if new_file:
            csv_writer.writeheader()
        for region_row in region_rows:
            row = dict(region_row)
            bid = _short_building_id(row.get("building_id"))
            rid = row.get("region_id", "")
            target = bid in target_buildings
            region_grad_norm = 0.0
            nonzero_count = 0
            region_count = 0
            if (
                grad is not None
                and torch.is_tensor(region_ids)
                and torch.is_tensor(cutline_mask)
                and rid != ""
            ):
                mask = (region_ids == int(rid)) & (~cutline_mask)
                values = grad[mask]
                region_count = int(values.numel())
                if region_count:
                    region_grad_norm = float(values.detach().norm().cpu().item())
                    nonzero_count = int((values.detach() != 0).sum().cpu().item())
            if target and region_grad_norm > 0.0 and nonzero_count > 0:
                positive_targets.add(bid)
            csv_writer.writerow(
                {
                    "step": int(it),
                    "view": view_name,
                    "region_id": rid,
                    "building_id": bid,
                    "is_pi_target": int(target),
                    "denominator_role": "audit_only",
                    "loss_smooth": float(smooth.detach().cpu().item()),
                    "weight_smooth": result.get("weight_smooth", 0.0),
                    "weighted_smooth": float(result.get("weighted_smooth", 0.0)),
                    "loss_plane": float(plane.detach().cpu().item()),
                    "weight_plane": result.get("weight_plane", 0.0),
                    "weighted_plane": float(result.get("weighted_plane", 0.0)),
                    "loss_semdepth_weighted": float(weighted_semdepth.detach().cpu().item()),
                    "loss_boundary_normal": float(boundary.detach().cpu().item()),
                    "weight_boundary_normal": result.get("weight_boundary_normal", 0.0),
                    "weighted_boundary_normal": float(weighted_boundary_normal.detach().cpu().item()),
                    "view_smooth_valid_stencil_count": result.get("smooth_valid_stencil_count", 0),
                    "smooth_valid_stencil_count": row.get("smooth_valid_stencil_count", ""),
                    "boundary_valid_pixel_count": result.get("boundary_valid_pixel_count", 0),
                    "boundary_kernel_size": result.get("boundary_kernel_size", ""),
                    "boundary_radius_px": result.get("boundary_radius_px", ""),
                    "semdepth_depth_grad_norm": region_grad_norm,
                    "semdepth_depth_grad_norm_share": (
                        region_grad_norm / grad_norm_total if grad_norm_total > 0 else 0.0
                    ),
                    "semdepth_depth_grad_nonzero_pixel_count": nonzero_count,
                    "semdepth_depth_grad_nonzero_fraction": (
                        nonzero_count / region_count if region_count else 0.0
                    ),
                    "target_observation_count": target_observations.get(bid, 0),
                    "view_region_count": view_region_count,
                    "plane_active_region_count": plane_active_region_count,
                    "plane_skipped_region_count": plane_skipped_region_count,
                    "raycast_assignment_primary_provenance": check_primary.get("provenance", ""),
                    "raycast_misassignment_rate": check_primary.get("misassignment_rate", ""),
                    "raycast_misassignment_numerator": check_primary.get("misassigned_building_pixels", ""),
                    "raycast_misassignment_denominator": check_primary.get("comparable_true_roof_pixels", ""),
                    "raycast_official_provenance": check_official.get("provenance", ""),
                    "raycast_official_misassignment_rate": check_official.get("misassignment_rate", ""),
                    "raycast_official_misassignment_numerator": check_official.get("misassigned_building_pixels", ""),
                    "raycast_official_misassignment_denominator": check_official.get("comparable_true_roof_pixels", ""),
                    **{
                        key: row.get(key, "")
                        for key in fields
                        if key in row and key not in {"region_id", "building_id"}
                    },
                }
            )

    summary_path = audit_dir / "semantic_target_observations.csv"
    new_summary = not summary_path.exists()
    with summary_path.open("a", newline="", encoding="utf-8") as fh:
        summary_writer = csv.DictWriter(
            fh,
            fieldnames=["step", "building_id", "active_view_observation_count"],
            lineterminator="\n",
        )
        if new_summary:
            summary_writer.writeheader()
        for bid in sorted(target_buildings):
            summary_writer.writerow(
                {
                    "step": int(it),
                    "building_id": bid,
                    "active_view_observation_count": target_observations.get(bid, 0),
                }
            )

    return positive_targets


def _log_disabled_mutual_terms(
    writer: SummaryWriter,
    it: int,
    *,
    semcal_enabled: bool = False,
) -> None:
    tags = []
    if not semcal_enabled:
        tags.append("loss/mutual_sem_geom_calib")
    tags.extend([
        "loss/mutual_roof_wall_relation",
        "loss/mutual_terrain_wall_relation",
    ])
    for tag in tags:
        writer.add_scalar(tag, float("nan"), it)
        writer.add_text(f"{tag}/status", "disabled", it)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    config_path = Path(args.config)
    with config_path.open() as f:
        cfg = yaml.safe_load(f)
    full_state = full_state_options(cfg)
    pilot_arm = _validate_pilot_config_contract(cfg, full_state)

    set_seed(cfg.get("seed", 0))
    device = cfg.get("device", "cuda")
    out_dir = Path(cfg["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ckpt").mkdir(exist_ok=True)
    (out_dir / "renders").mkdir(exist_ok=True)

    # ---------- data ----------
    # Non-pilot configs retain the historical ``mono_normal_dir`` alias for the
    # primary override.  Pilot configs make the two channels unambiguously
    # separate: normal=MVS primary, mono_normal=Omnidata auxiliary.
    primary_normal_dir = (
        cfg.get("normal_dir")
        if pilot_arm is not None
        else cfg.get("normal_dir") or cfg.get("mono_normal_dir")
    )
    auxiliary_normal_dir = cfg.get("mono_normal_dir") if pilot_arm is not None else None
    ds = ColmapDataset(
        root=cfg["data_root"],
        downscale=cfg.get("downscale", 0.5),
        load_depth=cfg.get("load_depth", True),
        load_normal=cfg.get("load_normal", True),
        load_semantic=cfg.get("load_semantic", False),
        normal_dir=primary_normal_dir,
        mono_normal_dir=auxiliary_normal_dir,
        mono_depth_dir=cfg.get("mono_depth_dir"),
        depth_scale=cfg.get("depth_scale", 1.0),
        mono_depth_scale=cfg.get("mono_depth_scale", 1.0),
        mono_depth_far_sentinel=cfg.get("mono_depth_far_sentinel", 28000.0),
        normal_encoding=cfg.get("normal_encoding", "half_range"),
        visible_views=cfg.get("visible_views"),
        photo_mask_manifest=cfg.get("photo_mask_manifest"),
        roof_audit_mask_manifest=cfg.get("roof_audit_mask_manifest"),
        plane_region_mask_manifest=cfg.get("plane_region_mask_manifest"),
        pilot_arm=pilot_arm,
    )
    print(f"[data] frames={len(ds)}  pts_init={ds.points_xyz.shape[0]}")

    # train/test split: interleave (every 10th frame → test) to avoid systematic
    # azimuth / viewpoint bias when frames are stored in sorted order (grouped by
    # capture type). Previously used "last 10%" which grouped all orbit views into
    # test → test was out-of-distribution → severe overfitting.
    train_idx, test_idx, view_role_audit = resolve_view_roles(
        ds.frames,
        train_views=cfg.get("train_views"),
        eval_views=cfg.get("eval_views"),
    )
    view_role_audit["visible_filter"] = ds.visible_view_audit
    print(
        f"[views] mode={view_role_audit['mode']} train={len(train_idx)} "
        f"eval={len(test_idx)} visible={len(ds.frames)}"
    )

    # ---------- semantic seeding (P2 ①): optional carve seeds for textureless bldgs ----------
    points_xyz, points_rgb = ds.points_xyz, ds.points_rgb
    points_sem = None
    points_init_opacity = None
    surface_seed_mask = None
    surface_seed_audit = None
    if cfg.get("seed_semantic", False):
        from .semantic_seed import build_semantic_seeds, cameras_from_frames, concat_seeds

        sc = dict(cfg["seed_cfg"])   # seeding config (the int `seed:` is the RNG seed)
        # P2 impl ②: optional per-building seeding band {bid: [z_min, z_max]} (GS-local). If
        # bands_file is given it overrides the global z_min/z_max per building (impl ① path,
        # no bands_file, is unchanged).
        bands = None
        if sc.get("bands_file"):
            import json as _json
            bands = _json.loads(Path(sc["bands_file"]).read_text())
            print(f"[seed] per-building bands from {sc['bands_file']} ({len(bands)} buildings)")
        seeds = build_semantic_seeds(
            cameras=cameras_from_frames(ds.frames),
            semantic_dir=sc["semantic_dir"],
            footprints_path=sc["footprints"],
            buildings=sc["buildings"],
            scene_rgb=ds.points_rgb.mean(axis=0),
            id_field=sc.get("id_field", "building_id"),
            world_offset=sc.get("world_offset", [690953.0, 5336071.0, 604.0]),
            z_min=sc.get("z_min", -55.0), z_max=sc.get("z_max", 5.0),
            bands=bands,
            voxel=sc.get("voxel", 1.0), tau=sc.get("tau", 0.6),
            min_obs=sc.get("min_obs", 5),
            roof_code=sc.get("roof_code", 1), wall_code=sc.get("wall_code", 2),
            max_seeds_per_building=sc.get("max_seeds_per_building", 0),
            geoid=sc.get("geoid"),
        )
        combined = concat_seeds(ds.points_xyz, ds.points_rgb, seeds)
        points_xyz, points_rgb, points_sem = combined
        points_init_opacity = combined.init_opacity
        surface_seed_mask = combined.is_surface_seed
        print(f"[seed] +{len(seeds.xyz)} semantic seeds over {len(sc['buildings'])} buildings "
              f"-> N {ds.points_xyz.shape[0]} -> {points_xyz.shape[0]}")

    # ---------- S3-A-prime external seed surface ----------
    surface_seed_path = cfg.get("surface_seed_npz")
    if surface_seed_path:
        from .semantic_seed import (
            concat_seeds,
            load_surface_seed_npz,
            perturb_surface_seed,
        )

        surface_seed_path = str(surface_seed_path)
        surface_seeds = load_surface_seed_npz(surface_seed_path)
        surface_seeds = perturb_surface_seed(
            surface_seeds,
            height_delta_m=float(cfg.get("surface_seed_height_delta_m", 0.0)),
            tilt_deg=float(cfg.get("surface_seed_tilt_deg", 0.0)),
            tilt_axis_xy=cfg.get("surface_seed_tilt_axis_xy"),
            tilt_pivot_xy=cfg.get("surface_seed_tilt_pivot_xy"),
        )
        combined = concat_seeds(
            points_xyz,
            points_rgb,
            surface_seeds,
            points_sem=points_sem,
            points_init_opacity=points_init_opacity,
            points_surface_seed=surface_seed_mask,
        )
        points_xyz, points_rgb, points_sem = combined
        points_init_opacity = combined.init_opacity
        surface_seed_mask = combined.is_surface_seed
        seed_bytes = Path(surface_seed_path).read_bytes()
        surface_seed_audit = {
            "path": surface_seed_path,
            "sha256": hashlib.sha256(seed_bytes).hexdigest(),
            "schema": surface_seeds.metadata.get("schema"),
            "metadata": surface_seeds.metadata,
            "n_surface_seed": int(surface_seed_mask.sum()),
            "init_opacity": 0.10,
        }
        print(
            f"[surface-seed] +{len(surface_seeds.xyz)} strict NPZ seeds "
            f"opacity=0.10 -> N={len(points_xyz)}"
        )

    # ---------- MVS-seed init (P2 make-or-break v6) ----------
    # INIT/DATA PATH ONLY (no engine logic): seed the model with a prepared GS-LOCAL MVS cloud
    # (dense=DIM / acmp=ACMP), produced offline by tum_mob_seed_prep.sh (AOI crop + per-cloud
    # geoid shift + voxel<=~3M + outlier clip). Default mode "concat": add the MVS points onto
    # the SfM base so the full scene stays trainable (ACMP exists only over the AOI), while the
    # 11 eval buildings get dense init. RGB = scene mean (same as the semantic seeds; L_photo
    # recolours during training). scene_scale is intentionally left on ds.points_xyz (the SfM
    # extent) so densification thresholds are unchanged by the AOI-concentrated seeds.
    mvs_seed_mask = None   # (P2 make-or-break C) bool over final init rows: True = MVS seed
    init_pc = cfg.get("init_pointcloud")
    if init_pc:
        from .pointcloud_io import read_init_pointcloud

        mode = cfg.get("init_pointcloud_mode", "concat")
        seed_xyz = read_init_pointcloud(init_pc)                      # (M,3) GS-LOCAL
        scene_rgb = ds.points_rgb.mean(axis=0)
        seed_rgb = np.broadcast_to(scene_rgb, (len(seed_xyz), 3)).astype(np.float32).copy()
        n0 = points_xyz.shape[0]
        if mode == "replace":
            points_xyz = seed_xyz.astype(np.float32)
            points_rgb = seed_rgb
            points_sem = None
            points_init_opacity = None
            surface_seed_mask = np.zeros(len(seed_xyz), dtype=np.bool_)
        elif mode == "concat":
            points_xyz = np.concatenate([points_xyz, seed_xyz], axis=0).astype(np.float32)
            points_rgb = np.concatenate([points_rgb, seed_rgb], axis=0).astype(np.float32)
            if points_sem is not None:
                points_sem = np.concatenate(
                    [points_sem, np.full(len(seed_xyz), -1, np.int64)]).astype(np.int64)
            if points_init_opacity is not None:
                points_init_opacity = np.concatenate(
                    [points_init_opacity, np.full(len(seed_xyz), 0.10, np.float32)]
                ).astype(np.float32)
            if surface_seed_mask is not None:
                surface_seed_mask = np.concatenate(
                    [surface_seed_mask, np.zeros(len(seed_xyz), dtype=np.bool_)]
                )
        else:
            raise ValueError(f"init_pointcloud_mode must be concat|replace, got {mode!r}")
        print(f"[mvs-seed] {mode} {len(seed_xyz)} MVS init pts from {init_pc}: "
              f"N {n0} -> {points_xyz.shape[0]}")
        mvs_seed_mask = np.zeros(points_xyz.shape[0], dtype=bool)
        mvs_seed_mask[(0 if mode == "replace" else n0):] = True   # replace=all, concat=appended rows

    mvs_seed_init_opacity = cfg.get("mvs_seed_init_opacity")
    points_init_opacity = apply_mvs_seed_init_opacity(
        len(points_xyz),
        mvs_seed_mask,
        points_init_opacity,
        mvs_seed_init_opacity,
    )
    if mvs_seed_init_opacity is not None:
        print(
            f"[mvs-seed] init opacity={float(mvs_seed_init_opacity):.3f} "
            f"for {int(mvs_seed_mask.sum())} lineage roots"
        )

    # ---------- model ----------
    model = GaussianModel2D(
        points_xyz=points_xyz,
        points_rgb=points_rgb,
        sh_degree=cfg.get("sh_degree", 3),
        device=device,
        points_sem=points_sem,
        points_init_opacity=points_init_opacity,
        surface_seed_mask=surface_seed_mask,
    )
    model = model.to(device)

    # 04a/04b share one deterministic plane-guided initialization path.  This
    # start gate is deliberately before optimizer construction: fresh runs set
    # only the dense-MVS seed quaternion rows, while resume requests validate
    # the immutable binding and leave checkpoint quaternions authoritative.
    pilot_plane_init_result = None
    pilot_plane_init_audit_path: Optional[Path] = None
    pilot_plane_init_resume_audit_path: Optional[Path] = None
    pilot_plane_init_effective: dict[str, Any] = {
        "status": "not_applicable_for_this_pilot_arm"
    }
    if pilot_arm in _PILOT_MEDIUM_ARMS:
        if mvs_seed_mask is None or not bool(mvs_seed_mask.any()):
            raise RuntimeError(
                f"{pilot_arm} plane-guided initialization requires nonempty MVS seeds"
            )
        if ds.plane_region_mask_binding is None:
            raise RuntimeError(
                f"{pilot_arm} plane-guided initialization requires a bound plane mask"
            )
        plane_init_config = _pilot_plane_init_config(cfg)
        pilot_plane_init_result = build_plane_guided_initialization(
            dataset=ds,
            training_view_indices=train_idx,
            mvs_seed_xyz=points_xyz[mvs_seed_mask],
            plane_mask_binding=ds.plane_region_mask_binding,
            pilot_arm=pilot_arm,
            config=plane_init_config,
        )
        pilot_plane_init_audit_path = (
            out_dir / "audit/pilot_plane_guided_init.json"
        )
        pilot_plane_init_preoptimizer_mode = _pilot_plane_init_start_mode(
            full_state["resume_request"],
            fresh_audit_exists=pilot_plane_init_audit_path.is_file(),
            checkpoint_candidate_exists=any(
                (out_dir / "ckpt").glob("step_*.pt")
            ),
        )
        pilot_plane_init_resume_audit_path = _execute_pilot_plane_init_start_gate(
            model=model,
            result=pilot_plane_init_result,
            mvs_seed_mask=mvs_seed_mask,
            start_mode=pilot_plane_init_preoptimizer_mode,
            fresh_audit_path=pilot_plane_init_audit_path,
            resume_audit_path=(
                out_dir / "audit/pilot_plane_guided_init_resume_verification.json"
            ),
        )

        init_audit = pilot_plane_init_result.audit
        pilot_plane_init_effective = {
            "status": "implemented_pre_optimizer_start_gate",
            "algorithm": init_audit["algorithm"]["algorithm"],
            "algorithm_sha256": init_audit["algorithm_sha256"],
            "binding_sha256": init_audit["binding_sha256"],
            "parameters": init_audit["parameters"],
            "source": init_audit["source"],
            "fresh_audit_path": str(pilot_plane_init_audit_path),
            "fresh_only_application": True,
            "checkpoint_quaternions_take_precedence_on_resume": True,
            "selection": "dense_mvs_seed_rows_only",
        }
        print(
            "[pilot-plane-init] "
            f"arm={pilot_arm} evidence={init_audit['counts']['evidence_sample_count']} "
            f"matched={init_audit['counts']['matched_seed_count']}/"
            f"{init_audit['counts']['mvs_seed_count']} "
            f"coverage={init_audit['counts']['matched_seed_fraction']:.6f} "
            f"mode={pilot_plane_init_preoptimizer_mode}",
            flush=True,
        )

    def _configured_optimizers(candidate_model: GaussianModel2D):
        return build_optimizers(
            candidate_model,
            lr_means=cfg.get("lr_means", 1.6e-4),
            lr_scales=cfg.get("lr_scales", 5e-3),
            lr_quats=cfg.get("lr_quats", 1e-3),
            lr_opacities=cfg.get("lr_opacities", 5e-2),
            lr_sh0=cfg.get("lr_sh0", 2.5e-3),
            lr_shN=cfg.get("lr_shN", 1.25e-4),
        )

    params = build_param_dict(model)
    optimizers = _configured_optimizers(model)

    # scene scale (for DefaultStrategy)
    scene_scale = float(np.linalg.norm(ds.points_xyz - ds.points_xyz.mean(0), axis=1).mean())
    scene_extent_bbox = float(np.linalg.norm(ds.points_xyz.max(axis=0) - ds.points_xyz.min(axis=0)))

    _strat_kwargs = dict(
        prune_opa=cfg.get("prune_opa", 0.005),
        grow_grad2d=cfg.get("grow_grad2d", 2e-4),
        grow_scale3d=cfg.get("grow_scale3d", 0.01),
        prune_scale3d=cfg.get("prune_scale3d", 0.1),
        refine_start_iter=cfg.get("refine_start_iter", 500),
        refine_stop_iter=cfg.get("refine_stop_iter", 15000),
        refine_every=cfg.get("refine_every", 100),
        reset_every=cfg.get("reset_every", 3000),
    )
    # Legacy ``seed_protect`` remains MVS-lineage protection.  S3-A-prime uses
    # a separate, surface-only switch so A0/A1 cannot accidentally inherit A2.
    legacy_mvs_seed_protect = bool(cfg.get("seed_protect", False)) and (
        mvs_seed_mask is not None
    )
    surface_seed_protect = bool(cfg.get("surface_seed_protect", False))
    if surface_seed_protect and (
        surface_seed_mask is None or not bool(surface_seed_mask.any())
    ):
        raise RuntimeError("surface_seed_protect=true requires a nonempty surface_seed_npz")
    if surface_seed_protect and legacy_mvs_seed_protect:
        raise ValueError(
            "S3-A-prime A2 protection is surface-lineage only; disable legacy seed_protect"
        )
    seed_protect_until_iter = cfg.get("seed_protect_until_iter")
    seed_prune_schedule = {}
    if surface_seed_protect:
        surface_until = int(cfg.get("surface_seed_protect_until_iter", 10000))
        schedule_initial = float(cfg.get("surface_seed_prune_opa_initial", 0.05))
        schedule_final = float(cfg.get("surface_seed_prune_opa_final", 0.01))
        schedule_switch = int(cfg.get("surface_seed_prune_switch_iter", 10000))
        if (surface_until, schedule_initial, schedule_final, schedule_switch) != (
            10000,
            0.05,
            0.01,
            10000,
        ):
            raise ValueError(
                "S3-A-prime A2 lock requires protect_until=10000 and "
                "prune opacity 0.05->0.01 at iteration 10000"
            )
        seed_protect_until_iter = surface_until
        seed_prune_schedule = {
            "seed_prune_opa_initial": schedule_initial,
            "seed_prune_opa_final": schedule_final,
            "seed_prune_switch_iter": schedule_switch,
        }
    elif seed_protect_until_iter is not None:
        seed_protect_until_iter = int(seed_protect_until_iter)

    seed_protect = legacy_mvs_seed_protect or surface_seed_protect
    seed_protect_mask = np.zeros(len(points_xyz), dtype=np.bool_)
    if legacy_mvs_seed_protect:
        seed_protect_mask |= mvs_seed_mask
    if surface_seed_protect:
        seed_protect_mask |= surface_seed_mask
    elongation_filter = bool(cfg.get("elongation_filter", False))
    elongation_axis_ratio_threshold = float(cfg.get("elongation_axis_ratio_threshold", 0.01))
    if seed_protect and elongation_filter:
        from .densification import build_seed_protect_elongation_filter_strategy
        strategy = build_seed_protect_elongation_filter_strategy(
            axis_ratio_threshold=elongation_axis_ratio_threshold,
            seed_protect_until_iter=seed_protect_until_iter,
            **seed_prune_schedule,
            **_strat_kwargs,
        )
    elif seed_protect:
        from .densification import build_seed_protect_strategy
        strategy = build_seed_protect_strategy(
            seed_protect_until_iter=seed_protect_until_iter,
            **seed_prune_schedule,
            **_strat_kwargs,
        )
    elif elongation_filter:
        from .densification import build_elongation_filter_strategy
        strategy = build_elongation_filter_strategy(
            axis_ratio_threshold=elongation_axis_ratio_threshold,
            **_strat_kwargs,
        )
    else:
        strategy = build_strategy(**_strat_kwargs)
    strategy.check_sanity(params, optimizers)
    strategy_state = strategy.initialize_state(scene_scale=scene_scale)
    if surface_seed_path:
        # Kept for every arm, not just A2.  gsplat duplicate/split/remove carries
        # arbitrary per-Gaussian state tensors in lockstep, so this remains a
        # true lineage mask after densification and pruning.
        strategy_state["surface_seed_lineage"] = torch.from_numpy(
            surface_seed_mask
        ).to(device)
    seed_log_boxes = None
    if seed_protect:
        strategy_state["is_seed"] = torch.from_numpy(seed_protect_mask).to(device)
        release_msg = "for all refine steps" if seed_protect_until_iter is None else f"until iter {seed_protect_until_iter}"
        protected_kind = (
            "surface+MVS" if surface_seed_protect and legacy_mvs_seed_protect
            else "surface" if surface_seed_protect
            else "MVS"
        )
        print(f"[seed-protect] protecting {int(seed_protect_mask.sum())} {protected_kind}-lineage "
              f"Gaussians from prune (of {len(seed_protect_mask)}) {release_msg}")
        seed_log_boxes = _load_footprint_boxes_local(
            cfg.get("seed_log_footprints"), cfg.get("world_offset", [690953.0, 5336071.0, 604.0]),
            cfg.get("seed_log_buildings"))
    if elongation_filter:
        print(
            f"[elongation-filter] in-plane min(scale0,scale1)/max(scale0,scale1) "
            f"> {elongation_axis_ratio_threshold:g} required for densify"
        )
    densify_audit_buildings = list(cfg.get("densify_audit_buildings") or [])
    if densify_audit_buildings:
        if not hasattr(strategy, "_densify_candidate_mask"):
            raise RuntimeError("densify_audit_buildings requires elongation_filter=true")
        densify_boxes = _load_footprint_boxes_local(
            cfg.get("densify_audit_footprints") or cfg.get("seed_log_footprints"),
            cfg.get("world_offset", [690953.0, 5336071.0, 604.0]),
            densify_audit_buildings,
        )
        if not densify_boxes or len(densify_boxes) != len(densify_audit_buildings):
            missing = sorted(set(densify_audit_buildings) - set((densify_boxes or {}).keys()))
            raise RuntimeError(f"densify audit footprint boxes missing for: {missing}")
        strategy.densify_audit_boxes = densify_boxes
        strategy.densify_audit_events = []
        print(f"[densify-audit] recording split/duplicate events for {len(densify_boxes)} buildings")

    # ---------- logging ----------
    writer = SummaryWriter(out_dir / "tb")

    # ---------- loss weights ----------
    w_photo = cfg.get("w_photo", 1.0)
    w_depth = cfg.get("w_depth", 1.0)
    w_normal = cfg.get("w_normal", 0.05)
    w_mono_normal_aux = float(cfg.get("w_mono_normal_aux", 0.0) or 0.0)
    w_plane = float(cfg.get("w_plane", 0.0) or 0.0)
    pilot_loss_audit_every = int(cfg.get("pilot_loss_audit_every", 0) or 0)
    pilot_plane_window_size = int(cfg.get("pilot_plane_window_size", 7))
    pilot_plane_stride = int(cfg.get("pilot_plane_stride", 4))
    pilot_plane_min_points = int(cfg.get("pilot_plane_min_points", 16))
    pilot_plane_alpha_threshold = float(
        cfg.get("pilot_plane_alpha_threshold", 0.5)
    )
    pilot_plane_max_depth_range = cfg.get("pilot_plane_max_depth_range", 1.0)
    if pilot_plane_max_depth_range is not None:
        pilot_plane_max_depth_range = float(pilot_plane_max_depth_range)
    pilot_plane_min_second_eigenvalue = float(
        cfg.get("pilot_plane_min_second_eigenvalue", 1.0e-10)
    )
    # P2-D: optional warm-up→ramp schedule for the depth/normal priors (lets the photometric
    # base settle before the MVS depth/normal supervision ramps in). Defaults reproduce a
    # plain constant weight, so prior configs without these keys are byte-identical.
    depth_warmup = int(cfg.get("depth_warmup", 0))
    depth_schedule = cfg.get("depth_schedule", "constant")
    depth_ramp_steps = int(cfg.get("depth_ramp_steps", 0))
    depth_final_weight = cfg.get("depth_final_weight")
    depth_final_factor = cfg.get("depth_final_factor")
    depth_weight_floor = cfg.get("depth_weight_floor")
    normal_warmup = int(cfg.get("normal_warmup", 0))
    normal_schedule = cfg.get("normal_schedule", "constant")
    normal_ramp_steps = int(cfg.get("normal_ramp_steps", 0))
    normal_final_weight = cfg.get("normal_final_weight")
    normal_final_factor = cfg.get("normal_final_factor")
    w_mono_depth = float(cfg.get("w_mono_depth", 0.0) or 0.0)
    mono_depth_warmup = int(cfg.get("mono_depth_warmup", 0))
    mono_depth_schedule = cfg.get("mono_depth_schedule", "constant")
    mono_depth_ramp_steps = int(cfg.get("mono_depth_ramp_steps", 0))
    mono_depth_final_weight = cfg.get("mono_depth_final_weight")
    mono_depth_final_factor = cfg.get("mono_depth_final_factor")
    mono_depth_loss = str(cfg.get("mono_depth_loss", "absolute_l1"))
    mono_normal_loss = str(cfg.get("mono_normal_loss", "global"))
    if mono_depth_loss not in {"absolute_l1", "ssi"}:
        raise ValueError("mono_depth_loss must be absolute_l1|ssi")
    if mono_normal_loss not in {"global", "target_region"}:
        raise ValueError("mono_normal_loss must be global|target_region")
    mono_target_buildings = {
        _short_building_id(value) for value in cfg.get("mono_target_buildings", [])
    }
    mono_target_min_pixels = int(cfg.get("mono_target_min_pixels", 64))
    target_region_priors = (
        (w_mono_depth > 0 and mono_depth_loss == "ssi")
        or (w_normal > 0 and mono_normal_loss == "target_region")
    )
    if target_region_priors and not mono_target_buildings:
        raise ValueError("target-region mono priors require mono_target_buildings")
    if target_region_priors and mono_target_min_pixels < 64:
        raise ValueError("mono_target_min_pixels must be >=64")
    w_nc = cfg.get("w_nc", 0.05)
    w_distort = cfg.get("w_distort", 100.0)   # 2DGS distortion reg
    distort_normalization = cfg.get("distort_normalization", "none")
    distort_norm_denominator = 1.0
    if distort_normalization in ("none", None):
        distort_normalization = "none"
    elif distort_normalization in ("scene_extent_sq", "scene_bbox_sq"):
        distort_norm_denominator = max(scene_extent_bbox * scene_extent_bbox, 1e-12)
    elif distort_normalization in ("scene_scale_sq", "strategy_scene_scale_sq"):
        distort_norm_denominator = max(scene_scale * scene_scale, 1e-12)
    else:
        raise ValueError(
            f"Unsupported distort_normalization={distort_normalization!r}; "
            "expected none|scene_extent_sq|scene_scale_sq"
        )
    w_sem = cfg.get("w_sem", 0.1)
    # P2 impl ②: release L_sem geometry detach so semantics can move geometry (default True
    # keeps the existing gradient-isolated behaviour, so the other configs are unaffected).
    sem_detach_geometry = cfg.get("sem_detach_geometry", True)
    # S3-A oracle class+instance-address mechanism test.  All three weights default to zero so
    # every pre-S3 configuration follows the previous execution path exactly.
    w_semdepth_smooth = float(cfg.get("w_semdepth_smooth", 0.0) or 0.0)
    w_semdepth_plane = float(cfg.get("w_semdepth_plane", 0.0) or 0.0)
    w_boundary_normal = float(cfg.get("w_boundary_normal", 0.0) or 0.0)
    semantic_geometry_warmup = int(cfg.get("semantic_geometry_warmup", 1500))
    semantic_geometry_audit_every = int(
        cfg.get("semantic_geometry_audit_every", cfg.get("loss_grad_audit_every", 0)) or 0
    )
    semantic_pi_target_buildings = {
        _short_building_id(value)
        for value in cfg.get(
            "semantic_pi_target_buildings",
            ["4907199", "8568391", "8568392"],
        )
    }
    semantic_pi_event_until_positive = bool(
        cfg.get("semantic_pi_event_until_positive", False)
    )
    (
        semantic_depth_enabled,
        boundary_normal_enabled,
        semantic_geometry_enabled,
        pjpl_gate_sweep_enabled,
    ) = _semantic_geometry_execution_flags(
        w_semdepth_smooth=w_semdepth_smooth,
        w_semdepth_plane=w_semdepth_plane,
        w_boundary_normal=w_boundary_normal,
        gate_attempt=int(cfg.get("s3_gate_attempt", 0)),
    )
    mono_depth_geometry_contract = _mono_depth_geometry_contract(
        semantic_geometry_enabled=semantic_geometry_enabled,
        w_mono_depth=w_mono_depth,
        mono_depth_loss=mono_depth_loss,
    )
    if min(w_semdepth_smooth, w_semdepth_plane, w_boundary_normal) < 0:
        raise ValueError("S3 semantic geometry weights must be non-negative")
    if semantic_geometry_warmup < 0:
        raise ValueError("semantic_geometry_warmup must be non-negative")
    semantic_region_cache = None
    semantic_geometry = None
    semantic_target_observations = {bid: 0 for bid in semantic_pi_target_buildings}
    semantic_pi_audited_targets: set[str] = set()
    if semantic_geometry_enabled:
        if not cfg.get("load_semantic", False):
            raise RuntimeError("S3 semantic geometry requires load_semantic=true")
        cache_root = cfg.get("semantic_region_cache")
        if semantic_depth_enabled and not cache_root:
            raise RuntimeError(
                "w_semdepth_smooth/plane>0 requires semantic_region_cache with oracle-ID-split NPZ files"
            )
        if cache_root:
            cache_path = Path(cache_root)
            if not cache_path.is_dir():
                raise FileNotFoundError(f"semantic_region_cache is not a directory: {cache_path}")
            missing_cache = [
                f"{Path(ds.frames[i].name).stem}.npz"
                for i in train_idx
                if not (cache_path / f"{Path(ds.frames[i].name).stem}.npz").exists()
            ]
            if semantic_depth_enabled and missing_cache:
                preview = ", ".join(missing_cache[:5])
                raise FileNotFoundError(
                    f"semantic_region_cache misses {len(missing_cache)} training views "
                    f"(first: {preview})"
                )
            semantic_region_cache = SemanticRegionCache(
                cache_path,
                expected_cutline_half_width_px=int(
                    cfg.get("semantic_cutline_half_width_px", 7)
                ),
                expected_source_component_min_pixels=int(
                    cfg.get("semantic_source_component_min_pixels", 256)
                ),
                expected_connectivity=int(cfg.get("semantic_component_connectivity", 8)),
                expected_footprint_buffer_m=float(
                    cfg.get("semantic_footprint_buffer_m", 20.0)
                ),
            )
            if semantic_depth_enabled:
                semantic_region_cache.validate_files(
                    [ds.frames[i].name for i in train_idx]
                )
        semantic_geometry = SemanticGuidedGeometry(
            semantic_region_cache,
            roof_class=int(cfg.get("semantic_roof_class", 1)),
            alpha_threshold=float(cfg.get("semantic_alpha_threshold", 0.5)),
            plane_min_pixels=int(cfg.get("semantic_plane_min_pixels", 64)),
            plane_refit_every=int(cfg.get("semantic_plane_refit_every", 500)),
            huber_delta=float(cfg.get("semantic_huber_delta", 1.0)),
            plane_irls_iterations=int(cfg.get("semantic_plane_irls_iterations", 5)),
            boundary_kernel_size=int(cfg.get("semantic_boundary_band_px", 5)),
        )
        print(
            "[S3-A] rendered-depth masked smooth+free-plane active; boundary normal "
            "reuses Omnidata; mono depth is allowed only as explicit target-region SSI"
        )
        print(
            f"[S3-A] warmup={semantic_geometry_warmup} "
            f"w_smooth={w_semdepth_smooth:g} w_plane={w_semdepth_plane:g} "
            f"w_nb={w_boundary_normal:g} cache={cache_root or 'not-required'}"
        )
    if target_region_priors:
        if not cfg.get("load_semantic", False):
            raise RuntimeError("target-region mono priors require load_semantic=true")
        cache_root = cfg.get("semantic_region_cache")
        if not cache_root:
            raise RuntimeError(
                "target-region mono priors require semantic_region_cache for address only"
            )
        if semantic_region_cache is None:
            cache_path = Path(cache_root)
            if not cache_path.is_dir():
                raise FileNotFoundError(
                    f"semantic_region_cache is not a directory: {cache_path}"
                )
            semantic_region_cache = SemanticRegionCache(
                cache_path,
                expected_cutline_half_width_px=int(
                    cfg.get("semantic_cutline_half_width_px", 7)
                ),
                expected_source_component_min_pixels=int(
                    cfg.get("semantic_source_component_min_pixels", 256)
                ),
                expected_connectivity=int(cfg.get("semantic_component_connectivity", 8)),
                expected_footprint_buffer_m=float(
                    cfg.get("semantic_footprint_buffer_m", 20.0)
                ),
            )
        semantic_region_cache.validate_files(
            [ds.frames[i].name for i in train_idx]
        )
        print(
            f"[mono-target] buildings={sorted(mono_target_buildings)} "
            f"normal={mono_normal_loss} depth={mono_depth_loss} "
            f"min_pixels={mono_target_min_pixels} address=semantic-region-cache"
        )
    w_structure = cfg.get("w_structure", 0.0)
    w_structure_na = cfg.get("w_structure_na", 1.0)
    w_structure_cp = cfg.get("w_structure_cp", 1.0)
    structure_warmup = int(cfg.get("structure_warmup", 15000))
    structure_regroup_every = int(cfg.get("structure_regroup_every", 500))
    structure_voxel_size = float(cfg.get("structure_voxel_size", 0.05))
    structure_n_directions = int(cfg.get("structure_n_directions", 12))
    structure_min_group = int(cfg.get("structure_min_group", 5))
    # P2-D: select grouping definition. g1 = patch-level (legacy; L_normal_align degenerates to
    # intra-patch smoothing). g2 = surface-level union-find (thesis target — coarse cell + merge).
    # g2_geometry = the first-wave geometry-only variant: selected footprint XY supplies only
    # a building partition and random/untrained semantic logits are never read.
    structure_grouping = cfg.get("structure_grouping", "g1")
    structure_merge_n_cos = float(cfg.get("structure_merge_n_cos", 0.92))   # g2 only
    structure_merge_d_tol = float(cfg.get("structure_merge_d_tol", 0.5))    # g2 only
    if structure_grouping not in ("g1", "g2", "g2_geometry"):
        raise ValueError(
            f"Unsupported structure_grouping={structure_grouping!r}; "
            "expected 'g1', 'g2', or 'g2_geometry'"
        )
    structure_partitions = ()
    structure_partition_path = None
    structure_partition_sha256 = None
    structure_partition_buildings: list[str] = []
    structure_partition_world_offset = cfg.get(
        "structure_partition_world_offset",
        cfg.get("world_offset", [690953.0, 5336071.0, 604.0]),
    )
    if structure_grouping == "g2_geometry":
        structure_partition_path = cfg.get("structure_partition_footprints")
        structure_partition_buildings = list(
            cfg.get("structure_partition_buildings") or []
        )
        if not structure_partition_path or not structure_partition_buildings:
            raise ValueError(
                "g2_geometry requires structure_partition_footprints and "
                "structure_partition_buildings"
            )
        structure_partition_file = Path(structure_partition_path)
        if not structure_partition_file.is_file():
            raise FileNotFoundError(structure_partition_file)
        structure_partitions = load_xy_partitions(
            structure_partition_file,
            structure_partition_buildings,
        )
        structure_partition_sha256 = hashlib.sha256(
            structure_partition_file.read_bytes()
        ).hexdigest()
        print(
            f"[structure] g2_geometry partitions={len(structure_partitions)} "
            f"source={structure_partition_file} sha256={structure_partition_sha256}"
        )

    def _group_primitives(centers, normals, sem_logits, scales):
        """Dispatch L_structure grouping per config (g1 patch-level | g2 surface-level).
        Both return the same (group_ids, rep_n, rep_d) signature."""
        if structure_grouping == "g2_geometry":
            partition_ids = assign_partition_ids(
                centers,
                structure_partitions,
                world_offset_xy=structure_partition_world_offset,
            )
            return group_primitives_g2_partitioned(
                centers=centers,
                normals=normals,
                partition_ids=partition_ids,
                scales=scales,
                voxel_size=structure_voxel_size,
                n_directions=structure_n_directions,
                merge_n_cos=structure_merge_n_cos,
                merge_d_tol=structure_merge_d_tol,
                min_group_size=structure_min_group,
            )
        if structure_grouping == "g2":
            return group_primitives_g2(
                centers=centers, normals=normals, sem_logits=sem_logits, scales=scales,
                voxel_size=structure_voxel_size, n_directions=structure_n_directions,
                merge_n_cos=structure_merge_n_cos, merge_d_tol=structure_merge_d_tol,
                min_group_size=structure_min_group)
        return group_primitives(
            centers=centers, normals=normals, sem_logits=sem_logits, scales=scales,
            voxel_size=structure_voxel_size, n_directions=structure_n_directions,
            min_group_size=structure_min_group)

    # group state (updated every T iters after warmup)
    _grp = {"group_ids": None, "rep_n": None, "rep_d": None}
    w_mutual = cfg.get("w_mutual", 0.0)
    mutual_warmup = int(cfg.get("mutual_warmup", 10000))
    mutual_schedule = cfg.get("mutual_schedule", "constant")
    mutual_ramp_steps = int(cfg.get("mutual_ramp_steps", 0))
    mutual_tau = float(cfg.get("mutual_tau", 0.15))
    mutual_height_th = float(cfg.get("mutual_height_th", 0.15))
    mutual_mode = cfg.get("mutual_mode", "full")
    mutual_audit_logging = bool(cfg.get("mutual_audit_logging", False))
    mutual_grad_audit_every = int(cfg.get("mutual_grad_audit_every", 0))
    mutual_log_class_stats_every = int(cfg.get("mutual_log_class_stats_every", 0))
    mutual_log_evidence_snapshot_every = int(cfg.get("mutual_log_evidence_snapshot_every", 0))
    mutual_enable_wall_vertical = bool(cfg.get("mutual_enable_wall_vertical", True))
    mutual_enable_roof_nonwall = bool(cfg.get("mutual_enable_roof_nonwall", True))
    mutual_enable_terrain_normal = bool(cfg.get("mutual_enable_terrain_normal", True))
    mutual_enable_terrain_height = bool(cfg.get("mutual_enable_terrain_height", True))
    mutual_enable_height_roof_side = bool(cfg.get("mutual_enable_height_roof_side", True))
    mutual_enable_height_terrain_side = bool(cfg.get("mutual_enable_height_terrain_side", True))
    mutual_w_wall_vertical = float(cfg.get("mutual_w_wall_vertical", 1.0))
    mutual_w_roof_nonwall = float(cfg.get("mutual_w_roof_nonwall", 1.0))
    mutual_w_terrain_normal = float(cfg.get("mutual_w_terrain_normal", 1.0))
    mutual_w_height = float(cfg.get("mutual_w_height", 1.0))
    mutual_w_height_roof = float(cfg.get("mutual_w_height_roof", 1.0))
    mutual_w_height_terrain = float(cfg.get("mutual_w_height_terrain", 1.0))
    mutual_terrain_gate_mode = cfg.get("mutual_terrain_gate_mode", "none")
    mutual_terrain_gate_conf_min = float(cfg.get("mutual_terrain_gate_conf_min", 0.0))
    mutual_terrain_gate_mass_min = float(cfg.get("mutual_terrain_gate_mass_min", 0.0))
    mutual_terrain_gate_entropy_max = float(cfg.get("mutual_terrain_gate_entropy_max", 1.0))
    mutual_terrain_height_reference = cfg.get("mutual_terrain_height_reference", "fixed")
    mutual_terrain_height_quantile = float(cfg.get("mutual_terrain_height_quantile", 0.5))
    mutual_terrain_height_margin = float(cfg.get("mutual_terrain_height_margin", 0.0))
    mutual_semcal_enabled = bool(cfg.get("mutual_semcal_enabled", False))
    mutual_semcal_classes = cfg.get("mutual_semcal_classes", "roof_wall")
    mutual_semcal_tau = float(cfg.get("mutual_semcal_tau", 0.05))
    mutual_semcal_weight_beta = float(cfg.get("mutual_semcal_weight_beta", 0.0))
    mutual_semcal_reliability_gate = cfg.get("mutual_semcal_reliability_gate", "conf_entropy")
    mutual_semcal_entropy_tau = float(cfg.get("mutual_semcal_entropy_tau", 0.75))
    mutual_semcal_entropy_alpha = float(cfg.get("mutual_semcal_entropy_alpha", 0.10))
    mutual_enable_roof_wall_relation = bool(cfg.get("mutual_enable_roof_wall_relation", False))
    mutual_enable_terrain_wall_relation = bool(cfg.get("mutual_enable_terrain_wall_relation", False))
    if mutual_enable_roof_wall_relation or mutual_enable_terrain_wall_relation:
        raise ValueError("FC-S5 relation hints are placeholders only; do not enable them in this run")
    if mutual_log_evidence_snapshot_every > 0:
        print("[mutual] evidence snapshot logging is reserved for offline export diagnostics in FC-S5")
    e_gravity = None
    grav_file = cfg.get("gravity_file")
    if grav_file and Path(grav_file).exists():
        import json as _json
        e_gravity = torch.tensor(_json.loads(Path(grav_file).read_text())["e_gravity"],
                                  dtype=torch.float32, device=device)
        print(f"[gravity] loaded e_g = {e_gravity.tolist()}")
    photo_lam = cfg.get("photo_lam", 0.2)

    # ---------- Phase B / B1: self-supervised multi-view consistency (L_mvc) ----------
    # PGSR/ULSR-style geometric consistency: reproject the source view's rendered depth
    # into a covisible neighbour and penalize depth+normal disagreement (occlusion-filtered).
    # NO GT labels. Default off (w_mvc=0) so all prior configs are byte-identical.
    w_mvc = cfg.get("w_mvc", 0.0)
    mvc_warmup = int(cfg.get("mvc_warmup", 7000))
    mvc_schedule = cfg.get("mvc_schedule", "constant")
    mvc_ramp_steps = int(cfg.get("mvc_ramp_steps", 0))
    mvc_every = int(cfg.get("mvc_every", 1))                  # fire every N iters (cost knob)
    mvc_neighbor_k = int(cfg.get("mvc_neighbor_k", 2))
    mvc_max_angle_deg = float(cfg.get("mvc_max_angle_deg", 40.0))
    mvc_min_baseline = float(cfg.get("mvc_min_baseline", 2.0))  # GS-local metres
    mvc_w_normal = float(cfg.get("mvc_w_normal", 0.5))
    mvc_rel_thresh = float(cfg.get("mvc_rel_thresh", 0.1))
    mvc_ref_detach = bool(cfg.get("mvc_ref_detach", True))     # render ref under no_grad (1-sided)
    _mvc_neighbors = None
    if w_mvc > 0:
        _mvc_neighbors = _build_mvc_neighbors(
            ds.frames, train_idx, mvc_neighbor_k, mvc_max_angle_deg, mvc_min_baseline)
        _ncov = sum(len(v) for v in _mvc_neighbors.values()) / max(1, len(_mvc_neighbors))
        print(f"[mvc] w_mvc={w_mvc} warmup={mvc_warmup} sched={mvc_schedule}+{mvc_ramp_steps} "
              f"every={mvc_every} k={mvc_neighbor_k} angle<{mvc_max_angle_deg} base>{mvc_min_baseline} "
              f"w_normal={mvc_w_normal} rel<{mvc_rel_thresh} ref_detach={mvc_ref_detach} "
              f"-> avg {_ncov:.1f} neighbors/view")
        # silent-zero guard (mirrors the depth/normal guard): a covisibility-empty index
        # would make L_mvc a no-op believed-on.
        if _ncov < 0.5:
            raise RuntimeError(
                "w_mvc>0 but the neighbor index is essentially empty — loosen "
                "mvc_max_angle_deg / mvc_min_baseline or check the poses.")

    max_iter = int(cfg["max_iter"])
    sh_up_every = int(cfg.get("sh_up_every", 1000))
    loss_grad_audit_every = int(cfg.get("loss_grad_audit_every", 0) or 0)
    loss_grad_audit_params = cfg.get("loss_grad_audit_params", "geometry")

    # P2-D silent-zero guard: w_depth/w_normal>0 contributes nothing unless per-view maps were
    # actually resolved on disk (the loss term is gated on the batch key). Turn that silent
    # no-op into a hard failure so a mis-located map is caught at startup, not believed-on.
    if w_depth > 0 and not any(f.depth_path is not None for f in ds.frames):
        raise RuntimeError(
            "w_depth>0 but NO depth maps resolved under data_root/stereo|depth — L_depth would be "
            "a silent no-op. Generate+stage maps (phases/p2-gsjso/scripts/prior_full_stereo.sh) or set w_depth=0.")
    if w_normal > 0 and not any(f.normal_path is not None for f in ds.frames):
        raise RuntimeError(
            "w_normal>0 but NO normal maps resolved under data_root/stereo|normal — L_normal would be "
            "a silent no-op. Generate+stage maps or set w_normal=0.")
    if w_mono_depth > 0 and not any(f.mono_depth_path is not None for f in ds.frames):
        raise RuntimeError(
            "w_mono_depth>0 but NO mono depth maps resolved via mono_depth_dir — "
            "L_mono_depth would be a silent no-op. Generate aligned mono-depth maps or set w_mono_depth=0.")
    if pilot_arm is not None:
        missing_depth = [frame.name for frame in ds.frames if frame.depth_path is None]
        missing_mvs_normal = [frame.name for frame in ds.frames if frame.normal_path is None]
        missing_mono_normal = [
            frame.name for frame in ds.frames if frame.mono_normal_path is None
        ]
        if missing_depth or missing_mvs_normal or missing_mono_normal:
            raise RuntimeError(
                "pilot prior inventory must cover every visible frame; "
                f"depth_missing={len(missing_depth)} "
                f"mvs_normal_missing={len(missing_mvs_normal)} "
                f"mono_normal_missing={len(missing_mono_normal)}"
            )
        if ds.roof_audit_mask_binding is None:
            raise RuntimeError("pilot roof_audit_mask binding is required")
        if pilot_arm == "01_surface" and ds.photo_mask_binding is not None:
            raise RuntimeError("arm 01 must not bind a photo loss mask")
        if pilot_arm in _PILOT_PHOTO_MASK_ARMS and ds.photo_mask_binding is None:
            raise RuntimeError(f"{pilot_arm} requires a bound photo loss mask")
        if pilot_arm in _PILOT_MEDIUM_ARMS and ds.plane_region_mask_binding is None:
            raise RuntimeError(f"{pilot_arm} requires a bound plane-region mask")
        print(
            f"[pilot] arm={pilot_arm} MVS+Omnidata maps={len(ds.frames)}/{len(ds.frames)} "
            f"photo_mask={'on' if ds.photo_mask_binding is not None else 'off'} "
            "roof_audit_mask=on "
            f"plane_region_mask={'on' if ds.plane_region_mask_binding is not None else 'off'}"
        )
    if w_depth > 0 or w_normal > 0 or w_mono_depth > 0:
        n_d = sum(f.depth_path is not None for f in ds.frames)
        n_n = sum(f.normal_path is not None for f in ds.frames)
        n_md = sum(f.mono_depth_path is not None for f in ds.frames)
        print(f"[prior] depth maps on {n_d}/{len(ds.frames)} frames, normal maps on {n_n}/{len(ds.frames)} "
              f"(w_depth={w_depth} sched={depth_schedule}@{depth_warmup}+{depth_ramp_steps}; "
              f"w_normal={w_normal} sched={normal_schedule}@{normal_warmup}+{normal_ramp_steps}; "
              f"mono_depth maps on {n_md}/{len(ds.frames)} frames, w_mono_depth={w_mono_depth} "
              f"sched={mono_depth_schedule}@{mono_depth_warmup}+{mono_depth_ramp_steps})")
    if w_distort > 0:
        print(
            f"[distort] w_distort={w_distort:g} normalization={distort_normalization} "
            f"denom={distort_norm_denominator:.6g} "
            f"(scene_extent_bbox={scene_extent_bbox:.6g}m; scene_scale={scene_scale:.6g}m)"
        )

    effective_config = {
        "scene_scale_strategy_m": scene_scale,
        "scene_extent_bbox_m": scene_extent_bbox,
        "distort_normalization": distort_normalization,
        "distort_norm_denominator": distort_norm_denominator,
        "distort_formula": "loss_distort = mean(rend_dist) / denominator; total += w_distort * loss_distort",
        "w_distort": w_distort,
        "depth_schedule": depth_schedule,
        "depth_warmup": depth_warmup,
        "depth_ramp_steps": depth_ramp_steps,
        "depth_base_weight": w_depth,
        "depth_final_weight": depth_final_weight,
        "depth_final_factor": depth_final_factor,
        "depth_weight_floor": depth_weight_floor,
        "normal_dir": primary_normal_dir,
        "mono_depth_dir": cfg.get("mono_depth_dir"),
        "mono_depth_base_weight": w_mono_depth,
        "mono_depth_schedule": mono_depth_schedule,
        "mono_depth_warmup": mono_depth_warmup,
        "mono_depth_ramp_steps": mono_depth_ramp_steps,
        "mono_depth_final_weight": mono_depth_final_weight,
        "mono_depth_final_factor": mono_depth_final_factor,
        "mono_depth_loss": mono_depth_loss,
        "mono_normal_loss": mono_normal_loss,
        "mono_target_buildings": sorted(mono_target_buildings),
        "mono_target_min_pixels": mono_target_min_pixels,
        "mono_depth_mask_rule": (
            "mono_depth_mask AND oracle-address target region"
            if mono_depth_loss == "ssi"
            else "mono_depth_mask AND NOT depth_mask when depth_mask is present"
        ),
        "mono_target_region_aggregate": "mean_of_per_region_means",
        "mono_depth_geometry_contract": mono_depth_geometry_contract,
        "view_roles": view_role_audit,
        "surface_seed": surface_seed_audit,
        "surface_seed_protect": surface_seed_protect,
        "legacy_mvs_seed_protect": legacy_mvs_seed_protect,
        "seed_protect": seed_protect,
        "seed_protect_until_iter": seed_protect_until_iter,
        "mvs_seed_init_opacity": (
            float(mvs_seed_init_opacity)
            if mvs_seed_init_opacity is not None
            else 0.10
        ),
        "seed_protected_lineage": (
            "surface+MVS" if surface_seed_protect and legacy_mvs_seed_protect
            else "surface" if surface_seed_protect
            else "MVS" if legacy_mvs_seed_protect
            else "none"
        ),
        "surface_seed_prune_opa_initial": seed_prune_schedule.get("seed_prune_opa_initial"),
        "surface_seed_prune_opa_final": seed_prune_schedule.get("seed_prune_opa_final"),
        "surface_seed_prune_switch_iter": seed_prune_schedule.get("seed_prune_switch_iter"),
        "prune_opa": _strat_kwargs["prune_opa"],
        "grow_grad2d": _strat_kwargs["grow_grad2d"],
        "grow_scale3d": _strat_kwargs["grow_scale3d"],
        "prune_scale3d": _strat_kwargs["prune_scale3d"],
        "refine_start_iter": _strat_kwargs["refine_start_iter"],
        "refine_stop_iter": _strat_kwargs["refine_stop_iter"],
        "refine_every": _strat_kwargs["refine_every"],
        "reset_every": _strat_kwargs["reset_every"],
        "final_prune_opa": float(cfg.get("final_prune_opa", 0.0) or 0.0),
        "elongation_filter": elongation_filter,
        "elongation_axis_ratio_threshold": elongation_axis_ratio_threshold,
        "elongation_axis_ratio_formula": "min(exp(scale0), exp(scale1)) / max(exp(scale0), exp(scale1))",
        "loss_grad_audit_every": loss_grad_audit_every,
        "loss_grad_audit_params": loss_grad_audit_params,
        "structure_grouping": structure_grouping,
        "structure_partition_footprints": (
            str(structure_partition_path) if structure_partition_path else None
        ),
        "structure_partition_footprints_sha256": structure_partition_sha256,
        "structure_partition_buildings": structure_partition_buildings,
        "structure_partition_world_offset": structure_partition_world_offset,
        "structure_semantic_logits_used": structure_grouping != "g2_geometry",
    }
    if pilot_arm is not None:
        effective_config.update(
            {
                "mono_normal_dir": auxiliary_normal_dir,
                "pilot_arm": pilot_arm,
                "pilot_mask_binding": ds.pilot_mask_audit,
                "w_mono_normal_aux": w_mono_normal_aux,
                "mono_normal_aux_schedule": "same_fraction_as_primary_normal_schedule",
                "mono_normal_gate_cache": "view_static_cpu_bool_no_rng_no_loss_change",
                "w_plane": w_plane,
                "pilot_plane_mode": (
                    "soft_local_global_coverage"
                    if pilot_arm == "03_plane_soft"
                    else "medium_local_window_mask_restricted"
                    if pilot_arm in _PILOT_MEDIUM_ARMS
                    else "off"
                ),
                "pilot_plane_window_size": pilot_plane_window_size,
                "pilot_plane_stride": pilot_plane_stride,
                "pilot_plane_min_points": pilot_plane_min_points,
                "pilot_plane_alpha_threshold": pilot_plane_alpha_threshold,
                "pilot_plane_max_depth_range": pilot_plane_max_depth_range,
                "pilot_plane_min_second_eigenvalue": pilot_plane_min_second_eigenvalue,
                "pilot_loss_audit_every": pilot_loss_audit_every,
                "pilot_loss_audit_terms": [
                    "pho", "dep", "nrm", "nc", "str.na", "str.cp", "plane"
                ],
                "pilot_loss_audit_csv_paths": list(PILOT_FULL_STATE_CSV_PATHS),
                "pilot_flattening_role": "audit_only_never_weighted",
                "pilot_plane_guided_init": pilot_plane_init_effective,
            }
        )
    if semantic_geometry_enabled:
        effective_config.update(
            {
                "s3_claim_scope": cfg.get("s3_claim_scope"),
                "absolute_mono_depth_forbidden": True,
                "mono_depth_ssi_enabled": bool(
                    mono_depth_geometry_contract["mono_depth_ssi_enabled"]
                ),
                "semantic_region_cache": cfg.get("semantic_region_cache"),
                "semantic_geometry_warmup": semantic_geometry_warmup,
                "semantic_geometry_active_updates": max(0, max_iter - semantic_geometry_warmup),
                "w_semdepth_smooth": w_semdepth_smooth,
                "w_semdepth_plane": w_semdepth_plane,
                "w_boundary_normal": w_boundary_normal,
                "semantic_roof_class": int(cfg.get("semantic_roof_class", 1)),
                "semantic_alpha_threshold": float(cfg.get("semantic_alpha_threshold", 0.5)),
                "semantic_source_component_min_pixels": int(cfg.get("semantic_source_component_min_pixels", 256)),
                "semantic_component_connectivity": int(cfg.get("semantic_component_connectivity", 8)),
                "semantic_cutline_half_width_px": int(cfg.get("semantic_cutline_half_width_px", 7)),
                "semantic_footprint_buffer_m": float(cfg.get("semantic_footprint_buffer_m", 20.0)),
                "semantic_plane_min_pixels": int(cfg.get("semantic_plane_min_pixels", 64)),
                "semantic_plane_refit_every": int(cfg.get("semantic_plane_refit_every", 500)),
                "semantic_plane_fit": "free-orientation weighted-PCA IRLS/Huber; n,d detached between refits",
                "semantic_boundary_band_kernel_px": int(cfg.get("semantic_boundary_band_px", 5)),
                "semantic_boundary_band_effective_radius_px": int(cfg.get("semantic_boundary_band_px", 5)) // 2,
                "semantic_boundary_band_definition": "true-width class band = dilate_5(M - erode_3(M)); instance cutline excluded",
                "semantic_smooth_aggregate": "sum of per-region Huber means",
                "semantic_plane_aggregate": "global pixel mean of residuals to per-region robust planes",
                "semantic_gate_share_denominator": "baseline effective components + combined weighted semdepth + weighted boundary_normal; smooth/plane detail audit-only",
                "semantic_pi_target_buildings": sorted(semantic_pi_target_buildings),
                "semantic_pi_event_until_positive": semantic_pi_event_until_positive,
                "semantic_geometry_audit_every": semantic_geometry_audit_every,
                "semantic_delta_keys": [
                    "w_semdepth_smooth",
                    "w_semdepth_plane",
                    "w_boundary_normal",
                    "semantic_geometry_warmup",
                    "semantic_region_cache",
                    "semantic_roof_class",
                    "semantic_alpha_threshold",
                    "semantic_source_component_min_pixels",
                    "semantic_component_connectivity",
                    "semantic_cutline_half_width_px",
                    "semantic_footprint_buffer_m",
                    "semantic_plane_min_pixels",
                    "semantic_plane_refit_every",
                    "semantic_huber_delta",
                    "semantic_plane_irls_iterations",
                    "semantic_boundary_band_px",
                    "semantic_pi_target_buildings",
                    "semantic_pi_event_until_positive",
                ],
            }
        )
    if full_state["enabled"]:
        effective_config.update(
            {
                "full_state_checkpoint_enabled": True,
                "full_state_checkpoint_steps": list(full_state["checkpoint_steps"]),
                "full_state_loss_csv_paths": list(full_state["loss_csv_paths"]),
                "full_state_step_semantics": "completed_optimizer_updates",
            }
        )

    start_completed_steps = 0
    pending_resume_rng_state = None
    learning_runs_started = 0
    full_state_binding: dict[str, str] = {}
    full_state_manifest: dict[str, Any] = {}
    full_state_manifest_path = out_dir / "full_state_manifest.json"
    resume_selected_path: Optional[Path] = None
    resume_selected_sha256: Optional[str] = None
    resume_skipped: list[dict[str, str]] = []
    loss_cursor_actions: list[str] = []

    if full_state["enabled"]:
        # Hash only the stable, training-effective section. Runtime selection
        # metadata is added below after strict binding has been resolved.
        full_state_binding = full_state_binding_sha256(
            cfg=cfg,
            effective_training_config=effective_config,
            out_dir=out_dir,
        )
        resume_request = full_state["resume_request"]
        selected_checkpoint: Any = None
        if resume_request is not None and resume_request.lower() in {"auto", "latest"}:
            discovery = discover_latest_checkpoint(
                out_dir / "ckpt",
                expected_binding_sha256=full_state_binding,
                map_location="cpu",
            )
            for skipped in discovery.skipped:
                record = {
                    "path": str(skipped.path),
                    "error_type": skipped.error_type,
                    "reason": skipped.reason,
                }
                resume_skipped.append(record)
                print(
                    f"[resume] skipped {skipped.path.name}: "
                    f"{skipped.error_type}: {skipped.reason}",
                    flush=True,
                )
            selected_checkpoint = discovery.selected
            if selected_checkpoint is None:
                if resume_request.lower() == "latest" or discovery.skipped:
                    raise RuntimeError(
                        "full_state_resume requested a checkpoint, but no valid "
                        "binding-matched checkpoint remains after discovery"
                    )
                print("[resume] auto found no checkpoint; starting fresh", flush=True)
        elif resume_request is not None:
            selected_checkpoint = Path(resume_request)

        if selected_checkpoint is not None:
            restored = restore_training_checkpoint(
                selected_checkpoint,
                expected_binding_sha256=full_state_binding,
                device=device,
                optimizer_builder=_configured_optimizers,
                restore_rng=False,
                strict_cuda_rng=bool(full_state["strict_cuda_rng"]),
            )
            model = restored.model
            optimizers = restored.optimizers
            strategy = restored.strategy
            strategy_state = restored.strategy_state
            params = build_param_dict(model)
            strategy.check_sanity(params, optimizers)
            (
                _grp,
                semantic_target_observations,
                semantic_pi_audited_targets,
            ) = restore_trainer_runtime_state(
                restored.grouping_state,
                semantic_geometry=semantic_geometry,
                expected_semantic_targets=set(semantic_pi_target_buildings),
            )
            start_completed_steps = restored.completed_steps
            if start_completed_steps > max_iter:
                raise RuntimeError(
                    "resume checkpoint is beyond configured max_iter: "
                    f"completed={start_completed_steps}, max_iter={max_iter}"
                )
            loss_cursor_actions = restore_loss_csv_cursor(
                out_dir,
                full_state["loss_csv_paths"],
                restored.loss_log_cursor,
                expected_completed_steps=start_completed_steps,
            )
            for action in loss_cursor_actions:
                print(f"[resume] loss CSV rollback: {action}", flush=True)
            learning_runs_started = restored.learning_runs_started
            pending_resume_rng_state = restored.checkpoint.payload["rng_state"]
            resume_selected_path = restored.checkpoint.path.resolve()
            resume_selected_sha256 = restored.checkpoint.sha256
            print(
                f"[resume] selected {resume_selected_path.name} "
                f"completed_updates={start_completed_steps}; "
                f"next_update={start_completed_steps + 1}",
                flush=True,
            )
        else:
            prior_runs = read_learning_runs_started(full_state_manifest_path)
            learning_runs_started = prior_runs

        if pilot_arm in _PILOT_MEDIUM_ARMS:
            if (
                pilot_plane_init_preoptimizer_mode == "resume_verify_only"
                and selected_checkpoint is None
            ):
                raise RuntimeError(
                    "medium-arm resume request resolved no checkpoint after its "
                    "pre-optimizer audit was verified; disable full_state_resume "
                    "to make a new fresh run"
                )
            if (
                pilot_plane_init_preoptimizer_mode == "fresh_auto_candidate"
                and selected_checkpoint is not None
            ):
                raise RuntimeError(
                    "full_state_resume=auto discovered a checkpoint without the "
                    "required prior plane-guided initialization audit"
                )

        planned_learning_runs_started, learning_run_increment_pending = (
            learning_runs_for_process(
                learning_runs_started,
                resuming=selected_checkpoint is not None,
                will_train=max_iter > start_completed_steps,
            )
        )
        # The preregistered counter changes only after optimizer update 1 has
        # actually completed.  Keep the durable manifest at the prior value
        # during setup (and if setup fails before the first update).
        learning_run_incremented = False
        if not learning_run_increment_pending:
            learning_runs_started = planned_learning_runs_started
        full_state_manifest = {
            "schema": FULL_STATE_MANIFEST_SCHEMA,
            "output_path": str(out_dir.resolve()),
            "config_path": str(config_path.resolve()),
            "config_file_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "binding_excluded_config_keys": sorted(
                FULL_STATE_BINDING_EXCLUDED_CONFIG_KEYS
            ),
            "binding_sha256": full_state_binding,
            "resume_requested": full_state["resume_request"],
            "resume_selected": (
                str(resume_selected_path) if resume_selected_path is not None else None
            ),
            "resume_selected_sha256": resume_selected_sha256,
            "resume_skipped": resume_skipped,
            "loss_csv_rollback_actions": loss_cursor_actions,
            "start_completed_steps": start_completed_steps,
            "next_update": (
                start_completed_steps + 1
                if start_completed_steps < max_iter
                else None
            ),
            "max_iter": max_iter,
            "checkpoint_steps": list(full_state["checkpoint_steps"]),
            "step_semantics": "completed_optimizer_updates",
            "loss_csv_paths": list(full_state["loss_csv_paths"]),
            "learning_runs_started": learning_runs_started,
            "learning_runs_incremented_this_process": learning_run_incremented,
            "learning_run_increment_pending_first_optimizer_update": (
                learning_run_increment_pending
            ),
            "latest_full_checkpoint": (
                {
                    "path": str(resume_selected_path),
                    "sha256": resume_selected_sha256,
                    "completed_steps": start_completed_steps,
                }
                if resume_selected_path is not None
                else None
            ),
            "last_completed_steps": start_completed_steps,
        }
        atomic_write_json(full_state_manifest_path, full_state_manifest)
        effective_config["full_state_runtime"] = {
            "binding_sha256": full_state_binding,
            "manifest": str(full_state_manifest_path),
            "resume_requested": full_state["resume_request"],
            "resume_selected": full_state_manifest["resume_selected"],
            "start_completed_steps": start_completed_steps,
            "next_update": full_state_manifest["next_update"],
            "learning_runs_started": learning_runs_started,
            "learning_runs_incremented_this_process": learning_run_incremented,
        }
    if pilot_arm in _PILOT_MEDIUM_ARMS:
        assert pilot_plane_init_result is not None
        init_runtime = {
            "mode": (
                "checkpoint_resume_verified"
                if resume_selected_path is not None
                else "fresh_applied"
            ),
            "initializer_reapplied_after_checkpoint_restore": False,
            "checkpoint_quaternions_restored": resume_selected_path is not None,
            "resume_completed_steps": int(start_completed_steps),
            "matched_seed_count": pilot_plane_init_result.audit["counts"][
                "matched_seed_count"
            ],
            "matched_seed_fraction": pilot_plane_init_result.audit["counts"][
                "matched_seed_fraction"
            ],
            "resume_verification_audit_path": (
                str(pilot_plane_init_resume_audit_path)
                if pilot_plane_init_resume_audit_path is not None
                else None
            ),
        }
        effective_config["pilot_plane_guided_init"]["runtime"] = init_runtime
    # Soft/strong plane arms may not begin (or resume) an optimizer update until
    # the gsplat 2DGS fixed-thickness invariant is proven.  This is a gate and an
    # audit only: its value is never added to ``loss_total`` or the plane share.
    if pilot_arm in {"03_plane_soft", *_PILOT_MEDIUM_ARMS}:
        flattening_start = audit_2dgs_flattening_invariant(model.scales)
        flattening_start_payload = {
            "schema": "jointbuildgs.pilot_1wave.flattening_start_gate.v1",
            "pilot_arm": pilot_arm,
            "evaluated_before_optimizer_update": True,
            "resume_completed_steps": int(start_completed_steps),
            "passed": flattening_start.passed,
            "expected_thickness": flattening_start.expected_thickness,
            "max_abs_error": (
                flattening_start.max_abs_error
                if math.isfinite(flattening_start.max_abs_error)
                else None
            ),
            "finite_count": flattening_start.finite_count,
            "total_count": flattening_start.total_count,
            "contributes_to_loss": flattening_start.contributes_to_loss,
        }
        flattening_start_path = out_dir / "audit/pilot_flattening_start_gate.json"
        atomic_write_json(flattening_start_path, flattening_start_payload)
        effective_config["pilot_flattening_start_gate"] = {
            **flattening_start_payload,
            "path": str(flattening_start_path),
        }
        if not flattening_start.passed:
            raise RuntimeError(
                "pilot 2DGS flattening start gate failed; no optimizer update executed"
            )
    (out_dir / "effective_config.json").write_text(json.dumps(effective_config, indent=2) + "\n")
    (out_dir / "view_roles.json").write_text(
        json.dumps(view_role_audit, indent=2) + "\n"
    )
    if surface_seed_audit is not None:
        (out_dir / "surface_seed_audit.json").write_text(
            json.dumps(surface_seed_audit, indent=2) + "\n"
        )

    if full_state["enabled"]:
        print(
            f"[train] max_iter={max_iter} start_completed={start_completed_steps} "
            f"out={out_dir}"
        )
    else:
        print(f"[train] max_iter={max_iter}  out={out_dir}")
    pbar = tqdm(range(start_completed_steps, max_iter), desc="train")
    t0 = time.time()
    # MVS/Omnidata targets are immutable, hence the fixed 16x16 agreement gate
    # is view-static.  Cache bool gates on CPU after their first exact build;
    # rebuilding the Python-audited patch grid at every sampled update would be
    # pure overhead and would not change any loss value.
    pilot_mono_gate_cache: Dict[str, tuple[torch.Tensor, Dict[str, Any]]] = {}

    # Restore after every setup action so the first view/neighbor draw is the
    # exact draw that followed the saved completed optimizer update.
    if pending_resume_rng_state is not None:
        restore_rng_state(
            pending_resume_rng_state,
            strict_cuda=bool(full_state["strict_cuda_rng"]),
        )

    for it in pbar:
        # pick a random training view
        idx = training_view_index(
            train_idx,
            iteration=it,
            sequential=bool(cfg.get("sequential", False)),
        )
        batch = ds[idx]
        rgb_gt = batch["rgb"].to(device)
        w2c = batch["w2c"].to(device)
        K = batch["K"].to(device)
        H, W = batch["height"], batch["width"]

        target_region_mask = None
        target_region_ids = None
        target_region_address_audit = None
        if target_region_priors:
            assert semantic_region_cache is not None
            target_frame = semantic_region_cache.get(batch["name"], H, W, device)
            (
                target_region_mask,
                target_region_ids,
                target_region_address_audit,
            ) = _target_region_mask(target_frame, mono_target_buildings)

        out = render(model, w2c, K, W, H, sh_degree=model.active_sh_degree, render_mode="RGB+ED")
        rgb_pred = out["rgb"]
        depth_pred = out["depth"]
        n_render = out["normal_render"]
        n_surf = out["normal_surf"]
        alpha = out["alpha"]
        distort = out["distort"]
        meta = out["meta"]

        # track grad for densification (gsplat DefaultStrategy hook)
        strategy.step_pre_backward(params, optimizers, strategy_state, it, meta)

        # losses.  Arm 01 receives no photo-mask tensor; the common roof audit
        # scope is loaded through a different key and is never consulted here.
        photo_loss_mask = None
        if pilot_arm is not None:
            if pilot_arm == "01_surface":
                if "photo_mask" in batch:
                    raise RuntimeError("arm 01 batch unexpectedly contains photo_mask")
            else:
                if "photo_mask" not in batch:
                    raise RuntimeError(f"{pilot_arm} batch is missing required photo_mask")
                photo_loss_mask = batch["photo_mask"].to(device)
        loss_photo = L.l_photo(
            rgb_pred,
            rgb_gt,
            lam=photo_lam,
            mask=photo_loss_mask,
        )
        loss_total = w_photo * loss_photo

        if "depth" in batch:
            d_gt = batch["depth"].to(device)
            d_m = batch["depth_mask"].to(device)
            loss_depth = L.l_depth(depth_pred, d_gt, d_m)
            w_depth_eff = _scheduled_weight(
                w_depth,
                it,
                depth_warmup,
                depth_schedule,
                depth_ramp_steps,
                final_weight=depth_final_weight,
                final_factor=depth_final_factor,
            )
            if depth_weight_floor is not None:
                w_depth_eff = max(float(w_depth_eff), float(depth_weight_floor))
            loss_total = loss_total + w_depth_eff * loss_depth
        else:
            loss_depth = torch.tensor(0.0, device=device)
            w_depth_eff = 0.0

        if "mono_depth" in batch:
            md_gt = batch["mono_depth"].to(device)
            md_m = batch["mono_depth_mask"].to(device)
            if mono_depth_loss == "ssi":
                if w_mono_depth > 0:
                    assert target_region_mask is not None and target_region_ids is not None
                    md_m = md_m & target_region_mask
                    loss_mono_depth, mono_depth_stats = L.l_mono_depth_ssi(
                        depth_pred,
                        md_gt,
                        target_region_ids,
                        md_m,
                        min_pixels=mono_target_min_pixels,
                    )
                else:
                    loss_mono_depth = depth_pred.sum() * 0.0
                    mono_depth_stats = {
                        "eligible_region_count": 0,
                        "mode": "ssi_weight_zero",
                    }
            else:
                if "depth_mask" in batch:
                    md_m = md_m & (~batch["depth_mask"].to(device))
                if bool(md_m.any().item()):
                    loss_mono_depth = L.l_depth(depth_pred, md_gt, md_m)
                else:
                    loss_mono_depth = torch.tensor(0.0, device=device)
                mono_depth_stats = {
                    "eligible_region_count": 0,
                    "mode": "legacy_absolute_l1",
                }
            w_mono_depth_eff = _scheduled_weight(
                w_mono_depth,
                it,
                mono_depth_warmup,
                mono_depth_schedule,
                mono_depth_ramp_steps,
                final_weight=mono_depth_final_weight,
                final_factor=mono_depth_final_factor,
            )
            loss_total = loss_total + w_mono_depth_eff * loss_mono_depth
        else:
            loss_mono_depth = torch.tensor(0.0, device=device)
            w_mono_depth_eff = 0.0
            mono_depth_stats = {"eligible_region_count": 0, "mode": "map_absent"}

        n_gt = None
        n_m = None
        loss_n_mvs = torch.tensor(0.0, device=device)
        loss_n_aux = torch.tensor(0.0, device=device)
        w_mono_normal_aux_eff = 0.0
        mono_gt = None
        mono_gate = None
        mono_gate_audit: Dict[str, Any] = {
            "mode": "disabled",
            "eligible_patch_count": 0,
            "gated_pixel_count": 0,
        }
        if "normal" in batch:
            n_gt = batch["normal"].to(device)
            n_m = batch["normal_mask"].to(device)
            if pilot_arm is not None:
                # Locked first-wave primary: MVS remains active on every valid
                # MVS pixel and is never narrowed to the mono gate.
                loss_n_mvs = L.l_normal(n_render, n_gt, w2c, n_m)
                if "mono_normal" not in batch or "mono_normal_mask" not in batch:
                    raise RuntimeError(
                        f"pilot Omnidata normal missing for active view {batch['name']!r}"
                )
                mono_gt = batch["mono_normal"].to(device)
                mono_gate_key = str(batch["name"])
                cached_gate = pilot_mono_gate_cache.get(mono_gate_key)
                if cached_gate is None:
                    # Build once on CPU to avoid one GPU synchronization per
                    # audited patch in the exact gate implementation.
                    mono_gate_cpu, full_gate_audit = build_mono_normal_gate(
                        batch["normal"],
                        batch["mono_normal"],
                        primary_valid=batch["normal_mask"],
                        auxiliary_valid=batch["mono_normal_mask"],
                    )
                    mono_gate_audit = {
                        key: value
                        for key, value in full_gate_audit.items()
                        if key != "patches"
                    }
                    pilot_mono_gate_cache[mono_gate_key] = (
                        mono_gate_cpu,
                        mono_gate_audit,
                    )
                    mono_gate = mono_gate_cpu.to(device=device)
                else:
                    mono_gate = cached_gate[0].to(device=device)
                    mono_gate_audit = cached_gate[1]
                loss_n_aux = l_auxiliary_mono_normal(
                    n_render,
                    mono_gt,
                    mono_gate,
                )
                loss_n = loss_n_mvs
                mono_normal_stats = {
                    "eligible_region_count": 0,
                    "mode": "pilot_fixed_patch_gate_auxiliary",
                }
            elif mono_normal_loss == "target_region":
                if w_normal > 0:
                    assert target_region_mask is not None and target_region_ids is not None
                    n_m = n_m & target_region_mask
                    loss_n, mono_normal_stats = L.l_normal_target_regions(
                        n_render,
                        n_gt,
                        target_region_ids,
                        n_m,
                        min_pixels=mono_target_min_pixels,
                    )
                else:
                    loss_n = n_render.sum() * 0.0
                    mono_normal_stats = {
                        "eligible_region_count": 0,
                        "mode": "target_region_weight_zero",
                    }
            else:
                loss_n = L.l_normal(n_render, n_gt, w2c, n_m)
                mono_normal_stats = {
                    "eligible_region_count": 0,
                    "mode": "legacy_global",
                }
            w_normal_eff = _scheduled_weight(
                w_normal,
                it,
                normal_warmup,
                normal_schedule,
                normal_ramp_steps,
                final_weight=normal_final_weight,
                final_factor=normal_final_factor,
            )
            if pilot_arm is not None:
                # Auxiliary follows the exact activation fraction of the MVS
                # schedule while retaining its own resolved numeric base weight.
                schedule_fraction = float(w_normal_eff) / float(w_normal)
                w_mono_normal_aux_eff = w_mono_normal_aux * schedule_fraction
                loss_total = (
                    loss_total
                    + w_normal_eff * loss_n_mvs
                    + w_mono_normal_aux_eff * loss_n_aux
                )
            else:
                loss_total = loss_total + w_normal_eff * loss_n
        else:
            loss_n = torch.tensor(0.0, device=device)
            w_normal_eff = 0.0
            mono_normal_stats = {"eligible_region_count": 0, "mode": "map_absent"}

        loss_nc = L.l_nc(n_render, n_surf, alpha=alpha.detach())
        loss_total = loss_total + w_nc * loss_nc

        loss_dist_raw = distort.mean()
        loss_dist = loss_dist_raw / distort_norm_denominator
        loss_total = loss_total + w_distort * loss_dist

        # First-wave plane ladder.  Every plane arm uses the same local rendered-
        # depth windows and edge guard.  The medium pair merely restricts those
        # windows by its bound plane mask and uses its stronger prelocked
        # ``w_plane``; fitting one plane to a binary union is intentionally
        # forbidden because it can collapse distinct roof facets.  04a/04b share
        # this exact branch, with mask provenance as their only difference.
        loss_plane = torch.tensor(0.0, device=device)
        pilot_plane_count = 0
        pilot_plane_point_count = 0
        if pilot_arm == "03_plane_soft":
            plane_result = _pilot_plane_window_coplanarity(
                pilot_arm=pilot_arm,
                depth=depth_pred,
                intrinsics=K,
                alpha=alpha,
                plane_region_mask=None,
                audit_mask=None,
                window_size=pilot_plane_window_size,
                stride=pilot_plane_stride,
                min_points=pilot_plane_min_points,
                alpha_threshold=pilot_plane_alpha_threshold,
                max_depth_range=pilot_plane_max_depth_range,
                min_second_eigenvalue=pilot_plane_min_second_eigenvalue,
            )
            loss_plane = plane_result.loss
            pilot_plane_count = plane_result.plane_count
            pilot_plane_point_count = plane_result.point_count
            loss_total = loss_total + w_plane * loss_plane
        elif pilot_arm in _PILOT_MEDIUM_ARMS:
            if "plane_region_mask" not in batch:
                raise RuntimeError(
                    f"{pilot_arm} batch is missing the locked plane_region_mask"
                )
            plane_result = _pilot_plane_window_coplanarity(
                pilot_arm=pilot_arm,
                depth=depth_pred,
                intrinsics=K,
                alpha=alpha,
                plane_region_mask=batch["plane_region_mask"],
                audit_mask=None,
                window_size=pilot_plane_window_size,
                stride=pilot_plane_stride,
                min_points=pilot_plane_min_points,
                alpha_threshold=pilot_plane_alpha_threshold,
                max_depth_range=pilot_plane_max_depth_range,
                min_second_eigenvalue=pilot_plane_min_second_eigenvalue,
            )
            loss_plane = plane_result.loss
            pilot_plane_count = plane_result.plane_count
            pilot_plane_point_count = plane_result.point_count
            loss_total = loss_total + w_plane * loss_plane

        # L_mvc (Phase B / B1): self-supervised multi-view geometric consistency.
        # Reproject this (source) view's rendered depth into a covisible neighbour and
        # penalize depth+normal disagreement. The neighbour is rendered under no_grad
        # (mvc_ref_detach), so the gradient flows one-sidedly into the source-view
        # geometry — pulling floating facets toward the multi-view-consistent surface.
        loss_mvc = torch.tensor(0.0, device=device)
        loss_mvc_depth = torch.tensor(0.0, device=device)
        loss_mvc_normal = torch.tensor(0.0, device=device)
        w_mvc_eff = 0.0
        mvc_n_inlier = 0
        if (w_mvc > 0 and it >= mvc_warmup and (it % mvc_every == 0)
                and _mvc_neighbors is not None):
            nbrs = _mvc_neighbors.get(idx) or []
            if nbrs:
                j = random.choice(nbrs)
                bj = ds[j]
                w2c_j = bj["w2c"].to(device)
                K_j = bj["K"].to(device)
                Hj, Wj = bj["height"], bj["width"]
                if mvc_ref_detach:
                    with torch.no_grad():
                        out_j = render(model, w2c_j, K_j, Wj, Hj,
                                       sh_degree=model.active_sh_degree, render_mode="RGB+ED")
                else:
                    out_j = render(model, w2c_j, K_j, Wj, Hj,
                                   sh_degree=model.active_sh_degree, render_mode="RGB+ED")
                mvc = l_multiview_consistency(
                    depth_src=depth_pred, normal_src=n_render, K_src=K, w2c_src=w2c,
                    depth_ref=out_j["depth"], normal_ref=out_j["normal_render"],
                    K_ref=K_j, w2c_ref=w2c_j,
                    w_normal=mvc_w_normal, rel_thresh=mvc_rel_thresh,
                )
                loss_mvc = mvc["total"]
                loss_mvc_depth = mvc["depth"]
                loss_mvc_normal = mvc["normal"]
                mvc_n_inlier = mvc["n_inlier"]
                w_mvc_eff = w_mvc * _ramp_weight_scale(it, mvc_warmup, mvc_schedule, mvc_ramp_steps)
                loss_total = loss_total + w_mvc_eff * loss_mvc

        # Semantic CE (only if GT provided and w_sem > 0).
        sem_gt = (
            batch["semantic"].to(device)
            if "semantic" in batch
            and (w_sem > 0 or (semantic_geometry_enabled and it >= semantic_geometry_warmup))
            else None
        )
        if sem_gt is not None and w_sem > 0 and hasattr(model, "sem_logits"):
            from .renderer import render_semantic
            sem_pred = render_semantic(model, w2c, K, W, H, sem_detach_geometry=sem_detach_geometry)
            loss_sem = L.l_sem(sem_pred, sem_gt, ignore_index=0)
            loss_total = loss_total + w_sem * loss_sem
        else:
            loss_sem = torch.tensor(0.0, device=device)
        loss_base_for_grad = loss_total

        # S3-A: semantics addresses geometry, but supplies no depth values.  The
        # first active update is exactly ``semantic_geometry_warmup`` (1500 in
        # the locked configs), hence a max_iter=2500 probe has 1000 active updates.
        loss_semdepth_smooth = depth_pred.sum() * 0.0
        loss_semdepth_plane = depth_pred.sum() * 0.0
        loss_boundary_normal = n_render.sum() * 0.0
        weighted_semdepth = depth_pred.sum() * 0.0
        weighted_boundary_normal = n_render.sum() * 0.0
        s3_result: Dict[str, object] = {
            "smooth": loss_semdepth_smooth,
            "plane": loss_semdepth_plane,
            "boundary_normal": loss_boundary_normal,
            "region_rows": [],
            "metadata": {},
            "region_ids": None,
            "cutline_mask": None,
            "smooth_valid_stencil_count": 0,
            "boundary_valid_pixel_count": 0,
        }
        semantic_geometry_active = semantic_geometry_enabled and it >= semantic_geometry_warmup
        semantic_pi_event_targets: set[str] = set()
        if semantic_geometry_active:
            if sem_gt is None:
                raise RuntimeError(f"S3 semantic label missing for active view {batch['name']!r}")
            assert semantic_geometry is not None
            s3_result = semantic_geometry(
                iteration=it,
                view_key=batch["name"],
                depth=depth_pred,
                alpha=alpha,
                K=K,
                semantic=sem_gt,
                normal_render=n_render,
                normal_target=n_gt,
                normal_mask=n_m,
                depth_anchor_mask=(batch["depth_mask"].to(device) if "depth_mask" in batch else None),
                enable_semdepth=semantic_depth_enabled,
                enable_boundary_normal=boundary_normal_enabled,
            )
            loss_semdepth_smooth = s3_result["smooth"]
            loss_semdepth_plane = s3_result["plane"]
            loss_boundary_normal = s3_result["boundary_normal"]
            weighted_semdepth = (
                w_semdepth_smooth * loss_semdepth_smooth
                + w_semdepth_plane * loss_semdepth_plane
            )
            weighted_boundary_normal = w_boundary_normal * loss_boundary_normal
            loss_total = loss_total + weighted_semdepth + weighted_boundary_normal
            s3_result.update(
                {
                    "weight_smooth": w_semdepth_smooth,
                    "weight_plane": w_semdepth_plane,
                    "weight_boundary_normal": w_boundary_normal,
                    "weighted_smooth": float(
                        (w_semdepth_smooth * loss_semdepth_smooth).detach().cpu().item()
                    ),
                    "weighted_plane": float(
                        (w_semdepth_plane * loss_semdepth_plane).detach().cpu().item()
                    ),
                }
            )
            seen_targets = {
                _short_building_id(row.get("building_id"))
                for row in s3_result.get("region_rows", [])
                if _short_building_id(row.get("building_id")) in semantic_pi_target_buildings
            }
            for bid in seen_targets:
                semantic_target_observations[bid] += 1
            # A periodic audit alone can miss a rare target merely because its
            # view was sampled between audit ticks.  Force the first observed
            # event for every P-I target into the audit without changing the
            # training-view sampler or optimizer path.
            if semantic_pi_event_until_positive:
                semantic_pi_event_targets = seen_targets - semantic_pi_audited_targets

        # L_mutual (intra-primitive, operates directly on primitives, no rendering)
        loss_mut_total = torch.tensor(0.0, device=device)
        loss_mut_vert = torch.tensor(0.0, device=device)
        loss_mut_slope = torch.tensor(0.0, device=device)
        loss_mut_horiz = torch.tensor(0.0, device=device)
        loss_mut_height = torch.tensor(0.0, device=device)
        loss_mut_wall_vertical = torch.tensor(0.0, device=device)
        loss_mut_roof_nonwall = torch.tensor(0.0, device=device)
        loss_mut_terrain_normal = torch.tensor(0.0, device=device)
        loss_mut_terrain_height = torch.tensor(0.0, device=device)
        loss_mut_height_roof = torch.tensor(0.0, device=device)
        loss_mut_height_terrain = torch.tensor(0.0, device=device)
        loss_mut_semcal = torch.tensor(0.0, device=device)
        loss_mut_semcal_reliability = torch.tensor(0.0, device=device)
        loss_mut_semcal_active_frac = torch.tensor(0.0, device=device)
        loss_mut_semcal_entropy = torch.tensor(0.0, device=device)
        mutual_weight_scale = _ramp_weight_scale(it, mutual_warmup, mutual_schedule, mutual_ramp_steps)
        if (w_mutual > 0 and mutual_weight_scale > 0
                and e_gravity is not None and hasattr(model, "sem_logits")):
            mut = l_mutual(
                normals=model.normals(),
                centers=model.means,
                sem_logits=model.sem_logits,
                e_gravity=e_gravity,
                tau=mutual_tau,
                height_th=mutual_height_th,
                w_vert=mutual_w_wall_vertical,
                w_slope=mutual_w_roof_nonwall,
                w_horiz=mutual_w_terrain_normal,
                w_height=mutual_w_height,
                w_height_roof=mutual_w_height_roof,
                w_height_terrain=mutual_w_height_terrain,
                mode=mutual_mode,
                enable_wall_vertical=mutual_enable_wall_vertical,
                enable_roof_nonwall=mutual_enable_roof_nonwall,
                enable_terrain_normal=mutual_enable_terrain_normal,
                enable_terrain_height=mutual_enable_terrain_height,
                enable_height_roof_side=mutual_enable_height_roof_side,
                enable_height_terrain_side=mutual_enable_height_terrain_side,
                terrain_gate_mode=mutual_terrain_gate_mode,
                terrain_gate_conf_min=mutual_terrain_gate_conf_min,
                terrain_gate_mass_min=mutual_terrain_gate_mass_min,
                terrain_gate_entropy_max=mutual_terrain_gate_entropy_max,
                terrain_height_reference=mutual_terrain_height_reference,
                terrain_height_quantile=mutual_terrain_height_quantile,
                terrain_height_margin=mutual_terrain_height_margin,
                enable_sem_geom_calib=mutual_semcal_enabled,
                semcal_classes=mutual_semcal_classes,
                semcal_tau=mutual_semcal_tau,
                semcal_weight_beta=mutual_semcal_weight_beta,
                semcal_reliability_gate=mutual_semcal_reliability_gate,
                semcal_entropy_tau=mutual_semcal_entropy_tau,
                semcal_entropy_alpha=mutual_semcal_entropy_alpha,
            )
            loss_mut_total = mut["total"]
            loss_mut_vert = mut["vert"]; loss_mut_slope = mut["slope"]
            loss_mut_horiz = mut["horiz"]; loss_mut_height = mut["height"]
            loss_mut_wall_vertical = mut["wall_vertical"]
            loss_mut_roof_nonwall = mut["roof_nonwall"]
            loss_mut_terrain_normal = mut["terrain_normal"]
            loss_mut_terrain_height = mut["terrain_height"]
            loss_mut_height_roof = mut["height_roof"]
            loss_mut_height_terrain = mut["height_terrain"]
            loss_mut_semcal = mut["sem_geom_calib"]
            loss_mut_semcal_reliability = mut["sem_geom_reliability"]
            loss_mut_semcal_active_frac = mut["sem_geom_active_frac"]
            loss_mut_semcal_entropy = mut["sem_geom_entropy"]
            loss_total = loss_total + (w_mutual * mutual_weight_scale) * loss_mut_total

        # L_structure (inter-primitive, Mechanism 2)
        loss_str_total = torch.tensor(0.0, device=device)
        loss_str_na = torch.tensor(0.0, device=device)
        loss_str_cp = torch.tensor(0.0, device=device)
        n_groups = 0; n_in_group = 0
        if w_structure > 0 and it >= structure_warmup and hasattr(model, "sem_logits"):
            # Re-group every T iter (and on first activation)
            if (_grp["group_ids"] is None
                    or (it - structure_warmup) % structure_regroup_every == 0):
                gids, rep_n, rep_d = _group_primitives(
                    centers=model.means.detach(),
                    normals=model.normals().detach(),
                    sem_logits=model.sem_logits.detach(),
                    scales=model.scales.detach(),
                )
                _grp["group_ids"] = gids
                _grp["rep_n"] = rep_n
                _grp["rep_d"] = rep_d
            # If N changed due to densification (shouldn't after refine_stop), drop stale groups
            if _grp["group_ids"].shape[0] != model.means.shape[0]:
                _grp["group_ids"] = None  # will regroup next matching iter
            else:
                sd = l_structure(
                    normals=model.normals(),
                    centers=model.means,
                    group_ids=_grp["group_ids"],
                    rep_normals=_grp["rep_n"],
                    rep_d=_grp["rep_d"],
                    w_normal_align=w_structure_na,
                    w_coplanar=w_structure_cp,
                )
                loss_str_total = sd["total"]
                loss_str_na = sd["normal_align"]
                loss_str_cp = sd["coplanar"]
                n_in_group = sd["n_used"]
                n_groups = _grp["rep_n"].shape[0]
                loss_total = loss_total + w_structure * loss_str_total

        if pilot_arm is not None and not bool(torch.isfinite(loss_total).item()):
            audit_dir = out_dir / "audit"
            audit_dir.mkdir(exist_ok=True)
            failure = {
                "step": int(it),
                "view": str(batch["name"]),
                "total_loss": float(loss_total.detach().cpu().item()),
                "pilot_arm": pilot_arm,
                "pilot_plane": float(loss_plane.detach().cpu().item()),
                "pilot_mvs_normal": float(loss_n_mvs.detach().cpu().item()),
                "pilot_mono_normal_aux": float(loss_n_aux.detach().cpu().item()),
            }
            with (audit_dir / "nonfinite_loss.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(failure, allow_nan=True) + "\n")
            raise FloatingPointError(
                f"Non-finite pilot loss at step={it} view={batch['name']!r}; "
                f"recorded in {audit_dir / 'nonfinite_loss.jsonl'}"
            )

        # Locked seven-term first-wave audit.  ``iter`` means completed optimizer
        # update number, matching the 5k checkpoint naming; the values are those
        # used to form that update immediately below.
        completed_update = it + 1
        pilot_audit_step = pilot_arm is not None and (
            completed_update % pilot_loss_audit_every == 0
            or completed_update in set(full_state["checkpoint_steps"])
        )
        if pilot_audit_step:
            if "roof_audit_mask" not in batch:
                raise RuntimeError(
                    f"pilot roof audit mask missing for active view {batch['name']!r}"
                )
            roof_audit_mask = batch["roof_audit_mask"].to(device)
            if roof_audit_mask.dtype != torch.bool or roof_audit_mask.shape != (H, W):
                raise RuntimeError("roof_audit_mask must be bool HxW at training resolution")

            # Pixel terms are recomputed in the common projected-footprint mask.
            loss_photo_roof = L.l_photo(
                rgb_pred,
                rgb_gt,
                lam=photo_lam,
                mask=roof_audit_mask,
            )
            if "depth" in batch:
                loss_depth_roof = L.l_depth(
                    depth_pred,
                    d_gt,
                    d_m & roof_audit_mask,
                )
            else:
                loss_depth_roof = depth_pred.sum() * 0.0
            loss_n_mvs_roof = L.l_normal(
                n_render,
                n_gt,
                w2c,
                n_m & roof_audit_mask,
            )
            assert mono_gt is not None and mono_gate is not None
            loss_n_aux_roof = l_auxiliary_mono_normal(
                n_render,
                mono_gt,
                mono_gate & roof_audit_mask,
            )
            loss_nc_roof = pilot_masked_normal_consistency(
                n_render,
                n_surf,
                roof_audit_mask,
                alpha=alpha,
            )

            # Plane audit uses the same primitive as its training arm, intersected
            # only for audit with the common mask.  The training loss above remains
            # unchanged by this recomputation.
            loss_plane_roof = depth_pred.sum() * 0.0
            if pilot_arm == "03_plane_soft":
                roof_plane_result = _pilot_plane_window_coplanarity(
                    pilot_arm=pilot_arm,
                    depth=depth_pred,
                    intrinsics=K,
                    alpha=alpha,
                    plane_region_mask=None,
                    audit_mask=roof_audit_mask,
                    window_size=pilot_plane_window_size,
                    stride=pilot_plane_stride,
                    min_points=pilot_plane_min_points,
                    alpha_threshold=pilot_plane_alpha_threshold,
                    max_depth_range=pilot_plane_max_depth_range,
                    min_second_eigenvalue=pilot_plane_min_second_eigenvalue,
                )
                loss_plane_roof = roof_plane_result.loss
            elif pilot_arm in _PILOT_MEDIUM_ARMS:
                roof_plane_result = _pilot_plane_window_coplanarity(
                    pilot_arm=pilot_arm,
                    depth=depth_pred,
                    intrinsics=K,
                    alpha=alpha,
                    plane_region_mask=batch["plane_region_mask"],
                    audit_mask=roof_audit_mask,
                    window_size=pilot_plane_window_size,
                    stride=pilot_plane_stride,
                    min_points=pilot_plane_min_points,
                    alpha_threshold=pilot_plane_alpha_threshold,
                    max_depth_range=pilot_plane_max_depth_range,
                    min_second_eigenvalue=pilot_plane_min_second_eigenvalue,
                )
                loss_plane_roof = roof_plane_result.loss

            # In g2_geometry, a nonnegative group ID can only be produced inside
            # one of the selected footprint partitions; outside and ungrouped
            # primitives are both -1 and do not enter L_structure.  Reusing this
            # exact loss-side membership avoids a second million-point CPU XY
            # assignment at every audit interval.
            primitive_scope = (
                _grp["group_ids"] >= 0
                if _grp["group_ids"] is not None
                else torch.zeros(model.num_points, dtype=torch.bool, device=device)
            )
            (
                loss_str_na_roof,
                loss_str_cp_roof,
                pilot_structure_roof_count,
            ) = pilot_structure_terms_in_scope(
                normals=model.normals(),
                centers=model.means,
                group_ids=_grp["group_ids"],
                rep_normals=_grp["rep_n"],
                rep_d=_grp["rep_d"],
                primitive_scope=primitive_scope,
            )

            nrm_raw_public, nrm_weighted_public = pilot_public_normal_term(
                loss_n_mvs,
                loss_n_aux,
                primary_weight=w_normal_eff,
                auxiliary_weight=w_mono_normal_aux_eff,
            )
            _nrm_roof_raw, nrm_roof_weighted_public = pilot_public_normal_term(
                loss_n_mvs_roof,
                loss_n_aux_roof,
                primary_weight=w_normal_eff,
                auxiliary_weight=w_mono_normal_aux_eff,
            )

            raw_public = {
                "pho": loss_photo,
                "dep": loss_depth,
                "nrm": nrm_raw_public,
                "nc": loss_nc,
                "str.na": loss_str_na,
                "str.cp": loss_str_cp,
                "plane": loss_plane,
            }
            weighted_public = {
                "pho": w_photo * loss_photo,
                "dep": w_depth_eff * loss_depth,
                "nrm": nrm_weighted_public,
                "nc": w_nc * loss_nc,
                "str.na": w_structure * w_structure_na * loss_str_na,
                "str.cp": w_structure * w_structure_cp * loss_str_cp,
                "plane": w_plane * loss_plane,
            }
            roof_weighted_public = {
                "pho": w_photo * loss_photo_roof,
                "dep": w_depth_eff * loss_depth_roof,
                "nrm": nrm_roof_weighted_public,
                "nc": w_nc * loss_nc_roof,
                "str.na": w_structure * w_structure_na * loss_str_na_roof,
                "str.cp": w_structure * w_structure_cp * loss_str_cp_roof,
                "plane": w_plane * loss_plane_roof,
            }
            append_pilot_loss_share_rows(
                out_dir,
                iteration=completed_update,
                raw=raw_public,
                weighted=weighted_public,
                roof_weighted=roof_weighted_public,
            )

            flattening_audit = audit_2dgs_flattening_invariant(model.scales)
            append_pilot_loss_detail_rows(
                out_dir,
                [
                    {
                        "iter": completed_update,
                        "detail": "nrm.mvs_primary",
                        "raw": float(loss_n_mvs.detach().cpu()),
                        "weight": float(w_normal_eff),
                        "weighted": float((w_normal_eff * loss_n_mvs).detach().cpu()),
                        "roof_raw": float(loss_n_mvs_roof.detach().cpu()),
                        "roof_weighted": float(
                            (w_normal_eff * loss_n_mvs_roof).detach().cpu()
                        ),
                        "count": int(n_m.sum().detach().cpu()),
                        "status": "primary",
                    },
                    {
                        "iter": completed_update,
                        "detail": "nrm.omnidata_aux_16x16_64_15deg",
                        "raw": float(loss_n_aux.detach().cpu()),
                        "weight": float(w_mono_normal_aux_eff),
                        "weighted": float(
                            (w_mono_normal_aux_eff * loss_n_aux).detach().cpu()
                        ),
                        "roof_raw": float(loss_n_aux_roof.detach().cpu()),
                        "roof_weighted": float(
                            (w_mono_normal_aux_eff * loss_n_aux_roof).detach().cpu()
                        ),
                        "count": int(mono_gate_audit["gated_pixel_count"]),
                        "status": (
                            f"eligible_patches={mono_gate_audit['eligible_patch_count']}"
                        ),
                    },
                    {
                        "iter": completed_update,
                        "detail": "plane.rendered_depth_l1",
                        "raw": float(loss_plane.detach().cpu()),
                        "weight": float(w_plane),
                        "weighted": float((w_plane * loss_plane).detach().cpu()),
                        "roof_raw": float(loss_plane_roof.detach().cpu()),
                        "roof_weighted": float(
                            (w_plane * loss_plane_roof).detach().cpu()
                        ),
                        "count": int(pilot_plane_point_count),
                        "status": f"planes={pilot_plane_count}",
                    },
                    {
                        "iter": completed_update,
                        "detail": "str.footprint_xy_scope",
                        "raw": "",
                        "weight": "",
                        "weighted": "",
                        "roof_raw": "",
                        "roof_weighted": "",
                        "count": pilot_structure_roof_count,
                        "status": "audit_only_scope_count",
                    },
                    {
                        "iter": completed_update,
                        "detail": "flattening.2dgs_fixed_thickness",
                        "raw": flattening_audit.max_abs_error,
                        "weight": 0.0,
                        "weighted": 0.0,
                        "roof_raw": "",
                        "roof_weighted": "",
                        "count": flattening_audit.finite_count,
                        "status": "pass" if flattening_audit.passed else "fail",
                    },
                ],
            )
            if pilot_arm in _PILOT_MEDIUM_ARMS:
                append_pilot_plane_photo_ratio(
                    out_dir,
                    iteration=completed_update,
                    weighted_roof_plane=roof_weighted_public["plane"],
                    weighted_roof_photo=roof_weighted_public["pho"],
                )

        if semantic_geometry_enabled and not bool(torch.isfinite(loss_total).item()):
            audit_dir = out_dir / "audit"
            audit_dir.mkdir(exist_ok=True)
            failure = {
                "step": int(it),
                "view": str(batch["name"]),
                "total_loss": float(loss_total.detach().cpu().item()),
                "semdepth_smooth": float(loss_semdepth_smooth.detach().cpu().item()),
                "semdepth_plane": float(loss_semdepth_plane.detach().cpu().item()),
                "boundary_normal": float(loss_boundary_normal.detach().cpu().item()),
            }
            with (audit_dir / "nonfinite_loss.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(failure, allow_nan=True) + "\n")
            raise FloatingPointError(
                f"Non-finite S3 total loss at step={it} view={batch['name']!r}; "
                f"recorded in {audit_dir / 'nonfinite_loss.jsonl'}"
            )

        if mutual_grad_audit_every > 0 and it % mutual_grad_audit_every == 0:
            _write_mutual_grad_diagnostics(
                writer=writer,
                out_dir=out_dir,
                it=it,
                model=model,
                losses={
                    "base": loss_base_for_grad,
                    "photo": loss_photo,
                    "depth": loss_depth,
                    "mono_depth": loss_mono_depth,
                    "normal": loss_n,
                    "semantic": loss_sem,
                    "mutual": loss_mut_total,
                },
            )

        loss_grad_audit_step = loss_grad_audit_every > 0 and (
            it % loss_grad_audit_every == 0
            or (semantic_geometry_enabled and it == max_iter - 1)
        )
        if loss_grad_audit_step:
            with torch.no_grad():
                p_for_audit = psnr(rgb_pred.clamp(0, 1), rgb_gt)
            audit_rowspec = {
                "photo": (loss_photo, float(w_photo), w_photo * loss_photo),
                "depth": (loss_depth, float(w_depth_eff), w_depth_eff * loss_depth),
                "mono_depth": (loss_mono_depth, float(w_mono_depth_eff), w_mono_depth_eff * loss_mono_depth),
                "normal": (
                    loss_n_mvs + loss_n_aux if pilot_arm is not None else loss_n,
                    1.0 if pilot_arm is not None else float(w_normal_eff),
                    (
                        w_normal_eff * loss_n_mvs
                        + w_mono_normal_aux_eff * loss_n_aux
                        if pilot_arm is not None
                        else w_normal_eff * loss_n
                    ),
                ),
                "nc": (loss_nc, float(w_nc), w_nc * loss_nc),
                "distort": (loss_dist, float(w_distort), w_distort * loss_dist),
                "semantic": (loss_sem, float(w_sem), w_sem * loss_sem),
                "mvc": (loss_mvc, float(w_mvc_eff), w_mvc_eff * loss_mvc),
                "mutual": (loss_mut_total, float(w_mutual * mutual_weight_scale), (w_mutual * mutual_weight_scale) * loss_mut_total),
                "structure": (loss_str_total, float(w_structure), w_structure * loss_str_total),
            }
            if semantic_geometry_enabled:
                # Only the combined weighted semdepth component enters the gate
                # denominator.  Smooth/plane detail is written separately below.
                audit_rowspec["semdepth"] = (
                    weighted_semdepth,
                    1.0,
                    weighted_semdepth,
                )
                audit_rowspec["boundary_normal"] = (
                    loss_boundary_normal,
                    float(w_boundary_normal if semantic_geometry_active else 0.0),
                    weighted_boundary_normal,
                )
            _write_loss_grad_audit(
                out_dir=out_dir,
                writer=writer,
                it=it,
                model=model,
                params=_audit_params(model, loss_grad_audit_params),
                rowspec=audit_rowspec,
                total_loss=loss_total,
                psnr_value=p_for_audit,
                n_primitives=model.num_points,
                audit_only_rowspec=(
                    {
                        "semdepth_smooth": (
                            loss_semdepth_smooth,
                            float(w_semdepth_smooth if semantic_geometry_active else 0.0),
                            (w_semdepth_smooth if semantic_geometry_active else 0.0)
                            * loss_semdepth_smooth,
                        ),
                        "semdepth_plane": (
                            loss_semdepth_plane,
                            float(w_semdepth_plane if semantic_geometry_active else 0.0),
                            (w_semdepth_plane if semantic_geometry_active else 0.0)
                            * loss_semdepth_plane,
                        ),
                    }
                    if semantic_geometry_enabled
                    else None
                ),
            )

        semantic_geometry_periodic_audit = (
            semantic_geometry_audit_every > 0
            and (it % semantic_geometry_audit_every == 0 or it == max_iter - 1)
        )
        semantic_geometry_audit_step = semantic_geometry_active and (
            semantic_geometry_periodic_audit or bool(semantic_pi_event_targets)
        )
        if semantic_geometry_audit_step:
            positive_targets = _write_semantic_geometry_audit(
                out_dir=out_dir,
                it=it,
                view_name=str(batch["name"]),
                result=s3_result,
                weighted_semdepth=weighted_semdepth,
                weighted_boundary_normal=weighted_boundary_normal,
                depth_pred=depth_pred,
                target_buildings=semantic_pi_target_buildings,
                target_observations=semantic_target_observations,
            )
            if semantic_pi_event_until_positive:
                semantic_pi_audited_targets.update(positive_targets)

        # backward
        for opt in optimizers.values():
            opt.zero_grad(set_to_none=True)
        loss_total.backward()

        strategy.step_post_backward(params, optimizers, strategy_state, it, meta)

        densify_events = getattr(strategy, "densify_audit_events", [])
        if densify_events:
            _append_densify_audit(out_dir, densify_events)
            strategy.densify_audit_events = []

        # sync params dict -> model (gsplat strategy may replace nn.Parameters on grow/prune)
        _sync_params_to_model(params, model)

        # (P2 make-or-break C) seed-survival diagnostic (every 5k + at 500 for pre-check)
        if seed_protect and (it == 500 or (it > 0 and it % 5000 == 0)):
            _log_seed_survival(it, model, strategy_state["is_seed"], seed_log_boxes, writer)

        for opt in optimizers.values():
            opt.step()

        if full_state["enabled"] and learning_run_increment_pending:
            # This is the first point at which the approved definition
            # "optimizer step 1 executed" is true for a fresh process.
            learning_runs_started = planned_learning_runs_started
            learning_run_increment_pending = False
            learning_run_incremented = True
            full_state_manifest["learning_runs_started"] = learning_runs_started
            full_state_manifest["learning_runs_incremented_this_process"] = True
            full_state_manifest[
                "learning_run_increment_pending_first_optimizer_update"
            ] = False
            full_state_manifest["learning_run_counter_incremented_at_completed_step"] = (
                it + 1
            )
            atomic_write_json(full_state_manifest_path, full_state_manifest)

        # SH warmup
        if (it + 1) % sh_up_every == 0:
            model.oneup_sh_degree()

        # logging
        if it % 10 == 0:
            with torch.no_grad():
                p = psnr(rgb_pred.clamp(0, 1), rgb_gt)
            writer.add_scalar("loss/total", loss_total.item(), it)
            writer.add_scalar("loss/photo", loss_photo.item(), it)
            writer.add_scalar("loss/depth", loss_depth.item(), it)
            writer.add_scalar("loss/mono_depth", loss_mono_depth.item(), it)
            writer.add_scalar("loss/normal", loss_n.item(), it)
            if pilot_arm is not None:
                writer.add_scalar("loss/normal_mvs_primary", loss_n_mvs.item(), it)
                writer.add_scalar("loss/normal_omnidata_aux", loss_n_aux.item(), it)
                writer.add_scalar(
                    "loss/normal_public_weighted",
                    float(
                        (
                            w_normal_eff * loss_n_mvs
                            + w_mono_normal_aux_eff * loss_n_aux
                        ).detach().cpu()
                    ),
                    it,
                )
                writer.add_scalar("loss/plane", loss_plane.item(), it)
                writer.add_scalar(
                    "loss_weight/normal_omnidata_aux",
                    float(w_mono_normal_aux_eff),
                    it,
                )
                writer.add_scalar("loss_weight/plane", float(w_plane), it)
                writer.add_scalar("stats/pilot_plane_count", pilot_plane_count, it)
                writer.add_scalar(
                    "stats/pilot_plane_point_count", pilot_plane_point_count, it
                )
            writer.add_scalar("loss/nc", loss_nc.item(), it)
            writer.add_scalar("loss/distort", loss_dist.item(), it)
            writer.add_scalar("loss/distort_raw", loss_dist_raw.item(), it)
            writer.add_scalar("loss_weight/depth", float(w_depth_eff), it)
            writer.add_scalar("loss_weight/mono_depth", float(w_mono_depth_eff), it)
            writer.add_scalar("loss_weight/normal", float(w_normal_eff), it)
            writer.add_scalar("loss_weight/distort", float(w_distort), it)
            if target_region_priors:
                writer.add_scalar(
                    "stats/mono_depth_eligible_regions",
                    int(mono_depth_stats.get("eligible_region_count", 0)),
                    it,
                )
                writer.add_scalar(
                    "stats/mono_normal_eligible_regions",
                    int(mono_normal_stats.get("eligible_region_count", 0)),
                    it,
                )
                _append_mono_target_audit(
                    out_dir,
                    {
                        "step": int(it),
                        "view": str(batch["name"]),
                        "target_buildings": sorted(mono_target_buildings),
                        "address": target_region_address_audit,
                        "mono_depth": mono_depth_stats,
                        "mono_normal": mono_normal_stats,
                    },
                )
            if elongation_filter:
                writer.add_scalar(
                    "stats/elongation_filter_blocked",
                    int(strategy_state.get("elongation_filter_blocked", 0)),
                    it,
                )
                writer.add_scalar(
                    "stats/elongation_axis_ratio_threshold",
                    float(strategy_state.get("elongation_axis_ratio_threshold", elongation_axis_ratio_threshold)),
                    it,
                )
            grow_step = int(strategy_state.get("last_grow_step", -1))
            prune_step = int(strategy_state.get("last_prune_step", -1))
            grow_duplicated = int(strategy_state.get("last_grow_duplicated", 0)) if grow_step == it else 0
            grow_split = int(strategy_state.get("last_grow_split", 0)) if grow_step == it else 0
            prune_candidates = int(strategy_state.get("last_prune_candidates", 0)) if prune_step == it else 0
            prune_seed_protected = int(strategy_state.get("last_prune_seed_protected", 0)) if prune_step == it else 0
            pruned = int(strategy_state.get("last_pruned", 0)) if prune_step == it else 0
            writer.add_scalar("stats/grow_duplicated", grow_duplicated, it)
            writer.add_scalar("stats/grow_split", grow_split, it)
            writer.add_scalar("stats/grow_total", grow_duplicated + grow_split, it)
            writer.add_scalar("stats/cum_grow_duplicated", int(strategy_state.get("cum_grow_duplicated", 0)), it)
            writer.add_scalar("stats/cum_grow_split", int(strategy_state.get("cum_grow_split", 0)), it)
            writer.add_scalar("stats/prune_candidates", prune_candidates, it)
            writer.add_scalar("stats/prune_seed_protected", prune_seed_protected, it)
            writer.add_scalar("stats/pruned", pruned, it)
            writer.add_scalar("stats/cum_prune_candidates", int(strategy_state.get("cum_prune_candidates", 0)), it)
            writer.add_scalar("stats/cum_prune_seed_protected", int(strategy_state.get("cum_prune_seed_protected", 0)), it)
            writer.add_scalar("stats/cum_pruned", int(strategy_state.get("cum_pruned", 0)), it)
            writer.add_scalar("stats/seed_protect_active", int(bool(strategy_state.get("last_seed_protect_active", False))), it)
            writer.add_scalar("stats/seed_protected_count", int(strategy_state.get("seed_protected_count", 0)), it)
            if surface_seed_protect:
                writer.add_scalar(
                    "stats/effective_prune_opa",
                    float(strategy_state.get("effective_prune_opa", _strat_kwargs["prune_opa"])),
                    it,
                )
                writer.add_scalar(
                    "stats/effective_reset_opa",
                    float(strategy_state.get("effective_reset_opa", 2.0 * _strat_kwargs["prune_opa"])),
                    it,
                )
            writer.add_scalar("loss/mvc", loss_mvc.item(), it)
            writer.add_scalar("loss/mvc_depth", float(loss_mvc_depth), it)
            writer.add_scalar("loss/mvc_normal", float(loss_mvc_normal), it)
            writer.add_scalar("stats/mvc_n_inlier", mvc_n_inlier, it)
            writer.add_scalar("loss/sem", loss_sem.item(), it)
            if semantic_geometry_enabled:
                writer.add_scalar("loss/semdepth_smooth", loss_semdepth_smooth.item(), it)
                writer.add_scalar("loss/semdepth_plane", loss_semdepth_plane.item(), it)
                writer.add_scalar("loss/semdepth_weighted", weighted_semdepth.item(), it)
                writer.add_scalar("loss/boundary_normal", loss_boundary_normal.item(), it)
                writer.add_scalar("loss/boundary_normal_weighted", weighted_boundary_normal.item(), it)
                writer.add_scalar(
                    "stats/semdepth_valid_stencils",
                    int(s3_result.get("smooth_valid_stencil_count", 0)),
                    it,
                )
                writer.add_scalar(
                    "stats/boundary_normal_valid_pixels",
                    int(s3_result.get("boundary_valid_pixel_count", 0)),
                    it,
                )
            writer.add_scalar("loss/mutual", loss_mut_total.item(), it)
            writer.add_scalar("loss/mutual_vert", loss_mut_vert.item(), it)
            writer.add_scalar("loss/mutual_slope", loss_mut_slope.item(), it)
            writer.add_scalar("loss/mutual_horiz", loss_mut_horiz.item(), it)
            writer.add_scalar("loss/mutual_height", loss_mut_height.item(), it)
            if mutual_audit_logging:
                writer.add_scalar("loss/mutual_wall_vertical", loss_mut_wall_vertical.item(), it)
                writer.add_scalar("loss/mutual_roof_nonwall", loss_mut_roof_nonwall.item(), it)
                writer.add_scalar("loss/mutual_terrain_normal", loss_mut_terrain_normal.item(), it)
                writer.add_scalar("loss/mutual_terrain_height", loss_mut_terrain_height.item(), it)
                writer.add_scalar("loss/mutual_height_roof", loss_mut_height_roof.item(), it)
                writer.add_scalar("loss/mutual_height_terrain", loss_mut_height_terrain.item(), it)
                writer.add_scalar("loss/mutual_sem_geom_calib", loss_mut_semcal.item(), it)
                writer.add_scalar("mutual/semcal_reliability_mean", loss_mut_semcal_reliability.item(), it)
                writer.add_scalar("mutual/semcal_active_frac", loss_mut_semcal_active_frac.item(), it)
                writer.add_scalar("mutual/semcal_entropy_mean", loss_mut_semcal_entropy.item(), it)
                writer.add_scalar("loss/mutual_total", loss_mut_total.item(), it)
                _log_disabled_mutual_terms(writer, it, semcal_enabled=mutual_semcal_enabled)
            writer.add_scalar("loss/structure", loss_str_total.item(), it)
            writer.add_scalar("loss/structure_na", loss_str_na.item(), it)
            writer.add_scalar("loss/structure_cp", loss_str_cp.item(), it)
            writer.add_scalar("stats/n_groups", n_groups, it)
            writer.add_scalar("stats/n_in_group", n_in_group, it)
            writer.add_scalar("metric/psnr_train", p, it)
            writer.add_scalar("stats/n_primitives", model.num_points, it)
            pbar.set_postfix(loss=f"{loss_total.item():.4f}", psnr=f"{p:.2f}", N=model.num_points)

        if (
            mutual_log_class_stats_every > 0
            and it % mutual_log_class_stats_every == 0
            and e_gravity is not None
            and hasattr(model, "sem_logits")
        ):
            for tag, value in _mutual_class_stats(model, e_gravity).items():
                writer.add_scalar(tag, value, it)

        # periodic eval + render sample
        if it % cfg.get("eval_every", 2000) == 0 and it > 0:
            _eval_and_save(
                model, ds, test_idx, device, writer, out_dir, it,
                allow_explicit_empty=(view_role_audit["mode"] == "explicit_locked_roles"),
            )

        completed_steps = it + 1
        if full_state_checkpoint_due(
            full_state, completed_steps=completed_steps
        ):
            # All optimizer.step calls and SH warmup for this update have
            # completed. The checkpoint name therefore has no legacy +1 drift.
            loss_log_cursor = capture_loss_csv_cursor(
                out_dir,
                full_state["loss_csv_paths"],
                completed_steps=completed_steps,
            )
            trainer_runtime_state = capture_trainer_runtime_state(
                structure_groups=_grp,
                semantic_geometry=semantic_geometry,
                semantic_target_observations=semantic_target_observations,
                semantic_pi_audited_targets=semantic_pi_audited_targets,
            )
            saved = save_training_checkpoint(
                out_dir / "ckpt",
                completed_steps=completed_steps,
                model=model,
                optimizers=optimizers,
                strategy=strategy,
                strategy_state=strategy_state,
                grouping_state=trainer_runtime_state,
                binding_sha256=full_state_binding,
                loss_log_cursor=loss_log_cursor,
                learning_runs_started=learning_runs_started,
            )
            full_state_manifest["latest_full_checkpoint"] = {
                "path": str(saved.path.resolve()),
                "sha256": saved.sha256,
                "completed_steps": saved.completed_steps,
            }
            full_state_manifest["last_completed_steps"] = completed_steps
            atomic_write_json(full_state_manifest_path, full_state_manifest)
            print(
                f"[checkpoint] atomic full state {saved.path.name} "
                f"completed_updates={completed_steps} sha256={saved.sha256}",
                flush=True,
            )
        elif (
            not full_state["enabled"]
            and it % cfg.get("ckpt_every", 5000) == 0
            and it > 0
        ):
            # Legacy inference snapshot behavior is retained only when the new
            # full-state mode is absent, including its historical it semantics.
            checkpoint = {
                "it": it,
                "state_dict": model.state_dict(),
                "n_prim": model.num_points,
            }
            if "surface_seed_lineage" in strategy_state:
                checkpoint["surface_seed_lineage_mask"] = strategy_state[
                    "surface_seed_lineage"
                ].detach().cpu()
            torch.save(checkpoint, out_dir / "ckpt" / f"step_{it:06d}.pt")

    if pjpl_gate_sweep_enabled:
        if semantic_region_cache is None:
            raise RuntimeError("P-J/P-L final-view audit requires semantic region cache")
        semantic_pjpl_view_latest = _collect_pjpl_view_audit(
            model=model,
            ds=ds,
            view_indices=train_idx,
            device=device,
            region_cache=semantic_region_cache,
            target_buildings=semantic_pi_target_buildings,
            alpha_threshold=float(cfg.get("semantic_alpha_threshold", 0.5)),
            measurement_step=max_iter - 1,
        )
        pjpl_path = _write_pjpl_view_audit(out_dir, semantic_pjpl_view_latest)
        print(
            f"[S3-A P-J/P-L audit] {len(semantic_pjpl_view_latest)} "
            f"latest building-view measurements -> {pjpl_path}",
            flush=True,
        )

    final_prune_opa = float(cfg.get("final_prune_opa", 0.0) or 0.0)
    final_prune_candidates = 0
    final_pruned = 0
    if final_prune_opa > 0:
        from gsplat.strategy.ops import remove

        with torch.no_grad():
            final_prune_mask = torch.sigmoid(params["opacities"].flatten()) < final_prune_opa
            final_prune_candidates = int(final_prune_mask.sum().item())
            if final_prune_candidates > 0:
                remove(params=params, optimizers=optimizers, state=strategy_state, mask=final_prune_mask)
                _sync_params_to_model(params, model)
                final_pruned = final_prune_candidates
        writer.add_scalar("stats/final_prune_candidates", final_prune_candidates, max_iter)
        writer.add_scalar("stats/final_pruned", final_pruned, max_iter)
        print(f"[final-prune] opa<{final_prune_opa:g}: candidates={final_prune_candidates} pruned={final_pruned}")

    # final ckpt — also export Stage 2 group structure for Stage 3 (Track 1,
    # RESEARCH_CONTEXT §15). voxel_size etc. match training defaults, so the
    # exported groups are exactly what L_structure was optimizing toward at
    # the last grouping step.
    final_ckpt = {
        "it": max_iter,
        "state_dict": model.state_dict(),
        "n_prim": model.num_points,
        "final_prune_opa": final_prune_opa,
        "final_prune_candidates": final_prune_candidates,
        "final_pruned": final_pruned,
    }
    if "surface_seed_lineage" in strategy_state:
        final_ckpt["surface_seed_lineage_mask"] = strategy_state[
            "surface_seed_lineage"
        ].detach().cpu()
        final_ckpt["surface_seed_lineage_count"] = int(
            strategy_state["surface_seed_lineage"].sum().item()
        )
    try:
        from .model import quat_to_rotmat
        with torch.no_grad():
            scales_final = torch.exp(model.log_scales).detach()
            normals_final = quat_to_rotmat(model.quats.detach())[..., :, 2]
            gid, rep_n, rep_d = _group_primitives(
                centers=model.means.detach(),
                normals=normals_final,
                sem_logits=model.sem_logits.detach(),
                scales=scales_final,
            )
        final_ckpt["stage2_group_ids"] = gid.cpu()
        final_ckpt["stage2_rep_normals"] = rep_n.cpu()
        final_ckpt["stage2_rep_d"] = rep_d.cpu()
        print(f"[final] exported Stage 2 grouping: {rep_n.shape[0]} groups, "
              f"{int((gid >= 0).sum())} grouped primitives")
    except Exception as e:
        print(f"[final] WARNING: failed to export Stage 2 grouping: "
              f"{type(e).__name__}: {e}. Stage 3 will recompute via run_stage3.py.")
    torch.save(final_ckpt, out_dir / "ckpt" / "final.pt")
    _eval_and_save(
        model, ds, test_idx, device, writer, out_dir, max_iter, tag="final",
        allow_explicit_empty=(view_role_audit["mode"] == "explicit_locked_roles"),
    )
    dt = time.time() - t0
    if full_state["enabled"]:
        full_state_manifest["process_completed"] = True
        full_state_manifest["process_completed_steps"] = max_iter
        full_state_manifest["optimizer_updates_this_process"] = (
            max_iter - start_completed_steps
        )
        full_state_manifest["elapsed_seconds_this_process"] = dt
        atomic_write_json(full_state_manifest_path, full_state_manifest)
    print(f"[done] {max_iter} iter in {dt/60:.1f} min.  final N={model.num_points}")


@torch.no_grad()
def _eval_and_save(
    model,
    ds,
    test_idx,
    device,
    writer,
    out_dir,
    it,
    tag: str = "",
    allow_explicit_empty: bool = False,
):
    if not test_idx and allow_explicit_empty:
        writer.add_text("eval/status", "skipped_explicit_empty_eval_role", it)
        return
    psnrs, depth_maes, normal_coses = [], [], []
    for k, idx in enumerate(test_idx[:4]):
        b = ds[idx]
        rgb_gt = b["rgb"].to(device)
        w2c = b["w2c"].to(device)
        K = b["K"].to(device)
        H, W = b["height"], b["width"]
        out = render(model, w2c, K, W, H, sh_degree=model.active_sh_degree, render_mode="RGB+ED")
        rgb_p = out["rgb"].clamp(0, 1)
        mse = ((rgb_p - rgb_gt) ** 2).mean().item()
        psnrs.append(20 * math.log10(1.0) - 10 * math.log10(max(mse, 1e-10)))
        if "depth" in b:
            d_gt = b["depth"].to(device)
            d_m = b["depth_mask"].to(device)
            mae = ((out["depth"] - d_gt).abs() * d_m.float()).sum() / d_m.sum().clamp_min(1)
            depth_maes.append(mae.item())
        if "normal" in b:
            n_gt = b["normal"].to(device)
            n_m = b["normal_mask"].to(device)
            # Both n_render and n_gt are in WORLD frame (see RESEARCH_CONTEXT.md §12.6
            # for render_normals; dataloader canonicalizes EXR GT to world). No
            # additional rotation needed. The earlier `@ R.T` produced a spurious
            # camera-to-world rotation of already-world vectors → near-random cos.
            np_pred = torch.nn.functional.normalize(out["normal_render"], dim=-1, eps=1e-6)
            ng = torch.nn.functional.normalize(n_gt, dim=-1, eps=1e-6)
            c = (np_pred * ng).sum(-1).abs()
            normal_coses.append((c * n_m.float()).sum().item() / n_m.sum().clamp_min(1).item())

        # save sample renders
        import imageio.v2 as imageio
        rgb8 = (rgb_p.cpu().numpy() * 255).astype(np.uint8)
        imageio.imwrite(out_dir / "renders" / f"it{it:06d}_v{k}_rgb.png", rgb8)

    writer.add_scalar("eval/psnr", float(np.mean(psnrs)), it)
    if depth_maes:
        writer.add_scalar("eval/depth_mae", float(np.mean(depth_maes)), it)
    if normal_coses:
        writer.add_scalar("eval/normal_cos", float(np.mean(normal_coses)), it)


if __name__ == "__main__":
    main()

"""Stage-2 vanilla 2DGS training loop.

Usage (inside container):
    python -m src.stage2.train --config configs/vanilla.yaml

The config file specifies data root, output dir, max iterations, loss weights,
and densification schedule. This Phase-1 Step-1-1 trainer uses only the
data-fitting losses: L_photo, L_depth, L_normal, L_nc.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from pathlib import Path
from typing import Dict, Iterable, Optional

import numpy as np
import torch
import yaml
from torch.utils.tensorboard import SummaryWriter
from tqdm import tqdm

from .dataloader import ColmapDataset
from .densification import build_optimizers, build_param_dict, build_strategy
from .grouping import group_primitives
from .loss import data_fitting as L
from .loss.mutual import l_mutual
from .loss.structure import l_structure
from .model import GaussianModel2D
from .renderer import render


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


def psnr(a: torch.Tensor, b: torch.Tensor) -> float:
    mse = ((a - b) ** 2).mean().item()
    return 20 * math.log10(1.0) - 10 * math.log10(max(mse, 1e-10))


def _mutual_weight_scale(it: int, warmup: int, schedule: str, ramp_steps: int) -> float:
    if it < warmup:
        return 0.0
    if schedule == "constant":
        return 1.0
    if schedule == "ramp":
        if ramp_steps <= 0:
            return 1.0
        return min(1.0, float(it - warmup + 1) / float(ramp_steps))
    raise ValueError(f"Unsupported mutual_schedule={schedule!r}; expected 'constant' or 'ramp'")


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
    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    set_seed(cfg.get("seed", 0))
    device = cfg.get("device", "cuda")
    out_dir = Path(cfg["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ckpt").mkdir(exist_ok=True)
    (out_dir / "renders").mkdir(exist_ok=True)

    # ---------- data ----------
    ds = ColmapDataset(
        root=cfg["data_root"],
        downscale=cfg.get("downscale", 0.5),
        load_depth=cfg.get("load_depth", True),
        load_normal=cfg.get("load_normal", True),
        load_semantic=cfg.get("load_semantic", False),
        depth_scale=cfg.get("depth_scale", 1.0),
    )
    print(f"[data] frames={len(ds)}  pts_init={ds.points_xyz.shape[0]}")

    # train/test split: interleave (every 10th frame → test) to avoid systematic
    # azimuth / viewpoint bias when frames are stored in sorted order (grouped by
    # capture type). Previously used "last 10%" which grouped all orbit views into
    # test → test was out-of-distribution → severe overfitting.
    n = len(ds)
    test_idx = [i for i in range(n) if i % 10 == 9]
    train_idx = [i for i in range(n) if i not in test_idx]

    # ---------- semantic seeding (P2 ①): optional carve seeds for textureless bldgs ----------
    points_xyz, points_rgb = ds.points_xyz, ds.points_rgb
    points_sem = None
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
        points_xyz, points_rgb, points_sem = concat_seeds(ds.points_xyz, ds.points_rgb, seeds)
        print(f"[seed] +{len(seeds.xyz)} semantic seeds over {len(sc['buildings'])} buildings "
              f"-> N {ds.points_xyz.shape[0]} -> {points_xyz.shape[0]}")

    # ---------- MVS-seed init (P2 make-or-break v6) ----------
    # INIT/DATA PATH ONLY (no engine logic): seed the model with a prepared GS-LOCAL MVS cloud
    # (dense=DIM / acmp=ACMP), produced offline by tum_mob_seed_prep.sh (AOI crop + per-cloud
    # geoid shift + voxel<=~3M + outlier clip). Default mode "concat": add the MVS points onto
    # the SfM base so the full scene stays trainable (ACMP exists only over the AOI), while the
    # 11 eval buildings get dense init. RGB = scene mean (same as the semantic seeds; L_photo
    # recolours during training). scene_scale is intentionally left on ds.points_xyz (the SfM
    # extent) so densification thresholds are unchanged by the AOI-concentrated seeds.
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
        elif mode == "concat":
            points_xyz = np.concatenate([points_xyz, seed_xyz], axis=0).astype(np.float32)
            points_rgb = np.concatenate([points_rgb, seed_rgb], axis=0).astype(np.float32)
            if points_sem is not None:
                points_sem = np.concatenate(
                    [points_sem, np.full(len(seed_xyz), -1, np.int64)]).astype(np.int64)
        else:
            raise ValueError(f"init_pointcloud_mode must be concat|replace, got {mode!r}")
        print(f"[mvs-seed] {mode} {len(seed_xyz)} MVS init pts from {init_pc}: "
              f"N {n0} -> {points_xyz.shape[0]}")

    # ---------- model ----------
    model = GaussianModel2D(
        points_xyz=points_xyz,
        points_rgb=points_rgb,
        sh_degree=cfg.get("sh_degree", 3),
        device=device,
        points_sem=points_sem,
    )
    model = model.to(device)

    params = build_param_dict(model)
    optimizers = build_optimizers(
        model,
        lr_means=cfg.get("lr_means", 1.6e-4),
        lr_scales=cfg.get("lr_scales", 5e-3),
        lr_quats=cfg.get("lr_quats", 1e-3),
        lr_opacities=cfg.get("lr_opacities", 5e-2),
        lr_sh0=cfg.get("lr_sh0", 2.5e-3),
        lr_shN=cfg.get("lr_shN", 1.25e-4),
    )

    # scene scale (for DefaultStrategy)
    scene_scale = float(np.linalg.norm(ds.points_xyz - ds.points_xyz.mean(0), axis=1).mean())

    strategy = build_strategy(
        prune_opa=cfg.get("prune_opa", 0.005),
        grow_grad2d=cfg.get("grow_grad2d", 2e-4),
        grow_scale3d=cfg.get("grow_scale3d", 0.01),
        prune_scale3d=cfg.get("prune_scale3d", 0.1),
        refine_start_iter=cfg.get("refine_start_iter", 500),
        refine_stop_iter=cfg.get("refine_stop_iter", 15000),
        refine_every=cfg.get("refine_every", 100),
        reset_every=cfg.get("reset_every", 3000),
    )
    strategy.check_sanity(params, optimizers)
    strategy_state = strategy.initialize_state(scene_scale=scene_scale)

    # ---------- logging ----------
    writer = SummaryWriter(out_dir / "tb")

    # ---------- loss weights ----------
    w_photo = cfg.get("w_photo", 1.0)
    w_depth = cfg.get("w_depth", 1.0)
    w_normal = cfg.get("w_normal", 0.05)
    w_nc = cfg.get("w_nc", 0.05)
    w_distort = cfg.get("w_distort", 100.0)   # 2DGS distortion reg
    w_sem = cfg.get("w_sem", 0.1)
    # P2 impl ②: release L_sem geometry detach so semantics can move geometry (default True
    # keeps the existing gradient-isolated behaviour, so the other configs are unaffected).
    sem_detach_geometry = cfg.get("sem_detach_geometry", True)
    w_structure = cfg.get("w_structure", 0.0)
    w_structure_na = cfg.get("w_structure_na", 1.0)
    w_structure_cp = cfg.get("w_structure_cp", 1.0)
    structure_warmup = int(cfg.get("structure_warmup", 15000))
    structure_regroup_every = int(cfg.get("structure_regroup_every", 500))
    structure_voxel_size = float(cfg.get("structure_voxel_size", 0.05))
    structure_n_directions = int(cfg.get("structure_n_directions", 12))
    structure_min_group = int(cfg.get("structure_min_group", 5))
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

    max_iter = int(cfg["max_iter"])
    sh_up_every = int(cfg.get("sh_up_every", 1000))

    print(f"[train] max_iter={max_iter}  out={out_dir}")
    pbar = tqdm(range(max_iter), desc="train")
    t0 = time.time()

    for it in pbar:
        # pick a random training view
        idx = train_idx[it % len(train_idx)] if cfg.get("sequential", False) else random.choice(train_idx)
        batch = ds[idx]
        rgb_gt = batch["rgb"].to(device)
        w2c = batch["w2c"].to(device)
        K = batch["K"].to(device)
        H, W = batch["height"], batch["width"]

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

        # losses
        loss_photo = L.l_photo(rgb_pred, rgb_gt, lam=photo_lam)
        loss_total = w_photo * loss_photo

        if "depth" in batch:
            d_gt = batch["depth"].to(device)
            d_m = batch["depth_mask"].to(device)
            loss_depth = L.l_depth(depth_pred, d_gt, d_m)
            loss_total = loss_total + w_depth * loss_depth
        else:
            loss_depth = torch.tensor(0.0, device=device)

        if "normal" in batch:
            n_gt = batch["normal"].to(device)
            n_m = batch["normal_mask"].to(device)
            loss_n = L.l_normal(n_render, n_gt, w2c, n_m)
            loss_total = loss_total + w_normal * loss_n
        else:
            loss_n = torch.tensor(0.0, device=device)

        loss_nc = L.l_nc(n_render, n_surf, alpha=alpha.detach())
        loss_total = loss_total + w_nc * loss_nc

        loss_dist = distort.mean()
        loss_total = loss_total + w_distort * loss_dist

        # Semantic (only if GT provided and w_sem > 0)
        if "semantic" in batch and w_sem > 0 and hasattr(model, "sem_logits"):
            from .renderer import render_semantic
            sem_pred = render_semantic(model, w2c, K, W, H, sem_detach_geometry=sem_detach_geometry)
            sem_gt = batch["semantic"].to(device)
            loss_sem = L.l_sem(sem_pred, sem_gt, ignore_index=0)
            loss_total = loss_total + w_sem * loss_sem
        else:
            loss_sem = torch.tensor(0.0, device=device)
        loss_base_for_grad = loss_total

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
        mutual_weight_scale = _mutual_weight_scale(it, mutual_warmup, mutual_schedule, mutual_ramp_steps)
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
                gids, rep_n, rep_d = group_primitives(
                    centers=model.means.detach(),
                    normals=model.normals().detach(),
                    sem_logits=model.sem_logits.detach(),
                    scales=model.scales.detach(),
                    voxel_size=structure_voxel_size,
                    n_directions=structure_n_directions,
                    min_group_size=structure_min_group,
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
                    "normal": loss_n,
                    "semantic": loss_sem,
                    "mutual": loss_mut_total,
                },
            )

        # backward
        for opt in optimizers.values():
            opt.zero_grad(set_to_none=True)
        loss_total.backward()

        strategy.step_post_backward(params, optimizers, strategy_state, it, meta)

        # sync params dict -> model (gsplat strategy may replace nn.Parameters on grow/prune)
        _sync_params_to_model(params, model)

        for opt in optimizers.values():
            opt.step()

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
            writer.add_scalar("loss/normal", loss_n.item(), it)
            writer.add_scalar("loss/nc", loss_nc.item(), it)
            writer.add_scalar("loss/distort", loss_dist.item(), it)
            writer.add_scalar("loss/sem", loss_sem.item(), it)
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
            _eval_and_save(model, ds, test_idx, device, writer, out_dir, it)

        if it % cfg.get("ckpt_every", 5000) == 0 and it > 0:
            torch.save({
                "it": it,
                "state_dict": model.state_dict(),
                "n_prim": model.num_points,
            }, out_dir / "ckpt" / f"step_{it:06d}.pt")

    # final ckpt — also export Stage 2 group structure for Stage 3 (Track 1,
    # RESEARCH_CONTEXT §15). voxel_size etc. match training defaults, so the
    # exported groups are exactly what L_structure was optimizing toward at
    # the last grouping step.
    final_ckpt = {
        "it": max_iter,
        "state_dict": model.state_dict(),
        "n_prim": model.num_points,
    }
    try:
        from .model import quat_to_rotmat
        with torch.no_grad():
            scales_final = torch.exp(model.log_scales).detach()
            normals_final = quat_to_rotmat(model.quats.detach())[..., :, 2]
            gid, rep_n, rep_d = group_primitives(
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
    _eval_and_save(model, ds, test_idx, device, writer, out_dir, max_iter, tag="final")
    dt = time.time() - t0
    print(f"[done] {max_iter} iter in {dt/60:.1f} min.  final N={model.num_points}")


@torch.no_grad()
def _eval_and_save(model, ds, test_idx, device, writer, out_dir, it, tag: str = ""):
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

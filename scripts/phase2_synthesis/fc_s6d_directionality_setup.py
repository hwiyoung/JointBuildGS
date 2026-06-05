"""FC-S6D directionality inventory and no-training scale audit.

This script is intentionally bounded:
- no Stage2 training
- no Stage3 or Metric-v1 execution
- no L_structure or G2 execution

It inspects the accepted A8 terrain-off Mutual reference, computes a fixed
checkpoint/batch gradient-scale audit when possible, and writes the FC-S6D
screening scaffold without claiming directional screening results.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import torch
import torch.nn.functional as F
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.stage2.dataloader import ColmapDataset
from src.stage2.loss import data_fitting as L
from src.stage2.loss.mutual import l_mutual
from src.stage2.model import quat_to_rotmat
from src.stage2.renderer import render, render_semantic


OUT_ROOT = ROOT / "results/FC_S6D_lmutual_directionality"
PHASE0 = OUT_ROOT / "phase0_inventory"
PHASE1 = OUT_ROOT / "phase1_scale_audit"
PHASE2 = OUT_ROOT / "phase2_screening"
CONFIG_ROOT = ROOT / "configs/fc_s6d"

A8_CONFIG = ROOT / "configs/fc_s6/A8_no_terrain_terms.yaml"
A8_CKPT = (
    ROOT
    / "results/FC_S6_componentwise_revised_lmutual_design_validation"
    / "phase1_existing_terms/runs/A8_no_terrain_terms/ckpt/final.pt"
)
A8_SPLIT = (
    ROOT
    / "results/FC_S6_componentwise_revised_lmutual_design_validation"
    / "phase1_existing_terms/term_ablation_split_summary.csv"
)
A8_BY_BID = (
    ROOT
    / "results/FC_S6_componentwise_revised_lmutual_design_validation"
    / "phase1_existing_terms/term_ablation_metrics_by_bid.csv"
)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def ensure_dirs() -> None:
    for d in [PHASE0, PHASE1, PHASE2, CONFIG_ROOT]:
        d.mkdir(parents=True, exist_ok=True)


def read_yaml(path: Path) -> Dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f)


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        for row in rows:
            for k in row:
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def gravity_from_cfg(cfg: Dict[str, Any], device: torch.device) -> torch.Tensor:
    grav_file = cfg.get("gravity_file")
    if not grav_file:
        raise FileNotFoundError("A8 config has no gravity_file")
    p = ROOT / grav_file if not Path(grav_file).is_absolute() else Path(grav_file)
    data = read_json(p)
    return torch.tensor(data["e_gravity"], dtype=torch.float32, device=device)


def active_term_rows(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "term": "wall_verticality",
            "enabled": bool(cfg.get("mutual_enable_wall_vertical", True)),
            "term_weight": float(cfg.get("mutual_w_wall_vertical", 1.0)),
            "uses_terrain_evidence": False,
            "detach_policy": cfg.get("mutual_mode", "full"),
            "formula": "mean p_wall * (n dot g)^2",
            "target": "semantic_faces/WallSurface",
        },
        {
            "term": "roof_nonwall_prior",
            "enabled": bool(cfg.get("mutual_enable_roof_nonwall", True)),
            "term_weight": float(cfg.get("mutual_w_roof_nonwall", 1.0)),
            "uses_terrain_evidence": False,
            "detach_policy": cfg.get("mutual_mode", "full"),
            "formula": "mean p_roof * relu(tau - (n dot g)^2)^2",
            "target": "semantic_faces/RoofSurface",
        },
        {
            "term": "terrain_normal",
            "enabled": bool(cfg.get("mutual_enable_terrain_normal", True)),
            "term_weight": float(cfg.get("mutual_w_terrain_normal", 1.0)),
            "uses_terrain_evidence": True,
            "detach_policy": cfg.get("mutual_mode", "full"),
            "formula": "mean p_terrain * gate * (1 - abs(n dot g))^2",
            "target": "semantic_faces/GroundSurface candidate evidence",
        },
        {
            "term": "roof_side_height",
            "enabled": bool(cfg.get("mutual_enable_height_roof_side", True)),
            "term_weight": float(cfg.get("mutual_w_height", 1.0))
            * float(cfg.get("mutual_w_height_roof", 1.0)),
            "uses_terrain_evidence": False,
            "detach_policy": cfg.get("mutual_mode", "full"),
            "formula": "mean p_roof * relu(height_th - height)^2",
            "target": "shell_diagnostics/height-volume",
        },
        {
            "term": "terrain_side_height",
            "enabled": bool(cfg.get("mutual_enable_terrain_height", True))
            and bool(cfg.get("mutual_enable_height_terrain_side", True)),
            "term_weight": float(cfg.get("mutual_w_height", 1.0))
            * float(cfg.get("mutual_w_height_terrain", 1.0)),
            "uses_terrain_evidence": True,
            "detach_policy": cfg.get("mutual_mode", "full"),
            "formula": "mean p_terrain * gate * relu(height - terrain_height_ref)^2",
            "target": "semantic_faces/GroundSurface and shell height",
        },
        {
            "term": "roof_wall_relation_placeholder",
            "enabled": bool(cfg.get("mutual_enable_roof_wall_relation", False)),
            "term_weight": 0.0,
            "uses_terrain_evidence": False,
            "detach_policy": "disabled",
            "formula": "not implemented in train path",
            "target": "face_graph/roof-wall adjacency",
        },
        {
            "term": "terrain_wall_relation_placeholder",
            "enabled": bool(cfg.get("mutual_enable_terrain_wall_relation", False)),
            "term_weight": 0.0,
            "uses_terrain_evidence": True,
            "detach_policy": "disabled",
            "formula": "not implemented in train path",
            "target": "face_graph/wall-ground adjacency",
        },
    ]


def write_phase0(cfg: Dict[str, Any]) -> None:
    active_rows = active_term_rows(cfg)
    active_terms = [r["term"] for r in active_rows if r["enabled"]]
    inactive_terms = [r["term"] for r in active_rows if not r["enabled"]]

    text = [
        "# FC-S6D Phase 0: A8 Active Terms Inventory",
        "",
        "## Scope",
        "Inspection only. No training, Stage3, Metric-v1, L_structure, or G2 run was performed.",
        "",
        "## A8 Reference",
        f"- Config: `{rel(A8_CONFIG)}`",
        f"- Checkpoint: `{rel(A8_CKPT)}`",
        f"- `w_mutual`: `{cfg.get('w_mutual')}`",
        f"- `mutual_warmup`: `{cfg.get('mutual_warmup')}`",
        f"- `mutual_schedule`: `{cfg.get('mutual_schedule', 'constant')}`",
        f"- `mutual_ramp_steps`: `{cfg.get('mutual_ramp_steps', 0)}`",
        f"- `mutual_mode`: `{cfg.get('mutual_mode', 'full')}`",
        f"- `mutual_tau`: `{cfg.get('mutual_tau')}`",
        f"- `mutual_height_th`: `{cfg.get('mutual_height_th')}`",
        f"- `gravity_file`: `{cfg.get('gravity_file')}`",
        "",
        "## Actual Active Terms",
        "",
        "A8 is a terrain-off reference, but the current config still enables the roof-side height term.",
        "That means A8 is not only wall/roof normal priors; it is wall verticality + roof non-wall + roof-side height.",
        "",
        "| term | enabled | formula | target |",
        "|---|---:|---|---|",
    ]
    for row in active_rows:
        text.append(
            f"| `{row['term']}` | {row['enabled']} | `{row['formula']}` | {row['target']} |"
        )
    text.extend(
        [
            "",
            "## Active/Inactive Summary",
            f"- Active: {', '.join(f'`{x}`' for x in active_terms)}",
            f"- Inactive: {', '.join(f'`{x}`' for x in inactive_terms)}",
            "",
            "## Detach and Directionality",
            "- A8 uses `mutual_mode: full`, so semantic probabilities and geometry both receive gradients.",
            "- `A8_v2_geo` keeps the same active terms but uses `mutual_mode: sem2geo`, detaching `p_wall` and `p_roof`.",
            "- `A8_v2_joint` adds an explicit roof/wall semantic calibration term on top of `A8_v2_geo`.",
            "",
            "## Base Loss Components",
            "- Base loss is `w_photo*L_photo + w_depth*L_depth + w_normal*L_normal + w_nc*L_nc + w_distort*L_distort + w_sem*L_sem`.",
            "- `w_structure` is `0.0` in A8 and remains disabled for FC-S6D.",
        ]
    )
    (PHASE0 / "A8_ACTIVE_TERMS.md").write_text("\n".join(text) + "\n")

    formula_rows = [
        {
            "candidate": "A8_legacy_terrain_off",
            "formula": "lambda_mu * (L_wall + L_roof + L_roof_height)",
            "wall_term": "mean p_wall * (n dot g)^2",
            "roof_term": "mean p_roof * relu(tau - (n dot g)^2)^2",
            "roof_height_term": "mean p_roof * relu(height_th - height)^2",
            "semantic_detach": "no",
            "geometry_detach": "no",
            "terrain_terms": "off except terrain evidence is not used by active roof-side height",
            "train_support": "implemented by existing mutual.py with A8 config",
        },
        {
            "candidate": "A8_v2_geo",
            "formula": "lambda_mu * kappa_geo * (L_wall_sg + L_roof_sg + L_roof_height_sg)",
            "wall_term": "mean stopgrad(p_wall) * (n dot g)^2",
            "roof_term": "mean stopgrad(p_roof) * relu(tau - (n dot g)^2)^2",
            "roof_height_term": "mean stopgrad(p_roof) * relu(height_th - height)^2",
            "semantic_detach": "yes",
            "geometry_detach": "no",
            "terrain_terms": "off",
            "train_support": "config-only via mutual_mode=sem2geo and scaled w_mutual",
        },
        {
            "candidate": "A8_v2_joint",
            "formula": "A8_v2_geo + lambda_mu * beta * KL(stopgrad(s_geom_roofwall) || p_roofwall)",
            "wall_term": "same as A8_v2_geo",
            "roof_term": "same as A8_v2_geo",
            "roof_height_term": "same as A8_v2_geo",
            "semantic_detach": "geo term yes; semcal teacher stopgrad yes",
            "geometry_detach": "semcal geometry teacher detached",
            "terrain_terms": "off",
            "train_support": "not implemented in train.py/mutual.py yet; audit-only formula here",
        },
    ]
    write_csv(PHASE0 / "directional_formula_table.csv", formula_rows)

    lbase_rows = [
        {"component": "photo", "weight": cfg.get("w_photo", 1.0), "source": "train.py/A8 config"},
        {"component": "depth", "weight": cfg.get("w_depth", 1.0), "source": "train.py/A8 config"},
        {"component": "normal", "weight": cfg.get("w_normal", 0.05), "source": "train.py/A8 config"},
        {"component": "normal_consistency", "weight": cfg.get("w_nc", 0.05), "source": "train.py/A8 config"},
        {"component": "distortion", "weight": cfg.get("w_distort", 100.0), "source": "train.py/A8 config"},
        {"component": "semantic", "weight": cfg.get("w_sem", 0.1), "source": "train.py/A8 config"},
        {"component": "mutual", "weight": cfg.get("w_mutual", 0.0), "source": "train.py/A8 config"},
        {"component": "structure", "weight": cfg.get("w_structure", 0.0), "source": "train.py/A8 config"},
    ]
    write_csv(PHASE0 / "lbase_weight_table.csv", lbase_rows)


class LoadedGaussianModel2D(torch.nn.Module):
    """Minimal train-compatible model wrapper loaded directly from checkpoint.

    Avoids `GaussianModel2D` initialization because that estimates nearest
    neighbor scales with a KD-tree, which is unnecessary and slow for a
    densified 1.7M-primitive checkpoint.
    """

    def __init__(self, sd: Dict[str, torch.Tensor], sh_degree: int, device: torch.device):
        super().__init__()
        self.sh_degree = int(sh_degree)
        self.max_sh_degree = int(sh_degree)
        self.active_sh_degree = int(sh_degree)
        self.num_classes = int(sd["sem_logits"].shape[-1])
        for name in ["means", "quats", "log_scales", "opacities_raw", "sh0", "shN", "sem_logits"]:
            if name in sd:
                setattr(self, name, torch.nn.Parameter(sd[name].to(device).clone()))

    @property
    def num_points(self) -> int:
        return int(self.means.shape[0])

    @property
    def scales(self) -> torch.Tensor:
        return torch.exp(self.log_scales)

    @property
    def opacities(self) -> torch.Tensor:
        return torch.sigmoid(self.opacities_raw)

    def normals(self) -> torch.Tensor:
        return quat_to_rotmat(self.quats)[..., :, 2]

    def colors_sh(self) -> torch.Tensor:
        return torch.cat([self.sh0, self.shN], dim=1)


def load_model_from_ckpt(ckpt_path: Path, sh_degree: int, device: torch.device) -> LoadedGaussianModel2D:
    sd = torch.load(ckpt_path, map_location="cpu", weights_only=False)["state_dict"]
    return LoadedGaussianModel2D(sd, sh_degree=sh_degree, device=device).to(device)


def train_indices(ds: ColmapDataset) -> List[int]:
    test = {i for i in range(len(ds)) if i % 10 == 9}
    return [i for i in range(len(ds)) if i not in test]


def grad_params(model: LoadedGaussianModel2D) -> List[Tuple[str, torch.nn.Parameter]]:
    return [
        ("means", model.means),
        ("quats", model.quats),
        ("sem_logits", model.sem_logits),
    ]


def grads_for(loss: torch.Tensor, params: List[Tuple[str, torch.nn.Parameter]]) -> Dict[str, torch.Tensor | None]:
    tensors = [p for _, p in params]
    grads = torch.autograd.grad(loss, tensors, retain_graph=False, allow_unused=True)
    return {name: (g.detach() if g is not None else None) for (name, _), g in zip(params, grads)}


def grad_norm(grads: Dict[str, torch.Tensor | None], names: Iterable[str] | None = None) -> float:
    total = 0.0
    use_names = list(names) if names is not None else list(grads.keys())
    for name in use_names:
        g = grads.get(name)
        if g is not None:
            total += float((g.float() * g.float()).sum().item())
    return math.sqrt(total)


def grad_cos(a: Dict[str, torch.Tensor | None], b: Dict[str, torch.Tensor | None]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for key in a.keys():
        ga = a.get(key)
        gb = b.get(key)
        if ga is None or gb is None:
            continue
        ga = ga.float()
        gb = gb.float()
        dot += float((ga * gb).sum().item())
        na += float((ga * ga).sum().item())
        nb += float((gb * gb).sum().item())
    if na <= 0.0 or nb <= 0.0:
        return float("nan")
    return dot / math.sqrt(na * nb)


def scale_grads(grads: Dict[str, torch.Tensor | None], scale: float) -> Dict[str, torch.Tensor | None]:
    return {k: (None if g is None else g * float(scale)) for k, g in grads.items()}


def add_grads(
    a: Dict[str, torch.Tensor | None],
    b: Dict[str, torch.Tensor | None],
) -> Dict[str, torch.Tensor | None]:
    out: Dict[str, torch.Tensor | None] = {}
    for key in set(a.keys()) | set(b.keys()):
        ga = a.get(key)
        gb = b.get(key)
        if ga is None:
            out[key] = gb
        elif gb is None:
            out[key] = ga
        else:
            out[key] = ga + gb
    return out


def mutual_loss(
    model: LoadedGaussianModel2D,
    cfg: Dict[str, Any],
    e_gravity: torch.Tensor,
    mode: str,
) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
    terms = l_mutual(
        normals=model.normals(),
        centers=model.means,
        sem_logits=model.sem_logits,
        e_gravity=e_gravity,
        tau=float(cfg.get("mutual_tau", 0.15)),
        height_th=float(cfg.get("mutual_height_th", 0.15)),
        w_vert=float(cfg.get("mutual_w_wall_vertical", 1.0)),
        w_slope=float(cfg.get("mutual_w_roof_nonwall", 1.0)),
        w_horiz=float(cfg.get("mutual_w_terrain_normal", 1.0)),
        w_height=float(cfg.get("mutual_w_height", 1.0)),
        w_height_roof=float(cfg.get("mutual_w_height_roof", 1.0)),
        w_height_terrain=float(cfg.get("mutual_w_height_terrain", 1.0)),
        mode=mode,
        enable_wall_vertical=bool(cfg.get("mutual_enable_wall_vertical", True)),
        enable_roof_nonwall=bool(cfg.get("mutual_enable_roof_nonwall", True)),
        enable_terrain_normal=bool(cfg.get("mutual_enable_terrain_normal", True)),
        enable_terrain_height=bool(cfg.get("mutual_enable_terrain_height", True)),
        enable_height_roof_side=bool(cfg.get("mutual_enable_height_roof_side", True)),
        enable_height_terrain_side=bool(cfg.get("mutual_enable_height_terrain_side", True)),
        terrain_gate_mode=cfg.get("mutual_terrain_gate_mode", "none"),
        terrain_gate_conf_min=float(cfg.get("mutual_terrain_gate_conf_min", 0.0)),
        terrain_gate_mass_min=float(cfg.get("mutual_terrain_gate_mass_min", 0.0)),
        terrain_gate_entropy_max=float(cfg.get("mutual_terrain_gate_entropy_max", 1.0)),
        terrain_height_reference=cfg.get("mutual_terrain_height_reference", "fixed"),
        terrain_height_quantile=float(cfg.get("mutual_terrain_height_quantile", 0.5)),
        terrain_height_margin=float(cfg.get("mutual_terrain_height_margin", 0.0)),
    )
    return terms["total"], terms


def semcal_roofwall_loss(
    model: LoadedGaussianModel2D,
    e_gravity: torch.Tensor,
    tau: float,
    temperature: float = 0.05,
) -> Tuple[torch.Tensor, Dict[str, float]]:
    """Roof/wall-only semantic calibration, audit formula only.

    Geometry is teacher-side stopgrad. Terrain is excluded to preserve the
    accepted A8 terrain-off boundary.
    """
    p = F.softmax(model.sem_logits, dim=-1)
    p_rw = p[:, [1, 2]]
    p_rw_norm = p_rw / p_rw.sum(dim=-1, keepdim=True).clamp_min(1e-8)

    with torch.no_grad():
        n = F.normalize(model.normals(), dim=-1, eps=1e-6)
        dot2 = ((n * e_gravity.to(n.device)).sum(dim=-1)) ** 2
        e_roof = F.relu(float(tau) - dot2) ** 2
        e_wall = dot2
        geom_logits = torch.stack([-e_roof / temperature, -e_wall / temperature], dim=-1)
        s_geom = torch.softmax(geom_logits, dim=-1)
        geom_conf = ((s_geom.max(dim=-1).values - 0.5) * 2.0).clamp(0.0, 1.0)
        sem_mass = p_rw.detach().sum(dim=-1).clamp(0.0, 1.0)
        reliability = (geom_conf * sem_mass).clamp(0.0, 1.0)

    kl = (s_geom * (s_geom.clamp_min(1e-8).log() - p_rw_norm.clamp_min(1e-8).log())).sum(dim=-1)
    denom = reliability.sum().clamp_min(1.0)
    loss = (reliability * kl).sum() / denom
    stats = {
        "reliability_mean": float(reliability.mean().detach().cpu()),
        "reliability_active_frac": float((reliability > 0.05).float().mean().detach().cpu()),
        "geom_roof_mean": float(s_geom[:, 0].mean().detach().cpu()),
        "geom_wall_mean": float(s_geom[:, 1].mean().detach().cpu()),
    }
    return loss, stats


def compute_base_loss(
    model: LoadedGaussianModel2D,
    batch: Dict[str, Any],
    cfg: Dict[str, Any],
    device: torch.device,
) -> Tuple[torch.Tensor, Dict[str, float]]:
    rgb_gt = batch["rgb"].to(device)
    w2c = batch["w2c"].to(device)
    K = batch["K"].to(device)
    H, W = int(batch["height"]), int(batch["width"])
    out = render(model, w2c, K, W, H, sh_degree=model.active_sh_degree, render_mode="RGB+ED")
    rgb_pred = out["rgb"]
    depth_pred = out["depth"]
    n_render = out["normal_render"]
    n_surf = out["normal_surf"]
    alpha = out["alpha"]
    distort = out["distort"]

    loss_photo = L.l_photo(rgb_pred, rgb_gt, lam=float(cfg.get("photo_lam", 0.2)))
    total = float(cfg.get("w_photo", 1.0)) * loss_photo
    vals = {"photo": float(loss_photo.detach().cpu())}

    if "depth" in batch:
        d_gt = batch["depth"].to(device)
        d_m = batch["depth_mask"].to(device)
        loss_depth = L.l_depth(depth_pred, d_gt, d_m)
        total = total + float(cfg.get("w_depth", 0.5)) * loss_depth
        vals["depth"] = float(loss_depth.detach().cpu())

    if "normal" in batch:
        n_gt = batch["normal"].to(device)
        n_m = batch["normal_mask"].to(device)
        loss_normal = L.l_normal(n_render, n_gt, w2c, n_m)
        total = total + float(cfg.get("w_normal", 0.05)) * loss_normal
        vals["normal"] = float(loss_normal.detach().cpu())

    loss_nc = L.l_nc(n_render, n_surf, alpha=alpha.detach())
    total = total + float(cfg.get("w_nc", 0.05)) * loss_nc
    vals["nc"] = float(loss_nc.detach().cpu())

    loss_dist = distort.mean()
    total = total + float(cfg.get("w_distort", 0.0)) * loss_dist
    vals["distort"] = float(loss_dist.detach().cpu())

    if "semantic" in batch and float(cfg.get("w_sem", 0.1)) > 0:
        sem_pred = render_semantic(model, w2c, K, W, H)
        sem_gt = batch["semantic"].to(device)
        loss_sem = L.l_sem(sem_pred, sem_gt, ignore_index=0)
        total = total + float(cfg.get("w_sem", 0.1)) * loss_sem
        vals["sem"] = float(loss_sem.detach().cpu())

    vals["base_weighted_total"] = float(total.detach().cpu())
    return total, vals


def summarize_loss_row(
    batch_id: str,
    loss_name: str,
    raw_loss: float,
    weighted_loss: float,
    grads: Dict[str, torch.Tensor | None],
    base_grads: Dict[str, torch.Tensor | None] | None,
    base_norm: float,
    loss_scale: float = 1.0,
    notes: str = "",
) -> Dict[str, Any]:
    total_norm = grad_norm(grads)
    weighted_grads = scale_grads(grads, loss_scale)
    weighted_norm = grad_norm(weighted_grads)
    return {
        "batch_id": batch_id,
        "loss_name": loss_name,
        "raw_loss": raw_loss,
        "weighted_loss": weighted_loss,
        "loss_scale": loss_scale,
        "grad_norm_total": total_norm,
        "grad_norm_means": grad_norm(grads, ["means"]),
        "grad_norm_quats": grad_norm(grads, ["quats"]),
        "grad_norm_sem_logits": grad_norm(grads, ["sem_logits"]),
        "grad_ratio_to_base": total_norm / base_norm if base_norm > 0 else "",
        "weighted_grad_norm_total": weighted_norm,
        "weighted_grad_ratio_to_base": weighted_norm / base_norm if base_norm > 0 else "",
        "cosine_with_base": grad_cos(grads, base_grads) if base_grads is not None else "",
        "notes": notes,
    }


def run_scale_audit(cfg: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
    ds = ColmapDataset(
        root=cfg["data_root"],
        downscale=float(cfg.get("downscale", 1.0)),
        load_depth=bool(cfg.get("load_depth", True)),
        load_normal=bool(cfg.get("load_normal", True)),
        load_semantic=bool(cfg.get("load_semantic", True)),
        depth_scale=float(cfg.get("depth_scale", 1.0)),
    )
    idxs = train_indices(ds)[: max(1, int(args.n_batches))]
    model = load_model_from_ckpt(A8_CKPT, int(cfg.get("sh_degree", 3)), device)
    e_gravity = gravity_from_cfg(cfg, device)
    params = grad_params(model)

    rows: List[Dict[str, Any]] = []
    base_norms: List[float] = []
    legacy_norms: List[float] = []
    geo_norms: List[float] = []
    semcal_norms: List[float] = []
    legacy_raw_values: List[float] = []
    geo_raw_values: List[float] = []
    semcal_values: List[float] = []
    semcal_stats: Dict[str, float] = {}

    lambda_mu = float(cfg.get("w_mutual", 0.0))

    for pos, idx in enumerate(idxs):
        batch = ds[int(idx)]
        base_loss, base_vals = compute_base_loss(model, batch, cfg, device)
        base_grads = grads_for(base_loss, params)
        base_norm = grad_norm(base_grads)
        base_norms.append(base_norm)
        rows.append(
            summarize_loss_row(
                batch_id=str(idx),
                loss_name="L_base",
                raw_loss=float(base_loss.detach().cpu()),
                weighted_loss=float(base_loss.detach().cpu()),
                grads=base_grads,
                base_grads=None,
                base_norm=base_norm,
                loss_scale=1.0,
                notes=json.dumps(base_vals, sort_keys=True),
            )
        )

        legacy_loss, _ = mutual_loss(model, cfg, e_gravity, mode="full")
        legacy_grads = grads_for(legacy_loss, params)
        legacy_raw = float(legacy_loss.detach().cpu())
        legacy_raw_values.append(legacy_raw)
        legacy_norms.append(grad_norm(legacy_grads))
        rows.append(
            summarize_loss_row(
                batch_id=str(idx),
                loss_name="A8_legacy_mutual_raw",
                raw_loss=legacy_raw,
                weighted_loss=lambda_mu * legacy_raw,
                grads=legacy_grads,
                base_grads=base_grads,
                base_norm=base_norm,
                loss_scale=lambda_mu,
                notes="full bidirectional p*geometry A8 terms",
            )
        )

        geo_loss, _ = mutual_loss(model, cfg, e_gravity, mode="sem2geo")
        geo_grads = grads_for(geo_loss, params)
        geo_raw = float(geo_loss.detach().cpu())
        geo_raw_values.append(geo_raw)
        geo_norms.append(grad_norm(geo_grads))
        rows.append(
            summarize_loss_row(
                batch_id=str(idx),
                loss_name="A8_v2_geo_raw",
                raw_loss=geo_raw,
                weighted_loss=lambda_mu * geo_raw,
                grads=geo_grads,
                base_grads=base_grads,
                base_norm=base_norm,
                loss_scale=lambda_mu,
                notes="sem2geo stopgrad(p_wall/p_roof)",
            )
        )

        sem_loss, sem_stats = semcal_roofwall_loss(
            model,
            e_gravity,
            tau=float(cfg.get("mutual_tau", 0.15)),
            temperature=float(args.semcal_temperature),
        )
        semcal_stats = sem_stats
        sem_grads = grads_for(sem_loss, params)
        sem_raw = float(sem_loss.detach().cpu())
        semcal_values.append(sem_raw)
        semcal_norms.append(grad_norm(sem_grads))
        rows.append(
            summarize_loss_row(
                batch_id=str(idx),
                loss_name="L_semcal_raw",
                raw_loss=sem_raw,
                weighted_loss=sem_raw,
                grads=sem_grads,
                base_grads=base_grads,
                base_norm=base_norm,
                loss_scale=1.0,
                notes="roof/wall KL(stopgrad(s_geom)||p); terrain excluded",
            )
        )

        local_kappa = grad_norm(legacy_grads) / grad_norm(geo_grads) if grad_norm(geo_grads) > 0 else 1.0
        local_beta_0p02 = (
            (0.02 * base_norm) / (lambda_mu * grad_norm(sem_grads))
            if lambda_mu > 0 and grad_norm(sem_grads) > 0
            else float("nan")
        )
        if math.isfinite(local_beta_0p02):
            joint_grads = add_grads(
                scale_grads(geo_grads, lambda_mu * local_kappa),
                scale_grads(sem_grads, lambda_mu * local_beta_0p02),
            )
            joint_weighted = lambda_mu * local_kappa * geo_raw + lambda_mu * local_beta_0p02 * sem_raw
            rows.append(
                summarize_loss_row(
                    batch_id=str(idx),
                    loss_name="A8_v2_joint_candidate_rho_sem_0p02",
                    raw_loss=geo_raw + local_beta_0p02 * sem_raw,
                    weighted_loss=joint_weighted,
                    grads=joint_grads,
                    base_grads=base_grads,
                    base_norm=base_norm,
                    loss_scale=1.0,
                    notes=(
                        "manual combined weighted gradient: "
                        f"lambda*kappa_geo={lambda_mu * local_kappa:.6g}, "
                        f"lambda*beta={lambda_mu * local_beta_0p02:.6g}"
                    ),
                )
            )

        if pos == 0:
            # The primitive-only losses are view-independent. One base batch is
            # enough for scale recommendation; extra batches only refine G_base.
            pass

    g_base = float(np.mean(base_norms)) if base_norms else 0.0
    g_legacy = float(np.mean(legacy_norms)) if legacy_norms else 0.0
    g_geo = float(np.mean(geo_norms)) if geo_norms else 0.0
    g_semcal = float(np.mean(semcal_norms)) if semcal_norms else 0.0

    kappa_match_legacy = g_legacy / g_geo if g_geo > 0 else float("nan")
    kappa_cap_0p05 = (0.05 * g_base) / (lambda_mu * g_geo) if lambda_mu > 0 and g_geo > 0 else float("nan")
    recommended_kappa = min(kappa_match_legacy, kappa_cap_0p05)
    beta_0p02 = (0.02 * g_base) / (lambda_mu * g_semcal) if lambda_mu > 0 and g_semcal > 0 else float("nan")
    beta_0p05 = (0.05 * g_base) / (lambda_mu * g_semcal) if lambda_mu > 0 and g_semcal > 0 else float("nan")

    def fnum(x: float) -> float | str:
        return x if math.isfinite(x) else ""

    aggregate = {
        "batch_id": "aggregate",
        "loss_name": "recommendation",
        "raw_loss": "",
        "weighted_loss": "",
        "grad_norm_total": "",
        "grad_norm_means": "",
        "grad_norm_quats": "",
        "grad_norm_sem_logits": "",
        "grad_ratio_to_base": "",
        "cosine_with_base": "",
        "notes": json.dumps(
            {
                "G_base": g_base,
                "G_legacy_raw": g_legacy,
                "G_geo_raw": g_geo,
                "G_semcal_raw": g_semcal,
                "lambda_mu": lambda_mu,
                "kappa_match_legacy": fnum(kappa_match_legacy),
                "kappa_cap_0p05_base": fnum(kappa_cap_0p05),
                "recommended_kappa_geo": fnum(recommended_kappa),
                "beta_rho_sem_0p02": fnum(beta_0p02),
                "beta_rho_sem_0p05": fnum(beta_0p05),
                "semcal_stats": semcal_stats,
            },
            sort_keys=True,
        ),
    }
    rows.append(aggregate)
    write_csv(PHASE1 / "gradient_scale_audit.csv", rows)

    md = [
        "# FC-S6D Phase 1: Recommended Initial Weights",
        "",
        "No training was run. Values come from the A8 checkpoint and a fixed train-view batch set.",
        "",
        f"- Config: `{rel(A8_CONFIG)}`",
        f"- Checkpoint: `{rel(A8_CKPT)}`",
        f"- Fixed train view indices: `{','.join(map(str, idxs))}`",
        f"- Device: `{device}`",
        f"- `G_base`: `{g_base:.6e}`",
        f"- `G_legacy_raw`: `{g_legacy:.6e}`",
        f"- `G_geo_raw`: `{g_geo:.6e}`",
        f"- `G_semcal_raw`: `{g_semcal:.6e}`",
        "",
        "## Recommended Scale",
        "",
        f"- `kappa_match_legacy = G_legacy_raw / G_geo_raw`: `{fnum(kappa_match_legacy)}`",
        f"- `kappa_cap_0p05_base = 0.05 * G_base / (lambda_mu * G_geo_raw)`: `{fnum(kappa_cap_0p05)}`",
        f"- `recommended kappa_geo`: `{fnum(recommended_kappa)}`",
        f"- `beta` for `rho_sem=0.02`: `{fnum(beta_0p02)}`",
        f"- `beta` for `rho_sem=0.05`: `{fnum(beta_0p05)}`",
        "",
        "## Interpretation",
        "",
        "- `A8_v2_geo` should start with `mutual_mode=sem2geo` and `w_mutual = 0.1 * kappa_geo`.",
        "- `A8_v2_joint` needs a new default-off semantic calibration implementation before it can be trained.",
        "- The recommended `beta` is numerically large because the raw semcal gradient is small relative to the base gradient; treat this as a scale warning, not permission to launch joint training.",
        "- The semcal audit formula is roof/wall-only and excludes terrain to preserve the accepted A8 terrain-off boundary.",
    ]
    (PHASE1 / "recommended_initial_weights.md").write_text("\n".join(md) + "\n")

    return {
        "G_base": g_base,
        "G_legacy_raw": g_legacy,
        "G_geo_raw": g_geo,
        "G_semcal_raw": g_semcal,
        "recommended_kappa_geo": recommended_kappa,
        "beta_rho_sem_0p02": beta_0p02,
        "beta_rho_sem_0p05": beta_0p05,
        "fixed_batch_indices": idxs,
    }


def write_blocked_scale_audit(reason: str) -> Dict[str, Any]:
    rows = [
        {
            "batch_id": "NA",
            "loss_name": "BLOCKED",
            "raw_loss": "",
            "weighted_loss": "",
            "grad_norm_total": "",
            "grad_norm_means": "",
            "grad_norm_quats": "",
            "grad_norm_sem_logits": "",
            "grad_ratio_to_base": "",
            "cosine_with_base": "",
            "notes": reason,
        }
    ]
    write_csv(PHASE1 / "gradient_scale_audit.csv", rows)
    (PHASE1 / "recommended_initial_weights.md").write_text(
        "\n".join(
            [
                "# FC-S6D Phase 1: Recommended Initial Weights",
                "",
                "No-training gradient-scale audit is blocked.",
                "",
                f"- Blocker: {reason}",
                "",
                "No directional screening training should be launched until this audit is rerun successfully.",
            ]
        )
        + "\n"
    )
    return {"blocked": reason}


def extract_a8_existing_rows() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    by_bid = []
    split = []
    if A8_BY_BID.exists():
        for r in read_csv(A8_BY_BID):
            if r.get("run") == "A8_no_terrain_terms":
                row = dict(r)
                row["candidate"] = "A8_legacy_terrain_off"
                by_bid.append(row)
    if A8_SPLIT.exists():
        for r in read_csv(A8_SPLIT):
            if r.get("run") == "A8_no_terrain_terms":
                row = dict(r)
                row["candidate"] = "A8_legacy_terrain_off"
                split.append(row)
    return by_bid, split


def write_phase2(cfg: Dict[str, Any], rec: Dict[str, Any]) -> None:
    a8_bid, a8_split = extract_a8_existing_rows()

    metric_fields = [
        "candidate",
        "run",
        "bid",
        "status",
        "F",
        "precision",
        "recall",
        "roof_cov",
        "wall_cov",
        "ground_cov",
        "support_cov",
        "roof_support_cov",
        "wall_support_cov",
        "ground_support_cov",
        "h_err",
        "vol_ratio",
        "chamfer",
        "hausdorff",
        "open_edges",
        "non_manifold_edges",
        "failure_reason",
    ]
    out_bid = []
    for r in a8_bid:
        out_bid.append({k: r.get(k, "") for k in metric_fields})
    for cand in ["A8_v2_geo", "A8_v2_joint"]:
        out_bid.append(
            {
                "candidate": cand,
                "run": cand,
                "bid": "ALL",
                "status": "PENDING_NOT_RUN",
                "failure_reason": "FC-S6D setup only; short directional screening training/evaluation not launched.",
            }
        )
    write_csv(PHASE2 / "directional_metrics_by_bid.csv", out_bid, metric_fields)

    split_fields = [
        "candidate",
        "run",
        "split",
        "n_bids",
        "ok_count",
        "status",
        "mean_F",
        "mean_precision",
        "mean_recall",
        "mean_roof_cov",
        "mean_wall_cov",
        "mean_ground_cov",
        "mean_support_cov",
        "mean_roof_support_cov",
        "mean_wall_support_cov",
        "mean_ground_support_cov",
        "mean_h_err",
        "mean_vol_ratio",
        "mean_chamfer",
        "mean_hausdorff",
        "mean_open_edges",
        "mean_non_manifold_edges",
        "note",
    ]
    out_split = []
    for r in a8_split:
        out_split.append({k: r.get(k, "") for k in split_fields})
    for cand in ["A8_v2_geo", "A8_v2_joint"]:
        out_split.append(
            {
                "candidate": cand,
                "run": cand,
                "split": "all_10",
                "n_bids": "10",
                "ok_count": "0",
                "status": "PENDING_NOT_RUN",
                "note": "FC-S6D setup only; no Stage3Algo-v1 + Metric-v1 outputs yet.",
            }
        )
    write_csv(PHASE2 / "directional_split_summary.csv", out_split, split_fields)

    kappa = rec.get("recommended_kappa_geo")
    beta = rec.get("beta_rho_sem_0p02")
    cfg_geo = dict(cfg)
    cfg_geo["out_dir"] = rel(OUT_ROOT / "phase2_screening/runs/A8_v2_geo")
    cfg_geo["mutual_mode"] = "sem2geo"
    if isinstance(kappa, float) and math.isfinite(kappa):
        cfg_geo["w_mutual"] = float(cfg.get("w_mutual", 0.1)) * kappa
        cfg_geo["fc_s6d_kappa_geo"] = kappa
    cfg_geo["w_structure"] = 0.0
    (CONFIG_ROOT / "A8_v2_geo.yaml").write_text(yaml.safe_dump(cfg_geo, sort_keys=False))

    old_joint = CONFIG_ROOT / "A8_v2_joint.yaml"
    if old_joint.exists():
        old_joint.unlink()
    cfg_joint = dict(cfg_geo)
    cfg_joint["out_dir"] = rel(OUT_ROOT / "phase2_screening/runs/A8_v2_joint")
    cfg_joint["fc_s6d_semcal_beta_rho_0p02"] = beta if isinstance(beta, float) and math.isfinite(beta) else "BLOCKED"
    cfg_joint["fc_s6d_train_support"] = "BLOCKED: semantic calibration is audit-only until implemented default-off in Stage2 loss/train path"
    (CONFIG_ROOT / "A8_v2_joint_BLOCKED.yaml").write_text(yaml.safe_dump(cfg_joint, sort_keys=False))

    decision = [
        "# FC-S6D Directional Decision",
        "",
        "## Decision Label",
        "",
        "`KEEP_A8_LEGACY` as the current live-product reference only.",
        "",
        "This is not a claim that A8 is the final directional design. It means no directional Stage3 evidence exists yet for `A8_v2_geo` or `A8_v2_joint`.",
        "",
        "## Evidence State",
        "",
        "- A8 existing Stage3Algo-v1 + Metric-v1 rows were copied from FC-S6b/FC-S6 phase outputs.",
        "- `A8_v2_geo` is config-preparable because existing `mutual_mode=sem2geo` detaches semantic probabilities.",
        "- Runnable geo config: `configs/fc_s6d/A8_v2_geo.yaml`.",
        "- `A8_v2_joint` is not train-ready because the explicit KL semantic calibration term is not implemented in the Stage2 training path.",
        "- Joint stub is deliberately blocked at `configs/fc_s6d/A8_v2_joint_BLOCKED.yaml` to avoid accidentally running a geo-only substitute.",
        "- No FC-S6D training, Stage3 evaluation, L_structure, or G2 run was launched.",
        "",
        "## Phase 3 Recommendation",
        "",
        "- Do not run Lmu7 yet.",
        "- If directional screening is launched next, test `A8_v2_geo` first because it is the minimal directionality change and is supported by the existing config path.",
        "- Add Lmu7 single-term smoke only after either A8 legacy is explicitly retained after screening or `A8_v2_geo`/`A8_v2_joint` is selected by Stage3Algo-v1 + Metric-v1.",
        "",
        "## Blockers Before A8_v2_joint",
        "",
        "- Implement roof/wall `L_semcal = KL(stopgrad(s_geom)||p)` behind a default-off flag.",
        "- Re-run default-off equivalence.",
        "- Re-run the no-training gradient-scale audit after implementation.",
    ]
    (PHASE2 / "FC_S6D_DIRECTIONAL_DECISION.md").write_text("\n".join(decision) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n-batches", type=int, default=1)
    ap.add_argument("--semcal-temperature", type=float, default=0.05)
    ap.add_argument("--skip-scale-audit", action="store_true")
    args = ap.parse_args()

    ensure_dirs()
    cfg = read_yaml(A8_CONFIG)
    write_phase0(cfg)

    if args.skip_scale_audit:
        rec = write_blocked_scale_audit("Skipped by --skip-scale-audit.")
    else:
        try:
            rec = run_scale_audit(cfg, args)
        except Exception as exc:  # keep setup auditable instead of crashing half-written
            rec = write_blocked_scale_audit(f"{type(exc).__name__}: {exc}")

    write_phase2(cfg, rec)
    print(f"[fc-s6d] wrote outputs under {rel(OUT_ROOT)}")


if __name__ == "__main__":
    main()

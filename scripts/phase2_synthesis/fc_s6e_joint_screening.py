"""FC-S6E A8_v2_joint explicit bidirectional Mutual screening.

Boundaries:
- no L_structure, G2, Lmu7, or Lmu8
- no Stage3 or Metric-v1 code changes
- no GT roof type, roof partition, final mesh, or semantic surfaces for Stage2 loss
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import torch
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.fc_s6d_directionality_setup import (  # noqa: E402
    A8_CKPT,
    A8_CONFIG,
    add_grads,
    compute_base_loss,
    grad_cos,
    grad_norm,
    grad_params,
    grads_for,
    gravity_from_cfg,
    load_model_from_ckpt,
    scale_grads,
    train_indices,
)
from src.stage2.dataloader import ColmapDataset  # noqa: E402
from src.stage2.loss.mutual import l_mutual  # noqa: E402


OUT_ROOT = ROOT / "results/FC_S6E_joint"
PHASE0 = OUT_ROOT / "phase0_implementation"
PHASE1 = OUT_ROOT / "phase1_gradient_audit"
PHASE3 = OUT_ROOT / "phase3_eval"
PHASE4 = OUT_ROOT / "phase4_viewer"
JOBS = OUT_ROOT / "jobs"
CONFIGS = OUT_ROOT / "configs"
LOGS = OUT_ROOT / "logs"
CHECKPOINTS = OUT_ROOT / "checkpoints"
EVIDENCE = OUT_ROOT / "evidence_exports"

FC_S6_PHASE1_METRICS = (
    ROOT
    / "results/FC_S6_componentwise_revised_lmutual_design_validation"
    / "phase1_existing_terms/term_ablation_metrics_by_bid.csv"
)
FC_S6_PHASE2_METRICS = (
    ROOT
    / "results/FC_S6_componentwise_revised_lmutual_design_validation"
    / "phase2_terrain_safe/terrain_safe_metrics_by_bid.csv"
)
FC_S6D_GEO_METRICS = ROOT / "results/FC_S6D_directional_screening/phase3_eval/a8_v2_geo_metrics_by_bid.csv"
FC_S6D_GEO_SPLIT = ROOT / "results/FC_S6D_directional_screening/phase3_eval/a8_v2_geo_split_summary.csv"

TARGET_BIDS = ["B0", "B1", "B2", "B8", "B6", "B3", "B123", "B126", "B50", "B104"]
QA_BIDS = ["B104", "B6", "B3", "B123", "B126", "B0", "B1", "B2"]
REFERENCE_RUNS = [
    "A0_baseline_w0",
    "A1_original_mutual",
    "A4_terrain_normal_only",
    "A8_no_terrain_terms",
    "B2_terrain_confidence_gated",
    "A9_no_terrain_terms_ramp",
    "A8_v2_geo",
]
JOINT_RUN = "A8_v2_joint_2pct"
METRIC_FIELDS = [
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
    "n_faces",
    "n_roof_faces",
    "n_wall_faces",
    "n_ground_faces",
    "terrain_y_p10",
    "terrain_y_p50",
    "terrain_y_p90",
    "mutual_mass_roof",
    "mutual_mass_wall",
    "mutual_mass_terrain",
    "entropy_roof",
    "entropy_wall",
    "entropy_terrain",
]
SPLITS = {
    "all_10": TARGET_BIDS,
    "easy_control": ["B0", "B1", "B2", "B8", "B50"],
    "hard_diagnostic": ["B104", "B6", "B3", "B123", "B126"],
    "roof_complex": ["B3", "B123", "B126"],
    "terrain_sensitive": ["B104", "B6", "B50"],
    "guard_bids": ["B104", "B6", "B3", "B123", "B126", "B2", "B0", "B1"],
}


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def mkdirs() -> None:
    for d in [
        PHASE0,
        PHASE1,
        PHASE3,
        PHASE4 / "saved_views",
        JOBS,
        CONFIGS,
        LOGS,
        CHECKPOINTS,
        EVIDENCE,
    ]:
        d.mkdir(parents=True, exist_ok=True)


def read_yaml(path: Path) -> Dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f)


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        seen = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    fields.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def safe_float(v: Any) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def run_rows(path: Path, run: str) -> List[Dict[str, str]]:
    return [r for r in read_csv(path) if r.get("run") == run]


def row_for(rows: List[Dict[str, str]], key: str, value: str) -> Optional[Dict[str, str]]:
    return next((r for r in rows if r.get(key) == value), None)


def mean(rows: Iterable[Dict[str, str]], field: str) -> Optional[float]:
    vals = [safe_float(r.get(field)) for r in rows]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def write_phase0(default_diff: float) -> None:
    lines = [
        "# FC-S6E Phase 0: L_semcal Implementation",
        "",
        "## Status",
        "",
        "`IMPLEMENTED_DEFAULT_OFF`",
        "",
        "## Scope",
        "",
        "- Added optional roof/wall-only `L_semcal` inside `src/stage2/loss/mutual.py`.",
        "- Training integration is controlled by config flags in `src/stage2/train.py`.",
        "- Terrain semantic calibration remains disabled for FC-S6E.",
        "- Lmu7, Lmu8, L_structure, G2, Stage3, and Metric-v1 are not modified.",
        "",
        "## Config Flags",
        "",
        "- `mutual_semcal_enabled`: default `false`",
        "- `mutual_semcal_classes`: default `roof_wall`",
        "- `mutual_semcal_tau`: geometry cue temperature",
        "- `mutual_semcal_weight_beta`: beta inside the mutual raw total",
        "- `mutual_semcal_reliability_gate`: `none|confidence|entropy|conf_entropy`",
        "- `mutual_semcal_entropy_tau`, `mutual_semcal_entropy_alpha`: entropy gate shape",
        "",
        "## Formula",
        "",
        "`p_rw = normalize([p_roof, p_wall])`",
        "",
        "`score_roof = exp(-relu(tau - (n dot g)^2)^2 / tau_geom)`",
        "",
        "`score_wall = exp(-(n dot g)^2 / tau_geom)`",
        "",
        "`s_geom = normalize([score_roof, score_wall])`",
        "",
        "`L_semcal = mean stopgrad(reliability) * KL(stopgrad(s_geom) || p_rw)`",
        "",
        "## Effective Training Scale",
        "",
        "The train path uses `loss += w_mutual * (L_geo + beta_cfg * L_semcal)`.",
        "For FC-S6E, `w_mutual = lambda_mu * kappa_geo`, so `beta_cfg = beta_effective / kappa_geo`.",
    ]
    (PHASE0 / "L_SEMCAL_IMPLEMENTATION.md").write_text("\n".join(lines) + "\n")

    (PHASE0 / "default_off_equivalence.md").write_text(
        "\n".join(
            [
                "# FC-S6E Phase 0: Default-off Equivalence",
                "",
                "## Result",
                "",
                "`PASS`" if default_diff <= 1e-12 else "`CHECK`",
                "",
                f"- Random fixed-batch mutual scalar difference with semcal default-off: `{default_diff:.12e}`",
                "- Existing defaults keep `mutual_semcal_enabled=false` and `mutual_semcal_weight_beta=0.0`.",
                "- No additional backward path is active unless the flag and beta are explicitly set.",
            ]
        )
        + "\n"
    )

    write_csv(
        PHASE0 / "semcal_formula_table.csv",
        [
            {
                "component": "geometry_teacher",
                "formula": "s_geom = normalize([exp(-e_roof/tau_geom), exp(-e_wall/tau_geom)])",
                "gradient_path": "stopgrad",
                "classes": "roof,wall",
            },
            {
                "component": "semantic_student",
                "formula": "p_rw = normalize([p_roof,p_wall])",
                "gradient_path": "semantic logits receive gradient",
                "classes": "roof,wall",
            },
            {
                "component": "reliability",
                "formula": "confidence_gate * sigmoid((entropy_tau - entropy_rw) / entropy_alpha)",
                "gradient_path": "stopgrad",
                "classes": "roof,wall",
            },
            {
                "component": "loss",
                "formula": "mean stopgrad(reliability) * KL(stopgrad(s_geom) || p_rw)",
                "gradient_path": "semantic only",
                "classes": "roof,wall",
            },
        ],
    )


def default_off_check() -> float:
    gen = torch.Generator().manual_seed(608)
    normals = torch.randn(256, 3, generator=gen)
    centers = torch.randn(256, 3, generator=gen)
    sem_logits = torch.randn(256, 4, generator=gen)
    e_gravity = torch.tensor([0.0, 1.0, 0.0])
    base = l_mutual(normals, centers, sem_logits, e_gravity, mode="sem2geo")["total"]
    off = l_mutual(
        normals,
        centers,
        sem_logits,
        e_gravity,
        mode="sem2geo",
        enable_sem_geom_calib=False,
        semcal_weight_beta=999.0,
    )["total"]
    return float((base - off).abs().detach().cpu())


def l_mutual_from_cfg(
    model: torch.nn.Module,
    cfg: Dict[str, Any],
    e_gravity: torch.Tensor,
    *,
    mode: str,
    enable_semcal: bool = False,
    semcal_beta: float = 0.0,
    existing_terms: bool = True,
) -> torch.Tensor:
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
        enable_wall_vertical=existing_terms and bool(cfg.get("mutual_enable_wall_vertical", True)),
        enable_roof_nonwall=existing_terms and bool(cfg.get("mutual_enable_roof_nonwall", True)),
        enable_terrain_normal=existing_terms and bool(cfg.get("mutual_enable_terrain_normal", True)),
        enable_terrain_height=existing_terms and bool(cfg.get("mutual_enable_terrain_height", True)),
        enable_height_roof_side=existing_terms and bool(cfg.get("mutual_enable_height_roof_side", True)),
        enable_height_terrain_side=existing_terms and bool(cfg.get("mutual_enable_height_terrain_side", True)),
        terrain_gate_mode=cfg.get("mutual_terrain_gate_mode", "none"),
        terrain_gate_conf_min=float(cfg.get("mutual_terrain_gate_conf_min", 0.0)),
        terrain_gate_mass_min=float(cfg.get("mutual_terrain_gate_mass_min", 0.0)),
        terrain_gate_entropy_max=float(cfg.get("mutual_terrain_gate_entropy_max", 1.0)),
        terrain_height_reference=cfg.get("mutual_terrain_height_reference", "fixed"),
        terrain_height_quantile=float(cfg.get("mutual_terrain_height_quantile", 0.5)),
        terrain_height_margin=float(cfg.get("mutual_terrain_height_margin", 0.0)),
        enable_sem_geom_calib=enable_semcal,
        semcal_classes=cfg.get("mutual_semcal_classes", "roof_wall"),
        semcal_tau=float(cfg.get("mutual_semcal_tau", 0.05)),
        semcal_weight_beta=semcal_beta,
        semcal_reliability_gate=cfg.get("mutual_semcal_reliability_gate", "conf_entropy"),
        semcal_entropy_tau=float(cfg.get("mutual_semcal_entropy_tau", 0.75)),
        semcal_entropy_alpha=float(cfg.get("mutual_semcal_entropy_alpha", 0.10)),
    )
    return terms["total"]


def summarize_grad_row(
    batch_id: str,
    loss_name: str,
    raw_loss: float,
    weighted_loss: float,
    grads: Dict[str, torch.Tensor | None],
    base_grads: Optional[Dict[str, torch.Tensor | None]],
    base_norm: float,
    loss_scale: float,
    notes: str,
) -> Dict[str, Any]:
    weighted_grads = scale_grads(grads, loss_scale)
    raw_norm = grad_norm(grads)
    weighted_norm = grad_norm(weighted_grads)
    return {
        "batch_id": batch_id,
        "loss_name": loss_name,
        "raw_loss": raw_loss,
        "weighted_loss": weighted_loss,
        "loss_scale": loss_scale,
        "grad_norm_total": raw_norm,
        "grad_norm_means": grad_norm(grads, ["means"]),
        "grad_norm_quats": grad_norm(grads, ["quats"]),
        "grad_norm_sem_logits": grad_norm(grads, ["sem_logits"]),
        "grad_ratio_to_base": raw_norm / base_norm if base_norm > 0 else "",
        "weighted_grad_norm_total": weighted_norm,
        "weighted_grad_ratio_to_base": weighted_norm / base_norm if base_norm > 0 else "",
        "cosine_with_base": grad_cos(grads, base_grads) if base_grads is not None else "",
        "notes": notes,
    }


def run_gradient_audit(cfg: Dict[str, Any], args: argparse.Namespace) -> Dict[str, float]:
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

    lambda_mu = float(read_yaml(A8_CONFIG).get("w_mutual", 0.1))
    kappa_geo = float(cfg.get("fc_s6d_kappa_geo", 1.0))
    rows: List[Dict[str, Any]] = []
    base_norms: List[float] = []
    sem_norms: List[float] = []
    geo_norms: List[float] = []
    legacy_norms: List[float] = []

    for idx in idxs:
        batch = ds[int(idx)]
        base_loss, base_vals = compute_base_loss(model, batch, cfg, device)
        base_grads = grads_for(base_loss, params)
        base_norm = grad_norm(base_grads)
        base_norms.append(base_norm)
        rows.append(
            summarize_grad_row(
                str(idx),
                "L_base",
                float(base_loss.detach().cpu()),
                float(base_loss.detach().cpu()),
                base_grads,
                None,
                base_norm,
                1.0,
                json.dumps(base_vals, sort_keys=True),
            )
        )

        legacy_loss = l_mutual_from_cfg(model, cfg, e_gravity, mode="full")
        legacy_grads = grads_for(legacy_loss, params)
        legacy_norms.append(grad_norm(legacy_grads))
        rows.append(
            summarize_grad_row(
                str(idx),
                "A8_legacy_mutual_raw",
                float(legacy_loss.detach().cpu()),
                lambda_mu * float(legacy_loss.detach().cpu()),
                legacy_grads,
                base_grads,
                base_norm,
                lambda_mu,
                "full bidirectional p*geometry A8 terms",
            )
        )

        geo_loss = l_mutual_from_cfg(model, cfg, e_gravity, mode="sem2geo")
        geo_grads = grads_for(geo_loss, params)
        geo_norms.append(grad_norm(geo_grads))
        rows.append(
            summarize_grad_row(
                str(idx),
                "A8_v2_geo_raw",
                float(geo_loss.detach().cpu()),
                lambda_mu * kappa_geo * float(geo_loss.detach().cpu()),
                geo_grads,
                base_grads,
                base_norm,
                lambda_mu * kappa_geo,
                f"sem2geo stopgrad(p); kappa_geo={kappa_geo}",
            )
        )

        semcal_loss = l_mutual_from_cfg(
            model,
            cfg,
            e_gravity,
            mode="sem2geo",
            enable_semcal=True,
            semcal_beta=1.0,
            existing_terms=False,
        )
        semcal_grads = grads_for(semcal_loss, params)
        sem_norms.append(grad_norm(semcal_grads))
        rows.append(
            summarize_grad_row(
                str(idx),
                "L_semcal_raw",
                float(semcal_loss.detach().cpu()),
                float(semcal_loss.detach().cpu()),
                semcal_grads,
                base_grads,
                base_norm,
                1.0,
                "roof/wall KL(stopgrad(s_geom)||p_rw); terrain excluded",
            )
        )

        g_sem = grad_norm(semcal_grads)
        beta_2 = (0.02 * base_norm) / (lambda_mu * g_sem) if lambda_mu > 0 and g_sem > 0 else float("nan")
        if math.isfinite(beta_2):
            joint_grads = add_grads(
                scale_grads(geo_grads, lambda_mu * kappa_geo),
                scale_grads(semcal_grads, lambda_mu * beta_2),
            )
            joint_weighted_loss = (
                lambda_mu * kappa_geo * float(geo_loss.detach().cpu())
                + lambda_mu * beta_2 * float(semcal_loss.detach().cpu())
            )
            rows.append(
                summarize_grad_row(
                    str(idx),
                    "A8_v2_joint_2pct_candidate",
                    float(geo_loss.detach().cpu()) + beta_2 * float(semcal_loss.detach().cpu()),
                    joint_weighted_loss,
                    joint_grads,
                    base_grads,
                    base_norm,
                    1.0,
                    f"effective lambda*kappa={lambda_mu*kappa_geo:.8g}; lambda*beta={lambda_mu*beta_2:.8g}",
                )
            )

    g_base = sum(base_norms) / len(base_norms)
    g_sem = sum(sem_norms) / len(sem_norms)
    g_geo = sum(geo_norms) / len(geo_norms)
    g_legacy = sum(legacy_norms) / len(legacy_norms)
    beta_2 = (0.02 * g_base) / (lambda_mu * g_sem) if lambda_mu > 0 and g_sem > 0 else float("nan")
    beta_5 = (0.05 * g_base) / (lambda_mu * g_sem) if lambda_mu > 0 and g_sem > 0 else float("nan")
    beta_cfg_2 = beta_2 / kappa_geo if kappa_geo > 0 and math.isfinite(beta_2) else float("nan")

    rec = {
        "G_base": g_base,
        "G_legacy_raw": g_legacy,
        "G_geo_raw": g_geo,
        "G_semcal_raw": g_sem,
        "lambda_mu": lambda_mu,
        "kappa_geo": kappa_geo,
        "beta_rho_sem_0p02": beta_2,
        "beta_rho_sem_0p05": beta_5,
        "beta_cfg_rho_sem_0p02": beta_cfg_2,
    }
    rows.append({"batch_id": "aggregate", "loss_name": "recommendation", "notes": json.dumps(rec, sort_keys=True)})
    write_csv(PHASE1 / "gradient_scale_audit.csv", rows)

    (PHASE1 / "recommended_joint_weights.md").write_text(
        "\n".join(
            [
                "# FC-S6E Phase 1: Recommended Joint Weights",
                "",
                "No training was run for this audit.",
                "",
                f"- Config base: `{rel(A8_CONFIG)}`",
                f"- Checkpoint: `{rel(A8_CKPT)}`",
                f"- Fixed train view indices: `{','.join(map(str, idxs))}`",
                f"- Device: `{device}`",
                f"- `G_base`: `{g_base:.6e}`",
                f"- `G_legacy_raw`: `{g_legacy:.6e}`",
                f"- `G_geo_raw`: `{g_geo:.6e}`",
                f"- `G_semcal_raw`: `{g_sem:.6e}`",
                f"- `kappa_geo`: `{kappa_geo}`",
                f"- effective `beta` for `rho_sem=0.02`: `{beta_2}`",
                f"- effective `beta` for `rho_sem=0.05`: `{beta_5}`",
                f"- train-config `mutual_semcal_weight_beta` for 2pct: `{beta_cfg_2}`",
                "",
                "The train path uses `w_mutual=lambda*kappa_geo`, so the config beta is divided by `kappa_geo` to keep the effective semantic calibration coefficient at `lambda*beta`.",
                "",
                "Primary runnable candidate: `A8_v2_joint_2pct`.",
                "Do not run 5pct unless the 2pct run is stable but too weak.",
            ]
        )
        + "\n"
    )

    sem_row = row_for(rows, "loss_name", "L_semcal_raw") or {}
    (PHASE1 / "gradient_cosine_report.md").write_text(
        "\n".join(
            [
                "# FC-S6E Phase 1: Gradient Cosine Report",
                "",
                f"- L_semcal cosine with base: `{sem_row.get('cosine_with_base', '')}`",
                f"- L_semcal semantic-logit grad norm: `{sem_row.get('grad_norm_sem_logits', '')}`",
                f"- L_semcal geometry grad norm means/quats: `{sem_row.get('grad_norm_means', '')}`, `{sem_row.get('grad_norm_quats', '')}`",
                "",
                "Expected behavior: semantic-logit gradient is nonzero; geometry gradient is zero because geometry is teacher-side stopgrad.",
            ]
        )
        + "\n"
    )
    return rec


def joint_config(base_cfg: Dict[str, Any], rec: Dict[str, float]) -> Dict[str, Any]:
    cfg = dict(base_cfg)
    cfg["out_dir"] = rel(CHECKPOINTS / JOINT_RUN)
    cfg["fc_s6_arm"] = JOINT_RUN
    cfg["fc_s6_phase"] = "FC_S6E_joint"
    cfg["fc_s6_description"] = "A8_v2_joint_2pct explicit sem2geo plus roof/wall semcal screening."
    cfg["fc_s6e_joint_screening"] = True
    cfg["mutual_mode"] = "sem2geo"
    cfg["w_mutual"] = float(read_yaml(A8_CONFIG).get("w_mutual", 0.1)) * float(rec["kappa_geo"])
    cfg["mutual_semcal_enabled"] = True
    cfg["mutual_semcal_classes"] = "roof_wall"
    cfg["mutual_semcal_tau"] = float(cfg.get("mutual_semcal_tau", 0.05))
    cfg["mutual_semcal_weight_beta"] = float(rec["beta_cfg_rho_sem_0p02"])
    cfg["mutual_semcal_effective_beta"] = float(rec["beta_rho_sem_0p02"])
    cfg["mutual_semcal_target_rho"] = 0.02
    cfg["mutual_semcal_reliability_gate"] = cfg.get("mutual_semcal_reliability_gate", "conf_entropy")
    cfg["mutual_semcal_entropy_tau"] = float(cfg.get("mutual_semcal_entropy_tau", 0.75))
    cfg["mutual_semcal_entropy_alpha"] = float(cfg.get("mutual_semcal_entropy_alpha", 0.10))
    cfg["mutual_enable_terrain_normal"] = False
    cfg["mutual_enable_terrain_height"] = False
    cfg["mutual_enable_height_terrain_side"] = False
    cfg["mutual_enable_roof_wall_relation"] = False
    cfg["mutual_enable_terrain_wall_relation"] = False
    cfg["w_structure"] = 0.0
    return cfg


def reference_metric_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for run in ["A0_baseline_w0", "A1_original_mutual", "A4_terrain_normal_only", "A8_no_terrain_terms", "A9_no_terrain_terms_ramp"]:
        rows.extend(run_rows(FC_S6_PHASE1_METRICS, run))
    rows.extend(run_rows(FC_S6_PHASE2_METRICS, "B2_terrain_confidence_gated"))
    rows.extend(run_rows(FC_S6D_GEO_METRICS, "A8_v2_geo"))
    return rows


def write_reference_and_pending_metrics() -> None:
    rows = reference_metric_rows()
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    for key in ["run", "bid", "job_status", "config_path", "status", *METRIC_FIELDS, "failure_reason"]:
        if key not in fields:
            fields.append(key)
    for bid in TARGET_BIDS:
        rows.append(
            {
                "run": JOINT_RUN,
                "bid": bid,
                "job_status": "LAUNCHED_OR_PENDING",
                "config_path": rel(CONFIGS / f"{JOINT_RUN}.yaml"),
                "status": "PENDING",
                "failure_reason": "pending Stage2 training, evidence export, Stage3Algo-v1, and Metric-v1 evaluation",
            }
        )
    write_csv(PHASE3 / "a8_v2_joint_metrics_by_bid.csv", rows, fields)


def write_config_and_jobs(cfg: Dict[str, Any]) -> None:
    cfg_path = CONFIGS / f"{JOINT_RUN}.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    metrics = PHASE3 / "a8_v2_joint_metrics_by_bid.csv"
    split = PHASE3 / "a8_v2_joint_split_summary.csv"
    win_loss = PHASE3 / "a8_v2_joint_vs_a8_vs_geo_win_loss.csv"
    checkpoint = CHECKPOINTS / f"{JOINT_RUN}/ckpt/final.pt"
    train_log = LOGS / f"{JOINT_RUN}.train_eval.log"
    nohup_log = LOGS / f"{JOINT_RUN}.nohup.out"
    evidence = EVIDENCE / JOINT_RUN
    job_record = JOBS / f"{JOINT_RUN}_job_record.txt"
    run_script = JOBS / f"run_{JOINT_RUN}.sh"
    launch_script = JOBS / f"launch_{JOINT_RUN}.sh"
    pid_file = JOBS / f"{JOINT_RUN}.pid"

    run_script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

ARM="{JOINT_RUN}"
CONFIG="{rel(cfg_path)}"
CHECKPOINT="{rel(checkpoint)}"
LOG="{rel(train_log)}"
EVIDENCE="{rel(evidence)}"
METRICS="{rel(metrics)}"
SPLIT="{rel(split)}"
WINLOSS="{rel(win_loss)}"
JOB_RECORD="{rel(job_record)}"

mkdir -p "$(dirname "$LOG")" "$(dirname "$JOB_RECORD")" "{rel(EVIDENCE)}" "{rel(PHASE3)}"

GIT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || true)"
SEED="$(python - "$CONFIG" <<'PY'
import sys, yaml
with open(sys.argv[1]) as f:
    print(yaml.safe_load(f).get("seed", ""))
PY
)"
OUT_DIR="$(python - "$CONFIG" <<'PY'
import sys, yaml
with open(sys.argv[1]) as f:
    print(yaml.safe_load(f).get("out_dir", ""))
PY
)"

cat > "$JOB_RECORD" <<EOF
job_name: $ARM
launch_backend: setsid_detached
config_path: $CONFIG
seed: $SEED
checkpoint_path: $CHECKPOINT
train_log_path: $LOG
render_evidence_path: $EVIDENCE
stage3_evaluation_command: python scripts/phase2_synthesis/fc_s6_stage3_metric_v1_eval.py --run-name $ARM --config $CONFIG --checkpoint $CHECKPOINT --rendered-evidence-root $EVIDENCE --out-csv $METRICS --split-summary-csv $SPLIT --win-loss-csv $WINLOSS
output_directory: $OUT_DIR
git_commit: ${{GIT_COMMIT:-unavailable}}
started_at: $(date -Is)
pid: $$
EOF

exec >> "$LOG" 2>&1
echo "[fc-s6e] arm=$ARM config=$CONFIG out=$OUT_DIR"
echo "[fc-s6e] seed=$SEED git=${{GIT_COMMIT:-unavailable}}"

if [ -f "$CHECKPOINT" ] && [ "${{FC_S6E_FORCE_RETRAIN:-0}}" != "1" ]; then
    echo "[fc-s6e] checkpoint exists; skipping train: $CHECKPOINT"
    TRAIN_STATUS=0
else
    echo "[fc-s6e] train=python -m src.stage2.train --config $CONFIG"
    set +e
    python -m src.stage2.train --config "$CONFIG"
    TRAIN_STATUS="$?"
    set -e
fi
echo "train_exit_status: $TRAIN_STATUS" >> "$JOB_RECORD"
if [ "$TRAIN_STATUS" -ne 0 ]; then
    echo "finished_at: $(date -Is)" >> "$JOB_RECORD"
    exit "$TRAIN_STATUS"
fi

echo "[fc-s6e] eval=python scripts/phase2_synthesis/fc_s6_stage3_metric_v1_eval.py --run-name $ARM --config $CONFIG --checkpoint $CHECKPOINT --rendered-evidence-root $EVIDENCE --out-csv $METRICS --split-summary-csv $SPLIT --win-loss-csv $WINLOSS"
set +e
python scripts/phase2_synthesis/fc_s6_stage3_metric_v1_eval.py \\
    --run-name "$ARM" \\
    --config "$CONFIG" \\
    --checkpoint "$CHECKPOINT" \\
    --rendered-evidence-root "$EVIDENCE" \\
    --out-csv "$METRICS" \\
    --split-summary-csv "$SPLIT" \\
    --win-loss-csv "$WINLOSS"
EVAL_STATUS="$?"
set -e
echo "eval_exit_status: $EVAL_STATUS" >> "$JOB_RECORD"

python scripts/phase2_synthesis/fc_s6e_joint_screening.py --post-eval || true
echo "finished_at: $(date -Is)" >> "$JOB_RECORD"
exit "$EVAL_STATUS"
"""
    )
    run_script.chmod(0o755)

    launch_script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"
NOHUP_LOG="{rel(nohup_log)}"
RUN_SCRIPT="{rel(run_script)}"
MANIFEST="{rel(JOBS / 'FC_S6E_JOB_MANIFEST.md')}"
mkdir -p "$(dirname "$NOHUP_LOG")"
setsid bash "$RUN_SCRIPT" > "$NOHUP_LOG" 2>&1 < /dev/null &
PID="$!"
echo "$PID" > "{rel(pid_file)}"
cat >> "$MANIFEST" <<EOF

## Launch Record
- launched_at: $(date -Is)
- launch_backend: setsid_detached
- process_id: $PID
- nohup_log: $NOHUP_LOG
EOF
echo "$PID"
"""
    )
    launch_script.chmod(0o755)

    manifest = [
        "# FC-S6E Job Manifest",
        "",
        "## Scope",
        f"- Arm launched/prepared: `{JOINT_RUN}` only.",
        "- `A8_v2_joint_5pct`, Lmu7, Lmu8, L_structure, and G2 are not run.",
        "- Stage3 and Metric-v1 are called only after the Stage2 checkpoint exists.",
        "",
        "## Backend",
        "- `setsid` detached shell is used for persistence.",
        "",
        f"## {JOINT_RUN}",
        f"- config_path: `{rel(cfg_path)}`",
        f"- seed: `{cfg.get('seed')}`",
        f"- checkpoint_path: `{rel(checkpoint)}`",
        f"- train_log_path: `{rel(train_log)}`",
        f"- render_evidence_path: `{rel(evidence)}`",
        f"- output_directory: `{cfg.get('out_dir')}`",
        f"- stage3_evaluation_command: `python scripts/phase2_synthesis/fc_s6_stage3_metric_v1_eval.py --run-name {JOINT_RUN} --config {rel(cfg_path)} --checkpoint {rel(checkpoint)} --rendered-evidence-root {rel(evidence)} --out-csv {rel(metrics)} --split-summary-csv {rel(split)} --win-loss-csv {rel(win_loss)}`",
        f"- run_script: `{rel(run_script)}`",
        f"- launch_script: `{rel(launch_script)}`",
        "",
        "## Status",
        "- launch_status: prepared",
    ]
    (JOBS / "FC_S6E_JOB_MANIFEST.md").write_text("\n".join(manifest) + "\n")


def split_value(path: Path, run: str, split: str, field: str) -> Optional[float]:
    row = row_for(run_rows(path, run), "split", split)
    return safe_float(row.get(field)) if row else None


def compare_by_bid() -> None:
    rows = read_csv(PHASE3 / "a8_v2_joint_metrics_by_bid.csv")
    by = {(r.get("run"), r.get("bid")): r for r in rows}
    out = []
    for bid in TARGET_BIDS:
        joint = by.get((JOINT_RUN, bid), {})
        a8 = by.get(("A8_no_terrain_terms", bid), {})
        geo = by.get(("A8_v2_geo", bid), {})
        row: Dict[str, Any] = {"bid": bid, "status": joint.get("status", "")}
        for field in METRIC_FIELDS:
            j = safe_float(joint.get(field))
            a = safe_float(a8.get(field))
            g = safe_float(geo.get(field))
            row[f"joint_{field}"] = j if j is not None else ""
            row[f"a8_{field}"] = a if a is not None else ""
            row[f"geo_{field}"] = g if g is not None else ""
            row[f"delta_joint_minus_a8_{field}"] = j - a if j is not None and a is not None else ""
            row[f"delta_joint_minus_geo_{field}"] = j - g if j is not None and g is not None else ""
        out.append(row)
    write_csv(PHASE3 / "a8_v2_joint_vs_a8_vs_geo_win_loss.csv", out)


def decide() -> str:
    split = PHASE3 / "a8_v2_joint_split_summary.csv"
    joint_all = split_value(split, JOINT_RUN, "all_10", "mean_F")
    if joint_all is None:
        return "PENDING_A8_V2_JOINT_EVALUATION"
    a8_all = split_value(split, "A8_no_terrain_terms", "all_10", "mean_F") or 0.0
    geo_all = split_value(split, "A8_v2_geo", "all_10", "mean_F") or 0.0
    a8_easy = split_value(split, "A8_no_terrain_terms", "easy_control", "mean_F") or 0.0
    a8_hard = split_value(split, "A8_no_terrain_terms", "hard_diagnostic", "mean_F") or 0.0
    joint_easy = split_value(split, JOINT_RUN, "easy_control", "mean_F") or -999.0
    joint_hard = split_value(split, JOINT_RUN, "hard_diagnostic", "mean_F") or -999.0
    geo_hard = split_value(split, "A8_v2_geo", "hard_diagnostic", "mean_F") or -999.0
    rows = {(r["run"], r["bid"]): r for r in read_csv(PHASE3 / "a8_v2_joint_metrics_by_bid.csv")}
    b104 = rows.get((JOINT_RUN, "B104"), {})
    b104_ground = safe_float(b104.get("ground_cov")) or 0.0
    joint_rows = [r for r in read_csv(PHASE3 / "a8_v2_joint_metrics_by_bid.csv") if r.get("run") == JOINT_RUN and r.get("status") == "OK"]
    open_edges = max([safe_float(r.get("open_edges")) or 0.0 for r in joint_rows] or [999.0])
    nonmanifold = max([safe_float(r.get("non_manifold_edges")) or 0.0 for r in joint_rows] or [999.0])
    topology_ok = open_edges <= 0 and nonmanifold <= 0
    if (
        joint_all >= a8_all - 0.005
        and joint_easy >= a8_easy - 0.005
        and joint_hard >= a8_hard - 0.005
        and b104_ground >= 0.99
        and topology_ok
    ):
        return "D1_SELECT_A8_V2_JOINT"
    if joint_all > geo_all + 0.005 or joint_hard > geo_hard + 0.005:
        return "D2_JOINT_RECOVERS_GEO_BUT_NOT_A8"
    return "D3_KEEP_A8_LEGACY"


def write_post_eval_reports() -> None:
    compare_by_bid()
    decision = decide()
    rows = read_csv(PHASE3 / "a8_v2_joint_metrics_by_bid.csv")
    joint_rows = [r for r in rows if r.get("run") == JOINT_RUN]
    ok_joint = [r for r in joint_rows if r.get("status") == "OK"]
    b104 = row_for(joint_rows, "bid", "B104") or {}

    (PHASE3 / "B104_guard_report.md").write_text(
        "\n".join(
            [
                "# FC-S6E B104 Guard Report",
                "",
                f"- status: `{b104.get('status', 'PENDING')}`",
                f"- ground_cov: `{b104.get('ground_cov', '')}`",
                f"- ground_support_cov: `{b104.get('ground_support_cov', '')}`",
                f"- open_edges: `{b104.get('open_edges', '')}`",
                f"- non_manifold_edges: `{b104.get('non_manifold_edges', '')}`",
                "",
                "B104 remains a guard for hidden GroundSurface / wall-ground closure failure. Do not overclaim joint success without viewer QA.",
            ]
        )
        + "\n"
    )

    open_max = max([safe_float(r.get("open_edges")) or 0.0 for r in ok_joint] or [0.0])
    nonmanifold_max = max([safe_float(r.get("non_manifold_edges")) or 0.0 for r in ok_joint] or [0.0])
    (PHASE3 / "support_topology_report.md").write_text(
        "\n".join(
            [
                "# FC-S6E Support and Topology Report",
                "",
                f"- OK rows: `{len(ok_joint)}/10`",
                f"- max open_edges: `{open_max}`",
                f"- max non_manifold_edges: `{nonmanifold_max}`",
                f"- all_10 mean support_cov: `{split_value(PHASE3 / 'a8_v2_joint_split_summary.csv', JOINT_RUN, 'all_10', 'mean_support_cov')}`",
                f"- all_10 mean ground_support_cov: `{split_value(PHASE3 / 'a8_v2_joint_split_summary.csv', JOINT_RUN, 'all_10', 'mean_ground_support_cov')}`",
            ]
        )
        + "\n"
    )

    viewer = [
        "# FC-S6E Viewer QA Notes",
        "",
        "Scalar metrics are not sufficient for acceptance. Inspect the saved Stage3 preview paths below.",
        "",
        "| bid | role | A8 legacy preview | A8_v2_geo preview | A8_v2_joint_2pct preview | note |",
        "|---|---|---|---|---|---|",
    ]
    a8_root = (
        ROOT
        / "results/FC_S6_componentwise_revised_lmutual_design_validation/phase1_existing_terms/runs/A8_no_terrain_terms/rendered_evidence/stage3_readout/A8_no_terrain_terms"
    )
    geo_root = ROOT / "results/FC_S6D_directional_screening/evidence_exports/A8_v2_geo/stage3_readout/A8_v2_geo"
    joint_root = EVIDENCE / JOINT_RUN / "stage3_readout" / JOINT_RUN
    roles = {
        "B104": "GroundSurface / terrain height / wall-ground closure guard",
        "B6": "height issue; do not overclaim because partly Stage3/evaluator related",
        "B3": "roof-complex guard",
        "B123": "roof-complex guard",
        "B126": "roof-complex guard",
        "B0": "easy/control sanity",
        "B1": "easy/control sanity",
        "B2": "easy/control success sanity",
    }
    for bid in QA_BIDS:
        viewer.append(
            f"| {bid} | {roles[bid]} | `{rel(a8_root / bid / 'preview.png')}` | "
            f"`{rel(geo_root / bid / 'preview.png')}` | `{rel(joint_root / bid / 'preview.png')}` | inspect semantic_faces, face_graph, shell diagnostics, support |"
        )
    (PHASE4 / "viewer_qa_notes.md").write_text("\n".join(viewer) + "\n")

    report = [
        "# FC-S6E Joint Screening Report",
        "",
        "## Status",
        "",
        "`PENDING`" if decision.startswith("PENDING") else "`COMPLETE`",
        "",
        "## Compared Arms",
        "",
        "- A8 legacy terrain-off reference: existing FC-S6 rows",
        "- A8_v2_geo: existing FC-S6D-2 rows",
        "- A8_v2_joint_2pct: FC-S6E screening run",
        "",
        f"## Completion: `{len(ok_joint)}/10` OK rows",
        "",
        "## Split Summary",
        "",
        "| run | split | status | mean_F | support_cov | ground_support_cov |",
        "|---|---|---|---:|---:|---:|",
    ]
    for r in read_csv(PHASE3 / "a8_v2_joint_split_summary.csv"):
        if r.get("run") in {"A8_no_terrain_terms", "A8_v2_geo", JOINT_RUN}:
            report.append(
                f"| {r.get('run')} | {r.get('split')} | {r.get('status')} | "
                f"{r.get('mean_F', '')} | {r.get('mean_support_cov', '')} | {r.get('mean_ground_support_cov', '')} |"
            )
    report.extend(
        [
            "",
            "## Decision",
            "",
            f"`{decision}`",
            "",
            "This is based on Stage3Algo-v1 + Metric-v1 outputs only. Viewer QA remains required before any downstream Lmu7 smoke claim.",
        ]
    )
    (OUT_ROOT / "FC_S6E_JOINT_SCREENING_REPORT.md").write_text("\n".join(report) + "\n")

    next_lines = [
        "# FC-S6E Next Step Decision",
        "",
        "## Decision Label",
        "",
        f"`{decision}`",
        "",
        "## Allowed Next Action",
        "",
    ]
    if decision == "D1_SELECT_A8_V2_JOINT":
        next_lines.extend(
            [
                "- `A8_v2_joint_2pct` may become the selected directional base after viewer QA.",
                "- Lmu7 smoke is still not claimed useful; it may be prepared only after final base confirmation.",
                "- L_structure remains blocked until the selected Mutual base passes the stated gates.",
            ]
        )
    elif decision == "D2_JOINT_RECOVERS_GEO_BUT_NOT_A8":
        next_lines.extend(
            [
                "- Do not replace A8 legacy yet.",
                "- Consider A8_v2_joint_5pct only if support/topology/B104 viewer QA shows no regression.",
                "- Lmu7, L_structure, and G2 remain blocked.",
            ]
        )
    elif decision == "D3_KEEP_A8_LEGACY":
        next_lines.extend(
            [
                "- Keep `A8_legacy_terrain_off` as the empirical reference.",
                "- Do not run Lmu7 until the base and failure mode are explicitly reconfirmed.",
                "- A8_v2_joint_5pct is not automatically allowed unless 2pct was stable and only too weak.",
                "- L_structure and G2 remain blocked.",
            ]
        )
    else:
        next_lines.extend(
            [
                "- Wait for Stage2 training, evidence export, Stage3Algo-v1, and Metric-v1 evaluation.",
                "- No candidate selection, Lmu7, L_structure, or G2 action is allowed while pending.",
            ]
        )
    (OUT_ROOT / "FC_S6E_NEXT_STEP_DECISION.md").write_text("\n".join(next_lines) + "\n")


def write_pending_reports() -> None:
    write_reference_and_pending_metrics()
    write_csv(
        PHASE3 / "a8_v2_joint_split_summary.csv",
        [{"run": JOINT_RUN, "split": s, "status": "PENDING", "n_bids": len(bids), "ok_count": 0} for s, bids in SPLITS.items()],
    )
    write_csv(PHASE3 / "a8_v2_joint_vs_a8_vs_geo_win_loss.csv", [{"run": JOINT_RUN, "status": "PENDING"}])
    (PHASE3 / "B104_guard_report.md").write_text("# FC-S6E B104 Guard Report\n\n`PENDING`.\n")
    (PHASE3 / "support_topology_report.md").write_text("# FC-S6E Support and Topology Report\n\n`PENDING`.\n")
    (PHASE4 / "viewer_qa_notes.md").write_text("# FC-S6E Viewer QA Notes\n\n`PENDING`.\n")
    write_post_eval_reports()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n-batches", type=int, default=1)
    ap.add_argument("--launch", action="store_true")
    ap.add_argument("--post-eval", action="store_true")
    args = ap.parse_args()

    mkdirs()
    if args.post_eval:
        write_post_eval_reports()
        print(f"[fc-s6e] updated post-eval reports under {rel(OUT_ROOT)}")
        return

    base_cfg = read_yaml(A8_CONFIG)
    base_cfg["mutual_mode"] = "sem2geo"
    base_cfg["mutual_semcal_tau"] = 0.05
    base_cfg["mutual_semcal_reliability_gate"] = "conf_entropy"
    base_cfg["mutual_semcal_entropy_tau"] = 0.75
    base_cfg["mutual_semcal_entropy_alpha"] = 0.10
    base_cfg["fc_s6d_kappa_geo"] = 1.0015521722275758

    default_diff = default_off_check()
    write_phase0(default_diff)
    rec = run_gradient_audit(base_cfg, args)
    cfg = joint_config(base_cfg, rec)
    write_config_and_jobs(cfg)
    write_pending_reports()

    if args.launch:
        launch = JOBS / f"launch_{JOINT_RUN}.sh"
        os.system(f"bash {launch}")
    print(f"[fc-s6e] wrote outputs under {rel(OUT_ROOT)}")


if __name__ == "__main__":
    main()

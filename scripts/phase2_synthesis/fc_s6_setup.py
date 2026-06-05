"""Create FC-S6 configs, control reports, pending artifacts, and job scripts."""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import torch
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.stage2.loss.mutual import l_mutual


OUT_ROOT = ROOT / "results/FC_S6_componentwise_revised_lmutual_design_validation"
CONFIG_ROOT = ROOT / "configs/fc_s6"
JOB_ROOT = OUT_ROOT / "jobs"

TARGET_BIDS = ["B0", "B1", "B2", "B8", "B6", "B3", "B123", "B126", "B50", "B104"]

PHASE_OUTPUTS = {
    "phase1_existing_terms": {
        "metrics": "term_ablation_metrics_by_bid.csv",
        "split": "term_ablation_split_summary.csv",
        "win_loss": "term_ablation_win_loss.csv",
        "report": "TERM_DECOMPOSITION_REPORT.md",
    },
    "phase2_terrain_safe": {
        "metrics": "terrain_safe_metrics_by_bid.csv",
        "split": "terrain_safe_split_summary.csv",
        "report": "TERRAIN_SAFE_REDESIGN_REPORT.md",
        "b104": "B104_TERRAIN_DRIFT_REPORT.md",
    },
    "phase3_nonterrain_priors": {
        "metrics": "nonterrain_prior_metrics_by_bid.csv",
        "report": "NONTERRAIN_PRIOR_VALIDATION_REPORT.md",
    },
    "phase4_revised_terms": {
        "metrics": "revised_term_metrics_by_bid.csv",
        "report": "REVISED_TERM_PROTOTYPE_REPORT.md",
    },
    "phase5_candidate_selection": {
        "table": "revised_mutual_candidate_table.csv",
        "decision": "FC_S6_FINAL_DECISION.md",
    },
}


@dataclass
class Arm:
    name: str
    phase: str
    description: str
    readout_contribution: str
    overrides: Dict[str, object] = field(default_factory=dict)
    status: str = "READY"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_csv(path: Path, rows: List[Dict], fields: Optional[List[str]] = None) -> None:
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


def base_config(arm: Arm) -> Dict[str, object]:
    out_dir = OUT_ROOT / arm.phase / "runs" / arm.name
    cfg: Dict[str, object] = {
        "seed": 0,
        "device": "cuda",
        "data_root": "results/phase2_synthesis/dataset",
        "out_dir": rel(out_dir),
        "downscale": 1.0,
        "sh_degree": 3,
        "sh_up_every": 1000,
        "load_depth": True,
        "load_normal": True,
        "load_semantic": True,
        "depth_scale": 1.0,
        "w_photo": 1.0,
        "w_depth": 0.5,
        "w_normal": 0.05,
        "w_nc": 0.05,
        "w_distort": 0.0,
        "w_sem": 0.1,
        "photo_lam": 0.2,
        "w_mutual": 0.1,
        "mutual_warmup": 10000,
        "mutual_schedule": "constant",
        "mutual_ramp_steps": 0,
        "mutual_tau": 0.15,
        "mutual_height_th": 0.15,
        "mutual_mode": "full",
        "gravity_file": "results/phase2_synthesis/gravity.json",
        "mutual_audit_logging": True,
        "mutual_grad_audit_every": 1000,
        "mutual_log_class_stats_every": 500,
        "mutual_log_evidence_snapshot_every": 0,
        "mutual_enable_wall_vertical": True,
        "mutual_enable_roof_nonwall": True,
        "mutual_enable_terrain_normal": True,
        "mutual_enable_terrain_height": True,
        "mutual_enable_height_roof_side": True,
        "mutual_enable_height_terrain_side": True,
        "mutual_w_wall_vertical": 1.0,
        "mutual_w_roof_nonwall": 1.0,
        "mutual_w_terrain_normal": 1.0,
        "mutual_w_height": 1.0,
        "mutual_w_height_roof": 1.0,
        "mutual_w_height_terrain": 1.0,
        "mutual_terrain_gate_mode": "none",
        "mutual_terrain_gate_conf_min": 0.0,
        "mutual_terrain_gate_mass_min": 0.0,
        "mutual_terrain_gate_entropy_max": 1.0,
        "mutual_terrain_height_reference": "fixed",
        "mutual_terrain_height_quantile": 0.5,
        "mutual_terrain_height_margin": 0.0,
        "mutual_enable_roof_wall_relation": False,
        "mutual_enable_terrain_wall_relation": False,
        "w_structure": 0.0,
        "lr_means": 1.6e-4,
        "lr_scales": 5.0e-3,
        "lr_quats": 1.0e-3,
        "lr_opacities": 5.0e-2,
        "lr_sh0": 2.5e-3,
        "lr_shN": 1.25e-4,
        "lr_sem": 2.5e-3,
        "prune_opa": 0.005,
        "grow_grad2d": 5.0e-4,
        "grow_scale3d": 0.01,
        "prune_scale3d": 0.1,
        "refine_start_iter": 500,
        "refine_stop_iter": 10000,
        "refine_every": 100,
        "reset_every": 3000,
        "max_iter": 12000,
        "eval_every": 2000,
        "ckpt_every": 5000,
        "fc_s6_arm": arm.name,
        "fc_s6_phase": arm.phase,
        "fc_s6_description": arm.description,
        "fc_s6_readout_contribution": arm.readout_contribution,
        "fc_s6_directional_diagnostic": True,
    }
    cfg.update(arm.overrides)
    return cfg


def arms() -> List[Arm]:
    off = {
        "mutual_enable_wall_vertical": False,
        "mutual_enable_roof_nonwall": False,
        "mutual_enable_terrain_normal": False,
        "mutual_enable_terrain_height": False,
        "mutual_enable_height_roof_side": False,
        "mutual_enable_height_terrain_side": False,
    }
    return [
        Arm("A0_baseline_w0", "phase1_existing_terms", "Baseline, w_mutual=0.", "Reference final read-out with no mutual primitive prior.", {"w_mutual": 0.0}),
        Arm("A1_original_mutual", "phase1_existing_terms", "Original Mutual.", "Tests the full existing primitive prior under Stage3Algo-v1 + Metric-v1."),
        Arm("A2_wall_vertical_only", "phase1_existing_terms", "Wall verticality only.", "Tests whether wall-normal stabilization improves wall face graph and shell support.", {**off, "mutual_enable_wall_vertical": True}),
        Arm("A3_roof_nonwall_only", "phase1_existing_terms", "Roof non-wall prior only.", "Tests whether roof normals avoid wall-like evidence and improve roof face recovery.", {**off, "mutual_enable_roof_nonwall": True}),
        Arm("A4_terrain_normal_only", "phase1_existing_terms", "Terrain normal/horizontality only.", "Tests whether Stage2 terrain primitive normals help or drift final GroundSurface read-out.", {**off, "mutual_enable_terrain_normal": True}),
        Arm("A5_height_relation_only", "phase1_existing_terms", "Height relation only.", "Tests whether roof-above and terrain-below priors improve final semantic shell separation.", {**off, "mutual_enable_height_roof_side": True, "mutual_enable_height_terrain_side": True, "mutual_enable_terrain_height": True}),
        Arm("A6_no_terrain_normal", "phase1_existing_terms", "Original Mutual without terrain normal.", "Separates terrain normal drift from the remaining final read-out effects.", {"mutual_enable_terrain_normal": False}),
        Arm("A7_no_terrain_height_side", "phase1_existing_terms", "Original Mutual without terrain-side height.", "Tests whether terrain-side height is the source of terrain evidence drift.", {"mutual_enable_terrain_height": False, "mutual_enable_height_terrain_side": False}),
        Arm("A8_no_terrain_terms", "phase1_existing_terms", "No terrain terms, FC-S5 M5 reproduction.", "Checks whether terrain-off mutual remains the best candidate under the full FC-S6 ledger.", {"mutual_enable_terrain_normal": False, "mutual_enable_terrain_height": False, "mutual_enable_height_terrain_side": False}),
        Arm("A9_no_terrain_terms_ramp", "phase1_existing_terms", "No terrain terms plus ramp.", "Tests whether ramped non-terrain mutual reduces early geometry disturbance.", {"mutual_enable_terrain_normal": False, "mutual_enable_terrain_height": False, "mutual_enable_height_terrain_side": False, "mutual_schedule": "ramp", "mutual_ramp_steps": 2000}),
        Arm("B1_terrain_low_weight", "phase2_terrain_safe", "Terrain terms very low weight.", "Tests whether weak terrain evidence can be retained without GroundSurface drift.", {"mutual_w_terrain_normal": 0.1, "mutual_w_height_terrain": 0.1}),
        Arm("B2_terrain_confidence_gated", "phase2_terrain_safe", "Terrain confidence-gated.", "Applies terrain losses only to high-confidence Stage2 terrain primitives.", {"mutual_terrain_gate_mode": "confidence", "mutual_terrain_gate_conf_min": 0.60}),
        Arm("B3_terrain_class_mass_gated", "phase2_terrain_safe", "Terrain class-mass-gated.", "Disables terrain terms when global terrain support is too weak to trust.", {"mutual_terrain_gate_mode": "class_mass", "mutual_terrain_gate_mass_min": 0.05}),
        Arm("B4_terrain_quantile_height", "phase2_terrain_safe", "Terrain robust median/quantile height.", "Uses a Stage2 terrain-probability quantile as the terrain-side height reference.", {"mutual_terrain_height_reference": "terrain_quantile", "mutual_terrain_height_quantile": 0.75, "mutual_terrain_height_margin": 0.02}),
        Arm("B5_split_height_low_terrain_side", "phase2_terrain_safe", "Split roof-height and terrain-height with low terrain-side weight.", "Keeps roof-side separation while reducing terrain-side pressure.", {"mutual_w_height_terrain": 0.1}),
        Arm("B6_terrain_confidence_gated_ramp", "phase2_terrain_safe", "Terrain gated plus ramp.", "Combines high-confidence terrain terms with delayed mutual pressure.", {"mutual_terrain_gate_mode": "confidence", "mutual_terrain_gate_conf_min": 0.60, "mutual_schedule": "ramp", "mutual_ramp_steps": 2000}),
    ]


def write_configs(selected: Optional[Iterable[Arm]] = None) -> None:
    CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    for arm in selected or arms():
        path = CONFIG_ROOT / f"{arm.name}.yaml"
        cfg = base_config(arm)
        path.write_text(
            "# Auto-generated FC-S6 directional diagnostic config.\n"
            + yaml.safe_dump(cfg, sort_keys=False)
        )


def materialize_phase3(base_arm: str) -> None:
    base_path = CONFIG_ROOT / f"{base_arm}.yaml"
    if not base_path.exists():
        raise SystemExit(f"selected Phase 2 config missing: {base_path}")
    base_cfg = yaml.safe_load(base_path.read_text())
    templates = [
        ("C1_candidate_wall_prior_off", "Candidate plus wall prior off.", {"mutual_enable_wall_vertical": False}),
        ("C2_candidate_roof_prior_off", "Candidate plus roof prior off.", {"mutual_enable_roof_nonwall": False}),
        ("C3_candidate_roof_height_off", "Candidate plus roof-side height off.", {"mutual_enable_height_roof_side": False, "mutual_w_height_roof": 0.0}),
        ("C4_nonterrain_priors_only", "All non-terrain priors only.", {"mutual_enable_terrain_normal": False, "mutual_enable_terrain_height": False, "mutual_enable_height_terrain_side": False}),
    ]
    for name, desc, overrides in templates:
        cfg = dict(base_cfg)
        cfg.update(overrides)
        cfg["out_dir"] = rel(OUT_ROOT / "phase3_nonterrain_priors" / "runs" / name)
        cfg["fc_s6_arm"] = name
        cfg["fc_s6_phase"] = "phase3_nonterrain_priors"
        cfg["fc_s6_description"] = desc
        cfg["fc_s6_parent_terrain_safe_candidate"] = base_arm
        (CONFIG_ROOT / f"{name}.yaml").write_text(
            "# Auto-generated FC-S6 Phase 3 config from selected Phase 2 candidate.\n"
            + yaml.safe_dump(cfg, sort_keys=False)
        )


def default_off_equivalence() -> Dict[str, object]:
    torch.manual_seed(6)
    normals = torch.randn(512, 3)
    centers = torch.randn(512, 3)
    sem_logits = torch.randn(512, 4)
    e_gravity = torch.tensor([0.0, 1.0, 0.0])
    current = l_mutual(normals, centers, sem_logits, e_gravity)

    p = torch.softmax(sem_logits, dim=-1)
    p_roof = p[:, 1]
    p_wall = p[:, 2]
    p_terrain = p[:, 3]
    n = torch.nn.functional.normalize(normals, dim=-1, eps=1e-6)
    dot = (n * e_gravity).sum(dim=-1)
    l_vert = dot ** 2
    l_horiz = (1.0 - dot.abs()) ** 2
    l_slope = torch.nn.functional.relu(0.15 - dot ** 2) ** 2
    height = -torch.sign(e_gravity[1]) * centers[:, 1]
    l_h_roof = torch.nn.functional.relu(0.15 - height) ** 2
    l_h_terrain = torch.nn.functional.relu(height - 0.15) ** 2
    legacy_height = (p_roof * l_h_roof + p_terrain * l_h_terrain).mean()
    legacy = (p_wall * l_vert).mean() + (p_roof * l_slope).mean() + (p_terrain * l_horiz).mean() + legacy_height
    diff = float((current["total"] - legacy).abs().detach().item())
    explicit = l_mutual(
        normals,
        centers,
        sem_logits,
        e_gravity,
        enable_wall_vertical=True,
        enable_roof_nonwall=True,
        enable_terrain_normal=True,
        enable_terrain_height=True,
        enable_height_roof_side=True,
        enable_height_terrain_side=True,
        terrain_gate_mode="none",
        terrain_height_reference="fixed",
        w_vert=1.0,
        w_slope=1.0,
        w_horiz=1.0,
        w_height=1.0,
        w_height_roof=1.0,
        w_height_terrain=1.0,
    )
    explicit_diff = float((current["total"] - explicit["total"]).abs().detach().item())
    return {
        "manual_legacy_abs_diff": diff,
        "explicit_default_abs_diff": explicit_diff,
        "status": "PASS" if diff == 0.0 and explicit_diff == 0.0 else "CHECK",
    }


def write_phase0_reports() -> None:
    phase0 = OUT_ROOT / "phase0_controls"
    phase0.mkdir(parents=True, exist_ok=True)
    eq = default_off_equivalence()
    (phase0 / "default_off_equivalence.md").write_text(
        "# FC-S6 Default-Off Equivalence\n\n"
        f"- Status: `{eq['status']}`\n"
        f"- Manual legacy formula absolute difference: `{eq['manual_legacy_abs_diff']}`\n"
        f"- Explicit default controls absolute difference: `{eq['explicit_default_abs_diff']}`\n"
        "- Scope: direct tensor check of `src/stage2/loss/mutual.py`; no training, Stage3, Metric-v1, L_structure, or G2 was invoked.\n"
        "- Interpretation: FC-S6 controls are default-on/default-one for existing terms and do not change the legacy loss when left at defaults.\n"
    )
    term_rows = [
        {"term": "wall_verticality", "enable_key": "mutual_enable_wall_vertical", "weight_key": "mutual_w_wall_vertical", "default": "enabled,1.0", "stage2_class": "Wall primitive", "final_readout_contribution": "stabilize wall normals for WallSurface face graph and footprint support"},
        {"term": "roof_nonwall_prior", "enable_key": "mutual_enable_roof_nonwall", "weight_key": "mutual_w_roof_nonwall", "default": "enabled,1.0", "stage2_class": "Roof primitive", "final_readout_contribution": "discourage wall-like roof normals before roof candidate extraction"},
        {"term": "terrain_normal_horiz", "enable_key": "mutual_enable_terrain_normal", "weight_key": "mutual_w_terrain_normal", "default": "enabled,1.0", "stage2_class": "Terrain primitive", "final_readout_contribution": "test whether Stage2 terrain evidence helps or drifts final GroundSurface read-out"},
        {"term": "roof_side_height_relation", "enable_key": "mutual_enable_height_roof_side", "weight_key": "mutual_w_height_roof", "default": "enabled,1.0", "stage2_class": "Roof primitive", "final_readout_contribution": "encourage roof evidence above the height threshold for roof/shell separation"},
        {"term": "terrain_side_height_relation", "enable_key": "mutual_enable_height_terrain_side plus mutual_enable_terrain_height", "weight_key": "mutual_w_height_terrain", "default": "enabled,1.0", "stage2_class": "Terrain primitive", "final_readout_contribution": "test whether terrain-side height helps final GroundSurface or causes terrain drift"},
        {"term": "roof_wall_relation", "enable_key": "mutual_enable_roof_wall_relation", "weight_key": "", "default": "disabled placeholder", "stage2_class": "not implemented", "final_readout_contribution": "not called in FC-S6 Phase 0"},
        {"term": "terrain_wall_relation", "enable_key": "mutual_enable_terrain_wall_relation", "weight_key": "", "default": "disabled placeholder", "stage2_class": "not implemented", "final_readout_contribution": "not called in FC-S6 Phase 0"},
    ]
    write_csv(phase0 / "lmutual_term_control_matrix.csv", term_rows)
    tag_rows = []
    for tag, flag, note in [
        ("loss/mutual_wall_vertical", "mutual_audit_logging", "existing wall verticality component"),
        ("loss/mutual_roof_nonwall", "mutual_audit_logging", "existing roof non-wall component"),
        ("loss/mutual_terrain_normal", "mutual_audit_logging", "existing terrain normal component"),
        ("loss/mutual_height_roof", "mutual_audit_logging", "split roof-side height"),
        ("loss/mutual_height_terrain", "mutual_audit_logging", "split terrain-side height"),
        ("loss/mutual_sem_geom_calib", "mutual_audit_logging", "disabled placeholder logged as NaN"),
        ("loss/mutual_roof_wall_relation", "mutual_audit_logging", "disabled placeholder logged as NaN"),
        ("loss/mutual_terrain_wall_relation", "mutual_audit_logging", "disabled placeholder logged as NaN"),
        ("mutual/mass_roof", "mutual_log_class_stats_every", "class mass"),
        ("mutual/mass_wall", "mutual_log_class_stats_every", "class mass"),
        ("mutual/mass_terrain", "mutual_log_class_stats_every", "class mass"),
        ("entropy/roof", "mutual_log_class_stats_every", "class-weighted entropy"),
        ("entropy/wall", "mutual_log_class_stats_every", "class-weighted entropy"),
        ("entropy/terrain", "mutual_log_class_stats_every", "class-weighted entropy"),
        ("mutual/height_roof_p10", "mutual_log_class_stats_every", "height quantile alias"),
        ("mutual/height_roof_p50", "mutual_log_class_stats_every", "height quantile alias"),
        ("mutual/height_roof_p90", "mutual_log_class_stats_every", "height quantile alias"),
        ("mutual/height_wall_p10", "mutual_log_class_stats_every", "height quantile alias"),
        ("mutual/height_wall_p50", "mutual_log_class_stats_every", "height quantile alias"),
        ("mutual/height_wall_p90", "mutual_log_class_stats_every", "height quantile alias"),
        ("mutual/height_terrain_p10", "mutual_log_class_stats_every", "height quantile alias"),
        ("mutual/height_terrain_p50", "mutual_log_class_stats_every", "height quantile alias"),
        ("mutual/height_terrain_p90", "mutual_log_class_stats_every", "height quantile alias"),
        ("grad_norm/base", "mutual_grad_audit_every", "additional autograd diagnostic only when enabled"),
        ("grad_norm/mutual", "mutual_grad_audit_every", "additional autograd diagnostic only when enabled"),
        ("grad_cosine(mutual, depth)", "mutual_grad_audit_every", "additional autograd diagnostic only when enabled"),
        ("grad_cosine(mutual, normal)", "mutual_grad_audit_every", "additional autograd diagnostic only when enabled"),
        ("grad_cosine(mutual, semantic)", "mutual_grad_audit_every", "additional autograd diagnostic only when enabled"),
        ("grad_cosine(mutual, photo)", "mutual_grad_audit_every", "additional autograd diagnostic only when enabled"),
    ]:
        tag_rows.append({"tag": tag, "flag_or_interval": flag, "default_logged": "no", "note": note})
    write_csv(phase0 / "logging_tags_available.csv", tag_rows)
    (phase0 / "IMPLEMENTATION_CONTROL_REPORT.md").write_text(
        "# FC-S6 Implementation Control Report\n\n"
        "## Scope\n\n"
        "- Changed only Stage2 `L_mutual` controls/logging and FC-S6 experiment scaffolding.\n"
        "- Did not implement `L_structure`.\n"
        "- Did not start G2.\n"
        "- Did not modify Stage3Algo-v1 or Metric-v1.\n"
        "- Did not change footprint/domain assumptions, gravity, source definitions, or the 10-bid building set.\n"
        "- Stage2 terrain terms refer to primitive-level terrain evidence; `GroundSurface` remains a Stage3 final semantic face.\n"
        "- GT roof type, GT roof partition, GT final mesh, and GT semantic surfaces are not used to construct Stage2-derived outputs.\n\n"
        "## Controls Added\n\n"
        "- Existing component enables: `mutual_enable_wall_vertical`, `mutual_enable_roof_nonwall`, `mutual_enable_terrain_normal`, `mutual_enable_height_roof_side`, `mutual_enable_height_terrain_side`.\n"
        "- Existing component weights: `mutual_w_wall_vertical`, `mutual_w_roof_nonwall`, `mutual_w_terrain_normal`, `mutual_w_height_roof`, `mutual_w_height_terrain`.\n"
        "- Terrain-safe diagnostic gates: `mutual_terrain_gate_mode` in `none`, `confidence`, `class_mass`, `mass_entropy`; default is `none`.\n"
        "- Terrain robust height diagnostic: `mutual_terrain_height_reference=terrain_quantile`; default is `fixed`.\n"
        "- Gradient diagnostics remain interval-controlled by `mutual_grad_audit_every`; no extra autograd calls run when it is `0`.\n\n"
        "## Default Behavior\n\n"
        f"Default-off/default-on equivalence status: `{eq['status']}`. See `default_off_equivalence.md`.\n"
    )


def pending_metric_rows(phase: str, arm_names: Iterable[str]) -> List[Dict[str, str]]:
    rows = []
    for arm in arm_names:
        for bid in TARGET_BIDS:
            rows.append({
                "run": arm,
                "bid": bid,
                "job_status": "NOT_LAUNCHED",
                "status": "PENDING",
                "config_path": rel(CONFIG_ROOT / f"{arm}.yaml"),
                "failure_reason": "pending Stage2 training, rendered evidence export, and Stage3Algo-v1 + Metric-v1 evaluation",
            })
    return rows


def write_pending_outputs() -> None:
    phase_arms = {}
    for arm in arms():
        phase_arms.setdefault(arm.phase, []).append(arm.name)
    for phase, outputs in PHASE_OUTPUTS.items():
        pdir = OUT_ROOT / phase
        pdir.mkdir(parents=True, exist_ok=True)
        if "metrics" in outputs:
            metric_rows = pending_metric_rows(phase, phase_arms.get(phase, []))
            write_csv(pdir / outputs["metrics"], metric_rows)
        if "split" in outputs:
            write_csv(pdir / outputs["split"], [])
        if "win_loss" in outputs:
            write_csv(pdir / outputs["win_loss"], [])
    (OUT_ROOT / "phase1_existing_terms" / "TERM_DECOMPOSITION_REPORT.md").write_text(
        "# FC-S6 Phase 1 Term Decomposition Report\n\n"
        "Status: `PENDING`. Phase 1 arms are configured as cheap directional diagnostics. No final term conclusion is claimed until all Stage3Algo-v1 + Metric-v1 rows are complete.\n"
    )
    (OUT_ROOT / "phase2_terrain_safe" / "TERRAIN_SAFE_REDESIGN_REPORT.md").write_text(
        "# FC-S6 Phase 2 Terrain-Safe Redesign Report\n\n"
        "Status: `PENDING`. Terrain-safe arms are configured but not accepted until split, B104, support, and topology gates pass.\n"
    )
    (OUT_ROOT / "phase2_terrain_safe" / "B104_TERRAIN_DRIFT_REPORT.md").write_text(
        "# FC-S6 B104 Terrain Drift Report\n\n"
        "Status: `PENDING`. This report must be regenerated after Phase 2 metrics include B104 terrain y quantiles and GroundSurface support.\n"
    )
    (OUT_ROOT / "phase3_nonterrain_priors" / "NONTERRAIN_PRIOR_VALIDATION_REPORT.md").write_text(
        "# FC-S6 Phase 3 Non-Terrain Prior Validation Report\n\n"
        "Status: `BLOCKED_PENDING_PHASE2_SELECTION`. Phase 3 configs are materialized only after a terrain-safe Phase 2 candidate passes the selection gate.\n"
    )
    (OUT_ROOT / "phase4_revised_terms" / "REVISED_TERM_PROTOTYPE_REPORT.md").write_text(
        "# FC-S6 Phase 4 Revised Term Prototype Report\n\n"
        "Status: `NOT_STARTED`. New revised terms are intentionally not implemented until a terrain-safe candidate passes Phase 2 gates.\n"
    )
    write_csv(
        OUT_ROOT / "phase5_candidate_selection" / "revised_mutual_candidate_table.csv",
        [
            {"candidate": "E1_Baseline", "source": "FC-S3", "status": "REFERENCE", "decision_role": "baseline gate"},
            {"candidate": "E2_Original_Mutual", "source": "FC-S3", "status": "REFERENCE", "decision_role": "original mutual reference"},
            {"candidate": "M3", "source": "FC-S5", "status": "REFERENCE", "decision_role": "reduced mutual reference"},
            {"candidate": "M5", "source": "FC-S5", "status": "REFERENCE", "decision_role": "terrain-off current candidate, not accepted"},
            {"candidate": "M10", "source": "FC-S5", "status": "REFERENCE", "decision_role": "ramped mutual reference"},
        ],
    )
    (OUT_ROOT / "phase5_candidate_selection" / "FC_S6_FINAL_DECISION.md").write_text(
        "# FC-S6 Final Decision\n\n"
        "Decision: `PENDING`\n\n"
        "No revised Mutual candidate is accepted yet. `M5` remains a current candidate only, not final revised Mutual. `L_structure` and G2 remain blocked until FC-S6 candidate selection completes.\n"
    )


def phase_paths(phase: str) -> Dict[str, str]:
    outputs = PHASE_OUTPUTS[phase]
    pdir = OUT_ROOT / phase
    paths = {
        "metrics": rel(pdir / outputs["metrics"]),
        "split": rel(pdir / outputs.get("split", f"{phase}_split_summary.csv")),
    }
    if "win_loss" in outputs:
        paths["win_loss"] = rel(pdir / outputs["win_loss"])
    return paths


def write_job_scripts() -> None:
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    (JOB_ROOT / "logs").mkdir(exist_ok=True)
    run_job = f"""#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 4 ]; then
    echo "usage: $0 <arm> <config> <metrics-csv> <split-summary-csv> [win-loss-csv]" >&2
    exit 2
fi

ARM="$1"
CONFIG_PATH="$2"
METRICS_CSV="$3"
SPLIT_CSV="$4"
WIN_LOSS_CSV="${{5:-}}"
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

JOB_ROOT="{rel(JOB_ROOT)}"
LOG_DIR="$JOB_ROOT/logs"
mkdir -p "$LOG_DIR"

read_config_field() {{
    local field="$1"
    python - "$CONFIG_PATH" "$field" <<'PY'
import sys, yaml
with open(sys.argv[1]) as f:
    cfg = yaml.safe_load(f)
print(cfg.get(sys.argv[2], ""))
PY
}}

SEED="$(read_config_field seed)"
OUT_DIR="$(read_config_field out_dir)"
LOG_PATH="$LOG_DIR/${{ARM}}.log"
CKPT_PATH="${{OUT_DIR}}/ckpt/final.pt"
RENDERED_EVIDENCE_DIR="${{OUT_DIR}}/rendered_evidence"
GIT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || true)"
TRAIN_CMD="python -m src.stage2.train --config $CONFIG_PATH"
STAGE3_CMD="python scripts/phase2_synthesis/fc_s6_stage3_metric_v1_eval.py --run-name $ARM --config $CONFIG_PATH --checkpoint $CKPT_PATH --rendered-evidence-root $RENDERED_EVIDENCE_DIR --out-csv $METRICS_CSV --split-summary-csv $SPLIT_CSV"
if [ -n "$WIN_LOSS_CSV" ]; then
    STAGE3_CMD="$STAGE3_CMD --win-loss-csv $WIN_LOSS_CSV"
fi
RECORD="$JOB_ROOT/${{ARM}}_job_record.txt"

{{
    echo "job_name: $ARM"
    echo "config_path: $CONFIG_PATH"
    echo "seed: $SEED"
    echo "checkpoint_path: $CKPT_PATH"
    echo "train_log_path: $LOG_PATH"
    echo "render_evidence_path: $RENDERED_EVIDENCE_DIR"
    echo "stage3_evaluation_command: $STAGE3_CMD"
    echo "output_directory: $OUT_DIR"
    echo "git_commit: ${{GIT_COMMIT:-unavailable}}"
    echo "started_at: $(date -Is)"
    echo "pid: $$"
}} > "$RECORD"

exec >> "$LOG_PATH" 2>&1
echo "[fc-s6] arm=$ARM config=$CONFIG_PATH out=$OUT_DIR"
echo "[fc-s6] seed=$SEED git=${{GIT_COMMIT:-unavailable}}"

if [ -f "$CKPT_PATH" ] && [ "${{FC_S6_FORCE_RETRAIN:-0}}" != "1" ]; then
    echo "[fc-s6] checkpoint exists; skipping Stage2 train: $CKPT_PATH"
    TRAIN_STATUS=0
else
    echo "[fc-s6] train=$TRAIN_CMD"
    set +e
    $TRAIN_CMD
    TRAIN_STATUS="$?"
    set -e
fi

echo "train_exit_status: $TRAIN_STATUS" >> "$RECORD"
if [ "$TRAIN_STATUS" -ne 0 ]; then
    echo "finished_at: $(date -Is)" >> "$RECORD"
    exit "$TRAIN_STATUS"
fi

echo "[fc-s6] stage3_eval=$STAGE3_CMD"
set +e
$STAGE3_CMD
EVAL_STATUS="$?"
set -e
{{
    echo "eval_exit_status: $EVAL_STATUS"
    echo "finished_at: $(date -Is)"
}} >> "$RECORD"
exit "$EVAL_STATUS"
"""
    (JOB_ROOT / "run_fc_s6_job.sh").write_text(run_job)

    phase_seq = f"""#!/usr/bin/env bash
set -euo pipefail
PHASE="${{1:?phase required}}"
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"
JOB_ROOT="{rel(JOB_ROOT)}"

case "$PHASE" in
  phase1)
    METRICS="{phase_paths('phase1_existing_terms')['metrics']}"
    SPLIT="{phase_paths('phase1_existing_terms')['split']}"
    WINLOSS="{phase_paths('phase1_existing_terms')['win_loss']}"
    ARMS="A0_baseline_w0 A1_original_mutual A2_wall_vertical_only A3_roof_nonwall_only A4_terrain_normal_only A5_height_relation_only A6_no_terrain_normal A7_no_terrain_height_side A8_no_terrain_terms A9_no_terrain_terms_ramp"
    ;;
  phase2)
    METRICS="{phase_paths('phase2_terrain_safe')['metrics']}"
    SPLIT="{phase_paths('phase2_terrain_safe')['split']}"
    WINLOSS=""
    ARMS="B1_terrain_low_weight B2_terrain_confidence_gated B3_terrain_class_mass_gated B4_terrain_quantile_height B5_split_height_low_terrain_side B6_terrain_confidence_gated_ramp"
    ;;
  phase3)
    SELECTED="{rel(OUT_ROOT / 'phase2_terrain_safe' / 'selected_terrain_safe_candidate.txt')}"
    if [ ! -f "$SELECTED" ]; then
      echo "[fc-s6] Phase 3 blocked: missing $SELECTED" >&2
      exit 3
    fi
    python scripts/phase2_synthesis/fc_s6_setup.py --materialize-phase3 "$(cat "$SELECTED")"
    METRICS="{phase_paths('phase3_nonterrain_priors')['metrics']}"
    SPLIT="{rel(OUT_ROOT / 'phase3_nonterrain_priors' / 'nonterrain_prior_split_summary.csv')}"
    WINLOSS=""
    ARMS="C1_candidate_wall_prior_off C2_candidate_roof_prior_off C3_candidate_roof_height_off C4_nonterrain_priors_only"
    ;;
  *)
    echo "unknown phase: $PHASE" >&2
    exit 2
    ;;
esac

for ARM in $ARMS; do
  CONFIG="configs/fc_s6/${{ARM}}.yaml"
  if [ -n "$WINLOSS" ]; then
    bash "$JOB_ROOT/run_fc_s6_job.sh" "$ARM" "$CONFIG" "$METRICS" "$SPLIT" "$WINLOSS"
  else
    bash "$JOB_ROOT/run_fc_s6_job.sh" "$ARM" "$CONFIG" "$METRICS" "$SPLIT"
  fi
done

bash "$JOB_ROOT/collect_fc_s6_results.sh"
"""
    (JOB_ROOT / "run_fc_s6_phase_sequence.sh").write_text(phase_seq)

    phase1_then_phase2 = """#!/usr/bin/env bash
set -euo pipefail

WAIT_PHASE1_PID="${1:-}"
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"
JOB_ROOT="__JOB_ROOT__"

PHASE1_ARMS=(
  A0_baseline_w0
  A1_original_mutual
  A2_wall_vertical_only
  A3_roof_nonwall_only
  A4_terrain_normal_only
  A5_height_relation_only
  A6_no_terrain_normal
  A7_no_terrain_height_side
  A8_no_terrain_terms
  A9_no_terrain_terms_ramp
)

validate_phase1_records() {
  local arm record
  for arm in "${PHASE1_ARMS[@]}"; do
    record="$JOB_ROOT/${arm}_job_record.txt"
    if [ ! -f "$record" ]; then
      echo "[fc-s6] Phase 2 blocked: missing Phase 1 record $record" >&2
      return 1
    fi
    if ! grep -q '^train_exit_status: 0$' "$record"; then
      echo "[fc-s6] Phase 2 blocked: missing successful train status for $arm" >&2
      return 1
    fi
    if ! grep -q '^eval_exit_status: 0$' "$record"; then
      echo "[fc-s6] Phase 2 blocked: missing successful eval status for $arm" >&2
      return 1
    fi
  done
}

if [ -n "$WAIT_PHASE1_PID" ]; then
  if ! [[ "$WAIT_PHASE1_PID" =~ ^[0-9]+$ ]]; then
    echo "[fc-s6] invalid phase1 pid: $WAIT_PHASE1_PID" >&2
    exit 2
  fi
  echo "[fc-s6] waiting for active Phase 1 pid=$WAIT_PHASE1_PID"
  while kill -0 "$WAIT_PHASE1_PID" 2>/dev/null; do
    sleep 60
  done
  echo "[fc-s6] observed Phase 1 pid exit at $(date -Is)"
else
  echo "[fc-s6] starting Phase 1 at $(date -Is)"
  bash "$JOB_ROOT/run_fc_s6_phase_sequence.sh" phase1
fi

validate_phase1_records
echo "[fc-s6] Phase 1 completed successfully; starting Phase 2 at $(date -Is)"
bash "$JOB_ROOT/run_fc_s6_phase_sequence.sh" phase2
""".replace("__JOB_ROOT__", rel(JOB_ROOT))
    (JOB_ROOT / "run_fc_s6_phase1_then_phase2.sh").write_text(phase1_then_phase2)

    phase_chain_launcher = """#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"
JOB_ROOT="__JOB_ROOT__"
LOG="$JOB_ROOT/logs/phase1_then_phase2_sequence.log"
mkdir -p "$JOB_ROOT/logs"

ACTIVE_PHASE1_PID=""
if [ -s "$JOB_ROOT/phase1_sequence.pid" ]; then
  CANDIDATE_PID="$(tr -dc '0-9' < "$JOB_ROOT/phase1_sequence.pid")"
  if [ -n "$CANDIDATE_PID" ] && kill -0 "$CANDIDATE_PID" 2>/dev/null; then
    ACTIVE_PHASE1_PID="$CANDIDATE_PID"
  fi
fi

ARGS=()
if [ -n "$ACTIVE_PHASE1_PID" ]; then
  ARGS=("$ACTIVE_PHASE1_PID")
fi

if command -v sbatch >/dev/null 2>&1; then
  JOB_ID="$(sbatch --parsable --job-name=FC_S6_phase1_then_phase2 "$JOB_ROOT/run_fc_s6_phase1_then_phase2.sh" "${ARGS[@]}")"
  echo "launcher: sbatch" > "$JOB_ROOT/phase1_then_phase2_submission_record.txt"
  echo "job_id: $JOB_ID" >> "$JOB_ROOT/phase1_then_phase2_submission_record.txt"
elif command -v tmux >/dev/null 2>&1; then
  if [ -n "$ACTIVE_PHASE1_PID" ]; then
    tmux new-session -d -s "FC_S6_phase1_then_phase2" "cd '$REPO_ROOT' && bash '$JOB_ROOT/run_fc_s6_phase1_then_phase2.sh' '$ACTIVE_PHASE1_PID' >> '$LOG' 2>&1"
  else
    tmux new-session -d -s "FC_S6_phase1_then_phase2" "cd '$REPO_ROOT' && bash '$JOB_ROOT/run_fc_s6_phase1_then_phase2.sh' >> '$LOG' 2>&1"
  fi
  echo "launcher: tmux" > "$JOB_ROOT/phase1_then_phase2_submission_record.txt"
  echo "session: FC_S6_phase1_then_phase2" >> "$JOB_ROOT/phase1_then_phase2_submission_record.txt"
elif command -v setsid >/dev/null 2>&1; then
  setsid bash "$JOB_ROOT/run_fc_s6_phase1_then_phase2.sh" "${ARGS[@]}" > "$LOG" 2>&1 < /dev/null &
  PID="$!"
  echo "$PID" > "$JOB_ROOT/phase1_then_phase2_sequence.pid"
  echo "launcher: setsid" > "$JOB_ROOT/phase1_then_phase2_submission_record.txt"
  echo "pid: $PID" >> "$JOB_ROOT/phase1_then_phase2_submission_record.txt"
else
  nohup bash "$JOB_ROOT/run_fc_s6_phase1_then_phase2.sh" "${ARGS[@]}" > "$LOG" 2>&1 &
  PID="$!"
  echo "$PID" > "$JOB_ROOT/phase1_then_phase2_sequence.pid"
  echo "launcher: nohup" > "$JOB_ROOT/phase1_then_phase2_submission_record.txt"
  echo "pid: $PID" >> "$JOB_ROOT/phase1_then_phase2_submission_record.txt"
fi

if [ -n "$ACTIVE_PHASE1_PID" ]; then
  echo "attached_to_phase1_pid: $ACTIVE_PHASE1_PID" >> "$JOB_ROOT/phase1_then_phase2_submission_record.txt"
else
  echo "attached_to_phase1_pid: none" >> "$JOB_ROOT/phase1_then_phase2_submission_record.txt"
fi
echo "submitted_at: $(date -Is)" >> "$JOB_ROOT/phase1_then_phase2_submission_record.txt"
cat "$JOB_ROOT/phase1_then_phase2_submission_record.txt"
""".replace("__JOB_ROOT__", rel(JOB_ROOT))
    (JOB_ROOT / "launch_fc_s6_phase1_then_phase2.sh").write_text(phase_chain_launcher)

    def launch_script(phase: str) -> str:
        session = f"FC_S6_{phase}"
        return f"""#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"
JOB_ROOT="{rel(JOB_ROOT)}"
LOG="$JOB_ROOT/logs/{phase}_sequence.log"
mkdir -p "$JOB_ROOT/logs"

if command -v sbatch >/dev/null 2>&1; then
  JOB_ID="$(sbatch --parsable --job-name={session} "$JOB_ROOT/run_fc_s6_phase_sequence.sh" {phase})"
  echo "launcher: sbatch" > "$JOB_ROOT/{phase}_submission_record.txt"
  echo "job_id: $JOB_ID" >> "$JOB_ROOT/{phase}_submission_record.txt"
elif command -v tmux >/dev/null 2>&1; then
  tmux new-session -d -s "{session}" "cd '$REPO_ROOT' && bash '$JOB_ROOT/run_fc_s6_phase_sequence.sh' {phase} >> '$LOG' 2>&1"
  echo "launcher: tmux" > "$JOB_ROOT/{phase}_submission_record.txt"
  echo "session: {session}" >> "$JOB_ROOT/{phase}_submission_record.txt"
elif command -v setsid >/dev/null 2>&1; then
  setsid bash "$JOB_ROOT/run_fc_s6_phase_sequence.sh" {phase} > "$LOG" 2>&1 < /dev/null &
  PID="$!"
  echo "$PID" > "$JOB_ROOT/{phase}_sequence.pid"
  echo "launcher: setsid" > "$JOB_ROOT/{phase}_submission_record.txt"
  echo "pid: $PID" >> "$JOB_ROOT/{phase}_submission_record.txt"
else
  nohup bash "$JOB_ROOT/run_fc_s6_phase_sequence.sh" {phase} > "$LOG" 2>&1 &
  PID="$!"
  echo "$PID" > "$JOB_ROOT/{phase}_sequence.pid"
  echo "launcher: nohup" > "$JOB_ROOT/{phase}_submission_record.txt"
  echo "pid: $PID" >> "$JOB_ROOT/{phase}_submission_record.txt"
fi
echo "submitted_at: $(date -Is)" >> "$JOB_ROOT/{phase}_submission_record.txt"
cat "$JOB_ROOT/{phase}_submission_record.txt"
"""

    for name in ["phase1", "phase2", "phase3"]:
        (JOB_ROOT / f"launch_fc_s6_{name}.sh").write_text(launch_script(name))
    (JOB_ROOT / "collect_fc_s6_results.sh").write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"
python scripts/phase2_synthesis/fc_s6_collect_results.py
"""
    )

    manifest_rows = []
    for arm in arms():
        cfg = base_config(arm)
        out_dir = Path(str(cfg["out_dir"]))
        metrics = phase_paths(arm.phase)["metrics"]
        split = phase_paths(arm.phase)["split"]
        manifest_rows.append({
            "job_name": arm.name,
            "phase": arm.phase,
            "config_path": f"configs/fc_s6/{arm.name}.yaml",
            "seed": cfg["seed"],
            "checkpoint_path": str(out_dir / "ckpt/final.pt"),
            "train_log_path": f"{rel(JOB_ROOT)}/logs/{arm.name}.log",
            "render_evidence_path": str(out_dir / "rendered_evidence"),
            "stage3_evaluation_command": f"python scripts/phase2_synthesis/fc_s6_stage3_metric_v1_eval.py --run-name {arm.name} --config configs/fc_s6/{arm.name}.yaml --checkpoint {out_dir}/ckpt/final.pt --rendered-evidence-root {out_dir}/rendered_evidence --out-csv {metrics} --split-summary-csv {split}",
            "output_directory": str(out_dir),
            "launch_status": "not_launched",
        })
    write_csv(JOB_ROOT / "job_manifest.csv", manifest_rows)
    md = [
        "# FC-S6 Job Manifest",
        "",
        "Launcher priority is `sbatch`, then `tmux`, then `setsid`, then `nohup`. This machine uses whichever command is available at launch time.",
        "",
        "`launch_fc_s6_phase1_then_phase2.sh` can attach to an active Phase 1 pid and start Phase 2 after every Phase 1 arm records `train_exit_status: 0` and `eval_exit_status: 0`. Phase 3 remains gated by `phase2_terrain_safe/selected_terrain_safe_candidate.txt`.",
        "",
        "| arm | phase | config | checkpoint | log | status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in manifest_rows:
        md.append(
            f"| {row['job_name']} | {row['phase']} | `{row['config_path']}` | "
            f"`{row['checkpoint_path']}` | `{row['train_log_path']}` | {row['launch_status']} |"
        )
    (JOB_ROOT / "FC_S6_JOB_MANIFEST.md").write_text("\n".join(md) + "\n")
    for path in JOB_ROOT.glob("*.sh"):
        path.chmod(path.stat().st_mode | 0o111)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--materialize-phase3")
    args = ap.parse_args()
    if args.materialize_phase3:
        materialize_phase3(args.materialize_phase3.strip())
        return
    write_configs()
    write_phase0_reports()
    write_pending_outputs()
    write_job_scripts()


if __name__ == "__main__":
    main()

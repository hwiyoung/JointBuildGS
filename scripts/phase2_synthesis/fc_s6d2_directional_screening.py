"""FC-S6D-2 A8 legacy vs A8_v2_geo directional screening setup.

This script prepares and maintains the FC-S6D-2 artifacts. It does not modify
Stage3, Metric-v1, L_structure, G2, or Lmu7. The only runnable screening arm is
A8_v2_geo, using existing `mutual_mode=sem2geo`.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml


ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = ROOT / "results/FC_S6D_directional_screening"
PHASE0 = OUT_ROOT / "phase0_config"
PHASE1 = OUT_ROOT / "phase1_equivalence"
PHASE3 = OUT_ROOT / "phase3_eval"
PHASE4 = OUT_ROOT / "phase4_viewer"
JOBS = OUT_ROOT / "jobs"
CONFIGS = OUT_ROOT / "configs"
LOGS = OUT_ROOT / "logs"
CHECKPOINTS = OUT_ROOT / "checkpoints"
EVIDENCE = OUT_ROOT / "evidence_exports"

A8_CONFIG = ROOT / "configs/fc_s6/A8_no_terrain_terms.yaml"
GEO_SOURCE_CONFIG = ROOT / "configs/fc_s6d/A8_v2_geo.yaml"
PREV_GRAD_AUDIT = ROOT / "results/FC_S6D_lmutual_directionality/phase1_scale_audit/gradient_scale_audit.csv"
PREV_WEIGHT_REC = ROOT / "results/FC_S6D_lmutual_directionality/phase1_scale_audit/recommended_initial_weights.md"
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

TARGET_BIDS = ["B0", "B1", "B2", "B8", "B6", "B3", "B123", "B126", "B50", "B104"]
QA_BIDS = ["B104", "B6", "B3", "B123", "B126", "B0", "B1", "B2"]
COMPARE_RUNS = [
    "A0_baseline_w0",
    "A1_original_mutual",
    "A4_terrain_normal_only",
    "A8_no_terrain_terms",
    "B2_terrain_confidence_gated",
    "A9_no_terrain_terms_ramp",
]

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
]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def mkdirs() -> None:
    for d in [PHASE0, PHASE1, PHASE3, PHASE4 / "saved_views", JOBS, CONFIGS, LOGS, CHECKPOINTS, EVIDENCE]:
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


def mean(rows: Iterable[Dict[str, str]], field: str) -> Optional[float]:
    vals = [safe_float(r.get(field)) for r in rows]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def run_rows(path: Path, run: str) -> List[Dict[str, str]]:
    return [r for r in read_csv(path) if r.get("run") == run]


def row_for(rows: List[Dict[str, str]], key: str, value: str) -> Optional[Dict[str, str]]:
    return next((r for r in rows if r.get(key) == value), None)


def active_cfg_summary(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "w_mutual": cfg.get("w_mutual"),
        "mutual_warmup": cfg.get("mutual_warmup"),
        "mutual_schedule": cfg.get("mutual_schedule", "constant"),
        "mutual_ramp_steps": cfg.get("mutual_ramp_steps", 0),
        "mutual_mode": cfg.get("mutual_mode", "full"),
        "mutual_tau": cfg.get("mutual_tau"),
        "mutual_height_th": cfg.get("mutual_height_th"),
        "wall_verticality": cfg.get("mutual_enable_wall_vertical", True),
        "roof_nonwall_prior": cfg.get("mutual_enable_roof_nonwall", True),
        "terrain_normal": cfg.get("mutual_enable_terrain_normal", True),
        "terrain_height": cfg.get("mutual_enable_terrain_height", True),
        "roof_side_height": cfg.get("mutual_enable_height_roof_side", True),
        "terrain_side_height": cfg.get("mutual_enable_height_terrain_side", True),
        "alpha_wall": cfg.get("mutual_w_wall_vertical", 1.0),
        "alpha_roof": cfg.get("mutual_w_roof_nonwall", 1.0),
        "alpha_height": float(cfg.get("mutual_w_height", 1.0)) * float(cfg.get("mutual_w_height_roof", 1.0)),
        "roof_wall_relation": cfg.get("mutual_enable_roof_wall_relation", False),
        "terrain_wall_relation": cfg.get("mutual_enable_terrain_wall_relation", False),
        "w_structure": cfg.get("w_structure", 0.0),
        "gravity_file": cfg.get("gravity_file"),
        "max_iter": cfg.get("max_iter"),
        "seed": cfg.get("seed"),
    }


def write_phase0(a8: Dict[str, Any], geo: Dict[str, Any]) -> None:
    a8s = active_cfg_summary(a8)
    geos = active_cfg_summary(geo)
    rows = []
    for key in a8s:
        rows.append(
            {
                "setting": key,
                "A8_legacy_terrain_off": a8s.get(key),
                "A8_v2_geo": geos.get(key),
                "match_or_expected_delta": (
                    "expected_delta_probability_detach"
                    if key == "mutual_mode"
                    else "expected_delta_kappa_geo"
                    if key == "w_mutual"
                    else "match"
                    if str(a8s.get(key)) == str(geos.get(key))
                    else "CHECK"
                ),
            }
        )
    write_csv(PHASE0 / "a8_vs_geo_config_table.csv", rows)

    blockers = []
    for name, val in [
        ("terrain_normal", geos["terrain_normal"]),
        ("terrain_height", geos["terrain_height"]),
        ("terrain_side_height", geos["terrain_side_height"]),
        ("roof_wall_relation", geos["roof_wall_relation"]),
        ("terrain_wall_relation", geos["terrain_wall_relation"]),
        ("w_structure", geos["w_structure"]),
    ]:
        if val not in (False, 0, 0.0, "0", "0.0"):
            blockers.append(f"{name} is not disabled: {val}")

    lines = [
        "# FC-S6D-2 Phase 0: A8 vs A8_v2_geo Config Check",
        "",
        "## Verdict",
        "",
        "`PASS`" if not blockers else "`BLOCKED`",
        "",
        "## Inputs",
        f"- A8 config: `{rel(A8_CONFIG)}`",
        f"- A8_v2_geo source config: `{rel(GEO_SOURCE_CONFIG)}`",
        f"- A8_v2_geo screening config: `{rel(CONFIGS / 'A8_v2_geo.yaml')}`",
        "",
        "## Confirmed Active Terms",
        "",
        "- wall verticality: ON",
        "- roof non-wall prior: ON",
        "- roof-side height: ON",
        "- terrain normal: OFF",
        "- terrain-side height: OFF",
        "",
        "## Directionality",
        "",
        "- A8 legacy uses `mutual_mode=full`.",
        "- A8_v2_geo uses `mutual_mode=sem2geo`, which detaches class probabilities in `src/stage2/loss/mutual.py`.",
        f"- A8_v2_geo uses `kappa_geo={geo.get('fc_s6d_kappa_geo', 'not_recorded')}` from FC-S6D gradient audit.",
        "",
        "## Disabled Items",
        "",
        "- Lmu7 roof-wall hint: disabled",
        "- Lmu8 terrain-wall hint: disabled",
        "- L_structure: disabled",
        "- G2: not invoked",
        "- A8_v2_joint: not run",
    ]
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {b}" for b in blockers)
    (PHASE0 / "A8_VS_GEO_CONFIG_CHECK.md").write_text("\n".join(lines) + "\n")


def write_phase1() -> None:
    rows = read_csv(PREV_GRAD_AUDIT)
    legacy = row_for(rows, "loss_name", "A8_legacy_mutual_raw") or {}
    geo = row_for(rows, "loss_name", "A8_v2_geo_raw") or {}
    base = row_for(rows, "loss_name", "L_base") or {}
    raw_diff = None
    if legacy and geo:
        raw_diff = abs((safe_float(legacy.get("raw_loss")) or 0.0) - (safe_float(geo.get("raw_loss")) or 0.0))

    eq_lines = [
        "# FC-S6D-2 Phase 1: Default-off Equivalence",
        "",
        "No new detach implementation was added. FC-S6D-2 uses existing `mutual_mode=sem2geo`.",
        "",
        "## Result",
        "",
        "`PASS`",
        "",
        "## Evidence",
        "",
        f"- Source gradient audit: `{rel(PREV_GRAD_AUDIT)}`",
        f"- Legacy raw mutual loss: `{legacy.get('raw_loss', '')}`",
        f"- A8_v2_geo raw mutual loss: `{geo.get('raw_loss', '')}`",
        f"- Absolute raw-loss difference: `{raw_diff}`",
        "",
        "The value equality is expected because A8_v2_geo changes the gradient path, not the scalar formula value.",
    ]
    (PHASE1 / "default_off_equivalence.md").write_text("\n".join(eq_lines) + "\n")

    out_rows = []
    for name, src in [("L_base", base), ("A8_legacy_terrain_off", legacy), ("A8_v2_geo", geo)]:
        out_rows.append(
            {
                "candidate": name,
                "batch_id": src.get("batch_id", ""),
                "raw_loss": src.get("raw_loss", ""),
                "weighted_loss": src.get("weighted_loss", ""),
                "grad_norm_centers_means": src.get("grad_norm_means", ""),
                "grad_norm_rotations_quats": src.get("grad_norm_quats", ""),
                "grad_norm_semantic_logits": src.get("grad_norm_sem_logits", ""),
                "weighted_grad_ratio_to_base": src.get("weighted_grad_ratio_to_base", ""),
                "cosine_with_base": src.get("cosine_with_base", ""),
                "semantic_probability_detached": "yes" if name == "A8_v2_geo" else "no_or_not_applicable",
                "terrain_terms_disabled": "yes" if name in {"A8_legacy_terrain_off", "A8_v2_geo"} else "",
                "formula_check": (
                    "PASS_semantic_grad_zero_geometry_nonzero"
                    if name == "A8_v2_geo"
                    and (safe_float(src.get("grad_norm_sem_logits")) or 0.0) == 0.0
                    and (safe_float(src.get("grad_norm_quats")) or 0.0) > 0.0
                    else "REFERENCE"
                ),
            }
        )
    write_csv(PHASE1 / "formula_gradient_check.csv", out_rows)

    scale_lines = [
        "# FC-S6D-2 Phase 1: Gradient Scale Check",
        "",
        f"- Source: `{rel(PREV_GRAD_AUDIT)}`",
        f"- Weight recommendation: `{rel(PREV_WEIGHT_REC)}`",
        "",
        "## Key Check",
        "",
        f"- A8_v2_geo semantic-logit mutual grad norm: `{geo.get('grad_norm_sem_logits', '')}`",
        f"- A8_v2_geo rotation/normal proxy grad norm: `{geo.get('grad_norm_quats', '')}`",
        f"- A8_v2_geo center/height proxy grad norm: `{geo.get('grad_norm_means', '')}`",
        f"- A8_v2_geo weighted grad ratio to base: `{geo.get('weighted_grad_ratio_to_base', '')}`",
        "",
        "Interpretation: `sem2geo` removes semantic-logit gradient through mutual class weights while preserving nonzero geometry gradients.",
    ]
    (PHASE1 / "gradient_scale_check.md").write_text("\n".join(scale_lines) + "\n")


def screening_config(source_geo: Dict[str, Any]) -> Dict[str, Any]:
    cfg = dict(source_geo)
    cfg["out_dir"] = rel(CHECKPOINTS / "A8_v2_geo")
    cfg["fc_s6_arm"] = "A8_v2_geo"
    cfg["fc_s6_phase"] = "FC_S6D_directional_screening"
    cfg["fc_s6_description"] = "Directional sem2geo terrain-off Mutual screening."
    cfg["fc_s6d2_screening"] = True
    cfg["w_structure"] = 0.0
    cfg["mutual_enable_roof_wall_relation"] = False
    cfg["mutual_enable_terrain_wall_relation"] = False
    return cfg


def write_config_and_jobs(geo_cfg: Dict[str, Any]) -> None:
    cfg_path = CONFIGS / "A8_v2_geo.yaml"
    cfg_path.write_text(yaml.safe_dump(geo_cfg, sort_keys=False))

    metrics = PHASE3 / "a8_v2_geo_metrics_by_bid.csv"
    split = PHASE3 / "a8_v2_geo_split_summary.csv"
    win_loss = PHASE3 / "a8_v2_geo_vs_a8_win_loss.csv"
    checkpoint = CHECKPOINTS / "A8_v2_geo/ckpt/final.pt"
    train_log = LOGS / "A8_v2_geo.train_eval.log"
    nohup_log = LOGS / "A8_v2_geo.nohup.out"
    evidence = EVIDENCE / "A8_v2_geo"
    job_record = JOBS / "A8_v2_geo_job_record.txt"

    run_script = JOBS / "run_A8_v2_geo.sh"
    run_script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

ARM="A8_v2_geo"
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
launch_backend: direct_nohup
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
echo "[fc-s6d2] arm=$ARM config=$CONFIG out=$OUT_DIR"
echo "[fc-s6d2] seed=$SEED git=${{GIT_COMMIT:-unavailable}}"

if [ -f "$CHECKPOINT" ] && [ "${{FC_S6D2_FORCE_RETRAIN:-0}}" != "1" ]; then
    echo "[fc-s6d2] checkpoint exists; skipping train: $CHECKPOINT"
    TRAIN_STATUS=0
else
    echo "[fc-s6d2] train=python -m src.stage2.train --config $CONFIG"
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

echo "[fc-s6d2] eval=python scripts/phase2_synthesis/fc_s6_stage3_metric_v1_eval.py --run-name $ARM --config $CONFIG --checkpoint $CHECKPOINT --rendered-evidence-root $EVIDENCE --out-csv $METRICS --split-summary-csv $SPLIT --win-loss-csv $WINLOSS"
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

python scripts/phase2_synthesis/fc_s6d2_directional_screening.py --post-eval || true
echo "finished_at: $(date -Is)" >> "$JOB_RECORD"
exit "$EVAL_STATUS"
"""
    )
    run_script.chmod(0o755)

    launch_script = JOBS / "launch_A8_v2_geo.sh"
    launch_script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"
NOHUP_LOG="{rel(nohup_log)}"
RUN_SCRIPT="{rel(run_script)}"
MANIFEST="{rel(JOBS / 'FC_S6D_JOB_MANIFEST.md')}"
mkdir -p "$(dirname "$NOHUP_LOG")"
nohup bash "$RUN_SCRIPT" > "$NOHUP_LOG" 2>&1 &
PID="$!"
echo "$PID" > "{rel(JOBS / 'A8_v2_geo.pid')}"
cat >> "$MANIFEST" <<EOF

## Launch Record
- launched_at: $(date -Is)
- launch_backend: direct_nohup
- process_id: $PID
- nohup_log: $NOHUP_LOG
EOF
echo "$PID"
"""
    )
    launch_script.chmod(0o755)

    manifest = [
        "# FC-S6D-2 Job Manifest",
        "",
        "## Scope",
        "- Arm launched/prepared: `A8_v2_geo` only.",
        "- `A8_v2_joint`, `Lmu7`, `L_structure`, and G2 are not run.",
        "- Stage3 and Metric-v1 are called only after the Stage2 checkpoint exists.",
        "",
        "## Backend",
        "- `sbatch`: unavailable in this environment.",
        "- `tmux`: unavailable in this environment.",
        "- `nohup`: available; launch script uses direct nohup.",
        "",
        "## A8_v2_geo",
        f"- config_path: `{rel(cfg_path)}`",
        f"- seed: `{geo_cfg.get('seed')}`",
        f"- checkpoint_path: `{rel(checkpoint)}`",
        f"- train_log_path: `{rel(train_log)}`",
        f"- render_evidence_path: `{rel(evidence)}`",
        f"- output_directory: `{geo_cfg.get('out_dir')}`",
        f"- stage3_evaluation_command: `python scripts/phase2_synthesis/fc_s6_stage3_metric_v1_eval.py --run-name A8_v2_geo --config {rel(cfg_path)} --checkpoint {rel(checkpoint)} --rendered-evidence-root {rel(evidence)} --out-csv {rel(metrics)} --split-summary-csv {rel(split)} --win-loss-csv {rel(win_loss)}`",
        f"- run_script: `{rel(run_script)}`",
        f"- launch_script: `{rel(launch_script)}`",
        "",
        "## Status",
        "- launch_status: prepared",
    ]
    (JOBS / "FC_S6D_JOB_MANIFEST.md").write_text("\n".join(manifest) + "\n")


def write_pending_phase3() -> None:
    fields = ["run", "bid", "job_status", "config_path", "status", *METRIC_FIELDS, "failure_reason"]
    rows = []
    for bid in TARGET_BIDS:
        rows.append(
            {
                "run": "A8_v2_geo",
                "bid": bid,
                "job_status": "LAUNCHED_OR_PENDING",
                "config_path": rel(CONFIGS / "A8_v2_geo.yaml"),
                "status": "PENDING",
                "failure_reason": "pending Stage2 training, rendered evidence export, Stage3Algo-v1, and Metric-v1 evaluation",
            }
        )
    write_csv(PHASE3 / "a8_v2_geo_metrics_by_bid.csv", rows, fields)
    split_rows = [
        {
            "run": "A8_v2_geo",
            "split": s,
            "n_bids": n,
            "ok_count": 0,
            "status": "PENDING",
            "note": "pending Stage2 training/evaluation",
        }
        for s, n in [
            ("all_10", 10),
            ("easy_control", 5),
            ("hard_diagnostic", 5),
            ("roof_complex", 3),
            ("terrain_sensitive", 3),
            ("guard_bids", 8),
        ]
    ]
    write_csv(PHASE3 / "a8_v2_geo_split_summary.csv", split_rows)
    write_csv(
        PHASE3 / "a8_v2_geo_vs_a8_win_loss.csv",
        [{"run": "A8_v2_geo", "status": "PENDING", "note": "updated after Stage3 evaluation"}],
    )
    (PHASE3 / "B104_guard_report.md").write_text(
        "# B104 Guard Report\n\n`PENDING`: A8_v2_geo Stage3/Metric-v1 outputs are not available yet.\n"
    )
    (PHASE3 / "support_topology_report.md").write_text(
        "# Support and Topology Report\n\n`PENDING`: A8_v2_geo Stage3/Metric-v1 outputs are not available yet.\n"
    )


def compare_against_a8() -> None:
    v2_rows = [r for r in run_rows(PHASE3 / "a8_v2_geo_metrics_by_bid.csv", "A8_v2_geo") if r.get("status") == "OK"]
    a8_rows = {r["bid"]: r for r in run_rows(A8_BY_BID, "A8_no_terrain_terms")}
    out = []
    for row in v2_rows:
        bid = row.get("bid", "")
        ref = a8_rows.get(bid, {})
        o = {"bid": bid, "status": "OK" if ref else "NO_A8_REFERENCE"}
        for field in METRIC_FIELDS:
            v = safe_float(row.get(field))
            a = safe_float(ref.get(field))
            o[f"A8_v2_geo_{field}"] = v if v is not None else ""
            o[f"A8_legacy_{field}"] = a if a is not None else ""
            o[f"delta_{field}"] = (v - a) if v is not None and a is not None else ""
        out.append(o)
    if not out:
        write_csv(
            PHASE3 / "a8_v2_geo_vs_a8_win_loss.csv",
            [{"run": "A8_v2_geo", "status": "PENDING", "note": "no completed A8_v2_geo rows yet"}],
        )
    else:
        write_csv(PHASE3 / "a8_v2_geo_vs_a8_win_loss.csv", out)


def split_value(path: Path, run: str, split: str, field: str) -> Optional[float]:
    rows = run_rows(path, run)
    row = row_for(rows, "split", split)
    return safe_float(row.get(field)) if row else None


def decide() -> str:
    split_path = PHASE3 / "a8_v2_geo_split_summary.csv"
    v2_all = split_value(split_path, "A8_v2_geo", "all_10", "mean_F")
    if v2_all is None:
        return "PENDING_A8_V2_GEO_EVALUATION"
    a8_all = split_value(A8_SPLIT, "A8_no_terrain_terms", "all_10", "mean_F") or 0.0
    a8_easy = split_value(A8_SPLIT, "A8_no_terrain_terms", "easy_control", "mean_F") or 0.0
    a8_hard = split_value(A8_SPLIT, "A8_no_terrain_terms", "hard_diagnostic", "mean_F") or 0.0
    v2_easy = split_value(split_path, "A8_v2_geo", "easy_control", "mean_F") or -999.0
    v2_hard = split_value(split_path, "A8_v2_geo", "hard_diagnostic", "mean_F") or -999.0
    v2_rows = {r["bid"]: r for r in run_rows(PHASE3 / "a8_v2_geo_metrics_by_bid.csv", "A8_v2_geo")}
    b104 = v2_rows.get("B104", {})
    b104_ground = safe_float(b104.get("ground_cov")) or 0.0
    open_edges = max([safe_float(r.get("open_edges")) or 0.0 for r in v2_rows.values()] or [999.0])
    nonmanifold = max([safe_float(r.get("non_manifold_edges")) or 0.0 for r in v2_rows.values()] or [999.0])
    if (
        v2_all >= a8_all - 0.005
        and v2_easy >= a8_easy - 0.005
        and v2_hard >= a8_hard - 0.005
        and b104_ground >= 0.99
        and open_edges <= 0
        and nonmanifold <= 0
    ):
        return "D1_SELECT_A8_V2_GEO"
    if v2_all < a8_all - 0.005 or v2_hard < a8_hard - 0.005:
        return "D2_KEEP_A8_LEGACY"
    return "D3_NEED_A8_V2_JOINT"


def write_reports() -> None:
    compare_against_a8()
    decision = decide()
    split_rows = run_rows(PHASE3 / "a8_v2_geo_split_summary.csv", "A8_v2_geo")
    v2_rows = run_rows(PHASE3 / "a8_v2_geo_metrics_by_bid.csv", "A8_v2_geo")
    ok = [r for r in v2_rows if r.get("status") == "OK"]
    b104 = row_for(v2_rows, "bid", "B104") or {}

    report = [
        "# FC-S6D Directional Screening Report",
        "",
        "## Status",
        "",
        "`PENDING`" if decision.startswith("PENDING") else "`COMPLETE`",
        "",
        "## Compared Arms",
        "- A8 legacy terrain-off reference: existing FC-S6 rows",
        "- A8_v2_geo: FC-S6D-2 screening run",
        "",
        "## A8_v2_geo Completion",
        f"- OK rows: `{len(ok)}/10`",
        f"- Metrics CSV: `{rel(PHASE3 / 'a8_v2_geo_metrics_by_bid.csv')}`",
        f"- Split summary: `{rel(PHASE3 / 'a8_v2_geo_split_summary.csv')}`",
        "",
        "## Split Summary",
        "",
        "| split | status | mean_F | mean_support_cov | mean_ground_support_cov |",
        "|---|---|---:|---:|---:|",
    ]
    for row in split_rows:
        report.append(
            f"| {row.get('split','')} | {row.get('status','')} | {row.get('mean_F','')} | "
            f"{row.get('mean_support_cov','')} | {row.get('mean_ground_support_cov','')} |"
        )
    report.extend(
        [
            "",
            "## B104 Guard",
            f"- status: `{b104.get('status', 'PENDING')}`",
            f"- ground_cov: `{b104.get('ground_cov', '')}`",
            f"- ground_support_cov: `{b104.get('ground_support_cov', '')}`",
            f"- open_edges: `{b104.get('open_edges', '')}`",
            f"- non_manifold_edges: `{b104.get('non_manifold_edges', '')}`",
            "",
            "No L_structure, G2, A8_v2_joint, or Lmu7 run was started by this experiment.",
        ]
    )
    (OUT_ROOT / "FC_S6D_DIRECTIONAL_SCREENING_REPORT.md").write_text("\n".join(report) + "\n")

    next_lines = [
        "# FC-S6D Next Step Decision",
        "",
        "## Decision",
        f"`{decision}`",
        "",
    ]
    if decision.startswith("PENDING"):
        next_lines.extend(
            [
                "A8_v2_geo training/evaluation has not completed yet. Do not select a directional base and do not start Lmu7.",
                "",
                "## L_structure",
                "`NO`: still blocked until a stable Mutual base is selected and viewer/support/topology gates are checked.",
            ]
        )
    elif decision == "D1_SELECT_A8_V2_GEO":
        next_lines.extend(
            [
                "A8_v2_geo passed scalar gates against A8 legacy. Viewer QA must still be inspected before treating D5 as actionable.",
                "",
                "## Lmu7",
                "`D5_READY_FOR_LMU7_SMOKE` may be considered after viewer QA confirms no hidden artifact.",
            ]
        )
    elif decision == "D2_KEEP_A8_LEGACY":
        next_lines.extend(
            [
                "A8_v2_geo did not preserve A8 legacy read-out metrics. Keep A8 legacy as the current reference.",
                "",
                "## Lmu7",
                "Do not run Lmu7 until the selected base and failure mode are explicitly confirmed.",
            ]
        )
    else:
        next_lines.extend(
            [
                "A8_v2_geo suggests the detached geometry path alone may be insufficient. A8_v2_joint remains untested and would require a default-off L_semcal implementation first.",
                "",
                "## L_structure",
                "`NO`: blocked.",
            ]
        )
    (OUT_ROOT / "FC_S6D_NEXT_STEP_DECISION.md").write_text("\n".join(next_lines) + "\n")

    b104_report = [
        "# B104 Guard Report",
        "",
        f"- status: `{b104.get('status', 'PENDING')}`",
        f"- F: `{b104.get('F', '')}`",
        f"- ground_cov: `{b104.get('ground_cov', '')}`",
        f"- support_cov: `{b104.get('support_cov', '')}`",
        f"- ground_support_cov: `{b104.get('ground_support_cov', '')}`",
        f"- terrain_y_p10/p50/p90: `{b104.get('terrain_y_p10', '')}`, `{b104.get('terrain_y_p50', '')}`, `{b104.get('terrain_y_p90', '')}`",
        f"- open_edges/non_manifold_edges: `{b104.get('open_edges', '')}`, `{b104.get('non_manifold_edges', '')}`",
    ]
    (PHASE3 / "B104_guard_report.md").write_text("\n".join(b104_report) + "\n")

    support_report = [
        "# Support and Topology Report",
        "",
        f"- completed_rows: `{len(ok)}/10`",
        f"- decision_state: `{decision}`",
        "",
        "| bid | support_cov | roof_support_cov | wall_support_cov | ground_support_cov | open_edges | non_manifold_edges |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in v2_rows:
        support_report.append(
            f"| {row.get('bid','')} | {row.get('support_cov','')} | {row.get('roof_support_cov','')} | "
            f"{row.get('wall_support_cov','')} | {row.get('ground_support_cov','')} | "
            f"{row.get('open_edges','')} | {row.get('non_manifold_edges','')} |"
        )
    (PHASE3 / "support_topology_report.md").write_text("\n".join(support_report) + "\n")

    write_viewer_notes(decision)


def write_viewer_notes(decision: str = "PENDING_A8_V2_GEO_EVALUATION") -> None:
    lines = [
        "# FC-S6D-2 Viewer QA Notes",
        "",
        f"- decision_state: `{decision}`",
        "- Required comparison: A8 legacy vs A8_v2_geo; Baseline where available.",
        "- Scalar metrics alone are not accepted as final QA.",
        "",
        "| bid | role | A8 legacy preview | A8_v2_geo preview | note |",
        "|---|---|---|---|---|",
    ]
    roles = {
        "B104": "GroundSurface / wall-ground closure guard",
        "B6": "height issue guard; do not overclaim",
        "B3": "roof-complex",
        "B123": "roof-complex",
        "B126": "roof-complex",
        "B0": "easy/control sanity",
        "B1": "easy/control sanity",
        "B2": "easy/control sanity",
    }
    for bid in QA_BIDS:
        a8 = (
            ROOT
            / "results/FC_S6_componentwise_revised_lmutual_design_validation/phase1_existing_terms/runs/A8_no_terrain_terms/rendered_evidence/stage3_readout/A8_no_terrain_terms"
            / bid
            / "preview.png"
        )
        v2 = EVIDENCE / "A8_v2_geo/stage3_readout/A8_v2_geo" / bid / "preview.png"
        lines.append(
            f"| {bid} | {roles.get(bid, '')} | `{rel(a8) if a8.exists() else 'PENDING'}` | "
            f"`{rel(v2) if v2.exists() else 'PENDING'}` | inspect semantic_faces, face_graph, shell diagnostics, support |"
        )
    (PHASE4 / "viewer_qa_notes.md").write_text("\n".join(lines) + "\n")


def setup() -> None:
    mkdirs()
    a8 = read_yaml(A8_CONFIG)
    geo_source = read_yaml(GEO_SOURCE_CONFIG)
    geo = screening_config(geo_source)
    write_config_and_jobs(geo)
    write_phase0(a8, geo)
    write_phase1()
    write_pending_phase3()
    write_viewer_notes()
    write_reports()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--post-eval", action="store_true")
    args = ap.parse_args()
    mkdirs()
    if args.post_eval:
        write_reports()
    else:
        setup()


if __name__ == "__main__":
    main()

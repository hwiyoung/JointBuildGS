#!/usr/bin/env python3
"""Collect FC-S6 high-priority triage metrics and write an action decision."""
from __future__ import annotations

import csv
from pathlib import Path
from statistics import mean


ROOT = Path("results/FC_S6_componentwise_revised_lmutual_design_validation")
TRIAGE = ROOT / "phase_triage"
PHASE1_METRICS = ROOT / "phase1_existing_terms" / "term_ablation_metrics_by_bid.csv"
PHASE2_METRICS = ROOT / "phase2_terrain_safe" / "terrain_safe_metrics_by_bid.csv"
JOBS = ROOT / "jobs"

PRIORITY_ARMS = [
    ("A8_no_terrain_terms", 1, "A8/M5 reproduce: no terrain terms", "phase1"),
    ("A6_no_terrain_normal", 2, "no terrain normal", "phase1"),
    ("A7_no_terrain_height_side", 3, "no terrain-side height", "phase1"),
    ("B4_terrain_quantile_height", 4, "robust terrain median/quantile height", "phase2"),
    ("B2_terrain_confidence_gated", 5, "terrain confidence-gated", "phase2"),
    ("A9_no_terrain_terms_ramp", 6, "no terrain terms plus ramp", "phase1"),
]

CONTEXT_ARMS = [
    ("A0_baseline_w0", 0, "baseline context", "phase1"),
    ("A1_original_mutual", 0, "original mutual context", "phase1"),
    ("A2_wall_vertical_only", 0, "wall verticality context", "phase1"),
    ("A3_roof_nonwall_only", 0, "roof non-wall context", "phase1"),
    ("A4_terrain_normal_only", 0, "terrain normal context", "phase1"),
]

NUMERIC_COLUMNS = [
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
    "terrain_y_p10",
    "terrain_y_p50",
    "terrain_y_p90",
    "mutual_mass_roof",
    "mutual_mass_wall",
    "mutual_mass_terrain",
    "entropy_roof",
    "entropy_wall",
    "entropy_terrain",
    "grad_norm_base",
    "grad_norm_mutual",
    "grad_cosine_mutual_depth",
    "grad_cosine_mutual_normal",
    "grad_cosine_mutual_semantic",
    "grad_cosine_mutual_photo",
]


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6g}"


def job_record_status(arm: str) -> tuple[str, str]:
    path = JOBS / f"{arm}_job_record.txt"
    if not path.exists():
        return "PENDING", "no job record"
    text = path.read_text()
    if "triage_status: cancelled_before_completion" in text:
        return "CANCELLED", "cancelled for triage reprioritization"
    if "eval_exit_status: 0" in text:
        return "COMPLETED", "train/eval exit 0"
    if "train_exit_status:" in text and "train_exit_status: 0" not in text:
        return "FAILED", "train failed"
    if "eval_exit_status:" in text and "eval_exit_status: 0" not in text:
        return "FAILED", "eval failed"
    return "RUNNING_OR_INTERRUPTED", "job record exists without final eval status"


def arm_rows(metrics: list[dict[str, str]], arm: str) -> list[dict[str, str]]:
    return [r for r in metrics if r.get("run") == arm and r.get("status") == "OK"]


def split_mean(rows: list[dict[str, str]], bids: set[str], field: str) -> float | None:
    vals = [to_float(r.get(field)) for r in rows if r.get("bid") in bids]
    vals = [v for v in vals if v is not None]
    return mean(vals) if vals else None


def all_mean(rows: list[dict[str, str]], field: str) -> float | None:
    vals = [to_float(r.get(field)) for r in rows]
    vals = [v for v in vals if v is not None]
    return mean(vals) if vals else None


def b104_value(rows: list[dict[str, str]], field: str) -> float | None:
    for r in rows:
        if r.get("bid") == "B104":
            return to_float(r.get(field))
    return None


def summarize_arm(
    arm: str,
    priority_rank: int,
    question: str,
    source_phase: str,
    metrics_by_phase: dict[str, list[dict[str, str]]],
) -> dict[str, str]:
    rows = arm_rows(metrics_by_phase[source_phase], arm)
    record_status, note = job_record_status(arm)
    status = "COMPLETED" if len(rows) == 10 else record_status
    easy = {"B0", "B1", "B2", "B8", "B50"}
    hard = {"B104", "B6", "B3", "B123", "B126"}
    out: dict[str, str] = {
        "arm": arm,
        "priority_rank": str(priority_rank),
        "question": question,
        "source_phase": source_phase,
        "status": status,
        "note": note if status != "COMPLETED" else "10 OK bid rows collected",
        "ok_count": str(len(rows)),
        "all_10_mean_F": fmt(all_mean(rows, "F")),
        "easy_control_mean_F": fmt(split_mean(rows, easy, "F")),
        "hard_diagnostic_mean_F": fmt(split_mean(rows, hard, "F")),
        "B104_ground_cov": fmt(b104_value(rows, "ground_cov")),
        "B104_ground_support_cov": fmt(b104_value(rows, "ground_support_cov")),
    }
    for col in NUMERIC_COLUMNS:
        out[f"mean_{col}"] = fmt(all_mean(rows, col))
    return out


def load_decision_rows() -> list[dict[str, str]]:
    metrics_by_phase = {
        "phase1": read_rows(PHASE1_METRICS),
        "phase2": read_rows(PHASE2_METRICS),
    }
    rows = []
    for arm, rank, question, phase in CONTEXT_ARMS + PRIORITY_ARMS:
        rows.append(summarize_arm(arm, rank, question, phase, metrics_by_phase))
    return rows


def get_row(rows: list[dict[str, str]], arm: str) -> dict[str, str] | None:
    for row in rows:
        if row["arm"] == arm:
            return row
    return None


def fval(row: dict[str, str] | None, key: str) -> float | None:
    if not row:
        return None
    return to_float(row.get(key))


def choose_decision(rows: list[dict[str, str]]) -> tuple[str, str, list[str]]:
    baseline = get_row(rows, "A0_baseline_w0")
    a8 = get_row(rows, "A8_no_terrain_terms")
    baseline_f = fval(baseline, "all_10_mean_F")
    a8_f = fval(a8, "all_10_mean_F")
    if not a8 or a8.get("status") != "COMPLETED":
        return (
            "PENDING_PRIORITY_RESULTS",
            "A8/M5 reproduction is not collected yet; selecting D1-D5 now would overclaim.",
            ["A8_no_terrain_terms", "A6_no_terrain_normal", "A7_no_terrain_height_side"],
        )
    if baseline_f is not None and a8_f is not None and a8_f < baseline_f - 0.01:
        return (
            "D1_REPRODUCIBILITY_FAILURE",
            "A8/M5 no-terrain arm did not reproduce the expected FC-S5 direction against the current A0 baseline.",
            [],
        )

    completed_candidates = [
        r for r in rows
        if r["priority_rank"] not in {"0", "1"} and r["status"] == "COMPLETED"
    ]
    safe_candidates = []
    for r in completed_candidates:
        cand_f = fval(r, "all_10_mean_F")
        cand_easy = fval(r, "easy_control_mean_F")
        cand_hard = fval(r, "hard_diagnostic_mean_F")
        a8_easy = fval(a8, "easy_control_mean_F")
        a8_hard = fval(a8, "hard_diagnostic_mean_F")
        b104_ground = fval(r, "B104_ground_cov")
        open_edges = fval(r, "mean_open_edges")
        non_manifold = fval(r, "mean_non_manifold_edges")
        if (
            cand_f is not None and a8_f is not None and cand_f >= a8_f - 0.005
            and cand_easy is not None and a8_easy is not None and cand_easy >= a8_easy - 0.005
            and cand_hard is not None and a8_hard is not None and cand_hard >= a8_hard - 0.005
            and b104_ground is not None and b104_ground >= 0.99
            and (open_edges is None or open_edges <= 0.0)
            and (non_manifold is None or non_manifold <= 0.0)
        ):
            safe_candidates.append(r)
    if safe_candidates:
        best = max(safe_candidates, key=lambda r: fval(r, "all_10_mean_F") or -1)
        return (
            "D3_TERRAIN_SAFE_IS_BEST",
            f"{best['arm']} matches or beats the no-terrain reference within triage tolerances while preserving B104/topology gates.",
            [],
        )

    pending_terrain = [
        r["arm"] for r in rows
        if r["priority_rank"] in {"2", "3", "4", "5", "6"} and r["status"] != "COMPLETED"
    ]
    if pending_terrain:
        return (
            "PENDING_PRIORITY_RESULTS",
            "A8 is available or expected, but terrain-safe/ramp priority arms are still pending.",
            pending_terrain,
        )
    return (
        "D2_TERRAIN_OFF_IS_BEST",
        "A8/M5 reproduced and no completed gated/robust/ramp terrain variant surpassed the terrain-off reference.",
        [],
    )


def write_decision_table(rows: list[dict[str, str]]) -> None:
    TRIAGE.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "arm",
        "priority_rank",
        "question",
        "source_phase",
        "status",
        "note",
        "ok_count",
        "all_10_mean_F",
        "easy_control_mean_F",
        "hard_diagnostic_mean_F",
        "B104_ground_cov",
        "B104_ground_support_cov",
        "mean_ground_cov",
        "mean_support_cov",
        "mean_ground_support_cov",
        "mean_roof_cov",
        "mean_wall_cov",
        "mean_h_err",
        "mean_vol_ratio",
        "mean_chamfer",
        "mean_open_edges",
        "mean_non_manifold_edges",
        "mean_terrain_y_p10",
        "mean_terrain_y_p50",
        "mean_terrain_y_p90",
        "mean_mutual_mass_roof",
        "mean_mutual_mass_wall",
        "mean_mutual_mass_terrain",
        "mean_entropy_roof",
        "mean_entropy_wall",
        "mean_entropy_terrain",
        "mean_grad_norm_base",
        "mean_grad_norm_mutual",
        "mean_grad_cosine_mutual_depth",
        "mean_grad_cosine_mutual_normal",
        "mean_grad_cosine_mutual_semantic",
        "mean_grad_cosine_mutual_photo",
    ]
    with (TRIAGE / "FC_S6_DECISION_TABLE.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_action_report(rows: list[dict[str, str]]) -> None:
    label, evidence, pending = choose_decision(rows)
    completed_priority = [r for r in rows if r["priority_rank"] != "0" and r["status"] == "COMPLETED"]
    a0 = get_row(rows, "A0_baseline_w0")
    a1 = get_row(rows, "A1_original_mutual")
    a4 = get_row(rows, "A4_terrain_normal_only")
    by_arm = {r["arm"]: r for r in rows}

    def compact_arm_line(arm: str) -> str:
        r = by_arm.get(arm)
        if not r:
            return f"- `{arm}`: missing."
        return (
            f"- `{arm}`: status=`{r.get('status', '')}`, "
            f"all_10_F=`{r.get('all_10_mean_F', '')}`, "
            f"easy_F=`{r.get('easy_control_mean_F', '')}`, "
            f"hard_F=`{r.get('hard_diagnostic_mean_F', '')}`, "
            f"B104_ground_cov=`{r.get('B104_ground_cov', '')}`, "
            f"B104_ground_support_cov=`{r.get('B104_ground_support_cov', '')}`, "
            f"support_cov=`{r.get('mean_support_cov', '')}`, "
            f"ground_support_cov=`{r.get('mean_ground_support_cov', '')}`, "
            f"open_edges=`{r.get('mean_open_edges', '')}`, "
            f"non_manifold_edges=`{r.get('mean_non_manifold_edges', '')}`."
        )

    if pending:
        next_lines = [
            "Run the remaining priority triage sequence in this order:",
            "",
            *[f"- `{arm}`" for arm in pending],
            "",
            "After each arm, regenerate `phase_triage/FC_S6_DECISION_TABLE.csv` and this report.",
        ]
    elif label == "D2_TERRAIN_OFF_IS_BEST":
        next_lines = [
            "Adopt `A8_no_terrain_terms` as the terrain-off Mutual candidate for triage follow-up.",
            "",
            "Next action: run support/topology/viewer QA for `A8_no_terrain_terms` against Baseline, Original Mutual, M3, M5, and M10. Keep terrain relation hints M7/M8 disabled.",
            "",
            "Do not start Phase 3/Phase 4 expansion or `L_structure` until this candidate passes the full acceptance gates.",
        ]
    elif label == "D3_TERRAIN_SAFE_IS_BEST":
        next_lines = [
            "Adopt the selected gated/robust terrain candidate for limited full validation.",
            "",
            "Next action: run support/topology/viewer QA and compare against Baseline, Original Mutual, M3, M5, and M10 before any new relation hint or `L_structure` work.",
        ]
    elif label == "D1_REPRODUCIBILITY_FAILURE":
        next_lines = [
            "Stop new loss experiments.",
            "",
            "Next action: audit config, seed, checkpoint, render export, and Stage3 evaluation for `A8_no_terrain_terms` before launching more arms.",
        ]
    elif label == "D4_NO_SAFE_MUTUAL":
        next_lines = [
            "Do not proceed to `L_structure`.",
            "",
            "Next action: revisit the `L_mutual` design or drop the Mutual-alone improvement claim.",
        ]
    else:
        next_lines = [
            "No automatic next experiment is selected by this triage report.",
            "",
            "Review the decision table and choose whether to run additional validation or stop the Mutual-alone path.",
        ]

    l_structure_answer = "Yes." if label == "D5_REVISED_MUTUAL_READY_FOR_STRUCTURE" else "No."
    if label == "D5_REVISED_MUTUAL_READY_FOR_STRUCTURE":
        l_structure_reason = (
            "`L_structure` is allowed only because this report selected `D5_REVISED_MUTUAL_READY_FOR_STRUCTURE`, "
            "meaning the revised Mutual candidate passed the required triage gates."
        )
    else:
        l_structure_reason = (
            "`L_structure` is blocked because this report did not select `D5_REVISED_MUTUAL_READY_FOR_STRUCTURE`. "
            "Starting `L_structure` now would mix an unresolved `L_mutual` design with a new structural loss and obscure whether terrain/read-out regressions are from Mutual or Structure."
        )

    lines = [
        "# FC-S6 Action Decision",
        "",
        "## 1. Decision Label",
        "",
        f"Selected label: `{label}`.",
        "",
        evidence,
        "",
        "This report is triage-only. It does not claim a final revised `L_mutual` unless `D5_REVISED_MUTUAL_READY_FOR_STRUCTURE` is selected.",
        "",
        "## 2. Evidence",
        "",
        f"- A0 baseline all_10 mean F: `{a0.get('all_10_mean_F', '') if a0 else ''}`.",
        f"- A1 original mutual all_10 mean F: `{a1.get('all_10_mean_F', '') if a1 else ''}`.",
        f"- A4 terrain-normal-only all_10 mean F: `{a4.get('all_10_mean_F', '') if a4 else ''}`.",
        f"- Completed priority arms: `{len(completed_priority)}`.",
        "- Priority arm summary:",
        compact_arm_line("A8_no_terrain_terms"),
        compact_arm_line("A6_no_terrain_normal"),
        compact_arm_line("A7_no_terrain_height_side"),
        compact_arm_line("B4_terrain_quantile_height"),
        compact_arm_line("B2_terrain_confidence_gated"),
        compact_arm_line("A9_no_terrain_terms_ramp"),
        "",
        "## 3. Cancelled Or Deprioritized Arms",
        "",
        "- Cancelled now: `A5_height_relation_only` was interrupted at triage switch because it is lower priority than A8/A6/A7.",
        "- Deprioritized until after terrain-first triage: `A5_height_relation_only`, `B1_terrain_low_weight`, `B3_terrain_class_mass_gated`, `B5_split_height_low_terrain_side`, `B6_terrain_confidence_gated_ramp`.",
        "- Deferred: all Phase 3, all Phase 4, relation hints M7/M8, `L_structure`, and G2.",
        "",
        "## 4. Next Concrete Experiment",
        "",
        *next_lines,
        "",
        "## 5. Is L_structure Allowed To Start?",
        "",
        l_structure_answer,
        "",
        l_structure_reason,
    ]
    if pending:
        lines.extend([
            "",
            "## Pending Priority Evidence",
            "",
            *[f"- `{arm}`" for arm in pending],
        ])
    (TRIAGE / "FC_S6_ACTION_DECISION.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    rows = load_decision_rows()
    write_decision_table(rows)
    write_action_report(rows)


if __name__ == "__main__":
    main()

"""Collect FC-S6 metrics into split summaries and conservative reports."""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import scripts.mutual_loss.fc_s6_stage3_metric_v1_eval as ev


OUT_ROOT = ROOT / "results/FC_S6_componentwise_revised_lmutual_design_validation"
BASELINE_CSV = ev.BASELINE_CSV
FC_S5_SPLIT = ROOT / "results/FC_S5_loss_ledger_instrumentation/phase2_diagnostics/diagnostic_split_summary.csv"


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


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


def fnum(value: object) -> Optional[float]:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def fmt(value: object, ndigits: int = 3) -> str:
    x = fnum(value)
    return "" if x is None else f"{x:.{ndigits}f}"


def mean_field(rows: Iterable[Dict[str, str]], field: str) -> Optional[float]:
    vals = [fnum(r.get(field)) for r in rows]
    vals = [v for v in vals if v is not None]
    return float(np.mean(vals)) if vals else None


def baseline_summary() -> Dict[str, Optional[float]]:
    rows = read_csv(BASELINE_CSV)
    easy = set(ev.SPLITS["easy_control"])
    hard = set(ev.SPLITS["hard_diagnostic"])
    return {
        "e1_all_F": mean_field(rows, "e1_F"),
        "e2_all_F": mean_field(rows, "e2_F"),
        "e1_easy_F": mean_field([r for r in rows if r.get("bid") in easy], "e1_F"),
        "e2_easy_F": mean_field([r for r in rows if r.get("bid") in easy], "e2_F"),
        "e1_hard_F": mean_field([r for r in rows if r.get("bid") in hard], "e1_F"),
        "e2_hard_F": mean_field([r for r in rows if r.get("bid") in hard], "e2_F"),
    }


def fc_s5_split_value(run: str, split: str, field: str = "mean_F") -> Optional[float]:
    for row in read_csv(FC_S5_SPLIT):
        if row.get("run") == run and row.get("split") == split:
            return fnum(row.get(field))
    return None


def split_row(split_csv: Path, run: str, split: str) -> Dict[str, str]:
    for row in read_csv(split_csv):
        if row.get("run") == run and row.get("split") == split:
            return row
    return {}


def all_runs(metrics_csv: Path) -> List[str]:
    return sorted({r.get("run", "") for r in read_csv(metrics_csv) if r.get("run")})


def table_from_split(split_csv: Path, runs: List[str]) -> str:
    lines = [
        "| run | all status | all mean F | easy mean F | hard mean F | terrain-sensitive F | mean support_cov | mean ground_support_cov |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run in runs:
        all_r = split_row(split_csv, run, "all_10")
        easy = split_row(split_csv, run, "easy_control")
        hard = split_row(split_csv, run, "hard_diagnostic")
        terrain = split_row(split_csv, run, "terrain_sensitive")
        lines.append(
            f"| {run} | {all_r.get('status', 'PENDING')} | {fmt(all_r.get('mean_F'))} | "
            f"{fmt(easy.get('mean_F'))} | {fmt(hard.get('mean_F'))} | "
            f"{fmt(terrain.get('mean_F'))} | {fmt(all_r.get('mean_support_cov'))} | "
            f"{fmt(all_r.get('mean_ground_support_cov'))} |"
        )
    return "\n".join(lines)


def select_phase2_candidate(metrics_csv: Path, split_csv: Path) -> Optional[str]:
    base = baseline_summary()
    e1_all = base.get("e1_all_F")
    e1_easy = base.get("e1_easy_F")
    e1_hard = base.get("e1_hard_F")
    m5_hard = fc_s5_split_value("M5", "hard_diagnostic") or e1_hard
    if e1_all is None or e1_easy is None or e1_hard is None:
        return None
    candidates = []
    metrics = read_csv(metrics_csv)
    for run in all_runs(metrics_csv):
        all_r = split_row(split_csv, run, "all_10")
        easy = split_row(split_csv, run, "easy_control")
        hard = split_row(split_csv, run, "hard_diagnostic")
        if not all(r.get("status") == "OK" for r in [all_r, easy, hard]):
            continue
        all_f = fnum(all_r.get("mean_F"))
        easy_f = fnum(easy.get("mean_F"))
        hard_f = fnum(hard.get("mean_F"))
        b104 = next((r for r in metrics if r.get("run") == run and r.get("bid") == "B104"), {})
        b104_ground = fnum(b104.get("ground_cov"))
        b104_ground_support = fnum(b104.get("ground_support_cov"))
        if all_f is None or easy_f is None or hard_f is None:
            continue
        if all_f < e1_all - 0.005:
            continue
        if easy_f < e1_easy - 0.005:
            continue
        if hard_f < max(e1_hard, m5_hard or e1_hard) - 0.005:
            continue
        if b104_ground is None or b104_ground < 0.99:
            continue
        if b104_ground_support is None:
            continue
        candidates.append((all_f, hard_f, run))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    selected = candidates[0][2]
    (OUT_ROOT / "phase2_terrain_safe" / "selected_terrain_safe_candidate.txt").write_text(selected + "\n")
    return selected


def update_summaries() -> None:
    phase1 = OUT_ROOT / "phase1_existing_terms"
    phase2 = OUT_ROOT / "phase2_terrain_safe"
    phase3 = OUT_ROOT / "phase3_nonterrain_priors"
    if (phase1 / "term_ablation_metrics_by_bid.csv").exists():
        ev.update_split_summary(phase1 / "term_ablation_metrics_by_bid.csv", phase1 / "term_ablation_split_summary.csv")
        ev.update_win_loss(phase1 / "term_ablation_metrics_by_bid.csv", phase1 / "term_ablation_win_loss.csv")
    if (phase2 / "terrain_safe_metrics_by_bid.csv").exists():
        ev.update_split_summary(phase2 / "terrain_safe_metrics_by_bid.csv", phase2 / "terrain_safe_split_summary.csv")
    if (phase3 / "nonterrain_prior_metrics_by_bid.csv").exists():
        ev.update_split_summary(phase3 / "nonterrain_prior_metrics_by_bid.csv", phase3 / "nonterrain_prior_split_summary.csv")


def write_reports() -> None:
    base = baseline_summary()
    phase1 = OUT_ROOT / "phase1_existing_terms"
    phase2 = OUT_ROOT / "phase2_terrain_safe"
    phase3 = OUT_ROOT / "phase3_nonterrain_priors"
    phase5 = OUT_ROOT / "phase5_candidate_selection"
    p1_runs = all_runs(phase1 / "term_ablation_metrics_by_bid.csv")
    p2_runs = all_runs(phase2 / "terrain_safe_metrics_by_bid.csv")
    p3_runs = all_runs(phase3 / "nonterrain_prior_metrics_by_bid.csv")
    selected = select_phase2_candidate(phase2 / "terrain_safe_metrics_by_bid.csv", phase2 / "terrain_safe_split_summary.csv")

    (phase1 / "TERM_DECOMPOSITION_REPORT.md").write_text(
        "# FC-S6 Phase 1 Term Decomposition Report\n\n"
        "## Baseline Context\n\n"
        f"- E1 all-10 mean F: {fmt(base.get('e1_all_F'))}\n"
        f"- E2 Original Mutual all-10 mean F: {fmt(base.get('e2_all_F'))}\n"
        f"- E1 easy/control mean F: {fmt(base.get('e1_easy_F'))}\n"
        f"- E1 hard diagnostic mean F: {fmt(base.get('e1_hard_F'))}\n\n"
        "## Arm Status\n\n"
        f"{table_from_split(phase1 / 'term_ablation_split_summary.csv', p1_runs)}\n\n"
        "## Decision State\n\n"
        "No term is accepted or rejected until all per-bid Stage3Algo-v1 + Metric-v1 rows are complete. Proxy loss improvements without final semantic surface graph/shell improvements must be reported as proxy mismatch.\n"
    )

    b104_lines = [
        "# FC-S6 B104 Terrain Drift Report",
        "",
        "| run | status | ground_cov | ground_support_cov | terrain_y_p10 | terrain_y_p50 | terrain_y_p90 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in read_csv(phase2 / "terrain_safe_metrics_by_bid.csv"):
        if row.get("bid") != "B104":
            continue
        b104_lines.append(
            f"| {row.get('run')} | {row.get('status')} | {fmt(row.get('ground_cov'))} | "
            f"{fmt(row.get('ground_support_cov'))} | {fmt(row.get('terrain_y_p10'))} | "
            f"{fmt(row.get('terrain_y_p50'))} | {fmt(row.get('terrain_y_p90'))} |"
        )
    (phase2 / "B104_TERRAIN_DRIFT_REPORT.md").write_text("\n".join(b104_lines) + "\n")
    (phase2 / "TERRAIN_SAFE_REDESIGN_REPORT.md").write_text(
        "# FC-S6 Phase 2 Terrain-Safe Redesign Report\n\n"
        "## Arm Status\n\n"
        f"{table_from_split(phase2 / 'terrain_safe_split_summary.csv', p2_runs)}\n\n"
        "## Gate State\n\n"
        f"Selected terrain-safe candidate: `{selected or 'NONE_YET'}`\n\n"
        "Terrain terms are retained only if they improve or tie final Stage3 read-out gates without B104/support/topology regression. Removing terrain terms remains only a candidate, not a final decision.\n"
    )

    phase3_status = "READY_AFTER_PHASE2_SELECTION" if selected else "BLOCKED_PENDING_PHASE2_SELECTION"
    (phase3 / "NONTERRAIN_PRIOR_VALIDATION_REPORT.md").write_text(
        "# FC-S6 Phase 3 Non-Terrain Prior Validation Report\n\n"
        f"Status: `{phase3_status}`\n\n"
        f"{table_from_split(phase3 / 'nonterrain_prior_split_summary.csv', p3_runs) if p3_runs else 'No Phase 3 metrics yet.'}\n"
    )

    candidate_rows = [
        {"candidate": "E1_Baseline", "source": "FC-S3", "status": "REFERENCE", "mean_F": fmt(base.get("e1_all_F")), "decision_label": ""},
        {"candidate": "E2_Original_Mutual", "source": "FC-S3", "status": "REFERENCE", "mean_F": fmt(base.get("e2_all_F")), "decision_label": ""},
        {"candidate": "M3", "source": "FC-S5", "status": "REFERENCE", "mean_F": fmt(fc_s5_split_value("M3", "all_10")), "decision_label": ""},
        {"candidate": "M5", "source": "FC-S5", "status": "REFERENCE_CURRENT_CANDIDATE_ONLY", "mean_F": fmt(fc_s5_split_value("M5", "all_10")), "decision_label": ""},
        {"candidate": "M10", "source": "FC-S5", "status": "REFERENCE", "mean_F": fmt(fc_s5_split_value("M10", "all_10")), "decision_label": ""},
    ]
    for split_csv, source in [
        (phase1 / "term_ablation_split_summary.csv", "FC-S6 Phase 1"),
        (phase2 / "terrain_safe_split_summary.csv", "FC-S6 Phase 2"),
        (phase3 / "nonterrain_prior_split_summary.csv", "FC-S6 Phase 3"),
    ]:
        for row in read_csv(split_csv):
            if row.get("split") != "all_10":
                continue
            candidate_rows.append({
                "candidate": row.get("run"),
                "source": source,
                "status": row.get("status"),
                "mean_F": fmt(row.get("mean_F")),
                "decision_label": "ACCEPT_TERRAIN_GATED_MUTUAL" if selected and row.get("run") == selected else "",
            })
    write_csv(phase5 / "revised_mutual_candidate_table.csv", candidate_rows)
    decision = "PENDING"
    if selected:
        if "no_terrain" in selected:
            decision = "ACCEPT_TERRAIN_OFF_MUTUAL"
        elif "gated" in selected or "gate" in selected:
            decision = "ACCEPT_TERRAIN_GATED_MUTUAL"
        else:
            decision = "ACCEPT_REVISED_MUTUAL"
    (phase5 / "FC_S6_FINAL_DECISION.md").write_text(
        "# FC-S6 Final Decision\n\n"
        f"Decision: `{decision}`\n\n"
        "This decision remains provisional unless all acceptance gates, viewer QA, support/topology checks, and gradient diagnostics are complete. Do not proceed to `L_structure` or G2 from this file unless the gate evidence is complete and explicitly accepted.\n"
    )


def main() -> None:
    update_summaries()
    write_reports()


if __name__ == "__main__":
    main()

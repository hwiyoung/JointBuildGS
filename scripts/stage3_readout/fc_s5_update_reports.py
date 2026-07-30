"""Update FC-S5 diagnostic markdown reports from current CSV artifacts."""
from __future__ import annotations

import csv
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = ROOT / "results/FC_S5_loss_ledger_instrumentation"
DIAG_ROOT = OUT_ROOT / "phase2_diagnostics"
JOB_ROOT = OUT_ROOT / "phase2_jobs/nohup"
BASELINE_CSV = (
    ROOT
    / "results/footprint_conditioned_readout"
    / "FC_S3_mutual_loss_alignment_g2_target_definition"
    / "phase1_full_e1_e2_comparison/e1_e2_paired_metrics_by_bid.csv"
)

RUNS = ["M3", "M5", "M10"]
EASY_CONTROL = {"B0", "B1", "B2", "B8", "B50"}
HARD_DIAGNOSTIC = {"B6", "B3", "B123", "B126", "B104"}


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def fnum(value: object) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt(value: object, ndigits: int = 3) -> str:
    x = fnum(value)
    return "" if x is None else f"{x:.{ndigits}f}"


def mean_field(rows: Iterable[Dict[str, str]], field: str) -> Optional[float]:
    vals = [fnum(r.get(field)) for r in rows]
    vals = [v for v in vals if v is not None]
    return mean(vals) if vals else None


def rows_for(run: str) -> List[Dict[str, str]]:
    return read_csv(DIAG_ROOT / f"{run}_metrics_by_bid.csv")


def completed_rows(run: str) -> List[Dict[str, str]]:
    return [r for r in rows_for(run) if r.get("status") == "OK"]


def run_status(run: str) -> str:
    rows = rows_for(run)
    if not rows:
        return "MISSING"
    statuses = {r.get("status", "") for r in rows}
    jobs = {r.get("job_status", "") for r in rows}
    if statuses == {"OK"} and len(rows) == 10:
        return "EVALUATED"
    if any("RUNNING" in j for j in jobs):
        return "RUNNING"
    if any("QUEUED" in j for j in jobs):
        return "QUEUED"
    if any(s == "PENDING" for s in statuses):
        return "PENDING"
    return "INCOMPLETE"


def baseline_summary() -> Dict[str, Optional[float]]:
    rows = read_csv(BASELINE_CSV)
    out = {
        "e1_all_F": mean_field(rows, "e1_F"),
        "e2_all_F": mean_field(rows, "e2_F"),
        "e1_easy_F": mean_field([r for r in rows if r.get("bid") in EASY_CONTROL], "e1_F"),
        "e2_easy_F": mean_field([r for r in rows if r.get("bid") in EASY_CONTROL], "e2_F"),
        "e1_hard_F": mean_field([r for r in rows if r.get("bid") in HARD_DIAGNOSTIC], "e1_F"),
        "e2_hard_F": mean_field([r for r in rows if r.get("bid") in HARD_DIAGNOSTIC], "e2_F"),
    }
    return out


def run_table() -> str:
    lines = [
        "| run | status | completed OK rows | mean F | mean ground_cov | note |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    notes = {
        "M3": "Reduced mutual weight; tests whether original mutual was too strong.",
        "M5": "Terrain terms disabled; tests B104-like terrain drift.",
        "M10": "Ramped mutual; tests early-geometry disturbance.",
    }
    for run in RUNS:
        ok = completed_rows(run)
        lines.append(
            f"| {run} | {run_status(run)} | {len(ok)}/10 | {fmt(mean_field(ok, 'F'))} | "
            f"{fmt(mean_field(ok, 'ground_cov'))} | {notes[run]} |"
        )
    return "\n".join(lines)


def selected_candidate() -> str:
    base = baseline_summary().get("e1_all_F")
    eligible = []
    for run in RUNS:
        ok = completed_rows(run)
        if len(ok) != 10:
            continue
        mean_f = mean_field(ok, "F")
        b104 = next((r for r in ok if r.get("bid") == "B104"), {})
        ground = fnum(b104.get("ground_cov"))
        if mean_f is not None and base is not None and mean_f >= base - 0.005 and ground is not None:
            eligible.append((mean_f, run))
    if not eligible:
        return "None selected yet."
    return f"{max(eligible)[1]} is the current candidate by all-10 mean F gate."


def write_loss_report() -> None:
    b104 = read_csv(DIAG_ROOT / "B104_terrain_drift_summary.csv")
    split = read_csv(DIAG_ROOT / "diagnostic_split_summary.csv")
    text = f"""# FC-S5 Loss Diagnostic Report

## Status

Current diagnostic state is derived from the metrics CSVs and job records. M3 Stage2 training has completed and its Stage3Algo-v1 + Metric-v1 evaluation is being run separately. M5/M10 are handled by the remaining background chain.

## Current Run State

{run_table()}

## B104 Terrain Drift

| run | job_status | ground_cov | ground_support_cov | terrain_drift_status |
| --- | --- | ---: | ---: | --- |
"""
    for row in b104:
        text += (
            f"| {row.get('run','')} | {row.get('job_status','')} | "
            f"{fmt(row.get('B104_ground_cov'))} | {fmt(row.get('B104_ground_support_cov'))} | "
            f"{row.get('terrain_drift_status','')} |\n"
        )
    text += """
## Split Summary

| run | split | status | mean_F | mean_ground_cov | mean_ground_support_cov |
| --- | --- | --- | ---: | ---: | ---: |
"""
    for row in split:
        text += (
            f"| {row.get('run','')} | {row.get('split','')} | {row.get('status','')} | "
            f"{fmt(row.get('mean_F'))} | {fmt(row.get('mean_ground_cov'))} | "
            f"{fmt(row.get('mean_ground_support_cov'))} |\n"
        )
    text += f"""
## Selection Gate State

{selected_candidate()}

No final mutual candidate should be accepted until all-10, easy/control, hard diagnostic, B104 terrain, support, and topology gates are evaluated.
"""
    (DIAG_ROOT / "LOSS_DIAGNOSTIC_REPORT.md").write_text(text)


def write_final_report() -> None:
    base = baseline_summary()
    text = f"""# FC-S5 Experiment Report

## Scope

This run implements FC-S5 loss ledger instrumentation and cheap mutual diagnostics. It does not run full G2 training, does not enable `L_structure`, does not implement relation hints, and does not modify Stage3 or Metric-v1.

## Baseline Context

- FC-S3 E1 all-10 mean F: {fmt(base.get('e1_all_F'))}
- FC-S3 E2 all-10 mean F: {fmt(base.get('e2_all_F'))}
- FC-S3 E1 easy/control mean F: {fmt(base.get('e1_easy_F'))}
- FC-S3 E2 easy/control mean F: {fmt(base.get('e2_easy_F'))}
- FC-S3 E1 hard diagnostic mean F: {fmt(base.get('e1_hard_F'))}
- FC-S3 E2 hard diagnostic mean F: {fmt(base.get('e2_hard_F'))}

## 1. Were the loss ledger logs successfully added?

Yes. `phase1_instrumentation/INSTRUMENTATION_REPORT.md` records the smoke pass, requested ledger tags, class stats, gradient diagnostics, and disabled placeholder records.

## 2. Did default-off behavior remain unchanged?

Yes for the direct mutual tensor equivalence check recorded in `phase1_instrumentation/default_off_equivalence.md`.

## Diagnostic Runs

{run_table()}

## 3. Did M3 restore baseline-like stability?

{answer_run('M3')}

## 4. Did M5 reduce B104 terrain drift or recover ground_cov?

{answer_run('M5')}

## 5. Did M10 improve stability?

{answer_run('M10')}

## 6. Which run is the best revised mutual candidate, if any?

{selected_candidate()}

## 7. Is it safe to proceed to relation-hint prototype?

Not until a revised mutual candidate ties or beats the baseline gates without B104/support/topology regressions.

## 8. Is it safe to proceed to L_structure prototype?

No. `L_structure` should remain disabled until revised mutual is stable under final Stage3Algo-v1 + Metric-v1 read-out.

## 9. Should the next step be full retraining, more loss redesign, or Stage3/evaluator work?

Pending final diagnostic metrics. If no candidate ties or beats the baseline gates, the next step remains loss redesign rather than full retraining.
"""
    (OUT_ROOT / "FC_S5_EXPERIMENT_REPORT.md").write_text(text)


def answer_run(run: str) -> str:
    status = run_status(run)
    ok = completed_rows(run)
    if len(ok) == 10:
        return f"Evaluated. all-10 mean F={fmt(mean_field(ok, 'F'))}, ground_cov={fmt(mean_field(ok, 'ground_cov'))}."
    return f"Not determined yet. Current status: {status}."


def main() -> None:
    write_loss_report()
    write_final_report()


if __name__ == "__main__":
    main()

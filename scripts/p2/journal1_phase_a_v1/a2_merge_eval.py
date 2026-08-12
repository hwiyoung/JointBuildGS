#!/usr/bin/env python3
"""A2 row merge: sealed A3 geometry rows + new E7/E8 rows → one merged read-out.

Reuses `geometry_eval.aggregate` unchanged (same metrics, same E2 baseline) on
the concatenated rows, and adds the §4.4 change-candidate stratification using
the Phase-A automatic label candidates (tiers A/B = change-candidate,
C = consistent, rest = NA). Labels are still automatic candidates — human
review (Phase B) is pending — so stratified numbers are preliminary.
Non-confirmatory; scientific_verdict stays null.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.p2.journal1_phase_a_v1.geometry_eval import aggregate

REPO = Path(__file__).resolve().parents[3]
TASK = Path("/artifacts/JointBuildGS/phase-payloads/p2/journal1_phase_a_v1/P2-JOURNAL1-PHASE-A-v1")
A3_EVAL = TASK / "evaluation"
A2_EVAL = TASK / "a2/evaluation_e7e8"
OUT = TASK / "a2/evaluation_merged"
LABELS = TASK / "labels/change_label_candidates_v1.csv"
CONFIG = REPO / "configs/p2/journal1_phase_a_v1/run_v2_e7e8.json"


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stratum_of(tier: str) -> str:
    if tier.startswith("A_") or tier.startswith("B_"):
        return "CHANGE_CANDIDATE_AB"
    if tier.startswith("C_"):
        return "CONSISTENT_C"
    return "NA_UNDECIDABLE"


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert cfg.get("scientific_verdict") is None
    a3_rows = read_rows(A3_EVAL / "rows.jsonl")
    a2_rows = read_rows(A2_EVAL / "rows.jsonl")
    a3_arms = {row["arm"] for row in a3_rows}
    a2_arms = {row["arm"] for row in a2_rows}
    if a3_arms & a2_arms:
        raise RuntimeError(f"arm overlap between A3 and A2 rows: {a3_arms & a2_arms}")
    rows = a3_rows + a2_rows

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "rows.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    keys = sorted({key for row in rows for key in row})
    with (OUT / "rows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)

    summary = aggregate(rows, cfg)
    json.dump(summary, (OUT / "summary.json").open("w"), indent=1)

    tiers = {row["stable_id"]: row["tier"] for row in csv.DictReader(LABELS.open(encoding="utf-8"))}
    strata: dict[str, set[str]] = {}
    for stable_id, tier in tiers.items():
        strata.setdefault(stratum_of(tier), set()).add(stable_id)
    stratified = {
        "note": "automatic change-label candidates (Phase-B human review pending); preliminary stratification",
        "tier_counts": {name: len(ids) for name, ids in sorted(strata.items())},
        "strata": {},
    }
    for name, ids in sorted(strata.items()):
        subset = [row for row in rows if row["stable_id"] in ids]
        stratified["strata"][name] = aggregate(subset, cfg)
    json.dump(stratified, (OUT / "stratified_summary.json").open("w"), indent=1)

    receipt = {
        "schema": "jointbuildgs.p2.journal1_phase_a_v1.a2_merged_eval.v1",
        "task_id": cfg["task_id"],
        "stage": "A2",
        "started_utc": started,
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "a3_rows": str(A3_EVAL / "rows.jsonl"),
            "a2_rows": str(A2_EVAL / "rows.jsonl"),
            "labels": str(LABELS),
            "config": str(CONFIG.relative_to(REPO)),
        },
        "n_rows": len(rows),
        "n_rows_a3": len(a3_rows),
        "n_rows_a2": len(a2_rows),
        "arms": sorted(a3_arms | a2_arms),
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    json.dump(receipt, (OUT / "receipt.json").open("w"), indent=1)
    print(json.dumps({key: value for key, value in summary["per_arm"].items() if key.startswith(("E7", "E8"))}, indent=1))
    print(f"[journal1-A2] merged → {OUT}")


if __name__ == "__main__":
    main()

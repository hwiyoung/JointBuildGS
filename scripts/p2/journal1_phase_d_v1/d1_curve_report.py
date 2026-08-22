#!/usr/bin/env python3
"""D1 curve report: paired degradation of every union-curve run vs its sealed
delta=0 anchor, on the confirmed 93-building population.

Benefit channel (completeness/coverage, plus tau=0.1/0.25 cross-check) and cost
channel (precision/z-spread/normal/outlier/f1/acc) are reported separately per
the pre-registered reading rule; Roofer technical-valid counts and auto-OX O50
(if present) join per run. Curves only — H-M2 verdict text stays for D3 and the
human reviewer. Non-confirmatory; scientific_verdict stays null.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy import stats

REPO = Path(__file__).resolve().parents[3]
ARTIFACTS = Path("/artifacts/JointBuildGS")
D1_CONFIG = REPO / "configs/p2/journal1_phase_d_v1/d1_union_curve_v1.json"
A2_ROOT = ARTIFACTS / "phase-payloads/p2/journal1_phase_a_v1/P2-JOURNAL1-PHASE-A-v1"
V3_RESULTS = ARTIFACTS / (
    "phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
    "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3/results/building_method_status_v3.csv")
BENEFIT = ["completeness@0.5", "coverage", "completeness@0.25", "completeness@0.1"]
COST = ["precision@0.5", "z_spread", "normal_med_deg", "outlier_rate", "f1@0.5", "acc_median"]


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def metric_map(rows: list[dict], arm: str, gt: str, key: str, chosen: set) -> dict:
    return {r["stable_id"]: r.get(key) for r in rows
            if r["arm"] == arm and r["gt"] == gt and r["stable_id"] in chosen}


def paired(delta_map: dict, anchor_map: dict) -> dict | None:
    pairs = [(delta_map[s], anchor_map[s]) for s in delta_map
             if s in anchor_map and delta_map[s] is not None and anchor_map[s] is not None]
    if len(pairs) < 5:
        return None
    d = np.array([a - b for a, b in pairs])
    nz = d[d != 0]
    out = {
        "n": int(len(d)),
        "delta_median": float(np.median(d)),
        "wins": int((d > 0).sum()), "losses": int((d < 0).sum()),
        "run_median": float(np.median([a for a, _ in pairs])),
        "anchor_median": float(np.median([b for _, b in pairs])),
    }
    if len(nz) >= 10:
        out["wilcoxon_p"] = float(stats.wilcoxon(nz).pvalue)
    return out


def roofer_valid(path: Path, condition: str, chosen: set) -> int | None:
    if not path.is_file():
        return None
    return sum(1 for r in csv.DictReader(path.open(encoding="utf-8"))
               if r["condition_id"] == condition and r["stable_id"] in chosen
               and r["status"] == "TECHNICAL_VALID_LOD22")


def main() -> None:
    d1 = json.load(open(D1_CONFIG))
    out_root = Path(d1["out_root"])
    report_dir = out_root.parent / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    chosen = set(json.load(open(d1["population"]))["effective_selected_ids"])
    anchor_rows = read_rows(A2_ROOT / "a2/evaluation_merged/rows.jsonl")

    anchors_roofer = {
        "E8": roofer_valid(A2_ROOT / "a2/results/building_method_status_a2_v1.csv", "E8", chosen),
        "E7": roofer_valid(A2_ROOT / "a2/results/building_method_status_a2_v1.csv", "E7", chosen),
        "E2": roofer_valid(V3_RESULTS, "C2_MVS", chosen),
    }

    ox_summary_path = report_dir / "d1_auto_ox_summary_v1.json"
    ox = json.load(open(ox_summary_path))["runs"] if ox_summary_path.is_file() else {}

    curves = {}
    for run in d1["runs"]:
        label, cond = run["label"], run["condition"]
        run_root = out_root / label
        rows_path = run_root / "evaluation/rows.jsonl"
        if not rows_path.is_file():
            print(f"[d1-curve] SKIP {label}: rows missing")
            continue
        run_rows = read_rows(rows_path)
        entry = {"condition": cond, "dx_east_m": run["dx"], "dz_m": run["dz"],
                 "benefit_channel": {}, "cost_channel": {},
                 "roofer_valid_selected93": roofer_valid(
                     run_root / "results/building_method_status_a2_v1.csv", cond, chosen),
                 "roofer_valid_anchor": anchors_roofer[cond],
                 "auto_ox": ox.get(label)}
        for gt in ("lod2", "e1"):
            for channel, keys in (("benefit_channel", BENEFIT), ("cost_channel", COST)):
                for key in keys:
                    delta_map = metric_map(run_rows, label, gt, key, chosen)
                    anchor_map = metric_map(anchor_rows, cond, gt, key, chosen)
                    result = paired(delta_map, anchor_map)
                    if result is not None:
                        entry[channel][f"{key}|{gt}"] = result
        curves[label] = entry
        print(f"[d1-curve] {label}: f1|e1 {entry['cost_channel'].get('f1@0.5|e1', {}).get('delta_median')}"
              f" comp|e1 {entry['benefit_channel'].get('completeness@0.5|e1', {}).get('delta_median')}"
              f" roofer {entry['roofer_valid_selected93']}/{entry['roofer_valid_anchor']}")

    payload = {
        "schema": "jointbuildgs.p2.journal1_phase_d_v1.d1_curve.v1",
        "task_id": d1["task_id"], "stage": "D1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "population": "confirmed 93 (labels/selection_confirm_v1.json)",
        "anchors": "sealed A2 delta=0 rows (E8, E7) and sealed C2_MVS Roofer results (E2 context)",
        "reading_rule": "benefit vs cost channels separated per the pre-registered Phase-D rule; tau=0.25/0.1 completeness are the bluntness cross-check",
        "curves": curves,
        "official_PASS_usable": None, "scientific_verdict": None,
    }
    (report_dir / "d1_curve_v1.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"[d1-curve] → {report_dir / 'd1_curve_v1.json'}")


if __name__ == "__main__":
    main()

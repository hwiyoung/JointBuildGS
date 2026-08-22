#!/usr/bin/env python3
"""HV-1: C2C conflict baseline — depth-based detector performance and blind
spots, on existing bytes only (no training, no new chains).

Per building (confirmed 93): conflict score S = median 3D nearest-neighbour
distance from the ALS-only crop (class 6) to the E2 crop (class 6), within the
sealed footprint+3m crops. Computed for delta in {0, 0.25, 0.5, 1.0} using the
sealed A2 E7 crop (delta=0) and the D1 E7_dx* crops (injected ground truth).

Read-outs (pre-registered in HV_VERIFICATION_DESIGN_ko_v1.md):
  1. H-V-delta: paired dS(delta), per-delta detection AUC (S_delta vs S_0),
     stratified by rf_roof_type (horizontal vs slanted) — sliding-blindness test.
  2. H-V-chg: ROC/AUC of S_0 separating A-tier change candidates from C-tier,
     within the confirmed 93 (candidate labels; preliminary).
Non-confirmatory; scientific_verdict stays null. CPU, project container.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import mannwhitneyu, wilcoxon

from scripts.p2.journal1_phase_a_v1.geometry_eval import read_ply, roof_points

ART = Path("/artifacts/JointBuildGS")
A2 = ART / "phase-payloads/p2/journal1_phase_a_v1/P2-JOURNAL1-PHASE-A-v1"
PD = ART / "phase-payloads/p2/journal1_phase_d_v1/P2-JOURNAL1-PHASE-D-v1"
OUT = PD / "hv1_c2c_baseline"
DELTAS = {
    "d000": A2 / "a2/assets_roofer_input/E7",
    "d025": PD / "union_curve/E7_dx025/assets_roofer_input/E7",
    "d050": PD / "union_curve/E7_dx050/assets_roofer_input/E7",
    "d100": PD / "union_curve/E7_dx100/assets_roofer_input/E7",
}
E2_DIR = ART / "phase-payloads/p2/e1_e6_roofer_ox_review_v1/P2-E1-E6-GATE5-DASHBOARD-v1/assets_roofer_input/E2"


def crop_roof(directory: Path, sid: str):
    hits = sorted(directory.glob(f"*_{sid}.points.ply"))
    if not hits:
        return None
    xyz, cls = read_ply(hits[0])
    roof, _ = roof_points(xyz, cls)
    return roof if len(roof) >= 30 else None


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    if not len(pos) or not len(neg):
        return float("nan")
    u = mannwhitneyu(pos, neg, alternative="greater").statistic
    return float(u / (len(pos) * len(neg)))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    chosen = sorted(json.load(open(A2 / "labels/selection_confirm_v1.json"))["effective_selected_ids"])
    tiers = {r["stable_id"]: r["tier"][0] for r in csv.DictReader(open(A2 / "labels/change_label_candidates_v1.csv"))}
    roof_type = {}
    for r in csv.DictReader(open(A2 / "a2/results/building_method_status_a2_v1.csv")):
        if r["condition_id"] == "E7" and r["rf_roof_type"] not in ("", "None"):
            roof_type[r["stable_id"]] = r["rf_roof_type"]

    rows = []
    for sid in chosen:
        e2 = crop_roof(E2_DIR, sid)
        if e2 is None:
            continue
        tree = cKDTree(e2)
        entry = {"stable_id": sid, "tier": tiers.get(sid, "?"),
                 "roof_type": roof_type.get(sid, "unknown")}
        for key, directory in DELTAS.items():
            als = crop_roof(directory, sid)
            if als is None:
                entry[f"S_{key}"] = None
                continue
            if len(als) > 200_000:
                als = als[:: int(np.ceil(len(als) / 200_000))]
            d, _ = tree.query(als, k=1, workers=-1)
            entry[f"S_{key}"] = float(np.median(d))
        rows.append(entry)

    with (OUT / "hv1_scores_v1.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    def series(key: str, subset=None):
        return np.array([r[f"S_{key}"] for r in rows
                          if r[f"S_{key}"] is not None and r["S_d000"] is not None
                          and (subset is None or subset(r))])

    summary = {"schema": "jointbuildgs.p2.journal1_hv_v1.hv1_c2c.v1",
               "generated_utc": datetime.now(timezone.utc).isoformat(),
               "n_buildings": len(rows),
               "delta_detection": {}, "roof_type_stratified": {},
               "change_roc": {}, "official_PASS_usable": None,
               "scientific_verdict": None}
    s0_all = series("d000")
    for key in ("d025", "d050", "d100"):
        paired = [(r[f"S_{key}"], r["S_d000"]) for r in rows
                  if r.get(f"S_{key}") is not None and r["S_d000"] is not None]
        d = np.array([a - b for a, b in paired])
        block = {"n": int(len(d)), "dS_median": float(np.median(d)),
                 "wins": int((d > 0).sum()),
                 "auc_vs_d000": auc(series(key), s0_all)}
        nz = d[d != 0]
        if len(nz) >= 10:
            block["wilcoxon_p"] = float(wilcoxon(nz).pvalue)
        for rt in ("horizontal", "slanted"):
            sub = lambda r, rt=rt: r["roof_type"] == rt
            pr = [(r[f"S_{key}"], r["S_d000"]) for r in rows
                  if r.get(f"S_{key}") is not None and r["S_d000"] is not None and r["roof_type"] == rt]
            if len(pr) >= 5:
                dd = np.array([a - b for a, b in pr])
                block[f"dS_median_{rt}"] = float(np.median(dd))
                block[f"auc_{rt}"] = auc(series(key, sub), series("d000", sub))
                block[f"n_{rt}"] = int(len(dd))
        summary["delta_detection"][key] = block

    pos = np.array([r["S_d000"] for r in rows if r["tier"] == "A" and r["S_d000"] is not None])
    neg = np.array([r["S_d000"] for r in rows if r["tier"] == "C" and r["S_d000"] is not None])
    summary["change_roc"] = {
        "positives_A": int(len(pos)), "negatives_C": int(len(neg)),
        "auc": auc(pos, neg),
        "S_median_A": float(np.median(pos)) if len(pos) else None,
        "S_median_C": float(np.median(neg)) if len(neg) else None,
        "note": "automatic candidate labels; preliminary",
    }
    (OUT / "hv1_summary_v1.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({"delta_detection": {k: {kk: round(vv, 4) if isinstance(vv, float) else vv
                                               for kk, vv in v.items()}
                                            for k, v in summary["delta_detection"].items()},
                       "change_roc": summary["change_roc"]}, indent=1))


if __name__ == "__main__":
    main()

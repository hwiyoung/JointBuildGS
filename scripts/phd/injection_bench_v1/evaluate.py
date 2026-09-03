#!/usr/bin/env python3
"""Injection bench v1 — evaluate the evidence channels on the injected variants against the un-injected baseline and the truth labels.

For every variant: join the variant's T1 cells, T2 cells and pairing top cells with the baseline (prism 2) cells on (ix, iy) and with the
truth cells; report, per truth group (injected / control), the pairing state distribution, dz, the 3D-b ray fractions, the 2D-a statistics
and their paired differences to the baseline; the registration-coherence statistic; the provisional rule reading versus the truth
(confusion matrix); and the pre-registered expectation checks of DESIGN_ko_v1.md §5.  Evidence-level only; no verdict.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any

import numpy as np

from scripts.phd.injection_bench_v1.inject import CELL_KIND, DEFAULT_CONFIG, atomic_json, git_head, load_config, sha256


KIND_NAME = {v: k for k, v in CELL_KIND.items()}
STATE_NAMES = {1: "COMPATIBLE", 2: "PRIOR_ABOVE", 3: "CURRENT_ABOVE", 4: "PRIOR_ONLY", 5: "CURRENT_ONLY"}
READINGS = ("H_C", "H_M_missing", "H_M_biased", "PRIOR_WRONG_OR_DELTA", "ABSTAIN", "OTHER")


def load_run(root: Path, ws: str, task: str) -> Path:
    p = root / f"phase-payloads/phd/{ws}/{task}"
    rc = json.loads((p / "validation_receipt.json").read_text(encoding="utf-8"))
    if any(v != "PASS" for v in rc["checks"].values()) or rc.get("artifact_manifest_sha256") != sha256(p / "artifact_manifest.json"):
        raise RuntimeError(f"{task}: receipt not PASS or not bound")
    return p


def cells_of(root: Path, suffix: str) -> dict[str, np.ndarray]:
    """T1 cells, T2 cells and pairing top cells of one run set (suffix = 'P2' baseline or 'BENCH-V5')."""
    t1 = np.load(load_run(root, "evidence_bank_v1", f"PHD-EVIDENCE-BANK-{suffix}-v1") / "evidence_cells.npy", allow_pickle=False)
    t2 = np.load(load_run(root, "warp_ncc_v1", f"PHD-WARP-NCC-{suffix}-v1") / "warp_ncc_cells.npy", allow_pickle=False)
    pc = np.load(load_run(root, "patch_pairing_xy_v1", f"PHD-PATCH-PAIRING-XY-{suffix}-v1") / "pair_cells.npy", allow_pickle=False)
    top = pc[pc["layer"] == 0]
    if len(t1) != len(t2) or np.any(t1["ix"] != t2["ix"]) or np.any(t1["iy"] != t2["iy"]) or len(top) != len(t1):
        raise RuntimeError(f"{suffix}: T1/T2/pairing cell sets differ")
    return {"t1": t1, "t2": t2, "top": top}


def key_index(cells: np.ndarray) -> dict[tuple[int, int], int]:
    return {(int(ix), int(iy)): i for i, (ix, iy) in enumerate(zip(cells["ix"], cells["iy"]))}


def nanmed(v: np.ndarray) -> float | None:
    v = np.asarray(v, dtype=np.float64); v = v[np.isfinite(v)]
    return float(np.median(v)) if len(v) else None


def nanmean(v: np.ndarray) -> float | None:
    v = np.asarray(v, dtype=np.float64); v = v[np.isfinite(v)]
    return float(np.mean(v)) if len(v) else None


def provisional_reading(t1: np.ndarray, t2: np.ndarray, top: np.ndarray, i: int, margin: float = 0.1) -> str:
    """Hand rule (design D-7 provisional attribution + the T2 sign); a pre-T4 check, not a verdict."""
    tested = int(t1["n_agree"][i] + t1["n_penetrate"][i] + t1["n_block"][i])
    n_m, n_p = int(t2["n_pairs_m"][i]), int(t2["n_pairs_p"][i]); delta = float(t2["delta_median"][i])
    dz = float(top["dz_m"][i]) if np.isfinite(top["dz_m"][i]) else np.nan
    if n_m == 0 and n_p >= 3 and t1["n_no_landing"][i] > tested:
        return "H_M_missing"
    if tested < 20:
        return "ABSTAIN"
    if t1["f_block"][i] >= 0.4 and np.isfinite(delta) and delta <= -margin:
        return "H_M_biased"
    if t1["f_penetrate"][i] >= 0.5 and np.isfinite(delta) and delta >= margin:
        return "PRIOR_WRONG_OR_DELTA"
    if np.isfinite(dz) and abs(dz) <= 0.3 and t1["f_agree"][i] >= 0.6:
        return "H_C"
    return "OTHER"


def truth_reading_target(kind: int) -> str:
    return {0: "H_C", 1: "PRIOR_WRONG_OR_DELTA", 2: "H_M_missing", 3: "H_C", 4: "H_M_biased", 5: "PRIOR_WRONG_OR_DELTA"}[int(kind)]


def group_stats(sel: np.ndarray, t1: np.ndarray, t2: np.ndarray, top: np.ndarray, base_t2: np.ndarray | None, base_map: dict | None) -> dict[str, Any]:
    if not sel.any():
        return {"cells": 0}
    s1, s2, st = t1[sel], t2[sel], top[sel]
    tested = s1["n_agree"] + s1["n_penetrate"] + s1["n_block"]
    out = {
        "cells": int(sel.sum()),
        "state_counts": {STATE_NAMES[k]: int(np.count_nonzero(st["state"] == k)) for k in STATE_NAMES},
        "dz_median": nanmed(st["dz_m"]), "dz_p10": (float(np.nanquantile(st["dz_m"], 0.1)) if np.isfinite(st["dz_m"]).any() else None), "dz_p90": (float(np.nanquantile(st["dz_m"], 0.9)) if np.isfinite(st["dz_m"]).any() else None),
        "rays_tested_sum": int(tested.sum()), "f_agree": (float(s1["n_agree"].sum() / tested.sum()) if tested.sum() else None),
        "f_penetrate": (float(s1["n_penetrate"].sum() / tested.sum()) if tested.sum() else None), "f_block": (float(s1["n_block"].sum() / tested.sum()) if tested.sum() else None),
        "n_no_landing_sum": int(s1["n_no_landing"].sum()), "n_mvs_only_sum": int(s1["n_mvs_only"].sum()),
        "n_pairs_m_median": float(np.median(s2["n_pairs_m"])), "n_pairs_p_median": float(np.median(s2["n_pairs_p"])),
        "power_m_fraction": float(np.mean(s2["power_2da_m"])), "power_p_fraction": float(np.mean(s2["power_2da_p"])),
        "S_M": nanmed(s2["ncc_median_m"]), "S_P": nanmed(s2["ncc_median_p"]), "delta": nanmed(s2["delta_median"]),
        "f_m_over_p": nanmean(s2["f_m_over_p"]), "f_p_over_m": nanmean(s2["f_p_over_m"]),
    }
    if base_t2 is not None and base_map is not None:
        rows = [base_map.get((int(ix), int(iy))) for ix, iy in zip(s2["ix"], s2["iy"])]
        ok = np.array([r is not None for r in rows]); idx = np.array([r if r is not None else 0 for r in rows])
        if ok.any():
            b = base_t2[idx[ok]]; v = s2[ok]
            out["paired_vs_baseline"] = {"cells": int(ok.sum()), "dS_M_median": nanmed(v["ncc_median_m"] - b["ncc_median_m"]),
                                         "dS_P_median": nanmed(v["ncc_median_p"] - b["ncc_median_p"]), "ddelta_median": nanmed(v["delta_median"] - b["delta_median"]),
                                         "baseline_S_M": nanmed(b["ncc_median_m"]), "baseline_S_P": nanmed(b["ncc_median_p"]), "baseline_delta": nanmed(b["delta_median"])}
    return out


def coherence(sel: np.ndarray, top: np.ndarray) -> dict[str, Any]:
    dz = top["dz_m"][sel]; dz = dz[np.isfinite(dz)]
    if len(dz) < 10:
        return {"cells": int(len(dz))}
    sign = np.sign(dz[np.abs(dz) > 0.05])
    return {"cells": int(len(dz)), "dz_mean": float(dz.mean()), "dz_variance": float(dz.var()), "dz_mad": float(np.median(np.abs(dz - np.median(dz)))),
            "sign_agreement": (float(max(np.mean(sign > 0), np.mean(sign < 0))) if len(sign) else None)}


def evaluate(cfg: dict[str, Any]) -> dict[str, Any]:
    root = Path(cfg["artifact_root"]); bench = root / cfg["output_relative_root"]
    base = cells_of(root, "P2"); base_map = key_index(base["t2"])
    base_compat = (base["top"]["state"] == 1) & (base["top"]["rough"] == 0)
    results = {}
    for variant in cfg["variants"]:
        vid = variant["id"]
        vr = cells_of(root, f"BENCH-{vid}")
        truth = np.load(bench / vid / "truth_cells.npy", allow_pickle=False)
        tmap = key_index(truth)
        kinds = np.array([truth["kind"][tmap[(int(ix), int(iy))]] if (int(ix), int(iy)) in tmap else 0 for ix, iy in zip(vr["t1"]["ix"], vr["t1"]["iy"])], dtype=np.uint8)
        # control = baseline-compatible planar cells that were not injected
        in_base_compat = np.array([base_compat[base_map[(int(ix), int(iy))]] if (int(ix), int(iy)) in base_map else False for ix, iy in zip(vr["t1"]["ix"], vr["t1"]["iy"])])
        injected = kinds > 0
        # for whole-tile delta variants the "injected" set is every cell; restrict the reading to baseline-compatible planar cells
        if variant["kind"] == "als_shift_all":
            injected = injected & in_base_compat
        control = in_base_compat & ~injected
        groups = {"injected": group_stats(injected, vr["t1"], vr["t2"], vr["top"], base["t2"], base_map),
                  "control": group_stats(control, vr["t1"], vr["t2"], vr["top"], base["t2"], base_map)}
        # missing cells: baseline compatible cells that vanished from the variant's top layer (e.g. MVS deleted and no ALS either)
        vkeys = set(key_index(vr["t1"]))
        vanished = int(sum(1 for (k, i) in base_map.items() if base_compat[i] and k not in vkeys))
        # provisional reading confusion
        confusion = {r: {t: 0 for t in READINGS} for r in ("truth_injected", "truth_control")}
        for i in np.flatnonzero(injected | control):
            reading = provisional_reading(vr["t1"], vr["t2"], vr["top"], int(i))
            confusion["truth_injected" if injected[i] else "truth_control"][reading] += 1
        target = truth_reading_target(int(kinds[injected].max())) if injected.any() else None
        results[vid] = {"variant": variant, "cells_total": int(len(vr["t1"])), "cells_injected": int(injected.sum()), "cells_control": int(control.sum()),
                        "baseline_compatible_cells_vanished": vanished, "groups": groups,
                        "coherence_injected": coherence(injected, vr["top"]), "coherence_control": coherence(control, vr["top"]),
                        "reading_confusion": confusion, "reading_target": target,
                        "reading_hit_rate": (float(confusion["truth_injected"][target] / max(1, injected.sum())) if target else None)}
    return {"baseline_compatible_planar_cells": int(base_compat.sum()), "variants": results}


def expectation_checks(res: dict[str, Any]) -> dict[str, Any]:
    v = res["variants"]
    def g(vid, grp, key):
        return v.get(vid, {}).get("groups", {}).get(grp, {}).get(key)
    checks = {}
    checks["(a) V7 BLOCK dominant and delta < 0"] = None if g("V7", "injected", "f_block") is None else bool(g("V7", "injected", "f_block") >= 0.4 and (g("V7", "injected", "delta") or 0) < 0)
    checks["(a) V8 PENETRATE dominant and delta > 0"] = None if g("V8", "injected", "f_penetrate") is None else bool(g("V8", "injected", "f_penetrate") >= 0.5 and (g("V8", "injected", "delta") or 0) > 0)
    checks["(b) V5 n_pairs_m = 0 and NO_LANDING dominant"] = None if g("V5", "injected", "n_pairs_m_median") is None else bool(g("V5", "injected", "n_pairs_m_median") == 0 and g("V5", "injected", "n_no_landing_sum") > g("V5", "injected", "rays_tested_sum"))
    checks["(b) V5 S_P >= 0.6"] = None if g("V5", "injected", "S_P") is None else bool(g("V5", "injected", "S_P") >= 0.6)
    checks["(c) V1 compatible cells read as PRIOR_ABOVE (majority)"] = None if not v.get("V1") else bool(v["V1"]["groups"]["injected"]["state_counts"]["PRIOR_ABOVE"] > 0.5 * v["V1"]["groups"]["injected"]["cells"])
    checks["(c) V1 PENETRATE >= 0.5 and delta > 0"] = None if g("V1", "injected", "f_penetrate") is None else bool(g("V1", "injected", "f_penetrate") >= 0.5 and (g("V1", "injected", "delta") or 0) > 0)
    coh = v.get("V2", {}).get("coherence_injected", {})
    checks["(c) V2 dz coherent (variance <= 0.1, sign >= 0.95)"] = None if coh.get("dz_variance") is None else bool(coh["dz_variance"] <= 0.1 and (coh.get("sign_agreement") or 0) >= 0.95)
    coh8 = v.get("V8", {}).get("coherence_control", {})
    checks["(c) V8 outside patches stays compatible (|dz mean| <= 0.15)"] = None if coh8.get("dz_mean") is None else bool(abs(coh8["dz_mean"]) <= 0.15)
    checks["(d) V4 horizontal shift unobservable on ground (|dz| <= 0.15, |delta| <= 0.1)"] = None if g("V4", "injected", "dz_median") is None else bool(abs(g("V4", "injected", "dz_median")) <= 0.15 and abs(g("V4", "injected", "delta") or 0) <= 0.1)
    return {"checks": checks, "met": int(sum(1 for c in checks.values() if c is True)), "total": int(sum(1 for c in checks.values() if c is not None))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    cfg = load_config(args.config.resolve())
    started = time.perf_counter()
    res = evaluate(cfg)
    checks = expectation_checks(res)
    out = Path(cfg["artifact_root"]) / cfg["output_relative_root"]
    doc = {"schema": "jointbuildgs.phd.injection_bench.evaluation.v1", "task_id": cfg["task_id"], "generated_utc": datetime.now(timezone.utc).isoformat(),
           "git_commit": git_head(), "config": {"path": str(args.config.resolve()), "sha256": sha256(args.config.resolve())},
           "evaluator": {"path": str(Path(__file__)), "sha256": sha256(Path(__file__))}, "expectations_before_run": cfg["expectations_before_run"],
           "expectation_checks": checks, "results": res, "elapsed_seconds": time.perf_counter() - started, "prohibited_inputs_accessed": [], "scientific_verdict": None}
    atomic_json(out / "bench_evaluation.json", doc)
    print(json.dumps(checks, indent=1))
    for vid, r in res["variants"].items():
        gi, gc = r["groups"]["injected"], r["groups"]["control"]
        print(f"{vid} {r['variant']['kind']:20s} inj {r['cells_injected']:4d} ctl {r['cells_control']:4d} | inj dz {gi.get('dz_median')} A/P/B {gi.get('f_agree')}/{gi.get('f_penetrate')}/{gi.get('f_block')} S_M {gi.get('S_M')} S_P {gi.get('S_P')} Δ {gi.get('delta')} | reading hit {r['reading_hit_rate']}")


if __name__ == "__main__":
    main()

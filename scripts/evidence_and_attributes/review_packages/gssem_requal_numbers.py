#!/usr/bin/env python3
"""P2 gssem re-qual — snapshot headline numbers for D/D4 from CURRENT on-disk read-out (READ-ONLY).
Usage: gssem_requal_numbers.py <label:smrf|gssem> <out.json>
Reads current disk: target-only facets (Roofer cityjson), val3dity codes (per-building report),
assembled/valid-solid (eval JSON for the label), RMS->ref (ref_rms_{D,d4}_<label>.csv).
Run BEFORE regen (label=smrf) and AFTER regen (label=gssem). Observation only.
"""
import sys, csv, glob, json
from pathlib import Path

label, outp = sys.argv[1], sys.argv[2]
suite = sys.argv[3] if len(sys.argv) > 3 else "DD4"   # DD4 (PART1) | D5 (PART2)
REPO = Path(__file__).resolve().parents[3]
M = REPO / "results/tum_transfer/mob"
A = REPO / "results/tum_transfer/mob_analysis"
EVALROOT = REPO / "phases/p0-audit/runs/mob_eval"
TARGETS = ["4906972", "4907182", "4906969", "4908023", "4907510", "42364659",
           "42364663", "42364609", "4908050", "4908166", "4908176"]
RECOVERY = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050", "4908166", "4908176"]
RMS_FOCUS = ["4906972", "4906969", "4908023"]
if suite == "D5":
    ARMS = {"D5a": ["gs_d5a_dense", "gs_d5a_acmp"], "D5b": ["gs_d5b_dense", "gs_d5b_acmp"],
            "D5c": ["gs_d5c_dense", "gs_d5c_acmp"]}
    EVALJSON = {(a, "gssem"): "eval_d5_gssem.json" for a in ARMS}
    EVALJSON.update({(a, "smrf"): "eval_d5_smrf.json" for a in ARMS})
    RMSCSV = {a: f"ref_rms_d5_{label}.csv" for a in ARMS}
else:
    ARMS = {"D": ["gs_prior_full_dense", "gs_prior_full_acmp"], "D4": ["gs_d4_dense", "gs_d4_acmp"]}
    EVALJSON = {("D", "gssem"): "eval_prior_full_gssem.json", ("D", "smrf"): "eval_prior_full_smrf.json",
                ("D4", "gssem"): "eval_d4_gssem.json", ("D4", "smrf"): "eval_d4_smrf.json"}
    RMSCSV = {"D": f"ref_rms_D_{label}.csv", "D4": f"ref_rms_d4_{label}.csv"}


def load_eval(fn):
    p = M / fn; d = {}
    if p.exists():
        for r in json.loads(p.read_text()):
            d[(r["config"], r["bid"], r.get("tag", "orig"))] = r
    return d


def load_rms(fn):
    p = A / fn; d = {}
    if p.exists():
        for r in csv.DictReader(open(p)):
            try:
                d[(r["config"], r["bid"], r.get("tag", "orig"))] = float(r["rms_to_ref_m"])
            except (TypeError, ValueError, KeyError):
                d[(r["config"], r["bid"], r.get("tag", "orig"))] = None
    return d


def target_roofs(cfg, bid):
    full = f"DEBY_LOD2_{bid}"
    g = glob.glob(str(EVALROOT / cfg / f"roofer_{full}_orig" / "*.city.jsonl"))
    if not g:
        return None
    n = 0
    for ln in open(g[0]):
        if not ln.strip():
            continue
        for cid, o in json.loads(ln).get("CityObjects", {}).items():
            if cid == full or cid.startswith(full + "-"):
                for geom in o.get("geometry", []):
                    for s in geom.get("semantics", {}).get("surfaces", []):
                        if s.get("type") == "RoofSurface":
                            n += 1
    return n


def val_codes(cfg, bid):
    f = glob.glob(str(EVALROOT / cfg / f"DEBY_LOD2_{bid}_orig_val3dity.json"))
    if not f:
        return None
    d = json.loads(Path(f[0]).read_text())
    codes = []
    def add(errs):
        for e in errs or []:
            if isinstance(e, dict):
                codes.append(str(e.get("code", e.get("type", "?"))))
            else:
                codes.append(str(e))
    add(d.get("all_errors")); add(d.get("dataset_errors"))
    for ft in d.get("features", []):
        add(ft.get("errors"))
    return {"valid": d.get("validity"), "codes": sorted(set(codes))}


def assembled(r):
    return bool(r and r.get("roofer_ok") and (r.get("roof_surfaces") or 0) > 0)


def valid_solid(r):
    return bool(r and r.get("val3dity_valid") and (r.get("roof_surfaces") or 0) > 0)


out = {"label": label, "arms": {}}
for arm, cfgs in ARMS.items():
    ev = load_eval(EVALJSON[(arm, label)]); rms = load_rms(RMSCSV[arm])
    for cfg in cfgs:
        facets = {t: target_roofs(cfg, t) for t in TARGETS}
        rv = [rms.get((cfg, f"DEBY_LOD2_{t}", "orig")) for t in TARGETS]
        rv = [x for x in rv if x is not None]
        out["arms"][cfg] = {
            "arm": arm,
            "facets_target_only": facets,
            "rms_mean": (sum(rv) / len(rv)) if rv else None,
            "rms_n": len(rv),
            "rms_focus": {t: rms.get((cfg, f"DEBY_LOD2_{t}", "orig")) for t in RMS_FOCUS},
            "assembled_REC": sum(assembled(ev.get((cfg, f"DEBY_LOD2_{t}", "orig"))) for t in RECOVERY),
            "valid_solid_REC": sum(valid_solid(ev.get((cfg, f"DEBY_LOD2_{t}", "orig"))) for t in RECOVERY),
            "val3dity": {t: val_codes(cfg, t) for t in TARGETS},
        }
Path(outp).write_text(json.dumps(out, indent=1))
print(f"[{label}] wrote {outp}: arms={list(out['arms'])}")

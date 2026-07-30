#!/usr/bin/env python3
"""P2-D 전체 prior 수트 — Phase 4 two-axis table (HOST, observation only; verdict = human).

Consolidates the D arms (gs_prior_full_{dense,acmp}) under BOTH read-outs (gssem = Lever-3
GS-semantic; smrf = control, isolates the training-prior effect) against v6-protect, raw/LiDAR,
and reference. Two axes:
  A) quality/accuracy: roof_surfaces vs ref (over-seg), val3dity valid, RMS->ref (toward LiDAR)
  B) generation: assembled (roofer roof>0) + valid-solid on the 8 v6-assembly-failed recovery bldgs
  C) no-degradation: control bldgs 4906972/4908023 vs v6
Inputs (results/tum_transfer/mob*): eval_prior_full_{gssem,smrf}.json, eval_v6_protect.json,
eval_v6_raw.json, baselines.json, mob_analysis/ref_rms_{D,protect,v6}.csv. Writes REPORT_D + csv.
"""
import csv, json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M = REPO / "results/tum_transfer/mob"
A = REPO / "results/tum_transfer/mob_analysis"
TARGETS = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050",
           "4908166", "4908176", "4906969", "4908023", "4906972"]
RECOVERY = {"42364609", "42364659", "42364663", "4907182", "4907510", "4908050", "4908166", "4908176"}
CTRL = {"4906972", "4908023"}


def load_eval(f):
    d = {}
    p = M / f
    if p.exists():
        for r in json.loads(p.read_text()):
            d[(r["config"], r["bid"], r.get("tag", "orig"))] = r
    return d


def load_rms(f):
    d = {}
    p = A / f
    if p.exists():
        for r in csv.DictReader(open(p)):
            v = r.get("rms_to_ref_m") or r.get("rms_to_ref")
            try:
                v = float(v)
            except (TypeError, ValueError):
                v = None
            d[(r["config"], r["bid"], r.get("tag", "orig"))] = v
    return d


def assembled(r):
    return bool(r and r.get("roofer_ok") and (r.get("roof_surfaces") or 0) > 0)


def valid_solid(r):
    return bool(r and r.get("val3dity_valid") and (r.get("roof_surfaces") or 0) > 0)


def main():
    G = load_eval("eval_prior_full_gssem.json")
    S = load_eval("eval_prior_full_smrf.json")
    V = load_eval("eval_v6_protect.json")
    R = load_eval("eval_v6_raw.json")
    base = json.loads((M / "baselines.json").read_text())
    rmsD = load_rms("ref_rms_D.csv")
    rmsV = load_rms("ref_rms_protect.csv")
    rms6 = load_rms("ref_rms_v6.csv")

    arms = [
        ("D_dense_gssem", G, "gs_prior_full_dense", rmsD),
        ("D_acmp_gssem", G, "gs_prior_full_acmp", rmsD),
        ("D_dense_smrf", S, "gs_prior_full_dense", rmsD),
        ("D_acmp_smrf", S, "gs_prior_full_acmp", rmsD),
        ("v6_dense", V, "gs_seed_dense_protect", rmsV),
        ("v6_acmp", V, "gs_seed_acmp_protect", rmsV),
        ("raw_dense", R, "raw_dense", rms6),
        ("lidar", R, "raw_lidar", rms6),
    ]

    lines = []
    def out(s=""):
        lines.append(s); print(s)

    out("# P2-D 전체 prior 수트 — Phase 4 (관찰만, 판정=사람)\n")
    # B axis summary
    out("## B) 생성 (8 recovery bldgs, tag=orig): assembled / valid-solid / mean RMS→ref")
    out(f"{'arm':>15} | {'assembled/8':>11} | {'valid-solid/8':>13} | {'meanRMS(REC)':>12}")
    for label, d, cfg, rms in arms:
        asm = sum(assembled(d.get((cfg, f"DEBY_LOD2_{t}", "orig"))) for t in RECOVERY)
        val = sum(valid_solid(d.get((cfg, f"DEBY_LOD2_{t}", "orig"))) for t in RECOVERY)
        rv = [rms.get((cfg, f"DEBY_LOD2_{t}", "orig")) for t in RECOVERY]
        rv = [x for x in rv if x is not None]
        mr = f"{sum(rv)/len(rv):.2f}(n{len(rv)})" if rv else "-"
        out(f"{label:>15} | {asm:>11} | {val:>13} | {mr:>12}")

    # A axis: facet vs ref + RMS, per building (gssem + smrf vs v6)
    out("\n## A) 품질: roof_surfaces (+valid) & RMS→ref(m), tag=orig  [cell: facets v/./x | rms]")
    hdr = f"{'bid':>9} {'set':>3} {'ref':>3} | {'Dd_gssem':>9} {'Dd_smrf':>8} {'v6_dense':>8} | {'Dd_RMS':>6} {'v6_RMS':>6} {'lidarRMS':>8}"
    out(hdr)
    def fc(d, cfg, t):
        r = d.get((cfg, f"DEBY_LOD2_{t}", "orig"))
        if not r:
            return "  -"
        s = r.get("roof_surfaces"); v = r.get("val3dity_valid")
        return f"{(s if s is not None else '?')}{'v' if v else ('.' if v is not None else 'x')}"
    def fr(rms, cfg, t):
        v = rms.get((cfg, f"DEBY_LOD2_{t}", "orig")); return f"{v:.2f}" if v is not None else " -"
    for t in TARGETS:
        st = "REC" if t in RECOVERY else ("CTL" if t in CTRL else "")
        ref = base[f"DEBY_LOD2_{t}"]["ref_roof_surfaces"]
        out(f"{t:>9} {st:>3} {ref:>3} | {fc(G,'gs_prior_full_dense',t):>9} {fc(S,'gs_prior_full_dense',t):>8} "
            f"{fc(V,'gs_seed_dense_protect',t):>8} | {fr(rmsD,'gs_prior_full_dense',t):>6} "
            f"{fr(rmsV,'gs_seed_dense_protect',t):>6} {fr(rms6,'raw_lidar',t):>8}")

    # over-seg means
    out("\n## C) 무열화/과분할: mean|facets-ref| (assembled, orig) & mean RMS→ref(all)")
    import statistics as stt
    for label, d, cfg, rms in arms:
        exc = []
        for t in TARGETS:
            r = d.get((cfg, f"DEBY_LOD2_{t}", "orig"))
            if assembled(r):
                exc.append(abs(r["roof_surfaces"] - base[f"DEBY_LOD2_{t}"]["ref_roof_surfaces"]))
        rv = [rms.get((cfg, f"DEBY_LOD2_{t}", "orig")) for t in TARGETS]
        rv = [x for x in rv if x is not None]
        oseg = f"{stt.mean(exc):.1f}(n{len(exc)})" if exc else "-"
        mr = f"{stt.mean(rv):.2f}(n{len(rv)})" if rv else "-"
        out(f"{label:>15}: over-seg |Δfacet|={oseg:>9}   meanRMS={mr}")

    (M / "REPORT_D.md").write_text("\n".join(lines) + "\n")
    print(f"\n[done] -> {M/'REPORT_D.md'}")


if __name__ == "__main__":
    main()

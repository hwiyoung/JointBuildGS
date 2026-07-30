#!/usr/bin/env python3
"""P2-D5 — cp-ablation comparison table (HOST, observation only; verdict=human).

Mirrors d4_table.py aggregation (assembled / valid_solid / over-seg / RMS defs) for the D5 cp ladder:
  D5a (cp off) / D4 (cp fair, REUSED) / D5c (cp early) / D5b (cp hard), dense+acmp, gssem read-out,
  vs v6 / image(raw) / LiDAR / ref.  Focus = composite multi-roof {42364663,42364659}, curved {4906969},
  flat {4906972,4907182}, control {4908023} — the §5/§6 measurements (over-seg, RMS->ref over-flatten watch).
NOTE: roof_surfaces here is the eval CLIP count (neighbor-contaminated, W_D4 §7). The pre-registered
measurement is TARGET-ONLY facets (d5_target_facets.py) — this table is the generation/RMS/solid view +
clip-facet context. Inputs: eval_d5_gssem.json, eval_d4_gssem.json, eval_prior_full_gssem.json,
eval_v6_protect.json, eval_v6_raw.json, baselines.json, ref_rms_{d5,d4,D,v6,raw}.csv (mob_analysis).
"""
import csv, json, statistics as stt
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M = REPO / "results/tum_transfer/mob"
A = REPO / "results/tum_transfer/mob_analysis"
TARGETS = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050",
           "4908166", "4908176", "4906969", "4908023", "4906972"]
RECOVERY = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050", "4908166", "4908176"]
COMPOSITE = ["42364663", "42364659"]   # multi-roof composite (cp over-seg focus)
CURVED = ["4906969"]                    # curved roof (over-flatten watch)
FLAT = ["4906972", "4907182"]          # flat roofs
CTRL = ["4908023"]                      # control


def load_eval(f):
    d = {}
    p = M / f
    if p.exists():
        for r in json.loads(p.read_text()):
            d[(r["config"], r["bid"], r.get("tag", "orig"))] = r
    return d


def load_rms_into(d, f):
    p = A / f
    if not p.exists():
        return d
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
    D5 = load_eval("eval_d5_gssem.json")
    D4 = load_eval("eval_d4_gssem.json")
    DG = load_eval("eval_prior_full_gssem.json")
    V = load_eval("eval_v6_protect.json")
    R = load_eval("eval_v6_raw.json")
    base = json.loads((M / "baselines.json").read_text())
    RMS = {}
    for f in ["ref_rms_d5.csv", "ref_rms_d4.csv", "ref_rms_D.csv", "ref_rms_v6.csv", "ref_rms_raw.csv"]:
        load_rms_into(RMS, f)

    # cp ladder (off -> fair=D4 -> early -> hard), dense then acmp
    ladder = [
        ("D5a_off_dn",  D5, "gs_d5a_dense"), ("D4_fair_dn", D4, "gs_d4_dense"),
        ("D5c_early_dn", D5, "gs_d5c_dense"), ("D5b_hard_dn", D5, "gs_d5b_dense"),
        ("D5a_off_ac",  D5, "gs_d5a_acmp"), ("D4_fair_ac", D4, "gs_d4_acmp"),
        ("D5c_early_ac", D5, "gs_d5c_acmp"), ("D5b_hard_ac", D5, "gs_d5b_acmp"),
        ("v6_dense", V, "gs_seed_dense_protect"), ("img_dense", R, "raw_dense"), ("LiDAR", R, "raw_lidar"),
    ]

    lines = []
    def out(s=""):
        lines.append(s); print(s)

    def gen_row(label, d, cfg):
        asm = sum(assembled(d.get((cfg, f"DEBY_LOD2_{t}", "orig"))) for t in RECOVERY)
        val = sum(valid_solid(d.get((cfg, f"DEBY_LOD2_{t}", "orig"))) for t in RECOVERY)
        rv = [RMS.get((cfg, f"DEBY_LOD2_{t}", "orig")) for t in RECOVERY]
        rv = [x for x in rv if x is not None]
        mr = f"{sum(rv)/len(rv):.2f}(n{len(rv)})" if rv else "-"
        return f"{label:>14} | {asm:>11} | {val:>13} | {mr:>12}"

    out("# P2-D5 — cp ablation comparison (관찰만, 판정=사람)\n")
    out("## Axis B — 생성 (8 recovery bldgs, tag=orig): assembled / valid-solid / meanRMS→ref")
    out(f"{'arm':>14} | {'assembled/8':>11} | {'valid-solid/8':>13} | {'meanRMS(REC)':>12}")
    for label, d, cfg in ladder:
        out(gen_row(label, d, cfg))

    def fc(d, cfg, t):
        r = d.get((cfg, f"DEBY_LOD2_{t}", "orig")) if d else None
        if not r:
            return "  -"
        s = r.get("roof_surfaces"); v = r.get("val3dity_valid")
        return f"{(s if s is not None else '?')}{'v' if v else ('.' if v is not None else 'x')}"

    def fr(cfg, t):
        v = RMS.get((cfg, f"DEBY_LOD2_{t}", "orig")); return f"{v:.2f}" if v is not None else " -"

    # Axis A: per-building over the cp ladder (clip facet + valid | RMS), focus buildings
    out("\n## Axis A — focus per-building [facet=CLIP roof_surfaces+valid (target-only=d5_target_facets.py); RMS→ref]")
    cpcols = [("off", D5, "gs_d5a_dense"), ("fair", D4, "gs_d4_dense"),
              ("early", D5, "gs_d5c_dense"), ("hard", D5, "gs_d5b_dense"), ("LiD", R, "raw_lidar")]
    hdr = f"{'bid':>9} {'set':>5} {'ref':>3} | " + " ".join(f"{n:>6}" for n, _, _ in cpcols) + \
          " | RMS " + " ".join(f"{n:>5}" for n, _, _ in cpcols)
    out(hdr)
    focus = [(t, "comp") for t in COMPOSITE] + [(t, "curv") for t in CURVED] + \
            [(t, "flat") for t in FLAT] + [(t, "ctrl") for t in CTRL]
    for t, st in focus:
        ref = base[f"DEBY_LOD2_{t}"]["ref_roof_surfaces"]
        fcells = " ".join(f"{fc(d, c, t):>6}" for _, d, c in cpcols)
        rcells = " ".join(f"{fr(c, t):>5}" for _, _, c in cpcols)
        out(f"{t:>9} {st:>5} {ref:>3} | {fcells} | RMS {rcells}")

    # Axis C: over-seg + meanRMS per cp arm (assembled, all targets) — clip metric
    out("\n## Axis C — over-seg mean|CLIPfacet-ref| & meanRMS→ref (all targets, assembled,orig)")
    for label, d, cfg in ladder:
        exc = []
        for t in TARGETS:
            r = d.get((cfg, f"DEBY_LOD2_{t}", "orig"))
            if assembled(r):
                exc.append(abs(r["roof_surfaces"] - base[f"DEBY_LOD2_{t}"]["ref_roof_surfaces"]))
        rv = [RMS.get((cfg, f"DEBY_LOD2_{t}", "orig")) for t in TARGETS]
        rv = [x for x in rv if x is not None]
        oseg = f"{stt.mean(exc):.1f}(n{len(exc)})" if exc else "-"
        mr = f"{stt.mean(rv):.2f}(n{len(rv)})" if rv else "-"
        out(f"{label:>14}: over-seg|Δfacet|(clip)={oseg:>9}  meanRMS={mr}")

    (M / "REPORT_D5.md").write_text("\n".join(lines) + "\n")
    print(f"\n[done] -> {M/'REPORT_D5.md'}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""P2-D4 — 8-way two-axis table (HOST, observation only; verdict=human).

Mirrors d_prior_full_table.py aggregation (same assembled/valid_solid/over-seg defs) but adds the
D4 arms (gs_d4_{dense,acmp}, gssem read-out) and builds the user's 8-way comparison:
  {image pointcloud, GS pointcloud} x {sparse, dense, acmp} + LiDAR + ref,  decision cells = dense/acmp,
  with the v6 -> D -> D4 GS progression side by side.
Axes: B) generation (assembled/8 + valid-solid/8 + meanRMS over the 8 recovery bldgs, tag=orig),
      A) quality (roof_surfaces vs ref over-seg + RMS->ref + valid-solid), C) no-degradation (controls).
Inputs (results/tum_transfer/mob* + mob_analysis): eval_d4_gssem.json, eval_prior_full_gssem.json,
eval_v6_protect.json, eval_v6_raw.json, baselines.json, ref_rms_{d4,D,v6,raw,protect}.csv.
"""
import csv, json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M = REPO / "results/tum_transfer/mob"
A = REPO / "results/tum_transfer/mob_analysis"
TARGETS = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050",
           "4908166", "4908176", "4906969", "4908023", "4906972"]
RECOVERY = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050", "4908166", "4908176"]
CTRL = ["4906972", "4908023"]
FLAT = ["4906972", "4907182"]          # flat roofs
CURVED = ["4906969"]                    # curved roof


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
    D4 = load_eval("eval_d4_gssem.json")
    DG = load_eval("eval_prior_full_gssem.json")
    V = load_eval("eval_v6_protect.json")
    R = load_eval("eval_v6_raw.json")
    base = json.loads((M / "baselines.json").read_text())
    RMS = {}
    for f in ["ref_rms_d4.csv", "ref_rms_D.csv", "ref_rms_v6.csv", "ref_rms_raw.csv", "ref_rms_protect.csv"]:
        load_rms_into(RMS, f)

    # 8-way arms (+ progression). (label, eval_dict, config, density_role)
    eightway = [
        ("img_sparse", R, "raw_sparse"), ("img_dense", R, "raw_dense"), ("img_acmp", R, "raw_acmp"),
        ("GS_sparse*", None, None),  # D4 sparse not trained
        ("GS_dense(D4)", D4, "gs_d4_dense"), ("GS_acmp(D4)", D4, "gs_d4_acmp"),
        ("LiDAR", R, "raw_lidar"),
    ]
    progression = [
        ("v6_dense", V, "gs_seed_dense_protect"), ("D_dense", DG, "gs_prior_full_dense"), ("D4_dense", D4, "gs_d4_dense"),
        ("v6_acmp", V, "gs_seed_acmp_protect"), ("D_acmp", DG, "gs_prior_full_acmp"), ("D4_acmp", D4, "gs_d4_acmp"),
    ]

    lines = []
    def out(s=""):
        lines.append(s); print(s)

    def gen_row(label, d, cfg):
        if d is None:
            return f"{label:>14} | {'(not trained)':>11} | {'-':>13} | {'-':>12}"
        asm = sum(assembled(d.get((cfg, f"DEBY_LOD2_{t}", "orig"))) for t in RECOVERY)
        val = sum(valid_solid(d.get((cfg, f"DEBY_LOD2_{t}", "orig"))) for t in RECOVERY)
        rv = [RMS.get((cfg, f"DEBY_LOD2_{t}", "orig")) for t in RECOVERY]
        rv = [x for x in rv if x is not None]
        mr = f"{sum(rv)/len(rv):.2f}(n{len(rv)})" if rv else "-"
        return f"{label:>14} | {asm:>11} | {val:>13} | {mr:>12}"

    out("# P2-D4 — 8-way two-axis (관찰만, 판정=사람)\n")
    out("## Axis B — 생성 (8 recovery bldgs, tag=orig): assembled / valid-solid / meanRMS→ref")
    out(f"{'arm':>14} | {'assembled/8':>11} | {'valid-solid/8':>13} | {'meanRMS(REC)':>12}")
    out("# --- 8-way ---")
    for label, d, cfg in eightway:
        out(gen_row(label, d, cfg))
    out("# --- GS progression v6->D->D4 ---")
    for label, d, cfg in progression:
        out(gen_row(label, d, cfg))

    # Axis A: per-building facet(roof_surf) + valid + RMS  (img_dense, D4_dense, D_dense, LiDAR, ref)
    out("\n## Axis A — 품질 per-building (tag=orig)  [facet=roof_surfaces; v=val3dity valid]")
    out(f"{'bid':>9} {'set':>4} {'ref':>3} | {'img_dn':>7} {'D_dn':>6} {'D4_dn':>6} {'D4_ac':>6} {'LiD':>5} | "
        f"{'imgRMS':>6} {'D4dRMS':>6} {'D4aRMS':>6} {'LiDRMS':>6}")

    def fc(d, cfg, t):
        r = d.get((cfg, f"DEBY_LOD2_{t}", "orig")) if d else None
        if not r:
            return "  -"
        s = r.get("roof_surfaces"); v = r.get("val3dity_valid")
        return f"{(s if s is not None else '?')}{'v' if v else ('.' if v is not None else 'x')}"

    def fr(cfg, t):
        v = RMS.get((cfg, f"DEBY_LOD2_{t}", "orig")); return f"{v:.2f}" if v is not None else " -"

    for t in TARGETS:
        st = "REC" if t in RECOVERY else ("FLAT/CTL" if t in CTRL else ("CURV" if t in CURVED else ""))
        ref = base[f"DEBY_LOD2_{t}"]["ref_roof_surfaces"]
        out(f"{t:>9} {st:>4} {ref:>3} | {fc(R,'raw_dense',t):>7} {fc(DG,'gs_prior_full_dense',t):>6} "
            f"{fc(D4,'gs_d4_dense',t):>6} {fc(D4,'gs_d4_acmp',t):>6} {fc(R,'raw_lidar',t):>5} | "
            f"{fr('raw_dense',t):>6} {fr('gs_d4_dense',t):>6} {fr('gs_d4_acmp',t):>6} {fr('raw_lidar',t):>6}")

    # Axis C: over-seg + meanRMS per arm; + control/flat/curved focus
    out("\n## Axis C — over-seg mean|roof_surf-ref| (assembled,orig) & meanRMS→ref(all targets)")
    import statistics as stt
    allarms = [("img_dense", R, "raw_dense"), ("img_acmp", R, "raw_acmp"),
               ("v6_dense", V, "gs_seed_dense_protect"), ("D_dense", DG, "gs_prior_full_dense"),
               ("D4_dense", D4, "gs_d4_dense"), ("D4_acmp", D4, "gs_d4_acmp"), ("LiDAR", R, "raw_lidar")]
    for label, d, cfg in allarms:
        exc = []
        for t in TARGETS:
            r = d.get((cfg, f"DEBY_LOD2_{t}", "orig"))
            if assembled(r):
                exc.append(abs(r["roof_surfaces"] - base[f"DEBY_LOD2_{t}"]["ref_roof_surfaces"]))
        rv = [RMS.get((cfg, f"DEBY_LOD2_{t}", "orig")) for t in TARGETS]
        rv = [x for x in rv if x is not None]
        oseg = f"{stt.mean(exc):.1f}(n{len(exc)})" if exc else "-"
        mr = f"{stt.mean(rv):.2f}(n{len(rv)})" if rv else "-"
        out(f"{label:>11}: over-seg|Δfacet|={oseg:>9}  meanRMS={mr}")

    out("\n## Focus — flat {4906972,4907182} / curved {4906969} / control {4908023}: facet | RMS  (D4_dn / D_dn / v6_dn / LiD / ref)")
    for t in FLAT + CURVED + ["4908023"]:
        ref = base[f"DEBY_LOD2_{t}"]["ref_roof_surfaces"]
        cat = "flat" if t in FLAT else ("curved" if t in CURVED else "control")
        out(f"  {t} [{cat}] ref={ref} facet: D4={fc(D4,'gs_d4_dense',t)} D={fc(DG,'gs_prior_full_dense',t)} "
            f"v6={fc(V,'gs_seed_dense_protect',t)} LiD={fc(R,'raw_lidar',t)} | "
            f"RMS: D4={fr('gs_d4_dense',t)} D={fr('gs_prior_full_dense',t)} v6={fr('gs_seed_dense_protect',t)} LiD={fr('raw_lidar',t)}")

    (M / "REPORT_D4.md").write_text("\n".join(lines) + "\n")
    print(f"\n[done] -> {M/'REPORT_D4.md'}")


if __name__ == "__main__":
    main()

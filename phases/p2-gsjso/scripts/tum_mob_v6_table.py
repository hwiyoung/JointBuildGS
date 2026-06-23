#!/usr/bin/env python3
"""P2 make-or-break v6 — assemble the 8-way table (Phase 4). Observation only; verdict = human.

8 constructions per building (11 targets): GS arm gs_seed_{sparse,dense,acmp} + raw arm
raw_{sparse,dense,acmp,lidar} + reference (LoD2 GT). Per cell:
  RoofSurface count | plane RMS->ref (m) | val3dity valid | solid (assembly success)

Inputs (host): eval_v6.json (GS), eval_v6_raw.json (raw), ref_rms_v6.csv (RMS->ref per arm/bid/tag),
baselines.json (ref_roof_surfaces). Writes REPORT_v6.md + table_v6.csv. No verdict — numbers only.
"""
import argparse, csv, json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "results/tum_transfer/mob"
TARGETS = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050",
           "4908166", "4908176", "4906969", "4908023", "4906972"]
RECOVERY = {"42364609", "42364659", "42364663", "4907182", "4907510", "4908050", "4908166", "4908176"}
GS_ARMS = ["gs_seed_sparse", "gs_seed_dense", "gs_seed_acmp"]
RAW_ARMS = ["raw_sparse", "raw_dense", "raw_acmp", "raw_lidar"]
ARMS = GS_ARMS + RAW_ARMS


def load_eval(paths):
    rows = {}
    for p in paths:
        if not Path(p).exists():
            continue
        for r in json.loads(Path(p).read_text()):
            rows[(r["config"], r["bid"], r.get("tag", "orig"))] = r
    return rows


def load_refrms(path):
    m = {}
    if Path(path).exists():
        for r in csv.DictReader(open(path)):
            v = r.get("rms_to_ref_m")
            m[(r["config"], r["bid"], r["tag"])] = (float(v) if v not in (None, "", "None") else None)
    return m


def fmt(x, nd=2):
    return "-" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def solid_of(r):
    if not r or r.get("error") or not r.get("roofer_ok"):
        return False
    rs = r.get("roof_surfaces")
    return bool(rs and rs > 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="matched", choices=["matched", "orig"],
                    help="density variant for the headline table (ALS-density-matched by default)")
    A = ap.parse_args()
    ev = load_eval([OUT / "eval_v6.json", OUT / "eval_v6_raw.json"])
    rr = load_refrms(REPO / "results/tum_transfer/mob_analysis/ref_rms_v6.csv")
    base = json.loads((OUT / "baselines.json").read_text())

    lines = [f"# P2 make-or-break v6 — 8-way (tag={A.tag}). Observation only; verdict = 김휘영.\n",
             "Per building: RoofSurface count / RMS->ref(m) / val3dity / solid. "
             "ref = LoD2 GT facet count.\n"]
    csv_rows = []
    # per-arm tallies
    tally = {a: {"solid": 0, "rms": [], "facet_close": 0, "n": 0} for a in ARMS}

    for t in TARGETS:
        bid = f"DEBY_LOD2_{t}"
        ref_roof = base.get(bid, {}).get("ref_roof_surfaces")
        tag = "[R]" if t in RECOVERY else "[Q]"
        lines.append(f"\n## {t} {tag}  (ref RoofSurface={ref_roof})")
        lines.append("| arm | RoofSurf | RMS->ref(m) | val3dity | solid |")
        lines.append("|---|---:|---:|:---:|:---:|")
        for a in ARMS:
            r = ev.get((a, bid, A.tag))
            rms = rr.get((a, bid, A.tag))
            rs = r.get("roof_surfaces") if r else None
            valid = r.get("val3dity_valid") if r else None
            sol = solid_of(r)
            err = (r or {}).get("error")
            tally[a]["n"] += 1
            if sol:
                tally[a]["solid"] += 1
            if rms is not None:
                tally[a]["rms"].append(rms)
            if ref_roof and rs and abs(rs - ref_roof) <= 1:
                tally[a]["facet_close"] += 1
            note = f" ({err})" if err else ""
            lines.append(f"| {a} | {fmt(rs)} | {fmt(rms,3)} | {fmt(valid)} | {'Y' if sol else 'N'}{note} |")
            csv_rows.append({"bid": bid, "is_recovery": t in RECOVERY, "arm": a, "tag": A.tag,
                             "ref_roof": ref_roof, "roof_surfaces": rs, "rms_to_ref_m": rms,
                             "val3dity_valid": valid, "solid": sol, "error": err})

    # summary
    import statistics as st
    lines.append("\n## summary (per arm, over 11 buildings)")
    lines.append("| arm | solid n/11 | median RMS->ref(m) | facet within +-1 of ref n/11 |")
    lines.append("|---|---:|---:|---:|")
    for a in ARMS:
        ta = tally[a]
        med = round(st.median(ta["rms"]), 3) if ta["rms"] else None
        lines.append(f"| {a} | {ta['solid']}/{ta['n']} | {fmt(med,3)} | {ta['facet_close']}/{ta['n']} |")

    # one-line observations (NO verdict) — GS(seed) vs raw(seed), per cloud
    lines.append("\n## one-line observations (no verdict)")
    for cloud in ["sparse", "dense", "acmp"]:
        g, rw = tally[f"gs_seed_{cloud}"], tally[f"raw_{cloud}"]
        gm = round(st.median(g["rms"]), 3) if g["rms"] else None
        rm = round(st.median(rw["rms"]), 3) if rw["rms"] else None
        lines.append(f"- **{cloud}**: solid GS {g['solid']}/{g['n']} vs raw {rw['solid']}/{rw['n']}; "
                     f"median RMS->ref GS {fmt(gm,3)} vs raw {fmt(rm,3)}; "
                     f"facet~ref GS {g['facet_close']}/{g['n']} vs raw {rw['facet_close']}/{rw['n']}.")
    la = tally["raw_lidar"]
    lm = round(st.median(la["rms"]), 3) if la["rms"] else None
    lines.append(f"- **LiDAR(raw_lidar) reference floor**: solid {la['solid']}/{la['n']}, median RMS->ref {fmt(lm,3)}, "
                 f"facet~ref {la['facet_close']}/{la['n']}.")

    rep = OUT / "REPORT_v6.md"
    rep.write_text("\n".join(lines) + "\n")
    with open(OUT / "table_v6.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["bid", "is_recovery", "arm", "tag", "ref_roof",
                           "roof_surfaces", "rms_to_ref_m", "val3dity_valid", "solid", "error"])
        w.writeheader(); w.writerows(csv_rows)
    print("\n".join(lines))
    print(f"\n[done] -> {rep}  +  {OUT/'table_v6.csv'}")


if __name__ == "__main__":
    main()

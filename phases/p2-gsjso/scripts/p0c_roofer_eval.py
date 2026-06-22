#!/usr/bin/env python3
"""P0 completeness re-verification (Step 2) — post-Roofer eval driver.

Reuses the EXACT P0 W2 parsing chain (08_roofer_w2.py: combine_cityjsonseq /
parse_roofer_features / classify_buildings / classify_reason) so generation-rate
and val3dity verdicts are identical to the canonical audit, but on a NEW cloud x
Roofer-param cell. Runs INSIDE jointbuildgs-p0-tools (val3dity on PATH). Observation
only — no judgment. EPSG:25832.

Inputs (args): --jsonl-dir (roofer output dir) --label (cell id) --outdir.
Writes: <outdir>/<label>_status.csv (all 199), prints target-population summary.
"""
import argparse, csv, importlib.util, json, subprocess, sys
from pathlib import Path

REPO = Path("/workspace/JointBuildGS")
MOD08 = REPO / "phases/p0-audit/scripts/08_roofer_w2.py"
IDS_CSV = REPO / "phases/p0-audit/docs/scene_aoi_buildings.csv"
CENSUS = REPO / "results/tum_transfer/mob_analysis/p0_census.json"


def load_mod08():
    spec = importlib.util.spec_from_file_location("rw2", MOD08)
    m = importlib.util.module_from_spec(spec)
    sys.modules["rw2"] = m
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl-dir", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()
    mod = load_mod08()
    outdir = Path(a.outdir); outdir.mkdir(parents=True, exist_ok=True)
    jsonl_files = sorted(Path(a.jsonl_dir).glob("*.city.jsonl"))
    if not jsonl_files:
        raise SystemExit(f"no .city.jsonl in {a.jsonl_dir}")

    cityjson = outdir / f"{a.label}.city.json"
    val_report = outdir / f"{a.label}_val3dity.json"
    mod.combine_cityjsonseq(jsonl_files, cityjson)
    subprocess.run(["val3dity", cityjson.as_posix(), "--report", val_report.as_posix()],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    vr = json.loads(val_report.read_text())
    val_by_id = {str(f.get("id")): f for f in vr.get("features", []) if f.get("id") is not None}
    roofer_by_id = mod.parse_roofer_features(jsonl_files)

    expected_ids = [r["building_id"] for r in csv.DictReader(open(IDS_CSV))]
    rows = mod.classify_buildings(a.label, expected_ids, roofer_by_id, val_by_id)
    status_csv = outdir / f"{a.label}_status.csv"
    with open(status_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    by = {r["building_id"]: r for r in rows}
    cen = json.load(open(CENSUS))
    tgt = {o["bid"]: o["dim_reason"] for o in cen["targets"]}
    from collections import defaultdict
    agg = defaultdict(lambda: [0, 0, 0])  # reason -> [n, success, has_lod22]
    recovered = []
    for bid, reason in tgt.items():
        r = by.get(bid, {})
        ok = r.get("status") == "success"; lod = r.get("has_lod22") == "True"
        agg[reason][0] += 1; agg[reason][1] += ok; agg[reason][2] += lod
        if lod:
            recovered.append((bid.split("_")[-1], reason, r.get("status"), r.get("rf_roof_planes"), r.get("val3dity_valid")))
    print(f"\n##### CELL {a.label}: target-population generation #####")
    print(f"  {'bucket':28s} n  has_lod22  success(valid)")
    for reason, x in sorted(agg.items()):
        print(f"  {reason:28s} {x[0]:2d}   {x[2]:2d}        {x[1]:2d}")
    print(f"  recovered LoD2.2 (has_lod22=True): {len(recovered)}/{len(tgt)}")
    for bid, reason, st, pl, vv in sorted(recovered):
        print(f"    {bid:12s} {reason:26s} status={st} planes={pl} val3dity={vv}")
    json.dump({"label": a.label, "agg": {k: v for k, v in agg.items()}, "recovered": recovered},
              open(outdir / f"{a.label}_target_summary.json", "w"), indent=1)
    print(f"[done] {status_csv}")


if __name__ == "__main__":
    main()

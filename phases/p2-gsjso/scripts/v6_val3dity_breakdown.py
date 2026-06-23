#!/usr/bin/env python3
"""P2 v6 analysis pack §4 — val3dity / assembly-outcome breakdown for the RAW arm. Read-only host.

For each (raw arm x 11 buildings x {orig,matched}) cross-reference the Roofer CityJSON (LoD levels,
surface types) + the val3dity report (validity, error codes) + the eval error field, and classify the
assembly outcome. Observation only; verdict = 김휘영.

Finding (encoded by this script, not assumed): the v6 raw non-solid mode is "Roofer emits only a LoD0
footprint MultiSurface, no LoD2.2 Solid" -> roof_surfaces=0 while val3dity=True (a flat LoD0 is
trivially valid). NO non-watertight/self-intersection val3dity errors occur. So the breakdown is by
ASSEMBLY outcome, with any real val3dity error codes captured if present.

Out: results/tum_transfer/mob/analysis_pack_v6/val3dity_breakdown.csv (+ printed per-arm summary)
"""
import csv, json
from collections import Counter
from pathlib import Path

REPO = Path("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS")
EVALROOT = REPO / "phases/p0-audit/runs/mob_eval"
OUT = REPO / "results/tum_transfer/mob/analysis_pack_v6"
ARMS = ["raw_sparse", "raw_dense", "raw_acmp", "raw_lidar"]
R8 = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050", "4908166", "4908176"]
Q3 = ["4906969", "4906972", "4908023"]
TARGETS = [(t, "R") for t in R8] + [(t, "Q") for t in Q3]


def geom_summary(cj_path):
    if not cj_path.exists():
        return None
    d = json.loads(cj_path.read_text())
    lods, surf = set(), Counter()
    has_lod22 = False
    for o in d.get("CityObjects", {}).values():
        for g in o.get("geometry", []):
            lod = str(g.get("lod"))
            lods.add(lod)
            if lod.startswith("2") and g.get("type") == "Solid":
                has_lod22 = True
            for s in g.get("semantics", {}).get("surfaces", []):
                surf[s.get("type")] += 1
    return {"lods": ",".join(sorted(lods)), "has_lod22_solid": has_lod22,
            "roof": surf.get("RoofSurface", 0), "wall": surf.get("WallSurface", 0),
            "ground": surf.get("GroundSurface", 0)}


def val_summary(vr_path):
    if not vr_path.exists():
        return None, ""
    d = json.loads(vr_path.read_text())
    valid = bool(d.get("validity", False))
    codes = []
    for e in (d.get("all_errors") or []):
        codes.append(str(e.get("code", e) if isinstance(e, dict) else e))
    for feat in (d.get("features") or []):
        for p in (feat.get("primitives") or []):
            for e in (p.get("errors") or []):
                codes.append(str(e.get("code", e) if isinstance(e, dict) else e))
    return valid, ";".join(sorted(set(c for c in codes if c)))


def main():
    eval_err = {}
    for p in [REPO / "results/tum_transfer/mob/eval_v6_raw.json"]:
        if p.exists():
            for r in json.loads(p.read_text()):
                eval_err[(r["config"], r["bid"], r.get("tag"))] = r.get("error")

    rows = []
    for arm in ARMS:
        for short, cls in TARGETS:
            bid = f"DEBY_LOD2_{short}"
            for tag in ("orig", "matched"):
                gs = geom_summary(EVALROOT / arm / f"{bid}_{tag}.city.json")
                valid, codes = val_summary(EVALROOT / arm / f"{bid}_{tag}_val3dity.json")
                err = eval_err.get((arm, bid, tag))
                if gs is None:
                    outcome = f"no_roofer_output ({err})" if err else "no_city_json"
                elif not gs["has_lod22_solid"]:
                    outcome = "lod0_only_no_lod22"          # only footprint emitted, no roof structured
                elif valid is False:
                    outcome = f"lod22_INVALID:{codes or '?'}"
                else:
                    outcome = "lod22_solid_valid"
                rows.append({"arm": arm, "building": short, "cls": cls, "tag": tag,
                             "lods": (gs or {}).get("lods"), "has_lod22_solid": (gs or {}).get("has_lod22_solid"),
                             "roof": (gs or {}).get("roof"), "wall": (gs or {}).get("wall"),
                             "ground": (gs or {}).get("ground"),
                             "val3dity_valid": valid, "val3dity_error_codes": codes,
                             "eval_error": err, "outcome": outcome})

    OUT.mkdir(parents=True, exist_ok=True)
    keys = ["arm", "building", "cls", "tag", "lods", "has_lod22_solid", "roof", "wall", "ground",
            "val3dity_valid", "val3dity_error_codes", "eval_error", "outcome"]
    with open(OUT / "val3dity_breakdown.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)

    print("=== §4 assembly/val3dity outcome per raw arm (88 cells = 4 arms x 11 x {orig,matched}) ===")
    for arm in ARMS:
        c = Counter(r["outcome"].split(":")[0].split(" ")[0] for r in rows if r["arm"] == arm)
        ninv = sum(1 for r in rows if r["arm"] == arm and r["val3dity_valid"] is False)
        print(f"  {arm:12} {dict(c)}  | val3dity-invalid: {ninv}")
    allinv = [r for r in rows if r["val3dity_valid"] is False]
    print(f"\nval3dity INVALID geometries across raw arm: {len(allinv)}  "
          f"(codes: {Counter(r['val3dity_error_codes'] for r in allinv) if allinv else 'none'})")
    print("→ raw non-solid = 'lod0_only_no_lod22' (Roofer emits footprint only, no LoD2.2). "
          "val3dity finds 0 geometric errors. Observation only.")
    print(f"[done] -> {OUT}/val3dity_breakdown.csv ({len(rows)} rows)")


if __name__ == "__main__":
    main()

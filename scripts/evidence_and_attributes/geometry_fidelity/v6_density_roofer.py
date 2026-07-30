#!/usr/bin/env python3
"""P2 v6 density-match §2 — re-run the v6-identical Roofer on each density-downsampled GS LAS
and count RoofSurface. Host drives P0 compose roofer (same image/flags as tum_mob_eval). Merges
facet count into density_match_metrics.csv -> density_match.csv. Observation only; verdict = 김휘영.
"""
import csv, json, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from scripts.input_and_alignment.tum_transfer.tum_mob_eval import combine_jsonl, count_roof_surfaces  # stdlib-only funcs

P0 = REPO / "phases/p0-audit"
P0_COMPOSE = ["docker", "compose", "-f", str(P0 / "env/docker-compose.p0.yml")]
FOOT = "/workspace/data/work/w2/footprints_scene_aoi.gpkg"
PACK = REPO / "results/tum_transfer/mob/analysis_pack_v6"


def main():
    base = json.loads((REPO / "results/tum_transfer/mob/baselines.json").read_text())
    metrics = list(csv.DictReader(open(PACK / "density_match_metrics.csv")))
    rows = []
    for m in metrics:
        bid = f"DEBY_LOD2_{m['building']}"; arm = m["arm"]; level = m["level"]
        x0, y0, x1, y1 = base[bid]["bbox_utm"]
        las_ct = f"/workspace/runs/mob_eval_density/{arm}/{bid}_{level}.las"
        out_ct = f"/workspace/runs/mob_eval_density/{arm}/roofer_{bid}_{level}"
        out_host = P0 / f"runs/mob_eval_density/{arm}/roofer_{bid}_{level}"
        out_host.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(P0_COMPOSE + ["run", "-T", "--rm", "roofer", "--id-attribute",
            "building_id", "--box", f"{x0:.3f}", f"{y0:.3f}", f"{x1:.3f}", f"{y1:.3f}",
            las_ct, FOOT, out_ct], capture_output=True, text=True)
        jsonls = list(out_host.glob("*.city.jsonl"))
        facet = None
        if jsonls:
            try:
                cj = combine_jsonl(jsonls[0], out_host / "combined.json")
                facet, _ = count_roof_surfaces(cj)
            except Exception as e:
                facet = f"err:{e}"
        m["roofer_facet"] = facet
        rows.append(m)
        print(f"{m['building']} {arm:13} {level:6} dens={m['density_pps_m2']:>7} "
              f"nDisp={m['normal_disp_deg']} ransac={m['ransac_planes']} -> roofer_facet={facet}"
              + ("" if jsonls else "  [no roofer output]"))

    keys = list(metrics[0].keys()) + ["roofer_facet"]
    keys = [k for i, k in enumerate(keys) if k not in keys[:i]]
    with open(PACK / "density_match.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    print(f"\n[done] -> {PACK}/density_match.csv")


if __name__ == "__main__":
    main()

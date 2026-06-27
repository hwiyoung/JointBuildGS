#!/usr/bin/env python3
"""P2-D6 step0 — supplementary (b)x(c): Roofer on the density-matched (GS@LiDAR-density) clouds.

Reads the downsampled LAS written by d6_density_match.py and re-runs Roofer (eps 0.30 + 0.80),
counting TARGET-ONLY facets. Compares GS@orig-density vs GS@LiDAR-density vs LiDAR to separate
the 33x density from intrinsic surface waviness as the curved over-seg driver.

Drives P0 compose roofer. EPSG:25832. Observation only; verdict = 김휘영.
Out: results/.../analysis_pack_d6/densmatch_roofer_d6.csv
"""
import csv, glob, json, subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
P0 = REPO / "phases/p0-audit"
P0_COMPOSE = ["docker", "compose", "-f", str(P0 / "env/docker-compose.p0.yml")]
FOOT = "/workspace/data/work/w2/footprints_scene_aoi.gpkg"
PACK = REPO / "results/tum_transfer/mob/analysis_pack_d6"
EPS = [0.30, 0.80]


def target_facets(out_host, full):
    g = glob.glob(str(out_host / "*.city.jsonl"))
    if not g:
        return None, None
    n = 0; rt = None
    for ln in open(g[0]):
        if not ln.strip():
            continue
        for cid, o in json.loads(ln).get("CityObjects", {}).items():
            if not (cid == full or cid.startswith(full + "-")):
                continue
            rt = o.get("attributes", {}).get("rf_roof_type", rt)
            for geom in o.get("geometry", []):
                for s in geom.get("semantics", {}).get("surfaces", []):
                    if s.get("type") == "RoofSurface":
                        n += 1
    return n, rt


def main():
    base = json.loads((REPO / "results/tum_transfer/mob/baselines.json").read_text())
    dm = list(csv.DictReader(open(PACK / "density_match_d6.csv")))
    rows = []
    for m in dm:
        bid = f"DEBY_LOD2_{m['bid']}"; arm = m["arm"]
        x0, y0, x1, y1 = base[bid]["bbox_utm"]
        las_ct = f"/workspace/runs/_d6_density/{arm}/{bid}_lidarD.las"
        for eps in EPS:
            tag = f"lidarD_eps{eps}"
            out_host = P0 / f"runs/_d6_density/{arm}/{bid}_{tag}"
            out_host.mkdir(parents=True, exist_ok=True)
            cmd = P0_COMPOSE + ["run", "-T", "--rm", "roofer", "--id-attribute", "building_id",
                                "--box", f"{x0:.3f}", f"{y0:.3f}", f"{x1:.3f}", f"{y1:.3f}",
                                "--plane-detect-epsilon", f"{eps}", las_ct, FOOT,
                                f"/workspace/runs/_d6_density/{arm}/{bid}_{tag}"]
            r = subprocess.run(cmd, capture_output=True, text=True)
            (out_host / "roofer.log").write_text((r.stdout or "") + "\n--STDERR--\n" + (r.stderr or ""))
            n, rt = target_facets(out_host, bid)
            rows.append({"bid": m["bid"], "arm": arm, "level": "lidarD", "dens": m["dens_lidarD"],
                         "eps": eps, "facets_target_only": n, "rf_roof_type": rt})
            print(f"{m['bid']:9} {arm:12} lidarD dens={m['dens_lidarD']:>5} eps={eps} -> facets={n} ({rt})")
    with open(PACK / "densmatch_roofer_d6.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["bid", "arm", "level", "dens", "eps",
                                          "facets_target_only", "rf_roof_type"])
        w.writeheader(); w.writerows(rows)
    print(f"\n[done] -> {PACK}/densmatch_roofer_d6.csv")


if __name__ == "__main__":
    main()

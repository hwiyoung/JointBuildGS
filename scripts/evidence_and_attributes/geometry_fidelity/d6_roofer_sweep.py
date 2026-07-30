#!/usr/bin/env python3
"""P2-D6 step0 — component (c): Roofer plane-detection / region-grow threshold SWEEP.

Feeds the SAME canonical _orig_classified.las to Roofer at several plane-detect thresholds and
counts TARGET-ONLY roof facets, applying the IDENTICAL params to GS and LiDAR. Answers: does
loosening Roofer bring GS curved facets down toward LiDAR's 5, or does GS bottom out above 5
(gap = input-side, not Roofer)?

Sweeps --plane-detect-epsilon (the documented over-seg control; Roofer default 0.3) as the headline
axis, plus a --plane-detect-min-points (region-grow) probe at default epsilon on the curved target.
Target-only facet count = d5_target_facets logic (keep CityObjects cid==full or cid.startswith
(full+'-'), drop neighbours). Sanity: eps=0.30 reproduces the D5 §5 numbers (GS_dense 4906969=14,
LiDAR=5).

GS = gs_d4_{dense,acmp} (gssem canonical disk). LiDAR = raw_lidar. Drives P0 compose roofer
(3dgi/roofer:v1.0.0), same image/flags as tum_mob_eval. EPSG:25832. Observation only; verdict=김휘영.
Out: results/.../analysis_pack_d6/roofer_sweep_d6.csv
"""
import csv, glob, json, subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
P0 = REPO / "phases/p0-audit"
P0_COMPOSE = ["docker", "compose", "-f", str(P0 / "env/docker-compose.p0.yml")]
FOOT = "/workspace/data/work/w2/footprints_scene_aoi.gpkg"
OUT = REPO / "results/tum_transfer/mob/analysis_pack_d6"
SWEEP_RUN = "_d6_sweep"  # under phases/p0-audit/runs -> /workspace/runs/_d6_sweep

EPS = [0.20, 0.30, 0.50, 0.80, 1.20]
MINPTS_PROBE = [30, 60]  # at eps=0.30 (mp=15 already covered by EPS sweep)

# (target, [sources]) — curved gets both GS arms; controls get GS_dense + LiDAR
PLAN = [
    ("4906969", "curved",    [("GS_dense", "gs_d4_dense"), ("GS_acmp", "gs_d4_acmp"), ("LiDAR", "raw_lidar")]),
    ("42364659", "composite", [("GS_dense", "gs_d4_dense"), ("LiDAR", "raw_lidar")]),
    ("4906972", "flat",       [("GS_dense", "gs_d4_dense"), ("LiDAR", "raw_lidar")]),
]


def target_facets(out_host, full):
    """Target-only RoofSurface count + roof_type/planes attrs from a roofer output dir."""
    g = glob.glob(str(out_host / "*.city.jsonl"))
    if not g:
        return None, None, None
    n = 0; rtype = None; rplanes = None
    for ln in open(g[0]):
        if not ln.strip():
            continue
        feat = json.loads(ln)
        for cid, o in feat.get("CityObjects", {}).items():
            if not (cid == full or cid.startswith(full + "-")):
                continue
            attr = o.get("attributes", {})
            rtype = attr.get("rf_roof_type", rtype)
            rplanes = attr.get("rf_roof_planes", rplanes)
            for geom in o.get("geometry", []):
                for s in geom.get("semantics", {}).get("surfaces", []):
                    if s.get("type") == "RoofSurface":
                        n += 1
    return n, rtype, rplanes


def run_roofer(arm, bid, tag, x0, y0, x1, y1, eps, minpts):
    las_ct = f"/workspace/runs/mob_eval/{arm}/{bid}_orig_classified.las"
    out_ct = f"/workspace/runs/{SWEEP_RUN}/{arm}/{bid}_{tag}"
    out_host = P0 / f"runs/{SWEEP_RUN}/{arm}/{bid}_{tag}"
    out_host.mkdir(parents=True, exist_ok=True)
    cmd = P0_COMPOSE + ["run", "-T", "--rm", "roofer", "--id-attribute", "building_id",
                        "--box", f"{x0:.3f}", f"{y0:.3f}", f"{x1:.3f}", f"{y1:.3f}",
                        "--plane-detect-epsilon", f"{eps}"]
    if minpts is not None:
        cmd += ["--plane-detect-min-points", str(minpts)]
    cmd += [las_ct, FOOT, out_ct]
    r = subprocess.run(cmd, capture_output=True, text=True)
    (out_host / "roofer.log").write_text((r.stdout or "") + "\n--STDERR--\n" + (r.stderr or ""))
    return out_host


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    base = json.loads((REPO / "results/tum_transfer/mob/baselines.json").read_text())
    rows = []

    def emit():
        keys = ["target", "set", "source", "arm", "axis", "eps", "min_points",
                "facets_target_only", "rf_roof_type", "rf_roof_planes"]
        with open(OUT / "roofer_sweep_d6.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            w.writeheader(); w.writerows(rows)

    for short, setname, sources in PLAN:
        bid = f"DEBY_LOD2_{short}"
        x0, y0, x1, y1 = base[bid]["bbox_utm"]
        for label, arm in sources:
            # epsilon sweep (default min-points=15)
            for eps in EPS:
                tag = f"eps{eps}"
                out_host = run_roofer(arm, bid, tag, x0, y0, x1, y1, eps, None)
                n, rt, rp = target_facets(out_host, bid)
                rows.append({"target": short, "set": setname, "source": label, "arm": arm,
                             "axis": "epsilon", "eps": eps, "min_points": 15,
                             "facets_target_only": n, "rf_roof_type": rt, "rf_roof_planes": rp})
                print(f"{short:9} {label:8} eps={eps:<4} mp=15  -> facets={n}  type={rt} planes={rp}")
                emit()
            # region-grow probe (min-points) at eps=0.30, curved only
            if short == "4906969":
                for mp in MINPTS_PROBE:
                    tag = f"eps0.3_mp{mp}"
                    out_host = run_roofer(arm, bid, tag, x0, y0, x1, y1, 0.30, mp)
                    n, rt, rp = target_facets(out_host, bid)
                    rows.append({"target": short, "set": setname, "source": label, "arm": arm,
                                 "axis": "min_points", "eps": 0.30, "min_points": mp,
                                 "facets_target_only": n, "rf_roof_type": rt, "rf_roof_planes": rp})
                    print(f"{short:9} {label:8} eps=0.30 mp={mp:<3} -> facets={n}  type={rt} planes={rp}")
                    emit()

    print(f"\n[done] {len(rows)} rows -> {OUT}/roofer_sweep_d6.csv")


if __name__ == "__main__":
    main()

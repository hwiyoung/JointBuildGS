#!/usr/bin/env python3
"""P2 make-or-break — density-corrected 5-way eval orchestrator (runs on HOST, drives Docker).

For each (config -> tsdf npz) x building x density variant {orig, matched}:
  1) clip + (density-match to ALS) + classify          [P0 tools container]
  2) Roofer reconstruction                             [P0 roofer service]
  3) combine CityJSONSeq -> CityJSON, val3dity         [host combine + P0 tools val3dity]
  4) parse RoofSurface count + validity + roughness -> results row

Writes results CSV + JSON. EPSG:25832. Engine untouched. Reuses P0 classify/roofer/val3dity.
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
P0 = REPO / "phases/p0-audit"
P0_COMPOSE = ["docker", "compose", "-f", str(P0 / "env/docker-compose.p0.yml")]
TOOLS_RUN = ["docker", "run", "--rm", "-i", "--user", f"{os.getuid()}:{os.getgid()}",
             "-v", f"{REPO}:/workspace/JointBuildGS", "-w", "/workspace/JointBuildGS",
             "jointbuildgs-p0-tools:t0"]
TARGETS = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050",
           "4908166", "4908176", "4906969", "4908023", "4906972"]
RECOVERY = {"42364609", "42364659", "42364663", "4907182", "4907510", "4908050", "4908166", "4908176"}


def sh(cmd, log=None):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if log:
        Path(log).write_text((r.stdout or "") + "\n--STDERR--\n" + (r.stderr or ""))
    return r


def combine_jsonl(jsonl_path, out_cityjson):
    """Minimal CityJSONSeq -> CityJSON for a single Roofer output file."""
    lines = [l for l in Path(jsonl_path).read_text().splitlines() if l.strip()]
    top = json.loads(lines[0])
    top["CityObjects"] = {}; top["vertices"] = []
    for line in lines[1:]:
        feat = json.loads(line)
        off = len(top["vertices"])
        top["vertices"].extend(feat.get("vertices", []))
        for oid, obj in feat.get("CityObjects", {}).items():
            for g in obj.get("geometry", []):
                g["boundaries"] = _shift(g.get("boundaries", []), off)
            top["CityObjects"][oid] = obj
    Path(out_cityjson).write_text(json.dumps(top, separators=(",", ":")))
    return top


def _shift(v, off):
    if isinstance(v, int):
        return v + off
    if isinstance(v, list):
        return [_shift(x, off) for x in v]
    return v


def count_roof_surfaces(cityjson):
    """Count RoofSurface / WallSurface semantic surfaces across all CityObjects."""
    roof = wall = 0
    for obj in cityjson.get("CityObjects", {}).values():
        for g in obj.get("geometry", []):
            sem = g.get("semantics", {})
            for s in sem.get("surfaces", []):
                t = s.get("type", "")
                if t == "RoofSurface":
                    roof += 1
                elif t == "WallSurface":
                    wall += 1
    return roof, wall


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", nargs="+", required=True,
                    help="name=tsdf_npz pairs, e.g. vanilla=results/.../tsdf_vanilla.npz")
    ap.add_argument("--baselines", default="results/tum_transfer/mob/baselines.json")
    ap.add_argument("--geojson", default="results/tum_transfer/analysis/footprints_aoi.geojson")
    ap.add_argument("--footprints", default="/workspace/data/work/w2/footprints_scene_aoi.gpkg")
    ap.add_argument("--evalroot", default="phases/p0-audit/runs/mob_eval")
    ap.add_argument("--out", default="results/tum_transfer/mob/eval_results.json")
    ap.add_argument("--targets", nargs="*", default=TARGETS)
    ap.add_argument("--densities", nargs="*", default=["orig", "matched"])
    ap.add_argument("--classifier", choices=["smrf", "gssem"], default="smrf",
                    help="ground/building labeling for the Roofer read-out: smrf (PDAL filters.smrf + "
                         "GT-footprint overlay, the v6 default) | gssem (GS per-point semantic argmax, "
                         "no SMRF — building=6 from Roof/Wall, ground=2 from Terrain + synth base)")
    A = ap.parse_args()
    prep_script = ("scripts/input_and_alignment/p2_gsjso/_mob_prep_las_gssem.py" if A.classifier == "gssem"
                   else "scripts/input_and_alignment/p2_gsjso/_mob_prep_las.py")
    print(f"[eval] classifier={A.classifier} -> {prep_script}")

    base = json.loads((REPO / A.baselines).read_text())
    configs = dict(c.split("=", 1) for c in A.configs)
    rows = []
    for cname, npz_rel in configs.items():
        npz_ct = f"/workspace/JointBuildGS/{npz_rel}"
        for t in A.targets:
            bid = f"DEBY_LOD2_{t}"
            bb = base[bid]
            x0, y0, x1, y1 = bb["bbox_utm"]
            outdir_host = REPO / A.evalroot / cname
            outdir_ct = f"/workspace/JointBuildGS/{A.evalroot}/{cname}"
            # roofer service mounts phases/p0-audit/runs -> /workspace/runs; derive its output dir
            # from evalroot (not a hardcoded 'mob_eval') so custom --evalroot values resolve.
            eval_rel = A.evalroot.split("phases/p0-audit/runs/", 1)[-1]
            outdir_roofer = f"/workspace/runs/{eval_rel}/{cname}"
            outdir_host.mkdir(parents=True, exist_ok=True)
            for tag in A.densities:
                tgt = (bb["als_roof_density_pps_m2"] or 0.0) if tag == "matched" else 0.0
                # 1) prep + classify (smrf or gssem per --classifier)
                pr = sh(TOOLS_RUN + ["python3", prep_script,
                        "--tsdf", npz_ct, "--bid", bid, "--geojson", f"/workspace/JointBuildGS/{A.geojson}",
                        "--target-density", str(tgt), "--outdir", outdir_ct, "--tag", tag],
                        log=str(outdir_host / f"{bid}_{tag}_prep.log"))
                mpath = outdir_host / f"{bid}_{tag}_metrics.json"
                if not mpath.exists():
                    rows.append({"config": cname, "bid": bid, "tag": tag, "error": "prep_failed",
                                 "prep_stderr": pr.stderr[-300:]})
                    print(f"[{cname}/{t}/{tag}] PREP FAILED"); continue
                met = json.loads(mpath.read_text())
                row = {"config": cname, "bid": bid, "tag": tag, "is_recovery": t in RECOVERY,
                       "ref_roof": bb["ref_roof_surfaces"], "ref_wall": bb["ref_wall_surfaces"],
                       "als_density": bb["als_roof_density_pps_m2"],
                       "n_clip": met["n_clip"], "n_used": met["n_used"],
                       "roof_density": met.get("roof_density"), "plane_rms": met.get("plane_rms"),
                       "n_building_in_fp": met.get("n_building_in_fp"),
                       "roofer_ok": False, "roof_surfaces": None, "wall_surfaces": None,
                       "val3dity_valid": None}
                clf = met.get("classified_las")
                if not clf:
                    row["error"] = "no_points"; rows.append(row)
                    print(f"[{cname}/{t}/{tag}] NO POINTS"); continue
                clf_roofer = clf.replace("/workspace/JointBuildGS/phases/p0-audit/runs", "/workspace/runs")
                roof_out_ct = f"{outdir_roofer}/roofer_{bid}_{tag}"
                roof_out_host = outdir_host / f"roofer_{bid}_{tag}"
                # 2) roofer
                rf = sh(P0_COMPOSE + ["run", "-T", "--rm", "roofer", "--id-attribute", "building_id",
                        "--box", f"{x0:.3f}", f"{y0:.3f}", f"{x1:.3f}", f"{y1:.3f}",
                        clf_roofer, A.footprints, roof_out_ct],
                        log=str(outdir_host / f"{bid}_{tag}_roofer.log"))
                jsonls = list(roof_out_host.glob("*.city.jsonl"))
                if not jsonls:
                    row["error"] = "roofer_no_output"; rows.append(row)
                    print(f"[{cname}/{t}/{tag}] ROOFER no output"); continue
                row["roofer_ok"] = True
                cj_host = outdir_host / f"{bid}_{tag}.city.json"
                try:
                    cj = combine_jsonl(jsonls[0], cj_host)
                    roof, wall = count_roof_surfaces(cj)
                    row["roof_surfaces"] = roof; row["wall_surfaces"] = wall
                except Exception as e:
                    row["error"] = f"combine_failed:{e}"; rows.append(row); continue
                # 3) val3dity (cityjson under /workspace/runs)
                cj_ct = str(cj_host).replace(str(REPO / "phases/p0-audit/runs"), "/workspace/runs")
                rep_ct = cj_ct.replace(".city.json", "_val3dity.json")
                rep_host = Path(str(cj_host).replace(".city.json", "_val3dity.json"))
                sh(P0_COMPOSE + ["run", "-T", "--rm", "tools", "val3dity", cj_ct, "--report", rep_ct],
                   log=str(outdir_host / f"{bid}_{tag}_val3dity.log"))
                if rep_host.exists():
                    try:
                        vr = json.loads(rep_host.read_text())
                        row["val3dity_valid"] = bool(vr.get("validity", False))
                    except Exception:
                        pass
                rows.append(row)
                print(f"[{cname}/{t}/{tag}] roof={row['roof_surfaces']} valid={row['val3dity_valid']} "
                      f"used={row['n_used']} rms={row['plane_rms']} dens={row['roof_density']}")

    Path(REPO / A.out).parent.mkdir(parents=True, exist_ok=True)
    Path(REPO / A.out).write_text(json.dumps(rows, indent=2))
    # csv
    import csv
    keys = ["config", "bid", "tag", "is_recovery", "ref_roof", "roof_surfaces", "wall_surfaces",
            "val3dity_valid", "roofer_ok", "n_clip", "n_used", "roof_density", "als_density",
            "plane_rms", "error"]
    with open(str(REPO / A.out).replace(".json", ".csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore"); w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[done] {len(rows)} rows -> {A.out}")


if __name__ == "__main__":
    main()

"""PHD-MAIN-METRICS-TRIAL-v1 records for the 4.7 proposals (jointbuildgs:dev, CPU; written after the results; purpose: show what
a changed definition would read; not criteria and not used for any number of the trial).

  python proposal_mt.py

Trial band (config): range of the GT heights within 0.5 m > 0.3 m. On a plane of slope a that range is about 2 r tan(a)
(= 0.58 m at 30 degrees), so every point of a steep face is in the band. Proposed: range - 2 r tan(a) > 0.3 m, with a = the
slope of the owning prior face (the patch normal). For the measured-agreement roof rows of each prior: the band shares by
slope under both rules, the points the proposal gives back per building, and on those points the signed distance along the
prior-face normal already computed for every result (metrics/<result>_rows.npz 'u_along', the 4.3 edge-band reading).
Also (same purpose): the floaters of every training split into 3-20 m (near the surfaces) and above 20 m over the highest GT
surface, with the share over the B173 wings; the mechanism layer of 11-14 split by the patch's |GT - prior| (< 0.5 m:
the 0.25 m probe at W also reaches Gaussians of the current surface).
Writes /out/tables/proposal_band.json, /out/tables/proposal_more.json. scientific_verdict: null."""
import json

import numpy as np
from matplotlib.path import Path as MPath

from mt_common import DR, OUT, jdump
from src.phd.metrics_v1 import stats

SLOPES = [0, 5, 17, 30, 45, 91]
RES = {"LoD2": ["b1_LoD2", "b2_LoD2", "surface_LoD2", "samepath_LoD2"], "ALS": ["b1_ALS", "b2_ALS", "surface_ALS", "samepath_ALS"]}


def main():
    G = np.load(OUT / "defs/gt_classes.npz")
    X = G["xyz"]
    fp = json.loads((DR / "s02_box/B173nb_b10/footprints.json").read_text())["footprints"]
    out = {}
    for p, results in RES.items():
        r = np.load(OUT / "defs" / f"rows_{p}.npz")
        m = (r["code"] == 2) & (r["kind"] == 1)
        pt = r["point"][m]
        slope = r["slope"][m].astype(np.float64)
        rng = np.nan_to_num(G["band_range"][pt].astype(np.float64), nan=0.0)
        trial = G["in_band"][pt]
        prop = (rng - 2 * 0.5 * np.tan(np.radians(np.minimum(slope, 80.0)))) > 0.3
        back = trial & ~prop
        e = dict(roof_points=int(m.sum()), trial_band_share=round(float(trial.mean()), 4), proposed_band_share=round(float(prop.mean()), 4),
                 by_slope=[], given_back_by_building={}, along_normal_on_given_back={})
        for a, b in zip(SLOPES[:-1], SLOPES[1:]):
            ms = (slope >= a) & (slope < b)
            e["by_slope"].append(dict(slope_deg=[a, b], points=int(ms.sum()), trial=None if not ms.any() else round(float(trial[ms].mean()), 4),
                                      proposed=None if not ms.any() else round(float(prop[ms].mean()), 4)))
        for f in fp:
            inside = MPath(np.asarray(f["ring_local"])).contains_points(X[pt, :2])
            e["given_back_by_building"][f["building"]] = int((inside & back).sum())
        for res in results:
            ua = np.load(OUT / "metrics" / f"{res}_rows.npz")["u_along"][m]
            e["along_normal_on_given_back"][res] = stats.robust(ua[back])
        out[p] = e
    jdump(OUT / "tables/proposal_band.json", dict(rule="proposed band: range of GT heights within 0.5 m minus 2 x 0.5 m x tan(prior-face slope) > 0.3 m (record)",
                                                  result=out, scientific_verdict=None))
    print(json.dumps(out, indent=1)[:3000])
    # floaters by height band, mechanism layer by conflict size
    from mt_common import S0, xy_to_uv
    tr = np.load(OUT / "defs/top_raster.npz")
    fl, mech = {}, {}
    for p, results in RES.items():
        rw = np.load(OUT / "defs" / f"rows_{p}.npz")
        g = np.abs(rw["w_gt_med"].astype(np.float64))
        for res in results[:2]:
            d = np.load(S0 / "stage0" / res / "model/dump/iteration_30000/gaussians.npz")
            fm = np.load(OUT / "gpu" / res / "floater_mask.npy")
            x = d["xyz"][fm].astype(np.float64)
            q = np.floor((x[:, :2] - tr["lo"]) / float(tr["cell"])).astype(np.int64)
            h = x[:, 2] - tr["grid"][q[:, 1], q[:, 0]]
            uv = xy_to_uv(x[:, :2])
            wing = ((uv[:, 1] > 79) & (uv[:, 1] < 89)) | ((uv[:, 1] > 99) & (uv[:, 1] < 108))
            near = h <= 20
            fl[res] = dict(near_3_20m=int(near.sum()), near_over_b173_wings=int((near & wing).sum()), near_prior_origin=int((near & (d["origin"][fm] == 1)).sum()),
                           sky_over_20m=int((~near).sum()), near_height_q=[round(float(v), 2) for v in np.quantile(h[near], [0.05, 0.5, 0.95])] if near.any() else None)
            c = np.load(OUT / "metrics" / f"{res}_rows.npz")["w_count_prior"]
            e = {}
            for cc in (11, 12, 13, 14):
                for nm, mm in (("lt_0.5m", (rw["w_code"] == cc) & (g < 0.5)), ("ge_0.5m", (rw["w_code"] == cc) & (g >= 0.5))):
                    e[f"{cc}_{nm}"] = dict(patches=int(mm.sum()), prior_origin_share=round(float((c[mm] > 0).mean()), 4) if mm.any() else None)
            mech[res] = e
    jdump(OUT / "tables/proposal_more.json", dict(floater_bands=fl, mechanism_by_size=mech, scientific_verdict=None))
    print(json.dumps(fl), json.dumps(mech)[:1500])


if __name__ == "__main__":
    main()

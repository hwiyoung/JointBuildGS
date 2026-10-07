"""PHD-MAIN-STAGE1-v1 the reference biases written next to the results' biases (order 5) (jointbuildgs:dev, CPU; no training result read).

ground    MVS - GT of the site's bare ground after the common shift: pass 2 of the common alignment (v3/align/common_shift.json,
          the box's pooled bare-ground pixels; median)
building  MVS - GT on the rows of the accuracy bundle's gentle roof (support agreement, roof-like, outside the band v2, prior-face
          slope <= 17 deg, thinned) of each unit: z_MVS of the GT point's 0.1 m cell (regions_v3/mvs_at_gt, float64) - z_GT; per
          building (the box footprints) and pooled; bias = median, NMAD with it. Rows of the B0 primary GT (no MVS lookup) are counted
          apart.

  python refbias_s1.py      -> /out/tables/refbias.json, .md
scientific_verdict: null."""
import json

import numpy as np
from matplotlib.path import Path as MPath

from s1_common import DR, OUT, SITES, jdump, log
from src.phd.metrics_v3 import stats


def main():
    cs = json.loads((OUT / "v3/align/common_shift.json").read_text())
    p2 = cs["passes"][1]["per_box"]
    res, md = {}, ["| 지역 | 단위 | 지면 MVS − 참값 (cm) | 건물 MVS − 참값 (cm, NMAD) | 건물별 MVS − 참값 (cm; 점 수) |", "|---|---|---|---|---|"]
    for site in SITES:
        G = np.load(OUT / "defs" / site / "gt_classes.npz")
        X = G["xyz_gt_points"].astype(np.float64)
        M = np.load(OUT / "regions_v3" / f"mvs_at_gt_{site}.npz")
        zm = np.full(len(X), np.nan)
        zm[M["gt_points_index"]] = M["gt_points_z_mvs"]
        fp = json.loads((DR / "s02_box" / site / "footprints.json").read_text())["footprints"]
        for unit in ("LoD2", "ALS"):
            r = np.load(OUT / "defs" / site / f"rows_{unit}.npz")
            gentle = (r["code"] == 2) & (r["kind"] == 1) & ~r["in_band_v2"] & (r["slope"].astype(np.float64) <= 17.0) & r["thin"]
            own = gentle & (r["src"] == 0)
            d = np.full(len(r["point"]), np.nan)
            d[own] = zm[r["point"][own]] - X[r["point"][own], 2]
            pooled = stats.bias_dispersion(d[own])
            by_b = {}
            for f in fp:
                inside = MPath(np.asarray(f["ring_local"])).contains_points(X[r["point"][own], :2])
                idx = np.nonzero(own)[0][inside]
                if len(idx):
                    b = stats.bias_dispersion(d[idx])
                    by_b[f["building"]] = dict(points=int(len(idx)), bias=b["bias"], nmad=b["nmad"])
            res[f"{site}/{unit}"] = dict(ground_mvs_minus_gt=round(float(p2[site]["median_m"]), 4), ground_pixels=int(p2[site]["pixels"]),
                                         building_mvs_minus_gt=pooled, by_building=by_b, rows_gentle=int(gentle.sum()),
                                         rows_without_mvs=int((own & ~np.isfinite(d)).sum()), rows_primary_gt_not_looked_up=int((gentle & (r["src"] != 0)).sum()))
            bb = "; ".join(f"{k.replace('DEBY_LOD2_', '')} {100 * v['bias']:+.1f} ({v['points']:,})" for k, v in by_b.items() if v["bias"] is not None)
            pb = "—" if pooled["bias"] is None else f"{100 * pooled['bias']:+.1f} ({100 * pooled['nmad']:.1f})"
            md.append(f"| {site} | {unit} | {100 * p2[site]['median_m']:+.1f} | {pb} | {bb} |")
            log("refbias", site, unit, pooled["n"], pooled["bias"])
    jdump(OUT / "tables/refbias.json", dict(rule=__doc__, sites=res, scientific_verdict=None))
    (OUT / "tables/refbias.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()

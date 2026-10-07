"""PHD-MAIN-STAGE1-v1 scale check of the batched DA3 depth against the box MVS (jointbuildgs:dev, CPU; decided 2026-10-07 with the
batching; a record next to the GeoGS results, not used by the training).

Per training view: the DA3 depth as GeoGS reads it (da3_prior/raw_depth at the inference resolution, resized to 1024 x 741 with
INTER_LINEAR as the official train.py) against the box MVS geometric depth of the same view (prep payload mvs/box_<site>), pixels valid
in both (finite, > 0): median of DA3 / MVS (scale), NMAD of log(DA3 / MVS), median |DA3 - MVS| (m), share within 5 %. Per batch: the
median of its views' scales; per site: the batches' scales (min, median, max, max / min).

  python geogs_scale.py <site> [<site> ...]    -> /out/geogs/<site>/da3_scale.json, /out/tables/geogs_da3_scale.md (the sites given)
scientific_verdict: null."""
import json
import sys

import cv2
import numpy as np

from s1_common import OUT, PREP, jdump, log, read_depth_bin

NMAD = 1.4826


def site_check(site):
    S = OUT / "geogs" / site / "scene/da3_prior"
    rec = json.loads((S / "receipt.json").read_text())
    mv = PREP / "mvs" / f"box_{site}" / "stereo/depth_maps"
    batches = []
    for row in rec["batch_rows"]:
        views = []
        for n in row["views"]:
            f = mv / f"{n}.JPG.geometric.bin"
            if not f.exists():
                views.append(dict(view=n, mvs=False))
                continue
            m = read_depth_bin(f).astype(np.float64)
            d = np.load(S / "raw_depth" / f"{n}.npy").astype(np.float32)
            d = cv2.resize(d, (m.shape[1], m.shape[0]), interpolation=cv2.INTER_LINEAR).astype(np.float64)
            ok = np.isfinite(m) & (m > 0) & np.isfinite(d) & (d > 0)
            if ok.sum() < 1000:
                views.append(dict(view=n, mvs=True, pixels=int(ok.sum())))
                continue
            r = d[ok] / m[ok]
            lr = np.log(r)
            views.append(dict(view=n, mvs=True, pixels=int(ok.sum()), scale=float(np.median(r)), nmad_log=float(NMAD * np.median(np.abs(lr - np.median(lr)))),
                              median_abs_m=float(np.median(np.abs(d[ok] - m[ok]))), within_5pct=float((np.abs(r - 1) <= 0.05).mean()),
                              mvs_median_m=float(np.median(m[ok]))))
        sc = [v["scale"] for v in views if "scale" in v]
        batches.append(dict(batch=row["batch"], views=views, scale=float(np.median(sc)) if sc else None,
                            scale_min=float(min(sc)) if sc else None, scale_max=float(max(sc)) if sc else None))
    bs = [b["scale"] for b in batches if b["scale"] is not None]
    allv = [v for b in batches for v in b["views"] if "scale" in v]
    out = dict(site=site, rule=__doc__, batches=batches, batch_scale=dict(n=len(bs), min=min(bs), median=float(np.median(bs)), max=max(bs), max_over_min=max(bs) / min(bs)) if bs else None,
               views=dict(n=len(allv), scale_median=float(np.median([v["scale"] for v in allv])) if allv else None,
                          scale_q05_q95=[float(np.quantile([v["scale"] for v in allv], q)) for q in (0.05, 0.95)] if allv else None,
                          median_abs_m=float(np.median([v["median_abs_m"] for v in allv])) if allv else None,
                          within_5pct=float(np.median([v["within_5pct"] for v in allv])) if allv else None,
                          without_mvs=sum(1 for b in batches for v in b["views"] if not v.get("mvs"))), scientific_verdict=None)
    jdump(OUT / "geogs" / site / "da3_scale.json", out)
    log("da3 scale", site, out["batch_scale"], out["views"])
    return out


def main(sites):
    md = ["| 지역 | 묶음 | 영상 | 묶음 척도 최소 / 중앙 / 최대 (DA3 ÷ MVS) | 최대 ÷ 최소 | 영상 척도 5~95 % | |DA3 − MVS| 중앙 (m) | 5 % 안 몫 (중앙) |",
          "|---|---|---|---|---|---|---|---|"]
    for s in sites:
        o = site_check(s)
        b, v = o["batch_scale"], o["views"]
        md.append(f"| {s} | {b['n']} | {v['n']} | {b['min']:.3f} / {b['median']:.3f} / {b['max']:.3f} | {b['max_over_min']:.3f} | "
                  f"{v['scale_q05_q95'][0]:.3f}~{v['scale_q05_q95'][1]:.3f} | {v['median_abs_m']:.2f} | {100 * v['within_5pct']:.0f} % |")
    f = OUT / "tables/geogs_da3_scale.md"
    old = f.read_text().splitlines()[2:] if f.exists() else []
    keep = [l for l in old if l.split("|")[1].strip() not in sites]
    f.write_text("\n".join(md[:2] + keep + md[2:]) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main(sys.argv[1:])

"""PHD-MAIN-PREP-MEASURE-v1 step 06b (jointbuildgs:dev, CPU): size rule of the case boxes (5.5).

  python step06b_box_stability.py [--stage1-sub step06/stage1]

For every box, prior and band: tau (roof, wall), registration shift (x, y, z), final check, horizontal estimability,
tolerance samples (sampled confidence-1 building-face pixels; a lower bound of the full count) and the tolerance record
(median after registration, NMAD before / after the 3-NMAD clip, clipped share) recomputed from residual_samples.npz with
the same module. Rule (config boxes.stability): the smallest band whose roof and wall tau are within 10 % of the next band's
and whose shift is within 5 cm (3-D vector) of the next band's, with enough samples (roof >= 5,000, wall >= 2,000, else
the wall takes the roof value and the box is marked). Written before the box results (box spec 21:45): a box is sized
for both priors, i.e. the larger of the two per-prior bands; 'over the upper limit' = a side longer than 100 m.
Writes step06/box_stability.json. scientific_verdict: null."""
import argparse
import json

import numpy as np

from common import CFG, OUT, jdump
from src.phd.prior_propagation_v4 import tolerance as tol


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--stage1-sub", default="step06/stage1")
    a = ap.parse_args()
    R = json.loads((OUT / "step06/box_ranges.json").read_text())
    BV = json.loads((OUT / "step06/box_views.json").read_text())["views"]
    bc = CFG["boxes"]; lim = bc["upper_limit_side_m"]
    roof_min, wall_min = 5000, 2000
    rows = {}
    for rid, r in R.items():
        for prior in ("LoD2", "ALS"):
            S1 = OUT / a.stage1_sub / rid / prior
            if not (S1 / "summary.json").exists():
                continue
            s = json.loads((S1 / "summary.json").read_text())
            rs = np.load(S1 / "residual_samples.npz")
            st_r = tol.robust_width(rs["roof"].astype(np.float64)); st_w = tol.robust_width(rs["wall"].astype(np.float64))
            reg = s["registration"]
            rows[(rid, prior)] = dict(box=r["box"], band_m=r["band_m"], prior=prior,
                                      side_m=[round(r["u_m"][1] - r["u_m"][0], 1), round(r["v_m"][1] - r["v_m"][0], 1)],
                                      area_m2=r["area_m2"], train_views=len(BV[rid]["train"]), eval_views=len(BV[rid]["evaluation"]),
                                      tau_roof=s["tolerance"]["roof"]["tau"], tau_wall=s["tolerance"]["wall"]["tau"],
                                      wall_side=s["tolerance"]["wall"]["side"], shift=reg["shift_applied"],
                                      horizontal_estimable=reg["horizontal_estimable"], final_check=reg.get("final_check", {}).get("passed"),
                                      nmad_bf_before=reg["building_face_nmad_unregistered"], nmad_bf_after=reg["building_face_nmad_registered"],
                                      n_roof=int(st_r.get("n", 0)), n_wall=int(st_w.get("n", 0)),
                                      roof_record={k: st_r.get(k) for k in st_r if k != "kept"},
                                      wall_record={k: st_w.get(k) for k in st_w if k != "kept"},
                                      enough_roof=bool(st_r.get("n", 0) >= roof_min),
                                      enough_wall=bool(st_w.get("n", 0) >= wall_min) if prior == "LoD2" else None,
                                      states=s["states"], support_vote=s["support_vote"], missing_judgment=s["missing_judgment"])
    boxes = sorted({r["box"] for r in R.values()})
    out = {}
    for b in boxes:
        bands = sorted({r["band_m"] for r in R.values() if r["box"] == b})
        per = {}
        for prior in ("LoD2", "ALS"):
            seq = [rows.get((f"{b}_b{int(x)}", prior)) for x in bands]
            if any(v is None for v in seq):
                per[prior] = dict(chosen=None, reason="missing runs"); continue
            checks = []
            chosen = None
            for i in range(len(seq) - 1):
                c, n = seq[i], seq[i + 1]
                dr = abs(c["tau_roof"] - n["tau_roof"]) / n["tau_roof"]
                dw = abs(c["tau_wall"] - n["tau_wall"]) / n["tau_wall"]
                ds = float(np.linalg.norm(np.subtract(c["shift"], n["shift"])))
                ok_s = c["enough_roof"] and (c["enough_wall"] is not False)
                ok = (dr <= 0.10) and (dw <= 0.10) and (ds <= 0.05) and ok_s
                checks.append(dict(band=c["band_m"], next=n["band_m"], d_tau_roof=round(dr, 4), d_tau_wall=round(dw, 4), d_shift_m=round(ds, 4),
                                   enough_samples=ok_s, stable=ok))
                if ok and chosen is None:
                    chosen = c["band_m"]
            per[prior] = dict(chosen=chosen, checks=checks,
                              reason=None if chosen is not None else "no band is stable against the next one (largest band cannot be checked)")
        if len(bands) == 1:
            out[b] = dict(bands=bands, per_prior=per, chosen_band=bands[0], note="outside the size rule (order 5.5: B173-only box)",
                          side_m=rows.get((f"{b}_b{int(bands[0])}", "LoD2"), {}).get("side_m"), over_limit=None)
            continue
        cb = [per[p]["chosen"] for p in ("LoD2", "ALS")]
        chosen = None if any(x is None for x in cb) else max(cb)
        side = rows[(f"{b}_b{int(chosen)}", "LoD2")]["side_m"] if chosen is not None else None
        out[b] = dict(bands=bands, per_prior=per, chosen_band=chosen, side_m=side,
                      over_limit=(max(side) > lim) if side else None)
    res = dict(task_id="PHD-MAIN-PREP-MEASURE-v1", step="06b box size rule", scientific_verdict=None,
               rule=bc["stability"], enough_samples=bc["enough_samples"], upper_limit_side_m=lim,
               rule_both_priors="the larger of the two per-prior chosen bands (box spec 21:45, before results)",
               rows=[dict(rid=k[0], **v) for k, v in rows.items()], boxes=out)
    jdump(OUT / "step06/box_stability.json", res)
    for b, v in out.items():
        print(b, "chosen", v["chosen_band"], "side", v.get("side_m"), "over", v.get("over_limit"),
              {p: v["per_prior"][p].get("chosen") for p in v["per_prior"]})


if __name__ == "__main__":
    main()

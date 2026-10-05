"""PHD-MAIN-PREP-MEASURE-v1 step 06d (jointbuildgs:dev, CPU): preliminary box-question table (5.5).

  python step06d_box_cases.py [--stage1-sub step03] [--gt-sub step04] [--cases-sub step05] [--tag search]

For every case box, the real cases of the search stage (5.4) whose judgment units (or blob centres) fall inside the box's
evaluation range, counted per question; tolerance = the search range's (preliminary: the box re-grading needs the box runs).
Search range of a box: B0 -> B0 crop, B173nb / B173 -> R2, R1rep -> R1, R4weak -> R4, R5agree -> R5, SWdemo -> SW.
Writes step06/box_questions_<tag>.json. scientific_verdict: null."""
import argparse
import csv
import json

import numpy as np

from common import OUT, jdump, xy_to_uv
from src.phd.prior_propagation_v4 import rule

SEARCH_OF = {"B0": "B0", "B173nb": "R2", "B173": "R2", "R1rep": "R1", "R4weak": "R4", "R5agree": "R5", "SWdemo": "SW"}


def in_eval(xy, b):
    uv = xy_to_uv(np.asarray(xy, float).reshape(-1, 2))
    return (uv[:, 0] >= b["eval_u"][0]) & (uv[:, 0] <= b["eval_u"][1]) & (uv[:, 1] >= b["eval_v"][0]) & (uv[:, 1] <= b["eval_v"][1])


def rcsv(p):
    try:
        with open(p) as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--stage1-sub", default="step03"); ap.add_argument("--gt-sub", default="step04")
    ap.add_argument("--cases-sub", default="step05"); ap.add_argument("--tag", default="search")
    ap.add_argument("--mode", default="search", choices=["search", "box"], help="box: the final box runs (user decision 23:02)")
    a = ap.parse_args()
    boxes = json.loads((OUT / "step06/boxes_v1.json").read_text())["boxes"]
    BOX_OF = {"B0": "B0_b10", "B173nb": "B173nb_b10", "B173": "B173_b0", "R1rep": "R1rep_b10"}
    if a.mode == "box":
        boxes = {k: v for k, v in boxes.items() if k in BOX_OF and (OUT / a.cases_sub / BOX_OF[k] / "cases.json").exists()}
    out = {}
    for bid, b in boxes.items():
        rid = SEARCH_OF[bid] if a.mode == "search" else BOX_OF[bid]
        q = dict(search_range=rid, eval_u=b["eval_u"], eval_v=b["eval_v"], label=b.get("label", ""))
        for prior in ("LoD2", "ALS"):
            U = dict(np.load(OUT / a.stage1_sub / rid / prior / "units.npz"))
            G = dict(np.load(OUT / a.gt_sub / rid / f"labels_{prior}.npz"))
            ev = in_eval(U["loc_center"][:, :2], b) & U["loc_in_range"] & ~G["excluded"]
            lab, med = G["label"], G["gt_med"].astype(float); tau = G["tau"].astype(float)
            st, vo, J, kind = U["state"], U["vote"], U["J"], U["loc_kind"]
            P = {}
            P["units_eval"] = int(ev.sum()); P["with_gt"] = int((ev & (lab >= 0)).sum())
            P["true_conflict"] = int((ev & (lab == 1)).sum())
            if prior == "LoD2":
                T = np.load(OUT / a.cases_sub / rid / "case1_unit_types_LoD2.npz")
                typ, bi = T["type"], T["bin"]
                P["q1_bins"] = {nm: int((ev & (bi == k)).sum()) for k, nm in enumerate(["<=1", "1-2", "2-4", ">4"])}
                P["q1_types"] = {t: int((ev & (typ == t)).sum()) for t in ["curved", "wall position", "eave", "rooftop structure", "other"]}
                P["q8_1to2tau"] = dict(roof=int((ev & (bi == 1) & (kind == 1)).sum()), wall=int((ev & (bi == 1) & (kind == 2)).sum()))
            M = np.load(OUT / a.cases_sub / rid / f"case2_missing_{prior}.npz")
            mu = M["unit"]; me = ev[mu]
            Jm, Lm = J[mu][me], lab[mu][me]
            P["q2"] = dict(missing_on_supported_surfaces=int(me.sum()),
                           propagated_conflict=int((Jm == rule.J_CONFLICT).sum()), propagated_agree=int((Jm == rule.J_AGREE).sum()),
                           mixed=int((Jm == rule.J_MIXED).sum()), insufficient=int((Jm == rule.J_INSUFF).sum()),
                           right=int((((Jm == rule.J_AGREE) & (Lm == 0)) | ((Jm == rule.J_CONFLICT) & (Lm == 1))).sum()),
                           wrong=int((((Jm == rule.J_AGREE) & (Lm == 1)) | ((Jm == rule.J_CONFLICT) & (Lm == 0))).sum()),
                           conflict_moved_right=int(((Jm == rule.J_CONFLICT) & (Lm == 1)).sum()), agree_moved_right=int(((Jm == rule.J_AGREE) & (Lm == 0)).sum()))
            inv = ev & (st == rule.ST_INVISIBLE)
            P["q4"] = dict(invisible=int(inv.sum()), with_gt=int((inv & (lab >= 0)).sum()), inherit_right=int((inv & (lab == 0)).sum()),
                           inherit_wrong=int((inv & (lab == 1)).sum()))
            F5 = np.load(OUT / a.cases_sub / rid / f"case5_units_{prior}.npz")
            P["q5"] = dict(prior_in_front=int(ev[F5["front"]].sum()), prior_behind=int(ev[F5["behind"]].sum()))
            ab = rcsv(OUT / a.cases_sub / rid / f"case5_absent_{prior}.csv")
            if ab:
                xy = np.array([[float(r["x"]), float(r["y"])] for r in ab]); m_ = in_eval(xy, b)
                P["q5"]["absent_blobs"] = int(m_.sum()); P["q5"]["absent_area_m2"] = float(sum(float(r["area_m2"]) for r, k in zip(ab, m_) if k))
            if prior == "LoD2":
                C5 = OUT / a.cases_sub / rid / "case5_cause_LoD2.npz"
                if C5.exists():
                    c5 = np.load(C5); e5 = ev[c5["unit"]]
                    P["q5"]["lod2_representation"] = int((c5["representation"] & e5).sum()); P["q5"]["lod2_change_candidate"] = int((c5["change_candidate"] & e5).sum())
            # tolerance sensitivity: true labels of the evaluation units with the tau of each band of this box (same GT values)
            stab = json.loads((OUT / "step06/box_stability.json").read_text()) if (a.mode == "search" and (OUT / "step06/box_stability.json").exists()) else None
            if stab:
                sens = {}
                has = ev & np.isfinite(med) & (G["gt_n"] >= 5)
                for rr in stab["rows"]:
                    if not rr["rid"].startswith(bid + "_b") or rr["prior"] != prior:
                        continue
                    tb = np.where(kind == 2, rr["tau_wall"], rr["tau_roof"])
                    sens[rr["rid"]] = dict(tau_roof=rr["tau_roof"], tau_wall=rr["tau_wall"], true_conflict=int((has & (np.abs(med) > tb)).sum()))
                base = (has & (lab == 1)).sum()
                P["tau_sensitivity"] = dict(search_tau_true_conflict=int(base), by_band=sens, units_with_gt=int(has.sum()))
            sup = ev & (st == rule.ST_SUPPORT)
            P["support"] = dict(units=int(sup.sum()), conflict=int((sup & (vo == rule.V_CONFLICT)).sum()),
                                right=int((sup & (((vo == rule.V_AGREE) & (lab == 0)) | ((vo == rule.V_CONFLICT) & (lab == 1)))).sum()),
                                wrong=int((sup & (((vo == rule.V_AGREE) & (lab == 1)) | ((vo == rule.V_CONFLICT) & (lab == 0)))).sum()))
            q[prior] = P
        for kk in ("a", "b"):
            bl = rcsv(OUT / a.cases_sub / rid / f"case3_blobs_{kk}.csv")
            if bl:
                xy = np.array([[float(r["x"]), float(r["y"])] for r in bl]); m_ = in_eval(xy, b)
                q[f"q3_blobs_{kk}"] = dict(blobs=int(m_.sum()), area_m2=float(sum(float(r["area_m2"]) for r, k in zip(bl, m_) if k)))
        q["q6"] = "B0 conditions (A15 / A9 / A3 / COVER)" if bid == "B0" else None
        q["q7"] = "mostly changed scene" if bid == "B173" else None
        q["q9"] = {"R1rep": "R1 80 m tiles", "R4weak": "R4 80 m tiles"}.get(bid)
        out[bid] = q
    jdump(OUT / f"step06/box_questions_{a.tag}.json", dict(task_id="PHD-MAIN-PREP-MEASURE-v1", step="06d box-question table (preliminary)",
                                                          tolerance="search range (box re-grading pending the size decision)", boxes=out, scientific_verdict=None))
    for bid, q in out.items():
        print(bid, q["search_range"], "LoD2 q1", q["LoD2"].get("q1_bins"), "q2", q["LoD2"]["q2"]["right"], q["LoD2"]["q2"]["wrong"], "ALS q2", q["ALS"]["q2"]["right"], q["ALS"]["q2"]["wrong"])


if __name__ == "__main__":
    main()

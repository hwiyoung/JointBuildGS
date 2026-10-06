"""PHD-MAIN-STAGE0-v1 5.1 checks 2 and 3: v6 against v5 on the four boxes (jointbuildgs:dev, CPU; rules fixed in
configs/phd/main_stage0_v1/stage0_v1.json check_51 before any result).

  python compare_51.py [--v6 s61/box] [--v6-gt s61/box_gt] [--out compare51]

Per box x prior (same cells in both versions, aligned by index):
  store fix     v5 current (/dr/s52/box units, /dr/rules/decisions) against v6 current (vote_tau, J_tau); also v5 margin_all_2
                against v6 margin_all_2 (rules.apply on the v6 tallies) = the fix under the new rule
  rule default  v6 current against v6 with the rule of the run (units vote / J; LoD2 current, ALS margin_all_2)
  counted       changed states / votes / propagated judgments / discard decisions among the judged patches (support + missing)
                of the box (loc_in_range) and of its evaluation range; the stop rule of check_51 (LoD2 and unshifted runs
                identical; store-fix change of the discard decisions <= 3 % of the judged patches)
  labels        wrong discard (discarded true agree) / wrong keep (kept true conflict) by face kind and measured / unmeasured,
                invisible apart, as the discard task's rules_eval (v5 decisions with the v5 labels, v6 with the v6 labels; and
                v5 decisions with the v6 labels = the decision change alone); label changes v5 -> v6 split into the read-back
                of the GT points from their float32 file (v5 code on the same points, --v5code-gt) and the store fix;
                unplanted points (LoD2 patches, ALS TIN vertices)
Writes <out>/compare.json, compare_long.csv. scientific_verdict: null."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from common import CFG, DR, OUT, PREP, SCFG, inside_range, jdump, log, xy_to_uv
from src.phd.prior_propagation_v6 import locations as locs
from src.phd.prior_propagation_v6 import rule
from src.phd.prior_propagation_v6 import rules as R
from src.phd.prior_propagation_v6 import surfaces as surf

BOXES = {"B0_b10": "B0", "B173nb_b10": "B173nb", "B173_b0": "B173", "R1rep_b10": "R1rep"}
JUDGED = (rule.ST_SUPPORT, rule.ST_MISSING)


def labels_of(gt_dir, prior, rid):
    G = np.load(gt_dir / f"labels_{prior}.npz")
    lab, ex = G["label"].astype(np.int8), G["excluded"]
    if rid.startswith("B0") and (gt_dir / f"labels_uls_{prior}.npz").exists():
        Gu = np.load(gt_dir / f"labels_uls_{prior}.npz")
        use = (lab < 0) & (Gu["label"] >= 0)
        lab = np.where(use, Gu["label"], lab).astype(np.int8); ex = ex | (use & Gu["excluded"])
    return lab, ex


def eval_mask(centres_xy, bid):
    b = json.loads((PREP / "step06/boxes_v1.json").read_text())["boxes"][bid]
    uv = xy_to_uv(centres_xy)
    return (uv[:, 0] >= b["eval_u"][0]) & (uv[:, 0] <= b["eval_u"][1]) & (uv[:, 1] >= b["eval_v"][0]) & (uv[:, 1] <= b["eval_v"][1])


def als_vertices(run_dir, U, J_loc, moved):
    summ = json.loads((run_dir / "summary.json").read_text())
    md = Path(summ["mesh_dir"]); shift = np.asarray(summ["registration"]["shift_applied"], np.float64)
    if not moved and str(md).startswith("/out/"):      # a v5 summary records the discard task's own container path (/out = /dr here)
        md = DR / str(md)[len("/out/"):]
    m = dict(np.load(md / "als_mesh.npz"))
    Vv = m["V"].astype(np.float64) + shift; F = m["F"].astype(np.int64); ts = m["tri_surface"].astype(np.int64)
    eligible = np.zeros(int(ts.max()) + 2, bool)
    for r_ in json.loads((md / "als_surfaces.json").read_text())["surfaces"]:
        eligible[r_["ext"]] = True
    vs = surf.vertex_surface(F, ts, eligible)
    ci = np.where(vs >= 0, locs.compact_index(U, np.maximum(vs, 0)), -1)
    has = ci >= 0; seat = np.full(len(Vv), -1, np.int64)
    seat[has] = locs.locate(U, ci[has], Vv[has])          # v5: the unmoved store (its own lookup); v6: the moved store
    inr = inside_range(Vv[:, :2], json.loads((md / "range.json").read_text()))
    bad = has & (J_loc[np.maximum(seat, 0)] == rule.J_CONFLICT) & (U["state"][np.maximum(seat, 0)] == rule.ST_MISSING)
    return int((bad & inr).sum())


def counts(state, disc, lab, ex, kind, region, prior):
    base = region & ~ex & (lab >= 0)
    c = {}
    for kn, kv in (("roof", 1), ("wall", 2)):
        if prior == "ALS" and kv == 2:
            continue
        for mn, sv in (("measured", rule.ST_SUPPORT), ("unmeasured", rule.ST_MISSING)):
            m = base & (kind == kv) & (state == sv)
            c[f"{kn}_{mn}"] = dict(n=int(m.sum()), true_conflict=int((m & (lab == 1)).sum()), discard=int((m & disc).sum()),
                                   correct_discard=int((m & disc & (lab == 1)).sum()), wrong_discard=int((m & disc & (lab == 0)).sum()),
                                   correct_keep=int((m & ~disc & (lab == 0)).sum()), wrong_keep=int((m & ~disc & (lab == 1)).sum()))
        mi = base & (kind == kv) & (state == rule.ST_INVISIBLE)
        c[f"{kn}_invisible"] = dict(n=int(mi.sum()), true_conflict=int((mi & (lab == 1)).sum()))
    tot = {k: sum(v.get(k, 0) for kk, v in c.items() if not kk.endswith("invisible")) for k in ("n", "discard", "wrong_discard", "wrong_keep", "correct_discard", "correct_keep")}
    c["judged_total"] = tot
    return c


def diff(a_state, a_vote, a_J, a_disc, b_state, b_vote, b_J, b_disc, region):
    judged = np.isin(a_state, JUDGED) | np.isin(b_state, JUDGED)
    m = region & judged
    return dict(judged=int(m.sum()), state=int((m & (a_state != b_state)).sum()), vote=int((m & (a_vote != b_vote)).sum()),
                J=int((m & (a_J != b_J)).sum()), discard=int((m & (a_disc != b_disc)).sum()),
                discard_share=round(float((m & (a_disc != b_disc)).sum()) / max(int(m.sum()), 1), 5),
                discard_to_keep=int((m & a_disc & ~b_disc).sum()), keep_to_discard=int((m & ~a_disc & b_disc).sum()))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--v6", default="s61/box"); ap.add_argument("--v6-gt", default="s61/box_gt")
    ap.add_argument("--out", default="compare51")
    ap.add_argument("--v5code-gt", default="s61/box_gt_v5code", help="labels of the v5 code from the same (float32) GT points as v6")
    a = ap.parse_args()
    O = OUT / a.out; O.mkdir(parents=True, exist_ok=True)
    jc = CFG["judgment"]; q, k, r = jc["majority"], int(jc["min_evidence"]), float(jc["max_distance_m"])
    res, rows, stop = {}, [], []
    for box, bid in BOXES.items():
        for prior in ("LoD2", "ALS"):
            r5, r6 = DR / "s52/box" / box / prior, OUT / a.v6 / box / prior
            U5, U6 = np.load(r5 / "units.npz"), np.load(r6 / "units.npz")
            if len(U5["state"]) != len(U6["state"]) or not np.array_equal(U5["loc_surface"], U6["loc_surface"]):
                raise RuntimeError(f"{box} {prior}: v5 and v6 cells differ")
            sh = np.asarray(json.loads((r6 / "summary.json").read_text())["registration"]["shift_applied"], np.float64)
            dec5 = np.load(DR / "rules/decisions" / f"{box}_{prior}.npz")
            pairs = dict(np.load(r6 / "unit_view_pairs.npz")); kn = np.load(r6 / "knn.npz")
            L = len(U6["state"])
            st6 = U6["state"]
            d6 = {}
            for nm in ("current", "margin_all_2"):
                s_, v_, J_, dd = R.apply(pairs, L, kn["mis"], kn["k_dist"], kn["k_id"], nm, q, k, r)
                d6[nm] = dict(vote=v_, J=J_, disc=dd)
            assert np.array_equal(d6["current"]["vote"], U6["vote_tau"]) and np.array_equal(d6["current"]["J"], U6["J_tau"])
            rule_run = str(U6["rule"])
            d6["rule"] = dict(vote=U6["vote"], J=U6["J"], disc=R.discard(st6, U6["vote"], U6["J"]))
            # v5 decisions: votes / judgments of the stored current run; margin_all_2 by rules.apply on the v5 tallies
            pairs5 = dict(np.load(r5 / "unit_view_pairs.npz")); kn5 = np.load(r5 / "knn.npz")
            d5 = {}
            for nm in ("current", "margin_all_2"):
                s_, v_, J_, dd = R.apply(pairs5, L, kn5["mis"], kn5["k_dist"], kn5["k_id"], nm, q, k, r)
                if not np.array_equal(dd, dec5[nm]):
                    raise RuntimeError(f"{box} {prior} {nm}: v5 decisions differ from the discard task's file")
                d5[nm] = dict(vote=v_, J=J_, disc=dd)
            lab5, ex5 = labels_of(DR / "s52/box_gt" / box, prior, box)
            lab6, ex6 = labels_of(OUT / a.v6_gt / box, prior, box)
            v5f = OUT / a.v5code_gt / box
            lab5f, ex5f = labels_of(v5f, prior, box) if (v5f / f"labels_{prior}.npz").exists() else (None, None)
            in5 = U5["loc_in_range"]; in6 = U6["loc_in_range"]
            ev5 = eval_mask(U5["loc_center"][:, :2] + sh[:2], bid) & in5; ev6 = eval_mask(U6["loc_center"][:, :2], bid) & in6
            box_any = in5 | in6
            ent = dict(shift=sh.tolist(), rule_of_run=rule_run, cells=L,
                       loc_in_range_changed=int((in5 != in6).sum()), labels_changed=int((box_any & (lab5 != lab6)).sum()),
                       labels_v5=dict(agree=int((in5 & (lab5 == 0)).sum()), conflict=int((in5 & (lab5 == 1)).sum())),
                       labels_v6=dict(agree=int((in6 & (lab6 == 0)).sum()), conflict=int((in6 & (lab6 == 1)).sum())))
            if lab5f is not None:   # label changes split: reading the GT points back from their float32 file / the store fix
                ent["labels_changed_float32_readback"] = int((box_any & (lab5 != lab5f)).sum())
                ent["labels_changed_store_fix"] = int((box_any & (lab5f != lab6)).sum())
            for reg, m5, m6 in (("box", in5, in6), ("evaluation", ev5, ev6)):
                mm = m5 | m6
                ent[f"store_fix_current_{reg}"] = diff(U5["state"], d5["current"]["vote"], d5["current"]["J"], d5["current"]["disc"],
                                                      st6, d6["current"]["vote"], d6["current"]["J"], d6["current"]["disc"], mm)
                ent[f"store_fix_margin_all_2_{reg}"] = diff(U5["state"], d5["margin_all_2"]["vote"], d5["margin_all_2"]["J"], d5["margin_all_2"]["disc"],
                                                           st6, d6["margin_all_2"]["vote"], d6["margin_all_2"]["J"], d6["margin_all_2"]["disc"], mm)
                ent[f"rule_default_{reg}"] = diff(st6, d6["current"]["vote"], d6["current"]["J"], d6["current"]["disc"],
                                                 st6, d6["rule"]["vote"], d6["rule"]["J"], d6["rule"]["disc"], m6)
                for tag, U_, d_, lab, ex, m in (("v5_current", U5, d5["current"], lab5, ex5, m5), ("v5_margin_all_2", U5, d5["margin_all_2"], lab5, ex5, m5),
                                               ("v5_current_v6labels", U5, d5["current"], lab6, ex6, m6), ("v5_margin_all_2_v6labels", U5, d5["margin_all_2"], lab6, ex6, m6),
                                               ("v6_current", U6, d6["current"], lab6, ex6, m6), ("v6_margin_all_2", U6, d6["margin_all_2"], lab6, ex6, m6),
                                               ("v6_rule", U6, d6["rule"], lab6, ex6, m6)):
                    c = counts(U_["state"], d_["disc"], lab, ex, U_["loc_kind"], m, prior)
                    ent[f"labels_{tag}_{reg}"] = c
                    for part, v in c.items():
                        if part == "judged_total":
                            continue
                        rows.append(dict(box=box, prior=prior, region=reg, decisions=tag, part=part, **v))
            # unplanted
            if prior == "LoD2":
                for tag, U_, d_, m in (("v5_current", U5, d5["current"], in5), ("v6_current", U6, d6["current"], in6), ("v6_rule", U6, d6["rule"], in6)):
                    Jl = locs.location_judgment(U_["state"], d_["vote"], d_["J"])
                    ent[f"unplanted_{tag}"] = int(((U_["state"] == rule.ST_MISSING) & (Jl == rule.J_CONFLICT) & m).sum())
            else:
                for tag, U_, d_, rd in (("v5_current", U5, d5["current"], r5), ("v5_margin_all_2", U5, d5["margin_all_2"], r5),
                                        ("v6_current", U6, d6["current"], r6), ("v6_rule", U6, d6["rule"], r6)):
                    ent[f"unplanted_{tag}"] = als_vertices(rd, U_, locs.location_judgment(U_["state"], d_["vote"], d_["J"]), tag.startswith("v6"))
            # stop rule (check_51.stop_rule)
            fix_c, fix_m = ent["store_fix_current_box"], ent["store_fix_margin_all_2_box"]
            if not np.any(sh):
                if any(fix_c[x] for x in ("state", "vote", "J", "discard")) or any(fix_m[x] for x in ("state", "vote", "J", "discard")):
                    stop.append(f"{box} {prior}: no shift but v6 differs from v5 ({fix_c}, {fix_m})")
            elif max(fix_c["discard_share"], fix_m["discard_share"]) > 0.03:
                stop.append(f"{box} {prior}: store fix changes {fix_c['discard_share']:.2%} / {fix_m['discard_share']:.2%} of the discard decisions (> 3 %)")
            res[f"{box}/{prior}"] = ent
            log(box, prior, "store fix", fix_c["discard"], fix_c["discard_share"], "rule", ent["rule_default_box"]["discard"])
    jdump(O / "compare.json", dict(rule=__doc__.split("\n\n")[1], runs=res, stop_rule=SCFG["check_51"]["stop_rule"], stop=stop, scientific_verdict=None))
    keys = sorted({kk for r_ in rows for kk in r_})
    with open(O / "compare_long.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    print("STOP" if stop else "within the stop rule", stop)


if __name__ == "__main__":
    main()

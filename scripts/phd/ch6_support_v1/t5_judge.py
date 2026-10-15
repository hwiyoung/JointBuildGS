"""PHD-CH6-SUPPORT-v1 task 5: the pre-training judgment of the final code against the true labels, over the seven search
ranges (selection area) and the four experiment regions (evaluation area) (jointbuildgs:dev, CPU; definitions = configs
ch6_support_v1.json 'task5_judgment', written before any result).

  python t5_judge.py

Per patch: truth = label (0 prior right, 1 prior wrong, base tau), judgment = J_loc of the v6 run (rule auto), release = J_loc
conflict, keep = everything else (mixed / insufficient also counted apart as 'undetermined', invisible = no judgment).
Item per patch from the region codes (ranges: stage-0 rule on the patch medians; boxes: region files v3) -> ch6_common.ITEMS.
Areas: selection = range patches outside every box evaluation range, deduplicated in the order of the ranges; evaluation =
box evaluation ranges (B173_b0 reported apart: it lies inside B173nb_b10). Supplements: confidence-excluded wrong observations
(mask-off runs), B173_b0 with its own tolerance and registration, per-building concentration of the wrong decisions.
Writes /out/t5/judge/{counts.json, counts_long.csv, buildings.csv, concentration.json, patches/<run>_<prior>.npz}.
scientific_verdict: null."""
import csv
import json
from collections import defaultdict

import numpy as np

from ch6_common import (BOXES, CCFG, DR, FIX, ITEMS, OUT, PRIORS, RANGES, RNGDEF, S0, S1, codes_from, footprint_index, in_eval_rect,
                        inside_range, items_from, jdump, labels_of, log, rule, xy_to_uv)

O = OUT / "t5/judge"
(O / "patches").mkdir(parents=True, exist_ok=True)
S, M, I = rule.ST_SUPPORT, rule.ST_MISSING, rule.ST_INVISIBLE
GROUPS = (("direct", S), ("propagated", M), ("none", I))
CATS = ("correct_keep", "wrong_keep", "correct_release", "wrong_release")


def cats(rel, lab):
    return dict(correct_keep=~rel & (lab == 0), wrong_keep=~rel & (lab == 1), correct_release=rel & (lab == 1), wrong_release=rel & (lab == 0))


def tally(R, mask):
    """{item|group: {cat: [area m2, patches], undetermined: [..]}} and per-item totals over groups."""
    out = {}
    C = cats(R["rel"], R["lab"])
    und = np.isin(R["J"], (rule.J_MIXED, rule.J_INSUFF))
    for ii, (k, _) in enumerate(ITEMS):
        m = mask & (R["item"] == ii)
        for gname, sv in GROUPS:
            mm = m & (R["st"] == sv)
            if not mm.any():
                continue
            d = {c: [round(float(R["area"][mm & C[c]].sum()), 3), int((mm & C[c]).sum())] for c in CATS}
            d["undetermined"] = [round(float(R["area"][mm & und].sum()), 3), int((mm & und).sum())]
            out[f"{k}|{gname}"] = d
    return out


def add(a, b):
    for key, d in b.items():
        t = a.setdefault(key, {c: [0.0, 0] for c in CATS + ("undetermined",)})
        for c, (ar, n) in d.items():
            t[c][0] = round(t[c][0] + ar, 3); t[c][1] += n
    return a


def load_range(rid, prior):
    run = OUT / "t5/s03" / rid / prior
    U = np.load(run / "units.npz")
    summ = json.loads((run / "summary.json").read_text())
    lab, med, tau, ex = labels_of(OUT / "t5/gt" / rid, prior, rid)
    st = U["state"]; mvs = -U["mvs_r_med"].astype(np.float64)
    inr = U["loc_in_range"].astype(bool)
    code, premise = codes_from(lab, med, tau, ex, st, mvs, inr, prior)
    R = dict(xy=U["loc_center"][:, :2].astype(np.float64), area=U["loc_area"].astype(np.float64), kind=U["loc_kind"], st=st, J=U["J_loc"],
             rel=U["J_loc"] == rule.J_CONFLICT, lab=lab, med=med, tau=tau, ex=ex, mvs=mvs, code=code, premise=premise, inr=inr,
             item=items_from(code, premise, med, tau), shift=np.asarray(U["frame_shift"], np.float64), summ=summ)
    R["fp"], R["fp_names"] = footprint_index(DR / "s02" / rid / "footprints.json", R["xy"])
    return R


def load_box(box, prior):
    run = S0 / "s61/box" / box / prior
    U = np.load(run / "units.npz")
    G = np.load(S1 / "regions_v3" / f"regions_ext_v3_{box}_{prior}.npz")
    if not np.array_equal(G["state"], U["state"]):
        raise RuntimeError(f"{box} {prior}: region v3 states differ from the stage-0 run")
    code = G["code_ext_v3"].astype(np.int8); premise = G["premise_violation"].astype(bool)
    med = G["gt_med"].astype(np.float64); tau = G["tau"].astype(np.float64)
    lab = np.where(np.isin(code, (2, 3, 4, 5)), 0, np.where(np.isin(code, (11, 12, 13, 14)), 1, -1)).astype(np.int8)
    R = dict(xy=U["loc_center"][:, :2].astype(np.float64), area=U["loc_area"].astype(np.float64), kind=U["loc_kind"], st=U["state"], J=U["J_loc"],
             rel=U["J_loc"] == rule.J_CONFLICT, lab=lab, med=med, tau=tau, mvs=G["mvs_minus_prior"].astype(np.float64), code=code,
             premise=premise, inr=G["in_eval"].astype(bool), item=items_from(code, premise, med, tau),
             shift=np.asarray(U["frame_shift"], np.float64), summ=json.loads((run / "summary.json").read_text()))
    R["ex"] = (code == 0)
    R["fp"], R["fp_names"] = footprint_index(DR / "s02_box" / box / "footprints.json", R["xy"])
    return R


def maskoff_flags(R, U_off):
    """prior right, the mask-off median wrong, and the mask-on side missing or right: wrong observations the mask excluded."""
    if not np.array_equal(np.asarray(U_off["frame_shift"], np.float64), R["shift"]):
        raise RuntimeError("mask-off run with another registration")
    m_off = -U_off["mvs_r_med"].astype(np.float64); st_off = U_off["state"]
    raw_wrong = (st_off == S) & np.isfinite(m_off) & (np.abs(m_off - R["med"]) > R["tau"])
    on_ok = (R["st"] == M) | ((R["st"] == S) & (np.abs(R["mvs"] - R["med"]) <= R["tau"]))
    return (R["lab"] == 0) & (R["code"] > 0) & raw_wrong & on_ok


def conc(rows_area, key):
    """concentration of one wrong-decision kind over buildings."""
    tot = sum(v[key] for v in rows_area.values())
    s = sorted(((v[key], b) for b, v in rows_area.items()), reverse=True)
    acc, n50, n80 = 0.0, None, None
    for i, (a, _) in enumerate(s):
        acc += a
        if n50 is None and acc >= 0.5 * tot:
            n50 = i + 1
        if n80 is None and acc >= 0.8 * tot:
            n80 = i + 1
    return dict(total_m2=round(tot, 2), buildings_with_any=int(sum(1 for a, _ in s if a > 0)), buildings=len(s),
                top1=[s[0][1], round(s[0][0], 2), round(s[0][0] / tot, 4)] if tot > 0 else None,
                top5_share=round(sum(a for a, _ in s[:5]) / tot, 4) if tot > 0 else None, n_for_50pct=n50, n_for_80pct=n80,
                top10=[[b, round(a, 2)] for a, b in s[:10]])


def main():
    res = dict(definitions=CCFG["task5_judgment"], items=ITEMS, selection={}, selection_per_range={}, evaluation={}, maskoff={},
               b173_self={}, checks={}, concentration={})
    rows = []
    bld = defaultdict(lambda: defaultdict(float))       # (area kind, prior, building) -> sums
    for prior in PRIORS:
        res["selection"][prior] = {}
        for idx, rid in enumerate(RANGES):
            R = load_range(rid, prior)
            uv = xy_to_uv(R["xy"])
            in_eval = np.zeros(len(uv), bool)
            for b in ("B0", "B173nb", "B173", "R1rep"):
                in_eval |= in_eval_rect(uv, b)
            earlier = np.zeros(len(uv), bool)
            for rp in RANGES[:idx]:
                earlier |= inside_range(R["xy"], RNGDEF[rp])
            base = R["inr"] & (R["item"] >= 0)
            sel = base & ~in_eval
            seld = sel & ~earlier
            t_r = tally(R, sel); t_d = tally(R, seld)
            res["selection_per_range"][f"{rid}/{prior}"] = t_r
            add(res["selection"][prior], t_d)
            # v5 comparison (discard task decisions of the same rule on the same patch ids)
            rname = "current" if prior == "LoD2" else "margin_all_2"
            dec = np.load(DR / "rules/decisions" / f"{rid}_{prior}.npz")[rname]
            v5 = json.loads((DR / "s52/s03" / rid / prior / "summary.json").read_text())
            res["checks"][f"{rid}/{prior}"] = dict(
                patches=int(len(R["st"])), release_same_as_v5=round(float((dec == R["rel"])[base].mean()), 5),
                tau_v6={k: round(v["tau"], 4) for k, v in R["summ"]["tolerance"].items()}, tau_v5={k: round(v["tau"], 4) for k, v in v5["tolerance"].items()},
                shift_v6=[round(x, 4) for x in R["summ"]["registration"]["shift_applied"]], shift_v5=[round(x, 4) for x in v5["registration"]["shift_applied"]],
                rule=str(np.load(OUT / "t5/s03" / rid / prior / "units.npz")["rule"]))
            # mask-off supplement
            mo = OUT / "t5/s03_maskoff" / rid / prior / "units.npz"
            if mo.exists():
                ce = maskoff_flags(R, np.load(mo)) & seld
                R2 = dict(R); R2["item"] = np.where(ce, 0, -1).astype(np.int8)
                add(res["maskoff"].setdefault(f"selection/{prior}", {}), {k.replace("both_right", "conf_excluded_wrong"): v for k, v in tally(R2, ce).items()})
            # per building (deduplicated selection area)
            C = cats(R["rel"], R["lab"])
            for c in CATS:
                m = seld & C[c]
                if m.any():
                    sums = np.bincount(R["fp"][m] + 1, weights=R["area"][m])
                    for fi in np.nonzero(sums)[0]:
                        name = R["fp_names"][fi - 1] if fi > 0 else "(발자국 밖)"
                        bld[("selection", prior, name)][c] += float(sums[fi])
                        bld[("selection", prior, name)].setdefault("range", rid)
            np.savez_compressed(O / "patches" / f"{rid}_{prior}.npz", xy=R["xy"].astype(np.float32), area=R["area"].astype(np.float32),
                                item=R["item"], rel=R["rel"], lab=R["lab"], st=R["st"], sel=seld, fp=R["fp"].astype(np.int32),
                                fp_names=np.array(R["fp_names"]), kind=R["kind"], med=R["med"].astype(np.float32), tau=R["tau"].astype(np.float32))
            for key, d in t_r.items():
                it, g = key.split("|")
                for c in CATS + ("undetermined",):
                    rows.append(dict(area_kind="selection_per_range", run=rid, prior=prior, item=it, group=g, cat=c, area_m2=d[c][0], patches=d[c][1]))
            log("selection", rid, prior, "patches", int(base.sum()), "selection", int(sel.sum()), "dedup", int(seld.sum()))
        for key, d in res["selection"][prior].items():
            it, g = key.split("|")
            for c in CATS + ("undetermined",):
                rows.append(dict(area_kind="selection", run="all", prior=prior, item=it, group=g, cat=c, area_m2=d[c][0], patches=d[c][1]))
    for box in BOXES:
        for prior in PRIORS:
            R = load_box(box, prior)
            ev = R["inr"] & (R["item"] >= 0)
            t = tally(R, ev)
            res["evaluation"][f"{box}/{prior}"] = t
            for key, d in t.items():
                it, g = key.split("|")
                for c in CATS + ("undetermined",):
                    rows.append(dict(area_kind="evaluation", run=box, prior=prior, item=it, group=g, cat=c, area_m2=d[c][0], patches=d[c][1]))
            mo = OUT / "t5/box_maskoff" / box / prior / "units.npz"
            if not mo.exists():
                mo = S0 / "s61/box_maskoff" / box / prior / "units.npz"
            if mo.exists():
                ce = maskoff_flags(R, np.load(mo)) & ev
                R2 = dict(R); R2["item"] = np.where(ce, 0, -1).astype(np.int8)
                res["maskoff"][f"{box}/{prior}"] = {k.replace("both_right", "conf_excluded_wrong"): v for k, v in tally(R2, ce).items()}
                res["maskoff"][f"{box}/{prior}"]["source"] = str(mo)
            C = cats(R["rel"], R["lab"])
            for c in CATS:
                m = ev & C[c]
                if m.any():
                    sums = np.bincount(R["fp"][m] + 1, weights=R["area"][m])
                    for fi in np.nonzero(sums)[0]:
                        name = R["fp_names"][fi - 1] if fi > 0 else "(발자국 밖)"
                        bld[(box, prior, name)][c] += float(sums[fi])
            np.savez_compressed(O / "patches" / f"{box}_{prior}.npz", xy=R["xy"].astype(np.float32), area=R["area"].astype(np.float32),
                                item=R["item"], rel=R["rel"], lab=R["lab"], st=R["st"], sel=ev, fp=R["fp"].astype(np.int32),
                                fp_names=np.array(R["fp_names"]), kind=R["kind"], med=R["med"].astype(np.float32), tau=R["tau"].astype(np.float32))
            log("evaluation", box, prior, "patches", int(ev.sum()))
    # B173_b0 with its own tolerance and registration (truth on the same fixed tau as the stage-0 run)
    for prior in PRIORS:
        run = OUT / "t5/b173self/B173_b0" / prior
        if not (run / "units.npz").exists():
            continue
        U = np.load(run / "units.npz")
        G = np.load(OUT / "t5/b173self_gt/B173_b0" / f"labels_{prior}.npz")
        fixed = json.loads((S0 / "s61/box/B173_b0" / prior / "summary.json").read_text())["tolerance"]
        own = json.loads((run / "summary.json").read_text())
        tau_fix = np.where(U["loc_kind"] == 2, fixed["wall"]["tau"], fixed["roof"]["tau"])
        med = G["gt_med"].astype(np.float64); has = G["label"] >= 0
        lab = np.where(has, (np.abs(med) > tau_fix).astype(np.int8), -1).astype(np.int8)
        ex = G["excluded"].astype(bool)
        ev = in_eval_rect(xy_to_uv(U["loc_center"][:, :2]), "B173") & U["loc_in_range"].astype(bool) & ~ex & (lab >= 0)
        rel = U["J_loc"] == rule.J_CONFLICT
        C = cats(rel, lab)
        d = {}
        for gname, sv in GROUPS:
            mm = ev & (U["state"] == sv)
            d[gname] = {c: [round(float(U["loc_area"][mm & C[c]].sum()), 2), int((mm & C[c]).sum())] for c in CATS}
        d["all"] = {c: [round(float(U["loc_area"][ev & C[c]].sum()), 2), int((ev & C[c]).sum())] for c in CATS}
        d["own_tau"] = {k: round(v["tau"], 3) for k, v in own["tolerance"].items()}
        d["own_shift"] = [round(x, 3) for x in own["registration"]["shift_applied"]]
        d["truth_tau_fixed"] = {k: round(v["tau"], 3) for k, v in fixed.items()}
        d["state_area"] = {gname: round(float(U["loc_area"][ev & (U["state"] == sv)].sum()), 2) for gname, sv in GROUPS}
        res["b173_self"][prior] = d
        log("b173 self", prior, d["all"])
    # concentration
    groups = defaultdict(dict)
    for (ak, prior, name), v in bld.items():
        groups[(ak, prior)][name] = {c: v.get(c, 0.0) for c in CATS}
    for (ak, prior), rows_area in groups.items():
        res["concentration"][f"{ak}/{prior}"] = {c: conc(rows_area, c) for c in ("wrong_release", "wrong_keep")}
    with open(O / "buildings.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["area_kind", "prior", "building", "range"] + list(CATS) + ["released_share_of_prior_right"])
        for (ak, prior, name), v in sorted(bld.items()):
            pr = v.get("correct_keep", 0) + v.get("wrong_release", 0)
            w.writerow([ak, prior, name, v.get("range", "")] + [round(v.get(c, 0.0), 2) for c in CATS] + [round(v.get("wrong_release", 0) / pr, 4) if pr > 0 else ""])
    jdump(O / "counts.json", dict(**res, scientific_verdict=None))
    with open(O / "counts_long.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print("t5 done", len(rows), "rows")


if __name__ == "__main__":
    main()

"""PHD-MAIN-STAGE1-v1 3.6: counts of the pre-training judgment of every variant against the v3 true labels (jointbuildgs:dev, CPU).

  python sens_count.py      -> /out/sens/counts.json, /out/sens/counts.md

Per variant x site x prior (patches in the box evaluation range, not excluded, with a true label; roof-like / wall-like; measured =
support, unmeasured = missing; invisible apart): correct keep (judged agree, true agree), wrong keep (agree, true conflict), correct
release (judged conflict, true conflict), wrong release (conflict, true agree), undetermined (mixed / insufficient: inherited) - as
patches and as area (m2; patch sizes differ between variants). 'current' = the stage-0 box run (s61/box); the confidence variants are
also compared with their re-implementation at the current values (conf_current). Changed judgments (J_loc differs from the reference,
same store) per variant; the propagation value with the most changes is named. Labels: the v3 labels (/out/v3/box_gt); patch-size
variants: the labels made on their store with the v3 GT (/out/sens/<variant>/box_gt). scientific_verdict: null."""
import json
from pathlib import Path

import numpy as np

from s1_common import OUT, S0, SITES, boxes, jdump, xy_to_uv
from src.phd.prior_propagation_v6 import rule

VARIANTS = ["conf_current", "conf_strict", "conf_loose", "patch_0125", "patch_05", "majority_half", "majority_34", "min_evidence_3",
            "min_evidence_10", "max_distance_05", "max_distance_2"]
PROP = ["majority_half", "majority_34", "min_evidence_3", "min_evidence_10", "max_distance_05", "max_distance_2"]


def labels_of(gt_dir, site, prior):
    G = np.load(Path(gt_dir) / site / f"labels_{prior}.npz")
    lab, ex = G["label"].astype(np.int8), G["excluded"]
    if site.startswith("B0") and (Path(gt_dir) / site / f"labels_uls_{prior}.npz").exists():
        Gu = np.load(Path(gt_dir) / site / f"labels_uls_{prior}.npz")
        use = (lab < 0) & (Gu["label"] >= 0)
        lab = np.where(use, Gu["label"], lab).astype(np.int8)
        ex = ex | (use & Gu["excluded"])
    return lab, ex


def counts(U, lab, ex, box):
    uv = xy_to_uv(U["loc_center"][:, :2])
    inev = (uv[:, 0] >= box["eval_u"][0]) & (uv[:, 0] <= box["eval_u"][1]) & (uv[:, 1] >= box["eval_v"][0]) & (uv[:, 1] <= box["eval_v"][1]) & U["loc_in_range"]
    base = inev & ~ex & (lab >= 0)
    J, st, kind, area = U["J_loc"], U["state"], U["loc_kind"], U["loc_area"].astype(np.float64)
    out = {}
    for kn, kv in (("roof", 1), ("wall", 2)):
        for sn, sv in (("measured", rule.ST_SUPPORT), ("unmeasured", rule.ST_MISSING)):
            m = base & (kind == kv) & (st == sv)
            if not m.any():
                continue
            cats = dict(correct_keep=m & (J == rule.J_AGREE) & (lab == 0), wrong_keep=m & (J == rule.J_AGREE) & (lab == 1),
                        correct_release=m & (J == rule.J_CONFLICT) & (lab == 1), wrong_release=m & (J == rule.J_CONFLICT) & (lab == 0),
                        undetermined=m & np.isin(J, (rule.J_MIXED, rule.J_INSUFF)))
            out[f"{kn}_{sn}"] = {k: dict(patches=int(v.sum()), area_m2=round(float(area[v].sum()), 1)) for k, v in cats.items()}
        mi = base & (kind == kv) & (st == rule.ST_INVISIBLE)
        if mi.any():
            out[f"{kn}_invisible"] = dict(patches=int(mi.sum()), area_m2=round(float(area[mi].sum()), 1))
    tot = {}
    for k in ("correct_keep", "wrong_keep", "correct_release", "wrong_release", "undetermined"):
        tot[k] = dict(patches=sum(v[k]["patches"] for kk, v in out.items() if not kk.endswith("invisible")),
                      area_m2=round(sum(v[k]["area_m2"] for kk, v in out.items() if not kk.endswith("invisible")), 1))
    out["total"] = tot
    return out, base


def main():
    bx = boxes()
    res, changes, md = {}, {}, []
    for site in SITES:
        box = bx[SITES[site]]
        for prior in ("LoD2", "ALS"):
            lab, ex = labels_of(OUT / "v3/box_gt", site, prior)
            Ucur = np.load(S0 / "s61/box" / site / prior / "units.npz")
            c, base = counts(Ucur, lab, ex, box)
            res[f"current/{site}/{prior}"] = c
            Uref_conf = None
            for v in VARIANTS:
                f = OUT / "sens" / v / "box" / site / prior / "units.npz"
                if not f.exists():
                    continue
                U = np.load(f)
                if v.startswith("patch_"):
                    lv, ev = labels_of(OUT / "sens" / v / "box_gt", site, prior)
                    cv, bv = counts(U, lv, ev, box)
                else:
                    cv, bv = counts(U, lab, ex, box)
                    ref = Ucur
                    if v in ("conf_strict", "conf_loose"):
                        fr = OUT / "sens/conf_current/box" / site / prior / "units.npz"
                        ref = np.load(fr) if fr.exists() else Ucur
                    diff = base & (U["J_loc"] != ref["J_loc"])
                    changes.setdefault(v, {})[f"{site}/{prior}"] = dict(changed=int(diff.sum()), judged=int(base.sum()),
                                                                       reference="conf_current" if v in ("conf_strict", "conf_loose") else "current")
                    if v == "conf_current":
                        changes.setdefault("conf_current_vs_colmap", {})[f"{site}/{prior}"] = dict(changed=int(diff.sum()), judged=int(base.sum()))
                res[f"{v}/{site}/{prior}"] = cv
    agg = {v: dict(changed=sum(x["changed"] for x in d.values()), judged=sum(x["judged"] for x in d.values())) for v, d in changes.items()}
    prop_rank = sorted([(v, agg[v]["changed"]) for v in PROP if v in agg], key=lambda x: -x[1])
    jdump(OUT / "sens/counts.json", dict(rule=__doc__, counts=res, changes=changes, changes_pooled=agg, propagation_most_changed=prop_rank[0][0] if prop_rank else None,
                                         propagation_rank=prop_rank, scientific_verdict=None))
    # markdown: pooled over the sites, per prior, totals as area
    keys = ["correct_keep", "wrong_keep", "correct_release", "wrong_release", "undetermined"]
    for prior in ("LoD2", "ALS"):
        md.append(f"\n**{prior}** (네 지역 합, 넓이 m²; 괄호는 패치 수)\n")
        md.append("| 값 | 맞게 지킴 | 잘못 지킴 | 맞게 놓음 | 잘못 놓음 | 미판정 | 판정이 바뀐 패치 |")
        md.append("|---|---|---|---|---|---|---|")
        for v in ["current"] + VARIANTS:
            ent = [res.get(f"{v}/{s}/{prior}") for s in SITES]
            if not all(ent):
                continue
            cells = []
            for k in keys:
                a = sum(e["total"][k]["area_m2"] for e in ent)
                n = sum(e["total"][k]["patches"] for e in ent)
                cells.append(f"{a:,.0f} ({n:,})")
            ch = "—" if v in ("current",) or v.startswith("patch_") else f"{sum(changes[v][f'{s}/{prior}']['changed'] for s in SITES):,}"
            md.append(f"| {v} | " + " | ".join(cells) + f" | {ch} |")
    for prior in ("LoD2", "ALS"):
        md.append(f"\n**{prior}, 몫** (네 지역 합 넓이에서 각 갈래의 몫 %; 패치 크기마다 라벨이 붙는 넓이가 달라 몫으로 견줌)\n")
        md.append("| 값 | 라벨 넓이 m² | 맞게 지킴 | 잘못 지킴 | 맞게 놓음 | 잘못 놓음 | 미판정 |")
        md.append("|---|---|---|---|---|---|---|")
        for v in ["current"] + VARIANTS:
            ent = [res.get(f"{v}/{s}/{prior}") for s in SITES]
            if not all(ent):
                continue
            ar = {k: sum(e["total"][k]["area_m2"] for e in ent) for k in keys}
            tot = sum(ar.values())
            md.append(f"| {v} | {tot:,.0f} | " + " | ".join(f"{100 * ar[k] / max(tot, 1e-9):.1f}" for k in keys) + " |")
    (OUT / "sens/counts.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print("propagation rank", prop_rank)


if __name__ == "__main__":
    main()

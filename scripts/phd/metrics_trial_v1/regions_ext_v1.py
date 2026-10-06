"""PHD-MAIN-METRICS-TRIAL-v1 4.2: the widened evaluation regions of the four sites x two priors, fixed for stage 1 from
pre-training data only (jointbuildgs:dev, CPU; definitions = configs metrics_trial_v1.json 'regions_ext' and 'unseen_split').

  python regions_ext_v1.py

Input per site x prior: the stage-0 region file (/s0/regions/regions_<site>_<prior>.npz: code, label, state, MVS - prior,
tau, ...; left unchanged), the v6 labels and GT ownership (/s0/s61/box_gt/<site>), the LoD2 store of the v6 box run.
code_ext per patch: the stage-0 codes with code 3 renamed 'image wrong' and the true conflicts (stage-0 code 1) split into
  11 prior wrong (support, |MVS - GT| <= tau)     12 both wrong (support, |MVS - GT| > tau or no MVS value)
  13 unmeasured wrong prior, missing              14 unmeasured wrong prior, invisible
gt_points per patch = the rows of the GT ownership (B0 sites: the owner file of the patch's label source, gt_clean or ULS).
Unseen split (B173 sites, LoD2 file): B173 wall patches invisible in the v6 LoD2 run, inside the evaluation range, split by
the current top behind the wall (highest GT point 0.3-2.0 m behind the patch centre, within 0.5 m along the wall, >= 5
points): above top + tau_wall = 1 (gone old upper wall), below top - tau_wall = 0 (wall expected to stand), else 2
(ambiguous), no top = -1; -2 = not an unseen patch.
Writes /out/regions_ext/regions_ext_<site>_<prior>.npz, summary.json, summary.csv, tables_regions_ext.md, and
/out/figs/regions_ext_<site>.png. scientific_verdict: null."""
import csv
import json

import numpy as np
from matplotlib.patches import Patch
from scipy.spatial import cKDTree

from mt_common import COL, DR, KO, MCFG, NAMES, ORDER, OUT, S0, B173, Timer, boxes, jdump, log, setup_fonts, xy_to_uv
from src.phd.prior_propagation_v6 import rule

plt = setup_fonts()
SITES = {"B0_b10": "B0", "B173nb_b10": "B173nb", "B173_b0": "B173", "R1rep_b10": "R1rep"}
UNSEEN_SITES = MCFG["unseen_split"]["sites"]


def code_ext(R):
    c = R["code"].astype(np.int8).copy()
    conflict = R["code"] == 1
    st = R["state"]
    mvs = R["mvs_minus_prior"].astype(np.float64)
    off = ~(np.abs(mvs - R["gt_med"].astype(np.float64)) <= R["tau"].astype(np.float64))     # nan (no MVS value) -> off
    c[conflict] = -9
    c[conflict & (st == rule.ST_SUPPORT) & ~off] = 11
    c[conflict & (st == rule.ST_SUPPORT) & off] = 12
    c[conflict & (st == rule.ST_MISSING)] = 13
    c[conflict & (st == rule.ST_INVISIBLE)] = 14
    assert not (c == -9).any(), "a true conflict without a state"
    return c


def gt_rows(site, prior, n):
    D = S0 / "s61/box_gt" / site
    o = np.load(D / f"gt_owner_{prior}.npz")
    cnt = np.bincount(o["patch"], minlength=n).astype(np.int64)
    if site.startswith("B0") and (D / f"labels_uls_{prior}.npz").exists():
        G = np.load(D / f"labels_{prior}.npz")
        Gu = np.load(D / f"labels_uls_{prior}.npz")
        use = (G["label"] < 0) & (Gu["label"] >= 0)          # the stage-0 rule: ULS label where gt_clean has none
        ou = np.load(D / f"gt_owner_uls_{prior}.npz")
        cu = np.bincount(ou["patch"], minlength=n).astype(np.int64)
        cnt = np.where(use, cu, cnt)
    return cnt


def unseen_split(site, R):
    """inferred split of the B173 unseen wall patches (LoD2 file); -2 elsewhere."""
    U = np.load(S0 / "s61/box" / site / "LoD2" / "units.npz")
    tab = {r["ext"]: r for r in json.loads((DR / "s02_box" / site / "lod2_surfaces.json").read_text())["surfaces"]}
    se = U["surf_ext"][U["loc_surface"]]
    bld = np.array([tab[int(e)]["building"] == B173 for e in se])
    un = bld & (U["loc_kind"] == 2) & (U["state"] == rule.ST_INVISIBLE) & R["in_eval"]
    lab = np.full(len(se), -2, np.int8)
    top = np.full(len(se), np.nan, np.float32)
    idx = np.nonzero(un)[0]
    if not len(idx):
        return lab, top, un
    c = U["loc_center"][idx]
    n = np.array([tab[int(e)]["normal"] for e in se[idx]], np.float64)
    nh = n[:, :2] / np.linalg.norm(n[:, :2], axis=1, keepdims=True)
    g = np.load(S0 / "s61/box_gt" / site / "gt_points.npz")["xyz"].astype(np.float64)
    us = MCFG["unseen_split"]
    tree = cKDTree(g[:, :2])
    L = tree.query_ball_point(c[:, :2] - nh * 1.15, 1.25)      # a disk holding the strip 0.3-2.0 m behind, +-0.5 m along
    tau_w = float(np.median(R["tau"][un]))
    for k, l in enumerate(L):
        if not l:
            continue
        P = g[l]
        v = P[:, :2] - c[k, :2]
        dep = -(v @ nh[k])
        al = np.abs(v @ np.array([-nh[k, 1], nh[k, 0]]))
        m = (dep >= 0.3) & (dep <= 2.0) & (al <= 0.5)
        if m.sum() >= 5:
            top[idx[k]] = P[m, 2].max()
    d = c[:, 2] - top[idx].astype(np.float64)
    li = np.full(len(idx), -1, np.int8)
    li[d > tau_w] = 1
    li[d < -tau_w] = 0
    li[np.abs(d) <= tau_w] = 2
    lab[idx] = li
    return lab, top, un


def main():
    T = Timer()
    O = OUT / "regions_ext"
    O.mkdir(parents=True, exist_ok=True)
    (OUT / "figs").mkdir(exist_ok=True)
    bx = boxes()
    summ, rows, md = {}, [], []
    for site, bid in SITES.items():
        b = bx[bid]
        fig, axs = plt.subplots(1, 3, figsize=(19, 6.6), constrained_layout=True)
        for prior in ("LoD2", "ALS"):
            R = np.load(S0 / "regions" / f"regions_{site}_{prior}.npz")
            ce = code_ext(R)
            n = len(ce)
            gpts = gt_rows(site, prior, n)
            arrays = {k: R[k] for k in R.files}
            arrays.update(code_ext=ce, code_ext_values=np.array(sorted(NAMES)), code_ext_names=np.array([NAMES[k] for k in sorted(NAMES)]),
                          gt_points=gpts.astype(np.int32))
            ent = dict(patches_eval=int(R["in_eval"].sum()), by_kind={})
            if prior == "LoD2" and site in UNSEEN_SITES:
                ul, top, un = unseen_split(site, R)
                arrays.update(unseen_label_inferred=ul, unseen_top_behind=top)
                ent["unseen_b173"] = dict(patches=int(un.sum()), area_m2=round(float(R["area"][un].sum()), 1),
                                          above_current_roof=int((ul == 1).sum()), below_current_roof=int((ul == 0).sum()),
                                          ambiguous=int((ul == 2).sum()), no_top=int((ul == -1).sum()),
                                          true_label={str(k): int(v) for k, v in zip(*np.unique(R["label"][un], return_counts=True))},
                                          gt_points=int(gpts[un].sum()), patches_with_gt_point=int((gpts[un] > 0).sum()))
                log(site, "unseen", ent["unseen_b173"])
            np.savez_compressed(O / f"regions_ext_{site}_{prior}.npz", **arrays)
            kind, area, tau = R["kind"], R["area"], R["tau"]
            for kn, kv in (("roof", 1), ("wall", 2)):
                km = kind == kv
                if not (km & R["in_eval"]).any():
                    continue
                t = float(np.median(tau[km])) if km.any() else None
                d = {}
                for c in ORDER:
                    m = km & (ce == c)
                    d[NAMES[c]] = dict(patches=int(m.sum()), area_m2=round(float(area[m].sum()), 1), gt_points=int(gpts[m].sum()))
                    rows.append(dict(site=site, prior=prior, kind=kn, code=c, region=NAMES[c], patches=int(m.sum()),
                                     area_m2=round(float(area[m].sum()), 1), gt_points=int(gpts[m].sum()), tau_m=round(t, 4)))
                ent["by_kind"][kn] = dict(tau_m=round(t, 4), regions=d)
            summ[f"{site}/{prior}"] = ent
            log(site, prior, {NAMES[c]: int(((ce == c) & R["in_eval"]).sum()) for c in ORDER})
            # map panels: LoD2 roofs, LoD2 walls (seen from above), ALS
            uv = xy_to_uv(R["centre"][:, :2])
            panels = [(0, 1), (1, 2)] if prior == "LoD2" else [(2, 1)]
            for ax_i, kv in panels:
                ax = axs[ax_i]
                m = R["in_eval"] & (kind == kv)
                for c in [0, 2, 4, 5, 3, 12, 13, 14, 11]:
                    mm = m & (ce == c)
                    ax.scatter(uv[mm, 0], uv[mm, 1], s=0.6 if kv == 1 else 1.6, c=COL[c], marker="s", linewidths=0, rasterized=True)
                ax.plot([b["eval_u"][0], b["eval_u"][1], b["eval_u"][1], b["eval_u"][0], b["eval_u"][0]],
                        [b["eval_v"][0], b["eval_v"][0], b["eval_v"][1], b["eval_v"][1], b["eval_v"][0]], "k-", lw=0.8)
                ax.set_aspect("equal")
                ax.set_xlabel("u (m)")
                ax.set_ylabel("v (m)")
                title = {(0, 1): "LoD2 지붕", (1, 2): "LoD2 벽 (위에서 본 자리)", (2, 1): "항공 LiDAR"}[(ax_i, kv)]
                tv = float(np.median(tau[kind == kv]))
                ax.set_title(f"{title} — τ {tv:.2f} m", fontsize=11)
        fig.legend(handles=[Patch(color=COL[c], label=KO[c]) for c in ORDER], loc="lower center", ncol=5, fontsize=10, bbox_to_anchor=(0.5, -0.1))
        fig.suptitle(f"{site} 넓힌 평가 영역 (학습 전 자료로 고정: v6 첫째 단계 + v6 참 라벨, 평가 범위 안 패치)", fontsize=12, x=0.01, ha="left")
        fig.savefig(OUT / "figs" / f"regions_ext_{site}.png", dpi=110, bbox_inches="tight")
        plt.close(fig)
    jdump(O / "summary.json", dict(rule=MCFG["regions_ext"], unseen_rule=MCFG["unseen_split"], codes=NAMES, sites=summ,
                                   seconds=T.mark("all"), scientific_verdict=None))
    with open(O / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    # markdown table: per site x prior, roof / wall: patches, area, GT points per region
    md.append("| 지역 · 사전 정보 · 면 | τ (m) | " + " | ".join(KO[c] for c in ORDER) + " |")
    md.append("|---|---:|" + "---|" * len(ORDER))
    for key, ent in summ.items():
        site, prior = key.split("/")
        for kn, d in ent["by_kind"].items():
            cells = [f"{d['regions'][NAMES[c]]['patches']:,} · {d['regions'][NAMES[c]]['area_m2']:,.0f} m² · {d['regions'][NAMES[c]]['gt_points']:,}" for c in ORDER]
            md.append(f"| {site} · {prior} · {'지붕' if kn == 'roof' else '벽'} | {d['tau_m']:.3f} | " + " | ".join(cells) + " |")
    (O / "tables_regions_ext.md").write_text("\n".join(md) + "\n\n(칸 = 패치 수 · 넓이 · 참값 점 수(소유 행). 평가 범위 밖 패치는 세지 않았다.)\n")
    print("regions_ext done", len(summ), T.mark("all"))


if __name__ == "__main__":
    main()

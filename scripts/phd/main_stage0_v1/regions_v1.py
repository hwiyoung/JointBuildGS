"""PHD-MAIN-STAGE0-v1 5.3: agreement-region maps of the four sites x two priors, fixed before any training result
(jointbuildgs:dev, CPU; definitions = configs/phd/main_stage0_v1/stage0_v1.json 'agreement_regions', written before any result).

  python regions_v1.py [--stage1 s61/box] [--gt s61/box_gt] [--out regions]

Data: the v6 box stage-1 runs (box MVS of the training images, fixed tolerance / registration, moved store) and their v6
labels (B0: gt_clean, ULS where gt_clean has no label). Patches of the box evaluation range (moved centres, in range).
Region code per patch:
  -1 outside the evaluation range        0 no GT (label < 0 or excluded cell): shown, never compared
   1 true conflict (|GT - prior| > tau)   2 agreement, measured: support and |MVS - GT| <= tau
   3 agreement, measured but the image off by more than tau (support, |MVS - GT| > tau): shown, in neither comparison
   4 agreement, unmeasured (missing)      5 agreement, unmeasured (invisible)
with GT - prior = the label's median and MVS - prior = -mvs_r_med (vertical on roof-like, along the outward normal on
wall-like patches), tau = the label's tau (base value of the patch kind). 'all' = 2 + 3 + 4 + 5.
Writes <out>/regions_<site>_<prior>.npz, <out>/regions_summary.json, <out>/regions_summary.csv, figs/regions_<site>.png.
scientific_verdict: null."""
import argparse
import csv
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
import numpy as np

from common import OUT, PREP, SCFG, jdump, log, uv_to_xy, xy_to_uv
from src.phd.prior_propagation_v6 import rule

for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
    try:
        font_manager.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
SITES = {"B0_b10": "B0", "B173nb_b10": "B173nb", "B173_b0": "B173", "R1rep_b10": "R1rep"}
NAMES = {-1: "outside", 0: "no GT", 1: "true conflict", 2: "agreement measured", 3: "agreement measured, image off",
         4: "agreement unmeasured (missing)", 5: "agreement unmeasured (invisible)"}
KO = {0: "참값 없음", 1: "참 충돌", 2: "잰 일치", 3: "잰 곳·영상 오차 큼", 4: "못 잰 일치(결측)", 5: "못 잰 일치(비가시)"}
COL = {0: "#c8c8c8", 1: "#d62728", 2: "#2ca02c", 3: "#bcbd22", 4: "#1f77b4", 5: "#9467bd"}


def labels_of(gt_dir, prior, rid):
    G = np.load(gt_dir / f"labels_{prior}.npz")
    lab, med, tau, ex = G["label"].astype(np.int8), G["gt_med"].astype(np.float64), G["tau"].astype(np.float64), G["excluded"]
    n = G["gt_n"].astype(np.int64)
    if rid.startswith("B0") and (gt_dir / f"labels_uls_{prior}.npz").exists():
        Gu = np.load(gt_dir / f"labels_uls_{prior}.npz")
        use = (lab < 0) & (Gu["label"] >= 0)
        lab = np.where(use, Gu["label"], lab).astype(np.int8); med = np.where(use, Gu["gt_med"], med); ex = ex | (use & Gu["excluded"])
        n = np.where(use, Gu["gt_n"], n)
    return lab, med, tau, ex, n


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--stage1", default="s61/box"); ap.add_argument("--gt", default="s61/box_gt")
    ap.add_argument("--out", default="regions")
    a = ap.parse_args()
    O = OUT / a.out; O.mkdir(parents=True, exist_ok=True); (OUT / "figs").mkdir(exist_ok=True)
    boxes = json.loads((PREP / "step06/boxes_v1.json").read_text())["boxes"]
    summ, rows = {}, []
    for site, bid in SITES.items():
        b = boxes[bid]
        fig, axs = plt.subplots(1, 3, figsize=(19, 6.6), constrained_layout=True)
        for pi, prior in enumerate(("LoD2", "ALS")):
            run = OUT / a.stage1 / site / prior
            U = np.load(run / "units.npz")
            lab, med, tau, ex, gtn = labels_of(OUT / a.gt / site, prior, site)
            uv = xy_to_uv(U["loc_center"][:, :2])
            inev = (uv[:, 0] >= b["eval_u"][0]) & (uv[:, 0] <= b["eval_u"][1]) & (uv[:, 1] >= b["eval_v"][0]) & (uv[:, 1] <= b["eval_v"][1]) & U["loc_in_range"]
            st = U["state"]; mvs = -U["mvs_r_med"].astype(np.float64)
            code = np.full(len(st), -1, np.int8)
            code[inev] = 0
            g = inev & ~ex & (lab >= 0)
            code[g & (lab == 1)] = 1
            agree = g & (lab == 0)
            off = np.abs(mvs - med) > tau
            code[agree & (st == rule.ST_SUPPORT) & ~off] = 2
            code[agree & (st == rule.ST_SUPPORT) & (off | ~np.isfinite(mvs))] = 3
            code[agree & (st == rule.ST_MISSING)] = 4
            code[agree & (st == rule.ST_INVISIBLE)] = 5
            area = U["loc_area"]; kind = U["loc_kind"]
            np.savez_compressed(O / f"regions_{site}_{prior}.npz", code=code, code_names=np.array([NAMES[i] for i in range(-1, 6)]),
                                centre=U["loc_center"].astype(np.float64), kind=kind, area=area, label=lab, gt_med=med.astype(np.float32),
                                gt_n=gtn.astype(np.int32), mvs_minus_prior=mvs.astype(np.float32), tau=tau.astype(np.float32), state=st,
                                frame_shift=U["frame_shift"], surf_ext=U["surf_ext"][U["loc_surface"]], in_eval=inev)
            ent = dict(patches_eval=int(inev.sum()), area_eval_m2=round(float(area[inev].sum()), 1),
                       gt_coverage_patches=round(float(g.sum()) / max(int(inev.sum()), 1), 4),
                       gt_coverage_area=round(float(area[g].sum()) / max(float(area[inev].sum()), 1e-9), 4),
                       tau_roof=float(np.median(tau[(kind == 1)])) if (kind == 1).any() else None,
                       tau_wall=float(np.median(tau[(kind == 2)])) if (kind == 2).any() else None, by_kind={})
            for kn, kv in (("roof", 1), ("wall", 2), ("all", 0)):
                km = (kind == kv) if kv else np.ones(len(kind), bool)
                if prior == "ALS" and kv == 2:
                    continue
                d = {}
                for c in range(0, 6):
                    m = km & (code == c)
                    d[NAMES[c]] = dict(patches=int(m.sum()), area_m2=round(float(area[m].sum()), 1))
                allm = km & np.isin(code, (2, 3, 4, 5))
                d["agreement all"] = dict(patches=int(allm.sum()), area_m2=round(float(area[allm].sum()), 1))
                ent["by_kind"][kn] = d
                for nm, v in d.items():
                    rows.append(dict(site=site, prior=prior, kind=kn, region=nm, **v))
            summ[f"{site}/{prior}"] = ent
            log(site, prior, {k: v["patches"] for k, v in ent["by_kind"]["all"].items()})
            # map panels: LoD2 roofs, LoD2 walls, ALS
            panels = [(0, 1), (1, 2)] if prior == "LoD2" else [(2, 1)]
            for ax_i, kv in panels:
                ax = axs[ax_i]
                m = inev & (kind == kv)
                for c in range(0, 6):
                    mm = m & (code == c)
                    ax.scatter(uv[mm, 0], uv[mm, 1], s=0.6 if kv == 1 else 1.6, c=COL[c], marker="s", linewidths=0, rasterized=True)
                ax.plot([b["eval_u"][0], b["eval_u"][1], b["eval_u"][1], b["eval_u"][0], b["eval_u"][0]],
                        [b["eval_v"][0], b["eval_v"][0], b["eval_v"][1], b["eval_v"][1], b["eval_v"][0]], "k-", lw=0.8)
                ax.set_aspect("equal"); ax.set_xlabel("u (m)"); ax.set_ylabel("v (m)")
                t = {(0, 1): "LoD2 지붕", (1, 2): "LoD2 벽 (위에서 본 자리)", (2, 1): "항공 LiDAR"}[(ax_i, kv)]
                cov = float(area[g & (kind == kv)].sum()) / max(float(area[inev & (kind == kv)].sum()), 1e-9)
                ent.setdefault("gt_coverage_area_by_kind", {})["roof" if kv == 1 else "wall"] = round(cov, 4)
                ax.set_title(f"{t} — 참값 피복 {cov:.0%}(넓이)", fontsize=11)
        fig.legend(handles=[Patch(color=COL[c], label=KO[c]) for c in range(0, 6)], loc="lower center", ncol=6, fontsize=10, bbox_to_anchor=(0.5, -0.06))
        fig.suptitle(f"{site} 일치 영역 (학습 전 자료로 고정: v6 첫째 단계 + v6 참 라벨, 평가 범위 안 패치)", fontsize=12, x=0.01, ha="left")
        fig.savefig(OUT / "figs" / f"regions_{site}.png", dpi=110, bbox_inches="tight"); plt.close(fig)
    jdump(O / "regions_summary.json", dict(rule=SCFG["agreement_regions"], codes=NAMES, sites=summ, scientific_verdict=None))
    with open(O / "regions_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print("regions done", len(summ))


if __name__ == "__main__":
    main()

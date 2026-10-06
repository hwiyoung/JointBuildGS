"""PHD-MAIN-STAGE0-v1 5.2: table and figure of the seven B0 conditions with module v6 (jointbuildgs:dev, CPU) = the discard
task's figs_main.b0 (same counting area and counts) on this task's runs, plus the share of confidence-1 pixels among the prior
pixels of the target building (stage-1 coverage_footprints: px / a1 by face kind).

  python b0_table_v2.py

Counting area = target building footprint (prep step01 B0BLD) + 2 m (prep case 6), patches in range, not excluded; the
discard decision follows the run's rule (LoD2 current, ALS margin_all_2); wrong discard = discarded true agree, wrong keep =
kept true conflict (invisible apart), inherit = invisible + missing judged mixed / insufficient.
Writes tables/b0_conditions_v2.csv / .json and figs/b0_conditions_v2.png. scientific_verdict: null."""
import csv
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.path import Path as MPath
import numpy as np
from shapely.geometry import Polygon as SPoly

from common import OUT, PREP, jdump, log
from src.phd.prior_propagation_v6 import rule

for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
    try:
        font_manager.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
TARGET = "DEBY_LOD2_4959323"
CONDS = ("COVER", "A15", "A9", "A3", "N13", "N8", "N2")


def main():
    F = OUT / "figs"; T = OUT / "tables"; F.mkdir(exist_ok=True); T.mkdir(exist_ok=True)
    fpoly = SPoly(json.loads((PREP / "step01/ranges.json").read_text())["B0BLD"]["polygon_local"]).buffer(2.0)
    rows = []
    conds = [c for c in CONDS if (OUT / "s62_gt" / c / "B0" / "labels_LoD2.npz").exists()]
    for c in conds:
        for p in ("LoD2", "ALS"):
            run = OUT / "s62" / c / "B0" / p
            U = np.load(run / "units.npz"); G = np.load(OUT / "s62_gt" / c / "B0" / f"labels_{p}.npz")
            summ = json.loads((run / "summary.json").read_text())
            cfp = [r for r in json.loads((run / "coverage_footprints.json").read_text()) if r["building"] == TARGET]
            in_t = MPath(np.asarray(fpoly.exterior.coords)).contains_points(U["loc_center"][:, :2])
            lab = G["label"]; ex = G["excluded"]; st, vote, J = U["state"], U["vote"], U["J"]
            m = U["loc_in_range"] & in_t & ~ex
            for kname, kv in (("roof", 1), ("wall", 2)):
                if p == "ALS" and kv == 2:
                    continue
                mk = m & (U["loc_kind"] == kv)
                n = int(mk.sum())
                sup = mk & (st == rule.ST_SUPPORT); mis = mk & (st == rule.ST_MISSING); inv = mk & (st == rule.ST_INVISIBLE)
                und = mis & ((J == rule.J_MIXED) | (J == rule.J_INSUFF))
                disc = (sup & (vote == rule.V_CONFLICT)) | (mis & (J == rule.J_CONFLICT))
                g = lab >= 0
                px = sum(r[f"{kname}_px"] for r in cfp); a1 = sum(r[f"{kname}_a1"] for r in cfp)
                rows.append(dict(condition=c, prior=p, kind=kname, rule=summ["rule"], views=summ["views"],
                                 views_without_depth_map=len(summ["views_without_depth_map"]), patches=n, labelled=int((mk & g).sum()),
                                 conf1_share=round(a1 / max(px, 1), 4), prior_pixels=int(px),
                                 support=round(sup.sum() / max(n, 1), 4), missing=round(mis.sum() / max(n, 1), 4), invisible=round(inv.sum() / max(n, 1), 4),
                                 inherit_share=round((inv.sum() + und.sum()) / max(n, 1), 4),
                                 support_conflict=round((sup & (vote == rule.V_CONFLICT)).sum() / max(sup.sum(), 1), 4),
                                 discard=int(disc.sum()), wrong_discard=int((disc & g & (lab == 0)).sum()), correct_discard=int((disc & g & (lab == 1)).sum()),
                                 wrong_keep=int((mk & ~disc & g & (lab == 1) & ~inv).sum()), correct_keep=int((mk & ~disc & g & (lab == 0) & ~inv).sum()),
                                 inherit_true_agree=int(((inv | und) & g & (lab == 0)).sum()), inherit_true_conflict=int(((inv | und) & g & (lab == 1)).sum()),
                                 tau_roof=summ["tolerance"]["roof"]["tau"], tau_wall=summ["tolerance"]["wall"]["tau"],
                                 shift=summ["registration"]["shift_applied"]))
    with open(T / "b0_conditions_v2.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    jdump(T / "b0_conditions_v2.json", rows)
    fig, axs = plt.subplots(1, 3, figsize=(17, 5.0), constrained_layout=True)
    for ax, (p, k) in zip(axs, (("LoD2", "roof"), ("LoD2", "wall"), ("ALS", "roof"))):
        sel = {r_["condition"]: r_ for r_ in rows if r_["prior"] == p and r_["kind"] == k}
        xs = np.arange(len(conds))
        ax.bar(xs, [sel[c]["support"] for c in conds], color="#9ad19a", label="지지")
        ax.bar(xs, [sel[c]["missing"] for c in conds], bottom=[sel[c]["support"] for c in conds], color="#f0b429", label="결측")
        ax.bar(xs, [sel[c]["invisible"] for c in conds], bottom=[sel[c]["support"] + sel[c]["missing"] for c in conds], color="#4a6fd1", label="비가시")
        ax.plot(xs, [sel[c]["conf1_share"] for c in conds], "ks--", label="신뢰도 1 픽셀 비율")
        ax.plot(xs, [sel[c]["inherit_share"] for c in conds], "o-", color="#7f3fbf", label="이어받는 몫")
        ax.axvline(3.5, color="k", lw=0.6, ls=":")
        ax.set_xticks(xs); ax.set_xticklabels([f"{c}\n{sel[c]['views']}장" for c in conds], fontsize=8)
        ax.set_ylim(0, 1); ax.set_title(f"{p} {'지붕' if k == 'roof' else '벽'}", fontsize=11); ax.grid(alpha=0.3, axis="y")
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, fontsize=9, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.07))
    fig.suptitle("B0 관측의 양 (대상 건물 + 2 m): 패치 상태, 신뢰도 1 픽셀 비율, 이어받는 몫. A = 저자 경사 영상, N = 연직을 넣은 같은 수(설정 v2: 겹치는 영상만 더함). 모듈 v6, B0 크롭 값 고정",
                 fontsize=10.5, x=0.01, ha="left")
    fig.savefig(F / "b0_conditions_v2.png", dpi=100, bbox_inches="tight"); plt.close(fig)
    log("b0 v2", len(rows))


if __name__ == "__main__":
    main()

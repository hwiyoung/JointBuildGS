"""PHD-CH6-SUPPORT-v1 task 5 figures (jointbuildgs:dev, CPU): from /out/t5/judge (t5_judge.py).

  python t5_figs.py

fig_t5_bars.png   per prior: items (rows) x {selection, evaluation}: shares of correct keep / wrong keep / correct release /
                  wrong release by area, the item area written at the end
fig_t5_maps_<prior>.png  the seven ranges (selection area, deduplicated) and the four boxes: wrong decisions in colour, correct
                  ones in light grey, footprints outlined; u-v frame with v down (a proper rotation of the map)
fig_t5_conc.png   cumulative share of the wrong releases / wrong keeps over the buildings ranked by that area (selection area)
scientific_verdict: null."""
import csv
import json

import numpy as np

from ch6_common import BOXES, DR, ITEMS, OUT, PRIOR_KO, PRIORS, RANGES, RNGDEF, SITE_KO, setup_fonts, xy_to_uv

J = OUT / "t5/judge"; F = J / "figs"; F.mkdir(parents=True, exist_ok=True)
CATS = ("correct_keep", "wrong_keep", "correct_release", "wrong_release")
CKO = {"correct_keep": "맞게 지킴", "wrong_keep": "잘못 지킴", "correct_release": "맞게 놓음", "wrong_release": "잘못 놓음"}
CCOL = {"correct_keep": "#c8c8c8", "wrong_keep": "#e67e22", "correct_release": "#2e86c1", "wrong_release": "#c0392b"}
IKO = dict(ITEMS)


def item_tot(t, item):
    d = {c: 0.0 for c in CATS}
    for key, v in t.items():
        if key.split("|")[0] == item:
            for c in CATS:
                d[c] += v[c][0]
    return d


def main():
    plt = setup_fonts()
    R = json.loads((J / "counts.json").read_text())
    # ---- bars
    fig, axs = plt.subplots(1, 2, figsize=(15, 7.6), constrained_layout=True)
    for ax, prior in zip(axs, PRIORS):
        ev = {}
        for box in ("B0_b10", "B173nb_b10", "R1rep_b10"):
            for key, v in R["evaluation"][f"{box}/{prior}"].items():
                t = ev.setdefault(key, {c: [0.0, 0] for c in CATS + ("undetermined",)})
                for c in t:
                    t[c][0] += v[c][0]; t[c][1] += v[c][1]
        rows = []
        for it, ko in ITEMS:
            for nm, src in (("고르는 곳", R["selection"][prior]), ("평가 지역", ev)):
                d = item_tot(src, it); tot = sum(d.values())
                if tot >= 1.0:                     # rows under 1 m2 left out of the chart (kept in the tables)
                    rows.append((f"{ko} · {nm}", d, tot))
        for i, (lab, d, tot) in enumerate(rows):
            left = 0.0
            for c in CATS:
                w = 100 * d[c] / tot
                ax.barh(i, w, left=left, color=CCOL[c], height=0.7, edgecolor="white", lw=0.5)
                if c in ("wrong_keep", "wrong_release") and w >= 4:
                    ax.text(left + w / 2, i, f"{w:.0f}", ha="center", va="center", fontsize=7.5, color="white", fontweight="bold")
                left += w
            ax.text(101, i, f"{tot:,.0f} m²", va="center", fontsize=7.5)
        ax.set_yticks(range(len(rows))); ax.set_yticklabels([r[0] for r in rows], fontsize=7.8); ax.invert_yaxis()
        ax.set_xlim(0, 118); ax.set_xlabel("넓이의 몫 (%)")
        ax.set_title(f"{PRIOR_KO[prior]}: 검증 항목마다 학습 전 판정의 네 갈래", fontsize=11, loc="left")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=CCOL[c], label=CKO[c]) for c in CATS], loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.04))
    fig.savefig(F / "fig_t5_bars.png", dpi=150, bbox_inches="tight"); plt.close(fig)
    # ---- maps
    for prior in PRIORS:
        runs = [(r, f"{r}", True) for r in RANGES] + [(b, SITE_KO[b], False) for b in BOXES]
        n = len(runs); nc = 4; nr = int(np.ceil(n / nc))
        fig, axs = plt.subplots(nr, nc, figsize=(5.2 * nc, 4.6 * nr), constrained_layout=True)
        for ax, (rid, name, is_range) in zip(axs.ravel(), runs):
            Z = np.load(J / "patches" / f"{rid}_{prior}.npz")
            m = Z["sel"]
            uv = xy_to_uv(Z["xy"].astype(np.float64))
            rel = Z["rel"]; lab = Z["lab"]
            C = dict(correct_keep=~rel & (lab == 0), wrong_keep=~rel & (lab == 1), correct_release=rel & (lab == 1), wrong_release=rel & (lab == 0))
            for c in CATS:
                mm = m & C[c]
                ax.scatter(uv[mm, 0], uv[mm, 1], s=0.15 if c == "correct_keep" else 0.5, c=CCOL[c], marker="s", linewidths=0, rasterized=True)
            fp_json = (DR / "s02" / rid / "footprints.json") if is_range else (DR / "s02_box" / rid / "footprints.json")
            Fp = json.loads(fp_json.read_text()); Fp = Fp["footprints"] if isinstance(Fp, dict) else Fp
            for f in Fp:
                ring = xy_to_uv(np.asarray(f["ring_local"], np.float64))
                ax.plot(np.r_[ring[:, 0], ring[0, 0]], np.r_[ring[:, 1], ring[0, 1]], color="#555555", lw=0.3)
            if is_range:
                p = xy_to_uv(np.asarray(RNGDEF[rid]["polygon_local"], np.float64))
                ax.plot(np.r_[p[:, 0], p[0, 0]], np.r_[p[:, 1], p[0, 1]], "k--", lw=0.6)
                if m.any():
                    lo, hi = uv[m].min(0) - 5, uv[m].max(0) + 5
                    ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1])
            elif m.any():
                lo, hi = uv[m].min(0) - 3, uv[m].max(0) + 3
                ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1])
            ax.invert_yaxis(); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
            a = Z["area"].astype(np.float64)
            wr = 100 * a[m & C["wrong_release"]].sum() / max(a[m & (lab == 0)].sum(), 1e-9)
            wk = 100 * a[m & C["wrong_keep"]].sum() / max(a[m & (lab == 1)].sum(), 1e-9)
            ax.set_title(f"{name} ({'고르는 곳' if is_range else '평가 지역'}): 잘못 놓음 {wr:.1f} %, 잘못 지킴 {wk:.1f} %", fontsize=9, loc="left")
        for ax in axs.ravel()[n:]:
            ax.axis("off")
        fig.legend(handles=[Patch(color=CCOL[c], label=CKO[c]) for c in CATS], loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.02))
        fig.suptitle(f"{PRIOR_KO[prior]}: 학습 전 판정이 틀린 자리 (잘못 놓음 = 맞는 사전 정보를 놓음, 잘못 지킴 = 틀린 사전 정보를 지킴; 몫은 넓이 기준)", fontsize=11)
        fig.savefig(F / f"fig_t5_maps_{prior}.png", dpi=140, bbox_inches="tight"); plt.close(fig)
    # ---- concentration
    rows = list(csv.DictReader(open(J / "buildings.csv")))
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.6), constrained_layout=True)
    for ax, c in zip(axs, ("wrong_release", "wrong_keep")):
        for prior, ls in zip(PRIORS, ("-", "--")):
            v = np.array(sorted([float(r[c]) for r in rows if r["area_kind"] == "selection" and r["prior"] == prior and r["building"] != "(발자국 밖)"], reverse=True))
            if v.sum() <= 0:
                continue
            cum = np.r_[0, np.cumsum(v)] / v.sum() * 100
            ax.plot(np.arange(len(cum)), cum, ls, label=f"{PRIOR_KO[prior]} (건물 {len(v)}, {v.sum():,.0f} m²)")
            for k in (1, 5):
                ax.annotate(f"{cum[k]:.0f} %", (k, cum[k]), textcoords="offset points", xytext=(6, -10 if prior == "LoD2" else 4), fontsize=8)
        ax.set_xlabel("건물 수 (그 넓이가 큰 차례)"); ax.set_ylabel("누적 몫 (%)"); ax.set_ylim(0, 102); ax.set_xlim(0, 60)
        ax.set_title(f"{CKO[c]}이 건물에 몰린 정도 (고르는 곳)", fontsize=11, loc="left"); ax.legend(fontsize=8, frameon=False)
        ax.grid(alpha=0.3)
    fig.savefig(F / "fig_t5_conc.png", dpi=150); plt.close(fig)
    print("t5 figs done")


if __name__ == "__main__":
    main()

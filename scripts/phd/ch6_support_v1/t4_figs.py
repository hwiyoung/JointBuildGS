"""PHD-CH6-SUPPORT-v1 task 4 figures for the report (jointbuildgs:dev, CPU), from /out/t4/buildings.csv and strict.csv.

  python t4_figs.py

fig_t4_scatter.png  every building (primary rows) of the seven ranges: (g_b - G_r) / tau with the building's spread sg_b / tau,
                    marker area ~ roof area; strict cases filled, real changes as crosses (clipped at +-3 tau)
fig_t4_maps.png     ranges B0, R3E, R4, R1 x LoD2 / airborne LiDAR: footprints coloured by (g_b - G_r) / tau, strict cases outlined
                    and numbered, real changes hatched; u-v frame with v down (a proper rotation of the map)
g_b = GT - prior median of the building's labelled roof patches, G_r = median of g_b over the range's buildings (same prior).
scientific_verdict: null."""
import csv
import json
from collections import defaultdict

import numpy as np

from ch6_common import DR, OUT, RANGES, RNGDEF, setup_fonts, xy_to_uv

O = OUT / "t4"
CHANGE_IDS = ("4959326", "4907510", "4907508", "4907207")


def f(x):
    return float(x) if x not in ("", None) else np.nan


def main():
    plt = setup_fonts()
    import matplotlib.colors as mcolors
    from matplotlib.cm import ScalarMappable
    rows = list(csv.DictReader(open(O / "buildings.csv")))
    strict = {(r["range"], r["prior"], r["building"]): r for r in csv.DictReader(open(O / "strict.csv"))}
    G = defaultdict(list)
    for r in rows:
        if np.isfinite(f(r["g_b"])):
            G[(r["range"], r["prior"])].append(f(r["g_b"]))
    Gr = {k: float(np.median(v)) for k, v in G.items()}
    # ---- scatter
    fig, axs = plt.subplots(2, 1, figsize=(13, 8.2), constrained_layout=True, sharex=False)
    for ax, prior in zip(axs, ("LoD2", "ALS")):
        x0 = 0; ticks = []
        for rid in RANGES:
            R_ = [r for r in rows if r["prior"] == prior and r["range"] == rid and r["primary"] == "True" and np.isfinite(f(r["g_b"]))]
            R_.sort(key=lambda r: f(r["g_b"]) - Gr[(rid, prior)])
            for i, r in enumerate(R_):
                tau = f(r["tau_roof"]); d = (f(r["g_b"]) - Gr[(rid, prior)]) / tau; e = f(r["sg_b"]) / tau
                x = x0 + i
                st = strict.get((rid, prior, r["building"]))
                chg = any(c in r["building"] for c in CHANGE_IDS) or abs(f(r["g_b"])) > 2.0
                dc = float(np.clip(d, -3, 3))
                if chg:
                    ax.plot([x], [dc], "kx", ms=8, mew=1.6)
                else:
                    filled = st is not None and st["strict_case"] == "True"
                    ax.errorbar([x], [dc], yerr=[[min(e, 3)], [min(e, 3)]], fmt="o", ms=3 + 7 * np.sqrt(f(r["roof_area_m2"]) / 1500),
                                color="#c0392b" if filled else "#7f8c8d", mfc="#c0392b" if filled else "white", elinewidth=0.7, capsize=0)
                    if filled and abs(d) >= 0.5:
                        ax.annotate(r["building"].replace("DEBY_LOD2_", ""), (x, dc), textcoords="offset points", xytext=(4, 4 if d > 0 else -10), fontsize=7.5)
            ticks.append((x0 + max(len(R_) - 1, 0) / 2, rid))
            x0 += len(R_) + 3
            ax.axvline(x0 - 1.5, color="#dddddd", lw=0.8)
        ax.axhline(0, color="k", lw=0.6); ax.axhline(1, color="#c0392b", lw=0.6, ls="--"); ax.axhline(-1, color="#c0392b", lw=0.6, ls="--")
        ax.set_xticks([t[0] for t in ticks]); ax.set_xticklabels([t[1] for t in ticks])
        ax.set_ylim(-3.3, 3.3); ax.set_ylabel("(참값 − 사전 정보) − 범위 공통값  [τ]")
        ax.set_title(f"{'LoD2' if prior == 'LoD2' else '항공 LiDAR'}: 건물마다 범위 공통값에서 벗어난 정도 (막대 = 건물 안 산포, 채운 점 = 엄격한 읽기의 사례, × = 실제 변화, ±3τ에서 자름)",
                     fontsize=10.5, loc="left")
    fig.savefig(O / "figs/fig_t4_scatter.png", dpi=150); plt.close(fig)
    # ---- maps
    sel = ["B0", "R3E", "R4", "R1"]
    fig, axs = plt.subplots(len(sel), 2, figsize=(12.5, 4.4 * len(sel)), constrained_layout=True)
    norm = mcolors.TwoSlopeNorm(vmin=-1.5, vcenter=0.0, vmax=1.5); cmap = plt.get_cmap("RdBu_r")
    for i, rid in enumerate(sel):
        F = json.loads((DR / "s02" / rid / "footprints.json").read_text()); F = F["footprints"] if isinstance(F, dict) else F
        pol = xy_to_uv(np.asarray(RNGDEF[rid]["polygon_local"], np.float64))
        for j, prior in enumerate(("LoD2", "ALS")):
            ax = axs[i, j]
            byb = {r["building"]: r for r in rows if r["range"] == rid and r["prior"] == prior}
            for fp in F:
                ring = xy_to_uv(np.asarray(fp["ring_local"], np.float64))
                r = byb.get(fp["building"])
                if r is None or not np.isfinite(f(r["g_b"])):
                    ax.fill(ring[:, 0], ring[:, 1], color="#eeeeee", lw=0); ax.plot(ring[:, 0], ring[:, 1], color="#bbbbbb", lw=0.3)
                    continue
                tau = f(r["tau_roof"]); d = (f(r["g_b"]) - Gr[(rid, prior)]) / tau
                chg = any(c in fp["building"] for c in CHANGE_IDS) or abs(f(r["g_b"])) > 2.0
                ax.fill(ring[:, 0], ring[:, 1], color=cmap(norm(np.clip(d, -1.5, 1.5))), lw=0, hatch="xx" if chg else None)
                st = strict.get((rid, prior, fp["building"]))
                strong = st is not None and st["strict_case"] == "True" and abs(d) >= 0.5
                ax.plot(ring[:, 0], ring[:, 1], color="k", lw=2.0 if strong else 0.4)
                if strong or chg:
                    c = ring.mean(0)
                    lo_, hi_ = pol.min(0) - 6, pol.max(0) + 6          # keep the tag inside the panel
                    c = np.clip(c, lo_, hi_)
                    ax.text(c[0], c[1], f"{fp['building'].replace('DEBY_LOD2_', '')}\n{d:+.2f}τ" + ("\n변화" if chg else ""), ha="center", va="center", fontsize=7,
                            bbox=dict(fc="white", ec="none", alpha=0.8, pad=1))
            ax.plot(np.r_[pol[:, 0], pol[0, 0]], np.r_[pol[:, 1], pol[0, 1]], "k--", lw=0.8)
            lo, hi = pol.min(0) - 8, pol.max(0) + 8
            ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.invert_yaxis(); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
            ax.set_title(f"{rid} · {'LoD2' if prior == 'LoD2' else '항공 LiDAR'}: 범위 공통값 {Gr.get((rid, prior), np.nan) * 100:+.1f} cm, τ = {f(next(iter(byb.values()))['tau_roof']) * 100:.0f} cm",
                         fontsize=9.5, loc="left")
    fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=axs, shrink=0.3, location="bottom", label="건물의 (참값 − 사전 정보) − 범위 공통값 [τ], ±1.5τ에서 자름 (빨강 = 사전 정보가 낮음)")
    fig.savefig(O / "figs/fig_t4_maps.png", dpi=130, bbox_inches="tight"); plt.close(fig)
    print("t4 figs done")


if __name__ == "__main__":
    main()

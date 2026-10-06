"""PHD-MAIN-METRICS-FIX-v1 figures (jointbuildgs:dev, CPU). Names of 2026-10-06; every figure has a 1-2 sentence reading in
the report.

  python figs_mf.py [name ...]

band_v2          support-agreement roof points of B173nb_b10 coloured by the seed-0 training's reading (gentle: height difference,
                 steep and band: normal distance; +-0.2 m), removed (band) points grey; trial band (v1) next to the new band (v2)
(more figures are added by the later steps: overlays, sections, height proportionality, virtual views)
scientific_verdict: null."""
import json
import sys

import numpy as np

from mf_common import MT, OUT, boxes, log, setup_fonts, xy_to_uv

plt = setup_fonts()
F = OUT / "figs"
F.mkdir(exist_ok=True)
RNG = np.random.default_rng(0)
KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}


def thin(idx, n):
    return idx if len(idx) <= n else np.sort(RNG.choice(idx, n, replace=False))


def frame(ax, box):
    eu, ev = box["eval_u"], box["eval_v"]
    ax.plot([eu[0], eu[1], eu[1], eu[0], eu[0]], [ev[0], ev[0], ev[1], ev[1], ev[0]], "k-", lw=0.6)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


def fig_band_v2():
    G = np.load(MT / "defs/gt_classes.npz")
    X = G["xyz"]
    box = boxes()["B173nb"]
    fig, axs = plt.subplots(2, 2, figsize=(17, 11), constrained_layout=True)
    sm = None
    for i, p in enumerate(("LoD2", "ALS")):
        r1 = np.load(MT / "defs" / f"rows_{p}.npz")
        rv1 = np.load(MT / "metrics" / f"b1_{p}_rows.npz")
        rv2 = np.load(OUT / "metrics" / f"b1_{p}_rows.npz")
        R2 = np.load(OUT / "regions_v2" / f"regions_ext_v2_B173nb_b10_{p}.npz")
        code2 = R2["code_ext_v2"][r1["patch"]]
        for j, (tag, roof, inb, val) in enumerate((
                ("시험 계산(v1) 띠", (r1["code"] == 2) & (r1["kind"] == 1), G["in_band"][r1["point"]], rv1["dz"]),
                ("새 띠(v2), 가파른 면은 법선 거리", (code2 == 2) & (r1["kind"] == 1), rv2["acc_in_band_v2"], np.where(rv2["acc_in_band_v2"], np.nan, rv2["acc_val"])))):
            ax = axs[i, j]
            mb = thin(np.nonzero(roof & inb)[0], 300_000)
            mr = thin(np.nonzero(roof & ~inb & np.isfinite(val))[0], 400_000)
            uvb = xy_to_uv(X[r1["point"][mb], :2])
            ax.scatter(uvb[:, 0], uvb[:, 1], s=0.2, c="#bdbdbd", linewidths=0, rasterized=True)
            uv = xy_to_uv(X[r1["point"][mr], :2])
            sm = ax.scatter(uv[:, 0], uv[:, 1], s=0.25, c=val[mr], cmap="RdBu_r", vmin=-0.2, vmax=0.2, linewidths=0, rasterized=True)
            frame(ax, box)
            share = float(inb[roof].mean()) if roof.any() else 0.0
            ax.set_title(f"{KO[p]} 씨앗 0 — {tag}: 뺀 몫 {100 * share:.1f} %, 남은 점 {int((roof & ~inb).sum()):,}", fontsize=11)
    fig.colorbar(sm, ax=axs, shrink=0.6, label="결과 − 참값 (m; 완만한 면은 높이 차, 가파른 면은 법선 거리)")
    fig.suptitle("B173nb_b10 지지 일치 영역의 지붕 점: 시험 계산의 가장자리 띠(왼쪽)와 새 띠(오른쪽). 회색 = 띠로 뺀 점", fontsize=12, x=0.01, ha="left")
    fig.savefig(F / "band_v2.png", dpi=85, bbox_inches="tight")
    plt.close(fig)


FIGS = dict(band_v2=fig_band_v2)

if __name__ == "__main__":
    for nm in (sys.argv[1:] or list(FIGS)):
        FIGS[nm]()
        log("figure", nm)

"""PHD-MAIN-PHOTOFIG-v1 figure 0: the places of the experiment sites. (jointbuildgs:dev, CPU)

  python f0_sites.py   -> /docs/figures/photo_fig0_sites.png|pdf|json
Base = the thesis figure 6.1 (가) base (PH/ch6_support_v1/PHD-CH6-SUPPORT-v1/t3/ortho_overview.npz: 0.5 m colour grid of the drone LiDAR
colours, MVS colours lightened where none; scripts/phd/ch6_support_v1/t3_fig61.py:189-192), as the request 5.7 asks; the thesis figure
files are not touched. (가) the four evaluation ranges (solid, the 6.1 colours) and the places of figures 1-6 (numbers). (나) the same +
the search region each site's tolerance came from (dashed, the site colour: B0 -> B0, B173 주변 -> R2, R1 -> R1) and the other four search
regions (R3E, R4, R5, SW; grey dashed, no names). scientific_verdict: null"""
import numpy as np

import pf_geo as G
from pf_common import DOCS, PH, PREP, box, cfg, jdump, jl, now, xy_to_uv

BCOL = {"B0_b10": "#c0392b", "B173nb_b10": "#1a5276", "B173_b0": "#117a65", "R1rep_b10": "#7d3c98"}
BNAME = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "B173_b0": "B173만", "R1rep_b10": "R1"}
SEARCH = {"B0_b10": "B0", "B173nb_b10": "R2", "R1rep_b10": "R1"}
OTHER = ("R3E", "R4", "R5", "SW")


def main():
    plt = G.setup_plt()
    import matplotlib.patheffects as pe
    halo = [pe.withStroke(linewidth=2.6, foreground="white")]
    C = cfg(); P = C["places"]
    OV = np.load(PH / "ch6_support_v1/PHD-CH6-SUPPORT-v1/t3/ortho_overview.npz")
    rgb = OV["rgb"]; u0, v0, res = float(OV["u0"]), float(OV["v0"]), float(OV["res"])
    H, W = rgb.shape[:2]
    RNG = jl(PREP / "step01/ranges.json")
    pts = [("1·2", "B173nb_b10", P["fig1"]["section"]["centre_xy"]), ("4", "B173nb_b10", P["fig4"]["centre"][:2]),
           ("3", "R1rep_b10", P["fig3"]["section"]["centre_xy"]), ("3", "R1rep_b10", P["fig3_extra"]["section"]["centre_xy"]),
           ("3-나", "R1rep_b10", P["fig3b"]["section"]["centre_xy"]), ("5", "B0_b10", P["fig5"]["section"]["centre_xy"])]
    for site in ("B173nb_b10", "R1rep_b10"):
        for f in P["fig6"][site]["faces"]:
            pts.append(("6", site, f["section"]["centre_xy"]))
    fig, axs = plt.subplots(2, 1, figsize=(11, 14.5), constrained_layout=True)
    for j, ax in enumerate(axs):
        ax.imshow(rgb, origin="lower", extent=[u0, u0 + W * res, v0, v0 + H * res], interpolation="bilinear", alpha=0.9)
        if j == 1:
            for site, rid in SEARCH.items():
                p = xy_to_uv(np.asarray(RNG[rid]["polygon_local"], np.float64)); p = np.vstack([p, p[:1]])
                ax.plot(p[:, 0], p[:, 1], color=BCOL[site], lw=1.6, ls="--")
            for rid in OTHER:
                p = xy_to_uv(np.asarray(RNG[rid]["polygon_local"], np.float64)); p = np.vstack([p, p[:1]])
                ax.plot(p[:, 0], p[:, 1], color="#7f7f7f", lw=1.1, ls="--")
        for site in BCOL:
            b = box(site)
            r = np.array([[b["eval_u"][0], b["eval_v"][0]], [b["eval_u"][1], b["eval_v"][0]], [b["eval_u"][1], b["eval_v"][1]], [b["eval_u"][0], b["eval_v"][1]], [b["eval_u"][0], b["eval_v"][0]]])
            ax.plot(r[:, 0], r[:, 1], color=BCOL[site], lw=2.0)
            ax.text(r[0, 0] + 1, r[0, 1] - 1.5, BNAME[site], color=BCOL[site], fontsize=9, fontweight="bold", va="bottom", path_effects=halo)
        for lab, site, xy in pts:
            uv = xy_to_uv(np.atleast_2d(np.asarray(xy, np.float64)))[0]
            ax.plot(uv[0], uv[1], "o", color="k", ms=4)
            ax.text(uv[0] + 2, uv[1] + 2, lab, fontsize=8.5, color="k", path_effects=halo)
        ax.set_xlim(u0, u0 + W * res); ax.set_ylim(v0, v0 + H * res); ax.invert_yaxis(); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        ax.text(0.01, 0.99, "(가) 실험 지역 넷의 평가 범위(실선)와 그림 1~6의 자리(번호)" if j == 0 else
                "(나) 같은 바탕에 허용 오차를 구한 탐색 지역(같은 색 점선)과 나머지 탐색 지역 넷(회색 점선)", transform=ax.transAxes, va="top", fontsize=10,
                bbox=dict(fc="w", ec="none", alpha=0.85))
    fig.suptitle("실험 지역의 자리", fontsize=14)
    for ext in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"photo_fig0_sites.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    jdump(DOCS / "figures/photo_fig0_sites.json", dict(base="PH/ch6_support_v1/PHD-CH6-SUPPORT-v1/t3/ortho_overview.npz (thesis figure 6.1 (가) base)",
                                                       places=[dict(label=l, site=s, xy=[float(x) for x in xy]) for l, s, xy in pts],
                                                       search_regions=dict(site_colour=SEARCH, grey=list(OTHER)),
                                                       caption="(가) 실험 지역 넷의 평가 범위(실선)와 그림 1~6의 자리. (나) 같은 바탕에 실험 지역마다 허용 오차를 구한 탐색 지역(같은 색 점선: B0는 B0, B173 주변은 R2, R1은 R1)과 나머지 탐색 지역 넷(회색 점선, 이름 없음).",
                                                       made=now(), scientific_verdict=None))
    print("ok", len(pts))


if __name__ == "__main__":
    main()

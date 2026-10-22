"""PHD-MAIN-AXES71-v2 일 6 (9.1): the cell maps (jointbuildgs:dev, CPU; reads the cells and the clumps, no result).

  python a6_maps.py [case ...]   -> /docs/figures/일6_영역지도_<site>_<prior>.png|pdf|json (top view + two oblique views)

Per case the in-range prior patches coloured by their cell (config cells.colours; 한계 and 참값 없음 hatched, config cells.hatch); the patches
of clumps under 2.5 m2 lighter (config cells.small_clump_alpha). Views: ax_map (top orthographic, north up, scale bar; oblique 45 deg,
azimuths 225 and 45 deg). Below the figure: the area share of every cell (일 2 table). Legend: the cell names only. [새로 그림]
scientific_verdict: null."""
import sys

import numpy as np

import ax_map as MP
from ax_common import CASES, CELL_KO, CELLS, CFG, CID, DOCS, SITE_KO, PRIOR_KO, WORK, jdump, jl, log, now
from ax_arrays import cells

COL = CFG["cells"]["colours"]
HAT = CFG["cells"]["hatch"]


def main(only=None):
    plt = MP.setup_plt()
    from matplotlib.patches import Patch
    R2 = jl(DOCS / "tables/일2_영역나눔.json")["data"]
    (DOCS / "figures").mkdir(exist_ok=True)
    for site, prior in CASES:
        u = f"{site}/{prior}"
        if only and u not in only:
            continue
        C = cells(site, prior)
        cell = C["cell"].astype(np.int64)
        K = np.load(WORK / f"clumps_{site}_{prior}.npz")
        small = K["clump_area"] < CFG["clumps"]["object_min_m2"]
        idx = np.nonzero(cell >= 0)[0]
        P, pa = MP.patch_points(site, prior, idx)
        lab, sm = cell[pa], small[pa]
        pal = {CID[c]: MP.rgb(COL[c]) for c in CELLS}
        hat = {CID[c]: (MP.rgb(v["bg"]), MP.rgb(v["line"])) for c, v in HAT.items()}
        lo, hi = P.min(0), P.max(0)
        px = CFG["maps"]["px_m"]
        T, Ts = MP.top_labels(P, lab, lo, hi, px, extra=sm)
        top = MP.paint(T, pal, hat, light=Ts & (T >= 0))
        obl = []
        for az in CFG["maps"]["oblique"]["azimuth_deg"]:
            cam = MP.camera(np.percentile(P, 0.5, 0), np.percentile(P, 99.5, 0), az, CFG["maps"]["oblique"]["tilt_deg"])
            O, Os = MP.oblique_labels(cam, P, lab, extra=sm, ss=1)
            obl.append((az, MP.paint(O, pal, hat, light=Os & (O >= 0)), cam))
        H0, W0 = top.shape[:2]
        fig = plt.figure(figsize=(17.0 / 2.54, 11.5 / 2.54))
        ax = fig.add_axes([0.01, 0.20, 0.50, 0.75])
        ax.imshow(top, interpolation="nearest"); ax.set_axis_off()
        MP.scalebar(ax, px, W0, H0, 10.0 if (hi[0] - lo[0]) < 120 else 20.0); MP.north(ax, W0, H0)
        ax.set_title("위에서", fontsize=7)
        for i, (az, img, cam) in enumerate(obl):
            a2 = fig.add_axes([0.52, 0.585 - 0.385 * i, 0.47, 0.37])
            a2.imshow(img, interpolation="nearest"); a2.set_axis_off()
            a2.set_title(f"비스듬히 · 방위 {az:g}°", fontsize=7)
        hs = []
        for c in CELLS:
            if c in HAT:
                hs.append(Patch(facecolor=HAT[c]["bg"], edgecolor=HAT[c]["line"], hatch="////", label=CELL_KO[c], lw=0.4))
            else:
                hs.append(Patch(facecolor=COL[c], edgecolor="#777777", label=CELL_KO[c], lw=0.4))
        fig.legend(handles=hs, loc="lower center", ncol=6, fontsize=6, frameon=False, bbox_to_anchor=(0.5, 0.075))
        d = R2[u]
        tot = d["area_total"]
        txt = " · ".join(f"{CELL_KO[c]} {100 * d['cells'][c]['area'] / tot:.1f}" for c in CELLS)
        fig.text(0.5, 0.03, "넓이 비율 (%): " + txt, ha="center", va="center", fontsize=5.5, wrap=True)
        fig.suptitle(f"{SITE_KO[site]} · {PRIOR_KO[prior]}", fontsize=8, y=0.995)
        stem = DOCS / "figures" / f"일6_영역지도_{site}_{prior}"
        fig.savefig(f"{stem}.png", dpi=300); fig.savefig(f"{stem}.pdf", dpi=300)
        plt.close(fig)
        jdump(f"{stem}.json", dict(task="PHD-MAIN-AXES71-v2", work="일 6 지도", case=u, made=now(), patches=int(len(idx)), px_m=px, extent_m=[lo.tolist(), hi.tolist()],
                                   cameras=[dict(azimuth=az, camera=cam.record()) for az, _, cam in obl], colours=COL, hatch=HAT,
                                   small_clump_rule=f"덩어리 넓이 < {CFG['clumps']['object_min_m2']} m² 옅게", area_share={c: d["cells"][c]["area"] / tot for c in CELLS},
                                   scientific_verdict=None))
        log(u, "map", top.shape)


if __name__ == "__main__":
    main(sys.argv[1:] or None)

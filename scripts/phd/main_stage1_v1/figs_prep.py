"""PHD-MAIN-STAGE1-v1 figures of the preparation stage (jointbuildgs:dev, CPU; pre-training data only).

  python figs_prep.py premise      3.2: nadir photos (the fix's overlay views) with the premise violation (red), the observation error
                                   within the threshold (yellow), the 2 m band (blue) and the other support agreement (green), roof-like
                                   patches of region v3 visible from the view -> /out/figs/premise_overlay.png
scientific_verdict: null."""
import json
import sys

import cv2
import numpy as np
from matplotlib.lines import Line2D

from s1_common import DR, GRID_H, GRID_W, MF, OUT, PRIOR_KO, S0, SITES, Views, setup_fonts
from common import DENSE
from src.phd.metrics_v3.surface import MeshScene

plt = setup_fonts()
COLS = {"viol": "#d62728", "within": "#ffbf00", "band": "#1f77b4", "sup": "#2ca02c"}
LAB = {"viol": "전제 위배 영역(관측 오류, |MVS − 사전 정보| > 문턱)", "within": "관측 오류 영역, 문턱 이내", "band": "전제 위배 둘레 2 m의 지지 일치 영역",
       "sup": "그 밖의 지지 일치 영역"}


def prior_mesh(site, prior):
    md = DR / "s02_box" / site
    sh = np.asarray(json.loads((S0 / "s61/box" / site / prior / "summary.json").read_text())["registration"]["shift_applied"], np.float64)
    m = np.load(md / ("lod2_mesh.npz" if prior == "LoD2" else "als_mesh.npz"))
    F = m["F"][m["tri_type"] != 2] if prior == "LoD2" else m["F"]
    return m["V"] + sh, F


def premise():
    V = Views()
    names = {n.split(".")[0]: n for n in V.ims}
    shots = [tuple(s) for s in json.loads((MF / "obs/obs_check.json").read_text())["shots"]]
    fig, axs = plt.subplots(len(shots), 2, figsize=(16, 5.9 * len(shots)), constrained_layout=True)
    for i, (site, view) in enumerate(shots):
        n = names[view]
        img = cv2.cvtColor(cv2.resize(cv2.imread(str(DENSE / "images" / n)), (GRID_W, GRID_H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        C = V.C(n)
        for j, prior in enumerate(("LoD2", "ALS")):
            ax = axs[i, j]
            R = np.load(OUT / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
            c = R["code_ext_v3"]
            grp = np.full(len(c), "", object)
            grp[c == 2] = "sup"
            grp[R["premise_band"]] = "band"
            grp[R["obs_within_threshold"]] = "within"
            grp[R["premise_violation"]] = "viol"
            m = (grp != "") & (R["kind"] == 1) & R["in_eval"]
            P = R["centre"][m]
            g = grp[m]
            u, vv, z = V.project(n, P)
            ins = (z > 0) & (u >= 0) & (u < GRID_W) & (vv >= 0) & (vv < GRID_H)
            Vm, Fm = prior_mesh(site, prior)
            sc = MeshScene(Vm, Fm)
            dvec = P - C[None, :]
            dist = np.linalg.norm(dvec, axis=1)
            th = sc.cast(np.broadcast_to(C, P.shape), dvec / dist[:, None])
            vis = ins & (th >= dist - 0.3)
            ax.imshow(img)
            for k in ("sup", "band", "within", "viol"):
                mm = vis & (g == k)
                ax.scatter(u[mm], vv[mm], s=0.6, c=COLS[k], linewidths=0, alpha=0.6, rasterized=True)
            if vis.any():
                pad = 30
                ax.set_xlim(max(u[vis].min() - pad, 0), min(u[vis].max() + pad, GRID_W))
                ax.set_ylim(min(vv[vis].max() + pad, GRID_H), max(vv[vis].min() - pad, 0))
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title(f"{site} · {PRIOR_KO[prior]} — {view} (전제 위배 {int((vis & (g == 'viol')).sum()):,}, 문턱 이내 {int((vis & (g == 'within')).sum()):,}, "
                         f"둘레 {int((vis & (g == 'band')).sum()):,} 패치)", fontsize=10)
    fig.legend(handles=[Line2D([], [], marker="s", ls="", color=COLS[k], label=LAB[k], markersize=9) for k in ("viol", "within", "band", "sup")],
               loc="lower center", ncol=2, fontsize=11, bbox_to_anchor=(0.5, -0.03))
    fig.suptitle("연직 사진 위의 전제 위배 영역과 둘레 — 지붕류 패치, 영역 v3 (학습 전 자료)", fontsize=13, x=0.01, ha="left")
    fig.savefig(OUT / "figs/premise_overlay.png", dpi=80, bbox_inches="tight")
    plt.close(fig)
    print("premise overlay")


if __name__ == "__main__":
    {"premise": premise}[sys.argv[1]]()

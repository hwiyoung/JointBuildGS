"""PHD-MAIN-PREP-MEASURE-v1 step 06f (jointbuildgs:dev, CPU): range figure of the chosen case boxes (5.5).

  python step06f_box_ranges_fig.py B0_b10 B173nb_b10 B173_b0 R1rep_b10

Per box: the survey colour ortho in (u, v), the evaluation range (white), the box with its 10 m context band (yellow),
the LoD2 GroundSurface rings of the box mesh (thin grey) and the search range whose tolerance / registration are fixed
(dashed). Writes step06/fig_box_ranges.png. scientific_verdict: null."""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

from common import OUT, SHIFT, SURVEY, uv_to_xy, xy_to_uv

for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
    try:
        font_manager.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
SEARCH_OF = {"B0": "B0", "B173nb": "R2", "B173": "R2", "R1rep": "R1"}


def main():
    rids = sys.argv[1:]
    R = json.loads((OUT / "step06/box_ranges.json").read_text()); S = json.loads((OUT / "step01/ranges.json").read_text())
    BV = json.loads((OUT / "step06/box_views.json").read_text())["views"]
    Sv = np.load(SURVEY / "derived.npz"); rgb = Sv["rgb_mvs"]
    fig, axs = plt.subplots(1, len(rids), figsize=(5.2 * len(rids), 5.4), constrained_layout=True, squeeze=False)
    for ax, rid in zip(axs[0], rids):
        r = R[rid]; u0, u1 = r["u_m"]; v0, v1 = r["v_m"]; pad = 25
        U0, U1, V0, V1 = u0 - pad, u1 + pad, v0 - pad, v1 + pad
        W = int((U1 - U0) / 0.25); H = int((V1 - V0) / 0.25)
        cc, rr = np.meshgrid(np.arange(W), np.arange(H))
        uu = U0 + 0.25 * cc; vv = V0 + 0.25 * rr
        xy = uv_to_xy(np.column_stack([uu.ravel(), vv.ravel()]))
        ix = ((xy[:, 0] + SHIFT[0] - 690700.0) / 0.5).astype(int); iy = ((xy[:, 1] + SHIFT[1] - 5335820.0) / 0.5).astype(int)
        ok = (ix >= 0) & (ix < rgb.shape[1]) & (iy >= 0) & (iy < rgb.shape[0])
        img = np.full((H * W, 3), 255, np.uint8); img[ok] = rgb[iy[ok], ix[ok]]
        ax.imshow(img.reshape(H, W, 3), extent=[U0, U1, V1, V0])
        fp = json.loads((OUT / "step06/mesh" / rid / "footprints.json").read_text())["footprints"]
        for f_ in fp:
            q = xy_to_uv(np.asarray(f_["ring_local"])); ax.plot(q[:, 0], q[:, 1], color="#dddddd", lw=0.6)
        eu, ev = r["eval_u"], r["eval_v"]
        ax.plot([eu[0], eu[1], eu[1], eu[0], eu[0]], [ev[0], ev[0], ev[1], ev[1], ev[0]], color="white", lw=2.2, label="평가 범위")
        ax.plot([u0, u1, u1, u0, u0], [v0, v0, v1, v1, v0], color="#f2c200", lw=2.0, label=f"상자 (맥락 띠 {r['band_m']:.0f} m)")
        srange = S.get(SEARCH_OF[r["box"]])
        if srange and srange["kind"] == "uv_box":
            su, sv = srange["u_m"], srange["v_m"]
            ax.plot([su[0], su[1], su[1], su[0], su[0]], [sv[0], sv[0], sv[1], sv[1], sv[0]], color="#ff5050", lw=1.2, ls="--",
                    label=f"τ·정합을 가져온 찾기 범위 {SEARCH_OF[r['box']]}")
        elif srange:
            q = xy_to_uv(np.asarray(srange["polygon_local"])); q = np.vstack([q, q[:1]])
            ax.plot(q[:, 0], q[:, 1], color="#ff5050", lw=1.2, ls="--", label=f"τ·정합을 가져온 찾기 범위 {SEARCH_OF[r['box']]}")
        ax.set_xlim(U0, U1); ax.set_ylim(V1, V0)
        bv = BV[rid]
        ax.set_title(f"{rid}: {u1 - u0:.0f} × {v1 - v0:.0f} m, 학습 {len(bv['train'])}장 · 평가 {len(bv['evaluation'])}장", fontsize=10)
        ax.legend(fontsize=7.5, loc="lower left", framealpha=0.85); ax.tick_params(labelsize=7)
        ax.set_xlabel("u (m)", fontsize=8); ax.set_ylabel("v (m)", fontsize=8)
    fig.savefig(OUT / "step06/fig_box_ranges.png", dpi=85); plt.close(fig)
    print("ok")


if __name__ == "__main__":
    main()

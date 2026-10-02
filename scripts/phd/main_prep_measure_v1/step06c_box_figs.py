"""PHD-MAIN-PREP-MEASURE-v1 step 06c (jointbuildgs:dev, CPU): box size-rule figure (5.5).

  python step06c_box_figs.py

tau (roof, wall) and registration shift against the context band for every box and prior (step06/box_stability.json),
with the search-range value of the same area for comparison. Writes step06/fig_box_stability.png. scientific_verdict: null."""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

from common import OUT

for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
    try:
        font_manager.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
SEARCH_OF = {"B0": "B0", "B173nb": "R2", "R1rep": "R1", "R4weak": "R4", "R5agree": "R5", "SWdemo": "SW"}


def main():
    S = json.loads((OUT / "step06/box_stability.json").read_text())
    rows = {(r["rid"], r["prior"]): r for r in S["rows"]}
    boxes = [b for b in S["boxes"] if len(S["boxes"][b]["bands"]) > 1]
    fig, axs = plt.subplots(2, len(boxes), figsize=(3.3 * len(boxes), 6.6), constrained_layout=True, squeeze=False)
    for j, b in enumerate(boxes):
        bands = S["boxes"][b]["bands"]
        for i, prior in enumerate(("LoD2", "ALS")):
            ax = axs[i, j]
            tr = [rows[(f"{b}_b{int(x)}", prior)]["tau_roof"] for x in bands]
            tw = [rows[(f"{b}_b{int(x)}", prior)]["tau_wall"] for x in bands]
            sh = [np.linalg.norm(rows[(f"{b}_b{int(x)}", prior)]["shift"]) for x in bands]
            sides = [max(rows[(f"{b}_b{int(x)}", prior)]["side_m"]) for x in bands]
            ax.plot(bands, tr, "o-", color="#1f5fbf", label="허용 오차 지붕")
            if prior == "LoD2":
                ax.plot(bands, tw, "s--", color="#e07b00", label="허용 오차 벽")
            sr = OUT / "step03" / SEARCH_OF[b] / prior / "summary.json"
            if sr.exists():
                ss = json.loads(sr.read_text())
                ax.axhline(ss["tolerance"]["roof"]["tau"], color="#1f5fbf", lw=0.8, ls=":", label=f"찾기 범위 {SEARCH_OF[b]} 지붕")
            for x, t, s_ in zip(bands, tr, sides):
                ax.annotate(f"{s_:.0f} m", (x, t), textcoords="offset points", xytext=(0, 6), fontsize=7, ha="center")
            ax2 = ax.twinx(); ax2.bar(bands, sh, width=3, color="#999999", alpha=0.35); ax2.set_ylim(0, max(0.35, max(sh) * 1.2))
            ax2.tick_params(labelsize=7); ax2.set_ylabel("정합 이동 크기 (m)", fontsize=7)
            ch = S["boxes"][b]["per_prior"][prior].get("chosen")
            ax.set_title(f"{b} {prior}: 안정 띠 = {ch if ch is not None else '없음'}", fontsize=9)
            ax.set_xticks(bands); ax.set_xlabel("맥락 띠 (m)", fontsize=8); ax.tick_params(labelsize=7)
            if j == 0:
                ax.set_ylabel("허용 오차 (m)", fontsize=8)
            ax.legend(fontsize=6.5, loc="upper left")
    fig.suptitle("상자 크기 규칙: 띠를 넓힐 때 허용 오차(선)와 정합 이동(막대) — 점 위 숫자 = 상자의 긴 변", fontsize=10.5)
    fig.savefig(OUT / "step06/fig_box_stability.png", dpi=85); plt.close(fig)
    print("ok")


if __name__ == "__main__":
    main()

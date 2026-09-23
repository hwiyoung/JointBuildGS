"""PHD-STAGE2-PROPAGATION-PREMEASURE-v1 summary figure (jointbuildgs:dev): three panels.
  (1) support locations per surface (bar length, log scale) and their conflict share (bar colour, value at the end)
  (2) cumulative distribution of the item-4 distance, one curve per setting, dots at the 25/50/75/90th percentiles
  (3) one training view of M_N: surface boundaries, agree/conflict marks of support pixels and the propagated judgment
      of the pixels in missing locations (majority 2/3, minimum 3 locations, maximum distance = median)
  python figure.py <out.png>     # mounts: /artifacts (ro), /repo (ro), /out (ro), /fonts (ro), /doc (rw)"""
import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.colors import ListedColormap, Normalize  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from PIL import Image  # noqa: E402

for fp in ["/fonts/NotoSansCJK-Regular.ttc"]:
    if Path(fp).exists():
        fm.fontManager.addfont(fp); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=fp).get_name()
matplotlib.rcParams["axes.unicode_minus"] = False
ART = Path("/artifacts/JointBuildGS")
SCENE = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene/images"
M = Path("/out/measure")
SETTINGS = ["M_N", "M_B", "L_N", "L_B"]
NAME = {"M_N": "LoD2 정상", "M_B": "LoD2 주지붕 +1 m", "L_N": "항공 LiDAR 정상", "L_B": "항공 LiDAR 주지붕 +1 m"}
COL = {"M_N": "#1f4e9c", "M_B": "#6fa8dc", "L_N": "#b35806", "L_B": "#f1a340"}
KIND = {"roof": "지붕", "wall": "벽", "ground": "바닥면", "step": "단차면", "building": "지붕"}
LOD2_NOTE = {3396: "주지붕", 3394: "그늘진 지붕 끝", 3403: "정면 벽", 3404: "끝 경사면", 3393: "뒷지붕", 3387: "날개 지붕", 3389: "날개 지붕"}


def surfaces(setting):
    rows = list(csv.DictReader(open(M / setting / "surfaces.csv")))
    sj = {r["id"]: r for r in json.loads((Path("/out/surfaces") / setting / "surfaces.json").read_text())["surfaces"]}
    return rows, sj


def label(setting, r, sj):
    s = int(r["surface"]); k = KIND.get(r["kind"], r["kind"])
    if setting.startswith("M"):
        note = LOD2_NOTE.get(s, "대상 건물" if r["target"] == "True" else "이웃 건물")
        if s >= 100000:
            return f"{NAME[setting]} · 단차면 {s - 100000} (올린 주지붕 둘레)"
        return f"{NAME[setting]} · 면 {s} {k} ({note})"
    info = sj[s]
    note = "올린 주지붕" if info.get("raised_share", 0) >= 0.5 else ("대상 건물 지붕 포함" if info.get("target") else "이웃 건물")
    return f"{NAME[setting]} · 표면 {s} {k} ({note})"


def main(out_png):
    fig = plt.figure(figsize=(21, 13.5))
    gs = fig.add_gridspec(2, 2, width_ratios=[0.95, 1.3], height_ratios=[0.8, 1.2], hspace=0.22, wspace=0.33)
    ax1 = fig.add_subplot(gs[:, 0]); ax2 = fig.add_subplot(gs[0, 1]); ax3 = fig.add_subplot(gs[1, 1])
    # ---------------------------------------------------------------- (1)
    ylab, vals, shares, colors_setting, ypos = [], [], [], [], []
    y = 0
    for setting in SETTINGS:
        rows, sj = surfaces(setting)
        if setting.startswith("M"):     # target-building surfaces with >= 100 support locations + the two largest neighbours
            tg = [r for r in rows if r["target"] == "True" and int(r["n_support"]) >= 100]
            nb = sorted([r for r in rows if r["target"] != "True"], key=lambda r: -int(r["n_support"]))[:2]
            pick = sorted(tg, key=lambda r: -int(r["n_support"])) + nb
        else:                           # airborne LiDAR surfaces with >= 500 support locations
            pick = sorted([r for r in rows if int(r["n_support"]) >= 500], key=lambda r: -int(r["n_support"]))
        for r in pick:
            ylab.append(label(setting, r, sj)); vals.append(int(r["n_support"])); shares.append(float(r["conflict_share"]))
            colors_setting.append(COL[setting]); ypos.append(y); y += 1
        y += 0.8
    cmap = plt.get_cmap("RdYlGn_r"); norm = Normalize(0, 1)
    ax1.barh(ypos, vals, color=[cmap(norm(s)) for s in shares], edgecolor="#333", linewidth=0.4, height=0.8)
    for yy, v, s in zip(ypos, vals, shares):
        ax1.text(v * 1.08, yy, f"충돌 {100 * s:.0f} %", va="center", fontsize=8)
    ax1.set_yticks(ypos); ax1.set_yticklabels(ylab, fontsize=8)
    for t, c in zip(ax1.get_yticklabels(), colors_setting):
        t.set_color(c)
    ax1.invert_yaxis(); ax1.set_xscale("log"); ax1.set_xlim(1, 2e5)
    ax1.set_xlabel("지지 영역 위치 수 (한 칸 0.25 m, 로그 눈금)")
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap); sm.set_array([])
    cb = fig.colorbar(sm, ax=ax1, orientation="horizontal", fraction=0.025, pad=0.06); cb.set_label("지지 위치 가운데 충돌 비율 (막대 색)")
    ax1.set_title("① 표면별 지지 영역 위치 수와 충돌 비율\n(LoD2: 대상 건물 표면 중 지지 위치 100개 이상 + 가장 큰 이웃 표면 2개; 항공 LiDAR: 지지 위치 500개 이상)", fontsize=10.5)
    # ---------------------------------------------------------------- (2)
    for setting in SETTINGS:
        z = np.load(M / setting / "locations.npz")
        d = z["near"][z["mis"]]
        ok = np.isfinite(d)
        x = np.sort(d[ok]); yv = np.arange(1, len(x) + 1) / len(x)
        summ = json.loads((M / setting / "summary.json").read_text())
        ls = "-" if setting.startswith("M") else "--"
        ax2.step(x, yv, where="post", color=COL[setting], ls=ls, lw=1.8,
                 label=f"{NAME[setting]}: 결측 {len(d):,}곳 (같은 표면에 지지 위치 없음 {int((~ok).sum()):,})")
        for p, v in summ["percentiles_m"].items():
            ax2.plot([v], [np.searchsorted(x, v, side="right") / len(x)], "o", color=COL[setting], ms=5)
    ax2.set_xlim(0, 4); ax2.set_ylim(0, 1.01)
    ax2.set_xlabel("표면 위 거리 (m) — 같은 표면 안, 경계를 넘지 않는 격자 경로")
    ax2.set_ylabel("결측 위치의 누적 비율")
    ax2.grid(alpha=0.3); ax2.legend(fontsize=8, loc="lower right")
    ax2.set_title("② 결측 위치에서 같은 표면의 가장 가까운 지지 위치까지 거리 (누적 분포)\n점 = 25·50·75·90번째 백분위수 (최대 거리 후보)", fontsize=10.5)
    # ---------------------------------------------------------------- (3)
    setting = "M_N"
    summ = json.loads((M / setting / "summary.json").read_text())
    mv = summ["map_view"]
    mp = np.load(M / setting / f"map_{mv}.npz"); z = np.load(M / setting / "locations.npz")
    W, H = 5644, 4082
    idx = mp["idx"].astype(np.int64); loc = mp["loc"].astype(np.int64)
    code = np.zeros(H * W, np.int8)                 # 0 none
    st = z["state"][loc]; jr = z["jref"][loc]
    a1 = mp["a1"]
    code[idx[a1 & mp["agree"]]] = 1                 # agree mark
    code[idx[a1 & mp["conflict"]]] = 2              # conflict mark
    a0 = ~a1
    code[idx[a0 & (st == 1)]] = 3                   # A = 0 pixel of a support location (other views measured it)
    for j, c in ((0, 4), (1, 5), (2, 6), (3, 7)):   # missing location: propagated judgment
        code[idx[a0 & (st == 2) & (jr == j)]] = c
    code[idx[a1 & (st == 2)]] = np.where(mp["agree"][a1 & (st == 2)], 1, 2)
    code = code.reshape(H, W)
    tri = np.load(Path("/out/ids") / setting / f"{mv}.npz")["tri"]
    ts = np.load(Path("/out/surfaces") / setting / "mesh.npz")["tri_surface"]
    surf = np.where(tri >= 0, ts[np.maximum(tri, 0)], -1)
    P = np.load(ART / f"phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1/inputs/maps/prior_{setting}/raw_depth/{mv}.npy")
    surf[~np.isfinite(P)] = -1
    edge = np.zeros_like(surf, bool)
    edge[:, 1:] |= surf[:, 1:] != surf[:, :-1]; edge[1:, :] |= surf[1:, :] != surf[:-1, :]
    # crop to the target building pixels
    rows = {r["id"]: r for r in json.loads((Path("/out/surfaces") / setting / "surfaces.json").read_text())["surfaces"]}
    tgt = np.isin(surf, [s for s, r in rows.items() if r["target"]])
    vv, uu = np.nonzero(tgt)
    pad = 120
    v0, v1 = max(0, vv.min() - pad), min(H, vv.max() + pad); u0, u1 = max(0, uu.min() - pad), min(W, uu.max() + pad)
    img = np.asarray(Image.open(SCENE / f"{mv}.JPG").convert("L"), np.float32)[v0:v1, u0:u1] / 255.0
    cols = ["#00000000", "#9bd19b", "#f4a3a3", "#d9d9d9", "#b2182b", "#1a7a1a", "#7b3294", "#4a6fa5"]
    rgba = np.zeros((v1 - v0, u1 - u0, 4), np.float32)
    cc = code[v0:v1, u0:u1]
    lut = np.array([matplotlib.colors.to_rgba(c) for c in cols], np.float32); lut[0] = (0, 0, 0, 0)
    rgba = lut[cc]; rgba[..., 3] = np.where(cc > 0, 0.85, 0)
    ax3.imshow(0.35 + 0.5 * img, cmap="gray", vmin=0, vmax=1, interpolation="nearest")
    ax3.imshow(rgba, interpolation="nearest")
    e = edge[v0:v1, u0:u1]
    er = np.zeros(e.shape + (4,), np.float32); er[e] = (0, 0, 0, 1)
    from scipy.ndimage import binary_dilation
    er[binary_dilation(e, iterations=5)] = (0, 0, 0, 1)
    ax3.imshow(er, interpolation="nearest")
    ax3.set_xticks([]); ax3.set_yticks([])
    handles = [Patch(color=cols[1], label="지지 · 일치"), Patch(color=cols[2], label="지지 · 충돌"),
               Patch(color=cols[3], label="이 시점은 못 쟀지만 다른 시점이 잰 위치(지지)"),
               Patch(color=cols[4], label="결측 → 충돌로 전파"), Patch(color=cols[5], label="결측 → 일치로 전파"),
               Patch(color=cols[6], label="결측 → 혼재"), Patch(color=cols[7], label="결측 → 근거 부족"),
               Patch(facecolor="white", edgecolor="black", label="검은 선 = 표면 경계")]
    ax3.legend(handles=handles, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.01), ncol=4, frameon=False)
    ax3.set_title(f"③ LoD2 정상 · 학습 시점 {mv[-6:-2]}: 표면 번호 경계, 일치·충돌 표시, 전파된 판정\n(다수의 기준 2/3, 증거의 최소량 3곳, 최대 거리 = 중앙값 {summ['percentiles_m']['50']:.2f} m)", fontsize=10.5)
    fig.suptitle("전파 규칙 사전 측정 — 표면 번호와 일치·충돌 표시로 결측 영역의 판정을 같은 표면의 지지 영역에서 전파 (학습 없음)", fontsize=13)
    fig.savefig(out_png, dpi=130, bbox_inches="tight")
    print("wrote", out_png)


if __name__ == "__main__":
    main(sys.argv[1])

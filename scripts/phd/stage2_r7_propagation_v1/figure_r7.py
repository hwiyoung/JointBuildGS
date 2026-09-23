"""PHD-STAGE2-R7-PROPAGATION-v1 summary figure (jointbuildgs:dev): three panels.
  (1) registered residuals of the tolerance pool (LoD2 roof-like, LoD2 wall-like, airborne LiDAR roof-like; every 10th
      pixel of the 15 views) with the tolerances (data width and the adopted value)
  (2) airborne LiDAR surface numbers in one training view, before and after the building-outline boundaries
  (3) LoD2 nominal, the same view: marks and the propagated judgment at the fixed values, roof-like and wall-like apart
  python figure_r7.py <out.png> [view]    # mounts as stage1_products.py plus /fonts (ro)"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from PIL import Image  # noqa: E402
from scipy.ndimage import binary_dilation  # noqa: E402

import stage1_products as s1  # noqa: E402
from src.phd.prior_propagation_v1 import conversion as conv  # noqa: E402
from src.phd.prior_propagation_v1 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v1 import rule  # noqa: E402

for fp in ["/fonts/NotoSansCJK-Regular.ttc"]:
    if Path(fp).exists():
        fm.fontManager.addfont(fp); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=fp).get_name()
matplotlib.rcParams["axes.unicode_minus"] = False
SCENE_IMG = s1.ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene/images"
out_png = sys.argv[1]
VIEW = sys.argv[2] if len(sys.argv) > 2 else "DJI_20241217101313_0009_D"          # panel 3 (front wall and roof)
VIEW2 = sys.argv[3] if len(sys.argv) > 3 else "DJI_20241217101343_0024_D"         # panel 2 (roofs seen from above)
TOL = json.loads((s1.OUT / "tolerance.json").read_text())["priors"]
V = s1.CFG["values"]


def residual_samples(setting, stride=10):
    m, ts, n_used, table = s1.surfaces_of(setting, "lod2" if setting.startswith("L") else "poly")
    target = np.zeros(int(max(table) + 1), bool)
    for e, r in table.items():
        target[e] = bool(r["target"]) and r["is_building_face"]
    out = {conv.KIND_ROOF: [], conv.KIND_WALL: []}
    for stem in s1.VIEWS:
        tri, P, A, M = s1.view_arrays(setting, stem)
        n, s, hit = s1.pixel_normals(tri, ts, n_used)
        pix = np.nonzero(np.isfinite(P) & hit & (s >= 0) & (A == 1))[0]
        pix = pix[target[s[pix]]][::stride]
        d, _ = s1.rays(stem, pix)
        r = (M[pix] - P[pix]).astype(np.float64) * conv.factor(n[pix], d)
        k = conv.surface_kind(n[pix, 2])
        for kk in out:
            out[kk].append(r[k == kk])
    return {k: np.concatenate(v) for k, v in out.items()}


fig = plt.figure(figsize=(22, 13.5))
gs = fig.add_gridspec(2, 4, height_ratios=[1, 1.05], hspace=0.25, wspace=0.08)
ax1 = fig.add_subplot(gs[0, 0:2])
# ---------------------------------------------------------------- (1)
rm = residual_samples("M_N"); rl = residual_samples("L_N")
bins = np.linspace(-0.6, 0.6, 241)
for x, col, lab in ((rm[conv.KIND_ROOF], "#1f4e9c", "LoD2 지붕형"), (rm[conv.KIND_WALL], "#7b3294", "LoD2 벽형 (면에 수직)"),
                    (rl[conv.KIND_ROOF], "#d95f02", "항공 LiDAR 지붕형")):
    ax1.hist(x, bins=bins, density=True, histtype="step", lw=1.8, color=col, label=f"{lab}: 표본 {x.size:,} (10분의 1)")
for p, kind, col, ls in (("M", "roof", "#1f4e9c", "--"), ("M", "wall", "#7b3294", "--"), ("L", "roof", "#d95f02", ":")):
    t = TOL[p]["data"][kind]["tau"]
    for sgn in (-1, 1):
        ax1.axvline(sgn * t, color=col, ls=ls, lw=1.1)
    ax1.text(t, ax1.get_ylim()[1] * (0.93 if p == "M" and kind == "roof" else 0.83 if kind == "wall" else 0.73), f" {t:.3f} m", color=col, fontsize=8)
ax1.set_xlim(-0.6, 0.6); ax1.set_xlabel("정합 뒤 잔차 (m) — 지붕형: 연직, 벽형: 면에 수직; + = MVS가 사전 정보보다 멀다(아래·안쪽)")
ax1.set_ylabel("밀도")
ax1.legend(fontsize=8.5, loc="upper left")
ax1.set_title("① 대상 건물의 지붕·벽 잔차와 허용 오차 (정상 장면)\n선 = 실측 폭 2.5×NMAD. 채택한 값은 사양 하한 때문에 LoD2 지붕 1.00 m, 항공 LiDAR 0.12 m (그림 밖), LoD2 벽 0.195 m (사양 없음)", fontsize=10)

# ---------------------------------------------------------------- (2)
W, H = 5644, 4082
tri = np.load(s1.OUT / "ids/L_N" / f"{VIEW2}.npz")["tri"]
P = np.load(s1.MAPS / f"prior_L_N/raw_depth/{VIEW2}.npy")
img2 = np.asarray(Image.open(SCENE_IMG / f"{VIEW2}.JPG").convert("L"), np.float32) / 255.0
img = np.asarray(Image.open(SCENE_IMG / f"{VIEW}.JPG").convert("L"), np.float32) / 255.0
rng = np.random.default_rng(3)


def surface_rgb(var):
    ts = np.load(s1.OUT / "products/L_N" / f"tri_surface_{var}.npy")
    table = {r["ext"]: r for r in json.loads((s1.OUT / "products/L_N" / f"surfaces_{var}.json").read_text())["surfaces"]}
    s = np.where(tri >= 0, ts[np.maximum(tri, 0)], -1)
    s[~np.isfinite(P)] = -1
    ext_ids = np.unique(s[s >= 0])
    lut = {e: rng.uniform(0.25, 1.0, 3) for e in ext_ids}
    rgb = np.stack([0.35 + 0.5 * img2] * 3, -1)
    for e in ext_ids:
        if not table[e]["is_building_face"]:
            continue
        mm = s == e
        rgb[mm] = 0.35 * rgb[mm] + 0.65 * lut[e]
    rgb[s == -2] = 0.35 * rgb[s == -2] + 0.65 * np.array([0.55, 0.55, 0.55])
    edge = np.zeros(s.shape, bool)
    edge[:, 1:] |= s[:, 1:] != s[:, :-1]; edge[1:, :] |= s[1:, :] != s[:-1, :]
    edge &= (s >= 0) | (np.roll(s, 1, 0) >= 0)
    rgb[binary_dilation(edge, iterations=3)] = 0
    nb = sum(1 for e in ext_ids if table[e]["is_building_face"])
    return rgb, nb


bv, bu = np.nonzero(np.isfinite(P) & (tri >= 0))
tsb = np.load(s1.OUT / "products/L_N" / "tri_surface_lod2.npy")
tb = {r["ext"]: r for r in json.loads((s1.OUT / "products/L_N" / "surfaces_lod2.json").read_text())["surfaces"]}
sb = np.where(tri >= 0, tsb[np.maximum(tri, 0)], -1)
isb = np.isin(sb, [e for e, r in tb.items() if r["is_building_face"]]) & np.isfinite(P)
vv, uu = np.nonzero(isb)
crop2 = (slice(max(0, vv.min() - 80), min(H, vv.max() + 80)), slice(max(0, uu.min() - 80), min(W, uu.max() + 80)))
for i, (var, ttl) in enumerate((("none", "윤곽 경계 전: 가파른 삼각형만"), ("lod2", "윤곽 경계 후: + LoD2 바닥면 윤곽"))):
    ax = fig.add_subplot(gs[0, 2 + i])
    rgb, nb = surface_rgb(var)
    ax.imshow(np.clip(rgb[crop2], 0, 1)); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"② 항공 LiDAR 표면 — {ttl}\n(학습 시점 {VIEW2[-6:-2]}, 보이는 건물 표면 {nb}개)", fontsize=9.5)
fig.text(0.74, 0.515, "색 = 표면 번호 하나, 회색 = 가파른 삼각형(번호 없음), 검은 선 = 표면 경계", ha="center", fontsize=9)

# ---------------------------------------------------------------- (3)
st = locs.load_store(s1.OUT / "products/M_N" / f"store_poly_c{V['cell_m']}.npz")
state, vote = st["state_spec"], st["vote_spec"]
J, _ = locs.propagate(st, state, vote, V["majority"], V["min_evidence_locations"], V["max_distance_m"])
lm = np.load(s1.OUT / "products/M_N/locmap" / f"{VIEW}.npy").reshape(-1)
A = np.load(s1.MAPS / f"conf/raw_depth/{VIEW}.npy").reshape(-1)
M = np.load(s1.MAPS / f"mvs/raw_depth/{VIEW}.npy").reshape(-1)
Pm = np.load(s1.MAPS / f"prior_M_N/raw_depth/{VIEW}.npy").reshape(-1)
triM = np.load(s1.OUT / "ids/M_N" / f"{VIEW}.npz")["tri"].reshape(-1)
m_, ts_, n_used, table = s1.surfaces_of("M_N", "poly")
n, sext, hit = s1.pixel_normals(triM, ts_, n_used)
idx = np.nonzero(lm >= 0)[0]
d, _ = s1.rays(VIEW, idx)
f = conv.factor(n[idx], d)
kind = conv.surface_kind(n[idx, 2])
tau = np.where(kind == conv.KIND_ROOF, TOL["M"]["spec"]["roof"]["tau"], TOL["M"]["spec"]["wall"]["tau"])
agree = (A[idx] == 1) & (np.abs(M[idx] - Pm[idx]) * f <= tau)
conf = (A[idx] == 1) & ~agree
loc = lm[idx]; stl = state[loc]; jl = J[loc]
code = np.zeros(W * H, np.int8)
c = np.zeros(len(idx), np.int8)
c[agree] = 1; c[conf] = 2
a0 = A[idx] != 1
c[a0 & (stl == rule.ST_SUPPORT)] = 3
for j, cc in ((rule.J_CONFLICT, 4), (rule.J_AGREE, 5), (rule.J_MIXED, 6), (rule.J_INSUFF, 7)):
    c[a0 & (stl == rule.ST_MISSING) & (jl == j)] = cc
code[idx] = c
kmap = np.zeros(W * H, np.int8); kmap[idx] = kind
cols = ["#00000000", "#9bd19b", "#f4a3a3", "#d9d9d9", "#b2182b", "#1a7a1a", "#7b3294", "#4a6fa5"]
lut = np.array([matplotlib.colors.to_rgba(x) for x in cols], np.float32); lut[0] = 0
for i, (kv, ttl) in enumerate(((conv.KIND_ROOF, "지붕형 면"), (conv.KIND_WALL, "벽형 면"))):
    ax = fig.add_subplot(gs[1, 2 * i:2 * i + 2])
    crop = (slice(600, 3900), slice(300, 5400))
    cc = np.where(kmap == kv, code, 0).reshape(H, W)[crop]
    rgba = lut[cc]; rgba[..., 3] = np.where(cc > 0, 0.88, 0)
    ax.imshow(0.35 + 0.5 * img[crop], cmap="gray", vmin=0, vmax=1)
    ax.imshow(rgba); ax.set_xticks([]); ax.set_yticks([])
    ttl2 = f"허용 오차 {TOL['M']['spec']['roof' if kv == 1 else 'wall']['tau']:.3f} m"
    ax.set_title(f"③ LoD2 정상 · 학습 시점 {VIEW[-6:-2]} — {ttl} ({ttl2}): 일치·충돌 표시와 전파된 판정\n(다수의 기준 2/3, 최소량 {V['min_evidence_locations']}곳, 최대 거리 {V['max_distance_m']:g} m)", fontsize=10)
handles = [Patch(color=cols[1], label="지지 · 일치"), Patch(color=cols[2], label="지지 · 충돌"), Patch(color=cols[3], label="이 시점은 못 쟀지만 다른 시점이 잰 위치(지지)"),
           Patch(color=cols[4], label="결측 → 충돌로 전파"), Patch(color=cols[5], label="결측 → 일치로 전파"), Patch(color=cols[6], label="결측 → 혼재"),
           Patch(color=cols[7], label="결측 → 근거 부족")]
fig.legend(handles=handles, loc="lower center", ncol=7, fontsize=9, frameon=False, bbox_to_anchor=(0.5, 0.045))
fig.suptitle("위치 기반 판정의 전파를 둘째 단계에 넣기 — 새 정의로 다시 잰 사전 측정 (학습 없음)", fontsize=13)
fig.savefig(out_png, dpi=110, bbox_inches="tight")
print("wrote", out_png)

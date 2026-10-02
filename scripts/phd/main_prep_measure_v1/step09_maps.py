"""PHD-MAIN-PREP-MEASURE-v1 step 09 (jointbuildgs:dev, CPU): pre-training judgment maps of a range (5.2-5.3).

  python step09_maps.py <range_id> [--stage1-sub step03] [--gt-sub step04] [--mesh-sub step02] [--out-sub step09] [--tag ""]

Top view (u, v; 0.25 m raster, the highest unit of a cell is drawn) of every judgment unit inside the range, per prior:
(a) patch state and judgment (support agree / support conflict / missing -> agree, conflict, mixed, insufficient / invisible),
(b) pre-training conflict share per footprint (confidence-1 building-face pixels that conflict, all training views) and the
points that initialisation would not plant (missing patches judged conflict), (c) the true label of the patch (step 04).
Writes <out>/<range>/map_<prior>.png and map_summary.json. scientific_verdict: null."""
import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import ListedColormap, Normalize
from matplotlib.patches import Patch, Polygon as MPoly
import numpy as np

from common import OUT, jdump, xy_to_uv
from src.phd.prior_propagation_v4 import rule

for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
    try:
        font_manager.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

CLS = ["지지·일치", "지지·충돌", "결측→일치", "결측→충돌", "결측→혼재", "결측→근거 부족", "비가시"]
CCOL = ["#a6dba0", "#f4a582", "#1b7837", "#b2182b", "#f0b429", "#fee391", "#4a6fd1"]
TCOL = ["#2a9d3a", "#d62728", "#d9d9d9"]


def classes(U):
    st, vo, J = U["state"], U["vote"], U["J"]
    c = np.full(len(st), -1, np.int8)
    c[(st == rule.ST_SUPPORT) & (vo == rule.V_AGREE)] = 0
    c[(st == rule.ST_SUPPORT) & (vo == rule.V_CONFLICT)] = 1
    c[(st == rule.ST_MISSING) & (J == rule.J_AGREE)] = 2
    c[(st == rule.ST_MISSING) & (J == rule.J_CONFLICT)] = 3
    c[(st == rule.ST_MISSING) & (J == rule.J_MIXED)] = 4
    c[(st == rule.ST_MISSING) & (J == rule.J_INSUFF)] = 5
    c[st == rule.ST_INVISIBLE] = 6
    return c


def raster(uv, z, val, ext, cell=0.25, fill=-1):
    (u0, u1), (v0, v1) = ext
    nu = int(np.ceil((u1 - u0) / cell)); nv = int(np.ceil((v1 - v0) / cell))
    iu = np.floor((uv[:, 0] - u0) / cell).astype(int); iv = np.floor((uv[:, 1] - v0) / cell).astype(int)
    ok = (iu >= 0) & (iu < nu) & (iv >= 0) & (iv < nv)
    o = np.argsort(z[ok])
    img = np.full((nv, nu), fill, np.int16)
    img[iv[ok][o], iu[ok][o]] = val[ok][o]
    return img


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("range_id")
    ap.add_argument("--stage1-sub", default="step03"); ap.add_argument("--gt-sub", default="step04")
    ap.add_argument("--mesh-sub", default="step02"); ap.add_argument("--out-sub", default="step09"); ap.add_argument("--tag", default="")
    a = ap.parse_args()
    rid = a.range_id
    O = OUT / a.out_sub / rid; O.mkdir(parents=True, exist_ok=True)
    mesh_dir = OUT / a.mesh_sub / rid
    rng = json.loads((mesh_dir / "range.json").read_text())
    fp = json.loads((mesh_dir / "footprints.json").read_text())["footprints"]
    summ_all = {}
    for prior in ("LoD2", "ALS"):
        S1 = OUT / a.stage1_sub / rid / prior
        if not (S1 / "units.npz").exists():
            continue
        U = dict(np.load(S1 / "units.npz"))
        summ = json.loads((S1 / "summary.json").read_text())
        inr = U["loc_in_range"]
        uv = xy_to_uv(U["loc_center"][:, :2]); z = U["loc_center"][:, 2]
        if rng["kind"] == "uv_box":
            ext = ((rng["u_m"][0] - 3, rng["u_m"][1] + 3), (rng["v_m"][0] - 3, rng["v_m"][1] + 3))
        else:
            q = uv[inr]; ext = ((q[:, 0].min() - 3, q[:, 0].max() + 3), (q[:, 1].min() - 3, q[:, 1].max() + 3))
        c = classes(U)
        sel = inr & (c >= 0)
        # walls drawn under roofs: shift wall z down so a roof unit wins its cell
        zz = np.where(U["loc_kind"] == 2, z - 1000.0, z)
        img_c = raster(uv[sel], zz[sel], c[sel], ext)
        lab = None
        G = OUT / a.gt_sub / rid / f"labels_{prior}.npz"
        if G.exists():
            L = np.load(G); lab = np.where(L["excluded"], -2, L["label"]).astype(np.int16)
            img_t = raster(uv[inr], zz[inr], np.where(lab[inr] < 0, 2, lab[inr]).astype(np.int16), ext)
            ex_img = raster(uv[inr], zz[inr], (lab[inr] == -2).astype(np.int16), ext, fill=0)
        cov = {r["building"]: r for r in json.loads((S1 / "coverage_footprints.json").read_text())}
        asp = (ext[1][1] - ext[1][0]) / (ext[0][1] - ext[0][0])
        fig, axs = plt.subplots(1, 3, figsize=(3 * 6.8 * min(1.0, 1.0 / asp) + 2.5, 7.6), constrained_layout=True)
        extent = [ext[0][0], ext[0][1], ext[1][1], ext[1][0]]
        axs[0].imshow(np.where(img_c < 0, 7, img_c), cmap=ListedColormap(CCOL + ["#ffffff"]), vmin=0, vmax=7, extent=extent, interpolation="nearest")
        axs[0].legend(handles=[Patch(color=CCOL[i], label=CLS[i]) for i in range(7)], fontsize=7.5, loc="lower left", framealpha=0.85)
        axs[0].set_title(f"(가) 패치 상태와 판정 — {rid} {prior}", fontsize=10)
        cm = plt.get_cmap("Reds"); nrm = Normalize(0, 0.6)
        for r in fp:
            ring = xy_to_uv(np.asarray(r["ring_local"]))
            cv_ = cov.get(r["building"])
            share = (cv_["cf"] / cv_["a1"]) if (cv_ and cv_["a1"] > 0) else None
            axs[1].add_patch(MPoly(ring, closed=True, facecolor=cm(nrm(share)) if share is not None else "#eeeeee", edgecolor="#555555", lw=0.4))
        up = inr & (U["state"] == rule.ST_MISSING) & (U["J"] == rule.J_CONFLICT)
        axs[1].plot(uv[up, 0], uv[up, 1], ",", color="black", alpha=0.6)
        sm = plt.cm.ScalarMappable(norm=nrm, cmap=cm); fig.colorbar(sm, ax=axs[1], fraction=0.035, label="발자국별 충돌 비율 (신뢰도 1 픽셀)")
        axs[1].set_xlim(ext[0]); axs[1].set_ylim(ext[1][1], ext[1][0]); axs[1].set_aspect("equal")
        axs[1].set_title(f"(나) 학습 전 충돌 비율과 심지 않을 점(검정, {int(up.sum()):,}개 패치)", fontsize=10)
        if lab is not None:
            timg = np.where(ex_img > 0, 3, img_t); timg = np.where(img_t < 0, 4, timg)
            axs[2].imshow(timg, cmap=ListedColormap(TCOL + ["#7f7f7f", "#ffffff"]), vmin=0, vmax=4, extent=extent, interpolation="nearest")
            axs[2].legend(handles=[Patch(color=TCOL[0], label="참 일치"), Patch(color=TCOL[1], label="참 충돌"), Patch(color=TCOL[2], label="참값 없음"),
                                   Patch(color="#7f7f7f", label="평가 제외(나무·일시 반사)")], fontsize=7.5, loc="lower left", framealpha=0.85)
            axs[2].set_title("(다) 참 라벨 (드론 LiDAR, 범위 허용 오차)", fontsize=10)
        for ax in axs:
            ax.set_xlabel("u (m)", fontsize=8); ax.set_ylabel("v (m)", fontsize=8); ax.tick_params(labelsize=7)
            if rng["kind"] == "uv_box":
                ax.plot([rng["u_m"][0], rng["u_m"][1], rng["u_m"][1], rng["u_m"][0], rng["u_m"][0]],
                        [rng["v_m"][0], rng["v_m"][0], rng["v_m"][1], rng["v_m"][1], rng["v_m"][0]], color="#333333", lw=0.8, ls="--")
        t = summ["tolerance"]; rg = summ["registration"]
        fig.suptitle(f"{rid} {prior}{a.tag}: 허용 오차 지붕 {t['roof']['tau']:.3f} m · 벽 {t['wall']['tau']:.3f} m, 정합 이동 "
                     f"({rg['shift_applied'][0]:+.3f}, {rg['shift_applied'][1]:+.3f}, {rg['shift_applied'][2]:+.3f}) m, 학습 영상 {summ['views']}장",
                     fontsize=11, x=0.01, ha="left")
        fig.savefig(O / f"map_{prior}.png", dpi=80)
        plt.close(fig)
        area = lambda m: float(U["loc_area"][m].sum())
        k = U["loc_kind"]
        rows = {}
        for i, name in enumerate(CLS):
            rows[name] = dict(roof_m2=round(area(inr & (c == i) & (k == 1)), 1), wall_m2=round(area(inr & (c == i) & (k == 2)), 1))
        summ_all[prior] = dict(classes=rows, unplanted_patches=int(up.sum()), unplanted_area_m2=round(area(up), 1),
                               pixels_without_unit=summ.get("pixels_without_unit"), unplanted=summ.get("unplanted"))
    jdump(O / "map_summary.json", dict(range=rid, stage1=a.stage1_sub, summary=summ_all, scientific_verdict=None))
    print("maps", rid, list(summ_all))


if __name__ == "__main__":
    main()

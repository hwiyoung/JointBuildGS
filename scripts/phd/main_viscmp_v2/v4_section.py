"""PHD-MAIN-VISCMP-v2 V4 by the request's fallback: the renders of v4_wall.py did not show the missing area's shape, so the photo-figure-3
(다) horizontal section (wall 19, the missing patches' median height, 0.5 m band, along the wall) is drawn as lines: GT points and the TSDF
mesh of 학습 전 사전 정보, 2DGS, GeoGS, 결합, 본 방법, 결측 지키기, names at the line ends (no legend). The across axis = the OUTWARD
normal (+ = outside; the photo-figure correction of 10-20), shown +-2 m as figure 3 (다); the along axis = the missing patches' extent +- 2 m,
the missing extent lightly shaded. Photo = DJI_20241217101317_0011_D with the section as one line. Values = the face's missing recall (0.2 m).
  python v4_section.py -> /docs/figures/V4_missing_R1_LoD2.png|pdf|json (the render version stays as V4_missing_R1_LoD2_render.*)
scientific_verdict: null"""
import time

import numpy as np
from matplotlib.collections import LineCollection

import vc_common  # noqa: F401
import p0_places as P0
import pf_geo as G
import vc_fig as VF
import vc_render as RD
from vc_common import CFG, DOCS, jdump, jl, log, mesh_path, now, res_name
from v4_wall import recall

KEY = "V4"
LINES = ["학습 전 사전 정보", "2DGS", "GeoGS", "결합", "본 방법", "결측 지키기"]
COL = {"학습 전 사전 정보": "#7f7f7f", "2DGS": "#9467bd", "GeoGS": "#8c564b", "결합": "#17becf", "본 방법": "#ff7f0e", "결측 지키기": "#1f77b4"}


def main():
    t0 = time.time()
    C = jl(CFG); P = C["places"][KEY]; F = C["figures"][KEY]
    site, prior, ext = P["site"], P["prior"], P["ext"]
    sec = jl("/repo/configs/phd/main_photofig_v1/photofig_v1.json")["places"]["fig3"]["section"]
    c = np.asarray(sec["centre_xy"], np.float64); a = np.asarray(sec["axis_xy"], np.float64); a /= np.linalg.norm(a)
    n_out = np.asarray(P["outward_normal"], np.float64)[:2]; n_out /= np.linalg.norm(n_out)
    z0, sr = sec["z_m"], sec["s_range_m"]
    R = P0.region(site, prior); U = P0.store(site, prior)
    se = R["surf_ext"].astype(int); ev = R["in_eval"].astype(bool); code = R["code_ext_v3"].astype(int)
    mp = np.nonzero(ev & (se == ext) & np.isin(code, [4, 13]))[0]
    smp = (U["loc_center"][mp][:, :2] - c) @ a
    xl = [max(sr[0], smp.min() - 2.0), min(sr[1], smp.max() + 2.0)]
    ends = np.array([c + sr[0] * a, c + sr[1] * a])
    box = [float(ends[:, 0].min()), float(ends[:, 1].min()), float(ends[:, 0].max()), float(ends[:, 1].max())]
    segs, rec, vals = {}, {}, {}
    for m in LINES:
        res = res_name(m, prior)
        p = mesh_path(site, prior, res)
        if p is None:
            rec[m] = dict(result=res, status="결과 없음"); continue
        V, Fc, info = RD.load_mesh(p, box, margin=3.0)
        sg = G.cut_horizontal(V, Fc, z0, c, a, sr)            # across = (X - c) . rot90(a), the inward normal here
        rot = np.array([-a[1], a[0]])
        sgn = float(np.sign(rot @ n_out))                      # -1: turn to the outward normal
        segs[m] = sg * np.array([1.0, sgn])
        vals[m] = recall(site, prior, res, mp)
        rec[m] = dict(result=res, status="ok", mesh=str(p), mesh_info=info, segments=int(len(sg)))
        log(m, res, vals[m])
    Xg = VF.gt(site, box, margin=3.0)
    d = Xg[:, :2] - c
    gs_, gd = d @ a, d @ n_out
    mg = (np.abs(Xg[:, 2] - z0) <= 0.25) & (gs_ >= sr[0]) & (gs_ <= sr[1]) & (np.abs(gd) <= 3.0)
    # photo
    pv = P["photo"]
    pc = RD.Pinhole(pv, (0, 0, 1400, 1013), 1)
    E3 = np.array([[*(c + xl[0] * a), z0], [*(c + xl[1] * a), z0]])
    eu, ev_, _ = pc.project(E3)
    Qm = VF.quads(U, mp)
    pbox = VF.crop_box(pv, Qm, 1.0)
    ph = VF.photo(pv, pbox)
    # draw
    plt = G.setup_plt()
    fig = plt.figure(figsize=(17, 6.2))
    gsp = fig.add_gridspec(1, 2, width_ratios=[1.0, 3.6], wspace=0.12)
    ax0 = fig.add_subplot(gsp[0, 0])
    ax0.imshow(ph, extent=(pbox[0], pbox[2], pbox[3], pbox[1])); ax0.plot(eu, ev_, color="#ffd400", lw=2.2)
    ax0.set_xlim(pbox[0], pbox[2]); ax0.set_ylim(pbox[3], pbox[1]); ax0.set_xticks([]); ax0.set_yticks([]); ax0.set_title("사진", fontsize=12)
    ax0.text(0.5, -0.03, f"영상 {pv}\n노란 선 = 단면 자리", transform=ax0.transAxes, ha="center", va="top", fontsize=9)
    ax = fig.add_subplot(gsp[0, 1])
    ax.axvspan(smp.min() - 0.125, smp.max() + 0.125, color="#ebebeb", zorder=0)
    ax.text(0.5 * (smp.min() + smp.max()), 1.93, "결측 영역", ha="center", va="top", fontsize=10, color="#666666")
    ax.plot(gs_[mg], gd[mg], ".", color="#4d4d4d", ms=1.6, alpha=0.6, zorder=3)
    ends_y = []
    for m, sg in segs.items():
        pri = m == "학습 전 사전 정보"
        ax.add_collection(LineCollection(sg, colors=COL[m], linewidths=1.6 if pri else 2.0, linestyles="--" if pri else "-", zorder=5 if pri else 4))
        mid = sg.mean(1) if len(sg) else np.zeros((0, 2))
        tail = mid[(mid[:, 0] >= xl[1] - 1.5) & (mid[:, 0] <= xl[1]) & (np.abs(mid[:, 1]) <= 2.0)] if len(mid) else mid
        ends_y.append([m, float(np.median(tail[:, 1])) if len(tail) else 0.0])
    ends_y.append(["참값", float(np.median(gd[mg & (gs_ >= xl[1] - 1.5) & (gs_ <= xl[1])])) if (mg & (gs_ >= xl[1] - 1.5) & (gs_ <= xl[1])).any() else 0.0])
    ends_y.sort(key=lambda r: r[1])
    for k_ in range(1, len(ends_y)):
        if ends_y[k_][1] - ends_y[k_ - 1][1] < 0.22:
            ends_y[k_][1] = ends_y[k_ - 1][1] + 0.22
    for m, y in ends_y:
        ax.text(xl[1] + 0.012 * (xl[1] - xl[0]), y, m + (" (점)" if m == "참값" else " (점선)" if m == "학습 전 사전 정보" else ""),
                color=COL.get(m, "#4d4d4d"), fontsize=11, va="center")
    ax.set_xlim(xl[0], xl[1] + 0.16 * (xl[1] - xl[0])); ax.set_ylim(-2.0, 2.0)
    ax.set_xlabel(f"벽을 따라 (m), 높이 {z0:.1f} m의 수평 단면"); ax.set_ylabel("벽에서 바깥으로 (m)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(F["title"], fontsize=13.5, y=0.985)
    line = " · ".join(f"{m} {100 * vals[m]['recall']:.1f} %" for m in LINES if vals.get(m) and vals[m]["recall"] is not None)
    fig.text(0.5, 0.01, f"R1 · LoD2, 벽면 19(결측 패치 {len(mp)}) · 단면 폭 0.5 m · 이 면의 결측 재현율(0.2 m, {vals['본 방법']['rows']}행): {line}", ha="center", fontsize=10)
    fig.subplots_adjust(left=0.02, right=0.99, top=0.88, bottom=0.17)
    for e in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"V4_missing_R1_LoD2.{e}", dpi=140)
    plt.close(fig)
    vals["본 방법 씨앗 1"] = recall(site, prior, res_name("본 방법 씨앗 1", prior), mp)
    out = dict(key=KEY, title=F["title"], form="horizontal section (the request's fallback: the renders did not show the shape)", site=site, prior=prior, face=ext,
               section=dict(sec, across_axis="outward normal (+ = outside)"), xlim=xl, gt_points_in_band=int(mg.sum()), photo=dict(view=pv, crop_native=pbox),
               panels=rec, values=vals, render_version="V4_missing_R1_LoD2_render.png|pdf|json (v4_wall.py)", seconds=round(time.time() - t0, 1), made=now(), scientific_verdict=None)
    jdump(DOCS / "figures" / "V4_missing_R1_LoD2.json", out)
    log("done", out["seconds"])


if __name__ == "__main__":
    main()

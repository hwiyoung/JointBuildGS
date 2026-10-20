"""PHD-MAIN-VISCMP-v2 V3 (다듬기) and V5 (보존): one small photo (the photo figure's view, the section as one line) and one vertical
section 0.5 m wide (the photo figure's section): GT points (black dots) and the TSDF mesh of each method cut by the band's middle plane,
names written at the line ends (no legend), the height axis = GT median +- 0.3 m. Values = the median of 'result - GT' (the new distance
metric's signed per-row distance r_d x r_sign) over the place's GT rows, and the number of rows:
  V3  the 32,932 gentle-roof rows of B173 주변 ALS face 1 (FT/prep/figpos_fig1_rows.npz, as photo figure 4)
  V5  the GT rows of the 23 patches of the B0 ALS image-error cluster (r_patch in the cluster, as photo figure 5)
  python vs_sections.py V3|V5 -> /docs/figures/V3_refine_B173nb_ALS.* | V5_keep_B0_ALS.*   scientific_verdict: null"""
import sys
import time

import numpy as np
from matplotlib.collections import LineCollection

import vc_common  # noqa: F401
import pf_geo as G
import vc_fig as VF
import vc_render as RD
from vc_common import CFG, DOCS, FT, dist_file, jdump, jl, log, mesh_path, now, res_name

NAMES = {"V3": "V3_refine_B173nb_ALS", "V5": "V5_keep_B0_ALS"}


def rows_values(key, site, prior, P, res):
    df = dist_file(site, prior, res)
    if df is None:
        return None
    d = np.load(df)
    sg = d["r_d"].astype(np.float64) * np.where(d["r_sign"] == 0, 1, d["r_sign"])
    if key == "V3":
        rows = np.load(FT / "prep/figpos_fig1_rows.npz")["rows"]
        pos = np.searchsorted(d["r_idx"], rows)
        ok = (pos < len(d["r_idx"])) & (d["r_idx"][np.minimum(pos, len(d["r_idx"]) - 1)] == rows)
        v = sg[pos[ok]]
    else:
        v = sg[np.isin(d["r_patch"], np.asarray(P["cluster_patches"], int))]
    return dict(median_cm=float(100 * np.median(v)) if len(v) else None, rows=int(len(v)), dist=str(df))


def main(key):
    t0 = time.time()
    C = jl(CFG); P = C["places"][key]; F = C["figures"][key]
    site, prior = P["site"], P["prior"]
    sec = P["section"]; c = np.asarray(sec["centre_xy"], np.float64); a = np.asarray(sec["axis_xy"], np.float64); a /= np.linalg.norm(a)
    sr = sec["s_range_m"]
    ends = np.array([c + sr[0] * a, c + sr[1] * a])
    box = [float(ends[:, 0].min()), float(ends[:, 1].min()), float(ends[:, 0].max()), float(ends[:, 1].max())]
    Xg = VF.gt(site, box, margin=1.0)
    mg, sg_ = G.band(Xg, c, a, sr)
    gt_s, gt_z = sg_[mg], Xg[mg, 2]
    zmid = float(np.median(gt_z))
    segs, vals, rec = {}, {}, {}
    for m in F["lines"][1:]:
        res = res_name(m, prior)
        p = mesh_path(site, prior, res)
        if p is None:
            rec[m] = dict(result=res, status="결과 없음"); continue
        V, Fc, info = RD.load_mesh(p, box, margin=3.0)
        segs[m] = G.cut_vertical(V, Fc, c, a, sr)
        vals[m] = rows_values(key, site, prior, P, res)
        rec[m] = dict(result=res, status="ok", mesh=str(p), mesh_info=info, segments=int(len(segs[m])))
        log(key, m, res, vals[m])
    s1 = res_name("본 방법 씨앗 1", prior)
    vals["본 방법 씨앗 1"] = rows_values(key, site, prior, P, s1)
    # photo: the section as one line at the GT height
    view = P["photo"]["view"]
    pc = RD.Pinhole(view, (0, 0, 1400, 1013), 1)
    E3 = np.column_stack([ends, [zmid, zmid]])
    eu, ev, _ = pc.project(E3)
    du, dv = abs(eu[1] - eu[0]), abs(ev[1] - ev[0]); L = max(du, dv)
    cx_, cy_ = eu.mean(), ev.mean(); hw = 0.65 * L
    bx = [int(max(cx_ - hw, 0)), int(max(cy_ - hw, 0)), int(min(cx_ + hw, 1400)), int(min(cy_ + hw, 1013))]
    ph = VF.photo(view, bx)
    # draw
    plt = G.setup_plt()
    col = C["render"]["section_lines"]
    fig = plt.figure(figsize=(17, 5.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 4.2], wspace=0.13)
    ax0 = fig.add_subplot(gs[0, 0])
    ax0.imshow(ph, extent=(bx[0], bx[2], bx[3], bx[1])); ax0.plot(eu, ev, color="#ffd400", lw=2.2)
    ax0.set_xlim(bx[0], bx[2]); ax0.set_ylim(bx[3], bx[1]); ax0.set_xticks([]); ax0.set_yticks([]); ax0.set_title("사진", fontsize=12)
    ax0.text(0.5, -0.04, f"영상 {view}\n노란 선 = 단면 자리", transform=ax0.transAxes, ha="center", va="top", fontsize=9)
    ax = fig.add_subplot(gs[0, 1])
    # [그리는 법만 바꿈, V5 첫 그림 뒤] height above the GT profile: the 0.25 m-bin median GT height (>= 5 points) interpolated over gaps
    # <= 1 m, subtracted from every point and line vertex; the axis is GT +- 0.3 m in both V3 and V5 (V5's section climbs a steep slope)
    edges = np.arange(sr[0], sr[1] + 0.25, 0.25); bc = 0.5 * (edges[:-1] + edges[1:])
    bi = np.clip(np.digitize(gt_s, edges) - 1, 0, len(bc) - 1)
    gm = np.array([np.median(gt_z[bi == k]) if (bi == k).sum() >= 5 else np.nan for k in range(len(bc))])
    okb = np.isfinite(gm)

    def prof(sv):
        sv = np.asarray(sv, np.float64)
        g = np.interp(sv, bc[okb], gm[okb])
        near = np.min(np.abs(sv[:, None] - bc[okb][None, :]), 1) if okb.any() else np.full(len(sv), np.inf)
        g[near > 1.0] = np.nan
        return g
    dz_gt = gt_z - prof(gt_s)
    ax.plot(gt_s, dz_gt, ".", color="#4d4d4d", ms=1.0, alpha=0.35, zorder=2)   # [그리는 법만 바꿈, 첫 그림 뒤] the dense black GT hid the lines on it
    ax.axhline(0.0, color="#000000", lw=0.6, zorder=3)
    if key == "V5":
        cp = np.asarray(P["cluster_patches"], int)
        import p0_places as P0
        Rr = P0.region(site, prior)
        cc = Rr["centre"][cp][:, :2].astype(np.float64) - c
        ss_, dd_ = cc @ a, cc @ np.array([-a[1], a[0]])
        nb = np.abs(dd_) <= 1.0
        if nb.any():
            ax.axvspan(ss_[nb].min() - 0.125, ss_[nb].max() + 0.125, color="#ebebeb", zorder=0)
            ax.text(0.5 * (ss_[nb].min() + ss_[nb].max()), 0.285, "덩어리", ha="center", va="top", fontsize=10, color="#666666")
    lo, hi = -0.3, 0.3
    ends_y = []
    for m, sg in segs.items():
        pri = m == "학습 전 사전 정보"                         # [그리는 법만 바꿈, 둘째 그림 뒤] dashed on top: it lies exactly under 결합 here
        if len(sg):
            sg = sg.copy()
            for e in (0, 1):
                sg[:, e, 1] = sg[:, e, 1] - prof(sg[:, e, 0])
            sg = sg[np.isfinite(sg[:, :, 1]).all(1)]
        ax.add_collection(LineCollection(sg, colors=col[m], linewidths=2.2 if not pri else 1.6, linestyles="--" if pri else "-", zorder=5 if pri else 4))
        if len(sg):
            mid = sg.mean(1)
            tail = mid[mid[:, 0] >= sr[1] - 0.15 * (sr[1] - sr[0])]
            tail = tail[(tail[:, 1] >= lo) & (tail[:, 1] <= hi)]
            y = float(np.median(tail[:, 1])) if len(tail) else float(np.clip(np.median(mid[:, 1]), lo, hi))
        else:
            y = hi
        ends_y.append([m, y])
    ends_y.append(["참값", 0.0])
    ends_y.sort(key=lambda r: r[1])
    gap = 0.045
    for k_ in range(1, len(ends_y)):
        if ends_y[k_][1] - ends_y[k_ - 1][1] < gap:
            ends_y[k_][1] = ends_y[k_ - 1][1] + gap
    for m, y in ends_y:
        ax.text(sr[1] + 0.012 * (sr[1] - sr[0]), y, m + (" (옅은 점)" if m == "참값" else " (점선)" if m == "학습 전 사전 정보" else ""), color=col.get(m, "#000000") if m != "참값" else "#4d4d4d", fontsize=11, va="center")
    ax.set_xlim(sr[0], sr[1] + 0.13 * (sr[1] - sr[0])); ax.set_ylim(lo, hi)
    ax.set_xlabel("단면을 따라 (m)"); ax.set_ylabel("참값과의 높이 차 (m)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(F["title"], fontsize=13.5, y=0.985)
    order = ["학습 전 사전 정보", "2DGS", "GeoGS", "결합", "본 방법"]
    line = " · ".join(f"{m} {vals[m]['median_cm']:+.1f} cm ({vals[m]['rows']:,}행)" for m in order if vals.get(m) and vals[m]["median_cm"] is not None)
    place = "B173 주변 · 항공 LiDAR, 면 1 평평한 지붕" if key == "V3" else f"B0 · 항공 LiDAR, 영상이 틀린 덩어리({P['cluster_area_m2']:.2f} m², {len(P['cluster_patches'])}패치)"
    fig.text(0.5, 0.01, f"{place} · 단면 폭 0.5 m · 결과 − 참값 중앙값: {line}", ha="center", fontsize=10)
    fig.subplots_adjust(left=0.02, right=0.99, top=0.88, bottom=0.17)
    for ext in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"{NAMES[key]}.{ext}", dpi=140)
    plt.close(fig)
    out = dict(key=key, title=F["title"], site=site, prior=prior, section=sec, gt_points_in_band=int(len(gt_s)), gt_median_z=zmid, ylim=[lo, hi], height_axis='z - GT profile (0.25 m-bin median, gaps <= 1 m)',
               photo=dict(view=view, crop_native=bx, camera=pc.record()), panels=rec, values=vals, seconds=round(time.time() - t0, 1), made=now(), scientific_verdict=None)
    jdump(DOCS / "figures" / f"{NAMES[key]}.json", out)
    log("done", out["seconds"])


if __name__ == "__main__":
    main(sys.argv[1])

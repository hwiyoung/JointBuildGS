"""PHD-MAIN-VISCMP-v2 V1 (보정): R1 LoD2 stepped roof (the stage-3 reinforcement-1 piece, 2,621 patches) seen by the oblique training
camera of vp_places.py, every panel the same camera (focal x 4, 2 x 2 supersampled), grey headlight, faded to 30 % outside the piece's plan
squares (+0.25 m); the GT panel = the study's GT points as dark grey dots; one zoom box (the largest roof step, 3 m) on every panel and
enlarged in the lower row. Values = the median of the new distance metric's per-point distance (s_d) over the GT points of the piece.
  python v1_corr.py -> /docs/figures/V1_correction_R1_LoD2.png|pdf|json   scientific_verdict: null"""
import time

import numpy as np

import vc_common  # noqa: F401
import p0_places as P0
import pf_geo as G
import vc_fig as VF
import vc_render as RD
from vc_common import CFG, DOCS, dist_file, jdump, jl, log, mesh_path, now, res_name

KEY, SC = "V1", 4


def main():
    t0 = time.time()
    C = jl(CFG); P = C["places"][KEY]; F = C["figures"][KEY]
    site, prior = P["site"], P["prior"]
    U = P0.store(site, prior)
    piece = np.asarray(P["piece_patches"], int)
    Q = VF.quads(U, piece)
    view = P["photo"]["view"]
    box_n = VF.crop_box(view, Q, 0.10, margin_v=1.0)        # [그리는 법만 바꿈, 첫 그림 뒤] the piece is a thin band here; +100 % up and down shows the whole stepped roof
    cam_hi = RD.Pinhole(view, box_n, SC * VF.SS); cam = RD.Pinhole(view, box_n, SC)
    ol = VF.outline(cam, Q)
    inside = VF.plan_inside(Q, pad=0.25)
    xy = U["loc_center"][piece][:, :2]
    box_xy = [float(xy[:, 0].min()), float(xy[:, 1].min()), float(xy[:, 0].max()), float(xy[:, 1].max())]
    zc = np.asarray(P["zoom"]["centre"]); h = P["zoom"]["half_m"]
    zcorn = np.array([zc + np.array([a, b, c_]) for a in (-h, h) for b in (-h, h) for c_ in (-h, h)])
    zu, zv, _ = cam.project(zcorn)
    zb = [float(zu.min()), float(zv.min()), float(zu.max()), float(zv.max())]
    panels, rec, vals = {}, {}, {}
    for m in F["panels"]:
        if m == "사진":
            panels[m] = VF.photo(view, box_n); rec[m] = dict(view=view, crop_native=box_n); continue
        if m == "참값":
            Xg = VF.gt(site, box_xy, margin=12.0)
            panels[m], rec[m] = VF.render_gt(Xg, cam_hi, inside, radius=1); continue
        res = res_name(m, prior)
        p = mesh_path(site, prior, res)
        if p is None:
            rec[m] = dict(result=res, status="결과 없음"); continue
        panels[m], r_ = VF.render(p, box_xy, cam_hi, inside, margin=12.0)
        rec[m] = dict(result=res, status="ok", **r_)
        df = dist_file(site, prior, res)
        if df is not None:
            d = np.load(df)
            sel = np.isin(d["s_patch"], piece)
            vals[m] = dict(median_cm=float(100 * np.median(d["s_d"][sel])) if sel.any() else None, points=int(sel.sum()), dist=str(df))
        log(m, res, rec[m].get("hit_in_place"), vals.get(m))
    for nm in ("본 방법 씨앗 1",):
        res = res_name(nm, prior); df = dist_file(site, prior, res)
        if df is not None:
            d = np.load(df); sel = np.isin(d["s_patch"], piece)
            vals[nm] = dict(median_cm=float(100 * np.median(d["s_d"][sel])), points=int(sel.sum()), dist=str(df))
    # draw
    plt = G.setup_plt()
    from matplotlib.patches import Rectangle
    cols = F["panels"]; ncol = len(cols)
    aw = 3.0; ah = aw * cam.H / cam.W
    zh = aw * (zb[3] - zb[1]) / max(zb[2] - zb[0], 1)
    fig, axs = plt.subplots(2, ncol, figsize=(ncol * aw + 0.4, ah + zh + 2.4), gridspec_kw=dict(height_ratios=[ah, zh]))
    fig.subplots_adjust(left=0.01, right=0.99, top=0.86, bottom=0.10, wspace=0.03, hspace=0.30)
    for j, m in enumerate(cols):
        for i in range(2):
            ax = axs[i, j]; ax.set_xticks([]); ax.set_yticks([])
            if m not in panels:
                ax.text(0.5, 0.5, "결과 없음", transform=ax.transAxes, ha="center", va="center"); continue
            img = panels[m]
            if m == "사진":
                ax.imshow(img, extent=(0, cam.W, cam.H, 0), interpolation="bicubic")
                if i == 0:
                    ax.contour(ol.astype(float), levels=[0.5], colors=["#ffd400"], linewidths=1.6)
            else:
                ax.imshow(img, cmap="gray", vmin=0, vmax=1, interpolation="nearest" if i == 0 else "bilinear", extent=(0, cam.W, cam.H, 0))
            if i == 0:
                ax.set_xlim(0, cam.W); ax.set_ylim(cam.H, 0)
                ax.add_patch(Rectangle((zb[0], zb[1]), zb[2] - zb[0], zb[3] - zb[1], fill=False, ec="#000000", lw=1.2))
                ax.set_title(m, fontsize=12)
                v = vals.get(m)
                if v and v["median_cm"] is not None:
                    ax.text(0.5, -0.04, f"{v['median_cm']:.1f} cm ({v['points']:,}점)", transform=ax.transAxes, ha="center", va="top", fontsize=10)
            else:
                ax.set_xlim(zb[0], zb[2]); ax.set_ylim(zb[3], zb[1])
    fig.suptitle(F["title"], fontsize=14, y=0.975)
    fig.text(0.5, 0.02, f"R1 · LoD2, 3단계 보강 덩어리({len(piece):,}패치, {P['area_m2']} m²) · 영상 {view} · 칸 아래 = 이 자리 참값 점의 거리 중앙값(새 거리 지표) · "
             f"아래 줄 = 검은 상자(계단 높이 차 {P['zoom']['step_m']:.1f} m인 곳) 확대 · 자리 밖은 옅게", ha="center", fontsize=10)
    for ext in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"V1_correction_R1_LoD2.{ext}", dpi=140)
    plt.close(fig)
    out = dict(key=KEY, title=F["title"], site=site, prior=prior, piece_patches=int(len(piece)), camera=cam.record(), zoom_px=zb, panels=rec, values=vals,
               seconds=round(time.time() - t0, 1), made=now(), scientific_verdict=None)
    jdump(DOCS / "figures" / "V1_correction_R1_LoD2.json", out)
    log("done", out["seconds"])


if __name__ == "__main__":
    main()

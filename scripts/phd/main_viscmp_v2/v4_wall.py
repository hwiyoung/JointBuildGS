"""PHD-MAIN-VISCMP-v2 V4 (상속 결측, 고친 판): R1 LoD2 wall 19 seen by the training camera whose angle to the outward wall normal is
closest to 60 deg (vp_places.py), every render panel the same camera (focal x 4, 2 x 2 supersampled), grey headlight, faded to 30 % outside
the wall (+-1.5 m of the plane and inside the face's patch squares); the missing area (158 patches, closed into one piece) = one dashed line on
every panel; the photo panel = DJI_20241217101317_0011_D (request 3, photo figure 3's view) with the same outline. Values = the face's
missing recall (0.2 m): share of the c4-place GT rows of the face's missing patches with r_d <= 0.2 m (photo figure 3's rule).
  python v4_wall.py -> /docs/figures/V4_missing_R1_LoD2_render.png|pdf|json (the request fallback v4_section.py makes V4_missing_R1_LoD2.*)   scientific_verdict: null"""
import time

import numpy as np

import vc_common  # noqa: F401
import p0_places as P0
import pf_geo as G
import vc_fig as VF
import vc_render as RD
from vc_common import CFG, DOCS, dist_file, jdump, jl, log, mesh_path, now, res_name

KEY, SC, BIT_C4 = "V4", 4, 1 << 3


def recall(site, prior, res, mp):
    df = dist_file(site, prior, res)
    if df is None:
        return None
    d = np.load(df)
    m = ((d["r_place"] & BIT_C4) > 0) & np.isin(d["r_patch"], mp)
    return dict(recall=float((d["r_d"][m] <= 0.2).mean()) if m.any() else None, rows=int(m.sum()), dist=str(df))


def main():
    t0 = time.time()
    C = jl(CFG); P = C["places"][KEY]; F = C["figures"][KEY]
    site, prior, ext = P["site"], P["prior"], P["ext"]
    R = P0.region(site, prior); U = P0.store(site, prior)
    se = R["surf_ext"].astype(int); ev = R["in_eval"].astype(bool); code = R["code_ext_v3"].astype(int)
    face = np.nonzero(ev & (se == ext))[0]; mp = np.nonzero(ev & (se == ext) & np.isin(code, [4, 13]))[0]
    Qf, Qm = VF.quads(U, face), VF.quads(U, mp)
    view = P["view"]
    box_n = VF.crop_box(view, Qm, 1.0)
    cam_hi = RD.Pinhole(view, box_n, SC * VF.SS); cam = RD.Pinhole(view, box_n, SC)
    ol = VF.outline(cam, Qm)
    inside = VF.wall_inside(Qf, P["outward_normal"], half=1.5)
    xy = U["loc_center"][mp][:, :2]
    box_xy = [float(xy[:, 0].min()), float(xy[:, 1].min()), float(xy[:, 0].max()), float(xy[:, 1].max())]
    # photo panel (its own camera, the request's view)
    pv = P["photo"]
    pbox = VF.crop_box(pv, Qm, 1.0); pcam = RD.Pinhole(pv, pbox, SC); pol = VF.outline(pcam, Qm)
    panels, rec, vals = {}, {}, {}
    for m in sum(F["panels"], []):
        if m == "사진":
            panels[m] = VF.photo(pv, pbox); rec[m] = dict(view=pv, crop_native=pbox, camera=pcam.record()); continue
        if m == "참값":
            Xg = VF.gt(site, box_xy, margin=14.0)
            panels[m], rec[m] = VF.render_gt(Xg, cam_hi, inside, radius=1); continue
        res = res_name(m, prior)
        p = mesh_path(site, prior, res)
        if p is None:
            rec[m] = dict(result=res, status="결과 없음"); log("no result", m); continue
        panels[m], r_ = VF.render(p, box_xy, cam_hi, inside, margin=14.0)
        rec[m] = dict(result=res, status="ok", **r_)
        vals[m] = recall(site, prior, res, mp)
        log(m, res, r_["hit_in_place"], vals[m])
    vals["본 방법 씨앗 1"] = recall(site, prior, res_name("본 방법 씨앗 1", prior), mp)
    # draw
    plt = G.setup_plt()
    rows = F["panels"]
    aw = 4.0; ah = aw * cam.H / cam.W
    fig, axs = plt.subplots(2, 4, figsize=(4 * aw + 0.4, 2 * (ah + 0.9) + 1.2))
    fig.subplots_adjust(left=0.01, right=0.99, top=0.90, bottom=0.07, wspace=0.03, hspace=0.25)
    for i, row in enumerate(rows):
        for j, m in enumerate(row):
            ax = axs[i, j]; ax.set_xticks([]); ax.set_yticks([]); ax.set_title(m, fontsize=12)
            if m not in panels:
                ax.text(0.5, 0.5, "결과 없음", transform=ax.transAxes, ha="center", va="center"); continue
            if m == "사진":
                ax.imshow(panels[m], extent=(0, pcam.W, pcam.H, 0), interpolation="bicubic")
                ax.contour(pol.astype(float), levels=[0.5], colors=["#ffd400"], linewidths=1.6)
                ax.set_xlim(0, pcam.W); ax.set_ylim(pcam.H, 0)
                ax.text(0.5, -0.03, f"영상 {pv}", transform=ax.transAxes, ha="center", va="top", fontsize=9)
                continue
            ax.imshow(panels[m], cmap="gray", vmin=0, vmax=1, interpolation="nearest", extent=(0, cam.W, cam.H, 0))
            ax.contour(ol.astype(float), levels=[0.5], colors=["#000000"], linewidths=1.2, linestyles="--")
            ax.set_xlim(0, cam.W); ax.set_ylim(cam.H, 0)
            v = vals.get(m)
            if v and v["recall"] is not None:
                ax.text(0.5, -0.03, f"결측 재현율 {100 * v['recall']:.1f} % ({v['rows']}행)", transform=ax.transAxes, ha="center", va="top", fontsize=10)
    fig.suptitle(F["title"], fontsize=14, y=0.975)
    fig.text(0.5, 0.012, f"R1 · LoD2, 벽면 19(결측 패치 {len(mp)}) · 렌더 칸 = 영상 {view}의 카메라(벽 법선과 {P['candidates'][0]['view_angle_deg']:.0f}°) · "
             "점선(사진은 노란 선) = 결측 영역 · 자리 밖은 옅게 · 칸 아래 = 이 면의 결측 재현율(0.2 m)", ha="center", fontsize=10)
    for e in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"V4_missing_R1_LoD2_render.{e}", dpi=140)
    plt.close(fig)
    out = dict(key=KEY, title=F["title"], site=site, prior=prior, face=ext, missing=int(len(mp)), camera=cam.record(), panels=rec, values=vals,
               seconds=round(time.time() - t0, 1), made=now(), scientific_verdict=None)
    jdump(DOCS / "figures" / "V4_missing_R1_LoD2_render.json", out)
    log("done", out["seconds"])


if __name__ == "__main__":
    main()

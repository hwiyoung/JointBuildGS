"""PHD-MAIN-VISCMP-v3 V1, V3, V5, V4 (request 1, 4): one camera per figure (config), panels = the left panel, the inputs, the methods.
  top '결과 면'          the panel's mesh ray-cast (2 x 2 supersampled), one grey, a headlight, faded to 30 % outside the place
  V1 '확대'              the zoom box of the top row (the left panel: the GT points)
  bottom '참값과의 거리'  the crop's scene GT points, coloured by d_g to the panel's mesh (bwr, +- range, clipped), grey where no surface is near
                         (rays along +- the oriented GT normal within 2 x range); the place = a dashed outline; the number = median |d_g| of
                         the place's region rows (cm)
Stored d_g: the distance task's / fix-test task's distance files. The image-depth panel (V1, V3, V5): the figure camera's training MVS depth
map as a pixel-grid mesh, d_g computed here with the distance task's code (vd_dist) [이 발주에서 냄].
  python f3_fig.py V1|V3|V5|V4   -> /docs/figures/<file>.png (300 dpi) | .pdf | .json   scientific_verdict: null"""
import sys
import time

import numpy as np
from matplotlib import cm, colors

import vc_common  # noqa: F401
import p0_places as P0
import pf_geo as G
import vc_fig as VF
import vc_render as RD
import vd_dist as VD
from vc_common import CFG, DOCS, FT, S0, jdump, jl, log, mesh_path, now, res_name


def setup(key, C):
    P, F = C["places"][key], C["figures"][key]
    site = P.get("site", F.get("site")); prior = P.get("prior", F.get("prior"))
    U = P0.store(site, prior); R = P0.region(site, prior)
    info = {}
    if key == "V1":
        place = np.asarray(P["piece_patches"], int); view = P["photo"]["view"]; box = P["crop_native"]; sc = P["scale"]
    elif key == "V3":
        place = np.asarray(P["patches"], int); view = P["view"]; box = VF.crop_box(view, VF.quads(U, place), 0.05); sc = None
    elif key == "V5":
        place = np.asarray(P["patches"], int); view = P["view"]; box = VF.crop_box(view, VF.quads(U, place), 1.0); sc = None
    else:
        se = R["surf_ext"].astype(int); ev = R["in_eval"].astype(bool); code = R["code_ext_v3"].astype(int)
        place = np.nonzero(ev & (se == P["ext"]) & np.isin(code, [4, 13]))[0]; view = None; box = None; sc = None
        info["face"] = np.nonzero(ev & (se == P["ext"]))[0]
    if key != "V4":
        if sc is None:
            sc = float(np.clip(900.0 / max(box[2] - box[0], 1), 2, 12)); info["scale_rule"] = "900 px across the crop (2-12)"
        cam_hi, cam = RD.Pinhole(view, box, sc * VF.SS), RD.Pinhole(view, box, sc)
    else:
        cd = P["camera"]
        cam_hi = RD.Ortho(cd["centre"], cd["right"], cd["up"], cd["toward_viewer"], cd["s_range"], cd["h_range"], cd["pixel"] / VF.SS)
        cam = RD.Ortho(cd["centre"], cd["right"], cd["up"], cd["toward_viewer"], cd["s_range"], cd["h_range"], cd["pixel"])
    return P, F, site, prior, U, R, place, view, box, cam_hi, cam, info


def main(key):
    t0 = time.time()
    C = jl(CFG); D = C["draw"]
    P, F, site, prior, U, R, place, view, box, cam_hi, cam, info = setup(key, C)
    rng = F["range_m"]
    Qp = VF.quads(U, place)
    if key == "V4":
        Qf = VF.quads(U, info["face"]); inside = VF.wall_inside(Qf, P["outward_normal"], half=1.5)
        xy = U["loc_center"][info["face"]][:, :2]
    else:
        inside = VF.plan_inside(Qp, pad=0.25); xy = U["loc_center"][place][:, :2]
    box_xy = [float(xy[:, 0].min()), float(xy[:, 1].min()), float(xy[:, 0].max()), float(xy[:, 1].max())]
    ol = VF.outline(cam, Qp)
    case = VD.Case(site, prior)
    # GT scene points of the crop (in the image, in front)
    cand = case.scene_in_box(box_xy, margin=25.0)
    u_, v_, z_ = cam.project(case.gt.Gb[cand])
    sidx = cand[(z_ > 0) & (u_ >= 0) & (u_ < cam.W) & (v_ >= 0) & (v_ < cam.H)]
    if key == "V4":
        d4 = case.gt.Gb[sidx] - np.asarray(P["camera"]["centre"])
        sidx = sidx[np.abs(d4 @ np.asarray(P["camera"]["toward_viewer"])) <= 3.0]     # the wall slab (+-3 m): the wall's own points
    Xs = case.gt.Gb[sidx]; Ns = case.oriented_normals(sidx)
    rows_place = case.rows_of(place)
    if key == "V3":
        rf = np.load(FT / "prep/figpos_fig1_rows.npz")["rows"]
        pos = np.searchsorted(case.u.rows_idx, rf); rows_place = pos[(pos < len(case.u.rows_idx)) & (case.u.rows_idx[np.minimum(pos, len(case.u.rows_idx) - 1)] == rf)]
    s_place = np.isin(case.own[sidx], place)
    norm = colors.Normalize(-rng, rng, clip=True); cmap = cm.get_cmap(D["cmap"])
    grey = np.array(colors.to_rgb(D["no_surface_grey"]))
    panels = F["inputs"] + F["methods"]
    top, bot, rec = {}, {}, {}
    depth_info = None
    for m in panels:
        if m == "영상 깊이":
            dep = np.load(S0 / "fork_inputs/s61" / site / "maps/mvs" / f"{view}.npy")
            V, Fc, depth_info = VD.depth_mesh(view, dep)
            keepv = (V[:, 0] >= box_xy[0] - 25) & (V[:, 0] <= box_xy[2] + 25) & (V[:, 1] >= box_xy[1] - 25) & (V[:, 1] <= box_xy[3] + 25)
            Fc = Fc[keepv[Fc].all(1)]
            dsc = case.dg_scene(V, Fc, sidx); drw = case.dg_rows(V, Fc, rows_place)
            src = dict(result="training MVS depth map", view=view, mesh=depth_info, mark="이 발주에서 냄")
        else:
            res = res_name(m, prior)
            p = mesh_path(site, prior, res)
            st = case.stored(res)
            if p is None or st is None:
                rec[m] = dict(result=res, status="결과 없음"); log("no result", m, res); continue
            V, Fc, minfo = RD.load_mesh(p, box_xy, margin=25.0)
            dsc = st["scene"][sidx]; drw = st["rows"][rows_place]
            src = dict(result=res, mesh=str(p), mesh_info=minfo, dist=st["file"])
        t, n, Dd = RD.raycast(V, Fc, cam_hi)
        g, hit = RD.shade(t, n, Dd)
        X = RD.hit_points(t, cam_hi)
        ins = inside(X.reshape(-1, 3)).reshape(hit.shape)
        top[m] = RD.down(RD.fade(g, hit, ins), VF.SS)
        nos, has_n = VD.no_surface(V, Fc, Xs, Ns, 2 * rng)
        nos = np.where(has_n, nos, np.abs(dsc) > 2 * rng)
        rgb = cmap(norm(np.nan_to_num(dsc, nan=0.0)))[:, :3]
        rgb[nos | ~np.isfinite(dsc)] = grey
        bot[m], npts = RD.splat_rgb(cam, Xs, rgb, radius=D["point_radius_px"])
        val = float(np.median(np.abs(drw))) if len(drw) else None
        rec[m] = dict(src, status="ok", value_cm=None if val is None else 100 * val, signed_cm=None if val is None else 100 * float(np.median(drw)),
                      rows=int(len(drw)), scene_place_median_cm=float(100 * np.median(np.abs(dsc[s_place]))) if s_place.any() else None,
                      scene_place_points=int(s_place.sum()), scene_points=int(len(sidx)), grey_share=float(nos.mean()), grey_share_place=float(nos[s_place].mean()) if s_place.any() else None)
        if key == "V4" and m != "영상 깊이":
            stf = case.stored(res_name(m, prior))
            c4 = ((stf["r_place"] & (1 << 3)) > 0) & np.isin(stf["r_patch"], place)
            rec[m]["recall_0_2"] = float((np.abs(stf["rows"][c4]) <= 0.2).mean()); rec[m]["recall_rows"] = int(c4.sum())
        log(key, m, rec[m]["value_cm"], rec[m]["signed_cm"], rec[m]["grey_share"])
    s1 = case.stored(res_name("본 방법 씨앗 1", prior))
    if s1 is not None:
        drw = s1["rows"][rows_place]
        rec["본 방법 씨앗 1"] = dict(result=res_name("본 방법 씨앗 1", prior), value_cm=100 * float(np.median(np.abs(drw))), signed_cm=100 * float(np.median(drw)), rows=int(len(drw)))
        if key == "V4":
            c4 = ((s1["r_place"] & (1 << 3)) > 0) & np.isin(s1["r_patch"], place)
            rec["본 방법 씨앗 1"]["recall_0_2"] = float((np.abs(s1["rows"][c4]) <= 0.2).mean())
    # V5 title by the request-3 rule
    title = F["title"]; tinfo = None
    if key == "V5":
        base = {m: rec[m]["value_cm"] for m in ("2DGS", "GeoGS", "결합", "CDGS") if rec.get(m, {}).get("value_cm") is not None}
        bm = min(base, key=base.get); d0, d1 = rec["본 방법"]["value_cm"], rec["본 방법 씨앗 1"]["value_cm"]
        spread = 2.8 * abs(d0 - d1) / np.sqrt(2); diff = d0 - base[bm]
        sg = rec["본 방법"]["signed_cm"]; roof = int(np.bincount(R["kind"][place].astype(int)).argmax()) == 1
        word = ("위에 떴고" if sg >= 0 else "아래로 꺼졌고") if roof else ("바깥으로 나왔고" if sg >= 0 else "안으로 들어갔고")
        same_side = np.sign(sg) == np.sign(rec["영상 깊이"]["signed_cm"])
        if diff > spread and same_side:
            title = f"영상이 틀린 이 자리에서 본 방법은 영상 깊이를 따라 {abs(sg):.0f} cm {word}, {bm}은 참값에 더 가까웠다"
        elif diff > spread:
            title = f"영상이 틀린 이 자리에서 본 방법은 {abs(sg):.0f} cm 벗어났고, {bm}은 참값에 더 가까웠다"
        elif abs(diff) <= spread:
            title = f"영상이 틀린 이 자리에서 본 방법은 {bm}만큼 참값에 가까웠다"
        else:
            title = "영상이 틀린 이 자리에서 본 방법이 기존 방법보다 참값에 가까웠다"
        tinfo = dict(closest_baseline=bm, closest_cm=base[bm], proposed_cm=d0, seed1_cm=d1, spread_cm=spread, diff_cm=diff, proposed_signed_cm=sg,
                     image_signed_cm=rec["영상 깊이"]["signed_cm"], same_side=bool(same_side), roof=roof)
    # zoom (V1)
    zb = None
    if "확대" in F["rows"]:
        zc = np.asarray(P["zoom"]["centre"]); h = P["zoom"]["half_m"]
        zu, zv, _ = cam.project(np.array([zc + np.array([a, b, c_]) for a in (-h, h) for b in (-h, h) for c_ in (-h, h)]))
        zb = [float(zu.min()), float(zv.min()), float(zu.max()), float(zv.max())]
    # left panel images
    if key == "V4":
        pv = P["photo"]; pbox = VF.crop_box(pv, Qp, 1.0); pcam = RD.Pinhole(pv, pbox, 4); photo = VF.photo(pv, pbox); pol = VF.outline(pcam, Qp)
    else:
        pv, pbox, pcam, photo, pol = view, box, cam, VF.photo(view, box), ol
    plain, _ = RD.splat_rgb(cam, Xs, np.tile([D["gt_plain_grey"]] * 3, (len(Xs), 1)), radius=D["point_radius_px"])
    # ---- draw
    plt = G.setup_plt()
    from matplotlib.patches import Rectangle
    plt.rcParams.update({"font.size": D["font_size"]})
    cols = ["left"] + panels; nc = len(cols); rows = F["rows"]; nr = len(rows)
    pw = D["panel_width_in"]; ph = pw * cam.H / cam.W
    zh = pw * (zb[3] - zb[1]) / max(zb[2] - zb[0], 1) if zb else 0
    hr = [ph if r != "확대" else zh for r in rows]
    fig = plt.figure(figsize=(nc * pw + 1.6, sum(hr) + 0.55 * nr + 1.3))
    gs = fig.add_gridspec(nr, nc + 1, width_ratios=[1] * nc + [0.08], height_ratios=hr, wspace=0.04, hspace=0.18, left=0.045, right=0.975, top=0.88, bottom=0.07)
    for i, rname in enumerate(rows):
        for j, m in enumerate(cols):
            ax = fig.add_subplot(gs[i, j]); ax.set_xticks([]); ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_linewidth(0.4)
            if i == 0:
                ax.set_title({"left": "사진"}.get(m, m), fontsize=D["font_size"] + 1)
            if j == 0:
                ax.set_ylabel(rname, fontsize=D["font_size"] + 1)
            if m == "left":
                if rname == "결과 면":
                    ax.imshow(photo, extent=(0, pcam.W, pcam.H, 0), interpolation="bicubic"); ax.contour(pol.astype(float), levels=[0.5], colors=["#ffd400"], linewidths=1.0)
                    ax.set_xlim(0, pcam.W); ax.set_ylim(pcam.H, 0)
                else:
                    ax.imshow(plain, extent=(0, cam.W, cam.H, 0), interpolation="nearest"); ax.contour(ol.astype(float), levels=[0.5], colors=["#000000"], linewidths=0.6, linestyles="--")
                    ax.set_xlim(0, cam.W) if rname != "확대" else ax.set_xlim(zb[0], zb[2]); ax.set_ylim(cam.H, 0) if rname != "확대" else ax.set_ylim(zb[3], zb[1])
                    if rname == "참값과의 거리":
                        ax.set_title("참값", fontsize=D["font_size"], pad=2)
                continue
            if m not in top:
                ax.text(0.5, 0.5, "결과 없음", transform=ax.transAxes, ha="center", va="center"); continue
            if rname in ("결과 면", "확대"):
                ax.imshow(top[m], cmap="gray", vmin=0, vmax=1, interpolation="nearest", extent=(0, cam.W, cam.H, 0))
                if rname == "결과 면":
                    ax.set_xlim(0, cam.W); ax.set_ylim(cam.H, 0)
                    if zb:
                        ax.add_patch(Rectangle((zb[0], zb[1]), zb[2] - zb[0], zb[3] - zb[1], fill=False, ec="#000000", lw=0.6))
                    if key == "V4":
                        ax.contour(ol.astype(float), levels=[0.5], colors=["#000000"], linewidths=0.6, linestyles="--")
                else:
                    ax.set_xlim(zb[0], zb[2]); ax.set_ylim(zb[3], zb[1])
            else:
                ax.imshow(bot[m], extent=(0, cam.W, cam.H, 0), interpolation="nearest")
                ax.contour(ol.astype(float), levels=[0.5], colors=["#000000"], linewidths=0.6, linestyles="--")
                ax.set_xlim(0, cam.W); ax.set_ylim(cam.H, 0)
                v = rec[m].get("value_cm")
                ax.text(0.5, -0.03, "—" if v is None else f"{v:.1f} cm", transform=ax.transAxes, ha="center", va="top", fontsize=D["font_size"] + 1)
    # group headers and the separator
    x_in0 = gs[0, 1].get_position(fig).x0; x_in1 = gs[0, len(F["inputs"])].get_position(fig).x1
    x_m0 = gs[0, len(F["inputs"]) + 1].get_position(fig).x0; x_m1 = gs[0, nc - 1].get_position(fig).x1
    ytop = gs[0, 1].get_position(fig).y1 + 0.045
    fig.text(0.5 * (x_in0 + x_in1), ytop, "입력", ha="center", fontsize=D["font_size"] + 2)
    fig.text(0.5 * (x_m0 + x_m1), ytop, "결과", ha="center", fontsize=D["font_size"] + 2)
    xs = 0.5 * (x_in1 + x_m0); ybot = gs[nr - 1, 1].get_position(fig).y0
    fig.add_artist(plt.Line2D([xs, xs], [ybot, ytop + 0.01], color="#666666", lw=0.6, transform=fig.transFigure))
    if rng is not None:
        cax = fig.add_subplot(gs[nr - 1, nc])
        cb = fig.colorbar(cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax, extend="both")
        cb.set_ticks([-rng, 0, rng]); cb.ax.tick_params(labelsize=D["font_size"])
        cax.text(0.5, 1.08, D["cbar_top"], transform=cax.transAxes, ha="center", va="bottom", fontsize=D["font_size"])
        cax.text(0.5, -0.08, D["cbar_bottom"] + "\n" + D["cbar_note"], transform=cax.transAxes, ha="center", va="top", fontsize=D["font_size"] - 1)
    fig.suptitle(title, fontsize=D["title_size"], y=0.975)
    nrows = rec[F["methods"][-1]]["rows"] if F["methods"][-1] in rec else 0
    foot = f"자리 참값 행 {nrows:,} · 칠한 참값 점 {len(sidx):,} · 칸 아래 = 자리 참값 행의 거리(|d_g| 중앙값) · " + D["cdgs_note"]
    if F.get("foot"):
        foot = F["foot"] + " · " + foot
    fig.text(0.5, 0.012, foot, ha="center", fontsize=D["font_size"])
    for e in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"{F['file']}.{e}", dpi=D["dpi"])
    plt.close(fig)
    out = dict(key=key, title=title, title_rule=tinfo, site=site, prior=prior, place_patches=int(len(place)), place_rows=int(len(rows_place)), camera=cam.record(),
               left_photo=dict(view=pv, crop_native=pbox), range_m=rng, depth_mesh=depth_info, panels=rec, zoom_px=zb, seconds=round(time.time() - t0, 1), made=now(),
               scientific_verdict=None)
    jdump(DOCS / "figures" / f"{F['file']}.json", out)
    log("done", out["seconds"], title)


if __name__ == "__main__":
    main(sys.argv[1])

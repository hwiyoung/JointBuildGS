"""PHD-MAIN-VISCMP-v4 일 가 V1, V3, V5, V4, V6 (request 6.2-6.3, 덧붙임 1 V6). Two rows:
  입력  자리 photo [+ 확대], 참값, 학습 전 사전 정보, 영상 깊이 (V1, V3, V5, V6)
  결과  2DGS, GeoGS, 결합, CDGS, 본 방법 [, 결측 지키기 (V4)]
one perspective camera for every render panel (prep/places.json: V1 = the v3 training camera and crop; else the virtual camera of the
config's camera rule), the meshes cut to the place's plan box + the rule's margin. Two plates:
  판가  the panel's surface; per pixel the signed distance from the visible surface point to the nearest GT point (sign = (X - G) . n_G,
        n_G = the GT point's oriented normal, vd_dist.Case.oriented_normals; + = above / outside), bwr +- range, times the v3 headlight
        (SHADE); surface in GT-excluded cells or outside the metric's GT cells = light grey hatching; no surface = the blue-grey background
  판나  v3: the GT points coloured by d_g to the panel's surface (stored distance files; the image-depth mesh: vd_dist), grey = no surface
        near (rays along +- the oriented normal within 2 x range); hatching where the prior's surface lies in GT-excluded cells
Values (json, and two lines under each panel): 완전성 = median |d_g| of the place's region rows (the v3 panel value); 정확도 = median d_r
of the result points whose nearest prior patch is a place patch (the distance files' q_d, q_patch; the image-depth mesh: the same
result_sample and nearest-patch rule on the cut mesh [이 발주에서 냄]). V6: 유리 / 둘레 결측 completeness. A blind copy of each plate (no
title, foot line, values) goes to /vc/work for the first-viewer check.
  python f4_fig.py V1|V3|V5|V4|V6 [--replot]   scientific_verdict: null"""
import pickle
import sys
import time

import numpy as np
from matplotlib import cm, colors
from scipy.spatial import cKDTree

import vc_common  # noqa: F401
import p0_places as P0
import pf_geo as G
import vc_fig as VF
import vc_render as RD
import vd_dist as VD
from a3_split import excl_lookup
from dm_common import result_sample
from vc_common import CFG, DOCS, FT, S0, VC, jdump, jl, log, mesh_path, now, res_name

FILES = {"V1": "V1_correction_R1_LoD2", "V3": "V3_refine_B173nb_ALS", "V5": "V5_keep_B173nb_ALS", "V4": "V4_missing_R1_LoD2", "V6": "V6_limit_B173nb_ALS"}
PLACES = CFG.parent / "places_v4.json"   # the second lock (prep/places.json copied; sha in PF/config_lock.json places_lock)
PW = 420          # shown render width (px; ~ the 300 dpi panel width), rendered 2 x 2 supersampled  [첫 그림 뒤: 700 -> 420, hatching moire]
V1_MARGIN = 25.0  # V1: v3's mesh / GT margin around the place (the v3 camera and crop)


def cameras(key, P, U, place):
    """(cam_hi, cam, info). V1: the v3 training camera over the v3 crop (focal scaled to PW across the crop). Else the rule's virtual
    look-at camera; the fit box = the place's patch corners + margin_m; the panel aspect = the fit box's projected aspect (0.4-1.3)."""
    c = P["camera"]
    if c["kind"] == "v3 camera":
        box = c["crop_native"]; sc = PW / (box[2] - box[0])
        return RD.Pinhole(c["view"], box, sc * VF.SS), RD.Pinhole(c["view"], box, sc), dict(rule="v3 camera and crop", scale=sc)
    X = VF.quads(U, place).reshape(-1, 3); m = float(c["margin_m"])
    # [그리는 법만 바꿈, 첫 그림 뒤 10-21 16:40] the margin is added in plan only (the rule: the place + margin fills 70 % of the panel width);
    # the first run also added it to the height, which made the place small in V3, V5, V6
    lo, hi = X.min(0) - np.array([m, m, 0.0]), X.max(0) + np.array([m, m, 0.0])
    fit = np.array([[a, b, z] for a in (lo[0], hi[0]) for b in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    mg = 1.0 / float(c["fill"]) - 1.0
    probe = RD.LookAt(c["eye"], c["target"], c["up"], fit, [PW, PW], margin=mg)
    u, v, _ = probe.project(fit)
    asp = float(np.clip((v.max() - v.min()) / max(u.max() - u.min(), 1e-6), 0.4, 1.3))
    H = int(round(PW * asp))
    return (RD.LookAt(c["eye"], c["target"], c["up"], fit, [PW * VF.SS, H * VF.SS], margin=mg), RD.LookAt(c["eye"], c["target"], c["up"], fit, [PW, H], margin=mg),
            dict(rule="virtual look-at; fit = the place's patch corners + margin_m in plan (z = the place's own range), 1 / fill - 1 margin; aspect from the fit's projection (0.4-1.3)", aspect=asp))


SHADE = (0.6, 0.4)     # 판가 colour x (a + b |n . d|) [그리는 법만 바꿈, 첫 그림 뒤 10-21 16:45: v3's 0.12 + 0.78 made near-zero (white) roofs dark grey;
#                        16:57: 0.45 + 0.55 -> 0.6 + 0.4, first viewers could not tell the shaded white from the background]
BG_GA = "#93a8c2"      # 판가 'no surface' [결과를 본 뒤 바꿈 10-21 16:57, 첫 보는 이 점검 1·2회: the config's #dfe6ee was read as the white of '참값과 같음']


def compose(raw, cmap, norm, bg):
    """판가 panel from the stored per-pixel record (hi-res): signed distance sd, |n . d| ndl, hit, hatch mask -> the shown rgb."""
    sd, ndl, hit, hm = raw["sd"], raw["ndl"], raw["hit"], raw["hatch"]
    rgb = np.tile(bg, sd.shape + (1,)).astype(np.float64)
    if hit.any():
        rgb[hit] = cmap(norm(sd[hit]))[:, :3] * (SHADE[0] + SHADE[1] * ndl[hit])[:, None]
    img = hatch(rgb, hm, period=6 * VF.SS, width=2 * VF.SS)
    return np.stack([RD.down(img[..., k], VF.SS) for k in range(3)], -1)


FADE, FADE_PX, LINE_PX = 1.0, 4, 3    # [그리는 법만 바꿈, 첫 보는 이 점검 1회 뒤 10-21 16:55] the dashed line drawn 3 px outside the place; the fade outside
#                                       the place (35 % contrast, 16:55) taken out again at 16:57 (FADE = 1: none): first viewers read the faded colours as '참값과 같음'


def disk(r):
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return (xx ** 2 + yy ** 2) <= r * r


def fade_out(img, inside, base):
    out = img.copy()
    out[~inside] = base + FADE * (img[~inside] - base)
    return out


def hatch(img, mask, base=0.94, line=0.5, period=6, width=2):
    out = img.copy()
    yy, xx = np.nonzero(mask)
    out[yy, xx] = base
    s = ((yy + xx) % period) < width
    out[yy[s], xx[s]] = line
    return out


def fit_crop(box, aspect, keep=None, W=1400, H=1013):
    """a photo crop with the panel aspect (H / W): grown around the crop's centre; when the image is too small for that, the longer side is
    trimmed instead [그리는 법만 바꿈, 첫 그림 뒤: the photo panel shrank], the window shifted to hold `keep` (the place's pixel box) and the image."""
    x0, y0, x1, y1 = (float(b) for b in box); w, h = x1 - x0, y1 - y0
    if h / w < aspect:
        h = w * aspect
    else:
        w = h / aspect
    if w > W:
        w = W; h = w * aspect
    if h > H:
        h = H; w = h / aspect
    cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    if keep is not None:
        cx = min(max(cx, keep[2] - w / 2), keep[0] + w / 2); cy = min(max(cy, keep[3] - h / 2), keep[1] + h / 2)
    a = min(max(cx - w / 2, 0), W - w); b = min(max(cy - h / 2, 0), H - h)
    return [a, b, a + w, b + h]


def main(key):
    t0 = time.time()
    C = jl(CFG); W = C["work_ga"]; P = jl(PLACES)[key]
    site, prior = P["site"], P["prior"]; rng = float(W["ranges_m"][key])
    U = P0.store(site, prior)
    place = np.asarray(P["place"], int); Qp = VF.quads(U, place)
    cam_hi, cam, cinfo = cameras(key, P, U, place)
    xy = U["loc_center"][place][:, :2]
    mg = V1_MARGIN if key == "V1" else float(P["camera"]["margin_m"])
    box_xy = [float(xy[:, 0].min() - mg), float(xy[:, 1].min() - mg), float(xy[:, 0].max() + mg), float(xy[:, 1].max() + mg)]
    case = VD.Case(site, prior)
    exf, _ = excl_lookup(site)
    gtree = cKDTree(case.gt.Gb); ptree = cKDTree(case.u.centre)
    cand = case.scene_in_box(box_xy, 0.0)
    u_, v_, z_ = cam.project(case.gt.Gb[cand])
    sidx = cand[(z_ > 0) & (u_ >= 0) & (u_ < cam.W) & (v_ >= 0) & (v_ < cam.H)]
    Xs = case.gt.Gb[sidx]; Ns = case.oriented_normals(sidx)
    rows_place = case.rows_of(place)
    if key == "V3":   # v3: the fix-test figure-1 rows of face 1
        rf = np.load(FT / "prep/figpos_fig1_rows.npz")["rows"]
        pos = np.searchsorted(case.u.rows_idx, rf); rows_place = pos[(pos < len(case.u.rows_idx)) & (case.u.rows_idx[np.minimum(pos, len(case.u.rows_idx) - 1)] == rf)]
    subs = {"유리": np.asarray(P["glass"], int), "둘레 결측": np.asarray(P["ring_missing"], int)} if key == "V6" else {}
    sub_rows = {nm: case.rows_of(pl) for nm, pl in subs.items()}
    norm = colors.Normalize(-rng, rng, clip=True); cmap = cm.get_cmap(W["cmap"])
    bg = np.array(colors.to_rgb(W["background"])); grey = np.array(colors.to_rgb("#bdbdbd"))
    panels = ["학습 전 사전 정보"] + (["영상 깊이"] if key != "V4" else []) + list(W["panels_bottom"]) + (["결측 지키기"] if key == "V4" else [])
    ga, na, rec, ex_prior = {}, {}, {}, None
    for m in panels:
        if m == "영상 깊이":
            dv = P["depth_view"]["view"]
            dep = np.load(S0 / "fork_inputs/s61" / site / "maps/mvs" / f"{dv}.npy")
            V, F, dinfo = VD.depth_mesh(dv, dep)
            kv = (V[:, 0] >= box_xy[0]) & (V[:, 0] <= box_xy[2]) & (V[:, 1] >= box_xy[1]) & (V[:, 1] <= box_xy[3])
            F = F[kv[F].all(1)]
            d_scene = case.dg_scene(V, F, sidx); d_rows = case.dg_rows(V, F, rows_place)
            smp = result_sample(V, F, case.gt)
            q_d = gtree.query(smp, workers=-1)[0] if len(smp) else np.zeros(0)
            q_patch = ptree.query(smp, workers=-1)[1] if len(smp) else np.zeros(0, int)
            dsub = {nm: case.dg_rows(V, F, rr) for nm, rr in sub_rows.items()}
            src = dict(result="training MVS depth map", view=dv, mesh=dict(dinfo, cut="place plan box + margin", triangles_in_box=int(len(F))), mark="이 발주에서 냄")
        else:
            res = res_name(m, prior); p = mesh_path(site, prior, res); st = case.stored(res)
            if p is None or st is None:
                rec[m] = dict(result=res, status="결과 없음"); log("no result", m, res); continue
            V, F, minfo = RD.load_mesh(p, box_xy, margin=0.0)
            kv = (V[:, 0] >= box_xy[0]) & (V[:, 0] <= box_xy[2]) & (V[:, 1] >= box_xy[1]) & (V[:, 1] <= box_xy[3])
            F = F[kv[F].all(1)]
            d_scene = st["scene"][sidx]; d_rows = st["rows"][rows_place]
            z = np.load(st["file"]); q_d, q_patch = z["q_d"].astype(np.float64), z["q_patch"].astype(np.int64)
            dsub = {nm: st["rows"][rr] for nm, rr in sub_rows.items()}
            src = dict(result=res, mesh=str(p), mesh_info=dict(minfo, triangles_in_box=int(len(F))), dist=st["file"])
        # 판가: the surface coloured by the signed distance to the nearest GT point x the headlight
        t, n, D = RD.raycast(V, F, cam_hi)
        g, hit = RD.shade(t, n, D)
        X = RD.hit_points(t, cam_hi).reshape(-1, 3); hv = hit.reshape(-1)
        sd = np.full(len(X), np.nan)
        if hv.any():
            dd, ii = gtree.query(X[hv], workers=-1)
            Ng = case.oriented_normals(ii)
            s = np.sign(((X[hv] - case.gt.Gb[ii]) * np.nan_to_num(Ng)).sum(1)); s[s == 0] = 1.0
            sd[hv] = dd * s
        ex = np.zeros(len(X), bool); ex[hv] = exf(X[hv])
        # [그리는 법만 바꿈, 첫 그림(V1) 뒤 10-21 16:22] surfaces outside the distance metric's GT cells (SiteGT.in_cells, the building-surface
        # cells: the metric counts no result point there) were coloured as far from the GT (ground, facades below the cells): hatched as '참값 없음' too
        out_cells = np.zeros(len(X), bool); out_cells[hv] = ~case.gt.in_cells(X[hv])
        hw = (cam_hi.H, cam_hi.W)
        ga[m] = dict(sd=sd.reshape(hw).astype(np.float32), ndl=np.abs((n * D).sum(-1)).astype(np.float32), hit=hit, hatch=(ex | out_cells).reshape(hw))
        if m == "학습 전 사전 정보":
            ex_prior = ex.reshape(hw)
        # 판나: the GT points coloured by d_g to this surface (v3)
        nos, has_n = VD.no_surface(V, F, Xs, Ns, 2 * rng)
        nos = np.where(has_n, nos, np.abs(d_scene) > 2 * rng)
        c2 = cmap(norm(np.nan_to_num(d_scene)))[:, :3]; c2[nos | ~np.isfinite(d_scene)] = grey
        na[m], _ = RD.splat_rgb(cam, Xs, c2, radius=1)
        sel = np.isin(q_patch, place)
        e = dict(src, status="ok", completeness_cm=100 * float(np.median(np.abs(d_rows))) if len(d_rows) else None,
                 signed_cm=100 * float(np.median(d_rows)) if len(d_rows) else None, rows=int(len(d_rows)),
                 accuracy_cm=100 * float(np.median(q_d[sel])) if sel.any() else None, accuracy_points=int(sel.sum()),
                 surface_pixels=int(hv.sum()), surface_pixel_median_signed_cm=100 * float(np.nanmedian(sd)) if hv.any() else None,
                 surface_in_excluded_share=float(ex.sum() / max(hv.sum(), 1)), surface_outside_gt_cells_share=float((out_cells & ~ex).sum() / max(hv.sum(), 1)), grey_share_plate_na=float(nos.mean()) if len(nos) else None)
        for nm, pl in subs.items():
            dr_ = dsub[nm]; s2 = np.isin(q_patch, pl)
            e[nm] = dict(completeness_cm=100 * float(np.median(np.abs(dr_))) if len(dr_) else None, signed_cm=100 * float(np.median(dr_)) if len(dr_) else None,
                         rows=int(len(dr_)), accuracy_cm=100 * float(np.median(q_d[s2])) if s2.any() else None, accuracy_points=int(s2.sum()))
        if key == "V4":
            c4 = ((st["r_place"] & (1 << 3)) > 0) & np.isin(st["r_patch"], place)
            e["recall_0_2"] = float((np.abs(st["rows"][c4]) <= 0.2).mean()) if c4.any() else None; e["recall_rows"] = int(c4.sum())
        rec[m] = e
        log(key, m, e["completeness_cm"], e["accuracy_cm"], {nm: e[nm]["signed_cm"] for nm in subs})
    r1 = res_name("본 방법 씨앗 1", prior); s1 = case.stored(r1)
    if s1 is not None:
        z1 = np.load(s1["file"]); sel = np.isin(z1["q_patch"], place); d1 = s1["rows"][rows_place]
        rec["본 방법 씨앗 1"] = dict(result=r1, completeness_cm=100 * float(np.median(np.abs(d1))), signed_cm=100 * float(np.median(d1)), rows=int(len(d1)),
                                 accuracy_cm=100 * float(np.median(z1["q_d"][sel])) if sel.any() else None, accuracy_points=int(sel.sum()))
        for nm, rr in sub_rows.items():
            dr_ = s1["rows"][rr]; rec["본 방법 씨앗 1"][nm] = dict(completeness_cm=100 * float(np.median(np.abs(dr_))), signed_cm=100 * float(np.median(dr_)), rows=int(len(dr_)))
        if key == "V4":
            c4 = ((s1["r_place"] & (1 << 3)) > 0) & np.isin(s1["r_patch"], place)
            rec["본 방법 씨앗 1"]["recall_0_2"] = float((np.abs(s1["rows"][c4]) <= 0.2).mean())
    # GT panel (판가: dark grey points on the background; 판나: v3 plain grey on white), hatching = the prior's surface in excluded cells
    emask = (RD.down(ex_prior.astype(float), VF.SS) > 0.5) if ex_prior is not None else np.zeros((cam.H, cam.W), bool)
    gt_ga, _ = RD.splat_rgb(cam, Xs, np.tile([0.25, 0.25, 0.25], (len(Xs), 1)), radius=1, bg=tuple(bg))
    gt_na, _ = RD.splat_rgb(cam, Xs, np.tile([0.25, 0.25, 0.25], (len(Xs), 1)), radius=1)
    na["참값"] = gt_na
    ol = VF.outline(cam, Qp) if not subs else None
    subol = {nm: VF.outline(cam, VF.quads(U, pl)) for nm, pl in subs.items()}
    pv = P["photo"]; pfull = RD.Pinhole(pv, (0, 0, 1400, 1013), 1)
    qo = VF.outline(pfull, Qp, close_px=4)
    asp = cam.H / cam.W
    yy, xx = np.nonzero(qo); kb = [int(xx.min()), int(yy.min()), int(xx.max()), int(yy.max())] if len(yy) else None
    # V4: the request names the whole image (letterboxed in the panel); else the crop with the panel aspect
    wide = [0.0, 0.0, 1400.0, 1013.0] if key == "V4" else fit_crop(P["crops"]["wide"], asp, keep=kb)
    zoom = fit_crop(P["crops"]["zoom"], asp, keep=kb) if (P["crops"].get("zoom") and key != "V6") else None
    photo_full = VF.photo(pv, [0, 0, 1400, 1013])
    title, tinfo = W["titles"].get(key), None
    if key == "V6":     # 덧붙임 1 V6: the title from the numbers of the place
        sg = rec["본 방법"]["유리"]["signed_cm"]; rs = rec["본 방법"]["둘레 결측"]["signed_cm"]; ims = rec["영상 깊이"]["유리"]["signed_cm"]
        same = bool(np.sign(sg) == np.sign(ims))
        title = (f"맞는 자료를 판단할 수 없는 이 유리에서 본 방법은 {'영상 깊이를 따라 ' if same else ''}{abs(sg):.0f} cm {'아래로 꺼졌고' if sg < 0 else '위로 떴고'}, "
                 f"둘레 결측의 면은 참값보다 {abs(rs):.0f} cm {'위에 떴다' if rs >= 0 else '아래로 꺼졌다'}")
        tinfo = dict(rule="덧붙임 1 V6", proposed_glass_signed_cm=sg, image_glass_signed_cm=ims, proposed_ring_signed_cm=rs, same_side=same,
                     check_image_glass_cm=-41.7, check_ring_render_depth_m=[0.88, 0.87, 0.90], check_ring_note="photofig fig2: render depth - GT of seed 0, seed 1, 결측 지키기")
    ctx = dict(ga=ga, na=na, emask=emask, gt_ga=gt_ga, bg=bg, rec=rec, ol=ol, subol=subol, photo_full=photo_full, qo=qo, wide=wide, zoom=zoom, cam_wh=(cam.W, cam.H), title=title, tinfo=tinfo,
               camera=dict(cam.record(), **cinfo), panels=panels, t0=t0, n_rows=int(len(rows_place)), n_pts=int(len(sidx)), site=site, prior=prior, pv=pv,
               box_xy=box_xy, P={k: v for k, v in P.items() if k not in ("place", "glass", "ring_missing")})
    (VC / "work").mkdir(exist_ok=True)
    with open(VC / "work" / f"f4_{key}.pkl", "wb") as fh:
        pickle.dump(ctx, fh)
    draw(key, ctx)


def draw(key, ctx, blind=False):
    C = jl(CFG); W = C["work_ga"]; rng = float(W["ranges_m"][key])
    plt = G.setup_plt()
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch, Rectangle
    fs = 6.5
    plt.rcParams.update({"font.size": fs, "hatch.linewidth": 0.6})
    rec, (Wc, Hc) = ctx["rec"], ctx["cam_wh"]
    top = ["자리"] + (["확대"] if ctx["zoom"] else []) + ["참값", "학습 전 사전 정보"] + (["영상 깊이"] if "영상 깊이" in ctx["panels"] else [])
    bot = [p for p in ctx["panels"] if p not in ("학습 전 사전 정보", "영상 깊이")]
    ncol = max(len(top), len(bot))
    IN = 2.54; fw = 16 / IN; lab = 0.13; cbw = 0.8
    cw = (fw - lab - cbw) / ncol; ch = cw * Hc / Wc
    head = 0.08 if blind else 0.42; valh = 0.0 if blind else 0.2; gap = 0.2 + valh; foot = 0.12 if blind else 0.24
    fh = head + 0.14 + ch + gap + 0.14 + ch + valh + foot + 0.05
    out_size = dict(width_cm=round(fw * IN, 2), height_cm=round(fh * IN, 2), render_panel_cm=round(cw * IN, 2))
    cmap = cm.get_cmap(W["cmap"]); norm = colors.Normalize(-rng, rng, clip=True); bg0 = ctx["bg"]; bg = np.array(colors.to_rgb(BG_GA)); em = ctx["emask"]
    GA = {k: compose(v, cmap, norm, bg) for k, v in ctx["ga"].items()}
    gfree = np.abs(ctx["gt_ga"] - bg0).sum(-1) < 1e-6
    g2 = ctx["gt_ga"].copy(); g2[gfree] = bg
    GA["참값"] = hatch(g2, em & gfree)
    NA = {k: hatch(v, em & (v.sum(-1) > 2.999)) for k, v in ctx["na"].items()}
    from scipy import ndimage
    pm = ctx["ol"] if ctx["ol"] is not None else np.any(np.stack(list(ctx["subol"].values())), 0)
    inside = ndimage.binary_dilation(pm, structure=disk(FADE_PX))
    GA = {k: fade_out(v, inside, bg) for k, v in GA.items()}
    NA = {k: fade_out(v, inside, np.ones(3)) for k, v in NA.items()}
    line_ol = ndimage.binary_dilation(ctx["ol"], structure=disk(LINE_PX)) if ctx["ol"] is not None else None
    line_sub = {nm: ndimage.binary_dilation(so, structure=disk(LINE_PX)) for nm, so in ctx["subol"].items()}
    for plate in ("판가", "판나"):
        imgs = GA if plate == "판가" else NA
        fig = plt.figure(figsize=(fw, fh))
        ys = [fh - head - 0.14 - ch, fh - head - 0.14 - ch - gap - 0.14 - ch]
        for r, row in enumerate((top, bot)):
            for j, m in enumerate(row):
                ax = fig.add_axes([(lab + j * cw + 0.012) / fw, ys[r] / fh, (cw - 0.024) / fw, ch / fh])
                ax.set_xticks([]); ax.set_yticks([])
                for sp in ax.spines.values():
                    sp.set_linewidth(0.4)
                ax.set_title(m, fontsize=fs + 0.5, pad=2, weight="bold" if m == "본 방법" else "normal")
                if m in ("자리", "확대"):
                    b = ctx["wide"] if m == "자리" else ctx["zoom"]
                    ax.imshow(ctx["photo_full"], interpolation="bilinear")
                    ax.contour(ctx["qo"].astype(float), levels=[0.5], colors=["#ffd400"], linewidths=0.9)
                    if m == "자리" and ctx["zoom"]:
                        z = ctx["zoom"]; ax.add_patch(Rectangle((z[0], z[1]), z[2] - z[0], z[3] - z[1], fill=False, ec="#ffd400", lw=0.8))
                    ax.set_xlim(b[0], b[2]); ax.set_ylim(b[3], b[1])
                    continue
                if m not in imgs:
                    ax.text(0.5, 0.5, "결과 없음", transform=ax.transAxes, ha="center", va="center"); continue
                ax.imshow(imgs[m], interpolation="nearest")
                if line_ol is not None:
                    ax.contour(line_ol.astype(float), levels=[0.5], colors=["#000000"], linewidths=0.7, linestyles=[(0, (4, 2))])
                for nm, so in line_sub.items():
                    ax.contour(so.astype(float), levels=[0.5], colors=["#000000"], linewidths=0.7, linestyles=[(0, (4, 2)) if nm == "유리" else (0, (1, 1.2))])
                    if m == "참값":
                        from scipy import ndimage
                        lb, nlb = ndimage.label(so)
                        if nlb:
                            big = 1 + int(np.argmax(ndimage.sum(so, lb, range(1, nlb + 1))))
                            yy, xx = np.nonzero(lb == big)
                            up = nm == "유리"
                            ax.annotate(nm, xy=(xx.mean(), yy.min() if up else yy.max()), xytext=(xx.mean(), (yy.min() - 0.12 * Hc) if up else (yy.max() + 0.12 * Hc)),
                                        fontsize=fs - 0.5, ha="center", va="bottom" if up else "top", arrowprops=dict(arrowstyle="-", lw=0.5, color="#000000"),
                                        bbox=dict(fc="w", ec="none", alpha=0.8, pad=0.4))
                ax.set_xlim(-0.5, Wc - 0.5); ax.set_ylim(Hc - 0.5, -0.5)
                e = rec.get(m, {})
                if not blind and e.get("status") == "ok":
                    if ctx["subol"]:
                        t = "\n".join(f"{nm} {e[nm]['completeness_cm']:.1f} cm" for nm in ctx["subol"])
                    else:
                        t = f"완전성 {e['completeness_cm']:.1f} cm" + (f"\n정확도 {e['accuracy_cm']:.1f} cm" if e.get("accuracy_cm") is not None else "")
                    ax.text(0.5, -0.025, t, transform=ax.transAxes, ha="center", va="top", fontsize=fs)
        ysep = (ys[0] - gap * 0.5 - 0.02) / fh
        fig.add_artist(Line2D([0.005, 1 - (cbw + 0.02) / fw], [ysep, ysep], color="#888888", lw=0.5))
        fig.text(0.06 / fw, (ys[0] + ch / 2) / fh, "입력", rotation=90, ha="center", va="center", fontsize=fs + 1)
        fig.text(0.06 / fw, (ys[1] + ch / 2) / fh, "결과", rotation=90, ha="center", va="center", fontsize=fs + 1)
        # colour bar and the legend under it
        cx0 = (fw - cbw + 0.3) / fw; cb_lo = ys[1] + 0.72; cb_hi = ys[0] + ch - 0.3
        cax = fig.add_axes([cx0, cb_lo / fh, 0.08 / fw, (cb_hi - cb_lo) / fh])
        cb = fig.colorbar(cm.ScalarMappable(norm=colors.Normalize(-rng, rng), cmap=cm.get_cmap(W["cmap"])), cax=cax, extend="both")
        cb.set_ticks([-rng, 0, rng]); cb.set_ticklabels([f"−{rng:g} m", "0\n" + W["cbar"][1].replace(" ", "\n", 1), f"+{rng:g} m"])
        cb.ax.tick_params(labelsize=fs - 1, length=1.5, pad=1)
        cax.text(0.5, 1.09, W["cbar"][0].replace("·", "·\n"), transform=cax.transAxes, ha="center", va="bottom", fontsize=fs - 1)
        cax.text(0.5, -0.1, W["cbar"][2].replace("·", "·\n"), transform=cax.transAxes, ha="center", va="top", fontsize=fs - 1)   # [마지막 점검 뒤, 글자 겹침만: -0.05 -> -0.1]
        hl = ([Line2D([], [], color="#000000", lw=0.7, ls=(0, (4, 2)), label="점선: 볼 곳")] if not ctx["subol"] else
              [Line2D([], [], color="#000000", lw=0.7, ls=(0, (4, 2)), label="점선: 유리"), Line2D([], [], color="#000000", lw=0.7, ls=(0, (1, 1.2)), label="짧은 점선: 둘레 결측")])
        hl += [Patch(fc="#f0f0f0", ec="#555555", hatch="/////", label="빗금: 참값 없음")]
        hl += [Patch(fc=BG_GA, ec="#777777", label="청회색: 결과 면 없음")] if plate == "판가" else [Patch(fc="#bdbdbd", ec="#777777", label="회색: 가까이에 면 없음")]
        fig.legend(handles=hl, loc="lower left", bbox_to_anchor=((fw - cbw - 0.04) / fw, (ys[1] - valh) / fh), fontsize=fs - 1.7, frameon=False, handlelength=1.0,
                   handleheight=1.0, labelspacing=0.6, borderaxespad=0.1)
        if not blind:
            fig.text(0.5, 1 - 0.07 / fh, ctx["title"], ha="center", va="top", fontsize=fs + 1.3, weight="bold", wrap=True)
            ft = W["cdgs_note"] + (" · 점선 안은 영상 깊이가 없는 곳(결측)" if key == "V4" else "")
            fig.text(0.5, 0.06 / fh, ft, ha="center", va="bottom", fontsize=fs - 0.5)
            (DOCS / "figures" / plate).mkdir(parents=True, exist_ok=True)
            for ext in ("png", "pdf"):
                fig.savefig(DOCS / "figures" / plate / f"{FILES[key]}.{ext}", dpi=300)
        else:
            fig.savefig(VC / "work" / f"blind_{key}_{plate}.png", dpi=300)
        plt.close(fig)
    if not blind:
        out = dict(task="PHD-MAIN-VISCMP-v4", work="일 가", key=key, title=ctx["title"], title_rule=ctx["tinfo"], site=ctx["site"], prior=ctx["prior"],
                   camera=ctx["camera"], render_box_xy=ctx["box_xy"], photo=dict(view=ctx["pv"], wide_shown=ctx["wide"], zoom_shown=ctx["zoom"], places=ctx["P"]),
                   panels=rec, place_rows=ctx["n_rows"], gt_points_drawn=ctx["n_pts"], range_m=rng, size=out_size,
                   drawing=dict(plate_ga=W["plate_ga"], plate_na=W["plate_na"], light=f"판가 colour x ({SHADE[0]} + {SHADE[1]} |n . d|) (headlight)",
                                hatch="판가: the panel's own surface in excluded cells or outside the metric's GT cells (SiteGT.in_cells); 판나 and 참값: where the prior's surface lies in excluded cells",
                                fade=f"none (FADE {FADE}); the dashed line {LINE_PX} px outside the place's projected patch squares", background_plate_ga=BG_GA),
                   seconds=round(time.time() - ctx["t0"], 1), made=now(), scientific_verdict=None)
        for plate in ("판가", "판나"):
            jdump(DOCS / "figures" / plate / f"{FILES[key]}.json", dict(out, plate=plate))
        draw(key, ctx, blind=True)
        log("done", out["seconds"], out["size"], ctx["title"])


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "--replot":
        with open(VC / "work" / f"f4_{sys.argv[1]}.pkl", "rb") as fh:
            draw(sys.argv[1], pickle.load(fh))
    else:
        main(sys.argv[1])

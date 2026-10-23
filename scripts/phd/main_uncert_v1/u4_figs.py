"""PHD-MAIN-UNCERT-v1 일 3~4 figures (jointbuildgs:dev, CPU): maps of the per-patch values seen from above (orthographic, north up,
0.1 m pixels, the highest patch wins; scripts/phd/main_axes71_v2/ax_map.top_labels) and in the two oblique views of the two-axis task
(ax_map.camera / oblique_labels: 45 deg from vertical, azimuths 225 and 45 deg), and the place figures E (zoom maps + a section).

  python u4_figs.py <R> <A|Aob|B|C|D|E|...> [site or place ...]   -> /docs/figures/R<R>/<name>.png|pdf|json

Colours (config figures): u 0-50 cm viridis, > 50 cm = the 50 cm colour with black dots every 4 pixels, no value = light grey hatching;
MVS weight share: 0 orange (prior leads) - 0.5 near white - 1 blue (MVS leads), no value grey. Places (5.2) are outlined in black with a
short name. The numbers under a figure are the values of that figure's area (named). scientific_verdict: null."""
import sys

import numpy as np
from matplotlib.colors import LinearSegmentedColormap, Normalize
from scipy.ndimage import binary_dilation

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
sys.path.insert(0, "/repo/scripts/phd/main_axes71_v2")
import ax_map as AM  # noqa: E402
import u3_lib as L  # noqa: E402
import u_core as C  # noqa: E402
import uc_common as U  # noqa: E402

FC = U.CFG["figures"]
TITLES = FC["titles"]
plt = AM.setup_plt()
VIR = plt.get_cmap(FC["u_cmap"])
WCM = LinearSegmentedColormap.from_list("w", ["#d95f02", "#f7f7f7", "#1b6fa8"])
NOV_BG, NOV_LN = np.array([0.949, 0.949, 0.949]), np.array([0.722, 0.722, 0.722])
EXCL = AM.rgb("#e8dcc0")
UMAX = FC["u_range_cm"][1] / 100.0
PANEL = ["(가)", "(나)", "(다)", "(라)"]
SHORT = {"glass_strip": "유리 띠", "glass_dome": "유리 둥근 지붕", "flat_roof": "평평한 지붕", "b173_wing": "날개", "r1_step_roof": "계단 지붕"}


def colours(val, kind):
    v = np.asarray(val, np.float64)
    out = np.zeros((len(v), 3))
    ok = np.isfinite(v)
    if kind == "u":
        out[ok] = VIR(np.clip(v[ok] / UMAX, 0, 1))[:, :3]
    elif kind == "w":
        out[ok] = WCM(np.clip(v[ok], 0, 1))[:, :3]
    elif kind == "bool":
        out[ok] = np.where(v[ok, None] > 0.5, AM.rgb("#c62f26"), AM.rgb("#d9d9d9"))
    return out, ok


def paint(lab, rgb, ok, over=None, excl=None, kind="u"):
    H, W = lab.shape
    img = np.ones((H, W, 3))
    pix = lab >= 0
    L_ = np.where(pix, lab, 0)
    img[pix] = rgb[L_[pix]]
    hm = AM.hatch_mask(H, W)
    nv = pix & ~ok[L_]
    if kind == "w":
        img[nv] = AM.rgb("#9a9a9a")
    else:
        img[nv] = NOV_BG
        img[nv & hm] = NOV_LN
    if excl is not None:
        ex = pix & excl[L_]
        img[ex] = EXCL
    if over is not None:
        yy, xx = np.mgrid[0:H, 0:W]
        dots = (yy % 4 == 0) & (xx % 4 == 0)
        img[pix & over[L_] & dots] = 0.0
    return img


def outline(img, lab, sel_local, name, ax=None, texts=None):
    pm = np.isin(lab, sel_local)
    if not pm.any():
        return
    b = binary_dilation(pm, iterations=2) & ~pm
    img[b] = 0.0
    if texts is not None:
        yy, xx = np.nonzero(pm)
        texts.append((float(xx.mean()), float(yy.min()) - 4, name))


def top(site, prior, idx, lo, hi, px=0.1):
    k = 5 if px >= 0.1 else 9
    P, lab = AM.patch_points(site, prior, idx, k=k)
    loc = np.repeat(np.arange(len(idx)), k * k)
    img, _ = AM.top_labels(P, loc, lo, hi, px)
    return img


def oblique(site, prior, idx, cam):
    P, lab = AM.patch_points(site, prior, idx, k=9)
    loc = np.repeat(np.arange(len(idx)), 81)
    img, _ = AM.oblique_labels(cam, P, loc)
    return img


def places_in(site, prior):
    """[(local mask over patches of the set, short name)] of the places on this site and prior."""
    arr = np.load(U.WORK / "places.npz")
    pl = U.jl(U.WORK / "places.json")["places"]
    out = []
    for k in arr.files:
        name, pr = k.split("__")
        info = pl.get(name) or pl.get(k) or {}
        if pr != prior or info.get("site") != site or not len(arr[k]):
            continue
        short = SHORT.get(name) or ("고른 · 보정" if name.endswith("s_corr") else "고른 · 보존" if name.endswith("s_keep") else name)
        out.append((arr[k], short))
    return out


def eval_box(site):
    lo, hi = None, None
    for p in U.PRIORS:
        z = U.patches(site, p)
        c = z["centre"][z["in_eval"]]
        lo = c.min(0) if lo is None else np.minimum(lo, c.min(0))
        hi = c.max(0) if hi is None else np.maximum(hi, c.max(0))
    return lo - 1.0, hi + 1.0


def figure(panels, title, footer, kind, path, js, stack=None, cbar_label=None):
    """panels: [(img, label)] of equal size; one colour bar; the title; one footer line. All panels are cropped to the same box around
    the drawn pixels (the union over the panels, 12 pixels margin), so the panels stay comparable."""
    occ = np.zeros(panels[0][0].shape[:2], bool)
    for img, _, _ in panels:
        occ |= (img < 0.995).any(-1)
    if occ.any():
        yy, xx = np.nonzero(occ)
        y0, y1 = max(int(yy.min()) - 12, 0), min(int(yy.max()) + 13, occ.shape[0])
        x0, x1 = max(int(xx.min()) - 12, 0), min(int(xx.max()) + 13, occ.shape[1])
        panels = [(img[y0:y1, x0:x1], lab_, [(x - x0, y - y0, t) for (x, y, t) in (texts or [])]) for img, lab_, texts in panels]
        js = dict(js, crop_px=[x0, y0, x1, y1])
    H, W = panels[0][0].shape[:2]
    vertical = (W > 1.3 * H) if stack is None else stack == "v"
    n = len(panels)
    fw, top_in, foot_in, lab_in = 7.4, 0.42, 0.42, 0.2
    if vertical:
        pw = fw * 0.86
        ph = pw * H / W
        fh = top_in + n * (ph + lab_in) + foot_in
        fig = plt.figure(figsize=(fw, fh))
        axs = []
        for i in range(n):
            y0 = fh - top_in - (i + 1) * (ph + lab_in) + 0.02
            axs.append(fig.add_axes([0.02, y0 / fh, pw / fw, ph / fh]))
        cax = fig.add_axes([0.02 + pw / fw + 0.02, (foot_in + 0.3) / fh, 0.015, (fh - top_in - foot_in - 0.6) / fh])
    else:
        gap = 0.06
        pw = (fw - 0.2 - gap * (n - 1)) / n
        ph = pw * H / W
        cb_in = 0.55
        fh = top_in + lab_in + ph + cb_in + foot_in
        fig = plt.figure(figsize=(fw, fh))
        axs = [fig.add_axes([(0.1 + i * (pw + gap)) / fw, (foot_in + cb_in) / fh, pw / fw, ph / fh]) for i in range(n)]
        cax = fig.add_axes([0.25, (foot_in + 0.28) / fh, 0.5, 0.09 / fh])
    for ax, (img, lab_, texts) in zip(axs, panels):
        ax.imshow(img, interpolation="nearest")
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_linewidth(0.4)
        ax.set_title(lab_, fontsize=7, loc="left", pad=2)
        for (x, y, t) in texts or []:
            x = min(max(x, 0.06 * W), 0.94 * W); y = min(max(y, 0.04 * H), 0.96 * H)
            ax.text(x, y, t, fontsize=5.5, ha="center", va="bottom", color="k",
                    bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.8))
    fig.suptitle(title, fontsize=8.5, y=1 - 0.08 / fh, va="top")
    if kind not in ("u", "w"):
        cax.set_visible(False)
    if kind in ("u", "w"):
        sm = plt.cm.ScalarMappable(cmap=VIR if kind == "u" else WCM, norm=Normalize(0, 50 if kind == "u" else 1))
        cb = fig.colorbar(sm, cax=cax, orientation="vertical" if vertical else "horizontal")
        cb.ax.tick_params(labelsize=6)
        cb.set_label(cbar_label or ("불확실도 (cm). 50 넘음 = 검은 점 무늬, 빗금 = 값 없음, 흰색 = 패치 없음, 검은 테두리 = 자리" if kind == "u"
                                    else "MVS 무게 비율 (0 사전 정보 쪽, 1 MVS 쪽). 회색 = 둘 다 값 없음, 흰색 = 패치 없음, 검은 테두리 = 자리"), fontsize=6)
    fig.text(0.01, 0.04 / fh, footer, fontsize=5.5, ha="left", va="bottom", wrap=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix(".png"), dpi=FC["dpi"])
    fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)
    U.jdump(path.with_suffix(".json"), dict(js, title=title, footer=footer, made=U.now(), config_sha256=U.sha256(U.CFGP), scientific_verdict=None))


def pct(x):
    return f"{100 * x:.1f} %"


def cm(x):
    return "결과 없음" if x is None or not np.isfinite(x) else f"{100 * x:.1f} cm"


# ------------------------------------------------------------------------------------------------ A, A-oblique, C, D
def maps_site(S, site, which, out, views=("top",)):
    lo, hi = eval_box(site)
    for view in views:
        cams = {}
        if view != "top":
            cams = {p: AM.camera(lo, hi, float(view)) for p in U.PRIORS}
        panels, js, foot = [], dict(site=site, R=S.R, view=view, panels=[]), []
        for k, (prior, data, field, label) in enumerate(which):
            z = S.get(site, prior)
            idx = np.nonzero(L.ev(z))[0]
            if data == "lod2":
                val = np.full(len(idx), U.D["lod2_u_m"])
            elif data.startswith("R"):
                S2 = L.Store(float(data[1:]))
                z2 = S2.get(site, prior)
                val = L.val(z2, field[0], field[1])[idx]
            else:
                val = L.val(z, data, field)[idx]
            rgb, ok = colours(val, "u")
            lab = top(site, prior, idx, lo[:2], hi[:2]) if view == "top" else oblique(site, prior, idx, cams[prior])
            img = paint(lab, rgb, ok, over=ok & (val > UMAX))
            texts = []
            if view == "top":
                for pm, nm in places_in(site, prior):
                    sel = np.nonzero(np.isin(idx, pm))[0]
                    outline(img, lab, sel, nm, texts=texts)
            panels.append((img, f"{PANEL[k]} {label}", texts))
            v = val[ok]
            js["panels"].append(dict(label=label, prior=prior, data=data, patches=int(len(idx)), area_m2=float(z["area"][idx].sum()),
                                     with_value=int(ok.sum()), u_med_cm=100 * float(np.median(v)) if len(v) else None,
                                     over_50cm_share=float(np.mean(v > UMAX)) if len(v) else None))
            foot.append(f"{PANEL[k]} u 중앙값 {cm(np.median(v) if len(v) else None)}, 값 있음 {pct(ok.mean())}, 50 cm 넘음 {pct(np.mean(v > UMAX) if len(v) else 0)}")
        yield view, panels, js, "지역 전체(평가 범위): " + "; ".join(foot)


def fig_A(S, site, out, oblique_views=False):
    which = [("LoD2", "mvs_a", "u", "MVS (LoD2 패치)"), ("ALS", "als", "u", "항공 LiDAR (항공 LiDAR 패치)"), ("LoD2", "lod2", "u", "LoD2 (20 cm로 둠)")]
    views = ("225", "45") if oblique_views else ("top",)
    for view, panels, js, foot in maps_site(S, site, which, out, views):
        name = f"A_{site}" if view == "top" else f"A_oblique_{site}_az{view}"
        t = TITLES["A"] if view == "top" else TITLES["A_oblique"]
        figure(panels, f"{t} — {U.SITE_KO[site]}" + ("" if view == "top" else f", 비스듬히(방위 {view}°)"), foot, "u", out / name, js)


def fig_C(S, site, out):
    which = [("LoD2", "mvs_a", "a", "어긋남 (MVS, LoD2 패치)"), ("LoD2", "mvs_a", "s", "흩어짐 (MVS, LoD2 패치)")]
    for view, panels, js, foot in maps_site(S, site, which, out):
        figure(panels, f"{TITLES['C']} — {U.SITE_KO[site]}", foot.replace("u 중앙값", "중앙값"), "u", out / f"C_{site}", js, cbar_label="cm. 50 넘음 = 검은 점 무늬, 빗금 = 값 없음, 흰색 = 패치 없음, 검은 테두리 = 자리")


def fig_D(S, site, out):
    for prior, data, lab in (("LoD2", "mvs_a", "MVS (LoD2 패치)"), ("ALS", "als", "항공 LiDAR (항공 LiDAR 패치)")):
        which = [(prior, f"R{r}", (data, "u"), f"{lab}, 고리 {r} m") for r in U.D["ring_radii_m"]]
        for view, panels, js, foot in maps_site(S, site, which, out):
            figure(panels, f"{TITLES['D']} — {U.SITE_KO[site]}, {lab}", foot, "u", out / f"D_{site}_{prior}", js)


# ------------------------------------------------------------------------------------------------ B
def fig_B(S, site, out):
    lo, hi = eval_box(site)
    panels, js, foot = [], dict(site=site, R=S.R, panels=[]), []
    for k, (prior, label) in enumerate((("ALS", "MVS와 항공 LiDAR (항공 LiDAR 패치)"), ("LoD2", "MVS와 LoD2 (LoD2 패치)"))):
        z = S.get(site, prior)
        idx = np.nonzero(L.ev(z))[0]
        w = z["w_a"][idx]
        rgb, ok = colours(w, "w")
        lab = top(site, prior, idx, lo[:2], hi[:2])
        img = paint(lab, rgb, ok, kind="w")
        texts = []
        for pm, nm in places_in(site, prior):
            outline(img, lab, np.nonzero(np.isin(idx, pm))[0], nm, texts=texts)
        panels.append((img, f"{PANEL[k]} {label}", texts))
        ar = z["area"][idx]
        okw = np.isfinite(w)
        lead = float(ar[okw & (w > 0.5)].sum() / ar[okw].sum()) if okw.any() else None
        js["panels"].append(dict(label=label, patches=int(len(idx)), w_med=float(np.median(w[okw])) if okw.any() else None, mvs_leads_area_share=lead,
                                 none_share=float((~okw).mean())))
        foot.append(f"{PANEL[k]} 무게 비율 중앙값 {np.median(w[okw]):.2f}, MVS가 이끄는 넓이 {pct(lead)}, 둘 다 값 없음 {pct((~okw).mean())}")
    figure(panels, f"{TITLES['B']} — {U.SITE_KO[site]}", "지역 전체(평가 범위): " + "; ".join(foot), "w", out / f"B_{site}", js)


# ------------------------------------------------------------------------------------------------ E
def section_axis(C3):
    c0 = C3.mean(0)
    X = C3[:, :2] - c0[:2]
    if len(X) < 2:
        return c0, np.array([1.0, 0.0, 0.0])
    w, v = np.linalg.eigh(X.T @ X)
    t = np.array([v[0, -1], v[1, -1], 0.0])
    return c0, t / np.linalg.norm(t)


def largest_part(C3, area):
    """the largest part of a place (patch centres joined within 0.36 m, as the clump rule): the section goes through it."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    pr = cKDTree(C3).query_pairs(0.36, output_type="ndarray")
    nc, lab = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(len(C3), len(C3))), directed=False)
    k = int(np.argmax(np.bincount(lab, weights=area, minlength=nc)))
    return lab == k, int(nc)


def mvs_box(site, var, lo, hi):
    X = np.load(U.PTS / site / f"mvs_{var}_xyz.npy", mmap_mode="r")
    m = (X[:, 0] >= lo[0]) & (X[:, 0] <= hi[0]) & (X[:, 1] >= lo[1]) & (X[:, 1] <= hi[1])
    idx = np.nonzero(m)[0]
    return idx, np.asarray(X[idx], np.float64)


def thin_per_m(s, idx_order, per_m=400):
    """keep at most per_m points per 1 m of s, the smallest index (= key) first."""
    b = np.floor(s).astype(np.int64)
    o = np.lexsort((idx_order, b))
    bs = b[o]
    first = np.r_[0, np.nonzero(np.diff(bs))[0] + 1]
    rank = np.arange(len(bs)) - np.repeat(first, np.diff(np.r_[first, len(bs)]))
    keep = np.zeros(len(s), bool)
    keep[o[rank < per_m]] = True
    return keep


def section_panel(ax, S, site, prior, var, c0, t, s_rng, place_mask, zz):
    nh = np.array([-t[1], t[0], 0.0])
    z = S.get(site, prior)
    d = f"mvs_{var}"
    lo = np.minimum(c0 + s_rng[0] * t, c0 + s_rng[1] * t) - 3.0
    hi = np.maximum(c0 + s_rng[0] * t, c0 + s_rng[1] * t) + 3.0
    gidx, X = mvs_box(site, var, lo, hi)
    s = (X - c0) @ t
    off = (X - c0) @ nh
    band = (np.abs(off) <= 0.25) & (s >= s_rng[0]) & (s <= s_rng[1])
    kk = thin_per_m(s[band], gidx[band])
    ax.scatter(s[band][kk], X[band][kk, 2], s=0.15, c="#9a9a9a", lw=0, rasterized=True, zorder=1)
    G = np.load(U.PTS / site / "gt_xyz.npy", mmap_mode="r")
    gm = (G[:, 0] >= lo[0]) & (G[:, 0] <= hi[0]) & (G[:, 1] >= lo[1]) & (G[:, 1] <= hi[1])
    GX = np.asarray(G[np.nonzero(gm)[0]], np.float64)
    gs, go = (GX - c0) @ t, (GX - c0) @ nh
    gb = (np.abs(go) <= 0.25) & (gs >= s_rng[0]) & (gs <= s_rng[1])
    gk = thin_per_m(gs[gb], np.arange(gb.sum()))
    ax.scatter(gs[gb][gk], GX[gb][gk, 2], s=0.3, c="k", lw=0, rasterized=True, zorder=3)
    # prior surface: each patch as a short segment along its in-section direction
    C3, N3 = z["centre"], z["normal"]
    ps, po = (C3 - c0) @ t, (C3 - c0) @ nh
    pb = np.nonzero((np.abs(po) <= 0.125) & (ps >= s_rng[0]) & (ps <= s_rng[1]))[0]
    for i in pb:
        dirv = t - (t @ N3[i]) * N3[i]
        if np.linalg.norm(dirv) < 1e-6:
            dirv = np.array([0, 0, 1.0])
        dirv /= np.linalg.norm(dirv)
        a, b = C3[i] - 0.125 * dirv, C3[i] + 0.125 * dirv
        ax.plot([(a - c0) @ t, (b - c0) @ t], [a[2], b[2]], color="#e66101", lw=1.0, zorder=4, solid_capstyle="butt")
    # sample patches on the line: one per 1 m, centre within 0.125 m of the line
    cond = (np.abs(po) <= 0.125) & (ps >= s_rng[0] + 0.5) & (ps <= s_rng[1] - 0.5) & (z[f"{d}_status"] == 0)
    if place_mask is not None and (cond & place_mask).sum() >= 3:
        cond &= place_mask                                     # the sample patches are the place's own patches where it crosses the line
    on = np.nonzero(cond)[0]
    pick = []
    for k in np.unique(np.floor(ps[on])):
        cand = on[np.floor(ps[on]) == k]
        pick.append(int(cand[np.argmin(np.abs(ps[cand] - (k + 0.5)))]))
    from scipy.spatial import cKDTree
    tree = cKDTree(X)
    inner_z = []
    for i in pick:
        c, n = C3[i], N3[i]
        o = float(z[f"{d}_o"][i])
        H = U.D["column_half_m"]["roof" if z["roof_like"][i] else "wall"]
        cand = np.asarray(tree.query_ball_point(c + o * n, np.hypot(0.5, 1.0) + 1e-6), np.int64)
        tt, rho, _ = C.column_coords(X[cand] - c, n)
        mm = (rho <= 0.5) & (np.abs(tt - o) <= 1.0) & (np.abs(tt) <= H)
        inn = cand[mm]
        inn = inn[np.argsort(gidx[inn])][:U.D["mvs_cap_inner"]]
        Q = X[inn]
        inner_z.extend(np.percentile(Q[:, 2], [5, 95]).tolist() if len(Q) else [])
        ax.scatter((Q - c0) @ t, Q[:, 2], s=0.5, c="#00b5b5", lw=0, rasterized=True, zorder=3.5)
        m3 = np.array([z[f"{d}_nx"][i], z[f"{d}_ny"][i], z[f"{d}_nz"][i]], np.float64)
        h = float(z[f"{d}_h"][i])
        if abs(m3[2]) > 1e-3:
            sc = (c - c0) @ t
            ss = np.linspace(sc - 0.5, sc + 0.5, 5)
            # the plane {x: (x - c) . m = h} met by the vertical section plane through the line: solve for z at each s
            zs = [c[2] + (h - np.array([(c0 + s_ * t - c)[0], (c0 + s_ * t - c)[1], 0.0]) @ m3) / m3[2] for s_ in ss]
            ax.plot(ss, zs, ls=(0, (1.5, 1.2)), color="#005f5f", lw=0.9, zorder=5)
        pw = z[f"pW_{var}"][i]
        if np.isfinite(pw):
            P = c + pw * n
            ax.plot([(P - c0) @ t - 0.2, (P - c0) @ t + 0.2], [P[2], P[2]], color="#7b3294", lw=1.6, zorder=6, solid_capstyle="butt")
    ax.set_xlim(*s_rng)
    if zz is None:                                             # frame = the place's stretch: its GT, its prior patches, its sample patches' inner points
        ps_in = (place_mask[pb] if place_mask is not None else np.ones(len(pb), bool))
        pr_z = C3[pb][ps_in][:, 2] if ps_in.any() else C3[pb][:, 2]
        pr_s = ps[pb][ps_in] if ps_in.any() else ps[pb]
        sl, sh = (float(pr_s.min()), float(pr_s.max())) if len(pr_s) else s_rng
        gsel = gb & (gs >= sl) & (gs <= sh)
        ref = np.concatenate([GX[gsel][:, 2], pr_z] + ([np.asarray(inner_z)] if inner_z else []))
        zz = (float(np.percentile(ref, 1)) - 0.3, float(np.percentile(ref, 99)) + 0.3) if len(ref) else (c0[2] - 1.0, c0[2] + 1.0)
    ax.set_ylim(*zz)
    bb = ax.get_window_extent().transformed(ax.figure.dpi_scale_trans.inverted())
    ex = ((s_rng[1] - s_rng[0]) / bb.width) / ((zz[1] - zz[0]) / bb.height)
    ax.set_xlabel("단면을 따라 (m)", fontsize=6); ax.set_ylabel(f"높이 (m), 세로 ×{ex:.1f}", fontsize=6)
    ax.tick_params(labelsize=5.5)
    return dict(z_limits=zz, vertical_exaggeration=ex, mvs_points_in_band=int(band.sum()), gt_points_in_band=int(gb.sum()), sample_patches=pick, prior_patches_in_band=int(len(pb)))


def fig_E(S, place, out):
    arr = np.load(U.WORK / "places.npz")
    pl = U.jl(U.WORK / "places.json")["places"]
    info = pl.get(place) or {}
    if info.get("status") or (place not in pl and f"{place}__LoD2" not in pl):
        return
    if place == "b173_wing":
        site, prior = "B173nb_b10", "ALS"
    else:
        site, prior = info["site"], info["prior"]
    idx = arr[f"{place}__{prior}"]
    z = S.get(site, prior)
    C3 = z["centre"][idx]
    lo, hi = C3.min(0) - FC["zoom_margin_m"], C3.max(0) + FC["zoom_margin_m"]
    inbox = np.nonzero((z["centre"][:, 0] >= lo[0]) & (z["centre"][:, 0] <= hi[0]) & (z["centre"][:, 1] >= lo[1]) & (z["centre"][:, 1] <= hi[1]))[0]
    px = 0.05 if (hi - lo)[:2].max() < 40 else 0.1
    lab = top(site, prior, inbox, lo[:2], hi[:2], px)
    sel = np.nonzero(np.isin(inbox, idx))[0]
    up = L.val(z, "als", "u")[inbox] if prior == "ALS" else np.full(len(inbox), U.D["lod2_u_m"])
    vals = [(L.val(z, "mvs_a", "u")[inbox], "u", "MVS u"), (up, "u", "항공 LiDAR u" if prior == "ALS" else "LoD2 u (20 cm로 둠)"),
            (z["w_a"][inbox], "w", "MVS 무게 비율")]
    glass = place in ("glass_strip", "glass_dome")
    nrow = 3 if glass else 2
    H, W = lab.shape
    fw = 7.4
    tw = fw / 3 * 0.96
    th = tw * H / W
    sec_h = 2.0
    Ht = th + sec_h * (nrow - 1) + 1.9
    fig = plt.figure(figsize=(fw, Ht))
    for k, (v, kind, nm) in enumerate(vals):
        ax = fig.add_axes([0.01 + k * 0.33, 1 - (0.45 + th) / Ht, 0.32, th / Ht])
        rgb, ok = colours(v, kind)
        img = paint(lab, rgb, ok, over=(ok & (v > UMAX)) if kind == "u" else None, kind=kind)
        outline(img, lab, sel, "")
        ax.imshow(img, interpolation="nearest"); ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"{PANEL[k]} {nm}" + (": 주황 사전 정보, 파랑 MVS가 이끎" if kind == "w" else ""), fontsize=6.5, loc="left", pad=2)
    cax = fig.add_axes([0.03, 1 - (0.78 + th) / Ht, 0.6, 0.1 / Ht])
    cb = fig.colorbar(plt.cm.ScalarMappable(cmap=VIR, norm=Normalize(0, 50)), cax=cax, orientation="horizontal")
    cb.ax.tick_params(labelsize=5.5); cb.set_label("(가)(나) 불확실도 (cm), 50 넘음 = 점 무늬, 빗금 = 값 없음", fontsize=5.5)
    comp, ncomp = largest_part(C3, z["area"][idx])
    c0, t = section_axis(C3[comp])
    sp = (C3[comp] - c0) @ t
    s_rng = (float(sp.min()) - 2.0, float(sp.max()) + 2.0)
    secs = []
    gz = []
    for r, var in enumerate(["a"] + (["b"] if glass else [])):
        ax = fig.add_axes([0.08, 1 - (1.25 + th + sec_h * (r + 1) - 0.45) / Ht, 0.9, (sec_h - 0.55) / Ht])
        pmask = np.zeros(len(z["centre"]), bool)
        pmask[idx] = True
        info_s = section_panel(ax, S, site, prior, var, c0, t, s_rng, pmask, gz[0] if gz else None)
        secs.append(info_s)
        gz.append(info_s["z_limits"])
        ax.set_title(f"{PANEL[3] if r == 0 else '(마)'} 단면, MVS {'판 가' if var == 'a' else '판 나(마스크 전)'}: 회색 MVS 점, 청록 안쪽 원 점, 점선 고리 평면, "
                     f"검정 참값, 주황 사전 정보 면(단면선 0.125 m 안 패치), 보라 막대 무게 평균의 자리(청록·점선·보라 = 자리 패치)", fontsize=5.5, loc="left", pad=2)
    m = np.zeros(len(z["centre"]), bool)
    m[idx] = True
    pv = __import__("u3_tables").place_values(S, place, site, prior, idx)
    a = pv["mvs_a"]

    def f(x):
        return "결과 없음" if x is None else f"{x:.1f}"
    wtxt = "결과 없음" if a["w_med"] is None else f"{a['w_med']:.2f}"
    foot = (f"자리({len(idx)}패치, {pv['area_m2']:.1f} m², 참값 여러 층 {pct(pv['gt_multi_layer_share'] or 0)}) 중앙값: u_M {f(a['u_cm'])} cm, u_사전 {f(pv['u_prior_cm'])} cm, "
            f"e_M {f(a['e_cm'])} cm, e_사전 {f(pv['e_prior_cm'])} cm, MVS 무게 비율 {wtxt}, "
            f"p_M {f(a['p_cm'])} cm, p_G {f(pv['p_G_cm'])} cm, p_W {f(a['pW_cm'])} cm")
    if glass:
        b = pv["mvs_b"]
        foot += f"; 판 나: u_M {f(b['u_cm'])} cm, e_M {f(b['e_cm'])} cm, p_M {f(b['p_cm'])} cm"
    fig.suptitle(f"{TITLES['E']} — {info.get('ko', place) if place != 'b173_wing' else 'B173 날개'} ({U.case_ko(site, prior)})", fontsize=8, y=0.997, va="top")
    fig.text(0.01, 0.004, foot, fontsize=5.3, ha="left", va="bottom", wrap=True)
    p = out / f"E_{place}"
    fig.savefig(p.with_suffix(".png"), dpi=FC["dpi"]); fig.savefig(p.with_suffix(".pdf")); plt.close(fig)
    U.jdump(p.with_suffix(".json"), dict(place=place, site=site, prior=prior, R=S.R, values=pv, sections=secs,
                                         section_axis=dict(centre=c0, t=t, s_range=s_rng, through="자리의 가장 큰 덩어리(0.36 m로 이음)의 긴 축",
                                                           parts=ncomp, largest_part_patches=int(comp.sum())),
                                         zoom=dict(lo=lo, hi=hi, px=px), footer=foot, made=U.now(), scientific_verdict=None))


# ------------------------------------------------------------------------------------------------ F (6.1-6.5)
def simple_fig(n, title, w=7.4, h=2.6):
    fig, axs = plt.subplots(1, n, figsize=(w, h), squeeze=False)
    fig.suptitle(title, fontsize=8.5, y=0.99, va="top")
    fig.subplots_adjust(bottom=0.25, top=0.82, wspace=0.32, left=0.08, right=0.98)
    return fig, axs[0]


def save(fig, path, js, footer):
    fig.text(0.01, 0.01, footer, fontsize=5.5, ha="left", va="bottom", wrap=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix(".png"), dpi=FC["dpi"]); fig.savefig(path.with_suffix(".pdf")); plt.close(fig)
    U.jdump(path.with_suffix(".json"), dict(js, footer=footer, made=U.now(), config_sha256=U.sha256(U.CFGP), scientific_verdict=None))


def styl(ax):
    ax.tick_params(labelsize=6)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


def fig_F_ga(S, out):
    edges = U.CFG["tables"]["u_bins_cm"]
    labs = [f"{a}~{b}" if b is not None else f"{a}~" for a, b in zip(edges[:-1], edges[1:])]
    fig, axs = simple_fig(3, TITLES["F_ga"], h=2.9)
    js = dict(R=str(S.R), panels=[])
    foot = []
    for k, (d, sets, nm) in enumerate((("mvs_a", ("LoD2", "ALS"), "MVS 판 가"), ("mvs_b", ("LoD2", "ALS"), "MVS 판 나"), ("als", ("ALS",), "항공 LiDAR"))):
        ax = axs[k]
        for i, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
            ax.add_patch(plt.Rectangle((i - 0.45, a), 0.9, (b if b is not None else 100) - a, color="#ececec", lw=0, zorder=0))
        for j, pset in enumerate(sets):
            z = S.pooled(pset)
            m = L.ev(z) & L.has(z, d) & np.isfinite(z[f"{d}_e"])
            u, e = 100 * z[f"{d}_u"][m].astype(np.float64), 100 * z[f"{d}_e"][m].astype(np.float64)
            stats = []
            for i, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
                kk = (u >= a) & ((u < b) if b is not None else True)
                v = e[kk]
                if len(v) >= U.CFG["tables"]["min_patches"]:
                    stats.append(dict(med=np.median(v), q1=np.quantile(v, .25), q3=np.quantile(v, .75), whislo=np.quantile(v, .1), whishi=np.quantile(v, .9),
                                      fliers=[], label=labs[i], n=int(len(v))))
                else:
                    stats.append(None)
            off = (j - (len(sets) - 1) / 2) * 0.32
            st = [x for x in stats if x is not None]
            pos = [i + off for i, x in enumerate(stats) if x is not None]
            col = "#2b5c8a" if pset == "LoD2" else "#9ecae1"
            bp = ax.bxp(st, positions=pos, widths=0.28, showfliers=False, patch_artist=True, manage_ticks=False)
            for b_ in bp["boxes"]:
                b_.set_facecolor(col); b_.set_edgecolor("k"); b_.set_linewidth(0.5)
            for key in ("medians", "whiskers", "caps"):
                for l_ in bp[key]:
                    l_.set_color("k"); l_.set_linewidth(0.6)
            js["panels"].append(dict(data=nm, set=pset, bins=[None if x is None else {kk: (float(v) if kk != "label" else v) for kk, v in x.items() if kk != "fliers"}
                                                              for x in stats]))
            if len(sets) > 1:
                ax.text(len(edges) - 1.6 + off, 1.0 if j == 0 else 0.62, f"{U.PRIOR_KO[pset]} 패치", fontsize=5.5, color=col if pset == "ALS" else "#2b5c8a",
                        ha="center")
        ax.set_yscale("log"); ax.set_ylim(0.5, 2000)
        ax.set_xticks(range(len(labs))); ax.set_xticklabels(labs, fontsize=5.5)
        ax.set_xlabel("u 구간 (cm)", fontsize=6)
        if k == 0:
            ax.set_ylabel("실제 오차 e (cm, 로그)", fontsize=6)
        ax.set_title(f"{PANEL[k]} {nm}", fontsize=7, loc="left")
        styl(ax)
    foot = ("세 지역 합, 평가 범위, 값과 참값 평면이 있는 패치. 상자 = 25~75 %, 가로선 = 중앙값, 수염 = 10~90 %, 옅은 회색 띠 = e가 그 u 구간 안(e = u; 40~ 구간은 100 cm까지만 칠함). "
            "구간 30패치 미만은 그리지 않음. 항공 LiDAR 값은 항공 LiDAR 패치에서만 구함.")
    save(fig, out / "F_ga_u_vs_e", js, foot)


def fig_F_na(S, out):
    fig, axs = simple_fig(2, TITLES["F_na"], h=3.0, w=6.4)
    js = dict(R=str(S.R), panels=[])
    cols = {"u": "#1b6fa8", "어긋남": "#e66101", "흩어짐": "#5e3c99", "q": "#1a9850"}
    for k, pset in enumerate(U.PRIORS):
        z = S.pooled(pset)
        e = L.ev(z)
        c = z["cell"]
        gt = z["gt_status"] == 0
        pos = np.isin(c, [U.CID[x] for x in U.CFG["tables"]["roc_positive_cells"]]) & gt & e
        neg = np.isin(c, [U.CID[x] for x in U.CFG["tables"]["roc_negative_cells"]]) & gt & e
        ax = axs[k]
        txt = []
        rec = {}
        for nm, f in (("u", "u"), ("어긋남", "a"), ("흩어짐", "s"), ("q", "q")):
            sc = L.val(z, "mvs_a", f)
            cv = L.roc_curve(sc, pos, neg, 201)
            a = L.auc(sc, pos, neg)
            rec[nm] = dict(auc=a, curve=cv)
            ax.plot(cv["fpr"], cv["tpr"], color=cols[nm], lw=1.0 if nm != "u" else 1.6)
            txt.append((nm, a["auc"]))
        ax.plot([0, 1], [0, 1], color="#bbbbbb", lw=0.6, ls="--")
        for i, (nm, a) in enumerate(txt):
            ax.text(0.97, 0.05 + 0.08 * i, f"{nm} {a:.2f}", color=cols[nm], fontsize=6.5, ha="right", transform=ax.transAxes)
        ax.set_xlabel("음성을 잘못 잡은 비율", fontsize=6); ax.set_ylabel("양성을 잡은 비율", fontsize=6)
        ax.set_title(f"{PANEL[k]} {U.PRIOR_KO[pset]} 패치", fontsize=7, loc="left")
        js.setdefault("counts", []).append(f"{PANEL[k]} 양성 {rec['u']['auc']['n_pos']:,}, 음성 {rec['u']['auc']['n_neg']:,}")
        ax.set_aspect("equal"); styl(ax)
        js["panels"].append(dict(set=pset, scores={k_: dict(auc=v["auc"], curve=v["curve"]) for k_, v in rec.items()}))
    save(fig, out / "F_na_roc", js, "MVS 판 가, 세 지역 합, 평가 범위, 참값 평면이 있는 패치(" + "; ".join(js["counts"]) + "). 양성 = 보존 · 문턱 안, 한계, 이중 오류; 음성 = 다듬기, 보정 두 칸. "
         "오른쪽 아래 숫자 = 곡선 아래 넓이(u = 지금 식, q = 68.3 % 값). u, 흩어짐, q 곡선은 거의 겹친다.")


def fig_F_da(S, out):
    fig, axs = simple_fig(3, TITLES["F_da"], h=2.7)
    js = dict(R=str(S.R), panels=[])
    foot = []
    for k, s in enumerate(U.SITES):
        z = S.get(s, "LoD2")
        e = L.ev(z) & z["roof_like"].astype(bool)
        uM = L.val(z, "mvs_a", "u")
        pM = np.abs(L.val(z, "mvs_a", "p"))
        pG = np.abs(np.where(z["gt_status"] == 0, z["gt_p"], np.nan))
        ax = axs[k]
        rec = {}
        for nm, v, col, ls in (("MVS (u_M ≤ 5 cm)", pM[e & (uM <= 0.05)], "#1b6fa8", "-"), ("MVS (u_M ≤ 10 cm)", pM[e & (uM <= 0.10)], "#9ecae1", "--"),
                               ("참값 (보정 · 4τ 넘음 뺌)", pG[e & (z["cell"] != U.CID["c_corr4p"])], "k", "-")):
            v = np.sort(100 * v[np.isfinite(v)])
            if len(v):
                ax.plot(v, np.arange(1, len(v) + 1) / len(v), color=col, ls=ls, lw=1.1)
            rec[nm] = dict(n=int(len(v)), within20=float(np.mean(v <= 20)) if len(v) else None, within30=float(np.mean(v <= 30)) if len(v) else None,
                           q68=float(np.quantile(v, .68)) if len(v) else None)
        for x in (20, 30):
            ax.axvline(x, color="#888888", ls=":", lw=0.8)
        ax.set_xlim(0, 100); ax.set_ylim(0, 1)
        ax.set_xlabel("LoD2 지붕면에서의 차 크기 (cm)", fontsize=6)
        if k == 0:
            ax.set_ylabel("누적 비율", fontsize=6)
        ax.set_title(f"{PANEL[k]} {U.SITE_KO[s]}", fontsize=7, loc="left")
        y = 0.08
        for nm, col in (("MVS (u_M ≤ 5 cm)", "#1b6fa8"), ("MVS (u_M ≤ 10 cm)", "#5a9bd0"), ("참값 (보정 · 4τ 넘음 뺌)", "k")):
            r = rec[nm]
            if r["n"]:
                ax.text(98, y, f"{nm}: 20 cm 안 {100 * r['within20']:.0f} %", fontsize=5.3, color=col, ha="right")
            y += 0.08
        styl(ax)
        js["panels"].append(dict(site=s, lines=rec))
    save(fig, out / "F_da_lod2", js, "평가 범위의 LoD2 지붕꼴 패치. 파랑 = 믿을 만한 MVS의 |p_M|(실선 u_M ≤ 5 cm, 점선 ≤ 10 cm), 검정 = 참값의 |p_G|(보정 · 4τ 넘음 = LoD2가 참값에서 4τ 넘게 벗어난 칸을 뺌). "
         "점선 = 20, 30 cm. 곡선이 1에 닿지 않는 만큼은 100 cm 넘는 패치.")


def bool_map(S, site, cases, title, name, out, key):
    lo, hi = eval_box(site)
    panels, js, foot = [], dict(site=site, R=str(S.R), panels=[]), []
    for k, (prior, d, label) in enumerate(cases):
        z = S.get(site, prior)
        idx = np.nonzero(L.ev(z))[0]
        lab = top(site, prior, idx, lo[:2], hi[:2])
        has = L.has(z, d)[idx]
        ee = z[f"{d}_e"][idx].astype(np.float64)
        excl = ~np.isfinite(ee) & has
        if key == "missed":
            u = L.val(z, d, "u")[idx]
            flag = has & np.isfinite(ee) & (ee > 0.2) & (ee > 2 * u)
            rgb = np.where(flag[:, None], AM.rgb("#c62f26"), AM.rgb("#d9d9d9"))
            img = paint(lab, rgb, has, excl=excl)
            n_ok = int((has & np.isfinite(ee)).sum())
            js["panels"].append(dict(label=label, missed=int(flag.sum()), with_value_and_gt=n_ok, area_m2=float(z["area"][idx][flag].sum())))
            foot.append(f"{PANEL[k]} 놓친 패치 {int(flag.sum()):,} / {n_ok:,} ({100 * flag.sum() / max(n_ok, 1):.1f} %)")
            panels.append((img, f"{PANEL[k]} {label}", []))
    figure(panels, f"{title} — {U.SITE_KO[site]}", "지역 전체(평가 범위): " + "; ".join(foot) + ". 빨강 = 놓친 패치(실제 오차 e > 20 cm 그리고 e > 2u), 회색 = 그 밖의 값 있는 패치, 빗금 = 값 없음, 황갈 = 참값 평면 없음",
           "none", out / name, js)


def fig_F_ra(S, site, out):
    cases = [("LoD2", "mvs_a", "MVS 판 가 (LoD2 패치)"), ("ALS", "mvs_a", "MVS 판 가 (항공 LiDAR 패치)"), ("ALS", "als", "항공 LiDAR (항공 LiDAR 패치)")]
    bool_map(S, site, cases, TITLES["F_ra"], f"F_ra_missed_{site}", out, "missed")


def fig_F_ma(S, out):
    eb = U.CFG["tables"]["edge_bins_m"]
    labs = [f"{a}~{b}" if b is not None else f"{a}~" for a, b in zip(eb[:-1], eb[1:])]
    fig, axs = simple_fig(3, TITLES["F_ma"], h=2.6)
    js = dict(R=str(S.R), panels=[])
    ymax = 0.0
    for k, (pset, d, nm) in enumerate((("LoD2", "mvs_a", "MVS 판 가 (LoD2 패치)"), ("ALS", "mvs_a", "MVS 판 가 (항공 LiDAR 패치)"), ("ALS", "als", "항공 LiDAR"))):
        z = S.pooled(pset)
        m = L.ev(z) & L.has(z, d) & np.isfinite(z[f"{d}_e"])
        ux, ex, ns = [], [], []
        for a, b in zip(eb[:-1], eb[1:]):
            kk = m & (z["edge"] >= a) & ((z["edge"] < b) if b is not None else True)
            ns.append(int(kk.sum()))
            ux.append(100 * float(np.median(z[f"{d}_u"][kk])) if kk.sum() >= 30 else np.nan)
            ex.append(100 * float(np.median(z[f"{d}_e"][kk])) if kk.sum() >= 30 else np.nan)
        ax = axs[k]
        ax.plot(range(len(labs)), ux, "-o", color="#1b6fa8", ms=3, lw=1.2)
        ax.plot(range(len(labs)), ex, "-s", color="k", ms=3, lw=1.2)
        ax.text(len(labs) - 1, ux[-1], " u", color="#1b6fa8", fontsize=6.5, va="center")
        ax.text(len(labs) - 1, ex[-1], " e", color="k", fontsize=6.5, va="center")
        ax.set_xticks(range(len(labs))); ax.set_xticklabels(labs, fontsize=6)
        ax.set_xlabel("다른 면까지 거리 (m)", fontsize=6)
        if k == 0:
            ax.set_ylabel("중앙값 (cm)", fontsize=6)
        ymax = max(ymax, np.nanmax(ux + ex))
        ax.set_title(f"{PANEL[k]} {nm}", fontsize=6.5, loc="left")
        styl(ax)
        js["panels"].append(dict(set=pset, data=d, bins=labs, u_med_cm=ux, e_med_cm=ex, patches=ns))
    for ax in axs:
        ax.set_ylim(0, 1.1 * ymax)
    save(fig, out / "F_ma_edge", js, "세 지역 합, 평가 범위, 값과 참값 평면이 있는 패치. 가로 = 면 번호가 다른 가장 가까운 패치까지 거리. 파랑 = u의 중앙값, 검정 = 실제 오차 e의 중앙값. 세 칸의 세로축 같음.")


def fig_F_ba(S, site, out):
    lo, hi = eval_box(site)
    z = S.get(site, "LoD2")
    idx = np.nonzero(L.ev(z))[0]
    lab = top(site, "LoD2", idx, lo[:2], hi[:2])
    has = L.has(z, "mvs_a")[idx]
    ff = z["mvs_a_f"][idx].astype(np.float64)
    half = has & (ff >= 0.3) & (ff <= 0.5)
    excl = has & ~np.isfinite(ff)
    panels, js, foot = [], dict(site=site, R=str(S.R), panels=[]), []
    for k, (f, nm) in enumerate((("u", "지금 식 u"), ("q", "68.3 % 값 q"))):
        v = L.val(z, "mvs_a", f)[idx]
        rgb, ok = colours(v, "u")
        rgb[~half] = AM.rgb("#e3e3e3")
        img = paint(lab, rgb, has, over=half & (v > UMAX), excl=excl)
        panels.append((img, f"{PANEL[k]} 반쯤 틀린 패치를 {nm}로 칠함", []))
        vv = v[half]
        js["panels"].append(dict(score=f, half_patches=int(half.sum()), med_cm=100 * float(np.median(vv)) if len(vv) else None))
        foot.append(f"{PANEL[k]} {nm} 중앙값 {cm(np.median(vv) if len(vv) else None)}")
    figure(panels, f"{TITLES['F_ba']} — {U.SITE_KO[site]}", f"지역 전체(평가 범위, LoD2 패치, MVS 판 가): 반쯤 틀린 패치(틀린 점 30~50 %) {int(half.sum()):,}개; "
           + "; ".join(foot) + ". 회색 = 그 밖의 값 있는 패치, 황갈 = 참값 평면 없음", "u", out / f"F_ba_half_{site}", js)


if __name__ == "__main__":
    R, folder = L.parse_R(sys.argv[1])
    what = sys.argv[2]
    S = L.Store(R)
    out = U.DOCS / "figures" / folder
    args = sys.argv[3:]
    T = U.Timer()
    if what in ("A", "Aob", "B", "C", "D"):
        for s in args or U.SITES:
            {"A": lambda: fig_A(S, s, out), "Aob": lambda: fig_A(S, s, out, oblique_views=True), "B": lambda: fig_B(S, s, out),
             "C": lambda: fig_C(S, s, out), "D": lambda: fig_D(S, s, out)}[what]()
            U.log(what, s, T.mark(s))
    elif what == "E":
        for p in args:
            fig_E(S, p, out)
            U.log("E", p, T.mark(p))
    elif what in ("F_ga", "F_na", "F_da", "F_ma"):
        {"F_ga": fig_F_ga, "F_na": fig_F_na, "F_da": fig_F_da, "F_ma": fig_F_ma}[what](S, out)
        U.log(what, T.mark(what))
    elif what in ("F_ra", "F_ba"):
        for s in args or U.SITES:
            {"F_ra": fig_F_ra, "F_ba": fig_F_ba}[what](S, s, out)
            U.log(what, s, T.mark(s))

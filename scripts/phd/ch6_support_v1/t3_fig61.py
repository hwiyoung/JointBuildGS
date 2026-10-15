"""PHD-CH6-SUPPORT-v1 task 3: figure 6.1 (experiment regions) and the list of the marked sites (jointbuildgs:dev, CPU;
definitions = configs ch6_support_v1.json 'task3_figure' and the request's table of sites, written before the drawing).

  python t3_fig61.py [--stats]

(a) campus overview (ULS colour, MVS colour where ULS is absent) with the eight search ranges and the four evaluation ranges
    (solid) with their 10 m band (dashed); (b)-(e) one region each on its 0.1 m ULS true ortho, the evaluation range, and the
    item sites painted from the stage-1 region files v3 (both priors as listed in SITES), each with a short name tag.
Maps are drawn in the rotated u-v frame of the boxes with the v axis pointing down, which makes them a proper rotation of the
map (the u-v frame is mirrored); a north arrow is drawn on every panel.
Writes /out/t3/fig6_1_regions.png (+ .pdf), /out/t3/sites.csv, sites.json, and with --stats only the item areas.
scientific_verdict: null."""
import argparse
import csv
import json

import numpy as np
import scipy.ndimage as ndi

from pathlib import Path

from ch6_common import BOXDEF, DR, OUT, RNGDEF, S0, S1, footprint_index, jdump, log, rule, setup_fonts, uv_to_xy
from common import SHIFT

O = OUT / "t3"
A_DEG = 70.0
STYLE = {"wrong": ("사전 정보가 틀린 곳", "#d62728"), "slight": ("사전 정보가 조금 틀린 곳", "#f39c12"),
         "missing": ("영상이 보지 못한 곳 (결측)", "#1f77b4"), "invisible": ("영상이 보지 못한 곳 (비가시)", "#8e44ad"),
         "undecidable": ("맞는 자료를 판단할 수 없는 곳", "#111111")}
SHORT = {"wrong": "사전 정보 틀림", "slight": "조금 틀림", "missing": "보지 못함", "invisible": "보지 못함", "undecidable": "판단 불가"}
INF = np.inf
# (item, place word, selection) per region; codes of the region files v3 (gt_med = GT - prior; sign -1 = prior above GT)
SITES_CFG = json.loads(Path("/repo/configs/phd/main_prep_discard_rule_v1/sites_v1.json").read_text())["sites"]
FACES = {x["id"]: x["faces_gml"] for x in SITES_CFG}
# (item, place word, selection) per region. Codes of the region files v3 (gt_med = GT - prior; sign -1 = prior above GT);
# 'state' selects by the observation state (GT-independent, the unseen items); 'faces' = the sites_v1 membership rule
# (LoD2 patches of the faces, ALS patches within 0.5 m in plan of those LoD2 patch centres); 'outline' hatches the faces.
SITES = {
    "B0_b10": [("wrong", "정면·지붕 가장자리", dict(priors=["LoD2"], codes=[11], ratio=(4, INF))),
               ("slight", "1~4τ 패치", dict(priors=["LoD2", "ALS"], codes=[11], ratio=(1, 4))),
               ("missing", "깊이 없는 창", dict(priors=["LoD2"], state="missing", kind=2))],
    "B173nb_b10": [("wrong", "날개", dict(priors=["LoD2", "ALS"], codes=[11], ratio=(4, INF), sign=-1, building="4959326")),
                   ("invisible", "긴 벽", dict(priors=["LoD2"], state="invisible", kind=2)),
                   ("missing", "이웃 건물 벽", dict(priors=["LoD2"], state="missing", kind=2, not_building="4959326")),
                   ("undecidable", "유리 채광창", dict(priors=["LoD2", "ALS"], codes=[3], premise=True, faces="B173_middle"))],
    "B173_b0": [("undecidable", "대부분 바뀐 장면", None)],
    "R1rep_b10": [("wrong", "낮은 지붕", dict(priors=["LoD2"], codes=[11], ratio=(4, INF), sign=1)),
                  ("slight", "1~4τ 패치", dict(priors=["LoD2", "ALS"], codes=[11], ratio=(1, 4))),
                  ("missing", "지붕 빈 곳", dict(priors=["LoD2", "ALS"], state="missing", kind=1)),
                  ("undecidable", "반투명 지붕", dict(priors=["ALS"], codes=[3], premise=True, faces="R1_hall", outline=True))],
}
TITLE = {"B0_b10": "(나) B0", "B173nb_b10": "(다) B173 주변", "B173_b0": "(라) B173만", "R1rep_b10": "(마) R1"}
BAND = {"B0_b10": 10.0, "B173nb_b10": 10.0, "B173_b0": 0.0, "R1rep_b10": 10.0}
BID = {"B0_b10": "B0", "B173nb_b10": "B173nb", "B173_b0": "B173", "R1rep_b10": "R1rep"}
LABEL_OFFSET = {("B173nb_b10", "wrong"): (-30.0, -24.0), ("B173nb_b10", "undecidable"): (6.0, 6.0)}   # (box, item) -> label position - cluster centre (m); set after the first look, drawing only


def face_members(box, gmls):
    """the sites_v1 membership rule (as stage-1 regions_v3.site_faces)."""
    from scipy.spatial import cKDTree
    tab = json.loads((DR / "s02_box" / box / "lod2_surfaces.json").read_text())["surfaces"]
    exts = {r["ext"] for r in tab if r["gml"] in gmls}
    U = np.load(S0 / "s61/box" / box / "LoD2" / "units.npz")
    lod = np.isin(U["surf_ext"][U["loc_surface"]], list(exts))
    Ua = np.load(S0 / "s61/box" / box / "ALS" / "units.npz")
    d, _ = cKDTree(U["loc_center"][lod][:, :2]).query(Ua["loc_center"][:, :2], distance_upper_bound=0.5)
    return dict(LoD2=lod, ALS=np.isfinite(d))


def select(box, sel, eval_only=True):
    """union over the listed priors of the patches matching the selection; returns centres (u, v), areas, kinds, priors."""
    from ch6_common import xy_to_uv
    out = []
    mem = face_members(box, FACES[sel["faces"]]) if "faces" in sel else None
    for prior in sel["priors"]:
        G = np.load(S1 / "regions_v3" / f"regions_ext_v3_{box}_{prior}.npz")
        code = G["code_ext_v3"]; med = G["gt_med"].astype(np.float64); tau = G["tau"].astype(np.float64)
        m = G["in_eval"].astype(bool) if eval_only else np.ones(len(code), bool)
        if "codes" in sel:
            m &= np.isin(code, sel["codes"])
        if "state" in sel:
            m &= G["state"] == {"missing": rule.ST_MISSING, "invisible": rule.ST_INVISIBLE}[sel["state"]]
        if "ratio" in sel:
            r = np.abs(med) / tau
            m &= (r >= sel["ratio"][0]) & (r < sel["ratio"][1])
        if "sign" in sel:
            m &= np.sign(med) == sel["sign"]
        if "kind" in sel:
            m &= G["kind"] == sel["kind"]
        if sel.get("premise"):
            m &= G["premise_violation"].astype(bool)
        if mem is not None:
            m &= mem[prior]
        if "building" in sel or "not_building" in sel:
            fp, names = footprint_index(DR / "s02_box" / box / "footprints.json", G["centre"][:, :2])
            isb = np.array([(fi >= 0) and (sel.get("building", sel.get("not_building")) in names[fi]) for fi in fp])
            m &= isb if "building" in sel else ~isb
        uv = xy_to_uv(G["centre"][m][:, :2])
        out.append((uv, G["area"][m].astype(np.float64), G["kind"][m], np.full(int(m.sum()), prior)))
    return (np.concatenate([o[0] for o in out]), np.concatenate([o[1] for o in out]), np.concatenate([o[2] for o in out]),
            np.concatenate([o[3] for o in out]))


def face_outline_uv(box, face_id):
    """LoD2 patch centres of the faces (whole box, not only the evaluation range)."""
    from ch6_common import xy_to_uv
    mem = face_members(box, FACES[face_id])
    U = np.load(S0 / "s61/box" / box / "LoD2" / "units.npz")
    return xy_to_uv(U["loc_center"][mem["LoD2"]][:, :2]), U["loc_area"][mem["LoD2"]].astype(np.float64)


def paint(shape, u0, v0, res, uv, area):
    H, W = shape
    msk = np.zeros((H, W), bool)
    if len(uv) == 0:
        return msk
    side = np.maximum(np.sqrt(area), 0.3)
    k = int(np.ceil(side.max() / res / 2))
    iu = ((uv[:, 0] - u0) / res).astype(np.int64); iv = ((uv[:, 1] - v0) / res).astype(np.int64)
    kk = np.ceil(side / res / 2).astype(np.int64)
    for du in range(-k, k + 1):
        for dv in range(-k, k + 1):
            ok = (np.abs(du) <= kk) & (np.abs(dv) <= kk)
            a = np.clip(iu[ok] + du, 0, W - 1); b = np.clip(iv[ok] + dv, 0, H - 1)
            msk[b, a] = True
    return msk


def north(ax, u, v, L):
    a = np.deg2rad(A_DEG)
    du, dv = L * np.sin(a), -L * np.cos(a)          # north (0, 1) in the u-v frame
    ax.annotate("", xy=(u + du, v + dv), xytext=(u, v), arrowprops=dict(arrowstyle="-|>", color="k", lw=1.4))
    ax.text(u + 1.25 * du, v + 1.25 * dv, "N", ha="center", va="center", fontsize=8.5, fontweight="bold")


def scalebar(ax, u, v, L, text):
    ax.plot([u, u + L], [v, v], color="k", lw=2.4, solid_capstyle="butt")
    ax.plot([u, u + L], [v, v], color="white", lw=1.0, solid_capstyle="butt")
    ax.text(u + L / 2, v - 0.025 * L * 8, text, ha="center", va="bottom", fontsize=7.5)


def rect_uv(b, band=0.0):
    u0, u1 = b["eval_u"][0] - band, b["eval_u"][1] + band; v0, v1 = b["eval_v"][0] - band, b["eval_v"][1] + band
    return np.array([[u0, v0], [u1, v0], [u1, v1], [u0, v1], [u0, v0]])


def uv_to_epsg(uv):
    xy = uv_to_xy(np.asarray(uv, np.float64))
    return xy + SHIFT[:2]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--stats", action="store_true"); a = ap.parse_args()
    sites_rows = []
    stats = {}
    for box, items in SITES.items():
        for item, place, sel in items:
            if sel is None:
                r = rect_uv(BOXDEF[BID[box]])
                stats[f"{box}/{item}"] = dict(place=place, whole_range=True)
                e = uv_to_epsg(r[:4])
                sites_rows.append(dict(region=box, item=STYLE[item][0], place=place, priors="둘 다", patches="", area_m2=round(float((r[1, 0] - r[0, 0]) * (r[2, 1] - r[1, 1])), 1),
                                       u_min=r[:, 0].min(), u_max=r[:, 0].max(), v_min=r[:, 1].min(), v_max=r[:, 1].max(),
                                       E_min=round(e[:, 0].min(), 2), E_max=round(e[:, 0].max(), 2), N_min=round(e[:, 1].min(), 2), N_max=round(e[:, 1].max(), 2)))
                continue
            uv, area, kind, pri = select(box, sel)
            stats[f"{box}/{item}"] = dict(place=place, patches=int(len(uv)), area_m2=round(float(area.sum()), 1),
                                          by_prior={p: round(float(area[pri == p].sum()), 1) for p in sel["priors"]})
            if len(uv):
                e = uv_to_epsg(uv)
                sites_rows.append(dict(region=box, item=STYLE[item][0], place=place, priors="·".join(sel["priors"]), patches=int(len(uv)), area_m2=round(float(area.sum()), 1),
                                       u_min=round(uv[:, 0].min(), 2), u_max=round(uv[:, 0].max(), 2), v_min=round(uv[:, 1].min(), 2), v_max=round(uv[:, 1].max(), 2),
                                       E_min=round(e[:, 0].min(), 2), E_max=round(e[:, 0].max(), 2), N_min=round(e[:, 1].min(), 2), N_max=round(e[:, 1].max(), 2)))
    jdump(O / "sites_stats.json", stats)
    log(json.dumps(stats, ensure_ascii=False))
    if a.stats:
        return
    plt = setup_fonts()
    from matplotlib.patches import Patch, Polygon as MPoly
    import matplotlib.patheffects as pe
    halo = [pe.withStroke(linewidth=2.6, foreground="white")]
    fig = plt.figure(figsize=(8.6, 11.6))
    gs = fig.add_gridspec(4, 2, height_ratios=[1.32, 1.0, 1.0, 0.16], hspace=0.16, wspace=0.06, left=0.03, right=0.97, top=0.975, bottom=0.02)
    # (a) overview
    ax = fig.add_subplot(gs[0, :])
    OV = np.load(O / "ortho_overview.npz")
    rgb = OV["rgb"]; u0, v0, res = float(OV["u0"]), float(OV["v0"]), float(OV["res"])
    H, W = rgb.shape[:2]
    ax.imshow(rgb, origin="lower", extent=[u0, u0 + W * res, v0, v0 + H * res], interpolation="bilinear", alpha=0.9)
    rname = {"R1": "R1", "R2": "R2", "R3": "R3", "R4": "R4", "R5": "R5", "B0": "B0 범위", "SW": "SW", "R3E": "R3E"}
    for rid in ("R1", "R2", "R3", "R4", "R5", "B0", "SW", "R3E"):
        from ch6_common import xy_to_uv
        p = xy_to_uv(np.asarray(RNGDEF[rid]["polygon_local"], np.float64))
        p = np.vstack([p, p[:1]])
        ls = ":" if rid == "R3" else "-"
        ax.plot(p[:, 0], p[:, 1], color="#2b2b2b", lw=0.9, ls=ls)
        c = p[:-1].mean(0)
        corner = p[np.argmin(p[:-1, 0] + p[:-1, 1])]  # the (u min, v min) corner = upper left on the page
        ax.text(corner[0] + 3, corner[1] + 3, rname[rid], fontsize=7.5, color="#2b2b2b", ha="left", va="top", path_effects=halo)
    bcol = {"B0_b10": "#c0392b", "B173nb_b10": "#1a5276", "B173_b0": "#117a65", "R1rep_b10": "#7d3c98"}
    bname = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "B173_b0": "B173만", "R1rep_b10": "R1"}
    for box in SITES:
        b = BOXDEF[BID[box]]
        r = rect_uv(b); ax.plot(r[:, 0], r[:, 1], color=bcol[box], lw=1.8)
        if BAND[box] > 0:
            rb = rect_uv(b, BAND[box]); ax.plot(rb[:, 0], rb[:, 1], color=bcol[box], lw=1.1, ls="--")
        if box == "B173nb_b10":          # above its band (the B173-only range lies inside it)
            ax.text(r[0, 0] - BAND[box], r[0, 1] - BAND[box] - 1.5, bname[box], color=bcol[box], fontsize=8.5, fontweight="bold", ha="left", va="bottom", path_effects=halo)
        elif box == "B173_b0":
            ax.text(r[1, 0] - 1, r[2, 1] - 1, bname[box], color=bcol[box], fontsize=8.5, fontweight="bold", ha="right", va="bottom", path_effects=halo)
        else:
            ax.text(r[0, 0] + 1, r[2, 1] - 1, bname[box], color=bcol[box], fontsize=8.5, fontweight="bold", ha="left", va="bottom", path_effects=halo)
    ax.set_xlim(u0, u0 + W * res); ax.set_ylim(v0, v0 + H * res); ax.invert_yaxis(); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    north(ax, u0 + W * res - 30, v0 + H * res - 30, 22)
    scalebar(ax, u0 + 15, v0 + H * res - 18, 50, "50 m")
    ax.set_title("(가) 찾기 범위 여덟 곳과 실험 지역 넷 (실선 = 평가 범위, 점선 = 둘레 10 m)", fontsize=9, loc="left")
    # (b)-(e)
    pos = {"B0_b10": (1, 0), "B173nb_b10": (1, 1), "B173_b0": (2, 0), "R1rep_b10": (2, 1)}
    for box, items in SITES.items():
        ax = fig.add_subplot(gs[pos[box]])
        R = np.load(O / f"ortho_{box}.npz")
        rgb = R["rgb"]; u0, v0, res = float(R["u0"]), float(R["v0"]), float(R["res"])
        H, W = rgb.shape[:2]
        grey = (0.35 * rgb.mean(-1, keepdims=True) + 0.65 * rgb).astype(np.uint8)
        ax.imshow(grey, origin="lower", extent=[u0, u0 + W * res, v0, v0 + H * res], interpolation="bilinear")
        b = BOXDEF[BID[box]]
        r = rect_uv(b)
        for item, place, sel in items:
            col = STYLE[item][1]
            if sel is None:
                ax.add_patch(MPoly(r[:4], closed=True, fill=False, hatch="////", edgecolor=col, lw=0.0, alpha=0.55))
                ax.text(r[:, 0].mean(), r[:, 1].mean(), f"{SHORT[item]}\n{place}", ha="center", va="center", fontsize=8, color=col, path_effects=halo, fontweight="bold")
                continue
            if sel.get("outline"):
                fuv, farea = face_outline_uv(box, sel["faces"])
                fm = paint((H, W), u0, v0, res, fuv, farea)
                fr = np.zeros((H, W, 4)); fr[fm, :3] = 0.25; fr[fm, 3] = 0.28
                ax.imshow(fr, origin="lower", extent=[u0, u0 + W * res, v0, v0 + H * res], interpolation="nearest")
                ax.contour(np.arange(W) * res + u0 + res / 2, np.arange(H) * res + v0 + res / 2, ndi.binary_closing(fm, iterations=3).astype(float),
                           levels=[0.5], colors=[col], linewidths=0.9, linestyles="--")
            uv, area, kind, pri = select(box, sel)
            msk = paint((H, W), u0, v0, res, uv, area)
            if not msk.any():
                continue
            rgba = np.zeros((H, W, 4)); c = np.array([int(col[i:i + 2], 16) / 255 for i in (1, 3, 5)])
            rgba[msk, :3] = c; rgba[msk, 3] = 0.78
            ax.imshow(rgba, origin="lower", extent=[u0, u0 + W * res, v0, v0 + H * res], interpolation="nearest")
            # tag at the largest cluster (1 m closing), pushed away from the panel centre
            lab, n = ndi.label(ndi.binary_dilation(msk, iterations=int(1.0 / res)))
            if n:
                sizes = ndi.sum(msk, lab, index=np.arange(1, n + 1)); big = int(np.argmax(sizes)) + 1
                yy, xx = np.nonzero((lab == big) & msk)
                cu, cv = u0 + (xx.mean() + 0.5) * res, v0 + (yy.mean() + 0.5) * res
                pc = np.array([u0 + W * res / 2, v0 + H * res / 2])
                d = np.array([cu, cv]) - pc; d = d / (np.linalg.norm(d) + 1e-9)
                off = LABEL_OFFSET.get((box, item), tuple(9.0 * d))
                tu = np.clip(cu + off[0], u0 + 6, u0 + W * res - 6); tv = np.clip(cv + off[1], v0 + 3, v0 + H * res - 3)
                pu, pv = u0 + (xx + 0.5) * res, v0 + (yy + 0.5) * res          # leader to the cluster pixel nearest the tag
                j = int(np.argmin((pu - tu) ** 2 + (pv - tv) ** 2)); au, av = pu[j], pv[j]
                ax.annotate(f"{SHORT[item]}\n{place}", xy=(au, av), xytext=(tu, tv), fontsize=7.4, color=col, ha="center", va="center",
                            fontweight="bold", path_effects=halo, arrowprops=dict(arrowstyle="-", color=col, lw=0.9))
        ax.plot(r[:, 0], r[:, 1], color="white", lw=3.0); ax.plot(r[:, 0], r[:, 1], color="k", lw=1.3)
        if BAND[box] > 0:
            rb = rect_uv(b, BAND[box]); ax.plot(rb[:, 0], rb[:, 1], color="k", lw=0.9, ls="--")
        ax.set_xlim(u0, u0 + W * res); ax.set_ylim(v0, v0 + H * res); ax.invert_yaxis(); ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        north(ax, u0 + W * res - 9, v0 + H * res - 9, 6)
        scalebar(ax, u0 + 4, v0 + H * res - 4.5, 10, "10 m")
        ax.set_title(TITLE[box], fontsize=9, loc="left")
    # legend
    axl = fig.add_subplot(gs[3, :]); axl.axis("off")
    hs = [Patch(facecolor=STYLE[k][1], edgecolor="none", alpha=0.8, label=STYLE[k][0]) for k in ("wrong", "slight", "missing", "invisible", "undecidable")]
    axl.legend(handles=hs, loc="center", ncol=3, fontsize=7.6, frameon=False, handlelength=1.4, columnspacing=1.2)
    fig.savefig(O / "fig6_1_regions.png", dpi=300); fig.savefig(O / "fig6_1_regions.pdf"); plt.close(fig)
    keys = list(sites_rows[0])
    with open(O / "sites.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(sites_rows)
    jdump(O / "sites.json", dict(sites=sites_rows, stats=stats, crs_uv="box frame: u = 70 deg ccw from easting, v mirrored; E/N = EPSG:25832",
                                 scientific_verdict=None))
    log("figure 6.1 written")


if __name__ == "__main__":
    main()

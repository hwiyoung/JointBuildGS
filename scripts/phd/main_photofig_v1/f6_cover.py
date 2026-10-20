"""PHD-MAIN-PHOTOFIG-v1 figure 6 and table B: how much more of the walls does the manual flight (TUM2TWIN v1.2.0) cover than the current
GT (the nadir flight with the study's wall rule)? and how far apart are the two flights? (jointbuildgs:dev, CPU)

  python f6_cover.py <site> [...]   site = B173nb_b10 | R1rep_b10 | B0_b10 (B0: table B only)
  -> /docs/tables/fig6_<site>.json|md, /docs/figures/photo_fig6_<site>_<ext>.png|pdf|json (B173nb, R1)

Wall space (as B0REF 3.3): per LoD2 wall face, horizontal distance to the plane <= 1.0 m, foot inside the face, lower edge + 0.5 m to upper
edge - 0.5 m, evaluation range. Current GT wall points = nadir points of the study's rule (s04_gt_v7 vertical_points on all returns &
single return). Roof space = LoD2 roof faces, <= 1.0 m along the normal. Clouds in the raw frame (laz - shift), no height alignment.
Offsets (table B): per face, 0.5 m cells of (along, height) for walls and (plane axes) for roofs where both flights have >= 3 points;
cell medians of the outward normal distance; manual - nadir; median and NMAD per face and pooled. B0 walls = the target building's
walls (as B0REF 4.3) and, apart, all walls in the range.
Patches with GT, current vs current + manual [근사]: a patch has GT when it has >= 5 points; current = region file gt_n; manual points are
given to patches by nearest patch centre (roof-like: plan distance <= 0.18 m, top layer within 1.0 m below the patch's highest point;
wall-like: vertical points, the patch's plane square, <= 2 m along the normal) — a shortened form of s04_gt_v7.py:255-295.
Background of figure 6 = the training photo of places.fig6 (the most frontal view), laid on the wall plane (0.05 m), cells hidden behind
the LoD2 render depth (> 0.5 m) left grey. [이 발주에서 냄] scientific_verdict: null"""
import sys
import time

import numpy as np
from scipy.spatial import cKDTree

import pf_geo as G
from pf_common import DOCS, DR, PF, S0, S1, cfg, in_rect, jdump, jl, log, nmad, now, return_class

H_M, GAP = 1.0, 0.5
TARGET = {"B0_b10": "DEBY_LOD2_4959323"}


def faces_of(site):
    m = np.load(DR / "s02_box" / site / "lod2_mesh.npz")
    sh = np.asarray(jl(S0 / "s61/box" / site / "LoD2/summary.json")["registration"]["shift_applied"], np.float64)
    V = m["V"] + sh
    tab = {r["ext"]: r for r in jl(DR / "s02_box" / site / "lod2_surfaces.json")["surfaces"]}
    fps = {r.get("building"): np.asarray(r["ring_local"], np.float64)[:, :2].mean(0) for r in jl(DR / "s02_box" / site / "footprints.json")["footprints"]}
    out = []
    for e, r in sorted(tab.items()):
        T = V[m["F"][m["tri_surface"] == e]]
        if not len(T) or r["kind"] not in (1, 2):
            continue
        n = np.asarray(r["normal"], np.float64); n /= np.linalg.norm(n)
        c = T.reshape(-1, 3).mean(0)
        if r["kind"] == 2:
            n[2] = 0; n /= np.linalg.norm(n)
            cen = fps.get(r["building"])
            if cen is not None and np.dot(c[:2] - cen, n[:2]) < 0:
                n = -n
        elif n[2] < 0:
            n = -n
        out.append(dict(ext=int(e), kind=int(r["kind"]), building=r["building"], normal=n, tris=T, origin=c))
    return out


def in_tris(P2, T2, eps=1e-9):
    inside = np.zeros(len(P2), bool)
    for a, b, c in T2:
        v0, v1 = c - a, b - a; v2 = P2 - a
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        den = d00 * d11 - d01 * d01
        if abs(den) < 1e-12:
            continue
        d20, d21 = v2 @ v0, v2 @ v1
        u = (d11 * d20 - d01 * d21) / den; v = (d00 * d21 - d01 * d20) / den
        inside |= (u >= -eps) & (v >= -eps) & (u + v <= 1 + eps)
    return inside


def wall_axes(f):
    n = f["normal"]
    return n, np.array([-n[1], n[0], 0.0])


def wall_space(f, X):
    n, t = wall_axes(f); o = f["origin"]
    R_ = X - o; d = R_ @ n; s = R_ @ t
    T2 = np.stack([(f["tris"] - o) @ t, f["tris"][..., 2]], -1)
    lo, hi = T2.reshape(-1, 2).min(0), T2.reshape(-1, 2).max(0)
    m = (np.abs(d) <= H_M) & (s >= lo[0]) & (s <= hi[0]) & (X[:, 2] >= lo[1] + GAP) & (X[:, 2] <= hi[1] - GAP)
    idx = np.nonzero(m)[0]
    if len(idx):
        ok = in_tris(np.column_stack([s[idx], X[idx, 2] - GAP]), T2) & in_tris(np.column_stack([s[idx], X[idx, 2] + GAP]), T2)
        m[idx[~ok]] = False
    return m, d, s


def roof_axes(f):
    n = f["normal"]
    e1 = np.cross(n, [0.0, 0.0, 1.0]) if abs(n[2]) < 0.999 else np.array([1.0, 0.0, 0.0])
    e1 /= np.linalg.norm(e1); e2 = np.cross(n, e1)
    return n, e1, e2


def roof_space(f, X):
    n, e1, e2 = roof_axes(f); o = f["origin"]
    R_ = X - o; d = R_ @ n; a = R_ @ e1; b = R_ @ e2
    T2 = np.stack([(f["tris"] - o) @ e1, (f["tris"] - o) @ e2], -1)
    lo, hi = T2.reshape(-1, 2).min(0), T2.reshape(-1, 2).max(0)
    m = (np.abs(d) <= H_M) & (a >= lo[0]) & (a <= hi[0]) & (b >= lo[1]) & (b <= hi[1])
    idx = np.nonzero(m)[0]
    if len(idx):
        m[idx[~in_tris(np.column_stack([a[idx], b[idx]]), T2)]] = False
    return m, d, a, b


def face_area(f, site, step=0.05):
    o = f["origin"]
    if f["kind"] == 2:
        n, t = wall_axes(f); T2 = np.stack([(f["tris"] - o) @ t, f["tris"][..., 2]], -1); e1, e2, base = t, np.array([0, 0, 1.0]), np.array([o[0], o[1], 0])
    else:
        n, e1, e2 = roof_axes(f); T2 = np.stack([(f["tris"] - o) @ e1, (f["tris"] - o) @ e2], -1); base = o
    lo, hi = T2.reshape(-1, 2).min(0), T2.reshape(-1, 2).max(0)
    ga = np.arange(lo[0] + step / 2, hi[0], step); gb = np.arange(lo[1] + step / 2, hi[1], step)
    A, B = np.meshgrid(ga, gb, indexing="ij"); P2 = np.column_stack([A.ravel(), B.ravel()])
    if len(P2) > 4_000_000:
        step *= 2
        return face_area(f, site, step)
    ins = in_tris(P2, T2)
    X3 = base + P2[:, :1] * e1 + P2[:, 1:2] * e2
    ev = in_rect(X3[:, :2], site)
    if f["kind"] == 2:
        core = in_tris(P2 - [0, GAP], T2) & in_tris(P2 + [0, GAP], T2)
        return float((core & ev).sum() * step * step), float((ins & ev).sum() * step * step)
    return float((ins & ev).sum() * step * step), float((ins & ev).sum() * step * step)


def compass(n):
    az = (np.degrees(np.arctan2(n[0], n[1])) + 360.0) % 360.0
    return ["북", "북동", "동", "남동", "남", "남서", "서", "북서"][int(((az + 22.5) % 360) // 45)], float(az)


def cell_medians(k1, k2, d, cell=0.5, min_n=3):
    key = np.floor(k1 / cell).astype(np.int64) * 1000003 + np.floor(k2 / cell).astype(np.int64)
    o = np.argsort(key, kind="stable"); key, d = key[o], d[o]
    u, st, cn = np.unique(key, return_index=True, return_counts=True)
    return {int(a): float(np.median(d[s:s + c])) for a, s, c in zip(u, st, cn) if c >= min_n}


def diff_cells(A, B):
    both = sorted(set(A) & set(B))
    return np.array([A[k] - B[k] for k in both])


def vertical_points(X):
    sys.path.insert(0, "/repo/scripts/phd/main_stage1_v1"); sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1"); sys.path.insert(0, "/repo")
    import s04_gt_v7 as s4
    return s4.vertical_points(X)


def main(site):
    t0 = time.time()
    C = cfg(); FC = C["places"]["fig6"].get(site)
    src = {}
    for k in ("nadir", "manual", "fill"):
        z = np.load(PF / "crop" / site / f"{k}.npz")
        src[k] = dict(xyz=z["xyz"], rc=return_class(z["return_number"], z["number_of_returns"]), gps=z["gps_time"])
    vn = vertical_points(src["nadir"]["xyz"])
    src["gt_wall"] = dict(xyz=src["nadir"]["xyz"][vn & (src["nadir"]["rc"] == 0)])
    log(site, {k: len(v["xyz"]) for k, v in src.items()})
    faces = faces_of(site)
    walls = [f for f in faces if f["kind"] == 2]; roofs = [f for f in faces if f["kind"] == 1]
    ev = {k: in_rect(v["xyz"][:, :2], site) for k, v in src.items()}
    wall_rows, roof_rows = [], []
    pooled_w, pooled_r, pooled_wt = [], [], []
    tgt = TARGET.get(site)
    for f in walls:
        area, aface = face_area(f, site)
        if area <= 0.5:
            continue
        row = dict(ext=f["ext"], building=f["building"], area_space_m2=area, facing=compass(f["normal"])[0], azimuth=compass(f["normal"])[1])
        cells = {}
        for k in ("gt_wall", "manual", "fill", "nadir"):
            m, d, s = wall_space(f, src[k]["xyz"]); m &= ev[k]
            row[f"{k}_points"] = int(m.sum()); row[f"{k}_per_m2"] = float(m.sum() / area)
            sz = np.column_stack([s[m], src[k]["xyz"][m, 2]])
            occ = np.unique(np.floor(sz / 0.25).astype(np.int64), axis=0) if m.any() else np.zeros((0, 2))
            row[f"{k}_cells_0_25"] = int(len(occ)); row[f"{k}_cell_share"] = float(len(occ) * 0.0625 / area)
            if k in ("manual", "nadir"):
                cells[k] = cell_medians(s[m], src[k]["xyz"][m, 2], d[m])
        dd = diff_cells(cells["manual"], cells["nadir"])
        row["offset_cells"] = int(len(dd)); row["offset_median_m"] = float(np.median(dd)) if len(dd) else None; row["offset_nmad_m"] = nmad(dd) if len(dd) else None
        pooled_w.append(dd)
        if tgt and f["building"] == tgt:
            pooled_wt.append(dd)
        wall_rows.append(row)
    for f in roofs:
        area, _ = face_area(f, site)
        if area <= 0.5:
            continue
        row = dict(ext=f["ext"], building=f["building"], area_m2=area)
        cells = {}
        for k in ("nadir", "manual", "fill"):
            m, d, a, b = roof_space(f, src[k]["xyz"]); m &= ev[k]
            row[f"{k}_points"] = int(m.sum()); row[f"{k}_per_m2"] = float(m.sum() / area)
            if k in ("manual", "nadir"):
                cells[k] = cell_medians(a[m], b[m], d[m])
        dd = diff_cells(cells["manual"], cells["nadir"])
        row["offset_cells"] = int(len(dd)); row["offset_median_m"] = float(np.median(dd)) if len(dd) else None
        pooled_r.append(dd)
        roof_rows.append(row)
    def pool(lst):
        a = np.concatenate(lst) if lst else np.zeros(0)
        return dict(cells=int(len(a)), median_m=float(np.median(a)) if len(a) else None, nmad_m=nmad(a) if len(a) else None)
    tabB = dict(walls=pool(pooled_w), roofs=pool(pooled_r))
    if tgt:
        tabB["walls_target_building"] = pool(pooled_wt)
    roof_tot = {k: dict(points=int(sum(r[f"{k}_points"] for r in roof_rows)), per_m2=float(sum(r[f"{k}_points"] for r in roof_rows) / max(sum(r["area_m2"] for r in roof_rows), 1e-9)))
                for k in ("nadir", "manual", "fill")}
    log(site, "table B", tabB)
    # patches with GT, current vs + manual [approximation]
    pc = {}
    for prior in ("LoD2", "ALS"):
        Rf = S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz"
        if not Rf.exists():
            continue
        R = np.load(Rf); U = np.load(S0 / "s61/box" / site / prior / "units.npz")
        code = R["code_ext_v3"].astype(int); evp = R["in_eval"].astype(bool); kind = R["kind"].astype(int); gtn = R["gt_n"].astype(int)
        cen = R["centre"].astype(np.float64)
        Xm = src["manual"]["xyz"]
        cnt = np.zeros(len(code), np.int64)
        rr = np.nonzero(kind == 1)[0]
        if len(rr):
            tr = cKDTree(cen[rr][:, :2])
            dd_, jj = tr.query(Xm[:, :2], distance_upper_bound=0.18)
            ok = np.isfinite(dd_)
            owner = rr[jj[ok]]; zz = Xm[ok, 2]
            top = np.full(len(code), -np.inf); np.maximum.at(top, owner, zz)
            keep = zz >= top[owner] - 1.0
            np.add.at(cnt, owner[keep], 1)
        ww = np.nonzero(kind == 2)[0]
        if len(ww):
            vm = vertical_points(Xm)
            Xv = Xm[vm]
            t1 = U["loc_t1"].astype(np.float64); t2 = U["loc_t2"].astype(np.float64)
            nn_ = np.cross(t1, t2); nn_ /= np.maximum(np.linalg.norm(nn_, axis=1, keepdims=True), 1e-12)
            trw = cKDTree(cen[ww])
            dk, jk = trw.query(Xv, k=8, distance_upper_bound=2.02)
            assigned = np.full(len(Xv), -1, np.int64)
            for col in range(jk.shape[1]):
                okk = np.isfinite(dk[:, col]) & (assigned < 0)
                if not okk.any():
                    continue
                cand = ww[jk[okk, col]]
                r_ = Xv[okk] - cen[cand]
                okc = (np.abs((r_ * t1[cand]).sum(1)) <= 0.125) & (np.abs((r_ * t2[cand]).sum(1)) <= 0.125) & (np.abs((r_ * nn_[cand]).sum(1)) <= 2.0)
                idx_ = np.nonzero(okk)[0][okc]
                assigned[idx_] = cand[okc]
            np.add.at(cnt, assigned[assigned >= 0], 1)
        has_now = gtn >= 5; has_plus = has_now | (cnt >= 5)
        st = R["state"].astype(int)          # 0 invisible, 1 support, 2 missing (the patch's observation state; codes 4/13/5/14 need GT by definition)
        groups = {"모든 패치": np.ones(len(code), bool), "결측 패치(상태)": st == 2, "비가시 패치(상태)": st == 0, "지지 패치(상태)": st == 1,
                  "결측 영역(코드 4·13)": np.isin(code, [4, 13]), "비가시 영역(코드 5·14)": np.isin(code, [5, 14]), "지붕꼴": kind == 1, "벽꼴": kind == 2}
        pc[prior] = {g: dict(patches=int((evp & m).sum()), with_gt_now=int((evp & m & has_now).sum()), with_gt_plus_manual=int((evp & m & has_plus).sum()))
                     for g, m in groups.items()}
    gps = {k: dict(min=float(src[k]["gps"].min()), max=float(src[k]["gps"].max())) for k in ("nadir", "manual", "fill") if len(src[k]["gps"])}
    out = dict(site=site, walls=sorted(wall_rows, key=lambda r: -r["area_space_m2"]), roofs_total=roof_tot, roofs=roof_rows, table_B=tabB,
               patches_with_gt=pc, gps_seconds_of_week_adjusted=gps, points_box={k: int(len(v["xyz"])) for k, v in src.items()},
               rule=__doc__.split("\n\n")[1], made=now(), scientific_verdict=None)
    jdump(DOCS / "tables" / f"fig6_{site}.json", out)
    # figure 6
    if FC and site != "B0_b10":
        plt = G.setup_plt()
        from matplotlib.colors import LogNorm
        for fp in FC["faces"]:
            f = [x for x in walls if x["ext"] == fp["ext"]][0]
            n, t = wall_axes(f); o = f["origin"]
            T2 = np.stack([(f["tris"] - o) @ t, f["tris"][..., 2]], -1)
            lo, hi = T2.reshape(-1, 2).min(0), T2.reshape(-1, 2).max(0)
            es = np.arange(np.floor(lo[0] / 0.25) * 0.25, hi[0] + 0.25, 0.25); ez = np.arange(np.floor(lo[1] / 0.25) * 0.25, hi[1] + 0.25, 0.25)
            Hs = {}
            for k in ("gt_wall", "manual", "fill"):
                m, d, s = wall_space(f, src[k]["xyz"]); m &= ev[k]
                Hs[k] = np.histogram2d(s[m], src[k]["xyz"][m, 2], bins=[es, ez])[0]
            view = (fp.get("photo") or {}).get("view")
            bg = None
            if view:
                gs_ = np.arange(lo[0], hi[0], 0.05) + 0.025; gz = np.arange(lo[1], hi[1], 0.05) + 0.025
                SS, ZZ = np.meshgrid(gs_, gz)
                P3 = np.column_stack([o[0] + SS.ravel() * t[0], o[1] + SS.ravel() * t[1], ZZ.ravel()])
                u, v, zc = G.project(view, P3)
                ins = (zc > 0) & (u >= 0) & (u < 1024) & (v >= 0) & (v < 741)
                im = G.image(site, view)
                Dp = G.export(site, "LoD2", "prior", view)
                img = np.full((len(P3), 3), 0.82)
                iu = np.floor(u[ins]).astype(int); iv = np.floor(v[ins]).astype(int)
                okv = np.isfinite(Dp[iv, iu]) & (np.abs(zc[ins] - Dp[iv, iu]) <= 0.5)
                sel = np.nonzero(ins)[0][okv]
                img[sel] = im[iv[okv], iu[okv]] / 255.0
                bg = img.reshape(len(gz), len(gs_), 3)
            vmax = max(h.max() for h in Hs.values())
            fig, axs = plt.subplots(3, 1, figsize=(12, 3.2 * 3 + 1.2), constrained_layout=True)
            row = [r for r in wall_rows if r["ext"] == f["ext"]][0]
            labs = {"gt_wall": "(가) 지금 참값의 벽 점(연직 비행, 이 연구의 벽 규칙)", "manual": "(나) 수동 비행의 모든 점", "fill": "(다) 5 mm 처리본"}
            for ax, k in zip(axs, ("gt_wall", "manual", "fill")):
                if bg is not None:
                    ax.imshow(bg, extent=(lo[0], hi[0], lo[1], hi[1]), origin="lower", interpolation="nearest")
                Hm = np.ma.masked_equal(Hs[k], 0)
                im_ = ax.pcolormesh(es, ez, Hm.T, norm=LogNorm(vmin=1, vmax=max(vmax, 2)), cmap="viridis", shading="flat", alpha=0.85)
                ax.set_aspect("equal"); ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1])
                ax.text(0.01, 0.97, f"{labs[k]}\n{row[k + '_points']:,}점, {row[k + '_per_m2']:,.1f}점/m², 점이 있는 칸 {row[k + '_cell_share']*100:.0f} %", transform=ax.transAxes, va="top",
                        fontsize=9.5, bbox=dict(fc="w", ec="none", alpha=0.85))
                ax.set_ylabel("높이 (m)")
            axs[-1].set_xlabel("벽을 따라 (m; 바깥에서 본 오른쪽이 +)")
            cb = fig.colorbar(im_, ax=axs, shrink=0.6); cb.set_label("0.25 m 칸의 점 수(로그)")
            ttl = "수동 비행이 B173 주변과 R1의 벽을 지금 참값보다 얼마나 더 덮는가"
            fig.suptitle(f"{ttl} — {'B173 주변' if site == 'B173nb_b10' else 'R1'} 벽면 {f['ext']}({row['facing']}향, 공간 {row['area_space_m2']:.0f} m²)", fontsize=12.5)
            lab_place = "넓이가 가장 큰 벽면" if fp["ext"] == FC["largest"]["ext"] else "결측 패치가 가장 많은 벽면"
            if FC["largest"]["ext"] == FC["most_missing"]["ext"]:
                lab_place = "넓이가 가장 크고 결측 패치도 가장 많은 벽면"
            offs = "—" if row["offset_median_m"] is None else f"{row['offset_median_m'] * 1000:+.1f} mm"
            line = (f"{lab_place} · 지금 참값 {row['gt_wall_per_m2']:.1f} · 수동 비행 {row['manual_per_m2']:.1f} · 5 mm 처리본 {row['fill_per_m2']:.1f} 점/m² · "
                    f"두 비행의 어긋남(수동 − 연직) {offs} ({row['offset_cells']}칸) · 바탕 = {view} 영상을 벽면에 편 것")
            fig.text(0.01, -0.01, line, fontsize=8.5)
            G.locator(fig, site, o[:2], rect=(0.9, 0.93, 0.08, 0.06))
            nm = f"photo_fig6_{'b173nb' if site == 'B173nb_b10' else 'r1'}_wall{f['ext']}"
            for ext in ("png", "pdf"):
                fig.savefig(DOCS / "figures" / f"{nm}.{ext}", dpi=140, bbox_inches="tight")
            plt.close(fig)
            jdump(DOCS / "figures" / f"{nm}.json", dict(face=row, numbers_line=line, photo=view, made=now(), scientific_verdict=None))
    log(site, "done", round(time.time() - t0, 1))


if __name__ == "__main__":
    for s in sys.argv[1:]:
        main(s)

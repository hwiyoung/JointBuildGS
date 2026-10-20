"""PHD-MAIN-FIXTEST-v1 일 7 step 1: why the upper-left triangle of the B173nb_b10 LoD2 face 53 looks like a checkerboard in
docs/experiments/phd/main_fill_v1/figures/items/unseen_1.png (jointbuildgs:dev, CPU; no training, no GPU, no render).
  bash run_item7.sh cause cause.py
Reads (all read only): S1/defs/fig_views_v1.json 'unseen_face' (the place), S1/defs/<site>/unseen.npz (the unseen patch set the figure
draws), S0/s61/box/<site>/LoD2/units.npz (every cell of the face: state, n_seeing, grid frame), unit_view_pairs.npz (which training view
put pixels on which cell), S0/s61/export/<site>/LoD2/locmap/<view>.npy (the location of every pixel of that view), the fork scene's
cameras/poses, S1/regions_v3 (area, in_eval), the LoD2 mesh (DR/s02_box), SL/work/virtual/metrics/<site>/wall_flags_LoD2.npz and
<result>__LoD2.json (the fill task's wall-present flags and values).
Writes: /item7/cause.json (every number), /item7/cause_cells.npz (per cell of the face), /item7/view_hits.npz (the view's pixel hits).
Region 'T' (the triangle) = the cells of the face that a training view sees: the cell centre projects into that view on a pixel whose
location (locmap) is a cell of the same face. scientific_verdict: null."""
import numpy as np
from scipy.spatial import cKDTree

import item7_common as I


def nn_stats(sz):
    """nearest-neighbour distance between patch centres (s, z) of one region."""
    if len(sz) < 2:
        return None
    d, _ = cKDTree(sz).query(sz, k=2)
    d = d[:, 1]
    return dict(n=int(len(d)), median_m=float(np.median(d)), mean_m=float(d.mean()),
                share_0_25=float((d <= 0.26).mean()), share_0_35=float(((d > 0.34) & (d <= 0.36)).mean()),
                share_0_5_or_more=float((d >= 0.49).mean()))


def main():
    T = I.Timer()
    w, un, face = I.wall_place()
    c0, t, nrm = I.frame(w)
    FACE = int(w["surf_ext"])
    U = np.load(I.BOX / "units.npz")
    R = np.load(I.S1 / "regions_v3" / f"regions_ext_v3_{I.SITE}_LoD2.npz")
    P = np.load(I.BOX / "unit_view_pairs.npz")
    se = U["surf_ext"][U["loc_surface"]]
    nL = len(se)
    f53 = np.nonzero(se == FACE)[0]
    pos = np.full(nL + 1, -1, np.int64)          # pos[-1] stays -1 for locmap's -1
    pos[f53] = np.arange(len(f53))
    X = U["loc_center"][f53]
    s, z = (X - c0) @ t, X[:, 2]
    pu = un["patch"][face]
    li_u = un["label_inferred"][face]
    in_set = np.zeros(len(f53), bool)
    in_set[pos[pu]] = True
    li = np.full(len(f53), -9, np.int8)
    li[pos[pu]] = li_u
    state, nsee = U["state"][f53], U["n_seeing"][f53]
    out = dict(task_id="PHD-MAIN-FIXTEST-v1", item="일 7", step="cause", site=I.SITE, face=FACE, mark="[이 발주에서 냄]",
               place=dict(source="S1/defs/fig_views_v1.json sites.B173nb_b10.unseen_face", **w), scientific_verdict=None)
    out["face_cells"] = dict(all=int(len(f53)), unseen_set=int(in_set.sum()), not_in_unseen_set=int((~in_set).sum()),
                             state={I_: int((state == v).sum()) for I_, v in (("invisible", 0), ("support", 1), ("missing", 2))},
                             n_seeing={str(int(k)): int(v) for k, v in zip(*np.unique(nsee, return_counts=True))},
                             unseen_set_equals_invisible=bool(np.array_equal(in_set, state == 0)),
                             unseen_file_patches_all_faces=int(len(un["patch"])), source="S0/s61/box/B173nb_b10/LoD2/units.npz; S1/defs/B173nb_b10/unseen.npz")
    # ---------------- the store's cell grid of the face (one grid? axes against the drawing's s and z?)
    sidx = np.nonzero(U["surf_ext"] == FACE)[0]
    sp = float(U["sp"])
    grids = []
    for k in sidx:
        m = U["loc_surface"][f53] == k
        o, e1, e2 = U["o"][k], U["e1"][k], U["e2"][k]
        uu, vv = (X[m] - o) @ e1 / sp, (X[m] - o) @ e2 / sp
        grids.append(dict(store_surface=int(k), cells=int(m.sum()), o=o, e1=e1, e2=e2, cell_m=sp,
                          angle_e1_to_drawing_s_deg=float(np.degrees(np.arccos(min(1.0, abs(float(e1 @ t)))))),
                          angle_e2_to_vertical_deg=float(np.degrees(np.arccos(min(1.0, abs(float(e2[2])))))),
                          centre_offset_in_cell_u=[float((uu - np.floor(uu)).min()), float((uu - np.floor(uu)).max())],
                          centre_offset_in_cell_v=[float((vv - np.floor(vv)).min()), float((vv - np.floor(vv)).max())]))
    out["store_grid"] = dict(surfaces_with_ext=int(len(sidx)), grids=grids)
    # ---------------- the LoD2 mesh triangles of the face (which triangle each cell centre lies on)
    M = np.load(I.DR / "s02_box" / I.SITE / "lod2_mesh.npz")
    tm = np.nonzero(M["tri_surface"] == FACE)[0]
    o, e1, e2 = U["o"][sidx[0]], U["e1"][sidx[0]], U["e2"][sidx[0]]
    uvc = np.stack([(X - o) @ e1, (X - o) @ e2], 1)
    tri_of = np.full(len(f53), -1, np.int64)
    tri_rows = []
    for k in tm:
        Vt = M["V"][M["F"][k]]
        uvt = np.stack([(Vt - o) @ e1, (Vt - o) @ e2], 1)
        a, b, c = uvt
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        l1 = ((b[1] - c[1]) * (uvc[:, 0] - c[0]) + (c[0] - b[0]) * (uvc[:, 1] - c[1])) / den
        l2 = ((c[1] - a[1]) * (uvc[:, 0] - c[0]) + (a[0] - c[0]) * (uvc[:, 1] - c[1])) / den
        ins = (l1 >= -1e-9) & (l2 >= -1e-9) & (1 - l1 - l2 >= -1e-9) & (tri_of < 0)
        tri_of[ins] = k
        sv = (Vt - c0) @ t
        tri_rows.append(dict(triangle=int(k), tri_type=int(M["tri_type"][k]), vertices_s_z=np.stack([sv, Vt[:, 2]], 1).round(3).tolist(),
                             cells=int(ins.sum())))
    T.mark("grid and triangles")
    # ---------------- which training views put pixels on the face, and how
    pm = pos[P["loc"]] >= 0
    pv, pl, npx = P["view"][pm], P["loc"][pm], P["npix"][pm]
    names = [str(n) for n in P["views"]]
    views = []
    cams = I.Cameras()
    T_mask = np.zeros(len(f53), bool)
    hits_s, hits_z, hits_cell, hits_view = [], [], [], []
    for vi in np.unique(pv):
        name = names[int(vi)]
        stem = name.rsplit(".", 1)[0]
        mv = pv == vi
        lm = np.load(I.EXPORT / "locmap" / f"{stem}.npy")
        on = (lm >= 0) & (pos[np.where(lm >= 0, lm, nL)] >= 0)
        rr, cc = np.nonzero(on)
        loc_px = lm[rr, cc]
        Cc = cams.C(stem)
        o_pl = U["o"][sidx[0]]

        def hit(r_, c_):
            d = cams.rays(stem, r_, c_)
            lam = ((o_pl - Cc) @ nrm) / (d @ nrm)
            return Cc + lam[:, None] * d, d

        Xh, d = hit(rr, cc)
        Xr, _ = hit(rr, cc + 1)
        Xd, _ = hit(rr + 1, cc)
        sz = lambda A: np.stack([(A - c0) @ t, A[:, 2]], 1)  # noqa: E731
        Sh, Sr, Sd = sz(Xh), sz(Xr), sz(Xd)
        a_, b_ = Sr - Sh, Sd - Sh
        area = np.abs(a_[:, 0] * b_[:, 1] - a_[:, 1] * b_[:, 0])
        dist = np.linalg.norm(Xh - Cc, axis=1)
        inc = np.degrees(np.arccos(np.clip(np.abs((d / np.linalg.norm(d, axis=1, keepdims=True)) @ nrm), 0, 1)))
        # the plane hit's own cell against the locmap's cell (does the pixel land where the store says?)
        uu = np.floor((Xh - o_pl) @ e1 / sp).astype(np.int64) - U["i0"][sidx[0]]
        vv = np.floor((Xh - o_pl) @ e2 / sp).astype(np.int64) - U["j0"][sidx[0]]
        okg = (uu >= 0) & (uu < U["ni"][sidx[0]]) & (vv >= 0) & (vv < U["nj"][sidx[0]])
        cell_plane = np.full(len(uu), -1, np.int64)
        cell_plane[okg] = U["member"][U["off"][sidx[0]] + uu[okg] * U["nj"][sidx[0]] + vv[okg]]
        # the cells whose centre this view sees on the face (region T of this view)
        u, v, zc = cams.project(stem, X)
        ok = (zc > 0) & (u >= 0) & (u < I.GRID_W) & (v >= 0) & (v < I.GRID_H)
        tv = np.zeros(len(f53), bool)
        lmv = lm[np.floor(v[ok]).astype(int), np.floor(u[ok]).astype(int)]
        tv[np.nonzero(ok)[0]] = pos[np.where(lmv >= 0, lmv, nL)] >= 0
        T_mask |= tv
        # what this view shows where it does not see the face (the cells of the face outside its region): surface and building
        tab = {r_["ext"]: r_ for r_ in I.jload(I.DR / "s02_box" / I.SITE / "lod2_surfaces.json")["surfaces"]}
        oth = ok & ~tv
        lmo = lm[np.floor(v[oth]).astype(int), np.floor(u[oth]).astype(int)]
        ext_o = np.where(lmo >= 0, se[np.maximum(lmo, 0)], -1)
        occl = {}
        for e_, n_ in zip(*np.unique(ext_o, return_counts=True)):
            r_ = tab.get(int(e_), {})
            occl[str(int(e_))] = dict(cells=int(n_), type=r_.get("type"), building=r_.get("building"),
                                      normal=r_.get("normal"))
        cells_hit = np.unique(pos[loc_px])
        cnt = np.bincount(pos[loc_px], minlength=len(f53))[cells_hit]
        views.append(dict(view=name, pairs_on_face=int(mv.sum()), pixels_on_face=int(len(rr)), pixels_on_face_pairs=int(npx[mv].sum()),
                          cells_hit=int(len(cells_hit)), pixels_per_hit_cell={str(int(k)): int(v_) for k, v_ in zip(*np.unique(cnt, return_counts=True))},
                          cells_whose_centre_it_sees=int(tv.sum()), share_of_those_cells_hit=float(np.isin(np.nonzero(tv)[0], cells_hit).mean()) if tv.any() else None,
                          camera_centre=Cc, distance_m=dict(median=float(np.median(dist)), min=float(dist.min()), max=float(dist.max())),
                          incidence_deg_from_wall_normal=dict(median=float(np.median(inc)), min=float(inc.min()), max=float(inc.max())),
                          pixel_footprint_m2=dict(median=float(np.median(area)), p10=float(np.percentile(area, 10)), p90=float(np.percentile(area, 90))),
                          cells_per_pixel_median=float(np.median(area) / (sp * sp)),
                          pixel_step_on_wall_m=dict(along_image_row=dict(ds=float(np.median(np.abs(a_[:, 0]))), dz=float(np.median(np.abs(a_[:, 1])))),
                                                    along_image_column=dict(ds=float(np.median(np.abs(b_[:, 0]))), dz=float(np.median(np.abs(b_[:, 1]))))),
                          plane_hit_cell_equals_locmap_cell=float((cell_plane == loc_px).mean()),
                          face_cells_in_image_outside_region=int(oth.sum()), face_cells_outside_image=int((~ok).sum()),
                          hidden_cells_s_range=[float(s[oth].min()), float(s[oth].max())] if oth.any() else None,
                          hidden_cells_z_range=[float(z[oth].min()), float(z[oth].max())] if oth.any() else None,
                          what_the_view_shows_there=dict(rule="locmap location's LoD2 surface (ext; -1 = no prior surface) at the cell centre's "
                                                              "pixel", surfaces=occl)))
        hits_s.append(Sh[:, 0]); hits_z.append(Sh[:, 1]); hits_cell.append(pos[loc_px]); hits_view.append(np.full(len(rr), int(vi)))
    out["views_on_face"] = views
    T.mark("views")
    seen = state != 0
    out["seen_cells_outside_T"] = int((seen & ~T_mask).sum())
    # ---------------- region numbers: T (the triangle) and the rest of the face
    area = R["area"][f53]
    rows = {}
    for nm, m in (("T", T_mask), ("rest", ~T_mask), ("face", np.ones(len(f53), bool))):
        a_m2 = float(area[m].sum())
        ms = m & in_set
        rows[nm] = dict(cells=int(m.sum()), area_m2=a_m2, area_share_of_face=float(a_m2 / area.sum()),
                        s_range=[float(s[m].min()), float(s[m].max())] if m.any() else None,
                        z_range=[float(z[m].min()), float(z[m].max())] if m.any() else None,
                        seen_by_a_training_view=int((m & seen).sum()), seen_share=float((m & seen).mean() / max(m.mean(), 1e-12)),
                        unseen_set_patches=int(ms.sum()), unseen_set_per_m2=float(ms.sum() / a_m2) if a_m2 else None,
                        cells_per_m2=float(m.sum() / a_m2) if a_m2 else None,
                        label_inferred={k: int((ms & (li == v)).sum()) for k, v in (("0 맞음으로 미룸(셈)", 0), ("1 지금 지붕보다 위", 1), ("2 모호", 2))},
                        counted_li0_per_m2=float((ms & (li == 0)).sum() / a_m2) if a_m2 else None,
                        patch_area_m2=dict(min=float(area[m].min()), max=float(area[m].max())) if m.any() else None,
                        in_eval_share=float(R["in_eval"][f53][m].mean()) if m.any() else None,
                        nn_spacing_unseen_set=nn_stats(np.stack([s[ms], z[ms]], 1)),
                        nn_spacing_all_cells=nn_stats(np.stack([s[m], z[m]], 1)),
                        lod2_triangle={str(int(k)): int((m & (tri_of == k)).sum()) for k in np.unique(tri_of[m])} if m.any() else {})
    out["regions"] = rows
    out["lod2_triangles_of_face"] = tri_rows
    # checkerboard measure: unseen-set cells among the 4 raster neighbours of an unseen-set cell (perfect checkerboard 0, full 4)
    gi = np.floor((z - z.min()) / sp + 0.5).astype(int)
    gj = np.floor((s - s.min()) / sp + 0.5).astype(int)
    Hh, Ww = gi.max() + 3, gj.max() + 3
    occ = np.zeros((Hh, Ww), bool)
    occ[gi[in_set] + 1, gj[in_set] + 1] = True
    face_r = np.zeros((Hh, Ww), bool)
    face_r[gi + 1, gj + 1] = True
    nb = np.zeros(len(f53), int)
    nface = np.zeros(len(f53), int)
    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nb += occ[gi + 1 + di, gj + 1 + dj]
        nface += face_r[gi + 1 + di, gj + 1 + dj]
    inner = nface == 4
    for nm, m in (("T", T_mask), ("rest", ~T_mask)):
        mm = m & in_set & inner
        rows[nm]["unseen_set_4_neighbours_in_set"] = dict(mean=float(nb[mm].mean()) if mm.any() else None,
                                                         share_0=float((nb[mm] == 0).mean()) if mm.any() else None,
                                                         share_4=float((nb[mm] == 4).mean()) if mm.any() else None, cells=int(mm.sum()))
    # ---------------- the unseen split's label rule (scripts/phd/main_stage1_v1/regions_v3.py unseen_split, lines 70-105) for the cells
    # outside the set (only for the sensitivity of step 4): the current top behind a cell depends on its x, y only, so every cell of a
    # column of the face (same store index along e1) has the top of the set's cells of that column; d = z - top, tau_w = median tau of
    # the whole unseen set; label 1 above +tau_w, 0 below -tau_w, 2 within.
    top_all = R["unseen_top_behind"][f53].astype(np.float64)
    tau_w = float(np.median(R["tau"][R["unseen_label_inferred"] > -2]))
    ci = np.floor((X - o) @ e1 / sp).astype(np.int64)
    k0 = ci - ci.min()
    m_ = in_set & np.isfinite(top_all)
    tmin, tmax = np.full(k0.max() + 1, np.inf), np.full(k0.max() + 1, -np.inf)
    np.minimum.at(tmin, k0[m_], top_all[m_])
    np.maximum.at(tmax, k0[m_], top_all[m_])
    top_c = np.where(np.isfinite(tmin), tmin, np.nan)[k0]
    d_ = z - top_c
    li_rule = np.full(len(f53), -1, np.int8)
    li_rule[d_ > tau_w] = 1
    li_rule[d_ < -tau_w] = 0
    li_rule[np.abs(d_) <= tau_w] = 2
    out["label_rule_for_cells_outside_set"] = dict(
        source="scripts/phd/main_stage1_v1/regions_v3.py unseen_split lines 70-105; top = S1/regions_v3 unseen_top_behind of the same column",
        tau_w=tau_w, columns=int(len(np.unique(k0))), columns_with_top=int(np.isfinite(tmin).sum()),
        top_constant_in_column=bool(np.all((tmax - tmin)[np.isfinite(tmin)] <= 1e-6)),
        rule_reproduces_set_labels=bool(np.array_equal(li_rule[in_set], li[in_set])),
        cells_outside_set=int((~in_set).sum()), outside_set_without_top=int((~in_set & ~np.isfinite(top_c)).sum()),
        outside_set_labels={k: int((~in_set & (li_rule == v)).sum()) for k, v in (("0", 0), ("1", 1), ("2", 2), ("-1 no top", -1))})
    # ---------------- the drawing of the fill task: one raster cell per patch? empty raster cells inside the face?
    cf = un["centre"][face].astype(np.float64)
    su, zu = (cf - c0) @ t, cf[:, 2]
    ri, rj, shape, ext = I.wall_grid(su, zu)
    s0, z0 = ext[0], ext[2]
    ai = np.floor((z - z0) / I.CELL).astype(int)
    aj = np.floor((s - s0) / I.CELL).astype(int)
    lin_u = ri * shape[1] + rj
    lin_a = ai * shape[1] + aj
    fr_s, fr_z = (s - s0) / I.CELL - aj, (z - z0) / I.CELL - ai
    out["drawing"] = dict(source="scripts/phd/main_fill_v1/figs_fl_walls.py draw() lines 84-165 (wall_grid lines 25-31, binning lines 89-92, "
                                 "imshow line 134)", raster_shape=list(shape), extent=list(ext),
                          patches_drawn=int(len(su)), raster_cells_filled=int(len(np.unique(lin_u))),
                          raster_cells_with_two_or_more_patches=int((np.bincount(lin_u) > 1).sum()),
                          face_cells_to_distinct_raster_cells=bool(len(np.unique(lin_a)) == len(lin_a)),
                          face_cells_left_transparent=int(len(np.setdiff1d(lin_a, lin_u))),
                          transparent_cells_are_the_seen_cells=bool(np.array_equal(np.sort(np.setdiff1d(lin_a, lin_u)), np.sort(lin_a[~in_set]))),
                          centre_offset_in_raster_cell_s=[float(fr_s.min()), float(fr_s.max())],
                          centre_offset_in_raster_cell_z=[float(fr_z.min()), float(fr_z.max())],
                          transparent_reads_as="white = the colour of '없음' (img alpha 0 over the white axes)")
    # ---------------- the wall-present value (0.25 m) recomputed from the fill task's flags, overall and by region
    fl = np.load(I.VW / "wall_flags_LoD2.npz")
    Tu = T_mask[pos[pu]]
    vals = {}
    for res in ("prop_LoD2_s0", "prop_LoD2_s1", "imgonly_2dgs_s0", "trust_LoD2_fix1"):
        f = fl[res].astype(bool)
        cnt = li_u == 0
        js = I.jload(I.VW / f"{res}__LoD2.json")["wall"]
        vals[res] = dict(recomputed=dict(share=float(f[cnt].mean()), present=int(f[cnt].sum()), patches=int(cnt.sum())),
                         fill_json=dict(share=js["share"], present=js["present"], patches=js["patches"],
                                        source=f"SL/work/virtual/metrics/B173nb_b10/{res}__LoD2.json 'wall'"),
                         same=bool(int(f[cnt].sum()) == js["present"] and int(cnt.sum()) == js["patches"]),
                         T=dict(share=float(f[cnt & Tu].mean()), present=int(f[cnt & Tu].sum()), patches=int((cnt & Tu).sum())),
                         rest=dict(share=float(f[cnt & ~Tu].mean()), present=int(f[cnt & ~Tu].sum()), patches=int((cnt & ~Tu).sum())))
    out["wall_present"] = dict(flags_source="SL/work/virtual/metrics/B173nb_b10/wall_flags_LoD2.npz (order = unseen.npz patches of face 53)",
                               rule="virtual-view mesh within 0.25 m of the patch centre; share over label_inferred 0", values=vals)
    out["seconds"] = T.marks
    I.jdump(I.OUT / "cause.json", out)
    np.savez_compressed(I.OUT / "cause_cells.npz", loc=f53, s=s, z=z, centre=X, in_set=in_set, li=li, li_rule=li_rule, state=state,
                        n_seeing=nsee, T=T_mask, tri=tri_of, raster_i=ai, raster_j=aj)
    np.savez_compressed(I.OUT / "view_hits.npz", s=np.concatenate(hits_s), z=np.concatenate(hits_z), cell=np.concatenate(hits_cell),
                        view=np.concatenate(hits_view), view_names=np.array(names))
    T.mark("write")
    I.log("cause done", T.marks)
    import json
    print(json.dumps({k: out[k] for k in ("face_cells", "store_grid", "seen_cells_outside_T", "drawing", "label_rule_for_cells_outside_set")},
                     indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    print(json.dumps(out["views_on_face"], indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    print(json.dumps(out["regions"], indent=1, ensure_ascii=False))
    print(json.dumps(out["lod2_triangles_of_face"], indent=1))
    print(json.dumps(out["wall_present"], indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()

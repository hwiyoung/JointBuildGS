"""PHD-MAIN-PHOTOFIG-v1 figure 2: the missing patches around the glass skylight of B173 주변 (항공 LiDAR). Where did the result surface
on them come from, and what did 결측 지키기 change? Place, photo (= figure 1's vertical photo) and section from the locked config.
(jointbuildgs:dev, CPU)

  python f2_missing.py   -> /docs/tables/fig2_patches.md|json, /pf/proj/fig2_*.npz

Per missing patch (code 4 or 13) in the glass place (case + 2 m band; places.fig2.missing_patches) and, as extra lines, the other
missing patches of the evaluation range: in_eval, place; the borrowed judgment and neighbours of the current method (SL/work/undecidable/
borrow_B173nb_b10_ALS.npz, the fork's propagation); the judgment of 결측 지키기 (FT/checks/dry/r16B_.../locations.npz 'judgment',
'judgment_before_own_depth', 'own_depth_changed'); GT rows and the signed GT->result distances (dist files r_*); the result surface height
at the patch centre and at the nearest glass (case) patch centre (TSDF mesh, vertical ray) and the GT top at both; the Gaussians located
on the patch in the 30,000-iteration dump (origin, shared initial point), the prior-born initial points near the patch and the iteration
they were removed at; the new depth-term pixels (r16B - r16d gate maps, all training views) and the extra planted points (init_points
'planted' r16B - r16d). [이 발주에서 냄] scientific_verdict: null"""
import time

import numpy as np
from scipy.spatial import cKDTree

import pf_geo as G
from pf_common import DOCS, FT, PF, S0, S1, SD, SL, S2, cfg, jdump, log, now

SITE, PRIOR = "B173nb_b10", "ALS"
RUNS = {"지금 방법 씨앗 0": S0 / "stage0/b1_ALS", "지금 방법 씨앗 1": S0 / "stage0/b2_ALS", "결측 지키기": FT / "runs/B173nb_b10/fixB_ALS_s0"}
DIST = {"지금 방법 씨앗 0": SD / "dist/B173nb_b10_ALS__prop_ALS_s0.npz", "지금 방법 씨앗 1": SD / "dist/B173nb_b10_ALS__prop_ALS_s1.npz",
        "결측 지키기": FT / "dist/B173nb_b10_ALS__fixB_ALS_s0.npz"}
JNAME = {-1: "없음", 0: "충돌", 1: "일치", 2: "섞임", 3: "모자람"}
PLACE = {4: "사전 정보가 맞는 결측 패치", 13: "사전 정보가 틀린 결측 패치"}


def main():
    t0 = time.time()
    C = cfg(); P = C["places"]["fig2"]; P1 = C["places"]["fig1"]
    R = np.load(S1 / "regions_v3" / f"regions_ext_v3_{SITE}_{PRIOR}.npz")
    U = np.load(S0 / "s61/box" / SITE / PRIOR / "units.npz")
    code = R["code_ext_v3"].astype(int); ev = R["in_eval"].astype(bool)
    mis = np.array(P["missing_patches"], int)
    extra = np.array([i for i in P["missing_in_eval_all"] if i not in set(mis.tolist())], int)
    allp = np.concatenate([mis, extra])
    case = np.array(P1["case_patches"], int)
    cen = R["centre"].astype(np.float64)
    B = np.load(SL / "work/undecidable/borrow_B173nb_b10_ALS.npz")
    bpos = {int(m): i for i, m in enumerate(B["mis"])}
    LB = np.load(FT / "checks/dry/r16B_B173nb_b10_ALS/model/monitor/locations.npz")
    LD = np.load(FT / "checks/dry/r16d_B173nb_b10_ALS/model/monitor/locations.npz")
    D = {k: np.load(v) for k, v in DIST.items()}
    xb = P1["place_xy_box"]
    meshes = {}
    for k, r in RUNS.items():
        V, F, info = G.read_ply_mesh_box(r / "post/mesh_tsdf.ply", xb, margin=5.0)
        meshes[k] = (V, F); log("mesh", k, info)
    Xg, _, _ = G.gt_points(SITE, xb, margin=3.0)
    tg = cKDTree(Xg[:, :2])
    def gtop(xy):
        out = np.full(len(xy), np.nan)
        for i, l in enumerate(tg.query_ball_point(xy, r=0.25)):
            if len(l) >= 3:
                z = Xg[l, 2]; out[i] = np.median(z[z >= z.max() - 0.5])
        return out
    tc = cKDTree(cen[case][:, :2])
    dn, jn = tc.query(cen[allp][:, :2])
    nb = case[jn]
    zres = {k: (G.raycast_top(V, F, cen[allp][:, :2]), G.raycast_top(V, F, cen[nb][:, :2])) for k, (V, F) in meshes.items()}
    # boundary step (config reading 'fig2'): at the midpoint of the two centres, 0.05 m into each side
    dvec = cen[nb][:, :2] - cen[allp][:, :2]
    dvec /= np.maximum(np.linalg.norm(dvec, axis=1, keepdims=True), 1e-9)
    mid = 0.5 * (cen[nb][:, :2] + cen[allp][:, :2])
    zb = {k: (G.raycast_top(V, F, mid - 0.05 * dvec), G.raycast_top(V, F, mid + 0.05 * dvec)) for k, (V, F) in meshes.items()}
    gt_a, gt_b = gtop(cen[allp][:, :2]), gtop(cen[nb][:, :2])
    # Gaussians in the dumps
    dumps = {}
    for k, r in RUNS.items():
        z = np.load(r / "model/dump/iteration_30000/gaussians.npz")
        loc = z["location"]; ii = z["init_id"]
        cnt = np.bincount(ii[ii >= 0], minlength=int(ii.max()) + 1)
        dumps[k] = dict(loc=loc, origin=z["origin"], shared=(ii >= 0) & (cnt[np.maximum(ii, 0)] > 1), init_xyz=z["init_xyz"].astype(np.float64),
                        init_origin=z["init_origin"], removed=z["init_removed_at"])
    # new depth-term pixels and extra planted points (pre-training records of 결측 지키기 vs the default)
    gB = np.load(FT / "checks/dry/r16B_B173nb_b10_ALS/model/monitor/gate_check.npz")
    gD = np.load(FT / "checks/dry/r16d_B173nb_b10_ALS/model/monitor/gate_check.npz")
    newpix = np.zeros(len(code), np.int64); vview = P["photo"]; new_in_photo = None
    for kk in gB.files:
        if not kk.startswith("g_"):
            continue
        n = kk[2:]
        nw = gB[kk] & ~gD[kk]
        if nw.any():
            lm = gB["lm_" + n]
            np.add.at(newpix, lm[nw][lm[nw] >= 0], 1)
        if n == vview:
            new_in_photo = np.column_stack(np.nonzero(nw))
    iB = np.load(FT / "checks/dry/r16B_B173nb_b10_ALS/model/monitor/init_points.npz")
    iD = np.load(FT / "checks/dry/r16d_B173nb_b10_ALS/model/monitor/init_points.npz")
    nD = len(iD["planted"])
    plantB = iB["planted"].copy()
    extra_plant = np.nonzero(plantB[:nD] & ~iD["planted"])[0].tolist() + [nD + i for i in np.nonzero(plantB[nD:])[0]]
    ep_xyz = iB["xyz"][extra_plant].astype(np.float64) if len(extra_plant) else np.zeros((0, 3))
    ep_loc = iB["location"][extra_plant] if len(extra_plant) else np.zeros(0, int)
    zb_ = zb
    rows = []
    for j, p in enumerate(allp):
        e = dict(patch=int(p), place=PLACE.get(int(code[p]), str(code[p])), code=int(code[p]), in_eval=bool(ev[p]), in_glass_place=bool(j < len(mis)),
                 centre=cen[p].round(3).tolist(), gt_rows=0)
        if int(p) in bpos:
            i = bpos[int(p)]
            e["borrowed_judgment"] = JNAME.get(int(B["J_mis"][i]), str(B["J_mis"][i]))
            e["borrowed_neighbours"] = [int(x) for x in B["borrowed"][i] if x >= 0]
            e["borrowed_votes"] = [JNAME.get(int(x), str(x)) for x in B["borrowed_vote"][i]]
            e["neighbour_places"] = [PLACE.get(int(code[x]), {3: "맞는 자료를 판단할 수 없는 곳" if R["premise_violation"][x] else "영상이 틀린 곳(문턱 안)", 2: "두 자료가 모두 맞는 곳"}.get(int(code[x]), str(int(code[x])))) for x in B["borrowed"][i] if x >= 0]
        e["judgment_current_dry"] = JNAME.get(int(LD["judgment"][p]), str(LD["judgment"][p]))
        e["judgment_fixB"] = JNAME.get(int(LB["judgment"][p]), str(LB["judgment"][p]))
        e["judgment_fixB_before_own_depth"] = JNAME.get(int(LB["judgment_before_own_depth"][p]), str(LB["judgment_before_own_depth"][p]))
        e["own_depth_changed"] = bool(LB["own_depth_changed"][p])
        for k, d in D.items():
            m = d["r_patch"] == p
            e["gt_rows"] = int(m.sum())
            if m.any():
                sd = d["r_d"][m].astype(np.float64) * np.where(d["r_sign"][m] == 0, 1, d["r_sign"][m])
                e[f"dist_{k}"] = dict(median_abs_m=float(np.median(np.abs(sd))), median_signed_m=float(np.median(sd)), within_0_2m=float(np.mean(np.abs(sd) <= 0.2)))
        e["neighbour_glass_patch"] = int(nb[j]); e["neighbour_distance_m"] = float(dn[j])
        e["gt_top_patch_m"] = float(gt_a[j]); e["gt_top_neighbour_m"] = float(gt_b[j])
        for k in RUNS:
            za, zb = zres[k][0][j], zres[k][1][j]
            e[f"surface_{k}"] = dict(patch_z=float(za), neighbour_z=float(zb), step_m=float(za - zb), minus_gt_patch_m=float(za - gt_a[j]),
                                     boundary_step_m=float(zb_[k][0][j] - zb_[k][1][j]))
            dd = dumps[k]
            g = dd["loc"] == p
            ip = (np.abs(dd["init_xyz"][:, :2] - cen[p][:2]).max(1) <= 0.125) & (np.abs(dd["init_xyz"][:, 2] - cen[p][2]) <= 1.0) & (dd["init_origin"] == 1)
            rem = dd["removed"][ip]
            e[f"gauss_{k}"] = dict(n=int(g.sum()), prior_born=int((g & (dd["origin"] == 1)).sum()), image_born=int((g & (dd["origin"] == 0)).sum()),
                                   sharing_initial_point=int((g & dd["shared"]).sum()), prior_initial_points=int(ip.sum()), removed=int((rem >= 0).sum()),
                                   removed_at=sorted(int(x) for x in rem[rem >= 0])[:10])
        e["new_depth_pixels_fixB"] = int(newpix[p])
        e["extra_planted_points_fixB"] = int((ep_loc == p).sum())
        rows.append(e)
    np.savez_compressed(PF / "proj/fig2_records.npz", new_in_photo=new_in_photo if new_in_photo is not None else np.zeros((0, 2), int), extra_planted_xyz=ep_xyz,
                        extra_planted_loc=ep_loc)
    # section
    sec = P["section"]; c = np.asarray(sec["centre_xy"]); a = np.asarray(sec["axis_xy"]); sr = sec["s_range_m"]
    mg, sg = G.band(Xg, c, a, sr)
    Va, Fa = G.prior_mesh(SITE, "ALS")
    segs = {k: G.cut_vertical(V, F, c, a, sr) for k, (V, F) in meshes.items()}
    train = G.jl(S0 / "fork_inputs/s61" / SITE / "split.json")["train"]
    AP, AF = [], []
    for n in train:
        lm = G.export(SITE, PRIOR, "locmap", n)
        msk = np.isin(lm, np.concatenate([mis, case]))
        if not msk.any():
            continue
        cf = G.export(SITE, PRIOR, "conf", n) > 0.5
        X, _, _ = G.backproject(n, G.export(SITE, PRIOR, "mvs", n), msk & cf)
        b, s = G.band(X, c, a, sr); AP.append(np.column_stack([s[b], X[b, 2]]))
        Xf, _, _ = G.backproject(n, G.fork_map(SITE, "mvs_photometric", n), msk & ~cf)
        if len(Xf):
            b, s = G.band(Xf, c, a, sr); AF.append(np.column_stack([s[b], Xf[b, 2]]))
    mp = np.isin(np.arange(len(code)), mis)
    ms_c = cen[mis]; bm, sm = G.band(ms_c, c, a, sr, half=0.4)
    np.savez_compressed(PF / "proj/fig2_section.npz", gt_s=sg[mg], gt_z=Xg[mg, 2], seg_als=G.cut_vertical(Va, Fa, c, a, sr),
                        all_pass=np.concatenate(AP) if AP else np.zeros((0, 2)), all_fail=np.concatenate(AF) if AF else np.zeros((0, 2)),
                        missing_s=sm[bm], **{f"seg_{i}": v for i, v in enumerate(segs.values())})
    out = dict(rows=rows, runs={k: str(v) for k, v in RUNS.items()}, seg_order=list(segs.keys()), new_depth_pixels_total=int(newpix.sum()),
               new_depth_pixels_on_listed=int(newpix[allp].sum()), new_pixels_in_photo=int(len(new_in_photo)) if new_in_photo is not None else 0,
               extra_planted_total=int(len(extra_plant)), extra_planted_on_listed=int(np.isin(ep_loc, allp).sum()),
               mid_report_changed=dict(code4_changed=int(((code == 4) & LB["own_depth_changed"] & ev).sum()), code13_changed=int(((code == 13) & LB["own_depth_changed"] & ev).sum()),
                                       changed_all_eval=int((LB["own_depth_changed"] & ev).sum()), changed_any=int(LB["own_depth_changed"].sum()),
                                       changed_ids=np.nonzero(LB["own_depth_changed"])[0].tolist()),
               seconds=round(time.time() - t0, 1), made=now(), scientific_verdict=None)
    jdump(DOCS / "tables/fig2_patches.json", out)
    log("done", out["seconds"], out["new_depth_pixels_total"], out["extra_planted_total"])


if __name__ == "__main__":
    main()

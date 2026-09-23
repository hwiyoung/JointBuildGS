"""PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1 step 3 (jointbuildgs:dev, CPU): the stage-1 products of r9 with the overlapping
parts of LoD2 party walls left out of the prior surface (fix 'na'); everything else is r9's code (stage1_products_r9.py)
with the r10 paths. A cut polygon keeps the plane normal and the cell-grid origin of its r9 polygon (meshes_r10
frames_<setting>.npz), so its remaining cells are r9 cells.

  python stage1_products_r10.py tau                 tolerance per prior and surface kind (2.5 x NMAD; spec compared, not a floor)
  python stage1_products_r10.py product <setting>   surfaces, conversion, marks, judgment units (patches) and their states
  mounts: /artifacts (ro), /repo (ro), /r7 (PHD-STAGE2-R7-PROPAGATION-v1 payload, ro), /p9 (r9, ro), /p10 (rw)

LoD2 (M_N, M_B): the meshes without the bottom faces and the party-wall overlaps (meshes_r10.py) and their prior depth /
triangle ids (render_r10.py);
the CityGML type and building of a triangle come with the r9 mesh. Airborne LiDAR (L_N, L_B): r7's meshes and ids and the
stage-2 prior depth, exactly as r8 and r9 (the r10 trainings read r9's airborne LiDAR products; only tau is recomputed here and
must equal r9's).
Every rule is a call into src/phd/prior_propagation_v4 (v3 byte-identical for these rules apart from the grid origin option).
Outputs /p10/stage1/tolerance.json and /p10/stage1/products/<setting>/..."""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v4 import conversion as conv  # noqa: E402
from src.phd.prior_propagation_v4 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v4 import outlines as outl  # noqa: E402
from src.phd.prior_propagation_v4 import rule  # noqa: E402
from src.phd.prior_propagation_v4 import surfaces as surf  # noqa: E402
from src.phd.prior_propagation_v4 import tolerance as tol  # noqa: E402

ART = Path("/artifacts/JointBuildGS")
S1 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
S2 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1"
MAPS = S2 / "inputs/maps"
SPARSE = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
R7 = Path("/r7")
P9 = Path("/p9"); P10 = Path("/p10"); OUT = P10 / "stage1"
CFG = json.loads(Path("/repo/configs/phd/stage2_r10_two_fixes_three_checks_v1/r10.json").read_text())
PJ = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
PZ = np.load(S1 / "inputs/lod2_polygons.npz")
RECT = np.array(PJ["als_crop_local_xy"], float)
TARGET = PJ["target_building"]
TRAIN = json.loads((S2 / "runs/P_M_N/model/monitor/meta.json").read_text())["train_views"]
STEEP_NZ = CFG["surfaces"]["steep_nz"]
STEP_BASE = 100000
TAG = "data"          # the one tolerance of r8 (data width); kept as the key suffix of the store arrays
GROUND_RINGS = [(p["poly_index"], p["building_id"], p["ring_local_xy"]) for p in PJ["polygons"] if p["citygml_type"] == "GroundSurface"]
TARGET_RING = [i for i, (pi, bid, _) in enumerate(GROUND_RINGS) if bid == TARGET][0]


def q2R(q):
    w, x, y, z = q
    return np.array([[1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w], [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w],
                     [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]])


def load_cameras():
    cams, imgs = {}, {}
    for l in (SPARSE / "cameras.txt").read_text().splitlines():
        if l.strip() and not l.startswith("#"):
            t = l.split(); cams[int(t[0])] = dict(W=int(t[2]), H=int(t[3]), p=[float(x) for x in t[4:]])
    for l in (SPARSE / "images.txt").read_text().splitlines():
        t = l.split()
        if len(t) >= 10 and not l.startswith("#") and t[9].lower().endswith(".jpg"):
            imgs[Path(t[9]).stem] = dict(R=q2R([float(x) for x in t[1:5]]), t=np.array([float(x) for x in t[5:8]]), cam=int(t[8]))
    return cams, imgs


CAMS, IMGS = load_cameras()
VIEWS = sorted(IMGS)


def view_arrays(setting, stem):
    if setting.startswith("M"):   # r10: LoD2 without the bottom faces and the party-wall overlaps (render_r10.py)
        tri = np.load(OUT / "ids" / setting / f"{stem}.npz")["tri"].reshape(-1)
        P = np.load(OUT / "prior" / setting / "raw_depth" / f"{stem}.npy").reshape(-1)
    else:                         # airborne LiDAR: as r8
        tri = np.load(R7 / "stage1/ids" / setting / f"{stem}.npz")["tri"].reshape(-1)
        P = np.load(MAPS / f"prior_{setting}/raw_depth/{stem}.npy").reshape(-1)
    A = np.load(MAPS / f"conf/raw_depth/{stem}.npy").reshape(-1)
    M = np.load(MAPS / f"mvs/raw_depth/{stem}.npy").reshape(-1)
    return tri, P, A, M


def rays(stem, idx):
    im = IMGS[stem]; cam = CAMS[im["cam"]]; fx, fy, cx, cy = cam["p"]
    d = conv.pixel_rays(fx, fy, cx, cy, im["R"], cam["W"], cam["H"], flat_idx=idx, dtype=np.float64)
    return d, conv.camera_centre(im["R"], im["t"])


# ------------------------------------------------------------------------------------------------ surfaces
def surfaces_of(setting, variant):
    """(mesh, tri_surface_ext [T], tri_normal_used [T,3], table {ext: row}) for a setting and outline variant."""
    m = dict(np.load((OUT if setting.startswith("M") else R7 / "stage1") / "meshes" / f"{setting}.npz", allow_pickle=False))
    V, F = m["V"], m["F"]
    n_tri, a_tri = surf.tri_geometry(V, F)
    table = {}
    if setting.startswith("M"):
        pot = m["tri_poly"]
        kinds = {"RoofSurface": "roof", "WallSurface": "wall", "GroundSurface": "ground"}
        normal_used = np.zeros_like(n_tri)
        fz = np.load(OUT / "meshes" / f"faces_{setting}.npz")
        n_out = {int(p): fz["normal_outward"][i] for i, p in enumerate(fz["ids"])}
        fr = np.load(OUT / "meshes" / f"frames_{setting}.npz")      # r10: the r9 plane normal and grid origin of every polygon
        fr_n = {int(p): fr["normal"][i] for i, p in enumerate(fr["ids"])}
        for s in np.unique(pot):
            sel = pot == s
            nn = np.asarray(fr_n[int(s)], np.float64)
            normal_used[sel] = nn
            if s >= STEP_BASE:
                typ, bid = "step", TARGET
            else:
                typ = kinds.get(str(m["tri_type"][sel][0]), "other"); bid = str(m["tri_building"][sel][0])
            table[int(s)] = dict(ext=int(s), type=typ, building=bid, target=bid == TARGET, is_building_face=True,
                                 kind=int(conv.surface_kind(nn[2])), normal=nn.tolist(), normal_outward=n_out[int(s)].tolist(),
                                 area_mesh_m2=float(a_tri[sel].sum()))
        return m, pot.astype(np.int64), normal_used, table
    cent = V[F].mean(1)
    cls = m["cls"]; raised = m["raised"]
    if variant == "lod2":
        region = outl.region_from_rings(cent[:, :2], [r for _, _, r in GROUND_RINGS])
        ts, n_tri, a_tri = surf.tin_surfaces(V, F, STEEP_NZ, region=region)
    elif variant == "cls2":          # decision 4: classification = building / non-building only, steep triangles split buildings
        region = None
        ts, n_tri, a_tri = surf.tin_surfaces(V, F, STEEP_NZ, building=outl.building_triangles(F, cls, CFG["surfaces"]["building_class"]))
    else:
        raise ValueError(variant)
    tri_in_target = outl.region_from_rings(cent[:, :2], [GROUND_RINGS[TARGET_RING][2]]) == 0
    for s in np.unique(ts[ts >= 0]):
        sel = ts == s
        vid = np.unique(F[sel])
        c6 = float((cls[vid] == 6).mean())
        reg = int(np.bincount(np.maximum(region[sel], -1) + 1).argmax() - 1) if region is not None else None
        nn = (n_tri[sel] * a_tri[sel, None]).sum(0); nn /= np.linalg.norm(nn)
        tshare = float((a_tri[sel] * tri_in_target[sel]).sum() / a_tri[sel].sum())
        is_b = bool(c6 >= 0.5) if variant == "lod2" else True     # cls2: only building triangles carry a number
        table[int(s)] = dict(ext=int(s), type="tin", building=None, is_building_face=is_b, class6_share=c6,
                             raised_share=float(raised[vid].mean()), region=reg, target_footprint_share=tshare,
                             target=bool(is_b and tshare >= 0.5), kind=conv.KIND_ROOF, normal=nn.tolist(),
                             area_mesh_m2=float(a_tri[sel].sum()), n_tri=int(sel.sum()))
    return m, ts.astype(np.int64), n_tri, table


def pixel_normals(tri, ts_ext, n_used):
    """normal and surface number per hit pixel; steep TIN triangles keep their own normal (no surface number)."""
    hit = tri >= 0
    n = np.zeros((len(tri), 3)); n[hit] = n_used[tri[hit]]
    s = np.full(len(tri), -1, np.int64); s[hit] = ts_ext[tri[hit]]
    return n, s, hit


def building_face_flags(table):
    mx = int(max(table)) + 1 if table else 1
    b = np.zeros(mx, bool)
    for e, r in table.items():
        b[e] = bool(r["is_building_face"])
    return b


# ------------------------------------------------------------------------------------------------ tolerance
def step_tau():
    res = {"rule": CFG["tolerance"]["rule"], "pool": CFG["tolerance"]["pool"], "k": CFG["values"]["nmad_k"],
           "clip_nmad": CFG["values"]["clip_nmad"], "priors": {}}
    for prior, setting in (("M", "M_N"), ("L", "L_N")):
        m, ts, n_used, table = surfaces_of(setting, "poly" if prior == "M" else "lod2")
        target = np.zeros(int(max(table) + 1), bool)
        for e, r in table.items():
            target[e] = bool(r["target"]) and r["is_building_face"]
        samples = {conv.KIND_ROOF: [], conv.KIND_WALL: []}
        for stem in VIEWS:
            tri, P, A, M = view_arrays(setting, stem)
            n, s, hit = pixel_normals(tri, ts, n_used)
            pix = np.nonzero(np.isfinite(P) & hit & (s >= 0) & (A == 1))[0]
            pix = pix[target[s[pix]]]
            d, _ = rays(stem, pix)
            r = conv.residual_metres((M[pix] - P[pix]).astype(np.float64), conv.factor(n[pix], d))
            kind = conv.surface_kind(n[pix, 2])
            for k in samples:
                samples[k].append(r[kind == k])
        spec = CFG["tolerance"]["spec_m"][prior]; src = CFG["tolerance"]["spec_source"]
        roof_x = np.concatenate(samples[conv.KIND_ROOF]); wall_x = np.concatenate(samples[conv.KIND_WALL])
        roof_st = tol.robust_width(roof_x, CFG["values"]["nmad_k"], CFG["values"]["clip_nmad"])
        wall_st = tol.robust_width(wall_x, CFG["values"]["nmad_k"], CFG["values"]["clip_nmad"])
        roof_t = tol.tolerance(roof_st, spec["roof"], src[f"{prior}_roof"])
        if prior == "M":
            wall_t = tol.tolerance(wall_st, spec["wall"], src["walls"], fallback=roof_t)
        else:   # walls are not surfaces of the TIN: the roof value, recorded
            wall_t = tol.tolerance(dict(width=None), spec["wall"], src["walls"], fallback=roof_t)
            wall_t["side"] = "roof value (walls are not surfaces of the TIN)"
        res["priors"][prior] = dict(roof=dict(stats=roof_st, **roof_t), wall=dict(stats=wall_st, **wall_t))
        # residual sample for the figure (every 10th, float32)
        np.savez_compressed(OUT / f"residuals_{prior}.npz", roof=roof_x[::10].astype(np.float32), wall=wall_x[::10].astype(np.float32))
        print(prior, json.dumps({k: (v["tau"], v["side"], v["exceeds_spec"], v["stats"]["n"]) for k, v in res["priors"][prior].items()}), flush=True)
    (OUT / "tolerance.json").write_text(json.dumps(res, indent=1))


# ------------------------------------------------------------------------------------------------ products
def build_store(setting, table, m, ts, n_used, cell):
    rows = [r for r in table.values() if r["is_building_face"]]
    if setting.startswith("M"):   # polygons whose triangles touch the crop rectangle (as r7)
        V, F = m["V"], m["F"]
        lo = V[F][:, :, :2].min(1); hi = V[F][:, :, :2].max(1)
        touch = (hi[:, 0] >= RECT[0, 0]) & (lo[:, 0] <= RECT[1, 0]) & (hi[:, 1] >= RECT[0, 1]) & (lo[:, 1] <= RECT[1, 1])
        keep = set(np.unique(ts[touch]).tolist())
        rows = [r for r in rows if r["ext"] in keep]
        fr = np.load(OUT / "meshes" / f"frames_{setting}.npz")      # r10: the r9 grid origin (cut polygons keep their cells)
        fr_o = {int(p): fr["o"][i] for i, p in enumerate(fr["ids"])}
        return locs.build_plane_store(m["V"], m["F"], ts, [dict(ext=r["ext"], normal=r["normal"], o=fr_o[int(r["ext"])]) for r in rows], RECT, cell)
    return locs.build_tin_store(m["V"], m["F"], ts, n_used, surf.tri_geometry(m["V"], m["F"])[1], [dict(ext=r["ext"]) for r in rows], RECT, cell)


def step_product(setting):
    t0 = time.time()
    prior = setting[0]
    TAU = json.loads((OUT / "tolerance.json").read_text())["priors"][prior]
    tv = {conv.KIND_ROOF: TAU["roof"]["tau"], conv.KIND_WALL: TAU["wall"]["tau"]}
    variants = ["poly"] if setting.startswith("M") else ["lod2", "cls2"]
    main = variants[0]
    cell = CFG["values"]["cell_m"]
    D = OUT / "products" / setting; D.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for var in variants:
        m, ts, n_used, table = surfaces_of(setting, var)
        (D / f"surfaces_{var}.json").write_text(json.dumps(dict(setting=setting, variant=var, surfaces=list(table.values())), indent=1))
        np.save(D / f"tri_surface_{var}.npy", ts.astype(np.int32))
        st = build_store(setting, table, m, ts, n_used, cell)
        jobs[var] = dict(store=st, ts=ts, n_used=n_used, table=table, bface=building_face_flags(table), nloc=len(st["loc_area"]),
                         npix=[], na1=[], nag=[], ncf=[])
        print(setting, var, "surfaces", len(st["surf_ext"]), "units", len(st["loc_area"]), f"{time.time() - t0:.0f}s", flush=True)
    for sub in ("fconv", "locmap", "markmap"):
        (D / sub).mkdir(exist_ok=True)
    pix_rec = {}
    for stem in VIEWS:
        tri, P, A, M = view_arrays(setting, stem)
        W, H = CAMS[IMGS[stem]["cam"]]["W"], CAMS[IMGS[stem]["cam"]]["H"]
        jm = jobs[main]
        n, s_main, hit = pixel_normals(tri, jm["ts"], jm["n_used"])
        prior_px = np.isfinite(P)
        idx_all = np.nonzero(prior_px)[0]
        d_all, Cc = rays(stem, idx_all)
        f_all = conv.factor(n[idx_all], d_all, has_surface=hit[idx_all])
        fmap = np.full(len(tri), np.nan, np.float32); fmap[idx_all] = f_all
        np.save(D / "fconv" / f"{stem}.npy", fmap.reshape(H, W))
        s_ext = np.where(hit[idx_all], jm["ts"][np.maximum(tri[idx_all], 0)], -1)
        bface = (s_ext >= 0) & jm["bface"][np.clip(s_ext, 0, len(jm["bface"]) - 1)]
        if setting.startswith("M"):
            bface = hit[idx_all].copy()          # every LoD2 polygon (and step quad) is a building face
        kind_all = conv.surface_kind(n[idx_all, 2])
        tau_px = np.where(bface, np.where(kind_all == conv.KIND_ROOF, tv[conv.KIND_ROOF], tv[conv.KIND_WALL]), tv[conv.KIND_ROOF])
        a1_all = A[idx_all] == 1
        r_all = np.abs(M[idx_all] - P[idx_all]).astype(np.float64) * f_all
        ag = a1_all & (r_all <= tau_px); cf = a1_all & ~(r_all <= tau_px)
        mk = np.full(len(tri), rule.MARK_NONE, np.int8); mk[idx_all[ag]] = rule.MARK_AGREE; mk[idx_all[cf]] = rule.MARK_CONFLICT
        np.save(D / "markmap" / f"{stem}.npy", mk.reshape(H, W))
        X_all = Cc[None, :] + P[idx_all, None].astype(np.float64) * d_all
        for var, jb in jobs.items():
            st = jb["store"]
            sx = np.where(hit[idx_all], jb["ts"][np.maximum(tri[idx_all], 0)], -1)
            cidx = locs.compact_index(st, np.maximum(sx, 0)); cidx[sx < 0] = -1
            ok = cidx >= 0
            loc = np.full(len(idx_all), -1, np.int64)
            loc[ok] = locs.locate(st, cidx[ok], X_all[ok])
            L = jb["nloc"]
            jb["npix"].append(np.bincount(loc[ok], minlength=L).astype(np.int32))
            jb["na1"].append(np.bincount(loc[ok], weights=a1_all[ok], minlength=L).astype(np.int32))
            jb["nag"].append(np.bincount(loc[ok], weights=ag[ok], minlength=L).astype(np.int32))
            jb["ncf"].append(np.bincount(loc[ok], weights=cf[ok], minlength=L).astype(np.int32))
            if var == main:
                lm = np.full(len(tri), -1, np.int32); lm[idx_all] = loc
                np.save(D / "locmap" / f"{stem}.npy", lm.reshape(H, W))
                nl = ~ok
                pix_rec[stem] = dict(prior_px=int(len(idx_all)), located_px=int(ok.sum()), no_unit_px=int(nl.sum()),
                                     no_unit_steep_px=int((nl & (sx == surf.STEEP)).sum()),
                                     no_unit_nonbuilding_surface_px=int((nl & (sx >= 0)).sum()),
                                     no_unit_no_hit_px=int((nl & ~hit[idx_all]).sum()),
                                     no_unit_a1_px=int((nl & a1_all).sum()), no_unit_agree_px=int((nl & ag).sum()),
                                     no_unit_conflict_px=int((nl & cf).sum()), located_a1_px=int((ok & a1_all).sum()),
                                     located_agree_px=int((ok & ag).sum()), located_conflict_px=int((ok & cf).sum()),
                                     nonbuilding_px=int((~bface).sum()))
        print(setting, stem, pix_rec[stem], f"{time.time() - t0:.0f}s", flush=True)
    ti = [VIEWS.index(v) for v in TRAIN]
    summary = dict(setting=setting, main=main, tolerance={"roof": tv[conv.KIND_ROOF], "wall": tv[conv.KIND_WALL]}, pixels=pix_rec,
                   train_views=TRAIN, jobs={})
    for var, jb in jobs.items():
        npix = np.stack(jb["npix"])[ti]; na1 = np.stack(jb["na1"])[ti]
        nag = np.stack(jb["nag"])[ti]; ncf = np.stack(jb["ncf"])[ti]
        state, vote, ns, nsp, E = rule.location_state(npix, na1, nag, ncf)
        out = dict(jb["store"])
        out.update(pix_sum=npix.sum(0), a1_sum=na1.sum(0), n_seeing_views=(npix > 0).sum(0).astype(np.int32))
        out.update({f"state_{TAG}": state, f"vote_{TAG}": vote, f"n_seeing_{TAG}": ns, f"n_supporting_{TAG}": nsp, f"E_{TAG}": E,
                    f"agree_sum_{TAG}": nag.sum(0), f"conflict_sum_{TAG}": ncf.sum(0)})
        locs.save_store(D / f"store_{var}_c{cell}.npz", out)
        summary["jobs"][var] = dict(n_units=int(len(state)), support=int((state == rule.ST_SUPPORT).sum()),
                                    missing=int((state == rule.ST_MISSING).sum()), invisible=int((state == rule.ST_INVISIBLE).sum()))
    summary["seconds"] = round(time.time() - t0, 1)
    (D / "summary.json").write_text(json.dumps(summary, indent=1))
    print(setting, "done", summary["jobs"], flush=True)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    if sys.argv[1] == "tau":
        step_tau()
    else:
        step_product(sys.argv[2])

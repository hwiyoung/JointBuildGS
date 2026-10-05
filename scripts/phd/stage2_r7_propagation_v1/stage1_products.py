"""PHD-STAGE2-R7-PROPAGATION-v1 step 3 (jointbuildgs:dev, CPU): the new stage-1 products (no training).

  python stage1_products.py tau                 tolerance per prior and surface kind from the nominal scenes
  python stage1_products.py product <setting>   surfaces, conversion maps, marks, locations, states for one setting
  mounts: /artifacts (ro), /repo (ro), /p7 (rw)

Every rule is a call into src/phd/prior_propagation_v1 (conversion, tolerance, surfaces, outlines, rule, locations).
  surfaces    LoD2: polygon (+ step quads). TIN: gentle triangles joined through shared edges inside one outline region;
              outline variants: lod2 = LoD2 GroundSurface polygons (used), cls = own-classification clusters, none =
              steepness only (pre-measurement v1). A TIN surface is a building face when most of its vertices are class 6.
  conversion  f per pixel with the scene's own normal (LoD2 polygon normal, TIN triangle normal; steep TIN triangles use
              their own normal as wall-like); pixels without a hit have no prior.
  tolerance   nominal scene, 15 views, A = 1, target-building surfaces, residual (MVS - prior) * f split by the kind of the
              own normal; robust_width and tolerance(spec) per kind; walls without a sample or not surfaces -> roof value.
  marks       support pixel of a building surface: |MVS - prior| * f <= tau_kind -> agree, else conflict; two tolerance
              variants in one pass: spec (max with the agency spec, the order) and data (width only, 2026-09-23 rule).
  locations   cells of 0.25 m (0.5 m for the sensitivity), 13 training views, per (view, location) pixel counts ->
              rule.location_state per tolerance variant.
Outputs /p7/stage1/tolerance.json and /p7/stage1/products/<setting>/..."""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v1 import conversion as conv  # noqa: E402
from src.phd.prior_propagation_v1 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v1 import outlines as outl  # noqa: E402
from src.phd.prior_propagation_v1 import rule  # noqa: E402
from src.phd.prior_propagation_v1 import surfaces as surf  # noqa: E402
from src.phd.prior_propagation_v1 import tolerance as tol  # noqa: E402

ART = Path("/artifacts/JointBuildGS")
S1 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
S2 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1"
MAPS = S2 / "inputs/maps"
SPARSE = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
P7 = Path("/p7"); OUT = P7 / "stage1"
CFG = json.loads(Path("/repo/configs/phd/stage2_r7_propagation_v1/r7.json").read_text())
PJ = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
PZ = np.load(S1 / "inputs/lod2_polygons.npz")
RECT = np.array(PJ["als_crop_local_xy"], float)
TARGET = PJ["target_building"]
TRAIN = json.loads((S2 / "runs/P_M_N/model/monitor/meta.json").read_text())["train_views"]
STEEP_NZ = CFG["surfaces"]["steep_nz"]
STEP_BASE = 100000
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
    tri = np.load(OUT / "ids" / setting / f"{stem}.npz")["tri"].reshape(-1)
    P = (np.load(OUT / "prior_M_C" / f"{stem}.npy") if setting == "M_C" else np.load(MAPS / f"prior_{setting}/raw_depth/{stem}.npy")).reshape(-1)
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
    m = dict(np.load(OUT / "meshes" / f"{setting}.npz"))
    V, F = m["V"], m["F"]
    n_tri, a_tri = surf.tri_geometry(V, F)
    table = {}
    if setting.startswith("M"):
        pot = m["tri_poly"]
        kinds = {"RoofSurface": "roof", "WallSurface": "wall", "GroundSurface": "ground"}
        normal_used = np.zeros_like(n_tri)
        labels = PZ["labels"]; bids = PZ["building_ids"]
        for s in np.unique(pot):
            sel = pot == s
            nn = (n_tri[sel] * a_tri[sel, None]).sum(0); nn /= np.linalg.norm(nn)
            normal_used[sel] = nn
            if s >= STEP_BASE:
                typ, bid = "step", TARGET
            else:
                typ = kinds.get(str(labels[sel[: len(labels)]][0]), "other"); bid = str(bids[sel[: len(bids)]][0])
            table[int(s)] = dict(ext=int(s), type=typ, building=bid, target=bid == TARGET, is_building_face=True,
                                 kind=int(conv.surface_kind(nn[2])), normal=nn.tolist(), area_mesh_m2=float(a_tri[sel].sum()))
        return m, pot.astype(np.int64), normal_used, table
    # TIN
    cent = V[F].mean(1)
    if variant == "lod2":
        region = outl.region_from_rings(cent[:, :2], [r for _, _, r in GROUND_RINGS])
    elif variant == "cls":
        co = CFG["surfaces"]["classification_outline"]
        lab, rec = outl.classification_clusters(V[:, :2], m["cls"], RECT, cell=co["cell_m"], building_class=co["building_class"],
                                                min_share=co["min_share"], close_iter=co["close_iter"], min_cells=co["min_cells"])
        region = outl.region_from_raster(cent[:, :2], lab, RECT, CFG["surfaces"]["classification_outline"]["cell_m"])
    else:
        region = None
    ts, n_tri, a_tri = surf.tin_surfaces(V, F, STEEP_NZ, region=region)
    cls = m["cls"]; raised = m["raised"]
    for s in np.unique(ts[ts >= 0]):
        sel = ts == s
        vid = np.unique(F[sel])
        c6 = float((cls[vid] == 6).mean())
        reg = int(np.bincount(np.maximum(region[sel], -1) + 1).argmax() - 1) if region is not None else None
        nn = (n_tri[sel] * a_tri[sel, None]).sum(0); nn /= np.linalg.norm(nn)
        tshare = float((a_tri[sel] * (outl.region_from_rings(cent[sel, :2], [GROUND_RINGS[TARGET_RING][2]]) == 0)).sum() / a_tri[sel].sum())
        table[int(s)] = dict(ext=int(s), type="tin", building=None, is_building_face=bool(c6 >= 0.5), class6_share=c6,
                             raised_share=float(raised[vid].mean()), region=reg, target_footprint_share=tshare,
                             target=bool(c6 >= 0.5 and tshare >= 0.5), kind=conv.KIND_ROOF, normal=nn.tolist(),
                             area_mesh_m2=float(a_tri[sel].sum()), n_tri=int(sel.sum()))
    return m, ts.astype(np.int64), n_tri, table


def pixel_normals(tri, ts_ext, n_used):
    """normal and surface number per hit pixel; steep TIN triangles keep their own normal (no surface number)."""
    hit = tri >= 0
    n = np.zeros((len(tri), 3)); n[hit] = n_used[tri[hit]]
    s = np.full(len(tri), -1, np.int64); s[hit] = ts_ext[tri[hit]]
    return n, s, hit


# ------------------------------------------------------------------------------------------------ tolerance
def step_tau():
    res = {"pool": CFG["tolerance"]["pool"], "k": CFG["tolerance"]["k"], "clip_nmad": CFG["tolerance"]["clip_nmad"], "priors": {}}
    for prior, setting in (("M", "M_N"), ("L", "L_N")):
        m, ts, n_used, table = surfaces_of(setting, "lod2")
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
            f = conv.factor(n[pix], d)
            r = conv.residual_metres((M[pix] - P[pix]).astype(np.float64), f)
            kind = conv.surface_kind(n[pix, 2])
            for k in samples:
                samples[k].append(r[kind == k])
        out = {}
        spec = CFG["tolerance"]["spec_m"][prior]
        for use_spec, tag in ((True, "spec"), (False, "data")):
            roof_st = tol.robust_width(np.concatenate(samples[conv.KIND_ROOF]), CFG["tolerance"]["k"], CFG["tolerance"]["clip_nmad"])
            wall_x = np.concatenate(samples[conv.KIND_WALL]) if samples[conv.KIND_WALL] else np.zeros(0)
            wall_st = tol.robust_width(wall_x, CFG["tolerance"]["k"], CFG["tolerance"]["clip_nmad"])
            roof_t = tol.tolerance(roof_st, spec["roof"], use_spec)
            wall_t = tol.tolerance(wall_st, spec["wall"], use_spec, fallback=roof_t) if prior == "M" else \
                dict(tau=roof_t["tau"], width=None, spec=spec["wall"], side="roof value (walls are not surfaces of the TIN)")
            out[tag] = dict(roof=dict(stats=roof_st, **roof_t), wall=dict(stats=wall_st, **wall_t))
        res["priors"][prior] = out
        print(prior, json.dumps({t: {k: (v["tau"], v["side"], v["stats"]["n"]) for k, v in o.items()} for t, o in out.items()}), flush=True)
    (OUT / "tolerance.json").write_text(json.dumps(res, indent=1))


# ------------------------------------------------------------------------------------------------ products
def build_store(setting, variant, table, m, ts, n_used, cell):
    rows = [r for r in table.values() if r["is_building_face"]]
    if setting.startswith("M"):   # polygons whose triangles touch the crop rectangle (as pre-measurement v1)
        V, F = m["V"], m["F"]
        lo = V[F][:, :, :2].min(1); hi = V[F][:, :, :2].max(1)
        touch = (hi[:, 0] >= RECT[0, 0]) & (lo[:, 0] <= RECT[1, 0]) & (hi[:, 1] >= RECT[0, 1]) & (lo[:, 1] <= RECT[1, 1])
        keep = set(np.unique(ts[touch]).tolist())
        rows = [r for r in rows if r["ext"] in keep]
        return locs.build_plane_store(m["V"], m["F"], ts, [dict(ext=r["ext"], normal=r["normal"]) for r in rows], RECT, cell)
    return locs.build_tin_store(m["V"], m["F"], ts, n_used, surf.tri_geometry(m["V"], m["F"])[1], [dict(ext=r["ext"]) for r in rows], RECT, cell)


def step_product(setting):
    t0 = time.time()
    prior = setting[0]
    TAU = json.loads((OUT / "tolerance.json").read_text())["priors"][prior]
    tv = {tag: {conv.KIND_ROOF: TAU[tag]["roof"]["tau"], conv.KIND_WALL: TAU[tag]["wall"]["tau"]} for tag in ("spec", "data")}
    variants = ["poly"] if setting.startswith("M") else ["lod2", "none", "cls"]
    cells = CFG["sensitivity"]["cell_m"] + [CFG["values"]["cell_m"]]
    D = OUT / "products" / setting; D.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for var in variants:
        m, ts, n_used, table = surfaces_of(setting, var)
        (D / f"surfaces_{var}.json").write_text(json.dumps(dict(setting=setting, variant=var, surfaces=list(table.values())), indent=1))
        np.save(D / f"tri_surface_{var}.npy", ts.astype(np.int32))
        for cell in (cells if var in ("poly", "lod2") else [CFG["values"]["cell_m"]]):
            st = build_store(setting, var, table, m, ts, n_used, cell)
            jobs[(var, cell)] = dict(store=st, ts=ts, n_used=n_used, table=table, nloc=len(st["loc_area"]),
                                     counts={tag: [] for tag in ("spec", "data")}, npix=[], na1=[])
            print(setting, var, cell, "surfaces", len(st["surf_ext"]), "locations", len(st["loc_area"]), f"{time.time() - t0:.0f}s", flush=True)
    main_key = ("poly", CFG["values"]["cell_m"]) if setting.startswith("M") else ("lod2", CFG["values"]["cell_m"])
    (D / "fconv").mkdir(exist_ok=True); (D / "locmap").mkdir(exist_ok=True)
    pix_rec = {}
    for stem in VIEWS:
        tri, P, A, M = view_arrays(setting, stem)
        W, H = CAMS[IMGS[stem]["cam"]]["W"], CAMS[IMGS[stem]["cam"]]["H"]
        jm = jobs[main_key]
        n, s_main, hit = pixel_normals(tri, jm["ts"], jm["n_used"])
        prior_px = np.isfinite(P)
        # conversion factor over every prior pixel (own normals), saved for the stage-1 / stage-2 check
        idx_all = np.nonzero(prior_px)[0]
        d_all, Cc = rays(stem, idx_all)
        f_all = conv.factor(n[idx_all], d_all, has_surface=hit[idx_all])
        fmap = np.full(len(tri), np.nan, np.float32); fmap[idx_all] = f_all
        np.save(D / "fconv" / f"{stem}.npy", fmap.reshape(H, W))
        kind_all = conv.surface_kind(n[idx_all, 2])
        tau_px = {tag: np.where(kind_all == conv.KIND_ROOF, tv[tag][conv.KIND_ROOF], tv[tag][conv.KIND_WALL]) for tag in tv}
        a1_all = A[idx_all] == 1
        r_all = np.abs(M[idx_all] - P[idx_all]).astype(np.float64) * f_all
        marks = {tag: (a1_all & (r_all <= tau_px[tag]), a1_all & ~(r_all <= tau_px[tag])) for tag in tv}
        X_all = Cc[None, :] + P[idx_all, None].astype(np.float64) * d_all
        rec = {}
        for key, jb in jobs.items():
            st = jb["store"]
            s_ext = np.where(hit[idx_all], jb["ts"][np.maximum(tri[idx_all], 0)], -1)
            cidx = locs.compact_index(st, np.maximum(s_ext, 0)); cidx[s_ext < 0] = -1
            ok = cidx >= 0
            loc = np.full(len(idx_all), -1, np.int64)
            loc[ok] = locs.locate(st, cidx[ok], X_all[ok])
            L = jb["nloc"]
            jb["npix"].append(np.bincount(loc[ok], minlength=L).astype(np.int32))
            jb["na1"].append(np.bincount(loc[ok], weights=a1_all[ok], minlength=L).astype(np.int32))
            for tag in tv:
                ag, cf = marks[tag]
                jb["counts"][tag].append((np.bincount(loc[ok], weights=ag[ok], minlength=L).astype(np.int32),
                                          np.bincount(loc[ok], weights=cf[ok], minlength=L).astype(np.int32)))
            if key == main_key:
                lm = np.full(len(tri), -1, np.int32); lm[idx_all] = loc
                np.save(D / "locmap" / f"{stem}.npy", lm.reshape(H, W))
                rec = dict(prior_px=int(prior_px.sum()), hit_outside_prior_px=int((hit & ~prior_px).sum()),
                           building_px=int(ok.sum()), steep_px=int((hit[idx_all] & (s_ext == surf.STEEP)).sum()),
                           nonbuilding_surface_px=int((~ok & (s_ext >= 0)).sum()),
                           support_px=int((a1_all & ok).sum()), no_surface_px=int((~hit[idx_all]).sum()))
        pix_rec[stem] = rec
        print(setting, stem, rec, f"{time.time() - t0:.0f}s", flush=True)
    # states per job and tolerance variant, from the 13 training views
    ti = [VIEWS.index(v) for v in TRAIN]
    summary = dict(setting=setting, main=list(main_key), pixels=pix_rec, jobs={})
    for (var, cell), jb in jobs.items():
        npix = np.stack(jb["npix"])[ti]; na1 = np.stack(jb["na1"])[ti]
        out = dict(jb["store"])
        out.update(pix_sum=npix.sum(0), a1_sum=na1.sum(0))
        for tag in tv:
            nag = np.stack([c[0] for c in jb["counts"][tag]])[ti]; ncf = np.stack([c[1] for c in jb["counts"][tag]])[ti]
            state, vote, ns, nsp, E = rule.location_state(npix, na1, nag, ncf)
            out.update({f"state_{tag}": state, f"vote_{tag}": vote, f"n_seeing_{tag}": ns, f"n_supporting_{tag}": nsp, f"E_{tag}": E,
                        f"agree_sum_{tag}": nag.sum(0), f"conflict_sum_{tag}": ncf.sum(0)})
            summary["jobs"][f"{var}_{cell}_{tag}"] = dict(n_locations=int(len(state)), support=int((state == rule.ST_SUPPORT).sum()),
                                                          missing=int((state == rule.ST_MISSING).sum()),
                                                          invisible=int((state == rule.ST_INVISIBLE).sum()))
        # per-view seeing counts for the re-read check (seeing views of each location over the training views)
        out["n_seeing_views"] = (npix > 0).sum(0).astype(np.int32)
        locs.save_store(D / f"store_{var}_c{cell}.npz", out)
    summary["seconds"] = round(time.time() - t0, 1)
    (D / "summary.json").write_text(json.dumps(summary, indent=1))
    print(setting, "done", summary["jobs"], flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "tau":
        step_tau()
    else:
        step_product(sys.argv[2])

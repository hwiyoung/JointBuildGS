"""PHD-STAGE2-PROPAGATION-PREMEASURE-v1 step 3 (jointbuildgs:dev, CPU, no training): marks, locations, per-surface
counts (item 3), in-surface distances (item 4), the candidate grid (items 5, 6) and the injected-face check (item 7).

  python measure.py <M_N|M_B|L_N|L_B> [--map-view auto|<stem>]
  mounts: /artifacts/JointBuildGS (ro), /repo (ro), /out (this task's payload, rw)

Rules: configs/phd/stage2_propagation_premeasure_v1/premeasure.json (location_rules, mark_rule, distance_rules, grid).
Inputs per setting: surface meshes (surfaces.py), triangle-id maps (render_ids.py, depth identical to the prior maps),
the stage-2 maps of r5/r6 (conf = A, mvs, prior_<setting>, tau_<M|L>), the sparse_txt cameras of the prior renders.
Writes /out/measure/<setting>/: locations.npz, surfaces.csv, grid.csv, distance.csv, pixels.json, check_a.json,
injected.csv, map_<view>.npz and summary.json."""
import argparse
import csv
import json
import time
from pathlib import Path

import numpy as np
from matplotlib.tri import Triangulation
from scipy.ndimage import distance_transform_edt
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

ART = Path("/artifacts/JointBuildGS")
V2 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-VERIFY-v2"
S1 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
S2 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1"
MAPS = S2 / "inputs/maps"
SPARSE = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
CFG = json.loads(Path("/repo/configs/phd/stage2_propagation_premeasure_v1/premeasure.json").read_text())
TAU_V = {k: v for k, v in json.loads((V2 / "out_v2_data/checks_v2.json").read_text())["handover"].items() if k in ("tau_L", "tau_M")}
PJ = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
RECT = np.array(PJ["als_crop_local_xy"], float)
TRAIN = json.loads((S2 / "runs/P_M_N/model/monitor/meta.json").read_text())["train_views"]
SP = float(CFG["location_rules"]["spacing_m"])
WALL_NZ = 0.5
GRID = CFG["grid"]
Q_LIST, K_LIST, PCT_LIST = GRID["majority"], GRID["min_evidence_locations"], GRID["max_distance_percentiles"]
KMAX = max(K_LIST)
from propagation_rule import (J_AGREE, J_CONFLICT, J_INSUFF, J_MIXED, J_NAMES, ST_INVISIBLE, ST_MISSING, ST_SUPPORT,  # noqa: E402,F401
                              V_AGREE, V_CONFLICT, csr as _csr, grid_edges as _edges, judge as _judge, location_state)


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
            imgs[Path(t[9]).stem] = dict(q=[float(x) for x in t[1:5]], t=np.array([float(x) for x in t[5:8]]), cam=int(t[8]))
    return cams, imgs


CAMS, IMGS = load_cameras()


def view_rays(stem, flat_idx):
    """R^T (x, y, 1) at the pixel centres of flat_idx (full resolution) and the camera centre."""
    im = IMGS[stem]; cam = CAMS[im["cam"]]; fx, fy, cx, cy = cam["p"]; W = cam["W"]
    R = q2R(im["q"]); C = -R.T @ im["t"]
    v, u = np.divmod(flat_idx, W)
    xn = (u + 0.5 - cx) / fx; yn = (v + 0.5 - cy) / fy
    d = np.stack([R[0, k] * xn + R[1, k] * yn + R[2, k] for k in range(3)], 1)
    return d, C


# --------------------------------------------------------------------------------------------- location builders
class Lod2Locations:
    """Square cells in each polygon's own plane. Members: cell centre inside the polygon and inside the crop rectangle."""

    def __init__(self, mesh, surf_rows):
        V, F, ts = mesh["V"], mesh["F"].astype(np.int64), mesh["tri_surface"]
        self.rows = {r["id"]: r for r in surf_rows}
        tri_xy_min = V[F][:, :, :2].min(1); tri_xy_max = V[F][:, :, :2].max(1)
        touch = (tri_xy_max[:, 0] >= RECT[0, 0]) & (tri_xy_min[:, 0] <= RECT[1, 0]) & (tri_xy_max[:, 1] >= RECT[0, 1]) & (tri_xy_min[:, 1] <= RECT[1, 1])
        self.frames, self.center, self.area, self.surface, self.grid_ij = {}, [], [], [], []
        self.extra = {}
        n_loc = 0
        for s in np.unique(ts[touch]):
            r = self.rows[int(s)]
            if r["kind"] not in ("roof", "wall", "ground", "step"):
                continue
            tris = F[ts == s]
            n = np.array(r["normal"], float)
            e1 = np.cross([0.0, 0.0, 1.0], n)
            e1 = e1 / np.linalg.norm(e1) if np.linalg.norm(e1) > 1e-6 else np.array([1.0, 0.0, 0.0])
            e2 = np.cross(n, e1); e2 /= np.linalg.norm(e2)
            o = V[tris[0, 0]]
            uv = np.stack([(V[tris] - o) @ e1, (V[tris] - o) @ e2], -1)            # [T, 3, 2]
            i0, j0 = np.floor(uv[..., 0].min() / SP).astype(int) - 1, np.floor(uv[..., 1].min() / SP).astype(int) - 1
            i1, j1 = np.floor(uv[..., 0].max() / SP).astype(int) + 1, np.floor(uv[..., 1].max() / SP).astype(int) + 1
            ni, nj = i1 - i0 + 1, j1 - j0 + 1
            cu = (np.arange(i0, i1 + 1) + 0.5) * SP; cv = (np.arange(j0, j1 + 1) + 0.5) * SP
            CU, CV = np.meshgrid(cu, cv, indexing="ij")
            inside = np.zeros((ni, nj), bool)
            for t in uv:     # barycentric test of every cell centre in the triangle's box
                a, b, c = t
                lo = np.floor((t.min(0) / SP)).astype(int) - np.array([i0, j0]); hi = np.floor((t.max(0) / SP)).astype(int) - np.array([i0, j0]) + 1
                lo = np.maximum(lo, 0); hi = np.minimum(hi, [ni - 1, nj - 1])
                pu = CU[lo[0]:hi[0] + 1, lo[1]:hi[1] + 1]; pv = CV[lo[0]:hi[0] + 1, lo[1]:hi[1] + 1]
                den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
                if abs(den) < 1e-12:
                    continue
                l1 = ((b[1] - c[1]) * (pu - c[0]) + (c[0] - b[0]) * (pv - c[1])) / den
                l2 = ((c[1] - a[1]) * (pu - c[0]) + (a[0] - c[0]) * (pv - c[1])) / den
                l3 = 1 - l1 - l2
                inside[lo[0]:hi[0] + 1, lo[1]:hi[1] + 1] |= (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9)
            P3 = o[None, None, :] + CU[..., None] * e1 + CV[..., None] * e2
            incrop = (P3[..., 0] >= RECT[0, 0]) & (P3[..., 0] <= RECT[1, 0]) & (P3[..., 1] >= RECT[0, 1]) & (P3[..., 1] <= RECT[1, 1])
            member = inside & incrop
            loc = np.full((ni, nj), -1, np.int64)
            k = int(member.sum())
            if k:
                loc[member] = np.arange(n_loc, n_loc + k)
                self.center.append(P3[member]); self.area.append(np.full(k, SP * SP)); self.surface.append(np.full(k, s))
                ii, jj = np.nonzero(member); self.grid_ij.append(np.stack([ii, jj], 1))
                _, near = distance_transform_edt(~member, return_indices=True)
                nearest = loc[near[0], near[1]]
                n_loc += k
            else:
                nearest = None
            self.frames[int(s)] = dict(o=o, e1=e1, e2=e2, i0=i0, j0=j0, ni=ni, nj=nj, loc=loc, nearest=nearest, P3=P3)
        self.n_grid = n_loc
        self.center = np.concatenate(self.center) if self.center else np.zeros((0, 3))
        self.area = np.concatenate(self.area) if self.area else np.zeros(0)
        self.surface = np.concatenate(self.surface).astype(np.int64) if self.surface else np.zeros(0, np.int64)
        self.extra_rows = []

    def extra_location(self, s, X):
        """one location for a polygon without a member cell (tiny or cut by the crop), at the mean of its first pixels."""
        if s not in self.extra:
            self.extra[s] = self.n_grid + len(self.extra_rows)
            r = self.rows[int(s)]
            self.extra_rows.append(dict(surface=int(s), center=X.mean(0), area=min(SP * SP, r["area_mesh_m2"])))
        return self.extra[s]

    def locate(self, surf, X):
        out = np.full(len(surf), -1, np.int64)
        for s in np.unique(surf):
            m = surf == s
            fr = self.frames.get(int(s))
            if fr is None:
                continue
            if fr["nearest"] is None:
                out[m] = self.extra_location(int(s), X[m]); continue
            d = X[m] - fr["o"]
            i = np.clip(np.floor((d @ fr["e1"]) / SP).astype(np.int64) - fr["i0"], 0, fr["ni"] - 1)
            j = np.clip(np.floor((d @ fr["e2"]) / SP).astype(np.int64) - fr["j0"], 0, fr["nj"] - 1)
            out[m] = fr["nearest"][i, j]
        return out

    def finalize(self):
        if self.extra_rows:
            self.center = np.concatenate([self.center, np.array([r["center"] for r in self.extra_rows])])
            self.area = np.concatenate([self.area, np.array([r["area"] for r in self.extra_rows])])
            self.surface = np.concatenate([self.surface, np.array([r["surface"] for r in self.extra_rows], np.int64)])
        self.n = len(self.area)

    def graph(self):
        """16-neighbourhood graph of the member cells of each polygon (block diagonal: no edge between polygons)."""
        rows, cols, w = [], [], []
        for s, fr in self.frames.items():
            loc = fr["loc"]
            if fr["nearest"] is None:
                continue
            _edges(loc, fr["P3"], rows, cols, w)
        return _csr(rows, cols, w, self.n)


class TinLocations:
    """Square cells of one XY grid over the crop rectangle; a cell belongs to the building surface of the TIN triangle
    under its centre (ground surfaces and steep triangles own no location)."""

    def __init__(self, mesh, surf_rows):
        V, F, ts, tn = mesh["V"], mesh["F"].astype(np.int64), mesh["tri_surface"], mesh["tri_normal"]
        self.rows = {r["id"]: r for r in surf_rows}
        building = np.array([self.rows.get(int(s), {}).get("kind") == "building" if s >= 0 else False for s in range(ts.max() + 1)])
        self.building = building
        x0, y0 = RECT[0]; self.x0, self.y0 = x0, y0
        self.ni = int(np.ceil((RECT[1, 0] - x0) / SP)); self.nj = int(np.ceil((RECT[1, 1] - y0) / SP))
        cx = x0 + (np.arange(self.ni) + 0.5) * SP; cy = y0 + (np.arange(self.nj) + 0.5) * SP
        CX, CY = np.meshgrid(cx, cy, indexing="ij")
        tri = Triangulation(V[:, 0], V[:, 1], F).get_trifinder()(CX, CY)
        tri = np.asarray(tri, np.int64)
        owner = np.where(tri >= 0, ts[np.maximum(tri, 0)], -1).astype(np.int64)
        owner = np.where((owner >= 0) & building[np.maximum(owner, 0)], owner, -1)
        # height of the centre on its triangle's plane, and the 3D area of the cell on the TIN
        n = tn[np.maximum(tri, 0)].astype(np.float64); p0 = V[F[np.maximum(tri, 0), 0]]
        nz = np.where(np.abs(n[..., 2]) > 1e-6, n[..., 2], 1e-6)
        CZ = p0[..., 2] - (n[..., 0] * (CX - p0[..., 0]) + n[..., 1] * (CY - p0[..., 1])) / nz
        self.P3 = np.stack([CX, CY, CZ], -1)
        member = owner >= 0
        self.loc = np.full((self.ni, self.nj), -1, np.int64)
        self.loc[member] = np.arange(int(member.sum()))
        self.owner = owner
        self.n_grid = int(member.sum())
        self.center = self.P3[member]
        self.area = (SP * SP / np.abs(nz))[member]
        self.surface = owner[member]
        self.trees = {}
        self.extra, self.extra_rows = {}, []

    def locate(self, surf, X):
        i = np.clip(np.floor((X[:, 0] - self.x0) / SP).astype(np.int64), 0, self.ni - 1)
        j = np.clip(np.floor((X[:, 1] - self.y0) / SP).astype(np.int64), 0, self.nj - 1)
        out = np.where(self.owner[i, j] == surf, self.loc[i, j], -1)
        bad = np.nonzero(out < 0)[0]
        for s in np.unique(surf[bad]):
            m = bad[surf[bad] == s]
            if s not in self.trees:
                ids = np.nonzero(self.surface == s)[0]
                self.trees[s] = (cKDTree(self.center[ids, :2]), ids) if len(ids) else None
            tr = self.trees[s]
            if tr is None:
                if s not in self.extra:
                    self.extra[s] = self.n_grid + len(self.extra_rows)
                    r = self.rows[int(s)]
                    self.extra_rows.append(dict(surface=int(s), center=X[m].mean(0), area=r["area_mesh_m2"]))
                out[m] = self.extra[s]
            else:
                _, k = tr[0].query(X[m, :2]); out[m] = tr[1][k]
        return out

    def finalize(self):
        if self.extra_rows:
            self.center = np.concatenate([self.center, np.array([r["center"] for r in self.extra_rows])])
            self.area = np.concatenate([self.area, np.array([r["area"] for r in self.extra_rows])])
            self.surface = np.concatenate([self.surface, np.array([r["surface"] for r in self.extra_rows], np.int64)])
        self.n = len(self.area)

    def graph(self):
        rows, cols, w = [], [], []
        _edges(self.loc, self.P3, rows, cols, w, owner=self.owner)
        return _csr(rows, cols, w, self.n)


# --------------------------------------------------------------------------------------------- per-view pass
def view_pass(setting, stem, locs, surf_kind_arr, tri_surface, tri_normal, tau_v, impl_tau, locate=True):
    tri = np.load(Path("/out/ids") / setting / f"{stem}.npz")["tri"].reshape(-1)
    P = np.load(MAPS / f"prior_{setting}/raw_depth/{stem}.npy").reshape(-1)
    A = np.load(MAPS / f"conf/raw_depth/{stem}.npy").reshape(-1)
    M = np.load(MAPS / f"mvs/raw_depth/{stem}.npy").reshape(-1)
    hit = tri >= 0
    surf = np.where(hit, tri_surface[np.maximum(tri, 0)], -1)
    prior = np.isfinite(P)
    kind = np.where(surf >= 0, surf_kind_arr[np.maximum(surf, 0)], -1)      # 1 building surface, 0 non-building surface
    pix = dict(prior_px=int(prior.sum()), building_px=int((prior & (kind == 1)).sum()), nonbuilding_surface_px=int((prior & (kind == 0)).sum()),
               steep_px=int((prior & (surf == -2)).sum()), hit_outside_prior_px=int((hit & ~prior).sum()), no_hit_px=int((~hit).sum()))
    idx = np.nonzero(prior & (kind == 1))[0]
    d, C = view_rays(stem, idx)
    X = C[None, :] + P[idx, None].astype(np.float64) * d
    s = surf[idx].astype(np.int64)
    n = tri_normal[tri[idx]].astype(np.float64) if tri_normal is not None else None
    nd = np.abs((n * d).sum(1)); nz = np.abs(n[:, 2])
    f = np.where(nz >= WALL_NZ, nd / np.maximum(nz, 1e-6), nd)
    a1 = A[idx] == 1
    r = np.abs(M[idx] - P[idx])
    agree = a1 & (r * f <= tau_v)
    conflict = a1 & ~agree
    it = impl_tau[idx] if impl_tau is not None else None
    chk = {}
    if it is not None:
        has = np.isfinite(it)
        impl_agree = a1 & has & (r <= it)
        chk = dict(support_px=int(a1.sum()), support_px_without_impl_width=int((a1 & ~has).sum()),
                   mark_differs_px=int((a1 & has & (impl_agree != agree)).sum()),
                   own_conflict_impl_agree_px=int((a1 & has & impl_agree & conflict).sum()),
                   own_agree_impl_conflict_px=int((a1 & has & ~impl_agree & agree).sum()),
                   prior_building_px_without_impl_width=int((~has).sum()))
    if not locate:
        return dict(pix=pix, chk=chk)
    loc = locs.locate(s, X)
    keep = loc >= 0
    pix["building_px_without_location"] = int((~keep).sum())
    return dict(idx=idx[keep], loc=loc[keep], a1=a1[keep], agree=agree[keep], conflict=conflict[keep], pix=pix, chk=chk)


def accumulate(n_loc_max, res):
    loc = res["loc"]
    n_pix = np.bincount(loc, minlength=n_loc_max)
    n_a1 = np.bincount(loc, weights=res["a1"], minlength=n_loc_max)
    n_ag = np.bincount(loc, weights=res["agree"], minlength=n_loc_max)
    n_cf = np.bincount(loc, weights=res["conflict"], minlength=n_loc_max)
    return n_pix.astype(np.int32), n_a1.astype(np.int32), n_ag.astype(np.int32), n_cf.astype(np.int32)


# --------------------------------------------------------------------------------------------- rule
def judge(k_dist, k_vote, n_found, q, k, r):
    """see propagation_rule.judge (n_found is unused, kept for the callers)."""
    return _judge(k_dist, k_vote, q, k, r)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("setting"); ap.add_argument("--map-view", default="auto"); args = ap.parse_args()
    setting = args.setting
    t0 = time.time()
    OUT = Path("/out/measure") / setting; OUT.mkdir(parents=True, exist_ok=True)
    mesh = dict(np.load(Path("/out/surfaces") / setting / "mesh.npz"))
    sj = json.loads((Path("/out/surfaces") / setting / "surfaces.json").read_text())
    rows = sj["surfaces"]
    is_lod2 = setting.startswith("M")
    tau_v = TAU_V["tau_M" if is_lod2 else "tau_L"]
    ts = mesh["tri_surface"]
    max_id = int(max(r["id"] for r in rows)) + 1
    kind_arr = np.zeros(max_id, np.int8)
    for r in rows:
        # building faces: every LoD2 polygon kind (the LoD2 'ground' is the building's floor polygon) / TIN 'building'
        # surfaces only (the TIN 'ground' kind is terrain)
        kind_arr[r["id"]] = 1 if r["kind"] in (("roof", "wall", "ground", "step") if is_lod2 else ("building",)) else 0
    if is_lod2:
        # tri_normal of a LoD2 pixel = its polygon normal (the conversion uses the face, as stage 2 does)
        pn = np.zeros((max_id, 3), np.float32)
        for r in rows:
            pn[r["id"]] = r["normal"]
        tri_normal = pn[ts]
        locs = Lod2Locations(mesh, rows)
    else:
        tri_normal = mesh["tri_normal"]
        locs = TinLocations(mesh, rows)
    print(setting, "grid locations", locs.n_grid, f"{time.time() - t0:.0f}s", flush=True)
    impl_key = "tau_M" if is_lod2 else "tau_L"
    per_view, pix_rows, chk_rows = {}, {}, {}
    all_views = sorted(p.stem for p in (Path("/out/ids") / setting).glob("*.npz"))
    for stem in all_views:
        impl_tau = np.load(MAPS / f"{impl_key}/raw_depth/{stem}.npy").reshape(-1)
        res = view_pass(setting, stem, locs, kind_arr, ts, tri_normal, tau_v, impl_tau, locate=stem in TRAIN)
        pix_rows[stem] = res["pix"]; chk_rows[stem] = res["chk"]
        if stem in TRAIN:
            per_view[stem] = res
        print(setting, stem, res["pix"], res["chk"], f"{time.time() - t0:.0f}s", flush=True)
    locs.finalize()
    NL = locs.n
    views = [v for v in TRAIN if v in per_view]
    acc = {v: accumulate(NL, per_view[v]) for v in views}
    n_pix = np.stack([acc[v][0] for v in views]); n_a1 = np.stack([acc[v][1] for v in views])
    n_ag = np.stack([acc[v][2] for v in views]); n_cf = np.stack([acc[v][3] for v in views])
    state, vote, n_obs, n_meas = location_state(n_pix, n_a1, n_ag, n_cf)
    E_loc = np.where(n_obs > 0, n_meas / np.maximum(n_obs, 1), np.nan)
    surface = locs.surface
    print(setting, "locations", NL, "support", int((state == 1).sum()), "missing", int((state == 2).sum()), "invisible", int((state == 0).sum()), f"{time.time() - t0:.0f}s", flush=True)

    # ---- item 4: in-surface distance to the nearest support location
    G = locs.graph()
    sup = np.nonzero(state == ST_SUPPORT)[0]
    mis = np.nonzero(state == ST_MISSING)[0]
    near = dijkstra(G, directed=False, indices=sup, min_only=True) if len(sup) else np.full(NL, np.inf)
    near = np.asarray(near)
    sup_on_surface = np.zeros(NL, bool)
    has_sup = np.zeros(int(surface.max()) + 1, bool); has_sup[surface[sup]] = True
    sup_on_surface = has_sup[surface]
    d_mis = near[mis]
    ok = np.isfinite(d_mis)
    pct = {p: float(np.percentile(d_mis[ok], p)) for p in PCT_LIST} if ok.any() else {p: float("nan") for p in PCT_LIST}
    rmax = max(pct.values())
    print(setting, "missing with support on the surface", int(ok.sum()), "of", len(mis), "percentiles", pct, f"{time.time() - t0:.0f}s", flush=True)

    # ---- nearest KMAX support locations within rmax for every missing location (same surface, graph distance)
    k_dist = np.full((len(mis), KMAX), np.inf); k_vote = np.full((len(mis), KMAX), -1, np.int8)
    mis_pos = {int(m): i for i, m in enumerate(mis)}
    for s in np.unique(surface[mis]):
        ids = np.nonzero(surface == s)[0]
        m_s = ids[state[ids] == ST_MISSING]; s_s = ids[state[ids] == ST_SUPPORT]
        if len(s_s) == 0 or len(m_s) == 0:
            continue
        Gs = G[ids][:, ids]
        pos = {int(g): i for i, g in enumerate(ids)}
        src = np.array([pos[int(g)] for g in m_s]); tgt = np.array([pos[int(g)] for g in s_s])
        for b0 in range(0, len(src), 256):
            bs = src[b0:b0 + 256]
            D = dijkstra(Gs, directed=False, indices=bs, limit=rmax + 1e-9)[:, tgt]
            kk = min(KMAX, D.shape[1])
            part = np.argpartition(D, kk - 1, axis=1)[:, :kk] if D.shape[1] > kk else np.tile(np.arange(D.shape[1]), (len(bs), 1))
            pd = np.take_along_axis(D, part, 1)
            # order by distance, ties by location index
            order = np.lexsort((s_s[part], pd), axis=1)
            part = np.take_along_axis(part, order, 1); pd = np.take_along_axis(pd, order, 1)
            rows_i = np.array([mis_pos[int(g)] for g in m_s[b0:b0 + 256]])
            k_dist[rows_i, :kk] = pd
            k_vote[rows_i, :kk] = np.where(np.isfinite(pd), vote[s_s[part]], -1)
    print(setting, "k-nearest done", f"{time.time() - t0:.0f}s", flush=True)

    # ---- items 5, 6: the grid
    area = locs.area
    a_mis = area[mis]
    kind_of = {r["id"]: r["kind"] for r in rows}
    target_of = {r["id"]: bool(r["target"]) for r in rows}
    surf_area = np.bincount(surface, weights=area, minlength=int(surface.max()) + 1)
    total_area = float(area.sum())
    grid_rows, J_store = [], {}
    for q in Q_LIST:
        for k in K_LIST:
            for p in PCT_LIST:
                j = judge(k_dist, k_vote, None, q, k, pct[p])
                J_store[(q, k, p)] = j
                row = dict(majority=round(q, 4), min_evidence=k, max_distance_percentile=p, max_distance_m=pct[p], n_missing=int(len(mis)))
                for code, name in enumerate(J_NAMES):
                    row[f"n_{name}"] = int((j == code).sum()); row[f"area_{name}_m2"] = float(a_mis[j == code].sum())
                cs = np.unique(surface[mis][j == J_CONFLICT])
                row["conflict_surfaces"] = int(len(cs))
                row["conflict_surfaces_area_m2"] = float(surf_area[cs].sum())
                row["conflict_share_of_those_surfaces"] = row["area_conflict_m2"] / row["conflict_surfaces_area_m2"] if len(cs) else 0.0
                row["conflict_share_of_all_building_surfaces"] = row["area_conflict_m2"] / total_area
                grid_rows.append(row)
    with open(OUT / "grid.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(grid_rows[0].keys())); w.writeheader(); [w.writerow(r) for r in grid_rows]

    # ---- item 3: per surface
    ref = GRID["reference"]
    jref = J_store[(ref["majority"], ref["min_evidence_locations"], ref["max_distance_percentile"])]
    jloc = np.full(NL, -1, np.int8); jloc[mis] = jref
    srows = []
    for s in np.unique(surface):
        m = surface == s
        sup_m = m & (state == ST_SUPPORT); mis_m = m & (state == ST_MISSING)
        nsup = int(sup_m.sum())
        dm = near[mis_m]
        srow = dict(surface=int(s), kind=kind_of.get(int(s), "?"), target=target_of.get(int(s), False),
                    n_locations=int(m.sum()), area_m2=float(area[m].sum()), n_support=nsup,
                    agree_share=float((vote[sup_m] == V_AGREE).mean()) if nsup else float("nan"),
                    conflict_share=float((vote[sup_m] == V_CONFLICT).mean()) if nsup else float("nan"),
                    n_missing=int(mis_m.sum()), n_invisible=int((m & (state == ST_INVISIBLE)).sum()),
                    area_support_m2=float(area[sup_m].sum()), area_missing_m2=float(area[mis_m].sum()),
                    missing_distance_p50_m=float(np.median(dm[np.isfinite(dm)])) if np.isfinite(dm).any() else float("nan"),
                    missing_without_support=int((mis_m & ~sup_on_surface).sum()))
        for code, name in enumerate(J_NAMES):
            srow[f"ref_{name}"] = int((m & (jloc == code)).sum())
        srows.append(srow)
    with open(OUT / "surfaces.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(srows[0].keys())); w.writeheader(); [w.writerow(r) for r in srows]

    # ---- item 4 table
    kinds_loc = np.array([kind_of.get(int(s), "?") for s in surface])
    drow = []
    for grp, sel in (("all", np.ones(len(mis), bool)), ("roof", np.isin(kinds_loc[mis], ["roof", "building"])),
                     ("wall", np.isin(kinds_loc[mis], ["wall", "step"])), ("ground", kinds_loc[mis] == "ground")):
        x = d_mis[sel]; f = np.isfinite(x)
        drow.append(dict(group=grp, n_missing=int(sel.sum()), n_with_support=int(f.sum()), n_without_support=int((~f).sum()),
                         area_without_support_m2=float(a_mis[sel][~f].sum()),
                         **{f"p{p}_m": float(np.percentile(x[f], p)) if f.any() else float("nan") for p in (10, 25, 50, 75, 90, 99)},
                         max_m=float(x[f].max()) if f.any() else float("nan")))
    with open(OUT / "distance.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(drow[0].keys())); w.writeheader(); [w.writerow(r) for r in drow]

    # ---- item 7: injected surfaces
    inj_rows = []
    if setting == "M_B":
        inj = [3396]
    elif setting == "L_B":
        inj = [r["id"] for r in rows if r["kind"] == "building" and r["raised_share"] >= 0.5]
    else:
        inj = []
    for s in inj:
        m_s = surface[mis] == s
        base = dict(surface=int(s), n_support=int(((surface == s) & (state == ST_SUPPORT)).sum()),
                    support_conflict_share=float((vote[(surface == s) & (state == ST_SUPPORT)] == V_CONFLICT).mean()) if ((surface == s) & (state == ST_SUPPORT)).any() else float("nan"),
                    n_missing=int(m_s.sum()), area_missing_m2=float(a_mis[m_s].sum()))
        for (q, k, p), j in J_STORE_ITEMS(J_store):
            rr = dict(base, majority=round(q, 4), min_evidence=k, max_distance_percentile=p)
            for code, name in enumerate(J_NAMES):
                rr[f"n_{name}"] = int((j[m_s] == code).sum())
            inj_rows.append(rr)
    if inj_rows:
        with open(OUT / "injected.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(inj_rows[0].keys())); w.writeheader(); [w.writerow(r) for r in inj_rows]

    # ---- map of one training view (figure panel 3)
    tgt_ids = np.array([r["id"] for r in rows if r["target"]])
    tmis = np.isin(surface, tgt_ids) & (state == ST_MISSING)
    counts = {v: int(tmis[per_view[v]["loc"]].sum()) for v in views}
    mv = max(counts, key=counts.get) if args.map_view == "auto" else args.map_view
    res = per_view[mv]
    np.savez_compressed(OUT / f"map_{mv}.npz", idx=res["idx"].astype(np.int32), loc=res["loc"].astype(np.int32), a1=res["a1"], agree=res["agree"],
                        conflict=res["conflict"])
    np.savez_compressed(OUT / "locations.npz", center=locs.center, area=area, surface=surface, state=state, vote=vote, E_loc=E_loc,
                        n_obs=n_obs, n_meas=n_meas, near=near, jref=jloc, mis=mis, k_dist=k_dist, k_vote=k_vote,
                        pix_sum=n_pix.sum(0), a1_sum=n_a1.sum(0), agree_sum=n_ag.sum(0), conflict_sum=n_cf.sum(0))
    (OUT / "pixels.json").write_text(json.dumps(dict(all_views=pix_rows, train_views=views), indent=1))
    (OUT / "check_a.json").write_text(json.dumps(chk_rows, indent=1))
    summ = dict(setting=setting, tau_v=tau_v, spacing_m=SP, n_locations=int(NL), n_grid_locations=int(locs.n_grid), n_extra_locations=int(NL - locs.n_grid),
                n_support=int((state == 1).sum()), n_missing=int((state == 2).sum()), n_invisible=int((state == 0).sum()),
                area_total_m2=total_area, area_support_m2=float(area[state == 1].sum()), area_missing_m2=float(area[state == 2].sum()),
                area_invisible_m2=float(area[state == 0].sum()), support_conflict_share=float((vote[state == 1] == V_CONFLICT).mean()),
                percentiles_m={str(p): v for p, v in pct.items()}, missing_without_support=int((~ok).sum()),
                map_view=mv, map_view_counts=counts, views=views, seconds=round(time.time() - t0, 1))
    (OUT / "summary.json").write_text(json.dumps(summ, indent=1))
    print(setting, "done", summ, flush=True)


def J_STORE_ITEMS(J_store):
    return sorted(J_store.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0]))


if __name__ == "__main__":
    main()

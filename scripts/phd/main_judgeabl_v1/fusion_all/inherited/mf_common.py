"""PHD-MAIN-BASELINES-v1 MVS-based fusion of Zhou et al. (2020), reproduced (order v1.1, 5.6 and 6.5): shared helpers of the CPU steps
(jointbuildgs:dev through run_cpu_bl.sh; cwd scripts/phd/main_baselines_v1, every input read-only, this payload SB read-write).

Inputs (first stage of the method; per training view, 1024 x 741, camera-z metres, NaN = none):
  prior depth   /s0/s61/export/<site>/<prior>/prior/<stem>.npy       MVS depth (observation mask 1 only)  .../mvs/<stem>.npy
  tau (depth)   .../tau/<stem>.npy                                    images  /s0/fork_inputs/s61/<site>/images/<stem>.jpg (JPEG 1024 x 741)
  cameras       the fork scene's sparse model (PINHOLE at the grid = common.Views.K; the measurement grid's camera code, order 5.6 item 5:
                pixel index i has its centre at i + 0.5; preparation check 2 showed the fork camera's ray cast = the export maps)
  prior mesh    the export's own scene: DR/s02_box/<site>/lod2_mesh.npz (every face, caps included) or als_mesh.npz, + the registration shift
                of S0/s61/box/<site>/<prior>/summary.json (the per-pixel triangle ids come from it; every view's re-cast is checked
                against the export prior map)
Plan cells: 0.25 m in the local frame (x = E - 690953, y = N - 5336071), over the box range rectangle + 10 m.
scientific_verdict: null."""
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo")
sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1")
from common import GRID_H, GRID_W, Scene, Views, basis  # noqa: E402

PH = Path("/ph")
SB = PH / "main_baselines_v1/PHD-MAIN-BASELINES-v1"
S0, S1, DR = Path("/s0"), Path("/out"), Path("/dr")
SITES = ("B0_b10", "B173nb_b10", "B173_b0", "R1rep_b10")
SITE_KO = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "B173_b0": "B173만", "R1rep_b10": "R1"}
H, W = GRID_H, GRID_W
CELL = 0.25

# the reproduction's rules and values (order 6.5; the paper check is SB/prep/mvsfuse/paper_check.json). DECISIONS_1015 = the three
# paper-faithful choices the user approved on 10-15 ("권함대로", relayed by the orchestrating session); they are in RULE below.
DECISIONS_1015 = [
    dict(id="D1015-1", what="steep prior faces are not judged",
         rule="pixels whose prior surface is steep (|n_z| < 0.5: LoD2 walls, ALS steep TIN faces) are not judged, neither in the colour test nor in "
              "the removed-building test; a plan cell takes its decision from the remaining (judged) pixels only. Extension (same decision, "
              "clarified by the orchestrating session on 10-15): the steep pixels also give no MVS - prior height difference, so the growth and "
              "the size filter's height test work on the 2.5-D top surface as in the paper",
         why="the paper's DSM has no facade heights; its facade pixels are occlusions and are not matched (p. 9 l. 183-185, 194-195)"),
    dict(id="D1015-2", what="growth removes small new pieces",
         rule="in each growth iteration the 8-connected components of the new change cells below 1 x 1 m2 (fewer than 16 cells) are removed; "
              "they stay searched and do not seed the next ring",
         why="'The irrelevant change and outliers of with a size below 1 x 1 m2 is removed' (p. 15 l. 280-281)"),
    dict(id="D1015-3", what="size test with the minimum-area rotated rectangle",
         rule="a component is kept when both sides of the minimum-area rotated rectangle around its cells (cell corners) are >= 2 m and its area "
              ">= 4 m2 (plus the 2 m median height difference, unchanged); the size filter stays after the growth",
         why="'size below 2x2 m2' (p. 17) is not tied to the grid axes; the axis-aligned extents let thin diagonal strips through"),
]
STEEP_NZ = 0.5          # D1015-1: steep face = |vertical normal component| < 0.5 (as order 5.4)
PIECE_MIN_M2 = 1.0      # D1015-2
RULE = dict(
    pairs=dict(flight="time-sorted names of the 937 posed images; a new flight starts where two consecutive capture times (from the name) "
                      "differ by more than 60 s", flight_gap_s=60.0, max_view_angle_deg=20.0, target_overlap=0.60,
               overlap="share of view i's MVS points (export mvs map, every 4th pixel in x and y) that project inside view j's frame "
                       "(prior-free, so both priors get the same pairs)", overlap_stride_px=4, min_overlap_points=200,
               tie="smaller view angle, then name"),
    pixel=dict(correspondence="the prior surface point of the pixel projected into the pair image; the pixel within +-2 px (5 x 5 candidates) "
                              "with the largest max(0, NCC) of the 3 x 3 grey patches; ties (incl. all 0) -> the candidate nearest to the projection",
               search_px=2, ncc_window=3, grey="0.299 R + 0.587 G + 0.114 B (the paper's NCC is on intensity)", occlusion_tolerance_m=0.05,
               occlusion="ray from the pair camera to the prior point hits the prior surface more than 0.05 m before it -> not judged in that pair",
               frame="the 3 x 3 patch of the pixel and the 7 x 7 search window in the pair image must lie inside the frames",
               steep_not_judged="D1015-1: pixels whose prior surface has |n_z| < 0.5 are not judged (colour test and removed-building test)",
               steep_nz=STEEP_NZ,
               colour="RMS over R, G, B (0-255) of the pixel and its correspondence", colour_threshold=25.0, colour_threshold_reference=[20.0, 30.0]),
    opening=dict(relief_height_m=2.0, factor=0.7, factor_source="10 / 14.2 (the paper's erosion size / relief displacement of 2 m)",
                 displacement="per pair: median over the judged pixels (up to 20,000, strided) of |(p_j(X + 2 m up) - p_j(X)) - (p_i(X + 2 m up) - p_i(X))|, "
                              "the parallax change of a 2 m height change in that pair's geometry",
                 kernel="square k x k, k = round(0.7 x displacement); k < 2 -> no opening", operation="opening (erosion then dilation) of the view's "
                 "binary change image (judged and change = 1, else 0); the result is kept on judged pixels only"),
    cells=dict(cell_m=CELL, view_vote="a paired view says 'change' for a cell when more than half of its judged pixels whose prior point falls in "
                                     "the cell are change after the opening",
               cell_vote="change cell: more than half of the paired views that judge the cell say change, and at least 2 views judge it",
               min_views=2),
    removal=dict(share=0.95, rule="per prior building region: every non-steep pixel (D1015-1) of the paired training views whose prior hit is on the building is re-projected "
                                  "through the ground height (ray / horizontal plane), its correspondence found as above (occlusion only by other buildings); "
                                  "if at least 95 % of those pixels (pooled over the views) have a colour RMS at or below the threshold, every plan cell "
                                  "of the building is a change cell",
                 region_LoD2="faces of one building (tri_building)", region_ALS="vertex-connected components of the building_tri triangles",
                 ground_LoD2="median over the building's wall surfaces of the lowest vertex height", ground_ALS="median centroid height of the "
                             "ground (non-building) TIN triangles whose centroid lies in the 2 m band around the building's plan cells", band_m=2.0),
    growth=dict(ring_m=1.0, step_m=2.0, dz_m=2.0, dz_reference_m=1.5, piece_min_m2=PIECE_MIN_M2,
                rule="search the cells within 1 m of the change cells; a searched prior cell whose median MVS - prior height difference exceeds 2 m in "
                     "magnitude becomes a change cell; components of the new cells below 1 m2 are removed (D1015-2); then search within 2 m of the "
                     "new change cells; a searched cell is not searched again; stop when nothing is added",
                cell_dz="per cell: median over every training view's non-steep pixels (|n_z| >= 0.5, D1015-1) whose prior point falls in the cell and that have MVS of "
                        "(MVS depth - prior depth) x ray z (the height difference along the pixel's ray)"),
    size=dict(min_extent_m=2.0, min_area_m2=4.0, min_height_m=2.0, connectivity=8, stage="after the growth (the paper's end filter, 3.3)",
              extent="D1015-3: both sides of the minimum-area rotated rectangle (cv2.minAreaRect) around the component's cell corners",
              rule="8-connected components of the change cells; kept when both sides of the minimum-area rotated rectangle are >= 2 m and the area "
                   ">= 4 m2, and the median over its cells with MVS of |cell height difference| is >= 2 m; when more than half of its cells have no "
                   "MVS the height is not seen and the component is kept (counted)"),
    update="per training view: a pixel whose prior hit lies in a change cell -> MVS depth (none -> empty); other prior pixels -> prior depth; "
           "pixels without prior -> MVS depth (none -> empty). The cell height difference of the growth and the size filter uses the non-steep "
           "prior pixels only (D1015-1, the 2.5-D top surface)",
    decisions_1015=[d["id"] for d in DECISIONS_1015],
    filters="NDVI and road / river masks are not applied (no near-infrared image, no topographic map); the change area outside the evaluation "
            "range is recorded")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def jdump(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))


def capture_time(stem):
    return dt.datetime.strptime(stem.split("_")[1], "%Y%m%d%H%M%S")


def flights(gap_s=RULE["pairs"]["flight_gap_s"]):
    """stem -> flight number over the 937 posed images (time-sorted names), and the flight table."""
    names = [n.rsplit(".", 1)[0] for n in Views().names]
    names.sort(key=lambda s: (capture_time(s), s))
    fl, k, prev, rows = {}, 0, None, []
    for s in names:
        t = capture_time(s)
        if prev is not None and (t - capture_time(prev)).total_seconds() > gap_s:
            k += 1
        fl[s] = k
        prev = s
    for f in range(k + 1):
        m = [s for s in names if fl[s] == f]
        rows.append(dict(flight=f, images=len(m), first=m[0], last=m[-1]))
    return fl, rows


def views(site):
    """the site's measurement cameras (the fork scene's sparse model; names '<stem>.jpg') and the training stems."""
    V = Views(sparse=S0 / "fork_inputs/s61" / site / "scene_LoD2/sparse/0")
    split = json.loads((S0 / "fork_inputs/s61" / site / "split.json").read_text())
    return V, list(split["train"]), list(split["test"])


def ex_dir(site, prior):
    return S0 / "s61/export" / site / prior


def load_map(site, prior, kind, stem):
    return np.load(ex_dir(site, prior) / kind / f"{stem}.npy")


def read_rgb(site, stem):
    import cv2
    img = cv2.imread(str(S0 / "fork_inputs/s61" / site / "images" / f"{stem}.jpg"), cv2.IMREAD_COLOR)
    if img is None or img.shape[:2] != (H, W):
        raise RuntimeError(f"image {stem}: {None if img is None else img.shape}")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)


def grey(rgb):
    return (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype(np.float32)


def local_stats(g):
    """3 x 3 mean and standard deviation (interior pixels are used only)."""
    import cv2
    m = cv2.blur(g, (3, 3), borderType=cv2.BORDER_REFLECT)
    s2 = cv2.blur(g * g, (3, 3), borderType=cv2.BORDER_REFLECT) - m * m
    return m, np.sqrt(np.maximum(s2, 0.0))


def shift_of(site, prior):
    return np.asarray(json.loads((S0 / "s61/box" / site / prior / "summary.json").read_text())["registration"]["shift_applied"], np.float64)


def tri_components(F, sel):
    """vertex-connected components of the selected triangles -> component id per triangle (-1 not selected)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    f = F[sel]
    nv = int(F.max()) + 1
    r = np.concatenate([f[:, 0], f[:, 1], f[:, 2]])
    c = np.concatenate([f[:, 1], f[:, 2], f[:, 0]])
    g = coo_matrix((np.ones(len(r), np.int8), (r, c)), shape=(nv, nv))
    _, lab = connected_components(g, directed=False)
    comp = np.full(len(F), -1, np.int64)
    first = lab[f[:, 0]]
    u, inv = np.unique(first, return_inverse=True)
    comp[sel] = inv
    return comp


class Prior:
    """the export's prior surface (registered), its triangle -> building region, and the ground height of each building."""

    def __init__(self, site, prior):
        self.site, self.prior = site, prior
        md = DR / "s02_box" / site
        self.shift = shift_of(site, prior)
        if prior == "LoD2":
            m = np.load(md / "lod2_mesh.npz")
            self.V, self.F = m["V"].astype(np.float64) + self.shift, m["F"].astype(np.int64)
            self.tri_bld = m["tri_building"].astype(np.int64)
            self.tri_type = m["tri_type"].astype(np.int64)
            self.tri_surface = m["tri_surface"].astype(np.int64)
            self.building_names = [str(x) for x in m["building_names"]]
        else:
            m = np.load(md / "als_mesh.npz")
            self.V, self.F = m["V"].astype(np.float64) + self.shift, m["F"].astype(np.int64)
            self.building_tri = m["building_tri"].astype(bool)
            self.tri_bld = tri_components(self.F, self.building_tri)
            self.tri_type = None
            self.tri_surface = m["tri_surface"].astype(np.int64)
            self.building_names = None
        self.n_bld = int(self.tri_bld.max()) + 1 if (self.tri_bld >= 0).any() else 0
        nrm = np.cross(self.V[self.F[:, 1]] - self.V[self.F[:, 0]], self.V[self.F[:, 2]] - self.V[self.F[:, 0]])
        self.nz = np.abs(nrm[:, 2]) / np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)     # |vertical normal component| per triangle
        self._scene = None
        self._bscene = None

    def scene(self):
        if self._scene is None:
            self._scene = Scene(self.V, self.F)
        return self._scene

    def building_scene(self):
        """building triangles only (the occluders of the removed-building test); returns the scene and scene-triangle -> building id."""
        if self._bscene is None:
            sel = np.nonzero(self.tri_bld >= 0)[0]
            self._bscene = (Scene(self.V, self.F[sel]), self.tri_bld[sel])
        return self._bscene


class Grid:
    def __init__(self, site, margin=10.0):
        rng = json.loads((DR / "s02_box" / site / "range.json").read_text())
        P = np.asarray(rng["polygon_local"], np.float64)
        self.lo = np.floor((P.min(0) - margin) / CELL) * CELL
        hi = np.ceil((P.max(0) + margin) / CELL) * CELL
        self.nx, self.ny = int(round((hi[0] - self.lo[0]) / CELL)), int(round((hi[1] - self.lo[1]) / CELL))
        tr = np.load(S1 / "defs" / site / "top_raster.npz")
        self.eval_u, self.eval_v = tr["eval_u"].astype(np.float64), tr["eval_v"].astype(np.float64)
        self.B = basis()
        cx = self.lo[0] + (np.arange(self.nx) + 0.5) * CELL
        cy = self.lo[1] + (np.arange(self.ny) + 0.5) * CELL
        gx, gy = np.meshgrid(cx, cy)
        self.centres = np.stack([gx, gy], -1)                     # [ny, nx, 2]
        self.in_eval = self.eval_mask(self.centres.reshape(-1, 2)).reshape(self.ny, self.nx)

    def eval_mask(self, xy):
        uv = np.asarray(xy, np.float64)[:, :2] @ self.B.T
        return (uv[:, 0] >= self.eval_u[0]) & (uv[:, 0] <= self.eval_u[1]) & (uv[:, 1] >= self.eval_v[0]) & (uv[:, 1] <= self.eval_v[1])

    def cell(self, xy):
        """linear cell id (iy * nx + ix) of local XY, -1 outside the grid."""
        q = np.floor((np.asarray(xy, np.float64)[:, :2] - self.lo) / CELL)
        ok = np.isfinite(q).all(1) & (q[:, 0] >= 0) & (q[:, 0] < self.nx) & (q[:, 1] >= 0) & (q[:, 1] < self.ny)
        out = np.full(len(q), -1, np.int64)
        out[ok] = q[ok, 1].astype(np.int64) * self.nx + q[ok, 0].astype(np.int64)
        return out

    @property
    def n(self):
        return self.nx * self.ny


def raster_triangles(grid, V, F, step=0.1):
    """plan cells covered by triangles (cell centres inside the plan triangle, plus cells along the edges sampled every 0.1 m, so that steep
    and vertical faces mark the cells they stand on) -> sorted unique cell ids."""
    cells = []
    A, Bv, Cv = V[F[:, 0], :2], V[F[:, 1], :2], V[F[:, 2], :2]
    for P0, P1 in ((A, Bv), (Bv, Cv), (Cv, A)):
        L = np.linalg.norm(P1 - P0, axis=1)
        n = np.maximum(np.ceil(L / step).astype(np.int64), 1)
        rep = np.repeat(np.arange(len(F)), n + 1)
        start = np.repeat(np.cumsum(n + 1) - (n + 1), n + 1)
        off = (np.arange(int((n + 1).sum())) - start) / np.repeat(n, n + 1)
        pts = P0[rep] + (P1[rep] - P0[rep]) * off[:, None]
        cells.append(grid.cell(pts))
    # interior cell centres
    lo = np.minimum(np.minimum(A, Bv), Cv)
    hi = np.maximum(np.maximum(A, Bv), Cv)
    i0 = np.floor((lo - grid.lo) / CELL).astype(np.int64)
    i1 = np.floor((hi - grid.lo) / CELL).astype(np.int64)
    big = np.nonzero(((i1 - i0) >= 1).any(1))[0]
    for t in big:
        xs = np.arange(max(i0[t, 0], 0), min(i1[t, 0], grid.nx - 1) + 1)
        ys = np.arange(max(i0[t, 1], 0), min(i1[t, 1], grid.ny - 1) + 1)
        if len(xs) == 0 or len(ys) == 0:
            continue
        gx, gy = np.meshgrid(xs, ys)
        P = np.stack([grid.lo[0] + (gx.ravel() + 0.5) * CELL, grid.lo[1] + (gy.ravel() + 0.5) * CELL], 1)
        a, b, c = A[t], Bv[t], Cv[t]
        v0, v1, v2 = c - a, b - a, P - a
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        den = d00 * d11 - d01 * d01
        if abs(den) < 1e-12:
            continue
        d20, d21 = v2 @ v0, v2 @ v1
        uu = (d11 * d20 - d01 * d21) / den
        vv = (d00 * d21 - d01 * d20) / den
        ins = (uu >= -1e-9) & (vv >= -1e-9) & (uu + vv <= 1 + 1e-9)
        cells.append(gy.ravel()[ins] * grid.nx + gx.ravel()[ins])
    c = np.concatenate(cells) if cells else np.zeros(0, np.int64)
    return np.unique(c[c >= 0])


def disk(radius_cells):
    r = int(np.floor(radius_cells))
    y, x = np.mgrid[-r:r + 1, -r:r + 1]
    return ((x * x + y * y) <= radius_cells * radius_cells + 1e-9).astype(np.uint8)


def dilate(mask, radius_m):
    import cv2
    return cv2.dilate(mask.astype(np.uint8), disk(radius_m / CELL)) > 0


def components(mask):
    from scipy import ndimage
    lab, n = ndimage.label(mask, structure=np.ones((3, 3), int))
    return lab, n


def lod2_change_classes(site):
    """order 7.1 / stage-3 8.2 (scripts/phd/main_stage3_v1/measure8_s3.py, change(), the same rule re-implemented here without its stage-3
    imports): each LoD2 code-11 (and 13) patch is told by the ALS prior at the same GT points (ALS rows of the same unit matched by the GT
    point): the ALS patch's v3 true label agree (0) on the majority -> 'representation', conflict -> 'real_change', fewer than half of the
    patch's points with an ALS row -> 'undecided'. Returns {code: {patch: class}}."""
    def rows(prior):
        r = np.load(S1 / "defs" / site / f"rows_{prior}.npz")
        return {k: r[k] for k in ("src", "point", "patch", "code")}
    L, A = rows("LoD2"), rows("ALS")
    RA = np.load(S1 / "regions_v3" / f"regions_ext_v3_{site}_ALS.npz")
    key = lambda R_: R_["src"].astype(np.int64) * 10 ** 10 + R_["point"].astype(np.int64)
    ka, kl = key(A), key(L)
    o = np.argsort(ka)
    pos = np.searchsorted(ka[o], kl)
    hit = (pos < len(ka)) & (ka[o][np.minimum(pos, len(ka) - 1)] == kl)
    ia = np.where(hit, o[np.minimum(pos, len(ka) - 1)], -1)
    alab = np.full(len(kl), -1, np.int8)
    alab[hit] = RA["label"][A["patch"][ia[hit]]]
    out = {}
    order = np.argsort(L["patch"], kind="stable")
    sp = L["patch"][order]
    for code in (11, 13):
        pm = np.unique(L["patch"][L["code"] == code])
        cls = {}
        for p in pm:
            a, b = np.searchsorted(sp, p, "left"), np.searchsorted(sp, p, "right")
            rr = order[a:b]
            n = len(rr)
            h = hit[rr] & (alab[rr] >= 0)
            if h.sum() < 0.5 * n:
                cls[int(p)] = "undecided"
            else:
                cls[int(p)] = "representation" if (alab[rr][h] == 0).mean() >= 0.5 else "real_change"
        out[code] = cls
    return out

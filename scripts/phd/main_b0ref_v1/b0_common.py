"""PHD-MAIN-B0REF-v1 shared helpers (jointbuildgs:dev, CPU; no training, no GPU).

Frame = the study's working frame (configs/phd/main_prep_measure_v1/prep_v5.json 'frame': EPSG:25832 minus the world shift
[690953, 5336071, 604] m; uv = the box axes, u at 70 deg ccw from easting). The B0 target building is DEBY_LOD2_4959323; its LoD2
faces are the stage-0 box mesh (DR/s02_box/B0_b10/lod2_mesh.npz + the B0 LoD2 registration shift of S0/s61/box/B0_b10/LoD2, which
is [0, 0, 0]). The evaluation range is the B0 box's eval_u x eval_v (PREP/step06/boxes_v1.json). Settings: configs/phd/main_b0ref_v1/
b0ref_v1.json. scientific_verdict: null."""
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ART = Path("/art")
PH = ART / "phase-payloads/phd"
B0 = Path("/b0")
DOCS = Path("/docs")
REPO = Path("/repo")
CFG = json.loads((REPO / "configs/phd/main_b0ref_v1/b0ref_v1.json").read_text())
PCFG = json.loads((REPO / "configs/phd/main_prep_measure_v1/prep_v5.json").read_text())
SHIFT = np.array(PCFG["frame"]["world_shift_xyz_m"], np.float64)
ANG = np.deg2rad(PCFG["frame"]["u_axis_angle_degrees_ccw_from_easting"])
DR = PH / "main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
S0 = PH / "main_stage0_v1/PHD-MAIN-STAGE0-v1"
S1 = PH / "main_stage1_v1/PHD-MAIN-STAGE1-v1"
PREP = PH / "main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"
BOX = "B0_b10"
BLD = CFG["building"]
SRC = {k: ART / v for k, v in CFG["sources"].items() if isinstance(v, str)}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S %Z")


def jdump(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))


def jl(path):
    return json.loads(Path(path).read_text())


def sha256(p, chunk=1 << 22):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def basis():
    """= scripts/phd/main_stage0_v1/common.py:53-55 (v = the reflected axis)."""
    return np.array([[np.cos(ANG), np.sin(ANG)], [np.sin(ANG), -np.cos(ANG)]])


def xy_to_uv(xy):
    return np.asarray(xy, np.float64)[..., :2] @ basis().T


def box_def():
    b = jl(DR / "s02_box" / BOX / "range.json")
    return dict(u=b["u_m"], v=b["v_m"], eval_u=b["eval_u"], eval_v=b["eval_v"])


def in_rect(xy, which="eval"):
    b = box_def()
    uv = xy_to_uv(xy)
    if which == "eval":
        u, v = b["eval_u"], b["eval_v"]
    else:
        u, v = b["u"], b["v"]
    return (uv[:, 0] >= u[0]) & (uv[:, 0] <= u[1]) & (uv[:, 1] >= v[0]) & (uv[:, 1] <= v[1])


# ------------------------------------------------------------------------------------------------ point clouds
def read_geogs(raw=True):
    """GeoGS evaluation cloud r1_b1_sub002_transformed.ply (Open3D binary: double x y z, uchar r g b). raw=True: the author frame
    plus [2, -29, 0] m (the study's xy move; no height alignment) = the frame of the raw ULS (laz - world shift)."""
    p = SRC["geogs"]
    with open(p, "rb") as f:
        hdr = b""
        while b"end_header" not in hdr:
            hdr += f.readline()
        off = len(hdr)
    n = int([l for l in hdr.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
    mm = np.memmap(p, dtype=np.dtype([("x", "<f8"), ("y", "<f8"), ("z", "<f8"), ("r", "u1"), ("g", "u1"), ("b", "u1")]), mode="r",
                   offset=off, shape=(n,))
    mv = CFG["geogs_to_study_frame"]["xy_move_m"]
    X = np.stack([np.asarray(mm["x"]) + mv[0], np.asarray(mm["y"]) + mv[1], np.asarray(mm["z"]) + mv[2]], 1)
    if not raw:
        X[:, 2] += CFG["geogs_to_study_frame"]["z_gt_clean_m"] + CFG["geogs_to_study_frame"]["z_stage1_common_m"]
    rgb = np.stack([np.asarray(mm["r"]), np.asarray(mm["g"]), np.asarray(mm["b"])], 1)
    return X, rgb, hdr.decode(errors="replace")


def load_crop(name):
    """a cropped source of c1_crop.py (B0 box, raw frame)."""
    z = np.load(B0 / "crop" / f"{name}.npz")
    return {k: z[k] for k in z.files}


def return_class(rn, nr):
    """0 single (1 of 1), 1 first of many, 2 middle, 3 last of many, -1 invalid."""
    rn = rn.astype(np.int64); nr = nr.astype(np.int64)
    c = np.full(len(rn), -1, np.int8)
    c[(nr == 1) & (rn == 1)] = 0
    many = nr > 1
    c[many & (rn == 1)] = 1
    c[many & (rn > 1) & (rn < nr)] = 2
    c[many & (rn == nr)] = 3
    return c


# ------------------------------------------------------------------------------------------------ LoD2 faces of the target building
def lod2_faces():
    """the target building's LoD2 faces: ext, kind (1 roof, 2 wall), outward unit normal, triangles (registered, local frame)."""
    m = np.load(DR / "s02_box" / BOX / "lod2_mesh.npz")
    sh = np.asarray(jl(S0 / "s61/box" / BOX / "LoD2/summary.json")["registration"]["shift_applied"], np.float64)
    V = m["V"] + sh
    tab = {r["ext"]: r for r in jl(DR / "s02_box" / BOX / "lod2_surfaces.json")["surfaces"]}
    fp = [r for r in jl(DR / "s02_box" / BOX / "footprints.json")["footprints"] if r.get("building") == BLD][0]
    cen = np.asarray(fp["ring_local"], np.float64)[:, :2].mean(0)
    faces = []
    for e, r in sorted(tab.items()):
        if r["building"] != BLD:
            continue
        T = V[m["F"][m["tri_surface"] == e]]
        if not len(T):
            continue
        n = np.asarray(r["normal"], np.float64)
        n /= np.linalg.norm(n)
        c = T.reshape(-1, 3).mean(0)
        flip = False
        if r["kind"] == 2:
            n[2] = 0.0
            n /= np.linalg.norm(n)
            if np.dot(c[:2] - cen, n[:2]) < 0:      # outward = away from the footprint centre
                n = -n; flip = True
        elif n[2] < 0:
            n = -n; flip = True
        faces.append(dict(ext=int(e), kind=int(r["kind"]), type=r["type"], gml=r["gml"], normal=n, tris=T, origin=c,
                          area_table_m2=float(r["area_m2"]), cut=bool(r["cut"]), flipped=flip))
    return faces


def compass(n):
    az = (np.degrees(np.arctan2(n[0], n[1])) + 360.0) % 360.0
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return names[int(((az + 22.5) % 360) // 45)], float(az)


def wall_axes(f):
    n = f["normal"]
    t = np.array([-n[1], n[0], 0.0])
    return n, t


def _in_tris_2d(P, T2, eps=1e-9):
    """P [N, 2] inside any of the 2-D triangles T2 [M, 3, 2]."""
    inside = np.zeros(len(P), bool)
    for a, b, c in T2:
        v0, v1 = c - a, b - a
        v2 = P - a
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        den = d00 * d11 - d01 * d01
        if abs(den) < 1e-12:
            continue
        d20, d21 = v2 @ v0, v2 @ v1
        u = (d11 * d20 - d01 * d21) / den
        v = (d00 * d21 - d01 * d20) / den
        inside |= (u >= -eps) & (v >= -eps) & (u + v <= 1 + eps)
    return inside


def wall_space(f, X, h_m=None, gap_m=None):
    """3.3 '공간으로 고름' for one wall face: horizontal distance to the face plane <= h_m, the projection inside the face (lateral),
    and 0.5 m above the face's lower edge up to 0.5 m below its upper edge at that place (both (s, z - gap) and (s, z + gap) inside
    the face polygon). Returns the mask and the signed outward distance d, along-wall s, height z."""
    h_m = CFG["wall_selection"]["space"]["horizontal_m"] if h_m is None else h_m
    gap_m = CFG["wall_selection"]["space"]["vertical_margin_m"] if gap_m is None else gap_m
    n, t = wall_axes(f)
    o = f["origin"]
    R = X - o
    d = R @ n
    s = R @ t
    msk = np.abs(d) <= h_m
    T2 = np.stack([(f["tris"] - o) @ t, f["tris"][..., 2]], -1)
    lo, hi = T2.reshape(-1, 2).min(0), T2.reshape(-1, 2).max(0)
    msk &= (s >= lo[0]) & (s <= hi[0]) & (X[:, 2] >= lo[1] + gap_m) & (X[:, 2] <= hi[1] - gap_m)
    idx = np.nonzero(msk)[0]
    if len(idx):
        ok = _in_tris_2d(np.column_stack([s[idx], X[idx, 2] - gap_m]), T2) & _in_tris_2d(np.column_stack([s[idx], X[idx, 2] + gap_m]), T2)
        msk[idx[~ok]] = False
    return msk, d, s


def roof_space(f, X, h_m=None):
    """3.3 roof: distance along the face normal <= h_m and the projection inside the face."""
    h_m = CFG["wall_selection"]["roof_space"]["normal_m"] if h_m is None else h_m
    n = f["normal"]
    e1 = np.cross(n, [0.0, 0.0, 1.0]) if abs(n[2]) < 0.999 else np.array([1.0, 0.0, 0.0])
    e1 /= np.linalg.norm(e1); e2 = np.cross(n, e1)
    o = f["origin"]
    R = X - o
    d = R @ n
    a, b = R @ e1, R @ e2
    T2 = np.stack([(f["tris"] - o) @ e1, (f["tris"] - o) @ e2], -1)
    lo, hi = T2.reshape(-1, 2).min(0), T2.reshape(-1, 2).max(0)
    msk = (np.abs(d) <= h_m) & (a >= lo[0]) & (a <= hi[0]) & (b >= lo[1]) & (b <= hi[1])
    idx = np.nonzero(msk)[0]
    if len(idx):
        msk[idx[~_in_tris_2d(np.column_stack([a[idx], b[idx]]), T2)]] = False
    return msk, d


def face_area_in_space(f, step=0.05):
    """area of the face inside its selection space and the evaluation range (sampled on a step grid in the face plane):
    walls = the face between lower edge + margin and upper edge - margin; roofs = the whole face. Also the whole-face area in range."""
    o = f["origin"]
    if f["kind"] == 2:
        n, t = wall_axes(f)
        T2 = np.stack([(f["tris"] - o) @ t, f["tris"][..., 2]], -1)
        e1, e2, base = t, np.array([0.0, 0.0, 1.0]), np.array([o[0], o[1], 0.0])
    else:
        n = f["normal"]
        e1 = np.cross(n, [0.0, 0.0, 1.0]) if abs(n[2]) < 0.999 else np.array([1.0, 0.0, 0.0])
        e1 /= np.linalg.norm(e1); e2 = np.cross(n, e1)
        T2 = np.stack([(f["tris"] - o) @ e1, (f["tris"] - o) @ e2], -1)
        base = o
    lo, hi = T2.reshape(-1, 2).min(0), T2.reshape(-1, 2).max(0)
    ga = np.arange(lo[0] + step / 2, hi[0], step); gb = np.arange(lo[1] + step / 2, hi[1], step)
    A, Bq = np.meshgrid(ga, gb, indexing="ij")
    P = np.column_stack([A.ravel(), Bq.ravel()])
    inside = _in_tris_2d(P, T2)
    X3 = base + P[:, :1] * e1 + P[:, 1:2] * e2
    ev = in_rect(X3[:, :2])
    out = dict(area_face_m2=float(inside.sum() * step * step), area_face_in_eval_m2=float((inside & ev).sum() * step * step))
    if f["kind"] == 2:
        g = CFG["wall_selection"]["space"]["vertical_margin_m"]
        core = _in_tris_2d(P - [0, g], T2) & _in_tris_2d(P + [0, g], T2)
        out["area_space_in_eval_m2"] = float((core & ev).sum() * step * step)
        out["z_min"], out["z_max"] = float(f["tris"][..., 2].min()), float(f["tris"][..., 2].max())
    else:
        out["area_space_in_eval_m2"] = out["area_face_in_eval_m2"]
    return out


def vertical_points(X):
    """the study's wall-GT vertical-surface test, imported unchanged (scripts/phd/main_stage1_v1/s04_gt_v7.py:107-125)."""
    sys.path.insert(0, "/repo/scripts/phd/main_stage1_v1")
    sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1")
    sys.path.insert(0, "/repo")
    import s04_gt_v7 as s4
    return s4.vertical_points(X)

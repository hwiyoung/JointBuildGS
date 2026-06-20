#!/usr/bin/env python3
"""
E-R3 RECOVERABILITY DIAGNOSTIC  -- P2 make-or-break, step 3a (labels-only / 2a)
==============================================================================

PURPOSE
-------
Decide, per recovery building, whether the *textureless* roof is RECOVERABLE
from the imagery using SEMANTIC LABELS ALONE (no reference geometry, no MVS
depth, no height prior). This separates "method can't" from "data can't":

    R (recoverable)  -> multi-view semantic signal constrains a 3D roof volume.
                        If E-R3 still fails here, it's a METHOD failure.
    D (data-limited) -> labels do not constrain depth (too few views / no
                        parallax / carve is depth-ambiguous). No seeder, not
                        even E-R3, can recover it -> exclude / rescope.

It runs the *carve* only (= step 1 of E-R3), so nothing here is throwaway:
the same multi-view semantic intersection is what the E-R3 seeder will use.

METHOD (semantic visual hull)
-----------------------------
For each building, voxelize an (x,y) region over a wide z search band. Each
voxel is projected into every camera; we read the semantic label at that pixel
and accumulate  roof_vote = (#views labelling it Roof) / (#views observing it).
Voxels with roof_vote >= TAU and enough observations form the roof occupancy.

    C1 coverage   : # cameras that see this building's roof  (>= N_MIN)
    C2 parallax   : max angle between camera->centroid rays  (>= THETA_MIN deg)
    C3 sharpness  : per-(x,y)-column z-thickness of occupancy; median small
                    (<= THICK_MAX) and occupancy non-empty  => depth localized

    R iff  C1 and C2 and C3 all pass, else D (with reason).

NOTE: occlusion is ignored (conservative -> occupancy may be over-inclusive,
which only makes C3 *harder* to pass, i.e. the test errs toward calling things
D, not R). Distortion coefficients are ignored (pinhole projection).

INPUTS
------
--colmap DIR        COLMAP sparse model (cameras.bin/images.bin or .txt)
   OR
--poses-json FILE   [{ "name":..., "K":[fx,fy,cx,cy], "R":[9 row-major],
                       "t":[3], "width":W, "height":H }, ...]   (escape hatch:
                    wire this from your repo's own pose loader if COLMAP parse
                    mismatches; R,t are world->cam, X_cam = R@X_world + t)

--semantic-dir DIR  semantic masks; for image "name" the mask is
                    <semantic-dir>/<stem>.png  (uint8: BG=0 Roof=1 Wall=2 Gnd=3)
--footprints FILE   GeoJSON (FeatureCollection of building polygons) with an id
                    field, OR a JSON dict {building_id: [minx,miny,maxx,maxy]}
                    in the footprint CRS (default EPSG:25832).
--buildings ID ...  building ids to test (must match footprint ids / substrings)

--world-offset X Y Z  EPSG = GS_local + offset. Footprints are converted to the
                      pose/local frame by subtracting this. Default TUM scene.
--z-min --z-max     z search band IN THE LOCAL/POSE FRAME (set per scene).

OUTPUT
------
Prints a table and writes --out (csv + json) with per-building C1/C2/C3 and the
R/D verdict. Send that small file back; thresholds are all CLI-overridable.

SELF-TEST
---------
    python3 er3_recoverability_diag.py --selftest
exercises the decision logic (C2/C3/classify) on synthetic inputs; needs only
numpy (no COLMAP files, no PIL).
"""
import argparse
import glob
import json
import os
import struct
import sys

import numpy as np

ROOF_DEFAULT = 1
WORLD_OFFSET_DEFAULT = (690953.0, 5336071.0, 604.0)

# COLMAP camera model id -> number of params
MODEL_NUM_PARAMS = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12, 7: 5, 8: 4, 9: 5, 10: 12}
# models whose params start with a single focal length f (then cx,cy,...)
SINGLE_F_MODELS = {0, 2, 3, 8, 9}


# ----------------------------------------------------------------------------
# COLMAP readers
# ----------------------------------------------------------------------------
def qvec2rotmat(q):
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w),     2 * (x * z + y * w)],
        [2 * (x * y + z * w),     1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w),     2 * (y * z + x * w),     1 - 2 * (x * x + y * y)],
    ], dtype=np.float64)


def get_fxfycxcy(model, params):
    if model in SINGLE_F_MODELS:
        return float(params[0]), float(params[0]), float(params[1]), float(params[2])
    return float(params[0]), float(params[1]), float(params[2]), float(params[3])


def read_cameras_binary(path):
    cams = {}
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            cam_id, model_id, width, height = struct.unpack("<iiQQ", f.read(24))
            npar = MODEL_NUM_PARAMS.get(model_id, 4)
            params = struct.unpack("<" + "d" * npar, f.read(8 * npar))
            cams[cam_id] = dict(model=model_id, width=width, height=height, params=params)
    return cams


def read_images_binary(path):
    imgs = []
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            (image_id,) = struct.unpack("<I", f.read(4))
            qw, qx, qy, qz, tx, ty, tz = struct.unpack("<7d", f.read(56))
            (cam_id,) = struct.unpack("<I", f.read(4))
            name = b""
            while True:
                c = f.read(1)
                if c == b"\x00" or c == b"":
                    break
                name += c
            (n2d,) = struct.unpack("<Q", f.read(8))
            f.read(24 * n2d)  # x(d) y(d) point3D_id(Q)
            imgs.append(dict(image_id=image_id, q=(qw, qx, qy, qz),
                             t=(tx, ty, tz), cam_id=cam_id,
                             name=name.decode("utf-8", "replace")))
    return imgs


def read_cameras_text(path):
    cams = {}
    with open(path) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            e = line.split()
            cam_id = int(e[0]); model = e[1]
            width, height = int(e[2]), int(e[3])
            params = list(map(float, e[4:]))
            mid = {v: k for k, v in {
                0: "SIMPLE_PINHOLE", 1: "PINHOLE", 2: "SIMPLE_RADIAL", 3: "RADIAL",
                4: "OPENCV", 5: "OPENCV_FISHEYE", 6: "FULL_OPENCV", 7: "FOV",
                8: "SIMPLE_RADIAL_FISHEYE", 9: "RADIAL_FISHEYE",
                10: "THIN_PRISM_FISHEYE"}.items()}.get(model, 1)
            cams[cam_id] = dict(model=mid, width=width, height=height, params=params)
    return cams


def read_images_text(path):
    imgs = []
    with open(path) as f:
        lines = [ln for ln in f if not ln.startswith("#")]
    for i in range(0, len(lines), 2):  # every 2nd line is points2D (skipped)
        e = lines[i].split()
        if len(e) < 10:
            continue
        imgs.append(dict(
            image_id=int(e[0]),
            q=(float(e[1]), float(e[2]), float(e[3]), float(e[4])),
            t=(float(e[5]), float(e[6]), float(e[7])),
            cam_id=int(e[8]), name=e[9]))
    return imgs


def load_cameras(colmap_dir):
    """Return list of dicts: name, K(fx,fy,cx,cy), R(3x3), t(3), W, H, center(3)."""
    cb, ib = os.path.join(colmap_dir, "cameras.bin"), os.path.join(colmap_dir, "images.bin")
    ct, it = os.path.join(colmap_dir, "cameras.txt"), os.path.join(colmap_dir, "images.txt")
    if os.path.exists(cb) and os.path.exists(ib):
        cams, imgs = read_cameras_binary(cb), read_images_binary(ib)
    elif os.path.exists(ct) and os.path.exists(it):
        cams, imgs = read_cameras_text(ct), read_images_text(it)
    else:
        raise FileNotFoundError(f"No cameras/images .bin or .txt in {colmap_dir}")
    out = []
    for im in imgs:
        cam = cams[im["cam_id"]]
        fx, fy, cx, cy = get_fxfycxcy(cam["model"], cam["params"])
        R = qvec2rotmat(im["q"]); t = np.array(im["t"], dtype=np.float64)
        out.append(dict(name=im["name"], K=(fx, fy, cx, cy), R=R, t=t,
                        W=cam["width"], H=cam["height"], center=-R.T @ t))
    return out


def load_poses_json(path):
    out = []
    for d in json.load(open(path)):
        R = np.array(d["R"], dtype=np.float64).reshape(3, 3)
        t = np.array(d["t"], dtype=np.float64)
        fx, fy, cx, cy = d["K"]
        out.append(dict(name=d["name"], K=(fx, fy, cx, cy), R=R, t=t,
                        W=int(d["width"]), H=int(d["height"]), center=-R.T @ t))
    return out


# ----------------------------------------------------------------------------
# footprints
# ----------------------------------------------------------------------------
def _poly_bbox(coords):
    xs = [c[0] for ring in coords for c in ring]
    ys = [c[1] for ring in coords for c in ring]
    return [min(xs), min(ys), max(xs), max(ys)]


def load_footprints(path, id_field="gml_id"):
    data = json.load(open(path))
    if isinstance(data, dict) and "features" not in data:
        return {str(k): list(map(float, v)) for k, v in data.items()}  # plain bbox dict
    out = {}
    for ft in data.get("features", []):
        props = ft.get("properties", {}) or {}
        bid = props.get(id_field) or props.get("id") or props.get("name")
        if bid is None:
            continue
        g = ft.get("geometry", {}) or {}
        gt, co = g.get("type"), g.get("coordinates")
        if gt == "Polygon":
            out[str(bid)] = _poly_bbox(co)
        elif gt == "MultiPolygon":
            out[str(bid)] = _poly_bbox([r for poly in co for r in poly])
    return out


def match_building(bid, footprints):
    if bid in footprints:
        return footprints[bid]
    for k, v in footprints.items():
        if bid in k or k in bid:
            return v
    return None


# ----------------------------------------------------------------------------
# geometry helpers (unit-tested in --selftest)
# ----------------------------------------------------------------------------
def max_pairwise_angle_deg(dirs):
    """Max angle (deg) between any pair of unit direction vectors."""
    if len(dirs) < 2:
        return 0.0
    d = np.asarray(dirs, dtype=np.float64)
    d /= (np.linalg.norm(d, axis=1, keepdims=True) + 1e-12)
    cos = np.clip(d @ d.T, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos.min())))


def column_thickness(occ_idx, voxel, nz):
    """occ_idx: (M,3) int voxel indices (ix,iy,iz). Return (median_thick, n_cols)."""
    if len(occ_idx) == 0:
        return float("inf"), 0
    occ_idx = np.asarray(occ_idx)
    keys = occ_idx[:, 0].astype(np.int64) * 100003 + occ_idx[:, 1].astype(np.int64)
    thick = []
    for k in np.unique(keys):
        zs = occ_idx[keys == k, 2]
        thick.append((zs.max() - zs.min() + 1) * voxel)
    return float(np.median(thick)), int(len(thick))


def classify(c1_views, c2_deg, c3_thick, c3_nvox, thr):
    reasons = []
    if c1_views < thr["n_min"]:
        reasons.append(f"C1 coverage {c1_views}<{thr['n_min']}")
    if c2_deg < thr["theta_min"]:
        reasons.append(f"C2 parallax {c2_deg:.1f}deg<{thr['theta_min']}")
    if c3_nvox < thr["min_occ_vox"]:
        reasons.append(f"C3 empty ({c3_nvox} vox)")
    elif c3_thick > thr["thick_max"]:
        reasons.append(f"C3 depth-ambiguous (thick {c3_thick:.1f}m>{thr['thick_max']}m)")
    return ("R", "ok") if not reasons else ("D", "; ".join(reasons))


# ----------------------------------------------------------------------------
# carve
# ----------------------------------------------------------------------------
def build_grid(bbox_local, z_min, z_max, voxel):
    minx, miny, maxx, maxy = bbox_local
    xs = np.arange(minx, maxx + voxel, voxel)
    ys = np.arange(miny, maxy + voxel, voxel)
    zs = np.arange(z_min, z_max + voxel, voxel)
    gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
    V = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)  # (N,3) world/local
    ix, iy, iz = np.meshgrid(np.arange(len(xs)), np.arange(len(ys)),
                             np.arange(len(zs)), indexing="ij")
    IDX = np.stack([ix.ravel(), iy.ravel(), iz.ravel()], axis=1)
    return V, IDX, (len(xs), len(ys), len(zs))


def run(args):
    thr = dict(n_min=args.n_min, theta_min=args.theta_min,
               thick_max=args.thick_max, min_occ_vox=args.min_occ_vox)
    cams = (load_poses_json(args.poses_json) if args.poses_json
            else load_cameras(args.colmap))
    footprints = load_footprints(args.footprints, args.id_field)
    offset = np.array(args.world_offset, dtype=np.float64)
    from PIL import Image  # lazy: not needed for --selftest

    # per-building voxel grids in LOCAL frame
    B = {}
    for bid in args.buildings:
        bbox = match_building(bid, footprints)
        if bbox is None:
            print(f"[warn] no footprint for {bid}; skipping", file=sys.stderr)
            continue
        bbox_local = [bbox[0] - offset[0], bbox[1] - offset[1],
                      bbox[2] - offset[0], bbox[3] - offset[1]]
        V, IDX, dims = build_grid(bbox_local, args.z_min, args.z_max, args.voxel)
        B[bid] = dict(V=V, IDX=IDX, dims=dims,
                      obs=np.zeros(len(V), np.int32), roof=np.zeros(len(V), np.int32),
                      centroid=np.array([(bbox_local[0] + bbox_local[2]) / 2,
                                         (bbox_local[1] + bbox_local[3]) / 2,
                                         (args.z_min + args.z_max) / 2]),
                      roof_cam_centers=[])

    # iterate cameras once; accumulate into every building grid
    for ci, cam in enumerate(cams):
        stem = os.path.splitext(os.path.basename(cam["name"]))[0]
        mpath = os.path.join(args.semantic_dir, stem + ".png")
        if not os.path.exists(mpath):
            continue
        try:
            mask = np.asarray(Image.open(mpath))
        except Exception:
            continue
        if mask.ndim == 3:
            mask = mask[:, :, 0]
        H, W = mask.shape[:2]
        fx, fy, cx, cy = cam["K"]; R = cam["R"]; t = cam["t"]; C = cam["center"]
        for bid, b in B.items():
            Xc = (R @ b["V"].T) + t.reshape(3, 1)        # (3,N)
            z = Xc[2]
            front = z > 1e-6
            u = np.empty_like(z); v = np.empty_like(z)
            u[front] = fx * Xc[0, front] / z[front] + cx
            v[front] = fy * Xc[1, front] / z[front] + cy
            inb = front & (u >= 0) & (u < W) & (v >= 0) & (v < H)
            idx = np.where(inb)[0]
            if idx.size == 0:
                continue
            lab = mask[v[idx].astype(np.int32), u[idx].astype(np.int32)]
            b["obs"][idx] += 1
            roof_hit = idx[lab == args.roof_code]
            if roof_hit.size:
                b["roof"][roof_hit] += 1
                b["roof_cam_centers"].append(C)
        if args.verbose and ci % 100 == 0:
            print(f"  ...{ci}/{len(cams)} cams", file=sys.stderr)

    # per-building metrics + verdict
    rows = []
    for bid, b in B.items():
        with np.errstate(divide="ignore", invalid="ignore"):
            vote = np.where(b["obs"] >= args.min_obs, b["roof"] / np.maximum(b["obs"], 1), 0.0)
        occ = (vote >= args.tau) & (b["obs"] >= args.min_obs)
        occ_idx = b["IDX"][occ]
        thick, ncols = column_thickness(occ_idx, args.voxel, b["dims"][2])
        centers = b["roof_cam_centers"]
        dirs = [(b["centroid"] - c) for c in centers]
        c2 = max_pairwise_angle_deg(dirs) if len(dirs) >= 2 else 0.0
        c1 = len(centers)
        nvox = int(occ.sum())
        klass, reason = classify(c1, c2, thick, nvox, thr)
        rows.append(dict(building=bid, verdict=klass, reason=reason,
                         C1_roof_views=c1, C2_parallax_deg=round(c2, 1),
                         C3_med_thick_m=(None if thick == float("inf") else round(thick, 2)),
                         C3_occ_voxels=nvox, C3_occ_columns=ncols))

    rows.sort(key=lambda r: (r["verdict"], r["building"]))
    # print
    hdr = ["building", "verdict", "C1_roof_views", "C2_parallax_deg",
           "C3_med_thick_m", "C3_occ_voxels", "reason"]
    print("\t".join(hdr))
    for r in rows:
        print("\t".join(str(r[k]) for k in hdr))
    nR = sum(r["verdict"] == "R" for r in rows)
    print(f"\n# R (recoverable)={nR}  D (data-limited)={len(rows)-nR}", file=sys.stderr)
    print(f"# thresholds: N_min={thr['n_min']} theta_min={thr['theta_min']} "
          f"thick_max={thr['thick_max']} tau={args.tau} voxel={args.voxel} "
          f"min_obs={args.min_obs}", file=sys.stderr)

    if args.out:
        json.dump(dict(thresholds=thr, tau=args.tau, voxel=args.voxel,
                       min_obs=args.min_obs, rows=rows), open(args.out, "w"), indent=2)
        csvp = os.path.splitext(args.out)[0] + ".csv"
        with open(csvp, "w") as f:
            f.write(",".join(hdr) + "\n")
            for r in rows:
                f.write(",".join('"%s"' % r[k] if k == "reason" else str(r[k]) for k in hdr) + "\n")
        print(f"# wrote {args.out} and {csvp}", file=sys.stderr)
    return rows


# ----------------------------------------------------------------------------
# self-test (logic only; numpy-only)
# ----------------------------------------------------------------------------
def selftest():
    ok = True

    # C2: wide ring of rays -> large angle; near-parallel -> small
    wide = [[1, 0, -1], [-1, 0, -1], [0, 1, -1], [0, -1, -1]]
    narrow = [[0.01 * k, 0, -1] for k in range(4)]
    a_wide, a_narrow = max_pairwise_angle_deg(wide), max_pairwise_angle_deg(narrow)
    print(f"[selftest] C2 wide={a_wide:.1f}deg narrow={a_narrow:.1f}deg")
    ok &= a_wide > 45 and a_narrow < 5

    # C3: thin occupancy (1 z-layer) vs spanning (many z) over a 3x3 column set
    cols = [(i, j) for i in range(3) for j in range(3)]
    thin = np.array([[i, j, 5] for (i, j) in cols])
    span = np.array([[i, j, z] for (i, j) in cols for z in range(0, 40)])
    t_thin, _ = column_thickness(thin, 1.0, 50)
    t_span, _ = column_thickness(span, 1.0, 50)
    print(f"[selftest] C3 thin={t_thin:.1f}m span={t_span:.1f}m")
    ok &= t_thin <= 1.0 and t_span >= 35

    thr = dict(n_min=10, theta_min=15.0, thick_max=3.0, min_occ_vox=20)
    # recoverable: good coverage, parallax, thin, enough voxels
    kR, _ = classify(120, 40.0, 1.0, 900, thr)
    # data-limited (no parallax)
    kD1, r1 = classify(120, 4.0, 1.0, 900, thr)
    # data-limited (depth-ambiguous)
    kD2, r2 = classify(120, 40.0, 38.0, 900, thr)
    # data-limited (no coverage)
    kD3, r3 = classify(3, 40.0, 1.0, 900, thr)
    print(f"[selftest] classify R={kR}  noParallax={kD1}({r1})  "
          f"ambiguous={kD2}({r2})  noCov={kD3}({r3})")
    ok &= (kR == "R" and kD1 == "D" and kD2 == "D" and kD3 == "D")

    print("[selftest] PASS" if ok else "[selftest] FAIL")
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(description="E-R3 recoverability diagnostic (labels-only)")
    p.add_argument("--selftest", action="store_true")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--colmap", help="COLMAP sparse dir (cameras/images .bin or .txt)")
    src.add_argument("--poses-json", help="alternative pose loader (see header)")
    p.add_argument("--semantic-dir", help="dir of <stem>.png semantic masks")
    p.add_argument("--footprints", help="GeoJSON or {id:[minx,miny,maxx,maxy]} JSON")
    p.add_argument("--id-field", default="gml_id")
    p.add_argument("--buildings", nargs="+", default=[])
    p.add_argument("--world-offset", nargs=3, type=float, default=list(WORLD_OFFSET_DEFAULT))
    p.add_argument("--z-min", type=float, default=-20.0)
    p.add_argument("--z-max", type=float, default=80.0)
    p.add_argument("--voxel", type=float, default=1.0)
    p.add_argument("--tau", type=float, default=0.6, help="roof-vote threshold")
    p.add_argument("--min-obs", type=int, default=5, help="min views/voxel to count")
    p.add_argument("--roof-code", type=int, default=ROOF_DEFAULT)
    # R/D thresholds
    p.add_argument("--n-min", type=int, default=10)
    p.add_argument("--theta-min", type=float, default=15.0)
    p.add_argument("--thick-max", type=float, default=3.0)
    p.add_argument("--min-occ-vox", type=int, default=20)
    p.add_argument("--out", help="output json (csv written alongside)")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if args.selftest:
        return selftest()
    missing = [k for k in ("semantic_dir", "footprints") if not getattr(args, k)]
    if not (args.colmap or args.poses_json) or missing or not args.buildings:
        p.error("need --colmap/--poses-json, --semantic-dir, --footprints, --buildings "
                "(or run --selftest)")
    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

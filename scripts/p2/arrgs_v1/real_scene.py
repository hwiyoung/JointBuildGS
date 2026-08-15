#!/usr/bin/env python3
"""ARRGS real-building scene assembly (X1–X4).

Working frame: viewer-local = EPSG:25832 world − [690700, 5335700, 550]
(v22 crop convention — matches every per-building crop asset).
Full-scene COLMAP frame = world − [690953, 5336071, 604] (C4 WORLD_SHIFT,
pure translation): x_viewer = x_colmap + [253, 371, 54].

S1 candidates:
  prior  — RANSAC planes on the registered-ALS crop (E7 A2 asset, class 6)
  mvs    — RANSAC planes on the E2 crop (class 6), deduped against prior
  footprint — vertical wall planes from shared standard footprint edges (DEC-P1-019
              XY-support role, D-3 confirmed) + ground plane from ALS class 2

δ injection (X3) happens HERE on the raw ALS bytes (points), so detected prior
planes and the occupancy init stay byte-consistent with the injected shift.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
import torch

VIEWER_SHIFT = np.array([690700.0, 5335700.0, 550.0])
COLMAP_TO_VIEWER = np.array([253.0, 371.0, 54.0])
ART = Path("/artifacts/JointBuildGS")

FULLSCENE_SPARSE = ART / "phase-payloads/p0-audit/data/work/mvs/colmap_dense/sparse"
FULLSCENE_IMAGES = ART / "phase-payloads/p0-audit/data/work/mvs/colmap_dense/images"
FULLSCENE_DEPTH = (ART / "phase-payloads/p2/e3_full_scene_fused_normal_confidence_v1/"
                   "P2-E3-FULL-SCENE-FUSED-NORMAL-CONFIDENCE-v1/data/"
                   "fused_normal_confidence_colmap_full/depth")  # fused MVS z-depth EXR
A2_CROPS = ART / "phase-payloads/p2/journal1_phase_a_v1/P2-JOURNAL1-PHASE-A-v1/a2/assets_roofer_input"
FOOTPRINTS = (ART / "phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
              "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3/freeze/"
              "shared_footprints_199.geojson")  # frozen DEC-P1-019 lineage, EPSG:25832


# ---------------- COLMAP + PLY IO ----------------

def read_colmap_cameras(path):
    cams = {}
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            cid, model, w, h = struct.unpack("<iiQQ", f.read(24))
            np_map = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12, 7: 5, 8: 4, 9: 5, 10: 12}
            params = struct.unpack(f"<{np_map[model]}d", f.read(8 * np_map[model]))
            cams[cid] = {"model": model, "w": w, "h": h, "params": params}
    return cams


def read_colmap_images(path):
    imgs = []
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            iid = struct.unpack("<I", f.read(4))[0]
            q = struct.unpack("<4d", f.read(32))
            t = struct.unpack("<3d", f.read(24))
            cam = struct.unpack("<I", f.read(4))[0]
            name = b""
            while True:
                c = f.read(1)
                if c == b"\x00":
                    break
                name += c
            n2d = struct.unpack("<Q", f.read(8))[0]
            f.read(24 * n2d)
            imgs.append({"id": iid, "q": q, "t": np.asarray(t), "cam": cam,
                         "name": name.decode()})
    return imgs


def quat_to_R(q):
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def read_ply_xyzc(path):
    """Binary LE PLY with x,y,z float + optional rgb/classification uchar."""
    with open(path, "rb") as f:
        header = b""
        while not header.endswith(b"end_header\n"):
            header += f.readline()
        lines = header.decode().splitlines()
        count = 0
        props = []
        for ln in lines:
            if ln.startswith("element vertex"):
                count = int(ln.split()[-1])
            elif ln.startswith("property"):
                _, typ, name = ln.split()
                props.append((typ, name))
        fmt = {"float": ("f", 4), "uchar": ("B", 1), "double": ("d", 8),
               "int": ("i", 4), "uint": ("I", 4)}
        rec = "".join(fmt[t][0] for t, _ in props)
        size = sum(fmt[t][1] for t, _ in props)
        raw = np.frombuffer(f.read(count * size), dtype=np.dtype(
            [(nm, "<" + fmt[t][0]) for t, nm in props]))
        xyz = np.stack([raw["x"], raw["y"], raw["z"]], axis=1).astype(np.float64)
        cls = raw["classification"].astype(np.int32) if "classification" in raw.dtype.names else None
        return xyz, cls


# ---------------- candidates ----------------

def ransac_planes(pts, max_planes=8, tol=0.15, min_frac=0.03, min_abs=150,
                  reject_vertical=0.25, seed=0):
    rng = np.random.default_rng(seed)
    remaining = pts.copy()
    out = []
    total = len(pts)
    while len(remaining) > max(min_abs, min_frac * total) and len(out) < max_planes:
        best_inl, best = 0, None
        for _ in range(300):
            idx = rng.choice(len(remaining), 3, replace=False)
            p0, p1, p2 = remaining[idx]
            n = np.cross(p1 - p0, p2 - p0)
            nn = np.linalg.norm(n)
            if nn < 1e-9:
                continue
            n = n / nn
            if n[2] < 0:
                n = -n
            d = n @ p0
            inl = np.abs(remaining @ n - d) < tol
            if inl.sum() > best_inl:
                best_inl, best = int(inl.sum()), (n, d, inl)
        if best is None or best_inl < max(min_abs, min_frac * total):
            break
        n, d, inl = best
        # PCA refit
        P = remaining[inl]
        c = P.mean(axis=0)
        _, _, Vt = np.linalg.svd(P - c, full_matrices=False)
        n = Vt[2] / np.linalg.norm(Vt[2])
        if n[2] < 0:
            n = -n
        d = float(n @ c)
        inl = np.abs(remaining @ n - d) < tol
        if abs(n[2]) >= reject_vertical:
            out.append({"n": n.tolist(), "d": d, "inliers": int(inl.sum()),
                        "frac": float(inl.sum() / total)})
        remaining = remaining[~inl]
    return out


def dedupe(planes_a, planes_b, ang_deg=10.0, d_tol=0.4):
    """Drop b-planes near-duplicate to any a-plane."""
    keep = []
    for b in planes_b:
        nb, db = np.asarray(b["n"]), b["d"]
        dup = False
        for a in planes_a:
            na, da = np.asarray(a["n"]), a["d"]
            cos = abs(float(na @ nb))
            if cos > np.cos(np.deg2rad(ang_deg)) and abs(da - db) < d_tol:
                dup = True
                break
        if not dup:
            keep.append(b)
    return keep


def load_footprint(stable_id):
    gj = json.load(open(FOOTPRINTS))
    for feat in gj["features"]:
        props = feat.get("properties", {})
        sid = str(props.get("stable_id") or props.get("gml_id") or props.get("id") or "")
        if stable_id in sid:
            geom = feat["geometry"]
            ring = geom["coordinates"][0]
            if geom["type"] == "MultiPolygon":
                ring = geom["coordinates"][0][0]
            xy = np.asarray(ring, dtype=np.float64)[:, :2] - VIEWER_SHIFT[:2]
            # drop closing vertex, simplify until the edge count keeps the
            # arrangement tractable (wall planes multiply cells)
            if np.allclose(xy[0], xy[-1]):
                xy = xy[:-1]
            from shapely.geometry import Polygon
            poly = Polygon(xy)
            # 24-edge cap: 14 was too blunt for deep-concave perimeter blocks
            # (B022: 159 verts -> 14 edges filled the U-opening with phantom roof)
            for tol in (0.3, 0.5, 0.8, 1.2, 1.8, 2.5, 3.5):
                simp = poly.simplify(tol)
                if len(simp.exterior.coords) - 1 <= 24:
                    return np.asarray(simp.exterior.coords)[:-1]
            return np.asarray(simp.exterior.coords)[:-1]
    raise KeyError(f"footprint not found for {stable_id}")


def load_real_scene(scene, device):
    stable_id = scene["stable_id"]
    bkey = scene["bkey"]  # e.g. B036_DEBY_LOD2_4906982
    inj_e = float(scene.get("inject_delta_east_m", 0.0))
    inj_z = float(scene.get("inject_delta_z_m", 0.0))
    shift = np.array([inj_e, 0.0, inj_z])

    fp = load_footprint(stable_id)
    als_xyz, als_cls = read_ply_xyzc(A2_CROPS / "E7" / f"{bkey}.points.ply")
    if inj_e or inj_z:
        als_xyz = als_xyz + shift  # δ on the prior bytes (X3)
    e2_path = A2_CROPS / "E8" / f"{bkey}.points.ply"  # E8 = E2∪ALS; better: use E2 arm crop if configured
    e2_xyz, e2_cls = (None, None)
    if scene.get("e2_dir"):
        p = Path(scene["e2_dir"]) / f"{bkey}.points.ply"
        if p.is_file():
            e2_xyz, e2_cls = read_ply_xyzc(p)

    roof_als = als_xyz[als_cls == 6] if als_cls is not None else als_xyz
    ground_als = als_xyz[als_cls == 2] if als_cls is not None else als_xyz
    # class-agnostic guard: B036's SMRF roof-as-ground pollution lifted the
    # class-2 median to roof height — take the more conservative of the two
    q05_all = float(np.quantile(als_xyz[:, 2], 0.05)) if len(als_xyz) else 0.0
    cls2_med = float(np.median(ground_als[:, 2])) if len(ground_als) else q05_all
    ground_z = min(cls2_med, q05_all + 1.0)
    # X1-diag fix: the footprint+3m crop can catch neighbour structure (tower
    # tails inflated top_z to +13 m -> phantom solid headroom). Restrict the
    # vertical-extent and plane statistics to points INSIDE the footprint.
    from shapely.geometry import Polygon as ShPolygon
    from shapely.prepared import prep
    fp_poly = prep(ShPolygon(fp).buffer(0.3))
    from shapely.geometry import Point as ShPt
    if len(roof_als):
        in_fp = np.fromiter((fp_poly.contains(ShPt(x, y)) for x, y in roof_als[:, :2]),
                            dtype=bool, count=len(roof_als))
        roof_fp = roof_als[in_fp] if in_fp.any() else roof_als
    else:
        roof_fp = roof_als
    top_z = float(np.quantile(roof_fp[:, 2], 0.98) + 1.5) if len(roof_fp) else ground_z + 15.0

    s1_mode = scene.get("s1_mode", "roofer")
    planes = []
    if s1_mode == "roofer":
        # S1R: sealed Roofer outputs as the plane detector (E7=prior, E8=union increment)
        from s1r import candidates_from_roofer
        e7_obj = A2_CROPS / "E7" / f"{bkey}.roofer.obj"
        e8_obj = A2_CROPS / "E8" / f"{bkey}.roofer.obj"
        planes = candidates_from_roofer(
            e7_obj if e7_obj.is_file() else None,
            e8_obj if e8_obj.is_file() else None,
            delta_shift=shift if (inj_e or inj_z) else None)
    if len(planes) < 2:  # fallback: v1 RANSAC path
        prior_planes = ransac_planes(roof_fp, max_planes=scene.get("max_prior_planes", 12),
                                     reject_vertical=0.5)
        prior_planes = sorted(prior_planes, key=lambda p: -p["inliers"])[:10]
        for i, pl in enumerate(prior_planes):
            planes.append({"id": f"prior{i}", "n": pl["n"], "d": pl["d"], "source": "prior_als",
                           "prior": {"n0": pl["n"], "d0": pl["d"], "w": min(1.0, pl["frac"] * 5)}})
        if e2_xyz is not None:
            roof_e2 = e2_xyz[e2_cls == 6] if e2_cls is not None else e2_xyz
            mvs_planes = dedupe(prior_planes, ransac_planes(roof_e2, max_planes=4))
            for i, pl in enumerate(mvs_planes[:scene.get("max_mvs_planes", 3)]):
                planes.append({"id": f"mvs{i}", "n": pl["n"], "d": pl["d"],
                               "source": "mvs", "prior": None})
    for i in range(len(fp)):
        a, b = fp[i], fp[(i + 1) % len(fp)]
        e = np.array([b[0] - a[0], b[1] - a[1], 0.0])
        if np.linalg.norm(e) < 0.5:
            continue
        n = np.array([e[1], -e[0], 0.0])
        n /= np.linalg.norm(n)
        # support corridor: only facets near this edge segment carry walls/seeds
        from shapely.geometry import LineString
        corr = LineString([tuple(a), tuple(b)]).buffer(1.2)
        planes.append({"id": f"wall{i}", "n": n.tolist(), "d": float(n[:2] @ a),
                       "source": "footprint", "prior": None,
                       "support": [np.asarray(corr.exterior.coords)[:-1].tolist()]})
    planes.append({"id": "groundp", "n": [0, 0, 1.0], "d": ground_z + 0.05,
                   "source": "footprint", "prior": None,
                   "support": [np.asarray(fp).tolist()]})
    # S1 input-side verdict (upper envelope of ALL crop returns — SMRF-hole immune)
    from s1r import s1_verdict, upper_envelope, gapfill_planes
    above = als_xyz[als_xyz[:, 2] > ground_z + 2.0]
    env_src = upper_envelope(above)  # column-top skin: walls collapse to eaves
    roofish = [p for p in planes if p["source"] != "footprint"]
    verdict = s1_verdict(roofish, env_src, fp)
    if not verdict["pass"]:
        extra = gapfill_planes(roofish, env_src, fp, ransac_fn=ransac_planes)
        if extra:
            planes = planes + extra
            roofish = roofish + extra
            verdict = s1_verdict(roofish, env_src, fp)
            verdict["gapfill_added"] = len(extra)
    # grade: residue after gapfill exhaustion = plane-unfittable content
    # (canopy/superstructure), not a structural miss
    if verdict["pass"]:
        verdict["grade"] = "PASS"
    elif verdict["explained"] >= 0.95:
        verdict["grade"] = "PASS_RESIDUE"
    else:
        verdict["grade"] = "FAIL"

    # occupancy init from (possibly shifted) ALS solid proxy — defined before
    # the camera section so skip_images sweeps (oracle) can use it.
    from scipy.spatial import cKDTree
    col_src = roof_fp if len(roof_fp) else als_xyz
    tree = cKDTree(col_src[:, :2]) if len(col_src) else None
    if s1_mode == "roofer" and len(als_xyz):  # B036: class-6 hole immunity
        col_src = als_xyz
        tree = cKDTree(als_xyz[:, :2])

    # plane-aware occupancy surface: on sawtooth/parapet roofs the raw column
    # p90 envelope fills to the TOOTH TOPS (B173 oracle collapse, comp 0.02) —
    # prefer the local candidate-plane surface where a support region covers
    # the column, envelope as fallback.
    from shapely.prepared import prep as _prep2
    from shapely.ops import unary_union as _uu
    from shapely.geometry import Polygon
    plane_surfs = []
    for p in planes:
        if p["source"] == "footprint" or not p.get("support"):
            continue
        polys = [Polygon(r) for r in p["support"] if len(r) >= 3]
        polys = [q for q in polys if q.is_valid and q.area > 0.5]
        if not polys:
            continue
        n = np.asarray(p["n"])
        if abs(n[2]) < 0.1:
            continue
        plane_surfs.append((_prep2(_uu(polys)), n, float(p["d"])))

    def o_init_fn(centroid):
        # envelope-primary (plane-surface variant REGRESSED: overlapping
        # buffered supports overfill to the tallest covering plane —
        # B022 0.695->0.470, B036 0.801->0.696; kept for reference)
        if tree is None:
            return 0.5
        idx = tree.query_ball_point(centroid[:2], r=0.75)
        if not idx:
            return 0.2
        zsurf = float(np.percentile(col_src[idx, 2], 90))
        return 0.75 if centroid[2] < zsurf else 0.15

    # ---------------- cameras / views ----------------
    if scene.get("skip_images"):  # oracle sweeps need no photometry
        return {
            "planes": planes, "footprint": fp, "ground_z": ground_z,
            "top_z": top_z, "o_init_fn": o_init_fn, "s1_verdict": verdict,
            "s1_mode": s1_mode if len(planes) > len(fp) + 1 else "ransac_fallback",
            "als_points": len(als_xyz), "inject": [inj_e, 0.0, inj_z],
        }
    cams = read_colmap_cameras(FULLSCENE_SPARSE / "cameras.bin")
    imgs = read_colmap_images(FULLSCENE_SPARSE / "images.bin")
    cam0 = cams[imgs[0]["cam"]]
    fx, fy, cx, cy = cam0["params"][:4]
    W, H = int(cam0["w"]), int(cam0["h"])
    K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1.0]])
    center = np.array([fp[:, 0].mean(), fp[:, 1].mean(), (ground_z + top_z) / 2])
    corners = []
    for z in (ground_z, top_z):
        for p in fp:
            corners.append([p[0], p[1], z])
    corners = np.asarray(corners)

    scored = []
    for im in imgs:
        R = quat_to_R(im["q"])
        t = im["t"] - R @ COLMAP_TO_VIEWER  # viewer-local extrinsics
        Xc = (R @ center) + t
        if Xc[2] < 15.0 or Xc[2] > 180.0:
            continue
        uv = K @ (Xc / Xc[2])
        mg = 0.12
        if not (W * mg < uv[0] < W * (1 - mg) and H * mg < uv[1] < H * (1 - mg)):
            continue
        Cc = (R @ corners.T).T + t
        if (Cc[:, 2] <= 0.5).any():
            continue
        uvc = (K @ (Cc / Cc[:, 2:3]).T).T[:, :2]
        from scipy.spatial import ConvexHull
        try:
            area = ConvexHull(uvc).volume  # 2D hull area
        except Exception:
            continue
        scored.append((area, im, R, t))
    scored.sort(key=lambda s: -s[0])
    sel = scored[:scene.get("max_views", 48)]
    if len(sel) < 8:
        raise RuntimeError(f"only {len(sel)} usable views for {stable_id}")

    from PIL import Image as PILImage
    scale = float(scene.get("image_scale", 1.0))
    Ws, Hs = int(W * scale), int(H * scale)
    Ks_np = np.tile(K, (len(sel), 1, 1))
    if scale != 1.0:
        Ks_np[:, :2, :] *= scale
    import os
    os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
    import cv2
    viewmats_np = []
    targets = np.zeros((len(sel), Hs, Ws, 3), dtype=np.float32)
    depths = np.zeros((len(sel), Hs, Ws), dtype=np.float32)
    for i, (_, im, R, t) in enumerate(sel):
        T = np.eye(4)
        T[:3, :3] = R
        T[:3, 3] = t
        viewmats_np.append(T)
        img = PILImage.open(FULLSCENE_IMAGES / im["name"])
        if scale != 1.0:
            img = img.resize((Ws, Hs), PILImage.LANCZOS)
        targets[i] = np.asarray(img, dtype=np.float32)[..., :3] / 255.0
        dpath = FULLSCENE_DEPTH / (Path(im["name"]).stem + ".exr")
        if dpath.is_file():
            d = cv2.imread(str(dpath), cv2.IMREAD_UNCHANGED)
            if d is not None:
                if d.ndim == 3:
                    d = d[..., 0]
                d = np.nan_to_num(d, nan=0.0, posinf=0.0, neginf=0.0)
                if scale != 1.0:
                    d = cv2.resize(d, (Ws, Hs), interpolation=cv2.INTER_NEAREST)
                depths[i] = d
    viewmats_np = np.stack(viewmats_np)

    from arrgs_train import project_mask
    masks = np.stack([project_mask(fp, ground_z, top_z, viewmats_np[i], Ks_np[i],
                                   Ws, Hs, buffer_scale=1.12) for i in range(len(sel))])
    # occluder rejection (OPT-IN, scene["occluder_mask"]): keep a masked pixel
    # only if its fused-MVS depth ray lands inside the footprint prism. B022
    # A/B: this REGRESSED f1 0.394->0.298 (MVS facade noise drops true building
    # pixels too) — default off, kept for follow-up diagnosis.
    from shapely.geometry import Polygon as ShPoly2
    from shapely.prepared import prep as prep2
    fp_prism = prep2(ShPoly2(fp).buffer(1.5))
    from shapely.geometry import Point as ShPt2
    for i in range(len(sel) if scene.get("occluder_mask") else 0):
        d = depths[i]
        valid = d > 0.5
        if not valid.any():
            continue
        Kinv = np.linalg.inv(Ks_np[i])
        Rw = viewmats_np[i][:3, :3].T  # cam->world (viewer-local)
        tw = -Rw @ viewmats_np[i][:3, 3]
        ys, xs = np.nonzero(masks[i] & valid)
        if len(ys) == 0:
            continue
        rays = (Kinv @ np.stack([xs + 0.5, ys + 0.5, np.ones(len(xs))])).T
        pts = (Rw @ (rays * d[ys, xs][:, None]).T).T + tw
        inside_z = (pts[:, 2] > ground_z - 1.0) & (pts[:, 2] < top_z + 2.0)
        keep = np.zeros(len(pts), dtype=bool)
        # coarse XY test on a 0.5 m grid cache to avoid per-point shapely calls
        gx = np.round(pts[:, 0] * 2) / 2
        gy = np.round(pts[:, 1] * 2) / 2
        cache = {}
        for j, (x, y) in enumerate(zip(gx, gy)):
            key = (x, y)
            if key not in cache:
                cache[key] = fp_prism.contains(ShPt2(x, y))
            keep[j] = cache[key]
        keep &= inside_z
        drop = ~keep
        masks[i][ys[drop], xs[drop]] = False

    return {
        "planes": planes, "footprint": fp, "ground_z": ground_z, "top_z": top_z,
        "o_init_fn": o_init_fn,
        "depth_targets": torch.tensor(depths, device=device) if depths.any() else None,
        "targets": torch.tensor(targets, device=device),
        "masks": masks,
        "viewmats": torch.tensor(viewmats_np, dtype=torch.float32, device=device),
        "Ks": torch.tensor(Ks_np, dtype=torch.float32, device=device),
        "W": Ws, "H": Hs,
        "bg": torch.tensor([0.5, 0.5, 0.5], device=device),
        "view_names": [s[1]["name"] for s in sel],
        "als_points": len(als_xyz),
        "inject": [inj_e, 0.0, inj_z],
        "s1_verdict": verdict,
        "s1_mode": s1_mode if len(planes) > len(fp) + 1 else "ransac_fallback",
    }

"""Generate per-building E2 judgment visuals (dZ heatmap PNG + plane overlay SVG).

Reuses the exact evaluator functions from add_development_g3_g4_v0.py so visuals
match the v16 numbers. Read-only over frozen v16 assets; outputs to scratchpad.
"""
import base64, importlib.util, json, struct, sys, zlib
from pathlib import Path

import numpy as np
from shapely.affinity import translate
from shapely.geometry import shape, box

REPO = Path("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator")
ART = Path("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts")
V16 = ART / "phase-payloads/p2/e1_e6_roofer_ox_review_v1/P2-E1-E6-ROOFER-OX-REVIEW-v16-G3G4-DEV0P1"
OUT = Path(""+os.environ.get("JBGS_GATE5_WORK","/tmp/jbgs_gate5_work")+"/visuals.json")

spec = importlib.util.spec_from_file_location(
    "ev", REPO / "scripts/p2/e1_e6_roofer_ox_review_v1/add_development_g3_g4_v0.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)

cfg = json.load(open(REPO / "configs/p2/e1_e6_roofer_ox_review_v1/development_g3_g4_v0.json"))
crit, geo = cfg["structure_reference"], cfg["geometry_reference"]
CELL = geo["cell_size_m"]

LOD2REF = json.load(open(OUT.parent / "lod2_ref_planes.json"))
manifest = json.load(open(V16 / "viewer_manifest.json"))
origin = np.asarray(manifest["scene_local_origin_xyz"], dtype=np.float64)
fp_payload = json.load(open(ART / cfg["shared_footprints"]["path"]))
footprints = {str(f["properties"]["stable_id"]): shape(f["geometry"]) for f in fp_payload["features"]}
target_aoi = box(*map(float, cfg["roofer_target_aoi_epsg25832"]))

# ---------- tiny PNG writer ----------
def png_data_uri(rgb: np.ndarray) -> str:
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 8)) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode()

# diverging dZ colormap: blue (low) - neutral gray (0) - red (high), clamp +-2 m
def dz_color(v):
    t = max(-1.0, min(1.0, v / 2.0))
    lo, mid, hi = np.array([46, 107, 168]), np.array([158, 163, 168]), np.array([194, 69, 58])
    c = mid + (hi - mid) * t if t >= 0 else mid + (lo - mid) * (-t)
    return c.astype(np.uint8)

def seq_color(t):  # sequential blue ramp for reference height (0..1)
    lo, hi = np.array([225, 233, 241]), np.array([28, 70, 115])
    return (lo + (hi - lo) * max(0.0, min(1.0, t))).astype(np.uint8)

UNCOV = np.array([225, 200, 120], dtype=np.uint8)   # uncovered ref cell (amber tint)
BGPX = np.array([246, 247, 248], dtype=np.uint8)

def cell_grid_png(cells_xy, values, mode, scale=8, maxpx=560):
    """cells_xy: N x 2 local coords; values: N (dZ m, nan=uncovered) or heights."""
    ij = np.floor(cells_xy / CELL).astype(np.int64)
    i0, j0 = ij[:, 0].min(), ij[:, 1].min()
    ij -= [i0, j0]
    W, H = ij[:, 0].max() + 1, ij[:, 1].max() + 1
    scale = max(3, min(scale, maxpx // max(W, H) or 3))
    img = np.tile(BGPX, (H * scale, W * scale, 1))
    if mode == "ref":
        lo, hi = np.percentile(values, 2), np.percentile(values, 98)
        rng = max(hi - lo, 0.5)
    for (cx, cy), v in zip(ij, values):
        if mode == "dz":
            col = UNCOV if np.isnan(v) else dz_color(v)
        else:
            col = seq_color((v - lo) / rng)
        y = (H - 1 - cy) * scale
        x = cx * scale
        img[y:y + scale, x:x + scale] = col
    return png_data_uri(img), int(W), int(H)

# ---------- plane overlay SVG ----------
def poly_paths(geom):
    geoms = getattr(geom, "geoms", [geom])
    out = []
    for g in geoms:
        if g.is_empty or not hasattr(g, "exterior"):
            continue
        rings = [g.exterior] + list(g.interiors)
        d = ""
        for r in rings:
            pts = list(r.coords)
            d += "M" + "L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + "Z"
        out.append(d)
    return out

def overlay_svg(fp_local, ref_planes, pred_planes, matches):
    minx, miny, maxx, maxy = fp_local.bounds
    pad = 1.5
    minx, miny, maxx, maxy = minx - pad, miny - pad, maxx + pad, maxy + pad
    w, h = maxx - minx, maxy - miny
    m_ref = {r for _, _, r, _ in matches}
    m_pred = {p for _, _, _, p in matches}
    def tx(d):  # flip y for SVG
        return d
    parts = [f'<svg viewBox="0 0 {w:.1f} {h:.1f}" xmlns="http://www.w3.org/2000/svg">',
             f'<g transform="translate({-minx:.2f},{maxy:.2f}) scale(1,-1)">']
    for d in poly_paths(fp_local):
        parts.append(f'<path d="{d}" fill="none" stroke="#8B95A0" stroke-width="0.22" stroke-dasharray="0.7 0.5"/>')
    for i, pl in enumerate(ref_planes):          # missed reference planes = amber
        if i in m_ref: continue
        for d in poly_paths(pl["polygon"]):
            parts.append(f'<path d="{d}" fill="#C98A1F" fill-opacity="0.30" stroke="#A8721F" stroke-width="0.18"/>')
    for j, pl in enumerate(pred_planes):         # spurious prediction planes = red
        if j in m_pred: continue
        for d in poly_paths(pl["polygon"]):
            parts.append(f'<path d="{d}" fill="#C2453A" fill-opacity="0.32" stroke="#C2453A" stroke-width="0.18"/>')
    for j, pl in enumerate(pred_planes):         # matched prediction planes = blue fill
        if j not in m_pred: continue
        for d in poly_paths(pl["polygon"]):
            parts.append(f'<path d="{d}" fill="#2E6BA8" fill-opacity="0.34" stroke="#2E6BA8" stroke-width="0.18"/>')
    for i, pl in enumerate(ref_planes):          # matched reference outline = dark ink
        if i not in m_ref: continue
        for d in poly_paths(pl["polygon"]):
            parts.append(f'<path d="{d}" fill="none" stroke="#1B2026" stroke-width="0.14" stroke-dasharray="0.45 0.3"/>')
    parts.append("</g></svg>")
    return "".join(parts)

def pack_obj(path, center):
    """Compact mesh: shared-center 2dp vertices + triangulated index list."""
    if path is None or not path.is_file():
        return None
    verts, faces = [], []
    for line in path.read_text(encoding="ascii").splitlines():
        if line.startswith("v "):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("f "):
            idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
            for k in range(1, len(idx) - 1):
                faces += [idx[0], idx[k], idx[k + 1]]
    if not verts or not faces:
        return None
    v = np.asarray(verts, dtype=np.float64) - center
    return {"v": [round(float(x), 2) for x in v.ravel()], "f": faces}


def g3_matches(reference, prediction, thr):
    edges = []
    for ri, ref in enumerate(reference):
        for pi, pred in enumerate(prediction):
            ov = float(ref["polygon"].intersection(pred["polygon"]).area)
            if ov <= 0: continue
            if ov / ref["area_m2"] >= thr and ov / pred["area_m2"] >= thr:
                union = ref["area_m2"] + pred["area_m2"] - ov
                edges.append((ov / union if union > 0 else 0.0, ov, ri, pi))
    used_r, used_p, out = set(), set(), []
    for e in sorted(edges, reverse=True):
        if e[2] in used_r or e[3] in used_p: continue
        used_r.add(e[2]); used_p.add(e[3]); out.append(e)
    return out

# ---------- main loop ----------
vis, checks = {}, []
for b in manifest["buildings"]:
    sid = b["stable_id"]
    idx = int(b["population_index"])
    fp = footprints[sid]
    fp_local = translate(fp, xoff=-origin[0], yoff=-origin[1])
    inset = fp_local.buffer(-geo["evaluation_inset_m"])
    eval_poly = inset if not inset.is_empty else fp_local
    e1 = b["lidar"]
    entry = {}

    # G3 reference policy: original-CityGML LoD2 RoofSurfaces (primary, metric frame)
    # -> valid E1 Roofer planes (secondary) -> none.
    ref_planes, ref_src = [], None
    for p in LOD2REF.get(sid, []):
        poly = ev.Polygon(p["ring"])
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area <= 1e-6:
            continue
        ref_planes.append({"polygon": poly, "area_m2": float(poly.area),
                           "normal": np.asarray(p["normal"], dtype=np.float64)})
    ref_planes = ev.major_planes(ref_planes, crit["minimum_plane_area_m2"]) if ref_planes else []
    if ref_planes:
        ref_src = "L"
    elif e1.get("technical_status") == "TECHNICAL_VALID_LOD22" and e1.get("roofer"):
        ref_planes = ev.major_planes(
            ev.cluster_roof_planes(ev.parse_obj_triangles(V16 / e1["roofer"]),
                                   crit["plane_angle_tolerance_deg"], crit["plane_height_tolerance_m"]),
            crit["minimum_plane_area_m2"])
        ref_src = "E1" if ref_planes else None
    entry["rs"] = ref_src
    ref_cells = (ev.roof_reference_cells(V16 / e1["points"], CELL, eval_poly)
                 if e1.get("point_count", 0) > 0 else np.empty((0, 3)))

    e2 = b["mvs"]
    tri = ev.parse_obj_triangles(V16 / e2["roofer"]) if e2.get("roofer") else np.empty((0, 3, 3))

    # embedded 3D meshes (shared per-building center keeps overlays aligned)
    c = np.asarray(fp_local.centroid.coords[0] + (0.0,), dtype=np.float64)
    for key, path in (("m2", V16 / e2["roofer"] if e2.get("roofer") else None),
                      ("m1", V16 / e1["roofer"] if e1.get("roofer") else None),
                      ("mp", V16 / b["comparison_priors"]["PRIOR_LOD2"]["roofer"]
                       if b.get("comparison_priors", {}).get("PRIOR_LOD2", {}).get("roofer") else None)):
        packed = pack_obj(path, c)
        if packed:
            entry[key] = packed

    # per-condition normal angle vs E1 reference planes (E1 vs itself ~ 0 = sanity)
    nac = {}
    conds = {"E1": e1, "E2": e2}
    for cn in ("E3", "E4", "E5", "E6"):
        if b.get("conditions", {}).get(cn):
            conds[cn] = b["conditions"][cn]
    l2 = {}
    if ref_planes:
        ref_area = sum(p["area_m2"] for p in ref_planes)
        for cn, spec in conds.items():
            rp = spec.get("roofer")
            if not rp:
                continue
            t = ev.parse_obj_triangles(V16 / rp)
            if not len(t):
                continue
            pp = ev.major_planes(
                ev.cluster_roof_planes(t, crit["plane_angle_tolerance_deg"], crit["plane_height_tolerance_m"]),
                crit["minimum_plane_area_m2"])
            if not pp:
                continue
            pred_area = sum(p["area_m2"] for p in pp)
            # granularity-robust matching: normal-compatible (<=15 deg) union coverage, 1:M allowed
            ANG = 15.0
            def angle(a, b):
                return float(np.degrees(np.arccos(abs(float(np.clip(np.dot(a["normal"], b["normal"]), -1, 1))))))
            cov_r = 0.0
            asum = wsum = 0.0
            for rp_ in ref_planes:
                compat = []
                for p_ in pp:
                    ov = float(rp_["polygon"].intersection(p_["polygon"]).area)
                    if ov <= 0:
                        continue
                    ang = angle(rp_, p_)
                    asum += ang * ov
                    wsum += ov
                    if ang <= ANG:
                        compat.append(p_["polygon"])
                if compat:
                    cov_r += float(rp_["polygon"].intersection(ev.unary_union(compat)).area)
            cov_p = 0.0
            for p_ in pp:
                compat = [rp_["polygon"] for rp_ in ref_planes
                          if angle(rp_, p_) <= ANG and rp_["polygon"].intersects(p_["polygon"])]
                if compat:
                    cov_p += float(p_["polygon"].intersection(ev.unary_union(compat)).area)
            c = min(cov_r / ref_area, 1.0) if ref_area > 0 else None
            co = min(cov_p / pred_area, 1.0) if pred_area > 0 else None
            q = None
            if c is not None and co is not None:
                q = (c * co / (c + co - c * co)) if (c + co - c * co) > 0 else 0.0
            na = round(asum / wsum, 2) if wsum > 0 else None
            l2[cn] = [round(c, 3) if c is not None else None,
                      round(co, 3) if co is not None else None,
                      round(q, 3) if q is not None else None, na]
    if l2:
        entry["l2"] = l2
    nac = {cn: v[3] for cn, v in l2.items() if v[3] is not None}
    if nac:
        entry["nac"] = nac

    if len(tri):
        pred_planes = ev.major_planes(
            ev.cluster_roof_planes(tri, crit["plane_angle_tolerance_deg"], crit["plane_height_tolerance_m"]),
            crit["minimum_plane_area_m2"])
        matches = g3_matches(ref_planes, pred_planes, crit["matching_overlap_fraction"])
        if matches:
            angs, wts = [], []
            for _, ov, ri, pi in matches:
                d = float(np.clip(np.dot(ref_planes[ri]["normal"], pred_planes[pi]["normal"]), -1, 1))
                angs.append(float(np.degrees(np.arccos(d)))); wts.append(ov)
            entry["na"] = round(sum(a * w for a, w in zip(angs, wts)) / sum(wts), 2)
            entry["nap"] = [round(a, 1) for a in angs]
        if ref_planes or pred_planes:
            entry["ov"] = overlay_svg(fp_local, ref_planes, pred_planes, matches)
            entry["pn"] = [len(ref_planes), len(pred_planes), len(matches)]
        if len(ref_cells):
            pz = ev.top_surface_z(tri, ref_cells[:, :2])
            dz = np.where(np.isfinite(pz), pz - ref_cells[:, 2], np.nan)
            uri, W, H = cell_grid_png(ref_cells[:, :2], dz, "dz")
            entry["dz"] = uri; entry["gw"] = W; entry["gh"] = H
            fin = np.isfinite(dz)
            if fin.sum():
                rm = float(np.sqrt(np.mean(dz[fin] ** 2)))
                mref = e2.get("development_g3_g4", {}).get("g4", {}).get("rmse_z_m")
                if mref is not None:
                    checks.append((idx, rm, mref))
    else:
        if len(ref_cells):  # generation failure: show what exists to reconstruct
            uri, W, H = cell_grid_png(ref_cells[:, :2], ref_cells[:, 2], "ref")
            entry["ref"] = uri; entry["gw"] = W; entry["gh"] = H
        if ref_planes:
            entry["ov"] = overlay_svg(fp_local, ref_planes, [], [])
            entry["pn"] = [len(ref_planes), 0, 0]
    if entry:
        vis[idx] = entry

json.dump(vis, open(OUT, "w"), separators=(",", ":"))
size = OUT.stat().st_size
bad = [c for c in checks if abs(c[1] - c[2]) > 1e-6]
print(f"visuals for {len(vis)} buildings, {size/1e6:.2f} MB")
print(f"RMSZ sanity: {len(checks)} compared, {len(bad)} mismatched")
if bad[:3]: print("mismatches:", bad[:3])

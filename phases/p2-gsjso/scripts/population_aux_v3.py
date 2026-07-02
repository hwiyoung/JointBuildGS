#!/usr/bin/env python3
"""population-aux v3 — UNIFIED observation-geometry raw material over ALL 199 buildings, single
definition·single script (new computation, NO reconstruction/retrain). Observe only; NO subclass
labels (rules=김휘영). Geo CRS 25832 (footprints/GML); OPF/COLMAP frame 32632 (sub-m offset,
negligible for view geometry, same as P0 T9). Runs in jointbuildgs:dev (needs cv2).

Reuses the P0 T9 projection math (parse_colmap_cameras/project_points/incidence_angle + OPF scene_ref)
and the LoD2 GML 3D roof faces (per building). For each building:
 [1] sample reference roof faces (~1 pt/m^2, cap SAMPLE_CAP); per sample: visible views (in-frame),
     incidence angle (view↔roof-normal), pairwise parallax angles among visible views, coverage.
     -> n_views_nadir(≤20°)/oblique/total, median_pair_angle_deg, frac_pairs_10_60deg,
        median_incidence_deg, frac_views_incidence_le60, roof_obs_covered_frac
 [2] Reconstructability (Smith et al. 2018 idea; adopted weight forms documented in QA/versions):
     R_sample = Σ_(visible view pairs) w_parallax(α)·w_incidence(θ)·w_distance(d); building=median,p10.
 [3] roof texture (near-nadir else lowest-incidence view crop): roof_lowtex_frac (T11 sharp def),
     roof_grad_p10, roof_sat_frac (bright-saturated frac = specular proxy), roof_periodicity (2nd
     autocorrelation peak = repetitive-pattern proxy).
 [4] occlusion approx (T7 logic ext): neighbour-building height blocking roof-ward line of sight.
Out: population_aux_v3.csv (199) + prints coverage. Params echoed for versions.txt/QA.
"""
import csv, glob, json, math, sys
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import cv2

ROOT = Path("/workspace/JointBuildGS/phases/p0-audit")
REPO = Path("/workspace/JointBuildGS")
DATA = ROOT / "data"
IMAGE_DIR = DATA / "work/images/Images"
GEOJSON = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
GMLDIR = DATA / "raw/lod2"
OUT = REPO / "results/tum_transfer/mob/overseg_lever/population_aux_v3.csv"


# ---- LoD2 GML 3D roof faces (copied verbatim from d6_shape_audit; xml-only, no laspy) ----
def _Lc(t): return t.rsplit("}", 1)[-1]

def gml_building(bid):
    """roofType, roof RoofSurface 3D rings, wall rings."""
    full = f"DEBY_LOD2_{bid}"
    for g in glob.glob(str(GMLDIR / "*.gml")):
        for _, el in ET.iterparse(g, events=("end",)):
            if _Lc(el.tag) != "Building":
                continue
            b = next((v for k, v in el.attrib.items() if _Lc(k) == "id"), None)
            if b != full:
                el.clear(); continue
            rts = [e.text.strip() for e in el.iter() if _Lc(e.tag) == "roofType" and e.text]
            def rings(kind):
                out = []
                for s in el.iter():
                    if _Lc(s.tag) != kind:
                        continue
                    for pl in s.iter():
                        if _Lc(pl.tag) == "posList" and pl.text:
                            out.append(np.array([float(x) for x in pl.text.split()]).reshape(-1, 3))
                return out
            roof, wall = rings("RoofSurface"), rings("WallSurface")
            el.clear()
            return (rts[0] if rts else "NONE"), roof, wall
    return "NONE", [], []

# ---- adopted parameters (echoed to QA) ----
SAMPLE_DENSITY = 1.0      # pt / m^2
SAMPLE_CAP = 400          # per building
NADIR_MAX_DEG = 20.0      # near-nadir incidence threshold (project convention)
INC_OK_DEG = 60.0         # Soudarissanane incidence bound
PAIR_LO, PAIR_HI = 10.0, 60.0   # Schoenberger-style parallax band
MAXV_PAIR = 24            # cap visible views per sample for pairwise (keep lowest-incidence)
# Smith2018-style weights (adopted forms; see QA)
PAR_PEAK = 20.0; PAR_SIG = 20.0   # w_parallax gaussian around 20deg
D_LO, D_HI = 20.0, 120.0          # w_distance plateau (m); linear decay outside
LOWTEX_GRAD = 0.02                # T11 sharp low-texture gradient threshold (normalized [0,1] gray)
SAT_THRESH = 0.97                 # bright-saturation fraction threshold


# ===== copied P0 projection math (self-contained; identical to 09_failure_surface_cause) =====
def qvec_to_rotmat(q):
    q0, q1, q2, q3 = q
    return np.array([[1-2*q2*q2-2*q3*q3, 2*q1*q2-2*q0*q3, 2*q3*q1+2*q0*q2],
                     [2*q1*q2+2*q0*q3, 1-2*q1*q1-2*q3*q3, 2*q2*q3-2*q0*q1],
                     [2*q3*q1-2*q0*q2, 2*q2*q3+2*q0*q1, 1-2*q1*q1-2*q2*q2]], float)

def _t(sr): return sr.get("base_to_canonical", {})
def base_to_canonical(p, sr):
    a = p.copy(); t = _t(sr)
    if t.get("swap_xy", False): a[:, [0, 1]] = a[:, [1, 0]]
    return (a + np.array(t.get("shift", [0, 0, 0]), float)) * np.array(t.get("scale", [1, 1, 1]), float)
def canonical_to_base(p, sr):
    t = _t(sr); a = p / np.array(t.get("scale", [1, 1, 1]), float) - np.array(t.get("shift", [0, 0, 0]), float)
    if t.get("swap_xy", False): a[:, [0, 1]] = a[:, [1, 0]]
    return a

class Cam:
    __slots__ = ("name", "tvec", "rot", "center")
    def __init__(s, name, q, tv, sr):
        s.name = name; s.tvec = tv; s.rot = qvec_to_rotmat(q)
        s.center = canonical_to_base((-s.rot.T @ tv).reshape(1, 3), sr)[0]

def parse_cam_model(path):
    for ln in open(path):
        p = ln.strip().split()
        if p and not ln.startswith("#") and len(p) > 4:
            return int(p[2]), int(p[3]), np.array([float(x) for x in p[4:]], float)  # W,H,params
    raise RuntimeError("no cam model")

def parse_cameras(path, sr):
    cams = []; expect = True
    for ln in open(path):
        s = ln.strip()
        if not s or s.startswith("#"): continue
        if not expect: expect = True; continue
        p = s.split()
        cams.append(Cam(" ".join(p[9:]), np.array([float(x) for x in p[1:5]], float),
                        np.array([float(x) for x in p[5:8]], float), sr)); expect = False
    return cams

def project(points_base, cam, W, H, params, sr):
    pc = base_to_canonical(points_base, sr)
    c = (cam.rot @ pc.T).T + cam.tvec
    front = c[:, 2] > 0.1
    uv = np.full((len(points_base), 2), np.nan)
    if not front.any(): return uv, front
    fx, fy, cx, cy, k1, k2, p1, p2, k3, k4, k5, k6 = params[:12]
    x = c[front, 0]/c[front, 2]; y = c[front, 1]/c[front, 2]
    r2 = x*x+y*y; r4 = r2*r2; r6 = r4*r2
    den = 1+k4*r2+k5*r4+k6*r6; den = np.where(np.abs(den) < 1e-12, 1.0, den)
    rad = (1+k1*r2+k2*r4+k3*r6)/den
    xd = x*rad + 2*p1*x*y + p2*(r2+2*x*x); yd = y*rad + p1*(r2+2*y*y) + 2*p2*x*y
    uv[front, 0] = fx*xd+cx; uv[front, 1] = fy*yd+cy
    return uv, front


# ===== roof face sampling =====
def sample_roof(rings):
    """uniform ~SAMPLE_DENSITY/m^2 over triangulated roof faces (fan); returns (pts Nx3, normals Nx3)."""
    pts, nrm = [], []
    for r in rings:
        r = np.asarray(r, float)
        if len(r) < 3: continue
        v0 = r[0]
        # fan triangulation
        for i in range(1, len(r)-1):
            a, b, c = v0, r[i], r[i+1]
            n = np.cross(b-a, c-a); area = 0.5*np.linalg.norm(n)
            if area < 1e-6: continue
            n = n/(2*area); n = n if n[2] >= 0 else -n
            k = max(1, int(area*SAMPLE_DENSITY))
            for _ in range(k):
                s, t = np.random.rand(2)
                if s+t > 1: s, t = 1-s, 1-t
                pts.append(a + s*(b-a) + t*(c-a)); nrm.append(n)
    if not pts: return np.zeros((0, 3)), np.zeros((0, 3))
    P = np.array(pts); N = np.array(nrm)
    if len(P) > SAMPLE_CAP:
        idx = np.random.choice(len(P), SAMPLE_CAP, replace=False); P, N = P[idx], N[idx]
    return P, N


def w_parallax(a): return float(np.exp(-((a-PAR_PEAK)**2)/(2*PAR_SIG**2)))
def w_incidence(th): return float(max(0.0, math.cos(math.radians(th))))
def w_distance(d):
    if d < D_LO: return max(0.0, d/D_LO)
    if d > D_HI: return max(0.0, 1.0 - (d-D_HI)/D_HI)
    return 1.0


def main():
    sr = json.load(open(DATA/"work/opf/opf/scene_reference_frame.json"))
    W, H, params = parse_cam_model(DATA/"work/colmap/sparse/0/cameras.txt")
    cams = parse_cameras(DATA/"work/colmap/sparse/0/images.txt", sr)
    centers = np.array([c.center for c in cams])   # UTM
    print(f"[v3] {len(cams)} cameras, img {W}x{H}")
    # building list + footprints
    feats = json.load(open(GEOJSON))["features"]
    fp = {}
    for f in feats:
        bid = f["properties"]["building_id"].replace("DEBY_LOD2_", "")
        g = f["geometry"]; ring = g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len)
        nv = len(ring)-1 if len(ring) > 1 and ring[0] == ring[-1] else len(ring)
        prev = fp.get(bid)
        if prev is None or nv > prev[0]:
            fp[bid] = (nv, f["properties"].get("area_m2"), np.array(ring, float),
                       (f["properties"]["min_x"], f["properties"]["min_y"], f["properties"]["max_x"], f["properties"]["max_y"]))
    bids = sorted(fp)
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    if only: bids = [b for b in bids if b in only]
    # neighbour ridge heights for occlusion: building_id -> (cx,cy,zmax)
    nbr = []
    rows = []
    for bi, b in enumerate(bids):
        nverts, area, ring, bbox = fp[b]
        row = {"building_id": f"DEBY_LOD2_{b}", "footprint_area_m2": round(area, 2) if area else "",
               "n_exterior_vertices": nverts}
        try:
            rt, roof, wall = gml_building(b)
        except Exception:
            roof = None
        if not roof:
            rows.append({**row, **{k: "" for k in COLS}}); continue
        P, Nn = sample_roof(roof)
        if len(P) == 0:
            rows.append({**row, **{k: "" for k in COLS}}); continue
        roof_z = float(np.median(P[:, 2])); zmax = float(P[:, 2].max())
        nbr.append((float(np.mean([r0[0] for r0 in ring])), float(np.mean([r0[1] for r0 in ring])), zmax, b))
        # candidate cameras: those whose footprint bbox roughly projects in-frame (cheap prefilter)
        corners = np.array([[bbox[0], bbox[1], roof_z], [bbox[2], bbox[1], roof_z],
                            [bbox[2], bbox[3], roof_z], [bbox[0], bbox[3], roof_z]])
        cand = []
        for ci, cam in enumerate(cams):
            uv, fr = project(corners, cam, W, H, params, sr)
            if fr.any() and np.nanmax(uv[:, 0]) >= 0 and np.nanmin(uv[:, 0]) < W and np.nanmax(uv[:, 1]) >= 0 and np.nanmin(uv[:, 1]) < H:
                cand.append(ci)
        # per-sample visibility (VECTORIZED per camera: project all samples at once)
        ns = len(P)
        per = [ [] for _ in range(ns) ]   # per sample: list of (incidence, dist, ray_unit, cam_idx)
        for ci in cand:
            cam = cams[ci]
            uv, fr = project(P, cam, W, H, params, sr)
            inframe = fr & (uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)
            if not inframe.any(): continue
            vd = cam.center - P                     # (ns,3) point->camera vectors
            dist = np.linalg.norm(vd, axis=1)
            unit = vd/np.maximum(dist[:, None], 1e-9)
            cosinc = np.clip(np.abs(np.sum(unit*Nn, axis=1)), -1, 1)
            inc = np.degrees(np.arccos(cosinc))                       # view vs roof normal
            nad = np.degrees(np.arccos(np.clip(unit[:, 2], -1, 1)))   # view vs vertical (nadir angle)
            for si in np.where(inframe)[0]:
                per[si].append((float(inc[si]), float(dist[si]), unit[si], ci, float(nad[si])))
        n_nad = n_obl = n_tot = covered = 0
        pair_angles, incid_all, recon = [], [], []
        # building-level best texture view: near-nadir preferred (min nadir angle) else lowest incidence
        best_nadir = (1e9, None); best_incid = (1e9, None)
        for si in range(ns):
            vis = per[si]
            if not vis: continue
            vis.sort(key=lambda t: t[0])   # by incidence
            for inc, d, u, ci, nad in vis:
                incid_all.append(inc)
                if nad <= NADIR_MAX_DEG: n_nad += 1
                else: n_obl += 1
                if nad < best_nadir[0]: best_nadir = (nad, cams[ci].name)
                if inc < best_incid[0]: best_incid = (inc, cams[ci].name)
            n_tot += len(vis)
            vv = vis[:MAXV_PAIR]
            rays = np.array([t[2] for t in vv]); incs = np.array([t[0] for t in vv]); dists = np.array([t[1] for t in vv])
            if len(vv) >= 2:
                cosm = np.clip(rays @ rays.T, -1, 1); ang = np.degrees(np.arccos(cosm))
                iu, ju = np.triu_indices(len(vv), k=1)
                pang = ang[iu, ju]; pair_angles.extend(pang.tolist())
                good = bool(np.any((pang >= PAIR_LO) & (pang <= PAIR_HI)))
                wp = np.exp(-((pang-PAR_PEAK)**2)/(2*PAR_SIG**2))
                wi = np.maximum(0.0, np.cos(np.radians(0.5*(incs[iu]+incs[ju]))))
                dm = 0.5*(dists[iu]+dists[ju])
                wd = np.where(dm < D_LO, np.maximum(0, dm/D_LO), np.where(dm > D_HI, np.maximum(0, 1-(dm-D_HI)/D_HI), 1.0))
                recon.append(float(np.sum(wp*wi*wd)))
                if good: covered += 1
            else:
                recon.append(0.0)
        # occlusion approx computed after all buildings' ridge heights known -> placeholder now
        row.update({
            "n_samples": ns,
            "n_views_nadir": round(n_nad/ns, 2), "n_views_oblique": round(n_obl/ns, 2), "n_views_total": round(n_tot/ns, 2),
            "median_pair_angle_deg": round(float(np.median(pair_angles)), 2) if pair_angles else "",
            "frac_pairs_10_60deg": round(float(np.mean([(PAIR_LO <= a <= PAIR_HI) for a in pair_angles])), 3) if pair_angles else "",
            "median_incidence_deg": round(float(np.median(incid_all)), 2) if incid_all else "",
            "frac_views_incidence_le60": round(float(np.mean([(i <= INC_OK_DEG) for i in incid_all])), 3) if incid_all else "",
            "roof_obs_covered_frac": round(covered/ns, 3),
            "recon_score_median": round(float(np.median(recon)), 3) if recon else 0.0,
            "recon_score_p10": round(float(np.percentile(recon, 10)), 3) if recon else 0.0,
            "_best_view": (best_nadir[1] if best_nadir[0] <= NADIR_MAX_DEG else best_incid[1]) or "",
            "_ring": ring.tolist(), "_roof_z": roof_z, "_zmax": zmax,
            "_cx": float(np.mean(ring[:, 0])), "_cy": float(np.mean(ring[:, 1])),
        })
        # [3] texture from best (lowest-incidence) view
        tex = roof_texture(row["_best_view"], roof, W, H, params, sr, cams)
        row.update(tex)
        rows.append(row)
        if (bi+1) % 20 == 0: print(f"[v3] {bi+1}/{len(bids)} buildings")
    # [4] occlusion approx: neighbour ridge blocks roof-ward LOS (coarse: any neighbour within 30m taller than roof+2m)
    nb = np.array([(x, y, z) for x, y, z, _ in nbr]) if nbr else np.zeros((0, 3))
    for r in rows:
        if "_cx" not in r: r["occlusion_frac_approx"] = ""; continue
        cx, cy, zt = r["_cx"], r["_cy"], r["_zmax"]
        if len(nb) == 0: r["occlusion_frac_approx"] = 0.0; continue
        d = np.sqrt((nb[:, 0]-cx)**2 + (nb[:, 1]-cy)**2)
        near = (d > 1) & (d < 30.0)
        taller = near & (nb[:, 2] > zt + 2.0)
        r["occlusion_frac_approx"] = round(float(taller.sum()/max(1, near.sum())), 3) if near.any() else 0.0
    # write (strip private _ cols)
    cols = ["building_id", "footprint_area_m2", "n_exterior_vertices", "n_samples",
            "n_views_nadir", "n_views_oblique", "n_views_total",
            "median_pair_angle_deg", "frac_pairs_10_60deg", "median_incidence_deg", "frac_views_incidence_le60",
            "roof_obs_covered_frac", "recon_score_median", "recon_score_p10",
            "roof_lowtex_frac", "roof_grad_p10", "roof_sat_frac", "roof_periodicity", "occlusion_frac_approx"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as fo:
        w = csv.DictWriter(fo, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in cols})
    print(f"[done] {len(rows)} buildings -> {OUT}")
    nonblank = lambda k: sum(1 for r in rows if r.get(k) not in ("", None))
    for k in cols[3:]: print(f"  {k:26} {nonblank(k)}/{len(rows)}")


def _incidence(center, target, normal):
    v = center - target; n = np.linalg.norm(v)
    if n <= 0: return math.nan
    return math.degrees(math.acos(abs(float(np.clip((v/n) @ normal, -1, 1)))))


def roof_texture(view_name, roof, W, H, params, sr, cams):
    """texture on ROOF-POLYGON pixels of the chosen view. lowtex/grad = detail; sat = specular proxy;
    periodicity = strongest autocorrelation peak OUTSIDE the main central lobe (repeat-pattern proxy)."""
    blank = {"roof_lowtex_frac": "", "roof_grad_p10": "", "roof_sat_frac": "", "roof_periodicity": ""}
    if not view_name: return blank
    img_path = IMAGE_DIR / view_name
    if not img_path.exists(): return blank
    cam = next((c for c in cams if c.name == view_name), None)
    if cam is None: return blank
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None: return blank
    # project each roof ring; build polygon mask in the crop
    polys = []
    xs, ys = [], []
    for r in roof:
        r = np.asarray(r, float)
        if len(r) < 3: continue
        uv, fr = project(r, cam, W, H, params, sr)
        if fr.sum() < 3: continue
        polys.append(uv[fr]); xs += uv[fr, 0].tolist(); ys += uv[fr, 1].tolist()
    if not polys: return blank
    x0 = int(max(0, min(xs))); y0 = int(max(0, min(ys)))
    x1 = int(min(W, max(xs))); y1 = int(min(H, max(ys)))
    if x1-x0 < 8 or y1-y0 < 8: return blank
    crop = img[y0:y1, x0:x1].astype(np.float32)/255.0
    mask = np.zeros(crop.shape, np.uint8)
    for p in polys:
        q = np.round(p - [x0, y0]).astype(np.int32)
        cv2.fillPoly(mask, [q], 1)
    m = mask.astype(bool)
    if m.sum() < 32: return blank
    # downsample large crops for stable periodicity scale + speed
    if max(crop.shape) > 512:
        s = 512.0/max(crop.shape)
        crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        mask = cv2.resize(mask, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_NEAREST)
        m = mask.astype(bool)
    gx = cv2.Sobel(crop, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(crop, cv2.CV_32F, 0, 1, ksize=3)
    grad = np.sqrt(gx*gx+gy*gy)
    lowtex = float(np.mean(grad[m] < LOWTEX_GRAD)); gp10 = float(np.percentile(grad[m], 10))
    sat = float(np.mean(crop[m] > SAT_THRESH))
    # periodicity: masked autocorrelation; zero the main central lobe (radius ~ min(h,w)/8), take max outside
    c = crop.copy(); c[~m] = crop[m].mean(); c = (c - crop[m].mean()) * mask
    f = np.fft.fft2(c); ac = np.fft.fftshift(np.fft.ifft2(f*np.conj(f)).real)
    ac = ac/(ac.max()+1e-9)
    cy, cx = np.array(ac.shape)//2
    R = max(3, min(ac.shape)//8)
    yy, xx = np.ogrid[:ac.shape[0], :ac.shape[1]]
    ac[(yy-cy)**2 + (xx-cx)**2 <= R*R] = 0    # remove main lobe
    period = float(ac.max())
    return {"roof_lowtex_frac": round(lowtex, 3), "roof_grad_p10": round(gp10, 4),
            "roof_sat_frac": round(sat, 4), "roof_periodicity": round(period, 3)}


COLS = ["n_samples", "n_views_nadir", "n_views_oblique", "n_views_total", "median_pair_angle_deg",
        "frac_pairs_10_60deg", "median_incidence_deg", "frac_views_incidence_le60", "roof_obs_covered_frac",
        "recon_score_median", "recon_score_p10", "roof_lowtex_frac", "roof_grad_p10", "roof_sat_frac",
        "roof_periodicity", "occlusion_frac_approx"]

if __name__ == "__main__":
    np.random.seed(0)
    main()

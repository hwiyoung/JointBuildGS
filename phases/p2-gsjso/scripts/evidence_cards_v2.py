#!/usr/bin/env python3
"""population-lock-aux v4 / evidence-cards-v2 — readable evidence cards for the 27 non-A buildings, with a
CORRECT roof/footprint projection (near-plane Sutherland-Hodgman clip -> behind-camera vertices culled, no
spikes; roof faces UNIONED to one outline, not a per-face mesh). Read + small compute; NO reconstruction.
Observe only; verdict/label/demolition=김휘영 (NO labels attached). EPSG:25832 geo / 32632 OPF frame.
Runs in jointbuildgs-p0-tools:t0 (PIL+laspy+matplotlib; NO cv2).

4 panels/card: (a) context ~60m crop @ bestview: yellow=footprint proj, green=roof-union outline, arrow+ID;
(b) roof close-up: same view, semi-transparent green roof mask (what lowtex_v4 read); (c)(d) DIM/ALS top-view.
Also: [2] QA closeups for the 5 most-oblique-view buildings + off-roof report; [3] time-diff dumps + date table.
"""
import json, csv, glob, math, sys
from pathlib import Path
import numpy as np
import laspy
from PIL import Image, ImageDraw
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from projection_datum import (
    as_ellipsoidal_points,
    base_to_canonical_points,
    canonical_to_base_points,
)

ROOT = Path("/workspace/JointBuildGS/phases/p0-audit")
REPO = Path("/workspace/JointBuildGS")
DATA = ROOT / "data"
IMAGE_DIR = DATA / "work/images/Images"
GMLDIR = DATA / "raw/lod2"
GEOJSON = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
DIM_CLOUD = DATA / "work/w2/dim_v1_classified_z_minus0p174.laz"
ALS_TILES = sorted(glob.glob(str(DATA / "raw/als/*.la[sz]")))
CARDDIR = REPO / "docs/evidence_cards_v2"
BVIEW = REPO / "results/tum_transfer/mob/overseg_lever/population_aux_v3_bestview.json"
IMAGERY_DATE = "2024-12-17"
TD_TARGETS = ["4906999", "42364663", "4959320", "42364667"]   # [3] task-named + high-error-both
import xml.etree.ElementTree as ET


def qrot(q):
    w, x, y, z = q
    return np.array([[1-2*y*y-2*z*z, 2*x*y-2*w*z, 2*z*x+2*w*y],
                     [2*x*y+2*w*z, 1-2*x*x-2*z*z, 2*y*z-2*w*x],
                     [2*z*x-2*w*y, 2*y*z+2*w*x, 1-2*x*x-2*y*y]], float)

def b2c(p, sr, input_datum="orthometric", geoid_m=None):
    return base_to_canonical_points(p, sr, input_datum=input_datum, geoid_m=geoid_m)

class Cam:
    __slots__ = ("name", "tvec", "rot", "center")
    def __init__(s, name, q, tv, sr):
        s.name = name; s.tvec = tv; s.rot = qrot(q)
        cc = (-s.rot.T @ tv)
        s.center = canonical_to_base_points(cc.reshape(1, 3), sr)[0]

def parse_cam_model(path):
    for ln in open(path):
        p = ln.strip().split()
        if p and not ln.startswith("#") and len(p) > 4:
            return int(p[2]), int(p[3]), np.array([float(x) for x in p[4:]], float)

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


# ---- clean projection: base UTM -> camera coords -> near-plane clip -> distort -> pixels ----
def to_cam(ring_base, cam, sr, input_datum="orthometric", geoid_m=None):
    pc = b2c(ring_base, sr, input_datum=input_datum, geoid_m=geoid_m)
    return (cam.rot @ pc.T).T + cam.tvec           # (N,3) camera coords, +z forward

def clip_near(cam_poly, eps=1.0):
    """Sutherland-Hodgman clip a closed polygon (Nx3 cam coords) against plane z>eps."""
    P = list(cam_poly); out = []
    n = len(P)
    for i in range(n):
        a = P[i]; b = P[(i+1) % n]
        ain = a[2] > eps; bin_ = b[2] > eps
        if ain: out.append(a)
        if ain != bin_:
            t = (eps - a[2])/(b[2]-a[2])
            out.append(a + t*(b-a))
    return np.array(out) if out else np.zeros((0, 3))

def clip_frustum(cam_poly, params, W=5280, H=3956, margin=0.12):
    """clip polygon (Nx3 cam coords, z>0) to the view FOV in normalized (X/Z,Y/Z) space, so no vertex
    lands at a huge field angle where the FULL_OPENCV rational distortion extrapolates/explodes."""
    fx, fy, cx, cy = params[:4]
    xmin = (0-cx)/fx - margin; xmax = (W-cx)/fx + margin
    ymin = (0-cy)/fy - margin; ymax = (H-cy)/fy + margin

    def clip(pts, val):
        out = []; n = len(pts)
        for i in range(n):
            a = pts[i]; b = pts[(i+1) % n]
            va = val(a); vb = val(b)
            if va >= 0: out.append(a)
            if (va >= 0) != (vb >= 0):
                t = va/(va-vb); out.append(a + t*(b-a))
        return out
    P = list(cam_poly)
    P = clip(P, lambda p: p[0]-xmin*p[2])   # X/Z >= xmin
    if P: P = clip(P, lambda p: xmax*p[2]-p[0])
    if P: P = clip(P, lambda p: p[1]-ymin*p[2])
    if P: P = clip(P, lambda p: ymax*p[2]-p[1])
    return np.array(P) if P else np.zeros((0, 3))

def distort(cam_pts, params):
    fx, fy, cx, cy, k1, k2, p1, p2, k3, k4, k5, k6 = params[:12]
    x = cam_pts[:, 0]/cam_pts[:, 2]; y = cam_pts[:, 1]/cam_pts[:, 2]
    r2 = x*x+y*y; r4 = r2*r2; r6 = r4*r2
    den = 1+k4*r2+k5*r4+k6*r6; den = np.where(np.abs(den) < 1e-12, 1.0, den)
    rad = (1+k1*r2+k2*r4+k3*r6)/den
    xd = x*rad + 2*p1*x*y + p2*(r2+2*x*x); yd = y*rad + p1*(r2+2*y*y) + 2*p2*x*y
    return np.column_stack([fx*xd+cx, fy*yd+cy])

def proj_ring(ring_base, cam, params, sr, input_datum="orthometric", geoid_m=None):
    cc = clip_near(to_cam(ring_base, cam, sr, input_datum=input_datum, geoid_m=geoid_m))
    if len(cc) < 3: return None
    cc = clip_frustum(cc, params)
    if len(cc) < 3: return None
    return distort(cc, params)


def gml_building(bid):
    full = f"DEBY_LOD2_{bid}"
    for g in glob.glob(str(GMLDIR / "*.gml")):
        for _, el in ET.iterparse(g, events=("end",)):
            if el.tag.rsplit("}", 1)[-1] != "Building": continue
            b = next((v for k, v in el.attrib.items() if k.rsplit("}", 1)[-1] == "id"), None)
            if b != full: el.clear(); continue
            def rings(kind):
                out = []
                for s in el.iter():
                    if s.tag.rsplit("}", 1)[-1] != kind: continue
                    for pl in s.iter():
                        if pl.tag.rsplit("}", 1)[-1] == "posList" and pl.text:
                            out.append(np.array([float(x) for x in pl.text.split()]).reshape(-1, 3))
                return out
            cd = next((e.text for e in el.iter() if e.tag.rsplit("}", 1)[-1] == "creationDate"), None)
            gr = None
            for e in el.iter():
                nm = e.attrib.get("name") or next((v for k, v in e.attrib.items() if k.rsplit("}", 1)[-1] == "name"), None)
                if nm == "Grundrissaktualitaet": gr = next((c.text for c in e if c.tag.rsplit("}", 1)[-1] == "value"), None)
            rt = next((e.text.strip() for e in el.iter() if e.tag.rsplit("}", 1)[-1] == "roofType" and e.text), "NONE")
            roof, wall = rings("RoofSurface"), rings("WallSurface")
            el.clear(); return dict(roof=roof, wall=wall, roofType=rt, creationDate=cd, grundriss=gr)
    return None


def clip_poly_rect(poly, x0, y0, x1, y1):
    """Sutherland-Hodgman clip a polygon (Nx2) to the axis-aligned rect -> visible sub-polygon (no spikes)."""
    def edge(pts, inside, inter):
        out = []; n = len(pts)
        for i in range(n):
            a = pts[i]; b = pts[(i+1) % n]
            ai = inside(a); bi = inside(b)
            if ai: out.append(a)
            if ai != bi: out.append(inter(a, b))
        return out
    pts = [np.asarray(p, float) for p in poly]
    pts = edge(pts, lambda p: p[0] >= x0, lambda a, b: a+(b-a)*((x0-a[0])/((b[0]-a[0]) or 1e-9)))
    if not pts: return []
    pts = edge(pts, lambda p: p[0] <= x1, lambda a, b: a+(b-a)*((x1-a[0])/((b[0]-a[0]) or 1e-9)))
    if not pts: return []
    pts = edge(pts, lambda p: p[1] >= y0, lambda a, b: a+(b-a)*((y0-a[1])/((b[1]-a[1]) or 1e-9)))
    if not pts: return []
    pts = edge(pts, lambda p: p[1] <= y1, lambda a, b: a+(b-a)*((y1-a[1])/((b[1]-a[1]) or 1e-9)))
    return pts


def roof_mask(roof_rings, cam, params, sr, W, H):
    """PIL union mask of projected roof faces (each ring near-plane clipped then rect-clipped -> no spikes)."""
    im = Image.new("L", (W, H), 0); dr = ImageDraw.Draw(im)
    for r in roof_rings:
        uv = proj_ring(r, cam, params, sr)
        if uv is None or len(uv) < 3: continue
        cp = clip_poly_rect(uv, 0, 0, W-1, H-1)
        if len(cp) >= 3:
            dr.polygon([tuple(map(float, p)) for p in cp], fill=1)
    return np.asarray(im, bool)


def nadir_of(cam, ctr3, input_datum="orthometric", geoid_m=None):
    target = as_ellipsoidal_points(np.asarray(ctr3, float), input_datum=input_datum, geoid_m=geoid_m)[0]
    v = cam.center - target; u = v/np.linalg.norm(v)
    return math.degrees(math.acos(min(1, abs(u[2]))))


def roof_inframe_frac(roof_rings, cam, sr, params, W, H):
    """fraction of roof vertices that are in front of the camera AND project inside the image."""
    allv = np.vstack(roof_rings)
    cc = to_cam(allv, cam, sr); front = cc[:, 2] > 1.0
    if front.sum() == 0: return 0.0
    uv = distort(cc[front], params)
    inb = (uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)
    return float(inb.sum())/len(allv)


def select_card_view(roof_rings, ring, cams, sr, params, W, H):
    """readable view: whole roof in front AND in-frame AND CENTERED (low-distortion region), preferring
    small nadir. The FULL_OPENCV rational distortion explodes at large field angle (image edge), so a
    half-off-frame view makes the roof polygon spike; requiring the roof near image centre avoids this."""
    allv = np.vstack(roof_rings); ctr = np.array([ring[:, 0].mean(), ring[:, 1].mean(), np.median(allv[:, 2])])
    cx, cy = params[2], params[3]
    strong, weak = [], []
    for c in cams:
        cc = to_cam(allv, c, sr); front = cc[:, 2] > 1.0
        if front.mean() < 0.99: continue
        uv = distort(cc, params)
        inb = (uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)
        infrac = inb.mean()
        rad = np.sqrt(((uv[:, 0]-cx)/(0.5*W))**2 + ((uv[:, 1]-cy)/(0.5*H))**2).max()
        nad = nadir_of(c, ctr)
        weak.append((infrac, -rad, nad, c))
        if infrac >= 0.99 and rad < 0.85:                 # whole roof safely inside central region
            strong.append((0.6*rad + 0.4*(nad/90.0), rad, nad, c))
    if strong:
        strong.sort(key=lambda t: t[0]); b = strong[0]; return b[3], b[2]
    if weak:                                              # fallback: most in-frame, then most central
        weak.sort(key=lambda t: (-t[0], t[1])); b = weak[0]; return b[3], b[2]
    return None, None


def context_bbox(ctr3, cam, params, sr, W, H, radius=30.0):
    """pixel bbox of a ~2*radius context around the building: project a circle of points, keep those in
    front AND within the FOV (|x/z|,|y/z| bounded -> no distortion explosion), bbox them, clip to image."""
    ring = np.array([[ctr3[0]+radius*math.cos(t), ctr3[1]+radius*math.sin(t), ctr3[2]] for t in np.linspace(0, 2*math.pi, 24)])
    cc = to_cam(ring, cam, sr)
    xz = cc[:, 0]/np.maximum(cc[:, 2], 1e-6); yz = cc[:, 1]/np.maximum(cc[:, 2], 1e-6)
    valid = (cc[:, 2] > 1.0) & (np.abs(xz) < 1.0) & (np.abs(yz) < 0.9)
    if valid.sum() < 3:   # fallback: centroid +- fixed box
        cc0 = to_cam(ctr3[None], cam, sr)
        if cc0[0, 2] <= 1: return None
        uv0 = distort(cc0, params)[0]
        if not (0 <= uv0[0] < W and 0 <= uv0[1] < H): return None
        return (int(max(0, uv0[0]-300)), int(max(0, uv0[1]-300)), int(min(W, uv0[0]+300)), int(min(H, uv0[1]+300)))
    uv = distort(cc[valid], params)
    x0 = max(0, int(np.min(uv[:, 0]))); y0 = max(0, int(np.min(uv[:, 1])))
    x1 = min(W, int(np.max(uv[:, 0]))); y1 = min(H, int(np.max(uv[:, 1])))
    return (x0, y0, x1, y1) if (x1-x0 > 20 and y1-y0 > 20) else None


def draw_overlay(ax, img_crop, x0, y0, footprint_uv, roof_mask_full, bb, arrow_ctr=None, bid=None, title=""):
    ax.imshow(img_crop); ax.set_title(title, fontsize=8); ax.axis("off")
    # roof union outline (green) via contour of the cropped mask
    sub = roof_mask_full[bb[1]:bb[3], bb[0]:bb[2]]
    if sub.any():
        ax.contour(sub.astype(float), levels=[0.5], colors="lime", linewidths=1.6)
    # footprint outline (yellow): rect-clip the projected polygon to the crop -> closed outline, no spikes
    if footprint_uv is not None and len(footprint_uv) >= 3:
        cp = clip_poly_rect(footprint_uv, bb[0], bb[1], bb[2], bb[3])
        if len(cp) >= 2:
            cp = np.array(cp + [cp[0]])
            ax.plot(cp[:, 0]-x0, cp[:, 1]-y0, "-", c="yellow", lw=1.6)
    if arrow_ctr is not None:
        cxp, cyp = arrow_ctr[0]-x0, arrow_ctr[1]-y0
        h, w = img_crop.shape[:2]
        if 0 <= cxp < w and 0 <= cyp < h:
            ax.annotate(bid or "", xy=(cxp, cyp), xytext=(min(w*0.9, cxp+w*0.28), max(h*0.08, cyp-h*0.22)),
                        color="red", fontsize=9, fontweight="bold",
                        arrowprops=dict(arrowstyle="->", color="red", lw=1.8))


def clip(xy, z, bb):
    m = (xy[:, 0] >= bb[0]) & (xy[:, 0] <= bb[2]) & (xy[:, 1] >= bb[1]) & (xy[:, 1] <= bb[3])
    return xy[m], z[m]


def load_clouds(aoi):
    d = laspy.read(str(DIM_CLOUD))
    dxy = np.column_stack([np.asarray(d.x), np.asarray(d.y)]).astype(np.float32); dz = np.asarray(d.z, np.float32)
    dxy, dz = clip(dxy, dz, aoi)
    axy_l, az_l = [], []
    for t in ALS_TILES:
        with laspy.open(t) as fh:
            h = fh.header
            if h.x_max < aoi[0] or h.x_min > aoi[2] or h.y_max < aoi[1] or h.y_min > aoi[3]: continue
        a = laspy.read(t)
        xy = np.column_stack([np.asarray(a.x), np.asarray(a.y)]).astype(np.float32); z = np.asarray(a.z, np.float32)
        xy, z = clip(xy, z, aoi)
        if len(xy): axy_l.append(xy); az_l.append(z)
    axy = np.vstack(axy_l) if axy_l else np.zeros((0, 2), np.float32); az = np.concatenate(az_l) if az_l else np.zeros(0, np.float32)
    return dxy, dz, axy, az


def cloud_panel(axk, xy, z, ring, name, parea):
    cxy, cz = clip(xy, z, [ring[:, 0].min()-2, ring[:, 1].min()-2, ring[:, 0].max()+2, ring[:, 1].max()+2])
    npoly = int(MPath(ring[:, :2]).contains_points(cxy).sum()) if len(cxy) else 0
    if len(cxy):
        sc = axk.scatter(cxy[:, 0], cxy[:, 1], c=cz, s=3, cmap="viridis"); plt.colorbar(sc, ax=axk, fraction=0.046, label="Z(m)")
    axk.plot(np.append(ring[:, 0], ring[0, 0]), np.append(ring[:, 1], ring[0, 1]), "r-", lw=1.2)
    axk.set_aspect("equal"); axk.set_title(f"{name} top-view in-fp={npoly} ({npoly/parea:.1f}/m2)", fontsize=8)
    axk.set_xlabel("E"); axk.set_ylabel("N"); return npoly/parea if parea > 0 else 0.0


def main():
    sr = json.load(open(DATA/"work/opf/opf/scene_reference_frame.json"))["base_to_canonical"]
    W, H, params = parse_cam_model(DATA/"work/colmap/sparse/0/cameras.txt")
    cams = parse_cameras(DATA/"work/colmap/sparse/0/images.txt", sr)
    cam_by = {c.name: c for c in cams}
    bview = {k.replace("DEBY_LOD2_", ""): v for k, v in json.load(open(BVIEW)).items()}
    v3 = {r["building_id"].replace("DEBY_LOD2_", ""): r for r in csv.DictReader(open(REPO/"docs/archive/population_aux/v3/tables/population_aux_v3.csv"))}
    canon = glob.glob(str(REPO/"phases/p0-audit/runs/w2_1_roofer_default_*/building_reconstruction_status.csv"))[0]
    dimdens = {r["building_id"].replace("DEBY_LOD2_", ""): r.get("rf_pt_density", "") for r in csv.DictReader(open(canon)) if r["input"].lower() == "dim"}
    feats = json.load(open(GEOJSON))["features"]
    fp = {}
    for f in feats:
        b = f["properties"]["building_id"].replace("DEBY_LOD2_", "")
        g = f["geometry"]; ring = np.array(g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len), float)
        if b not in fp or len(ring) > len(fp[b]): fp[b] = ring
    # 27 non-A + [3] targets union for cloud AOI
    xw = list(csv.DictReader(open(REPO/"docs/archive/bucket_crosswalk/v1/tables/bucket_crosswalk.csv")))
    A = {"A1_촬영확실", "A2_촬영경계", "경계_방법회복"}
    nonA = [r["building_id"].replace("DEBY_LOD2_", "") for r in xw if r["new_class"] not in A]
    targets = sorted(set(nonA) | set(TD_TARGETS))
    if len(sys.argv) > 1 and sys.argv[1] != "--full":
        pilot = set(sys.argv[1:]); targets = [b for b in targets if b in pilot]
    allr = np.vstack([fp[b][:, :2] for b in targets if b in fp])
    aoi = [allr[:, 0].min()-40, allr[:, 1].min()-40, allr[:, 0].max()+40, allr[:, 1].max()+40]
    dxy, dz, axy, az = load_clouds(aoi)
    print(f"clouds: DIM {len(dxy)} ALS {len(axy)} | targets {len(targets)} (nonA {len(nonA)})")
    CARDDIR.mkdir(parents=True, exist_ok=True)

    def make_view_panels(ax_ctx, ax_close, b, cam, gb, ring, roofz, ground_z):
        ctr3 = np.array([ring[:, 0].mean(), ring[:, 1].mean(), roofz])
        nad = nadir_of(cam, ctr3)
        rmask = roof_mask(gb["roof"], cam, params, sr, W, H)
        fp3 = np.column_stack([ring[:, 0], ring[:, 1], np.full(len(ring), ground_z)])
        fp_uv = proj_ring(fp3, cam, params, sr)
        cpt = None
        cc = clip_near(to_cam(ctr3[None], cam, sr))
        if len(cc): cpt = distort(cc, params)[0]
        img = np.asarray(Image.open(IMAGE_DIR/cam.name).convert("RGB"))
        # context
        cbb = context_bbox(ctr3, cam, params, sr, W, H, 30.0)
        if cbb:
            crop = img[cbb[1]:cbb[3], cbb[0]:cbb[2]]
            draw_overlay(ax_ctx, crop, cbb[0], cbb[1], fp_uv, rmask, cbb, cpt, b, f"context @{cam.name[:18]} nadir={nad:.0f}deg")
        else:
            ax_ctx.text(0.5, 0.5, "no context", ha="center"); ax_ctx.axis("off")
        # closeup: roof bbox
        ys, xs = np.where(rmask)
        if len(xs) > 10:
            rbb = [max(0, xs.min()-15), max(0, ys.min()-15), min(W, xs.max()+15), min(H, ys.max()+15)]
            crop2 = img[rbb[1]:rbb[3], rbb[0]:rbb[2]].copy()
            ax_close.imshow(crop2)
            ov = np.zeros((*crop2.shape[:2], 4)); sub = rmask[rbb[1]:rbb[3], rbb[0]:rbb[2]]
            ov[sub] = [0.1, 1.0, 0.1, 0.42]
            ax_close.imshow(ov)
            ax_close.set_title(f"roof close-up (green=lowtex_v4 mask) nadir={nad:.0f}deg", fontsize=8); ax_close.axis("off")
        else:
            ax_close.text(0.5, 0.5, "no roof mask", ha="center"); ax_close.axis("off")
        return nad, (len(xs) > 10)

    used_nadir = {}; lowtex_reliab = {}
    for b in targets:
        gb = gml_building(b); ring = fp.get(b)
        if not gb or not gb["roof"] or ring is None:
            print(f"  {b} skip (no roof/fp)"); continue
        # lowtex_v4 reliability = roof in-frame fraction on v3's bestview (the view lowtex_v4 used)
        bv = cam_by.get(bview.get(b))
        lowtex_reliab[b] = round(roof_inframe_frac(gb["roof"], bv, sr, params, W, H), 2) if bv else 0.0
        # card view = READABLE view (roof in-frame, min nadir) — not necessarily v3 bestview
        cam, _cardnad = select_card_view(gb["roof"], ring, cams, sr, params, W, H)
        if cam is None: print(f"  {b} skip (no in-frame view)"); continue
        allz = np.vstack(gb["roof"] + gb["wall"])[:, 2] if (gb["roof"] or gb["wall"]) else np.array([0.0])
        roofz = float(np.median(np.vstack(gb["roof"])[:, 2])) if gb["roof"] else float(allz.max())
        ground_z = float(allz.min())
        r = v3.get(b, {}); parea = abs(np.sum(ring[:-1, 0]*ring[1:, 1]-ring[1:, 0]*ring[:-1, 1]))/2 if len(ring) > 2 else 1.0
        fig, ax = plt.subplots(2, 2, figsize=(13, 10))
        nad, okmask = make_view_panels(ax[0, 0], ax[0, 1], b, cam, gb, ring, roofz, ground_z)
        used_nadir[b] = nad
        cloud_panel(ax[1, 0], dxy, dz, ring, "DIM(classified)", parea)
        cloud_panel(ax[1, 1], axy, az, ring, "ALS", parea)
        cap = (f"DEBY_LOD2_{b} [manual review - NO label]  roofType={gb['roofType']} card_view_nadir={nad:.0f}deg | "
               f"lowtex_v4={r.get('roof_lowtex_v4','?')}(v4-view roof in-frame={lowtex_reliab.get(b,'?')}) "
               f"sat={r.get('roof_sat_frac','?')} period={r.get('roof_periodicity','?')} "
               f"occl={r.get('occlusion_frac_approx','?')} recon={r.get('recon_score_median','?')} inc60={r.get('frac_views_incidence_le60','?')} "
               f"area={r.get('footprint_area_m2','?')}m2 rf_density={dimdens.get(b,'?')}")
        fig.suptitle(cap, fontsize=8.2); fig.tight_layout(rect=[0, 0, 1, 0.97])
        fig.savefig(CARDDIR/f"{b}.png", dpi=105); plt.close(fig)
        print(f"  card {b} nadir={nad:.0f}")

    # [2] QA: 5 most-oblique CARD-view among the 27 nonA + lowtex_v4 off-frame flags
    obl = sorted([b for b in nonA if b in used_nadir], key=lambda b: -used_nadir[b])[:5]
    offframe = sorted([b for b in nonA if lowtex_reliab.get(b, 1) < 0.5], key=lambda b: lowtex_reliab.get(b, 1))
    print(f"[2] QA oblique CARD-view 5: {[(b, round(used_nadir[b])) for b in obl]}")
    print(f"[2] lowtex_v4 UNRELIABLE (v3-bestview roof <50% in-frame): {[(b, lowtex_reliab[b]) for b in offframe]}")
    json.dump({"card_nadir": {b: round(used_nadir[b], 1) for b in used_nadir},
               "lowtex_v4_view_inframe": lowtex_reliab, "qa5_oblique": obl, "lowtex_v4_offframe": offframe},
              open(REPO/"results/tum_transfer/mob/overseg_lever/evidence_v2_meta.json", "w"))

    # [2b] QA visual: render the roof mask ON THE lowtex_v4 view (v3 bestview) for the off-frame buildings
    # -> shows the clipped/off-roof mask lowtex_v4 actually read (side-by-side with the good centered view).
    for b in offframe:
        gb = gml_building(b); ring = fp.get(b); bv = cam_by.get(bview.get(b)); cardcam, _ = select_card_view(gb["roof"], ring, cams, sr, params, W, H)
        if bv is None or cardcam is None: continue
        fig, ax = plt.subplots(1, 2, figsize=(12, 5.2))
        for k, (cam, tag) in enumerate([(bv, f"lowtex_v4 view (bestview) in-frame={lowtex_reliab[b]}"), (cardcam, "good centered view")]):
            rmask = roof_mask(gb["roof"], cam, params, sr, W, H); img = np.asarray(Image.open(IMAGE_DIR/cam.name).convert("RGB"))
            ys, xs = np.where(rmask)
            if len(xs) > 5:
                bb = [max(0, xs.min()-25), max(0, ys.min()-25), min(W, xs.max()+25), min(H, ys.max()+25)]
            else:  # roof entirely off-frame: show the frame edge region toward the roof centroid
                cc = clip_near(to_cam(np.array([[ring[:, 0].mean(), ring[:, 1].mean(), np.median(np.vstack(gb['roof'])[:, 2])]]), cam, sr))
                cp = distort(cc, params)[0] if len(cc) else np.array([W/2, 0])
                bb = [int(max(0, min(cp[0], W)-200)), 0, int(min(W, max(cp[0], 0)+200)), min(H, 400)]
            crop = img[bb[1]:bb[3], bb[0]:bb[2]]; ax[k].imshow(crop)
            sub = rmask[bb[1]:bb[3], bb[0]:bb[2]]
            if sub.any():
                ov = np.zeros((*crop.shape[:2], 4)); ov[sub] = [0.1, 1.0, 0.1, 0.45]; ax[k].imshow(ov)
            else:
                ax[k].text(0.5, 0.9, "roof projects OFF this crop/frame", transform=ax[k].transAxes, ha="center", color="red", fontsize=9)
            ax[k].set_title(tag, fontsize=8); ax[k].axis("off")
        fig.suptitle(f"DEBY_LOD2_{b} lowtex_v4 RELIABILITY: v4 read on clipped bestview vs good centered view (observe only)", fontsize=9)
        fig.tight_layout(rect=[0, 0, 1, 0.95]); fig.savefig(CARDDIR/f"qa_lowtexview_{b}.png", dpi=110); plt.close(fig)
        print(f"  qa_lowtexview {b}")

    # [3] time-diff: 2 views (min & max nadir among candidate views) + date table
    td_rows = []
    for b in TD_TARGETS:
        gb = gml_building(b); ring = fp.get(b)
        if not gb or ring is None: continue
        allz = np.vstack(gb["roof"] + gb["wall"])[:, 2] if (gb["roof"] or gb["wall"]) else np.array([0.0])
        roofz = float(np.median(np.vstack(gb["roof"])[:, 2])) if gb["roof"] else float(allz.max())
        ground_z = float(allz.min())
        fp3 = np.column_stack([ring[:, 0], ring[:, 1], np.full(len(ring), ground_z)])
        ctr3 = np.array([ring[:, 0].mean(), ring[:, 1].mean(), roofz])
        # GOOD views only: whole roof in front + in-frame + centered (clean overlay) -> pick 2 differing
        # in angle AND capture time, so both panels clearly show the building.
        allv = np.vstack(gb["roof"]); cx, cy = params[2], params[3]
        good = []
        for c in cams:
            cc = to_cam(allv, c, sr); front = cc[:, 2] > 1.0
            if front.mean() < 0.99: continue
            uv = distort(cc, params)
            if ((uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)).mean() < 0.95: continue
            rad = np.sqrt(((uv[:, 0]-cx)/(0.5*W))**2 + ((uv[:, 1]-cy)/(0.5*H))**2).max()
            if rad > 0.9: continue
            good.append((nadir_of(c, ctr3), c))
        if len(good) < 2:   # fallback: any view whose centroid is in-frame
            for c in cams:
                cc = clip_near(to_cam(ctr3[None], c, sr))
                if not len(cc): continue
                u = distort(cc, params)[0]
                if 0 <= u[0] < W and 0 <= u[1] < H: good.append((nadir_of(c, ctr3), c))
        if len(good) < 2: continue
        good.sort(key=lambda t: t[0])
        v_lo = good[0][1]                              # most overhead good view
        obl_pool = [g for g in good if g[1].name[11:17] != v_lo.name[11:17]] or good[1:]
        v_hi = max(obl_pool, key=lambda g: g[0])[1]    # most oblique among good, different time
        fig, ax = plt.subplots(1, 2, figsize=(13, 5.5))
        for k, (cam, tag) in enumerate([(v_lo, "near-nadir"), (v_hi, "oblique")]):
            gbc = gb
            cbb = context_bbox(ctr3, cam, params, sr, W, H, 28.0)
            cc = clip_near(to_cam(ctr3[None], cam, sr)); cpt = distort(cc, params)[0] if len(cc) else None
            img = np.asarray(Image.open(IMAGE_DIR/cam.name).convert("RGB"))
            rmask = roof_mask(gbc["roof"], cam, params, sr, W, H); fp_uv = proj_ring(fp3, cam, params, sr)
            if cbb:
                draw_overlay(ax[k], img[cbb[1]:cbb[3], cbb[0]:cbb[2]], cbb[0], cbb[1], fp_uv, rmask, cbb, cpt, b,
                             f"{tag} {cam.name[11:17]} nadir={nadir_of(cam,ctr3):.0f}deg")
            else:
                ax[k].text(0.5, 0.5, "no crop", ha="center"); ax[k].axis("off")
        fig.suptitle(f"DEBY_LOD2_{b} time-diff | created {gb['creationDate']} (imagery {IMAGERY_DATE}) grundriss {gb['grundriss']} roofType {gb['roofType']} - does it stand there? (observe only)", fontsize=8.5)
        fig.tight_layout(rect=[0, 0, 1, 0.95]); fig.savefig(CARDDIR/f"timediff_{b}.png", dpi=110); plt.close(fig)
        td_rows.append(dict(building_id=f"DEBY_LOD2_{b}", creationDate=gb["creationDate"], grundriss=gb["grundriss"],
                            roofType=gb["roofType"], post_imagery=int(gb["creationDate"] > IMAGERY_DATE if gb["creationDate"] else 0)))
        print(f"  timediff {b} created {gb['creationDate']}")
    json.dump(td_rows, open(REPO/"results/tum_transfer/mob/overseg_lever/evidence_v2_timediff.json", "w"), ensure_ascii=False)
    print(f"[done] cards -> {CARDDIR}")


if __name__ == "__main__":
    main()

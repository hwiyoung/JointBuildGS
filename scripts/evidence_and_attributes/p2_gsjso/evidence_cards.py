#!/usr/bin/env python3
"""population-lock-aux v4 [4] — evidence card (PNG) per UNCLASSIFIED building for manual review by 김휘영.
3 panels: (1) roof-view image crop with projected roof-polygon overlay, (2) DIM point cloud top-view clip,
(3) ALS point cloud top-view clip; numeric caption (lowtex_v4/sat/period/occl/recon/inc60/area/DIM-density).
NO label is attached (manual review). Observe only. Runs in jointbuildgs-p0-tools:t0 (PIL+laspy+matplotlib,
NO cv2 -> numpy projection copied). EPSG:25832 geo / 32632 OPF frame."""
import json, csv, glob, math
from pathlib import Path
import numpy as np
import laspy
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from projection_datum import base_to_canonical_points

ROOT = Path("/workspace/JointBuildGS/phases/p0-audit")
REPO = Path("/workspace/JointBuildGS")
DATA = ROOT / "data"
IMAGE_DIR = DATA / "work/images/Images"
GMLDIR = DATA / "raw/lod2"
GEOJSON = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
DIM_CLOUD = DATA / "work/w2/dim_v1_classified_z_minus0p174.laz"   # full-extent classified DIM (covers AOI-edge
# buildings; source of Roofer rf_pt_density). dim_aoi_crop.laz is clipped at x>=690792 -> edge buildings sparse.
ALS_TILES = sorted(glob.glob(str(DATA / "raw/als/*.la[sz]")))
CARDDIR = REPO / "docs/evidence/evidence_cards_v1"
import xml.etree.ElementTree as ET


# ---- numpy projection (copied; no cv2) ----
def qrot(q):
    w, x, y, z = q
    return np.array([[1-2*y*y-2*z*z, 2*x*y-2*w*z, 2*z*x+2*w*y],
                     [2*x*y+2*w*z, 1-2*x*x-2*z*z, 2*y*z-2*w*x],
                     [2*z*x-2*w*y, 2*y*z+2*w*x, 1-2*x*x-2*y*y]], float)

def b2c(p, sr, input_datum="orthometric", geoid_m=None):
    return base_to_canonical_points(p, sr, input_datum=input_datum, geoid_m=geoid_m)

class Cam:
    __slots__ = ("name", "tvec", "rot")
    def __init__(s, name, q, tv): s.name = name; s.tvec = tv; s.rot = qrot(q)

def parse_cam_model(path):
    for ln in open(path):
        p = ln.strip().split()
        if p and not ln.startswith("#") and len(p) > 4:
            return int(p[2]), int(p[3]), np.array([float(x) for x in p[4:]], float)

def parse_cameras(path):
    cams = []; expect = True
    for ln in open(path):
        s = ln.strip()
        if not s or s.startswith("#"): continue
        if not expect: expect = True; continue
        p = s.split()
        cams.append(Cam(" ".join(p[9:]), np.array([float(x) for x in p[1:5]], float),
                        np.array([float(x) for x in p[5:8]], float))); expect = False
    return cams

def project(points_base, cam, W, H, params, sr, input_datum="orthometric", geoid_m=None):
    pc = b2c(points_base, sr, input_datum=input_datum, geoid_m=geoid_m)
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

def _Lc(t): return t.rsplit("}", 1)[-1]
def gml_roof(bid):
    full = f"DEBY_LOD2_{bid}"
    for g in glob.glob(str(GMLDIR / "*.gml")):
        for _, el in ET.iterparse(g, events=("end",)):
            if _Lc(el.tag) != "Building": continue
            b = next((v for k, v in el.attrib.items() if _Lc(k) == "id"), None)
            if b != full: el.clear(); continue
            out = []
            for s in el.iter():
                if _Lc(s.tag) != "RoofSurface": continue
                for pl in s.iter():
                    if _Lc(pl.tag) == "posList" and pl.text:
                        out.append(np.array([float(x) for x in pl.text.split()]).reshape(-1, 3))
            el.clear(); return out
    return []


def clip(xy, z, bb):
    m = (xy[:, 0] >= bb[0]) & (xy[:, 0] <= bb[2]) & (xy[:, 1] >= bb[1]) & (xy[:, 1] <= bb[3])
    return xy[m], z[m]


def main():
    sr = json.load(open(DATA/"work/opf/opf/scene_reference_frame.json"))["base_to_canonical"]
    W, H, params = parse_cam_model(DATA/"work/colmap/sparse/0/cameras.txt")
    cams = {c.name: c for c in parse_cameras(DATA/"work/colmap/sparse/0/images.txt")}
    bview = {k.replace("DEBY_LOD2_", ""): v for k, v in json.load(open(REPO/"results/tum_transfer/mob/overseg_lever/population_aux_v3_bestview.json")).items()}
    v3 = {r["building_id"].replace("DEBY_LOD2_", ""): r for r in csv.DictReader(open(REPO/"docs/archive/population_aux/v3/tables/population_aux_v3.csv"))}
    canon = glob.glob(str(REPO/"phases/p0-audit/runs/w2_1_roofer_default_*/building_reconstruction_status.csv"))[0]
    dimdens = {}
    for r in csv.DictReader(open(canon)):
        if r["input"].lower() == "dim": dimdens[r["building_id"].replace("DEBY_LOD2_", "")] = r.get("rf_pt_density", "")
    fp = {}
    for f in json.load(open(GEOJSON))["features"]:
        b = f["properties"]["building_id"].replace("DEBY_LOD2_", "")
        g = f["geometry"]; ring = np.array(g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len), float)
        if b not in fp or len(ring) > len(fp[b]): fp[b] = ring
    # unclassified list from crosswalk
    uncls = [r["building_id"].replace("DEBY_LOD2_", "") for r in csv.DictReader(open(REPO/"docs/archive/bucket_crosswalk/v1/tables/bucket_crosswalk.csv")) if r["new_class"] == "미분류"]
    print(f"unclassified: {len(uncls)} -> {uncls}")
    # AOI bbox from unclassified footprints
    allr = np.vstack([fp[b] for b in uncls if b in fp])
    aoi = [allr[:, 0].min()-5, allr[:, 1].min()-5, allr[:, 0].max()+5, allr[:, 1].max()+5]
    # preload DIM (AOI crop) xy,z
    d = laspy.read(str(DIM_CLOUD))
    dxy = np.column_stack([np.asarray(d.x), np.asarray(d.y)]).astype(np.float32); dz = np.asarray(d.z, np.float32)
    dxy, dz = clip(dxy, dz, aoi)
    print(f"DIM AOI-unc clip: {len(dxy)} pts")
    # preload ALS (tiles overlapping AOI) xy,z
    axy_l, az_l = [], []
    for t in ALS_TILES:
        with laspy.open(t) as fh:
            h = fh.header
            if h.x_max < aoi[0] or h.x_min > aoi[2] or h.y_max < aoi[1] or h.y_min > aoi[3]: continue
        a = laspy.read(t)
        xy = np.column_stack([np.asarray(a.x), np.asarray(a.y)]).astype(np.float32); z = np.asarray(a.z, np.float32)
        xy, z = clip(xy, z, aoi)
        if len(xy): axy_l.append(xy); az_l.append(z)
    axy = np.vstack(axy_l) if axy_l else np.zeros((0, 2), np.float32)
    az = np.concatenate(az_l) if az_l else np.zeros(0, np.float32)
    print(f"ALS AOI-unc clip: {len(axy)} pts")
    CARDDIR.mkdir(parents=True, exist_ok=True)
    for b in uncls:
        r = v3.get(b, {}); ring = fp.get(b)
        if ring is None: print(f"  {b} no footprint"); continue
        bb = [ring[:, 0].min()-2, ring[:, 1].min()-2, ring[:, 0].max()+2, ring[:, 1].max()+2]
        fig, ax = plt.subplots(1, 3, figsize=(15, 5.2))
        # panel 1: roof view crop + mask
        vn = bview.get(b); done1 = False
        if vn and vn in cams and (IMAGE_DIR/vn).exists():
            roof = gml_roof(b)
            if roof:
                polys, xs, ys = [], [], []
                for rr in roof:
                    uv, fr = project(np.asarray(rr, float), cams[vn], W, H, params, sr)
                    if fr.sum() >= 3: polys.append(uv[fr]); xs += uv[fr, 0].tolist(); ys += uv[fr, 1].tolist()
                if polys:
                    x0 = max(0, int(min(xs))-30); y0 = max(0, int(min(ys))-30)
                    x1 = min(W, int(max(xs))+30); y1 = min(H, int(max(ys))+30)
                    img = np.asarray(Image.open(IMAGE_DIR/vn).convert("RGB"))[y0:y1, x0:x1]
                    ax[0].imshow(img)
                    for p in polys:
                        pc = np.vstack([p, p[:1]]) - [x0, y0]
                        ax[0].plot(pc[:, 0], pc[:, 1], "-", c="lime", lw=1.5)
                    ax[0].set_title(f"roof view {vn[:20]}", fontsize=8); ax[0].axis("off"); done1 = True
        if not done1: ax[0].text(0.5, 0.5, "no roof view", ha="center"); ax[0].axis("off")
        # panel 2/3: DIM / ALS top-view ; in-footprint density (from SHOWN cloud, matches panel)
        parea = abs(np.sum(ring[:-1, 0]*ring[1:, 1] - ring[1:, 0]*ring[:-1, 1]))/2 if len(ring) > 2 else 1.0
        infp = {}
        for k, (xy, z, name) in enumerate([(dxy, dz, "DIM(classified)"), (axy, az, "ALS")]):
            cxy, cz = clip(xy, z, bb)
            npoly = int(MPath(ring[:, :2]).contains_points(cxy).sum()) if len(cxy) else 0
            infp[name] = npoly/parea if parea > 0 else 0.0
            axk = ax[k+1]
            if len(cxy):
                sc = axk.scatter(cxy[:, 0], cxy[:, 1], c=cz, s=3, cmap="viridis")
                plt.colorbar(sc, ax=axk, fraction=0.046, label="Z (m)")
            axk.plot(np.append(ring[:, 0], ring[0, 0]), np.append(ring[:, 1], ring[0, 1]), "r-", lw=1.2)
            axk.set_aspect("equal"); axk.set_title(f"{name} top-view  bbox_n={len(cxy)} in-fp={npoly} ({infp[name]:.1f}/m2)", fontsize=8.5)
            axk.set_xlabel("E"); axk.set_ylabel("N")
        cap = (f"DEBY_LOD2_{b}  [UNCLASSIFIED — manual review]   "
               f"lowtex_v4={r.get('roof_lowtex_v4','?')} sat={r.get('roof_sat_frac','?')} period={r.get('roof_periodicity','?')} "
               f"occl={r.get('occlusion_frac_approx','?')} recon={r.get('recon_score_median','?')} "
               f"inc60={r.get('frac_views_incidence_le60','?')} area={r.get('footprint_area_m2','?')}m2 | "
               f"DIM in-fp={infp['DIM(classified)']:.1f}/m2 ALS in-fp={infp['ALS']:.1f}/m2 (rf_pt_density[Roofer raw clip]={dimdens.get(b,'?')})")
        fig.suptitle(cap, fontsize=8.5)
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        fig.savefig(CARDDIR/f"{b}.png", dpi=110); plt.close(fig)
        print(f"  card {b}")
    print(f"[done] {len(uncls)} cards -> {CARDDIR}")


if __name__ == "__main__":
    main()

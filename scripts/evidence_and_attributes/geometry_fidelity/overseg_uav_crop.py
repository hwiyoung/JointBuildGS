#!/usr/bin/env python3
"""P2 overseg-faithfulness — qualitative: crop the nearest near-nadir UAV image over a building so the
roof's real step structure can be eyeballed. Reuses the OPF photogrammetry bundle (calibrated cameras).
OPF-local = UTM(EPSG:32632≈25832) - [690953,5336071,604] (same shift as GS-local). NO reconstruction.
Observation only. Approximate projection (near-nadir pinhole + kappa in-plane rotation); crop is generous.
Out: docs/figs/W_faithful/<bid>_uav.png
"""
import json, sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path("/workspace/JointBuildGS")
OPF = REPO / "phases/p0-audit/data/work/opf/opf"
IMG = REPO / "phases/p0-audit/data/work/images/Images"
GEO = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
FIG = REPO / "docs/figs/W_faithful"
SHIFT = np.array([690953.0, 5336071.0, 604.0])
BLD = ["4906969", "42364659"]


def fp_centroid(bid):
    full = f"DEBY_LOD2_{bid}"
    for ft in json.loads(GEO.read_text())["features"]:
        if ft["properties"].get("building_id") != full:
            continue
        g = ft["geometry"]
        poly = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
        P = np.asarray(poly)[:, :2]
        return P.mean(0), P
    return None, None


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    cams = json.load(open(OPF / "calibrated_cameras.json"))
    sens = {s["id"]: s for s in cams["sensors"]}
    uri = {c["id"]: c["uri"] for c in json.load(open(OPF / "camera_list.json"))["cameras"]}
    cam = cams["cameras"]
    for bid in BLD:
        cxy, poly = fp_centroid(bid)
        if cxy is None:
            print(f"{bid}: no footprint"); continue
        b_local = np.array([cxy[0], cxy[1], 0.0]) - SHIFT  # building xy in OPF-local (z approx)
        # near-nadir cameras = small omega/phi (first two orientation_deg); nearest in XY to building
        best = None
        for c in cam:
            o = c["orientation_deg"]
            if abs(o[0]) > 10 or abs(o[1]) > 10:
                continue
            p = np.array(c["position"])
            d = np.hypot(p[0] - b_local[0], p[1] - b_local[1])
            if best is None or d < best[0]:
                best = (d, c)
        if best is None:
            print(f"{bid}: no near-nadir cam"); continue
        d, c = best
        s = sens[c["sensor_id"]]["internals"]
        f = s["focal_length_px"]; pp = s["principal_point_px"]
        p = np.array(c["position"]); kappa = np.radians(c["orientation_deg"][2])
        # approx near-nadir pinhole: image offset = f/(cam_z - roof_z) * R(-kappa)·(building_xy - cam_xy)
        roof_local_z = -30.0  # roof ellip ~574 - 604
        sc = f / max(5.0, (p[2] - roof_local_z))
        dxy = b_local[:2] - p[:2]
        R = np.array([[np.cos(-kappa), -np.sin(-kappa)], [np.sin(-kappa), np.cos(-kappa)]])
        off = sc * (R @ dxy)
        px, py = pp[0] + off[0], pp[1] - off[1]   # image y down
        img_path = IMG / Path(uri[c["id"]]).name
        if not img_path.exists():
            print(f"{bid}: image missing {img_path.name}"); continue
        im = plt.imread(img_path)
        H, W = im.shape[:2]
        half = 900
        x0, x1 = int(np.clip(px - half, 0, W)), int(np.clip(px + half, 0, W))
        y0, y1 = int(np.clip(py - half, 0, H)), int(np.clip(py + half, 0, H))
        crop = im[y0:y1, x0:x1]
        fig, ax = plt.subplots(figsize=(6, 6)); ax.imshow(crop); ax.set_axis_off()
        ax.set_title(f"{bid} near-nadir UAV {img_path.name}\n(cam {d:.0f}m from bldg in XY; building near center, approx)", fontsize=8)
        fp = FIG / f"{bid}_uav.png"; fig.savefig(fp, dpi=110, bbox_inches="tight"); plt.close(fig)
        print(f"{bid}: cam {img_path.name} dist {d:.1f}m  proj px=({px:.0f},{py:.0f}) of {W}x{H} -> {fp.name}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Render read-only 20k E3-control versus E4 qualitative comparisons."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import laspy
import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.colors import Normalize
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from PIL import Image, ImageOps, ImageDraw
import torch
from shapely import contains_xy
from shapely.geometry import shape

from src.visualization.fixed_view_qualitative import load_cityjsonseq


ROOT = Path(
    "/artifacts/JointBuildGS/phase-payloads/p2/e4_local_4906982_55v_als_prior_v1/"
    "P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1"
)
MVS_NPY = Path(
    "/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_mvs_transfer_diag_v1/"
    "P2-E3-LOCAL-4906982-MVS-TRANSFER-DIAG-v1/fused_seed/mvs_xyz_f32.npy"
)
OUTPUT = ROOT / "representative_images/final_comparison"
SHIFT = np.asarray([690953.0, 5336071.0, 604.0], dtype=np.float64)
ARMS = ("FUSED_VIS_CONF", "E4_ALS_PRIOR_ONLY")
LABELS = {"FUSED_VIS_CONF": "55-view MVS-depth control", "E4_ALS_PRIOR_ONLY": "55-view E4 + Existing ALS"}
COLORS = {"FUSED_VIS_CONF": "#2563eb", "E4_ALS_PRIOR_ONLY": "#f97316"}
SEED = 4906982


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sample(points: np.ndarray, maximum: int, offset: int) -> np.ndarray:
    if len(points) <= maximum:
        return points
    rng = np.random.default_rng(SEED + offset)
    return points[np.sort(rng.choice(len(points), maximum, replace=False))]


def footprint_geometry():
    feature = json.loads((ROOT / "control/shared_standard_footprint_4906982.geojson").read_text())["features"][0]
    return shape(feature["geometry"])


def checkpoint_geometry(arm: str) -> tuple[np.ndarray, np.ndarray]:
    payload = torch.load(ROOT / f"arms/{arm}/R1/ckpt/step_020000.pt", map_location="cpu", weights_only=False)
    state = payload["model"]["state_dict"]
    xyz = state["means"].detach().cpu().numpy().astype(np.float64) + SHIFT
    opacity = torch.sigmoid(state["opacities_raw"].detach().cpu()).numpy().reshape(-1)
    return xyz, opacity


def cloud(arm: str, name: str) -> tuple[np.ndarray, np.ndarray | None]:
    data = laspy.read(ROOT / f"arms/{arm}/R1/evaluation/step_020000/fusion/{name}")
    xyz = np.column_stack((np.asarray(data.x), np.asarray(data.y), np.asarray(data.z))).astype(np.float64)
    cls = np.asarray(data.classification, dtype=np.uint8) if "classification" in data.point_format.dimension_names else None
    return xyz, cls


def ordinary_surface_panel(footprint, mvs: np.ndarray, fused: dict[str, np.ndarray]) -> Path:
    cx, cy = footprint.centroid.x, footprint.centroid.y
    inside = {arm: xyz[contains_xy(footprint, xyz[:, 0], xyz[:, 1])] for arm, xyz in fused.items()}
    datasets = (("Filtered OpenMVS reference", mvs),) + tuple((LABELS[arm], inside[arm]) for arm in ARMS)
    zvalues = np.concatenate([values[:, 2] for _, values in datasets])
    zlo, zhi = np.quantile(zvalues, [0.01, 0.99])
    minx, miny, maxx, maxy = footprint.bounds
    boundary = np.asarray(footprint.exterior.coords)
    fig = plt.figure(figsize=(15, 10), dpi=150, constrained_layout=True)
    for column, (label, values) in enumerate(datasets):
        points = sample(values, 28000, column).copy()
        points[:, 0] -= cx; points[:, 1] -= cy
        for row, (elev, azim, view) in enumerate(((30, -60, "oblique"), (89.9, -90, "top"))):
            axis = fig.add_subplot(2, 3, row * 3 + column + 1, projection="3d", proj_type="ortho")
            axis.scatter(points[:, 0], points[:, 1], points[:, 2], c=points[:, 2], cmap="viridis", vmin=zlo, vmax=zhi, s=.35, alpha=.8, rasterized=True)
            axis.plot(boundary[:, 0]-cx, boundary[:, 1]-cy, np.full(len(boundary), zlo), color="black", linewidth=1)
            axis.set_xlim(minx-cx-3, maxx-cx+3); axis.set_ylim(miny-cy-3, maxy-cy+3); axis.set_zlim(zlo, zhi)
            axis.view_init(elev=elev, azim=azim)
            axis.set_title(f"{label}\n{view} · n={len(values):,}", fontsize=9)
            axis.set_xlabel("E offset (m)"); axis.set_ylabel("N offset (m)"); axis.set_zlabel("Z (m)")
            axis.tick_params(labelsize=7)
    fig.suptitle("DEBY_LOD2_4906982 · fused surface before SMRF · 20k", fontsize=13)
    path = OUTPUT / "ordinary_surface_3d_20k.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def high_z_panel(footprint, gaussian: dict[str, tuple[np.ndarray, np.ndarray]]) -> Path:
    cx, cy = footprint.centroid.x, footprint.centroid.y
    high = {}
    for index, arm in enumerate(ARMS):
        xyz, opacity = gaussian[arm]
        mask = xyz[:, 2] > 650.0
        high[arm] = sample(np.column_stack((xyz[mask], opacity[mask])), 6000, 100 + index)
    combined = np.concatenate([high[arm][:, :3] for arm in ARMS])
    xlim = np.quantile((combined[:, 0] - cx) / 1000.0, [0, 1])
    ylim = np.quantile((combined[:, 1] - cy) / 1000.0, [0, 1])
    zlim = (650.0, float(combined[:, 2].max()))
    norm = Normalize(0, 1)
    fig = plt.figure(figsize=(15, 9), dpi=150, constrained_layout=True)
    for column, arm in enumerate(ARMS):
        points = high[arm]
        x = (points[:, 0]-cx)/1000.0; y = (points[:, 1]-cy)/1000.0
        axis = fig.add_subplot(2, 2, column + 1, projection="3d")
        scatter = axis.scatter(x, y, points[:, 2], c=points[:, 3], cmap="plasma", norm=norm, s=5, alpha=.72, rasterized=True)
        axis.scatter([0], [0], [650], marker="s", s=45, facecolors="none", edgecolors="black")
        axis.set_xlim(*xlim); axis.set_ylim(*ylim); axis.set_zlim(*zlim); axis.view_init(elev=24, azim=-57)
        axis.set_title(f"{LABELS[arm]}\nZ>650: {len(points):,} (all outside footprint)")
        axis.set_xlabel("E offset (km)"); axis.set_ylabel("N offset (km)"); axis.set_zlabel("Z (m)")
        fig.colorbar(scatter, ax=axis, fraction=.025, pad=.02, label="opacity")
        side = fig.add_subplot(2, 2, column + 3)
        side.scatter(x, points[:, 2], c=points[:, 3], cmap="plasma", norm=norm, s=5, alpha=.72, rasterized=True)
        side.axvline(0, color="black", linewidth=1); side.axhline(650, color="black", linewidth=1)
        side.set_xlim(*xlim); side.set_ylim(*zlim); side.grid(True, alpha=.25)
        side.set_xlabel("E offset (km)"); side.set_ylabel("Z (m)")
    fig.suptitle("DEBY_LOD2_4906982 · global high-Z Gaussian tail · 20k", fontsize=13)
    path = OUTPUT / "high_z_tail_3d_20k.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def roofer_panel(footprint) -> Path:
    rows = {}
    for arm in ARMS:
        base = ROOT / f"arms/{arm}/R1/evaluation/step_020000/fusion"
        xyz, cls = cloud(arm, "classified_surface.laz")
        inside = contains_xy(footprint, xyz[:, 0], xyz[:, 1])
        class2 = xyz[inside & (cls == 2)]
        class6 = xyz[inside & (cls == 6)]
        city = next((base / "roofer/output").glob("*.city.jsonl"))
        surfaces = load_cityjsonseq(city)
        terminal = json.loads((base / "roofer/roofer_terminal.json").read_text())["target_attributes"]
        rows[arm] = (class2, class6, surfaces, terminal)
    zvalues = []
    for _, class6, surfaces, _ in rows.values():
        zvalues.extend(class6[:, 2].tolist())
        zvalues.extend(v for surface in surfaces for v in surface.xyz[:, 2])
    zlo, zhi = np.quantile(zvalues, [.01, .99]); zlo -= 1.5; zhi += 1.5
    minx, miny, maxx, maxy = footprint.bounds; pad = 3
    boundary = np.asarray(footprint.exterior.coords)
    fig = plt.figure(figsize=(15, 10), dpi=150, constrained_layout=True)
    for column, arm in enumerate(ARMS):
        class2, class6, surfaces, terminal = rows[arm]
        axis = fig.add_subplot(2, 2, column + 1)
        p2 = sample(class2, 16000, 300 + column); p6 = sample(class6, 16000, 310 + column)
        axis.scatter(p2[:,0], p2[:,1], s=.4, color="#d9a441", alpha=.22, linewidths=0, label=f"class 2={len(class2):,}")
        axis.scatter(p6[:,0], p6[:,1], s=.6, color="#595959", alpha=.45, linewidths=0, label=f"class 6={len(class6):,}")
        for surface in surfaces:
            if surface.semantic == "RoofSurface":
                xy=np.asarray(surface.xyz)[:,:2]
                axis.fill(xy[:,0],xy[:,1],facecolor=COLORS[arm],edgecolor="black",alpha=.55,linewidth=.6)
        axis.plot(boundary[:,0],boundary[:,1],color="black",linewidth=1.2)
        axis.set_xlim(minx-pad,maxx+pad);axis.set_ylim(miny-pad,maxy+pad);axis.set_aspect("equal");axis.set_axis_off();axis.legend(markerscale=6,loc="lower left",fontsize=8)
        axis.set_title(f"{LABELS[arm]} · classified evidence + Roofer roof\nplanes={terminal['rf_roof_planes']} · internal RMSE={terminal['rf_rmse_lod22']:.2f} m")
        axis = fig.add_subplot(2, 2, column + 3, projection="3d", proj_type="ortho")
        p6 = sample(class6, 12000, 320 + column)
        axis.scatter(p6[:,0],p6[:,1],p6[:,2],s=.45,color="#737373",alpha=.18,depthshade=False)
        semantic_colors={"RoofSurface":COLORS[arm],"WallSurface":"#a3a3a3","GroundSurface":"#d4d4d4"}
        for surface in surfaces:
            xyz=np.asarray(surface.xyz)
            if len(xyz)>=3:
                axis.add_collection3d(Poly3DCollection([xyz],facecolor=semantic_colors.get(surface.semantic,"#d4d4d4"),edgecolor="#262626",linewidth=.35,alpha=.72))
        axis.set_xlim(minx-pad,maxx+pad);axis.set_ylim(miny-pad,maxy+pad);axis.set_zlim(zlo,zhi)
        axis.set_box_aspect((maxx-minx+2*pad,maxy-miny+2*pad,zhi-zlo));axis.view_init(elev=29,azim=-55)
        axis.set_title(f"{LABELS[arm]} · actual Roofer CityJSONSeq")
        axis.set_xlabel("E");axis.set_ylabel("N");axis.set_zlabel("Z")
    fig.suptitle("DEBY_LOD2_4906982 · SMRF output evidence and Roofer geometry · 20k", fontsize=13)
    path=OUTPUT/"classified_and_roofer_20k.png";fig.savefig(path);plt.close(fig);return path


def heldout_montage() -> Path:
    names=("DJI_20241217090827_0016_D.png","DJI_20241217095139_0076_D.png","DJI_20241217101359_0032_D.png")
    images=[]
    for name in names:
        path=ROOT/"representative_images/paired"/f"step_020000__{name}"
        image=Image.open(path).convert("RGB")
        image.thumbnail((2400, 420), Image.Resampling.LANCZOS)
        labelled=ImageOps.expand(image,border=(0,28,0,0),fill="white")
        ImageDraw.Draw(labelled).text((8,6),name.removesuffix(".png"),fill="black")
        images.append(labelled)
    canvas=Image.new("RGB",(max(i.width for i in images),sum(i.height for i in images)),"white")
    y=0
    for image in images:
        canvas.paste(image,(0,y));y+=image.height
    path=OUTPUT/"heldout_views_20k.png";canvas.save(path,optimize=True);return path


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    footprint=footprint_geometry()
    mvs=np.load(MVS_NPY).astype(np.float64)+SHIFT
    mvs=mvs[contains_xy(footprint,mvs[:,0],mvs[:,1])]
    fused={arm:cloud(arm,"fused_surface.laz")[0] for arm in ARMS}
    gaussian={arm:checkpoint_geometry(arm) for arm in ARMS}
    outputs=[ordinary_surface_panel(footprint,mvs,fused),high_z_panel(footprint,gaussian),roofer_panel(footprint),heldout_montage()]
    receipt={
        "schema":"jointbuildgs.p2.e4_local_4906982_55v_als_prior_v1.qualitative.v1",
        "status":"COMPLETE","training_reruns":0,"fusion_reruns":0,"roofer_reruns":0,
        "lod2_geometry_used":False,"scientific_verdict":None,
        "inputs":{"mvs_reference_sha256":sha256(MVS_NPY),"arm_count":2,"step":20000},
        "outputs":{path.name:sha256(path) for path in outputs},
    }
    (OUTPUT/"receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print(json.dumps(receipt,indent=2,sort_keys=True))


if __name__ == "__main__":
    main()

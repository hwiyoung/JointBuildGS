#!/usr/bin/env python3
"""Render evaluation-only 3D geometry comparisons for the completed 20k arms."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import laspy
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.colors import Normalize
import numpy as np
import torch
from shapely import contains_xy
from shapely.geometry import shape


ROOT = Path("/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_mvs_surface_depth_v1/P2-E3-LOCAL-4906982-MVS-SURFACE-DEPTH-v1")
MVS_NPY = Path("/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_mvs_transfer_diag_v1/P2-E3-LOCAL-4906982-MVS-TRANSFER-DIAG-v1/fused_seed/mvs_xyz_f32.npy")
OUTPUT = ROOT / "representative_images/geometry_3d"
SHIFT = np.asarray([690953.0, 5336071.0, 604.0], dtype=np.float64)
ARMS = ("RAW_DEPTH", "MVS_SURFACE_METRIC")
LABELS = {"RAW_DEPTH": "RAW COLMAP depth", "MVS_SURFACE_METRIC": "OpenMVS surface metric depth"}
SEED = 4906982
REPO = Path("/workspace")


def sample(points: np.ndarray, maximum: int, seed_offset: int = 0) -> np.ndarray:
    if len(points) <= maximum:
        return points
    rng = np.random.default_rng(SEED + seed_offset)
    return points[np.sort(rng.choice(len(points), maximum, replace=False))]


def checkpoint_geometry(arm: str) -> tuple[np.ndarray, np.ndarray]:
    payload = torch.load(
        ROOT / f"arms/{arm}/R1/ckpt/step_020000.pt",
        map_location="cpu",
        weights_only=False,
    )
    state = payload["model"]["state_dict"]
    xyz = state["means"].detach().cpu().numpy().astype(np.float64) + SHIFT
    opacity = torch.sigmoid(state["opacities_raw"].detach().cpu()).numpy().reshape(-1)
    return xyz, opacity


def fused_points(arm: str) -> np.ndarray:
    cloud = laspy.read(ROOT / f"arms/{arm}/R1/evaluation/step_020000/fusion/fused_surface.laz")
    return np.column_stack([cloud.x, cloud.y, cloud.z]).astype(np.float64)


def footprint_geometry():
    body = json.loads((ROOT / "control/shared_standard_footprint_4906982.geojson").read_text())
    return shape(body["features"][0]["geometry"])


def style_3d(axis) -> None:
    axis.grid(True, alpha=0.25)
    axis.set_xlabel("Easting offset (m)")
    axis.set_ylabel("Northing offset (m)")
    axis.set_zlabel("Z EPSG:25832 (m)")
    axis.tick_params(labelsize=8)


def surface_figure(footprint, mvs: np.ndarray, fused: dict[str, np.ndarray]) -> None:
    cx, cy = footprint.centroid.x, footprint.centroid.y
    inside = {arm: points[contains_xy(footprint, points[:, 0], points[:, 1])] for arm, points in fused.items()}
    datasets = [mvs, inside[ARMS[0]], inside[ARMS[1]]]
    names = ["Filtered OpenMVS reference", LABELS[ARMS[0]], LABELS[ARMS[1]]]
    colors = ["viridis", "viridis", "viridis"]
    all_z = np.concatenate([points[:, 2] for points in datasets])
    z0, z1 = np.quantile(all_z, [0.01, 0.99])
    minx, miny, maxx, maxy = footprint.bounds
    pad = 3.0
    fig = plt.figure(figsize=(15, 10), dpi=150, constrained_layout=True)
    for column, (points, name, cmap) in enumerate(zip(datasets, names, colors)):
        plotted = sample(points, 28000, column)
        rel = plotted.copy(); rel[:, 0] -= cx; rel[:, 1] -= cy
        for row, (elev, azim, view_name) in enumerate(((30, -60, "oblique"), (89.9, -90, "top"))):
            axis = fig.add_subplot(2, 3, row * 3 + column + 1, projection="3d")
            axis.scatter(rel[:, 0], rel[:, 1], rel[:, 2], c=rel[:, 2], cmap=cmap, vmin=z0, vmax=z1, s=0.35, alpha=0.8, rasterized=True)
            boundary = np.asarray(footprint.exterior.coords)
            axis.plot(boundary[:, 0] - cx, boundary[:, 1] - cy, np.full(len(boundary), z0), color="black", linewidth=1.2)
            axis.set_xlim(minx - cx - pad, maxx - cx + pad)
            axis.set_ylim(miny - cy - pad, maxy - cy + pad)
            axis.set_zlim(z0, z1)
            axis.view_init(elev=elev, azim=azim)
            axis.set_title(f"{name}\n{view_name} · n={len(points):,}", fontsize=10)
            style_3d(axis)
    fig.suptitle("DEBY_LOD2_4906982 · ordinary fused surface inside the shared footprint · 20k", fontsize=13)
    fig.savefig(OUTPUT / "ordinary_surface_3d.png")
    plt.close(fig)


def tail_figure(footprint, gaussian: dict[str, tuple[np.ndarray, np.ndarray]]) -> None:
    cx, cy = footprint.centroid.x, footprint.centroid.y
    high = {}
    for arm, (xyz, opacity) in gaussian.items():
        mask = xyz[:, 2] > 650.0
        points = np.column_stack([xyz[mask], opacity[mask]])
        high[arm] = sample(points, 6000, 100 + ARMS.index(arm))
    combined = np.concatenate([high[arm][:, :3] for arm in ARMS])
    xlim = np.quantile((combined[:, 0] - cx) / 1000.0, [0.0, 1.0])
    ylim = np.quantile((combined[:, 1] - cy) / 1000.0, [0.0, 1.0])
    zlim = (650.0, float(combined[:, 2].max()))
    norm = Normalize(0.0, 1.0)
    fig = plt.figure(figsize=(15, 10), dpi=150, constrained_layout=True)
    for column, arm in enumerate(ARMS):
        points = high[arm]
        x = (points[:, 0] - cx) / 1000.0; y = (points[:, 1] - cy) / 1000.0
        axis = fig.add_subplot(2, 2, column + 1, projection="3d")
        scatter = axis.scatter(x, y, points[:, 2], c=points[:, 3], norm=norm, cmap="plasma", s=4, alpha=0.72, rasterized=True)
        axis.scatter([0], [0], [650], marker="s", s=45, facecolors="none", edgecolors="black", linewidths=1.5, label="footprint centroid")
        axis.set_xlim(*xlim); axis.set_ylim(*ylim); axis.set_zlim(*zlim)
        axis.set_xlabel("Easting offset (km)"); axis.set_ylabel("Northing offset (km)"); axis.set_zlabel("Z (m)")
        axis.view_init(elev=24, azim=-57)
        axis.set_title(f"{LABELS[arm]}\nZ>650: {int((gaussian[arm][0][:,2] > 650).sum()):,}")
        axis.legend(loc="upper right", fontsize=8)
        fig.colorbar(scatter, ax=axis, fraction=0.025, pad=0.02, label="opacity")
        side = fig.add_subplot(2, 2, column + 3)
        side.scatter(x, points[:, 2], c=points[:, 3], norm=norm, cmap="plasma", s=4, alpha=0.65, rasterized=True)
        side.axvline(0, color="black", linewidth=1, label="footprint centroid")
        side.axhline(650, color="black", linewidth=1)
        side.set_xlim(*xlim); side.set_ylim(*zlim)
        side.set_xlabel("Easting offset from footprint (km)"); side.set_ylabel("Z EPSG:25832 (m)")
        side.set_title("side projection")
        side.grid(True, alpha=0.25)
    fig.suptitle("DEBY_LOD2_4906982 · global high-Z Gaussian tail · 20k", fontsize=13)
    fig.savefig(OUTPUT / "high_z_tail_3d.png")
    plt.close(fig)


def interactive_payload(footprint, mvs: np.ndarray, fused: dict[str, np.ndarray], gaussian: dict[str, tuple[np.ndarray, np.ndarray]]) -> None:
    cx, cy = footprint.centroid.x, footprint.centroid.y
    boundary = np.asarray(footprint.exterior.coords, dtype=np.float64)

    def rows(points: np.ndarray, maximum: int, offset: int, opacity: np.ndarray | None = None) -> dict[str, list[float]]:
        if opacity is not None:
            values = np.column_stack([points, opacity])
            chosen = sample(values, maximum, offset)
            points = chosen[:, :3]; opacity = chosen[:, 3]
        else:
            points = sample(points, maximum, offset)
        result = {
            "x": np.round(points[:, 0] - cx, 3).tolist(),
            "y": np.round(points[:, 1] - cy, 3).tolist(),
            "z": np.round(points[:, 2], 3).tolist(),
        }
        if opacity is not None:
            result["opacity"] = np.round(opacity, 4).tolist()
        return result

    inside = {arm: points[contains_xy(footprint, points[:, 0], points[:, 1])] for arm, points in fused.items()}
    high = {}
    for arm, (xyz, opacity) in gaussian.items():
        mask = xyz[:, 2] > 650.0
        high[arm] = rows(xyz[mask], 2500, 300 + ARMS.index(arm), opacity[mask])
    body = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_surface_depth_v1.geometry_3d.v1",
        "origin_epsg25832": [cx, cy, 0.0],
        "footprint": {"x": np.round(boundary[:, 0] - cx, 3).tolist(), "y": np.round(boundary[:, 1] - cy, 3).tolist()},
        "ordinary": {
            "mvs": rows(mvs, 1800, 200),
            ARMS[0]: rows(inside[ARMS[0]], 2400, 201),
            ARMS[1]: rows(inside[ARMS[1]], 2400, 202),
        },
        "high_z": high,
        "counts": {
            arm: {
                "gaussian_total": int(len(gaussian[arm][0])),
                "z_gt_650": int((gaussian[arm][0][:, 2] > 650.0).sum()),
                "z_gt_650_opacity_ge_0p9": int(((gaussian[arm][0][:, 2] > 650.0) & (gaussian[arm][1] >= 0.9)).sum()),
                "fused_inside_footprint": int(len(inside[arm])),
            }
            for arm in ARMS
        },
        "scientific_verdict": None,
    }
    (OUTPUT / "geometry_3d_samples.json").write_text(json.dumps(body, separators=(",", ":")) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def update_task_records() -> None:
    marker = "## 3D qualitative audit"
    notes = ROOT / "NOTES.md"
    notes_text = notes.read_text()
    if marker not in notes_text:
        notes_text += (
            "\n## 3D qualitative audit\n\n"
            "- Ordinary fused surfaces inside the shared footprint and global Z>650 Gaussian tails were rendered separately.\n"
            "- The 3D audit used checkpoints, fused surfaces, the filtered OpenMVS reference, and the shared XY footprint only; LoD2 geometry was not used.\n"
            "- Scientific verdict: `null`.\n"
        )
        notes.write_text(notes_text)

    comparison = ROOT / "comparison.md"
    comparison_text = comparison.read_text()
    if marker not in comparison_text:
        comparison_text += (
            "\n## 3D qualitative audit\n\n"
            "- The ordinary-surface panel is restricted to the shared footprint; the high-Z panel is global.\n"
            "- Both arms retain broadly similar central roof sheets, while the MVS-surface-depth arm has more scattered edge points and does not reproduce the full OpenMVS wall volume.\n"
            "- All Z>650 Gaussians are outside the footprint. The MVS-surface-depth arm forms a much denser, spatially remote tail, so its improved ordinary-surface median and worsened high-Z count are spatially compatible.\n"
            "- Static panels: `representative_images/geometry_3d/ordinary_surface_3d.png` and `representative_images/geometry_3d/high_z_tail_3d.png`.\n"
        )
        comparison.write_text(comparison_text)

    provenance_path = ROOT / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    source_hashes = provenance.setdefault("source_config_sha256", {})
    for rel in (
        "scripts/p2/e3_local_4906982_mvs_surface_depth_v1/render_3d_comparison.py",
        "scripts/p2/e3_local_4906982_mvs_surface_depth_v1/build_3d_inline.py",
    ):
        source_hashes[rel] = sha256(REPO / rel)
    output_hashes = provenance.setdefault("output_index_sha256", {})
    for rel in (
        "representative_images/geometry_3d/ordinary_surface_3d.png",
        "representative_images/geometry_3d/high_z_tail_3d.png",
        "representative_images/geometry_3d/geometry_3d_samples.json",
        "representative_images/geometry_3d/receipt.json",
        "NOTES.md",
        "comparison.md",
    ):
        output_hashes[rel] = sha256(ROOT / rel)
    provenance["scientific_verdict"] = None
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    footprint = footprint_geometry()
    mvs = np.load(MVS_NPY).astype(np.float64) + SHIFT
    mvs = mvs[contains_xy(footprint, mvs[:, 0], mvs[:, 1])]
    fused = {arm: fused_points(arm) for arm in ARMS}
    gaussian = {arm: checkpoint_geometry(arm) for arm in ARMS}
    surface_figure(footprint, mvs, fused)
    tail_figure(footprint, gaussian)
    interactive_payload(footprint, mvs, fused, gaussian)
    receipt = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_surface_depth_v1.geometry_3d_receipt.v1",
        "status": "COMPLETE",
        "inputs": {"checkpoints": 2, "fused_surfaces": 2, "mvs_reference": str(MVS_NPY)},
        "outputs": ["ordinary_surface_3d.png", "high_z_tail_3d.png", "geometry_3d_samples.json"],
        "lod2_geometry_used": False,
        "scientific_verdict": None,
    }
    (OUTPUT / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    receipt["output_sha256"] = {
        name: sha256(OUTPUT / name)
        for name in receipt["outputs"]
    }
    (OUTPUT / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    update_task_records()
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()

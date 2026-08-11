#!/usr/bin/env python3
"""Render existing 20k classified evidence and Roofer geometry read-only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import laspy
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from shapely import contains_xy
from shapely.geometry import shape

from src.visualization.fixed_view_qualitative import load_cityjsonseq


ROOT = Path("/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_mvs_surface_depth_v1/P2-E3-LOCAL-4906982-MVS-SURFACE-DEPTH-v1")
REPO = Path("/workspace")
OUTPUT = ROOT / "representative_images/roofer_qualitative"
ARMS = ("RAW_DEPTH", "MVS_SURFACE_METRIC")
COLORS = {"RAW_DEPTH": "#2563eb", "MVS_SURFACE_METRIC": "#f97316"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sample(points: np.ndarray, maximum: int) -> np.ndarray:
    if len(points) <= maximum:
        return points
    select = np.linspace(0, len(points) - 1, maximum, dtype=np.int64)
    return points[select]


def load_arm(arm: str, footprint):
    base = ROOT / f"arms/{arm}/R1/evaluation/step_020000/fusion"
    cloud = laspy.read(base / "classified_surface.laz")
    xyz = np.column_stack((np.asarray(cloud.x), np.asarray(cloud.y), np.asarray(cloud.z)))
    classification = np.asarray(cloud.classification, dtype=np.uint8)
    inside = contains_xy(footprint, xyz[:, 0], xyz[:, 1])
    class6 = xyz[inside & (classification == 6)]
    class2 = xyz[inside & (classification == 2)]
    surfaces = load_cityjsonseq(base / "roofer/output/690897_5336168.city.jsonl")
    terminal = json.loads((base / "roofer/roofer_terminal.json").read_text())
    receipt = json.loads((base / "classification_receipt.json").read_text())
    return class6, class2, surfaces, terminal["target_attributes"], receipt["class_counts"]


def footprint_line(axis, footprint, z: float) -> None:
    xy = np.asarray(footprint.exterior.coords)
    axis.plot(xy[:, 0], xy[:, 1], np.full(len(xy), z), color="#171717", linewidth=1.2)


def static_panel(footprint, rows) -> Path:
    z_values = []
    for class6, class2, surfaces, _, _ in rows.values():
        z_values.extend(class6[:, 2].tolist())
        z_values.extend(value for surface in surfaces for value in surface.xyz[:, 2])
    zlo, zhi = np.quantile(np.asarray(z_values), [0.01, 0.99])
    zlo -= 1.5; zhi += 1.5
    minx, miny, maxx, maxy = footprint.bounds
    pad = 3.0
    fig = plt.figure(figsize=(15, 10), dpi=150, constrained_layout=True)
    for column, arm in enumerate(ARMS):
        class6, class2, surfaces, terminal, counts = rows[arm]
        # Top-down: exact footprint scale, evidence and semantic RoofSurface polygons.
        axis = fig.add_subplot(2, 2, column + 1)
        points = sample(class6, 16000)
        axis.scatter(points[:, 0], points[:, 1], s=0.5, color="#737373", alpha=0.22, linewidths=0)
        for surface in surfaces:
            if surface.semantic != "RoofSurface":
                continue
            xy = np.asarray(surface.xyz)[:, :2]
            axis.fill(xy[:, 0], xy[:, 1], facecolor=COLORS[arm], edgecolor="#171717", alpha=0.55, linewidth=0.6)
        boundary = np.asarray(footprint.exterior.coords)
        axis.plot(boundary[:, 0], boundary[:, 1], color="#171717", linewidth=1.2)
        axis.set_xlim(minx - pad, maxx + pad); axis.set_ylim(miny - pad, maxy + pad)
        axis.set_aspect("equal"); axis.set_axis_off()
        axis.set_title(
            f"{arm} · top\nclass 6={int(counts['6']):,} · roof planes={terminal['rf_roof_planes']} · ridgelines={terminal['rf_ridgelines']}",
            fontsize=10,
        )

        # Oblique: direct Roofer output plus the exact class-6 evidence it received.
        axis = fig.add_subplot(2, 2, column + 3, projection="3d", proj_type="ortho")
        points = sample(class6, 12000)
        axis.scatter(points[:, 0], points[:, 1], points[:, 2], s=0.5, color="#737373", alpha=0.20, linewidths=0, depthshade=False)
        semantic_colors = {"RoofSurface": COLORS[arm], "WallSurface": "#a3a3a3", "GroundSurface": "#d4d4d4"}
        for surface in surfaces:
            xyz = np.asarray(surface.xyz)
            if len(xyz) < 3:
                continue
            axis.add_collection3d(Poly3DCollection(
                [xyz], facecolor=semantic_colors.get(surface.semantic, "#d4d4d4"),
                edgecolor="#262626", linewidth=0.35, alpha=0.70,
            ))
        footprint_line(axis, footprint, float(terminal["rf_h_ground"]))
        axis.set_xlim(minx - pad, maxx + pad); axis.set_ylim(miny - pad, maxy + pad); axis.set_zlim(zlo, zhi)
        axis.set_box_aspect((maxx-minx+2*pad, maxy-miny+2*pad, zhi-zlo))
        axis.view_init(elev=29, azim=-55)
        axis.set_xlabel("E", fontsize=7); axis.set_ylabel("N", fontsize=7); axis.set_zlabel("Z", fontsize=7)
        axis.tick_params(labelsize=6)
        axis.set_title(
            f"Roofer output · volume={terminal['rf_volume_lod22']:.1f} m³ · internal RMSE={terminal['rf_rmse_lod22']:.1f}",
            fontsize=10,
        )
    fig.suptitle("DEBY_LOD2_4906982 · fixed 20k Roofer input evidence and actual output geometry", fontsize=14)
    path = OUTPUT / "roofer_evidence_and_output_20k.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def payload(footprint, rows) -> Path:
    cx, cy = footprint.centroid.x, footprint.centroid.y
    boundary = np.asarray(footprint.exterior.coords)
    body = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_surface_depth_v1.roofer_qualitative.v1",
        "footprint": [[round(float(x-cx), 3), round(float(y-cy), 3)] for x, y in boundary],
        "arms": {},
        "scientific_verdict": None,
    }
    for arm in ARMS:
        class6, class2, surfaces, terminal, counts = rows[arm]
        points = sample(class6, 3500)
        body["arms"][arm] = {
            "class6": [[round(float(x-cx), 3), round(float(y-cy), 3), round(float(z), 3)] for x, y, z in points],
            "surfaces": [
                {
                    "semantic": surface.semantic,
                    "xyz": [[round(float(x-cx), 3), round(float(y-cy), 3), round(float(z), 3)] for x, y, z in surface.xyz],
                }
                for surface in surfaces if len(surface.xyz) >= 3
            ],
            "metrics": {
                "class6": int(counts["6"]), "class2": int(counts["2"]),
                "roof_planes": int(terminal["rf_roof_planes"]), "ridgelines": int(terminal["rf_ridgelines"]),
                "volume_m3": float(terminal["rf_volume_lod22"]), "rmse": float(terminal["rf_rmse_lod22"]),
                "ground_z": float(terminal["rf_h_ground"]),
            },
        }
    path = OUTPUT / "roofer_qualitative.json"
    path.write_text(json.dumps(body, separators=(",", ":")) + "\n")
    return path


def update_records(outputs: list[Path]) -> None:
    receipt = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_surface_depth_v1.roofer_qualitative_receipt.v1",
        "status": "COMPLETE",
        "training_reruns": 0, "fusion_reruns": 0, "classification_reruns": 0, "roofer_reruns": 0,
        "lod2_geometry_used": False, "scientific_verdict": None,
        "outputs": {path.name: sha256(path) for path in outputs},
    }
    receipt_path = OUTPUT / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    outputs.append(receipt_path)
    marker = "## Roofer qualitative audit"
    comparison_path = ROOT / "comparison.md"
    comparison = comparison_path.read_text()
    if marker not in comparison:
        comparison += (
            "\n## Roofer qualitative audit\n\n"
            "- Read-only 20k inspection: RAW_DEPTH class-6 evidence 8,821, roof planes 25, ridgelines 1, and output volume 77.1 m3.\n"
            "- MVS_SURFACE_METRIC class-6 evidence 6,478, roof planes 11, ridgelines 0, and output volume 38.3 m3.\n"
            "- At the full shared-footprint scale, both outputs are partial; the MVS-surface-depth output retains only the narrow eastern roof patch.\n"
            "- No training, fusion, classification, or Roofer process was rerun for this audit. `scientific_verdict` remains `null`.\n"
        )
        comparison_path.write_text(comparison)
    notes_path = ROOT / "NOTES.md"
    notes = notes_path.read_text()
    if marker not in notes:
        notes += (
            "\n## Roofer qualitative audit\n\n"
            "- Existing classified evidence and CityJSONSeq outputs were rendered at matched top and oblique views.\n"
            "- LoD2 geometry was not used by this rendering step; scientific verdict remains `null`.\n"
        )
        notes_path.write_text(notes)
    outputs.extend((comparison_path, notes_path))
    provenance_path = ROOT / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    for rel_script in (
        "scripts/p2/e3_local_4906982_mvs_surface_depth_v1/render_roofer_qualitative.py",
        "scripts/p2/e3_local_4906982_mvs_surface_depth_v1/build_roofer_inline.py",
    ):
        provenance.setdefault("source_config_sha256", {})[rel_script] = sha256(REPO / rel_script)
    for path in outputs:
        rel = path.relative_to(ROOT).as_posix()
        provenance.setdefault("output_index_sha256", {})[rel] = sha256(path)
    provenance["scientific_verdict"] = None
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    footprint = shape(json.loads((ROOT / "control/shared_standard_footprint_4906982.geojson").read_text())["features"][0]["geometry"])
    rows = {arm: load_arm(arm, footprint) for arm in ARMS}
    outputs = [static_panel(footprint, rows), payload(footprint, rows)]
    update_records(outputs)
    print(json.dumps({"status": "COMPLETE", "outputs": [str(path) for path in outputs], "scientific_verdict": None}, indent=2))


if __name__ == "__main__":
    main()

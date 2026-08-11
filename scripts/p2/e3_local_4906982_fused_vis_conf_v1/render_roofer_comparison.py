#!/usr/bin/env python3
"""Render the existing 20k Roofer CityJSON outputs without changing them."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon as PolygonPatch
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union


REPO = Path("/workspace/JointBuildGS")
SOURCE_ROOT = Path(
    "/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1/"
    "P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1"
)
OUTPUT_ROOT = Path(
    "/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_roofer_vis_v1/"
    "P2-E3-LOCAL-4906982-ROOFER-VIS-v1"
)
FOOTPRINT = SOURCE_ROOT / "control/shared_standard_footprint_4906982.geojson"
CASES = {
    "MVS_SURFACE_METRIC": {
        "label": "All fused-mesh ray hits",
        "path": SOURCE_ROOT
        / "arms/MVS_SURFACE_METRIC/R1/evaluation/step_020000/fusion/roofer/output/690897_5336168.city.jsonl",
        "color": "#de6b35",
    },
    "FUSED_VIS_CONF": {
        "label": "View-supported fused target",
        "path": SOURCE_ROOT
        / "arms/FUSED_VIS_CONF/R1/evaluation/step_020000/fusion/roofer/output/690897_5336168.city.jsonl",
        "color": "#2a9d8f",
    },
}
SURFACE_COLORS = {
    "RoofSurface": "#d95f3b",
    "WallSurface": "#7d91ad",
    "GroundSurface": "#c5cbd3",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def transformed_vertices(feature: dict, transform: dict) -> list[tuple[float, float, float]]:
    scale = transform["scale"]
    translate = transform["translate"]
    return [
        tuple(float(vertex[i]) * float(scale[i]) + float(translate[i]) for i in range(3))
        for vertex in feature["vertices"]
    ]


def solid_faces(geometry: dict, vertices: list[tuple[float, float, float]]):
    if geometry.get("type") != "Solid" or not geometry.get("boundaries"):
        return []
    shell = geometry["boundaries"][0]
    values = geometry.get("semantics", {}).get("values", [[]])[0]
    surfaces = geometry.get("semantics", {}).get("surfaces", [])
    result = []
    for index, face in enumerate(shell):
        if not face or not face[0]:
            continue
        semantic_index = values[index] if index < len(values) else None
        semantic_type = (
            surfaces[semantic_index].get("type", "UnknownSurface")
            if isinstance(semantic_index, int) and semantic_index < len(surfaces)
            else "UnknownSurface"
        )
        result.append((semantic_type, [vertices[vertex_index] for vertex_index in face[0]]))
    return result


def load_case(path: Path) -> dict:
    lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    header = next(item for item in lines if item.get("type") == "CityJSON")
    feature = next(item for item in lines if item.get("type") == "CityJSONFeature")
    vertices = transformed_vertices(feature, header["transform"])
    faces = []
    parts = []
    parent_attributes = {}
    for object_id, city_object in feature["CityObjects"].items():
        if object_id == "DEBY_LOD2_4906982":
            parent_attributes = city_object.get("attributes", {})
        if city_object.get("type") == "BuildingPart":
            parts.append(object_id)
            for geometry in city_object.get("geometry", []):
                faces.extend(solid_faces(geometry, vertices))
    roof_polygons = []
    for semantic_type, face in faces:
        if semantic_type != "RoofSurface" or len(face) < 3:
            continue
        polygon = Polygon([(point[0], point[1]) for point in face])
        if polygon.is_valid and polygon.area > 0:
            roof_polygons.append(polygon)
    return {
        "faces": faces,
        "parts": parts,
        "attributes": parent_attributes,
        "roof_union": unary_union(roof_polygons),
    }


def style_axis(axis) -> None:
    axis.set_facecolor("#f6f4ef")
    axis.grid(color="#d8d4cc", linewidth=0.7, alpha=0.7)
    axis.tick_params(labelsize=8, colors="#4a4a4a")


def plot_plan(axis, footprint, case: dict, case_meta: dict) -> None:
    style_axis(axis)
    exterior = list(footprint.exterior.coords)
    axis.plot(*zip(*exterior), color="#222222", linewidth=2.2, label="shared footprint XY")
    for interior in footprint.interiors:
        axis.plot(*zip(*interior.coords), color="#222222", linewidth=1.2)
    roofs = case["roof_union"]
    polygons = list(roofs.geoms) if roofs.geom_type == "MultiPolygon" else [roofs]
    patches = [PolygonPatch(list(polygon.exterior.coords), closed=True) for polygon in polygons if not polygon.is_empty]
    if patches:
        axis.add_collection(
            PatchCollection(patches, facecolor=case_meta["color"], edgecolor="#6f2b18", alpha=0.84, linewidth=1.1)
        )
    minx, miny, maxx, maxy = footprint.bounds
    margin = 2.5
    axis.set_xlim(minx - margin, maxx + margin)
    axis.set_ylim(miny - margin, maxy + margin)
    axis.set_aspect("equal", adjustable="box")
    coverage = 100.0 * roofs.area / footprint.area
    axis.set_title(case_meta["label"], fontsize=13, fontweight="bold", color="#202020", pad=10)
    axis.text(
        0.02,
        0.03,
        f"roof projection {roofs.area:.1f} m²  |  {coverage:.2f}% of footprint  |  {len(case['parts'])} part(s)",
        transform=axis.transAxes,
        fontsize=9,
        color="#2a2a2a",
        bbox={"facecolor": "#fffdf8", "edgecolor": "#c9c2b8", "alpha": 0.94, "pad": 4},
    )
    axis.set_xlabel("Easting (m)", fontsize=9)
    axis.set_ylabel("Northing (m)", fontsize=9)


def plot_solid(axis, footprint, case: dict, case_meta: dict) -> None:
    style_axis(axis)
    by_surface: dict[str, list[list[tuple[float, float, float]]]] = {}
    for semantic_type, face in case["faces"]:
        by_surface.setdefault(semantic_type, []).append(face)
    for semantic_type, faces in by_surface.items():
        axis.add_collection3d(
            Poly3DCollection(
                faces,
                facecolors=SURFACE_COLORS.get(semantic_type, "#a8a8a8"),
                edgecolors="#3b4654",
                linewidths=0.45,
                alpha=0.92,
            )
        )
    all_z = [point[2] for _, face in case["faces"] for point in face]
    ground_z = min(all_z) if all_z else 0.0
    footprint_ring = [(x, y, ground_z) for x, y in footprint.exterior.coords]
    axis.plot3D(*zip(*footprint_ring), color="#171717", linewidth=2.2)
    minx, miny, maxx, maxy = footprint.bounds
    axis.set_xlim(minx - 2.5, maxx + 2.5)
    axis.set_ylim(miny - 2.5, maxy + 2.5)
    z_min = min(all_z) - 0.25
    z_max = max(all_z) + 0.25
    axis.set_zlim(z_min, z_max)
    axis.set_box_aspect((maxx - minx, maxy - miny, 16.0))
    axis.view_init(elev=29, azim=-56)
    axis.set_title(f"{case_meta['label']} — Roofer solid", fontsize=12, fontweight="bold", pad=6)
    axis.set_xlabel("E", fontsize=8, labelpad=2)
    axis.set_ylabel("N", fontsize=8, labelpad=2)
    axis.set_zlabel("Z (m)", fontsize=8, labelpad=2)
    axis.text2D(0.02, 0.02, "black outline = full shared footprint  |  Z visually exaggerated", transform=axis.transAxes, fontsize=8)


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    output_dir = OUTPUT_ROOT / "representative_images"
    output_dir.mkdir(parents=True, exist_ok=True)
    footprint_document = json.loads(FOOTPRINT.read_text())
    footprint = shape(footprint_document["features"][0]["geometry"])
    cases = {name: load_case(meta["path"]) for name, meta in CASES.items()}

    figure = plt.figure(figsize=(16, 11), facecolor="#ece9e2")
    grid = figure.add_gridspec(2, 2, height_ratios=(1.02, 1.0), hspace=0.13, wspace=0.08)
    for column, (name, meta) in enumerate(CASES.items()):
        plot_plan(figure.add_subplot(grid[0, column]), footprint, cases[name], meta)
        plot_solid(figure.add_subplot(grid[1, column], projection="3d"), footprint, cases[name], meta)
    figure.suptitle(
        "DEBY_LOD2_4906982 — actual Roofer outputs at 20k",
        fontsize=18,
        fontweight="bold",
        color="#1f2933",
        y=0.985,
    )
    figure.text(
        0.5,
        0.006,
        "Roofer returned a model in both cases, but only the colored roof patches were reconstructed inside the full black footprint.",
        ha="center",
        fontsize=10,
        color="#3b3b3b",
    )
    png = output_dir / "roofer_20k_comparison.png"
    figure.savefig(png, dpi=170, bbox_inches="tight", facecolor=figure.get_facecolor())
    plt.close(figure)

    metrics = {}
    for name, case in cases.items():
        attrs = case["attributes"]
        metrics[name] = {
            "roofer_success": attrs.get("rf_success"),
            "roof_projection_area_m2": case["roof_union"].area,
            "shared_footprint_area_m2": footprint.area,
            "roof_projection_coverage_pct": 100.0 * case["roof_union"].area / footprint.area,
            "building_parts": len(case["parts"]),
            "roof_planes": attrs.get("rf_roof_planes"),
            "ridgelines": attrs.get("rf_ridgelines"),
            "roofer_internal_rmse_lod22": attrs.get("rf_rmse_lod22"),
        }
    git_prefix = ["git", "-c", f"safe.directory={REPO}"]
    git_commit = subprocess.check_output([*git_prefix, "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    git_branch = subprocess.check_output([*git_prefix, "branch", "--show-current"], cwd=REPO, text=True).strip()
    receipt = {
        "schema": "jointbuildgs.p2.e3_local_4906982.roofer_visualization.v1",
        "task_id": "P2-E3-LOCAL-4906982-ROOFER-VIS-v1",
        "status": "COMPLETE",
        "git_commit": git_commit,
        "git_branch": git_branch,
        "source_task": str(SOURCE_ROOT),
        "inputs_sha256": {"footprint": sha256(FOOTPRINT), **{name: sha256(meta["path"]) for name, meta in CASES.items()}},
        "metrics": metrics,
        "outputs_sha256": {str(png.relative_to(OUTPUT_ROOT)): sha256(png)},
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "lod2_z_or_roof_geometry_used": False,
        "scientific_verdict": None,
    }
    (OUTPUT_ROOT / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

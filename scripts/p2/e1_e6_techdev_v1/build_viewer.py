from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import open3d as o3d
from shapely.geometry import shape

from scripts.p2.e1_e6_techdev_v1.prepare_prior_geometry import load_scene_als
from src.stage2.pilot_plane_mask_producer import load_lod2_citygml_scene


TASK_REL = Path("phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1")
WORLD_SHIFT = np.asarray([690953.0, 5336071.0, 604.0])


def local_rings(geometry) -> list[list[list[float]]]:
    polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
    output = []
    for polygon in polygons:
        for ring in (polygon.exterior, *polygon.interiors):
            output.append([
                [float(x - WORLD_SHIFT[0]), float(y - WORLD_SHIFT[1])]
                for x, y in ring.coords
            ])
    return output


def change_label(change: dict) -> tuple[str, str]:
    if change.get("simulates") == "NEW_CONSTRUCTION":
        return "신축 모사 (과거 prior 제거)", "#ef4444"
    if change.get("simulates") == "DEMOLITION":
        return "철거 모사 (과거 prior 삽입)", "#06b6d4"
    scale = float(change["scale"])
    direction = "증가" if scale > 1 else "감소"
    return f"높이 {direction} 모사 (x{scale:.1f})", "#facc15"


def viewer_metadata(task: Path, footprints_data: dict) -> tuple[list[dict], list[dict], list[dict]]:
    wb = json.loads((task / "prep/w_b.json").read_text(encoding="utf-8"))["buildings"]
    changes = json.loads((task / "prep/synthetic_changes.json").read_text(encoding="utf-8"))["changes"]
    changes_by_id = {str(item["stable_id"]): item for item in changes}
    real_path = task / "prep/real_change_candidates/candidates.geojson"
    real_data = json.loads(real_path.read_text(encoding="utf-8"))
    real_by_id = {
        str(feature["properties"]["stable_id"]): feature["properties"]
        for feature in real_data["features"]
    }
    real_geometry_by_id = {
        str(feature["properties"]["stable_id"]): shape(feature["geometry"])
        for feature in real_data["features"]
    }
    buildings, synthetic_regions, real_regions = [], [], []
    for feature in footprints_data["features"]:
        stable_id = str(feature["properties"]["stable_id"])
        geometry = shape(feature["geometry"])
        minx, miny, maxx, maxy = geometry.bounds
        change = changes_by_id.get(stable_id)
        change_summary = None
        if change is not None:
            label, color = change_label(change)
            change_summary = {**change, "label_ko": label, "color": color}
            synthetic_regions.append({
                **change_summary,
                "rings_local_xy": local_rings(geometry),
            })
        real_summary = real_by_id.get(stable_id)
        if real_summary is not None:
            real_regions.append({
                **real_summary,
                "rings_local_xy": local_rings(real_geometry_by_id[stable_id]),
            })
        buildings.append({
            "stable_id": stable_id,
            "bbox_local_xy": [
                minx - WORLD_SHIFT[0], miny - WORLD_SHIFT[1],
                maxx - WORLD_SHIFT[0], maxy - WORLD_SHIFT[1],
            ],
            "w_b": float(wb[stable_id]["w_b"]),
            "support_status": wb[stable_id]["support_status"],
            "synthetic_change": change_summary,
            "real_change_candidate": real_summary,
        })
    return buildings, synthetic_regions, real_regions


def add_pointcloud_assets(task: Path, panels: list[dict]) -> list[dict]:
    pointclouds = json.loads((task / "viewer/roofer_pointclouds.json").read_text(encoding="utf-8"))
    for condition, panel in zip(("E1", "E2", "E3", "E4", "E5", "E6"), panels[:6], strict=True):
        panel["condition"] = condition
        panel["roofer_pointcloud"] = pointclouds["conditions"][condition]
    return panels


def add_surface_mesh_assets(task: Path, panels: list[dict]) -> list[dict]:
    meshes = json.loads((task / "viewer/surface_meshes.json").read_text(encoding="utf-8"))
    panel_by_condition = {panel.get("condition"): panel for panel in panels}
    for condition, record in meshes["conditions"].items():
        if condition in panel_by_condition:
            panel_by_condition[condition]["surface_mesh"] = record
    return panels


def rings(value):
    if isinstance(value, list) and value and all(isinstance(item, int) for item in value):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from rings(item)


def cityjson_obj(source: Path, destination: Path) -> None:
    data = json.loads(source.read_text(encoding="utf-8"))
    transform = data.get("transform", {"scale": [1, 1, 1], "translate": [0, 0, 0]})
    scale, translate = np.asarray(transform["scale"]), np.asarray(transform["translate"])
    vertices = np.asarray(data["vertices"], dtype=np.float64) * scale + translate - WORLD_SHIFT
    lines = [*(f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in vertices)]
    for cityobject in data["CityObjects"].values():
        for geometry in cityobject.get("geometry", []):
            for ring in rings(geometry.get("boundaries", [])):
                if len(ring) >= 3:
                    lines.append("f " + " ".join(str(index + 1) for index in ring))
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def add_e3_local_variants(task: Path, assets: Path, panels: list[dict]) -> list[dict]:
    registry_path = task / "viewer/e3_local_variants.json"
    if not registry_path.is_file():
        return panels
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    pointclouds = json.loads((task / "viewer/roofer_pointclouds.json").read_text(encoding="utf-8"))
    meshes = json.loads((task / "viewer/surface_meshes.json").read_text(encoding="utf-8"))
    panel = next(item for item in panels if item.get("condition") == "E3")
    variants = [{
        "id": "ORIGINAL_GLOBAL",
        "label": "E3 image-only GS · 기존 전체 scene",
        "condition": "E3",
        "type": panel["type"],
        "asset": panel["asset"],
        "color": panel["color"],
        "roofer_pointcloud": panel["roofer_pointcloud"],
        "surface_mesh": panel["surface_mesh"],
        "step": None,
        "validation_selected": False,
    }]
    for record in registry["variants"]:
        condition = f"E3_{record['id']}"
        destination = assets / f"{condition}.obj"
        override = task / "runs" / record["run_name"] / "roofer/assembled.city.json"
        cityjson_obj(override, destination)
        variants.append({
            "id": record["id"],
            "label": f"E3 image-only GS · 4906982 {record['label']}",
            "condition": condition,
            "type": "mesh",
            "asset": f"assets/{destination.name}",
            "color": panel["color"],
            "roofer_pointcloud": pointclouds["conditions"][condition],
            "surface_mesh": meshes["conditions"][condition],
            "step": record["step"],
            "validation_selected": record["validation_selected"],
        })
    default = next(item for item in variants if item["validation_selected"])
    panel.update(default)
    panel["variants"] = variants
    panel["variant_selection_rule"] = "ORIGINAL_GLOBAL_AND_7K_30K_LOCAL_RUNS_SELECTABLE_7K_DEFAULT"
    return panels


def lod_obj(scene, destination: Path) -> None:
    triangles = np.asarray(scene.triangles_local)
    lines = []
    for triangle in triangles:
        base = len(lines) // 4 * 3 + 1
        lines.extend(f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in triangle)
        lines.append(f"f {base} {base + 1} {base + 2}")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    repo, artifacts = args.repository_root.resolve(), args.artifact_root.resolve()
    task = artifacts / TASK_REL
    viewer, assets = task / "viewer", task / "viewer/assets"
    receipt = viewer / "viewer_manifest.json"
    viewer.mkdir(parents=True, exist_ok=True); assets.mkdir(parents=True, exist_ok=True)
    app = repo / "src/apps/e1_e6_roofer_web_review"
    for name in ("index.html", "app.js"):
        shutil.copy2(app / name, viewer / name)
    shutil.copy2(repo / "src/apps/gs3d_4way_viewer/build/three.module.min.js", viewer / "three.module.min.js")
    footprint_path = artifacts / (
        "phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
        "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/freeze/shared_footprints_199.geojson"
    )
    footprints_data = json.loads(footprint_path.read_text(encoding="utf-8"))
    if receipt.is_file():
        manifest = json.loads(receipt.read_text(encoding="utf-8"))
        manifest["buildings"], manifest["synthetic_change_regions"], manifest["real_change_candidates"] = viewer_metadata(task, footprints_data)
        manifest.pop("change_regions", None)
        manifest["panels"] = add_pointcloud_assets(task, manifest["panels"])
        manifest["panels"] = add_surface_mesh_assets(task, manifest["panels"])
        manifest["panels"] = add_e3_local_variants(task, assets, manifest["panels"])
        manifest["synthetic_change_region_source"] = {
            "stable_ids": "prep/synthetic_changes.json",
            "geometry": str(footprint_path),
            "meaning": "SYNTHETIC_CHANGE_BUILDING_FOOTPRINTS_NOT_DDSM_THRESHOLD_REGIONS",
        }
        manifest["real_change_candidate_source"] = {
            "path": "prep/real_change_candidates/candidates.geojson",
            "meaning": "AUTOMATIC_2024_E1_ULS_VS_2022_EXISTING_ALS_SENSOR_DIFFERENCE_CANDIDATES_NOT_VERIFIED_CHANGE_GT",
        }
        manifest.pop("change_region_source", None)
        receipt.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0
    city_sources = {
        "E1": task / "runs/E1/roofer/assembled.city.json",
        "E2": task / "runs/E2/roofer/assembled.city.json",
        "E3": task / "runs/E3_GS_IMAGE/roofer/assembled.city.json",
        "E4": task / "runs/E4_GS_ALS_UNWEIGHTED/roofer/assembled.city.json",
        "E5": task / "runs/E5_GS_ALS_WB/roofer/assembled.city.json",
        "E6": task / "runs/E6_GS_LOD2_PLANES_DIAGNOSTIC/roofer/assembled.city.json",
    }
    for condition, source in city_sources.items():
        cityjson_obj(source, assets / f"{condition}.obj")
    ids = [str(feature["properties"]["stable_id"]) for feature in footprints_data["features"]]
    gml = [artifacts / f"phase-payloads/p0-audit/data/raw/lod2/{tile}.gml" for tile in ("690_5334", "690_5336")]
    scene = load_lod2_citygml_scene(gml, ids, include_unselected=False)
    lod_obj(scene, assets / "prior_lod2.obj")
    als_paths = [artifacts / f"phase-payloads/p0-audit/data/raw/als/{tile}.laz" for tile in ("690_5335", "690_5336", "691_5335", "691_5336")]
    als_world, _classes, _sources = load_scene_als(als_paths)
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(als_world - WORLD_SHIFT)).voxel_down_sample(1.0)
    np.asarray(cloud.points, dtype=np.float32).tofile(assets / "prior_lidar_xyz_f32.bin")
    buildings, synthetic_regions, real_regions = viewer_metadata(task, footprints_data)
    panels = [
        {"label":"E1 lidar-roofer (2024 ULS)","type":"mesh","asset":"assets/E1.obj","color":"#2f80ed"},
        {"label":"E2 mvs-roofer","type":"mesh","asset":"assets/E2.obj","color":"#d946ef"},
        {"label":"E3 image-only GS","type":"mesh","asset":"assets/E3.obj","color":"#9ca3af"},
        {"label":"E4 ALS unweighted","type":"mesh","asset":"assets/E4.obj","color":"#f59e0b"},
        {"label":"E5 ALS x w_b","type":"mesh","asset":"assets/E5.obj","color":"#22c55e"},
        {"label":"E6 LoD planes diagnostic","type":"mesh","asset":"assets/E6.obj","color":"#9333ea"},
        {"label":"Existing ALS raw prior (1m viewer adapter)","type":"points","asset":"assets/prior_lidar_xyz_f32.bin","color":"#38bdf8"},
        {"label":"Existing LoD2 original","type":"mesh","asset":"assets/prior_lod2.obj","color":"#eab308"},
    ]
    panels = add_pointcloud_assets(task, panels)
    panels = add_surface_mesh_assets(task, panels)
    panels = add_e3_local_variants(task, assets, panels)
    receipt.write_text(json.dumps({
        "schema": "jointbuildgs.p2.e1_e6.viewer.v1",
        "panels": panels,
        "buildings": buildings,
        "synthetic_change_regions": synthetic_regions,
        "real_change_candidates": real_regions,
        "synthetic_change_region_source": {
            "stable_ids": "prep/synthetic_changes.json",
            "geometry": str(footprint_path),
            "meaning": "SYNTHETIC_CHANGE_BUILDING_FOOTPRINTS_NOT_DDSM_THRESHOLD_REGIONS",
        },
        "real_change_candidate_source": {
            "path": "prep/real_change_candidates/candidates.geojson",
            "meaning": "AUTOMATIC_2024_E1_ULS_VS_2022_EXISTING_ALS_SENSOR_DIFFERENCE_CANDIDATES_NOT_VERIFIED_CHANGE_GT",
        },
        "camera_sync": True,
        "scientific_verdict": None,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

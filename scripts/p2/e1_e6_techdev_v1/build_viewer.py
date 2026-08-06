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
    if receipt.is_file():
        return 0
    viewer.mkdir(parents=True, exist_ok=True); assets.mkdir(parents=True, exist_ok=True)
    app = repo / "src/apps/e1_e6_roofer_web_review"
    for name in ("index.html", "app.js"):
        shutil.copy2(app / name, viewer / name)
    shutil.copy2(repo / "src/apps/gs3d_4way_viewer/build/three.module.min.js", viewer / "three.module.min.js")
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
    footprint_path = artifacts / (
        "phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
        "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/freeze/shared_footprints_199.geojson"
    )
    footprints_data = json.loads(footprint_path.read_text(encoding="utf-8"))
    ids = [str(feature["properties"]["stable_id"]) for feature in footprints_data["features"]]
    gml = [artifacts / f"phase-payloads/p0-audit/data/raw/lod2/{tile}.gml" for tile in ("690_5334", "690_5336")]
    scene = load_lod2_citygml_scene(gml, ids, include_unselected=False)
    lod_obj(scene, assets / "prior_lod2.obj")
    als_paths = [artifacts / f"phase-payloads/p0-audit/data/raw/als/{tile}.laz" for tile in ("690_5335", "690_5336", "691_5335", "691_5336")]
    als_world, _classes, _sources = load_scene_als(als_paths)
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(als_world - WORLD_SHIFT)).voxel_down_sample(1.0)
    np.asarray(cloud.points, dtype=np.float32).tofile(assets / "prior_lidar_xyz_f32.bin")
    wb = json.loads((task / "prep/w_b.json").read_text(encoding="utf-8"))["buildings"]
    buildings = []
    for feature in footprints_data["features"]:
        stable_id = str(feature["properties"]["stable_id"]); geometry = shape(feature["geometry"])
        minx, miny, maxx, maxy = geometry.bounds
        buildings.append({"stable_id": stable_id, "bbox_local_xy": [minx-WORLD_SHIFT[0], miny-WORLD_SHIFT[1], maxx-WORLD_SHIFT[0], maxy-WORLD_SHIFT[1]], "w_b": float(wb[stable_id]["w_b"]), "support_status": wb[stable_id]["support_status"]})
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
    receipt.write_text(json.dumps({"schema":"jointbuildgs.p2.e1_e6.viewer.v1","panels":panels,"buildings":buildings,"camera_sync":True,"scientific_verdict":None}, indent=2)+"\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

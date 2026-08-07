from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import open3d as o3d


WORLD_SHIFT = np.asarray([690953.0, 5336071.0, 604.0], dtype=np.float64)
TARGET_TRIANGLES = 180_000
SCHEMA = "jointbuildgs.p2.e1_e6.viewer_surface_meshes.v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def mesh_sources(task: Path) -> dict[str, dict]:
    output = {
        "E2": {
            "path": task / "prep/viewer_surface_meshes/E2_openmvs_mesh.ply",
            "role": "OPENMVS_RECONSTRUCTMESH_FROM_EXACT_E2_DENSE_MVS_PROJECT_VIEWER_DERIVATIVE",
        },
        "E3": {"path": task / "runs/E3_GS_IMAGE/mesh/tsdf_mesh.ply", "role": "E3_TSDF_EVALUATION_MESH"},
        "E4": {"path": task / "runs/E4_GS_ALS_UNWEIGHTED/mesh/tsdf_mesh.ply", "role": "E4_TSDF_EVALUATION_MESH"},
        "E5": {"path": task / "runs/E5_GS_ALS_WB/mesh/tsdf_mesh.ply", "role": "E5_TSDF_EVALUATION_MESH"},
        "E6": {"path": task / "runs/E6_GS_LOD2_PLANES_DIAGNOSTIC/mesh/tsdf_mesh.ply", "role": "E6_TSDF_EVALUATION_MESH"},
    }
    variants_path = task / "viewer/e3_local_variants.json"
    if variants_path.is_file():
        variants = json.loads(variants_path.read_text(encoding="utf-8"))
        for variant in variants["variants"]:
            output[f"E3_{variant['id']}"] = {
                "path": Path(variant["depth_fusion"]["mesh"]["path"]),
                "role": f"E3_LOCAL_4906982_{variant['id']}_TSDF_DIAGNOSTIC_MESH",
            }
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    args = parser.parse_args()
    task = args.task_root.resolve()
    viewer = task / "viewer"
    assets = viewer / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    receipt_path = viewer / "surface_meshes.json"
    sources = mesh_sources(task)
    for condition, record in sources.items():
        if not record["path"].is_file():
            raise FileNotFoundError(f"{condition} surface mesh missing: {record['path']}")
    identities = {condition: sha256(record["path"]) for condition, record in sources.items()}
    previous_conditions = {}
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("schema") == SCHEMA:
            previous_conditions = receipt.get("conditions", {})
        if (
            receipt.get("schema") == SCHEMA
            and receipt.get("source_identity") == identities
            and all((viewer / item["asset"]).is_file() for item in receipt["conditions"].values())
        ):
            return 0

    conditions = {}
    for condition, record in sources.items():
        source = record["path"]
        previous = previous_conditions.get(condition)
        if (
            previous
            and previous.get("source_sha256") == identities[condition]
            and (viewer / previous.get("asset", "")).is_file()
        ):
            conditions[condition] = previous
            print(f"[viewer mesh] reuse {condition}", flush=True)
            continue
        print(f"[viewer mesh] reading {condition}: {source}", flush=True)
        mesh = o3d.io.read_triangle_mesh(str(source), enable_post_processing=False)
        source_triangles = len(mesh.triangles)
        if source_triangles == 0:
            raise RuntimeError(f"{condition} source has no triangles")
        source_vertices = np.asarray(mesh.vertices)
        coordinate_frame = "EPSG25832_WORLD"
        if float(np.median(np.abs(source_vertices[:, :2]))) < 100_000.0:
            coordinate_frame = "GS_LOCAL"
        else:
            mesh.translate(-WORLD_SHIFT)
        if source_triangles > TARGET_TRIANGLES:
            mesh = mesh.simplify_quadric_decimation(TARGET_TRIANGLES)
        triangles = np.asarray(mesh.triangles, dtype=np.int64)
        vertices = np.asarray(mesh.vertices, dtype=np.float32)
        expanded = np.ascontiguousarray(vertices[triangles].reshape(-1, 3), dtype=np.float32)
        destination = assets / f"{condition}_surface_mesh_triangles_f32.bin"
        expanded.tofile(destination)
        conditions[condition] = {
            "source": str(source),
            "source_sha256": identities[condition],
            "source_role": record["role"],
            "source_coordinate_frame": coordinate_frame,
            "source_triangle_count": source_triangles,
            "display_triangle_count": int(len(triangles)),
            "display_proxy_method": f"OPEN3D_QUADRIC_DECIMATION_TARGET_{TARGET_TRIANGLES}_THEN_EXPANDED_FLOAT32_TRIANGLES",
            "asset": f"assets/{destination.name}",
            "asset_sha256": sha256(destination),
        }
        print(
            f"[viewer mesh] {condition}: {source_triangles} -> {len(triangles)} triangles",
            flush=True,
        )
    atomic_json(receipt_path, {
        "schema": SCHEMA,
        "role": "DISPLAY_ONLY_SURFACE_MESH_ADAPTERS_NOT_ROOFER_INPUTS",
        "source_identity": identities,
        "target_display_triangles": TARGET_TRIANGLES,
        "conditions": conditions,
        "E1_surface_mesh": None,
        "E1_reason": "CURRENT_ULS_BASELINE_HAS_NO_FROZEN_SURFACE_MESH; POINT_CLOUD_REMAINS_THE_NATIVE_EVIDENCE",
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Bake current RGB onto sealed Poisson/TSDF roof meshes using planar roof UVs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import load_building_references
from scripts.p2.c3_mesh_attribute_hybrid_v1.render import _ground_z, _resample_ring
from scripts.p2.c3_roof_texture_bake_v1.contract import load_config, validate_config
from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import canonical_json_bytes, file_record, resolve_artifact, write_new
from scripts.p2.c3_tsdf_roof_diagnostic_v1.render import VIEWS, _draw_footprint, _principal_frame, _setup_axes
from src.stage2.dataloader import ColmapDataset


def _visible_names(config: Mapping[str, Any], repo_root: Path) -> list[str]:
    manifest = json.loads((repo_root / config["source"]["exact_view_manifest_git_path"]).read_text(encoding="utf-8"))
    names = [str(row["basename"]) for row in manifest["rows"]]
    if len(names) != int(config["source"]["exact_view_count"]):
        raise RuntimeError("exact current RGB membership drifted")
    return names


def _mesh_path(root: Path, condition: str, stable_id: str, method: str) -> Path:
    name = "poisson_same_evidence_roof_mesh_v1.ply" if method == "POISSON" else "tsdf_roof_mesh_v1.ply"
    return root / f"conditions/{condition}/buildings/{stable_id}/{name}"


def _uv(vertices: np.ndarray, bounds: tuple[float, float, float, float]) -> np.ndarray:
    x0, y0, x1, y1 = bounds
    u = (vertices[:, 0] - x0) / max(x1 - x0, 1e-9)
    v = (vertices[:, 1] - y0) / max(y1 - y0, 1e-9)
    return np.column_stack((np.clip(u, 0, 1), np.clip(v, 0, 1)))


def _top_surface(
    mesh: o3d.geometry.TriangleMesh,
    bounds: tuple[float, float, float, float],
    resolution: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    center = vertices.mean(axis=0)
    local = o3d.geometry.TriangleMesh(mesh)
    local.vertices = o3d.utility.Vector3dVector(vertices - center)
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(local))
    x0, y0, x1, y1 = bounds
    xs = np.linspace(x0, x1, resolution, endpoint=False) + (x1 - x0) / (2 * resolution)
    ys = np.linspace(y1, y0, resolution, endpoint=False) - (y1 - y0) / (2 * resolution)
    xx, yy = np.meshgrid(xs, ys)
    origin_z = float(vertices[:, 2].max() + 5.0)
    origins = np.column_stack((xx.ravel(), yy.ravel(), np.full(xx.size, origin_z))) - center
    rays = np.column_stack((origins, np.tile([0.0, 0.0, -1.0], (len(origins), 1)))).astype(np.float32)
    hit = scene.cast_rays(o3d.core.Tensor(rays))
    distance = hit["t_hit"].numpy()
    valid = np.isfinite(distance)
    points = origins[valid] + np.asarray([0, 0, -1.0]) * distance[valid, None] + center
    normals = hit["primitive_normals"].numpy()[valid].astype(np.float64)
    primitive_ids = hit["primitive_ids"].numpy()[valid].astype(np.int64)
    return points, normals, np.flatnonzero(valid), primitive_ids


def _top_triangle_mesh(mesh: o3d.geometry.TriangleMesh, primitive_ids: np.ndarray) -> o3d.geometry.TriangleMesh:
    """Keep only triangles reached by top-down atlas rays; walls/back faces are excluded."""
    source_vertices = np.asarray(mesh.vertices, dtype=np.float64)
    source_triangles = np.asarray(mesh.triangles, dtype=np.int64)
    selected = source_triangles[np.unique(primitive_ids)]
    used, inverse = np.unique(selected.ravel(), return_inverse=True)
    roof = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(source_vertices[used]),
        o3d.utility.Vector3iVector(inverse.reshape(-1, 3)),
    )
    roof.compute_vertex_normals()
    return roof


def _display_wall_hybrid(
    roof_mesh: o3d.geometry.TriangleMesh,
    footprint: Any,
    ground_z: float,
    spacing: float,
    nearest_count: int,
    minimum_wall_height: float,
) -> tuple[o3d.geometry.TriangleMesh, int, dict[str, Any]]:
    """Add an untextured GT-footprint wall skirt for display only."""
    roof_vertices=np.asarray(roof_mesh.vertices,dtype=np.float64); roof_faces=np.asarray(roof_mesh.triangles,dtype=np.int64)
    if not len(roof_vertices) or not len(roof_faces): raise RuntimeError("empty roof mesh")
    tree=cKDTree(roof_vertices[:,:2]); polygons=[footprint] if footprint.geom_type=="Polygon" else list(footprint.geoms)
    added_vertices=[]; added_faces=[]; base=len(roof_vertices)
    for polygon in polygons:
        rings=[np.asarray(polygon.exterior.coords)]+[np.asarray(ring.coords) for ring in polygon.interiors]
        for raw_ring in rings:
            ring=_resample_ring(raw_ring,spacing); k=min(max(1,nearest_count),len(roof_vertices)); distance,index=tree.query(ring,k=k)
            if k==1: distance,index=distance[:,None],index[:,None]
            weight=1.0/np.maximum(distance,0.25); top_z=np.sum(roof_vertices[index,2]*weight,axis=1)/np.sum(weight,axis=1); top_z=np.maximum(top_z,ground_z+minimum_wall_height)
            start=base+len(added_vertices)
            for xy,z in zip(ring,top_z): added_vertices.extend((np.asarray([xy[0],xy[1],z]),np.asarray([xy[0],xy[1],ground_z])))
            for i0 in range(len(ring)):
                i1=(i0+1)%len(ring); t0,b0=start+2*i0,start+2*i0+1; t1,b1=start+2*i1,start+2*i1+1; added_faces.extend(((t0,b0,t1),(t1,b0,b1)))
    wall_vertices=np.asarray(added_vertices,dtype=np.float64); wall_faces=np.asarray(added_faces,dtype=np.int64)
    hybrid=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(np.vstack((roof_vertices,wall_vertices))),o3d.utility.Vector3iVector(np.vstack((roof_faces,wall_faces)))); hybrid.compute_vertex_normals()
    return hybrid,len(roof_faces),{"role":"GT_FOOTPRINT_DISPLAY_WALL_NOT_HONEST_STAGE3","source_roof_vertex_count":int(len(roof_vertices)),"source_roof_face_count":int(len(roof_faces)),"wall_vertex_count":int(len(wall_vertices)),"wall_face_count":int(len(wall_faces)),"ground_z_m":float(ground_z),"wall_texture_created":False,"ground_cap_created":False,"honest_stage3_output":False,"official_metric_input":False,"scientific_verdict":None}


def _bilinear(image: np.ndarray, uv: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    x = np.clip(uv[:, 0], 0, w - 1.001)
    y = np.clip(uv[:, 1], 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    wx, wy = x - x0, y - y0
    return (
        image[y0, x0] * (1 - wx)[:, None] * (1 - wy)[:, None]
        + image[y0, x1] * wx[:, None] * (1 - wy)[:, None]
        + image[y1, x0] * (1 - wx)[:, None] * wy[:, None]
        + image[y1, x1] * wx[:, None] * wy[:, None]
    )


def _bake_texture(
    mesh: o3d.geometry.TriangleMesh,
    bounds: tuple[float, float, float, float],
    frames: Sequence[tuple[Any, Mapping[str, Any]]],
    config: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray, o3d.geometry.TriangleMesh, dict[str, Any]]:
    cfg = config["texture"]
    resolution = int(cfg["atlas_resolution_px"])
    points, normals, atlas_index, primitive_ids = _top_surface(mesh, bounds, resolution)
    roof_mesh = _top_triangle_mesh(mesh, primitive_ids)
    shift = np.asarray(config["frame"]["world_shift_xyz"], dtype=np.float64)
    color_sum = np.zeros((len(points), 3), dtype=np.float64)
    weight_sum = np.zeros(len(points), dtype=np.float64)
    view_count = np.zeros(len(points), dtype=np.uint16)
    depth_confirmed_count = np.zeros(len(points), dtype=np.uint16)
    used_views = []
    for frame, sample in frames:
        rgb = sample["rgb"].numpy().astype(np.float64)
        K = sample["K"].numpy().astype(np.float64)
        w2c = sample["w2c"].numpy().astype(np.float64)
        local = points - shift
        camera = local @ w2c[:3, :3].T + w2c[:3, 3]
        front = camera[:, 2] > 0.1
        uvw = camera @ K.T
        uv = np.zeros((len(points), 2), dtype=np.float64)
        uv[front] = uvw[front, :2] / uvw[front, 2:3]
        h, w = rgb.shape[:2]
        inside = front & (uv[:, 0] >= 0) & (uv[:, 0] < w - 1) & (uv[:, 1] >= 0) & (uv[:, 1] < h - 1)
        camera_center_local = -w2c[:3, :3].T @ w2c[:3, 3]
        view_vector = camera_center_local[None, :] - local
        view_vector /= np.maximum(np.linalg.norm(view_vector, axis=1, keepdims=True), 1e-12)
        incidence = np.abs(np.sum(normals * view_vector, axis=1))
        inside &= incidence >= float(cfg["minimum_incidence_cosine"])
        candidate = np.flatnonzero(inside)
        if not len(candidate):
            continue
        pixel_x = np.rint(uv[candidate, 0]).astype(int)
        pixel_y = np.rint(uv[candidate, 1]).astype(int)
        packed = pixel_y * w + pixel_x
        zbuffer = np.full(h * w, np.inf, dtype=np.float64)
        np.minimum.at(zbuffer, packed, camera[candidate, 2])
        visible = camera[candidate, 2] <= zbuffer[packed] + float(cfg["self_zbuffer_tolerance_m"])
        selected = candidate[visible]
        if not len(selected):
            continue
        depth_confirmed = np.zeros(len(selected), dtype=bool)
        if "depth" in sample:
            depth = sample["depth"].numpy()
            depth_mask = sample["depth_mask"].numpy()
            sx = np.rint(uv[selected, 0]).astype(int)
            sy = np.rint(uv[selected, 1]).astype(int)
            valid_depth = depth_mask[sy, sx]
            difference = np.abs(depth[sy, sx] - camera[selected, 2])
            depth_confirmed = valid_depth & (difference <= float(cfg["mvs_depth_occlusion_tolerance_m"]))
            behind = valid_depth & (camera[selected, 2] > depth[sy, sx] + float(cfg["mvs_depth_occlusion_tolerance_m"]))
            selected = selected[~behind]
            depth_confirmed = depth_confirmed[~behind]
        if not len(selected):
            continue
        sampled = _bilinear(rgb, uv[selected])
        weight = np.maximum(incidence[selected], 1e-6) ** 2
        color_sum[selected] += sampled * weight[:, None]
        weight_sum[selected] += weight
        view_count[selected] += 1
        depth_confirmed_count[selected] += depth_confirmed.astype(np.uint16)
        used_views.append(str(frame.name))
    rgba = np.tile(np.asarray(cfg["unobserved_rgba"], dtype=np.uint8), (resolution * resolution, 1))
    support = np.zeros(resolution * resolution, dtype=np.uint16)
    observed = weight_sum > 0
    rgb8 = np.rint(np.clip(color_sum[observed] / weight_sum[observed, None], 0, 1) * 255).astype(np.uint8)
    rgba[atlas_index[observed], :3] = rgb8
    rgba[atlas_index[observed], 3] = 255
    support[atlas_index] = view_count
    rgba = rgba.reshape(resolution, resolution, 4)
    support = support.reshape(resolution, resolution)
    maximum_support = int(np.max(view_count)) if len(view_count) else 0
    return rgba, support, roof_mesh, {
        "surface_texel_count": int(len(points)),
        "observed_texel_count": int(np.count_nonzero(observed)),
        "observed_surface_texel_fraction": float(np.mean(observed)) if len(observed) else 0.0,
        "depth_confirmed_texel_count": int(np.count_nonzero(depth_confirmed_count > 0)),
        "maximum_supporting_view_count": maximum_support,
        "source_triangle_count": int(len(np.asarray(mesh.triangles))),
        "textured_roof_triangle_count": int(len(np.asarray(roof_mesh.triangles))),
        "excluded_non_top_triangle_count": int(len(np.asarray(mesh.triangles)) - len(np.asarray(roof_mesh.triangles))),
        "top_surface_filter": "TOP_DOWN_VISIBLE_TRIANGLES_WITHIN_PADDED_GT_FOOTPRINT_ATLAS",
        "used_view_names": sorted(set(used_views)),
        "texture_claim": "CURRENT_RGB_MULTI_VIEW_PLANAR_UV_ROOF_TEXTURE",
        "wall_texture_created": False,
        "unobserved_texels_inpainted": False,
        "scientific_verdict": None,
    }


def _obj_bytes(mesh: o3d.geometry.TriangleMesh, bounds: tuple[float, float, float, float], mtl_name: str) -> bytes:
    vertices = np.asarray(mesh.vertices)
    normals = np.asarray(mesh.vertex_normals)
    if len(normals) != len(vertices):
        mesh.compute_vertex_normals(); normals = np.asarray(mesh.vertex_normals)
    uv = _uv(vertices, bounds)
    faces = np.asarray(mesh.triangles, dtype=np.int64) + 1
    lines = [f"mtllib {mtl_name}", "usemtl roof_texture"]
    lines.extend(f"v {x:.9f} {y:.9f} {z:.9f}" for x, y, z in vertices)
    lines.extend(f"vt {u:.9f} {v:.9f}" for u, v in uv)
    lines.extend(f"vn {x:.8f} {y:.8f} {z:.8f}" for x, y, z in normals)
    lines.extend(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}" for a, b, c in faces)
    return ("\n".join(lines) + "\n").encode("ascii")


def _hybrid_obj_bytes(mesh: o3d.geometry.TriangleMesh, roof_face_count: int, bounds: tuple[float, float, float, float], mtl_name: str) -> bytes:
    vertices=np.asarray(mesh.vertices); normals=np.asarray(mesh.vertex_normals)
    if len(normals)!=len(vertices): mesh.compute_vertex_normals(); normals=np.asarray(mesh.vertex_normals)
    uv=_uv(vertices,bounds); faces=np.asarray(mesh.triangles,dtype=np.int64)+1
    lines=[f"mtllib {mtl_name}"]
    lines.extend(f"v {x:.9f} {y:.9f} {z:.9f}" for x,y,z in vertices); lines.extend(f"vt {u:.9f} {v:.9f}" for u,v in uv); lines.extend(f"vn {x:.8f} {y:.8f} {z:.8f}" for x,y,z in normals)
    lines.append("usemtl observed_roof_texture"); lines.extend(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}" for a,b,c in faces[:roof_face_count])
    lines.append("usemtl gt_footprint_display_wall"); lines.extend(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}" for a,b,c in faces[roof_face_count:])
    return ("\n".join(lines)+"\n").encode("ascii")


def _atlas_face_colors(mesh: o3d.geometry.TriangleMesh, bounds: tuple[float, float, float, float], rgba: np.ndarray, support: np.ndarray, mode: str, roof_face_count: int | None = None, wall_color: Sequence[float] = (0.62,0.65,0.68)) -> np.ndarray:
    vertices = np.asarray(mesh.vertices); faces = np.asarray(mesh.triangles)
    center = vertices[faces].mean(axis=1)
    uv = _uv(center, bounds)
    h, w = rgba.shape[:2]
    x = np.clip(np.rint(uv[:, 0] * (w - 1)).astype(int), 0, w - 1)
    y = np.clip(np.rint((1 - uv[:, 1]) * (h - 1)).astype(int), 0, h - 1)
    if mode == "TEXTURE":
        colors = rgba[y, x, :3].astype(np.float64) / 255.0
        colors[rgba[y, x, 3] == 0] = np.asarray([0.55, 0.55, 0.55])
        if roof_face_count is not None: colors[roof_face_count:]=np.asarray(wall_color)
        return colors
    values = support[y, x].astype(np.float64)
    maximum = float(np.max(values)) if len(values) else 0.0
    normalized = values / max(maximum, 1.0)
    colors = plt.get_cmap("plasma")(normalized)[:, :3]
    colors[values == 0] = np.asarray([0.55, 0.55, 0.55])
    if roof_face_count is not None: colors[roof_face_count:]=np.asarray(wall_color)
    return colors


def _panel(path: Path, *, mesh: o3d.geometry.TriangleMesh, reference: Any, view: str, ground_z: float, zlim: tuple[float, float], bounds: tuple[float, float, float, float], rgba: np.ndarray, support: np.ndarray, mode: str, title: str, roof_face_count: int | None = None, wall_color: Sequence[float] = (0.62,0.65,0.68)) -> None:
    vertices = np.asarray(mesh.vertices); triangles = np.asarray(mesh.triangles)
    colors = _atlas_face_colors(mesh, bounds, rgba, support, mode, roof_face_count, wall_color)
    # These roof meshes are at most a few hundred thousand faces.  Thinning
    # them creates false white holes in TSDF previews, so render every face.
    stride = 1
    faces = vertices[triangles[::stride]]; face_colors = colors[::stride]
    figure = plt.figure(figsize=(6.4, 4.8), dpi=150)
    ax = figure.add_subplot(111, projection="3d", proj_type="ortho") if view.startswith("OBLIQUE") else figure.add_subplot(111)
    if view == "TOP":
        ax.add_collection(PolyCollection(faces[:, :, :2], facecolors=face_colors, edgecolors="none"))
    elif view.startswith("OBLIQUE"):
        ax.add_collection3d(Poly3DCollection(faces, facecolors=face_colors, edgecolors="none"))
    else:
        center, axis, cross = _principal_frame(reference); local = faces[:, :, :2] - center
        band = max(min(np.ptp((vertices[:, :2] - center) @ cross) * 0.08, 1.5), 0.6)
        selected = (np.min(local @ cross, axis=1) <= band) & (np.max(local @ cross, axis=1) >= -band)
        section = np.stack((local[selected] @ axis, faces[selected, :, 2]), axis=2)
        if len(section): ax.add_collection(PolyCollection(section, facecolors=face_colors[selected], edgecolors="none"))
    _draw_footprint(ax, reference, view, ground_z); _setup_axes(ax, reference, zlim, view)
    ax.set_title(title, fontsize=10.5, fontweight="bold")
    note = "current RGB roof texture; neutral wall=DISPLAY-ONLY GT FOOTPRINT, untextured" if mode == "TEXTURE" else "roof view support; neutral wall=DISPLAY-ONLY GT FOOTPRINT, not evidence"
    figure.text(0.02, 0.018, note, fontsize=7.2, bbox={"facecolor":"white","edgecolor":"#999","alpha":0.88,"pad":3})
    figure.tight_layout(rect=(0, 0.10, 1, 1)); path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, metadata={"Software":"JointBuildGS roof texture bake renderer"}); plt.close(figure)


def _sheet(path: Path, stable_id: str, rows: Sequence[tuple[str, Sequence[Path]]]) -> None:
    cell_w, cell_h, label_w, header_h = 960, 720, 330, 120
    canvas = np.full((header_h + len(rows)*cell_h, label_w + 8*cell_w, 3), 255, np.uint8)
    cv2.putText(canvas, stable_id, (22,43), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (20,20,20), 2, cv2.LINE_AA)
    cv2.putText(canvas, "roof-only current RGB texture | gray=unobserved | scientific_verdict=null", (22,87), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (55,55,55), 1, cv2.LINE_AA)
    for block,label in enumerate(("C3-1 SEMANTIC","C3-2 SEMANTIC + DEPTH")):
        cv2.putText(canvas,label,(label_w+block*4*cell_w+20,32),cv2.FONT_HERSHEY_SIMPLEX,0.67,(80,40,30),2,cv2.LINE_AA)
        for column,view in enumerate(VIEWS): cv2.putText(canvas,view,(label_w+(block*4+column)*cell_w+18,88),cv2.FONT_HERSHEY_SIMPLEX,0.65,(20,20,20),2,cv2.LINE_AA)
    for row_index,(label,paths) in enumerate(rows):
        y0=header_h+row_index*cell_h; cv2.rectangle(canvas,(0,y0),(label_w,y0+cell_h),(242,244,247),-1)
        for li,line in enumerate(label.split("\n")): cv2.putText(canvas,line,(18,y0+55+li*32),cv2.FONT_HERSHEY_SIMPLEX,0.58,(25,25,25),1,cv2.LINE_AA)
        for column,panel in enumerate(paths):
            image=cv2.imread(str(panel));
            if image is None: raise RuntimeError(f"panel unreadable: {panel}")
            image=cv2.resize(image,(cell_w,cell_h),interpolation=cv2.INTER_AREA); x0=label_w+column*cell_w; canvas[y0:y0+cell_h,x0:x0+cell_w]=image
    ok,encoded=cv2.imencode(".png",canvas)
    if not ok: raise RuntimeError("sheet encode failed")
    write_new(path,encoded.tobytes())


def _records(root: Path) -> list[dict[str, Any]]:
    excluded={"control/artifact_manifest_v1.json","control/technical_return_v1.json","control/200-verified.local_v1.json","control/300-closed.local_v1.json"}
    return [file_record(p,root) for p in sorted(root.rglob("*")) if p.is_file() and p.relative_to(root).as_posix() not in excluded]


def run(output_root: Path, artifact_root: Path, repo_root: Path, source_commit: str) -> dict[str, Any]:
    config=load_config(); validate_config(config)
    mesh_root=resolve_artifact(artifact_root,config["source"]["mesh_relative_root"],"mesh root"); data_root=resolve_artifact(artifact_root,config["source"]["colmap_relative_root"],"COLMAP"); v13_root=resolve_artifact(artifact_root,config["source"]["v13_relative_root"],"v13 context"); lod2=resolve_artifact(artifact_root,config["source"]["lod2_relative_path"],"LoD2")
    plan=json.loads(resolve_artifact(artifact_root,config["source"]["shared_view_plan_relative_path"],"shared view plan").read_text())["plan"]; references=load_building_references(lod2,config["scope"]["building_ids"])
    dataset=ColmapDataset(data_root,downscale=float(config["texture"]["image_downscale"]),load_depth=True,load_normal=False,load_semantic=False,visible_views=_visible_names(config,repo_root)); frame_by_name={frame.name:(index,frame) for index,frame in enumerate(dataset.frames)}
    texture_records=[]; wall_records=[]; cases=[]; wall_color=tuple(float(value) for value in config["hybrid"]["wall_color_rgb"])
    for stable_id in config["scope"]["building_ids"]:
        reference=references[stable_id]; pad=float(config["texture"]["atlas_footprint_padding_m"]); bounds=reference.footprint.buffer(pad).bounds; ground_z,ground_policy=_ground_z(config,artifact_root,v13_root,stable_id)
        view_rows=plan[stable_id][:int(config["texture"]["maximum_views_per_building"])]; frames=[(frame_by_name[row["name"]][1],dataset[frame_by_name[row["name"]][0]]) for row in view_rows]
        context_paths=[]; context_records=[]
        for index,view in enumerate(VIEWS,1):
            source=v13_root/f"qualitative/c3/comparison/{stable_id}/panels/01_rgb_roofline_{index}.png"; destination=output_root/f"qualitative/{stable_id}/panels/context_current_rgb_2022_roofline_{view.lower()}.png"; write_new(destination,source.read_bytes()); context_paths.append(destination); context_records.append({"view":view,"source":file_record(source,v13_root),"copy":file_record(destination,output_root)})
        outputs={}; zvalues=[ground_z]
        for condition in config["scope"]["condition_ids"]:
            for method in config["scope"]["mesh_methods"]:
                source_path=_mesh_path(mesh_root,condition,stable_id,method); mesh=o3d.io.read_triangle_mesh(str(source_path)); mesh.compute_vertex_normals(); zvalues.extend(np.asarray(mesh.vertices)[:,2].tolist()); rgba,support,roof_mesh,receipt=_bake_texture(mesh,bounds,frames,config)
                hybrid,roof_face_count,wall_receipt=_display_wall_hybrid(roof_mesh,reference.footprint,ground_z,float(config["hybrid"]["boundary_sample_spacing_m"]),int(config["hybrid"]["nearest_roof_vertex_count"]),float(config["hybrid"]["minimum_wall_height_m"]))
                root=output_root/f"textures/{condition}/{stable_id}/{method.lower()}"; texture_path=root/"roof_texture_current_rgb_v1.png"; support_path=root/"roof_texture_view_support_v1.png"; root.mkdir(parents=True,exist_ok=True)
                ok,encoded=cv2.imencode(".png",cv2.cvtColor(rgba,cv2.COLOR_RGBA2BGRA));
                if not ok: raise RuntimeError("texture encode failed")
                write_new(texture_path,encoded.tobytes()); max_support=max(int(np.max(support)),1); support_rgb=np.rint(plt.get_cmap("plasma")(support/max_support)*255).astype(np.uint8); support_rgb[support==0]=np.asarray([140,140,140,255],np.uint8); ok,encoded=cv2.imencode(".png",cv2.cvtColor(support_rgb,cv2.COLOR_RGBA2BGRA));
                if not ok: raise RuntimeError("support encode failed")
                write_new(support_path,encoded.tobytes()); obj_path=root/"roof_textured_v1.obj"; mtl_path=root/"roof_textured_v1.mtl"; write_new(obj_path,_obj_bytes(roof_mesh,bounds,mtl_path.name)); write_new(mtl_path,b"newmtl roof_texture\nKd 1 1 1\nmap_Kd roof_texture_current_rgb_v1.png\n")
                hybrid_obj=root/"roof_textured_gt_footprint_display_wall_v1.obj"; hybrid_mtl=root/"roof_textured_gt_footprint_display_wall_v1.mtl"; write_new(hybrid_obj,_hybrid_obj_bytes(hybrid,roof_face_count,bounds,hybrid_mtl.name)); wall_rgb=" ".join(f"{value:.4f}" for value in wall_color); write_new(hybrid_mtl,(f"newmtl observed_roof_texture\nKd 1 1 1\nmap_Kd roof_texture_current_rgb_v1.png\nnewmtl gt_footprint_display_wall\nKd {wall_rgb}\n").encode("ascii"))
                wall_receipt.update({"condition_id":condition,"stable_id":stable_id,"mesh_method":method,"ground_policy":ground_policy,"hybrid_obj":file_record(hybrid_obj,output_root),"hybrid_mtl":file_record(hybrid_mtl,output_root),"wall_color_rgb":list(wall_color)}); wall_records.append(wall_receipt)
                receipt.update({"schema":"jointbuildgs.c3_roof_texture_bake_record.v1","condition_id":condition,"stable_id":stable_id,"mesh_method":method,"source_mesh":file_record(source_path,mesh_root),"texture":file_record(texture_path,output_root),"support":file_record(support_path,output_root),"obj":file_record(obj_path,output_root),"mtl":file_record(mtl_path,output_root),"display_wall":wall_receipt,"uv_bounds_epsg25832":list(map(float,bounds)),"gt_footprint_xy_used_for_atlas_bounds":True,"source_mesh_reconstructed":False,"textured_output_is_top_surface_subset":True}); receipt_path=root/"roof_texture_receipt_v1.json"; write_new(receipt_path,canonical_json_bytes(receipt)); texture_records.append(receipt); outputs[(condition,method)]=(hybrid,roof_face_count,rgba,support)
        zlim=(float(min(ground_z-1.0,np.quantile(zvalues,0.001)-1.5)),float(np.quantile(zvalues,0.999)+1.5)); rows=[("2024 RGB + 2022 ROOFLINE\nPROJECTION CONTEXT",context_paths+context_paths)]; panels=[record["copy"] for record in context_records]
        for method in config["scope"]["mesh_methods"]:
            for mode in ("TEXTURE","SUPPORT"):
                paths=[]
                for condition in config["scope"]["condition_ids"]:
                    hybrid,roof_face_count,rgba,support=outputs[(condition,method)]
                    for view in VIEWS:
                        path=output_root/f"qualitative/{stable_id}/panels/{method.lower()}_{mode.lower()}_{condition}_{view.lower()}.png"; _panel(path,mesh=hybrid,reference=reference,view=view,ground_z=ground_z,zlim=zlim,bounds=bounds,rgba=rgba,support=support,mode=mode,title=f"{condition} | {method} | TEXTURED ROOF + GT DISPLAY WALL | {mode} | {view}",roof_face_count=roof_face_count,wall_color=wall_color); paths.append(path); panels.append(file_record(path,output_root))
                rows.append((f"{method}\n{mode}",paths))
        sheet=output_root/f"qualitative/{stable_id}/case_sheet_roof_texture_v1.png"; _sheet(sheet,stable_id,rows); cases.append({"stable_id":stable_id,"row_count":5,"column_count":8,"panel_count":40,"unique_panel_png_count":len(panels),"context":context_records,"case_sheet":file_record(sheet,output_root),"panels":panels})
    counters={"gs_training_invocations":0,"checkpoint_render_extractions":0,"poisson_reconstructions":0,"tsdf_reconstructions":0,"roof_texture_bakes":len(texture_records),"display_only_gt_footprint_wall_assemblies":len(wall_records),"roofer_invocations":0,"g2_invocations":0,"metric_recomputations":0,"c4_c5_accesses":0}
    index={"schema":"jointbuildgs.c3_roof_texture_bake_index.v1","status":"COMPLETE_CURRENT_RGB_ROOF_TEXTURES_WITH_CONTEXT_AND_DISPLAY_WALL","source_commit":source_commit,"case_count":3,"texture_bake_count":len(texture_records),"display_only_wall_assembly_count":len(wall_records),"panel_count":sum(c["panel_count"] for c in cases),"unique_panel_png_count":sum(c["unique_panel_png_count"] for c in cases),"cases":cases,"execution_counters":counters,"official_G3_G4_PASS_usable":None,"scientific_verdict":None}; write_new(output_root/"qualitative/index_v1.json",canonical_json_bytes(index))
    report="# C3 roof texture + projection context + display-only wall\n\n맨 위 행은 이전에 봉인된 2024 RGB + 2022 roofline 투영이다. Poisson/TSDF roof에는 exact current RGB texture를 적용했다. GT footprint wall은 형상을 읽기 위한 중립 회색 display-only geometry이며 texture, ground cap, honest Stage-3 output 또는 official metric input이 아니다.\n"; write_new(output_root/"reports/technical_report_ko_v1.md",report.encode("utf-8")); links="".join(f'<section><h2>{html.escape(c["stable_id"])}</h2><a href="../{c["case_sheet"]["path"]}"><img src="../{c["case_sheet"]["path"]}"></a></section>' for c in cases); write_new(output_root/"reports/case_index.html",("<!doctype html><meta charset=utf-8><style>img{width:100%}</style><h1>C3 roof texture context hybrid</h1>"+links).encode())
    returned={"schema":"jointbuildgs.c3_roof_texture_bake_technical_return.v1","status":"RETURNED_LOCAL_COMPLETE_ROOF_TEXTURE_CONTEXT_HYBRID_DIAGNOSTIC","source_commit":source_commit,"generated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"case_count":3,"texture_bake_count":12,"display_only_wall_assembly_count":12,"panel_count":index["panel_count"],"execution_counters":counters,"official_G3_G4_PASS_usable":None,"scientific_verdict":None}; write_new(output_root/"control/technical_return_v1.json",canonical_json_bytes(returned)); manifest={"schema":"jointbuildgs.c3_roof_texture_bake_artifact_manifest.v1","status":"COMPLETE_HASHED_MATERIAL_PAYLOAD","source_commit":source_commit,"records":_records(output_root),"scientific_verdict":None}; manifest["record_count"]=len(manifest["records"]); write_new(output_root/"control/artifact_manifest_v1.json",canonical_json_bytes(manifest))
    checks={"case_count_3":len(cases)==3,"texture_bakes_12":len(texture_records)==12,"display_walls_12":len(wall_records)==12,"panels_120":index["panel_count"]==120,"context_hashes_copied":all(row["source"]["sha256"]==row["copy"]["sha256"] for case in cases for row in case["context"]),"walls_untextured":all(not row["wall_texture_created"] for row in wall_records),"walls_not_honest_or_metric":all(not row["honest_stage3_output"] and not row["official_metric_input"] for row in wall_records),"no_inpainting":all(not row["unobserved_texels_inpainted"] for row in texture_records),"prohibited_counters_zero":all(counters[key]==0 for key in ("gs_training_invocations","checkpoint_render_extractions","poisson_reconstructions","tsdf_reconstructions","roofer_invocations","g2_invocations","metric_recomputations","c4_c5_accesses")),"scientific_verdict_null":index["scientific_verdict"] is None}; verified={"schema":"jointbuildgs.local_technical_200_verified.v1","status":"200-VERIFIED_LOCAL_SELF_CHECK","checks":checks,"manifest":file_record(output_root/"control/artifact_manifest_v1.json",output_root),"scientific_verdict":None}
    if not all(checks.values()): raise RuntimeError("roof texture context hybrid verification failed")
    write_new(output_root/"control/200-verified.local_v1.json",canonical_json_bytes(verified)); closed={"schema":"jointbuildgs.local_technical_300_closed.v1","status":"300-CLOSED_LOCAL_ROOF_TEXTURE_CONTEXT_HYBRID_DIAGNOSTIC","technical_return":file_record(output_root/"control/technical_return_v1.json",output_root),"verified":file_record(output_root/"control/200-verified.local_v1.json",output_root),"manifest":file_record(output_root/"control/artifact_manifest_v1.json",output_root),"official_G3_G4_PASS_usable":None,"scientific_verdict":None}; write_new(output_root/"control/300-closed.local_v1.json",canonical_json_bytes(closed)); return closed


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--output-root",type=Path,required=True); parser.add_argument("--artifact-root",type=Path,required=True); parser.add_argument("--repo-root",type=Path,required=True); parser.add_argument("--source-commit",required=True); args=parser.parse_args(); print(json.dumps(run(args.output_root,args.artifact_root,args.repo_root,args.source_commit),ensure_ascii=False,sort_keys=True))


if __name__ == "__main__": main()

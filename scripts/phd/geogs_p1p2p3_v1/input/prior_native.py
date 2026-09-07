"""Official GeoGS ALS input preparation with an audited nearest-ray correction.

Official sampling, pose projection, observation limits and point assembly remain
callable source functions. The source's broken Scene.ray -> always-visible fallback
is replaced explicitly by cached nearest intersections against the same mesh.
Only train-camera metadata is used for visibility and prior depth generation.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import sys
import time
import traceback

import numpy as np

from .prepare import require_isolation, sha, record, write_json


def official_module(source):
    sys.path.insert(0, str(source))
    sys.path.insert(0, str(source / "data"))
    spec = importlib.util.spec_from_file_location("geogs_official_generate_pcd", source / "data/generate_pcd.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VisibilityCache:
    def __init__(self, vertices, faces, points, cameras, images, tolerance, output):
        import open3d as o3d
        from LoD2Depth.camera_loader import quaternion_to_rotation_matrix
        from LoD2Depth.raycasting import create_mesh_scene
        self.scene = create_mesh_scene(vertices, faces)
        self.points = {tuple(point): index for index, point in enumerate(points)}
        self.origins = {}
        self.visible = np.zeros((len(images), len(points)), dtype=bool)
        self.calls = 0
        self.rows = []
        for row, (image_id, pose) in enumerate(images.items()):
            R = quaternion_to_rotation_matrix(pose.qvec)
            origin = -R.T @ np.asarray(pose.tvec)
            self.origins[tuple(origin)] = row
            rays = points - origin
            expected = np.linalg.norm(rays, axis=1)
            directions = rays / expected[:, None]
            inputs = np.concatenate([np.broadcast_to(origin, points.shape), directions], axis=1).astype(np.float32)
            result = self.scene.cast_rays(o3d.core.Tensor(inputs))
            hit = result["t_hit"].numpy()
            residual = np.abs(hit-expected)
            self.visible[row] = np.isfinite(hit) & (residual < tolerance)
            self.rows.append(dict(image_id=int(image_id), visible=int(self.visible[row].sum()),
                near_tolerance_boundary_count=int((np.abs(residual-tolerance)<1e-5).sum()),
                finite_nearest_hits=int(np.isfinite(hit).sum())))
        np.save(output / "visibility_cache.npy", self.visible, allow_pickle=False)
        write_json(output / "visibility_cache_manifest.json", dict(rows=self.rows,
            sample_order="official sample_points_from_mesh order", tolerance_m=tolerance,
            algorithm="Float32 nearest-hit Open3D rays against unchanged ALS mesh; Euclidean ray distance comparison, not camera-Z depth.",
            evaluation_images_used=False, scientific_verdict=None))

    def query(self, scene, point, camera_position, camera_direction):
        self.calls += 1
        return bool(self.visible[self.origins[tuple(camera_position)], self.points[tuple(point)]])


def visibility_fixture():
    import open3d as o3d
    from LoD2Depth.raycasting import create_mesh_scene
    vertices=np.array([[-2.,-2.,2.],[2.,-2.,2.],[2.,2.,2.],[-2.,2.,2.]])
    scene=create_mesh_scene(vertices,np.array([[0,1,2],[0,2,3]]))
    points=np.array([[0.,0.,2.],[0.,0.,5.],[1.,0.,2.]])
    distance=np.linalg.norm(points,axis=1)
    rays=np.concatenate([np.zeros_like(points),points/distance[:,None]],axis=1).astype(np.float32)
    hit=scene.cast_rays(o3d.core.Tensor(rays))["t_hit"].numpy()
    actual=np.isfinite(hit)&(np.abs(hit-distance)<.05)
    if actual.tolist()!=[True,False,True]:
        raise RuntimeError("Nearest-ray occluder fixture failed")
    return dict(status="PASS", visible=actual.tolist(), expected=[True,False,True],
                meaning="Near surface visible, same ray far point occluded, off-axis near point visible")


def init_points(cfg, source, scene, surface, output):
    from plyfile import PlyData, PlyElement
    module=official_module(source)
    policy=cfg["initialization"]
    if policy["color_rgb"] != [128,128,128]:
        raise ValueError("Official initialization uses gray128")
    np.random.seed(cfg["seed"])
    random.seed(cfg["seed"])
    _,vertices,faces,_,_=module.load_and_transform_mesh(str(surface/"als_surface.obj"),
        str(scene/"scene_reference_frame.json"),policy["additional_z_offset_m"])
    cameras=module.load_cameras(str(scene/"train_sparse_txt/cameras.txt"))
    train_images=module.load_images(str(scene/"train_sparse_txt/images.txt"))
    full_images=module.load_images(str(scene/"sparse_txt/images.txt"))
    split=json.loads((scene/"split_manifest.json").read_text())
    expected_train={view["image_id"] for view in split["train"]}
    if set(train_images)!=expected_train or set(full_images)!={view["image_id"] for view in split["all"]}:
        raise ValueError("Prior initialization camera split changed")
    fixture=visibility_fixture()
    samples,face_indices=module.sample_points_from_mesh(vertices,faces,policy["num_points"])
    np.savez_compressed(output/"all_surface_samples.npz",xyz=samples,official_face_indices=face_indices)
    visibility=VisibilityCache(vertices,faces,samples,cameras,train_images,
                               policy["visibility_tolerance_m"],output)
    module.is_point_visible_from_camera=visibility.query
    def fail_closed(*args,**kwargs):
        raise RuntimeError("Official visibility fallback attempted after nearest-ray correction")
    module.is_point_visible_fallback=fail_closed
    point_cloud=module.generate_point_cloud(vertices,faces,samples,face_indices,cameras,train_images,
        policy["min_observations"],policy["max_observations"])
    if not point_cloud:
        raise RuntimeError("Official initialization produced no visible points")
    sparse=output/"sparse_lod/0"
    sparse.mkdir(parents=True)
    module.write_points3D_file(point_cloud,str(sparse/"points3D.txt"))
    module.update_images_with_points2D(full_images,point_cloud,str(sparse/"images.txt"))
    shutil.copyfile(scene/"sparse_txt/cameras.txt",sparse/"cameras.txt")
    # Native readColmapSceneInfo reads xyz/rgb/normals from PLY, ignoring tracks.
    xyz=np.asarray([point["xyz"] for point in point_cloud],dtype=np.float64)
    data=np.empty(len(xyz),dtype=[("x","<f4"),("y","<f4"),("z","<f4"),
        ("nx","<f4"),("ny","<f4"),("nz","<f4"),("red","u1"),("green","u1"),("blue","u1")])
    for i,name in enumerate(("x","y","z")):data[name]=xyz[:,i]
    for name in ("nx","ny","nz"):data[name]=0.
    for name in ("red","green","blue"):data[name]=128
    PlyData([PlyElement.describe(data,"vertex")],text=False,byte_order="<").write(str(sparse/"points3D.ply"))
    shutil.copyfile(sparse/"points3D.ply",output/"lod2_pcd.ply")
    np.save(output/"retained_sample_ids.npy",np.asarray([point["id"] for point in point_cloud],dtype=np.int64))
    return dict(status="OFFICIAL_INITIALIZATION_WITH_EXPLICIT_VISIBLE_RAY_CORRECTION", counts=dict(
        sampled=len(samples),retained=len(point_cloud),not_retained=len(samples)-len(point_cloud),train_views=len(train_images),
        visibility_queries=visibility.calls), visibility_fixture=fixture,
        original_functions=["sample_points_from_mesh","generate_point_cloud","write_points3D_file","update_images_with_points2D"],
        deviations=["Broken source Scene.ray fallback replaced with batched cached nearest intersections; fallback is fatal.",
                    "Initialization visibility uses train poses only; full sparse_lod includes evaluation poses without evaluation pixel reads.",
                    "Protection PLY is exactly the same visibility-retained sample PLY as initialization, not all100000 raw sampled points."],
        original_default_protection_pointcloud_recipe="Official public example supplies lod2_pcd.ply, but repository does not generate its provenance; equality to visible initialization is an explicit ALS adaptation choice.",
        semantic_building_flag="Proximity to ALS-derived surface, including context ground/other returns; not semantic building GT.",
        transform_z_offset_m=policy["additional_z_offset_m"], protection_matches_initialization_bytes=
        sha(output/"lod2_pcd.ply")==sha(sparse/"points3D.ply"), voxel_downsampling_applied=False)


def depth_maps(cfg,source,scene,surface,output):
    module=official_module(source)
    from LoD2Depth.raycasting import create_mesh_scene,generate_depth_normal_maps
    _,vertices,faces,_,_=module.load_and_transform_mesh(str(surface/"als_surface.obj"),
        str(scene/"scene_reference_frame.json"),cfg["initialization"]["additional_z_offset_m"])
    cameras=module.load_cameras(str(scene/"train_sparse_txt/cameras.txt"))
    images=module.load_images(str(scene/"train_sparse_txt/images.txt"))
    split=json.loads((scene/"split_manifest.json").read_text())
    if set(images)!={view["image_id"] for view in split["train"]}:
        raise ValueError("Depth camera split changed")
    mesh_scene=create_mesh_scene(vertices,faces)
    raw=output/"raw_depth"
    raw.mkdir()
    rows=[]
    for image_id,pose in images.items():
        camera=cameras[pose.camera_id]
        K=module.get_camera_intrinsics(camera)
        E=module.get_camera_extrinsics(pose)
        depth,_,_=generate_depth_normal_maps(mesh_scene,K,E,camera.width,camera.height)
        valid=np.isfinite(depth)&(depth>0)
        # Preserve official helper values (including inf/NaN misses); training's finite-positive mask excludes them.
        path=raw/(Path(pose.name).stem+".npy")
        np.save(path,depth.astype(np.float32),allow_pickle=False)
        rows.append(dict(image_id=int(image_id),name=pose.name,valid_pixels=int(valid.sum()),
                         total_pixels=int(depth.size),depth_min_m=float(depth[valid].min()) if valid.any() else None,
                         depth_max_m=float(depth[valid].max()) if valid.any() else None,sha256=sha(path)))
        print(json.dumps({"depth_image":pose.name,"valid_pixels":int(valid.sum())}),flush=True)
    return dict(status="OFFICIAL_RAYCAST_ALS_DEPTH_TRAIN_VIEWS_ONLY",rows=rows,
        depth_frame="CAMERA_Z_METERS",pixel_center="Original Open3D pinhole helper u+0.5,v+0.5; source K retained.",
        no_hit="Original finite-positive training mask; no filling or extrapolation.",
        evaluation_views_missing_by_design=True,voxel_downsampling_applied=False)


def run(args):
    started=time.monotonic()
    isolation=require_isolation()
    cfg=json.loads(args.config.read_text())
    if args.output.exists() and any(args.output.iterdir()):raise FileExistsError(args.output)
    args.output.mkdir(parents=True,exist_ok=True)
    try:
        result=(init_points if args.stage=="initialization" else depth_maps)(cfg,args.source,args.scene,args.surface,args.output)
        result.update(scientific_verdict=None,reference_paths_absent=isolation,evaluation_rgb_accessed=False,
            config=record(args.config),seed=cfg["seed"],frame=cfg["crs"],elapsed_seconds=time.monotonic()-started,
            inputs={"surface_receipt":record(args.surface/"surface_receipt.json"),"surface_mesh":record(args.surface/"als_surface.obj"),
                    "split_manifest":record(args.scene/"split_manifest.json")},
            official_source={str(path.relative_to(args.source)):record(path) for path in [args.source/"data/generate_pcd.py",args.source/"LoD2Depth/raycasting.py"]},
            outputs={str(path.relative_to(args.output)):record(path) for path in args.output.rglob("*") if path.is_file()},
            command=sys.argv,source_sha256=sha(__file__),image_id=os.environ.get("JBGS_CONTAINER_IMAGE_ID"))
        write_json(args.output/"receipt.json",result)
        print(json.dumps({"status":result["status"],"counts":result.get("counts"),"depth_views":len(result.get("rows",[]))}),flush=True)
    except Exception:
        write_json(args.output/"failure.json",dict(status="FAILED",scientific_verdict=None,traceback=traceback.format_exc(),
            elapsed_seconds=time.monotonic()-started,command=sys.argv,source_sha256=sha(__file__)))
        raise


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,required=True)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--scene",type=Path,required=True)
    parser.add_argument("--surface",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--stage",choices=("initialization","depth"),required=True)
    run(parser.parse_args())

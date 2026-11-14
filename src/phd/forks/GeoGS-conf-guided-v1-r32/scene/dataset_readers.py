#
# Copyright (C) 2023, Inria
# GRAPHDECO research group, https://team.inria.fr/graphdeco
# All rights reserved.
#
# This software is free for non-commercial, research and evaluation use 
# under the terms of the LICENSE.md file.
#
# For inquiries contact  george.drettakis@inria.fr
#

import os
import sys
from PIL import Image
import matplotlib.pyplot as plt
from typing import NamedTuple
from scene.colmap_loader import read_extrinsics_text, read_intrinsics_text, qvec2rotmat, \
    read_extrinsics_binary, read_intrinsics_binary, read_points3D_binary, read_points3D_text
from utils.graphics_utils import getWorld2View2, focal2fov, fov2focal
import numpy as np
import json
import cv2
import torch
from pathlib import Path
from plyfile import PlyData, PlyElement
from utils.sh_utils import SH2RGB
from scene.gaussian_model import BasicPointCloud

class CameraInfo(NamedTuple):
    uid: int
    R: np.array
    T: np.array
    FovY: np.array
    FovX: np.array
    image: np.array
    image_path: str
    image_name: str
    width: int
    height: int

class SceneInfo(NamedTuple):
    point_cloud: BasicPointCloud
    train_cameras: list
    test_cameras: list
    nerf_normalization: dict
    ply_path: str
    building_depth_maps: dict = {}
    building_normal_maps: dict = {}
    building_masks: dict = {}

def loadBuildingData(path, cam_infos, boundary_tolerance=2, debug=False):
    """
    Load building depth maps and normal maps from .npy files and resize them to match RGB image size.
    Create building mask based on valid depth values (finite values are considered buildings).
    Optionally save debug images if debug=True.
    """
    depth_maps = {}
    normal_maps = {}
    masks = {}

    depth_dir = os.path.join(path, "raw_depth")
    normal_dir = os.path.join(path, "raw_normal")

    if not all(os.path.exists(d) for d in [depth_dir, normal_dir]):
        print(f"Warning: Building data directories not found in {path}")
        return depth_maps, normal_maps, masks

    print("Loading building supervision data...")

    target_width = 1600
    aspect_ratio = cam_infos[0].height / cam_infos[0].width
    target_height = int(target_width * aspect_ratio)
    target_size = (target_height, target_width)

    print(f"Will resize all building data to target size: {target_size}")

    if debug:
        debug_dir = Path("./output/debug_masks")
        debug_dir.mkdir(parents=True, exist_ok=True)

    for idx, cam in enumerate(cam_infos):
        sys.stdout.write('\r')
        sys.stdout.write(f"Loading building data {idx+1}/{len(cam_infos)}")
        sys.stdout.flush()

        image_name = cam.image_name

        depth_path = os.path.join(depth_dir, f"{image_name}.npy")
        normal_path = os.path.join(normal_dir, f"{image_name}.npy")

        if not os.path.exists(depth_path) or not os.path.exists(normal_path):
            continue

        try:
            depth = np.load(depth_path)
            normal = np.load(normal_path)

            # Create mask using valid depth values
            # Since only building areas have valid depth values
            mask = np.isfinite(depth).astype(np.float32)
            
            # Process depth map for further calculations (replace non-finite values with 0)
            depth_processed = np.nan_to_num(depth, nan=0.0, posinf=0.0, neginf=0.0)

            # Debug visualization
            if debug:

                plt.figure(figsize=(8, 8))
                plt.imshow(mask, cmap='gray')
                plt.axis('off')
                plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
                plt.savefig(debug_dir / f"{image_name}_mask.png", bbox_inches='tight', pad_inches=0)
                plt.close()

                # plt.figure(figsize=(15, 5))
                # plt.subplot(1, 2, 1)
                # plt.imshow(depth_processed, cmap='turbo')
                # plt.title(f"Depth - {image_name}")
                # plt.colorbar()

                # plt.subplot(1, 2, 2)
                # plt.imshow(mask, cmap='gray')
                # plt.title(f"Mask - {image_name}")
                # plt.colorbar()

                # plt.tight_layout()
                # plt.savefig(debug_dir / f"{image_name}_depth_mask_simple.png")
                # plt.close()

            # Resize depth and mask
            depth_processed = cv2.resize(depth_processed, (target_width, target_height), interpolation=cv2.INTER_NEAREST)
            mask = cv2.resize(mask, (target_width, target_height), interpolation=cv2.INTER_NEAREST)

            # Resize and normalize normal map
            if len(normal.shape) == 3 and normal.shape[2] == 3:
                resized_normal = np.zeros((target_height, target_width, 3))
                for c in range(3):
                    resized_normal[..., c] = cv2.resize(normal[..., c], (target_width, target_height), interpolation=cv2.INTER_LINEAR)
                norm = np.sqrt(np.sum(resized_normal**2, axis=2, keepdims=True))
                normal = resized_normal / (norm + 1e-10)
            else:
                normal = cv2.resize(normal, (target_width, target_height), interpolation=cv2.INTER_LINEAR)

            # Apply boundary dilation if required
            if boundary_tolerance > 0:
                kernel = np.ones((boundary_tolerance, boundary_tolerance), np.uint8)
                mask = cv2.dilate(mask.astype(np.uint8), kernel) > 0
                mask = mask.astype(np.float32)

            # Convert to GPU tensors
            depth_tensor = torch.from_numpy(depth_processed).float().cuda()
            mask_tensor = torch.from_numpy(mask).float().cuda()

            normal_tensor = torch.from_numpy(normal).float().cuda()
            if len(normal_tensor.shape) == 3 and normal_tensor.shape[2] == 3:
                normal_tensor = normal_tensor.permute(2, 0, 1)

            mask_coverage = mask_tensor.mean().item()
            print(f" | Mask coverage for {image_name}: {mask_coverage:.2%}")

            if mask_coverage > 0.01:
                depth_maps[image_name] = depth_tensor
                normal_maps[image_name] = normal_tensor
                masks[image_name] = mask_tensor
            else:
                print(f"\nWarning: Mask for {image_name} covers too little area ({mask_coverage:.2%}), skipping")

        except Exception as e:
            print(f"\nError loading data for {image_name}: {e}")
            import traceback
            traceback.print_exc()
            continue

    sys.stdout.write('\n')
    print(f"Loaded building data for {len(masks)} cameras")
    return depth_maps, normal_maps, masks

def loadDepthOnlyData(path, cam_infos, boundary_tolerance=2, debug=False):
    """
    Load depth-only data with automatic masking of invalid values.

    Args:
        path: Path to depth data directory (expects raw_depth/ subdirectory)
        cam_infos: Camera info list
        boundary_tolerance: Boundary tolerance for mask creation (deprecated)
        debug: Whether to save debug images

    Returns:
        depth_maps: Dictionary of depth maps
        normal_maps: Empty dictionary (not used in depth_only mode)
        masks: Empty dictionary (masking handled during training)
    """
    depth_maps = {}
    normal_maps = {}  # Empty for depth_only mode
    masks = {}  # Empty - masking handled during training

    # Always look for raw_depth/ subdirectory
    depth_dir = os.path.join(path, "raw_depth")

    if not os.path.exists(depth_dir):
        print(f"Warning: Depth directory not found: {depth_dir}")
        return depth_maps, normal_maps, masks

    print(f"Loading depth data from {depth_dir}...")

    target_width = 1600
    aspect_ratio = cam_infos[0].height / cam_infos[0].width
    target_height = int(target_width * aspect_ratio)
    target_size = (target_height, target_width)

    print(f"Will resize all depth data to target size: {target_size}")

    if debug:
        debug_dir = Path("./output/debug_depth_only")
        debug_dir.mkdir(parents=True, exist_ok=True)

    for idx, cam in enumerate(cam_infos):
        sys.stdout.write('\r')
        sys.stdout.write(f"Loading depth data {idx+1}/{len(cam_infos)}")
        sys.stdout.flush()

        image_name = cam.image_name
        depth_path = os.path.join(depth_dir, f"{image_name}.npy")

        if not os.path.exists(depth_path):
            print(f"Depth file not found: {depth_path}")
            continue

        try:
            depth = np.load(depth_path)
            print(f"Loaded depth for {image_name}: shape={depth.shape}, finite_count={np.isfinite(depth).sum()}")

            # Keep invalid values as nan/inf - masking will be done during training
            # This allows automatic filtering of invalid regions without pre-computing masks
            depth_resized = cv2.resize(depth, (target_width, target_height), interpolation=cv2.INTER_LINEAR)

            # Convert to CUDA tensor (keep nan/inf values for automatic masking)
            depth_maps[image_name] = torch.tensor(depth_resized, dtype=torch.float32, device="cuda")

            if debug:
                debug_dir = Path("./output/debug_depth_only")
                debug_dir.mkdir(parents=True, exist_ok=True)

                # Visualize depth map
                plt.figure(figsize=(8, 6))
                plt.imshow(depth_resized, cmap='turbo')
                plt.title(f"Depth - {image_name}")
                plt.colorbar()
                plt.savefig(debug_dir / f"{image_name}_depth.png")
                plt.close()

                # Visualize valid depth mask (for debugging)
                valid_mask = np.isfinite(depth_resized) & (depth_resized > 0)
                plt.figure(figsize=(8, 6))
                plt.imshow(valid_mask, cmap='gray')
                plt.title(f"Valid Depth Mask - {image_name}")
                plt.colorbar()
                plt.savefig(debug_dir / f"{image_name}_mask.png")
                plt.close()

        except Exception as e:
            print(f"\nError loading depth data for {image_name}: {e}")
            continue

    print()
    print(f"Loaded depth data for {len(depth_maps)} images")
    print("Note: Invalid values (nan/inf/0) will be automatically masked during training")

    return depth_maps, normal_maps, masks

def getNerfppNorm(cam_info):
    def get_center_and_diag(cam_centers):
        cam_centers = np.hstack(cam_centers)
        avg_cam_center = np.mean(cam_centers, axis=1, keepdims=True)
        center = avg_cam_center
        dist = np.linalg.norm(cam_centers - center, axis=0, keepdims=True)
        diagonal = np.max(dist)
        return center.flatten(), diagonal

    cam_centers = []

    for cam in cam_info:
        W2C = getWorld2View2(cam.R, cam.T)
        C2W = np.linalg.inv(W2C)
        cam_centers.append(C2W[:3, 3:4])

    center, diagonal = get_center_and_diag(cam_centers)
    radius = diagonal * 1.1

    translate = -center

    return {"translate": translate, "radius": radius}

def readColmapCameras(cam_extrinsics, cam_intrinsics, images_folder):
    cam_infos = []
    for idx, key in enumerate(cam_extrinsics):
        sys.stdout.write('\r')
        # the exact output you're looking for:
        sys.stdout.write("Reading camera {}/{}".format(idx+1, len(cam_extrinsics)))
        sys.stdout.flush()

        extr = cam_extrinsics[key]
        intr = cam_intrinsics[extr.camera_id]
        height = intr.height
        width = intr.width

        uid = intr.id
        R = np.transpose(qvec2rotmat(extr.qvec))
        T = np.array(extr.tvec)

        if intr.model=="SIMPLE_PINHOLE":
            focal_length_x = intr.params[0]
            FovY = focal2fov(focal_length_x, height)
            FovX = focal2fov(focal_length_x, width)
        elif intr.model=="PINHOLE":
            focal_length_x = intr.params[0]
            focal_length_y = intr.params[1]
            FovY = focal2fov(focal_length_y, height)
            FovX = focal2fov(focal_length_x, width)
        else:
            assert False, "Colmap camera model not handled: only undistorted datasets (PINHOLE or SIMPLE_PINHOLE cameras) supported!"

        image_path = os.path.join(images_folder, os.path.basename(extr.name))
        image_name = os.path.basename(image_path).split(".")[0]
        image = Image.open(image_path)

        cam_info = CameraInfo(uid=uid, R=R, T=T, FovY=FovY, FovX=FovX, image=image,
                              image_path=image_path, image_name=image_name, width=width, height=height)
        cam_infos.append(cam_info)
    sys.stdout.write('\n')
    return cam_infos

def fetchPly(path):
    plydata = PlyData.read(path)
    vertices = plydata['vertex']
    positions = np.vstack([vertices['x'], vertices['y'], vertices['z']]).T
    colors = np.vstack([vertices['red'], vertices['green'], vertices['blue']]).T / 255.0
    normals = np.vstack([vertices['nx'], vertices['ny'], vertices['nz']]).T
    return BasicPointCloud(points=positions, colors=colors, normals=normals)

def storePly(path, xyz, rgb):
    # Define the dtype for the structured array
    dtype = [('x', 'f4'), ('y', 'f4'), ('z', 'f4'),
            ('nx', 'f4'), ('ny', 'f4'), ('nz', 'f4'),
            ('red', 'u1'), ('green', 'u1'), ('blue', 'u1')]
    
    normals = np.zeros_like(xyz)

    elements = np.empty(xyz.shape[0], dtype=dtype)
    attributes = np.concatenate((xyz, normals, rgb), axis=1)
    elements[:] = list(map(tuple, attributes))

    # Create the PlyData object and write to file
    vertex_element = PlyElement.describe(elements, 'vertex')
    ply_data = PlyData([vertex_element])
    ply_data.write(path)

def readColmapSceneInfo(path, images, eval, llffhold=8, building_mode="default", building_data_path=None, boundary_tolerance=2, depth_loss_scheme="original", sparse_dir="sparse"):
    try:
        cameras_extrinsic_file = os.path.join(path, f"{sparse_dir}/0", "images.bin")
        cameras_intrinsic_file = os.path.join(path, f"{sparse_dir}/0", "cameras.bin")
        cam_extrinsics = read_extrinsics_binary(cameras_extrinsic_file)
        cam_intrinsics = read_intrinsics_binary(cameras_intrinsic_file)
    except:
        cameras_extrinsic_file = os.path.join(path, f"{sparse_dir}/0", "images.txt")
        cameras_intrinsic_file = os.path.join(path, f"{sparse_dir}/0", "cameras.txt")
        cam_extrinsics = read_extrinsics_text(cameras_extrinsic_file)
        cam_intrinsics = read_intrinsics_text(cameras_intrinsic_file)

    reading_dir = "images" if images == None else images
    cam_infos_unsorted = readColmapCameras(cam_extrinsics=cam_extrinsics, cam_intrinsics=cam_intrinsics, images_folder=os.path.join(path, reading_dir))
    cam_infos = sorted(cam_infos_unsorted.copy(), key = lambda x : x.image_name)

    _split = os.environ.get("JBGS_SPLIT_JSON", "")   # r11 (PHD-MAIN-PREP-DISCARD-RULE-v1): explicit train / test names
    if _split:
        import json as _json
        _sp = _json.loads(open(_split).read())
        _tr, _te = set(_sp["train"]), set(_sp.get("test", []))
        train_cam_infos = [c for c in cam_infos if c.image_name in _tr]
        test_cam_infos = [c for c in cam_infos if c.image_name in _te] if eval else []
        if len(train_cam_infos) != len(_tr):
            raise ValueError(f"split: {len(_tr) - len(train_cam_infos)} training names not in the scene")
    elif eval:
        train_cam_infos = [c for idx, c in enumerate(cam_infos) if idx % llffhold != 0]
        test_cam_infos = [c for idx, c in enumerate(cam_infos) if idx % llffhold == 0]
    else:
        train_cam_infos = cam_infos
        test_cam_infos = []

    nerf_normalization = getNerfppNorm(train_cam_infos)

    ply_path = os.path.join(path, f"{sparse_dir}/0/points3D.ply")
    bin_path = os.path.join(path, f"{sparse_dir}/0/points3D.bin")
    txt_path = os.path.join(path, f"{sparse_dir}/0/points3D.txt")
    if not os.path.exists(ply_path):
        print("Converting point3d.bin to .ply, will happen only the first time you open the scene.")
        try:
            xyz, rgb, _ = read_points3D_binary(bin_path)
        except:
            xyz, rgb, _ = read_points3D_text(txt_path)
        storePly(ply_path, xyz, rgb)
    try:
        pcd = fetchPly(ply_path)
    except:
        pcd = None

    building_depth_maps = {}
    building_normal_maps = {}
    building_masks = {}

    if building_mode in ["building_enhanced", "building_only"] and building_data_path is not None:
        if os.path.exists(building_data_path):
            all_cam_infos = train_cam_infos + test_cam_infos
            building_depth_maps, building_normal_maps, building_masks = loadBuildingData(
                building_data_path, all_cam_infos, boundary_tolerance
            )
        else:
            print(f"Warning: Building data path {building_data_path} does not exist")
    elif building_data_path is not None:
        # Simplified: automatically load depth data if building_data_path is provided
        if os.path.exists(building_data_path):
            all_cam_infos = train_cam_infos + test_cam_infos
            building_depth_maps, building_normal_maps, building_masks = loadDepthOnlyData(
                building_data_path, all_cam_infos, boundary_tolerance
            )
            print(f"Loaded depth-only data from {building_data_path}")
        else:
            print(f"Warning: Building data path {building_data_path} does not exist")

    scene_info = SceneInfo(point_cloud=pcd,
                           train_cameras=train_cam_infos,
                           test_cameras=test_cam_infos,
                           nerf_normalization=nerf_normalization,
                           ply_path=ply_path,
                           building_depth_maps=building_depth_maps,
                           building_normal_maps=building_normal_maps,
                           building_masks=building_masks)
    return scene_info

def readCamerasFromTransforms(path, transformsfile, white_background, extension=".png"):
    cam_infos = []

    with open(os.path.join(path, transformsfile)) as json_file:
        contents = json.load(json_file)
        fovx = contents["camera_angle_x"]

        frames = contents["frames"]
        for idx, frame in enumerate(frames):
            cam_name = os.path.join(path, frame["file_path"] + extension)

            # NeRF 'transform_matrix' is a camera-to-world transform
            c2w = np.array(frame["transform_matrix"])
            # change from OpenGL/Blender camera axes (Y up, Z back) to COLMAP (Y down, Z forward)
            c2w[:3, 1:3] *= -1

            # get the world-to-camera transform and set R, T
            w2c = np.linalg.inv(c2w)
            R = np.transpose(w2c[:3,:3])  # R is stored transposed due to 'glm' in CUDA code
            T = w2c[:3, 3]

            image_path = os.path.join(path, cam_name)
            image_name = Path(cam_name).stem
            image = Image.open(image_path)

            im_data = np.array(image.convert("RGBA"))

            bg = np.array([1,1,1]) if white_background else np.array([0, 0, 0])

            norm_data = im_data / 255.0
            arr = norm_data[:,:,:3] * norm_data[:, :, 3:4] + bg * (1 - norm_data[:, :, 3:4])
            image = Image.fromarray(np.array(arr*255.0, dtype=np.byte), "RGB")

            fovy = focal2fov(fov2focal(fovx, image.size[0]), image.size[1])
            FovY = fovy 
            FovX = fovx

            cam_infos.append(CameraInfo(uid=idx, R=R, T=T, FovY=FovY, FovX=FovX, image=image,
                            image_path=image_path, image_name=image_name, width=image.size[0], height=image.size[1]))
            
    return cam_infos

def readNerfSyntheticInfo(path, white_background, eval, extension=".png", building_mode="default", building_data_path=None, boundary_tolerance=2, depth_loss_scheme="original"):
    print("Reading Training Transforms")
    train_cam_infos = readCamerasFromTransforms(path, "transforms_train.json", white_background, extension)
    print("Reading Test Transforms")
    test_cam_infos = readCamerasFromTransforms(path, "transforms_test.json", white_background, extension)
    
    if not eval:
        train_cam_infos.extend(test_cam_infos)
        test_cam_infos = []

    nerf_normalization = getNerfppNorm(train_cam_infos)

    ply_path = os.path.join(path, "points3d.ply")
    if not os.path.exists(ply_path):
        # Since this data set has no colmap data, we start with random points
        num_pts = 100_000
        print(f"Generating random point cloud ({num_pts})...")
        
        # We create random points inside the bounds of the synthetic Blender scenes
        xyz = np.random.random((num_pts, 3)) * 2.6 - 1.3
        shs = np.random.random((num_pts, 3)) / 255.0
        pcd = BasicPointCloud(points=xyz, colors=SH2RGB(shs), normals=np.zeros((num_pts, 3)))

        storePly(ply_path, xyz, SH2RGB(shs) * 255)
    try:
        pcd = fetchPly(ply_path)
    except:
        pcd = None

    building_depth_maps = {}
    building_normal_maps = {}
    building_masks = {}

    if building_mode in ["building_enhanced", "building_only"] and building_data_path is not None:
        if os.path.exists(building_data_path):
            all_cam_infos = train_cam_infos + test_cam_infos
            building_depth_maps, building_normal_maps, building_masks = loadBuildingData(
                building_data_path, all_cam_infos, boundary_tolerance
            )
        else:
            print(f"Warning: Building data path {building_data_path} does not exist")
    elif building_data_path is not None:
        # Simplified: automatically load depth data if building_data_path is provided
        if os.path.exists(building_data_path):
            all_cam_infos = train_cam_infos + test_cam_infos
            building_depth_maps, building_normal_maps, building_masks = loadDepthOnlyData(
                building_data_path, all_cam_infos, boundary_tolerance
            )
            print(f"Loaded depth-only data from {building_data_path}")
        else:
            print(f"Warning: Building data path {building_data_path} does not exist")

    scene_info = SceneInfo(point_cloud=pcd,
                           train_cameras=train_cam_infos,
                           test_cameras=test_cam_infos,
                           nerf_normalization=nerf_normalization,
                           ply_path=ply_path,
                           building_depth_maps=building_depth_maps,
                           building_normal_maps=building_normal_maps,
                           building_masks=building_masks)
    return scene_info

sceneLoadTypeCallbacks = {
    "Colmap": readColmapSceneInfo,
    "Blender" : readNerfSyntheticInfo
}

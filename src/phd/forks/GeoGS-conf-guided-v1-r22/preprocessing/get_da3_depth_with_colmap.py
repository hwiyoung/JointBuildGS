#!/usr/bin/env python3
"""
Process COLMAP data with DA3 to generate metric-scale aligned depth maps.

This script:
1. Reads COLMAP reconstruction (images, extrinsics, intrinsics)
2. Runs DA3NESTED-GIANT-LARGE inference with pose conditioning
3. Saves individual depth maps (.npy) and visualizations (.png)
4. Saves complete results (.npz)

This is a standalone version with COLMAP reading utilities integrated.

Usage:
    python get_da3_depth_with_colmap.py
"""

import os
import sys
import numpy as np
import torch
import cv2
from pathlib import Path
from tqdm import tqdm
import glob
import struct
import collections

from depth_anything_3.api import DepthAnything3


# ============================================================================
# COLMAP Reading Utilities
# ============================================================================

CameraModel = collections.namedtuple(
    "CameraModel", ["model_id", "model_name", "num_params"])
Camera = collections.namedtuple(
    "Camera", ["id", "model", "width", "height", "params"])
BaseImage = collections.namedtuple(
    "Image", ["id", "qvec", "tvec", "camera_id", "name", "xys", "point3D_ids"])
Point3D = collections.namedtuple(
    "Point3D", ["id", "xyz", "rgb", "error", "image_ids", "point2D_idxs"])


class Image(BaseImage):
    def qvec2rotmat(self):
        return qvec2rotmat(self.qvec)


CAMERA_MODELS = {
    CameraModel(model_id=0, model_name="SIMPLE_PINHOLE", num_params=3),
    CameraModel(model_id=1, model_name="PINHOLE", num_params=4),
    CameraModel(model_id=2, model_name="SIMPLE_RADIAL", num_params=4),
    CameraModel(model_id=3, model_name="RADIAL", num_params=5),
    CameraModel(model_id=4, model_name="OPENCV", num_params=8),
    CameraModel(model_id=5, model_name="OPENCV_FISHEYE", num_params=8),
    CameraModel(model_id=6, model_name="FULL_OPENCV", num_params=12),
    CameraModel(model_id=7, model_name="FOV", num_params=5),
    CameraModel(model_id=8, model_name="SIMPLE_RADIAL_FISHEYE", num_params=4),
    CameraModel(model_id=9, model_name="RADIAL_FISHEYE", num_params=5),
    CameraModel(model_id=10, model_name="THIN_PRISM_FISHEYE", num_params=12)
}
CAMERA_MODEL_IDS = dict([(camera_model.model_id, camera_model)
                          for camera_model in CAMERA_MODELS])
CAMERA_MODEL_NAMES = dict([(camera_model.model_name, camera_model)
                            for camera_model in CAMERA_MODELS])


def qvec2rotmat(qvec):
    """Convert quaternion to rotation matrix."""
    return np.array([
        [1 - 2 * qvec[2]**2 - 2 * qvec[3]**2,
         2 * qvec[1] * qvec[2] - 2 * qvec[0] * qvec[3],
         2 * qvec[3] * qvec[1] + 2 * qvec[0] * qvec[2]],
        [2 * qvec[1] * qvec[2] + 2 * qvec[0] * qvec[3],
         1 - 2 * qvec[1]**2 - 2 * qvec[3]**2,
         2 * qvec[2] * qvec[3] - 2 * qvec[0] * qvec[1]],
        [2 * qvec[3] * qvec[1] - 2 * qvec[0] * qvec[2],
         2 * qvec[2] * qvec[3] + 2 * qvec[0] * qvec[1],
         1 - 2 * qvec[1]**2 - 2 * qvec[2]**2]
    ])


def rotmat2qvec(R):
    """Convert rotation matrix to quaternion."""
    Rxx, Ryx, Rzx, Rxy, Ryy, Rzy, Rxz, Ryz, Rzz = R.flat
    K = np.array([
        [Rxx - Ryy - Rzz, 0, 0, 0],
        [Ryx + Rxy, Ryy - Rxx - Rzz, 0, 0],
        [Rzx + Rxz, Rzy + Ryz, Rzz - Rxx - Ryy, 0],
        [Ryz - Rzy, Rzx - Rxz, Rxy - Ryx, Rxx + Ryy + Rzz]]) / 3.0
    eigvals, eigvecs = np.linalg.eigh(K)
    qvec = eigvecs[[3, 0, 1, 2], np.argmax(eigvals)]
    if qvec[0] < 0:
        qvec *= -1
    return qvec


def read_next_bytes(fid, num_bytes, format_char_sequence, endian_character="<"):
    """Read and unpack the next bytes from a binary file.
    """
    data = fid.read(num_bytes)
    return struct.unpack(endian_character + format_char_sequence, data)


def read_cameras_text(path):
    cameras = {}
    with open(path, "r") as fid:
        while True:
            line = fid.readline()
            if not line:
                break
            line = line.strip()
            if len(line) > 0 and line[0] != "#":
                elems = line.split()
                camera_id = int(elems[0])
                model = elems[1]
                width = int(elems[2])
                height = int(elems[3])
                params = np.array(tuple(map(float, elems[4:])))
                cameras[camera_id] = Camera(id=camera_id, model=model,
                                             width=width, height=height,
                                             params=params)
    return cameras


def read_cameras_binary(path_to_model_file):
    cameras = {}
    with open(path_to_model_file, "rb") as fid:
        num_cameras = read_next_bytes(fid, 8, "Q")[0]
        for _ in range(num_cameras):
            camera_properties = read_next_bytes(
                fid, num_bytes=24, format_char_sequence="iiQQ")
            camera_id = camera_properties[0]
            model_id = camera_properties[1]
            model_name = CAMERA_MODEL_IDS[camera_properties[1]].model_name
            width = camera_properties[2]
            height = camera_properties[3]
            num_params = CAMERA_MODEL_IDS[model_id].num_params
            params = read_next_bytes(fid, num_bytes=8*num_params,
                                      format_char_sequence="d"*num_params)
            cameras[camera_id] = Camera(id=camera_id,
                                         model=model_name,
                                         width=width,
                                         height=height,
                                         params=np.array(params))
        assert len(cameras) == num_cameras
    return cameras


def read_images_text(path):
    images = {}
    with open(path, "r") as fid:
        while True:
            line = fid.readline()
            if not line:
                break
            line = line.strip()
            if len(line) > 0 and line[0] != "#":
                elems = line.split()
                image_id = int(elems[0])
                qvec = np.array(tuple(map(float, elems[1:5])))
                tvec = np.array(tuple(map(float, elems[5:8])))
                camera_id = int(elems[8])
                image_name = elems[9]
                elems = fid.readline().split()
                xys = np.column_stack([tuple(map(float, elems[0::3])),
                                        tuple(map(float, elems[1::3]))])
                point3D_ids = np.array(tuple(map(int, elems[2::3])))
                images[image_id] = Image(
                    id=image_id, qvec=qvec, tvec=tvec,
                    camera_id=camera_id, name=image_name,
                    xys=xys, point3D_ids=point3D_ids)
    return images


def read_images_binary(path_to_model_file):
    images = {}
    with open(path_to_model_file, "rb") as fid:
        num_reg_images = read_next_bytes(fid, 8, "Q")[0]
        for _ in range(num_reg_images):
            binary_image_properties = read_next_bytes(
                fid, num_bytes=64, format_char_sequence="idddddddi")
            image_id = binary_image_properties[0]
            qvec = np.array(binary_image_properties[1:5])
            tvec = np.array(binary_image_properties[5:8])
            camera_id = binary_image_properties[8]
            binary_image_name = b""
            current_char = read_next_bytes(fid, 1, "c")[0]
            while current_char != b"\x00":   # look for the ASCII 0 entry
                binary_image_name += current_char
                current_char = read_next_bytes(fid, 1, "c")[0]
            image_name = binary_image_name.decode("utf-8")
            num_points2D = read_next_bytes(fid, num_bytes=8,
                                            format_char_sequence="Q")[0]
            x_y_id_s = read_next_bytes(fid, num_bytes=24*num_points2D,
                                        format_char_sequence="ddq"*num_points2D)
            xys = np.column_stack([tuple(map(float, x_y_id_s[0::3])),
                                    tuple(map(float, x_y_id_s[1::3]))])
            point3D_ids = np.array(tuple(map(int, x_y_id_s[2::3])))
            images[image_id] = Image(
                id=image_id, qvec=qvec, tvec=tvec,
                camera_id=camera_id, name=image_name,
                xys=xys, point3D_ids=point3D_ids)
    return images


def read_points3D_text(path):
    points3D = {}
    with open(path, "r") as fid:
        while True:
            line = fid.readline()
            if not line:
                break
            line = line.strip()
            if len(line) > 0 and line[0] != "#":
                elems = line.split()
                point3D_id = int(elems[0])
                xyz = np.array(tuple(map(float, elems[1:4])))
                rgb = np.array(tuple(map(int, elems[4:7])))
                error = float(elems[7])
                image_ids = np.array(tuple(map(int, elems[8::2])))
                point2D_idxs = np.array(tuple(map(int, elems[9::2])))
                points3D[point3D_id] = Point3D(id=point3D_id, xyz=xyz, rgb=rgb,
                                                error=error, image_ids=image_ids,
                                                point2D_idxs=point2D_idxs)
    return points3D


def read_points3D_binary(path_to_model_file):
    points3D = {}
    with open(path_to_model_file, "rb") as fid:
        num_points = read_next_bytes(fid, 8, "Q")[0]
        for _ in range(num_points):
            binary_point_line_properties = read_next_bytes(
                fid, num_bytes=43, format_char_sequence="QdddBBBd")
            point3D_id = binary_point_line_properties[0]
            xyz = np.array(binary_point_line_properties[1:4])
            rgb = np.array(binary_point_line_properties[4:7])
            error = np.array(binary_point_line_properties[7])
            track_length = read_next_bytes(
                fid, num_bytes=8, format_char_sequence="Q")[0]
            track_elems = read_next_bytes(
                fid, num_bytes=8*track_length,
                format_char_sequence="ii"*track_length)
            image_ids = np.array(tuple(map(int, track_elems[0::2])))
            point2D_idxs = np.array(tuple(map(int, track_elems[1::2])))
            points3D[point3D_id] = Point3D(
                id=point3D_id, xyz=xyz, rgb=rgb,
                error=error, image_ids=image_ids,
                point2D_idxs=point2D_idxs)
    return points3D


def read_model(path, ext=""):
    """
    Read COLMAP model (cameras, images, points3D).

    Args:
        path: Path to the COLMAP sparse reconstruction directory
        ext: Extension (".bin" for binary, ".txt" for text).
             If empty, will try binary first, then text.

    Returns:
        cameras, images, points3D dictionaries
    """
    # Cameras
    if ext == ".txt" or (ext == "" and os.path.exists(os.path.join(path, "cameras.txt"))):
        cameras = read_cameras_text(os.path.join(path, "cameras.txt"))
    elif ext == ".bin" or (ext == "" and os.path.exists(os.path.join(path, "cameras.bin"))):
        cameras = read_cameras_binary(os.path.join(path, "cameras.bin"))
    else:
        raise FileNotFoundError(f"cameras{ext} not found in {path}")

    # Images
    if ext == ".txt" or (ext == "" and os.path.exists(os.path.join(path, "images.txt"))):
        images = read_images_text(os.path.join(path, "images.txt"))
    elif ext == ".bin" or (ext == "" and os.path.exists(os.path.join(path, "images.bin"))):
        images = read_images_binary(os.path.join(path, "images.bin"))
    else:
        raise FileNotFoundError(f"images{ext} not found in {path}")

    # Points3D
    if ext == ".txt" or (ext == "" and os.path.exists(os.path.join(path, "points3D.txt"))):
        points3D = read_points3D_text(os.path.join(path, "points3D.txt"))
    elif ext == ".bin" or (ext == "" and os.path.exists(os.path.join(path, "points3D.bin"))):
        points3D = read_points3D_binary(os.path.join(path, "points3D.bin"))
    else:
        # Points3D is optional
        points3D = {}

    return cameras, images, points3D


# ============================================================================
# Absolute Depth Visualization Configuration (Easily Adjustable)
# ============================================================================
# These ranges control the color mapping when using --visualize-abs mode
# Adjust these values to focus on different depth ranges of interest

ABSOLUTE_DEPTH_CONFIG = {
    # Default depth range for absolute visualization
    'default_min_depth': 20,    # meters
    'default_max_depth': 200.0,  # meters
}

def visualize_depth(
    depth: np.ndarray,
    depth_min=None,
    depth_max=None,
    percentile=2,
    cmap="Spectral",
    use_absolute_range=False,
    abs_min_depth=20,
    abs_max_depth=200.0,
) -> np.ndarray:
    """
    Visualize depth map using DA3's official visualization method.
    This matches the implementation in src/depth_anything_3/utils/visualize.py

    Args:
        depth: Input depth map array (in meters)
        depth_min: Minimum depth value for normalization. If None, uses percentile or absolute range
        depth_max: Maximum depth value for normalization. If None, uses percentile or absolute range
        percentile: Percentile for min/max computation if not provided (default: 2)
        cmap: Matplotlib colormap name (default: "Spectral")
        use_absolute_range: If True, use fixed depth range instead of percentiles
        abs_min_depth: Minimum depth for absolute range visualization (meters)
        abs_max_depth: Maximum depth for absolute range visualization (meters)

    Returns:
        Colored depth visualization as uint8 numpy array (H, W, 3)
    """
    import matplotlib

    depth = depth.copy()

    # Invert depth values (depth to disparity-like representation)
    valid_mask = depth > 0
    depth[valid_mask] = 1 / depth[valid_mask]

    # Compute min/max: either from absolute range or percentiles
    if use_absolute_range:
        # Use fixed absolute depth range
        # Note: inverted because we're in disparity space (1/depth)
        # Larger depth -> smaller disparity
        depth_min = 1 / abs_max_depth  # Far depth -> small disparity
        depth_max = 1 / abs_min_depth  # Near depth -> large disparity

        # Debug: print actual disparity range
        valid_disparities = depth[valid_mask]
        if len(valid_disparities) > 0:
            actual_min = valid_disparities.min()
            actual_max = valid_disparities.max()
            # Only print once (check if this is the first call)
            import builtins
            if not hasattr(builtins, '_depth_vis_debug_printed'):
                print(f"\n🔍 Disparity range DEBUG:")
                print(f"   Configured: [{depth_min:.6f}, {depth_max:.6f}] (from depths [{abs_max_depth}, {abs_min_depth}]m)")
                print(f"   Actual:     [{actual_min:.6f}, {actual_max:.6f}]")
                builtins._depth_vis_debug_printed = True

    else:
        # Use percentile-based range (original behavior)
        if depth_min is None:
            if valid_mask.sum() <= 10:
                depth_min = 0
            else:
                depth_min = np.percentile(depth[valid_mask], percentile)
        if depth_max is None:
            if valid_mask.sum() <= 10:
                depth_max = 0
            else:
                depth_max = np.percentile(depth[valid_mask], 100 - percentile)

    if depth_min == depth_max:
        depth_min = depth_min - 1e-6
        depth_max = depth_max + 1e-6

    # Normalize and invert
    cm = matplotlib.colormaps[cmap]
    depth = ((depth - depth_min) / (depth_max - depth_min)).clip(0, 1)
    depth = 1 - depth  # Invert so closer is warmer colors

    # Apply colormap
    img_colored_np = cm(depth[None], bytes=False)[:, :, :, 0:3]
    img_colored_np = (img_colored_np[0] * 255.0).astype(np.uint8)

    return img_colored_np


def read_colmap_data(colmap_dir: str, sparse_subdir: str = "0"):
    """
    Read COLMAP reconstruction data.

    Args:
        colmap_dir: Path to COLMAP directory (contains images/ and sparse/)
        sparse_subdir: Sparse reconstruction subdirectory

    Returns:
        Tuple of (image_paths, extrinsics, intrinsics, image_names, original_sizes)
    """
    sparse_path = os.path.join(colmap_dir, "sparse", sparse_subdir)
    images_dir = os.path.join(colmap_dir, "images")

    print(f"Reading COLMAP data from: {sparse_path}")

    # Read COLMAP model
    cameras, images, points3d = read_model(sparse_path, ext=".bin")

    print(f"  Cameras: {len(cameras)}")
    print(f"  Images: {len(images)}")
    print(f"  3D Points: {len(points3d)}")

    # Sort images by ID
    image_ids = sorted(images.keys())

    image_paths = []
    extrinsics_list = []
    intrinsics_list = []
    image_names = []
    original_sizes = []  # Store (width, height) for each image

    for img_id in image_ids:
        img_meta = images[img_id]
        cam = cameras[img_meta.camera_id]

        # Get image path
        img_path = os.path.join(images_dir, img_meta.name)
        if not os.path.exists(img_path):
            print(f"Warning: Image not found: {img_path}")
            continue

        image_paths.append(img_path)

        # Extract image name (without extension)
        image_name = os.path.splitext(img_meta.name)[0]
        image_names.append(image_name)

        # Store original image size (width, height)
        from PIL import Image
        with Image.open(img_path) as img:
            original_sizes.append(img.size)  # (width, height)

        # Build extrinsics (world-to-camera)
        R = qvec2rotmat(img_meta.qvec)
        t = img_meta.tvec.reshape(3, 1)
        extrinsic = np.hstack([R, t])  # (3, 4)
        extrinsics_list.append(extrinsic)

        # Build intrinsics
        # COLMAP camera models: SIMPLE_PINHOLE, PINHOLE, etc.
        # params = [fx, fy, cx, cy] or [f, cx, cy]
        if cam.model == "SIMPLE_PINHOLE":
            f, cx, cy = cam.params
            fx = fy = f
        elif cam.model == "PINHOLE":
            fx, fy, cx, cy = cam.params
        elif cam.model == "SIMPLE_RADIAL":
            f, cx, cy, k = cam.params
            fx = fy = f
        elif cam.model == "RADIAL":
            f, cx, cy, k1, k2 = cam.params
            fx = fy = f
        else:
            raise ValueError(f"Unsupported camera model: {cam.model}")

        intrinsic = np.array([
            [fx, 0, cx],
            [0, fy, cy],
            [0, 0, 1]
        ])
        intrinsics_list.append(intrinsic)

    extrinsics = np.stack(extrinsics_list, axis=0)  # (N, 3, 4)
    intrinsics = np.stack(intrinsics_list, axis=0)  # (N, 3, 3)

    # Convert to 4x4 extrinsics for DA3 API
    N = extrinsics.shape[0]
    extrinsics_4x4 = np.zeros((N, 4, 4))
    extrinsics_4x4[:, :3, :] = extrinsics
    extrinsics_4x4[:, 3, 3] = 1.0

    print(f"\nLoaded {len(image_paths)} images with camera parameters")

    return image_paths, extrinsics_4x4, intrinsics, image_names, original_sizes


def main():
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Process COLMAP data with DA3 for metric-scale depth estimation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Default mode (adaptive percentile-based visualization)
    python get_da3_depth_with_colmap.py

    # Absolute depth mode (fixed range for cross-image consistency)
    python get_da3_depth_with_colmap.py --visualize-abs

    # Custom absolute depth range (focus on near objects)
    python get_da3_depth_with_colmap.py --visualize-abs --abs-min-depth 0.5 --abs-max-depth 50
        """
    )

    parser.add_argument(
        "--colmap-dir",
        type=str,
        default="/path/to/colmap/project",
        help="COLMAP directory containing images/ and sparse/"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="/path/to/output/depth_maps",
        help="Output directory for depth maps and visualizations"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="da3nested-giant-large",
        help="DA3 model name"
    )
    parser.add_argument(
        "--sparse-subdir",
        type=str,
        default="0",
        help="Sparse reconstruction subdirectory"
    )
    parser.add_argument(
        "--process-res",
        type=int,
        default=840,
        help="Processing resolution (longer side in pixels). Higher = better quality but slower. Recommended: 504 (fast), 840 (balanced), 1008 (high quality)"
    )
    parser.add_argument(
        "--upsample-to-original",
        action="store_true",
        help="Upsample depth maps to original image resolution after inference. Useful for pixel-level tasks."
    )
    parser.add_argument(
        "--visualize-abs",
        action="store_true",
        help="Use absolute depth ranges for visualization (same depth = same color across all images)"
    )
    parser.add_argument(
        "--abs-min-depth",
        type=float,
        default=ABSOLUTE_DEPTH_CONFIG['default_min_depth'],
        help=f"Minimum depth for absolute visualization in meters (default: {ABSOLUTE_DEPTH_CONFIG['default_min_depth']})"
    )
    parser.add_argument(
        "--abs-max-depth",
        type=float,
        default=ABSOLUTE_DEPTH_CONFIG['default_max_depth'],
        help=f"Maximum depth for absolute visualization in meters (default: {ABSOLUTE_DEPTH_CONFIG['default_max_depth']})"
    )

    args = parser.parse_args()

    # Configuration from arguments
    COLMAP_DIR = args.colmap_dir
    OUTPUT_DIR = args.output_dir
    MODEL_NAME = args.model
    SPARSE_SUBDIR = args.sparse_subdir
    PROCESS_RES = args.process_res
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

    print("=" * 80)
    print("DA3 COLMAP Depth Processing (Python)")
    print("=" * 80)
    print(f"COLMAP directory: {COLMAP_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Model: {MODEL_NAME}")
    print(f"Device: {DEVICE}")

    if args.visualize_abs:
        print(f"\n🎨 Absolute Depth Visualization: ENABLED")
        print(f"   Depth range: [{args.abs_min_depth}, {args.abs_max_depth}] meters")
        print(f"   Color mapping: Same depth = Same color across all images")
    else:
        print(f"\n🎨 Adaptive Visualization: ENABLED")
        print(f"   Each image uses its own percentile-based range")

    print("=" * 80)
    print()

    # Create output directories
    raw_depth_dir = os.path.join(OUTPUT_DIR, "raw_depth")
    vis_depth_dir = os.path.join(OUTPUT_DIR, "vis_depth")
    exports_dir = os.path.join(OUTPUT_DIR, "exports", "npz")

    os.makedirs(raw_depth_dir, exist_ok=True)
    os.makedirs(vis_depth_dir, exist_ok=True)
    os.makedirs(exports_dir, exist_ok=True)

    # Create upsampled directory if needed
    if args.upsample_to_original:
        raw_depth_upsampled_dir = os.path.join(OUTPUT_DIR, "raw_depth_upsampled")
        os.makedirs(raw_depth_upsampled_dir, exist_ok=True)

    # Step 1: Read COLMAP data
    print("Step 1: Reading COLMAP data...")
    image_paths, extrinsics, intrinsics, image_names, original_sizes = read_colmap_data(
        COLMAP_DIR, SPARSE_SUBDIR
    )

    # Print original image dimensions
    if len(original_sizes) > 0:
        print(f"  Original image size (first image): {original_sizes[0][0]}x{original_sizes[0][1]} pixels")

    # Step 2: Load DA3 model
    print("\nStep 2: Loading DA3 model...")
    model = DepthAnything3.from_pretrained(f"depth-anything/{MODEL_NAME.upper()}")
    model = model.to(DEVICE)
    print("Model loaded successfully")

    # Step 3: Run inference
    print("\nStep 3: Running inference with pose conditioning...")
    print(f"Processing {len(image_paths)} images at resolution {PROCESS_RES}...")
    if args.upsample_to_original:
        print(f"  Upsampling to original resolution will be performed after inference")

    prediction = model.inference(
        image=image_paths,
        extrinsics=extrinsics,
        intrinsics=intrinsics,
        align_to_input_ext_scale=True,
        process_res=PROCESS_RES,
        process_res_method="upper_bound_resize"
    )

    print("Inference completed")
    print(f"  Depth shape: {prediction.depth.shape}")
    print(f"  Confidence shape: {prediction.conf.shape}")
    print(f"  Extrinsics shape: {prediction.extrinsics.shape}")
    print(f"  Intrinsics shape: {prediction.intrinsics.shape}")

    # Step 4: Save individual depth maps and visualizations
    print("\nStep 4: Saving individual depth maps and visualizations...")

    # Print depth statistics for first image (for debugging)
    if len(prediction.depth) > 0:
        first_depth = prediction.depth[0]
        valid_first = first_depth[first_depth > 0]
        print(f"\n🔍 Depth statistics (first image):")
        print(f"   Min: {valid_first.min():.3f} m")
        print(f"   Max: {valid_first.max():.3f} m")
        print(f"   Mean: {valid_first.mean():.3f} m")
        print(f"   Median: {np.median(valid_first):.3f} m")
        if args.visualize_abs:
            print(f"   Visualization range: [{args.abs_min_depth}, {args.abs_max_depth}] m")

    for idx, image_name in enumerate(tqdm(image_names, desc="Saving files")):
        depth_map = prediction.depth[idx]
        original_size = original_sizes[idx]  # (width, height)

        # Save raw depth at inference resolution
        npy_path = os.path.join(raw_depth_dir, f"{image_name}.npy")
        np.save(npy_path, depth_map.astype(np.float32))

        # Upsample to original resolution if requested
        if args.upsample_to_original:
            # Upsample depth map
            depth_upsampled = cv2.resize(
                depth_map,
                original_size,  # (width, height)
                interpolation=cv2.INTER_CUBIC
            )

            # Save upsampled depth
            npy_upsampled_path = os.path.join(raw_depth_upsampled_dir, f"{image_name}.npy")
            np.save(npy_upsampled_path, depth_upsampled.astype(np.float32))

        # Create and save visualization (using DA3's official method)
        depth_vis = visualize_depth(
            depth_map,
            use_absolute_range=args.visualize_abs,
            abs_min_depth=args.abs_min_depth,
            abs_max_depth=args.abs_max_depth
        )

        vis_path = os.path.join(vis_depth_dir, f"{image_name}.png")
        cv2.imwrite(vis_path, cv2.cvtColor(depth_vis, cv2.COLOR_RGB2BGR))

    print(f"  Saved {len(image_names)} depth maps to: {raw_depth_dir}")
    if args.upsample_to_original:
        print(f"  Saved {len(image_names)} upsampled depth maps to: {raw_depth_upsampled_dir}")
    print(f"  Saved {len(image_names)} visualizations to: {vis_depth_dir}")

    # Step 5: Save complete NPZ file
    print("\nStep 5: Saving complete results...")

    results_path = os.path.join(exports_dir, "results.npz")
    np.savez(
        results_path,
        image=prediction.processed_images,
        depth=prediction.depth,
        conf=prediction.conf,
        extrinsics=prediction.extrinsics,
        intrinsics=prediction.intrinsics
    )

    print(f"  Saved complete results to: {results_path}")

    # Print summary
    print("\n" + "=" * 80)
    print("Processing Complete!")
    print("=" * 80)

    # Get depth map dimensions
    depth_shape = prediction.depth[0].shape

    print(f"\nOutput structure:")
    print(f"  {OUTPUT_DIR}/")
    print(f"  ├── raw_depth/          # Depth maps at inference resolution ({depth_shape[1]}x{depth_shape[0]})")
    print(f"  │   ├── {image_names[0]}.npy")
    print(f"  │   └── ... ({len(image_names)} files)")

    if args.upsample_to_original:
        print(f"  ├── raw_depth_upsampled/ # Upsampled to original resolution ({original_sizes[0][0]}x{original_sizes[0][1]})")
        print(f"  │   ├── {image_names[0]}.npy")
        print(f"  │   └── ... ({len(image_names)} files)")

    print(f"  ├── vis_depth/          # Depth visualizations (.png)")
    print(f"  │   ├── {image_names[0]}.png")
    print(f"  │   └── ... ({len(image_names)} files)")
    print(f"  └── exports/npz/")
    print(f"      └── results.npz     # Complete results")
    print()

    print("Resolution information:")
    print(f"  Original images: {original_sizes[0][0]}x{original_sizes[0][1]} pixels")
    print(f"  Inference resolution: {depth_shape[1]}x{depth_shape[0]} pixels")
    print(f"  Downscale factor: {original_sizes[0][0]/depth_shape[1]:.2f}x")
    if args.upsample_to_original:
        print(f"  Upsampled back to: {original_sizes[0][0]}x{original_sizes[0][1]} pixels")
    print()

    print("To load depth data in Python:")
    print("  import numpy as np")
    print(f"  depth = np.load('{raw_depth_dir}/{image_names[0]}.npy')")
    if args.upsample_to_original:
        print(f"  depth_hires = np.load('{raw_depth_upsampled_dir}/{image_names[0]}.npy')")
    print("  # OR")
    print(f"  data = np.load('{results_path}')")
    print("  all_depths = data['depth']")
    print()


if __name__ == "__main__":
    main()

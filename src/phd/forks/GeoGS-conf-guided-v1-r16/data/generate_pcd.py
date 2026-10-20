#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script for generating COLMAP-compatible points3D.txt from an OBJ model and camera parameters.
This script samples points from the mesh surface and projects them into camera views to create
a synthetic point cloud that follows the COLMAP format.
"""

import os
import argparse
import sys
import numpy as np
import random
import trimesh
import open3d as o3d
from collections import defaultdict

# Add parent directory to path to import LoD2Depth modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import functions from LoD2Depth module
from LoD2Depth.camera_loader import (
    load_cameras, 
    load_images, 
    get_camera_intrinsics, 
    get_camera_extrinsics,
    quaternion_to_rotation_matrix
)

# Import necessary functions from local modules
from mesh_handler import load_and_transform_mesh
from lodgs_utils import ensure_directory_exists


def create_trimesh_scene(vertices, faces):
    """
    Create a trimesh scene for raycasting.
    
    Parameters:
        vertices (numpy.ndarray): Mesh vertices
        faces (numpy.ndarray): Mesh faces
        
    Returns:
        trimesh.Scene: Scene for raycasting
    """
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    scene = trimesh.Scene(mesh)
    return scene


def sample_points_from_mesh(vertices, faces, num_points=60000):
    """
    Sample points uniformly from the mesh surface.
    
    Parameters:
        vertices (numpy.ndarray): Mesh vertices
        faces (numpy.ndarray): Mesh faces
        num_points (int): Number of points to sample
        
    Returns:
        numpy.ndarray: Sampled points (N x 3)
    """
    # Create a trimesh object
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    
    # Sample points from the mesh surface
    points, face_indices = trimesh.sample.sample_surface(mesh, num_points)
    
    print(f"Sampled {len(points)} points from mesh surface")
    return points, face_indices


def is_point_visible_from_camera(scene, point, camera_position, camera_direction):
    """
    Check if a point is visible from a camera using raycasting with trimesh.
    
    Parameters:
        scene (trimesh.Scene): Trimesh scene for raycasting
        point (numpy.ndarray): 3D point coordinates
        camera_position (numpy.ndarray): Camera position
        camera_direction (numpy.ndarray): Direction from camera to point
        
    Returns:
        bool: True if point is visible, False otherwise
    """
    # Calculate expected distance to the point
    expected_distance = np.linalg.norm(point - camera_position)
    
    # Normalize direction vector
    direction = camera_direction / np.linalg.norm(camera_direction)
    
    # Create ray origins and directions
    ray_origins = [camera_position]
    ray_directions = [direction]
    
    # Cast ray and get intersections
    locations, index_ray, index_tri = scene.ray.intersects_location(
        ray_origins=ray_origins,
        ray_directions=ray_directions
    )
    
    # If no intersections, the point is not visible
    if len(locations) == 0:
        return False
    
    # Get distance to the first intersection
    first_intersection = locations[0]
    actual_distance = np.linalg.norm(first_intersection - camera_position)
    
    # If the intersection is approximately at the expected distance, the point is visible
    # Allow a small threshold for numerical precision
    threshold = 0.05  # 5cm tolerance
    return abs(actual_distance - expected_distance) < threshold


def is_point_visible_fallback(vertices, faces, point, camera_position):
    """
    Alternative visibility check that uses simple ray casting logic.
    This is a fallback in case the trimesh ray casting doesn't work.
    
    Parameters:
        vertices (numpy.ndarray): Mesh vertices
        faces (numpy.ndarray): Mesh faces
        point (numpy.ndarray): 3D point coordinates
        camera_position (numpy.ndarray): Camera position
        
    Returns:
        bool: Always returns True as a fallback, assuming all points in front of camera are visible
    """
    # This is a simple fallback that assumes all points are visible
    # In a real implementation, you would need to check for occlusion
    return True


def project_point_to_camera(point, camera_extrinsics, camera_intrinsics, width, height):
    """
    Project a 3D point to 2D camera coordinates.
    
    Parameters:
        point (numpy.ndarray): 3D point coordinates
        camera_extrinsics (numpy.ndarray): 4x4 camera extrinsic matrix
        camera_intrinsics (numpy.ndarray): 3x3 camera intrinsic matrix
        width (int): Image width
        height (int): Image height
        
    Returns:
        tuple: (x, y) pixel coordinates, or None if behind camera or outside frame
    """
    # Convert point to homogeneous coordinates
    point_homogeneous = np.append(point, 1)
    
    # Transform point to camera coordinates
    point_camera = camera_extrinsics @ point_homogeneous
    
    # Check if point is behind camera
    if point_camera[2] <= 0:
        return None
    
    # Project to image coordinates
    point_normalized = point_camera[:3] / point_camera[2]
    point_pixel = camera_intrinsics @ point_normalized
    
    # Extract pixel coordinates
    x, y = point_pixel[0], point_pixel[1]
    
    # Check if point is within image bounds (with a small margin)
    margin = 5
    if margin <= x < width - margin and margin <= y < height - margin:
        return (x, y)
    else:
        return None


def generate_point_cloud(vertices, faces, points, face_indices, cameras, images, min_observations=2, max_observations=10):
    """
    Generate a COLMAP-compatible point cloud from sampled mesh points.
    
    Parameters:
        vertices (numpy.ndarray): Mesh vertices
        faces (numpy.ndarray): Mesh faces
        points (numpy.ndarray): Sampled 3D points
        face_indices (numpy.ndarray): Face indices for each sampled point
        cameras (dict): Camera intrinsic parameters
        images (dict): Camera extrinsic parameters
        min_observations (int): Minimum number of cameras that must observe a point
        max_observations (int): Maximum number of cameras to record for each point
        
    Returns:
        list: List of points with their observations in COLMAP format
    """
    point_cloud = []
    
    # Try to create a trimesh scene for visibility checking
    try:
        scene = create_trimesh_scene(vertices, faces)
        use_trimesh = True
        print("Using trimesh for visibility checking")
    except Exception as e:
        print(f"Warning: Failed to create trimesh scene, using fallback visibility check: {e}")
        use_trimesh = False
    
    # Process each point
    for i, point in enumerate(points):
        if i % 1000 == 0:
            print(f"Processing point {i}/{len(points)}")
        
        observations = []
        
        # Check visibility from each camera
        for image_id, image_data in images.items():
            camera = cameras[image_data.camera_id]
            
            # Get camera intrinsics and extrinsics
            camera_intrinsics = get_camera_intrinsics(camera)
            camera_extrinsics = get_camera_extrinsics(image_data)
            
            # Get camera position (inverse of extrinsics translation)
            R = quaternion_to_rotation_matrix(image_data.qvec)
            t = np.array(image_data.tvec)
            camera_position = -R.T @ t
            
            # Vector from camera to point
            camera_to_point = point - camera_position
            
            # Project point to camera
            projection = project_point_to_camera(
                point, camera_extrinsics, camera_intrinsics, camera.width, camera.height
            )
            
            if projection:
                # Check visibility
                is_visible = False
                if use_trimesh:
                    try:
                        is_visible = is_point_visible_from_camera(scene, point, camera_position, camera_to_point)
                    except Exception as e:
                        print(f"Warning: Trimesh visibility check failed, falling back: {e}")
                        is_visible = is_point_visible_fallback(vertices, faces, point, camera_position)
                else:
                    is_visible = is_point_visible_fallback(vertices, faces, point, camera_position)
                
                if is_visible:
                    # In COLMAP, POINT2D_IDX is the index in the list of keypoints for that image
                    # Here we're creating synthetic data, so we'll assign sequential indices
                    point2d_idx = len(observations)
                    observations.append((image_id, point2d_idx, projection[0], projection[1]))
        
        # Only include points observed by a minimum number of cameras
        if len(observations) >= min_observations:
            # Limit the number of observations to prevent very long tracks
            if len(observations) > max_observations:
                observations = random.sample(observations, max_observations)
            
            # Gray color for all points (as requested)
            gray_value = 128
            color = (gray_value, gray_value, gray_value)
            
            # Add to point cloud
            point_cloud.append({
                'id': i,
                'xyz': point,
                'rgb': color,
                'error': 0.0,  # Default error
                'observations': observations
            })
    
    print(f"Generated point cloud with {len(point_cloud)} points")
    return point_cloud


def write_points3D_file(point_cloud, output_file):
    """
    Write point cloud to COLMAP points3D.txt format.
    
    Parameters:
        point_cloud (list): List of points with their observations
        output_file (str): Output file path
    """
    # Calculate mean track length
    total_observations = sum(len(point['observations']) for point in point_cloud)
    mean_track_length = total_observations / len(point_cloud) if point_cloud else 0
    
    with open(output_file, 'w') as f:
        # Write header
        f.write(f"# 3D point list with one line of data per point:\n")
        f.write(f"#   POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[] as (IMAGE_ID, POINT2D_IDX)\n")
        f.write(f"# Number of points: {len(point_cloud)}, mean track length: {mean_track_length}\n")
        
        # Write points
        for point in point_cloud:
            # Format: POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[]
            point_id = point['id']
            x, y, z = point['xyz']
            r, g, b = point['rgb']
            error = point['error']
            
            # Start with point information
            line = f"{point_id} {x} {y} {z} {r} {g} {b} {error}"
            
            # Add track information
            for obs in point['observations']:
                image_id, point2d_idx, _, _ = obs
                line += f" {image_id} {point2d_idx}"
            
            f.write(line + "\n")
    
    print(f"Wrote point cloud to {output_file}")


def update_images_with_points2D(images, point_cloud, output_file):
    """
    Update the images.txt file with generated point2D information.
    
    Parameters:
        images (dict): Original images data
        point_cloud (list): Generated point cloud with observations
        output_file (str): Output file path for updated images.txt
    """
    # Collect points2D for each image
    image_points = defaultdict(list)
    
    for point in point_cloud:
        point_id = point['id']
        for obs in point['observations']:
            image_id, point2d_idx, x, y = obs
            # Store (x, y, point3D_id)
            image_points[image_id].append((x, y, point_id))
    
    # Write updated images.txt
    with open(output_file, 'w') as f:
        f.write("# Image list with two lines of data per image:\n")
        f.write("#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n")
        f.write("#   POINTS2D[] as (X, Y, POINT3D_ID)\n")
        
        for image_id, image_data in sorted(images.items()):
            # First line: camera extrinsics
            qw, qx, qy, qz = image_data.qvec
            tx, ty, tz = image_data.tvec
            f.write(f"{image_id} {qw} {qx} {qy} {qz} {tx} {ty} {tz} {image_data.camera_id} {image_data.name}\n")
            
            # Second line: points2D
            points2D_line = ""
            for x, y, point3d_id in image_points.get(image_id, []):
                points2D_line += f"{x} {y} {point3d_id} "
            
            f.write(points2D_line.strip() + "\n")
    
    print(f"Wrote updated images.txt to {output_file}")


def main():
    """
    Main function: Process input arguments, transform the model, and generate point cloud.
    """
    parser = argparse.ArgumentParser(description='Generate COLMAP-compatible point cloud from OBJ model')
    parser.add_argument('--mesh_path', type=str, 
                        default='./LoD2Depth/data/Mesh/lod2_model.obj',
                        help='Input OBJ file path')
    parser.add_argument('--reference_frame_path', type=str, 
                        default='./LoD2Depth/data/scene_reference_frame.json', 
                        help='Scene reference frame JSON file path')
    parser.add_argument('--output_dir', type=str, 
                        default='./example_data/building14/building14_15/sparse_lod/0',
                        help='Output directory for point cloud files')
    parser.add_argument('--z_offset', type=float, default=45.66,
                        help='Additional Z-axis offset')
    parser.add_argument('--colmap_dir', type=str, 
                        default='./example_data/building14/building14_15/sparse_txt',
                        help='Directory containing COLMAP files (cameras.txt, images.txt)')
    parser.add_argument('--num_points', type=int, default=100000,
                        help='Number of points to sample from mesh')
    parser.add_argument('--min_observations', type=int, default=2,
                        help='Minimum number of cameras that must observe a point')
    parser.add_argument('--max_observations', type=int, default=15,
                        help='Maximum number of cameras to record for each point')
    parser.add_argument('--skip_visibility', action='store_true',
                        help='Skip visibility checking (faster but less accurate)')
    
    args = parser.parse_args()
    
    # Ensure output directory exists
    ensure_directory_exists(args.output_dir)
    
    # Load and transform mesh
    print("Loading and transforming mesh...")
    _, transformed_vertices, faces, _, _ = load_and_transform_mesh(
        args.mesh_path, args.reference_frame_path, args.z_offset
    )
    
    # Load COLMAP camera information
    cameras_file = os.path.join(args.colmap_dir, 'cameras.txt')
    images_file = os.path.join(args.colmap_dir, 'images.txt')
    
    print(f"Loading camera parameters from: {cameras_file}")
    cameras = load_cameras(cameras_file)
    
    print(f"Loading image parameters from: {images_file}")
    images = load_images(images_file)
    
    # Sample points from mesh
    print(f"Sampling {args.num_points} points from mesh...")
    points, face_indices = sample_points_from_mesh(transformed_vertices, faces, args.num_points)
    
    # Generate point cloud
    print("Generating point cloud...")
    point_cloud = generate_point_cloud(
        transformed_vertices, faces, points, face_indices, cameras, images, 
        args.min_observations, args.max_observations
    )
    
    # Write point cloud to COLMAP format
    points3D_file = os.path.join(args.output_dir, 'points3D.txt')
    write_points3D_file(point_cloud, points3D_file)
    
    # Optionally update images.txt with new points2D information
    updated_images_file = os.path.join(args.output_dir, 'images.txt')
    update_images_with_points2D(images, point_cloud, updated_images_file)
    
    print(f"All operations completed. Point cloud saved to {points3D_file}")


if __name__ == "__main__":
    main()
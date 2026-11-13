#!/usr/bin/env python3
import open3d as o3d
import numpy as np
import json
import os
import argparse

def apply_transformation(points, transform_params, z_shift=0.0):
    """
    Apply transformation parameters to point cloud
    
    Parameters:
        points: numpy array with shape (N, 3) representing point cloud coordinates
        transform_params: dictionary containing transformation parameters
        z_shift: additional shift to apply on z-axis (float)
        
    Returns:
        Transformed point cloud coordinates, numpy array with shape (N, 3)
    """
    # Extract scale and shift from transformation parameters
    scale = np.array(transform_params['base_to_canonical']['scale'])
    shift = np.array(transform_params['base_to_canonical']['shift'])
    swap_xy = transform_params['base_to_canonical']['swap_xy']
    
    # Apply scale
    transformed_points = points * scale
    
    # Apply shift
    transformed_points = transformed_points + shift
    
    # Apply additional z-shift
    transformed_points[:, 2] += z_shift
    
    # If X and Y coordinates need to be swapped
    if swap_xy:
        transformed_points[:, [0, 1]] = transformed_points[:, [1, 0]]
    
    return transformed_points

def transform_pointcloud(input_path, output_path, transform_path, z_shift=0.0):
    """
    Transform a point cloud using transformation parameters and save to a new file
    
    Parameters:
        input_path: Path to input point cloud file (.ply)
        output_path: Path to save transformed point cloud (.ply)
        transform_path: Path to transformation parameters JSON file
        z_shift: additional shift to apply on z-axis (float)
    """
    # Load the point cloud
    print(f"Loading point cloud from {input_path}")
    pcd = o3d.io.read_point_cloud(input_path)
    original_points = np.asarray(pcd.points)
    print(f"Point cloud contains {len(original_points)} points")
    
    # Load transformation parameters
    print(f"Loading transformation parameters from {transform_path}")
    with open(transform_path, 'r') as f:
        transform_params = json.load(f)
    
    # Apply transformation
    print("Applying transformation...")
    print(f"Using additional z_shift: {z_shift}")
    transformed_points = apply_transformation(original_points, transform_params, z_shift)
    
    # Create a new point cloud with transformed points
    transformed_pcd = o3d.geometry.PointCloud()
    transformed_pcd.points = o3d.utility.Vector3dVector(transformed_points)
    
    # Preserve original colors if available
    if hasattr(pcd, 'colors') and len(np.asarray(pcd.colors)) > 0:
        print("Preserving original point cloud colors...")
        transformed_pcd.colors = pcd.colors
    
    # Save the transformed point cloud
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    o3d.io.write_point_cloud(output_path, transformed_pcd)
    print(f"Transformed point cloud saved to {output_path}")
    
    # Optional: Print bounding box information to help with understanding the transformation
    bbox_original = pcd.get_axis_aligned_bounding_box()
    bbox_transformed = transformed_pcd.get_axis_aligned_bounding_box()
    
    print("\nBounding Box Information:")
    print(f"Original: Min={bbox_original.min_bound}, Max={bbox_original.max_bound}")
    print(f"Transformed: Min={bbox_transformed.min_bound}, Max={bbox_transformed.max_bound}")
    
    return transformed_pcd

def main():
    parser = argparse.ArgumentParser(description="Transform a point cloud using JSON parameters")
    parser.add_argument("--input", "-i", default="./evaluation_data/example_ply/gt.ply", help="Input point cloud file (.ply)")
    parser.add_argument("--output", "-o", default="./evaluation_data/example_ply/gt_transformed.ply", help="Output transformed point cloud file (.ply)")
    parser.add_argument("--transform", "-t", default="./LoD2Depth/data/scene_reference_frame.json", help="Transformation parameters JSON file")
    parser.add_argument("--z_shift", "-z", type=float, default=0, help="Additional shift to apply on z-axis")
    # parser.add_argument("--z_shift", "-z", type=float, default=46.55, help="Additional shift to apply on z-axis")
    
    args = parser.parse_args()
    
    try:
        transform_pointcloud(args.input, args.output, args.transform, args.z_shift)
        print("Transformation completed successfully!")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
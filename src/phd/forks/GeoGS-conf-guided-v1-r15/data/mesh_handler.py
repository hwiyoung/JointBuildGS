#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mesh loading and transformation operations.
Handles loading OBJ files and applying reference frame transformations.
"""

import os
import numpy as np
import open3d as o3d
import sys

# Add parent directory to path to import LoD2Depth modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import functions from LoD2Depth module
from LoD2Depth.mesh_loader import load_obj
from LoD2Depth.reference_frame import load_reference_frame, apply_transformation
from LoD2Depth.mesh_saver import save_obj
from LoD2Depth.raycasting import create_mesh_scene


def load_and_transform_mesh(mesh_path, reference_frame_path, z_offset=0.0):
    """
    Load an OBJ file and apply transformation based on reference frame.
    
    Parameters:
        mesh_path (str): Path to input OBJ file
        reference_frame_path (str): Path to scene reference frame JSON file
        z_offset (float): Additional Z-axis offset
        
    Returns:
        tuple: (original_vertices, transformed_vertices, faces, normals, texcoords)
    """
    print(f"Loading OBJ file: {mesh_path}")
    vertices, faces, normals, texcoords = load_obj(mesh_path)
    print(f"Loaded mesh with {len(vertices)} vertices and {len(faces)} faces")
    
    print(f"Loading scene reference frame: {reference_frame_path}")
    reference_frame = load_reference_frame(reference_frame_path)
    
    print("Applying transformation...")
    # Get transformation parameters from reference frame
    scale = reference_frame["base_to_canonical"]["scale"]
    shift = reference_frame["base_to_canonical"]["shift"]
    # Modify Z-axis offset
    modified_shift = [shift[0], shift[1], shift[2] + z_offset]
    swap_xy = reference_frame["base_to_canonical"]["swap_xy"]
    
    # Apply transformation to mesh
    transformed_vertices = apply_transformation(vertices, scale, modified_shift, swap_xy)
    print("Transformation complete")
    
    return vertices, transformed_vertices, faces, normals, texcoords


def save_transformed_mesh(output_path, vertices, faces, normals, texcoords):
    """
    Save transformed mesh to OBJ file.
    
    Parameters:
        output_path (str): Path to save transformed OBJ file
        vertices (numpy.ndarray): Transformed vertices
        faces (list): Mesh faces
        normals (list): Mesh normals
        texcoords (list): Mesh texture coordinates
    """
    print(f"Saving transformed OBJ file: {output_path}")
    save_obj(output_path, vertices, faces, normals, texcoords)
    print("Save complete")


def create_scene_for_raycasting(vertices, faces):
    """
    Create a raycasting scene from mesh vertices and faces.
    
    Parameters:
        vertices (numpy.ndarray): Mesh vertices
        faces (list): Mesh faces
        
    Returns:
        open3d.t.geometry.RaycastingScene: Scene for raycasting
    """
    print("Creating mesh scene for raycasting...")
    scene = create_mesh_scene(vertices, faces)
    return scene
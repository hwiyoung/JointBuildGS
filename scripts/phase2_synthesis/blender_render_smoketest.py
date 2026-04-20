"""Blender smoke test: load scene.obj, 1 camera, 1 render with depth/normal/semantic passes.

Verifies bpy rendering pipeline works for our 3D BAG scene before full rendering.
"""
import bpy
import json
import os
import sys
import numpy as np
from pathlib import Path

# Paths (assumes cwd = repo root)
SCENE_OBJ = Path('results/phase2_synthesis/scene.obj')
LAYOUT = Path('results/phase2_synthesis/scene_layout.json')
OUT_DIR = Path('results/phase2_synthesis/smoke_test')
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Semantic class → PassIndex (for segmentation via Object Index or Material Index)
MTL_TO_CLASS = {
    'Ground': 3,    # Terrain also but OBJ uses 'Ground' for building footprint, 'Terrain' for ground plane
    'Terrain': 3,
    'Wall': 2,
    'Roof': 1,
}


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_scene():
    bpy.ops.wm.obj_import(filepath=str(SCENE_OBJ.resolve()))
    # Count objects loaded
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    print(f'[import] {len(meshes)} mesh objects')
    # Assign pass_index per material for Material ID pass
    for mat in bpy.data.materials:
        name = mat.name.split('.')[0]  # Strip .001 etc
        if name in MTL_TO_CLASS:
            mat.pass_index = MTL_TO_CLASS[name]
            print(f'  material {mat.name} -> pass_index {mat.pass_index}')


def setup_camera(location, look_at, fov_deg=60):
    """Create a camera at location looking at look_at."""
    cam_data = bpy.data.cameras.new('Camera')
    cam_data.lens_unit = 'FOV'
    cam_data.angle = np.radians(fov_deg)
    cam = bpy.data.objects.new('Camera', cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = location
    # Look at: set rotation to point -Z axis toward look_at
    direction = np.array(look_at) - np.array(location)
    direction = direction / np.linalg.norm(direction)
    # Blender cam looks down -Z by default; align -Z with direction
    # Compute rotation from (0,0,-1) to direction
    from mathutils import Vector, Matrix
    rot_quat = Vector((0, 0, -1)).rotation_difference(Vector(direction.tolist()))
    cam.rotation_mode = 'QUATERNION'
    cam.rotation_quaternion = rot_quat
    bpy.context.scene.camera = cam
    return cam


def setup_render(resolution=(800, 600), samples=16):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.render.resolution_x = resolution[0]
    scene.render.resolution_y = resolution[1]
    scene.render.resolution_percentage = 100
    scene.cycles.samples = samples
    scene.cycles.device = 'GPU' if bpy.context.preferences.addons.get('cycles') else 'CPU'
    # Use Experimental feature set for stable material index pass
    scene.view_layers['ViewLayer'].use_pass_z = True
    scene.view_layers['ViewLayer'].use_pass_normal = True
    scene.view_layers['ViewLayer'].use_pass_material_index = True
    # Output format
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '8'
    # Enable compositor nodes for multi-pass output
    scene.use_nodes = True


def setup_compositor(out_prefix):
    scene = bpy.context.scene
    tree = scene.node_tree
    # Clear
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    # Render Layers
    rl = tree.nodes.new('CompositorNodeRLayers')
    # Viewer (standard RGB)
    out_rgb = tree.nodes.new('CompositorNodeOutputFile')
    out_rgb.base_path = str(out_prefix.parent)
    out_rgb.file_slots[0].path = f'{out_prefix.name}_rgb_'
    out_rgb.format.file_format = 'PNG'
    out_rgb.format.color_mode = 'RGB'
    out_rgb.format.color_depth = '8'
    tree.links.new(rl.outputs['Image'], out_rgb.inputs[0])

    # Depth: save as OpenEXR
    out_z = tree.nodes.new('CompositorNodeOutputFile')
    out_z.base_path = str(out_prefix.parent)
    out_z.file_slots[0].path = f'{out_prefix.name}_depth_'
    out_z.format.file_format = 'OPEN_EXR'
    out_z.format.color_mode = 'BW'
    out_z.format.color_depth = '32'
    tree.links.new(rl.outputs['Depth'], out_z.inputs[0])

    # Normal: save as OpenEXR
    out_n = tree.nodes.new('CompositorNodeOutputFile')
    out_n.base_path = str(out_prefix.parent)
    out_n.file_slots[0].path = f'{out_prefix.name}_normal_'
    out_n.format.file_format = 'OPEN_EXR'
    out_n.format.color_mode = 'RGB'
    out_n.format.color_depth = '32'
    tree.links.new(rl.outputs['Normal'], out_n.inputs[0])

    # Semantic via Material Index pass: needs ID Mask or direct IndexMA output
    # Use the IndexMA output directly, remap to grayscale
    out_sem = tree.nodes.new('CompositorNodeOutputFile')
    out_sem.base_path = str(out_prefix.parent)
    out_sem.file_slots[0].path = f'{out_prefix.name}_sem_'
    out_sem.format.file_format = 'OPEN_EXR'
    out_sem.format.color_mode = 'BW'
    out_sem.format.color_depth = '16'
    tree.links.new(rl.outputs['IndexMA'], out_sem.inputs[0])


def main():
    reset_scene()
    import_scene()
    layout = json.loads(LAYOUT.read_text())
    # Scene bbox center for camera target
    bbox_min = np.array(layout['scene_bbox_min'])
    bbox_max = np.array(layout['scene_bbox_max'])
    center = (bbox_min + bbox_max) / 2
    print(f'scene center: {center}, bbox extent: {bbox_max - bbox_min}')

    # Place one camera at elevated oblique angle
    cam_loc = (center[0] + 30, -40, center[2] + 30)  # -40 in Y = high up (COLMAP -Y up)
    cam = setup_camera(cam_loc, center.tolist())
    print(f'camera at {cam_loc} looking at {center.tolist()}')

    setup_render(resolution=(800, 600), samples=16)
    out_prefix = OUT_DIR / 'v001'
    setup_compositor(out_prefix)

    bpy.context.scene.frame_set(0)
    bpy.ops.render.render(write_still=False)
    print(f'rendered to {OUT_DIR}')


if __name__ == '__main__':
    main()

"""Blender 4.3 full scene renderer: aerial + oblique + perimeter camera sampling.

Produces raw Blender EXR/PNG outputs per view; pair with postprocess_exr.py.

Camera strategy (adaptive to scene bbox):
  - Aerial nadir grid: GRID_NX × GRID_NY cameras straight above, looking down
    with slight inward tilt for multi-view triangulation baseline
  - Oblique rings: 3 tilt angles (30°, 45°, 60°) × 12 azimuths, pointed at scene center
  - Perimeter orbit: 1 ring at roof level, 12 azimuths around the scene
Total default: 25 + 36 + 12 = 73 views.
"""
import bpy
import json
import math
from pathlib import Path

import numpy as np
from mathutils import Vector, Matrix

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENE_OBJ = REPO_ROOT / 'results/phase2_synthesis/scene.obj'
OUT_DIR = REPO_ROOT / 'results/phase2_synthesis/renders_raw'
OUT_DIR.mkdir(parents=True, exist_ok=True)

MTL_TO_CLASS = {'Ground': 3, 'Terrain': 3, 'Wall': 2, 'Roof': 1}
DEPTH_SKY_CLAMP = 29000.0

RES_W, RES_H = 800, 600
SAMPLES = 32
FOV_DEG = 50.0

GRID_NX, GRID_NY = 5, 5
RING_AZIMUTHS = 12
RING_TILTS = [30, 45, 60]           # degrees from nadir (0=straight down)
NADIR_TILT_IN = 8                   # degrees inward tilt for grid views


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_scene():
    bpy.ops.wm.obj_import(filepath=str(SCENE_OBJ))
    for o in bpy.data.objects:
        if o.type == 'MESH':
            for poly in o.data.polygons:
                poly.use_smooth = False
    for mat in bpy.data.materials:
        name = mat.name.split('.')[0]
        if name in MTL_TO_CLASS:
            mat.pass_index = MTL_TO_CLASS[name]


def add_lighting():
    sun_data = bpy.data.lights.new('Sun', 'SUN')
    sun_data.energy = 3.0
    sun_data.angle = math.radians(5)
    sun = bpy.data.objects.new('Sun', sun_data)
    bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(40), math.radians(20), math.radians(30))
    world = bpy.data.worlds.new('World')
    world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.55, 0.70, 0.85, 1.0)
    bg.inputs['Strength'].default_value = 0.25
    bpy.context.scene.world = world


def scene_bbox_blender():
    xs, ys, zs = [], [], []
    for o in bpy.data.objects:
        if o.type != 'MESH':
            continue
        for v in o.data.vertices:
            w = o.matrix_world @ v.co
            xs.append(w.x); ys.append(w.y); zs.append(w.z)
    return (np.array([min(xs), min(ys), min(zs)]),
            np.array([max(xs), max(ys), max(zs)]))


def setup_camera_obj():
    cam_data = bpy.data.cameras.new('Camera')
    cam_data.lens_unit = 'FOV'
    cam_data.angle = math.radians(FOV_DEG)
    cam = bpy.data.objects.new('Camera', cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    return cam


def aim_camera(cam, loc, target, up=(0, 0, -1)):
    """Place cam at `loc` looking at `target` with explicit world-up hint (Blender frame)."""
    loc_v = Vector(loc)
    forward = (Vector(target) - loc_v).normalized()
    up_v = Vector(up).normalized()
    # If forward || up, pick a fallback horizontal up
    if abs(forward.dot(up_v)) > 0.999:
        up_v = Vector((1, 0, 0)) if abs(forward.x) < 0.9 else Vector((0, 1, 0))
    right = forward.cross(up_v).normalized()
    cam_up = right.cross(forward).normalized()
    rot = Matrix((right, cam_up, -forward)).transposed().to_4x4()
    cam.matrix_world = Matrix.Translation(loc_v) @ rot


def setup_render():
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.render.resolution_x = RES_W
    scene.render.resolution_y = RES_H
    scene.render.resolution_percentage = 100
    scene.cycles.samples = SAMPLES
    try:
        scene.cycles.device = 'GPU'
    except Exception:
        pass
    vl = scene.view_layers['ViewLayer']
    vl.use_pass_z = True
    vl.use_pass_normal = True
    vl.use_pass_material_index = True
    scene.use_nodes = True


def setup_compositor(prefix):
    scene = bpy.context.scene
    tree = scene.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    rl = tree.nodes.new('CompositorNodeRLayers')

    def file_out(label, slot, fmt, cm, depth, upstream=None):
        node = tree.nodes.new('CompositorNodeOutputFile')
        node.base_path = str(prefix.parent)
        node.file_slots[0].path = f'{prefix.name}_{label}_'
        node.format.file_format = fmt
        node.format.color_mode = cm
        node.format.color_depth = depth
        tree.links.new(upstream if upstream else rl.outputs[slot], node.inputs[0])
        return node

    file_out('rgb', 'Image', 'PNG', 'RGB', '8')

    clamp = tree.nodes.new('CompositorNodeMath')
    clamp.operation = 'MINIMUM'
    clamp.inputs[1].default_value = DEPTH_SKY_CLAMP
    tree.links.new(rl.outputs['Depth'], clamp.inputs[0])
    file_out('depth', 'Depth', 'OPEN_EXR', 'BW', '32', upstream=clamp.outputs[0])

    file_out('normal', 'Normal', 'OPEN_EXR', 'RGB', '32')
    file_out('sem', 'IndexMA', 'OPEN_EXR', 'BW', '32')


def camera_pose_dict(cam):
    M = np.array(cam.matrix_world)
    flip = np.diag([1.0, -1.0, -1.0, 1.0])
    c2w_cv = M @ flip
    w2c_cv = np.linalg.inv(c2w_cv)
    scene = bpy.context.scene
    W, H = scene.render.resolution_x, scene.render.resolution_y
    fx = W * cam.data.lens / cam.data.sensor_width
    return {
        'W': W, 'H': H, 'fx': fx, 'fy': fx,
        'cx': W / 2.0, 'cy': H / 2.0,
        'w2c': w2c_cv.tolist(),
        'c2w': c2w_cv.tolist(),
    }


def generate_cameras(bbox_min, bbox_max):
    """Return list of (view_name, loc_bl, target_bl, up_bl) tuples."""
    center = (bbox_min + bbox_max) / 2
    extent = bbox_max - bbox_min
    # In Blender: physical up is -Z (OBJ import flipped COLMAP -Y up to Blender -Z).
    # Roofs at bbox_min[2] (most negative Z).
    max_xy = max(extent[0], extent[1])
    altitude = bbox_min[2] - max_xy * 0.7      # above roofs by ~70% of scene width
    radius = max_xy * 0.75                      # horizontal distance from center
    up_bl = (0, 0, -1)                          # physical up = Blender -Z
    cams = []

    # 1) Aerial nadir grid — target = ground point below (straight down) blended toward center for tilt_in°
    ground_z = bbox_max[2]  # Blender +Z ground (scene ground at Z≈0)
    tilt_frac = math.sin(math.radians(NADIR_TILT_IN))
    for iy in range(GRID_NY):
        for ix in range(GRID_NX):
            fx = (ix + 0.5) / GRID_NX - 0.5
            fy = (iy + 0.5) / GRID_NY - 0.5
            x = center[0] + fx * extent[0] * 0.8
            y = center[1] + fy * extent[1] * 0.8
            loc = (x, y, altitude)
            straight_down_tgt = np.array([x, y, ground_z])
            toward_center_tgt = np.array([center[0], center[1], ground_z])
            target = (1 - tilt_frac) * straight_down_tgt + tilt_frac * toward_center_tgt
            cams.append((f'nadir_{iy:02d}_{ix:02d}', loc, target.tolist(), up_bl))

    # 2) Oblique rings
    for tilt_deg in RING_TILTS:
        for ai in range(RING_AZIMUTHS):
            az = 2 * math.pi * ai / RING_AZIMUTHS
            tilt = math.radians(tilt_deg)
            # Spherical coords: tilt from nadir (0° = straight down)
            # Camera is offset from center by radius*sin(tilt) horizontally,
            # and up by |altitude|*cos(tilt) above scene top
            horiz_r = radius * math.sin(tilt)
            vert_h = altitude + (0 - altitude) * (1 - math.cos(tilt)) * 0.3  # gentle lift
            x = center[0] + horiz_r * math.cos(az)
            y = center[1] + horiz_r * math.sin(az)
            z = vert_h
            cams.append((f'oblique_t{tilt_deg:02d}_a{ai:02d}',
                         (x, y, z), center.tolist(), up_bl))

    # 3) Perimeter orbit at roof level
    orbit_z = bbox_min[2] - max_xy * 0.05  # just above roofs
    orbit_r = max_xy * 0.9
    for ai in range(RING_AZIMUTHS):
        az = 2 * math.pi * ai / RING_AZIMUTHS
        x = center[0] + orbit_r * math.cos(az)
        y = center[1] + orbit_r * math.sin(az)
        cams.append((f'orbit_a{ai:02d}', (x, y, orbit_z), center.tolist(), up_bl))

    return cams


def render_view(cam, name):
    prefix = OUT_DIR / name
    setup_compositor(prefix)
    (OUT_DIR / f'{name}_cam.json').write_text(json.dumps(camera_pose_dict(cam), indent=2))
    bpy.context.scene.frame_set(0)
    bpy.ops.render.render(write_still=False)


def main():
    reset()
    import_scene()
    add_lighting()
    bbox_min, bbox_max = scene_bbox_blender()
    print(f'[bbox] min={bbox_min} max={bbox_max}')
    cams = generate_cameras(bbox_min, bbox_max)
    print(f'[cameras] generated {len(cams)} views')

    cam = setup_camera_obj()
    setup_render()

    for i, (name, loc, target, up) in enumerate(cams):
        aim_camera(cam, loc, target, up=up)
        render_view(cam, name)
        if (i + 1) % 10 == 0 or i == 0:
            print(f'  [{i+1:3d}/{len(cams)}] {name}')
    print(f'[done] {len(cams)} views rendered to {OUT_DIR}')


if __name__ == '__main__':
    main()

"""Blender 4.3 scene renderer — UAV Pix4D-standard mission (DJI P4 RTK proxy).

Camera strategy: at each nadir waypoint on a regular grid, capture 5 images:
  1 nadir (straight down) + 4 oblique (45° tilt facing N/E/S/W).
Grid spacing derived from Pix4D 80% forward / 70% side overlap targets.

Spec basis:
  - Platform: DJI Phantom 4 RTK proxy (5472×3648 @ 74° h-FOV, downsampled 2.67× for GS training)
  - Altitude: 80 m AGL (Pix4D default, both nadir and oblique)
  - Resolution: 2048×1536 (4:3) for training (GSD ≈ 5.5 cm at 80m)
  - Overlap: 80% forward / 70% side
  - Oblique: 45° tilt × 4 cardinal (Pix4D double-grid + oblique standard)
  - NO orbit (not a standard UAV mapping product; excluded for Pix4D conformance)

Produces raw Blender EXR/PNG; pair with postprocess_exr.py.
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
DEPTH_SKY_CLAMP = 30000.0  # > any realistic UAV depth

# ------------ camera specs (Pix4D-standard UAV mission) ------------
RES_W, RES_H = 2048, 1536
SAMPLES = 32
FOV_DEG = 74.0                   # DJI P4 RTK horizontal FOV
ALTITUDE = 80.0                  # AGL meters (Pix4D standard)

FORWARD_OVERLAP = 0.80           # along-Z spacing
SIDE_OVERLAP    = 0.70           # along-X spacing

OBLIQUE_TILT_DEG = 45.0          # Pix4D oblique standard
# Cardinal directions that the oblique camera looks toward (XZ plane)
OBLIQUE_AZIMUTHS = [0, 90, 180, 270]  # N, E, S, W (degrees)


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
    add_procedural_texture_to_materials()


def add_procedural_texture_to_materials():
    """Add Perlin noise variation to each material's base color.

    Flat material colors (RGB ≈ semantic label) make L_photo trivial and
    weaken the L_mutual semantic↔geometry feedback measurement. This breaks
    the trivial correspondence while keeping:
      - Semantic pass unchanged (driven by material pass_index, not color)
      - Depth/Normal passes unchanged (geometry-only)
      - Per-class color identity preserved (dominant color)

    Design:
      - Noise uses WORLD (Generated) coords, scale ~0.05 (very wide features,
        ~5-10 m patches across the scene). World coords are continuous across
        object boundaries so adjacent walls blend smoothly.
      - ColorRamp expands contrast: narrow input range (0.25-0.75) → full
        grayscale (0.3 to 1.0), so multiplier range covers 0.3 × base to
        1.0 × base = 70 % brightness variation.
      - MULTIPLY against base color (clamped ≤1).
    """
    # Scale unit here: cycles across object's Generated-coord bbox (0-1).
    # Scene buildings are ~10-20m wide, so scale=3.0 → 3 cycles → ~3-6m patches
    # (well above GSD 5.9 cm, well below building size for visible variation).
    params = {
        'Roof':    {'scale': 3.5, 'ramp_lo': 0.35, 'ramp_hi': 1.00,
                    'pos_lo': 0.25, 'pos_hi': 0.75, 'detail': 6.0},
        'Wall':    {'scale': 2.5, 'ramp_lo': 0.40, 'ramp_hi': 1.00,
                    'pos_lo': 0.25, 'pos_hi': 0.75, 'detail': 5.0},
        'Ground':  {'scale': 5.0, 'ramp_lo': 0.50, 'ramp_hi': 1.00,
                    'pos_lo': 0.25, 'pos_hi': 0.75, 'detail': 5.0},
        'Terrain': {'scale': 4.0, 'ramp_lo': 0.55, 'ramp_hi': 1.00,
                    'pos_lo': 0.25, 'pos_hi': 0.75, 'detail': 4.0},
    }
    for mat in bpy.data.materials:
        name = mat.name.split('.')[0]
        if name not in params:
            continue
        p = params[name]
        if not mat.use_nodes:
            mat.use_nodes = True
        nt = mat.node_tree
        nodes = nt.nodes
        links = nt.links
        bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is None:
            continue
        base = tuple(bsdf.inputs['Base Color'].default_value[:3])
        # Clean any previously-added texture nodes (re-invocation safety)
        for n in list(nodes):
            if n.type in ('TEX_COORD', 'MAPPING', 'TEX_NOISE', 'VALTORGB', 'MIX_RGB'):
                nodes.remove(n)
        # Drop any link into BSDF Base Color
        for link in list(links):
            if link.to_socket == bsdf.inputs['Base Color']:
                links.remove(link)

        # Chain: TexCoord.Generated → Noise → ColorRamp → MixMultiply → BSDF
        coord = nodes.new('ShaderNodeTexCoord'); coord.location = (-900, 0)
        noise = nodes.new('ShaderNodeTexNoise'); noise.location = (-600, 0)
        noise.noise_dimensions = '3D'
        noise.inputs['Scale'].default_value = p['scale']
        noise.inputs['Detail'].default_value = p['detail']
        noise.inputs['Roughness'].default_value = 0.6

        ramp = nodes.new('ShaderNodeValToRGB'); ramp.location = (-350, 0)
        # Expand contrast: narrow input range so small noise fac changes → full output swing
        ramp.color_ramp.elements[0].position = p['pos_lo']
        ramp.color_ramp.elements[1].position = p['pos_hi']
        ramp.color_ramp.elements[0].color = (p['ramp_lo'],) * 3 + (1.0,)
        ramp.color_ramp.elements[1].color = (p['ramp_hi'],) * 3 + (1.0,)
        ramp.color_ramp.interpolation = 'LINEAR'

        mix = nodes.new('ShaderNodeMixRGB'); mix.location = (-100, 0)
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Fac'].default_value = 1.0
        mix.inputs['Color1'].default_value = (*base, 1.0)

        # Use Generated (object-local 0-1 normalized) rather than Object so texture
        # tiles the same across object bbox. Generated is continuous per-mesh-island.
        links.new(coord.outputs['Generated'], noise.inputs['Vector'])
        links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
        links.new(ramp.outputs['Color'], mix.inputs['Color2'])
        links.new(mix.outputs['Color'], bsdf.inputs['Base Color'])


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
    # M = camera-local -> Blender world.
    # flip = (y,z) sign swap: OpenGL camera axes -> OpenCV camera axes.
    # T_obj_to_bl = OBJ world -> Blender world. Blender imported the OBJ with the
    # default axis swap "OBJ Y up -> Blender Z up", which maps points
    # (x, y, z)_obj -> (x, -z, y)_bl. We write w2c in OBJ world so it matches
    # scene.obj / points3D.bin (COLMAP -Y up). Prevents the Step 2-1 frame bug.
    M = np.array(cam.matrix_world)
    flip = np.diag([1.0, -1.0, -1.0, 1.0])
    T_obj_to_bl = np.array([
        [1, 0,  0, 0],
        [0, 0, -1, 0],
        [0, 1,  0, 0],
        [0, 0,  0, 1],
    ], dtype=float)
    c2w_cv_bl = M @ flip                            # OpenCV-cam -> Blender-world
    w2c_cv_bl = np.linalg.inv(c2w_cv_bl)            # Blender-world -> OpenCV-cam
    w2c_cv = w2c_cv_bl @ T_obj_to_bl                # OBJ-world -> OpenCV-cam
    c2w_cv = np.linalg.inv(w2c_cv)
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
    """Generate UAV Pix4D-standard camera positions over the scene.

    Coord frame notes (Blender-world after default OBJ import):
      - OBJ -Y up maps to Blender -Z up, so "physical up" in Blender is -Z.
      - Scene roofs are at most-negative Z (bbox_min[2]), ground at ~Z=0.
      - Camera altitude ALTITUDE meters above the highest roof.

    Strategy:
      - Determine ground footprint per image at ALTITUDE from FOV_DEG + aspect.
      - Derive nadir grid spacing from (1 - overlap) × footprint.
      - At each nadir waypoint: 1 nadir image + 4 oblique images
        (45° tilt, facing cardinal directions toward scene). 5 captures/waypoint.
    """
    extent = bbox_max - bbox_min
    cx, cy = (bbox_min[0] + bbox_max[0]) / 2, (bbox_min[1] + bbox_max[1]) / 2
    # Z is Blender "up" axis with flipped sign (scene ground at Z≈0, roofs at negative Z).
    ground_z = bbox_max[2]                # scene ground (least-negative Z)
    roof_top_z = bbox_min[2]              # highest roof (most-negative Z)
    altitude_z = roof_top_z - ALTITUDE    # camera altitude in Blender frame (more negative = higher)

    # Ground footprint per image at ALTITUDE (distance from camera to ground = ALTITUDE
    # + however deep we look to the ground; approximate with ALTITUDE for Pix4D standard)
    hfov = math.radians(FOV_DEG)
    footprint_w = 2 * ALTITUDE * math.tan(hfov / 2)             # along camera X
    # vertical FOV from aspect
    vfov = 2 * math.atan(math.tan(hfov / 2) * RES_H / RES_W)
    footprint_h = 2 * ALTITUDE * math.tan(vfov / 2)             # along camera Y

    # Along-track (Z in Blender XY plane convention; really we pick X=along-track, Y=across)
    # Pix4D: forward = primary flight direction, we call it +X.
    # Actually we're using XY-plane with X east, Y north (Blender convention).
    # For simplicity: X = side, Y = forward. side_overlap 70% on X, fwd_overlap 80% on Y.
    side_spacing = (1 - SIDE_OVERLAP) * footprint_w         # X direction
    fwd_spacing = (1 - FORWARD_OVERLAP) * footprint_h       # Y direction
    n_cols = max(2, int(math.ceil(extent[0] / side_spacing)) + 1)
    n_rows = max(2, int(math.ceil(extent[1] / fwd_spacing)) + 1)
    # Evenly distribute n waypoints across the scene extent
    if n_cols > 1:
        xs = np.linspace(bbox_min[0], bbox_max[0], n_cols)
    else:
        xs = np.array([cx])
    if n_rows > 1:
        ys = np.linspace(bbox_min[1], bbox_max[1], n_rows)
    else:
        ys = np.array([cy])

    up_bl = (0, 0, -1)  # physical up in Blender frame
    cams = []

    # Compute once: oblique look-at vector for each azimuth.
    # azimuth 0 = +Y (north), 90 = +X (east), 180 = -Y (south), 270 = -X (west)
    # Oblique camera tilts 45° toward the scene → it looks down-and-toward-target.
    tilt = math.radians(OBLIQUE_TILT_DEG)
    # Horizontal offset from waypoint to a target in the looking direction:
    # Place target at (waypoint_xy + unit_azimuth * ALTITUDE*tan(tilt)) and ground z.
    obl_target_offset = ALTITUDE * math.tan(tilt)

    for iy, y in enumerate(ys):
        for ix, x in enumerate(xs):
            loc = (float(x), float(y), float(altitude_z))
            # Nadir: look straight down
            nadir_target = (float(x), float(y), float(ground_z))
            cams.append((f'waypt_{iy:02d}_{ix:02d}_nadir',
                         loc, nadir_target, up_bl))
            # 4 oblique captures at same waypoint, rotated azimuth
            for az_deg in OBLIQUE_AZIMUTHS:
                az = math.radians(az_deg)
                tx = x + obl_target_offset * math.sin(az)
                ty = y + obl_target_offset * math.cos(az)
                target = (float(tx), float(ty), float(ground_z))
                cams.append((f'waypt_{iy:02d}_{ix:02d}_oblique_az{az_deg:03d}',
                             loc, target, up_bl))

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

"""Load 20 selected 3D BAG buildings → arrange in grid → export single scene mesh.

Output: scene.obj with per-face semantic material tags.
  - 5x4 grid (buildings spaced 15m apart)
  - Each building translated so its ground footprint centered at grid position,
    ground at Y=0 (COLMAP: -Y up, so Y=0 is ground, -Y is up).
  - Large ground plane added at Y=0 spanning entire scene
  - Semantic per face via material name: Roof / Wall / Ground / Terrain
"""
import json, sys, glob
import numpy as np
from pathlib import Path
sys.path.insert(0, 'scripts/synthetic_a')
from buildings_3dbag import parse_tile

GRID_COLS = 5
GRID_ROWS = 4
SPACING = 18.0  # m between building centers
GROUND_PAD = 10.0  # m extra ground around grid edge
OUT_DIR = Path('results/phase2_synthesis')

# Label mapping (buildings_3dbag.py: 1=Roof, 2=Wall, 3=Ground)
LABEL_TO_NAME = {1: 'Roof', 2: 'Wall', 3: 'Ground'}


def load_selected():
    tiles = sorted(glob.glob('results/synthetic_a/3dbag_raw/amsterdam_jordaan/*.city.json'))
    all_bldgs = []
    for t in tiles: all_bldgs.extend(parse_tile(t))
    sel_meta = json.load(open(OUT_DIR / 'selected_buildings.json'))
    sel_names = {s['name']: s['sel_id'] for s in sel_meta}
    selected = []
    for b in all_bldgs:
        if b['name'] in sel_names:
            b['sel_id'] = sel_names[b['name']]
            selected.append(b)
    selected.sort(key=lambda b: b['sel_id'])
    return selected


def place_building(b, tx, tz):
    """Translate vertices so building footprint center is at (tx, *, tz), ground at Y=0.

    COLMAP up = -Y, so ground = max Y (least -up), roof = min Y (most +up).
    Translate building so ground aligns with Y=0, XZ center at (tx, tz).
    """
    v = np.array(b['vertices'], dtype=np.float32)
    ground_y = v[:, 1].max()  # ground = max Y in COLMAP -Y up convention
    v[:, 1] -= ground_y  # now ground at Y=0, building up at Y<0
    cx = (v[:, 0].min() + v[:, 0].max()) * 0.5
    cz = (v[:, 2].min() + v[:, 2].max()) * 0.5
    v[:, 0] += tx - cx
    v[:, 2] += tz - cz
    return v


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    selected = load_selected()
    print(f'Loaded {len(selected)} selected buildings')

    # Build a combined OBJ with per-face material (material name = semantic class)
    lines_obj = ['# Phase 2 Step 2-1 scene: 20 3D BAG buildings in 5x4 grid']
    lines_obj.append('mtllib scene.mtl')
    mtls = {'Roof':(0.86,0.24,0.24), 'Wall':(0.24,0.31,0.78), 'Ground':(0.35,0.62,0.35), 'Terrain':(0.50,0.55,0.45)}
    v_offset = 1  # OBJ indices are 1-based

    scene_info = []
    for b in selected:
        i = b['sel_id']
        col = i % GRID_COLS
        row = i // GRID_COLS
        tx = (col - (GRID_COLS-1)/2) * SPACING
        tz = (row - (GRID_ROWS-1)/2) * SPACING
        v = place_building(b, tx, tz)
        lines_obj.append(f'# Building {i}: {b["name"]} ({b["type"]}) at grid ({col},{row}) = ({tx:.1f},{tz:.1f})')
        lines_obj.append(f'o building_{i:02d}_{b["type"]}')
        for vx, vy, vz in v:
            lines_obj.append(f'v {vx:.4f} {vy:.4f} {vz:.4f}')
        for f_idx, face in enumerate(b['faces']):
            label = b['labels'][f_idx]
            mtl_name = LABEL_TO_NAME.get(label, 'Wall')
            lines_obj.append(f'usemtl {mtl_name}')
            lines_obj.append(f's off')
            # OBJ face: 1-based indices
            face_str = 'f ' + ' '.join(str(idx + v_offset) for idx in face)
            lines_obj.append(face_str)
        v_offset += len(v)
        # Record bounding box in final positions
        scene_info.append({
            'sel_id': i, 'name': b['name'], 'type': b['type'],
            'grid_xz': [float(tx), float(tz)],
            'bbox_min': v.min(axis=0).tolist(),
            'bbox_max': v.max(axis=0).tolist(),
            'n_faces': len(b['faces']),
        })

    # Add ground plane (large flat quad at Y=0, Terrain material)
    grid_half_x = (GRID_COLS-1) * SPACING / 2 + GROUND_PAD
    grid_half_z = (GRID_ROWS-1) * SPACING / 2 + GROUND_PAD
    lines_obj.append('# Ground plane (Terrain)')
    lines_obj.append('o ground_plane')
    # 4 corners of ground plane at Y=0
    gp = [
        (-grid_half_x, 0.0, -grid_half_z),
        ( grid_half_x, 0.0, -grid_half_z),
        ( grid_half_x, 0.0,  grid_half_z),
        (-grid_half_x, 0.0,  grid_half_z),
    ]
    for vx, vy, vz in gp:
        lines_obj.append(f'v {vx:.4f} {vy:.4f} {vz:.4f}')
    lines_obj.append('usemtl Terrain')
    lines_obj.append('s off')
    lines_obj.append(f'f {v_offset} {v_offset+1} {v_offset+2} {v_offset+3}')
    v_offset += 4

    # Write OBJ
    (OUT_DIR / 'scene.obj').write_text('\n'.join(lines_obj))
    # Write MTL
    mtl_lines = []
    for name, (r, g, bl) in mtls.items():
        mtl_lines.append(f'newmtl {name}')
        mtl_lines.append(f'Kd {r:.3f} {g:.3f} {bl:.3f}')
        mtl_lines.append(f'Ka 0.100 0.100 0.100')
        mtl_lines.append(f'Ks 0.000 0.000 0.000')
        mtl_lines.append(f'Ns 1')
        mtl_lines.append(f'd 1')
    (OUT_DIR / 'scene.mtl').write_text('\n'.join(mtl_lines))

    # Scene info
    info = {
        'n_buildings': len(selected),
        'grid': {'cols': GRID_COLS, 'rows': GRID_ROWS, 'spacing': SPACING},
        'ground_extent_xz': [-grid_half_x, grid_half_x, -grid_half_z, grid_half_z],
        'scene_bbox_min': [-grid_half_x, min(b['bbox_min'][1] for b in scene_info), -grid_half_z],
        'scene_bbox_max': [ grid_half_x, 0.0, grid_half_z],
        'buildings': scene_info,
    }
    (OUT_DIR / 'scene_layout.json').write_text(json.dumps(info, indent=2))

    total_verts = sum(b['n_vertices'] for b in json.load(open(OUT_DIR/'selected_buildings.json')))
    total_faces = sum(b['n_faces'] for b in scene_info)
    print(f'\nScene:')
    print(f'  grid: {GRID_COLS}x{GRID_ROWS}, spacing {SPACING}m')
    print(f'  scene bbox: X=[{-grid_half_x:.1f},{grid_half_x:.1f}] Z=[{-grid_half_z:.1f},{grid_half_z:.1f}]')
    print(f'  Y extent: [{info["scene_bbox_min"][1]:.1f}, 0] ({-info["scene_bbox_min"][1]:.1f}m tall)')
    print(f'  total building faces: {total_faces}, ground plane: 1 quad')
    print(f'  total vertices: {total_verts} + 4 ground = {total_verts+4}')
    print(f'\nwrote {OUT_DIR}/scene.obj, scene.mtl, scene_layout.json')

if __name__ == '__main__':
    main()

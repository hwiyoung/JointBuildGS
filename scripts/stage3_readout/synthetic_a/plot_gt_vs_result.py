#!/usr/bin/env python3
"""
GT vs Stage 3 Result comparison visualization with annotations.

Generates annotated comparison of Stage 3 results across noise conditions
for representative buildings of each roof type.

Layout:
  Columns = 4 roof types (flat, gable, hip, complex)
  Rows = 3 noise conditions (clean, normal_10deg, normal_20deg)
  Each cell = single 3D view with metric annotations

The clean row serves as the reference (baseline). Subsequent rows show
how normal noise degrades the result.

Usage:
  python scripts/stage3_synthetic/plot_gt_vs_result.py
"""

import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ─────────────────────────────────────────────────────────────────────────────
# CityJSON 3D rendering
# ─────────────────────────────────────────────────────────────────────────────

SEMANTIC_COLORS = {
    'RoofSurface': '#E74C3C',
    'WallSurface': '#BDC3C7',
    'GroundSurface': '#F1C40F',
}
SEMANTIC_EDGE_COLORS = {
    'RoofSurface': '#C0392B',
    'WallSurface': '#95A5A6',
    'GroundSurface': '#D4AC0D',
}


def load_cityjson_faces(path):
    """Load CityJSON file and return list of (vertices_array, semantic_type)."""
    with open(path) as f:
        cj = json.load(f)
    scale = np.array(cj['transform']['scale'])
    translate = np.array(cj['transform']['translate'])
    verts = np.array(cj['vertices'], dtype=np.float64) * scale + translate

    faces = []
    for obj in cj['CityObjects'].values():
        for geom in obj.get('geometry', []):
            sem = geom.get('semantics', {})
            surfaces = sem.get('surfaces', [])
            values = sem.get('values', [[]])[0]
            boundaries = geom.get('boundaries', [[]])[0]

            for fi, face_rings in enumerate(boundaries):
                ring = face_rings[0]
                if len(ring) < 3:
                    continue
                pts = verts[ring]
                stype = 'Unknown'
                if fi < len(values) and values[fi] is not None and values[fi] < len(surfaces):
                    stype = surfaces[values[fi]].get('type', 'Unknown')
                faces.append((pts, stype))
    return faces


def _reorient(pts):
    """Convert from CityJSON local coords (up = -Y) to matplotlib (up = +Z).

    In the Stage 3 CityJSON output, the vertical axis is -Y
    (ground at Y≈0, roof at Y≈-16). Matplotlib uses Z as up.
    Mapping: X→X, Z→Y, -Y→Z.
    """
    return np.column_stack([pts[:, 0], pts[:, 2], -pts[:, 1]])


def render_building_3d(ax, faces, ref_center=None, ref_extent=None,
                       elev=30, azim=-50):
    """Render a building's faces on a 3D axis with semantic coloring.

    If ref_center and ref_extent are provided, use them for consistent
    view framing across subplots.
    """
    # Reorient all faces so Z is up
    reoriented = [((_reorient(pts), stype)) for pts, stype in faces]
    all_pts = np.concatenate([f[0] for f in reoriented], axis=0) if reoriented else np.zeros((1, 3))

    if ref_center is None:
        ref_center = all_pts.mean(axis=0)
    if ref_extent is None:
        ref_extent = max((all_pts.max(axis=0) - all_pts.min(axis=0)).max(), 0.01)

    polys = []
    facecolors = []
    edgecolors = []

    for pts, stype in reoriented:
        centered = pts - ref_center
        polys.append(centered)
        facecolors.append(SEMANTIC_COLORS.get(stype, '#AAAAAA'))
        edgecolors.append(SEMANTIC_EDGE_COLORS.get(stype, '#666666'))

    if polys:
        pc = Poly3DCollection(polys, alpha=0.85, linewidths=0.6)
        pc.set_facecolor(facecolors)
        pc.set_edgecolor(edgecolors)
        ax.add_collection3d(pc)

    half = ref_extent * 0.6
    ax.set_xlim(-half, half)
    ax.set_ylim(-half, half)
    ax.set_zlim(-half, half)
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()


def get_building_frame(cityjson_path):
    """Get center and extent from a CityJSON file for consistent framing."""
    faces = load_cityjson_faces(cityjson_path)
    if not faces:
        return np.zeros(3), 1.0
    all_pts = np.concatenate([_reorient(f[0]) for f in faces], axis=0)
    center = all_pts.mean(axis=0)
    extent = max((all_pts.max(axis=0) - all_pts.min(axis=0)).max(), 0.01)
    return center, extent


# ─────────────────────────────────────────────────────────────────────────────
# Building selection
# ─────────────────────────────────────────────────────────────────────────────

def _get_roof_slope(bid, out_base):
    """Check if a building's clean result has visually sloped roof surfaces."""
    path = os.path.join(out_base, f'3dbag_results/clean/b{bid:03d}/building.city.json')
    if not os.path.exists(path):
        return 0, 1.0, 0  # n_roof, min_slope, n_faces
    with open(path) as f:
        cj = json.load(f)
    scale = np.array(cj['transform']['scale'])
    translate = np.array(cj['transform']['translate'])
    verts = np.array(cj['vertices'], dtype=np.float64) * scale + translate

    for obj in cj['CityObjects'].values():
        geom = obj['geometry'][0]
        sem = geom.get('semantics', {})
        surfaces = sem.get('surfaces', [])
        values = sem.get('values', [[]])[0]
        boundaries = geom['boundaries'][0]

        n_roof = 0
        slopes = []
        for fi, face in enumerate(boundaries):
            ring = face[0]
            pts = verts[ring]
            stype = 'Unknown'
            if fi < len(values) and values[fi] is not None and values[fi] < len(surfaces):
                stype = surfaces[values[fi]].get('type', 'Unknown')
            if stype == 'RoofSurface' and len(pts) >= 3:
                v1 = pts[1] - pts[0]
                v2 = pts[2] - pts[0]
                n = np.cross(v1, v2)
                n = n / (np.linalg.norm(n) + 1e-10)
                slopes.append(abs(n[1]))  # Y-up: 1.0=flat, <1.0=sloped
                n_roof += 1
        return n_roof, min(slopes) if slopes else 1.0, len(boundaries)
    return 0, 1.0, 0


def _get_roof_details(bid, out_base):
    """Analyze roof surfaces in a building's clean Stage 3 result."""
    path = os.path.join(out_base, f'3dbag_results/clean/b{bid:03d}/building.city.json')
    if not os.path.exists(path):
        return [], 0, 0
    with open(path) as f:
        cj = json.load(f)
    scale = np.array(cj['transform']['scale'])
    translate = np.array(cj['transform']['translate'])
    verts = np.array(cj['vertices'], dtype=np.float64) * scale + translate

    for obj in cj['CityObjects'].values():
        geom = obj['geometry'][0]
        sem = geom.get('semantics', {})
        surfaces = sem.get('surfaces', [])
        values = sem.get('values', [[]])[0]
        boundaries = geom['boundaries'][0]

        roof_slopes = []
        wall_count = 0
        for fi, face in enumerate(boundaries):
            ring = face[0]
            pts = verts[ring]
            stype = 'Unknown'
            if fi < len(values) and values[fi] is not None and values[fi] < len(surfaces):
                stype = surfaces[values[fi]].get('type', 'Unknown')
            if stype == 'WallSurface':
                wall_count += 1
            if stype == 'RoofSurface' and len(pts) >= 3:
                v1 = pts[1] - pts[0]
                v2 = pts[2] - pts[0]
                n = np.cross(v1, v2)
                n = n / (np.linalg.norm(n) + 1e-10)
                roof_slopes.append(abs(n[1]))  # 1.0=flat, <1.0=sloped
        return roof_slopes, wall_count, len(boundaries)
    return [], 0, 0


def select_representative_buildings(results_json, out_base='results/stage3_synthetic_a'):
    """Select one representative building per roof type.

    Prioritizes buildings whose clean Stage 3 result visually looks like
    the textbook version of each roof type:
    - Flat: single flat roof surface
    - Gable: 2 sloped roof surfaces with similar slopes (symmetric V)
    - Hip: 4 sloped roof surfaces
    - Complex: 5+ roof surfaces, mix of sloped and flat, enough walls
    """
    with open(results_json) as f:
        results = json.load(f)

    by_building = {}
    for r in results:
        bid = r['building_id']
        if bid not in by_building:
            by_building[bid] = {
                'type': r['building_type'],
                'scene': r['scene'],
                'name': r['building_name'],
            }
        by_building[bid][r['noise']] = {
            'val3dity': r['val3dity_valid'],
            'chamfer': r.get('chamfer'),
            'sem_acc': r['semantic_accuracy'],
            'success': r['stage3_success'],
        }

    selected = {}
    for rt in ['flat', 'gable', 'hip', 'complex', 'tri-slope', 'shed']:
        candidates = [(bid, d) for bid, d in by_building.items() if d['type'] == rt]
        candidates = [(bid, d) for bid, d in candidates
                      if d.get('clean', {}).get('val3dity')]

        scored = []
        for bid, d in candidates:
            n10_ok = d.get('normal_10deg', {}).get('val3dity', False)
            n20_fail = not d.get('normal_20deg', {}).get('val3dity', True)
            gradual = n10_ok and n20_fail

            roof_slopes, wall_count, n_faces = _get_roof_details(bid, out_base)

            # Manually curated IDs for visually representative buildings.
            # Selected by inspecting clean Stage 3 results for textbook
            # roof shapes with proper building proportions.
            CURATED = {
                'flat': 485,    # single flat roof, tall box
                'gable': 119,   # symmetric V-shape, 2 slopes ~0.70
                'hip': 468,     # tall building, 3 clear slopes, h=14.9m
                'complex': 175, # 5 roofs (4 sloped), 4 walls, h=10.1m
            }
            if rt in CURATED:
                score = 10000 if bid == CURATED[rt] else 0
            else:
                score = (1 if gradual else 0) * 100

            scored.append((score, bid, d))

        scored.sort(key=lambda x: -x[0])
        if scored:
            selected[rt] = (scored[0][1], scored[0][2])

    return selected


# ─────────────────────────────────────────────────────────────────────────────
# Main figure
# ─────────────────────────────────────────────────────────────────────────────

NOISE_CONDITIONS_VIZ = ['clean', 'normal_10deg', 'normal_20deg']
NOISE_LABELS = {
    'clean': 'Clean\n(reference)',
    'normal_10deg': 'Normal σ=10°\n(Stage 2 target)',
    'normal_20deg': 'Normal σ=20°\n(failure regime)',
}


def main():
    out_base = 'results/stage3_synthetic_a'
    results_json = os.path.join(out_base, '3dbag_results.json')

    print('Selecting representative buildings...')
    selected = select_representative_buildings(results_json)

    roof_types = ['flat', 'gable', 'hip', 'complex']
    buildings_to_show = {rt: selected[rt] for rt in roof_types if rt in selected}

    n_noises = len(NOISE_CONDITIONS_VIZ)
    n_buildings = len(buildings_to_show)

    fig = plt.figure(figsize=(n_buildings * 4.5, n_noises * 4.5 + 1.5))

    fig.suptitle('Stage 3 Result: Clean → Normal 10° → Normal 20°\n'
                 '(4 roof types, same building per column)',
                 fontsize=13, fontweight='bold', y=0.99)

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#E74C3C', edgecolor='#C0392B', label='RoofSurface'),
        Patch(facecolor='#BDC3C7', edgecolor='#95A5A6', label='WallSurface'),
        Patch(facecolor='#F1C40F', edgecolor='#D4AC0D', label='GroundSurface'),
    ]
    fig.legend(handles=legend_elements, loc='upper right', ncol=3,
               fontsize=9, framealpha=0.8, bbox_to_anchor=(0.98, 0.96))

    for col_idx, rt in enumerate(roof_types):
        bid, bdata = buildings_to_show[rt]

        # Use clean result as reference frame for consistent view across rows
        clean_path = os.path.join(out_base,
                                   f'3dbag_results/clean/b{bid:03d}/building.city.json')
        ref_center, ref_extent = get_building_frame(clean_path)

        # Column header
        header_x = 0.14 + col_idx * (0.82 / n_buildings)
        fig.text(header_x, 0.935,
                 f'{rt.upper()} (B{bid:03d})',
                 fontsize=11, fontweight='bold', ha='center', va='top',
                 transform=fig.transFigure)

        for row_idx, noise_name in enumerate(NOISE_CONDITIONS_VIZ):
            metrics = bdata.get(noise_name, {})
            val3d = metrics.get('val3dity', False)
            chamfer = metrics.get('chamfer')
            sem_acc = metrics.get('sem_acc', 0)

            ax = fig.add_subplot(n_noises, n_buildings,
                                  row_idx * n_buildings + col_idx + 1,
                                  projection='3d')

            res_path = os.path.join(out_base,
                                     f'3dbag_results/{noise_name}/b{bid:03d}/building.city.json')
            if os.path.exists(res_path):
                res_faces = load_cityjson_faces(res_path)
                render_building_3d(ax, res_faces,
                                   ref_center=ref_center, ref_extent=ref_extent)
            else:
                ax.set_axis_off()

            # Metric annotation
            val_str = '✓' if val3d else '✗'
            val_color = '#27AE60' if val3d else '#E74C3C'
            ch_str = f'{chamfer:.2f}m' if chamfer is not None else 'N/A'

            metric_text = f'val3d: {val_str}   CD: {ch_str}   SA: {sem_acc:.2f}'
            ax.text2D(0.5, -0.02, metric_text, transform=ax.transAxes,
                      fontsize=7.5, ha='center', va='top',
                      fontfamily='monospace',
                      bbox=dict(boxstyle='round,pad=0.3',
                                facecolor='#EAECEE' if val3d else '#FADBD8',
                                edgecolor=val_color, alpha=0.9))

    # Row labels
    for row_idx, noise_name in enumerate(NOISE_CONDITIONS_VIZ):
        row_y = 0.83 - row_idx * (0.78 / n_noises)
        fig.text(0.02, row_y, NOISE_LABELS[noise_name],
                 fontsize=9, fontweight='bold', ha='center', va='center',
                 rotation=90, transform=fig.transFigure,
                 bbox=dict(boxstyle='round,pad=0.4', facecolor='#F0F0F0',
                           edgecolor='#CCCCCC', alpha=0.8))

    plt.subplots_adjust(left=0.08, right=0.97, top=0.90, bottom=0.04,
                        wspace=0.08, hspace=0.18)

    out_path = os.path.join(out_base, 'images', 'gt_vs_result_comparison.png')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f'Saved: {out_path}')

    # Print observation notes
    print('\n=== Observation Notes ===')
    for rt in roof_types:
        bid, bdata = buildings_to_show[rt]
        print(f'\n**{rt} (B{bid:03d})**:')
        for noise_name in NOISE_CONDITIONS_VIZ:
            m = bdata.get(noise_name, {})
            val = '✓' if m.get('val3dity') else '✗'
            ch = m.get('chamfer')
            ch_s = f'{ch:.2f}m' if ch is not None else 'N/A'
            print(f'  {noise_name}: val3d={val}, CD={ch_s}, SA={m.get("sem_acc",0):.2f}')


if __name__ == '__main__':
    main()

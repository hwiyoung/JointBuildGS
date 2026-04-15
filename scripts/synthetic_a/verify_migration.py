#!/usr/bin/env python3
"""
Part D verification: confirm that the new modular src/stage3/ preserves the
behavior of the original monolithic `building_to_citygml_v4.py`.

Strategy:
  1. Import functions from both the legacy/planarsplat_ref/building_to_citygml_v4.py
     (reference) and the new src/stage3/ modules.
  2. Regenerate primitives for several 3D BAG buildings using the shared
     scripts/synthetic_a/primitives.py (unchanged from original).
  3. Run both pipelines on identical inputs and compare outputs.
"""

import importlib.util
import os
import sys
import tempfile

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'scripts', 'synthetic_a'))

# New modular pipeline
from src.stage3.clustering import cluster_primitives as new_cluster
from src.stage3.ground_surface import (
    orient_normals_outward as new_orient,
    add_ground_surface as new_add_ground,
    add_bbox_planes as new_add_bbox,
)
from src.stage3.plane_intersection import (
    build_convex_polytope as new_polytope,
)
from src.stage3.citygml_export import build_cityjson as new_cityjson

# Legacy monolithic reference
_legacy_path = os.path.join(ROOT, 'legacy/planarsplat_ref/building_to_citygml_v4.py')
_spec = importlib.util.spec_from_file_location('legacy_v4', _legacy_path)
legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(legacy)

# Synthetic A data generation (unchanged)
from buildings_3dbag import load_all_scenes
from primitives import generate_primitives_for_building


def run_pipeline(cluster_fn, orient_fn, add_ground_fn, add_bbox_fn,
                 polytope_fn, cityjson_fn, prims, bid, out_dir):
    """Generic pipeline runner using supplied function references."""
    centers = prims['centers']
    normals = prims['normals']
    areas = prims['areas']
    labels = prims['semantic_probs'].argmax(axis=1)

    if (labels == 1).sum() == 0 or (labels == 2).sum() == 0:
        return None

    groups = cluster_fn(centers, normals, areas, labels, cos_thresh=0.85)
    building_center = centers.mean(axis=0)
    orient_fn(groups, building_center)
    wall_centers = centers[labels == 2]
    add_ground_fn(groups, wall_centers, building_center)
    add_bbox_fn(groups, centers)

    polygons = polytope_fn(groups, centers, hs_tol=0.05)
    if polygons is None or len(polygons) < 4:
        return None

    return cityjson_fn(bid, groups, polygons, out_dir)


def main():
    print("Loading 3D BAG scenes...")
    scenes = load_all_scenes(
        base_dir=os.path.join(ROOT, 'data/3dbag/raw'))

    # Pick a few buildings from the Amsterdam sample
    buildings = []
    for scene_name, scene in scenes.items():
        for b in scene[:3]:
            buildings.append((scene_name, b))
        if len(buildings) >= 5:
            break
    buildings = buildings[:5]

    print(f"Comparing legacy vs new pipelines on {len(buildings)} buildings\n")

    with tempfile.TemporaryDirectory() as tmp:
        old_out = os.path.join(tmp, 'old')
        new_out = os.path.join(tmp, 'new')
        os.makedirs(old_out, exist_ok=True)
        os.makedirs(new_out, exist_ok=True)

        rows = []
        for i, (scene_name, b) in enumerate(buildings):
            bid = i + 1
            prims = generate_primitives_for_building(b, n_prims_per_face=50)
            if prims is None:
                rows.append((bid, 'no_prims', None, None, None, None))
                continue

            # Suppress print spam from inner pipeline
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                old = run_pipeline(
                    legacy.cluster_primitives, legacy.orient_normals_outward,
                    legacy.add_ground_surface, legacy.add_bbox_planes,
                    legacy.build_convex_polytope, legacy.build_cityjson,
                    prims, bid, os.path.join(old_out, f'b{bid:03d}'))
                new = run_pipeline(
                    new_cluster, new_orient, new_add_ground, new_add_bbox,
                    new_polytope, new_cityjson,
                    prims, bid, os.path.join(new_out, f'b{bid:03d}'))

            if old is None or new is None:
                rows.append((bid, 'fail',
                             old and old.get('n_surfaces'),
                             new and new.get('n_surfaces'),
                             old and old.get('signed_volume'),
                             new and new.get('signed_volume')))
                continue

            match = (old['n_surfaces'] == new['n_surfaces']
                     and abs(old['signed_volume'] - new['signed_volume']) < 1e-6)
            rows.append((bid, 'MATCH' if match else 'DIFFER',
                         old['n_surfaces'], new['n_surfaces'],
                         old['signed_volume'], new['signed_volume']))

    print("=" * 82)
    print(f"{'bid':>4s} {'status':10s} "
          f"{'old_surf':>10s} {'new_surf':>10s} "
          f"{'old_vol':>14s} {'new_vol':>14s}")
    print("-" * 82)
    for bid, status, os_, ns, ov, nv in rows:
        ov_s = f"{ov:.6f}" if isinstance(ov, (int, float)) else "-"
        nv_s = f"{nv:.6f}" if isinstance(nv, (int, float)) else "-"
        os_s = f"{os_}" if os_ is not None else "-"
        ns_s = f"{ns}" if ns is not None else "-"
        print(f"{bid:>4d} {status:10s} {os_s:>10s} {ns_s:>10s} {ov_s:>14s} {nv_s:>14s}")

    n_match = sum(1 for r in rows if r[1] == 'MATCH')
    n_total = len(rows)
    print(f"\n{n_match}/{n_total} buildings match between legacy and new pipelines.")
    return 0 if n_match == n_total else 1


if __name__ == '__main__':
    sys.exit(main())

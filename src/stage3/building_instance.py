"""
Building Instance Processing Pipeline

Orchestrates the full Stage 3 pipeline for a single building:
  cluster -> orient -> ground -> polytope -> CityJSON
"""

import json
import os

import numpy as np

from .clustering import cluster_primitives
from .ground_surface import orient_normals_outward, add_ground_surface, add_bbox_planes
from .plane_intersection import build_convex_polytope
from .citygml_export import build_cityjson
from .building_2_5d import build_2_5d_solid, faces_to_cityjson


def process_building(building_id, prim_ids, primitives, out_dir,
                     cos_thresh=0.85, hs_tol=0.05, method="convex"):
    """Process one building → CityJSON.

    method:
      - "convex" (default): half-space intersection → ConvexHull. Manifold-
                guaranteed, fails on non-convex footprints (Amsterdam L/U shapes).
                On GT input: val3dity 76.3%. On Stage 2 baseline: 40.5%.
      - "2_5d": footprint extraction + roof-type-specific construction (3D BAG
                style, aims for non-convex support). Ported from
                legacy/planarsplat_ref but shows LOWER val3dity than convex on
                Amsterdam Jordaan data (GT 61% / Baseline 16%). Needs further
                debugging/tuning for real-world building topology. Kept as
                experimental.
    """
    centers = primitives['centers'][prim_ids]
    normals = primitives['normals'][prim_ids]
    areas = primitives['areas'][prim_ids]
    labels = primitives['semantic_probs'][prim_ids].argmax(axis=1)

    n_roof, n_wall = int((labels == 1).sum()), int((labels == 2).sum())
    print(f"\n=== Building {building_id}: {len(prim_ids)} prims "
          f"(roof={n_roof}, wall={n_wall}) ===")

    if n_roof == 0 or n_wall == 0:
        print(f"  Skip: need both roof and wall")
        return None

    # Step 1: Cluster primitives -> surface groups
    groups = cluster_primitives(centers, normals, areas, labels,
                                cos_thresh=cos_thresh)
    for g in groups:
        g['prim_ids'] = [prim_ids[lid] for lid in g['prim_ids']]

    # Orient normals outward from building center
    building_center = centers.mean(axis=0)
    orient_normals_outward(groups, building_center)

    # Add virtual ground surface at wall base
    wall_centers = centers[labels == 2]
    add_ground_surface(groups, wall_centers, building_center)

    # Add bbox planes for unobserved directions
    n_bbox = add_bbox_planes(groups, centers)

    n_r = sum(1 for g in groups if g['class'] == 1)
    n_w = sum(1 for g in groups if g['class'] == 2)
    print(f"  {len(groups)} surfaces (roof={n_r}, wall={n_w}, ground=1, bbox={n_bbox})")

    if method == "2_5d":
        # Step 2 (2.5D hybrid): Extract non-convex footprint + roof-type construction.
        # NOTE: groups' prim_ids were converted to GLOBAL indices above, so we must
        # pass the FULL primitives['centers'] (not the building-local subset).
        try:
            faces = build_2_5d_solid(groups, primitives['centers'])
        except Exception as e:
            print(f"  2.5D build error: {type(e).__name__}: {e}; fallback to convex")
            faces = None
        if faces is None or len(faces) < 4:
            # Fallback to convex polytope
            print(f"  2.5D failed, fallback to convex polytope")
            polygons = build_convex_polytope(groups, centers, hs_tol=hs_tol)
            if polygons is None or len(polygons) < 4:
                print(f"  Both methods failed")
                return None
            for gi in sorted(polygons.keys()):
                cls = {1: 'roof', 2: 'wall', -1: 'ground'}.get(groups[gi]['class'], '?')
                gnd = ' [G]' if groups[gi].get('is_ground') else ''
                print(f"    S{gi}({cls}{gnd}): {len(polygons[gi])}v")
            result = build_cityjson(building_id, groups, polygons, out_dir)
        else:
            # Write 2.5D faces via faces_to_cityjson
            for f in faces:
                print(f"    [{f['type']}] {len(f['vertices'])}v")
            result = faces_to_cityjson(faces, building_id, out_dir)
    elif method == "convex":
        polygons = build_convex_polytope(groups, centers, hs_tol=hs_tol)
        if polygons is None or len(polygons) < 4:
            print(f"  Polytope failed or <4 faces")
            return None
        for gi in sorted(polygons.keys()):
            cls = {1: 'roof', 2: 'wall', -1: 'ground'}.get(groups[gi]['class'], '?')
            gnd = ' [G]' if groups[gi].get('is_ground') else ''
            print(f"    S{gi}({cls}{gnd}): {len(polygons[gi])}v")
        result = build_cityjson(building_id, groups, polygons, out_dir)
    else:
        raise ValueError(f"unknown method: {method!r}")

    if result:
        print(f"  -> {result.get('n_surfaces', '?')}s {result.get('n_vertices', '?')}v"
              + (f"  vol={result['signed_volume']:.4f}" if 'signed_volume' in result else ''))
    return result


def process_all_buildings(primitives, building_faces, out_dir,
                          cos_thresh=0.85, hs_tol=0.05, building_ids=None):
    """Process all buildings from primitives and building assignment data."""
    building_ids_arr = building_faces['building_ids']
    face_prim_indices = building_faces['face_prim_indices']

    print(f"  Primitives: {primitives['centers'].shape[0]}")
    print(f"  Face->prim: {len(face_prim_indices)} faces")

    unique_bids = np.unique(building_ids_arr)
    unique_bids = unique_bids[unique_bids >= 0]
    if building_ids is not None:
        unique_bids = [b for b in building_ids if b in unique_bids]

    print(f"\nProcessing {len(unique_bids)} buildings...")
    os.makedirs(out_dir, exist_ok=True)
    results = []

    for bid in sorted(unique_bids):
        bmask = building_ids_arr == bid
        prim_ids = np.unique(face_prim_indices[bmask])
        prim_ids = prim_ids[prim_ids >= 0]
        if len(prim_ids) < 3:
            continue
        result = process_building(
            bid, prim_ids, primitives, out_dir,
            cos_thresh=cos_thresh, hs_tol=hs_tol)
        if result:
            results.append(result)

    # Summary
    summary = {
        'version': 'v4-convex',
        'params': {'cos_thresh': cos_thresh, 'hs_tol': hs_tol},
        'n_buildings_processed': len(results),
        'n_buildings_total': len(unique_bids),
        'buildings': results,
    }
    with open(os.path.join(out_dir, 'summary.json'), 'w') as f:
        json.dump(summary, f, indent=2,
                  default=lambda x: int(x) if isinstance(x, np.integer)
                  else float(x) if isinstance(x, np.floating) else x)

    print(f"\n{'=' * 60}")
    print(f"Summary: {len(results)}/{len(unique_bids)} buildings processed")
    if results:
        total_sh = sum(r['n_edges_shared'] for r in results)
        total_bd = sum(r['n_edges_boundary'] for r in results)
        total_nm = sum(r['n_edges_nonmanifold'] for r in results)
        print(f"Edges total: {total_sh} shared, {total_bd} boundary, {total_nm} non-manifold")

    return results

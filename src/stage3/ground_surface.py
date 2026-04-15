"""
Step 2: Plane Orientation + Ground/BBox Surface Addition
"""

import numpy as np


def orient_normals_outward(groups, building_center):
    """Flip normals to point away from building center."""
    for g in groups:
        if np.dot(g['plane_normal'], g['center'] - building_center) < 0:
            g['plane_normal'] = -g['plane_normal']
            g['plane_d'] = -g['plane_d']


def add_ground_surface(groups, wall_centers, building_center):
    """Add virtual GroundSurface at wall base. COLMAP: -Y up, down = +Y outward."""
    y_base = float(np.max(wall_centers[:, 1]))
    groups.append({
        'plane_normal': np.array([0.0, 1.0, 0.0]),
        'plane_d': float(y_base),
        'class': -1,
        'prim_ids': [],
        'center': np.array([building_center[0], y_base, building_center[2]]),
        'area': 0.0,
        'is_ground': True,
    })


def add_bbox_planes(groups, prim_centers, margin=0.05):
    """
    Add axis-aligned bounding box planes for unobserved building faces.

    Only adds planes for directions not already covered by real surface groups.
    """
    normals_existing = np.array([g['plane_normal'] for g in groups])
    bbox_min = prim_centers.min(axis=0) - margin
    bbox_max = prim_centers.max(axis=0) + margin
    center = prim_centers.mean(axis=0)

    candidates = [
        (np.array([1.0, 0, 0]), bbox_max[0], 2,
         np.array([bbox_max[0], center[1], center[2]])),
        (np.array([-1.0, 0, 0]), -bbox_min[0], 2,
         np.array([bbox_min[0], center[1], center[2]])),
        (np.array([0, -1.0, 0]), -bbox_min[1], 1,
         np.array([center[0], bbox_min[1], center[2]])),
        (np.array([0, 0, 1.0]), bbox_max[2], 2,
         np.array([center[0], center[1], bbox_max[2]])),
        (np.array([0, 0, -1.0]), -bbox_min[2], 2,
         np.array([center[0], center[1], bbox_min[2]])),
    ]

    n_added = 0
    for normal, d, cls, c in candidates:
        cos_sims = normals_existing @ normal
        if np.any(cos_sims > 0.7):
            continue
        groups.append({
            'plane_normal': normal,
            'plane_d': float(d),
            'class': cls,
            'prim_ids': [],
            'center': c,
            'area': 0.0,
            'is_bbox': True,
        })
        n_added += 1

    return n_added

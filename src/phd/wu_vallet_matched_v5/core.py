"""Audited boundary between sampled face relations and corrected point updating.

This does not replace sampled rays with the unpublished author's intersection
predicate.  It prevents the historical v2 assembled masks from entering the v5
caller and validates the same v3 face-to-point policy used by all three regions.
"""
from __future__ import annotations

import numpy as np

from src.phd.wu_vallet_p3_v2.ray_runtime import (
    RuntimeConfig, SensorMesh, classify_and_update as _classify_v2,
)
from scripts.phd.wu_vallet_p3_v3.analyze_filtered_update import (
    assemble_status as _assemble_v3, components,
)


def classify_relations(old: SensorMesh, new: SensorMesh, config: RuntimeConfig):
    """Return raw face evidence, never the v2 point assembly or its area filter."""
    if config.small_region_area_m2 != 0:
        raise ValueError("Classify raw relations at area zero; filter only in assemble_status")
    for side, mesh in (("old", old), ("new", new)):
        if mesh.optical_origins is None:
            if side == "new" or config.direction_mode == "BIDIRECTIONAL":
                raise ValueError(f"Missing {side} optical origins")
        elif mesh.triangles.size and not np.isfinite(mesh.optical_origins[mesh.triangles]).all():
            raise ValueError(f"Unsupported {side} optical origin referenced by a triangle")
    result = _classify_v2(old, new, config)
    keys = ("raw_old_face_labels", "raw_new_face_labels", "conflict_pairs",
            "conflict_pair_columns", "diagnostics", "reproduction_scope",
            "old_sample_surface_distances_m", "new_sample_surface_distances_m")
    raw = {key: result[key] for key in keys}
    raw["reproduction_scope"] = dict(result["reproduction_scope"],
        caller_assembly="v5 validated v3 status assembly; v2 keep masks never exposed",
        actual_small_region_filter="separate full-context changed-face area components",
        unsupported_origin_policy="fail if unsupported origin is referenced by a triangle",
        author_equivalent_predicate=False)
    return raw


def assemble_status(vertex_count, triangles, raw_labels, regions, area_threshold):
    """Validate raw component identities and the corrected admission invariants."""
    triangles = np.asarray(triangles)
    raw_labels = np.asarray(raw_labels)
    if triangles.ndim != 2 or triangles.shape[1] != 3 or triangles.dtype.kind not in "iu":
        raise ValueError("triangles must be integer [F,3]")
    if triangles.size and (triangles.min() < 0 or triangles.max() >= vertex_count):
        raise ValueError("triangle index outside vertex domain")
    component_ids = np.asarray(regions["face_component_id"])
    areas = np.asarray(regions["area_m2"])
    if component_ids.shape != raw_labels.shape or not np.isfinite(areas).all() or (areas < 0).any():
        raise ValueError("Invalid changed-component geometry")
    changed_ids = component_ids[raw_labels == "changed"]
    if changed_ids.size and ((changed_ids < 0).any() or (changed_ids >= len(areas)).any()):
        raise ValueError("Changed face has no valid component")
    selection = _assemble_v3(vertex_count, triangles, raw_labels, regions, area_threshold)
    incident = selection["incident"]
    evidence = incident["accepted_changed"] | incident["raw_single"]
    expected_new = evidence & ~incident["consistent"]
    expected_old = ~incident["accepted_changed"] | incident["consistent"]
    if not np.array_equal(selection["new_keep"], expected_new):
        raise AssertionError("New point admitted without accepted/raw-single face evidence")
    if not np.array_equal(selection["old_keep"], expected_old):
        raise AssertionError("Old point retention disagrees with declared face precedence")
    filtered_only = incident["filtered"] & ~evidence & ~incident["consistent"]
    if selection["new_keep"][filtered_only].any():
        raise AssertionError("Filtered-only new vertices reentered the update")
    return selection

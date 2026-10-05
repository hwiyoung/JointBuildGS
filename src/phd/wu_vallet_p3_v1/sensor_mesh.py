"""Explicit acquisition-to-sensor-mesh adapters for the Wu--Vallet component.

These are paper-based preprocessing candidates with declared filtering choices.
An existing COLMAP/Metashape depth raster substitutes for the paper's PSMNet and
multi-view matching stage; it is not an end-to-end reproduction.  ALS scan IDs,
beam order, GPS times and optical-center trajectory must be supplied.  No XYZ
projection, time sorting heuristic, vertical viewpoint or trajectory extrapolation
is used to invent missing acquisition metadata.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.spatial import Delaunay, QhullError

from .ray_update import SensorMesh


def _positive_finite(value: float, name: str) -> None:
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be explicitly positive and finite")


@dataclass(frozen=True)
class ImageMeshConfig:
    max_edge_length_m: float
    max_depth_jump_m: float
    pixel_center_offset: float = 0.0
    retain_isolated_vertices: bool = False

    def __post_init__(self):
        _positive_finite(self.max_edge_length_m, "max_edge_length_m")
        _positive_finite(self.max_depth_jump_m, "max_depth_jump_m")
        if not np.isfinite(self.pixel_center_offset):
            raise ValueError("pixel_center_offset must be finite")


@dataclass(frozen=True)
class ALSMeshConfig:
    max_edge_length_m: float
    max_scan_gap: int
    max_beam_gap: int
    max_time_gap_s: float
    trajectory_coordinate_role: str
    retain_isolated_vertices: bool = False

    def __post_init__(self):
        _positive_finite(self.max_edge_length_m, "max_edge_length_m")
        _positive_finite(self.max_time_gap_s, "max_time_gap_s")
        for name in ("max_scan_gap", "max_beam_gap"):
            value = getattr(self, name)
            if not isinstance(value, (int, np.integer)) or value < 1:
                raise ValueError(f"{name} must be an explicitly positive integer")
        if self.trajectory_coordinate_role != "sensor_optical_center":
            raise ValueError("trajectory must explicitly represent sensor_optical_center; apply known lever-arm/calibration upstream")


def _face_geometry(vertices: np.ndarray, triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    points = vertices[triangles]
    edges = np.stack((points[:, 1] - points[:, 0], points[:, 2] - points[:, 1], points[:, 0] - points[:, 2]), axis=1)
    max_edge = np.linalg.norm(edges, axis=2).max(axis=1)
    twice_area = np.linalg.norm(np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]), axis=1)
    return max_edge, twice_area


def _compact(vertices: np.ndarray, triangles: np.ndarray, origins: np.ndarray,
             native_rows: np.ndarray, retain_isolated: bool) -> tuple[SensorMesh, np.ndarray]:
    selected = np.arange(len(vertices)) if retain_isolated else np.unique(triangles)
    inverse = np.full(len(vertices), -1, dtype=np.int64)
    inverse[selected] = np.arange(len(selected))
    mesh = SensorMesh(vertices[selected], inverse[triangles], origins[selected], native_rows[selected])
    return mesh, selected


def image_depth_to_sensor_mesh(depth: np.ndarray, K: np.ndarray,
                               R_world_to_camera: np.ndarray, t_world_to_camera: np.ndarray,
                               config: ImageMeshConfig, image_id: str = "unspecified") -> dict:
    """Unproject camera-Z depth in metres using a K already in depth-pixel units.

    X_camera = R_world_to_camera @ X_world + t_world_to_camera.
    No intrinsics resizing, lens undistortion, gravity inference or CRS shift is
    performed here.  Each raster quad has a fixed northwest-to-southeast diagonal;
    missing pixels are not triangulated across.  Native IDs are row-major pixels.
    """
    depth = np.asarray(depth, dtype=np.float64)
    K = np.asarray(K, dtype=np.float64)
    R = np.asarray(R_world_to_camera, dtype=np.float64)
    t = np.asarray(t_world_to_camera, dtype=np.float64)
    if depth.ndim != 2 or min(depth.shape) < 2:
        raise ValueError("depth must be a camera-Z [H,W] raster with H,W >= 2")
    if K.shape != (3, 3) or not np.isfinite(K).all() or K[0, 0] <= 0 or K[1, 1] <= 0:
        raise ValueError("K must be a finite pinhole 3x3 matrix with positive focal lengths")
    if not np.allclose(K[2], [0, 0, 1], rtol=0, atol=1e-12):
        raise ValueError("K must use standard pinhole homogeneous coordinates")
    if R.shape != (3, 3) or not np.isfinite(R).all() or not np.allclose(R.T @ R, np.eye(3), atol=1e-6):
        raise ValueError("R_world_to_camera must be a finite orthonormal 3x3 rotation")
    if not np.isclose(np.linalg.det(R), 1.0, atol=1e-6):
        raise ValueError("R_world_to_camera must have determinant +1")
    if t.shape != (3,) or not np.isfinite(t).all():
        raise ValueError("t_world_to_camera must be finite [3]")
    height, width = depth.shape
    valid = np.isfinite(depth) & (depth > 0)
    flat_ids = np.flatnonzero(valid.ravel())
    v, u = np.divmod(flat_ids, width)
    uv = np.column_stack((u, v)).astype(np.int64)
    homogeneous = np.column_stack((u + config.pixel_center_offset, v + config.pixel_center_offset, np.ones(len(u))))
    try:
        camera_rays = homogeneous @ np.linalg.inv(K).T
    except np.linalg.LinAlgError as error:
        raise ValueError("K must be invertible") from error
    camera_points = camera_rays * depth.ravel()[flat_ids, None]
    vertices = (camera_points - t) @ R
    center = -R.T @ t
    origins = np.broadcast_to(center, vertices.shape).copy()

    yy, xx = np.indices((height - 1, width - 1))
    northwest = (yy * width + xx).ravel()
    southeast = northwest + width + 1
    candidate_flat = np.concatenate((np.column_stack((northwest, northwest + 1, southeast)),
                                     np.column_stack((northwest, southeast, northwest + width))))
    valid_face = valid.ravel()[candidate_flat].all(axis=1)
    flat_triangles = candidate_flat[valid_face]
    flat_to_vertex = np.full(depth.size, -1, dtype=np.int64)
    flat_to_vertex[flat_ids] = np.arange(len(flat_ids))
    triangles = flat_to_vertex[flat_triangles]
    max_edge, twice_area = _face_geometry(vertices, triangles)
    depth_jump = np.ptp(depth.ravel()[flat_triangles], axis=1)
    bad_edge = max_edge > config.max_edge_length_m
    bad_jump = depth_jump > config.max_depth_jump_m
    bad_area = twice_area <= 1e-12
    keep_face = ~(bad_edge | bad_jump | bad_area)
    mesh, selected = _compact(vertices, triangles[keep_face], origins, flat_ids, config.retain_isolated_vertices)
    pixel_ids = flat_ids[selected]
    meshed_mask = np.zeros(depth.size, dtype=bool)
    if mesh.triangles.size:
        meshed_mask[mesh.native_rows[np.unique(mesh.triangles)]] = True
    retained_mask = np.zeros(depth.size, dtype=bool)
    retained_mask[pixel_ids] = True
    return {
        "mesh": mesh, "pixel_ids": pixel_ids, "pixel_uv": uv[selected],
        "valid_pixel_mask": valid, "meshed_pixel_mask": meshed_mask.reshape(depth.shape),
        "retained_pixel_mask": retained_mask.reshape(depth.shape),
        "diagnostics": {
            "pixels": depth.size, "valid_positive_depth_pixels": len(flat_ids),
            "invalid_or_nonpositive_depth_pixels": int((~valid).sum()),
            "candidate_faces": len(candidate_flat), "faces_with_invalid_depth": int((~valid_face).sum()),
            "faces_with_long_edge": int(bad_edge.sum()), "faces_with_depth_jump": int(bad_jump.sum()),
            "degenerate_faces": int(bad_area.sum()), "retained_faces": len(mesh.triangles),
            "retained_vertices": len(mesh.vertices), "valid_but_unmeshed_pixels": int(valid.sum() - meshed_mask.sum()),
            "face_rejection_counts_may_overlap": True,
        },
        "reproduction_scope": {
            "name": "PAPER_BASED_IMAGE_SENSOR_MESH_FROM_SUPPLIED_DEPTH", "image_id": str(image_id),
            "native_Wu_Vallet_reproduction": False, "scientific_verdict": None,
            "config": asdict(config), "depth_convention": "camera_Z_metres_not_ray_range",
            "intrinsics_convention": "K_already_in_supplied_depth_raster_pixel_coordinates",
            "pose_convention": "X_camera=R_world_to_camera@X_world+t_world_to_camera",
            "topology": "fixed_NW_SE_diagonal_pixel_adjacency",
            "optical_origins": "exact_supplied_camera_center_-R_transpose_t",
            "native_pixel_id": "row_major_v_times_width_plus_u",
            "scope_limitations": ["supplied_depth_replaces_PSMNet_and_multiview_matching_stage",
                                  "edge_and_depth_jump_filters_are_declared_development_choices",
                                  "camera_calibration_depth_accuracy_and_currentness_not_certified"],
        },
    }


def als_acquisition_to_sensor_mesh(points: np.ndarray, scan_ids: np.ndarray, beam_orders: np.ndarray,
                                   gps_times: np.ndarray, trajectory_times: np.ndarray,
                                   trajectory_positions: np.ndarray, config: ALSMeshConfig,
                                   native_rows: np.ndarray | None = None) -> dict:
    """Delaunay in the provided (beam_order, scan_id) plane, never physical XY.

    Times must share a declared upstream GPS-time basis.  Trajectory positions
    must already be sensor optical centers in the point-coordinate frame.  Echo
    selection and scanline recovery are upstream responsibilities; duplicate
    (scan, beam) coordinates fail instead of silently selecting a LiDAR return.
    """
    points = np.asarray(points, dtype=np.float64)
    scan_ids, beam_orders = np.asarray(scan_ids), np.asarray(beam_orders)
    gps_times = np.asarray(gps_times, dtype=np.float64)
    trajectory_times = np.asarray(trajectory_times, dtype=np.float64)
    trajectory_positions = np.asarray(trajectory_positions, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError("points must be finite [N,3]")
    count = len(points)
    for name, array in (("scan_ids", scan_ids), ("beam_orders", beam_orders)):
        if array.shape != (count,) or array.dtype.kind not in "iu":
            raise ValueError(f"{name} must be explicit integer [N]")
    if count < 3:
        raise ValueError("at least three acquisition points are needed for triangulation")
    if gps_times.shape != (count,) or not np.isfinite(gps_times).all():
        raise ValueError("gps_times must be finite [N]")
    if trajectory_times.ndim != 1 or len(trajectory_times) < 2 or not np.isfinite(trajectory_times).all():
        raise ValueError("trajectory_times must contain at least two finite times")
    if np.any(np.diff(trajectory_times) <= 0):
        raise ValueError("trajectory_times must be strictly increasing without duplicates")
    if trajectory_positions.shape != (len(trajectory_times), 3) or not np.isfinite(trajectory_positions).all():
        raise ValueError("trajectory_positions must be finite [T,3] optical centers")
    if gps_times.min() < trajectory_times[0] or gps_times.max() > trajectory_times[-1]:
        raise ValueError("GPS times outside trajectory support: clamping/extrapolation prohibited")
    acquisition_xy = np.column_stack((beam_orders, scan_ids))
    if len(np.unique(acquisition_xy, axis=0)) != count:
        raise ValueError("duplicate (scan_id, beam_order): select returns explicitly upstream")
    if np.linalg.matrix_rank(acquisition_xy.astype(float) - acquisition_xy[0]) < 2:
        raise ValueError("scan-order coordinates are collinear; cannot invent a second scanline")
    origins = np.column_stack([np.interp(gps_times, trajectory_times, trajectory_positions[:, axis]) for axis in range(3)])
    try:
        triangles = Delaunay(acquisition_xy.astype(np.float64)).simplices.astype(np.int64)
    except QhullError as error:
        raise ValueError("scan-order Delaunay failed; no random jitter fallback permitted") from error
    max_edge, twice_area = _face_geometry(points, triangles)
    bad_scan = np.ptp(scan_ids[triangles], axis=1) > config.max_scan_gap
    bad_beam = np.ptp(beam_orders[triangles], axis=1) > config.max_beam_gap
    bad_time = np.ptp(gps_times[triangles], axis=1) > config.max_time_gap_s
    bad_edge, bad_area = max_edge > config.max_edge_length_m, twice_area <= 1e-12
    keep = ~(bad_scan | bad_beam | bad_time | bad_edge | bad_area)
    if native_rows is None:
        rows = np.arange(count, dtype=np.int64)
    else:
        rows = np.asarray(native_rows)
        if rows.shape != (count,) or rows.dtype.kind not in "iu" or len(np.unique(rows)) != count:
            raise ValueError("native_rows must uniquely identify all input points")
    mesh, selected = _compact(points, triangles[keep], origins, rows, config.retain_isolated_vertices)
    return {
        "mesh": mesh, "input_indices": selected, "scan_ids": scan_ids[selected],
        "beam_orders": beam_orders[selected], "gps_times": gps_times[selected],
        "diagnostics": {
            "input_vertices": count, "candidate_faces": len(triangles),
            "faces_with_scan_gap": int(bad_scan.sum()), "faces_with_beam_gap": int(bad_beam.sum()),
            "faces_with_time_gap": int(bad_time.sum()), "faces_with_long_edge": int(bad_edge.sum()),
            "degenerate_faces": int(bad_area.sum()), "retained_faces": len(mesh.triangles),
            "retained_vertices": len(mesh.vertices),
            "face_rejection_counts_may_overlap": True,
        },
        "reproduction_scope": {
            "name": "PAPER_BASED_ALS_SENSOR_MESH_FROM_EXPLICIT_ACQUISITION_METADATA",
            "native_Wu_Vallet_reproduction": False, "scientific_verdict": None, "config": asdict(config),
            "topology": "Delaunay_in_provided_beam_order_scan_id_plane_not_XY",
            "optical_origins": "linear_interpolation_of_supplied_sensor_optical_center_trajectory",
            "trajectory_extrapolation": "prohibited",
            "scope_limitations": ["scanline_recovery_and_return_selection_not_inferred",
                                  "GPS_time_basis_coordinate_frame_and_lever_arm_must_be_resolved_upstream",
                                  "Delaunay_filter_values_are_declared_development_choices",
                                  "sensor_metadata_and_geometry_accuracy_not_certified"],
        },
    }

"""Opt-in source-camera calibration for the unchanged native GeoGS rasterizer.

The native ndc2pix mapping is ((ndc+1)*size-1)/2. A metadata-only
adapter restores principal points lost by GeoGS's FoV-only camera constructor.
No image is warped, and scenes without explicit metadata retain native behavior.
"""
import functools
import json
from pathlib import Path

import numpy as np


def apply_projection(camera, calibration):
    width, height = calibration["width"], calibration["height"]
    if (camera.image_width, camera.image_height) != (width, height):
        raise ValueError("Calibrated input adapter requires unchanged image resolution")
    K = np.asarray(calibration["K"], dtype=np.float64)
    if K.shape != (3, 3) or not np.isfinite(K).all() or K[0, 1] != 0 or K[1, 0] != 0:
        raise ValueError("Expected finite zero-skew PINHOLE K")
    projection = camera.projection_matrix.T.clone()
    projection[0, 0] = 2 * K[0, 0] / width
    projection[1, 1] = 2 * K[1, 1] / height
    projection[0, 2] = (2 * K[0, 2] + 1 - width) / width
    projection[1, 2] = (2 * K[1, 2] + 1 - height) / height
    camera.projection_matrix = projection.T.contiguous()
    camera.full_proj_transform = camera.world_view_transform @ camera.projection_matrix
    camera.jbgs_source_intrinsics = K.copy()
    return camera


@functools.lru_cache(maxsize=8)
def read_calibration(path):
    path = Path(path)
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if value["schema"] != "jointbuildgs.geogs.source_calibration.v1":
        raise ValueError("Unexpected source-camera calibration schema")
    return value


def maybe_calibrate_camera(camera, args, cam_info):
    value = read_calibration(str(Path(args.source_path) / "jbgs_calibration.json"))
    if value is None:
        return camera
    name = cam_info.image_name
    if name not in value["images"]:
        raise ValueError(f"Calibrated camera is missing from the explicit manifest: {name}")
    return apply_projection(camera, value["images"][name])

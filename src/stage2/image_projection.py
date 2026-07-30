"""Single coordinate-safe path for projecting geometry into COLMAP images.

The public base-coordinate entry point deliberately requires ``input_datum``.
This prevents orthometric ALS/GML heights from silently taking the historical
ellipsoidal projection path.  Vertical-datum conversion is delegated to the
shared helper in ``src/geospatial/projection_datum.py``; this module owns only shape
validation, COLMAP camera projection, and validity reporting.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence

import numpy as np


class ProjectionError(ValueError):
    """Raised when a projection contract cannot be satisfied safely."""


class ProjectionResult(NamedTuple):
    """Projected pixels, camera-space depth, and per-point validity.

    ``valid`` means the input and projected coordinates are finite and the
    point is farther than ``min_depth_m`` in front of the camera.  It does not
    imply that the pixel lies inside the image; use :func:`in_frame_mask` for
    that additional test.
    """

    uv: np.ndarray
    depth: np.ndarray
    valid: np.ndarray


def _load_projection_datum_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "src" / "geospatial" / "projection_datum.py"
    if not module_path.is_file():
        raise ImportError(f"projection datum helper is missing: {module_path}")
    spec = importlib.util.spec_from_file_location(
        "_jointbuildgs_projection_datum", module_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load projection datum helper: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_projection_datum = _load_projection_datum_module()
ORTHOMETRIC = _projection_datum.ORTHOMETRIC
ELLIPSOIDAL = _projection_datum.ELLIPSOIDAL


_DATUM_ALIASES = {
    "ortho": ORTHOMETRIC,
    "orthometric": ORTHOMETRIC,
    "dhhn": ORTHOMETRIC,
    "dhhn2016": ORTHOMETRIC,
    "ellip": ELLIPSOIDAL,
    "ellipsoid": ELLIPSOIDAL,
    "ellipsoidal": ELLIPSOIDAL,
    "wgs84": ELLIPSOIDAL,
}

_MODEL_PARAMETER_COUNTS = {
    "SIMPLE_PINHOLE": 3,
    "PINHOLE": 4,
    "SIMPLE_RADIAL": 4,
    "RADIAL": 5,
    "OPENCV": 8,
    "FULL_OPENCV": 12,
}


def _points3(points: np.ndarray | Sequence[Sequence[float]], name: str) -> np.ndarray:
    array = np.asarray(points, dtype=np.float64)
    if array.ndim == 1:
        if array.shape != (3,):
            raise ProjectionError(f"{name} must have shape (3,) or (N, 3), got {array.shape}")
        array = array[None, :]
    if array.ndim != 2 or array.shape[1] != 3:
        raise ProjectionError(f"{name} must have shape (3,) or (N, 3), got {array.shape}")
    return array


def _validate_scene_reference(scene_reference: Mapping[str, Any]) -> None:
    """Reject implicit, singular, or non-finite base/canonical transforms."""

    if not isinstance(scene_reference, Mapping):
        raise ProjectionError("scene_reference must be a mapping")
    transform = scene_reference.get("base_to_canonical", scene_reference)
    if not isinstance(transform, Mapping):
        raise ProjectionError("scene_reference.base_to_canonical must be a mapping")
    missing = sorted({"shift", "scale", "swap_xy"} - set(transform))
    if missing:
        raise ProjectionError(
            "scene_reference transform is missing explicit fields: " + ", ".join(missing)
        )
    shift = np.asarray(transform["shift"], dtype=np.float64)
    scale = np.asarray(transform["scale"], dtype=np.float64)
    if shift.shape != (3,) or not np.all(np.isfinite(shift)):
        raise ProjectionError("scene_reference shift must contain three finite values")
    if scale.shape != (3,) or not np.all(np.isfinite(scale)):
        raise ProjectionError("scene_reference scale must contain three finite values")
    if np.any(scale == 0.0):
        raise ProjectionError("scene_reference scale must be non-zero on every axis")
    if not isinstance(transform["swap_xy"], (bool, np.bool_)):
        raise ProjectionError("scene_reference swap_xy must be boolean")


def _finite_transform_result(
    converted: Any,
    *,
    expected_shape: tuple[int, int],
    operation: str,
) -> np.ndarray:
    result = np.asarray(converted, dtype=np.float64)
    if result.shape != expected_shape:
        raise ProjectionError(
            f"{operation} returned shape {result.shape}, expected {expected_shape}"
        )
    if not np.all(np.isfinite(result)):
        raise ProjectionError(f"{operation} returned non-finite coordinates")
    return result


def _datum_name(value: str, argument: str) -> str:
    if not isinstance(value, str):
        raise ProjectionError(f"{argument} must be a datum name, got {type(value).__name__}")
    canonical = _DATUM_ALIASES.get(value.lower())
    if canonical is None:
        raise ProjectionError(f"unknown {argument}={value!r}")
    return canonical


def _camera_parameters(camera: Any) -> tuple[str, np.ndarray]:
    model = str(getattr(camera, "model", ""))
    expected = _MODEL_PARAMETER_COUNTS.get(model)
    if expected is None:
        raise ProjectionError(f"unsupported COLMAP camera model: {model or '<missing>'}")
    params = np.asarray(getattr(camera, "params", None), dtype=np.float64)
    if params.ndim != 1 or len(params) != expected:
        raise ProjectionError(
            f"{model} requires exactly {expected} parameters, got shape {params.shape}"
        )
    if not np.all(np.isfinite(params)):
        raise ProjectionError(f"{model} camera parameters must all be finite")
    return model, params


def base_to_canonical(
    points_base: np.ndarray | Sequence[Sequence[float]],
    scene_reference: Mapping[str, Any],
    *,
    input_datum: str,
    geoid_m: float | None = None,
    config_path: str | Path | None = None,
) -> np.ndarray:
    """Convert EPSG:25832 base points to the canonical camera/world frame.

    ``input_datum`` has no default by design.  ALS/GML callers normally pass
    ``ORTHOMETRIC``; inputs already expressed in ellipsoidal height pass
    ``ELLIPSOIDAL``.
    """

    points = _points3(points_base, "points_base")
    if not np.all(np.isfinite(points)):
        raise ProjectionError("points_base must contain only finite coordinates")
    _validate_scene_reference(scene_reference)
    datum = _datum_name(input_datum, "input_datum")
    try:
        converted = _projection_datum.base_to_canonical_points(
            points,
            scene_reference,
            input_datum=datum,
            geoid_m=geoid_m,
            config_path=config_path,
        )
        return _finite_transform_result(
            converted,
            expected_shape=points.shape,
            operation="base-to-canonical conversion",
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ProjectionError):
            raise
        raise ProjectionError(f"base-to-canonical conversion failed: {exc}") from exc


def canonical_to_base(
    points_canonical: np.ndarray | Sequence[Sequence[float]],
    scene_reference: Mapping[str, Any],
    *,
    output_datum: str,
    geoid_m: float | None = None,
    config_path: str | Path | None = None,
) -> np.ndarray:
    """Convert canonical camera/world points back to explicit base heights."""

    points = _points3(points_canonical, "points_canonical")
    if not np.all(np.isfinite(points)):
        raise ProjectionError("points_canonical must contain only finite coordinates")
    _validate_scene_reference(scene_reference)
    datum = _datum_name(output_datum, "output_datum")
    try:
        base_ellipsoidal = _finite_transform_result(
            _projection_datum.canonical_to_base_points(points, scene_reference),
            expected_shape=points.shape,
            operation="canonical-to-base conversion",
        )
        if datum == ORTHOMETRIC:
            base_ellipsoidal[:, 2] -= _projection_datum.projection_geoid_m(
                geoid_m, config_path
            )
        if not np.all(np.isfinite(base_ellipsoidal)):
            raise ProjectionError("canonical-to-base datum conversion returned non-finite coordinates")
        return base_ellipsoidal
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ProjectionError):
            raise
        raise ProjectionError(f"canonical-to-base conversion failed: {exc}") from exc


def _distort_normalized(model: str, params: np.ndarray, x: np.ndarray, y: np.ndarray):
    if model == "SIMPLE_PINHOLE":
        f, cx, cy = params
        return f, f, cx, cy, x, y
    if model == "PINHOLE":
        fx, fy, cx, cy = params
        return fx, fy, cx, cy, x, y

    r2 = x * x + y * y
    if model == "SIMPLE_RADIAL":
        f, cx, cy, k1 = params
        scale = 1.0 + k1 * r2
        return f, f, cx, cy, x * scale, y * scale
    if model == "RADIAL":
        f, cx, cy, k1, k2 = params
        scale = 1.0 + k1 * r2 + k2 * r2 * r2
        return f, f, cx, cy, x * scale, y * scale

    if model == "OPENCV":
        fx, fy, cx, cy, k1, k2, p1, p2 = params
        radial = 1.0 + k1 * r2 + k2 * r2 * r2
    elif model == "FULL_OPENCV":
        fx, fy, cx, cy, k1, k2, p1, p2, k3, k4, k5, k6 = params
        r4 = r2 * r2
        r6 = r4 * r2
        denominator = 1.0 + k4 * r2 + k5 * r4 + k6 * r6
        if np.any(~np.isfinite(denominator)) or np.any(np.abs(denominator) < 1e-12):
            raise ProjectionError("FULL_OPENCV radial denominator is singular")
        radial = (1.0 + k1 * r2 + k2 * r4 + k3 * r6) / denominator
    else:  # Guarded by _camera_parameters; retained as a fail-closed invariant.
        raise ProjectionError(f"unsupported COLMAP camera model: {model}")

    xd = x * radial + 2.0 * p1 * x * y + p2 * (r2 + 2.0 * x * x)
    yd = y * radial + p1 * (r2 + 2.0 * y * y) + 2.0 * p2 * x * y
    return fx, fy, cx, cy, xd, yd


def project_camera_points(
    camera: Any,
    camera_xyz: np.ndarray | Sequence[Sequence[float]],
    *,
    min_depth_m: float = 1.0,
) -> ProjectionResult:
    """Project camera-frame points with a supported COLMAP camera model."""

    points = _points3(camera_xyz, "camera_xyz")
    if not np.isfinite(min_depth_m) or min_depth_m < 0.0:
        raise ProjectionError("min_depth_m must be finite and non-negative")
    model, params = _camera_parameters(camera)

    depth = points[:, 2].copy()
    valid = np.all(np.isfinite(points), axis=1) & (depth > float(min_depth_m))
    uv = np.full((len(points), 2), np.nan, dtype=np.float64)
    if not np.any(valid):
        return ProjectionResult(uv=uv, depth=depth, valid=valid)

    chosen = points[valid]
    x = chosen[:, 0] / chosen[:, 2]
    y = chosen[:, 1] / chosen[:, 2]
    fx, fy, cx, cy, xd, yd = _distort_normalized(model, params, x, y)
    projected = np.column_stack((fx * xd + cx, fy * yd + cy))
    finite_projection = np.all(np.isfinite(projected), axis=1)
    valid_indices = np.flatnonzero(valid)
    uv[valid_indices[finite_projection]] = projected[finite_projection]
    valid[valid_indices[~finite_projection]] = False
    return ProjectionResult(uv=uv, depth=depth, valid=valid)


def project_canonical_points(
    points_canonical: np.ndarray | Sequence[Sequence[float]],
    image: Any,
    camera: Any,
    *,
    min_depth_m: float = 1.0,
) -> ProjectionResult:
    """Project canonical world points through a binary-COLMAP-compatible pose."""

    points = _points3(points_canonical, "points_canonical")
    rotation_method = getattr(image, "R", None)
    if not callable(rotation_method):
        raise ProjectionError("COLMAP image must provide an R() rotation method")
    rotation = np.asarray(rotation_method(), dtype=np.float64)
    translation = np.asarray(getattr(image, "tvec", None), dtype=np.float64)
    if rotation.shape != (3, 3) or translation.shape != (3,):
        raise ProjectionError(
            f"invalid COLMAP pose shapes: R={rotation.shape}, tvec={translation.shape}"
        )
    if not np.all(np.isfinite(rotation)) or not np.all(np.isfinite(translation)):
        raise ProjectionError("COLMAP pose must be finite")
    camera_xyz = (rotation @ points.T).T + translation
    return project_camera_points(camera, camera_xyz, min_depth_m=min_depth_m)


def project_base_points(
    points_base: np.ndarray | Sequence[Sequence[float]],
    image: Any,
    camera: Any,
    scene_reference: Mapping[str, Any],
    *,
    input_datum: str,
    geoid_m: float | None = None,
    config_path: str | Path | None = None,
    xy_shift: Sequence[float] = (0.0, 0.0),
    min_depth_m: float = 1.0,
) -> ProjectionResult:
    """Convert explicit-datum base points and project them into an image."""

    points = _points3(points_base, "points_base").copy()
    shift = np.asarray(xy_shift, dtype=np.float64)
    if shift.shape != (2,) or not np.all(np.isfinite(shift)):
        raise ProjectionError(f"xy_shift must contain two finite values, got {xy_shift!r}")
    points[:, :2] += shift
    canonical = base_to_canonical(
        points,
        scene_reference,
        input_datum=input_datum,
        geoid_m=geoid_m,
        config_path=config_path,
    )
    return project_canonical_points(
        canonical,
        image,
        camera,
        min_depth_m=min_depth_m,
    )


def in_frame_mask(result: ProjectionResult, camera: Any) -> np.ndarray:
    """Return valid projected points inside the camera's half-open image bounds."""

    width = int(getattr(camera, "width", 0))
    height = int(getattr(camera, "height", 0))
    if width <= 0 or height <= 0:
        raise ProjectionError(f"camera dimensions must be positive, got {width}x{height}")
    uv = np.asarray(result.uv, dtype=np.float64)
    valid = np.asarray(result.valid, dtype=bool)
    if uv.ndim != 2 or uv.shape[1] != 2 or valid.shape != (len(uv),):
        raise ProjectionError("ProjectionResult has inconsistent uv/valid shapes")
    return (
        valid
        & (uv[:, 0] >= 0.0)
        & (uv[:, 0] < width)
        & (uv[:, 1] >= 0.0)
        & (uv[:, 1] < height)
    )


__all__ = [
    "ELLIPSOIDAL",
    "ORTHOMETRIC",
    "ProjectionError",
    "ProjectionResult",
    "base_to_canonical",
    "canonical_to_base",
    "in_frame_mask",
    "project_base_points",
    "project_camera_points",
    "project_canonical_points",
]

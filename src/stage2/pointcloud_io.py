"""Read a prepared point cloud as Gaussian init (P2 make-or-break v6: MVS-seed init).

INIT/DATA PATH ONLY — no engine logic. The heavy work (AOI crop, per-cloud geoid
Z shift to the GS-LOCAL ellipsoidal frame, voxel downsample, outlier clip) is done
*offline* by ``scripts/input_and_alignment/tum_transfer/tum_mob_seed_prep.sh`` (PDAL, p0-tools
container). This reader just loads the resulting GS-LOCAL cloud so the training
image needs no LAZ/PDAL dependency.

Frame contract: the file is ALREADY in the GS-LOCAL frame (EPSG:25832 minus
world_offset [690953, 5336071, 604], ellipsoidal). NO transform is applied here.
Supported: .ply (via open3d, already used by the TSDF extractor), .npz / .npy.
PLY colours and explicit NPZ ``rgb``/``colors`` arrays are preserved when
present.  RGB is returned in the same float32 [0, 1] convention as COLMAP.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np


_XYZ_KEYS = ("xyz", "points", "P_local", "P_utm_clean", "P_utm")
_RGB_KEYS = ("rgb", "colors", "color", "colours", "colour")


def _validated_xyz(values: np.ndarray, path: Path) -> np.ndarray:
    xyz = np.asarray(values)
    if xyz.ndim != 2 or xyz.shape[1] < 3:
        raise ValueError(f"{path}: point coordinates must have shape (N,>=3)")
    if len(xyz) == 0:
        raise ValueError(f"empty point cloud: {path}")
    if xyz.dtype.kind not in "iuf":
        raise ValueError(f"{path}: point coordinates must be real numeric values")
    xyz = np.ascontiguousarray(xyz[:, :3], dtype=np.float32)
    if not np.isfinite(xyz).all():
        raise ValueError(f"{path}: point coordinates must be finite float32 values")
    return xyz


def _validated_rgb(
    values: np.ndarray,
    point_count: int,
    path: Path,
) -> np.ndarray:
    rgb = np.asarray(values)
    if rgb.shape != (point_count, 3):
        raise ValueError(f"{path}: RGB must have shape ({point_count},3)")
    if rgb.dtype.kind not in "iuf":
        raise ValueError(f"{path}: RGB must be real numeric values")
    if not np.isfinite(rgb).all():
        raise ValueError(f"{path}: RGB must be finite")

    if rgb.dtype.kind in "iu":
        if np.any((rgb < 0) | (rgb > 255)):
            raise ValueError(f"{path}: integer RGB must lie in [0,255]")
        rgb = rgb.astype(np.float32) / 255.0
    else:
        rgb = rgb.astype(np.float32)
        if np.any((rgb < 0.0) | (rgb > 1.0)):
            raise ValueError(f"{path}: floating-point RGB must lie in [0,1]")

    # Check again after conversion so overflow cannot silently enter SH init.
    if not np.isfinite(rgb).all() or np.any((rgb < 0.0) | (rgb > 1.0)):
        raise ValueError(f"{path}: normalized RGB must be finite and lie in [0,1]")
    return np.ascontiguousarray(rgb, dtype=np.float32)


def _npz_xyz_key(npz: np.lib.npyio.NpzFile, path: Path) -> str:
    for key in _XYZ_KEYS:
        if key in npz:
            return key

    # Preserve the historical single-array NPZ convention without guessing
    # among metadata, colour, or multiple geometry-like arrays.
    candidates = []
    excluded = set(_RGB_KEYS) | {"metadata_json", "sem"}
    for key in npz.files:
        if key in excluded:
            continue
        value = np.asarray(npz[key])
        if value.dtype.kind in "iuf" and value.ndim == 2 and value.shape[1] >= 3:
            candidates.append(key)
    if len(candidates) != 1:
        raise ValueError(
            f"{path}: NPZ must contain one coordinate array under "
            f"{_XYZ_KEYS}; unambiguous fallback candidates={candidates}"
        )
    return candidates[0]


def read_init_pointcloud_with_rgb(
    path: str,
) -> tuple[np.ndarray, Optional[np.ndarray]]:
    """Return GS-LOCAL XYZ and optional per-point RGB.

    XYZ is contiguous float32 with shape ``(M,3)``.  RGB, when present, is
    contiguous float32 with the identical shape and values in ``[0,1]``.
    Metadata and semantic arrays in an NPZ are never interpreted as colour.
    """
    p = Path(path)
    suf = p.suffix.lower()
    if suf == ".ply":
        import open3d as o3d  # present in the dev image (cf. tum_mob_tsdf_extract.py)

        pc = o3d.io.read_point_cloud(str(p))
        xyz = _validated_xyz(np.asarray(pc.points), p)
        rgb = (
            _validated_rgb(np.asarray(pc.colors), len(xyz), p)
            if pc.has_colors()
            else None
        )
    elif suf == ".npy":
        xyz = _validated_xyz(np.load(p, allow_pickle=False), p)
        rgb = None
    elif suf == ".npz":
        with np.load(p, allow_pickle=False) as npz:
            xyz = _validated_xyz(npz[_npz_xyz_key(npz, p)], p)
            colour_keys = [key for key in _RGB_KEYS if key in npz]
            if len(colour_keys) > 1:
                raise ValueError(
                    f"{p}: NPZ has ambiguous RGB arrays {colour_keys}; keep exactly one"
                )
            rgb = (
                _validated_rgb(npz[colour_keys[0]], len(xyz), p)
                if colour_keys
                else None
            )
    else:
        raise ValueError(f"unsupported init_pointcloud format: {suf} ({p})")
    return xyz, rgb


def read_init_pointcloud(path: str) -> np.ndarray:
    """Return an (M, 3) float32 array of GS-LOCAL point centres.

    This legacy XYZ-only API intentionally retains its original return type.
    Call :func:`read_init_pointcloud_with_rgb` when seed colour is needed.
    """
    xyz, _rgb = read_init_pointcloud_with_rgb(path)
    return xyz

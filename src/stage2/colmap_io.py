"""COLMAP binary/text IO helpers.

Minimal re-implementation of the parts of scripts/read_write_model.py and
scripts/read_write_dense.py we need: cameras/images/points3D readers and a
reader for COLMAP PatchMatch depth/normal .bin files.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np


# ---------- cameras / images / points3D (binary) ----------

CAMERA_MODEL_IDS = {
    0: ("SIMPLE_PINHOLE", 3),
    1: ("PINHOLE", 4),
    2: ("SIMPLE_RADIAL", 4),
    3: ("RADIAL", 5),
    4: ("OPENCV", 8),
    5: ("OPENCV_FISHEYE", 8),
    6: ("FULL_OPENCV", 12),
    7: ("FOV", 5),
    8: ("SIMPLE_RADIAL_FISHEYE", 4),
    9: ("RADIAL_FISHEYE", 5),
    10: ("THIN_PRISM_FISHEYE", 12),
}
CAMERA_MODEL_NAMES = {v[0]: (k, v[1]) for k, v in CAMERA_MODEL_IDS.items()}


@dataclass
class Camera:
    id: int
    model: str
    width: int
    height: int
    params: np.ndarray  # (num_params,)

    def K(self) -> np.ndarray:
        """Return 3x3 intrinsic matrix (assumes pinhole-like model)."""
        if self.model == "SIMPLE_PINHOLE":
            f, cx, cy = self.params
            fx = fy = f
        elif self.model == "PINHOLE":
            fx, fy, cx, cy = self.params
        elif self.model in ("SIMPLE_RADIAL", "SIMPLE_RADIAL_FISHEYE"):
            f, cx, cy, _ = self.params
            fx = fy = f
        elif self.model in ("RADIAL", "RADIAL_FISHEYE"):
            f, cx, cy, _, _ = self.params
            fx = fy = f
        elif self.model in ("OPENCV", "OPENCV_FISHEYE", "FULL_OPENCV"):
            fx, fy, cx, cy = self.params[:4]
        else:
            raise ValueError(f"Unsupported camera model: {self.model}")
        return np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)


@dataclass
class Image:
    id: int
    qvec: np.ndarray  # (4,) w,x,y,z
    tvec: np.ndarray  # (3,)
    camera_id: int
    name: str

    def R(self) -> np.ndarray:
        w, x, y, z = self.qvec
        return np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
            ],
            dtype=np.float64,
        )

    def world_to_camera(self) -> np.ndarray:
        """4x4 world->camera matrix (COLMAP convention)."""
        T = np.eye(4)
        T[:3, :3] = self.R()
        T[:3, 3] = self.tvec
        return T


def _read(fid, fmt):
    size = struct.calcsize(fmt)
    data = fid.read(size)
    return struct.unpack(fmt, data)


def read_cameras_bin(path: Path) -> Dict[int, Camera]:
    cams: Dict[int, Camera] = {}
    with open(path, "rb") as f:
        (n,) = _read(f, "<Q")
        for _ in range(n):
            cam_id, model_id, width, height = _read(f, "<iiQQ")
            model_name, nparams = CAMERA_MODEL_IDS[model_id]
            params = np.array(_read(f, "<" + "d" * nparams))
            cams[cam_id] = Camera(cam_id, model_name, width, height, params)
    return cams


def read_images_bin(path: Path) -> Dict[int, Image]:
    images: Dict[int, Image] = {}
    with open(path, "rb") as f:
        (n,) = _read(f, "<Q")
        for _ in range(n):
            img_id = _read(f, "<I")[0]
            qvec = np.array(_read(f, "<dddd"))
            tvec = np.array(_read(f, "<ddd"))
            cam_id = _read(f, "<I")[0]
            name = b""
            while True:
                c = f.read(1)
                if c == b"\x00":
                    break
                name += c
            num_pts2d = _read(f, "<Q")[0]
            # skip POINTS2D
            f.read(24 * num_pts2d)  # (x,y,id): d,d,q
            images[img_id] = Image(img_id, qvec, tvec, cam_id, name.decode())
    return images


def read_points3d_bin(path: Path) -> np.ndarray:
    """Return (N,6) array: xyz + rgb[0..255]."""
    out = []
    with open(path, "rb") as f:
        (n,) = _read(f, "<Q")
        for _ in range(n):
            _pid = _read(f, "<Q")[0]
            xyz = _read(f, "<ddd")
            rgb = _read(f, "<BBB")
            _err = _read(f, "<d")[0]
            track_len = _read(f, "<Q")[0]
            f.read(8 * track_len)  # (image_id, pt2d_idx): ii
            out.append((xyz[0], xyz[1], xyz[2], rgb[0], rgb[1], rgb[2]))
    return np.asarray(out, dtype=np.float64)


# ---------- COLMAP dense depth/normal bin ----------

def read_array(path: Path) -> np.ndarray:
    """Read COLMAP dense .bin (depth/normal) produced by PatchMatch.

    File format: "&"-separated header "width&height&channels&\n" then raw float32 row-major.
    """
    with open(path, "rb") as f:
        header = b""
        n_amp = 0
        while n_amp < 3:
            c = f.read(1)
            if not c:
                raise ValueError(f"Unexpected EOF in header: {path}")
            header += c
            if c == b"&":
                n_amp += 1
        # Consume the trailing '\n' if present (COLMAP writes header then newline).
        # Actually COLMAP writes "W&H&C&" with no newline — safe to just parse.
        w, h, ch = [int(x) for x in header.decode().strip("&").split("&") if x]
        arr = np.fromfile(f, dtype=np.float32, count=w * h * ch)
        if ch == 1:
            arr = arr.reshape(h, w)
        else:
            arr = arr.reshape(h, w, ch)
    return arr

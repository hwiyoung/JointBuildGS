"""Seongsu COLMAP-dense dataset loader.

Expects the COLMAP dense workspace produced by scripts/stage2/run_colmap_dense.sh:
    data/seongsu/colmap/dense/
        images/                         # undistorted JPGs
        sparse/                         # undistorted sparse (cameras/images/points3D .bin)
        stereo/depth_maps/*.geometric.bin
        stereo/normal_maps/*.geometric.bin

Images/depths/normals are loaded lazily per __getitem__ and downscaled to `downscale`
(default 0.5). World<-camera extrinsics follow COLMAP convention: x_cam = R * x_world + t.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image as PILImage
import torch
from torch.utils.data import Dataset

from .colmap_io import (
    Camera,
    Image,
    read_array,
    read_cameras_bin,
    read_images_bin,
    read_points3d_bin,
)


@dataclass
class Frame:
    image_id: int
    name: str
    cam_id: int
    image_path: Path
    depth_path: Optional[Path]
    normal_path: Optional[Path]
    K: np.ndarray        # 3x3 intrinsics at native resolution (undistorted)
    R: np.ndarray        # 3x3 world->cam
    t: np.ndarray        # 3 world->cam translation
    width: int
    height: int


class SeongsuDataset(Dataset):
    def __init__(
        self,
        root: str | Path,
        downscale: float = 0.5,
        load_depth: bool = True,
        load_normal: bool = True,
        device: str = "cpu",
    ):
        self.root = Path(root)
        self.downscale = float(downscale)
        self.load_depth = load_depth
        self.load_normal = load_normal
        self.device = device

        dense = self.root / "dense"
        self.image_dir = dense / "images"
        self.depth_dir = dense / "stereo" / "depth_maps"
        self.normal_dir = dense / "stereo" / "normal_maps"
        sparse_dir = dense / "sparse"
        # Support both flat (sparse/*.bin) and nested (sparse/0/*.bin) layouts
        if (sparse_dir / "0" / "cameras.bin").exists():
            sparse_dir = sparse_dir / "0"

        self.cameras: Dict[int, Camera] = read_cameras_bin(sparse_dir / "cameras.bin")
        colmap_images: Dict[int, Image] = read_images_bin(sparse_dir / "images.bin")
        pts = read_points3d_bin(sparse_dir / "points3D.bin")
        self.points_xyz = pts[:, :3].astype(np.float32)
        self.points_rgb = pts[:, 3:6].astype(np.float32) / 255.0

        self.frames: List[Frame] = []
        for img_id, img in colmap_images.items():
            cam = self.cameras[img.camera_id]
            img_path = self.image_dir / img.name
            if not img_path.exists():
                continue
            depth_path = self.depth_dir / f"{img.name}.geometric.bin"
            if not depth_path.exists():
                depth_path = self.depth_dir / f"{img.name}.photometric.bin"
            normal_path = self.normal_dir / f"{img.name}.geometric.bin"
            if not normal_path.exists():
                normal_path = self.normal_dir / f"{img.name}.photometric.bin"
            self.frames.append(
                Frame(
                    image_id=img_id,
                    name=img.name,
                    cam_id=img.camera_id,
                    image_path=img_path,
                    depth_path=depth_path if depth_path.exists() else None,
                    normal_path=normal_path if normal_path.exists() else None,
                    K=cam.K(),
                    R=img.R(),
                    t=img.tvec.copy(),
                    width=cam.width,
                    height=cam.height,
                )
            )
        self.frames.sort(key=lambda f: f.name)

    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.frames)

    def image_size(self, idx: int = 0) -> Tuple[int, int]:
        """Return (H, W) after downscale."""
        fr = self.frames[idx]
        H = int(round(fr.height * self.downscale))
        W = int(round(fr.width * self.downscale))
        return H, W

    def scaled_K(self, idx: int = 0) -> np.ndarray:
        fr = self.frames[idx]
        K = fr.K.copy()
        K[0, 0] *= self.downscale
        K[1, 1] *= self.downscale
        K[0, 2] *= self.downscale
        K[1, 2] *= self.downscale
        return K

    # ------------------------------------------------------------------
    def __getitem__(self, idx: int) -> dict:
        fr = self.frames[idx]
        H = int(round(fr.height * self.downscale))
        W = int(round(fr.width * self.downscale))

        # RGB
        pil = PILImage.open(fr.image_path).convert("RGB")
        if (pil.size[0], pil.size[1]) != (W, H):
            pil = pil.resize((W, H), PILImage.BILINEAR)
        rgb = np.asarray(pil, dtype=np.float32) / 255.0  # (H,W,3)

        # Depth
        depth = None
        depth_mask = None
        if self.load_depth and fr.depth_path is not None:
            d = read_array(fr.depth_path)  # (H0, W0)
            d = _resize_float(d, (H, W), order="bilinear")
            depth_mask = d > 0
            depth = np.where(depth_mask, d, 0.0)

        # Normal (COLMAP normals are in camera coord; 0 means invalid)
        normal = None
        normal_mask = None
        if self.load_normal and fr.normal_path is not None:
            n = read_array(fr.normal_path)  # (H0, W0, 3)
            n = _resize_float(n, (H, W), order="bilinear")
            norm = np.linalg.norm(n, axis=-1, keepdims=True)
            normal_mask = (norm[..., 0] > 1e-3)
            n = np.where(norm > 1e-6, n / np.maximum(norm, 1e-6), 0.0)
            normal = n.astype(np.float32)

        # Build world->cam 4x4
        w2c = np.eye(4, dtype=np.float32)
        w2c[:3, :3] = fr.R
        w2c[:3, 3] = fr.t
        K = self.scaled_K(idx).astype(np.float32)

        out = {
            "image_id": fr.image_id,
            "name": fr.name,
            "rgb": torch.from_numpy(rgb),                         # (H,W,3) float32 [0,1]
            "w2c": torch.from_numpy(w2c),                         # (4,4)
            "K": torch.from_numpy(K),                             # (3,3)
            "height": H,
            "width": W,
        }
        if depth is not None:
            out["depth"] = torch.from_numpy(depth.astype(np.float32))             # (H,W)
            out["depth_mask"] = torch.from_numpy(depth_mask.astype(np.bool_))     # (H,W)
        if normal is not None:
            out["normal"] = torch.from_numpy(normal)                               # (H,W,3)
            out["normal_mask"] = torch.from_numpy(normal_mask.astype(np.bool_))   # (H,W)
        return out


def _resize_float(arr: np.ndarray, size_hw: Tuple[int, int], order: str = "bilinear") -> np.ndarray:
    """Resize float array via PIL. Supports (H,W) or (H,W,C)."""
    import cv2

    H, W = size_hw
    interp = cv2.INTER_LINEAR if order == "bilinear" else cv2.INTER_NEAREST
    if arr.ndim == 2:
        return cv2.resize(arr, (W, H), interpolation=interp)
    out = cv2.resize(arr, (W, H), interpolation=interp)
    return out

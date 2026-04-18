"""COLMAP dataset loader with optional depth/normal GT.

Supported GT formats:
  A) COLMAP PatchMatch MVS: stereo/depth_maps/*.{geometric,photometric}.bin
     stereo/normal_maps/*.{geometric,photometric}.bin

  B) MatrixCity-style synthetic GT: depth/*.exr and normal/*.exr
     (EXR format via OpenCV, BGR ordered; normals encoded as (n+1)/2)

Standard COLMAP directory layout:
    root/
        images/                          # RGB images
        sparse/0/                        # SfM output
        stereo/                          # (optional) COLMAP MVS
        depth/                           # (optional) MatrixCity GT depth (EXR)
        normal/                          # (optional) MatrixCity GT normal (EXR)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image as PILImage
import torch
from torch.utils.data import Dataset

# Enable OpenEXR support in OpenCV
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2  # noqa: E402

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
    depth_format: str                   # "colmap_bin" | "exr" | None
    normal_format: str                  # "colmap_bin" | "exr" | None
    K: np.ndarray
    R: np.ndarray
    t: np.ndarray
    width: int
    height: int


class ColmapDataset(Dataset):
    """COLMAP dataset loader supporting COLMAP MVS and MatrixCity GT formats.

    Args:
        root: Path containing images/, sparse/0/, and optionally stereo/ or depth/, normal/.
        downscale: Image downscale factor (1.0 = native).
        load_depth: Load depth maps (auto-detects colmap MVS or EXR GT).
        load_normal: Load normal maps (auto-detects).
        depth_far_sentinel: EXR GT frequently uses a large "sky" value; mask out
            pixels >= this value (None = no masking beyond > 0).
        normal_encoding: "raw" or "half_range" (MatrixCity uses (n+1)/2 → "half_range").
    """

    def __init__(
        self,
        root: str | Path,
        downscale: float = 1.0,
        load_depth: bool = True,
        load_normal: bool = True,
        load_semantic: bool = False,
        depth_far_sentinel: Optional[float] = 28000.0,
        depth_scale: float = 1.0,
        normal_encoding: str = "half_range",
    ):
        self.root = Path(root)
        self.downscale = float(downscale)
        self.load_depth = load_depth
        self.load_normal = load_normal
        self.load_semantic = load_semantic
        self.semantic_dir = self.root / "semantic"
        self.depth_far_sentinel = depth_far_sentinel
        self.depth_scale = float(depth_scale)
        self.normal_encoding = normal_encoding

        self.image_dir = self.root / "images"
        # COLMAP PatchMatch layout
        self.colmap_depth_dir = self.root / "stereo" / "depth_maps"
        self.colmap_normal_dir = self.root / "stereo" / "normal_maps"
        # MatrixCity-style GT layout
        self.exr_depth_dir = self.root / "depth"
        self.exr_normal_dir = self.root / "normal"

        sparse_dir = self.root / "sparse"
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

            dpath, dfmt = self._find_depth(img.name)
            npath, nfmt = self._find_normal(img.name)

            self.frames.append(
                Frame(
                    image_id=img_id, name=img.name, cam_id=img.camera_id,
                    image_path=img_path,
                    depth_path=dpath, depth_format=dfmt,
                    normal_path=npath, normal_format=nfmt,
                    K=cam.K(), R=img.R(), t=img.tvec.copy(),
                    width=cam.width, height=cam.height,
                )
            )
        self.frames.sort(key=lambda f: f.name)

    def _find_depth(self, img_name: str) -> Tuple[Optional[Path], Optional[str]]:
        # COLMAP PatchMatch .bin
        for suffix in [".geometric.bin", ".photometric.bin"]:
            p = self.colmap_depth_dir / f"{img_name}{suffix}"
            if p.exists():
                return p, "colmap_bin"
        # EXR GT (MatrixCity): same base name, .exr extension
        stem = Path(img_name).stem
        p = self.exr_depth_dir / f"{stem}.exr"
        if p.exists():
            return p, "exr"
        return None, None

    def _find_normal(self, img_name: str) -> Tuple[Optional[Path], Optional[str]]:
        for suffix in [".geometric.bin", ".photometric.bin"]:
            p = self.colmap_normal_dir / f"{img_name}{suffix}"
            if p.exists():
                return p, "colmap_bin"
        stem = Path(img_name).stem
        p = self.exr_normal_dir / f"{stem}.exr"
        if p.exists():
            return p, "exr"
        return None, None

    def __len__(self) -> int:
        return len(self.frames)

    def image_size(self, idx: int = 0) -> Tuple[int, int]:
        fr = self.frames[idx]
        H = int(round(fr.height * self.downscale))
        W = int(round(fr.width * self.downscale))
        return H, W

    def scaled_K(self, idx: int = 0) -> np.ndarray:
        fr = self.frames[idx]
        K = fr.K.copy()
        K[0, :] *= self.downscale
        K[1, :] *= self.downscale
        return K

    def _load_depth(self, fr: Frame, H: int, W: int):
        if fr.depth_path is None:
            return None, None
        if fr.depth_format == "colmap_bin":
            d = read_array(fr.depth_path)
            d = _resize_float(d, (H, W))
            mask = d > 0
            return np.where(mask, d, 0.0).astype(np.float32), mask
        # EXR (MatrixCity): 4 channels, all identical, float32
        raw = cv2.imread(str(fr.depth_path), cv2.IMREAD_UNCHANGED)
        if raw is None:
            return None, None
        d = raw[..., 0] if raw.ndim == 3 else raw
        d = _resize_float(d, (H, W))
        mask = d > 0
        if self.depth_far_sentinel is not None:
            mask &= d < self.depth_far_sentinel
        d = d * self.depth_scale
        return np.where(mask, d, 0.0).astype(np.float32), mask

    def _load_normal(self, fr: Frame, H: int, W: int):
        """Load normal map and return in WORLD frame.

        COLMAP PatchMatch normals are in camera frame → transform to world using R_c2w.
        MatrixCity EXR normals are already in world frame.
        """
        if fr.normal_path is None:
            return None, None
        if fr.normal_format == "colmap_bin":
            n_cam = read_array(fr.normal_path)
            n_cam = _resize_float(n_cam, (H, W))
            norm = np.linalg.norm(n_cam, axis=-1, keepdims=True)
            mask = norm[..., 0] > 1e-3
            n_cam = np.where(norm > 1e-6, n_cam / np.maximum(norm, 1e-6), 0.0)
            # camera -> world:  n_world = R_c2w @ n_cam
            R_c2w = fr.R.T  # inverse of rotation part of w2c
            n_world = n_cam @ R_c2w.T
            return n_world.astype(np.float32), mask
        # EXR (MatrixCity): BGR(A) → RGB, (n+1)/2 decode; already in WORLD frame
        raw = cv2.imread(str(fr.normal_path), cv2.IMREAD_UNCHANGED)
        if raw is None:
            return None, None
        n_enc = raw[..., :3][..., ::-1].astype(np.float32)
        n = n_enc * 2.0 - 1.0 if self.normal_encoding == "half_range" else n_enc
        norm = np.linalg.norm(n, axis=-1, keepdims=True)
        mask = norm[..., 0] > 0.5
        n = np.where(norm > 1e-6, n / np.maximum(norm, 1e-6), 0.0)
        n = _resize_float(n, (H, W))
        mask = _resize_float(mask.astype(np.float32), (H, W)) > 0.5
        return n.astype(np.float32), mask

    def __getitem__(self, idx: int) -> dict:
        fr = self.frames[idx]
        H = int(round(fr.height * self.downscale))
        W = int(round(fr.width * self.downscale))

        pil = PILImage.open(fr.image_path).convert("RGB")
        if (pil.size[0], pil.size[1]) != (W, H):
            pil = pil.resize((W, H), PILImage.BILINEAR)
        rgb = np.asarray(pil, dtype=np.float32) / 255.0

        depth, depth_mask = (None, None)
        if self.load_depth:
            depth, depth_mask = self._load_depth(fr, H, W)

        normal, normal_mask = (None, None)
        if self.load_normal:
            normal, normal_mask = self._load_normal(fr, H, W)

        semantic = None
        if self.load_semantic:
            stem = Path(fr.name).stem
            sem_path = self.semantic_dir / f"{stem}.png"
            if sem_path.exists():
                lbl = np.asarray(PILImage.open(sem_path))  # (H0, W0) uint8, 0..3
                if lbl.shape[:2] != (H, W):
                    lbl = cv2.resize(lbl, (W, H), interpolation=cv2.INTER_NEAREST)
                semantic = lbl.astype(np.int64)

        w2c = np.eye(4, dtype=np.float32)
        w2c[:3, :3] = fr.R
        w2c[:3, 3] = fr.t
        K = self.scaled_K(idx).astype(np.float32)

        out = {
            "image_id": fr.image_id,
            "name": fr.name,
            "rgb": torch.from_numpy(rgb),
            "w2c": torch.from_numpy(w2c),
            "K": torch.from_numpy(K),
            "height": H,
            "width": W,
        }
        if depth is not None:
            out["depth"] = torch.from_numpy(depth)
            out["depth_mask"] = torch.from_numpy(depth_mask.astype(np.bool_))
        if normal is not None:
            out["normal"] = torch.from_numpy(normal)
            out["normal_mask"] = torch.from_numpy(normal_mask.astype(np.bool_))
        if semantic is not None:
            out["semantic"] = torch.from_numpy(semantic)
        return out


def _resize_float(arr: np.ndarray, size_hw: Tuple[int, int]) -> np.ndarray:
    H, W = size_hw
    if arr.shape[:2] == (H, W):
        return arr
    return cv2.resize(arr, (W, H), interpolation=cv2.INTER_LINEAR)

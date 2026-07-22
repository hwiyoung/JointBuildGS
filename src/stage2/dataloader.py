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
from typing import Dict, List, Optional, Sequence, Tuple

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
from .pilot_mask_schema import (
    MONO_GATE_CONSUMER_ARMS,
    BinaryMaskSet,
    MaskPurpose,
    MaskSchemaError,
    MaskSource,
    sha256_file,
)


@dataclass
class Frame:
    image_id: int
    name: str
    cam_id: int
    image_path: Path
    depth_path: Optional[Path]
    normal_path: Optional[Path]
    mono_normal_path: Optional[Path]
    mono_depth_path: Optional[Path]
    depth_format: str                   # "colmap_bin" | "exr" | None
    normal_format: str                  # "colmap_bin" | "exr" | None
    mono_normal_format: str             # "npy_world" | "exr" | None
    mono_depth_format: str              # "npy" | "exr" | None
    K: np.ndarray
    R: np.ndarray
    t: np.ndarray
    width: int
    height: int


def _view_lookup(frames: Sequence[Frame]) -> Dict[str, int]:
    """Map exact name, basename and stem to one unambiguous frame index."""

    lookup: Dict[str, int] = {}
    ambiguous: set[str] = set()
    for index, frame in enumerate(frames):
        keys = {str(frame.name), Path(frame.name).name, Path(frame.name).stem}
        for key in keys:
            if key in lookup and lookup[key] != index:
                ambiguous.add(key)
            else:
                lookup[key] = index
    for key in ambiguous:
        lookup.pop(key, None)
    return lookup


def resolve_view_roles(
    frames: Sequence[Frame],
    train_views: Optional[Sequence[str]] = None,
    eval_views: Optional[Sequence[str]] = None,
) -> tuple[List[int], List[int], dict]:
    """Resolve locked filename roles, or reproduce the legacy 10th-view split.

    Explicit roles must be disjoint and cover every already-filtered frame.  An
    empty eval list is valid for three-view crops; evaluation then records no
    aggregate instead of a NaN.  Supplying neither key preserves old behavior.
    """

    if train_views is None and eval_views is None:
        test_idx = [i for i in range(len(frames)) if i % 10 == 9]
        train_idx = [i for i in range(len(frames)) if i not in test_idx]
        return train_idx, test_idx, {
            "mode": "legacy_every_10th_eval",
            "train_views": [frames[i].name for i in train_idx],
            "eval_views": [frames[i].name for i in test_idx],
        }
    if train_views is None or eval_views is None:
        raise ValueError("train_views and eval_views must be supplied together")

    lookup = _view_lookup(frames)

    def resolve(names: Sequence[str], role: str) -> List[int]:
        indices: List[int] = []
        missing: List[str] = []
        for value in names:
            key = str(value)
            if key not in lookup:
                missing.append(key)
            else:
                indices.append(lookup[key])
        if missing:
            raise ValueError(f"unknown or ambiguous {role} views: {missing}")
        if len(indices) != len(set(indices)):
            raise ValueError(f"duplicate frame in {role}_views")
        return indices

    train_idx = resolve(train_views, "train")
    eval_idx = resolve(eval_views, "eval")
    if not train_idx:
        raise ValueError("train_views must contain at least one frame")
    overlap = sorted(set(train_idx) & set(eval_idx))
    if overlap:
        raise ValueError(
            f"train/eval roles overlap: {[frames[i].name for i in overlap]}"
        )
    covered = set(train_idx) | set(eval_idx)
    if covered != set(range(len(frames))):
        unused = [frames[i].name for i in range(len(frames)) if i not in covered]
        raise ValueError(f"explicit view roles leave frames unassigned: {unused}")
    return train_idx, eval_idx, {
        "mode": "explicit_locked_roles",
        "train_views": [frames[i].name for i in train_idx],
        "eval_views": [frames[i].name for i in eval_idx],
    }


_PILOT_ARMS = frozenset(MONO_GATE_CONSUMER_ARMS)
_PLANE_SOURCE_BY_ARM = {
    "04a_plane_medium_vision": MaskSource.VISION_GROUNDEDSAM_ROOF,
    "04b_plane_medium_gt_upperbound": MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND,
}


def _validate_pilot_arm(pilot_arm: Optional[str]) -> Optional[str]:
    if pilot_arm is None:
        return None
    if not isinstance(pilot_arm, str) or pilot_arm not in _PILOT_ARMS:
        raise ValueError(
            "pilot_arm must be one of the locked first-wave arms: "
            f"{sorted(_PILOT_ARMS)}"
        )
    return pilot_arm


def _resize_binary_mask(mask: np.ndarray, size_hw: Tuple[int, int]) -> np.ndarray:
    """Nearest-resize one validated bool HxW mask for a training frame."""

    value = np.asarray(mask)
    if value.ndim != 2 or value.dtype != np.bool_:
        raise MaskSchemaError(
            f"runtime mask must be a bool HxW array, got {value.dtype} {value.shape}"
        )
    height, width = (int(size_hw[0]), int(size_hw[1]))
    if height <= 0 or width <= 0:
        raise MaskSchemaError(f"invalid training mask shape: {(height, width)}")
    if value.shape == (height, width):
        resized = np.ascontiguousarray(value)
    else:
        resized = cv2.resize(
            value.astype(np.uint8),
            (width, height),
            interpolation=cv2.INTER_NEAREST,
        ).astype(np.bool_)
    if not bool(resized.any()):
        raise MaskSchemaError(
            "nearest resize produced an empty runtime mask; refusing silent loss disable"
        )
    return np.ascontiguousarray(resized)


@dataclass(frozen=True)
class PilotMaskBinding:
    """Strict mapping from one immutable mask inventory to dataset frames."""

    role: str
    mask_set: BinaryMaskSet
    record_id_by_frame_name: Dict[str, str]
    audit: dict

    def load(self, frame: Frame, size_hw: Tuple[int, int]) -> np.ndarray:
        try:
            record_id = self.record_id_by_frame_name[frame.name]
        except KeyError as exc:  # Defensive: construction requires full coverage.
            raise MaskSchemaError(
                f"{self.role} mask is missing at runtime for frame {frame.name!r}"
            ) from exc
        return _resize_binary_mask(self.mask_set.load(record_id), size_hw)


def _bind_pilot_mask_manifest(
    manifest_path: str | Path,
    *,
    frames: Sequence[Frame],
    downscale: float,
    pilot_arm: Optional[str],
    role: str,
) -> PilotMaskBinding:
    """Validate purpose, source, consumer arm and exact frame inventory.

    ``role`` is deliberately closed to two loss-side masks plus the separate
    projected-footprint audit scope accepted by the first-wave runtime.  Every
    archive is opened during binding, so a missing,
    hash-mismatched, side-channel, or shape-mismatched file fails before the
    first optimizer step rather than on a later sampled view.
    """

    arm = _validate_pilot_arm(pilot_arm)
    if arm is None:
        raise MaskSchemaError(f"pilot_arm is required with {role}_mask_manifest")
    if role not in {"photo", "plane_region", "roof_audit"}:
        raise ValueError(f"unsupported pilot mask role: {role!r}")

    mask_set = BinaryMaskSet(manifest_path)
    if role in {"photo", "roof_audit"}:
        expected_purpose = MaskPurpose.PHOTO_SUPPORT
        expected_source = MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT
    else:
        expected_purpose = MaskPurpose.PLANE_REGION
        expected_source = _PLANE_SOURCE_BY_ARM.get(arm)
        if expected_source is None:
            raise MaskSchemaError(
                "plane_region_mask_manifest is permitted only for "
                "04a_plane_medium_vision or 04b_plane_medium_gt_upperbound"
            )

    if mask_set.purpose is not expected_purpose:
        raise MaskSchemaError(
            f"{role} manifest purpose mismatch: "
            f"{mask_set.purpose.value} != {expected_purpose.value}"
        )
    if mask_set.source is not expected_source:
        raise MaskSchemaError(
            f"{role} manifest source mismatch for {arm}: "
            f"{mask_set.source.value} != {expected_source.value}"
        )
    # ``consumer_arms`` describes loss-side photo masking.  The same immutable
    # projected-footprint inventory is also the preregistered, audit-only roof
    # scope for all five arms, including arm 01.  Keep that role in a distinct
    # batch key so accepting it can never enable arm-01 photo masking.
    if role != "roof_audit" and arm not in mask_set.consumer_arms:
        raise MaskSchemaError(
            f"pilot arm {arm} is not a declared consumer of the {role} manifest"
        )

    lookup = _view_lookup(frames)
    unknown = sorted(view_id for view_id in mask_set.records if view_id not in lookup)
    if unknown:
        raise MaskSchemaError(
            f"{role} mask inventory contains outside/unknown views: {unknown}"
        )
    record_by_index: Dict[int, str] = {}
    duplicate_frames: list[str] = []
    for view_id in mask_set.records:
        frame_index = lookup[view_id]
        if frame_index in record_by_index:
            duplicate_frames.append(frames[frame_index].name)
        else:
            record_by_index[frame_index] = view_id
    if duplicate_frames:
        raise MaskSchemaError(
            f"{role} mask inventory maps multiple records to frames: "
            f"{sorted(duplicate_frames)}"
        )
    missing = [
        frame.name for index, frame in enumerate(frames) if index not in record_by_index
    ]
    if missing:
        raise MaskSchemaError(f"{role} mask inventory is missing views: {missing}")

    source_shapes: set[tuple[int, int]] = set()
    target_shapes: set[tuple[int, int]] = set()
    record_id_by_frame_name: Dict[str, str] = {}
    for frame_index, frame in enumerate(frames):
        record_id = record_by_index[frame_index]
        source_mask = mask_set.load(record_id)
        target_shape = (
            int(round(frame.height * float(downscale))),
            int(round(frame.width * float(downscale))),
        )
        _resize_binary_mask(source_mask, target_shape)
        source_shapes.add(tuple(int(value) for value in source_mask.shape))
        target_shapes.add(target_shape)
        record_id_by_frame_name[frame.name] = record_id

    audit = {
        "role": role,
        "pilot_arm": arm,
        "manifest_path": str(Path(manifest_path).resolve()),
        "manifest_sha256": sha256_file(Path(manifest_path)),
        "purpose": mask_set.purpose.value,
        "source": mask_set.source.value,
        "consumer_arms": list(mask_set.consumer_arms),
        "inventory_sha256": mask_set.inventory_sha256,
        "view_count": len(record_id_by_frame_name),
        "source_shapes": [list(shape) for shape in sorted(source_shapes)],
        "training_shapes": [list(shape) for shape in sorted(target_shapes)],
        "resize_interpolation": "nearest",
        "inventory_match": "exact",
        "preflight_loaded_all_records": True,
        "loss_consuming": role != "roof_audit",
        "consumer_contract_enforced": role != "roof_audit",
    }
    return PilotMaskBinding(
        role=role,
        mask_set=mask_set,
        record_id_by_frame_name=record_id_by_frame_name,
        audit=audit,
    )


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
        normal_dir: Optional[str | Path] = None,
        mono_normal_dir: Optional[str | Path] = None,
        mono_depth_dir: Optional[str | Path] = None,
        depth_far_sentinel: Optional[float] = 28000.0,
        mono_depth_far_sentinel: Optional[float] = 28000.0,
        depth_scale: float = 1.0,
        mono_depth_scale: float = 1.0,
        normal_encoding: str = "half_range",
        visible_views: Optional[Sequence[str]] = None,
        photo_mask_manifest: Optional[str | Path] = None,
        roof_audit_mask_manifest: Optional[str | Path] = None,
        plane_region_mask_manifest: Optional[str | Path] = None,
        pilot_arm: Optional[str] = None,
    ):
        self.root = Path(root)
        self.downscale = float(downscale)
        self.load_depth = load_depth
        self.load_normal = load_normal
        self.load_semantic = load_semantic
        self.semantic_dir = self.root / "semantic"
        self.override_normal_dir = self._resolve_aux_dir(normal_dir)
        self.mono_normal_dir = self._resolve_aux_dir(mono_normal_dir)
        self.mono_depth_dir = self._resolve_aux_dir(mono_depth_dir)
        self.depth_far_sentinel = depth_far_sentinel
        self.mono_depth_far_sentinel = mono_depth_far_sentinel
        self.depth_scale = float(depth_scale)
        self.mono_depth_scale = float(mono_depth_scale)
        self.normal_encoding = normal_encoding
        self.pilot_arm = _validate_pilot_arm(pilot_arm)

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
            mnpath, mnfmt = self._find_mono_normal(img.name)
            mdpath, mdfmt = self._find_mono_depth(img.name)

            self.frames.append(
                Frame(
                    image_id=img_id, name=img.name, cam_id=img.camera_id,
                    image_path=img_path,
                    depth_path=dpath, depth_format=dfmt,
                    normal_path=npath, normal_format=nfmt,
                    mono_normal_path=mnpath, mono_normal_format=mnfmt,
                    mono_depth_path=mdpath, mono_depth_format=mdfmt,
                    K=cam.K(), R=img.R(), t=img.tvec.copy(),
                    width=cam.width, height=cam.height,
                )
            )
        self.frames.sort(key=lambda f: f.name)
        self.visible_view_audit = {
            "mode": "all_colmap_views",
            "requested": None,
            "resolved": [frame.name for frame in self.frames],
        }
        if visible_views is not None:
            lookup = _view_lookup(self.frames)
            requested = [str(value) for value in visible_views]
            missing = [value for value in requested if value not in lookup]
            if missing:
                raise ValueError(f"unknown or ambiguous visible_views: {missing}")
            selected = [lookup[value] for value in requested]
            if len(selected) != len(set(selected)):
                raise ValueError("visible_views resolves the same frame more than once")
            self.frames = [self.frames[index] for index in selected]
            self.visible_view_audit = {
                "mode": "explicit_locked_visible_views",
                "requested": requested,
                "resolved": [frame.name for frame in self.frames],
            }

        self.photo_mask_binding = None
        if photo_mask_manifest is not None:
            self.photo_mask_binding = _bind_pilot_mask_manifest(
                photo_mask_manifest,
                frames=self.frames,
                downscale=self.downscale,
                pilot_arm=self.pilot_arm,
                role="photo",
            )
        self.roof_audit_mask_binding = None
        if roof_audit_mask_manifest is not None:
            self.roof_audit_mask_binding = _bind_pilot_mask_manifest(
                roof_audit_mask_manifest,
                frames=self.frames,
                downscale=self.downscale,
                pilot_arm=self.pilot_arm,
                role="roof_audit",
            )
        self.plane_region_mask_binding = None
        if plane_region_mask_manifest is not None:
            self.plane_region_mask_binding = _bind_pilot_mask_manifest(
                plane_region_mask_manifest,
                frames=self.frames,
                downscale=self.downscale,
                pilot_arm=self.pilot_arm,
                role="plane_region",
            )
        self.pilot_mask_audit = {
            "pilot_arm": self.pilot_arm,
            "photo_mask": (
                None
                if self.photo_mask_binding is None
                else self.photo_mask_binding.audit
            ),
            "roof_audit_mask": (
                None
                if self.roof_audit_mask_binding is None
                else self.roof_audit_mask_binding.audit
            ),
            "plane_region_mask": (
                None
                if self.plane_region_mask_binding is None
                else self.plane_region_mask_binding.audit
            ),
        }

    def _resolve_aux_dir(self, value: Optional[str | Path]) -> Optional[Path]:
        if value is None or str(value).strip() == "":
            return None
        p = Path(value)
        if not p.is_absolute():
            p = self.root / p
        return p

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
        stem = Path(img_name).stem
        if self.override_normal_dir is not None:
            for suffix, fmt in [(".npy", "npy_world"), (".exr", "exr")]:
                p = self.override_normal_dir / f"{stem}{suffix}"
                if p.exists():
                    return p, fmt
        for suffix in [".geometric.bin", ".photometric.bin"]:
            p = self.colmap_normal_dir / f"{img_name}{suffix}"
            if p.exists():
                return p, "colmap_bin"
        p = self.exr_normal_dir / f"{stem}.exr"
        if p.exists():
            return p, "exr"
        return None, None

    def _find_mono_depth(self, img_name: str) -> Tuple[Optional[Path], Optional[str]]:
        if self.mono_depth_dir is None:
            return None, None
        stem = Path(img_name).stem
        for suffix, fmt in [(".npy", "npy"), (".exr", "exr")]:
            p = self.mono_depth_dir / f"{stem}{suffix}"
            if p.exists():
                return p, fmt
        return None, None

    def _find_mono_normal(
        self, img_name: str
    ) -> Tuple[Optional[Path], Optional[str]]:
        if self.mono_normal_dir is None:
            return None, None
        stem = Path(img_name).stem
        for suffix, fmt in [(".npy", "npy_world"), (".exr", "exr")]:
            path = self.mono_normal_dir / f"{stem}{suffix}"
            if path.exists():
                return path, fmt
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

    def _load_mono_depth(self, fr: Frame, H: int, W: int):
        if fr.mono_depth_path is None:
            return None, None
        if fr.mono_depth_format == "npy":
            d = np.load(fr.mono_depth_path).astype(np.float32)
        else:
            raw = cv2.imread(str(fr.mono_depth_path), cv2.IMREAD_UNCHANGED)
            if raw is None:
                return None, None
            d = raw[..., 0] if raw.ndim == 3 else raw
        d = _resize_float(d, (H, W))
        d = d * self.mono_depth_scale
        mask = np.isfinite(d) & (d > 0)
        if self.mono_depth_far_sentinel is not None:
            mask &= d < self.mono_depth_far_sentinel
        return np.where(mask, d, 0.0).astype(np.float32), mask

    def _load_normal_path(
        self,
        fr: Frame,
        path: Optional[Path],
        normal_format: Optional[str],
        H: int,
        W: int,
    ):
        """Load normal map and return in WORLD frame.

        COLMAP PatchMatch normals are in camera frame → transform to world using R_c2w.
        MatrixCity EXR normals are already in world frame.
        """
        if path is None:
            return None, None
        if normal_format == "npy_world":
            n = np.load(path, allow_pickle=False).astype(np.float32)
            if n.ndim == 3 and n.shape[0] == 3 and n.shape[-1] != 3:
                n = np.moveaxis(n, 0, -1)
            n = _resize_float(n, (H, W))
            norm = np.linalg.norm(n, axis=-1, keepdims=True)
            mask = norm[..., 0] > 0.5
            n = np.where(norm > 1e-6, n / np.maximum(norm, 1e-6), 0.0)
            return n.astype(np.float32), mask
        if normal_format == "colmap_bin":
            n_cam = read_array(path)
            n_cam = _resize_float(n_cam, (H, W))
            norm = np.linalg.norm(n_cam, axis=-1, keepdims=True)
            mask = norm[..., 0] > 1e-3
            n_cam = np.where(norm > 1e-6, n_cam / np.maximum(norm, 1e-6), 0.0)
            # camera -> world:  n_world = R_c2w @ n_cam
            R_c2w = fr.R.T  # inverse of rotation part of w2c
            n_world = n_cam @ R_c2w.T
            return n_world.astype(np.float32), mask
        # EXR (MatrixCity): BGR(A) → RGB, (n+1)/2 decode; already in WORLD frame
        if normal_format != "exr":
            raise ValueError(f"unsupported normal format: {normal_format!r}")
        raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
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

    def _load_normal(self, fr: Frame, H: int, W: int):
        return self._load_normal_path(
            fr, fr.normal_path, fr.normal_format, H, W
        )

    def _load_mono_normal(self, fr: Frame, H: int, W: int):
        return self._load_normal_path(
            fr, fr.mono_normal_path, fr.mono_normal_format, H, W
        )

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

        mono_depth, mono_depth_mask = self._load_mono_depth(fr, H, W)

        normal, normal_mask = (None, None)
        if self.load_normal:
            normal, normal_mask = self._load_normal(fr, H, W)

        mono_normal, mono_normal_mask = self._load_mono_normal(fr, H, W)

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
        if mono_depth is not None:
            out["mono_depth"] = torch.from_numpy(mono_depth)
            out["mono_depth_mask"] = torch.from_numpy(mono_depth_mask.astype(np.bool_))
        if normal is not None:
            out["normal"] = torch.from_numpy(normal)
            out["normal_mask"] = torch.from_numpy(normal_mask.astype(np.bool_))
        if mono_normal is not None:
            out["mono_normal"] = torch.from_numpy(mono_normal)
            out["mono_normal_mask"] = torch.from_numpy(
                mono_normal_mask.astype(np.bool_)
            )
        if self.photo_mask_binding is not None:
            out["photo_mask"] = torch.from_numpy(
                self.photo_mask_binding.load(fr, (H, W))
            )
        roof_audit_binding = getattr(self, "roof_audit_mask_binding", None)
        if roof_audit_binding is not None:
            out["roof_audit_mask"] = torch.from_numpy(
                roof_audit_binding.load(fr, (H, W))
            )
        if self.plane_region_mask_binding is not None:
            out["plane_region_mask"] = torch.from_numpy(
                self.plane_region_mask_binding.load(fr, (H, W))
            )
        if semantic is not None:
            out["semantic"] = torch.from_numpy(semantic)
        return out


def _resize_float(arr: np.ndarray, size_hw: Tuple[int, int]) -> np.ndarray:
    H, W = size_hw
    if arr.shape[:2] == (H, W):
        return arr
    return cv2.resize(arr, (W, H), interpolation=cv2.INTER_LINEAR)

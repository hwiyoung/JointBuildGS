"""Immutable binary per-view mask contract for the pilot first wave.

The training engine intentionally does not depend on this module yet.  It is a
small, strict boundary between mask generation and later loss integration:

* every archive contains exactly one ``bool`` HxW array named ``mask``;
* every file and every provenance component is addressed by SHA-256;
* the manifest uses a closed schema and a finite source enumeration; and
* arms 02--04b share one inventory instead of receiving private copies.

In particular, an NPZ carrying roof heights, region IDs, LoD2 coordinates, or
any other numeric side-channel is rejected even when it also contains a valid
binary mask.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import secrets
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

import numpy as np
import torch


SCHEMA = "jointbuildgs.pilot_binary_view_masks.v1"
RUN_ID = "20260721_pilot_1wave"
CRS = "EPSG:25832"
PHOTO_SUPPORT_CONSUMER_ARMS = (
    "02_photo_control",
    "03_plane_soft",
    "04a_plane_medium_vision",
    "04b_plane_medium_gt_upperbound",
)
MONO_GATE_CONSUMER_ARMS = (
    "01_surface",
    *PHOTO_SUPPORT_CONSUMER_ARMS,
)
FORBIDDEN_GT_NUMERIC_ARRAYS = (
    "lod2_z",
    "roof_z",
    "roof_height",
    "roof_type",
    "semantic",
    "semantic_class",
    "region_ids",
    "building_ids",
    "roof_surface",
    "face_ids",
    "plane_ids",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_KEYS = {
    "schema",
    "run_id",
    "crs",
    "purpose",
    "source",
    "source_disclosure",
    "binary_mask_only",
    "forbidden_gt_numeric_arrays",
    "consumer_arms",
    "input_sha256",
    "config_sha256",
    "inventory_sha256",
    "records",
}
_RECORD_KEYS = {
    "view_id",
    "shape",
    "file",
    "mask_sha256",
    "input_sha256",
    "config_sha256",
    "geometry_sha256",
}


class MaskSchemaError(ValueError):
    """The mask artifact violates the closed pilot schema."""


class MaskSource(str, Enum):
    """Permitted mask origins with GT provenance kept explicit."""

    LOD2_GROUNDSURFACE_XY_SFM_HEIGHT = "lod2_groundsurface_xy_sfm_height"
    VISION_GROUNDEDSAM_ROOF = "vision_groundedsam_roof"
    LOD2_ROOFSURFACE_GT_UPPERBOUND = "lod2_roofsurface_gt_upperbound"
    OMNIDATA_MVS_NORMAL_ANGLE_GATE = "omnidata_mvs_normal_angle_gate"


class MaskPurpose(str, Enum):
    """Loss-side use of a mask, kept separate from where it came from."""

    PHOTO_SUPPORT = "photo_support"
    PLANE_REGION = "plane_region"
    MONO_GATE = "mono_gate"


_CONSUMER_CONTRACT = {
    (
        MaskPurpose.PHOTO_SUPPORT,
        MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
    ): PHOTO_SUPPORT_CONSUMER_ARMS,
    (
        MaskPurpose.PLANE_REGION,
        MaskSource.VISION_GROUNDEDSAM_ROOF,
    ): ("04a_plane_medium_vision",),
    (
        MaskPurpose.PLANE_REGION,
        MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND,
    ): ("04b_plane_medium_gt_upperbound",),
    (
        MaskPurpose.MONO_GATE,
        MaskSource.OMNIDATA_MVS_NORMAL_ANGLE_GATE,
    ): MONO_GATE_CONSUMER_ARMS,
}


@dataclass(frozen=True)
class MaskRecord:
    view_id: str
    shape: tuple[int, int]
    file: str
    mask_sha256: str
    input_sha256: str
    config_sha256: str
    geometry_sha256: str


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_sha256(value: Any, field: str) -> str:
    text = str(value)
    if not _SHA256_RE.fullmatch(text):
        raise MaskSchemaError(f"{field} must be a lowercase SHA-256 hex digest")
    return text


def _validate_relative_file(value: Any) -> str:
    text = str(value)
    pure = PurePosixPath(text)
    if pure.is_absolute() or ".." in pure.parts or pure.suffix != ".npz":
        raise MaskSchemaError(f"unsafe mask file path: {text!r}")
    if not pure.parts or pure.parts[0] != "masks":
        raise MaskSchemaError("mask files must live below masks/")
    return text


def _validate_mask(mask: np.ndarray, *, require_nonempty: bool = True) -> np.ndarray:
    value = np.asarray(mask)
    if value.ndim != 2:
        raise MaskSchemaError(f"binary mask must be HxW, got {value.shape}")
    if value.dtype != np.bool_:
        raise MaskSchemaError(f"binary mask dtype must be bool, got {value.dtype}")
    if value.shape[0] <= 0 or value.shape[1] <= 0:
        raise MaskSchemaError("binary mask shape must be non-empty")
    if require_nonempty and not bool(value.any()):
        raise MaskSchemaError("empty projected mask is forbidden")
    return np.ascontiguousarray(value)


def _deterministic_mask_npz(
    mask: np.ndarray, *, require_nonempty: bool = True
) -> bytes:
    """Return a deterministic ZIP containing only ``mask.npy``."""

    mask = _validate_mask(mask, require_nonempty=require_nonempty)
    npy = io.BytesIO()
    np.save(npy, mask, allow_pickle=False)
    payload = io.BytesIO()
    info = zipfile.ZipInfo("mask.npy", date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o444 << 16
    with zipfile.ZipFile(payload, mode="w") as archive:
        archive.writestr(info, npy.getvalue())
    return payload.getvalue()


def _record_payload(record: MaskRecord) -> dict[str, Any]:
    return {
        "view_id": record.view_id,
        "shape": list(record.shape),
        "file": record.file,
        "mask_sha256": record.mask_sha256,
        "input_sha256": record.input_sha256,
        "config_sha256": record.config_sha256,
        "geometry_sha256": record.geometry_sha256,
    }


def _inventory_sha256(
    records: Sequence[MaskRecord],
    purpose: MaskPurpose,
    source: MaskSource,
    consumer_arms: Sequence[str],
) -> str:
    payload = {
        "schema": SCHEMA,
        "purpose": purpose.value,
        "source": source.value,
        "consumer_arms": list(consumer_arms),
        "records": [_record_payload(record) for record in records],
    }
    return sha256_bytes(canonical_json_bytes(payload))


def _atomic_write(path: Path, payload: bytes, *, mode: int = 0o444) -> None:
    """Atomically publish one immutable file and sync file and directory data."""

    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(8)
    temporary = path.parent / f".{path.name}.{os.getpid()}.{token}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(mode)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_binary_mask_set(
    root: Path,
    masks: Mapping[str, np.ndarray],
    *,
    purpose: MaskPurpose,
    source: MaskSource,
    source_disclosure: str,
    input_sha256: str,
    config_sha256: str,
    geometry_sha256_by_view: Mapping[str, str],
) -> Path:
    """Write a closed-schema mask set into an empty directory.

    The caller owns directory lifecycle.  This function refuses a non-empty
    root so an existing mask inventory can never be silently amended.
    """

    input_sha256 = _require_sha256(input_sha256, "input_sha256")
    config_sha256 = _require_sha256(config_sha256, "config_sha256")
    if not isinstance(purpose, MaskPurpose):
        raise MaskSchemaError("purpose must be a MaskPurpose enum member")
    if not isinstance(source, MaskSource):
        raise MaskSchemaError("source must be a MaskSource enum member")
    try:
        consumer_arms = _CONSUMER_CONTRACT[(purpose, source)]
    except KeyError as exc:
        raise MaskSchemaError(
            f"unsupported purpose/source contract: {purpose.value}/{source.value}"
        ) from exc
    if not str(source_disclosure).strip():
        raise MaskSchemaError("source_disclosure must not be empty")
    if not masks:
        raise MaskSchemaError("a mask set must contain at least one view")
    if set(masks) != set(geometry_sha256_by_view):
        raise MaskSchemaError("mask and geometry-SHA view IDs must match exactly")
    root = Path(root)
    if root.is_symlink():
        raise MaskSchemaError("mask output root must not be a symlink")
    if root.exists() and any(root.iterdir()):
        raise MaskSchemaError(f"mask output directory is not empty: {root}")
    (root / "masks").mkdir(parents=True, exist_ok=True)

    allow_empty_per_view = (
        purpose is MaskPurpose.PLANE_REGION
        and source is MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND
    )
    records: list[MaskRecord] = []
    used_files: set[str] = set()
    for index, view_id in enumerate(sorted(masks), start=1):
        if not view_id or "\x00" in view_id:
            raise MaskSchemaError("view_id must be a non-empty text value")
        mask = _validate_mask(
            masks[view_id], require_nonempty=not allow_empty_per_view
        )
        geometry_sha256 = _require_sha256(
            geometry_sha256_by_view[view_id], f"geometry_sha256[{view_id}]"
        )
        safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(view_id).stem)[:80]
        view_token = sha256_bytes(view_id.encode("utf-8"))[:12]
        rel_file = f"masks/{index:06d}_{safe_stem}_{view_token}.npz"
        if rel_file in used_files:
            raise MaskSchemaError(f"mask filename collision for {view_id!r}")
        used_files.add(rel_file)
        data = _deterministic_mask_npz(
            mask, require_nonempty=not allow_empty_per_view
        )
        path = root / rel_file
        _atomic_write(path, data)
        records.append(
            MaskRecord(
                view_id=view_id,
                shape=(int(mask.shape[0]), int(mask.shape[1])),
                file=rel_file,
                mask_sha256=sha256_bytes(data),
                input_sha256=input_sha256,
                config_sha256=config_sha256,
                geometry_sha256=geometry_sha256,
            )
        )

    manifest = {
        "schema": SCHEMA,
        "run_id": RUN_ID,
        "crs": CRS,
        "purpose": purpose.value,
        "source": source.value,
        "source_disclosure": str(source_disclosure),
        "binary_mask_only": True,
        "forbidden_gt_numeric_arrays": list(FORBIDDEN_GT_NUMERIC_ARRAYS),
        "consumer_arms": list(consumer_arms),
        "input_sha256": input_sha256,
        "config_sha256": config_sha256,
        "inventory_sha256": _inventory_sha256(
            records, purpose, source, consumer_arms
        ),
        "records": [_record_payload(record) for record in records],
    }
    manifest_path = root / "mask_manifest.json"
    _atomic_write(
        manifest_path,
        (
            json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False)
            + "\n"
        ).encode("utf-8"),
    )
    return manifest_path


class BinaryMaskSet:
    """Validated, hash-checking loader for one immutable mask inventory."""

    def __init__(self, manifest_path: str | Path):
        self.manifest_path = Path(manifest_path)
        if self.manifest_path.is_symlink():
            raise MaskSchemaError("mask manifest must not be a symlink")
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MaskSchemaError(f"cannot read mask manifest: {exc}") from exc
        if not isinstance(payload, dict) or set(payload) != _MANIFEST_KEYS:
            got = set(payload) if isinstance(payload, dict) else type(payload).__name__
            raise MaskSchemaError(f"manifest must use the closed key set; got {got}")
        if payload["schema"] != SCHEMA or payload["run_id"] != RUN_ID:
            raise MaskSchemaError("unsupported mask schema or run_id")
        if payload["crs"] != CRS:
            raise MaskSchemaError(f"mask CRS must be {CRS}")
        try:
            self.purpose = MaskPurpose(payload["purpose"])
        except ValueError as exc:
            raise MaskSchemaError(f"unknown mask purpose: {payload['purpose']!r}") from exc
        try:
            self.source = MaskSource(payload["source"])
        except ValueError as exc:
            raise MaskSchemaError(f"unknown mask source: {payload['source']!r}") from exc
        if not isinstance(payload["source_disclosure"], str) or not payload[
            "source_disclosure"
        ].strip():
            raise MaskSchemaError("source disclosure is required")
        if payload["binary_mask_only"] is not True:
            raise MaskSchemaError("binary_mask_only must be true")
        if tuple(payload["forbidden_gt_numeric_arrays"]) != FORBIDDEN_GT_NUMERIC_ARRAYS:
            raise MaskSchemaError("forbidden numeric-array policy does not match the schema")
        expected_consumers = _CONSUMER_CONTRACT.get((self.purpose, self.source))
        if expected_consumers is None:
            raise MaskSchemaError(
                f"unsupported purpose/source contract: {self.purpose.value}/{self.source.value}"
            )
        if tuple(payload["consumer_arms"]) != expected_consumers:
            raise MaskSchemaError("consumer arms do not match the purpose/source contract")
        self.consumer_arms = expected_consumers
        self.input_sha256 = _require_sha256(payload["input_sha256"], "input_sha256")
        self.config_sha256 = _require_sha256(payload["config_sha256"], "config_sha256")
        expected_inventory = _require_sha256(
            payload["inventory_sha256"], "inventory_sha256"
        )

        raw_records = payload["records"]
        if not isinstance(raw_records, list) or not raw_records:
            raise MaskSchemaError("records must be a non-empty list")
        records: list[MaskRecord] = []
        seen_ids: set[str] = set()
        seen_files: set[str] = set()
        for raw in raw_records:
            if not isinstance(raw, dict) or set(raw) != _RECORD_KEYS:
                raise MaskSchemaError("mask record must use the closed key set")
            view_id = raw["view_id"]
            if not isinstance(view_id, str) or not view_id or view_id in seen_ids:
                raise MaskSchemaError(f"invalid or duplicate view_id: {view_id!r}")
            shape = raw["shape"]
            if (
                not isinstance(shape, list)
                or len(shape) != 2
                or any(type(value) is not int or value <= 0 for value in shape)
            ):
                raise MaskSchemaError(f"invalid mask shape for {view_id!r}")
            rel_file = _validate_relative_file(raw["file"])
            if rel_file in seen_files:
                raise MaskSchemaError(f"duplicate mask file: {rel_file}")
            record = MaskRecord(
                view_id=view_id,
                shape=(shape[0], shape[1]),
                file=rel_file,
                mask_sha256=_require_sha256(raw["mask_sha256"], "mask_sha256"),
                input_sha256=_require_sha256(raw["input_sha256"], "record.input_sha256"),
                config_sha256=_require_sha256(raw["config_sha256"], "record.config_sha256"),
                geometry_sha256=_require_sha256(
                    raw["geometry_sha256"], "record.geometry_sha256"
                ),
            )
            if (
                record.input_sha256 != self.input_sha256
                or record.config_sha256 != self.config_sha256
            ):
                raise MaskSchemaError("record provenance hashes must match the common hashes")
            records.append(record)
            seen_ids.add(view_id)
            seen_files.add(rel_file)
        if [record.view_id for record in records] != sorted(seen_ids):
            raise MaskSchemaError("records must be ordered lexically by view_id")
        if (
            _inventory_sha256(
                records, self.purpose, self.source, self.consumer_arms
            )
            != expected_inventory
        ):
            raise MaskSchemaError("common arm inventory SHA mismatch")
        self.inventory_sha256 = expected_inventory
        self.records = {record.view_id: record for record in records}

    def load(self, view_id: str) -> np.ndarray:
        """Load and verify one bool HxW mask, rejecting every side-channel array."""

        try:
            record = self.records[view_id]
        except KeyError as exc:
            raise MaskSchemaError(f"view is not present in mask inventory: {view_id}") from exc
        path = self.manifest_path.parent / record.file
        base = self.manifest_path.parent.resolve()
        cursor = path
        while cursor != self.manifest_path.parent:
            if cursor.is_symlink():
                raise MaskSchemaError(
                    f"mask path and its parents must not be symlinks: {record.file}"
                )
            cursor = cursor.parent
        try:
            path.resolve(strict=True).relative_to(base)
        except (FileNotFoundError, ValueError) as exc:
            raise MaskSchemaError(f"mask path escapes or is missing: {record.file}") from exc
        if sha256_file(path) != record.mask_sha256:
            raise MaskSchemaError(f"mask SHA mismatch: {record.file}")
        try:
            with np.load(path, allow_pickle=False) as archive:
                keys = tuple(archive.files)
                if keys != ("mask",):
                    forbidden = sorted(set(keys) - {"mask"})
                    raise MaskSchemaError(
                        "mask archive must contain exactly bool array 'mask'; "
                        f"extra numeric arrays rejected: {forbidden}"
                    )
                mask = np.array(archive["mask"], copy=True)
        except MaskSchemaError:
            raise
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            raise MaskSchemaError(f"cannot read mask archive {record.file}: {exc}") from exc
        allow_empty_per_view = (
            self.purpose is MaskPurpose.PLANE_REGION
            and self.source is MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND
        )
        mask = _validate_mask(mask, require_nonempty=not allow_empty_per_view)
        if tuple(mask.shape) != record.shape:
            raise MaskSchemaError(
                f"mask shape mismatch for {view_id}: {mask.shape} != {record.shape}"
            )
        return mask


def masked_l1(
    prediction: torch.Tensor,
    target: torch.Tensor,
    mask: torch.Tensor,
) -> torch.Tensor:
    """Standalone exact masked L1 for HxW or HxWxC tensors.

    The denominator counts selected scalar elements.  Therefore changing any
    value outside ``mask`` cannot change either the numerator or denominator.
    Empty masks are an error rather than a silent graph-connected zero.
    """

    if prediction.shape != target.shape:
        raise ValueError("prediction and target must have the same shape")
    if prediction.ndim not in (2, 3):
        raise ValueError("masked_l1 expects HxW or HxWxC tensors")
    if mask.dtype != torch.bool or mask.ndim != 2:
        raise ValueError("mask must be a bool HxW tensor")
    if tuple(mask.shape) != tuple(prediction.shape[:2]):
        raise ValueError("mask HxW must match prediction spatial shape")
    selected = mask if prediction.ndim == 2 else mask[..., None].expand_as(prediction)
    if not bool(selected.any().item()):
        raise ValueError("masked_l1 forbids an empty mask")
    return (prediction - target).abs()[selected].mean()

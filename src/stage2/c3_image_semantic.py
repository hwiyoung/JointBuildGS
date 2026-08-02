"""Pinned, image-only semantic labels for the exact 937-image C3 source set.

This producer deliberately exposes no pose, footprint, building identity, LiDAR,
LoD1, LoD2, or UAS interface. Heavy model loading happens only when ``produce``
is explicitly called with the already verified offline asset cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import ctypes
import errno
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import tempfile
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from PIL import Image as PILImage

from src.text_identity import CanonicalTextError, canonical_lf_bytes

from .pilot_plane_mask_producer import (
    GroundedSamRoofInference,
    MaskProducerError,
    canonical_json_bytes,
    sha256_file,
)
from .c3_image_semantic_assets import (
    EXPECTED_ASSETS,
    RECEIPT_SCHEMA as ASSET_RECEIPT_SCHEMA,
    audit_c3_runtime,
    load_c3_contract,
    verify_c3_asset_receipt,
)
from .colmap_io import CAMERA_MODEL_IDS


REPO = Path(__file__).resolve().parents[2]
CANONICAL_CROSSWALK = (
    REPO / "artifacts/manifests/gate_s0/common_base_r2b/exact_937_member_crosswalk_v1.json"
)
CROSSWALK_BYTES = 378466
CROSSWALK_SHA256 = "b4af779ecfae859de9772ce50cb24326b20c3f86614f6a8957453779d1cd4c17"
SEMANTIC_CONTRACT = REPO / "configs/c3_first_wave_v2/c3_image_semantic_producer_v1.json"
SEMANTIC_CONTRACT_BYTES = 3451
SEMANTIC_CONTRACT_SHA256 = "61eb4cecab6b2e998576aca21bef676394c922a40eaee522421f0c3e827bcf3d"
INPUT_SCHEMA = "jointbuildgs.c3_image_semantic_membership_manifest.v2"
FINAL_SCHEMA = "jointbuildgs.c3_image_semantic_output_manifest.v2"
COMPLETION_SCHEMA = "jointbuildgs.c3_image_semantic_completion.v2"
WORK_NAMESPACE_SCHEMA = "jointbuildgs.c3_image_semantic_work_namespace.v2"
WORK_NAMESPACE_ID = "EXACT_937_COLMAP_UNDISTORTED_R2"
SOURCE_ROLE = "EXACT_937_COLMAP_UNDISTORTED_TRAINING_RGB"
PROMPTS: dict[int, tuple[str, ...]] = {
    1: ("roof",),
    2: ("facade", "wall"),
    3: ("ground", "road", "pavement"),
}
CLASS_NAMES = {0: "unknown", 1: "roof", 2: "facade_or_wall", 3: "ground_road_or_pavement"}
BOX_THRESHOLD = 0.30
TEXT_THRESHOLD = 0.25
NMS_IOU = 0.80


class C3SemanticError(RuntimeError):
    """A C3 image-only semantic contract failed closed."""


@dataclass(frozen=True)
class SemanticCandidate:
    class_id: int
    prompt: str
    phrase: str
    score: float
    box_xyxy: tuple[float, float, float, float]
    mask: np.ndarray


@dataclass(frozen=True)
class SemanticResult:
    labels: np.ndarray
    candidates: tuple[SemanticCandidate, ...]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bound_text(path: Path, role: str) -> bytes:
    try:
        return canonical_lf_bytes(path.read_bytes())
    except CanonicalTextError as error:
        raise C3SemanticError(f"{role} contains a lone carriage return") from error


def resolve_semantic_pixels(
    shape: tuple[int, int], candidates: Sequence[SemanticCandidate]
) -> np.ndarray:
    """Highest DINO score wins; exact score ties select the lower class ID."""

    labels = np.zeros(shape, dtype=np.uint8)
    scores = np.full(shape, -np.inf, dtype=np.float64)
    owners = np.full(shape, 255, dtype=np.uint8)
    for candidate in candidates:
        if candidate.class_id not in PROMPTS or not math.isfinite(candidate.score):
            raise C3SemanticError("semantic candidate class or score is invalid")
        mask = np.asarray(candidate.mask)
        if mask.shape != shape or mask.dtype != np.bool_:
            raise C3SemanticError("SAM instance mask must be bool HxW")
        update = mask & (
            (float(candidate.score) > scores)
            | ((float(candidate.score) == scores) & (candidate.class_id < owners))
        )
        labels[update] = candidate.class_id
        scores[update] = float(candidate.score)
        owners[update] = candidate.class_id
    return np.ascontiguousarray(labels)


class GroundedSamImageSemanticInference(GroundedSamRoofInference):
    """Multi-class subclass that reuses only the byte-compatible pinned loader."""

    def __call__(self, rgb: np.ndarray) -> SemanticResult:
        self._load()
        image = np.asarray(rgb)
        if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
            raise MaskProducerError("C3 semantic input must be uint8 RGB HxWx3")
        height, width = image.shape[:2]
        pil = PILImage.fromarray(image, mode="RGB")
        tensor, _ = self._transform(pil, None)
        pending: list[dict[str, Any]] = []
        for class_id in sorted(PROMPTS):
            class_rows: list[dict[str, Any]] = []
            for prompt in PROMPTS[class_id]:
                caption = f"{prompt}."
                with self._torch.no_grad():
                    output = self._model(tensor[None].to(self.device), captions=[caption])
                logits = output["pred_logits"].sigmoid()[0].detach().cpu()
                boxes = output["pred_boxes"][0].detach().cpu()
                keep = logits.max(dim=1).values > BOX_THRESHOLD
                logits, boxes = logits[keep], boxes[keep]
                if len(boxes) == 0:
                    continue
                scores = logits.max(dim=1).values
                tokenized = self._model.tokenizer(caption)
                phrases = tuple(
                    self._get_phrases(logit > TEXT_THRESHOLD, tokenized, self._model.tokenizer)
                    for logit in logits
                )
                cx, cy, bw, bh = boxes.unbind(dim=1)
                xyxy = self._torch.stack(
                    [cx - bw / 2.0, cy - bh / 2.0, cx + bw / 2.0, cy + bh / 2.0],
                    dim=1,
                )
                xyxy *= self._torch.tensor([width, height, width, height], dtype=xyxy.dtype)
                for index in range(len(xyxy)):
                    class_rows.append(
                        {
                            "class_id": class_id,
                            "prompt": prompt,
                            "phrase": phrases[index],
                            "score": scores[index],
                            "box": xyxy[index],
                        }
                    )
            if class_rows:
                class_boxes = self._torch.stack([row["box"] for row in class_rows])
                class_scores = self._torch.stack([row["score"] for row in class_rows])
                keep_indices = self._nms(class_boxes, class_scores, NMS_IOU).tolist()
                pending.extend(class_rows[int(index)] for index in keep_indices)
        if not pending:
            return SemanticResult(np.zeros((height, width), dtype=np.uint8), ())
        boxes = self._torch.stack([row["box"] for row in pending])
        self._predictor.set_image(image, image_format="RGB")
        transformed = self._predictor.transform.apply_boxes_torch(
            boxes.to(self.device), image.shape[:2]
        )
        with self._torch.no_grad():
            masks, _, _ = self._predictor.predict_torch(
                point_coords=None,
                point_labels=None,
                boxes=transformed,
                multimask_output=False,
            )
        mask_array = masks[:, 0].detach().cpu().numpy().astype(bool)
        candidates = tuple(
            SemanticCandidate(
                class_id=int(row["class_id"]),
                prompt=str(row["prompt"]),
                phrase=str(row["phrase"]),
                score=float(row["score"]),
                box_xyxy=tuple(float(value) for value in row["box"].tolist()),
                mask=np.ascontiguousarray(mask_array[index]),
            )
            for index, row in enumerate(pending)
        )
        return SemanticResult(resolve_semantic_pixels((height, width), candidates), candidates)


def canonical_membership_rows(
    crosswalk_path: Path = CANONICAL_CROSSWALK,
) -> list[dict[str, Any]]:
    """Return membership only; do not open RGB, COLMAP binaries, or depth payloads."""

    data = _canonical_bound_text(crosswalk_path, "exact-937 crosswalk")
    if len(data) != CROSSWALK_BYTES or sha256_bytes(data) != CROSSWALK_SHA256:
        raise C3SemanticError("exact-937 crosswalk identity differs")
    value = json.loads(data)
    if not isinstance(value, Mapping):
        raise C3SemanticError("exact-937 crosswalk must be an object")
    rows = value.get("rows")
    if value.get("schema") != "jointbuildgs.gate_s0_exact_937_member_crosswalk.v1" or not isinstance(rows, list):
        raise C3SemanticError("exact-937 crosswalk schema differs")
    names = [row.get("basename") for row in rows]
    if len(names) != 937 or len(set(names)) != 937 or any(not isinstance(name, str) for name in names):
        raise C3SemanticError("exact-937 crosswalk membership differs")
    result: list[dict[str, Any]] = []
    for row in rows:
        if (
            type(row.get("colmap_image_id")) is not int
            or row["colmap_image_id"] <= 0
            or type(row.get("colmap_camera_model_id")) is not int
            or row["colmap_camera_model_id"] not in CAMERA_MODEL_IDS
            or row.get("geometric_depth") is not True
        ):
            raise C3SemanticError("exact-937 crosswalk COLMAP/depth membership differs")
        name = row["basename"]
        result.append(
            {
                "name": name,
                "relative_path": name,
                "colmap_image_id": row["colmap_image_id"],
                "colmap_camera_model_id": row["colmap_camera_model_id"],
                "geometric_depth_relative_path": f"{name}.geometric.bin",
            }
        )
    if len({row["colmap_image_id"] for row in result}) != 937:
        raise C3SemanticError("exact-937 crosswalk COLMAP image IDs are duplicated")
    return result


def canonical_image_names(crosswalk_path: Path = CANONICAL_CROSSWALK) -> list[str]:
    return [row["name"] for row in canonical_membership_rows(crosswalk_path)]


def _safe_relative(value: Any) -> PurePosixPath:
    if not isinstance(value, str):
        raise C3SemanticError("image relative_path must be a string")
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise C3SemanticError("image relative_path is unsafe")
    return path


def load_input_manifest(path: Path, expected_names: Sequence[str] | None = None) -> tuple[list[dict[str, Any]], str]:
    data = path.read_bytes()
    value = json.loads(data)
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "source_role",
        "images",
        "scientific_verdict",
    }:
        raise C3SemanticError("input manifest exposes fields outside the image-only contract")
    if (
        value["schema"] != INPUT_SCHEMA
        or value["source_role"] != SOURCE_ROLE
        or value["scientific_verdict"] is not None
    ):
        raise C3SemanticError("input manifest schema or scientific_verdict differs")
    rows = value["images"]
    if not isinstance(rows, list):
        raise C3SemanticError("input manifest images must be an array")
    canonical_rows = canonical_membership_rows() if expected_names is None else None
    expected = list(
        [row["name"] for row in canonical_rows]
        if canonical_rows is not None
        else expected_names or ()
    )
    if len(expected) != len(set(expected)):
        raise C3SemanticError("expected image names are duplicated")
    observed: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "name",
            "relative_path",
            "colmap_image_id",
            "colmap_camera_model_id",
            "geometric_depth_relative_path",
        }:
            raise C3SemanticError("input image row is not membership-only")
        relative = _safe_relative(row["relative_path"])
        depth_relative = _safe_relative(row["geometric_depth_relative_path"])
        if (
            not isinstance(row["name"], str)
            or relative.name != row["name"]
            or depth_relative.name != f"{row['name']}.geometric.bin"
            or type(row["colmap_image_id"]) is not int
            or row["colmap_image_id"] <= 0
            or type(row["colmap_camera_model_id"]) is not int
            or row["colmap_camera_model_id"] not in CAMERA_MODEL_IDS
        ):
            raise C3SemanticError("input membership name/path/COLMAP contract differs")
        observed.append(row["name"])
    if observed != expected:
        raise C3SemanticError("input manifest does not equal the exact ordered RGB-name set")
    if canonical_rows is not None and rows != canonical_rows:
        raise C3SemanticError("input manifest does not equal the canonical COLMAP membership")
    if len({row["colmap_image_id"] for row in rows}) != len(rows):
        raise C3SemanticError("input manifest COLMAP image IDs are duplicated")
    return rows, sha256_bytes(data)


def build_input_manifest(output_path: Path) -> dict[str, Any]:
    """Build exact-937 membership without opening any RGB or derivative payload."""

    if output_path.exists():
        raise C3SemanticError("semantic input manifest is add-once and already exists")
    rows = canonical_membership_rows()
    value = {
        "schema": INPUT_SCHEMA,
        "source_role": SOURCE_ROLE,
        "images": rows,
        "scientific_verdict": None,
    }
    payload = canonical_json_bytes(value)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=output_path.parent, prefix=f".{output_path.name}.", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    _publish_file_noreplace(temporary, output_path)
    return {
        "path": str(output_path),
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "image_count": len(rows),
        "rgb_pre_reads": 0,
        "colmap_binary_pre_reads": 0,
        "depth_pre_reads": 0,
        "images_zip_reads_or_hashes": 0,
        "scientific_verdict": None,
    }


def _require_regular_file(path: Path, role: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise C3SemanticError(f"{role} must be a regular non-symlink file")


def _read_exact(handle: Any, size: int, role: str) -> bytes:
    value = handle.read(size)
    if len(value) != size:
        raise C3SemanticError(f"{role} is truncated")
    return value


def _load_colmap_semantic_bindings(
    cameras_bin: Path,
    images_bin: Path,
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    """Read camera/name bindings while skipping pose bytes without decoding them."""

    _require_regular_file(cameras_bin, "COLMAP cameras.bin")
    _require_regular_file(images_bin, "COLMAP images.bin")
    cameras: dict[int, dict[str, Any]] = {}
    with cameras_bin.open("rb") as handle:
        count = struct.unpack("<Q", _read_exact(handle, 8, "COLMAP cameras.bin"))[0]
        for _ in range(count):
            camera_id, model_id, width, height = struct.unpack(
                "<iiQQ", _read_exact(handle, 24, "COLMAP cameras.bin")
            )
            if model_id not in CAMERA_MODEL_IDS or camera_id in cameras:
                raise C3SemanticError("COLMAP camera model or ID differs")
            model, parameter_count = CAMERA_MODEL_IDS[model_id]
            _read_exact(handle, 8 * parameter_count, "COLMAP cameras.bin")
            if width <= 0 or height <= 0:
                raise C3SemanticError("COLMAP camera dimensions are invalid")
            cameras[camera_id] = {
                "camera_id": camera_id,
                "camera_model_id": model_id,
                "camera_model": model,
                "width": width,
                "height": height,
                "pose_values_decoded": 0,
                "pose_values_exposed_to_inference": 0,
            }
        if handle.read(1):
            raise C3SemanticError("COLMAP cameras.bin has unexpected trailing bytes")
    images: dict[int, dict[str, Any]] = {}
    names: set[str] = set()
    with images_bin.open("rb") as handle:
        file_size = os.fstat(handle.fileno()).st_size
        count = struct.unpack("<Q", _read_exact(handle, 8, "COLMAP images.bin"))[0]
        for _ in range(count):
            image_id = struct.unpack("<I", _read_exact(handle, 4, "COLMAP images.bin"))[0]
            if 56 > file_size - handle.tell():
                raise C3SemanticError("COLMAP images.bin pose region is truncated")
            handle.seek(56, os.SEEK_CUR)
            camera_id = struct.unpack("<I", _read_exact(handle, 4, "COLMAP images.bin"))[0]
            encoded_name = bytearray()
            while True:
                character = _read_exact(handle, 1, "COLMAP images.bin image name")
                if character == b"\x00":
                    break
                encoded_name.extend(character)
                if len(encoded_name) > 4096:
                    raise C3SemanticError("COLMAP image name is unreasonably long")
            try:
                name = encoded_name.decode("utf-8")
            except UnicodeDecodeError as error:
                raise C3SemanticError("COLMAP image name is not UTF-8") from error
            point_count = struct.unpack(
                "<Q", _read_exact(handle, 8, "COLMAP images.bin")
            )[0]
            skip_bytes = 24 * point_count
            if skip_bytes > file_size - handle.tell():
                raise C3SemanticError("COLMAP images.bin POINTS2D payload is truncated")
            handle.seek(skip_bytes, os.SEEK_CUR)
            if image_id in images or name in names or camera_id not in cameras:
                raise C3SemanticError("COLMAP image ID/name/camera binding differs")
            images[image_id] = {"image_id": image_id, "camera_id": camera_id, "name": name}
            names.add(name)
        if handle.tell() != file_size:
            raise C3SemanticError("COLMAP images.bin has unexpected trailing bytes")
    return cameras, images


def _expected_colmap_binding(
    row: Mapping[str, Any],
    cameras: Mapping[int, Mapping[str, Any]],
    images: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    image = images.get(row["colmap_image_id"])
    if not isinstance(image, Mapping) or image.get("name") != row["name"]:
        raise C3SemanticError("membership row does not match COLMAP images.bin")
    camera = cameras.get(image["camera_id"])
    if (
        not isinstance(camera, Mapping)
        or camera.get("camera_model_id") != row["colmap_camera_model_id"]
    ):
        raise C3SemanticError("membership row does not match COLMAP cameras.bin")
    return {"image_id": row["colmap_image_id"], **dict(camera)}


def _read_colmap_depth_shape(path: Path, relative_path: str) -> dict[str, Any]:
    """Read only the COLMAP array header and bind its exact payload length."""

    _require_regular_file(path, "COLMAP geometric depth")
    with path.open("rb") as handle:
        header = bytearray()
        while header.count(b"&") < 3:
            header.extend(_read_exact(handle, 1, "COLMAP geometric depth header"))
            if len(header) > 128:
                raise C3SemanticError("COLMAP geometric depth header is invalid")
        try:
            fields = header.decode("ascii").rstrip("&").split("&")
            width, height, channels = (int(value) for value in fields)
        except (UnicodeDecodeError, ValueError) as error:
            raise C3SemanticError("COLMAP geometric depth header is invalid") from error
        size = os.fstat(handle.fileno()).st_size
        expected_size = len(header) + width * height * channels * 4
    if width <= 0 or height <= 0 or channels != 1 or size != expected_size:
        raise C3SemanticError("COLMAP geometric depth shape or byte length differs")
    return {
        "relative_path": relative_path,
        "bytes": size,
        "width": width,
        "height": height,
        "channels": channels,
        "shape_matches_rgb": True,
    }


def _read_undistorted_rgb_once(path: Path, relative_path: str) -> tuple[np.ndarray, dict[str, Any]]:
    """Natural inference read: digest and decode the same byte stream exactly once."""

    _require_regular_file(path, "COLMAP undistorted RGB")
    source = path.read_bytes()
    try:
        with PILImage.open(BytesIO(source)) as image:
            rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    except (OSError, ValueError) as error:
        raise C3SemanticError("COLMAP undistorted RGB cannot be decoded") from error
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise C3SemanticError("COLMAP undistorted RGB decode differs")
    return rgb, {
        "role": SOURCE_ROLE,
        "relative_path": relative_path,
        "bytes": len(source),
        "sha256": sha256_bytes(source),
        "width": int(rgb.shape[1]),
        "height": int(rgb.shape[0]),
        "decoded_mode": "RGB",
        "natural_read_count": 1,
        "standalone_rehash_count": 0,
        "resize_count": 0,
    }


def _load_semantic_producer_contract() -> dict[str, Any]:
    contract_data = _canonical_bound_text(SEMANTIC_CONTRACT, "C3 semantic producer contract")
    if (
        len(contract_data) != SEMANTIC_CONTRACT_BYTES
        or sha256_bytes(contract_data) != SEMANTIC_CONTRACT_SHA256
    ):
        raise C3SemanticError("C3 semantic producer contract identity differs")
    value = json.loads(contract_data)
    if (
        not isinstance(value, dict)
        or value.get("schema") != "jointbuildgs.c3_image_semantic_producer.v2"
        or value.get("scientific_verdict") is not None
        or not isinstance(value.get("input"), dict)
        or not isinstance(value["input"].get("runtime_paths"), dict)
    ):
        raise C3SemanticError("C3 semantic producer contract schema differs")
    return value


def _bind_semantic_runtime_paths(
    contract: Mapping[str, Any],
    *,
    image_root: Path,
    cameras_bin: Path,
    images_bin: Path,
    geometric_depth_root: Path,
    input_manifest: Path,
    work_dir: Path,
    output_dir: Path,
    test_only_allow_unbound_paths: bool,
    expected_names: Sequence[str] | None,
) -> None:
    if test_only_allow_unbound_paths:
        if expected_names is None:
            raise C3SemanticError("test-only unbound paths require an explicit synthetic roster")
        return
    configured = contract["input"]["runtime_paths"]
    actual = {
        "colmap_undistorted_rgb_root": image_root,
        "cameras_bin": cameras_bin,
        "images_bin": images_bin,
        "geometric_depth_root": geometric_depth_root,
        "membership_manifest": input_manifest,
        "work_dir": work_dir,
        "output_dir": output_dir,
    }
    if set(configured) != set(actual) or any(
        not isinstance(configured[key], str)
        or Path(configured[key]).resolve(strict=False) != path.resolve(strict=False)
        for key, path in actual.items()
    ):
        raise C3SemanticError("runtime paths differ from the exact semantic producer contract")


def _runtime_pins(
    lock_path: Path,
    receipt_path: Path,
    lock: Mapping[str, Any],
    producer_contract: Mapping[str, Any],
) -> dict[str, Any]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    artifacts = receipt.get("artifacts", {})
    if (
        receipt.get("schema") != ASSET_RECEIPT_SCHEMA
        or receipt.get("contract_sha256") != sha256_file(lock_path)
        or not isinstance(artifacts, dict)
        or tuple(artifacts) != EXPECTED_ASSETS
        or receipt.get("scientific_verdict") is not None
    ):
        raise C3SemanticError("C3 asset receipt metadata differs from the C3-only contract")
    return {
        "c3_semantic_contract": {
            "path": str(SEMANTIC_CONTRACT.relative_to(REPO)).replace("\\", "/"),
            "bytes": SEMANTIC_CONTRACT_BYTES,
            "sha256": SEMANTIC_CONTRACT_SHA256,
        },
        "producer_lock": {"path": str(lock_path), "sha256": sha256_file(lock_path)},
        "asset_receipt": {"path": str(receipt_path), "sha256": sha256_file(receipt_path)},
        "runtime_environment": lock["runtime_environment"],
        "sources": {
            key: lock["runtime_assets"][key]["revision"]
            for key in ("groundingdino_source", "segment_anything_source", "bert_base_uncased")
        },
        "verified_asset_identities": {
            key: {
                "kind": artifacts[key]["kind"],
                "size_bytes": artifacts[key]["size_bytes"],
                "sha256": artifacts[key]["sha256"],
            }
            for key in (
                "groundingdino_source",
                "segment_anything_source",
                "groundingdino_swint_ogc",
                "sam_vit_h",
                "bert_base_uncased",
            )
        },
        "weights": {
            key: {"size_bytes": artifacts[key]["size_bytes"], "sha256": artifacts[key]["sha256"]}
            for key in ("groundingdino_swint_ogc", "sam_vit_h")
        },
        "semantic_contract": {
            "classes": CLASS_NAMES,
            "prompts": PROMPTS,
            "box_threshold_strict_gt": BOX_THRESHOLD,
            "text_threshold_strict_gt": TEXT_THRESHOLD,
            "nms_iou": NMS_IOU,
            "nms_scope": "PER_CLASS_AFTER_ALL_CLASS_SYNONYM_PROMPTS",
            "overlap_rule": "HIGHEST_DINO_SCORE_EXACT_TIE_LOWER_CLASS_ID",
            "sam_masks": "PER_INSTANCE_MULTIMASK_FALSE",
        },
        "input_contract": {
            "role": producer_contract["input"]["role"],
            "runtime_paths": producer_contract["input"]["runtime_paths"],
            "work_namespace": producer_contract["resume"]["work_namespace"],
        },
    }


def _completion_name(index: int, name: str) -> str:
    return f"{index:04d}_{sha256_bytes(name.encode('utf-8'))[:16]}"


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
    except ValueError:
        return False
    return True


def _png_bytes(labels: np.ndarray) -> bytes:
    if labels.dtype != np.uint8 or labels.ndim != 2 or np.any(labels > 3):
        raise C3SemanticError("semantic output must be uint8 HxW with values 0..3")
    stream = BytesIO()
    PILImage.fromarray(labels, mode="L").save(stream, format="PNG", optimize=False, compress_level=9)
    return stream.getvalue()


def _validate_completion(
    directory: Path,
    index: int,
    row: Mapping[str, Any],
    expected_colmap: Mapping[str, Any],
    pins_sha256: str,
) -> dict[str, Any]:
    receipt_path, mask_path = directory / "receipt.json", directory / "mask.png"
    if (
        directory.is_symlink()
        or not directory.is_dir()
        or {path.name for path in directory.iterdir()} != {"receipt.json", "mask.png"}
        or receipt_path.is_symlink()
        or mask_path.is_symlink()
        or not receipt_path.is_file()
        or not mask_path.is_file()
    ):
        raise C3SemanticError("completed image directory is incomplete or symlinked")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        not isinstance(receipt, dict)
        or set(receipt)
        != {
            "schema",
            "index",
            "membership",
            "source_rgb",
            "colmap_camera",
            "geometric_depth",
            "output",
            "candidate_count",
            "runtime_pins_sha256",
            "scientific_verdict",
        }
        or receipt.get("schema") != COMPLETION_SCHEMA
        or receipt.get("index") != index
        or receipt.get("membership") != dict(row)
        or receipt.get("colmap_camera") != dict(expected_colmap)
        or receipt.get("runtime_pins_sha256") != pins_sha256
        or type(receipt.get("candidate_count")) is not int
        or receipt["candidate_count"] < 0
        or receipt.get("scientific_verdict") is not None
    ):
        raise C3SemanticError("completed image receipt differs from the exact run contract")
    source_rgb = receipt.get("source_rgb")
    if (
        not isinstance(source_rgb, dict)
        or set(source_rgb)
        != {
            "role",
            "relative_path",
            "bytes",
            "sha256",
            "width",
            "height",
            "decoded_mode",
            "natural_read_count",
            "standalone_rehash_count",
            "resize_count",
        }
        or source_rgb.get("role") != SOURCE_ROLE
        or source_rgb.get("relative_path") != row["relative_path"]
        or type(source_rgb.get("bytes")) is not int
        or source_rgb["bytes"] <= 0
        or not isinstance(source_rgb.get("sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", source_rgb["sha256"]) is None
        or source_rgb.get("width") != expected_colmap["width"]
        or source_rgb.get("height") != expected_colmap["height"]
        or source_rgb.get("decoded_mode") != "RGB"
        or source_rgb.get("natural_read_count") != 1
        or source_rgb.get("standalone_rehash_count") != 0
        or source_rgb.get("resize_count") != 0
    ):
        raise C3SemanticError("completed undistorted RGB ledger differs")
    depth = receipt.get("geometric_depth")
    if (
        not isinstance(depth, dict)
        or set(depth)
        != {
            "relative_path",
            "bytes",
            "width",
            "height",
            "channels",
            "shape_matches_rgb",
        }
        or depth.get("relative_path") != row["geometric_depth_relative_path"]
        or type(depth.get("bytes")) is not int
        or depth["bytes"] <= 0
        or depth.get("width") != expected_colmap["width"]
        or depth.get("height") != expected_colmap["height"]
        or depth.get("channels") != 1
        or depth.get("shape_matches_rgb") is not True
    ):
        raise C3SemanticError("completed geometric-depth shape binding differs")
    mask = mask_path.read_bytes()
    output = receipt.get("output")
    if (
        not isinstance(output, dict)
        or set(output)
        != {
            "bytes",
            "sha256",
            "width",
            "height",
            "dtype",
            "class_pixel_counts",
        }
        or type(output.get("bytes")) is not int
        or output["bytes"] <= 0
        or not isinstance(output.get("sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", output["sha256"]) is None
        or type(output.get("width")) is not int
        or output["width"] <= 0
        or type(output.get("height")) is not int
        or output["height"] <= 0
        or output["width"] != source_rgb["width"]
        or output["height"] != source_rgb["height"]
        or output.get("dtype") != "uint8"
        or not isinstance(output.get("class_pixel_counts"), dict)
        or set(output["class_pixel_counts"]) != {"0", "1", "2", "3"}
        or any(
            type(value) is not int or value < 0
            for value in output["class_pixel_counts"].values()
        )
        or sum(output["class_pixel_counts"].values())
        != output["width"] * output["height"]
        or len(mask) != output["bytes"]
        or sha256_bytes(mask) != output["sha256"]
    ):
        raise C3SemanticError("completed semantic PNG identity differs")
    with PILImage.open(BytesIO(mask)) as image:
        labels = np.asarray(image).copy()
    if labels.dtype != np.uint8 or labels.ndim != 2 or np.any(labels > 3):
        raise C3SemanticError("completed semantic PNG content differs")
    if labels.shape != (output["height"], output["width"]):
        raise C3SemanticError("completed semantic PNG dimensions differ")
    observed_counts = {
        str(class_id): int(np.count_nonzero(labels == class_id))
        for class_id in range(4)
    }
    if observed_counts != output["class_pixel_counts"]:
        raise C3SemanticError("completed semantic PNG class counts differ")
    return receipt


def _publish_file_noreplace(staging: Path, target: Path) -> None:
    """Atomically publish a complete file without replacing any existing name."""

    try:
        os.link(staging, target)
    except FileExistsError as exc:
        raise C3SemanticError(f"add-once target already exists: {target}") from exc
    finally:
        if staging.exists():
            staging.unlink()


def _bind_work_namespace(work_dir: Path) -> None:
    """Reject legacy/raw completion trees before creating the R2 namespace."""

    if work_dir.is_symlink() or (work_dir.exists() and not work_dir.is_dir()):
        raise C3SemanticError("semantic work directory must be a real directory")
    work_dir.mkdir(parents=True, exist_ok=True)
    marker = work_dir / "namespace.json"
    expected = {
        "schema": WORK_NAMESPACE_SCHEMA,
        "namespace_id": WORK_NAMESPACE_ID,
        "source_role": SOURCE_ROLE,
        "legacy_raw_completion_reuse_allowed": False,
        "resize_legacy_completion_allowed": False,
        "scientific_verdict": None,
    }
    if marker.exists():
        _require_regular_file(marker, "semantic work namespace marker")
        if json.loads(marker.read_text(encoding="utf-8")) != expected:
            raise C3SemanticError("semantic work namespace marker differs")
        return
    if any(work_dir.iterdir()):
        raise C3SemanticError("legacy or unbound semantic work directory cannot be reused")
    payload = canonical_json_bytes(expected)
    with tempfile.NamedTemporaryFile(
        dir=work_dir, prefix=".namespace.json.", delete=False
    ) as handle:
        staging = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    _publish_file_noreplace(staging, marker)


def _publish_directory_noreplace(staging: Path, target: Path) -> None:
    """Linux atomic directory publication using renameat2(RENAME_NOREPLACE)."""

    if os.name != "posix":
        raise C3SemanticError("atomic no-clobber directory publication requires POSIX")
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise C3SemanticError("renameat2 is unavailable; refusing non-atomic publication")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        -100,
        os.fsencode(staging),
        -100,
        os.fsencode(target),
        1,
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error in (errno.EEXIST, errno.ENOTEMPTY):
        raise C3SemanticError(f"add-once target appeared during publication: {target}")
    raise C3SemanticError(
        f"atomic no-clobber publication failed for {target}: {os.strerror(error)}"
    )


AssetVerifier = Callable[[Mapping[str, Any], Path, Path, Path], dict[str, Path]]
InferenceFactory = Callable[[Mapping[str, Any], Mapping[str, Path], str], Any]
RuntimeVerifier = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def produce(
    *,
    image_root: Path,
    cameras_bin: Path,
    images_bin: Path,
    geometric_depth_root: Path,
    input_manifest: Path,
    lock_path: Path,
    asset_root: Path,
    asset_receipt: Path,
    work_dir: Path,
    output_dir: Path,
    device: str = "cuda",
    expected_names: Sequence[str] | None = None,
    test_only_allow_unbound_paths: bool = False,
    asset_verifier: AssetVerifier = verify_c3_asset_receipt,
    runtime_verifier: RuntimeVerifier = audit_c3_runtime,
    inference_factory: InferenceFactory | None = None,
) -> dict[str, Any]:
    """Resume exact completed images and atomically publish only after all finish."""

    if output_dir.exists():
        raise C3SemanticError("final semantic output directory is add-once and already exists")
    if image_root.is_symlink() or not image_root.is_dir():
        raise C3SemanticError("image root must be a real directory")
    if geometric_depth_root.is_symlink() or not geometric_depth_root.is_dir():
        raise C3SemanticError("geometric depth root must be a real directory")
    _require_regular_file(cameras_bin, "COLMAP cameras.bin")
    _require_regular_file(images_bin, "COLMAP images.bin")
    if asset_root.is_symlink() or not asset_root.is_dir():
        raise C3SemanticError("asset root must be a real directory")
    if any(
        _is_within(target, protected)
        for target in (work_dir, output_dir)
        for protected in (
            image_root,
            geometric_depth_root,
            cameras_bin.parent,
            images_bin.parent,
            asset_root,
        )
    ):
        raise C3SemanticError("work/output path must be outside all immutable input roots")
    if _is_within(output_dir, work_dir) or _is_within(work_dir, output_dir):
        raise C3SemanticError("work and final output namespaces must be disjoint")
    producer_contract = _load_semantic_producer_contract()
    _bind_semantic_runtime_paths(
        producer_contract,
        image_root=image_root,
        cameras_bin=cameras_bin,
        images_bin=images_bin,
        geometric_depth_root=geometric_depth_root,
        input_manifest=input_manifest,
        work_dir=work_dir,
        output_dir=output_dir,
        test_only_allow_unbound_paths=test_only_allow_unbound_paths,
        expected_names=expected_names,
    )
    rows, input_manifest_sha = load_input_manifest(input_manifest, expected_names)
    cameras, images = _load_colmap_semantic_bindings(cameras_bin, images_bin)
    expected_ids = {row["colmap_image_id"] for row in rows}
    if set(images) != expected_ids:
        raise C3SemanticError("COLMAP images.bin does not equal exact membership")
    colmap_bindings = [
        _expected_colmap_binding(row, cameras, images) for row in rows
    ]
    lock = load_c3_contract(lock_path)
    pins = _runtime_pins(lock_path, asset_receipt, lock, producer_contract)
    pins_sha = sha256_bytes(canonical_json_bytes(pins))
    factory = inference_factory or (
        lambda locked, resolved, target: GroundedSamImageSemanticInference(
            locked, resolved, device=target
        )
    )
    inference: Any | None = None
    _bind_work_namespace(work_dir)
    completed_root = work_dir / "completed"
    if os.path.lexists(completed_root):
        if completed_root.is_symlink() or not completed_root.is_dir():
            raise C3SemanticError("semantic completed root must be a real directory")
    else:
        try:
            completed_root.mkdir()
        except FileExistsError as error:
            raise C3SemanticError("semantic completed root appeared during creation") from error
        if completed_root.is_symlink() or not completed_root.is_dir():
            raise C3SemanticError("semantic completed root must be a real directory")
    expected_completion_names = {_completion_name(index, row["name"]) for index, row in enumerate(rows)}
    unexpected = {path.name for path in completed_root.iterdir()} - expected_completion_names
    if unexpected:
        raise C3SemanticError("semantic progress contains entries outside the exact image set")
    prevalidated: dict[int, dict[str, Any]] = {}
    for index, (row, colmap_binding) in enumerate(zip(rows, colmap_bindings)):
        completion = completed_root / _completion_name(index, row["name"])
        if os.path.lexists(completion):
            prevalidated[index] = _validate_completion(
                completion, index, row, colmap_binding, pins_sha
            )
    completions: list[dict[str, Any]] = []
    resumed = 0
    started = 0
    root = image_root.resolve()
    depth_root = geometric_depth_root.resolve()
    for index, (row, colmap_binding) in enumerate(zip(rows, colmap_bindings)):
        completion = completed_root / _completion_name(index, row["name"])
        if index in prevalidated:
            completions.append(prevalidated[index])
            resumed += 1
            continue
        relative = _safe_relative(row["relative_path"])
        image_path = root.joinpath(*relative.parts)
        try:
            image_path.resolve(strict=True).relative_to(root)
        except (FileNotFoundError, ValueError) as error:
            raise C3SemanticError("input image is missing or escapes image root") from error
        if image_path.is_symlink() or not image_path.is_file():
            raise C3SemanticError("input image must be a regular non-symlink file")
        rgb, source_rgb = _read_undistorted_rgb_once(image_path, row["relative_path"])
        if (
            source_rgb["width"] != colmap_binding["width"]
            or source_rgb["height"] != colmap_binding["height"]
        ):
            raise C3SemanticError("undistorted RGB dimensions differ from COLMAP camera")
        depth_relative = _safe_relative(row["geometric_depth_relative_path"])
        depth_path = depth_root.joinpath(*depth_relative.parts)
        try:
            depth_path.resolve(strict=True).relative_to(depth_root)
        except (FileNotFoundError, ValueError) as error:
            raise C3SemanticError("geometric depth is missing or escapes depth root") from error
        depth_binding = _read_colmap_depth_shape(
            depth_path, row["geometric_depth_relative_path"]
        )
        if (
            depth_binding["width"] != source_rgb["width"]
            or depth_binding["height"] != source_rgb["height"]
        ):
            raise C3SemanticError("geometric depth shape differs from undistorted RGB")
        if inference is None:
            runtime_verifier(lock)
            assets = asset_verifier(lock, lock_path, asset_root, asset_receipt)
            inference = factory(lock, assets, device)
        result = inference(rgb)
        if not isinstance(result, SemanticResult):
            raise C3SemanticError("semantic inference returned an unexpected result type")
        if result.labels.shape != (source_rgb["height"], source_rgb["width"]):
            raise C3SemanticError("semantic inference resized or reshaped the undistorted RGB")
        png = _png_bytes(result.labels)
        counts = {str(class_id): int(np.count_nonzero(result.labels == class_id)) for class_id in range(4)}
        receipt = {
            "schema": COMPLETION_SCHEMA,
            "index": index,
            "membership": dict(row),
            "source_rgb": source_rgb,
            "colmap_camera": colmap_binding,
            "geometric_depth": depth_binding,
            "output": {
                "bytes": len(png),
                "sha256": sha256_bytes(png),
                "width": int(result.labels.shape[1]),
                "height": int(result.labels.shape[0]),
                "dtype": "uint8",
                "class_pixel_counts": counts,
            },
            "candidate_count": len(result.candidates),
            "runtime_pins_sha256": pins_sha,
            "scientific_verdict": None,
        }
        staging = Path(tempfile.mkdtemp(prefix=f".{completion.name}.", dir=completed_root))
        try:
            (staging / "mask.png").write_bytes(png)
            (staging / "receipt.json").write_bytes(canonical_json_bytes(receipt))
            _publish_directory_noreplace(staging, completion)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        completions.append(receipt)
        started += 1
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_output = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        masks_dir = staging_output / "masks"
        masks_dir.mkdir()
        records: list[dict[str, Any]] = []
        output_names = [f"{Path(row['name']).stem}.png" for row in rows]
        if len(set(output_names)) != len(output_names):
            raise C3SemanticError("semantic output stems are not unique")
        for index, (row, receipt) in enumerate(zip(rows, completions)):
            source_mask = completed_root / _completion_name(index, row["name"]) / "mask.png"
            output_name = output_names[index]
            target = masks_dir / output_name
            mask_bytes = source_mask.read_bytes()
            if sha256_bytes(mask_bytes) != receipt["output"]["sha256"]:
                raise C3SemanticError("final semantic PNG copy identity differs")
            target.write_bytes(mask_bytes)
            records.append(
                {
                    "name": row["name"],
                    "membership": dict(row),
                    "undistorted_rgb": receipt["source_rgb"],
                    "colmap_camera": receipt["colmap_camera"],
                    "geometric_depth": receipt["geometric_depth"],
                    "output_path": f"masks/{output_name}",
                    **receipt["output"],
                }
            )
        final_manifest = {
            "schema": FINAL_SCHEMA,
            "status": "COMPLETED_EXACT_COLMAP_UNDISTORTED_RGB_LEDGER_AND_IMAGE_ONLY_SEMANTICS",
            "source_role": SOURCE_ROLE,
            "image_count": len(records),
            "expected_image_count": len(rows),
            "input_manifest": {"path": str(input_manifest), "sha256": input_manifest_sha},
            "canonical_name_crosswalk": {
                "path": str(CANONICAL_CROSSWALK.relative_to(REPO)).replace("\\", "/"),
                "bytes": CROSSWALK_BYTES,
                "sha256": CROSSWALK_SHA256,
            },
            "runtime_pins": pins,
            "resumption": {"reused_exact_completed_images": resumed, "new_inference_images": started},
            "work_namespace": {
                "schema": WORK_NAMESPACE_SCHEMA,
                "namespace_id": WORK_NAMESPACE_ID,
                "legacy_raw_completion_reuse_allowed": False,
                "resize_legacy_completion_allowed": False,
            },
            "records": records,
            "prohibited_input_counts": {
                "pose": 0,
                "footprint": 0,
                "building_id": 0,
                "lod1": 0,
                "lod2": 0,
                "uas": 0,
                "als": 0,
                "gt": 0,
            },
            "colmap_pose_values_decoded": 0,
            "colmap_pose_values_exposed_to_inference": 0,
            "downloads": 0,
            "learning_runs_started": 0,
            "scientific_verdict": None,
        }
        (staging_output / "manifest.json").write_bytes(canonical_json_bytes(final_manifest))
        _publish_directory_noreplace(staging_output, output_dir)
    finally:
        if staging_output.exists():
            shutil.rmtree(staging_output)
    return final_manifest

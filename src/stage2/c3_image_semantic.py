"""Pinned, image-only semantic labels for the exact 937-image C3 source set.

This producer deliberately exposes no pose, footprint, building identity, LiDAR,
LoD1, LoD2, or UAS interface. Heavy model loading happens only when ``produce``
is explicitly called with the already verified offline asset cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import ctypes
import csv
import errno
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from PIL import Image as PILImage

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


REPO = Path(__file__).resolve().parents[2]
CANONICAL_CROSSWALK = (
    REPO / "artifacts/manifests/gate_s0/common_base_r2b/exact_937_member_crosswalk_v1.json"
)
CROSSWALK_BYTES = 390716
CROSSWALK_SHA256 = "5944ecf5294732fb3e0f355492de15f59e520b7bf7e3f59933630c9cb1964081"
CANONICAL_IMAGE_INVENTORY = (
    REPO / "artifacts/manifests/gate_s0/gate_s0_image_member_inventory_v1.csv"
)
IMAGE_INVENTORY_BYTES = 152076
IMAGE_INVENTORY_SHA256 = "70e18629c79dffce540d38dedb74ee813b3e1500cdca95f7c139e38a216ff73d"
SEMANTIC_CONTRACT = REPO / "configs/c3_first_wave_v2/c3_image_semantic_producer_v1.json"
SEMANTIC_CONTRACT_BYTES = 1936
SEMANTIC_CONTRACT_SHA256 = "bf550af4b277c81e8d0cd17d134ec64a2faab6388bda6dd6e4889502ab4f3063"
INPUT_SCHEMA = "jointbuildgs.c3_image_semantic_input_manifest.v1"
FINAL_SCHEMA = "jointbuildgs.c3_image_semantic_output_manifest.v1"
COMPLETION_SCHEMA = "jointbuildgs.c3_image_semantic_completion.v1"
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


def canonical_image_names(crosswalk_path: Path = CANONICAL_CROSSWALK) -> list[str]:
    data = crosswalk_path.read_bytes()
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
    return names


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
    if not isinstance(value, dict) or set(value) != {"schema", "images", "scientific_verdict"}:
        raise C3SemanticError("input manifest exposes fields outside the image-only contract")
    if value["schema"] != INPUT_SCHEMA or value["scientific_verdict"] is not None:
        raise C3SemanticError("input manifest schema or scientific_verdict differs")
    rows = value["images"]
    if not isinstance(rows, list):
        raise C3SemanticError("input manifest images must be an array")
    expected = list(canonical_image_names() if expected_names is None else expected_names)
    if len(expected) != len(set(expected)):
        raise C3SemanticError("expected image names are duplicated")
    observed: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"name", "relative_path", "bytes", "sha256"}:
            raise C3SemanticError("input image row has non-image fields")
        relative = _safe_relative(row["relative_path"])
        if (
            not isinstance(row["name"], str)
            or relative.name != row["name"]
            or type(row["bytes"]) is not int
            or row["bytes"] <= 0
        ):
            raise C3SemanticError("input image name/path/byte contract differs")
        if not isinstance(row["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None:
            raise C3SemanticError("input image SHA-256 is invalid")
        observed.append(row["name"])
    if observed != expected:
        raise C3SemanticError("input manifest does not equal the exact ordered RGB-name set")
    return rows, sha256_bytes(data)


def build_input_manifest(
    output_path: Path,
    inventory_path: Path = CANONICAL_IMAGE_INVENTORY,
) -> dict[str, Any]:
    """Bind the exact 937 extracted RGB files from the existing R1 ledger.

    This reads only the compact Git CSV.  It does not reopen or rehash Images.zip
    or any extracted image; the producer verifies each image in its inference
    stream against the already attested per-member digest.
    """

    if output_path.exists():
        raise C3SemanticError("semantic input manifest is add-once and already exists")
    data = inventory_path.read_bytes()
    if len(data) != IMAGE_INVENTORY_BYTES or sha256_bytes(data) != IMAGE_INVENTORY_SHA256:
        raise C3SemanticError("canonical image inventory identity differs")
    ledger = {
        row["basename"]: row
        for row in csv.DictReader(data.decode("utf-8").splitlines())
    }
    names = canonical_image_names()
    if len(ledger) != 962 or any(name not in ledger for name in names):
        raise C3SemanticError("canonical image inventory membership differs")
    rows = [
        {
            "name": name,
            "relative_path": name,
            "bytes": int(ledger[name]["uncompressed_bytes"]),
            "sha256": ledger[name]["sha256"],
        }
        for name in names
    ]
    value = {"schema": INPUT_SCHEMA, "images": rows, "scientific_verdict": None}
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
        "raw_image_reads": 0,
        "images_zip_reads_or_hashes": 0,
        "scientific_verdict": None,
    }


def _runtime_pins(lock_path: Path, receipt_path: Path, lock: Mapping[str, Any]) -> dict[str, Any]:
    contract_data = SEMANTIC_CONTRACT.read_bytes()
    if (
        len(contract_data) != SEMANTIC_CONTRACT_BYTES
        or sha256_bytes(contract_data) != SEMANTIC_CONTRACT_SHA256
    ):
        raise C3SemanticError("C3 semantic producer contract identity differs")
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
            "input",
            "output",
            "candidate_count",
            "runtime_pins_sha256",
            "scientific_verdict",
        }
        or receipt.get("schema") != COMPLETION_SCHEMA
        or receipt.get("index") != index
        or receipt.get("input") != dict(row)
        or receipt.get("runtime_pins_sha256") != pins_sha256
        or type(receipt.get("candidate_count")) is not int
        or receipt["candidate_count"] < 0
        or receipt.get("scientific_verdict") is not None
    ):
        raise C3SemanticError("completed image receipt differs from the exact run contract")
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
    input_manifest: Path,
    lock_path: Path,
    asset_root: Path,
    asset_receipt: Path,
    work_dir: Path,
    output_dir: Path,
    device: str = "cuda",
    expected_names: Sequence[str] | None = None,
    asset_verifier: AssetVerifier = verify_c3_asset_receipt,
    runtime_verifier: RuntimeVerifier = audit_c3_runtime,
    inference_factory: InferenceFactory | None = None,
) -> dict[str, Any]:
    """Resume exact completed images and atomically publish only after all finish."""

    if output_dir.exists():
        raise C3SemanticError("final semantic output directory is add-once and already exists")
    if image_root.is_symlink() or not image_root.is_dir():
        raise C3SemanticError("image root must be a real directory")
    if asset_root.is_symlink() or not asset_root.is_dir():
        raise C3SemanticError("asset root must be a real directory")
    if any(
        _is_within(target, protected)
        for target in (work_dir, output_dir)
        for protected in (image_root, asset_root)
    ):
        raise C3SemanticError("work/output path must be outside image and model input roots")
    if _is_within(output_dir, work_dir) or _is_within(work_dir, output_dir):
        raise C3SemanticError("work and final output namespaces must be disjoint")
    rows, input_manifest_sha = load_input_manifest(input_manifest, expected_names)
    lock = load_c3_contract(lock_path)
    pins = _runtime_pins(lock_path, asset_receipt, lock)
    pins_sha = sha256_bytes(canonical_json_bytes(pins))
    factory = inference_factory or (
        lambda locked, resolved, target: GroundedSamImageSemanticInference(
            locked, resolved, device=target
        )
    )
    inference: Any | None = None
    if work_dir.is_symlink():
        raise C3SemanticError("semantic work directory must not be a symlink")
    completed_root = work_dir / "completed"
    completed_root.mkdir(parents=True, exist_ok=True)
    expected_completion_names = {_completion_name(index, row["name"]) for index, row in enumerate(rows)}
    unexpected = {path.name for path in completed_root.iterdir()} - expected_completion_names
    if unexpected:
        raise C3SemanticError("semantic progress contains entries outside the exact image set")
    completions: list[dict[str, Any]] = []
    resumed = 0
    started = 0
    root = image_root.resolve()
    for index, row in enumerate(rows):
        completion = completed_root / _completion_name(index, row["name"])
        if completion.exists():
            completions.append(_validate_completion(completion, index, row, pins_sha))
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
        if inference is None:
            runtime_verifier(lock)
            assets = asset_verifier(lock, lock_path, asset_root, asset_receipt)
            inference = factory(lock, assets, device)
        source = image_path.read_bytes()
        if len(source) != row["bytes"] or sha256_bytes(source) != row["sha256"]:
            raise C3SemanticError("input image identity differs from its exact manifest")
        with PILImage.open(BytesIO(source)) as image:
            rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        result = inference(rgb)
        if not isinstance(result, SemanticResult):
            raise C3SemanticError("semantic inference returned an unexpected result type")
        png = _png_bytes(result.labels)
        counts = {str(class_id): int(np.count_nonzero(result.labels == class_id)) for class_id in range(4)}
        receipt = {
            "schema": COMPLETION_SCHEMA,
            "index": index,
            "input": dict(row),
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
                    "input_sha256": row["sha256"],
                    "output_path": f"masks/{output_name}",
                    **receipt["output"],
                }
            )
        final_manifest = {
            "schema": FINAL_SCHEMA,
            "status": "COMPLETED_IMAGE_ONLY_DIAGNOSTIC_INPUT",
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

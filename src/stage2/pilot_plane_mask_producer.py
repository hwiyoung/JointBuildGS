"""Locked 04a vision and 04b LoD2 upper-bound plane-mask production.

This module is deliberately independent from :mod:`src.stage2.train`.  It
contains four boundaries that are useful before the first pilot learning run:

* an offline, receipt-verified GroundingDINO Swin-T + SAM ViT-H wrapper;
* GT-free MVS-depth/COLMAP-pose cross-view consistency and footprint fusion;
* LoD2 semantic-surface raycasting whose public result is a bool mask only; and
* a hard controlled-pair validator that permits exactly the three declared
  plane-mask source/path/hash differences between 04a and 04b.

No import in this file downloads a model.  Heavy optional dependencies and
pinned upstream source trees are imported only when inference/raycast is
explicitly executed.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import platform
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from typing import Any, Mapping, Sequence
from urllib.request import Request, urlopen

import cv2
import numpy as np
from PIL import Image as PILImage
from shapely.geometry import Polygon
from shapely.ops import triangulate as shapely_triangulate

from .colmap_io import Camera, Image
from .pilot_mask_schema import BinaryMaskSet, MaskPurpose, MaskSource


LOCK_SCHEMA = "jointbuildgs.pilot_1wave.mask_producer_lock.v1"
RECEIPT_SCHEMA = "jointbuildgs.pilot_1wave.mask_producer_asset_receipt.v1"
EXPECTED_ASSETS = (
    "groundingdino_source",
    "segment_anything_source",
    "groundingdino_swint_ogc",
    "sam_vit_h",
    "bert_base_uncased",
)
EXPECTED_BERT_REPOSITORY = "google-bert/bert-base-uncased"
EXPECTED_BERT_REVISION = "86b5e0934494bd15c9632b12f734a8a67f723594"
EXPECTED_DINO_REVISION = "856dde20aee659246248e20734ef9ba5214f5e44"
EXPECTED_SAM_REVISION = "dca509fe793f601edb92606367a655c15ac00fdf"
EXPECTED_BASE_DOCKER_IMAGE_TAG = "jointbuildgs:dev"
EXPECTED_BASE_DOCKER_IMAGE_ID = (
    "sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
)
EXPECTED_DOCKER_IMAGE_TAG = "jointbuildgs:p1w-groundedsam-v1"
EXPECTED_DOCKER_IMAGE_ID = (
    "sha256:3622911fb15eb2f460637f5c3f7f34f2790f5957b0475d1827d6c0a3e5dc88b1"
)
EXPECTED_RUNTIME_REQUIREMENTS_SHA256 = (
    "399b3860c291e6685bc63c3704bf34b1a6b1ef9a5c59e1ede6e583433d36a063"
)
EXPECTED_DISTRIBUTION_VERSIONS = {
    "torch": "2.4.1+cu121",
    "torchvision": "0.19.1+cu121",
    "transformers": "4.40.2",
    "tokenizers": "0.19.1",
    "huggingface-hub": "0.23.5",
    "safetensors": "0.4.3",
    "timm": "0.9.16",
    "addict": "2.4.0",
    "yapf": "0.40.2",
    "regex": "2024.5.15",
    "termcolor": "2.4.0",
    "tomli": "2.0.1",
    "pycocotools": "2.0.8",
}
EXPECTED_PYTHON_MODULES = (
    "torch",
    "torchvision",
    "transformers",
    "tokenizers",
    "huggingface_hub",
    "safetensors",
    "timm",
    "addict",
    "yapf",
    "regex",
    "termcolor",
    "tomli",
    "pycocotools",
)
MODULE_DISTRIBUTION = {"huggingface_hub": "huggingface-hub"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SURFACE_CLASS = {"RoofSurface": 1, "WallSurface": 2, "GroundSurface": 3}
CONTROLLED_PAIR_PATHS = (
    "plane_region_mask.source",
    "plane_region_mask.manifest_path",
    "plane_region_mask.manifest_sha256",
)


class MaskProducerError(RuntimeError):
    """A producer lock, geometry, asset, or controlled-pair gate failed."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_file(path: str | Path, block_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative(value: Any, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise MaskProducerError(f"{field} must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise MaskProducerError(f"{field} is unsafe: {value!r}")
    return path


def _tree_receipt(path: Path) -> tuple[int, str, list[dict[str, Any]]]:
    """Hash a flat/extracted runtime tree, excluding VCS administrative files."""

    if not path.is_dir() or path.is_symlink():
        raise MaskProducerError(f"runtime tree must be a real directory: {path}")
    rows: list[dict[str, Any]] = []
    total = 0
    for item in sorted(path.rglob("*")):
        relative = item.relative_to(path)
        if ".git" in relative.parts:
            continue
        if item.is_symlink():
            raise MaskProducerError(f"runtime assets must not contain symlinks: {item}")
        if item.is_dir():
            continue
        if not item.is_file():
            raise MaskProducerError(f"runtime asset is not a regular file: {item}")
        size = item.stat().st_size
        digest = sha256_file(item)
        total += size
        rows.append(
            {"path": relative.as_posix(), "size_bytes": size, "sha256": digest}
        )
    if not rows:
        raise MaskProducerError(f"runtime tree contains no files: {path}")
    return total, hashlib.sha256(canonical_json_bytes(rows)).hexdigest(), rows


def _git_output(root: Path, arguments: Sequence[str]) -> str:
    process = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        text=True,
        capture_output=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if process.returncode != 0:
        detail = (process.stderr or process.stdout).strip()[-2000:]
        raise MaskProducerError(f"git source attestation failed: {detail}")
    return process.stdout


def _git_tracked_source_attestation(
    root: Path, expected_revision: str, *, include_root: bool
) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise MaskProducerError(f"runtime source root must be a real directory: {root}")
    head = _git_output(root, ["rev-parse", "HEAD"]).strip()
    if head != expected_revision:
        raise MaskProducerError(
            f"source HEAD differs: {root}: {head} != {expected_revision}"
        )
    tree = _git_output(root, ["rev-parse", "HEAD^{tree}"]).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", tree):
        raise MaskProducerError(f"source git tree is malformed: {root}")
    tracked_status = _git_output(
        root, ["status", "--porcelain", "--untracked-files=no"]
    )
    if tracked_status:
        raise MaskProducerError(f"source tracked worktree is dirty: {root}")
    tracked_names = _git_output(root, ["ls-files", "-z"]).split("\0")
    tracked_rows: list[dict[str, Any]] = []
    total = 0
    for name in tracked_names:
        if not name:
            continue
        relative = _safe_relative(name, "git tracked source path")
        path = root.joinpath(*relative.parts)
        if not path.is_file() or path.is_symlink():
            raise MaskProducerError(f"tracked source must be a regular file: {path}")
        size = path.stat().st_size
        total += size
        tracked_rows.append(
            {
                "path": relative.as_posix(),
                "size_bytes": size,
                "sha256": sha256_file(path),
            }
        )
    if not tracked_rows:
        raise MaskProducerError(f"source checkout contains no tracked files: {root}")
    result: dict[str, Any] = {
        "git_head": head,
        "git_tree": tree,
        "tracked_worktree_clean": True,
        "tracked_file_count": len(tracked_rows),
        "tracked_size_bytes": total,
        "tracked_files_sha256": hashlib.sha256(
            canonical_json_bytes(tracked_rows)
        ).hexdigest(),
    }
    if include_root:
        result["source_root"] = str(root.resolve())
    return result


def collect_runtime_attestation(lock: Mapping[str, Any]) -> dict[str, Any]:
    """Attest the exact image-side runtime independently from fetched assets."""

    runtime = lock["runtime_environment"]
    gate = lock["runtime_dependency_gate"]
    if platform.python_version() != gate["required_python_version"]:
        raise MaskProducerError(
            f"Python runtime differs: {platform.python_version()} != "
            f"{gate['required_python_version']}"
        )
    versions: dict[str, str] = {}
    for distribution, expected in gate["required_distribution_versions"].items():
        try:
            actual = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError as exc:
            raise MaskProducerError(
                f"required runtime distribution is missing: {distribution}"
            ) from exc
        if actual != expected:
            raise MaskProducerError(
                f"runtime distribution differs: {distribution} {actual} != {expected}"
            )
        versions[distribution] = actual
    requirements_path = Path(runtime["runtime_requirements_path"])
    if (
        not requirements_path.is_file()
        or requirements_path.is_symlink()
        or sha256_file(requirements_path) != runtime["runtime_requirements_sha256"]
    ):
        raise MaskProducerError("runtime requirements file SHA differs from lock")
    dino_root = Path(runtime["groundingdino_source_root"])
    sam_root = Path(runtime["segment_anything_source_root"])
    source_trees = {
        "groundingdino": _git_tracked_source_attestation(
            dino_root, EXPECTED_DINO_REVISION, include_root=True
        ),
        "segment_anything": _git_tracked_source_attestation(
            sam_root, EXPECTED_SAM_REVISION, include_root=True
        ),
    }
    evidence = lock["groundingdino_primary_source_evidence"]
    runtime_pins = {
        "groundingdino/models/GroundingDINO/groundingdino.py": evidence[
            "model_source_sha256"
        ],
        "groundingdino/util/get_tokenlizer.py": evidence[
            "tokenizer_loader_sha256"
        ],
    }
    for relative, expected_sha in runtime_pins.items():
        path = dino_root / relative
        if not path.is_file() or path.is_symlink() or sha256_file(path) != expected_sha:
            raise MaskProducerError(f"runtime GroundingDINO source differs: {relative}")
    extensions = sorted(
        path
        for path in dino_root.glob(gate["required_groundingdino_extension_glob"])
        if path.is_file() and not path.is_symlink()
    )
    if len(extensions) != 1:
        raise MaskProducerError(
            f"runtime must contain exactly one GroundingDINO _C extension, got {len(extensions)}"
        )
    extension = extensions[0]
    ignored = subprocess.run(
        ["git", "-C", str(dino_root), "check-ignore", "-q", str(extension)],
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    ).returncode == 0
    if not ignored:
        raise MaskProducerError("runtime extension must be ignored by the clean source tree")
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - distribution gate catches this first
        raise MaskProducerError("runtime torch import failed") from exc
    if str(torch.version.cuda) != gate["compiled_torch_cuda"]:
        raise MaskProducerError(
            f"torch CUDA differs: {torch.version.cuda} != {gate['compiled_torch_cuda']}"
        )
    if os.environ.get("TORCH_CUDA_ARCH_LIST") != gate["compiled_cuda_arch"]:
        raise MaskProducerError("TORCH_CUDA_ARCH_LIST differs from runtime lock")
    return {
        "python_version": platform.python_version(),
        "distribution_versions": versions,
        "runtime_requirements": {
            "path": str(requirements_path),
            "size_bytes": requirements_path.stat().st_size,
            "sha256": sha256_file(requirements_path),
        },
        "source_trees": source_trees,
        "groundingdino_cuda_extension": {
            "path": str(extension.resolve()),
            "size_bytes": extension.stat().st_size,
            "sha256": sha256_file(extension),
            "git_ignored": True,
            "torch_cuda": str(torch.version.cuda),
            "cuda_arch": os.environ["TORCH_CUDA_ARCH_LIST"],
        },
    }


def load_producer_lock(path: str | Path) -> dict[str, Any]:
    lock = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(lock, dict) or lock.get("schema") != LOCK_SCHEMA:
        raise MaskProducerError(f"producer lock schema must be {LOCK_SCHEMA}")
    if lock.get("training_started_by_this_lock") is not False:
        raise MaskProducerError("producer lock must not claim a learning run")
    if lock.get("inference_started_by_this_lock") is not False:
        raise MaskProducerError("producer lock itself must not claim inference")
    runtime = lock.get("runtime_environment", {})
    if (
        runtime.get("base_docker_image_tag") != EXPECTED_BASE_DOCKER_IMAGE_TAG
        or runtime.get("base_docker_image_id") != EXPECTED_BASE_DOCKER_IMAGE_ID
        or runtime.get("runtime_requirements_sha256")
        != EXPECTED_RUNTIME_REQUIREMENTS_SHA256
        or runtime.get("docker_image_tag") != EXPECTED_DOCKER_IMAGE_TAG
        or runtime.get("docker_image_id") != EXPECTED_DOCKER_IMAGE_ID
    ):
        raise MaskProducerError("mask producer Docker image tag/ID changed")
    dependency_gate = lock.get("runtime_dependency_gate", {})
    required_versions = dependency_gate.get("required_distribution_versions")
    if (
        dependency_gate.get("required_python_modules") != list(EXPECTED_PYTHON_MODULES)
        or required_versions != EXPECTED_DISTRIBUTION_VERSIONS
        or dependency_gate.get("required_python_version") != "3.11.15"
        or dependency_gate.get("required_groundingdino_extension_glob")
        != "groundingdino/_C*.so"
        or dependency_gate.get("compiled_cuda_arch") != "8.6"
        or dependency_gate.get("compiled_torch_cuda") != "12.1"
    ):
        raise MaskProducerError("GroundedSAM runtime dependency gate changed")
    assets = lock.get("runtime_assets")
    if not isinstance(assets, dict) or tuple(assets) != EXPECTED_ASSETS:
        raise MaskProducerError("producer runtime assets differ from the locked inventory")
    if assets["groundingdino_source"].get("revision") != EXPECTED_DINO_REVISION:
        raise MaskProducerError("GroundingDINO source revision changed")
    if assets["segment_anything_source"].get("revision") != EXPECTED_SAM_REVISION:
        raise MaskProducerError("Segment Anything source revision changed")
    bert = assets["bert_base_uncased"]
    if (
        bert.get("repository") != EXPECTED_BERT_REPOSITORY
        or bert.get("revision") != EXPECTED_BERT_REVISION
        or bert.get("fetch_weight_file") != "model.safetensors"
    ):
        raise MaskProducerError("BERT repository/revision changed")
    expected_cache_paths = {
        "groundingdino_source": "sources/GroundingDINO",
        "segment_anything_source": "sources/segment-anything",
        "groundingdino_swint_ogc": "weights/groundingdino_swint_ogc.pth",
        "sam_vit_h": "weights/sam_vit_h_4b8939.pth",
        "bert_base_uncased": "snapshots/google-bert_bert-base-uncased_86b5e0934494bd15",
    }
    for artifact_id, relative in expected_cache_paths.items():
        if assets[artifact_id].get("cache_relative_path") != relative:
            raise MaskProducerError(f"cache layout changed: {artifact_id}")
    evidence = lock.get("groundingdino_primary_source_evidence", {})
    if (
        evidence.get("locked_field") != "text_encoder_type"
        or evidence.get("locked_value") != "bert-base-uncased"
        or not SHA256_RE.fullmatch(str(evidence.get("config_sha256", "")))
        or not SHA256_RE.fullmatch(str(evidence.get("model_source_sha256", "")))
        or not SHA256_RE.fullmatch(str(evidence.get("tokenizer_loader_sha256", "")))
    ):
        raise MaskProducerError("GroundingDINO BERT primary-source evidence is incomplete")
    grounded = lock.get("grounded_sam", {})
    expected_grounded = {
        "prompt_literal": "roof",
        "effective_caption": "roof.",
        "box_threshold_strict_gt": 0.25,
        "text_threshold_strict_gt": 0.25,
        "nms_iou": 0.8,
    }
    for key, value in expected_grounded.items():
        if grounded.get(key) != value:
            raise MaskProducerError(f"GroundedSAM lock changed: {key}")
    preprocess = grounded.get("groundingdino_rgb_preprocess", {})
    if (
        preprocess.get("pil_mode") != "RGB"
        or preprocess.get("short_side") != 800
        or preprocess.get("max_side") != 1333
        or preprocess.get("mean") != [0.485, 0.456, 0.406]
        or preprocess.get("std") != [0.229, 0.224, 0.225]
    ):
        raise MaskProducerError("GroundingDINO RGB preprocessing lock changed")
    sam = grounded.get("sam", {})
    if (
        sam.get("model_type") != "vit_h"
        or sam.get("longest_side") != 1024
        or sam.get("multimask_output") is not False
        or sam.get("mask_threshold") != 0.0
    ):
        raise MaskProducerError("SAM ViT-H preprocessing/output lock changed")
    cross = lock.get("cross_view_consistency", {})
    expected_cross = {
        "minimum_support_views_including_source": 2,
        "maximum_pose_neighbors_per_source": 4,
        "maximum_optical_axis_angle_deg": 20.0,
        "minimum_camera_baseline_m": 0.5,
        "reprojection_mask_tolerance_px": 3,
        "target_depth_absolute_tolerance_m": 0.5,
        "target_depth_relative_tolerance": 0.02,
    }
    for key, value in expected_cross.items():
        if cross.get(key) != value:
            raise MaskProducerError(f"cross-view lock changed: {key}")
    fusion = lock.get("vision_fusion", {})
    expected_fusion = {
        "footprint_dilation_radius_px": 5,
        "footprint_core_erosion_radius_px": 5,
        "small_core_retry_erosion_radius_px": 1,
        "small_core_final_fallback_erosion_radius_px": 0,
        "small_core_fallback_order_px": [5, 1, 0],
        "structuring_element": "closed Euclidean disk",
        "zero_radius_policy": (
            "only after 5px and 1px cores are empty, retain the original nonempty "
            "per-building projected footprint; a view with no nonempty projected "
            "selected-building footprint still hard-fails"
        ),
        "fallback_audit_policy": (
            "record per-view 1px/0px fallback counts and building IDs plus "
            "per-building erosion radius"
        ),
        "inference_attempt_cli": "--prior-inference-runs-started",
        "inference_attempt_policy": (
            "required explicit nonnegative prior failed-attempt count; successful "
            "manifest records cumulative started, successful, and failed counts"
        ),
        "gt_used": False,
    }
    for key, value in expected_fusion.items():
        if fusion.get(key) != value:
            raise MaskProducerError(f"vision-fusion lock changed: {key}")
    upper = lock.get("gt_upperbound", {})
    if (
        upper.get("positive_class") != "selected-building RoofSurface"
        or upper.get("world_offset") != [690953.0, 5336071.0, 604.0]
        or upper.get("orthometric_geoid_m") != 45.7
        or upper.get("polygon_planarity_tolerance_m") != 0.01
        or not SHA256_RE.fullmatch(str(upper.get("projection_datum_sha256", "")))
    ):
        raise MaskProducerError("LoD2 upper-bound coordinate/archive lock changed")
    pair = lock.get("controlled_pair", {})
    if tuple(pair.get("allowed_training_config_difference_paths", ())) != CONTROLLED_PAIR_PATHS:
        raise MaskProducerError("controlled-pair allowed difference paths changed")
    receipt = lock.get("asset_receipt", {})
    if (
        receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("receipt_sha256")
        != "ff144c6571713563895a41a67585e4d8b6f3d6f4bdef4a46716a19bd6efab76c"
        or receipt.get("producer_lock_sha256_at_fetch")
        != "4728402e0ff781d8322c8fbf2f663e473575f872cfac0d7180c1f34627916f16"
        or receipt.get("revision_note")
        != "fusion-only revision; asset bytes unchanged"
        or tuple(receipt.get("required_artifact_ids", ())) != EXPECTED_ASSETS
        or receipt.get("download_during_preflight") is not False
        or receipt.get("symlinks_allowed") is not False
        or receipt.get("verify_source_git_head_tree_and_clean_tracked_worktree")
        is not True
        or receipt.get("verify_runtime_extension_sha256_and_size") is not True
    ):
        raise MaskProducerError("asset receipt contract changed")
    return lock


def verify_asset_receipt(
    lock: Mapping[str, Any],
    lock_path: str | Path,
    cache_root: str | Path,
    receipt_path: str | Path,
) -> dict[str, Path]:
    """Verify every local inference asset without any network access."""

    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise MaskProducerError(f"asset receipt schema must be {RECEIPT_SCHEMA}")
    receipt_contract = lock["asset_receipt"]
    if sha256_file(receipt_path) != receipt_contract["receipt_sha256"]:
        raise MaskProducerError("asset receipt bytes differ from the frozen receipt SHA")
    if (
        receipt.get("producer_lock_sha256")
        != receipt_contract["producer_lock_sha256_at_fetch"]
    ):
        raise MaskProducerError("asset receipt fetch-time producer-lock SHA differs")
    if receipt.get("runtime_environment") != lock.get("runtime_environment"):
        raise MaskProducerError("asset receipt Docker image tag/ID differs from lock")
    current_runtime_attestation = collect_runtime_attestation(lock)
    if (
        canonical_json_bytes(receipt.get("runtime_attestation"))
        != canonical_json_bytes(current_runtime_attestation)
    ):
        raise MaskProducerError(
            "asset receipt runtime source/dependency/extension attestation differs"
        )
    rows = receipt.get("artifacts")
    if not isinstance(rows, dict) or tuple(rows) != EXPECTED_ASSETS:
        raise MaskProducerError("asset receipt must contain the exact locked inventory")
    root = Path(cache_root)
    if not root.is_dir() or root.is_symlink():
        raise MaskProducerError(f"asset cache root must be a real directory: {root}")
    resolved: dict[str, Path] = {}
    locked_assets = lock["runtime_assets"]
    for artifact_id in EXPECTED_ASSETS:
        row = rows[artifact_id]
        if not isinstance(row, dict):
            raise MaskProducerError(f"invalid receipt row: {artifact_id}")
        relative = _safe_relative(row.get("relative_path"), f"{artifact_id}.relative_path")
        if relative.as_posix() != locked_assets[artifact_id].get("cache_relative_path"):
            raise MaskProducerError(f"asset cache path differs from lock: {artifact_id}")
        path = root.joinpath(*relative.parts)
        try:
            path.resolve(strict=True).relative_to(root.resolve(strict=True))
        except (FileNotFoundError, ValueError) as exc:
            raise MaskProducerError(f"asset escapes cache or is missing: {artifact_id}") from exc
        locked = locked_assets[artifact_id]
        if row.get("kind") != locked.get("kind"):
            raise MaskProducerError(f"asset kind differs from lock: {artifact_id}")
        if locked["kind"] == "file":
            if not path.is_file() or path.is_symlink():
                raise MaskProducerError(f"asset must be a regular file: {artifact_id}")
            size = path.stat().st_size
            digest = sha256_file(path)
            if row.get("source") != locked.get("url"):
                raise MaskProducerError(f"asset source URL differs from lock: {artifact_id}")
        else:
            size, digest, _entries = _tree_receipt(path)
            if locked["kind"] == "source_tree":
                if (
                    row.get("source") != locked.get("repository")
                    or row.get("revision") != locked.get("revision")
                ):
                    raise MaskProducerError(f"source tree pin differs: {artifact_id}")
                git = subprocess.run(
                    ["git", "-C", str(path), "rev-parse", "HEAD"],
                    check=False,
                    text=True,
                    capture_output=True,
                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                )
                if git.returncode != 0 or git.stdout.strip() != locked.get("revision"):
                    raise MaskProducerError(f"source checkout HEAD differs: {artifact_id}")
                expected_git = _git_tracked_source_attestation(
                    path, str(locked["revision"]), include_root=False
                )
                if canonical_json_bytes(row.get("git")) != canonical_json_bytes(
                    expected_git
                ):
                    raise MaskProducerError(
                        f"source checkout tracked-tree receipt differs: {artifact_id}"
                    )
            elif locked["kind"] == "huggingface_snapshot":
                if (
                    row.get("source") != locked.get("repository")
                    or row.get("revision") != locked.get("revision")
                ):
                    raise MaskProducerError("BERT snapshot pin differs from lock")
                for filename in locked["required_files"]:
                    target = path / filename
                    if not target.is_file() or target.is_symlink():
                        raise MaskProducerError(f"BERT snapshot lacks {filename}")
                if not any(
                    (path / filename).is_file()
                    and not (path / filename).is_symlink()
                    for filename in locked["required_weight_alternatives"]
                ):
                    raise MaskProducerError("BERT snapshot lacks a locked model-weight alternative")
            else:  # pragma: no cover - load_producer_lock closes the enumeration
                raise AssertionError(locked["kind"])
        if int(row.get("size_bytes", -1)) != size:
            raise MaskProducerError(f"asset byte count differs from receipt: {artifact_id}")
        if row.get("sha256") != digest or not SHA256_RE.fullmatch(str(digest)):
            raise MaskProducerError(f"asset SHA256 differs from receipt: {artifact_id}")
        resolved[artifact_id] = path
    dino_root = resolved["groundingdino_source"]
    evidence = lock["groundingdino_primary_source_evidence"]
    pinned_files = {
        "groundingdino/config/GroundingDINO_SwinT_OGC.py": evidence[
            "config_sha256"
        ],
        "groundingdino/models/GroundingDINO/groundingdino.py": evidence[
            "model_source_sha256"
        ],
        "groundingdino/util/get_tokenlizer.py": evidence[
            "tokenizer_loader_sha256"
        ],
    }
    for relative, expected_sha in pinned_files.items():
        path = dino_root / relative
        if not path.is_file() or path.is_symlink() or sha256_file(path) != expected_sha:
            raise MaskProducerError(
                f"GroundingDINO primary source differs from pinned revision: {relative}"
            )
    return resolved


def audit_grounded_sam_runtime(
    lock: Mapping[str, Any], assets: Mapping[str, Path] | None = None
) -> dict[str, Any]:
    """Read-only audit of modules and GroundingDINO's compiled deformable-attn op."""

    modules: dict[str, Any] = {}
    for module_name in lock["runtime_dependency_gate"]["required_python_modules"]:
        present = importlib.util.find_spec(module_name) is not None
        version: str | None = None
        expected_version: str | None = None
        if present:
            distribution = MODULE_DISTRIBUTION.get(module_name, module_name)
            expected_version = lock["runtime_dependency_gate"][
                "required_distribution_versions"
            ].get(distribution)
            try:
                version = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                version = "present_version_unavailable"
        modules[module_name] = {
            "present": present,
            "version": version,
            "expected_version": expected_version,
            "version_matches": present and version == expected_version,
        }
    runtime_attestation: dict[str, Any] | None = None
    runtime_error: str | None = None
    try:
        runtime_attestation = collect_runtime_attestation(lock)
    except MaskProducerError as exc:
        runtime_error = str(exc)
    all_modules = all(row["version_matches"] for row in modules.values())
    extension = (
        None
        if runtime_attestation is None
        else runtime_attestation["groundingdino_cuda_extension"]
    )
    return {
        "modules": modules,
        "runtime_attestation": runtime_attestation,
        "runtime_error": runtime_error,
        "all_required_modules_present": all_modules,
        "groundingdino_compiled_extension_present": extension is not None,
        "ready": all_modules and runtime_attestation is not None,
    }


def _assert_cache_target_safe(cache_root: Path, repository_root: Path) -> None:
    """Require an external path or an explicitly git-ignored in-repo cache."""

    target = cache_root.resolve(strict=False)
    repo = repository_root.resolve(strict=True)
    try:
        relative = target.relative_to(repo)
    except ValueError:
        return
    probe = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", relative.as_posix()],
        cwd=repo,
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if probe.returncode != 0:
        raise MaskProducerError(
            f"in-repository asset cache must be git-ignored: {relative.as_posix()}"
        )


def _run_git(arguments: Sequence[str], *, cwd: Path | None = None) -> None:
    process = subprocess.run(
        list(arguments),
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if process.returncode != 0:
        detail = (process.stderr or process.stdout).strip()[-2000:]
        raise MaskProducerError(f"git asset fetch failed: {detail}")


def _fetch_source_checkout(destination: Path, repository: str, revision: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run_git(["git", "init", str(destination)])
    _run_git(["git", "-C", str(destination), "remote", "add", "origin", repository])
    _run_git(
        [
            "git",
            "-C",
            str(destination),
            "fetch",
            "--depth=1",
            "origin",
            revision,
        ]
    )
    _run_git(["git", "-C", str(destination), "checkout", "--detach", "FETCH_HEAD"])
    head = subprocess.run(
        ["git", "-C", str(destination), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if head != revision:
        raise MaskProducerError(f"source checkout resolved {head}, expected {revision}")


def _download_file(url: str, destination: Path) -> None:
    if not url.startswith("https://"):
        raise MaskProducerError(f"asset download URL must use HTTPS: {url}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "JointBuildGS-P1W-mask-assets/1"})
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.download")
    if temporary.exists():
        raise MaskProducerError(f"download temporary path already exists: {temporary}")
    try:
        with urlopen(request) as response, temporary.open("xb") as stream:
            while True:
                block = response.read(8 * 1024 * 1024)
                if not block:
                    break
                stream.write(block)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.stat().st_size <= 0:
            raise MaskProducerError(f"downloaded asset is empty: {url}")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(
        payload, ensure_ascii=False, indent=2, sort_keys=False, allow_nan=False
    ).encode("utf-8") + b"\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _artifact_receipt_row(
    artifact_id: str,
    locked: Mapping[str, Any],
    path: Path,
    staging_root: Path,
) -> dict[str, Any]:
    if path.is_dir():
        size, digest, _ = _tree_receipt(path)
    else:
        if not path.is_file() or path.is_symlink():
            raise MaskProducerError(f"fresh asset is not a regular file: {artifact_id}")
        size, digest = path.stat().st_size, sha256_file(path)
    row = {
        "kind": locked["kind"],
        "relative_path": path.relative_to(staging_root).as_posix(),
        "source": locked.get("repository", locked.get("url")),
        "size_bytes": size,
        "sha256": digest,
    }
    if "revision" in locked:
        row["revision"] = locked["revision"]
    if locked["kind"] == "source_tree":
        row["git"] = _git_tracked_source_attestation(
            path, str(locked["revision"]), include_root=False
        )
    return row


def fetch_asset_bundle(
    lock: Mapping[str, Any],
    lock_path: str | Path,
    cache_root: str | Path,
    repository_root: str | Path,
) -> dict[str, Any]:
    """Explicitly fetch one immutable asset bundle and atomically publish it.

    A pre-existing bundle is reused only when its receipt and every local byte,
    source-tree HEAD, and directory tree hash verify.  Invalid or partial roots
    are never overwritten.
    """

    target = Path(cache_root)
    repo = Path(repository_root)
    _assert_cache_target_safe(target, repo)
    runtime_attestation = collect_runtime_attestation(lock)
    receipt_name = "asset_receipt.json"
    if target.exists():
        receipt_path = target / receipt_name
        if not target.is_dir() or target.is_symlink() or not receipt_path.is_file():
            raise MaskProducerError(
                "existing asset cache is not a receipt-verified bundle; choose a new path"
            )
        verify_asset_receipt(lock, lock_path, target, receipt_path)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        return {"reused_existing": True, "receipt": receipt, "receipt_path": str(receipt_path)}

    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.staging.", dir=str(parent))
    )
    try:
        assets = lock["runtime_assets"]
        for artifact_id in ("groundingdino_source", "segment_anything_source"):
            row = assets[artifact_id]
            destination = staging / row["cache_relative_path"]
            _fetch_source_checkout(destination, row["repository"], row["revision"])
        for artifact_id in ("groundingdino_swint_ogc", "sam_vit_h"):
            row = assets[artifact_id]
            _download_file(row["url"], staging / row["cache_relative_path"])
        bert = assets["bert_base_uncased"]
        bert_root = staging / bert["cache_relative_path"]
        filenames = [*bert["required_files"], bert["fetch_weight_file"]]
        for filename in filenames:
            url = (
                f"https://huggingface.co/{bert['repository']}/resolve/"
                f"{bert['revision']}/{filename}"
            )
            _download_file(url, bert_root / filename)

        artifact_rows: dict[str, Any] = {}
        for artifact_id in EXPECTED_ASSETS:
            row = assets[artifact_id]
            artifact_rows[artifact_id] = _artifact_receipt_row(
                artifact_id,
                row,
                staging / row["cache_relative_path"],
                staging,
            )
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "producer_lock_sha256": sha256_file(lock_path),
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "runtime_environment": dict(lock["runtime_environment"]),
            "runtime_attestation": runtime_attestation,
            "network_accessed": True,
            "learning_runs_started": 0,
            "inference_runs_started": 0,
            "artifacts": artifact_rows,
        }
        receipt_path = staging / receipt_name
        _write_json_atomic(receipt_path, receipt)
        verify_asset_receipt(lock, lock_path, staging, receipt_path)
        if target.exists():
            raise MaskProducerError("asset cache target appeared during fetch; refusing overwrite")
        staging.chmod(0o755)
        os.replace(staging, target)
        directory_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return {
            "reused_existing": False,
            "receipt": receipt,
            "receipt_path": str(target / receipt_name),
        }
    except Exception:
        if staging.exists() and staging.parent.resolve() == parent.resolve():
            shutil.rmtree(staging)
        raise


@dataclass(frozen=True)
class CrossViewParameters:
    minimum_support_views_including_source: int = 2
    maximum_pose_neighbors_per_source: int = 4
    maximum_optical_axis_angle_deg: float = 20.0
    minimum_camera_baseline_m: float = 0.5
    reprojection_mask_tolerance_px: int = 3
    target_depth_absolute_tolerance_m: float = 0.5
    target_depth_relative_tolerance: float = 0.02


@dataclass(frozen=True)
class ViewFrame:
    view_id: str
    camera: Camera
    image: Image
    mvs_depth: np.ndarray

    def __post_init__(self) -> None:
        depth = np.asarray(self.mvs_depth)
        if depth.ndim != 2 or depth.shape != (self.camera.height, self.camera.width):
            raise MaskProducerError(
                f"{self.view_id}: MVS depth shape {depth.shape} does not match "
                f"camera {(self.camera.height, self.camera.width)}"
            )

    @property
    def centre_world(self) -> np.ndarray:
        return -self.image.R().T @ self.image.tvec

    @property
    def optical_axis_world(self) -> np.ndarray:
        value = self.image.R().T @ np.asarray([0.0, 0.0, 1.0])
        return value / np.linalg.norm(value)


@dataclass(frozen=True)
class CrossViewAudit:
    view_id: str
    eligible_neighbor_ids: tuple[str, ...]
    raw_candidate_pixels: int
    source_valid_depth_candidate_pixels: int
    consistent_candidate_pixels: int
    no_valid_neighbor: bool


def resize_mvs_depth_to_camera(depth: np.ndarray, camera: Camera) -> np.ndarray:
    value = np.asarray(depth, dtype=np.float32)
    if value.ndim != 2:
        raise MaskProducerError("MVS depth must be HxW")
    if value.shape != (camera.height, camera.width):
        value = cv2.resize(
            value,
            (int(camera.width), int(camera.height)),
            interpolation=cv2.INTER_NEAREST,
        )
    value = np.asarray(value, dtype=np.float32)
    value[~np.isfinite(value) | (value <= 0.0)] = np.nan
    return np.ascontiguousarray(value)


def _disk(radius: int) -> np.ndarray:
    if type(radius) is not int or radius < 0:
        raise MaskProducerError("morphology radius must be a non-negative integer")
    yy, xx = np.mgrid[-radius : radius + 1, -radius : radius + 1]
    return np.asarray(xx * xx + yy * yy <= radius * radius, dtype=np.uint8)


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    return cv2.dilate(np.asarray(mask, dtype=np.uint8), _disk(radius), iterations=1).astype(bool)


def _erode(mask: np.ndarray, radius: int) -> np.ndarray:
    return cv2.erode(np.asarray(mask, dtype=np.uint8), _disk(radius), iterations=1).astype(bool)


def select_pose_neighbors(
    source: ViewFrame,
    frames: Mapping[str, ViewFrame],
    parameters: CrossViewParameters = CrossViewParameters(),
) -> tuple[ViewFrame, ...]:
    candidates: list[tuple[float, str, ViewFrame]] = []
    source_axis = source.optical_axis_world
    source_centre = source.centre_world
    for view_id, target in frames.items():
        if view_id == source.view_id:
            continue
        baseline = float(np.linalg.norm(target.centre_world - source_centre))
        if baseline < parameters.minimum_camera_baseline_m:
            continue
        cosine = float(np.clip(np.dot(source_axis, target.optical_axis_world), -1.0, 1.0))
        angle = math.degrees(math.acos(cosine))
        if angle > parameters.maximum_optical_axis_angle_deg:
            continue
        candidates.append((baseline, view_id, target))
    candidates.sort(key=lambda row: (row[0], row[1]))
    return tuple(row[2] for row in candidates[: parameters.maximum_pose_neighbors_per_source])


def _neighbor_support(
    source: ViewFrame,
    target: ViewFrame,
    source_candidate: np.ndarray,
    target_candidate: np.ndarray,
    parameters: CrossViewParameters,
) -> tuple[np.ndarray, int]:
    ys, xs = np.nonzero(source_candidate)
    support = np.zeros(source_candidate.shape, dtype=bool)
    if len(xs) == 0:
        return support, 0
    source_depth = np.asarray(source.mvs_depth, dtype=np.float64)[ys, xs]
    source_valid = np.isfinite(source_depth) & (source_depth > 0.0)
    if not np.any(source_valid):
        return support, 0
    ys_valid = ys[source_valid]
    xs_valid = xs[source_valid]
    depths = source_depth[source_valid]
    pixels = np.column_stack(
        [xs_valid.astype(np.float64) + 0.5, ys_valid.astype(np.float64) + 0.5, np.ones(len(depths))]
    )
    camera_xyz = (np.linalg.inv(source.camera.K()) @ pixels.T).T * depths[:, None]
    world_xyz = (source.image.R().T @ (camera_xyz - source.image.tvec).T).T
    target_xyz = (target.image.R() @ world_xyz.T).T + target.image.tvec
    projected_depth = target_xyz[:, 2]
    uvw = (target.camera.K() @ target_xyz.T).T
    with np.errstate(divide="ignore", invalid="ignore"):
        u = uvw[:, 0] / uvw[:, 2]
        v = uvw[:, 1] / uvw[:, 2]
    target_x = np.rint(u - 0.5).astype(np.int64)
    target_y = np.rint(v - 0.5).astype(np.int64)
    in_frame = (
        np.isfinite(u)
        & np.isfinite(v)
        & (projected_depth > 0.0)
        & (target_x >= 0)
        & (target_x < target.camera.width)
        & (target_y >= 0)
        & (target_y < target.camera.height)
    )
    indices = np.flatnonzero(in_frame)
    if len(indices) == 0:
        return support, int(len(depths))
    tx = target_x[indices]
    ty = target_y[indices]
    observed = np.asarray(target.mvs_depth, dtype=np.float64)[ty, tx]
    predicted = projected_depth[indices]
    depth_tolerance = np.maximum(
        parameters.target_depth_absolute_tolerance_m,
        parameters.target_depth_relative_tolerance * np.abs(predicted),
    )
    depth_ok = (
        np.isfinite(observed)
        & (observed > 0.0)
        & (np.abs(observed - predicted) <= depth_tolerance)
    )
    target_near_candidate = _dilate(
        np.asarray(target_candidate, dtype=bool),
        parameters.reprojection_mask_tolerance_px,
    )
    mask_ok = target_near_candidate[ty, tx]
    accepted = indices[depth_ok & mask_ok]
    support[ys_valid[accepted], xs_valid[accepted]] = True
    return support, int(len(depths))


def cross_view_consistent_masks(
    frames: Mapping[str, ViewFrame],
    candidates: Mapping[str, np.ndarray],
    parameters: CrossViewParameters = CrossViewParameters(),
) -> tuple[dict[str, np.ndarray], dict[str, CrossViewAudit]]:
    if set(frames) != set(candidates):
        raise MaskProducerError("frame and candidate view inventories differ")
    outputs: dict[str, np.ndarray] = {}
    audits: dict[str, CrossViewAudit] = {}
    for view_id in sorted(frames):
        frame = frames[view_id]
        candidate = np.asarray(candidates[view_id])
        if candidate.dtype != np.bool_ or candidate.shape != (
            frame.camera.height,
            frame.camera.width,
        ):
            raise MaskProducerError(f"{view_id}: candidate must be bool camera-sized HxW")
        neighbors = select_pose_neighbors(frame, frames, parameters)
        support_count = candidate.astype(np.uint16)
        valid_source_count = int(
            np.count_nonzero(candidate & np.isfinite(frame.mvs_depth) & (frame.mvs_depth > 0.0))
        )
        for neighbor in neighbors:
            supported, _ = _neighbor_support(
                frame,
                neighbor,
                candidate,
                candidates[neighbor.view_id],
                parameters,
            )
            support_count += supported.astype(np.uint16)
        if neighbors:
            consistent = candidate & (
                support_count >= parameters.minimum_support_views_including_source
            )
        else:
            consistent = np.zeros_like(candidate)
        outputs[view_id] = np.ascontiguousarray(consistent)
        audits[view_id] = CrossViewAudit(
            view_id=view_id,
            eligible_neighbor_ids=tuple(value.view_id for value in neighbors),
            raw_candidate_pixels=int(candidate.sum()),
            source_valid_depth_candidate_pixels=valid_source_count,
            consistent_candidate_pixels=int(consistent.sum()),
            no_valid_neighbor=not bool(neighbors),
        )
    return outputs, audits


def fuse_vision_roof_mask(
    raw_candidate: np.ndarray,
    consistent_candidate: np.ndarray,
    per_building_footprints: Sequence[np.ndarray],
    *,
    footprint_ids: Sequence[str] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Apply locked support and the per-building 5px/1px/0px core rule."""

    raw = np.asarray(raw_candidate)
    consistent = np.asarray(consistent_candidate)
    if raw.dtype != np.bool_ or consistent.dtype != np.bool_ or raw.shape != consistent.shape:
        raise MaskProducerError("raw/consistent candidates must be same-shape bool masks")
    if not per_building_footprints:
        raise MaskProducerError("fusion requires at least one projected footprint")
    if footprint_ids is None:
        ids = [f"index:{index}" for index in range(len(per_building_footprints))]
    else:
        ids = [str(value) for value in footprint_ids]
        if len(ids) != len(per_building_footprints):
            raise MaskProducerError("footprint IDs and masks must have the same length")
        if any(not value for value in ids) or len(set(ids)) != len(ids):
            raise MaskProducerError("footprint IDs must be non-empty and unique")
    footprint_union = np.zeros(raw.shape, dtype=bool)
    core_union = np.zeros(raw.shape, dtype=bool)
    erosion_used: list[int] = []
    core_audit: list[dict[str, Any]] = []
    empty_footprint_ids: list[str] = []
    one_px_fallback_ids: list[str] = []
    zero_px_fallback_ids: list[str] = []
    visible_buildings = 0
    for footprint_id, item in zip(ids, per_building_footprints, strict=True):
        footprint = np.asarray(item)
        if footprint.dtype != np.bool_ or footprint.shape != raw.shape:
            raise MaskProducerError("each projected footprint must be camera-sized bool HxW")
        if not footprint.any():
            empty_footprint_ids.append(footprint_id)
            continue
        visible_buildings += 1
        footprint_union |= footprint
        core = _erode(footprint, 5)
        radius = 5
        if not core.any():
            core = _erode(footprint, 1)
            radius = 1
            if core.any():
                one_px_fallback_ids.append(footprint_id)
        if not core.any():
            core = np.ascontiguousarray(footprint)
            radius = 0
            zero_px_fallback_ids.append(footprint_id)
        core_union |= core
        erosion_used.append(radius)
        core_audit.append(
            {
                "building_id": footprint_id,
                "footprint_pixels": int(footprint.sum()),
                "core_erosion_px": radius,
                "core_pixels": int(core.sum()),
            }
        )
    if visible_buildings == 0:
        raise MaskProducerError("view has no non-empty projected selected-building footprint")
    supported = consistent & _dilate(footprint_union, 5)
    fused = supported | core_union
    if not fused.any():
        raise MaskProducerError("locked fusion unexpectedly produced an empty plane mask")
    audit = {
        "sam_candidate_present": bool(raw.any()),
        "cross_view_consistent_candidate_present": bool(consistent.any()),
        "candidate_inside_dilated_footprint_present": bool(supported.any()),
        "core_erosion_px_used": sorted(set(erosion_used)),
        "core_erosion_by_visible_building": core_audit,
        "small_core_1px_fallback_count": len(one_px_fallback_ids),
        "small_core_1px_fallback_building_ids": one_px_fallback_ids,
        "small_core_0px_fallback_count": len(zero_px_fallback_ids),
        "small_core_0px_fallback_building_ids": zero_px_fallback_ids,
        "empty_projected_footprint_count": len(empty_footprint_ids),
        "empty_projected_footprint_building_ids": empty_footprint_ids,
        "core_only_fallback": not bool(supported.any()),
        "visible_selected_building_count": visible_buildings,
        "raw_candidate_pixels": int(raw.sum()),
        "cross_view_consistent_pixels": int(consistent.sum()),
        "supported_candidate_pixels": int(supported.sum()),
        "footprint_pixels": int(footprint_union.sum()),
        "core_pixels": int(core_union.sum()),
        "fused_pixels": int(fused.sum()),
        "footprint_overlap_fraction_of_fused": float(
            np.count_nonzero(fused & footprint_union) / max(1, int(fused.sum()))
        ),
    }
    return np.ascontiguousarray(fused), audit


def inference_attempt_audit(prior_inference_runs_started: int) -> dict[str, int]:
    """Return explicit cumulative accounting for one successful 04a attempt."""

    if type(prior_inference_runs_started) is not int or prior_inference_runs_started < 0:
        raise MaskProducerError(
            "prior_inference_runs_started must be an explicit nonnegative integer"
        )
    return {
        "prior_inference_runs_started": prior_inference_runs_started,
        "inference_runs_started": prior_inference_runs_started + 1,
        "inference_runs_successful": 1,
        "inference_runs_failed": prior_inference_runs_started,
    }


@dataclass(frozen=True)
class GroundedSamResult:
    mask: np.ndarray
    boxes_xyxy: np.ndarray
    scores: np.ndarray
    phrases: tuple[str, ...]


class GroundedSamRoofInference:
    """Pinned upstream wrapper; construction is offline and inference is explicit."""

    def __init__(
        self,
        lock: Mapping[str, Any],
        assets: Mapping[str, Path],
        *,
        device: str = "cuda",
    ) -> None:
        if set(assets) != set(EXPECTED_ASSETS):
            raise MaskProducerError("GroundedSAM wrapper requires the verified exact asset set")
        self.lock = lock
        self.assets = {key: Path(value) for key, value in assets.items()}
        self.device = device
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        dino_root = self.assets["groundingdino_source"]
        sam_root = self.assets["segment_anything_source"]
        # Receipt-verified source trees are immutable inputs.  Do not create
        # __pycache__ side effects that would invalidate their locked tree SHA.
        sys.dont_write_bytecode = True
        extension_glob = self.lock["runtime_dependency_gate"][
            "required_groundingdino_extension_glob"
        ]
        source_extensions = sorted(dino_root.glob(extension_glob))
        if source_extensions:
            dino_import_root: Path | None = dino_root
        else:
            dino_import_root = None
            evidence = self.lock["groundingdino_primary_source_evidence"]
            verified_installed_root: Path | None = None
            for value in sys.path:
                if not value or not Path(value).is_dir():
                    continue
                package_root = Path(value) / "groundingdino"
                model_path = package_root / "models/GroundingDINO/groundingdino.py"
                tokenizer_path = package_root / "util/get_tokenlizer.py"
                if (
                    any(package_root.glob("_C*.so"))
                    and model_path.is_file()
                    and sha256_file(model_path) == evidence["model_source_sha256"]
                    and tokenizer_path.is_file()
                    and sha256_file(tokenizer_path)
                    == evidence["tokenizer_loader_sha256"]
                ):
                    verified_installed_root = package_root
                    break
            if verified_installed_root is None:
                raise MaskProducerError(
                    "no exact-source-verified installed GroundingDINO _C runtime"
                )
        import_roots = [sam_root]
        if dino_import_root is not None:
            import_roots.append(dino_import_root)
        for path in import_roots:
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
        try:
            import torch
            from groundingdino.models import build_model
            import groundingdino.datasets.transforms as dino_transforms
            from groundingdino.util.slconfig import SLConfig
            from groundingdino.util.utils import clean_state_dict, get_phrases_from_posmap
            from segment_anything import SamPredictor, sam_model_registry
            from torchvision.ops import nms
        except ImportError as exc:  # pragma: no cover - only used in external runtime
            raise MaskProducerError(f"pinned GroundedSAM runtime import failed: {exc}") from exc
        config_path = dino_root / "groundingdino/config/GroundingDINO_SwinT_OGC.py"
        if not config_path.is_file():
            raise MaskProducerError(f"pinned GroundingDINO config is missing: {config_path}")
        args = SLConfig.fromfile(str(config_path))
        if getattr(args, "text_encoder_type", None) != "bert-base-uncased":
            raise MaskProducerError("official pinned GroundingDINO config no longer uses bert-base-uncased")
        # GroundingDINO passes this value to both tokenizer and BertModel.  A
        # verified local path avoids an unpinned Hub resolution at runtime.
        args.text_encoder_type = str(self.assets["bert_base_uncased"].resolve())
        args.device = self.device
        model = build_model(args)
        checkpoint = torch.load(
            self.assets["groundingdino_swint_ogc"],
            map_location="cpu",
            weights_only=False,
        )
        state = checkpoint.get("model", checkpoint)
        model.load_state_dict(clean_state_dict(state), strict=False)
        model.eval().to(self.device)
        transform = dino_transforms.Compose(
            [
                dino_transforms.RandomResize([800], max_size=1333),
                dino_transforms.ToTensor(),
                dino_transforms.Normalize(
                    [0.485, 0.456, 0.406],
                    [0.229, 0.224, 0.225],
                ),
            ]
        )
        sam = sam_model_registry["vit_h"](
            checkpoint=str(self.assets["sam_vit_h"])
        ).to(device=self.device)
        self._torch = torch
        self._nms = nms
        self._get_phrases = get_phrases_from_posmap
        self._model = model
        self._transform = transform
        self._predictor = SamPredictor(sam)
        self._loaded = True

    def __call__(self, rgb: np.ndarray) -> GroundedSamResult:
        self._load()
        image = np.asarray(rgb)
        if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
            raise MaskProducerError("GroundedSAM input must be uint8 RGB HxWx3")
        height, width = image.shape[:2]
        pil = PILImage.fromarray(image, mode="RGB")
        tensor, _ = self._transform(pil, None)
        caption = "roof."
        with self._torch.no_grad():
            output = self._model(
                tensor[None].to(self.device), captions=[caption]
            )
        logits = output["pred_logits"].sigmoid()[0].detach().cpu()
        boxes = output["pred_boxes"][0].detach().cpu()
        keep = logits.max(dim=1).values > 0.25
        logits = logits[keep]
        boxes = boxes[keep]
        if len(boxes) == 0:
            return GroundedSamResult(
                mask=np.zeros((height, width), dtype=bool),
                boxes_xyxy=np.empty((0, 4), dtype=np.float32),
                scores=np.empty(0, dtype=np.float32),
                phrases=(),
            )
        scores = logits.max(dim=1).values
        tokenized = self._model.tokenizer(caption)
        phrases = tuple(
            self._get_phrases(logit > 0.25, tokenized, self._model.tokenizer)
            for logit in logits
        )
        cx, cy, bw, bh = boxes.unbind(dim=1)
        xyxy = self._torch.stack(
            [cx - bw / 2.0, cy - bh / 2.0, cx + bw / 2.0, cy + bh / 2.0],
            dim=1,
        )
        scale = self._torch.tensor([width, height, width, height], dtype=xyxy.dtype)
        xyxy = xyxy * scale
        keep_indices = self._nms(xyxy, scores, 0.8)
        xyxy = xyxy[keep_indices]
        scores = scores[keep_indices]
        phrases = tuple(phrases[int(index)] for index in keep_indices.tolist())
        self._predictor.set_image(image, image_format="RGB")
        transformed_boxes = self._predictor.transform.apply_boxes_torch(
            xyxy.to(self.device), image.shape[:2]
        )
        with self._torch.no_grad():
            masks, _, _ = self._predictor.predict_torch(
                point_coords=None,
                point_labels=None,
                boxes=transformed_boxes,
                multimask_output=False,
            )
        union = masks[:, 0].any(dim=0).detach().cpu().numpy().astype(bool)
        return GroundedSamResult(
            mask=np.ascontiguousarray(union),
            boxes_xyxy=xyxy.detach().cpu().numpy().astype(np.float32),
            scores=scores.detach().cpu().numpy().astype(np.float32),
            phrases=phrases,
        )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _gml_id(element: ET.Element) -> str:
    for key, value in element.attrib.items():
        if _local_name(key) == "id":
            return str(value)
    return ""


def _parse_poslist(text: str) -> np.ndarray:
    values = np.asarray([float(value) for value in text.split()], dtype=np.float64)
    if values.size == 0 or values.size % 3:
        raise MaskProducerError("LoD2 gml:posList must contain XYZ triples")
    points = values.reshape(-1, 3)
    if len(points) >= 2 and np.allclose(points[0], points[-1]):
        points = points[:-1]
    return points


def _newell_normal(ring: np.ndarray) -> np.ndarray:
    normal = np.zeros(3, dtype=np.float64)
    for index, current in enumerate(ring):
        following = ring[(index + 1) % len(ring)]
        normal[0] += (current[1] - following[1]) * (current[2] + following[2])
        normal[1] += (current[2] - following[2]) * (current[0] + following[0])
        normal[2] += (current[0] - following[0]) * (current[1] + following[1])
    length = float(np.linalg.norm(normal))
    if length <= 1e-12:
        raise MaskProducerError("degenerate LoD2 surface ring")
    return normal / length


def _point_in_triangle_2d(
    point: np.ndarray, first: np.ndarray, second: np.ndarray, third: np.ndarray
) -> bool:
    denominator = (
        (second[1] - third[1]) * (first[0] - third[0])
        + (third[0] - second[0]) * (first[1] - third[1])
    )
    if abs(float(denominator)) < 1e-18:
        return False
    s_value = (
        (second[1] - third[1]) * (point[0] - third[0])
        + (third[0] - second[0]) * (point[1] - third[1])
    ) / denominator
    t_value = (
        (third[1] - first[1]) * (point[0] - third[0])
        + (first[0] - third[0]) * (point[1] - third[1])
    ) / denominator
    return s_value >= -1e-9 and t_value >= -1e-9 and s_value + t_value <= 1.0 + 1e-9


def _earclip(poly: np.ndarray) -> list[tuple[int, int, int]]:
    if len(poly) < 3:
        return []
    area = 0.5 * float(
        np.sum(
            poly[:, 0] * np.roll(poly[:, 1], -1)
            - np.roll(poly[:, 0], -1) * poly[:, 1]
        )
    )
    indices = list(range(len(poly)))
    if area < 0.0:
        indices.reverse()
    triangles: list[tuple[int, int, int]] = []
    guard = 0
    while len(indices) > 3 and guard < 100000:
        guard += 1
        found = False
        for cursor in range(len(indices)):
            i0 = indices[(cursor - 1) % len(indices)]
            i1 = indices[cursor]
            i2 = indices[(cursor + 1) % len(indices)]
            first, second, third = poly[i0], poly[i1], poly[i2]
            cross = (
                (second[0] - first[0]) * (third[1] - first[1])
                - (second[1] - first[1]) * (third[0] - first[0])
            )
            if cross <= 1e-12:
                continue
            if any(
                index not in (i0, i1, i2)
                and _point_in_triangle_2d(poly[index], first, second, third)
                for index in indices
            ):
                continue
            triangles.append((i0, i1, i2))
            del indices[cursor]
            found = True
            break
        if not found:
            break
    if len(indices) == 3:
        triangles.append(tuple(indices))
    elif len(indices) > 3:
        triangles.extend(
            (indices[0], indices[index], indices[index + 1])
            for index in range(1, len(indices) - 1)
        )
    return triangles


def triangulate_surface_ring(ring: np.ndarray) -> np.ndarray:
    value = np.asarray(ring, dtype=np.float64)
    if value.ndim != 2 or value.shape[1] != 3 or len(value) < 3:
        raise MaskProducerError("LoD2 surface ring must be Nx3 with N>=3")
    normal = _newell_normal(value)
    drop = int(np.argmax(np.abs(normal)))
    keep = [axis for axis in range(3) if axis != drop]
    indices = _earclip(value[:, keep])
    if not indices:
        raise MaskProducerError("LoD2 surface could not be triangulated")
    return np.asarray([[value[i], value[j], value[k]] for i, j, k in indices])


def triangulate_surface_polygon(rings: Sequence[np.ndarray]) -> np.ndarray:
    """Triangulate one planar 3D polygon, preserving any CityGML holes."""

    if not rings:
        raise MaskProducerError("LoD2 polygon has no rings")
    values = [np.asarray(ring, dtype=np.float64) for ring in rings]
    if any(ring.ndim != 2 or ring.shape[1] != 3 or len(ring) < 3 for ring in values):
        raise MaskProducerError("every LoD2 polygon ring must be Nx3 with N>=3")
    normal = _newell_normal(values[0])
    drop = int(np.argmax(np.abs(normal)))
    keep = [axis for axis in range(3) if axis != drop]
    exterior_2d = values[0][:, keep]
    holes_2d = [ring[:, keep] for ring in values[1:]]
    polygon = Polygon(exterior_2d, holes_2d)
    if polygon.is_empty or not polygon.is_valid or polygon.area <= 1e-12:
        raise MaskProducerError("LoD2 polygon with holes is empty or invalid")
    triangles_2d: list[np.ndarray] = []
    if not holes_2d:
        indices = _earclip(exterior_2d)
        if not indices:
            raise MaskProducerError("LoD2 exterior ring could not be triangulated")
        # Preserve the source XYZ exactly when no new intersection vertex is
        # needed.  Some official faces carry millimetre-scale quantization
        # non-planarity which must not be silently flattened.
        return np.asarray(
            [[values[0][i], values[0][j], values[0][k]] for i, j, k in indices],
            dtype=np.float64,
        )
    else:
        # GEOS Delaunay triangles tile the convex hull.  Intersecting each with
        # exterior-minus-holes yields non-overlapping simple polygon pieces;
        # ear-clipping those pieces preserves concavities and interior rings.
        def polygon_parts(geometry: Any) -> list[Any]:
            if geometry.is_empty:
                return []
            if geometry.geom_type == "Polygon":
                return [geometry]
            if geometry.geom_type in {"MultiPolygon", "GeometryCollection"}:
                output: list[Any] = []
                for part in geometry.geoms:
                    output.extend(polygon_parts(part))
                return output
            return []

        for delaunay in shapely_triangulate(polygon):
            clipped = delaunay.intersection(polygon)
            for part in polygon_parts(clipped):
                if part.area <= 1e-12:
                    continue
                if len(part.interiors):
                    raise MaskProducerError(
                        "LoD2 hole triangulation produced a nested interior piece"
                    )
                coordinates = np.asarray(part.exterior.coords, dtype=np.float64)[:-1]
                indices = _earclip(coordinates)
                triangles_2d.extend(
                    np.asarray([coordinates[i], coordinates[j], coordinates[k]])
                    for i, j, k in indices
                )
    covered_area = float(
        sum(
            0.5
            * abs(
                (triangle[1, 0] - triangle[0, 0])
                * (triangle[2, 1] - triangle[0, 1])
                - (triangle[1, 1] - triangle[0, 1])
                * (triangle[2, 0] - triangle[0, 0])
            )
            for triangle in triangles_2d
        )
    )
    if not math.isclose(covered_area, float(polygon.area), rel_tol=1e-8, abs_tol=1e-8):
        raise MaskProducerError(
            "LoD2 constrained polygon triangulation did not preserve exterior-minus-holes area"
        )
    all_points = np.vstack(values)
    design = np.column_stack(
        [all_points[:, keep[0]], all_points[:, keep[1]], np.ones(len(all_points))]
    )
    coefficients = np.linalg.lstsq(design, all_points[:, drop], rcond=None)[0]
    residual = np.abs(design @ coefficients - all_points[:, drop])
    maximum_residual = float(residual.max(initial=0.0))
    if maximum_residual > 1e-2:
        raise MaskProducerError(
            f"LoD2 semantic polygon is not planar within 1 cm: {maximum_residual:.6f} m"
        )
    triangles_3d: list[np.ndarray] = []
    for xy in triangles_2d:
        triangle = np.empty((3, 3), dtype=np.float64)
        triangle[:, keep[0]] = xy[:, 0]
        triangle[:, keep[1]] = xy[:, 1]
        triangle[:, drop] = (
            coefficients[0] * xy[:, 0]
            + coefficients[1] * xy[:, 1]
            + coefficients[2]
        )
        triangles_3d.append(triangle)
    return np.asarray(triangles_3d, dtype=np.float64)


def _polygon_rings_from_gml(polygon: ET.Element) -> list[np.ndarray]:
    exterior: np.ndarray | None = None
    interiors: list[np.ndarray] = []
    for boundary in polygon.iter():
        kind = _local_name(boundary.tag)
        if kind not in {"exterior", "interior"}:
            continue
        text = next(
            (
                item.text
                for item in boundary.iter()
                if _local_name(item.tag) == "posList" and item.text
            ),
            None,
        )
        if text is None:
            continue
        ring = _parse_poslist(text)
        if kind == "exterior":
            if exterior is not None:
                raise MaskProducerError("LoD2 polygon contains multiple exterior rings")
            exterior = ring
        else:
            interiors.append(ring)
    if exterior is None:
        fallback = next(
            (
                item.text
                for item in polygon.iter()
                if _local_name(item.tag) == "posList" and item.text
            ),
            None,
        )
        if fallback is None:
            return []
        exterior = _parse_poslist(fallback)
    return [exterior, *interiors]


@dataclass(frozen=True)
class LoD2TriangleScene:
    triangles_local: np.ndarray
    triangle_class: np.ndarray
    triangle_selected_building: np.ndarray
    selected_building_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        triangles = np.asarray(self.triangles_local)
        classes = np.asarray(self.triangle_class)
        selected = np.asarray(self.triangle_selected_building)
        if triangles.ndim != 3 or triangles.shape[1:] != (3, 3) or len(triangles) == 0:
            raise MaskProducerError("LoD2 triangle scene must contain Tx3x3 triangles")
        if classes.shape != (len(triangles),) or selected.shape != (len(triangles),):
            raise MaskProducerError("LoD2 triangle metadata length mismatch")


def load_lod2_citygml_scene(
    gml_paths: Sequence[str | Path],
    selected_building_ids: Sequence[str],
    *,
    world_offset: Sequence[float] = (690953.0, 5336071.0, 604.0),
    orthometric_geoid_m: float = 45.7,
    aoi_xy_local: Sequence[float] | None = None,
) -> LoD2TriangleScene:
    """Load semantic LoD2 geometry internally for 04b raycasting.

    All roof/wall/ground faces in the requested AOI remain occluders.  Only a
    hit on a selected-building RoofSurface becomes ``True`` in the public mask.
    """

    selected_aliases: set[str] = set()
    for value in selected_building_ids:
        text = str(value)
        selected_aliases.add(text)
        selected_aliases.add(text.removeprefix("DEBY_LOD2_"))
        selected_aliases.add(f"DEBY_LOD2_{text.removeprefix('DEBY_LOD2_')}")
    offset = np.asarray(world_offset, dtype=np.float64)
    if offset.shape != (3,) or not np.isfinite(offset).all():
        raise MaskProducerError("world_offset must be a finite XYZ vector")
    triangles: list[np.ndarray] = []
    classes: list[int] = []
    selected_flags: list[bool] = []
    selected_seen: set[str] = set()
    selected_roof_seen: set[str] = set()
    for path in sorted(Path(value) for value in gml_paths):
        if not path.is_file():
            raise MaskProducerError(f"LoD2 CityGML is missing: {path}")
        for _event, building in ET.iterparse(path, events=("end",)):
            if _local_name(building.tag) != "Building":
                continue
            building_id = _gml_id(building)
            short = building_id.removeprefix("DEBY_LOD2_")
            is_selected = building_id in selected_aliases or short in selected_aliases
            if is_selected:
                selected_seen.add(short)
            for surface in building.iter():
                class_id = SURFACE_CLASS.get(_local_name(surface.tag))
                if class_id is None:
                    continue
                polygon_elements = [
                    item for item in surface.iter() if _local_name(item.tag) == "Polygon"
                ]
                if not polygon_elements:
                    polygon_elements = [surface]
                for polygon in polygon_elements:
                    world_rings = _polygon_rings_from_gml(polygon)
                    if not world_rings:
                        continue
                    local_rings: list[np.ndarray] = []
                    for world_ring in world_rings:
                        local_ring = world_ring.copy()
                        local_ring[:, 0] -= offset[0]
                        local_ring[:, 1] -= offset[1]
                        local_ring[:, 2] += float(orthometric_geoid_m) - offset[2]
                        local_rings.append(local_ring)
                    if aoi_xy_local is not None:
                        x0, y0, x1, y1 = map(float, aoi_xy_local)
                        centre = local_rings[0][:, :2].mean(axis=0)
                        if not (x0 <= centre[0] <= x1 and y0 <= centre[1] <= y1):
                            continue
                    surface_triangles = triangulate_surface_polygon(local_rings)
                    triangles.extend(surface_triangles)
                    classes.extend([class_id] * len(surface_triangles))
                    selected_flags.extend([is_selected] * len(surface_triangles))
                    if is_selected and class_id == SURFACE_CLASS["RoofSurface"]:
                        selected_roof_seen.add(short)
            building.clear()
    wanted_short = {
        str(value).removeprefix("DEBY_LOD2_") for value in selected_building_ids
    }
    missing = sorted(wanted_short - selected_seen)
    if missing:
        raise MaskProducerError(f"selected LoD2 buildings missing from CityGML: {missing}")
    missing_roof = sorted(wanted_short - selected_roof_seen)
    if missing_roof:
        raise MaskProducerError(
            f"selected LoD2 RoofSurface missing from raycast AOI: {missing_roof}"
        )
    return LoD2TriangleScene(
        triangles_local=np.asarray(triangles, dtype=np.float32),
        triangle_class=np.asarray(classes, dtype=np.uint8),
        triangle_selected_building=np.asarray(selected_flags, dtype=bool),
        selected_building_ids=tuple(sorted(wanted_short)),
    )


def _camera_ray_chunk(
    camera: Camera,
    image: Image,
    start: int,
    stop: int,
) -> np.ndarray:
    width = int(camera.width)
    flat = np.arange(start, stop, dtype=np.int64)
    y = flat // width
    x = flat - y * width
    pixels = np.column_stack(
        [x.astype(np.float64) + 0.5, y.astype(np.float64) + 0.5, np.ones(len(flat))]
    )
    directions_camera = (np.linalg.inv(camera.K()) @ pixels.T).T
    directions_world = directions_camera @ image.R()
    directions_world /= np.linalg.norm(directions_world, axis=1, keepdims=True) + 1e-12
    centre = -image.R().T @ image.tvec
    origins = np.broadcast_to(centre, directions_world.shape)
    return np.ascontiguousarray(
        np.column_stack([origins, directions_world]), dtype=np.float32
    )


def raycast_lod2_roof_bool_mask(
    scene_data: LoD2TriangleScene,
    camera: Camera,
    image: Image,
    *,
    ray_chunk_size: int = 1_000_000,
) -> np.ndarray:
    """Return only the selected-building RoofSurface hit mask (bool HxW)."""

    try:
        import open3d as o3d
    except ImportError as exc:  # pragma: no cover - Docker includes open3d
        raise MaskProducerError("04b raycasting requires pinned Docker open3d") from exc
    triangles = np.asarray(scene_data.triangles_local, dtype=np.float32)
    vertices = triangles.reshape(-1, 3)
    indices = np.arange(len(vertices), dtype=np.uint32).reshape(-1, 3)
    ray_scene = o3d.t.geometry.RaycastingScene()
    ray_scene.add_triangles(o3d.core.Tensor(vertices), o3d.core.Tensor(indices))
    total = int(camera.width) * int(camera.height)
    output = np.zeros(total, dtype=bool)
    invalid = o3d.t.geometry.RaycastingScene.INVALID_ID
    positive_triangle = (
        (np.asarray(scene_data.triangle_class) == SURFACE_CLASS["RoofSurface"])
        & np.asarray(scene_data.triangle_selected_building, dtype=bool)
    )
    for start in range(0, total, ray_chunk_size):
        stop = min(total, start + ray_chunk_size)
        rays = _camera_ray_chunk(camera, image, start, stop)
        primitive = ray_scene.cast_rays(o3d.core.Tensor(rays))["primitive_ids"].numpy()
        hit = primitive != invalid
        local = np.zeros(stop - start, dtype=bool)
        local[hit] = positive_triangle[primitive[hit].astype(np.int64)]
        output[start:stop] = local
    return np.ascontiguousarray(output.reshape(camera.height, camera.width))


def _pop_path(payload: dict[str, Any], dotted_path: str) -> Any:
    parts = dotted_path.split(".")
    cursor: dict[str, Any] = payload
    for part in parts[:-1]:
        value = cursor.get(part)
        if not isinstance(value, dict):
            raise MaskProducerError(f"controlled-pair config lacks {dotted_path}")
        cursor = value
    if parts[-1] not in cursor:
        raise MaskProducerError(f"controlled-pair config lacks {dotted_path}")
    return cursor.pop(parts[-1])


def validate_04a_04b_control_pair(
    config_04a: Mapping[str, Any],
    config_04b: Mapping[str, Any],
    *,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    """Hard-fail unless source/path/SHA are the pair's only differences."""

    left = copy.deepcopy(dict(config_04a))
    right = copy.deepcopy(dict(config_04b))
    left_values = {path: _pop_path(left, path) for path in CONTROLLED_PAIR_PATHS}
    right_values = {path: _pop_path(right, path) for path in CONTROLLED_PAIR_PATHS}
    if canonical_json_bytes(left) != canonical_json_bytes(right):
        raise MaskProducerError(
            "04a/04b resolved training configs differ outside plane-mask source/path/hash"
        )
    if left_values["plane_region_mask.source"] != MaskSource.VISION_GROUNDEDSAM_ROOF.value:
        raise MaskProducerError("04a plane mask source is not the locked vision source")
    if right_values["plane_region_mask.source"] != MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND.value:
        raise MaskProducerError("04b plane mask source is not the locked GT upper-bound source")
    for label, values in (("04a", left_values), ("04b", right_values)):
        if not SHA256_RE.fullmatch(str(values["plane_region_mask.manifest_sha256"])):
            raise MaskProducerError(f"{label} plane mask manifest SHA256 is malformed")
    result: dict[str, Any] = {
        "controlled_pair_equal_except": list(CONTROLLED_PAIR_PATHS),
        "04a": left_values,
        "04b": right_values,
    }
    if repository_root is None:
        return result
    root = Path(repository_root)
    manifests: dict[str, BinaryMaskSet] = {}
    for label, values in (("04a", left_values), ("04b", right_values)):
        manifest_path = Path(str(values["plane_region_mask.manifest_path"]))
        if not manifest_path.is_absolute():
            manifest_path = root / manifest_path
        if sha256_file(manifest_path) != values["plane_region_mask.manifest_sha256"]:
            raise MaskProducerError(f"{label} plane mask manifest SHA mismatch")
        masks = BinaryMaskSet(manifest_path)
        if masks.purpose is not MaskPurpose.PLANE_REGION:
            raise MaskProducerError(f"{label} manifest is not a plane-region mask set")
        manifests[label] = masks
    if manifests["04a"].source is not MaskSource.VISION_GROUNDEDSAM_ROOF:
        raise MaskProducerError("04a manifest source mismatch")
    if manifests["04b"].source is not MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND:
        raise MaskProducerError("04b manifest source mismatch")
    inventory_a = {
        view_id: record.shape for view_id, record in manifests["04a"].records.items()
    }
    inventory_b = {
        view_id: record.shape for view_id, record in manifests["04b"].records.items()
    }
    if inventory_a != inventory_b:
        raise MaskProducerError("04a/04b mask view inventories or shapes differ")
    result["view_inventory"] = {
        "count": len(inventory_a),
        "view_ids": sorted(inventory_a),
    }
    return result

"""C3-only GroundedSAM runtime and offline asset contract.

This module intentionally does not inherit the historical pilot lock or receipt.
It verifies a new C3 receipt against the live bytes, including exact Git HEAD/tree
attestation for both source checkouts.  Network access is available only through
the explicit fetch entry point; inference uses the read-only verifier.
"""

from __future__ import annotations

from datetime import datetime, timezone
import ctypes
import errno
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from .pilot_plane_mask_producer import (
    MaskProducerError,
    _assert_cache_target_safe,
    _download_file,
    _fetch_source_checkout,
    _git_tracked_source_attestation,
    _tree_receipt,
    canonical_json_bytes,
    sha256_file,
)


CONTRACT_SCHEMA = "jointbuildgs.c3_image_semantic_runtime.v1"
RECEIPT_SCHEMA = "jointbuildgs.c3_image_semantic_asset_receipt.v1"
EXPECTED_ASSETS = (
    "groundingdino_source",
    "segment_anything_source",
    "groundingdino_swint_ogc",
    "sam_vit_h",
    "bert_base_uncased",
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")

BASE_IMAGE_TAG = "jointbuildgs:dev"
BASE_IMAGE_ID = "sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
TARGET_IMAGE_TAG = "jointbuildgs:c3-groundedsam-v1"
TARGET_IMAGE_ID = "sha256:7217f813ecf7f690816341bb9cdf6fd80928e635d7edb1ce420ae2561b2c7b79"
REQUIREMENTS_SHA256 = "399b3860c291e6685bc63c3704bf34b1a6b1ef9a5c59e1ede6e583433d36a063"
DINO_REVISION = "856dde20aee659246248e20734ef9ba5214f5e44"
SAM_REVISION = "dca509fe793f601edb92606367a655c15ac00fdf"
BERT_REVISION = "86b5e0934494bd15c9632b12f734a8a67f723594"

EXPECTED_DISTRIBUTIONS = {
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


class C3AssetError(MaskProducerError):
    """A C3 runtime or asset identity failed closed."""


def _publish_directory_noreplace(staging: Path, target: Path) -> None:
    """Atomically publish a directory and never replace a raced target."""

    if os.name != "posix":
        raise C3AssetError("atomic no-clobber asset publication requires POSIX")
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise C3AssetError("renameat2 is unavailable; refusing non-atomic asset publication")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(-100, os.fsencode(staging), -100, os.fsencode(target), 1)
    if result == 0:
        return
    error = ctypes.get_errno()
    if error in (errno.EEXIST, errno.ENOTEMPTY):
        raise C3AssetError("C3 cache target appeared during atomic publication")
    raise C3AssetError(f"atomic asset publication failed: {os.strerror(error)}")


def _safe_relative(value: Any, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise C3AssetError(f"{field} must be a non-empty relative path")
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise C3AssetError(f"{field} is unsafe")
    return path


def _require_exact(value: Any, expected: Any, field: str) -> None:
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        raise C3AssetError(f"C3 runtime contract changed: {field}")


def load_c3_contract(path: str | Path) -> dict[str, Any]:
    """Load the new C3 contract and reject historical or partially repinned locks."""

    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise C3AssetError("C3 runtime contract must be an object")
    required_top = {
        "schema",
        "status",
        "runtime_environment",
        "runtime_dependency_gate",
        "runtime_assets",
        "groundingdino_primary_source_evidence",
        "asset_receipt",
        "semantic_boundary",
        "learning_runs_started",
        "inference_runs_started",
        "scientific_verdict",
    }
    if set(value) != required_top or value.get("schema") != CONTRACT_SCHEMA:
        raise C3AssetError("C3 runtime contract schema or fields differ")
    if (
        value.get("status") != "PINNED_REMOTE_RUNTIME_BUILT_NOT_EXECUTED"
        or value.get("scientific_verdict") is not None
        or value.get("learning_runs_started") != 0
        or value.get("inference_runs_started") != 0
    ):
        raise C3AssetError("C3 contract status/run counters/scientific_verdict differ")

    runtime = value["runtime_environment"]
    expected_runtime = {
        "base_docker_image_tag": BASE_IMAGE_TAG,
        "base_docker_image_id": BASE_IMAGE_ID,
        "docker_image_tag": TARGET_IMAGE_TAG,
        "docker_image_id": TARGET_IMAGE_ID,
        "runtime_requirements_path": "/opt/jointbuildgs/p1w_groundedsam/requirements-runtime.txt",
        "runtime_requirements_sha256": REQUIREMENTS_SHA256,
        "groundingdino_source_root": "/opt/jointbuildgs/p1w_groundedsam/GroundingDINO",
        "segment_anything_source_root": "/opt/jointbuildgs/p1w_groundedsam/segment-anything",
    }
    _require_exact(runtime, expected_runtime, "runtime_environment")

    gate = value["runtime_dependency_gate"]
    if (
        gate.get("required_python_version") != "3.11.15"
        or gate.get("required_distribution_versions") != EXPECTED_DISTRIBUTIONS
        or gate.get("required_groundingdino_extension_glob") != "groundingdino/_C*.so"
        or gate.get("compiled_cuda_arch") != "8.6"
        or gate.get("compiled_torch_cuda") != "12.1"
        or set(gate) != {
            "required_python_version",
            "required_distribution_versions",
            "required_groundingdino_extension_glob",
            "compiled_cuda_arch",
            "compiled_torch_cuda",
        }
    ):
        raise C3AssetError("C3 runtime dependency gate differs")

    assets = value["runtime_assets"]
    if not isinstance(assets, dict) or tuple(assets) != EXPECTED_ASSETS:
        raise C3AssetError("C3 asset inventory/order differs")
    expected_sources = {
        "groundingdino_source": (
            "https://github.com/IDEA-Research/GroundingDINO.git",
            DINO_REVISION,
            "sources/GroundingDINO",
        ),
        "segment_anything_source": (
            "https://github.com/facebookresearch/segment-anything.git",
            SAM_REVISION,
            "sources/segment-anything",
        ),
    }
    for artifact_id, (repository, revision, relative) in expected_sources.items():
        _require_exact(
            assets[artifact_id],
            {
                "kind": "source_tree",
                "repository": repository,
                "revision": revision,
                "cache_relative_path": relative,
            },
            artifact_id,
        )
    expected_files = {
        "groundingdino_swint_ogc": (
            "https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth",
            "weights/groundingdino_swint_ogc.pth",
            693_997_677,
            "3b3ca2563c77c69f651d7bd133e97139c186df06231157a64c507099c52bc799",
        ),
        "sam_vit_h": (
            "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth",
            "weights/sam_vit_h_4b8939.pth",
            2_564_550_879,
            "a7bf3b02f3ebf1267aba913ff637d9a2d5c33d3173bb679e46d9f338c26f262e",
        ),
    }
    for artifact_id, (url, relative, size, digest) in expected_files.items():
        _require_exact(
            assets[artifact_id],
            {
                "kind": "file",
                "url": url,
                "cache_relative_path": relative,
                "size_bytes": size,
                "sha256": digest,
            },
            artifact_id,
        )
    _require_exact(
        assets["bert_base_uncased"],
        {
            "kind": "huggingface_snapshot",
            "repository": "google-bert/bert-base-uncased",
            "revision": BERT_REVISION,
            "cache_relative_path": "snapshots/google-bert_bert-base-uncased_86b5e0934494bd15",
            "required_files": ["config.json", "tokenizer_config.json", "tokenizer.json", "vocab.txt"],
            "weight_file": "model.safetensors",
        },
        "bert_base_uncased",
    )

    _require_exact(
        value["groundingdino_primary_source_evidence"],
        {
            "config_sha256": "172e80017f9395668a9cb5d1b8bd9d061c0e360471c6ed673c83b69bb14399f1",
            "model_source_sha256": "cdfb48d5b15d6b98f3d2002f59ae4730740a1ecfbaeba324f6840c5e4666a5b8",
            "tokenizer_loader_sha256": "bedc47db390249eb2230c2031b114d1d5f470ed6dbc1d3905e97e742289cb3b3",
            "locked_text_encoder": "bert-base-uncased",
        },
        "groundingdino_primary_source_evidence",
    )
    _require_exact(
        value["asset_receipt"],
        {
            "schema": RECEIPT_SCHEMA,
            "required_artifact_ids": list(EXPECTED_ASSETS),
            "network_during_inference": False,
            "symlinks_allowed": False,
            "source_head_tree_clean_required": True,
        },
        "asset_receipt",
    )
    _require_exact(
        value["semantic_boundary"],
        {
            "image_count": 937,
            "allowed_inputs": ["RGB_IMAGE_BYTES"],
            "prohibited_inputs": ["POSE", "FOOTPRINT", "BUILDING_ID", "LOD1", "LOD2", "UAS", "ALS", "GT"],
            "publication": "ADD_ONCE_ATOMIC_WITH_PER_IMAGE_RESUME",
        },
        "semantic_boundary",
    )
    return value


def _resolve_asset(root: Path, relative_value: Any, field: str) -> Path:
    relative = _safe_relative(relative_value, field)
    path = root.joinpath(*relative.parts)
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (FileNotFoundError, ValueError) as exc:
        raise C3AssetError(f"asset is missing or escapes cache: {field}") from exc
    return path


def _source_evidence(contract: Mapping[str, Any], dino_root: Path) -> None:
    evidence = contract["groundingdino_primary_source_evidence"]
    expected = {
        "groundingdino/config/GroundingDINO_SwinT_OGC.py": evidence["config_sha256"],
        "groundingdino/models/GroundingDINO/groundingdino.py": evidence["model_source_sha256"],
        "groundingdino/util/get_tokenlizer.py": evidence["tokenizer_loader_sha256"],
    }
    for relative, digest in expected.items():
        path = dino_root / relative
        if not path.is_file() or path.is_symlink() or sha256_file(path) != digest:
            raise C3AssetError(f"GroundingDINO primary source differs: {relative}")


def verify_c3_asset_receipt(
    contract: Mapping[str, Any],
    contract_path: str | Path,
    cache_root: str | Path,
    receipt_path: str | Path,
) -> dict[str, Path]:
    """Verify the new C3 receipt and every live asset byte without network access."""

    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA:
        raise C3AssetError(f"asset receipt schema must be {RECEIPT_SCHEMA}")
    if (
        receipt.get("contract_sha256") != sha256_file(contract_path)
        or receipt.get("runtime_environment") != contract.get("runtime_environment")
        or receipt.get("network_accessed") is not True
        or receipt.get("learning_runs_started") != 0
        or receipt.get("inference_runs_started") != 0
        or receipt.get("scientific_verdict") is not None
    ):
        raise C3AssetError("asset receipt contract/runtime/run metadata differs")
    rows = receipt.get("artifacts")
    if not isinstance(rows, dict) or tuple(rows) != EXPECTED_ASSETS:
        raise C3AssetError("asset receipt inventory/order differs")
    root = Path(cache_root)
    if not root.is_dir() or root.is_symlink():
        raise C3AssetError("asset cache root must be a real directory")
    locked_assets = contract["runtime_assets"]
    resolved: dict[str, Path] = {}
    for artifact_id in EXPECTED_ASSETS:
        locked = locked_assets[artifact_id]
        row = rows[artifact_id]
        if not isinstance(row, dict):
            raise C3AssetError(f"invalid receipt row: {artifact_id}")
        if (
            row.get("kind") != locked["kind"]
            or row.get("relative_path") != locked["cache_relative_path"]
        ):
            raise C3AssetError(f"asset kind/path differs: {artifact_id}")
        path = _resolve_asset(root, row["relative_path"], artifact_id)
        if locked["kind"] == "file":
            if not path.is_file() or path.is_symlink():
                raise C3AssetError(f"asset must be a regular file: {artifact_id}")
            if row.get("source") != locked["url"]:
                raise C3AssetError(f"asset URL differs: {artifact_id}")
            size, digest = path.stat().st_size, sha256_file(path)
            if size != locked["size_bytes"] or digest != locked["sha256"]:
                raise C3AssetError(f"locked model weight differs: {artifact_id}")
        else:
            if (
                row.get("source") != locked["repository"]
                or row.get("revision") != locked["revision"]
            ):
                raise C3AssetError(f"source/revision differs: {artifact_id}")
            if locked["kind"] == "source_tree":
                attestation = _git_tracked_source_attestation(
                    path, locked["revision"], include_root=False
                )
                status = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(path),
                        "status",
                        "--porcelain",
                        "--untracked-files=all",
                    ],
                    check=False,
                    text=True,
                    capture_output=True,
                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                )
                if status.returncode != 0 or status.stdout:
                    raise C3AssetError(
                        f"source checkout contains untracked or dirty files: {artifact_id}"
                    )
                size = attestation["tracked_size_bytes"]
                digest = attestation["tracked_files_sha256"]
                if canonical_json_bytes(row.get("git")) != canonical_json_bytes(attestation):
                    raise C3AssetError(f"source HEAD/tree/clean attestation differs: {artifact_id}")
            elif locked["kind"] == "huggingface_snapshot":
                size, digest, _entries = _tree_receipt(path)
                required = [*locked["required_files"], locked["weight_file"]]
                for filename in required:
                    target = path / filename
                    if not target.is_file() or target.is_symlink():
                        raise C3AssetError(f"BERT snapshot lacks locked file: {filename}")
        if row.get("size_bytes") != size or row.get("sha256") != digest:
            raise C3AssetError(f"asset live size/SHA differs from receipt: {artifact_id}")
        if not SHA256_RE.fullmatch(str(digest)):
            raise C3AssetError(f"asset SHA-256 is malformed: {artifact_id}")
        resolved[artifact_id] = path
    _source_evidence(contract, resolved["groundingdino_source"])
    return resolved


def _receipt_row(
    locked: Mapping[str, Any], path: Path, staging_root: Path
) -> dict[str, Any]:
    git_attestation: dict[str, Any] | None = None
    if locked["kind"] == "source_tree":
        git_attestation = _git_tracked_source_attestation(
            path, locked["revision"], include_root=False
        )
        status = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain", "--untracked-files=all"],
            check=False,
            text=True,
            capture_output=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if status.returncode != 0 or status.stdout:
            raise C3AssetError("fresh source checkout contains untracked or dirty files")
        size = git_attestation["tracked_size_bytes"]
        digest = git_attestation["tracked_files_sha256"]
    elif path.is_dir():
        size, digest, _entries = _tree_receipt(path)
    elif path.is_file() and not path.is_symlink():
        size, digest = path.stat().st_size, sha256_file(path)
    else:
        raise C3AssetError("fresh asset is not a regular file/tree")
    row: dict[str, Any] = {
        "kind": locked["kind"],
        "relative_path": path.relative_to(staging_root).as_posix(),
        "source": locked.get("repository", locked.get("url")),
        "size_bytes": size,
        "sha256": digest,
    }
    if "revision" in locked:
        row["revision"] = locked["revision"]
    if git_attestation is not None:
        row["git"] = git_attestation
    return row


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


def fetch_c3_asset_bundle(
    contract: Mapping[str, Any],
    contract_path: str | Path,
    cache_root: str | Path,
    repository_root: str | Path,
) -> dict[str, Any]:
    """Explicit network fetch with add-once, verify-before-publish semantics."""

    target = Path(cache_root)
    repository = Path(repository_root)
    _assert_cache_target_safe(target, repository)
    receipt_name = "asset_receipt.json"
    if target.exists():
        receipt_path = target / receipt_name
        if not target.is_dir() or target.is_symlink() or not receipt_path.is_file():
            raise C3AssetError("existing C3 cache is not a complete receipted bundle")
        verify_c3_asset_receipt(contract, contract_path, target, receipt_path)
        return {
            "reused_existing": True,
            "receipt_path": str(receipt_path),
            "receipt": json.loads(receipt_path.read_text(encoding="utf-8")),
        }

    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging.", dir=parent))
    try:
        assets = contract["runtime_assets"]
        for artifact_id in ("groundingdino_source", "segment_anything_source"):
            locked = assets[artifact_id]
            _fetch_source_checkout(
                staging / locked["cache_relative_path"],
                locked["repository"],
                locked["revision"],
            )
        for artifact_id in ("groundingdino_swint_ogc", "sam_vit_h"):
            locked = assets[artifact_id]
            destination = staging / locked["cache_relative_path"]
            _download_file(locked["url"], destination)
        bert = assets["bert_base_uncased"]
        bert_root = staging / bert["cache_relative_path"]
        for filename in [*bert["required_files"], bert["weight_file"]]:
            _download_file(
                f"https://huggingface.co/{bert['repository']}/resolve/{bert['revision']}/{filename}",
                bert_root / filename,
            )
        rows = {
            artifact_id: _receipt_row(
                assets[artifact_id],
                staging / assets[artifact_id]["cache_relative_path"],
                staging,
            )
            for artifact_id in EXPECTED_ASSETS
        }
        for artifact_id in ("groundingdino_swint_ogc", "sam_vit_h"):
            if (
                rows[artifact_id]["size_bytes"] != assets[artifact_id]["size_bytes"]
                or rows[artifact_id]["sha256"] != assets[artifact_id]["sha256"]
            ):
                raise C3AssetError(f"downloaded model weight differs: {artifact_id}")
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "contract_sha256": sha256_file(contract_path),
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "runtime_environment": dict(contract["runtime_environment"]),
            "network_accessed": True,
            "learning_runs_started": 0,
            "inference_runs_started": 0,
            "scientific_verdict": None,
            "fresh_fetch_hash_policy": {
                "model_weight_full_hash_passes": 1,
                "source_tracked_file_hash_passes": 1,
                "bert_snapshot_file_hash_passes": 1,
                "post_receipt_rehash_before_atomic_publish": 0,
            },
            "artifacts": rows,
        }
        receipt_path = staging / receipt_name
        _write_json_atomic(receipt_path, receipt)
        _publish_directory_noreplace(staging, target)
        directory_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return {
            "reused_existing": False,
            "receipt_path": str(target / receipt_name),
            "receipt": receipt,
        }
    except Exception:
        if staging.exists() and staging.parent.resolve() == parent.resolve():
            shutil.rmtree(staging)
        raise


def audit_c3_runtime(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed unless the running container matches the C3 image contents."""

    runtime = contract["runtime_environment"]
    gate = contract["runtime_dependency_gate"]
    if platform.python_version() != gate["required_python_version"]:
        raise C3AssetError("C3 Python version differs")
    versions: dict[str, str] = {}
    for distribution, expected in gate["required_distribution_versions"].items():
        try:
            actual = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError as exc:
            raise C3AssetError(f"required distribution is missing: {distribution}") from exc
        if actual != expected:
            raise C3AssetError(f"runtime distribution differs: {distribution}")
        versions[distribution] = actual
    requirements = Path(runtime["runtime_requirements_path"])
    if (
        not requirements.is_file()
        or requirements.is_symlink()
        or sha256_file(requirements) != runtime["runtime_requirements_sha256"]
    ):
        raise C3AssetError("runtime requirements bytes differ")
    dino = Path(runtime["groundingdino_source_root"])
    sam = Path(runtime["segment_anything_source_root"])
    source_attestations = {
        "groundingdino": _git_tracked_source_attestation(
            dino, DINO_REVISION, include_root=False
        ),
        "segment_anything": _git_tracked_source_attestation(
            sam, SAM_REVISION, include_root=False
        ),
    }
    extensions = list(dino.glob(gate["required_groundingdino_extension_glob"]))
    if len(extensions) != 1 or not extensions[0].is_file() or extensions[0].is_symlink():
        raise C3AssetError("runtime must contain exactly one regular GroundingDINO extension")
    extension = extensions[0]
    ignored = subprocess.run(
        ["git", "-C", str(dino), "check-ignore", "-q", str(extension)],
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    ).returncode == 0
    if not ignored:
        raise C3AssetError("runtime extension must be ignored by the clean source tree")
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - distribution gate catches first
        raise C3AssetError("runtime torch import failed") from exc
    if str(torch.version.cuda) != gate["compiled_torch_cuda"]:
        raise C3AssetError("runtime torch CUDA differs")
    if os.environ.get("TORCH_CUDA_ARCH_LIST") != gate["compiled_cuda_arch"]:
        raise C3AssetError("TORCH_CUDA_ARCH_LIST differs from runtime contract")
    return {
        "contract_docker_image_id": runtime["docker_image_id"],
        "python_version": platform.python_version(),
        "distribution_versions": versions,
        "runtime_requirements_sha256": sha256_file(requirements),
        "source_attestations": source_attestations,
        "groundingdino_extension": {
            "path": str(extension),
            "size_bytes": extension.stat().st_size,
            "sha256": sha256_file(extension),
            "git_ignored": True,
            "torch_cuda": str(torch.version.cuda),
            "cuda_arch": os.environ["TORCH_CUDA_ARCH_LIST"],
        },
        "scientific_verdict": None,
    }

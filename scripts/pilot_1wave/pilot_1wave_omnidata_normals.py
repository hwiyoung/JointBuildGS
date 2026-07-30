#!/usr/bin/env python3
"""Pinned Omnidata world-normal producer for the expanded P1W scene.

This producer is inference-only.  It refuses to load the model until the
approved code, model, backbone, timm, input manifest, and view inventory pins
all match.  Per-view receipts make interrupted inference safely resumable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

REPO = Path(__file__).resolve().parents[2]
DEFAULT_LOCK = REPO / "phases/p2-gsjso/configs/pilot_1wave/pilot_1wave_omnidata_normal_lock.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO / candidate


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_tree_sha256(root: Path, roots: Sequence[Path]) -> tuple[str, int]:
    files: list[Path] = []
    for candidate in roots:
        if candidate.is_file():
            files.append(candidate)
        elif candidate.is_dir():
            files.extend(
                path
                for path in candidate.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
            )
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: str(item.relative_to(root))):
        rel = str(path.relative_to(root)).replace("\\", "/")
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest(), len(files)


def sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def atomic_npy(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        np.save(handle, array, allow_pickle=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label} mismatch: actual={actual!r}, expected={expected!r}")


def load_lock(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    lock = json.loads(raw)
    require_equal(
        lock.get("schema"),
        "jointbuildgs.pilot_1wave.omnidata_normal.lock.v1",
        "lock schema",
    )
    require_equal(lock.get("learning_runs_allowed"), 0, "learning allowance")
    require_equal(
        lock.get("new_mononormal_inference_allowed"), True, "inference allowance"
    )
    return lock, hashlib.sha256(raw).hexdigest()


def verify_file_pin(path: Path, expected_size: int, expected_sha: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"missing {label}: {path}")
    require_equal(path.stat().st_size, expected_size, f"{label} byte count")
    actual_sha = sha256_file(path)
    require_equal(actual_sha, expected_sha, f"{label} SHA256")
    return {"path": relative(path), "bytes": expected_size, "sha256": actual_sha}


def verify_assets(lock: dict[str, Any]) -> dict[str, Any]:
    model = lock["model"]
    code_root = resolve(model["code_root"])
    code_sha, code_files = stable_tree_sha256(
        code_root, [code_root / "hubconf.py", code_root / "omnidata_models"]
    )
    require_equal(code_sha, model["code_tree_sha256"], "Omnidata code tree SHA256")
    timm_root = resolve(model["timm_path"])
    timm_sha, timm_files = stable_tree_sha256(
        timm_root, [timm_root / "timm", timm_root / "timm-0.4.12.dist-info"]
    )
    require_equal(timm_sha, model["timm_tree_sha256"], "timm tree SHA256")
    return {
        "repository": model["repository"],
        "model": model["name"],
        "revision": model["revision"],
        "code_root": relative(code_root),
        "code_tree_sha256": code_sha,
        "code_tree_file_count": code_files,
        "weights": verify_file_pin(
            resolve(model["weights_path"]),
            int(model["weights_bytes"]),
            model["weights_sha256"],
            "Omnidata weights",
        ),
        "backbone_weights": verify_file_pin(
            resolve(model["backbone_weights_path"]),
            int(model["backbone_weights_bytes"]),
            model["backbone_weights_sha256"],
            "Omnidata backbone weights",
        ),
        "timm_path": relative(timm_root),
        "timm_version": model["timm_version"],
        "timm_tree_sha256": timm_sha,
        "timm_tree_file_count": timm_files,
    }


def load_dataset(lock: dict[str, Any]):
    from src.stage2.dataloader import ColmapDataset

    inputs = lock["input"]
    prep_manifest_path = resolve(inputs["prep_manifest"])
    require_equal(
        sha256_file(prep_manifest_path),
        inputs["prep_manifest_sha256"],
        "prep manifest SHA256",
    )
    prep = json.loads(prep_manifest_path.read_text(encoding="utf-8"))
    require_equal(prep.get("learning_runs_started"), 0, "prep learning_runs_started")
    require_equal(prep.get("semantic_source_read"), False, "prep semantic source read")
    require_equal(prep.get("lod2_z_read"), False, "prep LoD2 Z read")
    require_equal(prep.get("roofsurface_read"), False, "prep RoofSurface read")
    data_root = resolve(inputs["data_root"])
    dataset = ColmapDataset(
        root=data_root,
        downscale=float(inputs["downscale"]),
        load_depth=False,
        load_normal=False,
        load_semantic=False,
    )
    require_equal(len(dataset), int(inputs["expected_view_count"]), "view count")
    return dataset, prep_manifest_path


def input_receipt(frame: Any, batch: dict[str, Any]) -> dict[str, Any]:
    image_sha = sha256_file(frame.image_path)
    camera_payload = {
        "image_id": int(batch["image_id"]),
        "name": str(batch["name"]),
        "height": int(batch["height"]),
        "width": int(batch["width"]),
        "K": np.asarray(batch["K"], dtype=np.float32).tolist(),
        "w2c": np.asarray(batch["w2c"], dtype=np.float32).tolist(),
    }
    return {
        "image_name": str(batch["name"]),
        "image_path": relative(frame.image_path),
        "image_sha256": image_sha,
        "camera_sha256": sha256_json(camera_payload),
        "height": int(batch["height"]),
        "width": int(batch["width"]),
    }


def validate_output(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    expected_shape = (int(receipt["height"]), int(receipt["width"]), 3)
    normal = np.load(path, allow_pickle=False, mmap_mode="r")
    require_equal(tuple(normal.shape), expected_shape, f"normal shape {path.name}")
    require_equal(str(normal.dtype), "float32", f"normal dtype {path.name}")
    if not bool(np.isfinite(normal).all()):
        raise RuntimeError(f"non-finite normal values: {path}")
    norms = np.linalg.norm(np.asarray(normal), axis=-1)
    max_unit_error = float(np.max(np.abs(norms - 1.0)))
    if max_unit_error > 2e-4:
        raise RuntimeError(f"normal unit error {max_unit_error} exceeds 2e-4: {path}")
    return {
        **receipt,
        "normal_path": relative(path),
        "normal_sha256": sha256_file(path),
        "normal_bytes": path.stat().st_size,
        "normal_shape": list(expected_shape),
        "normal_dtype": "float32",
        "normal_frame": "world",
        "max_unit_error": max_unit_error,
    }


def load_model(lock: dict[str, Any], device: Any):
    model_cfg = lock["model"]
    timm_root = resolve(model_cfg["timm_path"])
    if str(timm_root) not in sys.path:
        sys.path.insert(0, str(timm_root))
    torch_home = resolve(model_cfg["weights_path"]).parents[2]
    os.environ["TORCH_HOME"] = str(torch_home)
    import torch

    model = torch.hub.load(
        str(resolve(model_cfg["code_root"])),
        model_cfg["name"],
        source="local",
        pretrained=True,
        trust_repo=True,
    )
    model.to(device).eval()
    return model


def infer_one(model: Any, image_path: Path, r_world_to_camera: np.ndarray, device: Any) -> np.ndarray:
    import torch
    import torch.nn.functional as functional
    from PIL import Image
    from torchvision.transforms.functional import pil_to_tensor, resize
    from torchvision.transforms import InterpolationMode

    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    image = resize(
        image,
        [384, 384],
        interpolation=InterpolationMode.BILINEAR,
        antialias=True,
    )
    tensor = pil_to_tensor(image).to(device=device, dtype=torch.float32).div_(255.0)
    with torch.inference_mode():
        output = model(tensor[:3].unsqueeze(0)).float().clamp_(0.0, 1.0)
        output = functional.interpolate(
            output,
            size=(height, width),
            mode="bilinear",
            align_corners=False,
        )[0].permute(1, 2, 0)
        n_camera = functional.normalize(output.mul(2.0).sub(1.0), dim=-1, eps=1e-6)
        rotation = torch.as_tensor(
            r_world_to_camera, device=device, dtype=torch.float32
        )
        n_world = functional.normalize(n_camera @ rotation, dim=-1, eps=1e-6)
    return n_world.cpu().numpy().astype(np.float32, copy=False)


def aggregate_receipt_sha(rows: Iterable[dict[str, Any]]) -> str:
    return sha256_json(
        [
            {
                "image_name": row["image_name"],
                "image_sha256": row["image_sha256"],
                "camera_sha256": row["camera_sha256"],
                "normal_sha256": row["normal_sha256"],
            }
            for row in rows
        ]
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    lock_path = resolve(args.lock)
    lock, lock_sha = load_lock(lock_path)
    assets = verify_assets(lock)
    dataset, prep_manifest_path = load_dataset(lock)
    output_dir = resolve(lock["output"]["normal_dir"])
    manifest_path = resolve(lock["output"]["manifest"])
    verification_path = resolve(lock["output"]["verification_receipt"])
    progress_path = output_dir / ".progress.json"
    progress: dict[str, Any] = {"rows": {}}
    if progress_path.is_file():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
    rows_by_name = progress.setdefault("rows", {})

    if args.mode == "preflight":
        return {
            "schema": "jointbuildgs.pilot_1wave.omnidata_normal.preflight.v1",
            "status": "pass",
            "lock": relative(lock_path),
            "lock_sha256": lock_sha,
            "assets": assets,
            "prep_manifest": relative(prep_manifest_path),
            "view_count": len(dataset),
            "learning_runs_started": 0,
            "new_mononormal_inference_runs": 0,
        }

    model = None
    torch = None
    device = None
    if args.mode == "infer":
        import torch as torch_module

        torch = torch_module
        require_equal(torch.__version__, lock["runtime"]["torch_version"], "torch version")
        require_equal(
            os.environ.get("P1W_DOCKER_IMAGE_ID"),
            lock["runtime"]["docker_image_id"],
            "Docker image ID attestation",
        )
        if not torch.cuda.is_available() and args.device.startswith("cuda"):
            raise RuntimeError("CUDA requested but not available")
        device = torch.device(args.device)
        torch.manual_seed(20260721)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(20260721)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        model = load_model(lock, device)

    complete_rows: list[dict[str, Any]] = []
    newly_inferred = 0
    for index in range(len(dataset)):
        batch = dataset[index]
        frame = dataset.frames[index]
        receipt = input_receipt(frame, batch)
        name = receipt["image_name"]
        output_path = output_dir / f"{Path(name).stem}.npy"
        prior = rows_by_name.get(name)
        reusable = (
            prior is not None
            and prior.get("image_sha256") == receipt["image_sha256"]
            and prior.get("camera_sha256") == receipt["camera_sha256"]
            and output_path.is_file()
            and prior.get("normal_sha256") == sha256_file(output_path)
        )
        if args.mode == "infer" and not reusable:
            assert model is not None and device is not None
            rotation = np.asarray(batch["w2c"], dtype=np.float32)[:3, :3]
            atomic_npy(output_path, infer_one(model, frame.image_path, rotation, device))
            newly_inferred += 1
        if not output_path.is_file():
            raise RuntimeError(f"missing normal output for {name}: {output_path}")
        row = validate_output(output_path, receipt)
        rows_by_name[name] = row
        complete_rows.append(row)
        progress.update(
            {
                "schema": "jointbuildgs.pilot_1wave.omnidata_normal.progress.v1",
                "lock_sha256": lock_sha,
                "updated_utc": utc_now(),
                "completed_view_count": len(complete_rows),
                "expected_view_count": len(dataset),
            }
        )
        atomic_json(progress_path, progress)
        if args.mode == "infer" and (index + 1) % 10 == 0:
            print(
                json.dumps(
                    {
                        "stage": "omnidata_normal",
                        "completed": index + 1,
                        "total": len(dataset),
                        "newly_inferred": newly_inferred,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    complete_rows.sort(key=lambda row: row["image_name"])
    manifest = {
        "schema": "jointbuildgs.pilot_1wave.omnidata_normal.manifest.v1",
        "run_id": lock["run_id"],
        "task_id": lock["task_id"],
        "status": "complete",
        "mode": args.mode,
        "created_utc": utc_now(),
        "lock": relative(lock_path),
        "lock_sha256": lock_sha,
        "prep_manifest": relative(prep_manifest_path),
        "prep_manifest_sha256": sha256_file(prep_manifest_path),
        "assets": assets,
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "torch": None if torch is None else torch.__version__,
            "device": None if device is None else str(device),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "docker_tag": lock["runtime"]["docker_tag"],
            "docker_image_id": os.environ.get("P1W_DOCKER_IMAGE_ID"),
        },
        "contract": lock["inference"],
        "view_count": len(complete_rows),
        "newly_inferred_view_count_this_invocation": newly_inferred,
        "normal_receipt_sha256": aggregate_receipt_sha(complete_rows),
        "normal_dir": relative(output_dir),
        "learning_runs_started": 0,
        "new_mononormal_inference_runs": 1 if args.mode == "infer" and newly_inferred else 0,
        "forbidden_sources_read": [],
        "rows": complete_rows,
    }
    if args.mode == "verify":
        if not manifest_path.is_file():
            raise RuntimeError(
                f"generation manifest is required before verification: {manifest_path}"
            )
        generation_bytes = manifest_path.read_bytes()
        generation = json.loads(generation_bytes)
        require_equal(
            generation.get("schema"),
            "jointbuildgs.pilot_1wave.omnidata_normal.manifest.v1",
            "generation manifest schema",
        )
        require_equal(generation.get("mode"), "infer", "generation manifest mode")
        require_equal(generation.get("status"), "complete", "generation status")
        require_equal(generation.get("lock_sha256"), lock_sha, "generation lock SHA256")
        require_equal(generation.get("view_count"), len(complete_rows), "generation view count")
        require_equal(
            generation.get("normal_receipt_sha256"),
            manifest["normal_receipt_sha256"],
            "generation normal receipt SHA256",
        )
        require_equal(generation.get("rows"), complete_rows, "generation per-view receipts")
        verification = {
            "schema": "jointbuildgs.pilot_1wave.omnidata_normal.verification.v1",
            "run_id": lock["run_id"],
            "task_id": lock["task_id"],
            "status": "pass",
            "created_utc": utc_now(),
            "lock": relative(lock_path),
            "lock_sha256": lock_sha,
            "generation_manifest": relative(manifest_path),
            "generation_manifest_sha256": hashlib.sha256(generation_bytes).hexdigest(),
            "view_count": len(complete_rows),
            "normal_receipt_sha256": manifest["normal_receipt_sha256"],
            "checks": [
                "input image SHA256",
                "camera SHA256",
                "output file SHA256",
                "shape HxWx3",
                "dtype float32",
                "finite values",
                "unit normal max error <= 2e-4",
                "world-frame contract",
            ],
            "learning_runs_started": 0,
            "new_mononormal_inference_runs": 0,
        }
        atomic_json(verification_path, verification)
        return verification
    atomic_json(manifest_path, manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", default=str(DEFAULT_LOCK))
    parser.add_argument("--mode", choices=("preflight", "infer", "verify"), required=True)
    parser.add_argument("--device", default="cuda:0")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(args)
    summary = {
        key: result.get(key)
        for key in (
            "schema",
            "status",
            "mode",
            "view_count",
            "newly_inferred_view_count_this_invocation",
            "normal_receipt_sha256",
            "learning_runs_started",
            "new_mononormal_inference_runs",
            "generation_manifest_sha256",
        )
        if key in result
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

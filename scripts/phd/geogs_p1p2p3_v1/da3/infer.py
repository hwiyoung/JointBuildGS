"""Train-only, pose-conditioned DA3 preprocessing using official GeoGS helpers.

Run in the dedicated Docker image with only train batch folders, metadata,
official script, pinned model and a new output folder mounted. No UAS or full
regional images directory is required or allowed by the supplied launcher.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import resource
import time
import traceback

import cv2
import numpy as np
import torch
import depth_anything_3.api as da3_api
from depth_anything_3.api import DepthAnything3

from acquire_weights import MODEL, REVISION, SOURCE_COMMIT, WEIGHT_SHA256, sha

OFFICIAL_SCRIPT_SHA256 = "97703618afba7563b7f6f8ef2671219b525925e1474140871609db2fc2c7c2ea"


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("/config.json"))
    parser.add_argument("--batch-policy", type=Path, default=Path("/batch_policy.json"))
    parser.add_argument("--split", type=Path, default=Path("/split.json"))
    parser.add_argument("--batches", type=Path, default=Path("/batches"))
    parser.add_argument("--official-script", type=Path, default=Path("/official.py"))
    parser.add_argument("--acquisition", type=Path, default=Path("/acquisition.json"))
    parser.add_argument("--model", type=Path, default=Path("/model"))
    parser.add_argument("--output", type=Path, default=Path("/out"))
    parser.add_argument("--batch-id", type=int, help="Only this predeclared batch, for runtime preflight")
    args = parser.parse_args()
    if not Path("/.dockerenv").exists() or Path("/artifacts").exists():
        raise RuntimeError("A dedicated Docker container without the artifact root mount is required")
    if any(args.output.iterdir()):
        raise FileExistsError("Output must be a new, empty directory")
    config_bytes = args.config.read_bytes()
    config = json.loads(config_bytes)
    split = json.loads(args.split.read_text())
    acquisition = json.loads(args.acquisition.read_text())
    revision_bytes = args.batch_policy.read_bytes()
    revision = json.loads(revision_bytes)
    policy = dict(config["da3"], **revision["da3"])
    if policy["model"] != MODEL or policy["process_res"] != 840 or policy["max_batch_views"] != 8:
        raise ValueError("This version is frozen to the declared giant model, 840 resolution, max8 views")
    if policy["partition"] != "balanced_consecutive_disjoint_train_only" or policy["min_batch_views"] != 3 or policy["batch_revision"] != 2:
        raise ValueError("The shared input-only balanced batching revision2 is required")
    if acquisition["status"] != "PASS_PINNED_OFFICIAL_SOURCE_AND_WEIGHTS" or acquisition["model_revision"] != REVISION or acquisition["source_commit"] != SOURCE_COMMIT:
        raise ValueError("Exact successful source/weight acquisition receipt required")
    if sha(args.model / "model.safetensors") != WEIGHT_SHA256:
        raise ValueError("Model weight identity mismatch")
    for filename in ("config.json",):
        if sha(args.model / filename) != acquisition["files"][filename]["sha256"]:
            raise ValueError(f"Model {filename} identity mismatch")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required; no hidden CPU fallback")
    if sha(args.official_script) != OFFICIAL_SCRIPT_SHA256:
        raise ValueError("Official GeoGS preprocessing script changed")
    installed_root = Path(da3_api.__file__).parent
    prefix = "src/depth_anything_3/"
    for relative, digest in acquisition["source_files"].items():
        if relative.startswith(prefix) and Path(relative).suffix in (".py", ".yaml"):
            if sha(installed_root / relative.removeprefix(prefix)) != digest:
                raise ValueError(f"Installed official DA3 source differs: {relative}")
    train = {item["name"]: item for item in split["train"]}
    excluded = {item["name"] for item in split["evaluation"]}
    batches = split["da3_batches"]
    flat = [name for batch in batches for name in batch["names"]]
    if len(flat) != len(set(flat)) or set(flat) != set(train) or set(flat) & excluded:
        raise ValueError("DA3 batching does not partition the exact train-only image set")
    groups = np.array_split(np.array(sorted(train)), (len(train)+7)//8)
    if [batch["names"] for batch in batches] != [group.tolist() for group in groups]:
        raise ValueError("DA3 batches differ from the frozen balanced consecutive partition")
    rank_preflight = {}
    for batch in batches:
        centers = np.stack([-np.asarray(train[name]["R"]).T @ np.asarray(train[name]["t"]) for name in batch["names"]])
        centered = centers-centers.mean(axis=0)
        rank = int(np.linalg.matrix_rank(centered))
        if len(centers) < 3 or rank < 2:
            raise ValueError("Balanced batch cannot support official Sim3 alignment: collinear training camera centers")
        rank_preflight[str(batch["batch_id"])] = dict(count=len(centers), rank=rank,
                                                     singular_values=np.linalg.svd(centered, compute_uv=False).tolist())
    if args.batch_id is not None:
        batches = [batch for batch in batches if batch["batch_id"] == args.batch_id]
        if len(batches) != 1:
            raise ValueError("Unknown batch ID")
    for batch in batches:
        if not 3 <= len(batch["names"]) <= policy["max_batch_views"]:
            raise ValueError("Official evo Umeyama alignment needs at least3 noncollinear views; max8 must be preserved")
        scene = args.batches / f"batch_{batch['batch_id']:03d}"
        found = {p.name for p in (scene / "images").iterdir()}
        if found != set(batch["names"]):
            raise ValueError("Batch image directory differs from fixed membership")
        for name in batch["names"]:
            path = scene / "images" / name
            if not path.resolve().is_relative_to(args.batches.resolve()) or sha(path) != train[name]["sha256"]:
                raise ValueError("Training RGB bytes changed or escaped the train-only mount")
    spec = importlib.util.spec_from_file_location("official_geogs_da3", args.official_script)
    official = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(official)
    seed = config["seed"]
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    # Resource-only preflight policy: leave GPU0 desktop/display headroom.
    torch.cuda.set_per_process_memory_fraction(0.8, 0)
    torch.cuda.reset_peak_memory_stats()
    start = time.monotonic()
    receipt = dict(task_id=config["task_id"], region=split["region"], scientific_verdict=None,
                   model=MODEL, model_revision=REVISION, model_sha256=WEIGHT_SHA256,
                   source_commit=SOURCE_COMMIT, official_script_sha256=sha(args.official_script),
                   driver_sha256=sha(Path(__file__)), config_sha256=hashlib.sha256(config_bytes).hexdigest(),
                   batch_policy_sha256=hashlib.sha256(revision_bytes).hexdigest(), batch_rank_preflight=rank_preflight,
                   split_sha256=sha(args.split), acquisition_sha256=sha(args.acquisition),
                   seed=seed, policy=policy, device=torch.cuda.get_device_name(0),
                   torch_version=torch.__version__, cuda_version=torch.version.cuda,
                   cuda_allocator_memory_fraction=0.8,
                   batch_allocator_policy="release prediction; gc.collect; torch.cuda.empty_cache after each completed batch",
                   evaluation_rgb_accessed=False, reference_accessed=False,
                   full_region=args.batch_id is None, batches=[], status="RUNNING")
    write(args.output / "start_receipt.json", receipt)
    (args.output / "config_executed.json").write_bytes(config_bytes)
    (args.output / "batch_policy_executed.json").write_bytes(revision_bytes)
    write(args.output / "effective_da3_policy.json", policy)
    try:
        model = DepthAnything3.from_pretrained(str(args.model), local_files_only=True).to("cuda")
        model.eval()
        for folder in ("raw_depth", "raw_depth_upsampled", "confidence", "confidence_upsampled", "batches"):
            (args.output / folder).mkdir()
        for batch in batches:
            batch_start = time.monotonic()
            scene = args.batches / f"batch_{batch['batch_id']:03d}"
            paths, extrinsics, intrinsics, stems, original_sizes = official.read_colmap_data(str(scene), "0")
            indices = sorted(range(len(paths)), key=lambda index: Path(paths[index]).name)
            paths = [paths[i] for i in indices]
            stems = [stems[i] for i in indices]
            original_sizes = [original_sizes[i] for i in indices]
            extrinsics, intrinsics = extrinsics[indices], intrinsics[indices]
            if [Path(path).name for path in paths] != sorted(batch["names"]):
                raise ValueError("Official helper did not read every exact training camera/image")
            for i, path in enumerate(paths):
                view = train[Path(path).name]
                if (not np.allclose(extrinsics[i, :3, :3], view["R"], rtol=0, atol=1e-12)
                        or not np.allclose(extrinsics[i, :3, 3], view["t"], rtol=0, atol=1e-9)
                        or not np.allclose(intrinsics[i], view["K"], rtol=0, atol=1e-12)):
                    raise ValueError("Input camera changed from frozen source membership")
            camera_centers = -np.einsum("nji,nj->ni", extrinsics[:, :3, :3], extrinsics[:, :3, 3])
            center_rank = int(np.linalg.matrix_rank(camera_centers-camera_centers.mean(axis=0)))
            if center_rank < 2:
                raise ValueError("Training camera centers are collinear; official Sim3 pose scale alignment is undefined")
            # Official GeoGS inference arguments, plus explicit depth-only output.
            prediction = model.inference(image=paths, extrinsics=extrinsics, intrinsics=intrinsics,
                                         align_to_input_ext_scale=True, process_res=840,
                                         process_res_method="upper_bound_resize", infer_gs=False)
            torch.cuda.synchronize()
            if prediction.depth.shape[0] != len(paths) or prediction.conf.shape != prediction.depth.shape:
                raise ValueError("Unexpected prediction membership or confidence shape")
            if not np.allclose(prediction.extrinsics, extrinsics[:, :3, :], rtol=0, atol=1e-5):
                raise ValueError("DA3 did not preserve input metric extrinsics after scale alignment")
            batch_files = {}
            statistics = []
            for i, stem in enumerate(stems):
                depth = prediction.depth[i].astype(np.float32)
                confidence = prediction.conf[i].astype(np.float32)
                valid = np.isfinite(depth) & (depth > 0)
                if not np.any(valid):
                    raise ValueError(f"No valid predicted depth: {stem}")
                # Match official GeoGS upsampling exactly; record invalid results rather than silently clamp.
                upsampled = cv2.resize(depth, original_sizes[i], interpolation=cv2.INTER_CUBIC)
                conf_up = cv2.resize(confidence, original_sizes[i], interpolation=cv2.INTER_CUBIC)
                for folder, array in (("raw_depth", depth), ("raw_depth_upsampled", upsampled),
                                      ("confidence", confidence), ("confidence_upsampled", conf_up)):
                    target = args.output / folder / f"{stem}.npy"
                    if target.exists():
                        raise FileExistsError(target)
                    np.save(target, array)
                    batch_files[str(target.relative_to(args.output))] = sha(target)
                statistics.append(dict(name=Path(paths[i]).name, shape=list(depth.shape),
                                       original_size=list(original_sizes[i]), valid_fraction=float(valid.mean()),
                                       median_m=float(np.median(depth[valid])), min_m=float(depth[valid].min()),
                                       max_m=float(depth[valid].max()),
                                       upsampled_valid_fraction=float((np.isfinite(upsampled) & (upsampled > 0)).mean())))
            export = args.output / "batches" / f"batch_{batch['batch_id']:03d}.npz"
            np.savez(export, depth=prediction.depth, conf=prediction.conf,
                     extrinsics=prediction.extrinsics, intrinsics=prediction.intrinsics,
                     input_extrinsics=extrinsics, input_intrinsics=intrinsics,
                     image_names=np.array([Path(path).name for path in paths]))
            batch_files[str(export.relative_to(args.output))] = sha(export)
            row = dict(batch_id=batch["batch_id"], names=[Path(path).name for path in paths],
                       input_camera_center_rank=center_rank,
                       image_ids=batch["image_ids"], statistics=statistics, files=batch_files,
                       wall_seconds=time.monotonic()-batch_start,
                       peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(),
                       peak_cuda_reserved_bytes=torch.cuda.max_memory_reserved())
            del prediction
            gc.collect()
            torch.cuda.empty_cache()
            row.update(post_batch_cuda_allocated_bytes=torch.cuda.memory_allocated(),
                       post_batch_cuda_reserved_bytes=torch.cuda.memory_reserved())
            write(args.output / "batches" / f"batch_{batch['batch_id']:03d}.json", row)
            receipt["batches"].append(row)
            print(json.dumps({"batch_id": row["batch_id"], "status": "PASS", "wall_seconds": row["wall_seconds"]}), flush=True)
        receipt["status"] = "PASS_TRAIN_ONLY_DEPTH_GENERATION"
    except Exception as error:
        receipt.update(status="FAILED_DEPTH_GENERATION", error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        receipt.update(wall_seconds=time.monotonic()-start,
                       peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(),
                       peak_cuda_reserved_bytes=torch.cuda.max_memory_reserved(),
                       peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
        write(args.output / "receipt.json", receipt)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # The supplied launcher always mounts /out. Preserve early contract
        # failures too, before the main training-free inference receipt exists.
        output = Path("/out")
        if output.is_dir() and not (output / "receipt.json").exists() and not (output / "early_failure.json").exists():
            write(output / "early_failure.json", dict(status="FAILED_PREFLIGHT_BEFORE_INFERENCE",
                  scientific_verdict=None, error=str(error), traceback=traceback.format_exc(),
                  reference_accessed=False, evaluation_rgb_accessed=False,
                  driver_sha256=sha(Path(__file__))))
        raise

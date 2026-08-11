#!/usr/bin/env python3
"""Freeze and validate the upstream DN-Splatter run contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import torch
import yaml


TASK_ID = "P2-E3-LOCAL-4906982-DN-SPLATTER-UPSTREAM-v1"
UPSTREAM_COMMIT = "97588b4290128ce7ba6fdbfaac3020b42b17de4c"


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def record(path: Path, role: str, lineage: str) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "role": role,
        "lineage": lineage,
    }


def write_json(path: Path, value: object, *, mutable: bool = False) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not mutable and path.read_text() != payload:
        raise RuntimeError(f"existing contract drift: {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload)
    os.replace(temporary, path)


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={repo}", "-C", str(repo), *args], text=True
    ).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--crop", type=Path, required=True)
    parser.add_argument("--roles", type=Path, required=True)
    parser.add_argument("--prior-input-hashes", type=Path, required=True)
    parser.add_argument("--docker-image-id", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--mode", choices=("preflight", "finalize"), default="preflight")
    parser.add_argument("--return-code", type=int)
    args = parser.parse_args()

    prior = json.loads(args.prior_input_hashes.read_text())
    prior_records = prior["records"]
    roles = yaml.safe_load(args.roles.read_text())
    train = list(roles["train_views"])
    held_out = list(roles["eval_views"])
    visible = list(roles.get("visible_views", train + held_out))
    if (len(visible), len(train), len(held_out)) != (55, 47, 8):
        raise RuntimeError("fixed view counts drift")

    sparse = args.crop / "sparse/0"
    records = {
        "view_roles": record(args.roles, "47 train / 8 held-out roles", "frozen v6 control reused without regeneration"),
        "colmap_cameras": record(sparse / "cameras.bin", "intrinsics", "frozen 55-view COLMAP crop"),
        "colmap_images": record(sparse / "images.bin", "extrinsics", "frozen 55-view COLMAP crop"),
        "sparse_sfm_seed": record(sparse / "points3D.bin", "upstream DN initialization", "frozen 55-view COLMAP sparse model"),
        "adapter_transforms": record(args.task_root / "data/transforms.json", "DN-Splatter dataset adapter", "OpenCV c2w to OpenGL camera axes; world XYZ unchanged"),
        "adapter_sparse_ply": record(args.task_root / "data/sparse_pc.ply", "DN-Splatter sparse PLY", "exact COLMAP sparse coordinates and colors"),
        "openmvs_fused_dense_cloud": record(Path(prior_records["openmvs_fused_dense_cloud"]["path"]), "evaluation-only fused MVS reference", prior_records["openmvs_fused_dense_cloud"]["lineage"]),
        "filtered_voxelized_full_seed": record(Path(prior_records["filtered_voxelized_full_seed"]["path"]), "evaluation-only 0.40m MVS seed", prior_records["filtered_voxelized_full_seed"]["lineage"]),
        "shared_footprint_xy": record(Path(prior_records["shared_footprint_xy"]["path"]), "evaluation/region XY only", "DEC-P1-019 shared GroundSurface XY control"),
    }
    expected_map = {
        "view_roles": "view_roles",
        "colmap_cameras": "colmap_cameras",
        "colmap_images": "colmap_images",
        "sparse_sfm_seed": "sparse_sfm_seed",
        "openmvs_fused_dense_cloud": "openmvs_fused_dense_cloud",
        "filtered_voxelized_full_seed": "filtered_voxelized_full_seed",
        "shared_footprint_xy": "shared_footprint_xy",
    }
    for current, old in expected_map.items():
        if records[current]["sha256"] != prior_records[old]["sha256"]:
            raise RuntimeError(f"frozen input hash drift: {current}")

    image_hashes = {}
    depth_hashes = {}
    receipt = json.loads((args.task_root / "dataset_adapter_receipt.json").read_text())
    for name in visible:
        image = args.crop / "images" / name
        depth = args.crop / "stereo/depth_maps" / f"{name}.geometric.bin"
        image_hashes[name] = sha256(image)
        depth_hashes[name] = sha256(depth)
        if depth_hashes[name] != receipt["depth"][name]["source_sha256"]:
            raise RuntimeError(f"depth hash drift: {name}")
        if depth_hashes[name] != prior["colmap_geometric_depth_sha256"][name]:
            raise RuntimeError(f"depth differs from prior frozen audit: {name}")
        if image_hashes[name] != prior["selected_images_sha256"][name]:
            raise RuntimeError(f"image differs from prior frozen audit: {name}")

    inputs = {
        "schema": "jointbuildgs.p2.e3_local_4906982_dn_splatter_upstream_v1.input_hashes.v1",
        "records": records,
        "selected_images_sha256": image_hashes,
        "colmap_geometric_depth_sha256": depth_hashes,
        "view_counts": {"visible": 55, "train": 47, "held_out": 8},
        "prior_hash_manifest": record(args.prior_input_hashes, "cross-check source", "MVS transfer diagnostic input audit"),
        "training_inputs": ["selected_images_sha256", "colmap_geometric_depth_sha256", "view_roles", "colmap_cameras", "colmap_images", "sparse_sfm_seed", "adapter_transforms", "adapter_sparse_ply"],
        "evaluation_only_inputs": ["openmvs_fused_dense_cloud", "filtered_voxelized_full_seed", "shared_footprint_xy"],
        "scientific_verdict": None,
    }
    write_json(args.task_root / "input_hashes.json", inputs)

    owned = [
        args.repo / "Dockerfile.dn-splatter-upstream",
        args.repo / "configs/p2/e3_local_4906982_dn_splatter_upstream_v1/upstream.yaml",
        args.repo / "configs/p2/e3_local_4906982_dn_splatter_upstream_v1/reference_sources.yaml",
        args.repo / "scripts/p2/e3_local_4906982_dn_splatter_upstream_v1/prepare_dataset.py",
        args.repo / "scripts/p2/e3_local_4906982_dn_splatter_upstream_v1/prepare_contract.py",
        args.repo / "scripts/p2/e3_local_4906982_dn_splatter_upstream_v1/run.sh",
        args.repo / "scripts/p2/e3_local_4906982_dn_splatter_upstream_v1/evaluate.py",
        args.repo / "scripts/p2/e3_local_4906982_dn_splatter_upstream_v1/make_report.py",
    ]
    sources = {str(path.relative_to(args.repo)): sha256(path) for path in owned}
    upstream_head = git(Path("/opt/dn-splatter"), "rev-parse", "HEAD")
    if upstream_head != UPSTREAM_COMMIT or git(Path("/opt/dn-splatter"), "status", "--porcelain"):
        raise RuntimeError("pinned upstream source gate failed")

    contract = {
        "schema": "jointbuildgs.p2.e3_local_4906982_dn_splatter_upstream_v1.contract.v1",
        "task_id": TASK_ID,
        "building_id": "DEBY_LOD2_4906982",
        "method": {"name": "DN-Splatter", "upstream_commit": UPSTREAM_COMMIT, "source_edits": False},
        "fixed_data": {"views": 55, "train": 47, "held_out": 8, "random_seed": 0},
        "training": {
            "iterations": 20000,
            "requested_checkpoint_updates": [7000, 12000, 15000, 20000],
            "nerfstudio_checkpoint_steps": [7000, 12000, 15000, 19999],
            "depth": {"source": "raw COLMAP geometric camera-Z", "valid_mask": "finite and >0", "loss": "EdgeAwareLogL1", "lambda": 0.2},
            "normal": {"supervision": "derived from input depth", "loss_enabled": True, "tv_enabled": True, "lambda": 0.1},
            "gaussians": "2D",
            "regularization_strategy": "dn-splatter",
            "initialization": "exact sparse SfM PLY",
            "camera_optimizer": "off",
        },
        "prohibited": ["LoD2 Z/roof/semantic training use", "ALS prior", "MVC", "confidence filtering", "DN-Splatter source modification"],
        "preflight_passed": True,
        "scientific_verdict": None,
    }
    write_json(args.task_root / "experiment_contract.json", contract)

    diff = """Pinned upstream DN-Splatter defaults -> DEBY_LOD2_4906982 run\n\nCHANGED\nmax_num_iterations: 30000 -> 20000\nsteps_per_save: 1000000 -> 1000\nsave_only_latest_checkpoint: True -> False\nsteps_per_eval_image: 500 -> 1000\nsteps_per_eval_batch: 500 -> 1000\nvis: viewer -> tensorboard\nuse_depth_loss: False -> True\ndepth_lambda: 0.0 -> 0.2\nnormal_supervision: mono -> depth\nload_depths: False -> True\nload_normals: False (retained; normals derive from input depth)\ndataset: upstream examples -> frozen DEBY 55-view adapter\n\nUNCHANGED METHOD CONTROLS\nregularization_strategy: dn-splatter\ndepth_loss_type: EdgeAwareLogL1\nuse_normal_loss: True\nuse_normal_tv_loss: True\nnormal_lambda: 0.1\ntwo_d_gaussians: True\nwarmup_length: 500\nstop_split_at: 15000\ncamera_optimizer: off\nmeans LR schedule max_steps: 30000\nDN minimum-scale regularizer: enabled by DNRegularization\nPhysGaussian scale regularization: False\n"""
    diff_path = args.task_root / "config_diff.txt"
    if diff_path.exists() and diff_path.read_text() != diff:
        raise RuntimeError("existing config diff drift")
    diff_path.write_text(diff)

    notes = """# NOTES\n\n- This task executes the pinned official DN-Splatter implementation; it is not the earlier JointBuildGS depth-loss transplant.\n- The frozen 55-view crop, cameras, view roles, sparse SfM seed, and raw COLMAP geometric depth are reused after SHA256 verification.\n- OpenMVS geometry and the shared footprint are evaluation-only and are not exposed to training.\n- Raw depth validity is exactly finite and positive. No confidence/support/LoD mask is added.\n- Camera axes are adapted from COLMAP OpenCV to Nerfstudio OpenGL; world coordinates and sparse XYZ remain unchanged.\n- scientific_verdict is null.\n"""
    notes_path = args.task_root / "NOTES.md"
    if notes_path.exists() and notes_path.read_text() != notes:
        raise RuntimeError("existing notes drift")
    notes_path.write_text(notes)

    provenance_path = args.task_root / "provenance.json"
    now = datetime.now(timezone.utc).isoformat()
    if provenance_path.exists():
        provenance = json.loads(provenance_path.read_text())
    else:
        provenance = {
            "schema": "jointbuildgs.p2.e3_local_4906982_dn_splatter_upstream_v1.provenance.v1",
            "task_id": TASK_ID,
            "git": {
                "commit": git(args.repo, "rev-parse", "HEAD"),
                "branch": git(args.repo, "branch", "--show-current"),
                "dirty": bool(git(args.repo, "status", "--porcelain")),
                "status_porcelain": git(args.repo, "status", "--porcelain").splitlines(),
            },
            "docker": {"image": "jointbuildgs:dn-splatter-upstream-97588b4", "image_id": args.docker_image_id, "upstream_commit": upstream_head},
            "gpu_model": torch.cuda.get_device_name(0),
            "source_config_sha256": sources,
            "input_hashes_sha256": sha256(args.task_root / "input_hashes.json"),
            "random_seed": 0,
            "command_line": args.command,
            "started_utc": now,
            "ended_utc": None,
            "return_code": None,
            "scientific_verdict": None,
        }
    if args.mode == "finalize":
        if args.return_code is None:
            raise RuntimeError("--return-code required for finalize")
        provenance["source_config_sha256"] = sources
        provenance["input_hashes_sha256"] = sha256(args.task_root / "input_hashes.json")
        provenance["command_line"] = args.command
        if provenance["ended_utc"] is None:
            provenance["ended_utc"] = now
        provenance["return_code"] = args.return_code
    write_json(provenance_path, provenance, mutable=True)
    print(json.dumps({"preflight_passed": True, "mode": args.mode, "input_hashes": len(image_hashes) + len(depth_hashes), "gpu": provenance["gpu_model"]}, indent=2))


if __name__ == "__main__":
    main()

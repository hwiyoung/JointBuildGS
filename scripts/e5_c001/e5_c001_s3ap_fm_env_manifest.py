#!/usr/bin/env python3
"""Write the locked S3-A-prime MASt3R environment manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import torch


REPO = Path(__file__).resolve().parents[2]


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={path}", "-C", str(path), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def repo_git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", type=Path, required=True)
    parser.add_argument("--dockerfile", type=Path, required=True)
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--base-image-tag", required=True)
    parser.add_argument("--base-image-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--freeze-out", type=Path, required=True)
    args = parser.parse_args()

    smoke = json.loads(args.smoke.read_text(encoding="utf-8"))
    if smoke.get("status") != "pass" or smoke.get("finite_and_shape_check") != "pass":
        raise RuntimeError("environment manifest requires a passing finite smoke")
    freeze = subprocess.check_output(["python", "-m", "pip", "freeze", "--all"], text=True)
    freeze_lines = sorted(line.strip() for line in freeze.splitlines() if line.strip())
    args.freeze_out.parent.mkdir(parents=True, exist_ok=True)
    args.freeze_out.write_text("\n".join(freeze_lines) + "\n", encoding="utf-8")

    mast3r = Path("/opt/mast3r")
    payload = {
        "schema": "jointbuildgs.s3ap.fm_env_manifest.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "environment_locked_smoke_pass",
        "learning_runs_started": 0,
        "repo_git_head": repo_git("rev-parse", "HEAD"),
        "repo_branch": repo_git("branch", "--show-current"),
        "model": {
            "id": smoke["model_id"],
            "revision": smoke["model_revision"],
            "weights_sha256": smoke["model_sha256"],
            "weights_bytes": smoke["model_bytes"],
            "config_sha256": smoke["config_sha256"],
            "source": "complete pre-existing local Hugging Face cache; mounted read-only; offline mode",
        },
        "code": {
            "mast3r_repository": "https://github.com/naver/mast3r.git",
            "mast3r_commit": git_head(mast3r),
            "dust3r_repository": "https://github.com/naver/dust3r.git",
            "dust3r_commit": git_head(mast3r / "dust3r"),
            "croco_repository": "https://github.com/naver/croco.git",
            "croco_commit": git_head(mast3r / "dust3r/croco"),
        },
        "runtime_lock": {
            "docker_image_tag": args.image_tag,
            "docker_image_id": args.image_id,
            "base_image_tag": args.base_image_tag,
            "base_image_id": args.base_image_id,
            "dockerfile": str(args.dockerfile),
            "dockerfile_sha256": sha256_file(args.dockerfile),
            "python": platform.python_version(),
            "torch": torch.__version__,
            "torch_cuda": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "pip_freeze": str(args.freeze_out),
            "pip_freeze_sha256": sha256_file(args.freeze_out),
            "pip_freeze_line_count": len(freeze_lines),
            "dependency_lock_method": "immutable local Docker image ID plus complete pip freeze",
            "offline_inference": True,
        },
        "smoke": {
            "status_line": (
                f"pass; matches={smoke['reciprocal_match_count']}; "
                f"pts1={smoke['output']['pred1_pts3d']['shape']}; "
                f"pts2={smoke['output']['pred2_pts3d_in_other_view']['shape']}; finite=true"
            ),
            "artifact": str(args.smoke),
            "artifact_sha256": sha256_file(args.smoke),
            "building": "DEBY_LOD2_4907199",
            "pair": ["DJI_20241217095441_0023_D", "DJI_20241217095531_0048_D"],
            "crop_rule": "raw source image cropped by the already-recorded T0-1 crop_box_xyxy",
            "output_shapes": {
                "pred1_pts3d": smoke["output"]["pred1_pts3d"]["shape"],
                "pred2_pts3d_in_other_view": smoke["output"]["pred2_pts3d_in_other_view"]["shape"],
                "pred1_desc": smoke["output"]["pred1_desc"]["shape"],
                "pred2_desc": smoke["output"]["pred2_desc"]["shape"],
            },
            "all_finite": True,
            "reciprocal_match_count": smoke["reciprocal_match_count"],
        },
        "runtime_notes": [
            "CUDA RoPE2D extension was not compiled; official PyTorch fallback was used.",
            "The first inference completed but its provenance write stopped on git dubious-ownership; no artifact was written. The rerun used explicit per-repository safe.directory and passed.",
            "No weight download, model training, seed generation, or experiment input mutation occurred.",
        ],
        "gt_use": "none in environment lock and smoke",
        "interpretation_or_verdict": None,
    }
    expected = {
        "mast3r": "f5209afc300cec36239a7ac992263f36847bbba0",
        "dust3r": "3cc8c88c413bb9e34c41db0e0eef99c2ee010b12",
        "croco": "d7de0705845239092414480bd829228723bf20de",
    }
    actual = {
        "mast3r": payload["code"]["mast3r_commit"],
        "dust3r": payload["code"]["dust3r_commit"],
        "croco": payload["code"]["croco_commit"],
    }
    if actual != expected:
        raise RuntimeError(f"code lock mismatch: {actual} != {expected}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(payload["smoke"]["status_line"])
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

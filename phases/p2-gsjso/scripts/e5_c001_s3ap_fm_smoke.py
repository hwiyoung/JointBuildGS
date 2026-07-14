#!/usr/bin/env python3
"""One-pair MASt3R environment smoke for S3-A-prime learning-zero work."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image as PILImage

import mast3r.utils.path_to_dust3r  # noqa: F401
from dust3r.inference import inference
from dust3r.utils.image import load_images
from mast3r.fast_nn import fast_reciprocal_NNs
from mast3r.model import AsymmetricMASt3R


REPO = Path(__file__).resolve().parents[3]
EXPECTED_MODEL_SHA256 = "0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
EXPECTED_MODEL_BYTES = 2_754_661_648
EXPECTED_MODEL_REVISION = "06e7259f34c3060f322df5cb0c7b9094f57e41fc"


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def finite_summary(value: Any) -> dict[str, Any]:
    if torch.is_tensor(value):
        array = value.detach().float().cpu().numpy()
    else:
        array = np.asarray(value)
    return {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "finite_count": int(np.count_nonzero(np.isfinite(array))),
        "value_count": int(array.size),
        "all_finite": bool(np.isfinite(array).all()),
        "min": float(np.nanmin(array)) if array.size else None,
        "max": float(np.nanmax(array)) if array.size else None,
    }


def git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={path}", "-C", str(path), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def parse_box(value: str) -> tuple[int, int, int, int]:
    box = tuple(int(part) for part in value.split(","))
    if len(box) != 4 or box[2] <= box[0] or box[3] <= box[1]:
        raise argparse.ArgumentTypeError(f"invalid xyxy crop: {value!r}")
    return box


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--image-a", type=Path, required=True)
    parser.add_argument("--image-b", type=Path, required=True)
    parser.add_argument("--crop-box-a", type=parse_box, required=True)
    parser.add_argument("--crop-box-b", type=parse_box, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--size", type=int, default=512)
    args = parser.parse_args()

    weights = args.model_dir / "model.safetensors"
    config = args.model_dir / "config.json"
    if args.model_dir.name != EXPECTED_MODEL_REVISION:
        raise RuntimeError(f"model revision path mismatch: {args.model_dir.name}")
    if not weights.exists() or not config.exists():
        raise FileNotFoundError(f"incomplete model snapshot: {args.model_dir}")
    weight_sha = sha256_file(weights)
    if weights.stat().st_size != EXPECTED_MODEL_BYTES or weight_sha != EXPECTED_MODEL_SHA256:
        raise RuntimeError(
            f"weight lock mismatch bytes={weights.stat().st_size} sha256={weight_sha}"
        )
    if not torch.cuda.is_available() and args.device.startswith("cuda"):
        raise RuntimeError("CUDA smoke requested but CUDA is unavailable")

    model = AsymmetricMASt3R.from_pretrained(str(args.model_dir)).to(args.device)
    model.eval()
    with tempfile.TemporaryDirectory(prefix="jointbuildgs_s3ap_smoke_") as tmp:
        crop_paths = [Path(tmp) / "crop_a.png", Path(tmp) / "crop_b.png"]
        for source, box, target in zip(
            [args.image_a, args.image_b],
            [args.crop_box_a, args.crop_box_b],
            crop_paths,
        ):
            with PILImage.open(source) as image:
                image.convert("RGB").crop(box).save(target)
        images = load_images([str(path) for path in crop_paths], size=args.size, verbose=False)
        with torch.inference_mode():
            output = inference([tuple(images)], model, args.device, batch_size=1, verbose=False)
    pred1 = output["pred1"]
    pred2 = output["pred2"]
    desc1 = pred1["desc"].squeeze(0).detach()
    desc2 = pred2["desc"].squeeze(0).detach()
    matches1, matches2 = fast_reciprocal_NNs(
        desc1,
        desc2,
        subsample_or_initxy1=8,
        device=args.device,
        dist="dot",
        block_size=2**13,
    )
    summaries = {
        "pred1_pts3d": finite_summary(pred1["pts3d"]),
        "pred2_pts3d_in_other_view": finite_summary(pred2["pts3d_in_other_view"]),
        "pred1_desc": finite_summary(pred1["desc"]),
        "pred2_desc": finite_summary(pred2["desc"]),
        "pred1_conf": finite_summary(pred1["conf"]),
        "pred2_conf": finite_summary(pred2["conf"]),
    }
    if not all(item["all_finite"] for item in summaries.values()):
        raise RuntimeError("non-finite MASt3R smoke output")
    if len(matches1) != len(matches2) or len(matches1) == 0:
        raise RuntimeError(f"invalid reciprocal matches: {len(matches1)} vs {len(matches2)}")

    mast3r_root = Path("/opt/mast3r")
    payload = {
        "schema": "jointbuildgs.s3ap.mast3r_smoke.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pass",
        "learning_runs_started": 0,
        "device": args.device,
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "model_id": "naver/MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric",
        "model_revision": EXPECTED_MODEL_REVISION,
        "model_sha256": weight_sha,
        "model_bytes": weights.stat().st_size,
        "config_sha256": sha256_file(config),
        "mast3r_commit": git_head(mast3r_root),
        "dust3r_commit": git_head(mast3r_root / "dust3r"),
        "croco_commit": git_head(mast3r_root / "dust3r/croco"),
        "images": [
            {"path": str(args.image_a), "sha256": sha256_file(args.image_a), "crop_box_xyxy": list(args.crop_box_a)},
            {"path": str(args.image_b), "sha256": sha256_file(args.image_b), "crop_box_xyxy": list(args.crop_box_b)},
        ],
        "load_size": args.size,
        "output": summaries,
        "reciprocal_match_count": int(len(matches1)),
        "matches1_shape": list(np.asarray(matches1).shape),
        "matches2_shape": list(np.asarray(matches2).shape),
        "finite_and_shape_check": "pass",
        "interpretation_or_verdict": None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "status=pass "
        f"matches={len(matches1)} "
        f"pts1={summaries['pred1_pts3d']['shape']} "
        f"pts2={summaries['pred2_pts3d_in_other_view']['shape']} "
        "finite=true"
    )


if __name__ == "__main__":
    main()

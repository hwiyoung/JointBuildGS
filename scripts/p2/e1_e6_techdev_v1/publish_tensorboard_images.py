from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image
from torch.utils.tensorboard import SummaryWriter


RUNS = (
    "E3_GS_IMAGE",
    "E4_GS_ALS_UNWEIGHTED",
    "E5_GS_ALS_WB",
    "E6_GS_LOD2_PLANES_DIAGNOSTIC",
)
RENDER_PATTERN = re.compile(r"it(?P<step>\d{6})_(?P<view>v\d+)_(?P<kind>rgb|depth)\.png")
SCHEMA = "jointbuildgs.p2.e1_e6.tensorboard_qualitative.v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def depth_preview(path: Path) -> np.ndarray:
    depth_code = np.asarray(Image.open(path), dtype=np.float32)
    valid = depth_code > 0
    normalized = np.zeros_like(depth_code, dtype=np.float32)
    if np.any(valid):
        low, high = np.percentile(depth_code[valid], (2.0, 98.0))
        if high <= low:
            high = low + 1.0
        normalized[valid] = np.clip((depth_code[valid] - low) / (high - low), 0.0, 1.0)
    red = np.clip(1.5 - np.abs(4.0 * normalized - 3.0), 0.0, 1.0)
    green = np.clip(1.5 - np.abs(4.0 * normalized - 2.0), 0.0, 1.0)
    blue = np.clip(1.5 - np.abs(4.0 * normalized - 1.0), 0.0, 1.0)
    preview = np.stack((red, green, blue), axis=-1)
    preview[~valid] = 0.0
    return np.rint(preview * 255).astype(np.uint8)


def publish_run(run_root: Path) -> dict:
    render_paths = sorted((run_root / "renders").glob("it*_v*_[rd][ge][bp]*.png"))
    render_paths = [path for path in render_paths if RENDER_PATTERN.fullmatch(path.name)]
    sanity_paths = sorted((run_root / "sanity").glob("*.png"))
    inputs = {
        str(path.relative_to(run_root)): sha256(path)
        for path in (*render_paths, *sanity_paths)
    }
    tb_root = run_root / "tb"
    receipt_path = tb_root / "qualitative_receipt.json"
    if receipt_path.is_file():
        previous = json.loads(receipt_path.read_text(encoding="utf-8"))
        if previous.get("schema") == SCHEMA and previous.get("inputs") == inputs:
            return previous

    writer = SummaryWriter(tb_root, filename_suffix=".qualitative")
    tags: set[str] = set()
    for path in render_paths:
        match = RENDER_PATTERN.fullmatch(path.name)
        assert match is not None
        step = int(match.group("step"))
        view = match.group("view")
        kind = match.group("kind")
        tag = f"qualitative/{view}/{kind}"
        if kind == "depth":
            image = depth_preview(path)
        else:
            image = np.asarray(Image.open(path).convert("RGB"))
        writer.add_image(tag, image, step, dataformats="HWC")
        tags.add(tag)
    for path in sanity_paths:
        tag = f"sanity/{path.stem}"
        writer.add_image(tag, np.asarray(Image.open(path).convert("RGB")), 0, dataformats="HWC")
        tags.add(tag)
    writer.add_text(
        "qualitative/provenance",
        "Existing checkpoint render PNGs published after training; no retraining and no checkpoint selection.",
        0,
    )
    writer.flush()
    writer.close()
    receipt = {
        "schema": SCHEMA,
        "run": run_root.name,
        "render_image_count": len(render_paths),
        "sanity_image_count": len(sanity_paths),
        "tensorboard_image_tags": sorted(tags),
        "inputs": inputs,
        "retraining_started": False,
        "checkpoint_selection_changed": False,
        "scientific_verdict": None,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    args = parser.parse_args()
    receipts = [publish_run(args.task_root / "runs" / run) for run in RUNS]
    print(json.dumps({"runs": len(receipts), "render_images": sum(item["render_image_count"] for item in receipts), "sanity_images": sum(item["sanity_image_count"] for item in receipts)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

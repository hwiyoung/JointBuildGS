"""Remap MatrixCity block-local EXR files to global indices.

After untar, each block's files are 0000.exr, 0001.exr, ... (block-local index).
We need to rename them to match the global images.bin ordering (0000.png..5620.png)
using pose/block_all/transforms_train.json mapping.

Symlinks are used (not copies) to save disk space (~72GB → ~0).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pose-json", default="data/matrixcity/small_city/aerial/pose/block_all/transforms_train.json")
    ap.add_argument("--block-base", default="data/matrixcity",
                    help="directory containing block_*_depth/ and block_*_normal/ subdirs")
    ap.add_argument("--out-depth", default="data/matrixcity/depth")
    ap.add_argument("--out-normal", default="data/matrixcity/normal")
    ap.add_argument("--use-copy", action="store_true", help="copy instead of symlink")
    args = ap.parse_args()

    with open(args.pose_json) as f:
        data = json.load(f)
    frames = data["frames"]
    print(f"pose json: {len(frames)} frames")

    out_d = Path(args.out_depth); out_d.mkdir(parents=True, exist_ok=True)
    out_n = Path(args.out_normal); out_n.mkdir(parents=True, exist_ok=True)
    base = Path(args.block_base)

    linked_d, linked_n, missing_d, missing_n = 0, 0, 0, 0
    for idx, fr in enumerate(frames):
        global_name = f"{idx:04d}.exr"
        fp = fr["file_path"]  # e.g. "../../train/block_1/0001.png"
        parts = fp.split("/")
        block = parts[-2]  # block_1
        stem = Path(parts[-1]).stem  # 0001

        # depth
        src_d = base / f"{block}_depth" / f"{stem}.exr"
        if src_d.exists():
            dst_d = out_d / global_name
            if dst_d.is_symlink() or dst_d.exists():
                dst_d.unlink()
            if args.use_copy:
                import shutil; shutil.copy2(src_d, dst_d)
            else:
                # relative symlink so it resolves the same inside Docker
                rel = os.path.relpath(src_d.resolve(), dst_d.parent.resolve())
                dst_d.symlink_to(rel)
            linked_d += 1
        else:
            missing_d += 1

        # normal
        src_n = base / f"{block}_normal" / f"{stem}.exr"
        if src_n.exists():
            dst_n = out_n / global_name
            if dst_n.is_symlink() or dst_n.exists():
                dst_n.unlink()
            if args.use_copy:
                import shutil; shutil.copy2(src_n, dst_n)
            else:
                rel = os.path.relpath(src_n.resolve(), dst_n.parent.resolve())
                dst_n.symlink_to(rel)
            linked_n += 1
        else:
            missing_n += 1

    print(f"depth: linked={linked_d}, missing={missing_d}")
    print(f"normal: linked={linked_n}, missing={missing_n}")


if __name__ == "__main__":
    main()

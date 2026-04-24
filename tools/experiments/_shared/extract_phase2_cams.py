"""Extract Phase 2 synthetic Pix4D camera poses + thumbnails.

Reads sparse/0/images.bin and produces:
  - cams.json: [{"name": "waypt_00_00_nadir.jpg", "pos": [x,y,z], "fwd": [dx,dy,dz]}, ...]
  - thumbs/<name>.jpg: 320px-wide JPEG thumbnails

All positions/vectors are in the scene.obj world frame (Y-down, ground at Y=0).

Usage:
    python tools/experiments/_shared/extract_phase2_cams.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.stage2.colmap_io import read_images_bin  # noqa: E402

SPARSE = ROOT / "results/phase2_synthesis/dataset/sparse/0/images.bin"
IMGDIR = ROOT / "results/phase2_synthesis/dataset/images"
OUTDIR = ROOT / "tools/experiments/_shared/phase2_cams"
THUMB_W = 800
JPEG_Q = 82


def main():
    imgs = read_images_bin(SPARSE)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    thumbdir = OUTDIR / "thumbs"
    thumbdir.mkdir(exist_ok=True)

    cams = []
    for img_id, im in sorted(imgs.items()):
        # world-to-camera: R, t. camera position in world: -R^T @ t.
        R = im.R()
        t = im.tvec
        pos = (-R.T @ t).tolist()
        # forward direction in world: R^T @ [0,0,1] (camera looks +Z in its frame)
        fwd = (R.T @ np.array([0, 0, 1])).tolist()
        name = Path(im.name).stem
        thumb_path = thumbdir / f"{name}.jpg"
        src = IMGDIR / im.name
        if not thumb_path.exists():
            try:
                with PILImage.open(src) as p:
                    ratio = THUMB_W / p.width
                    new_h = int(p.height * ratio)
                    p.thumbnail((THUMB_W, new_h))
                    if p.mode != "RGB":
                        p = p.convert("RGB")
                    p.save(thumb_path, "JPEG", quality=JPEG_Q)
            except Exception as e:
                print(f"  [thumb fail] {im.name}: {e}")
                continue
        cams.append({"name": name, "pos": pos, "fwd": fwd})

    (OUTDIR / "cams.json").write_text(json.dumps(cams))
    print(f"[extract] {len(cams)} cameras → {OUTDIR/'cams.json'}")
    print(f"[extract] thumbs dir: {thumbdir} ({len(list(thumbdir.glob('*.jpg')))} jpegs)")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw


PANELS = (
    ("semantic_gt_dense", "0.25 m geometry"),
    ("semantic_gt_rgb_sam_v2", "0.25 m + RGB/SAM"),
    ("semantic_gt_dense_scan_pilot_v1", "raw ULS geometry"),
    ("semantic_gt_dense_scan_rgb_sam_pilot_v1", "raw ULS + RGB/SAM"),
)


def valid_fraction(root: Path, stem: str) -> float:
    mask = imageio.imread(root / "masks" / f"{stem}.png")
    return float(np.count_nonzero(mask) / mask.size)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--view-names", nargs="+", required=True)
    args = parser.parse_args()

    task_root = args.task_root.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for view_name in args.view_names:
        stem = Path(view_name).stem
        tiles = []
        fractions = {}
        for directory, title in PANELS:
            root = task_root / "prep" / directory
            source = Image.open(root / "overlays" / f"{stem}.png").convert("RGB")
            fraction = valid_fraction(root, stem)
            fractions[directory] = fraction
            canvas = Image.new("RGB", (source.width, source.height + 48), (28, 30, 34))
            canvas.paste(source, (0, 48))
            draw = ImageDraw.Draw(canvas)
            draw.text((18, 16), f"{title} | valid {fraction:.1%}", fill=(255, 255, 255))
            tiles.append(canvas)
        width = max(tile.width for tile in tiles)
        height = max(tile.height for tile in tiles)
        comparison = Image.new("RGB", (width * 2, height * 2), (12, 12, 12))
        for index, tile in enumerate(tiles):
            comparison.paste(tile, ((index % 2) * width, (index // 2) * height))
        destination = output_root / f"{stem}_comparison.png"
        comparison.save(destination)
        rows.append({
            "view": view_name,
            "comparison": str(destination),
            "valid_fraction": fractions,
            "raw_geometry_gain_over_voxel025": (
                fractions["semantic_gt_dense_scan_pilot_v1"] - fractions["semantic_gt_dense"]
            ),
            "raw_rgb_sam_gain_over_voxel025_rgb_sam": (
                fractions["semantic_gt_dense_scan_rgb_sam_pilot_v1"]
                - fractions["semantic_gt_rgb_sam_v2"]
            ),
        })
    receipt = {
        "schema": "jointbuildgs.p2.e1_e6.semantic_dense_scan_pilot_comparison.v1",
        "layout": [title for _directory, title in PANELS],
        "views": rows,
        "scientific_verdict": None,
    }
    (output_root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

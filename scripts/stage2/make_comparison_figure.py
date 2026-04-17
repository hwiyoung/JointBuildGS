"""Create side-by-side comparison figures (pred | GT | diff) for Step 1-1 REPORT.

Reads existing renders from renders_final/ and stacks them into comparison panels.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import imageio.v2 as imageio
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--renders-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-views", type=int, default=4)
    args = ap.parse_args()

    rd = Path(args.renders_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for i in range(args.n_views):
        try:
            pred = imageio.imread(rd / f"v{i:02d}_rgb_pred.png")
            gt = imageio.imread(rd / f"v{i:02d}_rgb_gt.png")
        except FileNotFoundError:
            continue
        if pred.shape != gt.shape:
            continue
        # Per-pixel L1 diff (amplified ×3 for visibility)
        diff = np.clip(np.abs(pred.astype(np.int32) - gt.astype(np.int32)) * 3, 0, 255).astype(np.uint8)
        row = np.concatenate([pred, gt, diff], axis=1)
        rows.append(row)

    if not rows:
        print("No views found")
        return

    # Ensure same width (they should be, but just in case)
    w = min(r.shape[1] for r in rows)
    rows = [r[:, :w] for r in rows]

    # Add captions via text header (simple: just stack)
    panel = np.concatenate(rows, axis=0)
    imageio.imwrite(out_path, panel)
    print(f"wrote {out_path} shape={panel.shape}")


if __name__ == "__main__":
    main()

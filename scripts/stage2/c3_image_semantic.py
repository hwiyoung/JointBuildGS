#!/usr/bin/env python3
"""CLI for the offline exact-937 C3 image-only semantic producer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.stage2.c3_image_semantic import produce


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--producer-lock", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--asset-receipt", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    result = produce(
        image_root=args.image_root,
        input_manifest=args.input_manifest,
        lock_path=args.producer_lock,
        asset_root=args.asset_root,
        asset_receipt=args.asset_receipt,
        work_dir=args.work_dir,
        output_dir=args.output,
        device=args.device,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

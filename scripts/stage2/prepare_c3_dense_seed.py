#!/usr/bin/env python3
"""CLI for the exact common-base C3 dense-seed producer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.stage2.c3_dense_seed import DenseSeedConfig, produce_dense_seed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read the exact common dim_dense.ply once, count frozen 0.10/0.20/0.40 m "
            "voxel candidates, and publish only the finest candidate at or below 3M points."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--expected-input-sha256")
    parser.add_argument("--temp-parent", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    receipt = produce_dense_seed(
        DenseSeedConfig(
            source_path=args.input,
            output_path=args.output,
            receipt_path=args.receipt,
            expected_input_sha256=args.expected_input_sha256,
            temp_parent=args.temp_parent,
        )
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

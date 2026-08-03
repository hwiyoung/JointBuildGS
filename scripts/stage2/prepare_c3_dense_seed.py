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

from src.stage2.c3_dense_seed import (
    DenseSeedConfig,
    UTARGET199_NEUTRAL_CONTRACT,
    UTARGET199_NEUTRAL_MAX_DENSE_SEED_POINTS,
    UTARGET199_NEUTRAL_VOXEL_SPACINGS_M,
    produce_dense_seed,
    produce_utarget199_neutral_dense_seed,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read the exact common dim_dense.ply once, count the selected contract's "
            "frozen voxel candidates, and publish only the finest candidate under its cap."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--expected-input-sha256")
    parser.add_argument("--temp-parent", type=Path)
    parser.add_argument(
        "--utarget199-neutral",
        action="store_true",
        help="Use the exact unclassified geometry-only C3/C4/C5 common seed contract.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = DenseSeedConfig(
        source_path=args.input,
        output_path=args.output,
        receipt_path=args.receipt,
        expected_input_sha256=args.expected_input_sha256,
        temp_parent=args.temp_parent,
        voxel_spacings_m=(
            UTARGET199_NEUTRAL_VOXEL_SPACINGS_M
            if args.utarget199_neutral
            else (0.10, 0.20, 0.40)
        ),
        max_dense_points=(
            UTARGET199_NEUTRAL_MAX_DENSE_SEED_POINTS
            if args.utarget199_neutral
            else 3_000_000
        ),
        contract=(
            UTARGET199_NEUTRAL_CONTRACT
            if args.utarget199_neutral
            else "FIRST_WAVE_V2"
        ),
    )
    receipt = (
        produce_utarget199_neutral_dense_seed(config)
        if args.utarget199_neutral
        else produce_dense_seed(config)
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

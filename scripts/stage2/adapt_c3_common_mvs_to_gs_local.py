#!/usr/bin/env python3
"""CLI for the exact attested 1 m common-MVS to GS-local adapter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.stage2.c3_common_mvs_adapter import (
    CommonMvsAdapterConfig,
    adapt_common_mvs_to_gs_local,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the exact attested ASCII mvs_class26_v1.ply in one natural read, "
            "subtract the frozen GS-local shift, and add-once publish binary float32 XYZ."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    receipt = adapt_common_mvs_to_gs_local(
        CommonMvsAdapterConfig(
            source_path=args.input,
            output_path=args.output,
            receipt_path=args.receipt,
        )
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

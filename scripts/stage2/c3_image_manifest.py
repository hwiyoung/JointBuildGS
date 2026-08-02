#!/usr/bin/env python3
"""Build the exact-937 semantic input manifest from the compact Git ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.stage2.c3_image_semantic import build_input_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_input_manifest(args.output), sort_keys=True))


if __name__ == "__main__":
    main()

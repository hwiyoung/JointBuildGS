#!/usr/bin/env python3
"""Publish local E3 periodic RGB/depth renders with the existing E1-E6 tags."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.p2.e1_e6_techdev_v1.publish_tensorboard_images import publish_run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(publish_run(args.run_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create viewer registry additions for one checkpoint and two fusion arms."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))["selected"]
    specs = [
        {
            "id": "DIST0P1_BASELINE_7K",
            "label": "7k distortion 0.1 · alpha-only TSDF",
            "run_name": "E3_LOCAL_4906982_DIST0P1_BESTVAL7K_BASELINE",
            "step": int(selection["step"]),
            "default": False,
            "validation_selected": False,
            "checkpoint_sha256": selection["checkpoint_sha256"],
        },
        {
            "id": "DIST0P1_CONSENSUS3_7K",
            "label": "7k distortion 0.1 · SfM bounds + min 3-view TSDF",
            "run_name": "E3_LOCAL_4906982_DIST0P1_BESTVAL7K_CONSENSUS3",
            "step": int(selection["step"]),
            "default": False,
            "validation_selected": False,
            "checkpoint_sha256": selection["checkpoint_sha256"],
        },
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(specs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps({"status": "written", "variants": len(specs)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

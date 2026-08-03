#!/usr/bin/env python3
"""CLI for outcome-separated C3 development Stage-3 preparation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.p2.c3_development_stage3_v1.contract import (
    AddOnceStore,
    associate_development,
    finalize_technical,
    prepare_geometry,
    validate_contract,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("preflight")
    geometry = sub.add_parser("prepare-geometry")
    geometry.add_argument("--output-root", type=Path, required=True)
    geometry.add_argument("--checkpoint", type=Path, required=True)
    geometry.add_argument("--source-commit", required=True)
    geometry.add_argument("--run-id", required=True)
    associate = sub.add_parser("associate-development")
    associate.add_argument("--output-root", type=Path, required=True)
    associate.add_argument("--score-cells", type=Path, required=True)
    associate.add_argument("--source-commit", required=True)
    associate.add_argument("--run-id", required=True)
    final = sub.add_parser("finalize-technical")
    final.add_argument("--output-root", type=Path, required=True)
    final.add_argument("--source-commit", required=True)
    final.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.mode == "preflight":
        result = validate_contract()
    else:
        store = AddOnceStore(args.output_root)
        if args.mode == "prepare-geometry":
            result = prepare_geometry(
                store,
                checkpoint_path=args.checkpoint,
                source_commit=args.source_commit,
                run_id=args.run_id,
            )
        elif args.mode == "associate-development":
            result = associate_development(
                store,
                score_cells_path=args.score_cells,
                source_commit=args.source_commit,
                run_id=args.run_id,
            )
        else:
            result = finalize_technical(
                store,
                source_commit=args.source_commit,
                run_id=args.run_id,
            )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

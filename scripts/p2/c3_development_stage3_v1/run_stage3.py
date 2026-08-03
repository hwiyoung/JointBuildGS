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
    record_roofer_terminal,
    validate_contract,
    verify_roofer_terminal,
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
    verify = sub.add_parser("verify-roofer-terminal")
    verify.add_argument("--output-root", type=Path, required=True)
    verify.add_argument("--unit-id", required=True)
    record = sub.add_parser("record-roofer-terminal")
    record.add_argument("--output-root", type=Path, required=True)
    record.add_argument("--unit-id", required=True)
    record.add_argument("--exit-code", type=int, required=True)
    record.add_argument("--runtime-seconds", type=int, required=True)
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
        elif args.mode == "finalize-technical":
            result = finalize_technical(
                store,
                source_commit=args.source_commit,
                run_id=args.run_id,
            )
        elif args.mode == "verify-roofer-terminal":
            result = verify_roofer_terminal(store, unit_id=args.unit_id)
        else:
            result = record_roofer_terminal(
                store,
                unit_id=args.unit_id,
                exit_code=args.exit_code,
                runtime_seconds=args.runtime_seconds,
            )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

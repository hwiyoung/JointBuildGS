#!/usr/bin/env python3
"""CLI for bounded C4 U_target=199 post-processing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.p2.c4_utarget199_postprocess_v1.contract import (
    AddOnceStore,
    associate_population,
    complete_task,
    finalize,
    prepare_condition,
    record_failure,
    record_terminal,
    validate_config,
    verify_terminal,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("preflight")
    prepare = sub.add_parser("prepare-condition")
    prepare.add_argument("--output-root", type=Path, required=True)
    prepare.add_argument("--checkpoint", type=Path, required=True)
    prepare.add_argument("--source-commit", required=True)
    prepare.add_argument("--run-id", required=True)
    associate = sub.add_parser("associate")
    associate.add_argument("--output-root", type=Path, required=True)
    associate.add_argument("--current-uas-reference", type=Path, required=True)
    associate.add_argument("--source-commit", required=True)
    associate.add_argument("--run-id", required=True)
    record = sub.add_parser("record-terminal")
    record.add_argument("--output-root", type=Path, required=True)
    record.add_argument("--unit-id", required=True)
    record.add_argument("--exit-code", type=int, required=True)
    record.add_argument("--runtime-seconds", type=int, required=True)
    verify = sub.add_parser("verify-terminal")
    verify.add_argument("--output-root", type=Path, required=True)
    verify.add_argument("--unit-id", required=True)
    final = sub.add_parser("finalize")
    final.add_argument("--output-root", type=Path, required=True)
    final.add_argument("--artifact-root", type=Path, required=True)
    final.add_argument("--source-commit", required=True)
    final.add_argument("--run-id", required=True)
    complete = sub.add_parser("complete")
    complete.add_argument("--output-root", type=Path, required=True)
    failure = sub.add_parser("record-failure")
    failure.add_argument("--output-root", type=Path, required=True)
    failure.add_argument("--stage", required=True)
    failure.add_argument("--exit-code", type=int, required=True)
    failure.add_argument("--source-commit", required=True)
    failure.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.mode == "preflight":
        result = validate_config()
    else:
        store = AddOnceStore(args.output_root)
        if args.mode == "prepare-condition":
            result = prepare_condition(
                store,
                checkpoint_path=args.checkpoint,
                source_commit=args.source_commit,
                run_id=args.run_id,
            )
        elif args.mode == "associate":
            result = associate_population(
                store,
                current_uas_reference_path=args.current_uas_reference,
                source_commit=args.source_commit,
                run_id=args.run_id,
            )
        elif args.mode == "record-terminal":
            result = record_terminal(
                store,
                unit_id=args.unit_id,
                exit_code=args.exit_code,
                runtime_seconds=args.runtime_seconds,
            )
        elif args.mode == "verify-terminal":
            result = verify_terminal(store, args.unit_id)
        elif args.mode == "finalize":
            result = finalize(
                store,
                artifact_root=args.artifact_root,
                source_commit=args.source_commit,
                run_id=args.run_id,
            )
        elif args.mode == "complete":
            result = complete_task(store)
        else:
            result = record_failure(
                store,
                stage=args.stage,
                exit_code=args.exit_code,
                source_commit=args.source_commit,
                run_id=args.run_id,
            )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

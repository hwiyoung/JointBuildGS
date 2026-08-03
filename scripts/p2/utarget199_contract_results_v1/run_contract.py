#!/usr/bin/env python3
"""CLI for the U_target=199 C1/C2/C3 contract-result census."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.p2.utarget199_contract_results_v1.contract import (
    AddOnceStore,
    finalize,
    prepare,
    record_roofer_terminal,
    validate_config,
    verify_terminal,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("preflight")
    prep = sub.add_parser("prepare")
    prep.add_argument("--output-root", type=Path, required=True)
    prep.add_argument("--c1-c2-source-root", type=Path, required=True)
    prep.add_argument("--c3-source-root", type=Path, required=True)
    prep.add_argument("--source-commit", required=True)
    prep.add_argument("--run-id", required=True)
    record = sub.add_parser("record-roofer-terminal")
    record.add_argument("--output-root", type=Path, required=True)
    record.add_argument("--unit-id", required=True)
    record.add_argument("--exit-code", type=int, required=True)
    record.add_argument("--runtime-seconds", type=int, required=True)
    verify = sub.add_parser("verify-terminal")
    verify.add_argument("--output-root", type=Path, required=True)
    verify.add_argument("--unit-id", required=True)
    final = sub.add_parser("finalize")
    final.add_argument("--output-root", type=Path, required=True)
    final.add_argument("--reference-cells", type=Path, required=True)
    final.add_argument("--g2-receipts", type=Path, required=True)
    final.add_argument("--source-commit", required=True)
    final.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.mode == "preflight":
        result = validate_config()
    else:
        store = AddOnceStore(args.output_root)
        if args.mode == "prepare":
            result = prepare(
                store,
                c1_c2_source_root=args.c1_c2_source_root,
                c3_source_root=args.c3_source_root,
                source_commit=args.source_commit,
                run_id=args.run_id,
            )
        elif args.mode == "record-roofer-terminal":
            result = record_roofer_terminal(
                store,
                unit_id=args.unit_id,
                exit_code=args.exit_code,
                runtime_seconds=args.runtime_seconds,
            )
        elif args.mode == "verify-terminal":
            result = verify_terminal(store, args.unit_id)
        else:
            result = finalize(
                store,
                reference_cells=args.reference_cells,
                g2_receipts=args.g2_receipts,
                source_commit=args.source_commit,
                run_id=args.run_id,
            )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

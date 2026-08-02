#!/usr/bin/env python3
"""CLI for the bounded C1/C2 development feasibility pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.p2_baselines.c1_c2_feasibility_pilot_v1.contract import (
    AddOnceStore,
    execution_units,
    finalize,
    next_synthetic_action,
    next_attempt,
    prepare_scientific,
    prepare_synthetic,
    promote,
    record_attempt,
    validate_contract,
    verify_synthetic,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("preflight")
    smoke = sub.add_parser("prepare-synthetic")
    smoke.add_argument("--output-root", type=Path, required=True)
    smoke_action = sub.add_parser("next-synthetic")
    smoke_action.add_argument("--output-root", type=Path, required=True)
    smoke_action.add_argument("--machine-lines", action="store_true")
    verify = sub.add_parser("verify-synthetic")
    verify.add_argument("--output-root", type=Path, required=True)
    verify.add_argument("--roofer-output", type=Path, required=True)
    verify.add_argument("--exit-code", type=int, required=True)
    prepare = sub.add_parser("prepare-scientific")
    prepare.add_argument("--output-root", type=Path, required=True)
    prepare.add_argument("--c1-grid", type=Path, required=True)
    prepare.add_argument("--c1-checkpoint", type=Path, required=True)
    prepare.add_argument("--c2-ply", type=Path, required=True)
    prepare.add_argument("--c2-checkpoint", type=Path, required=True)
    prepare.add_argument("--reference-cells", type=Path, required=True)
    prepare.add_argument("--source-commit", required=True)
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--handoff-id", required=True)
    prepare.add_argument("--accepted-receipt", type=Path, required=True)
    prepare.add_argument("--accepted-commit", required=True)
    prepare.add_argument("--project-image-id", required=True)
    prepare.add_argument("--artifact-root-token", required=True)
    units = sub.add_parser("execution-units")
    units.add_argument("--output-root", type=Path, required=True)
    attempt = sub.add_parser("next-attempt")
    attempt.add_argument("--output-root", type=Path, required=True)
    attempt.add_argument("--unit-id", required=True)
    attempt.add_argument("--machine-lines", action="store_true")
    record = sub.add_parser("record-attempt")
    record.add_argument("--output-root", type=Path, required=True)
    record.add_argument("--unit-id", required=True)
    record.add_argument("--attempt-number", type=int, required=True)
    record.add_argument("--exit-code", type=int, required=True)
    record.add_argument("--runtime-seconds", type=float, required=True)
    record.add_argument("--peak-memory-bytes", type=int)
    record.add_argument("--peak-memory-unavailable-reason")
    final = sub.add_parser("finalize")
    final.add_argument("--output-root", type=Path, required=True)
    promotion = sub.add_parser("promote")
    promotion.add_argument("--output-root", type=Path, required=True)
    promotion.add_argument("--repo-root", type=Path, required=True)
    promotion.add_argument("--promotion-parent-commit", required=True)
    args = parser.parse_args()
    if args.mode == "preflight":
        result = validate_contract()
    else:
        store = AddOnceStore(args.output_root)
        if args.mode == "prepare-synthetic":
            result = prepare_synthetic(store)
        elif args.mode == "next-synthetic":
            result = next_synthetic_action(store)
        elif args.mode == "verify-synthetic":
            result = verify_synthetic(store, args.roofer_output, args.exit_code)
        elif args.mode == "prepare-scientific":
            result = prepare_scientific(
                store,
                c1_grid_path=args.c1_grid,
                c1_checkpoint_path=args.c1_checkpoint,
                c2_ply_path=args.c2_ply,
                c2_checkpoint_path=args.c2_checkpoint,
                reference_cells_path=args.reference_cells,
                source_commit=args.source_commit,
                run_id=args.run_id,
                handoff_id=args.handoff_id,
                accepted_receipt_path=args.accepted_receipt,
                accepted_commit=args.accepted_commit,
                project_image_id=args.project_image_id,
                artifact_root_token=args.artifact_root_token,
            )
        elif args.mode == "execution-units":
            result = execution_units(store)
        elif args.mode == "next-attempt":
            result = next_attempt(store, args.unit_id)
        elif args.mode == "finalize":
            result = finalize(store)
        elif args.mode == "promote":
            result = promote(store, args.repo_root, args.promotion_parent_commit)
        else:
            result = record_attempt(
                store, args.unit_id, args.attempt_number, args.exit_code, args.runtime_seconds,
                args.peak_memory_bytes, args.peak_memory_unavailable_reason,
            )
    if args.mode in {"next-attempt", "next-synthetic"} and args.machine_lines:
        print(result["action"])
        print(result.get("attempt_number", 0))
    else:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.mode == "record-attempt" and result.get("status") == "RETRY_AUTHORIZED_INFRASTRUCTURE_ONLY":
        raise SystemExit(75)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""CLI for the add-once R4 finalize-only recovery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.p2_baselines.c1_c2_feasibility_pilot_finalize_recovery_r4_v1.contract import (
    AddOnceStore,
    finalize_recovery,
    promote_recovery,
    validate_execution_authority,
    validate_recovery_contract,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("preflight")
    authority = sub.add_parser("authority-preflight")
    authority.add_argument("--source-closed-receipt", type=Path, required=True)
    authority.add_argument("--accepted-receipt", type=Path, required=True)
    authority.add_argument("--source-commit", required=True)
    authority.add_argument("--accepted-commit", required=True)
    authority.add_argument("--project-image-id", required=True)
    authority.add_argument("--run-id", required=True)
    recover = sub.add_parser("recover-finalize")
    recover.add_argument("--source-root", type=Path, required=True)
    recover.add_argument("--output-root", type=Path, required=True)
    recover.add_argument("--source-closed-receipt", type=Path, required=True)
    recover.add_argument("--accepted-receipt", type=Path, required=True)
    recover.add_argument("--source-commit", required=True)
    recover.add_argument("--accepted-commit", required=True)
    recover.add_argument("--project-image-id", required=True)
    recover.add_argument("--run-id", required=True)
    recover.add_argument("--handoff-id", required=True)
    recover.add_argument("--artifact-root-token", required=True)
    promote = sub.add_parser("promote")
    promote.add_argument("--output-root", type=Path, required=True)
    promote.add_argument("--repo-root", type=Path, required=True)
    promote.add_argument("--promotion-parent-commit", required=True)
    args = parser.parse_args()
    if args.mode == "preflight":
        result = validate_recovery_contract()
    elif args.mode == "authority-preflight":
        result = validate_execution_authority(
            source_closed_receipt_path=args.source_closed_receipt,
            accepted_receipt_path=args.accepted_receipt,
            source_commit=args.source_commit,
            accepted_commit=args.accepted_commit,
            project_image_id=args.project_image_id,
            run_id=args.run_id,
        )
    elif args.mode == "recover-finalize":
        result = finalize_recovery(
            AddOnceStore(args.output_root),
            source_root=args.source_root,
            source_closed_receipt_path=args.source_closed_receipt,
            accepted_receipt_path=args.accepted_receipt,
            source_commit=args.source_commit,
            accepted_commit=args.accepted_commit,
            project_image_id=args.project_image_id,
            run_id=args.run_id,
            handoff_id=args.handoff_id,
            artifact_root_token=args.artifact_root_token,
        )
    else:
        result = promote_recovery(
            AddOnceStore(args.output_root), args.repo_root, args.promotion_parent_commit,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

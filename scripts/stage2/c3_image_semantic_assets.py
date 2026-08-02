#!/usr/bin/env python3
"""Verify, explicitly fetch, or audit the C3-only GroundedSAM runtime assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.stage2.c3_image_semantic_assets import (
    audit_c3_runtime,
    fetch_c3_asset_bundle,
    load_c3_contract,
    verify_c3_asset_receipt,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("configs/stage2/c3_image_semantic_runtime_v1.json"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify", help="offline live-byte receipt verification")
    verify.add_argument("--asset-root", type=Path, required=True)
    verify.add_argument("--asset-receipt", type=Path, required=True)

    fetch = subparsers.add_parser("fetch", help="explicit add-once network fetch")
    fetch.add_argument("--asset-root", type=Path, required=True)
    fetch.add_argument("--repository-root", type=Path, required=True)
    fetch.add_argument(
        "--allow-network-fetch",
        action="store_true",
        help="required acknowledgement that this command performs network downloads",
    )

    subparsers.add_parser("audit-runtime", help="audit the running C3 container")
    args = parser.parse_args()
    contract = load_c3_contract(args.contract)
    if args.command == "verify":
        assets = verify_c3_asset_receipt(
            contract, args.contract, args.asset_root, args.asset_receipt
        )
        result = {
            "verified": True,
            "assets": {key: str(value) for key, value in assets.items()},
            "network_accessed": False,
            "scientific_verdict": None,
        }
    elif args.command == "fetch":
        if not args.allow_network_fetch:
            parser.error("fetch requires --allow-network-fetch")
        result = fetch_c3_asset_bundle(
            contract, args.contract, args.asset_root, args.repository_root
        )
    else:
        result = audit_c3_runtime(contract)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

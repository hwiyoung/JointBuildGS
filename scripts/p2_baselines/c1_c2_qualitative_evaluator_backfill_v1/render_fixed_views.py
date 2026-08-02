#!/usr/bin/env python3
"""CLI for the C1/C2 fixed-view qualitative visualization supplement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.visualization.fixed_view_qualitative import render_from_config


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--config", type=Path, required=True)
    value.add_argument("--repository-root", type=Path, required=True)
    value.add_argument("--artifact-root", type=Path, required=True)
    value.add_argument("--r3-root", type=Path, required=True)
    value.add_argument("--compact-reference-cells", type=Path)
    value.add_argument("--output-dir", type=Path, required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    manifest = render_from_config(
        config_path=args.config,
        repository_root=args.repository_root,
        artifact_root=args.artifact_root,
        r3_root=args.r3_root,
        output_dir=args.output_dir,
        compact_reference_cells_path=args.compact_reference_cells,
    )
    print(json.dumps({"status": manifest["status"], "case_sheets": len(manifest["case_sheets"]), "scientific_verdict": None}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

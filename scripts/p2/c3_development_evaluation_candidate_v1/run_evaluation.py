from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.evaluation.c3_dev_diagnostics_v1.evaluator import evaluate, prepare


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--c3-root", type=Path, required=True)
    prep.add_argument("--output-root", type=Path, required=True)
    run = sub.add_parser("evaluate")
    run.add_argument("--c3-root", type=Path, required=True)
    run.add_argument("--score-cells", type=Path, required=True)
    run.add_argument("--c1-c2-diagnostics", type=Path, required=True)
    run.add_argument("--c1-c2-source-root", type=Path, required=True)
    run.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.c3_root, args.output_root) if args.mode == "prepare" else evaluate(
        args.c3_root, args.score_cells, args.c1_c2_diagnostics, args.c1_c2_source_root, args.output_root
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

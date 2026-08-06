from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.p2.e1_e6_techdev_v1.configuration import (
    e4_e5_scientific_diff,
    materialize_config,
    write_runtime_config,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("condition", choices=("E3", "E4", "E5", "E6"))
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--max-iter", type=int)
    parser.add_argument("--als-depth-weight", type=float)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    config = materialize_config(
        args.condition,
        repository_root=args.repository_root.resolve(),
        artifact_root=args.artifact_root.resolve(),
        max_iter=args.max_iter,
        als_depth_weight=args.als_depth_weight,
    )
    if args.out_dir is not None:
        config["out_dir"] = str(args.out_dir.resolve())
        if args.condition == "E5" and args.als_depth_weight is not None:
            config["condition_id"] = f"E5_LAMBDA_GRID_{args.als_depth_weight:g}"
    write_runtime_config(config, args.output.resolve())
    if args.condition in {"E4", "E5"}:
        peer = "E5" if args.condition == "E4" else "E4"
        peer_config = materialize_config(
            peer,
            repository_root=args.repository_root.resolve(),
            artifact_root=args.artifact_root.resolve(),
            max_iter=args.max_iter,
            als_depth_weight=args.als_depth_weight,
        )
        diff = e4_e5_scientific_diff(config, peer_config)
        if diff:
            raise RuntimeError(f"E4/E5 forbidden scientific config differences: {diff}")
    print(json.dumps({"condition": args.condition, "output": str(args.output.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

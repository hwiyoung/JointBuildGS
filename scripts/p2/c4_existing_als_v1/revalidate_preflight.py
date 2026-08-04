#!/usr/bin/env python3
"""Re-run the final gradient and 22,000 MiB memory gate without rewriting priors."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from scripts.p2.c4_existing_als_v1.prepare_prior import atomic_json, gradient_and_memory_preflight


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    prior = next(path for path in sorted((args.artifact_root / "prior/views").glob("*.npz")) if path.stat().st_size > 1000)
    gradient = gradient_and_memory_preflight(prior)
    if gradient["gpu_free_bytes_before_training"] < 22_000 * 1024**2:
        raise RuntimeError("22,000 MiB GPU free-memory gate failed")
    receipt = {
        "schema": "jointbuildgs.p2.c4_existing_als_final_preflight.v1",
        "status": "210-PASSED_NONZERO_GRADIENT_AND_22000MIB_GPU_GATE",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sample_prior": str(prior),
        "gradient_and_gpu_memory": gradient,
        "scientific_verdict": None,
    }
    atomic_json(args.artifact_root / "control/210-c4-final-preflight-passed.json", receipt)
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()

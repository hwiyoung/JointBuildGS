#!/usr/bin/env python3
"""Convert per-run diagnostics.jsonl -> TensorBoard event files.

diagnostics.jsonl stays the artifact-of-record (receipt-friendly, network-none
safe); this adapter mirrors it into <run>/tb/ so a host-side TensorBoard can
serve the same curves. Idempotent: each pass rewrites a run's tb dir only when
the jsonl grew. --loop N re-converts every N seconds (live mode during sweeps).

Usage (container):
  python diag_to_tb.py [--root PATH ...] [--loop 30]
Then on the host:
  tensorboard --logdir <artifacts>/phase-payloads/p2/arrgs_v1/P2-ARRGS-ANCHOR-v1/runs \
              --port 8886 --bind_all
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

DEFAULT_ROOTS = [
    "/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1/P2-ARRGS-ANCHOR-v1/runs",
]


def convert_run(run_dir: Path, state: dict) -> bool:
    src = run_dir / "diagnostics.jsonl"
    if not src.is_file():
        return False
    size = src.stat().st_size
    if state.get(str(run_dir)) == size:
        return False
    from torch.utils.tensorboard import SummaryWriter
    tb = run_dir / "tb"
    if tb.exists():
        shutil.rmtree(tb)
    w = SummaryWriter(log_dir=str(tb))
    for ln in open(src):
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue  # partially-flushed last line of a live run
        it = r["iter"]
        for k, v in r.get("loss", {}).items():
            w.add_scalar(f"loss/{k}", v, it)
        for k, v in r.get("occ", {}).items():
            w.add_scalar(f"occ/{k}", v, it)
        w.add_scalar("lam/bin", r.get("lam_bin", 0.0), it)
    w.close()
    state[str(run_dir)] = size
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", action="append", default=None)
    ap.add_argument("--loop", type=int, default=0)
    args = ap.parse_args()
    roots = [Path(r) for r in (args.root or DEFAULT_ROOTS)]
    state = {}
    while True:
        n = 0
        for root in roots:
            if not root.is_dir():
                continue
            for run_dir in sorted(root.iterdir()):
                if run_dir.is_dir() and convert_run(run_dir, state):
                    n += 1
        print(f"[diag_to_tb] converted {n} run(s)", flush=True)
        if not args.loop:
            break
        time.sleep(args.loop)


if __name__ == "__main__":
    main()

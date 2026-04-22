"""FC-2: Measure actual iterations/second for Phase 2 training setup.

Runs 500 iters of baseline training, measures warm-up + steady-state throughput,
extrapolates full 30k training time for planning.

Usage:
    python scripts/phase2_synthesis/benchmark_iter_speed.py

Output:
    /tmp/fc2_benchmark.json with timings + 30k extrapolation
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path


SMOKE_CFG = "configs/phase2_smoke.yaml"
N_ITER = 500
OUT = Path("/tmp/fc2_benchmark.json")


def main():
    # Patch smoke config to 500 iter
    import yaml
    cfg_path = Path(SMOKE_CFG)
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["max_iter"] = N_ITER
    cfg["out_dir"] = "/workspace/JointBuildGS/results/phase2_synthesis/smoke_fc2"
    cfg["eval_every"] = N_ITER + 1   # skip eval
    cfg["ckpt_every"] = N_ITER + 1   # skip ckpt
    tmp_cfg = Path("/tmp/phase2_fc2.yaml")
    tmp_cfg.write_text(yaml.safe_dump(cfg))

    print(f"[fc2] running {N_ITER}-iter benchmark …")
    t0 = time.time()
    proc = subprocess.run(
        ["python", "-m", "src.stage2.train", "--config", str(tmp_cfg)],
        cwd="/workspace/JointBuildGS", capture_output=True, text=True,
    )
    dt = time.time() - t0

    # Parse tqdm output for steady-state rate
    log = proc.stdout + proc.stderr
    last_rate = None
    for line in log.splitlines():
        if "it/s" in line:
            # tqdm format:  ' ##%|##| 500/500 [00:35<00:00, 14.03it/s, ...'
            for tok in line.split(","):
                tok = tok.strip()
                if tok.endswith("it/s"):
                    try:
                        last_rate = float(tok.replace("it/s", "").strip().split()[-1])
                    except ValueError:
                        pass
    rate_mean = N_ITER / dt

    extrapolation_30k_h = (30000 / rate_mean) / 3600 if rate_mean > 0 else None
    extrapolation_30k_h_peak = (30000 / last_rate) / 3600 if (last_rate and last_rate > 0) else None

    result = {
        "n_iter": N_ITER,
        "wall_time_sec": dt,
        "mean_rate_it_per_s": rate_mean,
        "last_tqdm_rate_it_per_s": last_rate,
        "return_code": proc.returncode,
        "extrapolation": {
            "30k_at_mean_rate_h": extrapolation_30k_h,
            "30k_at_peak_rate_h": extrapolation_30k_h_peak,
            "4conds_30k_at_mean_rate_h": (4 * 30000 / rate_mean) / 3600 if rate_mean > 0 else None,
            "4conds_30k_at_peak_rate_h": (4 * 30000 / last_rate) / 3600 if (last_rate and last_rate > 0) else None,
        },
    }
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

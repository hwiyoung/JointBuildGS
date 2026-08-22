#!/usr/bin/env python3
"""D2a corridor smoke host driver: rerun the sealed exact-55 E4 rig with a
delta-shifted ALS prior, in a fresh Phase-D smoke namespace.

Strategy: import the sealed `e4_local_4906982_55v_als_prior_v1/run.py` driver
module and repoint its namespace constants (task root, run root, runtime
config, prior receipt) plus a `materialized()` wrapper that swaps in the
delta prior directory and smoke ids. Every stage function (preflight →
binding-probe → smoke → fork-7k → train-to-12k → dose-gate → train) then runs
byte-identically on the smoke namespace. Single substantive difference from
the sealed run: the prior bytes carry the synthetic +X delta.

Purpose: plumbing validation + a first GS(delta) preview before the full-scene
D2b nights. Non-confirmatory; scientific_verdict stays null.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
SMOKE_REL = "phase-payloads/p2/journal1_phase_d_v1/P2-JOURNAL1-PHASE-D-v1/corridor_smoke/GS55_dx050"
SMOKE_ROOT = ARTIFACT_ROOT / SMOKE_REL
DELTA = 0.5


def load_e4():
    spec = importlib.util.spec_from_file_location(
        "e4_smoke_rig", REPO / "scripts/p2/e4_local_4906982_55v_als_prior_v1/run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=(
        "prepare-prior", "preflight", "binding-probe", "smoke", "fork-7k",
        "train-to-12k", "dose-gate", "train", "all"))
    args = parser.parse_args()

    e4 = load_e4()
    container_smoke = "/artifacts/JointBuildGS/" + SMOKE_REL

    # Repoint the sealed rig to the Phase-D smoke namespace.
    e4.TASK_ID = "P2-JOURNAL1-PHASE-D-v1-D2A"
    e4.TASK_ROOT = SMOKE_ROOT
    e4.PRIOR_RECEIPT = SMOKE_ROOT / "control/200-55v-als-prior-preflight-passed.json"
    e4.RUN_ROOT = SMOKE_ROOT / "arms/E4_ALS_PRIOR_ONLY/R1"
    e4.RUNTIME_CONFIG = SMOKE_ROOT / "control/runtime_configs/e4_als_prior_only_r1.yaml"
    e4.base.TASK_ID = e4.TASK_ID
    e4.base.TASK_ROOT = SMOKE_ROOT

    original_materialized = e4.materialized

    def materialized_delta():
        body = original_materialized()
        body["task_id"] = e4.TASK_ID
        body["run_id"] = "E4_ALS_PRIOR_ONLY_R1_DX050"
        body["out_dir"] = e4.container_path(e4.RUN_ROOT)
        body["external_als_prior_dir"] = container_smoke + "/prior/views"
        return body

    e4.materialized = materialized_delta

    def prepare_prior() -> None:
        receipt = e4.PRIOR_RECEIPT
        if receipt.is_file():
            print("[d2a] prior already receipted")
            return
        SMOKE_ROOT.mkdir(parents=True, exist_ok=True)
        (SMOKE_ROOT / "cache/torch_extensions").mkdir(parents=True, exist_ok=True)
        argv = e4.base.docker_base(gpu=True) + [
            "python", "-B", "-m", "scripts.p2.journal1_phase_d_v1.d2a_prepare_prior_delta",
            "--smoke-root", container_smoke, "--delta-xy-east-m", str(DELTA),
        ]
        proc = subprocess.run([str(v) for v in argv], text=True)
        if proc.returncode != 0:
            raise RuntimeError("delta prior preparation failed")

    stages = {
        "prepare-prior": prepare_prior,
        "preflight": e4.preflight,
        "binding-probe": e4.binding_probe,
        "smoke": e4.smoke,
        "fork-7k": e4.fork_7k,
        "train-to-12k": e4.train_to_12k,
        "dose-gate": e4.dose_gate,
        "train": e4.train,
    }
    order = ["prepare-prior", "preflight", "binding-probe", "smoke", "fork-7k",
             "train-to-12k", "dose-gate", "train"]
    todo = order if args.stage == "all" else [args.stage]
    for name in todo:
        print(f"[d2a] === {name} ===", flush=True)
        stages[name]()
        print(f"[d2a] {name} done", flush=True)
    print(json.dumps({"smoke_root": str(SMOKE_ROOT), "delta_xy_east_m": DELTA,
                       "scientific_verdict": None}))


if __name__ == "__main__":
    main()

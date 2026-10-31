#!/usr/bin/env bash
set -euo pipefail
SCRIPT=$(cd "$(dirname "$0")" && pwd)
export TARGET_LANE=b173
export MEM=32
bash "$SCRIPT/run_cpu.sh" b173-patches b173_uncert.py patches
IMG=jointbuildgs:geogs-conf-guided-v1 bash "$SCRIPT/run_cpu.sh" b173-mvs b173_uncert.py mvs
bash "$SCRIPT/run_cpu.sh" b173-als b173_uncert.py als
bash "$SCRIPT/run_cpu.sh" b173-rings b173_uncert.py rings

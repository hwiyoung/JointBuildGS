#!/usr/bin/env bash
# PHD-MAIN-STAGE1-v1: run the CPU jobs of a file in parallel (each line: <tag> <script.py> [args ...]) with run_cpu.sh.
#   bash run_jobs.sh <jobs.txt> <parallel> [cpus per job]
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
jobs=$1; par=$2; cpus=${3:-12}
CPUS=$cpus xargs -P "$par" -L 1 bash "$HERE/run_cpu.sh" < "$jobs" > /dev/null

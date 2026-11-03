#!/usr/bin/env bash
# Exact own orchestration PIDs, captured before safe-merger handoff.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$REPO"
for worker in 2311292 2312150; do
 while [[ -r /proc/$worker/stat ]]; do
  state=$(ps -p "$worker" -o stat=)
  [[ "$state" == Z* ]] && break
  sleep 10
 done
done
for orchestration in 2257284 2292380 2089336 2089400; do
 if [[ -r /proc/$orchestration/cmdline ]]; then
  command=$(tr '\0' ' ' < "/proc/$orchestration/cmdline")
  [[ "$command" == *main_rescore_v1/compare_b173_lane.sh* || "$command" == *main_rescore_v1/run_mesh_named.sh* ]] || exit 1
  kill -KILL "$orchestration"
 fi
done
bash scripts/phd/main_rescore_v1/compare_b173_resume.sh A & a=$!
bash scripts/phd/main_rescore_v1/compare_b173_resume.sh B & b=$!
wait "$a";wait "$b"

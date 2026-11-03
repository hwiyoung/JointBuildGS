#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
tag=$1
name="jbgs-judgecheck-$tag"
bash "$REPO/scripts/phd/main_judgecheck_v1/run_gpu_reply2.sh" "$@" &
child=$!
guard=''
cleanup() { if [[ -n "$guard" ]]; then kill "$guard" 2>/dev/null || true; fi; }
trap cleanup EXIT
while kill -0 "$child" 2>/dev/null; do
  if docker inspect "$name" >/dev/null 2>&1; then
    bash "$REPO/scripts/phd/main_judgecheck_v1/gpu_guard_reply2.sh" "$name" &
    guard=$!
    break
  fi
  sleep 1
done
wait "$child"

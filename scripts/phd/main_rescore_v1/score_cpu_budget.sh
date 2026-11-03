#!/usr/bin/env bash
# Update only this task's already queued scorers; never touch FINALTRAIN.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
declare -A updated=()
while [[ ! -f "$REPO/docs/experiments/phd/main_rescore_v1/B173주변_비교방법_채점.md" ]]; do
 while IFS= read -r name; do
  [[ "$name" == jbgs-rescore-score-* ]] || continue
  [[ -z "${updated[$name]:-}" ]] || continue
  if docker update --cpus 16 "$name" >/dev/null 2>&1; then
   updated[$name]=1
   printf -- '- %s: %s CPU 상한 16 적용; 메모리/우선순위 유지.\n' "$(date --iso-8601=seconds)" "$name" >> "$REPO/docs/experiments/phd/main_rescore_v1/progress.md"
  fi
 done < <(docker ps --format '{{.Names}}' --filter name=jbgs-rescore-score)
 sleep 15
done

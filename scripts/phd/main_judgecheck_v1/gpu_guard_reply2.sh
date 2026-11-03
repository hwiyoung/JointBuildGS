#!/usr/bin/env bash
set -euo pipefail
name=$1
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1
record="$OUT/r2/resources/${name}_gpu_wait.tsv"
while true; do
  state=$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null) || exit 0
  [[ "$state" == running || "$state" == paused ]] || exit 0
  own=$(docker top "$name" -eo pid | tail -n +2 | tr -d ' ')
  other=''
  while IFS=, read -r pid process; do
    pid=${pid// /}
    [[ "$process" == *gnome-remote-desktop* || "$process" == *'/usr/share/rustdesk/rustdesk'* || -z "$pid" ]] && continue
    if ! rg -qx "$pid" <<< "$own"; then other="$other $pid"; fi
  done < <(nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader)
  if [[ -n "$other" && "$state" == running ]]; then
    docker pause "$name" >/dev/null
    printf '%s\tpause\t%s\n' "$(date -Is)" "$other" >> "$record"
    printf 'GPU_WAIT %s other PIDs:%s\n' "$name" "$other"
  elif [[ -z "$other" && "$state" == paused ]]; then
    docker unpause "$name" >/dev/null
    printf '%s\tresume\tno_other_research_compute\n' "$(date -Is)" >> "$record"
    printf 'GPU_RESUME %s\n' "$name"
  fi
  sleep 5
done

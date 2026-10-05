#!/usr/bin/env bash
set -euo pipefail
attempt=${1:?absolute frozen attempt path}
test -s "$attempt/launch_receipt.json"
test -s "$attempt/source_snapshot/scripts/phd/source_selected_2dgs_v1/run_queue.sh"
test ! -e "$attempt/queue_started.txt"
test ! -e "$attempt/queue.pid"
nohup setsid bash "$attempt/source_snapshot/scripts/phd/source_selected_2dgs_v1/run_queue.sh" "$attempt" \
  > "$attempt/queue.log" 2>&1 < /dev/null &
queue_pid=$!
printf '%s\n' "$queue_pid" > "$attempt/queue.pid"
printf 'BACKGROUND_PID=%s\n' "$queue_pid"

#!/usr/bin/env bash
set -euo pipefail
geogs_fd_code="${1:?code}"
geogs_fd_task="${2:?task}"
geogs_fd_region="${3:?region}"
geogs_fd_gpu="${4:?gpu}"
case "$geogs_fd_region:$geogs_fd_gpu" in P[123]:[01]) ;; *) exit 2 ;; esac
geogs_fd_attempt="no_anchor_sfm_gradient_memory_v3_$geogs_fd_region"
geogs_fd_out="$geogs_fd_task/$geogs_fd_attempt/detached_run_v1"
printf '%s\n' "$$" > "$geogs_fd_out/supervisor.pid"
trap 'geogs_fd_exit=$?; printf "%s\n" "$geogs_fd_exit" > "$geogs_fd_out/exit_code.txt"' EXIT
printf '%s\n' CHECKING_ACTUAL_LANE_RELEASE > "$geogs_fd_out/status.txt"
mkdir -p -- "$geogs_fd_task/no_anchor_sfm_v1/locks"
exec 8> "$geogs_fd_task/no_anchor_sfm_v1/locks/final_retry_gpu_$geogs_fd_gpu.lock"
flock -n 8
if [[ "$geogs_fd_gpu" == 0 ]]; then
  geogs_fd_prior="$geogs_fd_task/no_anchor_sfm_memory_recovery_P3_v3/lane_wait_desktop_v2"
  geogs_fd_exitfile="$geogs_fd_prior/exit_code.txt"
else
  geogs_fd_prior="$geogs_fd_task/orchestration_recovery_v1/P2"
  geogs_fd_exitfile="$geogs_fd_prior/supervisor_exit_code.txt"
fi
test -s "$geogs_fd_exitfile"
read -r geogs_fd_prior_pid < "$geogs_fd_prior/supervisor.pid"
case "$geogs_fd_prior_pid" in *[!0-9]*|'') exit 2 ;; esac
if kill -0 "$geogs_fd_prior_pid" 2>/dev/null; then
  printf '%s\n' 'The predecessor lane supervisor is still alive.' >&2
  exit 3
fi
nvidia-smi -i "$geogs_fd_gpu" --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits > "$geogs_fd_out/gpu_before.csv"
while IFS= read -r geogs_fd_row; do
  [[ -z "$geogs_fd_row" ]] && continue
  if [[ "$geogs_fd_gpu" == 0 && "$geogs_fd_row" == '72937, /usr/libexec/gnome-remote-desktop-daemon, '* ]]; then
    geogs_fd_mib="${geogs_fd_row##*, }"
    case "$geogs_fd_mib" in *[!0-9]*|'') exit 4 ;; esac
    [[ "$geogs_fd_mib" -le 512 ]]
    [[ "$(awk '{print $22}' /proc/72937/stat)" == 60213 ]]
  else
    printf '%s\n' 'GPU has another active compute process; training was not started.' >&2
    exit 4
  fi
done < "$geogs_fd_out/gpu_before.csv"
date -u +%FT%TZ > "$geogs_fd_out/started_utc.txt"
printf '%s\n' RUNNING_FIXED_FINAL_RETRY > "$geogs_fd_out/status.txt"
bash "$geogs_fd_code/run_region.sh" "$geogs_fd_region" "$geogs_fd_gpu" "$geogs_fd_attempt"
printf '%s\n' READY_FOR_VIEWER_AND_REVIEW > "$geogs_fd_out/status.txt"

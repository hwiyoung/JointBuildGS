#!/usr/bin/env bash
set -euo pipefail
geogs_q3_code="${1:?absolute code directory}"
geogs_q3_task="${2:?absolute task directory}"
geogs_q3_wait="$geogs_q3_task/no_anchor_sfm_memory_recovery_P3_v3/lane_wait_desktop_v2"
geogs_q3_p1="$geogs_q3_task/orchestration_recovery_v1/P1"
geogs_q3_receipt="$geogs_q3_task/no_anchor_sfm_memory_recovery_v2/runs/P1/SFM_noanchor_D005_Pnative/receipt.json"
test -f "$geogs_q3_task/no_anchor_sfm_memory_recovery_P3_v3/amendment.json"
read -r geogs_q3_desktop_pid geogs_q3_desktop_start < "$geogs_q3_wait/desktop_identity.txt"
case "$geogs_q3_desktop_pid:$geogs_q3_desktop_start" in *[!0-9:]*|:) exit 2 ;; esac
printf '%s\n' "$$" > "$geogs_q3_wait/supervisor.pid"
trap 'geogs_q3_exit=$?; printf "%s\n" "$geogs_q3_exit" > "$geogs_q3_wait/exit_code.txt"' EXIT
printf '%s\n' WAITING_ACTUAL_GPU0_RELEASE > "$geogs_q3_wait/status.txt"
while true; do
  if [[ -s "$geogs_q3_p1/supervisor_exit_code.txt" && -s "$geogs_q3_receipt" && -s "$geogs_q3_p1/supervisor.pid" ]]; then
    read -r geogs_q3_p1_pid < "$geogs_q3_p1/supervisor.pid"
    if ! kill -0 "$geogs_q3_p1_pid" 2>/dev/null; then
      geogs_q3_compute=$(nvidia-smi -i 0 --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits)
      geogs_q3_containers=$(docker ps --filter name=jbgs-geogs-no_anchor_sfm_memory_recovery_v2-P1 --format '{{.Names}}')
      geogs_q3_safe=true
      while IFS= read -r geogs_q3_row; do
        [[ -z "$geogs_q3_row" ]] && continue
        case "$geogs_q3_row" in
          "$geogs_q3_desktop_pid, /usr/libexec/gnome-remote-desktop-daemon, "*)
            geogs_q3_desktop_memory="${geogs_q3_row##*, }"
            case "$geogs_q3_desktop_memory" in *[!0-9]*|'') geogs_q3_safe=false ;; esac
            if [[ "$geogs_q3_safe" == true ]]; then
              [[ "$geogs_q3_desktop_memory" -le 512 ]] || geogs_q3_safe=false
              [[ "$(awk '{print $22}' "/proc/$geogs_q3_desktop_pid/stat")" == "$geogs_q3_desktop_start" ]] || geogs_q3_safe=false
            fi
            ;;
          *) geogs_q3_safe=false ;;
        esac
      done <<< "$geogs_q3_compute"
      if [[ "$geogs_q3_safe" == true && -z "$geogs_q3_containers" ]]; then
        break
      fi
    fi
  fi
  sleep 10
done
docker run --rm --network none --cpus 1 --memory 256m --memory-swap 256m \
  --user "$(id -u):$(id -g)" --mount "type=bind,src=$geogs_q3_receipt,dst=/receipt.json,readonly" \
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
  python -c 'import json; r=json.load(open("/receipt.json")); assert r["region"]=="P1" and r["phase"]=="train" and r["status"] in ("PASS","FAIL") and "finished_unix" in r; print(r["status"])' \
  > "$geogs_q3_wait/predecessor_receipt_status.txt"
nvidia-smi -i 0 --query-compute-apps=pid,process_name --format=csv > "$geogs_q3_wait/gpu0_before_launch.csv"
date -u +%FT%TZ > "$geogs_q3_wait/started_utc.txt"
printf '%s\n' RUNNING_P3 > "$geogs_q3_wait/status.txt"
bash "$geogs_q3_code/run_region.sh" P3 0 no_anchor_sfm_memory_recovery_P3_v3
printf '%s\n' READY_FOR_VIEWER_AND_REVIEW > "$geogs_q3_wait/status.txt"

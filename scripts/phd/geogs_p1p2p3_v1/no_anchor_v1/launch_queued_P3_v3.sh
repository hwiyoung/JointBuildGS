#!/usr/bin/env bash
set -euo pipefail
geogs_l3_code=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
geogs_l3_repo=$(cd -- "$geogs_l3_code/../../../.." && pwd)
geogs_l3_task=$(realpath "$geogs_l3_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_l3_out="$geogs_l3_task/no_anchor_sfm_memory_recovery_P3_v3/lane_wait_desktop_v2"
test ! -e "$geogs_l3_out"
test -f "$geogs_l3_task/no_anchor_sfm_memory_recovery_P3_v3/amendment.json"
mkdir -p -- "$geogs_l3_out"
test "$(awk '{print $22}' /proc/72937/stat)" = 60213
test "$(ps -p 72937 -o args=)" = /usr/libexec/gnome-remote-desktop-daemon
printf '%s\n' '72937 60213' > "$geogs_l3_out/desktop_identity.txt"
cat > "$geogs_l3_out/desktop_allowance.json" <<'JSON'
{"scientific_verdict":null,"pid":72937,"proc_start_ticks":60213,"process_name":"/usr/libexec/gnome-remote-desktop-daemon","observed_gpu0_memory_mib":260,"maximum_allowed_gpu0_memory_mib":512,"preexisting_service_preserved":true,"other_compute_processes_allowed":false,"training_controls_changed":false}
JSON
cp -- "${BASH_SOURCE[0]}" "$geogs_l3_code/run_queued_P3_v3.sh" "$geogs_l3_out/"
date -u +%FT%TZ > "$geogs_l3_out/queued_utc.txt"
setsid nohup bash "$geogs_l3_out/run_queued_P3_v3.sh" "$geogs_l3_code" "$geogs_l3_task" \
  < /dev/null > "$geogs_l3_out/stdout.log" 2> "$geogs_l3_out/stderr.log" &
printf '%s\n' "$!" > "$geogs_l3_out/launched_pid.txt"
printf '%s\n' 'Launched detached P3 wait with actual completion and GPU checks'

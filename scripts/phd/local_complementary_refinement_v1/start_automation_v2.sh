#!/usr/bin/env bash
# Transfer follow-on orchestration to the user systemd manager; no LLM scheduler.
set -euo pipefail
main_pid=${1:?Existing run_queue_v2.sh PID}
retry_pid=${2:?Existing P3 same-policy retry wrapper PID}
(( $# == 2 ))
[[ $main_pid =~ ^[0-9]+$ && $retry_pid =~ ^[0-9]+$ ]]
[[ $(ps -p "$main_pid" -o args=) == *run_queue_v2.sh* ]]
[[ $(ps -p "$retry_pid" -o args=) == *retry_after_queue_v2.sh*P3*LC_D0005_Pnative*P3_LC_D0005_Pnative_attempt2* ]]
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
state="$task_root/main_v2/automation_v2"
[[ ! -e "$state/started.txt" ]]
mkdir -p "$state"
systemd-run --user --unit jbgs-lc-v2-automation --description='JointBuildGS local complementary full18 follow-on evaluation and review' \
 --property=Type=exec --property=RemainAfterExit=yes --property=Restart=no \
 --setenv="JBGS_MAIN_QUEUE_PID=$main_pid" --setenv="JBGS_REGISTERED_RETRY_PID=$retry_pid" \
 --working-directory="$repo" /usr/bin/bash "$repo/scripts/phd/local_complementary_refinement_v1/run_automation_v2.sh"
systemctl --user show jbgs-lc-v2-automation -p Id -p ActiveState -p SubState -p MainPID -p ExecStart -p Environment -p Restart -p FragmentPath > "$state/systemd_launch.txt"
loginctl show-user "$(id -u)" -p Linger >> "$state/systemd_launch.txt"
cat "$state/systemd_launch.txt"

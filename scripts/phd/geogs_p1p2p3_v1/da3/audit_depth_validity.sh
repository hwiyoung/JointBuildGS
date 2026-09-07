#!/usr/bin/env bash
set -euo pipefail
task_repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
task_root="${JBGS_GEOGS_TASK_ROOT:-$task_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1}"
task_tag="${1:?Specify a NEW audit tag, for example depth_validity_audit_v2}"
[[ "$task_tag" =~ ^[a-zA-Z0-9_-]+$ ]]
task_output="$task_root/runtime/da3/$task_tag"
test ! -e "$task_output"
mkdir "$task_output"
task_command=(docker run --rm --network none --read-only --cpus 4 --memory 4g
  --user "$(id -u):$(id -g)" --tmpfs /tmp:rw,size=128m --entrypoint python
  --mount "type=bind,src=$task_repo/scripts/phd/geogs_p1p2p3_v1/da3,dst=/scripts,readonly"
  --mount "type=bind,src=$task_output,dst=/out")
for task_region in P1 P2 P3; do
  task_command+=(--mount "type=bind,src=$task_root/inputs/$task_region/da3,dst=/inputs/$task_region,readonly")
done
task_command+=(jointbuildgs:geogs-da3-3d835ec-v1 /scripts/audit_depth_validity.py --inputs /inputs --output /out)
printf '%q ' "${task_command[@]}" > "$task_root/runtime/da3/${task_tag}_command.sh"
printf '\n' >> "$task_root/runtime/da3/${task_tag}_command.sh"
"${task_command[@]}" 2>&1 | tee "$task_root/runtime/da3/${task_tag}.log"

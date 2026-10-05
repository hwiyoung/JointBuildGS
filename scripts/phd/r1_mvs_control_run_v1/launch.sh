#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
artifact_root=$(realpath "$repo_root/../JointBuildGS-artifacts")
IFS=, read -r gpu_free gpu_util <<< "$(nvidia-smi --id=1 --query-gpu=memory.free,utilization.gpu --format=csv,noheader,nounits)"
gpu_free=${gpu_free//[[:space:]]/};gpu_util=${gpu_util//[[:space:]]/}
(( gpu_free >= 23000 && gpu_util <= 5 )) || { printf 'GPU 1 is occupied; preserve the active work.\n' >&2; exit 1; }
task_root="$artifact_root/phase-payloads/phd/r1_mvs_control_run_v1/PHD-R1-MVS-CONTROL-RUN-v1"
mkdir -p "$task_root"
attempt=$(mktemp -d "$task_root/attempt_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXXXX")
mkdir "$attempt/snapshot"
cp "$repo_root/scripts/phd/r1_mvs_control_run_v1/"*.py "$repo_root/scripts/phd/r1_mvs_control_run_v1/"*.sh "$attempt/snapshot/"
cp "$repo_root/scripts/phd/geogs_mvs_pgsr_v1/run_phase.py" "$attempt/snapshot/legacy_validation.py"
git -C "$repo_root" rev-parse HEAD > "$attempt/commit.txt"
docker image inspect sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e > "$attempt/image_inspect.json"
nvidia-smi --query-gpu=index,uuid,memory.free,utilization.gpu --format=csv > "$attempt/gpu_before.csv"
printf '%s\n' 'User authorized R1 basic control background execution and viewer results on 2026-09-16. Single R1 MVS prior .005 native protection; no manual weights or PGSR.' > "$attempt/authorization.txt"
sha256sum "$attempt/snapshot/"* > "$attempt/driver_hashes.sha256"
unit="jbgs-r1-${attempt##*/}"
printf '%s\n' "$unit" > "$attempt/systemd_unit.txt"
systemd-run --user --unit "$unit" --property=Type=exec --property=RemainAfterExit=yes /bin/bash "$attempt/snapshot/queue.sh" "$attempt"
printf '%s\n' "$attempt"

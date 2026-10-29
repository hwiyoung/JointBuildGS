#!/usr/bin/env bash
set -euo pipefail
task_repo=$(cd "$(dirname "$0")/../../.." && pwd)
task_art=$(realpath "$task_repo/../JointBuildGS-artifacts")
task_out="$task_art/phase-payloads/phd/main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1"
mode=${1:?queue or delivery}
if [[ "$mode" == queue ]]; then
  task_git_common=$(git -C "$task_repo" rev-parse --path-format=absolute --git-common-dir)
  mkdir -p "$task_out/queue_snapshots"
  task_queue_snapshot="$task_out/queue_snapshots/run_mesh_queue_$(date +%Y%m%dT%H%M%S)_$$.sh"
  cp "$task_repo/scripts/phd/main_meshpatch_v1/run_mesh_queue.sh" "$task_queue_snapshot"
  docker run -d --name jbgs-meshpatch-queue --network none --memory 512m --memory-swap 512m --cpus 1 \
    --user "$(id -u):$(id -g)" --group-add "$(stat -c %g /var/run/docker.sock)" -e TZ=Asia/Seoul -e JBGS_MESHPATCH_REPO="$task_repo" \
    -v /usr/bin/docker:/usr/bin/docker:ro -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$task_git_common:$task_git_common:ro" \
    -v "$task_repo:$task_repo:ro" -v "$task_art:$task_art:ro" -v "$task_out:$task_out" \
    -v "$task_repo/configs/phd/main_meshpatch_v1:$task_repo/configs/phd/main_meshpatch_v1" \
    -v "$task_repo/docs/experiments/phd/main_meshpatch_v1:$task_repo/docs/experiments/phd/main_meshpatch_v1" \
    -w "$task_repo" --entrypoint bash jointbuildgs:dev "$task_queue_snapshot"
elif [[ "$mode" == interview-delivery ]]; then
  docker run -d --name jbgs-meshpatch-interview-delivery --network none --memory 512m --memory-swap 512m --cpus 1 \
    --user "$(id -u):$(id -g)" -e TZ=Asia/Seoul -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$task_out:/out" -v "$task_repo:/repo:ro" \
    -v "$task_repo/configs/phd/main_meshpatch_v1:/config:ro" \
    -v "$task_repo/docs/experiments/phd/main_meshpatch_v1:/docs" \
    -w /repo/scripts/phd/main_meshpatch_v1 --entrypoint python jointbuildgs:dev interview_delivery.py --schedule
elif [[ "$mode" == delivery ]]; then
  docker run -d --name jbgs-meshpatch-delivery-v4 --network none --memory 256m --memory-swap 256m --cpus 1 \
    --user "$(id -u):$(id -g)" -e TZ=Asia/Seoul -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$task_out:/out" -v "$task_repo:/repo:ro" \
    -v "$task_repo/configs/phd/main_meshpatch_v1:/config:ro" \
    -v "$task_repo/docs/experiments/phd/main_meshpatch_v1:/docs:ro" \
    -w /repo/scripts/phd/main_meshpatch_v1 --entrypoint python jointbuildgs:dev deliver.py --schedule
else
  exit 2
fi

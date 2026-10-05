#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
test "$(docker image inspect jointbuildgs:geogs-official-db40c95-v1 --format '{{.Id}}')" = sha256:6886d5920db3dc7dc9176b235a8a9240ebaccd607440f09fd7da32c106f2aee6
test ! -e "$task_root/runtime/build_compat_v1.log"
docker build --progress plain --file "$repo_root/Dockerfile.geogs-compat-v1" \
  --tag jointbuildgs:geogs-official-db40c95-compat-v1 "$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime" \
  2>&1 | tee "$task_root/runtime/build_compat_v1.log"
docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 > "$task_root/runtime/image_inspect_compat_v1.json"
docker run --rm --network none jointbuildgs:geogs-official-db40c95-compat-v1 cat /opt/geogs-runtime-freeze.txt \
  > "$task_root/runtime/pip_freeze_compat_v1.txt"

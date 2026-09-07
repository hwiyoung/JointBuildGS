#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
source_root="$task_root/sources/GeoGS"
runtime_root="$task_root/runtime"
image_tag=jointbuildgs:geogs-official-db40c95-v1
expected_base=sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774
test "$(docker image inspect jointbuildgs:dev --format '{{.Id}}')" = "$expected_base"
test "$(git -C "$source_root" rev-parse HEAD)" = db40c95c657ec03ff21c83cb99cf39f4e90247a6
test -z "$(git -C "$source_root" status --porcelain)"
test ! -e "$runtime_root/build.log"
mkdir -p "$runtime_root"
# Refuse a potentially disruptive low-space build; never prune existing images.
available_kib="$(df --output=avail /var/lib/docker | tail -1 | tr -d ' ')"
test "$available_kib" -ge 20971520
docker build --progress=plain --build-arg GEOGS_BASE_IMAGE=jointbuildgs:dev \
  --file "$repo_root/Dockerfile.geogs-v1" --tag "$image_tag" "$source_root" \
  2>&1 | tee "$runtime_root/build.log"
docker image inspect "$image_tag" > "$runtime_root/image_inspect.json"
docker run --rm --network none --gpus '"device=1"' \
  --volume "$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime:/audit:ro" \
  "$image_tag" python /audit/probe_runtime.py > "$runtime_root/probe.json"
docker run --rm --network none "$image_tag" cat /opt/geogs-runtime-freeze.txt \
  > "$runtime_root/pip_freeze.txt"
printf '%s\n' "$image_tag"

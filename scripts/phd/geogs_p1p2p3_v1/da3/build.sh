#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
source_root="$task_root/sources/Depth-Anything-3"
expected="3d835ec1a5802d64a8b8b15f817a1ab54809bfe4"
[[ "$(git -C "$source_root" rev-parse HEAD)" == "$expected" ]] || exit 2
[[ -z "$(git -C "$source_root" status --porcelain)" ]] || exit 2
[[ "$(docker image inspect jointbuildgs:dev --format '{{.Id}}')" == "sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774" ]] || exit 2
docker_free_kb="$(df --output=avail /var/lib/docker | tail -1)"
if [[ "$docker_free_kb" -lt 10485760 ]]; then echo "Docker filesystem has <10GiB available" >&2; exit 3; fi
docker build -f "$repo_root/Dockerfile.geogs-da3-v1" -t jointbuildgs:geogs-da3-3d835ec-v1 "$source_root"

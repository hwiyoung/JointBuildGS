#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
source_root="$task_root/sources/Depth-Anything-3"
commit="3d835ec1a5802d64a8b8b15f817a1ab54809bfe4"
if [[ ! -e "$source_root" ]]; then
  git init "$source_root"
  git -C "$source_root" remote add origin https://github.com/ByteDance-Seed/Depth-Anything-3.git
  git -C "$source_root" fetch --depth 1 origin "$commit"
  git -C "$source_root" checkout --detach FETCH_HEAD
fi
[[ "$(git -C "$source_root" rev-parse HEAD)" == "$commit" ]] || exit 2
[[ -z "$(git -C "$source_root" status --porcelain)" ]] || exit 2
test ! -e "$task_root/runtime/da3/acquisition.json"
mkdir -p "$task_root/sources/DA3NESTED-GIANT-LARGE" "$task_root/runtime/da3"
docker run --rm --name jbgs-geogs-da3-acquire-v1 --entrypoint python --cpus 2 --memory 4g \
  -v "$repo_root/scripts/phd/geogs_p1p2p3_v1/da3:/drivers:ro" \
  -v "$source_root:/da3-source:ro" \
  -v "$task_root/sources/DA3NESTED-GIANT-LARGE:/weights" \
  -v "$task_root/runtime/da3:/runtime" \
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774 \
  /drivers/acquire_weights.py --source-root /da3-source --weights-root /weights \
  --receipt /runtime/acquisition.json

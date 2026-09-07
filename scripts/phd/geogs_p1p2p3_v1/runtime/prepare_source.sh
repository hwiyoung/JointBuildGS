#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
payload_parent="$(cd "$repo_root/../JointBuildGS-artifacts/phase-payloads/phd" && pwd)"
task_root="$payload_parent/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
upstream="$payload_parent/geogs_contribution_v1/PHD-GEOGS-CONTRIBUTION-v1/sources/GeoGS"
source_root="$task_root/sources/GeoGS"
expected_commit=db40c95c657ec03ff21c83cb99cf39f4e90247a6
test "$(git -C "$upstream" rev-parse HEAD)" = "$expected_commit"
test -z "$(git -C "$upstream" status --porcelain)"
test ! -e "$source_root"
mkdir -p "$task_root/sources" "$task_root/runtime"
git clone --no-hardlinks "$upstream" "$source_root"
git -C "$source_root" checkout --detach "$expected_commit"
git -C "$source_root" remote set-url origin https://github.com/zqlin0521/GeoGS.git
git -C "$source_root" submodule update --init --recursive
test -z "$(git -C "$source_root" status --porcelain)"
git -C "$source_root" submodule status --recursive > "$task_root/runtime/submodule_status.txt"
if rg -q '^[+U-]' "$task_root/runtime/submodule_status.txt"; then
  echo 'Submodule state does not match pinned gitlinks' >&2
  exit 1
fi
git -C "$source_root" rev-parse HEAD > "$task_root/runtime/source_commit.txt"
sha256sum "$source_root/train.py" > "$task_root/runtime/train_sha256.txt"
printf '%s\n' "$source_root"

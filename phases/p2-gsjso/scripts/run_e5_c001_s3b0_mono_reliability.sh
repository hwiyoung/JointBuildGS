#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
image="jointbuildgs:dev"
uid_value="$(id -u)"
gid_value="$(id -g)"

docker run --rm -i \
  --user "${uid_value}:${gid_value}" \
  -e HOME=/tmp/s3b0-home \
  -e XDG_CACHE_HOME=/tmp/s3b0-xdg \
  -v "${repo}:/workspace/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "${image}" \
  python phases/p2-gsjso/scripts/e5_c001_s3b0_mono_reliability.py

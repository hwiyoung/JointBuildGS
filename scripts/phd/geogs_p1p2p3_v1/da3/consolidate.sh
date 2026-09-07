#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 2 && "$1" =~ ^P[123]$ && "$2" =~ ^[a-zA-Z0-9_-]+$ ]] || exit 2
region="$1"
run_tag="$2"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
output_root="$task_root/inputs/$region/da3"
test ! -e "$output_root"
test -f "$task_root/da3/$region/$run_tag/receipt.json"
mkdir "$output_root"
docker run --rm --network none --read-only --cpus 4 --memory 8g --tmpfs /tmp:rw,size=128m \
  -v "$repo_root/scripts/phd/geogs_p1p2p3_v1/da3:/drivers:ro" \
  -v "$task_root/da3/$region/$run_tag:/generated:ro" \
  -v "$task_root/inputs/$region/scene/split_manifest_da3_v2.json:/split.json:ro" \
  -v "$output_root:/out" \
  sha256:4130d2597c2c3c2804a7cacb8302be948314bc37ba81a1a21383e1c8b7fbba73 \
  /drivers/consolidate.py --generated /generated --split /split.json --output /out

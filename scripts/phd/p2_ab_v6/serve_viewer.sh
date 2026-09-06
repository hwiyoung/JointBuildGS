#!/usr/bin/env bash
set -euo pipefail
v6_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
v6_artifacts=$(realpath "$v6_repo/../JointBuildGS-artifacts")
v6_parent="$v6_artifacts/phase-payloads/phd/p2_ab_v6"
test -f "$v6_parent/PHD-P2-AB-V6-VIEWER-v1/viewer/technical_receipt.json"
docker run -d --name jbgs-p2-ab-inspector-v6-8896 --restart unless-stopped \
  -p 127.0.0.1:8896:8080 --read-only --cpus 1 --memory 512m \
  --mount "type=bind,src=$v6_parent,dst=/srv,readonly" \
  --workdir /srv --entrypoint python jointbuildgs:dev \
  -m http.server 8080 --bind 0.0.0.0
printf '%s\n' 'http://127.0.0.1:8896/PHD-P2-AB-V6-VIEWER-v1/viewer/?view=333'

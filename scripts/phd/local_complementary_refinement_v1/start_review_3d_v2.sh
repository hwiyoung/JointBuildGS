#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
parent_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
port=${1:-8906};name="jbgs-local-complementary-3d-$port"
test -f "$task_root/main_v2/review_3d/current.json"
if [[ -n $(ss -H -ltn "sport = :$port") ]]; then echo "Port $port occupied; existing service preserved" >&2;exit 1;fi
docker run -d --name "$name" --restart unless-stopped --read-only --cpus 1 --memory 512m --memory-swap 512m -w /tmp \
 --publish "127.0.0.1:$port:8080" --mount "type=bind,src=$task_root/main_v2/review_3d,dst=/site,readonly" \
 --mount "type=bind,src=$task_root/main_v2,dst=/task,readonly" --mount "type=bind,src=$parent_root/evaluation,dst=/parent,readonly" \
 --mount "type=bind,src=$repo/src/apps/gs3d_4way_viewer/build/three.module.min.js,dst=/three/three.module.min.js,readonly" \
 --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/serve_review_3d_v2.py,dst=/serve.py,readonly" \
 sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e python /serve.py
printf 'http://localhost:%s\n' "$port"

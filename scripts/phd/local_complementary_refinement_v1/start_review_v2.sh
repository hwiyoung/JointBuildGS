#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
name=jbgs-local-complementary-review-8905
test -s "$task_root/main_v2/review_site/current.json"
if docker container inspect "$name" >/dev/null 2>&1; then
 [[ $(docker container inspect "$name" --format '{{.State.Running}}') == true ]]
 echo 'Existing review container is running';exit 0
fi
exec docker run -d --name "$name" --restart unless-stopped --read-only --cpus 1 --memory 512m --memory-swap 512m \
 -w /tmp --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 -e TZ=Asia/Seoul -p 127.0.0.1:8905:8080 \
 --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/serve_review_v2.py,dst=/app/serve.py,readonly" \
 --mount "type=bind,src=$task_root/main_v2/review_site,dst=/site,readonly" \
 --mount "type=bind,src=$task_root/main_v2,dst=/task,readonly" \
 sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e python /app/serve.py --site /site --task /task

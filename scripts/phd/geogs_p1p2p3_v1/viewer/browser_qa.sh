#!/usr/bin/env bash
set -euo pipefail
geogs_qa_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_qa_task=$(realpath "$geogs_qa_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_qa_id=${1:?Fresh QA run identifier required}
if [[ ! "$geogs_qa_id" =~ ^[A-Za-z0-9_-]+$ ]]; then echo 'Invalid QA run identifier' >&2; exit 1; fi
geogs_qa_url=${2:-http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/viewer/manifest.json}
geogs_qa_out="$geogs_qa_task/evaluation/browser_qa/$geogs_qa_id"
if [[ -e "$geogs_qa_out" ]]; then echo 'Fresh output required; prior QA preserved' >&2; exit 1; fi
geogs_qa_image=$(docker image inspect jointbuildgs:geogs-viewer-browser-v2 --format '{{.Id}}')
mkdir -p -- "$geogs_qa_out"
cp -- "$geogs_qa_repo/scripts/phd/geogs_p1p2p3_v1/viewer/browser_qa.mjs" "$geogs_qa_out/browser_qa_source.mjs"
cp -- "$geogs_qa_repo/scripts/phd/geogs_p1p2p3_v1/viewer/browser_qa.sh" "$geogs_qa_out/browser_qa_wrapper.sh"
cp -- "$geogs_qa_repo/src/apps/geogs_p1p2p3_v1/viewer.js" "$geogs_qa_out/viewer_source.js"
cp -- "$geogs_qa_repo/src/apps/geogs_p1p2p3_v1/resolution.mjs" "$geogs_qa_out/resolution_source.mjs"
docker run --rm --read-only --network host --cpus 2 --memory 3g \
  --tmpfs /tmp:rw,nosuid,size=1g --shm-size 512m \
  --env "GEOGS_QA_IMAGE_ID=$geogs_qa_image" \
  --mount "type=bind,src=$geogs_qa_repo/scripts/phd/geogs_p1p2p3_v1/viewer/browser_qa.mjs,dst=/qa/browser_qa.mjs,readonly" \
  --mount "type=bind,src=$geogs_qa_out,dst=/out" \
  "$geogs_qa_image" /qa/browser_qa.mjs "$geogs_qa_url" /out
printf '%s\n' "$geogs_qa_out/browser_qa.json"

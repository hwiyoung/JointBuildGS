#!/usr/bin/env bash
set -euo pipefail
preview_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
preview_task=$(realpath "$preview_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
preview_manifest="$preview_task/evaluation/viewer/manifest_preview_v1.json"
[[ -f "$preview_manifest" ]] || { echo 'Preview manifest not yet available' >&2; exit 1; }
preview_image=$(docker image inspect jointbuildgs:geogs-viewer-browser-v2 --format '{{.Id}}')
preview_url='http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/viewer/manifest_preview_v1.json'
mkdir -p -- "$preview_task/viewer_qa_preview_v1"
preview_out=$(mktemp -d "$preview_task/viewer_qa_preview_v1/attempt.$(date -u +%Y%m%dT%H%M%SZ).XXXXXX")
for preview_file in preview_smoke_v1.mjs run_preview_smoke_v1.sh Dockerfile.browser; do
  cp -- "$preview_repo/scripts/phd/geogs_p1p2p3_v1/viewer/$preview_file" "$preview_out/$preview_file"
done
for preview_file in viewer.js resolution.mjs display_data.mjs index.html style.css; do
  cp -- "$preview_repo/src/apps/geogs_p1p2p3_v1/$preview_file" "$preview_out/$preview_file"
done
cp -- "$preview_manifest" "$preview_out/manifest_preview_v1.json"
preview_command=(docker run --rm --read-only --network host --cpus 2 --memory 3g --memory-swap 3g --pids-limit 256
  --tmpfs /tmp:rw,nosuid,size=1g --shm-size 512m
  --env "GEOGS_QA_IMAGE_ID=$preview_image"
  --mount "type=bind,src=$preview_out/preview_smoke_v1.mjs,dst=/qa/preview_smoke_v1.mjs,readonly"
  --mount "type=bind,src=$preview_out,dst=/out"
  "$preview_image" /qa/preview_smoke_v1.mjs "$preview_url" /out)
printf '%q ' "${preview_command[@]}" > "$preview_out/command.sh"
printf '\n' >> "$preview_out/command.sh"
printf '%s\n' "$preview_out"
set +e
"${preview_command[@]}" > "$preview_out/run.log" 2>&1
preview_exit=$?
set -e
printf '%s\n' "$preview_exit" > "$preview_out/exit_code.txt"
(cd -- "$preview_out" && sha256sum -- ./* > SHA256SUMS)
cat -- "$preview_out/run.log"
printf '%s\n' "$preview_out/receipt.json"
exit "$preview_exit"

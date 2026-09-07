#!/usr/bin/env bash
# Strict by default. Explicit --allow-partial audits unavailable states as well.
set -euo pipefail
na_qa_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
na_qa_task=$(realpath "$na_qa_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
na_qa_publish=${1:?Published no-anchor profile identifier required}
na_qa_id=${2:-$na_qa_publish}
na_qa_port=${3:-8902}
na_qa_mode=${4:-}
(( $# <= 4 )) || { echo 'Usage: browser_qa.sh PROFILE QA_ID PORT [--allow-partial]' >&2; exit 2; }
[[ -z "$na_qa_mode" || "$na_qa_mode" == --allow-partial ]] || { echo 'Only --allow-partial may relax availability' >&2; exit 2; }
na_qa_flags=()
if [[ "$na_qa_mode" == --allow-partial ]]; then
  na_qa_flags+=(--allow-partial)
fi
[[ "$na_qa_publish" =~ ^[A-Za-z0-9_-]+$ && "$na_qa_id" =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'Invalid profile/QA identifier' >&2; exit 1; }
[[ "$na_qa_port" =~ ^[0-9]{1,5}$ ]] && ((10#$na_qa_port >= 1 && 10#$na_qa_port <= 65535)) || { echo 'Invalid local viewer port' >&2; exit 1; }
na_qa_manifest="$na_qa_task/evaluation/no_anchor_sfm_v1/profiles/$na_qa_publish/manifest.json"
[[ -f "$na_qa_manifest" ]] || { echo 'Selected profile manifest is not available' >&2; exit 1; }
na_qa_url="http://127.0.0.1:$na_qa_port/app/index.html?manifest=/task/evaluation/no_anchor_sfm_v1/profiles/$na_qa_publish/manifest.json&color=height"
na_qa_out="$na_qa_task/no_anchor_sfm_v1/validation/browser_qa/$na_qa_id"
[[ ! -e "$na_qa_out" ]] || { echo 'Fresh QA output required; prior records are preserved' >&2; exit 1; }
na_qa_image=$(docker image inspect jointbuildgs:geogs-viewer-browser-v2 --format '{{.Id}}')
mkdir -p -- "$na_qa_out"
cp -- "$na_qa_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/browser_qa.mjs" "$na_qa_out/browser_qa.mjs"
cp -- "${BASH_SOURCE[0]}" "$na_qa_out/browser_qa_wrapper.sh"
cp -- "$na_qa_manifest" "$na_qa_out/manifest_snapshot.json"
for na_qa_file in viewer.js resolution.mjs display_data.mjs index.html style.css; do
  cp -- "$na_qa_repo/src/apps/geogs_p1p2p3_v1/$na_qa_file" "$na_qa_out/$na_qa_file"
done
na_qa_manifest_sha=$(sha256sum "$na_qa_out/manifest_snapshot.json")
na_qa_manifest_sha=${na_qa_manifest_sha%% *}
na_qa_command=(docker run --rm --read-only --network host --cpus 2 --memory 3g --memory-swap 3g --pids-limit 256
  --tmpfs /tmp:rw,nosuid,size=1g --shm-size 512m
  --env "GEOGS_QA_IMAGE_ID=$na_qa_image" --env "GEOGS_QA_MANIFEST_SHA256=$na_qa_manifest_sha"
  --mount "type=bind,src=$na_qa_out/browser_qa.mjs,dst=/qa/browser_qa.mjs,readonly"
  --mount "type=bind,src=$na_qa_out,dst=/out"
  "$na_qa_image" /qa/browser_qa.mjs "$na_qa_url" /out "${na_qa_flags[@]}")
printf '%q ' "${na_qa_command[@]}" > "$na_qa_out/command.sh"
printf '\n' >> "$na_qa_out/command.sh"
printf '%s\n' "$na_qa_image" > "$na_qa_out/docker_image_id.txt"
printf '%s\n' "$na_qa_out"
set +e
"${na_qa_command[@]}" > "$na_qa_out/run.log" 2>&1
na_qa_exit=$?
set -e
printf '%s\n' "$na_qa_exit" > "$na_qa_out/exit_code.txt"
(cd -- "$na_qa_out" && sha256sum -- ./* > SHA256SUMS)
cat -- "$na_qa_out/run.log"
printf '%s\n' "$na_qa_out/receipt.json"
exit "$na_qa_exit"

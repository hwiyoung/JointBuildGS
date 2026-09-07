#!/usr/bin/env bash
# Run only for an explicitly prepared prefix profile; this does not trigger evaluation.
set -euo pipefail
prefix_qa_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../../.." && pwd)
prefix_qa_task=$(realpath "$prefix_qa_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
prefix_qa_profile=${1:?profile id}
prefix_qa_id=${2:-$prefix_qa_profile}
prefix_qa_port=${3:-8902}
prefix_qa_mode=${4:-}
(( $# <= 4 )) || exit 2
[[ "$prefix_qa_profile" =~ ^[A-Za-z0-9_-]+$ && "$prefix_qa_id" =~ ^[A-Za-z0-9_-]+$ ]] || exit 2
[[ "$prefix_qa_port" =~ ^[0-9]{1,5}$ ]] && ((10#$prefix_qa_port >= 1 && 10#$prefix_qa_port <= 65535)) || exit 2
[[ -z "$prefix_qa_mode" || "$prefix_qa_mode" == --allow-partial ]] || exit 2
prefix_qa_args=()
if [[ "$prefix_qa_mode" == --allow-partial ]]; then prefix_qa_args+=(--allow-partial); fi
prefix_qa_root="$prefix_qa_task/evaluation/no_anchor_sfm_prefix8000_v1"
prefix_qa_manifest="$prefix_qa_root/profiles/$prefix_qa_profile/manifest.json"
prefix_qa_out="$prefix_qa_root/qa/$prefix_qa_id"
test -f "$prefix_qa_manifest"
test ! -e "$prefix_qa_out"
mkdir -p "$prefix_qa_out/source" "$prefix_qa_out/app"
cp -- "$(dirname -- "${BASH_SOURCE[0]}")/browser_qa.mjs" "$prefix_qa_out/source/"
cp -- "${BASH_SOURCE[0]}" "$prefix_qa_out/source/"
cp -- "$prefix_qa_manifest" "$prefix_qa_out/manifest_snapshot.json"
cp -- "$prefix_qa_repo/src/apps/geogs_p1p2p3_v1/"{viewer.js,resolution.mjs,display_data.mjs,index.html,style.css} "$prefix_qa_out/app/"
prefix_qa_image=$(docker image inspect jointbuildgs:geogs-viewer-browser-v2 --format '{{.Id}}')
prefix_qa_sha=$(sha256sum "$prefix_qa_out/manifest_snapshot.json")
prefix_qa_sha=${prefix_qa_sha%% *}
prefix_qa_url="http://127.0.0.1:$prefix_qa_port/app/index.html?manifest=/task/evaluation/no_anchor_sfm_prefix8000_v1/profiles/$prefix_qa_profile/manifest.json&color=height"
prefix_qa_cmd=(docker run --rm --read-only --network host --cpus 2 --memory 3g --memory-swap 3g --pids-limit 256
  --tmpfs /tmp:rw,nosuid,size=1g --shm-size 512m
  --env "GEOGS_QA_IMAGE_ID=$prefix_qa_image" --env "GEOGS_QA_MANIFEST_SHA256=$prefix_qa_sha"
  --mount "type=bind,src=$prefix_qa_out/source/browser_qa.mjs,dst=/qa/browser_qa.mjs,readonly"
  --mount "type=bind,src=$prefix_qa_out,dst=/out"
  "$prefix_qa_image" /qa/browser_qa.mjs "$prefix_qa_url" /out "${prefix_qa_args[@]}")
printf '%q ' "${prefix_qa_cmd[@]}" > "$prefix_qa_out/command.sh"
printf '\n' >> "$prefix_qa_out/command.sh"
printf '%s\n' "$prefix_qa_image" > "$prefix_qa_out/docker_image_id.txt"
set +e
"${prefix_qa_cmd[@]}" > "$prefix_qa_out/run.log" 2>&1
prefix_qa_exit=$?
set -e
printf '%s\n' "$prefix_qa_exit" > "$prefix_qa_out/exit_code.txt"
(cd "$prefix_qa_out" && rg --files -0 -g '!SHA256SUMS' | sort -z | xargs -0 sha256sum) > "$prefix_qa_out/SHA256SUMS"
cat "$prefix_qa_out/run.log"
exit "$prefix_qa_exit"

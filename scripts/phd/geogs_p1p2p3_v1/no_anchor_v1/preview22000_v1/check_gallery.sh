#!/usr/bin/env bash
set -euo pipefail
preview_qa_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../../.." && pwd)
preview_qa_task=$(realpath "$preview_qa_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
preview_qa_root="$preview_qa_task/preview22000_v1/P2"
preview_qa_id=${1:-actual_v1}
[[ "$preview_qa_id" =~ ^[A-Za-z0-9_-]+$ ]] || exit 2
preview_qa_out="$preview_qa_root/browser_qa/$preview_qa_id"
test -s "$preview_qa_root/gallery_v1/receipt.json"
test ! -e "$preview_qa_out"
mkdir -p "$preview_qa_out/source"
cp -- "${BASH_SOURCE[0]}" "$preview_qa_root/gallery_build_v1/code/browser_qa.mjs" "$preview_qa_out/source/"
preview_qa_image=$(docker image inspect jointbuildgs:geogs-viewer-browser-v2 --format '{{.Id}}')
preview_qa_manifest=$(sha256sum "$preview_qa_root/gallery_v1/manifest.json")
preview_qa_manifest=${preview_qa_manifest%% *}
preview_qa_cmd=(docker run --rm --read-only --network host --cpus 2 --memory 2g --memory-swap 2g --pids-limit 256
  --tmpfs /tmp:rw,nosuid,size=1g --shm-size 512m --env "PREVIEW_MANIFEST_SHA256=$preview_qa_manifest"
  --mount "type=bind,src=$preview_qa_out/source/browser_qa.mjs,dst=/qa/browser_qa.mjs,readonly"
  --mount "type=bind,src=$preview_qa_out,dst=/out"
  "$preview_qa_image" /qa/browser_qa.mjs http://127.0.0.1:8902/task/preview22000_v1/P2/gallery_v1/index.html /out)
printf '%q ' "${preview_qa_cmd[@]}" > "$preview_qa_out/command.sh"
printf '\n' >> "$preview_qa_out/command.sh"
printf '%s\n' "$preview_qa_image" > "$preview_qa_out/image_id.txt"
trap 'preview_qa_exit=$?; printf "%s\n" "$preview_qa_exit" > "$preview_qa_out/exit_code.txt"' EXIT
"${preview_qa_cmd[@]}" > "$preview_qa_out/stdout.log" 2> "$preview_qa_out/stderr.log"
cat "$preview_qa_out/stdout.log"

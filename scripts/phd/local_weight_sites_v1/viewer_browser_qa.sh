#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd "$(dirname "$0")" && pwd)
viewer_url=${1:?Usage: viewer_browser_qa.sh LOCAL_URL NEW_ABSOLUTE_QA_OUTPUT}
qa_output=${2:?Fresh QA output directory required}
qa_mode=${3:-full}
[[ "$qa_mode" = full || "$qa_mode" = entry ]]
[[ "$qa_output" = /* ]]
mkdir "$qa_output"
cp "$script_dir/viewer_browser_qa.mjs" "$script_dir/viewer_browser_qa.sh" "$qa_output/"
browser_image=$(docker image inspect jointbuildgs:geogs-viewer-browser-v2 --format '{{.Id}}')
printf '%s\n' "$browser_image" > "$qa_output/image_id.txt"
runtime=(docker run --rm --read-only --network host --cpus 2 --memory 4g
  --tmpfs /tmp:rw,nosuid,size=1g --shm-size 512m -v "$qa_output:/out"
  "$browser_image" /out/viewer_browser_qa.mjs "$viewer_url" /out "$qa_mode")
printf '%q ' "${runtime[@]}" > "$qa_output/command.txt"
printf '\n' >> "$qa_output/command.txt"
"${runtime[@]}" > "$qa_output/process.log" 2>&1

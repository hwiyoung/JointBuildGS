#!/usr/bin/env bash
set -euo pipefail
geogs_anchor_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_anchor_task=$(realpath "$geogs_anchor_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_anchor_id=${1:-browser_qa}
[[ "$geogs_anchor_id" =~ ^[A-Za-z0-9_-]+$ ]]
geogs_anchor_out="$geogs_anchor_task/evaluation/anchor_review_v1/$geogs_anchor_id"
test ! -e "$geogs_anchor_out"
mkdir -- "$geogs_anchor_out"
trap 'geogs_anchor_exit=$?; printf "%s\n" "$geogs_anchor_exit" > "$geogs_anchor_out/exit_code.txt"' EXIT
cp -- "${BASH_SOURCE[0]}" "$geogs_anchor_out/launcher_snapshot.sh"
sed -e 's@/task/evaluation/viewer/manifest_preview_v1.json@/task/evaluation/anchor_review_v1/manifest.json@g' \
    -e 's/PREVIEW_DISPLAY_SMOKE/ANCHOR_REVIEW_DISPLAY_SMOKE/g' \
    -e 's/1240/1900/g' \
    -e "/const raster=await pixels(state);/a\    check(state.resolution_mode==='512' \&\& state.condition==='D0005_Pnative' \&\& state.panels.anchor.status==='available' \&\& state.panels.anchor.candidate.includes('anchor_512') \&\& state.panels.vanilla.candidate!==state.panels.changed.candidate,'matched512_anchor_and_distinct_changed',state);" \
    "$geogs_anchor_repo/scripts/phd/geogs_p1p2p3_v1/viewer/preview_smoke_v1.mjs" > "$geogs_anchor_out/check.mjs"
geogs_anchor_image=$(docker image inspect jointbuildgs:geogs-viewer-browser-v2 --format '{{.Id}}')
printf '%s\n' "$geogs_anchor_image" > "$geogs_anchor_out/image_id.txt"
docker run --rm --read-only --network host --cpus 2 --memory 3g --memory-swap 3g \
  --pids-limit 256 --tmpfs /tmp:rw,nosuid,size=1g --shm-size 512m \
  --env "GEOGS_QA_IMAGE_ID=$geogs_anchor_image" \
  --mount "type=bind,src=$geogs_anchor_out/check.mjs,dst=/qa/check.mjs,readonly" \
  --mount "type=bind,src=$geogs_anchor_out,dst=/out" "$geogs_anchor_image" \
  /qa/check.mjs 'http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/anchor_review_v1/manifest.json&color=height' /out \
  > "$geogs_anchor_out/stdout.log" 2> "$geogs_anchor_out/stderr.log"
cat "$geogs_anchor_out/stdout.log"

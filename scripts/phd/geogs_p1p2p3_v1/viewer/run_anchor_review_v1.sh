#!/usr/bin/env bash
set -euo pipefail
geogs_review_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_review_task=$(realpath "$geogs_review_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_review_out="$geogs_review_task/evaluation/anchor_review_v1"
test ! -e "$geogs_review_out"
geogs_review_image=$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')
mkdir -- "$geogs_review_out"
trap 'geogs_review_exit=$?; printf "%s\n" "$geogs_review_exit" > "$geogs_review_out/exit_code.txt"' EXIT
cp -- "$geogs_review_repo/scripts/phd/geogs_p1p2p3_v1/viewer/build_anchor_review_v1.py" "$geogs_review_out/script_snapshot.py"
cp -- "$geogs_review_repo/configs/phd/geogs_p1p2p3_v1/anchor_review_v1.json" "$geogs_review_out/config_snapshot.json"
cp -- "${BASH_SOURCE[0]}" "$geogs_review_out/launcher_snapshot.sh"
printf '%s\n' "$geogs_review_image" > "$geogs_review_out/image_id.txt"
git -C "$geogs_review_repo" rev-parse HEAD > "$geogs_review_out/git_head.txt"
docker run --rm --read-only --network none --cpus 2 --memory 2g --memory-swap 2g \
  --tmpfs /tmp:rw,nosuid,size=128m --mount "type=bind,src=$geogs_review_task,dst=/task,readonly" \
  --mount "type=bind,src=$geogs_review_out,dst=/out" \
  --entrypoint /opt/geogs/bin/python "$geogs_review_image" /out/script_snapshot.py \
  --task /task --config /out/config_snapshot.json --out /out \
  > "$geogs_review_out/stdout.log" 2> "$geogs_review_out/stderr.log"
cat "$geogs_review_out/stdout.log"
printf '%s\n' 'http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/anchor_review_v1/manifest.json&color=height'

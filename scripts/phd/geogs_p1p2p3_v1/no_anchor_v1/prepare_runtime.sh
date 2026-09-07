#!/usr/bin/env bash
set -euo pipefail
geogs_na_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_na_task=$(realpath "$geogs_na_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_na_exp="$geogs_na_task/no_anchor_sfm_v1"
geogs_na_image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test ! -e "$geogs_na_exp/source"
test ! -e "$geogs_na_exp/preparation_runtime"
mkdir -p -- "$geogs_na_exp/preparation_runtime"
test ! -e "$geogs_na_exp/config.json"
cp -- "$geogs_na_repo/configs/phd/geogs_p1p2p3_v1/no_anchor_sfm_v1.json" "$geogs_na_exp/config.json"
cp -- "$geogs_na_repo/docs/experiments/phd/geogs_p1p2p3_v1/SFM_NO_ANCHOR_PLAN_ko_v1.md" "$geogs_na_exp/preparation_runtime/plan_before_training.md"
cp -- "${BASH_SOURCE[0]}" "$geogs_na_exp/preparation_runtime/launcher.sh"
cp -- "$geogs_na_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/prepare_runtime.py" "$geogs_na_exp/preparation_runtime/prepare_runtime.py"
cp -- "$geogs_na_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/no_anchor_adapter.py" "$geogs_na_exp/preparation_runtime/no_anchor_adapter.py"
git -C "$geogs_na_repo" rev-parse HEAD > "$geogs_na_exp/preparation_runtime/git_head.txt"
printf '%s\n' "$geogs_na_image" > "$geogs_na_exp/preparation_runtime/image_id.txt"
trap 'geogs_na_exit=$?; printf "%s\n" "$geogs_na_exit" > "$geogs_na_exp/preparation_runtime/exit_code.txt"' EXIT
docker run --rm --network none --cpus 2 --memory 2g --memory-swap 2g \
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$geogs_na_task/sources/GeoGS-state-camera-v1,dst=/original,readonly" \
  --mount "type=bind,src=$geogs_na_exp,dst=/out" \
  "$geogs_na_image" python /out/preparation_runtime/prepare_runtime.py \
  --source /original --destination /out/source \
  > "$geogs_na_exp/preparation_runtime/stdout.log" 2> "$geogs_na_exp/preparation_runtime/stderr.log"
cat "$geogs_na_exp/preparation_runtime/stdout.log"

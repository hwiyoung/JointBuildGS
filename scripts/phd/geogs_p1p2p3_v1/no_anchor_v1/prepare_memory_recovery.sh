#!/usr/bin/env bash
set -euo pipefail
geogs_mr_region="${1:?P1 P2 P3}"
case "$geogs_mr_region" in P1) geogs_mr_attempt=no_anchor_sfm_memory_recovery_v1 ;; P2|P3) geogs_mr_attempt="no_anchor_sfm_memory_recovery_${geogs_mr_region}_v1" ;; *) exit 2 ;; esac
geogs_mr_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_mr_task=$(realpath "$geogs_mr_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_mr_parent="$geogs_mr_task/no_anchor_sfm_v1"
geogs_mr_out="$geogs_mr_task/$geogs_mr_attempt"
geogs_mr_code="$geogs_mr_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1"
geogs_mr_image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test ! -e "$geogs_mr_out"
test -f "$geogs_mr_parent/runs/$geogs_mr_region/SFM_noanchor_D005_Pnative/receipt.json"
mkdir -p -- "$geogs_mr_out/preparation_runtime" "$geogs_mr_out/inputs"
cp -- "$geogs_mr_parent/config.json" "$geogs_mr_out/config.json"
cp -a -- "$geogs_mr_parent/inputs/$geogs_mr_region" "$geogs_mr_out/inputs/$geogs_mr_region"
cp -- "$geogs_mr_code/memory_recovery_v1/prepare_runtime.py" "$geogs_mr_code/memory_recovery_v1/memory_adapter.py" "$geogs_mr_out/preparation_runtime/"
cp -- "${BASH_SOURCE[0]}" "$geogs_mr_out/preparation_runtime/launcher.sh"
trap 'geogs_mr_exit=$?; printf "%s\n" "$geogs_mr_exit" > "$geogs_mr_out/preparation_runtime/exit_code.txt"' EXIT
docker run --rm --network none --cpus 2 --memory 2g --memory-swap 2g \
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$geogs_mr_parent/source,dst=/original,readonly" \
  --mount "type=bind,src=$geogs_mr_out,dst=/out" \
  "$geogs_mr_image" python /out/preparation_runtime/prepare_runtime.py \
  --source /original --destination /out/source \
  > "$geogs_mr_out/preparation_runtime/stdout.log" 2> "$geogs_mr_out/preparation_runtime/stderr.log"
cat "$geogs_mr_out/preparation_runtime/stdout.log"

#!/usr/bin/env bash
set -euo pipefail
geogs_pv_region="${1:?P1 P2 P3}"
case "$geogs_pv_region" in P1) geogs_pv_attempt=no_anchor_sfm_memory_recovery_v2 ;; P2|P3) geogs_pv_attempt="no_anchor_sfm_memory_recovery_${geogs_pv_region}_v2" ;; *) exit 2 ;; esac
if [[ "${2:-}" == scheduling_retry_v1 && "$geogs_pv_region" == P3 ]]; then
  geogs_pv_attempt=no_anchor_sfm_memory_recovery_P3_v3
elif [[ -n "${2:-}" ]]; then
  exit 2
fi
geogs_pv_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_pv_task=$(realpath "$geogs_pv_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_pv_parent="$geogs_pv_task/no_anchor_sfm_v1"
geogs_pv_out="$geogs_pv_task/$geogs_pv_attempt"
geogs_pv_code="$geogs_pv_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1"
geogs_pv_image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test ! -e "$geogs_pv_out"
test -f "$geogs_pv_parent/runs/$geogs_pv_region/SFM_noanchor_D005_Pnative/receipt.json"
mkdir -p -- "$geogs_pv_out/preparation_runtime/memory_recovery_v1" "$geogs_pv_out/preparation_runtime/memory_recovery_v2" "$geogs_pv_out/inputs"
cp -- "$geogs_pv_parent/config.json" "$geogs_pv_out/config.json"
cp -a -- "$geogs_pv_parent/inputs/$geogs_pv_region" "$geogs_pv_out/inputs/$geogs_pv_region"
cp -- "$geogs_pv_code/memory_recovery_v1/prepare_runtime.py" "$geogs_pv_code/memory_recovery_v1/memory_adapter.py" "$geogs_pv_out/preparation_runtime/memory_recovery_v1/"
cp -- "$geogs_pv_code/memory_recovery_v2/prepare_runtime.py" "$geogs_pv_code/memory_recovery_v2/runtime_adapter.py" "$geogs_pv_code/memory_recovery_v2/pinned_storage.py" "$geogs_pv_code/memory_recovery_v2/verify_runtime.py" "$geogs_pv_out/preparation_runtime/memory_recovery_v2/"
cp -- "${BASH_SOURCE[0]}" "$geogs_pv_out/preparation_runtime/launcher.sh"
trap 'geogs_pv_exit=$?; printf "%s\n" "$geogs_pv_exit" > "$geogs_pv_out/preparation_runtime/exit_code.txt"' EXIT
docker run --rm --network none --cpus 2 --memory 2g --memory-swap 2g \
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$geogs_pv_parent/source,dst=/original,readonly" \
  --mount "type=bind,src=$geogs_pv_out,dst=/out" \
  "$geogs_pv_image" /opt/geogs/bin/python /out/preparation_runtime/memory_recovery_v2/prepare_runtime.py \
  --source /original --destination /out/source --v1-directory /out/preparation_runtime/memory_recovery_v1 \
  > "$geogs_pv_out/preparation_runtime/stdout.log" 2> "$geogs_pv_out/preparation_runtime/stderr.log"
cat "$geogs_pv_out/preparation_runtime/stdout.log"

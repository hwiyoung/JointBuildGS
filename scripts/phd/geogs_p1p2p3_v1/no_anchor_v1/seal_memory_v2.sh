#!/usr/bin/env bash
set -euo pipefail
geogs_sv_region="${1:?P1 P2 P3}"
case "$geogs_sv_region" in P1) geogs_sv_suffix='' ;; P2|P3) geogs_sv_suffix="_$geogs_sv_region" ;; *) exit 2 ;; esac
geogs_sv_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_sv_task=$(realpath "$geogs_sv_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_sv_attempt="no_anchor_sfm_memory_recovery${geogs_sv_suffix}_v2"
if [[ "${2:-}" == scheduling_retry_v1 && "$geogs_sv_region" == P3 ]]; then
  geogs_sv_attempt=no_anchor_sfm_memory_recovery_P3_v3
elif [[ -n "${2:-}" ]]; then
  exit 2
fi
geogs_sv_out="$geogs_sv_task/$geogs_sv_attempt"
geogs_sv_code="$geogs_sv_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1"
geogs_sv_extra=()
if [[ "$geogs_sv_region" != P3 ]]; then
  geogs_sv_extra=(--prior-resource-attempt "no_anchor_sfm_memory_recovery${geogs_sv_suffix}_v1")
elif [[ "$geogs_sv_attempt" == no_anchor_sfm_memory_recovery_P3_v3 ]]; then
  geogs_sv_extra=(--prior-initialization-failure no_anchor_sfm_memory_recovery_P3_v2)
fi
test ! -e "$geogs_sv_out/seal_execution"
mkdir -p -- "$geogs_sv_out/seal_execution"
cp -- "${BASH_SOURCE[0]}" "$geogs_sv_code/seal_memory_attempt.py" "$geogs_sv_out/seal_execution/"
trap 'geogs_sv_exit=$?; printf "%s\n" "$geogs_sv_exit" > "$geogs_sv_out/seal_execution/exit_code.txt"' EXIT
docker run --rm --network none --cpus 1 --memory 2g --memory-swap 2g \
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$geogs_sv_task,dst=/task,readonly" \
  --mount "type=bind,src=$geogs_sv_out,dst=/out" \
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
  python /out/seal_execution/seal_memory_attempt.py --task /task --experiment /out \
  --task-relative "$geogs_sv_attempt" --region "$geogs_sv_region" \
  --validation-relative no_anchor_sfm_memory_recovery_v2/validation/runtime_cuda_v1/receipt.json \
  --additional-capture-iteration 8000 --additional-capture-iteration 15000 "${geogs_sv_extra[@]}" \
  > "$geogs_sv_out/seal_execution/stdout.log" 2> "$geogs_sv_out/seal_execution/stderr.log"
cat "$geogs_sv_out/seal_execution/stdout.log"

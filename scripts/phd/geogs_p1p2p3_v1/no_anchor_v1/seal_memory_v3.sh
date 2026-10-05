#!/usr/bin/env bash
set -euo pipefail
geogs_gs_region="${1:?P1 P2 P3}"
geogs_gs_policy="${2:?task-relative frozen finite retry policy}"
geogs_gs_policy_sha="${3:?exact frozen policy SHA256}"
geogs_gs_validation="${4:?task-relative PASS tiny CUDA runtime proof}"
geogs_gs_resource_failure="${5:-}"
geogs_gs_extra=()
if [[ -n "$geogs_gs_resource_failure" ]]; then
  geogs_gs_extra=(--predecessor-resource-failure "$geogs_gs_resource_failure")
fi
case "$geogs_gs_region" in
  P1) geogs_gs_predecessor=no_anchor_sfm_memory_recovery_v2 ;;
  P2) geogs_gs_predecessor=no_anchor_sfm_memory_recovery_P2_v2 ;;
  P3) geogs_gs_predecessor=no_anchor_sfm_memory_recovery_P3_v3 ;;
  *) exit 2 ;;
esac
geogs_gs_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_gs_task=$(realpath "$geogs_gs_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_gs_attempt="no_anchor_sfm_gradient_memory_v3_$geogs_gs_region"
geogs_gs_out="$geogs_gs_task/$geogs_gs_attempt"
geogs_gs_code="$geogs_gs_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1"
test ! -e "$geogs_gs_out/seal_execution"
test ! -e "$geogs_gs_out/runs"
mkdir -p -- "$geogs_gs_out/seal_execution"
cp -- "${BASH_SOURCE[0]}" "$geogs_gs_code/seal_memory_attempt.py" "$geogs_gs_out/seal_execution/"
trap 'geogs_gs_exit=$?; printf "%s\n" "$geogs_gs_exit" > "$geogs_gs_out/seal_execution/exit_code.txt"' EXIT
docker run --rm --network none --read-only --cpus 2 --memory 2g --memory-swap 2g \
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 --env NVIDIA_VISIBLE_DEVICES=void --env CUDA_VISIBLE_DEVICES= \
  --mount "type=bind,src=$geogs_gs_task,dst=/task,readonly" \
  --mount "type=bind,src=$geogs_gs_out,dst=/out" \
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
  python /out/seal_execution/seal_memory_attempt.py --task /task --experiment /out \
  --task-relative "$geogs_gs_attempt" --region "$geogs_gs_region" --validation-relative "$geogs_gs_validation" \
  --predecessor-attempt "$geogs_gs_predecessor" --final-retry-policy "$geogs_gs_policy" \
  --final-retry-policy-sha256 "$geogs_gs_policy_sha" --additional-capture-iteration 8000 --additional-capture-iteration 15000 \
  "${geogs_gs_extra[@]}" \
  > "$geogs_gs_out/seal_execution/stdout.log" 2> "$geogs_gs_out/seal_execution/stderr.log"
cat "$geogs_gs_out/seal_execution/stdout.log"

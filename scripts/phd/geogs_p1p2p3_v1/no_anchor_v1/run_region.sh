#!/usr/bin/env bash
# One GPU lane; mesh extraction and geometric scoring use a shared CPU-memory lock.
set -euo pipefail
geogs_na_region="${1:?P1 P2 P3}"
geogs_na_gpu="${2:?0 or 1}"
geogs_na_attempt="${3:-no_anchor_sfm_v1}"
case "$geogs_na_attempt" in no_anchor_sfm_v1|no_anchor_sfm_memory_recovery_v1|no_anchor_sfm_memory_recovery_P2_v1|no_anchor_sfm_memory_recovery_P3_v1|no_anchor_sfm_memory_recovery_v2|no_anchor_sfm_memory_recovery_P2_v2|no_anchor_sfm_memory_recovery_P3_v2|no_anchor_sfm_memory_recovery_P3_v3|no_anchor_sfm_gradient_memory_v3_P1|no_anchor_sfm_gradient_memory_v3_P2|no_anchor_sfm_gradient_memory_v3_P3) ;; *) exit 2 ;; esac
if [[ "$geogs_na_attempt" == no_anchor_sfm_gradient_memory_v3_* ]]; then
  test "$geogs_na_attempt" = "no_anchor_sfm_gradient_memory_v3_$geogs_na_region"
fi
geogs_na_code=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
geogs_na_repo=$(cd -- "$geogs_na_code/../../../.." && pwd)
geogs_na_task=$(realpath "$geogs_na_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_na_queue="$geogs_na_task/$geogs_na_attempt/queue/$geogs_na_region"
test ! -e "$geogs_na_queue"
mkdir -p -- "$geogs_na_queue" "$geogs_na_task/no_anchor_sfm_v1/locks"
cp -- "${BASH_SOURCE[0]}" "$geogs_na_queue/launcher_snapshot.sh"
trap 'geogs_na_exit=$?; printf "%s\n" "$geogs_na_exit" > "$geogs_na_queue/exit_code.txt"' EXIT
printf '%s\n' "TRAINING" > "$geogs_na_queue/status.txt"
bash "$geogs_na_code/run_phase.sh" "$geogs_na_region" train "$geogs_na_gpu" '' "$geogs_na_attempt"
for geogs_na_iter in 22000 30000; do
  printf '%s\n' "EXPORTING_$geogs_na_iter" > "$geogs_na_queue/status.txt"
  flock "$geogs_na_task/no_anchor_sfm_v1/locks/heavy_cpu.lock" \
    bash "$geogs_na_code/run_phase.sh" "$geogs_na_region" export "$geogs_na_gpu" "$geogs_na_iter" "$geogs_na_attempt"
  printf '%s\n' "SEALING_$geogs_na_iter" > "$geogs_na_queue/status.txt"
  bash "$geogs_na_code/evaluate.sh" "$geogs_na_region" "$geogs_na_iter" seal "$geogs_na_gpu" "$geogs_na_attempt"
  printf '%s\n' "GEOMETRY_$geogs_na_iter" > "$geogs_na_queue/status.txt"
  flock "$geogs_na_task/no_anchor_sfm_v1/locks/heavy_cpu.lock" \
    bash "$geogs_na_code/evaluate.sh" "$geogs_na_region" "$geogs_na_iter" geometry "$geogs_na_gpu" "$geogs_na_attempt"
  printf '%s\n' "RENDERS_$geogs_na_iter" > "$geogs_na_queue/status.txt"
  bash "$geogs_na_code/evaluate.sh" "$geogs_na_region" "$geogs_na_iter" renders "$geogs_na_gpu" "$geogs_na_attempt"
  bash "$geogs_na_code/evaluate.sh" "$geogs_na_region" "$geogs_na_iter" summary "$geogs_na_gpu" "$geogs_na_attempt"
done
printf '%s\n' "READY_FOR_VIEWER_AND_REVIEW" > "$geogs_na_queue/status.txt"

#!/usr/bin/env bash
set -euo pipefail
geogs_na_region="${1:?P1 P2 P3}"
geogs_na_phase="${2:?train export}"
geogs_na_gpu="${3:?0 or 1}"
geogs_na_iteration="${4:-}"
geogs_na_attempt="${5:-no_anchor_sfm_v1}"
case "$geogs_na_attempt" in no_anchor_sfm_v1|no_anchor_sfm_memory_recovery_v1|no_anchor_sfm_memory_recovery_P2_v1|no_anchor_sfm_memory_recovery_P3_v1|no_anchor_sfm_memory_recovery_v2|no_anchor_sfm_memory_recovery_P2_v2|no_anchor_sfm_memory_recovery_P3_v2|no_anchor_sfm_memory_recovery_P3_v3|no_anchor_sfm_gradient_memory_v3_P1|no_anchor_sfm_gradient_memory_v3_P2|no_anchor_sfm_gradient_memory_v3_P3) ;; *) exit 2 ;; esac
case "$geogs_na_region" in P1|P2|P3) ;; *) exit 2 ;; esac
case "$geogs_na_phase" in train|export) ;; *) exit 2 ;; esac
case "$geogs_na_gpu" in 0|1) ;; *) exit 2 ;; esac
geogs_na_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_na_task=$(realpath "$geogs_na_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_na_exp="$geogs_na_task/$geogs_na_attempt"
geogs_na_image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test "$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')" = "$geogs_na_image"
cmp -s "$geogs_na_repo/configs/phd/geogs_p1p2p3_v1/no_anchor_sfm_v1.json" "$geogs_na_exp/config.json"
geogs_na_run="$geogs_na_exp/runs/$geogs_na_region/SFM_noanchor_D005_Pnative"
geogs_na_out="$geogs_na_run"
geogs_na_extra_mounts=()
geogs_na_extra_args=()
if [[ "$geogs_na_phase" == export ]]; then
  case "$geogs_na_iteration" in 22000|30000) ;; *) exit 2 ;; esac
  geogs_na_out="$geogs_na_run/exports/iteration_$geogs_na_iteration"
  geogs_na_extra_mounts=(--mount "type=bind,src=$geogs_na_run,dst=/trained,readonly")
  geogs_na_extra_args=(--iteration "$geogs_na_iteration")
fi
if [[ "$geogs_na_attempt" != no_anchor_sfm_v1 ]]; then
  geogs_na_extra_mounts+=(--mount "type=bind,src=$geogs_na_exp/amendment.json,dst=/amendment.json,readonly")
  geogs_na_extra_args+=(--memory-recovery)
fi
if [[ "$geogs_na_attempt" == no_anchor_sfm_gradient_memory_v3_* ]]; then
  test "$geogs_na_attempt" = "no_anchor_sfm_gradient_memory_v3_$geogs_na_region"
  test -d "$geogs_na_exp/final_retry_evidence"
  geogs_na_extra_mounts+=(--mount "type=bind,src=$geogs_na_exp/final_retry_evidence,dst=/retry_evidence,readonly")
  geogs_na_extra_args+=(--resource-recovery-version 3)
fi
test ! -e "$geogs_na_out"
test -s "$geogs_na_exp/inputs/$geogs_na_region/initialization_manifest.json"
mkdir -p -- "$geogs_na_out"
cp -- "${BASH_SOURCE[0]}" "$geogs_na_out/launcher_snapshot.sh"
git -C "$geogs_na_repo" rev-parse HEAD > "$geogs_na_out/git_head.txt"
trap 'geogs_na_exit=$?; printf "%s\n" "$geogs_na_exit" > "$geogs_na_out/wrapper_exit_code.txt"' EXIT
docker run --rm --name "jbgs-geogs-${geogs_na_attempt}-${geogs_na_region}-${geogs_na_phase}${geogs_na_iteration}" \
  --network none --gpus "device=$geogs_na_gpu" --cpus 8 --memory 32g --memory-swap 32g --shm-size 4g \
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 \
  --env JBGS_RUNTIME_IMAGE_ID="$geogs_na_image" \
  --env PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128 \
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib \
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 \
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 \
  --mount "type=bind,src=$geogs_na_repo/scripts/phd/geogs_p1p2p3_v1,dst=/audit,readonly" \
  --mount "type=bind,src=$geogs_na_exp/config.json,dst=/config.json,readonly" \
  --mount "type=bind,src=$geogs_na_task/contracts/execution_v1.json,dst=/base_config.json,readonly" \
  --mount "type=bind,src=$geogs_na_exp/source,dst=/source,readonly" \
  --mount "type=bind,src=$geogs_na_exp/inputs/$geogs_na_region,dst=/sfm_input,readonly" \
  --mount "type=bind,src=$geogs_na_task/inputs/$geogs_na_region,dst=/input,readonly" \
  --mount "type=bind,src=$geogs_na_task/runtime/weights,dst=/weights,readonly" \
  --mount "type=bind,src=$geogs_na_out,dst=/output" \
  "${geogs_na_extra_mounts[@]}" "$geogs_na_image" python /audit/no_anchor_v1/run_phase.py \
  --region "$geogs_na_region" --phase "$geogs_na_phase" "${geogs_na_extra_args[@]}" \
  > "$geogs_na_out/wrapper_stdout.log" 2> "$geogs_na_out/wrapper_stderr.log"
cat "$geogs_na_out/wrapper_stdout.log"

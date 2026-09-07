#!/usr/bin/env bash
set -euo pipefail
geogs_na_region="${1:?P1 P2 P3}"
geogs_na_iteration="${2:?22000 30000}"
geogs_na_stage="${3:?seal geometry renders summary}"
geogs_na_gpu="${4:-1}"
geogs_na_attempt="${5:-no_anchor_sfm_v1}"
case "$geogs_na_attempt" in no_anchor_sfm_v1|no_anchor_sfm_memory_recovery_v1|no_anchor_sfm_memory_recovery_P2_v1|no_anchor_sfm_memory_recovery_P3_v1|no_anchor_sfm_memory_recovery_v2|no_anchor_sfm_memory_recovery_P2_v2|no_anchor_sfm_memory_recovery_P3_v2|no_anchor_sfm_memory_recovery_P3_v3|no_anchor_sfm_gradient_memory_v3_P1|no_anchor_sfm_gradient_memory_v3_P2|no_anchor_sfm_gradient_memory_v3_P3) ;; *) exit 2 ;; esac
case "$geogs_na_region" in P1|P2|P3) ;; *) exit 2 ;; esac
case "$geogs_na_iteration" in 22000|30000) ;; *) exit 2 ;; esac
case "$geogs_na_stage" in seal|geometry|renders|summary) ;; *) exit 2 ;; esac
case "$geogs_na_gpu" in 0|1) ;; *) exit 2 ;; esac
geogs_na_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_na_artifacts=$(realpath "$geogs_na_repo/../JointBuildGS-artifacts")
geogs_na_task="$geogs_na_artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
geogs_na_out="$geogs_na_task/evaluation/no_anchor_sfm_v1"
geogs_na_log="$geogs_na_out/execution/$geogs_na_region/R${geogs_na_iteration}/$geogs_na_stage"
geogs_na_image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test ! -e "$geogs_na_log"
mkdir -p -- "$geogs_na_log"
cp -- "${BASH_SOURCE[0]}" "$geogs_na_log/launcher_snapshot.sh"
cp -- "$geogs_na_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/evaluate.py" "$geogs_na_log/evaluate_snapshot.py"
cp -- "$geogs_na_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/final_retry.py" "$geogs_na_log/final_retry.py"
geogs_na_extra=()
if [[ "$geogs_na_stage" == geometry ]]; then
  geogs_na_ref="$geogs_na_artifacts/phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4/run/$geogs_na_region/reference.npz"
  geogs_na_extra+=(--mount "type=bind,src=$geogs_na_ref,dst=/reference/$geogs_na_region/reference.npz,readonly")
fi
if [[ "$geogs_na_stage" == renders ]]; then
  geogs_na_extra+=(--gpus "device=$geogs_na_gpu")
fi
trap 'geogs_na_exit=$?; printf "%s\n" "$geogs_na_exit" > "$geogs_na_log/exit_code.txt"' EXIT
docker run --rm --name "jbgs-geogs-sfm-eval-${geogs_na_region}-${geogs_na_iteration}-${geogs_na_stage}" \
  --network none --cpus 8 --memory 32g --memory-swap 32g --shm-size 4g \
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 \
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 \
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib \
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 \
  --mount "type=bind,src=$geogs_na_task,dst=/task,readonly" \
  --mount "type=bind,src=$geogs_na_out,dst=/out" \
  --mount "type=bind,src=$geogs_na_repo/scripts/phd/geogs_p1p2p3_v1,dst=/audit,readonly" \
  --mount "type=bind,src=$geogs_na_task/sources/GeoGS-state-camera-v1,dst=/source,readonly" \
  --mount "type=bind,src=$geogs_na_task/runtime/weights,dst=/weights,readonly" \
  "${geogs_na_extra[@]}" "$geogs_na_image" \
  python "/out/execution/$geogs_na_region/R${geogs_na_iteration}/$geogs_na_stage/evaluate_snapshot.py" \
  --task /task --experiment "/task/$geogs_na_attempt" --out /out \
  --evaluation-lib /audit/evaluation --region "$geogs_na_region" \
  --iteration "$geogs_na_iteration" --stage "$geogs_na_stage" \
  > "$geogs_na_log/stdout.log" 2> "$geogs_na_log/stderr.log"
cat "$geogs_na_log/stdout.log"

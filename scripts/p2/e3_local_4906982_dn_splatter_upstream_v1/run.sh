#!/usr/bin/env bash
set -euo pipefail

TASK_ROOT=${1:?task root required}
DATA_ROOT=${2:?adapter data root required}
MAX_NUM_ITERATIONS=${DN_MAX_NUM_ITERATIONS:-20000}
STEPS_PER_SAVE=${DN_STEPS_PER_SAVE:-1000}
RUN_TIMESTAMP=${DN_RUN_TIMESTAMP:-R1}
export XDG_CACHE_HOME=${XDG_CACHE_HOME:-${TASK_ROOT}/.cache}
export MPLCONFIGDIR=${MPLCONFIGDIR:-${XDG_CACHE_HOME}/matplotlib}
export TORCH_EXTENSIONS_DIR=${TORCH_EXTENSIONS_DIR:-${XDG_CACHE_HOME}/torch_extensions}
export TORCHINDUCTOR_CACHE_DIR=${TORCHINDUCTOR_CACHE_DIR:-${XDG_CACHE_HOME}/torch_inductor}
export TRITON_CACHE_DIR=${TRITON_CACHE_DIR:-${XDG_CACHE_HOME}/triton}
export USER=jbgs-runtime
export LOGNAME=jbgs-runtime
mkdir -p "${MPLCONFIGDIR}" "${TORCH_EXTENSIONS_DIR}" "${TORCHINDUCTOR_CACHE_DIR}" "${TRITON_CACHE_DIR}"

exec ns-train dn-splatter \
  --output-dir "${TASK_ROOT}/outputs" \
  --experiment-name DEBY_LOD2_4906982 \
  --timestamp "${RUN_TIMESTAMP}" \
  --machine.seed 0 \
  --max-num-iterations "${MAX_NUM_ITERATIONS}" \
  --steps-per-save "${STEPS_PER_SAVE}" \
  --save-only-latest-checkpoint False \
  --steps-per-eval-image 1000 \
  --steps-per-eval-batch 1000 \
  --steps-per-eval-all-images 1000000 \
  --vis tensorboard \
  --pipeline.model.use-depth-loss True \
  --pipeline.model.depth-loss-type EdgeAwareLogL1 \
  --pipeline.model.depth-lambda 0.2 \
  --pipeline.model.use-normal-loss True \
  --pipeline.model.use-normal-tv-loss True \
  --pipeline.model.normal-supervision depth \
  --pipeline.model.two-d-gaussians True \
  --pipeline.model.warmup-length 500 \
  --pipeline.model.stop-split-at 15000 \
  --pipeline.model.camera-optimizer.mode off \
  normal-nerfstudio \
  --data "${DATA_ROOT}" \
  --load-depths True \
  --load-normals False \
  --load-3D-points True \
  --load-pcd-normals True \
  --orientation-method none \
  --center-method none \
  --auto-scale-poses False \
  --scale-factor 1.0 \
  --depth-unit-scale-factor 1.0 \
  --scene-scale 250.0 \
  --eval-mode filename

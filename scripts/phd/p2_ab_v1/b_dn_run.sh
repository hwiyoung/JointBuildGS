#!/usr/bin/env bash
set -euo pipefail
b_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
b_artifacts=$(realpath "$b_repo/../JointBuildGS-artifacts")
b_parent="$b_artifacts/phase-payloads/phd/p2_ab_v1"
b_run=${1:-PHD-P2-AB-B-DN-v2}
b_output="$b_parent/$b_run"
b_source=/artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v1/PHD-P2-AB-B-PRIOR-v2
mkdir "$b_output"
docker run --rm --network none --gpus '"device=1"' --cpus 4 --memory 12g --entrypoint python \
  --mount "type=bind,src=$b_repo,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$b_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$b_output,dst=/output" \
  --mount "type=bind,src=$b_parent/PHD-P2-AB-B-RUNTIME-v1,dst=/root/.cache/torch_extensions" \
  --workdir /workspace/JointBuildGS -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 \
  jointbuildgs:dev -m scripts.phd.p2_ab_v1.b_dn_adapter \
  --source "$b_source" --output /output/data --container-output /task/data \
  2>&1 | tee "$b_output/adapter.console.log"
# The copied runtime cache is task-owned; the old experiment is only read.
cp -a "$b_artifacts/phase-payloads/p2/e3_local_4906982_dn_splatter_upstream_v1/P2-E3-LOCAL-4906982-DN-SPLATTER-UPSTREAM-v1/.cache" "$b_output/.cache"
docker run --rm --network none --gpus '"device=1"' --cpus 4 --memory 12g \
  --mount "type=bind,src=$b_output,dst=/task" \
  --env XDG_CACHE_HOME=/task/.cache --env TORCH_EXTENSIONS_DIR=/task/.cache/torch_extensions \
  --env MPLCONFIGDIR=/task/.cache/matplotlib --env USER=jbgs-runtime --env LOGNAME=jbgs-runtime \
  --env OMP_NUM_THREADS=2 --entrypoint ns-train \
  jointbuildgs:dn-splatter-upstream-97588b4 dn-splatter \
  --output-dir /task/outputs --experiment-name PHD_P2_AB_FIXED_PRIOR --timestamp v1 \
  --machine.seed 0 --max-num-iterations 96 --steps-per-save 96 \
  --steps-per-eval-image 1000 --steps-per-eval-batch 1000 --steps-per-eval-all-images 1000000 \
  --vis tensorboard --pipeline.model.use-depth-loss True \
  --pipeline.model.depth-loss-type EdgeAwareLogL1 --pipeline.model.depth-lambda 0.2 \
  --pipeline.model.use-normal-loss True --pipeline.model.use-normal-tv-loss True \
  --pipeline.model.normal-supervision depth --pipeline.model.two-d-gaussians True \
  --pipeline.model.sh-degree 3 --pipeline.model.num-downscales 0 \
  --pipeline.model.warmup-length 500 --pipeline.model.stop-split-at 0 \
  --pipeline.model.camera-optimizer.mode off normal-nerfstudio \
  --data /task/data --load-depths True --load-normals False --load-3D-points True \
  --load-pcd-normals True --orientation-method none --center-method none \
  --auto-scale-poses False --scale-factor 1.0 --depth-unit-scale-factor 1.0 \
  --scene-scale 250.0 --eval-mode filename \
  2>&1 | tee "$b_output/training.console.log"

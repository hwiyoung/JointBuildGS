#!/usr/bin/env bash
set -euo pipefail
b_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
b_artifacts=$(realpath "$b_repo/../JointBuildGS-artifacts")
b_parent="$b_artifacts/phase-payloads/phd/p2_ab_v1"
b_output="$b_parent/${1:?new DN run with completed training required}"
b_source="$b_parent/PHD-P2-AB-B-PRIOR-v2"
for b_mode in final initial; do
  b_extra=()
  if [[ "$b_mode" == initial ]]; then b_extra=(--initial); fi
  docker run --rm --network none --gpus '"device=1"' --cpus 4 --memory 12g --entrypoint python3 \
    --mount "type=bind,src=$b_repo,dst=/workspace/JointBuildGS,readonly" \
    --mount "type=bind,src=$b_output,dst=/task" --mount "type=bind,src=$b_source,dst=/source,readonly" \
    --env XDG_CACHE_HOME=/task/.cache --env TORCH_EXTENSIONS_DIR=/task/.cache/torch_extensions \
    --env MPLCONFIGDIR=/task/.cache/matplotlib --env OMP_NUM_THREADS=2 \
    jointbuildgs:dn-splatter-upstream-97588b4 \
    /workspace/JointBuildGS/scripts/phd/p2_ab_v1/b_dn_evaluate.py --task /task --source /source "${b_extra[@]}" \
    > "$b_output/evaluation_${b_mode}.console.log" 2>&1
done
docker run --rm --network none --entrypoint python \
  --mount "type=bind,src=$b_repo,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$b_output,dst=/task" --mount "type=bind,src=$b_source,dst=/source,readonly" \
  --workdir /workspace/JointBuildGS -e PYTHONDONTWRITEBYTECODE=1 jointbuildgs:dev \
  -m scripts.phd.p2_ab_v1.b_dn_finalize --task /task --source /source

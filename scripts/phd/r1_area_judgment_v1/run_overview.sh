#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
artifact_root=$(realpath "$repo_root/../JointBuildGS-artifacts")
audit_run=${1:?Pass completed whole-R1 audit attempt}
mkdir "$audit_run/overview_source"
cp "$repo_root/scripts/phd/r1_area_judgment_v1/overview.py" "$audit_run/overview_source/overview.py"
command=(docker run --rm --runtime runc --network none --cpus 2 --memory 4g --user "$(id -u):$(id -g)"
  -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=2 -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= -e MPLCONFIGDIR=/tmp/mpl
  --mount "type=bind,source=$audit_run/source,target=/repo,readonly"
  --mount "type=bind,source=$audit_run/overview_source,target=/driver,readonly"
  --mount "type=bind,source=$audit_run/result,target=/evidence,readonly"
  --mount "type=bind,source=$audit_run,target=/output"
  --mount "type=bind,source=$artifact_root/phase-payloads/p2/mvs_native_textured_mesh_preflight_v1/P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2/work/mvs/openmvs/dim_dense.ply,target=/fused.ply,readonly"
  --mount type=bind,source=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc,target=/font.ttf,readonly
  --entrypoint python sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774 /driver/overview.py)
printf '%q ' "${command[@]}" > "$audit_run/overview_command.sh"
printf '\n' >> "$audit_run/overview_command.sh"
"${command[@]}" 2>&1 | tee "$audit_run/overview.log"

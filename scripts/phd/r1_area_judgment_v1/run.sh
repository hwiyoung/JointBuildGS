#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
artifact_root=$(realpath "$repo_root/../JointBuildGS-artifacts")
task_root="$artifact_root/phase-payloads/phd/r1_area_judgment_v1/PHD-R1-AREA-JUDGMENT-v1"
mkdir -p "$task_root"
audit_run=$(mktemp -d "$task_root/attempt_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXXXX")
mkdir -p "$audit_run/source"
for relative in scripts/phd/r1_area_judgment_v1 configs/phd/r1_area_judgment_v1 src/phd/region_view_support_v1.py; do
  mkdir -p "$audit_run/source/$(dirname "$relative")"
  cp -a "$repo_root/$relative" "$audit_run/source/$relative"
done
git -C "$repo_root" rev-parse HEAD > "$audit_run/commit.txt"
image=sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774
docker image inspect "$image" > "$audit_run/image_inspect.json"
command=(docker run --rm --runtime runc --network none --cpus 4 --memory 8g --user "$(id -u):$(id -g)"
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=4
  -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= -e MPLCONFIGDIR=/tmp/mpl
  --mount "type=bind,source=$audit_run/source,target=/repo,readonly"
  --mount "type=bind,source=$artifact_root/phase-payloads/phd/r1_mvs_control_v1/PHD-R1-MVS-CONTROL-PREP-v1/attempt_20260916T130151Z_jm4gu7vc/result/input,target=/input,readonly"
  --mount "type=bind,source=$artifact_root/phase-payloads/phd/region_view_support_v1/PHD-R1R5-VIEW-SUPPORT-v1/attempt_20260915T130845Z_TkeMtl/result,target=/audit,readonly"
  --mount "type=bind,source=$artifact_root/phase-payloads/p2/mvs_native_textured_mesh_preflight_v1/P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2/work/mvs/openmvs/dim_dense.ply,target=/fused.ply,readonly"
  --mount "type=bind,source=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc,target=/font.ttf,readonly"
  --mount "type=bind,source=$audit_run,target=/output" --entrypoint python "$image"
  /repo/scripts/phd/r1_area_judgment_v1/audit.py --config /repo/configs/phd/r1_area_judgment_v1/audit_v1.json --output /output/result)
printf '%q ' "${command[@]}" > "$audit_run/command.sh"
printf '\n' >> "$audit_run/command.sh"
printf 'AUDIT_RUN=%s\n' "$audit_run"
"${command[@]}" 2>&1 | tee "$audit_run/run.log"

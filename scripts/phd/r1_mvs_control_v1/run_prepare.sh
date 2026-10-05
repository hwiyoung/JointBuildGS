#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
artifact_root=$(realpath "$repo_root/../JointBuildGS-artifacts")
task_root="$artifact_root/phase-payloads/phd/r1_mvs_control_v1/PHD-R1-MVS-CONTROL-PREP-v1"
mkdir -p "$task_root"
prep_run=$(mktemp -d "$task_root/attempt_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXXXX")
mkdir -p "$prep_run/source"
for relative in scripts/phd/r1_mvs_control_v1 scripts/phd/geogs_p1p2p3_v1/input \
    scripts/phd/wu_vallet_p3_v2 src/phd/region_view_support_v1.py src/phd/geogs_mvs_pgsr_v1 \
    src/phd/wu_vallet_p3_v1 src/phd/wu_vallet_p3_v2 \
    configs/phd/r1_mvs_control_v1 configs/phd/mvs_als_source_relation_v1/run_v1.json; do
  mkdir -p "$prep_run/source/$(dirname "$relative")"
  cp -a "$repo_root/$relative" "$prep_run/source/$relative"
done
git -C "$repo_root" rev-parse HEAD > "$prep_run/commit.txt"
image=sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774
docker image inspect "$image" > "$prep_run/image_inspect.json"
command=(docker run --rm --runtime runc --network none --cpus 4 --memory 12g --user "$(id -u):$(id -g)"
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=4
  -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= -e MPLCONFIGDIR=/tmp/mpl
  --mount "type=bind,source=$prep_run/source,target=/repo,readonly"
  --mount "type=bind,source=$artifact_root/phase-payloads/phd/region_view_support_v1/PHD-R1R5-VIEW-SUPPORT-v1/attempt_20260915T130845Z_TkeMtl,target=/audit,readonly"
  --mount "type=bind,source=$artifact_root/phase-payloads/p0-audit/data/work/mvs/colmap_dense,target=/cameras,readonly"
  --mount "type=bind,source=$artifact_root/phase-payloads/p0-audit/data/raw/als,target=/als,readonly"
  --mount "type=bind,source=$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/sources/GeoGS,target=/geogs_original,readonly"
  --mount "type=bind,source=$prep_run,target=/output" --entrypoint python "$image"
  /repo/scripts/phd/r1_mvs_control_v1/prepare.py --config /repo/configs/phd/r1_mvs_control_v1/preparation_v1.json --output /output/result)
printf '%q ' "${command[@]}" > "$prep_run/command.sh"
printf '\n' >> "$prep_run/command.sh"
printf 'PREPARATION_RUN=%s\n' "$prep_run"
"${command[@]}" 2>&1 | tee "$prep_run/run.log"

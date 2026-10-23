#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
PH="$ART/phase-payloads/phd"
TASK_OUT="$PH/main_uncert_view_v1/PHD-MAIN-UNCERT-VIEW-v1"
mkdir -p "$TASK_OUT/logs"
exec docker run --rm --network none --user "$(id -u):$(id -g)" --cpus "${VIEW_CPUS:-8}" --memory 32g --memory-swap 32g \
  -e CUDA_VISIBLE_DEVICES= -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONUNBUFFERED=1 -e TZ=Asia/Seoul -e VIEW_COMMIT="$(git -C "$REPO" rev-parse HEAD)" \
  -e VIEW_IMAGE="$(docker image inspect jointbuildgs:dev -f '{{.Id}}')" \
  -v "$REPO:/repo:ro" -v "$PH:/ph:ro" -v "$ART:/art:ro" \
  -v "$PH/main_uncert_v1/PHD-MAIN-UNCERT-v1:/out:ro" \
  -v "$PH/main_stage1_v1/PHD-MAIN-STAGE1-v1:/s1:ro" \
  -v "$TASK_OUT:/view" -v "$REPO/configs/phd/main_uncert_view_v1:/cfg" \
  -v "$REPO/docs/experiments/phd/main_uncert_view_v1:/docs" \
  -w /tmp --entrypoint python jointbuildgs:dev -I -u "/repo/scripts/phd/main_uncert_view_v1/$@"

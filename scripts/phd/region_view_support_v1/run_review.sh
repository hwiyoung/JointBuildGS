#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
artifact_root=$(realpath "$repo_root/../JointBuildGS-artifacts")
audit_run=$(realpath "${1:?Pass the completed audit attempt directory}")
test -f "$audit_run/result/receipt.json"
test ! -e "$audit_run/review_source"
mkdir "$audit_run/review_source"
cp "$repo_root/scripts/phd/region_view_support_v1/review.py" "$audit_run/review_source/review.py"
cp "$repo_root/scripts/phd/region_view_support_v1/run_review.sh" "$audit_run/review_source/run_review.sh"
audit_image=$(docker image inspect --format '{{.Id}}' jointbuildgs:dev)
printf '%s\n' "$audit_image" > "$audit_run/review_image_id.txt"
docker run --rm --runtime runc --network none --cpus 2 --memory 3g --user "$(id -u):$(id -g)" \
  -e PYTHONPATH=/repo -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 \
  -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= -e MPLCONFIGDIR=/tmp/mpl \
  -v "$audit_run/source:/repo:ro" -v "$audit_run/result:/input:ro" \
  -v "$audit_run/review_source:/review_source:ro" \
  -v "$artifact_root/phase-payloads/p0-audit/data/work/mvs/colmap_dense:/cameras:ro" \
  --mount "type=bind,source=$artifact_root/phase-payloads/phd/manual_region_masks_v1/support_audit.rvEKKQ/result/reference_sample_support.npz,target=/p1_ground/reference_sample_support.npz,readonly" \
  -v "$artifact_root/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/inputs_v2/P1/bindings.json:/bindings/P1.json:ro" \
  -v /usr/share/fonts/opentype/noto:/font:ro -v "$audit_run:/output" --entrypoint python "$audit_image" \
  /review_source/review.py --result /input --output /output/review \
  2>&1 | tee "$audit_run/review.log"

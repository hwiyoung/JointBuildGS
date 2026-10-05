#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
artifact_root=$(realpath "$repo_root/../JointBuildGS-artifacts")
p1_probe="$artifact_root/phase-payloads/phd/manual_region_masks_v1/support_audit.rvEKKQ/result/reference_sample_support.npz"
test -f "$p1_probe"
audit_parent="$artifact_root/phase-payloads/phd/region_view_support_v1/PHD-R1R5-VIEW-SUPPORT-v1"
mkdir -p "$audit_parent"
audit_run=$(mktemp -d "$audit_parent/attempt_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXX")
snapshot_root="$audit_run/source"
mkdir -p "$snapshot_root"
for relative in \
  src/phd/region_view_support_v1.py \
  src/stage2/colmap_io.py \
  scripts/phd/region_view_support_v1/audit.py \
  scripts/phd/region_view_support_v1/run.sh \
  configs/phd/region_view_support_v1/regions_v1.json \
  artifacts/manifests/gate_s0/common_base_r2b/exact_937_member_crosswalk_v1.json \
  tests/phd/region_view_support_v1/test_support.py; do
  mkdir -p "$snapshot_root/$(dirname "$relative")"
  cp "$repo_root/$relative" "$snapshot_root/$relative"
done
git -C "$repo_root" rev-parse HEAD > "$audit_run/source_git_head.txt"
docker image inspect jointbuildgs:dev > "$audit_run/docker_image_inspect.json"
audit_image=$(docker image inspect --format '{{.Id}}' jointbuildgs:dev)
printf 'AUDIT_RUN=%s\n' "$audit_run"
docker run --rm --network none --cpus 2 --memory 1g \
  -e PYTHONPATH=/repo -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=1 \
  -v "$snapshot_root:/repo:ro" --entrypoint python "$audit_image" \
  -m unittest discover -s /repo/tests/phd/region_view_support_v1 -v \
  2>&1 | tee "$audit_run/unit_tests.log"
bindings_root="$artifact_root/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/inputs_v2"
docker run --rm --name "jbgs-r1r5-audit-$(basename "$audit_run")" \
  --network none --cpus 4 --memory 6g --user "$(id -u):$(id -g)" \
  -e PYTHONPATH=/repo -e PYTHONDONTWRITEBYTECODE=1 \
  -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -e "JBGS_SOURCE_GIT_HEAD=$(cat "$audit_run/source_git_head.txt")" \
  -v "$snapshot_root:/repo:ro" \
  -v "$artifact_root/phase-payloads/p0-audit/data/work/mvs/colmap_dense:/cameras:ro" \
  -v "$artifact_root/phase-payloads/p2/mvs_native_textured_mesh_preflight_v1/P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2/work/mvs/openmvs/dim_dense.ply:/fused/dim_dense.ply:ro" \
  --mount "type=bind,source=$p1_probe,target=/p1_ground/reference_sample_support.npz,readonly" \
  -v "$bindings_root/P1/bindings.json:/bindings/P1.json:ro" \
  -v "$bindings_root/P2/bindings.json:/bindings/P2.json:ro" \
  -v "$bindings_root/P3/bindings.json:/bindings/P3.json:ro" \
  -v "$audit_run:/output" --entrypoint python "$audit_image" \
  /repo/scripts/phd/region_view_support_v1/audit.py \
  --config /repo/configs/phd/region_view_support_v1/regions_v1.json --output /output/result \
  2>&1 | tee "$audit_run/audit.log"

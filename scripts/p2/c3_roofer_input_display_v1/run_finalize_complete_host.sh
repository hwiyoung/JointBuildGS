#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${JBGS_ARTIFACT_ROOT:-/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts}"
base="phase-payloads/p2/c3_roofer_input_display_v1"
source_rel="${base}/P2-C3-12ROW-COMPARISON-DISPLAY-RECOVERY-v6"
input_rel="${base}/P2-C3-ROOFER-INPUT-DISPLAY-RECOVERY-v3"
diagnostic_rel="phase-payloads/p2/c3_tsdf_roof_diagnostic_v1/P2-C3-TSDF-ROOF-DIAGNOSTIC-RENDER-RECOVERY-v1"
output_rel="${base}/P2-C3-COMPLETE-LINEAGE-REPORT-RECOVERY-v4"
output_root="${artifact_root}/${output_rel}"
image="jointbuildgs:dev"
expected_image="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
host_uid="$(id -u)"
host_gid="$(id -g)"

if [[ -n "$(git -C "${repo_root}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "complete-lineage finalization requires a clean source checkout" >&2
  exit 2
fi
head_commit="$(git -C "${repo_root}" rev-parse HEAD)"
if [[ "${head_commit}" != "$(git -C "${repo_root}" rev-parse origin/main)" ]]; then
  echo "complete-lineage finalization requires HEAD=origin/main" >&2
  exit 2
fi
if [[ "$(docker image inspect "${image}" --format '{{.Id}}')" != "${expected_image}" ]]; then
  echo "project image identity mismatch" >&2
  exit 2
fi
if [[ -e "${output_root}" ]]; then
  echo "add-once report namespace already exists: ${output_root}" >&2
  exit 2
fi
docker run --rm --network none -v "${artifact_root}:/artifacts/JointBuildGS" "${image}" \
  sh -lc "install -d -o ${host_uid} -g ${host_gid} -m 0755 '/artifacts/JointBuildGS/${output_rel}/reports' '/artifacts/JointBuildGS/${output_rel}/control'"
docker run --rm --network none --user "${host_uid}:${host_gid}" \
  -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
  -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS "${image}" python -B -m scripts.p2.c3_roofer_input_display_v1.finalize_complete \
  --source-root "/artifacts/JointBuildGS/${source_rel}" \
  --input-root "/artifacts/JointBuildGS/${input_rel}" \
  --diagnostic-root "/artifacts/JointBuildGS/${diagnostic_rel}" \
  --output-root "/artifacts/JointBuildGS/${output_rel}" \
  --source-commit "${head_commit}"

echo "C3 complete-lineage report closed: ${output_root}"

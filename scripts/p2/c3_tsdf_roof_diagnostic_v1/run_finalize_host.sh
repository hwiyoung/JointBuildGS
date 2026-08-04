#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${JBGS_ARTIFACT_ROOT:-/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts}"
relative_root="phase-payloads/p2/c3_tsdf_roof_diagnostic_v1/P2-C3-TSDF-ROOF-DIAGNOSTIC-RENDER-RECOVERY-v1"
output_root="${artifact_root}/${relative_root}"
plugin_root="/home/innopam/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.8-13ceeea1f599"
image="jointbuildgs:dev"
expected_image="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
host_uid="$(id -u)"
host_gid="$(id -g)"

if [[ -n "$(git -C "${repo_root}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "C3 TSDF diagnostic finalization requires a clean source checkout" >&2
  exit 2
fi
head_commit="$(git -C "${repo_root}" rev-parse HEAD)"
if [[ "${head_commit}" != "$(git -C "${repo_root}" rev-parse origin/main)" ]]; then
  echo "C3 TSDF diagnostic finalization requires HEAD=origin/main" >&2
  exit 2
fi
if [[ "$(docker image inspect "${image}" --format '{{.Id}}')" != "${expected_image}" ]]; then
  echo "project image identity mismatch" >&2
  exit 2
fi
if [[ ! -f "${output_root}/qualitative/index_v1.json" ]]; then
  echo "completed render output is missing" >&2
  exit 2
fi

docker run --rm --network none \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  "${image}" sh -lc "install -d -o ${host_uid} -g ${host_gid} -m 0755 '/artifacts/JointBuildGS/${relative_root}/reports' && chown ${host_uid}:${host_gid} '/artifacts/JointBuildGS/${relative_root}/control'"

docker run --rm --network none \
  --user "${host_uid}:${host_gid}" \
  -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "${image}" python -B -m scripts.p2.c3_tsdf_roof_diagnostic_v1.finalize prepare \
    --output-root "/artifacts/JointBuildGS/${relative_root}"

node "${plugin_root}/skills/build-report/scripts/deliver_portable_artifact.mjs" \
  --input "${output_root}/reports/artifact.json" \
  --output "${output_root}/reports/report.html"

docker run --rm --network none \
  --user "${host_uid}:${host_gid}" \
  -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "${image}" python -B -m scripts.p2.c3_tsdf_roof_diagnostic_v1.finalize seal \
    --output-root "/artifacts/JointBuildGS/${relative_root}" \
    --source-commit "${head_commit}"

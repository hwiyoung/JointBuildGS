#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${JBGS_ARTIFACT_ROOT:-$(cd "${repo_root}/../JointBuildGS-artifacts" && pwd)}"
output_root="${artifact_root}/phase-payloads/p2/c2_mvs_improvement_census_199_v1/P2-C2-MVS-IMPROVEMENT-CENSUS-199-v1"

docker run --rm --network none \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS \
  jointbuildgs:dev \
  python -B scripts/p2/c2_mvs_improvement_census_199_v1/analyze.py \
    --artifact-root /artifacts/JointBuildGS \
    --output-root /artifacts/JointBuildGS/phase-payloads/p2/c2_mvs_improvement_census_199_v1/P2-C2-MVS-IMPROVEMENT-CENSUS-199-v1

echo "${output_root}"

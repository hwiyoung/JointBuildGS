#!/usr/bin/env bash
# Run only after CORRECTED-NATIVE-v1 has completed; all outputs are new and fail if present.
set -euo pipefail
b_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$b_repo"
test -f ../JointBuildGS-artifacts/phase-payloads/phd/p2_ab_v2/PHD-P2-AB-V2-B-CORRECTED-NATIVE-v1/result.json
bash scripts/phd/p2_ab_v2/b_gradient_corrected_docker.sh
bash scripts/phd/p2_ab_v2/b_run_corrected_docker.sh configs/phd/p2_ab_v2/b_corrected_representation_v1.json PHD-P2-AB-V2-B-CORRECTED-REPRESENTATION-v1
bash scripts/phd/p2_ab_v2/b_run_corrected_docker.sh configs/phd/p2_ab_v2/b_corrected_prior_shift_v1.json PHD-P2-AB-V2-B-CORRECTED-PRIOR-SHIFT-v1
bash scripts/phd/p2_ab_v2/b_verify_corrected_docker.sh

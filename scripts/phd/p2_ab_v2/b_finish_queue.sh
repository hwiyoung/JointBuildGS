#!/usr/bin/env bash
# Continue only this turn's declared new experiments after its current main run.
set -euo pipefail
b_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
b_parent=$(realpath "$b_repo/../JointBuildGS-artifacts")/phase-payloads/phd/p2_ab_v2
while [[ ! -f "$b_parent/PHD-P2-AB-V2-B-NATIVE-v1/result.json" ]]; do
  if [[ -f "$b_parent/PHD-P2-AB-V2-B-NATIVE-v1/FAILED.json" ]]; then exit 1; fi
  sleep 5
done
cd "$b_repo"
bash scripts/phd/p2_ab_v2/b_run_docker.sh configs/phd/p2_ab_v2/b_fixed_corrected_v2.json PHD-P2-AB-V2-B-NATIVE-FIXED-v2
bash scripts/phd/p2_ab_v2/b_run_docker.sh configs/phd/p2_ab_v2/b_representation_v1.json PHD-P2-AB-V2-B-REPRESENTATION-v1
bash scripts/phd/p2_ab_v2/b_run_docker.sh configs/phd/p2_ab_v2/b_prior_shift_v1.json PHD-P2-AB-V2-B-PRIOR-SHIFT-v1
bash scripts/phd/p2_ab_v2/b_verify_docker.sh

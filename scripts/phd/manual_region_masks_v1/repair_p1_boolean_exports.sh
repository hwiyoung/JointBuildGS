#!/usr/bin/env bash
set -euo pipefail
FIX_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
FIX_ARTIFACTS="$(realpath "$FIX_REPO/../JointBuildGS-artifacts")"
FIX_ROOT="$FIX_ARTIFACTS/phase-payloads/phd/manual_region_masks_v1/PHD-P1-MANUAL-REGIONS-v1"
FIX_PARENT="$FIX_ROOT/attempt.uCJGq4"
FIX_IMAGE=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
FIX_OUT="$(mktemp -d "$FIX_ROOT/attempt.boolfix.XXXXXX")"
mkdir "$FIX_OUT/source" "$FIX_OUT/qa"
cp "$FIX_REPO/scripts/phd/manual_region_masks_v1/"*.py "$FIX_OUT/source/"
cp "$FIX_REPO/scripts/phd/manual_region_masks_v1/"*.sh "$FIX_OUT/source/"
cp "$FIX_REPO/src/phd/manual_region_masks_v1.py" "$FIX_OUT/source/"
cp "$FIX_REPO/src/phd/geogs_mvs_pgsr_v1/mvs_depth.py" "$FIX_OUT/source/"
cp "$FIX_REPO/configs/phd/manual_region_masks_v1/p1_v1.json" "$FIX_OUT/source/"
cp "$FIX_REPO/tests/phd/test_manual_region_masks_v1.py" "$FIX_OUT/source/"
git -C "$FIX_REPO" rev-parse HEAD > "$FIX_OUT/commit.txt"
FIX_CMD=(docker run --rm --runtime runc --network none --cpus 2 --memory 2g
  --user "$(id -u):$(id -g)" --read-only --cap-drop ALL --security-opt no-new-privileges
  -e OPENBLAS_NUM_THREADS=2 -e OMP_NUM_THREADS=2 -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES=
  -v "$FIX_PARENT:/parent_attempt:ro" -v "$FIX_OUT:/output:rw"
  -v "$FIX_ARTIFACTS/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/inputs/P1:/prior_input:ro"
  -v "$FIX_ARTIFACTS/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/inputs_v2/P1:/mvs_input:ro"
  --entrypoint python "$FIX_IMAGE" /output/source/repair_boolean_exports.py)
printf '%q ' "${FIX_CMD[@]}" > "$FIX_OUT/repair_command.txt"
printf '\n' >> "$FIX_OUT/repair_command.txt"
printf 'FIXED_ATTEMPT=%s\n' "$FIX_OUT"
"${FIX_CMD[@]}" 2>&1 | tee "$FIX_OUT/repair.log"
FIX_QA=(docker run --rm --runtime runc --network none --cpus 2 --memory 2g
  --user "$(id -u):$(id -g)" --read-only --cap-drop ALL --security-opt no-new-privileges
  -e OPENBLAS_NUM_THREADS=2 -e OMP_NUM_THREADS=2 -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES=
  -v "$FIX_OUT/result:/result:ro" -v "$FIX_OUT/source:/source:ro" -v "$FIX_OUT/qa:/qa:rw"
  --entrypoint python "$FIX_IMAGE" /source/validate_output.py --result /result --output /qa/receipt.json)
printf '%q ' "${FIX_QA[@]}" > "$FIX_OUT/qa_command.txt"
printf '\n' >> "$FIX_OUT/qa_command.txt"
"${FIX_QA[@]}" 2>&1 | tee "$FIX_OUT/qa/run.log"

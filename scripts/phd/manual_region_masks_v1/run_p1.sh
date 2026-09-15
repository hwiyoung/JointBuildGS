#!/usr/bin/env bash
set -euo pipefail
MASK_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
MASK_ARTIFACTS="$(realpath "$MASK_REPO/../JointBuildGS-artifacts")"
MASK_PARENT="$MASK_ARTIFACTS/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/inputs/P1"
MASK_MVS="$MASK_ARTIFACTS/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/inputs_v2/P1"
MASK_ROOT="$MASK_ARTIFACTS/phase-payloads/phd/manual_region_masks_v1/PHD-P1-MANUAL-REGIONS-v1"
MASK_IMAGE=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
mkdir -p "$MASK_ROOT"
MASK_ATTEMPT="$(mktemp -d "$MASK_ROOT/attempt.XXXXXX")"
mkdir "$MASK_ATTEMPT/source"
cp "$MASK_REPO/scripts/phd/manual_region_masks_v1/generate.py" "$MASK_ATTEMPT/source/"
cp "$MASK_REPO/scripts/phd/manual_region_masks_v1/run_p1.sh" "$MASK_ATTEMPT/source/"
cp "$MASK_REPO/src/phd/manual_region_masks_v1.py" "$MASK_ATTEMPT/source/"
cp "$MASK_REPO/src/phd/geogs_mvs_pgsr_v1/mvs_depth.py" "$MASK_ATTEMPT/source/"
cp "$MASK_REPO/configs/phd/manual_region_masks_v1/p1_v1.json" "$MASK_ATTEMPT/source/"
cp "$MASK_REPO/tests/phd/test_manual_region_masks_v1.py" "$MASK_ATTEMPT/source/"
git -C "$MASK_REPO" rev-parse HEAD > "$MASK_ATTEMPT/commit.txt"
MASK_COMMIT="$(cat "$MASK_ATTEMPT/commit.txt")"
MASK_CMD=(docker run --rm --runtime runc --network none --cpus 2 --memory 4g
  --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges
  --read-only --tmpfs /tmp:rw,size=512m -e MPLCONFIGDIR=/tmp/mpl
  -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2
  -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES=
  -v "$MASK_PARENT:/prior_input:ro"
  -v "$MASK_MVS:/mvs_input:ro"
  -v /usr/share/fonts/opentype/noto:/font:ro
  -v "$MASK_ATTEMPT:/output:rw"
  --entrypoint python "$MASK_IMAGE" /output/source/generate.py
  --config /output/source/p1_v1.json --output /output/result
  --commit "$MASK_COMMIT" --runtime-image-id "$MASK_IMAGE")
printf '%q ' "${MASK_CMD[@]}" > "$MASK_ATTEMPT/command.txt"
printf '\n' >> "$MASK_ATTEMPT/command.txt"
printf 'MASK_ATTEMPT=%s\n' "$MASK_ATTEMPT"
"${MASK_CMD[@]}" 2>&1 | tee "$MASK_ATTEMPT/run.log"

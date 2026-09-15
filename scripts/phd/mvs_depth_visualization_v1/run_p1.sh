#!/usr/bin/env bash
set -euo pipefail
VIS_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
VIS_ARTIFACTS="$(realpath "$VIS_REPO/../JointBuildGS-artifacts")"
VIS_PARENT="$VIS_ARTIFACTS/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/inputs/P1"
VIS_MVS="$VIS_ARTIFACTS/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
VIS_ROOT="$VIS_ARTIFACTS/phase-payloads/phd/mvs_depth_visualization_v1/PHD-P1-MVS-INPUT-VIS-v1"
VIS_IMAGE=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
mkdir -p "$VIS_ROOT"
VIS_ATTEMPT="$(mktemp -d "$VIS_ROOT/attempt.XXXXXX")"
mkdir "$VIS_ATTEMPT/source"
cp "$VIS_REPO/scripts/phd/mvs_depth_visualization_v1/visualize.py" "$VIS_ATTEMPT/source/"
cp "$VIS_REPO/scripts/phd/mvs_depth_visualization_v1/run_p1.sh" "$VIS_ATTEMPT/source/"
cp "$VIS_REPO/src/phd/geogs_mvs_pgsr_v1/mvs_depth.py" "$VIS_ATTEMPT/source/"
cp "$VIS_REPO/configs/phd/mvs_depth_visualization_v1/p1_v1.json" "$VIS_ATTEMPT/source/"
git -C "$VIS_REPO" rev-parse HEAD > "$VIS_ATTEMPT/commit.txt"
VIS_COMMIT="$(cat "$VIS_ATTEMPT/commit.txt")"
VIS_CMD=(docker run --rm --network none --cpus 2 --memory 4g
  --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges
  --read-only --tmpfs /tmp:rw,size=512m -e MPLCONFIGDIR=/tmp/mpl
  -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2
  -v "$VIS_REPO:/repo:ro"
  -v "$VIS_PARENT:/prior_input:ro"
  -v "$VIS_MVS/inputs_v2/P1:/mvs_input:ro"
  -v "$VIS_MVS/viewer_rgb_v1/rgb_diagnostic_v1/attempt.Ym5F9Uzs/selection.json:/selection.json:ro"
  -v /usr/share/fonts/opentype/noto:/font:ro
  -v "$VIS_ATTEMPT:/output:rw"
  --entrypoint python "$VIS_IMAGE" /output/source/visualize.py
  --config /output/source/p1_v1.json --output /output/figures
  --commit "$VIS_COMMIT" --runtime-image-id "$VIS_IMAGE")
printf '%q ' "${VIS_CMD[@]}" > "$VIS_ATTEMPT/command.txt"
printf '\n' >> "$VIS_ATTEMPT/command.txt"
printf 'VISUALIZATION_ATTEMPT=%s\n' "$VIS_ATTEMPT"
"${VIS_CMD[@]}" 2>&1 | tee "$VIS_ATTEMPT/run.log"

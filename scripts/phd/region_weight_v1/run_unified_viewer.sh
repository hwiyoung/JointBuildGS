#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
payload=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd")
viewer="$payload/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/viewer_rgb_v1/weights_v1"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
mkdir "$viewer"
mkdir "$viewer/source"
cp "$repo/scripts/phd/region_weight_v1/build_unified_viewer.py" "$viewer/source/"
cp "$repo/scripts/phd/region_weight_v1/run_unified_viewer.sh" "$viewer/source/"
cp "$repo/configs/phd/region_weight_v1/unified_viewer_v1.json" "$viewer/source/config.json"
cp "$repo/src/phd/geogs_mvs_pgsr_v1/mvs_depth.py" "$viewer/source/"
git -C "$repo" rev-parse HEAD > "$viewer/source/repository_head.txt"
docker run --rm --runtime runc --network none --cpus 2 --memory 4g \
  --user "$(id -u):$(id -g)" -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= \
  -e MPLCONFIGDIR=/tmp/mpl -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 \
  -v "$repo:/repo:ro" -v "$payload:/payload:ro" -v "$viewer:/out" \
  -v /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc:/font/NotoSansCJK-Regular.ttc:ro \
  --entrypoint python "$image" /out/source/build_unified_viewer.py --config /out/source/config.json \
  > "$viewer/build.log" 2>&1
cat "$viewer/build.log"

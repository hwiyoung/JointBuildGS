#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
image="jointbuildgs:dev"
revision="dca509fe793f601edb92606367a655c15ac00fdf"
runtime="results/tum_transfer/e5_s3b0/runtime/sam_vit_b"
host_uid="$(id -u)"
host_gid="$(id -g)"

docker run --rm -i \
  -v "${repo}:/workspace/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "${image}" bash -lc "
set -euo pipefail
mkdir -p '${runtime}'
git config --global --add safe.directory '/workspace/JointBuildGS/${runtime}/segment-anything'
if [ ! -d '${runtime}/segment-anything/.git' ]; then
  git clone https://github.com/facebookresearch/segment-anything.git '${runtime}/segment-anything'
fi
git -C '${runtime}/segment-anything' fetch --depth=1 origin '${revision}'
git -C '${runtime}/segment-anything' checkout --detach '${revision}'
if [ ! -f '${runtime}/sam_vit_b_01ec64.pth' ]; then
  curl -fL --retry 3 -o '${runtime}/sam_vit_b_01ec64.pth.tmp' \
    https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth
  mv '${runtime}/sam_vit_b_01ec64.pth.tmp' '${runtime}/sam_vit_b_01ec64.pth'
fi
chown -R '${host_uid}:${host_gid}' '${runtime}'
"

docker run --rm -i --gpus all \
  --user "${host_uid}:${host_gid}" \
  -e CUDA_VISIBLE_DEVICES="${S3B0_GPU:-1}" \
  -e MPLCONFIGDIR=/tmp/matplotlib \
  -e XDG_CACHE_HOME=/tmp \
  -v "${repo}:/workspace/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "${image}" \
  python scripts/experiments/e5_c001_s3b0/e5_c001_s3b0_semantic.py --device cuda

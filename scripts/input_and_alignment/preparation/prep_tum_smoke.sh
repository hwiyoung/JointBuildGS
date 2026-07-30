#!/usr/bin/env bash
# Data adapter — P2 TUM transfer smoke (vanilla 2DGS engine check).
#
# Stages the P0 TUM undistorted COLMAP-dense workspace into the layout
# src/stage2/dataloader.py (ColmapDataset) expects:  data_root/images/ +
# data_root/sparse/0/{cameras,images,points3D}.bin
#
# Uses RELATIVE symlinks (ln -sr) so paths resolve identically on the host and
# inside the Docker bind mount (/workspace/JointBuildGS). Source is read-only;
# stereo/frames/rigs are intentionally NOT staged (pure vanilla: photo+nc only,
# no depth/normal/semantic). No engine logic changed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SRC_REL="phases/p0-audit/data/work/mvs/colmap_dense"   # image_undistorter output (PINHOLE)
SRC="$ROOT/$SRC_REL"
DST="$ROOT/results/tum_transfer/data"

[ -d "$SRC/images" ]            || { echo "ERROR: missing $SRC/images"; exit 1; }
[ -f "$SRC/sparse/cameras.bin" ] || { echo "ERROR: missing $SRC/sparse/cameras.bin"; exit 1; }

rm -rf "$DST"
mkdir -p "$DST/sparse/0"
ln -sr "$SRC/images" "$DST/images"
for f in cameras images points3D; do
  ln -sr "$SRC/sparse/$f.bin" "$DST/sparse/0/$f.bin"
done

echo "staged data_root: $DST"
ls -l "$DST" "$DST/sparse/0"
echo "image count: $(ls "$SRC/images" | wc -l)"

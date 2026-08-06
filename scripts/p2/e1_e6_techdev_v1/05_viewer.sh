#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
run_dev python scripts/p2/e1_e6_techdev_v1/build_viewer.py \
  --repository-root /workspace/JointBuildGS --artifact-root /artifacts/JointBuildGS \
  >"${logs_root}/05_viewer.log" 2>&1
printf 'Viewer ready: %s/viewer/index.html\n' "${task_root}"

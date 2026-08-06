#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${root}/00_prep.sh"
"${root}/01_mvs.sh"
"${root}/02_lambda_grid.sh"
for condition in E3 E4 E5 E6; do "${root}/02_train_${condition}.sh"; done
"${root}/03_extract.sh"
"${root}/04_roofer.sh"
"${root}/05_viewer.sh"
"${root}/06_semantic_gt.sh"
"${root}/07_eval.sh"

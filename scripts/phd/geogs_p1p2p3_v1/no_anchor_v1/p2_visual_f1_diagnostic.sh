#!/usr/bin/env bash
set -euo pipefail
diag_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
diag_task=$(realpath "$diag_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
diag_out="$diag_task/evaluation/no_anchor_sfm_prefix8000_v1/p2_native30k_vs_sfm8k_diagnostic_v1"
test ! -e "$diag_out"
mkdir -p "$diag_out/code"
cp -- "${BASH_SOURCE[0]}" "$(dirname -- "${BASH_SOURCE[0]}")/p2_visual_f1_diagnostic.py" "$diag_out/code/"
cp -- "$diag_repo/configs/phd/geogs_p1p2p3_v1/p2_visual_f1_diagnostic_v1.json" "$diag_out/config.json"
trap 'diag_exit=$?; printf "%s\n" "$diag_exit" > "$diag_out/exit_code.txt"' EXIT
diag_command=(docker run --rm --network none --cpus 2 --memory 2g --memory-swap 2g
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 --env OPENBLAS_NUM_THREADS=1 --env OMP_NUM_THREADS=1
  --env MPLCONFIGDIR=/tmp/geogs-matplotlib
  --mount "type=bind,src=$diag_task,dst=/task,readonly" --mount "type=bind,src=$diag_out,dst=/out"
  --mount "type=bind,src=$diag_out/config.json,dst=/config.json,readonly"
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e python /out/code/p2_visual_f1_diagnostic.py)
printf '%q ' "${diag_command[@]}" > "$diag_out/command.sh"
printf '\n' >> "$diag_out/command.sh"
"${diag_command[@]}" > "$diag_out/stdout.log" 2> "$diag_out/stderr.log"
cat "$diag_out/stdout.log"

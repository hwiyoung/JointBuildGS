#!/usr/bin/env bash
set -euo pipefail
test "$#" -eq 0
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$(realpath "$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test "$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')" = "$image"
mkdir -p "$task_root/runtime/factor_contrast_validation_v1"
attempt="$(mktemp -d "$task_root/runtime/factor_contrast_validation_v1/attempt.XXXXXX")"
source_root="$attempt/source"
mkdir -p "$source_root/scripts/phd/geogs_p1p2p3_v1/runtime" "$source_root/tests/phd/geogs_p1p2p3_v1" "$source_root/configs/phd/geogs_p1p2p3_v1"
scripts="$repo_root/scripts/phd/geogs_p1p2p3_v1"
cp -a -- "$scripts/analysis" "$scripts/evaluation" "$source_root/scripts/phd/geogs_p1p2p3_v1/"
cp -p -- "$scripts/resource_contract.py" "$scripts/repeat_contract.py" "$source_root/scripts/phd/geogs_p1p2p3_v1/"
cp -p -- "$scripts/runtime/finalization_control.py" "$source_root/scripts/phd/geogs_p1p2p3_v1/runtime/"
cp -p -- "$repo_root/tests/phd/geogs_p1p2p3_v1/test_factor_contrasts.py" "$source_root/tests/phd/geogs_p1p2p3_v1/"
for name in experiment_v1.json evaluation_analysis_v1.json runtime_layout_allocator_v2.json supplemental_repeat_v1.json extraction_resource_v3.json; do
  cp -p -- "$repo_root/configs/phd/geogs_p1p2p3_v1/$name" "$source_root/configs/phd/geogs_p1p2p3_v1/$name"
done
printf '%s\n' "$image" > "$attempt/image_id.txt"
printf '%s\n' "$attempt"
trap 'code=$?; printf "%s\n" "$code" > "$attempt/exit_code.txt"' EXIT
command=(docker run --rm --network none --read-only --cpus 2 --memory 2g --tmpfs /tmp:rw,size=512m
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 --env MPLCONFIGDIR=/tmp/matplotlib
  --env OPENBLAS_NUM_THREADS=1 --env OMP_NUM_THREADS=1 --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
  --env "EXECUTION_IMAGE_ID=$image"
  --mount "type=bind,src=$source_root,dst=/repo,readonly"
  --mount "type=bind,src=$attempt,dst=/out" --workdir /repo
  "$image" python scripts/phd/geogs_p1p2p3_v1/analysis/validate_factor_contrasts.py)
printf '%q ' "${command[@]}" > "$attempt/command.sh"
printf '\n' >> "$attempt/command.sh"
"${command[@]}" > "$attempt/stdout.log" 2> "$attempt/stderr.log"
cat "$attempt/stdout.log"

#!/usr/bin/env bash
set -euo pipefail
test "$#" -eq 0
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$(realpath "$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test "$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')" = "$image"
mkdir -p "$task_root/runtime/control_trajectory_validation_v1"
attempt="$(mktemp -d "$task_root/runtime/control_trajectory_validation_v1/attempt.XXXXXX")"
source_root="$attempt/source"
mkdir -p "$source_root/scripts/phd/geogs_p1p2p3_v1/analysis" "$source_root/scripts/phd/geogs_p1p2p3_v1/runtime" "$source_root/scripts/phd/geogs_p1p2p3_v1/evaluation" "$source_root/tests/phd/geogs_p1p2p3_v1" "$source_root/configs/phd/geogs_p1p2p3_v1"
scripts="$repo_root/scripts/phd/geogs_p1p2p3_v1"
for name in control_trajectories.py run_control_trajectories.sh validate_control_trajectories.py run_control_synthetic_validation.sh; do
  cp -p -- "$scripts/analysis/$name" "$source_root/scripts/phd/geogs_p1p2p3_v1/analysis/$name"
done
for name in resource_contract.py repeat_contract.py jbgs_state.py; do cp -p -- "$scripts/$name" "$source_root/scripts/phd/geogs_p1p2p3_v1/$name"; done
for name in seal_candidates.py runtime_layout.py supplemental_repeat.py resource_support.py; do
  cp -p -- "$scripts/evaluation/$name" "$source_root/scripts/phd/geogs_p1p2p3_v1/evaluation/$name"
done
cp -p -- "$scripts/runtime/finalization_control.py" "$source_root/scripts/phd/geogs_p1p2p3_v1/runtime/"
cp -p -- "$repo_root/tests/phd/geogs_p1p2p3_v1/test_control_trajectories.py" "$source_root/tests/phd/geogs_p1p2p3_v1/"
for name in experiment_v1.json runtime_layout_allocator_v2.json supplemental_repeat_v1.json extraction_resource_v3.json; do
  cp -p -- "$repo_root/configs/phd/geogs_p1p2p3_v1/$name" "$source_root/configs/phd/geogs_p1p2p3_v1/$name"
done
printf '%s\n' "$image" > "$attempt/image_id.txt"
printf '%s\n' "$attempt"
trap 'code=$?; printf "%s\n" "$code" > "$attempt/exit_code.txt"' EXIT
command=(docker run --rm --network none --read-only --cpus 2 --memory 2g --tmpfs /tmp:rw,size=512m
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 --env MPLCONFIGDIR=/tmp/matplotlib
  --env OPENBLAS_NUM_THREADS=1 --env OMP_NUM_THREADS=1 --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
  --env "EXECUTION_IMAGE_ID=$image"
  --mount "type=bind,src=$source_root,dst=/repo,readonly" --mount "type=bind,src=$attempt,dst=/out"
  --workdir /repo "$image" python scripts/phd/geogs_p1p2p3_v1/analysis/validate_control_trajectories.py)
printf '%q ' "${command[@]}" > "$attempt/command.sh"
printf '\n' >> "$attempt/command.sh"
"${command[@]}" > "$attempt/stdout.log" 2> "$attempt/stderr.log"
cat "$attempt/stdout.log"

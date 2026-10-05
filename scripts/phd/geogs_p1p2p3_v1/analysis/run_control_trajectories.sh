#!/usr/bin/env bash
# Separate, post-all21-seal control report; never modifies a live execution.
set -euo pipefail
test "$#" -eq 0
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$(realpath "$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")"
scripts="$repo_root/scripts/phd/geogs_p1p2p3_v1"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test -s "$task_root/contracts/candidates_sealed_v1.json"
test "$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')" = "$image"
mkdir -p "$task_root/evaluation/control_trajectories_v1"
attempt="$(mktemp -d "$task_root/evaluation/control_trajectories_v1/attempt.XXXXXX")"
mkdir "$attempt/code" "$attempt/code/evaluation_code"
cp -p -- "${BASH_SOURCE[0]}" "$attempt/launcher_snapshot.sh"
cp -p -- "$scripts/analysis/control_trajectories.py" "$scripts/runtime/finalization_control.py" "$attempt/code/"
cp -p -- "$scripts/jbgs_state.py" "$attempt/code/trace_instrumentation_source.py"
for name in resource_contract.py repeat_contract.py; do cp -p -- "$scripts/$name" "$attempt/code/$name"; done
for name in seal_candidates.py runtime_layout.py supplemental_repeat.py resource_support.py; do
  cp -p -- "$scripts/evaluation/$name" "$attempt/code/evaluation_code/$name"
done
git_head="$(git -C "$repo_root" rev-parse HEAD)"
printf '%s\n' "$image" > "$attempt/image_id.txt"
printf '%s\n' "$git_head" > "$attempt/git_head.txt"
printf '%s\n' "$attempt"
trap 'code=$?; printf "%s\n" "$code" > "$attempt/exit_code.txt"' EXIT
base=(docker run --rm --network none --read-only --cpus 2 --memory 2g --tmpfs /tmp:rw,size=512m
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 --env MPLCONFIGDIR=/tmp/matplotlib
  --env OPENBLAS_NUM_THREADS=1 --env OMP_NUM_THREADS=1 --env PYTHONPATH=/code/evaluation_code:/code
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 --env "EXECUTION_IMAGE_ID=$image" --env "EXECUTION_GIT_HEAD=$git_head"
  --mount "type=bind,src=$task_root/contracts,dst=/task/contracts,readonly"
  --mount "type=bind,src=$attempt/code,dst=/code,readonly" --mount "type=bind,src=$attempt,dst=/out")
gate=("${base[@]}" "$image" python /code/control_trajectories.py --mode inventory)
printf '%q ' "${gate[@]}" > "$attempt/commands.sh"
printf '\n' >> "$attempt/commands.sh"
"${gate[@]}" > "$attempt/gate_stdout.log" 2> "$attempt/gate_stderr.log"
# Only exact trace/train-receipt filenames can be added after the contracts-only gate.
payload=("${base[@]}")
while IFS= read -r relative; do
  [[ "$relative" =~ ^(runs_allocator_v2|native_repeat_allocator_v2)/(P1|P2|P3)/(D005_Pnative|D0005_Pnative|D0_Pnative|D005_Prelease|D0005_Prelease|D0_Prelease)/(model/jbgs_trace\.jsonl|train_receipt\.json)$ ]]
  payload+=(--mount "type=bind,src=$task_root/$relative,dst=/task/$relative,readonly")
done < "$attempt/mount_relative_paths.txt"
command=("${payload[@]}" "$image" python /code/control_trajectories.py --mode extract)
printf '%q ' "${command[@]}" >> "$attempt/commands.sh"
printf '\n' >> "$attempt/commands.sh"
"${command[@]}" > "$attempt/stdout.log" 2> "$attempt/stderr.log"
cat "$attempt/stdout.log"

#!/usr/bin/env bash
# Additional post-summary derivation; never part of a live training launcher.
set -euo pipefail
test "$#" -eq 0
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$(realpath "$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")"
scripts="$repo_root/scripts/phd/geogs_p1p2p3_v1"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
# Refuse early invocation before creating even an attempt directory.
test -s "$task_root/contracts/candidates_sealed_v1.json"
test -s "$task_root/evaluation/summary/receipt.json"
test "$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')" = "$image"
mkdir -p "$task_root/evaluation/factor_contrasts_v1"
attempt="$(mktemp -d "$task_root/evaluation/factor_contrasts_v1/attempt.XXXXXX")"
mkdir "$attempt/code" "$attempt/code/evaluation_code"
cp -p -- "${BASH_SOURCE[0]}" "$attempt/launcher_snapshot.sh"
cp -p -- "$scripts/analysis/factor_contrasts.py" "$scripts/runtime/finalization_control.py" "$attempt/code/"
for name in resource_contract.py repeat_contract.py; do cp -p -- "$scripts/$name" "$attempt/code/$name"; done
for name in seal_candidates.py runtime_layout.py supplemental_repeat.py resource_support.py; do
  cp -p -- "$scripts/evaluation/$name" "$attempt/code/evaluation_code/$name"
done
git_head="$(git -C "$repo_root" rev-parse HEAD)"
printf '%s\n' "$image" > "$attempt/image_id.txt"
printf '%s\n' "$git_head" > "$attempt/git_head.txt"
printf '%s\n' "$attempt"
trap 'code=$?; printf "%s\n" "$code" > "$attempt/exit_code.txt"' EXIT
command=(docker run --rm --network none --read-only --cpus 2 --memory 2g
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1
  --env PYTHONPATH=/code/evaluation_code:/code --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
  --env "EXECUTION_IMAGE_ID=$image" --env "EXECUTION_GIT_HEAD=$git_head"
  --mount "type=bind,src=$task_root/contracts,dst=/task/contracts,readonly"
  --mount "type=bind,src=$task_root/evaluation/summary,dst=/task/evaluation/summary,readonly"
  --mount "type=bind,src=$attempt/code,dst=/code,readonly"
  --mount "type=bind,src=$attempt,dst=/out"
  "$image" python /code/factor_contrasts.py --task /task --output /out/results)
printf '%q ' "${command[@]}" > "$attempt/command.sh"
printf '\n' >> "$attempt/command.sh"
"${command[@]}" > "$attempt/stdout.log" 2> "$attempt/stderr.log"
cat "$attempt/stdout.log"

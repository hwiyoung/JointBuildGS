#!/usr/bin/env bash
# Additive final preservation audit, only after the actual complete candidate seal.
set -euo pipefail
test "$#" -eq 0
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$(realpath "$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")"
scripts="$repo_root/scripts/phd/geogs_p1p2p3_v1"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test -s "$task_root/contracts/candidates_sealed_v1.json"
test "$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')" = "$image"
exec 9>"$task_root/preservation/final_preservation.lock"
flock -n 9
mkdir -p "$task_root/preservation/final_v1"
attempt="$(mktemp -d "$task_root/preservation/final_v1/attempt.XXXXXX")"
mkdir "$attempt/code" "$attempt/code/evaluation_code"
cp -p -- "${BASH_SOURCE[0]}" "$attempt/launcher_snapshot.sh"
for name in verify_final.py verify_service_snapshot.py verify_interim.py reconcile_interim.py; do
  cp -p -- "$scripts/preservation/$name" "$attempt/code/$name"
done
cp -p -- "$scripts/runtime/finalization_control.py" "$attempt/code/finalization_control.py"
for name in resource_contract.py repeat_contract.py; do cp -p -- "$scripts/$name" "$attempt/code/$name"; done
for name in seal_candidates.py runtime_layout.py supplemental_repeat.py resource_support.py; do
  cp -p -- "$scripts/evaluation/$name" "$attempt/code/evaluation_code/$name"
done
printf '%s\n' "$image" > "$attempt/image_id.txt"
printf '%s\n' "$attempt"
trap 'code=$?; printf "%s\n" "$code" > "$attempt/exit_code.txt"' EXIT
command=(docker run --rm --network none --read-only --cpus 2 --memory 4g
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 --env GIT_OPTIONAL_LOCKS=0
  --env PYTHONPATH=/code/evaluation_code:/code --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
  --mount "type=bind,src=$task_root,dst=/task,readonly"
  --mount "type=bind,src=$attempt/code,dst=/code,readonly"
  --mount "type=bind,src=$attempt,dst=/out")
gate=("${command[@]}" "$image" python /code/verify_final.py --mode gate)
printf '%q ' "${gate[@]}" > "$attempt/commands.sh"
printf '\n' >> "$attempt/commands.sh"
"${gate[@]}" > "$attempt/gate.log" 2>&1
# Original default-format descriptors are compared; full descriptors stay separate evidence.
services_default=(docker ps -a --format '{{.ID}} {{.Names}} {{.Image}} {{.Status}} {{.Ports}}')
services_full=(docker ps -a --no-trunc --format '{{json .}}')
printf '%q ' "${services_default[@]}" >> "$attempt/commands.sh"
printf '> %q\n' "$attempt/services_current_default.txt" >> "$attempt/commands.sh"
"${services_default[@]}" > "$attempt/services_current_default.txt"
printf '%q ' "${services_full[@]}" >> "$attempt/commands.sh"
printf '> %q\n' "$attempt/services_current_no_trunc.jsonl" >> "$attempt/commands.sh"
"${services_full[@]}" > "$attempt/services_current_no_trunc.jsonl"
final=("${command[@]}" --mount "type=bind,src=$repo_root,dst=/repo,readonly"
  "$image" python /code/verify_final.py --mode final)
printf '%q ' "${final[@]}" >> "$attempt/commands.sh"
printf '\n' >> "$attempt/commands.sh"
"${final[@]}" > "$attempt/verifier.log" 2>&1
cat "$attempt/verifier.log"

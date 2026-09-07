#!/usr/bin/env bash
# Explicit operational archive only: never starts training or retries itself.
set -euo pipefail
test "$#" -eq 1
region="$1"
case "$region" in P1) gpu=0 ;; P2) gpu=1 ;; *) exit 2 ;; esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$(cd "$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1" && pwd)"
source_run="$task_root/native_repeat_allocator_v2/$region/D005_Pnative"
config="$repo_root/configs/phd/geogs_p1p2p3_v1/native_repeat_retry_v1.json"
verifier="$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime/verify_failed_repeat_archive.py"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test -d "$source_run"
test ! -L "$source_run"
test "$(realpath -e -- "$source_run")" = "$source_run"
exec 9>"$task_root/queue_allocator_v2/locks/gpu${gpu}.lock"
flock -n 9
container="jbgs-geogs-${region}-D005_Pnative-train-allocator_v2-native_repeat_1"
containers="$(docker ps -a --filter "name=^/${container}$" --format '{{.ID}} {{.Names}}')"
test -z "$containers"
retry_root="$task_root/runtime/native_repeat_retry_v1/$region"
shopt -s nullglob
for prior in "$retry_root"/attempt.*/preserved_failed_run; do
  test ! -e "$prior" && test ! -L "$prior"
done
mkdir -p "$retry_root"
attempt="$(mktemp -d "$retry_root/attempt.XXXXXX")"
evidence="$attempt/metadata"
archive="$attempt/preserved_failed_run"
mkdir "$evidence"
trap 'status=$?; printf "%s\n" "$status" > "$attempt/overall_exit_code.txt"' EXIT
cp -p -- "$verifier" "$evidence/verify_failed_repeat_archive.py"
cp -p -- "$config" "$evidence/config.json"
cp -p -- "${BASH_SOURCE[0]}" "$evidence/archive_failed_repeat.sh"
printf '%s\n' "$image" > "$evidence/image_id.txt"
git -C "$repo_root" rev-parse HEAD > "$evidence/repository_head.txt"
printf '%s\n' "gpu${gpu}.lock held by this wrapper until exit" > "$evidence/gpu_lock_evidence.txt"
printf '%s' "$containers" > "$evidence/target_containers_before.txt"
date -u +'%Y-%m-%dT%H:%M:%S.%NZ' > "$evidence/started_utc.txt"
test "$(stat -c %d -- "$source_run")" = "$(stat -c %d -- "$attempt")"
printf '%s\n' 'PASS_SAME_FILESYSTEM' > "$evidence/filesystem_precheck.txt"
base=(docker run --rm --read-only --network none --cpus 1 --memory 256m
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 --env JBGS_ARCHIVE_RUNTIME_IMAGE_ID="$image")
preflight=("${base[@]}" --mount "type=bind,src=$source_run,dst=/failed,readonly"
  --mount "type=bind,src=$evidence,dst=/evidence" "$image" python /evidence/verify_failed_repeat_archive.py
  --mode preflight --region "$region" --source-host "$source_run" --archive-host "$archive")
printf '%q ' "${preflight[@]}" > "$evidence/preflight_command.sh"
printf '\n' >> "$evidence/preflight_command.sh"
if "${preflight[@]}" > "$evidence/preflight_stdout.log" 2> "$evidence/preflight_stderr.log"; then status=0; else status=$?; fi
printf '%s\n' "$status" > "$evidence/preflight_exit_code.txt"
test "$status" -eq 0
test -s "$evidence/preflight_receipt.json"
containers="$(docker ps -a --filter "name=^/${container}$" --format '{{.ID}} {{.Names}}')"
printf '%s' "$containers" > "$evidence/target_containers_before_move.txt"
test -z "$containers"
test ! -e "$archive"
test ! -L "$archive"
test "$(stat -c %d -- "$source_run")" = "$(stat -c %d -- "$attempt")"
move=(mv -T -n -- "$source_run" "$archive")
printf '%q ' "${move[@]}" > "$evidence/move_command.sh"
printf '\n' >> "$evidence/move_command.sh"
if "${move[@]}" > "$evidence/move_stdout.log" 2> "$evidence/move_stderr.log"; then status=0; else status=$?; fi
printf '%s\n' "$status" > "$evidence/mv_exit_code.txt"
test "$status" -eq 0
test ! -e "$source_run"
test ! -L "$source_run"
test -d "$archive"
test ! -L "$archive"
printf '%s\n' 'PASS_SOURCE_ABSENT' > "$evidence/source_absence_postcheck.txt"
post=("${base[@]}" --mount "type=bind,src=$archive,dst=/failed,readonly"
  --mount "type=bind,src=$evidence,dst=/evidence" "$image" python /evidence/verify_failed_repeat_archive.py
  --mode post --region "$region" --source-host "$source_run" --archive-host "$archive")
printf '%q ' "${post[@]}" > "$evidence/post_command.sh"
printf '\n' >> "$evidence/post_command.sh"
if "${post[@]}" > "$evidence/post_stdout.log" 2> "$evidence/post_stderr.log"; then status=0; else status=$?; fi
printf '%s\n' "$status" > "$evidence/post_exit_code.txt"
cat "$evidence/preflight_stdout.log" "$evidence/post_stdout.log"
printf 'Failed-repeat archive evidence: %s\n' "$attempt"
exit "$status"

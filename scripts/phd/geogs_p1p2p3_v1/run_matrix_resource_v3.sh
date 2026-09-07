#!/usr/bin/env bash
# Resumes only completed producer-bound phases; original queue evidence survives.
set -euo pipefail
gpu="${1:?GPU0 or1}"
case "$gpu" in 0|1) ;; *) exit 2 ;; esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
queue="$task_root/queue_allocator_v2"
new_queue="$queue/resource_v3"
export JBGS_RUNTIME_REVISION=allocator_v2
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
mkdir -p "$new_queue/claims" "$new_queue/locks" "$new_queue/done" "$new_queue/failed"
exec 9>"$queue/locks/gpu${gpu}.lock"
flock -n 9
check() {
  docker run --rm --network none --cpus 2 --memory 4g --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,src=$task_root,dst=/task,readonly" \
    --mount "type=bind,src=$repo_root/scripts/phd/geogs_p1p2p3_v1,dst=/audit,readonly" \
    --mount "type=bind,src=$attempt,dst=/operational" "$image" \
    python /audit/runtime/resource_phase_integrity.py "$@"
}
conditions=(D005_Pnative D0005_Pnative D0_Pnative D005_Prelease D0005_Prelease D0_Prelease)
while true; do
  test -z "$(find "$new_queue/failed" -type f -print -quit)"
  if [[ "$(find "$new_queue/done" -maxdepth 1 -type f | wc -l)" -eq 18 ]]; then exit 0; fi
  found=0
  for region in P1 P2 P3; do
    for condition in "${conditions[@]}"; do
      job="${region}_${condition}"
      [[ -e "$new_queue/done/$job" ]] && continue
      [[ -n "$(docker ps --filter "name=jbgs-geogs-${region}-${condition}-" --format '{{.Names}}')" ]] && continue
      if [[ "$condition" != D005_Pnative ]]; then
        [[ -s "$task_root/runs_allocator_v2/$region/D005_Pnative/model/jbgs_complete/iteration_8100/receipt.json" ]] || continue
      elif [[ "$region" == P2 ]]; then
        [[ -s "$task_root/runs_allocator_v2/P1/D005_Pnative/train_receipt.json" ]] || continue
      elif [[ "$region" == P3 ]]; then
        [[ -s "$task_root/runs_allocator_v2/P2/D005_Pnative/train_receipt.json" ]] || continue
      fi
      exec 6>"$new_queue/locks/$job.lock"
      if ! flock -n 6; then exec 6>&-; continue; fi
      if [[ -e "$new_queue/done/$job" ]]; then exec 6>&-; continue; fi
      mkdir -p "$queue/claims/$job" "$new_queue/claims/$job"
      attempt="$(mktemp -d "$new_queue/claims/$job/attempt.XXXXXX")"
      cp -p -- "${BASH_SOURCE[0]}" "$attempt/worker_snapshot.sh"
      if [[ -f "$queue/failed/$job" ]]; then cp -p -- "$queue/failed/$job" "$attempt/original_failed_marker"; fi
      if [[ -f "$queue/claims/$job/run.log" ]]; then cp -p -- "$queue/claims/$job/run.log" "$attempt/original_claim_run.log"; fi
      found=1
      printf '%s\n' "GPU$gpu resumes $job; evidence=$attempt"
      set +e
      (
        set -e
        for phase in train render metrics auxiliary; do
          action="$(check --mode phase --region "$region" --condition "$condition" --phase "$phase")"
          if [[ "$action" == SKIP ]]; then continue; fi
          test "$action" = RUN
          if [[ "$phase" == train ]]; then
            while [[ "$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)" -lt 25165824 ]]; do sleep 5; done
            if [[ "$condition" != D005_Pnative || "$region" == P1 ]]; then
              bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/ensure_regional_anchor.sh" "$region" "$gpu"
            fi
          elif [[ "$phase" == render ]]; then
            while [[ "$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)" -lt 41943040 ]]; do sleep 5; done
          fi
          if [[ "$phase" == auxiliary ]]; then
            bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_auxiliary_resource_v3.sh" "$region" "$condition" "$gpu"
          else
            bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_regional_phase.sh" "$region" "$condition" "$phase" "$gpu"
          fi
        done
        check --mode job_complete --region "$region" --condition "$condition" --output /operational/complete.json
      ) > "$attempt/run.log" 2>&1
      code=$?
      set -e
      printf '%s\n' "$code" > "$attempt/exit_code.txt"
      if [[ "$code" -ne 0 ]]; then
        (set -o noclobber; printf '%s\n' "$attempt" > "$new_queue/failed/$job")
        tail -n 12 "$attempt/run.log"
        exit "$code"
      fi
      if [[ -f "$queue/failed/$job" ]]; then
        cmp -s "$queue/failed/$job" "$attempt/original_failed_marker"
        mv -n -- "$queue/failed/$job" "$attempt/archived_failed_marker"
        test ! -e "$queue/failed/$job"
      fi
      (set -o noclobber; printf '%s\n' "$attempt/complete.json" > "$new_queue/done/$job")
      if [[ ! -e "$queue/done/$job" ]]; then (set -o noclobber; printf '%s\n' "$attempt/complete.json" > "$queue/done/$job"); fi
      exec 6>&-
      printf '%s\n' "GPU$gpu completed $job under resource_v3"
      break 2
    done
  done
  if [[ "$found" -eq 0 ]]; then sleep 5; fi
done

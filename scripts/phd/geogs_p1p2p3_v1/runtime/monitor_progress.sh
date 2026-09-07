#!/usr/bin/env bash
# Read-only operational status; no UAS or regional quality values are opened.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
docker ps --filter name=jbgs-geogs-P --filter name=jbgs-geogs-finalize- --format '{{.Names}} {{.Status}}'
for run_dir in "$task_root"/runs_allocator_v2/*/* "$task_root"/native_repeat_allocator_v2/*/D005_Pnative; do
  [[ -d "$run_dir" ]] || continue
  if [[ -f "$run_dir/train_invocation.json" && ! -f "$run_dir/train_receipt.json" && -f "$run_dir/model/jbgs_trace.jsonl" ]]; then
    printf '%s ' "${run_dir#"$task_root/"}"
    tail -n 1 "$run_dir/model/jbgs_trace.jsonl" | sed -nE 's/.*"iteration": ([0-9]+).*"gaussians": ([0-9]+).*"protected": ([0-9]+).*/iteration=\1 gaussians=\2 protected=\3/p'
  fi
  for phase in render auxiliary; do
    if [[ -f "$run_dir/${phase}.log" && ! -f "$run_dir/${phase}_receipt.json" ]]; then
      printf '%s %s ' "${run_dir#"$task_root/"}" "$phase"
      tail -c 350 "$run_dir/${phase}.log" | tr '\r' '\n' | tail -n 2
      printf '\n'
    fi
  done
done
for variant in "$task_root"/runs_allocator_v2/*/*/auxiliary/* "$task_root"/native_repeat_allocator_v2/*/D005_Pnative/auxiliary/* "$task_root"/extraction_resource_v3/*/*/*/auxiliary/*; do
  if [[ -f "$variant/render.log" && ! -f "$variant/receipt.json" ]]; then
    printf '%s ' "${variant#"$task_root/"}"
    tail -c 250 "$variant/render.log" | tr '\r' '\n' | tail -n 1
    printf '\n'
  fi
done
printf 'primary jobs completed: '
find "$task_root/queue_allocator_v2/done" -maxdepth 1 -type f | wc -l
if [[ -d "$task_root/queue_allocator_v2/resource_v3/done" ]]; then
  printf 'resource_v3 completed: '
  find "$task_root/queue_allocator_v2/resource_v3/done" -maxdepth 1 -type f | wc -l
  find "$task_root/queue_allocator_v2/resource_v3/failed" -maxdepth 1 -type f -print
fi
for control_log in "$task_root"/runtime/resource_v3_continuation/*/orchestrator.log; do
  if [[ -f "$control_log" ]]; then
    if [[ -f "${control_log%/*}/exit_code.txt" ]]; then
      printf 'Original controller exited: '
      cat "${control_log%/*}/exit_code.txt"
      continue
    fi
    control_line="$(tail -n 1 "$control_log")"
    if [[ "$control_line" != Waiting\ for\ current\ training* ]]; then printf '%s\n' "$control_line"; fi
  fi
done
for region in P1 P2 P3; do
  repeat_root="$task_root/native_repeat_allocator_v2/$region/D005_Pnative"
  printf 'supplemental %s: ' "$region"
  if [[ -f "$repeat_root/train_receipt.json" ]]; then
    sed -n '/"status":/p' "$repeat_root/train_receipt.json" | head -n 1
  elif [[ ! -e "$repeat_root" ]]; then
    printf 'NOT_ATTEMPTED\n'
  else
    printf 'STARTED_WITHOUT_CLOSED_TRAIN_RECEIPT\n'
  fi
done
for final_log in "$task_root"/runtime/finalization_primary18_v2/*/orchestrator.log; do
  [[ -f "$final_log" ]] || continue
  printf 'Primary18 evaluation: '
  tail -n 1 "$final_log"
done
for gate in "$task_root"/parity_allocator_v2/P*/anchor_gate.json; do
  [[ -f "$gate" ]] || continue
  printf '%s ' "${gate#"$task_root/"}"
  sed -n '/"status":/p' "$gate" | head -n 1
done

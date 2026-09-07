#!/usr/bin/env bash
# Task-local paths; Python drivers bind and validate the corresponding contract.
runtime_revision="${JBGS_RUNTIME_REVISION:-v1}"
runtime_env=()
runtime_mounts=()
case "$runtime_revision" in
  v1)
    runs_root="$task_root/runs"
    parity_root="$task_root/parity"
    queue_root="$task_root/queue"
    ;;
  allocator_v2)
    runs_root="$task_root/runs_allocator_v2"
    parity_root="$task_root/parity_allocator_v2"
    queue_root="$task_root/queue_allocator_v2"
    runtime_layout="$task_root/contracts/runtime_layout_allocator_v2.json"
    test -s "$runtime_layout"
    runtime_env=(--env PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128 --env JBGS_RUNTIME_REVISION=allocator_v2)
    runtime_mounts=(--mount "type=bind,src=$runtime_layout,dst=/runtime_layout.json,readonly")
    ;;
  *) printf '%s\n' "Unknown runtime revision: $runtime_revision" >&2; exit 2 ;;
esac
if [[ -n "${region:-}" ]]; then
  baseline_root="$runs_root/$region/D005_Pnative"
  if [[ "$runtime_revision" == allocator_v2 && "$region" == P1 ]]; then
    baseline_root="$task_root/runs/P1/D005_Pnative"
  fi
  anchor_root="$baseline_root/model/jbgs_complete/iteration_8000"
fi

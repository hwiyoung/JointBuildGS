#!/usr/bin/env bash
set -euo pipefail
geogs_gv_region="${1:?P1 P2 P3}"
geogs_gv_policy="${2:?task-relative frozen finite retry policy}"
geogs_gv_policy_sha="${3:?exact frozen policy SHA256}"
geogs_gv_resource_failure="${4:-}"
geogs_gv_retry="${5:-}"
case "$geogs_gv_region" in
  P1) geogs_gv_predecessor=no_anchor_sfm_memory_recovery_v2 ;;
  P2) geogs_gv_predecessor=no_anchor_sfm_memory_recovery_P2_v2 ;;
  P3) geogs_gv_predecessor=no_anchor_sfm_memory_recovery_P3_v3 ;;
  *) exit 2 ;;
esac
geogs_gv_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_gv_task=$(realpath "$geogs_gv_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_gv_attempt="no_anchor_sfm_gradient_memory_v3_$geogs_gv_region"
geogs_gv_parent="$geogs_gv_task/no_anchor_sfm_v1"
geogs_gv_out="$geogs_gv_task/$geogs_gv_attempt"
geogs_gv_code="$geogs_gv_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1"
geogs_gv_image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
if [[ -e "$geogs_gv_out" ]]; then
  test "$geogs_gv_retry" = retry_preflight_v1
  test "$geogs_gv_region" = P2
  test ! -e "$geogs_gv_out/failed_preflight_v1"
  for geogs_gv_existing in "$geogs_gv_out"/*; do
    case "${geogs_gv_existing##*/}" in preparation_runtime|inputs) ;; *) exit 2 ;; esac
  done
  test -f "$geogs_gv_out/preparation_runtime/exit_code.txt"
  test "$(cat "$geogs_gv_out/preparation_runtime/exit_code.txt")" = 1
  rg -q 'Unexpected cgroup evidence role or duplicate' "$geogs_gv_out/preparation_runtime/preflight_stderr.log"
  if compgen -G "$geogs_gv_out/inputs/*" > /dev/null; then exit 2; fi
  mv -- "$geogs_gv_out/preparation_runtime" "$geogs_gv_out/failed_preflight_v1"
elif [[ -n "$geogs_gv_retry" ]]; then
  exit 2
fi
test -f "$geogs_gv_task/$geogs_gv_predecessor/runs/$geogs_gv_region/SFM_noanchor_D005_Pnative/receipt.json"
test -f "$geogs_gv_code/memory_recovery_v3/verify_runtime.py"
mkdir -p -- "$geogs_gv_out/preparation_runtime/memory_recovery_v1" "$geogs_gv_out/preparation_runtime/memory_recovery_v2" "$geogs_gv_out/preparation_runtime/memory_recovery_v3" "$geogs_gv_out/inputs"
cp -- "${BASH_SOURCE[0]}" "$geogs_gv_code/seal_memory_attempt.py" "$geogs_gv_out/preparation_runtime/"
trap 'geogs_gv_exit=$?; printf "%s\n" "$geogs_gv_exit" > "$geogs_gv_out/preparation_runtime/exit_code.txt"' EXIT
docker run --rm --network none --read-only --cpus 2 --memory 2g --memory-swap 2g \
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 --env NVIDIA_VISIBLE_DEVICES=void --env CUDA_VISIBLE_DEVICES= \
  --mount "type=bind,src=$geogs_gv_task,dst=/task,readonly" \
  --mount "type=bind,src=$geogs_gv_out/preparation_runtime,dst=/audit" \
  "$geogs_gv_image" python -c 'import sys,json; from pathlib import Path; sys.path.insert(0,"/audit"); from seal_memory_attempt import final_retry_evidence,sha; previous=Path("/task")/sys.argv[5]/"failed_preflight_v1"; preserved={str(p.relative_to(previous)):sha(p) for p in previous.rglob("*") if p.is_file()} if sys.argv[7] else {}; payload=dict(schema="GEOGS_PREPARATION_PREFLIGHT_RETRY_v1",scientific_verdict=None,region=sys.argv[4],training_attempts_started=0,source_created_before_retry=False,preserved_failure_path=str(previous.relative_to("/task")),preserved_file_sha256=preserved,cause="RESOURCE_EVIDENCE_LIST_ROLE_HANDLING",retry=bool(sys.argv[7])); out=Path("/audit/preparation_retry.json"); out.open("x").write(json.dumps(payload,indent=2)+"\n") if sys.argv[7] else None; final_retry_evidence(Path("/task"),sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],sys.argv[5],sha(Path("/task/no_anchor_sfm_v1/config.json")),sys.argv[6] or None); print("PASS_FIXED_PREDECESSOR_AND_FINITE_POLICY")' \
  "$geogs_gv_predecessor" "$geogs_gv_policy" "$geogs_gv_policy_sha" "$geogs_gv_region" "$geogs_gv_attempt" "$geogs_gv_resource_failure" "$geogs_gv_retry" \
  > "$geogs_gv_out/preparation_runtime/preflight_stdout.log" 2> "$geogs_gv_out/preparation_runtime/preflight_stderr.log"
cp -- "$geogs_gv_parent/config.json" "$geogs_gv_out/config.json"
cp -a -- "$geogs_gv_parent/inputs/$geogs_gv_region" "$geogs_gv_out/inputs/$geogs_gv_region"
cp -- "$geogs_gv_code/memory_recovery_v1/prepare_runtime.py" "$geogs_gv_code/memory_recovery_v1/memory_adapter.py" "$geogs_gv_out/preparation_runtime/memory_recovery_v1/"
cp -- "$geogs_gv_code/memory_recovery_v2/prepare_runtime.py" "$geogs_gv_code/memory_recovery_v2/runtime_adapter.py" "$geogs_gv_code/memory_recovery_v2/pinned_storage.py" "$geogs_gv_out/preparation_runtime/memory_recovery_v2/"
cp -- "$geogs_gv_code/memory_recovery_v3/prepare_runtime.py" "$geogs_gv_code/memory_recovery_v3/runtime_adapter.py" "$geogs_gv_code/memory_recovery_v3/stream_ply.py" "$geogs_gv_code/memory_recovery_v3/verify_runtime.py" "$geogs_gv_out/preparation_runtime/memory_recovery_v3/"
docker run --rm --network none --read-only --cpus 2 --memory 2g --memory-swap 2g \
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 --env NVIDIA_VISIBLE_DEVICES=void --env CUDA_VISIBLE_DEVICES= \
  --mount "type=bind,src=$geogs_gv_parent/source,dst=/original,readonly" \
  --mount "type=bind,src=$geogs_gv_out,dst=/out" \
  "$geogs_gv_image" python /out/preparation_runtime/memory_recovery_v3/prepare_runtime.py \
  --source /original --destination /out/source --v1-directory /out/preparation_runtime/memory_recovery_v1 \
  --v2-directory /out/preparation_runtime/memory_recovery_v2 \
  > "$geogs_gv_out/preparation_runtime/stdout.log" 2> "$geogs_gv_out/preparation_runtime/stderr.log"
cat "$geogs_gv_out/preparation_runtime/stdout.log"

#!/usr/bin/env bash
# Sequential native GPU extraction, then explicit-reference CPU evaluation.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact="$(realpath "$repo/../JointBuildGS-artifacts")"
base="$artifact/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
task="$artifact/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
reference="$artifact/phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4/run"
source_path="$task/sources/GeoGS-mvs-pgsr-v1"
config="$task/inputs_v2/experiment.json"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
gpu=1
mode=run
run_index=""
frozen=""
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --preflight) mode=preflight; shift ;;
    --run-index) run_index="${2:?}"; shift 2 ;;
    --frozen-plan) frozen="${2:?}"; shift 2 ;;
    --gpu) gpu="${2:?}"; shift 2 ;;
    *) printf '%s\n' "Unknown finalizer argument: $1" >&2; exit 2 ;;
  esac
done
case "$gpu" in 0|1) ;; *) exit 2 ;; esac
test "$(docker image inspect "$image" --format '{{.Id}}')" = "$image"
cmp -s "$repo/configs/phd/geogs_mvs_pgsr_v1/experiment_v2.json" "$config"
common=(docker run --rm --network none --cpus 8 --memory 32g --shm-size 4g
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
  --env PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128)
ref_mounts=()
for region in P1 P2 P3; do
  test -s "$reference/$region/reference.npz"
  ref_mounts+=(--mount "type=bind,src=$reference/$region/reference.npz,dst=/reference/$region/reference.npz,readonly")
done
if [[ "$mode" == preflight ]]; then
  test -z "$run_index"
  test -z "$frozen"
  mkdir -p "$task/evaluation/static_preflight"
  frozen="$(mktemp -d "$task/evaluation/static_preflight/attempt.XXXXXXXX")"
  cp -a -- "$repo/scripts/phd/geogs_p1p2p3_v1" "$frozen/legacy"
  cp -p -- "$repo/scripts/phd/geogs_mvs_pgsr_v1/finalize.py" "$frozen/finalize.py"
  cp -p -- "${BASH_SOURCE[0]}" "$frozen/finalize.sh"
  git -C "$repo" rev-parse HEAD > "$frozen/repository_head.txt"
  "${common[@]}" --name "jbgs-mvs-pgsr-finalizer-preflight-$(basename "$frozen")" \
    --mount "type=bind,src=$frozen,dst=/frozen" \
    --mount "type=bind,src=$frozen/legacy,dst=/legacy,readonly" \
    --mount "type=bind,src=$base,dst=/base,readonly" \
    --mount "type=bind,src=$source_path,dst=/source,readonly" \
    --mount "type=bind,src=$config,dst=/experiment.json,readonly" \
    --mount "type=bind,src=$base/runtime/weights,dst=/weights,readonly" \
    "${ref_mounts[@]}" "$image" python /frozen/finalize.py --stage static
  printf '%s\n' "$frozen"
  exit 0
fi
test -n "$run_index"
test -n "$frozen"
run_index="$(realpath "$run_index")"
frozen="$(realpath "$frozen")"
test -s "$run_index"
test -s "$frozen/static.json"
cmp -s "$repo/scripts/phd/geogs_mvs_pgsr_v1/finalize.py" "$frozen/finalize.py"
cmp -s "${BASH_SOURCE[0]}" "$frozen/finalize.sh"
mkdir -p "$task/evaluation"
exec 8>"$task/evaluation/finalization.lock"
flock -n 8
test ! -e "$task/evaluation/finalization_receipt_v1.json"
test -z "$(docker ps --format '{{.Names}}' --filter name=jbgs-mvs-pgsr-P)"
attempt="$(mktemp -d "$task/evaluation/attempt.XXXXXXXX")"
printf '%s\n' "$attempt"
cp -p -- "$frozen/finalize.py" "$attempt/finalize_snapshot.py"
cp -p -- "$frozen/finalize.sh" "$attempt/finalize_snapshot.sh"
stage=plan
failure_trap() {
  local code=$?
  if [[ "$code" -ne 0 ]]; then
    "${common[@]}" --mount "type=bind,src=$attempt,dst=/evaluation" \
      "$image" python /evaluation/finalize_snapshot.py --stage failure \
      --failure-stage "$stage" --exit-code "$code" || true
  fi
}
trap failure_trap EXIT
"${common[@]}" --name "jbgs-mvs-pgsr-finalizer-plan-$(basename "$attempt")" \
  --mount "type=bind,src=$attempt,dst=/evaluation" \
  --mount "type=bind,src=$frozen,dst=/frozen,readonly" \
  --mount "type=bind,src=$frozen/legacy,dst=/legacy,readonly" \
  --mount "type=bind,src=$run_index,dst=/run_index.json,readonly" \
  --mount "type=bind,src=$base,dst=/base,readonly" \
  --mount "type=bind,src=$task,dst=/task,readonly" \
  --mount "type=bind,src=$source_path,dst=/source,readonly" \
  --mount "type=bind,src=$config,dst=/experiment.json,readonly" \
  "$image" python /evaluation/finalize_snapshot.py --stage plan --run-index /run_index.json --host-task "$task" \
  > "$attempt/plan.log" 2>&1
while IFS=$'\t' read -r region identifier; do
  stage="extract-$identifier"
  printf '%s\n' "$stage"
  "${common[@]}" --name "jbgs-mvs-pgsr-extract-${identifier//./-}-$(basename "$attempt")" \
    --gpus "device=$gpu" \
    --mount "type=bind,src=$attempt/finalize_snapshot.py,dst=/finalize.py,readonly" \
    --mount "type=bind,src=$frozen/legacy,dst=/legacy,readonly" \
    --mount "type=bind,src=$source_path,dst=/source,readonly" \
    --mount "type=bind,src=$base/inputs/$region,dst=/input,readonly" \
    --mount "type=bind,src=$attempt/extractions/$identifier,dst=/output" \
    "$image" python /finalize.py --stage extract > "$attempt/$stage.log" 2>&1
done < "$attempt/extractions.tsv"
for region in P1 P2 P3; do
  stage="evaluate-$region"
  printf '%s\n' "$stage"
  "${common[@]}" --name "jbgs-mvs-pgsr-evaluate-$region-$(basename "$attempt")" \
    --mount "type=bind,src=$attempt,dst=/evaluation" \
    --mount "type=bind,src=$frozen/legacy,dst=/legacy,readonly" \
    --mount "type=bind,src=$base,dst=/base,readonly" \
    --mount "type=bind,src=$source_path,dst=/source,readonly" \
    --mount "type=bind,src=$base/runtime/weights,dst=/weights,readonly" \
    --mount "type=bind,src=$reference/$region/reference.npz,dst=/reference/$region/reference.npz,readonly" \
    "$image" python /evaluation/finalize_snapshot.py --stage evaluate --region "$region" \
    > "$attempt/$stage.log" 2>&1
done
stage=report
"${common[@]}" --name "jbgs-mvs-pgsr-finalizer-report-$(basename "$attempt")" \
  --env JBGS_FINAL_HOST_ATTEMPT="$attempt" \
  --mount "type=bind,src=$attempt,dst=/evaluation" \
  --mount "type=bind,src=$task/evaluation,dst=/resolver" \
  --mount "type=bind,src=$task,dst=/task,readonly" \
  --mount "type=bind,src=$base,dst=/base,readonly" \
  "$image" python /evaluation/finalize_snapshot.py --stage report > "$attempt/report.log" 2>&1
printf '%s\n' "Finalization complete: $attempt/REPORT.md"

#!/usr/bin/env bash
# CPU-only additive evaluation. Frozen model/reference inputs are read-only.
set -euo pipefail
stage="${1:-evaluate}"
if (( $# )); then shift; fi
case "$stage" in evaluate|baseline-preflight|appearance-preflight|figures) ;; *) echo 'Expected evaluate, baseline-preflight, appearance-preflight, or figures' >&2; exit 2 ;; esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="$repo_root/../JointBuildGS-artifacts"
task_root="$artifact_root/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1"
parent_root="$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
reference_root="$artifact_root/phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4/run"
image='jointbuildgs:geogs-official-db40c95-compat-v1'
expected_image='sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
actual_image="$(docker image inspect --format '{{.Id}}' "$image")"
[[ "$actual_image" == "$expected_image" ]] || { echo 'Frozen evaluation image differs' >&2; exit 1; }
launcher_sha="$(sha256sum "${BASH_SOURCE[0]}" | cut -d ' ' -f 1)"
test -s "$task_root/contracts/main_v2/experiment_v2.json"
output_relative='main_v2/evaluation'
entry='evaluate_v2.py'
arguments=(--task /task/main_v2 --parent /parent --config /task/contracts/main_v2/experiment_v2.json)
cpus=4
memory=16g
case "$stage" in
  baseline-preflight)
    output_relative='main_v2/evaluation_preflight'
    arguments+=(--baseline-preflight)
    cpus=2
    memory=8g
    ;;
  appearance-preflight)
    output_relative='main_v2/evaluation_preflight'
    entry='evaluation_appearance_preflight_v2.py'
    arguments=(--parent /parent --config /task/contracts/main_v2/experiment_v2.json)
    cpus=2
    memory=4g
    ;;
  figures)
    output_relative='main_v2/figures'
    entry='evaluation_visuals_v2.py'
    if (( $# == 0 )); then echo 'figures requires a completed /task/main_v2/evaluation/attempt_* path' >&2; exit 2; fi
    case "$1" in /task/main_v2/evaluation/attempt_*) ;; *) echo 'Unexpected evaluation input path' >&2; exit 2 ;; esac
    [[ "$1" != *'..'* ]] || exit 2
    arguments+=(--evaluation "$1")
    shift
    ;;
esac
mkdir -p "$task_root/$output_relative"
arguments+=(--output "/task/$output_relative")
mounts=(--mount "type=bind,src=$repo_root,dst=/workspace,readonly"
  --mount "type=bind,src=$task_root,dst=/task,readonly"
  --mount "type=bind,src=$task_root/$output_relative,dst=/task/$output_relative"
  --mount "type=bind,src=$parent_root,dst=/parent,readonly")
if [[ "$stage" == evaluate || "$stage" == baseline-preflight ]]; then
  for region in P1 P2 P3; do
    mounts+=(--mount "type=bind,src=$reference_root/$region/reference.npz,dst=/references/$region/reference.npz,readonly")
  done
fi
# Arguments are passed as distinct array entries. A fresh timestamped evaluation
# attempt is created by the Python driver; existing attempts are never replaced.
exec docker run --rm --network none --read-only --cpus "$cpus" --memory "$memory" --memory-swap "$memory" \
  --tmpfs /tmp:rw,size=1g --user "$(id -u):$(id -g)" \
  -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS="$cpus" -e OPENBLAS_NUM_THREADS="$cpus" \
  -e MPLCONFIGDIR=/tmp/mpl -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 \
  -e JBGS_EVALUATION_IMAGE_ID="$actual_image" -e JBGS_EVALUATION_LAUNCHER_SHA256="$launcher_sha" \
  "${mounts[@]}" -w /workspace "$actual_image" \
  python "/workspace/scripts/phd/local_complementary_refinement_v1/$entry" "${arguments[@]}" "$@"

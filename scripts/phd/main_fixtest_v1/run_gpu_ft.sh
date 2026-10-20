#!/usr/bin/env bash
# PHD-MAIN-FIXTEST-v1 thin runner of one GPU post step (gpu_ft.py post|run <site> <result>) = stage 3's run_gpu3.sh with THIS payload
# read-write at /ph/main_fixtest_v1/PHD-MAIN-FIXTEST-v1, fork r14 as /source (ro; the renderer, unchanged since r12) and the stage-0
# split of the site.   GPU=0 [MEM=72g] bash run_gpu_ft.sh <tag> gpu_ft.py <mode> <site> <result>   scientific_verdict: null.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts"); PH="$ART/phase-payloads/phd"
FT="$PH/main_fixtest_v1/PHD-MAIN-FIXTEST-v1"; S1="$PH/main_stage1_v1/PHD-MAIN-STAGE1-v1"; S0="$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1"
DR="$PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"; W="$PH/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights"
PREP="$PH/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"
GPU=${GPU:-0}
tag=$1; shift; script=$1; shift
site=${2:-}
SPLIT=/s0/fork_inputs/s61/$site/split.json
mkdir -p "$FT/logs"; [ -f "$FT/logs/$tag.log" ] && mv "$FT/logs/$tag.log" "$FT/logs/$tag.$(date +%H%M%S).log"
t0=$SECONDS
docker run --rm --name "jbgs-ftg-${tag,,}" --gpus "device=$GPU" --network none --user "$(id -u):$(id -g)" --cpus 16 --memory "${MEM:-72g}" --shm-size 8g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e TORCH_HOME=/weights/torch \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True -e JBGS_SPLIT_JSON=$SPLIT \
  -v "$PH:/ph:ro" -v "$FT:/ph/main_fixtest_v1/PHD-MAIN-FIXTEST-v1" -v "$S0:/s0:ro" -v "$DR:/dr:ro" -v "$S1:/out:ro" -v "$PREP:/prep:ro" -v "$REPO:/repo:ro" \
  -v "$REPO/src/phd/forks/GeoGS-conf-guided-v1-r14:/source:ro" -v "$W:/weights:ro" \
  -w /source --entrypoint python jointbuildgs:geogs-conf-guided-v1 /repo/scripts/phd/main_fixtest_v1/$script "$@" > "$FT/logs/$tag.log" 2>&1
rc=$?; echo "$(date '+%m-%d %H:%M:%S') $tag rc=$rc $((SECONDS-t0))s" | tee -a "$FT/logs/queue.log"
exit $rc

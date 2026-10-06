#!/usr/bin/env bash
# PHD-MAIN-STAGE0-v1 5.4 (host driver): post step of stage-0 trainings, one at a time (TSDF host memory), in the training image.
#   GPU=0 bash run_post.sh b1_LoD2 b1_ALS
# Each: post_stage0.py <run> -> stage0/<run>/post/ (evaluation renders, TSDF mesh, post.json); log logs/post_<run>.log;
# queue.log line "<time> post_<run> rc=<rc> <s>s".
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/main_stage0_v1/PHD-MAIN-STAGE0-v1"; DR="$ART/phase-payloads/phd/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
GPU=${GPU:-0}
for run in "$@"; do
  t0=$SECONDS
  docker run --rm --name "jbgs-r12-post-${run,,}" --gpus "device=$GPU" --network none --user "$(id -u):$(id -g)" --cpus 16 --shm-size 8g \
    -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e JBGS_SPLIT_JSON=/p/fork_inputs/s61/B173nb_b10/split.json \
    -v "$ART:/artifacts/JointBuildGS:ro" -v "$P:/p" -v "$DR:/dr:ro" -v "$REPO:/repo:ro" -v "$REPO/src/phd/forks/GeoGS-conf-guided-v1-r12:/source:ro" \
    -w /source --entrypoint python jointbuildgs:geogs-conf-guided-v1 /repo/scripts/phd/main_stage0_v1/post_stage0.py "$run" > "$P/logs/post_$run.log" 2>&1
  rc=$?; echo "$(date +%H:%M:%S) post_$run rc=$rc $((SECONDS-t0))s" | tee -a "$P/logs/queue.log"
done

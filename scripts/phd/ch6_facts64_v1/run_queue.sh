#!/usr/bin/env bash
# PHD-CH6-FACTS64-v1 host queue (the PHD-CH6-SUPPORT-v1 run_queue.sh with this task's payload and the CH6 payload read-only):
# run "<script> <args...>" lines from a file with N parallel Docker jobs (CPU, jointbuildgs:dev, no network).
#   bash run_queue.sh <jobs_file> <parallel> <cpus_per_job> <mem_gb_per_job>      WORKDIR=<dir under /repo> (default stage-0 scripts)
# Mounts: /art artifacts (ro), /prep prep-measure payload (ro), /dr discard-rule payload (ro), /s0 stage-0 payload (ro),
#         /s1 stage-1 payload (ro), /s3 stage-3 payload (ro), /out this payload, /repo (ro).
set -uo pipefail
JOBS=$1; NP=${2:-2}; CPUS=${3:-10}; MEM=${4:-14}
MAXP=${JBGS_MAX_PAR:-2}; if [ "$NP" -gt "$MAXP" ]; then NP=$MAXP; fi      # shared host (a training queue runs too): at most two jobs
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/ch6_facts64_v1/PHD-CH6-FACTS64-v1"; C6="$ART/phase-payloads/phd/ch6_support_v1/PHD-CH6-SUPPORT-v1"
PREP="$ART/phase-payloads/phd/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"
DR="$ART/phase-payloads/phd/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
S0="$ART/phase-payloads/phd/main_stage0_v1/PHD-MAIN-STAGE0-v1"
S1="$ART/phase-payloads/phd/main_stage1_v1/PHD-MAIN-STAGE1-v1"
S3="$ART/phase-payloads/phd/main_stage3_v1/PHD-MAIN-STAGE3-v1"
WD=${WORKDIR:-scripts/phd/main_stage0_v1}
mkdir -p "$P/logs"
run_one() {
  line="$1"; tag=$(echo "$line" | tr ' /' '__' | tr -cd '[:alnum:]_.-' | cut -c1-110); t0=$(date +%s)
  docker run --rm --network none --user "$(id -u):$(id -g)" --cpus "$CPUS" --memory "${MEM}g" -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS="$CPUS" \
    -e PYTHONDONTWRITEBYTECODE=1 -v "$ART:/art:ro" -v "$PREP:/prep:ro" -v "$DR:/dr:ro" -v "$S0:/s0:ro" -v "$S1:/s1:ro" -v "$S3:/s3:ro" -v "$C6:/c6:ro" \
    -v "$P:/out" -v "$REPO:/repo:ro" -v /usr/share/fonts/opentype/noto:/fonts:ro -w "/repo/$WD" --entrypoint python jointbuildgs:dev $line > "$P/logs/q_$tag.log" 2>&1
  rc=$?; echo "$(date +%H:%M:%S) $tag rc=$rc $(( $(date +%s)-t0 ))s" | tee -a "$P/logs/queue.log"
}
export -f run_one; export ART P C6 PREP DR S0 S1 S3 REPO CPUS MEM WD
grep -v '^#' "$JOBS" | grep . | xargs -I{} -P "$NP" bash -c 'run_one "$@"' _ {}

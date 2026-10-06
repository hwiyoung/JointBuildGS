#!/usr/bin/env bash
# PHD-MAIN-STAGE0-v1 host queue (the discard task's run_queue.sh with this task's payload; thin: only the paths differ):
# run "<script> <args...>" lines from a file with N parallel Docker jobs (CPU, jointbuildgs:dev, no network).
#   bash run_queue.sh <jobs_file> <parallel> <cpus_per_job> <mem_gb_per_job>
# Mounts: /art artifacts (ro), /prep prep-measure payload (ro), /dr discard-rule payload (ro), /out this payload, /repo (ro).
set -uo pipefail
JOBS=$1; NP=${2:-3}; CPUS=${3:-10}; MEM=${4:-12}
MAXP=${JBGS_MAX_PAR:-3}; if [ "$NP" -gt "$MAXP" ]; then NP=$MAXP; fi      # shared host: at most three jobs
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/main_stage0_v1/PHD-MAIN-STAGE0-v1"
PREP="$ART/phase-payloads/phd/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"
DR="$ART/phase-payloads/phd/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
mkdir -p "$P/logs"
run_one() {
  line="$1"; tag=$(echo "$line" | tr ' /' '__' | tr -cd '[:alnum:]_.-' | cut -c1-90); t0=$(date +%s)
  docker run --rm --network none --user "$(id -u):$(id -g)" --cpus "$CPUS" --memory "${MEM}g" -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS="$CPUS" \
    -e PYTHONDONTWRITEBYTECODE=1 -v "$ART:/art:ro" -v "$PREP:/prep:ro" -v "$DR:/dr:ro" -v "$P:/out" -v "$REPO:/repo:ro" \
    -v /usr/share/fonts/opentype/noto:/fonts:ro -w /repo/scripts/phd/main_stage0_v1 --entrypoint python jointbuildgs:dev $line > "$P/logs/q_$tag.log" 2>&1
  rc=$?; echo "$(date +%H:%M:%S) $tag rc=$rc $(( $(date +%s)-t0 ))s" | tee -a "$P/logs/queue.log"
}
export -f run_one; export ART P PREP DR REPO CPUS MEM
grep -v '^#' "$JOBS" | grep . | xargs -I{} -P "$NP" bash -c 'run_one "$@"' _ {}

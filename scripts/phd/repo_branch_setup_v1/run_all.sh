#!/usr/bin/env bash
# PHD-REPO-BRANCH-SETUP-v1 3.5: checks of the clean checkout exp/main-experiment (host driver; every computation in Docker).
#   bash scripts/phd/repo_branch_setup_v1/run_all.sh [step ...]     steps (default all, in order):
#   tests    unit tests of module v5 and of the first prep measure                                   -> logs/tests.log
#   rebuild  r11 rebuilt by build_fork_r11.py from the r10 sources (read-only); three-way sha256         -> rebuild/
#   forks    dry initialisations of the committed r11: 4 boxes x 2 priors all on, switch box x 2 priors x 7 switches off
#            (run_fork_check.py, one queue per prior and GPU)                                          -> fork_runs/chk/
#   checks   fork_checks.py of the repository on those runs (check 2, switch table)                     -> fork_checks/chk.json
#   compare  runs and fork_checks against the discard-rule originals (fork_runs/s52, fork_checks/s52.json) -> compare/
#   receipt  receipt_task.json
# The discard-rule and prep payloads and the r10 sources are mounted read-only; only this task's payload is written. No training.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
V="$ART/phase-payloads/phd/repo_branch_setup_v1/PHD-REPO-BRANCH-SETUP-v1"
P="$ART/phase-payloads/phd/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
PREP="$ART/phase-payloads/phd/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"
R10="$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1/sources/GeoGS-conf-guided-v1-r10"
S="$REPO/scripts/phd/repo_branch_setup_v1"; DEV=jointbuildgs:dev; FORKIMG=jointbuildgs:geogs-conf-guided-v1
COMMIT=$(git -C "$REPO" rev-parse HEAD)
export PYTHONDONTWRITEBYTECODE=1   # the host orchestration (run_fork_check.py imports run_fork.py) leaves no __pycache__ in the checkout
mkdir -p "$V/logs"

D() { docker run --rm --network none --user "$(id -u):$(id -g)" -e MPLCONFIGDIR=/tmp/mpl -e PYTHONDONTWRITEBYTECODE=1 "$@"; }

step() {
  local name=$1; shift; local t0; t0=$(date +%s)
  echo "$(date +%H:%M:%S) $name start" >> "$V/logs/progress.md"
  "$@" > "$V/logs/$name.log" 2>&1; local rc=$?
  printf '{"step": "%s", "rc": %d, "seconds": %d, "end": "%s"}\n' "$name" "$rc" "$(( $(date +%s) - t0 ))" "$(date +%H:%M:%S)" >> "$V/logs/steps.jsonl"
  echo "$(date +%H:%M:%S) $name rc=$rc $(( $(date +%s) - t0 ))s" | tee -a "$V/logs/progress.md"
  return $rc
}

tests() {
  D -v "$REPO:/repo:ro" -v "$ART:/art:ro" -w /repo --entrypoint python "$DEV" \
    -m unittest -v tests.phd.test_prior_propagation_v5 tests.phd.test_main_prep_measure_v1
}

rebuild() {
  D -v "$R10:/r10:ro" -v "$REPO:/repo:ro" -v "$V:/v" --entrypoint python "$DEV" \
    /repo/scripts/phd/main_prep_discard_rule_v1/build_fork_r11.py --parent /r10 --out /v/rebuild/sources/GeoGS-conf-guided-v1-r11 \
    --provenance /v/rebuild/provenance --repo /repo --repo_commit "$COMMIT" || return 1
  D -v "$P/sources:/orig_sources:ro" -v "$P/provenance:/orig_prov:ro" -v "$REPO:/repo:ro" -v "$V:/v" --entrypoint python "$DEV" \
    /repo/scripts/phd/repo_branch_setup_v1/compare_r11.py
}

forks() {
  /usr/bin/python3 "$S/run_fork_check.py" --prior LoD2 --gpu 0 > "$V/logs/queue_LoD2.log" 2>&1 & local a=$!
  /usr/bin/python3 "$S/run_fork_check.py" --prior ALS --gpu 1 > "$V/logs/queue_ALS.log" 2>&1 & local b=$!
  wait "$a"; local ra=$?; wait "$b"; local rb=$?
  cat "$V/logs/queue_LoD2.log" "$V/logs/queue_ALS.log"
  return $(( ra | rb ))
}

checks() {
  mkdir -p "$V/s52" "$V/fork_inputs"   # empty mount points for the read-only originals inside /out
  D -v "$ART:/art:ro" -v "$PREP:/prep:ro" -v "$V:/out" -v "$P/s52:/out/s52:ro" -v "$P/fork_inputs:/out/fork_inputs:ro" \
    -v "$REPO:/repo:ro" -w /repo/scripts/phd/main_prep_discard_rule_v1 --entrypoint python "$DEV" \
    fork_checks.py --tag chk --inputs fork_inputs/s52 --run-sub s52/box --out fork_checks/chk.json
}

compare() {
  D -v "$P/fork_runs/s52:/orig:ro" -v "$P/fork_checks:/orig_checks:ro" -v "$V:/v" -v "$REPO:/repo:ro" --entrypoint python "$DEV" \
    /repo/scripts/phd/repo_branch_setup_v1/compare_runs.py
}

receipt() {
  D -v "$V:/v" -v "$REPO:/repo:ro" -e JBGS_CHECKOUT="$REPO" -e JBGS_BRANCH="$(git -C "$REPO" branch --show-current)" \
    -e JBGS_COMMIT="$COMMIT" \
    -e JBGS_DIRTY="$(git -C "$REPO" status --porcelain | wc -l) uncommitted paths = this task's own scripts and config (committed after the run, unchanged)" \
    -e JBGS_DEV="$DEV" -e JBGS_DEV_ID="$(docker inspect --format '{{.Id}}' "$DEV")" \
    -e JBGS_FORK="$FORKIMG" -e JBGS_FORK_ID="$(docker inspect --format '{{.Id}}' "$FORKIMG")" \
    --entrypoint python "$DEV" /repo/scripts/phd/repo_branch_setup_v1/receipt.py
}

steps=("$@"); [ ${#steps[@]} -eq 0 ] && steps=(tests rebuild forks checks compare receipt)
rc_all=0
for st in "${steps[@]}"; do step "$st" "$st" || rc_all=1; done
echo "ALL DONE rc=$rc_all"
exit $rc_all

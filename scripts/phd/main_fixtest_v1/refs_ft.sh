#!/usr/bin/env bash
# PHD-MAIN-FIXTEST-v1 일 5: the new distance metric of the reference results (dm_ft.py d2 / d2b) for the sites given, each under the
# training queue's CPU slot lock (logs/slot0.lock) so that it never runs beside a post step.   bash refs_ft.sh R1rep_b10 B0_b10
# scientific_verdict: null.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
FT="$ART/phase-payloads/phd/main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
for s in "$@"; do
  refs="nojudge_LoD2_s0 nojudge_ALS_s0 imgonly_s0 trust_ALS"
  [ "$s" = R1rep_b10 ] && refs="$refs abl_band_LoD2_s0"
  [ "$s" = B173nb_b10 ] && refs="$refs abl_band_ALS_s0"
  ( exec 9>>"$FT/logs/slot0.lock"; flock 9; CPUS=16 MEM=40 bash "$HERE/run_step_ft.sh" "dm_ref_d2_${s}" dm_ft.py d2 "$s" $refs )
  if [ "$s" = B0_b10 ]; then ( exec 9>>"$FT/logs/slot0.lock"; flock 9; CPUS=16 MEM=40 bash "$HERE/run_step_ft.sh" "dm_ref_d2b" dm_ft.py d2b $refs ); fi
done
echo "refs_ft done $(date '+%m-%d %H:%M:%S')"

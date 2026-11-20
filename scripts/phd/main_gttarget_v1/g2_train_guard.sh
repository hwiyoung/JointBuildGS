#!/bin/bash
# 2026-11-20 (user decision): training resumed alone while the main experiment's tiles run. Every 60 s: if memory pressure 'full avg60' > 15 %
# on two checks in a row, pause the training container again (g3_resume_watch.sh later unpauses it). Ends when the container is gone.
C=jbgs-gttarget-train-B173nb_b10__LoD2-gtt_s0_rerun1; hi=0
while docker inspect $C >/dev/null 2>&1; do
  f=$(awk '/^full/{split($3,a,"="); print a[2]}' /proc/pressure/memory); st=$(docker inspect -f '{{.State.Status}}' $C)
  if [ "$st" = running ] && awk -v f="$f" 'BEGIN{exit !(f>15)}'; then hi=$((hi+1)); else hi=0; fi
  echo "$(date +%FT%T) $st mem_full_avg60=$f hi=$hi"
  if [ $hi -ge 2 ]; then docker pause $C; echo "$(date +%FT%T) PAUSED_AGAIN"; hi=0; fi
  sleep 60
done
echo "$(date +%FT%T) container gone"

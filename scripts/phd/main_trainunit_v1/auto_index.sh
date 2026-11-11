#!/usr/bin/env bash
# Index a unit's maps once all of its map parts reported MAPS_DONE (host loop, 60 s).
TU=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1
cd "$(dirname "$0")"
while true; do
  left=0
  for u in campus cell0 cell1 cell2 cell3; do for p in ALS LoD2; do
    [ -f "$TU/stage1/${u}__$p/ready.json" ] && continue
    left=1
    parts=$(ls $TU/logs/maps-$u-$p-*.log 2>/dev/null | wc -l); done_=$(grep -l MAPS_DONE $TU/logs/maps-$u-$p-*.log 2>/dev/null | wc -l)
    if [ "$parts" -gt 0 ] && [ "$parts" = "$done_" ] && ! docker ps --format '{{.Names}}' | grep -q "jbgs-trainunit-index-$u-$p\$"; then
      bash run_cpu.sh index-$u-$p 2 6g tu_campus.py index $u $p > /dev/null 2>&1
    fi
  done; done
  [ "$left" = "0" ] && exit 0
  sleep 60
done

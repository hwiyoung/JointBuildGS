#!/bin/bash
# Resume after the 2026-11-20 10:28 pause (host memory/disk saturation while the main experiment ran three TSDF tiles).
# Every 5 min: resume when no b151 tile container runs and memory pressure 'full avg60' < 5 %. Then: unpause training, continue the
# main g_mesh (pid 293601) and its paused tile container, and 10 min later start the second mesh worker (g3_mesh_helper.py).
P=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_gttarget_v1/PHD-MAIN-GTTARGET-v1
cd "$(dirname "$0")"
while true; do
  n=$(docker ps --format '{{.Names}}' | grep -cE 'b151-post.*(-tile[0-9]+|-t[0-9]+)$')
  f=$(awk '/^full/{split($3,a,"="); print a[2]}' /proc/pressure/memory)
  echo "$(date +%FT%T) b151_tiles=$n mem_full_avg60=$f"
  if [ "$n" -eq 0 ] && awk -v f="$f" 'BEGIN{exit !(f<5)}'; then break; fi
  sleep 300
done
echo "$(date +%FT%T) RESUME"
docker unpause jbgs-gttarget-train-B173nb_b10__LoD2-gtt_s0_rerun1
kill -CONT 293601
for c in $(docker ps --filter status=paused --format '{{.Names}}' | grep '^jbgs-gtt-gtj-'); do docker unpause $c; done
sleep 600
echo "$(date +%FT%T) HELPER START"
GT_FASTWORK=/home/innopam/jbgs_fastwork_gtt python3 g3_mesh_helper.py $(cat $P/logs/mesh_jobs_main.txt)
echo "$(date +%FT%T) HELPER DONE"

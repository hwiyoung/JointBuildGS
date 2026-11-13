#!/usr/bin/env bash
# Addendum 14 execution only (no setting or result changes): while another session's CPU meshing (cv2_case_run.py) runs, the
# two parallel cellsef cells pushed host MemAvailable under the 20 GB guard (cell2 and cell1 attempt 1, 2026-11-13 19:09/19:12).
# GPU 1's queue was told to stop after its current job (control/EF_STOP_1), so the cells run one at a time on GPU 0. This waits until
# that meshing has ended, then lifts the stop file and, if queue 1 has already ended, starts it again.
#   nohup bash tu_gpu1_resume.sh > <log> 2>&1 &
set -u
here=$(cd "$(dirname "$0")" && pwd)
cd "$here"
TU=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1
while pgrep -f "python3 cv2_case_run.py" >/dev/null; do sleep 120; done
echo "other meshing ended $(date +%T)"
if ! pgrep -f "python3 tu_ef_queue.py" >/dev/null; then echo "no queue left: nothing to resume"; exit 0; fi
rm -f "$TU/control/EF_STOP_1"
if pgrep -f "python3 tu_ef_queue.py 1" >/dev/null; then
  echo "queue 1 still running: stop file removed $(date +%T)"
else
  nohup python3 tu_ef_queue.py 1 >> "$TU/logs/ef_queue_add14_gpu1.log" 2>&1 &
  echo "queue 1 restarted pid $! $(date +%T)"
fi

#!/usr/bin/env bash
# Read-only rendering of complete arms inside this task's own admitted container.
# No other GPU owner's process is entered, interrupted, or reconfigured.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_candpick_v1/PHD-MAIN-CANDPICK-v1
gpu=$1
case "$gpu" in
  0) container=jbgs-candpick-train-b173; unit=B173_ALS ;;
  1) container=jbgs-candpick-train-r1; unit=R1_LoD2 ;;
  *) exit 2 ;;
esac
test "$(docker inspect -f '{{.State.Running}}' "$container")" = true
free_mib=$(nvidia-smi --id="$gpu" --query-gpu=memory.free --format=csv,noheader,nounits)
test "$free_mib" -ge 10240
available_kib=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
test "$available_kib" -ge 16777216
limit=$(docker inspect -f '{{.HostConfig.Memory}}' "$container")
used=$(docker exec "$container" cat /sys/fs/cgroup/memory.current)
test "$((limit-used))" -ge 8589934592
stamp=$(date -u +%Y%m%dT%H%M%SZ)
python3 - "$OUT" "$unit" "$container" "$free_mib" "$available_kib" "$limit" "$used" "$stamp" <<'PY'
import json,sys
from pathlib import Path
out,unit,container,gpu_free,host_free,limit,used,stamp=sys.argv[1:]
p=Path(out)/'logs'/('shared_render_admission_'+unit+'_'+stamp+'.json')
p.write_text(json.dumps(dict(unit=unit,container=container,gpu_free_mib=int(gpu_free),
 host_available_kib=int(host_free),existing_cgroup_limit_bytes=int(limit),existing_cgroup_used_bytes=int(used),
 action='read-only complete-arm render in same unchanged task cgroup',scientific_verdict=None),indent=2)+'\n')
PY
docker exec "$container" python -B -u scripts/phd/main_candpick_v1/render_crops.py "$unit" \
  2>&1 | tee "$OUT/logs/shared_render_${unit}_${stamp}.log"

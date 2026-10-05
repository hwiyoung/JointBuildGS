#!/usr/bin/env bash
# Forward-only, foreground bounded diagnostic; existing payloads mounted read-only.
set -euo pipefail
probe_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
probe_artifact="$(realpath "$probe_repo/../JointBuildGS-artifacts")"
probe_base="$probe_artifact/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
probe_task="$probe_artifact/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
probe_image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
[[ "$#" == 0 ]]
test "$(docker image inspect "$probe_image" --format '{{.Id}}')" = "$probe_image"
mkdir -p "$probe_task/rgb_radius_probe_v1"
probe_out="$(mktemp -d "$probe_task/rgb_radius_probe_v1/attempt.XXXXXXXX")"
cp -p "$probe_repo/scripts/phd/geogs_mvs_pgsr_v1/rgb_radius_probe.py" "$probe_out/rgb_radius_probe.py"
cp -p "${BASH_SOURCE[0]}" "$probe_out/launcher.sh"
cp -p "$probe_repo/configs/phd/geogs_mvs_pgsr_v1/rgb_radius_probe_v1.json" "$probe_out/config.json"
git -C "$probe_repo" rev-parse HEAD > "$probe_out/operator_head.txt"
nvidia-smi --query-gpu=index,uuid,memory.free,utilization.gpu --format=csv > "$probe_out/gpu_before.csv"
probe_observation="$(nvidia-smi --id=0 --query-gpu=memory.free,utilization.gpu --format=csv,noheader,nounits)"
IFS=, read -r probe_free probe_util <<< "$probe_observation"
probe_free="${probe_free//[[:space:]]/}"; probe_util="${probe_util//[[:space:]]/}"
if (( probe_free < 20000 || probe_util > 5 )); then
  printf 'GPU busy; no job launched\n' > "$probe_out/run.log"
  printf '2\n' > "$probe_out/exit_code.txt"
  printf '%s\n' "$probe_out"
  exit 2
fi
probe_container="jbgs-rgb-radius-$(basename "$probe_out" | tr '[:upper:]' '[:lower:]')"
probe_command=(docker run --rm --name "$probe_container" --read-only --network none --cpus 2 --memory 16g --memory-swap 16g
  --user "$(id -u):$(id -g)" --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges
  --gpus device=0 --tmpfs /tmp:rw,nosuid,size=512m --env PYTHONDONTWRITEBYTECODE=1
  --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=2 --env MKL_NUM_THREADS=2
  --env "DIAGNOSTIC_IMAGE_ID=$probe_image" --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
  --mount "type=bind,src=$probe_base,dst=/base,readonly"
  --mount "type=bind,src=$probe_task,dst=/task,readonly"
  --mount "type=bind,src=$probe_out,dst=/out"
  --mount "type=bind,src=$probe_out/config.json,dst=/config.json,readonly"
  "$probe_image" python /out/rgb_radius_probe.py)
printf '%q ' "${probe_command[@]}" > "$probe_out/command.sh"
printf '\n' >> "$probe_out/command.sh"
printf '%s\n' "$probe_out"
set +e
timeout --signal=TERM --kill-after=15s 600s "${probe_command[@]}" > "$probe_out/run.log" 2>&1
probe_exit=$?
set -e
if docker inspect "$probe_container" >/dev/null 2>&1; then
  docker stop --time 10 "$probe_container" >> "$probe_out/run.log" 2>&1 || true
fi
printf '%s\n' "$probe_exit" > "$probe_out/exit_code.txt"
nvidia-smi --query-gpu=index,uuid,memory.free,utilization.gpu --format=csv > "$probe_out/gpu_after.csv"
tail -n 10 "$probe_out/run.log"
exit "$probe_exit"

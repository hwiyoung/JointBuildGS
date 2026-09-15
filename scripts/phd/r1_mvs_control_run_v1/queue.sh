#!/usr/bin/env bash
set -euo pipefail
attempt=${1:?absolute attempt path}
artifact_root=$(realpath "$attempt/../../../../..")
prep="$artifact_root/phase-payloads/phd/r1_mvs_control_v1/PHD-R1-MVS-CONTROL-PREP-v1/attempt_20260916T130151Z_jm4gu7vc"
runtime="$prep/finalize_20260916T131410Z_ZpnUStaZ/runtime"
weights="$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
failure() { local code=$?; if (( code != 0 )); then printf 'FAILED %s exit=%s\n' "${stage:-startup}" "$code" > "$attempt/status.txt"; fi; }
trap failure EXIT
test ! -e "$attempt/started.txt"
date -Is > "$attempt/started.txt"
gpu=1
common=(--rm --network none --cpus 8 --shm-size 4g --user "$(id -u):$(id -g)"
 -e PYTHONDONTWRITEBYTECODE=1 -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
 --mount "type=bind,source=$attempt/snapshot,target=/driver,readonly"
 --mount "type=bind,source=$prep/result/input,target=/input,readonly"
 --mount "type=bind,source=$runtime,target=/runtime,readonly"
 --mount "type=bind,source=$weights,target=/weights,readonly" --workdir /source)
run_stage() {
 local role=$1;shift
 stage=$role
 mkdir "$attempt/$role"
 printf '%s\n' "$role" > "$attempt/status.txt"
 local source=refinement
 [[ "$role" == anchor || "$role" == verify ]] && source=anchor
 local hardware=(--gpus "device=$gpu")
 [[ "$role" == verify ]] && hardware=(--runtime runc -e NVIDIA_VISIBLE_DEVICES=void)
 local mounts=()
 if [[ "$role" == preflight || "$role" == refinement ]]; then mounts+=(--mount "type=bind,source=$attempt/anchor/model/jbgs_complete/iteration_8000,target=/anchor,readonly"); fi
 if [[ "$role" == refinement ]]; then mounts+=(--mount "type=bind,source=$attempt/preflight,target=/gate,readonly"); fi
 if [[ "$role" == extract_anchor ]]; then mounts+=(--mount "type=bind,source=$attempt/anchor,target=/trained,readonly"); fi
 if [[ "$role" == extract_final ]]; then mounts+=(--mount "type=bind,source=$attempt/refinement,target=/trained,readonly"); fi
 local phase=$role
 [[ "$role" == extract_* ]] && phase=extract
 local resources=(--memory 32g)
 if [[ "$role" == extract_* ]]; then
   resources=(--memory 56g --memory-swap 56g)
   while (( $(awk '/MemAvailable:/ {print $2}' /proc/meminfo) < 62000000 )); do
     printf 'WAITING_RAM %s\n' "$role" > "$attempt/status.txt"
     sleep 30
   done
   printf '%s\n' "$role" > "$attempt/status.txt"
 fi
 local command=(docker run "${common[@]}" "${resources[@]}" "${hardware[@]}" "${mounts[@]}"
 --name "jbgs-r1-${attempt##*/}-$role"
 --mount "type=bind,source=$runtime/${source}_source,target=/source,readonly"
 --mount "type=bind,source=$attempt/$role,target=/output"
 "$image" python /driver/phase.py "$phase" "$@")
 printf '%q ' "${command[@]}" > "$attempt/$role/command.sh"
 printf '\n' >> "$attempt/$role/command.sh"
 "${command[@]}" > "$attempt/$role/driver.log" 2>&1
}
run_stage verify
run_stage anchor
run_stage preflight
run_stage refinement
run_stage extract_final --iteration 30000
run_stage extract_anchor --iteration 8000
printf 'COMPLETE\n' > "$attempt/status.txt"
date -Is > "$attempt/completed.txt"

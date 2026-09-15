#!/usr/bin/env bash
# Continue only extraction from validated checkpoints; preserve the failed stage.
set -euo pipefail
attempt=${1:?original run attempt}
recovery=${2:?fresh recovery path inside the attempt}
artifact_root=$(realpath "$attempt/../../../../..")
prep="$artifact_root/phase-payloads/phd/r1_mvs_control_v1/PHD-R1-MVS-CONTROL-PREP-v1/attempt_20260916T130151Z_jm4gu7vc"
runtime="$prep/finalize_20260916T131410Z_ZpnUStaZ/runtime"
weights="$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
failure() { local code=$?; if (( code != 0 )); then printf 'FAILED %s exit=%s\n' "${stage:-startup}" "$code" > "$recovery/status.txt"; fi; }
trap failure EXIT
test ! -e "$recovery/started.txt"
date -Is > "$recovery/started.txt"
for stage in extract_final extract_anchor; do
 iteration=30000;trained=refinement
 if [[ "$stage" == extract_anchor ]]; then iteration=8000;trained=anchor;fi
 mkdir "$recovery/$stage"
 printf '%s\n' "$stage" > "$recovery/status.txt"
 command=(docker run --rm --network none --gpus device=1 --cpus 8 --memory 56g --memory-swap 56g --shm-size 4g
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
  --name "jbgs-r1-${recovery##*/}-$stage"
  --mount "type=bind,source=$recovery/source,target=/driver,readonly"
  --mount "type=bind,source=$prep/result/input,target=/input,readonly"
  --mount "type=bind,source=$runtime,target=/runtime,readonly"
  --mount "type=bind,source=$weights,target=/weights,readonly"
  --mount "type=bind,source=$runtime/refinement_source,target=/source,readonly"
  --mount "type=bind,source=$attempt/$trained,target=/trained,readonly"
  --mount "type=bind,source=$recovery/$stage,target=/output" --workdir /source
  "$image" python /driver/phase.py extract --iteration "$iteration")
 printf '%q ' "${command[@]}" > "$recovery/$stage/command.sh"
 printf '\n' >> "$recovery/$stage/command.sh"
 "${command[@]}" > "$recovery/$stage/driver.log" 2>&1
done
printf 'COMPLETE\n' > "$recovery/status.txt"
date -Is > "$recovery/completed.txt"

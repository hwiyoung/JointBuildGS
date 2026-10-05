#!/usr/bin/env bash
set -euo pipefail
geogs_rr_region="${1:?P1 P2}"
case "$geogs_rr_region" in P1) geogs_rr_suffix='' ;; P2) geogs_rr_suffix=_P2 ;; *) exit 2 ;; esac
geogs_rr_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_rr_task=$(realpath "$geogs_rr_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_rr_old="no_anchor_sfm_memory_recovery${geogs_rr_suffix}_v1"
geogs_rr_new="no_anchor_sfm_memory_recovery${geogs_rr_suffix}_v2"
geogs_rr_run="$geogs_rr_task/$geogs_rr_old/runs/$geogs_rr_region/SFM_noanchor_D005_Pnative"
geogs_rr_out="$geogs_rr_task/$geogs_rr_new"
geogs_rr_container="jbgs-geogs-${geogs_rr_old}-${geogs_rr_region}-train"
geogs_rr_code="$geogs_rr_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1"
geogs_rr_image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test ! -e "$geogs_rr_out/replacement_execution"
mkdir -p -- "$geogs_rr_out/replacement_execution"
cp -- "${BASH_SOURCE[0]}" "$geogs_rr_code/replace_memory_retry.py" "$geogs_rr_out/replacement_execution/"
docker inspect "$geogs_rr_container" > "$geogs_rr_out/replacement_execution/container_before.json"
trap 'geogs_rr_exit=$?; printf "%s\n" "$geogs_rr_exit" > "$geogs_rr_out/replacement_execution/exit_code.txt"' EXIT
docker run --rm --network none --cpus 1 --memory 2g --memory-swap 2g \
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$geogs_rr_task,dst=/task,readonly" \
  --mount "type=bind,src=$geogs_rr_out,dst=/replacement" \
  --mount "type=bind,src=$geogs_rr_run,dst=/output" \
  "$geogs_rr_image" python /replacement/replacement_execution/replace_memory_retry.py --mode prepare --region "$geogs_rr_region" \
  > "$geogs_rr_out/replacement_execution/prepare_stdout.log" 2> "$geogs_rr_out/replacement_execution/prepare_stderr.log"
docker exec "$geogs_rr_container" python /audit/no_anchor_v1/replace_memory_retry.py --mode stop --region "$geogs_rr_region" \
  > "$geogs_rr_out/replacement_execution/stop_stdout.log" 2> "$geogs_rr_out/replacement_execution/stop_stderr.log"
cat "$geogs_rr_out/replacement_execution/stop_stdout.log"

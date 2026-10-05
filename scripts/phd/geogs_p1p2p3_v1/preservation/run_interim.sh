#!/usr/bin/env bash
set -euo pipefail
geogs_pres_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_pres_task=$(realpath "$geogs_pres_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_pres_out="$geogs_pres_task/preservation"
if [[ -e "$geogs_pres_out/interim_allocator_v2.json" || -e "$geogs_pres_out/services_interim_allocator_v2.jsonl" ]]; then echo 'Interim preservation output exists; preserve it' >&2; exit 1; fi
docker ps -a --no-trunc --format '{{json .}}' > "$geogs_pres_out/services_interim_allocator_v2.jsonl"
cp -- "$geogs_pres_repo/scripts/phd/geogs_p1p2p3_v1/preservation/verify_interim.py" "$geogs_pres_out/interim_allocator_v2_source.py"
cp -- "$geogs_pres_repo/scripts/phd/geogs_p1p2p3_v1/preservation/run_interim.sh" "$geogs_pres_out/interim_allocator_v2_command.sh"
geogs_pres_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
printf '%s\n' "$geogs_pres_image" > "$geogs_pres_out/interim_allocator_v2_image_id.txt"
docker run --rm --network none --read-only --cpus 2 --memory 2g \
  --mount "type=bind,src=$geogs_pres_repo,dst=/repo,readonly" \
  --mount "type=bind,src=$geogs_pres_out,dst=/baseline,readonly" \
  --mount "type=bind,src=$geogs_pres_out/interim_allocator_v2_source.py,dst=/audit.py,readonly" \
  --mount "type=bind,src=$geogs_pres_out/services_interim_allocator_v2.jsonl,dst=/services_current.jsonl,readonly" \
  --mount "type=bind,src=$geogs_pres_out,dst=/out" \
  --entrypoint python "$geogs_pres_image" /audit.py > "$geogs_pres_out/interim_allocator_v2.log" 2>&1
cat -- "$geogs_pres_out/interim_allocator_v2.log"

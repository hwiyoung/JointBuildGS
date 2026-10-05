#!/usr/bin/env bash
set -euo pipefail
geogs_rec_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_rec_task=$(realpath "$geogs_rec_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_rec_out="$geogs_rec_task/preservation"
if [[ -e "$geogs_rec_out/interim_allocator_v2_reconciliation.json" ]]; then echo 'Reconciliation exists; preserve it' >&2; exit 1; fi
test -f "$geogs_rec_out/services_interim_allocator_v2_default_format.txt"
cp -- "$geogs_rec_repo/scripts/phd/geogs_p1p2p3_v1/preservation/reconcile_interim.py" "$geogs_rec_out/interim_allocator_v2_reconciliation_source.py"
cp -- "$geogs_rec_repo/scripts/phd/geogs_p1p2p3_v1/preservation/run_reconcile.sh" "$geogs_rec_out/interim_allocator_v2_reconciliation_command.sh"
geogs_rec_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
printf '%s\n' "$geogs_rec_image" > "$geogs_rec_out/interim_allocator_v2_reconciliation_image_id.txt"
docker run --rm --network none --read-only --cpus 2 --memory 2g \
  --mount "type=bind,src=$geogs_rec_repo,dst=/repo,readonly" \
  --mount "type=bind,src=$geogs_rec_out,dst=/out" \
  --mount "type=bind,src=$geogs_rec_task/contracts/runtime_layout_allocator_v2.json,dst=/layout_external.json,readonly" \
  --entrypoint python "$geogs_rec_image" /repo/scripts/phd/geogs_p1p2p3_v1/preservation/reconcile_interim.py \
  > "$geogs_rec_out/interim_allocator_v2_reconciliation.log" 2>&1
cat -- "$geogs_rec_out/interim_allocator_v2_reconciliation.log"

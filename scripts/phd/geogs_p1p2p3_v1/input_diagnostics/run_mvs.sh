#!/usr/bin/env bash
set -euo pipefail
geogs_mvs_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_mvs_task=$(realpath "$geogs_mvs_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_mvs_out="$geogs_mvs_task/input_diagnostics_v1/mvs_projection"
if [[ -e "$geogs_mvs_out" ]]; then echo 'MVS diagnostic output exists; preserve evidence' >&2; exit 1; fi
mkdir -- "$geogs_mvs_out"
cp -- "$geogs_mvs_repo/scripts/phd/geogs_p1p2p3_v1/input_diagnostics/mvs_projection.py" "$geogs_mvs_out/script_source.py"
cp -- "$geogs_mvs_repo/scripts/phd/geogs_p1p2p3_v1/input_diagnostics/run_mvs.sh" "$geogs_mvs_out/command.sh"
geogs_mvs_mounts=()
for geogs_mvs_region in P1 P2 P3; do
  geogs_mvs_mounts+=(--mount "type=bind,src=$geogs_mvs_task/evaluation_inputs/$geogs_mvs_region/native.npz,dst=/native/$geogs_mvs_region.npz,readonly")
  geogs_mvs_mounts+=(--mount "type=bind,src=$geogs_mvs_task/inputs/$geogs_mvs_region/prior,dst=/inputs/$geogs_mvs_region/prior,readonly")
  geogs_mvs_mounts+=(--mount "type=bind,src=$geogs_mvs_task/inputs/$geogs_mvs_region/da3,dst=/inputs/$geogs_mvs_region/da3,readonly")
  geogs_mvs_mounts+=(--mount "type=bind,src=$geogs_mvs_task/inputs/$geogs_mvs_region/scene/split_manifest_da3_v2.json,dst=/inputs/$geogs_mvs_region/scene/split_manifest_da3_v2.json,readonly")
done
geogs_mvs_image=$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')
printf '%s\n' "$geogs_mvs_image" > "$geogs_mvs_out/image_id.txt"
docker run --rm --name jbgs-geogs-input-mvs-diagnostic-v1 --read-only --network none --cpus 4 --memory 8g \
  --tmpfs /tmp:rw,nosuid,size=256m --env MPLCONFIGDIR=/tmp/mpl --env OPENBLAS_NUM_THREADS=1 --env OMP_NUM_THREADS=1 \
  --mount "type=bind,src=$geogs_mvs_out/script_source.py,dst=/mvs.py,readonly" \
  --mount "type=bind,src=$geogs_mvs_task/input_diagnostics_v1/depth_compare_source.py,dst=/base_script.py,readonly" \
  --mount "type=bind,src=$geogs_mvs_task/input_diagnostics_v1/roi_contract_source.py,dst=/roi_contract.py,readonly" \
  --mount "type=bind,src=$geogs_mvs_task/input_diagnostics_v1/config_snapshot.json,dst=/config.json,readonly" \
  --mount "type=bind,src=$geogs_mvs_task/input_diagnostics_v1/selected_views.json,dst=/selected_views.json,readonly" \
  "${geogs_mvs_mounts[@]}" --mount "type=bind,src=$geogs_mvs_out,dst=/out" \
  --entrypoint /opt/geogs/bin/python "$geogs_mvs_image" /mvs.py > "$geogs_mvs_out/run.log" 2>&1
printf '%s\n' "$geogs_mvs_out/receipt.json"

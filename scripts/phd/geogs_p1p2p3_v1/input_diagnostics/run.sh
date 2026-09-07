#!/usr/bin/env bash
set -euo pipefail
geogs_diag_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_diag_task=$(realpath "$geogs_diag_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_diag_out="$geogs_diag_task/input_diagnostics_v1"
if [[ -e "$geogs_diag_out" ]]; then echo 'Diagnostic output exists; preserve prior evidence' >&2; exit 1; fi
mkdir -- "$geogs_diag_out"
cp -- "$geogs_diag_repo/scripts/phd/geogs_p1p2p3_v1/input_diagnostics/depth_compare.py" "$geogs_diag_out/depth_compare_source.py"
cp -- "$geogs_diag_repo/scripts/phd/geogs_p1p2p3_v1/input_diagnostics/run.sh" "$geogs_diag_out/command.sh"
cp -- "$geogs_diag_repo/scripts/phd/geogs_p1p2p3_v1/evaluation/render_quality.py" "$geogs_diag_out/roi_contract_source.py"
geogs_diag_image=$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')
printf '%s\n' "$geogs_diag_image" > "$geogs_diag_out/image_id.txt"
geogs_diag_mounts=()
for geogs_diag_region in P1 P2 P3; do
  geogs_diag_mounts+=(--mount "type=bind,src=$geogs_diag_task/inputs/$geogs_diag_region/prior,dst=/inputs/$geogs_diag_region/prior,readonly")
  geogs_diag_mounts+=(--mount "type=bind,src=$geogs_diag_task/inputs/$geogs_diag_region/da3,dst=/inputs/$geogs_diag_region/da3,readonly")
  geogs_diag_mounts+=(--mount "type=bind,src=$geogs_diag_task/inputs/$geogs_diag_region/scene/split_manifest_da3_v2.json,dst=/inputs/$geogs_diag_region/scene/split_manifest_da3_v2.json,readonly")
  geogs_diag_mounts+=(--mount "type=bind,src=$geogs_diag_task/inputs/$geogs_diag_region/scene/da3_batches_v2,dst=/train_rgb/$geogs_diag_region,readonly")
  geogs_diag_mounts+=(--mount "type=bind,src=$geogs_diag_task/da3/$geogs_diag_region/balanced_v2/batches,dst=/batches/$geogs_diag_region,readonly")
done
docker run --rm --name jbgs-geogs-input-depth-diagnostic-v1 --read-only --network none --cpus 4 --memory 8g \
  --tmpfs /tmp:rw,nosuid,size=256m --env MPLCONFIGDIR=/tmp/mpl --env OPENBLAS_NUM_THREADS=1 --env OMP_NUM_THREADS=1 \
  --mount "type=bind,src=$geogs_diag_out/depth_compare_source.py,dst=/diagnostic.py,readonly" \
  --mount "type=bind,src=$geogs_diag_out/roi_contract_source.py,dst=/roi_contract.py,readonly" \
  --mount "type=bind,src=$geogs_diag_repo/configs/phd/geogs_p1p2p3_v1/experiment_v1.json,dst=/config.json,readonly" \
  "${geogs_diag_mounts[@]}" --mount "type=bind,src=$geogs_diag_out,dst=/out" \
  --entrypoint /opt/geogs/bin/python "$geogs_diag_image" /diagnostic.py > "$geogs_diag_out/run.log" 2>&1
printf '%s\n' "$geogs_diag_out/receipt.json"

#!/usr/bin/env bash
set -euo pipefail
geogs_domain_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_domain_task=$(realpath "$geogs_domain_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_domain_out="$geogs_domain_task/input_diagnostics_v1/extraction_domain_v1"
if [[ -e "$geogs_domain_out" ]]; then echo 'Diagnostic output exists; preserve prior evidence' >&2; exit 1; fi
mkdir -- "$geogs_domain_out"
cp -- "$geogs_domain_repo/scripts/phd/geogs_p1p2p3_v1/input_diagnostics/extraction_domain.py" "$geogs_domain_out/extraction_domain_source.py"
cp -- "$geogs_domain_repo/scripts/phd/geogs_p1p2p3_v1/input_diagnostics/run_extraction_domain.sh" "$geogs_domain_out/command.sh"
cp -- "$geogs_domain_repo/scripts/phd/geogs_p1p2p3_v1/evaluation/render_quality.py" "$geogs_domain_out/roi_contract_source.py"
cp -- "$geogs_domain_task/contracts/execution_v1.json" "$geogs_domain_out/config_snapshot.json"
geogs_domain_image=$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')
if [[ "$geogs_domain_image" != sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e ]]; then
  echo 'Exact frozen image identity mismatch' >&2; exit 1
fi
printf '%s\n' "$geogs_domain_image" > "$geogs_domain_out/image_id.txt"
geogs_domain_mounts=()
for geogs_domain_region in P1 P2 P3; do
  for geogs_domain_file in input_manifest.json scene/split_manifest_da3_v2.json scene/sparse/0/images.bin; do
    geogs_domain_mounts+=(--mount "type=bind,src=$geogs_domain_task/inputs/$geogs_domain_region/$geogs_domain_file,dst=/inputs/$geogs_domain_region/$geogs_domain_file,readonly")
  done
done
docker run --rm --name jbgs-geogs-input-extraction-domain-v1 --read-only --network none --cpus 2 --memory 3g \
  --tmpfs /tmp:rw,nosuid,size=128m --env MPLCONFIGDIR=/tmp/mpl --env OPENBLAS_NUM_THREADS=1 --env OMP_NUM_THREADS=1 \
  --env PYTHONDONTWRITEBYTECODE=1 --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 \
  --mount "type=bind,src=$geogs_domain_out/extraction_domain_source.py,dst=/diagnostic.py,readonly" \
  --mount "type=bind,src=$geogs_domain_out/roi_contract_source.py,dst=/roi_contract.py,readonly" \
  --mount "type=bind,src=$geogs_domain_out/config_snapshot.json,dst=/config.json,readonly" \
  --mount "type=bind,src=$geogs_domain_task/sources/GeoGS-state-camera-v1,dst=/source,readonly" \
  "${geogs_domain_mounts[@]}" --mount "type=bind,src=$geogs_domain_out,dst=/out" \
  --entrypoint /opt/geogs/bin/python "$geogs_domain_image" /diagnostic.py > "$geogs_domain_out/run.log" 2>&1
printf '%s\n' "$geogs_domain_out/receipt.json"

#!/usr/bin/env bash
set -euo pipefail
sor_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
sor_artifacts=$(realpath "$sor_repo/../JointBuildGS-artifacts")
sor_id=${1:-PHD-WU-VALLET-P3-SOR-DIAGNOSTIC-v3}
sor_base="$sor_artifacts/phase-payloads/phd/wu_vallet_p3_v3"
sor_output="$sor_base/$sor_id"
sor_snapshot="$sor_base/${sor_id}_source"
sor_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
sor_head=$(git -C "$sor_repo" rev-parse HEAD)
mkdir -p "$sor_base"
mkdir "$sor_output"
python3 - "$sor_repo" "$sor_snapshot" <<'PY'
import hashlib,json,pathlib,shutil,sys
repo,out=map(pathlib.Path,sys.argv[1:]);out.mkdir(exist_ok=False)
files=['scripts/phd/wu_vallet_p3_v3/spatial_outlier_diagnostic.py',
       'scripts/phd/wu_vallet_p3_v3/run_sor_diagnostic.sh',
       'configs/phd/wu_vallet_p3_v3/sor_diagnostic_v3.json','AGENTS.md']
hashes={}
for name in files:
    dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(repo/name,dest);hashes[name]=hashlib.sha256(dest.read_bytes()).hexdigest()
(out/'SOURCE_MANIFEST.json').write_text(json.dumps(hashes,indent=2)+'\n')
PY
docker run --rm --name "jbgs-${sor_id,,}" --network none --cpus 4 --memory 8g \
  --entrypoint python --mount "type=bind,src=$sor_snapshot,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$sor_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$sor_output,dst=/output" --workdir /workspace/JointBuildGS \
  --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=4 --env OPENBLAS_NUM_THREADS=1 \
  --env "JBGS_SOURCE_GIT_HEAD=$sor_head" --env "JBGS_CONTAINER_IMAGE_ID=$sor_image" \
  --env "JBGS_SOURCE_SNAPSHOT_MANIFEST=$sor_snapshot/SOURCE_MANIFEST.json" \
  "$sor_image" scripts/phd/wu_vallet_p3_v3/spatial_outlier_diagnostic.py \
  --config configs/phd/wu_vallet_p3_v3/sor_diagnostic_v3.json --output /output/run \
  2>&1 | tee "$sor_base/${sor_id}.console.log"

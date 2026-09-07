#!/usr/bin/env bash
set -euo pipefail
wv3_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
wv3_artifacts=$(realpath "$wv3_repo/../JointBuildGS-artifacts")
wv3_base="$wv3_artifacts/phase-payloads/phd/wu_vallet_p3_v3"
wv3_id=${1:-PHD-WU-VALLET-P3-FILTER-v3}
wv3_run="$wv3_base/$wv3_id"
wv3_source="$wv3_base/${wv3_id}_source"
wv3_image=sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774
wv3_head=$(git -C "$wv3_repo" rev-parse HEAD)
mkdir -p "$wv3_base"
mkdir "$wv3_run"
python3 - "$wv3_repo" "$wv3_source" <<'PY'
import sys,pathlib,shutil,hashlib,json
repo,out=map(pathlib.Path,sys.argv[1:]);out.mkdir(exist_ok=False)
names=['scripts/phd/wu_vallet_p3_v3/analyze_filtered_update.py',
       'scripts/phd/wu_vallet_p3_v3/run_filter_docker.sh',
       'configs/phd/wu_vallet_p3_v3/filter_v3.json',
       'tests/phd/test_wu_vallet_filter_v3.py','AGENTS.md','requirements.txt']
rows={}
for name in names:
    source=repo/name;dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    rows[name]=hashlib.sha256(dest.read_bytes()).hexdigest()
(out/'SOURCE_MANIFEST.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps({'snapshot':str(out),'files':len(rows)}))
PY
# Candidate generation cannot access UAS: only the existing Wu v2 input run is mounted.
docker run --rm --name "jbgs-${wv3_id,,}-candidates" --network none --cpus 6 --memory 16g \
  --entrypoint python --mount "type=bind,src=$wv3_source,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$wv3_artifacts/phase-payloads/phd/wu_vallet_p3_v2/PHD-WU-VALLET-P3-UPDATE-v2,dst=/artifacts/JointBuildGS/phase-payloads/phd/wu_vallet_p3_v2/PHD-WU-VALLET-P3-UPDATE-v2,readonly" \
  --mount "type=bind,src=$wv3_run,dst=/output" --workdir /workspace/JointBuildGS \
  --env PYTHONDONTWRITEBYTECODE=1 --env OPENBLAS_NUM_THREADS=2 --env OMP_NUM_THREADS=6 \
  --env "JBGS_SOURCE_GIT_HEAD=$wv3_head" --env "JBGS_CONTAINER_IMAGE_ID=$wv3_image" \
  --env "JBGS_SOURCE_SNAPSHOT_MANIFEST=$wv3_source/SOURCE_MANIFEST.json" \
  "$wv3_image" -m scripts.phd.wu_vallet_p3_v3.analyze_filtered_update \
  --config configs/phd/wu_vallet_p3_v3/filter_v3.json --output /output/run --stage candidates \
  2>&1 | tee "$wv3_run/candidates.console.log"
docker run --rm --name "jbgs-${wv3_id,,}-evaluation" --network none --cpus 6 --memory 16g \
  --entrypoint python --mount "type=bind,src=$wv3_source,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$wv3_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$wv3_run,dst=/output" --workdir /workspace/JointBuildGS \
  --env PYTHONDONTWRITEBYTECODE=1 --env OPENBLAS_NUM_THREADS=2 --env OMP_NUM_THREADS=6 \
  --env "JBGS_SOURCE_GIT_HEAD=$wv3_head" --env "JBGS_CONTAINER_IMAGE_ID=$wv3_image" \
  --env "JBGS_SOURCE_SNAPSHOT_MANIFEST=$wv3_source/SOURCE_MANIFEST.json" \
  "$wv3_image" -m scripts.phd.wu_vallet_p3_v3.analyze_filtered_update \
  --config configs/phd/wu_vallet_p3_v3/filter_v3.json --output /output/run --stage evaluation \
  2>&1 | tee "$wv3_run/evaluation.console.log"

#!/usr/bin/env bash
set -euo pipefail
wv3_mode=${1:?forensics or viewer}
wv3_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
wv3_artifacts=$(realpath "$wv3_repo/../JointBuildGS-artifacts")
wv3_base="$wv3_artifacts/phase-payloads/phd/wu_vallet_p3_v3"
case "$wv3_mode" in
  forensics) wv3_id=PHD-WU-VALLET-P3-FORENSICS-v3; wv3_module=scripts.phd.wu_vallet_p3_v3.build_forensics; wv3_cfg=configs/phd/wu_vallet_p3_v3/forensics_v3.json ;;
  viewer) wv3_id=PHD-WU-VALLET-P3-VIEWER-v3; wv3_module=scripts.phd.wu_vallet_p3_v3.build_viewer; wv3_cfg=configs/phd/wu_vallet_p3_v3/viewer_v3.json ;;
  *) exit 2 ;;
esac
wv3_id=${2:-$wv3_id}
wv3_run="$wv3_base/$wv3_id"
wv3_source="$wv3_base/${wv3_id}_source"
wv3_image=sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774
docker image inspect "$wv3_image" >/dev/null
wv3_head=$(git -C "$wv3_repo" rev-parse HEAD)
mkdir -p "$wv3_base"
mkdir "$wv3_run"
python3 - "$wv3_repo" "$wv3_source" <<'PY'
import sys,pathlib,subprocess,shutil,hashlib,json
repo,out=map(pathlib.Path,sys.argv[1:]);out.mkdir(exist_ok=False)
names=subprocess.check_output(['git','-C',str(repo),'ls-files','--cached','--others','--exclude-standard','-z','src','scripts','configs','tests','artifacts/manifests','AGENTS.md','requirements.txt']).decode().split('\0')
rows={}
for name in sorted(set(names)-{''}):
    source=repo/name
    if not source.is_file(): continue
    dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    rows[name]=hashlib.sha256(dest.read_bytes()).hexdigest()
(out/'SOURCE_MANIFEST.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps({'snapshot':str(out),'files':len(rows)}))
PY
docker run --rm --name "jbgs-${wv3_id,,}" --network none --cpus 4 --memory 16g \
  --entrypoint python --mount "type=bind,src=$wv3_source,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$wv3_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$wv3_run,dst=/output" --workdir /workspace/JointBuildGS \
  --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=4 --env OPENBLAS_NUM_THREADS=1 \
  --env MPLCONFIGDIR=/tmp/matplotlib \
  --env "JBGS_SOURCE_GIT_HEAD=$wv3_head" --env "JBGS_CONTAINER_IMAGE_ID=$wv3_image" \
  --env "JBGS_SOURCE_SNAPSHOT_MANIFEST=$wv3_source/SOURCE_MANIFEST.json" \
  "$wv3_image" -m "$wv3_module" --config "$wv3_cfg" --output /output/run \
  2>&1 | tee "$wv3_base/${wv3_id}.console.log"

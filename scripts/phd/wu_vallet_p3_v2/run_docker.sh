#!/usr/bin/env bash
set -euo pipefail
wv2_mode=${1:?update, evaluation, or viewer}
wv2_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
wv2_artifacts=$(realpath "$wv2_repo/../JointBuildGS-artifacts")
wv2_base="$wv2_artifacts/phase-payloads/phd/wu_vallet_p3_v2"
case "$wv2_mode" in
  update) wv2_id=PHD-WU-VALLET-P3-UPDATE-v2; wv2_module=scripts.phd.wu_vallet_p3_v2.update_points; wv2_cfg=configs/phd/wu_vallet_p3_v2/update_v2.json ;;
  evaluation) wv2_id=PHD-WU-VALLET-P3-EVALUATION-v2; wv2_module=scripts.phd.wu_vallet_p3_v2.evaluate_update; wv2_cfg=configs/phd/wu_vallet_p3_v2/evaluation_v2.json ;;
  viewer) wv2_id=PHD-WU-VALLET-P3-VIEWER-v2; wv2_module=scripts.phd.wu_vallet_p3_v2.build_viewer; wv2_cfg=configs/phd/wu_vallet_p3_v2/viewer_v2.json ;;
  *) exit 2 ;;
esac
wv2_id=${2:-$wv2_id}
wv2_run="$wv2_base/$wv2_id"
wv2_source="$wv2_base/${wv2_id}_source"
wv2_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
wv2_head=$(git -C "$wv2_repo" rev-parse HEAD)
mkdir -p "$wv2_base"
mkdir "$wv2_run"
python3 - "$wv2_repo" "$wv2_source" <<'PY'
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
docker run --rm --name "jbgs-${wv2_id,,}" --network none --cpus 6 --memory 28g \
  --entrypoint python --mount "type=bind,src=$wv2_source,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$wv2_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$wv2_run,dst=/output" --workdir /workspace/JointBuildGS \
  --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=6 --env OPENBLAS_NUM_THREADS=2 \
  --env "JBGS_SOURCE_GIT_HEAD=$wv2_head" --env "JBGS_CONTAINER_IMAGE_ID=$wv2_image" \
  --env "JBGS_SOURCE_SNAPSHOT_MANIFEST=$wv2_source/SOURCE_MANIFEST.json" \
  "$wv2_image" -m "$wv2_module" --config "$wv2_cfg" --output /output/run \
  2>&1 | tee "$wv2_base/${wv2_id}.console.log"

#!/usr/bin/env bash
set -euo pipefail
wv4_stage=${1:?prepare, acquisition, trajectory, update, evaluation, or viewer}
wv4_region=${2:?P1, P2, or ALL}
wv4_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
wv4_artifacts=$(realpath "$wv4_repo/../JointBuildGS-artifacts")
wv4_base="$wv4_artifacts/phase-payloads/phd/wu_vallet_regions_v4"
wv4_extra=()
case "$wv4_stage" in
  prepare) wv4_id="PHD-WU-VALLET-${wv4_region}-INPUT-v4"; wv4_module=scripts.phd.wu_vallet_regions_v4.prepare_inputs; wv4_cfg=configs/phd/wu_vallet_regions_v4/regions_v4.json; wv4_extra=(--region "$wv4_region") ;;
  acquisition) wv4_id="PHD-WU-VALLET-${wv4_region}-ACQUISITION-v4"; wv4_module=scripts.phd.wu_vallet_regions_v4.recover_acquisition; wv4_cfg="configs/phd/wu_vallet_regions_v4/${wv4_region}_acquisition_v4.json" ;;
  trajectory) wv4_id="PHD-WU-VALLET-${wv4_region}-TRAJECTORY-v4"; wv4_module=scripts.phd.wu_vallet_regions_v4.recover_trajectory; wv4_cfg="configs/phd/wu_vallet_regions_v4/${wv4_region}_trajectory_v4.json" ;;
  update) wv4_id="PHD-WU-VALLET-${wv4_region}-UPDATE-v4"; wv4_module=scripts.phd.wu_vallet_regions_v4.update_regions; wv4_cfg=configs/phd/wu_vallet_regions_v4/regions_v4.json; wv4_extra=(--region "$wv4_region") ;;
  evaluation) wv4_id=PHD-WU-VALLET-REGIONS-EVALUATION-v4; wv4_module=scripts.phd.wu_vallet_regions_v4.evaluate_regions; wv4_cfg=configs/phd/wu_vallet_regions_v4/evaluation_v4.json ;;
  comparison) wv4_id=PHD-WU-VALLET-REGIONS-COMPARISON-v4; wv4_module=scripts.phd.wu_vallet_regions_v4.compose_comparison; wv4_cfg=configs/phd/wu_vallet_regions_v4/comparison_v4.json ;;
  viewer) wv4_id=PHD-WU-VALLET-REGIONS-VIEWER-v4; wv4_module=scripts.phd.wu_vallet_regions_v4.build_comparison_viewer; wv4_cfg=configs/phd/wu_vallet_regions_v4/viewer_v4.json ;;
  *) exit 2 ;;
esac
wv4_id=${3:-$wv4_id}
wv4_cfg=${4:-$wv4_cfg}
wv4_run="$wv4_base/$wv4_id"
wv4_source="$wv4_base/${wv4_id}_source"
wv4_image=sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774
docker image inspect "$wv4_image" >/dev/null
wv4_head=$(git -C "$wv4_repo" rev-parse HEAD)
mkdir -p "$wv4_base"
mkdir "$wv4_run"
python3 - "$wv4_repo" "$wv4_source" <<'PY'
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
wv4_mounts=(--mount "type=bind,src=$wv4_artifacts,dst=/artifacts/JointBuildGS,readonly")
# Hide evaluation-only raw UAS for every candidate-producing stage. Older frozen
# reference crops may coexist in artifact storage but are not opened by these modules.
if [[ "$wv4_stage" != evaluation && "$wv4_stage" != viewer ]]; then
  wv4_mounts+=(--mount "type=bind,src=/dev/null,dst=/artifacts/JointBuildGS/phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz,readonly")
fi
docker run --rm --name "jbgs-${wv4_id,,}" --network none --cpus 4 --memory 18g \
  --entrypoint python --mount "type=bind,src=$wv4_source,dst=/workspace/JointBuildGS,readonly" \
  "${wv4_mounts[@]}" --mount "type=bind,src=$wv4_run,dst=/output" --workdir /workspace/JointBuildGS \
  --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=4 --env OPENBLAS_NUM_THREADS=1 \
  --env MPLCONFIGDIR=/tmp/matplotlib \
  --env "JBGS_SOURCE_GIT_HEAD=$wv4_head" --env "JBGS_CONTAINER_IMAGE_ID=$wv4_image" \
  --env "JBGS_SOURCE_SNAPSHOT_MANIFEST=$wv4_source/SOURCE_MANIFEST.json" \
  "$wv4_image" -m "$wv4_module" --config "$wv4_cfg" --output /output/run "${wv4_extra[@]}" \
  2>&1 | tee "$wv4_base/${wv4_id}.console.log"

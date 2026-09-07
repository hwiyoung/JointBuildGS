#!/usr/bin/env bash
set -euo pipefail
p3_mode=${1:?preflight, ray, b, evaluation, or viewer}
p3_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
p3_artifacts=$(realpath "$p3_repo/../JointBuildGS-artifacts")
p3_parent="$p3_artifacts/phase-payloads/phd/wu_vallet_p3_v1"
case "$p3_mode" in
 preflight) p3_id=PHD-WU-VALLET-P3-v1; p3_module=scripts.phd.wu_vallet_p3_v1.preflight; p3_cfg=configs/phd/wu_vallet_p3_v1/p3_v1.json; p3_dest=/output ;;
 b) p3_id=PHD-WU-VALLET-P3-B-DEVELOPMENT-v1; p3_module=scripts.phd.wu_vallet_p3_v1.b_development; p3_cfg=configs/phd/wu_vallet_p3_v1/b_development_v1.json; p3_dest=/output/run ;;
 ray) p3_id=PHD-WU-VALLET-RAY-FIXTURE-v1; p3_module=scripts.phd.wu_vallet_p3_v1.run_ray_fixture; p3_cfg=configs/phd/wu_vallet_p3_v1/ray_fixture_v1.json; p3_dest=/output/run ;;
 image) p3_id=PHD-WU-VALLET-P3-IMAGE-SENSOR-MESH-v1; p3_module=scripts.phd.wu_vallet_p3_v1.image_sensor_mesh; p3_cfg=configs/phd/wu_vallet_p3_v1/image_sensor_mesh_v1.json; p3_dest=/output/run ;;
 image-v2) p3_id=PHD-WU-VALLET-P3-IMAGE-SENSOR-MESH-v2; p3_module=scripts.phd.wu_vallet_p3_v1.image_sensor_mesh; p3_cfg=configs/phd/wu_vallet_p3_v1/image_sensor_mesh_v2.json; p3_dest=/output/run ;;
 evaluation) p3_id=PHD-WU-VALLET-P3-EVALUATION-v1; p3_module=scripts.phd.wu_vallet_p3_v1.evaluate; p3_cfg=configs/phd/wu_vallet_p3_v1/evaluation_v1.json; p3_dest=/output/evaluation ;;
 viewer) p3_id=PHD-WU-VALLET-P3-VIEWER-v1; p3_module=scripts.phd.wu_vallet_p3_v1.build_viewer; p3_cfg=; p3_dest=/output/viewer ;;
 *) exit 2 ;;
esac
p3_id=${2:-$p3_id}
p3_run="$p3_parent/$p3_id"
p3_snapshot="$p3_parent/${p3_id}_source"
p3_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
p3_head=$(git -C "$p3_repo" rev-parse HEAD)
mkdir -p "$p3_parent"
mkdir "$p3_run"
# Copy code/config/metadata bytes before execution so other tasks may continue editing.
python3 - "$p3_repo" "$p3_snapshot" <<'PY'
import sys,pathlib,subprocess,shutil,hashlib,json
repo,out=map(pathlib.Path,sys.argv[1:]);out.mkdir(exist_ok=False)
paths=subprocess.check_output(['git','-C',str(repo),'ls-files','--cached','--others','--exclude-standard','-z','src','scripts','configs','tests','artifacts/manifests','AGENTS.md','requirements.txt']).decode().split('\0')
rows={}
for name in sorted(set(paths)-{''}):
 p=repo/name
 if not p.is_file():continue
 target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
 rows[name]=hashlib.sha256(target.read_bytes()).hexdigest()
(out/'SOURCE_MANIFEST.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps({'snapshot':str(out),'files':len(rows)}))
PY
p3_extra=()
p3_args=()
if [[ -n "$p3_cfg" ]]; then p3_args+=(--config "$p3_cfg"); fi
if [[ "$p3_mode" == evaluation || "$p3_mode" == viewer ]]; then
 p3_args+=(--b-root /artifacts/JointBuildGS/phase-payloads/phd/wu_vallet_p3_v1/PHD-WU-VALLET-P3-B-DEVELOPMENT-v1/run)
fi
if [[ "$p3_mode" == evaluation ]]; then
 p3_args+=(--common /artifacts/JointBuildGS/phase-payloads/phd/wu_vallet_p3_v1/PHD-WU-VALLET-P3-v1-r2/common/native.npz)
fi
if [[ "$p3_mode" == viewer ]]; then
 p3_args+=(--evaluation /artifacts/JointBuildGS/phase-payloads/phd/wu_vallet_p3_v1/PHD-WU-VALLET-P3-EVALUATION-v1-r2/evaluation)
fi
if [[ "$p3_mode" == b ]]; then
 p3_cache="$p3_parent/${p3_id}_cache"
 p3_oldcache="$p3_artifacts/phase-payloads/phd/p2_ab_v4/PHD-P2-AB-V4-B-RUNTIME-v1"
 p3_overlay="$p3_artifacts/phase-payloads/phd/p2_ab_v2/PHD-P2-AB-V2-B-GEOMETRY-ADAPTER-v2/overlay"
 p3_adapter_snapshot="$p3_parent/${p3_id}_adapter"
 mkdir "$p3_adapter_snapshot"
 cp "$p3_overlay/../adapter_manifest.json" "$p3_adapter_snapshot/"
 cp "$p3_overlay/rasterize_to_pixels_2dgs_fwd.cu" "$p3_overlay/rasterize_to_pixels_2dgs_bwd.cu" "$p3_adapter_snapshot/"
 mkdir "$p3_cache"
 cp -a "$p3_oldcache/." "$p3_cache/"
 p3_extra+=(--gpus '"device=1"' --mount "type=bind,src=$p3_cache,dst=/root/.cache/torch_extensions")
 for p3_cuda in rasterize_to_pixels_2dgs_fwd.cu rasterize_to_pixels_2dgs_bwd.cu; do
   p3_extra+=(--mount "type=bind,src=$p3_adapter_snapshot/$p3_cuda,dst=/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/$p3_cuda,readonly")
 done
 p3_extra+=(--env JBGS_P2_GEOMETRY_ADAPTER=c4_c8_v1 --env JBGS_GSPLAT_MEDIAN_IS_SURFACE_SUM=1)
 p3_extra+=(--env "JBGS_GEOMETRY_ADAPTER_SNAPSHOT=/artifacts/JointBuildGS/phase-payloads/phd/wu_vallet_p3_v1/${p3_id}_adapter")
fi
docker run --rm --name "jbgs-${p3_id,,}" --network none --cpus 6 --memory 24g --entrypoint python \
 --mount "type=bind,src=$p3_snapshot,dst=/workspace/JointBuildGS,readonly" \
 --mount "type=bind,src=$p3_artifacts,dst=/artifacts/JointBuildGS,readonly" \
 --mount "type=bind,src=$p3_run,dst=/output" --workdir /workspace/JointBuildGS \
 --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=1 --env MAX_JOBS=2 \
 --env "JBGS_SOURCE_GIT_HEAD=$p3_head" --env "JBGS_CONTAINER_IMAGE_ID=$p3_image" \
 --env "JBGS_SOURCE_SNAPSHOT_MANIFEST=$p3_snapshot/SOURCE_MANIFEST.json" \
 "${p3_extra[@]}" "$p3_image" -m "$p3_module" "${p3_args[@]}" --output "$p3_dest" \
 2>&1 | tee "$p3_parent/${p3_id}.console.log"

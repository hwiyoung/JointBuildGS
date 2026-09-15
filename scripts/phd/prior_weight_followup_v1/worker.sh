#!/usr/bin/env bash
set -euo pipefail
bundle="$(realpath "${1:?bundle}")";gpu="${2:?gpu}";shift 2
payload=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd
base="$payload/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
parent="$payload/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
viewer="$parent/viewer_rgb_v1"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
cpu=(docker run --rm --runtime runc --network none --cpus 2 --memory 12g --user "$(id -u):$(id -g)" -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 -e MPLCONFIGDIR=/tmp/mpl)
refresh() {
 exec 8>"$bundle/refresh.lock";flock 8
 "${cpu[@]}" -v "$bundle:/bundle:ro" -v "$viewer:/viewer" "$image" python /bundle/scripts/refresh.py >> "$bundle/refresh.log" 2>&1
 flock -u 8;exec 8>&-
}
region=NONE;stage=START
finish() { code=$?;if [[ "$code" -ne 0 && "$region" != NONE ]];then printf 'FAIL %s exit=%s\n' "$stage" "$code" > "$bundle/$region/status.txt";refresh || true;fi; }
trap finish EXIT
"${cpu[@]}" -v "$bundle:/bundle:ro" "$image" python /bundle/scripts/verify_bundle.py
for region in "$@"; do
 exp="$bundle/$region";output="$viewer/prior_weights_v1/$region"
 test "$(cat "$exp/status.txt")" = QUEUED
 prefix=region_weight;prov=region_weight_source_provenance.json
 mask=manifest.json;envs=(-e JBGS_REGION_WEIGHT_MASK=/mask/manifest.json -e JBGS_REGION_WEIGHT_ALPHA=4)
 anchor="$base/runs_allocator_v2/$region/D005_Pnative/model/jbgs_complete/iteration_8000"
 if [[ "$region" == P1 ]];then
  prefix=p1_weight;prov=p1_single_view_weight_source_provenance.json;mask=r1_mask.npz
  envs=(-e JBGS_P1_WEIGHT_MASK=/mask/r1_mask.npz -e JBGS_P1_WEIGHT_MASK_KEY=r1_mask -e JBGS_P1_WEIGHT_ALPHA=4 -e JBGS_P1_WEIGHT_TARGET_CAMERA=DJI_20241217084553_0100_D)
  anchor="$base/runs/P1/D005_Pnative/model/jbgs_complete/iteration_8000"
 fi
 mask_sha="$(sha256sum "$exp/mask/$mask" | cut -d ' ' -f1)"
 if [[ "$region" == P1 ]];then envs+=(-e JBGS_P1_WEIGHT_MASK_SHA256="$mask_sha");else envs+=(-e JBGS_REGION_WEIGHT_MASK_SHA256="$mask_sha");fi
 for phase in preflight train; do
  stage="${phase^^}_PRIOR_0005_R1_4";printf '%s\n' "$stage" > "$exp/status.txt";refresh
  exec 9>"/tmp/jbgs-p1-single-view-gpu-$gpu.lock";flock 9
  while (( $(nvidia-smi --id="$gpu" --query-gpu=memory.used --format=csv,noheader,nounits) > 1500 ));do sleep 30;done
  run="$exp/$phase/alpha_4";test ! -e "$run";mkdir -p "$run"
  gate=();[[ "$phase" == train ]] && gate=(-v "$exp/gate.json:/gate.json:ro")
  command=(docker run --rm --name "jbgs-prior0005-$region-$phase-$(basename "$bundle")" --network none --gpus "device=$gpu" --cpus 8 --memory 32g --shm-size 4g --user "$(id -u):$(id -g)"
   -e JBGS_RUNTIME_IMAGE_ID="$image" -e JBGS_MVS_PGSR_MODE=mvs -e JBGS_MVS_REGION="$region"
   -e JBGS_MVS_CONFIG=/experiment.json -e JBGS_MVS_CONFIG_SHA256="$(sha256sum "$parent/inputs_v2/experiment.json" | cut -d ' ' -f1)"
   -e JBGS_MVS_BINDING=/mvs/bindings.json -e JBGS_MVS_BINDING_SHA256="$(sha256sum "$parent/inputs_v2/$region/bindings.json" | cut -d ' ' -f1)"
   "${envs[@]}" -e TORCH_HOME=/weights/torch -e MPLCONFIGDIR=/tmp/mpl -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
   -e OMP_NUM_THREADS=8 -e OPENBLAS_NUM_THREADS=8 -e PYTHONDONTWRITEBYTECODE=1 -e PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128
   -v "$exp/scripts:/audit:ro" -v "$exp/parent_scripts:/parent_scripts:ro" -v "$exp/source:/source:ro"
   -v "$exp/config.json:/task_config.json:ro" -v "$exp/mask:/mask:ro" -v "$parent/inputs_v2/experiment.json:/experiment.json:ro"
   -v "$parent/inputs_v2/$region:/mvs:ro" -v "$base/inputs/$region:/input:ro" -v "$anchor:/anchor:ro"
   -v "$base/runtime/weights:/weights:ro" -v "$run:/output" "${gate[@]}" "$image" python /audit/run_phase.py --phase "$phase" --alpha 4)
  printf '%q ' "${command[@]}" > "$run/docker_command.sh"
  "${command[@]}" > "$exp/$phase.driver.log" 2>&1
  flock -u 9;exec 9>&-
  if [[ "$phase" == preflight ]];then
   stage=VALIDATING_PREFLIGHT;printf '%s\n' "$stage" > "$exp/status.txt";refresh
   "${cpu[@]}" -v "$exp:/experiment" -v "$exp/parent_scripts:/parent_scripts:ro" -v "$bundle/scripts:/audit:ro" "$image" python /audit/gate.py > "$exp/gate.log" 2>&1
  fi
 done
 stage=EXTRACTION;printf '%s\n' "$stage" > "$exp/status.txt";refresh
 publish_cpu() {
  "${cpu[@]}" -v "$exp/scripts:/driver:ro" -v "$parent/sources/GeoGS-mvs-pgsr-v1:/source:ro" -v "$base/inputs/$region:/input:ro" \
   -v "$exp:/experiment:ro" -v "$exp/viewer_config.json:/viewer_config.json:ro" -v "$output:/output" "$image" python /driver/viewer_publish.py "$@"
 }
 publish_cpu stage --alpha 4 > "$exp/display_stage.log" 2>&1
 exec 9>"/tmp/jbgs-p1-single-view-gpu-$gpu.lock";flock 9
 while (( $(nvidia-smi --id="$gpu" --query-gpu=memory.used --format=csv,noheader,nounits) > 1500 ));do sleep 30;done
 docker run --rm --name "jbgs-prior0005-$region-extract" --network none --gpus "device=$gpu" --cpus 8 --memory 32g --shm-size 4g --user "$(id -u):$(id -g)" \
  -e TORCH_HOME=/weights/torch -e MPLCONFIGDIR=/tmp/mpl -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 -e OMP_NUM_THREADS=8 -e OPENBLAS_NUM_THREADS=8 -e PYTHONDONTWRITEBYTECODE=1 -e PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128 \
  -v "$exp/parent_scripts:/finalizer:ro" -v "$exp/legacy_scripts:/legacy:ro" -v "$parent/sources/GeoGS-mvs-pgsr-v1:/source:ro" \
  -v "$base/inputs/$region:/input:ro" -v "$base/runtime/weights:/weights:ro" -v "$output/alpha_4/extraction:/output" \
  "$image" python /finalizer/finalize.py --stage extract > "$exp/extraction.log" 2>&1
 flock -u 9;exec 9>&-
 stage=PUBLISHING;printf '%s\n' "$stage" > "$exp/status.txt";refresh
 publish_cpu publish --alpha 4 > "$exp/publish.log" 2>&1
 printf 'PASS_TRAINED_EXTRACTED_PUBLISHED\n' > "$exp/status.txt";refresh
done

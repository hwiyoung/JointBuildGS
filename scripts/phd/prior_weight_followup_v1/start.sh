#!/usr/bin/env bash
set -euo pipefail
bundle="$(realpath "${1:?prepared bundle}")"
viewer=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/viewer_rgb_v1
test -s "$bundle/preparation.json"
test ! -e "$viewer/prior_weights_v1"
mkdir "$viewer/prior_weights_v1" "$viewer/prior_weights_v1/P1" "$viewer/prior_weights_v1/P2" "$viewer/prior_weights_v1/P3"
cp "${BASH_SOURCE[0]}" "$bundle/launch.sh"
sha256sum "$bundle/launch.sh" > "$bundle/launcher.sha256"
printf '%s\n' "$bundle" > "$viewer/prior_weights_v1/experiment_path.txt"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
docker run --rm --runtime runc --network none --cpus 1 --memory 1g --user "$(id -u):$(id -g)" -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= -e PYTHONDONTWRITEBYTECODE=1 -v "$bundle:/bundle:ro" -v "$viewer:/viewer" "$image" python /bundle/scripts/refresh.py
for gpu in 0 1;do
 regions=(P1 P3);[[ "$gpu" == 1 ]] && regions=(P2)
 unit="jbgs-prior0005-gpu$gpu-$(basename "$bundle" | tr '[:upper:]' '[:lower:]')"
 printf '%s.service\n' "$unit" > "$bundle/gpu$gpu.systemd_unit.txt"
 systemd-run --user --unit="$unit" --description="Prior 0.0005 R1=4: ${regions[*]} training and incremental publication" --property=Type=exec --property=Restart=no \
  --property="StandardOutput=append:$bundle/gpu$gpu.supervisor.log" --property="StandardError=append:$bundle/gpu$gpu.supervisor.log" \
  /usr/bin/bash "$bundle/scripts/worker.sh" "$bundle" "$gpu" "${regions[@]}"
done

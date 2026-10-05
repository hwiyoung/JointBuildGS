#!/usr/bin/env bash
set -euo pipefail
bundle="$(realpath "${1:?bundle}")";region="${2:?P2 or P3}";gpu="${3:?GPU}"
experiment="$bundle/$region"
exec 7>"$experiment/queue.lock";flock -n 7
test ! -e "$experiment/status.txt"
stage=STARTING
finish() { code=$?;if [[ "$code" -ne 0 ]];then printf 'FAIL stage=%s exit=%s\n' "$stage" "$code" > "$experiment/status.txt";bash "$bundle/scripts/viewer_phase.sh" "$bundle" "$region" refresh >> "$experiment/viewer_refresh.log" 2>&1 || true;fi; }
trap finish EXIT
refresh() { bash "$bundle/scripts/viewer_phase.sh" "$bundle" "$region" refresh >> "$experiment/viewer_refresh.log" 2>&1; }
wait_p1() {
 local root=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd
 local status="$root/p1_single_view_weight_v1/PHD-P1-SINGLE-VIEW-WEIGHT-v1/attempt.annotated.uOkHWmgi/status.txt"
 local displayed="$root/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/viewer_rgb_v1/p1_weights_v1/alpha_4/publication.json"
 stage=WAITING_P1_FINAL_PUBLICATION_AND_POSTPROCESS
 printf '%s\n' "$stage" > "$experiment/status.txt";refresh
 while [[ "$(cat "$status")" != PASS_TRAINING_AND_COMPARISON_COMPLETE || ! -s "$displayed" ]]; do
   if [[ "$(cat "$status")" == FAIL* ]]; then printf 'Existing P1 failed; preserve its process and inspect before running new GPU work.\n' >&2;exit 1;fi
   sleep 30
 done
}
# P2 short GPU0 preflights can run while P1 alpha4 occupies GPU1.
if [[ "$region" == P3 ]]; then wait_p1; fi
for alpha in 0 1 4; do
 stage="PREFLIGHT_ALPHA_$alpha";printf '%s\n' "$stage" > "$experiment/status.txt";refresh
 bash "$bundle/scripts/run_phase.sh" "$bundle" "$region" preflight "$alpha" "$gpu" > "$experiment/preflight-alpha$alpha.driver.log" 2>&1
done
stage=VALIDATING_PREFLIGHTS;printf '%s\n' "$stage" > "$experiment/status.txt";refresh
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
docker run --rm --runtime runc --network none --cpus 2 --memory 3g --user "$(id -u):$(id -g)" \
 -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= -e PYTHONDONTWRITEBYTECODE=1 \
 -v "$experiment:/experiment" -v "$bundle/source:/experiment/source:ro" -v "$bundle/scripts:/audit:ro" \
 "$image" python /audit/validate_gate.py --root /experiment > "$experiment/gate.log" 2>&1
if [[ "$region" == P2 ]]; then wait_p1; fi
for alpha in 0 1 4; do
 stage="TRAINING_ALPHA_$alpha";printf '%s\n' "$stage" > "$experiment/status.txt";refresh
 bash "$bundle/scripts/run_phase.sh" "$bundle" "$region" train "$alpha" "$gpu" > "$experiment/train-alpha$alpha.driver.log" 2>&1
 stage="DISPLAY_PROCESSING_ALPHA_$alpha";printf '%s\n' "$stage" > "$experiment/status.txt";refresh
 bash "$bundle/scripts/viewer_phase.sh" "$bundle" "$region" publish "$alpha" "$gpu" > "$experiment/display-alpha$alpha.driver.log" 2>&1
done
printf 'PASS_ALL_THREE_TRAINED_AND_PUBLISHED\n' > "$experiment/status.txt";refresh

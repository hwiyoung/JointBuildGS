#!/usr/bin/env bash
# Independent systemd supervisor owns this immutable three-condition experiment.
set -euo pipefail
experiment="$(realpath "${1:?experiment directory}")"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
exec 8>"$experiment/queue.lock"
flock -n 8
test ! -e "$experiment/status.txt"
stage=STARTING
on_exit() {
  code=$?
  if [[ "$code" -ne 0 ]]; then
    printf 'FAIL stage=%s exit=%s\n' "$stage" "$code" > "$experiment/status.txt"
    printf '%s\n' "Failure retained in $experiment; stage=$stage; exit=$code" > "$experiment/failure.txt"
  fi
}
trap on_exit EXIT
run_pair() {
  local phase="$1" result=0 p0 p1
  bash "$experiment/scripts/run_phase.sh" "$experiment" "$phase" 0 0 > "$experiment/$phase-alpha0.driver.log" 2>&1 &
  p0=$!
  bash "$experiment/scripts/run_phase.sh" "$experiment" "$phase" 1 1 > "$experiment/$phase-alpha1.driver.log" 2>&1 &
  p1=$!
  wait "$p0" || result=1
  wait "$p1" || result=1
  return "$result"
}
stage=PREFLIGHT_ALPHA_0_1
printf '%s\n' "$stage" > "$experiment/status.txt"
run_pair preflight
stage=PREFLIGHT_ALPHA_4
printf '%s\n' "$stage" > "$experiment/status.txt"
bash "$experiment/scripts/run_phase.sh" "$experiment" preflight 4 1 > "$experiment/preflight-alpha4.driver.log" 2>&1
stage=VALIDATING_PREFLIGHTS
printf '%s\n' "$stage" > "$experiment/status.txt"
docker run --rm --runtime runc --network none --cpus 2 --memory 3g \
  --user "$(id -u):$(id -g)" --env NVIDIA_VISIBLE_DEVICES=void --env CUDA_VISIBLE_DEVICES= \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$experiment,dst=/experiment" \
  "$image" python /experiment/scripts/validate_gate.py --root /experiment > "$experiment/gate.log" 2>&1
stage=TRAINING_ALPHA_0_1
printf '%s\n' "$stage" > "$experiment/status.txt"
run_pair train
stage=TRAINING_ALPHA_4
printf '%s\n' "$stage" > "$experiment/status.txt"
bash "$experiment/scripts/run_phase.sh" "$experiment" train 4 1 > "$experiment/train-alpha4.driver.log" 2>&1
stage=POSTPROCESSING
printf '%s\n' "$stage" > "$experiment/status.txt"
bash "$experiment/scripts/postprocess.sh" --experiment-dir "$experiment" --gpu 1 > "$experiment/postprocess.driver.log" 2>&1
printf '%s\n' PASS_TRAINING_AND_COMPARISON_COMPLETE > "$experiment/status.txt"

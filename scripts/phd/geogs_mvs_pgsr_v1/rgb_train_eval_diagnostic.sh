#!/usr/bin/env bash
# Immutable CPU diagnostic of saved RGB only; no GPU or new training/rendering.
set -euo pipefail
diagnostic_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
diagnostic_artifact="$(realpath "$diagnostic_repo/../JointBuildGS-artifacts")"
diagnostic_base="$diagnostic_artifact/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
diagnostic_task="$diagnostic_artifact/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
diagnostic_parent="$diagnostic_task/viewer_rgb_v1/rgb_diagnostic_v1"
diagnostic_image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
[[ "$#" -le 1 ]] || { printf '%s\n' 'Expected zero arguments or one existing empty output attempt.' >&2; exit 2; }
mkdir -p "$diagnostic_parent"
if [[ "$#" -eq 1 ]]; then
  diagnostic_out="$(realpath "$1")"
  [[ "$diagnostic_out" == "$diagnostic_parent"/attempt.* ]]
  [[ -d "$diagnostic_out" && -z "$(ls -A "$diagnostic_out")" ]]
else
  diagnostic_out="$(mktemp -d "$diagnostic_parent/attempt.XXXXXXXX")"
fi
test "$(docker image inspect "$diagnostic_image" --format '{{.Id}}')" = "$diagnostic_image"
cp -p "$diagnostic_repo/scripts/phd/geogs_mvs_pgsr_v1/rgb_train_eval_diagnostic.py" "$diagnostic_out/rgb_train_eval_diagnostic.py"
cp -p "${BASH_SOURCE[0]}" "$diagnostic_out/rgb_train_eval_diagnostic.sh"
cp -p "$diagnostic_repo/configs/phd/geogs_mvs_pgsr_v1/rgb_train_eval_v1.json" "$diagnostic_out/config.json"
cp -p "$diagnostic_repo/scripts/phd/geogs_p1p2p3_v1/evaluation/render_quality.py" "$diagnostic_out/legacy_render_quality.py"
git -C "$diagnostic_repo" rev-parse HEAD > "$diagnostic_out/operator_head.txt"
diagnostic_command=(docker run --rm --read-only --network none --cpus 2 --memory 6g --memory-swap 6g
  --user "$(id -u):$(id -g)" --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges
  --tmpfs /tmp:rw,nosuid,size=512m --env PYTHONDONTWRITEBYTECODE=1
  --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=2 --env MKL_NUM_THREADS=2
  --env "DIAGNOSTIC_IMAGE_ID=$diagnostic_image" --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
  --mount "type=bind,src=$diagnostic_artifact,dst=/artifacts/JointBuildGS,readonly"
  --mount "type=bind,src=$diagnostic_base,dst=/base,readonly"
  --mount "type=bind,src=$diagnostic_task,dst=/task,readonly"
  --mount "type=bind,src=$diagnostic_out,dst=/out"
  --mount "type=bind,src=$diagnostic_out/config.json,dst=/config.json,readonly"
  --mount "type=bind,src=$diagnostic_out/legacy_render_quality.py,dst=/legacy_render_quality.py,readonly"
  "$diagnostic_image" python /out/rgb_train_eval_diagnostic.py)
printf '%q ' "${diagnostic_command[@]}" > "$diagnostic_out/command.sh"
printf '\n' >> "$diagnostic_out/command.sh"
printf '%s\n' "$diagnostic_out"
set +e
"${diagnostic_command[@]}" > "$diagnostic_out/run.log" 2>&1
diagnostic_exit=$?
set -e
printf '%s\n' "$diagnostic_exit" > "$diagnostic_out/exit_code.txt"
if [[ "$diagnostic_exit" -eq 0 && -s "$diagnostic_out/manifest.json" && -s "$diagnostic_out/receipt.json" ]]; then
  diagnostic_pointer="$(mktemp "$diagnostic_parent/latest.XXXXXXXX.tmp")"
  printf '{"manifest_url":"/data/rgb_diagnostic_v1/%s/manifest.json","scientific_verdict":null}\n' "$(basename "$diagnostic_out")" > "$diagnostic_pointer"
  mv -T "$diagnostic_pointer" "$diagnostic_parent/latest.json"
fi
cat "$diagnostic_out/run.log"
printf '%s\n' "$diagnostic_out/receipt.json"
exit "$diagnostic_exit"

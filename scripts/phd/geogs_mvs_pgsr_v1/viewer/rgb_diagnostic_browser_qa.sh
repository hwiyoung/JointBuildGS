#!/usr/bin/env bash
# Actual saved-RGB diagnostic browser QA in a new CPU-only container.
set -euo pipefail
qa_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
qa_task="$(realpath "$qa_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1")"
qa_image=sha256:5043f84d76db9d54e64fcf457125aad90ac5423fded88eca6cf487d2b4713a9e
qa_url=http://127.0.0.1:8910/app/rgb_diagnostic.html
[[ "$#" -eq 0 ]] || { printf '%s\n' 'This QA wrapper accepts only the frozen RGB diagnostic URL.' >&2; exit 2; }
test "$(docker image inspect jointbuildgs:geogs-viewer-browser-v2 --format '{{.Id}}')" = "$qa_image"
mkdir -p "$qa_task/viewer_rgb_v1/rgb_diagnostic_v1/browser_qa"
qa_output="$(mktemp -d "$qa_task/viewer_rgb_v1/rgb_diagnostic_v1/browser_qa/attempt.$(date -u +%Y%m%dT%H%M%SZ).XXXXXXXX")"
for qa_file in rgb_diagnostic_browser_qa.mjs rgb_diagnostic_browser_qa.sh; do
  cp -p "$qa_repo/scripts/phd/geogs_mvs_pgsr_v1/viewer/$qa_file" "$qa_output/$qa_file"
done
for qa_file in rgb_diagnostic.html rgb_diagnostic.js rgb_diagnostic.css; do
  cp -p "$qa_repo/src/apps/geogs_rgb_comparison_v1/$qa_file" "$qa_output/app_$qa_file"
done
git -C "$qa_repo" rev-parse HEAD > "$qa_output/operator_head.txt"
qa_command=(docker run --rm --read-only --init --network host --cpus 2 --memory 6g --memory-swap 6g
  --user "$(id -u):$(id -g)"
  --pids-limit 256 --cap-drop ALL --security-opt no-new-privileges
  --tmpfs /tmp:rw,nosuid,size=1g --shm-size 512m
  --env "GEOGS_QA_IMAGE_ID=$qa_image" --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=2
  --mount "type=bind,src=$qa_output/rgb_diagnostic_browser_qa.mjs,dst=/qa/rgb_diagnostic_browser_qa.mjs,readonly"
  --mount "type=bind,src=$qa_output,dst=/out"
  "$qa_image" /qa/rgb_diagnostic_browser_qa.mjs "$qa_url" /out)
printf '%q ' "${qa_command[@]}" > "$qa_output/command.sh"
printf '\n' >> "$qa_output/command.sh"
printf '%s\n' "$qa_output"
set +e
"${qa_command[@]}" > "$qa_output/run.log" 2>&1
qa_exit=$?
set -e
printf '%s\n' "$qa_exit" > "$qa_output/exit_code.txt"
if [[ ! -s "$qa_output/receipt.json" ]]; then
  printf '{"schema":"GEOGS_RGB_DIAGNOSTIC_BROWSER_QA_v1","status":"FAIL_BROWSER_PROCESS","exit_code":%s,"scientific_verdict":null}\n' "$qa_exit" > "$qa_output/receipt.json"
  qa_exit=1
fi
(cd "$qa_output" && sha256sum -- ./* > SHA256SUMS)
cat "$qa_output/run.log"
printf '%s\n' "$qa_output/receipt.json"
exit "$qa_exit"

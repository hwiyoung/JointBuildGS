#!/usr/bin/env bash
set -euo pipefail
bundle="$(realpath "${1:?bundle}")"
out="${2:-$bundle/completion_check}"
trap 'code=$?; if [[ "$code" -ne 0 ]]; then printf "FAIL_FINAL_CHECK exit=%s\n" "$code" >> "$out/status.txt"; fi' EXIT
while true;do
 completed=0
 for region in P1 P2 P3;do
  status="$(cat "$bundle/$region/status.txt")"
  if [[ "$status" == FAIL* ]];then printf 'FAIL %s %s\n' "$region" "$status" > "$out/status.txt";exit 1;fi
  [[ "$status" == PASS_TRAINED_EXTRACTED_PUBLISHED ]] && completed=$((completed+1))
 done
 [[ "$completed" == 3 ]] && break
 sleep 30
done
printf 'CHECKING_FINAL_VIEWER\n' > "$out/status.txt"
mkdir "$out/browser"
docker run --rm --runtime runc --network host --cpus 2 --memory 4g --user "$(id -u):$(id -g)" -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= -e JBGS_REQUIRE_COMPLETE=1 \
 -v "$out:/out" --entrypoint node sha256:5043f84d76db9d54e64fcf457125aad90ac5423fded88eca6cf487d2b4713a9e /out/browser_qa.mjs /out/browser > "$out/browser.log" 2>&1
printf 'PASS_ALL_THREE_TRAINED_PUBLISHED_BROWSER_VERIFIED\n' > "$out/status.txt"

#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="$(realpath "$repo/../JointBuildGS-artifacts")"
parent="$artifact_root/phase-payloads/phd/manual_region_masks_v1/PHD-P2P3-MANUAL-REGIONS-v1"
output="$(mktemp -d "$parent/browser_qa.XXXXXXXX")"
cp -p "$repo/scripts/phd/manual_region_masks_v1/"{browser_qa.mjs,run_browser_qa.sh} "$output/"
printf '%s\n' "$output" > /tmp/jbgs_P2P3_region_browser_qa.txt
image=sha256:5043f84d76db9d54e64fcf457125aad90ac5423fded88eca6cf487d2b4713a9e
command=(docker run --rm --runtime runc --network host --cpus 2 --memory 2g --shm-size 256m
 --user "$(id -u):$(id -g)" -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES=
 -e XDG_CONFIG_HOME=/tmp/config -e XDG_CACHE_HOME=/tmp/cache -v "$output:/out"
 --entrypoint node "$image" /out/browser_qa.mjs /out)
printf '%q ' "${command[@]}" > "$output/command.sh"
printf '\n' >> "$output/command.sh"
"${command[@]}" > "$output/run.log" 2>&1
printf '%s\n' "$output"

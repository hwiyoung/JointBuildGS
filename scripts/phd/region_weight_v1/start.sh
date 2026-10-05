#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
bundle="$(realpath "${1:?prepared bundle}")"
artifact="$(realpath "$repo/../JointBuildGS-artifacts")"
viewer="$artifact/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/viewer_rgb_v1/p2p3_weights_v1"
[[ -s "$bundle/preparation.json" && -s "$bundle/cpu_tests.log" ]]
sha256sum --check --status "$bundle/frozen_files.sha256"
test ! -e "$viewer"
mkdir "$viewer" "$viewer/P2" "$viewer/P3"
cp -p "${BASH_SOURCE[0]}" "$bundle/launch.sh"
sha256sum "$bundle/launch.sh" > "$bundle/launcher.sha256"
printf '%s\n' "$bundle" > "$viewer/experiment_path.txt"
for region in P2 P3; do
 bash "$bundle/scripts/viewer_phase.sh" "$bundle" "$region" refresh > "$bundle/$region/viewer_initialize.log" 2>&1
done
for region in P2 P3; do
 gpu=0;[[ "$region" == P3 ]] && gpu=1
 unit="jbgs-${region,,}-region-weights-$(basename "$bundle" | tr '[:upper:]' '[:lower:]')"
 printf '%s.service\n' "$unit" > "$bundle/$region/systemd_unit.txt"
 systemd-run --user --unit="$unit" --description="$region R1 0/1/4 training and per-condition viewer publication" \
  --property=Type=exec --property=Restart=no --property="StandardOutput=append:$bundle/$region/supervisor.log" \
  --property="StandardError=append:$bundle/$region/supervisor.log" \
  /usr/bin/bash "$bundle/scripts/run_queue.sh" "$bundle" "$region" "$gpu"
done
printf '%s\n' "$bundle" 'http://127.0.0.1:8910/app/p2p3_weights.html'

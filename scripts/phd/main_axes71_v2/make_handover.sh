#!/usr/bin/env bash
# PHD-MAIN-AXES71-v2 전달 묶음 (order 14): AX/handover/PHD-MAIN-AXES71-v2_handover.zip (docs, configs, scripts, payload tables/logs/receipts/json;
# no per-point npz/npy or meshes) and ..._handover_light.zip (report, numbers, tables, figures only). scientific_verdict: null.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); AX=$(realpath "$REPO/../JointBuildGS-artifacts/phase-payloads/phd/main_axes71_v2/PHD-MAIN-AXES71-v2")
OUT="$AX/handover"; mkdir -p "$OUT"; ST=$(mktemp -d); trap 'rm -rf "$ST"' EXIT
D="$ST/PHD-MAIN-AXES71-v2"; mkdir -p "$D/repo" "$D/payload"
( cd "$REPO" && cp -r --parents docs/experiments/phd/main_axes71_v2 configs/phd/main_axes71_v2 scripts/phd/main_axes71_v2 "$D/repo/" )
( cd "$AX" && find tables logs work -maxdepth 2 \( -name '*.json' -o -name '*.log' -o -name '*.md' -o -name '*.py' \) -print0 | xargs -0 cp --parents -t "$D/payload/" )
( cd "$AX" && find mvs -maxdepth 2 \( -name '*.json' -o -name '*.log' \) -print0 | xargs -0 cp --parents -t "$D/payload/" )
( cd "$AX" && find dist dist9 -maxdepth 1 -name '*.json' -print0 | xargs -0 cp --parents -t "$D/payload/" )
rm -f "$OUT/PHD-MAIN-AXES71-v2_handover.zip" "$OUT/PHD-MAIN-AXES71-v2_handover_light.zip"
( cd "$ST" && zip -qr "$OUT/PHD-MAIN-AXES71-v2_handover.zip" PHD-MAIN-AXES71-v2 )
L="$ST/light/PHD-MAIN-AXES71-v2_light"; mkdir -p "$L"
( cd "$REPO/docs/experiments/phd/main_axes71_v2" && cp -r . "$L/" )
( cd "$ST/light" && zip -qr "$OUT/PHD-MAIN-AXES71-v2_handover_light.zip" PHD-MAIN-AXES71-v2_light )
for z in "$OUT"/*.zip; do echo "$(basename "$z") $(du -h "$z" | cut -f1) $(unzip -l "$z" | tail -1 | awk '{print $2}') files sha256 $(sha256sum "$z" | cut -c1-16)"; done

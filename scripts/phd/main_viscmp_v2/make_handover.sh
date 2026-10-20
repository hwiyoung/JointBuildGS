#!/usr/bin/env bash
# PHD-MAIN-VISCMP-v2 handover zip (request 5): report, request, figures (png, pdf, json), config, lock, scripts, logs, places, SHA256SUMS.
# No point cloud, mesh or original photo.   bash make_handover.sh -> PH/main_viscmp_v2/PHD-MAIN-VISCMP-v2/handover/PHD-MAIN-VISCMP-v2_handover.zip
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
VC="$ART/phase-payloads/phd/main_viscmp_v2/PHD-MAIN-VISCMP-v2"; OUT="$VC/handover"; ST="$OUT/stage/PHD-MAIN-VISCMP-v2"
rm -rf "$OUT/stage"; mkdir -p "$ST/configs" "$ST/scripts" "$ST/payload_records/prep" "$ST/payload_records/logs"
cp -r "$REPO/docs/experiments/phd/main_viscmp_v2" "$ST/docs"
cp "$REPO/configs/phd/main_viscmp_v2/"*.json "$ST/configs/"
cp "$REPO/scripts/phd/main_viscmp_v2/"*.py "$REPO/scripts/phd/main_viscmp_v2/"*.sh "$ST/scripts/"
cp "$VC/config_lock.json" "$ST/payload_records/"; cp "$VC/prep/"*.json "$ST/payload_records/prep/"; cp "$VC/logs/"*.log "$ST/payload_records/logs/"
(cd "$ST" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
rm -f "$OUT/PHD-MAIN-VISCMP-v2_handover.zip"; (cd "$OUT/stage" && zip -qr "$OUT/PHD-MAIN-VISCMP-v2_handover.zip" PHD-MAIN-VISCMP-v2); rm -rf "$OUT/stage"
ls -la "$OUT/PHD-MAIN-VISCMP-v2_handover.zip"; sha256sum "$OUT/PHD-MAIN-VISCMP-v2_handover.zip"; unzip -l "$OUT/PHD-MAIN-VISCMP-v2_handover.zip" | tail -1

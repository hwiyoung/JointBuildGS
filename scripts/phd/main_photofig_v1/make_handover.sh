#!/usr/bin/env bash
# PHD-MAIN-PHOTOFIG-v1 handover zip (request 7): reports, request, tables, figures + number json + the cropped photos used, config, config
# lock, scripts, logs, small payload records (prep/*.json, crop/*inventory.json), SHA256SUMS. No point cloud, mesh or original photo.
#   bash make_handover.sh <1|final>  -> PF/handover/PHD-MAIN-PHOTOFIG-v1_handover_1.zip | PHD-MAIN-PHOTOFIG-v1_handover.zip
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
PF="$ART/phase-payloads/phd/main_photofig_v1/PHD-MAIN-PHOTOFIG-v1"; OUT="$PF/handover"; ST="$OUT/stage/PHD-MAIN-PHOTOFIG-v1"
name=$([ "${1:-final}" = "1" ] && echo PHD-MAIN-PHOTOFIG-v1_handover_1.zip || echo PHD-MAIN-PHOTOFIG-v1_handover.zip)
rm -rf "$OUT/stage"; mkdir -p "$ST/configs" "$ST/scripts" "$ST/payload_records"
cp -r "$REPO/docs/experiments/phd/main_photofig_v1" "$ST/docs"
cp "$REPO/configs/phd/main_photofig_v1/"*.json "$ST/configs/"
cp "$REPO/scripts/phd/main_photofig_v1/"*.py "$REPO/scripts/phd/main_photofig_v1/"*.sh "$ST/scripts/"
cp "$PF/config_lock.json" "$ST/payload_records/"; [ -f "$PF/receipt_task.json" ] && cp "$PF/receipt_task.json" "$ST/payload_records/"
mkdir -p "$ST/payload_records/prep" "$ST/payload_records/logs" "$ST/payload_records/crop"
cp "$PF/prep/"*.json "$ST/payload_records/prep/"; cp "$PF/logs/"*.log "$ST/payload_records/logs/"; cp "$PF/crop/"*_inventory.json "$ST/payload_records/crop/" 2>/dev/null || true
(cd "$ST" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
rm -f "$OUT/$name"; (cd "$OUT/stage" && zip -qr "$OUT/$name" PHD-MAIN-PHOTOFIG-v1); rm -rf "$OUT/stage"
ls -la "$OUT/$name"; sha256sum "$OUT/$name"; unzip -l "$OUT/$name" | tail -1

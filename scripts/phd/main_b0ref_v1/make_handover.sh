#!/usr/bin/env bash
# PHD-MAIN-B0REF-v1 handover zip (request 10): report, request, tables, figures + number json, config, config lock, scripts, logs,
# small payload records (prep/*.json, sel/*.json, dist/*.json), SHA256SUMS. No point-cloud file (npz, laz, ply) goes in.
#   bash make_handover.sh   -> PH/main_b0ref_v1/PHD-MAIN-B0REF-v1/handover/PHD-MAIN-B0REF-v1_handover.zip
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
B0="$ART/phase-payloads/phd/main_b0ref_v1/PHD-MAIN-B0REF-v1"; OUT="$B0/handover"; ST="$OUT/stage/PHD-MAIN-B0REF-v1"
rm -rf "$OUT/stage"; mkdir -p "$ST"
cp -r "$REPO/docs/experiments/phd/main_b0ref_v1" "$ST/docs"
mkdir -p "$ST/configs" "$ST/scripts" "$ST/payload_records"
cp "$REPO/configs/phd/main_b0ref_v1/"*.json "$ST/configs/"
cp "$REPO/scripts/phd/main_b0ref_v1/"*.py "$REPO/scripts/phd/main_b0ref_v1/"*.sh "$ST/scripts/"
cp "$B0/config_lock.json" "$ST/payload_records/" 2>/dev/null || true
[ -f "$B0/receipt_task.json" ] && cp "$B0/receipt_task.json" "$ST/payload_records/"
for d in prep sel dist logs; do
  mkdir -p "$ST/payload_records/$d"
  find "$B0/$d" -maxdepth 1 -type f \( -name '*.json' -o -name '*.log' -o -name '*.md' \) -exec cp {} "$ST/payload_records/$d/" \;
done
mkdir -p "$ST/payload_records/dl_sha256"; (cd "$B0/dl" && find . -type f -name '*.*' ! -name '*.laz' -printf '%p\n' > /dev/null; find . -type f -exec sha256sum {} \; > "$ST/payload_records/dl_sha256/SHA256SUMS_downloaded.txt")
(cd "$ST" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
rm -f "$OUT/PHD-MAIN-B0REF-v1_handover.zip"
(cd "$OUT/stage" && zip -qr "$OUT/PHD-MAIN-B0REF-v1_handover.zip" PHD-MAIN-B0REF-v1)
rm -rf "$OUT/stage"
ls -la "$OUT/PHD-MAIN-B0REF-v1_handover.zip"; sha256sum "$OUT/PHD-MAIN-B0REF-v1_handover.zip"
unzip -l "$OUT/PHD-MAIN-B0REF-v1_handover.zip" | tail -1

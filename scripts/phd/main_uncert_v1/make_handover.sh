#!/usr/bin/env bash
# PHD-MAIN-UNCERT-v1 전달 묶음 (order 9): PHD-MAIN-UNCERT-v1_handover.zip (보고서, 숫자표, 표, 그림과 json, 설정, 스크립트, 로그, progress.md,
# SHA256SUMS; 점 파일·패치 값 없음) and PHD-MAIN-UNCERT-v1_handover_light.zip (보고서, 숫자표, 표, 그림). Written to the payload's handover/.
# scientific_verdict: null.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_uncert_v1/PHD-MAIN-UNCERT-v1"; H="$OUT/handover"; ST="$H/stage"
rm -rf "$ST"; mkdir -p "$ST/docs" "$ST/configs" "$ST/scripts" "$ST/logs"
cp -r "$REPO/docs/experiments/phd/main_uncert_v1/." "$ST/docs/"
cp -r "$REPO/configs/phd/main_uncert_v1/." "$ST/configs/"
cp "$REPO/scripts/phd/main_uncert_v1/"*.py "$REPO/scripts/phd/main_uncert_v1/"*.sh "$ST/scripts/"
cp "$OUT/logs/"*.log "$ST/logs/"; cp "$OUT/progress.md" "$ST/"
cp "$OUT/work/"*.json "$ST/logs/" 2>/dev/null || true; mkdir -p "$ST/logs/blind"; cp "$OUT/work/blind/"*.md "$ST/logs/blind/"
(cd "$ST" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
rm -f "$H/PHD-MAIN-UNCERT-v1_handover.zip" "$H/PHD-MAIN-UNCERT-v1_handover_light.zip"
(cd "$ST" && zip -qr "$H/PHD-MAIN-UNCERT-v1_handover.zip" .)
(cd "$ST/docs" && zip -qr "$H/PHD-MAIN-UNCERT-v1_handover_light.zip" . -x "*.pdf")
ls -la "$H"/*.zip; sha256sum "$H"/*.zip

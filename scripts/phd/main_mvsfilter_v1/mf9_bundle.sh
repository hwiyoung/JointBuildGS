#!/usr/bin/env bash
# 묶음 만들기 (발주 10절): PHD-MAIN-MVSFILTER-v1_<가|나|다>_<월일>-<시분>_light.zip
# 담는 것: 보고서·표·그림(+json)·설정(잠금 포함)·스크립트·issues/progress·patches_<prior>(csv.gz; parquet 도구 없음, issues.md)·SHA256SUMS
# 사용: mf9_bundle.sh <가|나|다>
set -euo pipefail
B="$1"; H=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$H/../../.." && pwd)
O=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_mvsfilter_v1/PHD-MAIN-MVSFILTER-v1
NAME="PHD-MAIN-MVSFILTER-v1_${B}_$(date +%m%d-%H%M)_light"; ST="$O/delivery/stage_$NAME/PHD-MAIN-MVSFILTER-v1"
mkdir -p "$ST" "$O/delivery"
cd "$REPO"
for d in configs/phd/main_mvsfilter_v1 docs/experiments/phd/main_mvsfilter_v1; do mkdir -p "$ST/$d"; cp -r "$d/." "$ST/$d/"; done
mkdir -p "$ST/scripts/phd/main_mvsfilter_v1"; cp scripts/phd/main_mvsfilter_v1/*.{py,sh,cpp} "$ST/scripts/phd/main_mvsfilter_v1/"
mkdir -p "$ST/payload"; for f in "$O"/judge/patches_*.csv.gz; do [[ -f $f ]] && cp "$f" "$ST/payload/"; done
for f in "$O"/masks/*.json "$O"/fusion/*/fusion_receipt.json "$O"/fusion/*/fusion.log; do [[ -f $f ]] || continue; [[ $B == 가 && $(basename $f) =~ ^(B|C) ]] && continue; { r=${f#$O/}; mkdir -p "$ST/payload/$(dirname $r)"; cp "$f" "$ST/payload/$r"; }; done
for p in LoD2 ALS; do [[ -d "$O/judge/$p" ]] && { mkdir -p "$ST/payload/judge/$p"; cp "$O"/judge/$p/checks_*.json "$ST/payload/judge/$p/" 2>/dev/null || true; }; done
echo "commit $(git rev-parse HEAD)  branch $(git rev-parse --abbrev-ref HEAD)  made $(date -Iseconds)" > "$ST/BUNDLE_INFO.txt"
( cd "$ST" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS )
( cd "$O/delivery/stage_$NAME" && zip -qr "$O/delivery/$NAME.zip" PHD-MAIN-MVSFILTER-v1 )
rm -rf "$O/delivery/stage_$NAME"
ls -la "$O/delivery/$NAME.zip"; sha256sum "$O/delivery/$NAME.zip"

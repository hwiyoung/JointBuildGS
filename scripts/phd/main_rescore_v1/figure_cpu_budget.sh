#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
for prior in ALS LoD2; do
 name="jbgs-rescore-fig-cache-$prior"
 until docker inspect "$name" >/dev/null 2>&1; do sleep 15; done
 docker update --cpus 16 "$name" >/dev/null
 printf -- '- %s: %s CPU 상한 16; 그림용 동일 거리 계산과 메모리 제한 유지.\n' "$(date -Is)" "$name" >> "$REPO/docs/experiments/phd/main_rescore_v1/progress.md"
done

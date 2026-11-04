#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1/addendum3_stage2
DOC="$REPO/docs/experiments/phd/main_rescore_v1/addendum3_stage2"
run="$REPO/scripts/phd/main_rescore_v1/run_stage2.sh"
site=$1
exec 9>"$OUT/dispatch-$site.lock"
flock -n 9 || exit 0
worker() {
 local prior=$1
 bash "$REPO/scripts/phd/main_rescore_v1/s2_ft_queue.sh" "$site" "$prior"
 bash "$run" "$site-$prior-fig-cache-complete" s2_figures.py prepare "$site" "$prior"
 bash "$run" "$site-$prior-fig-draw" s2_figures.py draw "$site" "$prior"
 bash "$run" "$site-$prior-fig-preview" s2_preview.py "${site}__그림7_3_${prior}.png" "${site}__그림7_4_${prior}.png" "${site}__그림7_5_${prior}.png" "${site}__그림7_6_${prior}.png" "${site}__그림7_7_${prior}.png"
 printf -- '- %s: %s %s FINALTRAIN 메시·채점·그림 생성 완료. 그림의 최초 시각 검토와 최종 묶음 점검은 대기.\n' "$(TZ=Asia/Seoul date -Iseconds)" "$site" "$prior" >> "$DOC/progress.md"
}
bash "$run" "$site-arrival-dispatch" s2_arrival_events.py "$site" | {
 pids=()
 while read -r status event_site prior; do
  [[ "$event_site" == "$site" && ( "$prior" == ALS || "$prior" == LoD2 ) ]] || continue
  if [[ "$status" == READY ]]; then
   printf -- '- %s: %s %s 완료 영수증 이벤트 수신; 기존 단계 2의 메시·채점·그림 대기열 시작.\n' "$(TZ=Asia/Seoul date -Iseconds)" "$site" "$prior" >> "$DOC/progress.md"
   worker "$prior" > "$OUT/logs/${site}_${prior}_arrival_queue.log" 2>&1 &
   pids+=("$!")
  elif [[ "$status" == UNAVAILABLE ]]; then
   printf -- '- %s: %s %s FINALTRAIN terminal receipt; receipt의 실패 이유를 최종 보고에 명시하고 대체 학습하지 않음.\n' "$(TZ=Asia/Seoul date -Iseconds)" "$site" "$prior" >> "$DOC/issues.md"
  fi
 done
 failed=0
 for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
   failed=1
   printf -- '- %s: %s 완료 이벤트 후처리 오류. logs/*_arrival_queue.log의 원인을 확인해 완료 캐시 다음 단계부터 재개 필요.\n' "$(TZ=Asia/Seoul date -Iseconds)" "$site" >> "$DOC/issues.md"
  fi
 done
 exit "$failed"
}

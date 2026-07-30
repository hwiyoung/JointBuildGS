# A-prime 산출물 정리 정책

> 활성 실험의 입력·체크포인트·실패 기록을 삭제하지 않고 Git 표시와 검수 동선을
> 정리하기 위한 정책이다.

## Git에 선별 보존

- 사전등록·대상 명단·issues
- T1--T5의 정본 receipt·요약 CSV
- job별 학습 완료 receipt와 체크포인트 SHA 기록
- job별 panel-v4, opacity CSV, 검토용 Roofer CityJSON, panel 완료 receipt
- queue lock, terminal status, stage-stop 및 완료 receipt
- `RESULTS_INDEX.md`

## 로컬 보존·Git ignore

- 전처리 materialization payload와 `.staging`
- 30k 체크포인트, TensorBoard, 학습 로그
- TSDF 중간 NPZ·대용량 PLY/LAS/GPKG
- queue action/service 로그, runtime environment, 실행 lock
- 별도 정본이 있는 smoke-recovery의 원시 readout 트리
- superseded `review_v3`와 미완성 `report_v2`

이 파일들은 재현·후속 readout 의존성이 있으므로 활성 queue 종료 전 삭제하지 않는다.

## 종료 후에만 재검토

- 실패한 A-prime preprocess v1 캐시
- 2026-07-24 arm A의 전처리·체크포인트
- T2 receipt history와 실패 attempt 원시 payload

최종 T2와 모든 job의 provenance가 고정된 뒤 참조 관계를 검사하고 archive 또는 삭제 여부를
별도 task로 결정한다.

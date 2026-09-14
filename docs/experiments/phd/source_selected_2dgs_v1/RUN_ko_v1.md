# 실행 위치와 결과 읽기

`PHD-SOURCE-SELECTED-2DGS-v1` · `scientific_verdict: null`

실행 payload는 다음 외부 저장소의 독립 attempt에 있다.

```
../JointBuildGS-artifacts/phase-payloads/phd/source_selected_2dgs_v1/
  PHD-SOURCE-SELECTED-2DGS-v1/attempt_20260915_RFYU8S/
```

정확한 해석과 고정 파라미터는 `PLAN_ko_v1.md`와
`configs/phd/source_selected_2dgs_v1/experiment.json`에 있다.
원 workspace의 기존 변경 내용은 유지하며, 실행은 `source_snapshot`의 별도 복사본을
읽는다. 소스 준비 이후 바뀐 config나 준비 코드는 launch 검사에서 거부한다.

## 완료된 준비 검증

P1/P2/P3의 40개 시점, 전체 155개 준비 파일과 모든 표본의 원 카메라/픽셀 ID를
독립 CPU 감사에서 확인했다. P2는 Prior 550개를 제거하고 MVS 539개를 넣었으며,
P3는 98개를 98개로 교체했다. P1은 양쪽 모두 동일한 Prior 1,389개다.
수정 가능 MVS 표본 총 637개는 원래 채택된 13개 7×7 패치에 정확히 대응한다.
기존 Gaussian을 실제 수정한 결과가 아니라 새 실험의 소스 구성 결과다.

`preparation_audit/results/receipt.json`은 원본 ID·소스 기하·교체 조건·투영 마스크 및
주변 보존을 확인한다. `runtime_preflight_cpu/prepared_P1.json`–`prepared_P3.json`은
학습기가 읽는 실제 배열을 별도로 검사했다. 이 준비 PASS는 GPU 학습 완료를 뜻하지 않는다.

## 상태 및 산출물

| 위치 | 의미 |
|---|---|
| `status.txt`, `queue.pid`, `queue.log` | 현재 대기/학습/평가/완료 또는 실패 상태와 독립 프로세스 |
| `launch_receipt.json` | 준비 입력, 실행 소스/config, Docker, 승인 범위의 시작 기록 |
| `background_status_receipt.json` | 독립 PID/SID와 기존 실험 우선 대기가 실제로 동작한 시작 시점 기록 |
| `prepared/P1`–`P3` | 단계 1–5, 원본 ID, 소스 채택/유보 마스크와 카메라 |
| `runtime_preflight_cpu/receipt.json` | GPU를 사용하지 않은 stock CUDA 확장 컴파일 결과 |
| `gpu_preflight/P2_source_selected/receipt.json` | GPU 확보 후 실제 전방/역방향 및 픽셀 좌표 검사 |
| `training/P*/prior_only`, `training/P*/source_selected` | 각 2,000 step, 0/50/200/500/2000 checkpoint와 동일 시점 렌더 |
| `report/index.html`, `report/data.json` | 모바일 대응 8단계 화면과 수치, 현재 상태 자동 조회 |
| `report/receipt.json` | 모든 학습 봉인 후 별도 UAS 진단 및 보고서 생성 기록 |
| `completion_receipt.json` | 여섯 학습 결과와 GPU 검사 및 최종 보고서의 기술 완료 |

준비 보고서는 학습 전 단계 1–5를 보여주고 단계 6–8은 대기로 표시한다. 완료된
학습이 없는 동안 전후 효과를 0 또는 성공으로 표시하지 않는다. 웹 화면은 이 컴퓨터의
`http://127.0.0.1:8909/report/`에서 읽기 전용으로 제공한다. 이 loopback 주소 자체는
외부 휴대전화 접속 주소가 아니다. 최종 모바일 PNG/PDF는 같은 report에 생성한다.

대기열은 `nohup` + `setsid`로 터미널과 분리한다. 기존 MVS/PGSR 학습 단계가 끝나고
GPU0의 여유 메모리·사용률이 3회 연속 기준을 통과해야 다음 GPU 작업을 시작한다.
호스트 전원 종료를 넘기는 자동 재시작은 없다. 실패 시 부분 산출물과 오류 로그를
보존하고 자동 재시도하지 않는다. 완료는 상태 파일과 로컬 데스크톱 알림으로 남긴다.

학습 컨테이너에는 UAS 평가 참조를 제공하지 않는다. 학습 후 별도 컨테이너에서
동일 원 UAS 표본 ID로 비교한다. 직접 소스 교체의 차이, GS 최적화의 차이,
두 조건 최종 결과의 차이를 별도로 읽어야 한다.

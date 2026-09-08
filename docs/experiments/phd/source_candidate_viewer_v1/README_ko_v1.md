# P1/P2/P3 단계별 소스 후보 뷰어

Task: `PHD-SOURCE-CANDIDATE-VIEWER-v1` · `scientific_verdict: null`

2026-09-08 사용자가 보고서 사진의 가독성 개선과 영역별 단계 뷰어를 요청하여 구현했다.
뷰어는 `PHD-SOURCE-CANDIDATE-P1P2P3-v1`의 고정 결과를 읽는다. 현재 시점의 재판단이나
GS 학습을 실행하지 않는다. 초기 method/evaluation/원영상 해시를 확인하고, 영상쌍을
선택할 때 그 쌍의 저장된 관측 비용을 재생성해 대조한다.

## 사용 흐름

1. P1/P2/P3 중 영역을 선택한다. 같은 셀 선택을 유지하며 후보 입력·관측 평가·소스 판단
   단계를 바꿀 수 있다. 기본 사례는 P1 셀 16, P2 셀 5, P3 셀 43이다.
2. 후보 입력에서는 MVS·ALS native point를 회전·확대하고 영역 전체와 선택 셀을 비교한다.
   지도에서 셀을 고르거나 셀 번호로 이동한다. 표시용 원행 부분집합은 정량 평가에 쓰지 않는다.
3. 관측 평가에서는 원본 anchor/target 사진을 크게 열고 확대·이동한다. 실제 평가에 쓰인
   영상쌍과 패치를 선택하면 두 후보의 투영 위치·warp·공통 마스크를 함께 볼 수 있다.
   사진 파일은 원래 JPG를 그대로 제공한다. 확대가 원본에 없는 세부를 생성하지는 않는다.
4. 소스 판단에서는 IMAGE/PRIOR/ABSTAIN 지도, 판단 이유, 관측 근거, 고정 후 계산된
   UAS 거리값을 확인한다. 관측이 없거나 조건을 충족하지 못한 셀도 선택할 수 있다.

## 입력·서버 범위

- method 산출물, 원 native MVS·ALS, camera/view ledger, 원 RGB는 읽기 전용 마운트.
- 원 UAS geometry는 마운트하지 않고 고정된 사후 평가 JSON만 읽는다.
- 3D 표시 최대 60,000점/소스, 원 좌표를 평균하지 않는 행 부분집합.
- 원영상 경로는 정확한 regional RGB ledger에 등록된 ID로만 제공.
- 같은 저장 영상쌍에서 후보별 median 비용이 원래 값과 절대차 `1e-6` 이내인지 검사.
- 뷰어/API는 읽기 전용이다. 기존 8891–8902 뷰어와 다른 서비스는 교체하지 않는다.
- 브라우저 검증은 화면·상호작용 검증이며 연구 방법의 정확도 판정이 아니다.

## 재현

설정: `configs/phd/source_candidate_viewer_v1/viewer.json`.
host launcher는 표준 라이브러리로 source snapshot·Docker 실행·receipt만 처리하고,
project dependency 및 테스트는 Docker에서 실행한다.

```bash
/usr/bin/python3 scripts/phd/source_candidate_viewer_v1/run_local.py start --viewer-id NEW_VIEWER_ID
/usr/bin/python3 scripts/phd/source_candidate_viewer_v1/run_local.py qa --viewer-id NEW_VIEWER_ID --qa-id qa-v1
/usr/bin/python3 scripts/phd/source_candidate_viewer_v1/run_local.py status
```

기본 URL은 `http://127.0.0.1:8903/`이다. 포트가 사용 중이면 기존 서비스를 보존하고 중단한다.
이 작업의 label이 일치하는 뷰어를 수정한 버전으로 교체할 때만 `--replace-own`을 사용하며,
이전 source snapshot·실패 로그·QA 결과는 유지한다.

실행·QA payload는 sibling artifact backend의
`phase-payloads/phd/source_candidate_viewer_v1/<VIEWER_ID>/`에 저장한다.
최종 실행 URL·검증 수·source hash는 이 폴더의 receipt와 repository artifact manifest로 확인한다.

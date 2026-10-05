# 표면 표시 보완과 봉인 전 검증

2026-09-08 09:17 KST · `PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

표시 코드 보완과 합성 검증을 완료했다. **실제 세 지역 결과 화면 검증은 아직 아니다.** P1 주6개 필수 산출물 완료, P2 첫 두 조건 학습 중에 수행했으며 지역 품질값과 UAS payload는 열지 않았다. 공식 source·학습 제어·조건·평가 입력·문턱·표본화·사례 선택 규칙은 유지했다.

## 확인한 문제와 수정

기존 화면은 source 단색도 RGB 배열이 있다는 이유로 실제 RGB로 안내했고, 존재하지 않는 `source_count`를 읽어 원 평가 표본 수를 누락했다. 이를 실제 metadata에 연결해 표시 표본 수, 전체 평가 표본 수, 원 ROI 점 수, 면적 표본 간격, 평가 점/참조 voxel과 표시 voxel·상한을 구분했다. 단색·최근접 원 mesh 정점에서 옮긴 표시 색·실제 원 RGB의 출처도 구분한다.

기존 TSDF 화면은 면적 표본의 점 표시였다. 새 실제 삼각면 모드는 평가 과정이 이미 계산한 `clipped_vertices`와 `clipped_triangles`를 그대로 내보낸다. 추가 clipping·간소화·정점/삼각형 재정렬·인공 경계면·재표본화·재채점은 없다. 정점 파일은 local float64, 연결은 uint32이며, 기존 거리 BVH의 `float32_local_metric` 및 WebGL float32 표시와 각각 구분한다. float64 파일이 모든 거리 계산의 float64를 뜻하지 않는다.

원 ALS 입력 PLY와 공식 raw/post PLY 다운로드는 봉인된 경로·SHA·크기에 연결한다. 원 파일은 입력 문맥 또는 전체 TSDF 추출 범위를 포함하고, 표시 삼각면은 고정 XYZ 평가 prism으로 잘린 표면 부분이다. 표면 색은 소스/높이 표시용이며, 참조 거리 색은 기존 평가 표본 보기에서 제공한다. 실제 사진·GeoGS 렌더 비교는 별도다. 단면 그림도 같은 평가 표본의 고정0.5m 폭 구간이며 정확한 삼각형–평면 교차선이라고 부르지 않는다.

참조와 예측 표본이 모두0인 경계는 `no_geometry_reference_absent`와 “표시 기하 없음 · 참조 부재로 품질평가 불가”로 표시한다. 원 metric은 계속 `NOT_ASSESSED_REFERENCE_ABSENT`, F1은 null이다. 참조 없는 양의 기하는 계속 볼 수 있고, 참조가 있는 빈 예측은 기존 복원 실패/F1=0 정책을 유지한다. 이 경계를 실제 지역에서 관측했다고 주장하지 않는다.

## 실제 검증 근거

`$TASK`는 sibling `JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`이다.

| 검증 | 실제 결과 | 외부 증거 경로 |
|---|---|---|
| 관련 Python 검사 |58/58 PASS, skip0 | `runtime/display_review_v1/cpu_validation_v2/receipt.json` |
| 수치 경로 보존 | 기하·렌더 품질·sealer·resource support 전체 hash 및 기존 수치/선택 함수 등의56개 가드 PASS | 같은 경로의 `non_scientific_change_guards.json`, before/after diff |
| 최종 합성 브라우저 |433/433 assertions PASS. 실제 draw/triangle/pixel, 점↔면, raw/post·512/1024, 지연 응답, legacy 입력, 참조 부재 경계 | `runtime/display_review_v1/synthetic_browser_reference_absence_v2/attempt.jt3H1S/` |
| 최종 실제QA 코드의 합성 검사 |20/20 PASS. 실제 지역 QA 실행은 아님 | `runtime/display_review_v1/actual_qa_code_validation_v1/validation_receipt.json` |
| root 결합 CPU 검사 |133개 중130 PASS/3 SKIP/실패0, shell syntax9 PASS,8.371초 | `runtime/display_integration_validation_v1/receipt.json` |

결합 검사의3 SKIP은 공식 code/cache mount가 없는 `NativeMetricParityTests`이며 이번 PASS로 집계하지 않는다. 위 검사들은 서로 겹치므로 개수를 합쳐 독립 검사 수로 주장하지 않는다. 명령·Docker image·source/config/test 사본·로그·exit와 SHA가 각 경로에 있다. root는 이전 성공 합성 화면의 `mesh_512_raw.png`와 `mesh_1024_raw.png`도 직접 열어 면/점 분리, 선택 추출 미가용 및 색·표본 계보 안내를 확인했다.

수정 전37개 파일은 `runtime/display_review_v1/before_repo/`와 `before_receipt.json`에 보존했고, 이후 참조 부재 경계 수정 전의 구현·검증도 별도 사본으로 남겼다. 초기 브라우저 두 실패도 보존했다. `attempt.qoj3Jw`는 crashpad `--database is required`, `attempt.pm7XOQ`는 SwiftShader의 `VK_KHR_surface`/`VK_KHR_xcb_surface` 미지원으로 초기화에 실패했다. 새 container 전용 XDG 경로와 기존 private Xvfb·ANGLE GL·소프트웨어 Mesa 경로에서 성공했다. 학습 GPU나 기존 host X 세션은 사용하지 않았다.

## 남은 실제 결과 검증

모든21개 후보 봉인과 정량·사례 산출 후 다음 실제 QA를 새 경로에서 실행한다.

```bash
bash scripts/phd/geogs_p1p2p3_v1/viewer/browser_qa.sh full_results_display_v1 \
  'http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/viewer/manifest_v2.json&qa_mode=full'
```

최종 QA는 등록된 지역·조건·해상도·raw/post를 점/면 모드에서 순회해 실제 primitive 수와 표시 pixel을 검사한다. 명시적 기하 부재를 가짜 면 screenshot이나 과학적 실패로 바꾸지 않는다. root의 실제 사례 그림 확인과 해석은 이 자동 QA와 별도로 남는다. 간소화하지 않은 실제 지역 mesh의 브라우저 메모리·표시 속도도 실제 QA에서 확인해야 한다. 현재 주소는 같은 호스트의 loopback 주소다.

표시 export의 파일 I/O는 평가 단계 시간에 추가되며, native 학습·추출 비용 기록을 바꾸지는 않는다. 전체 변경 설명은 `$TASK/runtime/display_review_v1/IMPLEMENTATION_REVIEW.md`, 표시 계약은 [DISPLAY_CONTRACT.md](../../../../scripts/phd/geogs_p1p2p3_v1/evaluation/DISPLAY_CONTRACT.md)에 있다.

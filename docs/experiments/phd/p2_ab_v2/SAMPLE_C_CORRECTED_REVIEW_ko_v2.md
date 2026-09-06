# 수정 C 평가 코드 읽기 검토

2026-09-07. `scientific_verdict: null`. 수정 B 실행 완료 전의 읽기 검토이며,
C/B 코드나 기존 결과를 변경하지 않았다. 실제 수정 renderer의 기하·미분 검산과
새 결과의 유효성 검증은 이 검토 밖이다.

## 확인한 계산 계약

- `GeometryEvaluator`는 기존 v1의 기본 양방향 exact NN, XY 최근접 높이 차이,
  0.25/0.5/1 m 허용 거리와 원점 개수 분모를 유지한다. reference KD 재사용과
  workers=4가 비교 대상을 바꾸지 않는다. 원 v1의 선택적 `forward_reference`
  인터페이스는 새 클래스에 없지만 현재 C는 이 기능을 사용하지 않는다.
- 예측이 비면 reference recall은 0이고 전체 참조 점이 missing으로 남는다.
  거리 요약은 유한 값이 없으므로 null이다. XY가 영역 안이면 잘못된 Z도
  평가에 포함한다. 참조 정확도와 scientific verdict는 null이다.
- XYZ 캐시는 한 실행 안에서만 생성된다. 같은 참조·반경·허용 거리 아래에서
  float64 Nx3의 순서와 중복을 포함한 bytes를 키로 사용한다. 캐시 복사 뒤에
  각 파일의 전체 개수/영역 밖 개수를 붙이므로 다른 파일의 분모가 섞이지 않는다.
  향후 실행 간 영구 캐시로 바꿀 경우에는 참조와 지표 설정의 해시도 필요하다.
- 외관 평가는 주 ALS와 MVS의 학습 전 조건부 관측 support 합집합을 고정하고,
  initial/final과 모든 arm에서 같은 target bytes·카메라·분모를 사용한다.
  예측 RGB가 비거나 검어도 그 픽셀의 오차를 제거하지 않는다.
  plane-hit `geometry_mass >= 0.5` 존재율과 RGB alpha 존재율이 분리된다.
- arm 내부 detail 오차는 initial/final/reference 공통 stencil에서 계산하고,
  arm 간 비교에는 모든 arm·단계의 단일 교집합을 사용한다. 교집합 밖과
  각 arm의 누락 참조 stencil을 별도로 남긴다. 이는 2.5D median 높이 진단이며
  겹층 대응이나 세부 형상 인증이 아니다.
- `c_final_corrected_v2.json`은 `CORRECTED-NATIVE`,
  `CORRECTED-REPRESENTATION`, `CORRECTED-PRIOR-SHIFT` 세 root만 열거한다.
  prior anchor도 수정 NATIVE 실행의 geometry_fixed다. pipeline이 이 목록을
  직접 전달하므로 이전 결과 root를 자동 검색해 혼입하는 경로는 발견하지 못했다.

## 보완 권고와 처리 상태

1. C의 현재 완료 확인은 `result.json` 존재 검사다. 폴더 이름만 수정 실행이고
   실제로 이전 adapter bytes를 사용한 오입력까지 막으려면 root 완료 상태와
   수정 renderer의 명시적 계약/소스 fingerprint를 확인해야 한다. B가 확정할
   새 fingerprint를 root에 전달하도록 요청했다. 현재 config의 경로 분리는
   확인했으나 이 검토가 미래 파일 내용을 미리 보증하지는 않는다.
2. 외관 코드는 geometry mass의 유한성·범위를 확인하나 RGB alpha에는 같은
   검사가 없다. NaN alpha가 존재율 집계에서 조용히 false가 되는 것을 막는
   검사와 예상 arm/view 수 확인을 root에 권고했다. 현재 데이터에서 NaN이
   관측됐다는 주장은 아니다.
3. 뷰어 exporter가 누락된 사진 triple을 건너뛰고 기존 QA는 `images > 0`만
   요구했다. 수정된 소유 QA는 각 arm에 고정된 11개 평가 ID가 중복 없이 모두
   있어야 통과한다. arm ID 중복과 선택적 예상 arm 수 검사도 추가했다.
   수정 최종 QA 명령은 마지막 인수로 `12`를 지정한다. 기존 1,040개 통과
   기록과 당시 소스는 보존하며 새 검사를 소급 적용했다고 하지 않는다.

기존 4개 Docker 테스트의 통과는 root가 보고했고 코드를 읽어 해당 범위를 확인했다.
이 읽기 검토에서 프로젝트 테스트를 다시 실행하지 않았다. 새 브라우저 QA source는
Node 기본 구문 검사만 통과했으며 수정 결과를 대상으로 한 실제 브라우저 검사는 대기 중이다.

## 읽은 bytes

| 경로 | SHA256 |
|---|---|
| `src/phd/p2_ab_v2/geometry_evaluation.py` | `5615505371ae2a146f09ff7cb103ca88bb291a7a1022ed621234f123f2bab2de` |
| `scripts/phd/p2_ab_v2/c_evaluate.py` | `90d2ce97271c8d92ce06c135116c1ee1f331b8ac6b7e8f585c8b6e769be63aa1` |
| `scripts/phd/p2_ab_v2/c_common_appearance.py` | `b02a988a01bc5e2328d1d885b2aed3bb187bb3a5e21c03754bfe523b32104132` |
| `scripts/phd/p2_ab_v2/c_pipeline.py` | `7ec60c624a2c5863da1a58cdc6a2e7fda11f5bd755395e76a75ff1e271a1f5c3` |
| `configs/phd/p2_ab_v2/c_final_corrected_v2.json` | `c2579b00f16f77f696d86f33bb1a5af05140a039922dd70888f4049d2ee5e3fb` |
| 후속 `scripts/phd/p2_ab_v2/c_browser_qa.mjs` | `fdcc69cedb0a4a8f8c7d80f440c7f5c321c22c1ab33d8f6e367f4644746062df` |

## 수정 실행 완료 후 후속 확인

root가 위 권고를 반영한 후 새 source를 다시 읽었다. pipeline은 이제 B root와
각 arm의 `COMPLETED_DEVELOPMENT`, 정확한 arm/평가뷰 집합,
`geometry_contract=independent_plane_hit_v1`를 요구한다. 통과한 adapter 감사와
manifest의 SHA, B가 복사한 감사·manifest bytes, 실제 저장 CUDA source SHA도
대조한다. config는 `GEOMETRY-ADAPTER-v2`와 `ADAPTER-AUDIT-v3/corrected`를
명시적으로 연결한다. 외관 평가의 alpha finite/range 검사와 exporter의 전체
평가뷰 집합 검사도 추가됐다. 최초 읽기 검토의 권고와 해시 기록은 위에 보존했다.

후속 읽기 SHA256:

| 경로 | SHA256 |
|---|---|
| `scripts/phd/p2_ab_v2/c_pipeline.py` | `898dbdd6848e973a75cfba6bd82f42562f6cd2f95dfdca61eedbf2c012c4b364` |
| `scripts/phd/p2_ab_v2/c_common_appearance.py` | `0db19a0cbdd0f84232c72696df44d94baecdd9c9c6424144aa9254259823555c` |
| `scripts/phd/p2_ab_v2/c_viewer_build.py` | `af01455501c36d08fa84482f1c65e767f927374a60d86c483813ecd61015a2bd` |
| `configs/phd/p2_ab_v2/c_final_corrected_v2.json` | `57974274a33b7b2c7808ad90fdf85644ac53064ed9e9c581ca77a01a41e2586b` |

이 확인은 입력 계약과 코드 경로의 감사다. 별도 B adapter 검사와 C 계산 결과를
대체하거나 수정 renderer의 남은 모델링 한계를 없애는 과학적 승인이 아니다.
